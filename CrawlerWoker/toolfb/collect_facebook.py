"""
toolfb/collect_facebook.py — Thu thập thông tin từ bất kỳ URL Facebook nào
============================================================================
Nhận vào 1 URL (profile / group / page), agent nhìn screenshot tự quyết định
cần click tab nào, scroll ở đâu để lấy hết thông tin.

Không cần biết trước URL là loại gì — agent tự nhận diện qua ảnh.
"""

from services.publisher_kafka import KafkaPublisher
import json
import logging
import os
from playwright.async_api import Page
from steps.start_pipeline import CrawlerInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.browser import BrowserManager

logger = logging.getLogger(__name__)


async def collect_facebook(
    url: str,
    browser: "BrowserManager",
    max_steps: int = 20,
) -> dict:
    """
    Thu thập thông tin từ một URL Facebook bất kỳ (profile / group / page).

    Trả về:
        {
            "url": str,
            "status": "ok" | "error" | "needs_user",
            "extracted_data": list[dict],
            "summary": str,
        }
    """
    if not browser.context:
        return {"url": url, "status": "error", "error": "Browser chưa khởi động."}

    page: Page = await browser.new_page()
    fb_crawler_info = None
    result = None
    try:
        logger.info(f"[collect_facebook] Đăng nhập và navigate tới: {url}")
        login_ok = await browser.ensure_login(page, url)
        if not login_ok:
            return {"url": url, "status": "error", "error": "Đăng nhập thất bại."}

        # Chờ trang ổn định
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)  # buffer thêm cho SPA render
        except Exception:
            pass

        # Giao cho crawler pipeline xử lý theo từng step
        fb_crawler_info = CrawlerInfo()
        if "/group" in url and "/user" not in url:
            result = await fb_crawler_info.run_group(page)
        else:
            # Profile or Page (2 cái này dùng chung 1 flow)
            if "/user" in url:
                # user này được refer từ group. phải click mới đi vào hẳn trang cá nhân chính
                try:
                    from core.actions import click_user_refer_group

                    await click_user_refer_group(page, url)

                except Exception as e:
                    logger.error(f"[collect_facebook] Lỗi khi click vào user: {e}")
                    raise

            # Tất cả URL profile/page (có hoặc không có /user) đều dùng chung flow này
            result = await fb_crawler_info.run_user_profile(page)

        if result is None:
            raise ValueError("Pipeline trả về None, không có dữ liệu.")

        status = (
            "needs_user" if "[Cần can thiệp]" in result.get("summary", "") else "ok"
        )

        return {
            "url": url,
            "status": status,
            "extracted_data": result["extracted_data"],
            "discovery_entity_ralationship": result.get(
                "discovery_entity_ralationship", []
            ),
            "summary": result["summary"],
        }

    except BaseException as e:
        logger.error(f"[collect_facebook] Bị gián đoạn/Lỗi khi thu thập {url}: {e}")
        extracted = fb_crawler_info.extracted_data if fb_crawler_info else []
        discovery = fb_crawler_info.discovery_entity if fb_crawler_info else []

        # Chỉ publish error lên Kafka nếu đã thu được ít nhất 1 trường dữ liệu
        # (tránh gửi payload rỗng khi lỗi xảy ra ngạy từ đầu, VD: login thất bại)
        has_meaningful_data = any(
            k not in ("_metadata",)
            for item in extracted
            for k in (item.keys() if isinstance(item, dict) else [])
        )

        if has_meaningful_data or discovery:
            kafka_publisher = KafkaPublisher()
            await kafka_publisher.publish(
                data={
                    "url": url,
                    "status": "error",
                    "extracted_data": extracted,
                    "discovery_entity_ralationship": discovery,
                    "summary": "Bị gián đoạn do lỗi hoặc người dùng ngắt (Ctrl+C)",
                    "error": str(e),
                },
                topic="entity_info_crawl_error",
            )
            logger.info(
                f"[collect_facebook] Đã lưu dữ liệu tạm vào Kafka topic 'entity_info_crawl_error'."
            )
        else:
            logger.warning(
                f"[collect_facebook] Không có dữ liệu ý nghĩa nào để lưu, bỏ qua publish Kafka."
            )

        # # Nếu đang chạy dở mà bị ngắt, cứu dữ liệu trong agent
        # if result is None:
        #     result = {
        #         "url": url,
        #         "status": "interrupted",
        #         "extracted_data": (
        #             fb_crawler_info.extracted_data if fb_crawler_info else []
        #         ),
        #         "discovery_entity_ralationship": (
        #             fb_crawler_info.discovery_entity if fb_crawler_info else []
        #         ),
        #         "summary": "Bị gián đoạn do lỗi hoặc người dùng ngắt (Ctrl+C)",
        #         "error": str(e),
        #     }
        # Trả về None để caller (run_collect.py) biết thu thập thất bại
        return None

    finally:
        try:
            await page.close()
        except Exception:
            pass
