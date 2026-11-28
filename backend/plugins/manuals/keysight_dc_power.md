---
name: Keysight 是德科技可编程直流电源
protocol: keysight_dc_power
keywords: keysight, 是德科技, agilent, E36300, N5700, 可编程直流电源, SCPI, LAN, RS232
---

# Keysight 是德科技可编程直流电源手册

适用机型：**E36300 / N5700 系列**。插件协议 `keysight_dc_power`，设备类型 `power_supply`。
原始手册 PDF 下载在 `docs/dc_power/manuals/`，本文为面向 AITestLab 的可机读摘要。

## 1. 依据的官方资料

| 文档 | 关键章节 / 结论 |
|---|---|
| `Keysight_E36300_UsersGuide_EN.pdf` | 官网 PDF：Using sockets 明确 port 5025 为 SCPI socket；LAN/USB/GPIB 接口配置 |
| Keysight Series N5700 User's Guide（官网支持页） | 第 5 章 Language Reference：Common / Measure / Output / Source / Status / System 命令 |

## 2. 连接参数

| 项 | 说明 |
|---|---|
| 默认接口 | 串口 RS-232 / RS-485（`transport=serial`）；LAN（`transport=ethernet`）同样支持 |
| 串口 | E36300 无原生 RS-232（USB/LAN/GPIB）；N5700 等带串口机型或 USB-串口适配器用此通道，默认 9600 可配 |
| LAN | SCPI socket 标准端口 5025（手册原文），VXI-11 VISA 串为 TCPIP0::<IP>::inst0::INSTR |
| RS-485 | 该系列不提供 RS-485；若经 RS-485 转换器接入，按点对点串口使用 |
| `*IDN?` 应答格式 | `Keysight Technologies,E36312A,<序列号>,<固件版本>` |
| 命令结束符 | LF（可在接口配置改 CRLF / CR） |

> 在「设备管理 → 配置接口」切换 serial / ethernet 时，平台会把地址列同步进
> `config.transport`、`config.port` 或 `config.host/tcp_port`；不要在用例里手写这些键。

## 3. 常用命令（action → SCPI）

| action | SCPI |
|---|---|
| `idn` | `*IDN?` |
| `select_channel` | `INST:SEL {channel}` |
| `set_voltage` | `VOLT {value}` |
| `set_current` | `CURR {value}` |
| `output_on` | `OUTP ON` |
| `output_off` | `OUTP OFF` |
| `measure_voltage` | `MEAS:VOLT?` |
| `system_error` | `SYST:ERR?` |

完整清单见插件 `get_commands()`（调试终端与 AI 用例均可直接写 SCPI 字符串或
`{"action": "...", "value": ...}` 字典）。

## 4. 下发示例

| 场景 | 请求 | 实际命令 |
|---|---|---|
| 选择通道 1 | `{"action": "select_channel", "channel": "OUT1"}` | `INST:SEL OUT1` |
| 设定 5 V | `{"action": "set_voltage", "value": 5}` | `VOLT 5` |
| 打开输出 | `{"action": "output_on"}` | `OUTP ON` |

## 5. 安全与注意事项

- E36300 三输出机型设定电压/电流前必须先 INST:SEL 选择通道；单输出 N5700 可忽略。改量程/接线前先 OUTP OFF。
- 上电顺序建议：`*IDN?` → 设定电压/电流 → `output_on` → `MEAS:*?` 回读 → `output_off`。
- 查询命令带 `?`；设置命令不带。插件把查询应答原样返回，可在用例里配解析规则与上下限判定。
- 语义错误（未知 action / 缺 value / 非法数值）会抛 `ValueError`，**不会**把设备踢下线；
  断线、超时等才抛 `ConnectionError` 并触发设备离线。

## 6. 安装

插件文件位于 `backend/plugins/keysight_dc_power.py`（实际文件名见目录），
在插件管理页执行「扫描 → 安装 → 启用」，或用项目包导入 `plugins` 数组。
只有 `status=enabled` 才会进入协议白名单并被 `connect_device()` 加载。
