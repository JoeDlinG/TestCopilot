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
import ExecutionPlanner from './pages/ExecutionPlanner'
import Logs from './pages/Logs'
import Reports from './pages/Reports'
import Plugins from './pages/Plugins'
import PluginEditor from './pages/PluginEditor'
import SkillEditor from './pages/SkillEditor'
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
        <Route path="execution-plans" element={<ExecutionPlanner />} />
        <Route path="logs" element={<Logs />} />
        <Route path="reports" element={<Reports />} />
        <Route path="plugins" element={<Plugins />} />
        <Route path="plugin-editor" element={<PluginEditor />} />
        <Route path="skill-editor" element={<SkillEditor />} />
      <Route path="model-config" element={<ModelConfig />} />
      </Route>
    </Routes>
  )
}

export default App
