import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, theme, message } from 'antd'
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
} from '@ant-design/icons'
import { systemAPI } from '../../services/api'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/dashboards', icon: <AppstoreAddOutlined />, label: '自定义仪表盘' },
  { key: '/devices', icon: <ApiOutlined />, label: '设备管理' },
  { key: '/debug-terminal', icon: <CodeOutlined />, label: '调试终端' },
  { key: '/ai', icon: <RobotOutlined />, label: 'AI 助手' },
  { key: '/testcases', icon: <ExperimentOutlined />, label: '测试用例' },
  { key: '/executions', icon: <PlayCircleOutlined />, label: '测试执行' },
  { key: '/logs', icon: <FileTextOutlined />, label: '通信日志' },
  { key: '/reports', icon: <BarChartOutlined />, label: '测试报告' },
  { key: '/plugins', icon: <AppstoreAddOutlined />, label: '插件管理' },
  { key: '/plugin-editor', icon: <CodeOutlined />, label: '插件编辑器' },
  { key: '/skill-editor', icon: <FileTextOutlined />, label: 'Skill 编辑器' },
  { key: '/model-config', icon: <SettingOutlined />, label: '模型配置' },
]

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()
  const [restarting, setRestarting] = useState(false)

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await systemAPI.restart()
      // Wait for the backend to restart, then refresh the UI.
      message.loading({ content: '正在重启软件，刷新界面…', key: 'restart', duration: 3 })
      setTimeout(() => window.location.reload(), 3000)
    } catch (err) {
      setRestarting(false)
      message.error('重启失败，请手动重启服务')
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
            <Button
              icon={<ReloadOutlined />}
              loading={restarting}
              onClick={handleRestart}
            >
              重置软件
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
