# 📊 Antigravity Token 统计与多维度可视化分析器

<p align="center">
  <b>简体中文</b> | <a href="README_EN.md">English</a>
</p>

一个专为 **Google Antigravity**（Antigravity IDE 与 Antigravity CLI）打造的高性能、轻量级 Token 消耗统计、深度分析与现代化交互式仪表盘工具。

支持从本地会话数据库中高效提取全量模型调用元数据，提供模型分布、时间走势、年度贡献热力图、交互式 HTML 仪表盘与结构化 Markdown 报告在内的全方位数据洞察。

---

## 📸 交互式仪表盘预览

仪表盘采用单文件自包含设计，自动适配机型与屏幕比例，支持一键切换主题与工具视图：

### 1. ☀️ 暖阳米黄风格（默认）
适合日间办公与长时间数据查阅，舒缓温润不刺眼：

![暖阳米黄仪表盘预览](assets/dashboard_preview.png)

### 2. 🌙 极客暗黑风格（可选）
深邃 Slate 暗蓝灰搭配科技高光，图表色彩自适应换色并支持本地持久化记忆：

![极客暗黑仪表盘预览](assets/dashboard_preview_dark.png)

### 核心功能概览
- **顶层全局切换**：一键在 `全部工具 (All)`、`Antigravity IDE` 与 `Antigravity CLI` 之间切换，全图联动；支持双主题记忆切换。
- **对称黄金比例网格**：左侧各模型消耗环形图与右侧 GitHub 风格年度贡献热力图（52周矩阵+鼠标悬浮浮窗）紧凑并排，告别空白冗余。
- **全宽通栏走势图**：全宽横向拉长展示每日消耗，集成日期快捷胶囊、任意起止日选择器、模型下拉多选以及**实时动态求和统计卡片**。
- **深度指标明细表**：清晰展示 Windows vs WSL2 环境分布，以及各模型的上下文缓存命中率、思考 Token（Thinking Tokens）与响应耗时。

---

## ⚙️ 技术实现原理

本项目无需任何重量级外部服务，通过底层文件协议与二进制解码技术，实现秒级高可靠的数据提取与统计分析。

```
  ┌─────────────────────────────────────────────────────────────┐
  │                 1. 跨平台/跨机型自适应扫描探测                     │
  │   Windows: C:\Users\*\.gemini\antigravity-ide\conversations\*.db │
  │   WSL2:    \\wsl.localhost\<distro>\root & home\*\.gemini\*.db  │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 2. SQLite 无锁只读接入 (I/O 安全)             │
  │         URI: file:{db_path}?mode=ro&immutable=1             │
  │         - 规避 WSL2 9P/virtio-fs 虚拟文件系统锁挂死              │
  │         - 避免与正在运行的 Antigravity IDE 产生写锁冲突          │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 3. 自研原生 Protobuf 二进制解码               │
  │   解析 gen_metadata 表中的二进制 blob 数据                     │
  │   - Wire Type 0 (Varint) / Wire Type 2 (Length-delimited)   │
  │   - 零 .proto 文件编译，原生提取 Token、思考量、缓存量、模型等   │
  └──────────────────────────────┬──────────────────────────────┘
                                 │
                                 ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                 4. 多维数据聚合与单文件仪表盘渲染              │
  │   输出 Antigravity_Token_Dashboard.html 并自动唤起浏览器展示     │
  └─────────────────────────────────────────────────────────────┘
```

### 1. 扫描哪些目录（自适应跨平台定位）
工具摒弃了任何特定主机名或用户名的硬编码，无论用户使用何种电脑机型，均能全自动发现：
- **Windows 本地环境**：
  - 当前用户目录：`~/.gemini`、`~/.antigravity`
  - 全局用户驱动盘自适应扫描：枚举 `%SystemDrive%\Users` 下所有真实用户的 `.gemini/antigravity-ide/conversations/*.db` 及 CLI 相关目录。
- **WSL2 子系统环境**：
  - 自动调用 `wsl.exe -l -q`（采用 UTF-16-LE 容错解码规避 Windows 控制台乱码），枚举所有已安装的 Linux 发行版（如 Ubuntu、Debian、Arch 等）；
  - 通过 Windows 原生 UNC 网络路径穿透扫描：`\\wsl.localhost\<distro>\root\.gemini\antigravity-ide\conversations\*.db` 以及 `\\wsl.localhost\<distro>\home\<user>\.gemini\...`，无需在 WSL 内部部署额外代理。

### 2. 怎么读取的（无锁安全并发读取）
在读取 Antigravity 本地 SQLite 会话数据库时，必须保证既不干扰正在运行的 IDE，又不能被系统文件锁挂死：
- **SQLite 只读不可变 URI 模式**：
  ```python
  uri = f"file:{norm_path}?mode=ro&immutable=1"
  conn = sqlite3.connect(uri, uri=True)
  ```
- **核心原理解析**：
  - `mode=ro`：以纯只读模式打开，杜绝误写；
  - `immutable=1`：通知 SQLite 内核底层文件在连接生命周期内视为只读不可变，**SQLite 将彻底放弃尝试获取 POSIX / Windows 文件锁，并且绝不会创建或检查 `-shm`（共享内存）与 `-wal`（预写日志）临时文件**；
  - **解决痛点**：彻底根治了跨 Windows 和 WSL2 虚拟网络文件系统（9P/virtio-fs）访问时极其容易触发的 `database is locked`、`disk I/O error` 或主线程死锁假死问题。

### 3. 怎么解析的（自研纯 Python Protobuf 二进制解码）
Antigravity 会话的核心调用明细存储在数据库的 `gen_metadata` 数据表中，其记录内容以 Protocol Buffers 二进制序列化存储：
- **无需 `.proto` 定义文件的原生解码** (`proto_decoder.py`)：
  - 官方 Protobuf 结构属于内部私有格式，且引入 Google 官方 `protobuf` 编译器会带来繁重的第三方依赖；
  - 本项目内置轻量级二进制解析器，严格遵循 Google Protocol Buffers Wire Format 标准规范；
  - 基于**变长整数 (Varint)** 解码算法还原字段序号 (`field_num`) 与传输类型 (`wire_type`)；
  - 递归遍历 Wire Type 2（Length-delimited）嵌层消息，直接对二进制字节流进行结构化下钻。
- **精准提取字段**：
  - 模型标识：`gemini-3.8-flash`、`gemini-2.5-pro` 等；
  - 提示词细分：直接输入未缓存 Token (`prompt_tokens`)、系统提示词与工具调用占比；
  - 上下文缓存命中：`cached_content_token_count`，精准计算缓存节省率；
  - 模型生成输出：`candidates_token_count`，并细分提炼出思维链思考 Token (`thinking_token_count`)；
  - 耗时与时间戳：精准提取调用开始/结束毫秒级时间戳，统计平均生成延迟与历史时间序列。

### 4. 所需依赖包清单（零外部重量级依赖）
整个项目崇尚**极简、轻量、开箱即用**的设计哲学：
- **Python 运行端**：**100% 纯 Python 3.8+ 标准库**，无需 `pip install` 任何第三方包！
  - `sqlite3`：高性能本地会话数据库查询（带 URI 扩展）；
  - `json`：多维度数据汇总与前端结构序列化；
  - `os`, `sys`, `pathlib`：跨平台路径归一化处理；
  - `subprocess`：跨系统探测 WSL2 发行版；
  - `datetime`, `time`：时间戳运算与日期矩阵生成；
  - `re`：模型标识与路径文本解析；
  - `webbrowser`：分析完成后自动弹出系统浏览器呈现结果。
- **可视化仪表盘端**：
  - 单文件 HTML 原生架构（Vanilla HTML/CSS/JavaScript），无 Webpack/Vite 等 Node.js 构建负担；
  - 仅引入轻量开源 CDN `Chart.js`（用于高效绘制矢量环形图与柱状图）；
  - 完全脱机离线可用，生成的 HTML 文件直接双击或分享即可在任何浏览器渲染。

---

## 🚀 快速开始

### 1. 运行环境
- 操作系统：Windows 11 / 10、Linux 或 macOS
- Python 环境：Python 3.8 及以上（推荐 Python 3.12，支持使用 `uv` 或系统 `python`）

### 2. 执行分析与展示

在终端直接运行：

```bash
# 使用标准 Python 运行
python export_report.py

# 或使用 uv 极速运行
uv run export_report.py
```

执行后程序将全自动：
1. 探测并扫描本机所有 Windows 与 WSL2 会话库；
2. 提取全量会话与模型调用的 Token 元数据并全局去重；
3. 生成全量深度 Markdown 报告 `Antigravity_Token_Report.md`；
4. 生成交互式单文件仪表盘 `Antigravity_Token_Dashboard.html`；
5. **自动启动系统默认浏览器**，直接展现精美交互看板。

---

## 📁 项目结构

```text
Antigravity_token_stat/
├── token_analyzer.py             # 核心数据库跨环境自适应扫描与数据抽取器
├── proto_decoder.py              # 自研 Protobuf 二进制元数据递归解码模块
├── export_report.py              # 多维统计聚合引擎与 HTML/Markdown 报告生成器
├── Antigravity_Token_Dashboard.html # 生成的高性能可视化交互式仪表盘 (单文件)
├── Antigravity_Token_Report.md   # 生成的结构化分析报告
├── assets/                       # 仪表盘双主题高清预览截图
│   ├── dashboard_preview.png     # 暖阳米黄主题预览
│   └── dashboard_preview_dark.png # 极客暗黑主题预览
├── .gitignore                    # Git 忽略规则
└── README.md                     # 项目技术架构与说明文档
```

---

## 📄 许可证

[MIT License](LICENSE)

