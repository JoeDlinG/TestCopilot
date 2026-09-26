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

## 测试场景模板

### 基础通信测试
- 打开通道 → 期望连接成功
- 发送标准 CAN 消息 (ID=0x123, 8字节数据) → 期望发送成功确认
- 读取总线消息 → 期望返回消息或超时
- 关闭通道 → 期望断开成功

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
