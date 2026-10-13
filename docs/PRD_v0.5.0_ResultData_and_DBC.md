# AITestLab v0.5.0 产品需求文档

## 主题：结果数据管理（大数据存储）+ CAN DBC 导入与解析配置关联

- 版本号：**v0.5.0**（上一版 v0.4.0 = Windows 兼容 + 打包）
- 文档状态：待评审
- 基线代码：`609971c`
- 撰写日期：2026-10-06

---

## 0. 版本定位

v0.5.0 是 AITestLab 从「能跑通测试」走向「能承载真实产线数据量」的**数据能力版本**。两个需求分别解决两类瓶颈：

| 需求 | 解决的瓶颈 | 不做的后果 |
|---|---|---|
| **R1 结果数据管理（大数据存储）** | 长稳测试场景下采样点从「万级」涨到「亿级」，当前单 SQLite 表无法承载 | 长稳跑 24h 后数据库膨胀到 GB 级、查询超时、导出 OOM |
| **R2 DBC 导入 + 解析配置关联** | 当前解析配置靠人工填字节偏移，CAN 报文一改版全部失效 | 每换一个 DBC 就要手工重配几十个字段，且极易错位 |

**版本目标（一句话）**：让 10 亿级采样点的长稳测试可查询、可归档，并让 CAN 信号的解析配置可从 DBC 一键生成、自动跟随 DBC 变更。

---

## 1. 现状分析（基于代码实证）

### 1.1 数据存储现状

| 项 | 现状 | 位置 |
|---|---|---|
| 存储引擎 | SQLite + WAL，单文件 | `backend/app/core/database.py` |
| ORM | SQLAlchemy 2.0.36 async + aiosqlite 0.19.0 | `backend/requirements.txt` |
| 表数量 | 13 张 | `backend/app/models/models.py` |
| 采样点落库位置 | `test_step_results.parsed_results`（**Text 存 JSON 字符串**） | `models.py:314` |
| 采样点结构 | `{count, samples:[[{name,value,status,ok,detail}]], last:[...]}`，**一次响应的全部采样挤在一个 TEXT 字段里** | `models.py:306-314` |
| 通信日志 | `communication_logs`，单行一条报文，含 `raw_data` / `raw_data_hex` | `models.py:329-361` |
| 查询分页 | `logs.py:56-57` — `page` / `page_size`（上限 200） | `app/api/logs.py` |
| 批量导出 | `log_service.py:107-134` — 分批游标拉取（已优化） | `app/services/log_service.py` |
| **数据保留策略** | **不存在**（无 TTL、无归档、无清理、无 VACUUM 调度） | 全仓库检索确认 |
| 实测库规模 | 开发库 296 KB / 0 行；用户库历史实测 813 个判定点 | — |

**核心瓶颈判定**：`parsed_results` 把 N 个采样点序列化成**一个 JSON TEXT**。该字段无法被索引、无法按值过滤、更新时要整字段重写。当单个步骤重复下发 10 万次时，会产生一个数十 MB 的 TEXT 值，读取必然超时。这是 R1 必须首先解开的死结。

### 1.2 解析配置现状（R2 的对接对象）

解析配置（下文统称 **ParserSpec**）当前结构（`frontend/src/components/ResultParserConfig.tsx:27-42`，后端无 Pydantic 约束，经 `FlowNode.config` 透传）：

```python
ParserSpec = {
    "name": "母线电压",
    "data_type": "hex" | "bin" | "bool" | "dec" | "string",
    "start": 0,            # 起始偏移
    "length": 2,           # 长度
    "unit": "byte" | "bit",   # 切片单位
    "hex_field": "all" | "0" | "1" | "last",  # 多 0x 字段时选哪个
    "conditions": {"min": 10, "max": 60, "equals": ["0x01", "0x02"]},
}
```

解析引擎 `backend/app/services/response_parser.py`：

| 能力 | 位置 | 说明 |
|---|---|---|
| 字节提取 | `response_parser.py:141-173` | `extract()` — 按 `start`/`length`/`unit` 切片 |
| **bit 切片实现** | `response_parser.py:159-166` | `bits = "".join(f"{b:08b}" for b in data)` → `int(bits[start:start+length], 2)`，即**固定 MSB-first 大端位序** |
| 类型转换 | `response_parser.py:176-207` | hex/bin/bool/dec/string |
| 判定 | `response_parser.py:243-293` | min / max / equals（OR 语义） |
| 空帧识别 | `response_parser.py:77-97` | `0X` 空载荷 → `unknown` |

### 1.3 ⚠️ 已识别的架构风险（必须在 R2 前解决）

**解析逻辑存在两份独立实现，靠人工保持同步：**

| 实现 | 位置 | 用途 |
|---|---|---|
| A. 运行时引擎 | `backend/app/services/response_parser.py` | 执行时判定 PASS/FAIL |
| B. 生成器内联副本 | `backend/app/services/codegen_service.py:130` 起 `parse_field()` | 生成的 Python 脚本内自带一份解析函数 |

`KANBAN.md` 记载「代码生成器与运行时判定保持一致」，但当前一致性是**靠人肉同步两个文件维持**的。R2 引入字节序/符号/缩放/枚举后，若只改 A 不改 B，将出现**同一用例在平台内判定 PASS、导出脚本判定 FAIL**的严重不一致。

> **本版本硬性要求**：R2 开始前，先把解析逻辑抽为**单一真相源**（详见 §3.6 / 任务 T2.0），codegen 只做「引用或同源生成」。

### 1.4 DBC 支持现状

**完全没有。** 全仓库检索 `dbc`（大小写不敏感）在 `backend/app`、`backend/plugins`、`frontend/src` 中**零命中**。

依赖层面：`backend/requirements.txt` 已含 `python-can==4.3.1`（CAN 总线通信），但**无 `cantools`**（DBC 解析库），venv 实测确认未安装。

> 注：ATEMall 组织的 `can-log-analyzer` 项目已有 DBC 解码实现，可参考其解析约定，但**不可直接依赖**（不同仓库、不同技术栈）。

---

## 2. R1 — 结果数据管理（大数据存储）

### 2.1 需求拆解

| 编号 | 子需求 | 优先级 | 说明 |
|---|---|---|---|
| R1.1 | 采样点结构化落库 | P0 | 拆掉 `parsed_results` JSON TEXT，改为独立采样表 + 列式明细 |
| R1.2 | 存储引擎分层 | P0 | 元数据存 SQLite，海量明细存列式文件，查询走嵌入式分析引擎 |
| R1.3 | 分层查询 API | P0 | 时间窗聚合 / 下采样 / 明细翻页三类查询 |
| R1.4 | 数据生命周期管理 | P1 | 保留策略（TTL）、归档、清理、空间回收 |
| R1.5 | 批量导入导出 | P1 | 大结果集流式导出（CSV / Parquet）、Parquet/CSV 回灌 |
| R1.6 | 空间与性能可观测 | P1 | 数据量看板（各表/各文件占用、增长趋势） |
| R1.7 | 向后兼容迁移 | P0 | 存量 `parsed_results` 平滑迁移，不丢历史数据 |

### 2.2 数据分层模型（核心设计）

采用**三层分离**：索引层 / 摘要层 / 明细层。

```
┌─────────────────────────────────────────────────────────────┐
│ 索引层 (SQLite, 始终在内存可控范围)                          │
│   test_executions / test_step_results   ← 只存元数据与摘要   │
│   新增 result_series_index              ← 采样序列的索引卡  │
└─────────────────────────────────────────────────────────────┘
                              │ series_id
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 摘要层 (SQLite)                                             │
│   新增 result_series_summary                                │
│   min/max/avg/std/count/fail_count/unknown_count/last_value │
└─────────────────────────────────────────────────────────────┘
                              │ segment_uri
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 明细层 (Parquet 列式分片, 按执行+步骤+时间分片)              │
│   data/results/{execution_id}/{step_index}/{series_id}/*.parquet │
└─────────────────────────────────────────────────────────────┘
```

**设计要点**

1. **一条采样序列 = 一个 (execution, step, field) 三元组**。例如「母线电压」在 3 号步骤采样 10 万次 → 一条 series，10 万个采样点。
2. **摘要层常驻 SQLite**：仪表盘、判定汇总、趋势曲线首屏只读摘要，**不需要触碰明细文件**。这直接解决当前仪表盘「813 个判定点」类查询的性能问题。
3. **明细层按分片滚动写入**：单分片建议 64 MB 或 50 万行（取先到者），写完即封存（immutable）。封存后的 Parquet 支持列裁剪 + 谓词下推，聚合查询比 SQLite 行存快 1~2 个数量级。
4. **Parquet 不引入 `pyarrow`**：使用 DuckDB 自带的 Parquet 读写能力（`COPY ... TO 'x.parquet'` / `read_parquet()`），**只新增 `duckdb` 一个依赖**，避免 `pyarrow` 带来的 +80 MB 打包体积。

### 2.3 存储引擎选型

| 方案 | 代表 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A 纯 SQLite 分区表 | 按 execution 分表 + 索引优化 | 零新依赖、改动最小 | 亿级行时索引膨胀、写入放大、聚合仍需全扫 | 仅作 R1.1 的过渡态 |
| **B SQLite + Parquet + DuckDB** | 本项目推荐 | 列式压缩、**零服务进程**、可 PyInstaller 打包、分析查询快 | 新增 1 个依赖（`duckdb`，约 40–60 MB）、需自研分片管理 | ✅ **采纳** |
| C 时序数据库 | InfluxDB / TimescaleDB | 专业、压缩率最高 | **需独立服务进程**，与单机打包分发形态冲突 | ❌ 否决 |
| D Elasticsearch / ClickHouse | — | 生态强 | 同上，且资源占用远超桌面应用 | ❌ 否决 |

> **否决 C/D 的核心理由**：AITestLab 是 **PyInstaller 打包的单机桌面应用**（见 `backend/aitestlab.spec`、`backend/aitestlab.nsi`），要求「双击安装即用、无外部服务」。引入任何需要独立部署的数据库都违背产品形态。

### 2.4 数据模型变更

**新增表 1：`result_series_index`（序列索引）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(20) | 主键，`ser_xxxxxxxx` |
| `execution_id` | String(20) FK | 关联执行，级联删除 |
| `step_result_id` | String(20) FK | 关联步骤 |
| `step_index` | Integer | 冗余，便于排序 |
| `field_name` | String(200) | 字段名（如「母线电压」） |
| `data_type` | String(20) | hex/bin/bool/dec/string |
| `physical_unit` | String(50) | 物理单位（新增，见 §3.4） |
| `parser_ref` | Text | 生成该序列的 ParserSpec JSON 快照（含 DBC 溯源） |
| `sample_count` | Integer | 采样点总数 |
| `started_at` / `ended_at` | DateTime | 采样时间范围 |
| `storage_kind` | String(20) | `inline`（小数据，仍存 SQLite）/ `parquet`（大数据） |
| `created_at` | DateTime | — |

索引：`(execution_id, step_index)`、`(execution_id, field_name)`、`created_at`。

**新增表 2：`result_series_summary`（序列摘要）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `series_id` | String(20) PK/FK | 一对一 |
| `count` / `ok_count` / `fail_count` / `unknown_count` / `error_count` | Integer | 判定分布 |
| `min_value` / `max_value` / `avg_value` / `std_value` | Float | 数值统计（非数值序列为 NULL） |
| `last_value` | Text | 最新值 |
| `first_sample_at` / `last_sample_at` | DateTime | — |
| `segment_list` | Text | JSON 数组，记录 Parquet 分片相对路径与行数 |

**新增表 3：`result_segments`（分片登记）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | String(20) PK | `seg_xxxxxxxx` |
| `series_id` | String(20) FK | — |
| `relative_path` | String(500) | 相对 `data/results/` 的路径（**必须相对**，禁止绝对路径） |
| `row_count` | Integer | 行数 |
| `byte_size` | Integer | 文件大小 |
| `sealed` | Boolean | 是否已封存（封存后不再写） |
| `checksum` | String(64) | 可选，文件完整性 |

**Parquet 分片 schema**

| 列 | 类型 | 说明 |
|---|---|---|
| `seq` | INT64 | 序列内单调递增序号，用于稳定排序 |
| `ts` | TIMESTAMP(us) | 采样时间（**UTC**，见 §6.3） |
| `value_num` | DOUBLE | 数值化后的值（供聚合/绘图） |
| `value_text` | VARCHAR | 原始文本值（string/hex 类型） |
| `status` | VARCHAR | ok/fail/unknown/error |
| `detail` | VARCHAR | 判定说明 |

**变更现有表**

- `test_step_results.parsed_results`：**保留字段但降级**。新数据只写「最后一次采样」用于列表页快速展示；完整序列写入 `result_series_index` / Parquet。加迁移标记，存量数据由 R1.7 迁移任务处理。
- 增加 `series_count`（Integer）字段，用于列表页显示「本步骤产生 N 条序列」。

### 2.5 查询 API 契约

所有接口统一响应包装 `{code, message, data}`（沿用现有约定）。

**① 序列列表**

```
GET /api/results/series?execution_id=&step_index=&field_name=&page=&page_size=
→ { items: [{series_id, field_name, data_type, physical_unit, sample_count,
             started_at, ended_at, summary: {...}}], total, page, page_size }
```

**② 时间窗聚合（核心）**

```
GET /api/results/series/{series_id}/aggregate
    ?from=&to=&bucket=raw|1s|10s|1m|1h&agg=avg|min|max|count
→ { series_id, bucket, points: [{ts, avg, min, max, count}], point_count }
```
要求：`bucket=1m` 且跨度 24h 时返回点数 ≤ 1440（服务端强制下采样，禁止把 864 万个点原样返回）。

**③ 明细分页**

```
GET /api/results/series/{series_id}/samples?offset=&limit=（limit 上限 5000）
→ { items: [{seq, ts, value_num, value_text, status, detail}], total }
```

**④ 判定汇总**

```
GET /api/results/executions/{execution_id}/judgement-summary
→ { total, ok, fail, unknown, error, pass_rate, by_field: [...], recent_fails: [...] }
```
该接口**只读摘要层**，必须不触碰 Parquet 文件（供仪表盘高频轮询）。

**⑤ 空间统计**

```
GET /api/results/storage-stats
→ { sqlite_bytes, parquet_bytes, parquet_file_count,
    per_execution: [{execution_id, series_count, sample_count, bytes}],
    growth_7d: [...] }
```

**⑥ 归档与清理**

```
POST /api/results/archive    { before: "<date>", execution_ids?: [] }
POST /api/results/cleanup    { before: "<date>", dry_run: bool }
→ dry_run=true 时只返回将被删除的对象清单与可释放空间
```

### 2.6 数据生命周期

| 阶段 | 触发 | 动作 |
|---|---|---|
| 热数据 | 最近 N 天（默认 30，可配） | 保留在 `data/results/`，可查询、可图表 |
| 温数据 | 超过 N 天 | 打包为 `.tar.zst` 归档到 `data/archive/`，索引保留（可查元数据），明细需「解档后查询」 |
| 冷数据 | 超过 M 天（默认 180） | 清理，`cleanup` 二次确认；**默认关闭自动清理**，由用户显式开启 |

必须提供 `dry_run` 与执行前的影响面预览（将删除多少执行、释放多少空间）。

### 2.7 性能指标（验收量化）

| 指标 | 目标值 | 测量方式 |
|---|---|---|
| 采样点写入吞吐 | ≥ 20,000 点/秒（批量事务） | 1000 万点压测脚本 |
| 单次执行采样点容量 | ≥ 500 万 | 压测 |
| 累计采样点容量 | ≥ 1 亿（不出现查询超时） | 压测 + 老化数据 |
| 聚合查询延迟（24h 跨度，1m 桶） | P95 < 2 s | 压测 |
| 明细分页查询 | P95 < 300 ms（任意 offset） | 压测 |
| 判定汇总查询（仪表盘轮询） | P95 < 150 ms | 压测 |
| 磁盘占用 | 相比现状同等数据量降低 ≥ 60% | 对比测试（JSON TEXT vs Parquet 压缩） |
| 数据库文件增长 | 1 亿采样点后 SQLite 主库 ≤ 500 MB | 压测 |

---

## 3. R2 — CAN DBC 导入与解析配置关联

### 3.1 需求拆解

| 编号 | 子需求 | 优先级 | 说明 |
|---|---|---|---|
| R2.0 | **解析逻辑单一真相源**（前置） | P0 | 消除 `response_parser.py` 与 `codegen_service.py:130` 的双实现 |
| R2.1 | DBC 文件导入与校验 | P0 | 上传 `.dbc`，解析、校验、版本管理 |
| R2.2 | DBC 内容浏览与检索 | P0 | 报文树 / 信号详情 / 全文搜索 |
| R2.3 | 信号 → 解析配置关联（**核心**） | P0 | 从 DBC 信号一键生成 ParserSpec |
| R2.4 | 解析引擎能力扩展 | P0 | 字节序 / 符号 / 缩放 / 枚举 / 物理单位 |
| R2.5 | CAN ID 提取与报文匹配 | P0 | 从响应中定位报文 ID，匹配 DBC message |
| R2.6 | DBC 变更影响分析 | P1 | DBC 更新后，标出受影响的用例/步骤 |
| R2.7 | 代码生成器同步 | P0 | 生成的脚本与平台判定完全一致 |

### 3.2 DBC 导入流程

```
用户上传 .dbc
   ↓
① 文件校验：扩展名 / 大小上限（建议 20 MB）/ 编码（UTF-8，兼容 latin-1 回退）
   ↓
② 语法解析：cantools.database.load_file() → 捕获 DbcSyntaxError
   ↓
③ 语义校验：报文数 / 信号数统计，重复 ID、越界信号、非法 factor=0 告警
   ↓
④ 落库：dbc_files（原文件内容 + SHA256）+ dbc_messages + dbc_signals
   ↓
⑤ 返回解析摘要（报文数/信号数/告警列表）
```

**导入必须做到**：

- 同一 DBC 内容重复上传 → 按 SHA256 识别，提示「已存在，是否覆盖或另存为新版本」。
- 解析失败 → 返回**行号 + 原始行内容**，不是裸异常堆栈。
- 导入过程不得阻塞服务（大 DBC 解析放线程池）。

### 3.3 信号 → 解析配置映射（核心规格）

DBC 信号属性 → ParserSpec 字段的映射规则：

| DBC 信号属性 | ParserSpec 字段 | 转换规则 | 备注 |
|---|---|---|---|
| `signal.name` | `name` | 直接使用 | 需通过用例内唯一性校验（现有规则） |
| `message.frame_id` | `source.can_id` | 直接 | 新增，用于报文匹配 |
| `signal.start` | `start` | Motorola 需位序归一（见下） | **关键** |
| `signal.length` | `length` | 直接 | — |
| — | `unit` | 固定 `"bit"` | 保持既有切片语义 |
| `signal.byte_order` | `byte_order` | `little_endian`→`intel`；`big_endian`→`motorola` | **新增字段** |
| `signal.is_signed` | `is_signed` | 布尔 | **新增字段** |
| `signal.factor` | `factor` | 直接（默认 1） | **新增字段** |
| `signal.offset` | `offset` | 直接（默认 0） | **新增字段** |
| `signal.minimum` | `conditions.min` | 直接 | DBC 中该值已含 factor/offset |
| `signal.maximum` | `conditions.max` | 直接 | 同上 |
| `signal.choices` | `value_map` | `{raw_int: "文本"}` | **新增字段**（替代/补充 equals） |
| `signal.unit` | `physical_unit` | 直接 | **新增字段**，注意与切片 `unit` 区分 |
| `signal.comment` | `description` | 直接 | 展示用 |

> ⚠️ **命名冲突预警**：DBC 的 `unit`（V / A / degC）与现有 ParserSpec 的 `unit`（bit / byte）**语义完全不同**。**绝不可复用同一字段**，必须新增 `physical_unit`。复用会导致所有既有配置的切片单位被污染。

**Motorola 位序归一算法**

DBC 中 Motorola 信号的 `start_bit` 采用 sawtooth 编号（bit0 = 字节 0 的 LSB），而当前引擎 `response_parser.py:159-166` 使用**线性 MSB-first** 索引。两者需换算：

```python
def dbc_start_to_linear(start_bit: int, byte_order: str) -> int:
    """把 DBC 的 start_bit 归一化为线性 MSB-first 位索引。"""
    if byte_order == "little_endian":          # Intel
        # Intel: start_bit 即 LSB 的线性位置（bit0 = 字节0 LSB）
        return start_bit
    # Motorola: bit0 = 字节0 的 MSB
    return (start_bit // 8) * 8 + (7 - start_bit % 8)
```

**验收要求**：该换算**必须**用 `cantools` 的 `decode_message()` 作为金标准做交叉验证——对测试 DBC 中**每一个**信号，用随机字节串做 round-trip，断言本引擎解出的物理值与 cantools 完全一致（浮点容差 1e-9）。**禁止仅凭公式推导就认为正确**。

**缩放与符号处理顺序（规范）**

```
raw_bytes
  → 按 byte_order 取 length 位
  → 若 is_signed：二进制补码 → int
  → 得到 raw_value
  → physical_value = raw_value * factor + offset
  → 若 value_map 命中 raw_value：附上文本标签
  → 与 conditions.min/max 比较（比较对象是 physical_value）
```

顺序不可颠倒（`min/max` 是物理值域，必须在缩放后比较）。

### 3.4 ParserSpec 扩展后的完整结构

```python
ParserSpec_v2 = {
    # ---- 既有字段（保持兼容） ----
    "name": "母线电压",
    "data_type": "dec",
    "start": 8,
    "length": 16,
    "unit": "bit",
    "hex_field": "all",
    "conditions": {"min": 9.0, "max": 16.0, "equals": []},

    # ---- R2 新增字段 ----
    "byte_order": "intel" | "motorola",     # 默认 intel（保持现有行为）
    "is_signed": False,
    "factor": 0.1,
    "offset": 0.0,
    "physical_unit": "V",                    # 物理单位，展示用
    "value_map": {"0": "OFF", "1": "ON", "2": "FAULT"},
    "decimal_places": 1,                     # 展示精度

    # ---- 溯源信息（自动生成，只读） ----
    "source": {
        "kind": "dbc",
        "dbc_id": "dbc_a1b2c3d4",
        "dbc_version": 2,
        "message_id": 0x11,
        "message_name": "BMS_Status",
        "signal_name": "PackVoltage",
        "linked_at": "2026-10-06T04:00:00Z",
    },
}
```

**向后兼容硬约束**：`byte_order` **默认值必须是 `intel`**，且 `intel` 下 `start` 的语义与**当前实现完全一致**（线性 LSB 编号）。即：**既有 ParserSpec 不修改也能得到与今天完全相同的结果**。该点必须有回归测试保证。

### 3.5 CAN ID 提取与报文匹配

DBC 解码的前提是知道「这条响应属于哪个报文」。当前 `response_parser.to_bytes()`（`response_parser.py:100-139`）只提取 hex 载荷，**会丢弃 ID 字段**。

以 Mini-Gateway 风格响应 `1,STD,0X11,0X0102030000000000` 为例，字段含义为：通道 / 帧类型 / **CAN ID** / 数据。现有 `hex_field` 已能选择「第 N 个 0x 字段」，**复用同一语义**新增：

```python
"can_id_field": "0",        # 第 1 个 0x 字段 = CAN ID（与 hex_field 语义一致）
"can_id_hex": True,         # 字段是十六进制
"expected_can_id": 0x11,    # 可选：与 DBC signal 所属 message 比对，不符则报错
```

**匹配逻辑**：
1. 若配置了 `expected_can_id` → 直接使用，同时在运行时**校验**实际 ID 是否一致；不一致 → `status=error`，`detail` 明确说明「期望 0x11，实际 0x22」。
2. 若未配置但配置了 `can_id_field` → 从响应中提取 ID，按 ID 查 DBC message，取其下已关联的信号解码。
3. 两者都无 → 保持现有行为（仅按偏移解析，不做 DBC 匹配）。

**产品要求**：必须支持**扩展帧**（29 位 ID）与标准帧（11 位 ID）的区分，判定依据为配置项而非猜测。

### 3.6 解析逻辑单一真相源（R2.0，前置任务）

这是 R2 的**技术前提**，必须先做，否则 R2.4 的能力扩展会立刻造成双实现漂移。

**要求**：

1. 把「字节提取 + 类型转换 + 缩放 + 判定」抽为**唯一实现**，例如 `app/services/parser_core.py`，`response_parser.py` 与其**只做一层薄封装**。
2. `codegen_service.py` 生成脚本时，**不得再维护第二份 `parse_field()` 副本**（当前位于 `codegen_service.py:130`）。采用以下任一方案：
   - **方案 A（推荐）**：生成的脚本内联**由 `parser_core` 单一模板渲染出的代码**（模板与实现同目录，改一处两处同步）。
   - **方案 B**：生成脚本头部 `from aitestlab_parser import parse_field`，随脚本导出一个 `aitestlab_parser.py`。
3. 建立**一致性测试**：对同一组（响应样本 × ParserSpec）输入，断言
   - 运行时引擎输出
   - 生成的脚本执行输出
   两者**逐字段完全一致**（含 `status` / `value` / `detail`）。
4. 该一致性测试纳入 CI，作为 R2 全系列任务的回归门禁。

### 3.7 前端交互要求

| 页面/组件 | 变更 |
|---|---|
| **新增「DBC 管理」页** | 列表（名称/版本/报文数/信号数/大小/导入时间）、上传（拖拽 + 点击）、详情抽屉、删除、重新导入为新版本 |
| **DBC 详情** | 报文树（Message → Signals），信号详情显示 start/length/byte_order/factor/offset/min/max/unit/choices |
| **解析配置弹窗**（`ResultParserConfig.tsx`，现 420 行） | 新增「**从 DBC 选择信号**」入口：选 DBC → 选报文（可按 ID/名称搜索）→ 选信号 → 自动填充全部字段 |
| 同上 | 已关联 DBC 的字段显示**来源徽标**（如 `BMS_Status.PackVoltage`），偏移类字段置为**只读**（避免手改后与 DBC 不一致） |
| 同上 | 提供「**解绑**」按钮，解绑后转为手工配置（保留当前值） |
| 测试用例页 | 步骤旁显示是否已关联 DBC；关联失效（DBC 被删/信号消失）时给出**醒目告警**而非静默失败 |

**交互硬要求**：
- 从 DBC 选信号后，**必须**立即用该步骤已有的真实响应样本做 parsetree 预览，展示解析值与 PASS/FAIL（复用现有预览能力）。
- 信号搜索支持按**信号名 / 报文 ID / 报文名**三种方式。
- 一个用例可关联多个 DBC（多设备/多总线场景）。

### 3.8 R2 边界情况（必须有明确行为）

| 场景 | 期望行为 |
|---|---|
| DBC 中两个报文同 ID | 导入时告警，保留全部，关联时要求用户显式选择 |
| 信号名跨报文重复 | 允许（DBC 合法），UI 中以 `报文名.信号名` 全限定展示 |
| 关联的 DBC 被删除 | 相关 ParserSpec **标记为失效**（不是静默降级），用例列表红点提示，执行时给出明确错误 |
| DBC 更新后信号 start/length 变化 | ← R2.6 影响分析：列出受影响的用例/步骤，供用户决定是否同步 |
| factor/offset 为 0 或缺失 | `factor` 缺失按 1、`offset` 缺失按 0；`factor == 0` 视为非法，导入时告警 |
| 信号长度超过报文 DLC | 导入时告警，运行时该字段 `status=error` |
| 多路复用信号（multiplexed） | v0.5.0 **不要求支持**，导入时识别并标注「暂不支持」，不报错 |
| 报文含扩展帧 ID | 按 `is_extended_frame` 区分处理 |

---

## 4. 数据模型变更总览

| 表 | 变更 |
|---|---|
| `result_series_index` | **新增** |
| `result_series_summary` | **新增** |
| `result_segments` | **新增** |
| `dbc_files` | **新增**（名称/版本/SHA256/原文件/报文数/信号数/导入时间/告警 JSON） |
| `dbc_messages` | **新增**（dbc_id/frame_id/name/dlc/is_extended/sender/comment） |
| `dbc_signals` | **新增**（message_id/name/start/length/byte_order/is_signed/factor/offset/min/max/unit/choices JSON/comment） |
| `test_step_results` | 增加 `series_count`；`parsed_results` 降级为「最后一次采样」 |
| `parser_specs` | **可选新增**：若希望 ParserSpec 独立于 flow node 复用，可抽出独立表；否则继续存于 `FlowNode.config.parsers` |

数据库版本从 13 张表扩展到 **19 张表**（含可选）。

---

## 5. 任务拆解（WBS）

### M1 — 数据底座（R1 核心）

| 任务 | 内容 | 依赖 | 验收 |
|---|---|---|---|
| T1.1 | 新增三张结果表 + 迁移脚本（Alembic 或自研 `ensure_column` 风格） | — | 空库建表成功；存量库升级不丢数据 |
| T1.2 | 采样点写入管线：执行引擎改为「序列缓冲 → 摘要 + Parquet 分片」 | T1.1 | 1000 万点写入吞吐 ≥ 2 万点/秒 |
| T1.3 | 分片管理（滚动封存、路径生成、checksum） | T1.2 | 单分片 >64 MB 或 >50 万行时自动封存 |
| T1.4 | DuckDB 查询层（聚合 / 下采样 / 明细翻页） | T1.3 | 24h 跨度 1m 桶聚合 P95 < 2s |
| T1.5 | 系列查询 / 聚合 / 明细 / 判定汇总 六个 API | T1.4 | 契约测试全通过 |
| T1.6 | 仪表盘与趋势服务切换到摘要层 | T1.5 | 判定汇总 P95 < 150ms，且不读 Parquet |
| T1.7 | 存量 `parsed_results` 迁移工具 | T1.1 | 813 点历史用例迁移后查询结果与迁移前一致 |
| T1.8 | CI 性能回归基线 | T1.2–T1.6 | 每次 PR 跑小规模压测，超标即失败 |

### M2 — 生命周期与运维（R1 收尾）

| 任务 | 内容 | 依赖 | 验收 |
|---|---|---|---|
| T2.1 | 保留策略配置（热/温/冷天数，默认不自动清理） | T1 | 配置可持久化并生效 |
| T2.2 | 归档（`.tar.zst`）与清理（`dry_run` 预览） | T2.1 | dry_run 报告与实际执行一致 |
| T2.3 | 空间统计 API + 前端「存储」页 | T1.5 | 数字与实际文件系统一致（误差 <1%） |
| T2.4 | 流式导出（CSV / Parquet），大结果集不 OOM | T1.4 | 导出 1000 万点内存占用 < 300 MB |
| T2.5 | 回灌（CSV/Parquet → 结果库） | T2.4 | 往返导出导入后数据一致 |

### M3 — DBC 集成（R2）

| 任务 | 内容 | 依赖 | 验收 |
|---|---|---|---|
| **T3.0** | **解析逻辑单一真相源重构 + 一致性 CI** | — | 运行时 vs 生成脚本输出逐字段一致（见 §3.6） |
| T3.1 | 引入 `cantools`，DBC 解析与校验服务 | — | 合法 DBC 全通过；非法 DBC 返回行号 |
| T3.2 | 三张 DBC 表 + 导入 API（含 SHA256 去重、版本管理） | T3.1 | 重复上传正确识别 |
| T3.3 | 解析引擎扩展：byte_order / is_signed / factor / offset / value_map | T3.0 | **cantools round-trip 交叉验证全部信号通过** |
| T3.4 | Motorola 位序归一 + 单元测试 | T3.3 | 见 §3.3 验收要求 |
| T3.5 | CAN ID 提取与报文匹配（含扩展帧） | T3.3 | 期望/实际 ID 不符时 `status=error` 且提示明确 |
| T3.6 | codegen 同步（生成脚本支持全部新能力） | T3.0, T3.3 | 一致性 CI 覆盖新字段 |
| T3.7 | DBC 管理页（列表/上传/详情/删除） | T3.2 | 交互验收 |
| T3.8 | 解析配置弹窗集成信号选择器 + 来源徽标 + 解绑 | T3.3, T3.7 | 选信号后自动填充并即时预览 |
| T3.9 | DBC 变更影响分析（标出受影响用例） | T3.2 | 改 DBC 后能列出受影响步骤清单 |
| T3.10 | 边界情况全覆盖（见 §3.8 八项） | T3.3–T3.9 | 每项有独立测试用例 |
| T3.11 | 前置回归：既有 ParserSpec 行为不变 | T3.3 | `byte_order` 默认 intel，旧配置结果与 v0.4.0 逐字段一致 |

**关键路径**：T3.0 → T3.1 → T3.3 → T3.5 → T3.8。T3.0 必须最先完成，否则后续全部返工。

---

## 6. 非功能需求

### 6.1 打包兼容（硬约束）
- 新增依赖仅允许 **`duckdb`** 与 **`cantools`**（两者均纯 Python/含预编译 wheel，无外部服务）。
- `backend/aitestlab.spec` 的 `hiddenimports` 需补充 `duckdb`、`cantools` 及其子模块（参考现有 `collect_submodules("can")` 写法）。
- 打包体积增量目标 **≤ 80 MB**（在 NSIS 安装包上评估）。
- 若 `cantools` 打包后体积超标，备选：仅提取其 DBC 词法/语法解析部分（MIT 许可），但**须评估维护成本后再定**。

### 6.2 跨平台
- Parquet 分片路径一律 `os.path.join` + `tempfile`/配置目录，**禁止**出现 `/tmp`、`/dev/`。
- DuckDB 文件与 Parquet 路径必须用**相对路径**登记（相对数据根目录），避免换机器后失效。
- Windows 下文件被占用时的关闭重试逻辑（Parquet 封存后应释放句柄）。

### 6.3 时间与时区
- 所有新增时间列一律 **UTC**，且序列化带时区标识（`Z`）。
- 该要求与已登记的 **Issue #7**（时区缺陷）相关：R1/R2 新增的时间字段**不得**重蹈 `datetime.utcnow()` 无时区标识的覆辙，建议**在 R1 开工前先修掉 #7**，统一时间基座。

### 6.4 兼容与迁移
- 数据库升级必须**向前兼容**：旧版本程序遇到新库不崩溃（至少给出明确版本不匹配提示）。
- 迁移需可重入（中断后可重跑）。
- 迁移前自动备份 `.db` 文件。

### 6.5 可观测
- 记录写入/查询/归档的结构化日志（含耗时、点数、文件大小）。
- 提供 `/api/results/storage-stats` 供前端「存储」页与问题排查。

---

## 7. 风险与待决策项

| # | 类型 | 内容 | 建议 |
|---|---|---|---|
| K1 | **决策** | DBC `unit` 与切片 `unit` 命名冲突 | 已定：新增 `physical_unit`，**不复用** |
| K2 | **决策** | 是否引入 `duckdb`（+40~60 MB 打包体积） | 建议采纳；若不接受，退化为「SQLite 分区表」方案（但性能指标 §2.7 需下调） |
| K3 | **决策** | ParserSpec 是否抽为独立表以支持跨用例复用 | 建议 v0.5.0 **不做**，继续存于 flow node，避免放大改动面 |
| K4 | 风险 | Motorola 位序实现错误（静默解错值，最危险） | 强制 cantools round-trip 交叉验证，**不允许仅靠公式推导** |
| K5 | 风险 | 双实现漂移（`response_parser` vs `codegen`） | T3.0 前置重构 + CI 一致性门禁 |
| K6 | 风险 | 大 DBC（数千信号）导入慢 / 表单卡顿 | 导入走线程池；前端信号选择器用虚拟滚动 |
| K7 | 风险 | 迁移 813+ 点存量数据出错 | 迁移前自动备份 + 迁移后可回滚 + 逐用例比对 |
| K8 | 决策 | 多路复用信号（multiplexed）支持时机 | v0.5.0 明确**不支持**，仅识别并标注 |
| K9 | 依赖 | Issue #7（时区）未修则新字段时区问题叠加 | **建议 R1 开工前先修 #7** |

---

## 8. 全局验收标准

**R1（结果数据管理）**
1. 单次执行产生 500 万采样点，全流程不报错、不 OOM。
2. 累计 1 亿采样点后，§2.7 全部性能指标达标。
3. 同等数据量下磁盘占用较「JSON 存 SQLite」方案降低 ≥ 60%。
4. 判定汇总接口在数据规模增长 1000 倍时延迟增长 < 10 倍（证明读的是摘要层）。
5. 归档/清理提供 `dry_run`，且预览结果与实际执行一致。
6. 存量历史数据迁移后可正常查询，且与迁移前结果逐用例一致。

**R2（DBC）**
1. 导入一份含 ≥100 报文、≥1000 信号的真实 DBC，导入耗时 < 10 s，无报错。
2. 对测试 DBC 中**每一个**信号，本引擎解出的物理值与 `cantools.decode_message()` 完全一致。
3. 既有（未使用 DBC 的）ParserSpec 在升级后结果**逐字段不变**（回归零差异）。
4. 从 DBC 选信号到解析配置可预览，全流程 ≤ 3 次点击。
5. DBC 被删除/信号消失时，相关用例显示明确失效告警，执行时给出可读错误，**不静默降级**。
6. 平台内判定与导出脚本判定，在含 DBC 信号、符号、缩放、枚举的场景下**完全一致**。
7. §3.8 的八类边界场景全部有明确且已测的行为。

---

## 9. 交付物清单

- [ ] 本 PRD（评审通过）
- [ ] 数据库设计与迁移脚本（`docs/DB_DESIGN.md` 同步更新）
- [ ] 新增 API 契约（`docs/API_SPEC.md` 同步更新）
- [ ] DBC 集成使用手册（`docs/DBC_GUIDE.md`）
- [ ] 性能压测脚本（`Test/perf_result_storage.py`）
- [ ] DBC 解析一致性测试（`Test/test_dbc_parser_roundtrip.py`）
- [ ] 解析一致性 CI（运行时 vs 生成脚本）
- [ ] 打包验证报告（体积、冷启动、跨平台）
