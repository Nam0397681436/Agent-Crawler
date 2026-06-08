import json
import mcp.types as types
from core.browser import BrowserManager


async def handle_current_state(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    data = {
        "current_url": browser.current_url,
        "page_url": browser.page.url if browser.page else None,
        "visited_urls": browser.visited_urls,
    }
    return [
        types.TextContent(
            type="text", text=json.dumps(data, ensure_ascii=False, indent=2)
        )
    ]


current_state_tool = {
    "schema": types.Tool(
        name="crawler_current_state",
        description="""
Xem trạng thái hiện tại của worker crawler.

Trả về:
- URL hiện tại
- URL thực tế của page
- Danh sách URL đã truy cập

Dùng để agent biết mình đang ở đâu và tránh click lại URL đã thử.
""",
        inputSchema={"type": "object", "properties": {}},
    ),
    "handle": handle_current_state,
}


STATE_MODULE = [
    current_state_tool,
]
