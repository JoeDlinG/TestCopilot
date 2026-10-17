import { useEffect, useRef, useState } from 'react'
import {
  Card, Table, Button, Space, Modal, Form, Input, Checkbox, Radio,
  Tag, Typography, message, Popconfirm, Alert, Upload, Divider, Empty,
  Steps, Tooltip,
} from 'antd'
import {
  DownloadOutlined, UploadOutlined,   SaveOutlined, EditOutlined,
  DeleteOutlined, SyncOutlined, ImportOutlined, FileTextOutlined,
  ReloadOutlined, FileAddOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import { projectAPI, PROJECT_SECTIONS } from '../services/api'
import { extractData, handleApiError, _errorMessage } from '../services/apiHelper'
import { useI18n } from '../i18n'

const { Title, Text, Paragraph } = Typography

const ALL_SECTIONS = PROJECT_SECTIONS.map((s) => s.key)

interface ProjectRow {
  name: string
  file_name: string
  size: number
  counts: Record<string, number>
  app_version?: string
  exported_at?: string
  updated_at?: string
  error?: string | null
}

export default function ProjectManager() {
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [loading, setLoading] = useState(false)
  const [sections, setSections] = useState<string[]>(ALL_SECTIONS)
  const [mode, setMode] = useState<'merge' | 'replace'>('merge')

  const [saveOpen, setSaveOpen] = useState(false)
  const [renameOpen, setRenameOpen] = useState(false)
  const [newOpen, setNewOpen] = useState(false)
  const [keepModels, setKeepModels] = useState(true)
  const [newResult, setNewResult] = useState<any>(null)
  // ---- 项目向导 ----
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState(0)
  const [wizardName, setWizardName] = useState('')
  const [wizardSections, setWizardSections] = useState<string[]>(
    PROJECT_SECTIONS.map((s) => s.key),
  )
  const [importResult, setImportResult] = useState<any>(null)
  const [busy, setBusy] = useState<string>('')

  const [saveForm] = Form.useForm()
  const [renameForm] = Form.useForm()
  const renamingRef = useRef<string>('')
  const { t } = useI18n()

  const load = async () => {
    setLoading(true)
    try {
      const res = await projectAPI.list()
      setProjects(extractData(res, []))
    } catch (err) {
      handleApiError(err, '加载工程列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const sectionArg = () => (sections.length === ALL_SECTIONS.length ? undefined : sections)

  /** Trigger a browser download for a JSON payload. */
  const download = (filename: string, data: any) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // ---- 导出：把当前系统配置下载成文件 ----
  const handleExport = async () => {
    setBusy('export')
    try {
      const res = await projectAPI.exportBundle({ sections: sectionArg() })
      const bundle: any = extractData(res, null) || {}
      download(`Project_${bundle.project_name || 'export'}.json`, bundle)
      message.success('已导出当前配置')
    } catch (err) {
      handleApiError(err, '导出失败')
    } finally {
      setBusy('')
    }
  }

  // ---- 另存为：导出并同时存一份到服务端 ----
  const handleSaveAs = async () => {
    let name = ''
    try {
      const values = await saveForm.validateFields()
      name = (values.name || '').trim()
    } catch {
      return
    }
    setBusy('save')
    try {
      await projectAPI.save(name, sectionArg())
      message.success(`已保存为工程「${name}」`)
      setSaveOpen(false)
      saveForm.resetFields()
      load()
    } catch (err) {
      handleApiError(err, '另存为失败')
    } finally {
      setBusy('')
    }
  }

  // ---- 导入：把 bundle 写回系统 ----
  const applyBundle = async (bundle: any, from: string) => {
    setBusy('import')
    setImportResult(null)
    try {
      const res = await projectAPI.importBundle(bundle, sectionArg(), mode)
      const data: any = res.data?.data || res.data
      setImportResult({ ...data, from })
      message.success(`已从「${from}」导入配置`)
      load()
    } catch (err) {
      const detail = _errorMessage(err, '导入失败')
      message.error(detail, 6)
      setImportResult({ error: detail, from })
    } finally {
      setBusy('')
    }
  }

  const handleUpload = (file: File) => {
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const bundle = JSON.parse(String(reader.result))
        applyBundle(bundle, file.name)
      } catch {
        message.error('文件不是合法的 JSON')
      }
    }
    reader.onerror = () => message.error('文件读取失败')
    reader.readAsText(file)
    return false // prevent antd from uploading it
  }

  const handleImportSaved = async (row: ProjectRow) => {
    try {
      const res = await projectAPI.get(row.name)
      applyBundle(extractData(res, null), row.name)
    } catch (err) {
      handleApiError(err, '读取工程文件失败')
    }
  }

  const handleDownloadSaved = async (row: ProjectRow) => {
    try {
      const res = await projectAPI.get(row.name)
      download(row.file_name, extractData(res, null))
    } catch (err) {
      handleApiError(err, '下载失败')
    }
  }

  const handleRename = async () => {
    let newName = ''
    try {
      const values = await renameForm.validateFields()
      newName = (values.new_name || '').trim()
    } catch {
      return
    }
    try {
      await projectAPI.rename(renamingRef.current, newName)
      message.success('已重命名')
      setRenameOpen(false)
      renameForm.resetFields()
      load()
    } catch (err) {
      handleApiError(err, '重命名失败')
    }
  }

  // ---- 项目向导：选段 → 命名 → 生成 ----
  const openWizard = () => {
    setWizardStep(0)
    setWizardName('')
    setWizardSections(PROJECT_SECTIONS.map((s) => s.key))
    setWizardOpen(true)
  }

  const handleWizardFinish = async () => {
    const name = wizardName.trim()
    if (!name) {
      message.warning('请输入工程名称')
      return
    }
    setBusy('wizard')
    try {
      await projectAPI.save(name, wizardSections)
      message.success(`工程「${name}」已创建（${wizardSections.length} 个配置段）`)
      setWizardOpen(false)
      load()
    } catch (err) {
      handleApiError(err, '创建工程失败')
    } finally {
      setBusy('')
    }
  }

  // ---- 新建项目工程：清空工作区（默认保留 AI 模型配置）----
  const handleNewProject = async () => {
    setBusy('new')
    setNewResult(null)
    try {
      const res = await projectAPI.newProject(undefined, keepModels)
      const data: any = res.data?.data || res.data
      setNewResult(data)
      message.success(`已清空 ${data.total_cleared} 项配置，可以开始新项目`)
      setNewOpen(false)
      load()
    } catch (err) {
      handleApiError(err, '新建项目失败')
    } finally {
      setBusy('')
    }
  }

  const handleSync = async (row: ProjectRow) => {
    setBusy('sync:' + row.name)
    try {
      await projectAPI.sync(row.name, sectionArg())
      message.success(`已用当前配置覆盖「${row.name}」`)
      load()
    } catch (err) {
      handleApiError(err, '同步失败')
    } finally {
      setBusy('')
    }
  }

  const handleDelete = async (row: ProjectRow) => {
    try {
      await projectAPI.remove(row.name)
      message.success('已删除')
      load()
    } catch (err) {
      handleApiError(err, '删除失败')
    }
  }

  const columns = [
    {
      title: '工程名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, row: ProjectRow) => (
        <Space direction="vertical" size={0}>
          <Space>
            <FileTextOutlined />
            <Text strong>{name}</Text>
            {row.app_version && <Tag color="blue">v{row.app_version}</Tag>}
            {row.error && <Tag color="red">损坏</Tag>}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>{row.file_name}</Text>
        </Space>
      ),
    },
    {
      title: '包含配置',
      key: 'counts',
      render: (_: any, row: ProjectRow) => (
        <Space size={[4, 4]} wrap>
          {PROJECT_SECTIONS.filter((s) => (row.counts?.[s.key] ?? 0) > 0).map((s) => (
            <Tag key={s.key}>{s.label} {row.counts[s.key]}</Tag>
          ))}
          {Object.keys(row.counts || {}).length === 0 && <Text type="secondary">—</Text>}
        </Space>
      ),
    },
    {
      title: '大小 / 更新时间',
      key: 'meta',
      width: 180,
      render: (_: any, row: ProjectRow) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{(row.size / 1024).toFixed(1)} KB</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {row.exported_at ? new Date(row.exported_at).toLocaleString('zh-CN') : '-'}
          </Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 300,
      render: (_: any, row: ProjectRow) => (
        <Space size="small" wrap>
          <Button
            size="small" icon={<ImportOutlined />}
            loading={busy === 'import'}
            disabled={!!row.error}
            onClick={() => handleImportSaved(row)}
          >
            {t('common.import')}
          </Button>
          <Button
            size="small" icon={<DownloadOutlined />}
            disabled={!!row.error}
            onClick={() => handleDownloadSaved(row)}
          >
            {t('common.download')}
          </Button>
          <Button
            size="small" icon={<SyncOutlined />}
            loading={busy === 'sync:' + row.name}
            onClick={() => handleSync(row)}
          >
            {t('common.overwrite')}
          </Button>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => {
              renamingRef.current = row.name
              renameForm.setFieldsValue({ new_name: row.name })
              setRenameOpen(true)
            }}
          >
            {t('common.rename')}
          </Button>
          <Popconfirm title={`删除工程「${row.name}」？`} onConfirm={() => handleDelete(row)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-container">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>{t('project.title')}</Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          {t('common.refresh')}
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="工程文件把插件、Skill、测试用例、执行管理器、设备、仪表盘与模型配置打包成一个 JSON 文件"
        description="AI 模型的 api_key 属于敏感信息，始终不会写入工程文件；导入时也不会覆盖已有的密钥。"
      />

      <Card title={t('common.actions')} style={{ marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Text strong style={{ marginRight: 8 }}>{t('project.sections')}</Text>
            <Checkbox.Group
              options={PROJECT_SECTIONS.map((s) => ({ label: s.label, value: s.key }))}
              value={sections}
              onChange={(v) => setSections(v as string[])}
            />
          </div>
          <Divider style={{ margin: '4px 0' }} />
          <Space wrap>
            <Button
              type="primary" icon={<DownloadOutlined />}
              loading={busy === 'export'}
              onClick={handleExport}
            >
              {t('project.export')}
            </Button>
            <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>
              {t('project.saveAs')}
            </Button>
            <Button danger icon={<FileAddOutlined />} onClick={() => setNewOpen(true)}>
              {t('project.new')}
            </Button>
            <Tooltip title="分步引导：选配置段 → 命名 → 生成工程">
              <Button icon={<ThunderboltOutlined />} onClick={openWizard}>
                项目向导
              </Button>
            </Tooltip>
            <Upload
              beforeUpload={handleUpload}
              showUploadList={false}
              accept=".json,application/json"
            >
              <Button icon={<UploadOutlined />} loading={busy === 'import'}>
                {t('project.importFile')}
              </Button>
            </Upload>
            <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
              <Radio value="merge">{t('project.merge')}</Radio>
              <Radio value="replace">{t('project.replace')}</Radio>
            </Radio.Group>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }}>
            合并导入：按 ID / 名称匹配，已存在则更新、不存在则新建（重复导入不会产生重复数据）。
            替换导入：先清空该配置段再写入，会删除该段现有数据。
          </Text>
        </Space>
      </Card>

      {importResult && (
        <Card title={t('project.importResult')} size="small" style={{ marginBottom: 16 }}>
          {importResult.error ? (
            <Alert type="error" showIcon message={importResult.error} />
          ) : (
            <Space direction="vertical" size={4}>
              <Text>来源：{importResult.from}　模式：{importResult.mode}</Text>
              <Space size={[6, 6]} wrap>
                {Object.entries(importResult.sections || {}).map(([key, v]: any) => (
                  <Tag
                    key={key}
                    color={v.created > 0 ? 'green' : 'blue'}
                  >
                    {PROJECT_SECTIONS.find((s) => s.key === key)?.label || key}
                    ：新建 {v.created} / 更新 {v.updated}
                    {v.skipped > 0 && ` / 跳过 ${v.skipped}`}
                  </Tag>
                ))}
              </Space>
            </Space>
          )}
        </Card>
      )}

      {newResult && (
        <Card title={t('project.newResult')} size="small" style={{ marginBottom: 16 }}>
          <Space direction="vertical" size={4}>
            <Text>{t('project.clearedTotal', { n: newResult.total_cleared })}</Text>
            <Space size={[6, 6]} wrap>
              {Object.entries(newResult.cleared || {}).map(([key, n]: any) => (
                <Tag key={key} color="red">
                  {PROJECT_SECTIONS.find((s) => s.key === key)?.label || key}：{n}
                </Tag>
              ))}
            </Space>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('project.kept')}{(newResult.kept || [])
                .map((k: string) => PROJECT_SECTIONS.find((s) => s.key === k)?.label || k)
                .join('、') || '无'}
            </Text>
          </Space>
        </Card>
      )}

      <Card title={t('project.saved')}>
        <Table
          rowKey="name"
          loading={loading}
          dataSource={projects}
          columns={columns}
          pagination={false}
          locale={{
            emptyText: (
              <Empty description="还没有保存的工程文件，点击「另存为工程」创建">
                <Button type="primary" onClick={() => setSaveOpen(true)}>另存为工程</Button>
              </Empty>
            ),
          }}
        />
      </Card>

      <Modal
        title={t('project.saveAs')}
        open={saveOpen}
        onOk={handleSaveAs}
        confirmLoading={busy === 'save'}
        onCancel={() => setSaveOpen(false)}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
      >
        <Form form={saveForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="工程名称"
            rules={[{ required: true, message: '请输入工程名称' }]}
            extra={`将保存为 Project_名称.json（当前包含 ${sections.length} 个配置段）`}
          >
            <Input placeholder="例如：CAN 联调测试" autoFocus />
          </Form.Item>
        </Form>
      </Modal>

      {/* 项目向导：选段 → 命名 → 生成 */}
      <Modal
        title="项目向导"
        open={wizardOpen}
        onCancel={() => setWizardOpen(false)}
        width={620}
        footer={[
          <Button key="back" disabled={wizardStep === 0}
            onClick={() => setWizardStep((s) => s - 1)}>
            上一步
          </Button>,
          wizardStep < 2 ? (
            <Button key="next" type="primary" onClick={() => setWizardStep((s) => s + 1)}>
              下一步
            </Button>
          ) : (
            <Button key="done" type="primary" loading={busy === 'wizard'}
              onClick={handleWizardFinish}>
              生成工程
            </Button>
          ),
        ]}
      >
        <Steps
          size="small" current={wizardStep} style={{ marginBottom: 20 }}
          items={[{ title: '选择配置段' }, { title: '命名工程' }, { title: '确认生成' }]}
        />

        {wizardStep === 0 && (
          <div>
            <Text type="secondary">勾选要打包进工程的配置段：</Text>
            <div style={{ marginTop: 10 }}>
              <Checkbox.Group
                options={PROJECT_SECTIONS.map((s) => ({ label: s.label, value: s.key }))}
                value={wizardSections}
                onChange={(v) => setWizardSections(v as string[])}
              />
            </div>
          </div>
        )}

        {wizardStep === 1 && (
          <div>
            <Text type="secondary">给工程起一个名字（将保存为 Project_&lt;名称&gt;.json）：</Text>
            <Input
              style={{ marginTop: 10 }}
              value={wizardName}
              onChange={(e) => setWizardName(e.target.value)}
              placeholder="例如：CAN联调基线"
              onPressEnter={() => setWizardStep(2)}
            />
          </div>
        )}

        {wizardStep === 2 && (
          <div>
            <Text strong>即将创建：</Text>
            <div style={{ marginTop: 8 }}>
              <div>工程文件：<Text code>Project_{wizardName.trim() || '（未命名）'}.json</Text></div>
              <div style={{ marginTop: 6 }}>
                包含配置段：
                {wizardSections.length === 0
                  ? <Text type="danger"> 未选择任何配置段</Text>
                  : wizardSections.map((k) => (
                      <Tag key={k} color="blue">
                        {PROJECT_SECTIONS.find((s) => s.key === k)?.label || k}
                      </Tag>
                    ))}
              </div>
            </div>
            <Alert
              type="info" showIcon style={{ marginTop: 12 }}
              message="创建工程不会影响当前系统配置"
              description="向导只是把当前配置保存成一份工程文件；如需清空工作区重新开始，请使用「新建项目工程」。"
            />
          </div>
        )}
      </Modal>

      <Modal
        title={t('project.newTitle')}
        open={newOpen}
        onOk={handleNewProject}
        confirmLoading={busy === 'new'}
        onCancel={() => setNewOpen(false)}
        okText={t('common.confirm')}
        okButtonProps={{ danger: true }}
        cancelText={t('common.cancel')}
        width={560}
      >
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
          message="此操作会清空当前工作区的配置，且无法撤销"
          description="执行历史与通信日志不会被删除，但设备、插件、Skill、测试用例（含流程图）、执行计划、仪表盘会被全部移除。"
        />
        <Checkbox
          checked={keepModels}
          onChange={(e) => setKeepModels(e.target.checked)}
        >
          保留 AI 模型配置（推荐）
        </Checkbox>
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            AI 模型的接口地址与 API Key 属于环境配置而非项目数据，
            取消勾选后需要重新填写才能继续使用 AI 功能。
          </Text>
        </div>
        <div style={{ marginTop: 12 }}>
          <Text strong>将被清空：</Text>
          <div style={{ marginTop: 6 }}>
            {PROJECT_SECTIONS.filter((s) => s.key !== 'models').map((s) => (
              <Tag key={s.key} color="red">{s.label}</Tag>
            ))}
            {!keepModels && <Tag color="red">模型配置</Tag>}
          </div>
        </div>
      </Modal>

      <Modal
        title={t('common.rename')}
        open={renameOpen}
        onOk={handleRename}
        onCancel={() => setRenameOpen(false)}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
      >
        <Form form={renameForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="new_name"
            label="新名称"
            rules={[{ required: true, message: '请输入新名称' }]}
          >
            <Input autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
