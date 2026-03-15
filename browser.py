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
_lock       = asyncio.Lock()


# ─────────────────────────────────────────────────────────────
#  تهيئة المتصفح
# ─────────────────────────────────────────────────────────────

async def init_browser():
    global _playwright, _browser, _context

    if _context is not None:
        return

    logger.info("🚀 تشغيل المتصفح ...")
    _playwright = await async_playwright().start()
    _browser    = await _playwright.chromium.launch(
        headless=settings.BROWSER_HEADLESS,
        args=[
            "--no-sandbox",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-extensions",
        ]
    )

    cookies  = _load_cookies()
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
        logger.warning("⚠️  لا يوجد ملف كوكيز — سيعمل بدون تسجيل دخول")
        _context = await _browser.new_context(**_ctx_opts)

    # ✅ حجب الموارد الثقيلة فقط — مع السماح لصور التغريدات وفيديوهاتها
    async def _smart_block(route, request):
        url = request.url
        # حجب الخطوط والأيقونات فقط
        if any(url.endswith(ext) for ext in [
            ".woff", ".woff2", ".ttf", ".eot",
            ".ico", ".svg"
        ]):
            await route.abort()
        # حجب الإعلانات
        elif any(domain in url for domain in [
            "ads-twitter.com", "doubleclick.net",
            "google-analytics.com", "googletagmanager.com"
        ]):
            await route.abort()
        else:
            await route.continue_()

    await _context.route("**/*", _smart_block)

    logger.success("✅ المتصفح جاهز")


# ─────────────────────────────────────────────────────────────
#  تحميل الكوكيز
# ─────────────────────────────────────────────────────────────

def _load_cookies() -> List[Dict]:
    raw = None

    # أولاً: من متغير البيئة
    if settings.COOKIES_JSON:
        try:
            raw = json.loads(settings.COOKIES_JSON)
            logger.info("🍪 تحميل الكوكيز من متغير البيئة COOKIES_JSON")
        except Exception as e:
            logger.error(f"خطأ في قراءة COOKIES_JSON: {e}")

    # ثانياً: من الملف
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
        if isinstance(raw, list):
            cookies = []
            for c in raw:
                cookie: Dict = {
                    "name":  c.get("name",   c.get("Name",   "")),
                    "value": c.get("value",  c.get("Value",  "")),
                    "domain": c.get("domain", c.get("Domain", ".x.com")),
                    "path":  c.get("path",   c.get("Path",   "/")),
                }
                ss = c.get("sameSite", c.get("samesite", "None"))
                cookie["sameSite"]  = ss if ss in ("Strict","Lax","None") else "None"
                cookie["secure"]    = bool(c.get("secure",   c.get("Secure",   True)))
                cookie["httpOnly"]  = bool(c.get("httpOnly", c.get("HttpOnly", False)))
                exp = c.get("expirationDate", c.get("expires", c.get("Expires")))
                if exp and isinstance(exp, (int, float)) and exp > 0:
                    cookie["expires"] = int(exp)
                if not cookie["domain"].startswith("."):
                    cookie["domain"] = "." + cookie["domain"].lstrip(".")
                cookie["domain"] = cookie["domain"].replace(".twitter.com", ".x.com")
                cookies.append(cookie)
            return cookies
    except Exception as e:
        logger.error(f"خطأ في معالجة الكوكيز: {e}")
    return []


# ─────────────────────────────────────────────────────────────
#  إغلاق وإعادة تشغيل المتصفح
# ─────────────────────────────────────────────────────────────

async def close_browser():
    global _playwright, _browser, _context
    try:
        if _context:  await _context.close()
    except Exception: pass
    _context = None
    try:
        if _browser:  await _browser.close()
    except Exception: pass
    _browser = None
    try:
        if _playwright: await _playwright.stop()
    except Exception: pass
    _playwright = None
    logger.info("🛑 المتصفح أُغلق")


async def restart_browser():
    logger.warning("🔄 إعادة تشغيل المتصفح ...")
    await close_browser()
    await asyncio.sleep(2)
    await init_browser()
    logger.success("✅ المتصفح أُعيد تشغيله بنجاح")


# ─────────────────────────────────────────────────────────────
#  جلب تغريدات حساب واحد
# ─────────────────────────────────────────────────────────────

async def fetch_user_posts(username: str,
                            max_posts: int = 10) -> List[Dict]:
    global _context

    if _context is None:
        await init_browser()

    for attempt in range(2):
        async with _lock:
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

                # ✅ انتظر تحميل الصور والفيديو
                await asyncio.sleep(2)

                posts = await page.evaluate(
                    _EXTRACT_JS, {"username": username, "max": max_posts}
                )
                logger.info(f"✅ @{username}: جُلبت {len(posts)} تغريدة")
                return posts

            except Exception as e:
                err = str(e)
                logger.error(f"❌ خطأ أثناء جلب @{username}: {err}")
                if attempt == 0 and ("closed" in err or "Target" in err):
                    logger.warning("🔄 المتصفح انهار، جاري إعادة التشغيل...")
                    await page.close()
                    await restart_browser()
                    continue
                return []
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

    return []


# ─────────────────────────────────────────────────────────────
#  التعامل مع جدار تسجيل الدخول
# ─────────────────────────────────────────────────────────────

async def _handle_login_wall(page: Page):
    try:
        close_btn = page.locator(
            '[data-testid="xMigrationBottomBar"] button')
        if await close_btn.count() > 0:
            await close_btn.first.click()
            await asyncio.sleep(0.5)
    except Exception:
        pass
    try:
        modal = page.locator(
            '[data-testid="sheetDialog"] button[aria-label="Close"]')
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

  for (let i = 0; i < Math.min(tweets.length, max * 3); i++) {
    const t = tweets[i];
    try {

      // ─── ❌ تجاهل التغريدات المثبتة والريتويت ────────────
      const socialCtx = t.querySelector('[data-testid="socialContext"]');
      if (socialCtx) {
        const labelText = socialCtx.innerText || '';
        if (
          labelText.includes('Pinned')    ||
          labelText.includes('مثبّت')     ||
          labelText.includes('مثبت')      ||
          labelText.includes('reposted')  ||
          labelText.includes('Retweeted') ||
          labelText.includes('أعاد')      ||
          labelText.includes('رتويت')
        ) {
          continue;
        }
      }

      // ─── ❌ تجاهل الريتويت عبر اسم المستخدم ─────────────
      const tweetAuthorEl = t.querySelector(
        '[data-testid="User-Name"] a[href^="/"]'
      );
      if (tweetAuthorEl) {
        const authorHref = tweetAuthorEl.getAttribute('href') || '';
        const authorName = authorHref.replace('/', '').toLowerCase();
        if (authorName && authorName !== username.toLowerCase()) {
          continue;
        }
      }

      // ─── ✅ استخراج بيانات التغريدة ───────────────────────

      const textEl = t.querySelector('[data-testid="tweetText"]');
      const text   = textEl ? textEl.innerText.trim() : '';

      const linkEl  = t.querySelector('a[href*="/status/"]');
      const href    = linkEl ? linkEl.getAttribute('href') : '';
      const tweetId = href.match(/\\/status\\/(\\d+)/)?.[1] || '';
      const tweetUrl = tweetId ? `https://x.com${href}` : '';

      const timeEl    = t.querySelector('time');
      const createdAt = timeEl ? timeEl.getAttribute('datetime') : null;

      const getCount = (testId) => {
        const el = t.querySelector(`[data-testid="${testId}"]`);
        if (!el) return 0;
        const txt = el.innerText.replace(/[^0-9KMB.]/gi, '');
        if (!txt) return 0;
        const n = parseFloat(txt);
        if (txt.toUpperCase().includes('K')) return Math.round(n * 1000);
        if (txt.toUpperCase().includes('M')) return Math.round(n * 1000000);
        return Math.round(n);
      };

      const likes    = getCount('like');
      const retweets = getCount('retweet');
      const replies  = getCount('reply');

      const viewsEl = t.querySelector(
        '[aria-label*="Views"], [aria-label*="views"]'
      );
      let views = 0;
      if (viewsEl) {
        const m = viewsEl.getAttribute('aria-label').match(/([\\d,]+)/);
        if (m) views = parseInt(m[1].replace(/,/g, ''));
      }

      // ─── ✅ استخراج الميديا (صور + فيديو) ────────────────

      const mediaUrls = [];

      // 1️⃣ صور التغريدة من pbs.twimg.com
      t.querySelectorAll('img[src*="pbs.twimg.com/media"]').forEach(img => {
        let src = img.src || img.getAttribute('src') || '';
        // جلب أعلى جودة
        if (src) {
          src = src.replace(/&name=\\w+/, '&name=large');
          if (!mediaUrls.includes(src)) mediaUrls.push(src);
        }
      });

      // 2️⃣ الفيديو — عبر poster أو data-testid
      t.querySelectorAll('video').forEach(video => {
        // رابط الـ poster (صورة مصغرة للفيديو)
        const poster = video.getAttribute('poster') || '';
        if (poster && poster.includes('twimg.com') && !mediaUrls.includes(poster)) {
          mediaUrls.push(poster);
        }
        // رابط الـ src المباشر
        const vsrc = video.src || video.getAttribute('src') || '';
        if (vsrc && !mediaUrls.includes(vsrc)) {
          mediaUrls.push(vsrc);
        }
        // source داخل video
        video.querySelectorAll('source').forEach(s => {
          const ssrc = s.src || s.getAttribute('src') || '';
          if (ssrc && !mediaUrls.includes(ssrc)) mediaUrls.push(ssrc);
        });
      });

      // 3️⃣ GIF — مشابه للفيديو في X
      t.querySelectorAll('[data-testid="tweetPhoto"] img').forEach(img => {
        const src = img.src || img.getAttribute('src') || '';
        if (src && src.includes('twimg.com') && !mediaUrls.includes(src)) {
          mediaUrls.push(src);
        }
      });

      // ─── نوع الميديا ──────────────────────────────────────
      let mediaType = 'none';
      if (t.querySelector('video'))                           mediaType = 'video';
      else if (t.querySelector('img[src*="pbs.twimg.com"]')) mediaType = 'image';

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
          media_type: mediaType,
          tweet_url:  tweetUrl,
        });
      }

      if (results.length >= max) break;

    } catch(e) { /* تجاهل أخطاء التغريدة الواحدة */ }
  }
  return results;
}
"""
