# ============================================================
#  X-Monitor  — webhook_sender.py
#  إرسال إشعارات Webhook عند اكتشاف منشورات جديدة
# ============================================================

import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from typing import List, Dict, Optional
import httpx
from loguru import logger
import database as db
from config import settings


# ─────────────────────────────────────────────────────────────
#  إرسال حدث واحد لكل الـ Webhooks المسجَّلة
# ─────────────────────────────────────────────────────────────

async def dispatch_event(event: str, data: Dict):
    """
    يُرسل الحدث لكل Webhook مسجَّل مع الحدث المطلوب.
    يُعيد عدد الإرسالات الناجحة.
    """
    webhooks = await db.list_webhooks(active_only=True)
    if not webhooks:
        return 0

    payload = {
        "event":     event,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data":      data,
    }
    body = json.dumps(payload, ensure_ascii=False)

    tasks = []
    for wh in webhooks:
        if event in wh.get("events", ["new_post"]):
            tasks.append(_send_one(wh, body))

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success = sum(1 for r in results if r is True)
    return success


async def dispatch_new_posts(posts: List[Dict]):
    """اختصار: يُرسل كل تغريدة جديدة على حدة"""
    for post in posts:
        await dispatch_event("new_post", post)


# ─────────────────────────────────────────────────────────────
#  إرسال فعلي لـ Webhook واحد (مع إعادة المحاولة)
# ─────────────────────────────────────────────────────────────

async def _send_one(webhook: Dict, body: str) -> bool:
    url    = webhook["url"]
    secret = webhook.get("secret")
    wh_id  = webhook["id"]

    headers = {
        "Content-Type":  "application/json; charset=utf-8",
        "User-Agent":    "X-Monitor-Webhook/1.0",
        "X-Event-Source": "x-monitor",
    }

    if secret:
        sig = hmac.new(
            secret.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"

    for attempt in range(1, settings.WEBHOOK_RETRY_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, content=body, headers=headers)
            if resp.status_code < 400:
                await db.update_webhook_stats(wh_id, success=True)
                logger.debug(f"📤 Webhook {url} → {resp.status_code}")
                return True
            else:
                logger.warning(
                    f"⚠️  Webhook {url} رد بـ {resp.status_code} (محاولة {attempt})"
                )
        except Exception as e:
            logger.warning(f"⚠️  Webhook {url} خطأ: {e} (محاولة {attempt})")

        if attempt < settings.WEBHOOK_RETRY_ATTEMPTS:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

    await db.update_webhook_stats(wh_id, success=False)
    return False
