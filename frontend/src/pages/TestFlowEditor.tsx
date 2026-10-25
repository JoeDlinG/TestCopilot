/**
 * Enhanced Test Flow Editor — ReactFlow-based interactive flowchart editor.
 *
 * Features:
 *  - Custom node renderers: Start / Action / Condition / Loop / End
 *  - Drag-from-palette to add nodes
 *  - Double-click node to edit its config (condition expression, loop params, etc.)
 *  - Edge labelling for condition branches
 *  - "Generate Code" → calls backend codegen → shows results in a Drawer
 *  - Save flow via API
 */
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactFlow, {
  Node, Edge, Controls, Background,
  MiniMap, useNodesState, useEdgesState,
  addEdge, Connection, NodeProps, Handle, Position,
  ConnectionMode, ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  Card, Button, Space, message, Typography, Modal, Input, InputNumber, Form,
  Select, Tag, Breadcrumb, Drawer, Tooltip, Divider, Collapse,
} from 'antd'
import {
  SaveOutlined, ArrowLeftOutlined, PlusOutlined,
  PlayCircleOutlined, HomeOutlined, CodeOutlined,
  BranchesOutlined, SyncOutlined, ThunderboltOutlined,
  DeleteOutlined, DatabaseOutlined, ImportOutlined, ExportOutlined,
  CopyOutlined, SnippetsOutlined, DiffOutlined, ClockCircleOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
  // Native undo/redo: 返回 and 撤销 both used ArrowLeftOutlined, and redo was
  // that same arrow mirrored horizontally. Both now have their own glyph.
  UndoOutlined, RedoOutlined, StopOutlined,
} from '@ant-design/icons'
import { testCaseAPI, deviceAPI } from '../services/api'
import { extractData, extractItems, handleApiError, _errorMessage } from '../services/apiHelper'
import type { TestCase } from '../types'
import { useI18n } from '../i18n'

const { Title, Text } = Typography

// Extend ReactFlow Node to carry custom config per node type
interface FlowNode extends Node {
  config?: Record<string, any>
}

// ---------------------------------------------------------------------------
// Custom node components
// ---------------------------------------------------------------------------

/**
 * Node type encoding (issue #22, 方案 A).
 *
 * Every type is distinguished by **shape / icon / fill mode** — never by a
 * dedicated hue. Amber is the single exception and is reserved for 循环, whose
 * iteration boundary is the thing engineers most need to spot.
 *
 *   开始   描边空心        初始化 低饱和蓝底     操作   石墨实心
 *   判断   菱形（形状编码） 循环   琥珀描边+左色条  延时   虚线边框
 *   结束   弱化深底
 *
 * Colours come from CSS variables emitted from ``src/theme/tokens.ts``, so the
 * whole canvas follows the light/dark switch with no hard-coded hex here.
 */
type NodeKind = 'outline' | 'tint' | 'solid' | 'diamond' | 'loop' | 'dashed' | 'dim'

const NODE_BASE: React.CSSProperties = {
  padding: '10px 18px',
  // The old start/end pills used 20px; the system caps radii at 6px.
  borderRadius: 6,
  fontWeight: 600,
  fontSize: 12,
  minWidth: 140,
  textAlign: 'center',
  wordBreak: 'break-word',
}

function nodeSurface(kind: NodeKind): React.CSSProperties {
  const v = (name: string) => `var(--flow-node-${name})`
  switch (kind) {
    case 'outline': // start — deep Morandi blue
      return {
        background: v('start-bg'), color: v('start-fg'),
        border: `1px solid ${v('start-border')}`,
      }
    case 'tint': // init — blue grey
      return {
        background: v('init-bg'), color: v('init-fg'),
        border: `1px solid ${v('init-border')}`,
      }
    case 'solid': // action — graphite (deliberately not near-black)
      return {
        background: v('action-bg'), color: v('action-fg'),
        border: `1px solid ${v('action-border')}`,
      }
    case 'diamond': // condition — instrument blue (lighter)
      return {
        background: v('cond-bg'), color: v('cond-fg'),
        border: `1px solid ${v('cond-border')}`,
      }
    case 'loop': // loop — light amber fill + dark amber text + 3px left bar
      return {
        background: v('loop-bg'), color: v('loop-fg'),
        border: `1px solid ${v('loop-border')}`,
        borderLeft: `3px solid ${v('loop-bar')}`,
      }
    case 'dashed': // delay — mid grey + dashed border
      return {
        background: v('delay-bg'), color: v('delay-fg'),
        border: `1px dashed ${v('delay-border')}`,
      }
    case 'dim': // end — dark grey (never red: red belongs to FAIL/ERROR)
      return {
        background: v('end-bg'), color: v('end-fg'),
        border: `1px solid ${v('end-border')}`,
      }
    default:
      return { background: v('action-bg'), color: v('action-fg') }
  }
}

/**
 * Runtime state is a *separate layer* from node type (issue #22).
 *
 * - 运行中 = amber **pulsing halo** + spinning corner badge → dynamic
 * - 失败   = red ring → static
 *
 * Because it is a halo rather than a fill, it never competes with the static
 * amber border of a 循环 node.
 */
function NodeRuntimeRing({ data, children }: { data: any; children: React.ReactNode }) {
  const state = data?.runtimeState
  if (!state) return <>{children}</>
  const color = state === 'failed' ? 'var(--flow-failed)' : 'var(--flow-running)'
  return (
    <div style={{ position: 'relative' }}>
      {children}
      <span
        className={state === 'running' ? 'flow-pulse' : undefined}
        style={{
          position: 'absolute', inset: -5, borderRadius: 8,
          boxShadow: `0 0 0 2px ${color}`, pointerEvents: 'none',
        }}
      />
      {state === 'running' && (
        <SyncOutlined
          spin
          style={{
            position: 'absolute', top: -9, right: -9, fontSize: 13, color,
            background: 'var(--flow-node-solid-bg)', borderRadius: '50%', padding: 2,
          }}
        />
      )}
    </div>
  )
}

function StartNode({ data }: NodeProps) {
  return (
    <NodeRuntimeRing data={data}>
      <div style={{ ...NODE_BASE, ...nodeSurface('outline'), display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
        <PlayCircleOutlined style={{ fontSize: 14 }} />
        {data.label}
        <Handle type="source" position={Position.Bottom} />
      </div>
    </NodeRuntimeRing>
  )
}

function EndNode({ data }: NodeProps) {
  return (
    <NodeRuntimeRing data={data}>
      <div style={{ ...NODE_BASE, ...nodeSurface('dim'), display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
        <Handle type="target" position={Position.Top} />
        <StopOutlined style={{ fontSize: 14 }} />
        {data.label}
      </div>
    </NodeRuntimeRing>
  )
}

function ActionNode({ data }: NodeProps) {
  return (
    <NodeRuntimeRing data={data}>
      <div style={{ ...NODE_BASE, ...nodeSurface('solid') }}>
        <Handle type="target" position={Position.Top} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center' }}>
          <ThunderboltOutlined style={{ fontSize: 14 }} />
          {data.label}
        </div>
        <NodeIoBadges data={data} />
        <Handle type="source" position={Position.Bottom} />
      </div>
    </NodeRuntimeRing>
  )
}

function ConditionNode({ data, selected }: NodeProps) {
  // 判断 is encoded purely by shape: the diamond carries no hue at all, so it
  // remains unambiguous in a greyscale screenshot.
  return (
    <NodeRuntimeRing data={data}>
      <div style={{ width: 140, height: 70, position: 'relative' }}>
        <svg width="140" height="70" style={{ position: 'absolute', top: 0, left: 0 }}>
          <polygon
            points="70,2 138,35 70,68 2,35"
            fill="var(--flow-node-cond-bg)"
            stroke="var(--flow-node-cond-border)"
            strokeWidth={selected ? 2 : 1}
          />
        </svg>
        <div style={{
          position: 'relative', zIndex: 2, width: 140, height: 70,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 11, fontWeight: 600, color: 'var(--flow-node-cond-fg)',
          textAlign: 'center', padding: '0 30px', lineHeight: 1.3,
        }}>
          {data.label}
        </div>
        <Handle type="target" position={Position.Top}
          style={{ top: 0, left: '50%' }} />
        {/* True / false exits differ by lightness only — never green/red. */}
        <Handle type="source" position={Position.Bottom} id="s-true"
          style={{ background: 'var(--flow-handle-true)', bottom: -2, left: '30%' }} />
        <Handle type="source" position={Position.Bottom} id="s-false"
          style={{ background: 'var(--flow-handle-false)', bottom: -2, left: '70%' }} />
      </div>
    </NodeRuntimeRing>
  )
}

function LoopNode({ data }: NodeProps) {
  return (
    <NodeRuntimeRing data={data}>
      <div style={{
        ...NODE_BASE, ...nodeSurface('loop'),
        display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
      }}>
        <SyncOutlined style={{ fontSize: 14 }} />
        <Handle type="target" position={Position.Top} />
        <div>
          {data.label}
          <NodeIoBadges data={data} />
        </div>
        <Handle type="source" position={Position.Bottom} />
      </div>
    </NodeRuntimeRing>
  )
}

/** 初始化 / 重置节点：集中声明变量，供后续节点引用 */
function InitNode({ data, selected }: NodeProps) {
  const vars: any[] = (data as any)?.variables || []
  return (
    <NodeRuntimeRing data={data}>
      <div style={{
        ...NODE_BASE, ...nodeSurface('tint'), ...(selected ? { outline: '2px solid var(--flow-selected)' } : null),
        display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
      }}>
        <DatabaseOutlined style={{ fontSize: 14 }} />
        <Handle type="target" position={Position.Top} />
        <div>
          <div>{data.label}</div>
        {vars.length > 0 && (
          <div style={{ fontSize: 10, fontWeight: 400, marginTop: 2 }}>
            {vars.slice(0, 3).map((v: any, i: number) => (
              <span key={i}>{v?.name || '?'}{i < Math.min(vars.length, 3) - 1 ? ', ' : ''}</span>
            ))}
            {vars.length > 3 ? ` +${vars.length - 3}` : ''}
          </div>
        )}
          <NodeIoBadges data={data} />
        </div>
        <Handle type="source" position={Position.Bottom} />
      </div>
    </NodeRuntimeRing>
  )
}

/** 延时节点：按毫秒等待，支持 {占位符} 引用前序节点输出 */
function DelayNode({ data, selected }: NodeProps) {
  const { t } = useI18n()
  const ms = (data as any)?.duration
  return (
    <NodeRuntimeRing data={data}>
      <div style={{
        ...NODE_BASE, ...nodeSurface('dashed'), ...(selected ? { outline: '2px solid var(--flow-selected)' } : null),
        display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
      }}>
        <ClockCircleOutlined style={{ fontSize: 14 }} />
        <Handle type="target" position={Position.Top} />
        <div>
          <div>{data.label}</div>
          <div style={{ fontSize: 10, fontWeight: 400, marginTop: 2 }}>
            {t('node.delay')} {ms === undefined || ms === null || ms === '' ? '?' : ms} ms
          </div>
          <NodeIoBadges data={data} />
        </div>
        <Handle type="source" position={Position.Bottom} />
      </div>
    </NodeRuntimeRing>
  )
}

/**
 * 节点上的输入参数 / 输出返回值徽标（Issue #4）。
 * 让用户在画布上一眼看出哪些节点会产生可被后续引用的数据。
 */
function NodeIoBadges({ data }: { data: any }) {
  const { t } = useI18n()
  const inputs: any[] = data?.inputs || []
  const outputs: any[] = data?.outputs || []
  if (inputs.length === 0 && outputs.length === 0) return null
  // A translucent white badge was invisible on the light surfaces (开始 / 初始化)
  // and unusable in dark mode; the neutral is now derived from the canvas.
  const badge: React.CSSProperties = {
    fontSize: 9, lineHeight: '14px', padding: '0 4px', borderRadius: 4,
    background: 'var(--flow-badge-bg)', color: 'var(--flow-badge-fg)',
    border: '1px solid var(--flow-badge-border)',
  }
  return (
    <div style={{ display: 'flex', gap: 4, justifyContent: 'center', marginTop: 3 }}>
      {inputs.length > 0 && (
        <span
          title={`${t('label.inputsColon')}${inputs.map((i) => i?.name).join(', ')}`}
          style={badge}
        >
          <ImportOutlined /> {inputs.length}
        </span>
      )}
      {outputs.length > 0 && (
        <span
          title={`${t('label.outputsColon')}${outputs.map((o) => o?.name).join(', ')}`}
          style={badge}
        >
          <ExportOutlined /> {outputs.length}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Node types registry
// ---------------------------------------------------------------------------

const nodeTypes = {
  start: StartNode,
  end: EndNode,
  action: ActionNode,
  condition: ConditionNode,
  loop: LoopNode,
  init: InitNode,
  delay: DelayNode,
  test_step: ActionNode,
  default: ActionNode,
  input: StartNode,
  output: EndNode,
}

// ---------------------------------------------------------------------------
// Palette sidebar items (draggable onto the canvas)
// ---------------------------------------------------------------------------

interface PaletteItem {
  type: string
  label: string
  /** Which surface encoding this type uses (see :func:`nodeSurface`). */
  kind: NodeKind
  icon: React.ReactNode
}

/** 输入参数 / 输出返回值支持的值类型（与后端 flow_context.VALUE_TYPES 对应） */
const VALUE_TYPE_OPTIONS = (t: (k: string) => string) => [
  { label: t('dtype.string'), value: 'string' },
  { label: t('dtype.int'), value: 'int' },
  { label: t('dtype.float'), value: 'float' },
  { label: t('dtype.bool'), value: 'bool' },
  { label: t('dtype.hex'), value: 'hex' },
  { label: t('dtype.any'), value: 'any' },
]

const PALETTE = (t: (k: string) => string): PaletteItem[] => [
  { type: 'init', label: t('node.init'), kind: 'tint', icon: <DatabaseOutlined /> },
  { type: 'action', label: t('col.actions'), kind: 'solid', icon: <ThunderboltOutlined /> },
  { type: 'condition', label: t('node.condition'), kind: 'diamond', icon: <BranchesOutlined /> },
  { type: 'loop', label: t('col.loop'), kind: 'loop', icon: <SyncOutlined /> },
  { type: 'delay', label: t('node.delay'), kind: 'dashed', icon: <ClockCircleOutlined /> },
  { type: 'end', label: t('node.end'), kind: 'dim', icon: <StopOutlined /> },
]

/** Diamond palette chips read as a lozenge glyph rather than a filled block. */
/**
 * Palette chips use the exact same surface as the node they create, so what you
 * drag out is what you see. 判断 was previously a `clip-path` diamond with a
 * transparent fill — it read as "nothing there". The diamond is now a small
 * rotated-square marker *inside* a filled chip, which keeps the border visible
 * (clip-path would have cut it off) and the label legible.
 */
function paletteChipStyle(kind: NodeKind): React.CSSProperties {
  return nodeSurface(kind)
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

let _nodeIdCounter = 0
function newNodeId(): string { _nodeIdCounter++; return `user_node_${_nodeIdCounter}_${Date.now()}` }
function newEdgeId(): string { return `user_edge_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` }

/** 收集流程中的可用变量：初始化节点变量 + 各节点声明的输出返回值 */
function collectFlowVariables(nds: Node[], stopBeforeId?: string) {
  const found: { name: string; type?: string; source_label: string }[] = []
  const seen = new Set<string>()
  for (const n of nds) {
    if (stopBeforeId && n.id === stopBeforeId) break
    const cfg: any = (n as any).config || {}
    const label = n.data?.label || n.id
    const specs: any[] = [
      ...(n.type === 'init' ? (cfg.variables || []) : []),
      ...(cfg.outputs || []),
    ]
    for (const s of specs) {
      const name = (s?.name || '').toString().trim()
      if (!name || seen.has(name)) continue
      seen.add(name)
      found.push({ name, type: s?.type, source_label: label })
    }
  }
  return found
}

export default function TestFlowEditor() {
  const { t } = useI18n()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [testCase, setTestCase] = useState<TestCase | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading, setLoading] = useState(false)

  // Node edit modal
  const [editOpen, setEditOpen] = useState(false)
  const [editNode, setEditNode] = useState<Node | null>(null)
  const [editForm] = Form.useForm()
  // 响应式监听循环类型：切换 for / while 时表单字段即时联动
  const loopType = Form.useWatch('loop_type', editForm) || 'for'
  // 节点类型：可在编辑弹窗中就地切换（action / condition / loop / end）
  const nodeType = Form.useWatch('node_type', editForm) || editNode?.type || 'action'
  // 复制 / 粘贴剪贴板（节点 + 其内部连线）
  const clipboardRef = useRef<{ nodes: Node[]; edges: Edge[] } | null>(null)

  // Issue #4：本节点之前可用的变量（初始化变量 + 前序节点输出），
  // 可用 {变量名} 形式写进命令 / 预期结果 / 条件表达式
  const flowVars = collectFlowVariables(nodes, editNode?.id)

  // Code generation
  const [codeDrawerOpen, setCodeDrawerOpen] = useState(false)
  const [codeText, setCodeText] = useState('')
  const [codeLoading, setCodeLoading] = useState(false)

  // 全屏编辑（Esc 退出）
  const [fullscreen, setFullscreen] = useState(false)

  // 选中的节点 / 连线加高亮：光靠节点配色的细微差别看不出选中了什么
  const displayNodes = useMemo(() => nodes.map((n) => (
    (n as any).selected
      ? {
          ...n,
          zIndex: 10,
          style: {
            ...(n.style || {}),
            // State layer: blue ring, independent of the node's type colour.
            boxShadow: '0 0 0 3px var(--flow-selected)',
            borderRadius: 8,
          },
        }
      : n
  )), [nodes])

  const displayEdges = useMemo(() => edges.map((e) => (
    (e as any).selected
      ? {
          ...e,
          zIndex: 10,
          animated: true,
          style: { ...(e.style || {}), stroke: 'var(--b-500)', strokeWidth: 3 },
          labelStyle: { ...(e.labelStyle || {}), fill: 'var(--b-500)', fontWeight: 600 },
          labelBgStyle: { ...(e.labelBgStyle || {}), fill: 'var(--flow-canvas-bg)' },
        }
      : { ...e, style: { strokeWidth: 2, ...(e.style || {}) } }
  )), [edges])

  const reactFlowRef = useRef<ReactFlowInstance | null>(null)

  // 可选的执行设备列表 —— 节点可绑定到指定设备（并行流程会分列显示）
  const [devices, setDevices] = useState<any[]>([])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await deviceAPI.list()
        if (!cancelled) setDevices(extractItems(res))
      } catch {
        /* device list is optional here */
      }
    })()
    return () => { cancelled = true }
  }, [])

  // ---- Undo / Redo history stack ----
  const historyRef = useRef<{ nodes: Node[]; edges: Edge[] }[]>([])
  const historyPosRef = useRef(-1)
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)
  const _skipHistoryRef = useRef(false) // skip recording when undoing/redoing

  const pushHistory = useCallback(() => {
    if (_skipHistoryRef.current) return
    // Truncate any future history when a new action is taken
    const stack = historyRef.current
    historyRef.current = stack.slice(0, historyPosRef.current + 1)
    historyRef.current.push({
      nodes: JSON.parse(JSON.stringify(nodes)),
      edges: JSON.parse(JSON.stringify(edges)),
    })
    historyPosRef.current = historyRef.current.length - 1
    // Cap at 50 entries to save memory
    if (historyRef.current.length > 50) {
      historyRef.current = historyRef.current.slice(-50)
      historyPosRef.current = historyRef.current.length - 1
    }
    setCanUndo(historyPosRef.current > 0)
    setCanRedo(false)
  }, [nodes, edges])

  const undo = useCallback(() => {
    const stack = historyRef.current
    if (historyPosRef.current <= 0) return
    // Save current state at top of stack before moving back
    if (historyPosRef.current === stack.length - 1) {
      stack.push({
        nodes: JSON.parse(JSON.stringify(nodes)),
        edges: JSON.parse(JSON.stringify(edges)),
      })
    }
    historyPosRef.current--
    const snap = stack[historyPosRef.current]
    _skipHistoryRef.current = true
    setNodes(snap.nodes)
    setEdges(snap.edges)
    _skipHistoryRef.current = false
    setCanUndo(historyPosRef.current > 0)
    setCanRedo(true)
  }, [nodes, edges, setNodes, setEdges])

  const redo = useCallback(() => {
    const stack = historyRef.current
    if (historyPosRef.current >= stack.length - 1) return
    historyPosRef.current++
    const snap = stack[historyPosRef.current]
    _skipHistoryRef.current = true
    setNodes(snap.nodes)
    setEdges(snap.edges)
    _skipHistoryRef.current = false
    setCanUndo(true)
    setCanRedo(historyPosRef.current < stack.length - 1)
  }, [setNodes, setEdges])

  // ---- Load test case and flow ----
  const loadTestCase = useCallback(async () => {
    if (!id) return
    setLoading(true)
    try {
      const res = await testCaseAPI.get(id)
      const tc = extractData(res)
      setTestCase(tc)
      try {
        const flowRes = await testCaseAPI.getFlow(id)
        const flow = extractData(flowRes)
        if (flow?.nodes?.length) {
          setNodes(flow.nodes)
          setEdges(flow.edges || [])
          return
        }
      } catch { /* no flow yet — use default */ }
      // Default empty flow
      setNodes([
        { id: 'start', type: 'start', data: { label: t('node.start') }, position: { x: 400, y: 0 } },
        { id: 'end', type: 'end', data: { label: t('node.end') }, position: { x: 400, y: 400 } },
      ])
      setEdges([])
    } catch (err) {
      handleApiError(err, t('msg.loadCasesFailed'))
    } finally {
      setLoading(false)
    }
  }, [id, setNodes, setEdges])

  useEffect(() => { loadTestCase() }, [loadTestCase])

  // ---- Connect handler ----
  const onConnect = useCallback(
    (connection: Connection) => {
      pushHistory()
      setEdges((eds) => addEdge({
        ...connection,
        id: newEdgeId(),
        label: '',
      }, eds))
    },
    [setEdges, pushHistory],
  )

  // ---- Node double-click → edit ----
  const onNodeDoubleClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (node.type === 'start' || node.type === 'end' || node.type === 'input' || node.type === 'output') return
    setEditNode(node)
    const config = (node as any).config || {}
    editForm.setFieldsValue({
      label: node.data?.label || '',
      command: config.command || '',
      expected: config.expected || '',
      condition: config.condition || 'True',
      true_label: config.true_label || '',
      false_label: config.false_label || '',
      loop_type: config.loop_type || 'for',
      loop_variable: config.variable || 'i',
      loop_expression: config.condition || '3',
      duration: config.duration ?? config.duration_ms ?? 1000,
      device_id: config.device_id || '',
      node_type: node.type || 'action',
      variables: config.variables || [],
      entry_condition: config.entry_condition || '',
      entry_fail_action: config.entry_fail_action || 'skip',
      break_condition: config.break_condition || '',
      max_iterations: config.max_iterations || '',
      // Issue #4：输入参数与输出返回值
      inputs: config.inputs || [],
      outputs: config.outputs || [],
    })
    setEditOpen(true)
  }, [editForm])

  // ---- Save node edit ----
  const handleEditSave = () => {
    const vals = editForm.getFieldsValue()
    if (!editNode) return
    pushHistory()
    setNodes((nds) => nds.map((n) => {
      if (n.id !== editNode.id) return n
      const nextInputs = vals.inputs || []
      const nextOutputs = vals.outputs || []
      const updated = {
        ...n,
        data: {
          ...n.data,
          label: vals.label || n.data?.label,
          // 同步到 data，画布节点上直接显示输入/输出徽标 / 延时毫秒数
          duration: vals.duration,
          inputs: nextInputs,
          outputs: nextOutputs,
        },
        config: {
          ...(n as any).config,
          command: vals.command || '',
          expected: vals.expected || '',
          condition: vals.condition || 'True',
          true_label: vals.true_label || '',
          false_label: vals.false_label || '',
          loop_type: vals.loop_type || 'for',
          variable: vals.loop_variable || 'i',
          entry_condition: vals.entry_condition || '',
          entry_fail_action: vals.entry_fail_action || 'skip',
          break_condition: vals.break_condition || '',
          max_iterations: vals.max_iterations || '',
          duration: vals.duration ?? 1000,
          device_id: vals.device_id || '',
          variables: vals.variables || [],
          inputs: nextInputs,
          outputs: nextOutputs,
        },
      }
      // 节点类型就地切换：不兼容字段保留在 config 中（切回可恢复）
      const nextType = vals.node_type || n.type
      if (nextType !== n.type) {
        const cfg = { ...(updated as any).config }
        if (n.type === 'condition' && nextType === 'loop') {
          // 判断 → 循环：条件表达式映射为循环条件（while）
          cfg.loop_type = 'while'
          cfg.variable = cfg.variable || 'i'
        } else if (n.type === 'loop' && nextType === 'condition') {
          // 循环 → 判断：循环条件映射为判断条件
          cfg.condition = cfg.condition || 'True'
        } else if (nextType === 'condition' || nextType === 'loop') {
          // 操作 ⇄ 判断/循环：命令字段保留，仅补齐目标类型所需字段
          cfg.condition = cfg.condition || 'True'
          if (nextType === 'loop') {
            cfg.loop_type = cfg.loop_type || 'for'
            cfg.variable = cfg.variable || 'i'
          }
        }
        ;(updated as any).config = cfg
        ;(updated as any).type = nextType
      }
      // For loops, store expression in condition
      if ((updated as any).type === 'loop' && vals.loop_expression) {
        (updated as any).config.condition = vals.loop_expression
      }
      return updated
    }))
    setEditOpen(false)
    message.success(t('msg.nodeUpdated'))
  }

  // ---- Delete selected nodes/edges ----
  const handleDelete = useCallback(() => {
    const selectedNodes = nodes.filter((n) => n.selected && n.type !== 'start' && n.type !== 'end' && n.type !== 'input' && n.type !== 'output')
    const selectedEdges = edges.filter((e) => e.selected)
    if (selectedNodes.length === 0 && selectedEdges.length === 0) {
      message.info(t('flow.deleteHint'))
      return
    }
    // Save snapshot before mutation
    pushHistory()
    const nodeIds = new Set(selectedNodes.map((n) => n.id))
    setNodes((nds) => nds.filter((n) => !nodeIds.has(n.id)))
    // FIXED: was e.selected (kept selected edges), now !e.selected (removes selected edges)
    setEdges((eds) => eds.filter((e) => !e.selected && !nodeIds.has(e.source) && !nodeIds.has(e.target)))
    message.success(`${t('msg.deleted')} ${selectedNodes.length} ${t('label.node')}}, ${selectedEdges.length} ${t('label.edge')}`)
  }, [nodes, edges, setNodes, setEdges])

  // ---- Drag-over from palette ----
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()
      const paletteType = event.dataTransfer.getData('application/reactflow-type')
      if (!paletteType || !reactFlowRef.current) return
      const position = reactFlowRef.current.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })
      const nid = newNodeId()
      const labelMap: Record<string, string> = {
        init: t('node.init'), action: t('label.newAction'), condition: t('label.judgeCondition'),
        loop: t('col.loop'), delay: t('node.delay'), end: t('node.end'),
      }
      const defaultDuration = 1000
      const newNode = {
        id: nid,
        type: paletteType,
        data: {
          label: labelMap[paletteType] || paletteType,
          duration: paletteType === 'delay' ? defaultDuration : undefined,
          inputs: [],
          outputs: [],
        },
        position,
        config: paletteType === 'condition'
          ? { condition: 'True', true_label: t('common.yes'), false_label: t('common.no') }
          : paletteType === 'loop'
            ? { loop_type: 'for', variable: 'i', condition: '3' }
            : paletteType === 'delay'
              ? { duration: defaultDuration }
              : { command: '', expected: '' },
      } as FlowNode
      pushHistory()
      setNodes((nds) => [...nds, newNode])
        message.info(`${t('msg.addedPrefix')}${labelMap[paletteType] || paletteType}」${t('unit.nodeShort')}`)
    },
    [setNodes, pushHistory],
  )

  // ---- Save flow ----
  /**
   * Persist the current canvas.
   *
   * @returns true only when the flow really reached the backend.  Callers that
   * depend on the stored revision (code generation) MUST check this: the
   * backend generates from what is in the database, so continuing after a
   * failed save would silently emit code for the *previous* revision.
   */
  const handleSaveFlow = async (): Promise<boolean> => {
    if (!id) return false
    try {
      await testCaseAPI.updateFlow(id, { nodes, edges })
    } catch (err: any) {
      if (err?.response?.status === 404) {
        // No flow stored for this test case yet — create it.
        try {
          await testCaseAPI.createFlow(id, { nodes, edges })
        } catch (err2) {
          handleApiError(err2, t('msg.saveFailed'))
          return false
        }
      } else {
        // 400 (validation) / 409 / 5xx: a genuine failure.  Treating it as
        // "flow missing" and falling back to create() used to mask the error
        // and leave the old revision in place.
        handleApiError(err, t('msg.saveFailed'))
        return false
      }
    }
    message.success(t('msg.flowSaved'))
    return true
  }

  // ---- Generate code ----
  const handleGenerateCode = async () => {
    if (!id) return
    setCodeDrawerOpen(true)
    setCodeLoading(true)
    setCodeText('')
    // Persist first — the backend reads the *stored* flow, so an unsaved edit
    // would otherwise regenerate the previous (unchanged) revision.
    const saved = await handleSaveFlow()
    if (!saved) {
      setCodeText(
        `# ${t('msg.genAborted')}\n`
        + `# ${t('flow.fixErrorsFirst')}`,
      )
      setCodeLoading(false)
      return
    }
    try {
      const res = await testCaseAPI.generateCode(id)
      const data: any = res.data?.data || res.data
      setCodeText(data?.code || '// No code generated')
    } catch (err) {
      setCodeText(`# Error generating code:\n# ${_errorMessage(err, t('msg.generateCodeFailed'))}`)
    } finally {
      setCodeLoading(false)
    }
  }

  // ---- Edge label editing on double-click ----
  const onEdgeDoubleClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    const label = prompt(t('ph.edgeLabel'), edge.label as string || '')
    if (label !== null) {
      pushHistory()
      setEdges((eds) => eds.map((e) => (e.id === edge.id ? { ...e, label } : e)))
    }
  }, [setEdges, pushHistory])

  // ---- Copy / Paste / Duplicate ----
  /** 深拷贝一组节点及其内部连线，生成新 id 并做位置偏移（避免完全重叠） */
  const cloneSelection = useCallback((srcNodes: Node[], srcEdges: Edge[]) => {
    const idMap: Record<string, string> = {}
    const copies = srcNodes.map((n) => {
      const nid = newNodeId()
      idMap[n.id] = nid
      return {
        ...JSON.parse(JSON.stringify(n)),
        id: nid,
        selected: true,
        position: { x: (n.position?.x || 0) + 40, y: (n.position?.y || 0) + 40 },
      } as Node
    })
    const newEdges = srcEdges.map((e) => ({
      ...JSON.parse(JSON.stringify(e)),
      id: newEdgeId(),
      source: idMap[e.source],
      target: idMap[e.target],
      selected: false,
    })) as Edge[]
    return { copies, newEdges }
  }, [])

  /** 选中节点（开始/结束节点不参与）及其内部连线 */
  const selectedCopyable = useCallback(() => {
    const picked = nodes.filter(
      (n) => n.selected && n.type !== 'start' && n.type !== 'end' && n.type !== 'input' && n.type !== 'output',
    )
    const ids = new Set(picked.map((n) => n.id))
    // 只保留两端都在选中集合内的内部连线，外部连线不复制
    const inner = edges.filter((e) => ids.has(e.source) && ids.has(e.target))
    return { picked, inner }
  }, [nodes, edges])

  const handleCopy = useCallback(() => {
    const { picked, inner } = selectedCopyable()
    if (picked.length === 0) {
      message.info(t('msg.pickNodeToCopy'))
      return
    }
    clipboardRef.current = {
      nodes: JSON.parse(JSON.stringify(picked)),
      edges: JSON.parse(JSON.stringify(inner)),
    }
    message.success(`${t('msg.copied')} ${picked.length} ${t('unit.nodes')}`)
  }, [selectedCopyable])

  const handlePaste = useCallback(() => {
    const clip = clipboardRef.current
    if (!clip || clip.nodes.length === 0) {
      message.info(t('msg.clipboardEmpty'))
      return
    }
    pushHistory()
    const { copies, newEdges } = cloneSelection(clip.nodes, clip.edges)
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...copies])
    setEdges((eds) => [...eds, ...newEdges])
    message.success(`${t('msg.pasted')} ${copies.length} ${t('label.count')}}${t('label.node')}`)
  }, [cloneSelection, pushHistory, setNodes, setEdges])

  const handleDuplicate = useCallback(() => {
    const { picked, inner } = selectedCopyable()
    if (picked.length === 0) {
      message.info(t('msg.pickNodeToDuplicate'))
      return
    }
    pushHistory()
    const { copies, newEdges } = cloneSelection(picked, inner)
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...copies])
    setEdges((eds) => [...eds, ...newEdges])
    message.success(`${t('msg.created')} ${copies.length} ${t('unit.copies')}`)
  }, [cloneSelection, selectedCopyable, pushHistory, setNodes, setEdges])

  // ---- Keyboard shortcuts ----
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      const isMod = e.ctrlKey || e.metaKey
      if ((e.key === 'Delete' || e.key === 'Backspace') && !isMod) {
        handleDelete()
      }
      if (isMod && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      }
      if (isMod && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault()
        redo()
      }
      if (isMod && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault()
        handleCopy()
      }
      if (isMod && (e.key === 'v' || e.key === 'V')) {
        e.preventDefault()
        handlePaste()
      }
      if (isMod && (e.key === 'd' || e.key === 'D')) {
        e.preventDefault()
        handleDuplicate()
      }
      if (e.key === 'Escape') {
        setFullscreen(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleDelete, undo, redo, handleCopy, handlePaste, handleDuplicate])

  // ---- Render ----
  return (
    <div
      className="page-container"
      style={fullscreen ? {
        // 全屏：脱离页面布局铺满视口，Esc 退出。
        // Background follows the theme — a hard-coded white became a white
        // island the moment dark mode landed (issue #22).
        position: 'fixed', inset: 0, zIndex: 1200, background: 'var(--flow-canvas-bg)',
        padding: 16, display: 'flex', flexDirection: 'column',
      } : {
        height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column',
      }}
    >
      <Breadcrumb
        items={[
          { title: <a onClick={() => navigate('/')}><HomeOutlined />{t('nav.home')}</a> },
          { title: <a onClick={() => navigate('/testcases')}>{t('col.testCase')}</a> },
          { title: testCase?.name || t('page.flowEditor') },
        ]}
        style={{ marginBottom: 8 }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/testcases')}>{t('common.back')}</Button>
          <Title level={4} style={{ margin: 0 }}>{testCase?.name || t('page.flowEditor')}</Title>
          <Tag color="processing">{nodes.length} {t('unit.nodeShort')}</Tag>
          <Tag>{edges.length} {t('label.edge')}</Tag>
        </Space>
        <Space wrap>
          {/* ① t('group.history') */}
          <Tooltip title={t('tip.undo')}>
            <Button icon={<UndoOutlined />} disabled={!canUndo} onClick={undo}>{t('common.undo')}</Button>
          </Tooltip>
          <Tooltip title={t('tip.redo')}>
            <Button icon={<RedoOutlined />} disabled={!canRedo} onClick={redo}>{t('common.redo')}</Button>
          </Tooltip>
          <Divider type="vertical" />
          {/* ② Edit */}
          <Tooltip title={t('tip.copyNode')}>
            <Button icon={<CopyOutlined />} onClick={handleCopy}>{t('common.copy')}</Button>
          </Tooltip>
          <Tooltip title={t('tip.pasteNode')}>
            <Button icon={<SnippetsOutlined />} onClick={handlePaste}>{t('common.paste')}</Button>
          </Tooltip>
          <Tooltip title={t('tip.duplicateNode')}>
            <Button icon={<DiffOutlined />} onClick={handleDuplicate}>{t('btn.duplicate')}</Button>
          </Tooltip>
          <Divider type="vertical" />
          {/* ③ Destructive — isolated so it can never be hit by accident */}
          <Tooltip title={t('btn.deleteSelectedShort')}>
            <Button icon={<DeleteOutlined />} danger onClick={handleDelete}>{t('btn.deleteSelected')}</Button>
          </Tooltip>
          <Divider type="vertical" />
          {/* ④ t('group.view') */}
          <Tooltip title={fullscreen ? t('tip.exitFullscreen') : t('tip.fullscreen')}>
            <Button
              icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={() => setFullscreen(v => !v)}
            >
              {fullscreen ? t('btn.exitFullscreen') : t('btn.fullscreen')}
            </Button>
          </Tooltip>
          <Divider type="vertical" />
          {/* ⑤ Commit — save / generate code. "Generate code" used to be purple,
              a hue the palette does not define; both now share the primary colour. */}
          <Button icon={<SaveOutlined />} type="primary" onClick={handleSaveFlow}>{t('btn.saveFlow')}</Button>
          <Button
            icon={<CodeOutlined />}
            onClick={handleGenerateCode}
            loading={codeLoading}
          >{t('btn.generateCode')}</Button>
        </Space>
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, gap: 0 }}>
        {/* ---- Node palette sidebar ---- */}
        <div style={{
          // 120 was too narrow for the icon + label; 148 also gives the drag
          // chips room to breathe (issue #22).
          width: 148, minWidth: 148, background: 'var(--flow-panel-bg)',
          borderRight: '1px solid var(--flow-panel-border)', padding: 12,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <Text strong style={{ fontSize: 12, color: 'var(--flow-panel-fg)', marginBottom: 4 }}>{t('card.nodePalette')}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{t('tip.dragToCanvas')}</Text>
          {PALETTE(t).map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('application/reactflow-type', item.type)
                e.dataTransfer.effectAllowed = 'move'
              }}
              className="flow-palette-chip"
              style={{
                padding: '8px 10px',
                ...paletteChipStyle(item.kind),
                cursor: 'grab', fontSize: 12, fontWeight: 500,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                userSelect: 'none',
              }}
            >
              {item.kind === 'diamond' && (
                <span
                  aria-hidden
                  style={{
                    width: 9, height: 9, flex: '0 0 9px',
                    background: 'currentColor', opacity: 0.85,
                    transform: 'rotate(45deg)', borderRadius: 1,
                  }}
                />
              )}
              {item.icon} {item.label}
            </div>
          ))}
        </div>

        {/* ---- Flow canvas ---- */}
        <Card bodyStyle={{ padding: 0, height: '100%' }} style={{ flex: 1 }}>
          <ReactFlow
            nodes={displayNodes}
            edges={displayEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeDoubleClick={onNodeDoubleClick}
            onEdgeDoubleClick={onEdgeDoubleClick}
            onDragOver={onDragOver}
            onDrop={onDrop}
            onInit={(instance) => { reactFlowRef.current = instance }}
            nodeTypes={nodeTypes as any}
            connectionMode={ConnectionMode.Loose}
            fitView
            deleteKeyCode={['Delete', 'Backspace']}
            multiSelectionKeyCode="Shift"
            style={{ height: '100%' }}
          >
            <Controls />
            <MiniMap />
            <Background gap={20} color="var(--flow-grid)" />
          </ReactFlow>
        </Card>
      </div>

      {/* ---- Node edit modal ---- */}
      <Modal
        title={editNode ? `${t('common.edit')} ${(editNode as any)?.data?.label || t('label.node')}` : t('dlg.editNode')}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEditSave}
        width={760}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="label" label={t('label.nodeName')}>
            <Input />
          </Form.Item>
          <Form.Item name="node_type" label={t('label.nodeType')}
            extra={t('flow.switchTypeNote')}>
            <Select options={[
              { label: t('node.actionLong'), value: 'action' },
              { label: t('node.conditionLong'), value: 'condition' },
              { label: t('node.loopLong'), value: 'loop' },
              { label: t('node.initLong'), value: 'init' },
              { label: t('node.delayLong'), value: 'delay' },
              { label: t('node.end'), value: 'end' },
            ]} />
          </Form.Item>
          {['action', 'loop', 'delay'].includes(nodeType) && (
            <Form.Item name="device_id" label={t('label.execDevice')}
              extra={t('flow.pinDeviceHint')}>
              <Select allowClear placeholder={t('label.autoSelect')}
                options={devices.map((d: any) => ({ value: d.id, label: `${d.name} (${d.protocol})` }))} />
            </Form.Item>
          )}
          {nodeType === 'delay' && (
            <Form.Item name="duration" label={t('label.delayDuration')}
              extra={t('flow.delayFull')}>
              <InputNumber min={0} step={100} style={{ width: '100%' }} addonAfter="ms" />
            </Form.Item>
          )}
          {nodeType === 'init' && (
            <Form.Item label={t('label.variableDefs')}
              extra={t('flow.initDesc')}>
              <Form.List name="variables">
                {(fields, { add, remove, move }) => (
                  <>
                    {fields.map((field) => (
                      <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 4 }} wrap>
                        <Form.Item {...field} name={[field.name, 'name']}
                          rules={[{ required: true, message: t('msg.varNameRequired') }]}>
                          <Input placeholder={t('label.varName')} style={{ width: 110 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'type']} initialValue="int">
                          <Select style={{ width: 92 }} options={[
                            { label: t('dtype.int'), value: 'int' },
                            { label: t('dtype.float'), value: 'float' },
                            { label: t('dtype.string'), value: 'string' },
                            { label: t('dtype.bool'), value: 'bool' },
                            { label: t('dtype.hex'), value: 'hex' },
                          ]} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'value']}>
                          <Input placeholder={t('label.initialValue')} style={{ width: 110 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'desc']}>
                          <Input placeholder={t('label.notesOptional')} style={{ width: 120 }} />
                        </Form.Item>
                        <Tooltip title={t('common.moveUp')}>
                          <Button size="small" type="text" onClick={() => move(field.name, field.name - 1)}
                            disabled={field.name === 0}>↑</Button>
                        </Tooltip>
                        <Tooltip title={t('common.delete')}>
                          <Button size="small" type="text" icon={<DeleteOutlined />}
                            onClick={() => remove(field.name)} />
                        </Tooltip>
                      </Space>
                    ))}
                    <Button type="dashed" block icon={<PlusOutlined />}
                      onClick={() => add({ name: '', type: 'int', value: '', desc: '' })}>{t('btn.addVariable')}</Button>
                  </>
                )}
              </Form.List>
            </Form.Item>
          )}
          {nodeType === 'action' && (
            <>
              <Form.Item name="command" label={t('label.command')}>
                <Input.TextArea rows={2} placeholder={t('label.commandSent')} />
              </Form.Item>
              <Form.Item name="expected" label={t('col.expected')}>
                <Input placeholder={t('label.expectedReturn')} />
              </Form.Item>
            </>
          )}
          {nodeType === 'condition' && (
            <>
              <Form.Item name="condition" label={t('label.conditionExpr')} rules={[{ required: true }]}
                extra={t('flow.exprFull2')}>
                <Input placeholder="voltage > 10" />
              </Form.Item>
              <Form.Item name="true_label" label={t('label.trueBranch')}>
                <Input placeholder={t('common.yes')} />
              </Form.Item>
              <Form.Item name="false_label" label={t('label.falseBranch')}>
                <Input placeholder={t('common.no')} />
              </Form.Item>
            </>
          )}
          {nodeType === 'loop' && (
            <>
              <Form.Item name="loop_type" label={t('label.loopType')} rules={[{ required: true }]}>
                <Select options={[{ label: t('loop.for'), value: 'for' }, { label: t('loop.while'), value: 'while' }]} />
              </Form.Item>
              {loopType !== 'while' && (
                <Form.Item name="loop_variable" label={t('label.loopVar')}>
                  <Input placeholder="i" />
                </Form.Item>
              )}
              <Form.Item
                name="loop_expression"
                label={loopType === 'while' ? t('label.loopCondition') : t('label.loopCountCondition')}
                rules={[{ required: true }]}
                extra={loopType === 'while'
                  ? `Python ${t('ph.loopCondition')}_count < 10`
                  : `for: ${t('ph.loopCountOrWhile')}}`}
              >
                <Input placeholder={loopType === 'while' ? 'retry_count < 10' : '3'} />
              </Form.Item>

          {/* The loop node's own command / expected result (same shape as an action node) */}
              <Form.Item name="command" label={t('label.commandEachRound')}
                extra={t('flow.loopEmptyHint')}>
                <Input.TextArea rows={2} placeholder={t('flow.commandFull')} />
              </Form.Item>
              <Form.Item name="expected" label={t('label.expectedOptional')}
                extra={t('flow.assertHint')}>
                <Input placeholder={t('label.expectedReturn')} />
              </Form.Item>

              {loopType === 'while' && (
                <>
                  <Form.Item name="entry_condition" label={t('label.enterCondition')}
                    extra={t('flow.alwaysEnterFull')}>
                    <Input placeholder="device_ready == True" />
                  </Form.Item>
                  <Form.Item name="entry_fail_action" label={t('label.entryFalse')}>
                    <Select options={[
                      { label: t('onError.skipLoop'), value: 'skip' },
                      { label: t('onError.fail'), value: 'fail' },
                    ]} />
                  </Form.Item>
                  <Form.Item name="break_condition" label={t('label.breakCondition')}
                    extra={t('flow.breakFull')}>
                    <Input placeholder="response == 'OK'" />
                  </Form.Item>
                  <Form.Item name="max_iterations" label={t('label.maxIterations')}
                    extra={t('flow.maxIterHint')}>
                    <Input placeholder="10" />
                  </Form.Item>
                </>
              )}
            </>
          )}

          {/* ---- Issue #4: inputs / outputs (shared by every editable node) ---- */}
          <Divider style={{ margin: '4px 0 8px' }} />
          <Collapse
            size="small"
            ghost
            items={[
              {
                key: 'io',
                label: <Text strong style={{ fontSize: 13 }}>
                  {t('label.io')}
                  {((editNode as any)?.config?.inputs?.length ||
                    (editNode as any)?.config?.outputs?.length)
                    ? <Tag style={{ marginLeft: 8 }}>
                        in {(editNode as any)?.config?.inputs?.length || 0} · out {(editNode as any)?.config?.outputs?.length || 0}
                      </Tag>
                    : null}
                </Text>,
                children: (
                  <>
                    <div style={{ marginBottom: 10 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>{t('label.availableVars')}</Text>
                      <div style={{ marginTop: 4 }}>
                        {flowVars.length === 0 ? (
                          <Text type="secondary" style={{ fontSize: 12 }}>{t('flow.noVars')}</Text>
                        ) : flowVars.map((v) => (
                          <Tag
                            key={v.name}
                            style={{ cursor: 'pointer', marginBottom: 4 }}
                            onClick={() => {
                              navigator.clipboard.writeText(`{${v.name}}`)
      message.success(`${t('msg.copiedVar')} {${v.name}}`)
                            }}
                          >
                            {`{${v.name}}`} ← {v.source_label}
                          </Tag>
                        ))}
                      </div>
                    </div>

                    <Form.Item label={t('label.inputs')}
                      extra={t('flow.varResolveHint')}>
                      <Form.List name="inputs">
                        {(fields, { add, remove }) => (
                          <>
                            {fields.map((field) => (
                              <Space key={field.key} align="baseline"
                                style={{ display: 'flex', marginBottom: 4 }} wrap>
                                <Form.Item {...field} name={[field.name, 'name']}
                                  rules={[{ required: true, message: t('msg.paramNameRequired') }]}>
                                  <Input placeholder={t('label.paramName')} style={{ width: 110 }} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'type']} initialValue="string">
                                  <Select style={{ width: 92 }} options={VALUE_TYPE_OPTIONS(t)} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'default']}>
                                  <Input placeholder={t('label.defaultValue')} style={{ width: 110 }} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'desc']}>
                                  <Input placeholder={t('label.notesOptional')} style={{ width: 110 }} />
                                </Form.Item>
                                <Tooltip title={t('common.delete')}>
                                  <Button size="small" type="text" icon={<DeleteOutlined />}
                                    onClick={() => remove(field.name)} />
                                </Tooltip>
                              </Space>
                            ))}
                            <Button type="dashed" block size="small" icon={<PlusOutlined />}
                              onClick={() => add({ name: '', type: 'string', default: '', desc: '' })}>{t('btn.addInput')}</Button>
                          </>
                        )}
                      </Form.List>
                    </Form.Item>

                    <Form.Item label={t('label.outputValue')}
                      extra={t('flow.exprFull')}>
                      <Form.List name="outputs">
                        {(fields, { add, remove }) => (
                          <>
                            {fields.map((field) => (
                              <Space key={field.key} align="baseline"
                                style={{ display: 'flex', marginBottom: 4 }} wrap>
                                <Form.Item {...field} name={[field.name, 'name']}
                                  rules={[{ required: true, message: t('msg.outputNameRequired') }]}>
                                  <Input placeholder={t('label.outputName')} style={{ width: 110 }} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'type']} initialValue="string">
                                  <Select style={{ width: 92 }} options={VALUE_TYPE_OPTIONS(t)} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'value']}>
                                  <Input placeholder="response" style={{ width: 130 }} />
                                </Form.Item>
                                <Form.Item {...field} name={[field.name, 'desc']}>
                                  <Input placeholder={t('label.notesOptional')} style={{ width: 110 }} />
                                </Form.Item>
                                <Tooltip title={t('common.delete')}>
                                  <Button size="small" type="text" icon={<DeleteOutlined />}
                                    onClick={() => remove(field.name)} />
                                </Tooltip>
                              </Space>
                            ))}
                            <Button type="dashed" block size="small" icon={<PlusOutlined />}
                              onClick={() => add({ name: '', type: 'string', value: 'response', desc: '' })}>{t('btn.addOutput')}</Button>
                          </>
                        )}
                      </Form.List>
                    </Form.Item>

                    <Text type="secondary" style={{ fontSize: 12 }}>{t('flow.refHint')}<code>{`${t('label.varName')}}`}</code> {t('label.thenReference')}
                      {t('parser.sameRules')}
                    </Text>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      {/* ---- Code generation drawer ---- */}
      <Drawer
        title={(
          <>
            {t('dlg.generatedCode')}{' '}
            {/* 生成中 = 运行中（琥珀）；就绪 = 中性。紫/青/蓝等 AntD 预设色
                不受主题控制，已全部移除。 */}
            {codeLoading
              ? <Tag style={{ color: 'var(--a-fg)', borderColor: 'var(--a-fg)', background: 'transparent' }}>{t('label.generating')}...</Tag>
              : <Tag>{t('label.ready')}</Tag>}
          </>
        )}
        open={codeDrawerOpen}
        onClose={() => setCodeDrawerOpen(false)}
        width={640}
        extra={
          <Button
            type="primary"
            icon={<CodeOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(codeText)
              message.success(t('msg.codeCopied'))
            }}
          >{t('btn.copyCode')}</Button>
        }
      >
        <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
          {t('label.testCaseColon')}{testCase?.name} &nbsp;|&nbsp; {nodes.length} {t('label.node')}, {edges.length} {t('label.edge')}
        </Text>
        <Divider style={{ margin: '8px 0' }} />
        <pre style={{
          // 曾写死 VSCode 深色，浅色主题下很突兀；现跟随主题t('label.variable')。
          background: 'var(--flow-code-bg)', color: 'var(--flow-code-fg)', padding: 16,
          borderRadius: 6, fontSize: 13, fontFamily: 'Consolas, Monaco, monospace',
          overflow: 'auto', maxHeight: 'calc(100vh - 220px)', lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
        }}>
            {codeText || `// 点击「${t('btn.generateCode')}」按钮${t('btn.generate')}...`}
        </pre>
      </Drawer>
    </div>
  )
}
