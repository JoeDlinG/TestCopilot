import { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, theme } from 'antd'
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
  MenuUnfoldOutlined,
} from '@ant-design/icons'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/devices', icon: <ApiOutlined />, label: '设备管理' },
  { key: '/debug-terminal', icon: <CodeOutlined />, label: '调试终端' },
  { key: '/ai', icon: <RobotOutlined />, label: 'AI 助手' },
  { key: '/testcases', icon: <ExperimentOutlined />, label: '测试用例' },
  { key: '/executions', icon: <PlayCircleOutlined />, label: '测试执行' },
  { key: '/logs', icon: <FileTextOutlined />, label: '通信日志' },
  { key: '/reports', icon: <BarChartOutlined />, label: '测试报告' },
  { key: '/plugins', icon: <AppstoreAddOutlined />, label: '插件管理' },
]

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token } = theme.useToken()

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
