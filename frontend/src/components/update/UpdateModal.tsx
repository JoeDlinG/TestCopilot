/**
 * Update dialog (issue #25).
 *
 * Consent is the hard rule, so the flow has **two** explicit confirmations:
 *
 *   1. 立即更新   -> download + verify (progress bar)
 *   2. 立即安装并重启 -> actually swap files and restart
 *
 * Nothing is downloaded before step 1 and nothing is installed before step 2,
 * which keeps "自动下载" harmless: it may have bytes on disk, but the app is
 * only ever replaced after a deliberate click.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Modal, Progress, Space, Spin, Switch, Tag, Typography, message,
} from 'antd'
import { CheckCircleOutlined, SyncOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'

import { updateAPI } from '../../services/api'
import { useI18n } from '../../i18n'

const { Text, Paragraph } = Typography

interface CheckResult {
  current: string
  latest?: string
  available: boolean
  reason?: string | null
  error?: string
  notes?: string
  ignored?: boolean
  feed?: string
  asset?: { name?: string; kind?: string; size?: number } | null
  mandatory?: boolean
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function UpdateModal({ open, onClose }: Props) {
  const { t } = useI18n()

  const [checking, setChecking] = useState(false)
  const [info, setInfo] = useState<CheckResult | null>(null)
  const [phase, setPhase] = useState<'idle' | 'downloading' | 'verifying' | 'ready' | 'applying' | 'error' | 'done'>('idle')
  const [received, setReceived] = useState(0)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState('')
  const [token, setToken] = useState('')
  const [autoCheck, setAutoCheck] = useState(true)
  const pollRef = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const runCheck = useCallback(async () => {
    setChecking(true)
    setError('')
    try {
      const res = await updateAPI.check()
      setInfo(res.data?.data || null)
    } catch (e) {
      setError(t('update.checkFailed'))
    } finally {
      setChecking(false)
    }
  }, [t])

  useEffect(() => {
    if (!open) return
    setPhase('idle')
    setInfo(null)
    setReceived(0)
    setTotal(0)
    setToken('')
    runCheck()
    updateAPI.getSettings()
      .then((r) => setAutoCheck(r.data?.data?.auto_check !== false))
      .catch(() => {})
    return stopPolling
  }, [open, runCheck])

  const pollStatus = useCallback(() => {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const st = (await updateAPI.status()).data?.data || {}
        setReceived(st.received || 0)
        setTotal(st.total || 0)
        if (st.status === 'downloading') setPhase('downloading')
        else if (st.status === 'verifying') setPhase('verifying')
        else if (st.status === 'ready') {
          stopPolling()
          setToken(st.token || '')
          setPhase('ready')
        } else if (st.status === 'error') {
          stopPolling()
          setError(t('update.checksumFailed'))
          setPhase('error')
        }
      } catch { /* transient */ }
    }, 800)
  }, [t])

  const startDownload = async () => {
    setError('')
    try {
      await updateAPI.download()
      setPhase('downloading')
      pollStatus()
    } catch (e: any) {
      const code = e?.response?.data?.detail?.code
      setError(code === 40033 ? t('update.checksumFailed') : t('update.checkFailed'))
      setPhase('error')
    }
  }

  const applyNow = async () => {
    try {
      setPhase('applying')
      await updateAPI.apply(token)
      message.success(t('update.applying'))
    } catch (e) {
      setError(t('update.applyFailed'))
      setPhase('error')
    }
  }

  const ignoreThisVersion = async () => {
    const version = info?.latest
    if (!version) return
    try {
      await updateAPI.ignore(version)
      message.success(t('update.later'))
    } catch { /* ignore */ }
    onClose()
  }

  const toggleAutoCheck = async (v: boolean) => {
    setAutoCheck(v)
    try { await updateAPI.putSettings({ auto_check: v }) } catch { /* ignore */ }
  }

  const percent = total > 0 ? Math.round((received / total) * 100) : 0

  const body = () => {
    if (checking || (!info && !error)) {
      return <div style={{ textAlign: 'center', padding: '28px 0' }}><Spin /></div>
    }
    if (error) {
      return <Alert type="error" showIcon message={error} />
    }
    if (!info) return null

    if (!info.available) {
      const why = info.reason
      return (
        <div style={{ textAlign: 'center', padding: '14px 0 6px' }}>
          <CheckCircleOutlined style={{ fontSize: 34, color: '#52c41a' }} />
          <Paragraph style={{ marginTop: 10, marginBottom: 0 }}>
            {why === 'no_feed' ? t('update.noFeed') : t('update.upToDate')}
          </Paragraph>
          <Text type="secondary">
            {t('update.current')} {info.current}
          </Text>
          {why === 'wrong_platform' && (
            <div style={{ marginTop: 8 }}><Alert type="warning" showIcon message={t('update.wrongPlatform')} /></div>
          )}
          {info.reason === 'error' && (
            <div style={{ marginTop: 8 }}>
              <Alert type="warning" showIcon message={t('update.checkFailed')} description={info.error} />
            </div>
          )}
        </div>
      )
    }

    return (
      <div>
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          <Space wrap>
            <Tag>{t('update.current')} {info.current}</Tag>
            <Tag color="processing">{t('update.latest')} {info.latest}</Tag>
            {info.asset?.name && <Tag>{info.asset.name}</Tag>}
          </Space>

          {info.notes && (
            <div style={{ maxHeight: 180, overflow: 'auto' }}>
              <Text strong>{t('update.notes')}</Text>
              <div className="md-body"><ReactMarkdown>{info.notes}</ReactMarkdown></div>
            </div>
          )}

          {phase !== 'idle' && (
            <div>
              <Progress
                percent={phase === 'ready' || phase === 'applying' ? 100 : percent}
                status={phase === 'error' ? 'exception' : undefined}
                size="small"
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {phase === 'downloading' && t('update.downloading')}
                {phase === 'verifying' && t('update.verifying')}
                {phase === 'ready' && t('update.now')}
                {phase === 'applying' && t('update.applying')}
              </Text>
            </div>
          )}
        </Space>
      </div>
    )
  }

  const footer = () => {
    if (!info?.available) {
      return <Button type="primary" onClick={onClose}>{t('common.close')}</Button>
    }
    return (
      <Space>
        <Space size={4}>
          <Text type="secondary" style={{ fontSize: 12 }}>{t('update.autoCheck')}</Text>
          <Switch checked={autoCheck} onChange={toggleAutoCheck} size="small" />
        </Space>
        <Button onClick={ignoreThisVersion}>{t('update.ignore')}</Button>
        <Button onClick={onClose}>{t('update.later')}</Button>
        {phase === 'ready' ? (
          <Button type="primary" icon={<SyncOutlined />} onClick={applyNow}>
            {t('update.now')}
          </Button>
        ) : (
          <Button
            type="primary"
            loading={phase === 'downloading' || phase === 'verifying' || phase === 'applying'}
            disabled={phase === 'applying'}
            onClick={startDownload}
          >
            {t('update.now')}
          </Button>
        )}
      </Space>
    )
  }

  return (
    <Modal
      title={t('help.checkUpdate')}
      open={open}
      onCancel={onClose}
      footer={footer()}
      width={620}
      destroyOnClose={false}
    >
      {body()}
    </Modal>
  )
}
