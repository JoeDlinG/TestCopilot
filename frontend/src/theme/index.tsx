import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ConfigProvider, theme } from 'antd'
import { antdTokens, graphite, type ThemeMode } from './tokens'
import { cssVars } from './cssVars'

export { primitives, semantic, componentTokens, graphite, blue, amber, red } from './tokens'
export type { ThemeMode } from './tokens'

const STORAGE_KEY = 'aitestlab.theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

function detectMode(): ThemeMode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch { /* localStorage may be unavailable */ }
  if (typeof window !== 'undefined' && window.matchMedia?.(DARK_QUERY).matches) {
    return 'dark'
  }
  return 'light'
}

interface ThemeValue {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
  toggle: () => void
}

const ThemeContext = createContext<ThemeValue>({
  mode: 'light',
  setMode: () => {},
  toggle: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(detectMode)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, mode)
    } catch { /* ignore */ }
    // Keep native controls (scrollbars, form controls) in sync with the theme.
    document.documentElement.dataset.theme = mode
  }, [mode])

  const setMode = useCallback((next: ThemeMode) => setModeState(next), [])
  const toggle = useCallback(() => setModeState(m => (m === 'dark' ? 'light' : 'dark')), [])

  const value = useMemo(() => ({ mode, setMode, toggle }), [mode, setMode, toggle])

  return (
    <ThemeContext.Provider value={value}>
      {/* The flow editor (and any canvas/SVG surface) reads the palette through
          these variables, so it follows the theme without hard-coded colours. */}
      <style>{cssVars}</style>
      <ConfigProvider
        theme={{
          algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
          token: antdTokens(mode),
          components: {
            // The redesign targets a dense, instrument-like UI.
            Table: { cellPaddingBlock: 8, cellPaddingInline: 12 },
            Layout: {
              siderBg: mode === 'dark' ? graphite[900] : graphite[0],
              headerBg: mode === 'dark' ? graphite[900] : graphite[0],
            },
          },
        }}
      >
        {children}
      </ConfigProvider>
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext)
}
