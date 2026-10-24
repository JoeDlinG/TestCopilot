import { useEffect, useState } from 'react'
import {
  Modal, Form, Input, InputNumber, Select, Switch, Space, Alert,
  Typography, Tag, Skeleton, message,
} from 'antd'
import { deviceAPI } from '../../services/api'
import { extractData, handleApiError } from '../../services/apiHelper'
import { useI18n } from '../../i18n'
import type { Device } from '../../types'

const { Text } = Typography

interface FieldSpec {
  key: string
  label: string
  type: string
  store: string
  required: boolean
  default?: any
  options?: any[]
  placeholder?: string
  help?: string
}

interface InterfaceSpec {
  type: string
  label: string
  protocol: string
  simulated?: boolean
  note?: string
  fields: FieldSpec[]
}

interface Props {
  open: boolean
  device: Device | null
  onClose: () => void
  onSaved: () => void
}

/** Edit how a device is physically attached (interface type + its parameters). */
export default function InterfaceConfigModal({ open, device, onClose, onSaved }: Props) {
  const [specs, setSpecs] = useState<InterfaceSpec[]>([])
  const [currentType, setCurrentType] = useState<string>('')
  const [params, setParams] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()
  const { t } = useI18n()

  /** Backend labels are Chinese; use the catalogue entry when we have one. */
  const labelFor = (key: string, fallback: string) => {
    const value = t(key)
    return value === key ? fallback : value
  }

  useEffect(() => {
    if (!open) return
    loadSpecs()
  }, [open])

  useEffect(() => {
    if (!open || !device) return
    loadCurrent()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, device?.id])

  const loadSpecs = async () => {
    try {
      const res = await deviceAPI.listInterfaces()
      setSpecs(extractData(res, []))
    } catch (err) {
      handleApiError(err, '加载接口类型失败')
    }
  }

  const loadCurrent = async () => {
    if (!device) return
    setLoading(true)
    try {
      const res = await deviceAPI.getInterface(device.id)
      const data: any = extractData(res, {})
      const type = data.connection_type || 'serial'
      setCurrentType(type)
      setParams(data.params || {})
      form.setFieldsValue({ connection_type: type, ...(data.params || {}) })
    } catch (err) {
      handleApiError(err, '读取接口配置失败')
    } finally {
      setLoading(false)
    }
  }

  const spec = specs.find((s) => s.type === currentType)

  const onTypeChange = (type: string) => {
    const next = specs.find((s) => s.type === type)
    setCurrentType(type)
    // Reset the parameter fields to the newly chosen interface's defaults so
    // leftover values (e.g. baudrate) are never sent for another bus.
    const defaults: Record<string, any> = {}
    ;(next?.fields || []).forEach((f) => {
      if (f.default !== undefined && f.default !== null) defaults[f.key] = f.default
    })
    setParams(defaults)
    form.setFieldsValue({ connection_type: type, ...defaults })
  }

  const handleSave = async () => {
    if (!device) return
    let values: any = {}
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    const { connection_type, ...rest } = values
    setSaving(true)
    try {
      await deviceAPI.updateInterface(device.id, connection_type, rest)
      message.success('接口配置已保存')
      onSaved()
      onClose()
    } catch (err) {
      handleApiError(err, '保存接口配置失败')
    } finally {
      setSaving(false)
    }
  }

  const renderField = (f: FieldSpec) => {
    const common = { placeholder: f.placeholder, style: { width: '100%' } }
    if (f.options && f.options.length > 0) {
      return (
        <Select
          options={f.options.map((o) => ({ label: String(o), value: o }))}
          placeholder={f.placeholder || '请选择'}
        />
      )
    }
    if (f.type === 'boolean') {
      return <Switch />
    }
    if (f.type === 'integer' || f.type === 'number') {
      return <InputNumber {...common} style={{ width: '100%' }} />
    }
    return <Input {...common} />
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      confirmLoading={saving}
      okText={t('common.save')}
      cancelText={t('common.cancel')}
      width={620}
      title={
        <Space>
          <span>{t('iface.configTitle')}</span>
          {device && <Tag>{device.name}</Tag>}
        </Space>
      }
    >
      {loading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : (
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {spec?.note && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message={spec.label}
              description={spec.note}
            />
          )}

          <Form.Item
            name="connection_type"
            label={t('iface.type')}
            rules={[{ required: true, message: t('iface.type') }]}
          >
            <Select
              onChange={onTypeChange}
              options={specs.map((s) => ({
                label: s.simulated
                  ? `${labelFor(`iface.t.${s.type}`, s.label)}（模拟/simulated）`
                  : labelFor(`iface.t.${s.type}`, s.label),
                value: s.type,
              }))}
            />
          </Form.Item>

          {spec ? (
            spec.fields.map((f) => (
              <Form.Item
                key={f.key}
                name={f.key}
                label={labelFor(`iface.f.${f.key}`, f.label)}
                valuePropName={f.type === 'boolean' ? 'checked' : 'value'}
                rules={
                  f.required
                    ? [{ required: true, message: labelFor(`iface.f.${f.key}`, f.label) }]
                    : undefined
                }
                extra={f.help}
              >
                {renderField(f)}
              </Form.Item>
            ))
          ) : (
            <Text type="secondary">
              {specs.length === 0 ? '正在加载接口类型…' : '请选择接口类型'}
            </Text>
          )}

          {spec && (
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 8 }}
              message={t('iface.switchHint', {
                label: labelFor(`iface.t.${spec.type}`, spec.label),
              })}
            />
          )}
        </Form>
      )}
    </Modal>
  )
}
