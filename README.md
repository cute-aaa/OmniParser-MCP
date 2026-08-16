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
   │  HTTP localhost
   ▼
omniparserserver    (官方 OmniParser, FastAPI :8000, 模型常驻)
                     YOLOv9 图标检测 + Florence-2 图标描述 + EasyOCR 文本识别
```

模型只加载一次（在官方 omniparserserver 进程里），所有 MCP 客户端共享，显存只占一份。

## 快速开始

### 1. 安装并启动官方 OmniParser 后端（前置条件）

```powershell
git clone https://github.com/microsoft/OmniParser
cd OmniParser
conda create -n omni python==3.12 && conda activate omni
pip install -r requirements.txt

# 下载模型权重（国内网络先设置 $env:HF_ENDPOINT="https://hf-mirror.com"）
python setup_models.py   # 或按官方 README 使用 huggingface-cli

# 启动服务
python -m omniparserserver `
    --caption_model_name florence2 `
    --caption_model_path ../../weights/icon_caption_florence `
    --device cuda --BOX_TRESHOLD 0.05 --host 127.0.0.1 --port 8000
```

> 无 GPU 时把 `--device cuda` 换成 `--device cpu`。
> 若后端不在本机 8000 端口，用环境变量 `OMNIPARSER_API_URL` 指向它。

### 2. 安装本仓库依赖

```powershell
pip install -r requirements.txt   # 仅 mcp + httpx，轻量
```

### 3. 注册 MCP server

MCP 入口：`python <本仓库路径>\omniparser_mcp.py`

**Claude Desktop** — 编辑 `%APPDATA%\Claude\claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "omniparser": {
      "command": "python",
      "args": ["D:\\OmniParser-MCP\\omniparser_mcp.py"],
      "env": {
        "OMNIPARSER_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

**Cursor / Cline** — 本仓库已附带现成配置（使用 `${workspaceFolder}` 变量，clone 即用）：
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
| `omniparser_status` | 无 | 后端健康状态 + 未启动时的指引 |

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
| 工具报 backend not reachable | 启动官方 omniparserserver（见快速开始第 1 步） |
| 解析结果为空 | 调低 `box_threshold`（如 0.03）再试 |
| 首次调用慢 | 正常，模型 warm-up 约 30–40 秒，之后更快 |
| 需要 GPU 但显存不足 | `--device cpu` 运行后端，解析会慢但可用 |

## License

MIT（与 OmniParser 官方一致）。OmniParser 模型权重遵循其各自的 License。
