# tools/navigate.py
import mcp.types as types
from core.browser import BrowserManager


async def handle_navigate(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    url = arguments.get("url")
    if not url:
        return [
            types.TextContent(
                type="text", text="Error: url argument is required.", isError=True
            )
        ]

    if not browser.page:
        await browser.launch_page(url)
    else:
        # networkidle: chờ không còn request nào trong 500ms
        # → bắt được nhiều API hơn so với domcontentloaded (SPA thường load API sau khi DOM xong)
        try:
            await browser.page.goto(url, wait_until="networkidle", timeout=15000)
        except Exception:
            # Fallback nếu trang không bao giờ đạt networkidle (infinite poll, websocket...)
            await browser.page.goto(url, wait_until="domcontentloaded", timeout=15000)

    # Cập nhật state sau khi navigate để agent không truy cập lại URL này
    actual_url = browser.page.url
    browser.current_url = actual_url
    if not hasattr(browser, "visited_urls"):
        browser.visited_urls = {}
    browser.visited_urls[actual_url] = {"status": "visited"}

    return [types.TextContent(type="text", text=f"Navigated to {actual_url}")]


navigate_tool = {
    "schema": types.Tool(
        name="browser_navigate",
        description="Điều hướng trình duyệt tới một URL mới",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"}
            },
            "required": ["url"],
        },
    ),
    "handle": handle_navigate,
}


async def handle_go_back(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    if browser.page:
        await browser.page.go_back(wait_until="domcontentloaded")
        return [types.TextContent(type="text", text="Went back to previous page")]
    return [
        types.TextContent(
            type="text", text="Error: No page to go back to.", isError=True
        )
    ]


go_back_tool = {
    "schema": types.Tool(
        name="browser_navigate_back",
        description="Quay lại trang trước đó",
        inputSchema={"type": "object", "properties": {}},
    ),
    "handle": handle_go_back,
}


async def handle_go_forward(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    if browser.page:
        await browser.page.go_forward(wait_until="domcontentloaded")
        return [types.TextContent(type="text", text="Went forward to next page")]
    return [
        types.TextContent(
            type="text", text="Error: No page to go forward to.", isError=True
        )
    ]


go_forward_tool = {
    "schema": types.Tool(
        name="browser_navigate_forward",
        description="Đi tới trang tiếp theo trong lịch sử duyệt web",
        inputSchema={"type": "object", "properties": {}},
    ),
    "handle": handle_go_forward,
}

NAVIGATE_MODULE = [navigate_tool, go_back_tool, go_forward_tool]
