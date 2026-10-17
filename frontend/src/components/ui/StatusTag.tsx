import { Tag, Tooltip } from 'antd'
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ClockCircleFilled,
  ExclamationCircleFilled,
  QuestionCircleFilled,
  LoadingOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

export type StatusKind = 'pass' | 'fail' | 'error' | 'running' | 'warn' | 'idle' | 'skip'

const STATUS_MAP: Record<StatusKind, { color: string; icon: ReactNode; label: string }> = {
  pass: { color: 'var(--app-pass)', icon: <CheckCircleFilled />, label: 'PASS' },
  fail: { color: 'var(--app-fail)', icon: <CloseCircleFilled />, label: 'FAIL' },
  error: { color: 'var(--app-fail)', icon: <ExclamationCircleFilled />, label: 'ERROR' },
  running: { color: 'var(--app-warn)', icon: <LoadingOutlined />, label: 'RUNNING' },
  warn: { color: 'var(--app-warn)', icon: <ExclamationCircleFilled />, label: 'WARN' },
  idle: { color: 'var(--app-fg-subtle)', icon: <ClockCircleFilled />, label: 'IDLE' },
  skip: { color: 'var(--app-fg-subtle)', icon: <QuestionCircleFilled />, label: 'SKIP' },
}

interface Props {
  kind: StatusKind
  /** Override the default label (e.g. a translated string). */
  text?: string
  /** Extra explanation shown on hover. */
  tooltip?: string
  size?: 'small' | 'default'
}

/**
 * Status is always encoded by **icon + text + colour** (issue #20) — never by
 * colour alone, so it stays readable for colour-blind users and in greyscale.
 */
export default function StatusTag({ kind, text, tooltip, size = 'default' }: Props) {
  const spec = STATUS_MAP[kind] ?? STATUS_MAP.idle
  const tag = (
    <Tag color={spec.color} icon={spec.icon} style={{ marginInlineEnd: 0, fontSize: size === 'small' ? 11 : 12 }}>
      {text ?? spec.label}
    </Tag>
  )
  return tooltip ? <Tooltip title={tooltip}>{tag}</Tooltip> : tag
}
