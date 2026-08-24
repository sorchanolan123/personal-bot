"""REST API for the PWA companion app."""

from flask import Blueprint, jsonify, request, session
from functools import wraps
import db
from config import WEB_PIN, CRON_SECRET

api = Blueprint("api", __name__)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


# --- Auth ---

@api.route("/api/auth", methods=["POST"])
def auth():
    pin = (request.json or {}).get("pin", "")
    if pin == WEB_PIN:
        session["authenticated"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "wrong pin"}), 401


@api.route("/api/auth/check", methods=["GET"])
def auth_check():
    return jsonify({"authenticated": session.get("authenticated", False)})


# --- Dashboard data ---

@api.route("/api/today", methods=["GET"])
@require_auth
def today():
    # Focus items (due today + completed today)
    focus = db.get_focus_today()
    focus_items = [
        {"id": i["id"], "text": i["text"], "done": bool(i["done"]),
         "list_name": i["list_name"], "due_date": i["due_date"]}
        for i in focus
    ]

    # Overdue
    overdue = db.get_overdue()
    overdue_items = [
        {"id": i["id"], "text": i["text"], "list_name": i["list_name"],
         "due_date": i["due_date"]}
        for i in overdue
    ]

    # Habits
    habits_raw = db.get_habits()
    logged_today = db.get_habits_logged_today()
    habits = [
        {"name": h["name"], "done": h["name"] in logged_today,
         "streak": db.get_habit_streak(h["name"])}
        for h in habits_raw
    ]

    # Today's tracking
    tracking_raw = db.get_tracking_today()
    tracking = [
        {"type": t["type"], "value": t["value"], "notes": t["notes"],
         "created_at": t["created_at"]}
        for t in tracking_raw
    ]

    # Check if morning check-in is done (has mood/energy/sleep today)
    tracked_types = {t["type"] for t in tracking}
    morning_done = bool(tracked_types & {"mood", "energy", "sleep"})

    # Pending counts
    all_pending = db.get_all_pending()

    return jsonify({
        "focus": focus_items,
        "overdue": overdue_items,
        "habits": habits,
        "tracking": tracking,
        "morning_done": morning_done,
        "pending_count": len(all_pending),
    })


# --- Smart feed ---

@api.route("/api/feed", methods=["GET"])
@require_auth
def feed():
    """Single prioritised feed for the Today tab."""
    from datetime import datetime

    now = datetime.now()
    hour = now.hour
    today_str = now.strftime("%Y-%m-%d")

    # Gather raw data
    overdue = db.get_overdue()
    due_today = db.get_due_today()
    focus = db.get_focus_today()
    upcoming = db.get_upcoming(days=7)
    habits_raw = db.get_habits()
    logged_today = db.get_habits_logged_today()
    tracking_raw = db.get_tracking_today()
    all_pending = db.get_all_pending()

    # Check-in status
    tracked_types = {t["type"] for t in tracking_raw}
    morning_done = bool(tracked_types & {"mood", "energy", "sleep"})
    evening_done = "reflection" in tracked_types

    # Quick-tap values (mood/energy/sleep)
    quick_taps = {}
    for t in tracking_raw:
        if t["type"] in ("mood", "energy", "sleep") and t["value"] is not None:
            quick_taps[t["type"]] = t["value"]

    # Build feed items — each has: type, priority (lower = more urgent), data
    items = []

    # Overdue items (highest priority)
    for i in overdue:
        days_over = (now.date() - datetime.strptime(i["due_date"], "%Y-%m-%d").date()).days
        items.append({
            "type": "task",
            "priority": 0,
            "id": i["id"],
            "text": i["text"],
            "list_name": i["list_name"],
            "due_date": i["due_date"],
            "urgency": "overdue",
            "detail": f"overdue {days_over} day{'s' if days_over != 1 else ''}",
            "done": False,
        })

    # Due today (high priority)
    for i in due_today:
        items.append({
            "type": "task",
            "priority": 1,
            "id": i["id"],
            "text": i["text"],
            "list_name": i["list_name"],
            "due_date": i["due_date"],
            "urgency": "today",
            "detail": "due today",
            "done": False,
        })

    # Completed today (show as done)
    done_today = [i for i in focus if i["done"]]
    for i in done_today:
        items.append({
            "type": "task",
            "priority": 10,
            "id": i["id"],
            "text": i["text"],
            "list_name": i["list_name"],
            "due_date": i["due_date"],
            "urgency": "done",
            "detail": "done today",
            "done": True,
        })

    # Morning check-in nudge
    if not morning_done:
        items.append({
            "type": "checkin",
            "priority": 2,
            "checkin_type": "morning",
            "text": "Check in for today",
            "detail": "Log mood, energy, sleep",
        })

    # Unlogged habits
    unlogged = [h for h in habits_raw if h["name"] not in logged_today]
    if unlogged:
        items.append({
            "type": "habits",
            "priority": 3,
            "habits": [{"name": h["name"], "streak": db.get_habit_streak(h["name"])} for h in unlogged],
            "text": f"{len(unlogged)} habit{'s' if len(unlogged) != 1 else ''} to log",
            "detail": ", ".join(h["name"] for h in unlogged[:4]),
        })

    # Evening wrap-up (after 5pm)
    if hour >= 17 and not evening_done:
        done_count = len(done_today)
        total_focus = len(due_today) + len(done_today)
        habits_logged = len(logged_today)
        total_habits = len(habits_raw)
        items.append({
            "type": "checkin",
            "priority": 4,
            "checkin_type": "evening",
            "text": "Evening wrap-up",
            "detail": f"{done_count}/{total_focus} tasks, {habits_logged}/{total_habits} habits",
        })

    # Upcoming items (lower priority, "later" section)
    later = []
    for i in upcoming:
        later.append({
            "type": "task",
            "id": i["id"],
            "text": i["text"],
            "list_name": i["list_name"],
            "due_date": i["due_date"],
            "detail": i["due_date"],
            "done": False,
        })

    return jsonify({
        "quick_taps": quick_taps,
        "morning_done": morning_done,
        "items": sorted(items, key=lambda x: x.get("priority", 99)),
        "later": later,
        "pending_count": len(all_pending),
    })


# --- Quick tap (single value log) ---

@api.route("/api/quicktap", methods=["POST"])
@require_auth
def quicktap():
    """Log a single tracking value (mood, energy, sleep)."""
    data = request.json or {}
    type_ = data.get("type", "").strip().lower()
    value = data.get("value")
    if type_ not in ("mood", "energy", "sleep") or value is None:
        return jsonify({"error": "invalid"}), 400
    db.add_tracking(type_, float(value))
    return jsonify({"ok": True, "type": type_, "value": float(value)})


# --- Morning check-in ---

@api.route("/api/checkin/morning", methods=["POST"])
@require_auth
def morning_checkin():
    data = request.json or {}

    if data.get("mood") is not None:
        db.add_tracking("mood", float(data["mood"]), data.get("mood_notes"))
    if data.get("energy") is not None:
        db.add_tracking("energy", float(data["energy"]))
    if data.get("sleep") is not None:
        db.add_tracking("sleep", float(data["sleep"]))
    if data.get("notes"):
        db.add_tracking("morning_notes", None, data["notes"])

    # Process intentions as items if provided
    intentions = data.get("intentions", [])
    for item_text in intentions:
        if item_text.strip():
            from handlers import parse_due_date
            text, due = parse_due_date(item_text.strip())
            if not db.list_exists("todo"):
                db.create_list("todo", "Things to do")
            db.add_item("todo", text, due_date=due)

    return jsonify({"ok": True})


# --- Evening wrap-up ---

@api.route("/api/checkin/evening", methods=["POST"])
@require_auth
def evening_checkin():
    data = request.json or {}

    if data.get("reflection"):
        db.add_tracking("reflection", None, data["reflection"])
    if data.get("mood") is not None:
        db.add_tracking("evening_mood", float(data["mood"]))
    if data.get("gratitude"):
        db.add_tracking("gratitude", None, data["gratitude"])

    return jsonify({"ok": True})


# --- Habit logging ---

@api.route("/api/habit/<name>/log", methods=["POST"])
@require_auth
def log_habit(name):
    habits = {h["name"] for h in db.get_habits()}
    if name.lower() not in habits:
        return jsonify({"error": "not found"}), 404
    db.log_habit(name.lower())
    streak = db.get_habit_streak(name.lower())
    return jsonify({"ok": True, "streak": streak})


# --- Item actions ---

@api.route("/api/item/<int:item_id>/done", methods=["POST"])
@require_auth
def item_done(item_id):
    db.mark_done_by_id(item_id)
    return jsonify({"ok": True})


@api.route("/api/item/<int:item_id>/undone", methods=["POST"])
@require_auth
def item_undone(item_id):
    conn = db.get_db()
    conn.execute(
        "UPDATE items SET done = 0, completed_at = NULL WHERE id = ?",
        (item_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# --- Quick capture ---

@api.route("/api/capture", methods=["POST"])
@require_auth
def capture():
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400

    # Try LLM parsing first
    try:
        from llm import parse_freeform
        lists = db.get_lists()
        list_names = [l["name"] for l in lists]
        if "inbox" not in list_names:
            db.create_list("inbox", "Catch-all for unsorted items")
        actions = parse_freeform(text, list_names)
    except Exception:
        actions = None

    if not actions:
        # Fallback: add to inbox with date parsing
        from handlers import parse_due_date
        clean, due = parse_due_date(text)
        if not db.list_exists("inbox"):
            db.create_list("inbox", "Catch-all for unsorted items")
        db.add_item("inbox", clean, due_date=due)
        return jsonify({"ok": True, "result": f"Added to inbox: {clean}"})

    # Process LLM actions
    import re
    results = []
    for action in actions:
        a_type = action.get("action")
        if a_type == "list_item":
            list_name = action.get("list", "inbox").lower()
            item_text = action.get("text", "")
            due = action.get("due_date")
            if not db.list_exists(list_name):
                if re.match(r"^[a-z][a-z0-9_]{0,29}$", list_name):
                    db.create_list(list_name)
                else:
                    list_name = "inbox"
            db.add_item(list_name, item_text, due_date=due)
            results.append(f"Added to {list_name}: {item_text}")
        elif a_type == "tracking":
            type_ = action.get("type", "custom")
            value = action.get("value")
            notes = action.get("notes", "")
            db.add_tracking(type_, value, notes)
            results.append(f"Tracked {type_}")
        elif a_type == "mark_done":
            list_name = action.get("list", "").lower()
            search_text = action.get("text", "")
            if list_name and db.list_exists(list_name) and search_text:
                pos, item = db.find_item_by_text(list_name, search_text)
                if pos:
                    db.mark_done(list_name, pos)
                    results.append(f"Done: {item['text']}")
        elif a_type == "remove_item":
            list_name = action.get("list", "").lower()
            search_text = action.get("text", "")
            if list_name and db.list_exists(list_name) and search_text:
                pos, item = db.find_item_by_text(list_name, search_text)
                if pos:
                    db.delete_item(list_name, pos)
                    results.append(f"Removed: {item['text']}")

    return jsonify({"ok": True, "result": "; ".join(results) if results else "Processed"})


# --- Chat (question answering) ---

@api.route("/api/chat", methods=["POST"])
@require_auth
def chat():
    """Answer a question using LLM with context from the user's data."""
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400

    try:
        from llm import call_haiku
        import json

        # Gather context from the user's data
        context_parts = []

        # Lists and their items
        all_lists = db.get_lists()
        for lst in all_lists:
            items = db.get_items(lst["name"], include_done=False)
            if items:
                item_texts = [i["text"] for i in items[:20]]
                context_parts.append(f"List '{lst['name']}': {', '.join(item_texts)}")

        # Today's focus
        focus = db.get_focus_today()
        if focus:
            done = [f["text"] for f in focus if f["done"]]
            pending = [f["text"] for f in focus if not f["done"]]
            if pending:
                context_parts.append(f"Today's pending tasks: {', '.join(pending)}")
            if done:
                context_parts.append(f"Today's completed tasks: {', '.join(done)}")

        # Habits
        habits = db.get_habits()
        logged = db.get_habits_logged_today()
        if habits:
            habit_status = [f"{h['name']} ({'done' if h['name'] in logged else 'not done'})" for h in habits]
            context_parts.append(f"Habits: {', '.join(habit_status)}")

        # Recent tracking
        tracking = db.get_tracking_today()
        if tracking:
            track_summary = [f"{t['type']}: {t['value']}" for t in tracking if t["value"] is not None]
            if track_summary:
                context_parts.append(f"Today's tracking: {', '.join(track_summary)}")

        context = "\n".join(context_parts) if context_parts else "No data yet."

        system = f"""You are a friendly personal assistant embedded in a life management app.
The user is asking you a question. Use their data to give helpful, personalised answers.
Keep responses concise (2-3 sentences max). Be warm and supportive.

User's current data:
{context}"""

        reply = call_haiku(system, text)
        if reply:
            return jsonify({"ok": True, "reply": reply})
        return jsonify({"ok": False, "reply": "Hmm, I couldn't think of an answer. Try again?"}), 500

    except Exception as e:
        return jsonify({"ok": False, "reply": f"Something went wrong: {str(e)}"}), 500


# --- Lists ---

@api.route("/api/lists", methods=["GET"])
@require_auth
def lists():
    all_lists = db.get_lists()
    return jsonify([
        {"name": l["name"], "description": l["description"],
         "pending": l["pending"] or 0, "total": l["total"] or 0}
        for l in all_lists
    ])


@api.route("/api/list/<name>", methods=["GET"])
@require_auth
def list_items(name):
    if not db.list_exists(name.lower()):
        return jsonify({"error": "not found"}), 404
    items = db.get_items(name.lower(), include_done=True)
    return jsonify([
        {"id": i["id"], "text": i["text"], "done": bool(i["done"]),
         "due_date": i["due_date"], "created_at": i["created_at"],
         "metadata": i["metadata"]}
        for i in items
    ])


@api.route("/api/list/<name>/add", methods=["POST"])
@require_auth
def list_add_item(name):
    if not db.list_exists(name.lower()):
        return jsonify({"error": "not found"}), 404
    data = request.json or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    from handlers import parse_due_date
    clean, due = parse_due_date(text)
    item_id = db.add_item(name.lower(), clean, due_date=due)
    return jsonify({"ok": True, "id": item_id, "text": clean, "due_date": due})


@api.route("/api/item/<int:item_id>/edit", methods=["POST"])
@require_auth
def item_edit(item_id):
    data = request.json or {}
    new_text = data.get("text", "").strip()
    if not new_text:
        return jsonify({"error": "empty"}), 400
    conn = db.get_db()
    cursor = conn.execute("UPDATE items SET text = ? WHERE id = ?", (new_text, item_id))
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    if updated:
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


@api.route("/api/item/<int:item_id>", methods=["DELETE"])
@require_auth
def item_delete(item_id):
    conn = db.get_db()
    cursor = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    if deleted:
        return jsonify({"ok": True})
    return jsonify({"error": "not found"}), 404


# --- Deploy proxy (avoids exposing CRON_SECRET to the frontend) ---

@api.route("/api/deploy", methods=["POST"])
@require_auth
def deploy_proxy():
    """Call the deploy trigger using the server-side cron secret."""
    import requests as req
    try:
        base = request.host_url.rstrip("/")
        res = req.get(f"{base}/trigger/deploy?key={CRON_SECRET}", timeout=30)
        return jsonify(res.json())
    except Exception as e:
        # The deploy may kill the process before responding — that's expected
        return jsonify({"status": "deployed", "message": "Reload triggered (response may have been cut short)"})


# --- Tracking overview (habits + trackers with 7-day history) ---

@api.route("/api/tracking/overview", methods=["GET"])
@require_auth
def tracking_overview():
    try:
        from datetime import datetime, timedelta

        # Build last 7 day labels
        today = datetime.now().date()
        days = [(today - timedelta(days=6 - i)) for i in range(7)]
        day_strs = [d.strftime("%Y-%m-%d") for d in days]
        day_labels = [d.strftime("%a") for d in days]

        # --- Habits ---
        habits_raw = db.get_habits()
        logs = db.get_habit_logs_since(days=7)
        logged_today = db.get_habits_logged_today()

        # Build a set of (habit_name, day) from logs
        log_set = set()
        for log in logs:
            if log["done"]:
                log_set.add((log["habit_name"], log["day"]))

        habits = []
        for h in habits_raw:
            week = [1 if (h["name"], d) in log_set else 0 for d in day_strs]
            habits.append({
                "name": h["name"],
                "streak": db.get_habit_streak(h["name"]),
                "done_today": h["name"] in logged_today,
                "week": week,
            })

        # --- Trackers (numeric) ---
        tracking_raw = db.get_tracking_since(days=7)

        # Group by type, skip non-numeric and meta types
        skip_types = {"morning_notes", "reflection", "gratitude", "evening_mood"}
        type_data = {}
        for t in tracking_raw:
            if t["type"] in skip_types:
                continue
            if t["value"] is None:
                continue
            type_data.setdefault(t["type"], []).append({
                "value": t["value"],
                "date": t["created_at"][:10],
                "notes": t["notes"],
            })

        trackers = []
        for type_name, entries in sorted(type_data.items()):
            # Build 7-day values (use latest entry per day)
            day_vals = {}
            for e in entries:
                day_vals[e["date"]] = e["value"]  # last write wins

            week = [day_vals.get(d) for d in day_strs]
            latest = entries[0]["value"] if entries else None
            trackers.append({
                "type": type_name,
                "week": week,
                "latest": latest,
            })

        return jsonify({
            "day_labels": day_labels,
            "habits": habits,
            "trackers": trackers,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- Create habit ---

@api.route("/api/habit", methods=["POST"])
@require_auth
def create_habit():
    data = request.json or {}
    name = data.get("name", "").strip().lower()
    if not name:
        return jsonify({"error": "empty"}), 400
    if db.create_habit(name):
        return jsonify({"ok": True, "name": name})
    return jsonify({"error": "already exists"}), 409


# --- Tracking history (for charts) ---

@api.route("/api/tracking/<type_>", methods=["GET"])
@require_auth
def tracking_history(type_):
    days = request.args.get("days", 30, type=int)
    rows = db.get_tracking_by_type(type_, days=days)
    return jsonify([
        {"value": r["value"], "notes": r["notes"], "date": r["created_at"][:10]}
        for r in rows
    ])
