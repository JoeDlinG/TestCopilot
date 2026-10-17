import { Empty } from 'antd'
import type { ReactNode } from 'react'

interface Props {
  description?: ReactNode
  /** Guidance shown under the description — no bare blank pages (#20). */
  hint?: ReactNode
  icon?: ReactNode
  action?: ReactNode
}

/** Empty state that always tells the user what to do next. */
export default function EmptyState({ description = '暂无数据', hint, icon, action }: Props) {
  return (
    <Empty
      image={icon ?? Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <div style={{ color: 'inherit' }}>
          <div>{description}</div>
          {hint && (
            <div style={{ opacity: 0.65, fontSize: 12, marginTop: 4 }}>{hint}</div>
          )}
        </div>
      }
    >
      {action}
    </Empty>
  )
}
