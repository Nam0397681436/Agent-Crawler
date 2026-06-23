"""
toolfb/collect_group.py — Thu thập thông tin một Facebook Group
================================================================
Flow:
  1. Đảm bảo đã đăng nhập
  2. Navigate tới group URL
  3. Giao cho FacebookAgent tự:
       - Phát hiện nút Join/Tham gia → click nếu chưa vào
       - Hoặc nếu đã vào / public → duyệt qua các tab (Thảo luận, Giới thiệu, Thành viên)
       - Scroll từng tab để load thêm bài viết / thành viên
       - extract_data mọi thông tin thấy được
  4. Trả về dict kết quả cho router
"""
import logging
import os
from playwright.async_api import Page
from core.agent import FacebookAgent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.browser import BrowserManager

logger = logging.getLogger(__name__)

# ── Prompt chuyên biệt cho Group ──────────────────────────────────────────────
_GROUP_TASK_TEMPLATE = """
Bạn đang ở trang Facebook Group: {group_url}

Thực hiện theo thứ tự sau:

### Bước 1 — Xử lý trạng thái tham gia
- Quan sát trang. Nếu thấy nút "Tham gia nhóm", "Join Group", "Yêu cầu tham gia":
    → click vào nút đó để gửi yêu cầu/tham gia.
    → Sau khi click, dùng extract_data với label="join_status" ghi lại trạng thái.
- Nếu thấy giao diện bình thường của group (có các tab, có bài viết) → nhóm công khai hoặc đã vào → bỏ qua bước này.
- Nếu thấy nút "Đã gửi yêu cầu" / "Request sent" → ghi nhận rồi tiếp tục đọc thông tin công khai.

### Bước 2 — Thu thập thông tin cơ bản (tab Giới thiệu / About)
- Tìm tab "Giới thiệu" hoặc "About" trên thanh điều hướng của group → click vào.
- Chờ trang load rồi extract_data với label="group_about" toàn bộ thông tin: mô tả nhóm, nội quy, số thành viên, ngày thành lập, quyền riêng tư.
- Scroll xuống để xem thêm nếu cần.

### Bước 3 — Thu thập bài viết (tab Thảo luận / Posts / Discussion)
- Quay lại / tìm tab "Thảo luận", "Bài viết", "Discussion" → click vào.
- Scroll xuống ít nhất 3 lần để load thêm bài viết.
- Với mỗi bài viết thấy được: extract_data với label="post" ghi lại tên tác giả, nội dung, thời gian (nếu thấy).
- Thu thập tối đa 10 bài viết rồi dừng.

### Bước 4 — Thu thập danh sách thành viên (tab Thành viên / Members)
- Tìm tab "Thành viên", "Members" → click vào.
- Scroll xuống 2 lần.
- extract_data với label="members" liệt kê danh sách tên thành viên thấy được (tối đa 20 người).

### Kết thúc
- Sau khi hoàn thành các bước trên, gọi done với summary tổng hợp toàn bộ thông tin đã thu thập.
- Nếu bất kỳ bước nào gặp captcha hoặc yêu cầu xác minh → gọi ask_user ngay lập tức.
""".strip()


async def collect_group(
    group_url: str,
    browser: "BrowserManager",
    max_steps: int = 60,
) -> dict:
    """
    Thu thập thông tin từ một Facebook Group.

    Tham số:
        group_url — URL đầy đủ của group (vd: https://www.facebook.com/groups/123456)
        browser   — BrowserManager đã được start()
        max_steps — giới hạn số bước agent (mặc định 60)

    Trả về dict:
        {
            "url": str,
            "extracted_data": list[dict],
            "summary": str,
            "status": "ok" | "error" | "needs_user"
        }
    """
    if not browser.context:
        logger.error("[collect_group] BrowserManager chưa được start().")
        return {"url": group_url, "status": "error", "error": "Browser chưa khởi động."}

    # Tạo page mới, đảm bảo đăng nhập, rồi navigate vào group
    page: Page = await browser.new_page()
    try:
        logger.info(f"[collect_group] Đăng nhập và navigate tới: {group_url}")
        login_ok = await browser.ensure_login(page, group_url)
        if not login_ok:
            logger.error("[collect_group] Đăng nhập thất bại.")
            return {"url": group_url, "status": "error", "error": "Đăng nhập thất bại."}

        # Chờ trang ổn định
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass  # networkidle có thể timeout trên SPA — không sao

        # Giao cho FacebookAgent xử lý toàn bộ flow
        task_prompt = _GROUP_TASK_TEMPLATE.format(group_url=group_url)
        agent = FacebookAgent(
            task=task_prompt,
            max_steps=max_steps,
            model=os.getenv("AGENT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o")),
        )
        result = await agent.run(page)

        # Map trạng thái từ agent về status chuẩn
        if "[Cần can thiệp]" in result.get("summary", ""):
            status = "needs_user"
        else:
            status = "ok"

        return {
            "url": group_url,
            "status": status,
            "extracted_data": result["extracted_data"],
            "summary": result["summary"],
        }

    except Exception as e:
        logger.error(f"[collect_group] Lỗi không mong đợi: {e}")
        return {"url": group_url, "status": "error", "error": str(e)}

    finally:
        try:
            await page.close()
        except Exception:
            pass
