import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Unwrap FastAPI detail payload to log the actual reason, not just
    // the generic outer "message" string (e.g. log "API key invalid"
    // instead of "AI chat failed").
    const body = error.response?.data
    const detail = body?.detail
    let msg: string
    if (typeof detail === 'string') {
      msg = detail
    } else if (detail && typeof detail === 'object') {
      msg = detail.detail || detail.message || error.message || '请求失败'
    } else {
      msg = body?.message || error.message || '请求失败'
    }
    console.error('API Error:', msg, error.response?.status)
    return Promise.reject(error)
  }
)

// Device APIs
export const deviceAPI = {
  list: () => api.get('/devices/'),
  get: (id: string) => api.get(`/devices/${id}`),
  create: (data: any) => api.post('/devices/', data),
  delete: (id: string) => api.delete(`/devices/${id}`),
  discover: () => api.get('/devices/discover'),
  connect: (deviceId: string, config?: any) =>
    api.post('/devices/connect', { device_id: deviceId, config }),
  disconnect: (id: string) => api.post(`/devices/${id}/disconnect`),
  sendCommand: (id: string, command: string) =>
    api.post(`/devices/${id}/command`, { command }),
}

// AI APIs
export const aiAPI = {
  listModels: () => api.get('/ai/models'),
  createModel: (data: any) => api.post('/ai/models', data),
  updateModel: (id: string, data: any) => api.put(`/ai/models/${id}`, data),
  deleteModel: (id: string) => api.delete(`/ai/models/${id}`),
  activateModel: (id: string) => api.post(`/ai/models/${id}/activate`),
  testModel: (id: string) => api.post(`/ai/models/${id}/test`),
  chat: (data: any) => api.post('/ai/chat', data),
  generateTestCases: (data: any) => api.post('/ai/generate-testcases', data),
  naturalLanguageQuery: (data: any) => api.post('/ai/query', data),
  transcribeSpeech: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('/ai/speech/transcribe', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// Test Case APIs
export const testCaseAPI = {
  list: () => api.get('/testcases/'),
  get: (id: string) => api.get(`/testcases/${id}`),
  create: (data: any) => api.post('/testcases/', data),
  update: (id: string, data: any) => api.put(`/testcases/${id}`, data),
  delete: (id: string) => api.delete(`/testcases/${id}`),
  generate: (data: any) => api.post('/testcases/generate', data),
  // Import AI-generated test cases with flows
  importAiResult: (data: any) => api.post('/testcases/import-ai-result', data),
  // Flowchart
  getFlow: (id: string) => api.get(`/testcases/${id}/flow`),
  createFlow: (id: string, data: any) => api.post(`/testcases/${id}/flow`, data),
  updateFlow: (id: string, data: any) => api.put(`/testcases/${id}/flow`, data),
  // Code generation
  generateCode: (id: string) => api.post(`/testcases/${id}/generate-code`),
}

// Execution APIs
export const executionAPI = {
  list: (testCaseId?: string) =>
    api.get('/executions/', { params: { test_case_id: testCaseId } }),
  get: (id: string) => api.get(`/executions/${id}`),
  run: (testCaseId: string, options?: any) =>
    api.post('/executions/run', { test_case_id: testCaseId, options }),
  stop: (id: string) => api.post(`/executions/${id}/stop`),
}

// Log APIs
export const logAPI = {
  list: (params?: any) => api.get('/logs/', { params }),
  exportCSV: (params?: any) =>
    api.get('/logs/export/csv', { params, responseType: 'blob' }),
}

// Report APIs
export const reportAPI = {
  list: () => api.get('/reports/'),
  generate: (data: any) => api.post('/reports/generate', data),
  listTemplates: () => api.get('/reports/templates'),
  createTemplate: (data: any) => api.post('/reports/templates', data),
}

// System control APIs
export const systemAPI = {
  restart: () => api.post('/system/restart'),
}

// Plugin APIs
export const pluginAPI = {
  list: () => api.get('/plugins/'),
  install: (data: any) => api.post('/plugins/install', data),
  discovered: () => api.get('/plugins/discovered'),
  installDiscovered: (item: any) =>
    api.post('/plugins/install', {
      name: item.name,
      version: item.version || '1.0.0',
      description: item.description,
      protocol_type: item.protocol_name,
      file_path: item.file_path,
      module_name: item.module_name,
      class_name: item.class_name,
    }),
  enable: (id: string) => api.post(`/plugins/${id}/enable`),
  disable: (id: string) => api.post(`/plugins/${id}/disable`),
  addDevice: (id: string) => api.post(`/plugins/${id}/add-device`),
  listSkills: () => api.get('/plugins/skills'),
  getSkill: (protocol: string) => api.get(`/plugins/skills/${protocol}`),
}

export default api
