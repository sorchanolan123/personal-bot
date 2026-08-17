import json
import requests
from config import TELEGRAM_API


def send_message(chat_id, text, parse_mode="Markdown", reply_markup=None):
    """Send a message via the Telegram Bot API."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    return resp.json()


def edit_message(chat_id, message_id, text, parse_mode="Markdown", reply_markup=None):
    """Edit an existing message in place."""
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(f"{TELEGRAM_API}/editMessageText", json=payload)
    return resp.json()


def answer_callback(callback_query_id, text=None):
    """Acknowledge a callback query (dismisses the loading spinner)."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    resp = requests.post(f"{TELEGRAM_API}/answerCallbackQuery", json=payload)
    return resp.json()


def make_keyboard(buttons):
    """Build an InlineKeyboardMarkup from a list of button rows.

    buttons: list of rows, each row is a list of (label, callback_data) tuples.
    Example: [[("✅", "done:todo:1"), ("🗑", "del:todo:1")]]
    """
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in buttons
        ]
    }


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
    """Extract chat_id, text, and callback info from a Telegram update.

    Returns (chat_id, text, callback) where callback is a dict with
    {id, data, message_id} if this is a button tap, or None for text messages.
    """
    # Callback query (button tap)
    cb = update.get("callback_query")
    if cb:
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        return chat_id, None, {
            "id": cb["id"],
            "data": cb.get("data", ""),
            "message_id": message_id,
        }

    # Regular text message
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "")
    return chat_id, text, None
