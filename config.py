# ============================================================
#  X-Monitor  — config.py
#  إعدادات التطبيق المركزية
# ============================================================

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # ── تطبيق FastAPI ──────────────────────────────────────
    APP_TITLE: str = "X-Monitor API"
    APP_VERSION: str = "1.0.0"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_KEY: str = "x-monitor-secret-key-change-me"   # غيّره في .env

    # ── قاعدة البيانات ────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./x_monitor.db"
    DB_PATH: str = "x_monitor.db"

    # ── ملف الكوكيز ───────────────────────────────────────
    COOKIES_FILE: str = "cookies.json"

    # ── المراقبة ──────────────────────────────────────────
    MONITOR_INTERVAL_SECONDS: int = 30      # فترة الاستطلاع الافتراضية
    MAX_POSTS_PER_FETCH: int = 10           # عدد أحدث تغريدات يُجلبها كل مرة
    BROWSER_HEADLESS: bool = True           # True = بدون واجهة رسومية

    # ── Webhook ───────────────────────────────────────────
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_RETRY_ATTEMPTS: int = 3

    # ── واجهة الإدارة ────────────────────────────────────
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    SESSION_SECRET: str = "x-monitor-session-secret-change-me"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
