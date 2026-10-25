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

/**
 * Widget metadata — built by a factory (issue #27).
 *
 * ``label`` / ``desc`` / ``defaultTitle`` used to be plain Chinese literals in a
 * module-level constant, so an English user saw Chinese widget names and the
 * catalogue could never translate them. The factory takes ``t`` so the same
 * metadata renders in the active language.
 */
export const makeWidgetMeta = (t: (k: string) => string): Record<WidgetType, WidgetMeta> => ({
  parsed_value: {
    type: 'parsed_value',
    label: t('widget.parsed_value.label'),
    desc: t('widget.parsed_value.desc'),
    icon: <DashboardOutlined />,
    size: { w: 4, h: 5 },
    defaultTitle: t('widget.parsed_value.title'),
    defaultConfig: { field: '' },
    needsTestCase: true,
  },
  trend_chart: {
    type: 'trend_chart',
    label: t('widget.trend_chart.label'),
    desc: t('widget.trend_chart.desc'),
    icon: <LineChartOutlined />,
    size: { w: 8, h: 5 },
    defaultTitle: t('widget.trend_chart.title'),
    defaultConfig: { fields: [], height: 300, show_fail_dots: true },
    needsTestCase: true,
  },
  judge_summary: {
    type: 'judge_summary',
    label: t('widget.judge_summary.label'),
    desc: t('widget.judge_summary.desc'),
    icon: <CheckSquareOutlined />,
    size: { w: 8, h: 7 },
    defaultTitle: t('widget.judge_summary.title'),
    defaultConfig: { max_failures: 20 },
    needsTestCase: true,
  },
  device_status: {
    type: 'device_status',
    label: t('widget.device_status.label'),
    desc: t('widget.device_status.desc'),
    icon: <ApiOutlined />,
    size: { w: 5, h: 6 },
    defaultTitle: t('widget.device_status.title'),
    defaultConfig: {},
  },
  execution_stats: {
    type: 'execution_stats',
    label: t('widget.execution_stats.label'),
    desc: t('widget.execution_stats.desc'),
    icon: <BarChartOutlined />,
    size: { w: 7, h: 6 },
    defaultTitle: t('widget.execution_stats.title'),
    defaultConfig: {},
  },
  comm_log: {
    type: 'comm_log',
    label: t('widget.comm_log.label'),
    desc: t('widget.comm_log.desc'),
    icon: <CodeOutlined />,
    size: { w: 12, h: 8 },
    defaultTitle: t('widget.comm_log.title'),
    defaultConfig: { limit: 12, device_id: '' },
  },
  note: {
    type: 'note',
    label: t('widget.note.label'),
    desc: t('widget.note.desc'),
    icon: <FileTextOutlined />,
    size: { w: 6, h: 4 },
    defaultTitle: t('widget.note.title'),
    defaultConfig: { text: '' },
  },
})

export const makeWidgetList = (t: (k: string) => string): WidgetMeta[] =>
  Object.values(makeWidgetMeta(t))

export function newWidget(type: WidgetType, t: (k: string) => string): DashboardWidget {
  const meta = makeWidgetMeta(t)[type] ?? makeWidgetMeta(t).note
  return {
    id: `w_${Math.random().toString(36).slice(2, 9)}`,
    type,
    title: meta.defaultTitle,
    config: { ...meta.defaultConfig },
  }
}

/** judgment colours — FAIL is a *judgement result*, not a system alarm. */
export const STATUS_COLOR: Record<string, string> = {
  ok: 'var(--app-pass)',
  fail: 'var(--app-fail)',
  unknown: 'var(--app-fg-subtle)',
  error: 'var(--app-warn)',
  passed: 'var(--app-pass)',
  failed: 'var(--app-fail)',
  connected: 'var(--app-pass)',
  disconnected: 'var(--app-fg-subtle)',
}

export const makeStatusLabel = (t: (k: string) => string): Record<string, string> => ({
  ok: 'PASS',
  fail: 'FAIL',
  unknown: t('widget.status.emptyFrame'),
  error: t('widget.status.error'),
  passed: 'PASS',
  failed: 'FAIL',
  connected: t('widget.status.connected'),
  disconnected: t('widget.status.disconnected'),
})
