"""
Report Generator - Create HTML and PDF reports for daily Instagram monitoring

Generates comprehensive reports with profile stats, all posts/stories, and flagged content.
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import json
import base64

from jinja2 import Template

logger = logging.getLogger("reporter")


class ReportGenerator:
    """Generate HTML and PDF reports for Instagram analysis"""
    
    def __init__(self, templates_dir: str = "templates"):
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(exist_ok=True)
        
        # Create default templates if they don't exist
        self._ensure_templates_exist()
    
    def _ensure_templates_exist(self):
        """Create default templates if they don't exist"""
        email_template_path = self.templates_dir / "report_email.html"
        if not email_template_path.exists():
            email_template_path.write_text(self._default_email_template(), encoding='utf-8')
            logger.info("Created default email template")
        
        pdf_template_path = self.templates_dir / "report_pdf.html"
        if not pdf_template_path.exists():
            pdf_template_path.write_text(self._default_pdf_template(), encoding='utf-8')
            logger.info("Created default PDF template")
    
    def generate_report(
        self,
        username: str,
        profile: Dict[str, Any],
        summary: str,
        posts: List[Dict[str, Any]],
        stories: List[Dict[str, Any]],
        stats: Dict[str, Any],
        date_str: str
    ) -> Dict[str, str]:
        """
        Generate HTML and PDF reports
        
        Args:
            username: Instagram username
            profile: Profile information dict
            summary: Analysis summary text
            posts: List of analyzed posts
            stories: List of analyzed stories
            stats: Statistics dict
            date_str: Date string YYYY-MM-DD
        
        Returns:
            Dict with 'html' and 'pdf' keys containing file paths
        """
        logger.info(f"Generating report for @{username} ({date_str})")
        
        # Prepare data for templates
        report_data = {
            'username': username,
            'profile': profile,
            'summary': summary,
            'posts': posts,
            'stories': stories,
            'stats': stats,
            'date': date_str,
            'generated_at': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'),
            'flagged_posts': [p for p in posts if p.get('flagged', False)],
            'flagged_stories': [s for s in stories if s.get('flagged', False)],
            'total_flagged': len([p for p in posts if p.get('flagged', False)]) + 
                           len([s for s in stories if s.get('flagged', False)])
        }
        
        # Generate HTML report
        html_path = self._generate_html_report(report_data)
        
        # Generate PDF report
        pdf_path = self._generate_pdf_report(report_data, html_path)
        
        return {
            'html': str(html_path),
            'pdf': str(pdf_path)
        }
    
    def _generate_html_report(self, data: Dict[str, Any]) -> Path:
        """Generate HTML email report"""
        try:
            template_path = self.templates_dir / "report_email.html"
            template = Template(template_path.read_text(encoding='utf-8'))
            
            html_content = template.render(**data)
            
            # Save HTML file
            output_path = Path(f"temp_report_{data['username']}_{data['date']}.html")
            output_path.write_text(html_content, encoding='utf-8')
            
            logger.info(f"Generated HTML report: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate HTML report: {e}")
            raise
    
    def _generate_pdf_report(self, data: Dict[str, Any], html_path: Path) -> Path:
        """Generate PDF report from HTML"""
        try:
            from weasyprint import HTML, CSS
            
            # Use PDF-specific template if available, otherwise use HTML version
            pdf_template_path = self.templates_dir / "report_pdf.html"
            if pdf_template_path.exists():
                template = Template(pdf_template_path.read_text(encoding='utf-8'))
                html_content = template.render(**data)
            else:
                html_content = html_path.read_text(encoding='utf-8')
            
            # Generate PDF
            output_path = Path(f"temp_report_{data['username']}_{data['date']}.pdf")
            
            HTML(string=html_content, base_url=str(self.templates_dir)).write_pdf(
                output_path,
                stylesheets=[CSS(string=self._pdf_styles())]
            )
            
            logger.info(f"Generated PDF report: {output_path}")
            return output_path
            
        except ImportError:
            logger.warning("weasyprint not available, falling back to reportlab")
            return self._generate_pdf_reportlab(data)
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            raise
    
    def _generate_pdf_reportlab(self, data: Dict[str, Any]) -> Path:
        """Fallback PDF generation using ReportLab"""
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            from reportlab.lib import colors
            
            output_path = Path(f"temp_report_{data['username']}_{data['date']}.pdf")
            doc = SimpleDocTemplate(str(output_path), pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=30
            )
            story.append(Paragraph(f"Instagram Monitor Report: @{data['username']}", title_style))
            story.append(Paragraph(f"Date: {data['date']}", styles['Normal']))
            story.append(Paragraph(f"Generated: {data['generated_at']}", styles['Normal']))
            story.append(Spacer(1, 0.3*inch))
            
            # Profile Info
            story.append(Paragraph("Profile Information", styles['Heading2']))
            profile_data = [
                ['Full Name', data['profile'].get('full_name', 'N/A')],
                ['Username', f"@{data['username']}"],
                ['Followers', f"{data['profile'].get('followers', 0):,}"],
                ['Following', f"{data['profile'].get('following', 0):,}"],
                ['Total Posts', f"{data['profile'].get('post_count', 0):,}"]
            ]
            profile_table = Table(profile_data, colWidths=[2*inch, 4*inch])
            profile_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.grey),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(profile_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Summary
            story.append(Paragraph("Analysis Summary", styles['Heading2']))
            story.append(Paragraph(data['summary'], styles['Normal']))
            story.append(Spacer(1, 0.3*inch))
            
            # Statistics
            story.append(Paragraph("Statistics", styles['Heading2']))
            stats_data = [
                ['Posts Analyzed', str(data['stats'].get('total_posts', 0))],
                ['Stories Analyzed', str(data['stats'].get('total_stories', 0))],
                ['Flagged Content', str(data['total_flagged'])]
            ]
            stats_table = Table(stats_data, colWidths=[3*inch, 3*inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.grey),
                ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 0.3*inch))
            
            # Flagged Content
            if data['total_flagged'] > 0:
                story.append(Paragraph("Flagged Content", styles['Heading2']))
                for post in data['flagged_posts']:
                    story.append(Paragraph(f"<b>Post:</b> {post['url']}", styles['Normal']))
                    story.append(Paragraph(f"<b>Reason:</b> {post.get('flag_reason', 'N/A')}", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
                for story_item in data['flagged_stories']:
                    story.append(Paragraph(f"<b>Story:</b> {story_item['url']}", styles['Normal']))
                    story.append(Paragraph(f"<b>Reason:</b> {story_item.get('flag_reason', 'N/A')}", styles['Normal']))
                    story.append(Spacer(1, 0.1*inch))
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"Generated PDF report (reportlab): {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate PDF with reportlab: {e}")
            raise
    
    def _pdf_styles(self) -> str:
        """CSS styles for PDF generation"""
        return """
        @page {
            size: A4;
            margin: 2cm;
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.4;
        }
        h1 {
            color: #1a1a1a;
            font-size: 24pt;
            margin-bottom: 20px;
        }
        h2 {
            color: #333;
            font-size: 16pt;
            margin-top: 20px;
            margin-bottom: 10px;
            border-bottom: 2px solid #ddd;
        }
        .profile-info, .stats {
            background: #f5f5f5;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .flagged {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 10px;
            margin: 10px 0;
        }
        .post {
            margin: 15px 0;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        """
    
    def _default_email_template(self) -> str:
        """Default HTML email template"""
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .header h1 {
            margin: 0;
            font-size: 28px;
        }
        .header .subtitle {
            opacity: 0.9;
            margin-top: 10px;
        }
        .profile-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .profile-info table {
            width: 100%;
            border-collapse: collapse;
        }
        .profile-info td {
            padding: 8px;
            border-bottom: 1px solid #dee2e6;
        }
        .profile-info td:first-child {
            font-weight: bold;
            width: 150px;
        }
        .summary {
            background: #e7f3ff;
            padding: 20px;
            border-left: 4px solid #2196F3;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .stats {
            display: flex;
            justify-content: space-around;
            margin-bottom: 30px;
        }
        .stat-box {
            text-align: center;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            flex: 1;
            margin: 0 10px;
        }
        .stat-box .number {
            font-size: 36px;
            font-weight: bold;
            color: #667eea;
        }
        .stat-box .label {
            color: #666;
            margin-top: 5px;
        }
        .section {
            margin-bottom: 30px;
        }
        .section h2 {
            color: #1a1a1a;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }
        .post {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .post.flagged {
            border-left: 4px solid #dc3545;
            background: #fff5f5;
        }
        .post-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .post-date {
            color: #666;
            font-size: 14px;
        }
        .post-type {
            display: inline-block;
            padding: 3px 8px;
            background: #e7f3ff;
            color: #2196F3;
            border-radius: 4px;
            font-size: 12px;
        }
        .flagged-badge {
            display: inline-block;
            padding: 3px 8px;
            background: #dc3545;
            color: white;
            border-radius: 4px;
            font-size: 12px;
            margin-left: 5px;
        }
        .post-caption {
            margin: 10px 0;
            font-style: italic;
        }
        .post-description {
            margin: 10px 0;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .flag-reason {
            margin-top: 10px;
            padding: 10px;
            background: #fff3cd;
            border-left: 3px solid #ffc107;
            border-radius: 3px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #dee2e6;
            text-align: center;
            color: #666;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Instagram Monitor Report</h1>
        <div class="subtitle">@{{ username }} - {{ date }}</div>
        <div class="subtitle">Generated: {{ generated_at }}</div>
    </div>

    <div class="profile-info">
        <h3>Profile Information</h3>
        <table>
            <tr>
                <td>Username</td>
                <td>@{{ username }}</td>
            </tr>
            <tr>
                <td>Full Name</td>
                <td>{{ profile.full_name }}</td>
            </tr>
            <tr>
                <td>Followers</td>
                <td>{{ "{:,}".format(profile.followers) }}</td>
            </tr>
            <tr>
                <td>Following</td>
                <td>{{ "{:,}".format(profile.following) }}</td>
            </tr>
            <tr>
                <td>Total Posts</td>
                <td>{{ "{:,}".format(profile.post_count) }}</td>
            </tr>
        </table>
    </div>

    <div class="summary">
        <h3>Analysis Summary</h3>
        <p>{{ summary }}</p>
    </div>

    <div class="stats">
        <div class="stat-box">
            <div class="number">{{ stats.total_posts }}</div>
            <div class="label">Posts Analyzed</div>
        </div>
        <div class="stat-box">
            <div class="number">{{ stats.total_stories }}</div>
            <div class="label">Stories Analyzed</div>
        </div>
        <div class="stat-box">
            <div class="number">{{ total_flagged }}</div>
            <div class="label">Flagged Content</div>
        </div>
    </div>

    {% if flagged_posts or flagged_stories %}
    <div class="section">
        <h2>Flagged Content</h2>
        {% for post in flagged_posts %}
        <div class="post flagged">
            <div class="post-header">
                <span>
                    <span class="post-type">{{ 'Video' if post.is_video else 'Image' }}</span>
                    <span class="flagged-badge">FLAGGED</span>
                </span>
                <span class="post-date">{{ post.date[:10] }}</span>
            </div>
            <div><strong>URL:</strong> <a href="{{ post.url }}">{{ post.url }}</a></div>
            {% if post.caption %}
            <div class="post-caption">{{ post.caption[:200] }}{% if post.caption|length > 200 %}...{% endif %}</div>
            {% endif %}
            <div class="flag-reason">
                <strong>Flag Reason:</strong> {{ post.flag_reason }}
            </div>
            {% if post.media_description %}
            <div class="post-description">
                <strong>AI Analysis:</strong> {{ post.media_description[:300] }}{% if post.media_description|length > 300 %}...{% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
        {% for story in flagged_stories %}
        <div class="post flagged">
            <div class="post-header">
                <span>
                    <span class="post-type">Story - {{ 'Video' if story.is_video else 'Image' }}</span>
                    <span class="flagged-badge">FLAGGED</span>
                </span>
                <span class="post-date">{{ story.date[:10] }}</span>
            </div>
            <div class="flag-reason">
                <strong>Flag Reason:</strong> {{ story.flag_reason }}
            </div>
            {% if story.media_description %}
            <div class="post-description">
                <strong>AI Analysis:</strong> {{ story.media_description[:300] }}{% if story.media_description|length > 300 %}...{% endif %}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <div class="section">
        <h2>All Posts ({{ posts|length }})</h2>
        {% for post in posts %}
        <div class="post{% if post.flagged %} flagged{% endif %}">
            <div class="post-header">
                <span>
                    <span class="post-type">{{ 'Video' if post.is_video else 'Image' }}</span>
                    {% if post.flagged %}<span class="flagged-badge">FLAGGED</span>{% endif %}
                </span>
                <span class="post-date">{{ post.date[:10] }} - {{ post.likes }} likes</span>
            </div>
            <div><strong>URL:</strong> <a href="{{ post.url }}">{{ post.url }}</a></div>
            {% if post.caption %}
            <div class="post-caption">{{ post.caption[:200] }}{% if post.caption|length > 200 %}...{% endif %}</div>
            {% endif %}
            {% if post.media_description %}
            <div class="post-description">
                {{ post.media_description[:300] }}{% if post.media_description|length > 300 %}...{% endif %}
            </div>
            {% endif %}
            {% if post.flagged %}
            <div class="flag-reason">
                <strong>Flag Reason:</strong> {{ post.flag_reason }}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    {% if stories %}
    <div class="section">
        <h2>All Stories ({{ stories|length }})</h2>
        {% for story in stories %}
        <div class="post{% if story.flagged %} flagged{% endif %}">
            <div class="post-header">
                <span>
                    <span class="post-type">Story - {{ 'Video' if story.is_video else 'Image' }}</span>
                    {% if story.flagged %}<span class="flagged-badge">FLAGGED</span>{% endif %}
                </span>
                <span class="post-date">{{ story.date[:10] }}</span>
            </div>
            {% if story.media_description %}
            <div class="post-description">
                {{ story.media_description[:300] }}{% if story.media_description|length > 300 %}...{% endif %}
            </div>
            {% endif %}
            {% if story.flagged %}
            <div class="flag-reason">
                <strong>Flag Reason:</strong> {{ story.flag_reason }}
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <div class="footer">
        <p>Instagram Monitor - Automated Daily Report</p>
        <p>This is an automated report. Please do not reply to this email.</p>
    </div>
</body>
</html>
"""
    
    def _default_pdf_template(self) -> str:
        """Default PDF template (simpler version of email template)"""
        return self._default_email_template()  # Can use same template for both


