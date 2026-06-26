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

        scroll_y = await page.evaluate("window.scrollY || window.pageYOffset || 0")
        target_y = 300
        if scroll_y > target_y:
            distance_to_scroll = -(scroll_y - target_y)
            await smooth_wheel_scroll(
                page=page, distance=distance_to_scroll, min_steps=5, max_steps=10
            )
            await page.wait_for_timeout(random.randint(600, 1000))
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


async def _extract_data(page: Page, label: str, content: str, **_) -> dict:
    """
    Agent gọi action này để ghi nhận dữ liệu đã đọc được trên trang.
    Không tương tác với Playwright — chỉ là tín hiệu để vòng lặp lưu lại.
    """
    return {
        "status": "ok",
        "action": "extract_data",
        "label": label,
        "content": content,
    }


async def _ask_user(page: Page, question: str, **_) -> dict:
    """
    Agent gọi khi gặp captcha, xác minh, hoặc tình huống rủi ro.
    Tạm dừng 5 giây để người dùng có thời gian thao tác trước khi dừng nhiệm vụ.
    """
    logger.warning(f"[ask_user] Yêu cầu can thiệp: {question}")
    for i in range(5, 0, -1):
        logger.info(f"[ask_user] Đang tạm dừng trình duyệt... còn {i} giây")
        await page.wait_for_timeout(1000)
    return {"status": "ask_user", "action": "ask_user", "question": question}


async def _done(page: Page, summary: str, **_) -> dict:
    """Agent báo hiệu kết thúc nhiệm vụ kèm tổng kết."""
    return {"status": "done", "action": "done", "summary": summary}


async def _hover_users(
    page: Page,
    scroll_rounds: int = 5,
    hover_delay_ms: int = 1200,       # Giảm từ 2300 → 1200ms (đủ để FB kích hoạt API)
    discovery_entity: list[dict] | None = None,
    on_bulk_response=None,  # async callable(raw_text: str) -> None
    **_,
) -> dict:
    """
    Hover lần lượt qua từng thẻ người dùng trong trang Bạn bè / Thành viên.
    Mỗi lần hover sẽ kích hoạt bulk-route-definitions API của Facebook.
    Nếu truyền `on_bulk_response`, hàm đó sẽ được gọi ngay khi bắt được response.
    """
    # Selector dựa trên cấu trúc thực tế của thẻ bạn bè / thành viên Facebook:
    # <a role="link" aria-hidden="true" href="https://web.facebook.com/{username}">
    #     <img height="80" width="80" ...>   ← avatar cố định 80×80
    # </a>
    # Dùng JS evaluate để tìm chính xác vì :has() không phải lúc nào cũng hỗ trợ tốt

    FIND_CARDS_JS = """
    () => {
        const results = [];
        const seen = new Set();

        const avatarAnchors = document.querySelectorAll('a[aria-hidden="true"] img');

        for (const img of avatarAnchors) {
            const avatarAnchor = img.closest('a[aria-hidden="true"]');
            if (!avatarAnchor) continue;

            const href = avatarAnchor.href || '';
            if (!href.includes('facebook.com/')) continue;
            if (href.includes('/friends') || href.endsWith('facebook.com/')) continue;
            if (seen.has(href)) continue;

            const card = avatarAnchor.closest('div.x6s0dn4');
            if (!card) continue;

            const nameEl = card.querySelector('a[role="link"]:not([aria-hidden]) span[dir="auto"]');
            const name = nameEl ? nameEl.textContent.trim() : null;

            const imageUrl = img.src || null;

            // Tọa độ để hover
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

    total_hovered = 0
    total_rounds = 0

    from services.mouse_action import _move_mouse_curve
    from services.parse_bulk_route import bulk_route_parser_worker

    # Vị trí ban đầu của chuột (góc trên trái an toàn)
    cur_x, cur_y = 100.0, 300.0

    # Theo dõi href đã hover để bỏ qua giữa các round
    seen_hrefs: set[str] = set()

    for round_i in range(scroll_rounds):
        total_rounds += 1

        # Dùng JS tìm tất cả user card trong viewport (trả về tọa độ trực tiếp)
        try:
            cards: list[dict] = await page.evaluate(FIND_CARDS_JS)
        except Exception as e:
            logger.warning(f"[hover_users] Lỗi khi chạy FIND_CARDS_JS: {e}")
            cards = []

        # Chỉ lấy card trong viewport VÀ chưa hover lần nào
        in_viewport_cards = [
            c for c in cards
            if c.get("in_viewport") and c.get("href") not in seen_hrefs
        ]
        logger.info(
            f"[hover_users] Round {round_i+1}: {len(in_viewport_cards)} card mới trong viewport "
            f"(đã bỏ qua {len(cards) - len(in_viewport_cards)} card trùng/ngoài viewport)"
        )

        for card in in_viewport_cards:
            href = card.get("href", "")
            seen_hrefs.add(href)
            try:
                target_x = card["x"] + random.uniform(-5, 5)
                target_y = card["y"] + random.uniform(-3, 3)

                # Timeout ngắn hơn — chỉ đủ để FB kích hoạt API sau khi hover
                wait_ms = hover_delay_ms + random.randint(-100, 150)

                # Di chuyển chuột trước (nhanh hơn, ít bước hơn)
                await _move_mouse_curve(
                    page=page,
                    start_x=cur_x,
                    start_y=cur_y,
                    end_x=target_x,
                    end_y=target_y,
                    total_time_ms=random.uniform(180, 350),  # Giảm từ 300-600 → 180-350ms
                    steps=random.randint(5, 10),              # Giảm từ 8-18 → 5-10 bước
                    jitter_scale=0.5,
                )
                cur_x, cur_y = target_x, target_y

                # Lắng nghe response bulk-route-definitions
                try:
                    async with page.expect_response(
                        lambda r: "bulk-route-definitions/" in r.url,
                        timeout=wait_ms,
                    ) as bulk_resp_info:
                        await page.wait_for_timeout(wait_ms)

                    # Bắt được response → xử lý
                    bulk_resp = await bulk_resp_info.value
                    raw_text = await bulk_resp.text()

                    is_entity = bulk_route_parser_worker(raw_text)
                    if is_entity and discovery_entity is not None:
                        logger.info(f"[hover_users] Entity tìm thấy: {href}")
                        if href and not href.endswith("facebook.com/"):
                            discovery_entity.append(
                                {
                                    "entity_url": href,
                                    "name": card.get("name"),
                                    "image_url": card.get("image_url"),
                                }
                            )

                except Exception:
                    # Timeout — không wait thêm, chuyển card tiếp theo ngay
                    pass

                total_hovered += 1
            except Exception:
                pass

        # Cuộn xuống để load batch tiếp theo — kiểm tra đáy trước
        from services.scroll_antibot import smooth_wheel_scroll

        scroll_y_before = await page.evaluate("() => window.scrollY")
        await smooth_wheel_scroll(page, distance=500, min_steps=6, max_steps=14)
        scroll_y_after = await page.evaluate("() => window.scrollY")

        if scroll_y_after <= scroll_y_before:
            logger.info(
                f"[hover_users] Đã chạm đáy trang sau round {round_i+1}/{scroll_rounds}. Dừng sớm."
            )
            break

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
            "description": "Click vào một phần tử trên trang (button, link, tab, …).",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "string",
                        "description": "data-agent-id của phần tử cần click (ví dụ: 'a42').",
                    }
                },
                "required": ["element_id"],
            },
        },
    },
    "scroll_to_top": {
        "handler": _scroll_to_top,
        "schema": {
            "name": "scroll_to_top",
            "description": (
                "Cuộn ngay về đầu trang (top). "
                "PHẢI gọi action này trước khi click sang tab tiếp theo, "
                "để thanh điều hướng (tab bar) hiện trở lại trong viewport."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    "scroll": {
        "handler": _scroll,
        "schema": {
            "name": "scroll",
            "description": "Cuộn trang để kích hoạt lazy-load và API response.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Hướng cuộn. Mặc định: down.",
                    },
                    "times": {
                        "type": "integer",
                        "description": "Số lần cuộn. Mặc định: 3.",
                    },
                },
                "required": [],
            },
        },
    },
    "scroll_short": {
        "handler": _scroll_short,
        "schema": {
            "name": "scroll_short",
            "description": "Cuộn trang một đoạn NGẮN (khoảng 400px) để quan sát từ từ. Dùng tool này khi bạn đang tìm kiếm các nút bấm hoặc menu phụ để screenshot cập nhật mà không bị lướt qua mất chúng.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["down", "up"],
                        "description": "Hướng cuộn. Mặc định: down.",
                    }
                },
                "required": [],
            },
        },
    },
    "hover_users": {
        "handler": _hover_users,
        "schema": {
            "name": "hover_users",
            "description": (
                "Hover chuột lần lượt qua từng thẻ người dùng trong trang Bạn bè / Thành viên / Mọi người. "
                "Mỗi lần hover kích hoạt API thu thập thông tin user. "
                "PHẢI gọi ngay sau khi vừa click vào tab Bạn bè / Thành viên / Mọi người."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scroll_rounds": {
                        "type": "integer",
                        "description": "Số lượt cuộn và hover (mỗi lượt xử lý 1 batch user card). Mặc định: 5.",
                    },
                    "hover_delay_ms": {
                        "type": "integer",
                        "description": "Thời gian hover trên mỗi user (ms). Mặc định: 1200.",
                    },
                },
                "required": [],
            },
        },
    },
    "navigate": {
        "handler": _navigate,
        "schema": {
            "name": "navigate",
            "description": "Chuyển hướng tới một URL mới.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL đích (đầy đủ)."},
                },
                "required": ["url"],
            },
        },
    },
    "wait": {
        "handler": _wait,
        "schema": {
            "name": "wait",
            "description": "Chờ một khoảng thời gian (ms) để trang render hoặc API trả về.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ms": {
                        "type": "integer",
                        "description": "Thời gian chờ tính bằng millisecond.",
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
            "description": "Ghi nhận dữ liệu quan trọng tìm thấy trên trang (như tên, tiểu sử, thông tin liên hệ).",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Tên loại thông tin (ví dụ: 'Tiểu sử', 'Tên đầy đủ').",
                    },
                    "content": {
                        "type": "string",
                        "description": "Nội dung dữ liệu trích xuất được.",
                    },
                },
                "required": ["label", "content"],
            },
        },
    },
    "ask_user": {
        "handler": _ask_user,
        "schema": {
            "name": "ask_user",
            "description": (
                "Dừng lại và hỏi người dùng khi gặp captcha, xác minh 2 bước, "
                "hoặc bất kỳ tình huống rủi ro nào cần can thiệp của người."
            ),
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
            "description": "Kết thúc nhiệm vụ khi đã duyệt xong tất cả các tab có thể truy cập.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Tóm tắt ngắn gọn: đã click tab nào, scroll bao nhiêu lần.",
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
