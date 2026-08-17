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

Edit `config.py` and set:

```python
BOT_TOKEN = "your-token-from-botfather"
WEBHOOK_URL = "https://YOUR-USERNAME.pythonanywhere.com/webhook"
```

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
python setup_webhook.py
```

You should see `"ok": true`.

## 6. Test it

Open Telegram, find your bot, and send `/start`. You should get a welcome message back.

**Important:** The first message you send will show your **chat ID** in the PythonAnywhere error log (Web tab → Error log). Copy it and set `CHAT_ID` in `config.py` — the morning briefing needs this.

Actually, an easier way: after sending `/start`, go to `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser. Your chat ID will be in the response under `message.chat.id`.

## 7. Set up scheduled messages (free, using cron-job.org)

PythonAnywhere's free tier doesn't include cron jobs, so we use an external service to poke the app on a schedule. This is free and unlimited.

1. Set your `CHAT_ID` in `config.py` (see step 6)
2. Make sure `CRON_SECRET` is set in `config.py` (see step 3)
3. Reload the web app on PythonAnywhere
4. Go to [cron-job.org](https://cron-job.org) and create a free account
5. Create a new cron job for each trigger you want:

**Morning briefing** (e.g., 8:00 AM your time):
- URL: `https://YOUR-USERNAME.pythonanywhere.com/trigger/morning?key=YOUR_CRON_SECRET`
- Schedule: `0 8 * * *` (daily at 8am — adjust timezone in cron-job.org settings)

**Evening check-in** (e.g., 9:00 PM your time):
- URL: `https://YOUR-USERNAME.pythonanywhere.com/trigger/evening?key=YOUR_CRON_SECRET`
- Schedule: `0 21 * * *`

**Weekly stale items review** (e.g., Sunday 10:00 AM):
- URL: `https://YOUR-USERNAME.pythonanywhere.com/trigger/stale?key=YOUR_CRON_SECRET`
- Schedule: `0 10 * * 0`

You can add as many triggers as you like — just add a new route in `app.py` and a new cron job in cron-job.org.

## Quick reference

| Command | What it does |
|---------|-------------|
| `/newlist groceries` | Create a list |
| `/groceries oat milk` | Add an item |
| `/groceries bread due:tomorrow` | Add with due date |
| `/groceries` | View the list |
| `/done groceries 2` | Mark item 2 done |
| `/undo groceries 1` | Restore most recent done item |
| `/clear groceries` | Remove completed items |
| `/lists` | Show all lists |
| `/all` | Everything pending |
| `/briefing` | Morning briefing on demand |
| `/deletelist groceries` | Delete a list |
| `/rename groceries food` | Rename a list |
