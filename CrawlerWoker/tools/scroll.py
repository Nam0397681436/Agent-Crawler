import mcp.types as types
from core.browser import BrowserManager
import random
import time


async def handle_scroll(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    amount = arguments.get("amount", 1000)

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.mouse.wheel(0, amount)
    return [types.TextContent(type="text", text=f"Scrolled by {amount}")]


scroll_tool = {
    "schema": types.Tool(
        name="browser_scroll",
        description="Scroll current page by pixel amount",
        inputSchema={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Scroll amount in pixels. Positive scrolls down, negative scrolls up.",
                }
            },
        },
    ),
    "handle": handle_scroll,
}


async def handle_scroll_to_bottom(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    return [types.TextContent(type="text", text="Scrolled to bottom")]


scroll_to_bottom_tool = {
    "schema": types.Tool(
        name="browser_scroll_to_bottom",
        description="Scroll current page to bottom",
        inputSchema={"type": "object", "properties": {}},
    ),
    "handle": handle_scroll_to_bottom,
}
import mcp.types as types
from core.browser import BrowserManager


async def handle_auto_scroll(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    max_scrolls = arguments.get("max_scrolls", 10)
    amount = arguments.get("amount", 1200)
    wait_ms = arguments.get("wait_ms", 3000)
    stable_rounds_limit = arguments.get("stable_rounds_limit", 3)

    if not browser.page:
        return [
            types.TextContent(
                type="text",
                text="Error: No page opened.",
                isError=True,
            )
        ]

    result = await browser.page.evaluate(
        """
        async ({ maxScrolls, amount, waitMs, stableRoundsLimit }) => {
            const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

            let scrollCount = 0;
            let stableRounds = 0;
            let lastHeight = document.body.scrollHeight;
            let lastY = window.scrollY;

            for (let i = 0; i < maxScrolls; i++) {
                window.scrollBy(0, amount);
                scrollCount++;

                await sleep(waitMs);

                const currentHeight = document.body.scrollHeight;
                const currentY = window.scrollY;
                const viewportHeight = window.innerHeight;

                const reachedBottom =
                    Math.ceil(currentY + viewportHeight) >= currentHeight;

                const heightNotChanged = currentHeight === lastHeight;
                const yNotChanged = currentY === lastY;

                if (heightNotChanged && (reachedBottom || yNotChanged)) {
                    stableRounds++;
                } else {
                    stableRounds = 0;
                }

                lastHeight = currentHeight;
                lastY = currentY;

                if (stableRounds >= stableRoundsLimit) {
                    return {
                        stopped_reason: "reached_stable_bottom",
                        scroll_count: scrollCount,
                        final_scroll_y: currentY,
                        final_scroll_height: currentHeight,
                    };
                }
            }

            return {
                stopped_reason: "max_scrolls_reached",
                scroll_count: scrollCount,
                final_scroll_y: window.scrollY,
                final_scroll_height: document.body.scrollHeight,
            };
        }
        """,
        {
            "maxScrolls": max_scrolls,
            "amount": amount,
            "waitMs": wait_ms,
            "stableRoundsLimit": stable_rounds_limit,
        },
    )

    return [
        types.TextContent(
            type="text",
            text=(
                f"Auto scroll done. "
                f"reason={result.get('stopped_reason')}, "
                f"scroll_count={result.get('scroll_count')}, "
                f"final_scroll_y={result.get('final_scroll_y')}, "
                f"final_scroll_height={result.get('final_scroll_height')}"
            ),
        )
    ]


auto_scroll_tool = {
    "schema": types.Tool(
        name="browser_auto_scroll",
        description="""
Tự động cuộn trang để kích hoạt lazy load, infinite scroll và các API phát sinh.

Tool sẽ:
- Cuộn xuống từng đoạn
- Chờ nội dung động tải thêm
- Dừng khi trang không tăng chiều cao nữa
- Nếu trang dạng infinite scroll thì dừng theo max_scrolls để tránh chạy vô hạn

Dùng trước khi snapshot hoặc trước khi quyết định chuyển sang URL khác.
""",
        inputSchema={
            "type": "object",
            "properties": {
                "max_scrolls": {
                    "type": "number",
                    "description": "Số lần scroll tối đa, mặc định 30",
                },
                "amount": {
                    "type": "number",
                    "description": "Số pixel mỗi lần scroll, mặc định 1200",
                },
                "wait_ms": {
                    "type": "number",
                    "description": "Thời gian chờ sau mỗi lần scroll, tính bằng milliseconds, mặc định 1000",
                },
                "stable_rounds_limit": {
                    "type": "number",
                    "description": "Số vòng liên tiếp trang không đổi để coi là đã tới cuối, mặc định 3",
                },
            },
        },
    ),
    "handle": handle_auto_scroll,
}

SCROLL_MODULE = [
    scroll_tool,
    scroll_to_bottom_tool,
    auto_scroll_tool,
]
