# Multi-Window Communication Debug Terminal — Full Design Specification

## 1. Backend API Design

### 1.1 New WebSocket Endpoint: `/ws/terminal/{device_id}`

Replace the existing skeletal `/ws/devices/{device_id}` with a proper terminal WebSocket.

#### Connection Flow
```
Client  ──connect──>  /ws/terminal/{device_id}
Server  ──accept──>   {"type": "terminal.ready", "device_id": "...", "protocol": "scpi", "status": "connected"}
```

#### Client → Server Messages

| type | payload | description |
|------|---------|-------------|
| `terminal.command` | `{command: string, command_id: string}` | Send a raw command to the device |
| `terminal.ping` | `{}` | Keepalive |
| `terminal.start_receive` | `{interval_ms?: number}` | Start unsolicited data polling |
| `terminal.stop_receive` | `{}` | Stop unsolicited data polling |

#### Server → Client Messages

| type | payload | description |
|------|---------|-------------|
| `terminal.ready` | `{device_id, protocol, status}` | Connection established |
| `terminal.response` | `{command_id, command, response, duration_ms, timestamp}` | Command response |
| `terminal.error` | `{command_id?, command?, error, timestamp}` | Error from command or system |
| `terminal.unsolicited` | `{data, timestamp}` | Unsolicited data from device (polling result) |
| `terminal.disconnected` | `{reason}` | Device physically disconnected |
| `terminal.pong` | `{}` | Keepalive response |

#### Timestamp Format
All timestamps are ISO 8601 strings in UTC: `"2025-01-15T10:30:45.123Z"`

### 1.2 Unsolicited Data Mechanism

Since `CommunicationInterface.receive()` is blocking/sync-style, we implement a **background polling task** per WebSocket connection:

```
WebSocket connect
  └── spawn asyncio background task: _unsolicited_reader(device_id, websocket, interval=0.5)
        └── while not stopped:
              try:
                data = await interface.receive(timeout=0.5)
                if data:
                  await ws.send_json({"type": "terminal.unsolicited", ...})
              except Timeout:
                pass
              except Exception:
                break
```

The polling task is controlled by `terminal.start_receive` / `terminal.stop_receive` messages from the client. The task is also cancelled on WebSocket disconnect.

### 1.3 WebSocket Implementation (backend/app/api/terminal_ws.py)

New file. Key design:

```python
# Connection tracking
_terminal_sessions: Dict[str, Dict] = {}  # websocket_id -> {device_id, ws, poll_task}

@router.websocket("/ws/terminal/{device_id}")
async def terminal_websocket(websocket: WebSocket, device_id: str):
    await websocket.accept()
    
    # Verify device exists and is connected
    interface = _active_connections.get(device_id)
    if not interface:
        await websocket.send_json({"type": "terminal.error", "error": "Device not connected"})
        await websocket.close()
        return
    
    # Send ready
    await websocket.send_json({
        "type": "terminal.ready",
        "device_id": device_id,
        "protocol": ...,  # from device record
        "status": "connected",
    })
    
    poll_task = None
    session_id = str(uuid4())
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")
            
            if msg_type == "terminal.command":
                # Execute command via device_service.send_command()
                # Need a DB session here — use async context manager
                ...
            elif msg_type == "terminal.start_receive":
                if poll_task is None:
                    poll_task = asyncio.create_task(_poll_unsolicited(...))
            elif msg_type == "terminal.stop_receive":
                if poll_task:
                    poll_task.cancel()
                    poll_task = None
            elif msg_type == "terminal.ping":
                await websocket.send_json({"type": "terminal.pong"})
    except WebSocketDisconnect:
        ...
    finally:
        if poll_task:
            poll_task.cancel()
```

### 1.4 Need: DB-Agnostic Command Execution

The current `device_service.send_command()` requires `db: AsyncSession`. For the WebSocket, we need to either:
- **Option A**: Create a new `send_command_raw()` method that skips DB logging (simpler, pure terminal)
- **Option B**: Pass a DB session through the WebSocket context

**Recommendation: Option A** — the terminal is for debugging, not for persisted test execution. Add to `DeviceService`:

```python
async def send_command_raw(self, device_id: str, command: str) -> dict:
    """Send command without DB logging (for debug terminal)."""
    interface = _active_connections.get(device_id)
    if not interface:
        raise ValueError(f"Device {device_id} is not connected")
    
    start = datetime.utcnow()
    response = await interface.send(command)
    duration_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
    
    return {
        "device_id": device_id,
        "command": command,
        "response": response,
        "duration_ms": duration_ms,
    }
```

### 1.5 API Response Format

All responses follow existing `{code, message, data}` convention. No new REST endpoints needed — all real-time communication goes through WebSocket.

---

## 2. Frontend Design

### 2.1 Route & Navigation

- **Route**: `/terminal` — new top-level route
- **Nav item**: "调试终端" with `<CodeOutlined />` icon, placed after "通信日志" in `AppLayout.tsx`

### 2.2 Component Tree

```
TerminalPage                          (new: pages/Terminal.tsx)
├── DeviceSidebar                     (new: components/terminal/DeviceSidebar.tsx)
│   ├── Search input (filter devices)
│   ├── Device list (connected devices with status indicator)
│   └── Each item: name, protocol tag, status dot, click → open terminal
├── TerminalTabs                      (new: components/terminal/TerminalTabs.tsx)
│   └── TerminalTab[] (Ant Design Tabs with closeable tabs)
│       └── TerminalWindow            (new: components/terminal/TerminalWindow.tsx)
│           ├── Toolbar: device info, protocol, clear, toggle autoscroll
│           ├── MessageList           (new: components/terminal/MessageList.tsx)
│           │   └── MessageBubble[]   (new: components/terminal/MessageBubble.tsx)
│           │       ├── Direction indicator (→ sent, ← received, ⇠ unsolicited)
│           │       ├── Timestamp
│           │       ├── Content (monospace, syntax-highlighted)
│           │       └── Duration badge (for command-response pairs)
│           └── CommandInput          (new: components/terminal/CommandInput.tsx)
│               ├── TextArea or Input (Ant Design)
│               ├── Send button
│               ├── Enter to send, Shift+Enter for newline
│               └── Command history (up/down arrow)
```

### 2.3 State Management

New Zustand slice (add to `useStore.ts` or create separate `terminalStore.ts`):

```typescript
interface TerminalTab {
  id: string          // unique tab id
  deviceId: string    // which device this terminal is for
  deviceName: string
  protocol: string
  messages: TerminalMessage[]
  isReceiving: boolean // unsolicited data polling active
}

interface TerminalMessage {
  id: string
  direction: 'sent' | 'received' | 'unsolicited' | 'error' | 'system'
  content: string
  timestamp: string    // ISO 8601
  commandId?: string   // links sent command to its response
  durationMs?: number
}

interface TerminalState {
  tabs: TerminalTab[]
  activeTabId: string | null
  openTerminal: (deviceId: string, deviceName: string, protocol: string) => void
  closeTerminal: (tabId: string) => void
  setActiveTab: (tabId: string) => void
  addMessage: (tabId: string, message: TerminalMessage) => void
  clearMessages: (tabId: string) => void
  setReceiving: (tabId: string, receiving: boolean) => void
}
```

### 2.4 WebSocket Hook: `useTerminalWebSocket`

```typescript
function useTerminalWebSocket(deviceId: string, tabId: string) {
  // Opens WebSocket to ws://localhost:8000/ws/terminal/{deviceId}
  // Manages: connect, disconnect, sendCommand, startReceive, stopReceive
  // Auto-reconnect on disconnect with backoff
  // Dispatches incoming messages to terminalStore.addMessage()
  
  return {
    isConnected: boolean,
    sendCommand: (command: string) => void,
    startReceiving: () => void,
    stopReceiving: () => void,
  }
}
```

### 2.5 Layout (Responsive)

```
┌──────────────────────────────────────────────────────┐
│  [Sidebar: 280px]  │  [Terminal Area: flex-1]        │
│                    │  ┌─────────────────────────────┐ │
│  🔍 Search...      │  │ Tabs: [DeviceA ×][DeviceB ×]│ │
│  ────────────────  │  ├─────────────────────────────┤ │
│  ● Oscilloscope    │  │ Toolbar: [info] [clear] [↓] │ │
│    SCPI  USB       │  ├─────────────────────────────┤ │
│  ● Power Supply    │  │                             │ │
│    SCPI  Ethernet  │  │  → 10:30:45  *IDN?          │ │
│  ○ Multimeter      │  │  ← 10:30:45  Keysight...    │ │
│    Serial COM3     │  │     (23ms)                   │ │
│                    │  │  ⇠ 10:30:50  [unsolicited]  │ │
│                    │  │                             │ │
│                    │  ├─────────────────────────────┤ │
│                    │  │ [________________] [Send]   │ │
│                    │  └─────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

### 2.6 Key UX Behaviors

1. **Device Sidebar**: Only shows devices with `status === 'connected'`. Grey out disconnected devices at bottom.
2. **Tab Management**: Clicking a device opens a new tab if not already open, or focuses existing tab.
3. **Unsolicited Data**: When a tab is active, the client sends `terminal.start_receive`. When switching away, it sends `terminal.stop_receive` (to save resources).
4. **Command History**: Per-tab, stored in memory (last 100 commands), navigable with Up/Down arrow keys.
5. **Auto-scroll**: On by default. Disabled when user scrolls up. Re-enabled when user scrolls to bottom or clicks "scroll to bottom" button.
6. **Clear**: Clears the message list for the current tab.
7. **Disconnect handling**: If the WebSocket drops, show a banner "Connection lost. Reconnecting..." with exponential backoff.

---

## 3. File Changes Summary

### Backend (Python FastAPI)

| File | Action | Description |
|------|--------|-------------|
| `backend/app/api/terminal_ws.py` | **CREATE** | New WebSocket endpoint for terminal |
| `backend/app/services/device_service.py` | **MODIFY** | Add `send_command_raw()` method |
| `backend/app/main.py` | **MODIFY** | Register terminal_ws router |
| `backend/app/schemas/schemas.py` | **MODIFY** | Add WebSocket message schemas (optional, for documentation) |

### Frontend (React + TypeScript + Ant Design)

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/pages/Terminal.tsx` | **CREATE** | Main terminal page |
| `frontend/src/components/terminal/DeviceSidebar.tsx` | **CREATE** | Connected device list sidebar |
| `frontend/src/components/terminal/TerminalWindow.tsx` | **CREATE** | Single terminal window (tab content) |
| `frontend/src/components/terminal/MessageList.tsx` | **CREATE** | Scrollable message log |
| `frontend/src/components/terminal/MessageBubble.tsx` | **CREATE** | Individual message display |
| `frontend/src/components/terminal/CommandInput.tsx` | **CREATE** | Command input with history |
| `frontend/src/hooks/useTerminalWebSocket.ts` | **CREATE** | WebSocket connection hook |
| `frontend/src/stores/terminalStore.ts` | **CREATE** | Terminal state management |
| `frontend/src/App.tsx` | **MODIFY** | Add `/terminal` route |
| `frontend/src/components/layout/AppLayout.tsx` | **MODIFY** | Add nav item |
| `frontend/src/services/api.ts` | **MODIFY** | Add terminal API helpers (optional REST fallback) |

---

## 4. Message Format Reference (Contract)

### WebSocket Message Envelope

```json
{
  "type": "terminal.command",
  "command": "*IDN?",
  "command_id": "uuid-here"
}
```

### Response

```json
{
  "type": "terminal.response",
  "command_id": "uuid-here",
  "command": "*IDN?",
  "response": "Keysight Technologies,34465A,MY59001001,3.0.0",
  "duration_ms": 23,
  "timestamp": "2025-01-15T10:30:45.123Z"
}
```

### Unsolicited Data

```json
{
  "type": "terminal.unsolicited",
  "data": "+1.234E-03",
  "timestamp": "2025-01-15T10:30:50.456Z"
}
```

### Error

```json
{
  "type": "terminal.error",
  "command_id": "uuid-here",
  "command": "*BAD?",
  "error": "Device returned error: -113 Undefined header",
  "timestamp": "2025-01-15T10:30:46.789Z"
}
```

---

## 5. Testing Strategy (WuJin)

### 5.1 Backend Tests (`tests/test_terminal_ws.py`)

1. **WebSocket connection**: Connect to `/ws/terminal/{device_id}`, verify `terminal.ready` response
2. **Command execution**: Send `terminal.command`, verify `terminal.response` with correct data
3. **Error handling**: Send command to disconnected device, verify error message
4. **Unsolicited polling**: Send `terminal.start_receive`, verify `terminal.unsolicited` messages arrive
5. **Polling stop**: Send `terminal.stop_receive`, verify no more unsolicited messages
6. **Disconnect cleanup**: Disconnect WebSocket, verify background tasks are cancelled
7. **Multiple concurrent terminals**: Open 3 WebSocket connections to different devices simultaneously

### 5.2 Frontend Tests

1. **Sidebar rendering**: Verify connected devices appear in sidebar
2. **Tab open/close**: Click device → tab opens, close tab → tab removed
3. **Command send**: Type command, click send → message appears in log
4. **Response display**: Verify response appears with timestamp and duration
5. **Unsolicited data**: Enable receiving → verify unsolicited messages appear
6. **Command history**: Press Up arrow → previous command appears in input
7. **Auto-scroll toggle**: Scroll up → auto-scroll disables, scroll to bottom → re-enables

### 5.3 Integration Tests

1. End-to-end: Create device → connect → open terminal → send command → receive response
2. Multi-tab: Open 3 terminals simultaneously, verify each works independently
3. Reconnection: Kill WebSocket → verify UI shows reconnecting → restore → verify recovery
