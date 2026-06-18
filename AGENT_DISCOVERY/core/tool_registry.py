# core/tool_registry.py

import json
from toolfb.search_trend import search_trend_fb


class ToolRegistry:
    def __init__(self, browser):
        self.browser = browser
        self.tools = {}

        modules = [search_trend_fb]

        for tool in modules:
            name = tool["schema"].name
            self.tools[name] = tool

    def list_tools(self):
        return list(self.tools.values())

    def get_tool_descriptions(self):
        result = []

        for name, tool in self.tools.items():
            schema = tool["schema"]

            result.append(
                {
                    "name": schema.name,
                    "description": schema.description,
                    "inputSchema": schema.inputSchema,
                }
            )

        return result

    async def call_tool(self, name: str, arguments: dict | None = None):
        if arguments is None:
            arguments = {}

        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")

        handler = self.tools[name]["handle"]

        contents = await handler(arguments, self.browser)

        # MCP TextContent -> plain text
        texts = []
        for item in contents:
            text = getattr(item, "text", None)
            if text:
                texts.append(text)

        if not texts:
            return None

        raw = "\n".join(texts)

        # Nếu output là JSON thì parse luôn
        try:
            return json.loads(raw)
        except Exception:
            return raw
