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
  DeleteOutlined,
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

// ---------------------------------------------------------------------------
// Node types registry
// ---------------------------------------------------------------------------

const nodeTypes = {
  start: StartNode,
  end: EndNode,
  action: ActionNode,
  condition: ConditionNode,
  loop: LoopNode,
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

  // Code generation
  const [codeDrawerOpen, setCodeDrawerOpen] = useState(false)
  const [codeText, setCodeText] = useState('')
  const [codeLoading, setCodeLoading] = useState(false)

  const reactFlowRef = useRef<ReactFlowInstance | null>(null)

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
    (connection: Connection) => setEdges((eds) => addEdge({
      ...connection,
      id: newEdgeId(),
      label: '',
    }, eds)),
    [setEdges],
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
    })
    setEditOpen(true)
  }, [editForm])

  // ---- Save node edit ----
  const handleEditSave = () => {
    const vals = editForm.getFieldsValue()
    if (!editNode) return
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
        },
      }
      // For loops, store expression in condition
      if (n.type === 'loop' && vals.loop_expression) {
        (updated as any).config.condition = vals.loop_expression
      }
      return updated
    }))
    setEditOpen(false)
    message.success('节点已更新')
  }

  // ---- Delete selected nodes/edges ----
  const handleDelete = () => {
    const selectedNodes = nodes.filter((n) => n.selected && n.type !== 'start' && n.type !== 'end' && n.type !== 'input' && n.type !== 'output')
    const selectedEdges = edges.filter((e) => e.selected)
    if (selectedNodes.length === 0 && selectedEdges.length === 0) {
      message.info('选中节点或边后按 Delete 删除（开始/结束节点不可删）')
      return
    }
    const nodeIds = new Set(selectedNodes.map((n) => n.id))
    setNodes((nds) => nds.filter((n) => !nodeIds.has(n.id)))
    setEdges((eds) => eds.filter((e) => e.selected || (!nodeIds.has(e.source) && !nodeIds.has(e.target))))
    message.success(`已删除 ${selectedNodes.length} 节点, ${selectedEdges.length} 边`)
  }

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
      const labelMap: Record<string, string> = { action: '新操作', condition: '判断条件', loop: '循环', end: '结束' }
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
      setNodes((nds) => [...nds, newNode])
      message.info(`已添加「${labelMap[paletteType] || paletteType}」节点`)
    },
    [setNodes],
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
      setEdges((eds) => eds.map((e) => (e.id === edge.id ? { ...e, label } : e)))
    }
  }, [setEdges])

  // ---- Keyboard shortcuts ----
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Delete' || e.key === 'Backspace') {
        // Let ReactFlow handle selection first; we handle in handleDelete button
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

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
          {editNode?.type === 'action' && (
            <>
              <Form.Item name="command" label="执行命令">
                <Input.TextArea rows={2} placeholder="发送到设备的命令" />
              </Form.Item>
              <Form.Item name="expected" label="预期结果">
                <Input placeholder="预期返回值" />
              </Form.Item>
            </>
          )}
          {editNode?.type === 'condition' && (
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
          {editNode?.type === 'loop' && (
            <>
              <Form.Item name="loop_type" label="循环类型" rules={[{ required: true }]}>
                <Select options={[{ label: 'for (固定次数)', value: 'for' }, { label: 'while (条件循环)', value: 'while' }]} />
              </Form.Item>
              {editForm.getFieldValue('loop_type') !== 'while' && (
                <Form.Item name="loop_variable" label="循环变量">
                  <Input placeholder="i" />
                </Form.Item>
              )}
              <Form.Item name="loop_expression" label="循环次数/条件" rules={[{ required: true }]}
                extra="for: 循环次数 (整数); while: Python 条件表达式">
                <Input placeholder="3" />
              </Form.Item>
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
