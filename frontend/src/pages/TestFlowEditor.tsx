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
import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactFlow, {
  Node, Edge, Controls, Background,
  MiniMap, useNodesState, useEdgesState,
  addEdge, Connection, NodeProps, Handle, Position,
  ConnectionMode, ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  Card, Button, Space, message, Typography, Modal, Input, Form,
  Select, Tag, Breadcrumb, Drawer, Tooltip, Divider,
} from 'antd'
import {
  SaveOutlined, ArrowLeftOutlined, PlusOutlined,
  PlayCircleOutlined, HomeOutlined, CodeOutlined,
  BranchesOutlined, SyncOutlined, ThunderboltOutlined,
  DeleteOutlined, DatabaseOutlined,
} from '@ant-design/icons'
import { testCaseAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import type { TestCase } from '../types'

const { Title, Text } = Typography

// Extend ReactFlow Node to carry custom config per node type
interface FlowNode extends Node {
  config?: Record<string, any>
}

// ---------------------------------------------------------------------------
// Custom node components
// ---------------------------------------------------------------------------

function StartNode({ data }: NodeProps) {
  return (
    <div style={{
      padding: '8px 20px', borderRadius: 20,
      background: '#52c41a', color: '#fff', fontWeight: 600,
      fontSize: 13, minWidth: 100, textAlign: 'center', border: '2px solid #389e0d',
    }}>
      {data.label}
      <Handle type="source" position={Position.Bottom} style={{ background: '#389e0d' }} />
    </div>
  )
}

function EndNode({ data }: NodeProps) {
  return (
    <div style={{
      padding: '8px 20px', borderRadius: 20,
      background: '#ff4d4f', color: '#fff', fontWeight: 600,
      fontSize: 13, minWidth: 100, textAlign: 'center', border: '2px solid #cf1322',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#cf1322' }} />
      {data.label}
    </div>
  )
}

function ActionNode({ data }: NodeProps) {
  return (
    <div style={{
      padding: '10px 18px', borderRadius: 6,
      background: '#1677ff', color: '#fff', fontWeight: 500,
      fontSize: 12, minWidth: 140, textAlign: 'center',
      border: '2px solid #0958d9', wordBreak: 'break-word',
    }}>
      <Handle type="target" position={Position.Top} style={{ background: '#0958d9' }} />
      {data.label}
      <Handle type="source" position={Position.Bottom} style={{ background: '#0958d9' }} />
    </div>
  )
}

function ConditionNode({ data, selected }: NodeProps) {
  return (
    <div style={{
      width: 140, height: 70, position: 'relative',
    }}>
      {/* Diamond shape */}
      <svg width="140" height="70" style={{ position: 'absolute', top: 0, left: 0 }}>
        <polygon
          points="70,2 138,35 70,68 2,35"
          fill={selected ? '#faad14' : '#ffc53d'}
          stroke="#d48806" strokeWidth="2"
        />
      </svg>
      <div style={{
        position: 'relative', zIndex: 2, width: 140, height: 70,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 11, fontWeight: 600, color: '#333', textAlign: 'center',
        padding: '0 30px', lineHeight: 1.3,
      }}>
        {data.label}
      </div>
      <Handle type="target" position={Position.Top}
        style={{ background: '#d48806', top: 0, left: '50%' }} />
      <Handle type="source" position={Position.Bottom} id="s-true"
        style={{ background: '#52c41a', bottom: -2, left: '30%' }} />
      <Handle type="source" position={Position.Bottom} id="s-false"
        style={{ background: '#ff4d4f', bottom: -2, left: '70%' }} />
    </div>
  )
}

function LoopNode({ data, selected }: NodeProps) {
  return (
    <div style={{
      padding: '10px 18px', borderRadius: 6,
      background: selected ? '#722ed1' : '#9254de',
      color: '#fff', fontWeight: 600, fontSize: 12, minWidth: 140,
      textAlign: 'center', border: '2px solid #531dab',
      display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
    }}>
      <SyncOutlined style={{ fontSize: 14 }} />
      <Handle type="target" position={Position.Top} style={{ background: '#531dab' }} />
      {data.label}
      <Handle type="source" position={Position.Bottom} style={{ background: '#531dab' }} />
    </div>
  )
}

/** 初始化 / 重置节点：集中声明变量，供后续节点引用 */
function InitNode({ data, selected }: NodeProps) {
  const vars: any[] = (data as any)?.variables || []
  return (
    <div style={{
      padding: '10px 18px', borderRadius: 6,
      background: selected ? '#08979c' : '#13c2c2',
      color: '#fff', fontWeight: 600, fontSize: 12, minWidth: 140,
      textAlign: 'center', border: '2px solid #006d75',
      display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'center',
    }}>
      <DatabaseOutlined style={{ fontSize: 14 }} />
      <Handle type="target" position={Position.Top} style={{ background: '#006d75' }} />
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
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: '#006d75' }} />
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
  color: string
  icon: React.ReactNode
}

const PALETTE: PaletteItem[] = [
  { type: 'init', label: '初始化', color: '#13c2c2', icon: <DatabaseOutlined /> },
  { type: 'action', label: '操作', color: '#1677ff', icon: <ThunderboltOutlined /> },
  { type: 'condition', label: '判断', color: '#faad14', icon: <BranchesOutlined /> },
  { type: 'loop', label: '循环', color: '#9254de', icon: <SyncOutlined /> },
  { type: 'end', label: '结束', color: '#ff4d4f', icon: <PlayCircleOutlined /> },
]

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

let _nodeIdCounter = 0
function newNodeId(): string { _nodeIdCounter++; return `user_node_${_nodeIdCounter}_${Date.now()}` }
function newEdgeId(): string { return `user_edge_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` }

export default function TestFlowEditor() {
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

  // Code generation
  const [codeDrawerOpen, setCodeDrawerOpen] = useState(false)
  const [codeText, setCodeText] = useState('')
  const [codeLoading, setCodeLoading] = useState(false)

  const reactFlowRef = useRef<ReactFlowInstance | null>(null)

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
        { id: 'start', type: 'start', data: { label: '开始' }, position: { x: 400, y: 0 } },
        { id: 'end', type: 'end', data: { label: '结束' }, position: { x: 400, y: 400 } },
      ])
      setEdges([])
    } catch (err) {
      handleApiError(err, '加载测试用例失败')
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
      node_type: node.type || 'action',
      variables: config.variables || [],
      entry_condition: config.entry_condition || '',
      entry_fail_action: config.entry_fail_action || 'skip',
      break_condition: config.break_condition || '',
      max_iterations: config.max_iterations || '',
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
      const updated = {
        ...n,
        data: { ...n.data, label: vals.label || n.data?.label },
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
          variables: vals.variables || [],
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
    message.success('节点已更新')
  }

  // ---- Delete selected nodes/edges ----
  const handleDelete = useCallback(() => {
    const selectedNodes = nodes.filter((n) => n.selected && n.type !== 'start' && n.type !== 'end' && n.type !== 'input' && n.type !== 'output')
    const selectedEdges = edges.filter((e) => e.selected)
    if (selectedNodes.length === 0 && selectedEdges.length === 0) {
      message.info('选中节点或边后按 Delete 删除（开始/结束节点不可删）')
      return
    }
    // Save snapshot before mutation
    pushHistory()
    const nodeIds = new Set(selectedNodes.map((n) => n.id))
    setNodes((nds) => nds.filter((n) => !nodeIds.has(n.id)))
    // FIXED: was e.selected (kept selected edges), now !e.selected (removes selected edges)
    setEdges((eds) => eds.filter((e) => !e.selected && !nodeIds.has(e.source) && !nodeIds.has(e.target)))
    message.success(`已删除 ${selectedNodes.length} 节点, ${selectedEdges.length} 边`)
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
      const labelMap: Record<string, string> = { init: '初始化', action: '新操作', condition: '判断条件', loop: '循环', end: '结束' }
      const newNode = {
        id: nid,
        type: paletteType,
        data: { label: labelMap[paletteType] || paletteType },
        position,
        config: paletteType === 'condition'
          ? { condition: 'True', true_label: '是', false_label: '否' }
          : paletteType === 'loop'
            ? { loop_type: 'for', variable: 'i', condition: '3' }
            : { command: '', expected: '' },
      } as FlowNode
      pushHistory()
      setNodes((nds) => [...nds, newNode])
      message.info(`已添加「${labelMap[paletteType] || paletteType}」节点`)
    },
    [setNodes, pushHistory],
  )

  // ---- Save flow ----
  const handleSaveFlow = async () => {
    if (!id) return
    try {
      // Try PUT first (update existing), fallback to POST (create)
      try {
        await testCaseAPI.updateFlow(id, { nodes, edges })
      } catch {
        await testCaseAPI.createFlow(id, { nodes, edges })
      }
      message.success('流程图已保存')
    } catch (err) {
      handleApiError(err, '保存失败')
    }
  }

  // ---- Generate code ----
  const handleGenerateCode = async () => {
    if (!id) return
    // Save first
    await handleSaveFlow()
    setCodeLoading(true)
    setCodeDrawerOpen(true)
    try {
      const res = await testCaseAPI.generateCode(id)
      const data: any = res.data?.data || res.data
      setCodeText(data?.code || '// No code generated')
    } catch (err) {
      setCodeText(`# Error generating code:\n# ${(err as any)?.message || err}`)
    } finally {
      setCodeLoading(false)
    }
  }

  // ---- Edge label editing on double-click ----
  const onEdgeDoubleClick = useCallback((_event: React.MouseEvent, edge: Edge) => {
    const label = prompt('输入边的标签（如 true / false / exit）：', edge.label as string || '')
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
      message.info('请先选中要复制的节点（开始/结束节点不可复制）')
      return
    }
    clipboardRef.current = {
      nodes: JSON.parse(JSON.stringify(picked)),
      edges: JSON.parse(JSON.stringify(inner)),
    }
    message.success(`已复制 ${picked.length} 个节点`)
  }, [selectedCopyable])

  const handlePaste = useCallback(() => {
    const clip = clipboardRef.current
    if (!clip || clip.nodes.length === 0) {
      message.info('剪贴板为空，请先复制节点')
      return
    }
    pushHistory()
    const { copies, newEdges } = cloneSelection(clip.nodes, clip.edges)
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...copies])
    setEdges((eds) => [...eds, ...newEdges])
    message.success(`已粘贴 ${copies.length} 个节点`)
  }, [cloneSelection, pushHistory, setNodes, setEdges])

  const handleDuplicate = useCallback(() => {
    const { picked, inner } = selectedCopyable()
    if (picked.length === 0) {
      message.info('请先选中要创建副本的节点')
      return
    }
    pushHistory()
    const { copies, newEdges } = cloneSelection(picked, inner)
    setNodes((nds) => [...nds.map((n) => ({ ...n, selected: false })), ...copies])
    setEdges((eds) => [...eds, ...newEdges])
    message.success(`已创建 ${copies.length} 个副本`)
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
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleDelete, undo, redo, handleCopy, handlePaste, handleDuplicate])

  // ---- Render ----
  return (
    <div className="page-container" style={{ height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column' }}>
      <Breadcrumb
        items={[
          { title: <a onClick={() => navigate('/')}><HomeOutlined /> 首页</a> },
          { title: <a onClick={() => navigate('/testcases')}>测试用例</a> },
          { title: testCase?.name || '流程图编辑' },
        ]}
        style={{ marginBottom: 8 }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/testcases')}>返回</Button>
          <Title level={4} style={{ margin: 0 }}>{testCase?.name || '流程图编辑'}</Title>
          <Tag color="blue">{nodes.length} 节点</Tag>
          <Tag color="green">{edges.length} 边</Tag>
        </Space>
        <Space wrap>
          <Tooltip title="撤销 Ctrl+Z">
            <Button icon={<ArrowLeftOutlined />} disabled={!canUndo} onClick={undo}>撤销</Button>
          </Tooltip>
          <Tooltip title="重做 Ctrl+Y">
            <Button icon={<ArrowLeftOutlined style={{ display: 'inline-block', transform: 'scaleX(-1)' }} />} disabled={!canRedo} onClick={redo}>重做</Button>
          </Tooltip>
          <Divider type="vertical" />
          <Tooltip title="选中节点或边后点击删除（开始/结束不可删）">
            <Button icon={<DeleteOutlined />} danger onClick={handleDelete}>删除选中</Button>
          </Tooltip>
          <Button icon={<SaveOutlined />} type="primary" onClick={handleSaveFlow}>保存流程图</Button>
          <Button
            icon={<CodeOutlined />}
            type="primary"
            style={{ background: '#722ed1', borderColor: '#722ed1' }}
            onClick={handleGenerateCode}
            loading={codeLoading}
          >
            生成代码
          </Button>
        </Space>
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, gap: 0 }}>
        {/* ---- Node palette sidebar ---- */}
        <div style={{
          width: 120, minWidth: 120, background: '#fafafa',
          borderRight: '2px solid #e8e8e8', padding: 12,
          display: 'flex', flexDirection: 'column', gap: 8,
        }}>
          <Text strong style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>节点面板</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>拖拽到画布</Text>
          {PALETTE.map((item) => (
            <div
              key={item.type}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData('application/reactflow-type', item.type)
                e.dataTransfer.effectAllowed = 'move'
              }}
              style={{
                padding: '8px 10px', borderRadius: 6,
                background: item.color, color: '#fff',
                cursor: 'grab', fontSize: 12, fontWeight: 500,
                display: 'flex', alignItems: 'center', gap: 6,
                userSelect: 'none', opacity: 0.9,
              }}
            >
              {item.icon} {item.label}
            </div>
          ))}
        </div>

        {/* ---- Flow canvas ---- */}
        <Card bodyStyle={{ padding: 0, height: '100%' }} style={{ flex: 1 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
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
            <Background gap={20} color="#f0f0f0" />
          </ReactFlow>
        </Card>
      </div>

      {/* ---- Node edit modal ---- */}
      <Modal
        title={editNode ? `编辑 ${(editNode as any)?.data?.label || '节点'}` : '编辑节点'}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={handleEditSave}
        width={500}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="label" label="节点名称">
            <Input />
          </Form.Item>
          <Form.Item name="node_type" label="节点类型"
            extra="可就地切换类型；不兼容的字段会保留在配置中，切回后可恢复">
            <Select options={[
              { label: '操作（下发命令）', value: 'action' },
              { label: '判断（条件分支）', value: 'condition' },
              { label: '循环（for / while）', value: 'loop' },
              { label: '初始化（变量声明）', value: 'init' },
              { label: '结束', value: 'end' },
            ]} />
          </Form.Item>
          {nodeType === 'init' && (
            <Form.Item label="变量定义"
              extra="流程开始时集中声明变量；生成代码后可供后续节点的命令与条件表达式引用">
              <Form.List name="variables">
                {(fields, { add, remove, move }) => (
                  <>
                    {fields.map((field) => (
                      <Space key={field.key} align="baseline" style={{ display: 'flex', marginBottom: 4 }} wrap>
                        <Form.Item {...field} name={[field.name, 'name']}
                          rules={[{ required: true, message: '变量名必填' }]}>
                          <Input placeholder="变量名" style={{ width: 110 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'type']} initialValue="int">
                          <Select style={{ width: 92 }} options={[
                            { label: '整数', value: 'int' },
                            { label: '浮点', value: 'float' },
                            { label: '字符串', value: 'string' },
                            { label: '布尔', value: 'bool' },
                            { label: '十六进制', value: 'hex' },
                          ]} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'value']}>
                          <Input placeholder="初始值" style={{ width: 110 }} />
                        </Form.Item>
                        <Form.Item {...field} name={[field.name, 'desc']}>
                          <Input placeholder="说明(可选)" style={{ width: 120 }} />
                        </Form.Item>
                        <Tooltip title="上移">
                          <Button size="small" type="text" onClick={() => move(field.name, field.name - 1)}
                            disabled={field.name === 0}>↑</Button>
                        </Tooltip>
                        <Tooltip title="删除">
                          <Button size="small" type="text" icon={<DeleteOutlined />}
                            onClick={() => remove(field.name)} />
                        </Tooltip>
                      </Space>
                    ))}
                    <Button type="dashed" block icon={<PlusOutlined />}
                      onClick={() => add({ name: '', type: 'int', value: '', desc: '' })}>
                      添加变量
                    </Button>
                  </>
                )}
              </Form.List>
            </Form.Item>
          )}
          {nodeType === 'action' && (
            <>
              <Form.Item name="command" label="执行命令">
                <Input.TextArea rows={2} placeholder="发送到设备的命令" />
              </Form.Item>
              <Form.Item name="expected" label="预期结果">
                <Input placeholder="预期返回值" />
              </Form.Item>
            </>
          )}
          {nodeType === 'condition' && (
            <>
              <Form.Item name="condition" label="条件表达式" rules={[{ required: true }]}
                extra="Python 表达式，如 voltage > 10">
                <Input placeholder="voltage > 10" />
              </Form.Item>
              <Form.Item name="true_label" label="True 分支标签">
                <Input placeholder="是" />
              </Form.Item>
              <Form.Item name="false_label" label="False 分支标签">
                <Input placeholder="否" />
              </Form.Item>
            </>
          )}
          {nodeType === 'loop' && (
            <>
              <Form.Item name="loop_type" label="循环类型" rules={[{ required: true }]}>
                <Select options={[{ label: 'for (固定次数)', value: 'for' }, { label: 'while (条件循环)', value: 'while' }]} />
              </Form.Item>
              {loopType !== 'while' && (
                <Form.Item name="loop_variable" label="循环变量">
                  <Input placeholder="i" />
                </Form.Item>
              )}
              <Form.Item
                name="loop_expression"
                label={loopType === 'while' ? '循环条件（每轮开始前判断）' : '循环次数/条件'}
                rules={[{ required: true }]}
                extra={loopType === 'while'
                  ? 'Python 条件表达式，每轮开始前判断；成立才继续下一轮。例：retry_count < 10'
                  : 'for: 循环次数 (整数); while: Python 条件表达式'}
              >
                <Input placeholder={loopType === 'while' ? 'retry_count < 10' : '3'} />
              </Form.Item>

              {/* 循环节点自身的执行命令 / 预期结果（与操作节点保持一致） */}
              <Form.Item name="command" label="执行命令（每轮执行）"
                extra="留空则循环体内不下发命令，仅执行循环体子节点">
                <Input.TextArea rows={2} placeholder="发送到设备的命令，如 CAN1,SEND,0x850102" />
              </Form.Item>
              <Form.Item name="expected" label="预期结果（可选）"
                extra="填写后每轮对该命令的返回值做断言">
                <Input placeholder="预期返回值" />
              </Form.Item>

              {loopType === 'while' && (
                <>
                  <Form.Item name="entry_condition" label="进入条件（可选，循环开始前判断一次）"
                    extra="留空表示总是进入。例：device_ready == True">
                    <Input placeholder="device_ready == True" />
                  </Form.Item>
                  <Form.Item name="entry_fail_action" label="进入条件不满足时">
                    <Select options={[
                      { label: '跳过整个循环（继续后续节点）', value: 'skip' },
                      { label: '判定为失败（抛错终止）', value: 'fail' },
                    ]} />
                  </Form.Item>
                  <Form.Item name="break_condition" label="跳出条件（可选，每轮结束后判断）"
                    extra="成立则提前 break 退出循环。例：response == 'OK'">
                    <Input placeholder="response == 'OK'" />
                  </Form.Item>
                  <Form.Item name="max_iterations" label="最大迭代次数（可选）"
                    extra="防止条件恒真导致死循环；达到上限强制跳出并告警">
                    <Input placeholder="10" />
                  </Form.Item>
                </>
              )}
            </>
          )}
        </Form>
      </Modal>

      {/* ---- Code generation drawer ---- */}
      <Drawer
        title={<>生成的 Python 测试代码 <Tag color="purple">{codeLoading ? '生成中...' : '就绪'}</Tag></>}
        open={codeDrawerOpen}
        onClose={() => setCodeDrawerOpen(false)}
        width={640}
        extra={
          <Button
            type="primary"
            icon={<CodeOutlined />}
            onClick={() => {
              navigator.clipboard.writeText(codeText)
              message.success('代码已复制到剪贴板')
            }}
          >
            复制代码
          </Button>
        }
      >
        <Text type="secondary" style={{ marginBottom: 8, display: 'block' }}>
          测试用例：{testCase?.name} &nbsp;|&nbsp; {nodes.length} 节点, {edges.length} 边
        </Text>
        <Divider style={{ margin: '8px 0' }} />
        <pre style={{
          background: '#1e1e1e', color: '#d4d4d4', padding: 16,
          borderRadius: 6, fontSize: 13, fontFamily: 'Consolas, Monaco, monospace',
          overflow: 'auto', maxHeight: 'calc(100vh - 220px)', lineHeight: 1.6,
          whiteSpace: 'pre-wrap',
        }}>
          {codeText || '// 点击「生成代码」按钮生成...'}
        </pre>
      </Drawer>
    </div>
  )
}
