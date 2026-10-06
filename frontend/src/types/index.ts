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
  base_url?: string
  is_default: boolean
  status: string
  parameters?: Record<string, any>
  last_tested_at?: string
  created_at: string
}

export interface AIModelConfigRequest {
  name: string
  provider: string
  model_name: string
  api_key?: string
  base_url?: string
  parameters?: Record<string, any>
  is_default?: boolean
}

export const PROVIDERS: Record<string, { label: string; default_base_url?: string; hint: string }> = {
  openai: { label: 'OpenAI', default_base_url: 'https://api.openai.com/v1', hint: 'GPT-4o / GPT-4o-mini 等' },
  anthropic: { label: 'Anthropic Claude', default_base_url: 'https://api.anthropic.com/v1', hint: 'claude-3-opus / claude-3-sonnet 等' },
  ollama: { label: 'Ollama (本地)', default_base_url: 'http://localhost:11434/v1', hint: '本地部署，无需 API Key' },
  localai: { label: 'LocalAI', default_base_url: 'http://localhost:8080/v1', hint: 'OpenAI 兼容本地服务' },
  vllm: { label: 'vLLM', default_base_url: 'http://localhost:8000/v1', hint: 'OpenAI 兼容推理服务' },
  hunyuan: { label: '腾讯混元', default_base_url: 'https://api.hunyuan.cloud.tencent.com/v1', hint: 'hunyuan-pro 等' },
  qwen: { label: '阿里通义千问', default_base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', hint: 'qwen-max / qwen-plus 等' },
  ernie: { label: '百度文心一言', default_base_url: 'https://qianfan.baidubce.com/v2', hint: 'ernie-4.0 等' },
  deepseek: { label: 'DeepSeek', default_base_url: 'https://api.deepseek.com/v1', hint: 'deepseek-v4-pro / deepseek-v4-flash（注意：deepseek-chat 已弃用）' },
  minimax: { label: 'MiniMax', default_base_url: 'https://api.minimax.chat/v1', hint: 'abab6.5-chat / MiniMax-Text-01' },
  custom: { label: '自定义 (OpenAI 兼容)', default_base_url: '', hint: '任意 OpenAI 兼容端点' },
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
  test_case_id?: string
  /** actual payload field name used by the backend */
  testcase_id?: string
  /** resolved case name, returned alongside `testcase_id` since v0.7.3 */
  testcase_name?: string
  status: 'pending' | 'running' | 'passed' | 'failed' | 'error' | 'stopped'
  start_time?: string
  end_time?: string
  started_at?: string
  completed_at?: string
  total_steps?: number
  passed_steps?: number
  failed_steps?: number
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

// ============ Custom Dashboard ============

export type WidgetType =
  | 'parsed_value'      // 解析数值卡片
  | 'trend_chart'       // 解析值趋势曲线
  | 'judge_summary'     // 判定结果汇总
  | 'device_status'     // 设备状态
  | 'execution_stats'   // 执行统计
  | 'comm_log'          // 通信日志
  | 'note'              // 文本备注

export interface DashboardWidget {
  id: string
  type: WidgetType
  title: string
  config: Record<string, any>
}

export interface DashboardLayoutItem {
  i: string
  x: number
  y: number
  w: number
  h: number
  minW?: number
  minH?: number
}

export interface DashboardDataSource {
  test_case_id: string | null
  limit: number
  refresh_sec: number
}

export interface CustomDashboard {
  id: string
  name: string
  description?: string
  layout: DashboardLayoutItem[]
  widgets: DashboardWidget[]
  data_source: DashboardDataSource
  is_default: boolean
  created_at: string
  updated_at: string
}

/** one parsed value sampled from a single reply */
export interface ParsedPoint {
  execution_id: string
  step_index: number
  step_label?: string
  seq: number
  total: number
  completed_at?: string | null
  started_at?: string | null
  value: any
  num: number | null
  ok: boolean
  status: 'ok' | 'fail' | 'unknown' | 'error'
  detail?: string | null
}

export interface ParsedLatest {
  field: string
  value: any
  num: number | null
  status: string
  detail?: string | null
  points: number
  min: number | null
  max: number | null
  avg: number | null
  fail_count: number
  updated_at?: string | null
}

export interface DashboardSnapshot {
  generated_at: string
  test_case_id: string | null
  test_case_name: string | null
  devices: {
    total: number
    connected: number
    list: Array<{
      id: string; name: string; type: string; protocol: string
      connection_type: string; status: string; address?: string | null
      connected_at?: string | null; last_seen?: string | null
    }>
  }
  executions: {
    total: number; passed: number; failed: number; error: number
    running: number; pass_rate: number | null
    by_status: Record<string, number>
    recent: Array<{
      id: string; test_case_id: string; status: string; result?: string | null
      total_steps: number; passed_steps: number; failed_steps: number
      duration_ms?: number | null; created_at?: string | null
      completed_at?: string | null; error_message?: string | null
    }>
  }
  parsed: {
    fields: string[]
    series: Record<string, ParsedPoint[]>
    executions: Array<{ id: string; status?: string; result?: string; created_at?: string; started_at?: string }>
    total_points: number
    latest: Record<string, ParsedLatest>
  }
  judgement: {
    total: number; ok: number; fail: number; unknown: number; error: number
    pass_rate: number | null
    by_field: Record<string, {
      total: number; ok: number; fail: number; unknown: number; error: number
      last_value: any; last_num: number | null; last_status: string | null
      pass_rate: number | null
    }>
    failures: Array<{
      field: string; value: any; num: number | null; detail?: string | null
      execution_id?: string; step_index?: number; step_label?: string
      completed_at?: string | null
    }>
    failure_fields: string[]
  }
}

export const DEVICE_TYPES: Record<string, string> = {
  power_supply: '可编程电源',
  oscilloscope: '示波器',
  multimeter: '万用表',
  signal_generator: '信号发生器',
  spectrum_analyzer: '频谱分析仪',
  can_tool: 'CAN 工具',
  gateway: '网关',
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
  mini_gateway100: 'Mini Gateway 100',
}
