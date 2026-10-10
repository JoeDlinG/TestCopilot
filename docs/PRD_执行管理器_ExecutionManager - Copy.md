# 测试用例执行管理器 — 产品需求文档（待确认）

> 主题：**测试用例执行管理器**（多用例编排 + 并行调度 + 设备互斥告警）
> 版本：待定（建议 **v0.6.0**，与 v0.5.0「结果数据管理 + DBC」的排期关系见 §10 K7）
> 状态：**草稿 — 待用户确认后登记看板**
> 日期：2026-10-09
> 基线代码：`master` @ `609971c`

---

## 0. 一句话定义

提供一个「执行计划」层：用户挑选多个测试用例 → 编排执行顺序与并行关系 → 配置每项的循环次数与延时 → 启动批量执行；系统在执行前**静态识别「同一设备被多个并行用例占用」并报警**，在执行中**用设备租约强制互斥**，防止交叉污染。

---

## 1. 现状分析（基于代码实证）

这一节是设计的前提。当前架构**不具备设备冲突检测能力**，不是"没做 UI"，而是缺数据基础。

### 1.1 关键事实清单

| 编号 | 事实 | 代码定位 | 对本需求的影响 |
|---|---|---|---|
| **F1** | **测试用例不绑定设备**。`TestCase` 表无 `device_id` 字段 | `models.py:218-240` | ⚠️ 冲突检测缺输入，这是最大障碍 |
| **F2** | 设备是**运行时推断**的，三级回退：<br>① `config.device_id`/`options.device_id` ② 命令串 `@\d+_[A-Z]+` → 推断 `mini_gateway100` ③ **兜底 `devices[0].id`** | `execution_service.py:112-140` | ⚠️ 兜底会静默占用「任意已连接设备」，使冲突检测形同虚设 |
| **F3** | 协议推断**只认 mini_gateway100 一家** | `execution_service.py:105-110` | 其它协议用例走不到 ②，直接落 ③ 兜底 |
| **F4** | 设备**无占用状态**。`DeviceStatus` 仅 `connected/disconnected/error` | `models.py:63-67` | 无法表达"忙/被占用" |
| **F5** | **无并发保护**。`_command_in_flight` 是 bool 标记不是锁，全项目无 `asyncio.Lock` | `device_service.py:38,342` | 两条执行并发下发同一设备 → 命令交错、响应串台 |
| **F6** | 执行引擎是**进程内 `asyncio.Task`**，无队列、无并发上限、无调度器 | `execution_service.py:47,187` | 打包版单 uvicorn 进程，天然可并行但无管控 |
| **F7** | 背景任务**复用请求级 DB 会话**，而该会话在响应返回时即 `close()` | `execution_service.py:187-189` + `database.py:24-29` | 单条已脆弱；并行多条会放大为会话竞争 |
| **F8** | **无批次概念**。`TestExecution` 无 `plan_id`/`parent_id` | `models.py:259-287` | 无法聚合展示"一次批量运行" |
| **F9** | 循环只存在于**节点级**（从自然语言抽「循环 N 次」，上限 50），**用例级循环不存在** | `execution_service.py:59-60,99-101` | 用例级 loop 是纯新增能力 |
| **F10** | **延时能力不存在**（`timeout_per_step` 是超时，不是延时） | `execution_service.py:234` | 纯新增能力 |
| **F11** | WebSocket 是 **per-execution**（`/ws/executions/{id}`） | `websocket.py:189` | 批量运行需 per-run 通道或前端多路订阅 |
| **F12** | 新增字段走 `_apply_light_migrations`（SQLite 无迁移器） | `database.py:32` | 扩展 `test_executions` 需在此登记 |

### 1.2 结论：必须先解决的两个前置项

```
               本需求的核心 = 设备冲突检测
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   【前置 P0】设备占用可静态确定      【前置 P1】运行时互斥保护
   F1/F2/F3：用例→设备映射不存在       F4/F5：无 busy 态、无锁
   → 检测算法拿不到输入                 → 检测漏了就会真出事
```

**P0（配置期）与 P1（运行期）必须同时做**。只做 P0 会被"手工单跑用例"和"推断失败"绕过；只做 P1 则用户得不到提前告警，只能等运行时排队，体验差。

---

## 2. 概念模型（术语统一）

| 术语 | 英文 / 字段 | 定义 |
|---|---|---|
| **执行计划** | Execution Plan | 一批用例的编排配置（模板，可保存复用） |
| **计划项** | Plan Item | 计划中的一行 = 一个用例 + 它的循环/延时/分组配置 |
| **并行组** | Group / `group_no` | 组号相同的项**并行**执行；组间按组号升序**串行** |
| **运行批次** | Plan Run | 计划的一次具体执行实例（可重复运行同一计划） |
| **迭代** | Iteration | 计划项的第 k 次循环（1 ≤ k ≤ loop_count），**迭代间串行** |
| **设备解析** | Device Resolve | 由用例静态推导出它"会占用哪些设备"的集合 |
| **设备租约** | Device Lease | 运行期对某设备的独占标记（device_id → run/item） |

### 2.1 调度模型（核心）

采用 **「线性列表 + 并行组」**，而非「阶段分组」或「全局并发度」：

```
计划项按 group_no 升序执行，组内并行，组间串行
默认：每项 group_no = 各自序号  →  完全串行（与现状行为一致）
用户把若干项设为同一 group_no   →  它们并行
```

**为什么选它**：
1. 与用户「配置执行顺序」的心智模型一致 —— 列表顺序即执行顺序；
2. 冲突检测退化为一个极简判定：**同一 `group_no` 内是否存在设备交集**；
3. 默认行为 = 现状（串行），无需用户先理解新概念，渐进增强；
4. 前端改动小（AntD Table + 拖拽排序 + 一个分组列）。

**已知表达力限制（v1 接受）**：无法表达"第 1 项与第 3 项并行、第 2 项夹在中间"。如需此能力，v2 升级为阶段（Stage）模型。

### 2.2 执行时序示意

```
计划: [A×2] [B×1, C×3 并行] [D×1]
       组1     组2（并行）     组3

时间轴 ──────────────────────────────────────────►
       ├─A#1──┬─A#2──┤                           组1：A 的两次迭代串行
              │      ├─前置延时─┬─B#1──┬─后置延时─┤   组2 内 B 与 C 并行
              │      └─前置延时─┬─C#1─┬间─┬─C#2─┬间─┬─C#3─┬─后置延时─┘
              │                                              │
              └─等待组2全部完成──────────────────────────────┤
                                                             ├─D#1──┤
```

---

## 3. 功能需求拆解

### FR1 计划管理（配置层）

| ID | 需求 | 说明 |
|---|---|---|
| FR1.1 | 新建/编辑/删除/复制执行计划 | 名称、描述、全局配置 |
| FR1.2 | 计划可**重复运行** | 计划是模板，每次运行生成独立 Run，历史可追溯 |
| FR1.3 | 计划列表页 | 显示名称、用例数、最近运行时间与结果 |
| FR1.4 | 全局配置 | 计划级循环 `plan_loop_count`（默认 1）、最大并行度 `max_parallel`（默认 4）、失败策略 `on_error` |
| FR1.5 | **向后兼容** | 现有「单用例立即执行」入口保留，生成的 `TestExecution` 的 `plan_run_id` 为空 |

### FR2 用例选择与排序

| ID | 需求 | 说明 |
|---|---|---|
| FR2.1 | 多选用例加入计划 | 支持按名称搜索、按标签/状态过滤；已加入项置灰防重复拖入（同一组重复拖入需拦截） |
| FR2.2 | 拖拽排序 | 上下拖动调整 `seq` |
| FR2.3 | 每项可移除 / 批量移除 | |
| FR2.4 | 每项展示用例元信息 | 名称、流程节点数、最近执行结果与耗时（辅助用户判断时长） |
| FR2.5 | 上限 | 单个计划最多 **50** 项（超出提示拆分） |

### FR3 并行分组与并发控制

| ID | 需求 | 说明 |
|---|---|---|
| FR3.1 | 每项有并行组号 `group_no` | 默认 = 其自身序号（串行） |
| FR3.2 | 提供「与上一项并行 / 与下一项并行 / 独立成组」快捷操作 | 避免手填组号 |
| FR3.3 | 并行组内项在 UI 上**视觉聚合**（同色块/缩进） | 一眼看出哪些一起跑 |
| FR3.4 | 全局 `max_parallel` 上限（1–16，默认 4） | 组大小超过上限时报警；防止 asyncio 并发过多拖垮设备响应 |

### FR4 循环次数

| ID | 需求 | 说明 |
|---|---|---|
| FR4.1 | 项级 `loop_count`（默认 1，范围 1–10000） | 同一项的 N 次迭代**串行**执行 |
| FR4.2 | 迭代间可设 `loop_interval_ms` | 长稳测试常用 |
| FR4.3 | 单次迭代失败后的行为受 `on_error` 控制 | 见 FR9 |
| FR4.4 | 迭代进度实时可见 | UI 显示 `3 / 100` |
| FR4.5 | >1000 次时二次确认 | 防止误配导致计划跑几天 |

### FR5 延时配置

| ID | 需求 | 说明 |
|---|---|---|
| FR5.1 | `delay_before_ms` 前置延时 | 本项开始前等待（设备上电/稳定） |
| FR5.2 | `delay_after_ms` 后置延时 | 本项结束后等待 |
| FR5.3 | `loop_interval_ms` 循环间隔 | 同项相邻迭代之间等待（**不含**首次前置、末次后置） |
| FR5.4 | 单位毫秒，范围 0–3,600,000（1 小时） | UI 提供「秒」快捷输入 |
| FR5.5 | 延时期间状态为 `delaying`，可中断 | 中断立即跳过剩余延时 |

### FR6 设备占用建模 ★（P0 前置）

这是**整个需求的地基**。目标：在用户点「开始执行」之前，就能确定每个计划项会占用哪些设备。

#### 6.1 设备解析优先级

```
① 计划项显式指定 device_id（用户在 UI 手工覆盖）        → 最高优先级，确定值
② 用例 flow 节点中静态抽取的 config.device_id（并集）   → 确定值
③ 协议推断：_extract_commands() → _infer_protocol()
   → 当前已连接且 protocol 匹配的设备集合（可能是 0..N 个）
④ 以上皆无                                            → UNRESOLVED（未确定）
```

#### 6.2 硬约束（必须遵守）

> **H1：批量执行模式下，禁用 `devices[0]` 兜底。**
> 现状 `execution_service.py:140` 的 `return devices[0].id` 会让"未确定设备"的项静默占用任意设备。
> 只要保留这个兜底，冲突检测就是假的。
> **处置**：单用例立即执行保留兜底（向后兼容）；批量计划执行下，UNRESOLVED 一律按 FR7 报错阻断。

> **H2：解析结果在计划保存时快照到 `plan_items.resolved_device_ids`。**
> 不实时重算，避免"改了用例导致历史计划的语义漂移"；提供「重新检测设备」按钮应对设备变动。

> **H3：③ 的推断结果必须是集合而非单值。**
> 现状 `_resolve_device()` 返回单个 id，无法做交集判定。需新增 `resolve_device_candidates()` 返回集合。

#### 6.3 解析结果展示

计划项列表新增「设备」列，三态渲染：
- 🟢 **已确定**（1 个或多个具体设备）：显示设备名，可点击修改
- 🟡 **推断为多个候选**（协议匹配到多台）：显示"N 台候选"，需用户收敛为 1 台
- 🔴 **未确定**：显示"未指定"，必须手工选择才能参与并行组

### FR7 设备冲突检测与报警 ★（用户核心诉求）

#### 7.1 检测时机

| 时机 | 行为 |
|---|---|
| 计划保存时 | 校验并**持久化**校验结果，不阻断保存（允许先存后改） |
| 打开计划编辑器 | 自动重算并展示 |
| 点「开始执行」 | **强制校验**；存在 Error 则禁用按钮并弹出冲突面板 |
| 配置变更（分组/设备/拖拽） | 前端实时增量校验（防抖 300ms） |

#### 7.2 冲突判定算法

```python
def validate_plan(plan, items, devices) -> ValidationReport:
    errors, warnings, infos = [], [], []

    # ---- E1: 组间设备冲突（核心） ----
    for group_no, group_items in groupby(items, key=group_no):
        dev_map: dict[str, list[str]] = {}      # device_id -> [item_id]
        for it in group_items:
            if it.resolved_state == UNRESOLVED:
                # E2: 参与并行却未确定设备 —— 一律阻断
                if len(group_items) > 1:
                    errors.append(Error(
                        code="UNRESOLVED_DEVICE_IN_PARALLEL",
                        item_ids=[it.id],
                        msg=f"「{it.case_name}」未指定设备，不能与其它项并行",
                        fix="为该计划项指定具体设备，或将其移出并行组"))
                else:
                    warnings.append(Warning(
                        code="UNRESOLVED_DEVICE_SERIAL",
                        msg=f"「{it.case_name}」未指定设备，将沿用旧逻辑自动选择"))
                continue
            for d in it.resolved_device_ids:
                dev_map.setdefault(d, []).append(it.id)

        for dev_id, item_ids in dev_map.items():
            if len(item_ids) > 1:
                errors.append(Error(
                    code="DEVICE_CONFLICT",
                    device_id=dev_id,
                    item_ids=item_ids,
                    msg=f"设备「{dev_name}」被 {len(item_ids)} 个并行用例同时占用",
                    fix=AUTO_SERIALIZE))       # 一键拆组

    # ---- E3: 并行组超过并发上限 ----
    # ---- E4: 同一用例在同一并行组内重复 ----
    # ---- W1: 设备离线（status != connected） ----
    # ---- W2: 用例无 flow / 节点为空 ----
    # ---- W3: 预计时长超过阈值（如 24h） ----
    # ---- I1: 预计总时长估算 ----
    return ValidationReport(errors, warnings, infos)
```

#### 7.3 报警分级与 UI 呈现

| 级别 | 场景 | 是否阻断执行 | UI |
|---|---|---|---|
| 🔴 **Error** | 同组设备冲突（E1）<br>并行组内未确定设备（E2）<br>组大小 > max_parallel（E3）<br>同组重复用例（E4） | **是**，禁用「开始执行」 | 冲突面板顶部红色区块；表格中冲突行整行标红；设备列标红徽标 |
| 🟡 **Warning** | 设备离线（W1）<br>用例无流程（W2）<br>预计时长过长（W3）<br>串行项未确定设备（E2-串行） | 否，弹确认框二次确认 | 黄色区块；行内黄色标记 |
| 🔵 **Info** | 预计总时长、总迭代数、涉及设备清单 | 否 | 灰色信息条 |

#### 7.4 冲突面板交互（关键）

```
┌─ 执行前校验 ────────────────────────────────────────┐
│ 🔴 2 个冲突，必须处理后才能执行                        │
│                                                     │
│  ① 设备「PeakCAN USB」被 2 个并行用例占用              │
│     · 用例A：BMS 唤醒测试        （组 2）              │
│     · 用例B：CAN 报文周期检测     （组 2）              │
│     ┌──────────────┬──────────────┐                 │
│     │ 自动串行化(推荐)│  手动调整分组  │                 │
│     └──────────────┴──────────────┘                 │
│                                                     │
│  ② 「绝缘检测」未指定设备，不能并行                     │
│     [ 选择设备 ▾ ]                                    │
│                                                     │
│ 🟡 1 个警告                                          │
│   · 设备「RIGOL 示波器」当前离线，执行时会失败           │
│                                                     │
│ 🔵 预计：38 次迭代 / 5 台设备 / 约 42 分钟             │
└─────────────────────────────────────────────────────┘
```

**「自动串行化」行为**：把冲突项按 seq 顺序拆到**连续的独立组**，保持相对顺序不变，然后重新校验并给出差异预览（"预计总时长从 20 分钟变为 35 分钟"）。用户确认后应用。

#### 7.5 前端实时校验

`/api/execution-plans/validate` 接受**未保存的草稿计划**（前端传完整 plan + items JSON），后端返回校验报告，前端据此实时渲染 —— 不要求先保存才能校验。

### FR8 运行时设备互斥保护 ★（P1 前置）

静态检测覆盖不到的场景（手工单跑、推断漂移、跨计划并发），由运行期兜底。

| ID | 需求 | 说明 |
|---|---|---|
| FR8.1 | **设备租约** `device_leases(device_id, run_id, item_id, plan_id, acquired_at)` | 进程内 dict + DB 表双写（进程内用于快速判定，DB 用于重启后清理） |
| FR8.2 | 项进入 running 前申请其 `resolved_device_ids` 的全部租约 | 全部拿到才启动；否则置 `queued` 等待 |
| FR8.3 | 租约释放 | 项完成/失败/停止时释放；进程重启时清理孤儿租约 |
| FR8.4 | **每设备 `asyncio.Lock`** | 即使租约判定有竞态，也保证同一设备的 `send()` 不交错（顺带缓解 F5 与 Issue #14 的响应串台） |
| FR8.5 | 租约等待超时 | 超过 `lease_timeout`（默认 10 分钟）置 `failed`，错误码 `DELEASE_TIMEOUT` |
| FR8.6 | 设备占用看板 | 监控页显示每台设备当前被哪个 Run/用例占用 |

> **与 Issue #14 的关系**：#14（PeakCAN 回执被当作应答）会让并行执行下"拿到的是别人的回包"这一问题后果放大 —— 两个用例同时发 PeakCAN，各自收到的应答归属更混乱。
> **建议 FR8 与 #14 同期或 #14 先行。**

### FR9 失败策略与控制

| ID | 需求 | 说明 |
|---|---|---|
| FR9.1 | 全局 `on_error`：`abort_all`（默认）/ `continue` / `abort_group` | |
| FR9.2 | 停止整个 Run | 取消所有 running/queued 的项，已完成的保留结果 |
| FR9.3 | 停止单个项 | 该项置 stopped，同组其它项继续 |
| FR9.4 | 暂停/恢复 | **v1 不做**（跨迭代状态复杂），仅提供停止 |
| FR9.5 | 中断响应 | 延时中中断立即生效；运行中中断在当前 step 边界生效 |

### FR10 批量执行监控

| ID | 需求 | 说明 |
|---|---|---|
| FR10.1 | 新增 `WS /api/ws/execution-runs/{run_id}` | 推送 run 级与 item 级事件 |
| FR10.2 | Run 概览 | 总进度、当前组号、通过/失败统计、已用时长、预计剩余 |
| FR10.3 | 项列表 | 每项状态（pending/queued/delaying/running/passed/failed/stopped）、循环进度 `k/N`、当前设备 |
| FR10.4 | 设备占用列 | 实时显示"谁在占用" |
| FR10.5 | 下钻 | 点任一项 → 跳到现有单执行详情页（`/executions/{id}`，复用现有 UI） |
| FR10.6 | 现有执行列表页增加「批量运行」Tab | 按 Run 聚合，展开看项 |

### FR11 结果与数据归属

| ID | 需求 | 说明 |
|---|---|---|
| FR11.1 | 每次迭代生成**独立** `TestExecution` | 带 `plan_run_id` / `plan_item_id` / `iteration` |
| FR11.2 | 现有统计口径不变 | `plan_run_id IS NULL` 的单次执行保持原行为 |
| FR11.3 | 报告可按 Run 生成 | v1 仅提供「导出本批次结果 CSV」，报告合并放 v2 |

---

## 4. 数据模型变更

### 4.1 新增表

```sql
-- 执行计划（模板）
CREATE TABLE execution_plans (
  id            TEXT PRIMARY KEY,           -- pln_xxxx
  name          TEXT NOT NULL,
  description   TEXT,
  plan_loop_count INTEGER NOT NULL DEFAULT 1,   -- 计划级循环
  max_parallel  INTEGER NOT NULL DEFAULT 4,     -- 1..16
  on_error      TEXT NOT NULL DEFAULT 'abort_all',  -- abort_all|continue|abort_group
  last_run_id   TEXT,                       -- 最近一次运行
  created_at    DATETIME NOT NULL,
  updated_at    DATETIME NOT NULL
);

-- 计划项
CREATE TABLE execution_plan_items (
  id               TEXT PRIMARY KEY,        -- pitem_xxxx
  plan_id          TEXT NOT NULL REFERENCES execution_plans(id) ON DELETE CASCADE,
  testcase_id      TEXT NOT NULL,
  seq              INTEGER NOT NULL,        -- 展示/默认顺序
  group_no         INTEGER NOT NULL,        -- 并行组号；相同 = 并行
  loop_count       INTEGER NOT NULL DEFAULT 1,
  delay_before_ms  INTEGER NOT NULL DEFAULT 0,
  delay_after_ms   INTEGER NOT NULL DEFAULT 0,
  loop_interval_ms INTEGER NOT NULL DEFAULT 0,
  device_id        TEXT,                    -- 显式覆盖（可空 = 走推断）
  resolved_device_ids TEXT,                 -- JSON 数组快照（H2）
  resolved_state   TEXT NOT NULL DEFAULT 'unresolved',  -- resolved|candidates|unresolved
  created_at       DATETIME NOT NULL,
  updated_at       DATETIME NOT NULL
);
CREATE INDEX idx_pitems_plan ON execution_plan_items(plan_id, group_no);

-- 运行批次
CREATE TABLE execution_plan_runs (
  id             TEXT PRIMARY KEY,          -- prun_xxxx
  plan_id        TEXT,                      -- 可为 NULL（临时计划）
  plan_snapshot  TEXT NOT NULL,             -- JSON：运行时的计划快照（防改计划影响历史）
  status         TEXT NOT NULL,             -- pending|running|passed|failed|stopped|error
  total_items    INTEGER NOT NULL DEFAULT 0,
  completed_items INTEGER NOT NULL DEFAULT 0,
  passed_items   INTEGER NOT NULL DEFAULT 0,
  failed_items   INTEGER NOT NULL DEFAULT 0,
  error_message  TEXT,
  started_at     DATETIME,
  completed_at   DATETIME,
  duration_ms    INTEGER,
  created_at     DATETIME NOT NULL
);
CREATE INDEX idx_pruns_plan ON execution_plan_runs(plan_id);

-- 设备租约（运行期互斥）
CREATE TABLE device_leases (
  id           TEXT PRIMARY KEY,
  device_id    TEXT NOT NULL,
  run_id       TEXT,
  item_id      TEXT,
  execution_id TEXT,
  acquired_at  DATETIME NOT NULL,
  released_at  DATETIME
);
CREATE UNIQUE INDEX idx_lease_active ON device_leases(device_id)
  WHERE released_at IS NULL;      -- 部分唯一索引：同一设备只能有一条活跃租约
```

> SQLite 支持部分索引（`WHERE` 子句），这能让"同一设备只能有一条活跃租约"由**数据库强制**，而不是靠应用层逻辑。

### 4.2 扩展现有表

`test_executions` 新增（通过 `_apply_light_migrations` 登记）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `plan_run_id` | TEXT NULL | 所属批次；单用例执行为 NULL |
| `plan_item_id` | TEXT NULL | 所属计划项 |
| `iteration` | INTEGER NULL | 第几次循环（1-based） |
| `group_no` | INTEGER NULL | 并行组号 |

索引：`idx_executions_plan_run(plan_run_id)`。

### 4.3 迁移与兼容

- 全部为**新增表 + 新增可空列**，不改动既有列语义；
- `_apply_light_migrations` 中登记 4 个新列，保证老库升级不报错；
- 单用例执行路径**零改动**（新字段留空）。

---

## 5. API 契约

### 5.1 计划 CRUD

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/execution-plans/` | 创建计划 |
| GET | `/api/execution-plans/` | 列表（分页） |
| GET | `/api/execution-plans/{id}` | 详情（含 items） |
| PUT | `/api/execution-plans/{id}` | 更新（含 items 全量替换） |
| DELETE | `/api/execution-plans/{id}` | 删除 |
| POST | `/api/execution-plans/{id}/duplicate` | 复制 |

### 5.2 校验与设备解析 ★

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/execution-plans/validate` | **草稿校验**（body 为完整 plan+items，无需先保存） |
| GET | `/api/execution-plans/{id}/validate` | 已保存计划的校验 |
| POST | `/api/execution-plans/{id}/resolve-devices` | 重新推断所有项的设备（设备变动后） |
| GET | `/api/testcases/{id}/device-candidates` | 单用例的设备解析结果（供计划编辑器逐行调用） |

**校验响应结构**：

```jsonc
{
  "code": 0,
  "data": {
    "valid": false,                       // 无 Error 则为 true
    "blocking": true,                     // 是否禁止执行
    "errors": [
      {
        "code": "DEVICE_CONFLICT",
        "message": "设备「PeakCAN USB」被 2 个并行用例同时占用",
        "device_id": "dev_xxx",
        "device_name": "PeakCAN USB",
        "group_no": 2,
        "item_ids": ["pitem_a", "pitem_b"],
        "suggestions": [
          {"action": "auto_serialize", "label": "自动串行化(推荐)", "estimate_ms_delta": 900000},
          {"action": "manual",         "label": "手动调整分组"}
        ]
      }
    ],
    "warnings": [
      {"code": "DEVICE_OFFLINE", "message": "设备「RIGOL 示波器」当前离线", "item_ids": ["pitem_c"]}
    ],
    "infos": [
      {"code": "ESTIMATE", "total_iterations": 38, "devices": 5, "estimated_ms": 2520000}
    ]
  }
}
```

### 5.3 执行与控制

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/execution-plans/{id}/run` | 校验通过后启动，返回 `run_id`；有 Error 返回 **409** + 校验报告 |
| GET | `/api/execution-runs/{id}` | 批次详情（含每项进度） |
| GET | `/api/execution-runs/` | 批次列表 |
| POST | `/api/execution-runs/{id}/stop` | 停止整批 |
| POST | `/api/execution-runs/{id}/items/{item_id}/stop` | 停止单项 |
| GET | `/api/devices/leases` | 当前设备占用情况（供看板） |

### 5.4 WebSocket

新端点 `WS /api/ws/execution-runs/{run_id}`，事件类型：

| 事件 | 载荷 |
|---|---|
| `run_started` | run_id, total_items |
| `group_started` / `group_completed` | group_no, item_ids |
| `item_started` | item_id, testcase_id, execution_id, iteration, loop_count |
| `item_progress` | item_id, iteration, loop_count, status |
| `item_completed` | item_id, status, passed/failed, duration_ms |
| `run_completed` | status, 统计 |
| `lease_waiting` | item_id, device_id, waited_ms（租约等待中，提升可观测性） |

> 现有 `/ws/executions/{id}` 保持不变，单项下钻复用。

---

## 6. 前端交互设计

### 6.1 新增页面 `ExecutionPlanner.tsx`（路由 `/execution-plans/:id?`）

```
┌──────────────┬───────────────────────────────┬─────────────┐
│  用例库       │      执行序列                   │  校验面板    │
│              │                               │             │
│ [搜索框]     │ ┌───────────────────────────┐ │ 🔴 2 冲突   │
│ [标签筛选]   │ │组│用例│设备│循环│延时│操作 │ │  ① PeakCAN │
│              │ │1 │A  │CAN │ 2 │1s  │↑↓✕ │ │  ② 未指定  │
│ ☑ BMS唤醒    │ │2 │B  │CAN │ 1 │ -  │↑↓✕ │ │ 🟡 1 警告   │
│ ☑ CAN周期    │ │2 │C  │串  │100│5s  │↑↓✕ │ │ 🔵 预计42m │
│ ☐ 绝缘检测   │ │3 │D  │示波│ 1 │ -  │↑↓✕ │ │             │
│ ☐ 温升测试   │ └───────────────────────────┘ │ [开始执行]  │
│              │                               │  (冲突时禁用)│
│ [加入计划]   │ [+ 添加用例]                    │             │
└──────────────┴───────────────────────────────┴─────────────┘
                  全局：计划循环[1] 最大并行[4] 失败策略[停止全部▾]
```

**交互要点**：
- 表格行支持拖拽排序（`@dnd-kit/sortable`，需新增依赖）；
- 「组」列提供下拉：「独立成组 / 与上项并行 / 与下项并行」；
- 设备列三态渲染（§FR6.3），点击弹出设备选择器；
- 冲突行**整行标红** + 行内悬浮显示冲突原因；
- 校验面板实时更新（防抖 300ms 调 validate）；
- 「开始执行」在有 Error 时禁用 + Tooltip 说明。

### 6.2 改造页面 `Executions.tsx`

- 新增 Tab「批量运行」：Run 列表 → 展开看项进度；
- 单执行 Tab 保持现状。

### 6.3 新增组件

| 组件 | 职责 |
|---|---|
| `PlanItemTable.tsx` | 执行序列表格（排序/分组/循环/延时/设备） |
| `ValidationPanel.tsx` | 校验面板（分级展示 + 自动修复按钮） |
| `DeviceSelector.tsx` | 设备选择（含候选态提示） |
| `RunMonitor.tsx` | 批次监控（进度/设备占用） |

---

## 7. 非功能需求

| 项 | 要求 |
|---|---|
| **打包兼容** | 不新增重型依赖；`@dnd-kit` 约 30KB，可接受。后端零新增依赖 |
| **跨平台** | 不涉及新 IO；延时用 `asyncio.sleep`，进程管理复用既有跨平台分支 |
| **时区** | 新增时间字段统一沿用现状（⚠️ 受 Issue #7 影响，见 §10 K6） |
| **向后兼容** | 单用例执行路径零改动；新表/新列可空 |
| **并发安全** | 每个 execution 使用**独立 DB 会话**（修复 F7），禁止复用请求会话 |
| **性能** | 校验 50 项计划 ≤ 200ms；Run 事件推送 ≤ 500ms 延迟 |
| **可观测** | 租约申请/释放/等待超时均记日志；`lease_waiting` 事件推送前端 |

---

## 8. 验收标准

| # | 验收项 | 判定 |
|---|---|---|
| A1 | 配置 3 个用例、2 个并行组、循环 5 次、延时 1s，执行结果顺序与配置完全一致 | 人工 + 日志比对 |
| A2 | **同组两用例占用同一设备 → 校验报 E1 且「开始执行」禁用** | 自动化断言 |
| A3 | 点「自动串行化」→ 冲突消失，组号变为连续独立组，顺序不变 | 自动化断言 |
| A4 | 并行组内存在未指定设备的项 → 报 E2 阻断 | 自动化断言 |
| A5 | 绕过前端直接 `POST /run` 传冲突计划 → 返回 409 + 校验报告，**不启动** | API 断言（关键：后端必须独立校验） |
| A6 | 批量执行期间，手工对已占用设备发起单用例执行 → 该执行进入 `queued` 等待，不并发下发 | 集成测试 |
| A7 | 停止整批 → 所有 running/queued 项终止，已完成项结果保留 | 人工 |
| A8 | 预计时长估算与实际偏差 ≤ 30%（基于有历史数据的用例） | 抽样 |
| A9 | 老数据库升级后所有新表/新列就位，单用例执行行为不变 | 迁移测试 |
| A10 | `tsc --noEmit` + `npm run build` + 后端 `compileall` 全通过 | CI |

---

## 9. 任务拆解（WBS）

### M1 — 地基层（P0 + P1，必须先做）

| ID | 任务 | 依赖 | 说明 |
|---|---|---|---|
| T1.1 | `resolve_device_candidates()` 返回设备**集合** | — | 提取自 `_resolve_device`，不改原行为 |
| T1.2 | 新增 `execution_plans` / `execution_plan_items` 表 + CRUD API | — | |
| T1.3 | 设备解析与快照写入（`resolved_device_ids` / `resolved_state`） | T1.1 | |
| T1.4 | **设备租约 + 每设备 `asyncio.Lock`** | — | 含部分唯一索引、孤儿清理 |
| T1.5 | 修复 F7：每个 execution 独立 DB 会话 | — | 并行前必须修 |

### M2 — 校验与调度

| ID | 任务 | 依赖 |
|---|---|---|
| T2.1 | `validate_plan()` 算法（E1–E4 / W1–W3 / I1） | T1.3 |
| T2.2 | `POST /validate` 草稿校验 API | T2.1 |
| T2.3 | 批量调度器（组串行 / 组内并行 / 迭代串行 / 延时） | T1.4, T1.5 |
| T2.4 | `POST /run` 启动 + 409 阻断 | T2.1, T2.3 |
| T2.5 | 停止（整批 / 单项）+ 失败策略 | T2.3 |
| T2.6 | `WS /ws/execution-runs/{id}` 事件推送 | T2.3 |

### M3 — 前端

| ID | 任务 | 依赖 |
|---|---|---|
| T3.1 | `ExecutionPlanner.tsx` 页面 + 路由 + 菜单入口 | T2.2 |
| T3.2 | `PlanItemTable`（拖拽排序 / 分组 / 循环 / 延时） | T3.1 |
| T3.3 | `DeviceSelector` + 设备列三态渲染 | T3.2 |
| T3.4 | `ValidationPanel` + 自动串行化交互 | T3.1, T2.1 |
| T3.5 | `RunMonitor` + Executions 页「批量运行」Tab | T2.6 |
| T3.6 | 设备占用看板 | T3.5 |

### M4 — 收尾

| ID | 任务 |
|---|---|
| T4.1 | A1–A10 验收测试 |
| T4.2 | 老库迁移测试 + 打包验证 |
| T4.3 | 更新 `KANBAN.md` / `HISTORY.md` / `USER_MANUAL.md` |

**关键路径**：`T1.1 → T1.3 → T2.1 → T2.2 → T3.1 → T3.4`（校验链路）
`T1.4 → T1.5 → T2.3 → T2.4`（执行链路）

---

## 10. 待决策项（需你拍板）

| # | 决策点 | 我的建议 | 影响 |
|---|---|---|---|
| **K1** | 设备绑定方式：① 纯推断 ② 纯手工 ③ 推断+可覆盖（推荐） | **③** | 选①则 UNRESOLVED 时体验差；选②则每次要手配，老用例迁移成本高 |
| **K2** | 冲突时默认处置：① 阻断+提示 ② 自动串行化直接放行 | **① 阻断**，但提供一键「自动串行化」 | 选②会让用户不知情地被改变时序 |
| **K3** | 是否做运行时设备租约（FR8） | **必须做** | 不做则静态检测可被"手工单跑"绕过，冲突保护不完整 |
| **K4** | `max_parallel` 默认值 | **4**（上限 16） | 过大可能因设备响应慢导致超时误判 |
| **K5** | 是否分离「计划模板」与「运行批次」（Plan/Run） | **分离** | 合并则无法复用计划、历史追溯弱；分离多一张表 |
| **K6** | 是否先修 Issue #7（时区）再动工 | **建议先修** | 新增的时间字段会叠加同样问题（与 v0.5.0 K9 同议题） |
| **K7** | 排期：并入 v0.5.0 还是独立 v0.6.0 | **独立 v0.6.0，但 FR8 的设备锁可提前到 v0.5.0** | 设备锁是 v0.5.0 长稳测试的前置 |
| **K8** | 同一设备多通道（如 PeakCAN 双通道）是否算冲突 | v1 **算冲突**（按设备粒度） | 放宽需引入通道级建模，复杂度上升 |
| **K9** | 是否需要「暂停/恢复」 | v1 **不做** | 跨迭代状态与租约保持复杂，性价比低 |
| **K10** | 是否限制同一用例在同一计划中出现多次 | **不限制**，但同组内重复报 E4 | 长稳测试中"不同参数跑同一用例"是常见需求 |

---

## 11. 风险登记

| 风险 | 等级 | 缓解 |
|---|---|---|
| 禁用 `devices[0]` 兜底后，老用例在批量模式下大面积 UNRESOLVED | 中 | 提供「批量指定设备」入口；串行模式保留兜底 |
| Issue #14（PeakCAN 回执当应答）在并行下后果放大 | **高** | FR8 与 #14 同期或 #14 先行 |
| F7（复用请求会话）不修会导致并行下 DB 竞态 | **高** | T1.5 列为 M1 必做 |
| 拖拽依赖 `@dnd-kit` 引入构建体积 | 低 | ~30KB；或退化为「上移/下移」按钮 |
| 用户误配 10000 次循环导致计划跑数天 | 中 | FR4.5 二次确认 + 预计时长提示 |
