---
name: TDK-Lambda GENESYS+ 可编程直流电源
protocol: tdk_lambda_dc_power
keywords: tdk, tdk-lambda, lambda, genesys+, 可编程直流电源, SCPI, RS232, RS485, LAN
---

# TDK-Lambda GENESYS+ 可编程直流电源手册

适用机型：**GENESYS+ G+ / GH / GSP / GSPL 系列**。插件协议 `tdk_lambda_dc_power`，设备类型 `power_supply`。
原始手册 PDF 下载在 `docs/dc_power/manuals/`，本文为面向 AITestLab 的可机读摘要。

## 1. 依据的官方资料

| 文档 | 关键章节 / 结论 |
|---|---|
| `TDK_GenesysPlus_UserManual.pdf` | 内置 LAN/USB/RS-232/RS-485；1.9.4 默认 115200 + SCPI；第 4 章接口 |
| `TDK_Genesys_LAN_Interface_Manual.pdf` | TCP 8003 / UDP 8005；11.2/11.3 SCPI 示例；第 12 章 RS-485 多机 |

## 2. 连接参数

| 项 | 说明 |
|---|---|
| 默认接口 | 串口 RS-232 / RS-485（`transport=serial`）；LAN（`transport=ethernet`）同样支持 |
| 串口 | 默认 115200（可用 SYST:BAUD 改），8N1，语言须选 SCPI；RS485 地址在前面板设置 |
| LAN | TCP socket 端口 8003（手册原文），UDP 8005；VXI-11/VISA 另走 inst0 |
| RS-485 | 内置 RS232/RS485 IN 与 RS485 OUT，multi-drop 由带 LAN 的主电源经 J3 链路转发 |
| `*IDN?` 应答格式 | `TDK-LAMBDA,G…,<序列号>,<固件版本>` |
| 命令结束符 | LF（可在接口配置改 CRLF / CR） |

> 在「设备管理 → 配置接口」切换 serial / ethernet 时，平台会把地址列同步进
> `config.transport`、`config.port` 或 `config.host/tcp_port`；不要在用例里手写这些键。

## 3. 常用命令（action → SCPI）

| action | SCPI |
|---|---|
| `idn` | `*IDN?` |
| `set_voltage` | `VOLT {value}` |
| `set_current` | `CURR {value}` |
| `output_on` | `OUTP:STAT ON` |
| `output_off` | `OUTP:STAT OFF` |
| `measure_voltage` | `MEAS:VOLT?` |
| `measure_current` | `MEAS:CURR?` |
| `set_ovp` | `VOLT:PROT:LEV {value}` |

完整清单见插件 `get_commands()`（调试终端与 AI 用例均可直接写 SCPI 字符串或
`{"action": "...", "value": ...}` 字典）。

## 4. 下发示例

| 场景 | 请求 | 实际命令 |
|---|---|---|
| 设定 24 V | `{"action": "set_voltage", "value": 24}` | `VOLT 24` |
| 打开输出 | `{"action": "output_on"}` | `OUTP:STAT ON` |
| 实测电压 | `"MEAS:VOLT?"` | `MEAS:VOLT?` |

## 5. 安全与注意事项

- 输出开关用 OUTP:STAT（不是 OUTP）；电压保护阈值用 VOLT:PROT:LEV。RS-485 多机从站地址由主电源负责寻址。
- 上电顺序建议：`*IDN?` → 设定电压/电流 → `output_on` → `MEAS:*?` 回读 → `output_off`。
- 查询命令带 `?`；设置命令不带。插件把查询应答原样返回，可在用例里配解析规则与上下限判定。
- 语义错误（未知 action / 缺 value / 非法数值）会抛 `ValueError`，**不会**把设备踢下线；
  断线、超时等才抛 `ConnectionError` 并触发设备离线。

## 6. 安装

插件文件位于 `backend/plugins/tdk_lambda_dc_power.py`（实际文件名见目录），
在插件管理页执行「扫描 → 安装 → 启用」，或用项目包导入 `plugins` 数组。
只有 `status=enabled` 才会进入协议白名单并被 `connect_device()` 加载。
