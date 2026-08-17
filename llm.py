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
    """
    system = f"""You are a personal assistant parser. The user sent a freeform message to their life management bot.
Parse it into structured actions. Return ONLY valid JSON — an array of action objects.

Available lists: {json.dumps(existing_lists)}

Action types:

1. "list_item" — something to add to a list.
   {{"action": "list_item", "list": "<existing list name>", "text": "<item text>", "due_date": "<YYYY-MM-DD or null>"}}
   If the item fits an existing list, use it. If no list fits well, use "inbox".

2. "tracking" — a life event, metric, or status update (mood, workout, sleep, health, etc.)
   {{"action": "tracking", "type": "<mood|workout|sleep|energy|health|custom>", "value": <number or null>, "notes": "<description>"}}
   For mood/energy: value is 1-10. For workout: value can be duration in minutes or null. For sleep: value is hours.

3. "create_list" — suggest creating a new list if the user's message implies one that doesn't exist yet.
   {{"action": "create_list", "list": "<name>", "description": "<what it's for>"}}
   Only suggest this if the items clearly don't fit any existing list.

Rules:
- One message can produce multiple actions (e.g. "buy milk and I worked out for 30 mins" → list_item + tracking)
- Parse dates naturally: "tomorrow", "next friday", "by the 15th" → YYYY-MM-DD
- Today's date context will be provided in the user message
- Keep item text clean and concise
- If the message is conversational or you can't parse it, return: [{{"action": "unknown", "text": "<original>"}}]
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
