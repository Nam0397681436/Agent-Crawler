import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def human_like_type(page, text: str):
    """
    Nhập văn bản mô phỏng tốc độ gõ phím thực tế của con người.
    """
    for char in text:
        # Gõ ký tự
        await page.keyboard.type(char)
        # Delay ngẫu nhiên giữa các ký tự (ví dụ từ 50ms đến 150ms)
        await asyncio.sleep(random.uniform(0.15, 0.5))


async def login_fb(self, url) -> bool:
    """
    Ensure we are logged into Facebook before navigating to the target URL.

    Strategy:
    1. Always open facebook.com HOMEPAGE first – this is the only reliable
       place where the login form appears.  Search/group URLs return an empty
       page (not a login form) when the user is logged out.
    2. If the login form is not visible on the homepage → already logged in.
    3. If the login form is visible → fill credentials → wait for it to hide.
    4. Finally, navigate to the actual target URL.
    """
    homepage = "https://www.facebook.com"

    # Reuse the existing page if possible, or create a fresh one
    if not self.page:
        await self.launch_page(homepage)
    else:
        # Page may have been closed by a previous task; try to reuse it
        try:
            await self.page.goto(homepage)
        except Exception:
            # Page is closed or stale – open a new one
            logger.info("[*] Previous page is closed. Opening a new page...")
            self.page = await self.context.new_page()
            await self.page.goto(homepage)

    page = self.page
    email_selector = "input[name='email']"
    password_selector = "input[name='pass']"
    email = "nam0397681436@gmail.com"
    pwd = "Namtrautrelop10a2"

    # Check login state on the homepage
    try:
        if not await page.locator(email_selector).is_visible(timeout=5000):
            logger.info("[+] Already logged into Facebook. Navigating to target URL...")
            await page.goto(url)
            self.is_login = True
            return True
    except Exception as e:
        logger.error(f"[-] Error checking login form: {e}")

    # Perform login
    logger.info("[*] Login form detected. Filling credentials...")
    try:
        await page.locator(email_selector).click()
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await human_like_type(page, email)

        await page.locator(password_selector).click()
        await asyncio.sleep(random.uniform(0.5, 1.0))
        await human_like_type(page, pwd)

        await page.keyboard.press("Enter")
    except Exception as e:
        logger.error(f"[-] Error during credential input: {e}")
        self.is_login = False
        return False

    # Wait for login form to disappear (page transition after Enter)
    try:
        logger.info("[*] Waiting for login form to disappear...")
        await page.wait_for_selector(email_selector, state="hidden", timeout=15000)
    except Exception as e:
        logger.warning(f"[-] Login form still visible: {e}")
        self.is_login = False
        return False

    _auth_bad_patterns = [
        "login",
        "checkpoint",
        "two_step_verification",
        "recover",
        "hacked",
        "auth_platform",  # Xác nhận đăng nhập từ thiết bị mới
    ]

    async def _is_blocked() -> bool:
        return any(p in page.url for p in _auth_bad_patterns)

    # Give a moment for redirect to settle
    await asyncio.sleep(1.5)

    if await _is_blocked():
        logger.info(
            f"[*] Detected 2FA / checkpoint page ({page.url}). "
            "Waiting up to 90s for manual verification..."
        )
        try:
            # Poll until URL leaves the blocked zone
            await page.wait_for_function(
                """() => {
                        const url = window.location.href;
                        const blocked = ["login", "checkpoint", "two_step", "recover", "hacked", "auth_platform"];
                        return !blocked.some(p => url.includes(p));
                    }""",
                timeout=90000,
            )
            logger.info("[+] Manual 2FA completed. Continuing...")
        except Exception as e:
            logger.warning(f"[-] 2FA timeout or still blocked: {e}")
            self.is_login = False
            return False

    # Final sanity check: email form must NOT be visible (we might have bounced back)
    try:
        if await page.locator(email_selector).is_visible(timeout=3000):
            logger.warning(
                "[-] Login form reappeared. Login failed (wrong password / CAPTCHA?)."
            )
            self.is_login = False
            return False
    except Exception:
        pass

    # Navigate to the real target URL
    logger.info(f"[*] Login confirmed. Navigating to: {url}")
    await page.goto(url)

    self.is_login = True
    logger.info("[+] Facebook login successful.")
    return True
