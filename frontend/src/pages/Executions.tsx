import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Empty, Statistic,
  Row, Col, Drawer, Descriptions, Select, List, Alert, Tooltip
} from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, CheckCircleOutlined,
  CloseCircleOutlined, SyncOutlined, ReloadOutlined, ExclamationCircleOutlined,
  EyeOutlined, ClearOutlined, ApiOutlined, OrderedListOutlined,
  ArrowDownOutlined, ArrowUpOutlined, MinusCircleOutlined, AimOutlined
} from '@ant-design/icons'
import { executionAPI, deviceAPI, testCaseAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import type { TestExecution } from '../types'

const { Title, Text } = Typography

const MAX_LINES = 500

type ComLine = {
  id: number
  ts: string
  dir: 'TX' | 'RX' | 'SYS'
  text: string
}

let lineSeq = 0

function nowTs(): string {
  const d = new Date()
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

function formatPayload(data: any): string {
  if (data === null || data === undefined) return ''
  if (typeof data === 'string') return data
  if (typeof data === 'object') {
    // CAN frames arrive as objects - show id + data in a compact form
    const id = data.id ?? data.can_id ?? data.arbitration_id
    const payload = data.data ?? data.payload ?? data.hex
    if (id !== undefined && payload !== undefined) {
      const body = Array.isArray(payload)
        ? payload.map((b: any) => (typeof b === 'number' ? b.toString(16).padStart(2, '0') : b)).join(' ')
        : String(payload)
      return `ID=${id} DATA=${body}`
    }
    return JSON.stringify(data)
  }
  return String(data)
}

function wsBase(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname || 'localhost'
  return `${protocol}//${host}:8000`
}

/** parsed_results may arrive as a JSON string (DB) or an array (WebSocket) */
function normalizeParsed(v: any): any[] {
  if (!v) return []
  if (Array.isArray(v)) return v
  try {
    const parsed = JSON.parse(v)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export default function Executions() {
  const [executions, setExecutions] = useState<TestExecution[]>([])
  const [loading, setLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  // ---- live communication monitor ----
  const [devices, setDevices] = useState<any[]>([])
  const [selectedDevice, setSelectedDevice] = useState<string>('')
  const [comLines, setComLines] = useState<ComLine[]>([])
  const [comPaused, setComPaused] = useState(false)
  const [wsState, setWsState] = useState<'connecting' | 'open' | 'closed'>('closed')
  const pausedRef = useRef(false)
  const bufferRef = useRef<ComLine[]>([])
  const comEndRef = useRef<HTMLDivElement | null>(null)

  // ---- live step status ----
  const [trackedId, setTrackedId] = useState<string>('')
  const [trackedInfo, setTrackedInfo] = useState<any>(null)
  const [execSteps, setExecSteps] = useState<any[]>([])
  // all steps of the flow, so the window shows the whole plan while running
  const [flowSteps, setFlowSteps] = useState<any[]>([])

  const handleViewDetail = async (id: string) => {
    try {
      const res = await executionAPI.get(id)
      setDetail(res.data?.data ?? res.data)
      setDetailOpen(true)
    } catch (err) {
      handleApiError(err, '加载执行详情失败')
    }
  }

  const loadExecutions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await executionAPI.list()
      setExecutions(extractItems(res))
    } catch (err) {
      handleApiError(err, '加载执行记录失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadExecutions() }, [loadExecutions])

  const handleStop = async (id: string) => {
    try {
      await executionAPI.stop(id)
      message.success('已停止执行')
      loadExecutions()
    } catch (err) {
      handleApiError(err, '停止失败')
    }
  }

  const statusConfig: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
    pending: { color: 'default', icon: <SyncOutlined />, text: '等待中' },
    running: { color: 'processing', icon: <SyncOutlined spin />, text: '运行中' },
    passed: { color: 'success', icon: <CheckCircleOutlined />, text: '通过' },
    failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
    error: { color: 'warning', icon: <ExclamationCircleOutlined />, text: '异常' },
    stopped: { color: 'default', icon: <PauseCircleOutlined />, text: '已停止' },
  }

  const stepStatusConfig: Record<string, { color: string; text: string }> = {
    pending: { color: 'default', text: '等待' },
    running: { color: 'processing', text: '执行中' },
    passed: { color: 'success', text: '通过' },
    failed: { color: 'error', text: '失败' },
    error: { color: 'warning', text: '异常' },
    skipped: { color: 'default', text: '跳过' },
  }

  const stats = {
    total: executions.length,
    passed: executions.filter(e => e.status === 'passed').length,
    failed: executions.filter(e => e.status === 'failed').length,
    running: executions.filter(e => e.status === 'running').length,
    passRate: executions.length > 0
      ? Math.round((executions.filter(e => e.status === 'passed').length / executions.length) * 100)
      : 0,
  }

  // ------------------------------------------------------------------ //
  // Live communication monitor
  // ------------------------------------------------------------------ //

  // load devices once, default to a connected one
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await deviceAPI.list()
        const items = extractItems(res)
        if (cancelled) return
        setDevices(items)
        const preferred = items.find((d: any) => d.status === 'connected') || items[0]
        if (preferred) setSelectedDevice(prev => prev || preferred.id)
      } catch {
        /* device list is optional for this page */
      }
    })()
    return () => { cancelled = true }
  }, [])

  const pushLine = useCallback((dir: ComLine['dir'], text: string) => {
    const line: ComLine = { id: ++lineSeq, ts: nowTs(), dir, text }
    if (pausedRef.current) {
      // keep collecting while paused so nothing is lost when resuming
      bufferRef.current.push(line)
      if (bufferRef.current.length > MAX_LINES) {
        bufferRef.current = bufferRef.current.slice(-MAX_LINES)
      }
      return
    }
    setComLines(prev => [...prev, line].slice(-MAX_LINES))
  }, [])

  useEffect(() => { pausedRef.current = comPaused }, [comPaused])

  // device websocket
  useEffect(() => {
    if (!selectedDevice) return
    const ws = new WebSocket(`${wsBase()}/ws/devices/${selectedDevice}`)
    setWsState('connecting')

    ws.onopen = () => {
      setWsState('open')
      pushLine('SYS', `已连接设备 ${selectedDevice}`)
    }
    ws.onclose = () => setWsState('closed')
    ws.onerror = () => setWsState('closed')
    ws.onmessage = (ev) => {
      let msg: any
      try { msg = JSON.parse(ev.data) } catch { return }
      switch (msg.type) {
        case 'command_sent':
          pushLine('TX', String(msg.command ?? ''))
          break
        case 'command_response':
          pushLine('RX', formatPayload(msg.response))
          break
        case 'device_data':
          pushLine('RX', formatPayload(msg.data))
          break
        case 'command_error':
          pushLine('SYS', `[错误] ${msg.error ?? ''}`)
          break
        case 'connected':
          pushLine('SYS', String(msg.message ?? '已连接'))
          break
        case 'error':
          pushLine('SYS', String(msg.message ?? ''))
          break
        default:
          break
      }
    }
    return () => { ws.close() }
  }, [selectedDevice, pushLine])

  // auto-scroll to newest line
  useEffect(() => {
    comEndRef.current?.scrollIntoView({ block: 'end' })
  }, [comLines])

  const togglePause = () => {
    if (comPaused) {
      // flush everything collected while paused
      const buffered = bufferRef.current
      bufferRef.current = []
      setComLines(prev => [...prev, ...buffered].slice(-MAX_LINES))
      setComPaused(false)
    } else {
      setComPaused(true)
    }
  }

  const clearCom = () => {
    bufferRef.current = []
    setComLines([])
  }

  // ------------------------------------------------------------------ //
  // Live execution step status
  // ------------------------------------------------------------------ //

  const upsertStep = useCallback((index: number, patch: any) => {
    setExecSteps(prev => {
      const i = prev.findIndex(s => Number(s.step_index) === Number(index))
      if (i >= 0) {
        const next = [...prev]
        next[i] = { ...next[i], ...patch }
        return next
      }
      return [...prev, { step_index: index, label: patch.label ?? `步骤 ${index}`, ...patch }]
        .sort((a, b) => Number(a.step_index) - Number(b.step_index))
    })
  }, [])

  // follow the newest execution, and switch to a running one as soon as
  // it appears so the step window always shows the live run
  useEffect(() => {
    if (!executions.length) return
    const running = executions.find(e => e.status === 'running')
    const known = executions.some(e => e.id === trackedId)
    if (running) {
      if (trackedId !== running.id) setTrackedId(running.id)
    } else if (!known) {
      setTrackedId(executions[0].id)
    }
  }, [executions, trackedId])

  // load step results + subscribe to live updates for the tracked execution
  useEffect(() => {
    if (!trackedId) return
    let cancelled = false

    const loadDetail = async () => {
      try {
        const res = await executionAPI.get(trackedId)
        const d = res.data?.data ?? res.data
        if (cancelled) return
        setTrackedInfo(d)
        if (Array.isArray(d?.step_results) && d.step_results.length) {
          setExecSteps(
            d.step_results.slice().sort(
              (a: any, b: any) => Number(a.step_index) - Number(b.step_index)
            )
          )
        } else if (d?.status !== 'running') {
          setExecSteps([])
        }
      } catch {
        /* ignore transient failures */
      }
    }
    loadDetail()

    const ws = new WebSocket(`${wsBase()}/ws/executions/${trackedId}`)
    ws.onmessage = (ev) => {
      let msg: any
      try { msg = JSON.parse(ev.data) } catch { return }
      if (msg.type === 'step_started') {
        upsertStep(msg.step_index, { status: 'running', label: msg.label })
      } else if (msg.type === 'step_completed') {
        upsertStep(msg.step_index, { status: msg.status })
      } else if (msg.type === 'step_failed') {
        upsertStep(msg.step_index, { status: 'failed', error_message: msg.error })
      } else if (msg.type === 'execution_completed') {
        loadDetail()
        loadExecutions()
      }
    }
    return () => { cancelled = true; ws.close() }
  }, [trackedId, upsertStep, loadExecutions])

  // load the flow so every step is listed up front, not only the finished ones
  useEffect(() => {
    const tcId = trackedInfo?.testcase_id
    if (!tcId) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await testCaseAPI.getFlow(tcId)
        const data: any = res.data?.data ?? res.data
        const nodes: any[] = data?.nodes || []
        if (cancelled) return
        setFlowSteps(
          nodes
            .filter(n => n.type !== 'start' && n.type !== 'end')
            .map(n => ({
              id: n.id,
              label: n?.data?.label || n?.label || '',
              command: n?.config?.command || '',
              hasParsers: (n?.config?.parsers || []).length > 0,
            }))
        )
      } catch {
        if (!cancelled) setFlowSteps([])
      }
    })()
    return () => { cancelled = true }
  }, [trackedInfo?.testcase_id])

  // poll the list while something is running
  useEffect(() => {
    if (!executions.some(e => e.status === 'running')) return
    const timer = setInterval(loadExecutions, 2000)
    return () => clearInterval(timer)
  }, [executions, loadExecutions])

  // Merge the planned flow with live results so the whole step list is visible
  // while running, each step showing its judgement outcome once finished.
  const mergedSteps: any[] = flowSteps.length
    ? flowSteps.map((f: any, i: number) => {
        const r = execSteps.find(s => Number(s.step_index) === i + 1)
        return {
          step_index: i + 1,
          label: f.label || `步骤 ${i + 1}`,
          status: r?.status || 'pending',
          duration_ms: r?.duration_ms,
          parsed: normalizeParsed(r?.parsed_results),
          actual: r?.actual,
        }
      })
    : execSteps.map((s: any) => ({ ...s, parsed: normalizeParsed(s.parsed_results) }))

  const currentStep = mergedSteps.find(s => s.status === 'running')
  const trackedExec = executions.find(e => e.id === trackedId)

  const columns = [
    {
      title: '执行 ID',
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => id.slice(0, 8) + '...',
    },
    {
      title: '测试用例 ID',
      dataIndex: 'testcase_id',
      key: 'testcase_id',
      render: (id: string) => id?.slice(0, 8) + '...' || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const config = statusConfig[status] || statusConfig.pending
        return (
          <Tag color={config.color} icon={config.icon}>
            {config.text}
          </Tag>
        )
      },
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '结束时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '耗时 (ms)',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      render: (v: number) => v ?? '-',
    },
    {
      title: '结果详情',
      dataIndex: 'results',
      key: 'results',
      render: (results: any[]) => {
        if (!results?.length) return '-'
        return `${results.filter((r: any) => r.status === 'passed').length}/${results.length} 通过`
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: TestExecution) => (
        <Space>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record.id)}
          >
            详情
          </Button>
          <Tooltip title="在下方步骤状态窗口中实时跟踪该执行">
            <Button
              size="small"
              type={trackedId === record.id ? 'primary' : 'default'}
              icon={<AimOutlined />}
              onClick={() => setTrackedId(record.id)}
            >
              跟踪
            </Button>
          </Tooltip>
          {record.status === 'running' && (
            <Button
              size="small"
              danger
              icon={<PauseCircleOutlined />}
              onClick={() => handleStop(record.id)}
            >
              停止
            </Button>
          )}
        </Space>
      ),
    },
  ]

  const lineColor = (dir: ComLine['dir']) =>
    dir === 'TX' ? '#95de64' : dir === 'RX' ? '#d3d3d3' : '#faad14'

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>测试执行</Title>
        <Button icon={<ReloadOutlined />} onClick={loadExecutions}>刷新</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="总执行次数" value={stats.total} prefix={<PlayCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="通过"
              value={stats.passed}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="失败"
              value={stats.failed}
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="通过率"
              value={stats.passRate}
              suffix="%"
              valueStyle={{ color: stats.passRate >= 80 ? '#52c41a' : '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {/* ---------- live communication monitor ---------- */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <ApiOutlined />
                <span>实时通信监控</span>
                <Tag color={wsState === 'open' ? 'green' : wsState === 'connecting' ? 'gold' : 'red'}>
                  {wsState === 'open' ? '已连接' : wsState === 'connecting' ? '连接中' : '未连接'}
                </Tag>
                {comPaused && <Tag color="orange">已暂停</Tag>}
              </Space>
            }
            extra={
              <Space>
                <Select
                  size="small"
                  style={{ width: 190 }}
                  placeholder="选择设备"
                  value={selectedDevice || undefined}
                  onChange={(v) => { setSelectedDevice(v); setComLines([]) }}
                  options={devices.map((d: any) => ({
                    value: d.id,
                    label: `${d.name} (${d.protocol})`,
                  }))}
                />
                <Button
                  size="small"
                  icon={comPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
                  onClick={togglePause}
                >
                  {comPaused ? '继续' : '暂停'}
                </Button>
                <Button size="small" icon={<ClearOutlined />} onClick={clearCom}>
                  清空
                </Button>
              </Space>
            }
          >
            <div
              style={{
                height: 320,
                overflowY: 'auto',
                background: '#1e1e1e',
                borderRadius: 4,
                padding: 8,
                fontFamily: 'Menlo, Consolas, monospace',
                fontSize: 12,
              }}
            >
              {comLines.length === 0 ? (
                <div style={{ color: '#888', padding: 8 }}>
                  等待端口通信数据…（下发命令或设备主动上报时会实时显示）
                </div>
              ) : (
                comLines.map(line => (
                  <div key={line.id} style={{ color: lineColor(line.dir), lineHeight: 1.7 }}>
                    <span style={{ color: '#666' }}>{line.ts}</span>{' '}
                    <span style={{ fontWeight: 'bold' }}>
                      {line.dir === 'TX'
                        ? <ArrowUpOutlined />
                        : line.dir === 'RX'
                          ? <ArrowDownOutlined />
                          : <MinusCircleOutlined />}
                      {` ${line.dir}`}
                    </span>{' '}
                    {line.text}
                  </div>
                ))
              )}
              <div ref={comEndRef} />
            </div>
            <div style={{ marginTop: 6, color: '#888', fontSize: 12 }}>
              共 {comLines.length} 行（最多保留 {MAX_LINES} 行）
              {comPaused && ` · 暂停期间已缓存 ${bufferRef.current.length} 行`}
            </div>
          </Card>
        </Col>

        {/* ---------- live step status ---------- */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <Space>
                <OrderedListOutlined />
                <span>执行步骤状态</span>
                {trackedExec && (
                  <Tag color={(statusConfig[trackedExec.status] || statusConfig.pending).color}>
                    {(statusConfig[trackedExec.status] || statusConfig.pending).text}
                  </Tag>
                )}
              </Space>
            }
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                {trackedId ? `跟踪: ${trackedId.slice(0, 8)}…` : '未选择执行'}
              </Text>
            }
          >
            {currentStep ? (
              <Alert
                type="info"
                showIcon
                icon={<SyncOutlined spin />}
                style={{ marginBottom: 8 }}
                message={`正在执行第 ${currentStep.step_index} 步`}
                description={currentStep.label}
              />
            ) : (
              <div style={{ marginBottom: 8 }}>
                {trackedInfo ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    共 {trackedInfo.total_steps ?? 0} 步 ·
                    通过 {trackedInfo.passed_steps ?? 0} ·
                    失败 {trackedInfo.failed_steps ?? 0}
                  </Text>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    选择一次执行以查看步骤进度
                  </Text>
                )}
              </div>
            )}

            <div style={{ height: 288, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 4 }}>
              {mergedSteps.length === 0 ? (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="暂无步骤（执行开始后将实时显示）"
                  style={{ marginTop: 60 }}
                />
              ) : (
                <List
                  size="small"
                  dataSource={mergedSteps}
                  renderItem={(s: any) => {
                    const cfg = stepStatusConfig[s.status] || stepStatusConfig.pending
                    const running = s.status === 'running'
                    return (
                      <List.Item
                        style={{
                          background: running ? '#e6f4ff' : undefined,
                          padding: '6px 12px',
                          flexDirection: 'column',
                          alignItems: 'stretch',
                        }}
                      >
                        <Space size={8} style={{ width: '100%' }}>
                          <Tag color={cfg.color} style={{ marginInlineEnd: 0 }}>
                            {s.step_index}
                          </Tag>
                          <span style={{ flex: 1, wordBreak: 'break-all' }}>
                            {s.label || `步骤 ${s.step_index}`}
                          </span>
                          <Tag color={cfg.color} style={{ marginInlineEnd: 0 }}>
                            {cfg.text}
                          </Tag>
                          {s.duration_ms != null && (
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {s.duration_ms}ms
                            </Text>
                          )}
                        </Space>

                        {/* parsed values + judgement (result parsing config) */}
                        {s.parsed && s.parsed.length > 0 && (
                          <div style={{ marginTop: 4, paddingLeft: 28 }}>
                            {s.parsed.map((p: any, i: number) => (
                              <Tooltip key={i} title={p.detail || ''}>
                                <Tag
                                  color={p.ok ? 'green' : 'red'}
                                  style={{ marginBottom: 2, fontSize: 11 }}
                                >
                                  {p.name}={p.value === null || p.value === undefined
                                    ? '解析失败'
                                    : String(p.value)}
                                  {' '}
                                  {p.ok ? '✓' : '✗'}
                                </Tag>
                              </Tooltip>
                            ))}
                          </div>
                        )}
                      </List.Item>
                    )
                  }}
                />
              )}
            </div>
          </Card>
        </Col>
      </Row>

      <Card>
        <Table
          columns={columns}
          dataSource={executions}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: <Empty description="暂无执行记录" /> }}
        />
      </Card>

      <Drawer
        title="执行详情 — 每步真实收发"
        width={860}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      >
        {detail && (
          <>
            <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="执行 ID">{detail.id}</Descriptions.Item>
              <Descriptions.Item label="状态">{detail.status}</Descriptions.Item>
              <Descriptions.Item label="步骤">{detail.total_steps}</Descriptions.Item>
              <Descriptions.Item label="通过 / 失败">
                {detail.passed_steps} / {detail.failed_steps}
              </Descriptions.Item>
            </Descriptions>

            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={(detail.step_results || []).slice().sort(
                (a: any, b: any) => Number(a.step_index) - Number(b.step_index)
              )}
              columns={[
                { title: '#', dataIndex: 'step_index', width: 50 },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (s: string) => (
                    <Tag color={s === 'passed' ? 'green' : s === 'failed' ? 'red' : 'default'}>
                      {s}
                    </Tag>
                  ),
                },
                { title: '耗时', dataIndex: 'duration_ms', width: 70 },
                {
                  title: '下发指令', dataIndex: 'command',
                  render: (c: string) => (
                    <Text code style={{ fontSize: 11, wordBreak: 'break-all' }}>{c || '-'}</Text>
                  ),
                },
                {
                  title: '设备实际响应', dataIndex: 'actual',
                  render: (a: string) => (
                    <Text style={{ fontSize: 11, wordBreak: 'break-all' }}>{a || '-'}</Text>
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </div>
  )
}
