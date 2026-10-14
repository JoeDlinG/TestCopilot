import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, theme, message, Select, Tooltip } from 'antd'
import {
  DashboardOutlined,
  ApiOutlined,
  RobotOutlined,
  ExperimentOutlined,
  PlayCircleOutlined,
  FileTextOutlined,
  BarChartOutlined,
  AppstoreAddOutlined,
  CodeOutlined,
  MenuFoldOutlined,
  SettingOutlined,
  MenuUnfoldOutlined,
  ReloadOutlined,
  OrderedListOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons'
import { systemAPI } from '../../services/api'
import { useI18n, LOCALES } from '../../i18n'

const { Header, Sider, Content } = Layout

/** Menu definition — labels are i18n keys resolved at render time. */
const MENU_DEFINITION: { key: string; icon: React.ReactNode; labelKey: string }[] = [
  { key: '/', icon: <DashboardOutlined />, labelKey: 'nav.dashboard' },
  { key: '/dashboards', icon: <AppstoreAddOutlined />, labelKey: 'nav.customDashboard' },
  { key: '/devices', icon: <ApiOutlined />, labelKey: 'nav.devices' },
  { key: '/debug-terminal', icon: <CodeOutlined />, labelKey: 'nav.debugTerminal' },
  { key: '/ai', icon: <RobotOutlined />, labelKey: 'nav.ai' },
  { key: '/testcases', icon: <ExperimentOutlined />, labelKey: 'nav.testcases' },
  { key: '/executions', icon: <PlayCircleOutlined />, labelKey: 'nav.executions' },
  { key: '/execution-plans', icon: <OrderedListOutlined />, labelKey: 'nav.plans' },
  { key: '/logs', icon: <FileTextOutlined />, labelKey: 'nav.logs' },
  { key: '/reports', icon: <BarChartOutlined />, labelKey: 'nav.reports' },
  { key: '/plugins', icon: <AppstoreAddOutlined />, labelKey: 'nav.plugins' },
  { key: '/plugin-editor', icon: <CodeOutlined />, labelKey: 'nav.pluginEditor' },
  { key: '/skill-editor', icon: <FileTextOutlined />, labelKey: 'nav.skillEditor' },
  { key: '/model-config', icon: <SettingOutlined />, labelKey: 'nav.modelConfig' },
  { key: '/projects', icon: <FolderOpenOutlined />, labelKey: 'nav.projects' },
]

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()
  const [restarting, setRestarting] = useState(false)
  const { t, locale, setLocale } = useI18n()

  const menuItems = MENU_DEFINITION.map((item) => ({
    key: item.key,
    icon: item.icon,
    label: t(item.labelKey),
  }))

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await systemAPI.restart()
      // Wait for the backend to restart, then refresh the UI.
      message.loading({ content: t('app.restarting'), key: 'restart', duration: 3 })
      setTimeout(() => window.location.reload(), 3000)
    } catch (err) {
      setRestarting(false)
      message.error(t('app.restartFailed'))
    }
  }

  const selectedKey = '/' + location.pathname.split('/')[1]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        theme="light"
        style={{
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          boxShadow: '2px 0 8px rgba(0,0,0,0.05)',
        }}
      >
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <span className="logo-text">
            {collapsed ? 'ATL' : 'AITestLab'}
          </span>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: '0 24px',
            background: token.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            height: 64,
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Tooltip title={t('common.language')}>
              <Select
                value={locale}
                onChange={(v) => setLocale(v)}
                size="small"
                style={{ width: 110 }}
                options={LOCALES.map((l) => ({ value: l.value, label: l.label }))}
              />
            </Tooltip>
            <Button
              icon={<ReloadOutlined />}
              loading={restarting}
              onClick={handleRestart}
            >
              {t('app.restart')}
            </Button>
            <span style={{ color: token.colorTextSecondary, fontSize: 13 }}>
              AI 测试应用平台 v1.0
            </span>
          </div>
        </Header>
        <Content
          style={{
            margin: 0,
            background: token.colorBgLayout,
            minHeight: 280,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
