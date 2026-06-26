"""
core/browser.py — BrowserManager (lifecycle only)
===================================================
Chỉ xử lý vòng đời trình duyệt:
  - Khởi động / tắt Playwright + PersistentContext
  - Quản lý interceptor mạng
  - Expose page factory (new_page)

Mọi logic nghiệp vụ (đăng nhập, popup, cuộn, …) nằm ở
services/ hoặc các lớp bên ngoài.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright, BrowserContext, Page
from dotenv import load_dotenv

from core.interceptor import Interceptor
from core.download_extension import download_and_extract_extension
from model.factory_capture_api import FactoryRegexApi
from services.check_page import register_browser_dialog_handlers
from services.loginfb import login_fb

load_dotenv()
logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Quản lý vòng đời trình duyệt Playwright.

    Sử dụng:
        browser = BrowserManager()
        await browser.start()          # Khởi động
        page  = await browser.new_page()
        await browser.ensure_login(page, "https://www.facebook.com")
        ...
        await browser.stop()           # Tắt, lưu dữ liệu interceptor
    """

    def __init__(self):
        self.context: BrowserContext | None = None
        self.playwright = None
        self.interceptor: Interceptor | None = None
        self.stop_event: asyncio.Event | None = None

        # Đường dẫn profile (lưu session / cookie)
        self.profile_path: str = os.getenv(
            "PROFILE_PATH",
            os.path.join(os.getcwd(), "chrome_test_profile"),
        )
        # True nếu profile đã tồn tại → khả năng cao đã đăng nhập
        self.is_login: bool = os.path.exists(self.profile_path)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> BrowserContext:
        """Khởi động Playwright, load extension, mở persistent context."""
        self.playwright = await async_playwright().start()

        extension_path = self._prepare_extension()
        args = self._build_browser_args(extension_path)

        logger.info(f"[browser] Khởi tạo profile tại: {self.profile_path}")
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_path,
            headless=False,
            args=args,
            no_viewport=True,
        )

        # Event để biết khi nào trình duyệt bị đóng từ bên ngoài
        self.stop_event = asyncio.Event()
        self.context.on("close", lambda _: self.stop_event.set())

        # Interceptor bắt response mạng
        self.interceptor = Interceptor(FactoryRegexApi(), "facebook")
        self.context.on("response", self.interceptor.capture_network)

        # Tự động từ chối notification popup của browser
        await register_browser_dialog_handlers(self.context)

        return self.context

    async def stop(self) -> None:
        """
        Tắt trình duyệt.
        """
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            logger.debug(f"[browser] context.close(): {e}")
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"[browser] playwright.stop(): {e}")

        self.context = None
        self.playwright = None
        logger.info("[browser] Đã tắt trình duyệt.")

    # ------------------------------------------------------------------
    # Page factory
    # ------------------------------------------------------------------

    async def new_page(self, url: str | None = None) -> Page:
        """
        Tạo một tab (page) mới.
        Nếu truyền url, sẽ navigate ngay lập tức.
        """
        if not self.context:
            raise RuntimeError("BrowserManager chưa được khởi động. Gọi start() trước.")
        page = await self.context.new_page()
        if url:
            await page.goto(url)
        return page

    # ------------------------------------------------------------------
    # Login helper (delegate sang services/loginfb.py)
    # ------------------------------------------------------------------

    async def ensure_login(self, page: Page, target_url: str) -> bool:
        """
        Đảm bảo đã đăng nhập Facebook trước khi navigate tới target_url.
        Trả về True nếu thành công, False nếu thất bại.
        """
        ok = await login_fb(self, page, target_url)
        self.is_login = ok
        return ok

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prepare_extension(self) -> str:
        """Tải extension Nopecha nếu chưa có, trả về đường dẫn."""
        extension_id = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
        extension_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "extensions",
            "nopecha",
        )
        try:
            download_and_extract_extension(extension_id, extension_path)
        except Exception as e:
            logger.warning(f"[browser] Không thể tải extension: {e}")
        return extension_path

    def _build_browser_args(self, extension_path: str) -> list[str]:
        return [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--disable-features=PasswordManager",
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ]
