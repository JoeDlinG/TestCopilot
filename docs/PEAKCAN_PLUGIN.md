# PeakCAN USB Plugin

PEAK-System PCAN-USB / PCAN-USB FD 硬件插件，用于 AITestLab 平台通过 USB 接口进行 CAN/CAN FD 总线通信。

- **插件名称**: PeakCAN USB
- **协议名称**: `peakcan`
- **版本**: `1.0.0`
- **硬件厂商**: [PEAK-System](https://www.peak-system.com/)
- **支持协议**: CAN 2.0A/B, CAN FD (ISO 11898-1:2015)
- **Python 库**: `python-can`

---

## 目录

- [驱动与安装](#驱动与安装)
- [配置参数](#配置参数)
- [连接管理](#连接管理)
- [通信指令](#通信指令)
  - [send — 发送 CAN/CAN FD 消息](#send--发送-cancan-fd-消息)
  - [receive — 接收消息](#receive--接收消息)
  - [scan — 扫描可用通道](#scan--扫描可用通道)
- [消息格式详解](#消息格式详解)
- [硬件检测](#硬件检测)
- [快速开始](#快速开始)
- [故障排查](#故障排查)

---

## 驱动与安装

### 硬件连接

将 PCAN-USB 适配器通过 USB 线缆连接到 PC，确认设备被识别：

```bash
lsusb | grep PEAK
# 输出示例: Bus 001 Device 007: ID 0c72:0012 PEAK System
```

### 方案 A：SocketCAN（推荐，Linux 内核原生支持）

```bash
# 加载内核模块
sudo modprobe peak_usb

# 查看是否创建了 can0 接口
ip link show can0

# 启动 CAN 接口（波特率 500 kbit/s）
sudo ip link set can0 up type can bitrate 500000
```

### 方案 B：PCAN-Basic chardev 驱动

从 [PEAK-System Linux 驱动页面](https://www.peak-system.com/linux/) 下载并安装 PCAN-Basic API。

### Python 依赖

```bash
pip install python-can
```

---

## 配置参数

通过插件配置界面或 API 设置以下参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `interface` | string | `"auto"` | 驱动接口：`auto`（自动检测）、`socketcan`、`pcan` |
| `channel` | string | `""` | CAN 通道。socketcan: `can0`/`can1`；pcan: `PCAN_USBBUS1`/`0`。留空自动选择。 |
| `bitrate` | integer | `500000` | CAN 仲裁域波特率 (bps)。可选值：100000, 125000, 250000, 500000, 800000, 1000000 |
| `fd` | boolean | `false` | 是否启用 CAN FD 模式。需 PCAN-USB FD 或 PCAN-USB Pro FD 硬件。 |
| `data_bitrate` | integer | `2000000` | CAN FD 数据域波特率 (bps)。仅在 `fd=true` 时生效。 |
| `f_clock_mhz` | integer | — | 时钟频率 (MHz)。通常自动检测，仅在特殊硬件上手动指定。 |

**配置示例：**

```json
{
  "interface": "auto",
  "channel": "can0",
  "bitrate": 500000,
  "fd": false
}
```

CAN FD 配置：

```json
{
  "interface": "socketcan",
  "channel": "can0",
  "bitrate": 500000,
  "fd": true,
  "data_bitrate": 2000000
}
```

---

## 连接管理

### 连接

```python
await plugin.connect(config)
```

- 自动检测最佳驱动接口和通道：优先 SocketCAN → 回退 PCAN-Basic
- 创建 `can.Bus` 实例并启动后台 `Notifier` + `BufferedReader` 监听
- 返回 `True` 表示连接成功；失败抛出 `ConnectionError`

### 断开

```python
await plugin.disconnect()
```

- 停止 `Notifier` 并关闭 `can.Bus`
- 释放所有通道资源

### 查看状态

```python
status = plugin.get_status()
```

返回字段：

| 字段 | 说明 |
|------|------|
| `name` | 插件名称 |
| `protocol` | 协议名称 |
| `version` | 插件版本 |
| `connected` | 是否已连接 |
| `channel` | 当前使用的通道 |
| `interface` | 当前使用的驱动接口 |
| `mode` | 工作模式（`CAN` 或 `CAN FD`） |
| `available_socketcan_channels` | 系统中可用的 SocketCAN 接口列表 |
| `available_pcan_channels` | 系统中可用的 PCAN chardev 通道列表 |

---

## 通信指令

### send — 发送 CAN/CAN FD 消息

向 CAN 总线发送一条消息，支持两种输入格式。

#### 格式一：JSON 字典

```json
{
  "arbitration_id": 291,
  "data": [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88],
  "is_extended_id": false,
  "is_fd": false,
  "is_remote_frame": false,
  "dlc": 8
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `arbitration_id` | integer/string | 是 | CAN 标识符。支持十进制 (`291`)、十六进制字符串 (`"0x123"` 或 `"123"`) |
| `data` | array/string | 是 | 数据内容。字节数组 `[0x11, 0x22, ...]` 或十六进制字符串 `"112233..."` |
| `is_extended_id` | boolean | 否 | 是否使用 29-bit 扩展 ID，默认 `false`（11-bit 标准 ID） |
| `is_fd` | boolean | 否 | 是否作为 CAN FD 帧发送。不指定时跟随总线模式。 |
| `is_remote_frame` | boolean | 否 | 是否发送远程帧 (RTR)，默认 `false` |
| `dlc` | integer | 否 | 数据长度码，通常自动计算 |

#### 格式二：字符串简写

格式为 `"CAN_ID#HEX_DATA"`，支持以下变体：

```python
# 标准 CAN 消息（11-bit ID，8 字节数据）
"123#11223344AABBCCDD"

# 扩展帧（29-bit ID，ID 后加 'x'）
"123x#11223344AABBCCDD"

# 远程帧（数据部分为 'R'）
"123#R"

# CAN FD 消息（最多 64 字节）
"100#00112233445566778899AABBCCDDEEFF"
```

#### 成功响应

```json
{
  "status": "sent",
  "arbitration_id": 291,
  "is_extended_id": false,
  "is_fd": false,
  "data": "1122334455667788"
}
```

#### CAN FD 消息示例

```json
{
  "arbitration_id": 256,
  "data": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  "is_fd": true
}
```

---

### receive — 接收消息

从缓冲中读取一条 CAN 消息（非阻塞），无新消息时返回 `null`。

```json
{"action": "receive"}
```

#### 返回格式

```json
{
  "arbitration_id": 291,
  "is_extended_id": false,
  "is_remote_frame": false,
  "is_fd": false,
  "is_error_frame": false,
  "dlc": 8,
  "data": "1122334455667788",
  "timestamp": 1.234
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `arbitration_id` | integer | CAN 标识符 |
| `is_extended_id` | boolean | 是否为 29-bit 扩展帧 |
| `is_remote_frame` | boolean | 是否为远程帧 (RTR) |
| `is_fd` | boolean | 是否为 CAN FD 帧 |
| `is_error_frame` | boolean | 是否为错误帧 |
| `dlc` | integer | 数据长度码 |
| `data` | string | 数据内容的十六进制字符串 |
| `timestamp` | float | 消息时间戳（秒） |

---

### scan — 扫描可用通道

扫描系统中所有可用的 PCAN 通道。

```json
{"action": "scan"}
```

可通过 `get_status()` 的 `available_socketcan_channels` 和 `available_pcan_channels` 字段获取结果。

---

## 消息格式详解

### 标准帧 vs 扩展帧

| 类型 | ID 范围 | 设置方式 |
|------|--------|---------|
| 标准帧 (11-bit) | 0x000 - 0x7FF | `"is_extended_id": false`（默认） |
| 扩展帧 (29-bit) | 0x00000000 - 0x1FFFFFFF | `"is_extended_id": true` |

### CAN 2.0 vs CAN FD

| 类型 | 最大数据量 | 波特率 | 设置方式 |
|------|-----------|--------|---------|
| CAN 2.0A/B | 8 字节 | bitrate | `fd=false`（默认） |
| CAN FD | 64 字节 | bitrate + data_bitrate | `fd=true`, `is_fd=true` |

### 远程帧 (Remote Frame)

```json
{
  "arbitration_id": 0x123,
  "is_remote_frame": true,
  "dlc": 8
}
```

远程帧不含数据域，仅用于请求其他节点发送数据。

---

## 硬件检测

### 自动检测流程

1. 扫描 `/sys/class/net/*/type` 寻找 `ARPHRD_CAN` (值 `280`) 类型接口 → 识别为 SocketCAN 通道
2. 调用 `can.detect_available_configs(interfaces=['pcan'])` → 识别 PCAN chardev 通道
3. 优先使用第一个可用的 SocketCAN 通道 → 回退第一个 PCAN 通道 → 最终回退 `can0`/`PCAN_USBBUS1`

### 手动检测 Shell 命令

```bash
# 检查 USB 设备
lsusb | grep PEAK

# 检查内核模块
lsmod | grep peak_usb

# 检查 SocketCAN 接口
ip link show type can

# 检查接口状态（UP/DOWN）
ip -details link show can0

# Python 脚本检测
python3 -c "
import can
configs = can.detect_available_configs(interfaces=['pcan'])
for c in configs:
    print(c)
"
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install python-can
sudo modprobe peak_usb
sudo ip link set can0 up type can bitrate 500000
```

### 2. 连接设备

```python
from backend.plugins.peakcan_plugin import PeakCANPlugin

plugin = PeakCANPlugin()
await plugin.connect({
    "interface": "auto",
    "bitrate": 500000,
    "fd": False
})

# 检查状态
status = plugin.get_status()
print(f"Connected: {status['connected']}, Channel: {status['channel']}, Mode: {status['mode']}")
```

### 3. 发送和接收

```python
# 发送一条标准 CAN 消息
result = await plugin.send({
    "arbitration_id": 0x123,
    "data": [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]
})
print(result)
# {"status": "sent", "arbitration_id": 291, "is_extended_id": false, "is_fd": false, "data": "1122334455667788"}

# 使用字符串简写发送
result = await plugin.send("123#11223344AABBCCDD")

# 接收消息
msg = await plugin.receive()
if msg:
    print(f"ID=0x{msg['arbitration_id']:X}, data={msg['data']}")
else:
    print("No message received")
```

### 4. 断开

```python
await plugin.disconnect()
```

---

## 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| `ConnectionError: Failed to open CAN channel` | can0 未启动 | `sudo ip link set can0 up type can bitrate 500000` |
| 设备未检测到 | `peak_usb` 模块未加载 | `sudo modprobe peak_usb` |
| `ImportError: python-can is not installed` | 缺少依赖 | `pip install python-can` |
| 无法发送 CAN FD 消息 | 硬件不支持 FD | 使用 PCAN-USB FD 或 PCAN-USB Pro FD |
| SocketCAN 通道列表为空 | 系统无 CAN 接口 | 检查 USB 连接和内核模块；或安装 PCAN-Basic 驱动使用 pcan 接口 |
| 发送成功但接收不到消息 | 总线无其他节点或未接终端电阻 | CAN 总线两端需 120Ω 终端电阻，且至少有两个节点 |
| `buffer overflow` 警告 | 总线消息速率过高 | 降低消息速率或增大接收缓冲区 |
