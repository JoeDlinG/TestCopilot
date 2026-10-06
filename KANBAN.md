# 项目看板 — AITestLab

> 项目进展与计划同步看板。本文件用于快速同步各模块状态，详细变更见 `HISTORY.md`，使用说明见 `README.md`。
> 最后更新：2026-10-06

---

## 📌 看板总览

| 状态 | 含义 |
|------|------|
| 🔲 待办 (To Do) | 已规划，尚未开始 |
| 🔧 进行中 (In Progress) | 正在开发/调试 |
| ✅ 已完成 (Done) | 已实现并通过验证 |

---

## 🔲 待办 (To Do)

- [x] **自定义仪表盘**（用户自行定义需要查看的界面）— 设计草案见 `docs/CUSTOM_DASHBOARD_IDEAS.md`
      - [x] P1：栅格布局（`react-grid-layout`，拖拽移动/缩放）+ Widget 注册表 + 基础 Widget（设备状态/执行统计/通信日志/文本备注）+ 持久化 + 编辑锁定
      - [x] P2：**解析数值卡片** + 判定结果标记（FAIL 是判定结果，非告警）+ **趋势曲线** + **判定结果汇总**
      - [x] P3：内置模板（长稳视图/调试视图）、导入导出 JSON、多仪表盘、大屏模式
      - 🔲 尚未做：大屏自动轮播、响应式断点（当前固定 12 列）
      - 已定：不做权限体系；趋势数据复用 `parsed_results` 不单独建表；需大屏模式
      - 已交付：仪表盘**大屏模式**（超大字号 + 深色投屏 + 实时时钟 + 自动刷新 + 无权限）

- [ ] 性能优化（启动速度、大数据量日志渲染）
- [ ] 国际化（中英文界面切换）
- [ ] 打包与安装程序制作
- [ ] 更多仪器驱动适配（示波器/万用表/信号发生器等真实型号）
- [ ] 插件进程隔离沙箱（当前为同步加载，无独立进程）
- [ ] 语音输入对接（当前仅占位，未接浏览器录音上传）
- [ ] **GitHub Issue 增强项**（详见下方 Issues 表，均在 `feature/flow-enhancements` 分支推进）
      - [x] #1 流程图编辑器：节点复制/粘贴 + 节点类型切换（判断⇄循环⇄操作）
      - [x] #5 新增「初始化 / 重置」节点：自定义变量并赋值
      - [x] #4 所有节点支持输入参数与输出返回值（节点间数据串联）

- [x] **Skill 编辑器**：导入 / 修改 / 保存插件 Skill（Markdown）
      - 左侧列表选 Skill，右侧编辑名称 / 协议标识 / 关键词 / 正文；改协议标识自动重命名文件
      - 支持上传或粘贴 `.md` 导入，protocol 从 frontmatter 或文件名推断
      - 后端新增 `POST/PUT/DELETE /api/plugins/skills[/...]`、`POST /api/plugins/skills/import`

- [x] **插件编辑器 + 插件模板**：新建插件自动套用模板与示例
      - 4 套模板（通信协议 / 设备驱动 / 数据解析 / 报告模板），占位符自动填充
      - 在线编辑 `plugins/*.py`，语法校验 + 插件类识别
      - 后端新增 `/api/plugin-editor/*`（templates / files / validate），前端页 `/plugin-editor`

---

## 🐛 GitHub Issues（2026-10-05 从 GitHub 同步）

| Issue | 类型 | 标题 | 状态 |
|-------|------|------|------|
| #6 | bug | PeakCAN USB 连接失败：Windows 下 auto 错误回退 socketcan（WinError 10047） | ✅ 已修复 → v0.4.0；v0.7.1 加固（多候选重试 + 错误可读化 + `diagnose`） |
| #2 | bug | 循环节点缺少「执行命令 / 预期结果」配置（与操作节点不一致） | ✅ 已修复 → v0.4.0 |
| #3 | bug | while 循环缺少进入/跳出条件；条件表达式缺示例与可用变量说明 | ✅ 已修复 → v0.4.0 |
| #1 | enhancement | 流程图编辑器交互增强：节点复制/粘贴 + 节点类型切换 | ✅ 已实现 → v0.5.0（分支 `feature/flow-enhancements`） |
| #5 | enhancement | 新增「初始化 / 重置」节点：自定义变量并赋值 | ✅ 已实现 → v0.6.0（分支 `feature/flow-enhancements`） |
| #4 | enhancement | 所有节点支持输入参数与输出返回值，后续节点可引用前序输出 | ✅ 已实现 → v0.7.0（分支 `feature/flow-enhancements`） |

- **v0.4.0**（bug 修复版，master）：#6 / #2 / #3，备份 tag `backup-2026-10-05`
- **v0.5.0**（增强版，分支 `feature/flow-enhancements`）：#1 节点复制/粘贴（Ctrl+C/V、Ctrl+D）+ 节点类型就地切换
- **v0.6.0**（增强版，同分支）：#5 新增「初始化 / 重置」节点 — 变量定义（名称/类型/初始值/说明，支持增删改序），代码生成输出变量声明
  - 注：变量引用目前在**生成代码**路径生效；运行时执行引擎的变量解析随 #4 统一落地
- **v0.7.0**（增强版，同分支）：#4 输入参数 / 输出返回值 + Skill 编辑器 + 插件编辑器（模板）
  - #4 落地后，变量引用在**生成代码**与**运行时执行引擎**两条路径上行为一致
- **v0.7.2**（增强版，同分支）：延时节点（ms）+ 节点复制按钮 + 用例生成多设备并行拆流程 +
  执行界面双监控窗口 / 按设备多列步骤
- **v0.7.3**（增强版，同分支）：执行界面用例名标题 + 启动/停止按钮；流程图全屏编辑 + 选中节点/连线高亮；
  测试用例重命名 + 一键清空
- 增强功能（#1 → #5 → #4 → Skill/插件编辑器 → 延时/并行执行）在新分支 `feature/flow-enhancements` 上逐个版本推进

## 🔧 进行中 (In Progress)

- Issue #1 流程图编辑器交互增强（节点复制/粘贴 + 节点类型切换）— 分支 `feature/flow-enhancements`

---

## ✅ 已完成 (Done) — 最近更新

### v0.7.3 — 执行界面启动/停止 + 流程图全屏高亮 + 用例重命名/清空（2026-10-06，分支 `feature/flow-enhancements`）

- [x] **测试执行界面**
      - 标题显示**当前执行的测试用例名称**：后端 `executions.py` 新增 `_testcase_names()` 批量查名，
        `/run`、`GET /`、`GET /{id}` 统一回传 `testcase_name`；前端 `TestExecution` 类型补齐字段，列表无名字时按 id 回查
      - 新增「**启动**」按钮：Modal 选测试用例 → `executionAPI.run()` → 自动跟踪该执行
      - 新增「**停止**」按钮：停当前跟踪的执行或列表中运行中的执行；无运行中时提示
- [x] **流程图编辑器**
      - 新增「**全屏 / 退出全屏**」按钮（画布 `position: fixed` 铺满视口，Esc 退出）
      - **选中高亮**：选中节点蓝色外发光描边 + 提升层级；选中连线蓝色加粗 + 流动动画 + 标签高亮
- [x] **测试用例界面**
      - 每个用例支持**重命名**（Modal 输入新名称 → `update(id, {name})`）
      - 新增「**一键清空**」按钮（Popconfirm 二次确认，循环删除并统计失败数）
- [x] 验证：`npx tsc --noEmit` 通过；`python -m compileall app` 通过

### v0.7.2 — 延时节点 / 复制按钮 / 并行流程生成 / 执行界面多列（2026-10-05，分支 `feature/flow-enhancements`）

- [x] **延时节点（单位 ms）**
      - 画布新增「延时」节点（橙色 ⏱），节点弹窗用 InputNumber 配置毫秒数；节点卡片显示 `延时 N ms`
      - **代码生成器**：`delay` 输出 `_cast(_r(...,ctx),'float')` + `time.sleep(/1000)`，并计入 passed 步骤
      - **运行时执行引擎**：新分支 `asyncio.sleep`，支持 `{占位符}` 引用初始化变量 / 前序输出
      - 用例生成 `_description_to_flow` 支持 `flow_type=delay`（`duration_ms`）
- [x] **节点复制入口**：工具栏新增「复制 / 粘贴 / 创建副本」按钮（原有 Ctrl+C / Ctrl+V / Ctrl+D 保留）
- [x] **「测试用例生成」Skill 更新**：新增 `delay` 节点类型；**多设备默认拆分为并行独立流程**
      （不同设备的操作与指令分成各自独立的 test case，`devices_required` 单设备，共享 `并行:<组名>` tag）
- [x] **测试执行界面**
      - 实时通信监控拆成 **A / B 两个独立窗口**（各自设备选择、WebSocket 订阅、暂停/清空，默认不重复选同一设备）
      - 执行步骤按**执行设备**分列显示（列数取决于并行流程用到的设备数，不限 2 列），每列带头部的通过/失败统计
      - 节点编辑弹窗新增「执行设备」选择（绑定到指定设备，留空自动选择）
- [x] 验证：`tsc --noEmit` 与 `npm run build` 通过；延时节点生成代码实测总时长 502 ms（300+200）；
      通过 API 真实执行（start→初始化 `wait_ms=300`→延时 `{wait_ms}`→延时 200→end）→ 3 步 passed、耗时 1.1s

### v0.7.1 — PeakCAN 连接鲁棒性加固（2026-10-05，分支 `feature/flow-enhancements`）

> 针对 Issue #6 的残余问题：Windows 上仍报 `[WinError 10047] 使用了与请求的协议不兼容的地址`，
> 且错误信息里看不到任何可定位的原因。

- **根因**：`connect()` 只“盲试”一个组合，且只捕获 `can.exceptions.CanError`；
  当 SocketCAN 在 Windows 上创建 AF_CAN socket 时 python-can 抛出的是裸 `OSError`，
  直接穿透到 `device_service` → 前端只看到 `[WinError 10047]`。同时 `auto` 检测一旦
  选错接口（例如 `can0` 存在但未 UP）就没有任何回退。
- **修复**（`backend/plugins/peakcan_plugin.py` 1.1.0）：
  - 改为**按序尝试候选列表**：显式 channel（按名字猜驱动）→ 已 UP 的 SocketCAN 接口 →
     其它 SocketCAN 接口 → 检测到的 PCAN 通道 → 平台默认；Windows 上 SocketCAN 永不入选
  - 捕获 `Exception`（不再只捕 `CanError`），**每个候选的失败原因逐条汇总**后抛出
    `ConnectionError`，附平台修复提示 → 裸 `OSError` 不再可能到达 UI
  - 新增 `_explain()`：把 `10047` / `Network is down` / 缺 PCAN DLL 等翻译成可操作的中文原因
  - 新增 `{"action": "diagnose"}` 与 `{"action": "scan"}`（**断开状态可用**），
    返回平台、python-can 版本、候选顺序、检测到的通道与上次失败原因
  - 前端「连接失败」提示因此直接显示“尝试了哪些组合 + 各自为什么失败”
  - 修复手册/Skill 里 `{"action": ...}` JSON 字符串命令在 UI 下发时被当成 `id#data` 解析
    而报 `Invalid CAN string format` 的问题（现自动识别 JSON 对象命令）
- 验证：插件文件语法/结构检查通过；候选顺序逻辑覆盖 Linux/Windows 两条分支
  （受限于无 Windows + 无 PCAN 硬件，实际硬件连接需在设备机上按 `diagnose` 输出确认）

### v0.7.0 — 节点输入/输出 + Skill 编辑器 + 插件编辑器（2026-10-05，分支 `feature/flow-enhancements`）

- [x] **Issue #4：所有节点支持输入参数与输出返回值**
      - 新增 `app/services/flow_context.py`：`{占位符}` 渲染、类型强转、安全表达式求值、
        上下文播种（初始化节点变量）、输入解析（优先取前序同名输出，回退默认值）、输出收集
      - **代码生成器**：注入 `_r / _cast / _p / _out / _cond` 运行时助手；命令与预期结果支持占位符；
        条件/while/进入/跳出条件改用 `_cond()` 以流程上下文为变量求值
      - **运行时执行引擎**：每一步先解析输入、渲染命令/预期，再按 `response / parsed_N / 解析字段名`
        收集输出写入上下文；`step_completed` 广播附带 `context`
      - **前端**：节点编辑弹窗新增「输入参数 / 输出返回值」Form.List（名称/类型/默认值或表达式/说明）
        与「可用变量」标签（点击复制 `{变量名}`）；画布节点显示 in/out 徽标
- [x] **Skill 编辑器**（`/skill-editor`）：列表 → 编辑 → 保存；`.md` 导入；改名即重命名文件
- [x] **插件编辑器**（`/plugin-editor`）：4 套插件模板 + 占位符填充 + 源码编辑 + 语法/插件类校验
- [x] 验证：4 套模板渲染后可编译；Skill 增改删 + 导入实测通过；`tsc --noEmit` 与 `npm run build` 通过

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

### 解析正确性修复 (2026-09-26)
- [x] **每条应答都解析**：原先只解析步骤内最后一条响应，重复下发 50 次的步骤只出 1 个点；
      现 `parsed_results` 改为 `{count, samples[], last}`，每条应答一个采样点
- [x] **空帧识别**：`CAN1,RPLY1,0X`（无数据/超时）不再被当成 ASCII 文本切分
      （此前把 `,`=`0x2C`、`X`=`0x58` 当成了解析值），改为显示 **unknown**、跳过判定
- [x] 解析结果新增 `status`：ok / fail / unknown / error，UI 分别显示 PASS / FAIL / UNKNOWN / ERROR
- [x] **HEX 字段选择**：报文含多个 `0x` 字段时（`1,STD,0X11,0X0102030000000000`）可指定用哪一个，
      避免"全部拼接"导致偏移整体错位
- [x] 解析配置预览显示实际参与切分的字节；代码生成器与运行时判定保持一致

### SCPI 协议 Skill + RIGOL 示波器插件 (2026-09-26)
- [x] **SCPI 通用协议**：下载 SCPI-1999 官方规范（IVI Foundation，卷一 Syntax & Style）到 `docs/scpi/`
- [x] 新增 `scpi` Skill（`backend/plugins/skills/scpi_skill.md`）+ 手册（`backend/plugins/manuals/scpi.md`）：
      命令树/语法规则、参数类型（Bool/Discrete/NR1/NR2/NR3）、单位后缀、
      IEEE488.2 通用命令、状态报告模型、IEEE 明确长度块解析
- [x] **RIGOL 示波器插件** `rigol_oscilloscope`：SCPI over LAN(5555) / USB-TMC / VISA，
      含波形读取（PREamble + DATA + 电压换算）、屏幕截图、测量动作
- [x] 下载 RIGOL 官方编程手册（DS1000Z-E、MSO5000）到 `docs/rigol/`，
      整理为可机读手册 `backend/plugins/manuals/rigol_oscilloscope.md`
- [x] 插件已在后端安装并启用（`plg_9410ada9`），`/api/plugins/discovered` 可见
- [x] 排错修正：查询前清空接收缓冲（避免读到上一次应答）；
      `:MEASure:ITEM? VPP,CHAN1` 这类 `?` 在参数前的命令也能正确识别为查询
- 注：RIGOL 中国区支持站（supportcn.rigol.com）在当前网络不可达，
      手册改由 rigol.com 国际站公开直链下载，**未使用账号登录**

### 自定义仪表盘 (2026-09-26)
- [x] 新表 `dashboards`（layout / widgets / data_source 只存**描述**，不存数值）+ CRUD / 复制 / 设为默认 / 导入导出
      首次访问自动内置两个模板：**长稳视图**（解析卡片+趋势+判定汇总+统计）、**调试视图**（设备+统计+通信日志）
- [x] `GET /api/dashboards/snapshot`：一次请求拉齐所有 Widget（设备 + 执行统计 + 解析序列 + 判定汇总），
      N 个 Widget 只轮询一次而不是 N 次
- [x] 解析趋势逻辑抽到 `app/services/trend_service.py`，`/api/testcases/{id}/parsed-trend` 与仪表盘共用；
      点数据新增 `step_label` 便于定位来源步骤
- [x] **7 种 Widget**：
      - **解析数值卡片**：最新值大字号 + PASS/FAIL/空帧判定徽标，越界变红，附 min/max/均值/采样数/FAIL 次数
      - **趋势曲线**：按 (执行, 步骤, 第几次应答) 对齐铺点，FAIL 点标红，可加参考上下限参考线
      - **判定结果汇总**：判定总数/PASS/FAIL/空帧 + 通过率进度条 + 分字段表格 + 最近 FAIL 明细（含原因与步骤）
      - 设备状态 / 执行统计 / 通信日志 / 文本备注（Markdown）
- [x] 交互：编辑/锁定（锁定后不可拖动）、组件库抽屉、每个 Widget 独立配置、删除/复制、
      多仪表盘切换、新建/复制/设为默认/导入/导出 JSON、大屏模式（深色投屏 + 自动刷新）
- [x] 删除默认仪表盘后自动把最早的一个补为默认，保证始终有落地页
- [x] 验证：`tsc --noEmit`、`npm run build` 通过；`/dashboards/snapshot` 实测返回 813 个判定点
      （ok 49 / fail 13 / unknown 751）；Chromium 无头截屏 4 张确认渲染与交互正常

### 仪表盘大屏模式 (2026-09-26)
- [x] 仪表盘新增「大屏模式」入口：全视口深色投屏布局、超大字号统计卡（设备/用例/执行/通过率）
- [x] 实时时钟 + 自动刷新（5/10/30/60 秒可选）+ 立即刷新
- [x] 调用浏览器全屏 API（被拒绝时仍以全视口覆盖层渲染）；ESC 退出自动同步状态
- [x] **无权限控制**，任意用户均可进入投屏

---

### 仪表盘实时刷新 + 配置弹窗修复 + 端到端集成测试 + CI/CD (2026-09-27)
- [x] **自定义仪表盘实时刷新**：Widget 订阅运行中执行的 WebSocket（`/ws/executions/{id}`），`step_completed` / `execution_completed` / `step_failed` / `execution_stopped` / `execution_error` 事件驱动防抖刷新快照；保留 HTTP 轮询作为兜底心跳
- [x] **齿轮配置弹窗修复**：操作按钮（设置/复制/删除）移出拖拽手柄并加 `draggableCancel`，修复点击无响应；标题栏作为唯一拖拽手柄
- [x] **端到端集成测试**：新增 `Test/e2e_integration_test.py`，打通「设备(Mini Gateway 100) → AI 生成用例 → 执行 → 报告」全链路；实测生成 6 个用例、执行 `status=passed`、报告 HTML 可下载
- [x] **CI/CD 流水线**：新增 `.github/workflows/ci.yml`（后端导入/编译校验 + 前端 `npm ci` + `npm run build` + 构建产物上传）、`.github/workflows/e2e.yml`（手动触发，需自托管 Runner + 设备 + AI Key）
- [x] 全部改动已提交并推送至 GitHub `master`

### 稳定性 / 安全 / 体验优化 (2026-09-27)
- [x] **调试终端多窗口增强（后台轮询稳定性）**：监控循环加宽异常兜底（单条异常不再导致监控进程永久退出）；支持自定义轮询间隔；引入多窗口监听引用计数，单个窗口 `stop_receive` 不再误杀全设备共享监控
- [x] **通信日志导出性能**：CSV 导出改为分批游标拉取，避免大数据量一次性全量加载
- [x] **API Key 加密存储**：新增 `app/core/crypto.py`（Fernet），建/改模型时加密、调用时解密，并对存量明文兼容回退；`ai_service` 的 `TODO: encrypt` 已消除
- [x] **判定结果汇总表格时间戳**：FAIL 列表新增可见时间戳（原仅在 tooltip 显示）

## 🗺️ 近期计划 (Roadmap)

| 优先级 | 计划项 | 说明 |
|--------|--------|------|
| P1 | **插件编辑器增强** | 模板自定义（用户保存自己的模板）、插件一键安装/重载、手册（manuals）编辑 |
| P1 | 节点 I/O 可视化 | 画布上连线标注传递的变量、未定义变量实时提示 |
| P1 | **自定义仪表盘增强** | 大屏自动轮播、响应式断点、Widget 内实时 WS 订阅 |
| P0 | 端到端集成测试（已完成） | 打通"需求 → AI 用例 → 执行 → 报告"主链路 |
| P0 | API Key 加密（已完成） | 生产环境必须，避免明文存储 |
| P1 | 更多仪器驱动 | 真实型号 SCPI 指令集适配 |
| P1 | 插件进程隔离 | 提升稳定性与安全性 |
| P2 | 国际化 | 中英界面 |
| P2 | 打包分发 | 安装程序 / 容器镜像 |
| P3 | CI/CD（已完成） | 自动化测试与发布 |

---

## 📊 进度统计（估算）

- 核心模块完成度：~90%（9 大模块均已落地；端到端集成测试与 CI/CD 已补齐）
- 后端 API 端点：~45 个
- 数据库表：11 张
- 已接入 AI 供应商：OpenAI / Anthropic / Ollama / LocalAI / vLLM / 混元 / 通义 / 文心 / **DeepSeek** / **MiniMax** / 自定义
- 自定义协议插件：Modbus RTU（示例）、Mini Gateway 100
