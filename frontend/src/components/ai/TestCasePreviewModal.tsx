import { Modal, Descriptions, Table, Tag, Typography, Empty, Space, Button, Divider } from 'antd'
import { ImportOutlined } from '@ant-design/icons'

const { Text, Paragraph } = Typography

interface Props {
  open: boolean
  testCase: any | null
  onClose: () => void
  onImport?: (tc: any) => void
  importing?: boolean
}

/** Render a single generated test case in full detail before importing it. */
export default function TestCasePreviewModal({
  open, testCase, onClose, onImport, importing,
}: Props) {
  const tc = testCase
  const steps = tc?.steps || []

  const columns = [
    {
      title: '#',
      dataIndex: 'step_number',
      key: 'step_number',
      width: 44,
      render: (v: any, _r: any, i: number) => v ?? i + 1,
    },
    {
      title: '动作 / 类型',
      key: 'action',
      render: (_: any, s: any) => (
        <Space direction="vertical" size={2}>
          <Text>{s.action || '—'}</Text>
          <Space size={4}>
            <Tag color={s.flow_type === 'delay' ? 'orange' : 'blue'}>
              {s.flow_type || 'action'}
            </Tag>
            {s.device_type && <Tag>{s.device_type}</Tag>}
          </Space>
        </Space>
      ),
    },
    {
      title: '命令 / 参数',
      key: 'params',
      render: (_: any, s: any) => {
        const p = s.parameters || {}
        const cmd = p.command || (Array.isArray(p.commands) ? p.commands.join(' ; ') : '')
        const rest = Object.entries(p).filter(
          ([k]) => !['command', 'commands'].includes(k),
        )
        return (
          <Space direction="vertical" size={2}>
            {cmd ? (
              <Text code style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {cmd}
              </Text>
            ) : (
              <Text type="secondary">—</Text>
            )}
            {rest.length > 0 && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {rest.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join('  ')}
              </Text>
            )}
          </Space>
        )
      },
    },
    {
      title: '预期结果',
      dataIndex: 'expected_result',
      key: 'expected_result',
      render: (v: string) => v || <Text type="secondary">—</Text>,
    },
  ]

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={860}
      title={tc ? `用例预览：${tc.name}` : '用例预览'}
      footer={[
        <Button key="close" onClick={onClose}>关闭</Button>,
        onImport && (
          <Button
            key="import"
            type="primary"
            icon={<ImportOutlined />}
            loading={importing}
            onClick={() => tc && onImport(tc)}
          >
            添加到测试用例列表
          </Button>
        ),
      ]}
    >
      {!tc ? (
        <Empty description="没有可预览的用例" />
      ) : (
        <div style={{ maxHeight: '65vh', overflow: 'auto' }}>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="用例名称">{tc.name}</Descriptions.Item>
            <Descriptions.Item label="描述">
              {tc.description || <Text type="secondary">—</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="整体预期">
              {tc.expected_result || <Text type="secondary">—</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="需要设备">
              {Array.isArray(tc.devices_required) && tc.devices_required.length > 0
                ? tc.devices_required.map((d: string) => <Tag key={d}>{d}</Tag>)
                : <Text type="secondary">—</Text>}
            </Descriptions.Item>
            <Descriptions.Item label="标签">
              {Array.isArray(tc.tags) && tc.tags.length > 0
                ? tc.tags.map((t: string) => <Tag key={t} color="blue">{t}</Tag>)
                : <Text type="secondary">—</Text>}
            </Descriptions.Item>
          </Descriptions>

          <Divider orientation="left" style={{ marginTop: 20 }}>
            测试步骤（{steps.length}）
          </Divider>
          {steps.length > 0 ? (
            <Table
              rowKey={(_, i) => String(i)}
              dataSource={steps}
              columns={columns}
              pagination={false}
              size="small"
            />
          ) : (
            <Empty description="该用例没有步骤" />
          )}

          {tc.flow_description && (
            <>
              <Divider orientation="left">流程说明</Divider>
              <Paragraph style={{ whiteSpace: 'pre-wrap' }}>
                {tc.flow_description}
              </Paragraph>
            </>
          )}
        </div>
      )}
    </Modal>
  )
}
