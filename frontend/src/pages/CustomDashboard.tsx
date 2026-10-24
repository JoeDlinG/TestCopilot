import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { usePolling } from '../hooks/usePolling'
import {
  Button, Space, Select, Drawer, Card, Typography, message, Spin, Empty,
  InputNumber, Popconfirm, Upload, Tag, Divider,
} from 'antd'
import {
  PlusOutlined, SaveOutlined, LockOutlined, UnlockOutlined,
  SettingOutlined, DeleteOutlined, CopyOutlined, FullscreenOutlined,
  FullscreenExitOutlined, ReloadOutlined, ImportOutlined, ExportOutlined,
  DragOutlined,
} from '@ant-design/icons'
import RGL, { WidthProvider, Layout } from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

import { dashboardAPI, testCaseAPI, logAPI } from '../services/api'
import type {
  CustomDashboard, DashboardWidget, DashboardLayoutItem, DashboardSnapshot, WidgetType,
} from '../types'
import { useI18n } from '../i18n'
import { handleApiError } from '../services/apiHelper'
import { WIDGET_LIST, newWidget, STATUS_COLOR } from '../components/dashboard/registry'
import { WidgetBody } from '../components/dashboard/widgets'
import WidgetConfigDrawer from '../components/dashboard/WidgetConfigDrawer'

const { Title, Text } = Typography
const WidthProviderGrid = WidthProvider(RGL)

const GRID_COLS = 12
const ROW_HEIGHT = 40

export default function CustomDashboard() {
  const { t } = useI18n()
  const [loading, setLoading] = useState(true)
  const [dashboards, setDashboards] = useState<CustomDashboard[]>([])
  const [current, setCurrent] = useState<CustomDashboard | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  const [testCases, setTestCases] = useState<any[]>([])
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [logsLoading, setLogsLoading] = useState(false)

  const [libOpen, setLibOpen] = useState(false)
  const [cfgWidget, setCfgWidget] = useState<DashboardWidget | null>(null)
  const [big, setBig] = useState(false)

  const currentRef = useRef<CustomDashboard | null>(null)
  currentRef.current = current

  // live (real-time) refresh: one WebSocket per running execution of the
  // bound test case. Execution events push an immediate debounced snapshot.
  const wsRef = useRef<Record<string, WebSocket>>({})
  const wsDebounceRef = useRef<number | null>(null)

  /* ---------------- loaders ---------------- */
  const loadDashboards = useCallback(async () => {
    setLoading(true)
    try {
      const res = await dashboardAPI.list()
      const list: CustomDashboard[] = res.data?.data || []
      setDashboards(list)
      if (!list.length) {
        setCurrent(null)
        return
      }
      const keepId = currentRef.current?.id
      const next = list.find((d) => d.id === keepId)
        || list.find((d) => d.is_default)
        || list[0]
      setCurrent(next)
      setDirty(false)
    } catch (e) {
      message.error(t('msg.loadDashboardsFailed'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadDashboards() }, [loadDashboards])

  useEffect(() => {
    testCaseAPI.list()
      .then((r) => setTestCases(r.data?.data?.items || r.data?.data || []))
      .catch(() => setTestCases([]))
  }, [])

  const loadSnapshot = useCallback(async () => {
    const d = currentRef.current
    try {
      const res = await dashboardAPI.snapshot(
        d?.data_source?.test_case_id || null,
        Number(d?.data_source?.limit) || 50,
        d?.data_source?.since || null,
      )
      setSnapshot(res.data?.data || null)
    } catch (e) {
      // Keep the last snapshot on transient errors, but DO surface the failure:
      // silently swallowing it left every widget showing "pick a test case"
      // while the real cause was a rejected request (see issue: `since` 400).
      handleApiError(e, t('msg.loadSnapshotFailed'))
    }
  }, [])

  const loadLogs = useCallback(async () => {
    const d = currentRef.current
    if (!d?.widgets?.some((w) => w.type === 'comm_log')) return
    setLogsLoading(true)
    try {
      const commWidgets = d.widgets.filter((w) => w.type === 'comm_log')
      const maxLimit = Math.max(...commWidgets.map((w) => Number(w.config?.limit) || 12), 12)
      const params: any = { page: 1, page_size: Math.min(maxLimit, 50) }
      const devId = commWidgets.find((w) => w.config?.device_id)?.config?.device_id
      if (devId) params.device_id = devId
      const res = await logAPI.list(params)
      const data = res.data?.data
      setLogs(Array.isArray(data) ? data : (data?.items || []))
    } catch {
      /* ignore */
    } finally {
      setLogsLoading(false)
    }
  }, [])

  // initial load + refresh whenever the selected dashboard / data source changes
  useEffect(() => {
    if (!current) return
    loadSnapshot()
    loadLogs()
  }, [current?.id, current?.data_source?.test_case_id, current?.data_source?.limit,
      current?.data_source?.since, loadSnapshot, loadLogs])

  // auto refresh
  const refreshSec = Number(current?.data_source?.refresh_sec) || 10
  usePolling(() => {
    loadSnapshot()
    loadLogs()
  }, Math.max(2, refreshSec) * 1000, !!current)

  // ---- real-time: subscribe to running executions via WebSocket ----
  const liveRefresh = useCallback(() => {
    if (wsDebounceRef.current) window.clearTimeout(wsDebounceRef.current)
    wsDebounceRef.current = window.setTimeout(() => {
      loadSnapshot()
      loadLogs()
    }, 400)
  }, [loadSnapshot, loadLogs])

  useEffect(() => {
    const d = currentRef.current
    const tcId = d?.data_source?.test_case_id
    if (!tcId) return
    const running = (snapshot?.executions?.recent || [])
      .filter((e: any) => e.status === 'running' && e.test_case_id === tcId)
      .map((e: any) => e.id)
    const want = new Set(running)
    // close sockets for executions that finished / no longer match
    Object.keys(wsRef.current).forEach((id) => {
      if (!want.has(id)) {
        try { wsRef.current[id].close() } catch { /* ignore */ }
        delete wsRef.current[id]
      }
    })
    // open sockets for newly running executions
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname || 'localhost'
    want.forEach((id) => {
      if (wsRef.current[id]) return
      const ws = new WebSocket(`${proto}//${host}:8000/ws/executions/${id}`)
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if ([
            'step_started', 'step_completed', 'step_failed',
            'execution_completed', 'execution_stopped', 'execution_error',
          ].includes(msg.type)) {
            liveRefresh()
          }
        } catch { /* ignore */ }
      }
      wsRef.current[id] = ws
    })
  }, [snapshot?.executions?.recent, current?.data_source?.test_case_id, liveRefresh])

  // close every socket when leaving the page
  useEffect(() => () => {
    Object.values(wsRef.current).forEach((ws) => { try { ws.close() } catch { /* ignore */ } })
    if (wsDebounceRef.current) window.clearTimeout(wsDebounceRef.current)
  }, [])

  /* ---------------- mutations ---------------- */
  const patchCurrent = (patch: Partial<CustomDashboard>) => {
    setCurrent((prev) => (prev ? { ...prev, ...patch } : prev))
    setDirty(true)
  }

  const layoutOf = useMemo<DashboardLayoutItem[]>(
    () => current?.layout || [],
    [current?.layout],
  )
  const widgetsOf = useMemo<DashboardWidget[]>(
    () => current?.widgets || [],
    [current?.widgets],
  )

  const addWidget = (type: WidgetType) => {
    const w = newWidget(type)
    const maxY = layoutOf.reduce((m, l) => Math.max(m, l.y + l.h), 0)
    const item: DashboardLayoutItem = {
      i: w.id, x: 0, y: maxY,
      w: Math.min(GRID_COLS, WIDGET_LIST.find((m) => m.type === type)?.size.w || 6),
      h: WIDGET_LIST.find((m) => m.type === type)?.size.h || 4,
      minW: 2, minH: 2,
    }
    patchCurrent({ widgets: [...widgetsOf, w], layout: [...layoutOf, item] })
    setLibOpen(false)
    message.success(t('msg.widgetAdded'))
  }

  const updateWidget = (w: DashboardWidget) => {
    patchCurrent({ widgets: widgetsOf.map((x) => (x.id === w.id ? w : x)) })
  }

  const removeWidget = (id: string) => {
    patchCurrent({
      widgets: widgetsOf.filter((x) => x.id !== id),
      layout: layoutOf.filter((l) => l.i !== id),
    })
  }

  const duplicateWidget = (id: string) => {
    const src = widgetsOf.find((x) => x.id === id)
    const srcItem = layoutOf.find((l) => l.i === id)
    if (!src) return
    const copy: DashboardWidget = {
      ...src,
      id: `w_${Math.random().toString(36).slice(2, 9)}`,
      title: `${src.title} ${t('label.copySuffix')}`,
      config: { ...src.config },
    }
    const item: DashboardLayoutItem = {
      ...(srcItem || { x: 0, w: 6, h: 4 }),
      i: copy.id,
      y: (srcItem?.y ?? 0) + (srcItem?.h ?? 4),
      minW: 2, minH: 2,
    }
    patchCurrent({ widgets: [...widgetsOf, copy], layout: [...layoutOf, item] })
  }

  const onLayoutChange = (next: Layout[]) => {
    if (!editMode) return
    const cleaned: DashboardLayoutItem[] = next.map((l) => ({
      i: String(l.i), x: l.x, y: l.y, w: l.w, h: l.h, minW: l.minW ?? 2, minH: l.minH ?? 2,
    }))
    // react-grid-layout fires this on mount too — only mark dirty on real moves
    const key = (arr: DashboardLayoutItem[]) =>
      arr.map((l) => `${l.i}:${l.x},${l.y},${l.w},${l.h}`).sort().join('|')
    if (key(cleaned) !== key(layoutOf)) {
      patchCurrent({ layout: cleaned })
    }
  }

  const save = async () => {
    if (!current) return
    setSaving(true)
    try {
      const payload = {
        name: current.name,
        description: current.description,
        layout: current.layout,
        widgets: current.widgets,
        data_source: current.data_source,
      }
      const res = await dashboardAPI.update(current.id, payload)
      setCurrent(res.data?.data || current)
      setDirty(false)
      message.success(t('msg.saved'))
      await loadDashboards()
    } catch {
      message.error(t('msg.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  /**
   * 执行统计组件的「起始时间 / 清零」。
   * Persisted on the dashboard's data source so the window survives a reload —
   * and pushed straight to the backend because the counts are computed there.
   */
  const updateSince = async (iso: string | null) => {
    if (!current) return
    const next = {
      ...current,
      data_source: { ...current.data_source, since: iso },
    }
    setCurrent(next)
    try {
      await dashboardAPI.update(current.id, {
        name: next.name,
        description: next.description,
        layout: next.layout,
        widgets: next.widgets,
        data_source: next.data_source,
      })
      loadSnapshot()
    } catch {
      message.error(t('msg.saveFailed'))
    }
  }

  const createDashboard = async () => {
    const name = window.prompt(t('ph.dashboardName'), t('ph.myDashboard'))
    if (!name) return
    try {
      await dashboardAPI.create({
        name,
        layout: [],
        widgets: [],
        data_source: { test_case_id: null, limit: 50, refresh_sec: 10 },
      })
      await loadDashboards()
      setEditMode(true)
      message.success(t('msg.dashCreated'))
    } catch {
      message.error(t('msg.createFailed'))
    }
  }

  /* ---------------- big screen ---------------- */
  const enterBig = async () => {
    setBig(true)
    try { await document.documentElement.requestFullscreen() } catch { /* ignore */ }
  }
  const exitBig = async () => {
    setBig(false)
    try { if (document.fullscreenElement) await document.exitFullscreen() } catch { /* ignore */ }
  }
  useEffect(() => {
    const onChange = () => { if (!document.fullscreenElement) setBig(false) }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  /* ---------------- render helpers ---------------- */
  const renderWidgetCard = (w: DashboardWidget, bigMode: boolean) => {
    const cfgId = w.id
    const st = (w.type === 'parsed_value' && snapshot?.parsed?.latest?.[w.config?.field]?.status) || null
    const borderColor = st ? STATUS_COLOR[st] : undefined
    return (
      <div
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          background: bigMode ? 'rgba(255,255,255,0.06)' : 'var(--app-surface)',
          border: `1px solid ${bigMode ? 'rgba(255,255,255,0.12)' : (borderColor || 'var(--app-border)')}`,
          borderLeft: borderColor ? `4px solid ${borderColor}` : undefined,
          borderRadius: 8,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: bigMode ? '10px 16px' : '6px 10px',
            borderBottom: `1px solid ${bigMode ? 'rgba(255,255,255,0.10)' : 'var(--app-border)'}`,
            cursor: editMode && !bigMode ? 'move' : 'default',
            background: bigMode ? 'rgba(255,255,255,0.04)' : 'var(--app-surface-muted)',
            flexShrink: 0,
          }}
        >
          {/* Only the title is the drag handle — interactive buttons live
              OUTSIDE it so react-grid-layout's drag does not swallow clicks. */}
          <span
            className={editMode && !bigMode ? 'widget-drag-handle' : undefined}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontWeight: 600, fontSize: bigMode ? 20 : 14,
              color: bigMode ? 'var(--app-surface)' : undefined,
              flex: 1, minWidth: 0,
            }}
          >
            {editMode && !bigMode && <DragOutlined style={{ color: 'var(--app-fg-subtle)', flexShrink: 0 }} />}
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {w.title}
            </span>
          </span>
          {editMode && !bigMode && (
            <Space className="widget-actions" size={2}>
              <Button size="small" type="text" icon={<SettingOutlined />}
                onClick={() => setCfgWidget(w)} />
              <Button size="small" type="text" icon={<CopyOutlined />}
                onClick={() => duplicateWidget(cfgId)} />
              <Popconfirm title={t('msg.deleteWidget')} onConfirm={() => removeWidget(cfgId)}>
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          )}
        </div>
        <div style={{ flex: 1, minHeight: 0, padding: bigMode ? 16 : 10, overflow: 'auto', color: bigMode ? 'var(--app-surface)' : undefined }}>
          <WidgetBody
            widget={w}
            snapshot={snapshot}
            big={bigMode}
            logs={logs}
            logsLoading={logsLoading}
            since={current?.data_source?.since || null}
            onSinceChange={updateSince}
          />
        </div>
      </div>
    )
  }

  /* ---------------- big screen view ---------------- */
  if (big) {
    return (
      <div
        className="big-dash"
        style={{
          position: 'fixed', inset: 0, zIndex: 1200,
          background: 'var(--app-bigscreen-bg)', color: 'var(--app-on-dark)', padding: 24,
          display: 'flex', flexDirection: 'column', overflow: 'auto',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 28, fontWeight: 700 }}>
              {current?.name || t('page.customDashboard')}
            </div>
            <div style={{ fontSize: 14, opacity: 0.6, marginTop: 4 }}>
              {snapshot?.test_case_name ? `${t('label.dataSource')}${snapshot.test_case_name}` : t('label.noCaseBound')}
              {' · '}{t('label.every')} {refreshSec} {t('dash.autoRefreshSuffix')}
            </div>
          </div>
          <Space>
            <Button size="large" icon={<ReloadOutlined />} onClick={() => { loadSnapshot(); loadLogs() }}>{t('btn.refreshNow')}</Button>
            <Button size="large" type="primary" icon={<FullscreenExitOutlined />} onClick={exitBig}>{t('btn.exitBigScreen')}</Button>
          </Space>
        </div>
        {widgetsOf.length === 0 ? (
          <Empty description={t('dash.noWidgets')} style={{ marginTop: 80, color: 'var(--app-on-dark)' }} />
        ) : (
          <div style={{
            display: 'grid', gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`,
            gap: 16, alignItems: 'stretch',
          }}>
            {widgetsOf.map((w) => {
              const item = layoutOf.find((l) => l.i === w.id)
              const span = Math.min(GRID_COLS, Math.max(3, item?.w || 6))
              const hPx = Math.max(200, (item?.h || 5) * 62)
              return (
                <div key={w.id} style={{ gridColumn: `span ${span}`, height: hPx }}>
                  {renderWidgetCard(w, true)}
                </div>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  /* ---------------- normal view ---------------- */
  return (
    <div className="page-container">
      <style>{`
        .react-grid-item.react-grid-placeholder {
          background: var(--app-accent); opacity: .18; border-radius: 8px;
        }
        .widget-drag-handle { user-select: none; }
      `}</style>

      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>{t('page.customDashboard')}</Title>
          <Text type="secondary">{t('dash.composeDesc')}</Text>
        </div>
        <Space wrap>
          <Button
            type={editMode ? 'primary' : 'default'}
            icon={editMode ? <UnlockOutlined /> : <LockOutlined />}
            onClick={() => setEditMode(!editMode)}
          >
            {editMode ? t('label.editing') : t('label.locked')}
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setLibOpen(true)} disabled={!editMode}>{t('btn.addWidget')}</Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saving}
            onClick={save}
            disabled={!dirty}
          >
            {t('common.save')}{dirty ? `（${t('label.has')}${t('label.changes')}）` : ''}
          </Button>
          <Button icon={<FullscreenOutlined />} onClick={enterBig}>{t('btn.bigScreenShort')}</Button>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap size="middle">
          <Space size={6}>
            <Text strong>{t('page.dashboard')}</Text>
            <Select
              style={{ minWidth: 200 }}
              value={current?.id}
              onChange={(id: any) => {
                const d = dashboards.find((x) => x.id === id)
                if (d) { setCurrent(d); setDirty(false) }
              }}
              options={dashboards.map((d) => ({
                label: d.is_default ? `${d.name}（${t('status.default')}）` : d.name,
                value: d.id,
              }))}
            />
          </Space>

          <Space size={6}>
            <Text strong>{t('label.sourceCase')}</Text>
            <Select
              allowClear
              style={{ minWidth: 260 }}
              placeholder={t('label.pickCaseForParsers')}
              value={current?.data_source?.test_case_id || undefined}
              onChange={(v: any) => patchCurrent({
                data_source: { ...current!.data_source, test_case_id: v || null },
              })}
              options={testCases.map((t: any) => ({ label: t.name, value: t.id }))}
              showSearch
              optionFilterProp="label"
            />
          </Space>

          <Space size={6}>
            <Text strong>{t('label.viewCount')}</Text>
            <InputNumber
              min={1} max={500} style={{ width: 90 }}
              value={Number(current?.data_source?.limit) || 50}
              onChange={(v) => patchCurrent({
                data_source: { ...current!.data_source, limit: v ?? 50 },
              })}
            />
          </Space>

          <Space size={6}>
            <Text strong>{t('label.refreshSec')}</Text>
            <InputNumber
              min={2} max={600} style={{ width: 90 }}
              value={refreshSec}
              onChange={(v) => patchCurrent({
                data_source: { ...current!.data_source, refresh_sec: v ?? 10 },
              })}
            />
          </Space>

          <Divider type="vertical" />
          <Button size="small" icon={<ReloadOutlined />} onClick={() => { loadSnapshot(); loadLogs() }}>{t('common.refresh')}</Button>
          <Button size="small" icon={<PlusOutlined />} onClick={createDashboard}>{t('common.create')}</Button>
          <Popconfirm
            title={t('msg.dupDashboard')}
            onConfirm={async () => {
              if (!current) return
              const res = await dashboardAPI.duplicate(current.id)
              await loadDashboards()
              setCurrent(res.data?.data || null)
              message.success(t('msg.copied'))
            }}
          >
            <Button size="small" icon={<CopyOutlined />}>{t('common.copy')}</Button>
          </Popconfirm>
          <Button
            size="small"
            onClick={async () => {
              if (!current) return
              await dashboardAPI.setDefault(current.id)
              await loadDashboards()
              message.success(t('msg.setDefault'))
            }}
          >{t('btn.setDefault')}</Button>
          <Button
            size="small"
            icon={<ExportOutlined />}
            onClick={() => {
              if (!current) return
              const blob = new Blob([JSON.stringify(current, null, 2)], { type: 'application/json' })
              const a = document.createElement('a')
              a.href = URL.createObjectURL(blob)
              a.download = `${current.name}.json`
              a.click()
              URL.revokeObjectURL(a.href)
            }}
          >{t('common.export')}</Button>
          <Upload
            accept=".json"
            showUploadList={false}
            beforeUpload={async (file) => {
              try {
                const text = await file.text()
                const data = JSON.parse(text)
                const res = await dashboardAPI.importJson({
                  name: data.name || file.name.replace(/\.json$/, ''),
                  description: data.description,
                  layout: data.layout,
                  widgets: data.widgets,
                  data_source: data.data_source,
                })
                await loadDashboards()
                setCurrent(res.data?.data || null)
                message.success(t('msg.importOk'))
              } catch {
                message.error(t('msg.importInvalid'))
              }
              return false
            }}
          >
            <Button size="small" icon={<ImportOutlined />}>{t('common.import')}</Button>
          </Upload>
          <Popconfirm
            title={t('msg.deleteDashboard')}
            onConfirm={async () => {
              if (!current) return
              await dashboardAPI.delete(current.id)
              setCurrent(null)
              await loadDashboards()
              message.success(t('msg.deleted'))
            }}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>{t('common.delete')}</Button>
          </Popconfirm>
        </Space>
      </Card>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
          <Spin size="large" />
        </div>
      ) : !current ? (
        <Empty description={t('dash.none')} style={{ marginTop: 80 }} />
      ) : widgetsOf.length === 0 ? (
        <Empty
          description={
            <span>{t('dash.noWidgetsHint')}<Button type="link" size="small" onClick={() => { setEditMode(true); setLibOpen(true) }}>{t('btn.addWidget')}</Button>{t('btn.startComposing')}</span>
          }
          style={{ marginTop: 80 }}
        />
      ) : (
        <>
          {editMode && (
            <div style={{ marginBottom: 8 }}>
              <Tag color="blue">{t('dash.editHint')}</Tag>
            </div>
          )}
          <WidthProviderGrid
            className="layout"
            layout={layoutOf as Layout[]}
            cols={GRID_COLS}
            rowHeight={ROW_HEIGHT}
            isDraggable={editMode}
            isResizable={editMode}
            draggableHandle=".widget-drag-handle"
            draggableCancel=".widget-actions"
            onLayoutChange={onLayoutChange}
            margin={[12, 12]}
            containerPadding={[0, 0]}
            useCSSTransforms
          >
            {widgetsOf.map((w) => (
              <div key={w.id}>
                {renderWidgetCard(w, false)}
              </div>
            ))}
          </WidthProviderGrid>
        </>
      )}

      <Drawer
        title={t('card.widgetLibrary')}
        open={libOpen}
        onClose={() => setLibOpen(false)}
        width={420}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {WIDGET_LIST.map((m) => (
            <Card
              key={m.type}
              size="small"
              hoverable
              onClick={() => addWidget(m.type)}
              style={{ cursor: 'pointer' }}
            >
              <Space align="start">
                <span style={{ fontSize: 20 }}>{m.icon}</span>
                <div>
                  <div style={{ fontWeight: 600 }}>
                    {m.label}
                {m.needsTestCase && <Tag color="orange" style={{ marginLeft: 6 }}>{t('label.needsCase')}</Tag>}
                  </div>
                  <div style={{ color: 'var(--app-fg-subtle)', fontSize: 12 }}>{m.desc}</div>
                </div>
              </Space>
            </Card>
          ))}
        </Space>
      </Drawer>

      <WidgetConfigDrawer
        open={!!cfgWidget}
        widget={cfgWidget}
        snapshot={snapshot}
        onClose={() => setCfgWidget(null)}
        onChange={(w) => { updateWidget(w); setCfgWidget(w) }}
      />
    </div>
  )
}
