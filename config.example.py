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

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.db")

# Telegram API base URL
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
