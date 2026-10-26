/**
 * 帮助菜单（Issue: 增加帮助菜单，在帮助菜单加入帮助文件）
 *
 * Three surfaces behind one dropdown:
 *   • 帮助中心 —— markdown manuals served by ``/api/help/docs``. They are NOT
 *     bundled into the JS: the backend reads ``docs/*.md`` at runtime, so the
 *     repo copy stays the single source of truth.
 *   • 快捷键 —— a static table; cheaper and more accurate than scraping hints.
 *   • 关于 —— version of the running backend + frontend build.
 *
 * The tour / updater / feedback entries are injected by ``AppLayout`` so this
 * component stays free of those concerns.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  Button, Drawer, Dropdown, Empty, Modal, Space, Spin, Table, Tag, Typography, message,
} from 'antd'
import {
  BookOutlined, BugOutlined, DownOutlined, InfoCircleOutlined, KeyOutlined,
  QuestionCircleOutlined, ReadOutlined, RocketOutlined, SyncOutlined,
} from '@ant-design/icons'
import api, { helpAPI } from '../../services/api'
import MarkdownDoc from './MarkdownDoc'
import { useI18n } from '../../i18n'

const { Text, Title, Paragraph } = Typography

interface HelpDoc {
  id: string
  title: string
  description: string
  available: boolean
  updated_at?: string | null
  size: number
}

export interface HelpMenuProps {
  /** Replay the onboarding tour (issue: 首次运行引导). */
  onStartTour?: () => void
  /** Open the update dialog (issue #25). */
  onOpenUpdate?: () => void
  /** Open the feedback form (issue #26). */
  onOpenFeedback?: () => void
}

const SHORTCUTS: { group: 'global' | 'editor'; keys: string; labelKey: string }[] = [
  { group: 'global', keys: '⌘K / Ctrl+K', labelKey: 'help.sc.palette' },
  { group: 'global', keys: 'Esc', labelKey: 'help.sc.esc' },
  { group: 'global', keys: 'Alt+→ / Alt+←', labelKey: 'help.sc.dock' },
  { group: 'editor', keys: 'Ctrl+Z', labelKey: 'help.sc.undo' },
  { group: 'editor', keys: 'Ctrl+Y', labelKey: 'help.sc.redo' },
  { group: 'editor', keys: 'Ctrl+C', labelKey: 'help.sc.copy' },
  { group: 'editor', keys: 'Ctrl+V', labelKey: 'help.sc.paste' },
  { group: 'editor', keys: 'Delete', labelKey: 'help.sc.delete' },
  { group: 'editor', keys: 'F11', labelKey: 'help.sc.fullscreen' },
  { group: 'editor', keys: 'Ctrl+S', labelKey: 'help.sc.save' },
]

export default function HelpMenu({ onStartTour, onOpenUpdate, onOpenFeedback }: HelpMenuProps) {
  const { t } = useI18n()

  const [centerOpen, setCenterOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [aboutOpen, setAboutOpen] = useState(false)

  const [docs, setDocs] = useState<HelpDoc[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [activeDoc, setActiveDoc] = useState<string>('')
  const [markdown, setMarkdown] = useState('')
  const [docLoading, setDocLoading] = useState(false)

  const loadDocs = useCallback(async () => {
    setDocsLoading(true)
    try {
      const res = await helpAPI.listDocs()
      const items: HelpDoc[] = res.data?.data?.items || []
      setDocs(items)
      const first = items.find((d) => d.available) || items[0]
      if (first && !activeDoc) setActiveDoc(first.id)
    } catch {
      message.error(t('help.loadFailed'))
    } finally {
      setDocsLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (centerOpen && docs.length === 0) loadDocs()
  }, [centerOpen, docs.length, loadDocs])

  useEffect(() => {
    if (!centerOpen || !activeDoc) return
    let cancelled = false
    setDocLoading(true)
    helpAPI
      .getDoc(activeDoc)
      .then((res) => { if (!cancelled) setMarkdown(res.data?.data?.markdown || '') })
      .catch(() => { if (!cancelled) { setMarkdown(''); message.error(t('help.loadFailed')) } })
      .finally(() => { if (!cancelled) setDocLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [centerOpen, activeDoc])

  const openCenter = (docId?: string) => {
    if (docId) setActiveDoc(docId)
    setCenterOpen(true)
  }

  return (
    <>
      <Dropdown
        trigger={['click']}
        menu={{
          items: [
            ...(onStartTour
              ? [{ key: 'tour', icon: <RocketOutlined />, label: t('help.tourAgain') }]
              : []),
            { key: 'docs', icon: <BookOutlined />, label: t('help.docs') },
            { key: 'shortcuts', icon: <KeyOutlined />, label: t('help.shortcuts') },
            { type: 'divider' as const },
            ...(onOpenUpdate
              ? [{ key: 'update', icon: <SyncOutlined />, label: t('help.checkUpdate') }]
              : []),
            ...(onOpenFeedback
              ? [{ key: 'feedback', icon: <BugOutlined />, label: t('help.feedback') }]
              : []),
            { type: 'divider' as const },
            { key: 'about', icon: <InfoCircleOutlined />, label: t('help.aboutApp') },
          ],
          onClick: ({ key }) => {
            if (key === 'tour') onStartTour?.()
            else if (key === 'docs') openCenter()
            else if (key === 'shortcuts') setShortcutsOpen(true)
            else if (key === 'update') onOpenUpdate?.()
            else if (key === 'feedback') onOpenFeedback?.()
            else if (key === 'about') setAboutOpen(true)
          },
        }}
      >
        <Button type="text" icon={<QuestionCircleOutlined />}>
          <Space size={4}>
            {t('help.menu')}
            <DownOutlined style={{ fontSize: 10 }} />
          </Space>
        </Button>
      </Dropdown>

      {/* ---------------- 帮助中心 ---------------- */}
      <Drawer
        title={t('help.center')}
        open={centerOpen}
        onClose={() => setCenterOpen(false)}
        width={900}
        destroyOnClose={false}
        styles={{ body: { padding: 0, display: 'flex', minHeight: 0 } }}
      >
        <div
          style={{
            width: 230, flex: '0 0 230px', borderRight: '1px solid var(--app-border)',
            overflow: 'auto', padding: 8,
          }}
        >
          {docsLoading ? (
            <Spin style={{ display: 'block', margin: '24px auto' }} />
          ) : docs.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('help.offline')} />
          ) : (
            docs.map((d) => {
              const active = d.id === activeDoc
              return (
                <div
                  key={d.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => d.available && setActiveDoc(d.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') d.available && setActiveDoc(d.id) }}
                  style={{
                    padding: '8px 10px', borderRadius: 6, cursor: d.available ? 'pointer' : 'not-allowed',
                    background: active ? 'var(--app-surface-muted)' : undefined,
                    opacity: d.available ? 1 : 0.45, marginBottom: 2,
                  }}
                >
                  <Space size={6}>
                    <ReadOutlined />
                    <Text strong={active}>{d.title}</Text>
                  </Space>
                  <div style={{ fontSize: 11, opacity: 0.65, marginTop: 2, lineHeight: 1.4 }}>
                    {d.description}
                  </div>
                </div>
              )
            })
          )}
        </div>

        <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: '8px 24px 32px' }}>
          {docLoading ? (
            <Spin style={{ display: 'block', margin: '48px auto' }} />
          ) : markdown ? (
            <MarkdownDoc text={markdown} />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('help.pickDoc')}
              style={{ marginTop: 60 }}
            />
          )}
        </div>
      </Drawer>

      {/* ---------------- 快捷键 ---------------- */}
      <Modal
        title={t('help.shortcuts')}
        open={shortcutsOpen}
        onCancel={() => setShortcutsOpen(false)}
        footer={null}
        width={620}
      >
        {(['global', 'editor'] as const).map((group) => (
          <div key={group} style={{ marginBottom: 18 }}>
            <Title level={5} style={{ marginBottom: 8 }}>
              {group === 'global' ? t('help.sc.global') : t('help.sc.editor')}
            </Title>
            <Table
              size="small"
              pagination={false}
              rowKey="keys"
              showHeader={false}
              dataSource={SHORTCUTS.filter((s) => s.group === group)}
              columns={[
                { dataIndex: 'keys', width: 190, render: (v: string) => <Tag>{v}</Tag> },
                { dataIndex: 'labelKey', render: (v: string) => t(v) },
              ]}
            />
          </div>
        ))}
      </Modal>

      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} />
    </>
  )
}

/** About panel: version comes from the live backend, not a hard-coded string. */
function AboutModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useI18n()
  const [backend, setBackend] = useState<{ version?: string; name?: string }>({})

  useEffect(() => {
    if (!open) return
    api.get('/health')
      .then((r) => setBackend({ version: r.data?.version }))
      .catch(() => setBackend({}))
  }, [open])

  return (
    <Modal title={t('help.aboutApp')} open={open} onCancel={onClose} footer={null} width={560}>
      <div style={{ textAlign: 'center', padding: '8px 0 16px' }}>
        <img src="/logo-full.png" alt="TestCopilot" style={{ height: 44, maxWidth: '80%' }} />
        <Paragraph type="secondary" style={{ marginTop: 10, marginBottom: 0 }}>
          {t('help.aboutBody')}
        </Paragraph>
      </div>
      <Table
        size="small"
        pagination={false}
        showHeader={false}
        rowKey="k"
        // The base product is free to use but NOT open source, so no source
        // repository is advertised here (and never in the shipped UI).
        dataSource={[
          { k: 'v', label: t('help.version'), value: backend.version || '—' },
          { k: 'b', label: t('help.frontendBuild'), value: 'Vite / React 18' },
          { k: 'p', label: t('help.platform'), value: navigator.platform || '—' },
        ]}
        columns={[
          { dataIndex: 'label', width: 150, render: (v: string) => <Text type="secondary">{v}</Text> },
          { dataIndex: 'value', render: (v: string) => <Text>{v}</Text> },
        ]}
      />
    </Modal>
  )
}
