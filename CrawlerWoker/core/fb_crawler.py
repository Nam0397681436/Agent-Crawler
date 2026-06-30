"""
core/agent.py — Lớp 3: Vòng lặp điều phối (Perceive → Decide → Act)
=====================================================================
Dùng OpenAI function-calling để ép LLM LUÔN trả về 1 action có cấu trúc.
Không cho phép LLM "nói chuyện tự do" (tool_choice="required").

Vòng lặp:
  1. Quét lại trang qua dom_extractor (text + ảnh)
  2. Gửi state + lịch sử hội thoại cho LLM kèm tool schema
  3. LLM chọn đúng 1 action
  4. Thực thi action qua Playwright (actions.py)
  5. Đưa kết quả vào lịch sử → quay lại bước 1

Cơ chế an toàn:
  - max_steps: giới hạn số bước tránh lặp vô tận
  - history_window: chỉ giữ N bước gần nhất để tránh phình context
  - ask_user: dừng lại khi gặp captcha / tình huống rủi ro
  - done: agent tự báo kết thúc kèm tổng kết

Sử dụng:
    from core.agent import FacebookAgent
    agent = FacebookAgent(task="join group 'Mạng Xã Hội Việt Nam'")
    result = await agent.run(page)
"""

import logging
import os
import random
from urllib.parse import urlparse, urlunparse

from playwright.async_api import Page

from core import actions
from services.publisher_kafka import KafkaPublisher
from services.scroll_antibot import smart_scroll_for_api

logger = logging.getLogger(__name__)


class FacebookCrawler:

    def __init__(self):
        self.extracted_data: list[dict] = []
        self.clicked_elements: set[str] = set()
        self.discovery_entity: list[dict] = []

    @staticmethod
    def _clean_url(url: str) -> str:
        """
        Xóa query string (?_rdc=1&_rdr...) và fragment ra khỏi URL Facebook.
        Ví dụ:
          https://www.facebook.com/lam.anh/?_rdc=1&_rdr
          → https://www.facebook.com/lam.anh
        """
        parsed = urlparse(url)
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean).rstrip("/")

    async def _capture_avatar(self, page: Page) -> str | None:
        """Chụp avatar và lưu vào extracted_data."""
        from services.capture_img import capture_avatar

        url_avatar = await capture_avatar(page, self.extracted_data)
        if url_avatar:
            self.extracted_data.append({"url_avatar": url_avatar})
        self.extracted_data.append({"url_entity": page.url})
        return url_avatar

    async def _publish_result(self) -> dict:
        """Đóng gói kết quả và publish lên Kafka."""
        result_data = {
            "extracted_data": self.extracted_data,
            "discovery_entity_ralationship": self.discovery_entity,
            "summary": "ok",
        }
        topic = os.getenv("TOPIC_ENTITY_INFO", "entity_info_crawl").strip()
        kafka_publisher = KafkaPublisher()
        await kafka_publisher.publish(result_data, topic=topic)
        return result_data

    async def _safe_goto(self, page: Page, url: str) -> bool:
        """
        Navigate tới url và chờ trang ổn định.
        URL đưa vào phải đã được clean trước (không có query rác).
        """
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(random.randint(2000, 3000))  # buffer SPA render
        except Exception as e:
            logger.warning(f"[crawler] goto lỗi: {url} — {e}")
            return False

        logger.info(f"[crawler] Navigate thành công: {page.url}")
        return True

    async def run_user_profile(self, page: Page) -> dict:
        """
        Pipeline cho trang cá nhân (User Profile).
        Thêm bước mới: append thêm dict vào `steps` bên dưới.
          action: "scroll"  — navigate (nếu có url) rồi cuộn lấy thông tin
          action: "hover"   — navigate rồi hover lấy danh sách users
          action: "photos"  — navigate rồi capture ảnh
        """
        base_url = self._clean_url(page.url)
        logger.info(f"[crawler] base_url (clean): {base_url}")
        await self._capture_avatar(page)

        steps = [
            {"label": "home", "action": "scroll"},
            {"label": "about", "action": "click", "url": f"{base_url}/about"},
            {
                "label": "friends",
                "action": "hover",
                "url": f"{base_url}/friends",
                "url_group": f"{base_url}/members",
            },
            {"label": "photos", "action": "photos", "url": f"{base_url}/photos"},
        ]

        from services.capture_img import capture_photos

        for step in steps:
            label = step["label"]
            action = step["action"]
            logger.info(f"[crawler] Bắt đầu crawl: {label} (user profile)")

            # Navigate trước nếu step có url
            if "url" in step:
                ok = await self._safe_goto(page, step["url"])
                if not ok:
                    logger.warning(
                        f"[crawler] Bỏ qua bước '{label}' do navigate thất bại."
                    )
                    if "url_group" in step:
                        ok2 = await self._safe_goto(page, step["url_group"])
                        if not ok2:
                            logger.warning(
                                f"[crawler] Bỏ qua bước '{label}' do navigate thất bại."
                            )
                            continue
                    continue
            if label == "about":
                await actions._click_info_page_user(page)
                await actions._scroll(page, scroll_rounds=2)

            elif label == "home":
                await actions._scroll(page, scroll_rounds=5)

            elif label == "friends":
                await actions._hover_users(
                    page=page,
                    scroll_rounds=15,
                    hover_delay_ms=500,
                    discovery_entity=self.discovery_entity,
                )

            elif label == "photos":
                photos = await capture_photos(page, scroll_rounds=2)
                if photos:
                    self.extracted_data.append({"photos": photos})

        logger.info("[crawler] Hoàn thành pipeline user profile.")
        return await self._publish_result()

    async def run_group(self, page: Page) -> dict:
        """
        Pipeline cho trang Nhóm (Group).
        Thêm bước mới: append thêm dict vào `steps` bên dưới.
          action: "scroll" — navigate (nếu có url) rồi cuộn lấy thông tin nhóm
          action: "hover"  — navigate rồi hover lấy danh sách thành viên
        """
        base_url = self._clean_url(page.url)
        logger.info(f"[crawler] base_url (clean): {base_url}")
        await self._capture_avatar(page)

        steps = [
            {"label": "home", "action": "scroll"},
            {"label": "about", "action": "scroll", "url": f"{base_url}/about"},
            {"label": "members", "action": "hover", "url": f"{base_url}/members"},
        ]

        for step in steps:
            label = step["label"]
            action = step["action"]
            logger.info(f"[crawler] Bắt đầu crawl: {label} (group)")

            # Navigate trước nếu step có url
            if "url" in step:
                ok = await self._safe_goto(page, step["url"])
                if not ok:
                    logger.warning(
                        f"[crawler] Bỏ qua bước '{label}' do navigate thất bại."
                    )
                    continue

            if label == "home":
                await actions._scroll(page, scroll_rounds=20)

            elif label == "about":
                await smart_scroll_for_api(
                    page, max_scroll_loops=3, min_wait_ms=1200, max_wait_ms=3000
                )

            elif label == "members":
                await actions._hover_users(
                    page=page,
                    scroll_rounds=20,
                    hover_delay_ms=500,
                    discovery_entity=self.discovery_entity,
                )

        logger.info("[crawler] Hoàn thành pipeline group.")
        return await self._publish_result()
