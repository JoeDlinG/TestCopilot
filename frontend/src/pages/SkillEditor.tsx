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
import { useI18n } from '../i18n'

const { Title, Text } = Typography
const { TextArea } = Input

interface SkillMeta {
  protocol: string
  name: string
  keywords: string[]
  has_manual?: boolean
}

const SKILL_SCAFFOLD = (tr: (k: string) => string) => `## ${tr('label.applicability')}

- ${tr('skill.describeTarget')}

## ${tr('label.commandRules')}

1. ${tr('skill.stepCommandHint')}

## ${tr('label.stdTemplate')}

\`\`\`
*IDN?                  ; 1. identify the ${tr('col.device')}
\`\`\`
`

export default function SkillEditor() {
  const { t } = useI18n()
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
      handleApiError(err, `${t('msg.loadSkillsFailed')}`)
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
      handleApiError(err, `${t('msg.readSkillFailed')}`)
    }
  }

  const newSkill = () => {
    setCurrent(null)
    originalProtocolRef.current = null
    setName('')
    setProtocol('')
    setKeywords('')
    setContent(SKILL_SCAFFOLD(t))
    setDirty(true)
  }

  const handleSave = async () => {
    const p = (protocol || '').trim()
    if (!p) {
      message.warning(t('msg.protocolRequired'))
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
      message.success(`Skill ${t('msg.saved')}`)
      originalProtocolRef.current = p
      setCurrent(p)
      setDirty(false)
      loadSkills()
    } catch (err) {
      handleApiError(err, t('msg.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (p: string) => {
    try {
      await pluginAPI.deleteSkill(p)
      message.success(`Skill ${p} ${t('msg.deleted')}`)
      if (current === p) {
        setCurrent(null)
        originalProtocolRef.current = null
        setName(''); setProtocol(''); setKeywords(''); setContent('')
        setDirty(false)
      }
      loadSkills()
    } catch (err) {
      handleApiError(err, t('msg.deleteFailed'))
    }
  }

  const handleImport = async () => {
    if (!importText.trim()) {
      message.warning(`${t('msg.pickOrPaste')} .md ${t('label.content')}`)
      return
    }
    try {
      await pluginAPI.importSkill({ filename: importName, content: importText })
      message.success(`Skill ${t('msg.importOk')}`)
      setImportOpen(false)
      setImportName('')
      setImportText('')
      loadSkills()
    } catch (err) {
      handleApiError(err, t('msg.importFailed'))
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
          <Title level={3} style={{ margin: 0 }}>{t('tab.skillEditor')}</Title>
          <Text type="secondary">{t('skill.editorDesc')}</Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>{t('common.refresh')}</Button>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>{t('common.import')}</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={newSkill}>{t('btn.newSkill')}</Button>
        </Space>
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <Card
          style={{ width: 300, flex: '0 0 300px' }}
          title={<Space><FileMarkdownOutlined />{t('card.existingSkills')}</Space>}
          loading={loading}
        >
          {skills.length === 0 ? (
            <Empty description={t('msg.noSkills')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <List
              dataSource={skills}
              rowKey="protocol"
              renderItem={(item) => (
                <List.Item
                  onClick={() => openSkill(item.protocol)}
                  style={{
                    cursor: 'pointer',
                    background: current === item.protocol ? 'var(--app-accent-subtle)' : undefined,
                    paddingLeft: 8, paddingRight: 8,
                  }}
                  actions={[
                    <Popconfirm
                      key="del"
                      title={t('msg.deleteSkill')}
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
                    {item.has_manual && <Tag>{t('label.hasManual')}</Tag>}
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
                addonBefore={t('col.name')}
                style={{ width: 240 }}
                value={name}
                placeholder={t('label.exampleScpi')}
                onChange={(e) => { setName(e.target.value); setDirty(true) }}
              />
              <Input
                addonBefore={t('label.protocolId')}
                style={{ width: 240 }}
                value={protocol}
                placeholder={t('label.exampleScpiId')}
                onChange={(e) => { setProtocol(e.target.value); setDirty(true) }}
              />
              <Input
                addonBefore={t('label.keyword')}
                style={{ width: 320 }}
                value={keywords}
                placeholder={t('label.commaSeparated')}
                onChange={(e) => { setKeywords(e.target.value); setDirty(true) }}
              />
            </Space>

            <TextArea
              value={content}
              onChange={(e) => { setContent(e.target.value); setDirty(true) }}
              placeholder={t('skill.bodyFull')}
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
              >{t('common.save')}</Button>
              <Tooltip title={t('tip.copyBody')}>
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => {
                    navigator.clipboard.writeText(content)
                    message.success(t('msg.copied'))
                  }}
                >{t('common.copy')}</Button>
              </Tooltip>
                  {dirty && <Tag color="orange">{t('label.unsaved')}</Tag>}
              {!dirty && current && <Tag color="green">{t('msg.synced')}</Tag>}
            </Space>

            <Divider style={{ margin: '4px 0' }} />
            <Text type="secondary" style={{ fontSize: 12 }}>{t('label.writtenOnSave')}<code>plugins/skills/{'{protocol}'}_skill.md</code>；
              frontmatter（name / protocol / keywords）{t('label.autoFromFields')}
              {t('skill.renameWarning')}
            </Text>
          </Space>
        </Card>
      </div>

      <Modal
        title={t('dlg.importSkill')}
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={handleImport}
        width={720}
        okText={t('common.import')}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Upload
            accept=".md,.markdown,.txt"
            beforeUpload={async (file) => {
              try {
                const text = await readFileAsText(file as File)
                setImportName(file.name)
                setImportText(text)
      message.success(`${t('msg.loaded')} ${file.name}`)
              } catch {
                message.error(t('msg.readFileFailed'))
              }
              return false
            }}
            showUploadList={false}
          >
            <Button icon={<ImportOutlined />}>{t('btn.pickMarkdown')}</Button>
          </Upload>
          <Text type="secondary" style={{ fontSize: 12 }}>{t('skill.pasteHint')}<code>foo_skill.md</code> → <code>foo</code>），{t('label.overwriteExisting')}
          </Text>
          <TextArea
            rows={14}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={t('skill.paste')}
            style={{ fontFamily: 'Consolas, Monaco, monospace', fontSize: 13 }}
          />
        </Space>
      </Modal>
    </div>
  )
}
