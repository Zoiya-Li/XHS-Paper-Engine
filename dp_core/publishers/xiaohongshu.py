"""
Xiaohongshu Publisher - Based on Playwright browser automation

Features:
- Cookie login state management (save/load)
- QR code scan login
- Image upload
- Note publishing (image-text)
- Traffic data acquisition (likes, comments, favorites)

Dependencies:
pip install playwright
playwright install chromium

Reference implementation: xiaohongshu-mcp (https://github.com/9cxndy/xiaohongshu-mcp)
"""

import shutil
import asyncio
import requests
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


# Canonical storage dir. We always read AND write here so a saved login is found
# again next run. (The legacy ~/.dailypaper dir is only consulted for one-time
# migration below.)
STORAGE_DIR = Path.home() / ".xhs-paper-engine"
LEGACY_STORAGE_DIR = Path.home() / ".dailypaper"


def _resolve_storage_path(relative_path: str) -> Path:
    """Resolve a path under the canonical storage dir (deterministic).

    Earlier this returned whichever of the new/legacy dirs happened to *exist*,
    which split saves across two directories — the login tool could save to one
    dir while the publish tool read the other, forcing a re-scan every run. Now
    the path is always canonical; the legacy copy is migrated once in
    ``_cookies_path`` so a prior login keeps working.
    """
    return STORAGE_DIR / relative_path


def _cookies_path() -> Path:
    """Canonical session-state file, migrating a legacy copy once if present."""
    canonical = STORAGE_DIR / "xiaohongshu_cookies.json"
    legacy = LEGACY_STORAGE_DIR / "xiaohongshu_cookies.json"
    if not canonical.exists() and legacy.exists():
        try:
            canonical.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy, canonical)
            print(f"↪️  Migrated saved login from {legacy} to {canonical}")
        except Exception:
            pass
    return canonical


# ===========================================================================
# Xiaohongshu creator-backend selectors
#
# ⚠️ FRAGILITY WARNING: every selector below targets the Xiaohongshu web
# frontend (creator.xiaohongshu.com). Xiaohongshu can change its markup at any
# time, and when it does these selectors stop matching and publishing breaks.
# This is inherent to UI automation — there is no stable public API here.
#
# If publishing suddenly fails ("element not found" + a debug screenshot under
# ~/.xhs-paper-engine/debug/), inspect the page, update the lists below, and
# bump SELECTORS_LAST_VERIFIED. Order matters: most specific / most reliable
# selector first.
# ===========================================================================
SELECTORS_LAST_VERIFIED = "2026-05-28 (login/upload/title/content/tags confirmed working; publish button is inside a closed Shadow DOM of <xhs-publish-btn>, intercepted via attachShadow override to open mode, then clicked via xhs-publish-btn >> button.bg-red)"

# Switch the publish page from "video" to "image+text" mode
IMAGE_TAB_SELECTORS = [
    'text=上传图文',
    'div:has-text("上传图文")',
    '[class*="tab"]:has-text("图文")',
    '[class*="tab"]:has-text("上传图文")',
    'span:has-text("上传图文")',
]
# The hidden <input type=file> that accepts the images
UPLOAD_INPUT_SELECTORS = [
    '.upload-input',
    'input[type="file"]',
    'input[accept*="image"]',
    '.upload-input input',
    '[class*="upload"] input[type="file"]',
]
# Already-uploaded image thumbnails (used to count upload progress)
UPLOADED_IMAGE_SELECTORS = [
    '[class*="image-item"]',
    '[class*="upload-item"]',
    '[class*="preview"] img',
    '.image-list img',
    '[class*="publish-image"]',
]
TITLE_INPUT_SELECTORS = [
    'div.d-input input',
    'input[placeholder*="标题"]',
    '[class*="title"] input',
    '#title',
]
CONTENT_EDITOR_SELECTORS = [
    'div.ql-editor',
    '[contenteditable="true"]',
    '[placeholder*="正文"]',
    '[class*="content"] textarea',
    '#content',
]
VISIBILITY_DROPDOWN_SELECTORS = [
    'text=公开可见',
    ':has-text("公开可见")',
    '[class*="visible"] >> text=公开',
    'div:has-text("可见范围") >> text=公开可见',
]
PRIVATE_OPTION_SELECTORS = [
    'text=仅自己可见',
    ':has-text("仅自己可见")',
    '[class*="option"]:has-text("仅自己")',
]
DRAFT_BUTTON_SELECTORS = [
    'text=暂存离开',
    ':has-text("暂存离开")',
    'button:has-text("暂存离开")',
    'div:has-text("暂存离开")',
    'text=暂存',
    'text=存草稿',
    ':has-text("暂存")',
    ':has-text("存草稿")',
]
CONFIRM_BUTTON_SELECTORS = [
    'button:has-text("确认")',
    'button:has-text("确定")',
    'button:has-text("离开")',
    '[class*="confirm"]',
]
# Inject before any page loads to force closed shadow roots open so we can
# reach the real <button class="bg-red"> inside <xhs-publish-btn>.
INTERCEPT_SHADOW_SCRIPT = """
(() => {
    const original = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function(init) {
        return original.call(this, {...init, mode: 'open'});
    };
})();
"""

PUBLISH_BUTTON_SELECTORS = [
    # 2026-05-28: <xhs-publish-btn> uses a closed Shadow DOM. We force it open
    # via INTERCEPT_SHADOW_SCRIPT so Playwright can pierce inside. The real
    # publish button is <button class="ce-btn bg-red"> inside the shadow root.
    'xhs-publish-btn >> button.bg-red',
    'xhs-publish-btn >> button:has-text("发布")',
    # Fallbacks (without shadow piercing — may match sidebar nav or other elements)
    'xhs-publish-btn >> text=发布',
    'xhs-publish-btn[submit-text="发布"]',
    'xhs-publish-btn',
    'text="发布"',
    'div.submit div.d-button-content',
    'div.submit button',
    '.footer button:has-text("发布")',
    '[class*="publish"] button',
    '[class*="submit"]',
    'button:has-text("发布")',
    'div:has-text("发布"):not(:has-text("笔记"))',
]
SUCCESS_INDICATOR_SELECTORS = [
    '[class*="success"]',
    '[class*="toast"]:has-text("成功")',
    '[class*="toast"]:has-text("发布")',
    # 2026-05-28: Xiaohongshu shows a modal dialog with "发布成功" after publish
    'text="发布成功"',
    '[class*="el-message-box"]:has-text("发布成功")',
    '[class*="dialog"]:has-text("发布成功")',
]
# Presence of any of these on the creator home implies a logged-in session
LOGIN_INDICATOR_SELECTORS = '.user-info, .user-avatar, [class*="avatar"]'


class XiaohongshuPublisher:
    """Xiaohongshu Publisher"""

    # Xiaohongshu Creator Center URL
    CREATOR_URL = "https://creator.xiaohongshu.com"
    # Authenticated dashboard. The bare root redirects to /login even when logged
    # in, so login checks must target this page instead.
    CREATOR_HOME_URL = "https://creator.xiaohongshu.com/new/home"
    LOGIN_URL = "https://creator.xiaohongshu.com/login"
    # Directly use target=image parameter to enter image-text upload page
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image"

    def __init__(self, cookies_path: Optional[str] = None, headless: bool = False):
        """
        Initialize publisher

        Args:
            cookies_path: Cookie file save path
            headless: Whether to run in headless mode (recommend False for first login)
        """
        self.cookies_path = Path(cookies_path) if cookies_path else _cookies_path()
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    async def _ensure_playwright(self):
        """Ensure Playwright is installed"""
        try:
            from playwright.async_api import async_playwright
            return async_playwright
        except ImportError:
            raise ImportError(
                "Please install Playwright first:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

    async def start(self):
        """Start browser"""
        async_playwright = await self._ensure_playwright()
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=['--disable-blink-features=AutomationControlled']
        )

        # Create context, restoring full session state (cookies + localStorage)
        # if we have it. Xiaohongshu keeps part of the auth in localStorage, so
        # cookies alone are not enough — we persist Playwright's storage_state.
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ctx_kwargs = {'viewport': {'width': 1280, 'height': 800}, 'user_agent': ua}
        if self.cookies_path.exists():
            try:
                self.context = await self.browser.new_context(storage_state=str(self.cookies_path), **ctx_kwargs)
                print(f"✅ Session state loaded: {self.cookies_path}")
            except Exception as e:
                print(f"⚠️ Failed to load session state ({e}); starting fresh")
                self.context = await self.browser.new_context(**ctx_kwargs)
        else:
            self.context = await self.browser.new_context(**ctx_kwargs)

        # Force closed Shadow DOMs to open so we can pierce <xhs-publish-btn>
        await self.context.add_init_script(INTERCEPT_SHADOW_SCRIPT)

        self.page = await self.context.new_page()

    async def stop(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _save_debug_screenshot(self, name: str) -> str:
        """Save a timestamped debug screenshot and return its path (best effort)."""
        try:
            debug_dir = _resolve_storage_path("debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = debug_dir / f"{name}_{ts}.png"
            await self.page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return ""

    async def _query_first_visible(self, selectors):
        """Return the first matching visible element handle, or None."""
        for selector in selectors:
            try:
                elem = await self.page.query_selector(selector)
                if elem and await elem.is_visible():
                    return elem
            except Exception:
                continue
        return None

    async def _save_cookies(self):
        """Persist the full session state (cookies + localStorage)."""
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.storage_state(path=str(self.cookies_path))
        print(f"✅ Session saved to: {self.cookies_path}")

    async def check_login(self) -> bool:
        """
        Check login status

        Returns:
            Whether logged in
        """
        try:
            # Navigate to the authenticated dashboard (NOT the bare root, which
            # redirects to /login even when logged in). If our session is valid we
            # stay on /new/home; otherwise we get bounced to /login.
            try:
                await self.page.goto(self.CREATOR_HOME_URL, wait_until='domcontentloaded', timeout=60000)
            except Exception:
                # A client-side redirect can abort the navigation (net::ERR_ABORTED).
                # The page still lands somewhere — inspect the resulting URL below.
                pass

            # CRITICAL: a guest is redirected to /login by a client-side (SPA)
            # check that takes ~5s. The old code waited only 3s, saw the pre-
            # redirect /new/home URL, and reported a FALSE "logged in" — which
            # made the login flow skip the QR/save and left every run unauthed.
            # So POLL until the redirect settles instead of snapshotting once.
            deadline = asyncio.get_event_loop().time() + 15
            while asyncio.get_event_loop().time() < deadline:
                url = self.page.url
                if 'login' in url:
                    return False
                try:
                    indicator = await self.page.query_selector(LOGIN_INDICATOR_SELECTORS)
                    if indicator and await indicator.is_visible():
                        return True
                except Exception:
                    pass
                await asyncio.sleep(1)

            # Survived the whole window on the dashboard without being bounced to
            # /login → logged in. (A guest reliably hits /login within ~5s.)
            return 'login' not in self.page.url
        except Exception as e:
            print(f"⚠️ Error checking login status: {e}")
            return False

    async def login_with_qrcode(self, timeout: int = 180) -> bool:
        """
        QR code scan login.

        Detecting success is intentionally multi-signal because Xiaohongshu's
        login is a SPA: after a scan it may render the dashboard without changing
        the URL away from /login. We treat login as done if ANY of these hold:
          - the URL has left the /login route, or
          - a logged-in indicator (avatar/user-info) is visible, or
          - the QR code element has disappeared (consumed by a successful scan).
        Everything is wrapped so a closed/crashed page doesn't blow up the loop.

        Args:
            timeout: Seconds to wait for the scan.

        Returns:
            Whether login succeeded.
        """
        print("\n" + "="*60)
        print("📱 Xiaohongshu QR Code Login")
        print("="*60)

        # Already logged in with valid cookies? (one authoritative check up front)
        if await self.check_login():
            print("\n✅ Already logged in.")
            await self._save_cookies()
            return True

        # Show the QR ONCE and then poll the SAME page without navigating away —
        # navigating mid-scan invalidates the QR and forces a re-scan. A real scan
        # makes Xiaohongshu redirect this page off /login (or render an avatar).
        await self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(2)
        print("\n📷 Scan the QR code shown in the browser window with the Xiaohongshu APP")
        print(f"⏳ Waiting for login (timeout: {timeout}s)... (do not close the window)")

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            await asyncio.sleep(2)
            try:
                url = self.page.url
                left_login = "/login" not in url and "xiaohongshu.com" in url
                indicator = await self.page.query_selector(LOGIN_INDICATOR_SELECTORS)
                if left_login or indicator is not None:
                    await asyncio.sleep(2)  # let the redirect settle and cookies set
                    print("\n✅ Login detected, saving session...")
                    await self._save_cookies()
                    # Show a visible confirmation in the browser so the user knows the
                    # window closing is intentional, not a crash.
                    try:
                        await self.page.evaluate("""
                            const div = document.createElement('div');
                            div.innerHTML = '<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:99999;display:flex;align-items:center;justify-content:center;"><div style="background:#fff;padding:40px 60px;border-radius:16px;text-align:center;font-family:sans-serif;max-width:500px;"><h1 style="color:#ff2442;margin:0 0 16px;font-size:28px;">✅ 登录成功</h1><p style="font-size:18px;color:#333;line-height:1.6;margin:0;">Session 已保存，后续发布无需重新扫码。<br><br>此窗口将在 5 秒后自动关闭。</p></div></div>';
                            document.body.appendChild(div.firstElementChild);
                        """)
                    except Exception:
                        pass
                    print("   🪟 Browser will close in 5s (this is normal — session is saved).")
                    await asyncio.sleep(5)
                    return True
            except Exception as e:
                print(f"   (waiting… {type(e).__name__})")

        print("\n❌ Login timeout")
        return False

    def _calculate_title_width(self, title: str) -> int:
        """
        Calculate title width (Chinese/Japanese/Korean count as 2, English/numbers count as 1)
        Reference implementation from xiaohongshu-mcp
        """
        width = 0
        for char in title:
            # CJK character ranges
            if '\u4e00' <= char <= '\u9fff':  # Chinese
                width += 2
            elif '\u3040' <= char <= '\u30ff':  # Japanese
                width += 2
            elif '\uac00' <= char <= '\ud7af':  # Korean
                width += 2
            elif '\uff00' <= char <= '\uffef':  # Full-width characters
                width += 2
            else:
                width += 1
        return width

    async def _process_images(self, images: List[str]) -> List[str]:
        """
        Process images: support local paths and URLs
        Reference implementation from xiaohongshu-mcp's downloader
        """
        valid_images = []
        temp_dir = _resolve_storage_path("xiaohongshu_images")
        temp_dir.mkdir(parents=True, exist_ok=True)

        for img_path in images:
            # Check if it's a URL
            if img_path.startswith(('http://', 'https://')):
                print(f"   Downloading network image: {img_path[:50]}...")
                try:
                    response = requests.get(img_path, timeout=30)
                    response.raise_for_status()

                    # Extract filename from URL
                    file_name = img_path.split('/')[-1].split('?')[0]
                    if not file_name or '.' not in file_name:
                        file_name = f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"

                    # Save to temp directory
                    local_path = temp_dir / file_name
                    with open(local_path, 'wb') as f:
                        f.write(response.content)

                    valid_images.append(str(local_path.absolute()))
                    print(f"   ✅ Download successful: {file_name}")
                except Exception as e:
                    print(f"   ⚠️ Download failed: {e}")
            else:
                # Local file
                img_path = Path(img_path)
                if img_path.exists():
                    valid_images.append(str(img_path.absolute()))
                else:
                    print(f"   ⚠️ Image not found: {img_path}")

        return valid_images

    async def _wait_for_any_selector(self, selectors, timeout: int = 30):
        """Poll until any of ``selectors`` is present, or timeout.

        The publish page renders skeleton placeholders first and fills in the
        real upload UI a moment later, so a fixed sleep is unreliable on a slow
        load. Returns (selector, element) on success, or (None, None).
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            for sel in selectors:
                try:
                    el = await self.page.query_selector(sel)
                except Exception:
                    el = None
                if el:
                    return sel, el
            await asyncio.sleep(0.5)
        return None, None

    async def _dismiss_popups(self):
        """Close any open suggestion/topic dropdown overlaying the controls.

        Typing a #tag opens a topic-suggestion popup (a tippy dropdown). It sits
        on top of the visibility control and the publish button and intercepts
        their clicks — which made publishing scroll/retry forever and then fail.
        Pressing Escape closes it; best-effort.
        """
        try:
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _wait_for_upload_complete(self, expected_count: int, timeout: int = 120) -> int:
        """
        Wait for image upload to complete
        Reference implementation from xiaohongshu-mcp's waitForUploadComplete
        """
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            # Check number of uploaded images
            uploaded_count = await self._count_uploaded_images()

            # Check if there is uploading status
            uploading = await self.page.query_selector('[class*="uploading"], [class*="loading"]')

            if uploaded_count >= expected_count and not uploading:
                return uploaded_count

            await asyncio.sleep(1)

        return await self._count_uploaded_images()

    async def _count_uploaded_images(self) -> int:
        """Count number of uploaded images"""
        try:
            # Try multiple selectors to find uploaded images
            for selector in UPLOADED_IMAGE_SELECTORS:
                images = await self.page.query_selector_all(selector)
                if images:
                    return len(images)
            return 0
        except:
            return 0

    async def _input_tags(self, content_elem, tags: List[str]):
        """
        Input tags
        Reference implementation from xiaohongshu-mcp's inputTags
        Type #tag in content editor then press space
        """
        if not tags:
            return

        # Maximum 10 tags
        for tag in tags[:10]:
            try:
                # Add tag at end of content
                await content_elem.press('End')  # Move to end
                await content_elem.type(f' #{tag}')
                await asyncio.sleep(0.3)
                # Press space to confirm tag
                await content_elem.press('Space')
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"   ⚠️ Failed to add tag {tag}: {e}")

    async def publish(
        self,
        title: str,
        content: str,
        images: List[str],
        tags: Optional[List[str]] = None,
        location: Optional[str] = None,
        save_draft: bool = False,
        visibility: str = "public"  # public=publicly visible, private=only self visible
    ) -> Dict[str, Any]:
        """
        Publish Xiaohongshu note

        Args:
            title: Title (max 20 chars/40 width)
            content: Content text
            images: Image path list (min 1, max 18, supports URLs)
            tags: Topic tags (max 10)
            location: Location information
            save_draft: Whether to save as draft
            visibility: Visibility range - "public"(publicly visible) or "private"(only self visible)

        Returns:
            Publish result
        """
        result = {
            "success": False,
            "message": "",
            "title": title,
            "image_count": len(images)
        }

        # Validate title length (reference xiaohongshu-mcp)
        title_width = self._calculate_title_width(title)
        if title_width > 40:
            # Truncate title
            truncated = ""
            width = 0
            for char in title:
                char_width = 2 if '\u4e00' <= char <= '\u9fff' else 1
                if width + char_width > 40:
                    break
                truncated += char
                width += char_width
            title = truncated
            print(f"⚠️ Title too long, truncated to: {title}")

        # Validate parameters
        if not images:
            result["message"] = "At least 1 image required"
            return result

        if len(images) > 18:
            result["message"] = "Maximum 18 images supported"
            return result

        # Process images (supports URL download)
        valid_images = await self._process_images(images)
        if not valid_images:
            result["message"] = "No valid image files"
            return result

        result["image_count"] = len(valid_images)

        # Login is verified by the caller (publish_xiaohongshu tool) before we get
        # here. We deliberately don't re-check: a second /new/home navigation can
        # abort/flake and falsely report "not logged in". If the session really is
        # invalid, the publish page redirects to login and the upload-input check
        # below fails loudly with a screenshot.

        print(f"\n📝 Starting to publish Xiaohongshu note: {title}")
        print(f"   Valid images: {len(valid_images)}")

        try:
            # Enter publish page
            print("   Loading publish page...")
            await self.page.goto(self.PUBLISH_URL, wait_until='domcontentloaded', timeout=60000)

            # The page shows skeleton placeholders first, then renders the real
            # upload UI. Wait for that UI (the image tab or the file input) to
            # actually appear instead of guessing with a fixed sleep.
            print("   Waiting for the upload UI to render...")
            ready_sel, _ = await self._wait_for_any_selector(
                IMAGE_TAB_SELECTORS + UPLOAD_INPUT_SELECTORS, timeout=40
            )
            if ready_sel is None:
                shot = await self._save_debug_screenshot("xhs_publish_page_not_ready")
                result["message"] = (
                    "Publish page did not finish loading (upload UI never appeared). "
                    f"This is usually a slow network. Debug screenshot: {shot or 'n/a'}"
                )
                return result

            # Important: click "Upload Image-Text" tab (page defaults to "Upload Video")
            # Reference xiaohongshu-mcp: mustClickPublishTab(page, "上传图文")
            print("   Switching to image-text upload mode...")
            tab_clicked = False

            for selector in IMAGE_TAB_SELECTORS:
                try:
                    await self.page.click(selector, timeout=3000)
                    print("   ✅ Clicked image-text upload tab")
                    tab_clicked = True
                    await asyncio.sleep(2)
                    break
                except:
                    continue

            # Not fatal: the page may already default to image-text mode.
            if not tab_clicked:
                print("   ⚠️ Image-text upload tab not found; assuming already in image mode.")

            # Upload images
            # Reference xiaohongshu-mcp: uploadInput := pp.MustElement(".upload-input")
            print(f"📸 Uploading images ({len(valid_images)})...")

            # Find the file input (critical — without it we cannot publish).
            # Wait for it, since switching modes may re-render the panel.
            selector, upload_input = await self._wait_for_any_selector(
                UPLOAD_INPUT_SELECTORS, timeout=20
            )
            if upload_input:
                print(f"   Found upload input: {selector}")

            if not upload_input:
                # Hard failure: the page structure likely changed.
                shot = await self._save_debug_screenshot("xhs_upload_input_not_found")
                result["message"] = (
                    "Image upload input not found — Xiaohongshu's page markup likely "
                    f"changed. Update UPLOAD_INPUT_SELECTORS in publishers/xiaohongshu.py "
                    f"(selectors last verified: {SELECTORS_LAST_VERIFIED}). "
                    f"Debug screenshot: {shot or 'n/a'}"
                )
                return result

            # Batch upload images
            await upload_input.set_input_files(valid_images)
            print("   ✅ Images uploading...")

            # Wait for image upload to complete
            uploaded_count = await self._wait_for_upload_complete(len(valid_images))
            print(f"   ✅ Uploaded {uploaded_count}/{len(valid_images)} images")

            if uploaded_count == 0:
                shot = await self._save_debug_screenshot("xhs_upload_failed")
                result["message"] = (
                    "No images appear to have uploaded (the upload may have failed or the "
                    f"progress selectors changed). Debug screenshot: {shot or 'n/a'}"
                )
                return result

            # Wait for entering edit page
            await asyncio.sleep(3)

            # Input title
            # Reference xiaohongshu-mcp: titleElem := page.MustElement("div.d-input input")
            print(f"📝 Inputting title: {title}")
            title_filled = False
            for selector in TITLE_INPUT_SELECTORS:
                try:
                    title_input = await self.page.query_selector(selector)
                    if title_input:
                        await title_input.fill(title)
                        title_filled = True
                        break
                except:
                    continue

            # Not fatal (Xiaohongshu can derive a title), but warn loudly.
            if not title_filled:
                print("   ⚠️ Title input not found; publishing without an explicit title.")

            # Input content
            # Reference xiaohongshu-mcp: contentElem := getContentElement(page) -> "div.ql-editor"
            print(f"📝 Inputting content ({len(content)} chars)...")
            content_elem = None
            for selector in CONTENT_EDITOR_SELECTORS:
                try:
                    content_elem = await self.page.query_selector(selector)
                    if content_elem:
                        await content_elem.fill(content)
                        break
                except:
                    continue

            if not content_elem:
                # Hard failure: publishing an empty note is worse than failing loudly.
                shot = await self._save_debug_screenshot("xhs_content_editor_not_found")
                result["message"] = (
                    "Content editor not found — refusing to publish an empty note. "
                    "Xiaohongshu's markup likely changed; update CONTENT_EDITOR_SELECTORS "
                    f"in publishers/xiaohongshu.py (selectors last verified: "
                    f"{SELECTORS_LAST_VERIFIED}). Debug screenshot: {shot or 'n/a'}"
                )
                return result

            # Add topic tags
            # Reference xiaohongshu-mcp: inputTags(contentElem, tags)
            if tags and content_elem:
                print(f"🏷️ Adding tags: {tags}")
                await self._input_tags(content_elem, tags)
                # The last #tag leaves a topic-suggestion popup open, covering the
                # visibility control and publish button. Close it before going on.
                await self._dismiss_popups()

            # Wait for content filling to complete
            await asyncio.sleep(2)

            # Set visibility range (default to only self visible)
            if visibility == "private":
                print("🔒 Setting visibility: Only self visible")
                try:
                    # First open the "Visibility Range" dropdown
                    dropdown = await self._query_first_visible(VISIBILITY_DROPDOWN_SELECTORS)
                    if dropdown:
                        await dropdown.click(timeout=5000)
                        print("   ✅ Clicked visibility dropdown")
                        await asyncio.sleep(1)

                        # Then pick "Only self visible"
                        private_opt = await self._query_first_visible(PRIVATE_OPTION_SELECTORS)
                        if private_opt:
                            await private_opt.click(timeout=5000)
                            print("   ✅ Set to only self visible")
                            await asyncio.sleep(1)
                        else:
                            print("   ⚠️ 'Only self visible' option not found; visibility may stay public!")
                    else:
                        # This matters for privacy — warn prominently rather than silently.
                        print("   ⚠️ Visibility dropdown not found; the note may be PUBLIC. "
                              "Verify manually or update VISIBILITY_DROPDOWN_SELECTORS.")
                except Exception as e:
                    print(f"   ⚠️ Failed to set visibility (note may be PUBLIC): {e}")

            if save_draft:
                # Save draft
                print("💾 Saving draft...")

                # First screenshot to record current state
                debug_dir = _resolve_storage_path("debug")
                debug_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                await self.page.screenshot(path=str(debug_dir / f"xhs_before_save_{timestamp}.png"))
                print(f"   Debug screenshot: {debug_dir / f'xhs_before_save_{timestamp}.png'}")

                # Xiaohongshu Creator Center draft save button (text "暂存离开")
                draft_selectors = DRAFT_BUTTON_SELECTORS

                draft_clicked = False
                clicked_selector = None
                for selector in draft_selectors:
                    try:
                        # First check if element exists and is visible
                        elem = await self.page.query_selector(selector)
                        if elem:
                            is_visible = await elem.is_visible()
                            if is_visible:
                                await elem.click()
                                draft_clicked = True
                                clicked_selector = selector
                                print(f"   ✅ Clicked draft button: {selector}")
                                break
                    except Exception:
                        continue

                if draft_clicked:
                    await asyncio.sleep(2)

                    # Check if there is confirmation dialog
                    for confirm_sel in CONFIRM_BUTTON_SELECTORS:
                        try:
                            confirm_btn = await self.page.query_selector(confirm_sel)
                            if confirm_btn and await confirm_btn.is_visible():
                                await confirm_btn.click()
                                print(f"   ✅ Clicked confirm button: {confirm_sel}")
                                await asyncio.sleep(2)
                                break
                        except:
                            continue

                    # Screenshot after saving
                    await self.page.screenshot(path=str(debug_dir / f"xhs_after_save_{timestamp}.png"))
                    print(f"   Debug screenshot: {debug_dir / f'xhs_after_save_{timestamp}.png'}")

                    result["success"] = True
                    result["status"] = "draft"
                    result["message"] = f"Saved as draft. Note: Xiaohongshu drafts are stored locally in browser, need to use same browser to view (clicked: {clicked_selector})"
                    result["note"] = "Drafts are stored locally in browser and will not sync to mobile APP or other devices"
                else:
                    # Button not found, save screenshot to help debugging
                    screenshot_path = debug_dir / f"xhs_draft_not_found_{timestamp}.png"
                    await self.page.screenshot(path=str(screenshot_path))

                    # List all possible buttons on page
                    all_buttons = await self.page.query_selector_all('button, [class*="btn"], [class*="button"]')
                    button_texts = []
                    for btn in all_buttons[:20]:  # List max 20
                        try:
                            text = await btn.inner_text()
                            if text.strip():
                                button_texts.append(text.strip()[:30])
                        except:
                            pass

                    result["message"] = f"Draft save button not found. Screenshot: {screenshot_path}"
                    result["debug_buttons"] = button_texts
                    print(f"   ⚠️ Draft button not found, buttons on page: {button_texts}")
            else:
                # Publish
                print("🚀 Publishing note...")
                # Close any topic-suggestion popup that would intercept the click
                await self._dismiss_popups()

                # Debug screenshot before clicking publish
                await self._save_debug_screenshot("xhs_before_publish_click")

                publish_clicked = False
                clicked_selector = None

                # Scroll to bottom so the sticky publish bar is in viewport
                try:
                    await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Try selectors in order (most specific first).
                # With INTERCEPT_SHADOW_SCRIPT the closed Shadow DOM of
                # <xhs-publish-btn> is forced open, so Playwright can pierce
                # inside and hit the real <button class="ce-btn bg-red">.
                for selector in PUBLISH_BUTTON_SELECTORS:
                    elem = await self.page.query_selector(selector)
                    if not elem:
                        continue

                    # Skip the sidebar "发布笔记" nav button — it switches the
                    # publish *type* (image→video) rather than submitting.
                    try:
                        box = await elem.bounding_box()
                        if box and box['y'] < 150:
                            continue   # too high on the page → sidebar nav
                    except Exception:
                        pass

                    try:
                        tag = await elem.evaluate("el => el.tagName")
                        txt = await elem.inner_text()
                        classes = await elem.evaluate("el => el.className")
                        print(f"   Found element: <{tag}> class='{classes}' text='{txt.strip()}'")
                    except Exception:
                        pass

                    # Standard click first
                    try:
                        await self.page.click(selector, timeout=5000)
                        publish_clicked = True
                        clicked_selector = selector
                        print(f"   Clicked publish button: {selector}")
                        break
                    except Exception as e:
                        print(f"   ⚠️ {selector} click failed: {e}")

                    # Fallback: force click
                    try:
                        await self.page.click(selector, timeout=3000, force=True)
                        publish_clicked = True
                        clicked_selector = f"{selector} (force)"
                        print(f"   Clicked publish button (force): {selector}")
                        break
                    except Exception:
                        pass

                # Last resort: coordinate click inside xhs-publish-btn right half
                if not publish_clicked:
                    try:
                        btn = await self.page.query_selector('xhs-publish-btn')
                        if btn:
                            box = await btn.bounding_box()
                            if box:
                                x = box['x'] + box['width'] * 0.75
                                y = box['y'] + box['height'] / 2
                                await self.page.mouse.click(x, y)
                                publish_clicked = True
                                clicked_selector = f"coordinate-click ({x:.0f}, {y:.0f})"
                                print(f"   Clicked publish button at coordinates: {clicked_selector}")
                    except Exception as e:
                        print(f"   ⚠️ Coordinate click failed: {e}")

                if publish_clicked:
                    # Screenshot immediately after click
                    await self._save_debug_screenshot("xhs_after_publish_click")

                    # Poll for up to 30s: publishing is async and may need time
                    print("   ⏳ Waiting for publish to complete...")
                    deadline = asyncio.get_event_loop().time() + 30
                    while asyncio.get_event_loop().time() < deadline:
                        await asyncio.sleep(2)

                        current_url = self.page.url

                        # Left the publish page → very likely succeeded
                        if 'publish' not in current_url:
                            result["success"] = True
                            result["message"] = "Publish successful (left publish page)"
                            break

                        # Explicit success indicator on the page
                        for indicator in SUCCESS_INDICATOR_SELECTORS:
                            success_elem = await self.page.query_selector(indicator)
                            if success_elem:
                                try:
                                    success_text = await success_elem.inner_text()
                                except Exception:
                                    success_text = ""
                                result["success"] = True
                                result["message"] = f"Publish successful ({success_text.strip()})"
                                break
                        if result["success"]:
                            break

                        # Explicit error indicator
                        error_elem = await self.page.query_selector('[class*="error"], [class*="toast"]')
                        if error_elem:
                            error_text = await error_elem.inner_text()
                            shot = await self._save_debug_screenshot("xhs_publish_error")
                            result["message"] = f"Publish failed: {error_text}. Screenshot: {shot or 'n/a'}"
                            break

                    if not result["success"] and not result["message"]:
                        shot = await self._save_debug_screenshot("xhs_publish_outcome")
                        current_url = self.page.url
                        if 'publish' not in current_url:
                            result["success"] = True
                            result["message"] = (
                                f"Publish likely succeeded (please confirm manually). "
                                f"Screenshot: {shot or 'n/a'}"
                            )
                        else:
                            result["message"] = (
                                f"Publish status unknown, please check manually. "
                                f"Clicked: {clicked_selector}. Screenshot: {shot or 'n/a'}"
                            )
                else:
                    shot = await self._save_debug_screenshot("xhs_publish_button_not_found")
                    result["message"] = (
                        "Publish button not found — Xiaohongshu's markup likely changed; "
                        "update PUBLISH_BUTTON_SELECTORS in publishers/xiaohongshu.py "
                        f"(selectors last verified: {SELECTORS_LAST_VERIFIED}). "
                        f"Debug screenshot: {shot or 'n/a'}"
                    )

            return result

        except Exception as e:
            result["message"] = f"Error during publish: {str(e)}"
            # Save screenshot for debugging
            try:
                screenshot_path = _resolve_storage_path("xhs_error.png")
                await self.page.screenshot(path=str(screenshot_path))
                result["message"] += f" Screenshot saved to {screenshot_path}"
            except:
                pass
            return result
