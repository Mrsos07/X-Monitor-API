# ============================================================
#  X-Monitor  — Dockerfile (Production)
# ============================================================

# ── Stage 1: Dependencies ──────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production ───────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="X-Monitor" \
      description="نظام رصد حسابات X اللحظي" \
      version="1.0.0"

# متغيرات بيئة للإنتاج
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BROWSER_HEADLESS=true \
    DEBIAN_FRONTEND=noninteractive

# تثبيت مكتبات النظام + تنظيف
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-liberation \
    fonts-noto-color-emoji \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libdrm2 \
    libgbm1 \
    libxshmfence1 \
    libxrandr2 \
    libxcomposite1 \
    libxdamage1 \
    libpango-1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgcc-s1 \
    libglib2.0-0 \
    libnspr4 \
    libxcb1 \
    libxfixes3 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# نسخ الحزم من مرحلة البناء
COPY --from=builder /install /usr/local

# تثبيت Playwright Chromium
RUN playwright install chromium \
    && playwright install-deps chromium 2>/dev/null || true

# إنشاء مستخدم غير جذري
RUN groupadd -r xmonitor && useradd -r -g xmonitor -m -s /bin/bash xmonitor

WORKDIR /app

# نسخ الكود
COPY --chown=xmonitor:xmonitor . .

# إنشاء مجلد البيانات
RUN mkdir -p /app/data && chown -R xmonitor:xmonitor /app/data

# حذف الملفات غير الضرورية
RUN rm -f cookies.json.example webhook_receiver.py test_api.py 2>/dev/null || true

# التبديل للمستخدم غير الجذري
USER xmonitor

EXPOSE 8000

# فحص صحة الحاوية
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
