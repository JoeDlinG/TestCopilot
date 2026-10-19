import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Select, Space, Tag,
  message, Popconfirm, Typography, Tooltip, Alert
} from 'antd'
import {
  PlusOutlined, LinkOutlined, DisconnectOutlined,
  DeleteOutlined, ReloadOutlined, ApiOutlined,
  SearchOutlined, EditOutlined
} from '@ant-design/icons'
import { deviceAPI } from '../services/api'
import { extractData, extractItems, handleApiError } from '../services/apiHelper'
import InterfaceConfigModal from '../components/devices/InterfaceConfigModal'
import { DEVICE_TYPES, INTERFACE_TYPES } from '../types'
import { useI18n } from '../i18n'
import { DataTable, StatusTag } from '../components/ui'
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
  const [ifaceModalVisible, setIfaceModalVisible] = useState(false)
  const [ifaceDevice, setIfaceDevice] = useState<Device | null>(null)
  const [keyOpen, setKeyOpen] = useState(false)
  const [keyDevice, setKeyDevice] = useState<any>(null)
  const [keySaving, setKeySaving] = useState(false)
  const [keyForm] = Form.useForm()
  const [form] = Form.useForm()
  const { t } = useI18n()

  const loadDevices = async () => {
    setLoading(true)
    try {
      const res = await deviceAPI.list()
      setDevices(extractItems(res))
    } catch (err) {
      handleApiError(err, t('msg.loadDevicesFailed'))
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
      message.success(`${t('status.connected')} ${device.name}`)
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.connectFailed'))
    }
  }

  const handleDisconnect = async (device: Device) => {
    try {
      await deviceAPI.disconnect(device.id)
      message.success(`${t('status.disconnected')} ${device.name}`)
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.disconnectFailed'))
    }
  }

  // ---- 设备ID号（用例通过它关联设备，更换硬件时可复用同一个号）----
  const handleSaveDeviceKey = async () => {
    let values: any
    try {
      values = await keyForm.validateFields()
    } catch {
      return
    }
    if (!keyDevice) return
    setKeySaving(true)
    try {
      await deviceAPI.update(keyDevice.id, { device_key: (values.device_key || '').trim() })
      message.success(t('msg.deviceIdUpdated'))
      setKeyOpen(false)
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.editDeviceIdFailed'))
    } finally {
      setKeySaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deviceAPI.delete(id)
      message.success(t('msg.deviceDeleted'))
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
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
      message.success(t('msg.deviceAdded'))
      setModalVisible(false)
      form.resetFields()
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.addDeviceFailed'))
    }
  }

  const handleSendCommand = async () => {
    if (!selectedDevice || !command) return
    try {
      const res = await deviceAPI.sendCommand(selectedDevice.id, command)
      const data = res.data.data || res.data
      setCommandResponse(data.response || JSON.stringify(data))
    } catch (err) {
      handleApiError(err, t('msg.sendFailed'))
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
        message.info(t('msg.noHardware'))
      } else {
        message.success(`${t('btn.discover')} ${found.length} ${t('unit.devices')}`)
      }
    } catch (err) {
      handleApiError(err, t('msg.discoveryFailed'))
    } finally {
      setDiscovering(false)
    }
  }

  const handleQuickAdd = async (device: any) => {
    try {
      const isUSB = device.protocol === 'usb' || device.connection_type === 'usb'
      const payload: any = {
        name: device.name || device.serial_port || device.visa_address || t('label.newDevice'),
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
      message.success(`${t('label.devicesAdded')} ${payload.name}`)
      setDiscoverModalVisible(false)
      loadDevices()
    } catch (err) {
      handleApiError(err, t('msg.addDeviceFailed'))
    }
  }

  const columns = [
    {
      // Stable identifier test cases bind to — it survives a hardware swap.
      title: t('col.deviceId'),
      dataIndex: 'device_key',
      key: 'device_key',
      width: 110,
      render: (key: string, record: any) => (
        <Tooltip title={t('device.editIdFull')}>
          <Tag
            color="geekblue"
            style={{ cursor: 'pointer' }}
            onClick={() => {
              setKeyDevice(record)
              keyForm.setFieldsValue({ device_key: key || '' })
              setKeyOpen(true)
            }}
          >
            {key || t('label.unassigned')}
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: t('col.deviceName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      ellipsis: true,
      render: (text: string) => <a><ApiOutlined /> {text}</a>,
    },
    {
      title: t('device.deviceType'),
      dataIndex: 'type',
      key: 'type',
      width: 140,
      render: (type: string) => DEVICE_TYPES[type] || type,
    },
    {
      title: t('device.interfaceType'),
      dataIndex: 'protocol',
      key: 'protocol',
      width: 130,
      render: (type: string) => <Tag color="blue">{INTERFACE_TYPES[type] || type}</Tag>,
    },
    {
      title: t('common.address'),
      key: 'address',
      width: 220,
      ellipsis: true,
      render: (_: any, record: any) => (
        record.visa_address || record.serial_port || record.can_channel ||
        record.ip_address || '-'
      ),
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        // Icon + text + colour — never colour alone (issue #20).
        <StatusTag
          kind={status === 'connected' ? 'pass' : 'idle'}
          text={status === 'connected' ? t('common.connected') : t('common.disconnected')}
          size="small"
        />
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 230,
      render: (_: any, record: Device) => (
        <Space>
          {(record as any).status === 'connected' ? (
            <Tooltip title={t('btn.disconnectDevice')}>
              <Button
                size="small"
                danger
                icon={<DisconnectOutlined />}
                onClick={() => handleDisconnect(record)}
              />
            </Tooltip>
          ) : (
            <Tooltip title={t('btn.connectDevice')}>
              <Button
                size="small"
                type="primary"
                icon={<LinkOutlined />}
                onClick={() => handleConnect(record)}
              />
            </Tooltip>
          )}
          <Tooltip title={t('btn.sendCommand')}>
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
          <Tooltip title={t('device.configureInterface')}>
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => {
                setIfaceDevice(record)
                setIfaceModalVisible(true)
              }}
            />
          </Tooltip>
          <Popconfirm
            title={t('device.confirmDelete')}
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title={t('btn.deleteDevice')}>
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
        <Title level={3} style={{ margin: 0 }}>{t('device.title')}</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadDevices}>
            {t('common.refresh')}
          </Button>
          <Button
            icon={<SearchOutlined />}
            onClick={handleDiscover}
            loading={discovering}
          >
            {t('common.search')}
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            {t('device.add')}
          </Button>
        </Space>
      </div>

      <Card>
        <DataTable
          columns={columns}
          dataSource={devices}
          rowKey="id"
          loading={loading}
          scrollX={1100}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* Add Device Modal */}
      <Modal
        title={t('device.add')}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleAddDevice}>
          <Form.Item name="name" label={t('col.deviceName')} rules={[{ required: true, message: t('msg.enterDeviceName') }]}>
            <Input placeholder={t('ph.deviceExample')} />
          </Form.Item>
          <Form.Item name="device_type" label={t('label.deviceType')} rules={[{ required: true }]}>
            <Select placeholder={t('ph.deviceType')} options={
              Object.entries(DEVICE_TYPES).map(([k, v]) => ({ label: v, value: k }))
            } />
          </Form.Item>
          <Form.Item name="interface_type" label={t('iface.type')} rules={[{ required: true }]}>
            <Select placeholder={t('msg.selectInterface')} options={
              Object.entries(INTERFACE_TYPES).map(([k, v]) => ({ label: v, value: k }))
            } />
          </Form.Item>
          <Form.Item name="visa_address" label={t('ph.visaAddress')}>
            <Input placeholder={t('ph.visaExample')} />
          </Form.Item>
          <Form.Item name="serial_port" label={t('iface.f.serial_port')}>
            <Input placeholder={t('ph.serialExample')} />
          </Form.Item>
          <Form.Item name="can_channel" label={t('ph.canChannel')}>
            <Input placeholder={t('ph.canExample2')} />
          </Form.Item>
          <Form.Item name="ip_address" label={t('ph.ipAddress')}>
            <Input placeholder={t('ph.ipExample2')} />
          </Form.Item>
          <Form.Item name="port" label={t('iface.f.port')}>
            <Input type="number" placeholder={t('ph.portExample')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* Send Command Modal */}
      <Modal
        title={`${t('label.sendCommandDash')} ${selectedDevice?.name || ''}`}
        open={commandModalVisible}
        onCancel={() => setCommandModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setCommandModalVisible(false)}>{t('common.close')}</Button>,
          <Button key="send" type="primary" onClick={handleSendCommand}>{t('btn.send')}</Button>,
        ]}
      >
        <Form layout="vertical">
          <Form.Item label={t('col.command')}>
            <Input.TextArea
              rows={3}
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder={t('ph.scpiExample')}
            />
          </Form.Item>
          {commandResponse && (
            <Form.Item label={t('label.response')}>
              <Card size="small" style={{ background: 'var(--app-surface-sunken)' }}>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{commandResponse}</pre>
              </Card>
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* Discover Devices Modal */}
      <Modal
        title={t('card.discovered')}
        open={discoverModalVisible}
        onCancel={() => setDiscoverModalVisible(false)}
        footer={null}
        width={700}
      >
        {discoveredDevices.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 24, color: 'var(--app-fg-subtle)' }}>{t('device.noneFound')}<br />
            <small>t('device.driverHint')_acm）。</small>
          </div>
        ) : (
          <Table
            dataSource={discoveredDevices}
            rowKey={(record, index) => record.serial_port || record.visa_address || `usb-${record.vid}-${record.pid}` || String(index)}
            pagination={false}
            columns={[
              { title: t('col.deviceName'), dataIndex: 'name', key: 'name', ellipsis: true },
              { title: 'VID', dataIndex: 'vid', key: 'vid', width: 80,
                render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: 'PID', dataIndex: 'pid', key: 'pid', width: 80,
                render: (v: string) => v ? <Tag>{v}</Tag> : '-' },
              { title: t('col.portAddress'), dataIndex: 'serial_port', key: 'serial_port',
                render: (v: string, r: any) => v || r.visa_address || '(raw USB)' },
              { title: t('col.protocol'), dataIndex: 'protocol', key: 'protocol',
                render: (v: string) => <Tag color="blue">{v?.toUpperCase()}</Tag> },
              { title: t('col.driverStatus'), dataIndex: 'has_kernel_driver', key: 'driver',
                render: (v: boolean | undefined, r: any) => {
                  if (r.serial_port) return <Tag color="green">{t('label.loaded')}</Tag>
                  if (v === false) return <Tag color="orange">{t('label.needsPyusb')}</Tag>
                  return <Tag>{t('label.unknown')}</Tag>
                }},
              {
                title: t('col.actions'), key: 'actions',
                render: (_: any, record: any) => (
                  <Button size="small" type="primary" onClick={() => handleQuickAdd(record)}>{t('device.quickAdd')}</Button>
                ),
              },
            ]}
          />
        )}
      </Modal>

          {/* device ID */}
      <Modal
        title={t('btn.editDeviceId')}
        open={keyOpen}
        onOk={handleSaveDeviceKey}
        confirmLoading={keySaving}
        onCancel={() => setKeyOpen(false)}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('label.deviceIdUnique')}
          description={t('device.idExplain')}
        />
        <Form form={keyForm} layout="vertical">
          <Form.Item
            name="device_key"
            label={t('col.deviceId')}
            rules={[{ required: true, message: t('msg.enterDeviceId') }]}
            extra={keyDevice ? `${t('label.deviceColon')}${keyDevice.name}` : ''}
          >
            <Input placeholder={t('ph.deviceIdExample')} autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      {/* Interface (connection) configuration */}
      <InterfaceConfigModal
        open={ifaceModalVisible}
        device={ifaceDevice}
        onClose={() => setIfaceModalVisible(false)}
        onSaved={loadDevices}
      />
    </div>
  )
}
