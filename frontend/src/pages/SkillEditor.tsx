/**
 * Skill 编辑器 — 导入 / 修改 / 保存插件 Skill（Markdown）。
 *
 * Skill 的 frontmatter 支持 name / protocol / keywords，正文为 Markdown，
 * 供 AI 助手与用例生成时按协议自动注入。
 */
import { useEffect, useRef, useState } from 'react'
import {
  Card, Button, Space, Typography, List, Input, Tag, message,
  Empty, Modal, Popconfirm, Upload, Divider, Tooltip,
} from 'antd'
import {
  SaveOutlined, PlusOutlined, DeleteOutlined, ImportOutlined,
  ReloadOutlined, FileMarkdownOutlined, CopyOutlined,
} from '@ant-design/icons'
import { pluginAPI } from '../services/api'
import { extractData, handleApiError } from '../services/apiHelper'

const { Title, Text } = Typography
const { TextArea } = Input

interface SkillMeta {
  protocol: string
  name: string
  keywords: string[]
  has_manual?: boolean
}

const SKILL_SCAFFOLD = `## 适用范围

- 描述本 Skill 针对的设备 / 协议

## 命令生成规则

1. 每个测试步骤直接写设备命令字符串

## 标准测试流程模板

\`\`\`
*IDN?                  ; 1. 识别设备
\`\`\`
`

export default function SkillEditor() {
  const [skills, setSkills] = useState<SkillMeta[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const [current, setCurrent] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [protocol, setProtocol] = useState('')
  const [keywords, setKeywords] = useState('')
  const [content, setContent] = useState('')
  const [dirty, setDirty] = useState(false)
  /** 原始 protocol，用于改名时删除旧文件 */
  const originalProtocolRef = useRef<string | null>(null)

  const [importOpen, setImportOpen] = useState(false)
  const [importName, setImportName] = useState('')
  const [importText, setImportText] = useState('')

  const loadSkills = async () => {
    setLoading(true)
    try {
      const res = await pluginAPI.listSkills()
      setSkills(extractData(res, []))
    } catch (err) {
      handleApiError(err, '加载 Skill 列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadSkills() }, [])

  const openSkill = async (p: string) => {
    try {
      const res = await pluginAPI.getSkill(p)
      const data = extractData(res)
      setCurrent(p)
      originalProtocolRef.current = p
      setName(data?.name || p)
      setProtocol(data?.protocol || p)
      // 关键词只在列表接口里返回，从列表里取
      const meta = skills.find((s) => s.protocol === p)
      setKeywords((meta?.keywords || []).join(', '))
      setContent(data?.skill || '')
      setDirty(false)
    } catch (err) {
      handleApiError(err, '读取 Skill 失败')
    }
  }

  const newSkill = () => {
    setCurrent(null)
    originalProtocolRef.current = null
    setName('')
    setProtocol('')
    setKeywords('')
    setContent(SKILL_SCAFFOLD)
    setDirty(true)
  }

  const handleSave = async () => {
    const p = (protocol || '').trim()
    if (!p) {
      message.warning('请填写协议标识（protocol）')
      return
    }
    setSaving(true)
    try {
      const payload = {
        protocol: p,
        name: name || p,
        keywords: keywords.split(/[,，]/).map((k) => k.trim()).filter(Boolean),
        content,
        rename_from: originalProtocolRef.current,
      }
      if (originalProtocolRef.current) {
        await pluginAPI.updateSkill(originalProtocolRef.current, payload)
      } else {
        await pluginAPI.createSkill(payload)
      }
      message.success('Skill 已保存')
      originalProtocolRef.current = p
      setCurrent(p)
      setDirty(false)
      loadSkills()
    } catch (err) {
      handleApiError(err, '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (p: string) => {
    try {
      await pluginAPI.deleteSkill(p)
      message.success(`Skill ${p} 已删除`)
      if (current === p) {
        setCurrent(null)
        originalProtocolRef.current = null
        setName(''); setProtocol(''); setKeywords(''); setContent('')
        setDirty(false)
      }
      loadSkills()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const handleImport = async () => {
    if (!importText.trim()) {
      message.warning('请先选择或粘贴 .md 内容')
      return
    }
    try {
      await pluginAPI.importSkill({ filename: importName, content: importText })
      message.success('Skill 导入成功')
      setImportOpen(false)
      setImportName('')
      setImportText('')
      loadSkills()
    } catch (err) {
      handleApiError(err, '导入失败')
    }
  }

  const readFileAsText = (file: File) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={3} style={{ margin: 0 }}>Skill 编辑器</Title>
          <Text type="secondary">
            编辑插件 Skill（Markdown）：指导 AI 为对应协议/设备生成测试用例
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>刷新</Button>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>导入</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={newSkill}>新建 Skill</Button>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Card
          style={{ width: 300, flex: '0 0 300px' }}
          title={<Space><FileMarkdownOutlined /> 现有 Skill</Space>}
          loading={loading}
        >
          {skills.length === 0 ? (
            <Empty description="暂无 Skill" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={skills}
              rowKey="protocol"
              renderItem={(item) => (
                <List.Item
                  onClick={() => openSkill(item.protocol)}
                  style={{
                    cursor: 'pointer',
                    background: current === item.protocol ? '#e6f4ff' : undefined,
                    paddingLeft: 8, paddingRight: 8,
                  }}
                  actions={[
                    <Popconfirm
                      key="del"
                      title="确认删除该 Skill？"
                      onConfirm={(e) => { e?.stopPropagation(); handleDelete(item.protocol) }}
                    >
                      <Button
                        size="small" type="text" danger icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={<span style={{ fontSize: 13 }}>{item.name}</span>}
                    description={
                      <Space size={4} wrap>
                        <Tag color="blue">{item.protocol}</Tag>
                        {item.has_manual && <Tag color="green">含手册</Tag>}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>

        <Card style={{ flex: 1, minWidth: 420 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Space wrap>
              <Input
                addonBefore="名称"
                style={{ width: 240 }}
                value={name}
                placeholder="如：SCPI 通用协议"
                onChange={(e) => { setName(e.target.value); setDirty(true) }}
              />
              <Input
                addonBefore="协议标识"
                style={{ width: 240 }}
                value={protocol}
                placeholder="如：scpi"
                onChange={(e) => { setProtocol(e.target.value); setDirty(true) }}
              />
              <Input
                addonBefore="关键词"
                style={{ width: 320 }}
                value={keywords}
                placeholder="逗号分隔，用于 AI 自动匹配"
                onChange={(e) => { setKeywords(e.target.value); setDirty(true) }}
              />
            </Space>

            <TextArea
              value={content}
              onChange={(e) => { setContent(e.target.value); setDirty(true) }}
              placeholder="Skill 正文（Markdown，不含 frontmatter）"
              style={{
                minHeight: 'calc(100vh - 340px)',
                fontFamily: 'Consolas, Monaco, monospace',
                fontSize: 13, lineHeight: 1.6,
              }}
            />

            <Space>
              <Button
                type="primary" icon={<SaveOutlined />} loading={saving}
                onClick={handleSave}
              >
                保存
              </Button>
              <Tooltip title="复制当前正文到剪贴板">
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => {
                    navigator.clipboard.writeText(content)
                    message.success('已复制')
                  }}
                >
                  复制
                </Button>
              </Tooltip>
              {dirty && <Tag color="orange">未保存</Tag>}
              {!dirty && current && <Tag color="green">已同步</Tag>}
            </Space>

            <Divider style={{ margin: '4px 0' }} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              保存后写入 <code>plugins/skills/{'{protocol}'}_skill.md</code>；
              frontmatter（name / protocol / keywords）由上方字段自动生成。
              修改「协议标识」会同步重命名文件。
            </Text>
          </Space>
        </Card>
      </div>

      <Modal
        title="导入 Skill（.md）"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={handleImport}
        width={720}
        okText="导入"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Upload
            accept=".md,.markdown,.txt"
            beforeUpload={async (file) => {
              try {
                const text = await readFileAsText(file as File)
                setImportName(file.name)
                setImportText(text)
                message.success(`已读取 ${file.name}`)
              } catch {
                message.error('文件读取失败')
              }
              return false
            }}
            showUploadList={false}
          >
            <Button icon={<ImportOutlined />}>选择 Markdown 文件</Button>
          </Upload>
          <Text type="secondary" style={{ fontSize: 12 }}>
            也可以直接粘贴内容；protocol 从 frontmatter 或文件名推断（如
            <code>foo_skill.md</code> → <code>foo</code>），已存在则覆盖。
          </Text>
          <TextArea
            rows={14}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder="粘贴 Skill Markdown 内容"
            style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 13 }}
          />
        </Space>
      </Modal>
    </div>
  )
}
