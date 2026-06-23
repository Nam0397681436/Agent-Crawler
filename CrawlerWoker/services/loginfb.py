"""
services/loginfb.py — Facebook login service
=============================================
Tách hoàn toàn khỏi BrowserManager. Nhận page + browser (để
truy cập context khi cần tạo lại page) làm tham số tường minh,
không dùng `self` của BrowserManager nữa.
"""
import asyncio
import logging
import random

from playwright.async_api import Page

logger = logging.getLogger(__name__)

_AUTH_BAD_PATTERNS = [
    "login",
    "checkpoint",
    "two_step_verification",
    "recover",
    "hacked",
    "auth_platform",
]


async def human_like_type(page: Page, text: str) -> None:
    """Gõ từng ký tự với độ trễ ngẫu nhiên mô phỏng con người."""
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.12, 0.45))


async def login_fb(browser, page: Page, target_url: str) -> bool:
    """
    Đảm bảo đã đăng nhập Facebook, sau đó navigate tới target_url.

    Tham số:
        browser     — BrowserManager instance (để lấy context tạo page mới nếu cần)
        page        — Page Playwright hiện tại
        target_url  — URL đích sau khi đăng nhập xong

    Trả về True nếu thành công, False nếu thất bại.
    """
    import os
    homepage = "https://www.facebook.com"
    email = os.getenv("FB_EMAIL", "")
    pwd   = os.getenv("FB_PASSWORD", "")

    # --- Đảm bảo page còn sống và đang ở homepage ---
    page = await _ensure_page_at(browser, page, homepage)
    if page is None:
        return False

    email_sel    = "input[name='email']"
    password_sel = "input[name='pass']"

    # --- Kiểm tra đã đăng nhập chưa ---
    try:
        if not await page.locator(email_sel).is_visible(timeout=5000):
            logger.info("[login] Đã đăng nhập sẵn. Chuyển tới URL đích...")
            await page.goto(target_url, timeout=60000)
            return True
    except Exception as e:
        logger.debug(f"[login] Kiểm tra form login: {e}")

    if not email or not pwd:
        logger.error("[login] Chưa cấu hình FB_EMAIL / FB_PASSWORD trong .env")
        return False

    # --- Điền thông tin đăng nhập ---
    logger.info("[login] Phát hiện form đăng nhập. Đang điền thông tin...")
    try:
        await page.locator(email_sel).click()
        await asyncio.sleep(random.uniform(0.4, 0.9))
        await human_like_type(page, email)

        await page.locator(password_sel).click()
        await asyncio.sleep(random.uniform(0.4, 0.9))
        await human_like_type(page, pwd)

        await page.keyboard.press("Enter")
    except Exception as e:
        logger.error(f"[login] Lỗi điền form: {e}")
        return False

    # --- Chờ form biến mất ---
    try:
        await page.wait_for_selector(email_sel, state="hidden", timeout=15000)
    except Exception as e:
        logger.warning(f"[login] Form vẫn còn hiển thị: {e}")
        return False

    await asyncio.sleep(1.5)

    # --- Xử lý 2FA / checkpoint ---
    if _is_blocked(page.url):
        logger.info(f"[login] Trang checkpoint/2FA ({page.url}). Chờ xác minh tay tối đa 90s...")
        try:
            await page.wait_for_function(
                """() => {
                    const blocked = ["login","checkpoint","two_step","recover","hacked","auth_platform"];
                    return !blocked.some(p => window.location.href.includes(p));
                }""",
                timeout=90_000,
            )
            logger.info("[login] Xác minh thủ công hoàn tất.")
        except Exception as e:
            logger.warning(f"[login] Hết thời gian chờ 2FA: {e}")
            return False

    # --- Kiểm tra cuối: form không được xuất hiện lại ---
    try:
        if await page.locator(email_sel).is_visible(timeout=3000):
            logger.warning("[login] Form tái xuất hiện — sai mật khẩu hoặc CAPTCHA?")
            return False
    except Exception:
        pass

    logger.info(f"[login] Đăng nhập thành công. Chuyển tới: {target_url}")
    await page.goto(target_url, timeout=60000)
    return True


def _is_blocked(url: str) -> bool:
    return any(p in url for p in _AUTH_BAD_PATTERNS)


async def _ensure_page_at(browser, page: Page | None, url: str) -> Page | None:
    """
    Đảm bảo page đang sống và ở đúng URL.
    Nếu page đã đóng/stale → tạo page mới từ context.
    Trả về page hợp lệ hoặc None nếu không thể tạo.
    """
    if page is None:
        try:
            page = await browser.context.new_page()
            await page.goto(url, timeout=60000)
            return page
        except Exception as e:
            logger.error(f"[login] Không thể tạo page mới: {e}")
            return None

    try:
        await page.goto(url, timeout=60000)
        return page
    except Exception:
        logger.info("[login] Page cũ đã đóng. Tạo page mới...")
        try:
            page = await browser.context.new_page()
            await page.goto(url, timeout=60000)
            return page
        except Exception as e:
            logger.error(f"[login] Không thể tạo page mới: {e}")
            return None
