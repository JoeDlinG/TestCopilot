import type { ReactNode } from 'react'
import { Space } from 'antd'

interface Props {
  title: ReactNode
  /** Optional short description under the title. */
  subtitle?: ReactNode
  /** Right-aligned actions. */
  extra?: ReactNode
  children: ReactNode
}

/** Uniform page shell: title / actions / padded content. */
export default function PageContainer({ title, subtitle, extra, children }: Props) {
  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 16,
          marginBottom: 16,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{title}</h3>
          {subtitle && (
            <div style={{ marginTop: 4, fontSize: 12, opacity: 0.65 }}>{subtitle}</div>
          )}
        </div>
        {extra && <Space wrap>{extra}</Space>}
      </div>
      {children}
    </div>
  )
}
