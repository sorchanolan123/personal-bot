import json
import re
from datetime import datetime, timedelta
import db
from telegram import send_message, edit_message, answer_callback, make_keyboard


# Category tags per list — easy to extend later
LIST_CATEGORIES = {
    "watch": {"film": "🎬", "show": "📺"},
}


# --- Date parsing ---

def parse_due_date(text):
    """Extract a due date from item text. Returns (clean_text, date_string|None).

    Supported formats:
        due:today  due:tomorrow  due:monday  due:2025-03-15
    """
    match = re.search(r"\s*due:(\S+)", text, re.IGNORECASE)
    if not match:
        return text, None

    clean = text[: match.start()] + text[match.end() :]
    raw = match.group(1).lower()

    if raw == "today":
        return clean.strip(), datetime.now().strftime("%Y-%m-%d")
    if raw == "tomorrow":
        return clean.strip(), (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if raw in day_names:
        today = datetime.now()
        target = day_names.index(raw)
        delta = (target - today.weekday()) % 7
        if delta == 0:
            delta = 7
        return clean.strip(), (today + timedelta(days=delta)).strftime("%Y-%m-%d")

    # Try ISO date
    try:
        datetime.strptime(raw, "%Y-%m-%d")
        return clean.strip(), raw
    except ValueError:
        return text, None


# --- Response formatters ---

def format_items(items, list_name, show_done=False, with_buttons=False):
    """Format a list of items for display.

    Returns (text, keyboard) if with_buttons=True, otherwise just text.
    """
    if not items:
        text = f"📋 *{list_name}* is empty"
        return (text, None) if with_buttons else text

    # Look up category config for this list
    base_list = list_name.split(" (")[0]
    categories = LIST_CATEGORIES.get(base_list, {})

    lines = [f"📋 *{list_name}*\n"]
    buttons = []
    num = 1
    for item in items:
        # Category tag from metadata
        tag = ""
        if categories:
            meta = json.loads(item["metadata"] or "{}") if item["metadata"] else {}
            cat = meta.get("category", "")
            if cat in categories:
                tag = f" {categories[cat]}"

        if item["done"]:
            lines.append(f"  ✅ ~{item['text']}~{tag}")
        else:
            due = ""
            if item["due_date"]:
                due = f" 📅 {item['due_date']}"
            if with_buttons:
                # Item text goes on the button itself
                label = f"⬜ {item['text']}{tag}{due}"
                buttons.append([(label, f"done:{base_list}:{num}")])
            else:
                lines.append(f"  {num}. {item['text']}{tag}{due}")
            num += 1

    text = "\n".join(lines)
    if with_buttons:
        keyboard = make_keyboard(buttons) if buttons else None
        return text, keyboard
    return text


def format_all_lists(lists):
    if not lists:
        return "No lists yet. Create one with /newlist <name>"

    lines = ["📚 *Your lists*\n"]
    for lst in lists:
        pending = lst["pending"] or 0
        desc = f" — {lst['description']}" if lst["description"] else ""
        lines.append(f"  /{lst['name']} ({pending} pending){desc}")
    return "\n".join(lines)


# --- Command handlers ---

def handle_start(chat_id):
    send_message(chat_id, (
        "👋 *Hey! I'm your personal assistant.*\n\n"
        "*Just tell me things naturally:*\n"
        "  \"buy oat milk and call dentist by friday\"\n"
        "  \"worked out for 30 mins\"\n"
        "  \"feeling 7/10 today\"\n\n"
        "*Or use commands:*\n"
        "  /lists — see all lists\n"
        "  /all — everything pending\n"
        "  /focus — today's focus items\n"
        "  /habits — your habit tracker\n"
        "  /help — all commands"
    ))


def handle_help(chat_id):
    send_message(chat_id, (
        "*Commands*\n\n"
        "*Lists:*\n"
        "  /newlist <name> — create a list\n"
        "  /deletelist <name> — delete a list\n"
        "  /rename <old> <new> — rename a list\n"
        "  /lists — show all lists\n"
        "  /<list> — show items\n"
        "  /<list> <item> — add an item\n\n"
        "*Items:*\n"
        "  /done <list> <n> — mark done\n"
        "  /undo <list> <n> — undo\n"
        "  /remove <list> <n> — delete an item\n"
        "  /edit <list> <n> <new text> — edit an item\n"
        "  /due <list> <n> <date> — set due date\n"
        "  /undue <list> <n> — remove due date\n"
        "  /move <from> <n> <to> — move to another list\n"
        "  /clear <list> — clear completed\n\n"
        "*Focus & overview:*\n"
        "  /all — everything pending\n"
        "  /focus — today's focus items\n"
        "  /briefing — morning briefing\n\n"
        "*Tracking:*\n"
        "  /track mood 7 feeling good — log a metric\n"
        "  /track workout 45 morning run — log activity\n\n"
        "*Habits:*\n"
        "  /newhabit <name> — create a habit\n"
        "  /log <habit> — log it for today\n"
        "  /habits — see all habits + streaks\n"
        "  /deletehabit <name> — remove a habit\n\n"
        "*Or just type naturally* — I'll figure it out."
    ))


def handle_newlist(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /newlist <name> [description]")
        return

    parts = args.split(None, 1)
    name = parts[0].lower().strip()
    description = parts[1] if len(parts) > 1 else None

    if not re.match(r"^[a-z][a-z0-9_]{0,29}$", name):
        send_message(chat_id, "List name must be lowercase letters/numbers/underscores, start with a letter, max 30 chars.")
        return

    ok, reason = db.create_list(name, description)
    if ok:
        send_message(chat_id, f"✅ Created list *{name}*. Add items with /{name} <item>")
    elif reason == "exists":
        send_message(chat_id, f"A list called *{name}* already exists.")
    elif reason == "reserved":
        send_message(chat_id, f"*{name}* is a reserved command name. Pick something else.")


def handle_deletelist(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /deletelist <name>")
        return
    name = args.strip().lower()
    if db.delete_list(name):
        send_message(chat_id, f"🗑 Deleted list *{name}* and all its items.")
    else:
        send_message(chat_id, f"No list called *{name}*.")


def handle_rename(chat_id, args):
    parts = args.split() if args else []
    if len(parts) != 2:
        send_message(chat_id, "Usage: /rename <old_name> <new_name>")
        return
    old, new = parts
    if not re.match(r"^[a-z][a-z0-9_]{0,29}$", new):
        send_message(chat_id, "New name must be lowercase letters/numbers/underscores, start with a letter, max 30 chars.")
        return
    ok, reason = db.rename_list(old, new)
    if ok:
        send_message(chat_id, f"✅ Renamed *{old}* → *{new}*")
    elif reason == "exists":
        send_message(chat_id, f"A list called *{new}* already exists.")
    elif reason == "reserved":
        send_message(chat_id, f"*{new}* is a reserved command name.")


def handle_lists(chat_id):
    lists = db.get_lists()
    send_message(chat_id, format_all_lists(lists))


def handle_done(chat_id, args):
    parts = args.split() if args else []
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /done <list> <number>")
        return
    list_name, num = parts[0], int(parts[1])
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    if db.mark_done(list_name, num):
        send_message(chat_id, f"✅ Done!")
    else:
        send_message(chat_id, f"Item {num} not found in *{list_name}*.")


def handle_undo(chat_id, args):
    parts = args.split() if args else []
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /undo <list> <number>")
        return
    list_name, num = parts[0], int(parts[1])
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    if db.mark_undone(list_name, num):
        send_message(chat_id, "↩️ Restored!")
    else:
        send_message(chat_id, f"No completed item {num} in *{list_name}*.")


def handle_move(chat_id, args):
    """Move an item between lists. Usage: /move todo 2 shopping"""
    parts = args.split() if args else []
    if len(parts) != 3 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /move <from\\_list> <number> <to\\_list>")
        return
    from_list, num, to_list = parts[0], int(parts[1]), parts[2]
    if not db.list_exists(from_list):
        send_message(chat_id, f"No list called *{from_list}*.")
        return
    if not db.list_exists(to_list):
        # Auto-create destination list
        if re.match(r"^[a-z][a-z0-9_]{0,29}$", to_list):
            db.create_list(to_list)
        else:
            send_message(chat_id, f"Invalid list name: *{to_list}*.")
            return
    if db.move_item(from_list, num, to_list):
        send_message(chat_id, f"📦 Moved to *{to_list}*")
    else:
        send_message(chat_id, f"Item {num} not found in *{from_list}*.")


def handle_remove(chat_id, args):
    """Delete a specific item. Usage: /remove todo 2"""
    parts = args.split() if args else []
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /remove <list> <number>")
        return
    list_name, num = parts[0], int(parts[1])
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    removed_text = db.delete_item(list_name, num)
    if removed_text:
        send_message(chat_id, f"🗑 Removed: _{removed_text}_")
    else:
        send_message(chat_id, f"Item {num} not found in *{list_name}*.")


def handle_edit(chat_id, args):
    """Edit an item's text. Usage: /edit todo 2 new text here"""
    parts = args.split(None, 2) if args else []
    if len(parts) < 3 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /edit <list> <number> <new text>")
        return
    list_name, num, new_text = parts[0], int(parts[1]), parts[2]
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    if db.edit_item(list_name, num, new_text):
        send_message(chat_id, f"✏️ Updated: _{new_text}_")
    else:
        send_message(chat_id, f"Item {num} not found in *{list_name}*.")


def handle_due(chat_id, args):
    """Set a due date on an item. Usage: /due todo 2 tomorrow"""
    parts = args.split(None, 2) if args else []
    if len(parts) < 3:
        send_message(chat_id, "Usage: /due <list> <number> <date>")
        return
    list_name = parts[0]
    if not parts[1].isdigit():
        send_message(chat_id, "Usage: /due <list> <number> <date>")
        return
    num = int(parts[1])
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    # Reuse the date parser
    _, due_date = parse_due_date(f"placeholder due:{parts[2]}")
    if not due_date:
        send_message(chat_id, f"Couldn't parse date: *{parts[2]}*\nTry: today, tomorrow, monday, or 2025-03-15")
        return
    if db.set_due_date(list_name, num, due_date):
        send_message(chat_id, f"📅 Due date set: *{due_date}*")
    else:
        send_message(chat_id, f"Item {num} not found in *{list_name}*.")


def handle_undue(chat_id, args):
    """Remove a due date from an item. Usage: /undue todo 2"""
    parts = args.split() if args else []
    if len(parts) != 2 or not parts[1].isdigit():
        send_message(chat_id, "Usage: /undue <list> <number>")
        return
    list_name, num = parts[0], int(parts[1])
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*.")
        return
    if db.set_due_date(list_name, num, None):
        send_message(chat_id, "📅 Due date removed.")
    else:
        send_message(chat_id, f"Item {num} not found in *{list_name}*.")


def handle_clear(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /clear <list>")
        return
    name = args.strip().lower()
    if not db.list_exists(name):
        send_message(chat_id, f"No list called *{name}*.")
        return
    count = db.clear_done(name)
    send_message(chat_id, f"🧹 Cleared {count} completed item(s) from *{name}*.")


def handle_all(chat_id):
    items = db.get_all_pending()
    if not items:
        send_message(chat_id, "🎉 Nothing pending! You're all caught up.")
        return

    grouped = {}
    for item in items:
        grouped.setdefault(item["list_name"], []).append(item)

    lines = ["📋 *Everything pending*\n"]
    for list_name, list_items in grouped.items():
        lines.append(f"*{list_name}:*")
        for item in list_items:
            due = f" 📅 {item['due_date']}" if item["due_date"] else ""
            lines.append(f"  • {item['text']}{due}")
        lines.append("")

    send_message(chat_id, "\n".join(lines))


def handle_briefing(chat_id):
    """Morning briefing: just calls the same logic as the cron trigger."""
    from morning import build_briefing
    send_message(chat_id, build_briefing())


# --- Focus ---

def handle_focus(chat_id):
    """Show today's focus items, or suggest some if none set."""
    focus = db.get_daily_focus()
    if focus:
        lines = ["🎯 *Today's focus*\n"]
        buttons = []
        for i, item in enumerate(focus, 1):
            if item["done"]:
                lines.append(f"  ✅ ~{item['text']}~")
            else:
                lines.append(f"  {i}. {item['text']}")
                buttons.append([(f"✅ Done: {item['text'][:20]}", f"focus:{i}")])
        keyboard = make_keyboard(buttons) if buttons else None
        send_message(chat_id, "\n".join(lines), reply_markup=keyboard)
    else:
        suggestions = db.get_focus_items(limit=5)
        if suggestions:
            lines = ["🎯 *Suggested focus for today:*\n"]
            db.set_daily_focus([item["text"] for item in suggestions])
            focus = db.get_daily_focus()
            buttons = []
            for i, item in enumerate(focus, 1):
                due = f" 📅 {suggestions[i-1]['due_date']}" if i <= len(suggestions) and suggestions[i-1]["due_date"] else ""
                lines.append(f"  {i}. {item['text']}{due}")
                buttons.append([(f"✅ Done: {item['text'][:20]}", f"focus:{i}")])
            keyboard = make_keyboard(buttons) if buttons else None
            send_message(chat_id, "\n".join(lines), reply_markup=keyboard)
        else:
            send_message(chat_id, "🎯 Nothing pending to focus on — enjoy your day!")


def handle_done_focus(chat_id, args):
    if not args or not args.strip().isdigit():
        send_message(chat_id, "Usage: /done\\_focus <number>")
        return
    num = int(args.strip())
    if db.mark_focus_done(num):
        send_message(chat_id, "✅ Nice one!")
    else:
        send_message(chat_id, f"No focus item {num}.")


# --- Tracking ---

def handle_track(chat_id, args):
    """Log a tracking entry. Usage: /track mood 7 feeling great"""
    if not args:
        send_message(chat_id, (
            "Usage: /track <type> [value] [notes]\n\n"
            "Examples:\n"
            "  /track mood 7 feeling good\n"
            "  /track workout 45 morning run\n"
            "  /track sleep 7.5\n"
            "  /track energy 4 low day"
        ))
        return

    parts = args.split(None, 2)
    type_ = parts[0].lower()

    value = None
    notes = None

    if len(parts) >= 2:
        try:
            value = float(parts[1])
            notes = parts[2] if len(parts) > 2 else None
        except ValueError:
            # No numeric value, everything after type is notes
            notes = " ".join(parts[1:])

    db.add_tracking(type_, value, notes)

    response = f"📊 Logged *{type_}*"
    if value is not None:
        response += f": {value}"
    if notes:
        response += f" — {notes}"
    send_message(chat_id, response)


# --- Habits ---

def handle_newhabit(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /newhabit <name>")
        return
    name = args.strip().lower()
    if db.create_habit(name):
        send_message(chat_id, f"✅ Habit *{name}* created. Log it with /log {name}")
    else:
        send_message(chat_id, f"Habit *{name}* already exists.")


def handle_deletehabit(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /deletehabit <name>")
        return
    name = args.strip().lower()
    if db.delete_habit(name):
        send_message(chat_id, f"🗑 Deleted habit *{name}*.")
    else:
        send_message(chat_id, f"No habit called *{name}*.")


def handle_log(chat_id, args):
    if not args:
        send_message(chat_id, "Usage: /log <habit>")
        return
    name = args.strip().lower()
    habits = {h["name"] for h in db.get_habits()}
    if name not in habits:
        send_message(chat_id, f"No habit called *{name}*. Create one with /newhabit {name}")
        return
    db.log_habit(name)
    streak = db.get_habit_streak(name)
    streak_msg = f" — {streak} day streak! 🔥" if streak > 1 else ""
    send_message(chat_id, f"✅ Logged *{name}*{streak_msg}")


def handle_habits(chat_id):
    habits = db.get_habits()
    if not habits:
        send_message(chat_id, "No habits yet. Create one with /newhabit <name>")
        return

    logged_today = db.get_habits_logged_today()

    lines = ["🔄 *Your habits*\n"]
    buttons = []
    for habit in habits:
        name = habit["name"]
        streak = db.get_habit_streak(name)
        done_today = name in logged_today
        icon = "✅" if done_today else "⬜"
        streak_str = f" ({streak}🔥)" if streak > 0 else ""
        lines.append(f"  {icon} *{name}*{streak_str}")
        if not done_today:
            buttons.append([(f"✅ Log {name}", f"habit:{name}")])

    keyboard = make_keyboard(buttons) if buttons else None
    send_message(chat_id, "\n".join(lines), reply_markup=keyboard)


# --- Freeform capture (LLM-powered) ---

def handle_freeform(chat_id, text):
    """Parse freeform text using Haiku and act on the results."""
    try:
        from llm import parse_freeform
    except ImportError:
        send_message(chat_id, "LLM module not available. Use commands instead — /help")
        return

    # Get existing list names for context
    lists = db.get_lists()
    list_names = [l["name"] for l in lists]

    # Ensure inbox exists as a fallback list
    if "inbox" not in list_names:
        db.create_list("inbox", "Catch-all for unsorted items")
        list_names.append("inbox")

    actions = parse_freeform(text, list_names)

    if not actions:
        send_message(chat_id, "Sorry, I couldn't parse that. Try again or use /help for commands.")
        return

    # Process create_list actions first, so items can go into new lists
    for action in actions:
        if action.get("action") == "create_list":
            new_list = action.get("list", "").lower()
            desc = action.get("description", "")
            if new_list and re.match(r"^[a-z][a-z0-9_]{0,29}$", new_list):
                db.create_list(new_list, desc)

    responses = []
    for action in actions:
        a_type = action.get("action")

        if a_type == "list_item":
            list_name = action.get("list", "inbox").lower()
            item_text = action.get("text", "")
            due = action.get("due_date")

            # Auto-create the list if it doesn't exist (instead of falling back to inbox)
            if not db.list_exists(list_name):
                if re.match(r"^[a-z][a-z0-9_]{0,29}$", list_name):
                    db.create_list(list_name)
                    responses.append(f"📋 Created list *{list_name}*")
                else:
                    list_name = "inbox"

            db.add_item(list_name, item_text, due_date=due)
            due_msg = f" 📅 {due}" if due else ""
            responses.append(f"➕ *{list_name}*: {item_text}{due_msg}")

        elif a_type == "tracking":
            type_ = action.get("type", "custom")
            value = action.get("value")
            notes = action.get("notes", "")
            db.add_tracking(type_, value, notes)
            val_str = f": {value}" if value is not None else ""
            note_str = f" — {notes}" if notes else ""
            responses.append(f"📊 Tracked *{type_}*{val_str}{note_str}")

        elif a_type == "remove_item":
            list_name = action.get("list", "").lower()
            search_text = action.get("text", "")
            if list_name and db.list_exists(list_name) and search_text:
                pos, item = db.find_item_by_text(list_name, search_text)
                if pos:
                    removed = db.delete_item(list_name, pos)
                    responses.append(f"🗑 Removed from *{list_name}*: _{removed}_")
                else:
                    responses.append(f"Couldn't find \"{search_text}\" in *{list_name}*.")
            else:
                responses.append(f"Couldn't find that item to remove.")

        elif a_type == "mark_done":
            list_name = action.get("list", "").lower()
            search_text = action.get("text", "")
            if list_name and db.list_exists(list_name) and search_text:
                pos, item = db.find_item_by_text(list_name, search_text)
                if pos:
                    db.mark_done(list_name, pos)
                    responses.append(f"✅ Done: _{item['text']}_")
                else:
                    responses.append(f"Couldn't find \"{search_text}\" in *{list_name}*.")
            else:
                responses.append(f"Couldn't find that item to mark done.")

        elif a_type == "create_list":
            # Already processed above, just add response
            new_list = action.get("list", "").lower()
            if new_list and db.list_exists(new_list):
                responses.append(f"📋 Created list *{new_list}*")

        elif a_type == "query":
            query_type = action.get("type", "show_all")
            query_list = action.get("list")

            if query_type == "show_list" and query_list:
                if db.list_exists(query_list.lower()):
                    items = db.get_items(query_list.lower(), include_done=True)
                    responses.append(format_items(items, query_list.lower(), show_done=True))
                else:
                    responses.append(f"No list called *{query_list}*.")
            elif query_type == "show_all":
                handle_all(chat_id)
                return  # Already sent
            elif query_type == "show_focus":
                handle_focus(chat_id)
                return
            elif query_type == "show_habits":
                handle_habits(chat_id)
                return
            elif query_type == "show_tracking":
                tracking = db.get_tracking_since(days=7)
                if tracking:
                    lines = ["📊 *Recent tracking (7 days)*\n"]
                    for t in tracking[:15]:
                        val_str = f": {t['value']}" if t["value"] is not None else ""
                        note_str = f" — {t['notes']}" if t["notes"] else ""
                        lines.append(f"  • *{t['type']}*{val_str}{note_str} ({t['created_at'][:10]})")
                    responses.append("\n".join(lines))
                else:
                    responses.append("No tracking data in the last 7 days.")

        elif a_type == "unknown":
            responses.append(f"🤷 Not sure what to do with: _{action.get('text', text)}_")

    if responses:
        send_message(chat_id, "\n".join(responses))
    else:
        send_message(chat_id, "Processed, but nothing to report.")


def handle_list_command(chat_id, list_name, args):
    """Handle /<listname> or /<listname> <item text>."""
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*. Create it with /newlist {list_name}")
        return

    categories = LIST_CATEGORIES.get(list_name, {})

    if not args:
        # Show list with buttons
        items = db.get_items(list_name, include_done=True)
        text, keyboard = format_items(items, list_name, show_done=True, with_buttons=True)
        send_message(chat_id, text, reply_markup=keyboard)
        return

    # Check for category filter: "watch films" or "watch shows"
    if categories:
        filter_word = args.strip().lower()
        for cat in categories:
            if filter_word == cat or filter_word == cat + "s":
                items = db.get_items(list_name, include_done=True)
                filtered = [i for i in items
                            if json.loads(i["metadata"] or "{}").get("category") == cat]
                text, keyboard = format_items(filtered, f"{list_name} ({cat}s)",
                                              show_done=True, with_buttons=True)
                send_message(chat_id, text, reply_markup=keyboard)
                return

    # Check for category prefix: "watch film The Godfather"
    if categories:
        first_word = args.split(None, 1)[0].lower()
        if first_word in categories:
            rest = args.split(None, 1)[1] if len(args.split(None, 1)) > 1 else ""
            if not rest:
                send_message(chat_id, f"Usage: {list_name} {first_word} <title>")
                return
            text, due_date = parse_due_date(rest)
            emoji = categories[first_word]
            db.add_item(list_name, text, due_date=due_date, metadata={"category": first_word})
            due_msg = f" (due {due_date})" if due_date else ""
            send_message(chat_id, f"{emoji} Added to *{list_name}*: _{text}_{due_msg}")
            return

    # Normal add
    text, due_date = parse_due_date(args)
    db.add_item(list_name, text, due_date=due_date)
    due_msg = f" (due {due_date})" if due_date else ""
    send_message(chat_id, f"➕ Added to *{list_name}*{due_msg}")


# --- Main dispatcher ---

# --- Weekly review ---

def handle_review_response(chat_id, text):
    """Handle a message while a review is active. Returns True if consumed."""
    review = db.get_active_review()
    if not review:
        return False

    step = review["step"]
    if step >= len(db.REVIEW_QUESTIONS):
        return False

    # /skip skips the current question
    is_skip = text.strip().lower() in ("skip", "/skip")
    answer = None if is_skip else text

    next_step = db.advance_review(review["id"], answer or "skipped")

    if next_step is not None and next_step < len(db.REVIEW_QUESTIONS):
        # Ask next question
        send_message(chat_id,
                     f"*{db.REVIEW_QUESTIONS[next_step]}*\n\n(Type your answer, or /skip)")
    elif next_step is not None:
        # All questions done — generate summary
        answers = {
            "q1": review["q1_answer"] if step > 0 else (answer or "skipped"),
            "q2": review["q2_answer"] if step > 1 else (answer or "skipped"),
            "q3": answer or "skipped",
        }
        # Re-read to get all stored answers
        final = db.get_past_reviews(limit=1)
        if final:
            r = final[0]
            answers = {
                "q1": r["q1_answer"] or "skipped",
                "q2": r["q2_answer"] or "skipped",
                "q3": r["q3_answer"] or "skipped",
            }

        wins_data = json.loads(review["wins_data"] or "{}")

        try:
            from llm import generate_review_summary
            summary = generate_review_summary(wins_data, answers)
        except Exception:
            summary = None

        if summary:
            db.save_review_summary(review["id"], summary)
            send_message(chat_id, f"📝 *Your Weekly Review*\n\n{summary}")
        else:
            send_message(chat_id, "📝 Review saved. Thanks for reflecting!")

    return True


# --- Callback handler (button taps) ---

def handle_callback(chat_id, callback):
    """Process an inline keyboard button tap."""
    data = callback["data"]
    message_id = callback["message_id"]
    callback_id = callback["id"]

    parts = data.split(":")
    action = parts[0]

    if action == "done" and len(parts) == 3:
        list_name, num = parts[1], int(parts[2])
        if db.list_exists(list_name) and db.mark_done(list_name, num):
            answer_callback(callback_id, "✅ Done!")
            # Refresh the list in place
            items = db.get_items(list_name, include_done=True)
            text, keyboard = format_items(items, list_name, show_done=True, with_buttons=True)
            edit_message(chat_id, message_id, text, reply_markup=keyboard)
        else:
            answer_callback(callback_id, "Item not found")

    elif action == "focus" and len(parts) == 2:
        num = int(parts[1])
        if db.mark_focus_done(num):
            answer_callback(callback_id, "✅ Nice one!")
            # Refresh focus display
            focus = db.get_daily_focus()
            lines = ["🎯 *Today's focus*\n"]
            buttons = []
            for i, item in enumerate(focus, 1):
                if item["done"]:
                    lines.append(f"  ✅ ~{item['text']}~")
                else:
                    lines.append(f"  {i}. {item['text']}")
                    buttons.append([(f"✅ Done: {item['text'][:20]}", f"focus:{i}")])
            keyboard = make_keyboard(buttons) if buttons else None
            edit_message(chat_id, message_id, "\n".join(lines), reply_markup=keyboard)
        else:
            answer_callback(callback_id, "Item not found")

    elif action == "habit" and len(parts) == 2:
        name = parts[1]
        habits = {h["name"] for h in db.get_habits()}
        if name in habits:
            db.log_habit(name)
            streak = db.get_habit_streak(name)
            streak_msg = f" — {streak} day streak! 🔥" if streak > 1 else ""
            answer_callback(callback_id, f"✅ Logged {name}{streak_msg}")
            # Refresh habits display
            handle_habits_refresh(chat_id, message_id)
        else:
            answer_callback(callback_id, "Habit not found")

    else:
        answer_callback(callback_id)


def handle_habits_refresh(chat_id, message_id):
    """Refresh the habits message in place after a button tap."""
    habits = db.get_habits()
    logged_today = db.get_habits_logged_today()

    lines = ["🔄 *Your habits*\n"]
    buttons = []
    for habit in habits:
        name = habit["name"]
        streak = db.get_habit_streak(name)
        done_today = name in logged_today
        icon = "✅" if done_today else "⬜"
        streak_str = f" ({streak}🔥)" if streak > 0 else ""
        lines.append(f"  {icon} *{name}*{streak_str}")
        if not done_today:
            buttons.append([(f"✅ Log {name}", f"habit:{name}")])

    keyboard = make_keyboard(buttons) if buttons else None
    edit_message(chat_id, message_id, "\n".join(lines), reply_markup=keyboard)


COMMAND_MAP = {
    "start": handle_start,
    "help": handle_help,
    "lists": handle_lists,
    "all": handle_all,
    "briefing": handle_briefing,
    "focus": handle_focus,
    "habits": handle_habits,
}

COMMAND_WITH_ARGS_MAP = {
    "newlist": handle_newlist,
    "deletelist": handle_deletelist,
    "rename": handle_rename,
    "done": handle_done,
    "undo": handle_undo,
    "remove": handle_remove,
    "edit": handle_edit,
    "due": handle_due,
    "undue": handle_undue,
    "clear": handle_clear,
    "move": handle_move,
    "track": handle_track,
    "newhabit": handle_newhabit,
    "deletehabit": handle_deletehabit,
    "log": handle_log,
    "done_focus": handle_done_focus,
}


def handle_message(chat_id, text):
    """Route an incoming message to the right handler.

    Works with or without a leading slash. If the message doesn't match
    any command or list name, it's sent to the LLM for freeform parsing.
    """
    if not text:
        return

    # Strip bot username suffix (e.g., /todo@MyBot)
    text = re.sub(r"@\S+", "", text, count=1)

    # Strip leading slash if present
    has_slash = text.startswith("/")
    clean = text[1:] if has_slash else text

    parts = clean.split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Fixed commands (no args)
    if command in COMMAND_MAP:
        COMMAND_MAP[command](chat_id)
        return

    # Fixed commands (with args)
    if command in COMMAND_WITH_ARGS_MAP:
        COMMAND_WITH_ARGS_MAP[command](chat_id, args)
        return

    # Dynamic list command (if the first word matches a list name)
    if db.list_exists(command):
        handle_list_command(chat_id, command, args)
        return

    # If a weekly review is active, treat as a review answer
    if handle_review_response(chat_id, text.lstrip("/")):
        return

    # Nothing matched — send to LLM for freeform parsing
    handle_freeform(chat_id, text.lstrip("/"))
