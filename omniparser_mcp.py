#!/usr/bin/env python
"""
OmniParser MCP Server

Exposes Microsoft OmniParser (screen parsing for pure-vision GUI agents) as
Model Context Protocol tools over stdio transport.

This is a thin proxy over the omniparserserver HTTP API (the models live in
the official OmniParser repo, so they are loaded once per process and shared
by every MCP client):

    GET  {OMNIPARSER_API_URL}/probe/   -> health check
    POST {OMNIPARSER_API_URL}/parse/   -> { base64_image } ->
                                           { som_image_base64, parsed_content_list, latency }

Prerequisite: install and start the official OmniParser backend
(https://github.com/microsoft/OmniParser), e.g.

    python -m omniparserserver \
        --caption_model_name florence2 \
        --caption_model_path ../../weights/icon_caption_florence \
        --device cuda --BOX_TRESHOLD 0.05 --host 127.0.0.1 --port 8010

Then run this server and register it with any MCP client (Claude Desktop,
Cursor, Cline, ...) using stdio:

    python omniparser_mcp.py
"""

import base64
import os
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    raise SystemExit(
        "FastMCP is not available. This project requires mcp 1.x (mcp 2.0 moved FastMCP "
        "to a separate package). Install with:\n"
        "    pip install 'mcp>=1.0,<2.0'"
    )

# Default backend port is 8010 (not 8000) to avoid clashing with other dev
# tools; override with OMNIPARSER_API_URL if the backend runs elsewhere.
API_URL = os.environ.get("OMNIPARSER_API_URL", "http://127.0.0.1:8010")
# Optional: path to the official OmniParser repo, used to auto-start the
# backend when it is not running. Leave empty to require manual start.
OMNIPARSER_HOME = os.environ.get("OMNIPARSER_HOME", "").strip().strip('"').strip("'")
OMNIPARSER_DEVICE = os.environ.get("OMNIPARSER_DEVICE", "cuda")
DEFAULT_BOX_THRESHOLD = 0.05
DEFAULT_IOU_THRESHOLD = 0.1

mcp = FastMCP("omniparser")

_backend_proc: subprocess.Popen | None = None


def _probe() -> str:
    """Return '' if the backend is up, otherwise a human-readable hint."""
    try:
        r = httpx.get(f"{API_URL}/probe/", timeout=5)
        if r.status_code == 200:
            return ""
        return f"backend returned HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001 - surface any connection issue
        return f"backend not reachable at {API_URL} ({type(e).__name__}: {e})"


def _backend_host_port() -> tuple[str, int]:
    p = urlparse(API_URL)
    return p.hostname or "127.0.0.1", p.port or 8010


def _start_backend() -> str:
    """Auto-start the official omniparserserver under OMNIPARSER_HOME.

    Returns '' on success (backend became ready), otherwise an error hint.
    """
    global _backend_proc
    if not OMNIPARSER_HOME:
        return "set OMNIPARSER_HOME to the official OmniParser repo to auto-start the backend"
    if not os.path.isdir(OMNIPARSER_HOME):
        return f"OMNIPARSER_HOME is not a directory: {OMNIPARSER_HOME}"
    server_dir = os.path.join(OMNIPARSER_HOME, "omnitool", "omniparserserver")
    if not os.path.isfile(os.path.join(server_dir, "omniparserserver.py")):
        return f"omniparserserver package not found under {OMNIPARSER_HOME} (looked in {server_dir})"

    host, port = _backend_host_port()
    cmd = [
        sys.executable, "-m", "omniparserserver",
        "--caption_model_name", "florence2",
        "--caption_model_path", "../../weights/icon_caption_florence",
        "--device", OMNIPARSER_DEVICE,
        "--BOX_TRESHOLD", "0.05",
        "--host", host,
        "--port", str(port),
    ]
    env = dict(os.environ)
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    log_path = os.path.join(tempfile.gettempdir(), "omniparser_backend.log")
    log_file = open(log_path, "wb")
    try:
        _backend_proc = subprocess.Popen(
            cmd, cwd=server_dir, env=env,
            stdin=subprocess.DEVNULL,   # do not inherit the MCP stdio pipe
            stdout=log_file, stderr=subprocess.STDOUT,
        )
    except Exception as e:  # noqa: BLE001
        log_file.close()
        return f"failed to launch backend: {type(e).__name__}: {e}"

    # Wait until the backend answers /probe/ (model loading takes 30-60s).
    deadline = time.time() + 240
    while time.time() < deadline:
        if _probe() == "":
            return ""
        if _backend_proc.poll() is not None:
            return (
                f"backend process exited early (code {_backend_proc.returncode}); "
                f"see log {log_path}; check OMNIPARSER_DEVICE (cuda requires a GPU) "
                "or that OmniParser weights are downloaded"
            )
        time.sleep(3)
    return (
        f"backend did not become ready within 240s (device={OMNIPARSER_DEVICE}); "
        f"see log {log_path}"
    )


def _ensure_backend() -> str:
    """Probe; if down, try to auto-start it once. Returns '' when ready."""
    err = _probe()
    if not err:
        return ""
    start_err = _start_backend()
    if start_err:
        return f"{err}\nAuto-start failed: {start_err}"
    return ""


def _load_base64(image_path: str = "", base64_image: str = "") -> tuple[str, str]:
    """Return (base64_payload, error). Exactly one of the inputs must be set."""
    if image_path and base64_image:
        return "", "provide either image_path OR base64_image, not both"
    if not image_path and not base64_image:
        return "", "provide either image_path or base64_image"
    if image_path:
        if not os.path.isfile(image_path):
            return "", f"image file not found: {image_path}"
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii"), ""
        except Exception as e:  # noqa: BLE001
            return "", f"failed to read {image_path}: {e}"
    return base64_image, ""


def _format_elements(parsed: list, width: int, height: int) -> str:
    """Render parsed elements as compact, LLM-friendly text with pixel coords."""
    if not isinstance(parsed, list) or not parsed:
        return "(no elements detected)"
    lines = []
    for i, el in enumerate(parsed):
        elem_type = el.get("type", "?")
        bbox = el.get("bbox", [])
        content = el.get("content", "")
        interactive = el.get("interactivity", False)
        if isinstance(bbox, list) and len(bbox) == 4:
            x1, y1, x2, y2 = (float(v) for v in bbox)
            px = f"({int(x1 * width)},{int(y1 * height)},{int(x2 * width)},{int(y2 * height)})"
            ratio = f"({x1:.3f},{y1:.3f},{x2:.3f},{y2:.3f})"
        else:
            px = ratio = str(bbox)
        text = str(content).replace("\n", " ")[:120]
        lines.append(
            f"[{i}] {elem_type} px_xyxy={px} ratio_xyxy={ratio} "
            f"interactivity={interactive} content={text!r}"
        )
    return "\n".join(lines)


@mcp.tool()
def parse_screen(
    image_path: str = "",
    base64_image: str = "",
    image_size: str = "1920,1080",
    box_threshold: float = DEFAULT_BOX_THRESHOLD,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
    save_som_to: str = "",
) -> str:
    """Parse a screenshot into structured UI elements (text + icons with
    bounding boxes and semantic descriptions) using OmniParser.

    Args:
        image_path: local screenshot path (PNG/JPG). Use this OR base64_image.
        base64_image: base64-encoded image bytes. Use this OR image_path.
        image_size: "width,height" of the screenshot, used to convert the
            ratio coordinates into pixel coordinates in the output.
        box_threshold: detection confidence threshold (default 0.05).
        iou_threshold: NMS overlap threshold (default 0.1).
        save_som_to: optional local path to save the annotated (SoM) image.

    Returns:
        Text listing every detected element with pixel + ratio bounding boxes,
        plus the annotated image path when save_som_to was given.
    """
    err = _ensure_backend()
    if err:
        return (
            f"ERROR: {err}\n"
            "Start the OmniParser backend manually (see README.md):\n"
            "    pwsh -File <this-repo>\\start_backend.ps1 -OmniParserHome <official-OmniParser-dir>\n"
            "or set OMNIPARSER_HOME so the backend can be auto-started, "
            "or point OMNIPARSER_API_URL at an already running backend."
        )

    payload, load_err = _load_base64(image_path, base64_image)
    if load_err:
        return f"ERROR: {load_err}"

    try:
        w, h = (int(v) for v in image_size.replace("x", ",").replace(" ", "").split(","))
    except Exception:  # noqa: BLE001
        w, h = 1920, 1080

    try:
        with httpx.Client(timeout=300) as client:
            r = client.post(
                f"{API_URL}/parse/",
                json={"base64_image": payload},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:  # noqa: BLE001
        return f"ERROR: parse request failed: {type(e).__name__}: {e}"

    parsed = data.get("parsed_content_list", [])
    latency = data.get("latency", 0)
    som_b64 = data.get("som_image_base64", "")

    out = [f"OmniParser result (latency {latency:.1f}s, {len(parsed)} elements, image {w}x{h}):"]
    out.append(_format_elements(parsed, w, h))

    if save_som_to:
        try:
            with open(save_som_to, "wb") as f:
                f.write(base64.b64decode(som_b64))
            out.append(f"\nannotated image saved to: {save_som_to}")
        except Exception as e:  # noqa: BLE001
            out.append(f"\nWARNING: failed to save annotated image: {e}")

    return "\n".join(out)


@mcp.tool()
def omniparser_status() -> str:
    """Check whether the OmniParser backend service is running and ready.
    When OMNIPARSER_HOME is set and the backend is down, it is auto-started."""
    err = _ensure_backend()
    if not err:
        return "OmniParser backend is UP and ready (parse_screen is available)."
    return (
        "OmniParser backend is DOWN.\n"
        f"Reason: {err}\n"
        "Start it manually (see README.md), set OMNIPARSER_HOME to auto-start, "
        "or point the OMNIPARSER_API_URL environment variable at a running backend."
    )


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
