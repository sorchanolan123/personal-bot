import sqlite3
import json
from datetime import datetime, timedelta
from config import DB_PATH

RESERVED_COMMANDS = {
    "start", "help", "newlist", "deletelist", "lists", "done",
    "undo", "clear", "all", "briefing", "rename", "move", "remove",
    "edit", "due", "undue", "track", "habits", "newhabit",
    "deletehabit", "log", "focus", "evening", "skip",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS lists (
            name TEXT PRIMARY KEY,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_name TEXT NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 0,
            due_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (list_name) REFERENCES lists(name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            value REAL,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            schedule TEXT DEFAULT 'daily',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_name TEXT NOT NULL,
            done INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (habit_name) REFERENCES habits(name) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS weekly_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            step INTEGER DEFAULT 0,
            wins_data TEXT DEFAULT '{}',
            q1_answer TEXT,
            q2_answer TEXT,
            q3_answer TEXT,
            summary TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        );
    """)
    conn.commit()
    conn.close()


# --- List operations ---

def create_list(name, description=None):
    name = name.lower().strip()
    if name in RESERVED_COMMANDS:
        return False, "reserved"
    conn = get_db()
    try:
        conn.execute("INSERT INTO lists (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
        return True, "created"
    except sqlite3.IntegrityError:
        return False, "exists"
    finally:
        conn.close()


def delete_list(name):
    conn = get_db()
    conn.execute("DELETE FROM items WHERE list_name = ?", (name.lower(),))
    cursor = conn.execute("DELETE FROM lists WHERE name = ?", (name.lower(),))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def rename_list(old_name, new_name):
    old_name, new_name = old_name.lower().strip(), new_name.lower().strip()
    if new_name in RESERVED_COMMANDS:
        return False, "reserved"
    conn = get_db()
    try:
        # Temporarily disable FK checks — items reference the old name
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("UPDATE lists SET name = ? WHERE name = ?", (new_name, old_name))
        conn.execute("UPDATE items SET list_name = ? WHERE list_name = ?", (new_name, old_name))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.commit()
        return True, "renamed"
    except sqlite3.IntegrityError:
        conn.execute("PRAGMA foreign_keys=ON")
        return False, "exists"
    finally:
        conn.close()


def get_lists():
    conn = get_db()
    lists = conn.execute("""
        SELECT l.name, l.description,
               COUNT(i.id) as total,
               SUM(CASE WHEN i.done = 0 THEN 1 ELSE 0 END) as pending
        FROM lists l
        LEFT JOIN items i ON l.name = i.list_name
        GROUP BY l.name
        ORDER BY l.name
    """).fetchall()
    conn.close()
    return lists


def list_exists(name):
    conn = get_db()
    exists = conn.execute(
        "SELECT 1 FROM lists WHERE name = ?", (name.lower(),)
    ).fetchone() is not None
    conn.close()
    return exists


# --- Item operations ---

def add_item(list_name, text, due_date=None, metadata=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO items (list_name, text, due_date, metadata) VALUES (?, ?, ?, ?)",
        (list_name.lower(), text, due_date, json.dumps(metadata or {}))
    )
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return item_id


def get_items(list_name, include_done=False):
    conn = get_db()
    if include_done:
        # Show pending items + items completed in the last 24 hours
        cutoff = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        items = conn.execute(
            "SELECT * FROM items WHERE list_name = ? "
            "AND (done = 0 OR completed_at >= ?) "
            "ORDER BY done, created_at",
            (list_name.lower(), cutoff)
        ).fetchall()
    else:
        items = conn.execute(
            "SELECT * FROM items WHERE list_name = ? AND done = 0 ORDER BY created_at",
            (list_name.lower(),)
        ).fetchall()
    conn.close()
    return items


def move_item(from_list, item_number, to_list):
    """Move an item from one list to another by position (1-indexed)."""
    items = get_items(from_list)
    if item_number < 1 or item_number > len(items):
        return False
    item_id = items[item_number - 1]["id"]
    conn = get_db()
    conn.execute("UPDATE items SET list_name = ? WHERE id = ?", (to_list.lower(), item_id))
    conn.commit()
    conn.close()
    return True


def delete_item(list_name, item_number):
    """Delete a specific item by position (1-indexed)."""
    items = get_items(list_name)
    if item_number < 1 or item_number > len(items):
        return None
    item = items[item_number - 1]
    conn = get_db()
    conn.execute("DELETE FROM items WHERE id = ?", (item["id"],))
    conn.commit()
    conn.close()
    return item["text"]


def edit_item(list_name, item_number, new_text):
    """Edit the text of an item by position (1-indexed)."""
    items = get_items(list_name)
    if item_number < 1 or item_number > len(items):
        return False
    item_id = items[item_number - 1]["id"]
    conn = get_db()
    conn.execute("UPDATE items SET text = ? WHERE id = ?", (new_text, item_id))
    conn.commit()
    conn.close()
    return True


def set_due_date(list_name, item_number, due_date):
    """Set or clear the due date on an item by position (1-indexed). Pass None to remove."""
    items = get_items(list_name)
    if item_number < 1 or item_number > len(items):
        return False
    item_id = items[item_number - 1]["id"]
    conn = get_db()
    conn.execute("UPDATE items SET due_date = ? WHERE id = ?", (due_date, item_id))
    conn.commit()
    conn.close()
    return True


def find_item_by_text(list_name, search_text):
    """Find an item by partial text match. Returns (position, item) or (None, None)."""
    items = get_items(list_name)
    search_lower = search_text.lower()
    for i, item in enumerate(items, 1):
        if search_lower in item["text"].lower():
            return i, item
    return None, None


def mark_done(list_name, item_number):
    """Mark item done by its position in the active list (1-indexed)."""
    items = get_items(list_name)
    if item_number < 1 or item_number > len(items):
        return False
    item_id = items[item_number - 1]["id"]
    conn = get_db()
    conn.execute(
        "UPDATE items SET done = 1, completed_at = datetime('now') WHERE id = ?",
        (item_id,)
    )
    conn.commit()
    conn.close()
    return True


def mark_undone(list_name, item_number):
    """Undo the most recently completed items (1-indexed from recent)."""
    conn = get_db()
    items = conn.execute(
        "SELECT * FROM items WHERE list_name = ? AND done = 1 ORDER BY completed_at DESC",
        (list_name.lower(),)
    ).fetchall()
    if item_number < 1 or item_number > len(items):
        conn.close()
        return False
    item_id = items[item_number - 1]["id"]
    conn.execute(
        "UPDATE items SET done = 0, completed_at = NULL WHERE id = ?",
        (item_id,)
    )
    conn.commit()
    conn.close()
    return True


def transform_list_items(list_name, transform):
    """Apply a text transformation to all pending items in a list.
    transform: 'capitalize'|'uppercase'|'lowercase'|'title_case'
    Returns count of items changed."""
    items = get_items(list_name, include_done=False)
    if not items:
        return 0
    transforms = {
        "capitalize": lambda s: s.capitalize(),
        "uppercase": lambda s: s.upper(),
        "lowercase": lambda s: s.lower(),
        "title_case": lambda s: s.title(),
    }
    fn = transforms.get(transform)
    if not fn:
        return 0
    conn = get_db()
    count = 0
    for item in items:
        new_text = fn(item["text"])
        if new_text != item["text"]:
            conn.execute("UPDATE items SET text = ? WHERE id = ?", (new_text, item["id"]))
            count += 1
    conn.commit()
    conn.close()
    return count


def clear_done(list_name):
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM items WHERE list_name = ? AND done = 1",
        (list_name.lower(),)
    )
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


# --- Briefing helpers ---

def get_all_pending():
    """All pending items across every list, for the morning briefing."""
    conn = get_db()
    items = conn.execute("""
        SELECT list_name, text, due_date, created_at
        FROM items WHERE done = 0
        ORDER BY
            CASE WHEN due_date IS NOT NULL THEN 0 ELSE 1 END,
            due_date, created_at
    """).fetchall()
    conn.close()
    return items


def get_due_today():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    items = conn.execute(
        "SELECT * FROM items WHERE due_date = ? AND done = 0", (today,)
    ).fetchall()
    conn.close()
    return items


def get_overdue():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    items = conn.execute(
        "SELECT * FROM items WHERE due_date < ? AND done = 0 AND due_date IS NOT NULL",
        (today,)
    ).fetchall()
    conn.close()
    return items


def get_completed_since(days=7):
    conn = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    items = conn.execute(
        "SELECT * FROM items WHERE done = 1 AND completed_at >= ? ORDER BY completed_at DESC",
        (since,)
    ).fetchall()
    conn.close()
    return items


def get_stale_items(days=7):
    """Pending items untouched for N days."""
    conn = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    items = conn.execute(
        "SELECT * FROM items WHERE done = 0 AND created_at <= ? ORDER BY created_at",
        (cutoff,)
    ).fetchall()
    conn.close()
    return items


def get_due_tomorrow():
    conn = get_db()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    items = conn.execute(
        "SELECT * FROM items WHERE due_date = ? AND done = 0", (tomorrow,)
    ).fetchall()
    conn.close()
    return items


def get_upcoming(days=7):
    """Pending items due in the next N days (excluding today)."""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    items = conn.execute(
        "SELECT * FROM items WHERE due_date > ? AND due_date <= ? AND done = 0 "
        "ORDER BY due_date, created_at",
        (today, end)
    ).fetchall()
    conn.close()
    return items


def get_focus_today():
    """Get today's focus: items due today (pending) + items completed today."""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    items = conn.execute(
        "SELECT * FROM items WHERE "
        "(due_date = ? AND done = 0) OR "
        "(done = 1 AND date(completed_at) = ?) "
        "ORDER BY done, due_date, created_at",
        (today, today)
    ).fetchall()
    conn.close()
    return items


def mark_done_by_id(item_id):
    """Mark an item done by its database ID."""
    conn = get_db()
    conn.execute(
        "UPDATE items SET done = 1, completed_at = datetime('now') WHERE id = ?",
        (item_id,)
    )
    conn.commit()
    conn.close()


# --- Tracking operations ---

def add_tracking(type_, value=None, notes=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO tracking (type, value, notes) VALUES (?, ?, ?)",
        (type_.lower(), value, notes)
    )
    conn.commit()
    conn.close()


def get_tracking_since(days=7):
    conn = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT * FROM tracking WHERE created_at >= ? ORDER BY created_at DESC",
        (since,)
    ).fetchall()
    conn.close()
    return rows


def get_tracking_today():
    """Get all tracking entries from today."""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM tracking WHERE date(created_at) = ? ORDER BY created_at DESC",
        (today,)
    ).fetchall()
    conn.close()
    return rows


def get_tracking_by_type(type_, days=30):
    conn = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT * FROM tracking WHERE type = ? AND created_at >= ? ORDER BY created_at",
        (type_.lower(), since)
    ).fetchall()
    conn.close()
    return rows


# --- Habit operations ---

def create_habit(name, schedule="daily"):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO habits (name, schedule) VALUES (?, ?)",
            (name.lower().strip(), schedule)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_habit(name):
    conn = get_db()
    conn.execute("DELETE FROM habit_logs WHERE habit_name = ?", (name.lower(),))
    cursor = conn.execute("DELETE FROM habits WHERE name = ?", (name.lower(),))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def get_habits():
    conn = get_db()
    habits = conn.execute("SELECT * FROM habits ORDER BY name").fetchall()
    conn.close()
    return habits


def log_habit(name, done=True):
    conn = get_db()
    conn.execute(
        "INSERT INTO habit_logs (habit_name, done) VALUES (?, ?)",
        (name.lower(), 1 if done else 0)
    )
    conn.commit()
    conn.close()


def get_habit_streak(name):
    """Count consecutive days the habit was logged."""
    conn = get_db()
    logs = conn.execute(
        "SELECT DISTINCT date(created_at) as day FROM habit_logs "
        "WHERE habit_name = ? AND done = 1 ORDER BY day DESC",
        (name.lower(),)
    ).fetchall()
    conn.close()

    if not logs:
        return 0

    streak = 0
    expected = datetime.now().date()
    for log in logs:
        log_date = datetime.strptime(log["day"], "%Y-%m-%d").date()
        if log_date == expected or log_date == expected - timedelta(days=1):
            streak += 1
            expected = log_date - timedelta(days=1)
        else:
            break
    return streak


def get_habits_logged_today():
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    logged = conn.execute(
        "SELECT DISTINCT habit_name FROM habit_logs WHERE date(created_at) = ?",
        (today,)
    ).fetchall()
    conn.close()
    return {row["habit_name"] for row in logged}


def get_habit_logs_since(days=7):
    conn = get_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT habit_name, date(created_at) as day, done FROM habit_logs "
        "WHERE created_at >= ? ORDER BY created_at",
        (since,)
    ).fetchall()
    conn.close()
    return rows


# --- Weekly review ---

REVIEW_QUESTIONS = [
    "What went well this week?",
    "What didn't go as planned?",
    "What do you want to focus on next week?",
]


def start_weekly_review(wins_data):
    """Create a new review session. Returns the review id."""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    # Expire any stale open reviews
    conn.execute(
        "UPDATE weekly_reviews SET completed_at = datetime('now') "
        "WHERE completed_at IS NULL"
    )
    conn.execute(
        "INSERT INTO weekly_reviews (week_start, step, wins_data) VALUES (?, 0, ?)",
        (today, json.dumps(wins_data))
    )
    conn.commit()
    review_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return review_id


def get_active_review():
    """Return the active (incomplete) review, or None."""
    conn = get_db()
    review = conn.execute(
        "SELECT * FROM weekly_reviews WHERE completed_at IS NULL "
        "ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return review


def advance_review(review_id, answer):
    """Store the answer for the current step and advance to the next."""
    conn = get_db()
    review = conn.execute(
        "SELECT * FROM weekly_reviews WHERE id = ?", (review_id,)
    ).fetchone()
    if not review:
        conn.close()
        return None

    step = review["step"]
    col = f"q{step + 1}_answer"
    next_step = step + 1

    conn.execute(f"UPDATE weekly_reviews SET {col} = ?, step = ? WHERE id = ?",
                 (answer, next_step, review_id))

    if next_step >= len(REVIEW_QUESTIONS):
        conn.execute(
            "UPDATE weekly_reviews SET completed_at = datetime('now') WHERE id = ?",
            (review_id,)
        )

    conn.commit()
    conn.close()
    return next_step


def save_review_summary(review_id, summary):
    conn = get_db()
    conn.execute("UPDATE weekly_reviews SET summary = ? WHERE id = ?",
                 (summary, review_id))
    conn.commit()
    conn.close()


def get_past_reviews(limit=4):
    conn = get_db()
    reviews = conn.execute(
        "SELECT * FROM weekly_reviews WHERE completed_at IS NOT NULL "
        "ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return reviews
