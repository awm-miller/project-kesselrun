"""
Email Sender - Send daily reports via SMTP

Sends HTML emails with PDF attachments to configured subscribers.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("emailer")


class EmailSender:
    """Send reports via SMTP"""
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        from_name: str = "Instagram Monitor"
    ):
        """
        Initialize email sender
        
        Args:
            smtp_server: SMTP server address (e.g., smtp.gmail.com)
            smtp_port: SMTP port (587 for TLS, 465 for SSL)
            username: SMTP username
            password: SMTP password or app password
            from_email: Sender email address
            from_name: Sender display name
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.from_name = from_name
        
        logger.info(f"Email sender configured: {smtp_server}:{smtp_port}")
    
    def send_report(
        self,
        recipients: List[str],
        subject: str,
        html_content: str,
        pdf_attachment: Path = None
    ) -> bool:
        """
        Send report email with optional PDF attachment
        
        Args:
            recipients: List of recipient email addresses
            subject: Email subject
            html_content: HTML email content
            pdf_attachment: Optional path to PDF attachment
        
        Returns:
            True if successful, False otherwise
        """
        if not recipients:
            logger.warning("No recipients specified, skipping email")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(recipients)
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Attach PDF if provided
            if pdf_attachment and pdf_attachment.exists():
                with open(pdf_attachment, 'rb') as f:
                    pdf_part = MIMEBase('application', 'pdf')
                    pdf_part.set_payload(f.read())
                    encoders.encode_base64(pdf_part)
                    pdf_part.add_header(
                        'Content-Disposition',
                        f'attachment; filename="{pdf_attachment.name}"'
                    )
                    msg.attach(pdf_part)
                    logger.debug(f"Attached PDF: {pdf_attachment.name}")
            
            # Send email
            self._send_via_smtp(msg, recipients)
            
            logger.info(f"Email sent successfully to {len(recipients)} recipient(s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _send_via_smtp(self, msg: MIMEMultipart, recipients: List[str]):
        """Send message via SMTP"""
        try:
            # Determine SSL vs TLS
            if self.smtp_port == 465:
                # Use SSL
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=30)
            else:
                # Use TLS (port 587)
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                server.starttls()
            
            # Login
            server.login(self.username, self.password)
            
            # Send
            server.send_message(msg)
            server.quit()
            
            logger.debug("SMTP connection closed successfully")
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            raise
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}")
            raise
    
    def send_daily_report(
        self,
        recipients: List[str],
        username: str,
        date_str: str,
        html_path: Path,
        pdf_path: Path
    ) -> bool:
        """
        Send daily report for a specific account
        
        Args:
            recipients: List of recipient email addresses
            username: Instagram username
            date_str: Date string YYYY-MM-DD
            html_path: Path to HTML report
            pdf_path: Path to PDF report
        
        Returns:
            True if successful, False otherwise
        """
        subject = f"Instagram Monitor Report - @{username} - {date_str}"
        
        # Read HTML content
        try:
            html_content = html_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read HTML file: {e}")
            return False
        
        # Send email with PDF attachment
        return self.send_report(
            recipients=recipients,
            subject=subject,
            html_content=html_content,
            pdf_attachment=pdf_path if pdf_path.exists() else None
        )
    
    def test_connection(self) -> bool:
        """Test SMTP connection and authentication"""
        try:
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10)
                server.starttls()
            
            server.login(self.username, self.password)
            server.quit()
            
            logger.info("SMTP connection test successful")
            return True
            
        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False
    
    def send_daily_summary(
        self,
        recipients: List[str],
        date_str: str,
        account_results: List[Dict[str, Any]],
        pdf_attachments: List[Path] = None
    ) -> bool:
        """
        Send aggregated daily summary email with all flagged content
        
        Args:
            recipients: List of recipient email addresses
            date_str: Date string YYYY-MM-DD
            account_results: List of dicts with keys:
                - username: Instagram username
                - folder_url: Google Drive folder URL
                - total_posts: Number of posts analyzed
                - total_stories: Number of stories analyzed
                - flagged_count: Number of flagged items
                - flagged_items: List of flagged content dicts with:
                    - type: 'post' or 'story'
                    - url: Instagram URL
                    - reason: Why it was flagged
                    - gdrive_url: Google Drive archive URL
                    - media_description: AI analysis
            pdf_attachments: List of PDF report paths to attach
        
        Returns:
            True if successful, False otherwise
        """
        if not recipients:
            logger.warning("No recipients specified, skipping email")
            return False
        
        subject = f"Kessel Run - {date_str}"
        
        # Build HTML email
        html_content = self._build_summary_html(date_str, account_results)
        
        try:
            # Create message with mixed type to support multiple attachments
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = ', '.join(recipients)
            
            # Add HTML body
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            # Attach all PDFs
            if pdf_attachments:
                for pdf_path in pdf_attachments:
                    if pdf_path and pdf_path.exists():
                        with open(pdf_path, 'rb') as f:
                            pdf_part = MIMEBase('application', 'pdf')
                            pdf_part.set_payload(f.read())
                            encoders.encode_base64(pdf_part)
                            pdf_part.add_header(
                                'Content-Disposition',
                                f'attachment; filename="{pdf_path.name}"'
                            )
                            msg.attach(pdf_part)
                            logger.debug(f"Attached PDF: {pdf_path.name}")
            
            # Send email
            self._send_via_smtp(msg, recipients)
            
            logger.info(f"Daily summary sent to {len(recipients)} recipient(s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")
            return False
    
    def _build_summary_html(self, date_str: str, account_results: List[Dict[str, Any]]) -> str:
        """Build HTML content for daily summary email"""
        
        # Count totals
        total_accounts = len(account_results)
        total_flagged = sum(r.get('flagged_count', 0) for r in account_results)
        total_posts = sum(r.get('total_posts', 0) for r in account_results)
        total_stories = sum(r.get('total_stories', 0) for r in account_results)
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'IBM Plex Mono', monospace; margin: 0; padding: 20px; background: #0a0a0a; color: #3eb489; }}
        .container {{ max-width: 800px; margin: 0 auto; background: #111111; border-radius: 8px; border: 1px solid #2a2a2a; }}
        .header {{ background: #0a0a0a; color: #3eb489; padding: 30px; border-radius: 8px 8px 0 0; border-bottom: 1px solid #3eb489; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 22px; font-weight: 600; letter-spacing: -0.5px; }}
        .header .date {{ opacity: 0.7; font-size: 14px; }}
        .stats {{ display: flex; justify-content: center; gap: 60px; padding: 30px 30px 40px 30px; background: #0a0a0a; border-bottom: 1px solid #2a2a2a; margin-bottom: 10px; }}
        .stat {{ text-align: center; min-width: 80px; }}
        .stat-value {{ font-size: 32px; font-weight: 600; color: #3eb489; }}
        .stat-label {{ font-size: 11px; color: #6b6b6b; text-transform: uppercase; letter-spacing: 1px; margin-top: 5px; }}
        .stat-value.flagged {{ color: #ff6b6b; }}
        .section {{ padding: 20px 30px; }}
        .section-title {{ font-size: 14px; font-weight: 600; margin-bottom: 15px; color: #3eb489; border-bottom: 1px solid #2a2a2a; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}
        .account {{ background: #1a1a1a; border-radius: 4px; padding: 15px; margin-bottom: 12px; border-left: 3px solid #3eb489; }}
        .account-header {{ margin-bottom: 10px; }}
        .account-name {{ font-weight: 500; font-size: 14px; color: #3eb489; display: block; margin-bottom: 4px; }}
        .account-name a {{ color: #3eb489; text-decoration: none; }}
        .account-name a:hover {{ text-decoration: underline; }}
        .account-stats {{ font-size: 12px; color: #6b6b6b; display: block; }}
        .drive-link {{ display: inline-block; background: #3eb489; color: #0a0a0a !important; padding: 6px 12px; border-radius: 3px; text-decoration: none; font-size: 12px; margin-top: 8px; font-weight: 500; }}
        .flagged-section {{ background: #1a1212; border-left-color: #ff6b6b; }}
        .flagged-item {{ background: #0a0a0a; border: 1px solid #3a2a2a; border-radius: 4px; padding: 12px; margin-top: 10px; }}
        .flagged-badge {{ background: #ff6b6b; color: #0a0a0a; padding: 2px 8px; border-radius: 2px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
        .flagged-reason {{ margin: 10px 0; font-size: 13px; color: #ccc; }}
        .flagged-description {{ font-size: 12px; color: #888; margin: 10px 0; padding: 12px; background: #1a1a1a; border-radius: 4px; border-left: 2px solid #3eb489; }}
        .flagged-links {{ display: flex; gap: 15px; margin-top: 10px; }}
        .flagged-links a {{ font-size: 11px; color: #3eb489; text-decoration: none; }}
        .flagged-links a:hover {{ text-decoration: underline; }}
        .no-flagged {{ color: #3eb489; font-style: italic; }}
        .footer {{ padding: 25px 30px; text-align: center; color: #4a4a4a; font-size: 11px; border-top: 1px solid #2a2a2a; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Kessel Run</h1>
            <div class="date">{date_str}</div>
        </div>
        
        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total_accounts}</div>
                <div class="stat-label">Accounts</div>
            </div>
            <div class="stat">
                <div class="stat-value">{total_posts}</div>
                <div class="stat-label">Posts</div>
            </div>
            <div class="stat">
                <div class="stat-value">{total_stories}</div>
                <div class="stat-label">Stories</div>
            </div>
            <div class="stat">
                <div class="stat-value flagged">{total_flagged}</div>
                <div class="stat-label">Flagged</div>
            </div>
        </div>
"""
        
        # Accounts section
        html += '<div class="section"><div class="section-title">Accounts Analyzed</div>'
        
        for result in account_results:
            username = result.get('username', 'unknown')
            folder_url = result.get('folder_url', '')
            posts = result.get('total_posts', 0)
            stories = result.get('total_stories', 0)
            flagged = result.get('flagged_count', 0)
            
            html += f"""
            <div class="account">
                <div class="account-header">
                    <span class="account-name">
                        <a href="https://instagram.com/{username}" target="_blank">@{username}</a>
                    </span>
                    <span class="account-stats">{posts} posts, {stories} stories{f', <span style="color:#e53e3e;font-weight:600">{flagged} flagged</span>' if flagged else ''}</span>
                </div>
                {f'<a class="drive-link" href="{folder_url}" target="_blank">📁 View in Google Drive</a>' if folder_url else ''}
            </div>
"""
        
        html += '</div>'
        
        # Flagged content section
        html += '<div class="section"><div class="section-title">Flagged Content</div>'
        
        any_flagged = False
        for result in account_results:
            flagged_items = result.get('flagged_items', [])
            if not flagged_items:
                continue
            
            any_flagged = True
            username = result.get('username', 'unknown')
            
            html += f'<div class="account flagged-section"><div class="account-name">@{username}</div>'
            
            for item in flagged_items:
                item_type = item.get('type', 'post').upper()
                reason = item.get('reason', 'No reason provided')
                description = item.get('media_description', '')
                instagram_url = item.get('url', '')
                gdrive_url = item.get('gdrive_url', '')
                
                html += f"""
                <div class="flagged-item">
                    <span class="flagged-badge">{item_type}</span>
                    <div class="flagged-reason"><strong>Reason:</strong> {reason}</div>
                    {f'<div class="flagged-description">{description}</div>' if description else ''}
                    <div class="flagged-links">
                        {f'<a href="{instagram_url}" target="_blank">🔗 View on Instagram</a>' if instagram_url else ''}
                        {f'<a href="{gdrive_url}" target="_blank">📁 View Archive</a>' if gdrive_url else ''}
                    </div>
                </div>
"""
            
            html += '</div>'
        
        if not any_flagged:
            html += '<p class="no-flagged">✓ No flagged content found today</p>'
        
        html += '</div>'
        
        # Footer
        html += """
        <div class="footer">
            Generated by Kessel Run<br>
            Completed in under 12 parsecs!<br>
            © Bothan Labs 2025<br>
            <em>AI can make mistakes</em>
        </div>
    </div>
</body>
</html>
"""
        
        return html


def load_subscribers(filepath: str = "subscribers.json") -> List[str]:
    """Load subscriber email addresses from JSON file"""
    import json
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            subscribers = data.get("subscribers", [])
            logger.info(f"Loaded {len(subscribers)} subscriber(s)")
            return subscribers
    except FileNotFoundError:
        logger.warning(f"Subscribers file not found: {filepath}")
        return []
    except Exception as e:
        logger.error(f"Failed to load subscribers: {e}")
        return []


