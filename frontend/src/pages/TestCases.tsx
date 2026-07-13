import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Tag, message, Modal,
  Popconfirm, Typography, Tooltip, Form, Input, Select
} from 'antd'
import {
  PlusOutlined, PlayCircleOutlined, EditOutlined,
  DeleteOutlined, ApartmentOutlined, ReloadOutlined,
  ExperimentOutlined
} from '@ant-design/icons'
import { testCaseAPI, executionAPI } from '../services/api'
import { extractItems, handleApiError } from '../services/apiHelper'
import type { TestCase } from '../types'

const { Title } = Typography

export default function TestCases() {
  const navigate = useNavigate()
  const [testCases, setTestCases] = useState<TestCase[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [form] = Form.useForm()

  const loadTestCases = async () => {
    setLoading(true)
    try {
      const res = await testCaseAPI.list()
      setTestCases(extractItems(res))
    } catch (err) {
      handleApiError(err, '加载测试用例失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadTestCases() }, [])

  const handleCreate = async (values: any) => {
    try {
      await testCaseAPI.create(values)
      message.success('测试用例创建成功')
      setModalVisible(false)
      form.resetFields()
      loadTestCases()
    } catch (err) {
      handleApiError(err, '创建失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await testCaseAPI.delete(id)
      message.success('已删除')
      loadTestCases()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const handleRun = async (tc: TestCase) => {
    try {
      await executionAPI.run(tc.id)
      message.success(`开始执行: ${tc.name}`)
      navigate('/executions')
    } catch (err) {
      handleApiError(err, '执行失败')
    }
  }

  const statusColor: Record<string, string> = {
    draft: 'default',
    ready: 'blue',
    running: 'processing',
    completed: 'green',
    failed: 'red',
  }

  const columns = [
    {
      title: '用例名称',
      dataIndex: 'name',
      key: 'name',
      render: (text: string, record: TestCase) => (
        <a onClick={() => navigate(`/testcases/${record.id}/flow`)}>
          <ExperimentOutlined /> {text}
        </a>
      ),
    },
    {
      title: '描述',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
    },
    {
      title: '步骤数',
      key: 'steps',
      render: (_: any, record: TestCase) => record.steps?.length || 0,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) => (
        <Space>
          {(tags || []).map((tag) => (
            <Tag key={tag} color="blue">{tag}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={statusColor[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: TestCase) => (
        <Space>
          <Tooltip title="运行测试">
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={() => handleRun(record)}
            />
          </Tooltip>
          <Tooltip title="流程图编辑">
            <Button
              size="small"
              icon={<ApartmentOutlined />}
              onClick={() => navigate(`/testcases/${record.id}/flow`)}
            />
          </Tooltip>
          <Popconfirm
            title="确定删除此用例？"
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title="删除">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>测试用例</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadTestCases}>刷新</Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            创建用例
          </Button>
        </Space>
      </div>

      <Card>
        <Table
          columns={columns}
          dataSource={testCases}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      <Modal
        title="创建测试用例"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="用例名称" rules={[{ required: true }]}>
            <Input placeholder="输入测试用例名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="输入测试用例描述" />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Select mode="tags" placeholder="输入标签后回车" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
