# AITestLab API 契约文档

## 基础信息

- **Base URL**: `http://localhost:8000/api`
- **WebSocket Base**: `ws://localhost:8000/ws`
- **Content-Type**: `application/json`（除文件上传外）
- **认证方式**: Bearer Token（Phase 1 预留，暂不强制）

---

## 通用规范

### 通用响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 分页请求

```json
{
  "page": 1,
  "page_size": 20
}
```

### 分页响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

### 错误响应

```json
{
  "code": 40001,
  "message": "Device not found",
  "detail": "No device with id=xxx"
}
```

---

## 1. 设备管理 API

### 1.1 获取设备列表

```
GET /api/devices?page=1&page_size=20&status=connected&type=oscilloscope
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "dev_001",
        "name": "DSO-X 3034A",
        "type": "oscilloscope",
        "protocol": "scpi",
        "connection_type": "usb",
        "visa_address": "USB0::0x2A8D::0x0396::MY59012345::INSTR",
        "status": "connected",
        "connected_at": "2025-01-15T10:30:00Z",
        "config": {
          "timeout": 5000,
          "baud_rate": null
        },
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-15T10:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 1.2 获取设备详情

```
GET /api/devices/{id}
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "dev_001",
    "name": "DSO-X 3034A",
    "type": "oscilloscope",
    "protocol": "scpi",
    "connection_type": "usb",
    "visa_address": "USB0::0x2A8D::0x0396::MY59012345::INSTR",
    "status": "connected",
    "connected_at": "2025-01-15T10:30:00Z",
    "config": {
      "timeout": 5000,
      "baud_rate": null
    },
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  }
}
```

### 1.3 连接设备

```
POST /api/devices/connect
```

**Request:**
```json
{
  "name": "DSO-X 3034A",
  "type": "oscilloscope",
  "protocol": "scpi",
  "connection_type": "usb",
  "visa_address": "USB0::0x2A8D::0x0396::MY59012345::INSTR",
  "config": {
    "timeout": 5000
  }
}
```

**Response:**
```json
{
  "code": 0,
  "message": "Device connected successfully",
  "data": {
    "id": "dev_001",
    "name": "DSO-X 3034A",
    "type": "oscilloscope",
    "status": "connected",
    "connected_at": "2025-01-15T10:30:00Z"
  }
}
```

### 1.4 断开设备

```
DELETE /api/devices/{id}/disconnect
```

**Response:**
```json
{
  "code": 0,
  "message": "Device disconnected successfully",
  "data": null
}
```

### 1.5 获取设备状态

```
GET /api/devices/{id}/status
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": "dev_001",
    "status": "connected",
    "last_seen": "2025-01-15T10:35:00Z",
    "metrics": {
      "bytes_sent": 10240,
      "bytes_received": 20480,
      "uptime_seconds": 300
    }
  }
}
```

### 1.6 发送设备指令

```
POST /api/devices/{id}/command
```

**Request:**
```json
{
  "command": "*IDN?",
  "timeout": 5000
}
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "command": "*IDN?",
    "response": "Keysight Technologies,DSO-X 3034A,MY59012345,07.40.2021031101",
    "duration_ms": 42
  }
}
```

### 1.7 更新设备配置

```
PUT /api/devices/{id}
```

**Request:**
```json
{
  "name": "My Oscilloscope",
  "config": {
    "timeout": 10000
  }
}
```

**Response:** 同 1.2

### 1.8 删除设备记录

```
DELETE /api/devices/{id}
```

**Response:**
```json
{
  "code": 0,
  "message": "Device deleted successfully",
  "data": null
}
```

---

## 2. 测试用例 API

### 2.1 AI 生成测试用例

```
POST /api/testcases/generate
```

**Request:**
```json
{
  "requirement": "测试 DCDC 转换器在 12V 输入、5V 输出、2A 负载下的效率和纹波",
  "input_type": "text",
  "model_id": "model_001",
  "devices": ["dev_001", "dev_002"],
  "template_id": null
}
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "test_case": {
      "id": "tc_001",
      "name": "DCDC 12V→5V 效率纹波测试",
      "description": "测试 DCDC 转换器在 12V 输入、5V 输出、2A 负载下的效率和纹波",
      "status": "draft",
      "created_at": "2025-01-15T11:00:00Z"
    },
    "flow": {
      "id": "flow_001",
      "nodes": [
        {
          "id": "node_1",
          "type": "start",
          "label": "开始",
          "position": { "x": 100, "y": 50 },
          "config": {}
        },
        {
          "id": "node_2",
          "type": "test_step",
          "label": "设置电源输出 12V",
          "position": { "x": 100, "y": 150 },
          "config": {
            "device_id": "dev_001",
            "command": "VOLT 12",
            "expected": "12.0 ± 0.1V"
          }
        },
        {
          "id": "node_3",
          "type": "test_step",
          "label": "设置电子负载 2A",
          "position": { "x": 100, "y": 250 },
          "config": {
            "device_id": "dev_002",
            "command": "CURR 2",
            "expected": "2.0 ± 0.05A"
          }
        },
        {
          "id": "node_4",
          "type": "test_step",
          "label": "测量输出电压",
          "position": { "x": 100, "y": 350 },
          "config": {
            "device_id": "dev_003",
            "command": "MEAS:VOLT:DC?",
            "expected": "5.0 ± 0.25V"
          }
        },
        {
          "id": "node_5",
          "type": "test_step",
          "label": "测量输出纹波",
          "position": { "x": 100, "y": 450 },
          "config": {
            "device_id": "dev_003",
            "command": "MEAS:VRMS?",
            "expected": "< 50mV"
          }
        },
        {
          "id": "node_6",
          "type": "end",
          "label": "结束",
          "position": { "x": 100, "y": 550 },
          "config": {}
        }
      ],
      "edges": [
        { "id": "e1", "source": "node_1", "target": "node_2" },
        { "id": "e2", "source": "node_2", "target": "node_3" },
        { "id": "e3", "source": "node_3", "target": "node_4" },
        { "id": "e4", "source": "node_4", "target": "node_5" },
        { "id": "e5", "source": "node_5", "target": "node_6" }
      ]
    }
  }
}
```

### 2.2 获取测试用例列表

```
GET /api/testcases?page=1&page_size=20&status=draft&search=DCDC
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "tc_001",
        "name": "DCDC 12V→5V 效率纹波测试",
        "description": "测试 DCDC 转换器...",
        "status": "draft",
        "flow_id": "flow_001",
        "created_at": "2025-01-15T11:00:00Z",
        "updated_at": "2025-01-15T11:00:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 2.3 获取测试用例详情

```
GET /api/testcases/{id}
```

**Response:** 包含 test_case + flow 完整数据，格式同 2.1 的 data 字段。

### 2.4 更新测试用例

```
PUT /api/testcases/{id}
```

**Request:**
```json
{
  "name": "更新后的名称",
  "description": "更新后的描述",
  "flow": {
    "nodes": [...],
    "edges": [...]
  }
}
```

**Response:** 同 2.3

### 2.5 删除测试用例

```
DELETE /api/testcases/{id}
```

**Response:**
```json
{
  "code": 0,
  "message": "Test case deleted successfully",
  "data": null
}
```

### 2.6 更新流程图

```
PUT /api/testcases/{id}/flow
```

**Request:**
```json
{
  "nodes": [
    {
      "id": "node_1",
      "type": "start",
      "label": "开始",
      "position": { "x": 100, "y": 50 },
      "config": {}
    }
  ],
  "edges": [
    { "id": "e1", "source": "node_1", "target": "node_2" }
  ]
}
```

**Response:**
```json
{
  "code": 0,
  "message": "Flow updated successfully",
  "data": {
    "flow_id": "flow_001",
    "updated_at": "2025-01-15T12:00:00Z"
  }
}
```

---

## 3. 测试执行 API

### 3.1 启动测试执行

```
POST /api/executions/run
```

**Request:**
```json
{
  "testcase_id": "tc_001",
  "options": {
    "stop_on_error": true,
    "timeout_per_step": 30000,
    "parallel_devices": false
  }
}
```

**Response:**
```json
{
  "code": 0,
  "message": "Execution started",
  "data": {
    "execution_id": "exec_001",
    "testcase_id": "tc_001",
    "status": "running",
    "started_at": "2025-01-15T13:00:00Z",
    "total_steps": 5,
    "completed_steps": 0
  }
}
```

### 3.2 获取执行状态

```
GET /api/executions/{id}/status
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "execution_id": "exec_001",
    "testcase_id": "tc_001",
    "status": "running",
    "started_at": "2025-01-15T13:00:00Z",
    "total_steps": 5,
    "completed_steps": 2,
    "current_step": {
      "step_index": 3,
      "node_id": "node_4",
      "label": "测量输出电压",
      "started_at": "2025-01-15T13:02:00Z"
    },
    "results": [
      {
        "step_index": 1,
        "node_id": "node_2",
        "label": "设置电源输出 12V",
        "status": "passed",
        "actual": "12.01V",
        "duration_ms": 150
      },
      {
        "step_index": 2,
        "node_id": "node_3",
        "label": "设置电子负载 2A",
        "status": "passed",
        "actual": "2.01A",
        "duration_ms": 200
      }
    ]
  }
}
```

### 3.3 停止测试执行

```
POST /api/executions/{id}/stop
```

**Response:**
```json
{
  "code": 0,
  "message": "Execution stopped",
  "data": {
    "execution_id": "exec_001",
    "status": "stopped",
    "stopped_at": "2025-01-15T13:05:00Z"
  }
}
```

### 3.4 获取执行历史

```
GET /api/executions?page=1&page_size=20&testcase_id=tc_001&status=completed
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "execution_id": "exec_001",
        "testcase_id": "tc_001",
        "testcase_name": "DCDC 12V→5V 效率纹波测试",
        "status": "completed",
        "result": "passed",
        "started_at": "2025-01-15T13:00:00Z",
        "completed_at": "2025-01-15T13:05:00Z",
        "duration_ms": 300000,
        "total_steps": 5,
        "passed_steps": 5,
        "failed_steps": 0
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 3.5 获取执行详情

```
GET /api/executions/{id}
```

**Response:** 包含完整执行记录和所有步骤结果。

---

## 4. AI 模型配置 API

### 4.1 配置 AI 模型

```
POST /api/ai/config
```

**Request:**
```json
{
  "name": "GPT-4o",
  "provider": "openai",
  "model_name": "gpt-4o",
  "api_key": "sk-...",
  "base_url": "https://api.openai.com/v1",
  "parameters": {
    "temperature": 0.7,
    "max_tokens": 4096
  },
  "is_default": true
}
```

**Response:**
```json
{
  "code": 0,
  "message": "Model configured successfully",
  "data": {
    "id": "model_001",
    "name": "GPT-4o",
    "provider": "openai",
    "model_name": "gpt-4o",
    "is_default": true,
    "status": "active",
    "created_at": "2025-01-15T10:00:00Z"
  }
}
```

### 4.2 获取 AI 模型列表

```
GET /api/ai/models
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "model_001",
        "name": "GPT-4o",
        "provider": "openai",
        "model_name": "gpt-4o",
        "is_default": true,
        "status": "active",
        "created_at": "2025-01-15T10:00:00Z"
      },
      {
        "id": "model_002",
        "name": "Local Llama3",
        "provider": "ollama",
        "model_name": "llama3:8b",
        "base_url": "http://localhost:11434",
        "is_default": false,
        "status": "active",
        "created_at": "2025-01-15T10:05:00Z"
      }
    ]
  }
}
```

### 4.3 更新 AI 模型配置

```
PUT /api/ai/config/{id}
```

**Request:** 同 4.1，所有字段可选。

### 4.4 删除 AI 模型配置

```
DELETE /api/ai/config/{id}
```

### 4.5 测试 AI 模型连接

```
POST /api/ai/models/{id}/test
```

**Request:**
```json
{
  "message": "Hello, this is a test."
}
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "response": "Hello! I'm ready to help.",
    "latency_ms": 1200,
    "tokens_used": 15
  }
}
```

### 4.6 AI 对话

```
POST /api/ai/chat
```

**Request:**
```json
{
  "model_id": "model_001",
  "messages": [
    { "role": "system", "content": "你是一个硬件测试工程师助手" },
    { "role": "user", "content": "如何测试DCDC转换器的效率？" }
  ],
  "stream": false,
  "parameters": {
    "temperature": 0.7
  }
}
```

**Response (non-stream):**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "response": "测试DCDC转换器效率需要...",
    "tokens_used": { "prompt": 50, "completion": 200, "total": 250 },
    "model": "gpt-4o",
    "finished_at": "2025-01-15T14:00:00Z"
  }
}
```

**Response (stream):** SSE 格式
```
data: {"type": "token", "content": "测试"}
data: {"type": "token", "content": "DCDC"}
...
data: {"type": "done", "tokens_used": {...}}
```

---

## 5. 语音识别 API

### 5.1 语音转文字

```
POST /api/speech/transcribe
```

**Request:** `multipart/form-data`
```
audio: <binary audio file>
language: "zh" | "en" (optional, auto-detect)
model: "whisper-1" (optional)
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "text": "测试DCDC转换器在12伏输入5伏输出2安负载下的效率",
    "language": "zh",
    "duration_seconds": 4.5,
    "segments": [
      {
        "start": 0.0,
        "end": 4.5,
        "text": "测试DCDC转换器在12伏输入5伏输出2安负载下的效率"
      }
    ]
  }
}
```

---

## 6. 日志与查询 API

### 6.1 获取通信日志

```
GET /api/logs?page=1&page_size=50&device_id=dev_001&execution_id=exec_001&start_time=2025-01-01&end_time=2025-01-31&direction=sent
```

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| page | int | 否 | 页码 |
| page_size | int | 否 | 每页数量 |
| device_id | string | 否 | 设备 ID 筛选 |
| execution_id | string | 否 | 执行 ID 筛选 |
| start_time | datetime | 否 | 开始时间 |
| end_time | datetime | 否 | 结束时间 |
| direction | string | 否 | sent/received |
| status | string | 否 | success/error/timeout |

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "log_001",
        "timestamp": "2025-01-15T13:00:01.123Z",
        "device_id": "dev_001",
        "device_name": "DSO-X 3034A",
        "execution_id": "exec_001",
        "direction": "sent",
        "raw_data": "*IDN?\n",
        "raw_data_hex": "2a49444e3f0a",
        "protocol": "scpi",
        "status": "success",
        "duration_ms": 42,
        "response_log_id": "log_002"
      },
      {
        "id": "log_002",
        "timestamp": "2025-01-15T13:00:01.165Z",
        "device_id": "dev_001",
        "device_name": "DSO-X 3034A",
        "execution_id": "exec_001",
        "direction": "received",
        "raw_data": "Keysight Technologies,DSO-X 3034A,MY59012345,07.40\n",
        "raw_data_hex": "4b6579736967687420546563686e6f6c6f676965732c44534f2d582033303334412c...",
        "protocol": "scpi",
        "status": "success",
        "duration_ms": 42,
        "response_log_id": null
      }
    ],
    "total": 200,
    "page": 1,
    "page_size": 50
  }
}
```

### 6.2 获取单条日志详情

```
GET /api/logs/{id}
```

### 6.3 导出日志

```
GET /api/logs/export?format=csv&device_id=dev_001&start_time=2025-01-01&end_time=2025-01-31
```

**Response:** 文件下载（CSV 格式）

### 6.4 自然语言查询

```
POST /api/query/natural-language
```

**Request:**
```json
{
  "query": "上周执行的测试中，有多少个通过了？",
  "model_id": "model_001"
}
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "query": "上周执行的测试中，有多少个通过了？",
    "sql": "SELECT COUNT(*) as count FROM test_executions WHERE status='completed' AND result='passed' AND completed_at >= datetime('now', '-7 days')",
    "results": [
      { "count": 15 }
    ],
    "explanation": "上周共有15个测试执行通过。",
    "execution_time_ms": 3200
  }
}
```

### 6.5 语音查询

```
POST /api/query/speech
```

**Request:** `multipart/form-data`
```
audio: <binary audio file>
model_id: "model_001"
```

**Response:** 同 6.4

---

## 7. 报告 API

### 7.1 生成测试报告

```
POST /api/reports/generate
```

**Request:**
```json
{
  "execution_id": "exec_001",
  "template_id": "tpl_001",
  "format": "pdf",
  "fields": {
    "title": "DCDC 转换器测试报告",
    "author": "张三",
    "conclusion": "所有测试项通过，效率达到 92%，纹波 < 30mV",
    "custom_fields": {
      "environment_temp": "25°C",
      "humidity": "45%"
    }
  }
}
```

**Response:**
```json
{
  "code": 0,
  "message": "Report generated successfully",
  "data": {
    "report_id": "rpt_001",
    "title": "DCDC 转换器测试报告",
    "format": "pdf",
    "status": "generated",
    "file_url": "/api/reports/rpt_001/download",
    "generated_at": "2025-01-15T14:30:00Z"
  }
}
```

### 7.2 下载报告

```
GET /api/reports/{id}/download
```

**Response:** 文件下载（PDF/HTML/DOCX）

### 7.3 获取报告列表

```
GET /api/reports?page=1&page_size=20
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "rpt_001",
        "title": "DCDC 转换器测试报告",
        "format": "pdf",
        "execution_id": "exec_001",
        "status": "generated",
        "created_at": "2025-01-15T14:30:00Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
}
```

### 7.4 获取报告详情

```
GET /api/reports/{id}
```

### 7.5 获取报告模板列表

```
GET /api/reports/templates
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "tpl_001",
        "name": "标准测试报告",
        "description": "包含测试概要、步骤结果、结论",
        "format": "pdf",
        "is_default": true,
        "created_at": "2025-01-01T00:00:00Z"
      }
    ]
  }
}
```

### 7.6 创建报告模板

```
POST /api/reports/templates
```

**Request:**
```json
{
  "name": "自定义模板",
  "description": "我的自定义报告模板",
  "format": "pdf",
  "content": "<html><body><h1>{{ title }}</h1>...</body></html>",
  "fields_schema": {
    "title": { "type": "string", "required": true },
    "author": { "type": "string", "required": true },
    "conclusion": { "type": "string", "required": false }
  }
}
```

### 7.7 删除报告模板

```
DELETE /api/reports/templates/{id}
```

### 7.8 删除报告

```
DELETE /api/reports/{id}
```

---

## 8. 插件管理 API

### 8.1 获取插件列表

```
GET /api/plugins
```

**Response:**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "plg_001",
        "name": "custom_can_protocol",
        "version": "1.0.0",
        "description": "自定义 CAN 协议解析插件",
        "author": "开发者名",
        "status": "enabled",
        "protocol_type": "can",
        "config_schema": {
          "type": "object",
          "properties": {
            "bitrate": { "type": "integer", "default": 500000 }
          }
        },
        "installed_at": "2025-01-15T10:00:00Z",
        "enabled_at": "2025-01-15T10:05:00Z"
      }
    ]
  }
}
```

### 8.2 安装插件

```
POST /api/plugins/install
```

**Request:** `multipart/form-data`
```
plugin: <binary .py file or .zip package>
```

**Response:**
```json
{
  "code": 0,
  "message": "Plugin installed successfully",
  "data": {
    "id": "plg_001",
    "name": "custom_can_protocol",
    "version": "1.0.0",
    "status": "installed",
    "installed_at": "2025-01-15T10:00:00Z"
  }
}
```

### 8.3 启用插件

```
POST /api/plugins/{id}/enable
```

**Response:**
```json
{
  "code": 0,
  "message": "Plugin enabled successfully",
  "data": {
    "id": "plg_001",
    "status": "enabled",
    "enabled_at": "2025-01-15T10:05:00Z"
  }
}
```

### 8.4 禁用插件

```
POST /api/plugins/{id}/disable
```

**Response:**
```json
{
  "code": 0,
  "message": "Plugin disabled successfully",
  "data": {
    "id": "plg_001",
    "status": "disabled",
    "disabled_at": "2025-01-15T10:10:00Z"
  }
}
```

### 8.5 卸载插件

```
DELETE /api/plugins/{id}
```

---

## 9. WebSocket 端点

### 9.1 执行监控

```
WS /ws/executions/{execution_id}
```

**服务端推送消息类型：**

```json
// 执行开始
{ "type": "execution_started", "data": { "execution_id": "exec_001", "total_steps": 5 } }

// 步骤开始
{ "type": "step_start", "data": { "step_index": 1, "node_id": "node_2", "label": "设置电源输出 12V" } }

// 步骤进度（发送指令/等待响应等）
{ "type": "step_progress", "data": { "step_index": 1, "action": "sending_command", "detail": "*IDN?" } }

// 设备数据推送
{ "type": "device_data", "data": { "device_id": "dev_001", "value": "12.01", "unit": "V", "timestamp": "..." } }

// 步骤完成
{ "type": "step_complete", "data": { "step_index": 1, "status": "passed", "actual": "12.01V", "duration_ms": 150 } }

// 步骤错误
{ "type": "step_error", "data": { "step_index": 2, "error": "Timeout", "detail": "Device did not respond within 5000ms" } }

// 执行完成
{ "type": "execution_complete", "data": { "execution_id": "exec_001", "result": "passed", "duration_ms": 300000 } }

// 执行停止
{ "type": "execution_stopped", "data": { "execution_id": "exec_001" } }

// 心跳
{ "type": "heartbeat", "data": { "timestamp": "..." } }
```

### 9.2 设备实时监控

```
WS /ws/devices/{device_id}/monitor
```

**服务端推送：**
```json
{ "type": "device_data", "data": { "device_id": "dev_001", "metric": "voltage", "value": 12.01, "unit": "V" } }
{ "type": "device_status", "data": { "device_id": "dev_001", "status": "connected", "last_seen": "..." } }
{ "type": "device_error", "data": { "device_id": "dev_001", "error": "Connection lost" } }
```

---

## 10. 错误码定义

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| 0 | 200 | 成功 |
| 40001 | 404 | 资源不存在 |
| 40002 | 400 | 参数验证失败 |
| 40003 | 409 | 资源冲突（如设备已连接） |
| 40004 | 400 | 不支持的操作 |
| 40101 | 401 | 未认证 |
| 40102 | 403 | 无权限 |
| 50001 | 500 | 服务器内部错误 |
| 50002 | 502 | AI 服务调用失败 |
| 50003 | 504 | 设备通信超时 |
| 50004 | 500 | 插件加载失败 |
| 50005 | 500 | 报告生成失败 |
| 50006 | 500 | 语音识别失败 |
| 50007 | 503 | 设备不可达/断开 |
| 50008 | 500 | 测试执行异常 |

### 错误响应示例

```json
{
  "code": 40003,
  "message": "Device already connected",
  "detail": "Device dev_001 is already connected. Disconnect first before reconnecting.",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

---

## 11. 数据模型通用字段

所有 API 响应中的时间字段使用 **ISO 8601 UTC** 格式：
- `"2025-01-15T10:30:00Z"`

所有 ID 字段格式：
- 设备: `dev_<uuid_short>` (如 `dev_a1b2c3d4`)
- 测试用例: `tc_<uuid_short>`
- 流程: `flow_<uuid_short>`
- 执行: `exec_<uuid_short>`
- 日志: `log_<uuid_short>`
- 报告: `rpt_<uuid_short>`
- 模板: `tpl_<uuid_short>`
- AI 模型: `model_<uuid_short>`
- 插件: `plg_<uuid_short>`

所有枚举值：
- 设备类型: `power_supply`, `oscilloscope`, `multimeter`, `spectrum_analyzer`, `signal_generator`, `electronic_load`, `other`
- 协议类型: `scpi`, `can`, `serial`, `usb`, `ethernet`, `gpib`, `custom`
- 连接类型: `usb`, `ethernet`, `serial`, `gpib`, `can`
- 设备状态: `disconnected`, `connecting`, `connected`, `error`
- 测试用例状态: `draft`, `ready`, `archived`
- 执行状态: `pending`, `running`, `completed`, `failed`, `stopped`
- 执行结果: `passed`, `failed`, `error`, `stopped`
- 日志方向: `sent`, `received`
- 日志状态: `success`, `error`, `timeout`
- 插件状态: `installed`, `enabled`, `disabled`, `error`
- 报告格式: `pdf`, `html`, `docx`
- 流程图节点类型: `start`, `end`, `test_step`, `condition`, `loop_start`, `loop_end`
