# tools/mouse.py
import mcp.types as types
from core.browser import BrowserManager


async def handle_click(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    selector = arguments.get("selector")

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.click(selector)
    return [types.TextContent(type="text", text=f"Clicked selector: {selector}")]


click_tool = {
    "schema": types.Tool(
        name="browser_click",
        description="Nhấn chuột vào một phần tử trên trang bằng CSS selector",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to click"}
            },
            "required": ["selector"],
        },
    ),
    "handle": handle_click,
}


async def handle_hover(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    selector = arguments.get("selector")

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.hover(selector)
    return [types.TextContent(type="text", text=f"Hovered selector: {selector}")]


hover_tool = {
    "schema": types.Tool(
        name="browser_hover",
        description="Di chuột qua một phần tử trên trang bằng CSS selector",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to hover"}
            },
            "required": ["selector"],
        },
    ),
    "handle": handle_hover,
}


async def handle_double_click(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    selector = arguments.get("selector")

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.dblclick(selector)
    return [types.TextContent(type="text", text=f"Double clicked selector: {selector}")]


double_click_tool = {
    "schema": types.Tool(
        name="browser_double_click",
        description="Nhấn đúp chuột vào một phần tử trên trang bằng CSS selector",
        inputSchema={
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector to double click",
                }
            },
            "required": ["selector"],
        },
    ),
    "handle": handle_double_click,
}


async def handle_mouse_move(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    x = arguments.get("x")
    y = arguments.get("y")

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.mouse.move(x, y)
    return [types.TextContent(type="text", text=f"Đã di chuyển chuột đến ({x}, {y})")]


move_mouse_tool = {
    "schema": types.Tool(
        name="browser_mouse_move",
        description="Di chuyển chuột đến tọa độ x, y",
        inputSchema={
            "type": "object",
            "properties": {
                "x": {"type": "number", "description": "Tọa độ X"},
                "y": {"type": "number", "description": "Tọa độ Y"},
            },
            "required": ["x", "y"],
        },
    ),
    "handle": handle_mouse_move,
}


async def handle_mouse_drag_xy(
    arguments: dict, browser: BrowserManager
) -> list[types.TextContent]:
    start_x = arguments.get("startX")
    start_y = arguments.get("startY")
    end_x = arguments.get("endX")
    end_y = arguments.get("endY")

    if not browser.page:
        return [
            types.TextContent(type="text", text="Error: No page opened.", isError=True)
        ]

    await browser.page.mouse.move(start_x, start_y)
    await browser.page.mouse.down()
    await browser.page.mouse.move(end_x, end_y)
    await browser.page.mouse.up()

    return [
        types.TextContent(
            type="text",
            text=f"Đã kéo chuột từ ({start_x}, {start_y}) đến ({end_x}, {end_y})",
        )
    ]


mouse_drag_xy_tool = {
    "schema": types.Tool(
        name="browser_mouse_drag_xy",
        description="Kéo chuột trái từ tọa độ bắt đầu đến tọa độ kết thúc",
        inputSchema={
            "type": "object",
            "properties": {
                "startX": {"type": "number", "description": "Tọa độ X bắt đầu"},
                "startY": {"type": "number", "description": "Tọa độ Y bắt đầu"},
                "endX": {"type": "number", "description": "Tọa độ X kết thúc"},
                "endY": {"type": "number", "description": "Tọa độ Y kết thúc"},
            },
            "required": ["startX", "startY", "endX", "endY"],
        },
    ),
    "handle": handle_mouse_drag_xy,
}
MOUSE_MODULE = [
    click_tool,
    hover_tool,
    double_click_tool,
    move_mouse_tool,
    mouse_drag_xy_tool,
]
