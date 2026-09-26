# 项目看板 — AITestLab

> 项目进展与计划同步看板。本文件用于快速同步各模块状态，详细变更见 `HISTORY.md`，使用说明见 `README.md`。
> 最后更新：2026-08-05 (上午)

---

## 📌 看板总览

| 状态 | 含义 |
|------|------|
| 🔲 待办 (To Do) | 已规划，尚未开始 |
| 🔧 进行中 (In Progress) | 正在开发/调试 |
| ✅ 已完成 (Done) | 已实现并通过验证 |

---

## 🔲 待办 (To Do)

- [ ] **自定义仪表盘**（用户自行定义需要查看的界面）— 设计草案见 `docs/CUSTOM_DASHBOARD_IDEAS.md`
      - [ ] P1：栅格布局 + Widget 注册表 + 基础 Widget（通信窗口/步骤状态/设备状态/执行统计）+ 持久化 + 编辑锁定
      - [ ] P2：解析数值卡片 + 判定结果标记（FAIL 是判定结果，非告警）+ 趋势曲线
      - [ ] P3：内置模板、导入导出、多仪表盘、大屏轮播、响应式断点
      - 已定：不做权限体系；趋势数据复用 `parsed_results` 不单独建表；需大屏模式
- [ ] 端到端集成测试（设备 → AI 生成用例 → 执行 → 报告）
- [ ] API Key 加密存储（当前明文，后端 `ai_service` 有 `TODO: encrypt`）
- [ ] 性能优化（启动速度、大数据量日志渲染）
- [ ] 国际化（中英文界面切换）
- [ ] 打包与安装程序制作
- [ ] 更多仪器驱动适配（示波器/万用表/信号发生器等真实型号）
- [ ] CI/CD 流水线搭建
- [ ] 插件进程隔离沙箱（当前为同步加载，无独立进程）
- [ ] 语音输入对接（当前仅占位，未接浏览器录音上传）

---

## 🔧 进行中 (In Progress)

- [ ] 调试终端多窗口增强（后台 unsolicited 数据轮询稳定性优化）
- [ ] 通信日志大数据量分页与导出性能

---

## ✅ 已完成 (Done) — 最近更新

---

## ✅ 已完成 (Done)

### 基础设施 (M0)
- [x] 后端 FastAPI 框架、配置、数据库（SQLite WAL）、ORM 模型（11 表）
- [x] 前端 Vite + React + TS + Ant Design 脚手架、路由、布局、状态管理
- [x] 通信协议层：SCPI / CAN / 串口 / 以太网
- [x] 设备管理服务与 CRUD API、前端设备管理页
- [x] AI 服务抽象层（Provider 工厂）、对话、用例生成、NL 查询
- [x] 测试用例系统（CRUD + ReactFlow 流程图）
- [x] 测试执行引擎（顺序/并行/条件/循环、变量、钩子、WebSocket 监控）
- [x] 通信日志系统（SQLite + CSV 双写、查询、导出）
- [x] 测试报告系统（Jinja2 / docx、模板管理）
- [x] 插件系统（SDK、管理器、API、前端页、Modbus 示例）

### 调试终端 (2026-07-09 ~ 07-10)
- [x] WebSocket 终端端点 `/ws/terminal/{device_id}` 与前端多窗口终端
- [x] Python 3.8 兼容（`asyncio.to_thread` → `run_in_executor`）
- [x] 串口发送阻塞修复（`read_until` + fallback `read`）

### 日志与诊断 (2026-07-11)
- [x] 通信文件日志 `com_logger.py`（旋转、线程安全）
- [x] 前端时间戳毫秒级显示
- [x] 设备连接诊断（串口权限、Mock 设备）

### 自定义协议插件 + AI 模型配置前端 (2026-07-20 上午)
- [x] `BaseProtocolPlugin` 基类补齐（原被引用但未定义）
- [x] Mini Gateway 100 协议插件（22 条命令，板卡 ID 默认 11，波特率默认 115200）
- [x] `device_service` 路由非标准协议到插件实例
- [x] `POST /api/plugins/{id}/add-device` 按模板一键创建设备
- [x] 前端插件管理：已发现插件一键安装、添加设备
- [x] 前端「模型配置」页（CRUD / 测试 / 设为默认）

### AI 模型增强 + 对话修复 (2026-07-20)
- [x] 新增供应商：**DeepSeek**、**MiniMax**（均 OpenAI 兼容，已加入后端 `ProviderFactory` 与前端 `PROVIDERS`）
- [x] 前端「模型配置」新增**对话测试窗口**（Drawer，可直接与该模型对话验证）
- [x] **修复 AI 助手发送无响应**
- [x] 前端 `tsc --noEmit` 通过

### 修复插件「Plugin class not found」+ 插件 Skill 体系 (2026-07-25)
- [x] 修复 `_load_plugin_module` 返回值语义错误
- [x] 插件类 4 级解析回退 + 文件路径 4 级解析回退
- [x] 插件手册与 Skill 体系（manuals/ + skills/）
- [x] AI 助手集成插件 Skill（前端多选器 + 后端关键词自动检测注入）
- [x] 真实硬件端到端验证

### 修复 AI 模型「连接失败」+ 重置/Key 问题 (2026-07-25 ~ 07-27)
- [x] `ProviderFactory` 新增 `DEFAULT_BASE_URLS`；JoeAI 指向 DeepSeek
- [x] `AIModelConfigUpdate` 增加 `provider`、`model_name` 字段
- [x] `test_model` 返回真实错误；`custom` 缺 Base URL 后端拒绝
- [x] `PROVIDERS.deepseek` 提示更新为 `deepseek-v4-pro / deepseek-v4-flash`
- [x] **修复重置软件进程未完全关闭**：`restart_helper.py` 按端口 + 进程树 kill（解决 reload 模式 worker 残留）
- [x] **修复 API Key 显示为空**：前端编辑时以掩码显示已保存 Key，提交时保留原 Key 不变
- [x] **修复模型测试 400**：动态 placeholder 按供应商提示有效模型名，切换供应商清空旧名

### 测试用例流程图增强 (2026-07-27)
- [x] **AI 驱动流程图生成**：AI 从自然语言需求生成含判断/循环/分支的完整流程图节点
- [x] **流程图编辑器重写**：自定义 ReactFlow 节点（Start/Action/Condition/Loop/End），左侧节点面板拖拽添加
- [x] **判断节点**：菱形渲染，支持条件表达式编辑、true/false 分支
- [x] **循环节点**：for/while 循环，条件表达式编辑
- [x] **可执行代码输出**：`POST /api/testcases/{id}/generate-code` 从流程图生成 Python 测试脚本
- [x] **代码生成器**：遍历流程图拓扑结构，生成完整的 if/else/for/while 和执行步骤的 Python 代码

### 流程图编辑器增强 + 代码生成修复 (2026-08-01)
- [x] **BugFix: 连线选中后无法删除**：边删除过滤条件写反（`e.selected` → `!e.selected`），且添加了 Delete 键直接触发
- [x] **撤销/重做功能**：历史栈（50 步上限），Ctrl+Z 撤销 / Ctrl+Y 重做，工具栏按钮，操作前自动保存快照
- [x] **代码生成器修复**：修复函数体缩进错误（indent=2 → indent=1）、修复 f-string 引号嵌套导致语法错误、修复条件分支汇聚点被错误嵌套在 if 分支内部
- [x] **代码生成测试**：5 类流程图全覆盖测试（顺序/while 循环/中文标签/YesNo/无标签）、API 端到端验证通过、生成代码编译合法

### AI Token 预算与 JSON 输出优化 (2026-08-05)
- [x] **System Prompt 优化**：测试用例生成 prompt 从 ~2500 字符压缩到 ~800 字符，节省约 700 tokens
- [x] **前端默认 max_tokens 提升**：新建模型默认值 2048 → 16384，placeholder 同步更新
- [x] **Chat min_tokens 提升**：对话场景 token 下限 4096 → 16384
- [x] **reasoning_content 提取**：`OpenAIProvider.chat()` 返回结果增加 `reasoning_content` 字段，增强可观测性

### AI 测试用例生成超时修复 + 鲁棒性增强 (2026-08-05)
- [x] **根因定位**：前端 axios 默认超时 30s，DeepSeek V4 推理模型生成用例耗时 60-120s（reasoning_tokens 占比 70%+），前端提前 timeout
- [x] **前端超时优化**：AI 类 API（chat/generate/query/test）切换为 300s 长超时实例；基础 API 超时 120s
- [x] **后端 httpx 超时**：OpenAIProvider SDK 调用超时 120s → `httpx.Timeout(300s, connect=30s)`
- [x] **超时友好提示**：`apiHelper.ts` 检测 ECONNABORTED/ETIMEDOUT，提示"推理模型可能需要 1-3 分钟"
- [x] **日志增强**：`generate_test_cases` 增加耗时 + token 统计日志（含 reasoning_tokens 单独计数）
- [x] **验证**：用户需求"mini-Gateway100 读 DIG1 → CAN1 发送 0x850102 → 超时提示"生成 7 个测试用例验证通过

### 结果解析 + 代码生成修复 + 趋势曲线 (2026-09-26)
- [x] **代码生成修复**：未连线节点被丢弃、无标签分支全判为 true、下发整句自然语言 —— 三处均已修复
- [x] **结果解析能力**：hex/bin/bool/dec/string + 起始位/长度/单位(bit/byte) + 最小值/最大值/等于(或运算)
- [x] **解析配置界面**：用例展开即见步骤，步骤旁配置按钮，粘贴真实响应即时预览解析值与 PASS/FAIL
- [x] **执行页**：显示流程全部步骤（执行前即可见）+ 每步判定结果
- [x] **解析数据曲线**：执行时勾选实时显示；历史趋势从已落库 `parsed_results` 读回，不单独建表；支持大屏模式
- [x] **名称唯一校验**：解析项名称全用例唯一，前后端双重校验，重复提示重新命名
- [x] **语义澄清**：超出上下限 = 判定 FAIL（测试结果），不是系统/设备告警

---

## 🗺️ 近期计划 (Roadmap)

| 优先级 | 计划项 | 说明 |
|--------|--------|------|
| P1 | **自定义仪表盘** | 用户自由拼装监控界面；建议 P1+P2 一起做，接上刚落地的结果解析能力 |
| P0 | 端到端集成测试 | 打通"需求 → AI 用例 → 执行 → 报告"主链路 |
| P0 | API Key 加密 | 生产环境必须，避免明文存储 |
| P1 | 更多仪器驱动 | 真实型号 SCPI 指令集适配 |
| P1 | 插件进程隔离 | 提升稳定性与安全性 |
| P2 | 国际化 | 中英界面 |
| P2 | 打包分发 | 安装程序 / 容器镜像 |
| P3 | CI/CD | 自动化测试与发布 |

---

## 📊 进度统计（估算）

- 核心模块完成度：~85%（9 大模块均已落地，待集成测试与加固）
- 后端 API 端点：~45 个
- 数据库表：11 张
- 已接入 AI 供应商：OpenAI / Anthropic / Ollama / LocalAI / vLLM / 混元 / 通义 / 文心 / **DeepSeek** / **MiniMax** / 自定义
- 自定义协议插件：Modbus RTU（示例）、Mini Gateway 100
