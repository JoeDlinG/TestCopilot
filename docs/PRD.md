# AITestLab - 产品需求文档 (PRD)

> **版本**: v1.0  
> **日期**: 2026-07-04  
> **作者**: PM  
> **状态**: 初始草案

---

## 目录

1. [产品概述](#1-产品概述)
2. [目标用户](#2-目标用户)
3. [功能需求](#3-功能需求)
4. [非功能需求](#4-非功能需求)
5. [技术栈建议](#5-技术栈建议)
6. [系统架构概要](#6-系统架构概要)
7. [数据模型概要](#7-数据模型概要)
8. [UI/UX 设计方向](#8-uiux-设计方向)
9. [任务拆解](#9-任务拆解)
10. [里程碑规划](#10-里程碑规划)
11. [风险与应对](#11-风险与应对)

---

## 1. 产品概述

### 1.1 产品定位

AITestLab 是一款面向硬件测试工程师的 **AI 驱动的测试自动化平台**。它将传统仪器控制、通信协议、AI 大模型和测试管理整合到一个统一的桌面应用中，实现从"自然语言描述测试需求"到"自动化执行测试并生成报告"的全流程闭环。

### 1.2 核心价值

| 痛点 | AITestLab 解决方案 |
|------|-------------------|
| 测试脚本编写耗时 | AI 从自然语言/语音自动生成测试用例 |
| 多协议适配复杂 | 插件化协议扩展，统一设备抽象层 |
| 测试数据分散难管理 | SQLite + CSV 统一存储，支持自然语言查询 |
| 测试报告格式不统一 | 可自定义字段的标准化报告生成 |
| 设备切换成本高 | 统一设备连接管理，支持主流仪器和总线工具 |

### 1.3 产品边界

**包含**:
- 桌面端应用（Electron 或 Web 技术栈 + 本地服务）
- 本地 AI 推理 + 云端 AI 接入
- 测试用例生命周期管理（创建 → 执行 → 结果 → 报告）

**不包含**:
- 移动端 App
- 多人协作 / 云同步
- CI/CD 流水线集成（v1 阶段）
- 实时固件调试

---

## 2. 目标用户

### 2.1 用户画像

| 角色 | 描述 | 核心场景 |
|------|------|---------|
| **硬件测试工程师** | 负责板级/系统级测试验证 | 连接仪器 → 配置测试参数 → 执行测试 → 查看结果 |
| **嵌入式开发工程师** | 需要调试 CAN/串口通信 | 使用 CAN 工具发送/监听报文，分析通信日志 |
| **测试经理** | 审核测试覆盖率和结果 | 查看测试报告，追溯测试数据 |
| **自动化测试开发** | 编写和维护测试脚本 | 通过 AI 快速生成测试用例框架 |

### 2.2 典型使用流程

```
用户语音输入: "测试 DCDC 电源模块的输出电压，输入 12V，输出应为 5V ± 0.1V，负载 1A"

→ AI 解析需求
→ 生成测试流程图（可视化）
→ 用户确认/修改
→ 自动连接可编程电源 + 电子负载 + 万用表
→ 执行测试序列
→ 记录 CSV 日志 + SQLite
→ 生成测试报告
```

---

## 3. 功能需求

### F1: 设备连接与仪器控制

#### F1.1 设备发现与连接
- **优先级**: P0（核心）
- **描述**: 自动扫描并识别已连接的测试仪器，支持手动配置连接参数
- **详细需求**:
  1. 支持通过 VISA (Virtual Instrument Software Architecture) 发现 GPIB/USB/LAN 仪器
  2. 支持手动输入 IP 地址/端口连接网络仪器
  3. 支持串口自动扫描（列出可用 COM 口/tty 设备）
  4. 设备连接状态实时显示（已连接/断开/错误）
  5. 保存常用设备配置，支持一键重连
  6. 支持设备别名设置

#### F1.2 仪器类型支持
- **优先级**: P0
- **描述**: 支持主流测试仪器的基本控制
- **详细需求**:
  1. **可编程电源** (Programmable Power Supply)
     - 设置电压/电流
     - 读取实际输出电压/电流
     - 过压/过流保护配置
     - 支持 OVP/OCP 设置
  2. **示波器** (Oscilloscope)
     - 配置时基/垂直灵敏度
     - 触发设置
     - 波形数据捕获与导出
     - 自动测量（Vpp, Freq, Rise time 等）
  3. **万用表** (DMM)
     - DC/AC 电压测量
     - DC/AC 电流测量
     - 电阻/通断测量
     - 频率/周期测量
  4. **电子负载** (Electronic Load)
     - CC/CV/CR/CP 模式设置
     - 动态负载序列
  5. **信号发生器** (Function Generator)
     - 波形选择（正弦/方波/三角/任意波）
     - 频率/幅度/偏置设置

#### F1.3 测试工具链支持
- **优先级**: P0
- **描述**: 集成常用测试总线工具
- **详细需求**:
  1. **CAN 总线** (PCAN, Vector, Kvaser)
     - CAN 报文发送/接收
     - CAN DBC 文件解析
     - 信号级数据显示
     - 总线负载统计
     - 错误帧检测与统计
  2. **LIN 总线**
     - LIN 报文收发
     - LDF 文件解析
  3. **串口通信**
     - 波特率/数据位/停止位/校验位配置
     - ASCII/HEX 数据显示
     - 定时发送
     - 数据分包与协议解析
  4. **以太网通信**
     - TCP/UDP Socket 客户端
     - 自定义报文收发

### F2: 多接口与通信协议支持

#### F2.1 协议抽象层
- **优先级**: P0
- **描述**: 统一的通信接口抽象，屏蔽底层协议差异
- **详细需求**:
  1. 定义通用 `CommunicationInterface` 抽象类
     - `connect()`, `disconnect()`, `send(data)`, `receive()`, `is_connected()`
  2. 所有通信协议实现此接口
  3. 设备驱动基于此接口构建

#### F2.2 支持的协议
- **优先级**: P0-P1
- **详细需求**:
  1. **SCPI** (Standard Commands for Programmable Instruments) - P0
     - 基于 IEEE 488.2 标准
     - 支持 `*IDN?`, `*RST`, `*TST?` 等通用命令
     - 命令自动补全与提示
  2. **CAN** - P0
     - CAN 2.0A / 2.0B
     - CAN FD 支持
  3. **USB** - P1
     - USB HID
     - USB CDC (虚拟串口)
     - libusb 后端
  4. **串口 (UART)** - P0
     - RS-232 / RS-485
  5. **以太网 (TCP/UDP)** - P0
     - Raw Socket
     - Modbus TCP
  6. **GPIB** - P1
     - 通过 VISA 层支持

### F3: 插件扩展系统

#### F3.1 插件架构
- **优先级**: P0
- **描述**: 通过插件机制扩展通信协议和设备驱动
- **详细需求**:
  1. 定义标准插件接口规范（Plugin SDK）
  2. 插件生命周期管理：安装 / 启用 / 禁用 / 卸载 / 更新
  3. 插件市场（可选，v1 阶段内置几个官方插件）
  4. 插件隔离：每个插件在独立进程中运行（防止崩溃影响主程序）
  5. 插件配置持久化

#### F3.2 插件类型
- **优先级**: P0-P1
- **详细需求**:
  1. **协议插件**: 添加新通信协议（如 I2C, SPI, FlexRay, MOST）
  2. **设备驱动插件**: 添加新仪器驱动（如特定品牌型号）
  3. **数据解析插件**: 自定义数据格式解析器
  4. **报告模板插件**: 自定义报告格式

#### F3.3 插件开发工具
- **优先级**: P2
- **描述**: 提供 CLI 工具帮助开发者快速创建插件骨架
- 命令示例: `aitestlab plugin create my-protocol`

### F4: AI 大模型集成

#### F4.1 本地 AI 模型
- **优先级**: P0
- **描述**: 支持本地部署和运行 AI 模型
- **详细需求**:
  1. 支持 Ollama 作为本地推理后端
  2. 支持加载 GGUF/GGML 格式模型
  3. 模型管理：下载 / 切换 / 删除
  4. 支持本地模型列表：Llama, Qwen, DeepSeek 等主流开源模型
  5. 系统资源监控（CPU/内存/GPU 使用率）
  6. 离线工作能力（无需网络连接）

#### F4.2 云端 AI 模型
- **优先级**: P0
- **描述**: 支持接入云端大模型 API
- **详细需求**:
  1. 支持 OpenAI API 兼容接口
  2. 支持配置 API Key / Endpoint / Model Name
  3. 预设服务商模板：OpenAI, 通义千问, 文心一言, DeepSeek 等
  4. 自定义 API 端点（兼容 OpenAI 格式的第三方服务）
  5. 请求频率限制与重试机制
  6. Token 用量统计

#### F4.3 多模态输入
- **优先级**: P1
- **描述**: 支持文字和语音两种方式输入测试需求
- **详细需求**:
  1. **文字输入**: Markdown 编辑器，支持测试需求模板
  2. **语音输入**: 
     - 浏览器 SpeechRecognition API 或 Whisper 本地模型
     - 实时语音转文字
     - 支持中英文
  3. **混合输入**: 语音输入后可在编辑器中修改
  4. **上下文记忆**: 多轮对话，记住之前的测试上下文

#### F4.4 AI 配置管理
- **优先级**: P1
- **描述**: 灵活切换和管理 AI 模型配置
- **详细需求**:
  1. 预设配置方案（本地优先 / 云端优先 / 混合模式）
  2. 按任务类型自动选择模型（简单查询用本地，复杂生成用云端）
  3. 模型响应时间监控
  4. Fallback 机制：云端不可用时自动切换到本地

### F5: 测试用例生成

#### F5.1 AI 需求解析
- **优先级**: P0
- **描述**: 从自然语言/语音描述中提取测试参数和步骤
- **详细需求**:
  1. 实体提取：识别测试对象、参数、条件、期望值
  2. 歧义澄清：当 AI 不确定时，主动向用户提问
  3. 历史学习：参考历史相似测试用例

#### F5.2 测试用例结构
- **优先级**: P0
- **描述**: 标准化测试用例数据模型
- **详细需求**:
  1. 每个测试用例包含：
     - 用例 ID（自动生成）
     - 用例名称
     - 测试目标
     - 前置条件
     - 测试步骤（有序列表）
     - 每个步骤：操作描述、预期结果、超时时间、重试次数
     - 测试数据/参数
     - 判定条件（Pass/Fail 逻辑）
     - 关联设备列表
  2. 支持测试用例分组（Test Suite）
  3. 支持变量与参数化
  4. 支持导入/导出（JSON/YAML 格式）

#### F5.3 流程图展示
- **优先级**: P0
- **描述**: 可视化展示测试流程
- **详细需求**:
  1. 使用流程图库（如 React Flow / Mermaid）渲染
  2. 节点类型：
     - 开始/结束节点
     - 测试步骤节点（含操作和预期结果）
     - 判断节点（条件分支）
     - 循环节点
     - 并行节点
  3. 交互功能：
     - 拖拽调整节点位置
     - 点击节点查看/编辑详情
     - 缩放和平移
     - 导出为图片/SVG
  4. 流程图与测试用例数据双向同步
  5. AI 生成的流程图可直接在界面上修改

### F6: 测试执行引擎

#### F6.1 运行界面
- **优先级**: P0
- **描述**: 测试执行的仪表盘界面
- **详细需求**:
  1. 测试套件选择器（树形结构）
  2. 执行控制：运行 / 暂停 / 停止 / 单步执行
  3. 实时状态面板：
     - 总用例数 / 已执行 / 通过 / 失败 / 跳过
     - 进度条
     - 当前执行步骤高亮
  4. 实时日志窗口（可筛选级别）
  5. 设备连接状态面板
  6. 变量监视窗口（实时显示变量值）
  7. 执行历史记录

#### F6.2 执行引擎特性
- **优先级**: P0
- **描述**: 核心测试执行逻辑
- **详细需求**:
  1. 顺序执行模式（默认）
  2. 并行执行模式（独立用例可并行）
  3. 条件执行（依赖前一步结果）
  4. 循环执行（指定次数或直到条件满足）
  5. 超时控制（每步骤可配置超时）
  6. 失败处理策略：停止 / 跳过 / 重试 N 次
  7. 变量系统：支持全局变量、用例变量、步骤变量
  8. 钩子函数：setup / teardown / on_error

### F7: 日志与结果存储

#### F7.1 通信日志
- **优先级**: P0
- **描述**: 记录所有设备通信数据
- **详细需求**:
  1. 日志条目包含：
     - 时间戳（毫秒级）
     - 设备名称/别名
     - 方向（发送/接收）
     - 原始数据（HEX + ASCII）
     - 协议类型
     - 解析后的数据（如果适用）
  2. 日志级别：DEBUG / INFO / WARNING / ERROR
  3. 实时写入（流式）
  4. 日志过滤与搜索
  5. 日志导出（CSV / TXT）

#### F7.2 测试结果存储
- **优先级**: P0
- **描述**: 结构化存储测试执行结果
- **详细需求**:
  1. **默认 CSV 格式**:
     - 每次测试运行生成一个 CSV 文件
     - 文件命名：`{test_suite}_{timestamp}.csv`
     - 列：timestamp, case_id, case_name, step_id, step_desc, status, actual_value, expected_value, duration_ms, error_msg
  2. **SQLite 数据库**:
     - 表设计见数据模型章节
     - 所有历史数据可查询
     - 支持聚合统计
  3. 存储位置可配置（默认 `~/aitestlab_data/`）

### F8: 数据查询

#### F8.1 自然语言查询
- **优先级**: P1
- **描述**: 通过自然语言查询测试数据
- **详细需求**:
  1. 文本输入查询问题
  2. AI 将自然语言转换为 SQL 查询
  3. 显示生成的 SQL（可手动编辑）
  4. 查询结果以表格形式展示
  5. 查询结果可导出（CSV / Excel）
  6. 查询历史保存

#### F8.2 语音查询
- **优先级**: P2
- **描述**: 通过语音提问查询数据
- **详细需求**:
  1. 语音转文字 → NL2SQL → 执行 → 展示结果
  2. 结果可通过语音播报摘要
  3. 支持追问（上下文保持）

#### F8.3 查询示例
- "上周所有的测试通过率是多少？"
- "哪个测试用例失败次数最多？"
- "CAN 总线在 2026-07-01 的错误帧数量"
- "输出电压超过 5.1V 的测试记录"

### F9: 测试报告

#### F9.1 报告生成
- **优先级**: P0
- **描述**: 根据要求生成测试报告
- **详细需求**:
  1. 报告模板系统：
     - 预设模板（标准测试报告、快速摘要）
     - 用户可创建自定义模板
  2. 报告字段可定义：
     - 用户选择需要包含的数据字段
     - 字段顺序可调整
     - 支持计算字段（如通过率 = 通过数/总数）
  3. 输出格式：
     - PDF（默认）
     - HTML
     - Markdown
     - Word (.docx) - P2

#### F9.2 报告内容
- **优先级**: P0
- **描述**: 报告包含的标准内容
- **详细需求**:
  1. 报告头部：标题、日期、作者、版本
  2. 测试概要：通过率、执行时间、设备列表
  3. 测试结果明细表
  4. 失败用例详细分析
  5. 统计数据图表（趋势图、分布图）
  6. 通信日志摘要
  7. AI 生成的测试结论与建议（可选）

---

## 4. 非功能需求

### NFR1: 性能
| 指标 | 目标值 |
|------|--------|
| 应用启动时间 | < 5 秒 |
| AI 响应时间（本地） | < 10 秒（简单查询） |
| AI 响应时间（云端） | < 5 秒 |
| 通信日志写入延迟 | < 10 ms |
| 测试执行调度延迟 | < 50 ms |
| 流程图渲染（100 节点） | < 2 秒 |

### NFR2: 可靠性
- 单设备通信异常不影响其他设备
- 插件崩溃不导致主程序崩溃（进程隔离）
- 测试执行异常自动保存已执行结果
- SQLite 数据库自动备份

### NFR3: 安全性
- API Key 加密存储（使用操作系统密钥链）
- 本地数据不自动上传云端
- 插件沙箱运行，限制文件系统访问

### NFR4: 可用性
- 界面响应式设计，支持 1024x768 以上分辨率
- 支持中英文界面切换
- 关键操作有确认提示
- 错误信息清晰，提供解决建议

### NFR5: 可维护性
- 代码覆盖率目标 > 70%
- 核心模块（执行引擎、协议层）单元测试覆盖率 > 90%
- 完整的 API 文档（OpenAPI/Swagger）

---

## 5. 技术栈建议

### 5.1 前端
| 技术 | 用途 | 理由 |
|------|------|------|
| **TypeScript** | 主要语言 | 类型安全，大型项目可维护 |
| **React 18** | UI 框架 | 生态成熟，组件丰富 |
| **Ant Design / TDesign** | UI 组件库 | 企业级组件，适合工具类应用 |
| **React Flow** | 流程图渲染 | 专业的流程图组件，支持自定义节点 |
| **Zustand** | 状态管理 | 轻量，比 Redux 简洁 |
| **React Query (TanStack)** | 数据获取 | 缓存/同步/请求管理 |
| **ECharts / Recharts** | 图表 | 数据可视化 |
| **Monaco Editor** | 代码/配置编辑 | VS Code 同款编辑器 |
| **Vite** | 构建工具 | 快速开发和构建 |

### 5.2 后端
| 技术 | 用途 | 理由 |
|------|------|------|
| **Python 3.11+** | 主要语言 | 仪器控制生态好（pyvisa, python-can） |
| **FastAPI** | Web 框架 | 高性能，自动 API 文档，WebSocket 支持 |
| **SQLAlchemy** | ORM | 成熟，支持 SQLite |
| **Alembic** | 数据库迁移 | 版本管理 |
| **Pydantic** | 数据验证 | FastAPI 原生集成 |
| **Celery / ARQ** | 异步任务 | 测试执行的后台任务 |
| **python-can** | CAN 通信 | 支持 PCAN, Vector, Kvaser 等 |
| **PyVISA** | 仪器控制 | SCPI 仪器标准库 |
| **pyserial** | 串口通信 | 跨平台串口 |
| **Ollama Python SDK** | 本地 AI | 本地模型推理 |
| **openai Python SDK** | 云端 AI | OpenAI 兼容 API |
| **faster-whisper** | 语音识别 | 本地语音转文字 |

### 5.3 数据存储
| 技术 | 用途 |
|------|------|
| **SQLite** | 主数据库（测试结果、配置、日志索引） |
| **文件系统** | CSV 日志文件、报告文件 |
| **JSON** | 配置文件、插件元数据 |

### 5.4 部署与打包
| 技术 | 用途 |
|------|------|
| **Electron** | 桌面应用打包（备选方案） |
| **Tauri** | 轻量桌面应用打包（推荐，更小体积） |
| **Docker** | 后端服务容器化（可选） |

---

## 6. 系统架构概要

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (React/TS)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ 设备面板  │ │ 测试设计  │ │ 运行面板  │ │ 报告/查询面板  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│                                                               │
│              WebSocket / REST API / HTTP                       │
├─────────────────────────────────────────────────────────────┤
│                    Backend (Python FastAPI)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ 设备管理器 │ │ AI 服务   │ │ 执行引擎  │ │ 数据/报告服务  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ 协议抽象层 │ │ 插件管理器 │ │ 通信日志  │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
├─────────────────────────────────────────────────────────────┤
│                      数据层                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │  SQLite   │ │ CSV 文件  │ │ 配置文件  │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 数据模型概要

### 7.1 核心表设计

```sql
-- 设备配置表
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    alias TEXT,
    device_type TEXT NOT NULL,        -- power_supply, oscilloscope, dmm, etc.
    connection_type TEXT NOT NULL,     -- visa, serial, socket, can
    connection_params JSON NOT NULL,   -- {"port": "COM3", "baudrate": 115200}
    status TEXT DEFAULT 'disconnected',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试套件表
CREATE TABLE test_suites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试用例表
CREATE TABLE test_cases (
    id TEXT PRIMARY KEY,
    suite_id TEXT REFERENCES test_suites(id),
    name TEXT NOT NULL,
    objective TEXT,
    preconditions TEXT,
    steps JSON NOT NULL,               -- 测试步骤数组
    variables JSON,                    -- 变量定义
    flow_data JSON,                    -- 流程图数据
    status TEXT DEFAULT 'draft',       -- draft, ready, running, passed, failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试执行记录表
CREATE TABLE test_runs (
    id TEXT PRIMARY KEY,
    suite_id TEXT REFERENCES test_suites(id),
    status TEXT NOT NULL,              -- running, completed, aborted
    total_cases INTEGER,
    passed_cases INTEGER DEFAULT 0,
    failed_cases INTEGER DEFAULT 0,
    skipped_cases INTEGER DEFAULT 0,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 步骤执行结果表
CREATE TABLE step_results (
    id TEXT PRIMARY KEY,
    run_id TEXT REFERENCES test_runs(id),
    case_id TEXT REFERENCES test_cases(id),
    step_index INTEGER,
    step_desc TEXT,
    status TEXT,                       -- passed, failed, skipped, error
    actual_value TEXT,
    expected_value TEXT,
    duration_ms INTEGER,
    error_msg TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 通信日志表
CREATE TABLE comm_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    device_id TEXT REFERENCES devices(id),
    direction TEXT,                    -- send, receive
    protocol TEXT,                     -- scpi, can, serial, tcp
    raw_data_hex TEXT,
    raw_data_ascii TEXT,
    parsed_data JSON,
    level TEXT DEFAULT 'INFO'
);

-- AI 对话历史表
CREATE TABLE ai_conversations (
    id TEXT PRIMARY KEY,
    model_name TEXT,
    model_type TEXT,                   -- local, cloud
    messages JSON NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 测试报告模板表
CREATE TABLE report_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    fields JSON NOT NULL,              -- 报告字段定义
    output_format TEXT DEFAULT 'pdf',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插件表
CREATE TABLE plugins (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT,
    plugin_type TEXT,                  -- protocol, device_driver, parser, template
    entry_point TEXT,
    config JSON,
    enabled INTEGER DEFAULT 1,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. UI/UX 设计方向

### 8.1 整体布局

```
┌─────────────────────────────────────────────────┐
│  Logo   导航标签(设备|设计|运行|报告|设置)   用户 │
├──────────┬──────────────────────────────────────┤
│          │                                       │
│  侧边栏   │           主内容区域                   │
│  (设备树  │                                       │
│   测试列表│                                       │
│   日志)   │                                       │
│          │                                       │
├──────────┴──────────────────────────────────────┤
│              状态栏 (连接状态|AI状态|通知)         │
└─────────────────────────────────────────────────┘
```

### 8.2 设计原则
- **暗色主题**为主（适合实验室环境长时间使用）
- 信息密度适中，关键信息突出
- 操作反馈及时（加载状态、成功/失败动画）
- 键盘快捷键支持（高级用户）

---

## 9. 任务拆解

以下任务按优先级和依赖关系排列。

### Phase 0: 项目初始化 (T0)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T0.1 | 项目脚手架搭建（前端 Vite + React + TS，后端 FastAPI） | Arch | 2d | - |
| T0.2 | 开发环境配置（ESLint, Prettier, pytest, CI 配置） | Arch | 1d | T0.1 |
| T0.3 | SQLite 数据库初始化与 Alembic 迁移配置 | Backend | 1d | T0.1 |
| T0.4 | 前后端通信基础（REST API + WebSocket 框架） | Arch | 1d | T0.1 |
| T0.5 | UI 框架搭建（Ant Design + 路由 + 布局） | Frontend | 1d | T0.1 |

### Phase 1: 设备连接与协议层 (T1)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T1.1 | 通信协议抽象接口设计与实现 | Backend | 2d | T0.1 |
| T1.2 | SCPI 协议适配器（基于 PyVISA） | Backend | 3d | T1.1 |
| T1.3 | 串口协议适配器（基于 pyserial） | Backend | 2d | T1.1 |
| T1.4 | CAN 协议适配器（基于 python-can，支持 PCAN/Vector） | Backend | 3d | T1.1 |
| T1.5 | TCP/UDP Socket 协议适配器 | Backend | 2d | T1.1 |
| T1.6 | 设备管理器（发现/连接/状态/重连） | Backend | 3d | T1.1-T1.5 |
| T1.7 | 设备连接 UI（设备列表/连接配置/状态显示） | Frontend | 3d | T1.6 |
| T1.8 | 通信日志实时显示组件 | Frontend | 2d | T1.6 |

### Phase 2: 仪器控制 (T2)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T2.1 | 可编程电源驱动开发 | Backend | 3d | T1.1, T1.2 |
| T2.2 | 示波器驱动开发 | Backend | 4d | T1.1, T1.2 |
| T2.3 | 万用表驱动开发 | Backend | 2d | T1.1, T1.2 |
| T2.4 | 电子负载驱动开发 | Backend | 2d | T1.1, T1.2 |
| T2.5 | 仪器控制面板 UI（通用 + 各仪器专用面板） | Frontend | 5d | T2.1-T2.4 |
| T2.6 | 仪器 SCPI 命令交互终端（手动发送命令） | Frontend | 1d | T2.5 |

### Phase 3: 插件系统 (T3)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T3.1 | 插件 SDK 接口规范定义 | Arch | 2d | T1.1 |
| T3.2 | 插件管理器（加载/生命周期/进程隔离） | Backend | 4d | T3.1 |
| T3.3 | 插件配置持久化 | Backend | 1d | T3.2 |
| T3.4 | 插件管理 UI（安装/启用/禁用/卸载） | Frontend | 2d | T3.2 |
| T3.5 | 官方示例插件（示例协议插件 + 设备插件） | Backend | 2d | T3.2 |

### Phase 4: AI 大模型集成 (T4)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T4.1 | AI 服务抽象层（本地/云端统一接口） | Backend | 2d | T0.1 |
| T4.2 | Ollama 本地模型集成 | Backend | 2d | T4.1 |
| T4.3 | OpenAI 兼容云端 API 集成 | Backend | 2d | T4.1 |
| T4.4 | AI 模型配置管理（切换/Fallback/统计） | Backend | 2d | T4.2, T4.3 |
| T4.5 | 语音输入组件（Whisper + Web Speech API） | Frontend | 3d | T4.1 |
| T4.6 | AI 对话界面（聊天窗口 + 上下文管理） | Frontend | 3d | T4.1 |
| T4.7 | AI 配置管理 UI | Frontend | 2d | T4.4 |

### Phase 5: 测试用例生成与设计 (T5)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T5.1 | 测试用例数据模型与 CRUD API | Backend | 2d | T0.3 |
| T5.2 | AI 测试需求解析 Prompt 工程 | Backend | 3d | T4.1, T5.1 |
| T5.3 | 测试用例生成服务（NL → TestCase JSON） | Backend | 3d | T5.2 |
| T5.4 | 测试用例管理 UI（列表/新建/编辑/删除） | Frontend | 3d | T5.1 |
| T5.5 | 流程图渲染组件（React Flow） | Frontend | 4d | T5.1 |
| T5.6 | 流程图编辑交互（拖拽/连线/编辑节点） | Frontend | 4d | T5.5 |
| T5.7 | AI 生成测试用例入口 UI（文字+语音输入） | Frontend | 2d | T5.3 |

### Phase 6: 测试执行引擎 (T6)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T6.1 | 测试执行引擎核心（调度/状态机/超时） | Backend | 5d | T5.1 |
| T6.2 | 变量系统与作用域 | Backend | 2d | T6.1 |
| T6.3 | 并行执行与条件执行 | Backend | 3d | T6.1 |
| T6.4 | 钩子系统（setup/teardown/on_error） | Backend | 2d | T6.1 |
| T6.5 | 测试执行 UI（仪表盘/控制/进度） | Frontend | 4d | T6.1 |
| T6.6 | 实时状态更新（WebSocket 推送） | Fullstack | 2d | T6.1, T6.5 |
| T6.7 | 变量监视面板 | Frontend | 2d | T6.5 |

### Phase 7: 日志与结果存储 (T7)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T7.1 | 通信日志写入服务（CSV + SQLite 双写） | Backend | 2d | T1.8 |
| T7.2 | 测试结果存储服务 | Backend | 2d | T6.1 |
| T7.3 | 日志查询与过滤 API | Backend | 1d | T7.1 |
| T7.4 | 日志查看器 UI（表格/搜索/导出） | Frontend | 3d | T7.3 |
| T7.5 | 历史测试结果浏览 UI | Frontend | 2d | T7.2 |

### Phase 8: 数据查询 (T8)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T8.1 | NL2SQL 转换服务（AI 驱动） | Backend | 3d | T4.1, T7.2 |
| T8.2 | 查询执行与结果格式化 | Backend | 2d | T8.1 |
| T8.3 | 自然语言查询 UI（文本输入 + 结果表格） | Frontend | 2d | T8.2 |
| T8.4 | 语音查询 UI | Frontend | 2d | T4.5, T8.3 |

### Phase 9: 测试报告 (T9)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T9.1 | 报告模板数据模型与 CRUD API | Backend | 1d | T0.3 |
| T9.2 | 报告生成引擎（PDF/HTML/Markdown） | Backend | 4d | T7.2, T9.1 |
| T9.3 | 报告模板编辑器 UI（字段选择/排序/预览） | Frontend | 3d | T9.1 |
| T9.4 | 报告生成与下载 UI | Frontend | 2d | T9.2 |

### Phase 10: 集成测试与优化 (T10)

| ID | 任务 | 负责人 | 预估工时 | 依赖 |
|----|------|--------|---------|------|
| T10.1 | 端到端集成测试 | QA | 3d | All |
| T10.2 | 性能优化（启动速度/大数据渲染） | Fullstack | 2d | T10.1 |
| T10.3 | 国际化（中英文） | Frontend | 2d | All |
| T10.4 | 打包与安装程序制作 | Arch | 3d | T10.1 |
| T10.5 | 用户文档编写 | PM | 3d | All |
| T10.6 | 已知问题修复 | All | 3d | T10.1 |

---

## 10. 里程碑规划

| 里程碑 | 内容 | 预计时间 | 关键交付物 |
|--------|------|---------|-----------|
| **M0: 项目启动** | Phase 0 完成 | 第 1 周 | 脚手架、基础框架可运行 |
| **M1: 设备联通** | Phase 1-2 完成 | 第 3 周 | 可连接仪器、收发数据 |
| **M2: AI 就绪** | Phase 3-4 完成 | 第 5 周 | 插件系统 + AI 对话可用 |
| **M3: 测试闭环** | Phase 5-6 完成 | 第 8 周 | AI 生成用例 → 流程图 → 执行 |
| **M4: 数据与报告** | Phase 7-9 完成 | 第 10 周 | 日志/查询/报告完整 |
| **M5: 发布就绪** | Phase 10 完成 | 第 12 周 | 可发布版本 |

**总预估工时**: 约 120 人天（12 周，假设 2-3 人并行开发）

---

## 11. 风险与应对

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| 仪器驱动兼容性（不同品牌 SCPI 实现差异） | 高 | 中 | 抽象通用命令集 + 品牌特定适配层 |
| CAN 硬件驱动依赖（PCAN/Vector 需要系统驱动） | 中 | 中 | 提供驱动安装指南 + 检测与提示 |
| AI 生成测试用例质量不稳定 | 高 | 高 | Few-shot 示例 + 用户可编辑 + 反馈循环 |
| 本地 AI 模型资源消耗大 | 中 | 中 | 支持云端 Fallback，可选轻量模型 |
| 插件进程隔离复杂度 | 中 | 低 | 采用子进程 + IPC 通信模式 |
| 语音识别准确率（噪声环境） | 中 | 低 | 支持手动修正 + 多模型选择 |

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| SCPI | Standard Commands for Programmable Instruments，可编程仪器标准命令 |
| VISA | Virtual Instrument Software Architecture，虚拟仪器软件架构 |
| DMM | Digital Multimeter，数字万用表 |
| DBC | CAN Database Container，CAN 数据库文件格式 |
| NL2SQL | Natural Language to SQL，自然语言转 SQL |
| GGUF | GPT-Generated Unified Format，量化模型文件格式 |

### B. 参考

- IVI Foundation SCPI 规范: https://www.ivifoundation.org/
- python-can 文档: https://python-can.readthedocs.io/
- PyVISA 文档: https://pyvisa.readthedocs.io/
- React Flow 文档: https://reactflow.dev/
- Ollama 文档: https://ollama.ai/
