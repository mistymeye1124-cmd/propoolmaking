#!/usr/bin/env bash
# ==============================================================================
# Telegram Poll Bot - 1-Click Auto Run Installer (VPS)
# এই স্ক্রিপ্টটি VPS রিবুট হলেও বট নিজে নিজে চালু হওয়া (Auto-start on boot)
# এবং ক্র্যাশ করলে নিজে নিজে রিস্টার্ট হওয়ার সম্পূর্ণ সিস্টেম অটো সেটআপ করবে।
# ==============================================================================

set -e

# রুট পারমিশন চেক
if [ "$EUID" -ne 0 ]; then
  echo "❌ অনুগ্রহ করে স্ক্রিপ্টটি sudo দিয়ে রান করুন: sudo bash setup_autorun.sh"
  exit 1
fi

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

RUN_USER="${SUDO_USER:-root}"

echo ""
echo "==============================================================="
echo "🤖 Telegram Poll Bot - অটো-রান (Auto-Run) সেটআপ শুরু হচ্ছে..."
echo "📂 ফোল্ডার: $APP_DIR"
echo "👤 ইউজার: $RUN_USER"
echo "==============================================================="
echo ""

# ১. সিস্টেম প্যাকেজ ইনস্টলেশন
echo "📦 [১/৫] পাইথন এবং প্রয়োজনীয় প্যাকেজ ইনস্টল হচ্ছে..."
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl

# ২. ফাইল ও পারমিশন নিশ্চিতকরণ
echo "📄 [২/৫] ডাটাবেজ ও লগ ফাইল প্রস্তুত করা হচ্ছে..."
touch "$APP_DIR/bot_database.sqlite3"
touch "$APP_DIR/bot.log"
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR"

# ৩. ভার্চুয়াল এনভায়রনমেন্ট ও ডিপেন্ডেন্সি ইনস্টলেশন
echo "⚙️  [৩/৫] পাইথন ভার্চুয়াল এনভায়রনমেন্ট এবং লাইব্রেরি ইনস্টল হচ্ছে..."
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip --quiet
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet

# ৪. .env কনফিগারেশন চেক
echo "🔐 [৪/৫] .env ফাইল চেক করা হচ্ছে..."
if [ ! -f "$APP_DIR/.env" ]; then
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        chown "$RUN_USER:$RUN_USER" "$APP_DIR/.env"
    fi
    echo ""
    echo "⚠️  .env ফাইল পাওয়া যায়নি, নতুন তৈরি করা হয়েছে।"
    echo "👉 এখনই আপনার BOT_TOKEN ও ADMIN_ID বসাতে নিচের কমান্ডটি দিন:"
    echo "   nano $APP_DIR/.env"
    echo ""
fi

# ৫. ডাইনামিক Systemd সার্ভিস তৈরি (Auto-start on Boot + Auto-restart on Crash)
echo "🚀 [৫/৫] Systemd Auto-Run সার্ভিস কনফিগার করা হচ্ছে..."

SERVICE_FILE="/etc/systemd/system/telegram-bot.service"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Telegram Poll Bot (24/7 Auto-run & Auto-restart)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py

# ক্র্যাশ করলে ৩ সেকেন্ড পর অটো রিস্টার্ট হবে
Restart=always
RestartSec=3

# এনভায়রনমেন্ট ফাইল ও সেটিংস
EnvironmentFile=$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1

# লগ সেভ করার ডিরেক্টরি
StandardOutput=append:$APP_DIR/bot.log
StandardError=append:$APP_DIR/bot.log

KillMode=process
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
EOF

# Systemd রিলোড এবং অটো-স্টার্ট সক্রিয় করা
systemctl daemon-reload
systemctl enable telegram-bot
systemctl restart telegram-bot

echo ""
echo "==============================================================="
echo "🎉 দারুণ! আপনার বট সফলভাবে কনফিগার এবং চালু হয়েছে!"
echo "==============================================================="
echo ""
echo "✨ এই সেটআপে যা যা সুবিধা থাকবে:"
echo "   ১. 🔄 VPS বন্ধ হয়ে আবার চালু হলে (Reboot) বট একা একাই রান হবে।"
echo "   ২. 🛡️ বট কোনো কারণে ক্র্যাশ বা এরর দিলে ৩ সেকেন্ডে একা রিস্টার্ট হবে।"
echo "   ৩. 💻 টার্মিনাল/পিসি বন্ধ করে দিলেও বট ব্যাকগ্রাউন্ডে সবসময় চলবে।"
echo ""
echo "📌 প্রয়োজনীয় কমান্ডসমূহ:"
echo "   - বটের অবস্থা দেখতে : sudo systemctl status telegram-bot"
echo "   - লাইভ লগ দেখতে     : tail -f bot.log"
echo "   - বট বন্ধ করতে      : sudo systemctl stop telegram-bot"
echo "   - বট রিস্টার্ট করতে  : sudo systemctl restart telegram-bot"
echo "==============================================================="
echo ""

# বটের বর্তমান অবস্থা দেখান
sleep 2
systemctl status telegram-bot --no-pager || true
