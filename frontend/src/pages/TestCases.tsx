import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Tag, message, Modal,
  Popconfirm, Typography, Tooltip, Form, Input, Select,
  Row, Col, Empty, Divider, Badge
} from 'antd'
import {
  PlusOutlined, PlayCircleOutlined, EditOutlined,
  DeleteOutlined, ApartmentOutlined, ReloadOutlined,
  ExperimentOutlined, SettingOutlined, ClearOutlined
} from '@ant-design/icons'
import { testCaseAPI, executionAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import ResultParserConfig, { DATA_TYPES } from '../components/ResultParserConfig'
import type { ParserSpec } from '../components/ResultParserConfig'
import type { TestCase } from '../types'

const { Title, Text } = Typography

/** "cmd -> response | cmd2 -> resp2 || 解析: ..." -> the last response text */
function extractResponse(actual?: string): string {
  if (!actual) return ''
  const main = String(actual).split('||')[0]
  const parts = main.split('|')
  const last = parts[parts.length - 1] || ''
  const idx = last.indexOf('->')
  return idx >= 0 ? last.slice(idx + 2).trim() : last.trim()
}

export default function TestCases() {
  const navigate = useNavigate()
  const [testCases, setTestCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  // ---- rename / clear all ----
  const [renameOpen, setRenameOpen] = useState(false)
  const [renaming, setRenaming] = useState<TestCase | null>(null)
  const [renamingSaving, setRenamingSaving] = useState(false)
  const [renameForm] = Form.useForm()
  const [clearing, setClearing] = useState(false)

  // ---- expanded steps + result parsing config ----
  const [flows, setFlows] = useState<Record<string, any>>({})
  const [flowLoading, setFlowLoading] = useState<Record<string, boolean>>({})
  const [stepSamples, setStepSamples] = useState<Record<string, Record<number, string>>>({})
  const [parserOpen, setParserOpen] = useState(false)
  const [parserSaving, setParserSaving] = useState(false)
  const [parserTarget, setParserTarget] = useState<{
    tcId: string; nodeId: string; label: string; parsers: ParserSpec[]
    sample: string; otherNames: string[]
  } | null>(null)

  const loadTestCases = async () => {
    setLoading(true)
    try {
      const res = await testCaseAPI.list()
      setTestCases(extractItems(res))
    } catch (err) {
      handleApiError(err, '加载测试用例失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTestCases() }, [])

  // ---- load a case's flow (steps) + last-run responses for preview ----
  const loadFlow = async (tcId: string) => {
    if (flows[tcId]) return
    setFlowLoading(p => ({ ...p, [tcId]: true }))
    try {
      const res = await testCaseAPI.getFlow(tcId)
      const data: any = res.data?.data ?? res.data
      setFlows(p => ({ ...p, [tcId]: { nodes: data?.nodes || [], edges: data?.edges || [] } }))

      // seed the preview box with real responses from the most recent run
      try {
        const ex = await executionAPI.list(tcId)
        const list = extractItems(ex)
        if (list.length) {
          const dres = await executionAPI.get(list[0].id)
          const detail: any = dres.data?.data ?? dres.data
          const samples: Record<number, string> = {}
          for (const s of detail?.step_results || []) {
            const r = extractResponse(s.actual)
            if (r) samples[s.step_index] = r
          }
          setStepSamples(p => ({ ...p, [tcId]: samples }))
        }
      } catch { /* preview sample is optional */ }
    } catch (err) {
      setFlows(p => ({ ...p, [tcId]: { nodes: [], edges: [] } }))
    } finally {
      setFlowLoading(p => ({ ...p, [tcId]: false }))
    }
  }

  const openParserConfig = (tcId: string, node: any, stepIndex: number) => {
    const cfg = node?.config || {}
    // names already taken by the other steps - parsed field names must be
    // unique across the whole test case (they identify a value in trends)
    const otherNames: string[] = ((flows[tcId]?.nodes || []) as any[])
      .filter((n: any) => n.id !== node.id)
      .flatMap((n: any) =>
        ((n?.config?.parsers || []) as any[]).map((p: any) => String(p?.name || '').trim())
      )
      .filter(Boolean)
    setParserTarget({
      tcId,
      nodeId: node.id,
      label: node?.data?.label || node?.label || `步骤 ${stepIndex}`,
      parsers: cfg.parsers || [],
      sample: stepSamples[tcId]?.[stepIndex] || '',
      otherNames,
    })
    setParserOpen(true)
  }

  const saveParsers = async (parsers: ParserSpec[]) => {
    if (!parserTarget) return
    const { tcId, nodeId } = parserTarget
    const flow = flows[tcId]
    if (!flow) return
    setParserSaving(true)
    try {
      const nodes = (flow.nodes || []).map((n: any) => (
        n.id === nodeId ? { ...n, config: { ...(n.config || {}), parsers } } : n
      ))
      await testCaseAPI.updateFlow(tcId, { nodes, edges: flow.edges })
      setFlows(p => ({ ...p, [tcId]: { ...flow, nodes } }))
      message.success('结果解析配置已保存，执行时将按此配置解析并判定')
      setParserOpen(false)
    } catch (err) {
      handleApiError(err, '保存解析配置失败')
    } finally {
      setParserSaving(false)
    }
  }

  const expandedRowRender = (record: TestCase) => {
    const flow = flows[record.id]
    const loadingFlow = flowLoading[record.id]
    const steps = ((flow?.nodes || []) as any[]).filter(
      (n: any) => n.type !== 'start' && n.type !== 'end'
    )

    if (loadingFlow) return <Text type="secondary">加载步骤…</Text>
    if (!steps.length) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="该用例还没有流程图步骤，请先编辑流程图"
        />
      )
    }

    return (
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={steps}
        columns={[
          {
            title: '#', key: 'idx', width: 45,
            render: (_: any, __: any, i: number) => i + 1,
          },
          {
            title: '步骤', dataIndex: ['data', 'label'],
            render: (v: string, n: any) => v || n?.label || '-',
          },
          {
            title: '下发指令', key: 'cmd', ellipsis: true,
            render: (_: any, n: any) => {
              const cmd = n?.config?.command || ''
              return cmd ? <Text code style={{ fontSize: 11 }}>{String(cmd).slice(0, 70)}</Text> : '-'
            },
          },
          {
            title: '解析配置', key: 'parsers', width: 200,
            render: (_: any, n: any) => {
              const ps: ParserSpec[] = n?.config?.parsers || []
              if (!ps.length) return <Text type="secondary" style={{ fontSize: 12 }}>未配置</Text>
              return (
                <Space size={4} wrap>
                  {ps.map((p, i) => (
                    <Tooltip
                      key={i}
                      title={`类型 ${p.data_type} · 起始 ${p.start}${p.unit === 'bit' ? 'bit' : 'byte'} · 长度 ${p.length}`}
                    >
                      <Tag color="purple">
                        {p.name || `字段${i + 1}`}({DATA_TYPES.find(d => d.value === p.data_type)?.label.split(' ')[0] || p.data_type})
                      </Tag>
                    </Tooltip>
                  ))}
                </Space>
              )
            },
          },
          {
            title: '操作', key: 'act', width: 130,
            render: (_: any, n: any, i: number) => (
              <Button
                size="small"
                icon={<SettingOutlined />}
                onClick={() => openParserConfig(record.id, n, i + 1)}
              >
                解析配置
                {(n?.config?.parsers || []).length > 0 && (
                  <Badge
                    count={(n.config.parsers || []).length}
                    style={{ marginLeft: 4, backgroundColor: '#722ed1' }}
                  />
                )}
              </Button>
            ),
          },
        ]}
      />
    )
  }

  const handleCreate = async (values: any) => {
    try {
      await testCaseAPI.create(values)
      message.success('测试用例创建成功')
      setModalVisible(false)
      form.resetFields()
      loadTestCases()
    } catch (err) {
      handleApiError(err, '创建失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await testCaseAPI.delete(id)
      message.success('已删除')
      loadTestCases()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  // ---- rename ----
  const openRename = (tc: TestCase) => {
    setRenaming(tc)
    renameForm.setFieldsValue({ name: tc.name })
    setRenameOpen(true)
  }

  const handleRename = async () => {
    if (!renaming) return
    let name = ''
    try {
      const values = await renameForm.validateFields()
      name = String(values.name || '').trim()
    } catch {
      return
    }
    if (!name) {
      message.warning('名称不能为空')
      return
    }
    if (name === renaming.name) {
      setRenameOpen(false)
      return
    }
    try {
      setRenamingSaving(true)
      await testCaseAPI.update(renaming.id, { name })
      message.success('已重命名')
      setRenameOpen(false)
      loadTestCases()
    } catch (err) {
      handleApiError(err, '重命名失败')
    } finally {
      setRenamingSaving(false)
    }
  }

  // ---- clear the whole list ----
  const handleClearAll = async () => {
    if (testCases.length === 0) {
      message.info('列表已经是空的')
      return
    }
    try {
      setClearing(true)
      let failed = 0
      for (const tc of testCases) {
        try {
          await testCaseAPI.delete(tc.id)
        } catch {
          failed += 1
        }
      }
      if (failed) {
        message.warning(`已清空，但有 ${failed} 个用例删除失败，请刷新后重试`)
      } else {
        message.success(`已清空 ${testCases.length} 个测试用例`)
      }
      await loadTestCases()
    } finally {
      setClearing(false)
    }
  }

  const handleRun = async (tc: TestCase) => {
    try {
      await executionAPI.run(tc.id)
      message.success(`开始执行: ${tc.name}`)
      navigate('/executions')
    } catch (err) {
      handleApiError(err, '执行失败')
    }
  }

  const statusColor: Record<string, string> = {
    draft: 'default',
    ready: 'blue',
    running: 'processing',
    completed: 'green',
    failed: 'red',
  }

  const columns = [
    {
      title: '用例名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: TestCase) => (
        <a onClick={() => navigate(`/testcases/${record.id}/flow`)}>
          <ExperimentOutlined /> {text}
        </a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '步骤数',
      key: 'steps',
      render: (_: any, record: TestCase) => record.steps?.length || 0,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <Space>
          {(tags || []).map((tag) => (
            <Tag key={tag} color="blue">{tag}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: TestCase) => (
        <Space>
          <Tooltip title="运行测试">
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => handleRun(record)}
            />
          </Tooltip>
          <Tooltip title="重命名">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => openRename(record)}
            />
          </Tooltip>
          <Tooltip title="流程图编辑">
            <Button
              size="small"
              icon={<ApartmentOutlined />}
              onClick={() => navigate(`/testcases/${record.id}/flow`)}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此用例？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>测试用例</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadTestCases}>刷新</Button>
          <Popconfirm
            title={`确定清空全部 ${testCases.length} 个测试用例？`}
            description="用例及其流程图会被永久删除，此操作不可恢复。"
            okText="清空"
            okButtonProps={{ danger: true }}
            cancelText="取消"
            onConfirm={handleClearAll}
          >
            <Tooltip title="一键清空整个测试用例列表">
              <Button icon={<ClearOutlined />} danger loading={clearing}>
                一键清空
              </Button>
            </Tooltip>
          </Popconfirm>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            创建用例
          </Button>
        </Space>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={testCases}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender,
            onExpand: (expanded, record) => {
              if (expanded) loadFlow(record.id)
            },
            rowExpandable: () => true,
          }}
        />
      </Card>

      <Modal
        title="创建测试用例"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="用例名称" rules={[{ required: true }]}>
            <Input placeholder="输入测试用例名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="输入测试用例描述" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
        </Form>
      </Modal>

      {/* ---- rename ---- */}
      <Modal
        title="重命名测试用例"
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={handleRename}
        confirmLoading={renamingSaving}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={renameForm}
          layout="vertical"
          onFinish={handleRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !(e.target as any)?.tagName?.includes('TEXTAREA')) {
              e.preventDefault()
              handleRename()
            }
          }}
        >
          <Form.Item
            name="name"
            label="用例名称"
            rules={[{ required: true, message: '请输入用例名称' }]}
          >
            <Input placeholder="输入新的用例名称" />
          </Form.Item>
        </Form>
        {renaming && (
          <div style={{ color: '#888', fontSize: 12 }}>
            当前名称：{renaming.name}（ID {renaming.id}）
          </div>
        )}
      </Modal>

      {parserTarget && (
        <ResultParserConfig
          open={parserOpen}
          stepLabel={parserTarget.label}
          parsers={parserTarget.parsers}
          initialSample={parserTarget.sample}
          otherNames={parserTarget.otherNames}
          saving={parserSaving}
          onCancel={() => setParserOpen(false)}
          onSave={saveParsers}
        />
      )}
    </div>
  )
}
