---
name: Chroma 致茂 62000P 可编程直流电源
protocol: chroma_dc_power
keywords: chroma, 致茂, 62000P, 可程控直流电源, SCPI, RS232, RS485, LAN, GPIB
---

# Chroma 致茂 62000P 可编程直流电源手册

适用机型：**62000P 系列（62006P / 62012P / 62024P / 62050P）**。插件协议 `chroma_dc_power`，设备类型 `power_supply`。
原始手册 PDF 下载在 `docs/dc_power/manuals/`，本文为面向 AITestLab 的可机读摘要。

## 1. 依据的官方资料

| 文档 | 关键章节 / 结论 |
|---|---|
| `Chroma_62000P_Catalogue_CN.pdf` | 官网型录：标准 RS-232/USB、选配 GPIB 或以太网、后面板 RS-485 |
| 62000P Operating & Programming Manual（在线全文） | 第 5 章 Remote Operation：SOUR / CONF / FETC / MEAS / PROG / SYST 子系统 |

## 2. 连接参数

| 项 | 说明 |
|---|---|
| 默认接口 | 串口 RS-232 / RS-485（`transport=serial`）；LAN（`transport=ethernet`）同样支持 |
| 串口 | RS-232C 标准接口，波特率在面板 System Setup > Baudrate 设置（默认按机型，常用 9600） |
| LAN | 以太网为选配卡（A620004 为 GPIB 卡）；手册未规定统一 socket 端口，默认 5025 可配 |
| RS-485 | 后面板 19 号 RS-485 用于主从串/并联通信，非独立远程控制口 |
| `*IDN?` 应答格式 | `CHROMA,62000P,<序列号>,<固件版本>` |
| 命令结束符 | LF（可在接口配置改 CRLF / CR） |

> 在「设备管理 → 配置接口」切换 serial / ethernet 时，平台会把地址列同步进
> `config.transport`、`config.port` 或 `config.host/tcp_port`；不要在用例里手写这些键。

## 3. 常用命令（action → SCPI）

| action | SCPI |
|---|---|
| `idn` | `*IDN?` |
| `set_voltage` | `SOUR:VOLT {value}` |
| `set_current` | `SOUR:CURR {value}` |
| `output_on` | `CONF:OUTP ON` |
| `output_off` | `CONF:OUTP OFF` |
| `measure_voltage` | `MEAS:VOLT?` |
| `measure_power` | `FETC:POW?` |
| `get_status` | `FETC:STAT?` |

完整清单见插件 `get_commands()`（调试终端与 AI 用例均可直接写 SCPI 字符串或
`{"action": "...", "value": ...}` 字典）。

## 4. 下发示例

| 场景 | 请求 | 实际命令 |
|---|---|---|
| 设定 48 V | `{"action": "set_voltage", "value": 48}` | `SOUR:VOLT 48` |
| 打开输出 | `{"action": "output_on"}` | `CONF:OUTP ON` |
| 实测功率 | `{"action": "measure_power"}` | `FETC:POW?` |

## 5. 安全与注意事项

- 电压/电流用 SOUR: 前缀，输出开关用 CONF:OUTP（与通用 SCPI 的 OUTP 不同）；回读实测值可用 MEAS: 或 FETC:。
- 上电顺序建议：`*IDN?` → 设定电压/电流 → `output_on` → `MEAS:*?` 回读 → `output_off`。
- 查询命令带 `?`；设置命令不带。插件把查询应答原样返回，可在用例里配解析规则与上下限判定。
- 语义错误（未知 action / 缺 value / 非法数值）会抛 `ValueError`，**不会**把设备踢下线；
  断线、超时等才抛 `ConnectionError` 并触发设备离线。

## 6. 安装

插件文件位于 `backend/plugins/chroma_dc_power.py`（实际文件名见目录），
在插件管理页执行「扫描 → 安装 → 启用」，或用项目包导入 `plugins` 数组。
只有 `status=enabled` 才会进入协议白名单并被 `connect_device()` 加载。
