import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Empty, Input, Modal, Tag } from 'antd'
import { theme } from 'antd'
import { ALL_NAV_ITEMS } from '../../config/navigation'
import { useI18n } from '../../i18n'
import { useOutputDock } from '../../stores/outputDockStore'
import { deviceAPI, testCaseAPI } from '../../services/api'
import { extractItems } from '../../services/apiHelper'

interface Entry {
  key: string
  title: string
  subtitle: string
  group: string
  icon: React.ReactNode
  run: () => void
}

/**
 * ⌘K / Ctrl+K command palette (issue #21).
 *
 * The sidebar was narrowed to 8 items in #20, which makes deep pages (reports,
 * logs, a specific test case) slower to reach by mouse. A searchable palette
 * restores fast access without adding menu noise.
 */
export default function CommandPalette({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const { t } = useI18n()
  const { token } = theme.useToken()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [devices, setDevices] = useState<any[]>([])
  const [cases, setCases] = useState<any[]>([])
  const loadedRef = useRef(false)
  const expand = useOutputDock((s) => s.expand)
  const setTab = useOutputDock((s) => s.setTab)

  // Loaded lazily — the palette is the only consumer and users may never open it.
  useEffect(() => {
    if (!open || loadedRef.current) return
    loadedRef.current = true
    ;(async () => {
      try {
        setDevices(extractItems(await deviceAPI.list()))
      } catch { /* optional */ }
      try {
        setCases(extractItems(await testCaseAPI.list()))
      } catch { /* optional */ }
    })()
  }, [open])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
    }
  }, [open])

  const navEntries: Entry[] = useMemo(
    () =>
      ALL_NAV_ITEMS.map((item) => ({
        key: item.key,
        title: t(item.labelKey),
        subtitle: item.key.startsWith('dock:') ? t('dock.title') : item.key,
        group: item.key.startsWith('dock:') ? t('dock.title') : t('top.dashboards'),
        icon: item.icon,
        run: () => {
          if (item.key.startsWith('dock:')) {
            setTab(item.key.slice(5) as 'executions' | 'reports')
            expand(item.key.slice(5) as 'executions' | 'reports')
          } else {
            navigate(item.key)
          }
        },
      })),
    [t, navigate, expand, setTab],
  )

  const dynamicEntries: Entry[] = useMemo(() => {
    const out: Entry[] = []
    for (const d of devices) {
      out.push({
        key: `dev:${d.id}`,
        title: d.name,
        subtitle: `${d.device_key ?? ''} · ${d.protocol}`,
        group: t('nav.devices'),
        icon: <Tag color="geekblue">{d.device_key ?? '-'}</Tag>,
        run: () => navigate('/devices'),
      })
    }
    for (const c of cases) {
      out.push({
        key: `tc:${c.id}`,
        title: c.name,
        subtitle: c.description || c.id,
        group: t('nav.testcases'),
        icon: <Tag>{t('nav.testcases')}</Tag>,
        run: () => navigate(`/testcases/${c.id}/flow`),
      })
    }
    return out
  }, [devices, cases, t, navigate])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = [...navEntries, ...dynamicEntries]
    if (!q) return navEntries.slice(0, 12)
    return all
      .filter((e) => `${e.title} ${e.subtitle} ${e.group}`.toLowerCase().includes(q))
      .slice(0, 30)
  }, [query, navEntries, dynamicEntries])

  useEffect(() => {
    setActive((i) => Math.min(i, Math.max(0, results.length - 1)))
  }, [results.length])

  const commit = useCallback(
    (index: number) => {
      const entry = results[index]
      if (!entry) return
      entry.run()
      onClose()
    },
    [results, onClose],
  )

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % Math.max(1, results.length))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i - 1 + results.length) % Math.max(1, results.length))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      commit(active)
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={620}
      styles={{ body: { padding: 0 } }}
      destroyOnHidden
      title={null}
      closable={false}
      centered={false}
      style={{ top: 88 }}
    >
      <Input
        autoFocus
        size="large"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="搜索页面、设备、测试用例…（↑↓ 选择，Enter 打开，Esc 关闭）"
        style={{ border: 'none', boxShadow: 'none', padding: '10px 16px' }}
      />
      <div style={{ maxHeight: 380, overflow: 'auto', padding: '4px 0 8px' }}>
        {results.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={query ? `没有匹配「${query}」的结果` : ''}
            style={{ padding: '24px 0' }}
          />
        ) : (
          results.map((entry, i) => (
            <div
              key={entry.key}
              onMouseEnter={() => setActive(i)}
              onClick={() => commit(i)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '8px 16px',
                cursor: 'pointer',
                background: i === active ? token.controlItemBgActive : 'transparent',
              }}
            >
              <span style={{ width: 20, display: 'flex', justifyContent: 'center' }}>
                {entry.icon}
              </span>
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {entry.title}
              </span>
              <span style={{ fontSize: 11, color: token.colorTextTertiary, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {entry.subtitle}
              </span>
            </div>
          ))
        )}
      </div>
    </Modal>
  )
}
