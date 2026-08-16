# OmniParser MCP Server

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

### 2. 启动后端（二选一）

**方式 A — 手动启动（推荐，后端生命周期自己掌控）**

```powershell
# 从本仓库运行；自动探测 OmniParser 目录，或显式指定：
pwsh -File start_backend.ps1 -OmniParserHome D:\OmniParser -Device cuda
```

**方式 B — MCP 自动启动**

在 MCP 客户端配置的 `env` 里加上 `OMNIPARSER_HOME`（见下节），后端未运行时会自动拉起并等待就绪
（首次约 30–60 秒加载模型），无需手动操作。

### 3. 安装本仓库依赖并注册 MCP

```powershell
pip install -r requirements.txt   # 仅 mcp + httpx
```

**Claude Desktop** — 编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

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
python test_mcp.py
```

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
