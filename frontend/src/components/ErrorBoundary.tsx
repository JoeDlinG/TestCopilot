import { Component, ErrorInfo, ReactNode } from 'react'
import { Button, Result } from 'antd'
import { useI18n } from '../i18n'

interface CoreProps {
  children: ReactNode
  title: string
  reloadLabel: string
}

interface State {
  error: Error | null
}

/**
 * React render errors used to disappear silently: StrictMode unmounts the tree
 * and the user sees a blank page with no clue in the UI. Show an actionable
 * panel instead and keep the details in the console for support.
 */
class ErrorBoundaryCore extends Component<CoreProps, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] render failed:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <Result
          status="error"
          title={this.props.title}
          subTitle={this.state.error.message}
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              {this.props.reloadLabel}
            </Button>
          }
        />
      )
    }
    return this.props.children
  }
}

/** Error boundaries must be classes; translate their labels in a wrapper. */
export default function ErrorBoundary({ children }: { children: ReactNode }) {
  const { t } = useI18n()
  return (
    <ErrorBoundaryCore title={t('error.renderTitle')} reloadLabel={t('error.reload')}>
      {children}
    </ErrorBoundaryCore>
  )
}
