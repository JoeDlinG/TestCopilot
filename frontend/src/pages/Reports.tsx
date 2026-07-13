import { useEffect, useState } from 'react'
import {
  Card, Table, Button, Space, Tag, message, Typography, Modal, Form,
  Input, Select, Row, Col, Empty, Popconfirm, List
} from 'antd'
import {
  PlusOutlined, FileTextOutlined, DownloadOutlined,
  ReloadOutlined, EyeOutlined, FilePdfOutlined, FileExcelOutlined
} from '@ant-design/icons'
import { reportAPI, executionAPI } from '../services/api'
import { extractData, extractItems, handleApiError } from '../services/apiHelper'
import type { TestReport, ReportTemplate, TestExecution } from '../types'

const { Title, Text } = Typography

export default function Reports() {
  const [reports, setReports] = useState<TestReport[]>([])
  const [templates, setTemplates] = useState<ReportTemplate[]>([])
  const [executions, setExecutions] = useState<TestExecution[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [templateModalVisible, setTemplateModalVisible] = useState(false)
  const [form] = Form.useForm()
  const [templateForm] = Form.useForm()

  const loadData = async () => {
    setLoading(true)
    try {
      const [reportsRes, templatesRes, execsRes] = await Promise.all([
        reportAPI.list().catch(() => ({ data: { code: 0, data: [] } })),
        reportAPI.listTemplates().catch(() => ({ data: { code: 0, data: [] } })),
        executionAPI.list().catch(() => ({ data: { code: 0, data: { items: [] } } })),
      ])
      setReports(extractData(reportsRes, []))
      setTemplates(extractData(templatesRes, []))
      setExecutions(extractItems(execsRes))
    } catch (err) {
      handleApiError(err, '加载数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handleGenerate = async (values: any) => {
    try {
      // Map frontend form fields to backend API fields
      const payload = {
        title: values.name,
        execution_id: Array.isArray(values.execution_ids) ? values.execution_ids[0] : values.execution_ids,
        template_id: values.template_id,
        format: values.format || 'pdf',
        fields: values.fields ? (typeof values.fields === 'string' ? JSON.parse(values.fields) : values.fields) : {},
      }
      await reportAPI.generate(payload)
      message.success('报告已生成')
      setModalVisible(false)
      form.resetFields()
      loadData()
    } catch (err) {
      handleApiError(err, '生成报告失败')
    }
  }

  const handleCreateTemplate = async (values: any) => {
    try {
      // Parse fields from JSON or comma-separated string
      let fields = values.fields
      if (typeof fields === 'string') {
        fields = fields.split(',').map((f: string) => ({
          name: f.trim(),
          label: f.trim(),
        }))
      }
      await reportAPI.createTemplate({ ...values, fields })
      message.success('模板已创建')
      setTemplateModalVisible(false)
      templateForm.resetFields()
      loadData()
    } catch (err) {
      handleApiError(err, '创建模板失败')
    }
  }

  const formatIcon = (format: string) => {
    switch (format) {
      case 'pdf': return <FilePdfOutlined style={{ color: '#ff4d4f' }} />
      case 'csv': return <FileExcelOutlined style={{ color: '#52c41a' }} />
      default: return <FileTextOutlined />
    }
  }

  const reportColumns = [
    {
      title: '报告名称',
      dataIndex: 'title',
      key: 'title',
      render: (name: string, record: TestReport) => (
        <Space>
          {formatIcon(record.format)}
          {name}
        </Space>
      ),
    },
    {
      title: '格式',
      dataIndex: 'format',
      key: 'format',
      render: (f: string) => <Tag>{f.toUpperCase()}</Tag>,
    },
    {
      title: '执行数量',
      dataIndex: 'execution_ids',
      key: 'execution_ids',
      render: (ids: string[]) => ids?.length || 0,
    },
    {
      title: '生成时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: TestReport) => (
        <Button
          size="small"
          icon={<DownloadOutlined />}
          disabled={!record.file_path}
          onClick={() => message.info('下载功能开发中')}
        >
          下载
        </Button>
      ),
    },
  ]

  const templateColumns = [
    { title: '模板名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '字段数',
      dataIndex: 'fields',
      key: 'fields',
      render: (fields: any[]) => fields?.length || 0,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>测试报告</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
          <Button
            onClick={() => {
              setTemplateModalVisible(true)
              templateForm.resetFields()
            }}
          >
            创建模板
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setModalVisible(true)
              form.resetFields()
            }}
          >
            生成报告
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="报告列表">
            <Table
              columns={reportColumns}
              dataSource={reports}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
              locale={{ emptyText: <Empty description="暂无报告" /> }}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="报告模板">
            <Table
              columns={templateColumns}
              dataSource={templates}
              rowKey="id"
              loading={loading}
              pagination={false}
              locale={{ emptyText: <Empty description="暂无模板" /> }}
            />
          </Card>
        </Col>
      </Row>

      {/* Generate Report Modal */}
      <Modal
        title="生成测试报告"
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => form.submit()}
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleGenerate}>
          <Form.Item name="name" label="报告名称" rules={[{ required: true }]}>
            <Input placeholder="输入报告名称" />
          </Form.Item>
          <Form.Item name="execution_ids" label="选择执行记录" rules={[{ required: true }]}>
            <Select
              mode="multiple"
              placeholder="选择要包含的执行记录"
              options={executions.map(e => ({
                label: `${e.id?.slice(0, 8)}... - ${e.status}`,
                value: e.id,
              }))}
            />
          </Form.Item>
          <Form.Item name="template_id" label="报告模板">
            <Select
              allowClear
              placeholder="选择模板（可选）"
              options={templates.map(t => ({ label: t.name, value: t.id }))}
            />
          </Form.Item>
          <Form.Item name="format" label="输出格式" initialValue="pdf">
            <Select
              options={[
                { label: 'PDF', value: 'pdf' },
                { label: 'HTML', value: 'html' },
                { label: 'CSV', value: 'csv' },
                { label: 'DOCX', value: 'docx' },
              ]}
            />
          </Form.Item>
          <Form.Item name="fields" label="自定义字段 (JSON)">
            <Input.TextArea
              rows={3}
              placeholder='{"测试人员": "", "测试环境": "", "备注": ""}'
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Create Template Modal */}
      <Modal
        title="创建报告模板"
        open={templateModalVisible}
        onCancel={() => setTemplateModalVisible(false)}
        onOk={() => templateForm.submit()}
        width={560}
      >
        <Form form={templateForm} layout="vertical" onFinish={handleCreateTemplate}>
          <Form.Item name="name" label="模板名称" rules={[{ required: true }]}>
            <Input placeholder="输入模板名称" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="模板描述" />
          </Form.Item>
          <Form.Item name="fields" label="字段定义（逗号分隔）" rules={[{ required: true }]}>
            <Input placeholder="测试人员, 测试环境, 测试日期, 备注" />
          </Form.Item>
          <Form.Item name="template_content" label="Jinja2 模板内容">
            <Input.TextArea rows={6} placeholder="<h1>{{ report_title }}</h1>..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
