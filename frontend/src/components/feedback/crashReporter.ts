/**
 * Front-end crash capture (issue #26, sub-task F6).
 *
 * Three sources are wired up: React render errors (via ``ErrorBoundary``),
 * synchronous runtime errors (``window.onerror``) and rejected promises
 * (``unhandledrejection``).
 *
 * Two guards matter in practice:
 *  * **de-duplication** — a render loop or a failing poll produces the same
 *    error hundreds of times per second. Identical messages are collapsed.
 *  * **self-reporting loop** — if the feedback endpoint itself is down, posting
 *    the crash would reject and report itself, forever. Anything originating
 *    from our own API is dropped.
 */
import { feedbackAPI } from '../../services/api'

interface CrashPayload {
  kind: 'crash'
  title: string
  body: string
  stack: string
  route: string
  consent: boolean
  system: Record<string, string>
}

const seen = new Set<string>()
let sentInWindow = 0
let windowStart = Date.now()
const MAX_PER_MINUTE = 5

function systemInfo(): Record<string, string> {
  return {
    os: navigator.platform || navigator.userAgent,
    arch: (navigator as any).userAgentData?.architecture || '',
    python: '', // filled server-side
    ua: navigator.userAgent.slice(0, 200),
    lang: navigator.language,
  }
}

async function submit(payload: CrashPayload) {
  try {
    await feedbackAPI.submit(payload as any)
  } catch {
    /* offline or rejected — the backend also queues nothing here, so we just
       drop it; the next crash will try again. */
  }
}

function normalise(text: string): string {
  // Line numbers and object ids make otherwise-identical crashes look unique.
  return text.replace(/\d+/g, '#').slice(0, 300)
}

function report(title: string, stack: string, route: string) {
  if (/feedback|api\.github|\/api\//.test(`${title} ${stack}`)) return
  const key = normalise(`${title}|${stack}`)
  if (seen.has(key)) return
  seen.add(key)
  if (seen.size > 100) seen.clear()

  const now = Date.now()
  if (now - windowStart > 60_000) {
    windowStart = now
    sentInWindow = 0
  }
  if (sentInWindow >= MAX_PER_MINUTE) return
  sentInWindow++

  void submit({
    kind: 'crash',
    title: title.slice(0, 200),
    body: '',
    stack: stack.slice(0, 8000),
    route,
    consent: true,
    system: systemInfo(),
  })
}

export function installCrashReporter(getRoute: () => string): () => void {
  const onError = (event: ErrorEvent) => {
    const err = event.error
    const title = err?.name ? `${err.name}: ${err.message}` : (event.message || 'Unknown error')
    report(title, err?.stack || `${event.filename}:${event.lineno}:${event.colno}`, getRoute())
  }
  const onRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason
    const title = reason?.name
      ? `${reason.name}: ${reason.message}`
      : `Unhandled rejection: ${String(reason).slice(0, 120)}`
    report(title, reason?.stack || String(reason), getRoute())
  }

  window.addEventListener('error', onError)
  window.addEventListener('unhandledrejection', onRejection)
  return () => {
    window.removeEventListener('error', onError)
    window.removeEventListener('unhandledrejection', onRejection)
  }
}

/** Called by ``ErrorBoundary`` for render-time crashes. */
export function reportRenderError(error: Error, info: string, route: string) {
  report(`${error.name}: ${error.message}`, `${error.stack || ''}\n${info}`, route)
}
