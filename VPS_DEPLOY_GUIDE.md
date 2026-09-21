# 🚀 Telegram Poll Bot - VPS Deployment Guide (ভিপিএস ডিপ্লয়মেন্ট গাইড)

এই গাইডটিতে আপনার টেলিগ্রাম পোল বটটি নিরাপদে গিটহাবে পুশ করা এবং লিনাক্স ভিপিএস (Ubuntu / Debian)-এ ২৪/৭ চালু রাখার পুরো প্রসেস ধাপে ধাপে বুঝিয়ে দেওয়া হলো।

---

## 📌 সূচিপত্র
1. [গিট এবং গিটহাব সেটআপ (Local Machine)](#-ধাপ-১-গিট-ও-গিটহাব-সেটআপ-local-machine)
2. [ভিপিএস-এ প্রাথমিক প্রস্তুতি (VPS Initial Setup)](#-ধাপ-২-ভিপিএস-এ-প্রাথমিক-প্রস্তুতি-vps-preparation)
3. [পদ্ধতি ১: ডকার ডিপ্লয়মেন্ট (সবচেয়ে সহজ ও রিকমেন্ডেড)](#-পদ্ধতি-১-docker-দিয়ে-ডিপ্লয়-রিকমেন্ডেড)
4. [পদ্ধতি ২: Systemd Service ডিপ্লয়মেন্ট (ল্যাটেস্ট সরাসরি পাইথন)](#-পদ্ধতি-২-systemd-service-দিয়ে-সরাসরি-লিনাক্স-সার্ভিস)
5. [ভবিষ্যতে কোড আপডেট করার নিয়ম](#-ভবিষ্যতে-কোড-আপডেট-করার-নিয়ম)
6. [জরুরি কমান্ড ও লগ চেক](#-জরুরি-কমান্ড-ও-লগ-চেক)

---

## 🛡️ নিরাপত্তা নিশ্চিতকরণ (.gitignore)
আপনার প্রোজেক্টে `.gitignore` ফাইলটি এমনভাবে সেট করা হয়েছে যাতে:
- আপনার আসল বটের টোকেন এবং এডমিন আইডি থাকা `.env` ফাইল **কখনোই গিটহাবে যাবে না**।
- আপনার লোকাল ডাটাবেজ (`*.sqlite3`, `*.db`) গিটহাবে যাবে না, ফলে প্রোডাকশনের ডাটা নিরাপদ থাকবে।
- সব অপ্রয়োজনীয় ক্যাশ (`__pycache__`), লগ (`bot.log`), এবং ভার্চুয়াল এনভায়রনমেন্ট (`venv/`) গিট ট্র্যাক করবে না।

---

## 💻 ধাপ ১: গিট ও গিটহাব সেটআপ (Local Machine)

আপনার পিসির টার্মিনাল/পাওয়ারশেলে প্রোজেক্টের ফোল্ডারে গিয়ে নিচের কমান্ডগুলো এক এক করে রান করুন:

```bash
# ১. গিট রিপোজিটরি শুরু করুন
git init

# ২. ফাইলগুলো স্টেজিং-এ যোগ করুন (.env এবং ডাটাবেজ বাদ দিয়ে বাকি ফাইলগুলো যোগ হবে)
git add .

# ৩. প্রথম কমিট করুন
git commit -m "Initial commit: Ready for VPS deployment"

# ৪. মেইন ব্রাঞ্চ সিলেক্ট করুন
git branch -M main

# ৫. আপনার GitHub Private Repo লিঙ্ক যোগ করুন (GitHub-এ আগে একটি Private Repo বানিয়ে নিন)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# ৬. গিটহাবে পুশ করুন
git push -u origin main
```

> ⚠️ **গুরুত্বপূর্ণ:** GitHub-এ রিপোজিটরি তৈরি করার সময় অবশ্যই **Private** রাখবেন।

---

## 🌐 ধাপ ২: ভিপিএস-এ প্রাথমিক প্রস্তুতি (VPS Preparation)

আপনার পিসি বা টার্মিনাল থেকে SSH দিয়ে ভিপিএস-এ কানেক্ট করুন:
```bash
ssh root@YOUR_VPS_IP
```

ভিপিএস আপডেট করে নিন:
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl nano
```

প্রোজেক্টটি ভিপিএস-এ ক্লোন করুন:
```bash
# ডিরেক্টরিতে যান
cd /var/www || cd /root

# আপনার গিটহাব থেকে ক্লোন করুন
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git telegram-poll-bot

# প্রোজেক্ট ফোল্ডারে ঢুকুন
cd telegram-poll-bot
```

### পরিবেশের ভ্যারিয়েবল (.env) তৈরি করুন:
```bash
# .env.example থেকে .env তৈরি করুন
cp .env.example .env

# .env ফাইলটি এডিট করুন
nano .env
```
`nano` এডিটরে আপনার আসল `BOT_TOKEN` এবং `ADMIN_IDS` বসিয়ে `Ctrl + O`, `Enter` এবং তারপর `Ctrl + X` চেপে সেভ করুন।

---

## 🐳 পদ্ধতি ১: Docker দিয়ে ডিপ্লয় (রিকমেন্ডেড)

Docker ব্যবহার করলে ভিপিএস-এ পাইথন ভার্সন নিয়ে কোনো ঝামেলা হয় না এবং ব্যাকগ্রাউন্ডে বট ক্র্যাশ ছাড়াই স্মুথলি চলে।

### ১. Docker ও Docker Compose ইনস্টল করুন (যদি না থাকে):
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
```

### ২. ডাটাবেজ ও লগ ফাইল প্রি-ক্রিয়েট করুন:
```bash
touch bot_database.sqlite3 bot.log
```

### ৩. বট চালু করুন (এক কমান্ডে):
```bash
docker compose up -d --build
```

### ৪. স্টেটাস এবং লাইভ লগ দেখুন:
```bash
# বট ঠিকঠাক চালু হয়েছে কিনা লগ দেখুন
docker compose logs -f

# বট বন্ধ করতে চাইলে:
docker compose down

# বট রিস্টার্ট করতে চাইলে:
docker compose restart
```

---

## ⚙️ পদ্ধতি ২: Systemd Service দিয়ে সরাসরি লিনাক্স সার্ভিস

যদি আপনি ডকার ছাড়া সরাসরি পাইথনে চালাতে চান এবং ভিপিএস রিবুট হলেও বট নিজে নিজে চালু হতে দিতে চান:

### ১. ডিপ্লয়মেন্ট হেল্পার দিয়ে পরিবেশ তৈরি করুন:
```bash
chmod +x deploy.sh
./deploy.sh setup
```

### ২. Systemd সার্ভিস ফাইল সেট করুন:
```bash
# সার্ভিস ফাইলটি সিস্টেম ফোল্ডারে কপি করুন
sudo cp telegram-bot.service /etc/systemd/system/telegram-bot.service

# যদি আপনার প্রোজেক্ট পাথ /var/www/telegram-poll-bot না হয়ে অন্য কিছু হয়, তবে পাথ এডিট করুন:
# sudo nano /etc/systemd/system/telegram-bot.service

# Systemd রিলোড করুন
sudo systemctl daemon-reload

# সার্ভিস এনাবল এবং স্টার্ট করুন (যাতে VPS রিস্টার্ট হলেও বট নিজে থেকে চালু হয়)
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot
```

### ৩. সার্ভিস স্টেটাস ও লগ চেক করুন:
```bash
# স্টেটাস দেখতে:
sudo systemctl status telegram-bot

# লাইভ লগ দেখতে:
journalctl -u telegram-bot -f -n 50
# অথবা
tail -f bot.log
```

---

## 🔄 ভবিষ্যতে কোড আপডেট করার নিয়ম

যখনই আপনি লোকাল পিসি থেকে কোড পরিবর্তন করে GitHub-এ পুশ করবেন, ভিপিএস-এ এসে আপডেট করার উপায়:

### ডকার ব্যবহার করলে:
```bash
cd /var/www/telegram-poll-bot
git pull
docker compose up -d --build
```

### Systemd ব্যবহার করলে:
```bash
cd /var/www/telegram-poll-bot
./deploy.sh update
```
*(এটি স্বয়ংক্রিয়ভাবে গিট থেকে কোড টানবে, নতুন লাইব্রেরি ইনস্টল করবে এবং বট রিস্টার্ট করবে)*

---

## 🛠️ জরুরি কমান্ড ও লগ চেক

| কাজের বিবরণ | ডকার কমান্ড | Systemd কমান্ড |
| :--- | :--- | :--- |
| **বট চালু করা** | `docker compose up -d` | `sudo systemctl start telegram-bot` |
| **বট বন্ধ করা** | `docker compose down` | `sudo systemctl stop telegram-bot` |
| **বট রিস্টার্ট করা** | `docker compose restart` | `sudo systemctl restart telegram-bot` |
| **লাইভ লগ দেখা** | `docker compose logs -f` | `tail -f bot.log` বা `journalctl -u telegram-bot -f` |
| **বটের অবস্থা দেখা** | `docker compose ps` | `sudo systemctl status telegram-bot` |

---

## ❓ সাধারণ সমস্যা সমাধান (Troubleshooting)

1. **বট চালু হয়েই বন্ধ হয়ে যাচ্ছে:**
   - `.env` ফাইলটি চেক করুন। `BOT_TOKEN` ঠিকভাবে দেওয়া হয়েছে কিনা নিশ্চিত হোন (`cat .env`)।
   - লগ ফাইল চেক করুন: `tail -n 50 bot.log`।
2. **ডাটাবেজ পারমিশন সমস্যা:**
   - ফাইল পারমিশন ঠিক করতে ভিপিএস-এ রান করুন:
     ```bash
     chmod 664 bot_database.sqlite3
     ```
3. **টাইমজোন সমস্যা:**
   - ডকার ফাইলে ডিফল্ট হিসেবে `Asia/Dhaka` সেট করা আছে। আপনি চাইলে ডকার ফাইল বা সার্ভারে আপনার পছন্দমতো টাইমজোন সেট করতে পারেন।
