import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Input, Button, Select, Space, Typography, message, Tag,
  Collapse, Empty, List, Tabs, Tooltip, Modal, Divider, Alert,
  Upload, Image,
} from 'antd'
import {
  SendOutlined, AudioOutlined, RobotOutlined, UserOutlined,
  DiffOutlined, SearchOutlined, SettingOutlined,
  ClearOutlined, ApiOutlined, ImportOutlined, CheckCircleOutlined,
  EyeOutlined, BulbOutlined, SaveOutlined, DeleteOutlined,
  FileMarkdownOutlined, EditOutlined, PaperClipOutlined, FileOutlined,
} from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { aiAPI, testCaseAPI, pluginAPI, deviceAPI, memoryAPI } from '../services/api'
import { extractData, extractItems, handleApiError, _errorMessage } from '../services/apiHelper'
import { useChatStore } from '../stores/chatStore'
import TestCasePreviewModal from '../components/ai/TestCasePreviewModal'
import type { AIModel, TestCase } from '../types'

const { Title, Text } = Typography
const { TextArea } = Input

// Virtual built-in "skills" that are always available (not from plugins).
// Checked by default so users immediately get test-case generation capability.
const BUILTIN_SKILLS = [
  { name: '测试用例生成', protocol: '__builtin_testgen', default: true },
]

/** Height of the scrollable output area (the input stays visible below it). */
const OUTPUT_STYLE: React.CSSProperties = {
  height: 'calc(100vh - 400px)',
  minHeight: 260,
  overflow: 'auto',
}

const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

interface Attachment {
  uid: string
  name: string
  size: number
  mime: string
  /** base64 payload WITHOUT the `data:...;base64,` prefix */
  data: string
  kind: 'image' | 'file'
}

const readFileAsBase64 = (file: File): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('读取文件失败'))
    reader.readAsDataURL(file)
  })

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
  const refineInput = useChatStore((s) => s.refineInput)
  const memoryProject = useChatStore((s) => s.memoryProject)

  const setSessionId = useChatStore((s) => s.setSessionId)
  const addMessage = useChatStore((s) => s.addMessage)
  const setMessages = useChatStore((s) => s.setMessages)
  const setTestCaseResult = useChatStore((s) => s.setTestCaseResult)
  const setQueryResult = useChatStore((s) => s.setQueryResult)
  const setActiveTab = useChatStore((s) => s.setActiveTab)
  const setSelectedSkills = useChatStore((s) => s.setSelectedSkills)
  const setInput = useChatStore((s) => s.setInput)
  const setRefineInput = useChatStore((s) => s.setRefineInput)
  const setMemoryProject = useChatStore((s) => s.setMemoryProject)
  const clearStore = useChatStore((s) => s.clear)

  // --- local UI-only state ---
  const [models, setModels] = useState<AIModel[]>([])
  const [activeModel, setActiveModel] = useState<string>('')
  const [chatLoading, setChatLoading] = useState(false)
  const [genLoading, setGenLoading] = useState(false)
  const [queryLoading, setQueryLoading] = useState(false)
  const [pluginSkills, setPluginSkills] = useState<any[]>([])
  const [importingIds, setImportingIds] = useState<Set<string>>(new Set())
  const [importingAll, setImportingAll] = useState(false)
  const [devices, setDevices] = useState<any[]>([])

  // --- generated test case: preview + conversational refinement ---
  const [previewCase, setPreviewCase] = useState<any | null>(null)
  const [refining, setRefining] = useState(false)
  const [refineLog, setRefineLog] = useState<string[]>([])

  // --- attachments (files + images) ---
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [dragging, setDragging] = useState(false)

  // --- project memory ---
  const [memories, setMemories] = useState<any[]>([])
  const [memDraft, setMemDraft] = useState('')
  const [memView, setMemView] = useState<{ name: string; content: string } | null>(null)
  const [extracting, setExtracting] = useState(false)
  const [memSaving, setMemSaving] = useState(false)

  const messagesEndRef = useRef<HTMLDivElement>(null)

  /** Compact device payload sent to the generator (id + protocol + name). */
  const devicePayload = () => (Array.isArray(devices) ? devices : []).map((d: any) => ({
    id: d.id,
    name: d.name,
    type: d.type,
    protocol: d.protocol,
    status: d.status,
  }))

  const attachmentPayload = () =>
    attachments.map((a) => ({ name: a.name, size: a.size, mime: a.mime, data: a.data }))

  useEffect(() => {
    loadModels()
    loadPluginSkills()
    loadDevices()
    loadMemories()
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

  const loadDevices = async () => {
    try {
      const res = await deviceAPI.list()
      setDevices(extractItems(res))
    } catch { /* device list is optional */ }
  }

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

  // --- Attachments ---
  const addFiles = async (fileList: FileList | File[]) => {
    const files = Array.from(fileList || [])
    for (const file of files) {
      if (file.size > MAX_ATTACHMENT_BYTES) {
        message.warning(`「${file.name}」超过 10MB，已跳过`)
        continue
      }
      try {
        const dataUrl = await readFileAsBase64(file)
        const base64 = dataUrl.split(',')[1] || ''
        const mime = file.type || 'application/octet-stream'
        setAttachments((prev) => [...prev, {
          uid: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          size: file.size,
          mime,
          data: base64,
          kind: mime.startsWith('image/') ? 'image' : 'file',
        }])
      } catch {
        message.error(`读取「${file.name}」失败`)
      }
    }
  }

  const removeAttachment = (uid: string) =>
    setAttachments((prev) => prev.filter((a) => a.uid !== uid))

  // --- Project memory ---
  const loadMemories = async () => {
    try {
      const res = await memoryAPI.list()
      setMemories(extractData(res, []))
    } catch { /* optional */ }
  }

  const handleExtractMemory = async () => {
    if (!activeModel) { message.warning('请先选择 AI 模型'); return }
    if (messages.length === 0) { message.warning('当前没有可提炼的对话内容'); return }
    setExtracting(true)
    try {
      const existing = (memories.find((m) => m.name === memoryProject) && memView?.content) || ''
      const res = await aiAPI.extractMemory({
        model_id: activeModel,
        messages: messages.slice(-40).map((m) => ({ role: m.role, content: m.content })),
        project_name: memoryProject,
        existing_memory: existing,
      })
      const data: any = res.data?.data || res.data
      if (!data?.content) { message.warning('AI 未提炼出内容'); return }
      setMemDraft(data.content)
      message.success('已提炼对话要点，确认后写入记忆文件')
    } catch (err) {
      handleApiError(err, '提炼失败')
    } finally {
      setExtracting(false)
    }
  }

  const handleWriteMemory = async () => {
    if (!memDraft.trim()) { message.warning('没有可写入的内容，请先提炼或手动输入'); return }
    setMemSaving(true)
    try {
      await memoryAPI.write({
        name: memoryProject, content: memDraft, mode: 'append', title: 'AI 助手对话要点',
      })
      message.success(`已写入 Project_${memoryProject} Memory.md`)
      setMemDraft('')
      loadMemories()
      setMemView(null)
    } catch (err) {
      handleApiError(err, '写入记忆失败')
    } finally {
      setMemSaving(false)
    }
  }

  const handleReadMemory = async (name: string) => {
    try {
      const res = await memoryAPI.read(name)
      const data: any = extractData(res, {})
      setMemView({ name, content: data.content || '' })
    } catch (err) {
      handleApiError(err, '读取记忆失败')
    }
  }

  const handleDeleteMemory = (name: string) => {
    Modal.confirm({
      title: `删除记忆文件 Project_${name} Memory.md？`,
      content: '删除后无法恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await memoryAPI.remove(name)
          message.success('已删除')
          if (memView?.name === name) setMemView(null)
          loadMemories()
        } catch (err) {
          handleApiError(err, '删除失败')
        }
      },
    })
  }

  // --- Chat ---
  const handleChat = async () => {
    if ((!input.trim() && attachments.length === 0) || !activeModel) return
    const msg = input.trim()
    const files = attachmentPayload()
    addMessage({
      role: 'user',
      content: msg || '（仅附件）',
    })
    setInput('')
    setAttachments([])
    setChatLoading(true)
    try {
      const res = await aiAPI.chat({
        model_id: activeModel,
        message: msg,
        session_id: sessionId || undefined,
        input_type: 'text',
        skill_protocols: selectedSkills.filter((s) => !s.startsWith('__builtin_')),
        attachments: files,
      })
      const data: any = res.data?.data || res.data
      setSessionId(data?.session_id ?? '')
      addMessage({ role: 'assistant', content: data?.response ?? '（无响应内容）' })
    } catch (err) {
      const errMsg = _errorMessage(err, 'AI 请求失败')
      message.error(errMsg)
      addMessage({ role: 'assistant', content: `⚠️ 请求失败：${errMsg}` })
    } finally {
      setChatLoading(false)
    }
  }

  // --- Generate test cases ---
  const handleGenerateTestCases = async () => {
    if (!input.trim() || !activeModel) return
    const msg = input.trim()
    addMessage({ role: 'user', content: msg })
    setGenLoading(true)
    try {
      const res = await aiAPI.generateTestCases({
        requirements: msg,
        model_id: activeModel,
        input_type: 'text',
        skill_protocols: selectedSkills.filter((s) => !s.startsWith('__builtin_')),
        available_devices: devicePayload(),
      })
      const data: any = res.data?.data || res.data
      setTestCaseResult(data)
      setRefineLog([])
      if (data?.raw_response) {
        addMessage({ role: 'assistant', content: data.raw_response })
      }
      setActiveTab('result')
    } catch (err) {
      handleApiError(err, '生成测试用例失败')
      addMessage({ role: 'assistant', content: `⚠️ 生成测试用例失败：${_errorMessage(err, '生成测试用例失败')}` })
    } finally {
      setGenLoading(false)
    }
  }

  // --- Conversational refinement ---
  const handleRefine = async () => {
    const instruction = refineInput.trim()
    const cases = testCaseResult?.parsed?.test_cases || []
    if (!instruction || !activeModel) return
    if (cases.length === 0) { message.warning('没有可修改的测试用例，请先生成'); return }
    setRefining(true)
    try {
      const res = await aiAPI.refineTestCases({
        model_id: activeModel,
        test_cases: cases,
        instruction,
        available_devices: devicePayload(),
        skill_protocols: selectedSkills.filter((s) => !s.startsWith('__builtin_')),
        requirements: input || '',
      })
      const data: any = res.data?.data || res.data
      setTestCaseResult(data)
      setRefineLog((prev) => [...prev, instruction])
      setRefineInput('')
      addMessage({ role: 'user', content: `（修改用例）${instruction}` })
      if (data?.warning) message.warning(data.warning)
      else message.success('已按你的要求修改测试用例')
    } catch (err) {
      handleApiError(err, '修改测试用例失败')
    } finally {
      setRefining(false)
    }
  }

  const handleNaturalQuery = async () => {
    if (!input.trim() || !activeModel) return
    setQueryLoading(true)
    try {
      const res = await aiAPI.naturalLanguageQuery({ query: input, model_id: activeModel })
      const data: any = res.data?.data || res.data
      setQueryResult(data)
      setActiveTab('query')
    } catch (err) {
      handleApiError(err, '查询失败')
    } finally {
      setQueryLoading(false)
    }
  }

  const handleSaveOne = async (tc: any) => {
    setImportingIds((prev) => new Set(prev).add(tc.name))
    try {
      await testCaseAPI.importAiResult({
        test_cases: [tc],
        requirements: input || '',
        model_id: activeModel,
        available_devices: devicePayload(),
      })
      message.success(`「${tc.name}」已导入测试用例列表（含流程图）`)
    } catch {
      message.error(`「${tc.name}」导入失败`)
    } finally {
      setImportingIds((prev) => {
        const next = new Set(prev)
        next.delete(tc.name)
        return next
      })
    }
  }

  const handleImportAll = async () => {
    const cases = testCaseResult?.parsed?.test_cases || []
    if (cases.length === 0) { message.warning('没有可导入的测试用例'); return }
    setImportingAll(true)
    try {
      const res = await testCaseAPI.importAiResult({
        test_cases: cases,
        requirements: input || '',
        model_id: activeModel,
        available_devices: devicePayload(),
      })
      const data: any = res.data?.data || res.data
      const total = data.total_imported || data.saved_cases?.length || 0
      message.success(`已导入 ${total} 个测试用例（含流程图）`)
      if (total > 0) navigate('/testcases')
    } catch (err) {
      handleApiError(err, '批量导入失败')
    } finally {
      setImportingAll(false)
    }
  }

  const handleClear = () => {
    clearStore()
    setRefineLog([])
    setPreviewCase(null)
    setAttachments([])
  }

  const handleVoiceInput = () => {
    message.info('语音输入功能：请使用浏览器录音后上传')
  }

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
            options={models.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id }))}
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

      {/* ---------- 输出区（上方）：回复 / 结果 ---------- */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'chat',
            label: '对话',
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {messages.length === 0 ? (
                    <Empty description="开始与 AI 对话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  ) : (
                    messages.map((msg, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex', gap: 12,
                          padding: '12px 0', borderBottom: '1px solid #f0f0f0',
                        }}
                      >
                        <div>
                          {msg.role === 'assistant'
                            ? <RobotOutlined style={{ color: '#1677ff', fontSize: 20 }} />
                            : <UserOutlined style={{ color: '#52c41a', fontSize: 20 }} />}
                        </div>
                        <div style={{ flex: 1 }}>
                          <Text strong>{msg.role === 'assistant' ? 'AI' : '用户'}</Text>
                          <ReactMarkdown>{msg.content}</ReactMarkdown>
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={messagesEndRef} />
                </div>
              </Card>
            ),
          },
          {
            key: 'result',
            label: (
              <span>
                生成的测试用例
                {caseCount > 0 && <Tag color="blue" style={{ marginLeft: 6 }}>{caseCount}</Tag>}
              </span>
            ),
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {testCaseResult ? (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <Title level={5} style={{ margin: 0 }}>AI 生成结果</Title>
                        {caseCount > 0 && (
                          <Button
                            type="primary" icon={<ImportOutlined />}
                            onClick={handleImportAll} loading={importingAll}
                          >
                            一键添加全部 ({caseCount} 个)
                          </Button>
                        )}
                      </div>

                      {caseCount > 0 && (
                        <Card size="small" style={{ marginBottom: 12, background: '#fafcff' }}>
                          <Text strong style={{ display: 'block', marginBottom: 8 }}>
                            <EditOutlined /> 继续修改
                          </Text>
                          <TextArea
                            value={refineInput}
                            onChange={(e) => setRefineInput(e.target.value)}
                            placeholder="用自然语言描述修改意见，例如：把第 2 步的延时改成 500ms，最后增加一个读取版本号的步骤"
                            autoSize={{ minRows: 2, maxRows: 5 }}
                          />
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              AI 会返回修改后的完整用例集，确认无误后再一键添加
                            </Text>
                            <Button
                              icon={<CheckCircleOutlined />}
                              onClick={handleRefine} loading={refining}
                              disabled={!activeModel || !refineInput.trim()}
                            >
                              应用修改
                            </Button>
                          </div>
                          {refineLog.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>已应用的修改：</Text>
                              {refineLog.map((r, i) => (
                                <Tag key={i} color="green" style={{ marginTop: 4 }}>{i + 1}. {r}</Tag>
                              ))}
                            </div>
                          )}
                        </Card>
                      )}

                      {testCaseResult?.raw_response && (
                        <Collapse ghost style={{ marginBottom: 12 }} items={[{
                          key: 'raw',
                          label: <Text strong style={{ color: '#1677ff' }}>查看 AI 完整对话内容（原始响应）</Text>,
                          children: (
                            <div style={{
                              maxHeight: 400, overflow: 'auto', background: '#fafafa',
                              padding: 16, borderRadius: 8, whiteSpace: 'pre-wrap',
                              fontSize: 13, lineHeight: 1.7,
                            }}>
                              {testCaseResult.raw_response}
                            </div>
                          ),
                        }]} />
                      )}

                      {caseCount > 0 ? (
                        <List
                          dataSource={testCaseResult.parsed.test_cases}
                          renderItem={(tc: any) => (
                            <List.Item
                              actions={[
                                <Tag color="default" key="steps">{tc.steps?.length || 0} 步骤</Tag>,
                                <Tooltip title="预览用例详情" key="preview">
                                  <Button type="link" size="small" icon={<EyeOutlined />}
                                    onClick={() => setPreviewCase(tc)}>预览</Button>
                                </Tooltip>,
                                <Tooltip title="导入到测试用例列表" key="import">
                                  <Button type="link" size="small" icon={<ImportOutlined />}
                                    loading={importingIds.has(tc.name)}
                                    onClick={() => handleSaveOne(tc)}>添加</Button>
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
                          )}
                        />
                      ) : (
                        <Empty description="未能解析出测试用例" />
                      )}
                    </div>
                  ) : (
                    <Empty description="尚未生成测试用例。输入需求后点击「生成测试用例」" />
                  )}
                </div>
              </Card>
            ),
          },
          {
            key: 'memory',
            label: '项目记忆',
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  <Alert
                    type="info" showIcon style={{ marginBottom: 12 }}
                    message="把对话中确认的关键决策、约定与事实沉淀到 Project_<项目名> Memory.md"
                    description="先让 AI 从当前对话提炼要点，确认或修改后再写入文件。文件保存在 backend/memory/ 目录下，可直接提交到 Git。"
                  />
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>项目名：</Text>
                      <Input
                        value={memoryProject}
                        onChange={(e) => setMemoryProject(e.target.value)}
                        style={{ width: 240 }} placeholder="例如 AITestLab"
                      />
                      <Button icon={<BulbOutlined />} onClick={handleExtractMemory}
                        loading={extracting} disabled={!activeModel || messages.length === 0}>
                        从对话提炼要点
                      </Button>
                      <Button type="primary" icon={<SaveOutlined />} onClick={handleWriteMemory}
                        loading={memSaving} disabled={!memDraft.trim()}>
                        写入记忆文件
                      </Button>
                    </Space>

                    <TextArea
                      value={memDraft}
                      onChange={(e) => setMemDraft(e.target.value)}
                      placeholder="提炼结果会显示在这里，可手动修改后再写入"
                      autoSize={{ minRows: 6, maxRows: 16 }}
                    />

                    <Divider orientation="left" style={{ margin: '8px 0' }}>已有记忆文件</Divider>
                    {memories.length === 0 ? (
                      <Empty description="还没有记忆文件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ) : (
                      <List size="small" dataSource={memories} renderItem={(m: any) => (
                        <List.Item actions={[
                          <Button key="view" type="link" size="small" icon={<FileMarkdownOutlined />}
                            onClick={() => handleReadMemory(m.name)}>查看</Button>,
                          <Button key="del" type="link" size="small" danger icon={<DeleteOutlined />}
                            onClick={() => handleDeleteMemory(m.name)}>删除</Button>,
                        ]}>
                          <List.Item.Meta
                            title={<Space><Text strong>{m.name}</Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>{m.file_name}</Text></Space>}
                            description={<Text type="secondary" style={{ fontSize: 12 }}>
                              {m.section_count} 条记录 · {m.preview || '（无摘要）'}</Text>}
                          />
                        </List.Item>
                      )} />
                    )}

                    {memView && (
                      <>
                        <Divider orientation="left" style={{ margin: '8px 0' }}>{memView.name} 的内容</Divider>
                        <pre style={{
                          background: '#fafafa', padding: 16, borderRadius: 8,
                          maxHeight: 360, overflow: 'auto', fontSize: 12,
                        }}>
                          {memView.content}
                        </pre>
                      </>
                    )}
                  </Space>
                </div>
              </Card>
            ),
          },
          {
            key: 'query',
            label: '数据库查询结果',
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {queryResult ? (
                    <div>
                      <Title level={5}>查询结果</Title>
                      <Text type="secondary">SQL: {queryResult.sql_generated}</Text>
                      <p>共找到 {queryResult.result_count} 条记录</p>
                      {queryResult.results?.length > 0 && (
                        <pre style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, overflow: 'auto' }}>
                          {JSON.stringify(queryResult.results, null, 2)}
                        </pre>
                      )}
                    </div>
                  ) : (
                    <Empty description="尚未查询数据库" />
                  )}
                </div>
              </Card>
            ),
          },
        ]}
      />

      {/* ---------- 输入区（下方） ---------- */}
      <Card
        style={{ marginTop: 16, borderColor: dragging ? '#1677ff' : undefined }}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files)
        }}
      >
        {attachments.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <Space size={[8, 8]} wrap>
              {attachments.map((a) => (
                <span
                  key={a.uid}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 6,
                    padding: '4px 8px', border: '1px solid #d9d9d9',
                    borderRadius: 6, background: '#fafafa', fontSize: 12,
                  }}
                >
                  {a.kind === 'image' ? (
                    <Image
                      src={`data:${a.mime};base64,${a.data}`}
                      alt={a.name}
                      width={28} height={28}
                      style={{ objectFit: 'cover', borderRadius: 4 }}
                    />
                  ) : (
                    <FileOutlined style={{ color: '#8c8c8c' }} />
                  )}
                  <span style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {a.name}
                  </span>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {(a.size / 1024).toFixed(0)}KB
                  </Text>
                  <Button
                    type="text" size="small" icon={<DeleteOutlined />}
                    onClick={() => removeAttachment(a.uid)}
                  />
                </span>
              ))}
            </Space>
          </div>
        )}

        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入测试需求，或直接与 AI 对话…（可拖入文件/图片，或点击下方回形针）"
          autoSize={{ minRows: 3, maxRows: 6 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) { e.preventDefault(); handleChat() }
          }}
          disabled={!activeModel}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
          <Space>
            <Upload
              beforeUpload={(file) => { addFiles([file as any]); return false }}
              showUploadList={false}
              multiple
              accept="image/*,.txt,.md,.csv,.log,.json,.py,.yaml,.yml,.xml"
            >
              <Tooltip title="添加文件或图片（单个 ≤ 10MB）">
                <Button icon={<PaperClipOutlined />} disabled={!activeModel}>
                  附件{attachments.length > 0 ? ` (${attachments.length})` : ''}
                </Button>
              </Tooltip>
            </Upload>
            <Button icon={<AudioOutlined />} onClick={handleVoiceInput} disabled={!activeModel}>
              语音输入
            </Button>
            <Select
              mode="multiple" allowClear
              value={selectedSkills} onChange={setSelectedSkills}
              style={{ minWidth: 260 }} maxTagCount="responsive"
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
            <Button icon={<SearchOutlined />} onClick={handleNaturalQuery}
              disabled={!activeModel || !input.trim()} loading={queryLoading}>
              查询数据库
            </Button>
            <Button icon={<DiffOutlined />} onClick={handleGenerateTestCases}
              disabled={!activeModel || !input.trim()} loading={genLoading}>
              生成测试用例
            </Button>
            <Button type="primary" icon={<SendOutlined />} onClick={handleChat}
              disabled={!activeModel || (!input.trim() && attachments.length === 0)}
              loading={chatLoading}>
              发送
            </Button>
          </Space>
        </div>
        {attachments.some((a) => a.kind === 'image') && (
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
            提示：若当前模型不支持图片输入，系统会自动忽略图片并仅按文字内容回答。
          </Text>
        )}
      </Card>

      <TestCasePreviewModal
        open={!!previewCase}
        testCase={previewCase}
        onClose={() => setPreviewCase(null)}
        onImport={handleSaveOne}
        importing={!!previewCase && importingIds.has(previewCase.name)}
      />
    </div>
  )
}
