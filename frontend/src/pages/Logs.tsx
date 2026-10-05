import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Select,
  DatePicker, Input, Row, Col, Empty
} from 'antd'
import {
  ReloadOutlined, DownloadOutlined, SearchOutlined,
  ArrowUpOutlined, ArrowDownOutlined
} from '@ant-design/icons'
import { logAPI, deviceAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import type { CommunicationLog, Device } from '../types'
import { INTERFACE_TYPES } from '../types'

const { Title } = Typography
const { RangePicker } = DatePicker

export default function Logs() {
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
      handleApiError(err, '加载日志失败')
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
  useEffect(() => {
    const timer = setInterval(() => loadLogs(true), 5000)
    return () => clearInterval(timer)
  }, [filters])

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
      message.success('日志已导出')
    } catch (err) {
      handleApiError(err, '导出失败')
    }
  }

  const columns = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '设备',
      dataIndex: 'device_id',
      key: 'device_id',
      width: 120,
      render: (id: string) => {
        const device = devices.find(d => d.id === id)
        return device?.name || (id ? id.slice(0, 8) + '...' : '-')
      },
    },
    {
      title: '接口',
      dataIndex: 'protocol',
      key: 'protocol',
      width: 100,
      render: (type: string) => <Tag>{INTERFACE_TYPES[type] || type}</Tag>,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      width: 80,
      render: (dir: string) => (
        <Tag color={dir === 'sent' ? 'blue' : 'green'} icon={dir === 'sent' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}>
          {dir === 'sent' ? '发送' : '接收'}
        </Tag>
      ),
    },
    {
      title: '数据内容',
      dataIndex: 'raw_data',
      key: 'raw_data',
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
      width: 150,
      render: (hex: string) => (
        <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{hex || '-'}</code>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>通信日志</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadLogs()}>刷新</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportCSV}>导出 CSV</Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={[16, 8]}>
          <Col xs={24} sm={8}>
            <Select
              allowClear
              placeholder="选择设备"
              style={{ width: '100%' }}
              value={filters.device_id}
              onChange={(val: any) => setFilters({ ...filters, device_id: val })}
              options={devices.map(d => ({ label: d.name, value: d.id }))}
            />
          </Col>
          <Col xs={24} sm={8}>
            <Select
              allowClear
              placeholder="选择接口类型"
              style={{ width: '100%' }}
              value={filters.interface_type}
              onChange={(val: any) => setFilters({ ...filters, interface_type: val })}
              options={Object.entries(INTERFACE_TYPES).map(([k, v]) => ({ label: v, value: k }))}
            />
          </Col>
        </Row>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={logs}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
          locale={{ emptyText: <Empty description="暂无通信日志" /> }}
          size="small"
          scroll={{ x: 1000 }}
        />
      </Card>
    </div>
  )
}
