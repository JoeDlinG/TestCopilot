---
name: PeakCAN USB
protocol: peakcan
keywords: peakcan, pcan, can bus, can fd, can总线, peak-system, peak系统, usb-can, can测试, can通信
---

# PeakCAN USB 测试用例生成 Skill

本 Skill 指导 AI 为 PEAK-System PCAN-USB / PCAN-USB FD 硬件设备生成 CAN/CAN FD 通信测试用例。

## 硬件概述

- **厂商**: PEAK-System (德国)
- **接口**: USB 2.0
- **协议**: CAN 2.0A/B, CAN FD (ISO 11898-1:2015)
- **驱动**: PCAN-Basic API (Linux: chardev 驱动, Windows: 系统驱动)
- **Python 库**: `python-can` (interface: `pcan`)

## 通道命名

PCAN 通道使用以下格式：
- `PCAN_USBBUS1`, `PCAN_USBBUS2`, ... （多设备时自动编号）
- 也支持数字形式：`0`, `1`, ...

## 命令生成规则

### CAN 消息格式

1. 发送标准 CAN 消息（最大 8 字节）：
```json
{
  "action": "send",
  "arbitration_id": 291,
  "data": [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88],
  "is_extended_id": false
}
```

2. 发送 CAN FD 消息（最大 64 字节）：
```json
{
  "action": "send",
  "arbitration_id": 256,
  "data": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  "is_fd": true,
  "is_extended_id": false
}
```

3. 也支持字符串格式：`"123#11223344AABBCCDD"` 或 `"100#00112233445566778899AABBCCDDEEFF"`

### 周期 / 定时发送（period_ms 是参数，不是固定值）

当需求要求「每隔 N ms 发送一条报文」时，用 `send_periodic` action，并把间隔写进 `period_ms`
（**按需求填写，绝不能写死 200ms**）：

```json
{
  "action": "send_periodic",
  "arbitration_id": 32,
  "data": [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
  "is_extended_id": false,
  "period_ms": 200,
  "count": 20
}
```

- `period_ms`：发送间隔（毫秒，浮点），必须为正；由用例需求决定，例如「每 500ms」就填 `500`。
- `count`（可选）：发满 N 帧后自动停止；不填则一直发送，直到用例发 `{"action": "stop_periodic"}`。
- `key`（可选）：给该周期发送命名，便于 `{"action": "stop_periodic", "key": "xxx"}` 精确停止；
  不带 key 的 `stop_periodic` 会停止全部。
- 停止：`{"action": "stop_periodic"}` 或 `{"action": "stop_periodic", "key": "xxx"}`。

4. 接收消息格式：
```json
{
  "arbitration_id": 291,
  "is_extended_id": false,
  "is_fd": false,
  "is_remote_frame": false,
  "dlc": 8,
  "data": "1122334455667788",
  "timestamp": 1.234
}
```

### 连接配置

```json
{
  "channel": "PCAN_USBBUS1",
  "bitrate": 500000,
  "fd": false,
  "data_bitrate": 2000000
}
```

常用波特率：100000, 125000, 250000, 500000, 800000, 1000000

> 通道的**打开 / 关闭由平台「设备管理」统一负责**：连接设备时自动 open，断开时自动 close。
> 用例里**不要生成 `open` / `close` 命令**——插件不支持这两个 action，会报「未知的 PeakCAN action」。

## 测试场景模板

### 基础通信测试
- （通道的打开 / 关闭由平台「设备管理」负责，用例不生成 open/close 步骤）
- 发送标准 CAN 消息 (ID=0x123, 8字节数据) → 期望发送成功确认
- 读取总线消息 → 期望返回消息或超时

### CAN FD 测试（需 PCAN-USB FD 硬件）
- 以 FD 模式连接 → 期望连接成功
- 发送 64 字节 FD 消息 → 期望发送成功
- 发送 12 字节 FD 消息 (dlc=12) → 期望发送成功
- 接收 FD 消息 → 期望 is_fd=true

### 边界测试
- 发送最大标准 CAN 消息 (8字节) → 期望成功
- 发送超出 8 字节的标准 CAN 消息 → 期望错误
- 使用无效通道名 → 期望连接失败
- 使用不支持的波特率 → 期望连接失败

### 扩展帧测试
- 发送 29-bit 扩展 ID 消息 → 期望发送成功
- 接收扩展帧 → 期望 is_extended_id=true

### 远程帧测试
- 发送远程帧 (RTR) → 期望发送成功
- 远程帧数据长度应为 0

## 生成要求

- 覆盖基础通信、CAN FD、边界、扩展帧四大类场景
- 每条用例包含明确的期望结果（状态码 / 返回数据 / 错误信息）
- device_type 填 "other", devices_required 包含 "peakcan"
- 如测试环境无可用的物理 CAN 总线，备注"需要在有 CAN 总线或终端电阻的环境中进行"

### 命令必须写进结构化字段（关键）

- 每一步的 CAN 命令**必须**放进该 step 的 `parameters.command`（字符串）或 `parameters.commands`（数组），
  内容为上面的 JSON 命令（`{"action": "send", ...}`）或字符串形式 `"123#11223344"`。
- `action` 字段**只能**写一句人话描述，不要把命令写成 python-can 调用伪代码
  （例如 `bus.recv(timeout=2.0)` 这种是无效的，设备不会执行）。
- 周期需求必须用 `send_periodic`（`period_ms` 按需求填），不要用 loop 节点或散文表达周期。
- 支持的动作只有：`send` / `send_periodic` / `stop_periodic` / `receive` / `scan` / `diagnose`。
  通道的打开/关闭由平台「设备管理」负责，**不要生成 `open` / `close` 步骤**。
