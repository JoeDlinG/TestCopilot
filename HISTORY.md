# AITestLab — 项目工作记录

> 记录从项目启动到当前的所有关键工作、里程碑和技术决策。

---

## 2026-07-04: 项目启动 — 需求定义与架构设计

### 产品需求文档 (PRD v1.0)

- 完成《AITestLab — AI 驱动硬件测试平台》产品需求文档编写
- 定义了 **9 大功能模块**：
  - F1: 设备连接与仪器控制（电源、示波器、万用表、电子负载、信号发生器）
  - F2: 多接口通信协议（SCPI、CAN/CAN FD、串口、以太网）
  - F3: 插件扩展系统（进程隔离安全沙箱）
  - F4: AI 大模型集成（OpenAI/Ollama/Anthropic，支持混元/通义千问）
  - F5: 测试用例生成（自然语言 → AI → 结构化用例 + 流程图）
  - F6: 测试执行引擎（顺序/并行/条件/循环，变量系统，钩子系统）
  - F7: 日志与结果存储（SQLite + CSV 双写）
  - F8: 自然语言查询（NL2SQL）
  - F9: 测试报告（自定义模板，PDF/HTML/Markdown 输出）
- 拆解 **58 个子任务**，规划 **12 周里程碑**（M0-M5）
- 总预估工时：约 120 人天

### 系统架构设计

- 完成 `docs/ARCHITECTURE.md`：五层分层架构（前端展示层 → API 网关层 → 业务逻辑层 → 通信协议层 → 数据持久化层）
- 完成 `docs/API_SPEC.md`：40+ REST 端点、WebSocket 协议、13 个错误码
- 完成 `docs/DB_DESIGN.md`：11 张核心数据表设计、索引策略、迁移方案
- 完成 `docs/TECH_DECISIONS.md`：9 项技术选型分析、5 条 ADR 决策记录
- 完成 `docs/USER_MANUAL.md`：详细操作使用手册

### 技术栈确定

| 层级 | 技术选型 |
|------|----------|
| 前端 | React 18 + TypeScript + Ant Design 5 + ReactFlow 11 + Zustand + Vite 5 |
| 后端 | Python + FastAPI + SQLAlchemy 2.0 (async) + SQLite (WAL 模式) |
| 通信 | PyVISA + python-can + pyserial |
| AI | OpenAI SDK + Ollama（本地）+ Anthropic |

---

## 2026-07-05 ~ 2026-07-07: 基础框架搭建 (M0)

### 后端基础框架

- FastAPI 应用入口搭建（`backend/app/main.py`）
- 核心配置模块（`backend/app/core/config.py`）：Pydantic Settings 配置管理
- 数据库连接与会话管理（`backend/app/core/database.py`）：SQLite + aiosqlite + WAL 模式
- 自定义异常处理（`backend/app/core/exceptions.py`）
- 11 张 ORM 数据模型定义（`backend/app/models/models.py`）
- Pydantic 请求/响应 Schema（`backend/app/schemas/schemas.py`、`common.py`）
- 依赖注入模块（`backend/app/api/deps.py`）

### 前端基础框架

- Vite 5 + React 18 + TypeScript 项目搭建
- Ant Design 5 UI 框架集成
- 路由配置（React Router 6）：Dashboard、Devices、TestCases、Executions、Logs、Reports、AIChat、Plugins
- 主布局组件（AppLayout）：侧栏导航 + 头部 + 内容区
- WebSocket Provider 连接管理
- Zustand 状态管理初始化
- API 服务层封装（axios）

### 设备管理与通信协议层

- 通信协议抽象接口 `CommunicationInterface` 设计与实现
- SCPI 协议适配器（基于 PyVISA + PyVISA-py）
- CAN/CAN FD 协议适配器（基于 python-can）
- 串口 RS232/RS485 协议适配器（基于 pyserial）
- 以太网 TCP/UDP Socket 协议适配器
- 设备管理器：发现/连接/状态/重连
- 设备管理 CRUD API（`/api/devices`）
- 设备管理前端页面

### AI 服务集成

- AI 服务抽象层：Provider 模式，统一 OpenAI/Ollama/Anthropic 接口
- Ollama 本地模型集成
- OpenAI 兼容云端 API 集成
- AI 模型配置管理（切换/Fallback/统计）
- AI 对话界面（聊天窗口 + 上下文管理）
- AI 配置管理 UI

### 测试用例系统

- 测试用例数据模型与 CRUD API（`/api/testcases`）
- AI 测试需求解析 Prompt 工程
- 测试用例生成服务（NL → TestCase JSON）
- 测试用例管理前端页面
- ReactFlow 流程图渲染组件
- 流程图编辑交互（拖拽/连线/编辑节点）

### 测试执行引擎

- 测试执行引擎核心：调度/状态机/超时控制
- 变量系统与作用域
- 并行执行与条件执行
- 钩子系统（setup/teardown/on_error）
- 测试执行 CRUD API（`/api/executions`）
- WebSocket 实时状态推送
- 测试执行仪表盘前端页面
- 实时执行监控页面

### 通信日志系统

- 通信日志写入服务（SQLite + CSV 双写）
- 日志查询与过滤 API（`/api/logs`）
- 日志查看器前端页面（表格/搜索/导出）
- 通信日志实时显示组件

### 测试报告系统

- 报告模板数据模型与 CRUD API（`/api/reports`）
- 报告生成引擎（Jinja2 + python-docx）
- 报告模板编辑器前端页面
- 报告生成与下载前端页面

### 插件系统

- 插件 SDK 接口规范定义
- 插件管理器：加载/生命周期/进程隔离
- 插件配置持久化
- 插件管理 API（`/api/plugins`）
- 插件管理前端页面
- Modbus RTU 示例插件（`example_plugin.py`）

---

## 2026-07-08: 调试终端功能 — 设计与规划

### 需求背景

用户需要一个多窗口通信调试终端，能够直接与已连接设备进行原始命令交互，用于调试和诊断。

### 设计文档

- 完成 `SPEC_DEBUG_TERMINAL.md`：完整的调试终端设计规范
  - 后端 WebSocket 端点 `/ws/terminal/{device_id}` 协议定义
  - 前端组件树设计：TerminalPage → DeviceSidebar + TerminalTabs + TerminalWindow
  - 消息格式契约：`terminal.command`、`terminal.response`、`terminal.unsolicited`、`terminal.error`、`terminal.ping/pong`
  - 后台 unsolicited 数据轮询机制
  - 前端状态管理方案（Zustand terminalStore）
  - 测试策略（后端 10 项 + 前端 7 项 + 集成 3 项）
- 完成 `TASKS_DEBUG_TERMINAL.md`：任务分配与执行顺序
  - Arch：4 项设计审核任务
  - BaJie（后端）：5 项后端开发任务
  - WuKong（前端）：10 项前端开发任务
  - WuJin（测试）：5 项测试任务

---

## 2026-07-09 ~ 2026-07-10: 调试终端功能 — 实现与修复

### 后端实现

- **TASK-BE-001**: 在 `DeviceService` 中新增 `send_command_raw()` 方法，不依赖 DB session
- **TASK-BE-002**: 创建终端 WebSocket 端点 `backend/app/api/terminal_ws.py`
  - WebSocket 路由: `/ws/terminal/{device_id}`
  - 连接验证、命令执行、ping/pong 心跳
  - 后台 unsolicited 数据轮询任务管理
- **TASK-BE-003**: 实现后台轮询任务 `_poll_unsolicited_data()`
- **TASK-BE-004**: 路由注册到 `main.py`

### 前端实现

- **TASK-FE-001**: 创建终端状态管理 Store（`terminalStore.ts`）
- **TASK-FE-002**: 创建 WebSocket Hook（`useTerminalWebSocket.ts`）
- **TASK-FE-003**: 创建 DeviceSidebar 组件
- **TASK-FE-004**: 创建 MessageBubble 组件
- **TASK-FE-005**: 创建 MessageList 组件（自动滚动 + 手动暂停）
- **TASK-FE-006**: 创建 CommandInput 组件（命令历史 Up/Down 导航）
- **TASK-FE-007**: 创建 TerminalWindow 组件
- **TASK-FE-008**: 创建 TerminalPage 主页面
- **TASK-FE-009**: 添加路由 `/terminal` 和导航菜单项
- **TASK-FE-010**: 补充 TypeScript 类型定义

### Bug 修复

- **Python 3.8 兼容性问题**：`asyncio.to_thread` 在 Python 3.8.10 中不可用（3.9+ API）
  - 创建 `_run_in_thread()` 兼容函数，使用 `loop.run_in_executor()` + `ThreadPoolExecutor`
  - 替换 `backend/app/communication/__init__.py` 中所有 10 处 `asyncio.to_thread()` 调用
- **串口发送阻塞问题**：`SerialInterface.send()` 使用 `read_until('\n')` 在设备不发送换行符时永久阻塞
  - 修复：发送前 `reset_input_buffer()`，先尝试 `read_until`，超时后 fallback 到 `read(1024)`

---

## 2026-07-11: 通信日志与前端时间戳增强

### 通信文件日志系统

- 创建 `backend/app/services/com_logger.py`：文件旋转日志记录器
  - 日志路径：`backend/logs/communication/<device_id>/comm_<YYYYMMDD>_<seq>.log`
  - 格式：`[ISO_timestamp] SEND/RECV/SYSTEM/ERROR: data`
  - 旋转策略：单文件超过 10MB 自动创建新序号文件（`_001` → `_002`）
  - 线程安全：使用 `threading.Lock`
- 集成日志记录到 WebSocket 命令处理流程
- 集成日志记录到设备服务 `send_command()`
- 添加系统事件日志（WebSocket 连接/断开等）

### 前端时间戳增强

- `DebugTerminal.tsx` 消息时间戳增加毫秒级显示（`HH:MM:SS.mmm` 格式）
- WebSocket 消息处理使用服务器端 ISO 8601 时间戳

### 设备连接诊断

- 发现并修复设备 `dev_90555925` 串口配置错误（`/dev/tty` → `/dev/ttyACM0`）
- 诊断串口权限问题（需要用户加入 `dialout` 组）
- 创建 Mock 设备进行端到端测试验证

---

## 2026-07-14: 项目发布准备

### Git 初始化与 GitHub 上传

- 创建 `.gitignore` 文件（排除 venv、node_modules、日志、数据库、报告文件等）
- Git 仓库初始化
- 创建 `HISTORY.md`（本文件）：完整项目工作记录
- 更新 `README.md`
- 代码推送到 GitHub: https://github.com/JoeDlinG/TestCopilot

---

## 技术架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (React 18 + TypeScript)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ 仪表盘   │ │ 设备管理  │ │ 测试用例  │ │ 执行监控      │  │
│  │ 通信日志 │ │ 测试报告  │ │ AI 对话  │ │ 调试终端      │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│                                                               │
│              WebSocket / REST API (FastAPI)                    │
├─────────────────────────────────────────────────────────────┤
│                   Backend (Python + FastAPI)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ 设备管理  │ │ AI 服务   │ │ 执行引擎  │ │ 数据/报告     │  │
│  │ 通信协议  │ │ 插件系统  │ │ 日志系统  │ │ WebSocket    │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                      数据层 (SQLite + CSV)                    │
└─────────────────────────────────────────────────────────────┘
```

## 已完成的 API 端点

| 模块 | 前缀 | 端点数量 | 状态 |
|------|------|----------|------|
| 设备管理 | `/api/devices` | 7 | ✅ |
| AI 服务 | `/api/ai` | 7 | ✅ |
| 测试用例 | `/api/testcases` | 6 | ✅ |
| 测试执行 | `/api/executions` | 6 | ✅ |
| 通信日志 | `/api/logs` | 3 | ✅ |
| 测试报告 | `/api/reports` | 5 | ✅ |
| 插件管理 | `/api/plugins` | 5 | ✅ |
| WebSocket | `/ws/*` | 3 | ✅ |

## 已完成的数据库表

| 表名 | 说明 | 状态 |
|------|------|------|
| `devices` | 设备注册信息 | ✅ |
| `test_cases` | 测试用例 | ✅ |
| `test_flows` | 流程图数据 | ✅ |
| `test_executions` | 测试执行记录 | ✅ |
| `test_step_results` | 步骤执行结果 | ✅ |
| `communication_logs` | 设备通信日志 | ✅ |
| `ai_models` | AI 模型配置 | ✅ |
| `plugins` | 插件注册信息 | ✅ |
| `test_reports` | 测试报告 | ✅ |
| `report_templates` | 报告模板 | ✅ |
| `system_config` | 系统配置 | ✅ |

## 已完成的文档

| 文档 | 说明 | 大小 |
|------|------|------|
| `docs/PRD.md` | 产品需求文档 | 32.2 KB |
| `docs/ARCHITECTURE.md` | 系统架构设计 | 27.7 KB |
| `docs/API_SPEC.md` | API 契约文档 | 23.9 KB |
| `docs/DB_DESIGN.md` | 数据库设计 | 19.1 KB |
| `docs/TECH_DECISIONS.md` | 技术决策记录 | 19.5 KB |
| `docs/USER_MANUAL.md` | 用户使用手册 | 23.0 KB |
| `SPEC_DEBUG_TERMINAL.md` | 调试终端设计规范 | 14.9 KB |
| `TASKS_DEBUG_TERMINAL.md` | 调试终端任务分配 | 15.6 KB |

---

## 下一步计划

- [ ] 端到端集成测试
- [ ] 性能优化（启动速度、大数据渲染）
- [ ] 国际化（中英文界面切换）
- [ ] 打包与安装程序制作
- [ ] 更多仪器驱动的适配与测试
- [ ] CI/CD 流水线搭建

---

> 最后更新：2026-07-14
