/**
 * Output dock state — intentionally global.
 *
 * Issue #20: the dock's expanded / pinned / active-tab state must survive
 * navigating between left-menu pages; keeping it in a component would reset it
 * on every route change. "Auto-expand on run" is also triggered from arbitrary
 * pages (test case list, flow editor, execution manager), so pages call
 * :func:`openDock` instead of each implementing their own panel.
 */
import { create } from 'zustand'

export type DockTab = 'executions' | 'reports'
export type DockState = 'collapsed' | 'expanded' | 'fullscreen'

interface OutputDockStore {
  state: DockState
  tab: DockTab
  pinned: boolean
  /** Number of currently running executions (drives the collapsed badge). */
  runningCount: number

  expand: (tab?: DockTab) => void
  collapse: () => void
  setFullscreen: (on: boolean) => void
  toggle: () => void
  setTab: (tab: DockTab) => void
  togglePin: () => void
  setRunningCount: (n: number) => void
}

const PIN_KEY = 'aitestlab.dock.pinned'

function loadPinned(): boolean {
  try {
    return localStorage.getItem(PIN_KEY) === '1'
  } catch {
    return false
  }
}

export const useOutputDock = create<OutputDockStore>((set, get) => ({
  state: 'collapsed',
  tab: 'executions',
  pinned: loadPinned(),
  runningCount: 0,

  expand: (tab) =>
    set((s) => ({
      state: 'expanded',
      tab: tab ?? s.tab,
    })),

  collapse: () => set({ state: 'collapsed' }),

  setFullscreen: (on) => set({ state: on ? 'fullscreen' : 'expanded' }),

  toggle: () => {
    const { state } = get()
    set({ state: state === 'collapsed' ? 'expanded' : 'collapsed' })
  },

  setTab: (tab) => set({ tab }),
  togglePin: () => {
    const next = !get().pinned
    try {
      localStorage.setItem(PIN_KEY, next ? '1' : '0')
    } catch { /* ignore */ }
    set({ pinned: next })
  },

  setRunningCount: (n) => set({ runningCount: Math.max(0, n) }),
}))

/** Convenience for callers outside React (e.g. event handlers). */
export const openDock = (tab?: DockTab) => useOutputDock.getState().expand(tab)
