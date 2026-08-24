from flask import Flask, request, jsonify, send_from_directory
import hmac
import os
import random
import db
from config import CRON_SECRET, CHAT_ID, SECRET_KEY
from telegram import parse_update, send_message, send_document, make_keyboard
from handlers import handle_message, handle_callback, handle_evening
from morning import build_briefing
from api import api

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.register_blueprint(api)
db.init_db()


# --- Telegram webhook ---

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"status": "no data"}), 400

    chat_id, text, callback = parse_update(update)

    try:
        if callback and chat_id:
            handle_callback(chat_id, callback)
        elif chat_id and text:
            handle_message(chat_id, text)
    except Exception as e:
        print(f"Error handling update: {e}")

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

    handle_evening(CHAT_ID)
    return jsonify({"status": "sent"})


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


# --- Deadline nudge ---

@app.route("/trigger/deadline", methods=["GET", "POST"])
def trigger_deadline():
    """Remind about items due tomorrow."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    due_tomorrow = db.get_due_tomorrow()
    if not due_tomorrow:
        return jsonify({"status": "nothing due tomorrow"})

    lines = [f"⏰ *Due tomorrow: {len(due_tomorrow)} item(s)*\n"]
    for item in due_tomorrow:
        lines.append(f"  • {item['text']} — /{item['list_name']}")

    result = send_message(CHAT_ID, "\n".join(lines))
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Habit check-in ---

@app.route("/trigger/habits", methods=["GET", "POST"])
def trigger_habits():
    """Midday habit reminder for anything not yet logged."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    habits = db.get_habits()
    logged = db.get_habits_logged_today()
    unlogged = [h for h in habits if h["name"] not in logged]

    if not unlogged:
        return jsonify({"status": "all logged"})

    lines = ["🔄 *Habit reminder*\n"]
    buttons = []
    for h in unlogged:
        streak = db.get_habit_streak(h["name"])
        streak_str = f" ({streak}🔥)" if streak > 0 else ""
        lines.append(f"  ⬜ {h['name']}{streak_str}")
        buttons.append([(f"✅ Log {h['name']}", f"habit:{h['name']}")])

    keyboard = make_keyboard(buttons) if buttons else None
    result = send_message(CHAT_ID, "\n".join(lines), reply_markup=keyboard)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- One small thing ---

@app.route("/trigger/smallthing", methods=["GET", "POST"])
def trigger_smallthing():
    """Pick one random pending item as a suggestion."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    # Only nudge with todo items, not shopping/reference lists
    if db.list_exists("todo"):
        pending = db.get_items("todo")
    else:
        pending = db.get_all_pending()
    if not pending:
        return jsonify({"status": "nothing pending"})

    item = random.choice(pending)
    due = f" (due {item['due_date']})" if item["due_date"] else ""
    msg = f"💡 *Got a minute?*\n\n{item['text']}{due}"

    result = send_message(CHAT_ID, msg)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Weekly review ---

def build_wins_data():
    """Gather this week's stats into a dict for the review."""
    completed = db.get_completed_since(days=7)
    tracking = db.get_tracking_since(days=7)
    habit_logs = db.get_habit_logs_since(days=7)
    habits = db.get_habits()

    habit_summary = []
    for h in habits:
        days_logged = len(set(
            log["day"] for log in habit_logs if log["habit_name"] == h["name"] and log["done"]
        ))
        streak = db.get_habit_streak(h["name"])
        habit_summary.append({"name": h["name"], "days_logged": days_logged, "streak": streak})

    return {
        "completed": [{"list": i["list_name"], "text": i["text"]} for i in completed],
        "tracking": [{"type": t["type"], "value": t["value"], "notes": t["notes"],
                       "date": t["created_at"][:10]} for t in tracking],
        "habits": habit_summary,
    }


def format_wins_stats(wins_data):
    """Format wins data as a readable Telegram message."""
    lines = []

    completed = wins_data.get("completed", [])
    lines.append(f"✅ *Completed:* {len(completed)} item(s)")
    for item in completed[:10]:
        lines.append(f"  • {item['text']}")
    if len(completed) > 10:
        lines.append(f"  ...and {len(completed) - 10} more")

    tracking = wins_data.get("tracking", [])
    if tracking:
        types = {}
        for t in tracking:
            types.setdefault(t["type"], []).append(t)
        lines.append("")
        lines.append("📊 *Tracking:*")
        for type_, entries in types.items():
            values = [e["value"] for e in entries if e["value"] is not None]
            if values:
                avg = sum(values) / len(values)
                lines.append(f"  {type_}: {len(entries)} entries, avg {avg:.1f}")
            else:
                lines.append(f"  {type_}: {len(entries)} entries")

    habits = wins_data.get("habits", [])
    if habits:
        lines.append("")
        lines.append("🔄 *Habits:*")
        for h in habits:
            streak_str = f" ({h['streak']}🔥)" if h["streak"] > 0 else ""
            lines.append(f"  {h['name']}: {h['days_logged']}/7 days{streak_str}")

    return "\n".join(lines)


@app.route("/trigger/weekly", methods=["GET", "POST"])
def trigger_weekly():
    """Start the interactive weekly review."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    wins_data = build_wins_data()
    db.start_weekly_review(wins_data)

    stats = format_wins_stats(wins_data)
    msg = (
        f"🏆 *Weekly Review*\n\n"
        f"{stats}\n\n"
        f"---\n\n"
        f"Let's reflect. *{db.REVIEW_QUESTIONS[0]}*\n\n"
        f"(Type your answer, or /skip to skip)"
    )

    result = send_message(CHAT_ID, msg)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Backup ---

@app.route("/trigger/backup", methods=["GET", "POST"])
def trigger_backup():
    """Send bot.db to you via Telegram as a document."""
    import shutil
    from datetime import datetime
    from config import DB_PATH

    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    # Copy to a temp file with a dated name so you can tell backups apart
    timestamp = datetime.now().strftime("%Y%m%d")
    backup_name = f"bot_backup_{timestamp}.db"
    tmp_path = os.path.join("/tmp", backup_name)
    shutil.copy2(DB_PATH, tmp_path)

    result = send_document(CHAT_ID, tmp_path, caption=f"📦 Database backup — {timestamp}")
    os.remove(tmp_path)

    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Webhook health check ---

@app.route("/trigger/healthcheck", methods=["GET", "POST"])
def trigger_healthcheck():
    """Re-register webhook if Telegram has dropped it."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403

    from telegram import get_webhook_info, set_webhook
    from config import WEBHOOK_URL

    info = get_webhook_info().get("result", {})
    current_url = info.get("url", "")
    last_error = info.get("last_error_message", "")

    if current_url != WEBHOOK_URL or last_error:
        set_webhook(WEBHOOK_URL)
        return jsonify({"status": "re-registered", "reason": last_error or "url mismatch"})

    return jsonify({"status": "ok", "url": current_url})


# --- Health check ---

@app.route("/", methods=["GET"])
def health():
    return "Bot is running."


# --- PWA companion app ---

@app.route("/app")
@app.route("/app/")
def pwa():
    return send_from_directory("static", "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory("static", "sw.js")


if __name__ == "__main__":
    # For local testing only — PythonAnywhere uses WSGI
    app.run(debug=True, port=5000)
