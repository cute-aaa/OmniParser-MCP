"""Direct unit tests for omniparser_mcp (no MCP stdio subprocess, no backend).

Exercises the pure logic of the MCP server module so CI can validate it
without spawning child processes or needing GPU/models.

Run: python test_direct.py
"""

import os
import sys

os.environ.setdefault("OMNIPARSER_API_URL", "http://127.0.0.1:9")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import omniparser_mcp as m  # noqa: E402


def test_load_base64() -> None:
    assert m._load_base64("", "")[1].startswith("provide either")
    assert m._load_base64("a.png", "b64")[1].startswith("provide either")
    assert m._load_base64("/nonexistent/x.png", "")[1].startswith("image file not found")
    ok, err = m._load_base64("", "aGVsbG8=")
    assert err == "" and ok == "aGVsbG8="


def test_format_elements() -> None:
    parsed = [{"type": "text", "bbox": [0, 0, 0.5, 0.5], "content": "hi", "interactivity": True}]
    out = m._format_elements(parsed, 100, 100)
    assert "px_xyxy=(0,0,50,50)" in out
    assert "ratio_xyxy=(0.000,0.000,0.500,0.500)" in out
    assert "content='hi'" in out
    assert m._format_elements([], 100, 100) == "(no elements detected)"


def test_probe_graceful() -> None:
    err = m._probe()
    assert err != "", "probe should fail against an unroutable port"
    assert "127.0.0.1:9" in err


def test_ensure_backend_no_home() -> None:
    # Without OMNIPARSER_HOME, auto-start must fail gracefully with guidance.
    old = m.OMNIPARSER_HOME
    m.OMNIPARSER_HOME = ""
    try:
        err = m._ensure_backend()
        assert err != "" and "OMNIPARSER_HOME" in err
    finally:
        m.OMNIPARSER_HOME = old


if __name__ == "__main__":
    test_load_base64()
    test_format_elements()
    test_probe_graceful()
    test_ensure_backend_no_home()
    print("DIRECT TESTS PASSED")
