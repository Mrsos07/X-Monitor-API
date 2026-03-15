import asyncio
import sys
from playwright.async_api import async_playwright

configs = [
    {
        "name": "Test 1 — الأبسط",
        "args": ["--no-sandbox", "--disable-gpu"]
    },
    {
        "name": "Test 2 — مع SwiftShader",
        "args": ["--no-sandbox", "--disable-gpu",
                 "--use-gl=swiftshader",
                 "--use-angle=swiftshader-webgl"]
    },
    {
        "name": "Test 3 — مع user-data-dir",
        "args": ["--no-sandbox", "--disable-gpu",
                 "--user-data-dir=C:\\playwright-data"]
    },
    {
        "name": "Test 4 — headless=new",
        "args": ["--no-sandbox", "--disable-gpu",
                 "--headless=new"]
    },
    {
        "name": "Test 5 — بدون أي فلاجات",
        "args": []
    },
]

async def run_test(name, args, headless=True):
    print(f"\n{'='*50}")
    print(f"🧪 {name}")
    print(f"   headless={headless}, args={args}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=args,
                timeout=10000
            )
            context = await browser.new_context()
            page    = await context.new_page()

            # تصفح بسيط
            await page.goto("about:blank", timeout=8000)
            title = await page.title()
            await browser.close()
            print(f"   ✅ نجح! title='{title}'")
            return True
    except Exception as e:
        print(f"   ❌ فشل: {str(e)[:120]}")
        return False

async def main():
    print("=" * 50)
    print("🔍 تشخيص Playwright على Windows Server")
    print("=" * 50)

    for cfg in configs:
        ok = await run_test(cfg["name"], cfg["args"])
        if ok:
            print(f"\n🎯 الإعداد الناجح: {cfg['name']}")
            print(f"   args = {cfg['args']}")
            print("\nاستخدم هذه الـ args في browser.py ✅")
            break
    else:
        print("\n❌ كل الإعدادات فشلت!")
        print("🔧 جرّب الحلول التالية:")
        print("   1. winget install Microsoft.VCRedist.2015+.x64")
        print("   2. Add-MpPreference -ExclusionPath $env:LOCALAPPDATA\\ms-playwright")
        print("   3. تثبيت Google Chrome: winget install Google.Chrome")

asyncio.run(main())
