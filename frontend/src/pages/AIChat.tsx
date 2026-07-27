import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Input, Button, Select, Space, Typography, message, Spin, Tag,
  Upload, Collapse, Empty, List, Tabs
} from 'antd'
import {
  SendOutlined, AudioOutlined, RobotOutlined, UserOutlined,
  ExperimentOutlined, SearchOutlined, SettingOutlined,
  CloudOutlined, HomeOutlined, ClearOutlined, ApiOutlined
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { aiAPI, testCaseAPI, pluginAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import type { AIModel, AIChatMessage, TestCase } from '../types'

const { Title, Text } = Typography
const { TextArea } = Input

export default function AIChat() {
  const navigate = useNavigate()
  const [models, setModels] = useState<AIModel[]>([])
  const [activeModel, setActiveModel] = useState<string>('')
  const [messages, setMessages] = useState<AIChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const [testCaseResult, setTestCaseResult] = useState<any>(null)
  const [activeTab, setActiveTab] = useState('chat')
  const [queryResult, setQueryResult] = useState<any>(null)
  const [pluginSkills, setPluginSkills] = useState<any[]>([])
  const [selectedSkills, setSelectedSkills] = useState<string[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadModels()
    loadPluginSkills()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadModels = async () => {
    try {
      const res = await aiAPI.listModels()
      const modelList = extractData(res, [])
      setModels(modelList)
      // Auto-select: prefer default, then an active one, then the first model
      // so the chat is usable even if no model is explicitly marked default.
      const active: any =
        modelList.find((m: any) => m.is_default) ||
        modelList.find((m: any) => m.status === 'active') ||
        modelList[0]
      if (active?.id) setActiveModel(active.id)
    } catch (err) {
      console.error('Failed to load models:', err)
    }
  }

  const loadPluginSkills = async () => {
    try {
      const res = await pluginAPI.listSkills()
      setPluginSkills(extractData(res, []))
    } catch (err) {
      console.error('Failed to load plugin skills:', err)
    }
  }

  const handleChat = async () => {
    if (!input.trim() || !activeModel) return
    const userMsg: AIChatMessage = { role: 'user', content: input }
    setMessages(prev => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const res = await aiAPI.chat({
        model_id: activeModel,
        message: userMsg.content,
        session_id: sessionId || undefined,
        input_type: 'text',
        skill_protocols: selectedSkills,
      })
      const data: any = res.data?.data || res.data
      setSessionId(data?.session_id)
      setMessages(prev => [...prev, { role: 'assistant', content: data?.response ?? '（无响应内容）' }])
    } catch (err) {
      // Surface the real error detail (backend returns detail as a string or {message})
      const detail = (err as any)?.response?.data?.detail
      const errMsg = (typeof detail === 'string' ? detail : detail?.message) || 'AI 请求失败，请检查模型配置与网络'
      message.error(errMsg)
      // Also show the error inline so the user always gets a visible response
      setMessages(prev => [...prev, { role: 'assistant', content: `⚠️ 请求失败：${errMsg}` }])
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateTestCases = async () => {
    if (!input.trim() || !activeModel) return
    setLoading(true)
    try {
      const res = await aiAPI.generateTestCases({
        requirements: input,
        model_id: activeModel,
        input_type: 'text',
        skill_protocols: selectedSkills,
      })
      setTestCaseResult(res.data.data || res.data)
      setActiveTab('result')
    } catch (err) {
      handleApiError(err, '生成测试用例失败')
    } finally {
      setLoading(false)
    }
  }

  const handleNaturalQuery = async () => {
    if (!input.trim() || !activeModel) return
    setLoading(true)
    try {
      const res = await aiAPI.naturalLanguageQuery({
        query: input,
        model_id: activeModel,
      })
      setQueryResult(res.data.data || res.data)
      setActiveTab('query')
    } catch (err) {
      handleApiError(err, '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveTestCase = async (tc: any) => {
    try {
      await testCaseAPI.create({
        name: tc.name,
        description: tc.description,
        steps: tc.steps || [],
        expected_result: tc.expected_result,
        parameters: tc.parameters || {},
        devices_required: tc.devices_required || [],
        tags: tc.tags || [],
      })
      message.success(`测试用例 "${tc.name}" 已保存`)
    } catch (err) {
      message.error('保存测试用例失败')
    }
  }

  const handleClear = () => {
    setMessages([])
    setSessionId('')
    setTestCaseResult(null)
    setQueryResult(null)
  }

  const handleVoiceInput = () => {
    message.info('语音输入功能：请使用浏览器录音后上传')
  }

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>AI 助手</Title>
        <Space>
          <Select
            placeholder="选择 AI 模型"
            value={activeModel || undefined}
            onChange={setActiveModel}
            style={{ width: 280 }}
            options={models.map(m => ({
              label: `${m.name} (${m.provider})`,
              value: m.id,
            }))}
            notFoundContent={
              <Empty
                description="暂无模型，请先配置"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button type="primary" size="small" onClick={() => navigate('/model-config')}>
                  去配置模型
                </Button>
              </Empty>
            }
          />
          <Button icon={<ClearOutlined />} onClick={handleClear}>清空对话</Button>
        </Space>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入测试需求，或直接与 AI 对话..."
          autoSize={{ minRows: 3, maxRows: 6 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault()
              handleChat()
            }
          }}
          disabled={!activeModel}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
          <Space>
            <Button
              icon={<AudioOutlined />}
              onClick={handleVoiceInput}
              disabled={!activeModel}
            >
              语音输入
            </Button>
            <Select
              mode="multiple"
              allowClear
              placeholder={
                <span><ApiOutlined /> 导入插件 Skill（设备手册）</span>
              }
              value={selectedSkills}
              onChange={setSelectedSkills}
              style={{ minWidth: 260 }}
              maxTagCount="responsive"
              options={pluginSkills.map((s: any) => ({
                label: `${s.name} (${s.protocol})`,
                value: s.protocol,
              }))}
              notFoundContent={<Empty description="暂无插件 Skill" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            />
            {selectedSkills.length > 0 && (
              <Tag color="blue">已导入 {selectedSkills.length} 个设备 Skill</Tag>
            )}
          </Space>
          <Space>
            <Button
              icon={<SearchOutlined />}
              onClick={handleNaturalQuery}
              disabled={!activeModel || !input.trim()}
            >
              查询数据库
            </Button>
            <Button
              icon={<ExperimentOutlined />}
              onClick={handleGenerateTestCases}
              disabled={!activeModel || !input.trim()}
              loading={loading}
            >
              生成测试用例
            </Button>
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={handleChat}
              disabled={!activeModel || !input.trim()}
              loading={loading}
            >
              发送
            </Button>
          </Space>
        </div>
      </Card>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'chat',
          label: '对话',
          children: (
            <Card>
              {messages.length === 0 ? (
                <Empty description="开始与 AI 对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <div style={{ maxHeight: 500, overflow: 'auto' }}>
                  {messages.map((msg, i) => (
                    <div
                      key={i}
                      style={{
                        display: 'flex',
                        gap: 12,
                        padding: '12px 0',
                        borderBottom: '1px solid #f0f0f0',
                      }}
                    >
                      <div>
                        {msg.role === 'assistant' ? (
                          <RobotOutlined style={{ color: '#1677ff', fontSize: 20 }} />
                        ) : (
                          <UserOutlined style={{ color: '#52c41a', fontSize: 20 }} />
                        )}
                      </div>
                      <div style={{ flex: 1 }}>
                        <Text strong>{msg.role === 'assistant' ? 'AI' : '用户'}</Text>
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </Card>
          ),
        },
        {
          key: 'result',
          label: '生成的测试用例',
          children: (
            <Card>
              {testCaseResult ? (
                <div>
                  <Title level={5}>AI 生成结果</Title>
                  {testCaseResult.parsed?.test_cases?.length > 0 ? (
                    <List
                      dataSource={testCaseResult.parsed.test_cases}
                      renderItem={(tc: any) => (
                        <List.Item
                          actions={[
                            <Button
                              type="primary"
                              size="small"
                              onClick={() => handleSaveTestCase(tc)}
                            >
                              保存用例
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={tc.name}
                            description={tc.description}
                          />
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Empty description="未能解析出测试用例" />
                  )}
                </div>
              ) : (
                <Empty description="尚未生成测试用例" />
              )}
            </Card>
          ),
        },
        {
          key: 'query',
          label: '数据库查询结果',
          children: (
            <Card>
              {queryResult ? (
                <div>
                  <Title level={5}>查询结果</Title>
                  <Text type="secondary">SQL: {queryResult.sql_generated}</Text>
                  <p>共找到 {queryResult.result_count} 条记录</p>
                  {queryResult.results.length > 0 && (
                    <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, overflow: 'auto' }}>
                      {JSON.stringify(queryResult.results, null, 2)}
                    </pre>
                  )}
                </div>
              ) : (
                <Empty description="尚未查询数据库" />
              )}
            </Card>
          ),
        },
      ]} />
    </div>
  )
}
