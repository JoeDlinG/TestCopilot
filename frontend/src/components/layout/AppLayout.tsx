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
import OutputDock from './OutputDock'

const { Header, Sider, Content } = Layout

/**
 * Left navigation: 3 groups / 8 items (issue #20).
 *
 * The previous 15-item flat list mixed configuration with delivery, so authors
 * kept bouncing between "write" and "watch". Execution and reports now live in
 * the right-hand dock; the three plugin pages collapse into one entry.
 */
const NAV_GROUPS: {
  key: string
  labelKey: string
  items: { key: string; icon: React.ReactNode; labelKey: string }[]
}[] = [
  {
    key: 'g-config',
    labelKey: 'nav.group.config',
    items: [
      { key: '/devices', icon: <ApiOutlined />, labelKey: 'nav.devices' },
    ],
  },
  {
    key: 'g-design',
    labelKey: 'nav.group.design',
    items: [
      { key: '/testcases', icon: <DiffOutlined />, labelKey: 'nav.testcases' },
      { key: '/ai', icon: <RobotOutlined />, labelKey: 'nav.ai' },
      { key: '/execution-plans', icon: <OrderedListOutlined />, labelKey: 'nav.plans' },
      { key: '/debug-terminal', icon: <CodeOutlined />, labelKey: 'nav.debugTerminal' },
    ],
  },
  {
    key: 'g-system',
    labelKey: 'nav.group.system',
    items: [
      { key: '/plugins', icon: <AppstoreAddOutlined />, labelKey: 'nav.pluginCenter' },
      { key: '/model-config', icon: <SettingOutlined />, labelKey: 'nav.modelConfig' },
      { key: '/projects', icon: <FolderOpenOutlined />, labelKey: 'nav.projects' },
    ],
  },
]

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()
  const [restarting, setRestarting] = useState(false)
  const { t, locale, setLocale } = useI18n()
  const { mode, toggle: toggleTheme } = useTheme()
  const dockState = useOutputDock((s) => s.state)
  const dockPinned = useOutputDock((s) => s.pinned)
  const collapseDock = useOutputDock((s) => s.collapse)
  const runningCount = useOutputDock((s) => s.runningCount)

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
        collapsed={collapsed}
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
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
            <Dropdown
              menu={{
                items: [
                  { key: '/', icon: <DashboardOutlined />, label: t('nav.dashboard') },
                  { key: '/dashboards', icon: <AppstoreAddOutlined />, label: t('nav.customDashboard') },
                ],
                onClick: ({ key }) => navigate(key),
              }}
            >
              <Button type="text">
                <Space size={4}>
                  {t('top.dashboards')}
                  <DownOutlined style={{ fontSize: 10 }} />
                </Space>
              </Button>
            </Dropdown>
            <Dropdown
              menu={{
                items: [
                  { key: '/logs', icon: <FileTextOutlined />, label: t('nav.logs') },
                ],
                onClick: ({ key }) => navigate(key),
              }}
            >
              <Button type="text">
                <Space size={4}>
                  {t('top.tools')}
                  <DownOutlined style={{ fontSize: 10 }} />
                </Space>
              </Button>
            </Dropdown>
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
          {!dockIsRoute && <OutputDock />}
        </Content>
      </Layout>
    </Layout>
  )
}
