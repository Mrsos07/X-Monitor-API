# 🔍 X-Monitor — نظام رصد حسابات X لحظي

نظام متكامل لمراقبة حسابات **تويتر / X** بشكل **لحظي** باستخدام Playwright مع واجهة API RESTful كاملة ولوحة تحكم عصرية.

---

## 🏗️ هيكل المشروع

```
x-monitor/
├── main.py              # تطبيق FastAPI — API + واجهة الإدارة
├── monitor.py           # محرك المراقبة اللحظية (حلقات خلفية)
├── browser.py           # محرك Playwright (فتح X وجلب التغريدات)
├── database.py          # طبقة SQLite (aiosqlite)
├── webhook_sender.py    # إرسال إشعارات Webhook
├── models.py            # نماذج Pydantic
├── config.py            # إعدادات مركزية
├── export_cookies.py    # أداة تصدير الكوكيز
├── templates/
│   ├── login.html       # صفحة تسجيل الدخول
│   └── dashboard.html   # لوحة التحكم
├── test_api.py          # اختبار API
├── requirements.txt
├── Dockerfile           # Docker متعدد المراحل للإنتاج
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
└── cookies.json.example
```

---

## ⚡ التشغيل السريع

### 1. تثبيت المتطلبات

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. تصدير الكوكيز (مرة واحدة فقط)

```bash
python export_cookies.py
```
سيفتح متصفح — سجّل دخولك يدوياً — اضغط Enter — سيُحفظ `cookies.json` تلقائياً.

**أو** استخدم إضافة [Cookie-Editor](https://cookie-editor.com/) للمتصفح:
1. افتح `x.com` وسجّل الدخول
2. اضغط إضافة → Export → Export as JSON
3. احفظ المحتوى في `cookies.json`

### 3. إعداد المتغيرات

```bash
cp .env.example .env
# عدّل API_KEY على الأقل
```

### 4. تشغيل النظام

```bash
python main.py
```

| الرابط | الوصف |
|-------|-------|
| http://localhost:8000/login | تسجيل الدخول |
| http://localhost:8000/panel | لوحة التحكم |
| http://localhost:8000/docs | وثائق Swagger API |
| http://localhost:8000/health | فحص الصحة |

---

## 🐳 Docker (إنتاج)

```bash
# إعداد البيئة
cp .env.example .env
# ❗ عدّل جميع القيم السرية في .env

# بناء وتشغيل
docker-compose up -d --build

# متابعة السجلات
docker-compose logs -f

# إعادة التشغيل
docker-compose restart

# إيقاف
docker-compose down
```

**مميزات Docker:**
- بناء متعدد المراحل (Multi-stage) لتقليل حجم الصورة
- مستخدم غير جذري (non-root) للأمان
- Health check تلقائي
- تدوير السجلات (10MB × 3 ملفات)
- حدود الموارد (1GB RAM, 1 CPU)
- Volume مستقل لقاعدة البيانات

---

## 📡 نقاط API

### المصادقة
أرسل `X-API-Key` في هيدر كل طلب:
```
X-API-Key: x-monitor-secret-key-change-me
```

---

### 👤 الحسابات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| `POST` | `/accounts` | ➕ إضافة حساب للمراقبة |
| `GET` | `/accounts` | 📋 قائمة الحسابات |
| `GET` | `/accounts/{username}` | 🔍 تفاصيل حساب |
| `DELETE` | `/accounts/{username}` | 🗑️ حذف حساب |
| `PATCH` | `/accounts/{username}/pause` | ⏸️ إيقاف مؤقت |
| `POST` | `/accounts/{username}/check` | ⚡ فحص فوري |

**إضافة حساب:**
```bash
curl -X POST http://localhost:8000/accounts \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "elonmusk",
    "interval_seconds": 30,
    "webhook_url": "https://your-site.com/webhook"
  }'
```

---

### 📰 المنشورات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| `GET` | `/posts` | 📊 جميع المنشورات |
| `GET` | `/posts/{username}` | 👤 منشورات حساب محدد |

```bash
# آخر 20 تغريدة
curl http://localhost:8000/posts?limit=20 \
  -H "X-API-Key: YOUR_KEY"

# تغريدات حساب محدد
curl http://localhost:8000/posts/elonmusk \
  -H "X-API-Key: YOUR_KEY"
```

---

### 🔔 Webhooks

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| `POST` | `/webhooks` | ➕ تسجيل Webhook |
| `GET` | `/webhooks` | 📋 قائمة الـ Webhooks |
| `DELETE` | `/webhooks/{id}` | 🗑️ حذف Webhook |
| `POST` | `/webhooks/test` | 🧪 اختبار Webhook |

**تسجيل Webhook:**
```bash
curl -X POST http://localhost:8000/webhooks \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-site.com/receive",
    "secret": "my-secret",
    "events": ["new_post"]
  }'
```

**شكل البيانات المُرسَلة:**
```json
{
  "event": "new_post",
  "timestamp": "2025-01-01T12:00:00Z",
  "data": {
    "tweet_id": "1234567890",
    "username": "elonmusk",
    "text": "نص التغريدة هنا...",
    "created_at": "2025-01-01T11:59:00Z",
    "likes": 1500,
    "retweets": 300,
    "replies": 120,
    "views": 50000,
    "media_urls": ["https://pbs.twimg.com/media/..."],
    "tweet_url": "https://x.com/elonmusk/status/1234567890"
  }
}
```

إن أرسلت `secret` ستجد التوقيع في الهيدر:
```
X-Webhook-Signature: sha256=abc123...
```

---

### 📊 الإحصاءات والصحة

```bash
# صحة النظام (بدون مصادقة)
curl http://localhost:8000/health

# إحصاءات تفصيلية
curl http://localhost:8000/stats -H "X-API-Key: YOUR_KEY"
```

---

## 🧪 اختبار API

```bash
python test_api.py http://localhost:8000 YOUR_API_KEY
```

---

## ⚙️ الإعدادات

| المتغير | القيمة الافتراضية | الوصف |
|---------|------------------|-------|
| `API_KEY` | `x-monitor-...` | مفتاح المصادقة للـ API |
| `APP_PORT` | `8000` | منفذ الخادم |
| `MONITOR_INTERVAL_SECONDS` | `30` | فترة الاستطلاع (ثانية) |
| `MAX_POSTS_PER_FETCH` | `10` | عدد التغريدات كل فحص |
| `BROWSER_HEADLESS` | `true` | إخفاء نافذة المتصفح |
| `WEBHOOK_RETRY_ATTEMPTS` | `3` | محاولات إعادة الإرسال |
| `ADMIN_USERNAME` | `admin` | اسم مستخدم لوحة التحكم |
| `ADMIN_PASSWORD` | — | كلمة مرور لوحة التحكم |
| `SESSION_SECRET` | — | مفتاح سري للجلسات |

---

## 🔒 الأمان

- غيّر `API_KEY` و `ADMIN_PASSWORD` و `SESSION_SECRET` في `.env` قبل النشر
- لا تشارك `cookies.json` أو `.env` مع أحد
- استخدم HTTPS في الإنتاج (عبر Nginx/Caddy كـ reverse proxy)
- الحاوية تعمل بمستخدم غير جذري (non-root)
- لا ترفع `.env` أو `cookies.json` إلى Git (محمية بـ `.gitignore`)

---

## 📝 ملاحظات

- الكوكيز تُحمَّل **مرة واحدة** فقط عند بدء التشغيل
- المتصفح يبقى مفتوحاً طول مدة التشغيل
- كل حساب له **حلقة مستقلة** غير معطِّلة للأخرى
- التغريدات الجديدة تُرسَل للـ Webhooks فور اكتشافها
