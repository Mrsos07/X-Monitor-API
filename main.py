# ============================================================
#  X-Monitor  — main.py
#  تطبيق FastAPI الرئيسي  —  جميع نقاط API
# ============================================================

from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Query, BackgroundTasks, Form, Cookie, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from loguru import logger
import hashlib, hmac, secrets, time

import database as db
import monitor
from models import (
    AccountAdd, AccountOut, PostOut,
    WebhookRegister, WebhookOut,
    MessageResponse, StatsResponse,
)
from config import settings


# ─────────────────────────────────────────────────────────────
#  دورة حياة التطبيق
# ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 بدء تشغيل X-Monitor ...")
    await db.init_db()
    await monitor.start_monitor()
    yield
    logger.info("🛑 إيقاف X-Monitor ...")
    await monitor.stop_monitor()


# ─────────────────────────────────────────────────────────────
#  إنشاء التطبيق
# ─────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "🔍 **X-Monitor API** — رصد حسابات تويتر/X بشكل لحظي\n\n"
        "### الاستخدام\n"
        "1. ضع الكوكيز في `cookies.json`\n"
        "2. أضف حسابات للمراقبة عبر `POST /accounts`\n"
        "3. سجّل Webhook عبر `POST /webhooks`\n"
        "4. استقبل المنشورات الجديدة فوراً!\n\n"
        "### المصادقة\n"
        "أرسل `X-API-Key` في الهيدر لجميع الطلبات."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Jinja2
templates = Jinja2Templates(directory="templates")

# ── جلسات الويب ────────────────────────────────────────────
_active_sessions: dict = {}   # token → expiry timestamp

def _create_session() -> str:
    token = secrets.token_hex(32)
    _active_sessions[token] = time.time() + 86400  # 24 ساعة
    return token

def _verify_session(token: str) -> bool:
    if not token or token not in _active_sessions:
        return False
    if time.time() > _active_sessions[token]:
        del _active_sessions[token]
        return False
    return True


# ─────────────────────────────────────────────────────────────
#  المصادقة
# ─────────────────────────────────────────────────────────────

async def verify_api_key(x_api_key: Optional[str] = Header(None)):
    if settings.API_KEY and x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="مفتاح API غير صالح. أرسل X-API-Key في الهيدر."
        )


# ─────────────────────────────────────────────────────────────
#  الجذر  &  الصحة
# ─────────────────────────────────────────────────────────────

@app.get("/", tags=["عام"])
async def root():
    return {
        "name":    settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "status":  "running" if monitor.is_running() else "stopped",
        "docs":    "/docs",
    }


@app.get("/health", tags=["عام"])
async def health():
    stats = await db.get_stats()
    return {
        "status":         "healthy",
        "monitor_active": monitor.is_running(),
        **stats,
        "timestamp":      datetime.utcnow().isoformat() + "Z",
    }


@app.get("/stats", response_model=StatsResponse, tags=["عام"])
async def get_stats(_=Depends(verify_api_key)):
    stats = await db.get_stats()
    return StatsResponse(
        **stats,
        monitor_running=monitor.is_running()
    )


# ─────────────────────────────────────────────────────────────
#  ═══  الحسابات  ═══
# ─────────────────────────────────────────────────────────────

@app.post(
    "/accounts",
    response_model=AccountOut,
    status_code=201,
    tags=["حسابات"],
    summary="إضافة حساب للمراقبة",
)
async def add_account(
    body: AccountAdd,
    background_tasks: BackgroundTasks,
    _=Depends(verify_api_key),
):
    """
    أضف حساب X للمراقبة اللحظية.

    - **username**: المعرّف بدون `@`
    - **interval_seconds**: كم ثانية بين كل فحص (10–3600)
    - **webhook_url**: اختياري — Webhook مخصص لهذا الحساب فقط
    """
    row = await db.add_account(
        body.username, body.interval_seconds, body.webhook_url
    )
    # جلب فوري في الخلفية
    background_tasks.add_task(monitor.immediate_check, body.username)
    logger.info(f"➕ تمت إضافة @{body.username}")
    return _format_account(row)


@app.get(
    "/accounts",
    response_model=List[AccountOut],
    tags=["حسابات"],
    summary="قائمة الحسابات",
)
async def list_accounts(
    active_only: bool = Query(False, description="عرض النشطة فقط"),
    _=Depends(verify_api_key),
):
    rows = await db.list_accounts(active_only=active_only)
    return [_format_account(r) for r in rows]


@app.get(
    "/accounts/{username}",
    response_model=AccountOut,
    tags=["حسابات"],
    summary="تفاصيل حساب",
)
async def get_account(username: str, _=Depends(verify_api_key)):
    username = username.lstrip("@").lower()
    row = await db.get_account(username)
    if not row:
        raise HTTPException(404, f"الحساب @{username} غير موجود")
    return _format_account(row)


@app.delete(
    "/accounts/{username}",
    response_model=MessageResponse,
    tags=["حسابات"],
    summary="حذف حساب من المراقبة",
)
async def delete_account(username: str, _=Depends(verify_api_key)):
    username = username.lstrip("@").lower()
    row = await db.get_account(username)
    if not row:
        raise HTTPException(404, f"الحساب @{username} غير موجود")
    await db.delete_account(username)
    return MessageResponse(message=f"تم حذف @{username} من المراقبة")


@app.patch(
    "/accounts/{username}/pause",
    response_model=MessageResponse,
    tags=["حسابات"],
    summary="إيقاف مؤقت لحساب",
)
async def pause_account(username: str, _=Depends(verify_api_key)):
    username = username.lstrip("@").lower()
    await db.deactivate_account(username)
    return MessageResponse(message=f"تم إيقاف مراقبة @{username} مؤقتاً")


@app.post(
    "/accounts/{username}/check",
    response_model=MessageResponse,
    tags=["حسابات"],
    summary="فحص فوري لحساب",
)
async def force_check(
    username: str,
    background_tasks: BackgroundTasks,
    _=Depends(verify_api_key),
):
    username = username.lstrip("@").lower()
    background_tasks.add_task(monitor.immediate_check, username)
    return MessageResponse(message=f"بدأ الفحص الفوري لـ @{username}")


# ─────────────────────────────────────────────────────────────
#  ═══  المنشورات  ═══
# ─────────────────────────────────────────────────────────────

@app.get(
    "/posts",
    response_model=List[PostOut],
    tags=["منشورات"],
    summary="جميع المنشورات المجمَّعة",
)
async def get_all_posts(
    limit:  int = Query(50,  ge=1, le=500),
    offset: int = Query(0,   ge=0),
    _=Depends(verify_api_key),
):
    rows = await db.get_posts(limit=limit, offset=offset)
    return [_format_post(r) for r in rows]


@app.get(
    "/posts/{username}",
    response_model=List[PostOut],
    tags=["منشورات"],
    summary="منشورات حساب محدد",
)
async def get_user_posts(
    username: str,
    limit:  int = Query(50,  ge=1, le=500),
    offset: int = Query(0,   ge=0),
    _=Depends(verify_api_key),
):
    username = username.lstrip("@").lower()
    rows = await db.get_posts(username=username, limit=limit, offset=offset)
    return [_format_post(r) for r in rows]


# ─────────────────────────────────────────────────────────────
#  ═══  Webhooks  ═══
# ─────────────────────────────────────────────────────────────

@app.post(
    "/webhooks",
    response_model=WebhookOut,
    status_code=201,
    tags=["Webhooks"],
    summary="تسجيل Webhook جديد",
)
async def register_webhook(body: WebhookRegister, _=Depends(verify_api_key)):
    """
    سجّل عنوان URL لاستقبال إشعارات عند نشر تغريدات جديدة.

    **الـ Payload المرسَل:**
    ```json
    {
      "event": "new_post",
      "timestamp": "2025-01-01T00:00:00Z",
      "data": { ... بيانات التغريدة ... }
    }
    ```

    إن أرسلت `secret` سيتم إرفاق `X-Webhook-Signature: sha256=...` بكل طلب.
    """
    row = await db.add_webhook(body.url, body.secret, body.events)
    return _format_webhook(row)


@app.get(
    "/webhooks",
    response_model=List[WebhookOut],
    tags=["Webhooks"],
    summary="قائمة الـ Webhooks",
)
async def list_webhooks(
    active_only: bool = Query(True),
    _=Depends(verify_api_key),
):
    rows = await db.list_webhooks(active_only=active_only)
    return [_format_webhook(r) for r in rows]


@app.delete(
    "/webhooks/{webhook_id}",
    response_model=MessageResponse,
    tags=["Webhooks"],
    summary="حذف Webhook",
)
async def delete_webhook(webhook_id: int, _=Depends(verify_api_key)):
    await db.delete_webhook(webhook_id)
    return MessageResponse(message=f"تم حذف Webhook #{webhook_id}")


@app.post(
    "/webhooks/test",
    response_model=MessageResponse,
    tags=["Webhooks"],
    summary="اختبار Webhook",
)
async def test_webhook(body: WebhookRegister, _=Depends(verify_api_key)):
    """
    يُرسل حدث اختبار لعنوان URL المحدد دون حفظه.
    """
    import httpx
    payload = {
        "event": "test",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "data": {
            "message": "مرحباً من X-Monitor! 🎉",
            "tweet_id": "0000000000",
            "username": "test_user",
            "text": "هذه تغريدة اختبارية",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(body.url, json=payload)
        return MessageResponse(
            message=f"تم الإرسال — كود الاستجابة: {resp.status_code}"
        )
    except Exception as e:
        raise HTTPException(502, f"فشل الاتصال: {e}")


# ─────────────────────────────────────────────────────────────
#  تحويل الصفوف → نماذج Pydantic
# ─────────────────────────────────────────────────────────────

def _parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _format_account(r: dict) -> AccountOut:
    return AccountOut(
        id=r["id"],
        username=r["username"],
        interval_seconds=r["interval_seconds"],
        webhook_url=r.get("webhook_url"),
        is_active=bool(r["is_active"]),
        added_at=_parse_dt(r["added_at"]) or datetime.utcnow(),
        last_checked=_parse_dt(r.get("last_checked")),
        posts_collected=r.get("posts_collected", 0),
    )


def _format_post(r: dict) -> PostOut:
    import json as _json
    mu = r.get("media_urls", "[]")
    if isinstance(mu, str):
        mu = _json.loads(mu)
    return PostOut(
        id=r["id"],
        tweet_id=r["tweet_id"],
        username=r["username"],
        text=r.get("text", ""),
        created_at=_parse_dt(r.get("created_at")),
        likes=r.get("likes", 0),
        retweets=r.get("retweets", 0),
        replies=r.get("replies", 0),
        views=r.get("views", 0),
        media_urls=mu,
        tweet_url=r.get("tweet_url", ""),
        fetched_at=_parse_dt(r.get("fetched_at")) or datetime.utcnow(),
    )


def _format_webhook(r: dict) -> WebhookOut:
    import json as _json
    ev = r.get("events", '["new_post"]')
    if isinstance(ev, str):
        ev = _json.loads(ev)
    return WebhookOut(
        id=r["id"],
        url=r["url"],
        secret=r.get("secret"),
        events=ev,
        is_active=bool(r.get("is_active", 1)),
        created_at=_parse_dt(r["created_at"]) or datetime.utcnow(),
        last_triggered=_parse_dt(r.get("last_triggered")),
        success_count=r.get("success_count", 0),
        fail_count=r.get("fail_count", 0),
    )


# ─────────────────────────────────────────────────────────────
#  ═══  واجهة الويب  ═══
# ─────────────────────────────────────────────────────────────

@app.get("/panel", response_class=HTMLResponse, include_in_schema=False)
async def panel_page(request: Request, session: Optional[str] = Cookie(None)):
    if not _verify_session(session):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "api_key": settings.API_KEY,
    })


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, session: Optional[str] = Cookie(None)):
    if _verify_session(session):
        return RedirectResponse("/panel", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
    })


@app.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        token = _create_session()
        resp = RedirectResponse("/panel", status_code=302)
        resp.set_cookie("session", token, httponly=True, max_age=86400)
        logger.info(f"🔑 تسجيل دخول ناجح من واجهة الإدارة")
        return resp
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "اسم المستخدم أو كلمة المرور غير صحيحة",
    })


@app.get("/logout", include_in_schema=False)
async def logout(session: Optional[str] = Cookie(None)):
    if session and session in _active_sessions:
        del _active_sessions[session]
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie("session")
    return resp


# ─────────────────────────────────────────────────────────────
#  تشغيل
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=False,
        log_level="info",
    )
