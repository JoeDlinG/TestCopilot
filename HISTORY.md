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

## 2026-07-20: 自定义协议插件（Mini Gateway 100）与 AI 模型配置前端

### Mini Gateway 100 协议插件

- 新增 `backend/plugins/mini_gateway100_plugin.py`，实现手册定义的 `@<ID>_<CMD>=<PARAMS>;` 命令协议，覆盖 22 条命令（HELLO / SYSID / PSUV / PSUC / PSDV / PSDC / ETH / RTC / STORAGE / SETDIG / CLRDIG / GETDIG / CALBRT / GETVOLT / SETVOLT / OPEN / CLOSE / CONFIG / TSTRT / TSTOP / MSGTX / MSGRX）
- 响应解析支持 `[时间戳,size]#<ID>_<CMD>=<RESULT>;` 格式
- 按用户确认实现：
  - **PSU RS-232 电源开关命令**：暂跳过（无应用场景）
  - **USB-C 主机口波特率**：默认 `115200`，可选 9600–921600
  - **板卡 ID**：可配置，默认 `11`
- 提供 `get_config_schema()`（连接配置 UI schema）、`get_device_template()`（设备模板）、`get_commands()`（命令帮助）供前端使用

### 插件系统增强

- 补齐缺失的 `BaseProtocolPlugin` 基类（`backend/app/services/plugin_service.py`），原被 `example_plugin.py` 引用但未定义；新增 `get_plugin_class_by_protocol()` 辅助方法
- `device_service.connect()` 路由：当设备 `protocol` 为非标准协议时，自动加载并启用对应插件实例作为通信后端（`send_command` 直接复用）
- 新增后端端点 `POST /api/plugins/{id}/add-device`：按插件 `get_device_template()` 一键创建设备

### 前端插件管理增强

- `Plugins.tsx` 新增「已发现的插件」卡片：自动扫描 `plugins/` 目录，支持一键安装
- 插件列表新增「添加设备」按钮（调用 add-device 端点），启用后方可使用
- `types/index.ts`：`INTERFACE_TYPES` 增加 `mini_gateway100`，`DEVICE_TYPES` 增加 `gateway`

### AI 模型配置前端

- 后端原本已有 `AIModelConfig` 模型与 `ProviderFactory`（OpenAI/Anthropic/Ollama/混元/通义/文心等），但缺前端管理页，导致 AI 助手无法配置使用
- 新增 `frontend/src/pages/ModelConfig.tsx`：模型列表（供应商/模型名/Base URL/状态/默认标记）、添加/编辑（名称、供应商、模型名、API Key、Base URL、是否默认、高级参数）、测试连接、设为默认、删除
- `App.tsx` + `AppLayout.tsx`：新增「模型配置」路由与侧边导航
- `services/api.ts`：新增 `updateModel` / `deleteModel` / `testModel` 方法
- `types/index.ts`：对齐 `AIModel` 类型，新增 `PROVIDERS` 供应商元数据
- `AIChat.tsx`：无模型时按钮直达「模型配置」页

### 验证

- 后端 `py_compile` 通过；插件加载、命令构建、响应解析、基类导入验证通过
- 前端 `tsc --noEmit` 类型检查通过

---

## 2026-07-20 (下午): AI 供应商扩展、模型对话窗口、AI 助手无响应修复

### 新增 AI 供应商：DeepSeek、MiniMax
- 后端 `app/ai/__init__.py` 的 `ProviderFactory.PROVIDER_MAP` 新增 `deepseek`、`minimax`（均基于 OpenAI 兼容协议 `OpenAIProvider`）
- `app/models/models.py` 的 `ModelProvider` 枚举补充 `DEEPSEEK`、`MINIMAX`
- 前端 `types/index.ts` 的 `PROVIDERS` 补充 DeepSeek（`https://api.deepseek.com/v1`，模型 `deepseek-chat`/`deepseek-reasoner`）与 MiniMax（`https://api.minimax.chat/v1`，模型 `abab6.5-chat`/`MiniMax-Text-01`）

### 模型配置页新增「对话测试」窗口
- `ModelConfig.tsx` 每个模型行新增「对话测试」按钮，打开 Drawer 聊天窗口，直接调用 `aiAPI.chat` 与该模型对话验证
- 对话失败时在窗口内联显示后端返回的真实错误原因

### 修复 AI 助手发送对话无响应
根因分析（通过 mock provider 复现与单测定位）：
- **根因 1**：`AIModelConfigCreate` schema 缺失 `is_default` 字段，前端创建时勾选「设为默认」被后端忽略
- **根因 2**：`ai_service.test_model` 测试成功后未将 `status` 重置为 `active`；一旦某次测试失败 `status` 置为 `error`，AI 助手 `loadModels` 仅自动选中 `is_default` 或 `status==='active'` 的模型 → 该模型不再被选中 → 发送按钮禁用 → 表现为「发送无响应」
修复：
- `AIModelConfigCreate` 增加 `is_default`；`configure_model` 创建时若 `is_default` 为真则互斥取消其他模型默认
- `test_model` 成功时将 `status` 置为 `active`（失败置 `error`）
- AI 助手自动选择策略放宽：优先 `is_default` → 其次 `status==='active'` → 否则首个模型，确保发送按钮可用
- 对话失败时除错误提示外，在对话流中内联显示错误并给出真实原因，保证用户始终有可见反馈

### 验证
- 后端单测（mock provider）覆盖：创建默认/互斥、测试成功状态、对话成功、测试失败路径，均符合预期
- 前端 `tsc --noEmit` 通过

### 项目看板
- 新增 `KANBAN.md`：同步项目进展、计划与看板（待办/进行中/已完成），与 `HISTORY.md`、`README.md` 配套

---

## 2026-07-25: 修复 AI 模型「连接失败」（JoeAI / DeepSeek）

### 问题现象
用户新增模型 `JoeAI`（供应商选 `custom`，模型名 `Deepseek`，填写了有效 API Key），但「测试连接」始终失败，无明确原因。

### 根因定位（通过真实 API 探测 + 代码走查）
1. **后端默认 Base URL 缺失（主因）**：`OpenAIProvider.__init__` 在 `base_url` 为空时硬编码回退到 `https://api.openai.com/v1`。而 `custom` 供应商的 JoeAI 存储 `base_url=None`，导致请求被发往 **OpenAI** 而非 DeepSeek —— 本环境访问 OpenAI 超时，表现为「连接失败」。供应商专属默认地址（如 DeepSeek `https://api.deepseek.com/v1`）此前仅存在于前端 `PROVIDERS`，后端并未使用。
2. **模型名已废弃**：即便指向 DeepSeek，模型名 `Deepseek`/`deepseek-chat` 已被新版 API 弃用，需使用 `deepseek-v4-pro` / `deepseek-v4-flash`。
3. **测试错误被吞掉**：`AIProvider.test_connection` 捕获所有异常仅返回 `False`，真实原因（401 无效 Key / 400 模型名错误 / 主机不可达）从不返回，用户只见「失败」。
4. **`custom` 供应商无 Base URL 校验**：允许保存 `custom` + 空 URL，造成静默回退。
5. **无会话首条消息崩溃**：`chat_history.session_id` 为 `NOT NULL`，而前端首条消息未带 `session_id`，导致第一次对话即 `IntegrityError`。
6. **更新接口无法修正供应商/模型名**：`AIModelConfigUpdate` 缺少 `provider`/`model_name` 字段，错的配置无法通过 API/UI 改回。

### 修复
- 后端 `ProviderFactory` 新增 `DEFAULT_BASE_URLS`，按供应商解析默认地址；`custom` 为 `None`（必须由用户填写）。JoeAI 现正确指向 `https://api.deepseek.com/v1`。
- `AIModelConfigUpdate` 增加 `provider`、`model_name` 字段。
- `test_model` 返回真实错误：`{"status": "ok"/"failed", "error": <真实原因>}`；`OpenAI/AnthropicProvider` 在 HTTP 错误时把响应体一并抛出。
- 后端 `configure_model`/`update_model` 校验：`custom` 供应商若缺 `base_url` 直接报错。
- `ai_service.chat` 在 `session_id` 为空时自动生成，既满足 `NOT NULL` 又能让前端拿到会话 ID 续聊。
- 前端：`handleTest` 展示后端返回的真实错误；`custom` 供应商保存前强制校验 `base_url`；`PROVIDERS.deepseek` 提示更新为 `deepseek-v4-pro / deepseek-v4-flash`。

### 验证（使用用户真实 API Key 端到端）
- `POST /api/ai/models/model_b9be7020/test` → `{"status":"ok","error":null}`，JoeAI 连接成功。
- `POST /api/ai/chat`（JoeAI）→ DeepSeek 正常回复（如「你好！有什么我可以帮你的吗？😊」）。
- 诊断回归：另一 `deepseek` 模型（Key 无效）测试 → 清晰返回 `HTTP 401: ... Your api key: x is invalid`，证明错误可定位。
- 前端 `tsc --noEmit` 通过。

---

## 2026-07-25: 修复插件「Plugin class not found」+ 插件手册/Skill + AI 助手 Skill 导入

### 问题现象
插件管理中安装 Mini Gateway 100 后，点击「添加设备」报错 `Plugin class not found`。

### 根因定位（影响所有插件的系统性 bug）
1. **返回值语义错误（主因）**：`PluginService._load_plugin_module()` 名为加载"模块"，实际返回的是**类**；而两个调用方（`api/plugins.py` 的 `add-device`、`get_plugin_class_by_protocol`）把返回值当模块再 `getattr(module, class_name)` → 永远得到 `None` → 所有插件的「添加设备」和自定义协议设备连接必然报 "class not found"。
2. **相对路径脆弱**：DB 存储 `file_path='./plugins/xxx.py'`，进程工作目录一变即 `FileNotFoundError`。
3. **模块导入不当**：`device_service.py` 中 `from app.services import plugin_service` 导入的是**模块**而非服务实例，调用 `.get_plugin_class_by_protocol()` 直接 `AttributeError`。
4. **插件设备连接丢配置**：`_get_connect_config` 仅对 `usb` 协议合并设备存储配置，插件设备的 `port/baudrate/board_id` 被丢弃 → 连接报 "Missing 'port'"。
5. **发现扫描属性名错误**：`list_discovered_plugins` 读取 `plugin_version`，而插件定义的是 `version`；且 `hasattr(attr,"protocol_name")` 会把基类 `BaseProtocolPlugin` 也列出来。

### 修复（通用性，不针对单个插件）
- 新增 `load_plugin_class()`：4 级类解析回退（精确类名 → 大小写不敏感 → 模块内唯一插件子类 → 按 protocol 匹配），失败时报错附可用类列表。
- 新增 `_resolve_plugin_file()`：4 级路径解析（原路径 → backend 根相对 → PLUGIN_DIR/文件名 → PLUGIN_DIR/module_name.py）。
- `_exec_module()` 保证 backend 根在 `sys.path`，插件可在任意 CWD 下导入 `app.*`。
- `install/enable/get_plugin_class_by_protocol/add-device` 全部改走 `load_plugin_class()`。
- `device_service`: 修正插件服务导入；`_get_connect_config` 对所有协议合并设备存储配置。
- `list_discovered_plugins` 只列 `BaseProtocolPlugin` 子类、正确读取 `version`。

### 插件手册与 Skill 体系（新增）
- 目录约定：`backend/plugins/manuals/<protocol>.md`（使用手册）、`backend/plugins/skills/<protocol>_skill.md`（AI 测试用例生成 Skill，含 frontmatter：name/protocol/keywords）。
- 已生成：Mini Gateway 100（全命令参考、CAN 流程、边界/错误场景模板）、Modbus RTU。
- 新 API：`GET /api/plugins/skills`（列表）、`GET /api/plugins/skills/{protocol}`（skill+手册全文）。

### AI 助手集成插件 Skill（新增）
- `AIChatRequest`/`TestCaseGenerateRequest` 新增 `skill_protocols` 字段。
- `ai_service`：`_build_skill_context()` 将 skill+手册注入 system prompt；支持**显式导入** + **关键词自动检测**（对话中提到 "Mini Gateway 100"/"mg100"/"modbus" 等即自动附加对应知识）。
- 前端 AIChat 页新增「导入插件 Skill」多选器，对话与生成用例均携带所选 skill。

### 验证（真实硬件端到端）
- 单元测试 10 项全过：类解析 4 级回退、路径回退、FileNotFoundError、发现扫描、skill 列表/内容/关键词匹配。
- API 实测：`add-device` 成功创建设备（原报错点）→ `connect` 成功打开 /dev/ttyACM0 → `@11_HELLO;` 真实硬件应答 `2,11,12`（30ms）→ `disconnect` 正常。
- AI 实测（DeepSeek）：显式导入 skill 后正确识别设备；**未导入**仅在对话中提及 "Mini Gateway 100"，AI 自动读取手册并准确回答 `@11_GETVOLT=3;`；生成用例严格遵循协议（先 HELLO/SYSID 握手、R1/R96 边界）。
- 前端 `tsc --noEmit` 通过。

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
| 插件管理 | `/api/plugins` | 6 | ✅ |
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

## 2026-07-26: Bug 修复 — 重置软件、API Key 保存、模型测试 400

### 重置软件进程未完全关闭
- **根因**：`restart_helper.py` 只 `pkill -f 'run.py'` 杀 reloader 父进程，`uvicorn` 的 worker 及其 `multiprocessing` fork 仍占用 8000 端口 → 旧服务未停、重启失败
- **修复**：`restart_helper.py` 重写 — 按端口查 PID（`ss`/`lsof`/`fuser` 回退）→ 杀进程树 → `pkill -f 'run.py'` + `pkill -f 'app.main:app'` 双重兜底 → 重新拉起
- **验证**：真实 HTTP 调用 `/api/system/restart` → 返回 `restarting` → 8s 后健康检查 OK → 模型与数据完整保留

### API Key 配置页显示为空
- **根因**：数据层持久化正常（临时库 + 真实端点双验证 Key 正确落库），前端「编辑」弹窗不显示 Key（安全考虑），用户误以为未保存
- **修复**：编辑时以掩码 `••••••••••••` 显示 → 提交时保留原 Key（掩码或空值发送为 `undefined`）；前端提示"输入新值则覆盖"
- **预防**：模型配置页供应商选择时动态 placeholder 显示该供应商有效模型名（如 DeepSeek → `deepseek-v4-pro / deepseek-v4-flash`）

### 模型测试 400
- **根因**：JoeAI 的 `model_name` 为 `DeepSeek Flash`，DeepSeek API 要求精确名称 `deepseek-v4-pro` 或 `deepseek-v4-flash`
- **修复**：更新 `model_name` 为 `deepseek-v4-flash` → 测试通过 `status: ok`、对话正常返回

---

## 2026-07-27: 流程图增强 — 判断/循环/拖拽编辑/可执行代码生成

### AI 驱动流程图生成
- 更新 `ai_service.py` 测试用例生成 prompt：要求 AI 在每步骤中输出 `flow_type`（action/condition/loop）、条件表达式、循环参数
- 更新 `testgen_service.py` `_description_to_flow`：根据 `flow_type` 生成 **判断节点**（菱形，含 true/false 分支 + 合并点）和**循环节点**（for/while，含 body + exit 边）
- 流程图以 ReactFlow JSON（nodes/edges）存储于 `test_flows` 表

### 流程图编辑器重写（frontend/pages/TestFlowEditor.tsx）
- **自定义节点**：Start（绿色药丸）、Action（蓝色矩形）、**Condition（黄色菱形）**、**Loop（紫色矩形）**、End（红色药丸）
- **节点面板**：左侧 120px 侧边栏，拖动节点到画布即添加
- **双击编辑**：Action 节点可编辑命令/预期结果；Condition 可编辑条件表达式 + true/false 标签；Loop 可编辑 for/while + 循环变量 + 次数
- **边编辑**：双击边可编辑标签（用于条件分支）
- **删除**：选中节点/边后按 Delete 或点击「删除选中」按钮（开始/结束节点受保护）

### 可执行代码生成
- 新增 `backend/app/services/codegen_service.py`：遍历流程图拓扑，递归生成完整 Python 测试脚本
  - Action → `send_command()` + `assert` + 步骤计数
  - Condition → `if/else` 块
  - Loop → `for i in range(n)` / `while condition`
- 新增 API 端点：`POST /api/testcases/{id}/generate-code`
- 前端「生成代码」按钮 → 调用后端 → Drawer 展示代码 → 一键复制
- 验证：10 节点 12 边的温度监控流程图 → 生成 90 行 Python，含嵌套 if/else + for 循环 + 断言

### 前端 API 方法扩展
- `testCaseAPI.generate` — AI 生成并保存测试用例
- `testCaseAPI.getFlow` / `createFlow` / `updateFlow` — 流程图 CRUD
- `testCaseAPI.generateCode` — 流程图转代码

---

## 2026-08-01: 流程图编辑器 Bug 修复 + 撤销/重做 + 代码生成器修复

### Bug 修复: 连线选中后无法删除

- **根因**：`TestFlowEditor.tsx` 中 `handleDelete` 的边过滤条件写反 — `eds.filter((e) => e.selected || ...)` 意图删除已选中的边，但逻辑上是「保留」已选中的边，导致选中边后按 Delete 无反应
- **修复**：`e.selected` → `!e.selected`（删除选中的边而非保留），同时修复 `handleDelete` 的回调依赖使其在键盘快捷键中正常工作
- **快捷键增强**：Delete/Backspace 键现在直接触发删除（不受输入框聚焦影响），Ctrl+Z 撤销、Ctrl+Y 重做

### 新功能: 撤销/重做 (Undo/Redo)

- **历史栈**：`useRef` 存储 nodes/edges 快照数组，最大 50 步上限
- **快照时机**：拖拽添加节点、连线、编辑节点配置、编辑边标签、删除操作前自动 push
- **撤销/重做**：`_skipHistoryRef` 防止还原时的二次记录；`canUndo`/`canRedo` 控制按钮状态
- **UI**：工具栏新增「撤销」「重做」按钮（ArrowLeftOutlined 图标，重做按钮水平翻转显示）

### 代码生成器修复 (backend/app/services/codegen_service.py)

修复了 3 个 bug：

1. **函数体缩进错误**：初始 `walk()` 调用 `indent=2`（8 空格）→ 改为 `indent=1`（4 空格），末尾 `log.info`/`return results` 缩进同步修正
2. **f-string 引号嵌套语法错误**：断言消息 `f'Expected {expected!r}...'` 在 expected 为 `'OK'` 时生成 `f'Expected 'OK'...'` → 语法错误；改为双引号外层 `f\"Expected {expected}...\"`
3. **条件分支汇聚点错误嵌套**：`walk(true_target)` 会继续递归 walk 其剩余邻居 → 汇聚点（如 loop_repeat）被写入 if 分支内部；新增 `no_remaining` 参数，条件分支 walk 时 `no_remaining=True`，汇聚点由 condition handler 在 if/else 后通过取两个分支目标的直接后继交集显式 walk

### 测试验证

- 5 类流程图全覆盖测试全部通过：顺序流 / while 循环 / 中文标签(是/否) / YesNo 标签 / 无标签 fallback
- API 端到端验证：`POST /api/testcases/{id}/generate-code` → 生成代码编译为合法 Python
- 前端 `tsc --noEmit` 类型检查通过

---

## 2026-08-05: AI Token 预算与 JSON 输出优化

### 问题背景

DeepSeek V4 是推理模型，`max_tokens` 在 `reasoning_content`（内部推理）和 `content`（最终输出）之间共享。模型优先将 token 分配给推理过程，导致 JSON 输出被截断，测试用例生成为空。

### 实施方案（5 项优化）

1. **System Prompt 优化**：`ai_service.py` 中 `generate_test_cases` 的 system prompt 从约 2500 字符压缩到紧凑 schema 描述（~800 字符），节省约 700 tokens，直接让渡给 JSON 输出。

2. **前端默认 max_tokens 提升**：`ModelConfig.tsx` 新建模型时默认 `max_tokens` 从 2048 提升到 16384，placeholder 同步更新。

3. **Chat 场景 min_tokens 提升**：`ai_service.py` 中 `chat` 方法的 token 下限从 4096 提升到 16384。

4. **reasoning_content 提取**：`OpenAIProvider.chat()` 返回结果增加 `reasoning_content` 字段，便于日志观测。

5. **生成用例保持 32768**：压缩后的 system prompt 配合 32768 token 预算已足够。

### 关键文件变更
| 文件 | 变更 |
|------|------|
| `backend/app/services/ai_service.py` | System prompt 压缩 + chat min_tokens 4096→16384 |
| `backend/app/ai/__init__.py` | `OpenAIProvider.chat()` 增加 `reasoning_content` |
| `frontend/src/pages/ModelConfig.tsx` | 默认 max_tokens 2048→16384 + placeholder 更新 |
| `KANBAN.md` | 新增优化记录 |
| `HISTORY.md` | 本记录 |

---

## 2026-08-05 (上午): AI 测试用例生成超时修复 + 鲁棒性增强

### 问题现象

AI 模型配置正常，对话有回复。但 AI 助手中点击「生成测试用例」时提示 "AI请求失败"（前端 30s 超时），而后端直接调用 curl 却能成功（耗时约 70 秒）。

### 根因定位

**前端 axios 默认超时 30 秒**。DeepSeek V4 是推理模型，`completion_tokens` 的约 70% 被 `reasoning_content`（内部推理）消耗。例如用"mini-Gateway100 读 DIG1 → CAN1 发送 0x850102"测试时，实际 API 调用：`prompt_tokens=2558, completion_tokens=14928, reasoning_tokens=10510`，耗时约 70 秒——远超前端 30s 超时。

这是一个**之前未被发现的系统性 bug**：上次 Token 预算优化已增加后端 min_tokens（32768）和 httpx 超时（120s），但未同步更新前端 axios 超时。

### 修复（4 项 + 日志增强）

1. **前端 axios 超时分层**：新增 `apiLongTimeout` 实例（300s）；AI 类 API（chat/generate/query/test/speech）全部切到长超时；基础 API 保持 120s
2. **后端 httpx 分层超时**：`OpenAIProvider.chat()` 超时从 `timeout=120.0` → `httpx.Timeout(300.0, connect=30.0)`（总超时 5 分钟，连接超时 30 秒）
3. **超时友好提示**：`apiHelper.ts` 检测 `ECONNABORTED`/`ETIMEDOUT`，提示"推理模型可能需要 1-3 分钟生成回复"，避免用户困惑
4. **日志增强**：`generate_test_cases` 增加 `elapsed` 耗时 + `reasoning_tokens` 单独计数日志，便于后续排查

### 关键文件变更

| 文件 | 变更 |
|------|------|
| `frontend/src/services/api.ts` | 新增 `apiLongTimeout`（300s），AI API 全部切到此实例 |
| `frontend/src/services/apiHelper.ts` | 超时/网络错误特殊提示 |
| `backend/app/ai/__init__.py` | httpx 超时 `httpx.Timeout(300, connect=30)` |
| `backend/app/services/ai_service.py` | 导入 `time`，`generate_test_cases` 耗时+token 日志 |
| `KANBAN.md` | 新增优化记录 |
| `HISTORY.md` | 本记录 |

### 验证

- 用户需求文本"链接mini-Gateway100，通过mini-Gateway100读取数字通道1，如果读到是0，则通过CAN1，发送CAN消息 0x850102，CAN ID=0x10，并读取回复的消息，如果没有回复，提示time out" → 生成 7 个测试用例（正常/异常/边界全覆盖）
- 后端 Python 编译 ✅ | 前端 TypeScript 编译 ✅
- 耗时 ~70s，`completion_tokens=14928, reasoning_tokens=10510`

---

## 下一步计划
- [ ] 端到端集成测试（AI → 流程图 → 编辑 → 代码 → 执行）
- [ ] 性能优化（启动速度、大数据渲染）
- [ ] 国际化（中英文界面切换）
- [ ] 打包与安装程序制作
- [ ] 更多仪器驱动的适配与测试
- [ ] CI/CD 流水线搭建

---

> 最后更新：2026-08-05
