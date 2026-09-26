# RIGOL 示波器插件

通过 **SCPI** 远程控制 RIGOL（普源精电）数字示波器的硬件插件。

- **插件名称**：RIGOL 示波器
- **协议名称**：`rigol_oscilloscope`
- **版本**：`1.0.0`
- **厂商**：[RIGOL Technologies](https://www.rigol.com/)
- **支持型号**：DS1000Z-E / DS1000Z / MSO5000 / DS2000 系列等（命令高度一致）
- **依赖**：仅标准库（LAN / USB-TMC）；`pyvisa` 仅在使用 VISA 方式时需要

---

## 目录

- [安装与启用](#安装与启用)
- [连接方式](#连接方式)
- [配置参数](#配置参数)
- [通信指令](#通信指令)
  - [SCPI 字符串](#scpi-字符串)
  - [字典形式](#字典形式)
  - [waveform — 读波形](#waveform--读波形)
  - [screenshot — 屏幕截图](#screenshot--屏幕截图)
  - [其它内置动作](#其它内置动作)
- [波形换算](#波形换算)
- [常用命令](#常用命令)
- [快速开始](#快速开始)
- [故障排查](#故障排查)

---

## 安装与启用

插件文件位于 `backend/plugins/rigol_oscilloscope_plugin.py`，
后端会自动发现（`GET /api/plugins/discovered`）。安装并启用：

```bash
curl -X POST http://127.0.0.1:8000/api/plugins/install -H 'Content-Type: application/json' -d '{
  "name": "RIGOL 示波器", "version": "1.0.0",
  "protocol_type": "rigol_oscilloscope",
  "file_path": "./plugins/rigol_oscilloscope_plugin.py",
  "module_name": "rigol_oscilloscope_plugin",
  "class_name": "RigolOscilloscopePlugin"
}'
curl -X POST http://127.0.0.1:8000/api/plugins/<plugin_id>/enable
```

配套资料：

| 类型 | 路径 |
|------|------|
| Skill（AI 用例生成） | `backend/plugins/skills/rigol_oscilloscope_skill.md` |
| 手册（AI 可机读） | `backend/plugins/manuals/rigol_oscilloscope.md` |
| 官方 PDF | `docs/rigol/` |
| SCPI 通用协议 | `docs/scpi/` + `backend/plugins/manuals/scpi.md` |

---

## 连接方式

| `transport` | 说明 | 前置条件 |
|-------------|------|---------|
| `tcpip`（推荐） | 直连示波器 IP 的 **5555** 端口发 SCPI | 示波器与 PC 同网段；无需 VISA / 驱动 |
| `usbtmc` | 读写 Linux USB-TMC 字符设备 `/dev/usbtmc0` | 内核 `usbtmc` 模块；仪器 `Utility → IO Setting → USB Device = Computer` |
| `visa` | 任意 VISA 资源串 | `pip install pyvisa` + NI-VISA 或 `pyvisa-py` |

VISA 资源串示例：
`USB0::0x1AB1::0x04CE::DS1ZD170800001::INSTR`、`TCPIP0::192.168.1.10::INSTR`

---

## 配置参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `transport` | string | `tcpip` | `tcpip` / `usbtmc` / `visa` |
| `host` | string | `192.168.1.10` | 仪器 IP（`transport=tcpip`） |
| `port` | integer | `5555` | SCPI RAW 端口（`transport=tcpip`） |
| `device` | string | `/dev/usbtmc0` | USB-TMC 设备路径（`transport=usbtmc`） |
| `resource` | string | `USB0::0x1AB1::0x04CE::INSTR` | VISA 资源串（`transport=visa`） |
| `timeout` | number | `2.0` | 读取超时（秒），0.2 – 30 |

```json
{
  "transport": "tcpip",
  "host": "192.168.1.10",
  "port": 5555,
  "timeout": 2.0
}
```

USB-TMC：

```json
{"transport": "usbtmc", "device": "/dev/usbtmc0"}
```

---

## 通信指令

### SCPI 字符串

以 `?` 结尾（或关键字带 `?`）即视为查询，会等待并返回应答；
否则为写命令，返回 `OK`。

```python
await plugin.send("*IDN?")
# 'RIGOL TECHNOLOGIES,DS1202Z-E,DS1ZD170800001,00.06.02'

await plugin.send(":MEASure:ITEM? VPP,CHANnel1")
# '3.300000e+00'        ← 注意 ? 在参数之前，同样按查询处理

await plugin.send(":CHANnel1:SCALe 1")
# 'OK'
```

### 字典形式

```python
await plugin.send({"command": ":CHANnel1:SCALe", "value": 1})   # 写
await plugin.send({"command": ":CHANnel1:SCALe?"})              # 读
await plugin.send({"command": ":TIMebase:SCALe", "value": 1e-3})
```

### waveform — 读波形

```python
await plugin.send({
    "action": "waveform",
    "channel": "CHANnel1",   # CHANnel1 / CHANnel2 / MATH
    "format": "ASCii",       # ASCii / BYTE / WORD
    "mode": "NORMal",        # NORMal / MAXimum / RAW
    "include_data": False,   # True 时返回 data 采样数组
    "start": None, "stop": None,
})
```

插件内部依次执行 `:WAVeform:SOURce/MODE/FORMat` → `:WAVeform:PREamble?`
→ `:WAVeform:DATA?`，并自动解析 IEEE 明确长度块。返回：

```json
{
  "status": "ok", "channel": "CHANnel1", "mode": "NORMal", "format": "ASCii",
  "points": 1200, "raw_bytes": 9000,
  "xincrement": 1e-09, "xorigin": -0.003, "xreference": 0,
  "yincrement": 0.00413, "yorigin": 0.0, "yreference": 127,
  "vmax": 1.234, "vmin": -1.100, "vpp": 2.334,
  "vavg": 0.012, "vrms": 0.83,
  "period_s": 1.2e-06, "frequency_hz": 833333.3
}
```

> RAW 模式只能在 **STOP** 状态读取，且读取期间不能操作示波器。

### screenshot — 屏幕截图

```python
await plugin.send({"action": "screenshot", "path": "/tmp/screen.png"})
# {"status": "ok", "path": "/tmp/screen.png", "bytes": 38421}
```

### 其它内置动作

| `action` | 等价命令 | 说明 |
|----------|---------|------|
| `idn` / `identify` | `*IDN?` | 识别仪器 |
| `reset` | `*RST` | 复位 |
| `autoscale` / `auto` | `:AUToscale` | 自动设置 |
| `run` / `start` | `:RUN` | 启动采集 |
| `stop` | `:STOP` | 停止采集 |
| `single` | `:SINGle` | 单次触发 |
| `error` | `:SYSTem:ERRor?` | 读错误队列 |
| `measure` | `:MEASure:ITEM <item>,<src>` + 查询 | 需 `item`（如 `VPP`）、`channel` |

```python
await plugin.send({"action": "measure", "item": "VPP", "channel": "CHANnel1"})
# '3.300000e+00'
```

---

## 波形换算

```
电压 = (原始值 - yreference) × yincrement + yorigin
```

| `format` | 每点字节 | 解析方式 |
|----------|---------|---------|
| `BYTE`（默认） | 1 | 无符号 `>B` |
| `WORD` | 2 | 大端有符号 `>h` |
| `ASCii` | — | 逗号分隔的 ASCII 浮点 |

`:WAVeform:PREamble?` 返回 10 个字段：

```
format,type,points,count,xincrement,xorigin,xreference,yincrement,yorigin,yreference
```

- `format`：0=BYTE，1=WORD，2=ASC
- `type`：0=NORMal，1=MAXimum，2=RAW

---

## 常用命令

| 命令 | 说明 |
|------|------|
| `*IDN?` | 识别仪器 |
| `*RST` / `*CLS` | 复位 / 清状态 |
| `*OPC?` | 操作完成同步（返回 `1`） |
| `:SYSTem:ERRor?` | 读错误队列（排错首选） |
| `:RUN` / `:STOP` / `:SINGle` | 运行控制 |
| `:AUToscale` | 自动设置 |
| `:CHANnel<n>:SCALe <v>` | 垂直刻度（V/div） |
| `:CHANnel<n>:PROBe <atten>` | 探头比（1 / 10 / 100） |
| `:TIMebase[:MAIN]:SCALe <s>` | 时基（s/div） |
| `:TRIGger:EDGe:SOURce CHANnel1` | 触发源 |
| `:TRIGger:EDGe:LEVel <v>` | 触发电平（V） |
| `:TRIGger:SWEep AUTO\|NORMal\|SINGle` | 触发方式 |
| `:MEASure:ITEM <item>,<src>` | 启用测量项 |
| `:MEASure:ITEM? <item>,<src>` | 读测量值 |
| `:ACQuire:TYPE NORMal\|AVERages\|PEAK\|HRESolution` | 采集模式 |
| `:WAVeform:PREamble?` / `:WAVeform:DATA?` | 波形参数 / 数据 |
| `:DISPlay:DATA?` | 屏幕截图（PNG 块） |

完整命令表见 `backend/plugins/manuals/rigol_oscilloscope.md`。

---

## 快速开始

```python
from plugins.rigol_oscilloscope_plugin import RigolOscilloscopePlugin

p = RigolOscilloscopePlugin()
await p.connect({"transport": "tcpip", "host": "192.168.1.10", "port": 5555})

print(await p.send("*IDN?"))
await p.send("*RST")
await p.send(":CHANnel1:PROBe 10")
await p.send(":CHANnel1:SCALe 1")
await p.send(":TIMebase:SCALe 1e-3")
await p.send(":TRIGger:EDGe:SOURce CHANnel1")
await p.send(":TRIGger:EDGe:LEVel 0.16")
await p.send(":MEASure:ITEM VPP,CHANnel1")
await p.send(":RUN")

print(await p.send(":MEASure:ITEM? VPP,CHANnel1"))   # 3.300000e+00

await p.send(":STOP")
w = await p.send({"action": "waveform", "channel": "CHANnel1", "format": "ASCii"})
print(w["points"], w["vpp"], w["vmax"], w["vmin"])

print(await p.send(":SYSTem:ERRor?"))                 # 0,"No error"
await p.disconnect()
```

---

## 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| `连接 RIGOL 示波器失败` | IP / 端口不通 | 确认示波器 IP，端口 5555；`ping <ip>` 与 `nc -vz <ip> 5555` |
| USB-TMC 设备不存在 | `/dev/usbtmc0` 未生成 | 加载 `sudo modprobe usbtmc`；确认仪器 USB Device 设为 `Computer` |
| `未安装 pyvisa` | VISA 方式缺依赖 | `pip install pyvisa`（另需 NI-VISA 或 `pyvisa-py`） |
| 命令无应答 / 读到上一次的结果 | 残留数据未清 | 插件每次查询前会自动清空接收缓冲；仍异常时增大 `timeout` |
| 读波形报 `PREamble 返回异常` | 仪器未就绪或命令不支持 | 先 `:STOP` 再读；确认型号支持 `:WAVeform` |
| RAW 模式读失败 | 未停止采集 | RAW 只能在 STOP 状态读取 |
| 测量值一直是旧值 | 未同步 | 命令后加 `*OPC?` 或先 `:STOP` |
| 垂直刻度设置不生效 | 按 1-2-5 步进取整 | 需连续值先 `:CHANnel<n>:VERNier ON` |
| 幅度差 10 倍 | 探头比不匹配 | 检查 `:CHANnel<n>:PROBe?` 与实际探头一致 |
| 命令报错 | 参数越界 / 带单位 | 只发纯数值；查 `:SYSTem:ERRor?` |
