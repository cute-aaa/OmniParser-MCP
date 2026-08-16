"""CI smoke test: verifies the MCP server starts, exposes its tools, and
returns sensible errors without a real OmniParser backend (no GPU/models).

Run: python test_ci_smoke.py
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
SERVER_PY = ROOT / "omniparser_mcp.py"

# Force a port that will never have a backend on CI; the backend probe must
# fail gracefully (no crash, actionable message).
ENV = {
    **{k: v for k, v in __import__("os").environ.items()},
    "OMNIPARSER_API_URL": "http://127.0.0.1:9",
    "OMNIPARSER_HOME": "",
    "OMNIPARSER_DEVICE": "cpu",
}


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_PY)], cwd=str(ROOT), env=ENV)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert "parse_screen" in names, f"missing parse_screen, got {names}"
            assert "omniparser_status" in names, f"missing omniparser_status, got {names}"
            print("OK tools:", sorted(names))

            res = await session.call_tool("omniparser_status", {})
            text = res.content[0].text
            assert "DOWN" in text and "OMNIPARSER" in text.upper(), f"unexpected status text: {text[:200]}"
            print("OK omniparser_status (graceful DOWN):", text.splitlines()[0])

            res = await session.call_tool("parse_screen", {})
            text = res.content[0].text
            assert "ERROR" in text, f"unexpected parse_screen text: {text[:200]}"
            print("OK parse_screen (graceful ERROR):", text.splitlines()[0])

    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
