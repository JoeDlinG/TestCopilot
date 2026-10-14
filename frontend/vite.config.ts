import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Issue #12: the whole app used to land in one ~2.3 MB chunk, so every page
    // load pulled in the flow editor, the charts and all of antd even for users
    // who never open them.  Split vendor libraries by concern and let Rollup
    // emit per-route chunks (see the lazy imports in App.tsx).
    // antd (with its rc-* primitives) is ~1.0 MB on its own and cannot be split
    // meaningfully below that; everything else stays well under the limit.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('react-flow') || id.includes('@reactflow')) return 'vendor-flow'
          // The icon package ships every icon as its own module and is pulled in
          // by toolbar buttons on almost every page; isolate it so the rest of
          // antd can be cached independently.
          if (id.includes('@ant-design/icons')) return 'vendor-icons'
          // ``rc-*`` are antd's internal primitives — they must travel with it,
          // otherwise they end up in the catch-all chunk and get loaded
          // separately from the components that own them.
          if (
            id.includes('antd')
            || id.includes('@ant-design')
            || id.includes('/rc-')
          ) {
            return 'vendor-antd'
          }
          if (id.includes('echarts') || id.includes('recharts') || id.includes('d3-')) {
            return 'vendor-charts'
          }
          if (id.includes('react-markdown') || id.includes('remark') || id.includes('rehype')) {
            return 'vendor-markdown'
          }
          if (id.includes('react-router')) return 'vendor-router'
          if (id.includes('react-grid-layout')) return 'vendor-grid'
          // react-syntax-highlighter pulls in refractor's full language set.
          // Keep it isolated so pages that never render code skip it entirely.
          if (
            id.includes('react-syntax-highlighter')
            || id.includes('refractor')
            || id.includes('highlight.js')
          ) {
            return 'vendor-highlight'
          }
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('scheduler')) {
            return 'vendor-react'
          }
          if (id.includes('axios')) return 'vendor-http'
          return 'vendor-misc'
        },
      },
    },
  },
})
