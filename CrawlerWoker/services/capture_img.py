import logging
from playwright.async_api import Page

logger = logging.getLogger(__name__)


async def capture_avatar(page: Page, extracted_data: dict) -> str | None:
    """
    Lấy URL avatar lớn nhất (width/height >= 150) từ trang profile Facebook.
    Trả về URL ảnh hoặc None nếu không tìm thấy.
    """
    FIND_AVATAR_JS = """
    () => {
        const svgs = document.querySelectorAll('svg[aria-label][role="img"]');
        for (const svg of svgs) {
            const width = parseInt(svg.style.width) || parseInt(svg.getAttribute('width'));
            const height = parseInt(svg.style.height) || parseInt(svg.getAttribute('height'));
            if (!width || !height) continue;
            if (width < 150 || height < 150) continue;

            const image = svg.querySelector('image');
            if (!image) continue;

            const href = image.getAttribute('xlink:href');
            if (!href) continue;

            return href;
        }
        return null;
    }
    """

    try:
        url_avatar = await page.evaluate(FIND_AVATAR_JS)
        if url_avatar:
            logger.info(f"[capture_avatar] Tìm thấy avatar: {url_avatar}")
        else:
            logger.warning("[capture_avatar] Không tìm thấy avatar")
        return url_avatar
    except Exception as e:
        logger.error(f"[capture_avatar] Lỗi: {e}")
        return None


FIND_PHOTO_LINKS_JS = """
() => {
    const results = [];
    const anchors = document.querySelectorAll('a[href*="/photo"]');
    for (const a of anchors) {
        const href = a.href || '';
        if (!href.includes('fbid=')) continue;
        const img = a.querySelector('img');
        const imgSrc = img ? img.src : null;
        const rect = a.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        results.push({ href, img_src: imgSrc });
    }
    const seen = new Set();
    return results.filter(r => {
        if (seen.has(r.href)) return false;
        seen.add(r.href);
        return true;
    });
}
"""


async def capture_photos(page: Page, scroll_rounds: int = 2) -> list[dict]:
    """
    Scrape toàn bộ ảnh từ trang photos_by của Facebook.
    Trả về list { href, img_src }.
    """
    all_photos: dict[str, dict] = {}

    for round_i in range(scroll_rounds):
        try:
            photos: list[dict] = await page.evaluate(FIND_PHOTO_LINKS_JS)
        except Exception as e:
            logger.error(f"[capture_photos] Lỗi JS round {round_i + 1}: {e}")
            break

        new_count = 0
        for p in photos:
            if p["href"] not in all_photos:
                all_photos[p["href"]] = p
                new_count += 1

        logger.info(
            f"[capture_photos] Round {round_i + 1}: +{new_count} ảnh mới, tổng {len(all_photos)}"
        )

        if new_count == 0:
            logger.info("[capture_photos] Không có ảnh mới, dừng scroll")
            break

        # Scroll xuống để load thêm
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(1000)

    from core.actions import _scroll_to_top

    await _scroll_to_top(page)
    result = list(all_photos.values())
    logger.info(f"[capture_photos] Hoàn tất: {len(result)} ảnh")
    return result
