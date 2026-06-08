import mcp.types as types
from core.browser import BrowserManager


async def handle_scroll(arguments: dict, browser: BrowserManager) -> list[types.TextContent]:
    amount = arguments.get("amount", 1000)

    if not browser.page:
        return [types.TextContent(type="text", text="Error: No page opened.", isError=True)]

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
                    "description": "Scroll amount in pixels. Positive scrolls down, negative scrolls up."
                }
            }
        }
    ),
    "handle": handle_scroll
}


async def handle_scroll_to_bottom(arguments: dict, browser: BrowserManager) -> list[types.TextContent]:
    if not browser.page:
        return [types.TextContent(type="text", text="Error: No page opened.", isError=True)]

    await browser.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    return [types.TextContent(type="text", text="Scrolled to bottom")]


scroll_to_bottom_tool = {
    "schema": types.Tool(
        name="browser_scroll_to_bottom",
        description="Scroll current page to bottom",
        inputSchema={"type": "object", "properties": {}}
    ),
    "handle": handle_scroll_to_bottom
}


SCROLL_MODULE = [
    scroll_tool,
    scroll_to_bottom_tool,
]