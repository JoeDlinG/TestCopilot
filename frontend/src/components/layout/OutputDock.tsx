import { Suspense, lazy, useEffect } from 'react'
import { Badge, Button, Space, Tabs, Tooltip } from 'antd'
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  PlayCircleOutlined,
  FileDoneOutlined,
  PushpinOutlined,
} from '@ant-design/icons'
import { Spin } from 'antd'
import { useOutputDock } from '../../stores/outputDockStore'
import { componentTokens } from '../../theme/tokens'

const ExecutionsPanel = lazy(() => import('../../pages/Executions'))
const ReportsPanel = lazy(() => import('../../pages/Reports'))

const Loading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
    <Spin />
  </div>
)

/**
 * Right-hand "输出 / 交付" dock (issue #20).
 *
 * Three states: collapsed (34 px strip) → expanded (420 px) → fullscreen.
 * Engineers spend most of their time authoring configuration, where a permanent
 * run panel is noise; but the moment they hit 运行 the result must be visible.
 * "collapsed by default + auto-expand on run" is the state machine that serves
 * both ends — pinning covers the "watch while editing" case.
 */
export default function OutputDock() {
  const { state, tab, pinned, runningCount, expand, collapse, setFullscreen, setTab, togglePin } =
    useOutputDock()

  // Esc leaves fullscreen.
  useEffect(() => {
    if (state !== 'fullscreen') return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFullscreen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state, setFullscreen])

  if (state === 'collapsed') {
    return (
      <div
        style={{
          width: componentTokens.outputDockCollapsed,
          flex: `0 0 ${componentTokens.outputDockCollapsed}px`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          paddingTop: 12,
          gap: 12,
          borderLeft: '1px solid var(--app-border, rgba(128,128,128,0.2))',
          cursor: 'pointer',
        }}
        onClick={() => expand()}
        onDoubleClick={(e) => {
          e.stopPropagation()
          expand()
          setFullscreen(true)
        }}
        title="单击展开（420→720px），双击直接全屏"
      >
        <ArrowLeftOutlined style={{ fontSize: 12, opacity: 0.7 }} />
        <Badge
          count={runningCount}
          size="small"
          color={runningCount > 0 ? 'var(--app-running)' : 'transparent'}
          styles={{ indicator: { boxShadow: runningCount > 0 ? '0 0 0 1px var(--app-running)' : undefined } }}
        >
          <PlayCircleOutlined style={{ fontSize: 16, opacity: 0.85 }} />
        </Badge>
        <div
          style={{
            writingMode: 'vertical-rl',
            fontSize: 12,
            letterSpacing: 2,
            opacity: 0.7,
            userSelect: 'none',
          }}
        >
          输出 / 交付
        </div>
      </div>
    )
  }

  const isFull = state === 'fullscreen'

  return (
    <div
      style={{
        width: isFull
          ? '100%'
          : `min(${componentTokens.outputDockWidth}px, ${componentTokens.outputDockMaxVw}vw)`,
        flex: isFull
          ? '1 1 100%'
          : `0 0 min(${componentTokens.outputDockWidth}px, ${componentTokens.outputDockMaxVw}vw)`,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        borderLeft: '1px solid var(--app-border, rgba(128,128,128,0.2))',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 10px',
          borderBottom: '1px solid var(--app-border, rgba(128,128,128,0.15))',
        }}
      >
        <Tabs
          size="small"
          activeKey={tab}
          onChange={(k) => setTab(k as 'executions' | 'reports')}
          items={[
            { key: 'executions', label: <span><PlayCircleOutlined /> 测试执行</span> },
            { key: 'reports', label: <span><FileDoneOutlined /> 输出报告</span> },
          ]}
          style={{ flex: 1, minWidth: 0 }}
        />
        <Space size={2}>
          <Tooltip title={pinned ? '取消钉住' : '钉住（切换菜单时保持展开）'}>
            <Button
              size="small"
              type={pinned ? 'primary' : 'text'}
              icon={<PushpinOutlined />}
              onClick={togglePin}
            />
          </Tooltip>
          <Tooltip title={isFull ? '退出全屏 (Esc)' : '全屏'}>
            <Button
              size="small"
              type="text"
              icon={isFull ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={() => setFullscreen(!isFull)}
            />
          </Tooltip>
          <Tooltip title="收起">
            <Button size="small" type="text" icon={<ArrowRightOutlined />} onClick={collapse} />
          </Tooltip>
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 12 }}>
        <Suspense fallback={<Loading />}>
          {tab === 'executions' ? <ExecutionsPanel /> : <ReportsPanel />}
        </Suspense>
      </div>
    </div>
  )
}
