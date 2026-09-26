import { Routes, Route } from 'react-router-dom'
import AppLayout from './components/layout/AppLayout'
import Dashboard from './pages/Dashboard'
import CustomDashboard from './pages/CustomDashboard'
import Devices from './pages/Devices'
import DebugTerminal from './pages/DebugTerminal'
import AIChat from './pages/AIChat'
import TestCases from './pages/TestCases'
import TestFlowEditor from './pages/TestFlowEditor'
import Executions from './pages/Executions'
import Logs from './pages/Logs'
import Reports from './pages/Reports'
import Plugins from './pages/Plugins'
import ModelConfig from './pages/ModelConfig'

function App() {
  return (
    <Routes>
      <Route path="/" element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="dashboards" element={<CustomDashboard />} />
        <Route path="devices" element={<Devices />} />
        <Route path="debug-terminal" element={<DebugTerminal />} />
        <Route path="ai" element={<AIChat />} />
        <Route path="testcases" element={<TestCases />} />
        <Route path="testcases/:id/flow" element={<TestFlowEditor />} />
        <Route path="executions" element={<Executions />} />
        <Route path="logs" element={<Logs />} />
        <Route path="reports" element={<Reports />} />
        <Route path="plugins" element={<Plugins />} />
      <Route path="model-config" element={<ModelConfig />} />
      </Route>
    </Routes>
  )
}

export default App
