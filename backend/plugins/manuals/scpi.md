---
name: SCPI 通用协议
protocol: scpi
keywords: scpi, scpi协议, 程控仪器, ieee488.2, ieee 488.2, 可编程仪器, 仪器控制, visa, usbtmc, 示波器, 万用表, 电源, 信号源
---

# SCPI 协议手册（通用定义）

SCPI = **Standard Commands for Programmable Instruments**，可编程仪器标准命令。
它建立在 **IEEE 488.1 / IEEE 488.2** 之上，为所有程控仪器提供统一的命令语言，
使得不同厂商、不同型号的同类仪器可以互换。

- 规范版本：**SCPI 1999.0**（卷一 Syntax & Style 已下载到 `docs/scpi/`）
- 依赖标准：IEEE 488.2（语法/状态报告）、IEEE 754（浮点）、ISO 646（7 位 ASCII）

---

## 1. 命令结构

SCPI 命令是一棵**层次化命令树**，由根关键字和若干级子关键字组成：

```
:ACQuire:TYPE <type>       根关键字 ACQuire，二级关键字 TYPE
:CHANnel1:SCALe 0.1        通道后缀作为关键字的一部分
:MEASure:ITEM? VPP,CHAN1   带 ? 的查询
```

### 语法规则

| 规则 | 说明 |
|------|------|
| 起始符号 | 命令串通常以 `:` 开头（`:` 不是命令内容时可省略） |
| 层级分隔 | 关键字之间用 `:` 分隔 |
| 参数分隔 | 关键字与第一个参数用**空格**分隔；多个参数之间用 `,` 分隔 |
| 查询 | 命令末尾加 `?` |
| 多命令 | 同一行多条命令用 `;` 分隔；`;` 后接 `:` 表示新命令从根开始 |
| 大小写 | **不敏感**，`:meas:item?` == `:MEASure:ITEM?` |
| 缩写 | 只保留大写字母部分，`:MEASure:ADISplay?` → `:MEAS:ADIS?` |

### 文档符号（不随命令发送）

| 符号 | 含义 |
|------|------|
| `{}` | 可选参数组，必须选其一 |
| 竖线 `\|` | 分隔可选项 |
| `[]` | 可省略部分 |
| `<>` | 必须用有效值替换 |
| `<n>` / `<suffix>` | 通道号 / 序号后缀 |

---

## 2. 参数数据类型

| 类型 | 记号 | 说明 | 例子 |
|------|------|------|------|
| 布尔 | Bool | `ON`/`OFF` 或 `1`/`0`；查询固定返回 `1`/`0` | `:MEASure:ADISplay ON` |
| 离散 | Discrete | 枚举值，查询返回缩写形式 | `:ACQuire:TYPE NORMal` |
| 整数 | NR1 | 十进制整数，不允许小数 | `:DISPlay:GBRightness 50` |
| 实数 | NR2 | 带小数点的数 | `:CHANnel1:SCALe 0.1` |
| 实数 | NR3 | 科学计数法，查询多返回此格式 | `8.888889e-03` |
| 字符串 | ASCII String | 用引号包裹的 ASCII 串 | `:SYSTem:OPTion:INSTall "XXXX"` |
| 块数据 | Block | IEEE 488.2 明确长度块（见第 5 节） | `:WAVeform:DATA?` |

### 特殊数值

| 值 | 含义 |
|------|------|
| `DEFault` | 恢复该参数的默认值 |
| `MINimum` / `MAXimum` | 取该参数允许的最小 / 最大值，查询可用 `:CMD? MAX` |
| `INFinity` / `NINFinity` | 正 / 负无穷（9.9e37 / -9.9e37） |
| `NAN` | 非数字（9.91e37） |

---

## 3. 单位与后缀

| 类别 | 后缀 |
|------|------|
| 幅度 / 功率 | `V`、`A`、`W`、`dBm`、`dB` |
| 时间 / 频率 | `S`、`HZ`、`KHZ`、`MHZ`、`GHZ`、`PCT`（百分比） |
| 倍率 | `EX`1e18 `PE`1e15 `T`1e12 `G`1e9 `MA`1e6 `K`1e3 `M`1e-3 `U`1e-6 `N`1e-9 `P`1e-12 `F`1e-15 |

> **实践注意**：很多仪器（包括 RIGOL 示波器）只接受**纯数值**，
> 单位由命令隐含决定；随参数发送单位可能报错。以具体仪器的命令说明为准。

---

## 4. IEEE 488.2 通用命令（`*` 开头）

| 命令 | 作用 | 典型返回值 |
|------|------|-----------|
| `*IDN?` | 识别仪器 | `RIGOL TECHNOLOGIES,DS1202Z-E,DS1ZD170800001,00.06.02` |
| `*RST` | 复位（不改变通信接口配置） | — |
| `*CLS` | 清状态 / 清错误队列 | — |
| `*OPC?` | 操作完成查询，用于同步 | `1` |
| `*WAI` | 等待所有重叠命令完成 | — |
| `*ESR?` | 标准事件寄存器（bit0=OPC, bit5=命令错误, …） | `0` |
| `*ESE` / `*SRE` | 事件 / 服务请求使能 | — |
| `*STB?` | 状态字节 | `0` |
| `*TST?` | 自检 | `0`（通过） |
| `*SAV` / `*RCL` | 保存 / 调用仪器状态（0-9） | — |

### 同步建议

```
:TRIGger:SINGle;*OPC?      ; 触发单次并等待完成
:WAVeform:DATA?            ; 再读波形，保证数据已就绪
```

---

## 5. 状态报告模型

```
                          ┌── 标准事件寄存器  *ESR?  (*ESE 使能)
   状态字节 *STB? ────────┼── 操作状态寄存器  STATus:OPERation:…?
                          ├── 可疑数据寄存器  STATus:QUEStionable:…?
                          └── 错误队列       SYSTem:ERRor?
```

每个 SCPI 寄存器组提供：

| 后缀 | 含义 |
|------|------|
| `:CONDition?` | 实时状态，读不清零 |
| `:EVENt?` | 已锁存事件，**读取后清零** |
| `:ENABle` | 使能位掩码 |
| `:PTRansition` / `:NTRansition` | 正 / 负跳变过滤 |

错误排查首选 `SYSTem:ERRor?`，返回 `0,"No error"` 表示无错误。

---

## 6. 块数据传输（Definite Length Block）

二进制查询（波形、屏幕截图）返回：

```
# <N> <N 位十进制长度> <长度个字节的数据> <结束符>
```

| 示例 | 含义 |
|------|------|
| `#800001200<data>` | N=8，长度 = 00001200 = 1200 字节 |
| `#4200<data>` | N=4，长度 = 0200 = 200 字节 |

解析步骤：读 `#` → 读 1 位数字 N → 读 N 位十进制长度 → 读该长度的数据 → 读掉结束符。

---

## 7. 物理接口

| 接口 | 资源串示例 | 说明 |
|------|-----------|------|
| GPIB | `GPIB0::1::INSTR` | IEEE 488.1 总线 |
| USB-TMC | `USB0::0x1AB1::0x04CE::DS1ZD170800001::INSTR` | 即插即用，VISA |
| LAN / LXI | `TCPIP0::192.168.1.10::INSTR` | VXI-11；RIGOL 另支持 **RAW TCP 5555** |
| 串口 | `ASRL1::INSTR` | RS-232 |

在 Linux 上无 NI-VISA 时可用的替代方案：

- **RAW TCP**：直连 `host:5555`（RIGOL / 多数国产仪器支持）
- **USB-TMC 字符设备**：`/dev/usbtmc0`（内核 `usbtmc` 模块）
- **`python-usbtmc` / `pyvisa-py`**：纯 Python 的 VISA 实现

---

## 8. 常见子系统（SCPI 卷二）

| 子系统 | 含义 | 典型命令 |
|--------|------|---------|
| `:CONFigure` | 一键配置测量 | `:CONFigure:VPP CHANnel1` |
| `:MEASure` | 测量 | `:MEASure:ITEM? VPP,CHANnel1` |
| `:SENSe` | 输入/采集前端 | `:SENSe:VOLTage:RANGe` |
| `:CALCulate` | 后处理/数学 | `:CALCulate:MATH:EXPRession` |
| `:TRIGger` | 触发 | `:TRIGger:EDGe:LEVel 0.16` |
| `:INITiate` / `:ABORt` | 启动 / 终止采集 | `:INITiate:IMMediate` |
| `:FETCh` | 取已完成的测量结果 | `:FETCh:VPP?` |
| `:READ` | 启动 + 等待 + 取结果 | `:READ:VPP?` |
| `:SAMPle` | 采样计数 | `:SAMPle:COUNt 100` |
| `:STATus` | 状态 | `:STATus:OPERation:EVENt?` |
| `:SYSTem` | 系统 | `:SYSTem:ERRor?`、`:SYSTem:VERSion?` |
| `:DISPlay` | 显示 | `:DISPlay:DATA?`（截图） |
| `:FORMat` | 数据格式 | `:FORMat:DATA ASCii` |
| `:MMEMory` | 大容量存储 | `:MMEMory:STORe` |

---

## 9. 排错清单

| 现象 | 可能原因 | 处理 |
|------|---------|------|
| 无响应 | 接口/资源串错误、未进远程模式 | 先发 `*IDN?` 验证链路 |
| 命令报错 | 参数越界、单位错误、拼写错误 | 查 `SYSTem:ERRor?` |
| 读到的数据是旧的 | 未同步 | 加 `*OPC?` 或 `*WAI` |
| 波形数据长度对不上 | 未解析 IEEE 块头 | 按第 6 节解析 `#N<len>` |
| 缩写不识别 | 缩写未写全大写字母 | 用全称或写全大写部分 |
| 查询返回科学计数法 | 正常 | 解析时按 NR3 处理 |
