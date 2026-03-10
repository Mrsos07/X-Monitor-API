# ============================================================
#  X-Monitor  — models.py
#  نماذج Pydantic للطلبات والردود
# ============================================================

from pydantic import BaseModel, HttpUrl, Field, validator
from typing import Optional, List, Any
from datetime import datetime
import re


# ─────────────────────────────────────────────────────────────
#  الحسابات المراقَبة
# ─────────────────────────────────────────────────────────────

class AccountAdd(BaseModel):
    username: str = Field(..., description="معرّف X بدون @", examples=["elonmusk"])
    interval_seconds: int = Field(default=30, ge=10, le=3600,
                                   description="فترة الاستطلاع بالثواني")
    webhook_url: Optional[str] = Field(None,
                                        description="Webhook مخصص لهذا الحساب")

    @validator("username")
    def clean_username(cls, v: str) -> str:
        v = v.lstrip("@").strip()
        if not re.match(r"^[A-Za-z0-9_]{1,50}$", v):
            raise ValueError("معرّف المستخدم غير صالح")
        return v.lower()


class AccountOut(BaseModel):
    id: int
    username: str
    interval_seconds: int
    webhook_url: Optional[str]
    is_active: bool
    added_at: datetime
    last_checked: Optional[datetime]
    posts_collected: int

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────
#  التغريدات / المنشورات
# ─────────────────────────────────────────────────────────────

class PostOut(BaseModel):
    id: int
    tweet_id: str
    username: str
    text: str
    created_at: Optional[datetime]
    likes: int
    retweets: int
    replies: int
    views: int
    media_urls: List[str]
    tweet_url: str
    fetched_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────
#  Webhooks
# ─────────────────────────────────────────────────────────────

class WebhookRegister(BaseModel):
    url: str = Field(..., description="عنوان URL لاستقبال الإشعارات")
    secret: Optional[str] = Field(None, description="مفتاح سري لتوقيع الطلبات")
    events: List[str] = Field(
        default=["new_post"],
        description="أنواع الأحداث: new_post, account_error"
    )

    @validator("url")
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL يجب أن يبدأ بـ http:// أو https://")
        return v


class WebhookOut(BaseModel):
    id: int
    url: str
    secret: Optional[str]
    events: List[str]
    is_active: bool
    created_at: datetime
    last_triggered: Optional[datetime]
    success_count: int
    fail_count: int

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────
#  Webhook Payload  (ما يُرسَل للمستقبِل)
# ─────────────────────────────────────────────────────────────

class WebhookPayload(BaseModel):
    event: str = "new_post"
    timestamp: datetime
    data: Any


# ─────────────────────────────────────────────────────────────
#  ردود عامة
# ─────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    success: bool = True


class StatsResponse(BaseModel):
    total_accounts: int
    active_accounts: int
    total_posts: int
    posts_last_24h: int
    total_webhooks: int
    monitor_running: bool
