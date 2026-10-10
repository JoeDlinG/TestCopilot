import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Row, Col, Card, Table, Button, Space, Input, InputNumber, Select, Tag,
  Alert, Modal, Drawer, Progress, Tooltip, Typography, Divider, message,
  List, Checkbox, Empty, Spin,
} from 'antd'
import {
  PlusOutlined, ArrowUpOutlined, ArrowDownOutlined, DeleteOutlined,
  PlayCircleOutlined, SaveOutlined, StopOutlined, WarningOutlined,
  CopyOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { planAPI, planRunAPI, testCaseAPI, deviceAPI } from '../services/api'

const { Text, Title } = Typography

interface PlanItem {
  id: string
  testcase_id: string
  testcase_name?: string
  group_no: number
  loop_count: number
  delay_before_ms: number
  delay_after_ms: number
  loop_interval_ms: number
  device_id?: string | null
  resolved_device_ids?: string[]
  resolved_state?: string
}

const DEFAULT_ITEM = {
  group_no: 0,
  loop_count: 1,
  delay_before_ms: 0,
  delay_after_ms: 0,
  loop_interval_ms: 0,
}

/** Extract the `items` array out of the unified {code, message, data} envelope. */
function extractItems(res: any): any[] {
  const d = res?.data?.data
  if (Array.isArray(d)) return d
  if (Array.isArray(d?.items)) return d.items
  return []
}

function extractData(res: any): any {
  return res?.data?.data
}

/** Mirrors backend `auto_serialize`: keep order, give every item its own group. */
function autoSerialize(items: PlanItem[]): PlanItem[] {
  const ordered = [...items].sort((a, b) => a.group_no - b.group_no)
  let groupNo = 1
  let prev: number | null = null
  return ordered.map((it) => {
    if (prev !== null && it.group_no !== prev) groupNo += 1
    prev = it.group_no
    return { ...it, group_no: groupNo }
  })
}

const STATE_TAG: Record<string, { color: string; text: string }> = {
  resolved: { color: 'green', text: '已确定' },
  candidates: { color: 'orange', text: '多候选' },
  unresolved: { color: 'red', text: '未指定' },
}

export default function ExecutionPlanner() {
  const [cases, setCases] = useState<any[]>([])
  const [devices, setDevices] = useState<any[]>([])
  const [plans, setPlans] = useState<any[]>([])
  const [planId, setPlanId] = useState<string | null>(null)
  const [planName, setPlanName] = useState('新建执行计划')
  const [planLoop, setPlanLoop] = useState(1)
  const [maxParallel, setMaxParallel] = useState(4)
  const [onError, setOnError] = useState('abort_all')
  const [items, setItems] = useState<PlanItem[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [keyword, setKeyword] = useState('')
  const [validation, setValidation] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [runId, setRunId] = useState<string | null>(null)
  const [run, setRun] = useState<any>(null)
  const [monitorOpen, setMonitorOpen] = useState(false)
  const debounceRef = useRef<any>(null)

  const deviceName = useMemo(() => {
    const m: Record<string, string> = {}
    devices.forEach((d) => { m[d.id] = d.name })
    return m
  }, [devices])

  const loadBase = async () => {
    try {
      const [c, d, p] = await Promise.all([
        testCaseAPI.list(), deviceAPI.list(), planAPI.list(),
      ])
      setCases(extractItems(c))
      setDevices(extractItems(d))
      setPlans(extractItems(p))
    } catch (e) {
      message.error('加载用例/设备失败')
    }
  }

  useEffect(() => { loadBase() }, [])

  // ---- validate the draft whenever the configuration changes -----------
  useEffect(() => {
    if (!items.length) { setValidation(null); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await planAPI.validateDraft({
          plan: {
            name: planName,
            plan_loop_count: planLoop,
            max_parallel: maxParallel,
            on_error: onError,
          },
          items: items.map((it) => ({
            id: it.id,
            testcase_id: it.testcase_id,
            group_no: it.group_no,
            loop_count: it.loop_count,
            delay_before_ms: it.delay_before_ms,
            delay_after_ms: it.delay_after_ms,
            loop_interval_ms: it.loop_interval_ms,
            device_id: it.device_id,
            resolved_device_ids: it.resolved_device_ids,
            resolved_state: it.resolved_state,
          })),
        })
        setValidation(extractData(res))
      } catch (e) {
        setValidation(null)
      }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [items, planLoop, maxParallel, onError])

  // ---- poll the running batch -----------------------------------------
  useEffect(() => {
    if (!runId) return
    let alive = true
    const tick = async () => {
      try {
        const data = extractData(await planRunAPI.get(runId))
        if (!alive) return
        setRun(data)
        if (data?.status !== 'running') {
          setRunId((cur) => (cur === runId ? null : cur))
        }
      } catch { /* keep polling */ }
    }
    tick()
    const timer = setInterval(tick, 2000)
    return () => { alive = false; clearInterval(timer) }
  }, [runId])

  // ---- item helpers ----------------------------------------------------
  const addSelected = () => {
    if (!selected.length) { message.warning('请先在左侧勾选用例'); return }
    const existing = new Set(items.map((i) => i.testcase_id))
    const added: PlanItem[] = []
    selected.forEach((cid) => {
      if (existing.has(cid)) return
      const tc = cases.find((c) => c.id === cid)
      added.push({
        id: `tmp_${Date.now()}_${cid}`,
        testcase_id: cid,
        testcase_name: tc?.name,
        ...DEFAULT_ITEM,
        // Default = own sequence number => fully serial (PRD FR3.1)
        group_no: items.length + added.length + 1,
      })
    })
    setItems([...items, ...added])
    setSelected([])
  }

  const update = (id: string, patch: Partial<PlanItem>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)))

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= items.length) return
    const next = [...items]
    ;[next[index], next[target]] = [next[target], next[index]]
    setItems(next)
  }

  const remove = (id: string) => setItems((prev) => prev.filter((i) => i.id !== id))

  const mergeWithPrev = (index: number) => {
    if (index === 0) return
    const prevGroup = items[index - 1].group_no
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, group_no: prevGroup } : it)))
  }

  const splitGroup = (index: number) => {
    const maxGroup = Math.max(...items.map((i) => i.group_no))
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, group_no: maxGroup + 1 } : it)))
  }

  // ---- persistence -----------------------------------------------------
  const save = async () => {
    if (!items.length) { message.warning('计划为空'); return }
    setLoading(true)
    try {
      const payload = {
        name: planName,
        plan_loop_count: planLoop,
        max_parallel: maxParallel,
        on_error: onError,
        items: items.map((it, idx) => ({
          testcase_id: it.testcase_id,
          seq: idx + 1,
          group_no: it.group_no,
          loop_count: it.loop_count,
          delay_before_ms: it.delay_before_ms,
          delay_after_ms: it.delay_after_ms,
          loop_interval_ms: it.loop_interval_ms,
          device_id: it.device_id,
        })),
      }
      let res
      if (planId) res = await planAPI.update(planId, payload)
      else res = await planAPI.create(payload)
      const data = extractData(res)
      setPlanId(data.id)
      setItems(data.items.map((it: any) => ({ ...it })))
      message.success('计划已保存')
      loadBase()
    } catch (e: any) {
      message.error(e?.response?.data?.detail?.message || '保存失败')
    } finally {
      setLoading(false)
    }
  }

  const openPlan = async (id: string) => {
    const data = extractData(await planAPI.get(id))
    setPlanId(data.id)
    setPlanName(data.name)
    setPlanLoop(data.plan_loop_count)
    setMaxParallel(data.max_parallel)
    setOnError(data.on_error)
    setItems((data.items || []).map((it: any) => ({ ...it })))
  }

  const startRun = async () => {
    if (!planId) { message.warning('请先保存计划'); return }
    try {
      const res = await planAPI.run(planId)
      const data = extractData(res)
      setRunId(data.run_id)
      setRun({ status: 'running', total_items: data.total_items, items: [] })
      setMonitorOpen(true)
      message.success('批次已启动')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (e?.response?.status === 409) {
        setValidation(detail?.validation)
        const errs = detail?.validation?.errors || []
        Modal.error({
          title: '计划存在冲突，不能执行',
          content: (
            <div>
              {errs.map((x: any, i: number) => (
                <div key={i} style={{ marginTop: 6 }}>· {x.message}</div>
              ))}
            </div>
          ),
        })
      } else {
        message.error(detail?.message || '启动失败')
      }
    }
  }

  const filteredCases = cases.filter((c) =>
    !keyword || (c.name || '').toLowerCase().includes(keyword.toLowerCase())
  )

  const errorItemIds = new Set<string>()
  ;(validation?.errors || []).forEach((e: any) =>
    (e.item_ids || []).forEach((i: string) => errorItemIds.add(i))
  )

  const itemColumns: any[] = [
    {
      title: '序', width: 58,
      render: (_: any, __: any, idx: number) => (
        <Space size={2} direction="vertical">
          <Button size="small" type="text" icon={<ArrowUpOutlined />}
            disabled={idx === 0} onClick={() => move(idx, -1)} />
          <Button size="small" type="text" icon={<ArrowDownOutlined />}
            disabled={idx === items.length - 1} onClick={() => move(idx, 1)} />
        </Space>
      ),
    },
    {
      title: '组', width: 130,
      render: (_: any, r: PlanItem, idx: number) => (
        <Space size={4}>
          <Tag color={errorItemIds.has(r.id) ? 'red' : 'blue'}>组{r.group_no}</Tag>
          <Tooltip title="与上一项并行">
            <Button size="small" type="text" disabled={idx === 0}
              onClick={() => mergeWithPrev(idx)}>↰</Button>
          </Tooltip>
          <Tooltip title="独立成组（串行）">
            <Button size="small" type="text" onClick={() => splitGroup(idx)}>⇥</Button>
          </Tooltip>
        </Space>
      ),
    },
    {
      title: '用例', ellipsis: true,
      render: (_: any, r: PlanItem) => r.testcase_name || r.testcase_id,
    },
    {
      title: '设备', width: 190,
      render: (_: any, r: PlanItem) => {
        const st = STATE_TAG[r.resolved_state || 'unresolved']
        const ids = r.resolved_device_ids || []
        return (
          <Space size={4} direction="vertical" style={{ width: '100%' }}>
            <Tag color={st.color}>{st.text}</Tag>
            <Select
              size="small"
              style={{ width: '100%' }}
              allowClear
              placeholder="自动推断"
              value={r.device_id || undefined}
              onChange={(v) => update(r.id, { device_id: v })}
              options={devices.map((d) => ({ value: d.id, label: d.name }))}
            />
            {!!ids.length && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {ids.map((i) => deviceName[i] || i).join('、')}
              </Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '循环', width: 88,
      render: (_: any, r: PlanItem) => (
        <InputNumber size="small" min={1} max={10000} style={{ width: 72 }}
          value={r.loop_count}
          onChange={(v) => update(r.id, { loop_count: Number(v) || 1 })} />
      ),
    },
    {
      title: '延时(ms)', width: 190,
      render: (_: any, r: PlanItem) => (
        <Space size={2}>
          <Tooltip title="前置延时"><InputNumber size="small" min={0} style={{ width: 58 }}
            value={r.delay_before_ms}
            onChange={(v) => update(r.id, { delay_before_ms: Number(v) || 0 })} /></Tooltip>
          <Tooltip title="循环间隔"><InputNumber size="small" min={0} style={{ width: 58 }}
            value={r.loop_interval_ms}
            onChange={(v) => update(r.id, { loop_interval_ms: Number(v) || 0 })} /></Tooltip>
          <Tooltip title="后置延时"><InputNumber size="small" min={0} style={{ width: 58 }}
            value={r.delay_after_ms}
            onChange={(v) => update(r.id, { delay_after_ms: Number(v) || 0 })} /></Tooltip>
        </Space>
      ),
    },
    {
      title: '', width: 42,
      render: (_: any, r: PlanItem) => (
        <Button size="small" type="text" danger icon={<DeleteOutlined />}
          onClick={() => remove(r.id)} />
      ),
    },
  ]

  const blocking = !!validation?.blocking

  return (
    <div style={{ padding: 4 }}>
      <Row gutter={12}>
        {/* ---------- 左：用例库 ---------- */}
        <Col span={6}>
          <Card size="small" title="用例库" extra={
            <Button size="small" icon={<ReloadOutlined />} onClick={loadBase} />
          }>
            <Input.Search size="small" placeholder="搜索用例" allowClear
              value={keyword} onChange={(e) => setKeyword(e.target.value)}
              style={{ marginBottom: 8 }} />
            <div style={{ maxHeight: 420, overflowY: 'auto' }}>
              <Checkbox.Group style={{ width: '100%' }}
                value={selected} onChange={(v) => setSelected(v as string[])}>
                <List size="small" dataSource={filteredCases}
                  locale={{ emptyText: <Empty description="无用例" /> }}
                  renderItem={(c) => (
                    <List.Item style={{ padding: '4px 0' }}>
                      <Checkbox value={c.id}>
                        <Text ellipsis style={{ maxWidth: 160 }}>{c.name}</Text>
                      </Checkbox>
                    </List.Item>
                  )} />
              </Checkbox.Group>
            </div>
            <Button block type="dashed" icon={<PlusOutlined />} style={{ marginTop: 8 }}
              onClick={addSelected}>加入计划（{selected.length}）</Button>
          </Card>

          <Card size="small" title="已有计划" style={{ marginTop: 12 }}>
            <List size="small" dataSource={plans}
              locale={{ emptyText: <Empty description="暂无" /> }}
              renderItem={(p: any) => (
                <List.Item style={{ padding: '4px 0' }}>
                  <Space>
                    <Button size="small" type="link" onClick={() => openPlan(p.id)}>
                      {p.name}
                    </Button>
                    <Text type="secondary" style={{ fontSize: 11 }}>{p.item_count} 项</Text>
                  </Space>
                </List.Item>
              )} />
          </Card>
        </Col>

        {/* ---------- 中：执行序列 ---------- */}
        <Col span={13}>
          <Card size="small"
            title={<Space>
              <Input size="small" style={{ width: 220 }} value={planName}
                onChange={(e) => setPlanName(e.target.value)} />
              {planId && <Tag>{planId}</Tag>}
            </Space>}
            extra={<Space>
              <Button size="small" icon={<CopyOutlined />}
                onClick={async () => {
                  if (!planId) return message.warning('请先保存')
                  const d = extractData(await planAPI.duplicate(planId))
                  openPlan(d.id); loadBase()
                }}>复制</Button>
              <Button size="small" icon={<SaveOutlined />} loading={loading}
                onClick={save}>保存</Button>
            </Space>}>
            <Space size={12} style={{ marginBottom: 10 }} wrap>
              <Space size={4}>
                <Text type="secondary">计划循环</Text>
                <InputNumber size="small" min={1} max={1000} style={{ width: 70 }}
                  value={planLoop} onChange={(v) => setPlanLoop(Number(v) || 1)} />
              </Space>
              <Space size={4}>
                <Text type="secondary">最大并行</Text>
                <InputNumber size="small" min={1} max={16} style={{ width: 70 }}
                  value={maxParallel} onChange={(v) => setMaxParallel(Number(v) || 4)} />
              </Space>
              <Space size={4}>
                <Text type="secondary">失败策略</Text>
                <Select size="small" style={{ width: 120 }} value={onError}
                  onChange={setOnError}
                  options={[
                    { value: 'abort_all', label: '停止全部' },
                    { value: 'continue', label: '继续' },
                    { value: 'abort_group', label: '停止本组' },
                  ]} />
              </Space>
            </Space>

            <Table size="small" rowKey="id" pagination={false}
              dataSource={items} columns={itemColumns}
              rowClassName={(r) => (errorItemIds.has(r.id) ? 'plan-row-error' : '')}
              locale={{ emptyText: <Empty description="从左侧勾选用例加入" /> }} />
          </Card>
        </Col>

        {/* ---------- 右：校验面板 ---------- */}
        <Col span={5}>
          <Card size="small" title="执行前校验">
            {!validation && <Empty description="添加用例后自动校验" />}

            {!!(validation?.errors || []).length && (
              <Alert type="error" showIcon icon={<WarningOutlined />}
                style={{ marginBottom: 8 }}
                message={`${validation.errors.length} 个冲突，必须处理`}
                description={
                  <div>
                    {validation.errors.map((e: any, i: number) => (
                      <div key={i} style={{ marginTop: 6, fontSize: 12 }}>
                        {i + 1}. {e.message}
                      </div>
                    ))}
                    <Button size="small" style={{ marginTop: 8 }}
                      onClick={() => setItems(autoSerialize(items))}>
                      自动串行化(推荐)
                    </Button>
                  </div>
                } />
            )}

            {!!(validation?.warnings || []).length && (
              <Alert type="warning" showIcon style={{ marginBottom: 8 }}
                message={`${validation.warnings.length} 个警告`}
                description={validation.warnings.map((w: any, i: number) => (
                  <div key={i} style={{ fontSize: 12, marginTop: 4 }}>· {w.message}</div>
                ))} />
            )}

            {!!(validation?.infos || []).length && (
              <Alert type="info" showIcon style={{ marginBottom: 8 }}
                message={validation.infos[0].message} />
            )}

            <Divider style={{ margin: '10px 0' }} />
            <Tooltip title={blocking ? '存在冲突，无法执行' : !planId ? '请先保存计划' : ''}>
              <Button block type="primary" icon={<PlayCircleOutlined />}
                disabled={blocking || !items.length}
                onClick={startRun}>开始执行</Button>
            </Tooltip>

            {run && (
              <div style={{ marginTop: 10 }}>
                <Button block size="small" onClick={() => setMonitorOpen(true)}>
                  查看最近批次（{run.status}）
                </Button>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {/* ---------- 运行监控 ---------- */}
      <Drawer title="批量运行监控" width={620} open={monitorOpen}
        onClose={() => setMonitorOpen(false)}
        extra={run?.status === 'running' && (
          <Button danger size="small" icon={<StopOutlined />}
            onClick={async () => {
              if (runId) { await planRunAPI.stop(runId); message.info('已请求停止') }
            }}>停止批次</Button>
        )}>
        {!run ? <Spin /> : (
          <>
            <Space direction="vertical" style={{ width: '100%' }} size={8}>
              <Title level={5} style={{ margin: 0 }}>状态：{run.status}</Title>
              <Progress percent={run.total_items
                ? Math.round((run.completed_items || 0) / run.total_items * 100) : 0} />
              <Space size={16} wrap>
                <Text>通过 {run.passed_items || 0}</Text>
                <Text type="danger">失败 {run.failed_items || 0}</Text>
                <Text type="secondary">耗时 {run.duration_ms ? (run.duration_ms / 1000).toFixed(1) + 's' : '-'}</Text>
              </Space>
            </Space>
            <Divider />
            <List size="small" dataSource={run.items || []}
              renderItem={(it: any) => (
                <List.Item>
                  <Space direction="vertical" style={{ width: '100%' }} size={2}>
                    <Space>
                      <Tag>组{it.group_no}</Tag>
                      <Text strong>{it.testcase_name || it.testcase_id}</Text>
                      <Tag color={
                        it.status === 'passed' ? 'green'
                          : it.status === 'failed' ? 'red'
                            : it.status === 'running' ? 'blue' : 'default'
                      }>{it.status}</Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      迭代 {it.iteration || 0} / {it.loop_count || 1}
                      {it.execution_id ? ` · 执行 ${it.execution_id}` : ''}
                    </Text>
                  </Space>
                </List.Item>
              )} />
          </>
        )}
      </Drawer>

      <style>{`
        .plan-row-error { background: #fff1f0; }
        .plan-row-error:hover > td { background: #ffe7e5 !important; }
      `}</style>
    </div>
  )
}
