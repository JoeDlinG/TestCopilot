# Modbus TCP 插件使用手册

## 1. 概述

Modbus TCP 主站驱动，基于 `pymodbus`（BSD-3-Clause，纯 Python，无原生依赖）。

**一个驱动服务所有说 Modbus TCP 的设备**——PLC、机械臂控制器、电力仪表、温控表、远程 IO 模块。
不需要按品牌安装插件，也不需要建点位表：地址直接写在测试步骤里。

本程序只做**通信层的交互与控制**，不对 PLC 编程。

## 2. 连接参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| host | 设备 IP / 主机名（**必填**） | — |
| port | 端口 | 502 |
| slave_id | 从站号（Unit ID），1–247 | 1 |
| timeout | 单次请求超时（秒） | 3.0 |
| byte_order | 寄存器**内**字节序：`big` / `little` | big |
| word_order | 寄存器**之间**的字序：`big` / `little` | big |
| response_format | `text`（默认）/ `typed` | text |
| poll | 后台轮询命令（可选，见 §7） | 空 |
| poll_interval_ms | 轮询间隔（毫秒） | 1000 |

> TCP 直连时 `slave_id` 通常为 1；经网关转发串口从站时填实际从站号。
> 读 float32 / int32 得到乱数时，**先切 `word_order`**。

## 3. 支持的协议原语

| 原语 | FC | 方向 | 返回形态 |
|------|----|------|----------|
| read_coils | 01 | 读 | 位数组 |
| read_discrete_inputs | 02 | 读 | 位数组 |
| read_holding_registers | 03 | 读 | 寄存器数组 |
| read_input_registers | 04 | 读 | 寄存器数组 |
| write_single_coil | 05 | 写 | OK |
| write_single_register | 06 | 写 | OK |
| write_multiple_coils | 15 | 写 | OK |
| write_multiple_registers | 16 | 写 | OK |

## 4. 测试步骤的写法

### 4.1 紧凑写法

```
FC03:40001:2        # 读 2 个保持寄存器，起始 40001
FC03:0:2            # 同上（0-based 协议地址）
FC03:10:1           # 读 1 个保持寄存器
FC06:40010:1        # 把 1 写入 40010
FC01:00001:8        # 读 8 个线圈
FC05:00003:1        # 线圈 00003 置 1
FC16:40020:1,2,3    # 连续写 3 个寄存器
```

也支持原语名：`read_holding:40001:2`、`write_register:40010:1`。

### 4.2 结构化写法（JSON，支持数据类型解码）

```json
{"fc": 3, "addr": 100, "count": 2, "dtype": "float32"}
{"fc": 3, "addr": 100, "count": 2, "dtype": "float32", "word_order": "little"}
{"fc": 3, "addr": 200, "count": 4, "dtype": "string"}
{"fc": 6, "addr": 50, "value": 25.5, "dtype": "float32"}
```

### 4.3 地址写法

设备手册里的引用地址可直接照抄，驱动自动换算：

| 手册写法 | 含义 | 换算 |
|----------|------|------|
| `40001`–`49999` | 保持寄存器 | 减 40001 |
| `30001`–`39999` | 输入寄存器 | 减 30001 |
| `10001`–`19999` | 离散输入 | 减 10001 |
| `00001`–`09999` | 线圈 | 减 1 |

直接写 `0`–`65535` 的裸地址则原样使用。

## 5. 数据类型（dtype）

| dtype | 占用寄存器 | 说明 |
|-------|-----------|------|
| uint16 / int16 | 1 | 默认语义 |
| bool | 1 | 非 0 即真 |
| uint32 / int32 | 2 | 受 byte_order + word_order 影响 |
| float32 | 2 | 同上 |
| uint64 / int64 | 4 | |
| float64 | 4 | |
| string | 可变 | ASCII，2 字符/寄存器，尾部 `\x00` 自动去除 |
| raw（默认） | 可变 | 返回原始寄存器数组 |

## 6. 返回值与错误处理

**返回值（response_format = text，默认）**：

| 场景 | 返回 |
|------|------|
| 单值读 | `17000`、`23.5`、`1`（线圈真）、`0`（线圈假） |
| 多值读 | `17000,0`（逗号分隔） |
| 写操作 | `OK` |
| 设备返回 Modbus 异常 | `ERROR: ILLEGAL_DATA_ADDRESS(0x02)` |

**两类错误的语义不同，写用例时要注意**：

| 情况 | 行为 | 理由 |
|------|------|------|
| 设备**应答了**异常码（地址不存在、值非法、从站忙） | 返回 `ERROR: ...`，**连接保持** | 负向用例可以断言这条错误；链路是好的 |
| **无应答**（超时、掉线、IP 不通） | 抛 `ConnectionError`，设备自动置为离线 | 链路确实断了，应断开重连 |

常见异常码：

| 码 | 名称 | 含义 |
|----|------|------|
| 0x01 | ILLEGAL_FUNCTION | 设备不支持该功能码 |
| 0x02 | ILLEGAL_DATA_ADDRESS | 地址不存在 |
| 0x03 | ILLEGAL_DATA_VALUE | 写入值超出范围 |
| 0x04 | SLAVE_DEVICE_FAILURE | 从站内部错误 |
| 0x06 | SLAVE_DEVICE_BUSY | 从站忙，需重试 |

## 7. 后台轮询（可选）

Modbus 是严格的主从协议，**设备不会主动上报**。因此 `receive()` 默认返回空，
不会以 10Hz 空轮询轰炸 PLC。

如果需要在终端持续观察某个寄存器（例如机械臂"到位信号"），可在连接参数里配置：

```json
{"poll": "FC03:40001:1", "poll_interval_ms": 1000}
```

驱动最多按该间隔重读一次，不会更频繁。

## 8. 判定配置（结果解析）

响应是纯文本数值，建议解析配置用 **单位 = 文本**（直接按字符串取值，不做字节切片）：

| 字段 | 建议值 |
|------|--------|
| 数据类型 | `dec`（数值）/ `string`（文本）/ `bool` |
| 单位 | `text` |
| 起始/长度 | 0 / 1（text 单位下不生效） |
| 判断条件 | min / max / equals |

> 若仍用 `byte` 单位，形如 `1700` 的响应会被当作十六进制字节串解析，结果错误。
> 数值型响应一律用 `text` 单位。

## 9. 自检

```
python backend/plugins/selftest/modbus_tcp_selftest.py
```

脚本内置一个**独立手写的最小 Modbus TCP 从站**（不依赖 pymodbus server），
覆盖连接、读写回环、float32 字序、线圈、异常码、超时、非法命令共 20 项断言。
无真机时用它验证驱动本身是否健康。
