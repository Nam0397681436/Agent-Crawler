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
from services.scroll_antibot import smart_scroll_for_api

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Các hàm thực thi
# ---------------------------------------------------------------------------


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


async def _scroll(page: Page, direction: str = "down", times: int = 3, **_) -> dict:
    """Cuộn trang (anti-bot aware scroll)."""
    try:
        await smart_scroll_for_api(page, max_scroll_loops=times, debug=False)
        await _scroll_to_top(page)
        return {
            "status": "ok",
            "action": "scroll",
            "direction": direction,
            "times": times,
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
    hover_delay_ms: int = 800,  # Giảm từ 1200ms → 800ms; global listener không cần wait dài
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
                            120, 250
                        ),  # nhanh hơn v1 (180-350)
                        steps=random.randint(4, 8),  # ít bước hơn v1 (5-10)
                        jitter_scale=0.4,
                    )
                    cur_x, cur_y = target_x, target_y

                    # Ghi nhận href để callback map response đúng card
                    _pending_hrefs.append(href)
                    if len(_pending_hrefs) > 5:
                        _pending_hrefs.pop(0)  # giữ window 5 href gần nhất

                    # ── Chờ ngắn — không block cả 1200ms nếu không có response ─
                    # Thay vì expect_response (block hết timeout), chỉ wait đủ để
                    # FB kịp gửi hover event, response được bắt bởi global listener.
                    wait_ms = hover_delay_ms + random.randint(-100, 100)
                    await page.wait_for_timeout(wait_ms)

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
        "rounds": total_rounds,
    }


# ---------------------------------------------------------------------------
# Registry: ánh xạ tên action → (schema, handler)
# ---------------------------------------------------------------------------
# Thêm action mới: bổ sung một dict vào đây là xong.

ACTION_REGISTRY: dict[str, dict[str, Any]] = {
    "click": {
        "handler": _click,
        "schema": {
            "name": "click",
            "description": "Click vào phần tử (button, link, tab).",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "string",
                        "description": "data-agent-id của phần tử (vd: 'a42').",
                    }
                },
                "required": ["element_id"],
            },
        },
    },
    # "scroll_to_top": {
    #     "handler": _scroll_to_top,
    #     "schema": {
    #         "name": "scroll_to_top",
    #         "description": (
    #             "Cuộn ngay về đầu trang (top). "
    #             "PHẢI gọi action này trước khi click sang tab tiếp theo, "
    #             "để thanh điều hướng (tab bar) hiện trở lại trong viewport."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {},
    #             "required": [],
    #         },
    #     },
    # },
    "scroll": {
        "handler": _scroll,
        "schema": {
            "name": "scroll",
            "description": "Cuộn trang kích hoạt lazy-load.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Hướng cuộn (mặc định: down).",
                    },
                    "times": {
                        "type": "integer",
                        "description": "Số lần cuộn (mặc định: 3).",
                    },
                },
                "required": [],
            },
        },
    },
    # "scroll_short": {
    #     "handler": _scroll_short,
    #     "schema": {
    #         "name": "scroll_short",
    #         "description": "Cuộn trang một đoạn NGẮN (khoảng 400px) để quan sát từ từ. Dùng tool này khi bạn đang tìm kiếm các nút bấm hoặc menu phụ để screenshot cập nhật mà không bị lướt qua mất chúng.",
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "direction": {
    #                     "type": "string",
    #                     "enum": ["down", "up"],
    #                     "description": "Hướng cuộn. Mặc định: down.",
    #                 }
    #             },
    #             "required": [],
    #         },
    #     },
    # },
    # "hover_users": {
    #     "handler": _hover_users,
    #     "schema": {
    #         "name": "hover_users",
    #         "description": (
    #             "Hover chuột lần lượt qua từng thẻ người dùng trong trang Bạn bè / Thành viên / Mọi người. "
    #             "Mỗi lần hover kích hoạt API thu thập thông tin user. "
    #             "PHẢI gọi ngay sau khi vừa click vào tab Bạn bè / Thành viên / Mọi người."
    #         ),
    #         "parameters": {
    #             "type": "object",
    #             "properties": {
    #                 "scroll_rounds": {
    #                     "type": "integer",
    #                     "description": "Số lượt cuộn và hover (mỗi lượt xử lý 1 batch user card). Mặc định: 5.",
    #                 },
    #                 "hover_delay_ms": {
    #                     "type": "integer",
    #                     "description": "Thời gian hover trên mỗi user (ms). Mặc định: 1200.",
    #                 },
    #             },
    #             "required": [],
    #         },
    #     },
    # },
    "navigate": {
        "handler": _navigate,
        "schema": {
            "name": "navigate",
            "description": "Chuyển tới URL mới.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL đích."},
                },
                "required": ["url"],
            },
        },
    },
    "wait": {
        "handler": _wait,
        "schema": {
            "name": "wait",
            "description": "Chờ (ms) để trang render / API trả về.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ms": {
                        "type": "integer",
                        "description": "Millisecond cần chờ.",
                    },
                },
                "required": ["ms"],
            },
        },
    },
    "extract_data": {
        "handler": _extract_data,
        "schema": {
            "name": "extract_data",
            "description": "Ghi dữ liệu tìm thấy. Một mục: dùng label+content. Nhiều mục: dùng data array.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Tên thông tin (1 mục lẻ).",
                    },
                    "content": {
                        "type": "string",
                        "description": "Nội dung (1 mục lẻ).",
                    },
                    "data": {
                        "type": "array",
                        "description": "Nhiều mục: [{label, content}, ...]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["label", "content"],
                        },
                    },
                },
                "required": [],
            },
        },
    },
    "ask_user": {
        "handler": _ask_user,
        "schema": {
            "name": "ask_user",
            "description": "Dừng và yêu cầu can thiệp (captcha, xác minh 2 bước, rủi ro).",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Mô tả tình huống cần người dùng xử lý.",
                    },
                },
                "required": ["question"],
            },
        },
    },
    "done": {
        "handler": _done,
        "schema": {
            "name": "done",
            "description": "Kết thúc sau khi duyệt xong các tab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Tóm tắt ngắn: tab nào đã thực hiện.",
                    },
                },
                "required": ["summary"],
            },
        },
    },
}


def get_tool_schemas() -> list[dict]:
    """Trả về list schema theo chuẩn OpenAI function calling."""
    return [
        {"type": "function", "function": entry["schema"]}
        for entry in ACTION_REGISTRY.values()
    ]


async def execute(action_name: str, page: Page, params: dict) -> dict:
    """Thực thi một action theo tên."""
    entry = ACTION_REGISTRY.get(action_name)
    if not entry:
        return {"status": "error", "error": f"Action không tồn tại: {action_name}"}
    try:
        return await entry["handler"](page=page, **params)
    except Exception as e:
        logger.error(f"[actions] Lỗi thực thi '{action_name}': {e}")
        return {"status": "error", "action": action_name, "error": str(e)}
