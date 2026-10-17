import { Suspense, lazy, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Tag, message, Typography, Modal,
  Form, Input, Switch, Empty, Upload, Tabs, Spin
} from 'antd'
import { DataTable } from '../components/ui'
import {
  PlusOutlined, ReloadOutlined, PoweroffOutlined,
  PlayCircleOutlined, AppstoreAddOutlined, InboxOutlined, ApiOutlined,
  CodeOutlined, FileMarkdownOutlined,
} from '@ant-design/icons'
import { pluginAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import type { Plugin } from '../types'

const { Title, Text } = Typography
const { Dragger } = Upload

// The editor panels are heavy; keep them out of the initial bundle.
const PluginEditorPanel = lazy(() => import('./PluginEditor'))
const SkillEditorPanel = lazy(() => import('./SkillEditor'))

/** The plugin list / upload / enable-disable screen (was the whole page). */
function PluginManagement({ onOpenTab }: { onOpenTab?: (tab: string) => void }) {
  const navigate = useNavigate()
  const [plugins, setPlugins] = useState<Plugin[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()
  const [discovered, setDiscovered] = useState<any[]>([])
  const [discovering, setDiscovering] = useState(false)

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

  const loadDiscovered = async () => {
    setDiscovering(true)
    try {
      const res = await pluginAPI.discovered()
      setDiscovered(extractData(res, []))
    } catch (err) {
      handleApiError(err, '扫描插件失败')
    } finally {
      setDiscovering(false)
    }
  }

  useEffect(() => { loadPlugins(); loadDiscovered() }, [])

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

  const handleInstallDiscovered = async (item: any) => {
    try {
      await pluginAPI.installDiscovered(item)
      message.success(`插件 ${item.name} 安装成功`)
      loadPlugins()
      loadDiscovered()
    } catch (err) {
      handleApiError(err, '安装失败')
    }
  }

  const handleAddDevice = async (plugin: Plugin) => {
    try {
      await pluginAPI.addDevice(plugin.id)
      message.success(`已从插件 "${plugin.name}" 创建设备`)
    } catch (err) {
      handleApiError(err, '创建设备失败')
    }
  }

  const columns = [
    {
      title: '插件名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
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
      width: 90,
      render: (v: string) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: '协议',
      dataIndex: 'protocol_type',
      key: 'protocol_type',
      width: 130,
      render: (p: string) => <Tag>{p}</Tag>,
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 240,
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'enabled' ? 'green' : 'default'}>
          {status === 'enabled' ? '已启用' : '已禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: Plugin) => (
        <Space>
          <Button
            size="small"
            type={(record as any).status === 'enabled' ? 'default' : 'primary'}
            icon={<PoweroffOutlined />}
            onClick={() => handleToggle(record)}
          >
            {(record as any).status === 'enabled' ? '禁用' : '启用'}
          </Button>
          <Button
            size="small"
            icon={<ApiOutlined />}
            disabled={(record as any).status !== 'enabled'}
            onClick={() => handleAddDevice(record)}
            title="根据插件创建设备"
          >
            添加设备
          </Button>
        </Space>
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
            icon={<CodeOutlined />}
            onClick={() => (onOpenTab ? onOpenTab('editor') : navigate('/plugin-editor'))}
          >
            插件编辑器
          </Button>
          <Button
            icon={<FileMarkdownOutlined />}
            onClick={() => (onOpenTab ? onOpenTab('skill') : navigate('/skill-editor'))}
          >
            Skill 编辑器
          </Button>
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
        <div style={{ marginTop: 8, color: 'var(--app-fg-subtle)' }}>
          <p>
            1. 创建一个 Python 文件，继承 <code>BaseProtocolPlugin</code>
          </p>
          <p>2. 实现 <code>connect</code>、<code>disconnect</code>、<code>send</code>、<code>receive</code> 方法</p>
          <p>
            3. 将插件文件放入 <code>plugins/</code> 目录，通过下方表单安装
          </p>
          <p>参考示例：<code>plugins/example_plugin.py</code> (Modbus RTU 协议)</p>
          <p>
            更推荐：打开「<a onClick={() => (onOpenTab ? onOpenTab('editor') : navigate('/plugin-editor'))}>插件编辑器</a>」
            选择模板（协议 / 设备驱动 / 数据解析 / 报告模板）一键生成带示例的插件骨架；
            Skill（AI 用例生成指南）可在「<a onClick={() => (onOpenTab ? onOpenTab('skill') : navigate('/skill-editor'))}>Skill 编辑器</a>」中导入与修改。
          </p>
        </div>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text strong>已发现的插件</Text>
          <Button size="small" icon={<ReloadOutlined />} loading={discovering} onClick={loadDiscovered}>
            扫描
          </Button>
        </div>
        {discovered.length === 0 ? (
          <Empty description="未在 plugins/ 目录发现可安装插件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <DataTable
            dataSource={discovered}
            rowKey={(r: any) => r.module_name}
            pagination={false}
            size="small"
            columns={[
              { title: '名称', dataIndex: 'name', key: 'name' },
              { title: '版本', dataIndex: 'version', key: 'version',
                render: (v: string) => <Tag color="blue">v{v}</Tag> },
              { title: '协议', dataIndex: 'protocol_name', key: 'protocol_name',
                render: (p: string) => <Tag>{p}</Tag> },
              { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
              {
                title: '操作', key: 'actions',
                render: (_: any, record: any) => (
                  <Button
                    size="small"
                    type="primary"
                    icon={<AppstoreAddOutlined />}
                    onClick={() => handleInstallDiscovered(record)}
                  >
                    安装
                  </Button>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card>
        <DataTable
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

/**
 * 插件中心 (issue #21): one route, three tabs.
 *
 * Plugin management, the plugin editor and the skill editor used to be three
 * peer menu entries, which scattered a single concept across the navigation.
 * They now share `/plugins`. The old routes are kept working (App.tsx maps them
 * here with an explicit tab) so existing links and bookmarks still land
 * somewhere sensible.
 */
export default function Plugins({ tab }: { tab?: string }) {
  const [active, setActive] = useState(
    tab === 'editor' ? 'editor' : tab === 'skill' ? 'skill' : 'manage',
  )

  useEffect(() => {
    if (tab === 'editor' || tab === 'skill') setActive(tab)
  }, [tab])

  return (
    <div className="page-container">
      <Tabs
        activeKey={active}
        onChange={setActive}
        items={[
          {
            key: 'manage',
            label: <span><AppstoreAddOutlined /> 插件管理</span>,
            children: <PluginManagement onOpenTab={setActive} />,
          },
          {
            key: 'editor',
            label: <span><CodeOutlined /> 插件编辑器</span>,
            children: (
              <Suspense fallback={<Spin style={{ display: 'block', margin: '40px auto' }} />}>
                <PluginEditorPanel />
              </Suspense>
            ),
          },
          {
            key: 'skill',
            label: <span><FileMarkdownOutlined /> Skill 编辑器</span>,
            children: (
              <Suspense fallback={<Spin style={{ display: 'block', margin: '40px auto' }} />}>
                <SkillEditorPanel />
              </Suspense>
            ),
          },
        ]}
      />
    </div>
  )
}
