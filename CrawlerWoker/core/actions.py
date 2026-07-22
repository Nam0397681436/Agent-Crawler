"""
core/actions.py — Lớp 2: Action space
=======================================
Định nghĩa "menu" hành động agent được phép thực hiện.

Mỗi action gồm:
  schema  — OpenAI function calling schema (để LLM biết cú pháp)
  handle  — coroutine thực thi qua Playwright

Muốn thêm hành vi mới (gửi tin nhắn, báo cáo, v.v.)
→ thêm 1 entry vào ACTION_REGISTRY, không cần sửa agent.py.
"""

import asyncio
import logging
import random
from typing import Any

from playwright.async_api import Page
from services.mouse_action import human_like_click
from services.scroll_antibot import smart_scroll_for_api, smooth_wheel_scroll

logger = logging.getLogger(__name__)


async def _click(page: Page, element_id: str, **_) -> dict:
    """Click vào phần tử có data-agent-id = element_id."""
    locator = page.locator(f"[data-agent-id='{element_id}']")
    try:
        await human_like_click(
            page=page,
            locator=locator,
            timeout_ms=5000,
            debug=False,
        )
        await page.wait_for_timeout(random.randint(600, 1200))
        return {"status": "ok", "action": "click", "element_id": element_id}
    except Exception as e:
        return {
            "status": "error",
            "action": "click",
            "element_id": element_id,
            "error": str(e),
        }


async def _type_text(page: Page, element_id: str, text: str, **_) -> dict:
    """Click vào input rồi gõ text theo kiểu con người."""
    locator = page.locator(f"[data-agent-id='{element_id}']")
    try:
        await locator.click(timeout=5000)
        await asyncio.sleep(random.uniform(0.3, 0.7))
        for char in text:
            await page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.08, 0.30))
        return {
            "status": "ok",
            "action": "type_text",
            "element_id": element_id,
            "text": text,
        }
    except Exception as e:
        return {"status": "error", "action": "type_text", "error": str(e)}


async def _scroll(
    page: Page,
    direction: str = "down",
    times: int = 3,
    scroll_rounds: int = 0,
    min_wait_ms: int = 1500,
    max_wait_ms: int = 3000,
    **_,
) -> dict:
    """Cuộn trang (anti-bot aware scroll). scroll_rounds là alias của times."""
    loops = scroll_rounds or times  # scroll_rounds ưu tiên nếu được truyền vào
    try:
        import time

        start_time = time.perf_counter()
        await smart_scroll_for_api(
            page,
            max_scroll_loops=loops,
            min_wait_ms=min_wait_ms,
            max_wait_ms=max_wait_ms,
            debug=False,
        )

        await _scroll_to_top(page)
        return {
            "status": "ok",
            "action": "scroll",
            "direction": direction,
            "time_scroll": time.perf_counter() - start_time,
        }
    except Exception as e:
        return {"status": "error", "action": "scroll", "error": str(e)}


async def _scroll_to_top(page: Page, **_) -> dict:
    """Cuộn từ từ về gần đầu trang để thanh tab điều hướng hiện trở lại (chừa ~500px)."""
    try:
        from services.scroll_antibot import smooth_wheel_scroll

        TARGET_Y = random.randint(300, 400)  # Pixel cách đỉnh trang — luôn cố định

        scroll_y = await page.evaluate("window.scrollY || window.pageYOffset || 0")
        distance_to_scroll = TARGET_Y - scroll_y

        if abs(distance_to_scroll) > 10:

            # Bước 1: cuộn mượt bằng wheel để trông tự nhiên (anti-bot)
            await smooth_wheel_scroll(
                page=page, distance=distance_to_scroll, min_steps=7, max_steps=12
            )
            await page.wait_for_timeout(random.randint(300, 500))

        # Bước 2: snap chính xác về TARGET_Y bằng JS (bỏ qua noise của wheel)
        await page.evaluate(
            f"window.scrollTo({{ top: {TARGET_Y}, left: 0, behavior: 'instant' }})"
        )
        await page.wait_for_timeout(random.randint(200, 400))

        return {"status": "ok", "action": "scroll_to_top"}
    except Exception as e:
        return {"status": "error", "action": "scroll_to_top", "error": str(e)}


async def _scroll_short(page: Page, direction: str = "down", **_) -> dict:
    """Cuộn trang một đoạn NGẮN (khoảng 400px) để quan sát từ từ."""
    try:
        from services.scroll_antibot import smooth_wheel_scroll

        dist = 400 if direction == "down" else -400
        await smooth_wheel_scroll(page, distance=dist, min_steps=5, max_steps=12)
        await page.wait_for_timeout(random.randint(800, 1500))
        return {"status": "ok", "action": "scroll_short", "direction": direction}
    except Exception as e:
        return {"status": "error", "action": "scroll_short", "error": str(e)}


async def _navigate(page: Page, url: str, **_) -> dict:
    """Chuyển hướng tới URL khác."""
    try:
        await page.goto(url)
        await page.wait_for_load_state("networkidle", timeout=15000)
        return {"status": "ok", "action": "navigate", "url": url}
    except Exception as e:
        return {"status": "error", "action": "navigate", "url": url, "error": str(e)}


async def _wait(page: Page, ms: int = 2000, **_) -> dict:
    """Dừng một khoảng thời gian (ms). Hữu ích khi chờ animation/lazy-load."""
    await page.wait_for_timeout(ms)
    return {"status": "ok", "action": "wait", "ms": ms}


async def _extract_data(
    page: Page, label: str = None, content: str = None, data: list[dict] = None, **_
) -> dict:
    """
    Agent gọi action này để ghi nhận dữ liệu đã đọc được trên trang.
    Hỗ trợ cả việc gửi 1 phần tử lẻ (label, content) hoặc 1 danh sách nhiều phần tử (data).
    """
    return {
        "status": "ok",
        "action": "extract_data",
        "label": label,
        "content": content,
        "data": data or [],
    }


async def _click_info_page_user(page: Page, **_) -> dict:
    """
    Trỏ vào thẻ div chỉ định, lấy tất cả thẻ span và click vào từng thẻ.
    """
    import time

    start_time = time.perf_counter()  # Bắt đầu đếm thời gian

    try:
        selector = "div.x1qjc9v5.x78zum5.xdt5ytf.x3pnbk8 span"
        spans = page.locator(selector)
        count = await spans.count()

        for i in range(count):
            span_loc = spans.nth(i)

            await human_like_click(
                page=page,
                locator=span_loc,
                timeout_ms=500,
                debug=False,
            )

            try:
                await page.wait_for_load_state("networkidle", timeout=1000)
            except Exception:
                pass

            await page.wait_for_timeout(random.randint(500, 700))

        elapsed = time.perf_counter() - start_time
        print(f"Thời gian chạy: {elapsed:.2f} giây")

        return {
            "status": "ok",
            "action": "click_info_page_user",
            "clicked_count": count,
            "elapsed_time": round(elapsed, 2),
        }

    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error(f"[_extract_info] Lỗi: {e}")
        logger.info(f"Thời gian chạy trước khi lỗi: {elapsed:.2f} giây")

        return {
            "status": "error",
            "action": "extract_info",
            "error": str(e),
            "elapsed_time": round(elapsed, 2),
        }


async def _ask_user(page: Page, question: str, **_) -> dict:
    """
    Agent gọi khi gặp captcha, xác minh, hoặc tình huống rủi ro.
    Tạm dừng 6 giây để người dùng có thời gian thao tác trước khi dừng nhiệm vụ.
    """
    logger.warning(f"[ask_user] Yêu cầu can thiệp: {question}")
    for i in range(6, 0, -1):
        logger.info(f"[ask_user] Đang tạm dừng trình duyệt... còn {i} giây")
        await page.wait_for_timeout(1000)
    return {"status": "ask_user", "action": "ask_user", "question": question}


async def _done(page: Page, summary: str, **_) -> dict:
    """Agent báo hiệu kết thúc nhiệm vụ kèm tổng kết."""
    return {"status": "done", "action": "done", "summary": summary}


async def _extract_info_list_posts(
    page: Page, scroll_rounds: int = 10, isUser: bool = True
) -> dict:
    result = {"posts": {}}  # dict để dùng aria-posinset làm key, tránh trùng lặp
    EMPTY_TEXT = "Không có bài viết"
    TARGET_SELECTOR = 'div[aria-posinset][class~="x1a2a7pz"]'
    VIRTUALIZED_LOADED_SELECTOR = 'div[data-virtualized="false"]'
    SEE_MORE_TEXT = "Xem thêm"
    SEE_MORE_SELECTOR = 'div[role="button"]'
    EXTRACTS_MORE_INFO = [
        "Xem thêm thông tin cá nhân",
        "Xem thêm công việc",
        "Xem thêm học vấn",
    ]

    if isUser:
        # extract html info basic
        html_basic_info_el = await page.query_selector(
            "div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x193iq5w.xeuugli.x1iyjqo2.xs83m0k.xz9dl7a.x11lfxj5.xjkvuk6.x1g0dm76"
        )

        if not html_basic_info_el:
            raise Exception("Lỗi: Facebook có thể đã cập nhật giao diện")

        await smooth_wheel_scroll(page, distance=300, min_steps=2, max_steps=4)
        await page.wait_for_timeout(random.randint(1000, 3000))
        logger.info("Đang chờ để click lấy thêm info user")

        # extract html info user trước
        for text in EXTRACTS_MORE_INFO:
            locator = page.get_by_text(text, exact=True)
            if await locator.count() > 0:
                await human_like_click(page=page, locator=locator.first)
                await page.wait_for_timeout(random.randint(200, 300))

        div_element_info = await page.query_selector(
            "div.x1n2onr6.x1ja2u2z.x1jx94hy.xw5cjc7.x1dmpuos.x1vsv7so.xau1kf4.x9f619.xh8yej3.x6ikm8r.x10wlt62.xquyuld.xsag5q8"
        )

        if not div_element_info:
            # bắn log error facebook cập nhật giao diện
            raise Exception("Lỗi: Facebook có thể đã cập nhật giao diện.")

        html_content_info = await div_element_info.inner_html()
        html_basic_info = await html_basic_info_el.inner_html()  # ← fix: extract string, không lưu ElementHandle
        result["info_personal"] = html_content_info
        result["info_basic"] = html_basic_info
        await _scroll_to_top(page)

    # ---- BƯỚC 1: check trang có xác nhận "Không có bài viết" không ----
    # dùng get_by_text để match chính xác text (tránh match nhầm text chứa chuỗi con)
    empty_locator = page.get_by_text(EMPTY_TEXT, exact=True)
    if await empty_locator.count() > 0:
        logger.info(
            f"Tìm thấy span '{EMPTY_TEXT}' -> trang không có bài viết (hợp lệ)."
        )
        return result

    loaded_any = False
    for round_idx in range(scroll_rounds):
        elements = await page.locator(TARGET_SELECTOR).all()

        for el in elements:
            posinset = await el.get_attribute("aria-posinset")
            if posinset is None or posinset in result["posts"]:
                continue  # đã thu thập rồi, hoặc thiếu attribute -> bỏ qua

            loaded_child = el.locator(VIRTUALIZED_LOADED_SELECTOR)
            if await loaded_child.count() > 0:
                see_more = el.locator(SEE_MORE_SELECTOR).get_by_text(
                    SEE_MORE_TEXT, exact=True
                )
                see_more_count = await see_more.count()
                if see_more_count > 0:
                    target = see_more.first

                    # Check: hit-test tại toạ độ click, chỉ cần đảm bảo KHÔNG trúng
                    # link Reels ("Thước phim") hoặc link nhóm ("/groups/")
                    box = await target.bounding_box(timeout=1000)
                    is_unsafe_widget = False
                    if box and box["width"] > 0 and box["height"] > 0:
                        cx = box["x"] + box["width"] / 2
                        cy = box["y"] + box["height"] / 2
                        is_unsafe_widget = await page.evaluate(
                            """([x, y]) => {
                                const el = document.elementFromPoint(x, y);
                                if (!el) return false;
                                const bad = el.closest(
                                    'a[href^="/reel/"], a[aria-label="Thước phim"], ' +
                                    'a[href*="/groups/"], a[href^="group/"]'
                                );
                                return !!bad;
                            }""",
                            [cx, cy],
                        )

                    if not is_unsafe_widget:
                        try:
                            await human_like_click(page, target)
                            await page.wait_for_timeout(random.randint(200, 300))
                            logger.info(
                                f"Đã click 'Xem thêm' cho bài viết aria-posinset={posinset}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"Click 'Xem thêm' thất bại cho aria-posinset={posinset}: {e}"
                            )
                    else:
                        logger.info(
                            f"Bỏ qua click 'Xem thêm' cho aria-posinset={posinset} "
                            f"do không xác thực được toạ độ an toàn."
                        )

                # Lấy outerHTML SAU KHI đã click mở rộng (nếu có), để có full content
                html = await el.evaluate("node => node.outerHTML")
                result["posts"][posinset] = html
                loaded_any = True
                logger.info(
                    f"[scroll #{round_idx+1}] Đã lấy bài viết aria-posinset={posinset}"
                )
        await smooth_wheel_scroll(page, distance=1000, min_steps=1, max_steps=2)
        await page.wait_for_timeout(random.randint(200, 300))

    # BƯỚC 4: kết luận
    if not loaded_any and not result.get("empty"):
        # báo lỗi thay đổi cấu trúc html
        return {
            "error": "Structure changed",
            "message": "Không tìm thấy bài viết.",
            "posts": [],
        }

    await _scroll_to_top(page)
    return result


async def _extract_list_friends(
    page: Page,
    scroll_rounds: int = 10,
    **_,
) -> dict:
    """
    Trích xuất trực tiếp danh sách bạn bè/thành viên từ DOM bằng cách cuộn trang (không hover).
    """

    FIND_CARDS_JS = """
    () => {
        const results = [];
        const seen = new Set();

        const avatarAnchors = document.querySelectorAll('a[aria-hidden="true"] img');

        for (const img of avatarAnchors) {
            const avatarAnchor = img.closest('a[aria-hidden="true"]');
            if (!avatarAnchor) continue;

            const href = avatarAnchor.href || '';
            const excludedPaths = ['/place', '/page', '/groups', '/post', '/videos'];

            if (
                !href.includes('facebook.com/') ||
                excludedPaths.some(path => href.includes(path))
            ) {
                continue;
            }
            if (href.includes('/friends') || href.endsWith('facebook.com/')) continue;
            if (seen.has(href)) continue;

            const card = avatarAnchor.closest('div.x6s0dn4');
            if (!card) continue;

            const nameEl = card.querySelector('a[role="link"]:not([aria-hidden]) span[dir="auto"]');
            const name = nameEl ? nameEl.textContent.trim() : null;
            const imageUrl = img.src || null;

            const rect = avatarAnchor.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;

            seen.add(href);
            results.push({
                href,
                name,
                image_url: imageUrl,
            });
        }

        return results;
    }
    """
    from services.scroll_antibot import smooth_wheel_scroll
    import time
    import random

    total_rounds = 0
    seen_hrefs: set[str] = set()
    # List nội bộ — chỉ chứa entity do HÀM NÀY tìm được, không dùng chung với bên ngoài
    _found_entities: list[dict] = []
    start_time = time.perf_counter()

    for round_i in range(scroll_rounds):
        total_rounds += 1

        try:
            cards: list[dict] = await page.evaluate(FIND_CARDS_JS)
        except Exception as e:
            logger.warning(f"[extract_list_friends] Lỗi FIND_CARDS_JS: {e}")
            cards = []

        new_added = 0
        for card in cards:
            if card.get("href") not in seen_hrefs:
                seen_hrefs.add(card.get("href"))
                _found_entities.append(card)
                new_added += 1

        logger.info(
            f"[extract_list_friends] Round {round_i+1}/{scroll_rounds}: Thêm mới {new_added} bạn bè. Tổng đã tìm: {len(_found_entities)}"
        )

        # ── Scroll xuống batch tiếp theo ─────────────────────────────────
        scroll_y_before = await page.evaluate("() => window.scrollY")
        await smooth_wheel_scroll(page, distance=800, min_steps=5, max_steps=10)
        # Chờ lazy-load sau scroll
        await page.wait_for_timeout(random.randint(800, 1200))
        scroll_y_after = await page.evaluate("() => window.scrollY")

        if scroll_y_after <= scroll_y_before:
            logger.info(
                f"[extract_list_friends] Đã chạm đáy sau round {round_i+1}/{scroll_rounds}. Dừng sớm."
            )
            break

    # Cuộn ngược về đầu trang sau khi hoàn thành
    await _scroll_to_top(page)

    return {
        "status": "ok",
        "action": "extract_list_friends",
        "total_user_extract": len(_found_entities),
        "discovery_entity": _found_entities,
        "rounds": total_rounds,
        "time_crawl": time.perf_counter() - start_time,
    }


async def _extract_list_members(
    page: Page,
    scroll_rounds: int = 10,
    **_,
) -> dict:
    """
    Trích xuất trực tiếp danh sách thành viên nhóm từ DOM bằng cách cuộn trang (không hover).
    """

    FIND_CARDS_JS = """
    () => {
        const results = [];
        const seen = new Set();

        const avatarAnchors = document.querySelectorAll('a[aria-hidden="true"]');

        for (const avatarAnchor of avatarAnchors) {
            const svgImage = avatarAnchor.querySelector('svg image');
            if (!svgImage) continue;

            const href = avatarAnchor.href || '';
            if (!href.includes('facebook.com/')) continue;
            // Link thành viên nhóm có dạng /groups/<group_id>/user/<uid>/
            if (!href.includes('/user/')) continue;
            if (seen.has(href)) continue;

            const card = avatarAnchor.closest('div.x6s0dn4');
            if (!card) continue;

            // Tên nằm trong thẻ <a role="link"> không có aria-hidden (không phải badge, badge là <div>)
            const nameEl = card.querySelector('a[role="link"]:not([aria-hidden="true"])');
            const name = nameEl ? nameEl.textContent.trim() : null;

            const imageUrl =
                svgImage.getAttribute('xlink:href') ||
                svgImage.getAttribute('href') ||
                null;

            const rect = avatarAnchor.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;

            seen.add(href);
            results.push({
                href,
                name,
                image_url: imageUrl,
            });
        }

        return results;
    }
    """
    from services.scroll_antibot import smooth_wheel_scroll
    import time
    import random

    total_rounds = 0
    seen_hrefs: set[str] = set()
    # List nội bộ — chỉ chứa entity do HÀM NÀY tìm được, không dùng chung với bên ngoài
    _found_entities: list[dict] = []
    start_time = time.perf_counter()

    for round_i in range(scroll_rounds):
        total_rounds += 1

        try:
            cards: list[dict] = await page.evaluate(FIND_CARDS_JS)
        except Exception as e:
            logger.warning(f"[extract_list_members] Lỗi FIND_CARDS_JS: {e}")
            cards = []

        new_added = 0
        for card in cards:
            if card.get("href") not in seen_hrefs:
                seen_hrefs.add(card.get("href"))
                _found_entities.append(card)
                new_added += 1

        logger.info(
            f"[extract_list_members] Round {round_i+1}/{scroll_rounds}: Thêm mới {new_added} thành viên. Tổng đã tìm: {len(_found_entities)}"
        )

        # ── Scroll xuống batch tiếp theo ─────────────────────────────────
        scroll_y_before = await page.evaluate("() => window.scrollY")
        await smooth_wheel_scroll(page, distance=800, min_steps=5, max_steps=10)
        # Chờ lazy-load sau scroll
        await page.wait_for_timeout(random.randint(800, 1200))
        scroll_y_after = await page.evaluate("() => window.scrollY")

        if scroll_y_after <= scroll_y_before:
            logger.info(
                f"[extract_list_members] Đã chạm đáy sau round {round_i+1}/{scroll_rounds}. Dừng sớm."
            )
            break

    # Cuộn ngược về đầu trang sau khi hoàn thành
    await _scroll_to_top(page)

    return {
        "status": "ok",
        "action": "extract_list_members",
        "total_user_extract": len(_found_entities),
        "discovery_entity": _found_entities,
        "rounds": total_rounds,
        "time_crawl": time.perf_counter() - start_time,
    }


async def click_user_refer_group(page: Page, url: str):
    """
    Click vào menu 'Xem trang cá nhân'.
    """

    locator = page.locator("span").filter(has_text="Xem trang cá nhân").first

    try:
        await locator.wait_for(state="visible", timeout=5000)
    except TimeoutError:
        raise RuntimeError("Không tìm thấy menu 'Xem trang cá nhân'")

    await human_like_click(
        page=page,
        locator=locator,
        timeout_ms=5000,
    )

    await page.wait_for_load_state("networkidle")


async def extract_user_reaction_posts(
    page: Page, url: str, count_scroll: int = 10, count_click: int = 5
):
    """
    Tìm và click vào các thẻ span reaction để thu thập user.
    Tối ưu: dùng JS lấy vị trí Y tuyệt đối để dedup, chỉ click element chưa xử lý.
    """

    JS_FIND_REACTIONS = """() => {
        const spans = document.querySelectorAll('span[aria-label="Xem ai đã bày tỏ cảm xúc về tin này"]');
        const results = [];
        for (const span of spans) {
            const rect = span.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) continue;
            const inViewport = rect.top < window.innerHeight && rect.bottom > 0;
            results.push({
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                absY: Math.round(window.scrollY + rect.y + rect.height / 2),
                in_viewport: inViewport,
            });
        }
        return results;
    }"""

    JS_EXTRACT_DIALOG = """() => {
        const dialogs = document.querySelectorAll('div[role="dialog"]');
        if (dialogs.length === 0) return [];
        const dialog = dialogs[dialogs.length - 1];
        const links = dialog.querySelectorAll('a[role="link"]');
        const results = [];
        for (const a of links) {
            const text = a.innerText ? a.innerText.trim() : "";
            let href = a.getAttribute("href") || "";
            if (text && href) {
                if (href.includes("?")) href = href.split("?")[0];
                
                let imageUrl = null;
                let curr = a;
                for (let i = 0; i < 8; i++) {
                    if (!curr.parentElement || curr.parentElement === dialog) break;
                    curr = curr.parentElement;
                    if (curr.querySelectorAll('a[role="link"]').length > 4) break;
                    
                    const imgs = curr.querySelectorAll('image, img');
                    for (const img of imgs) {
                        const wVal = parseInt(img.getAttribute('width') || img.clientWidth || 0);
                        const hVal = parseInt(img.getAttribute('height') || img.clientHeight || 0);
                        if ((wVal > 0 && wVal <= 24) || (hVal > 0 && hVal <= 24)) continue;
                        
                        const src = img.getAttribute('xlink:href') || img.getAttribute('href') || (img.href ? (img.href.baseVal || img.href.val || img.href) : "") || img.src || "";
                        if (src && !src.includes('data:image')) {
                            imageUrl = src;
                            break;
                        }
                    }
                    if (imageUrl) break;
                }
                
                results.push({ name: text, entity_url: href, image_url: imageUrl });
            }
        }
        return results;
    }"""

    users_discovery = []
    seen_abs_y: set[int] = set()  # dedup element đã click theo vị trí Y tuyệt đối
    seen_urls: set[str] = set()  # dedup entity_url user
    await smooth_wheel_scroll(page, distance=500, min_steps=1, max_steps=3)

    for scroll_round in range(count_scroll):
        await smooth_wheel_scroll(page, distance=500, min_steps=1, max_steps=3)
        await page.wait_for_timeout(random.randint(500, 700))

        all_elements: list[dict] = await page.evaluate(JS_FIND_REACTIONS)

        new_elements = [
            el
            for el in all_elements
            if el["in_viewport"] and int(el["absY"]) not in seen_abs_y
        ]

        logger.info(
            f"[extract_user_reaction_posts] Round {scroll_round + 1}: "
            f"{len(all_elements)} tổng, {len(new_elements)} mới chưa xử lý"
        )

        for idx, el in enumerate(new_elements):
            abs_y_key = int(el["absY"])
            seen_abs_y.add(abs_y_key)

            try:
                # Lấy lại locator theo index trong danh sách elements hiện tại
                # (đã lọc in_viewport, nhưng cần map đúng index trong DOM)
                selector = 'span[aria-label="Xem ai đã bày tỏ cảm xúc về tin này"]'
                all_locs = page.locator(selector)
                # Tìm locator khớp với absY của element này
                count_locs = await all_locs.count()
                target_loc = None
                for j in range(count_locs):
                    loc = all_locs.nth(j)
                    try:
                        box = await loc.bounding_box()
                        if box is None:
                            continue
                        loc_abs_y = int(
                            await page.evaluate("window.scrollY")
                            + box["y"]
                            + box["height"] / 2
                        )
                        if abs(loc_abs_y - abs_y_key) <= 5:  # tolerance 5px
                            target_loc = loc
                            break
                    except Exception:
                        continue

                if target_loc is None:
                    logger.warning(
                        f"[extract_user_reaction_posts] Không tìm thấy locator cho absY={abs_y_key}, bỏ qua"
                    )
                    continue

                await human_like_click(page, target_loc)
                await page.wait_for_timeout(random.randint(1500, 2500))

                tab_all_loc = page.locator(
                    'div[role="tab"][aria-label*="Tất cả"]'
                ).first
                if await tab_all_loc.is_visible(timeout=2000):
                    await human_like_click(page, tab_all_loc)
                    await page.wait_for_timeout(random.randint(800, 1500))

                    # Scroll bên trong popup: hover chuột ngay phía dưới tab "Tất cả"
                    # (vùng list user) rồi wheel scroll — wheel event đến đúng container.
                    try:
                        tab_box = await tab_all_loc.bounding_box()
                        if tab_box:
                            hover_x = tab_box["x"] + tab_box["width"]
                            # Chéo xuống ~150px bên dưới tab → vào vùng danh sách
                            hover_y = tab_box["y"] + tab_box["height"] + 150
                            await page.mouse.move(hover_x, hover_y)
                            await page.wait_for_timeout(random.randint(300, 500))

                            for _ in range(6):
                                await smooth_wheel_scroll(
                                    page, distance=500, min_steps=3, max_steps=6
                                )
                                await page.wait_for_timeout(random.randint(300, 600))

                    except Exception as e:
                        logger.warning(
                            f"[extract_user_reaction_posts] Lỗi scroll dialog: {e}"
                        )

                    try:
                        extracted_users = await page.evaluate(JS_EXTRACT_DIALOG)
                        added = 0
                        for user_info in extracted_users:
                            url_key = user_info.get("entity_url", "")
                            if url_key and url_key not in seen_urls:
                                seen_urls.add(url_key)
                                users_discovery.append(user_info)
                                added += 1
                        logger.info(
                            f"[extract_user_reaction_posts] +{added} user mới "
                            f"(tổng unique: {len(users_discovery)})"
                        )
                    except Exception as e:
                        logger.warning(
                            f"[extract_user_reaction_posts] Lỗi JS extract: {e}"
                        )

            except Exception as e:
                logger.warning(
                    f"[extract_user_reaction_posts] Lỗi click reaction (absY={abs_y_key}): {e}"
                )
            finally:
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(random.randint(400, 800))
                except Exception:
                    pass

    logger.info(
        f"[extract_user_reaction_posts] Hoàn tất: {len(users_discovery)} user unique từ reactions"
    )
    return users_discovery
