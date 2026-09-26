import { useEffect, useState } from 'react'
import {
  Modal, Button, Space, Table, Tag, Input, InputNumber, Select,
  Card, Row, Col, Empty, Alert, Typography, Tooltip, Divider
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, ExperimentOutlined, CopyOutlined
} from '@ant-design/icons'
import { testCaseAPI } from '../services/api'
import { handleApiError } from '../services/apiHelper'

const { Text, Title } = Typography

export const DATA_TYPES = [
  { value: 'hex', label: '十六进制 (hex)' },
  { value: 'bin', label: '二进制 (bin)' },
  { value: 'bool', label: '布尔 (bool)' },
  { value: 'dec', label: '十进制数值 (dec)' },
  { value: 'string', label: '字符串 (string)' },
]

const UNITS = [
  { value: 'byte', label: '字节 (byte)' },
  { value: 'bit', label: '位 (bit)' },
]

export type ParserSpec = {
  name?: string
  data_type: 'hex' | 'bin' | 'bool' | 'dec' | 'string'
  start: number
  length: number
  unit: 'bit' | 'byte'
  conditions?: {
    min?: number | null
    max?: number | null
    equals?: string[]
  }
}

type Props = {
  open: boolean
  stepLabel: string
  parsers: ParserSpec[]
  /** A real response captured from a previous run, used to seed the preview */
  initialSample?: string
  saving?: boolean
  onCancel: () => void
  onSave: (parsers: ParserSpec[]) => void
}

function blankParser(index: number): ParserSpec {
  return {
    name: `字段${index + 1}`,
    data_type: 'hex',
    start: 0,
    length: 1,
    unit: 'byte',
    conditions: { min: null, max: null, equals: [] },
  }
}

function normalise(p: ParserSpec): ParserSpec {
  return {
    ...p,
    conditions: {
      min: p.conditions?.min ?? null,
      max: p.conditions?.max ?? null,
      equals: (p.conditions?.equals || []).filter(v => String(v).trim() !== ''),
    },
  }
}

export default function ResultParserConfig({
  open, stepLabel, parsers, initialSample, saving, onCancel, onSave,
}: Props) {
  const [items, setItems] = useState<ParserSpec[]>([])
  const [sample, setSample] = useState('')
  const [preview, setPreview] = useState<any[]>([])
  const [previewing, setPreviewing] = useState(false)
  const [allPassed, setAllPassed] = useState<boolean | null>(null)

  // Re-seed the form every time the dialog is opened for a step
  useEffect(() => {
    if (!open) return
    const seeded = (parsers || []).length
      ? (parsers || []).map(normalise)
      : [blankParser(0)]
    setItems(seeded)
    setSample(initialSample || '')
    setPreview([])
    setAllPassed(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const update = (index: number, patch: Partial<ParserSpec>) => {
    setItems(prev => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)))
  }

  const updateCondition = (index: number, patch: Partial<NonNullable<ParserSpec['conditions']>>) => {
    setItems(prev => prev.map((it, i) => (
      i === index ? { ...it, conditions: { ...(it.conditions || {}), ...patch } } : it
    )))
  }

  const addItem = () => setItems(prev => [...prev, blankParser(prev.length)])
  const removeItem = (index: number) => setItems(prev => prev.filter((_, i) => i !== index))

  const runPreview = async () => {
    if (!items.length) return
    setPreviewing(true)
    try {
      const res = await testCaseAPI.parsePreview(sample, items.map(normalise))
      const data = res.data?.data ?? res.data
      setPreview(data?.parsed || [])
      setAllPassed(!!data?.all_passed)
    } catch (err) {
      handleApiError(err, '预览解析失败')
    } finally {
      setPreviewing(false)
    }
  }

  const hasJudgement = items.some(it => {
    const c = it.conditions || {}
    return c.min != null || c.max != null || (c.equals && c.equals.length > 0)
  })

  return (
    <Modal
      title={<Space><ExperimentOutlined /><span>结果解析配置</span></Space>}
      width={900}
      open={open}
      onCancel={onCancel}
      onOk={() => onSave(items.map(normalise))}
      confirmLoading={saving}
      okText="保存解析配置"
      cancelText="取消"
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message={`测试步骤：${stepLabel}`}
        description="选择数据类型后，按「起始位 + 数据长度 + 单位」从返回结果中取值，再设置判断条件。判断不通过时该步骤将判定为失败。"
      />

      {/* ---------- parser definitions ---------- */}
      {items.map((item, index) => (
        <Card
          key={index}
          size="small"
          style={{ marginBottom: 10, background: '#fafafa' }}
          title={<Space><Tag color="blue">解析项 {index + 1}</Tag><Text strong>{item.name || ''}</Text></Space>}
          extra={<Button size="small" danger type="text" icon={<DeleteOutlined />} onClick={() => removeItem(index)} disabled={items.length === 1}>删除</Button>}
        >
          <Row gutter={8}>
            <Col span={7}>
              <Text type="secondary" style={{ fontSize: 12 }}>名称</Text>
              <Input
                size="small"
                style={{ marginTop: 2 }}
                placeholder="如：母线电压"
                value={item.name}
                onChange={e => update(index, { name: e.target.value })}
              />
            </Col>
            <Col span={7}>
              <Text type="secondary" style={{ fontSize: 12 }}>数据类型</Text>
              <Select
                size="small"
                style={{ width: '100%', marginTop: 2 }}
                value={item.data_type}
                options={DATA_TYPES}
                onChange={v => update(index, { data_type: v })}
              />
            </Col>
            <Col span={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>起始位</Text>
              <InputNumber
                size="small" min={0} style={{ width: '100%', marginTop: 2 }}
                value={item.start}
                onChange={v => update(index, { start: Number(v ?? 0) })}
              />
            </Col>
            <Col span={3}>
              <Text type="secondary" style={{ fontSize: 12 }}>长度</Text>
              <InputNumber
                size="small" min={1} style={{ width: '100%', marginTop: 2 }}
                value={item.length}
                onChange={v => update(index, { length: Number(v ?? 1) })}
              />
            </Col>
            <Col span={3}>
              <Text type="secondary" style={{ fontSize: 12 }}>单位</Text>
              <Select
                size="small"
                style={{ width: '100%', marginTop: 2 }}
                value={item.unit}
                options={UNITS}
                onChange={v => update(index, { unit: v })}
              />
            </Col>
          </Row>

          <Divider style={{ margin: '10px 0 6px' }} />
          <Text type="secondary" style={{ fontSize: 12 }}>判断条件（可只填范围或只填等于；两者都填时需同时满足）</Text>
          <Row gutter={8} style={{ marginTop: 4 }}>
            <Col span={5}>
              <InputNumber
                size="small" style={{ width: '100%' }} placeholder="最小值"
                value={item.conditions?.min ?? null}
                onChange={v => updateCondition(index, { min: v as any })}
              />
            </Col>
            <Col span={5}>
              <InputNumber
                size="small" style={{ width: '100%' }} placeholder="最大值"
                value={item.conditions?.max ?? null}
                onChange={v => updateCondition(index, { max: v as any })}
              />
            </Col>
            <Col span={14}>
              <Tooltip title="可输入多个值，回车添加；满足任意一个即判定通过（或运算）">
                <Select
                  size="small" mode="tags" style={{ width: '100%' }}
                  placeholder="等于（可多选，或运算）"
                  value={item.conditions?.equals || []}
                  onChange={v => updateCondition(index, { equals: v as string[] })}
                  open={false}
                  suffixIcon={null}
                />
              </Tooltip>
            </Col>
          </Row>
        </Card>
      ))}

      <Button size="small" type="dashed" block icon={<PlusOutlined />} onClick={addItem}>
        添加解析项
      </Button>

      {/* ---------- live preview ---------- */}
      <Divider />
      <Title level={5} style={{ fontSize: 13 }}>解析预览</Title>
      <Space.Compact style={{ width: '100%', marginBottom: 8 }}>
        <Input
          placeholder="粘贴一条真实返回结果，例如 CAN1,RPLY1,0X850201"
          value={sample}
          onChange={e => setSample(e.target.value)}
        />
        <Button icon={<ExperimentOutlined />} onClick={runPreview} loading={previewing}>
          预览解析
        </Button>
      </Space.Compact>

      {preview.length > 0 ? (
        <>
          <Alert
            type={allPassed ? 'success' : 'error'}
            showIcon
            style={{ marginBottom: 8 }}
            message={allPassed ? '全部判断通过' : '存在未通过的判断'}
          />
          <Table
            size="small"
            rowKey={(r: any, i?: number) => `${r.name}-${i}`}
            pagination={false}
            dataSource={preview}
            columns={[
              { title: '名称', dataIndex: 'name', width: 130 },
              { title: '类型', dataIndex: 'data_type', width: 70 },
              {
                title: '解析值', dataIndex: 'value', width: 150,
                render: (v: any) => (
                  <Text code style={{ fontSize: 11 }}>
                    {v === null || v === undefined ? '-' : String(v)}
                  </Text>
                ),
              },
              {
                title: '判定', dataIndex: 'ok', width: 80,
                render: (ok: boolean) => (
                  <Tag color={ok ? 'green' : 'red'}>{ok ? 'PASS' : 'FAIL'}</Tag>
                ),
              },
              { title: '说明', dataIndex: 'detail' },
            ]}
          />
        </>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="输入返回结果后点击「预览解析」，即可看到解析值与判定"
        />
      )}

      {!hasJudgement && (
        <div style={{ marginTop: 8 }}>
          <Text type="warning" style={{ fontSize: 12 }}>
            未设置任何判断条件时，该步骤仅做解析记录，不影响通过/失败判定。
          </Text>
        </div>
      )}
      <div style={{ marginTop: 6 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          <CopyOutlined /> 提示：起始位从 0 开始；单位为 byte 时按字节偏移，为 bit 时按位偏移（高位在前）。
        </Text>
      </div>
    </Modal>
  )
}
