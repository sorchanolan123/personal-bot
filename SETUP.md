# Personal Telegram Bot — Setup Guide

## 1. Get your bot token (if you haven't already)

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`, follow the prompts
3. Copy the token it gives you

## 2. Set up PythonAnywhere

1. Create a free account at [pythonanywhere.com](https://www.pythonanywhere.com)
2. Go to **Files** and create a directory called `personal-bot`
3. Upload all the project files into that directory
4. Open a **Bash console** and run:
   ```bash
   cd ~/personal-bot
   pip install --user -r requirements.txt
   ```

## 3. Configure

Copy `config.example.py` to `config.py` and fill in:

```python
BOT_TOKEN = "your-token-from-botfather"
WEBHOOK_URL = "https://YOUR-USERNAME.pythonanywhere.com/webhook"
ANTHROPIC_API_KEY = "your-anthropic-api-key"
```

The Anthropic API key is needed for freeform message parsing (Haiku). Without it, commands still work but natural language input won't.

Generate a cron secret (run this in a Python console):
```python
import secrets; print(secrets.token_urlsafe(32))
```

Paste the result into `config.py`:
```python
CRON_SECRET = "your-generated-secret-here"
```

## 4. Create the web app

1. Go to the **Web** tab
2. Click **Add a new web app**
3. Choose **Flask** and **Python 3.10**
4. Set the **Source code** path to `/home/YOUR-USERNAME/personal-bot`
5. In the **WSGI configuration file**, replace the contents with:

```python
import sys
sys.path.insert(0, '/home/YOUR-USERNAME/personal-bot')
from app import app as application
```

6. Click **Reload** the web app

## 5. Register the webhook

In a PythonAnywhere **Bash console**:

```bash
cd ~/personal-bot
python scripts/setup_webhook.py
```

You should see `"ok": true`.

## 6. Test it

Open Telegram, find your bot, and send `/start`. You should get a welcome message back.

To find your **chat ID**: after sending `/start`, go to `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser. Your chat ID will be in the response under `message.chat.id`. Set it as `CHAT_ID` in `config.py` — the scheduled triggers need this.

## 7. Set up scheduled messages (free, using cron-job.org)

PythonAnywhere's free tier doesn't include cron jobs, so we use an external service. This is free and unlimited.

1. Set your `CHAT_ID` in `config.py` (see step 6)
2. Make sure `CRON_SECRET` is set in `config.py` (see step 3)
3. Reload the web app on PythonAnywhere
4. Go to [cron-job.org](https://cron-job.org) and create a free account
5. Create cron jobs for the triggers you want:

| Trigger | URL path | Suggested schedule | What it does |
|---------|----------|--------------------|--------------|
| Morning briefing | `/trigger/morning` | `0 8 * * *` | Overdue items, today's focus, habit reminders |
| Evening check-in | `/trigger/evening` | `0 21 * * *` | Today's progress, unlogged habits with buttons |
| Habit reminder | `/trigger/habits` | `0 13 * * *` | Midday nudge for unlogged habits with inline buttons |
| Deadline nudge | `/trigger/deadline` | `0 20 * * *` | Items due tomorrow |
| One small thing | `/trigger/smallthing` | `0 15 * * *` | Random pending item suggestion |
| Stale items | `/trigger/stale` | `0 10 * * 0` | Items sitting 7+ days |
| Weekly review | `/trigger/weekly` | `0 18 * * 5` | Interactive 3-question reflection |
| Database backup | `/trigger/backup` | `0 3 * * 0` | Sends bot.db as a Telegram document |
| Webhook healthcheck | `/trigger/healthcheck` | `*/30 * * * *` | Re-registers webhook if Telegram dropped it |

All URLs follow the pattern: `https://YOUR-USERNAME.pythonanywhere.com/TRIGGER_PATH?key=YOUR_CRON_SECRET`

## 8. Deploy updates

After pushing changes to GitHub:

```bash
cd ~/personal-bot
bash scripts/deploy.sh
```

This pulls from git, touches the WSGI file to reload, and re-registers the webhook.

## Quick reference — Commands

| Command | What it does |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Full command list |
| `/newlist groceries` | Create a list |
| `/deletelist groceries` | Delete a list |
| `/rename groceries food` | Rename a list |
| `/lists` | Show all lists |
| `/groceries` | View list with inline buttons |
| `/groceries oat milk` | Add an item |
| `/groceries bread due:tomorrow` | Add with due date |
| `/done groceries 2` | Mark item 2 done |
| `/undo groceries 1` | Restore item |
| `/remove groceries 3` | Delete an item |
| `/edit groceries 2 new text` | Edit item text |
| `/due groceries 2 friday` | Set due date |
| `/undue groceries 2` | Remove due date |
| `/move groceries 1 todo` | Move item between lists |
| `/clear groceries` | Remove completed items |
| `/all` | Everything pending across all lists |
| `/focus` | Today's due/completed items with buttons |
| `/briefing` | Morning briefing on demand |

## Quick reference — Tracking & habits

| Command | What it does |
|---------|-------------|
| `/track mood 7 feeling good` | Log a metric with value and notes |
| `/track workout 45 morning run` | Log activity |
| `/newhabit meditate` | Create a habit |
| `/log meditate` | Log a habit for today |
| `/habits` | See all habits + streaks with buttons |
| `/deletehabit meditate` | Remove a habit |

## Quick reference — Natural language

You can also just type naturally instead of using commands:

- "buy oat milk and call dentist by friday" → adds to appropriate lists
- "worked out for 30 mins" → logs tracking entry
- "feeling 7/10 today" → logs mood tracking
- "what's on my todo?" → shows your list

## Quick reference — Date formats

Due dates can be set in several ways:

- Trailing word: `buy milk tomorrow`, `submit report friday`
- Explicit prefix: `call dentist due:monday`, `meeting due:2025-03-15`
- Ordinal day: `dentist on the 5th`, `submit report on the 23rd`
- ISO date: `meeting 2025-03-15`

## File structure

```
personal-bot/
├── app.py              # Flask webhook + cron trigger endpoints
├── config.py           # Secrets & settings (gitignored)
├── config.example.py   # Template for config.py
├── db.py               # SQLite database layer
├── handlers.py         # Command routing & message handlers
├── llm.py              # Anthropic Haiku integration for freeform parsing
├── morning.py          # Morning briefing builder
├── tg.py               # Telegram API wrapper
├── scripts/
│   ├── setup_webhook.py  # One-time webhook registration
│   └── deploy.sh         # Git pull + reload + webhook re-register
├── requirements.txt    # Python dependencies
├── SETUP.md            # This file
└── tests/              # Test suite (152 tests)
    ├── conftest.py     # Shared test base class
    ├── test_app.py     # Flask endpoint tests
    ├── test_date_parsing.py  # Date parsing tests
    ├── test_db.py      # Database operation tests
    ├── test_handlers.py      # Message routing tests
    ├── test_llm.py     # LLM integration tests (mocked, zero cost)
    └── test_telegram.py      # Telegram API wrapper tests
```
