# AITestLab — AI 驱动硬件测试平台

AITestLab 是一款面向硬件测试工程师的 **AI 驱动测试自动化平台**。它将传统仪器控制、通信协议、AI 大模型和测试管理整合到一个统一应用中，实现从"自然语言描述测试需求"到"自动化执行测试并生成报告"的全流程闭环。

## 核心功能

| 模块 | 说明 |
|------|------|
| **设备连接** | 支持可编程电源、示波器、万用表、电子负载、信号发生器，集成 PCAN/Vector/CAN/LIN/串口/以太网工具链 |
| **多接口通信** | SCPI (PyVISA)、CAN/CAN FD (python-can)、串口 RS232/RS485 (pyserial)、以太网 TCP/UDP |
| **插件扩展** | Python 插件 SDK，动态加载/卸载协议驱动、解析器、报告插件，进程隔离安全沙箱 |
| **AI 大模型** | 支持 OpenAI/Ollama/Anthropic 及国产模型（混元/通义千问等），Provider 抽象 + Fallback 机制 |
| **测试用例生成** | 文字/语音输入需求 → AI 自动生成结构化测试用例 → ReactFlow 流程图可视化编辑 |
| **测试执行引擎** | 顺序/并行/条件/循环执行，变量系统，钩子系统，WebSocket 实时仪表盘监控 |
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

## 项目结构

```
AITestLab/
├── frontend/                          # React 前端
│   ├── src/
│   │   ├── components/                # 通用 UI 组件
│   │   │   ├── Layout.tsx             # 主布局（侧栏 + 头部 + 内容区）
│   │   │   └── WebSocketProvider.tsx   # WebSocket 连接管理
│   │   ├── pages/                     # 页面组件
│   │   │   ├── DashboardPage.tsx      # 主页仪表盘
│   │   │   ├── DevicesPage.tsx        # 设备管理
│   │   │   ├── TestCasesPage.tsx      # 测试用例管理
│   │   │   ├── TestCaseFlowPage.tsx   # 流程图编辑器
│   │   │   ├── ExecutionsPage.tsx     # 测试执行
│   │   │   ├── ExecutionMonitorPage.tsx # 实时执行监控
│   │   │   ├── LogsPage.tsx           # 通信日志查询
│   │   │   ├── ReportsPage.tsx        # 报告管理
│   │   │   ├── AIConfigPage.tsx       # AI 模型配置
│   │   │   └── PluginsPage.tsx        # 插件管理
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
│   │   └── example_plugin.py          # Modbus RTU 示例插件
│   ├── requirements.txt
│   └── run.py
│
├── docs/                              # 项目文档
│   ├── PRD.md                         # 产品需求文档
│   ├── ARCHITECTURE.md                # 系统架构设计
│   ├── API_SPEC.md                    # API 契约文档 (40+ 端点)
│   ├── DB_DESIGN.md                   # 数据库设计 (11 张表)
│   └── TECH_DECISIONS.md             # 技术决策 (9 项选型 + 5 条 ADR)
│
└── README.md                          # 本文件
```

## API 概览

| 模块 | 前缀 | 主要端点 |
|------|------|----------|
| 设备管理 | `/api/devices` | CRUD、连接/断开、发送命令、可用设备发现 |
| AI | `/api/ai` | 模型配置 CRUD、对话补全、用例生成、语音转写、NL 查询 |
| 测试用例 | `/api/testcases` | 用例 CRUD、流程图同步 |
| 测试执行 | `/api/executions` | 创建执行、启动/停止、状态查询、步骤结果 |
| 通信日志 | `/api/logs` | 日志查询（分页/筛选）、CSV 导出 |
| 测试报告 | `/api/reports` | 报告生成、模板 CRUD、报告下载 |
| 插件 | `/api/plugins` | 插件列表、安装、启用/禁用、配置 |

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
| `test_step_results` | 步骤执行结果 | 步骤序号、输入/输出值、耗时、状态 |
| `communication_logs` | 设备通信日志 | 原始命令、响应、时间戳、方向 |
| `ai_models` | AI 模型配置 | Provider 类型、API Key、模型名 |
| `plugins` | 插件注册信息 | 名称、版本、类型、状态、配置 |
| `test_reports` | 测试报告 | 模板引用、执行引用、输出路径 |
| `report_templates` | 报告模板 | 字段定义 JSON、输出格式 |
| `system_config` | 系统配置 | 键值对存储 |

详细设计见 [docs/DB_DESIGN.md](docs/DB_DESIGN.md)。

## 插件开发

AITestLab 支持通过 Python 插件扩展通信协议。开发一个自定义协议插件只需 3 步：

### 1. 继承基类

```python
from app.communication import CommunicationInterface

class MyProtocolPlugin(CommunicationInterface):
    name = "my_protocol"
    description = "自定义协议驱动"

    async def connect(self) -> None:
        # 建立连接逻辑
        pass

    async def disconnect(self) -> None:
        # 断开连接逻辑
        pass

    async def send(self, command: str) -> None:
        # 发送命令逻辑
        pass

    async def receive(self) -> str:
        # 接收响应逻辑
        return ""
```

### 2. 放入插件目录

将 `.py` 文件放入 `backend/plugins/` 目录。

### 3. 通过 API 安装

```bash
curl -X POST http://localhost:8000/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"plugin_path": "plugins/my_protocol.py"}'
```

参考 `backend/plugins/example_plugin.py` (Modbus RTU 示例)。

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

## License

MIT
