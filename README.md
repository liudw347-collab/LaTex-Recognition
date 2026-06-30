# TextLens (LaTex-Recognition) — Windows 桌面版

> 图文识别桌面软件：粘贴 / 拖拽 / 上传图片，AI 自动识别文字与数学公式，支持三种格式复制。
>
> 基于 Web 版 [textlens](https://github.com/llduang/textlens) 移植，使用 Python + PySide6 实现。

## 与网页版的区别

| 项目 | 网页版 | 桌面版（本项目） |
|------|--------|------------------|
| 模型 / API Key | 由部署者在 Cloudflare 环境变量配置 | **每个用户绑定自己的模型和 Key** |
| 配置方式 | 服务器端固定 | 客户端配置文件，可随时修改 |
| 单次请求超时 | 固定 | **可调整（5–600 秒）** |
| 最大重试次数 | 固定 7 次 | **可调整（1–30 次）** |
| 限流退避策略 | 固定 3s × N | **可调整基数（0.5–30 秒）** |
| 数据存储 | 服务端 D1 数据库 | **全部本地，不上传** |
| 运行环境 | 浏览器 + Cloudflare Pages | Windows 桌面（也可 Linux/macOS） |

## 主要功能

- **三种图片输入方式**：文件选择、拖拽上传、Ctrl+V 粘贴截图
- **屏幕截图工具**：快捷键 `Ctrl+Alt+S` 框选屏幕区域自动识别
- **AI 识别**：调用任意 OpenAI 兼容接口，自动重试 + 限流退避
- **三种复制格式**：
  - **Typora**：原始 Markdown + LaTeX（`$...$` / `$$...$$`）
  - **Word**：带 MathML 的 HTML，可直接粘贴到 Word 渲染公式
  - **网页输入框**：`\(...\)` / `\[...\]` 语法（适用于 ChatGPT、Notion 等）
- **结果可编辑**：识别完成后可在文本框中手动修正再复制
- **本地历史记录**：自动保存最近 N 条识别结果，可查看 / 复制 / 删除
- **多服务商预设**：智谱 GLM / OpenAI / 通义千问 / DeepSeek / Moonshot / 自定义

## 快速开始

### 方式一：直接运行源码

1. 安装 Python 3.10+：<https://www.python.org/downloads/>
2. 克隆仓库并安装依赖：
   ```powershell
   git clone https://github.com/liudw347-collab/LaTex-Recognition.git
   cd LaTex-Recognition
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. 启动：
   ```powershell
   python main.py
   ```
4. 首次启动会弹出设置对话框，**填入你自己的 API Key 和模型名称**，保存后即可使用。

### 方式二：使用打包好的 exe

前往 [Releases](../../releases) 页面下载 `TextLens-windows-x64.zip`，解压后双击 `TextLens.exe` 即可运行，无需安装 Python。

### 方式三：自行打包 exe

```powershell
# 在项目根目录，已激活 venv 的状态下：
pip install pyinstaller==6.10.0
cd build
build_exe.bat
# 输出：dist\TextLens\TextLens.exe
```

详见 [build/BUILD.md](build/BUILD.md)。

## 配置说明

所有配置保存在：

| 系统 | 路径 |
|------|------|
| Windows | `%APPDATA%\TextLens\config.json` |
| macOS | `~/Library/Application Support/TextLens/config.json` |
| Linux | `~/.config/textLens/config.json` |

历史记录保存在同目录的 `history.json`。两者均为 JSON 格式，可手动编辑 / 备份 / 迁移。

> **安全提示**：API Key 以明文形式保存在 `config.json`。如需更高安全性，建议为该文件设置 NTFS 权限仅允许当前用户访问。后续版本计划支持 Windows DPAPI 加密。

## 支持的 API 服务商预设

| 服务商 | 默认 Base URL | 默认模型 | 获取 Key |
|--------|---------------|----------|----------|
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.6v-flash` | <https://open.bigmodel.cn/usercenter/apikeys> |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` | <https://platform.openai.com/api-keys> |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-plus` | <https://dashscope.console.aliyun.com/apiKey> |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | <https://platform.deepseek.com/api_keys> |
| Moonshot | `https://api.moonshot.cn/v1` | `moonshot-v1-8k-vision-preview` | <https://platform.moonshot.cn/console/api-keys> |
| 自定义 | — | — | 手动填写 Base URL / 模型 |

> **注意**：必须使用支持图片输入的视觉模型（如 `glm-4.6v-flash`、`gpt-4o`、`qwen-vl-plus`）。纯文本模型会在请求时报 400 错误。

## 项目结构

```
LaTex-Recognition/
├── main.py                     # 入口
├── requirements.txt
├── src/
│   ├── core/                   # 业务逻辑（不依赖 Qt）
│   │   ├── config.py           # 设置 + API 预设 + 持久化
│   │   ├── recognizer.py       # AI 识别引擎（含重试 / 限流退避）
│   │   ├── image_utils.py      # 图片加载 + 压缩
│   │   ├── formats.py          # Typora / Word / Web 三种格式转换
│   │   ├── history.py          # 本地历史记录管理
│   │   └── worker.py           # Qt 线程 worker
│   └── ui/                     # PySide6 界面
│       ├── main_window.py      # 主窗口
│       ├── settings_dialog.py  # 设置对话框
│       ├── history_dialog.py   # 历史记录对话框
│       └── screenshot_overlay.py # 截图选区覆盖层
├── build/
│   ├── textlens.spec           # PyInstaller 配置
│   ├── build_exe.bat           # Windows 一键打包脚本
│   └── BUILD.md                # 详细打包说明
└── .github/
    └── workflows/
        └── build.yml           # GitHub Actions：自动构建 + 发布 Release
```

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+O` | 打开图片文件 |
| `Ctrl+V` | 粘贴剪贴板图片（或文本到结果框） |
| `Ctrl+R` | 开始 / 重新识别 |
| `Ctrl+Alt+S` | 屏幕截图（可在设置中修改） |
| `Esc` | 取消截图选区 |

## 开发说明

### 添加新的 API 服务商预设

编辑 `src/core/config.py` 中的 `API_PRESETS` 列表，添加新的 `ApiPreset` 条目即可，UI 会自动出现在下拉菜单中。

### 修改系统提示词

编辑 `src/core/recognizer.py` 中的 `SYSTEM_PROMPT` 常量。

### 调整图片压缩参数

在设置对话框中修改「图片最大宽度」，或编辑 `src/core/config.py` 中 `Settings.image_max_width` 和 `image_quality` 的默认值。

## 许可证

继承自原项目 textlens，请遵循原作者的许可证要求。

## 致谢

- 原项目：[llduang/textlens](https://github.com/llduang/textlens)
- GUI 框架：[PySide6 (Qt for Python)](https://www.qt.io/qt-for-python)
- LaTeX → MathML：[latex2mathml](https://github.com/roniemartinez/latex2mathml)
- 屏幕截图：[mss](https://github.com/BoboTiG/python-mss)
