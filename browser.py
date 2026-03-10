# ============================================================
#  X-Monitor  — browser.py
#  محرك Playwright  — تسجيل الدخول بالكوكيز + جلب التغريدات
# ============================================================

import asyncio
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from loguru import logger
from playwright.async_api import (
    async_playwright, BrowserContext,
    Page, TimeoutError as PWTimeout
)
from config import settings

# ─────────────────────────────────────────────────────────────
#  المتغيرات العالمية المشتركة
# ─────────────────────────────────────────────────────────────

_playwright = None
_browser    = None
_context: Optional[BrowserContext] = None
_lock       = asyncio.Lock()          # منع التزامن على نفس الصفحة


# ─────────────────────────────────────────────────────────────
#  تهيئة المتصفح
# ─────────────────────────────────────────────────────────────

async def init_browser():
    global _playwright, _browser, _context

    if _context is not None:
        return  # مُشغَّل بالفعل

    logger.info("🚀 تشغيل المتصفح ...")
    _playwright = await async_playwright().start()
    _browser    = await _playwright.chromium.launch(
        headless=settings.BROWSER_HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--disable-software-rasterizer",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-component-update",
            "--no-first-run",
            "--no-zygote",
            "--single-process",
            "--js-flags=--max-old-space-size=128",
            "--renderer-process-limit=1",
            "--memory-pressure-off",
        ]
    )

    cookies = _load_cookies()

    _ctx_opts = dict(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        viewport={"width": 800, "height": 600},
        locale="en-US",
    )

    if cookies:
        logger.info(f"🍪 تحميل {len(cookies)} كوكيز من {settings.COOKIES_FILE}")
        _context = await _browser.new_context(**_ctx_opts)
        await _context.add_cookies(cookies)
    else:
        logger.warning("⚠️  لا يوجد ملف كوكيز — سيعمل بدون تسجيل دخول (محدودية)")
        _context = await _browser.new_context(**_ctx_opts)

    # حظر الصور والوسائط لتقليل استهلاك الذاكرة
    await _context.route("**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2,ttf}", lambda route: route.abort())
    await _context.route("**/{video,media}/**", lambda route: route.abort())

    logger.success("✅ المتصفح جاهز")


def _load_cookies() -> List[Dict]:
    raw = None

    # أولاً: محاولة التحميل من متغير البيئة (مناسب لـ Render)
    if settings.COOKIES_JSON:
        try:
            raw = json.loads(settings.COOKIES_JSON)
            logger.info("🍪 تحميل الكوكيز من متغير البيئة COOKIES_JSON")
        except Exception as e:
            logger.error(f"خطأ في قراءة COOKIES_JSON: {e}")

    # ثانياً: محاولة التحميل من الملف
    if raw is None:
        path = settings.COOKIES_FILE
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"خطأ في قراءة ملف الكوكيز: {e}")
            return []

    try:
        # دعم صيغة Netscape / EditThisCookie / JSON مباشر
        if isinstance(raw, list):
            cookies = []
            for c in raw:
                # تحويل اسم الحقول إن لزم
                cookie: Dict = {
                    "name":  c.get("name", c.get("Name", "")),
                    "value": c.get("value", c.get("Value", "")),
                    "domain": c.get("domain", c.get("Domain", ".x.com")),
                    "path":  c.get("path", c.get("Path", "/")),
                }
                # sameSite
                ss = c.get("sameSite", c.get("samesite", "None"))
                cookie["sameSite"] = ss if ss in ("Strict", "Lax", "None") else "None"
                # secure
                cookie["secure"] = bool(c.get("secure", c.get("Secure", True)))
                # httpOnly
                cookie["httpOnly"] = bool(c.get("httpOnly", c.get("HttpOnly", False)))
                # expiry
                exp = c.get("expirationDate", c.get("expires", c.get("Expires")))
                if exp and isinstance(exp, (int, float)) and exp > 0:
                    cookie["expires"] = int(exp)
                # تصحيح domain
                if not cookie["domain"].startswith("."):
                    cookie["domain"] = "." + cookie["domain"].lstrip(".")
                cookie["domain"] = cookie["domain"].replace(".twitter.com", ".x.com")
                cookies.append(cookie)
            return cookies
    except Exception as e:
        logger.error(f"خطأ في قراءة الكوكيز: {e}")
    return []


async def close_browser():
    global _playwright, _browser, _context
    if _context:
        await _context.close()
        _context = None
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("🛑 المتصفح أُغلق")


# ─────────────────────────────────────────────────────────────
#  جلب تغريدات حساب واحد
# ─────────────────────────────────────────────────────────────

async def fetch_user_posts(username: str,
                            max_posts: int = 10) -> List[Dict]:
    """
    يفتح صفحة x.com/{username} ويجلب أحدث التغريدات.
    يُعيد قائمة من القواميس.
    """
    if _context is None:
        await init_browser()

    async with _lock:  # طلب واحد في المرة
        page: Page = await _context.new_page()
        posts = []
        try:
            url = f"https://x.com/{username}"
            logger.debug(f"📡 فتح: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            await _handle_login_wall(page)

            # انتظر ظهور التغريدات
            try:
                await page.wait_for_selector(
                    '[data-testid="tweet"]', timeout=20_000)
            except PWTimeout:
                logger.warning(f"⏰ لم تظهر التغريدات لـ @{username}")
                return []

            # اجمع البيانات بـ JavaScript
            posts = await page.evaluate(
                _EXTRACT_JS, {"username": username, "max": max_posts}
            )
            logger.info(f"✅ @{username}: جُلبت {len(posts)} تغريدة")

        except Exception as e:
            logger.error(f"❌ خطأ أثناء جلب @{username}: {e}")
        finally:
            await page.close()

    return posts


# ─────────────────────────────────────────────────────────────
#  التعامل مع جدار تسجيل الدخول
# ─────────────────────────────────────────────────────────────

async def _handle_login_wall(page: Page):
    """إن ظهر شاشة الدخول نُغلقها"""
    try:
        close_btn = page.locator('[data-testid="xMigrationBottomBar"] button')
        if await close_btn.count() > 0:
            await close_btn.first.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass

    # كذلك منع الـ modal
    try:
        modal = page.locator('[data-testid="sheetDialog"] button[aria-label="Close"]')
        if await modal.count() > 0:
            await modal.first.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
#  JavaScript لاستخراج التغريدات من DOM
# ─────────────────────────────────────────────────────────────

_EXTRACT_JS = """
async (args) => {
  const { username, max } = args;
  const tweets = document.querySelectorAll('[data-testid="tweet"]');
  const results = [];

  for (let i = 0; i < Math.min(tweets.length, max); i++) {
    const t = tweets[i];
    try {
      // --- النص ---
      const textEl = t.querySelector('[data-testid="tweetText"]');
      const text = textEl ? textEl.innerText.trim() : '';

      // --- الرابط والمعرّف ---
      const linkEl = t.querySelector('a[href*="/status/"]');
      const href   = linkEl ? linkEl.getAttribute('href') : '';
      const tweetId = href.match(/\\/status\\/(\\d+)/)?.[1] || '';
      const tweetUrl = tweetId ? `https://x.com${href}` : '';

      // --- الوقت ---
      const timeEl = t.querySelector('time');
      const createdAt = timeEl ? timeEl.getAttribute('datetime') : null;

      // --- الإحصاءات ---
      const getCount = (testId) => {
        const el = t.querySelector(`[data-testid="${testId}"]`);
        if (!el) return 0;
        const txt = el.innerText.replace(/[^0-9KMB.]/gi,'');
        if (!txt) return 0;
        const n = parseFloat(txt);
        if (txt.toUpperCase().includes('K')) return Math.round(n * 1000);
        if (txt.toUpperCase().includes('M')) return Math.round(n * 1000000);
        return Math.round(n);
      };

      const likes    = getCount('like');
      const retweets = getCount('retweet');
      const replies  = getCount('reply');
      
      // views
      const viewsEl = t.querySelector('[aria-label*="Views"], [aria-label*="views"]');
      let views = 0;
      if (viewsEl) {
        const m = viewsEl.getAttribute('aria-label').match(/([\\d,]+)/);
        if (m) views = parseInt(m[1].replace(/,/g,''));
      }

      // --- الوسائط ---
      const mediaEls = t.querySelectorAll('img[src*="pbs.twimg.com/media"], video source');
      const mediaUrls = Array.from(mediaEls).map(el =>
        el.src || el.getAttribute('src') || ''
      ).filter(Boolean);

      if (tweetId) {
        results.push({
          tweet_id:   tweetId,
          username:   username,
          text:       text,
          created_at: createdAt,
          likes:      likes,
          retweets:   retweets,
          replies:    replies,
          views:      views,
          media_urls: mediaUrls,
          tweet_url:  tweetUrl,
        });
      }
    } catch(e) { /* تجاهل أخطاء التغريدة الواحدة */ }
  }
  return results;
}
"""
