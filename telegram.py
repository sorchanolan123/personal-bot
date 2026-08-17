import requests
from config import TELEGRAM_API


def send_message(chat_id, text, parse_mode="Markdown"):
    """Send a message via the Telegram Bot API."""
    resp = requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        },
    )
    return resp.json()


def set_webhook(url):
    """Register a webhook URL with Telegram."""
    resp = requests.post(
        f"{TELEGRAM_API}/setWebhook",
        json={"url": url},
    )
    return resp.json()


def delete_webhook():
    """Remove the current webhook."""
    resp = requests.post(f"{TELEGRAM_API}/deleteWebhook")
    return resp.json()


def get_webhook_info():
    """Check current webhook status."""
    resp = requests.get(f"{TELEGRAM_API}/getWebhookInfo")
    return resp.json()


def send_document(chat_id, file_path, caption=None):
    """Send a file as a Telegram document."""
    with open(file_path, "rb") as f:
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
        resp = requests.post(
            f"{TELEGRAM_API}/sendDocument",
            data=data,
            files={"document": f},
        )
    return resp.json()


def parse_update(update):
    """Extract chat_id and message text from a Telegram update."""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    return chat_id, text
