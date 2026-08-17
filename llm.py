"""Thin wrapper for Anthropic Haiku calls. Used only where LLM adds real value."""

import json
import requests
from config import ANTHROPIC_API_KEY


def call_haiku(system_prompt, user_message):
    """Make a single Haiku call and return the text response."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None


def parse_freeform(text, existing_lists):
    """Parse a freeform message into structured actions.

    Returns a list of dicts, each one of:
        {"action": "list_item", "list": "...", "text": "...", "due_date": "YYYY-MM-DD" or null}
        {"action": "tracking", "type": "mood|workout|sleep|custom", "value": number or null, "notes": "..."}
        {"action": "create_list", "list": "...", "description": "..."}
        {"action": "query", "type": "show_list|show_all|show_focus|show_habits|show_tracking", "list": "..." or null}
    """
    system = f"""You are a personal assistant parser. The user sent a freeform message to their life management bot.
Parse it into structured actions. Return ONLY valid JSON — an array of action objects.

Available lists: {json.dumps(existing_lists)}

Action types:

1. "list_item" — something to add to a list.
   {{"action": "list_item", "list": "<list name>", "text": "<item text>", "due_date": "<YYYY-MM-DD or null>"}}
   If the item fits an existing list, use it. If the user mentions a list that doesn't exist yet (e.g. "add to my shopping list"), use that name anyway (e.g. "shopping") — the system will auto-create it. Only use "inbox" if there's genuinely no clear category.

2. "tracking" — a life event, metric, or status update (mood, workout, sleep, health, etc.)
   {{"action": "tracking", "type": "<mood|workout|sleep|energy|health|custom>", "value": <number or null>, "notes": "<description>"}}
   For mood/energy: value is 1-10. For workout: value can be duration in minutes or null. For sleep: value is hours.

3. "create_list" — suggest creating a new list if the user's message implies one that doesn't exist yet.
   {{"action": "create_list", "list": "<name>", "description": "<what it's for>"}}
   Only suggest this if the items clearly don't fit any existing list.

4. "remove_item" — remove/delete an item from a list.
   {{"action": "remove_item", "list": "<list name>", "text": "<search text to match>"}}
   Use when the user says "remove X from my list", "delete X", "take X off my shopping list", etc.

5. "mark_done" — mark an item as completed.
   {{"action": "mark_done", "list": "<list name>", "text": "<search text to match>"}}
   Use when the user says "I did X", "X is done", "finished X", "completed X", etc.

6. "query" — the user is ASKING about their data, not adding something.
   {{"action": "query", "type": "<query_type>", "list": "<list name or null>"}}
   Query types:
   - "show_list" — show items in a specific list (set "list" to the list name). Use for "what's on my todo list", "show me my groceries", etc.
   - "show_all" — show everything pending. Use for "what do I need to do", "what's on my plate", "show me everything".
   - "show_focus" — show today's focus items. Use for "what should I focus on", "what's my plan for today".
   - "show_habits" — show habits and streaks. Use for "how are my habits", "what habits do I have".
   - "show_tracking" — show recent tracking data. Use for "how's my mood been", "show my tracking".

Rules:
- One message can produce multiple actions (e.g. "buy milk and I worked out for 30 mins" → list_item + tracking)
- Parse dates naturally: "tomorrow", "next friday", "by the 15th" → YYYY-MM-DD
- Today's date context will be provided in the user message
- Keep item text clean and concise
- IMPORTANT: If the user is asking a question about their lists or data, use "query" — do NOT add it as a list item!
- IMPORTANT: If the user says "add to my X list", use "X" as the list name in list_item actions — even if X isn't in the available lists. The system will create it automatically. Do NOT add "create X list" as a list_item.
- List names must be single lowercase words (letters, numbers, underscores). E.g. "shopping list" → list name "shopping", "work stuff" → list name "work".
- If the message is truly uninterpretable, return: [{{"action": "unknown", "text": "<original>"}}]
- Return ONLY the JSON array, no markdown formatting, no explanation"""

    from datetime import datetime
    dated_message = f"[Today is {datetime.now().strftime('%A, %Y-%m-%d')}]\n\n{text}"

    result = call_haiku(system, dated_message)
    if not result:
        return None

    try:
        # Strip markdown code fences if present
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        return json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        print(f"Failed to parse LLM response: {result}")
        return None


def generate_weekly_summary(completed_items, tracking_data, habit_data):
    """Generate a natural-language weekly summary using Haiku."""
    system = """You are a kind, encouraging personal assistant writing a weekly summary for someone who struggles with executive function. Be warm but concise. Use emoji sparingly. Focus on wins and patterns. Don't be patronising. Keep it under 200 words. Return plain text formatted for Telegram (use *bold* for emphasis)."""

    data = {
        "completed_tasks": [{"list": i["list_name"], "text": i["text"]} for i in completed_items],
        "tracking": [{"type": t["type"], "value": t["value"], "notes": t["notes"], "date": t["created_at"][:10]} for t in tracking_data],
        "habits": habit_data,
    }

    user_msg = f"Here's my data for this week:\n\n{json.dumps(data, indent=2)}\n\nWrite my weekly wins summary."

    result = call_haiku(system, user_msg)
    return result or "Couldn't generate summary this week — but you're doing great regardless. 💪"


def generate_review_summary(wins_data, answers):
    """Generate a combined weekly review summary from stats + reflections."""
    system = """You are a kind, encouraging personal assistant writing a weekly review summary for someone who struggles with executive function. Combine their stats with their own reflections into a short, meaningful summary. Be warm but concise. Don't be patronising. Keep it under 250 words. Return plain text formatted for Telegram (use *bold* for emphasis)."""

    user_msg = f"""Here's the data for this week:

*Stats:*
{json.dumps(wins_data, indent=2)}

*Their reflections:*
What went well: {answers.get('q1', 'skipped')}
What didn't go as planned: {answers.get('q2', 'skipped')}
Focus for next week: {answers.get('q3', 'skipped')}

Write a combined weekly review that weaves together the stats and their reflections. End with their focus for next week."""

    result = call_haiku(system, user_msg)
    return result or "Review saved — keep going. 💪"
