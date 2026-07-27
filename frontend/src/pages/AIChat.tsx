import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Input, Button, Select, Space, Typography, message, Tag,
  Collapse, Empty, List, Tabs, Tooltip
} from 'antd'
import {
  SendOutlined, AudioOutlined, RobotOutlined, UserOutlined,
  ExperimentOutlined, SearchOutlined, SettingOutlined,
  ClearOutlined, ApiOutlined, ImportOutlined, CheckCircleOutlined
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { aiAPI, testCaseAPI, pluginAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import { useChatStore } from '../stores/chatStore'
import type { AIModel, TestCase } from '../types'

const { Title, Text } = Typography
const { TextArea } = Input

// Virtual built-in "skills" that are always available (not from plugins).
// Checked by default so users immediately get test-case generation capability.
const BUILTIN_SKILLS = [
  { name: '测试用例生成', protocol: '__builtin_testgen', default: true },
]

export default function AIChat() {
  const navigate = useNavigate()

  // --- global persisted state (survives page switches) ---
  const sessionId = useChatStore((s) => s.sessionId)
  const messages = useChatStore((s) => s.messages)
  const testCaseResult = useChatStore((s) => s.testCaseResult)
  const queryResult = useChatStore((s) => s.queryResult)
  const activeTab = useChatStore((s) => s.activeTab)
  const selectedSkills = useChatStore((s) => s.selectedSkills)
  const input = useChatStore((s) => s.input)

  const setSessionId = useChatStore((s) => s.setSessionId)
  const addMessage = useChatStore((s) => s.addMessage)
  const setMessages = useChatStore((s) => s.setMessages)
  const setTestCaseResult = useChatStore((s) => s.setTestCaseResult)
  const setQueryResult = useChatStore((s) => s.setQueryResult)
  const setActiveTab = useChatStore((s) => s.setActiveTab)
  const setSelectedSkills = useChatStore((s) => s.setSelectedSkills)
  const setInput = useChatStore((s) => s.setInput)
  const clearStore = useChatStore((s) => s.clear)

  // --- local UI-only state ---
  const [models, setModels] = useState<AIModel[]>([])
  const [activeModel, setActiveModel] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [pluginSkills, setPluginSkills] = useState<any[]>([])
  const [importingIds, setImportingIds] = useState<Set<string>>(new Set())
  const [importingAll, setImportingAll] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  // --- init ---
  useEffect(() => {
    loadModels()
    loadPluginSkills()
    // Default-select builtin skills
    const store = useChatStore.getState()
    if (store.selectedSkills.length === 0) {
      store.setSelectedSkills(
        BUILTIN_SKILLS.filter((s) => s.default).map((s) => s.protocol),
      )
    }
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadModels = async () => {
    try {
      const res = await aiAPI.listModels()
      const ml = extractData(res, [])
      setModels(ml)
      const best: any = ml.find((m: any) => m.is_default) || ml.find((m: any) => m.status === 'active') || ml[0]
      if (best?.id) setActiveModel(best.id)
    } catch (err) {
      console.error('Failed to load models:', err)
    }
  }

  const loadPluginSkills = async () => {
    try {
      const res = await pluginAPI.listSkills()
      setPluginSkills(extractData(res, []))
    } catch { /* ignore */ }
  }

  // --- Chat ---
  const handleChat = async () => {
    if (!input.trim() || !activeModel) return
    const msg = input.trim()
    addMessage({ role: 'user', content: msg })
    setInput('')
    setLoading(true)

    try {
      const res = await aiAPI.chat({
        model_id: activeModel,
        message: msg,
        session_id: sessionId || undefined,
        input_type: 'text',
        skill_protocols: selectedSkills.filter((s) => !s.startsWith('__builtin_')),
      })
      const data: any = res.data?.data || res.data
      setSessionId(data?.session_id ?? '')
      addMessage({ role: 'assistant', content: data?.response ?? '（无响应内容）' })
    } catch (err) {
      const detail = (err as any)?.response?.data?.detail
      const errMsg = (typeof detail === 'string' ? detail : detail?.message) || 'AI 请求失败'
      message.error(errMsg)
      addMessage({ role: 'assistant', content: `⚠️ 请求失败：${errMsg}` })
    } finally {
      setLoading(false)
    }
  }

  // --- Generate test cases ---
  const handleGenerateTestCases = async () => {
    if (!input.trim() || !activeModel) return
    setLoading(true)
    try {
      const res = await aiAPI.generateTestCases({
        requirements: input,
        model_id: activeModel,
        input_type: 'text',
        skill_protocols: selectedSkills.filter((s) => !s.startsWith('__builtin_')),
      })
      const data: any = res.data?.data || res.data
      setTestCaseResult(data)
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
      const res = await aiAPI.naturalLanguageQuery({ query: input, model_id: activeModel })
      const data: any = res.data?.data || res.data
      setQueryResult(data)
      setActiveTab('query')
    } catch (err) {
      handleApiError(err, '查询失败')
    } finally {
      setLoading(false)
    }
  }

  // --- Save one test case ---
  const handleSaveOne = async (tc: any) => {
    setImportingIds((prev) => new Set(prev).add(tc.name))
    try {
      await testCaseAPI.create({
        name: tc.name,
        description: tc.description || '',
        steps: tc.steps || [],
        expected_result: tc.expected_result || '',
        parameters: tc.parameters || {},
        devices_required: tc.devices_required || [],
        tags: tc.tags || [],
      })
      message.success(`「${tc.name}」已导入测试用例列表`)
    } catch (err) {
      message.error(`「${tc.name}」导入失败`)
    } finally {
      setImportingIds((prev) => {
        const next = new Set(prev)
        next.delete(tc.name)
        return next
      })
    }
  }

  // --- Import ALL generated test cases at once ---
  const handleImportAll = async () => {
    const cases = testCaseResult?.parsed?.test_cases || []
    if (cases.length === 0) {
      message.warning('没有可导入的测试用例')
      return
    }
    setImportingAll(true)
    let ok = 0
    for (const tc of cases) {
      try {
        await testCaseAPI.create({
          name: tc.name,
          description: tc.description || '',
          steps: tc.steps || [],
          expected_result: tc.expected_result || '',
          parameters: tc.parameters || {},
          devices_required: tc.devices_required || [],
          tags: tc.tags || [],
        })
        ok++
      } catch { /* skip failures */ }
    }
    setImportingAll(false)
    message.success(`已导入 ${ok}/${cases.length} 个测试用例`)
    if (ok > 0) navigate('/testcases')
  }

  // --- Clear ---
  const handleClear = () => {
    clearStore()
  }

  const handleVoiceInput = () => {
    message.info('语音输入功能：请使用浏览器录音后上传')
  }

  // Combine built-in + plugin skills for the selector
  const allSkills = [
    ...BUILTIN_SKILLS.map((s) => ({ name: s.name, protocol: s.protocol, builtin: true })),
    ...pluginSkills.map((s: any) => ({ name: s.name, protocol: s.protocol, builtin: false })),
  ]

  const caseCount = testCaseResult?.parsed?.test_cases?.length || 0

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
            options={models.map((m) => ({
              label: `${m.name} (${m.provider})`,
              value: m.id,
            }))}
            notFoundContent={
              <Empty description="暂无模型，请先配置" image={Empty.PRESENTED_IMAGE_SIMPLE}>
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
            <Button icon={<AudioOutlined />} onClick={handleVoiceInput} disabled={!activeModel}>
              语音输入
            </Button>
            <Select
              mode="multiple"
              allowClear
              value={selectedSkills}
              onChange={setSelectedSkills}
              style={{ minWidth: 260 }}
              maxTagCount="responsive"
              placeholder={<span><ApiOutlined /> 导入 Skill / 知识库</span>}
              options={allSkills.map((s) => ({
                label: s.builtin ? `⚡ ${s.name}（内置）` : `${s.name} (${s.protocol})`,
                value: s.protocol,
              }))}
            />
            {selectedSkills.length > 0 && (
              <Tag color="blue">已启用 {selectedSkills.length} 项 Skill</Tag>
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

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
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
                          display: 'flex', gap: 12,
                          padding: '12px 0', borderBottom: '1px solid #f0f0f0',
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
            label: (
              <span>
                生成的测试用例
                {caseCount > 0 && (
                  <Tag color="blue" style={{ marginLeft: 6 }}>{caseCount}</Tag>
                )}
              </span>
            ),
            children: (
              <Card>
                {testCaseResult ? (
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <Title level={5} style={{ margin: 0 }}>AI 生成结果</Title>
                      {caseCount > 0 && (
                        <Button
                          type="primary"
                          icon={<ImportOutlined />}
                          onClick={handleImportAll}
                          loading={importingAll}
                        >
                          一键导入全部 ({caseCount} 个)
                        </Button>
                      )}
                    </div>
                    {caseCount > 0 ? (
                      <List
                        dataSource={testCaseResult.parsed.test_cases}
                        renderItem={(tc: any) => {
                          const stepCount = tc.steps?.length || 0
                          return (
                            <List.Item
                              actions={[
                                <Tag color="default" key="steps">
                                  {stepCount} 步骤
                                </Tag>,
                                <Tooltip title="导入到测试用例列表" key="import">
                                  <Button
                                    type="link"
                                    size="small"
                                    icon={<ImportOutlined />}
                                    loading={importingIds.has(tc.name)}
                                    onClick={() => handleSaveOne(tc)}
                                  >
                                    导入
                                  </Button>
                                </Tooltip>,
                              ]}
                            >
                              <List.Item.Meta
                                title={tc.name}
                                description={
                                  <Text type="secondary" ellipsis style={{ maxWidth: 400 }}>
                                    {tc.description || '（无描述）'}
                                  </Text>
                                }
                              />
                            </List.Item>
                          )
                        }}
                      />
                    ) : (
                      <Empty description="未能解析出测试用例" />
                    )}
                  </div>
                ) : (
                  <Empty description="尚未生成测试用例。输入需求后点击「生成测试用例」" />
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
                    <p>
                      共找到 {queryResult.result_count} 条记录
                    </p>
                    {queryResult.results?.length > 0 && (
                      <pre
                        style={{
                          background: '#f5f5f5', padding: 16,
                          borderRadius: 8, overflow: 'auto',
                        }}
                      >
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
        ]}
      />
    </div>
  )
}
