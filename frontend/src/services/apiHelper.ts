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

/**
 * Unwrap a successful API response regardless of its envelope.
 *
 * Most routers answer with `{ code: 0, message: "success", data: <payload> }`.
 * The DBC router (issue #24) answers with the bare payload — a JSON array for
 * list endpoints and a JSON object for detail/parser-spec endpoints. Passing
 * those bare responses to `extractData`/`extractItems` made the DBC page and
 * the "pick a DBC signal" dialog render an empty list even though the import
 * had been committed. This helper accepts BOTH shapes so a later backend
 * normalisation cannot silently blank the UI again.
 *
 * A wrapped response with a non-zero `code` is treated as an error instead of
 * being swallowed as an empty result.
 */
export function unwrapPayload<T = any>(response: any, fallback: T | null = null): T | null {
  const body = response?.data
  if (body === undefined || body === null) return fallback
  const isEnvelope = typeof body === 'object' && !Array.isArray(body)
    && Object.prototype.hasOwnProperty.call(body, 'code')
    && Object.prototype.hasOwnProperty.call(body, 'data')
  if (!isEnvelope) return body as T
  if (body.code !== 0) {
    throw new Error(String(body.message || body.detail || `服务端返回 code=${body.code}`))
  }
  return (body.data ?? fallback) as T
}

/** List version of `unwrapPayload`: bare array, `{items}` or wrapped data. */
export function extractItemsCompat<T = any>(response: any, fallback: T[] = []): T[] {
  const payload: any = unwrapPayload(response)
  if (Array.isArray(payload)) return payload as T[]
  if (payload && Array.isArray(payload.items)) return payload.items as T[]
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
  const status = err?.response?.status
  if (body === undefined || body === null) {
    // No response at all — most likely a timeout, network error, or a local
    // JS error thrown before the request was even sent.
    if (err?.code === 'ECONNABORTED' || err?.message?.includes('timeout')) {
      return `${defaultMsg}（请求超时：AI 模型正在推理中，请稍后重试。推理模型可能需要 1-3 分钟生成回复。）`
    }
    if (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network')) {
      return `${defaultMsg}（网络错误：请检查后端服务是否正常运行）`
    }
    return err?.message ? `${defaultMsg}（${err.message}）` : defaultMsg
  }
  // Non-JSON body (e.g. an HTML error page from a proxy or an unhandled 500).
  if (typeof body === 'string') {
    const snippet = body.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 200)
    return `${defaultMsg}（${status ? `HTTP ${status}: ` : ''}${snippet || '服务器返回了非 JSON 错误'}）`
  }
  const detail = body.detail
  // FastAPI 422 validation errors: detail is an ARRAY of {loc, msg, type}.
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) => {
        if (typeof d === 'string') return d
        const loc = Array.isArray(d?.loc)
          ? d.loc.filter((x: any) => x !== 'body').join('.')
          : ''
        return `${loc ? `${loc}: ` : ''}${d?.msg || d?.type || JSON.stringify(d)}`
      })
      .filter(Boolean)
    return msgs.length ? `${defaultMsg}（${msgs.join('；')}）` : defaultMsg
  }
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
