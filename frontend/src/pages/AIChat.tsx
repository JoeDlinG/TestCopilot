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
import { useI18n } from '../i18n'

const { Title, Text } = Typography
const { TextArea } = Input

// Virtual built-in "skills" that are always available (not from plugins).
// Checked by default so users immediately get test-case generation capability.
const BUILTIN_SKILLS = (tr: (k: string) => string) => [
  { name: tr('card.caseGeneration'), protocol: '__builtin_testgen', default: true },
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

const readFileAsBase64 = (file: File, t: (k: string) => string): Promise<string> =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error(t('msg.readFileFailed')))
    reader.readAsDataURL(file)
  })

export default function AIChat() {
  const { t } = useI18n()
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
        BUILTIN_SKILLS(t).filter((s) => s.default).map((s) => s.protocol),
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
        message.warning(`「${file.name}」${t('msg.over10mb')}`)
        continue
      }
      try {
        const dataUrl = await readFileAsBase64(file, t)
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
        message.error(`${t('msg.readingPrefix')}${file.name}」${t('status.failed')}`)
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
    if (!activeModel) { message.warning(t('msg.pickModelFirst')); return }
    if (messages.length === 0) { message.warning(t('msg.noConversation')); return }
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
      if (!data?.content) { message.warning(`AI ${t('msg.nothingExtracted')}`); return }
      setMemDraft(data.content)
      message.success(t('msg.memoryExtracted'))
    } catch (err) {
      handleApiError(err, t('msg.extractFailed'))
    } finally {
      setExtracting(false)
    }
  }

  const handleWriteMemory = async () => {
    if (!memDraft.trim()) { message.warning(t('msg.nothingToWrite')); return }
    setMemSaving(true)
    try {
      await memoryAPI.write({
        name: memoryProject, content: memDraft, mode: 'append', title: `AI ${t('card.assistantPoints')}`,
      })
      message.success(`${t('msg.memoryWritten')}_${memoryProject} Memory.md`)
      setMemDraft('')
      loadMemories()
      setMemView(null)
    } catch (err) {
      handleApiError(err, t('msg.writeMemoryFailed'))
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
      handleApiError(err, t('msg.readMemoryFailed'))
    }
  }

  const handleDeleteMemory = (name: string) => {
    Modal.confirm({
      title: `${t('msg.deleteMemoryPrefix')}_${name} Memory.md？`,
      content: t('msg.deleteIrreversible'),
      okText: t('common.delete'),
      okButtonProps: { danger: true },
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await memoryAPI.remove(name)
          message.success(t('msg.deleted'))
          if (memView?.name === name) setMemView(null)
          loadMemories()
        } catch (err) {
          handleApiError(err, t('msg.deleteFailed'))
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
      content: msg || `（${t('label.attachmentOnly')}`,
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
      addMessage({ role: 'assistant', content: data?.response ?? t('msg.noResponse') })
    } catch (err) {
      const errMsg = _errorMessage(err, `AI ${t('msg.requestFailed')}`)
      message.error(errMsg)
      addMessage({ role: 'assistant', content: `⚠️ ${t('msg.requestFailedColon')}${errMsg}` })
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
      handleApiError(err, t('msg.generateFailed'))
      addMessage({ role: 'assistant', content: `⚠️ ${t('msg.genFailedColon')}${_errorMessage(err, t('msg.generateFailed'))}` })
    } finally {
      setGenLoading(false)
    }
  }

  // --- Conversational refinement ---
  const handleRefine = async () => {
    const instruction = refineInput.trim()
    const cases = testCaseResult?.parsed?.test_cases || []
    if (!instruction || !activeModel) return
    if (cases.length === 0) { message.warning(t('msg.nothingToRefine')); return }
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
      addMessage({ role: 'user', content: `${t('label.refineSuffix')}${instruction}` })
      if (data?.warning) message.warning(data.warning)
      else message.success(t('msg.casesRefined'))
    } catch (err) {
      handleApiError(err, t('msg.refineFailed'))
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
      handleApiError(err, t('msg.queryFailed'))
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
      message.success(`「${tc.name}」${t('msg.casesImported')}`)
    } catch {
      message.error(`「${tc.name}」${t('msg.importFailed')}`)
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
    if (cases.length === 0) { message.warning(t('msg.nothingToImport')); return }
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
      message.success(`${t('msg.imported')} ${total} ${t('unit.casesWithFlows')}`)
      if (total > 0) navigate('/testcases')
    } catch (err) {
      handleApiError(err, t('msg.bulkImportFailed'))
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
    message.info(t('msg.voiceHint'))
  }

  const allSkills = [
    ...BUILTIN_SKILLS(t).map((s) => ({ name: s.name, protocol: s.protocol, builtin: true })),
    ...pluginSkills.map((s: any) => ({ name: s.name, protocol: s.protocol, builtin: false })),
  ]

  const caseCount = testCaseResult?.parsed?.test_cases?.length || 0

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>AI {t('label.assistant')}</Title>
        <Space>
          <Select
            placeholder={t('ph.pickModel')}
            value={activeModel || undefined}
            onChange={setActiveModel}
            style={{ width: 280 }}
            options={models.map((m) => ({ label: `${m.name} (${m.provider})`, value: m.id }))}
            notFoundContent={
              <Empty description={t('msg.noModelYet')} image={Empty.PRESENTED_IMAGE_SIMPLE}>
                <Button type="primary" size="small" onClick={() => navigate('/model-config')}>{t('btn.goConfigureModel')}</Button>
              </Empty>
            }
          />
          <Button icon={<ClearOutlined />} onClick={handleClear}>{t('btn.clearChat')}</Button>
        </Space>
      </div>

          {/* ---------- output area (top): reply / result ---------- */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'chat',
            label: t('tab.chat'),
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {messages.length === 0 ? (
                    <Empty description={t('btn.startChat')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  ) : (
                    messages.map((msg, i) => (
                      <div
                        key={i}
                        style={{
                          display: 'flex', gap: 12,
                          padding: '12px 0', borderBottom: '1px solid var(--app-border)',
                        }}
                      >
                        <div>
                          {msg.role === 'assistant'
                            ? <RobotOutlined style={{ color: 'var(--app-accent)', fontSize: 20 }} />
                            : <UserOutlined style={{ color: 'var(--app-pass)', fontSize: 20 }} />}
                        </div>
                        <div style={{ flex: 1 }}>
                          <Text strong>{msg.role === 'assistant' ? 'AI' : t('label.user')}</Text>
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
                {t('tab.generatedCases')}
                {caseCount > 0 && <Tag color="blue" style={{ marginLeft: 6 }}>{caseCount}</Tag>}
              </span>
            ),
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {testCaseResult ? (
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <Title level={5} style={{ margin: 0 }}>{t('card.aiResult')}</Title>
                        {caseCount > 0 && (
                          <Button
                            type="primary" icon={<ImportOutlined />}
                            onClick={handleImportAll} loading={importingAll}
                          >
                            t('btn.addAllPrefix'){caseCount} {t('label.itemsParen')}
                          </Button>
                        )}
                      </div>

                      {caseCount > 0 && (
                        <Card size="small" style={{ marginBottom: 12, background: 'var(--app-accent-subtle)' }}>
                          <Text strong style={{ display: 'block', marginBottom: 8 }}>
                            <EditOutlined />{t('label.keepRefining')}</Text>
                          <TextArea
                            value={refineInput}
                            onChange={(e) => setRefineInput(e.target.value)}
                            placeholder={t('ph.refineInstruction')}
                            autoSize={{ minRows: 2, maxRows: 5 }}
                          />
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              AI {t('tip.refineResult')}
                            </Text>
                            <Button
                              icon={<CheckCircleOutlined />}
                              onClick={handleRefine} loading={refining}
                              disabled={!activeModel || !refineInput.trim()}
                            >{t('btn.applyChanges')}</Button>
                          </div>
                          {refineLog.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>{t('label.appliedChanges')}</Text>
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
                          label: <Text strong style={{ color: 'var(--app-accent)' }}>{t('btn.viewRawReply')}</Text>,
                          children: (
                            <div style={{
                              maxHeight: 400, overflow: 'auto', background: 'var(--app-surface-muted)',
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
                                <Tag color="default" key="steps">{tc.steps?.length || 0} {t('col.steps')}</Tag>,
                                <Tooltip title={t('btn.previewCase')} key="preview">
                                  <Button type="link" size="small" icon={<EyeOutlined />}
                                    onClick={() => setPreviewCase(tc)}>{t('btn.preview')}</Button>
                                </Tooltip>,
                                <Tooltip title={t('btn.importToList')} key="import">
                                  <Button type="link" size="small" icon={<ImportOutlined />}
                                    loading={importingIds.has(tc.name)}
                                    onClick={() => handleSaveOne(tc)}>{t('common.add')}</Button>
                                </Tooltip>,
                              ]}
                            >
                              <List.Item.Meta
                                title={tc.name}
                                description={
                                  <Text type="secondary" ellipsis style={{ maxWidth: 400 }}>
                                    {tc.description || `（${t('label.noDesc')}`}
                                  </Text>
                                }
                              />
                            </List.Item>
                          )}
                        />
                      ) : (
                        <Empty description={t('msg.parseCasesFailed')} />
                      )}
                    </div>
                  ) : (
                    <Empty description={t('msg.noCasesGenerated')} />
                  )}
                </div>
              </Card>
            ),
          },
          {
            key: 'memory',
            label: t('tab.memory'),
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  <Alert
                    type="info" showIcon style={{ marginBottom: 12 }}
                    message={t('memory.purposeFull')}
                    description={t('memory.howto')}
                  />
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    <Space wrap>
                      <Text strong>{t('label.projectNameColon')}</Text>
                      <Input
                        value={memoryProject}
                        onChange={(e) => setMemoryProject(e.target.value)}
                        style={{ width: 240 }} placeholder={t('ph.projectExample')}
                      />
                      <Button icon={<BulbOutlined />} onClick={handleExtractMemory}
                        loading={extracting} disabled={!activeModel || messages.length === 0}>{t('btn.extractMemory')}</Button>
                      <Button type="primary" icon={<SaveOutlined />} onClick={handleWriteMemory}
                        loading={memSaving} disabled={!memDraft.trim()}>{t('btn.writeMemory')}</Button>
                    </Space>

                    <TextArea
                      value={memDraft}
                      onChange={(e) => setMemDraft(e.target.value)}
                      placeholder={t('ph.memoryDraft')}
                      autoSize={{ minRows: 6, maxRows: 16 }}
                    />

                    <Divider orientation="left" style={{ margin: '8px 0' }}>{t('card.existingMemory')}</Divider>
                    {memories.length === 0 ? (
                      <Empty description={t('msg.noMemoryFiles')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ) : (
                      <List size="small" dataSource={memories} renderItem={(m: any) => (
                        <List.Item actions={[
                          <Button key="view" type="link" size="small" icon={<FileMarkdownOutlined />}
                            onClick={() => handleReadMemory(m.name)}>{t('btn.view')}</Button>,
                          <Button key="del" type="link" size="small" danger icon={<DeleteOutlined />}
                            onClick={() => handleDeleteMemory(m.name)}>{t('common.delete')}</Button>,
                        ]}>
                          <List.Item.Meta
                            title={<Space><Text strong>{m.name}</Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>{m.file_name}</Text></Space>}
                            description={<Text type="secondary" style={{ fontSize: 12 }}>
                              {m.section_count} t('unit.recordsDot') {m.preview || `（${t('label.noSummary')}`}</Text>}
                          />
                        </List.Item>
                      )} />
                    )}

                    {memView && (
                      <>
                        <Divider orientation="left" style={{ margin: '8px 0' }}>{memView.name} {t('label.contentSuffix')}</Divider>
                        <pre style={{
                          background: 'var(--app-surface-muted)', padding: 16, borderRadius: 8,
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
            label: t('card.queryResult'),
            children: (
              <Card>
                <div style={OUTPUT_STYLE}>
                  {queryResult ? (
                    <div>
                      <Title level={5}>{t('card.queryResult')}</Title>
                      <Text type="secondary">SQL: {queryResult.sql_generated}</Text>
                      <p>t('label.foundTotal') {queryResult.result_count} {t('unit.records')}</p>
                      {queryResult.results?.length > 0 && (
                        <pre style={{ background: 'var(--app-surface-sunken)', padding: 16, borderRadius: 8, overflow: 'auto' }}>
                          {JSON.stringify(queryResult.results, null, 2)}
                        </pre>
                      )}
                    </div>
                  ) : (
                    <Empty description={t('msg.notQueried')} />
                  )}
                </div>
              </Card>
            ),
          },
        ]}
      />

        {/* ---------- input area (bottom) ---------- */}
      <Card
        style={{ marginTop: 16, borderColor: dragging ? 'var(--app-accent)' : undefined }}
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
                    padding: '4px 8px', border: '1px solid var(--app-border)',
                    borderRadius: 6, background: 'var(--app-surface-muted)', fontSize: 12,
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
                    <FileOutlined style={{ color: 'var(--app-fg-subtle)' }} />
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
          placeholder={t('ph.chatInput')}
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
              <Tooltip title={t('btn.attachFull')}>
                <Button icon={<PaperClipOutlined />} disabled={!activeModel}>
                  t('label.attachment'){attachments.length > 0 ? ` (${attachments.length})` : ''}
                </Button>
              </Tooltip>
            </Upload>
            <Button icon={<AudioOutlined />} onClick={handleVoiceInput} disabled={!activeModel}>{t('btn.voiceInput')}</Button>
            <Select
              mode="multiple" allowClear
              value={selectedSkills} onChange={setSelectedSkills}
              style={{ minWidth: 260 }} maxTagCount="responsive"
              placeholder={<span><ApiOutlined />{t('btn.importSkillKb')}</span>}
              options={allSkills.map((s) => ({
                label: s.builtin ? `⚡ ${s.name}（${t('label.builtin')}` : `${s.name} (${s.protocol})`,
                value: s.protocol,
              }))}
            />
            {selectedSkills.length > 0 && (
              <Tag color="blue">t('status.enabled') {selectedSkills.length} {t('unit.skills')}</Tag>
            )}
          </Space>
          <Space>
            <Button icon={<SearchOutlined />} onClick={handleNaturalQuery}
              disabled={!activeModel || !input.trim()} loading={queryLoading}>{t('btn.queryDb')}</Button>
            <Button icon={<DiffOutlined />} onClick={handleGenerateTestCases}
              disabled={!activeModel || !input.trim()} loading={genLoading}>{t('btn.generateCases')}</Button>
            <Button type="primary" icon={<SendOutlined />} onClick={handleChat}
              disabled={!activeModel || (!input.trim() && attachments.length === 0)}
              loading={chatLoading}>{t('btn.send')}</Button>
          </Space>
        </div>
        {attachments.some((a) => a.kind === 'image') && (
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>{t('tip.imageUnsupported')}</Text>
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
