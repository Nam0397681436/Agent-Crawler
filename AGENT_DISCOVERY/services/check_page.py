import asyncio
import logging
from typing import Dict, Any

from playwright.async_api import Page, BrowserContext

from services.mouse_action import human_like_click

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Các selector popup IN-PAGE của Facebook (modal, drawer, banner)
# ---------------------------------------------------------------------------
_FACEBOOK_CLOSE_SELECTORS = [
    '[aria-label="Close"]',
    '[aria-label="Đóng"]',
    '[aria-label="Not now"]',
    '[aria-label="Lúc khác"]',
    '[aria-label="Dismiss"]',
    '[aria-label="Bỏ qua"]',
    'div[aria-label="Close"]',
    'div[aria-label="Đóng"]',
    # Nút "Block" trong popup xin phép thông báo của Facebook (in-page fallback)
    'button:has-text("Block")',
    'button:has-text("Chặn")',
    # Nút "No thanks" / "Never" trong popup lưu mật khẩu in-page (hiếm)
    'button:has-text("No thanks")',
    'button:has-text("Never")',
    'button:has-text("Không, cảm ơn")',
]


async def handle_popup(page: Page) -> Dict[str, Any]:
    """
    Đóng các popup nhẹ IN-PAGE của Facebook (modal, notification banner, …).

    Không xử lý captcha/checkpoint.
    Trả về dict tóm tắt kết quả.
    """
    clicked = []
    errors = []

    for selector in _FACEBOOK_CLOSE_SELECTORS:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            if count <= 0:
                continue

            target = locator.first
            await human_like_click(
                page=page,
                locator=target,
                timeout_ms=1200,
                move_steps_min=6,
                move_steps_max=16,
                hover_wait_min_ms=80,
                hover_wait_max_ms=250,
                click_hold_min_ms=50,
                click_hold_max_ms=120,
                debug=False,
            )
            await page.wait_for_timeout(300)
            clicked.append(selector)
            logger.info(f"[handle_popup] clicked in-page popup: selector={selector}")
            break  # Chỉ cần đóng một popup mỗi lần gọi

        except Exception as exc:
            errors.append({"selector": selector, "error": str(exc)})
            logger.debug(f"[handle_popup] skip selector={selector}, error={exc}")

    return {
        "status": "completed",
        "clicked_count": len(clicked),
        "clicked_selectors": clicked,
        "errors": errors,
    }


def register_browser_dialog_handlers(context: BrowserContext):
    """
    Đăng ký handler tự động cho CÁC DIALOG CỦA BROWSER (không phải in-page):
      - Notification permission popup  → tự động từ chối (grant_permissions rỗng)
      - Save password popup            → Chrome arg --password-store=basic giải quyết ở tầng launch
      - JS alert/confirm/prompt        → tự động dismiss

    Gọi hàm này MỘT LẦN ngay sau khi khởi tạo BrowserContext và await kết quả.
    Trả về coroutine để caller có thể await.
    """
    # Tự động dismiss dialog JS alert/confirm/prompt
    def _on_dialog(dialog):
        asyncio.ensure_future(dialog.dismiss())
        logger.debug(f"[browser_dialog] dismissed JS dialog type={dialog.type}")

    # Áp dụng handler cho mọi page mới mở trong context
    def _on_new_page(page: Page):
        page.on("dialog", _on_dialog)

    context.on("page", _on_new_page)

    # Từ chối quyền notification cho Facebook → popup "Allow / Block" sẽ không xuất hiện
    async def _deny():
        try:
            await context.grant_permissions([], origin="https://www.facebook.com")
            logger.info("[browser_dialog] Notification permission denied for facebook.com")
        except Exception as e:
            logger.debug(f"[browser_dialog] grant_permissions error: {e}")

    return _deny()


async def dismiss_popups(page: Page) -> None:
    """
    Tiện ích: thử đóng tất cả popup in-page trên trang hiện tại.
    Lặp tối đa 3 lần để bắt trường hợp popup xuất hiện liên tiếp.
    """
    for _ in range(3):
        result = await handle_popup(page)
        if result["clicked_count"] == 0:
            break
        await asyncio.sleep(0.5)
