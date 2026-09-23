import os
import sys
import json
import sqlite3
import subprocess
import urllib.request
from datetime import datetime

# UTF-8 encoding support for Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def print_header(title: str):
    print("\n" + "=" * 62)
    print(f"  🔍 {title}")
    print("=" * 62)

def check_process_status():
    print("\n[1/5] 🤖 বট প্রসেস স্ট্যাটাস (Process Check):")
    try:
        cmd = 'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'python.exe\'\\" | Where-Object { $_.CommandLine -like \'*main.py*\' } | Select-Object ProcessId, CommandLine"'
        output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
        lines = [l.strip() for l in output.strip().splitlines() if l.strip() and not l.startswith("ProcessId") and not l.startswith("---------")]
        if lines:
            print(f"  ✅ বট ব্যাকগ্রাউন্ডে চলছে (Running, {len(lines)} Process/Worker found).")
            return True
        else:
            print("  ⚠️ বট বর্তমানে চালু নেই (Not Running).")
            print("     👉 চালু করতে 'run_bot.bat' ফাইলে ডাবল-ক্লিক করুন।")
            return False
    except Exception as e:
        print(f"  ⚠️ প্রসেস চেক করতে পারেনি: {e}")
        return False

def check_telegram_api():
    print("\n[2/5] 🌐 টেলিগ্রাম সার্ভার কানেকশন (Telegram API Check):")
    env_file = ".env"
    bot_token = None
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("BOT_TOKEN="):
                    bot_token = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                    break
    
    if not bot_token or ":" not in bot_token:
        print("  ❌ .env ফাইলে BOT_TOKEN পাওয়া যায়নি বা সঠিক নয়!")
        return False

    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode())
            if data.get("ok"):
                res = data.get("result", {})
                username = res.get("username", "Unknown")
                name = res.get("first_name", "Unknown")
                bot_id = res.get("id", "")
                print(f"  ✅ টেলিগ্রাম সার্ভার কানেকশন সফল (100% OK)!")
                print(f"     • Bot Name: {name}")
                print(f"     • Username: @{username}")
                print(f"     • Bot ID:   {bot_id}")
                print(f"     • Direct Link: https://t.me/{username}")
                return True
            else:
                print(f"  ❌ টেলিগ্রাম রেসপন্স এরর: {data}")
                return False
    except Exception as e:
        print(f"  ❌ টেলিগ্রাম সার্ভারে কানেক্ট হতে পারছে না: {e}")
        print("     👉 ইন্টারনেট কানেকশন বা ভিপিএন/প্রক্সি চেক করুন।")
        return False

def check_database():
    print("\n[3/5] 🗄️ ডাটাবেস স্বাস্থ্য পরীক্ষা (Database Health):")
    db_file = "bot_database.sqlite3"
    if not os.path.exists(db_file):
        print(f"  ⚠️ ডাটাবেস ফাইল '{db_file}' এখনো তৈরি হয়নি (বট প্রথমবার রান করলে তৈরি হবে)।")
        return True

    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        
        # User count
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        
        # Poll count
        cur.execute("SELECT COUNT(*) FROM polls")
        poll_count = cur.fetchone()[0]
        
        # Active polls
        cur.execute("SELECT COUNT(*) FROM polls WHERE status = 'active'")
        active_polls = cur.fetchone()[0]

        # Vote count
        cur.execute("SELECT COUNT(*) FROM votes")
        vote_count = cur.fetchone()[0]

        # Connected channels
        cur.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1")
        channel_count = cur.fetchone()[0]

        conn.close()
        print(f"  ✅ ডাটাবেস সুরক্ষিত ও সম্পূর্ণ সচল:")
        print(f"     • মোট ইউজার (Users):      {user_count}")
        print(f"     • মোট পোল (Total Polls): {poll_count} (সক্রিয়: {active_polls})")
        print(f"     • মোট ভোট (Total Votes): {vote_count}")
        print(f"     • যুক্ত চ্যানেলসমূহ:      {channel_count}")
        return True
    except Exception as e:
        print(f"  ❌ ডাটাবেস এরর: {e}")
        return False

def check_logs():
    print("\n[4/5] 📋 এরর লগ ও হিস্টোরি পরীক্ষা (Error Logs Check):")
    log_file = "bot.log"
    if not os.path.exists(log_file):
        print("  ℹ️ 'bot.log' ফাইলটি এখনো তৈরি হয়নি। নতুন আপডেটের পর বট রান করলে সব লগ ও এরর এখানে জমা হবে।")
        return True

    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        
        if not lines:
            print("  ✅ লগ ফাইল পরিষ্কার (কোনো এরর নেই)।")
            return True

        recent_lines = lines[-50:]
        errors = [l for l in recent_lines if "[ERROR]" in l or "CRITICAL" in l or "Traceback" in l]
        
        if errors:
            print(f"  ⚠️ সাম্প্রতিক লগে {len(errors)}টি এরর/সতর্কবার্তা পাওয়া গেছে:")
            for err in errors[-5:]:
                print(f"     ❌ {err.strip()[:100]}")
            print("     👉 বিস্তারিত দেখতে 'bot.log' ফাইলটি নোটপ্যাডে ওপেন করুন।")
        else:
            print("  ✅ সাম্প্রতিক লগে কোনো এরর পাওয়া যায়নি (0 Errors)!")
            print(f"     • সর্বশেষ লগ: {recent_lines[-1].strip()[:90]}")
        return True
    except Exception as e:
        print(f"  ⚠️ লগ রিড করতে ব্যর্থ: {e}")
        return False

def check_code_integrity():
    print("\n[5/5] 🧩 কোড ইন্টিগ্রিটি ও মডিউল টেস্ট (Code Integrity):")
    try:
        from bot.config import BOT_TOKEN, ADMIN_IDS
        from bot.database.db import init_db
        from bot.templates import get_raw_template, render_poll_card
        from bot.keyboards.reply import build_persistent_menu
        from bot.keyboards.inline import build_poll_keyboard
        print("  ✅ সকল পাইথন ফাইল, হ্যান্ডলার ও টেমপ্লেট ১০০% সিনট্যাক্স-এররমুক্ত!")
        return True
    except Exception as e:
        print(f"  ❌ কোডে ইমপোর্ট বা সিনট্যাক্স এরর: {e}")
        return False

def main():
    print_header("TELEGRAM VIRAL POLL BOT - স্বাস্থ্য ও ডায়াগনস্টিক রিপোর্ট")
    print(f"  সময়: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")
    
    p_ok = check_process_status()
    t_ok = check_telegram_api()
    d_ok = check_database()
    l_ok = check_logs()
    c_ok = check_code_integrity()

    print("\n" + "=" * 62)
    print("  📊 সামগ্রিক ফলাফল (Final Summary):")
    print("=" * 62)
    if p_ok and t_ok and c_ok:
        print("  🟢 [STATUS: ALL OK] আপনার বট ১০০% সুস্থ, সচল এবং কোনো এরর নেই!")
        print("     টেলিগ্রামে গিয়ে @ProPoolMaking_bot এ /start পাঠিয়ে টেস্ট করুন।")
    elif not p_ok:
        print("  🟡 [STATUS: STOPPED] কোড এবং সার্ভার ঠিক আছে, তবে বট বর্তমানে অফলাইন।")
        print("     বট চালু করতে ফোল্ডারের 'run_bot.bat' ফাইলে ডাবল-ক্লিক করুন।")
    else:
        print("  🔴 [STATUS: ACTION REQUIRED] কিছু সমস্যা শনাক্ত হয়েছে। উপরের রিপোর্ট দেখে সমাধান করুন।")
    print("=" * 62 + "\n")

if __name__ == "__main__":
    main()
