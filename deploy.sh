#!/usr/bin/env bash
# ==============================================================================
# Telegram Poll Bot - VPS Helper Script
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh [setup | start | stop | restart | logs | update]
# ==============================================================================

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

check_env() {
    if [ ! -f "$APP_DIR/.env" ]; then
        echo "⚠️  .env file not found!"
        if [ -f "$APP_DIR/.env.example" ]; then
            echo "📋 Copying .env.example to .env..."
            cp "$APP_DIR/.env.example" "$APP_DIR/.env"
            echo "❗ Please edit .env now and put your actual BOT_TOKEN: nano .env"
        fi
        exit 1
    fi
}

ensure_files() {
    # Ensure database & log files exist before starting
    touch "$APP_DIR/bot_database.sqlite3"
    touch "$APP_DIR/bot.log"
}

case "$1" in
    setup)
        echo "🚀 [1/4] Updating system packages..."
        sudo apt update && sudo apt install -y python3 python3-pip python3-venv git

        echo "📦 [2/4] Creating Python virtual environment..."
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi

        echo "📥 [3/4] Installing Python dependencies..."
        ./venv/bin/pip install --upgrade pip
        ./venv/bin/pip install -r requirements.txt

        echo "📄 [4/4] Ensuring runtime files exist..."
        ensure_files
        check_env

        echo "✅ Setup completed successfully!"
        echo "👉 Now configure your .env file: nano .env"
        ;;

    start)
        ensure_files
        check_env
        if systemctl is-active --quiet telegram-bot 2>/dev/null; then
            echo "ℹ️  Bot is already running via systemd."
        elif command -v docker >/dev/null 2>&1 && docker compose ps --services --filter "status=running" 2>/dev/null | grep -q "telegram-poll-bot"; then
            echo "ℹ️  Bot is already running via Docker."
        else
            echo "🚀 Starting bot with systemd..."
            sudo systemctl start telegram-bot 2>/dev/null || (
                echo "Systemd service not active, starting directly in background..."
                nohup ./venv/bin/python main.py >> bot.log 2>&1 &
                echo "✅ Bot started in background! PID: $!"
            )
        fi
        ;;

    stop)
        echo "🛑 Stopping bot..."
        sudo systemctl stop telegram-bot 2>/dev/null || true
        pkill -f "python main.py" 2>/dev/null || true
        if command -v docker >/dev/null 2>&1; then
            docker compose down 2>/dev/null || true
        fi
        echo "✅ Bot stopped."
        ;;

    restart)
        echo "🔄 Restarting bot..."
        if sudo systemctl is-active --quiet telegram-bot 2>/dev/null; then
            sudo systemctl restart telegram-bot
            echo "✅ Restarted via systemd."
        elif command -v docker >/dev/null 2>&1 && docker compose ps -q 2>/dev/null | grep -q .; then
            docker compose restart
            echo "✅ Restarted via Docker."
        else
            pkill -f "python main.py" 2>/dev/null || true
            nohup ./venv/bin/python main.py >> bot.log 2>&1 &
            echo "✅ Bot restarted in background!"
        fi
        ;;

    logs)
        echo "📜 Showing live logs (Press Ctrl+C to exit)..."
        if [ -f "$APP_DIR/bot.log" ]; then
            tail -f -n 50 "$APP_DIR/bot.log"
        else
            journalctl -u telegram-bot -f -n 50
        fi
        ;;

    update)
        echo "⬇️  Pulling latest changes from Git..."
        git pull

        echo "📦 Updating dependencies..."
        if [ -d "venv" ]; then
            ./venv/bin/pip install -r requirements.txt
        fi

        echo "🔄 Restarting service..."
        if sudo systemctl is-active --quiet telegram-bot 2>/dev/null; then
            sudo systemctl restart telegram-bot
        elif command -v docker >/dev/null 2>&1 && docker compose ps -q 2>/dev/null | grep -q .; then
            docker compose down && docker compose up -d --build
        fi
        echo "✅ Bot updated and restarted successfully!"
        ;;

    *)
        echo "Telegram Poll Bot - Helper Commands:"
        echo "  ./deploy.sh setup    - Install packages, venv and requirements"
        echo "  ./deploy.sh start    - Start the bot"
        echo "  ./deploy.sh stop     - Stop the bot"
        echo "  ./deploy.sh restart  - Restart the bot"
        echo "  ./deploy.sh logs     - Follow real-time log output"
        echo "  ./deploy.sh update   - Pull latest git commits and restart"
        ;;
esac
