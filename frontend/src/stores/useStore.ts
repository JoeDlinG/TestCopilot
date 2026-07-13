import { create } from 'zustand'
import type { Device, AIModel, TestCase, TestExecution, Plugin } from '../types'

interface AppState {
  // Devices
  devices: Device[]
  setDevices: (devices: Device[]) => void

  // AI Models
  aiModels: AIModel[]
  setAiModels: (models: AIModel[]) => void
  activeModelId: string | null
  setActiveModelId: (id: string | null) => void

  // Test Cases
  testCases: TestCase[]
  setTestCases: (cases: TestCase[]) => void

  // Executions
  executions: TestExecution[]
  setExecutions: (executions: TestExecution[]) => void

  // Plugins
  plugins: Plugin[]
  setPlugins: (plugins: Plugin[]) => void

  // UI State
  sidebarCollapsed: boolean
  toggleSidebar: () => void
  selectedKeys: string[]
  setSelectedKeys: (keys: string[]) => void
}

const useStore = create<AppState>((set) => ({
  devices: [],
  setDevices: (devices) => set({ devices }),

  aiModels: [],
  setAiModels: (models) => set({ aiModels: models }),
  activeModelId: null,
  setActiveModelId: (id) => set({ activeModelId: id }),

  testCases: [],
  setTestCases: (cases) => set({ testCases: cases }),

  executions: [],
  setExecutions: (executions) => set({ executions }),

  plugins: [],
  setPlugins: (plugins) => set({ plugins }),

  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  selectedKeys: ['/'],
  setSelectedKeys: (keys) => set({ selectedKeys: keys }),
}))

export default useStore
