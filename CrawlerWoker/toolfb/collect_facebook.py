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

Nhìn vào screenshot để xác định đây là Profile, Group hay Page.
Nhiệm vụ của bạn gồm 2 phần BẮT BUỘC phải thực hiện song song:
1. ĐIỀU HƯỚNG: click tab chính, khám phá các menu phụ, và scroll để kích hoạt API.
2. TRÍCH XUẤT DỮ LIỆU: Bóc tách toàn bộ thông tin văn bản hiển thị trên màn hình.

### 🔴 QUY TẮC TỐI THƯỢNG VỀ TRÍCH XUẤT DỮ LIỆU (KHÔNG ĐƯỢC LÀM TRÁI):
1. MỖI KHI BẠN NHÌN THẤY THÔNG TIN CÁ NHÂN TRÊN MÀN HÌNH (như "Giới tính", "Ngày sinh", "Học vấn", "Công việc", "Mối quan tâm", "Nơi sống", "Số điện thoại"...), BẠN BẮT BUỘC PHẢI GỌI CÔNG CỤ `extract_data` NGAY LẬP TỨC!
2. KHÔNG ĐƯỢC PHÉP click sang trang khác hoặc scroll đi chỗ khác nếu bạn chưa dùng `extract_data` để lấy toàn bộ các thông tin đang hiển thị trên màn hình hiện tại.
3. Cứ 1 khối thông tin (ví dụ: khối "Giáo dục"), hãy gọi 1 lần `extract_data` với label="Giáo dục" và content là toàn bộ text bên trong khối đó (ví dụ: "Học viện Công nghệ Bưu chính Viễn thông...").
4. TUYỆT ĐỐI KHÔNG ỷ lại vào hệ thống network API. Dữ liệu trên màn hình là do BẠN phải tự đọc và tự trích xuất bằng mắt (vision) của chính bạn.

### 🔵 QUY TẮC QUAN TRỌNG VỀ SCROLL VÀ KHÁM PHÁ:

**1. Khám phá menu phụ (Sub-tabs):**
- Khi click vào tab chính (Ví dụ: "Giới thiệu" / "About"), HÃY TÌM KIẾM CÁC MENU PHỤ bên trái hoặc bên trong trang (như "Tổng quan", "Thông tin cá nhân", "Trình độ học vấn", "Nơi từng sống", "Mối quan tâm"...).
- Bạn PHẢI tự động click vào TỪNG MENU PHỤ để khám phá, chờ load, và scroll để hệ thống lấy dữ liệu. Đừng chỉ click tab chính rồi bỏ đi.

**2. Quy tắc Scroll & Điều hướng:**
- Khi muốn TÌM KIẾM CÁC MENU PHỤ hoặc nút bấm để khám phá, hãy dùng công cụ `scroll_short` (cuộn ngắn). Điều này giúp ảnh screenshot cập nhật từ từ và bạn không bị lướt qua mất các nút bấm quan trọng.
- Khi muốn lấy dữ liệu nhanh qua API, hãy dùng công cụ `scroll` (cuộn dài/nhiều lần).
- SAU KHI scroll xong một trang, BẮT BUỘC gọi `scroll_to_top` để quay lại đầu trang.
- Chỉ khi quay lại đầu trang, các thanh tab và menu phụ mới hiển thị để bạn click sang mục tiếp theo.

**3. Chu trình chuẩn tại mỗi mục:**
  1. Click mục (tab chính hoặc menu phụ) → wait 2000ms.
  2. scroll (vài lần tuỳ trang).
  3. scroll_to_top ← BẮT BUỘC.
  4. Lặp lại với mục chưa khám phá.

### Trình tự khám phá (ƯU TIÊN LẤY THÔNG TIN HỒ SƠ / THỰC THỂ)

Mục tiêu chính của bạn là thu thập THÔNG TIN CHI TIẾT (thông tin cá nhân, liên hệ, học vấn, thành viên, file, ảnh/video...). Tạm thời KHÔNG QUAN TÂM đến nội dung các bài đăng thông thường.

1. **TRƯỜNG HỢP ĐẶC BIỆT KHI XEM THÀNH VIÊN NHÓM**:
   - Nếu bạn thấy nút "Xem trang cá nhân" (thường nằm cạnh nút Nhắn tin), BẠN BẮT BUỘC PHẢI CLICK VÀO NÓ ngay lập tức. Điều này giúp bạn chuyển sang trang cá nhân đầy đủ của user để lấy được nhiều thông tin hơn, thay vì chỉ xem tóm tắt trong nhóm.
2. **Ưu tiên TÌM & CLICK các tab/menu chứa THÔNG TIN CỐ LÕI**:
   - Trên thanh điều hướng chính, HÃY TÌM VÀ CLICK CÁC TAB: `Giới thiệu` (About), `Bạn bè` / `Mọi người` / `Thành viên` (Members), `File phương tiện` / `Ảnh` / `Video` (Media), `File`...
   - Tại tab `Giới thiệu`, **BẮT BUỘC PHẢI CLICK TẤT CẢ** các menu phụ hiện ra (ví dụ: `Tổng quan`, `Công việc và học vấn`, `Nơi từng sống`, `Thông tin liên hệ`, `Chi tiết trang`...). Đừng bỏ sót thông tin cá nhân nào!
2. **Các tab NÊN BỎ QUA (Không ưu tiên click)**:
   - `Bài viết` (Posts), `Thảo luận` (Discussion), `Đáng chú ý` (Featured), `Reels`, `Sự kiện` (Events), Xem thêm, Checkin, Bài đánh giá đã viết.
   - Nếu bạn lỡ click vào tab chứa bài viết feed, hãy chỉ scroll 1-2 lần rồi lập tức `scroll_to_top` và tìm tab Giới thiệu/Thông tin để click.
3. **Chu trình đặc biệt tại tab Bạn bè / Mọi người / Thành viên — PHẢI DÙNG HOVER**:
   - Ngay SAU KHI click vào tab `Bạn bè` / `Mọi người` / `Thành viên`, **PHẢI GỌI NGAY `hover_users`** (thay vì chỉ scroll thông thường).
   - `hover_users` sẽ tự động di chuột qua từng thẻ người dùng để kích hoạt API thu thập thông tin user, sau đó cuộn xuống và lặp lại.
   - Bạn KHÔNG CẦN scroll thêm sau khi `hover_users` — nó đã tự cuộn xong.
   - Sau khi `hover_users` hoàn thành → gọi `scroll_to_top` → click tab quan trọng tiếp theo.
4. **Chu trình tại các tab quan trọng khác (Giới thiệu, File, Media)**:
   - Click tab/menu phụ → chờ load 2000ms → scroll sâu xuống → `scroll_to_top` → click mục tiếp theo.
### Các quy tắc khác
- Nếu không thấy tab hoặc click lỗi → bỏ qua, scroll_to_top rồi đi tiếp.
- Gặp captcha hoặc yêu cầu xác minh → gọi `ask_user` ngay lập tức.
- Khi đã duyệt hết các tab và menu phụ có thể truy cập → gọi `done` kèm tóm tắt.
- Không click vào các mục đã click (ví dụ: đã click vào tab "Bạn bè" và đã scroll xong rồi thì không click lại tab đó nữa). 
- Nếu đã click hết các tab thì dừng chương trình không cần chạy hết tất cả các bước đánh status = done để dừng vòng lặp khám phá.
- KHÔNG join group, KHÔNG kết bạn, KHÔNG gửi tin nhắn.
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
