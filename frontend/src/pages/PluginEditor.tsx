/**
 * 插件编辑器 — 基于模板新建插件、在线编辑插件源码并校验。
 *
 * 新建插件时自动套用所选模板（协议 / 设备驱动 / 数据解析 / 报告模板），
 * 并把占位符（插件名、协议名、类名…）替换成用户输入，得到一个可直接运行的示例。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Button, Space, Typography, List, Input, Form, Select, Tag, message,
  Empty, Modal, Popconfirm, Tooltip, Divider, Switch, Result,
} from 'antd'
import {
  SaveOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined,
  CodeOutlined, CheckCircleOutlined, FileTextOutlined, ApiOutlined,
} from '@ant-design/icons'
import { pluginEditorAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import { useI18n } from '../i18n'

const { Title, Text } = Typography
const { TextArea } = Input

interface TemplateItem {
  key: string
  name: string
  plugin_type: string
  description: string
}

interface PluginFileItem {
  module_name: string
  file_name: string
  file_path: string
  classes: string[]
  updated_at?: string
}

const TEMPLATE_TYPE_LABEL = (tr: (k: string) => string): Record<string, string> => ({
  protocol: tr('label.commProtocol'),
  device_driver: tr('label.deviceDriver'),
  data_parser: tr('label.dataParser'),
  report: tr('card.reportTemplates'),
})

export default function PluginEditor() {
  const { t } = useI18n()
  const navigate = useNavigate()

  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [files, setFiles] = useState<PluginFileItem[]>([])
  const [loading, setLoading] = useState(false)

  const [current, setCurrent] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checkResult, setCheckResult] = useState<any>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()

  const editorRef = useRef<HTMLTextAreaElement | null>(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [tplRes, fileRes] = await Promise.all([
        pluginEditorAPI.listTemplates(),
        pluginEditorAPI.listFiles(),
      ])
      setTemplates(extractData(tplRes, []))
      setFiles(extractData(fileRes, []))
    } catch (err) {
      handleApiError(err, t('msg.loadPluginTplFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  const openFile = async (moduleName: string) => {
    try {
      const res = await pluginEditorAPI.readFile(moduleName)
      const data = extractData(res)
      setCurrent(moduleName)
      setContent(data?.content || '')
      setDirty(false)
      setCheckResult(null)
    } catch (err) {
      handleApiError(err, `${t('msg.readPluginFailed')}`)
    }
  }

  const handleSave = async () => {
    if (!current) return
    setSaving(true)
    try {
      await pluginEditorAPI.writeFile(current, content)
      message.success(t('msg.pluginSaved'))
      setDirty(false)
      loadAll()
    } catch (err) {
      handleApiError(err, t('msg.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleValidate = async () => {
    if (!current) return
    try {
      const res = await pluginEditorAPI.validate(current, content)
      const data = extractData(res)
      setCheckResult(data)
      if (data?.ok) {
        message.success(`${t('msg.syntaxOk')}${data?.classes?.length ? `, ${t('label.pluginClass')} ${data.classes.join(', ')}` : ''}`)
      } else {
        message.error(data?.error || t('msg.checkFailed'))
      }
    } catch (err) {
      handleApiError(err, t('msg.checkError'))
    }
  }

  const handleDelete = async (moduleName: string) => {
    try {
      await pluginEditorAPI.deleteFile(moduleName)
      message.success(`${t('msg.deleted')} ${moduleName}.py`)
      if (current === moduleName) {
        setCurrent(null); setContent(''); setDirty(false); setCheckResult(null)
      }
      loadAll()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
    }
  }

  const handleCreate = async (values: any) => {
    try {
      const res = await pluginEditorAPI.createFile({
        plugin_name: values.plugin_name,
        protocol_name: values.protocol_name,
        template_key: values.template_key,
        version: values.version || '1.0.0',
        description: values.description || '',
        author: values.author || '',
        module_name: values.module_name || undefined,
        overwrite: !!values.overwrite,
      })
      const data = extractData(res)
      message.success(`${t('msg.created')} ${data?.file_name}（${t('label.templateColon')}${values.template_key}）`)
      setCreateOpen(false)
      createForm.resetFields()
      await loadAll()
      if (data?.module_name) {
        setCurrent(data.module_name)
        setContent(data.content || '')
        setDirty(false)
        setCheckResult(null)
      }
    } catch (err) {
      handleApiError(err, `${t('btn.create')}${t('label.plugin')}${t('status.failed')}`)
    }
  }

  const insertSnippet = (snippet: string) => {
    const el = editorRef.current
    if (!el) return
    const start = el.selectionStart ?? content.length
    const end = el.selectionEnd ?? start
    const next = content.slice(0, start) + snippet + content.slice(end)
    setContent(next)
    setDirty(true)
  }

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>{t('tab.pluginEditor')}</Title>
          <Text type="secondary">{t('plugin.editorDesc')}</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadAll}>{t('common.refresh')}</Button>
          <Button onClick={() => navigate('/plugins')} icon={<ApiOutlined />}>{t('tab.manage')}</Button>
          <Button
            type="primary" icon={<PlusOutlined />}
            onClick={() => { setCreateOpen(true); createForm.resetFields() }}
          >{t('btn.newPlugin')}</Button>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Card
          style={{ width: 300, flex: '0 0 300px' }}
          title={<Space><FileTextOutlined /> plugins/ {t('label.directory')}</Space>}
          loading={loading}
        >
          {files.length === 0 ? (
            <Empty description={t('msg.noPluginFiles')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={files}
              rowKey="module_name"
              renderItem={(item) => (
                <List.Item
                  onClick={() => openFile(item.module_name)}
                  style={{
                    cursor: 'pointer',
                    background: current === item.module_name ? 'var(--app-accent-subtle)' : undefined,
                    paddingLeft: 8, paddingRight: 8,
                  }}
                  actions={[
                    <Popconfirm
                      key="del"
                      title={t('msg.deletePluginFile')}
                      onConfirm={(e) => { e?.stopPropagation(); handleDelete(item.module_name) }}
                    >
                      <Button
                        size="small" type="text" danger icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<span style={{ fontSize: 13 }}>{item.file_name}</span>}
                    description={
                      item.classes?.length
                        ? item.classes.map((c) => <Tag key={c} color="purple">{c}</Tag>)
                        : <Text type="secondary" style={{ fontSize: 12 }}>{t('msg.noPluginClass')}</Text>
                    }
                  />
                </List.Item>
              )}
            />
          )}
          <Divider style={{ margin: '8px 0' }} />
          <Text strong style={{ fontSize: 12 }}>{t('label.availableTemplates')}</Text>
          <div style={{ marginTop: 6 }}>
            {templates.map((tpl) => (
              <Tag key={tpl.key} style={{ marginBottom: 4 }}>
                {tpl.name}（{TEMPLATE_TYPE_LABEL(t)[tpl.plugin_type] || tpl.plugin_type}）
              </Tag>
            ))}
          </div>
        </Card>

        <Card style={{ flex: 1, minWidth: 460 }}>
          {!current ? (
            <Result
              icon={<CodeOutlined />}
              title={t('msg.noPluginFile')}
              subTitle={t('plugin.pickOrNew')}
            />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Space wrap>
                <Text strong>{current}.py</Text>
            {dirty && <Tag color="orange">{t('label.unsaved')}</Tag>}
                {!dirty && <Tag color="green">{t('msg.synced')}</Tag>}
                <Button
                  type="primary" icon={<SaveOutlined />} loading={saving}
                  onClick={handleSave}
                >{t('common.save')}</Button>
                <Button icon={<CheckCircleOutlined />} onClick={handleValidate}>{t('btn.syntaxCheck')}</Button>
          <Tooltip title={t('dlg.insertSendSkeleton')}>
                  <Button size="small" onClick={() => insertSnippet(
                    "\n    async def send(self, data):\n        if not self._connected:\n            raise ConnectionError(\"not connected\")\n        return str(data)\n",
            )}>{t('btn.insertSendExample')}</Button>
                </Tooltip>
              </Space>

              {checkResult && (
                <Tag color={checkResult.ok ? 'green' : 'red'}>
                  {checkResult.ok
                    ? `${t('msg.checkPassed')}${checkResult.classes?.length ? ` · ${t('label.pluginClass')} ${checkResult.classes.join(', ')}` : ''}`
                    : `${t('label.checkFailedColon')}${checkResult.error}`}
                </Tag>
              )}

              <TextArea
                ref={(el: any) => { editorRef.current = el?.resizableTextArea?.textArea ?? el }}
                value={content}
                onChange={(e) => { setContent(e.target.value); setDirty(true) }}
                spellCheck={false}
                style={{
                  minHeight: 'calc(100vh - 340px)',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: 13, lineHeight: 1.6,
                  whiteSpace: 'pre', overflow: 'auto',
                }}
              />

              <Text type="secondary" style={{ fontSize: 12 }}>{t('plugin.afterSave')}<code> BaseProtocolPlugin </code>{t('plugin.apiNote')}</Text>
            </Space>
          )}
        </Card>
      </div>

      <Modal
        title={t('btn.newPluginTpl')}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        width={620}
        okText={t('btn.create')}
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}
          initialValues={{ template_key: 'protocol_plugin', version: '1.0.0' }}>
          <Form.Item name="plugin_name" label={t('col.pluginName')} rules={[{ required: true }]}>
            <Input placeholder={t('ph.mg100Example')} />
          </Form.Item>
          <Form.Item
            name="protocol_name" label={t('label.protocolId')} rules={[{ required: true }]}
            extra={t('skill.protocolRule')}
          >
            <Input placeholder={t('ph.protocolExample')} />
          </Form.Item>
          <Form.Item name="template_key" label={t('label.pluginTemplate')} rules={[{ required: true }]}>
            <Select
              options={templates.map((tpl) => ({
                label: `${tpl.name}（${TEMPLATE_TYPE_LABEL(t)[tpl.plugin_type] || tpl.plugin_type}）— ${tpl.description}`,
                value: tpl.key,
              }))}
              placeholder={t('ph.pickTemplate')}
            />
          </Form.Item>
          <Space wrap>
            <Form.Item name="version" label={t('col.version')}>
              <Input style={{ width: 140 }} placeholder="1.0.0" />
            </Form.Item>
            <Form.Item name="author" label={t('label.author')}>
              <Input style={{ width: 160 }} placeholder={t('label.optional')} />
            </Form.Item>
            <Form.Item name="module_name" label={t('ph.fileNameOptional')}>
              <Input style={{ width: 200 }} placeholder={t('ph.defaultPluginFile')} />
            </Form.Item>
          </Space>
          <Form.Item name="description" label={t('col.description')}>
            <Input placeholder={t('ph.pluginSummary')} />
          </Form.Item>
          <Form.Item name="overwrite" label={t('label.overwriteSameName')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('plugin.templateFilled')}
            {t('plugin.openAndCheck')}
          </Text>
        </Form>
      </Modal>
    </div>
  )
}
