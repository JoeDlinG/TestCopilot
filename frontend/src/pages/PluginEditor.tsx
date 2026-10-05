/**
 * 插件编辑器 — 基于模板新建插件、在线编辑插件源码并校验。
 *
 * 新建插件时自动套用所选模板（协议 / 设备驱动 / 数据解析 / 报告模板），
 * 并把占位符（插件名、协议名、类名…）替换成用户输入，得到一个可直接运行的示例。
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Button, Space, Typography, List, Input, Form, Select, Tag, message,
  Empty, Modal, Popconfirm, Tooltip, Divider, Switch, Result,
} from 'antd'
import {
  SaveOutlined, PlusOutlined, DeleteOutlined, ReloadOutlined,
  CodeOutlined, CheckCircleOutlined, FileTextOutlined, ApiOutlined,
} from '@ant-design/icons'
import { pluginEditorAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'

const { Title, Text } = Typography
const { TextArea } = Input

interface TemplateItem {
  key: string
  name: string
  plugin_type: string
  description: string
}

interface PluginFileItem {
  module_name: string
  file_name: string
  file_path: string
  classes: string[]
  updated_at?: string
}

const TEMPLATE_TYPE_LABEL: Record<string, string> = {
  protocol: '通信协议',
  device_driver: '设备驱动',
  data_parser: '数据解析',
  report: '报告模板',
}

export default function PluginEditor() {
  const navigate = useNavigate()

  const [templates, setTemplates] = useState<TemplateItem[]>([])
  const [files, setFiles] = useState<PluginFileItem[]>([])
  const [loading, setLoading] = useState(false)

  const [current, setCurrent] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [checkResult, setCheckResult] = useState<any>(null)

  const [createOpen, setCreateOpen] = useState(false)
  const [createForm] = Form.useForm()

  const editorRef = useRef<HTMLTextAreaElement | null>(null)

  const loadAll = async () => {
    setLoading(true)
    try {
      const [tplRes, fileRes] = await Promise.all([
        pluginEditorAPI.listTemplates(),
        pluginEditorAPI.listFiles(),
      ])
      setTemplates(extractData(tplRes, []))
      setFiles(extractData(fileRes, []))
    } catch (err) {
      handleApiError(err, '加载插件/模板失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  const openFile = async (moduleName: string) => {
    try {
      const res = await pluginEditorAPI.readFile(moduleName)
      const data = extractData(res)
      setCurrent(moduleName)
      setContent(data?.content || '')
      setDirty(false)
      setCheckResult(null)
    } catch (err) {
      handleApiError(err, '读取插件文件失败')
    }
  }

  const handleSave = async () => {
    if (!current) return
    setSaving(true)
    try {
      await pluginEditorAPI.writeFile(current, content)
      message.success('插件已保存')
      setDirty(false)
      loadAll()
    } catch (err) {
      handleApiError(err, '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleValidate = async () => {
    if (!current) return
    try {
      const res = await pluginEditorAPI.validate(current, content)
      const data = extractData(res)
      setCheckResult(data)
      if (data?.ok) {
        message.success(`语法检查通过${data?.classes?.length ? `，插件类：${data.classes.join(', ')}` : ''}`)
      } else {
        message.error(data?.error || '检查未通过')
      }
    } catch (err) {
      handleApiError(err, '检查失败')
    }
  }

  const handleDelete = async (moduleName: string) => {
    try {
      await pluginEditorAPI.deleteFile(moduleName)
      message.success(`已删除 ${moduleName}.py`)
      if (current === moduleName) {
        setCurrent(null); setContent(''); setDirty(false); setCheckResult(null)
      }
      loadAll()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const handleCreate = async (values: any) => {
    try {
      const res = await pluginEditorAPI.createFile({
        plugin_name: values.plugin_name,
        protocol_name: values.protocol_name,
        template_key: values.template_key,
        version: values.version || '1.0.0',
        description: values.description || '',
        author: values.author || '',
        module_name: values.module_name || undefined,
        overwrite: !!values.overwrite,
      })
      const data = extractData(res)
      message.success(`已创建 ${data?.file_name}（模板：${values.template_key}）`)
      setCreateOpen(false)
      createForm.resetFields()
      await loadAll()
      if (data?.module_name) {
        setCurrent(data.module_name)
        setContent(data.content || '')
        setDirty(false)
        setCheckResult(null)
      }
    } catch (err) {
      handleApiError(err, '创建插件失败')
    }
  }

  const insertSnippet = (snippet: string) => {
    const el = editorRef.current
    if (!el) return
    const start = el.selectionStart ?? content.length
    const end = el.selectionEnd ?? start
    const next = content.slice(0, start) + snippet + content.slice(end)
    setContent(next)
    setDirty(true)
  }

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>插件编辑器</Title>
          <Text type="secondary">
            基于模板新建插件（自动套用示例），或直接编辑 plugins/ 下的插件源码
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>
          <Button onClick={() => navigate('/plugins')} icon={<ApiOutlined />}>
            插件管理
          </Button>
          <Button
            type="primary" icon={<PlusOutlined />}
            onClick={() => { setCreateOpen(true); createForm.resetFields() }}
          >
            新建插件
          </Button>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Card
          style={{ width: 300, flex: '0 0 300px' }}
          title={<Space><FileTextOutlined /> plugins/ 目录</Space>}
          loading={loading}
        >
          {files.length === 0 ? (
            <Empty description="暂无插件文件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={files}
              rowKey="module_name"
              renderItem={(item) => (
                <List.Item
                  onClick={() => openFile(item.module_name)}
                  style={{
                    cursor: 'pointer',
                    background: current === item.module_name ? '#e6f4ff' : undefined,
                    paddingLeft: 8, paddingRight: 8,
                  }}
                  actions={[
                    <Popconfirm
                      key="del"
                      title="确认删除该插件文件？"
                      onConfirm={(e) => { e?.stopPropagation(); handleDelete(item.module_name) }}
                    >
                      <Button
                        size="small" type="text" danger icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<span style={{ fontSize: 13 }}>{item.file_name}</span>}
                    description={
                      item.classes?.length
                        ? item.classes.map((c) => <Tag key={c} color="purple">{c}</Tag>)
                        : <Text type="secondary" style={{ fontSize: 12 }}>无插件类</Text>
                    }
                  />
                </List.Item>
              )}
            />
          )}
          <Divider style={{ margin: '8px 0' }} />
          <Text strong style={{ fontSize: 12 }}>可用模板</Text>
          <div style={{ marginTop: 6 }}>
            {templates.map((t) => (
              <Tag key={t.key} color="geekblue" style={{ marginBottom: 4 }}>
                {t.name}（{TEMPLATE_TYPE_LABEL[t.plugin_type] || t.plugin_type}）
              </Tag>
            ))}
          </div>
        </Card>

        <Card style={{ flex: 1, minWidth: 460 }}>
          {!current ? (
            <Result
              icon={<CodeOutlined />}
              title="未选择插件文件"
              subTitle="从左侧选择一个插件，或点击「新建插件」从模板创建"
            />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size="middle">
              <Space wrap>
                <Text strong>{current}.py</Text>
                {dirty && <Tag color="orange">未保存</Tag>}
                {!dirty && <Tag color="green">已同步</Tag>}
                <Button
                  type="primary" icon={<SaveOutlined />} loading={saving}
                  onClick={handleSave}
                >
                  保存
                </Button>
                <Button icon={<CheckCircleOutlined />} onClick={handleValidate}>
                  语法校验
                </Button>
                <Tooltip title="插入一个 send 方法骨架">
                  <Button size="small" onClick={() => insertSnippet(
                    "\n    async def send(self, data):\n        if not self._connected:\n            raise ConnectionError(\"未连接设备\")\n        return str(data)\n",
                  )}>插入 send 示例</Button>
                </Tooltip>
              </Space>

              {checkResult && (
                <Tag color={checkResult.ok ? 'green' : 'red'}>
                  {checkResult.ok
                    ? `校验通过${checkResult.classes?.length ? ` · 插件类：${checkResult.classes.join(', ')}` : ''}`
                    : `校验失败：${checkResult.error}`}
                </Tag>
              )}

              <TextArea
                ref={(el: any) => { editorRef.current = el?.resizableTextArea?.textArea ?? el }}
                value={content}
                onChange={(e) => { setContent(e.target.value); setDirty(true) }}
                spellCheck={false}
                style={{
                  minHeight: 'calc(100vh - 340px)',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: 13, lineHeight: 1.6,
                  whiteSpace: 'pre', overflow: 'auto',
                }}
              />

              <Text type="secondary" style={{ fontSize: 12 }}>
                保存后到「插件管理」页扫描并安装即可生效；插件类需继承
                <code> BaseProtocolPlugin </code>并实现 connect / disconnect / send / receive。
              </Text>
            </Space>
          )}
        </Card>
      </div>

      <Modal
        title="新建插件（从模板创建）"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        width={620}
        okText="创建"
      >
        <Form form={createForm} layout="vertical" onFinish={handleCreate}
          initialValues={{ template_key: 'protocol_plugin', version: '1.0.0' }}>
          <Form.Item name="plugin_name" label="插件名称" rules={[{ required: true }]}>
            <Input placeholder="例如：Mini Gateway 100" />
          </Form.Item>
          <Form.Item
            name="protocol_name" label="协议标识" rules={[{ required: true }]}
            extra="小写字母/数字/下划线/连字符，设备 protocol 字段会用它"
          >
            <Input placeholder="例如：mini_gateway100" />
          </Form.Item>
          <Form.Item name="template_key" label="插件模板" rules={[{ required: true }]}>
            <Select
              options={templates.map((t) => ({
                label: `${t.name}（${TEMPLATE_TYPE_LABEL[t.plugin_type] || t.plugin_type}）— ${t.description}`,
                value: t.key,
              }))}
              placeholder="选择模板"
            />
          </Form.Item>
          <Space wrap>
            <Form.Item name="version" label="版本">
              <Input style={{ width: 140 }} placeholder="1.0.0" />
            </Form.Item>
            <Form.Item name="author" label="作者">
              <Input style={{ width: 160 }} placeholder="可选" />
            </Form.Item>
            <Form.Item name="module_name" label="文件名(可选)">
              <Input style={{ width: 200 }} placeholder="默认 <协议>_plugin.py" />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <Input placeholder="插件功能一句话描述" />
          </Form.Item>
          <Form.Item name="overwrite" label="覆盖同名文件" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Text type="secondary" style={{ fontSize: 12 }}>
            创建后会自动填充模板占位符（插件名 / 协议名 / 类名 / 版本 / 日期），
            并在编辑器中打开，可直接运行「语法校验」。
          </Text>
        </Form>
      </Modal>
    </div>
  )
}
