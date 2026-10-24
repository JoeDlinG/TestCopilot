import { useEffect, useState } from 'react'
import { usePolling } from '../hooks/usePolling'
import {
  Card, Table, Button, Space, Tag, message, Typography, Select,
  DatePicker, Input, Row, Col, Empty
} from 'antd'
import { DataTable } from '../components/ui'
import {
  ReloadOutlined, DownloadOutlined, SearchOutlined,
  ArrowUpOutlined, ArrowDownOutlined
} from '@ant-design/icons'
import { logAPI, deviceAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import type { CommunicationLog, Device } from '../types'
import { INTERFACE_TYPES } from '../types'
import { useI18n } from '../i18n'

const { Title } = Typography
const { RangePicker } = DatePicker

export default function Logs() {
  const { t } = useI18n()
  const [logs, setLogs] = useState<CommunicationLog[]>([])
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({
    device_id: undefined as string | undefined,
    interface_type: undefined as string | undefined,
  })

  const loadLogs = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const params: any = { limit: 200 }
      if (filters.device_id) params.device_id = filters.device_id
      if (filters.interface_type) params.interface_type = filters.interface_type
      const res = await logAPI.list(params)
      setLogs(extractItems(res))
    } catch (err) {
      handleApiError(err, t('msg.loadLogsFailed'))
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const loadDevices = async () => {
    try {
      const res = await deviceAPI.list()
      setDevices(extractItems(res))
    } catch (err) { /* ignore */ }
  }

  useEffect(() => {
    loadDevices()
    loadLogs()
  }, [])

  useEffect(() => { loadLogs() }, [filters])

  // Auto-refresh every 5s so the terminal shows live traffic during tests
  // (pauses while the tab is hidden, and never stacks requests).
  usePolling(() => loadLogs(true), 5000)

  const handleExportCSV = async () => {
    try {
      const params: any = {}
      if (filters.device_id) params.device_id = filters.device_id
      if (filters.interface_type) params.interface_type = filters.interface_type
      const res = await logAPI.exportCSV(params)
      const blob = new Blob([res.data], { type: 'text/csv' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `communication_logs_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      message.success(t('msg.logsExported'))
    } catch (err) {
      handleApiError(err, t('msg.exportFailed'))
    }
  }

  const columns = [
    {
      title: t('col.time'),
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('col.device'),
      dataIndex: 'device_id',
      key: 'device_id',
      width: 120,
      render: (id: string) => {
        const device = devices.find(d => d.id === id)
        return device?.name || (id ? id.slice(0, 8) + '...' : '-')
      },
    },
    {
      title: t('col.interface'),
      dataIndex: 'protocol',
      key: 'protocol',
      width: 100,
      render: (type: string) => <Tag>{INTERFACE_TYPES[type] || type}</Tag>,
    },
    {
      title: t('col.direction'),
      dataIndex: 'direction',
      key: 'direction',
      width: 80,
      render: (dir: string) => (
        <Tag color={dir === 'sent' ? 'blue' : 'green'} icon={dir === 'sent' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
          {dir === 'sent' ? t('btn.send') : t('term.recv')}
        </Tag>
      ),
    },
    {
      title: t('col.dataContent'),
      dataIndex: 'raw_data',
      key: 'raw_data',
      width: 320,
      render: (data: string) => (
        <div style={{ maxWidth: 500, overflow: 'hidden', textOverflow: 'ellipsis' }}>
          <code style={{ fontSize: 12 }}>{data || '-'}</code>
        </div>
      ),
    },
    {
      title: 'Hex',
      dataIndex: 'raw_data_hex',
      key: 'raw_data_hex',
      width: 180,
      render: (hex: string) => (
        <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{hex || '-'}</code>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>{t('label.commLog')}</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadLogs()}>{t('common.refresh')}</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportCSV}>{t('btn.exportCsv')}</Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 8]}>
          <Col xs={24} sm={8}>
            <Select
              allowClear
              placeholder={t('btn.selectDevice')}
              style={{ width: '100%' }}
              value={filters.device_id}
              onChange={(val: any) => setFilters({ ...filters, device_id: val })}
              options={devices.map(d => ({ label: d.name, value: d.id }))}
            />
          </Col>
          <Col xs={24} sm={8}>
            <Select
              allowClear
              placeholder={t('msg.selectInterface')}
              style={{ width: '100%' }}
              value={filters.interface_type}
              onChange={(val: any) => setFilters({ ...filters, interface_type: val })}
              options={Object.entries(INTERFACE_TYPES).map(([k, v]) => ({ label: v, value: k }))}
            />
          </Col>
        </Row>
      </Card>

      <Card>
        <DataTable
          columns={columns}
          dataSource={logs}
          rowKey="id"
          loading={loading}
          // 性能优化：通信日志可以积到几十万行。开启虚拟滚动后，即使把每页
          // 调到 200 条也只渲染可视区域内的行，滚动不再掉帧。
          virtual
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: [20, 50, 100, 200],
            showTotal: (total) => `${t('label.total')} ${total} ${t('unit.items')}`,
          }}
          locale={{ emptyText: <Empty description={t('msg.noComLogs')} /> }}
          size="small"
          scroll={{ x: 1000, y: 'calc(100vh - 430px)' }}
        />
      </Card>
    </div>
  )
}
