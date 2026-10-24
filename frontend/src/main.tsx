import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import App from './App'
import { LanguageProvider } from './i18n'
import { ThemeProvider, blue } from './theme'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      {/* ThemeProvider owns colours (algorithm + tokens); LanguageProvider owns
          the locale pack. Both wrap themselves in antd's ConfigProvider, and
          antd merges nested providers, so the innermost wins per concern. */}
      <ConfigProvider
        theme={{
          algorithm: theme.defaultAlgorithm,
          token: {
            colorPrimary: blue[500],
            borderRadius: 6,
          },
        }}
      >
        <ThemeProvider>
          <LanguageProvider>
            <App />
          </LanguageProvider>
        </ThemeProvider>
      </ConfigProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
