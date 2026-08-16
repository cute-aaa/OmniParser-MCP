"""Smoke test for the OmniParser MCP server (stdio).

Run from this repo:
    python test_mcp.py

Requires the official omniparserserver backend running on :8010
(or set OMNIPARSER_API_URL).
"""

import asyncio
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
SERVER_PY = ROOT / "omniparser_mcp.py"
IMG = ROOT / "test_image.png"  # replace with any screenshot

# Pass through the MCP-relevant env vars explicitly (mcp stdio may not inherit
# shell-set vars reliably on Windows).
MCP_ENV = {
    **os.environ,
    "OMNIPARSER_API_URL": os.environ.get("OMNIPARSER_API_URL", "http://127.0.0.1:8010"),
    "OMNIPARSER_HOME": os.environ.get("OMNIPARSER_HOME", ""),
    "OMNIPARSER_DEVICE": os.environ.get("OMNIPARSER_DEVICE", "cuda"),
}


async def main():
    params = StdioServerParameters(
        command="python", args=[str(SERVER_PY)], cwd=str(ROOT), env=MCP_ENV
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("=== MCP tools ===")
            for t in tools.tools:
                print(f"  - {t.name}: {(t.description or '').splitlines()[0]}")

            res = await session.call_tool("omniparser_status", {})
            print("\n=== omniparser_status ===")
            print(res.content[0].text)

            if IMG.is_file():
                res = await session.call_tool(
                    "parse_screen",
                    {"image_path": str(IMG), "image_size": "1920,1080",
                     "save_som_to": str(ROOT / "test_som.png")},
                )
                print("\n=== parse_screen (truncated) ===")
                text = res.content[0].text
                print(text[:1500])
                print("..." if len(text) > 1500 else "")
            else:
                print(f"\n(skip parse_screen: put a screenshot at {IMG} to test it)")


asyncio.run(main())
