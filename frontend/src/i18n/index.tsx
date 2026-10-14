import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'dayjs/locale/en'
import { messages } from './messages'

export type Locale = 'zh-CN' | 'en-US'

export const LOCALES: { value: Locale; label: string }[] = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

/** antd's own locale pack for each supported language. */
export const ANTD_LOCALE: Record<Locale, any> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

const STORAGE_KEY = 'aitestlab.locale'
const DAYJS_LOCALE: Record<Locale, string> = { 'zh-CN': 'zh-cn', 'en-US': 'en' }

/** ``zh-CN`` entries double as the fallback, so partial translations are safe. */
const FALLBACK: Locale = 'zh-CN'

function detectLocale(): Locale {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'zh-CN' || stored === 'en-US') return stored
  } catch { /* localStorage may be unavailable */ }
  const nav = (typeof navigator !== 'undefined' && navigator.language) || ''
  return nav.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en-US'
}

interface I18nValue {
  locale: Locale
  setLocale: (locale: Locale) => void
  /** Translate a key, substituting ``{name}`` placeholders from *vars*. */
  t: (key: string, vars?: Record<string, string | number>) => string
}

const I18nContext = createContext<I18nValue>({
  locale: 'zh-CN',
  setLocale: () => {},
  t: (key) => key,
})

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(detectLocale)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, locale)
    } catch { /* ignore */ }
    // Keeps antd's date pickers and dayjs formatting in sync with the UI.
    dayjs.locale(DAYJS_LOCALE[locale])
  }, [locale])

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const raw = messages[locale]?.[key] ?? messages[FALLBACK]?.[key] ?? key
      if (!vars) return raw
      return raw.replace(/\{(\w+)\}/g, (m, name: string) =>
        name in vars ? String(vars[name]) : m,
      )
    },
    [locale],
  )

  const setLocale = useCallback((next: Locale) => setLocaleState(next), [])

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t])

  return (
    <I18nContext.Provider value={value}>
      <ConfigProvider locale={ANTD_LOCALE[locale]}>{children}</ConfigProvider>
    </I18nContext.Provider>
  )
}

export function useI18n(): I18nValue {
  return useContext(I18nContext)
}
