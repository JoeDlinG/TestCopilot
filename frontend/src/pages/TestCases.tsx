import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Tag, message, Modal,
  Popconfirm, Typography, Tooltip, Form, Input, Select,
  Row, Col, Empty, Divider, Badge, Alert
} from 'antd'
import {
  PlusOutlined, PlayCircleOutlined, EditOutlined,
  DeleteOutlined, ApartmentOutlined, ReloadOutlined,
  DiffOutlined, SettingOutlined, ClearOutlined, SwapOutlined
} from '@ant-design/icons'
import { testCaseAPI, executionAPI, deviceAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import ResultParserConfig, { DATA_TYPES } from '../components/ResultParserConfig'
import type { ParserSpec } from '../components/ResultParserConfig'
import { openDock } from '../stores/outputDockStore'
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
  // Which test case is currently being started — gives the clicked row's
  // button an immediate spinner instead of the UI looking frozen.
  const [runningId, setRunningId] = useState<string | null>(null)

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

  // ---- flows pinning a device id that no longer exists ----
  const [staleBindings, setStale] = useState(0)
  const [rebinding, setRebinding] = useState(false)

  // ---- switch the case to another device (by 设备ID号) ----
  const [switchOpen, setSwitchOpen] = useState(false)
  const [switchTarget, setSwitchTarget] = useState<TestCase | null>(null)
  const [switchSaving, setSwitchSaving] = useState(false)
  const [switchResult, setSwitchResult] = useState<any>(null)
  const [devices, setDevices] = useState<any[]>([])
  const [switchForm] = Form.useForm()

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

  // Flows pin a device by id. When a device is deleted and re-added it gets a
  // NEW id, so those pins dangle: the step aborts with "device is not
  // connected", no command is ever sent and the communication pane stays empty.
  // Surface it here instead of letting the user debug a silent failure.
  const checkStaleBindings = async () => {
    try {
      const res = await testCaseAPI.staleDevices()
      const data: any = res.data?.data || res.data
      setStale(data?.affected_test_cases || 0)
    } catch {
      /* best effort */
    }
  }

  const handleRebind = async () => {
    setRebinding(true)
    try {
      const res = await testCaseAPI.rebindDevices()
      const data: any = res.data?.data || res.data
      message.success(`已重新绑定 ${data.rebound ?? 0} 个节点到当前设备`)
      setStale(0)
      loadTestCases()
    } catch (err) {
      handleApiError(err, '重新绑定设备失败')
    } finally {
      setRebinding(false)
    }
  }

  const loadDevices = async () => {
    try {
      const res = await deviceAPI.list()
      setDevices(extractItems(res))
    } catch { /* optional */ }
  }

  const openSwitch = async (tc: TestCase) => {
    setSwitchTarget(tc)
    setSwitchResult(null)
    if (!devices.length) await loadDevices()
    switchForm.setFieldsValue({ to_device_key: undefined, from_device_key: undefined })
    setSwitchOpen(true)
  }

  const handleSwitchDevice = async () => {
    let values: any
    try {
      values = await switchForm.validateFields()
    } catch {
      return
    }
    if (!switchTarget) return
    setSwitchSaving(true)
    try {
      const res = await testCaseAPI.switchDevice(
        switchTarget.id, values.to_device_key, values.from_device_key || undefined,
      )
      const data: any = res.data?.data || res.data
      setSwitchResult(data)
      message.success(
        `已将 ${data.changed_count} 个步骤切换到 ${data.device?.device_key}，并重新生成代码`,
      )
      loadTestCases()
      checkStaleBindings()
    } catch (err) {
      handleApiError(err, '切换设备失败')
    } finally {
      setSwitchSaving(false)
    }
  }

  useEffect(() => {
    loadTestCases()
    checkStaleBindings()
  }, [])

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
    if (runningId) return // one at a time
    try {
      setRunningId(tc.id)
      await executionAPI.run(tc.id)
      message.success(`开始执行: ${tc.name}`)
      // Issue #20: results must be visible immediately — open the output dock
      // on the 测试执行 tab instead of navigating away from the authoring page.
      openDock('executions')
      navigate('/executions')
    } catch (err) {
      handleApiError(err, '执行失败')
    } finally {
      setRunningId(null)
    }
  }

  const statusColor: Record<string, string> = {
    draft: 'default',
    ready: 'blue',
    running: 'processing',
    completed: 'green',
    failed: 'red',
  }

  // Every column declares an explicit width. AntD switches the table to
  // `table-layout: fixed` as soon as any column sets `ellipsis`; without
  // widths the remaining space is distributed by content, so a long "标签"
  // cell pushed into 状态 / 创建时间 / 操作 and the text overlapped.
  const columns = [
    {
      title: '用例名称',
      dataIndex: 'name',
      key: 'name',
      width: 240,
      ellipsis: true,
      render: (text: string, record: TestCase) => (
        <Tooltip title={text}>
          <a onClick={() => navigate(`/testcases/${record.id}/flow`)}>
            <DiffOutlined /> {text}
          </a>
        </Tooltip>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      width: 260,
      ellipsis: true,
    },
    {
      title: '步骤数',
      key: 'steps',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: TestCase) => record.steps?.length || 0,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      width: 220,
      render: (tags: string[]) => {
        const list = tags || []
        if (list.length === 0) return <Text type="secondary">-</Text>
        return (
          <Tooltip title={list.join('、')}>
            <span
              style={{
                display: 'inline-block', maxWidth: '100%',
                overflow: 'hidden', whiteSpace: 'nowrap', verticalAlign: 'bottom',
              }}
            >
              {list.map((tag) => (
                <Tag key={tag} color="blue" style={{ marginInlineEnd: 4 }}>{tag}</Tag>
              ))}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 250,
      render: (_: any, record: TestCase) => (
        <Space>
          <Tooltip title="运行测试">
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={runningId === record.id}
              onClick={() => handleRun(record)}
            />
          </Tooltip>
          <Tooltip title="切换设备（按设备ID号重新绑定并重新生成代码）">
            <Button
              size="small"
              icon={<SwapOutlined />}
              onClick={() => openSwitch(record)}
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
      {staleBindings > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`有 ${staleBindings} 个用例绑定了已不存在的设备`}
          description="设备被删除后重新添加会得到新的 ID，而这些用例仍指向旧 ID：执行时会直接判定失败、不下发任何指令，因此通信窗口看不到任何消息。点击下方按钮可按节点命令推断出的协议重新绑定到当前设备。"
          action={
            <Button size="small" type="primary" icon={<ApartmentOutlined />}
              loading={rebinding} onClick={handleRebind}>
              重新绑定设备
            </Button>
          }
        />
      )}
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

      {/* 切换设备：按设备ID号重新绑定，并重新生成代码 */}
      <Modal
        title="切换设备"
        open={switchOpen}
        onOk={handleSwitchDevice}
        confirmLoading={switchSaving}
        onCancel={() => setSwitchOpen(false)}
        okText="切换并重新生成代码"
        cancelText="取消"
        width={560}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="用例通过「设备ID号」关联设备"
          description="更换硬件时，把同一个设备ID号赋给新设备，或直接把用例切换到另一个设备ID号。切换后会自动按新设备重新生成代码。"
        />
        <Form form={switchForm} layout="vertical">
          <Form.Item
            name="to_device_key"
            label="切换到（目标设备ID号）"
            rules={[{ required: true, message: '请选择目标设备' }]}
          >
            <Select
              placeholder="选择设备"
              options={devices.map((d) => ({
                value: d.device_key,
                label: `${d.device_key}　${d.name}（${d.protocol}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="from_device_key"
            label="仅切换当前绑定（可选）"
            extra="留空表示切换本用例所有已绑定设备的步骤"
          >
            <Select
              allowClear
              placeholder="全部（默认）"
              options={devices.map((d) => ({
                value: d.device_key,
                label: `${d.device_key}　${d.name}`,
              }))}
            />
          </Form.Item>
        </Form>

        {switchResult && (
          <div style={{ marginTop: 8 }}>
            <Text strong>切换结果</Text>
            <div style={{ marginTop: 6 }}>
              <Tag color="green">
                已切换 {switchResult.changed_count} 个步骤 → {switchResult.device?.device_key}
              </Tag>
              <Tag color="blue">已重新生成代码（{switchResult.code?.length ?? 0} 字符）</Tag>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
