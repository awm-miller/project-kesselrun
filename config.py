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

# Paths
ACCOUNTS_FILE = "accounts.json"
RESULTS_DIR = "results"
TEMP_DIR = "temp_downloads"
COOKIES_FILE = "cookies.txt"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# State tracking
STATE_FILE = "state.json"

# Dashboard
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "kessel-run-secret-key")

