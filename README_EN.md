# OmniParser MCP Server

[![CI](https://github.com/cute-aaa/OmniParser-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/cute-aaa/OmniParser-MCP/actions/workflows/ci.yml)

Wrap Microsoft [OmniParser](https://github.com/microsoft/OmniParser) — the screen parsing tool for
pure-vision GUI agents — as a [Model Context Protocol](https://modelcontextprotocol.io) server, so any
MCP client (Claude Desktop, Cursor, Cline, ...) can turn a screenshot into structured UI elements:
text boxes, icons, bounding-box coordinates, interactivity flags and semantic descriptions.

This repository is a **standalone project**: it does not contain OmniParser's models or code. It is a
thin MCP proxy that calls the official `omniparserserver` HTTP API over localhost.

## Architecture

```
MCP client (Claude Desktop / Cursor / Cline / ...)
   │  stdio
   ▼
omniparser_mcp.py   (this repo, MCP Server, thin proxy, deps: mcp + httpx only)
   │  HTTP localhost (OMNIPARSER_API_URL, default http://127.0.0.1:8010)
   ▼
omniparserserver    (official OmniParser, FastAPI, models resident in memory)
                     YOLOv9 icon detection + Florence-2 icon captioning + EasyOCR text OCR
```

The MCP layer **does not care where OmniParser is installed** — it only talks to an HTTP address.
OmniParser may live in any local directory, another machine, Docker, or a remote server; just tell the
MCP server the address via `OMNIPARSER_API_URL`.

> **Port note**: this project defaults to port **8010** (not the official 8000) to avoid clashing with
> common dev tools. The port is fully configurable: start the backend with `-Port` and set
> `OMNIPARSER_API_URL` to the same address.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `OMNIPARSER_API_URL` | Backend HTTP address | `http://127.0.0.1:8010` |
| `OMNIPARSER_HOME` | Path to the official OmniParser repo; when set, the MCP server **auto-starts** the backend if it is not running | empty (manual start) |
| `OMNIPARSER_DEVICE` | Device used when auto-starting the backend | `cuda` (set `cpu` without a GPU) |

`OMNIPARSER_API_URL` can be set in three ways (highest precedence first): process environment
variable, the `env` field of your MCP client config, or the code default.

## Quick start

### 1. Install the official OmniParser (one-time)

```bash
git clone https://github.com/microsoft/OmniParser
cd OmniParser
conda create -n omni python==3.12 && conda activate omni
pip install -r requirements.txt
# Download model weights (see the official README; for CN networks first run:
#   export HF_ENDPOINT=https://hf-mirror.com)
```

### 2. Start the backend (choose one)

**Option A — manual start (recommended, you own the backend lifecycle)**

```powershell
# From this repo; auto-detects the OmniParser directory, or specify it:
pwsh -File start_backend.ps1 -OmniParserHome D:\OmniParser -Device cuda
```

**Option B — let MCP auto-start it**

Add `OMNIPARSER_HOME` to the `env` of your MCP client config (see below). When the backend is not
running, the first tool call launches it automatically and waits until it is ready (first start takes
~30–60 s while models load).

### 3. Install this repo's deps and register the MCP server

```bash
pip install -r requirements.txt    # mcp + httpx only
```

**Claude Desktop** — edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "omniparser": {
      "command": "python",
      "args": ["D:\\OmniParser-MCP\\omniparser_mcp.py"],
      "env": {
        "OMNIPARSER_API_URL": "http://127.0.0.1:8010",
        "OMNIPARSER_HOME": "D:\\OmniParser",
        "OMNIPARSER_DEVICE": "cuda"
      }
    }
  }
}
```

**Cursor / Cline** — ready-made configs are included (use the `${workspaceFolder}` variable, so no
path editing is needed after cloning): `.cursor/mcp.json` and `.cline/mcp_settings.json`.

### 4. Smoke test

```bash
python test_mcp.py        # full local test (needs the backend running)
python test_ci_smoke.py   # CI-safe test (no backend / GPU required)
```

## Tools

| Tool | Arguments | Returns |
| --- | --- | --- |
| `parse_screen` | `image_path` or `base64_image` (one of them), `image_size="W,H"`, `box_threshold=0.05`, `iou_threshold=0.1`, `save_som_to="out.png"` | Element list with pixel + ratio bounding boxes: `type / px_xyxy / ratio_xyxy / interactivity / content`; optionally saves the annotated image |
| `omniparser_status` | — | Backend health; auto-starts the backend when `OMNIPARSER_HOME` is set and it is down |

Example:

```
User: parse C:\shots\app.png and tell me where the search box is
Agent: calls parse_screen(image_path="C:\shots\app.png", image_size="2560,1440")
       → [12] text px=(320,180,880,230) content='Search...' interactivity=True
       Search box center ≈ (600, 205)
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Tool reports "backend not reachable" | Start the backend (`start_backend.ps1`) or set `OMNIPARSER_HOME` to enable auto-start |
| Auto-start still fails | Check `OMNIPARSER_DEVICE` (`cpu` without a GPU), weights downloaded, deps installed; auto-start logs go to `%TEMP%\omniparser_backend.log` |
| Empty parse results | Lower `box_threshold` (e.g. 0.03) |
| First call is slow | Expected: model warm-up takes ~30–40 s, later calls are faster |

## License

MIT. OmniParser model weights are subject to their own licenses.
