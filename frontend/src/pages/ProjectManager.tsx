import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Card, Button, Space, Modal, Form, Input, Checkbox, Radio,
  Tag, Typography, message, Popconfirm, Alert, Upload, Divider, Empty,
  Steps, Tooltip, Tree, Collapse,
} from 'antd'
import { DataTable } from '../components/ui'
import {
  DownloadOutlined, UploadOutlined,   SaveOutlined, EditOutlined,
  DeleteOutlined, SyncOutlined, ImportOutlined, FileTextOutlined,
  ReloadOutlined, FileAddOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { projectAPI, PROJECT_SECTIONS } from '../services/api'
import { extractData, handleApiError, _errorMessage } from '../services/apiHelper'
import { useI18n } from '../i18n'

const { Title, Text, Paragraph } = Typography

const ALL_SECTIONS = PROJECT_SECTIONS.map((s) => s.key)

interface ProjectRow {
  name: string
  file_name: string
  size: number
  counts: Record<string, number>
  app_version?: string
  exported_at?: string
  updated_at?: string
  error?: string | null
}

// --------------------------------------------------------------------------- //
// 工程配置预览
// --------------------------------------------------------------------------- //

/** Never surface credentials, even though the bundle already strips them. */
const HIDDEN_KEYS = new Set([
  'api_key_encrypted', 'api_key', 'password', 'secret', 'token',
])

function Cell({ value }: { value: any }) {
  const { t } = useI18n()
  if (value === null || value === undefined || value === '') {
    return <Text type="secondary">-</Text>
  }
  if (typeof value === 'boolean') return <span>{value ? t('common.yes') : t('common.no')}</span>
  const raw = typeof value === 'object' ? JSON.stringify(value) : String(value)
  const shown = raw.length > 60 ? `${raw.slice(0, 60)}…` : raw
  return <span title={raw} style={{ fontSize: 12 }}>{shown}</span>
}

/**
 * Render one configuration section without knowing its schema up front.
 *
 * Bundles are heterogeneous — a device row and a test-case row share almost no
 * fields — so columns are derived from the first rows and long values are
 * truncated with the full text kept in the tooltip.
 */
function SectionTable({ rows }: { rows: any[] }) {
  const { t } = useI18n()
  const list = (rows || []).filter((r) => r && typeof r === 'object')
  if (list.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('msg.sectionEmpty')}
        style={{ padding: '16px 0', margin: 0 }}
      />
    )
  }

  const keys: string[] = []
  for (const row of list.slice(0, 30)) {
    for (const k of Object.keys(row)) {
      if (HIDDEN_KEYS.has(k) || keys.includes(k) || keys.length >= 8) continue
      keys.push(k)
    }
  }

  const columns = keys.map((k, i) => ({
    title: k,
    dataIndex: k,
    key: k,
    width: i === 0 ? 200 : 170,
    ellipsis: true,
    render: (v: any) => <Cell value={v} />,
  }))

  return (
    <DataTable
      rowKey="_idx"
      size="small"
      dataSource={list.slice(0, 200).map((r, i) => ({ ...r, _idx: i }))}
      columns={columns}
      scroll={{ x: keys.length * 180, y: 340 }}
      pagination={list.length > 20 ? { pageSize: 20, simple: true } : false}
    />
  )
}

/** Split a tree key: ``p:<name>`` for a project, ``s:<name>:<section>`` for a section. */
function parseTreeKey(key: string): { name: string; section: string | null } {
  if (key.startsWith('p:')) return { name: key.slice(2), section: null }
  const [, name, section] = key.split(':')
  return { name, section: section ?? null }
}

// --------------------------------------------------------------------------- //
// 仪表盘：渲染 layout 缩略图，而不是摊开一堆参数
// --------------------------------------------------------------------------- //

const WIDGET_TYPE_LABEL = (tr: (k: string) => string): Record<string, string> => ({
  parsed_value: tr('label.parsedValue'),
  trend_chart: tr('label.trendChart'),
  judge_summary: tr('label.judgeSummary'),
  execution_stats: tr('card.execStats'),
  device_status: tr('card.deviceStatus'),
  comm_log: tr('label.commLog'),
})

/** Grid row height in px for the miniature — small enough to scan, big enough to read. */
const LAYOUT_UNIT = 26
const LAYOUT_COLS = 12

/**
 * Draw a dashboard's ``layout`` as a scaled-down diagram.
 *
 * The raw layout is a 12-column react-grid-layout array — readable only to
 * whoever wrote it. Rendering the actual arrangement answers "what does this
 * dashboard look like?" at a glance; the JSON stays available under a collapse
 * for anyone who does need the numbers.
 */
function DashboardPreview({ dashboard }: { dashboard: any }) {
  const { t } = useI18n()
  const layout: any[] = dashboard?.layout || []
  const widgets: any[] = dashboard?.widgets || []
  const byId = new Map(widgets.map((w) => [w.id, w]))

  if (layout.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('msg.noLayout')}
        style={{ padding: '12px 0', margin: 0 }}
      />
    )
  }

  const totalRows = layout.reduce((n, l) => Math.max(n, (l.y || 0) + (l.h || 1)), 0)

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <div
        style={{
          position: 'relative',
          height: totalRows * LAYOUT_UNIT + 8,
          background: 'var(--flow-canvas-bg)',
          border: '1px solid var(--flow-border)',
          borderRadius: 6,
          padding: 4,
        }}
      >
        {layout.map((l) => {
          const w = byId.get(l.i)
          return (
            <div
              key={l.i}
              title={w?.title || l.i}
              style={{
                position: 'absolute',
                left: `calc(${((l.x || 0) / LAYOUT_COLS) * 100}% + 3px)`,
                width: `calc(${((l.w || 1) / LAYOUT_COLS) * 100}% - 6px)`,
                top: (l.y || 0) * LAYOUT_UNIT + 4,
                height: (l.h || 1) * LAYOUT_UNIT - 6,
                boxSizing: 'border-box',
                background: 'var(--flow-badge-bg)',
                border: '1px solid var(--flow-badge-border)',
                borderRadius: 4,
                color: 'var(--flow-badge-fg)',
                padding: '2px 6px',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
              }}
            >
              <Text strong style={{ fontSize: 11, lineHeight: 1.2 }} ellipsis>
                {w?.title || l.i}
              </Text>
              <Text style={{ fontSize: 10, opacity: 0.75, lineHeight: 1.2 }} ellipsis>
                {WIDGET_TYPE_LABEL(t)[w?.type] || w?.type || t('label.widget')}
              </Text>
            </div>
          )
        })}
      </div>
      <Collapse
        ghost
        size="small"
        items={[{
          key: 'raw',
          label: <Text type="secondary" style={{ fontSize: 12 }}>{t('btn.viewRawParams')}</Text>,
          children: (
            <pre style={{
              margin: 0, fontSize: 11, maxHeight: 220, overflow: 'auto',
              background: 'var(--flow-code-bg)', color: 'var(--flow-code-fg)',
              padding: 10, borderRadius: 6,
            }}>
              {JSON.stringify({ layout, widgets }, null, 2)}
            </pre>
          ),
        }]}
      />
    </Space>
  )
}

// --------------------------------------------------------------------------- //
// 执行管理器：展开计划项并显示其测试用例
// --------------------------------------------------------------------------- //

const ON_ERROR_LABEL = (tr: (k: string) => string): Record<string, string> => ({
  abort_all: tr('onError.abortAll'),
  continue: tr('onError.continue'),
  skip_group: tr('onError.abortGroup'),
})

/**
 * A plan row on its own only says "循环 1 次、最大并行 4" — the useful part is
 * *which test cases run in which group*, so items are listed inline with their
 * case name resolved from the bundle's own test-case section.
 */
function PlanPreview({
  plan,
  caseNames,
  deviceNames,
}: {
  plan: any
  caseNames: Record<string, string>
  deviceNames: Record<string, string>
}) {
  const { t } = useI18n()
  const items: any[] = plan?.items || []

  const columns = [
    {
      title: t('col.group'), dataIndex: 'group_no', key: 'group_no', width: 70,
      render: (g: number) => <Tag>{g ?? '-'}</Tag>,
    },
    {
      title: t('col.seq'), dataIndex: 'seq', key: 'seq', width: 56,
    },
    {
      title: t('col.testCase'), dataIndex: 'testcase_id', key: 'testcase_id', width: 240,
      render: (id: string) => (
        <span title={id}>{caseNames[id] || <Text type="secondary">{id || '-'}</Text>}</span>
      ),
    },
    {
      title: t('col.loop'), dataIndex: 'loop_count', key: 'loop_count', width: 70,
    },
    {
      title: t('col.delayBefore'), dataIndex: 'delay_before_ms', key: 'delay_before_ms', width: 90,
      render: (v: number) => (v ? `${v} ms` : '-'),
    },
    {
      title: t('col.delayAfter'), dataIndex: 'delay_after_ms', key: 'delay_after_ms', width: 90,
      render: (v: number) => (v ? `${v} ms` : '-'),
    },
    {
      title: t('col.device'), dataIndex: 'resolved_device_ids', key: 'resolved_device_ids', width: 180,
      render: (ids: string[]) => {
        if (!ids || ids.length === 0) return <Text type="secondary">{t('label.autoResolve')}</Text>
        return (
          <span title={ids.join(', ')}>
            {ids.map((d) => deviceNames[d] || d).join('、')}
          </span>
        )
      },
    },
    {
      title: t('col.nodes'), dataIndex: 'node_count', key: 'node_count', width: 80,
    },
  ]

  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space size={[6, 4]} wrap>
        <Tag color="processing">t('label.planLoopShort') {plan?.plan_loop_count ?? 1} {t('label.times')}</Tag>
        <Tag>t('label.maxParallel') {plan?.max_parallel ?? '-'}</Tag>
        <Tag>t('label.onErrorColon'){ON_ERROR_LABEL(t)[plan?.on_error] || plan?.on_error || '-'}</Tag>
        <Tag>t('label.planItems') {items.length}</Tag>
      </Space>
      {items.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('msg.noPlanItems')}
          style={{ padding: '12px 0', margin: 0 }}
        />
      ) : (
        <DataTable
          rowKey="id"
          size="small"
          dataSource={items}
          columns={columns}
          pagination={false}
          scroll={{ x: 880 }}
        />
      )}
    </Space>
  )
}

export default function ProjectManager() {
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [loading, setLoading] = useState(false)
  const [sections, setSections] = useState<string[]>(ALL_SECTIONS)
  const [mode, setMode] = useState<'merge' | 'replace'>('merge')

  const [saveOpen, setSaveOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const [keepModels, setKeepModels] = useState(true)
  const [newResult, setNewResult] = useState<any>(null)
  // ---- 项目向导 ----
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState(0)
  const [wizardName, setWizardName] = useState('')
  const [wizardSections, setWizardSections] = useState<string[]>(
    PROJECT_SECTIONS.map((s) => s.key),
  )
  const [importResult, setImportResult] = useState<any>(null)
  const [busy, setBusy] = useState<string>('')
  // ---- 工程树 + 配置预览 ----
  const [selected, setSelected] = useState('')
  const [expanded, setExpanded] = useState<string[]>([])
  const [detail, setDetail] = useState<any>(null)
  const [detailName, setDetailName] = useState('')
  const [detailLoading, setDetailLoading] = useState(false)

  const [saveForm] = Form.useForm()
  const [renameForm] = Form.useForm()
  const renamingRef = useRef<string>('')
  const { t } = useI18n()

  const load = async () => {
    setLoading(true)
    try {
      const res = await projectAPI.list()
      setProjects(extractData(res, []))
    } catch (err) {
      handleApiError(err, t('msg.loadProjectsFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const sectionArg = () => (sections.length === ALL_SECTIONS.length ? undefined : sections)

  /** Trigger a browser download for a JSON payload. */
  const download = (filename: string, data: any) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // ---- 导出：把当前系统配置下载成文件 ----
  const handleExport = async () => {
    setBusy('export')
    try {
      const res = await projectAPI.exportBundle({ sections: sectionArg() })
      const bundle: any = extractData(res, null) || {}
      download(`Project_${bundle.project_name || 'export'}.json`, bundle)
      message.success(t('msg.exportedCurrent'))
    } catch (err) {
      handleApiError(err, t('msg.exportFailed'))
    } finally {
      setBusy('')
    }
  }

  // ---- 另存为：导出并同时存一份到服务端 ----
  const handleSaveAs = async () => {
    let name = ''
    try {
      const values = await saveForm.validateFields()
      name = (values.name || '').trim()
    } catch {
      return
    }
    setBusy('save')
    try {
      await projectAPI.save(name, sectionArg())
      message.success(`${t('msg.savedAsPrefix')}${name}」`)
      setSaveOpen(false)
      saveForm.resetFields()
      load()
    } catch (err) {
      handleApiError(err, t('msg.saveAsFailed'))
    } finally {
      setBusy('')
    }
  }

  // ---- 导入：把 bundle 写回系统 ----
  const applyBundle = async (bundle: any, from: string) => {
    setBusy('import')
    setImportResult(null)
    try {
      const res = await projectAPI.importBundle(bundle, sectionArg(), mode)
      const data: any = res.data?.data || res.data
      setImportResult({ ...data, from })
      message.success(`${t('msg.fromPrefix')}${from}」${t('btn.importConfig')}`)
      load()
    } catch (err) {
      const detail = _errorMessage(err, t('msg.importFailed'))
      message.error(detail, 6)
      setImportResult({ error: detail, from })
    } finally {
      setBusy('')
    }
  }

  const handleUpload = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const bundle = JSON.parse(String(reader.result))
        applyBundle(bundle, file.name)
      } catch {
        message.error(t('msg.notValidJson'))
      }
    }
    reader.onerror = () => message.error(t('msg.readFileFailed'))
    reader.readAsText(file)
    return false // prevent antd from uploading it
  }

  const handleImportSaved = async (row: ProjectRow) => {
    try {
      const res = await projectAPI.get(row.name)
      applyBundle(extractData(res, null), row.name)
    } catch (err) {
      handleApiError(err, t('msg.readProjectFailed'))
    }
  }

  const handleDownloadSaved = async (row: ProjectRow) => {
    try {
      const res = await projectAPI.get(row.name)
      download(row.file_name, extractData(res, null))
    } catch (err) {
      handleApiError(err, t('msg.downloadFailed'))
    }
  }

  const handleRename = async () => {
    let newName = ''
    try {
      const values = await renameForm.validateFields()
      newName = (values.new_name || '').trim()
    } catch {
      return
    }
    try {
      await projectAPI.rename(renamingRef.current, newName)
      message.success(t('msg.renamed'))
      setRenameOpen(false)
      renameForm.resetFields()
      load()
    } catch (err) {
      handleApiError(err, t('msg.renameFailed'))
    }
  }

  // ---- 项目向导：选段 → 命名 → 生成 ----
  const openWizard = () => {
    setWizardStep(0)
    setWizardName('')
    setWizardSections(PROJECT_SECTIONS.map((s) => s.key))
    setWizardOpen(true)
  }

  const handleWizardFinish = async () => {
    const name = wizardName.trim()
    if (!name) {
      message.warning(t('msg.enterProjectName'))
      return
    }
    setBusy('wizard')
    try {
      await projectAPI.save(name, wizardSections)
      message.success(`${t('label.projectPrefix')}${name}」t('msg.createdParen')}${wizardSections.length} ${t('unit.sectionsParen')}`)
      setWizardOpen(false)
      load()
    } catch (err) {
      handleApiError(err, t('msg.createProjectFailed'))
    } finally {
      setBusy('')
    }
  }

  // ---- 新建项目工程：清空工作区（默认保留 AI 模型配置）----
  const handleNewProject = async () => {
    setBusy('new')
    setNewResult(null)
    try {
      const res = await projectAPI.newProject(undefined, keepModels)
      const data: any = res.data?.data || res.data
      setNewResult(data)
      message.success(`${t('msg.cleared')} ${data.total_cleared} ${t('msg.clearedReady')}`)
      setNewOpen(false)
      load()
    } catch (err) {
      handleApiError(err, t('msg.newProjectFailed'))
    } finally {
      setBusy('')
    }
  }

  const handleSync = async (row: ProjectRow) => {
    setBusy('sync:' + row.name)
    try {
      await projectAPI.sync(row.name, sectionArg())
      message.success(`${t('msg.overwrotePrefix')}${row.name}」`)
      load()
    } catch (err) {
      handleApiError(err, t('msg.syncFailed'))
    } finally {
      setBusy('')
    }
  }

  const handleDelete = async (row: ProjectRow) => {
    try {
      await projectAPI.remove(row.name)
      message.success(t('msg.deleted'))
      if (detailName === row.name) {
        setDetail(null)
        setDetailName('')
        setSelected('')
      }
      load()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
    }
  }

  // ---- 工程树：选中后主页面展示该工程的全部配置 ----

  const loadDetail = async (name: string) => {
    setDetailLoading(true)
    setDetailName(name)
    try {
      const res = await projectAPI.get(name)
      setDetail(extractData(res, null))
    } catch (err) {
      handleApiError(err, t('msg.readProjectError'))
      setDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  const activeRow = projects.find((p) => p.name === detailName) || null
  const activeSection = selected ? parseTreeKey(selected).section : null
  const visibleSections = PROJECT_SECTIONS.filter(
    (s) => !activeSection || s.key === activeSection,
  )

  // 计划项只存 testcase_id / device_id，展示前先从同一份 bundle 里把名字解析出来。
  const caseNames = useMemo(() => {
    const m: Record<string, string> = {}
    for (const tc of detail?.data?.test_cases || []) m[tc.id] = tc.name
    return m
  }, [detail])

  const deviceNames = useMemo(() => {
    const m: Record<string, string> = {}
    for (const d of detail?.data?.devices || []) m[d.id] = d.name || d.device_key || d.id
    return m
  }, [detail])

  // Open on the most recent project so the page is useful straight away
  // instead of showing an empty pane until the user clicks.
  useEffect(() => {
    if (projects.length === 0 || detailName) return
    const first = projects[0].name
    setSelected(`p:${first}`)
    setExpanded([`p:${first}`])
    loadDetail(first)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects, detailName])

  const treeData = projects.map((p) => {
    const total = PROJECT_SECTIONS.reduce((n, s) => n + (p.counts?.[s.key] ?? 0), 0)
    return {
      key: `p:${p.name}`,
      title: (
        <Space size={4}>
          <FileTextOutlined />
          <Text strong style={{ fontSize: 13 }}>{p.name}</Text>
          {p.app_version && <Tag color="processing" style={{ fontSize: 10 }}>v{p.app_version}</Tag>}
          {p.error && <Tag color="red">{t('label.corrupted')}</Tag>}
          <Text type="secondary" style={{ fontSize: 11 }}>{total} {t('label.items')}</Text>
        </Space>
      ),
      children: PROJECT_SECTIONS.map((s) => {
        const n = p.counts?.[s.key] ?? 0
        return {
          key: `s:${p.name}:${s.key}`,
          title: (
            <Space size={4}>
              <Text style={{ fontSize: 12, opacity: n ? 1 : 0.45 }}>{s.label}</Text>
              <Text type="secondary" style={{ fontSize: 11 }}>{n}</Text>
            </Space>
          ),
        }
      }),
    }
  })


  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>{t('project.title')}</Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('common.refresh')}
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('project.bundleDesc')}
        description={t('project.keyFull')}
      />

      <Card title={t('common.actions')} style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Text strong style={{ marginRight: 8 }}>{t('project.sections')}</Text>
            <Checkbox.Group
              options={PROJECT_SECTIONS.map((s) => ({ label: s.label, value: s.key }))}
              value={sections}
              onChange={(v) => setSections(v as string[])}
            />
          </div>
          <Divider style={{ margin: '4px 0' }} />
          <Space wrap>
            <Button
              type="primary" icon={<DownloadOutlined />}
              loading={busy === 'export'}
              onClick={handleExport}
            >
              {t('project.export')}
            </Button>
            <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>
              {t('project.saveAs')}
            </Button>
            <Button danger icon={<FileAddOutlined />} onClick={() => setNewOpen(true)}>
              {t('project.new')}
            </Button>
            <Tooltip title={t('tip.wizardFull')}>
              <Button icon={<ThunderboltOutlined />} onClick={openWizard}>{t('btn.wizard')}</Button>
            </Tooltip>
            <Upload
              beforeUpload={handleUpload}
              showUploadList={false}
              accept=".json,application/json"
            >
              <Button icon={<UploadOutlined />} loading={busy === 'import'}>
                {t('project.importFile')}
              </Button>
            </Upload>
            <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
              <Radio value="merge">{t('project.merge')}</Radio>
              <Radio value="replace">{t('project.replace')}</Radio>
            </Radio.Group>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('project.mergeDesc')}
            {t('project.replaceDesc')}
          </Text>
        </Space>
      </Card>

      {importResult && (
        <Card title={t('project.importResult')} size="small" style={{ marginBottom: 16 }}>
          {importResult.error ? (
            <Alert type="error" showIcon message={importResult.error} />
          ) : (
            <Space direction="vertical" size={4}>
              <Text>t('label.sourceColon'){importResult.from}　t('label.modeColon'){importResult.mode}</Text>
              <Space size={[6, 6]} wrap>
                {Object.entries(importResult.sections || {}).map(([key, v]: any) => (
                  <Tag
                    key={key}
                    color={v.created > 0 ? 'green' : 'blue'}
                  >
                    {PROJECT_SECTIONS.find((s) => s.key === key)?.label || key}
                    ：t('common.create') {v.created} / t('label.updated') {v.updated}
                    {v.skipped > 0 && ` / ${t('status.skip')} ${v.skipped}`}
                  </Tag>
                ))}
              </Space>
            </Space>
          )}
        </Card>
      )}

      {newResult && (
        <Card title={t('project.newResult')} size="small" style={{ marginBottom: 16 }}>
          <Space direction="vertical" size={4}>
            <Text>{t('project.clearedTotal', { n: newResult.total_cleared })}</Text>
            <Space size={[6, 6]} wrap>
              {Object.entries(newResult.cleared || {}).map(([key, n]: any) => (
                <Tag key={key} color="red">
                  {PROJECT_SECTIONS.find((s) => s.key === key)?.label || key}：{n}
                </Tag>
              ))}
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('project.kept')}{(newResult.kept || [])
                .map((k: string) => PROJECT_SECTIONS.find((s) => s.key === k)?.label || k)
                .join('、') || t('label.none')}
            </Text>
          </Space>
        </Card>
      )}

      {/* ---- Project tree (left) + project configuration (right) ----
          expand a project to view a single section. */}
      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <Card
          title={t('project.saved')}
          size="small"
          style={{ width: 300, flex: '0 0 300px' }}
          styles={{ body: { padding: '8px 12px', maxHeight: 'calc(100vh - 220px)', overflow: 'auto' } }}
        >
          {projects.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('msg.noProjects')}
              style={{ padding: '16px 0' }}
            >
              <Button type="primary" onClick={() => setSaveOpen(true)}>{t('btn.saveAsProject')}</Button>
            </Empty>
          ) : (
            <Tree
              blockNode
              treeData={treeData}
              expandedKeys={expanded}
              onExpand={(keys) => setExpanded(keys as string[])}
              selectedKeys={selected ? [selected] : []}
              onSelect={(keys) => {
                const key = String(keys[0] || '')
                if (!key) {
                  setSelected('')
                  return
                }
                setSelected(key)
                const { name } = parseTreeKey(key)
                if (name !== detailName) loadDetail(name)
              }}
            />
          )}
        </Card>

        <div style={{ flex: 1, minWidth: 0 }}>
          {activeRow ? (
            <Card
              size="small"
              loading={detailLoading}
              title={(
                <Space size={6} wrap>
                  <FileTextOutlined />
                  <Text strong>{activeRow.name}</Text>
                  {activeRow.app_version && <Tag color="processing">v{activeRow.app_version}</Tag>}
                  {activeSection && (
                    <Tag>
                      {PROJECT_SECTIONS.find((s) => s.key === activeSection)?.label || activeSection}
                    </Tag>
                  )}
                </Space>
              )}
              extra={(
                <Space wrap size={4}>
                  <Button
                    size="small" icon={<ImportOutlined />}
                    disabled={!!activeRow.error}
                    onClick={() => handleImportSaved(activeRow)}
                  >
                    {t('common.import')}
                  </Button>
                  <Button
                    size="small" icon={<DownloadOutlined />}
                    onClick={() => handleDownloadSaved(activeRow)}
                  >
                    {t('common.download')}
                  </Button>
                  <Button
                    size="small" icon={<SyncOutlined />}
                    loading={busy === 'sync:' + activeRow.name}
                    onClick={() => handleSync(activeRow)}
                  >{t('btn.overwriteSync')}</Button>
                  <Button
                    size="small" icon={<EditOutlined />}
                    onClick={() => {
                      renamingRef.current = activeRow.name
                      setRenameOpen(true)
                    }}
                  >
                    {t('common.rename')}
                  </Button>
                  <Popconfirm
                    title={`${t('msg.deleteProjectPrefix')}${activeRow.name}」？`}
                    onConfirm={() => handleDelete(activeRow)}
                  >
                    <Button size="small" danger icon={<DeleteOutlined />}>{t('common.delete')}</Button>
                  </Popconfirm>
                </Space>
              )}
            >
              <Space direction="vertical" size={2} style={{ marginBottom: 12 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {activeRow.file_name} · {(activeRow.size / 1024).toFixed(1)} KB
                  {activeRow.exported_at
                    && ` · ${t('label.exportedAt')} ${new Date(activeRow.exported_at).toLocaleString('zh-CN')}`}
                </Text>
                {activeRow.error && <Alert type="error" showIcon message={activeRow.error} />}
              </Space>

              {detail && (
                <Space size={[6, 6]} wrap style={{ marginBottom: 12 }}>
                  {PROJECT_SECTIONS.map((s) => {
                    const n = detail?.data?.[s.key]?.length ?? activeRow.counts?.[s.key] ?? 0
                    return (
                      <Tag
                        key={s.key}
                        color={n > 0 ? 'processing' : 'default'}
                        style={{ cursor: 'pointer' }}
                        onClick={() => {
                          setSelected(`s:${activeRow.name}:${s.key}`)
                          setExpanded((ks) => Array.from(new Set([...ks, `p:${activeRow.name}`])))
                        }}
                      >
                        {s.label} {n}
                      </Tag>
                    )
                  })}
                </Space>
              )}

              {detail ? (
                visibleSections.map((s) => {
                  const rows = detail?.data?.[s.key] || []
                  return (
                    <Card
                      key={s.key}
                      type="inner"
                      size="small"
                      title={`${s.label}（${rows.length}）`}
                      style={{ marginBottom: 12 }}
                    >
          {/* Dashboards are unreadable as raw parameters — draw the layout instead */}
                      {s.key === 'dashboards' ? (
                        <Space direction="vertical" size={16} style={{ width: '100%' }}>
                          {rows.map((d: any) => (
                            <div key={d.id}>
                              <Text strong style={{ fontSize: 13 }}>{d.name}</Text>
                              {d.is_default && <Tag color="processing" style={{ marginLeft: 6 }}>{t('status.default')}</Tag>}
                              {d.description && (
                                <div>
                                  <Text type="secondary" style={{ fontSize: 12 }}>{d.description}</Text>
                                </div>
                              )}
                              <div style={{ marginTop: 8 }}>
                                <DashboardPreview dashboard={d} />
                              </div>
                            </div>
                          ))}
                          {rows.length === 0 && (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('msg.sectionEmpty')} />
                          )}
                        </Space>
                      ) : s.key === 'execution_plans' ? (
                        /* 计划本身信息太少，展开计划项并解析出测试用例名称 */
                        <Space direction="vertical" size={16} style={{ width: '100%' }}>
                          {rows.map((p: any) => (
                            <div key={p.id}>
                              <Text strong style={{ fontSize: 13 }}>{p.name}</Text>
                              {p.description && (
                                <div>
                                  <Text type="secondary" style={{ fontSize: 12 }}>{p.description}</Text>
                                </div>
                              )}
                              <div style={{ marginTop: 8 }}>
                                <PlanPreview
                                  plan={p}
                                  caseNames={caseNames}
                                  deviceNames={deviceNames}
                                />
                              </div>
                            </div>
                          ))}
                          {rows.length === 0 && (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('msg.sectionEmpty')} />
                          )}
                        </Space>
                      ) : (
                        <SectionTable rows={rows} />
                      )}
                    </Card>
                  )
                })
              ) : (
                !detailLoading && (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('msg.cannotReadProject')}
                  />
                )
              )}
            </Card>
          ) : (
            <Card size="small">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('msg.pickProject')}
              />
            </Card>
          )}
        </div>
      </div>

      <Modal
        title={t('project.saveAs')}
        open={saveOpen}
        onOk={handleSaveAs}
        confirmLoading={busy === 'save'}
        onCancel={() => setSaveOpen(false)}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
      >
        <Form form={saveForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label={t('label.projectName')}
            rules={[{ required: true, message: t('msg.enterProjectName') }]}
            extra={`${t('ph.savedAsProject')}_${t('col.name')}.json（${t('label.currentlyContains')} ${sections.length} ${t('unit.section')}${t('common.configure')}）`}
          >
            <Input placeholder={t('ph.projectExampleCan')} autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      {/* Project wizard: pick sections → name → generate */}
      <Modal
        title={t('btn.wizard')}
        open={wizardOpen}
        onCancel={() => setWizardOpen(false)}
        width={620}
        footer={[
          <Button key="back" disabled={wizardStep === 0}
            onClick={() => setWizardStep((s) => s - 1)}>{t('btn.prev')}</Button>,
          wizardStep < 2 ? (
            <Button key="next" type="primary" onClick={() => setWizardStep((s) => s + 1)}>{t('btn.next')}</Button>
          ) : (
            <Button key="done" type="primary" loading={busy === 'wizard'}
              onClick={handleWizardFinish}>{t('btn.generateProject')}</Button>
          ),
        ]}
      >
        <Steps
          size="small" current={wizardStep} style={{ marginBottom: 20 }}
          items={[{ title: t('wizard.selectSections') }, { title: t('wizard.nameProject') }, { title: t('wizard.confirm') }]}
        />

        {wizardStep === 0 && (
          <div>
            <Text type="secondary">{t('wizard.pickSections')}</Text>
            <div style={{ marginTop: 10 }}>
              <Checkbox.Group
                options={PROJECT_SECTIONS.map((s) => ({ label: s.label, value: s.key }))}
                value={wizardSections}
                onChange={(v) => setWizardSections(v as string[])}
              />
            </div>
          </div>
        )}

        {wizardStep === 1 && (
          <div>
            <Text type="secondary">t('ph.nameProject')_&lt;t('col.name')&gt;.json）：</Text>
            <Input
              style={{ marginTop: 10 }}
              value={wizardName}
              onChange={(e) => setWizardName(e.target.value)}
              placeholder={t('ph.wizardExample')}
              onPressEnter={() => setWizardStep(2)}
            />
          </div>
        )}

        {wizardStep === 2 && (
          <div>
            <Text strong>{t('label.aboutToCreateColon')}</Text>
            <div style={{ marginTop: 8 }}>
              <div>{t('label.projectFileColon')}<Text code>Project_{wizardName.trim() || `（${t('label.unnamed')}`}.json</Text></div>
              <div style={{ marginTop: 6 }}>
                {t('label.sectionsColon')}
                {wizardSections.length === 0
                  ? <Text type="danger">{t('msg.noSectionSelected')}</Text>
                  : wizardSections.map((k) => (
                      <Tag key={k} color="blue">
                        {PROJECT_SECTIONS.find((s) => s.key === k)?.label || k}
                      </Tag>
                    ))}
              </div>
            </div>
            <Alert
              type="info" showIcon style={{ marginTop: 12 }}
              message={t('project.createNoSideEffect')}
              description={t('project.wizardNote')}
            />
          </div>
        )}
      </Modal>

      <Modal
        title={t('project.newTitle')}
        open={newOpen}
        onOk={handleNewProject}
        confirmLoading={busy === 'new'}
        onCancel={() => setNewOpen(false)}
        okText={t('common.confirm')}
        okButtonProps={{ danger: true }}
        cancelText={t('common.cancel')}
        width={560}
      >
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message={t('project.clearWarn')}
          description={t('project.newWarn')}
        />
        <Checkbox
          checked={keepModels}
          onChange={(e) => setKeepModels(e.target.checked)}
        >{t('label.keepModels')}</Checkbox>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            AI {t('project.envNote')}
            {t('skill.disableNote')}
          </Text>
        </div>
        <div style={{ marginTop: 12 }}>
          <Text strong>{t('label.willBeClearedColon')}</Text>
          <div style={{ marginTop: 6 }}>
            {PROJECT_SECTIONS.filter((s) => s.key !== 'models').map((s) => (
              <Tag key={s.key} color="red">{s.label}</Tag>
            ))}
            {!keepModels && <Tag color="red">{t('page.modelConfig')}</Tag>}
          </div>
        </div>
      </Modal>

      <Modal
        title={t('common.rename')}
        open={renameOpen}
        onOk={handleRename}
        onCancel={() => setRenameOpen(false)}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
      >
        <Form form={renameForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="new_name"
            label={t('label.newName')}
            rules={[{ required: true, message: t('msg.enterNewName') }]}
          >
            <Input autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
