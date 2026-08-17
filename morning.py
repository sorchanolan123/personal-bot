#!/usr/bin/env python3
"""Morning briefing builder.

Called by app.py's /trigger/morning endpoint (via external cron service),
or run directly: python morning.py
"""

import sys
import os

# Ensure the project directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import CHAT_ID
from db import (init_db, get_overdue, get_due_today, get_stale_items,
                get_completed_since, get_focus_items, set_daily_focus,
                get_habits, get_habit_streak)
from telegram import send_message


def build_briefing():
    lines = ["☀️ *Morning Briefing*\n"]

    # What you got done yesterday
    completed = get_completed_since(days=1)
    if completed:
        lines.append(f"✅ *Completed yesterday:* {len(completed)} item(s)")
        for item in completed[:5]:
            lines.append(f"  • {item['text']}")
        if len(completed) > 5:
            lines.append(f"  ...and {len(completed) - 5} more")
        lines.append("")

    # Overdue
    overdue = get_overdue()
    if overdue:
        lines.append("🔴 *Overdue:*")
        for item in overdue:
            lines.append(f"  • {item['text']} (was due {item['due_date']}) — /{item['list_name']}")
        lines.append("")

    # Due today
    due_today = get_due_today()
    if due_today:
        lines.append("📅 *Due today:*")
        for item in due_today:
            lines.append(f"  • {item['text']} — /{item['list_name']}")
        lines.append("")

    # Today's focus — pick 3-5 items
    focus = get_focus_items(limit=5)
    if focus:
        set_daily_focus([item["text"] for item in focus])
        lines.append("🎯 *Today's focus:*")
        for i, item in enumerate(focus, 1):
            due = f" 📅 {item['due_date']}" if item["due_date"] else ""
            lines.append(f"  {i}. {item['text']}{due}")
        lines.append("")
    else:
        lines.append("🎉 Nothing pending! Enjoy your day.\n")

    # Habits reminder
    habits = get_habits()
    if habits:
        lines.append("🔄 *Habits to log today:*")
        for h in habits:
            streak = get_habit_streak(h["name"])
            streak_str = f" ({streak}🔥)" if streak > 0 else ""
            lines.append(f"  ⬜ {h['name']}{streak_str} — /log {h['name']}")
        lines.append("")

    # Stale items nudge
    stale = get_stale_items(days=7)
    if stale:
        lines.append(f"💤 {len(stale)} item(s) untouched for 7+ days.")

    return "\n".join(lines)


def main():
    if not CHAT_ID:
        print("Error: TELEGRAM_CHAT_ID not set in config.py or environment.")
        sys.exit(1)

    init_db()
    briefing = build_briefing()
    result = send_message(CHAT_ID, briefing)
    print(f"Briefing sent: {result.get('ok', False)}")


if __name__ == "__main__":
    main()
