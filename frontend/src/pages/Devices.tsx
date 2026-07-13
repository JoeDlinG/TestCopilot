import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Select, Space, Tag,
  message, Popconfirm, Typography, Tooltip
} from 'antd'
import {
  PlusOutlined, LinkOutlined, DisconnectOutlined,
  DeleteOutlined, ReloadOutlined, ApiOutlined,
  SearchOutlined
} from '@ant-design/icons'
import { deviceAPI } from '../services/api'
import { extractData, extractItems, handleApiError } from '../services/apiHelper'
import { DEVICE_TYPES, INTERFACE_TYPES } from '../types'
import type { Device } from '../types'

const { Title } = Typography

export default function Devices() {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [commandModalVisible, setCommandModalVisible] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)
  const [command, setCommand] = useState('')
  const [commandResponse, setCommandResponse] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [discoveredDevices, setDiscoveredDevices] = useState<any[]>([])
  const [discoverModalVisible, setDiscoverModalVisible] = useState(false)
  const [form] = Form.useForm()

  const loadDevices = async () => {
    setLoading(true)
    try {
      const res = await deviceAPI.list()
      setDevices(extractItems(res))
    } catch (err) {
      handleApiError(err, '加载设备列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadDevices() }, [])

  const handleConnect = async (device: Device) => {
    try {
      // Pass device config for USB devices that need VID/PID
      const config = (device as any).config || undefined
      await deviceAPI.connect(device.id, config)
      message.success(`已连接 ${device.name}`)
      loadDevices()
    } catch (err) {
      handleApiError(err, '连接失败')
    }
  }

  const handleDisconnect = async (device: Device) => {
    try {
      await deviceAPI.disconnect(device.id)
      message.success(`已断开 ${device.name}`)
      loadDevices()
    } catch (err) {
      handleApiError(err, '断开连接失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deviceAPI.delete(id)
      message.success('设备已删除')
      loadDevices()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const handleAddDevice = async (values: any) => {
    try {
      // Map frontend form fields to backend API fields
      const payload = {
        name: values.name,
        type: values.device_type,
        protocol: values.interface_type,
        connection_type: values.interface_type,
        visa_address: values.visa_address || undefined,
        serial_port: values.serial_port || undefined,
        can_channel: values.can_channel || undefined,
        ip_address: values.ip_address || undefined,
        port: values.port ? parseInt(values.port) : undefined,
      }
      await deviceAPI.create(payload)
      message.success('设备添加成功')
      setModalVisible(false)
      form.resetFields()
      loadDevices()
    } catch (err) {
      handleApiError(err, '添加设备失败')
    }
  }

  const handleSendCommand = async () => {
    if (!selectedDevice || !command) return
    try {
      const res = await deviceAPI.sendCommand(selectedDevice.id, command)
      const data = res.data.data || res.data
      setCommandResponse(data.response || JSON.stringify(data))
    } catch (err) {
      handleApiError(err, '发送命令失败')
    }
  }

  const handleDiscover = async () => {
    setDiscovering(true)
    try {
      const res = await deviceAPI.discover()
      const found = extractData(res, [])
      setDiscoveredDevices(found)
      setDiscoverModalVisible(true)
      if (found.length === 0) {
        message.info('未发现已连接的硬件设备')
      } else {
        message.success(`发现 ${found.length} 个设备`)
      }
    } catch (err) {
      handleApiError(err, '设备发现失败')
    } finally {
      setDiscovering(false)
    }
  }

  const handleQuickAdd = async (device: any) => {
    try {
      const isUSB = device.protocol === 'usb' || device.connection_type === 'usb'
      const payload: any = {
        name: device.name || device.serial_port || device.visa_address || '新设备',
        type: device.type || 'generic',
        protocol: device.protocol || 'serial',
        connection_type: device.connection_type || (device.serial_port ? 'serial' : 'usb'),
        serial_port: device.serial_port || undefined,
        visa_address: device.visa_address || undefined,
      }
      // For USB devices without kernel driver, pass VID/PID in config
      if (isUSB && !device.serial_port) {
        payload.config = {
          vid: device.vid || '',
          pid: device.pid || '',
        }
      }
      await deviceAPI.create(payload)
      message.success(`已添加设备: ${payload.name}`)
      setDiscoverModalVisible(false)
      loadDevices()
    } catch (err) {
      handleApiError(err, '添加设备失败')
    }
  }

  const columns = [
    {
      title: '设备名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => <a><ApiOutlined /> {text}</a>,
    },
    {
      title: '设备类型',
      dataIndex: 'type',
      key: 'type',
      render: (type: string) => DEVICE_TYPES[type] || type,
    },
    {
      title: '接口类型',
      dataIndex: 'protocol',
      key: 'protocol',
      render: (type: string) => <Tag color="blue">{INTERFACE_TYPES[type] || type}</Tag>,
    },
    {
      title: '连接地址',
      key: 'address',
      render: (_: any, record: any) => (
        record.visa_address || record.serial_port || record.can_channel ||
        record.ip_address || '-'
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'connected' ? 'green' : 'default'}>
          {status === 'connected' ? '已连接' : '未连接'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: Device) => (
        <Space>
          {(record as any).status === 'connected' ? (
            <Tooltip title="断开连接">
              <Button
                size="small"
                danger
                icon={<DisconnectOutlined />}
                onClick={() => handleDisconnect(record)}
              />
            </Tooltip>
          ) : (
            <Tooltip title="连接设备">
              <Button
                size="small"
                type="primary"
                icon={<LinkOutlined />}
                onClick={() => handleConnect(record)}
              />
            </Tooltip>
          )}
          <Tooltip title="发送命令">
            <Button
              size="small"
              icon={<ApiOutlined />}
              disabled={(record as any).status !== 'connected'}
              onClick={() => {
                setSelectedDevice(record)
                setCommand('')
                setCommandResponse('')
                setCommandModalVisible(true)
              }}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此设备？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title="删除设备">
              <Button size="small" icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>设备管理</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadDevices}>刷新</Button>
          <Button
            icon={<SearchOutlined />}
            onClick={handleDiscover}
            loading={discovering}
          >
            扫描设备
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            添加设备
          </Button>
        </Space>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={devices}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Add Device Modal */}
      <Modal
        title="添加设备"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleAddDevice}>
          <Form.Item name="name" label="设备名称" rules={[{ required: true, message: '请输入设备名称' }]}>
            <Input placeholder="例如：Keysight 34465A 万用表" />
          </Form.Item>
          <Form.Item name="device_type" label="设备类型" rules={[{ required: true }]}>
            <Select placeholder="选择设备类型" options={
              Object.entries(DEVICE_TYPES).map(([k, v]) => ({ label: v, value: k }))
            } />
          </Form.Item>
          <Form.Item name="interface_type" label="接口类型" rules={[{ required: true }]}>
            <Select placeholder="选择接口类型" options={
              Object.entries(INTERFACE_TYPES).map(([k, v]) => ({ label: v, value: k }))
            } />
          </Form.Item>
          <Form.Item name="visa_address" label="VISA 地址">
            <Input placeholder="例如：USB0::0x2A8D::0x0101::MY59001001::0::INSTR" />
          </Form.Item>
          <Form.Item name="serial_port" label="串口号">
            <Input placeholder="例如：COM3 或 /dev/ttyUSB0" />
          </Form.Item>
          <Form.Item name="can_channel" label="CAN 通道">
            <Input placeholder="例如：PCAN_USBBUS1 或 can0" />
          </Form.Item>
          <Form.Item name="ip_address" label="IP 地址">
            <Input placeholder="例如：192.168.1.100" />
          </Form.Item>
          <Form.Item name="port" label="端口号">
            <Input type="number" placeholder="例如：5025" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Send Command Modal */}
      <Modal
        title={`发送命令 - ${selectedDevice?.name || ''}`}
        open={commandModalVisible}
        onCancel={() => setCommandModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setCommandModalVisible(false)}>关闭</Button>,
          <Button key="send" type="primary" onClick={handleSendCommand}>发送</Button>,
        ]}
      >
        <Form layout="vertical">
          <Form.Item label="命令">
            <Input.TextArea
              rows={3}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="输入 SCPI 命令，例如：*IDN?"
            />
          </Form.Item>
          {commandResponse && (
            <Form.Item label="响应">
              <Card size="small" style={{ background: '#f5f5f5' }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{commandResponse}</pre>
              </Card>
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* Discover Devices Modal */}
      <Modal
        title="发现的设备"
        open={discoverModalVisible}
        onCancel={() => setDiscoverModalVisible(false)}
        footer={null}
        width={700}
      >
        {discoveredDevices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
            未发现已连接的硬件设备。请确保设备已通过 USB/串口连接。
            <br />
            <small>如果设备已连接但未显示，可能需要安装或加载内核驱动（如 cdc_acm）。</small>
          </div>
        ) : (
          <Table
            dataSource={discoveredDevices}
            rowKey={(record, index) => record.serial_port || record.visa_address || `usb-${record.vid}-${record.pid}` || String(index)}
            pagination={false}
            columns={[
              { title: '设备名称', dataIndex: 'name', key: 'name', ellipsis: true },
              { title: 'VID', dataIndex: 'vid', key: 'vid', width: 80,
                render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: 'PID', dataIndex: 'pid', key: 'pid', width: 80,
                render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: '端口/地址', dataIndex: 'serial_port', key: 'serial_port',
                render: (v: string, r: any) => v || r.visa_address || '(raw USB)' },
              { title: '协议', dataIndex: 'protocol', key: 'protocol',
                render: (v: string) => <Tag color="blue">{v?.toUpperCase()}</Tag> },
              { title: '驱动状态', dataIndex: 'has_kernel_driver', key: 'driver',
                render: (v: boolean | undefined, r: any) => {
                  if (r.serial_port) return <Tag color="green">已加载</Tag>
                  if (v === false) return <Tag color="orange">需pyusb</Tag>
                  return <Tag>未知</Tag>
                }},
              {
                title: '操作', key: 'actions',
                render: (_: any, record: any) => (
                  <Button size="small" type="primary" onClick={() => handleQuickAdd(record)}>
                    快速添加
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Modal>
    </div>
  )
}
