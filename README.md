# OmniParser MCP Server

[![CI](https://github.com/cute-aaa/OmniParser-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/cute-aaa/OmniParser-MCP/actions/workflows/ci.yml)　[English](README_EN.md)

把微软 [OmniParser](https://github.com/microsoft/OmniParser)（纯视觉 GUI Agent 的屏幕解析工具）封装为
[Model Context Protocol](https://modelcontextprotocol.io) 服务，让 Claude Desktop、Cursor、Cline 等
任何 MCP 客户端都能调用屏幕解析能力：给定一张截图，返回结构化的 UI 元素（文本、图标、坐标、语义描述）。

本仓库是**独立项目**：不包含 OmniParser 模型与官方代码，只提供一个薄 MCP 代理层，通过 HTTP 调用
官方 omniparserserver 服务。

## 架构

```
MCP 客户端 (Claude Desktop / Cursor / Cline / ...)
   │  stdio
   ▼
omniparser_mcp.py   (本仓库, MCP Server, 薄代理, 仅依赖 mcp + httpx)
   │  HTTP localhost (OMNIPARSER_API_URL, 默认 http://127.0.0.1:8010)
   ▼
omniparserserver    (官方 OmniParser, FastAPI, 模型常驻)
                     YOLOv9 图标检测 + Florence-2 图标描述 + EasyOCR 文本识别
```

MCP 层**不感知 OmniParser 的安装位置**——它只和 HTTP 地址通信。OmniParser 可以装在本机任意目录、
另一台机器、Docker 或远程服务器，只需把地址告诉 MCP（`OMNIPARSER_API_URL`）。

> **端口说明**：本项目默认后端端口是 **8010**（不是官方默认的 8000），避免与常用的 8000 端口
> 开发工具冲突。端口可任意更换：启动后端时指定 `-Port`，并把 `OMNIPARSER_API_URL` 改成对应地址
> 即可（二者保持一致）。

## 环境变量

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `OMNIPARSER_API_URL` | 后端 HTTP 地址 | `http://127.0.0.1:8010` |
| `OMNIPARSER_HOME` | 官方 OmniParser 仓库目录；设置后，后端未运行时 **MCP 会自动启动它** | 空（需手动启动） |
| `OMNIPARSER_DEVICE` | 自动启动后端时用的设备 | `cuda`（无 GPU 设为 `cpu`） |

三种方式指定 `OMNIPARSER_API_URL`：环境变量 / MCP 客户端配置的 `env` 字段 / 代码默认值（兜底）。

## 快速开始

### 1. 安装官方 OmniParser（一次性）

```powershell
git clone https://github.com/microsoft/OmniParser
cd OmniParser
conda create -n omni python==3.12 && conda activate omni
pip install -r requirements.txt
# 国内网络先设置 $env:HF_ENDPOINT="https://hf-mirror.com"，再按官方 README 下载权重
```

> 权重下载完成后，可先手动验证后端能起来（注意端口：本项目统一用 **8010**，
> 与官方默认 8000 不同，请显式加 `--port 8010`）：
>
> ```powershell
> python -m omniparserserver --caption_model_name florence2 `
>     --caption_model_path ../../weights/icon_caption_florence `
>     --device cuda --BOX_TRESHOLD 0.05 --host 127.0.0.1 --port 8010
> ```

### 2. 启动后端（二选一）

**方式 A — 手动启动（推荐，后端生命周期自己掌控）**

```powershell
# 从本仓库运行。start_backend.ps1 会自动向上层目录探测 OmniParser，
# 但本仓库 clone 后不含官方 OmniParser，通常需显式指定 -OmniParserHome：
pwsh -File start_backend.ps1 -OmniParserHome D:\OmniParser -Device cuda
```

**方式 B — MCP 自动启动**

在 MCP 客户端配置的 `env` 里加上 `OMNIPARSER_HOME`（见下节），后端未运行时会自动拉起并等待就绪
（首次加载模型约 30–60 秒，最长等待 240 秒），无需手动操作。

### 3. 安装本仓库依赖并注册 MCP

```powershell
pip install -r requirements.txt   # 仅 mcp(<2.0) + httpx
```

> 本仓库依赖建议装进**与步骤 1 相同的 conda 环境**（`omni`），MCP 层与 OmniParser 层共用
> 一个 Python 环境即可。

**Claude Desktop** — 编辑 `%APPDATA%\Claude\claude_desktop_config.json`（把
`D:\OmniParser-MCP`、`D:\OmniParser` 替换为你的实际路径）：

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

**Cursor / Cline** — 本仓库已附带现成配置（使用 `${workspaceFolder}` 变量，clone 即用），
按需在 `env` 里补 `OMNIPARSER_HOME` 即可开启自动启动：
- `.cursor/mcp.json`
- `.cline/mcp_settings.json`

### 4. 自测

```powershell
python test_mcp.py        # 完整测试：需后端已在 8010 运行、且仓库内放一张截图
                          # （默认用 test_image.png，可替换为任意截图）
python test_ci_smoke.py   # 轻量冒烟测试：无需后端/GPU，任何环境可跑
```

`test_mcp.py` 会枚举工具、检查后端状态并解析截图；`test_ci_smoke.py` 只验证
MCP server 能启动、工具可用、无后端时优雅报错。

## 工具说明

| 工具 | 参数 | 返回 |
| --- | --- | --- |
| `parse_screen` | `image_path` 或 `base64_image`（二选一）、`image_size="W,H"`、`box_threshold=0.05`、`iou_threshold=0.1`、`save_som_to="out.png"` | 结构化元素列表：`type / px_xyxy / ratio_xyxy / interactivity / content`，可选保存标注图 |
| `omniparser_status` | 无 | 后端健康状态；设置了 `OMNIPARSER_HOME` 且后端未运行时自动启动 |

调用示例：

```
用户: 解析这个截图 C:\shots\app.png 并告诉我搜索框在哪
Agent: 调用 parse_screen(image_path="C:\shots\app.png", image_size="2560,1440")
       → [12] text px=(320,180,880,230) content='Search...' interactivity=True
       搜索框中心 ≈ (600, 205)
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 工具报 backend not reachable | 启动后端（`start_backend.ps1`），或设置 `OMNIPARSER_HOME` 启用自动启动 |
| 自动启动后仍失败 | 确认 `OMNIPARSER_DEVICE`（无 GPU 用 `cpu`）、OmniParser 权重已下载、依赖已装 |
| 解析结果为空 | 调低 `box_threshold`（如 0.03）再试 |
| 首次调用慢 | 正常，模型 warm-up 约 30–40 秒，之后更快 |

## License

MIT。OmniParser 模型权重遵循其各自的 License。
