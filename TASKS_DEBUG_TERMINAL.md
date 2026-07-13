# 多窗口通信调试终端 — 任务分配

## 角色定义

- **Arch (架构师)**: 后端设计评审、接口契约审核、技术决策
- **BaJie (后端开发)**: Python FastAPI WebSocket 实现
- **WuKong (前端开发)**: React + TypeScript + Ant Design 页面实现
- **WuJin (测试)**: 自动化测试 + 手动集成测试

---

## Arch (架构师) 任务

### TASK-ARCH-001: 审核通信层接口兼容性
- **输入**: `backend/app/communication/__init__.py` 中 `CommunicationInterface` 抽象类
- **输出**: 确认 `send()` 和 `receive()` 方法签名是否满足终端 WebSocket 需求
- **检查点**:
  - `receive(timeout)` 是否可以在后台协程中安全调用（非阻塞）
  - `send()` 返回 `str` 是否足够，是否需要支持二进制数据
  - 各接口实现（SCPI, CAN, Serial, USB, Ethernet）在并发场景下是否线程安全
  - 是否需要增加 `receive_nonblocking()` 方法

### TASK-ARCH-002: 审核 WebSocket 消息协议设计
- **输入**: `SPEC_DEBUG_TERMINAL.md` 第4节消息格式
- **输出**: 确认消息类型、字段、错误码是否完整
- **检查点**:
  - 所有消息类型是否覆盖了前端的全部需求
  - `command_id` 关联机制是否能正确匹配命令和响应
  - 错误消息格式是否与现有 `ApiResponse` 风格一致
  - 是否需要增加 `terminal.status` 类型来推送设备状态变更

### TASK-ARCH-003: 审核数据流架构
- **输入**: `device_service.py` 中的 `_active_connections` 和 `send_command()`
- **输出**: 确认新增 `send_command_raw()` 的合理性，以及 DB 日志分离策略
- **检查点**:
  - `send_command_raw()` 跳过 DB 日志是否合理（调试终端不应污染生产日志表）
  - 是否需要在终端层保留可选日志开关
  - 后台轮询任务的生命周期管理（创建/取消/异常恢复）
  - 多个 WebSocket 同时连接同一设备时，轮询任务是否去重

### TASK-ARCH-004: 前端架构审核
- **输入**: 现有 Zustand store、API service 层、组件结构
- **输出**: 确认前端终端页面的状态管理方案和组件拆分是否合理
- **检查点**:
  - `terminalStore` 是合并到 `useStore.ts` 还是独立文件更优（建议独立）
  - WebSocket hook 是否需要抽象为通用 hook 供其他页面复用
  - Tab 组件是否需要虚拟化（如果同时打开 >10 个终端）
  - 命令历史和自动补全是否属于 MVP 范围

---

## BaJie (后端开发) 任务

### TASK-BE-001: 在 DeviceService 中添加 `send_command_raw()` 方法
- **文件**: `backend/app/services/device_service.py`
- **内容**:
  - 新增方法 `async def send_command_raw(self, device_id: str, command: str) -> dict`
  - 从 `_active_connections` 获取接口，调用 `interface.send(command)`
  - 返回 `{device_id, command, response, duration_ms}`
  - 不写入 CommunicationLog 表（终端调试不污染生产日志）
  - 不要求 `db: AsyncSession` 参数
- **验收**: 方法可通过 import 调用，返回格式正确

### TASK-BE-002: 创建终端 WebSocket 端点
- **文件**: `backend/app/api/terminal_ws.py` (新建)
- **内容**:
  - WebSocket 路由: `@router.websocket("/ws/terminal/{device_id}")`
  - 连接时验证设备存在且已连接（从 `_active_connections` 检查）
  - 发送 `terminal.ready` 确认消息
  - 处理客户端消息:
    - `terminal.command` → 调用 `device_service.send_command_raw()`，返回 `terminal.response`
    - `terminal.ping` → 返回 `terminal.pong`
    - `terminal.start_receive` → 启动后台 `asyncio.Task` 轮询 `interface.receive()`
    - `terminal.stop_receive` → 取消后台轮询任务
  - 连接断开时清理所有资源（取消轮询任务）
  - 使用 `_terminal_sessions: Dict[str, dict]` 跟踪活跃会话
- **验收**: WebSocket 可连接，命令可执行，轮询可启停

### TASK-BE-003: 实现后台轮询任务 `_poll_unsolicited_data()`
- **文件**: `backend/app/api/terminal_ws.py`
- **内容**:
  - `async def _poll_unsolicited_data(device_id: str, interface: CommunicationInterface, websocket: WebSocket, interval: float = 0.5)`
  - 循环调用 `interface.receive(timeout=0.3)` 
  - 收到非空数据时发送 `terminal.unsolicited` 消息
  - 捕获 `asyncio.CancelledError` 优雅退出
  - 捕获其他异常发送 `terminal.error` 并退出
  - 使用 `asyncio.Event` 作为停止信号
- **验收**: 启动后能收到 unsolicited 数据，停止后不再收到

### TASK-BE-004: 注册路由到 main.py
- **文件**: `backend/app/main.py`
- **内容**:
  - 添加 `from app.api import terminal_ws`
  - 添加 `app.include_router(terminal_ws.router)`
- **验收**: 启动应用后 `/ws/terminal/{device_id}` 可访问

### TASK-BE-005: 添加设备状态变更推送
- **文件**: `backend/app/api/terminal_ws.py` + `backend/app/api/websocket.py`
- **内容**:
  - 当设备断开连接时，通过现有 `broadcast_device_update()` 通知所有终端 WebSocket
  - 终端 WebSocket 收到后发送 `terminal.disconnected` 给客户端
  - 客户端可据此关闭对应 Tab 或显示断开提示
- **验收**: 设备断开后，已打开的终端 Tab 收到断开通知

---

## WuKong (前端开发) 任务

### TASK-FE-001: 创建终端状态管理 Store
- **文件**: `frontend/src/stores/terminalStore.ts` (新建)
- **内容**:
  - Zustand store: `useTerminalStore`
  - State: `tabs: TerminalTab[]`, `activeTabId: string | null`
  - Actions: `openTerminal`, `closeTerminal`, `setActiveTab`, `addMessage`, `clearMessages`, `setReceiving`
  - Types 定义在 `frontend/src/types/index.ts` 中补充: `TerminalTab`, `TerminalMessage`
- **验收**: Store 可导入，actions 可调用，状态变更正确

### TASK-FE-002: 创建 WebSocket Hook
- **文件**: `frontend/src/hooks/useTerminalWebSocket.ts` (新建)
- **内容**:
  - `function useTerminalWebSocket(deviceId: string, tabId: string)`
  - 使用 `useRef` 持有 WebSocket 实例
  - `useEffect` 管理连接生命周期（连接 → 监听 → 断开清理）
  - 自动重连: 断开后指数退避重连（1s, 2s, 4s, 8s, max 30s）
  - `sendCommand(command: string)`: 生成 UUID command_id，发送 `terminal.command`
  - `startReceiving()` / `stopReceiving()`: 控制 unsolicited 数据流
  - 收到消息后 dispatch 到 `terminalStore.addMessage()`
  - 返回: `{ isConnected, sendCommand, startReceiving, stopReceiving }`
- **验收**: Hook 在组件中使用，WebSocket 正常通信

### TASK-FE-003: 创建 DeviceSidebar 组件
- **文件**: `frontend/src/components/terminal/DeviceSidebar.tsx` (新建)
- **内容**:
  - 从 `deviceAPI.list()` 获取设备列表（或从 store 读取）
  - 过滤显示已连接设备（`status === 'connected'`）
  - 每个设备项显示: 状态指示灯（绿色圆点）、名称、协议 Tag
  - 搜索框（按名称过滤）
  - 点击设备 → 调用 `terminalStore.openTerminal(deviceId, deviceName, protocol)`
  - 使用 Ant Design `Card` + `List` 组件
  - 宽度固定 280px
- **验收**: 已连接设备显示在侧边栏，点击可打开终端

### TASK-FE-004: 创建 MessageBubble 组件
- **文件**: `frontend/src/components/terminal/MessageBubble.tsx` (新建)
- **内容**:
  - Props: `message: TerminalMessage`
  - 根据 `direction` 显示不同样式:
    - `sent`: 蓝色左边框，`→` 图标
    - `received`: 绿色左边框，`←` 图标
    - `unsolicited`: 橙色左边框，`⇠` 图标
    - `error`: 红色左边框，`✗` 图标
    - `system`: 灰色左边框，`ℹ` 图标
  - 显示时间戳（格式化为 `HH:mm:ss`）
  - 显示内容（等宽字体 `<pre>` 或 `<code>`）
  - 如果有 `durationMs`，显示耗时标签
- **验收**: 不同方向消息渲染不同样式

### TASK-FE-005: 创建 MessageList 组件
- **文件**: `frontend/src/components/terminal/MessageList.tsx` (新建)
- **内容**:
  - Props: `messages: TerminalMessage[]`
  - 使用 `useRef` + `useEffect` 实现自动滚动到底部
  - 监听 scroll 事件: 用户向上滚动时暂停自动滚动，滚动到底部时恢复
  - 渲染 `MessageBubble` 列表
  - 使用 Ant Design `Typography.Text` 或自定义样式
  - 空状态: "暂无消息，发送命令开始调试"
- **验收**: 消息自动滚动，手动滚动暂停自动滚动

### TASK-FE-006: 创建 CommandInput 组件
- **文件**: `frontend/src/components/terminal/CommandInput.tsx` (新建)
- **内容**:
  - Props: `onSend: (command: string) => void`, `disabled: boolean`
  - Ant Design `Input.TextArea` (1-3 行自适应) + `Button` (发送)
  - Enter 发送，Shift+Enter 换行
  - 命令历史: 本地数组存储最近 100 条，Up/Down 键导航
  - 发送后清空输入框
  - 发送按钮带 `<SendOutlined />` 图标
- **验收**: 输入命令 → Enter 发送 → 输入框清空 → Up 键恢复上一条

### TASK-FE-007: 创建 TerminalWindow 组件
- **文件**: `frontend/src/components/terminal/TerminalWindow.tsx` (新建)
- **内容**:
  - Props: `tab: TerminalTab`
  - 使用 `useTerminalWebSocket(tab.deviceId, tab.id)` hook
  - 顶部工具栏:
    - 设备名称 + 协议 Tag
    - 连接状态指示器 (WebSocket 状态)
    - 接收开关 Toggle (开始/停止 unsolicited 数据)
    - 清空按钮
    - 自动滚动开关
  - 中部: `MessageList` 显示 `tab.messages`
  - 底部: `CommandInput` 发送命令
  - 布局: flex column, MessageList flex-1 填充剩余空间
- **验收**: 完整的终端窗口，可发送命令并看到响应

### TASK-FE-008: 创建 TerminalPage 主页面
- **文件**: `frontend/src/pages/Terminal.tsx` (新建)
- **内容**:
  - 左侧: `DeviceSidebar` (280px 固定宽度)
  - 右侧: Ant Design `Tabs` 组件
    - `type="editable-card"` 支持关闭
    - `hideAdd` 不显示添加按钮（通过侧边栏打开）
    - `activeKey` 绑定 `terminalStore.activeTabId`
    - `onChange` → `terminalStore.setActiveTab`
    - `onEdit` (remove) → `terminalStore.closeTerminal`
    - 每个 Tab 内容为 `TerminalWindow`
  - 空状态: 当没有打开任何 Tab 时，显示引导提示 "从左侧选择一个已连接设备开始调试"
  - Tab 关闭时自动停止该设备的 WebSocket 和 unsolicited 接收
- **验收**: 页面完整渲染，侧边栏 + Tab 布局正常

### TASK-FE-009: 添加路由和导航
- **文件**: `frontend/src/App.tsx` + `frontend/src/components/layout/AppLayout.tsx`
- **内容**:
  - `App.tsx`: 添加 `<Route path="terminal" element={<Terminal />} />`
  - `AppLayout.tsx`: 
    - 导入 `CodeOutlined` from `@ant-design/icons`
    - 在 menuItems 中添加 `{ key: '/terminal', icon: <CodeOutlined />, label: '调试终端' }`
    - 建议放在 "通信日志" 之后
- **验收**: 侧边栏出现"调试终端"菜单项，点击跳转到终端页面

### TASK-FE-010: 补充类型定义
- **文件**: `frontend/src/types/index.ts`
- **内容**: 添加以下类型
```typescript
export interface TerminalTab {
  id: string
  deviceId: string
  deviceName: string
  protocol: string
  messages: TerminalMessage[]
  isReceiving: boolean
}

export interface TerminalMessage {
  id: string
  direction: 'sent' | 'received' | 'unsolicited' | 'error' | 'system'
  content: string
  timestamp: string
  commandId?: string
  durationMs?: number
}
```
- **验收**: 类型可导入使用

---

## WuJin (测试) 任务

### TASK-TEST-001: 后端 WebSocket 单元测试
- **文件**: `backend/tests/test_terminal_ws.py` (新建)
- **测试用例**:
  1. `test_connect_to_connected_device` — 连接已连接设备，验证 `terminal.ready`
  2. `test_connect_to_disconnected_device` — 连接未连接设备，验证错误消息
  3. `test_connect_to_nonexistent_device` — 连接不存在的设备，验证错误
  4. `test_send_command_and_receive_response` — 发送命令，验证响应格式
  5. `test_send_command_to_disconnected` — 对断开设备发命令，验证错误
  6. `test_start_stop_receive` — 启动/停止 unsolicited 轮询
  7. `test_unsolicited_data_received` — 验证 unsolicited 消息格式
  8. `test_ping_pong` — 验证心跳机制
  9. `test_multiple_concurrent_connections` — 3 个并发连接
  10. `test_disconnect_cleanup` — 断开后资源清理
- **工具**: `pytest` + `httpx` (支持 WebSocket 测试的 `AsyncClient`)
- **Mock**: 使用 `MockInterface` 避免需要真实硬件

### TASK-TEST-002: `send_command_raw()` 单元测试
- **文件**: `backend/tests/test_device_service.py` (新建或追加)
- **测试用例**:
  1. `test_send_command_raw_success` — 正常发送命令，验证返回格式
  2. `test_send_command_raw_device_not_connected` — 设备未连接时抛异常
  3. `test_send_command_raw_nonexistent_device` — 设备不存在时抛异常

### TASK-TEST-003: 前端组件单元测试
- **文件**: `frontend/src/components/terminal/__tests__/` (新建)
- **测试用例**:
  1. `MessageBubble.test.tsx` — 各方向消息渲染测试（快照测试）
  2. `CommandInput.test.tsx` — 输入、发送、历史导航测试
  3. `DeviceSidebar.test.tsx` — 设备列表渲染、搜索过滤、点击事件
- **工具**: `vitest` + `@testing-library/react`

### TASK-TEST-004: 前端集成测试
- **文件**: `frontend/src/pages/__tests__/Terminal.test.tsx` (新建)
- **测试用例**:
  1. 页面渲染: 侧边栏 + 空状态提示
  2. 点击设备 → 打开 Tab
  3. 关闭 Tab
  4. 发送命令 → 消息列表更新
  5. 清空消息
- **Mock**: 使用 `msw` mock WebSocket

### TASK-TEST-005: 端到端手动测试清单
- **文件**: `TEST_CHECKLIST_TERMINAL.md` (新建)
- **清单内容**:
  1. [ ] 启动后端和前端
  2. [ ] 创建一个 Mock 设备（protocol=mock）
  3. [ ] 连接设备
  4. [ ] 导航到调试终端页面
  5. [ ] 验证设备出现在侧边栏
  6. [ ] 点击设备 → 打开终端 Tab
  7. [ ] 输入命令 `*IDN?` → 发送 → 看到响应
  8. [ ] 开启 unsolicited 接收 → 看到定时数据
  9. [ ] 打开第二个设备终端 → 两个 Tab 独立工作
  10. [ ] 关闭一个 Tab → 另一个不受影响
  11. [ ] 断开设备 → 终端显示断开提示
  12. [ ] 刷新页面 → 终端状态丢失（预期行为）
  13. [ ] 测试不同协议: SCPI, CAN, Serial（Mock）

---

## 依赖关系和执行顺序

```
Phase 1 (并行):
  Arch: TASK-ARCH-001, TASK-ARCH-002  (审核设计)
  BaJie: TASK-BE-001 (send_command_raw)
  WuKong: TASK-FE-010 (类型定义), TASK-FE-001 (Store)

Phase 2 (BE 先行):
  BaJie: TASK-BE-002, TASK-BE-003, TASK-BE-004 (WebSocket 端点)
  WuJin: TASK-TEST-002 (send_command_raw 测试)

Phase 3 (FE 开发, 依赖 BE 完成):
  WuKong: TASK-FE-002 → TASK-FE-003, TASK-FE-004, TASK-FE-005, TASK-FE-006
          → TASK-FE-007 → TASK-FE-008 → TASK-FE-009

Phase 4 (测试):
  WuJin: TASK-TEST-001 (依赖 BE Phase 2)
         TASK-TEST-003, TASK-TEST-004 (依赖 FE Phase 3)
         TASK-TEST-005 (端到端, 依赖全部完成)

Phase 5 (收尾):
  Arch: TASK-ARCH-003, TASK-ARCH-004 (最终审核)
  BaJie: TASK-BE-005 (状态推送, 可选增强)
```

---

## 风险提示

1. **WebSocket 与 AsyncSession**: `send_command_raw()` 不依赖 DB session，避免了 WebSocket 中管理 DB 会话的复杂性。但如果未来需要在终端中记录日志，需要设计一个异步队列写入方案。

2. **轮询效率**: 后台 `receive()` 轮询使用 0.3s 超时，每个终端一个后台任务。如果同时打开 20+ 个终端，会有 20+ 个协程。这在 asyncio 中是可接受的（协程轻量），但需注意 `receive()` 内部是否使用了 `asyncio.to_thread()`（SCPI/Serial 会），可能消耗线程池资源。

3. **前端 WebSocket 重连**: 浏览器可能同时打开多个 Tab 终端，每个都维护独立 WebSocket。需确保重连退避不会导致连接风暴。

4. **Mock 测试覆盖**: 集成测试只能覆盖 Mock 协议。真实硬件（SCPI via PyVISA, CAN via python-can）的行为差异需要在手动测试中覆盖。
