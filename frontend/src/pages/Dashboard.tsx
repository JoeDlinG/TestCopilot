import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Card, Statistic, Button, Space, Typography, List, Tag, Spin } from 'antd'
import {
  ApiOutlined, ExperimentOutlined, PlayCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  PlusOutlined, RobotOutlined,
} from '@ant-design/icons'
import { deviceAPI, testCaseAPI, executionAPI, aiAPI } from '../services/api'
import { extractItems, extractData } from '../services/apiHelper'

const { Title } = Typography

export default function Dashboard() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    devices: 0,
    connectedDevices: 0,
    testCases: 0,
    executions: 0,
    passedExecutions: 0,
    aiModels: 0,
  })
  const [recentExecutions, setRecentExecutions] = useState<any[]>([])

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    try {
      setLoading(true)
      const [devicesRes, casesRes, execsRes, modelsRes] = await Promise.all([
        deviceAPI.list().catch(() => ({ data: { code: 0, data: { items: [] } } })),
        testCaseAPI.list().catch(() => ({ data: { code: 0, data: { items: [] } } })),
        executionAPI.list().catch(() => ({ data: { code: 0, data: { items: [] } } })),
        aiAPI.listModels().catch(() => ({ data: { code: 0, data: [] } })),
      ])

      const devices = extractItems(devicesRes)
      const cases = extractItems(casesRes)
      const execs = extractItems(execsRes)
      const models = extractData(modelsRes, [])

      setStats({
        devices: devices.length,
        connectedDevices: devices.filter((d: any) => d.status === 'connected').length,
        testCases: cases.length,
        executions: execs.length,
        passedExecutions: execs.filter((e: any) => e.status === 'passed').length,
        aiModels: models.length,
      })

      setRecentExecutions(execs.slice(0, 5))
    } catch (err) {
      console.error('Failed to load dashboard:', err)
    } finally {
      setLoading(false)
    }
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case 'passed': return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'failed': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      case 'running': return <SyncOutlined spin style={{ color: '#1890ff' }} />
      case 'error': return <CloseCircleOutlined style={{ color: '#faad14' }} />
      default: return <CheckCircleOutlined style={{ color: '#d9d9d9' }} />
    }
  }

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 100 }}><Spin size="large" /></div>
  }

  return (
    <div className="page-container">
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>仪表盘</Title>
        <p style={{ color: '#888', marginTop: 4 }}>AITestLab - AI 驱动的硬件测试平台</p>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={8}>
          <Card hoverable onClick={() => navigate('/devices')}>
            <Statistic
              title="设备总数"
              value={stats.devices}
              prefix={<ApiOutlined />}
              suffix={
                <span style={{ fontSize: 14, color: '#52c41a' }}>
                  {stats.connectedDevices} 已连接
                </span>
              }
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card hoverable onClick={() => navigate('/testcases')}>
            <Statistic
              title="测试用例"
              value={stats.testCases}
              prefix={<ExperimentOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card hoverable onClick={() => navigate('/executions')}>
            <Statistic
              title="测试执行"
              value={stats.executions}
              prefix={<PlayCircleOutlined />}
              suffix={
                <span style={{ fontSize: 14, color: '#52c41a' }}>
                  {stats.passedExecutions} 通过
                </span>
              }
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} lg={16}>
          <Card
            title="最近执行"
            extra={<Button type="link" onClick={() => navigate('/executions')}>查看全部</Button>}
          >
            <List
              dataSource={recentExecutions}
              locale={{ emptyText: '暂无执行记录' }}
              renderItem={(item: any) => (
                <List.Item>
                  <List.Item.Meta
                    avatar={statusIcon(item.status)}
                    title={item.id?.slice(0, 8) + '...'}
                    description={`状态: ${item.status} | 时长: ${item.duration_ms || '-'}ms`}
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Card title="快捷操作">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                block
                onClick={() => navigate('/devices')}
              >
                添加设备
              </Button>
              <Button
                icon={<RobotOutlined />}
                block
                onClick={() => navigate('/ai')}
              >
                AI 生成测试用例
              </Button>
              <Button
                icon={<ExperimentOutlined />}
                block
                onClick={() => navigate('/testcases')}
              >
                管理测试用例
              </Button>
              <Button
                icon={<PlayCircleOutlined />}
                block
                onClick={() => navigate('/executions')}
              >
                查看测试执行
              </Button>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
