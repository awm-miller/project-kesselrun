# Instagram Monitor

Standalone Instagram monitoring tool with video transcription, story scraping, and multi-account support. Designed to run as a cron job on a VPS.

## Features

- Scrapes public Instagram posts (images + videos)
- Downloads and transcribes videos with Gemini 2.0 Flash
- Scrapes Instagram Stories (requires login)
- AI-powered content analysis and flagging
- Multi-account support with anti-bot detection delays
- JSON output for easy processing

## Setup

### 1. Install Dependencies

```bash
cd instagram_monitor
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file or set environment variables:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key

# Optional (required for stories)
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
```

### 3. Configure Accounts

Edit `accounts.json` to add accounts to monitor:

```json
{
  "accounts": [
    {"username": "target_account_1", "include_stories": true},
    {"username": "target_account_2", "include_stories": false}
  ]
}
```

## Usage

### Run Manually

```bash
# Monitor all accounts in accounts.json
python monitor.py

# Limit posts per account
python monitor.py --max-posts 50

# Use different accounts file
python monitor.py --accounts my_accounts.json
```

### Run as Cron Job

```bash
# Edit crontab
crontab -e

# Add entry (runs every 6 hours)
0 */6 * * * cd /opt/instagram_monitor && /usr/bin/python3 monitor.py >> /var/log/ig_monitor.log 2>&1
```

## Output

Results are saved to `results/{username}.json` with this structure:

```json
{
  "username": "example_account",
  "analyzed_at": "2025-12-19T10:30:00.000000",
  "profile": {
    "username": "example_account",
    "full_name": "Example User",
    "bio": "...",
    "followers": 1000,
    "following": 500,
    "post_count": 100
  },
  "summary": "Clinical summary of the account...",
  "stats": {
    "total_posts": 50,
    "total_stories": 3,
    "flagged_count": 5
  },
  "posts": [
    {
      "index": 0,
      "shortcode": "ABC123",
      "url": "https://www.instagram.com/p/ABC123/",
      "date": "2025-12-19T10:00:00+00:00",
      "caption": "Post caption...",
      "is_video": true,
      "is_story": false,
      "likes": 100,
      "media_description": "AI description of the content...",
      "flagged": true,
      "flag_reason": "Contains antisemitic imagery"
    }
  ]
}
```

## Configuration

Edit `config.py` to customize:

- `ACCOUNT_DELAY_SECONDS`: Delay between accounts (default: 30s)
- `GEMINI_MODEL`: Gemini model to use (default: gemini-2.0-flash)
- `TEMP_DIR`: Temporary download directory
- `RESULTS_DIR`: Output directory for results

## Notes

- **Stories require Instagram login** - without credentials, only posts are scraped
- **30-second delay** between accounts helps avoid bot detection
- **Media files are cleaned up** after analysis to save disk space
- **Videos are uploaded to Gemini** for transcription - may take longer for large files

