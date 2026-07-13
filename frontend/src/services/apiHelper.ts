import { message } from 'antd'

// Extract data from a successful axios response
// The axios response has shape: { data: { code, message, data: actualData }, status, ... }
// We need to extract response.data.data
export function extractData<T = any>(response: any, fallback: T = [] as any): T {
  if (response?.data?.code === 0) {
    return response.data.data ?? fallback
  }
  return fallback
}

// Extract items array from paginated list response
export function extractItems<T = any>(response: any, fallback: T[] = []): T[] {
  const data = extractData(response)
  if (data && Array.isArray(data.items)) {
    return data.items
  }
  if (Array.isArray(data)) {
    return data
  }
  return fallback
}

// Extract total count from paginated list response
export function extractTotal(response: any, fallback: number = 0): number {
  const data = extractData(response)
  if (data && typeof data.total === 'number') {
    return data.total
  }
  if (Array.isArray(data)) {
    return data.length
  }
  return fallback
}

// Handle API error with user-friendly message
export function handleApiError(err: any, defaultMsg: string = '操作失败'): void {
  const msg = err?.response?.data?.detail?.message || err?.response?.data?.message || defaultMsg
  message.error(msg)
}
