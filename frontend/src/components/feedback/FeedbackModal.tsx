/**
 * Feedback form (issue #26, sub-tasks F8–F10).
 *
 * Manual feedback is the user's own text, so unlike crash reports it is not
 * anonymised — but credentials are still scrubbed server side before anything
 * is stored or forwarded, and attaching the runtime log is opt-in and visible.
 */
import { useEffect, useState } from 'react'
import {
  Alert, Button, Checkbox, Input, Modal, Radio, Space, Typography, message,
} from 'antd'

import { feedbackAPI } from '../../services/api'
import { useI18n } from '../../i18n'

const { Text, Paragraph } = Typography
const { TextArea } = Input

interface Props {
  open: boolean
  onClose: () => void
  /** Current route — attached automatically so we know where it happened. */
  route: string
}

export default function FeedbackModal({ open, onClose, route }: Props) {
  const { t } = useI18n()

  const [kind, setKind] = useState<'idea' | 'issue' | 'other'>('idea')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [contact, setContact] = useState('')
  const [attachLogs, setAttachLogs] = useState(true)
  const [sending, setSending] = useState(false)
  const [autoReport, setAutoReport] = useState(true)
  const [tokenConfigured, setTokenConfigured] = useState(true)

  useEffect(() => {
    if (!open) return
    setKind('idea'); setSubject(''); setBody(''); setContact('')
    feedbackAPI
      .getSettings()
      .then((r) => {
        const d = r.data?.data || {}
        setAutoReport(d.auto_crash_report !== false)
        setTokenConfigured(!!d.token_configured)
      })
      .catch(() => {})
  }, [open])

  const submit = async () => {
    if (!subject.trim() || !body.trim()) {
      message.warning(t('fb.needFields'))
      return
    }
    setSending(true)
    try {
      const res = await feedbackAPI.submit({
        kind,
        title: subject.trim(),
        body: contact.trim()
          ? `${body.trim()}\n\n${t('fb.contact')}: ${contact.trim()}`
          : body.trim(),
        route,
        consent: true,
        attach_logs: attachLogs,
      })
      const d = res.data?.data || {}
      if (d.status === 'deduped') message.info(t('fb.deduped'))
      else if (!d.token_configured) message.warning(t('fb.noToken'))
      else message.success(t('fb.ok'))
      onClose()
    } catch {
      message.error(t('fb.queued'))
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal
      title={t('fb.title')}
      open={open}
      onCancel={onClose}
      width={640}
      footer={[
        <Button key="cancel" onClick={onClose}>{t('common.close')}</Button>,
        <Button key="ok" type="primary" loading={sending} onClick={submit}>
          {t('fb.submit')}
        </Button>,
      ]}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <div>
          <Text strong>{t('fb.kind')}</Text>
          <div style={{ marginTop: 6 }}>
            <Radio.Group
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: t('fb.idea'), value: 'idea' },
                { label: t('fb.problem'), value: 'issue' },
                { label: t('fb.other'), value: 'other' },
              ]}
            />
          </div>
        </div>

        <div>
          <Text strong>{t('fb.subject')}</Text>
          <Input
            style={{ marginTop: 6 }}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            maxLength={120}
          />
        </div>

        <div>
          <Text strong>{t('fb.body')}</Text>
          <TextArea
            style={{ marginTop: 6 }}
            rows={5}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t('fb.bodyPh')}
          />
        </div>

        <div>
          <Text strong>{t('fb.contact')}</Text>
          <Input
            style={{ marginTop: 6 }}
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="you@example.com"
          />
        </div>

        <Space direction="vertical" size={2}>
          <Checkbox
            checked={attachLogs}
            onChange={(e) => setAttachLogs(e.target.checked)}
          >
            {t('fb.attachLogs')}
          </Checkbox>
          <Checkbox
            checked={autoReport}
            onChange={(e) => {
              setAutoReport(e.target.checked)
              feedbackAPI.putSettings({ auto_crash_report: e.target.checked }).catch(() => {})
            }}
          >
            {t('fb.autoReport')}
          </Checkbox>
        </Space>

        {!autoReport && (
          <Alert type="info" showIcon message={t('fb.autoOff')} />
        )}
        {!tokenConfigured && (
          <Alert type="warning" showIcon message={t('fb.noToken')} />
        )}

        <Paragraph type="secondary" style={{ fontSize: 11, marginBottom: 0 }}>
          {t('fb.attachSys')} · v{import.meta.env?.VITE_APP_VERSION || '—'} · {route}
        </Paragraph>
      </Space>
    </Modal>
  )
}
