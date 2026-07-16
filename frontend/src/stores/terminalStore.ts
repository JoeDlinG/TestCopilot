import { create } from 'zustand'

export interface TerminalMessage {
  id: string
  timestamp: string
  type: 'sent' | 'received' | 'data' | 'error' | 'system'
  content: string
}

export interface TerminalTab {
  deviceId: string
  deviceName: string
  messages: TerminalMessage[]
  listening: boolean
  ws: WebSocket | null
  reconnectAttempts: number
}

interface TerminalState {
  tabs: Record<string, TerminalTab>
  activeTabId: string | null
  commandInputs: Record<string, string>
  commandHistories: Record<string, string[]>
  historyIndexes: Record<string, number>

  openTerminal: (deviceId: string, deviceName: string, ws: WebSocket) => void
  closeTerminal: (deviceId: string) => void
  setActiveTab: (deviceId: string) => void
  addMessage: (deviceId: string, msg: TerminalMessage) => void
  clearMessages: (deviceId: string) => void
  setListening: (deviceId: string, listening: boolean) => void
  setWs: (deviceId: string, ws: WebSocket | null) => void
  setReconnectAttempts: (deviceId: string, n: number) => void
  setCommandInput: (deviceId: string, value: string) => void
  addCommandHistory: (deviceId: string, cmd: string) => void
  setHistoryIndex: (deviceId: string, idx: number) => void
}

export const useTerminalStore = create<TerminalState>((set) => ({
  tabs: {},
  activeTabId: null,
  commandInputs: {},
  commandHistories: {},
  historyIndexes: {},

  openTerminal: (deviceId, deviceName, ws) =>
    set((state) => {
      if (state.tabs[deviceId]) {
        return { activeTabId: deviceId }
      }
      return {
        activeTabId: deviceId,
        tabs: {
          ...state.tabs,
          [deviceId]: {
            deviceId,
            deviceName,
            messages: [],
            listening: false,
            ws,
            reconnectAttempts: 0,
          },
        },
      }
    }),

  closeTerminal: (deviceId) =>
    set((state) => {
      const tabs = { ...state.tabs }
      delete tabs[deviceId]
      const commandInputs = { ...state.commandInputs }
      delete commandInputs[deviceId]
      const commandHistories = { ...state.commandHistories }
      delete commandHistories[deviceId]
      const historyIndexes = { ...state.historyIndexes }
      delete historyIndexes[deviceId]
      const keys = Object.keys(tabs)
      const activeTabId =
        state.activeTabId === deviceId
          ? keys.length > 0
            ? keys[keys.length - 1]
            : null
          : state.activeTabId
      return { tabs, commandInputs, commandHistories, historyIndexes, activeTabId }
    }),

  setActiveTab: (deviceId) => set({ activeTabId: deviceId }),

  addMessage: (deviceId, msg) =>
    set((state) => {
      const tab = state.tabs[deviceId]
      if (!tab) return {}
      return {
        tabs: {
          ...state.tabs,
          [deviceId]: { ...tab, messages: [...tab.messages, msg] },
        },
      }
    }),

  clearMessages: (deviceId) =>
    set((state) => {
      const tab = state.tabs[deviceId]
      if (!tab) return {}
      return {
        tabs: { ...state.tabs, [deviceId]: { ...tab, messages: [] } },
      }
    }),

  setListening: (deviceId, listening) =>
    set((state) => {
      const tab = state.tabs[deviceId]
      if (!tab) return {}
      return { tabs: { ...state.tabs, [deviceId]: { ...tab, listening } } }
    }),

  setWs: (deviceId, ws) =>
    set((state) => {
      const tab = state.tabs[deviceId]
      if (!tab) return {}
      return { tabs: { ...state.tabs, [deviceId]: { ...tab, ws } } }
    }),

  setReconnectAttempts: (deviceId, n) =>
    set((state) => {
      const tab = state.tabs[deviceId]
      if (!tab) return {}
      return { tabs: { ...state.tabs, [deviceId]: { ...tab, reconnectAttempts: n } } }
    }),

  setCommandInput: (deviceId, value) =>
    set((state) => ({ commandInputs: { ...state.commandInputs, [deviceId]: value } })),

  addCommandHistory: (deviceId, cmd) =>
    set((state) => ({
      commandHistories: {
        ...state.commandHistories,
        [deviceId]: [...(state.commandHistories[deviceId] || []), cmd],
      },
    })),

  setHistoryIndex: (deviceId, idx) =>
    set((state) => ({ historyIndexes: { ...state.historyIndexes, [deviceId]: idx } })),
}))

let msgIdCounter = 0
export function nextMsgId(): string {
  return `msg_${++msgIdCounter}_${Date.now()}`
}
