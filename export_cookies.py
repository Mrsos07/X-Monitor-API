#!/usr/bin/env python3
# ============================================================
#  X-Monitor  — export_cookies.py
#  أداة مساعدة: تسجيل الدخول مرة واحدة وحفظ الكوكيز
# ============================================================

"""
الاستخدام:
    python export_cookies.py

سيفتح المتصفح بواجهة رسومية لتسجيل الدخول يدوياً.
بعد الدخول اضغط Enter وسيُحفظ cookies.json تلقائياً.
"""

import asyncio
import json
from playwright.async_api import async_playwright


async def main():
    print("🚀 فتح المتصفح لتسجيل الدخول إلى X ...")
    print("━" * 50)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.goto("https://x.com/login")

        print("👤 سجّل دخولك في نافذة المتصفح التي فُتحت ...")
        print("   بعد الدخول الناجح اضغط ENTER هنا ↓")
        input()

        # تحقق من الدخول
        url = page.url
        if "home" in url or "x.com" in url and "login" not in url:
            cookies = await context.cookies()
            with open("cookies.json", "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
            print(f"✅ تم حفظ {len(cookies)} كوكيز في cookies.json")
            print("🎉 يمكنك الآن تشغيل النظام: python main.py")
        else:
            print("⚠️  يبدو أن تسجيل الدخول لم يكتمل. حاول مجدداً.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
