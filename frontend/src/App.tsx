import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Spin } from 'antd'
import AppLayout from './components/layout/AppLayout'
import Dashboard from './pages/Dashboard'

// Issue #12: the bundle used to be a single ~2.3 MB chunk. Pages that pull in
// heavy dependencies (React Flow, antd widgets, markdown, charts) are loaded on
// demand so the initial download only covers what the user actually opens.
const CustomDashboard = lazy(() => import('./pages/CustomDashboard'))
const Devices = lazy(() => import('./pages/Devices'))
const DebugTerminal = lazy(() => import('./pages/DebugTerminal'))
const AIChat = lazy(() => import('./pages/AIChat'))
const TestCases = lazy(() => import('./pages/TestCases'))
const TestFlowEditor = lazy(() => import('./pages/TestFlowEditor'))
const Executions = lazy(() => import('./pages/Executions'))
const ExecutionPlanner = lazy(() => import('./pages/ExecutionPlanner'))
const Logs = lazy(() => import('./pages/Logs'))
const Reports = lazy(() => import('./pages/Reports'))
const Plugins = lazy(() => import('./pages/Plugins'))
// NOTE: PluginEditor / SkillEditor are no longer routed directly — they are
// tabs inside 插件中心 (./pages/Plugins).

const ModelConfig = lazy(() => import('./pages/ModelConfig'))
const ProjectManager = lazy(() => import('./pages/ProjectManager'))

const PageLoading = () => (
  <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
    <Spin size="large" />
  </div>
)

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route
          path="dashboards"
          element={<Suspense fallback={<PageLoading />}><CustomDashboard /></Suspense>}
        />
        <Route
          path="devices"
          element={<Suspense fallback={<PageLoading />}><Devices /></Suspense>}
        />
        <Route
          path="debug-terminal"
          element={<Suspense fallback={<PageLoading />}><DebugTerminal /></Suspense>}
        />
        <Route
          path="ai"
          element={<Suspense fallback={<PageLoading />}><AIChat /></Suspense>}
        />
        <Route
          path="testcases"
          element={<Suspense fallback={<PageLoading />}><TestCases /></Suspense>}
        />
        <Route
          path="testcases/:id/flow"
          element={<Suspense fallback={<PageLoading />}><TestFlowEditor /></Suspense>}
        />
        <Route
          path="executions"
          element={<Suspense fallback={<PageLoading />}><Executions /></Suspense>}
        />
        <Route
          path="execution-plans"
          element={<Suspense fallback={<PageLoading />}><ExecutionPlanner /></Suspense>}
        />
        <Route
          path="logs"
          element={<Suspense fallback={<PageLoading />}><Logs /></Suspense>}
        />
        <Route
          path="reports"
          element={<Suspense fallback={<PageLoading />}><Reports /></Suspense>}
        />
        <Route
          path="plugins"
          element={<Suspense fallback={<PageLoading />}><Plugins /></Suspense>}
        />
        {/* Issue #21: the three plugin pages merged into one 插件中心 route.
            These legacy paths are kept so old links still open the right tab. */}
        <Route
          path="plugin-editor"
          element={<Suspense fallback={<PageLoading />}><Plugins tab="editor" /></Suspense>}
        />
        <Route
          path="skill-editor"
          element={<Suspense fallback={<PageLoading />}><Plugins tab="skill" /></Suspense>}
        />
        <Route
          path="model-config"
          element={<Suspense fallback={<PageLoading />}><ModelConfig /></Suspense>}
        />
        <Route
          path="projects"
          element={<Suspense fallback={<PageLoading />}><ProjectManager /></Suspense>}
        />
      </Route>
    </Routes>
  )
}

export default App
