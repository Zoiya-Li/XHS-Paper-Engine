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

import os
import json
import asyncio
import requests
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from io import BytesIO


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


class XiaohongshuPublisher:
    """Xiaohongshu Publisher"""

    # Xiaohongshu Creator Center URL
    CREATOR_URL = "https://creator.xiaohongshu.com"
    LOGIN_URL = "https://creator.xiaohongshu.com/login"
    # Directly use target=image parameter to enter image-text upload page
    PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish?from=menu&target=image"

    # Xiaohongshu main site (for getting traffic data)
    EXPLORE_URL = "https://www.xiaohongshu.com/explore"

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
            # Use domcontentloaded instead of networkidle to avoid timeout
            await self.page.goto(self.CREATOR_URL, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)

            # Check if redirected to login page
            current_url = self.page.url
            if 'login' in current_url:
                return False

            # Check if there is user avatar or other login indicators
            try:
                # Try to find user info element
                user_info = await self.page.query_selector('.user-info, .user-avatar, [class*="avatar"]')
                if user_info:
                    return True
            except:
                pass

            return 'login' not in current_url
        except Exception as e:
            print(f"⚠️ Error checking login status: {e}")
            return False

    async def login_with_qrcode(self, timeout: int = 120) -> bool:
        """
        QR code scan login

        Args:
            timeout: Timeout for waiting scan (seconds)

        Returns:
            Whether login is successful
        """
        print("\n" + "="*60)
        print("📱 Xiaohongshu QR Code Login")
        print("="*60)

        await self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(3)

        # Wait for QR code to appear
        try:
            qr_selector = '.qrcode-img, [class*="qrcode"], img[src*="qrcode"]'
            await self.page.wait_for_selector(qr_selector, timeout=10000)
            print("\n✅ QR code loaded, please scan the QR code on screen using Xiaohongshu APP")
            print(f"⏳ Waiting for scan login (timeout: {timeout} seconds)...")
        except:
            print("⚠️ QR code not found, may already be logged in or page structure changed")

        # Wait for successful login (URL change or user info appears)
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            current_url = self.page.url
            if 'login' not in current_url and 'creator.xiaohongshu.com' in current_url:
                print("\n✅ Login successful!")
                await self._save_cookies()
                return True
            await asyncio.sleep(2)

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
            selectors = [
                '[class*="image-item"]',
                '[class*="upload-item"]',
                '[class*="preview"] img',
                '.image-list img',
                '[class*="publish-image"]'
            ]
            for selector in selectors:
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

        # Check login status
        if not await self.check_login():
            result["message"] = "Not logged in, please scan QR code to login first"
            return result

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

            # Try multiple ways to click tab
            tab_click_methods = [
                # Method 1: text match
                lambda: self.page.click('text=上传图文'),
                # Method 2: div containing text
                lambda: self.page.click('div:has-text("上传图文")'),
                # Method 3: tab class selector
                lambda: self.page.click('[class*="tab"]:has-text("图文")'),
                lambda: self.page.click('[class*="tab"]:has-text("上传图文")'),
                # Method 4: span element
                lambda: self.page.click('span:has-text("上传图文")'),
            ]

            for click_method in tab_click_methods:
                try:
                    await click_method()
                    print("   ✅ Clicked image-text upload tab")
                    tab_clicked = True
                    await asyncio.sleep(2)
                    break
                except:
                    continue

            if not tab_clicked:
                print("   ⚠️ Image-text upload tab not found, trying to continue...")

            # Upload images
            # Reference xiaohongshu-mcp: uploadInput := pp.MustElement(".upload-input")
            print(f"📸 Uploading images ({len(valid_images)})...")
            await asyncio.sleep(2)

            # Try multiple selectors to find upload input
            upload_input = None
            upload_selectors = [
                '.upload-input',           # Selector used by xiaohongshu-mcp
                'input[type="file"]',
                'input[accept*="image"]',
                '.upload-input input',
                '[class*="upload"] input[type="file"]'
            ]

            for selector in upload_selectors:
                upload_input = await self.page.query_selector(selector)
                if upload_input:
                    print(f"   Found upload input: {selector}")
                    break

            if upload_input:
                # Batch upload images
                await upload_input.set_input_files(valid_images)
                print("   ✅ Images uploading...")

                # Wait for image upload to complete
                uploaded_count = await self._wait_for_upload_complete(len(valid_images))
                print(f"   ✅ Uploaded {uploaded_count}/{len(valid_images)} images")
            else:
                # Save screenshot for debugging
                screenshot_path = _resolve_storage_path("xhs_upload_failed.png")
                await self.page.screenshot(path=str(screenshot_path))
                print(f"   ⚠️ Upload entry not found, screenshot saved: {screenshot_path}")
                result["message"] = f"Image upload entry not found. Screenshot saved to {screenshot_path}"
                return result

            # Wait for entering edit page
            await asyncio.sleep(3)

            # Input title
            # Reference xiaohongshu-mcp: titleElem := page.MustElement("div.d-input input")
            print(f"📝 Inputting title: {title}")
            title_selectors = [
                'div.d-input input',        # Selector used by xiaohongshu-mcp
                'input[placeholder*="标题"]',
                '[class*="title"] input',
                '#title'
            ]

            title_filled = False
            for selector in title_selectors:
                try:
                    title_input = await self.page.query_selector(selector)
                    if title_input:
                        await title_input.fill(title)
                        title_filled = True
                        break
                except:
                    continue

            if not title_filled:
                print("   ⚠️ Title input not found")

            # Input content
            # Reference xiaohongshu-mcp: contentElem := getContentElement(page) -> "div.ql-editor"
            print(f"📝 Inputting content ({len(content)} chars)...")
            content_selectors = [
                'div.ql-editor',            # Selector used by xiaohongshu-mcp
                '[contenteditable="true"]',
                '[placeholder*="正文"]',
                '[class*="content"] textarea',
                '#content'
            ]

            content_elem = None
            for selector in content_selectors:
                try:
                    content_elem = await self.page.query_selector(selector)
                    if content_elem:
                        await content_elem.fill(content)
                        break
                except:
                    continue

            if not content_elem:
                print("   ⚠️ Content input not found")

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
                    # First click "Visibility Range" dropdown
                    visibility_selectors = [
                        'text=公开可见',
                        ':has-text("公开可见")',
                        '[class*="visible"] >> text=公开',
                        'div:has-text("可见范围") >> text=公开可见',
                    ]

                    dropdown_clicked = False
                    for selector in visibility_selectors:
                        try:
                            elem = await self.page.query_selector(selector)
                            if elem and await elem.is_visible():
                                await elem.click()
                                dropdown_clicked = True
                                print(f"   ✅ Clicked visibility dropdown")
                                await asyncio.sleep(1)
                                break
                        except:
                            continue

                    if dropdown_clicked:
                        # Select "Only self visible"
                        private_selectors = [
                            'text=仅自己可见',
                            ':has-text("仅自己可见")',
                            '[class*="option"]:has-text("仅自己")',
                        ]

                        for selector in private_selectors:
                            try:
                                elem = await self.page.query_selector(selector)
                                if elem and await elem.is_visible():
                                    await elem.click()
                                    print(f"   ✅ Set to only self visible")
                                    await asyncio.sleep(1)
                                    break
                            except:
                                continue
                    else:
                        print("   ⚠️ Visibility dropdown not found, will use default setting")
                except Exception as e:
                    print(f"   ⚠️ Failed to set visibility: {e}")

            if save_draft:
                # Save draft
                print("💾 Saving draft...")

                # First screenshot to record current state
                debug_dir = _resolve_storage_path("debug")
                debug_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                await self.page.screenshot(path=str(debug_dir / f"xhs_before_save_{timestamp}.png"))
                print(f"   Debug screenshot: {debug_dir / f'xhs_before_save_{timestamp}.png'}")

                # Xiaohongshu Creator Center draft save button selectors
                # Button text is "暂存离开"
                draft_selectors = [
                    # Exact match "暂存离开"
                    'text=暂存离开',
                    ':has-text("暂存离开")',
                    'button:has-text("暂存离开")',
                    'div:has-text("暂存离开")',
                    # Other possible selectors
                    'text=暂存',
                    'text=存草稿',
                    ':has-text("暂存")',
                    ':has-text("存草稿")',
                ]

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
                    except Exception as e:
                        continue

                if draft_clicked:
                    await asyncio.sleep(2)

                    # Check if there is confirmation dialog
                    confirm_selectors = [
                        'button:has-text("确认")',
                        'button:has-text("确定")',
                        'button:has-text("离开")',
                        '[class*="confirm"]',
                    ]

                    for confirm_sel in confirm_selectors:
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
                publish_selectors = [
                    'div.submit div.d-button-content',  # Selector used by xiaohongshu-mcp
                    'button:has-text("发布")',
                    'button[class*="publish"]',
                    'button:has-text("发布笔记")',
                    '[class*="submit"] button'
                ]

                publish_clicked = False
                for selector in publish_selectors:
                    try:
                        await self.page.click(selector)
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
                    success_indicators = [
                        '[class*="success"]',
                        '[class*="toast"]:has-text("成功")',
                        '[class*="toast"]:has-text("发布")'
                    ]

                    for indicator in success_indicators:
                        success_elem = await self.page.query_selector(indicator)
                        if success_elem:
                            result["success"] = True
                            result["message"] = "Publish successful"
                            break

                    if not result["success"]:
                        if 'publish' not in current_url or 'success' in current_url:
                            result["success"] = True
                            result["message"] = "Publish possibly successful (please manually confirm)"
                        else:
                            # Check if there is error message
                            error_elem = await self.page.query_selector('[class*="error"], [class*="toast"]')
                            if error_elem:
                                error_text = await error_elem.inner_text()
                                result["message"] = f"Publish failed: {error_text}"
                            else:
                                result["message"] = "Publish status unknown, please manually check"
                else:
                    result["message"] = "Publish button not found"

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

    async def get_feed_stats(self, feed_id: str, xsec_token: str = "") -> Dict[str, Any]:
        """
        Get traffic statistics data for note
        Reference implementation from xiaohongshu-mcp's GetFeedDetail

        Args:
            feed_id: Note ID
            xsec_token: Access token (optional)

        Returns:
            Traffic data (likes, comments, favorites, etc.)
        """
        try:
            # Build detail page URL
            url = f"https://www.xiaohongshu.com/explore/{feed_id}"
            if xsec_token:
                url += f"?xsec_token={xsec_token}&xsec_source=pc_feed"

            await self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)

            # Extract data from window.__INITIAL_STATE__
            # Reference implementation from xiaohongshu-mcp
            result = await self.page.evaluate('''() => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.note &&
                    window.__INITIAL_STATE__.note.noteDetailMap) {
                    const noteDetailMap = window.__INITIAL_STATE__.note.noteDetailMap;
                    return JSON.stringify(noteDetailMap);
                }
                return "";
            }''')

            if result:
                data = json.loads(result)
                # Extract interaction data
                for key, value in data.items():
                    if 'note' in value:
                        note = value['note']
                        interact_info = note.get('interactInfo', {})
                        return {
                            "success": True,
                            "feed_id": feed_id,
                            "title": note.get('title', ''),
                            "liked_count": interact_info.get('likedCount', '0'),
                            "comment_count": interact_info.get('commentCount', '0'),
                            "collected_count": interact_info.get('collectedCount', '0'),
                            "shared_count": interact_info.get('sharedCount', '0'),
                        }

            return {
                "success": False,
                "message": "Cannot get note data"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get traffic data: {str(e)}"
            }

    async def get_my_feeds(self) -> List[Dict[str, Any]]:
        """
        Get my note list
        Reference implementation from xiaohongshu-mcp's GetFeeds

        Returns:
            Note list
        """
        try:
            await self.page.goto(self.EXPLORE_URL, wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)

            # Extract data from window.__INITIAL_STATE__
            result = await self.page.evaluate('''() => {
                if (window.__INITIAL_STATE__ &&
                    window.__INITIAL_STATE__.feed &&
                    window.__INITIAL_STATE__.feed.feeds) {
                    const feeds = window.__INITIAL_STATE__.feed.feeds;
                    const feedsData = feeds.value !== undefined ? feeds.value : feeds._value;
                    if (feedsData) {
                        return JSON.stringify(feedsData);
                    }
                }
                return "";
            }''')

            if result:
                return json.loads(result)

            return []

        except Exception as e:
            print(f"Failed to get note list: {e}")
            return []


class XiaohongshuPublisherSync:
    """Synchronous version of Xiaohongshu publisher (for non-async environments)"""

    def __init__(self, cookies_path: Optional[str] = None, headless: bool = False):
        self.publisher = XiaohongshuPublisher(cookies_path, headless)

    def _run(self, coro):
        """Run coroutine"""
        return asyncio.get_event_loop().run_until_complete(coro)

    def start(self):
        return self._run(self.publisher.start())

    def stop(self):
        return self._run(self.publisher.stop())

    def check_login(self) -> bool:
        return self._run(self.publisher.check_login())

    def login_with_qrcode(self, timeout: int = 120) -> bool:
        return self._run(self.publisher.login_with_qrcode(timeout))

    def publish(
        self,
        title: str,
        content: str,
        images: List[str],
        tags: Optional[List[str]] = None,
        location: Optional[str] = None,
        save_draft: bool = False,
        visibility: str = "private"
    ) -> Dict[str, Any]:
        return self._run(self.publisher.publish(title, content, images, tags, location, save_draft, visibility))

    def get_feed_stats(self, feed_id: str, xsec_token: str = "") -> Dict[str, Any]:
        return self._run(self.publisher.get_feed_stats(feed_id, xsec_token))


# Convenience functions
async def publish_to_xiaohongshu(
    title: str,
    content: str,
    images: List[str],
    tags: Optional[List[str]] = None,
    headless: bool = False
) -> Dict[str, Any]:
    """
    Convenience function for publishing to Xiaohongshu

    Args:
        title: Title
        content: Content
        images: Image path list (supports URLs)
        tags: Topic tags
        headless: Whether to use headless mode

    Returns:
        Publish result
    """
    publisher = XiaohongshuPublisher(headless=headless)
    try:
        await publisher.start()

        # Check login
        if not await publisher.check_login():
            print("\n⚠️ Need to login to Xiaohongshu")
            success = await publisher.login_with_qrcode()
            if not success:
                return {"success": False, "message": "Login failed"}

        # Publish
        return await publisher.publish(title, content, images, tags)

    finally:
        await publisher.stop()


def publish_to_xiaohongshu_sync(
    title: str,
    content: str,
    images: List[str],
    tags: Optional[List[str]] = None,
    headless: bool = False
) -> Dict[str, Any]:
    """Synchronous version of publish function"""
    return asyncio.run(publish_to_xiaohongshu(title, content, images, tags, headless))
