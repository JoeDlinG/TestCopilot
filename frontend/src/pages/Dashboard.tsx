import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Row, Col, Card, Statistic, Button, Space, Typography, List, Tag, Spin,
  Tooltip, Select, Progress,
} from 'antd'
import {
  ApiOutlined, ExperimentOutlined, PlayCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  PlusOutlined, RobotOutlined, FullscreenOutlined, FullscreenExitOutlined,
  ReloadOutlined,
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

  // ---- 大屏模式（无权限控制，直接投屏；自动刷新 + 实时时钟）----
  const [bigScreen, setBigScreen] = useState(false)
  const [refreshSec, setRefreshSec] = useState(10)
  const [now, setNow] = useState(() => new Date())
  // latest loader, so the auto-refresh interval never has to be rebuilt
  const loadRef = useRef<() => void>(() => {})

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

  useEffect(() => { loadRef.current = loadDashboard })

  // big-screen helpers: fullscreen is opportunistic (may be blocked), the
  // overlay itself works with or without it
  const enterBigScreen = async () => {
    setBigScreen(true)
    try {
      await document.documentElement.requestFullscreen()
    } catch {
      /* browser refused - the overlay still renders full-viewport */
    }
  }

  const exitBigScreen = async () => {
    setBigScreen(false)
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
    } catch {
      /* ignore */
    }
  }

  // clock + auto refresh while in big-screen mode
  useEffect(() => {
    if (!bigScreen) return
    setNow(new Date())
    const clock = window.setInterval(() => setNow(new Date()), 1000)
    const timer = window.setInterval(() => loadRef.current(), refreshSec * 1000)
    return () => {
      window.clearInterval(clock)
      window.clearInterval(timer)
    }
  }, [bigScreen, refreshSec])

  // leaving fullscreen with ESC / F11 should also leave big-screen mode
  useEffect(() => {
    const onChange = () => {
      if (!document.fullscreenElement) setBigScreen(false)
    }
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

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

  // ============ 大屏模式 ============
  // No permission / role gating: anyone can throw this on a wall display.
  if (bigScreen) {
    const passRate = stats.executions
      ? Math.round((stats.passedExecutions / stats.executions) * 100)
      : 0
    const bg = '#0b1a2b'
    const cardBg = 'rgba(255,255,255,0.06)'
    const bigCard = (
      title: string,
      value: ReactNode,
      extra: ReactNode,
      icon: ReactNode,
      color: string,
    ) => (
      <div
        style={{
          background: cardBg,
          border: '1px solid rgba(255,255,255,0.10)',
          borderRadius: 14,
          padding: '22px 26px',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, opacity: 0.8, fontSize: 17 }}>
          <span style={{ color, fontSize: 22 }}>{icon}</span>
          {title}
        </div>
        <div style={{ fontSize: 54, fontWeight: 700, lineHeight: 1.15, fontVariantNumeric: 'tabular-nums' }}>
          {value}
        </div>
        <div style={{ fontSize: 15, opacity: 0.65 }}>{extra}</div>
      </div>
    )

    return (
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 1200,
          background: bg, color: '#fff',
          padding: 28, display: 'flex', flexDirection: 'column',
          overflow: 'auto',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 22, flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontSize: 30, fontWeight: 700, letterSpacing: 1 }}>
              AITestLab 测试监控大屏
            </div>
            <div style={{ fontSize: 14, opacity: 0.6, marginTop: 4 }}>
              无需权限，可直接投屏 · 每 {refreshSec} 秒自动刷新
            </div>
          </div>
          <Space size="middle" wrap>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 28, fontVariantNumeric: 'tabular-nums' }}>
                {now.toLocaleTimeString('zh-CN', { hour12: false })}
              </div>
              <div style={{ fontSize: 13, opacity: 0.6 }}>
                {now.toLocaleDateString('zh-CN')}
              </div>
            </div>
            <Select
              size="large"
              value={refreshSec}
              onChange={setRefreshSec}
              style={{ width: 120 }}
              options={[
                { label: '5 秒刷新', value: 5 },
                { label: '10 秒刷新', value: 10 },
                { label: '30 秒刷新', value: 30 },
                { label: '60 秒刷新', value: 60 },
              ]}
            />
            <Button size="large" icon={<ReloadOutlined />} onClick={() => loadRef.current()}>
              立即刷新
            </Button>
            <Button
              size="large"
              type="primary"
              icon={<FullscreenExitOutlined />}
              onClick={exitBigScreen}
            >
              退出大屏
            </Button>
          </Space>
        </div>

        <Row gutter={[20, 20]}>
          <Col xs={24} sm={12} xl={6}>
            {bigCard(
              '设备总数',
              stats.devices,
              `${stats.connectedDevices} 台已连接`,
              <ApiOutlined />, '#1677ff',
            )}
          </Col>
          <Col xs={24} sm={12} xl={6}>
            {bigCard(
              '测试用例',
              stats.testCases,
              '已创建的用例数',
              <ExperimentOutlined />, '#52c41a',
            )}
          </Col>
          <Col xs={24} sm={12} xl={6}>
            {bigCard(
              '测试执行',
              stats.executions,
              `${stats.passedExecutions} 次通过`,
              <PlayCircleOutlined />, '#fa8c16',
            )}
          </Col>
          <Col xs={24} sm={12} xl={6}>
            {bigCard(
              '通过率',
              `${passRate}%`,
              <Progress
                percent={passRate}
                showInfo={false}
                strokeColor={passRate >= 80 ? '#52c41a' : '#faad14'}
                trailColor="rgba(255,255,255,0.12)"
                size="small"
              />,
              <CheckCircleOutlined />, '#eb2f96',
            )}
          </Col>
        </Row>

        <div
          style={{
            flex: 1, minHeight: 240, marginTop: 20,
            background: cardBg,
            border: '1px solid rgba(255,255,255,0.10)',
            borderRadius: 14, padding: '18px 22px',
            overflow: 'auto',
          }}
        >
          <div style={{ fontSize: 18, opacity: 0.85, marginBottom: 10 }}>最近执行</div>
          {recentExecutions.length === 0 ? (
            <div style={{ opacity: 0.5, fontSize: 16, paddingTop: 30, textAlign: 'center' }}>
              暂无执行记录
            </div>
          ) : (
            <List
              dataSource={recentExecutions}
              renderItem={(item: any) => (
                <List.Item style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', padding: '14px 0' }}>
                  <List.Item.Meta
                    avatar={<span style={{ fontSize: 24 }}>{statusIcon(item.status)}</span>}
                    title={
                      <span style={{ color: '#fff', fontSize: 17 }}>
                        执行 {item.id?.slice(0, 8)} · {item.status}
                      </span>
                    }
                    description={
                      <span style={{ color: 'rgba(255,255,255,0.55)', fontSize: 14 }}>
                        {item.started_at ? new Date(item.started_at).toLocaleString('zh-CN') : '-'}
                        {' · 耗时 '}{item.duration_ms ?? '-'} ms
                      </span>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, gap: 12, flexWrap: 'wrap' }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>仪表盘</Title>
          <p style={{ color: '#888', marginTop: 4 }}>AITestLab - AI 驱动的硬件测试平台</p>
        </div>
        <Tooltip title="投屏到产线/实验室大屏：超大字号、自动刷新（无权限控制）">
          <Button type="primary" icon={<FullscreenOutlined />} onClick={enterBigScreen}>
            大屏模式
          </Button>
        </Tooltip>
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
