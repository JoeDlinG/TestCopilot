/**
 * Markdown renderer for the help centre.
 *
 * Plain `react-markdown` does not understand GFM pipe tables — the manuals are
 * full of them, and they came out as runs of `| a | b |` text. `remark-gfm`
 * would fix it, but adding a dependency here is not free (the install failed
 * against this node_modules tree), and AntD tables look better inside the app
 * anyway. So the document is split into text runs and table blocks: tables go
 * to AntD ``Table``, everything else still goes through ``ReactMarkdown``.
 */
import { Table, Typography } from 'antd'
import ReactMarkdown from 'react-markdown'

const { Text } = Typography

type Block =
  | { kind: 'md'; text: string }
  | { kind: 'table'; head: string[]; rows: string[][] }

/** `| a | b |` -> ['a', 'b'] */
function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((c) => c.trim())
}

const isSeparator = (line: string) => /^\|?[\s:|-]+\|?$/.test(line.trim()) && line.includes('-')

export function parseBlocks(text: string): Block[] {
  const lines = text.split('\n')
  const blocks: Block[] = []
  let buffer: string[] = []

  const flush = () => {
    if (buffer.length) {
      blocks.push({ kind: 'md', text: buffer.join('\n') })
      buffer = []
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const next = lines[i + 1]
    // A table starts with a pipe row immediately followed by the |---| divider.
    if (line.trim().startsWith('|') && next !== undefined && isSeparator(next)) {
      flush()
      const head = splitRow(line)
      const rows: string[][] = []
      i += 2
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        rows.push(splitRow(lines[i]))
        i++
      }
      i--
      blocks.push({ kind: 'table', head, rows })
      continue
    }
    buffer.push(line)
  }
  flush()
  return blocks
}

/** Render `code`, **bold** and _italic_ inside a table cell. */
function InlineCell({ value }: { value: string }) {
  if (!value) return <Text type="secondary">—</Text>
  const parts = value.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean)
  return (
    <span style={{ fontSize: 12 }}>
      {parts.map((part, i) => {
        if (part.startsWith('`') && part.endsWith('`')) {
          return (
            <code
              key={i}
              style={{
                fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
                fontSize: 11.5,
                padding: '0 4px',
                borderRadius: 4,
                background: 'var(--app-surface-muted)',
                border: '1px solid var(--app-border)',
              }}
            >
              {part.slice(1, -1)}
            </code>
          )
        }
        if (part.startsWith('**') && part.endsWith('**')) {
          return <strong key={i}>{part.slice(2, -2)}</strong>
        }
        return <span key={i}>{part}</span>
      })}
    </span>
  )
}

export default function MarkdownDoc({ text }: { text: string }) {
  const blocks = parseBlocks(text)
  return (
    <div className="md-body">
      {blocks.map((b, i) => {
        if (b.kind === 'md') {
          return <ReactMarkdown key={i}>{b.text}</ReactMarkdown>
        }
        const columns = b.head.map((title, ci) => ({
          title,
          dataIndex: String(ci),
          key: String(ci),
          render: (v: string) => <InlineCell value={v} />,
        }))
        const data = b.rows.map((r, ri) => {
          const row: Record<string, string> = { _k: String(ri) }
          r.forEach((cell, ci) => { row[String(ci)] = cell })
          return row
        })
        return (
          <Table
            key={i}
            size="small"
            bordered
            rowKey="_k"
            columns={columns}
            dataSource={data}
            pagination={false}
            scroll={{ x: 'max-content' }}
            style={{ margin: '10px 0', fontSize: 12.5 }}
          />
        )
      })}
    </div>
  )
}
