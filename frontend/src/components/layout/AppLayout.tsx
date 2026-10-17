import { useEffect, useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Layout, Menu, Button, theme, message, Select, Tooltip, Dropdown, Space, Badge,
} from 'antd'
import {
  DashboardOutlined,
  ApiOutlined,
  RobotOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  AppstoreAddOutlined,
  CodeOutlined,
  MenuFoldOutlined,
  SettingOutlined,
  MenuUnfoldOutlined,
  ReloadOutlined,
  OrderedListOutlined,
  FolderOpenOutlined,
  DownOutlined,
  SearchOutlined,
  FullscreenExitOutlined,
  BulbOutlined,
  BulbFilled,
  // Issue #20: a beaker reads as "chemistry lab"; test cases are about
  // expected vs actual, so the navigation icon is DiffOutlined.
  DiffOutlined,
} from '@ant-design/icons'
import { systemAPI, deviceAPI } from '../../services/api'
import { extractItems } from '../../services/apiHelper'
import { useI18n, LOCALES } from '../../i18n'
import { useTheme } from '../../theme'
import { useOutputDock } from '../../stores/outputDockStore'
import { componentTokens } from '../../theme/tokens'
import { NAV_GROUPS, TOP_MENUS } from '../../config/navigation'
import OutputDock from './OutputDock'
import CommandPalette from './CommandPalette'

const { Header, Sider, Content } = Layout

/**
 * Left navigation: 3 groups / 8 items (issue #20).
 *
 * The previous 15-item flat list mixed configuration with delivery, so authors
 * kept bouncing between "write" and "watch". Execution and reports now live in
 * the right-hand dock; the three plugin pages collapse into one entry.
 *
 * The definition itself lives in ``src/config/navigation.ts`` so the sidebar,
 * the top-bar dropdowns and the ⌘K palette stay in sync.
 */

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()
  const [restarting, setRestarting] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { t, locale, setLocale } = useI18n()
  const { mode, toggle: toggleTheme } = useTheme()
  const dockState = useOutputDock((s) => s.state)
  const dockPinned = useOutputDock((s) => s.pinned)
  const collapseDock = useOutputDock((s) => s.collapse)
  const runningCount = useOutputDock((s) => s.runningCount)

  // ⌘K / Ctrl+K — the sidebar only has 8 entries, so a searchable palette is
  // the fast path to deep pages (issue #21).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && String(e.key).toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Global status bar data (cheap: one small request, refreshed slowly).
  const [connectedDevices, setConnectedDevices] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const res = await deviceAPI.list()
        const items = extractItems(res)
        if (!cancelled) setConnectedDevices(items.filter((d: any) => d.status === 'connected').length)
      } catch { /* status bar is best effort */ }
    }
    load()
    const id = setInterval(load, 15000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await systemAPI.restart()
      message.loading({ content: t('app.restarting'), key: 'restart', duration: 3 })
      setTimeout(() => window.location.reload(), 3000)
    } catch {
      setRestarting(false)
      message.error(t('app.restartFailed'))
    }
  }

  // Unpinned dock auto-collapses when the user moves to another page —
  // otherwise the run panel would follow them everywhere.
  useEffect(() => {
    if (!dockPinned && dockState !== 'collapsed') collapseDock()
  }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  // The dock embeds the very same pages as /executions and /reports. Rendering
  // both at once would open duplicate WebSocket connections, so the dock steps
  // aside while one of those pages is the actual route.
  const dockIsRoute =
    location.pathname.startsWith('/executions') || location.pathname.startsWith('/reports')

  // Immersive mode (issue #21): the flow editor needs every pixel, so the
  // sidebar folds and the dock steps aside while editing. The header keeps an
  // explicit exit so the user is never trapped without chrome.
  const isFlowRoute = location.pathname.includes('/flow')
  const [immersiveOff, setImmersiveOff] = useState(false)
  const immersive = isFlowRoute && !immersiveOff

  useEffect(() => {
    if (!isFlowRoute) setImmersiveOff(false)
  }, [isFlowRoute])

  const siderCollapsed = collapsed || immersive
  const selectedKey = '/' + location.pathname.split('/')[1]

  const menuItems = NAV_GROUPS.map((group) => ({
    key: group.key,
    type: 'group' as const,
    label: t(group.labelKey),
    children: group.items.map((item) => ({
      key: item.key,
      icon: item.icon,
      label: t(item.labelKey),
    })),
  }))

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={siderCollapsed}
        theme="light"
        width={componentTokens.siderWidth}
        collapsedWidth={componentTokens.siderCollapsedWidth}
        style={{
          borderRight: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <div
          style={{
            height: componentTokens.headerHeight,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <span className="logo-text">{collapsed ? 'ATL' : 'AITestLab'}</span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8 }}
          // Collapsed: icons only, no wrapping (acceptance criterion).
          inlineCollapsed={collapsed}
        />
      </Sider>

      <Layout style={{ minWidth: 0 }}>
        <Header
          style={{
            padding: '0 16px',
            background: token.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            height: componentTokens.headerHeight,
            lineHeight: `${componentTokens.headerHeight}px`,
          }}
        >
          <Space size={4}>
            <Button
              type="text"
              disabled={immersive}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
            {immersive && (
              <Tooltip title="退出沉浸模式">
                <Button
                  size="small"
                  icon={<FullscreenExitOutlined />}
                  onClick={() => setImmersiveOff(true)}
                >
                  退出沉浸
                </Button>
              </Tooltip>
            )}
            {TOP_MENUS.map((menu) => (
              <Dropdown
                key={menu.key}
                menu={{
                  items: menu.items.map((item) => ({
                    key: item.key,
                    icon: item.icon,
                    label: t(item.labelKey),
                  })),
                  onClick: ({ key }) => navigate(key),
                }}
              >
                <Button type="text">
                  <Space size={4}>
                    {t(menu.labelKey)}
                    <DownOutlined style={{ fontSize: 10 }} />
                  </Space>
                </Button>
              </Dropdown>
            ))}
            <Tooltip title="全局搜索 / 跳转（⌘K / Ctrl+K）">
              <Button
                type="text"
                icon={<SearchOutlined />}
                onClick={() => setPaletteOpen(true)}
              />
            </Tooltip>
          </Space>

          <Space size={8}>
            <Tooltip title={t('common.language')}>
              <Select
                value={locale}
                onChange={(v) => setLocale(v)}
                size="small"
                style={{ width: 100 }}
                options={LOCALES.map((l) => ({ value: l.value, label: l.label }))}
              />
            </Tooltip>
            <Tooltip title={mode === 'dark' ? '切换为亮色主题' : '切换为深色主题'}>
              <Button
                type="text"
                icon={mode === 'dark' ? <BulbFilled /> : <BulbOutlined />}
                onClick={toggleTheme}
              />
            </Tooltip>
            <Button icon={<ReloadOutlined />} loading={restarting} onClick={handleRestart} size="small">
              {t('app.restart')}
            </Button>
          </Space>
        </Header>

        {/* Global status bar — persistent on every page */}
        <div
          style={{
            height: componentTokens.statusBarHeight,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            padding: '0 16px',
            fontSize: 12,
            color: token.colorTextSecondary,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            background: token.colorBgContainer,
          }}
        >
          <span>
            <Badge status="success" text={t('status.backend')} />
          </span>
          <span>
            <ApiOutlined /> {t('status.devices')}: {connectedDevices}
          </span>
          <span>
            <PlayCircleOutlined /> {t('status.running')}: {runningCount}
          </span>
          <span style={{ marginLeft: 'auto', opacity: 0.6 }}>AITestLab</span>
        </div>

        <Content style={{ display: 'flex', minHeight: 0, minWidth: 0, background: token.colorBgLayout }}>
          {/* NOTE: no `page-container` class here — pages apply it themselves,
              and doubling it would double the padding and nest the max-width. */}
          <div style={{ flex: 1, minWidth: 0, overflow: 'auto', padding: 20 }}>
            <Outlet />
          </div>
          {!dockIsRoute && !immersive && <OutputDock />}
          <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
        </Content>
      </Layout>
    </Layout>
  )
}
