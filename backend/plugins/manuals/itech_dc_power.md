---
name: ITECH 艾德克斯可编程直流电源
protocol: itech_dc_power
keywords: itech, 艾德克斯, 可编程直流电源, IT6800, IT6860A, IT6500, SCPI, RS232, RS485, LAN
---

# ITECH 艾德克斯可编程直流电源手册

适用机型：**IT6800 / IT6860A / IT6500 系列**。插件协议 `itech_dc_power`，设备类型 `power_supply`。
原始手册 PDF 下载在 `docs/dc_power/manuals/`，本文为面向 AITestLab 的可机读摘要。

## 1. 依据的官方资料

| 文档 | 关键章节 / 结论 |
|---|---|
| `ITECH_IT6800_SCPI_CN.pdf` | SCPI 命令表：OUTP / VOLT / CURR / MEAS / SYST:ERR? / *IDN? |
| `ITECH_IT6860A_UserManual_CN.pdf` | 6.1 RS232 接口：8N1、4800~115200、COMM=RS232 + CMD=SCPI |
| `ITECH_IT6800_UserManual_CN.pdf` | 第四章远端操作：默认 9600、DB9 经 IT-E131 转 RS232 |

## 2. 连接参数

| 项 | 说明 |
|---|---|
| 默认接口 | 串口 RS-232 / RS-485（`transport=serial`）；LAN（`transport=ethernet`）同样支持 |
| 串口 | 8 数据位 / 1 停止位 / 无校验（可 N/E/O），默认 9600，可选 4800 / 19200 / 38400 / 57600 / 115200 |
| LAN | IT6500 等机型选配；默认 TCP 5025（手册未规定统一端口，按设备实测修改） |
| RS-485 | IT6500 系列带 RS485；IT6800/IT6860A 需 IT-E123 等选件 |
| `*IDN?` 应答格式 | `ITECH,IT68XX,<序列号>,<固件版本>` |
| 命令结束符 | LF（可在接口配置改 CRLF / CR） |

> 在「设备管理 → 配置接口」切换 serial / ethernet 时，平台会把地址列同步进
> `config.transport`、`config.port` 或 `config.host/tcp_port`；不要在用例里手写这些键。

## 3. 常用命令（action → SCPI）

| action | SCPI |
|---|---|
| `idn` | `*IDN?` |
| `set_voltage` | `VOLT {value}` |
| `set_current` | `CURR {value}` |
| `output_on` | `OUTP ON` |
| `output_off` | `OUTP OFF` |
| `measure_voltage` | `MEAS:VOLT?` |
| `measure_current` | `MEAS:CURR?` |
| `measure_power` | `MEAS:POW?` |

完整清单见插件 `get_commands()`（调试终端与 AI 用例均可直接写 SCPI 字符串或
`{"action": "...", "value": ...}` 字典）。

## 4. 下发示例

| 场景 | 请求 | 实际命令 |
|---|---|---|
| 设定 12 V / 2 A | `{"action": "set_voltage", "value": 12}` | `VOLT 12` |
| 打开输出 | `{"action": "output_on"}` | `OUTP ON` |
| 实测电压 | `"MEAS:VOLT?"` | `MEAS:VOLT?` |

## 5. 安全与注意事项

- 设置电压电流时输出应处于 OFF；输出状态可用 OUTP? 回读。IT6800 帧格式协议与 SCPI 是两套命令，须在面板把 CMD 设为 SCPI。
- 上电顺序建议：`*IDN?` → 设定电压/电流 → `output_on` → `MEAS:*?` 回读 → `output_off`。
- 查询命令带 `?`；设置命令不带。插件把查询应答原样返回，可在用例里配解析规则与上下限判定。
- 语义错误（未知 action / 缺 value / 非法数值）会抛 `ValueError`，**不会**把设备踢下线；
  断线、超时等才抛 `ConnectionError` 并触发设备离线。

## 6. 安装

插件文件位于 `backend/plugins/itech_dc_power.py`（实际文件名见目录），
在插件管理页执行「扫描 → 安装 → 启用」，或用项目包导入 `plugins` 数组。
只有 `status=enabled` 才会进入协议白名单并被 `connect_device()` 加载。
