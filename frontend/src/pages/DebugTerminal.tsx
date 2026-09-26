import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Button, Input, Tag, Space, Tooltip, Card, Typography, Empty, Spin
} from 'antd'
import {
  SendOutlined, ClearOutlined, PlayCircleOutlined,
  PauseCircleOutlined, ApiOutlined, ReloadOutlined,
  CloseOutlined
} from '@ant-design/icons'
import { deviceAPI, logAPI } from '../services/api'
import { extractItems } from '../services/apiHelper'
import type { Device } from '../types'
import { useTerminalStore, nextMsgId } from '../stores/terminalStore'
import type { TerminalMessage } from '../stores/terminalStore'

const { Title, Text } = Typography

function formatTime() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  const ms = String(now.getMilliseconds()).padStart(3, '0')
  return `${h}:${m}:${s}.${ms}`
}

// Render message content (CAN frames arrive as objects -> stringify them)
function formatContent(content: any): string {
  if (content === null || content === undefined) return ''
  if (typeof content === 'object') {
    try {
      return JSON.stringify(content)
    } catch {
      return String(content)
    }
  }
  return String(content)
}

function formatTimestamp(isoStr?: string): string {
  // Parse server timestamp (ISO 8601) to local time with ms
  if (!isoStr) return formatTime()
  try {
    const d = new Date(isoStr)
    if (isNaN(d.getTime())) return formatTime()
    const h = String(d.getHours()).padStart(2, '0')
    const m = String(d.getMinutes()).padStart(2, '0')
    const s = String(d.getSeconds()).padStart(2, '0')
    const ms = String(d.getMilliseconds()).padStart(3, '0')
    return `${h}:${m}:${s}.${ms}`
  } catch {
    return formatTime()
  }
}

// Module-level WebSocket factory. Uses the global store directly so that
// message handling keeps working even after the React component unmounts
// (e.g. when navigating to another page and back).
function createWebSocket(deviceId: string): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.hostname || 'localhost'
  const wsUrl = `${protocol}//${host}:8000/ws/devices/${deviceId}`

  const ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    useTerminalStore.getState().setReconnectAttempts(deviceId, 0)
    useTerminalStore.getState().addMessage(deviceId, {
      id: nextMsgId(),
      timestamp: formatTime(),
      type: 'system',
      content: 'WebSocket 已连接',
    })
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      const ts = formatTimestamp(msg.timestamp)
      const store = useTerminalStore.getState()
      switch (msg.type) {
        case 'connected':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'system',
            content: msg.message || '已连接到设备',
          })
          break
        case 'command_sent':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'sent',
            content: formatContent(msg.command),
          })
          break
        case 'command_response':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'sent',
            content: formatContent(msg.command),
          })
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'received',
            content: `${formatContent(msg.response)}  (${msg.duration_ms}ms)`,
          })
          break
        case 'command_error':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'sent',
            content: msg.command,
          })
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'error',
            content: `Error: ${msg.error}`,
          })
          break
        case 'device_data':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'data',
            content: formatContent(msg.data),
          })
          break
        case 'receive_started':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'system',
            content: `开始监听设备数据 (间隔: ${msg.interval_ms}ms)`,
          })
          store.setListening(deviceId, true)
          break
        case 'receive_stopped':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'system',
            content: '已停止监听',
          })
          store.setListening(deviceId, false)
          break
        case 'receive_error':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'error',
            content: `接收错误: ${msg.error}`,
          })
          break
        case 'device_disconnected':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'error',
            content: `设备已断开: ${msg.message}`,
          })
          store.setListening(deviceId, false)
          break
        case 'pong':
          break
        case 'error':
          store.addMessage(deviceId, {
            id: nextMsgId(),
            timestamp: ts,
            type: 'error',
            content: msg.message,
          })
          break
      }
    } catch {
      // ignore parse errors
    }
  }

  ws.onclose = () => {
    const store = useTerminalStore.getState()
    const tab = store.tabs[deviceId]
    const attempts = (tab?.reconnectAttempts || 0) + 1
    store.setReconnectAttempts(deviceId, attempts)
    store.setListening(deviceId, false)
    store.addMessage(deviceId, {
      id: nextMsgId(),
      timestamp: formatTime(),
      type: 'system',
      content: 'WebSocket 已断开，将在 3s 后重连...',
    })

    // Reconnect with exponential backoff
    const delay = Math.min(1000 * Math.pow(2, Math.min(attempts, 5)), 30000)
    setTimeout(() => {
      const newWs = createWebSocket(deviceId)
      useTerminalStore.getState().setWs(deviceId, newWs)
    }, delay)
  }

  ws.onerror = () => {
    // onclose will fire after this
  }

  return ws
}

// Single terminal window (one device). Extracted so it can use hooks
// independently of the parent's render cycle.
function TerminalWindow({ deviceId }: { deviceId: string }) {
  const tab = useTerminalStore((s) => s.tabs[deviceId])
  const commandInput = useTerminalStore((s) => s.commandInputs[deviceId] || '')
  const setCommandInput = useTerminalStore((s) => s.setCommandInput)
  const setCommandHistory = useTerminalStore((s) => s.addCommandHistory)
  const setHistoryIndex = useTerminalStore((s) => s.setHistoryIndex)
  const historyIndexes = useTerminalStore((s) => s.historyIndexes)
  const commandHistories = useTerminalStore((s) => s.commandHistories)
  const clearMessages = useTerminalStore((s) => s.clearMessages)

  const logRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [tab?.messages.length])

  if (!tab) return null

  const sendCommand = () => {
    const command = commandInput.trim()
    if (!command) return

    const ws = tab.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      useTerminalStore.getState().addMessage(deviceId, {
        id: nextMsgId(),
        timestamp: formatTime(),
        type: 'error',
        content: 'WebSocket 未连接，无法发送命令',
      })
      return
    }

    ws.send(JSON.stringify({ type: 'command', command }))
    setCommandHistory(deviceId, command)
    setHistoryIndex(deviceId, (historyIndexes[deviceId] || 0) + 1)
    setCommandInput(deviceId, '')
  }

  const toggleListening = () => {
    const ws = tab.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    if (tab.listening) {
      ws.send(JSON.stringify({ type: 'stop_receive' }))
    } else {
      ws.send(JSON.stringify({ type: 'start_receive', interval_ms: 200 }))
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendCommand()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const history = commandHistories[deviceId] || []
      if (history.length === 0) return
      const currentIdx = historyIndexes[deviceId] ?? history.length
      const newIdx = Math.max(0, currentIdx - 1)
      setCommandInput(deviceId, history[newIdx] || '')
      setHistoryIndex(deviceId, newIdx)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const history = commandHistories[deviceId] || []
      const currentIdx = historyIndexes[deviceId] ?? history.length
      const newIdx = Math.min(history.length, currentIdx + 1)
      setCommandInput(deviceId, newIdx < history.length ? history[newIdx] : '')
      setHistoryIndex(deviceId, newIdx)
    }
  }

  const getMessageColor = (type: string) => {
    switch (type) {
      case 'sent': return '#569cd6'
      case 'received': return '#6a9955'
      case 'data': return '#ce9178'
      case 'error': return '#f44747'
      case 'system': return '#808080'
      default: return '#d4d4d4'
    }
  }

  const getMessagePrefix = (type: string) => {
    switch (type) {
      case 'sent': return '>> '
      case 'received': return '<< '
      case 'data': return '<< [RX] '
      case 'error': return '!! '
      case 'system': return '-- '
      default: return ''
    }
  }

  const isOpen = tab.ws && tab.ws.readyState === WebSocket.OPEN

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 12px',
        borderBottom: '1px solid #333',
        background: '#252526',
      }}>
        <Space>
          <Text style={{ color: '#ccc', fontSize: 13 }}>
            {tab.deviceName}
          </Text>
          <Tag color={isOpen ? 'green' : 'red'}>
            {isOpen ? '已连接' : '未连接'}
          </Tag>
        </Space>
        <Space>
          <Tooltip title={tab.listening ? '停止监听' : '开始监听实时数据'}>
            <Button
              size="small"
              type={tab.listening ? 'primary' : 'default'}
              danger={tab.listening}
              icon={tab.listening ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              onClick={toggleListening}
              disabled={!isOpen}
            >
              {tab.listening ? '停止监听' : '开始监听'}
            </Button>
          </Tooltip>
          <Tooltip title="清空日志">
            <Button
              size="small"
              icon={<ClearOutlined />}
              onClick={() => clearMessages(deviceId)}
            />
          </Tooltip>
        </Space>
      </div>

      {/* Message log */}
      <div
        ref={logRef}
        style={{
          flex: 1,
          overflow: 'auto',
          background: '#1e1e1e',
          padding: '12px',
          fontFamily: 'Consolas, Monaco, "Courier New", monospace',
          fontSize: 13,
          lineHeight: 1.6,
          minHeight: 0,
        }}
      >
        {tab.messages.length === 0 ? (
          <div style={{
            color: '#666',
            textAlign: 'center',
            paddingTop: 40,
          }}>
            等待设备数据... 在下方输入框发送命令
          </div>
        ) : (
          tab.messages.map(msg => (
            <div key={msg.id} style={{ marginBottom: 2 }}>
              <span style={{ color: '#666', fontSize: 11, marginRight: 8 }}>
                {msg.timestamp}
              </span>
              <span style={{ color: getMessageColor(msg.type) }}>
                {getMessagePrefix(msg.type)}{msg.content}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Command input */}
      <div style={{
        display: 'flex',
        gap: 8,
        padding: '8px 12px',
        borderTop: '1px solid #333',
        background: '#252526',
      }}>
        <Input
          value={commandInput}
          onChange={(e) => setCommandInput(deviceId, e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入命令，Enter 发送，Shift+Enter 换行，↑↓ 历史命令..."
          style={{
            background: '#3c3c3c',
            border: '1px solid #555',
            color: '#d4d4d4',
            fontFamily: 'Consolas, Monaco, monospace',
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={sendCommand}
          disabled={!isOpen}
        >
          发送
        </Button>
      </div>
    </div>
  )
}

export default function DebugTerminal() {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(false)

  const tabs = useTerminalStore((s) => s.tabs)
  const activeTabId = useTerminalStore((s) => s.activeTabId)
  const openTerminalAction = useTerminalStore((s) => s.openTerminal)
  const closeTerminalAction = useTerminalStore((s) => s.closeTerminal)
  const setActiveTab = useTerminalStore((s) => s.setActiveTab)

  const connectedDevices = devices.filter(
    (d: any) => d.status === 'connected'
  )

  const loadDevices = useCallback(async () => {
    setLoading(true)
    try {
      const res = await deviceAPI.list()
      const list = extractItems(res)
      setDevices(list)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDevices()
    const interval = setInterval(loadDevices, 5000)
    return () => clearInterval(interval)
  }, [loadDevices])

  // Load recent communication history from the DB once per opened device tab,
  // so the terminal shows past traffic even before new frames arrive.
  const historyLoadedRef = useRef<Set<string>>(new Set())
  const loadHistory = useCallback(async (did: string) => {
    try {
      const res = await logAPI.list({ device_id: did, limit: 100 })
      const items: any[] = extractItems(res)
      const msgs: TerminalMessage[] = items
        .filter((it) => it.direction === 'sent' || it.direction === 'received')
        .sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)))
        .map((it) => ({
          id: nextMsgId(),
          timestamp: formatTimestamp(it.timestamp) || '',
          type: it.direction === 'sent' ? 'sent' : 'received',
          content: it.direction === 'sent'
            ? formatContent(it.raw_data)
            : `${formatContent(it.raw_data)}${it.duration_ms != null ? `  (${it.duration_ms}ms)` : ''}`,
        }))
      if (msgs.length > 0) {
        useTerminalStore.setState((state) => {
          const tab = state.tabs[did]
          if (!tab) return {}
          return {
            tabs: {
              ...state.tabs,
              [did]: { ...tab, messages: [...msgs, ...tab.messages] },
            },
          }
        })
      }
    } catch {
      // ignore history load errors
    }
  }, [])

  useEffect(() => {
    Object.values(tabs).forEach((tab) => {
      if (historyLoadedRef.current.has(tab.deviceId)) return
      historyLoadedRef.current.add(tab.deviceId)
      loadHistory(tab.deviceId)
    })
  }, [tabs, loadHistory])

  // On mount, re-establish any WebSocket connections that were kept in the
  // global store while navigating away (e.g. the component was unmounted).
  // This keeps messages flowing and preserves history across page switches.
  useEffect(() => {
    const store = useTerminalStore.getState()
    Object.values(store.tabs).forEach((tab) => {
      if (!tab.ws || tab.ws.readyState === WebSocket.CLOSED) {
        const ws = createWebSocket(tab.deviceId)
        store.setWs(tab.deviceId, ws)
      }
    })
  }, [])

  const openTerminal = (device: Device) => {
    const deviceId = device.id
    const store = useTerminalStore.getState()
    if (store.tabs[deviceId]) {
      store.setActiveTab(deviceId)
      return
    }
    const ws = createWebSocket(deviceId)
    openTerminalAction(deviceId, device.name, ws)
  }

  const closeTerminal = (deviceId: string) => {
    const store = useTerminalStore.getState()
    const ws = store.tabs[deviceId]?.ws
    if (ws) {
      ws.onclose = null // prevent reconnect
      ws.close()
    }
    closeTerminalAction(deviceId)
  }

  // Render tab bar
  const renderTabBar = () => {
    const tabEntries = Object.entries(tabs)
    if (tabEntries.length === 0) return null

    return (
      <div style={{
        display: 'flex',
        background: '#2d2d2d',
        borderBottom: '1px solid #333',
        overflow: 'auto',
      }}>
        {tabEntries.map(([deviceId, tab]) => (
          <div
            key={deviceId}
            onClick={() => setActiveTab(deviceId)}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '8px 12px',
              cursor: 'pointer',
              borderRight: '1px solid #333',
              background: activeTabId === deviceId ? '#1e1e1e' : '#2d2d2d',
              color: activeTabId === deviceId ? '#fff' : '#999',
              whiteSpace: 'nowrap',
              fontSize: 13,
              minWidth: 0,
            }}
          >
            <ApiOutlined style={{ marginRight: 6, fontSize: 12 }} />
            <span style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {tab.deviceName}
            </span>
            <CloseOutlined
              style={{ marginLeft: 8, fontSize: 10, opacity: 0.6 }}
              onClick={(e) => {
                e.stopPropagation()
                closeTerminal(deviceId)
              }}
            />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)', overflow: 'hidden' }}>
      {/* Left sidebar - Device list */}
      <div style={{
        width: 250,
        minWidth: 250,
        borderRight: '1px solid #e8e8e8',
        background: '#fafafa',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '12px 16px',
          borderBottom: '1px solid #e8e8e8',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <Title level={5} style={{ margin: 0 }}>已连接设备</Title>
          <Button size="small" icon={<ReloadOutlined />} onClick={loadDevices} />
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 8 }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Spin />
            </div>
          ) : connectedDevices.length === 0 ? (
            <Card size="small" style={{ margin: 8, textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 13 }}>
                没有已连接的设备
              </Text>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  请先在设备管理页面连接设备
                </Text>
              </div>
            </Card>
          ) : (
            connectedDevices.map(device => {
              const isActive = activeTabId === device.id
              return (
                <div
                  key={device.id}
                  onClick={() => openTerminal(device)}
                  style={{
                    padding: '10px 12px',
                    margin: '4px 0',
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: isActive ? '#e6f4ff' : '#fff',
                    border: isActive ? '1px solid #1677ff' : '1px solid #e8e8e8',
                    transition: 'all 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Space>
                      <ApiOutlined style={{ color: isActive ? '#1677ff' : '#999' }} />
                      <Text
                        strong={isActive}
                        style={{
                          fontSize: 13,
                          maxWidth: 150,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {device.name}
                      </Text>
                    </Space>
                    <Tag color="green" style={{ fontSize: 11, margin: 0 }}>已连接</Tag>
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {(device as any).protocol?.toUpperCase() || 'UNKNOWN'}
                      {' · '}
                      {(device as any).serial_port || (device as any).visa_address || 'USB'}
                    </Text>
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Right area - Terminal windows */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {Object.keys(tabs).length === 0 ? (
          <div style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#f5f5f5',
          }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <span style={{ color: '#999' }}>
                  选择一个已连接的设备打开调试终端<br />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    支持同时打开多个设备的终端窗口
                  </Text>
                </span>
              }
            />
          </div>
        ) : (
          <>
            {renderTabBar()}
            <div style={{ flex: 1, overflow: 'hidden' }}>
              {activeTabId && tabs[activeTabId] ? (
                <TerminalWindow deviceId={activeTabId} />
              ) : (
                <div style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: '#1e1e1e',
                  color: '#666',
                }}>
                  选择一个终端窗口
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
