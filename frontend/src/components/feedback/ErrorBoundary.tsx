/**
 * Render-crash boundary (issue #26, sub-task F6).
 *
 * It wraps only the routed page, not the shell, so a crashing page still leaves
 * the sidebar and the help menu reachable — the user can navigate away or file
 * a report instead of staring at a blank screen.
 */
import { Component, ErrorInfo, ReactNode } from 'react'
import { Button, Result, Space, Typography } from 'antd'
import { BugOutlined } from '@ant-design/icons'

import { reportRenderError } from './crashReporter'
import { useI18n } from '../../i18n'

const { Paragraph, Text } = Typography

interface Props {
  children: ReactNode
  /** Where in the app we are — attached to the report. */
  route: string
  onOpenFeedback?: () => void
}

interface State {
  error: Error | null
}

/** i18n is a hook, and class components can't call hooks — so read it here. */
function FallbackText({ msgKey }: { msgKey: string }) {
  const { t } = useI18n()
  return <>{t(msgKey)}</>
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportRenderError(error, info.componentStack || '', this.props.route)
  }

  private reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <div style={{ padding: 32, overflow: 'auto' }}>
        <Result
          status="error"
          icon={<BugOutlined />}
          title={<FallbackText msgKey="fb.title" />}
          subTitle={<FallbackText msgKey="fb.renderFailed" />}
          extra={
            <Space>
              <Button type="primary" onClick={this.reset}>
                <FallbackText msgKey="common.retry" />
              </Button>
              {this.props.onOpenFeedback && (
                <Button icon={<BugOutlined />} onClick={this.props.onOpenFeedback}>
                  <FallbackText msgKey="help.feedback" />
                </Button>
              )}
            </Space>
          }
        >
          <Paragraph>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {error.name}: {error.message}
            </Text>
          </Paragraph>
        </Result>
      </div>
    )
  }
}
