import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button, Modal, Space, Input, Table, Tag, Typography, message, Tooltip,
  Alert, Empty,
} from 'antd'
import {
  UploadOutlined, ArrowLeftOutlined, CopyOutlined, SearchOutlined,
  DatabaseOutlined, FileTextOutlined,
} from '@ant-design/icons'
import { dbcAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import { useI18n } from '../i18n'
import { DataTable, PageContainer } from '../components/ui'
import type { DbcFile, DbcMessage, DbcSignal } from '../types'

const { Text } = Typography

function fmtDate(v?: string | null): string {
  if (!v) return '-'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString()
}

function byteOrderLabel(bo?: string): string {
  return bo === 'big_endian' ? 'Motorola' : 'Intel'
}

export default function Dbc() {
  const { t } = useI18n()
  const [files, setFiles] = useState<DbcFile[]>([])
  const [loading, setLoading] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importing, setImporting] = useState(false)
  const [detail, setDetail] = useState<DbcFile | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [query, setQuery] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const loadFiles = useCallback(async () => {
    setLoading(true)
    try {
      const res = await dbcAPI.listFiles()
      setFiles(extractItems(res))
    } catch (err) {
      handleApiError(err, t('dbc.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { loadFiles() }, [loadFiles])

  const openDetail = async (file: DbcFile) => {
    setDetailLoading(true)
    try {
      const res = await dbcAPI.getFile(file.id)
      setDetail(res.data)
      setQuery('')
    } catch (err) {
      handleApiError(err, t('dbc.loadFailed'))
    } finally {
      setDetailLoading(false)
    }
  }

  const doImport = async (file: File) => {
    setImporting(true)
    try {
      await dbcAPI.upload(file)
      message.success(t('dbc.importSuccess'))
      setImportOpen(false)
      await loadFiles()
    } catch (err) {
      handleApiError(err, t('dbc.importFailed'))
    } finally {
      setImporting(false)
    }
  }

  const copySpec = async (signal: DbcSignal) => {
    try {
      const res = await dbcAPI.signalParserSpec(signal.id)
      const spec = res.data
      await navigator.clipboard.writeText(JSON.stringify(spec, null, 2))
      message.success(t('dbc.copySpecDone'))
    } catch (err) {
      handleApiError(err, t('dbc.importFailed'))
    }
  }

  // ---- list view ----
  if (!detail) {
    return (
      <PageContainer
        title={t('dbc.title')}
        subtitle={t('dbc.subtitle')}
        extra={
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
            {t('dbc.import')}
          </Button>
        }
      >
        <input
          ref={fileInput}
          type="file"
          accept=".dbc,.DBC,text/plain"
          style={{ display: 'none' }}
          onChange={e => {
            const f = e.target.files?.[0]
            if (f) doImport(f)
            e.target.value = ''
          }}
        />
        {files.length === 0 && !loading ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('dbc.empty')}
            style={{ padding: 48 }}
          />
        ) : (
          <DataTable<DbcFile>
            rowKey="id"
            loading={loading}
            dataSource={files}
            pagination={false}
            columns={[
              {
                title: t('dbc.fileName'), dataIndex: 'name', width: 220,
                render: (v: string, r: DbcFile) => (
                  <Space>
                    <FileTextOutlined style={{ color: 'var(--app-text-secondary)' }} />
                    <Text>{v}</Text>
                    {r.filename && <Text type="secondary" style={{ fontSize: 12 }}>({r.filename})</Text>}
                  </Space>
                ),
              },
              { title: t('dbc.messageCount'), dataIndex: 'message_count', width: 110 },
              { title: t('dbc.signalCount'), dataIndex: 'signal_count', width: 110 },
              { title: t('dbc.createdAt'), dataIndex: 'created_at', width: 190, render: fmtDate },
              {
                title: t('dbc.actions'), key: 'actions', width: 120, fixed: 'right',
                render: (_: any, r: DbcFile) => (
                  <Button size="small" type="link" onClick={() => openDetail(r)}>
                    {t('dbc.view')}
                  </Button>
                ),
              },
            ]}
          />
        )}

        <Modal
          title={<Space><DatabaseOutlined /><span>{t('dbc.importTitle')}</span></Space>}
          open={importOpen}
          onCancel={() => setImportOpen(false)}
          onOk={() => fileInput.current?.click()}
          confirmLoading={importing}
          okText={t('dbc.import')}
          cancelText={t('common.cancel')}
          destroyOnClose
        >
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={t('dbc.importHint')}
          />
        </Modal>
      </PageContainer>
    )
  }

  // ---- detail view ----
  const messages = detail.messages || []
  const q = query.trim().toLowerCase()
  const filtered = messages.filter(m => {
    if (!q) return true
    const hitMsg = m.name.toLowerCase().includes(q) || String(m.message_id).includes(q)
    const hitSig = (m.signals || []).some(s => s.name.toLowerCase().includes(q))
    return hitMsg || hitSig
  })

  const signalColumns = [
    { title: t('dbc.signal'), dataIndex: 'name', width: 180 },
    { title: t('dbc.start'), dataIndex: 'start', width: 80 },
    { title: t('dbc.length'), dataIndex: 'length', width: 80 },
    {
      title: t('dbc.byteOrder'), dataIndex: 'byte_order', width: 100,
      render: (v: string) => <Tag>{byteOrderLabel(v)}</Tag>,
    },
    {
      title: t('dbc.signed'), dataIndex: 'is_signed', width: 90,
      render: (v: boolean) => <Tag color={v ? 'orange' : 'default'}>{v ? '±' : '+'}</Tag>,
    },
    { title: t('dbc.factor'), dataIndex: 'factor', width: 80 },
    { title: t('dbc.offset'), dataIndex: 'offset', width: 80 },
    { title: t('dbc.unit'), dataIndex: 'physical_unit', width: 90, render: (v: string) => v || '-' },
    {
      title: t('dbc.actions'), key: 'actions', width: 130, fixed: 'right',
      render: (_: any, s: DbcSignal) => (
        <Tooltip title={t('dbc.copySpec')}>
          <Button size="small" type="link" icon={<CopyOutlined />} onClick={() => copySpec(s)}>
            {t('dbc.copySpec')}
          </Button>
        </Tooltip>
      ),
    },
  ]

  return (
    <PageContainer
      title={t('dbc.title')}
      subtitle={`${detail.name} · ${detail.message_count} ${t('dbc.messageCount')} / ${detail.signal_count} ${t('dbc.signalCount')}`}
      extra={
        <Space>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={t('dbc.searchPlaceholder')}
            style={{ width: 240 }}
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <Button icon={<ArrowLeftOutlined />} onClick={() => setDetail(null)}>
            {t('dbc.back')}
          </Button>
        </Space>
      }
    >
      <Table<DbcMessage>
        rowKey="id"
        size="small"
        loading={detailLoading}
        dataSource={filtered}
        pagination={false}
        scroll={{ x: 1100 }}
        expandable={{
          expandedRowRender: (m: DbcMessage) => (
            <div style={{ padding: '4px 8px' }}>
              {m.comment && (
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                  {m.comment}
                </Text>
              )}
              <Table<DbcSignal>
                rowKey="id"
                size="small"
                dataSource={m.signals || []}
                pagination={false}
                columns={signalColumns as any}
                scroll={{ x: 1000 }}
              />
            </div>
          ),
        }}
        columns={[
          { title: t('dbc.canId'), dataIndex: 'message_id', width: 100, render: (v: number) => <Text code>0x{v.toString(16).toUpperCase()}</Text> },
          { title: t('dbc.message'), dataIndex: 'name', width: 220 },
          { title: t('dbc.dlc'), dataIndex: 'dlc', width: 80 },
          {
            title: t('dbc.signalCount'), dataIndex: 'signals', width: 100,
            render: (signals: DbcSignal[]) => (signals || []).length,
          },
        ]}
      />
      {filtered.length === 0 && (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: 32 }} />
      )}
    </PageContainer>
  )
}
