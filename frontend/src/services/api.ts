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
    const message = error.response?.data?.detail || error.message || '请求失败'
    console.error('API Error:', message)
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
  activateModel: (id: string) => api.post(`/ai/models/${id}/activate`),
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

// Plugin APIs
export const pluginAPI = {
  list: () => api.get('/plugins/'),
  install: (data: any) => api.post('/plugins/install', data),
  discovered: () => api.get('/plugins/discovered'),
  enable: (id: string) => api.post(`/plugins/${id}/enable`),
  disable: (id: string) => api.post(`/plugins/${id}/disable`),
}

export default api
