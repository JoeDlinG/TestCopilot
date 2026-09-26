---
name: RIGOL 示波器
protocol: rigol_oscilloscope
keywords: rigol, 普源, 示波器, oscilloscope, ds1000z, ds1000z-e, ds1202z-e, ds1102z-e, mso5000, ds2000, usbtmc, scpi
---

# RIGOL 示波器 SCPI 手册

适用于 **RIGOL（普源精电）数字示波器**，经 USB / LAN 远程控制。
命令取自官方编程手册（已下载到 `docs/rigol/`）：

- `DS1000ZE_ProgrammingGuide_EN.pdf`（DS1000Z-E 系列，2020-04，文档号 PGA27101-1110）
- `MSO5000_ProgrammingGuide_EN.pdf`（MSO5000 系列）

不同系列命令高度一致；使用缩写时**必须写全大写字母**（`:MEAS:ITEM?`）。

---

## 1. 通信接口

| 方式 | 配置 | 备注 |
|------|------|------|
| **LAN / RAW TCP** | `host` + `port=5555` | 最省事，无需 VISA；推荐 |
| **USB-TMC** | `/dev/usbtmc0` | Linux 内核 `usbtmc` 模块；Windows 需 IVI 驱动 |
| **VISA** | `USB0::0x1AB1::0x04CE::DS1ZD170800001::INSTR` | 需 `pyvisa` + NI-VISA / pyvisa-py |

- USB 连接前需在仪器上确认：`Utility → IO Setting → USB Device = Computer`。
- VISA 资源串示例：`DS1202Z-E (USB0::0x1AB1::0x04CE::DS1ZD170800001::INSTR)`。
- 每条命令以换行符终止；查询返回以换行结束的文本。

---

## 2. 语法与参数规则

```
:ACQuire:TYPE <type>      设置
:ACQuire:TYPE?            查询
:MEASure:ITEM VPP,CHAN1   关键字与参数用空格，多参数用逗号
```

| 参数类型 | 取值 | 查询返回 |
|---------|------|---------|
| Bool | `ON` / `OFF` / `1` / `0` | `1` 或 `0` |
| Discrete | 枚举（如 `NORM`、`AVER`、`PEAK`、`HRES`） | **缩写形式** |
| Integer | NR1 整数（不可带小数） | 整数 |
| Real | NR2 / NR3 | **科学计数法**，如 `1.000000e+00` |
| ASCII String | ASCII 串 | — |

> **重要**：设置类参数只接受**纯数值**，仪器按默认单位解释，
> 不能随参数发送单位（如写 `0.1V` 会报错）。

---

## 3. IEEE 488.2 通用命令

| 命令 | 说明 |
|------|------|
| `*IDN?` | 返回 `RIGOL TECHNOLOGIES,DS1202Z-E,DS1ZD170800001,00.06.02` |
| `*RST` | 复位到默认状态 |
| `*CLS` | 清除状态与错误队列 |
| `*OPC` / `*OPC?` | 操作完成同步（`*OPC?` 返回 `1`） |
| `*WAI` | 等待重叠命令完成 |
| `*ESR?` / `*ESE` | 标准事件寄存器 / 使能 |
| `*STB?` / `*SRE` | 状态字节 / 服务请求使能 |
| `*TST?` | 自检，返回 `0` |
| `*SAV` / `*RCL` | 保存 / 调用状态 |

---

## 4. 常用命令速查

### 运行控制

| 命令 | 说明 |
|------|------|
| `:RUN` / `:STOP` | 启动 / 停止采集 |
| `:SINGle` | 单次触发 |
| `:TFORce` | 强制触发 |
| `:AUToscale` | 自动设置（等同面板 AUTO 键）；正弦 ≥41 Hz、方波 ≥20 mVpp 才可靠 |
| `:CLEar` | 清屏 |

### 通道 `:CHANnel<n>`（n = 1 / 2）

| 命令 | 参数 | 说明 |
|------|------|------|
| `:CHANnel<n>:SCALe <scale>` | 1X 探头 1 mV–10 V；10X 探头 10 mV–100 V | 垂直刻度，默认 V；未开微调时按 1-2-5 步进 |
| `:CHANnel<n>:OFFSet <offset>` | 实数，单位 V | 垂直偏移 |
| `:CHANnel<n>:PROBe <atten>` | `1` / `10` / `100` … | 探头衰减比 |
| `:CHANnel<n>:COUPling <coupling>` | `AC` / `DC` / `GND` | 耦合方式 |
| `:CHANnel<n>:BWLimit <type>` | `20M` / `OFF` … | 带宽限制 |
| `:CHANnel<n>:DISPlay <bool>` | `ON` / `OFF` | 通道显示开关 |
| `:CHANnel<n>:INVert <bool>` | `ON` / `OFF` | 反相 |
| `:CHANnel<n>:UNITs <units>` | `VOLTage` / `WATT` / `AMPere` / `UNKNown` | 单位 |

### 时基 `:TIMebase`

| 命令 | 说明 |
|------|------|
| `:TIMebase[:MAIN]:SCALe <scale>` | 主时基刻度，单位 s/div |
| `:TIMebase[:MAIN]:OFFSet <offset>` | 主时基偏移，单位 s |
| `:TIMebase:MODE <mode>` | `MAIN` / `XY` / `ROLL` |
| `:TIMebase:DELay:ENABle <bool>` | 延迟扫描（ZOOM）开关 |
| `:TIMebase:DELay:SCALe` / `:OFFSet` | 延迟时基刻度 / 偏移 |

### 采集 `:ACQuire`

| 命令 | 参数 |
|------|------|
| `:ACQuire:TYPE <type>` | `NORMal` / `AVERages` / `PEAK` / `HRESolution` |
| `:ACQuire:AVERages <count>` | 平均次数 |
| `:ACQuire:MDEPth <mdep>` | 存储深度 |
| `:ACQuire:SRATe?` | 查询采样率 |

### 触发 `:TRIGger`

| 命令 | 说明 |
|------|------|
| `:TRIGger:MODE <mode>` | `EDGE` / `PULSe` / `VIDeo` / `PATTern` … |
| `:TRIGger:SWEep <mode>` | `AUTO` / `NORMal` / `SINGle` |
| `:TRIGger:EDGe:SOURce <source>` | `CHANnel1` / `CHANnel2` / `AC` / … |
| `:TRIGger:EDGe:LEVel <level>` | 触发电平，单位 V。例：`:TRIGger:EDGe:LEVel 0.16` = 160 mV |
| `:TRIGger:EDGe:SLOPe <slope>` | `POSitive` / `NEGative` / `RFALl` |

### 测量 `:MEASure`

```
:MEASure:ITEM <item>[,<src>[,<src>]]     启用测量项
:MEASure:ITEM? <item>[,<src>[,<src>]]    查询测量值
```

- 例：`:MEASure:ITEM VPP,CHANnel1` / `:MEASure:ITEM? VPP,CHANnel1`
- 查询返回科学计数法，如 `8.888889e-03`。
- 常用 `<item>`：`VPP`、`VMAX`、`VMIN`、`VAVG`、`VRMS`、`FREQuency`、`PERiod`、
  `RISetime`、`FALLtime`、`OVERshoot`、`PREShoot`、`PWIDth`、`NWIDth`、`PDUTy`、`NDUTy`。
- 统计量：`:MEASure:STATistic:ITEM <item>,<src>`、`:MEASure:STATistic:RESet`、
  `:MEASure:STATistic:MODE <mode>`、`:MEASure:STATistic:DISPlay <bool>`。

### 波形读取 `:WAVeform`

| 命令 | 参数 / 返回 |
|------|------------|
| `:WAVeform:SOURce <source>` | `CHANnel1` / `CHANnel2` / `MATH` |
| `:WAVeform:MODE <mode>` | `NORMal`（屏幕上）/ `MAXimum` / `RAW`（内部内存，需 STOP 状态） |
| `:WAVeform:FORMat <format>` | `ASCii` / `BYTE`（默认）/ `WORD` |
| `:WAVeform:STARt` / `:STOP` | 读取起始 / 结束点 |
| `:WAVeform:DATA?` | 波形数据（IEEE 明确长度块） |
| `:WAVeform:PREamble?` | 10 个参数 |
| `:WAVeform:XINCrement?` / `:XORigin?` / `:XREFerence?` | X 方向参数 |
| `:WAVeform:YINCrement?` / `:YORigin?` / `:YREFerence?` | Y 方向参数 |

#### `:WAVeform:PREamble?` 返回格式

```
<format>,<type>,<points>,<count>,<xincrement>,<xorigin>,<xreference>,
<yincrement>,<yorigin>,<yreference>
```

| 字段 | 含义 |
|------|------|
| `format` | 0=BYTE，1=WORD，2=ASC |
| `type` | 0=NORMal，1=MAXimum，2=RAW |
| `points` | 1 – 24000000 |
| `count` | 平均采样模式下的平均次数，其它模式为 1 |
| `xincrement` | 相邻两点的时间差 |
| `xorigin` | X 方向起始时间 |
| `xreference` | X 方向参考点 |
| `yincrement` | Y 方向增量 |
| `yorigin` | Y 方向相对于垂直参考位置的偏移 |
| `yreference` | Y 方向垂直参考位置 |

示例返回：
```
0,2,6000000,1,1.000000e-09,-3.000000e-03,0,4.132813e-01,0,127
```

#### 电压换算

```
电压值 = (原始值 - yreference) × yincrement + yorigin
```

- `BYTE`：每点 1 字节，无符号（0 – 255）
- `WORD`：每点 2 字节，大端有符号（>h）
- `ASCii`：逗号分隔的 ASCII 浮点

#### IEEE 明确长度块

`:WAVeform:DATA?` 返回：

```
#<N><N 位十进制长度><数据><结束符>
```

例：`#800001200` → 后面 1200 字节数据。插件已自动解析。

### 系统 `:SYSTem`

| 命令 | 说明 |
|------|------|
| `:SYSTem:ERRor[:NEXT]?` | 读并清除错误队列（排错首选） |
| `:SYSTem:AUToscale` | 自动设置开关 |
| `:SYSTem:OPTion:INSTall <license>` | 安装选件授权码 |
| `:SYSTem:LAN:IPADdress` | 设置 / 查询 IP |

### 其它子系统

`:CALibrate`（自检/自校准）、`:CURSor`（光标）、`:DECoder`（总线解码）、
`:DISPlay`（显示，`:DISPlay:DATA?` 截屏）、`:ETABle`（事件表）、`:FUNCtion`（波形录制）、
`:LAN`（网络）、`:MASK`（Pass/Fail 模板）、`:MATH`（运算）、`:REFerence`（参考波形）、
`:STORage`（存储）。

---

## 5. 典型自动化序列

```
*IDN?                              ; 识别
*RST                               ; 复位
:CHANnel1:SCALe 1                  ; 垂直 1 V/div
:CHANnel1:PROBe 10                 ; 10X 探头
:TIMebase:SCALe 1e-3               ; 时基 1 ms/div
:TRIGger:MODE EDGE                 ; 边沿触发
:TRIGger:EDGe:SOURce CHANnel1      ; 触发源 CH1
:TRIGger:EDGe:LEVel 0.16           ; 触发电平 160 mV
:TRIGger:SWEep NORMal              ; 正常触发
:MEASure:ITEM VPP,CHANnel1         ; 开启峰峰值测量
:MEASure:ITEM FREQuency,CHANnel1   ; 开启频率测量
:RUN                               ; 开始采集
:MEASure:ITEM? VPP,CHANnel1        ; 读峰峰值
:MEASure:ITEM? FREQuency,CHANnel1  ; 读频率
SYSTem:ERRor?                      ; 确认无错误
```

### 读波形的正确顺序

```
:STOP                       ; 必须先停止（RAW 模式尤其要求）
:WAVeform:SOURce CHANnel1
:WAVeform:MODE NORMal
:WAVeform:FORMat ASCii
:WAVeform:PREamble?         ; 取换算系数
:WAVeform:DATA?             ; 取数据（插件会先 PREamble 再 DATA）
```

---

## 6. 排错

| 现象 | 原因 / 处理 |
|------|------------|
| 无响应 | 检查 IP/端口（5555）、USB 是否设为 `Computer`、`*IDN?` 验证链路 |
| 命令报错 | 查 `:SYSTem:ERRor?`；确认参数是纯数值、无单位后缀 |
| 刻度设置不生效 | 垂直刻度按 1-2-5 步进；需连续值先开 `:CHANnel<n>:VERNier ON` |
| 波形数据长度不符 | 未解析 IEEE 块头 `#N<len>`（插件已处理） |
| RAW 模式读失败 | RAW 只能在 STOP 状态读取，且读取期间不能操作示波器 |
| 读到旧数据 | 加 `*OPC?` 同步，或先 `:STOP` 再读 |
| 缩放后读数偏差 | 检查探头比 `:CHANnel<n>:PROBe?` 与测量值是否匹配 |

---

## 7. 型号覆盖

| 系列 | 带宽 | 模拟通道 |
|------|------|---------|
| DS1202Z-E | 200 MHz | 2 |
| DS1102Z-E | 100 MHz | 2 |
| MSO5000 / DS1000Z / DS2000 系列 | — | 2 / 4（视型号） |

命令以 DS1202Z-E 为例说明，其它型号以官方手册为准。
