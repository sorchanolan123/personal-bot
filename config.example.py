import os

# Copy this file to config.py and fill in your values:
#   cp config.example.py config.py

# Telegram bot token from @BotFather
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TOKEN_HERE")

# Your Telegram chat ID (send /start to the bot, then check the API)
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# PythonAnywhere webhook URL
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://YOUR-USERNAME.pythonanywhere.com/webhook")

# Secret key for cron trigger endpoints.
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
CRON_SECRET = os.environ.get("CRON_SECRET", "CHANGE_ME_TO_A_RANDOM_STRING")

# Anthropic API key for Haiku calls (freeform parsing, weekly summaries)
# Get one at: https://console.anthropic.com/settings/keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_KEY_HERE")

# Web app PIN (for the PWA companion app)
# Generate: python -c "import secrets; print(secrets.token_urlsafe(6))"
WEB_PIN = os.environ.get("WEB_PIN", "CHANGE_ME")

# Flask secret key (for session cookies)
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE_ME_TO_A_RANDOM_STRING")

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

# Telegram API base URL
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
