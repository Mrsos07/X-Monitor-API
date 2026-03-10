#!/usr/bin/env python3
# ============================================================
#  X-Monitor  — test_api.py
#  اختبار سريع لجميع نقاط API
# ============================================================

"""
الاستخدام:
    python test_api.py [BASE_URL] [API_KEY]

مثال:
    python test_api.py http://localhost:8000 x-monitor-secret-key-change-me
"""

import sys
import json
import httpx


def main():
    BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    KEY  = sys.argv[2] if len(sys.argv) > 2 else "x-monitor-secret-key-change-me"
    H    = {"X-API-Key": KEY, "Content-Type": "application/json"}

    print(f"\n🧪 اختبار X-Monitor API على: {BASE}")
    print("═" * 60)

    # ─── Health ───────────────────────────────────────────
    print("\n1️⃣  /health")
    r = httpx.get(f"{BASE}/health")
    _show(r)

    # ─── Stats ────────────────────────────────────────────
    print("\n2️⃣  /stats")
    r = httpx.get(f"{BASE}/stats", headers=H)
    _show(r)

    # ─── Add Account ──────────────────────────────────────
    print("\n3️⃣  POST /accounts  (إضافة @nasa)")
    r = httpx.post(f"{BASE}/accounts", headers=H, json={
        "username": "nasa",
        "interval_seconds": 60,
    })
    _show(r)

    # ─── List Accounts ────────────────────────────────────
    print("\n4️⃣  GET /accounts")
    r = httpx.get(f"{BASE}/accounts", headers=H)
    _show(r)

    # ─── Add Account with webhook ──────────────────────────
    print("\n5️⃣  POST /accounts  (إضافة @elonmusk مع Webhook)")
    r = httpx.post(f"{BASE}/accounts", headers=H, json={
        "username": "elonmusk",
        "interval_seconds": 30,
        "webhook_url": "https://webhook.site/test-x-monitor",
    })
    _show(r)

    # ─── Force Check ──────────────────────────────────────
    print("\n6️⃣  POST /accounts/nasa/check  (فحص فوري)")
    r = httpx.post(f"{BASE}/accounts/nasa/check", headers=H)
    _show(r)

    # ─── Get Posts ────────────────────────────────────────
    print("\n7️⃣  GET /posts?limit=5")
    r = httpx.get(f"{BASE}/posts?limit=5", headers=H)
    _show(r)

    # ─── Register Webhook ─────────────────────────────────
    print("\n8️⃣  POST /webhooks  (تسجيل Webhook)")
    r = httpx.post(f"{BASE}/webhooks", headers=H, json={
        "url":    "https://webhook.site/your-unique-url",
        "secret": "my-secret-key",
        "events": ["new_post"],
    })
    _show(r)

    # ─── Test Webhook ─────────────────────────────────────
    print("\n9️⃣  POST /webhooks/test  (اختبار Webhook)")
    r = httpx.post(f"{BASE}/webhooks/test", headers=H, json={
        "url": "https://webhook.site/your-unique-url",
    })
    _show(r)

    # ─── List Webhooks ────────────────────────────────────
    print("\n🔟  GET /webhooks")
    r = httpx.get(f"{BASE}/webhooks", headers=H)
    _show(r)

    # ─── Pause Account ────────────────────────────────────
    print("\n1️⃣1️⃣  PATCH /accounts/nasa/pause")
    r = httpx.patch(f"{BASE}/accounts/nasa/pause", headers=H)
    _show(r)

    print("\n✅ انتهى الاختبار")


def _show(r: httpx.Response):
    print(f"   كود: {r.status_code}")
    try:
        data = r.json()
        print("   بيانات:", json.dumps(data, ensure_ascii=False, indent=4)[:500])
    except Exception:
        print("   نص:", r.text[:300])


if __name__ == "__main__":
    main()
