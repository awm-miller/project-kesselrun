# Instagram Monitor - Production Edition

Automated Instagram monitoring system with AI-powered content analysis, Google Drive storage, and daily email reports. Designed to run as a cron job on a VPS for continuous monitoring.

## Features

- **Smart State Tracking**: Only analyzes new posts/stories (no duplicate processing)
- **AI Content Analysis**: Gemini 2.0 Flash for image/video transcription and flagging
- **Google Drive Integration**: Automatic upload of all content and reports
- **Multi-Account Support**: Monitor multiple Instagram accounts
- **Story Scraping**: Instagram Stories support (requires login)
- **Email Reports**: Daily HTML and PDF reports sent to subscribers
- **Production Ready**: Designed for VPS deployment with cron scheduling

## Architecture

```
Daily Cron Job (Midnight)
    ↓
Load Accounts → For Each Account:
    ↓
1. Scrape Posts/Stories (Instagram API)
    ↓
2. Filter NEW Content Only (State Tracker)
    ↓
3. Analyze with Gemini AI
    ↓
4. Upload to Google Drive (user/POSTS|STORIES/YYYY-MM-DD/)
    ↓
5. Generate HTML + PDF Reports
    ↓
6. Send Email to Subscribers
    ↓
7. Update State (Mark as Analyzed)
    ↓
8. Cleanup Temp Files
```

## Quick Start - Local Testing

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# Instagram Authentication
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password

# Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Google Drive (create service account in Google Cloud Console)
GOOGLE_SERVICE_ACCOUNT_PATH=service_account.json
GOOGLE_DRIVE_ROOT_FOLDER_ID=  # Optional parent folder ID

# SMTP Email
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=Instagram Monitor
```

### 3. Configure Accounts

Edit `accounts.json`:

```json
{
  "accounts": [
    {"username": "target_account_1", "include_stories": true},
    {"username": "target_account_2", "include_stories": false}
  ]
}
```

### 4. Configure Subscribers

Edit `subscribers.json`:

```json
{
  "subscribers": [
    "admin@example.com",
    "team@example.com"
  ]
}
```

### 5. Test Locally

```bash
# Test mode (no uploads, no emails)
python monitor.py --test --max-posts 2

# Full run with limited posts
python monitor.py --max-posts 5
```

## Production Deployment to VPS

### Prerequisites

- Ubuntu 20.04+ or Debian 11+ VPS
- Python 3.11+
- SSH access with sudo privileges
- 2GB+ RAM (for video processing)
- 10GB+ disk space

### Step 1: Prepare Credentials

Before deploying, prepare these files:

1. **`.env`** - Environment variables (see template above)
2. **`service_account.json`** - Google Cloud service account credentials
3. **`cookies.txt`** - Instagram session cookies (optional, for Stories)
4. **`accounts.json`** - List of accounts to monitor
5. **`subscribers.json`** - Email recipients

⚠️ **NEVER commit these files to git!** They are already in `.gitignore`.

### Step 2: Deploy to VPS

```bash
# Make deployment script executable
chmod +x deploy/deploy.sh

# Deploy files to VPS
./deploy/deploy.sh user@your-vps-ip
```

### Step 3: Setup VPS

SSH into your VPS and run the setup script:

```bash
ssh user@your-vps-ip
sudo /opt/instagram_monitor/setup_vps.sh
```

This will:
- Install Python 3.11 and dependencies
- Create virtual environment
- Set up directory structure
- Configure cron job (runs daily at midnight)
- Set up log rotation

### Step 4: Upload Sensitive Files

From your local machine:

```bash
# Upload environment file
scp .env user@your-vps-ip:/opt/instagram_monitor/

# Upload Google service account
scp service_account.json user@your-vps-ip:/opt/instagram_monitor/

# Upload Instagram cookies (optional)
scp cookies.txt user@your-vps-ip:/opt/instagram_monitor/

# Upload configured accounts and subscribers
scp accounts.json user@your-vps-ip:/opt/instagram_monitor/
scp subscribers.json user@your-vps-ip:/opt/instagram_monitor/
```

### Step 5: Test on VPS

```bash
ssh user@your-vps-ip

# Switch to www-data user and test
sudo -u www-data /opt/instagram_monitor/venv/bin/python /opt/instagram_monitor/monitor.py --test --max-posts 2

# If test successful, run once fully
sudo -u www-data /opt/instagram_monitor/venv/bin/python /opt/instagram_monitor/monitor.py --max-posts 5
```

### Step 6: Monitor Logs

```bash
# Watch live logs
tail -f /var/log/instagram_monitor/monitor.log

# Check cron execution
grep "instagram_monitor" /var/log/syslog
```

## Google Drive Setup

### Create Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable **Google Drive API**
4. Create **Service Account**:
   - Go to "IAM & Admin" → "Service Accounts"
   - Click "Create Service Account"
   - Name it "instagram-monitor"
   - Grant role: "Editor" or "Owner"
   - Click "Create Key" → JSON
   - Download and save as `service_account.json`

5. Share Google Drive folder with service account email:
   - Open your Google Drive
   - Create folder for monitoring (e.g., "Instagram Monitor")
   - Right-click → Share
   - Add service account email (looks like `name@project.iam.gserviceaccount.com`)
   - Give "Editor" access

### Folder Structure in Google Drive

The system creates this structure automatically:

```
Instagram Monitor/
├── username1/
│   ├── POSTS/
│   │   ├── 2025-12-19/
│   │   │   ├── shortcode1.jpg
│   │   │   ├── shortcode1_analysis.json
│   │   │   └── ...
│   │   └── 2025-12-20/
│   ├── STORIES/
│   │   ├── 2025-12-19/
│   │   │   ├── story_12345.mp4
│   │   │   └── story_12345_analysis.json
│   │   └── ...
│   └── reports/
│       ├── 2025-12-19_report.html
│       ├── 2025-12-19_report.pdf
│       └── ...
└── username2/
    └── ...
```

## Gmail SMTP Setup

### Get App Password

1. Go to [Google Account](https://myaccount.google.com/)
2. Security → 2-Step Verification (must be enabled)
3. App Passwords → Generate new
4. Select "Mail" and "Other (Custom name)"
5. Copy the 16-character password
6. Use this in `.env` as `SMTP_PASSWORD`

**Note**: Regular Gmail password won't work - you must use App Password!

## Configuration

### State Tracking

The system maintains `state.json` to track analyzed content:

```json
{
  "username1": {
    "posts": ["shortcode1", "shortcode2", ...],
    "stories": ["story_id1", "story_id2", ...],
    "last_run": "2025-12-19T00:00:00"
  }
}
```

This ensures:
- No duplicate analysis
- Efficient processing (only new content)
- Persistent tracking across runs

### Cron Schedule Options

Edit cron with `crontab -e`:

```bash
# Daily at midnight
0 0 * * * cd /opt/instagram_monitor && venv/bin/python monitor.py >> /var/log/instagram_monitor/monitor.log 2>&1

# Every 6 hours
0 */6 * * * cd /opt/instagram_monitor && venv/bin/python monitor.py >> /var/log/instagram_monitor/monitor.log 2>&1

# Twice daily (midnight and noon)
0 0,12 * * * cd /opt/instagram_monitor && venv/bin/python monitor.py >> /var/log/instagram_monitor/monitor.log 2>&1
```

### Rate Limiting

- **30-second delay** between accounts (configurable in `config.py`)
- Prevents Instagram bot detection
- Uses cookie-based authentication for better reliability

## Command Line Options

```bash
# Test mode (no uploads, no emails)
python monitor.py --test

# Limit posts per account
python monitor.py --max-posts 50

# Custom accounts file
python monitor.py --accounts my_accounts.json

# Combined options
python monitor.py --test --max-posts 5
```

## Troubleshooting

### Issue: "Google Drive authentication failed"

- Check `service_account.json` exists and is valid
- Verify service account email has access to Drive folder
- Check `GOOGLE_SERVICE_ACCOUNT_PATH` in `.env`

### Issue: "Email sending failed"

- For Gmail: Use App Password, not regular password
- Check 2-Factor Authentication is enabled
- Verify `SMTP_PORT` (587 for TLS, 465 for SSL)
- Test: `python -c "from emailer import EmailSender; EmailSender(...).test_connection()"`

### Issue: "Instagram login failed"

- Cookie authentication preferred over username/password
- Cookies expire - refresh periodically
- Use browser extension to export cookies in Netscape format
- Fallback to username/password if cookies fail

### Issue: "No new content found"

- This is normal - means all content already analyzed
- Check `state.json` to see what's tracked
- Delete `state.json` to force re-analysis of everything

### Issue: "PDF generation failed"

- Install system dependencies: `sudo apt-get install libcairo2 libpango-1.0-0`
- Falls back to ReportLab if WeasyPrint unavailable
- Check logs for specific error

## Monitoring & Maintenance

### Check System Status

```bash
# View recent logs
tail -100 /var/log/instagram_monitor/monitor.log

# Check cron is running
systemctl status cron

# View cron jobs
crontab -l

# Check disk space
df -h /opt/instagram_monitor
```

### Reset State

To re-analyze all content:

```bash
rm /opt/instagram_monitor/state.json
```

### Update Code

```bash
# From local machine
./deploy/deploy.sh user@your-vps-ip

# On VPS, restart cron (automatic on next schedule)
```

## Security Best Practices

1. **Never commit sensitive files**:
   - `.env`
   - `service_account.json`
   - `cookies.txt`
   - `state.json`

2. **Secure your VPS**:
   - Use SSH keys, disable password auth
   - Configure firewall (UFW)
   - Keep system updated: `sudo apt update && sudo apt upgrade`

3. **Rotate credentials regularly**:
   - Instagram cookies (monthly)
   - Gmail app passwords (yearly)
   - Service account keys (yearly)

4. **Monitor for errors**:
   - Set up log monitoring
   - Configure email alerts for failures

## File Structure

```
project-kesselrun/
├── monitor.py              # Main orchestrator
├── scraper.py              # Instagram scraping
├── analyzer.py             # Gemini AI analysis
├── state_tracker.py        # State management
├── gdrive_uploader.py      # Google Drive integration
├── reporter.py             # Report generation
├── emailer.py              # Email sending
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
├── accounts.json           # Accounts to monitor
├── subscribers.json        # Email recipients
├── .env                    # Environment variables (not in git)
├── service_account.json    # Google credentials (not in git)
├── cookies.txt             # Instagram cookies (not in git)
├── state.json              # State tracker (generated)
├── deploy/
│   ├── deploy.sh           # Deployment script
│   ├── setup_vps.sh        # VPS setup
│   ├── crontab.txt         # Cron examples
│   └── instagram-monitor.service  # Systemd service
└── templates/
    ├── report_email.html   # Email template (auto-generated)
    └── report_pdf.html     # PDF template (auto-generated)
```

## Support

For issues or questions:
1. Check logs: `/var/log/instagram_monitor/monitor.log`
2. Run in test mode: `python monitor.py --test`
3. Check configuration files
4. Review this README

## License

This project is provided as-is for monitoring purposes.
