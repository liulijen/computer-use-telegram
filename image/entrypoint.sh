#!/bin/bash
set -e

./start_all.sh
./novnc_startup.sh

# Run telegram bot and pipe output directly to echo for real-time logging
python -m computer_use_demo.telegram_bot 2>&1 | while read -r line; do echo "[Telegram Bot] $line"; done &

echo "✨ Computer Use Demo is ready!"
echo "➡️  The Telegram bot is now running"

# Keep the container running
tail -f /dev/null
