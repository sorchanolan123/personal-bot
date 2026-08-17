#!/usr/bin/env python3
"""One-time script to register your webhook URL with Telegram."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import WEBHOOK_URL
from telegram import set_webhook, get_webhook_info


def main():
    if not WEBHOOK_URL:
        print("Error: Set WEBHOOK_URL in config.py first.")
        print("It should be: https://<your-username>.pythonanywhere.com/webhook")
        sys.exit(1)

    print(f"Setting webhook to: {WEBHOOK_URL}")
    result = set_webhook(WEBHOOK_URL)
    print(f"Result: {result}")

    print("\nCurrent webhook info:")
    info = get_webhook_info()
    print(info)


if __name__ == "__main__":
    main()
