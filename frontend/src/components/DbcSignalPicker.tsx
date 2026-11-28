import { useCallback, useEffect, useState } from 'react'
import {
  Modal, Button, Space, Input, Table, Tag, Typography, Empty, Alert, message,
} from 'antd'
import {
  ArrowLeftOutlined, SearchOutlined, DatabaseOutlined, FileTextOutlined,
} from '@ant-design/icons'
import { dbcAPI } from '../services/api'
import { extractItemsCompat, unwrapPayload, handleApiError } from '../services/apiHelper'
import { useI18n } from '../i18n'
import type { DbcFile, DbcMessage, DbcSignal } from '../types'

const { Text } = Typography

type Props = {
  open: boolean
  onCancel: () => void
  /** Called with the generated parser spec for the selected signal. */
  onSelect: (spec: Record<string, any>) => void
}

function byteOrderLabel(bo?: string): string {
  return bo === 'big_endian' ? 'Motorola' : 'Intel'
}

/** Pick a DBC signal and turn it into a platform parser spec. */
export default function DbcSignalPicker({ open, onCancel, onSelect }: Props) {
  const { t } = useI18n()
  const [files, setFiles] = useState<DbcFile[]>([])
  const [current, setCurrent] = useState<DbcFile | null>(null)
  const [loading, setLoading] = useState(false)
  const [pickingId, setPickingId] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await dbcAPI.listFiles()
      // /api/dbc/files returns a bare array, not the {code,data} envelope used
      // by other routers — the legacy envelope-only helper always yielded [].
      setFiles(extractItemsCompat<DbcFile>(res))
    } catch (err) {
      setFiles([])
      handleApiError(err, t('dbc.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => {
    if (open) {
      setCurrent(null)
      setQuery('')
      void loadFiles()
    }
  }, [open, loadFiles])

  // A DBC imported while this dialog is mounted must appear without a remount.
  useEffect(() => {
    const refresh = () => { void loadFiles() }
    window.addEventListener('aitestlab:dbc-changed', refresh)
    return () => window.removeEventListener('aitestlab:dbc-changed', refresh)
  }, [loadFiles])

  const openFile = async (file: DbcFile) => {
    setLoading(true)
    try {
      const res = await dbcAPI.getFile(file.id)
      const data = unwrapPayload<DbcFile>(res)
      if (!data || !Array.isArray(data.messages)) {
        throw new Error(t('dbc.loadFailed'))
      }
      setCurrent(data)
      setQuery('')
    } catch (err) {
      handleApiError(err, t('dbc.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  const pickSignal = async (signal: DbcSignal) => {
    setPickingId(signal.id)
    try {
      const res = await dbcAPI.signalParserSpec(signal.id)
      const spec = unwrapPayload<Record<string, any>>(res)
      // Never insert a blank parser row when the API returns no payload.
      if (!spec || !spec.name) {
        throw new Error('empty ParserSpec')
      }
      onSelect(spec)
      onCancel()
    } catch (err) {
      handleApiError(err, t('dbc.importFailed'))
    } finally {
      setPickingId(null)
    }
  }

  const fileColumns = [
    {
      title: t('dbc.fileName'), dataIndex: 'name', width: 180,
      render: (v: string) => <Space><FileTextOutlined /><Text>{v}</Text></Space>,
    },
    { title: t('dbc.messageCount'), dataIndex: 'message_count', width: 90 },
    { title: t('dbc.signalCount'), dataIndex: 'signal_count', width: 90 },
    {
      title: t('dbc.actions'), key: 'actions', width: 90,
      render: (_: any, r: DbcFile) => (
        <Button size="small" type="link" onClick={() => openFile(r)}>{t('dbc.view')}</Button>
      ),
    },
  ]

  const messages = current?.messages || []
  const q = query.trim().toLowerCase()
  const filtered = messages.filter(m => {
    if (!q) return true
    return m.name.toLowerCase().includes(q)
      || String(m.message_id).includes(q)
      || (m.signals || []).some(s => s.name.toLowerCase().includes(q))
  })

  const signalColumns = [
    { title: t('dbc.signal'), dataIndex: 'name', width: 180 },
    { title: t('dbc.start'), dataIndex: 'start', width: 80 },
    { title: t('dbc.length'), dataIndex: 'length', width: 80 },
    {
      title: t('dbc.byteOrder'), dataIndex: 'byte_order', width: 100,
      render: (v: string) => <Tag>{byteOrderLabel(v)}</Tag>,
    },
    { title: t('dbc.factor'), dataIndex: 'factor', width: 80 },
    { title: t('dbc.offset'), dataIndex: 'offset', width: 80 },
    { title: t('dbc.unit'), dataIndex: 'physical_unit', width: 90, render: (v: string) => v || '-' },
    {
      title: t('dbc.actions'), key: 'actions', width: 100,
      render: (_: any, s: DbcSignal) => (
        <Button
          size="small"
          type="primary"
          ghost
          loading={pickingId === s.id}
          onClick={() => pickSignal(s)}
        >
          {t('dbc.generateParser')}
        </Button>
      ),
    },
  ]

  return (
    <Modal
      title={<Space><DatabaseOutlined /><span>{t('parser.fromDbcTitle')}</span></Space>}
      open={open}
      onCancel={onCancel}
      footer={null}
      width={760}
      destroyOnClose
    >
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message={t('parser.fromDbcHint')} />

      {!current ? (
        <>
          {files.length === 0 && !loading ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('dbc.empty')}
              style={{ padding: 32 }}
            />
          ) : (
            <Table<DbcFile>
              rowKey="id"
              size="small"
              loading={loading}
              dataSource={files}
              pagination={false}
              columns={fileColumns as any}
            />
          )}
        </>
      ) : (
        <>
          <Space style={{ marginBottom: 10, width: '100%', justifyContent: 'space-between' }}>
            <Button size="small" icon={<ArrowLeftOutlined />} onClick={() => setCurrent(null)}>
              {t('dbc.back')}
            </Button>
            <Input
              allowClear
              size="small"
              prefix={<SearchOutlined />}
              placeholder={t('dbc.searchPlaceholder')}
              style={{ width: 260 }}
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </Space>
          <Table<DbcMessage>
            rowKey="id"
            size="small"
            loading={loading}
            dataSource={filtered}
            pagination={false}
            scroll={{ x: 1000 }}
            expandable={{
              expandedRowRender: (m: DbcMessage) => (
                <div style={{ padding: '4px 8px' }}>
                  <Table<DbcSignal>
                    rowKey="id"
                    size="small"
                    dataSource={m.signals || []}
                    pagination={false}
                    columns={signalColumns as any}
                    scroll={{ x: 900 }}
                  />
                </div>
              ),
            }}
            columns={[
              { title: t('dbc.canId'), dataIndex: 'message_id', width: 100, render: (v: number) => <Text code>0x{v.toString(16).toUpperCase()}</Text> },
              { title: t('dbc.message'), dataIndex: 'name', width: 220 },
              { title: t('dbc.dlc'), dataIndex: 'dlc', width: 80 },
              {
                title: t('dbc.signalCount'), dataIndex: 'signals', width: 90,
                render: (signals: DbcSignal[]) => (signals || []).length,
              },
            ]}
          />
        </>
      )}
    </Modal>
  )
}
