# ============================================================
#  X-Monitor  — monitor.py
#  محرك المراقبة اللحظية  (حلقة خلفية لكل حساب)
# ============================================================

import asyncio
from datetime import datetime
from typing import Dict, Set
from loguru import logger

import database as db
import browser
import webhook_sender
from config import settings

# ─────────────────────────────────────────────────────────────
#  حالة المراقب
# ─────────────────────────────────────────────────────────────

_running_tasks: Dict[str, asyncio.Task] = {}   # username → Task
_monitor_active: bool = False


def is_running() -> bool:
    return _monitor_active


# ─────────────────────────────────────────────────────────────
#  بدء / إيقاف المراقبة العامة
# ─────────────────────────────────────────────────────────────

async def start_monitor():
    global _monitor_active
    if _monitor_active:
        return
    _monitor_active = True
    await browser.init_browser()
    logger.success("🟢 محرك المراقبة بدأ")
    asyncio.create_task(_supervisor_loop())


async def stop_monitor():
    global _monitor_active
    _monitor_active = False
    for username, task in _running_tasks.items():
        task.cancel()
        logger.info(f"⏹  إيقاف مراقبة @{username}")
    _running_tasks.clear()
    await browser.close_browser()
    logger.warning("🔴 محرك المراقبة أُوقف")


# ─────────────────────────────────────────────────────────────
#  الحلقة الإشرافية  — تتفقد الحسابات وتشغّل المهام
# ─────────────────────────────────────────────────────────────

async def _supervisor_loop():
    """كل 5 ثوانٍ: تفقّد الحسابات الجديدة أو المُزالة"""
    while _monitor_active:
        try:
            accounts = await db.list_accounts(active_only=True)
            active_usernames: Set[str] = {a["username"] for a in accounts}

            # شغِّل مهمة لكل حساب جديد
            for acc in accounts:
                uname = acc["username"]
                if uname not in _running_tasks or _running_tasks[uname].done():
                    logger.info(f"▶️  بدء مراقبة @{uname}")
                    _running_tasks[uname] = asyncio.create_task(
                        _monitor_account_loop(acc)
                    )

            # أوقف مهام الحسابات المُزالة
            for uname in list(_running_tasks.keys()):
                if uname not in active_usernames:
                    _running_tasks[uname].cancel()
                    del _running_tasks[uname]
                    logger.info(f"🗑  إزالة مراقبة @{uname}")

        except Exception as e:
            logger.error(f"خطأ في المشرف: {e}")

        await asyncio.sleep(5)


# ─────────────────────────────────────────────────────────────
#  حلقة مراقبة حساب واحد
# ─────────────────────────────────────────────────────────────

async def _monitor_account_loop(account: Dict):
    username = account["username"]
    interval = account.get("interval_seconds", settings.MONITOR_INTERVAL_SECONDS)
    logger.info(f"👁  مراقبة @{username}  (كل {interval}ث)")

    while _monitor_active:
        try:
            await _check_account(username, account.get("webhook_url"))
        except asyncio.CancelledError:
            logger.info(f"❌ إلغاء مراقبة @{username}")
            break
        except Exception as e:
            logger.error(f"خطأ مراقبة @{username}: {e}")

        # أعد تحميل الإعدادات (قد تتغير الفترة)
        fresh = await db.get_account(username)
        if fresh:
            interval = fresh.get("interval_seconds", interval)

        await asyncio.sleep(interval)


# ─────────────────────────────────────────────────────────────
#  فحص حساب واحد ومعالجة التغريدات
# ─────────────────────────────────────────────────────────────

async def _check_account(username: str, account_webhook: str = None):
    # جلب التغريدات من المتصفح
    raw_posts = await browser.fetch_user_posts(
        username, max_posts=settings.MAX_POSTS_PER_FETCH
    )
    if not raw_posts:
        await db.update_last_checked(username)
        return

    # تحديد التغريدات الجديدة فقط
    known_ids = await db.get_known_tweet_ids(username)
    new_posts  = [p for p in raw_posts if p["tweet_id"] not in known_ids]

    if not new_posts:
        logger.debug(f"🔁 @{username}: لا جديد")
        await db.update_last_checked(username)
        return

    logger.success(f"🆕 @{username}: {len(new_posts)} منشور جديد!")

    # حفظ في قاعدة البيانات
    saved = await db.save_posts(new_posts)
    if saved > 0:
        await db.increment_posts_count(username, saved)

    # إرسال Webhook
    await webhook_sender.dispatch_new_posts(new_posts)

    # Webhook مخصص للحساب إن وُجد
    if account_webhook:
        for post in new_posts:
            import httpx
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(
                        account_webhook,
                        json={"event": "new_post", "data": post},
                    )
            except Exception as e:
                logger.warning(f"⚠️  Webhook الحساب فشل: {e}")

    await db.update_last_checked(username)


# ─────────────────────────────────────────────────────────────
#  جلب فوري لحساب (عند الإضافة)
# ─────────────────────────────────────────────────────────────

async def immediate_check(username: str):
    """يُستدعى عند إضافة حساب جديد لجلب أول دفعة فوراً"""
    acc = await db.get_account(username)
    if not acc:
        return
    await _check_account(username, acc.get("webhook_url"))
