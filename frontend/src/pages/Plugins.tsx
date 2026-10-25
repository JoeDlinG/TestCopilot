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
import { useI18n } from '../i18n'

const { Title, Text } = Typography
const { Dragger } = Upload

// The editor panels are heavy; keep them out of the initial bundle.
const PluginEditorPanel = lazy(() => import('./PluginEditor'))
const SkillEditorPanel = lazy(() => import('./SkillEditor'))

/** The plugin list / upload / enable-disable screen (was the whole page). */
function PluginManagement({ onOpenTab }: { onOpenTab?: (tab: string) => void }) {
  const { t } = useI18n()
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
      handleApiError(err, t('msg.loadPluginsFailed'))
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
      handleApiError(err, t('msg.scanPluginsFailed'))
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
        message.success(`${plugin.name} ${t('status.disabled')}`)
      } else {
        await pluginAPI.enable(plugin.id)
        message.success(`${plugin.name} ${t('status.enabled')}`)
      }
      loadPlugins()
    } catch (err) {
      handleApiError(err, t('msg.failed'))
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
      message.success(t('msg.pluginInstalled'))
      setModalVisible(false)
      form.resetFields()
      loadPlugins()
    } catch (err) {
      handleApiError(err, t('msg.installFailed'))
    }
  }

  const handleInstallDiscovered = async (item: any) => {
    try {
      await pluginAPI.installDiscovered(item)
      message.success(`${t('label.plugin')} ${item.name} ${t('msg.installed')}`)
      loadPlugins()
      loadDiscovered()
    } catch (err) {
      handleApiError(err, t('msg.installFailed'))
    }
  }

  const handleAddDevice = async (plugin: Plugin) => {
    try {
      await pluginAPI.addDevice(plugin.id)
      message.success(`${t('label.fromPlugin')} "${plugin.name}" ${t('btn.createDevice')}`)
    } catch (err) {
      handleApiError(err, t('msg.createDeviceFailed'))
    }
  }

  const columns = (t: (k: string) => string) => [
    {
      title: t('col.pluginName'),
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
      title: t('col.version'),
      dataIndex: 'version',
      key: 'version',
      width: 90,
      render: (v: string) => <Tag color="blue">v{v}</Tag>,
    },
    {
      title: t('col.protocol'),
      dataIndex: 'protocol_type',
      key: 'protocol_type',
      width: 130,
      render: (p: string) => <Tag>{p}</Tag>,
    },
    {
      title: t('col.description'),
      dataIndex: 'description',
      key: 'description',
      width: 240,
      ellipsis: true,
    },
    {
      title: t('col.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'enabled' ? 'green' : 'default'}>
          {status === 'enabled' ? t('status.enabled') : t('status.disabled')}
        </Tag>
      ),
    },
    {
      title: t('col.actions'),
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
            {(record as any).status === 'enabled' ? t('common.disable') : t('common.enable')}
          </Button>
          <Button
            size="small"
            icon={<ApiOutlined />}
            disabled={(record as any).status !== 'enabled'}
            onClick={() => handleAddDevice(record)}
            title={t('btn.createFromPlugin')}
          >{t('device.add')}</Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>{t('tab.manage')}</Title>
          <Text type="secondary">{t('plugin.extendDesc')}</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadPlugins}>{t('common.refresh')}</Button>
          <Button
            icon={<CodeOutlined />}
            onClick={() => (onOpenTab ? onOpenTab('editor') : navigate('/plugin-editor'))}
          >{t('tab.pluginEditor')}</Button>
          <Button
            icon={<FileMarkdownOutlined />}
            onClick={() => (onOpenTab ? onOpenTab('skill') : navigate('/skill-editor'))}
          >{t('tab.skillEditor')}</Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >{t('dlg.installPlugin')}</Button>
        </Space>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Text strong>{t('link.howToPlugin')}</Text>
        <div style={{ marginTop: 8, color: 'var(--app-fg-subtle)' }}>
          <p>
            1. {t('plugin.inheritHint')} <code>BaseProtocolPlugin</code>
          </p>
          <p>2. {t('label.implement')} <code>connect</code>、<code>disconnect</code>、<code>send</code>、<code>receive</code>{t('label.method')}</p>
          <p>
            3. {t('plugin.dropHint')} <code>plugins/</code>{t('plugin.installHint')}</p>
          <p>{t('label.reference')}<code>plugins/example_plugin.py</code> (Modbus RTU {t('col.protocol')})</p>
          <p>{t('label.betterOpen')}<a onClick={() => (onOpenTab ? onOpenTab('editor') : navigate('/plugin-editor'))}>{t('tab.pluginEditor')}</a>」
            {t('plugin.templateHint')}
            Skill（AI {t('btn.generateCases')}{t('label.guideInPanel')}<a onClick={() => (onOpenTab ? onOpenTab('skill') : navigate('/skill-editor'))}>{t('tab.skillEditor')}</a>」{t('label.importEditSuffix')}
          </p>
        </div>
      </Card>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text strong>{t('card.discoveredPlugins')}</Text>
          <Button size="small" icon={<ReloadOutlined />} loading={discovering} onClick={loadDiscovered}>{t('btn.scan')}</Button>
        </div>
        {discovered.length === 0 ? (
          <Empty description={t('plugin.noneFound')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <DataTable
            dataSource={discovered}
            rowKey={(r: any) => r.module_name}
            pagination={false}
            size="small"
            columns={[
              { title: t('col.name'), dataIndex: 'name', key: 'name' },
              { title: t('col.version'), dataIndex: 'version', key: 'version',
                render: (v: string) => <Tag color="blue">v{v}</Tag> },
              { title: t('col.protocol'), dataIndex: 'protocol_name', key: 'protocol_name',
                render: (p: string) => <Tag>{p}</Tag> },
              { title: t('col.description'), dataIndex: 'description', key: 'description', ellipsis: true },
              {
                title: t('col.actions'), key: 'actions',
                render: (_: any, record: any) => (
                  <Button
                    size="small"
                    type="primary"
                    icon={<AppstoreAddOutlined />}
                    onClick={() => handleInstallDiscovered(record)}
                  >{t('btn.install')}</Button>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card>
        <DataTable
          columns={columns(t)}
          dataSource={plugins}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: <Empty description={t('msg.noPluginsInstalled')} /> }}
        />
      </Card>

      <Modal
        title={t('dlg.installPlugin')}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleInstall}>
          <Form.Item name="name" label={t('col.pluginName')} rules={[{ required: true }]}>
            <Input placeholder={t('label.exampleModbus')} />
          </Form.Item>
          <Form.Item name="version" label={t('col.version')} initialValue="1.0.0">
            <Input placeholder="1.0.0" />
          </Form.Item>
          <Form.Item name="protocol_name" label={t('label.protocolName')} rules={[{ required: true }]}>
            <Input placeholder={t('ph.protocolExample2')} />
          </Form.Item>
          <Form.Item name="module_path" label={t('label.modulePath')} rules={[{ required: true }]}>
            <Input placeholder={t('ph.pluginFileExample')} />
          </Form.Item>
          <Form.Item name="description" label={t('col.description')}>
            <Input.TextArea rows={2} placeholder={t('label.pluginDesc')} />
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
  const { t } = useI18n()
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
            label: <span><AppstoreAddOutlined />{t('tab.manage')}</span>,
            children: <PluginManagement onOpenTab={setActive} />,
          },
          {
            key: 'editor',
            label: <span><CodeOutlined />{t('tab.pluginEditor')}</span>,
            children: (
              <Suspense fallback={<Spin style={{ display: 'block', margin: '40px auto' }} />}>
                <PluginEditorPanel />
              </Suspense>
            ),
          },
          {
            key: 'skill',
            label: <span><FileMarkdownOutlined />{t('tab.skillEditor')}</span>,
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
