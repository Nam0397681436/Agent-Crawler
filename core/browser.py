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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


class BrowserManager:
    _instance = None

    def __init__(self):
        self.context = None
        self.page = None
        self.playwright = None
        self.visted_urls = {}
        self.current_url = None
        self.profile_path = os.getenv("PROFILE_PATH")
        if not self.profile_path:
            self.profile_path = os.path.join(os.getcwd(), "chrome_test_profile")
        self.interceptor = None
        self.stop_event = None

    async def init_browser(self):
        self.playwright = await async_playwright().start()

        # Cấu hình Proxy dự phòng (nếu có yêu cầu xoay proxy)
        browser_args = [
            "--disable-blink-features=AutomationControlled",  # Né thuộc tính webdriver cơ bản
            "--start-maximized",
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

        self.interceptor = Interceptor(FactoryRegexApi(), "facebook")
        self.context.on("response", self.interceptor.capture_network)
        return self.context

    async def launch_page(self, url):
        self.page = await self.context.new_page()
        await self.page.goto(url)
        self.current_url = self.page.url
        self.visited_urls[self.page.url] = {"status": "visited"}
        return self.page

    async def close_browser(self):
        if self.interceptor:
            logger.info(
                f"[*] Đã bắt được {len(self.interceptor.storage_data)} phản hồi API."
            )
            with open("data.json", "w", encoding="utf-8") as f:
                json.dump(
                    self.interceptor.storage_data, f, ensure_ascii=False, indent=4
                )

        if self.playwright:
            await self.playwright.stop()


async def main():
    browser_manager = BrowserManager()
    try:
        await browser_manager.init_browser()
        page = await browser_manager.launch_page("https://www.facebook.com")
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
