import type { ReactNode } from 'react'
import {
  DashboardOutlined, LineChartOutlined, CheckSquareOutlined,
  ApiOutlined, BarChartOutlined, CodeOutlined, FileTextOutlined,
} from '@ant-design/icons'
import type { DashboardWidget, WidgetType } from '../../types'

export interface WidgetMeta {
  type: WidgetType
  label: string
  desc: string
  icon: ReactNode
  /** default grid size (12-column desktop grid, rowHeight 40) */
  size: { w: number; h: number }
  defaultTitle: string
  defaultConfig: Record<string, any>
  /** widget reads parsed values → needs data_source.test_case_id */
  needsTestCase?: boolean
}

export const WIDGET_META: Record<WidgetType, WidgetMeta> = {
  parsed_value: {
    type: 'parsed_value',
    label: '解析数值卡片',
    desc: '盯一个解析量：最新值 + PASS/FAIL 判定徽标，越界变红',
    icon: <DashboardOutlined />,
    size: { w: 4, h: 5 },
    defaultTitle: '解析数值',
    defaultConfig: { field: '' },
    needsTestCase: true,
  },
  trend_chart: {
    type: 'trend_chart',
    label: '趋势曲线',
    desc: '解析值随时间变化，FAIL 点标红（长稳测试看漂移）',
    icon: <LineChartOutlined />,
    size: { w: 8, h: 5 },
    defaultTitle: '解析值趋势',
    defaultConfig: { fields: [], height: 300, show_fail_dots: true },
    needsTestCase: true,
  },
  judge_summary: {
    type: 'judge_summary',
    label: '判定结果汇总',
    desc: '各字段 PASS/FAIL 统计 + 最近 FAIL 明细（判定结果，非告警）',
    icon: <CheckSquareOutlined />,
    size: { w: 8, h: 7 },
    defaultTitle: '判定结果汇总',
    defaultConfig: { max_failures: 20 },
    needsTestCase: true,
  },
  device_status: {
    type: 'device_status',
    label: '设备状态',
    desc: '设备在线/离线、协议、连接地址',
    icon: <ApiOutlined />,
    size: { w: 5, h: 6 },
    defaultTitle: '设备状态',
    defaultConfig: {},
  },
  execution_stats: {
    type: 'execution_stats',
    label: '执行统计',
    desc: '总执行次数 / 通过 / 失败 / 运行中 / 通过率',
    icon: <BarChartOutlined />,
    size: { w: 7, h: 6 },
    defaultTitle: '执行统计',
    defaultConfig: {},
  },
  comm_log: {
    type: 'comm_log',
    label: '通信日志',
    desc: '最新收发报文记录',
    icon: <CodeOutlined />,
    size: { w: 12, h: 8 },
    defaultTitle: '通信日志',
    defaultConfig: { limit: 12, device_id: '' },
  },
  note: {
    type: 'note',
    label: '文本备注',
    desc: '接线说明 / 操作 SOP，支持 Markdown',
    icon: <FileTextOutlined />,
    size: { w: 6, h: 4 },
    defaultTitle: '备注',
    defaultConfig: { text: '' },
  },
}

export const WIDGET_LIST: WidgetMeta[] = [
  WIDGET_META.parsed_value,
  WIDGET_META.trend_chart,
  WIDGET_META.judge_summary,
  WIDGET_META.device_status,
  WIDGET_META.execution_stats,
  WIDGET_META.comm_log,
  WIDGET_META.note,
]

export function newWidget(type: WidgetType): DashboardWidget {
  const meta = WIDGET_META[type] ?? WIDGET_META.note
  return {
    id: `w_${Math.random().toString(36).slice(2, 9)}`,
    type,
    title: meta.defaultTitle,
    config: { ...meta.defaultConfig },
  }
}

/** judgment colours — FAIL is a *judgement result*, not a system alarm. */
export const STATUS_COLOR: Record<string, string> = {
  ok: '#52c41a',
  fail: '#ff4d4f',
  unknown: '#8c8c8c',
  error: '#fa8c16',
  passed: '#52c41a',
  failed: '#ff4d4f',
  connected: '#52c41a',
  disconnected: '#8c8c8c',
}

export const STATUS_LABEL: Record<string, string> = {
  ok: 'PASS',
  fail: 'FAIL',
  unknown: '空帧',
  error: '错误',
  passed: 'PASS',
  failed: 'FAIL',
  connected: '已连接',
  disconnected: '未连接',
}
