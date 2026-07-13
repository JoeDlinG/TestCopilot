import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Modal,
  Form, Input, Switch, Empty, Upload
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, PoweroffOutlined,
  PlayCircleOutlined, AppstoreAddOutlined, InboxOutlined
} from '@ant-design/icons'
import { pluginAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import type { Plugin } from '../types'

const { Title, Text } = Typography
const { Dragger } = Upload

export default function Plugins() {
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  const loadPlugins = async () => {
    setLoading(true)
    try {
      const res = await pluginAPI.list()
      setPlugins(extractData(res, []))
    } catch (err) {
      handleApiError(err, '加载插件列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPlugins() }, [])

  const handleToggle = async (plugin: Plugin) => {
    try {
      const isEnabled = (plugin as any).status === 'enabled'
      if (isEnabled) {
        await pluginAPI.disable(plugin.id)
        message.success(`${plugin.name} 已禁用`)
      } else {
        await pluginAPI.enable(plugin.id)
        message.success(`${plugin.name} 已启用`)
      }
      loadPlugins()
    } catch (err) {
      handleApiError(err, '操作失败')
    }
  }

  const handleInstall = async (values: any) => {
    try {
      // Map frontend form fields to backend API fields
      const payload = {
        name: values.name,
        version: values.version || '1.0.0',
        description: values.description,
        protocol_type: values.protocol_name,
        file_path: values.module_path,
        module_name: values.module_path?.replace('.py', '') || values.name,
        class_name: values.name?.replace(/\s+/g, '') + 'Plugin' || 'CustomPlugin',
      }
      await pluginAPI.install(payload)
      message.success('插件安装成功')
      setModalVisible(false)
      form.resetFields()
      loadPlugins()
    } catch (err) {
      handleApiError(err, '安装失败')
    }
  }

  const columns = [
    {
      title: '插件名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string) => (
        <Space>
          <AppstoreAddOutlined />
          {name}
        </Space>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version',
      key: 'version',
      render: (v: string) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: '协议',
      dataIndex: 'protocol_type',
      key: 'protocol_type',
      render: (p: string) => <Tag>{p}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'enabled' ? 'green' : 'default'}>
          {status === 'enabled' ? '已启用' : '已禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: Plugin) => (
        <Button
          size="small"
          type={(record as any).status === 'enabled' ? 'default' : 'primary'}
          icon={<PoweroffOutlined />}
          onClick={() => handleToggle(record)}
        >
          {(record as any).status === 'enabled' ? '禁用' : '启用'}
        </Button>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>插件管理</Title>
          <Text type="secondary">通过插件扩展自定义通信协议支持</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadPlugins}>刷新</Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            安装插件
          </Button>
        </Space>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Text strong>如何创建自定义协议插件？</Text>
        <div style={{ marginTop: 8, color: '#666' }}>
          <p>
            1. 创建一个 Python 文件，继承 <code>BaseProtocolPlugin</code>
          </p>
          <p>2. 实现 <code>connect</code>、<code>disconnect</code>、<code>send</code>、<code>receive</code> 方法</p>
          <p>3. 将插件文件放入 <code>plugins/</code> 目录，通过下方表单安装</p>
          <p>参考示例：<code>plugins/example_plugin.py</code> (Modbus RTU 协议)</p>
        </div>
      </Card>

      <Card>
        <Table
          columns={columns}
          dataSource={plugins}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: <Empty description="暂无安装的插件" /> }}
        />
      </Card>

      <Modal
        title="安装插件"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleInstall}>
          <Form.Item name="name" label="插件名称" rules={[{ required: true }]}>
            <Input placeholder="例如：Modbus RTU" />
          </Form.Item>
          <Form.Item name="version" label="版本" initialValue="1.0.0">
            <Input placeholder="1.0.0" />
          </Form.Item>
          <Form.Item name="protocol_name" label="协议名称" rules={[{ required: true }]}>
            <Input placeholder="例如：modbus_rtu" />
          </Form.Item>
          <Form.Item name="module_path" label="模块路径" rules={[{ required: true }]}>
            <Input placeholder="例如：example_plugin.py" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="插件功能描述" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
