# AITestLab 系统架构设计文档

## 1. 系统整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (React 18)                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 设备管理  │ │ 测试用例  │ │ 测试执行  │ │ 数据查询  │ │ 报告管理  │ │
│  │ Device   │ │TestCase  │ │Execution │ │  Query   │ │ Report   │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ │
│       └─────────────┴────────────┴────────────┴────────────┘        │
│                              │ HTTP/WebSocket                        │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│                     Backend (Python 3.11+ FastAPI)                   │
│                              │                                       │
│  ┌───────────────────────────┴──────────────────────────────────┐   │
│  │                      API Layer (FastAPI)                      │   │
│  │  /api/devices  /api/testcases  /api/executions  /api/ai ...   │   │
│  └───────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│  ┌───────────────────────────┴──────────────────────────────────┐   │
│  │                    Service Layer (业务逻辑)                    │   │
│  │  DeviceService  TestGenService  ExecutionService              │   │
│  │  AIService      ReportService    LogService                   │   │
│  └───────┬───────────────┬───────────────┬──────────────────────┘   │
│          │               │               │                           │
│  ┌───────┴───────┐ ┌─────┴─────┐ ┌───────┴──────────┐              │
│  │ Communication │ │ AI Engine │ │  Plugin Manager  │              │
│  │    Layer      │ │ (统一抽象) │ │  (importlib)     │              │
│  │ SCPI/CAN/UART │ │Local/Cloud│ │  动态加载/卸载    │              │
│  └───────┬───────┘ └─────┬─────┘ └───────┬──────────┘              │
│          │               │               │                           │
│  ┌───────┴───────────────┴───────────────┴──────────────────┐      │
│  │              Data Layer (SQLAlchemy + SQLite)             │      │
│  └──────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

### 架构分层说明

| 层级 | 职责 | 关键技术 |
|------|------|----------|
| 前端展示层 | UI 渲染、用户交互、流程图编辑 | React 18 + Ant Design + ReactFlow |
| API 网关层 | 路由分发、请求验证、WebSocket 管理 | FastAPI + Pydantic |
| 服务层 | 业务逻辑编排、跨模块调用 | Python Service 类 |
| 通信层 | 硬件设备协议实现 | PyVISA / python-can / pyserial |
| AI 引擎层 | LLM 调用抽象与路由 | httpx + openai SDK |
| 插件层 | 动态协议扩展 | importlib + entry_points |
| 数据层 | ORM 映射、数据持久化 | SQLAlchemy + SQLite |

---

## 2. 前端架构设计

### 2.1 路由设计

```
/                          → 主页 / 仪表盘
/login                     → 登录页（预留）
/devices                   → 设备管理列表
/devices/:id               → 设备详情与实时监控
/testcases                 → 测试用例列表
/testcases/:id             → 测试用例详情 + 流程图编辑器
/testcases/:id/flow        → 全屏流程图编辑
/executions                → 测试执行历史
/executions/:id            → 执行详情与实时监控
/executions/:id/live       → 实时执行监控面板
/logs                      → 通信日志查询
/logs/:id                  → 日志详情
/reports                   → 报告管理
/reports/templates         → 报告模板管理
/reports/:id               → 报告预览
/ai/config                 → AI 模型配置
/plugins                   → 插件管理
/settings                  → 系统设置
```

### 2.2 组件树

```
<App>
├── <Layout>
│   ├── <Sidebar>                           # 侧边导航
│   │   ├── <Logo />
│   │   ├── <NavMenu />                     # Ant Design Menu
│   │   └── <DeviceStatusBadge />           # 设备连接状态指示
│   │
│   ├── <Header>
│   │   ├── <Breadcrumb />
│   │   ├── <GlobalSearch />                # 全局搜索
│   │   └── <UserMenu />                    # 设置/关于
│   │
│   └── <Content>
│       ├── <DashboardPage>                 # 主页仪表盘
│       │   ├── <DeviceOverview />
│       │   ├── <RecentExecutions />
│       │   └── <SystemStatus />
│       │
│       ├── <DevicePage>
│       │   ├── <DeviceList />              # 设备列表（Table）
│       │   ├── <DeviceConnectModal />      # 连接设备对话框
│       │   └── <DeviceDetail>
│       │       ├── <DeviceInfo />
│       │       ├── <DeviceConfigForm />
│       │       └── <DeviceLiveMonitor />   # 实时数据面板
│       │
│       ├── <TestCasePage>
│       │   ├── <TestCaseList />
│       │   ├── <TestCaseGenerator>         # AI 用例生成面板
│       │   │   ├── <RequirementInput />    # 需求输入（文字/语音）
│       │   │   ├── <VoiceInput />          # 语音输入组件
│       │   │   └── <GeneratedPreview />
│       │   └── <TestCaseFlowEditor>        # ReactFlow 流程图编辑器
│       │       ├── <FlowCanvas />          # 画布
│       │       ├── <NodePalette />         # 节点面板
│       │       ├── <NodeConfigPanel />     # 节点属性面板
│       │       └── <FlowToolbar />         # 工具栏（缩放/导出/保存）
│       │
│       ├── <ExecutionPage>
│       │   ├── <ExecutionList />
│       │   ├── <ExecutionRunner>           # 测试执行器
│       │   │   ├── <StepProgress />
│       │   │   ├── <DeviceDataPanel />
│       │   │   └── <ExecutionLog />
│       │   └── <ExecutionMonitor />        # 实时监控
│       │
│       ├── <LogPage>
│       │   ├── <LogFilter />               # 日志筛选器
│       │   ├── <LogTable />                # 日志列表
│       │   └── <LogDetail />
│       │
│       ├── <ReportPage>
│       │   ├── <ReportList />
│       │   ├── <ReportGenerator />
│       │   ├── <ReportPreview />           # 报告预览
│       │   └── <TemplateManager />
│       │
│       ├── <AIConfigPage>
│       │   ├── <ModelList />               # 已配置模型列表
│       │   ├── <ModelConfigForm />         # 模型配置表单
│       │   └── <ModelTestPanel />          # 模型测试面板
│       │
│       └── <PluginPage>
│           ├── <PluginList />
│           ├── <PluginInstallModal />
│           └── <PluginDetail />
│
├── <NotificationCenter />                  # 全局通知
└── <WebSocketProvider />                   # WebSocket 连接管理
```

### 2.3 状态管理方案

采用 **Zustand** 作为状态管理库（轻量、TypeScript 友好），划分以下 Store：

```typescript
// stores/deviceStore.ts       - 设备连接状态、设备列表
// stores/testcaseStore.ts     - 测试用例数据、流程图节点/边
// stores/executionStore.ts    - 执行状态、实时步骤进度
// stores/logStore.ts          - 通信日志数据
// stores/reportStore.ts       - 报告列表、模板数据
// stores/aiConfigStore.ts     - AI 模型配置
// stores/pluginStore.ts       - 插件列表与状态
// stores/uiStore.ts           - 全局 UI 状态（侧栏、主题等）
```

#### 状态分类策略

| 类型 | 管理方式 | 示例 |
|------|----------|------|
| 服务端状态 | React Query (TanStack Query) | 设备列表、测试用例列表、日志 |
| 客户端状态 | Zustand | 流程图编辑状态、UI 状态 |
| 实时状态 | WebSocket + Zustand | 设备监控数据、执行进度 |
| 表单状态 | Ant Design Form | 设备配置、AI 模型配置 |

---

## 3. 后端架构设计

### 3.1 模块划分

```
backend/app/
├── api/                    # API 路由层（仅处理请求/响应）
│   ├── __init__.py
│   ├── deps.py            # 依赖注入（get_db, get_current_user）
│   ├── devices.py         # /api/devices/*
│   ├── testcases.py       # /api/testcases/*
│   ├── executions.py      # /api/executions/*
│   ├── ai.py              # /api/ai/*
│   ├── speech.py          # /api/speech/*
│   ├── logs.py            # /api/logs/*, /api/query/*
│   ├── reports.py         # /api/reports/*
│   ├── plugins.py         # /api/plugins/*
│   └── websocket.py       # WebSocket 端点
│
├── core/                   # 核心配置与基础设施
│   ├── __init__.py
│   ├── config.py          # 配置管理（Pydantic Settings）
│   ├── database.py        # SQLAlchemy engine + session
│   ├── security.py        # 认证（预留）
│   └── exceptions.py      # 自定义异常
│
├── models/                 # SQLAlchemy ORM 模型
│   ├── __init__.py
│   ├── device.py
│   ├── test_case.py
│   ├── test_flow.py
│   ├── test_execution.py
│   ├── communication_log.py
│   ├── test_report.py
│   ├── ai_model.py
│   └── plugin.py
│
├── schemas/                # Pydantic 请求/响应模型
│   ├── __init__.py
│   ├── device.py
│   ├── test_case.py
│   ├── test_flow.py
│   ├── test_execution.py
│   ├── communication_log.py
│   ├── test_report.py
│   ├── ai_model.py
│   ├── plugin.py
│   └── common.py          # 通用分页、错误响应等
│
├── services/               # 业务逻辑层
│   ├── __init__.py
│   ├── device_service.py      # 设备连接/断开/状态管理
│   ├── testgen_service.py     # AI 测试用例生成
│   ├── execution_service.py   # 测试执行引擎
│   ├── ai_service.py          # AI 模型调用抽象
│   ├── speech_service.py      # 语音识别
│   ├── log_service.py         # 日志记录与查询
│   ├── report_service.py      # 报告生成
│   ├── plugin_service.py      # 插件管理
│   └── nl_query_service.py    # 自然语言查询
│
├── communication/           # 通信协议实现
│   ├── __init__.py
│   ├── base.py             # 通信抽象基类
│   ├── scpi.py             # SCPI 协议 (PyVISA)
│   ├── can_bus.py           # CAN/CAN FD (python-can)
│   ├── serial_port.py      # 串口 (pyserial)
│   ├── ethernet.py         # TCP/UDP (asyncio)
│   └── gpib.py             # GPIB (PyVISA)
│
├── ai/                      # AI 引擎抽象层
│   ├── __init__.py
│   ├── base.py             # AI Provider 抽象基类
│   ├── openai_provider.py  # OpenAI 兼容 API
│   ├── ollama_provider.py  # Ollama 本地模型
│   ├── anthropic_provider.py
│   └── factory.py          # Provider 工厂
│
├── plugins/                 # 插件系统核心
│   ├── __init__.py
│   ├── manager.py          # 插件管理器
│   ├── loader.py           # 插件加载器 (importlib)
│   ├── interface.py        # 插件接口规范 (ABC)
│   └── sandbox.py          # 插件安全沙箱
│
└── main.py                  # FastAPI 应用入口
```

### 3.2 服务层设计模式

每个 Service 采用依赖注入模式，通过 FastAPI Depends 注入：

```python
# 示例：DeviceService
class DeviceService:
    def __init__(self, db: Session, plugin_manager: PluginManager):
        self.db = db
        self.plugin_manager = plugin_manager

    async def connect_device(self, config: DeviceConnectRequest) -> Device:
        # 1. 根据协议类型选择通信驱动
        # 2. 建立连接
        # 3. 持久化设备信息
        # 4. 返回设备对象
        pass
```

### 3.3 测试执行引擎设计

```
ExecutionEngine
├── FlowParser           # 解析测试流程图为执行序列
│   ├── 拓扑排序节点
│   ├── 解析条件分支
│   └── 处理循环节点
│
├── StepExecutor         # 单步执行器
│   ├── 发送指令到设备
│   ├── 读取设备响应
│   ├── 超时处理
│   └── 结果验证
│
├── ParallelScheduler    # 并行执行调度
│   ├── asyncio.Task 管理
│   └── 设备资源锁
│
└── EventBus             # 执行事件总线
    ├── 步骤开始/完成事件
    ├── 错误事件
    └── 推送到 WebSocket
```

---

## 4. 插件系统架构

### 4.1 插件接口规范

```python
# plugins/interface.py

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class CommunicationPlugin(ABC):
    """通信协议插件基类"""

    # --- 元数据 ---
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    def config_schema(self) -> Dict[str, Any]:
        """返回 JSON Schema 描述插件配置项，供前端动态生成表单"""
        return {}

    # --- 生命周期 ---
    @abstractmethod
    async def connect(self, config: Dict[str, Any]) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def is_connected(self) -> bool: ...

    # --- 通信 ---
    @abstractmethod
    async def send(self, data: bytes, timeout: float = 5.0) -> None: ...

    @abstractmethod
    async def receive(self, timeout: float = 5.0) -> bytes: ...

    @abstractmethod
    async def query(self, data: bytes, timeout: float = 5.0) -> bytes: ...

    # --- 可选 ---
    async def get_status(self) -> Dict[str, Any]:
        """返回设备状态信息"""
        return {}

    async def discover_devices(self) -> List[Dict[str, Any]]:
        """设备发现"""
        return []
```

### 4.2 插件加载机制

```
Plugin Loader Flow:

1. 扫描阶段 (startup)
   ┌────────────────────────────────────────────────────┐
   │ ① 扫描 plugins/ 目录下的 .py 文件和包              │
   │ ② 扫描 setuptools entry_points: "aitestlab.plugins"│
   │ ③ 验证每个插件是否实现 CommunicationPlugin         │
   │ ④ 加载插件元数据到 PluginRegistry                  │
   └────────────────────────────────────────────────────┘

2. 启用阶段 (runtime)
   ┌────────────────────────────────────────────────────┐
   │ ① 用户通过 API/UI 启用插件                         │
   │ ② importlib.reload() 热加载插件模块                │
   │ ③ 实例化插件，调用 connect()                       │
   │ ④ 注册到 PluginManager.active_plugins              │
   └────────────────────────────────────────────────────┘

3. 运行时
   ┌────────────────────────────────────────────────────┐
   │ ① 设备操作通过 PluginManager 路由到对应插件        │
   │ ② 插件在独立线程/协程中运行                        │
   │ ③ 异常隔离：单个插件崩溃不影响系统                  │
   └────────────────────────────────────────────────────┘

4. 卸载阶段
   ┌────────────────────────────────────────────────────┐
   │ ① disconnect() → 清理资源                          │
   │ ② 从 PluginManager 移除                            │
   │ ③ 清理模块引用（可选 reload）                       │
   └────────────────────────────────────────────────────┘
```

### 4.3 插件安全沙箱

- **文件系统隔离**：插件仅允许读写 `plugins/<plugin_name>/data/` 目录
- **网络限制**：插件网络请求通过代理审计
- **超时控制**：每次调用设最大执行时间
- **异常捕获**：所有插件调用包裹 try/except，异常记入日志而不传播

---

## 5. AI 集成架构

### 5.1 统一抽象层

```
                    ┌──────────────────────────────┐
                    │       AIService (Facade)      │
                    │   - chat(prompt) -> response  │
                    │   - stream(prompt) -> stream  │
                    │   - embed(text) -> vector     │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┴───────────────┐
                    │       AIProviderFactory       │
                    │   create(provider_type, cfg)  │
                    └──────────────┬───────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────┴─────────┐   ┌─────────┴─────────┐   ┌─────────┴─────────┐
│  OpenAIProvider   │   │  OllamaProvider   │   │ AnthropicProvider │
│  (openai SDK)     │   │  (httpx)          │   │  (httpx)          │
├───────────────────┤   ├───────────────────┤   ├───────────────────┤
│ GPT-4/GPT-4o      │   │ Llama/Mistral/... │   │ Claude 3/3.5      │
│ 通义千问(兼容)     │   │ 本地模型           │   │                   │
│ 混元(兼容)         │   │                   │   │                   │
│ 文心一言(兼容)     │   │                   │   │                   │
└───────────────────┘   └───────────────────┘   └───────────────────┘
```

### 5.2 Provider 接口

```python
class AIProvider(ABC):
    @abstractmethod
    async def chat(self, messages: List[Dict], **kwargs) -> str: ...

    @abstractmethod
    async def stream_chat(self, messages: List[Dict], **kwargs) -> AsyncIterator[str]: ...

    @abstractmethod
    async def list_models(self) -> List[ModelInfo]: ...

    async def embed(self, text: str) -> List[float]:
        raise NotImplementedError
```

### 5.3 AI 调用流程

```
用户输入（文字/语音）
    │
    ▼
┌──────────────┐     ┌─────────────────┐
│ 语音转文字     │────▶│ Prompt 构建      │
│ (Whisper API) │     │ (模板+上下文)    │
└──────────────┘     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ AIService 路由   │
                     │ 选择 Provider    │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ 本地模型  │  │ 云端模型  │  │ 自定义   │
        │ Ollama   │  │ OpenAI   │  │ Endpoint │
        └──────────┘  └──────────┘  └──────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ 解析 AI 响应     │
                     │ 结构化输出       │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │ 生成测试用例/    │
                     │ 流程图/查询结果  │
                     └─────────────────┘
```

---

## 6. 数据流设计

### 6.1 测试用例生成数据流

```
用户输入需求
    │
    ▼
Frontend: RequirementInput
    │ POST /api/testcases/generate { requirement: "...", model_id: "..." }
    ▼
Backend: TestGenService
    │ 1. 构建 Prompt（系统提示 + 需求 + 设备上下文）
    │ 2. AIService.chat() → AI 响应
    │ 3. 解析 JSON 响应 → 测试步骤 + 流程图结构
    │ 4. 保存到 DB (test_cases, test_flows)
    ▼
Response: { test_case: {...}, flow: { nodes: [...], edges: [...] } }
    │
    ▼
Frontend: TestCaseFlowEditor
    │ ReactFlow 渲染流程图
    │ 用户可拖拽编辑
    │ PUT /api/testcases/{id} 保存修改
```

### 6.2 测试执行数据流

```
用户点击"运行测试"
    │
    ▼
Frontend
    │ POST /api/executions/run { testcase_id: "..." }
    │ 同时建立 WebSocket 连接: ws://host/ws/executions/{id}
    ▼
Backend: ExecutionService
    │ 1. 加载 test_flow → 解析执行序列
    │ 2. 按序执行步骤
    │    ├── 发送指令到设备 (DeviceService → CommunicationLayer)
    │    ├── 读取响应
    │    ├── 记录通信日志 (LogService)
    │    └── 验证结果
    │ 3. 通过 WebSocket 推送实时状态
    │    { type: "step_start"|"step_complete"|"error"|"progress", data: {...} }
    ▼
Frontend: ExecutionMonitor
    │ WebSocket 实时更新进度条、设备数据、日志
    │ 执行完成后显示结果摘要
```

### 6.3 自然语言查询数据流

```
用户输入查询（文字/语音）
    │
    ▼
Frontend
    │ POST /api/query/natural-language { query: "上周通过的测试有多少个？" }
    │ 或 POST /api/query/speech { audio: <base64> }
    ▼
Backend: NLQueryService
    │ 1. 语音 → Whisper 转文字（如果是语音查询）
    │ 2. AIService.chat() 将自然语言转为 SQL
    │    Prompt: "将以下查询转为 SQLite SQL: ... 表结构: ..."
    │ 3. 执行 SQL（只读，安全校验）
    │ 4. AIService.chat() 将结果转为自然语言解释
    │ 5. 返回结构化结果 + 自然语言解释
    ▼
Response: { sql: "...", results: [...], explanation: "..." }
    │
    ▼
Frontend: 展示查询结果（表格 + 图表）
```

### 6.4 WebSocket 实时数据流

```
Client                                    Server
  │                                          │
  │── WS /ws/executions/{id} ──────────────▶│ 订阅执行事件
  │                                          │
  │◀── { type: "execution_started" } ───────│
  │◀── { type: "step_start", step: 1 } ─────│
  │◀── { type: "device_data", data: {...} }─│
  │◀── { type: "step_complete", result: {}}─│
  │◀── { type: "execution_complete" } ──────│
  │                                          │
  │── WS /ws/devices/{id}/monitor ─────────▶│ 订阅设备实时数据
  │◀── { type: "device_data", value: 3.3 }──│ 持续推送
```

---

## 7. 部署架构（预留）

```
开发环境:
  Frontend: Vite Dev Server (localhost:5173)
  Backend:  uvicorn --reload (localhost:8000)
  DB:      SQLite (本地文件)

生产环境（规划）:
  Frontend: Nginx 静态文件服务
  Backend:  Gunicorn + Uvicorn Workers
  DB:      PostgreSQL (可切换)
```

---

## 8. 关键设计原则

1. **协议无关**：通信层抽象基类确保新增协议无需修改上层代码
2. **AI 模型无关**：统一 Provider 接口屏蔽不同厂商 API 差异
3. **插件热加载**：importlib 实现运行时加载/卸载，无需重启
4. **数据不可变日志**：通信日志只追加写入，不修改
5. **前端组件原子化**：每个页面组件独立，通过 Store 共享状态
6. **错误边界**：前后端均设错误边界，单点故障不扩散
