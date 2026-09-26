# AITestLab — AI 驱动硬件测试平台

AITestLab 是一款面向硬件测试工程师的 **AI 驱动测试自动化平台**。它将传统仪器控制、通信协议、AI 大模型和测试管理整合到一个统一应用中，实现从"自然语言描述测试需求"到"自动化执行测试并生成报告"的全流程闭环。

## 核心功能

| 模块 | 说明 |
|------|------|
| **设备连接** | 支持可编程电源、示波器、万用表、电子负载、信号发生器，集成 PCAN/Vector/CAN/LIN/串口/以太网工具链 |
| **多接口通信** | SCPI（PyVISA / LAN 直连 5555 / USB-TMC）、CAN/CAN FD (python-can)、串口 RS232/RS485 (pyserial)、以太网 TCP/UDP |
| **插件扩展** | Python 插件 SDK（`BaseProtocolPlugin` 基类），动态加载/卸载协议驱动、解析器、报告插件，进程隔离安全沙箱；支持自定义协议一键创建设备。**内置插件**：Mini Gateway 100、PeakCAN USB、**RIGOL 示波器**；每个插件可配 Skill（AI 用例生成指引）与手册（`backend/plugins/skills`、`backend/plugins/manuals`） |
| **AI 大模型** | 支持 OpenAI/Ollama/Anthropic 及国产模型（混元/通义千问/文心/LocalAI/vLLM 等），Provider 抽象 + Fallback 机制；前端模型管理页（API Key 配置/测试/默认切换） |
| **测试用例生成** | 文字/语音输入需求 → AI 自动生成结构化测试用例 → ReactFlow 流程图可视化编辑（支持拖拽、撤销/重做、条件分支、循环） |
| **测试执行引擎** | 顺序/并行/条件/循环执行，变量系统，钩子系统；执行页内置实时通信监控（暂停/继续/清空）、步骤状态窗口与解析数据曲线 |
| **结果解析与判定** | 每个测试步骤可配置多个解析项：数据类型（十六进制 / 二进制 / 布尔 / 十进制 / 字符串）+ 起始位 + 数据长度 + 单位（bit / byte）+ HEX 字段（报文含多个 `0x` 字段时指定用哪一个）；判定条件支持最小值 / 最大值、等于（可多选，即或运算）。解析值超出上下限即判定 **FAIL** —— 这是判定结果，不是系统或设备告警 —— 并驱动该步骤失败。解析项名称在用例内必须唯一，重复时提示重新命名。**空帧**（如 `CAN1,RPLY1,0X`，无数据 / 超时）记为 **unknown**，跳过判定、不产生数值采样点 |
| **解析数据趋势** | 解析值随步骤结果一起落库，可随时打开选择查看历史趋势曲线（不单独建趋势表）；**每一步的每条应答都是一个采样点**，重复下发 N 次的步骤能得到 N 个点的完整曲线（不再只剩最后一个点）；用例执行时可勾选需要实时显示的曲线，支持大屏模式 |
| **仪表盘大屏** | 仪表盘一键进入大屏模式：超大字号、深色投屏配色、实时时钟、5/10/30/60 秒自动刷新；无权限控制，可直接投到产线/实验室屏幕 |
| **自定义仪表盘** | 自由拼装看板：`react-grid-layout` 栅格（拖拽移动/缩放）+ 编辑/锁定 + 组件库 + 多仪表盘（新建/复制/设为默认/导入/导出 JSON）+ 大屏模式。内置 **7 种 Widget**：**解析数值卡片**（最新值 + PASS/FAIL 判定徽标，越界变红）、**趋势曲线**（FAIL 点标红，可加参考上下限）、**判定结果汇总**（PASS/FAIL/空帧统计 + 分字段表格 + 最近 FAIL 明细 —— FAIL 是判定结果，非告警）、设备状态、执行统计、通信日志、文本备注。仪表盘只存布局与数据源引用，数值运行时从 `parsed_results` 现算（`GET /api/dashboards/snapshot` 一次拉齐全部 Widget） |
| **通信日志** | SQLite + CSV 双写，通信数据实时记录，keyset 分页查询，CSV 批量导出 |
| **自然语言查询** | 文字/语音自然语言查询测试数据（NL2SQL），查询历史管理 |
| **测试报告** | 自定义字段模板，支持 PDF/HTML/Markdown 输出，AI 生成测试结论 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 18 + TypeScript |
| UI 组件库 | Ant Design 5 |
| 流程图编辑器 | ReactFlow 11 |
| 状态管理 | Zustand + React Query |
| 构建工具 | Vite 5 |
| 后端框架 | Python 3.11+ + FastAPI |
| ORM | SQLAlchemy 2.0 (异步) |
| 数据库 | SQLite (aiosqlite, WAL 模式) |
| SCPI/VISA | PyVISA + PyVISA-py |
| CAN 总线 | python-can |
| 串口通信 | pyserial + pyserial-asyncio |
| AI 集成 | httpx + openai SDK |
| 语音识别 | OpenAI Whisper |
| 报告生成 | Jinja2 + WeasyPrint + python-docx |

## 快速开始

### 环境要求

- **Python** >= 3.11
- **Node.js** >= 18
- **操作系统**: Linux / macOS / Windows

### 1. 启动后端

```bash
cd backend

# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
python run.py
```

后端服务启动于 **http://localhost:8000**，API 交互文档 **http://localhost:8000/docs**

### 2. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端启动于 **http://localhost:5173**

### 3. 配置 AI 模型（可选）

在 `backend/` 目录下创建 `.env` 文件：

```env
# OpenAI 兼容 API
OPENAI_API_KEY=sk-your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1

# 使用 Ollama 本地模型时无需设置 API Key
DEFAULT_AI_PROVIDER=ollama
```

> 除环境变量外，也可在前端「模型配置」页面可视化地添加/编辑/测试 AI 模型（支持 OpenAI、Anthropic、Ollama、LocalAI、vLLM、腾讯混元、阿里通义千问、百度文心一言及任意 OpenAI 兼容端点），并设置默认模型供 AI 助手使用。

## 项目结构

```
AITestLab/
├── frontend/                          # React 前端
│   ├── src/
│   │   ├── components/                # 通用 UI 组件
│   │   │   ├── Layout.tsx             # 主布局（侧栏 + 头部 + 内容区）
│   │   │   ├── WebSocketProvider.tsx   # WebSocket 连接管理
│   │   │   ├── ResultParserConfig.tsx  # 测试结果解析配置界面（数据类型/起始位/长度/单位/判定条件）
│   │   │   ├── ParsedTrendChart.tsx    # 解析数据趋势曲线（支持大屏模式）
│   │   │   └── dashboard/             # 自定义仪表盘 Widget 库
│   │   │       ├── registry.tsx       #   组件注册表（类型/尺寸/默认配置）
│   │   │       ├── widgets.tsx        #   7 种 Widget 实现
│   │   │       └── WidgetConfigDrawer.tsx # 组件配置抽屉
│   │   ├── pages/                     # 页面组件
│   │   │   ├── DashboardPage.tsx      # 主页仪表盘
│   │   │   ├── CustomDashboard.tsx    # 自定义仪表盘（栅格拼装 / 编辑锁定 / 大屏）
│   │   │   ├── DevicesPage.tsx        # 设备管理
│   │   │   ├── TestCasesPage.tsx      # 测试用例管理
│   │   │   ├── TestFlowEditor.tsx  # 流程图编辑器（拖拽/撤销/重做/代码生成）
│   │   │   ├── ExecutionsPage.tsx     # 测试执行
│   │   │   ├── ExecutionMonitorPage.tsx # 实时执行监控
│   │   │   ├── LogsPage.tsx           # 通信日志查询
│   │   │   ├── ReportsPage.tsx        # 报告管理
│   │   │   ├── ModelConfig.tsx        # AI 模型配置管理
│   │   │   └── Plugins.tsx            # 插件管理
│   │   ├── services/                  # API 调用服务
│   │   ├── stores/                    # Zustand 状态管理
│   │   ├── types/                     # TypeScript 类型定义
│   │   └── App.tsx                    # 路由配置
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
├── backend/                           # Python 后端
│   ├── app/
│   │   ├── api/                       # API 路由层
│   │   │   ├── devices.py             # /api/devices 设备管理
│   │   │   ├── testcases.py           # /api/testcases 测试用例
│   │   │   ├── executions.py          # /api/executions 测试执行
│   │   │   ├── ai.py                  # /api/ai AI 模型与用例生成
│   │   │   ├── logs.py                # /api/logs 通信日志
│   │   │   ├── reports.py             # /api/reports 报告与模板
│   │   │   ├── plugins.py             # /api/plugins 插件管理
│   │   │   ├── websocket.py           # WebSocket 实时推送
│   │   │   └── deps.py                # 依赖注入
│   │   ├── core/                      # 核心配置
│   │   │   ├── config.py              # 配置管理 (Pydantic Settings)
│   │   │   ├── database.py            # 数据库连接与会话
│   │   │   └── exceptions.py          # 自定义异常
│   │   ├── models/                    # SQLAlchemy ORM 模型 (11 张表)
│   │   │   └── models.py              # 所有数据模型
│   │   ├── schemas/                   # Pydantic 请求/响应 Schema
│   │   │   ├── schemas.py             # 业务 Schema
│   │   │   └── common.py              # 通用分页/错误响应
│   │   ├── services/                  # 业务逻辑层
│   │   │   ├── response_parser.py     # 结果解析与判定引擎（执行与代码生成共用）
│   │   │   ├── device_service.py      # 设备连接/状态管理
│   │   │   ├── testgen_service.py     # AI 测试用例生成
│   │   │   ├── execution_service.py   # 测试执行引擎
│   │   │   ├── ai_service.py          # AI 模型调用抽象
│   │   │   ├── log_service.py         # 日志记录与查询
│   │   │   ├── report_service.py      # 报告生成
│   │   │   └── plugin_service.py      # 插件管理
│   │   ├── communication/             # 通信协议实现
│   │   │   └── __init__.py            # SCPI/CAN/Serial/Ethernet 驱动
│   │   ├── ai/                        # AI 引擎抽象层
│   │   │   └── __init__.py            # OpenAI/Ollama/Anthropic Provider
│   │   └── main.py                    # FastAPI 应用入口
│   ├── plugins/                       # 用户插件目录
│   │   ├── __init__.py
│   │   ├── example_plugin.py          # Modbus RTU 示例插件
│   │   └── mini_gateway100_plugin.py  # Mini Gateway 100 协议插件
│   ├── requirements.txt
│   └── run.py
│
├── docs/                              # 项目文档
│   ├── PRD.md                         # 产品需求文档
│   ├── ARCHITECTURE.md                # 系统架构设计
│   ├── API_SPEC.md                    # API 契约文档 (40+ 端点)
│   ├── DB_DESIGN.md                   # 数据库设计 (11 张表)
│   ├── TECH_DECISIONS.md             # 技术决策 (9 项选型 + 5 条 ADR)
│   ├── PEAKCAN_PLUGIN.md             # PeakCAN USB 插件说明
│   ├── RIGOL_OSCILLOSCOPE_PLUGIN.md  # RIGOL 示波器插件说明
│   ├── scpi/                         # SCPI-1999 官方规范 PDF + 速查
│   └── rigol/                        # RIGOL 示波器官方编程手册 PDF
│
└── README.md                          # 本文件
```

## API 概览

| 模块 | 前缀 | 主要端点 |
|------|------|----------|
| 设备管理 | `/api/devices` | CRUD、连接/断开、发送命令、可用设备发现 |
| AI | `/api/ai` | 模型配置 CRUD、对话补全、用例生成、语音转写、NL 查询 |
| 测试用例 | `/api/testcases` | 用例 CRUD、流程图同步、解析预览 `parse-preview`、解析历史趋势 `parsed-trend`、代码生成 `generate-code` |
| 测试执行 | `/api/executions` | 创建执行、启动/停止、状态查询、步骤结果 |
| 通信日志 | `/api/logs` | 日志查询（分页/筛选）、CSV 导出 |
| 测试报告 | `/api/reports` | 报告生成、模板 CRUD、报告下载 |
| 插件 | `/api/plugins` | 插件列表、安装（含已发现插件扫描）、启用/禁用、按模板一键创建设备 |

**WebSocket 端点**:
- `ws://localhost:8000/ws/executions/{id}` — 测试执行实时监控
- `ws://localhost:8000/ws/devices/{id}` — 设备实时数据推送

## 数据库设计

系统包含 **11 张核心数据表**：

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `devices` | 设备注册信息 | 类型、协议、连接参数、状态 |
| `test_cases` | 测试用例 | 名称、需求描述、参数配置、关联流程图 |
| `test_flows` | 流程图数据 | ReactFlow nodes/edges JSON |
| `test_executions` | 测试执行记录 | 状态、开始/结束时间、变量上下文 |
| `test_step_results` | 步骤执行结果 | 步骤序号、输入/输出值、耗时、状态、解析判定结果（`parsed_results` JSON） |
| `communication_logs` | 设备通信日志 | 原始命令、响应、时间戳、方向 |
| `ai_models` | AI 模型配置 | Provider 类型、API Key、模型名 |
| `plugins` | 插件注册信息 | 名称、版本、类型、状态、配置 |
| `test_reports` | 测试报告 | 模板引用、执行引用、输出路径 |
| `report_templates` | 报告模板 | 字段定义 JSON、输出格式 |
| `system_config` | 系统配置 | 键值对存储 |

详细设计见 [docs/DB_DESIGN.md](docs/DB_DESIGN.md)。

## 插件开发

AITestLab 支持通过 Python 插件扩展自定义通信协议。插件继承 `BaseProtocolPlugin` 基类，并实现 `connect` / `disconnect` / `send` 等接口；设备服务在连接 `protocol` 为非标准协议（如 `mini_gateway100`）时，会自动加载并启用对应的插件实例作为通信后端。

开发一个自定义协议插件只需 3 步：

### 1. 继承基类

```python
from app.services.plugin_service import BaseProtocolPlugin

class MyProtocolPlugin(BaseProtocolPlugin):
    plugin_name = "My Protocol"
    protocol_name = "my_protocol"   # 设备 protocol 字段使用该值
    version = "1.0.0"

    async def connect(self, config: dict) -> bool:
        # 使用 config 建立连接（串口/以太网/...）
        return True

    async def disconnect(self) -> bool:
        return True

    async def send(self, data) -> any:
        # data 可为原始字符串或 {"command": "...", "parameters": [...]}
        # 返回解析后的响应
        return ""

    # 可选：为 UI 提供连接配置 schema / 设备模板 / 命令帮助
    def get_config_schema(self) -> dict: ...
    def get_device_template(self) -> dict: ...
    def get_commands(self) -> list: ...
```

### 2. 放入插件目录

将 `.py` 文件放入 `backend/plugins/` 目录。重启后端后，可在「插件管理 → 已发现的插件」中一键安装，启用后通过「添加设备」按钮按插件模板自动创建设备。

### 3. 通过 API 安装

```bash
curl -X POST http://localhost:8000/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"name": "My Protocol", "version": "1.0.0", "protocol_type": "my_protocol", "file_path": "plugins/my_protocol.py", "module_name": "my_protocol", "class_name": "MyProtocolPlugin"}'
```

### 内置插件示例

- `backend/plugins/example_plugin.py` — Modbus RTU 示例插件
- `backend/plugins/mini_gateway100_plugin.py` — **Mini Gateway 100** 协议插件，实现手册定义的 `@<ID>_<CMD>=<PARAMS>;` 命令集（HELLO/SYSID/PSUV/PSDV/ETH/RTC/STORAGE/SETDIG/CLRDIG/GETDIG/CALBRT/GETVOLT/SETVOLT/OPEN/CLOSE/CONFIG/TSTRT/TSTOP/MSGTX/MSGRX 共 22 条）。板卡 ID 可配置（默认 `11`），USB-C 主机口波特率默认 `115200` 可选。PSU RS-232 电源开关命令按需求暂未实现。

参考 `backend/plugins/example_plugin.py` 与 `backend/plugins/mini_gateway100_plugin.py`。

## 配置说明

### 环境变量

在 `backend/.env` 中配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./aitestlab.db` | 数据库连接 |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | 跨域白名单 |
| `DEFAULT_AI_PROVIDER` | `openai` | 默认 AI Provider |
| `OPENAI_API_KEY` | — | OpenAI API Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI 兼容 API 地址 |
| `WHISPER_MODEL` | `base` | Whisper 语音模型 |
| `VISA_TIMEOUT` | `5000` | VISA 超时 (ms) |
| `CAN_BITRATE` | `500000` | CAN 默认波特率 |
| `SERIAL_BAUDRATE` | `115200` | 串口默认波特率 |

### 通信协议驱动

系统内置以下通信协议驱动，无需额外配置：

| 协议 | 依赖 | 支持接口 |
|------|------|----------|
| SCPI/VISA | PyVISA + PyVISA-py | USB、GPIB、以太网 |
| CAN/CAN FD | python-can | PCAN、Vector、SocketCAN、Kvaser |
| 串口 | pyserial | RS232、RS485 |
| 以太网 | asyncio | TCP、UDP |

## 文档索引

| 文档 | 说明 |
|------|------|
| [PRD.md](docs/PRD.md) | 产品需求文档：9 大功能模块、58 个子任务、12 周里程碑 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构设计：五层分层、前端组件树、后端模块划分、数据流 |
| [API_SPEC.md](docs/API_SPEC.md) | API 契约：40+ 端点、WebSocket 协议、13 个错误码 |
| [DB_DESIGN.md](docs/DB_DESIGN.md) | 数据库设计：11 张表、字段定义、索引策略、迁移方案 |
| [TECH_DECISIONS.md](docs/TECH_DECISIONS.md) | 技术决策：9 项选型分析、5 条 ADR、性能目标、安全设计 |
| [USER_MANUAL.md](docs/USER_MANUAL.md) | 使用手册：详细操作指南 |
| [CUSTOM_DASHBOARD_IDEAS.md](docs/CUSTOM_DASHBOARD_IDEAS.md) | 自定义仪表盘：设计草案与头脑风暴（待办功能） |
| [PEAKCAN_PLUGIN.md](docs/PEAKCAN_PLUGIN.md) | PeakCAN USB 插件：驱动安装、配置参数、CAN/CAN FD 通信指令 |
| [RIGOL_OSCILLOSCOPE_PLUGIN.md](docs/RIGOL_OSCILLOSCOPE_PLUGIN.md) | RIGOL 示波器插件：SCPI 远程控制（LAN/USB-TMC/VISA）、波形读取、故障排查 |
| [scpi/](docs/scpi/) | **SCPI 协议资料**：SCPI-1999 官方规范 PDF + 语法/命令树/状态模型速查 |
| [rigol/](docs/rigol/) | **RIGOL 示波器官方编程手册** PDF（DS1000Z-E、MSO5000） |

## License

MIT
