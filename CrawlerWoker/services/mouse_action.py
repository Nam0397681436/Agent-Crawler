import math
import random
from typing import Dict, Any, Optional, Tuple

from playwright.async_api import Page, Locator


async def human_like_click(
    page: Page,
    locator: Locator,
    timeout_ms: int = 3000,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Di chuyển chuột tới element rồi click.

    Mô hình dùng:
    - Fitts's Law để ước lượng movement time.
    - Bezier curve để tạo đường đi cong.
    - Smoothstep easing để vận tốc tự nhiên hơn.
    - Gaussian jitter để tránh quỹ đạo quá thẳng/máy móc.
    - Log-normal pause cho hover/click hold.
    - Optional overshoot nhỏ cho target xa.

    Không dùng để bypass captcha/checkpoint.
    """

    await locator.wait_for(state="visible", timeout=timeout_ms)
    await locator.scroll_into_view_if_needed(timeout=timeout_ms)

    box = await locator.bounding_box(timeout=timeout_ms)

    if not box:
        raise RuntimeError("Cannot get element bounding box")

    target_x, target_y = _sample_click_point_in_box(box)
    start_x, start_y = await _get_or_init_mouse_position(page)

    distance = _distance(start_x, start_y, target_x, target_y)
    target_width = max(8.0, min(box["width"], box["height"]))

    movement_time_ms = _estimate_movement_time_ms(
        distance=distance,
        target_width=target_width,
    )

    steps = _estimate_steps(
        distance=distance,
        movement_time_ms=movement_time_ms,
    )

    if debug:
        print(
            "[mouse] "
            f"from=({round(start_x)}, {round(start_y)}) "
            f"to=({round(target_x)}, {round(target_y)}) "
            f"distance={round(distance)} "
            f"target_width={round(target_width)} "
            f"mt={round(movement_time_ms)}ms "
            f"steps={steps}"
        )

    # Với khoảng cách xa, đôi khi overshoot nhẹ rồi chỉnh lại.
    use_overshoot = distance > 350 and random.random() < 0.25

    if use_overshoot:
        over_x, over_y = _make_overshoot_point(
            start_x=start_x,
            start_y=start_y,
            target_x=target_x,
            target_y=target_y,
        )

        await _move_mouse_curve(
            page=page,
            start_x=start_x,
            start_y=start_y,
            end_x=over_x,
            end_y=over_y,
            total_time_ms=movement_time_ms * 0.78,
            steps=max(6, int(steps * 0.75)),
        )

        await page.wait_for_timeout(_sample_lognormal_ms(80, 220))

        await _move_mouse_curve(
            page=page,
            start_x=over_x,
            start_y=over_y,
            end_x=target_x,
            end_y=target_y,
            total_time_ms=movement_time_ms * 0.22,
            steps=max(3, int(steps * 0.25)),
            jitter_scale=0.45,
        )
    else:
        await _move_mouse_curve(
            page=page,
            start_x=start_x,
            start_y=start_y,
            end_x=target_x,
            end_y=target_y,
            total_time_ms=movement_time_ms,
            steps=steps,
        )

    hover_wait_ms = _sample_lognormal_ms(120, 650)
    await page.wait_for_timeout(hover_wait_ms)

    # Re-verify bounding box right before click to prevent missing due to layout shift
    final_box = await locator.bounding_box(timeout=timeout_ms)
    if final_box:
        if not (final_box["x"] <= target_x <= final_box["x"] + final_box["width"] and
                final_box["y"] <= target_y <= final_box["y"] + final_box["height"]):
            # Target moved out of previous coordinates. Adjust instantly.
            target_x, target_y = _sample_click_point_in_box(final_box)
            await page.mouse.move(target_x, target_y, steps=2)
            await page.wait_for_timeout(random.randint(40, 90))

    await page.mouse.down()

    click_hold_ms = _sample_lognormal_ms(45, 170)
    await page.wait_for_timeout(click_hold_ms)

    await page.mouse.up()

    _set_mouse_position(page, target_x, target_y)

    return {
        "status": "clicked",
        "target_x": round(target_x, 2),
        "target_y": round(target_y, 2),
        "distance": round(distance, 2),
        "target_width": round(target_width, 2),
        "movement_time_ms": round(movement_time_ms, 2),
        "steps": steps,
        "hover_wait_ms": hover_wait_ms,
        "click_hold_ms": click_hold_ms,
        "overshoot": use_overshoot,
    }


async def human_like_click_selector(
    page: Page,
    selector: str,
    timeout_ms: int = 5000,
    debug: bool = False,
) -> Dict[str, Any]:
    locator = page.locator(selector).first

    return await human_like_click(
        page=page,
        locator=locator,
        timeout_ms=timeout_ms,
        debug=debug,
    )


async def _move_mouse_curve(
    page: Page,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    total_time_ms: float,
    steps: int,
    jitter_scale: float = 1.0,
):
    """
    Di chuyển theo quadratic Bezier + easing + jitter.

    total_time_ms được chia ra các step delay nhỏ.
    """

    steps = max(3, steps)

    distance = _distance(start_x, start_y, end_x, end_y)

    control_x, control_y = _make_control_point(
        start_x=start_x,
        start_y=start_y,
        end_x=end_x,
        end_y=end_y,
        distance=distance,
    )

    base_delay = max(4.0, total_time_ms / steps)

    for i in range(1, steps + 1):
        t = i / steps

        eased_t = _smoothstep(t)

        x, y = _quadratic_bezier(
            start_x=start_x,
            start_y=start_y,
            control_x=control_x,
            control_y=control_y,
            end_x=end_x,
            end_y=end_y,
            t=eased_t,
        )

        # Jitter mạnh hơn ở giữa đường, giảm gần target để tránh miss click.
        mid_factor = math.sin(math.pi * t)
        jitter = random.gauss(0, 1.0) * mid_factor * jitter_scale

        x += jitter
        y += random.gauss(0, 1.0) * mid_factor * jitter_scale

        await page.mouse.move(x, y)

        delay = int(max(3, random.gauss(base_delay, base_delay * 0.25)))
        await page.wait_for_timeout(delay)


def _sample_click_point_in_box(box: Dict[str, float]) -> Tuple[float, float]:
    """
    Chọn điểm click trong vùng an toàn của element.

    Không luôn click chính giữa.
    Không click quá sát mép.
    """

    x = box["x"] + _sample_beta_centered() * box["width"]
    y = box["y"] + _sample_beta_centered() * box["height"]

    return x, y


def _sample_beta_centered(alpha: float = 2.5, beta: float = 2.5) -> float:
    """
    Phân phối beta đối xứng.

    Giá trị thường rơi gần giữa target hơn là sát mép.
    """
    value = random.betavariate(alpha, beta)

    return min(0.88, max(0.12, value))


def _estimate_movement_time_ms(
    distance: float,
    target_width: float,
    a_ms: float = 120.0,
    b_ms: float = 150.0,
) -> float:
    """
    Ước lượng movement time theo Fitts's Law.

    ID = log2(D / W + 1)
    MT = a + b * ID

    Thêm noise log-normal nhẹ để không deterministic.
    """

    safe_width = max(4.0, target_width)
    safe_distance = max(1.0, distance)

    index_of_difficulty = math.log2(safe_distance / safe_width + 1)

    mean_ms = a_ms + b_ms * index_of_difficulty

    noise = random.lognormvariate(0, 0.18)

    movement_time = mean_ms * noise

    return min(1800.0, max(180.0, movement_time))


def _estimate_steps(distance: float, movement_time_ms: float) -> int:
    """
    Tính số bước mouse.move.

    Target:
    - gần: ít bước
    - xa: nhiều bước hơn
    - movement_time dài: nhiều bước hơn
    """

    by_distance = distance / random.uniform(35, 65)
    by_time = movement_time_ms / random.uniform(18, 34)

    steps = int((by_distance + by_time) / 2)

    return min(42, max(7, steps))


def _make_control_point(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    distance: float,
) -> Tuple[float, float]:
    """
    Tạo control point cho Bezier.

    Đường cong lệch nhẹ theo phương vuông góc với vector di chuyển.
    """

    mid_x = (start_x + end_x) / 2
    mid_y = (start_y + end_y) / 2

    dx = end_x - start_x
    dy = end_y - start_y

    length = max(1.0, math.sqrt(dx * dx + dy * dy))

    # Vector vuông góc chuẩn hóa.
    nx = -dy / length
    ny = dx / length

    curvature = random.uniform(-0.22, 0.22) * min(distance, 600)

    control_x = mid_x + nx * curvature
    control_y = mid_y + ny * curvature

    return control_x, control_y


def _make_overshoot_point(
    start_x: float,
    start_y: float,
    target_x: float,
    target_y: float,
) -> Tuple[float, float]:
    """
    Tạo điểm overshoot nhỏ theo hướng di chuyển.
    """

    dx = target_x - start_x
    dy = target_y - start_y

    length = max(1.0, math.sqrt(dx * dx + dy * dy))

    ux = dx / length
    uy = dy / length

    overshoot_distance = random.uniform(8, 28)

    over_x = target_x + ux * overshoot_distance + random.uniform(-4, 4)
    over_y = target_y + uy * overshoot_distance + random.uniform(-4, 4)

    return over_x, over_y


def _quadratic_bezier(
    start_x: float,
    start_y: float,
    control_x: float,
    control_y: float,
    end_x: float,
    end_y: float,
    t: float,
) -> Tuple[float, float]:
    one_minus_t = 1 - t

    x = (
        one_minus_t * one_minus_t * start_x
        + 2 * one_minus_t * t * control_x
        + t * t * end_x
    )

    y = (
        one_minus_t * one_minus_t * start_y
        + 2 * one_minus_t * t * control_y
        + t * t * end_y
    )

    return x, y


def _smoothstep(t: float) -> float:
    """
    Easing function:
    - đầu chậm
    - giữa nhanh
    - cuối chậm
    """
    return t * t * (3 - 2 * t)


def _sample_lognormal_ms(min_ms: int, max_ms: int) -> int:
    """
    Sinh delay lệch phải bằng log-normal, rồi clamp vào khoảng cho phép.
    """

    center = (min_ms + max_ms) / 2

    value = random.lognormvariate(
        math.log(max(1, center)),
        0.35,
    )

    return int(min(max_ms, max(min_ms, value)))


async def _get_or_init_mouse_position(page: Page) -> Tuple[float, float]:
    """
    Playwright không expose vị trí mouse hiện tại.
    Ta lưu tạm trong page object.
    """

    pos = getattr(page, "_human_mouse_position", None)

    if pos:
        return pos

    viewport = page.viewport_size or {"width": 1365, "height": 768}

    x = random.uniform(viewport["width"] * 0.35, viewport["width"] * 0.65)
    y = random.uniform(viewport["height"] * 0.35, viewport["height"] * 0.65)

    await page.mouse.move(x, y)

    _set_mouse_position(page, x, y)

    return x, y


def _set_mouse_position(page: Page, x: float, y: float):
    setattr(page, "_human_mouse_position", (x, y))


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1

    return math.sqrt(dx * dx + dy * dy)
