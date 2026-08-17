import sqlite3
import json
from datetime import datetime, timedelta
from config import DB_PATH

RESERVED_COMMANDS = {
    "start", "help", "newlist", "deletelist", "lists", "done",
    "undo", "clear", "all", "briefing", "rename",
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
        conn.execute("UPDATE items SET list_name = ? WHERE list_name = ?", (new_name, old_name))
        conn.execute("UPDATE lists SET name = ? WHERE name = ?", (new_name, old_name))
        conn.commit()
        return True, "renamed"
    except sqlite3.IntegrityError:
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
        items = conn.execute(
            "SELECT * FROM items WHERE list_name = ? ORDER BY done, created_at",
            (list_name.lower(),)
        ).fetchall()
    else:
        items = conn.execute(
            "SELECT * FROM items WHERE list_name = ? AND done = 0 ORDER BY created_at",
            (list_name.lower(),)
        ).fetchall()
    conn.close()
    return items


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
