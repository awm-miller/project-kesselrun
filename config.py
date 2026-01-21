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
ACCOUNT_DELAY_MIN = 20  # seconds between accounts
ACCOUNT_DELAY_MAX = 40  # seconds between accounts
STORY_DELAY_MIN = 5  # seconds before fetching account's stories
STORY_DELAY_MAX = 15  # seconds before fetching account's stories
STORY_ITEM_DELAY = 5  # seconds between individual story items
STARTUP_DELAY_MAX = 2700  # max random delay before run starts (45 minutes)

# Paths
ACCOUNTS_FILE = "accounts.json"
RESULTS_DIR = "results"
TEMP_DIR = "temp_downloads"
COOKIES_FILE = "cookies.txt"
TEMPLATES_DIR = "templates"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# State tracking
STATE_FILE = "state.json"
STATS_FILE = "stats.json"
SUBSCRIBERS_FILE = "subscribers.json"

# Google Drive
GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "service_account.json")
GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")

# Email / SMTP
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Kessel Run")

# Alert email for system issues (cookie failures, login errors)
ALERT_EMAIL = os.getenv("ALERT_EMAIL", "am@bothanlabs.com")

# Dashboard
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "kessel-run-secret-key")

