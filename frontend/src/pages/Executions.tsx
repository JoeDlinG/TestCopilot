import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Empty, Statistic,
  Row, Col, Drawer, Descriptions, Select, List, Alert, Tooltip,
  Checkbox, Modal, Spin
} from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, CheckCircleOutlined,
  CloseCircleOutlined, SyncOutlined, ReloadOutlined, ExclamationCircleOutlined,
  EyeOutlined, ClearOutlined, ApiOutlined, OrderedListOutlined,
  ArrowDownOutlined, ArrowUpOutlined, MinusCircleOutlined, AimOutlined,
  LineChartOutlined, FullscreenOutlined, FullscreenExitOutlined,
  ExperimentOutlined
} from '@ant-design/icons'
import { executionAPI, deviceAPI, testCaseAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import ParsedTrendChart, { toNumber } from '../components/ParsedTrendChart'
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

/**
 * ``parsed_results`` may arrive as a JSON string (DB) or an object (WebSocket).
 * It holds one sample per reply, because a step may repeat the
 * same command N times ("循环读取 100 次").  Legacy rows hold a bare list,
 * which is treated as a single sample.
 */
function normalizeSamples(v: any): any[][] {
  if (!v) return []
  let parsed = v
  if (typeof v === 'string') {
    try { parsed = JSON.parse(v) } catch { return [] }
  }
  if (Array.isArray(parsed)) return [parsed]
  if (parsed && Array.isArray(parsed.samples)) {
    return parsed.samples.filter((s: any) => Array.isArray(s))
  }
  return []
}

/** Fields of the last reply - what the step list shows. */
function normalizeParsed(v: any): any[] {
  const samples = normalizeSamples(v)
  return samples.length ? samples[samples.length - 1] : []
}

/** One chart row per reply: { label: '#step' | '#step-seq', <field>: number } */
function buildCurveRows(stepIndex: number, parsed: any): any[] {
  const samples = normalizeSamples(parsed)
  if (!samples.length) return []
  const multi = samples.length > 1
  const rows: any[] = []
  samples.forEach((list, i) => {
    if (!Array.isArray(list) || !list.length) return
    const row: any = { label: multi ? `#${stepIndex}-${i + 1}` : `#${stepIndex}` }
    let any = false
    for (const p of list) {
      const name = String(p?.name || '').trim()
      if (!name) continue
      // "unknown" (empty frame / timeout) has no numeric value -> gap in the line
      row[name] = toNumber(p?.value)
      any = true
    }
    if (any) rows.push(row)
  })
  return rows
}

/** '#4' -> [4, 1];  '#4-12' -> [4, 12] */
function rowOrder(label: any): [number, number] {
  const m = /^#(\d+)(?:-(\d+))?$/.exec(String(label ?? ''))
  return m ? [Number(m[1]), Number(m[2] || 1)] : [0, 0]
}

const compareRows = (a: any, b: any) => {
  const [astep, aseq] = rowOrder(a.label)
  const [bstep, bseq] = rowOrder(b.label)
  return astep - bstep || aseq - bseq
}

// ---------------------------------------------------------------------------
// Live communication monitor windows (two independent instances)
// ---------------------------------------------------------------------------

function lineColor(dir: ComLine['dir']): string {
  return dir === 'TX' ? '#61dafb' : dir === 'RX' ? '#7ee787' : '#d4d4d4'
}

/**
 * 一个独立的通信监控窗口：自带设备选择、WebSocket 订阅、暂停/清空。
 * 页面上同时存在两个（A / B），用于并行执行时分别盯不同的设备。
 */
function useDeviceMonitor(devices: any[], slot: number) {
  const [selectedDevice, setSelectedDevice] = useState<string>('')
  const [lines, setLines] = useState<ComLine[]>([])
  const [paused, setPaused] = useState(false)
  const [wsState, setWsState] = useState<'connecting' | 'open' | 'closed'>('closed')
  const pausedRef = useRef(false)
  const bufferRef = useRef<ComLine[]>([])
  const endRef = useRef<HTMLDivElement | null>(null)

  // 默认给两个窗口挑不同的设备：已连接的优先
  useEffect(() => {
    if (!devices.length) return
    const ordered = [
      ...devices.filter((d: any) => d.status === 'connected'),
      ...devices.filter((d: any) => d.status !== 'connected'),
    ]
    const pick = ordered[slot] || ordered[0]
    if (pick) setSelectedDevice(prev => prev || pick.id)
  }, [devices, slot])

  const pushLine = useCallback((dir: ComLine['dir'], text: string) => {
    const line: ComLine = { id: ++lineSeq, ts: nowTs(), dir, text }
    if (pausedRef.current) {
      // 暂停期间继续收集，恢复时不丢数据
      bufferRef.current.push(line)
      if (bufferRef.current.length > MAX_LINES) {
        bufferRef.current = bufferRef.current.slice(-MAX_LINES)
      }
      return
    }
    setLines(prev => [...prev, line].slice(-MAX_LINES))
  }, [])

  useEffect(() => { pausedRef.current = paused }, [paused])

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

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [lines])

  const togglePause = useCallback(() => {
    if (paused) {
      const buffered = bufferRef.current
      bufferRef.current = []
      setLines(prev => [...prev, ...buffered].slice(-MAX_LINES))
    }
    setPaused(!paused)
  }, [paused])

  const clear = useCallback(() => {
    bufferRef.current = []
    setLines([])
  }, [])

  return { selectedDevice, setSelectedDevice, lines, paused, wsState, togglePause, clear, endRef, bufferRef }
}

/** 一列步骤列表（每个设备流程一列） */
function StepList({ steps, stepStatusConfig }: {
  steps: any[]
  stepStatusConfig: Record<string, { color: string; text: string }>
}) {
  if (!steps.length) {
    return (
      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无步骤" style={{ marginTop: 40 }} />
    )
  }
  return (
    <List
      size="small"
      dataSource={steps}
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
                {(s.samples?.length || 0) > 1 && (
                  <Tag style={{ marginBottom: 2, fontSize: 11 }}>
                    共 {s.samples.length} 次采样，显示最后一次
                  </Tag>
                )}
                {s.parsed.map((p: any, i: number) => {
                  const unknown = p.status === 'unknown'
                  return (
                    <Tooltip key={i} title={p.detail || ''}>
                      <Tag
                        color={unknown ? 'default' : (p.ok ? 'green' : 'red')}
                        style={{ marginBottom: 2, fontSize: 11 }}
                      >
                        {p.name}={p.value === null || p.value === undefined
                          ? '解析失败'
                          : String(p.value)}
                        {' '}
                        {unknown ? '?' : (p.ok ? '✓' : '✗')}
                      </Tag>
                    </Tooltip>
                  )
                })}
              </div>
            )}
          </List.Item>
        )
      }}
    />
  )
}

/** 单个通信监控窗口的渲染（A / B 两个实例共用） */
function ComMonitorCard({ title, m, devices, height = 260 }: {
  title: string
  m: ReturnType<typeof useDeviceMonitor>
  devices: any[]
  height?: number
}) {
  return (
    <Card
      size="small"
      title={
        <Space>
          <ApiOutlined />
          <span>{title}</span>
          <Tag color={m.wsState === 'open' ? 'green' : m.wsState === 'connecting' ? 'gold' : 'red'}>
            {m.wsState === 'open' ? '已连接' : m.wsState === 'connecting' ? '连接中' : '未连接'}
          </Tag>
          {m.paused && <Tag color="orange">已暂停</Tag>}
        </Space>
      }
      extra={
        <Space size={4}>
          <Select
            size="small"
            style={{ width: 170 }}
            placeholder="选择设备"
            value={m.selectedDevice || undefined}
            onChange={(v: any) => { m.setSelectedDevice(v); m.clear() }}
            options={devices.map((d: any) => ({
              value: d.id,
              label: `${d.name} (${d.protocol})`,
            }))}
          />
          <Button
            size="small"
            icon={m.paused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
            onClick={m.togglePause}
          >
            {m.paused ? '继续' : '暂停'}
          </Button>
          <Button size="small" icon={<ClearOutlined />} onClick={m.clear}>清空</Button>
        </Space>
      }
    >
      <div
        style={{
          height,
          overflowY: 'auto',
          background: '#1e1e1e',
          borderRadius: 4,
          padding: 8,
          fontFamily: 'Menlo, Consolas, monospace',
          fontSize: 12,
        }}
      >
        {m.lines.length === 0 ? (
          <div style={{ color: '#888', padding: 8 }}>
            等待端口通信数据…（下发命令或设备主动上报时会实时显示）
          </div>
        ) : (
          m.lines.map(line => (
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
        <div ref={m.endRef} />
      </div>
      <div style={{ marginTop: 6, color: '#888', fontSize: 12 }}>
        共 {m.lines.length} 行（最多保留 {MAX_LINES} 行）
        {m.paused && ` · 暂停期间已缓存 ${m.bufferRef.current.length} 行`}
      </div>
    </Card>
  )
}

export default function Executions() {
  const [executions, setExecutions] = useState<TestExecution[]>([])
  const [loading, setLoading] = useState(false)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  // ---- live communication monitor (two independent windows) ----
  const [devices, setDevices] = useState<any[]>([])
  const monitorA = useDeviceMonitor(devices, 0)
  const monitorB = useDeviceMonitor(devices, 1)

  // ---- start / stop controls ----
  const [startOpen, setStartOpen] = useState(false)
  const [caseOptions, setCaseOptions] = useState<any[]>([])
  const [selectedCase, setSelectedCase] = useState<string>('')
  const [starting, setStarting] = useState(false)
  // 后端已返回 testcase_name；这里是旧数据/用例被删除时的兜底缓存
  const [caseNames, setCaseNames] = useState<Record<string, string>>({})

  // ---- live step status ----
  const [trackedId, setTrackedId] = useState<string>('')
  const [trackedInfo, setTrackedInfo] = useState<any>(null)
  const [execSteps, setExecSteps] = useState<any[]>([])
  // all steps of the flow, so the window shows the whole plan while running
  const [flowSteps, setFlowSteps] = useState<any[]>([])

  // ---- parsed value curves (real-time + historical) ----
  const [curvePoints, setCurvePoints] = useState<any[]>([])
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const knownFieldsRef = useRef<string[]>([])
  const [trendOpen, setTrendOpen] = useState(false)
  const [trendData, setTrendData] = useState<any>(null)
  const [trendFields, setTrendFields] = useState<string[]>([])
  const [trendLoading, setTrendLoading] = useState(false)
  const [bigScreen, setBigScreen] = useState(false)

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

  const handleStop = async (id?: string) => {
    const running = executions.find(e => e.status === 'running')
    const target = id || running?.id || (trackedExec?.status === 'running' ? trackedId : '')
    if (!target) {
      message.info('当前没有运行中的执行')
      return
    }
    try {
      await executionAPI.stop(target)
      message.success('已停止执行')
      loadExecutions()
    } catch (err) {
      handleApiError(err, '停止失败')
    }
  }

  // ---- start a new run from this page ----
  const openStartModal = async () => {
    try {
      const res = await testCaseAPI.list()
      const items = extractItems(res)
      setCaseOptions(items)
      if (!selectedCase && items.length) setSelectedCase(items[0].id)
      setStartOpen(true)
    } catch (err) {
      handleApiError(err, '加载测试用例失败')
    }
  }

  const handleStart = async () => {
    if (!selectedCase) {
      message.warning('请先选择测试用例')
      return
    }
    try {
      setStarting(true)
      const res = await executionAPI.run(selectedCase)
      const started = (res as any)?.data?.data ?? (res as any)?.data
      message.success('已启动执行')
      setStartOpen(false)
      if (started?.id) setTrackedId(started.id)
      await loadExecutions()
    } catch (err) {
      handleApiError(err, '启动执行失败')
    } finally {
      setStarting(false)
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

  // load devices once — each monitor window picks its own default device
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await deviceAPI.list()
        const items = extractItems(res)
        if (!cancelled) setDevices(items)
      } catch {
        /* device list is optional for this page */
      }
    })()
    return () => { cancelled = true }
  }, [])

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

    // each execution starts with a clean curve + selection
    setCurvePoints([])
    setSelectedFields([])
    knownFieldsRef.current = []

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
        // chart points come straight from the stored parsed results - one
        // point per reply, so a repeated command yields a full series
        setCurvePoints(
          (d?.step_results || [])
            .slice()
            .sort((a: any, b: any) => Number(a.step_index) - Number(b.step_index))
            .flatMap((s: any) => buildCurveRows(s.step_index, s.parsed_results))
        )
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
        upsertStep(msg.step_index, {
          status: msg.status,
          actual: msg.actual,
          parsed_results: msg.parsed_results,
        })
        const rows = buildCurveRows(msg.step_index, msg.parsed_results)
        if (rows.length) {
          setCurvePoints(prev => {
            const fresh = new Set(rows.map(r => r.label))
            return [...prev.filter(r => !fresh.has(r.label)), ...rows]
              .sort(compareRows)
          })
        }
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
              // 节点级设备绑定 —— 并行流程按此拆列显示
              device_id: n?.config?.device_id || '',
            }))
        )
      } catch {
        if (!cancelled) setFlowSteps([])
      }
    })()
    return () => { cancelled = true }
  }, [trackedInfo?.testcase_id])

  // 用例名称兜底：后端已带 testcase_name，这里只在旧数据/用例已删除时补一次
  useEffect(() => {
    const tcId = trackedInfo?.testcase_id
    if (!tcId || caseNames[tcId]) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await testCaseAPI.get(tcId)
        const d: any = res.data?.data ?? res.data
        if (!cancelled && d?.name) {
          setCaseNames(prev => ({ ...prev, [tcId]: d.name }))
        }
      } catch {
        /* name is optional */
      }
    })()
    return () => { cancelled = true }
  }, [trackedInfo?.testcase_id, caseNames])

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
          samples: normalizeSamples(r?.parsed_results),
          actual: r?.actual,
          device_id: f.device_id || '',
        }
      })
    : execSteps.map((s: any) => ({
        ...s,
        parsed: normalizeParsed(s.parsed_results),
        samples: normalizeSamples(s.parsed_results),
      }))

  /** device id -> readable name */
  const deviceName = useCallback((id: string) => {
    if (!id) return '未指定设备'
    const d = devices.find((x: any) => x.id === id)
    return d ? `${d.name}` : id
  }, [devices])

  /**
   * 步骤按「执行设备」拆成多列：并行执行的设备流程各自一列，
   * 列数取决于实际用到的设备数量（不固定为 2 列）。
   */
  const stepColumns = (() => {
    if (mergedSteps.length === 0) return []
    const groups = new Map<string, { key: string; title: string; steps: any[] }>()
    for (const s of mergedSteps) {
      const key = s.device_id || '__default__'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          title: key === '__default__'
            ? (trackedInfo?.device_id ? deviceName(trackedInfo.device_id) : '主流程')
            : deviceName(key),
          steps: [],
        })
      }
      groups.get(key)!.steps.push(s)
    }
    return Array.from(groups.values())
  })()

  // ---- parsed fields that can be plotted ----
  const availableFields = (() => {
    const set = new Set<string>()
    mergedSteps.forEach(s => (s.parsed || []).forEach((p: any) => {
      const n = String(p?.name || '').trim()
      if (n) set.add(n)
    }))
    curvePoints.forEach(r => Object.keys(r).forEach(k => {
      if (k !== 'label') set.add(k)
    }))
    return Array.from(set)
  })()

  // newly discovered fields start selected; user can uncheck them anytime
  useEffect(() => {
    const fresh = availableFields.filter(f => !knownFieldsRef.current.includes(f))
    if (!fresh.length) return
    knownFieldsRef.current = [...knownFieldsRef.current, ...fresh]
    setSelectedFields(prev => Array.from(new Set([...prev, ...fresh])))
  }, [availableFields])

  // per-field summary: last / min / max and how many judgements failed
  const fieldStats = selectedFields.map(f => {
    const vals = curvePoints
      .map(r => r[f])
      .filter(v => typeof v === 'number' && Number.isFinite(v)) as number[]
    // count over every reply, not just the last one
    const fails = mergedSteps.reduce(
      (n, s) => n + (s.samples || []).reduce(
        (m: number, sample: any) => m + (Array.isArray(sample) ? sample : []).filter(
          (p: any) => String(p?.name || '').trim() === f && p?.ok === false
        ).length,
        0,
      ),
      0,
    )
    const unknowns = mergedSteps.reduce(
      (n, s) => n + (s.samples || []).reduce(
        (m: number, sample: any) => m + (Array.isArray(sample) ? sample : []).filter(
          (p: any) => String(p?.name || '').trim() === f && p?.status === 'unknown'
        ).length,
        0,
      ),
      0,
    )
    return {
      field: f,
      unknowns,
      last: vals.length ? vals[vals.length - 1] : null,
      min: vals.length ? Math.min(...vals) : null,
      max: vals.length ? Math.max(...vals) : null,
      fails,
    }
  })

  const openTrend = async () => {
    const tcId = trackedInfo?.testcase_id
    if (!tcId) {
      message.info('请先选择一次执行记录')
      return
    }
    setTrendOpen(true)
    setTrendLoading(true)
    try {
      const res = await testCaseAPI.parsedTrend(tcId, 50)
      const data = res.data?.data ?? res.data
      setTrendData(data)
      setTrendFields((data?.fields || []).slice(0, 5))
    } catch (err) {
      handleApiError(err, '加载历史趋势失败')
    } finally {
      setTrendLoading(false)
    }
  }

  // flatten historical series into chart rows, ordered by execution then step
  const trendRows = (() => {
    if (!trendData?.series) return []
    const order: Record<string, number> = {}
    ;(trendData.executions || []).forEach((e: any, i: number) => { order[e.id] = i })
    const rowByKey: Record<string, any> = {}
    const slots: Array<{ key: string; exec: string; step: number; seq: number }> = []
    for (const f of trendFields) {
      for (const p of (trendData.series[f] || [])) {
        // one row per reply: a step repeating a command N times is N rows
        const key = `${p.execution_id}#${p.step_index}#${p.seq ?? 0}`
        if (!rowByKey[key]) {
          rowByKey[key] = {
            label: (p.seq ?? 0) > 0 || (p.total ?? 1) > 1
              ? `#${p.step_index}-${(p.seq ?? 0) + 1}`
              : `#${p.step_index}`,
          }
          slots.push({
            key, exec: p.execution_id, step: p.step_index, seq: p.seq ?? 0,
          })
        }
        rowByKey[key][f] = p.num
      }
    }
    slots.sort(
      (a, b) => (
        (order[a.exec] ?? 0) - (order[b.exec] ?? 0) || a.step - b.step || a.seq - b.seq
      )
    )
    return slots.map(s => rowByKey[s.key])
  })()

  const currentStep = mergedSteps.find(s => s.status === 'running')
  const trackedExec = executions.find(e => e.id === trackedId)
  const runningExec = executions.find(e => e.status === 'running')

  // 标题处显示的用例名称：优先取正在运行的执行，其次取当前跟踪的执行
  const currentCaseName =
    runningExec?.testcase_name
    || trackedExec?.testcase_name
    || trackedInfo?.testcase_name
    || (trackedInfo?.testcase_id ? caseNames[trackedInfo.testcase_id] : '')
    || ''

  const columns = [
    {
      title: '执行 ID',
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => id.slice(0, 8) + '...',
    },
    {
      title: '测试用例',
      dataIndex: 'testcase_id',
      key: 'testcase_id',
      render: (id: string, record: any) => (
        <Space size={4}>
          <span>{record?.testcase_name || '（用例已删除）'}</span>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {id?.slice(0, 8) + '…' || '-'}
          </Text>
        </Space>
      ),
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

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <Title level={3} style={{ margin: 0 }}>测试执行</Title>
          {/* 当前执行（或正在跟踪）的用例名称 —— 一眼看出在跑什么 */}
          {currentCaseName && (
            <Tag color="blue" style={{ marginInlineEnd: 0, maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              <ExperimentOutlined /> {currentCaseName}
            </Tag>
          )}
        </div>
        <Space>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={openStartModal}
            disabled={executions.some(e => e.status === 'running')}
          >
            启动
          </Button>
          <Button
            danger
            icon={<PauseCircleOutlined />}
            onClick={() => handleStop()}
            disabled={!executions.some(e => e.status === 'running')}
          >
            停止
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadExecutions}>刷新</Button>
        </Space>
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

      {/* ---------- live communication monitor: TWO windows ---------- */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <ComMonitorCard title="实时通信监控 A" m={monitorA} devices={devices} />
        </Col>
        <Col xs={24} lg={12}>
          <ComMonitorCard title="实时通信监控 B" m={monitorB} devices={devices} />
        </Col>
      </Row>

      {/* ---------- live step status (one column per device) ---------- */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24}>
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

            {stepColumns.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无步骤（执行开始后将实时显示）"
                style={{ marginTop: 60 }}
              />
            ) : (
              <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 4 }}>
                {stepColumns.map(col => {
                  const passed = col.steps.filter((s: any) => s.status === 'passed').length
                  const failed = col.steps.filter((s: any) => s.status === 'failed' || s.status === 'error').length
                  return (
                    <div
                      key={col.key}
                      style={{
                        flex: '1 1 0',
                        minWidth: 260,
                        border: '1px solid #f0f0f0',
                        borderRadius: 6,
                        background: '#fafafa',
                      }}
                    >
                      <div style={{
                        padding: '6px 10px', borderBottom: '1px solid #f0f0f0',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      }}>
                        <Space size={6}>
                          <ApiOutlined style={{ color: '#1677ff' }} />
                          <Text strong style={{ fontSize: 12 }}>{col.title}</Text>
                        </Space>
                        <Space size={4}>
                          <Tag color="success" style={{ marginInlineEnd: 0, fontSize: 11 }}>通过 {passed}</Tag>
                          <Tag color="error" style={{ marginInlineEnd: 0, fontSize: 11 }}>失败 {failed}</Tag>
                          <Tag style={{ marginInlineEnd: 0, fontSize: 11 }}>{col.steps.length} 步</Tag>
                        </Space>
                      </div>
                      <div style={{ height: 288, overflowY: 'auto' }}>
                        <StepList steps={col.steps} stepStatusConfig={stepStatusConfig} />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------- parsed data curves (real time + historical) ---------- */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24}>
          <Card
            title={
              <Space>
                <LineChartOutlined />
                <span>解析数据曲线</span>
                <Tag color="purple">{curvePoints.length} 点</Tag>
                {selectedFields.length > 0 && (
                  <Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
                    已选 {selectedFields.length} 项
                  </Text>
                )}
              </Space>
            }
            extra={
              <Space>
                <Button size="small" icon={<LineChartOutlined />} onClick={openTrend}>
                  历史趋势
                </Button>
                <Tooltip title={bigScreen ? '退出大屏模式' : '大屏模式'}>
                  <Button
                    size="small"
                    icon={bigScreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                    onClick={() => setBigScreen(v => !v)}
                  >
                    {bigScreen ? '退出大屏' : '大屏'}
                  </Button>
                </Tooltip>
              </Space>
            }
          >
            {availableFields.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="该用例尚未配置结果解析 — 在「测试用例」页展开步骤即可配置，执行后这里会画出数据曲线"
              />
            ) : (
              <>
                <div style={{ marginBottom: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12, marginRight: 8 }}>
                    选择需要实时显示的数据：
                  </Text>
                  <Checkbox.Group
                    options={availableFields.map(f => ({ label: f, value: f }))}
                    value={selectedFields}
                    onChange={(v) => setSelectedFields(v as string[])}
                  />
                </div>
                <ParsedTrendChart
                  data={curvePoints}
                  fields={selectedFields}
                  height={bigScreen ? 420 : 260}
                  big={bigScreen}
                />
                {fieldStats.length > 0 && (
                  <div style={{ marginTop: 8 }}>
                    <Space wrap size={[12, 6]}>
                      {fieldStats.map(s => (
                        <Tag
                          key={s.field}
                          color={s.fails ? 'red' : 'blue'}
                          style={{ fontSize: bigScreen ? 15 : 12 }}
                        >
                          {s.field}：最新 {s.last ?? '-'} · 最小 {s.min ?? '-'} · 最大 {s.max ?? '-'}
                          {s.unknowns ? ` · 空帧 ${s.unknowns} 次` : ''}
                          {s.fails ? ` · 判定 FAIL ${s.fails} 次` : (s.unknowns ? '' : ' · 全部 PASS')}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}
              </>
            )}
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

      <Modal
        title={
          <Space>
            <LineChartOutlined />
            <span>历史解析数据趋势</span>
            <Tag color="blue">最近 {trendData?.executions?.length ?? 0} 次执行</Tag>
          </Space>
        }
        open={trendOpen}
        onCancel={() => setTrendOpen(false)}
        footer={null}
        width={bigScreen ? '96vw' : 900}
        style={{ top: bigScreen ? 16 : 40 }}
      >
        {trendLoading ? (
          <div style={{ textAlign: 'center', padding: 50 }}><Spin /></div>
        ) : (
          <>
            <Space style={{ marginBottom: 10 }} wrap>
              <Text type="secondary" style={{ fontSize: 12 }}>
                选择查看的数据：
              </Text>
              <Checkbox.Group
                options={(trendData?.fields || []).map((f: string) => ({ label: f, value: f }))}
                value={trendFields}
                onChange={(v) => setTrendFields(v as string[])}
              />
              <Tooltip title="大屏模式">
                <Button
                  size="small"
                  icon={bigScreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={() => setBigScreen(v => !v)}
                >
                  {bigScreen ? '退出大屏' : '大屏'}
                </Button>
              </Tooltip>
            </Space>

            <ParsedTrendChart
              data={trendRows}
              fields={trendFields}
              height={bigScreen ? 520 : 340}
              big={bigScreen}
            />

            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 11 }}>
                趋势数据直接来自已落库的步骤解析结果（共 {trendData?.total_points ?? 0} 个采样点），
                无需额外建表。每一步的每条应答都是一个采样点；空帧记为 unknown，不参与判定。
                判定 FAIL 的点同样记录在案 —— FAIL 是判定结果，不是系统/设备告警。
              </Text>
            </div>
          </>
        )}
      </Modal>

      {/* ---------- start a new execution ---------- */}
      <Modal
        title="启动测试执行"
        open={startOpen}
        onCancel={() => setStartOpen(false)}
        onOk={handleStart}
        confirmLoading={starting}
        okText="启动"
        cancelText="取消"
      >
        <div style={{ marginBottom: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            选择要执行的测试用例；执行开始后本页会自动跟踪这一次执行。
          </Text>
        </div>
        <Select
          style={{ width: '100%' }}
          placeholder="选择测试用例"
          showSearch
          optionFilterProp="label"
          value={selectedCase || undefined}
          onChange={(v: any) => setSelectedCase(v)}
          options={caseOptions.map((c: any) => ({
            value: c.id,
            label: c.name || c.id,
          }))}
        />
        {caseOptions.length === 0 && (
          <div style={{ marginTop: 8 }}>
            <Text type="danger" style={{ fontSize: 12 }}>
              暂无测试用例 —— 请先在「测试用例」页创建。
            </Text>
          </div>
        )}
      </Modal>

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
