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

const { Title, Text } = Typography

// Sentinel shown in the edit form to indicate "a key is already saved".
// It is never sent to the backend — an unchanged mask means "keep existing".
const API_KEY_MASK = '•'.repeat(12)

export default function ModelConfig() {
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
      handleApiError(err, '加载模型列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadModels() }, [])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ provider: 'openai', is_default: false, parameters: { temperature: 0.7, max_tokens: 2048 } })
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
      parameters: model.parameters || { temperature: 0.7, max_tokens: 2048 },
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
          message.error('高级参数不是合法的 JSON')
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
      message.error('自定义供应商必须填写 Base URL（OpenAI 兼容接口地址）')
      return
    }
    try {
      if (editing) {
        await aiAPI.updateModel(editing.id, payload)
        message.success('模型已更新')
      } else {
        await aiAPI.createModel(payload)
        message.success('模型已添加')
      }
      setModalVisible(false)
      loadModels()
    } catch (err) {
      handleApiError(err, '保存失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await aiAPI.deleteModel(id)
      message.success('模型已删除')
      loadModels()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const handleSetDefault = async (id: string) => {
    try {
      await aiAPI.activateModel(id)
      message.success('已设为默认模型')
      loadModels()
    } catch (err) {
      handleApiError(err, '设置失败')
    }
  }

    const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const res = await aiAPI.testModel(id)
      const data: any = res.data?.data || res.data
      if (data?.status === 'ok') {
        message.success('连接测试成功')
      } else {
        // Show the concrete failure reason returned by the backend
        const reason = data?.error || '未知原因'
        message.error(`连接测试失败：${reason}`)
      }
    } catch (err) {
      handleApiError(err, '连接测试失败')
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
      setChatMessages(prev => [...prev, { role: 'assistant', content: data?.response || '（无响应内容）' }])
    } catch (err) {
      const errMsg = _errorMessage(err, '对话失败')
      setChatMessages(prev => [...prev, { role: 'assistant', content: `⚠️ 错误：${errMsg}` }])
    } finally {
      setChatLoading(false)
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, r: AIModel) => (
        <Space>
          <ApiOutlined />
          {name}
          {r.is_default && <Tag color="green">默认</Tag>}
        </Space>
      ),
    },
    {
      title: '供应商',
      dataIndex: 'provider',
      key: 'provider',
      render: (p: string) => <Tag>{PROVIDERS[p]?.label || p}</Tag>,
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      key: 'model_name',
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      ellipsis: true,
      render: (v: string) => v || <Text type="secondary">默认</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'green' : s === 'error' ? 'red' : 'default'}>{s}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: AIModel) => (
        <Space>
          {!record.is_default && (
            <Button
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => handleSetDefault(record.id)}
            >
              设为默认
            </Button>
          )}
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            loading={testingId === record.id}
            onClick={() => handleTest(record.id)}
          >
            测试
          </Button>
          <Button
            size="small"
            icon={<MessageOutlined />}
            onClick={() => openChat(record)}
          >
            对话测试
          </Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Popconfirm title="确定删除该模型？" onConfirm={() => handleDelete(record.id)}>
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
          <Title level={3} style={{ margin: 0 }}>模型配置</Title>
          <Text type="secondary">配置 AI 模型（通过 API Key 调用主流大模型）</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadModels}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            添加模型
          </Button>
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
              <Empty description="暂无模型配置，请点击「添加模型」">
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                  添加模型
                </Button>
              </Empty>
            ),
          }}
        />
      </Card>

      <Modal
        title={editing ? '编辑模型' : '添加模型'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label="配置名称" rules={[{ required: true, message: '请输入配置名称' }]}>
            <Input placeholder="例如：我的 OpenAI" />
          </Form.Item>
          <Form.Item name="provider" label="供应商" rules={[{ required: true }]}>
            <Select
              placeholder="选择模型供应商"
              options={Object.entries(PROVIDERS).map(([k, v]) => ({ label: v.label, value: k }))}
              onChange={(val) => {
                const info = PROVIDERS[val]
                if (info?.default_base_url) form.setFieldValue('base_url', info.default_base_url)
                // Wipe the model_name when switching providers so the user
                // sees the provider-specific placeholder and doesn't accidentally
                // submit a stale name from the previous supplier.
                if (!editing) form.setFieldValue('model_name', undefined)
              }}
            />
          </Form.Item>
          <Form.Item name="model_name" label="模型名称" rules={[{ required: true, message: '请输入模型名称' }]}>
            <Input
              placeholder={
                providerWatch
                  ? PROVIDERS[providerWatch]?.hint || '请输入模型名称'
                  : '例如：gpt-4o / claude-3-opus / qwen-max'
              }
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={editing ? '已保存的 Key 以掩码显示；留空或不变更即保留原 Key，输入新值则覆盖' : '本地存储，未加密（演示环境）'}
          >
            <Input.Password placeholder="sk-..." />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL" extra="OpenAI 兼容接口地址；留空使用供应商默认地址">
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item name="is_default" label="设为默认模型" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="parameters" label="高级参数" extra="temperature / max_tokens 等">
            <Input.TextArea rows={3} placeholder='{"temperature": 0.7, "max_tokens": 2048}' />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={`对话测试 — ${chatModel?.name || ''} (${PROVIDERS[chatModel?.provider || '']?.label || chatModel?.provider})`}
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
              description="发送一条消息以测试该模型的对话能力"
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
                  borderBottom: '1px solid #f0f0f0',
                }}
              >
                <div style={{ fontWeight: 600, color: msg.role === 'assistant' ? '#1677ff' : '#52c41a' }}>
                  {msg.role === 'assistant' ? 'AI' : '我'}
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
          placeholder="输入消息，Enter 发送，Shift+Enter 换行"
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
          >
            发送
          </Button>
        </div>
      </Drawer>
    </div>
  )
}
