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
import random
from toolfb.search_trend import search_trend_fb
from core.download_extension import download_and_extract_extension
from services.mouse_action import human_like_click_selector
from services.check_page import register_browser_dialog_handlers
from services.loginfb import login_fb, human_like_type

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


class BrowserManager:
    _instance = None

    # Gắn hàm login_fb từ services
    login_fb = login_fb

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

        # Tự động tải và giải nén extension Nopecha nếu chưa có
        extension_id = "dknlfmjaanfblgfdfebhijalfmhmjjjo"
        extension_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "extensions",
            "nopecha",
        )
        try:
            download_and_extract_extension(extension_id, extension_path)
        except Exception as e:
            logger.warning(f"[-] Không thể tự động tải extension: {e}")

        # Cấu hình Chrome với extension
        browser_args = [
            "--disable-blink-features=AutomationControlled",  # Né thuộc tính webdriver cơ bản
            "--start-maximized",
            f"--disable-extensions-except={extension_path}",
            f"--load-extension={extension_path}",
        ]

        logger.info(f"[*] Khởi tạo Profile trình duyệt tại: {self.profile_path}")
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=None,
            headless=False,
            args=browser_args,
            no_viewport=True,
        )
        # Tạo event để chờ trình duyệt đóng
        self.stop_event = asyncio.Event()
        self.context.on("close", lambda _: self.stop_event.set())

        self.interceptor = Interceptor(FactoryRegexApi(), "facebook")
        self.context.on("response", self.interceptor.capture_network)
        await register_browser_dialog_handlers(self.context)
        return self.context

    async def launch_page(self, url):
        self.page = await self.context.new_page()
        await self.page.goto(url)
        self.current_url = self.page.url
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

        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()


async def main():
    browser_manager = BrowserManager()
    try:
        await browser_manager.init_browser()
        page = await browser_manager.launch_page("https://www.facebook.com")
        await asyncio.sleep(2)

        # Ví dụ hover, click và tự nhập email như người thật dùng các hàm của bạn
        selector = "input[name='email']"
        email_to_type = "nam0397681436@gmail.com"
        selector_password = "input[name='pass']"
        password = "Namtrautrelop10a2"

        try:
            logger.info(f"[*] Đang di chuyển chuột và click vào phần tử: {selector}")
            await human_like_click_selector(page, selector)

            # Đợi ngẫu nhiên từ 0.5s đến 1s trước khi gõ phím
            await asyncio.sleep(random.uniform(1, 2))

            logger.info(f"[*] Đang gõ phím tự động nhập email: {email_to_type}")
            await human_like_type(page, email_to_type)
            await asyncio.sleep(random.uniform(1, 2))
            logger.info(
                f"[*] Đang di chuyển chuột và click vào phần tử: {selector_password}"
            )
            await human_like_click_selector(page, selector_password)
            logger.info(f"[*] Đang gõ phím tự động nhập mật khẩu: {password}")
            await human_like_type(page, password)
            logger.info("[+] Đã tự động nhập xong mật khẩu.")

            # Đợi ngẫu nhiên từ 0.5s đến 1.2s trước khi nhấn Enter (mô phỏng phản xạ con người)
            await asyncio.sleep(random.uniform(0.5, 1.2))

            logger.info("[*] Đang nhấn phím Enter để thực hiện đăng nhập...")
            await page.keyboard.press("Enter")
            logger.info("[+] Đã nhấn Enter thành công.")
        except Exception as e:
            logger.error(f"[-] Lỗi khi tự động nhập hoặc nhấn Enter: {e}")

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
