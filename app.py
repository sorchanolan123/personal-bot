from flask import Flask, request, jsonify
import hmac
import os
import random
import db
from config import CRON_SECRET, CHAT_ID
from telegram import parse_update, send_message, send_document
from handlers import handle_message
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

    lines = ["🌙 *Evening check-in*\n"]

    # How did focus items go?
    focus = db.get_daily_focus()
    if focus:
        done_count = sum(1 for f in focus if f["done"])
        total = len(focus)
        lines.append(f"*Focus:* {done_count}/{total} completed")
        for item in focus:
            status = "✅" if item["done"] else "⬜"
            lines.append(f"  {status} {item['text']}")
        lines.append("")

    # Habits not yet logged
    habits = db.get_habits()
    logged = db.get_habits_logged_today()
    unlogged = [h for h in habits if h["name"] not in logged]
    if unlogged:
        lines.append("🔄 *Habits not logged yet:*")
        for h in unlogged:
            lines.append(f"  ⬜ {h['name']} — /log {h['name']}")
        lines.append("")

    # Pending count
    pending = db.get_all_pending()
    if pending:
        lines.append(f"📋 {len(pending)} item(s) still pending.")

    lines.append("\nAnything to capture before bed? Just type it.")

    result = send_message(CHAT_ID, "\n".join(lines))
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
    for h in unlogged:
        streak = db.get_habit_streak(h["name"])
        streak_str = f" ({streak}🔥)" if streak > 0 else ""
        lines.append(f"  ⬜ {h['name']}{streak_str} — /log {h['name']}")

    result = send_message(CHAT_ID, "\n".join(lines))
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- One small thing ---

@app.route("/trigger/smallthing", methods=["GET", "POST"])
def trigger_smallthing():
    """Pick one random pending item as a suggestion."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    pending = db.get_all_pending()
    if not pending:
        return jsonify({"status": "nothing pending"})

    item = random.choice(pending)
    due = f" (due {item['due_date']})" if item["due_date"] else ""
    msg = f"💡 *Got a minute?*\n\n{item['text']}{due}\n\nFrom /{item['list_name']}"

    result = send_message(CHAT_ID, msg)
    return jsonify({"status": "sent", "ok": result.get("ok", False)})


# --- Weekly wins ---

@app.route("/trigger/weekly", methods=["GET", "POST"])
def trigger_weekly():
    """Sunday weekly summary with stats and optional LLM narrative."""
    if not check_cron_secret():
        return jsonify({"error": "unauthorized"}), 403
    if not CHAT_ID:
        return jsonify({"error": "CHAT_ID not configured"}), 500

    completed = db.get_completed_since(days=7)
    tracking = db.get_tracking_since(days=7)
    habit_logs = db.get_habit_logs_since(days=7)
    habits = db.get_habits()

    # Build habit summary
    habit_summary = []
    for h in habits:
        days_logged = len(set(
            log["day"] for log in habit_logs if log["habit_name"] == h["name"] and log["done"]
        ))
        streak = db.get_habit_streak(h["name"])
        habit_summary.append({"name": h["name"], "days_logged": days_logged, "streak": streak})

    # Try LLM summary first
    try:
        from llm import generate_weekly_summary
        llm_summary = generate_weekly_summary(completed, tracking, habit_summary)
    except Exception:
        llm_summary = None

    if llm_summary:
        msg = f"🏆 *Weekly Wins*\n\n{llm_summary}"
    else:
        # Fallback: simple stats
        lines = ["🏆 *Weekly Wins*\n"]
        lines.append(f"✅ *Completed:* {len(completed)} item(s)")
        if completed:
            for item in completed[:10]:
                lines.append(f"  • {item['text']}")

        if tracking:
            # Group tracking by type
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

        if habit_summary:
            lines.append("")
            lines.append("🔄 *Habits:*")
            for h in habit_summary:
                streak_str = f" ({h['streak']}🔥)" if h["streak"] > 0 else ""
                lines.append(f"  {h['name']}: {h['days_logged']}/7 days{streak_str}")

        msg = "\n".join(lines)

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


# --- Health check ---

@app.route("/", methods=["GET"])
def health():
    return "Bot is running."


if __name__ == "__main__":
    # For local testing only — PythonAnywhere uses WSGI
    app.run(debug=True, port=5000)
