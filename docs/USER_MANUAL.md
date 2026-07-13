# AITestLab 使用手册

> **版本**: v1.0 | **更新日期**: 2026-07-05

---

## 目录

1. [快速入门](#1-快速入门)
2. [界面概览](#2-界面概览)
3. [设备管理](#3-设备管理)
4. [测试用例管理](#4-测试用例管理)
5. [AI 生成测试用例](#5-ai-生成测试用例)
6. [流程图编辑器](#6-流程图编辑器)
7. [测试执行](#7-测试执行)
8. [通信日志](#8-通信日志)
9. [自然语言查询](#9-自然语言查询)
10. [测试报告](#10-测试报告)
11. [AI 模型配置](#11-ai-模型配置)
12. [插件管理](#12-插件管理)
13. [常见问题](#13-常见问题)

---

## 1. 快速入门

### 1.1 启动应用

**启动后端服务**：

```bash
cd backend
pip install -r requirements.txt
python run.py
```

看到以下输出表示启动成功：

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

**启动前端**：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 **http://localhost:5173** 即可访问。

### 1.2 典型工作流程

```
步骤 1: 连接设备        → 设备管理页面添加并连接测试仪器
步骤 2: 生成测试用例     → AI 输入需求，自动生成测试用例和流程图
步骤 3: 编辑流程图       → 在流程图编辑器中调整测试步骤和逻辑
步骤 4: 执行测试         → 一键运行测试，实时监控执行状态
步骤 5: 查看日志         → 检查通信日志，确认设备交互正常
步骤 6: 生成报告         → 选择模板，导出 PDF/HTML 测试报告
```

---

## 2. 界面概览

### 2.1 主界面布局

```
┌──────────┬──────────────────────────────────────────┐
│          │  Header: 面包屑导航 + 全局搜索 + 设置      │
│  侧边栏   ├──────────────────────────────────────────┤
│  导航菜单 │                                          │
│          │         主内容区域                         │
│  · 仪表盘 │                                          │
│  · 设备   │                                          │
│  · 用例   │                                          │
│  · 执行   │                                          │
│  · 日志   │                                          │
│  · 报告   │                                          │
│  · AI配置 │                                          │
│  · 插件   │                                          │
│          │                                          │
├──────────┤                                          │
│ 设备状态  │                                          │
│ 指示器   │                                          │
└──────────┴──────────────────────────────────────────┘
```

### 2.2 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 仪表盘 | 设备概览、最近执行、系统状态 |
| `/devices` | 设备列表 | 管理所有测试设备 |
| `/devices/:id` | 设备详情 | 设备配置与实时监控 |
| `/testcases` | 测试用例列表 | 管理所有测试用例 |
| `/testcases/:id` | 用例详情 | 查看/编辑用例与流程图 |
| `/testcases/:id/flow` | 全屏流程图 | 流程图编辑器 |
| `/executions` | 执行历史 | 查看所有执行记录 |
| `/executions/:id` | 执行详情 | 查看执行步骤与结果 |
| `/executions/:id/live` | 实时监控 | 执行过程实时仪表盘 |
| `/logs` | 通信日志 | 查询设备通信记录 |
| `/reports` | 报告管理 | 管理测试报告 |
| `/reports/templates` | 模板管理 | 管理报告模板 |
| `/reports/:id` | 报告预览 | 预览报告内容 |
| `/ai/config` | AI 配置 | 管理 AI 模型 |
| `/plugins` | 插件管理 | 管理协议插件 |

---

## 3. 设备管理

### 3.1 添加设备

1. 进入 **设备管理** 页面 (`/devices`)
2. 点击 **添加设备** 按钮
3. 填写设备信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| 设备名称 | 自定义名称 | `直流电源-Keysight E36313A` |
| 设备类型 | 下拉选择 | `power_supply`、`oscilloscope`、`multimeter`、`electronic_load`、`signal_generator`、`other` |
| 通信协议 | 选择协议 | `scpi`、`can`、`serial`、`ethernet`、`gpib` |
| 连接类型 | 物理接口 | `usb`、`tcpip`、`serial`、`can`、`gpib` |
| 连接地址 | 协议相关地址 | `USB0::0x2A8D::0x0101::MY12345678::INSTR` (VISA)、`/dev/ttyUSB0` (串口)、`192.168.1.100:5025` (TCP) |

4. 点击 **保存**

### 3.2 连接设备

在设备列表中，点击目标设备的 **连接** 按钮。

- 状态变为 **已连接**（绿色指示）
- 侧边栏底部设备状态指示器同步更新

### 3.3 发送命令

1. 进入设备详情页
2. 在命令输入框中输入 SCPI/CAN 等协议命令
3. 点击 **发送**
4. 响应结果显示在下方

**示例命令**：

```
# 可编程电源
*IDN?                           # 查询设备身份
VOLT 5.0                        # 设置输出电压 5V
MEAS:VOLT?                      # 读取实际电压

# 示波器
:CHAN1:SCAL 1.0                # 设置通道1垂直刻度
:WAV:DATA?                     # 获取波形数据
```

### 3.4 断开设备

在设备详情页点击 **断开连接**，或在设备列表点击断开按钮。

### 3.5 删除设备

在设备列表中，点击 **删除** 按钮并确认。

---

## 4. 测试用例管理

### 4.1 手动创建测试用例

1. 进入 **测试用例** 页面 (`/testcases`)
2. 点击 **新建用例**
3. 填写：

| 字段 | 说明 |
|------|------|
| 用例名称 | 简短描述性名称 |
| 需求描述 | 详细的测试需求说明 |
| 参数配置 | JSON 格式，定义测试参数 |

**参数配置示例**：

```json
{
  "input_voltage": 12.0,
  "expected_output": 5.0,
  "tolerance": 0.1,
  "load_current": 1.0
}
```

### 4.2 编辑测试用例

点击用例行进入详情页，可修改名称、需求描述和参数配置。

### 4.3 删除测试用例

在用例列表中点击 **删除** 并确认。关联的流程图数据也会一并删除。

---

## 5. AI 生成测试用例

### 5.1 文字输入生成

1. 进入 **测试用例** 页面
2. 点击 **AI 生成** 按钮
3. 在输入框中输入测试需求，例如：

> 测试 DCDC 电源模块的输出电压，输入 12V，输出应为 5V ± 0.1V，负载 1A。需要分别测试空载、半载和满载三种工况。

4. 点击 **生成**
5. AI 自动生成：
   - 结构化的测试用例（名称、描述、参数）
   - 可视化流程图（测试步骤节点和连线）

6. 检查生成结果，点击 **确认保存**

### 5.2 语音输入生成

1. 点击 **AI 生成** 按钮
2. 点击麦克风图标开始录音
3. 说出测试需求
4. 再次点击停止录音
5. 系统自动转写并生成测试用例

### 5.3 提示词技巧

为获得更好的 AI 生成效果，建议在需求描述中包含：

- **被测对象**：设备/模块名称和类型
- **输入条件**：电压、电流、信号参数
- **预期输出**：期望值和容差范围
- **测试条件**：负载、温度、时序等
- **测试步骤**：操作顺序

---

## 6. 流程图编辑器

### 6.1 进入编辑器

在测试用例详情页中，流程图区域即为编辑器。点击 **全屏编辑** 可进入全屏模式。

### 6.2 界面说明

```
┌──────────────────────────────────────────────────┐
│  工具栏: 保存 | 撤销 | 重做 | 缩放 | 自动布局      │
├──────┬───────────────────────────────────────────┤
│ 节点  │                                           │
│ 面板  │           画布区域                         │
│      │                                           │
│ 开始  │   [开始] ──→ [设置电源] ──→ [测量] ──→ [结束] │
│ 操作  │                                           │
│ 判断  │                                           │
│ 等待  │                                           │
│ 结束  │                                           │
├──────┴───────────────────────────────────────────┤
│              属性面板（选中节点时显示）              │
└──────────────────────────────────────────────────┘
```

### 6.3 节点类型

| 节点 | 图标 | 说明 |
|------|------|------|
| 开始 | ▶ | 测试流程起点 |
| 操作 | ⚙ | 执行设备操作（设置参数、发送命令） |
| 判断 | ◇ | 条件分支（根据测量结果判断） |
| 等待 | ⏱ | 等待指定时间 |
| 循环 | ↻ | 重复执行子步骤 |
| 结束 | ■ | 测试流程终点 |

### 6.4 编辑操作

- **添加节点**：从左侧面板拖拽节点到画布
- **连接节点**：从节点底部连接点拖拽到目标节点顶部
- **配置节点**：选中节点，在右侧属性面板编辑参数
- **删除节点**：选中节点按 Delete 键
- **移动画布**：鼠标拖拽空白区域
- **缩放**：鼠标滚轮或工具栏按钮

### 6.5 操作节点配置示例

**设置电源输出**：
```json
{
  "device": "直流电源-Keysight E36313A",
  "command": "VOLT {input_voltage}",
  "description": "设置输入电压"
}
```

**测量输出电压**：
```json
{
  "device": "万用表-Keithley DMM6500",
  "command": "MEAS:VOLT:DC?",
  "variable": "measured_voltage",
  "description": "读取输出电压"
}
```

**条件判断**：
```json
{
  "condition": "abs(measured_voltage - expected_output) <= tolerance",
  "true_branch": "pass",
  "false_branch": "fail"
}
```

### 6.6 变量系统

在流程图中可使用变量，格式为 `{variable_name}`：

- **预定义变量**：来自测试用例的参数配置
- **运行时变量**：通过操作节点的 `variable` 字段捕获测量值
- **系统变量**：`{timestamp}`、`{execution_id}` 等

---

## 7. 测试执行

### 7.1 启动测试执行

1. 进入测试用例详情页
2. 确认流程图编辑完成
3. 点击 **执行测试** 按钮
4. 确认参数（可覆盖默认值）
5. 点击 **开始执行**

### 7.2 实时监控

执行启动后，自动跳转到实时监控页面 (`/executions/:id/live`)，显示：

| 面板 | 内容 |
|------|------|
| 流程图区域 | 当前执行步骤高亮，已完成/失败步骤不同颜色标记 |
| 步骤进度 | 当前步骤序号 / 总步骤数，进度条 |
| 设备数据 | 实时显示设备返回的测量数据 |
| 执行日志 | 时间线方式显示每步执行的详细信息 |
| 耗时统计 | 总耗时、单步耗时 |

**步骤状态颜色**：
- 🔵 蓝色 = 待执行
- 🟡 黄色 = 执行中
- 🟢 绿色 = 已完成
- 🔴 红色 = 执行失败
- ⚪ 灰色 = 已跳过

### 7.3 停止执行

在实时监控页面点击 **停止** 按钮，当前步骤完成后终止执行。

### 7.4 查看历史执行

1. 进入 **执行历史** 页面 (`/executions`)
2. 列表显示所有执行记录（状态、耗时、步骤数、时间）
3. 点击记录查看详细步骤结果

### 7.5 执行模式

| 模式 | 说明 |
|------|------|
| 顺序执行 | 按流程图从上到下依次执行每个节点 |
| 条件执行 | 根据判断节点的条件结果选择不同分支 |
| 循环执行 | 循环节点内子步骤重复执行指定次数 |

---

## 8. 通信日志

### 8.1 查看日志

1. 进入 **通信日志** 页面 (`/logs`)
2. 使用筛选条件缩小范围：

| 筛选项 | 说明 |
|--------|------|
| 设备 | 按设备筛选 |
| 执行记录 | 按执行记录筛选 |
| 方向 | 发送 / 接收 |
| 时间范围 | 起止时间 |
| 关键字 | 在命令/响应中搜索 |

3. 点击日志行查看详情（完整命令和响应内容）

### 8.2 导出日志

1. 设置筛选条件
2. 点击 **导出 CSV** 按钮
3. 下载 CSV 文件

CSV 导出格式：
```csv
timestamp,direction,device_name,command,response,duration_ms
2026-07-05T10:30:01.123,send,直流电源,"VOLT 5.0","",0
2026-07-05T10:30:01.456,receive,直流电源,"VOLT 5.0","OK",333
```

### 8.3 日志存储机制

- **实时写入**：设备通信时同步记录到 SQLite
- **批量写入**：采用缓冲批量写入，减少 I/O
- **三层存储**：内存缓冲 → SQLite WAL → CSV 归档
- **分页查询**：keyset 分页，大量数据下保持查询性能

---

## 9. 自然语言查询

### 9.1 文字查询

1. 在任意页面的全局搜索栏输入自然语言查询，例如：

> 最近一周有多少次测试失败？

> 电源输出电压超过 5.1V 的测试记录有哪些？

> 示波器通信超时的次数

2. 按 Enter 或点击搜索
3. 结果以表格形式展示

### 9.2 语音查询

1. 点击搜索栏旁边的麦克风图标
2. 说出查询内容
3. 系统自动转写并执行查询

### 9.3 支持的查询类型

| 查询类型 | 示例 |
|----------|------|
| 统计查询 | "今天执行了多少次测试" |
| 筛选查询 | "列出所有失败的测试步骤" |
| 排序查询 | "最近 10 条通信日志" |
| 聚合查询 | "各设备的平均响应时间" |
| 关联查询 | "测试用例 T001 的所有执行结果" |

---

## 10. 测试报告

### 10.1 创建报告模板

1. 进入 **报告管理** → **模板管理** (`/reports/templates`)
2. 点击 **新建模板**
3. 填写：

| 字段 | 说明 |
|------|------|
| 模板名称 | 如 `标准电源测试报告` |
| 输出格式 | PDF / HTML / Markdown |
| 字段定义 | JSON，定义报告包含的字段 |

**字段定义示例**：

```json
{
  "sections": [
    {
      "title": "测试概要",
      "fields": ["test_name", "test_date", "operator", "device_info"]
    },
    {
      "title": "测试条件",
      "fields": ["input_voltage", "output_voltage", "load_current", "temperature"]
    },
    {
      "title": "测试结果",
      "fields": ["pass_count", "fail_count", "total_steps", "duration"]
    },
    {
      "title": "AI 分析结论",
      "fields": ["ai_conclusion"]
    }
  ],
  "include_logs": true,
  "include_charts": true
}
```

### 10.2 生成报告

1. 进入 **报告管理** 页面 (`/reports`)
2. 点击 **生成报告**
3. 选择：
   - 报告模板
   - 测试执行记录
4. 点击 **生成**
5. 系统生成报告，可在线预览或下载

### 10.3 报告预览与下载

- **预览**：点击报告行，在线查看报告内容
- **下载**：点击下载按钮，选择格式（PDF/HTML/Markdown）
- **删除**：删除不需要的报告

### 10.4 AI 生成结论

在模板中启用 `ai_conclusion` 字段后，系统会：

1. 汇总测试执行的所有步骤结果
2. 调用配置的 AI 模型
3. 自动生成测试结论（包含通过率分析、异常点说明、改进建议）

---

## 11. AI 模型配置

### 11.1 添加 AI 模型

1. 进入 **AI 配置** 页面 (`/ai/config`)
2. 点击 **添加模型**
3. 填写配置：

| 字段 | 说明 | 示例 |
|------|------|------|
| 模型名称 | 显示名称 | `GPT-4o`、`本地 Llama3` |
| Provider 类型 | 下拉选择 | `openai`、`ollama`、`anthropic` |
| 模型标识 | Provider 的模型名 | `gpt-4o`、`llama3:8b`、`claude-3-opus` |
| API Key | 云端模型必填 | `sk-xxx...` |
| API 地址 | Provider 的 API 端点 | `https://api.openai.com/v1`、`http://localhost:11434/v1` |

### 11.2 配置 Ollama 本地模型

1. 确保 Ollama 已安装并运行：

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取模型
ollama pull llama3:8b
ollama pull qwen2:7b

# 启动服务（默认端口 11434）
ollama serve
```

2. 在 AITestLab 中添加模型：
   - Provider 类型：`ollama`
   - 模型标识：`llama3:8b`
   - API 地址：`http://localhost:11434/v1`
   - API Key：留空

### 11.3 配置国产模型

通过 OpenAI 兼容接口支持国产模型：

**腾讯混元**：
- Provider 类型：`openai`
- 模型标识：`hunyuan-lite`
- API 地址：`https://api.hunyuan.cloud.tencent.com/v1`
- API Key：从腾讯云获取

**阿里通义千问**：
- Provider 类型：`openai`
- 模型标识：`qwen-turbo`
- API 地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- API Key：从阿里云获取

### 11.4 设置默认模型

在模型列表中，点击目标模型的 **设为默认** 按钮。默认模型用于 AI 测试用例生成和报告结论生成。

### 11.5 测试模型连接

在模型详情页，点击 **测试连接** 按钮，系统发送测试请求验证模型可用性。

---

## 12. 插件管理

### 12.1 查看已安装插件

进入 **插件管理** 页面 (`/plugins`)，列表显示所有已安装插件及其状态：

| 字段 | 说明 |
|------|------|
| 插件名称 | 插件标识名 |
| 版本 | 插件版本号 |
| 类型 | protocol / driver / parser / report |
| 状态 | 已启用 / 已禁用 |
| 描述 | 插件功能描述 |

### 12.2 安装插件

1. 将插件 `.py` 文件放入 `backend/plugins/` 目录
2. 在插件管理页面点击 **安装插件**
3. 输入插件文件路径，如 `plugins/my_protocol.py`
4. 点击 **安装**

### 12.3 启用/禁用插件

在插件列表中点击 **启用** / **禁用** 开关。禁用的插件不会出现在设备连接协议选项中。

### 12.4 卸载插件

点击插件行的 **卸载** 按钮并确认。注意：已使用该插件的设备将无法正常连接。

### 12.5 开发自定义插件

参考 `backend/plugins/example_plugin.py`，完整示例：

```python
"""
Modbus RTU 协议插件示例。
放入 backend/plugins/ 目录后通过 API 安装即可使用。
"""
import asyncio
from typing import Optional
from app.communication import CommunicationInterface


class ModbusRTUPlugin(CommunicationInterface):
    name = "modbus_rtu"
    description = "Modbus RTU 串行通信协议 (RS485)"

    def __init__(self):
        self._serial = None
        self._connected = False

    async def connect(self) -> None:
        import serial_asyncio
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.config.get("port", "/dev/ttyUSB0"),
            baudrate=self.config.get("baudrate", 9600),
            bytesize=self.config.get("bytesize", 8),
            parity=self.config.get("parity", "N"),
            stopbits=self.config.get("stopbits", 1),
        )
        self._connected = True

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
        self._connected = False

    async def send(self, command: str) -> None:
        data = self._build_modbus_frame(command)
        self._writer.write(data)
        await self._writer.drain()

    async def receive(self) -> str:
        response = await self._reader.read(256)
        return self._parse_modbus_frame(response)

    def _build_modbus_frame(self, command: str) -> bytes:
        # Modbus RTU 帧构建逻辑
        parts = command.split()
        slave_id = int(parts[0])
        func_code = int(parts[1])
        # ... CRC 计算等
        return b""

    def _parse_modbus_frame(self, data: bytes) -> str:
        # Modbus RTU 帧解析逻辑
        return data.hex()

    @property
    def is_connected(self) -> bool:
        return self._connected
```

---

## 13. 常见问题

### 13.1 设备连接失败

**问题**：点击连接后提示"连接失败"或"超时"

**排查步骤**：
1. 确认设备已开机并正确连接到电脑
2. 检查连接地址是否正确（VISA 地址可通过 `pyvisa-shell` 或 NI MAX 查看）
3. 确认设备驱动已安装（NI-VISA 或 PyVISA-py 后端）
4. Linux 下检查串口权限：`sudo usermod -a -G dialout $USER`
5. 检查设备是否被其他程序占用

### 13.2 CAN 设备无法识别

**问题**：CAN 接口未在可用设备列表中显示

**排查步骤**：
1. Linux：确认 `can-utils` 已安装，`sudo ip link set can0 up type can bitrate 500000`
2. Windows：确认 PCAN 驱动已安装
3. 检查 `python-can` 配置：`python -m can.viewer` 测试
4. 确认 CAN 终端电阻已正确接入（120Ω）

### 13.3 AI 生成结果不理想

**问题**：AI 生成的测试用例不准确或流程图结构混乱

**改进方法**：
1. 提供更详细的需求描述（包含设备类型、参数范围、测试步骤）
2. 尝试不同的 AI 模型（大模型通常效果更好）
3. 使用流程图编辑器手动调整 AI 生成的结果
4. 将复杂测试拆分为多个较小的用例

### 13.4 Ollama 连接问题

**问题**：配置 Ollama 模型后无法连接

**排查步骤**：
1. 确认 Ollama 服务正在运行：`curl http://localhost:11434/api/tags`
2. 确认模型已拉取：`ollama list`
3. 检查 API 地址格式：应为 `http://localhost:11434/v1`
4. 检查防火墙设置是否阻止了 11434 端口

### 13.5 语音输入无反应

**问题**：点击麦克风后无法录音

**排查步骤**：
1. 确认浏览器已授予麦克风权限
2. 确认系统麦克风正常工作
3. 检查 Whisper 模型是否已下载（首次使用会自动下载 `base` 模型）
4. 手动下载 Whisper 模型：`python -c "import whisper; whisper.load_model('base')"`

### 13.6 数据库问题

**问题**：启动时数据库报错

**解决方案**：
```bash
# 删除旧数据库重新初始化（注意：会丢失所有数据）
rm backend/aitestlab.db
# 重启后端，自动创建新数据库
python backend/run.py
```

### 13.7 端口被占用

**问题**：启动时提示 `Address already in use`

**解决方案**：
```bash
# 查找占用端口的进程
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# 终止进程
kill -9 <PID>  # Linux/macOS
taskkill /PID <PID> /F  # Windows
```

---

## 附录

### A. 设备类型枚举

| 枚举值 | 中文名称 |
|--------|----------|
| `power_supply` | 可编程电源 |
| `oscilloscope` | 示波器 |
| `multimeter` | 数字万用表 |
| `electronic_load` | 电子负载 |
| `signal_generator` | 信号发生器 |
| `can_device` | CAN 设备 |
| `other` | 其他 |

### B. 通信协议枚举

| 枚举值 | 协议 | 驱动库 |
|--------|------|--------|
| `scpi` | SCPI 标准命令 | PyVISA |
| `can` | CAN / CAN FD | python-can |
| `serial` | 串口 RS232/RS485 | pyserial |
| `ethernet` | 以太网 TCP/UDP | asyncio |
| `gpib` | GPIB 总线 | PyVISA |
| `plugin` | 自定义插件协议 | 用户插件 |

### C. 执行状态枚举

| 枚举值 | 说明 |
|--------|------|
| `pending` | 等待执行 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 执行失败 |
| `stopped` | 手动停止 |

### D. 错误码参考

| 错误码 | 说明 |
|--------|------|
| 0 | 成功 |
| 40001 | 资源不存在 |
| 40002 | 参数验证失败 |
| 40003 | 设备连接失败 |
| 40004 | 设备通信超时 |
| 40005 | AI 调用失败 |
| 40006 | 语音转写失败 |
| 40007 | 插件加载失败 |
| 40008 | 报告生成失败 |
| 40009 | 执行状态异常 |
| 40010 | 文件操作失败 |
| 40011 | 数据库操作失败 |
| 50000 | 服务器内部错误 |
