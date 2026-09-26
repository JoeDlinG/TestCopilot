import { Empty } from 'antd'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'

const COLORS = [
  '#1677ff', '#52c41a', '#fa8c16', '#eb2f96',
  '#722ed1', '#13c2c2', '#f5222d', '#a0d911',
]

/** Best-effort numeric view of a parsed value ("0x85" -> 133). */
export function toNumber(v: any): number | null {
  if (v === null || v === undefined) return null
  if (typeof v === 'boolean') return v ? 1 : 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  const s = String(v).trim()
  if (!s) return null
  if (/^0x[0-9a-f]+$/i.test(s)) return parseInt(s, 16)
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}

type Props = {
  /** one row per sample; xKey holds the axis label, each field is a key */
  data: any[]
  fields: string[]
  xKey?: string
  height?: number
  /** large-screen mode: bigger fonts and thicker lines */
  big?: boolean
}

export default function ParsedTrendChart({
  data, fields, xKey = 'label', height = 260, big = false,
}: Props) {
  if (!fields.length || !data.length) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 40 }}
        description="暂无可绘制的数据（解析值需为数值类型）"
      />
    )
  }

  const fs = big ? 16 : 11

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={xKey} tick={{ fontSize: fs }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: fs }} width={big ? 74 : 46} />
        <Tooltip contentStyle={{ fontSize: fs }} />
        <Legend wrapperStyle={{ fontSize: fs }} />
        {fields.map((f, i) => (
          <Line
            key={f}
            type="monotone"
            dataKey={f}
            name={f}
            connectNulls
            stroke={COLORS[i % COLORS.length]}
            strokeWidth={big ? 3 : 2}
            dot={{ r: big ? 4 : 2 }}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}
