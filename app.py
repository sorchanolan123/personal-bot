from flask import Flask, request, jsonify
import hmac
import db
from config import CRON_SECRET, CHAT_ID
from telegram import parse_update, send_message
from handlers import handle_message, handle_briefing
from morning import build_briefing

app = Flask(__name__)
db.init_db()


# --- Telegram webhook ---

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"status": "no data"}), 400

    chat_id, text = parse_update(update)
    if chat_id and text:
        handle_message(chat_id, text)

    return jsonify({"status": "ok"})


# --- Cron trigger endpoints ---
# These are called by an external cron service (e.g., cron-job.org).
# Protected by a secret key in the URL query string.

def check_cron_secret():
    """Validate the secret key on cron trigger requests."""
    key = request.args.get("key", "")
    if not hmac.compare_digest(key, CRON_SECRET):
        return False
    if CRON_SECRET == "CHANGE_ME_TO_A_RANDOM_STRING":
        return False
    return True


@app.route("/trigger/morning", methods=["GET", "POST"])
def trigger_morning():
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    briefing = build_briefing()
    result = send_message(CHAT_ID, briefing)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


@app.route("/trigger/evening", methods=["GET", "POST"])
def trigger_evening():
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    pending = db.get_all_pending()
    if pending:
        count = len(pending)
        msg = f"🌙 *Evening check-in*\n\nYou have {count} item(s) still pending. Anything to add before bed?\n\nSee everything: /all"
    else:
        msg = "🌙 *Evening check-in*\n\n🎉 All clear — nothing pending. Rest easy!"

    result = send_message(CHAT_ID, msg)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


@app.route("/trigger/stale", methods=["GET", "POST"])
def trigger_stale():
    """Weekly nudge about items that have been sitting for 7+ days."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    stale = db.get_stale_items(days=7)
    if not stale:
        return jsonify({"status": "nothing stale"})

    lines = [f"📦 *Weekly review: {len(stale)} stale item(s)*\n"]
    for item in stale:
        lines.append(f"  • {item['text']} — /{item['list_name']} (added {item['created_at'][:10]})")
    lines.append("\nStill relevant? Mark done with /done or let them ride.")

    result = send_message(CHAT_ID, "\n".join(lines))
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Health check ---

@app.route("/", methods=["GET"])
def health():
    return "Bot is running."


if __name__ == "__main__":
    # For local testing only — PythonAnywhere uses WSGI
    app.run(debug=True, port=5000)
