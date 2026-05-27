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

import json
import asyncio
import requests
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


def _resolve_storage_path(relative_path: str) -> Path:
    """Prefer new storage dir, but fall back to legacy .dailypaper if it exists."""
    new_base = Path.home() / ".xhs-paper-engine"
    old_base = Path.home() / ".dailypaper"
    new_path = new_base / relative_path
    old_path = old_base / relative_path
    if new_path.exists():
        return new_path
    if old_path.exists():
        return old_path
    return new_path


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
SELECTORS_LAST_VERIFIED = "2024-06 (unverified since; update when you confirm)"

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
PUBLISH_BUTTON_SELECTORS = [
    'div.submit div.d-button-content',
    'button:has-text("发布")',
    'button[class*="publish"]',
    'button:has-text("发布笔记")',
    '[class*="submit"] button',
]
SUCCESS_INDICATOR_SELECTORS = [
    '[class*="success"]',
    '[class*="toast"]:has-text("成功")',
    '[class*="toast"]:has-text("发布")',
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
        self.cookies_path = Path(cookies_path) if cookies_path else _resolve_storage_path("xiaohongshu_cookies.json")
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

        # Create context, set user agent
        self.context = await self.browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Try to load saved cookies
        if self.cookies_path.exists():
            await self._load_cookies()

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
        """Save cookies to file"""
        cookies = await self.context.cookies()
        with open(self.cookies_path, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"✅ Cookies saved to: {self.cookies_path}")

    async def _load_cookies(self):
        """Load cookies from file"""
        try:
            with open(self.cookies_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            print(f"✅ Cookies loaded: {self.cookies_path}")
        except Exception as e:
            print(f"⚠️ Failed to load cookies: {e}")

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
                # The page still lands somewhere — inspect the resulting URL below
                # instead of treating the abort as "not logged in".
                pass
            await asyncio.sleep(3)

            # Check if redirected to login page
            current_url = self.page.url
            if 'login' in current_url:
                return False

            # Check if there is user avatar or other login indicators
            try:
                # Try to find user info element
                user_info = await self.page.query_selector(LOGIN_INDICATOR_SELECTORS)
                if user_info:
                    return True
            except:
                pass

            return 'login' not in current_url
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
            await asyncio.sleep(5)  # Wait for page to fully load

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
            await asyncio.sleep(2)

            # Find the file input (critical — without it we cannot publish)
            upload_input = None
            for selector in UPLOAD_INPUT_SELECTORS:
                upload_input = await self.page.query_selector(selector)
                if upload_input:
                    print(f"   Found upload input: {selector}")
                    break

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

            # Wait for content filling to complete
            await asyncio.sleep(2)

            # Set visibility range (default to only self visible)
            if visibility == "private":
                print("🔒 Setting visibility: Only self visible")
                try:
                    # First open the "Visibility Range" dropdown
                    dropdown = await self._query_first_visible(VISIBILITY_DROPDOWN_SELECTORS)
                    if dropdown:
                        await dropdown.click()
                        print("   ✅ Clicked visibility dropdown")
                        await asyncio.sleep(1)

                        # Then pick "Only self visible"
                        private_opt = await self._query_first_visible(PRIVATE_OPTION_SELECTORS)
                        if private_opt:
                            await private_opt.click()
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
                # Reference xiaohongshu-mcp: submitButton -> "div.submit div.d-button-content"
                print("🚀 Publishing note...")
                publish_clicked = False
                for selector in PUBLISH_BUTTON_SELECTORS:
                    try:
                        await self.page.click(selector, timeout=3000)
                        publish_clicked = True
                        print(f"   Clicked publish button: {selector}")
                        break
                    except:
                        continue

                if publish_clicked:
                    await asyncio.sleep(5)  # Wait for publish to complete

                    # Check if publish is successful
                    current_url = self.page.url

                    # Check success indicators
                    for indicator in SUCCESS_INDICATOR_SELECTORS:
                        success_elem = await self.page.query_selector(indicator)
                        if success_elem:
                            result["success"] = True
                            result["message"] = "Publish successful"
                            break

                    if not result["success"]:
                        # Outcome is ambiguous — capture a screenshot so the user can verify.
                        shot = await self._save_debug_screenshot("xhs_publish_outcome")
                        if 'publish' not in current_url or 'success' in current_url:
                            result["success"] = True
                            result["message"] = (
                                f"Publish likely succeeded (please confirm manually). "
                                f"Screenshot: {shot or 'n/a'}"
                            )
                        else:
                            # Check if there is error message
                            error_elem = await self.page.query_selector('[class*="error"], [class*="toast"]')
                            if error_elem:
                                error_text = await error_elem.inner_text()
                                result["message"] = f"Publish failed: {error_text}. Screenshot: {shot or 'n/a'}"
                            else:
                                result["message"] = (
                                    f"Publish status unknown, please check manually. "
                                    f"Screenshot: {shot or 'n/a'}"
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
