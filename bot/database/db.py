import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Tuple
from bot.config import DATABASE_PATH, ADMIN_IDS

@asynccontextmanager
async def get_db():
    conn = await aiosqlite.connect(DATABASE_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        await conn.close()

async def init_db():
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'bn',
                preferred_icon_style TEXT DEFAULT 'dynamic',
                custom_brand_name TEXT DEFAULT '',
                custom_brand_url TEXT DEFAULT '',
                custom_brand_btn TEXT DEFAULT '',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                username TEXT,
                added_by INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                poll_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                target_chat_id INTEGER NOT NULL,
                target_chat_title TEXT,
                target_chat_username TEXT,
                channel_message_id INTEGER,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                ends_at TIMESTAMP,
                parent_poll_id INTEGER,
                part_number INTEGER DEFAULT 1,
                winner_count INTEGER DEFAULT 1,
                icon_style TEXT DEFAULT 'dynamic',
                language TEXT DEFAULT 'bn'
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                votes_count INTEGER DEFAULT 0,
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id) ON DELETE CASCADE
            );
        """)

        # Migrations for existing tables if columns do not exist
        migrations = [
            ("users", "language", "TEXT DEFAULT 'bn'"),
            ("users", "preferred_icon_style", "TEXT DEFAULT 'dynamic'"),
            ("users", "custom_brand_name", "TEXT DEFAULT ''"),
            ("users", "custom_brand_url", "TEXT DEFAULT ''"),
            ("users", "custom_brand_btn", "TEXT DEFAULT ''"),
            ("polls", "ends_at", "TIMESTAMP"),
            ("polls", "parent_poll_id", "INTEGER"),
            ("polls", "part_number", "INTEGER DEFAULT 1"),
            ("polls", "winner_count", "INTEGER DEFAULT 1"),
            ("polls", "icon_style", "TEXT DEFAULT 'dynamic'"),
            ("polls", "language", "TEXT DEFAULT 'bn'"),
            ("polls", "contact_username", "TEXT DEFAULT ''"),
            ("users", "default_contact", "TEXT DEFAULT ''"),
        ]
        for table, col, col_def in migrations:
            try:
                await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def};")
                await db.commit()
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                candidate_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(poll_id, user_id),
                FOREIGN KEY (poll_id) REFERENCES polls(poll_id) ON DELETE CASCADE,
                FOREIGN KEY (candidate_id) REFERENCES candidates(candidate_id) ON DELETE CASCADE
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_channel_permissions (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, chat_id)
            );
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_saved_emojis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                emoji_id TEXT NOT NULL,
                name TEXT DEFAULT '',
                fallback_char TEXT DEFAULT '✨',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, emoji_id)
            );
        """)

        # Default Super Admin Brand Credit: @ProPoolMaking_bot
        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('custom_credit_name', '@ProPoolMaking_bot');
        """)
        await db.execute("""
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('custom_credit_url', 'https://t.me/ProPoolMaking_bot');
        """)

        await db.commit()

# --- User operations ---
async def save_user(user_id: int, username: Optional[str] = None, first_name: str = "", last_name: Optional[str] = None):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name;
        """, (user_id, username, first_name, last_name))
        await db.commit()

async def get_total_users() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def get_user_language(user_id: int) -> str:
    async with get_db() as db:
        async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row["language"] if (row and row["language"]) else "bn"

async def set_user_language(user_id: int, lang: str):
    async with get_db() as db:
        await db.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
        await db.commit()

async def get_all_user_ids() -> List[int]:
    async with get_db() as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# --- Channel operations ---
async def save_channel(chat_id: int, title: str, username: Optional[str], added_by: Optional[int] = None):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO channels (chat_id, title, username, added_by, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                username = excluded.username,
                added_by = COALESCE(channels.added_by, excluded.added_by),
                is_active = 1;
        """, (chat_id, title, username, added_by))
        if added_by:
            await db.execute("""
                INSERT OR IGNORE INTO user_channel_permissions (user_id, chat_id)
                VALUES (?, ?)
            """, (added_by, chat_id))
        await db.commit()

async def record_user_channel_access(user_id: int, chat_id: int):
    async with get_db() as db:
        await db.execute("""
            INSERT OR IGNORE INTO user_channel_permissions (user_id, chat_id)
            VALUES (?, ?)
        """, (user_id, chat_id))
        await db.commit()

async def remove_user_channel_permission(user_id: int, chat_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM user_channel_permissions WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        await db.commit()

async def is_user_authorized_for_channel_db(user_id: int, chat_id: int) -> bool:
    """
    Check if user is authorized for channel in DB.
    Strict isolation: only returns True if user connected the channel or has explicit permission.
    Never bypasses for ADMIN_IDS so that users cannot publish to channels they do not administer.
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT 1 FROM user_channel_permissions WHERE user_id = ? AND chat_id = ?
            UNION
            SELECT 1 FROM channels WHERE chat_id = ? AND added_by = ?
        """, (user_id, chat_id, chat_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row is not None

async def deactivate_channel(chat_id: int):
    async with get_db() as db:
        await db.execute("UPDATE channels SET is_active = 0 WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_all_active_channels() -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM channels WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_all_channels_with_status() -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM channels ORDER BY is_active DESC, created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_user_selectable_channels(user_id: int) -> List[Dict[str, Any]]:
    """
    Returns active channels connected by or authorized for this user.
    Every user (including Admin) ONLY sees channels they themselves added or are authorized for.
    Never exposes another user's channels.
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT DISTINCT c.* FROM channels c
            LEFT JOIN user_channel_permissions p ON c.chat_id = p.chat_id
            WHERE c.is_active = 1 AND (c.added_by = ? OR p.user_id = ?)
            ORDER BY c.created_at DESC
            LIMIT 15
        """, (user_id, user_id)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def get_channel(chat_id: int) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM channels WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def set_channel_status(chat_id: int, is_active: int):
    async with get_db() as db:
        await db.execute("UPDATE channels SET is_active = ? WHERE chat_id = ?", (is_active, chat_id))
        await db.commit()

async def delete_channel(chat_id: int):
    async with get_db() as db:
        await db.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        await db.commit()

async def get_user_all_channels(user_id: int) -> List[Dict[str, Any]]:
    """
    Returns all channels (both active and inactive) connected by or authorized for this user.
    Maintains strict user isolation: a user can only ever see their own channels.
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT DISTINCT c.* FROM channels c
            LEFT JOIN user_channel_permissions p ON c.chat_id = p.chat_id
            WHERE c.added_by = ? OR p.user_id = ?
            ORDER BY c.is_active DESC, c.created_at DESC
        """, (user_id, user_id)) as cursor:
            return [dict(r) for r in await cursor.fetchall()]

async def unlink_user_channel(user_id: int, chat_id: int):
    """
    Removes user's permission for a channel. If no other users are authorized,
    marks the channel inactive.
    """
    async with get_db() as db:
        await db.execute("DELETE FROM user_channel_permissions WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
        await db.execute("UPDATE channels SET added_by = NULL WHERE chat_id = ? AND added_by = ?", (chat_id, user_id))
        async with db.execute("SELECT COUNT(*) FROM user_channel_permissions WHERE chat_id = ?", (chat_id,)) as cur:
            row = await cur.fetchone()
            count = row[0] if row else 0
        if count == 0:
            await db.execute("UPDATE channels SET is_active = 0 WHERE chat_id = ?", (chat_id,))
        await db.commit()

# --- Custom Credit / Brand operations ---
async def get_custom_credit() -> Tuple[str, str]:
    name = await get_setting("custom_credit_name", "")
    url = await get_setting("custom_credit_url", "")
    if not name:
        name = "@ProPoolMaking_bot"
    if not url:
        url = "https://t.me/ProPoolMaking_bot"
    return name, url

async def set_custom_credit(name: str, url: str):
    await set_setting("custom_credit_name", name)
    await set_setting("custom_credit_url", url)

async def get_effective_credit(user_id: Optional[int] = None) -> Tuple[str, str, str]:
    """
    Returns (brand_name, brand_url, button_text).
    Exclusively returns the Super Admin's promotional credit settings across all polls.
    Defaults to @ProPoolMaking_bot and https://t.me/ProPoolMaking_bot.
    """
    g_name, g_url = await get_custom_credit()
    g_btn = await get_custom_credit_btn_text()
    name = g_name if g_name else "@ProPoolMaking_bot"
    url = g_url if g_url else "https://t.me/ProPoolMaking_bot"
    return (name, url, g_btn)

async def set_user_custom_credit(user_id: int, name: Optional[str] = None, url: Optional[str] = None, btn: Optional[str] = None, btn_text: Optional[str] = None):
    btn_val = btn if btn is not None else btn_text
    async with get_db() as db:
        if name is not None:
            await db.execute("UPDATE users SET custom_brand_name = ? WHERE user_id = ?", (name, user_id))
        if url is not None:
            await db.execute("UPDATE users SET custom_brand_url = ? WHERE user_id = ?", (url, user_id))
        if btn_val is not None:
            await db.execute("UPDATE users SET custom_brand_btn = ? WHERE user_id = ?", (btn_val, user_id))
        await db.commit()

# --- Poll operations ---
async def create_poll(creator_id: int, target_chat_id: int, target_chat_title: str,
                      target_chat_username: Optional[str], title: str, candidates: List[str],
                      ends_at: Optional[str] = None, created_at: Optional[str] = None,
                      parent_poll_id: Optional[int] = None, part_number: int = 1,
                      winner_count: int = 1, icon_style: str = "dynamic",
                      language: str = "bn", contact_username: Optional[str] = None) -> int:
    from datetime import datetime
    if not created_at:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    contact_clean = contact_username.strip().lstrip("@") if contact_username else ""
    async with get_db() as db:
        cursor = await db.execute("""
            INSERT INTO polls (creator_id, target_chat_id, target_chat_title, target_chat_username,
                               title, ends_at, created_at, parent_poll_id, part_number,
                               winner_count, icon_style, language, contact_username)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (creator_id, target_chat_id, target_chat_title, target_chat_username,
              title, ends_at, created_at, parent_poll_id, part_number,
              winner_count, icon_style, language, contact_clean))
        poll_id = cursor.lastrowid
        
        for cand in candidates:
            cand_name = cand.strip()
            if cand_name:
                await db.execute("""
                    INSERT INTO candidates (poll_id, name, votes_count)
                    VALUES (?, ?, 0)
                """, (poll_id, cand_name))
        
        await db.commit()
        return poll_id

async def add_candidates_to_poll(poll_id: int, candidate_names: List[str]) -> List[int]:
    """
    Appends new candidates to an existing live poll.
    Returns the list of newly created candidate IDs.
    """
    inserted_ids = []
    async with get_db() as db:
        for name in candidate_names:
            clean_name = name.strip()
            if clean_name:
                cursor = await db.execute("""
                    INSERT INTO candidates (poll_id, name, votes_count)
                    VALUES (?, ?, 0)
                """, (poll_id, clean_name))
                inserted_ids.append(cursor.lastrowid)
        await db.commit()
    return inserted_ids

async def update_poll_contact(poll_id: int, contact_username: str):
    contact_clean = contact_username.strip().lstrip("@") if contact_username else ""
    async with get_db() as db:
        await db.execute("UPDATE polls SET contact_username = ? WHERE poll_id = ?", (contact_clean, poll_id))
        await db.commit()

async def get_user_default_contact(user_id: int) -> str:
    async with get_db() as db:
        async with db.execute("SELECT default_contact, username FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                if row["default_contact"]:
                    return row["default_contact"]
                if row["username"]:
                    return row["username"]
            return ""

async def set_user_default_contact(user_id: int, contact: str):
    contact_clean = contact.strip().lstrip("@") if contact else ""
    async with get_db() as db:
        await db.execute("UPDATE users SET default_contact = ? WHERE user_id = ?", (contact_clean, user_id))
        await db.commit()

async def get_last_user_poll(creator_id: int) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("""
            SELECT * FROM polls 
            WHERE creator_id = ? 
            ORDER BY poll_id DESC LIMIT 1
        """, (creator_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_poll_parts(poll_id: int) -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT parent_poll_id FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
            row = await cursor.fetchone()
            root_id = (row["parent_poll_id"] if row and row["parent_poll_id"] else poll_id)

        async with db.execute("""
            SELECT * FROM polls 
            WHERE poll_id = ? OR parent_poll_id = ?
            ORDER BY part_number ASC, poll_id ASC
        """, (root_id, root_id)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_next_part_number(poll_id: int) -> int:
    async with get_db() as db:
        async with db.execute("SELECT parent_poll_id FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
            row = await cursor.fetchone()
            root_id = (row["parent_poll_id"] if row and row["parent_poll_id"] else poll_id)

        async with db.execute("""
            SELECT COUNT(*) FROM polls 
            WHERE poll_id = ? OR parent_poll_id = ?
        """, (root_id, root_id)) as cursor:
            row = await cursor.fetchone()
            count = row[0] if row else 1
            return count + 1

async def set_poll_message_id(poll_id: int, channel_message_id: int):
    async with get_db() as db:
        await db.execute("UPDATE polls SET channel_message_id = ? WHERE poll_id = ?", (channel_message_id, poll_id))
        await db.commit()

async def update_poll_title(poll_id: int, title: str):
    async with get_db() as db:
        await db.execute("UPDATE polls SET title = ? WHERE poll_id = ?", (title, poll_id))
        await db.commit()

async def get_poll(poll_id: int) -> Optional[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_expired_active_polls() -> List[Dict[str, Any]]:
    """
    Returns all active polls whose timer has expired.
    """
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        async with db.execute("""
            SELECT * FROM polls 
            WHERE status = 'active' AND ends_at IS NOT NULL AND datetime(ends_at) <= datetime(?)
        """, (now_str,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def get_candidates(poll_id: int) -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("SELECT * FROM candidates WHERE poll_id = ? ORDER BY candidate_id ASC", (poll_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def has_user_voted(poll_id: int, user_id: int) -> bool:
    if not user_id or user_id <= 0:
        return True
    async with get_db() as db:
        async with db.execute("SELECT parent_poll_id FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
            row = await cursor.fetchone()
            root_id = (row["parent_poll_id"] if row and row["parent_poll_id"] else poll_id)

        # Enforces 1 vote per user across all connected parts of the contest
        async with db.execute("""
            SELECT v.vote_id FROM votes v
            JOIN polls p ON v.poll_id = p.poll_id
            WHERE (p.poll_id = ? OR p.parent_poll_id = ?) AND v.user_id = ?
        """, (root_id, root_id, user_id)) as cursor:
            return await cursor.fetchone() is not None

async def cast_vote(poll_id: int, candidate_id: int, user_id: int) -> Tuple[bool, str]:
    if not user_id or user_id <= 0:
        return False, "INVALID_USER"

    async with get_db() as db:
        # 1. Check Poll Status & Expiration
        async with db.execute("SELECT status, ends_at, parent_poll_id FROM polls WHERE poll_id = ?", (poll_id,)) as cursor:
            poll = await cursor.fetchone()
            if not poll or poll["status"] != "active":
                return False, "POLL_CLOSED"
            if poll["ends_at"]:
                from datetime import datetime
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                async with db.execute("SELECT datetime(?) > datetime(?)", (now_str, poll["ends_at"])) as check_c:
                    row = await check_c.fetchone()
                    if row and row[0] == 1:
                        return False, "POLL_CLOSED"

        # 2. Strict Candidate Verification: Ensure candidate exists and belongs to this poll
        async with db.execute("SELECT candidate_id FROM candidates WHERE candidate_id = ? AND poll_id = ?", (candidate_id, poll_id)) as cursor:
            if await cursor.fetchone() is None:
                return False, "INVALID_CANDIDATE"

        # 3. Single Vote Rule: Ensure user has not voted in this poll or any connected part
        root_id = (poll["parent_poll_id"] if poll["parent_poll_id"] else poll_id)
        async with db.execute("""
            SELECT v.vote_id FROM votes v
            JOIN polls p ON v.poll_id = p.poll_id
            WHERE (p.poll_id = ? OR p.parent_poll_id = ?) AND v.user_id = ?
        """, (root_id, root_id, user_id)) as cursor:
            if await cursor.fetchone() is not None:
                return False, "ALREADY_VOTED"

        # 4. Atomic Database Insertion & Rollback Protection
        try:
            await db.execute("""
                INSERT INTO votes (poll_id, candidate_id, user_id)
                VALUES (?, ?, ?)
            """, (poll_id, candidate_id, user_id))

            await db.execute("""
                UPDATE candidates
                SET votes_count = votes_count + 1
                WHERE candidate_id = ? AND poll_id = ?
            """, (candidate_id, poll_id))

            await db.commit()
            return True, "VOTE_CAST"
        except Exception as e:
            await db.rollback()
            if "UNIQUE" in str(e) or "PRIMARY KEY" in str(e):
                return False, "ALREADY_VOTED"
            return False, str(e)

async def cleanup_expired_ended_polls(days: int = 2) -> int:
    """
    Auto-deletes polls that have been ended for more than `days` (default 2 days = 48 hours).
    Deletes related votes and candidates.
    """
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        async with db.execute("""
            SELECT poll_id FROM polls 
            WHERE status = 'ended' AND ended_at IS NOT NULL AND datetime(ended_at) <= datetime(?)
        """, (cutoff,)) as cursor:
            rows = await cursor.fetchall()
            expired_ids = [r[0] for r in rows]

        if not expired_ids:
            return 0

        for pid in expired_ids:
            await db.execute("DELETE FROM votes WHERE poll_id = ?", (pid,))
            await db.execute("DELETE FROM candidates WHERE poll_id = ?", (pid,))
            await db.execute("DELETE FROM polls WHERE poll_id = ?", (pid,))
        await db.commit()
        return len(expired_ids)

async def delete_poll_by_id(poll_id: int, creator_id: Optional[int] = None) -> bool:
    """
    Permanently deletes a poll, its candidates, and votes.
    If creator_id is provided and user is not an admin, verifies ownership.
    """
    async with get_db() as db:
        if creator_id is not None and creator_id not in ADMIN_IDS:
            async with db.execute("SELECT 1 FROM polls WHERE poll_id = ? AND creator_id = ?", (poll_id, creator_id)) as cur:
                if not await cur.fetchone():
                    return False

        await db.execute("DELETE FROM votes WHERE poll_id = ?", (poll_id,))
        await db.execute("DELETE FROM candidates WHERE poll_id = ?", (poll_id,))
        await db.execute("DELETE FROM polls WHERE poll_id = ?", (poll_id,))
        await db.commit()
        return True

async def delete_user_ended_polls(creator_id: int) -> int:
    """
    Permanently deletes all ended polls created by creator_id.
    """
    async with get_db() as db:
        async with db.execute("SELECT poll_id FROM polls WHERE creator_id = ? AND status = 'ended'", (creator_id,)) as cur:
            rows = await cur.fetchall()
            pids = [r[0] for r in rows]

        if not pids:
            return 0

        for pid in pids:
            await db.execute("DELETE FROM votes WHERE poll_id = ?", (pid,))
            await db.execute("DELETE FROM candidates WHERE poll_id = ?", (pid,))
            await db.execute("DELETE FROM polls WHERE poll_id = ?", (pid,))
        await db.commit()
        return len(pids)

async def get_user_polls(creator_id: int) -> List[Dict[str, Any]]:
    await cleanup_expired_ended_polls(days=2)
    async with get_db() as db:
        if creator_id in ADMIN_IDS:
            query = """
                SELECT p.*, (SELECT SUM(votes_count) FROM candidates WHERE poll_id = p.poll_id) as total_votes
                FROM polls p
                ORDER BY p.poll_id DESC
            """
            params = ()
        else:
            query = """
                SELECT p.*, (SELECT SUM(votes_count) FROM candidates WHERE poll_id = p.poll_id) as total_votes
                FROM polls p
                WHERE p.creator_id = ?
                ORDER BY p.poll_id DESC
            """
            params = (creator_id,)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def end_poll(poll_id: int) -> Optional[Dict[str, Any]]:
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    async with get_db() as db:
        await db.execute("""
            UPDATE polls 
            SET status = 'ended', ended_at = ? 
            WHERE poll_id = ? AND status = 'active'
        """, (now_str, poll_id))
        await db.commit()

        async with db.execute("""
            SELECT * FROM candidates 
            WHERE poll_id = ? 
            ORDER BY votes_count DESC, candidate_id ASC
        """, (poll_id,)) as cursor:
            candidates = [dict(r) for r in await cursor.fetchall()]

        poll_info = await get_poll(poll_id)
        if poll_info:
            # Candidates ordered strictly from MAX votes to LOW votes
            sorted_candidates = sorted(
                candidates,
                key=lambda c: (c.get("votes_count", 0), -c.get("candidate_id", 0)),
                reverse=True
            )
            poll_info["candidates"] = sorted_candidates
            poll_info["winner"] = sorted_candidates[0] if sorted_candidates else None
            w_count = int(poll_info.get("winner_count") or 1)
            # Pick the top w_count candidates strictly descending from MAX to LOW
            poll_info["top_winners"] = sorted_candidates[:w_count] if sorted_candidates else []
        return poll_info

async def end_all_poll_parts(poll_id: int) -> List[Dict[str, Any]]:
    parts = await get_poll_parts(poll_id)
    ended_parts = []
    for part in parts:
        if part["status"] == "active":
            p_data = await end_poll(part["poll_id"])
            if p_data:
                ended_parts.append(p_data)
    return ended_parts

async def get_system_stats() -> Dict[str, Any]:
    async with get_db() as db:
        total_users = 0
        total_channels = 0
        inactive_channels = 0
        total_polls = 0
        active_polls = 0
        total_votes = 0

        async with db.execute("SELECT COUNT(*) FROM users") as c:
            row = await c.fetchone()
            total_users = row[0] if row else 0

        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1") as c:
            row = await c.fetchone()
            total_channels = row[0] if row else 0

        async with db.execute("SELECT COUNT(*) FROM channels WHERE is_active = 0") as c:
            row = await c.fetchone()
            inactive_channels = row[0] if row else 0

        async with db.execute("SELECT COUNT(*) FROM polls") as c:
            row = await c.fetchone()
            total_polls = row[0] if row else 0

        async with db.execute("SELECT COUNT(*) FROM polls WHERE status = 'active'") as c:
            row = await c.fetchone()
            active_polls = row[0] if row else 0

        async with db.execute("SELECT COUNT(*) FROM votes") as c:
            row = await c.fetchone()
            total_votes = row[0] if row else 0

        ended_polls = max(0, total_polls - active_polls)

        return {
            "total_users": total_users,
            "total_channels": total_channels,
            "inactive_channels": inactive_channels,
            "total_polls": total_polls,
            "active_polls": active_polls,
            "ended_polls": ended_polls,
            "total_votes": total_votes
        }

async def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    async with get_db() as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else default

async def set_setting(key: str, value: str):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """, (key, value))
        await db.commit()

async def get_button_icon_style() -> str:
    val = await get_setting("poll_button_icon_style", "dynamic")
    return val if val else "dynamic"

async def set_button_icon_style(style: str):
    await set_setting("poll_button_icon_style", style)

async def get_user_icon_style(user_id: int) -> str:
    async with get_db() as db:
        async with db.execute("SELECT preferred_icon_style FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row["preferred_icon_style"]:
                return row["preferred_icon_style"]
    return await get_button_icon_style()

async def set_user_icon_style(user_id: int, style: str):
    async with get_db() as db:
        await db.execute("""
            INSERT INTO users (user_id, preferred_icon_style) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET preferred_icon_style = excluded.preferred_icon_style;
        """, (user_id, style))
        await db.commit()

async def get_custom_credit_btn_text() -> str:
    return (await get_setting("custom_credit_btn_text", "")) or ""

async def set_custom_credit_btn_text(text: str):
    await set_setting("custom_credit_btn_text", text)

# --- User Saved Custom Emojis ---
async def add_user_saved_emoji(user_id: int, emoji_id: str, name: str = "", fallback_char: str = "✨") -> bool:
    async with get_db() as db:
        clean_id = str(emoji_id).strip()
        clean_name = name.strip() or f"Emoji {clean_id[-6:]}"
        clean_fb = fallback_char.strip() or "✨"
        await db.execute("""
            INSERT INTO user_saved_emojis (user_id, emoji_id, name, fallback_char)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, emoji_id) DO UPDATE SET
                name = excluded.name,
                fallback_char = excluded.fallback_char;
        """, (user_id, clean_id, clean_name, clean_fb))
        await db.commit()
    return True

async def get_user_saved_emojis(user_id: int) -> List[Dict[str, Any]]:
    async with get_db() as db:
        async with db.execute("""
            SELECT id, user_id, emoji_id, name, fallback_char, created_at
            FROM user_saved_emojis
            WHERE user_id = ?
            ORDER BY id ASC;
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

async def delete_user_saved_emoji(user_id: int, emoji_id: str) -> bool:
    async with get_db() as db:
        await db.execute("""
            DELETE FROM user_saved_emojis WHERE user_id = ? AND emoji_id = ?;
        """, (user_id, str(emoji_id).strip()))
        await db.commit()
    return True

