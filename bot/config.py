import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Parse admin IDs as a set of integers
admin_ids_str = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = set()
if admin_ids_str:
    for aid in admin_ids_str.split(","):
        aid = aid.strip()
        if aid.isdigit():
            ADMIN_IDS.add(int(aid))

# Super Admin / Bot Owner Telegram User IDs (exclusive access to mass broadcast, network, stats, brand credit)
super_admin_ids_str = os.getenv("SUPER_ADMIN_IDS", "").strip()
SUPER_ADMIN_IDS = set()
if super_admin_ids_str:
    for aid in super_admin_ids_str.split(","):
        aid = aid.strip()
        if aid.isdigit():
            SUPER_ADMIN_IDS.add(int(aid))
else:
    SUPER_ADMIN_IDS = {8370293945, 7751516916, 5319231239}

GLOBAL_FORCE_CHANNEL = os.getenv("GLOBAL_FORCE_CHANNEL", "").strip()
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "bot_database.sqlite3").strip()
