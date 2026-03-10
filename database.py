# ============================================================
#  X-Monitor  — database.py
#  طبقة قاعدة البيانات  (aiosqlite)
# ============================================================

import aiosqlite
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from loguru import logger
from config import settings


DB = settings.DB_PATH


# ─────────────────────────────────────────────────────────────
#  تهيئة الجداول
# ─────────────────────────────────────────────────────────────

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS accounts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    username         TEXT    UNIQUE NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 30,
    webhook_url      TEXT,
    is_active        INTEGER NOT NULL DEFAULT 1,
    added_at         TEXT    NOT NULL,
    last_checked     TEXT,
    posts_collected  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS posts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id    TEXT    UNIQUE NOT NULL,
    username    TEXT    NOT NULL,
    text        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT,
    likes       INTEGER DEFAULT 0,
    retweets    INTEGER DEFAULT 0,
    replies     INTEGER DEFAULT 0,
    views       INTEGER DEFAULT 0,
    media_urls  TEXT    DEFAULT '[]',
    tweet_url   TEXT    NOT NULL DEFAULT '',
    fetched_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_posts_username ON posts(username);
CREATE INDEX IF NOT EXISTS idx_posts_fetched  ON posts(fetched_at);

CREATE TABLE IF NOT EXISTS webhooks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT    NOT NULL,
    secret          TEXT,
    events          TEXT    NOT NULL DEFAULT '["new_post"]',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    last_triggered  TEXT,
    success_count   INTEGER DEFAULT 0,
    fail_count      INTEGER DEFAULT 0
);
"""


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("✅ قاعدة البيانات جاهزة")


# ─────────────────────────────────────────────────────────────
#  حسابات
# ─────────────────────────────────────────────────────────────

async def add_account(username: str, interval: int,
                      webhook_url: Optional[str]) -> Dict:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        # إن كان موجوداً → أعِد التفعيل
        await db.execute(
            """INSERT INTO accounts (username, interval_seconds, webhook_url, added_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                 interval_seconds = excluded.interval_seconds,
                 webhook_url      = excluded.webhook_url,
                 is_active        = 1""",
            (username, interval, webhook_url, now)
        )
        await db.commit()
        row = await db.execute(
            "SELECT * FROM accounts WHERE username = ?", (username,))
        r = await row.fetchone()
        return dict(r)


async def list_accounts(active_only: bool = False) -> List[Dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM accounts"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY added_at DESC"
        cur = await db.execute(q)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_account(username: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM accounts WHERE username = ?", (username,))
        r = await cur.fetchone()
        return dict(r) if r else None


async def update_last_checked(username: str):
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE accounts SET last_checked = ? WHERE username = ?",
            (now, username))
        await db.commit()


async def increment_posts_count(username: str, count: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE accounts SET posts_collected = posts_collected + ? WHERE username = ?",
            (count, username))
        await db.commit()


async def deactivate_account(username: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE accounts SET is_active = 0 WHERE username = ?", (username,))
        await db.commit()


async def delete_account(username: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM accounts WHERE username = ?", (username,))
        await db.commit()


# ─────────────────────────────────────────────────────────────
#  منشورات
# ─────────────────────────────────────────────────────────────

async def save_posts(posts: List[Dict]) -> int:
    """يحفظ القائمة ويعيد عدد السجلات الجديدة فعلاً"""
    if not posts:
        return 0
    new_count = 0
    async with aiosqlite.connect(DB) as db:
        for p in posts:
            cur = await db.execute(
                """INSERT OR IGNORE INTO posts
                   (tweet_id, username, text, created_at, likes, retweets,
                    replies, views, media_urls, tweet_url, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    p["tweet_id"], p["username"], p.get("text", ""),
                    p.get("created_at"), p.get("likes", 0),
                    p.get("retweets", 0), p.get("replies", 0),
                    p.get("views", 0),
                    json.dumps(p.get("media_urls", [])),
                    p.get("tweet_url", ""),
                    datetime.utcnow().isoformat()
                )
            )
            new_count += cur.rowcount
        await db.commit()
    return new_count


async def get_posts(username: Optional[str] = None,
                    limit: int = 50,
                    offset: int = 0) -> List[Dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        if username:
            cur = await db.execute(
                "SELECT * FROM posts WHERE username=? ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
                (username, limit, offset))
        else:
            cur = await db.execute(
                "SELECT * FROM posts ORDER BY fetched_at DESC LIMIT ? OFFSET ?",
                (limit, offset))
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["media_urls"] = json.loads(d.get("media_urls") or "[]")
            result.append(d)
        return result


async def get_known_tweet_ids(username: str) -> set:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT tweet_id FROM posts WHERE username = ?", (username,))
        rows = await cur.fetchall()
        return {r[0] for r in rows}


# ─────────────────────────────────────────────────────────────
#  Webhooks
# ─────────────────────────────────────────────────────────────

async def add_webhook(url: str, secret: Optional[str],
                      events: List[str]) -> Dict:
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO webhooks (url, secret, events, created_at)
               VALUES (?, ?, ?, ?)""",
            (url, secret, json.dumps(events), now))
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM webhooks WHERE url = ? ORDER BY id DESC LIMIT 1", (url,))
        r = await cur.fetchone()
        d = dict(r)
        d["events"] = json.loads(d["events"])
        return d


async def list_webhooks(active_only: bool = True) -> List[Dict]:
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM webhooks"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY created_at DESC"
        cur = await db.execute(q)
        rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["events"] = json.loads(d.get("events") or '["new_post"]')
            result.append(d)
        return result


async def update_webhook_stats(webhook_id: int, success: bool):
    now = datetime.utcnow().isoformat()
    field = "success_count" if success else "fail_count"
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            f"UPDATE webhooks SET {field}={field}+1, last_triggered=? WHERE id=?",
            (now, webhook_id))
        await db.commit()


async def delete_webhook(webhook_id: int):
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
        await db.commit()


# ─────────────────────────────────────────────────────────────
#  إحصاءات
# ─────────────────────────────────────────────────────────────

async def get_stats() -> Dict:
    async with aiosqlite.connect(DB) as db:
        total_acc   = (await (await db.execute("SELECT COUNT(*) FROM accounts")).fetchone())[0]
        active_acc  = (await (await db.execute("SELECT COUNT(*) FROM accounts WHERE is_active=1")).fetchone())[0]
        total_posts = (await (await db.execute("SELECT COUNT(*) FROM posts")).fetchone())[0]
        posts_24h   = (await (await db.execute(
            "SELECT COUNT(*) FROM posts WHERE fetched_at >= datetime('now','-1 day')"
        )).fetchone())[0]
        total_wh    = (await (await db.execute("SELECT COUNT(*) FROM webhooks WHERE is_active=1")).fetchone())[0]
    return {
        "total_accounts": total_acc,
        "active_accounts": active_acc,
        "total_posts": total_posts,
        "posts_last_24h": posts_24h,
        "total_webhooks": total_wh,
    }
