"""One owned official-SDK peer; no external service or credentials."""

import asyncio

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool


async def list_tools(_context, _params):
    return ListToolsResult(tools=[Tool(name="echo", description="Echo local test input", inputSchema={"type": "object"})])


async def call_tool(_context, params):
    return CallToolResult(content=[TextContent(type="text", text=str((params.arguments or {}).get("text", "")))])


async def main():
    server = Server("owned-lifetime-peer", version="1", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
