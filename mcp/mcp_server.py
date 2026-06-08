import json
from core.browser import BrowserManager
from mcp.tool import NAVIGATE_MODULE
from mcp.tool import SELECTOR_MODULE
from mcp.tool import KEYBOARD_MODULE
from mcp.tool import MOUSE_MODULE
from mcp.tool import SCROLL_MODULE

from mcp.server import Server
from mcp.server.stdio import StdioServer
from mcp.types import Type
import logging
import asyncio

logger = logging.getLogger(__name__)


class McpServer:
    def __init__(self, url: str):
        self.page = None
        self.browser_manager = BrowserManager()
        self.tools = [
            NAVIGATE_MODULE,
            SELECTOR_MODULE,
            KEYBOARD_MODULE,
            MOUSE_MODULE,
            SCROLL_MODULE,
        ]
        self.server = StdioServer(self.tools)
        self.tool_map = {tool["schema"].name: tool for tool in self.tools}
        self.register_handlers()

    def register_handlers(self):
        @self.server.list_tools()
        async def list_tools():
            return [tool["schema"] for tool in self.tools]

        @self.server.call_tool()
        async def call_toll(name: str, args: dict | None):
            if args is None:
                args = {}
            tool = self.tool_map.get(name)
            if not tool:
                return [
                    types.TextContent(
                        type="text", text=f"Tool {name} not found.", isError=True
                    )
                ]
            try:
                logger.info(f"Calling tool {name} with args {args}")
                result = await tool["handle"](args, self.browser_manager)
                return result
            except Exception as e:
                logger.error(f"Error calling tool {name}: {e}")
                return [
                    types.TextContent(
                        type="text", text=f"Tool {name} failed: {e}", isError=True
                    )
                ]

    async def run(self):
        await self.browser_manager.init_browser()
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


async def main():
    mcp_server = McpServer("")
    await mcp_server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
