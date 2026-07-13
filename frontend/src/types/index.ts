// TypeScript type definitions for AITestLab

export interface Device {
  id: string
  name: string
  device_type: string
  interface_type: string
  visa_address?: string
  serial_port?: string
  can_channel?: string
  ip_address?: string
  port?: number
  config: Record<string, any>
  is_connected: boolean
  last_connected?: string
  created_at: string
}

export interface AIModel {
  id: string
  name: string
  provider: string
  model_name: string
  is_local: boolean
  is_active: boolean
  config: Record<string, any>
  created_at: string
}

export interface TestStep {
  step_number: number
  action: string
  expected_result: string
  parameters: Record<string, any>
  device_type?: string
}

export interface TestCase {
  id: string
  name: string
  description?: string
  requirements_text?: string
  steps: TestStep[]
  flow_data?: any
  expected_result?: string
  parameters: Record<string, any>
  devices_required: string[]
  tags: string[]
  status: string
  created_by_ai: boolean
  created_at: string
  updated_at: string
}

export interface TestExecution {
  id: string
  test_case_id: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'stopped'
  start_time?: string
  end_time?: string
  duration_ms?: number
  results: any[]
  error_message?: string
  created_at: string
}

export interface CommunicationLog {
  id: string
  device_id?: string
  execution_id?: string
  interface_type: string
  direction: 'send' | 'receive'
  raw_data?: string
  data_hex?: string
  timestamp: string
  metadata: Record<string, any>
}

export interface TestReport {
  id: string
  name: string
  execution_ids: string[]
  template_id?: string
  fields: Record<string, any>
  format: string
  file_path?: string
  created_at: string
}

export interface ReportTemplate {
  id: string
  name: string
  description?: string
  fields: any[]
  created_at: string
  updated_at: string
}

export interface Plugin {
  id: string
  name: string
  version: string
  description?: string
  protocol_name: string
  is_enabled: boolean
  created_at: string
}

export interface AIChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  input_type?: 'text' | 'voice'
}

export interface AIChatResponse {
  session_id: string
  response: string
  usage?: any
}

export interface NLQueryResult {
  query: string
  sql_generated?: string
  results: any[]
  result_count: number
  explanation?: string
}

export const DEVICE_TYPES: Record<string, string> = {
  power_supply: '可编程电源',
  oscilloscope: '示波器',
  multimeter: '万用表',
  signal_generator: '信号发生器',
  spectrum_analyzer: '频谱分析仪',
  can_tool: 'CAN 工具',
  generic: '通用设备',
}

export const INTERFACE_TYPES: Record<string, string> = {
  scpi: 'SCPI',
  can: 'CAN',
  usb: 'USB',
  serial: '串口',
  ethernet: '以太网',
  gpib: 'GPIB',
  custom: '自定义',
}
