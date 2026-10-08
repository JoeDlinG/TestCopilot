# AITestLab — 项目工作记录

> 记录从项目启动到当前的所有关键工作、里程碑和技术决策。

---

## 2026-10-08: 修复「AI 生成测试用例必失败」+ PeakCAN 自回环 + 新增执行日志（v0.8.5）

> 对照 GitHub Issue #13 / #14 / #15。核心结论：**生成失败是前端 bug，不是后端**。

### 1. Issue #13「生成测试用例必失败」——真正根因在前端（不是 NaN/Infinity）

- **根因**：`AIChat.tsx` 的 `loadDevices()` 用 `extractData(res, [])` 取 `/api/devices/` 的返回，但该接口是**分页**结构
  `{data: {items, total}}` → `devices` 被赋成**对象**；随后 `devicePayload()` 调 `devices.map()` 抛
  `TypeError: devices.map is not a function`，异常发生在**调用生成 API 之前**，被 catch 成默认文案
  「生成测试用例失败」。这正是「对话可以、生成必失败」的原因。
- **修复**：`loadDevices` 改用 `extractItems(res)`（返回 `data.items` 数组）；`devicePayload` 加 `Array.isArray` 兜底。
- **验证**：后端 `/api/ai/generate-testcases` 用用户截图里的原始需求实测 **HTTP 200 / 2 个用例**（后端本身没问题）。

### 2. Issue #13 防御：后端 NaN/Infinity 序列化

- `ai_service._sanitize_json()`：递归把 `NaN/Infinity` 换成 `null`，避免 Starlette JSON 编码（`allow_nan=False`）在
  try/except 之外抛 500。

### 3. Issue #15：前端错误提示退化

- `apiHelper._errorMessage()` 现在能解析：422 的**数组 detail**（拼 `loc.msg`）、**非 JSON 错误体**（脱 HTML 后截断），
  以及本地 JS 异常——不再一律退化成默认文案。

### 4. Issue #14：PeakCAN 自回环（v0.8.4 已修，此处归档）

- `peakcan_plugin.receive()`：非 loopback 模式跳过 `is_rx=false` 的自回环帧，发送方不再「收到」自己发的报文，
  也不再被当作应答参与 PASS/FAIL。验证：跑周期发送用例，自回环帧 **+0**。

### 5. 新增执行日志（便于事后分析）

- 目录结构（`backend/logs/`）：
  - `program/program_global.log` — 全局程序执行日志（root logger，**10MB 轮转**）
  - `communication/<device_id>/comm_*.log` — 全局通信日志（已有，10MB 轮转）
  - `executions/<execution_id>/` — **每次执行一个文件夹**：`program_*.log`（程序）+ `communication_*.log`（通信），均 10MB 轮转
- 新增 `app/services/program_logger.py`；`main.lifespan` 安装全局 handler；`execution_service` 记录每步；
  `device_service.send_command` 把收发镜像到该次执行的通信日志。
- 新增浏览 API：`GET /api/logs/program/files`、`GET /api/logs/executions/{id}/files`、
  `GET /api/logs/executions/{id}/file/{name}`。
- 验证：跑一次执行 → `logs/executions/exec_xxx/` 生成 `program_001.log` + `communication_001.log`；
  `logs/program/program_global.log` 同步增长。

### 验证汇总

| 项目 | 结果 |
|------|------|
| 后端生成（用户原始需求） | HTTP 200，2 个用例 |
| 前端 `loadDevices`/`devicePayload` | `npx tsc --noEmit` 通过；逻辑改用 `extractItems` |
| PeakCAN 自回环 | 执行后自回环帧 +0 |
| 执行 | `tc_7653d5b2 passed 4/4` |
| 日志 | per-execution 文件夹 + 全局程序日志均生成，10MB 轮转 |
| `python -m compileall app` | 通过 |

---

## 2026-10-08: PeakCAN skill 补「禁止生成 open/close」+ 真实硬件端到端跑通（v0.8.3）

### skill 更新（`peakcan_skill.md`）

- 通道的打开/关闭由平台「设备管理」负责，插件只支持 `send / send_periodic / stop_periodic / receive / scan / diagnose`
  六个 action；**禁止生成 `open` / `close` 步骤**（会报「未知 action」）。已在「连接配置」「测试场景模板」
  「命令必须写进结构化字段」三处写明。

### 真实硬件端到端验证（补 v0.8.2）

| 用例 | 结果 |
|------|------|
| PeakCAN 周期发送（`send_periodic` 200ms → 3s 窗口 → `stop_periodic`） | ✅ 4/4 通过 |
| MG100 接收（`CONFIG RX 0X20` → `TSTRT` → loop 10× `MSGRX`） | ✅ 11/12 通过，**读到 `0X010203`**（= PeakCAN 发的 ID 0x20 / data 01 02 03） |

> 导入前剔除了 PeakCAN 用例里 AI 生成的 `open`/`close` 两步（插件不支持），其余步骤一次跑通。

---

## 2026-10-07: MG100 RX 过滤/监控逻辑 + 收发时序对齐写入生成 skill（v0.8.2）

> 联调已跑通（PeakCAN 发 ↔ MG100 收），本轮把两条实测结论固化进 skill/prompt，让 AI 生成即对齐。

### 1. MG100 内在逻辑写入 `mini_gateway100_skill.md`（新增 2.4.1）

- 定义 RX 消息 ID（`@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;`）后，MG100 **只过滤并锁存该 ID**，且**只在执行
  `MSGRX` 时才读取返回**——之前到站的帧不会主动上报，必须「发一次 MSGRX 取一次」。
- 未定义任何 RX ID 时，MG100 会**监控总线上所有报文**（不做 ID 过滤）。

### 2. 收发时序对齐写入生成 skill（`ai_service.py` 系统提示词 + `mini_gateway100_skill.md` 生成要求）

- 新增 `SEND/RECEIVE TIMING ALIGNMENT` 规则：接收/轮询命令（如 `MSGRX`）只读「执行那一刻」总线上的报文，
  **禁止「先发一次、再读一次」的串行时序**；发送方必须周期/重复发送（PeakCAN `send_periodic`、MG100
  `PROCESS` MSGTX），接收方在同一窗口内反复轮询，让收发时间重叠。
- MG100 skill 的生成要求补一条跨设备收发联调要点（同上）。

### 验证（真实生成）

| 项目 | 结果 |
|------|------|
| `compileall app` | 通过 |
| skill 内容加载 | `RX 过滤与读取时序` / `只在执行 MSGRX 时才读取返回` / `监控总线上所有报文` 均已注入生成上下文 |
| 真实生成（DeepSeek，需求「PeakCAN 每 200ms 发 0x20，MG100 接收显示」） | PeakCAN 侧 `send_periodic(period_ms=200)` + 3s 发送窗口；MG100 侧 `CONFIG RX 0X20` + **loop 反复 MSGRX**，两者同属并行组「并行:PeakCAN-MG100-CAN周期收发」——时序对齐 |

---

## 2026-10-07: BugFix — 调试终端 python-can 语法被当 CAN 字符串报错（v0.8.1）

> 现象：调试终端输入 `bus.send_periodic(can.Message(arbitration_id=0x20, ...), 0.2)` 报
> `Invalid CAN string format: 'bus.send_periodic(...)'`，PeakCAN 一条都没发（命令根本没进发送逻辑）。

### 根因

PeakCAN 插件 `send()` 只认三种输入：JSON 字典（可带 `action`）、`"ID#DATA"` 字符串、以及 `{` 开头的 JSON 字符串。
用户（或某个没按 skill 写的步骤）在调试终端直接输入 **python-can 库调用**（`bus.send_periodic(...)` / `bus.send(...)` /
`bus.recv(...)` / `can.Message(...)`），这类字符串不是 `{` 开头、也不含 `#`，于是被 `_parse_can_string` 当 CAN 字符串
解析 → 抛 `Invalid CAN string format`，命令在进发送逻辑前就死了。

### 修复（彻底：翻译层 + 执行链识别）

- **PeakCAN 插件 `send()` 顶部新增 `_translate_python_can()`**：识别 python-can 风格调用并改写成插件自己的 JSON 命令——
  - `bus.send_periodic(can.Message(arbitration_id=0x20, data=[...]), 0.2)` → `{"action":"send_periodic", ..., "period_ms": 200.0}`
    （周期按秒参数 × 1000，**不是写死 200ms**，`0.5`→500ms、`0.1`→100ms）
  - `bus.send(can.Message(...))` / `can.Message(...)` → 单发
  - `bus.recv(timeout=2.0)` / `bus.recv()` → `{"action":"receive", ...}`
  - 支持 `bus.` / `self._bus.` 前缀、`0x` 十六进制 ID、`data=[...]` 列表、`is_extended_id/is_fd/dlc` 等关键字；
    用括号平衡扫描处理 `can.Message(...)` 嵌套，不误伤普通文本。
- **执行引擎同步识别**：`_extract_commands` 新增 `_python_can_commands()`（括号平衡提取、去重嵌套 `can.Message`），
  `_infer_protocol` 识别 python-can 调用 → `peakcan`（保证执行引擎按协议选到 PeakCAN，不再落空）。

### 验证

| 项目 | 结果 |
|------|------|
| 单元（翻译） | `bus.send_periodic`→`period_ms=200`；`bus.send`→单发；`bus.recv`→receive；`self._bus.send_periodic(...0.5)`→`500ms` |
| 提取去重 | 文本里 `bus.send_periodic(can.Message(...), 0.2)` 只提取 1 条命令（不再把内层 `can.Message` 当第二条） |
| 调试终端 WebSocket（真实 can0） | 原报错命令现在返回 `periodic_started`；`bus.send`→`sent`；`stop_periodic`→`periodic_stopped` |
| 回环自检（loopback，真实硬件） | 单发帧回环 `data=112233` 成功收到；周期发每 200ms 连续回环 3 帧 `32 0102`——帧确实出/回适配器 |
| `python -m compileall app plugins/peakcan_plugin.py` | 通过 |

> 备注：`can0` 控制器 `berr-counter tx≈100 rx=0`（ERROR-WARNING）——发出的帧没有节点应答。回环自检已证明
> 软件/驱动链路正常，此残留属**硬件层**问题（对端 MG100 未上总线 / 波特率 / 终端电阻 / 监听模式），
> 需在硬件侧排查；软件侧"命令不被识别"的 bug 已彻底修复。

---

## 2026-10-06: 修复 PeakCAN「只收不发」+ 生成设备丢失 + 运行时按图执行（v0.8.0）

> 分支 `feature/flow-enhancements`。问题根源：用例生成的 PeakCAN 分支设备栏为空、执行时 PeakCAN 一条报文都没发。

### 根因链（结论：是生成/执行链路的 bug，不是 PeakCAN 插件/skill）

1. **设备信息在"生成→流程图"被丢弃**：`testgen_service._description_to_flow` 把 `device_id` 写死 `None`，
   AI 输出的 `device_type`/`devices_required` 被忽略，前端也从不传 `available_devices` → PeakCAN 节点设备栏为空。
2. **PeakCAN 命令无法被识别**：`_extract_commands` 只认 MG100 的 `@NN_CMD;`，PeakCAN 的
   `{"action":"send",...}` / `"123#11223344"` 提取不到 → `commands=[]` → 步骤被当"无设备指令"跳过。
3. **设备解析静默错发**：`_resolve_device` 无 device_id 时回退 `devices[0]`（可能发给 MG100）→ PeakCAN 一条不发，
   而 MG100 在总线上发帧，PeakCAN 作为监听端"收到了消息"（日志全是 RECV、无 SEND）。
4. **运行时不执行 loop**：`loop` 节点直接 `passed / "Loop completed"`，"每 200ms"周期语义根本没落地（还假通过）。

### P0（链路正确性）

- **生成回填设备**：`testgen_service` 新增 `_match_device` / `_device_hints`，把 `device_type` / 设备名 /
  `devices_required` 映射到真实设备，写入节点 `config.device_id` + `device_protocol`；`import` 路径无设备列表时
  回退查询数据库里的设备；条件/循环的 body、merge 占位节点同样带设备。前端 AIChat 生成/导入时传递 `available_devices`。
- **命令识别**：`_extract_commands` 新增 `_JSON_CMD_RE`（校验 `action`/`arbitration_id` 等键）+ `"ID#DATA"` 字符串；
  `_infer_protocol` 支持 JSON/`ID#DATA` → `peakcan`。
- **设备解析**：`_resolve_device` 按「device_id → 推断协议 → 任意设备」顺序；推断出协议但无匹配设备时返回 None，
  由 `_missing_device_hint` 给出明确失败原因（"未找到已连接的 peakcan 设备，命令未下发"），不再静默错发。

### P1（周期发送参数化 + skill 同步）

- **PeakCAN 插件**：新增 `send_periodic` / `stop_periodic` action；`period_ms` 是**参数**（按用例需求填，非写死 200ms），
  支持 `count`（发满自动停）与 `key`（精确停止）；抽出 `_build_message` 复用，断开时自动停止所有周期发送。
- **skill**：`peakcan_skill.md` 增周期发送章节 +「命令必须写进 `parameters.command`，禁止写 python-can 伪代码」；
  `mini_gateway100_skill.md` 周期场景改为「默认优先 PROCESS、但非必须」，并注明 PROCESS 槽位有限（最多 32 个进程）。
- **prompt**：`ai_service` 系统提示词新增 COMMAND RULES（命令结构化、禁止库调用伪代码、周期用设备周期能力且
  `period_ms` 按需求填）。

### P2（运行时按 edges 执行，与 codegen 对齐）

`_execute_flow` 从"扁平顺序遍历"改为**沿 edges 走图**：`condition` 真正走 true/false 分支，
`loop` 真正按次数（for）或条件（while）迭代循环体；节点重复访问复用同一步骤行（带"第 N 轮"标记），
`step_index` 仍是节点在流程中的位置（UI 步骤列表不变）；带 `MAX_NODE_EXECUTIONS` / `MAX_LOOP_ITERATIONS` 防死循环上限。
`start_execution` 现在同时读取并传入 `flow.edges`。

### 验证（真实硬件：Mini Gateway 100 + PeakCAN USB）

| 项目 | 结果 |
|------|------|
| P0/P2 纯逻辑（命令识别/协议推断/设备匹配/循环次数/分支选择） | 20 项断言全过 |
| 线性 MG100 用例（回归） | `passed`（7 通过 / 0 失败 / 8 步） |
| 循环节点（for 3 轮，body 发 `@11_HELLO;`） | `passed`，loop 显示"循环共执行 3 轮"，body 显示"第 3 轮 @11_HELLO; -> 2,11,12" |
| 条件节点（`1>0` / `1<0`） | 只执行对应分支，另一分支跳过 |
| PeakCAN 单发 | `{"status":"sent","arbitration_id":32,...}`（命令正确路由到 PeakCAN） |
| PeakCAN 周期发（`period_ms=500`，非 200） | 返回 `period_ms: 500.0`，`stop_periodic` 生效 |
| `python -m compileall app` / `npx tsc --noEmit` | 均通过 |

> 备注：测试时曾出现一次 MG100 "no data" 报错，根因是**两个后端进程同时抢占 `/dev/ttyACM0`**（复现实例未关），
> 关闭多余实例后恢复正常——非代码问题。

---

## 2026-10-06: BugFix — 启动执行后不实际运行（v0.7.4）

> 现象：点「启动」后执行一直是 running、步骤与终端（实时通信监控）**一条消息都没有**，
> `test_step_results` 为 0 行。v0.7.3 引入的回归。

### 根因：后台任务与请求共用一个 AsyncSession

v0.7.3 为了在标题显示用例名，在 `POST /api/executions/run` 里**在 `asyncio.create_task()` 之后**
又 `await db.execute(select(TestCase...))` 查用例名。而后台任务 `_run_execution` 拿到的 `db`
正是同一个**请求作用域**会话（`Depends(get_db)`），它内部用 `async with db as session:` —— 退出时
会 `close()`。两者并发 → SQLAlchemy 抛出：

```
IllegalStateChangeError: Method 'close()' can't be called here;
method '_connection_for_bind()' is already in progress ... (isce)
```

异常发生在**第一个步骤落库之前**，被 `_run_execution` 的兜底 `except` 吞掉（只广播了一条
`execution_error`，而 UI 没订阅该事件）→ 表现为「启动成功但一直空转」，执行记录永远卡在
`running`，「启动」按钮也因此一直禁用。
数据库佐证：10:30 之后的 5 次执行 `step_results` 均为 0 行，而改动前 09:39 的那次有 12 行。

### 修复

- **`execution_service.start_execution`**：后台任务改为使用**自己的会话** `async_session()`，
  不再与请求会话共享 —— 请求处理器随后做什么都不会再与任务打架
- **`_run_execution`**：拆成 `_run_execution`（包装，负责 `finally: await db.close()`）
  + `_execute_flow`（原逻辑），会话生命周期由任务自己负责
- **`executions.py`**：`_testcase_names()` 移到 `start_execution()` **之前**（用 `data.test_case_id`
  查），请求处理器在 `create_task` 之后不再触碰 `db`
- **`main.py` 启动**：新增 `execution_engine.reset_stale_executions()` —— 把上次进程留下的
  `running` 执行标记为 `error`（"服务重启，执行中断"），并把卡在 `running` 的用例改回 `draft`；
  否则重启后「启动」按钮会永久禁用

### 验证（真实硬件 Mini Gateway 100 / `dev_7d2cc656`，`/dev/ttyACM0` @115200）

| 项目 | 结果 |
|------|------|
| 修复前复现 | `exec_8f7a7f08` → 0 条 `step_results`，日志报 `IllegalStateChangeError` |
| 修复后 API 执行 | `passed`，9 步 8 通过 1 跳过，每步都有真实应答（如 `@11_MSGRX=CAN1,RPLY1,8; -> CAN1,RPLY1,0X`） |
| WebSocket `/ws/executions/{id}` | 20 条事件（`step_started` / `step_completed` / `execution_completed`） |
| WebSocket `/ws/devices/{id}`（终端） | 21 条事件（`command_sent` / `command_response`）—— 终端不再空白 |
| 停止 | `POST /{id}/stop` → `stopped`，步骤已落库 |
| 停止后再次启动 | 再次 `passed`（8 通过 / 0 失败 / 9 步） |
| 启动清理 | 3 条卡住的 `running` 执行被标记为 `error` |
| `npx tsc --noEmit` / `python -m compileall app` | 均通过 |

---

## 2026-10-06: 执行界面启动/停止 + 流程图全屏与选中高亮 + 用例重命名/一键清空（v0.7.3）

> 分支 `feature/flow-enhancements`

### 1. 测试执行界面（Executions.tsx）

- **标题显示当前执行的用例名称**：后端 `executions.py` 新增 `_testcase_names()`（一次 `select` 批量查
  `TestCase.id/name`），`/run`、`/`、`/{id}` 三个接口统一回传 `testcase_name`；前端类型
  `TestExecution` 补齐 `testcase_id / testcase_name / started_at / completed_at / total_steps /
  passed_steps / failed_steps`。列表没有名字时前端按 `testcase_id` 逐个拉取补全（带缓存）
- **启动 / 停止按钮**：
  - 「启动」打开 Modal，从 `testCaseAPI.list()` 选一个用例 → `executionAPI.run(caseId)`
    → 成功后自动选中该执行开始跟踪
  - 「停止」优先停当前跟踪的执行，否则停列表里第一个 `running` 的执行；没有运行中的执行给提示
  - 原「刷新」按钮保留，三个按钮同处工具栏

### 2. 流程图编辑器（TestFlowEditor.tsx）

- **全屏编辑**：工具栏新增「全屏 / 退出全屏」按钮，画布容器切到 `position: fixed; inset: 0`
  铺满视口（脱离页面 header/侧边栏），Esc 退出
- **选中高亮**：`useMemo` 派生 `displayNodes / displayEdges` 传给 ReactFlow ——
  选中节点加 3px 蓝色外发光描边并提升 `zIndex`；选中连线改蓝色加粗（`strokeWidth: 3`）+ `animated`
  流动效果，标签同步高亮；未选中连线统一 `strokeWidth: 2`

### 3. 测试用例界面（TestCases.tsx）

- **重命名**：列表每个用例新增「重命名」按钮 → Modal 输入新名称 → `testCaseAPI.update(id, {name})`，
  空名称拦截
- **一键清空**：工具栏「清空」按钮 + `Popconfirm` 二次确认（显示将删除的数量），
  循环调用删除接口，统计失败数量并提示（部分失败会提示刷新重试）

### 验证

| 项目 | 结果 |
|------|------|
| `npx tsc --noEmit` | 通过 |
| `python -m compileall app` | 通过 |
| 后端接口 | `/run`、`GET /`、`GET /{id}` 均返回 `testcase_name` |

---

## 2026-10-05: 延时节点 + 节点复制入口 + 并行流程生成 + 执行界面多列（v0.7.2）

### 1. 延时节点（单位：毫秒）

- 画布：新增「延时」类型节点（橙色、⏱ 图标），卡片直接显示 `延时 N ms`；
  节点编辑弹窗用 `InputNumber`（addonAfter `ms`）配置时长
- **代码生成器**（`codegen_service.py`）：新增 `delay` 分支 ——
  `_delay_ms = _cast(_r(..., ctx), 'float')` → `time.sleep(max(0, _ms)/1000)` → 计入 `results['passed']`
- **运行时执行引擎**（`execution_service.py`）：新增 `delay` 分支，`{占位符}` 用流程上下文渲染后
  `asyncio.sleep(ms/1000)`，`actual` 记录实际延时毫秒数
- 用例生成（`testgen_service._description_to_flow`）：`flow_type=delay` → 延时节点（`duration_ms`）

### 2. 节点复制（可视化入口）

原有 Ctrl+C / Ctrl+V / Ctrl+D 只有快捷键、界面上不可见 —— 工具栏补「复制 / 粘贴 / 创建副本」三个按钮
（逻辑复用既有 `handleCopy / handlePaste / handleDuplicate`，带 Tooltip 说明快捷键）。

### 3. 「测试用例生成」Skill：多设备默认拆成并行独立流程

`ai_service.generate_test_cases` 的系统提示词更新：

- 新增 `delay` 节点类型（要求设备稳定时间用延时节点表达，不要只写在描述里）
- 新增 **MULTI-DEVICE RULE**：涉及 2 台及以上设备时，**不同设备的操作与指令必须拆成互相独立的
  test case**（每台设备一条并行流程），`devices_required` 只填一台，用 `并行:<组名>` tag 归组，
  各流程自带 start→steps→end，需要同步时用延时节点而非跨设备依赖

### 4. 测试执行界面

- 实时通信监控由 1 个窗口改为 **A / B 两个独立窗口**：抽出 `useDeviceMonitor(devices, slot)` hook
  （设备选择 + WebSocket + 暂停/清空各自独立），两个窗口默认选中不同设备（已连接的优先）
- 执行步骤状态改为**按执行设备分列**：列数取决于实际用到的设备数量（不限 2 列），
  每列带通过/失败/步数统计；抽出 `StepList` 组件复用渲染
- 流程节点编辑弹窗新增「执行设备」选择（`config.device_id`），这样“按设备分列”才有数据来源；
  留空时仍由执行引擎 `_resolve_device` 自动挑选已连接设备

### 验证

| 项目 | 结果 |
|------|------|
| `npx tsc --noEmit` / `npm run build` | 通过 |
| 延时节点生成代码后执行（300+200 ms） | 实测 502 ms，`passed=2` |
| API 真实执行（初始化 `wait_ms=300` → 延时 `{wait_ms}` → 延时 200） | 3 步 passed，1.1 s，占位符解析正确 |
| `_description_to_flow` 延时分支 + 提示词关键词 | 断言通过 |
| `python -m compileall app` | 通过 |

---

## 2026-10-05: PeakCAN 插件真实硬件联调（收发链路跑通）

> 硬件：PCAN-USB FD（USB `0c72:0012`），SocketCAN `can0` @ 500 kbps

### 环境验证

- 插件 `connect()` 走 `socketcan/can0` 连接成功；标准帧 / 字符串简写 /
  扩展帧发送均返回 `status=sent`，`receive()`、`disconnect()` 正常
- REST 链路端到端通过：`POST /api/devices/connect` → `/{id}/command` →
  全局接收监听抓到帧并落库 `communication_logs`（同时 WebSocket 广播）
- 物理层结论：`bus_state.rx=0 / tx=128` → **总线上没有任何节点应答**，
  需在硬件侧确认：对端上电、波特率一致、两端各一个 120Ω 终端电阻、CAN_H/CAN_L 未接反

### 代码修复

- `get_status()` / `diagnose()` 新增 `bus_state`（解析 `ip -details link show`）
  与 `bus_hint`：直接给出 ERROR-PASSIVE / BUS-OFF 的排查建议与复位命令
- 错误帧处理：默认 `skip_error_frames=true`，错误帧不再伪装成正常响应；
  显式开启时返回带 `error_desc`（中文解码：无 ACK / 发送 ERROR-PASSIVE / BUS-OFF …）
- 新增 `loopback` 自检开关：总线上没有对端时，用内核回环自发自收验证整条链路
- `_usb_hint()`：pyusb 枚举 USB，区分「没插 PEAK 设备」与「插了但内核模块未加载」
- 文档同步：`docs/PEAKCAN_PLUGIN.md`（配置项、返回字段、总线状态表）

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

## 2026-10-04 ~ 2026-10-05: Windows 兼容改造 + 打包为 Windows 安装包

### 背景

项目原先在 Linux 下开发，存在多处硬编码的 POSIX 路径与进程管理逻辑；本次目标：
① 让后端/前端/插件/测试在 Windows 上可运行；② 依赖可在 Python 3.13 上安装；
③ 产出开箱即用、内含全部测试运行环境的 Windows 安装包。

### 一、Windows 兼容修复（5 处硬编码）

| 文件 | 问题 | 修复 |
|------|------|------|
| `backend/app/communication/__init__.py` | `SerialInterface.connect()` 用 `os.path.exists(port)` 校验串口，Windows 下 COM 口不是文件 → 合法端口被拒 | 按平台分支：NT 用正则 `^COM\d{1,3}$` 校验后交 pyserial；POSIX 保持 `os.path.exists` |
| `backend/app/main.py` | `/api/system/restart` 用 `start_new_session=True` + 日志写死 `/tmp` | Windows 改用 `CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS`；日志路径改 `tempfile.gettempdir()` |
| `backend/restart_helper.py` | 依赖 `pkill`/`ss`/`lsof`/`fuser`/`killpg`，Windows 全不可用 | 重写跨平台：端口探测用 `netstat -ano`，杀进程树用 `taskkill /F /T`，按命令行匹配用 PowerShell `Get-CimInstance Win32_Process`；支持 frozen 重新拉起 exe |
| `backend/plugins/mini_gateway100_plugin.py`、`example_plugin.py` | 默认串口写死 `/dev/ttyACM0`、`/dev/ttyUSB0` | 新增 `_default_port()`：NT 返回 `COM3`，POSIX 保持原路径 |
| `backend/plugins/rigol_oscilloscope_plugin.py` | 截图默认路径 `/tmp/...`，Windows 无 `/tmp` | 改 `tempfile.gettempdir()/aitestlab_rigol/screen.png` |

### 二、依赖可在 Python 3.13 安装（`backend/requirements.txt`）

- 移除未被任何模块引用的 `pandas<2.0` / `numpy<1.25`（旧 pin 在 Py3.13 无 wheel）
- `sqlalchemy 2.0.23 → 2.0.36`（2.0.23 在 Py3.13 触发 TypingOnly 断言）
- `pydantic 2.5.2 → 2.10.6`、`pydantic-settings 2.1.0 → 2.7.1`（旧版依赖 pydantic-core 2.14.5，Py3.13 无预编译 wheel，强制源码编译 Rust）

### 三、前端类型修复（`tsc` 严格模式）

TypeScript 5.9 + `noImplicitAny` 下 13 处回调参数隐式 `any` → 全部补显式类型（`WidgetConfigDrawer.tsx`、`ResultParserConfig.tsx`、`CustomDashboard.tsx`、`Executions.tsx`、`Logs.tsx`、`ModelConfig.tsx`），前端 `build` EXIT=0。

### 四、独立运行 / 打包支持

- `backend/app/core/config.py`：新增 `_bundled_dir()`，frozen 时插件/静态资源从 `sys._MEIPASS` 解析；CORS 增加 `localhost:8000` / `127.0.0.1:8000`；新增 `STATIC_DIR`
- `backend/app/main.py`：挂载 `static/` 托管前端产物 + SPA fallback，使单进程 `:8000` 同时提供 UI 与 API
- `backend/run.py`：frozen 时 `chdir` 到 `%LOCALAPPDATA%\AITestLab`（可写数据目录），传 app 对象 + `reload=False`；dev 仍用 import string + `reload=True`；支持 `--restart-helper` 参数；启动后自动打开浏览器
- 新增 `backend/aitestlab.spec`（PyInstaller onedir，hiddenimports 覆盖 uvicorn/fastapi/sqlalchemy/pydantic/anyio/httpx/pyvisa/can/serial win32 后端/aiosqlite 等，datas 打包 static+plugins+manuals+skills+文档）
- 新增 `backend/make_icon.py`（PIL 生成 `static/aitestlab.ico`）
- 新增 `backend/aitestlab.nsi`（NSIS 脚本，安装到 `%LOCALAPPDATA%\Programs\AITestLab`，含开始菜单/桌面快捷方式与卸载器）

### 五、测试与验证

- 后端 `compileall` + `import app.main` 通过；服务冒烟：`/api/health`、`/api/devices`、`/api/devices/discover`、`/api/plugins/discovered`（2 插件）、`/api/dashboards/snapshot`、`/api/testcases/` 全部正常
- 单测：`test_codegen`、`test_can_comlog`、`test_mg100_skill_syntax`（改为相对路径）通过；`test_serial_multiline`（依赖 POSIX `pty`）加 Windows 跳过
- 前端 `npm install` + `vite build` + `tsc --noEmit` 通过
- 打包产物验证：`AITestLab.exe` 启动 → 服务/前端/API 全通，数据落 `%LOCALAPPDATA%\AITestLab`；NSIS 静默安装到测试目录成功（含 exe、Uninstaller、Python 运行时）

### 交付产物

- `backend/dist/AITestLab-Setup-v1.0.0.exe`（NSIS 安装包，~21 MB，内含全部测试运行环境）
- `backend/dist/AITestLab/AITestLab.exe`（PyInstaller onedir 可直接运行版）

### 备注

`.gitignore` 新增忽略 `node_modules/`、`frontend/dist/`、`backend/static/`、`build/`、`dist/`、`.workbuddy/`；构建产物不入库（通过 Release 分发）。

---

## 2026-10-05: 节点输入/输出（Issue #4）+ Skill 编辑器 + 插件编辑器（v0.7.0）

> 分支 `feature/flow-enhancements`

### Issue #4：所有节点支持输入参数与输出返回值

- 新增 `backend/app/services/flow_context.py`，作为**代码生成器**与**运行时执行引擎**共用的
  单一实现，保证「生成代码」与「实际执行」对变量的解析行为完全一致：
  - `render_template()`：`{占位符}` 渲染，未知占位符原样保留便于发现拼写错误
  - `coerce_value()`：string / int / float / bool / hex 类型强转，失败回退原文不中断执行
  - `safe_eval()` / `eval_condition()`：白名单内置函数的安全表达式求值
  - `seed_context()`：从初始化节点变量播种上下文
  - `resolve_inputs()`：输入参数取值优先级 = 上下文（前序节点同名输出）→ 声明默认值
  - `collect_outputs()`：按 `response` / `parsed_N` / 解析字段名取值，空表达式默认 `response`
  - `available_variables()`：供 UI 展示「可用变量」清单
- **代码生成器**（`codegen_service.py`）：
  - 注入 `_r / _cast / _p / _out / _cond` 运行时助手，`ctx` 在 `run()` 开头初始化
  - 命令与预期结果统一包 `_r(..., ctx)`；初始化节点变量同时写入 `ctx`
  - 条件 / while / 进入条件 / 跳出条件改用 `_cond(expr, ctx)`，可直接写 `voltage > 10`
  - 操作节点与循环节点在解析后追加输出返回值赋值与日志
- **运行时执行引擎**（`execution_service.py`）：每步先解析输入 → 渲染命令/预期 → 下发 →
  用 `response / parsed_N / 解析字段名` 作用域收集输出 → 写回上下文；
  `step_completed` WebSocket 事件新增 `context` 字段
- **前端**（`TestFlowEditor.tsx`）：节点编辑弹窗新增「输入参数 / 输出返回值」Form.List
  （名称 / 类型 / 默认值或表达式 / 说明），以及「可用变量」标签（点击即复制 `{变量名}`）；
  画布上的操作 / 初始化 / 循环节点显示 in/out 数量徽标

### Skill 编辑器（`/skill-editor`）

- 左侧列表选择现有 Skill，右侧编辑名称 / 协议标识 / 关键词 / Markdown 正文，保存写入
  `plugins/skills/<protocol>_skill.md`（frontmatter 自动生成）；修改协议标识会同步重命名文件
- 支持上传或粘贴 `.md` 导入，protocol 从 frontmatter 或文件名（`foo_skill.md` → `foo`）推断
- 后端新增 `POST /api/plugins/skills`、`PUT /api/plugins/skills/{protocol}`、
  `POST /api/plugins/skills/import`、`DELETE /api/plugins/skills/{protocol}`；
  `plugin_service` 新增 `save_plugin_skill` / `import_plugin_skill` / `delete_plugin_skill`

### 插件编辑器（`/plugin-editor`）+ 插件模板

- 新增 `backend/app/services/plugin_editor_service.py` 与 `backend/app/api/plugin_editor.py`
  （`/api/plugin-editor/templates`、`/files`、`/validate`）
- 4 套模板放在 `backend/plugins/templates/`（子目录不会被插件扫描器当成插件）：
  **通信协议**、**设备驱动**、**数据解析**、**报告模板**；每套都带可运行示例与 TODO 标注
- 新建插件时按 `{{PLUGIN_NAME}} / {{CLASS_NAME}} / {{PROTOCOL_NAME}} / {{VERSION}} / {{DATE}}`
  占位符自动填充，生成的文件可直接通过语法校验并含插件类
- 编辑器支持在线改源码、「语法校验」（`compile` + AST 找 `BaseProtocolPlugin` 子类）、
  删除文件；插件管理页新增两个入口按钮

### 验证

- 4 套模板渲染后 `compile()` 全部通过；Skill 增 / 改 / 删 / 导入实测通过
- 前端 `tsc --noEmit` 与 `npm run build` 通过

---

## 2026-10-05: PeakCAN 连接鲁棒性加固（v0.7.1）

> 背景：`Test/Issue_Bug/PeakCAN无法链接.png` —— Windows 上连接 PeakCAN 设备报
> `[WinError 10047] 使用了与请求的协议不兼容的地址`，且错误信息中没有任何可定位的原因。

### 根因分析

- `[WinError 10047]`（`WSAEAFNOSUPPORT`）是 **Windows 上创建 AF_CAN socket** 时产生的，
  即 SocketCAN 被用在了 Windows 上。SocketCAN 依赖 Linux 内核 CAN 子系统，Windows 不存在。
- 错误文本**没有**插件包装层（如 `Failed to open CAN channel ...`），说明它不是被
  `connect()` 的 `except can.exceptions.CanError` 捕获后重新抛出的 —— python-can 在
  建 socket 阶段抛的是裸 `OSError`，因此直接穿透 `device_service` 到了前端。
- 原 `auto` 检测是“单次盲试”：一旦选错组合（例如 `can0` 存在但 `operstate=down`、
  或 PCAN-Basic 驱动缺失）就没有任何回退，失败原因也看不到。

### 修复内容（`backend/plugins/peakcan_plugin.py` → v1.1.0）

- **多候选按序重试**：`_candidate_list()` 生成有序 `(接口, 通道)` 列表 —— 显式 channel
  （按名字猜驱动：`can0`/`vcan0` → socketcan，其它 → pcan）→ 已 UP 的 SocketCAN 接口 →
  其它 SocketCAN 接口 → 检测到的 PCAN 通道 → 平台默认。
  **Windows 上 SocketCAN 永远不会成为候选**；显式传 socketcan 或 `can0` 通道时直接给出中文说明。
- **不再泄漏裸 OS 错误**：`can.interface.Bus()` 改为捕获 `Exception`，把每个候选的失败原因
  逐条收集，最终抛出带完整尝试清单 + 平台修复提示的 `ConnectionError`。
- **`_explain()` 错误翻译**：`10047` / `Network is down` / `No such device` / 缺 PCAN DLL
  等分别转为可操作的中文原因与命令。
- **`_socketcan_channels(only_up=True)`**：读 `/sys/class/net/*/operstate`，把 `down`
  的接口排到后面，避免“接口存在但打不开”导致的误判。
- **新增诊断能力**：`send({"action": "diagnose"})`（环境报告：平台、python-can 版本、
  候选顺序、检测通道、上次失败原因、修复提示）与 `send({"action": "scan"})`（通道列表），
  **断开状态即可调用**；`get_status()` 增加 `platform` / `is_windows` / `last_error` /
  `available_socketcan_up_channels`；`Error` 场景下 `send()` 会把上次失败原因一并带出。
- **JSON 命令字符串归一化**：UI / 调试终端下发的是字符串，原 `send()` 只认 `id#hex` 或 dict，
  于是手册与 Skill 里写的 `{"action": "scan"}`、`{"arbitration_id": 291, "data": [...]}`
  会被当成 CAN 字符串并报 `Invalid CAN string format`。现在以 `{` 开头的字符串先尝试
  `json.loads`，成功则按 dict 处理（`action` → 分发；其余 → 正常发帧）。

### 文档

- `docs/PEAKCAN_PLUGIN.md`：补充「候选顺序」说明、`diagnose` 命令与返回示例，
  故障排查表新增 `WinError 10047` 一行（指向 PCAN-Basic 驱动与 `interface=pcan`）及推荐排查顺序。

### 验证

- 插件文件语法/结构检查通过（无 lint 错误）；候选顺序逻辑覆盖 Linux / Windows 两条分支。
- 受限于当前环境（Linux，无 PCAN 硬件、无 Windows），硬件连接需在设备机上通过
  `{"action": "diagnose"}` 的输出最终确认。

---

## 下一步计划
- [ ] 端到端集成测试（AI → 流程图 → 编辑 → 代码 → 执行）
- [ ] 性能优化（启动速度、大数据渲染）
- [ ] 国际化（中英文界面切换）
- [x] 打包与安装程序制作（v1.0.0 Windows 安装包 ✅）
- [ ] 更多仪器驱动的适配与测试
- [ ] CI/CD 流水线搭建
- [ ] 流程图编辑器能力增强（详见 GitHub Issues：复制粘贴/节点类型切换/循环节点动作/循环条件/节点输入输出/初始化节点）

---

> 最后更新：2026-10-05
