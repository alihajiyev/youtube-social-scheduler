#!/bin/bash
# DigitalOcean VPS Setup Script
# Run: bash setup_vps.sh

set -e

echo "=== Updating system ==="
sudo apt update && sudo apt upgrade -y

echo "=== Installing Python 3.11, pip, venv, git, nodejs ==="
sudo apt install -y python3.11 python3.11-venv python3-pip git curl

echo "=== Installing yt-dlp ==="
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

echo "=== Creating project directory ==="
mkdir -p ~/youtube-bot && cd ~/youtube-bot

echo "=== Cloning repo ==="
git clone https://github.com/alihajiyev/youtube-social-scheduler.git .

echo "=== Setting up Python venv ==="
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

echo ""
echo "=== SETUP COMPLETE ==="
echo ""
echo "Now create .env file manually:"
echo "  nano ~/youtube-bot/.env"
echo ""
echo "Copy the content from your local .env file"
echo "Then start the bot:"
echo "  cd ~/youtube-bot"
echo "  source venv/bin/activate"
echo "  python main.py"
