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
  pass: { color: '#2296C4', icon: <CheckCircleFilled />, label: 'PASS' },
  fail: { color: '#FF7B72', icon: <CloseCircleFilled />, label: 'FAIL' },
  error: { color: '#FF7B72', icon: <ExclamationCircleFilled />, label: 'ERROR' },
  running: { color: '#E8A33D', icon: <LoadingOutlined />, label: 'RUNNING' },
  warn: { color: '#E8A33D', icon: <ExclamationCircleFilled />, label: 'WARN' },
  idle: { color: '#7C8894', icon: <ClockCircleFilled />, label: 'IDLE' },
  skip: { color: '#7C8894', icon: <QuestionCircleFilled />, label: 'SKIP' },
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
