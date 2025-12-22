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


