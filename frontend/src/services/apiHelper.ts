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

/** Unwrap the actual error detail from a FastAPI HTTPException response.
 *
 * FastAPI ``HTTPException(detail={...})`` serialises as:
 *   ``{"detail": {"code": ..., "message": "generic", "detail": "actual"}}``
 *
 * We prefer the innermost ``detail.detail`` (the real reason) and fall back
 * through the generic ``detail.message``, the top-level ``message``, and
 * finally the caller-supplied default.
 *
 * Timeout errors (axios ECONNABORTED / ETIMEDOUT) receive a descriptive
 * message that explains the likely cause (reasoning model is still thinking).
 */
function _errorMessage(err: any, defaultMsg: string): string {
  const body = err?.response?.data
  if (!body) {
    // No response at all — most likely a timeout or network error
    if (err?.code === 'ECONNABORTED' || err?.message?.includes('timeout')) {
      return `${defaultMsg}（请求超时：AI 模型正在推理中，请稍后重试。推理模型可能需要 1-3 分钟生成回复。）`
    }
    if (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network')) {
      return `${defaultMsg}（网络错误：请检查后端服务是否正常运行）`
    }
    return defaultMsg
  }
  const detail = body.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    // Innermost detail is the most useful diagnostic
    return detail.detail || detail.message || defaultMsg
  }
  return body.message || defaultMsg
}

// Handle API error with user-friendly message
export function handleApiError(err: any, defaultMsg: string = '操作失败'): void {
  const msg = _errorMessage(err, defaultMsg)
  message.error(msg)
}

export { _errorMessage }
