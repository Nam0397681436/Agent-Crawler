"""
toolfb/collect_facebook.py — Thu thập thông tin từ bất kỳ URL Facebook nào
============================================================================
Nhận vào 1 URL (profile / group / page), agent nhìn screenshot tự quyết định
cần click tab nào, scroll ở đâu để lấy hết thông tin.

Không cần biết trước URL là loại gì — agent tự nhận diện qua ảnh.
"""

import logging
import os
from playwright.async_api import Page
from core.agent import FacebookAgent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.browser import BrowserManager

logger = logging.getLogger(__name__)

# ── Prompt kết hợp điều hướng và trích xuất dữ liệu (CỰC KỲ NGHIÊM NGẶT) ──────────────────────────
_TASK_TEMPLATE = """
Bạn đang ở URL Facebook: {url}
Nhìn vào screenshot để xác định đây là **Profile cá nhân**, **Group**, hay **Page**.
Thực hiện đúng quy trình tương ứng bên dưới.

---

## 🔴 QUY TẮC CHUNG (áp dụng cho mọi loại)
- KHÔNG join group, KHÔNG kết bạn, KHÔNG gửi tin nhắn.
- Gặp captcha hoặc xác minh → gọi `ask_user` ngay.
- Không click lại tab đã click rồi.
- Đã duyệt hết tab → gọi `done` kèm tóm tắt, không cần chờ hết bước.
- Click lỗi hoặc không thấy tab → bỏ qua, chuyển tab tiếp theo luôn.
- Các tab BỎ QUA (không click): `Reels`, `Sự kiện`, `Đáng chú ý`, `Checkin`, `Bài đánh giá`, `Xem thêm`.
- `scroll` và `hover_users` tự động cuộn về đầu trang khi xong — KHÔNG cần gọi `scroll_to_top` sau các action này.

---

## 👤 PROFILE CÁ NHÂN

**Thứ tự ưu tiên:** Giới thiệu → Bạn bè → Ảnh → Tất cả → dừng.

**Tab "Giới thiệu":**
- Click từng menu phụ: `Tổng quan`, `Công việc và học vấn`, `Nơi từng sống`, `Thông tin liên hệ`, `Chi tiết trang`...
- Tại MỖI menu phụ: đọc màn hình → gọi `extract_data` ngay với từng khối thông tin thấy được → scroll, hệ thống tự cuộn về đầu trang, sau đó click menu phụ tiếp theo.
- KHÔNG được chuyển sang menu phụ khác nếu chưa `extract_data` hết thông tin đang hiển thị.

**Tab "Bạn bè":**
- Gọi `hover_users` ngay sau khi click vào tab.
- `hover_users` tự động thu thập URL bạn bè và cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

**Tab "Ảnh":**
- Click vào tab → hệ thống tự động thu thập ảnh và cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

**Tab "Tất cả":**
- KHÔNG extract_data dù thấy thông tin cá nhân.
- Scroll 10 lần để thu bài viết qua API, hệ thống tự cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

---
## 👥 GROUP
**Thứ tự ưu tiên:** Giới thiệu → Thảo luận → Thành viên → dừng.
**KHÔNG click:** Ảnh, Video, File, Media.

**Tab "Giới thiệu":**
- Click từng menu phụ nếu có.
- Tại MỖI menu phụ: đọc màn hình → gọi `extract_data` ngay với từng khối thông tin thấy được (mô tả, quy tắc, số thành viên...) → scroll, hệ thống tự cuộn về đầu trang, sau đó click menu phụ tiếp theo.
- KHÔNG được chuyển sang menu phụ khác nếu chưa `extract_data` hết thông tin đang hiển thị.

**Tab "Thảo luận":**
- KHÔNG extract_data.
- Scroll 20 lần để thu bài viết qua API, hệ thống tự cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

**Tab "Thành viên" / "Mọi người":**
- Gọi `hover_users` ngay sau khi click vào tab.
- `hover_users` tự động thu thập URL thành viên và cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

---
## 📄 PAGE

**Thứ tự ưu tiên:** Giới thiệu → Người theo dõi → Tất cả → dừng.
**KHÔNG click:** Ảnh, Video, File, Media, Reels.

**Tab "Giới thiệu":**
- Click từng menu phụ nếu có.
- Tại MỖI menu phụ: đọc màn hình → gọi `extract_data` ngay với từng khối thông tin thấy được → scroll, hệ thống tự cuộn về đầu trang, sau đó click menu phụ tiếp theo.
- KHÔNG được chuyển sang menu phụ khác nếu chưa `extract_data` hết thông tin đang hiển thị.

**Tab "Người theo dõi" / "Follower":**
- Gọi `hover_users` ngay sau khi click vào tab.
- `hover_users` tự động thu thập URL người theo dõi và cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

**Tab "Tất cả":**
- KHÔNG extract_data dù thấy thông tin.
- Scroll 20 lần để thu bài viết qua API, hệ thống tự cuộn về đầu trang khi xong.
- Chuyển sang tab tiếp theo luôn.

---

## 📋 QUY TẮC EXTRACT_DATA
- Chỉ gọi `extract_data` khi đang ở tab **Giới thiệu** (mọi loại).
- Mỗi khối thông tin = 1 lần gọi `extract_data`. Ví dụ: label="Giáo dục", content="Học viện Công nghệ Bưu chính Viễn thông...".
- KHÔNG gọi `extract_data` khi đang ở tab Tất cả, Thảo luận, Bạn bè, Thành viên, Người theo dõi, Ảnh.
---

## 🔄 CHU TRÌNH CHUẨN TẠI MỖI TAB
1. Click tab/menu phụ → `wait` 1000ms.
2. Thực hiện đúng hành động của tab đó (scroll / hover_users / extract_data...).
3. Hệ thống tự cuộn về đầu trang — chuyển sang tab tiếp theo luôn.
""".strip()


async def collect_facebook(
    url: str,
    browser: "BrowserManager",
    max_steps: int = 25,
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
    agent = None
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

        # Giao cho agent tự nhìn screenshot và quyết định
        task_prompt = _TASK_TEMPLATE.format(url=url)
        agent = FacebookAgent(
            task=task_prompt,
            max_steps=max_steps,
            model=os.getenv("AGENT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o")),
        )
        result = await agent.run(page)

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
                "extracted_data": agent.extracted_data if agent else [],
                "discovery_entity_ralationship": (
                    agent.discovery_entity if agent else []
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
