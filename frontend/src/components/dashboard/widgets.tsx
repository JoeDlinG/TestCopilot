import { useMemo } from 'react'
import {
  Empty, Tag, Statistic, Progress, Table, List, Typography, Spin, Space, Tooltip,
} from 'antd'
import ReactMarkdown from 'react-markdown'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
  Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import type { DashboardWidget, DashboardSnapshot, ParsedPoint } from '../../types'
import { STATUS_COLOR, STATUS_LABEL } from './registry'

const { Text, Paragraph } = Typography

const TREND_COLORS = [
  '#1677ff', '#52c41a', '#fa8c16', '#eb2f96',
  '#722ed1', '#13c2c2', '#f5222d', '#a0d911',
]

export interface WidgetProps {
  widget: DashboardWidget
  snapshot: DashboardSnapshot | null
  big?: boolean
  logs?: any[]
  logsLoading?: boolean
}

/* ------------------------------------------------------------------ */
/* shared bits                                                         */
/* ------------------------------------------------------------------ */

function StatusTag({ status, big }: { status?: string | null; big?: boolean }) {
  if (!status) return <Tag>无数据</Tag>
  const color = STATUS_COLOR[status] || '#8c8c8c'
  return (
    <Tag
      color={color}
      style={{ fontSize: big ? 16 : 12, padding: big ? '2px 12px' : undefined, margin: 0 }}
    >
      {STATUS_LABEL[status] || status}
    </Tag>
  )
}

function fmtNum(v: any): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'number') {
    if (Number.isInteger(v)) return String(v)
    return Number(v.toFixed(6)).toString()
  }
  return String(v)
}

function fmtTime(v?: string | null): string {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return String(v)
  return d.toLocaleString('zh-CN', { hour12: false })
}

/* ------------------------------------------------------------------ */
/* 解析数值卡片                                                        */
/* ------------------------------------------------------------------ */
export function ParsedValueWidget({ widget, snapshot, big }: WidgetProps) {
  const field: string = widget.config?.field || ''
  const latest = field ? snapshot?.parsed?.latest?.[field] : undefined

  if (!field) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="点击右上角齿轮选择要盯的解析字段"
        style={{ marginTop: 30 }}
      />
    )
  }
  if (!snapshot?.test_case_id) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="请先在顶部「数据源」选择一个测试用例"
        style={{ marginTop: 30 }}
      />
    )
  }
  if (!latest) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={`字段「${field}」暂无解析数据`}
        style={{ marginTop: 30 }}
      />
    )
  }

  const color = STATUS_COLOR[latest.status] || '#8c8c8c'
  const display = latest.num !== null && latest.num !== undefined
    ? fmtNum(latest.num)
    : fmtNum(latest.value)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Text type="secondary" style={{ fontSize: big ? 18 : 13 }}>{field}</Text>
        <StatusTag status={latest.status} big={big} />
      </div>

      <div
        style={{
          fontSize: big ? 60 : 40,
          fontWeight: 700,
          lineHeight: 1.1,
          color,
          fontVariantNumeric: 'tabular-nums',
          wordBreak: 'break-all',
        }}
      >
        {display}
      </div>

      {latest.detail && (
        <div style={{ color: '#ff7875', fontSize: big ? 16 : 12 }}>
          {latest.detail}
        </div>
      )}

      <div style={{ marginTop: 'auto', display: 'flex', flexWrap: 'wrap', gap: big ? 20 : 12 }}>
        <span style={{ fontSize: big ? 16 : 12, color: '#8c8c8c' }}>
          最小 {fmtNum(latest.min)}
        </span>
        <span style={{ fontSize: big ? 16 : 12, color: '#8c8c8c' }}>
          最大 {fmtNum(latest.max)}
        </span>
        <span style={{ fontSize: big ? 16 : 12, color: '#8c8c8c' }}>
          均值 {fmtNum(latest.avg)}
        </span>
        <span style={{ fontSize: big ? 16 : 12, color: '#8c8c8c' }}>
          采样 {latest.points}
        </span>
        {latest.fail_count > 0 && (
          <span style={{ fontSize: big ? 16 : 12, color: '#ff4d4f' }}>
            FAIL {latest.fail_count} 次
          </span>
        )}
      </div>
      <div style={{ fontSize: big ? 14 : 11, color: '#bfbfbf' }}>
        更新于 {fmtTime(latest.updated_at)}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 趋势曲线                                                            */
/* ------------------------------------------------------------------ */
function buildTrendRows(series: Record<string, ParsedPoint[]>, fields: string[]) {
  const execOrder = new Map<string, number>()
  const map = new Map<string, any>()

  for (const f of fields) {
    const pts = series[f] || []
    for (const p of pts) {
      const k = `${p.execution_id}#${p.step_index}#${p.seq}`
      let row = map.get(k)
      if (!row) {
        row = {
          _k: k,
          execution_id: p.execution_id,
          step_index: p.step_index,
          seq: p.seq,
          _t: p.completed_at || p.started_at || '',
        }
        map.set(k, row)
      }
      row[f] = p.num
      row[`__st_${f}`] = p.status
      row[`__raw_${f}`] = p.value
    }
  }

  const rows = Array.from(map.values()).sort((a, b) => {
    const oa = execOrder.get(a.execution_id) ?? 0
    const ob = execOrder.get(b.execution_id) ?? 0
    if (oa !== ob) return oa - ob
    if (a.step_index !== b.step_index) return a.step_index - b.step_index
    return a.seq - b.seq
  })
  for (const r of rows) {
    r.label = `#${r.step_index}.${r.seq}`
  }
  return rows
}

export function TrendChartWidget({ widget, snapshot, big }: WidgetProps) {
  const fields: string[] = widget.config?.fields || []
  const showFailDots = widget.config?.show_fail_dots !== false
  const height = Number(widget.config?.height) || 300
  const minV = widget.config?.min_value
  const maxV = widget.config?.max_value

  const rows = useMemo(() => {
    if (!snapshot?.parsed?.series || !fields.length) return []
    return buildTrendRows(snapshot.parsed.series, fields)
  }, [snapshot, fields.join(',')])

  if (!fields.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="点击右上角齿轮勾选要绘制的解析字段"
        style={{ marginTop: 40 }}
      />
    )
  }
  if (!snapshot?.test_case_id) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="请先在顶部「数据源」选择一个测试用例"
        style={{ marginTop: 40 }}
      />
    )
  }
  if (!rows.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无可绘制的数据（解析值需为数值类型）"
        style={{ marginTop: 40 }}
      />
    )
  }

  const fs = big ? 16 : 11
  const renderDot = (field: string) => (props: any): any => {
    const { cx, cy, payload } = props
    if (cx === undefined || cy === undefined) return null
    const st = payload?.[`__st_${field}`]
    if (showFailDots && st === 'fail') {
      return <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={big ? 5 : 3.5} fill="#ff4d4f" stroke="#fff" strokeWidth={1} />
    }
    if (showFailDots && st === 'unknown') return null
    return <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={big ? 3 : 2} fill={TREND_COLORS[fields.indexOf(field) % TREND_COLORS.length]} />
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="label" tick={{ fontSize: fs }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: fs }} width={big ? 74 : 46} />
            <RTooltip
              contentStyle={{ fontSize: fs }}
              formatter={(value: any, name: any, item: any) => [
                `${fmtNum(value)}${item?.payload?.[`__raw_${name}`] !== undefined ? '' : ''}`,
                name,
              ]}
            />
            <Legend wrapperStyle={{ fontSize: fs }} />
            {minV !== undefined && minV !== null && minV !== '' && (
              <ReferenceLine y={Number(minV)} stroke="#faad14" strokeDasharray="4 4" />
            )}
            {maxV !== undefined && maxV !== null && maxV !== '' && (
              <ReferenceLine y={Number(maxV)} stroke="#faad14" strokeDasharray="4 4" />
            )}
            {fields.map((f, i) => (
              <Line
                key={f}
                type="monotone"
                dataKey={f}
                name={f}
                connectNulls
                stroke={TREND_COLORS[i % TREND_COLORS.length]}
                strokeWidth={big ? 3 : 2}
                isAnimationActive={false}
                dot={renderDot(f)}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ fontSize: big ? 14 : 11, color: '#bfbfbf', textAlign: 'right' }}>
        共 {rows.length} 个采样点{showFailDots ? ' · 红点 = FAIL 判定' : ''}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 判定结果汇总                                                        */
/* ------------------------------------------------------------------ */
export function JudgeSummaryWidget({ widget, snapshot, big }: WidgetProps) {
  const j = snapshot?.judgement
  const maxFailures = Number(widget.config?.max_failures) || 20

  if (!snapshot?.test_case_id) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="请先在顶部「数据源」选择一个测试用例"
        style={{ marginTop: 40 }}
      />
    )
  }
  if (!j || j.total === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无判定数据（先执行一次带结果解析的用例）"
        style={{ marginTop: 40 }}
      />
    )
  }

  const fieldRows = Object.entries(j.by_field || {}).map(([name, c]) => ({
    key: name,
    field: name,
    total: c.total,
    ok: c.ok,
    fail: c.fail,
    unknown: c.unknown,
    pass_rate: c.pass_rate,
    last: c.last_value,
    status: c.last_status,
  }))

  const columns = [
    { title: '解析字段', dataIndex: 'field', key: 'field', width: big ? 160 : 120 },
    { title: '采样', dataIndex: 'total', key: 'total', width: 70 },
    { title: 'PASS', dataIndex: 'ok', key: 'ok', width: 70, render: (v: number) => <span style={{ color: '#52c41a' }}>{v}</span> },
    {
      title: 'FAIL', dataIndex: 'fail', key: 'fail', width: 70,
      render: (v: number) => <span style={{ color: v > 0 ? '#ff4d4f' : undefined }}>{v}</span>,
    },
    { title: '空帧', dataIndex: 'unknown', key: 'unknown', width: 70 },
    {
      title: '通过率', dataIndex: 'pass_rate', key: 'pass_rate', width: 90,
      render: (v: number | null) => (v === null ? '-' : `${v}%`),
    },
    {
      title: '最新值', dataIndex: 'last', key: 'last',
      render: (v: any) => fmtNum(v),
    },
    {
      title: '判定', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <StatusTag status={v} />,
    },
  ]

  return (
    <div style={{ height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', gap: big ? 32 : 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <Statistic title="判定总数" value={j.total} valueStyle={{ fontSize: big ? 34 : 24 }} />
        <Statistic title="PASS" value={j.ok} valueStyle={{ color: '#52c41a', fontSize: big ? 34 : 24 }} />
        <Statistic title="FAIL" value={j.fail} valueStyle={{ color: '#ff4d4f', fontSize: big ? 34 : 24 }} />
        <Statistic title="空帧(未判定)" value={j.unknown} valueStyle={{ color: '#8c8c8c', fontSize: big ? 34 : 24 }} />
        <div style={{ flex: 1, minWidth: 160, display: 'flex', alignItems: 'center' }}>
          <Progress
            percent={j.pass_rate ?? 0}
            status={j.fail > 0 ? 'exception' : 'success'}
            strokeWidth={big ? 16 : 10}
            style={{ width: '100%' }}
          />
        </div>
      </div>

      <Table
        size={big ? 'middle' : 'small'}
        dataSource={fieldRows}
        columns={columns}
        pagination={false}
        scroll={{ y: big ? 200 : 150 }}
        style={{ fontSize: big ? 16 : 13 }}
      />

      <div style={{ marginTop: 12 }}>
        <Text strong style={{ fontSize: big ? 18 : 14 }}>
          最近 FAIL 判定（{j.failures.length}）
        </Text>
        {j.failures.length === 0 ? (
          <div style={{ color: '#52c41a', fontSize: big ? 16 : 13, marginTop: 6 }}>
            全部通过，无 FAIL 判定
          </div>
        ) : (
          <List
            size="small"
            dataSource={j.failures.slice(0, maxFailures)}
            style={{ fontSize: big ? 16 : 13 }}
            renderItem={(item: any, idx: number) => (
              <List.Item style={{ padding: '4px 0' }}>
                <Space size={6} wrap>
                  <Tag color="red">{item.field}</Tag>
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {fmtNum(item.value)}
                  </span>
                  <Text type="secondary" style={{ fontSize: big ? 15 : 12 }}>
                    {item.detail || '超出阈值'}
                  </Text>
                  <Tooltip title={item.step_label || ''}>
                    <Text type="secondary" style={{ fontSize: big ? 14 : 11 }}>
                      步骤{item.step_index} · {fmtTime(item.completed_at)}
                    </Text>
                  </Tooltip>
                </Space>
              </List.Item>
            )}
          />
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 设备状态                                                            */
/* ------------------------------------------------------------------ */
export function DeviceStatusWidget({ widget, snapshot, big }: WidgetProps) {
  const devices = snapshot?.devices?.list || []
  if (!devices.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无设备" style={{ marginTop: 30 }} />
  }
  return (
    <div style={{ height: '100%', overflow: 'auto' }}>
      <div style={{ marginBottom: 8, fontSize: big ? 18 : 13, color: '#8c8c8c' }}>
        共 {snapshot?.devices?.total ?? 0} 台，{snapshot?.devices?.connected ?? 0} 台已连接
      </div>
      <List
        size="small"
        dataSource={devices}
        style={{ fontSize: big ? 17 : 13 }}
        renderItem={(d: any) => (
          <List.Item style={{ padding: '6px 0' }}>
            <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8 }}>
              <StatusTag status={d.status} big={big} />
              <span style={{ fontWeight: 500 }}>{d.name}</span>
              <Text type="secondary" style={{ fontSize: big ? 15 : 12 }}>
                {d.protocol}
                {d.address ? ` · ${d.address}` : ''}
              </Text>
            </div>
          </List.Item>
        )}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 执行统计                                                            */
/* ------------------------------------------------------------------ */
export function ExecutionStatsWidget({ widget, snapshot, big }: WidgetProps) {
  const e = snapshot?.executions
  if (!e) return <Spin />
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 12 }}>
      <div style={{ display: 'flex', gap: big ? 40 : 24, flexWrap: 'wrap' }}>
        <Statistic title="执行总数" value={e.total} valueStyle={{ fontSize: big ? 36 : 26 }} />
        <Statistic title="通过" value={e.passed} valueStyle={{ color: '#52c41a', fontSize: big ? 36 : 26 }} />
        <Statistic title="失败" value={e.failed} valueStyle={{ color: '#ff4d4f', fontSize: big ? 36 : 26 }} />
        <Statistic title="运行中" value={e.running} valueStyle={{ color: '#1677ff', fontSize: big ? 36 : 26 }} />
      </div>
      <Progress
        percent={e.pass_rate ?? 0}
        status={e.failed > 0 ? 'exception' : 'success'}
        strokeWidth={big ? 18 : 12}
        format={(p) => `通过率 ${p ?? 0}%`}
      />
      {e.recent?.length > 0 && (
        <div style={{ fontSize: big ? 15 : 12, color: '#8c8c8c' }}>
          最近：{e.recent[0].id?.slice(0, 12)} · {STATUS_LABEL[e.recent[0].status] || e.recent[0].status}
          {' · '}{fmtTime(e.recent[0].created_at)}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 通信日志                                                            */
/* ------------------------------------------------------------------ */
export function CommLogWidget({ widget, big, logs, logsLoading }: WidgetProps) {
  const limit = Number(widget.config?.limit) || 12
  const rows = (logs || []).slice(0, limit)
  if (logsLoading && !rows.length) return <Spin style={{ marginTop: 20 }} />
  if (!rows.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通信日志" style={{ marginTop: 30 }} />
  }
  return (
    <div style={{ height: '100%', overflow: 'auto', fontFamily: 'monospace', fontSize: big ? 15 : 12 }}>
      <Table
        size="small"
        dataSource={rows}
        pagination={false}
        rowKey="id"
        columns={[
          {
            title: '方向', dataIndex: 'direction', width: big ? 110 : 80,
            render: (v: string) => (
              <Tag color={v === 'sent' ? 'blue' : 'green'} style={{ fontSize: big ? 14 : 11 }}>
                {v === 'sent' ? '发送' : '接收'}
              </Tag>
            ),
          },
          { title: '协议', dataIndex: 'protocol', width: big ? 110 : 80 },
          {
            title: '数据', dataIndex: 'raw_data',
            render: (v: string) => (
              <span style={{ wordBreak: 'break-all' }}>{v || '-'}</span>
            ),
          },
          {
            title: '时间', dataIndex: 'timestamp', width: big ? 200 : 160,
            render: (v: string) => fmtTime(v),
          },
        ]}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* 文本备注                                                            */
/* ------------------------------------------------------------------ */
export function NoteWidget({ widget, big }: WidgetProps) {
  const text: string = widget.config?.text || ''
  if (!text.trim()) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="点击右上角齿轮填写备注（支持 Markdown）"
        style={{ marginTop: 30 }}
      />
    )
  }
  return (
    <div style={{ height: '100%', overflow: 'auto', fontSize: big ? 18 : 14 }}>
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* dispatcher                                                          */
/* ------------------------------------------------------------------ */
export function WidgetBody(props: WidgetProps) {
  switch (props.widget.type) {
    case 'parsed_value':
      return <ParsedValueWidget {...props} />
    case 'trend_chart':
      return <TrendChartWidget {...props} />
    case 'judge_summary':
      return <JudgeSummaryWidget {...props} />
    case 'device_status':
      return <DeviceStatusWidget {...props} />
    case 'execution_stats':
      return <ExecutionStatsWidget {...props} />
    case 'comm_log':
      return <CommLogWidget {...props} />
    case 'note':
      return <NoteWidget {...props} />
    default:
      return <Paragraph type="secondary">未知的组件类型：{(props.widget as any).type}</Paragraph>
  }
}
