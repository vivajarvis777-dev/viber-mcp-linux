"""Standalone MCP client for the Viber server — test the tools without Claude Code.

Usage:
  uv run client.py list
  uv run client.py open   "+639171234567"
  uv run client.py send   "+639171234567" "hello from MCP" [--dry-run]
  uv run client.py read
  uv run client.py contacts
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = str(Path(__file__).with_name("server.py"))


async def _run(argv: list[str]) -> None:
    # Launch the server in-process over stdio using the same interpreter (uv run).
    params = StdioServerParameters(command=sys.executable, args=[SERVER])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            if not argv or argv[0] == "list":
                tools = await session.list_tools()
                for t in tools.tools:
                    print(f"- {t.name}: {t.description.splitlines()[0] if t.description else ''}")
                return

            cmd, rest = argv[0], argv[1:]
            if cmd == "open":
                result = await session.call_tool("open_chat", {"to": rest[0]})
            elif cmd == "send":
                dry = "--dry-run" in rest
                rest = [a for a in rest if a != "--dry-run"]
                to, text = rest[0], rest[1]
                result = await session.call_tool(
                    "send_message", {"to": to, "text": text, "dry_run": dry}
                )
            elif cmd == "read":
                result = await session.call_tool("read_open_chat", {})
            elif cmd == "contacts":
                result = await session.call_tool("list_contacts", {})
            else:
                print(f"Unknown command: {cmd}")
                print(__doc__)
                return

            # Structured content when available, else the text blocks.
            if result.structuredContent is not None:
                print(json.dumps(result.structuredContent, indent=2, ensure_ascii=False))
            else:
                for block in result.content:
                    print(getattr(block, "text", block))


def main() -> None:
    asyncio.run(_run(sys.argv[1:]))


if __name__ == "__main__":
    main()
