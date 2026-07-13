import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Button, Input, Tag, Space, Tooltip, Card, Typography, Empty, Spin
} from 'antd'
import {
  SendOutlined, ClearOutlined, PlayCircleOutlined,
  PauseCircleOutlined, ApiOutlined, ReloadOutlined,
  CloseOutlined
} from '@ant-design/icons'
import { deviceAPI } from '../services/api'
import { extractItems } from '../services/apiHelper'
import type { Device } from '../types'

const { Title, Text } = Typography

interface TerminalMessage {
  id: string
  timestamp: string
  type: 'sent' | 'received' | 'data' | 'error' | 'system'
  content: string
}

interface TerminalTab {
  deviceId: string
  deviceName: string
  messages: TerminalMessage[]
  listening: boolean
  ws: WebSocket | null
  reconnectAttempts: number
}

let msgIdCounter = 0
function nextMsgId() {
  return `msg_${++msgIdCounter}_${Date.now()}`
}

function formatTime() {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  const ms = String(now.getMilliseconds()).padStart(3, '0')
  return `${h}:${m}:${s}.${ms}`
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

export default function DebugTerminal() {
  const [devices, setDevices] = useState<Device[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTabKey, setActiveTabKey] = useState<string>('')
  const [tabs, setTabs] = useState<Map<string, TerminalTab>>(new Map())
  const [commandInputs, setCommandInputs] = useState<Record<string, string>>({})
  const [commandHistories, setCommandHistories] = useState<Record<string, string[]>>({})
  const [historyIndexes, setHistoryIndexes] = useState<Record<string, number>>({})
  const logRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const wsRefs = useRef<Record<string, WebSocket | null>>({})

  const connectedDevices = devices.filter(
    (d: any) => d.status === 'connected'
  )

  const loadDevices = async () => {
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
  }

  useEffect(() => {
    loadDevices()
    const interval = setInterval(loadDevices, 5000)
    return () => clearInterval(interval)
  }, [])

  const scrollToBottom = useCallback((deviceId: string) => {
    setTimeout(() => {
      const el = logRefs.current[deviceId]
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    }, 50)
  }, [])

  const addMessage = useCallback((deviceId: string, msg: TerminalMessage) => {
    setTabs(prev => {
      const next = new Map(prev)
      const tab = next.get(deviceId)
      if (tab) {
        next.set(deviceId, {
          ...tab,
          messages: [...tab.messages, msg],
        })
      }
      return next
    })
    scrollToBottom(deviceId)
  }, [scrollToBottom])

  const createWebSocket = useCallback((deviceId: string): WebSocket => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname || 'localhost'
    const wsUrl = `${protocol}//${host}:8000/ws/devices/${deviceId}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setTabs(prev => {
        const next = new Map(prev)
        const tab = next.get(deviceId)
        if (tab) {
          next.set(deviceId, { ...tab, reconnectAttempts: 0 })
        }
        return next
      })
      addMessage(deviceId, {
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
        switch (msg.type) {
          case 'connected':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'system',
              content: msg.message || '已连接到设备',
            })
            break
          case 'command_response':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'sent',
              content: msg.command,
            })
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'received',
              content: `${msg.response}  (${msg.duration_ms}ms)`,
            })
            break
          case 'command_error':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'sent',
              content: msg.command,
            })
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'error',
              content: `Error: ${msg.error}`,
            })
            break
          case 'device_data':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'data',
              content: msg.data,
            })
            break
          case 'receive_started':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'system',
              content: `开始监听设备数据 (间隔: ${msg.interval_ms}ms)`,
            })
            setTabs(prev => {
              const next = new Map(prev)
              const tab = next.get(deviceId)
              if (tab) {
                next.set(deviceId, { ...tab, listening: true })
              }
              return next
            })
            break
          case 'receive_stopped':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'system',
              content: '已停止监听',
            })
            setTabs(prev => {
              const next = new Map(prev)
              const tab = next.get(deviceId)
              if (tab) {
                next.set(deviceId, { ...tab, listening: false })
              }
              return next
            })
            break
          case 'receive_error':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'error',
              content: `接收错误: ${msg.error}`,
            })
            break
          case 'device_disconnected':
            addMessage(deviceId, {
              id: nextMsgId(),
              timestamp: ts,
              type: 'error',
              content: `设备已断开: ${msg.message}`,
            })
            setTabs(prev => {
              const next = new Map(prev)
              const tab = next.get(deviceId)
              if (tab) {
                next.set(deviceId, { ...tab, listening: false })
              }
              return next
            })
            break
          case 'pong':
            break
          case 'error':
            addMessage(deviceId, {
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
      setTabs(prev => {
        const next = new Map(prev)
        const tab = next.get(deviceId)
        if (tab) {
          const attempts = (tab.reconnectAttempts || 0) + 1
          next.set(deviceId, { ...tab, reconnectAttempts: attempts, listening: false })
        }
        return next
      })

      addMessage(deviceId, {
        id: nextMsgId(),
        timestamp: formatTime(),
        type: 'system',
        content: 'WebSocket 已断开，将在 3s 后重连...',
      })

      // Reconnect with exponential backoff
      setTabs(prev => {
        const tab = prev.get(deviceId)
        if (tab) {
          const attempts = tab.reconnectAttempts
          const delay = Math.min(1000 * Math.pow(2, Math.min(attempts, 5)), 30000)
          setTimeout(() => {
            const ws = createWebSocket(deviceId)
            wsRefs.current[deviceId] = ws
            setTabs(prev2 => {
              const next = new Map(prev2)
              const current = next.get(deviceId)
              if (current) {
                next.set(deviceId, { ...current, ws })
              }
              return next
            })
          }, delay)
        }
        return prev
      })
    }

    ws.onerror = () => {
      // onclose will fire after this
    }

    return ws
  }, [addMessage])

  const openTerminal = useCallback((device: Device) => {
    const deviceId = device.id
    if (tabs.has(deviceId)) {
      setActiveTabKey(deviceId)
      return
    }

    const ws = createWebSocket(deviceId)
    wsRefs.current[deviceId] = ws

    const newTab: TerminalTab = {
      deviceId,
      deviceName: device.name,
      messages: [],
      listening: false,
      ws,
      reconnectAttempts: 0,
    }

    setTabs(prev => {
      const next = new Map(prev)
      next.set(deviceId, newTab)
      return next
    })
    setActiveTabKey(deviceId)
  }, [tabs, createWebSocket])

  const closeTerminal = useCallback((deviceId: string) => {
    const ws = wsRefs.current[deviceId]
    if (ws) {
      ws.onclose = null // prevent reconnect
      ws.close()
      delete wsRefs.current[deviceId]
    }

    setTabs(prev => {
      const next = new Map(prev)
      next.delete(deviceId)
      return next
    })

    setCommandInputs(prev => {
      const next = { ...prev }
      delete next[deviceId]
      return next
    })

    setCommandHistories(prev => {
      const next = { ...prev }
      delete next[deviceId]
      return next
    })

    setHistoryIndexes(prev => {
      const next = { ...prev }
      delete next[deviceId]
      return next
    })

    // Switch to another tab if available
    if (activeTabKey === deviceId) {
      setTabs(prev => {
        const keys = Array.from(prev.keys())
        if (keys.length > 0) {
          setActiveTabKey(keys[keys.length - 1])
        } else {
          setActiveTabKey('')
        }
        return prev
      })
    }
  }, [activeTabKey])

  const sendCommand = useCallback((deviceId: string) => {
    const command = commandInputs[deviceId]?.trim()
    if (!command) return

    const ws = wsRefs.current[deviceId]
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      addMessage(deviceId, {
        id: nextMsgId(),
        timestamp: formatTime(),
        type: 'error',
        content: 'WebSocket 未连接，无法发送命令',
      })
      return
    }

    ws.send(JSON.stringify({ type: 'command', command }))

    // Save to history
    setCommandHistories(prev => ({
      ...prev,
      [deviceId]: [...(prev[deviceId] || []), command],
    }))
    setHistoryIndexes(prev => ({
      ...prev,
      [deviceId]: (prev[deviceId] || 0) + 1,
    }))

    // Clear input
    setCommandInputs(prev => ({ ...prev, [deviceId]: '' }))
  }, [commandInputs, addMessage])

  const toggleListening = useCallback((deviceId: string) => {
    const ws = wsRefs.current[deviceId]
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    const tab = tabs.get(deviceId)
    if (tab?.listening) {
      ws.send(JSON.stringify({ type: 'stop_receive' }))
    } else {
      ws.send(JSON.stringify({ type: 'start_receive', interval_ms: 200 }))
    }
  }, [tabs])

  const clearMessages = useCallback((deviceId: string) => {
    setTabs(prev => {
      const next = new Map(prev)
      const tab = next.get(deviceId)
      if (tab) {
        next.set(deviceId, { ...tab, messages: [] })
      }
      return next
    })
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent, deviceId: string) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendCommand(deviceId)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const history = commandHistories[deviceId] || []
      if (history.length === 0) return
      setHistoryIndexes(prev => {
        const currentIdx = prev[deviceId] ?? history.length
        const newIdx = Math.max(0, currentIdx - 1)
        setCommandInputs(prev2 => ({
          ...prev2,
          [deviceId]: history[newIdx] || '',
        }))
        return { ...prev, [deviceId]: newIdx }
      })
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const history = commandHistories[deviceId] || []
      setHistoryIndexes(prev => {
        const currentIdx = prev[deviceId] ?? history.length
        const newIdx = Math.min(history.length, currentIdx + 1)
        setCommandInputs(prev2 => ({
          ...prev2,
          [deviceId]: newIdx < history.length ? history[newIdx] : '',
        }))
        return { ...prev, [deviceId]: newIdx }
      })
    }
  }, [commandHistories, sendCommand])

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

  // Render tab content for a device
  const renderTerminalContent = (deviceId: string) => {
    const tab = tabs.get(deviceId)
    if (!tab) return null

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
            <Tag color={tab.ws && tab.ws.readyState === WebSocket.OPEN ? 'green' : 'red'}>
              {tab.ws && tab.ws.readyState === WebSocket.OPEN ? '已连接' : '未连接'}
            </Tag>
          </Space>
          <Space>
            <Tooltip title={tab.listening ? '停止监听' : '开始监听实时数据'}>
              <Button
                size="small"
                type={tab.listening ? 'primary' : 'default'}
                danger={tab.listening}
                icon={tab.listening ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
                onClick={() => toggleListening(deviceId)}
                disabled={!tab.ws || tab.ws.readyState !== WebSocket.OPEN}
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
          ref={(el) => { logRefs.current[deviceId] = el }}
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
            value={commandInputs[deviceId] || ''}
            onChange={(e) => setCommandInputs(prev => ({ ...prev, [deviceId]: e.target.value }))}
            onKeyDown={(e) => handleKeyDown(e, deviceId)}
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
            onClick={() => sendCommand(deviceId)}
            disabled={!tab.ws || tab.ws.readyState !== WebSocket.OPEN}
          >
            发送
          </Button>
        </div>
      </div>
    )
  }

  // Render tab bar
  const renderTabBar = () => {
    const tabEntries = Array.from(tabs.entries())
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
            onClick={() => setActiveTabKey(deviceId)}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '8px 12px',
              cursor: 'pointer',
              borderRight: '1px solid #333',
              background: activeTabKey === deviceId ? '#1e1e1e' : '#2d2d2d',
              color: activeTabKey === deviceId ? '#fff' : '#999',
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
              const isActive = activeTabKey === device.id
              const hasTab = tabs.has(device.id)
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
        {tabs.size === 0 ? (
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
              {activeTabKey && tabs.has(activeTabKey) ? (
                renderTerminalContent(activeTabKey)
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
