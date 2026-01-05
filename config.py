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

# Anti-bot detection (random delays to appear more human)
ACCOUNT_DELAY_MIN = 25
ACCOUNT_DELAY_MAX = 45
STORY_DELAY_MIN = 3
STORY_DELAY_MAX = 8

# Paths
ACCOUNTS_FILE = "accounts.json"
RESULTS_DIR = "results"
TEMP_DIR = "temp_downloads"
COOKIES_FILE = "cookies.txt"

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

