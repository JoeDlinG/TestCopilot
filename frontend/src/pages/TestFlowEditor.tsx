import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import ReactFlow, {
  Node, Edge, Controls, Background,
  MiniMap, useNodesState, useEdgesState,
  addEdge, Connection, NodeTypes,
} from 'reactflow'
import 'reactflow/dist/style.css'
import {
  Card, Button, Space, message, Typography, Modal, Input, Form,
  Select, Tag, Breadcrumb
} from 'antd'
import {
  SaveOutlined, ArrowLeftOutlined, PlusOutlined,
  PlayCircleOutlined, HomeOutlined
} from '@ant-design/icons'
import { testCaseAPI, executionAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'
import type { TestCase } from '../types'

const { Title, Text } = Typography

const initialNodes: Node[] = [
  {
    id: 'start',
    type: 'input',
    data: { label: '开始测试' },
    position: { x: 400, y: 0 },
    style: { background: '#52c41a', color: '#fff', border: 'none', width: 120 },
  },
]

const nodeTypes: NodeTypes = {}

export default function TestFlowEditor() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [testCase, setTestCase] = useState<TestCase | null>(null)
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [loading, setLoading] = useState(false)
  const [stepModalVisible, setStepModalVisible] = useState(false)
  const [selectedNode, setSelectedNode] = useState<Node | null>(null)
  const [stepForm] = Form.useForm()

  const loadTestCase = async () => {
    if (!id) return
    setLoading(true)
    try {
      const res = await testCaseAPI.get(id)
      const tc = extractData(res)
      setTestCase(tc)

      // Load flow data if exists
      if (tc?.flow_data?.nodes) {
        setNodes(tc.flow_data.nodes)
      } else if (tc?.steps?.length) {
        // Build flow from steps
        const stepNodes: Node[] = [{
          id: 'start',
          type: 'input',
          data: { label: '开始测试' },
          position: { x: 400, y: 0 },
          style: { background: '#52c41a', color: '#fff', border: 'none', width: 120 },
        }]

        const stepEdges: Edge[] = []

        tc.steps.forEach((step: any, index: number) => {
          const nodeId = `step_${step.step_number}`
          stepNodes.push({
            id: nodeId,
            type: 'default',
            data: { label: `${step.step_number}. ${step.action}` },
            position: { x: 400, y: 100 + index * 100 },
            style: { width: 200 },
          })
          const sourceId = index === 0 ? 'start' : `step_${tc.steps[index - 1].step_number}`
          stepEdges.push({
            id: `e_${sourceId}_${nodeId}`,
            source: sourceId,
            target: nodeId,
            animated: true,
          })
        })

        // Add end node
        const endId = 'end'
        stepNodes.push({
          id: endId,
          type: 'output',
          data: { label: '测试结束' },
          position: { x: 400, y: 100 + tc.steps.length * 100 },
          style: { background: '#ff4d4f', color: '#fff', border: 'none', width: 120 },
        })
        stepEdges.push({
          id: `e_step_${tc.steps[tc.steps.length - 1].step_number}_end`,
          source: `step_${tc.steps[tc.steps.length - 1].step_number}`,
          target: endId,
          animated: true,
        })

        setNodes(stepNodes)
        setEdges(stepEdges)
      }
    } catch (err) {
      handleApiError(err, '加载测试用例失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTestCase() }, [id])

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges]
  )

  const handleNodeClick = (_: any, node: Node) => {
    if (node.id === 'start' || node.id === 'end') return
    setSelectedNode(node)
    stepForm.setFieldsValue({
      step_number: parseInt(node.id.replace('step_', '')),
      action: node.data.label?.toString().replace(/^\d+\.\s*/, '') || '',
    })
    setStepModalVisible(true)
  }

  const handleAddStep = () => {
    const stepNum = nodes.filter(n => n.id.startsWith('step_')).length + 1
    const newNode: Node = {
      id: `step_${stepNum}`,
      type: 'default',
      data: { label: `${stepNum}. 新步骤` },
      position: { x: 400, y: 100 + (stepNum - 1) * 100 },
      style: { width: 200 },
    }
    setNodes((nds) => [...nds, newNode])
    message.success('已添加新步骤')
  }

  const handleSaveFlow = async () => {
    if (!id) return
    try {
      // Convert nodes/edges to steps
      const stepNodes = nodes
        .filter(n => n.id.startsWith('step_'))
        .sort((a, b) => a.position.y - b.position.y)

      const steps = stepNodes.map((node, index) => ({
        step_number: index + 1,
        action: node.data.label?.toString().replace(/^\d+\.\s*/, '') || '',
        expected_result: '',
        parameters: {},
      }))

      await testCaseAPI.update(id, {
        steps,
        flow_data: { nodes, edges },
      })
      message.success('流程图已保存')
    } catch (err) {
      message.error('保存失败')
    }
  }

  const handleRun = async () => {
    if (!id) return
    try {
      await executionAPI.run(id)
      message.success('开始执行测试')
      navigate('/executions')
    } catch (err) {
      message.error('执行失败')
    }
  }

  const handleStepSave = () => {
    const values = stepForm.getFieldsValue()
    if (selectedNode) {
      setNodes((nds) =>
        nds.map((node) =>
          node.id === selectedNode.id
            ? { ...node, data: { label: `${values.step_number}. ${values.action}` } }
            : node
        )
      )
    }
    setStepModalVisible(false)
    message.success('步骤已更新')
  }

  return (
    <div className="page-container">
      <Breadcrumb
        items={[
          { title: <a onClick={() => navigate('/')}><HomeOutlined /> 首页</a> },
          { title: <a onClick={() => navigate('/testcases')}>测试用例</a> },
          { title: testCase?.name || '流程图编辑' },
        ]}
        style={{ marginBottom: 16 }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/testcases')}>
            返回
          </Button>
          <Title level={4} style={{ margin: 0 }}>{testCase?.name || '流程图编辑'}</Title>
        </Space>
        <Space>
          <Button icon={<PlusOutlined />} onClick={handleAddStep}>添加步骤</Button>
          <Button icon={<SaveOutlined />} type="primary" onClick={handleSaveFlow}>
            保存流程图
          </Button>
          <Button
            icon={<PlayCircleOutlined />}
            type="primary"
            danger
            onClick={handleRun}
          >
            运行测试
          </Button>
        </Space>
      </div>

      <Card bodyStyle={{ padding: 0 }}>
        <div style={{ height: 600 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={handleNodeClick}
            nodeTypes={nodeTypes}
            fitView
          >
            <Controls />
            <MiniMap />
            <Background gap={16} />
          </ReactFlow>
        </div>
      </Card>

      <Modal
        title="编辑步骤"
        open={stepModalVisible}
        onCancel={() => setStepModalVisible(false)}
        onOk={handleStepSave}
      >
        <Form form={stepForm} layout="vertical">
          <Form.Item name="step_number" label="步骤编号">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="action" label="步骤操作" rules={[{ required: true }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
