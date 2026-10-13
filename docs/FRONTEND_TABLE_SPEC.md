# 前端表格规范（AntD Table / rc-table）

> 制定日期：2026-10-13
> 触发事件：Issue #17「测试用例表格『标签』列文字与其他列重叠」
> 适用范围：`frontend/src/**` 中所有使用 `<Table>` 的页面
> 强制级别：**新增表格必须遵守；存量表格在改动到该页时顺手收敛**

---

## 1. 背景：一个反直觉的底层机制

rc-table 在**任意一列**设置了 `ellipsis` 时，会把整张表从 `table-layout: auto` 切换为
`table-layout: fixed`：

```
node_modules/rc-table/es/Table.js:446-463
tableLayout = 有任意列 ellipsis 且未显式指定 ？ "fixed" : "auto"
```

切换为 `fixed` 后，浏览器**不再按内容分配列宽**，而是按 `<colgroup>` 或（无 `<colgroup>` 时）
**平均分配**。此时如果某列既没写 `width`、单元格内容又不可换行，超宽内容就会**溢出绘制到右侧相邻单元格上**——
这就是「文字重叠」的本质：不是 z-index 也不是绝对定位，是表格式布局的溢出未被裁剪。

**关键推论：只要有一列加了 `ellipsis`，整张表所有列的宽度都必须显式声明，否则就是在抽签。**

---

## 2. 硬性约定（必须遵守）

### 规则 A：每列显式声明 `width`

```tsx
// ✅ 正确
const columns = [
  { title: '用例名称', dataIndex: 'name', width: 220, ellipsis: true },
  { title: '步骤数',   dataIndex: 'steps', width: 80,  align: 'center' },
  { title: '操作',     key: 'action',      width: 160, fixed: 'right' },
]

// ❌ 错误：依赖 auto 布局兜底
const columns = [
  { title: '用例名称', dataIndex: 'name' },
  { title: '标签',     dataIndex: 'tags' },   // 内容长度不可控
]
```

单位 px。最后一列（通常是「操作」）按实际按钮数预留：**按钮数 × 按钮宽 + 24**。

### 规则 B：所有可能溢出的文本列加 `ellipsis`

判断标准：**内容来自用户输入或接口，长度不可控** 的列一律加。

- 名称 / 描述 / 备注 / 标签 / 路径 / ID → 加
- 状态 / 时间 / 数量 / 枚举 → 可视情况不加，但仍要给 `width`

`ellipsis` 会给单元格加 `overflow: hidden; white-space: nowrap; text-overflow: ellipsis`，
这是防止溢出的唯一有效手段。需要看全文时配 `ellipsis: { showTitle: true }` 或自定义 Tooltip。

### 规则 C：单元格渲染多值（Tag / 逗号列表）必须折叠

```tsx
// ✅ 正确：最多展示 2 个，其余折叠进 Tooltip
{
  title: '标签', dataIndex: 'tags', width: 320, ellipsis: true,
  render: (tags: string[] = []) => {
    if (!tags.length) return <Text type="secondary">—</Text>
    const [a, b, ...rest] = tags
    return (
      <span>
        <Tag>{a}</Tag>
        {b && <Tag>{b}</Tag>}
        {rest.length > 0 && (
          <Tooltip title={rest.join('、')}>
            <Tag>+{rest.length}</Tag>
          </Tooltip>
        )}
      </span>
    )
  },
}

// ❌ 错误：把整组 Tag 平铺，宽度随数据量线性增长
render: (tags: string[] = []) => tags.map(t => <Tag key={t}>{t}</Tag>)
```

原因：`.ant-tag` 自带 `display: inline-block; white-space: nowrap`，**永远不换行**，
N 个标签的固有宽度是它们的宽度之和，任何 N 都可能撑爆列宽。

### 规则 D：`<Table>` 必须声明 `scroll={{ x: <合计宽度> }}`

```tsx
<Table
  columns={columns}
  dataSource={data}
  rowKey="id"
  scroll={{ x: 1250 }}     // ≈ 所有列 width 之和 + expand 列 48
/>
```

这样窄屏退化成**横向滚动**，而不是压缩列宽导致重叠。**这是移动端/分屏场景唯一正确的降级方式。**

### 规则 E：优先用 `word-break` 兜底长串

对设备序列号、报文 ID、路径这类**无空格长串**，加：

```tsx
{ ellipsis: true, render: (v: string) => <span style={{ wordBreak: 'break-all' }}>{v}</span> }
```

---

## 3. 模板代码

新写表格页时直接复制：

```tsx
const COL_WIDTH_SUM = 1250

const columns: ColumnsType<Row> = [
  { title: '名称',   dataIndex: 'name',        width: 220, ellipsis: { showTitle: true } },
  { title: '描述',   dataIndex: 'description', width: 200, ellipsis: true,
    render: (v?: string) => v || <Text type="secondary">—</Text> },
  { title: '数量',   dataIndex: 'count',       width: 80,  align: 'center' },
  { title: '标签',   dataIndex: 'tags',        width: 320, ellipsis: true,
    render: (tags: string[] = []) => /* 见规则 C */ },
  { title: '状态',   dataIndex: 'status',      width: 100,
    render: (s: string) => <Tag color={STATUS_COLOR[s]}>{STATUS_LABEL[s]}</Tag> },
  { title: '创建时间', dataIndex: 'created_at', width: 170,
    render: (t: string) => dayjs(t).format('YYYY-MM-DD HH:mm:ss') },
  { title: '操作',   key: 'action',            width: 160, fixed: 'right',
    render: (_, r) => (<Space size={4}>{/* ... */}</Space>) },
]

<Table columns={columns} dataSource={data} rowKey="id" scroll={{ x: COL_WIDTH_SUM }} />
```

---

## 4. Code Review 检查项

在 CR 表格相关改动时逐条确认：

| # | 检查项 | 不通过的后果 |
|---|---|---|
| 1 | 每个 Column 都有 `width`（含 expand/序号列考虑） | `fixed` 布局下平均分配，长内容必溢出 |
| 2 | 长度不可控的文本列都有 `ellipsis` | 溢出绘制到相邻列 |
| 3 | 渲染 Tag 列表的列做了「前 N 个 + 折叠」 | 宽度随数据增长，必然重叠 |
| 4 | `<Table>` 有 `scroll={{ x }}` | 窄屏无横向滚动，压缩后重叠 |
| 5 | 无空格长串有 `word-break` | 单行超宽撑破布局 |
| 6 | 新增/删除操作列按钮时同步调整 `width` | 按钮换行或溢出 |

**自动化辅助**：以下脚本可在改动后用 Playwright 快速实测（见 `.workbuddy/reports/evidence-2026-10-13/probe_ui.py`），
断言「任意单元格内容盒不与右侧单元格起点相交」：

```js
// 核心断言
for (let i = 0; i < cells.length; i++)
  for (const kid of cells[i].kids)
    for (let j = i + 1; j < cells.length; j++)
      if (kid.right > cells[j].left + 1) → 判定重叠
```

---

## 5. 存量页面排查清单

| 页面 | 位置 | 状态 |
|---|---|---|
| TestCases.tsx 用例列表 | `src/pages/TestCases.tsx:337-430` | 🔴 待修（Issue #17，开发中）|
| TestCases.tsx 步骤表 | `src/pages/TestCases.tsx:164-215` | 🔴 待排查 |
| Devices.tsx | `src/pages/Devices.tsx:158-210` | 🔴 待排查 |
| Plugins.tsx | `src/pages/Plugins.tsx:112-165` | 🔴 待排查 |
| Executions.tsx | `src/pages/Executions.tsx:874-950` | 🔴 待排查 |
| ExecutionPlanner.tsx | `src/pages/ExecutionPlanner.tsx`（v0.9.0 新增）| 🔴 待排查 |

修复顺序建议：先修 TestCases（已报缺陷），其余按改动频次排期。

---

## 6. 为什么不用 `table-layout: auto`

实测：把 `#17` 的表格运行时改回 `auto`，重叠确实消失（列宽按内容分配）。但代价是
**表格横向溢出容器**且表头与内容可能错位，必须额外补齐 `scroll={{ x }}` 才能用。

结论：`auto` 只适合列数 ≤ 3、内容极简的表格；业务表格一律走 `fixed` + 显式列宽 + `scroll.x`。
