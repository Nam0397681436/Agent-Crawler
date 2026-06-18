import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright
from dotenv import load_dotenv
import asyncio
from core.interceptor import Interceptor
from model.factory_capture_api import FactoryRegexApi
import json
import logging
from toolfb.search_trend import search_trend_fb
from services.check_page import register_browser_dialog_handlers
import re
import random
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


class BrowserManager:
    _instance = None

    def __init__(self):
        self.context = None
        self.page = None
        self.playwright = None
        self.current_url = None
        self.profile_path = os.getenv("PROFILE_PATH")
        self.is_login = True
        if not self.profile_path:
            self.profile_path = os.path.join(os.getcwd(), "chrome_test_profile")

        # Đánh cờ is_login = False nếu chưa tồn tại thư mục profile
        if not os.path.exists(self.profile_path):
            self.is_login = False

        self.interceptor = None
        self.stop_event = None

    async def init_browser(self):
        self.playwright = await async_playwright().start()

        # Cấu hình Proxy dự phòng (nếu có yêu cầu xoay proxy)
        browser_args = [
            "--disable-blink-features=AutomationControlled",  # Né thuộc tính webdriver cơ bản
            "--start-maximized",
            "--disable-features=PasswordManager",  # Vô hiệu hóa popup Save Password
        ]

        logger.info(f"[*] Khởi tạo Profile trình duyệt tại: {self.profile_path}")
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_path,
            headless=False,
            args=browser_args,
            no_viewport=True,
        )

        # Tạo event để chờ trình duyệt đóng
        self.stop_event = asyncio.Event()
        self.context.on("close", lambda _: self.stop_event.set())

        # Xử lý các popup notification của browser
        await register_browser_dialog_handlers(self.context)

        return self.context

    async def launch_page(self, url):
        self.page = await self.context.new_page()
        await self.page.goto(url)
        self.current_url = self.page.url
        return self.page

    async def snapshot_url(self):
        anchors = await self.page.locator("a").evaluate_all(
            """
            els => els.map(a => ({
                text: (a.innerText || a.textContent || '').trim(),
                href: a.getAttribute('href') || ''
            }))
            """
        )
        with open("url_discovery.json", "w", encoding="utf-8") as f:
            json.dump(anchors, f, ensure_ascii=False, indent=4)
        url_discovery = set()
        for url in anchors:
            href = url.get("href", "").strip()
            if not href or href.startswith("javascript:") or href.startswith("#"):
                continue

            # Bỏ qua các URL chứa ?, = hoặc %
            if re.search(r"[?=%]", href):
                continue

            if href.startswith("/"):
                url_full = urljoin("https://www.facebook.com", href)
                url_discovery.add(url_full)
            elif (
                href.startswith("https://facebook.com")
                or href.startswith("https://web.facebook.com")
                or href.startswith("https://www.facebook.com")
                or href.startswith("https://m.facebook.com")
            ):
                url_discovery.add(href)

        return list(url_discovery)

    async def close_browser(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def login_fb(self, url) -> bool:
        """
        Ensure we are logged into Facebook before navigating to the target URL.

        Strategy:
        1. Always open facebook.com HOMEPAGE first – this is the only reliable
           place where the login form appears.  Search/group URLs return an empty
           page (not a login form) when the user is logged out.
        2. If the login form is not visible on the homepage → already logged in.
        3. If the login form is visible → fill credentials → wait for it to hide.
        4. Finally, navigate to the actual target URL.
        """
        homepage = "https://www.facebook.com"

        # Reuse the existing page if possible, or create a fresh one
        if not self.page:
            await self.launch_page(homepage)
        else:
            # Page may have been closed by a previous task; try to reuse it
            try:
                await self.page.goto(homepage)
            except Exception:
                # Page is closed or stale – open a new one
                logger.info("[*] Previous page is closed. Opening a new page...")
                self.page = await self.context.new_page()
                await self.page.goto(homepage)

        page = self.page
        email_selector = "input[name='email']"
        password_selector = "input[name='pass']"
        email = "nam0397681436@gmail.com"
        pwd = "Namtrautrelop10a2"

        # Check login state on the homepage
        try:
            if not await page.locator(email_selector).is_visible(timeout=5000):
                logger.info(
                    "[+] Already logged into Facebook. Navigating to target URL..."
                )
                await page.goto(url)
                self.is_login = True
                return True
        except Exception as e:
            logger.error(f"[-] Error checking login form: {e}")

        # Perform login
        logger.info("[*] Login form detected. Filling credentials...")
        try:
            await page.locator(email_selector).click()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await human_like_type(page, email)

            await page.locator(password_selector).click()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await human_like_type(page, pwd)

            await page.keyboard.press("Enter")
        except Exception as e:
            logger.error(f"[-] Error during credential input: {e}")
            self.is_login = False
            return False

        # Wait for login form to disappear (page transition after Enter)
        try:
            logger.info("[*] Waiting for login form to disappear...")
            await page.wait_for_selector(email_selector, state="hidden", timeout=15000)
        except Exception as e:
            logger.warning(f"[-] Login form still visible: {e}")
            self.is_login = False
            return False

        # After form disappears, FB might redirect to:
        #   A) Home feed → login successful
        #   B) Checkpoint / 2FA / two_step page → need manual action
        #   C) Back to login (wrong password, CAPTCHA) → failed
        # We check the URL to determine which case we're in.
        _auth_bad_patterns = [
            "login",
            "checkpoint",
            "two_step_verification",
            "recover",
            "hacked",
            "auth_platform",  # Xác nhận đăng nhập từ thiết bị mới
        ]

        async def _is_blocked() -> bool:
            return any(p in page.url for p in _auth_bad_patterns)

        # Give a moment for redirect to settle
        await asyncio.sleep(1.5)

        if await _is_blocked():
            logger.info(
                f"[*] Detected 2FA / checkpoint page ({page.url}). "
                "Waiting up to 90s for manual verification..."
            )
            try:
                # Poll until URL leaves the blocked zone
                await page.wait_for_function(
                    """() => {
                        const url = window.location.href;
                        const blocked = ["login", "checkpoint", "two_step", "recover", "hacked", "auth_platform"];
                        return !blocked.some(p => url.includes(p));
                    }""",
                    timeout=90000,
                )
                logger.info("[+] Manual 2FA completed. Continuing...")
            except Exception as e:
                logger.warning(f"[-] 2FA timeout or still blocked: {e}")
                self.is_login = False
                return False

        # Final sanity check: email form must NOT be visible (we might have bounced back)
        try:
            if await page.locator(email_selector).is_visible(timeout=3000):
                logger.warning(
                    "[-] Login form reappeared. Login failed (wrong password / CAPTCHA?)."
                )
                self.is_login = False
                return False
        except Exception:
            pass

        # Navigate to the real target URL
        logger.info(f"[*] Login confirmed. Navigating to: {url}")
        await page.goto(url)

        self.is_login = True
        logger.info("[+] Facebook login successful.")
        return True


async def human_like_type(page, text: str):
    """
    Nhập văn bản mô phỏng tốc độ gõ phím thực tế của con người.
    """
    for char in text:
        # Gõ ký tự
        await page.keyboard.type(char)
        # Delay ngẫu nhiên giữa các ký tự (ví dụ từ 50ms đến 150ms)
        await asyncio.sleep(random.uniform(0.15, 0.5))


async def main():
    browser_manager = BrowserManager()
    try:
        await browser_manager.init_browser()
        page = await browser_manager.launch_page("https://www.facebook.com")
        await asyncio.sleep(2)

        # Ví dụ hover, click và tự nhập email như người thật dùng các hàm của bạn

        if not browser_manager.stop_event.is_set():
            await browser_manager.stop_event.wait()
    except asyncio.CancelledError:
        logger.info("[*] Đã nhận tín hiệu ngắt (Ctrl+C).")
    except Exception as e:
        logger.error(f"[-] Lỗi: {e}")
    finally:
        logger.info("[*] Đang tiến hành đóng trình duyệt và lưu dữ liệu...")
        await browser_manager.close_browser()
        logger.info("[+] Hoàn tất.")


if __name__ == "__main__":
    # Đảm bảo hiển thị tiếng Việt không bị lỗi Unicode
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
