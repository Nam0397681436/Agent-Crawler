import random
from typing import Dict, Any

from playwright.async_api import Page


async def smart_scroll_for_api(
    page: Page,
    max_scroll_loops: int = 10,
    chunk_distance: int = 1400,
    min_wait_ms: int = 3000,
    max_wait_ms: int = 6000,
    stable_limit: int = 3,
    bottom_threshold_px: int = 500,
    debug: bool = True,
) -> Dict[str, Any]:
    """
    Scroll thông minh để trigger API/lazy-load.

    Bản này KHÔNG đếm số bài post/article nữa.

    Nó chỉ dựa vào:
    - scroll_height
    - scroll_y
    - inner_height
    - việc trang có tăng chiều cao sau scroll hay không
    - việc mouse.wheel có làm trang di chuyển hay không

    Dừng khi:
    - gần chạm đáy trang
    - scrollHeight không tăng sau stable_limit vòng
    - đạt max_scroll_loops
    """

    report = {
        "scroll_loops": 0,
        "wheel_events": 0,
        "start_height": None,
        "end_height": None,
        "stopped_reason": None,
    }

    start_metrics = await _get_scroll_metrics(page)
    report["start_height"] = start_metrics["scroll_height"]

    stable_rounds = 0
    last_height = start_metrics["scroll_height"]
    last_scroll_y = start_metrics["scroll_y"]

    for loop_index in range(1, max_scroll_loops + 1):
        metrics = await _get_scroll_metrics(page)

        scroll_height = metrics["scroll_height"]
        scroll_y = metrics["scroll_y"]
        inner_height = metrics["inner_height"]

        current_position = scroll_y + inner_height
        distance_to_bottom = scroll_height - current_position

        if distance_to_bottom <= bottom_threshold_px:
            report["stopped_reason"] = "bottom_reached"

            if debug:
                print(f"✅ Đã gần chạm đáy trang ở loop={loop_index}. Dừng.")

            break

        distance = min(chunk_distance, max(300, distance_to_bottom))

        if debug:
            print(
                f"⏳ loop={loop_index} "
                f"scrollY={scroll_y} "
                f"height={scroll_height} "
                f"distance={distance}"
            )

        wheel_count = await smooth_wheel_scroll(
            page=page,
            distance=distance,
            min_steps=6,
            max_steps=18,
        )

        report["scroll_loops"] += 1
        report["wheel_events"] += wheel_count

        wait_ms = random.randint(min_wait_ms, max_wait_ms)

        if debug:
            print(f"💤 Wait {wait_ms}ms for API/load")

        await page.wait_for_timeout(wait_ms)

        after = await _get_scroll_metrics(page)

        height_changed = after["scroll_height"] > last_height
        moved = after["scroll_y"] > last_scroll_y

        if not moved:
            if debug:
                print(
                    "⚠️ mouse.wheel không làm trang di chuyển. Fallback window.scrollBy"
                )

            await page.evaluate(
                """distance => {
                    window.scrollBy({
                        top: distance,
                        left: 0,
                        behavior: 'auto'
                    });
                }""",
                distance,
            )

            await page.wait_for_timeout(random.randint(700, 1200))

            after = await _get_scroll_metrics(page)

            height_changed = after["scroll_height"] > last_height
            moved = after["scroll_y"] > last_scroll_y

            if debug:
                if moved:
                    print("✅ Fallback window.scrollBy đã làm trang di chuyển.")
                else:
                    print("⚠️ Fallback window.scrollBy vẫn không làm trang di chuyển.")

        if not height_changed:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if debug:
            print(
                f"📏 after_height={after['scroll_height']} "
                f"after_scrollY={after['scroll_y']} "
                f"height_changed={height_changed} "
                f"moved={moved} "
                f"stable_rounds={stable_rounds}"
            )

        last_height = after["scroll_height"]
        last_scroll_y = after["scroll_y"]

        if stable_rounds >= stable_limit:
            report["stopped_reason"] = "stable_no_height_change"

            if debug:
                print(f"🛑 scrollHeight không tăng sau {stable_rounds} vòng. Dừng.")

            break

    else:
        report["stopped_reason"] = "max_scroll_loops_reached"

        if debug:
            print(f"🛑 Đạt giới hạn max_scroll_loops={max_scroll_loops}. Dừng.")

    end_metrics = await _get_scroll_metrics(page)
    report["end_height"] = end_metrics["scroll_height"]

    return report


async def smooth_wheel_scroll(
    page: Page,
    distance: float,
    min_steps: int = 6,
    max_steps: int = 18,
) -> int:
    """
    Scroll mượt theo một chunk.

    - Chia một đoạn scroll thành nhiều wheel event nhỏ.
    - Có easing để đầu/chặng cuối chậm hơn.
    - Có noise nhẹ để delta không đều tuyệt đối.
    - Có nghỉ ngắn giữa các wheel event.
    - Thỉnh thoảng scroll ngược nhẹ.
    """

    steps = random.randint(min_steps, max_steps)
    previous_y = 0

    for i in range(1, steps + 1):
        t = i / steps

        # Smoothstep easing: đầu chậm, giữa nhanh, cuối chậm.
        ease = (t * t) * (3 - 2 * t)

        current_y = distance * ease
        delta_y = current_y - previous_y

        noise = random.uniform(0.85, 1.15)
        final_delta_y = round(delta_y * noise)

        if final_delta_y != 0:
            await page.mouse.wheel(0, final_delta_y)

        previous_y = current_y

        await page.wait_for_timeout(random.randint(25, 90))

    # Thỉnh thoảng scroll ngược nhẹ để UI/lazy-load ổn hơn.
    if random.random() < 0.20:
        await page.wait_for_timeout(random.randint(100, 250))
        await page.mouse.wheel(0, -random.randint(30, 90))

    return steps


async def _get_scroll_metrics(page: Page) -> Dict[str, Any]:
    """
    Chỉ lấy thông số scroll.

    Không đếm post.
    Không dùng item_selector.
    """

    return await page.evaluate(
        """() => {
            const body = document.body;
            const doc = document.documentElement;

            return {
                scroll_height: Math.max(
                    body ? body.scrollHeight : 0,
                    doc ? doc.scrollHeight : 0,
                    body ? body.offsetHeight : 0,
                    doc ? doc.offsetHeight : 0,
                    body ? body.clientHeight : 0,
                    doc ? doc.clientHeight : 0
                ),
                scroll_y: window.scrollY || window.pageYOffset || 0,
                inner_height: window.innerHeight || 0
            };
        }"""
    )
