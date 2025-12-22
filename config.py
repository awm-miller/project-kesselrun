"""
Instagram Monitor Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Instagram credentials (required for stories)
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.0-flash"

# Anti-bot detection
ACCOUNT_DELAY_SECONDS = 30
STORY_DELAY_SECONDS = 60  # Pause before scraping stories

# Proxy Configuration (Mullvad SOCKS5)
PROXY_ENABLED = os.getenv("PROXY_ENABLED", "true").lower() == "true"
MULLVAD_ACCOUNT = os.getenv("MULLVAD_ACCOUNT", "8250455157402818")
MULLVAD_PROXY_SERVER = os.getenv("MULLVAD_PROXY_SERVER", "se-sto-wg-socks5-001.relays.mullvad.net")
MULLVAD_PROXY_PORT = int(os.getenv("MULLVAD_PROXY_PORT", "1080"))

# Paths
ACCOUNTS_FILE = "accounts.json"
RESULTS_DIR = "results"
TEMP_DIR = "temp_downloads"
COOKIES_FILE = "cookies.txt"
STATE_FILE = "state.json"
SUBSCRIBERS_FILE = "subscribers.json"

# Google Drive
GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "serviceaccount.json")
GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID")  # Optional

# SMTP Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Instagram Monitor")

# Report Generation
TEMPLATES_DIR = "templates"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = "monitor.log"

# Dashboard
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "instagram-monitor-secret-key-change-me")

