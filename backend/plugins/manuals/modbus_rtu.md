# Modbus RTU 插件使用手册

## 1. 概述

Modbus RTU 示例插件，演示如何为 AITestLab 编写自定义协议插件。通过串口与 Modbus RTU 从站设备通信。

## 2. 连接参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| port | 串口设备路径 | /dev/ttyUSB0 |
| baudrate | 波特率 | 9600 |
| parity | 校验位（none/even/odd） | none |
| slave_id | 从站地址（1-247） | 1 |

## 3. 命令格式

发送 dict 载荷：

```json
{"function_code": 3, "register_address": 0, "count": 2}
```

常用功能码：

| 功能码 | 说明 |
|--------|------|
| 1 | 读线圈 |
| 2 | 读离散输入 |
| 3 | 读保持寄存器 |
| 4 | 读输入寄存器 |
| 5 | 写单个线圈 |
| 6 | 写单个寄存器 |
| 16 | 写多个寄存器 |

## 4. 使用流程

1. 在「插件管理」中安装并启用 Modbus RTU 插件。
2. 创建 `protocol=modbus_rtu` 的设备并填写串口参数。
3. 连接后按功能码读写寄存器 / 线圈。

注：当前为演示实现，send() 返回模拟数据；生产环境请接入 pymodbus / minimalmodbus。
