import { Tooltip } from 'antd'

interface Props {
  children: React.ReactNode
  /** Right-align numeric/ID/time values per the layout spec. */
  align?: 'left' | 'right'
  maxWidth?: number
  tooltip?: boolean
}

/** Monospaced, optionally right-aligned text for IDs / time / numbers. */
export default function MonoText({ children, align = 'right', maxWidth, tooltip = true }: Props) {
  const node = (
    <span
      style={{
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
        fontVariantNumeric: 'tabular-nums',
        display: 'inline-block',
        textAlign: align,
        maxWidth,
        overflow: maxWidth ? 'hidden' : undefined,
        textOverflow: maxWidth ? 'ellipsis' : undefined,
        whiteSpace: maxWidth ? 'nowrap' : undefined,
        verticalAlign: 'bottom',
      }}
    >
      {children}
    </span>
  )
  return tooltip && maxWidth ? <Tooltip title={children}>{node}</Tooltip> : node
}
