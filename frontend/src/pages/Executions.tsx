import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Progress, Empty, Statistic, Row, Col
} from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, CheckCircleOutlined,
  CloseCircleOutlined, SyncOutlined, ReloadOutlined, ExclamationCircleOutlined
} from '@ant-design/icons'
import { executionAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import type { TestExecution } from '../types'

const { Title, Text } = Typography

export default function Executions() {
  const [executions, setExecutions] = useState<TestExecution[]>([])
  const [loading, setLoading] = useState(false)

  const loadExecutions = async () => {
    setLoading(true)
    try {
      const res = await executionAPI.list()
      setExecutions(extractItems(res))
    } catch (err) {
      handleApiError(err, '加载执行记录失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadExecutions() }, [])

  const handleStop = async (id: string) => {
    try {
      await executionAPI.stop(id)
      message.success('已停止执行')
      loadExecutions()
    } catch (err) {
      handleApiError(err, '停止失败')
    }
  }

  const statusConfig: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
    pending: { color: 'default', icon: <SyncOutlined />, text: '等待中' },
    running: { color: 'processing', icon: <SyncOutlined spin />, text: '运行中' },
    passed: { color: 'success', icon: <CheckCircleOutlined />, text: '通过' },
    failed: { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
    error: { color: 'warning', icon: <ExclamationCircleOutlined />, text: '异常' },
    stopped: { color: 'default', icon: <PauseCircleOutlined />, text: '已停止' },
  }

  const stats = {
    total: executions.length,
    passed: executions.filter(e => e.status === 'passed').length,
    failed: executions.filter(e => e.status === 'failed').length,
    running: executions.filter(e => e.status === 'running').length,
    passRate: executions.length > 0
      ? Math.round((executions.filter(e => e.status === 'passed').length / executions.length) * 100)
      : 0,
  }

  const columns = [
    {
      title: '执行 ID',
      dataIndex: 'id',
      key: 'id',
      render: (id: string) => id.slice(0, 8) + '...',
    },
    {
      title: '测试用例 ID',
      dataIndex: 'testcase_id',
      key: 'testcase_id',
      render: (id: string) => id?.slice(0, 8) + '...' || '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => {
        const config = statusConfig[status] || statusConfig.pending
        return (
          <Tag icon={config.icon} color={config.color}>{config.text}</Tag>
        )
      },
    },
    {
      title: '开始时间',
      dataIndex: 'started_at',
      key: 'started_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '结束时间',
      dataIndex: 'completed_at',
      key: 'completed_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '耗时 (ms)',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      render: (v: number) => v ?? '-',
    },
    {
      title: '结果详情',
      dataIndex: 'results',
      key: 'results',
      render: (results: any[]) => {
        if (!results?.length) return '-'
        return `${results.filter((r: any) => r.status === 'passed').length}/${results.length} 通过`
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: TestExecution) => (
        <Space>
          {record.status === 'running' && (
            <Button
              size="small"
              danger
              icon={<PauseCircleOutlined />}
              onClick={() => handleStop(record.id)}
            >
              停止
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>测试执行</Title>
        <Button icon={<ReloadOutlined />} onClick={loadExecutions}>刷新</Button>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic title="总执行次数" value={stats.total} prefix={<PlayCircleOutlined />} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="通过"
              value={stats.passed}
              valueStyle={{ color: '#52c41a' }}
              prefix={<CheckCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="失败"
              value={stats.failed}
              valueStyle={{ color: '#ff4d4f' }}
              prefix={<CloseCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card>
            <Statistic
              title="通过率"
              value={stats.passRate}
              suffix="%"
              valueStyle={{ color: stats.passRate >= 80 ? '#52c41a' : '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      <Card>
        <Table
          columns={columns}
          dataSource={executions}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{ emptyText: <Empty description="暂无执行记录" /> }}
        />
      </Card>
    </div>
  )
}
