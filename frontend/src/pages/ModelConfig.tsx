import { useEffect, useRef, useState } from 'react'
import {
  Card, Table, Button, Modal, Form, Input, Select, Switch, Space, Tag,
  message, Popconfirm, Typography, Empty, Drawer,
} from 'antd'
import {
  PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined,
  CheckCircleOutlined, ThunderboltOutlined, ApiOutlined, MessageOutlined,
} from '@ant-design/icons'
import { aiAPI } from '../services/api'
import { _errorMessage } from '../services/apiHelper'
import { extractData, handleApiError } from '../services/apiHelper'
import { PROVIDERS, type AIModel, type AIModelConfigRequest, type AIChatMessage } from '../types'
import { useI18n } from '../i18n'

const { Title, Text } = Typography

// Sentinel shown in the edit form to indicate "a key is already saved".
// It is never sent to the backend — an unchanged mask means "keep existing".
const API_KEY_MASK = '•'.repeat(12)

export default function ModelConfig() {
  const { t } = useI18n()
  const [models, setModels] = useState<AIModel[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editing, setEditing] = useState<AIModel | null>(null)
  const [testingId, setTestingId] = useState<string>('')
  const [form] = Form.useForm()

  // Watch the provider field to show provider-specific model-name hints.
  const providerWatch = Form.useWatch('provider', form)

  // Model chat/test window state
  const [chatModel, setChatModel] = useState<AIModel | null>(null)
  const [chatVisible, setChatVisible] = useState(false)
  const [chatMessages, setChatMessages] = useState<AIChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const loadModels = async () => {
    setLoading(true)
    try {
      const res = await aiAPI.listModels()
      setModels(extractData(res, []))
    } catch (err) {
      handleApiError(err, t('msg.loadModelsFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadModels() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ provider: 'openai', is_default: false, parameters: { temperature: 0.7, max_tokens: 16384 } })
    setModalVisible(true)
  }

  const openEdit = (model: AIModel) => {
    setEditing(model)
    form.resetFields()
    form.setFieldsValue({
      name: model.name,
      provider: model.provider,
      model_name: model.model_name,
      base_url: model.base_url,
      is_default: model.is_default,
      // Show a mask so the user can see a key is already saved. The real key
      // is never sent back to the client; an unchanged mask keeps the existing
      // key on the server (see handleSubmit).
      api_key: API_KEY_MASK,
      parameters: model.parameters || { temperature: 0.7, max_tokens: 16384 },
    })
    setModalVisible(true)
  }

  const handleSubmit = async (values: any) => {
    let parameters: Record<string, any> = {}
    if (values.parameters) {
      if (typeof values.parameters === 'string') {
        try {
          parameters = JSON.parse(values.parameters)
        } catch {
          message.error(t('msg.advParamsInvalid'))
          return
        }
      } else {
        parameters = values.parameters
      }
    }
    // Only send the key if the user actually typed a new one. The mask or an
    // empty field means "keep the existing saved key" (sent as undefined so
    // the backend preserves it).
    const apiKey =
      values.api_key && values.api_key !== API_KEY_MASK ? values.api_key : undefined
    const payload: AIModelConfigRequest = {
      name: values.name,
      provider: values.provider,
      model_name: values.model_name,
      api_key: apiKey,
      base_url: values.base_url || undefined,
      is_default: values.is_default,
      parameters,
    }

    // Custom (OpenAI-compatible) provider MUST have a Base URL, otherwise the
    // request silently falls back to OpenAI and fails with a confusing error.
    if (values.provider === 'custom' && !values.base_url?.trim()) {
      message.error(t('model.baseUrlRequired'))
      return
    }
    try {
      if (editing) {
        await aiAPI.updateModel(editing.id, payload)
        message.success(t('msg.modelUpdated'))
      } else {
        await aiAPI.createModel(payload)
        message.success(t('msg.modelAdded'))
      }
      setModalVisible(false)
      loadModels()
    } catch (err) {
      handleApiError(err, t('msg.saveFailed'))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await aiAPI.deleteModel(id)
      message.success(t('msg.modelDeleted'))
      loadModels()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
    }
  }

  const handleSetDefault = async (id: string) => {
    try {
      await aiAPI.activateModel(id)
      message.success(t('msg.defaultModelSet'))
      loadModels()
    } catch (err) {
      handleApiError(err, t('msg.setFailed'))
    }
  }

    const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const res = await aiAPI.testModel(id)
      const data: any = res.data?.data || res.data
      if (data?.status === 'ok') {
        message.success(t('msg.connTestOk'))
      } else {
        // Show the concrete failure reason returned by the backend
        const reason = data?.error || t('label.unknownReason')
        message.error(`${t('label.connTestFailed')}${reason}`)
      }
    } catch (err) {
      handleApiError(err, t('msg.connTestFail'))
    } finally {
      setTestingId('')
    }
  }

  const openChat = (model: AIModel) => {
    setChatModel(model)
    setChatMessages([])
    setChatInput('')
    setChatVisible(true)
  }

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  const handleChatSend = async () => {
    if (!chatInput.trim() || !chatModel || chatLoading) return
    const text = chatInput.trim()
    setChatMessages(prev => [...prev, { role: 'user', content: text }])
    setChatInput('')
    setChatLoading(true)
    try {
      const res = await aiAPI.chat({
        model_id: chatModel.id,
        message: text,
        input_type: 'text',
      })
      const data: any = res.data?.data || res.data
      setChatMessages(prev => [...prev, { role: 'assistant', content: data?.response || t('msg.noResponse') }])
    } catch (err) {
      const errMsg = _errorMessage(err, t('msg.chatFailed'))
      setChatMessages(prev => [...prev, { role: 'assistant', content: `⚠️ ${t('label.errorColon')}${errMsg}` }])
    } finally {
      setChatLoading(false)
    }
  }

  const columns = [
    {
      title: t('col.name'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, r: AIModel) => (
        <Space>
          <ApiOutlined />
          {name}
          {r.is_default && <Tag color="green">{t('status.default')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('col.vendor'),
      dataIndex: 'provider',
      key: 'provider',
      render: (p: string) => <Tag>{PROVIDERS[p]?.label || p}</Tag>,
    },
    {
      title: t('col.model'),
      dataIndex: 'model_name',
      key: 'model_name',
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">{t('status.default')}</Text>,
    },
    {
      title: t('col.status'),
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'green' : s === 'error' ? 'red' : 'default'}>{s}</Tag>
      ),
    },
    {
      title: t('col.actions'),
      key: 'actions',
      render: (_: any, record: AIModel) => (
        <Space>
          {!record.is_default && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => handleSetDefault(record.id)}
            >{t('btn.setDefault')}</Button>
          )}
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            loading={testingId === record.id}
            onClick={() => handleTest(record.id)}
          >{t('btn.test')}</Button>
          <Button
            size="small"
            icon={<MessageOutlined />}
            onClick={() => openChat(record)}
          >{t('btn.chatTest')}</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title={t('msg.deleteModel')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>{t('page.modelConfig')}</Title>
          <Text type="secondary">{t('model.configDesc')}</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadModels}>{t('common.refresh')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t('btn.addModel')}</Button>
        </Space>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={models}
          rowKey="id"
          loading={loading}
          pagination={false}
          locale={{
            emptyText: (
              <Empty description={t('model.none')}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>{t('btn.addModel')}</Button>
              </Empty>
            ),
          }}
        />
      </Card>

      <Modal
        title={editing ? t('btn.editModel') : t('btn.addModel')}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label={t('label.configName')} rules={[{ required: true, message: t('msg.enterConfigName') }]}>
            <Input placeholder={t('label.exampleMine')} />
          </Form.Item>
          <Form.Item name="provider" label={t('col.vendor')} rules={[{ required: true }]}>
            <Select
              placeholder={t('label.pickProvider')}
              options={Object.entries(PROVIDERS).map(([k, v]) => ({ label: v.label, value: k }))}
              onChange={(val: any) => {
                const info = PROVIDERS[val]
                if (info?.default_base_url) form.setFieldValue('base_url', info.default_base_url)
                // Wipe the model_name when switching providers so the user
                // sees the provider-specific placeholder and doesn't accidentally
                // submit a stale name from the previous supplier.
                if (!editing) form.setFieldValue('model_name', undefined)
              }}
            />
          </Form.Item>
          <Form.Item name="model_name" label={t('label.modelName')} rules={[{ required: true, message: t('msg.enterModelName') }]}>
            <Input
              placeholder={
                providerWatch
                  ? PROVIDERS[providerWatch]?.hint || t('msg.enterModelName')
                  : t('model.nameExample')
              }
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={editing ? t('model.keyHint') : t('model.storageNote')}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" extra={t('model.baseUrlFull')}>
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item name="is_default" label={t('btn.setDefaultModel')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="parameters" label={t('label.advancedParams')} extra={t('model.advancedExample')}>
            <Input.TextArea rows={3} placeholder='{"temperature": 0.7, "max_tokens": 16384}' />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`${t('label.chatTest')} ${chatModel?.name || ''} (${PROVIDERS[chatModel?.provider || '']?.label || chatModel?.provider})`}
        open={chatVisible}
        onClose={() => setChatVisible(false)}
        width={520}
      >
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '8px 4px',
            minHeight: 320,
            maxHeight: 'calc(100vh - 180px)',
          }}
        >
          {chatMessages.length === 0 ? (
            <Empty
              description={t('model.testHint')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            chatMessages.map((msg, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  gap: 8,
                  padding: '10px 0',
                  borderBottom: '1px solid var(--app-border)',
                }}
              >
                <div style={{ fontWeight: 600, color: msg.role === 'assistant' ? 'var(--app-accent)' : 'var(--app-pass)' }}>
                  {msg.role === 'assistant' ? t('label.assistant') : t('label.me')}
                </div>
                <div style={{ flex: 1, whiteSpace: 'pre-wrap' }}>{msg.content}</div>
              </div>
            ))
          )}
          <div ref={chatEndRef} />
        </div>
        <Input.TextArea
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          placeholder={t('model.chatHint')}
          autoSize={{ minRows: 2, maxRows: 5 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleChatSend()
            }
          }}
          disabled={chatLoading}
          style={{ marginTop: 12 }}
        />
        <div style={{ textAlign: 'right', marginTop: 8 }}>
          <Button
            type="primary"
            icon={<MessageOutlined />}
            onClick={handleChatSend}
            loading={chatLoading}
            disabled={!chatInput.trim()}
          >{t('btn.send')}</Button>
        </div>
      </Drawer>
    </div>
  )
}
