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

        TARGET_Y = random.randint(490, 500)  # Pixel cách đỉnh trang — luôn cố định

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


async def _hover_users(
    page: Page,
    scroll_rounds: int = 10,
    hover_delay_ms: int = 1000,  # Chờ đủ để FB kịp gửi bulk-route-definitions response
    discovery_entity: list[dict] | None = None,
    on_bulk_response=None,  # async callable(raw_text: str) -> None
    **_,
) -> dict:
    """
    Hover lần lượt qua từng thẻ người dùng trong trang Bạn bè / Thành viên.

    ── Tối ưu v2 (global listener) ────────────────────────────────────────────
    Thay vì dùng `page.expect_response()` cho mỗi card (block 1200ms/card),
    ta dùng 1 listener `page.on("response")` toàn cục chạy suốt toàn bộ hàm.
    Hover card nhanh, response được xử lý song song — giảm ~70% thời gian chờ.
    ────────────────────────────────────────────────────────────────────────────
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
            const inViewport = rect.top < window.innerHeight && rect.bottom > 0;

            seen.add(href);
            results.push({
                href,
                name,
                image_url: imageUrl,
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                in_viewport: inViewport,
            });
        }

        return results;
    }
    """

    from services.mouse_action import _move_mouse_curve
    from services.parse_bulk_route import bulk_route_parser_worker
    from services.scroll_antibot import smooth_wheel_scroll

    total_hovered = 0
    total_rounds = 0
    seen_hrefs: set[str] = set()

    # ── Global response listener (push model, không block hover loop) ────────
    # Mỗi khi FB gửi bulk-route-definitions, callback này được gọi ngay lập tức
    # mà không làm dừng vòng hover bên dưới.
    _pending_hrefs: list[str] = []  # href của card vừa hover gần nhất
    import time

    start_time = time.perf_counter()

    async def _on_bulk_response(response):
        """Xử lý response bulk-route-definitions khi nhận được."""
        if "bulk-route-definitions/" not in response.url:
            return
        try:
            raw_text = await response.text()
            is_entity = bulk_route_parser_worker(raw_text)
            if not is_entity or discovery_entity is None:
                return
            # Lấy href mới nhất của card đang hover (best-effort mapping)
            href = _pending_hrefs[-1] if _pending_hrefs else ""
            if href and not href.endswith("facebook.com/"):
                # Tránh thêm trùng
                known = {e["entity_url"] for e in discovery_entity}
                if href not in known:
                    # Tìm metadata card tương ứng
                    name = None
                    image_url = None
                    for _card_meta in _card_meta_map.values():
                        if _card_meta["href"] == href:
                            name = _card_meta.get("name")
                            image_url = _card_meta.get("image_url")
                            break
                    discovery_entity.append(
                        {"entity_url": href, "name": name, "image_url": image_url}
                    )
                    logger.info(f"[hover_users] ✅ Entity: {href}")
        except Exception as e:
            logger.debug(f"[hover_users] Lỗi xử lý bulk response: {e}")

    # Map href → metadata card để callback tra cứu
    _card_meta_map: dict[str, dict] = {}

    page.on("response", _on_bulk_response)

    try:
        cur_x, cur_y = 100.0, 300.0

        for round_i in range(scroll_rounds):
            total_rounds += 1

            try:
                cards: list[dict] = await page.evaluate(FIND_CARDS_JS)
            except Exception as e:
                logger.warning(f"[hover_users] Lỗi FIND_CARDS_JS: {e}")
                cards = []

            in_viewport_cards = [
                c
                for c in cards
                if c.get("in_viewport") and c.get("href") not in seen_hrefs
            ]
            logger.info(
                f"[hover_users] Round {round_i+1}: {len(in_viewport_cards)} card mới "
                f"(bỏ qua {len(cards) - len(in_viewport_cards)} trùng/ngoài viewport)"
            )

            for card in in_viewport_cards:
                href = card.get("href", "")
                seen_hrefs.add(href)
                _card_meta_map[href] = card  # lưu metadata để callback dùng

                try:
                    target_x = card["x"] + random.uniform(-5, 5)
                    target_y = card["y"] + random.uniform(-3, 3)

                    # ── Di chuyển chuột: dùng Bezier curve ngắn ─────────────
                    await _move_mouse_curve(
                        page=page,
                        start_x=cur_x,
                        start_y=cur_y,
                        end_x=target_x,
                        end_y=target_y,
                        total_time_ms=random.uniform(
                            300, 500
                        ),  # nhanh hơn v1 (180-350)
                        steps=random.randint(4, 8),  # ít bước hơn v1 (5-10)
                        jitter_scale=0.4,
                    )
                    cur_x, cur_y = target_x, target_y

                    # Ghi nhận href để callback map response đúng card
                    _pending_hrefs.append(href)
                    if len(_pending_hrefs) > 5:
                        _pending_hrefs.pop(0)  # giữ window 5 href gần nhất

                    # Chờ đủ để FB kịp gửi bulk-route-definitions response sau hover.
                    # Nếu quá nhanh → response chưa về, bỏ lỡ entity.
                    await page.wait_for_timeout(hover_delay_ms)

                    total_hovered += 1
                except Exception:
                    pass

            # ── Scroll xuống batch tiếp theo ─────────────────────────────────
            scroll_y_before = await page.evaluate("() => window.scrollY")
            await smooth_wheel_scroll(page, distance=500, min_steps=6, max_steps=14)
            # Chờ lazy-load sau scroll (giảm từ không chờ → 800ms cố định)
            await page.wait_for_timeout(random.randint(700, 1000))
            scroll_y_after = await page.evaluate("() => window.scrollY")

            if scroll_y_after <= scroll_y_before:
                logger.info(
                    f"[hover_users] Đã chạm đáy sau round {round_i+1}/{scroll_rounds}. Dừng sớm."
                )
                break

    finally:
        # Luôn gỡ listener dù có lỗi hay không
        page.remove_listener("response", _on_bulk_response)

    await _scroll_to_top(page)

    return {
        "status": "ok",
        "action": "hover_users",
        "total_hovered": total_hovered,
        "total_user_extract": len(discovery_entity),
        "discovery_entity": discovery_entity,
        "rounds": total_rounds,
        "time_crawl": time.perf_counter() - start_time,
    }


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
                results.push({ name: text, entity_url: href });
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

                            await smart_scroll_for_api(
                                page,
                                max_scroll_loops=6,
                                chunk_distance=500,
                                min_wait_ms=500,
                                max_wait_ms=1000,
                            )

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
