import { Table } from 'antd'
import type { TableProps } from 'antd'
import { componentTokens } from '../../theme/tokens'

type Props<RecordType> = TableProps<RecordType> & {
  /** Total width for horizontal scrolling. Defaults to the design token. */
  scrollX?: number
}

/**
 * Table with the column-width contract enforced.
 *
 * As soon as any column sets ``ellipsis``, antd switches the table to
 * ``table-layout: fixed``. Without explicit widths the remaining space is then
 * distributed by content, so a long cell spills into its neighbour (#17 / #19).
 * This wrapper guarantees ``scroll.x`` and warns (in dev) about columns that
 * forgot to declare a width.
 */
export default function DataTable<RecordType extends object>({
  columns,
  scroll,
  scrollX,
  size = 'small',
  ...rest
}: Props<RecordType>) {
  if (import.meta.env.DEV && Array.isArray(columns)) {
    const missing = (columns as any[])
      .filter((c) => !c.width && !c.children)
      .map((c) => String(c.key ?? c.dataIndex ?? '?'))
    if (missing.length) {
      // eslint-disable-next-line no-console
      console.warn(
        `[DataTable] columns without an explicit width: ${missing.join(', ')}. ` +
          'Declare a width so ellipsis cannot push content into the next column.',
      )
    }
  }

  return (
    <Table<RecordType>
      size={size}
      columns={columns}
      scroll={{ x: scrollX ?? componentTokens.tableScrollX, ...(scroll as object) }}
      {...rest}
    />
  )
}
