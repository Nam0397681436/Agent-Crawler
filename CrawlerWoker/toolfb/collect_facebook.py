"""
toolfb/collect_facebook.py — Thu thập thông tin từ bất kỳ URL Facebook nào
============================================================================
Nhận vào 1 URL (profile / group / page), agent nhìn screenshot tự quyết định
cần click tab nào, scroll ở đâu để lấy hết thông tin.

Không cần biết trước URL là loại gì — agent tự nhận diện qua ảnh.
"""

import json
import logging
import os
from playwright.async_api import Page
from steps.start_pipeline import CrawlerInfo
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.browser import BrowserManager

logger = logging.getLogger(__name__)

# ── Prompt điều hướng và trích xuất dữ liệu ─────────────────────────────────
_TASK_TEMPLATE = """
URL: {url}
Xác định loại trang qua screenshot: Profile, Group, hay Page.

QUY TẮC CHUNG (bắt buộc):
- Mỗi tab thực hiện ĐÚNG 1 LẦN theo thứ tự, KHÔNG quay lại.
- extract_data CHỈ dùng trong tab Giới thiệu. TUYỆT ĐỐI không gọi ở tab khác.
- Không join group, kết bạn, nhắn tin.
- Captcha/xác minh → ask_user ngay.
- Bỏ qua các tab: Reels, Sự kiện, Đáng chú ý, Checkin, Bài đánh giá, Xem thêm.
- Không phải profile/group/page → done ngay.

PROFILE / PAGE — Thứ tự: Tất cả → Giới thiệu → Bạn bè (Page: Người theo dõi) → Ảnh (Page: bỏ) → done
[1] Tất cả: Scroll 30 lần, KHÔNG extract_data.
[2] Giới thiệu: Click tab → extract_data header (Tên, bạn bè, theo dõi) → click từng menu phụ (Tổng quan, Công việc, Nơi sống, Liên hệ...) → ghi nhận nội dung mỗi menu → KHÔNG scroll.
[3] Bạn bè/Người theo dõi: Click tab → hệ thống tự thu thập.
[4] Ảnh (Profile only): Click tab → hệ thống tự thu thập → done.

GROUP — Thứ tự: Thảo luận → Giới thiệu → Thành viên/Mọi người → done
[1] Thảo luận: Scroll 30 lần, KHÔNG extract_data.
[2] Giới thiệu: Click tab → extract_data (tên, thành viên, mô tả, quy tắc...) → scroll nhẹ 2 lần → ghi nhận phần còn lại.
[3] Thành viên/Mọi người: Click tab → hệ thống tự thu thập.
""".strip()


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
        task_prompt = _TASK_TEMPLATE.format(url=url)
        fb_crawler_info = CrawlerInfo()
        result = await fb_crawler_info.run_user_profile(page)

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
        logger.error(f"[collect_facebook] Bị gián đoạn/Lỗi: {e}")

        # Nếu đang chạy dở mà bị ngắt, cứu dữ liệu trong agent
        if result is None:
            result = {
                "url": url,
                "status": "interrupted",
                "extracted_data": fb_crawler_info.extracted_data if fb_crawler_info else [],
                "discovery_entity_ralationship": (
                    fb_crawler_info.discovery_entity if fb_crawler_info else []
                ),
                "summary": "Bị gián đoạn do lỗi hoặc người dùng ngắt (Ctrl+C)",
                "error": str(e),
            }
        else:
            result["status"] = "error"
            result["error"] = str(e)

        with open("result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    finally:
        try:
            await page.close()
        except Exception:
            pass
