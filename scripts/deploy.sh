#!/bin/bash
cd ~/personal-bot
echo "Pulling latest..."
git pull
echo "Reloading web app..."
touch /var/www/sorchanolan_pythonanywhere_com_wsgi.py
sleep 2
echo "Re-registering webhook..."
python scripts/setup_webhook.py
echo "Done!"
