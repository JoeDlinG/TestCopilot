import { Drawer, Form, Input, InputNumber, Select, Switch, Typography, Empty } from 'antd'
import type { DashboardWidget, DashboardSnapshot } from '../../types'
import { WIDGET_META } from './registry'

const { Text } = Typography

type Props = {
  open: boolean
  widget: DashboardWidget | null
  snapshot: DashboardSnapshot | null
  onClose: () => void
  onChange: (widget: DashboardWidget) => void
}

export default function WidgetConfigDrawer({
  open, widget, snapshot, onClose, onChange,
}: Props) {
  if (!widget) return null

  const meta = WIDGET_META[widget.type]
  const fields: string[] = snapshot?.parsed?.fields || []
  const setCfg = (patch: Record<string, any>) =>
    onChange({ ...widget, config: { ...widget.config, ...patch } })

  return (
    <Drawer
      title={`配置 — ${meta?.label || widget.type}`}
      open={open}
      onClose={onClose}
      width={420}
      destroyOnClose
    >
      <Form layout="vertical" size="middle">
        <Form.Item label="标题">
          <Input
            value={widget.title}
            onChange={(e) => onChange({ ...widget, title: e.target.value })}
          />
        </Form.Item>

        {widget.type === 'parsed_value' && (
          <Form.Item
            label="解析字段"
            extra="来自该用例步骤的结果解析配置；需要先在顶部数据源选中用例"
          >
            {fields.length ? (
              <Select
                value={widget.config?.field || undefined}
                placeholder="选择要盯的解析量"
                onChange={(v: any) => setCfg({ field: v })}
                options={fields.map((f) => ({ label: f, value: f }))}
                showSearch
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="该用例暂无解析字段，先执行一次带解析的用例"
              />
            )}
          </Form.Item>
        )}

        {widget.type === 'trend_chart' && (
          <>
            <Form.Item label="解析字段（可多选）">
              <Select
                mode="multiple"
                value={widget.config?.fields || []}
                placeholder="选择要绘制的曲线"
                onChange={(v: any) => setCfg({ fields: v })}
                options={fields.map((f) => ({ label: f, value: f }))}
                showSearch
              />
            </Form.Item>
            <Form.Item label="图表高度 (px)">
              <InputNumber
                min={120}
                max={800}
                value={Number(widget.config?.height) || 300}
                onChange={(v) => setCfg({ height: v ?? 300 })}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item label="FAIL 点标红" valuePropName="checked">
              <Switch
                checked={widget.config?.show_fail_dots !== false}
                onChange={(v) => setCfg({ show_fail_dots: v })}
              />
            </Form.Item>
            <Form.Item label="参考下限（可选）">
              <InputNumber
                value={widget.config?.min_value ?? undefined}
                onChange={(v) => setCfg({ min_value: v })}
                style={{ width: '100%' }}
                placeholder="画一条下限参考线"
              />
            </Form.Item>
            <Form.Item label="参考上限（可选）">
              <InputNumber
                value={widget.config?.max_value ?? undefined}
                onChange={(v) => setCfg({ max_value: v })}
                style={{ width: '100%' }}
                placeholder="画一条上限参考线"
              />
            </Form.Item>
          </>
        )}

        {widget.type === 'judge_summary' && (
          <Form.Item label="FAIL 明细最多显示条数">
            <InputNumber
              min={1}
              max={200}
              value={Number(widget.config?.max_failures) || 20}
              onChange={(v) => setCfg({ max_failures: v ?? 20 })}
              style={{ width: '100%' }}
            />
          </Form.Item>
        )}

        {widget.type === 'comm_log' && (
          <>
            <Form.Item label="显示条数">
              <InputNumber
                min={1}
                max={100}
                value={Number(widget.config?.limit) || 12}
                onChange={(v) => setCfg({ limit: v ?? 12 })}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item label="设备过滤（可选）">
              <Select
                allowClear
                value={widget.config?.device_id || undefined}
                placeholder="全部设备"
                onChange={(v: any) => setCfg({ device_id: v || '' })}
                options={(snapshot?.devices?.list || []).map((d: any) => ({
                  label: d.name, value: d.id,
                }))}
                showSearch
                optionFilterProp="label"
              />
            </Form.Item>
          </>
        )}

        {widget.type === 'note' && (
          <Form.Item label="内容（支持 Markdown）">
            <Input.TextArea
              rows={10}
              value={widget.config?.text || ''}
              onChange={(e) => setCfg({ text: e.target.value })}
              placeholder={'例如：\n1. 先上电再接 CAN\n2. 探头比设为 10X'}
            />
          </Form.Item>
        )}

        {(widget.type === 'device_status' || widget.type === 'execution_stats') && (
          <Text type="secondary">
            该组件无需额外配置，数据跟随仪表盘轮询自动刷新。
          </Text>
        )}
      </Form>
    </Drawer>
  )
}
