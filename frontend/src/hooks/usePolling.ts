import { useEffect, useRef } from 'react'

/**
 * A ``setInterval`` that behaves itself on a busy dashboard.
 *
 * Two problems with the plain ``setInterval(callLoadingFn, 2000)`` calls this
 * replaced:
 *
 * 1. **Hidden tabs keep polling.** Switch away from AITestLab and every page
 *    still hammers the backend every 2–5 s, stealing bandwidth and CPU from
 *    the machine that is actually running the test.
 * 2. **Slow responses pile up.** If a request takes longer than the interval,
 *    the next tick fires anyway and requests stack on top of each other —
 *    the queue only gets longer exactly when the backend is already struggling.
 *
 * So: skip a tick while ``document.hidden``, and never start a new call before
 * the previous one settles.
 */
export function usePolling(
  callback: () => void | Promise<void>,
  intervalMs: number,
  enabled: boolean = true,
): void {
  const cbRef = useRef(callback)
  // Keep the latest closure without restarting the timer on every render.
  cbRef.current = callback

  useEffect(() => {
    if (!enabled || intervalMs <= 0) return

    let timer: number | undefined
    let inFlight = false

    const tick = async () => {
      if (typeof document !== 'undefined' && document.hidden) return
      if (inFlight) return
      inFlight = true
      try {
        await cbRef.current()
      } catch {
        /* the callback reports its own errors */
      } finally {
        inFlight = false
      }
    }

    const start = () => {
      stop()
      timer = window.setInterval(tick, intervalMs)
    }
    const stop = () => {
      if (timer !== undefined) {
        clearInterval(timer)
        timer = undefined
      }
    }
    const onVisibility = () => {
      if (typeof document === 'undefined') return
      // Catch up immediately when the user comes back instead of waiting a
      // full interval with stale data on screen.
      if (document.hidden) stop()
      else { start(); tick() }
    }

    start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [intervalMs, enabled])
}
