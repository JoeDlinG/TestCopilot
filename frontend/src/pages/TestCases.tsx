import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Tag, message, Modal,
  Popconfirm, Typography, Tooltip, Form, Input, Select,
  Row, Col, Empty, Divider, Badge, Alert
} from 'antd'
import { DataTable } from '../components/ui'
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
import { useI18n } from '../i18n'

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
  const { t } = useI18n()
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
      handleApiError(err, t('msg.loadCasesFailed'))
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
      message.success(`${t('msg.rebound')} ${data.rebound ?? 0} ${t('msg.nodesToDevice')}`)
      setStale(0)
      loadTestCases()
    } catch (err) {
      handleApiError(err, t('msg.rebindFailed'))
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
            `${t('msg.switchedPrefix')}${data.changed_count} ${t('msg.stepsSwitched')} ${data.device?.device_key}${t('label.andRegen')}${t('btn.generateCode')}`,
      )
      loadTestCases()
      checkStaleBindings()
    } catch (err) {
      handleApiError(err, t('msg.switchFailed'))
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
      label: node?.data?.label || node?.label || `${t('col.steps')} ${stepIndex}`,
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
      message.success(t('msg.parserSaved'))
      setParserOpen(false)
    } catch (err) {
      handleApiError(err, t('msg.saveParserFailed'))
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

    if (loadingFlow) return <Text type="secondary">{t('msg.loadingSteps')}</Text>
    if (!steps.length) {
      return (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('msg.noFlowSteps')}
        />
      )
    }

    return (
      <DataTable
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
            title: t('col.steps'), dataIndex: ['data', 'label'],
            render: (v: string, n: any) => v || n?.label || '-',
          },
          {
            title: t('col.command'), key: 'cmd', ellipsis: true,
            render: (_: any, n: any) => {
              const cmd = n?.config?.command || ''
              return cmd ? <Text code style={{ fontSize: 11 }}>{String(cmd).slice(0, 70)}</Text> : '-'
            },
          },
          {
            title: t('col.parserConfig'), key: 'parsers', width: 200,
            render: (_: any, n: any) => {
              const ps: ParserSpec[] = n?.config?.parsers || []
              if (!ps.length) return <Text type="secondary" style={{ fontSize: 12 }}>{t('label.notConfigured')}</Text>
              return (
                <Space size={4} wrap>
                  {ps.map((p, i) => (
                    <Tooltip
                      key={i}
                      title={`${t('col.type')} ${p.data_type} · t('label.start')} ${p.start}${p.unit === 'bit' ? 'bit' : 'byte'} · ${t('label.length')} ${p.length}`}
                    >
                      <Tag color="purple">
                        {p.name || `${t('label.field')}${i + 1}`}({DATA_TYPES.find(d => d.value === p.data_type)?.label.split(' ')[0] || p.data_type})
                      </Tag>
                    </Tooltip>
                  ))}
                </Space>
              )
            },
          },
          {
            title: t('col.actions'), key: 'act', width: 130,
            render: (_: any, n: any, i: number) => (
              <Button
                size="small"
                icon={<SettingOutlined />}
                onClick={() => openParserConfig(record.id, n, i + 1)}
              >
                {t('col.parserConfig')}
                {(n?.config?.parsers || []).length > 0 && (
                  <Badge
                    count={(n.config.parsers || []).length}
                    style={{ marginLeft: 4, backgroundColor: 'var(--app-series-5)' }}
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
      message.success(t('msg.caseCreated'))
      setModalVisible(false)
      form.resetFields()
      loadTestCases()
    } catch (err) {
      handleApiError(err, t('msg.createFailed'))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await testCaseAPI.delete(id)
      message.success(t('msg.deleted'))
      loadTestCases()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
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
      message.warning(t('msg.nameRequired'))
      return
    }
    if (name === renaming.name) {
      setRenameOpen(false)
      return
    }
    try {
      setRenamingSaving(true)
      await testCaseAPI.update(renaming.id, { name })
      message.success(t('msg.renamed'))
      setRenameOpen(false)
      loadTestCases()
    } catch (err) {
      handleApiError(err, t('msg.renameFailed'))
    } finally {
      setRenamingSaving(false)
    }
  }

  // ---- clear the whole list ----
  const handleClearAll = async () => {
    if (testCases.length === 0) {
      message.info(t('msg.listEmpty'))
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
        message.warning(`${t('msg.clearedBut')} ${failed} ${t('msg.deleteFailedSuffix')}`)
      } else {
        message.success(`${t('msg.cleared')} ${testCases.length} t('label.count')}${t('col.testCase')}`)
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
      message.success(`${t('label.startColon')} ${tc.name}`)
      // Issue #20: results must be visible immediately — open the output dock
      // on the 测试执行 tab instead of navigating away from the authoring page.
      openDock('executions')
      navigate('/executions')
    } catch (err) {
      handleApiError(err, t('msg.execFailed'))
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
  // widths the remaining space is distributed by content, so a long t('col.tags')
  // cell pushed into 状态 / 创建时间 / 操作 and the text overlapped.
  const columns = [
    {
      title: t('col.caseName'),
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
      title: t('col.description'),
      dataIndex: 'description',
      key: 'description',
      width: 260,
      ellipsis: true,
    },
    {
      title: t('col.stepCount'),
      key: 'steps',
      width: 80,
      align: 'center' as const,
      render: (_: any, record: TestCase) => record.steps?.length || 0,
    },
    {
      title: t('col.tags'),
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
      title: t('col.status'),
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: t('col.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('col.actions'),
      key: 'actions',
      width: 250,
      render: (_: any, record: TestCase) => (
        <Space>
          <Tooltip title={t('btn.runCase')}>
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={runningId === record.id}
              onClick={() => handleRun(record)}
            />
          </Tooltip>
          <Tooltip title={t('btn.switchDeviceLong')}>
            <Button
              size="small"
              icon={<SwapOutlined />}
              onClick={() => openSwitch(record)}
            />
          </Tooltip>
          <Tooltip title={t('common.rename')}>
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => openRename(record)}
            />
          </Tooltip>
          <Tooltip title={t('page.flowEditor')}>
            <Button
              size="small"
              icon={<ApartmentOutlined />}
              onClick={() => navigate(`/testcases/${record.id}/flow`)}
            />
          </Tooltip>
          <Popconfirm
            title={t('msg.deleteCase')}
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title={t('common.delete')}>
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
                message={`${t('label.has')} ${staleBindings} ${t('col.case')}${t('msg.staleDeviceBound')} ${t('col.device')}`}
          description={t('device.staleExplain')}
          action={
            <Button size="small" type="primary" icon={<ApartmentOutlined />}
              loading={rebinding} onClick={handleRebind}>{t('btn.rebind')}</Button>
          }
        />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>{t('col.testCase')}</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadTestCases}>{t('common.refresh')}</Button>
          <Popconfirm
            title={`${t('msg.clearAllConfirm')} ${testCases.length} ${t('msg.casesSuffix')}`}
            description={t('msg.deleteCaseWarn')}
            okText={t('common.clear')}
            okButtonProps={{ danger: true }}
            cancelText={t('common.cancel')}
            onConfirm={handleClearAll}
          >
            <Tooltip title={t('btn.clearAllCases')}>
              <Button icon={<ClearOutlined />} danger loading={clearing}>{t('btn.clearAll')}</Button>
            </Tooltip>
          </Popconfirm>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >{t('btn.createCase')}</Button>
        </Space>
      </div>

      <Card>
        <DataTable
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
        title={t('dlg.newTestCase')}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label={t('col.caseName')} rules={[{ required: true }]}>
            <Input placeholder={t('ph.caseName')} />
          </Form.Item>
          <Form.Item name="description" label={t('col.description')}>
            <Input.TextArea rows={3} placeholder={t('ph.caseDesc')} />
          </Form.Item>
          <Form.Item name="tags" label={t('col.tags')}>
            <Select mode="tags" placeholder={t('ph.tagEnter')} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ---- rename ---- */}
      <Modal
        title={t('btn.renameCase')}
        open={renameOpen}
        onCancel={() => setRenameOpen(false)}
        onOk={handleRename}
        confirmLoading={renamingSaving}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
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
            label={t('col.caseName')}
            rules={[{ required: true, message: t('msg.enterCaseName') }]}
          >
            <Input placeholder={t('ph.newCaseName')} />
          </Form.Item>
        </Form>
        {renaming && (
          <div style={{ color: 'var(--app-fg-muted)', fontSize: 12 }}>
            t('label.currentName'){renaming.name}（ID {renaming.id}）
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

            {/* Switch device: re-bind by device ID and regenerate the code */}
      <Modal
        title={t('btn.switchDevice')}
        open={switchOpen}
        onOk={handleSwitchDevice}
        confirmLoading={switchSaving}
        onCancel={() => setSwitchOpen(false)}
        okText={t('btn.switchAndRegen')}
        cancelText={t('common.cancel')}
        width={560}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('label.caseBindsById')}
          description={t('device.switchExplain')}
        />
        <Form form={switchForm} layout="vertical">
          <Form.Item
            name="to_device_key"
            label={t('ph.switchTarget')}
                  rules={[{ required: true, message: `${t('msg.pickTarget')}${t('col.device')}` }]}
          >
            <Select
              placeholder={t('btn.selectDevice')}
              options={devices.map((d) => ({
                value: d.device_key,
                label: `${d.device_key}　${d.name}（${d.protocol}）`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="from_device_key"
            label={t('label.onlyCurrentBinding')}
            extra={t('label.blankAllDevices')}
          >
            <Select
              allowClear
              placeholder={t('label.allDefault')}
              options={devices.map((d) => ({
                value: d.device_key,
                label: `${d.device_key}　${d.name}`,
              }))}
            />
          </Form.Item>
        </Form>

        {switchResult && (
          <div style={{ marginTop: 8 }}>
            <Text strong>{t('label.switchResult')}</Text>
            <div style={{ marginTop: 6 }}>
              <Tag color="green">
                t('msg.switched') {switchResult.changed_count} t('unit.steps') → {switchResult.device?.device_key}
              </Tag>
              <Tag color="blue">t('msg.regenerated'){switchResult.code?.length ?? 0} {t('label.chars')}</Tag>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
