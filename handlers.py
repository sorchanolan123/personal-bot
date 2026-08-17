import re
from datetime import datetime, timedelta
import db
from telegram import send_message


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

def format_items(items, list_name, show_done=False):
    if not items:
        return f"📋 *{list_name}* is empty"

    lines = [f"📋 *{list_name}*\n"]
    num = 1
    for item in items:
        if item["done"]:
            lines.append(f"  ✅ ~{item['text']}~")
        else:
            due = ""
            if item["due_date"]:
                due = f" 📅 {item['due_date']}"
            lines.append(f"  {num}. {item['text']}{due}")
            num += 1
    return "\n".join(lines)


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
        "👋 *Hey! I'm your personal list bot.*\n\n"
        "Create a list: /newlist todo\n"
        "Add an item: /todo buy milk\n"
        "Add with due date: /todo call dentist due:tuesday\n"
        "View a list: /todo\n"
        "Mark done: /done todo 1\n"
        "See all lists: /lists\n"
        "See everything: /all\n\n"
        "Type /help for all commands."
    ))


def handle_help(chat_id):
    send_message(chat_id, (
        "*Commands*\n\n"
        "/newlist <name> \\[description] — create a list\n"
        "/deletelist <name> — delete a list\n"
        "/rename <old> <new> — rename a list\n"
        "/lists — show all lists\n"
        "/<list> — show items in a list\n"
        "/<list> <item> \\[due:date] — add an item\n"
        "/done <list> <number> — mark item done\n"
        "/undo <list> <number> — undo a done item\n"
        "/clear <list> — remove completed items\n"
        "/all — everything pending across all lists\n"
        "/briefing — morning briefing\n\n"
        "*Due dates:* due:today, due:tomorrow, due:monday, due:2025-03-15"
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
    """Morning briefing: overdue, due today, then a summary of all lists."""
    lines = ["☀️ *Morning Briefing*\n"]

    overdue = db.get_overdue()
    if overdue:
        lines.append("🔴 *Overdue:*")
        for item in overdue:
            lines.append(f"  • {item['text']} (was due {item['due_date']}) — /{item['list_name']}")
        lines.append("")

    due_today = db.get_due_today()
    if due_today:
        lines.append("📅 *Due today:*")
        for item in due_today:
            lines.append(f"  • {item['text']} — /{item['list_name']}")
        lines.append("")

    all_pending = db.get_all_pending()
    other = [i for i in all_pending if i not in overdue and i not in due_today]
    if other:
        grouped = {}
        for item in other:
            grouped.setdefault(item["list_name"], []).append(item)
        lines.append("📋 *Other pending:*")
        for list_name, list_items in grouped.items():
            lines.append(f"  *{list_name}:* {len(list_items)} item(s)")
        lines.append("")

    if not overdue and not due_today and not other:
        lines.append("🎉 Nothing pending! Enjoy your day.")

    stale = db.get_stale_items(days=7)
    if stale:
        lines.append(f"💤 {len(stale)} item(s) have been sitting for 7+ days.")

    send_message(chat_id, "\n".join(lines))


def handle_list_command(chat_id, list_name, args):
    """Handle /<listname> or /<listname> <item text>."""
    if not db.list_exists(list_name):
        send_message(chat_id, f"No list called *{list_name}*. Create it with /newlist {list_name}")
        return

    if not args:
        # Show list
        items = db.get_items(list_name, include_done=True)
        send_message(chat_id, format_items(items, list_name, show_done=True))
    else:
        # Add item
        text, due_date = parse_due_date(args)
        item_id = db.add_item(list_name, text, due_date=due_date)
        due_msg = f" (due {due_date})" if due_date else ""
        send_message(chat_id, f"➕ Added to *{list_name}*{due_msg}")


# --- Main dispatcher ---

COMMAND_MAP = {
    "start": handle_start,
    "help": handle_help,
    "lists": handle_lists,
    "all": handle_all,
    "briefing": handle_briefing,
}

COMMAND_WITH_ARGS_MAP = {
    "newlist": handle_newlist,
    "deletelist": handle_deletelist,
    "rename": handle_rename,
    "done": handle_done,
    "undo": handle_undo,
    "clear": handle_clear,
}


def handle_message(chat_id, text):
    """Route an incoming message to the right handler."""
    if not text or not text.startswith("/"):
        return  # Ignore non-command messages

    # Strip bot username suffix (e.g., /todo@MyBot)
    text = re.sub(r"@\S+", "", text, count=1)

    parts = text[1:].split(None, 1)
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

    # Dynamic list command
    handle_list_command(chat_id, command, args)
