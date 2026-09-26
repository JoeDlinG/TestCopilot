# SCPI 协议资料

本目录存放 SCPI（Standard Commands for Programmable Instruments，可编程仪器标准命令）
的官方协议文件，供 AITestLab 平台编写 SCPI 类设备的插件 / Skill / 测试用例时查阅。

## 文件清单

| 文件 | 来源 | 说明 |
|------|------|------|
| `SCPI-99_Volume1_Syntax_and_Style.pdf` | [IVI Foundation](https://www.ivifoundation.org/downloads/SCPI/scpi-99.pdf) | **SCPI 1999.0 卷一：语法与风格**（官方原版，约 4.2 MB） |

> 卷一（Syntax and Style）是编写/解析 SCPI 命令必须遵守的规范：命令头、关键字缩写、
> 参数数据类型、表达式、状态报告模型、`*RST` 条件、命名约定等。
> 卷二（命令参考）、卷三（数据交换格式）、卷四（仪器类别）由同一页面发布，
> 需要时可到 <https://www.ivifoundation.org/About-IVI/scpi.html> 下载。

- 平台内的可机读版本：`backend/plugins/manuals/scpi.md`（手册）
- 平台内的用例生成 Skill：`backend/plugins/skills/scpi_skill.md`

---

## SCPI 要点速查（依据 SCPI-99 卷一）

### 1. 命令语法

```
:ACQuire:TYPE <type>      ← 设置命令
:ACQuire:TYPE?            ← 查询命令（末尾加 ?）
:MEASure:ITEM VPP,CHAN1   ← 关键字与第一个参数以空格分隔
```

- 命令串通常以 `:` 开头，关键字之间用 `:` 分隔，形成**树状层级**
  （根关键字 + 二级关键字 + …）。
- 同一命令的多个参数用 `,` 分隔。
- `?` 结尾表示查询；查询返回该命令的当前值。
- 命令**大小写不敏感**。缩写时**必须写全所有大写字母**：
  `:MEASure:ADISplay?` → `:MEAS:ADIS?`。

### 2. 文档符号约定（书写时不随命令发送）

| 符号 | 含义 |
|------|------|
| `{}` | 花括号内为可选参数，通常配合竖线使用，必须选其一 |
| 竖线 `\|` | 分隔多个可选参数，必须选其一 |
| `[]` | 方括号内内容可省略（如可省略的默认节点） |
| `<>` | 尖括号内必须用有效值替换 |
| `<n>` | 通道 / 序号后缀，如 `CHANnel1`、`CHANnel2` |

### 3. 参数数据类型（SCPI-99 第 7 章）

| 类型 | 说明 | 示例 |
|------|------|------|
| Bool | `ON` / `OFF` / `1` / `0`；查询返回 `1` 或 `0` | `:MEASure:ADISplay ON` |
| Discrete | 枚举值，只能取列出的值；查询返回缩写 | `:ACQuire:TYPE NORMal`（或 `AVERages`、`PEAK`、`HRESolution`） |
| Integer (NR1) | 整数，不能带小数 | `:DISPlay:GBRightness 50` |
| Real (NR2/NR3) | 实数，支持小数与科学计数法；查询常返回科学计数法 | `:TRIGger:TIMeout:TIMe 1.6e-08` |
| ASCII String | ASCII 字符串 | `:SYSTem:OPTion:INSTall <license>` |

### 4. 单位与后缀（SCPI-99 7.5 / IEEE 488.2 7.7.3）

- 基本单位：`V`、`A`、`W`、`dBm`、`S`（秒）、`Hz`、`OHM`。
- 倍率后缀：`EX`(1e18)、`PE`(1e15)、`T`(1e12)、`G`(1e9)、`MA`(1e6)、`K`(1e3)、
  `M`(1e-3)、`U`(1e-6)、`N`(1e-9)、`P`(1e-12)、`F`(1e-15)、`A`(1e-18)。
- **注意**：多数仪器（含 RIGOL 示波器）只接受**纯数值 + 默认单位**，
  不接受随参数一起发送的单位后缀 —— 单位以各命令说明为准。

### 5. IEEE 488.2 通用命令（`*` 开头，与仪器类型无关）

| 命令 | 名称 | 作用 |
|------|------|------|
| `*CLS` | Clear Status | 清除状态寄存器与错误队列 |
| `*ESE` / `*ESE?` | Standard Event Status Enable | 标准事件使能 |
| `*ESR?` | Standard Event Status Register | 读标准事件寄存器（错误检查常用） |
| `*IDN?` | Identification Query | **识别仪器**，返回 `厂商,型号,序列号,固件版本` |
| `*OPC` / `*OPC?` | Operation Complete | 操作完成同步（`*OPC?` 返回 `1`） |
| `*RST` | Reset | 复位到默认状态（不改变 IO 配置） |
| `*SRE` / `*SRE?` | Service Request Enable | 服务请求使能 |
| `*STB?` | Read Status Byte | 读状态字节 |
| `*TST?` | Self-Test Query | 自检，返回 `0` 表示通过 |
| `*WAI` | Wait-to-Continue | 等待前面所有重叠命令执行完 |

### 6. 状态报告模型（SCPI-99 第 9 章）

```
                        ┌── Standard Event Status Register (*ESR?)
                        ├── Operation Status Register (STATus:OPERation?)
     Status Byte (*STB?)┤
                        ├── QUEStionable Data/Signal Status Register (STATus:QUEStionable?)
                        └── Message Available / Event Status Enable ...
```

- 每个寄存器都配 `CONDition?`（当前状态）、`EVENt?`（已锁存事件，读后清零）、
  `ENABle`（使能位）、`PTRansition` / `NTRansition`（跳变过滤）。
- 自动化测试推荐做法：命令后发 `*OPC?` 或轮询 `*ESR?`，确认命令已生效再读取结果。

### 7. 读取数据块（IEEE 488.2 明确长度块）

`:WAVeform:DATA?`、`:DISPlay:DATA?` 等返回二进制数据时，使用
**definite length block** 格式：

```
# <N> <长度，N 位十进制数字> <数据字节 …> <结束符>
```

例：`#800001200` 表示后面有 1200 字节数据。解析时必须先读 `#`，
再读 1 位数字 `N`，再读 `N` 位长度，最后按长度读数据。

---

## 在 AITestLab 中的用法

1. 安装/启用 `RIGOL 示波器` 插件（协议 `rigol_oscilloscope`），见
   `docs/RIGOL_OSCILLOSCOPE_PLUGIN.md`。
2. 编写测试用例时可直接下发 SCPI 字符串（如 `*IDN?`、`:MEASure:ITEM? VPP,CHANnel1`），
   或用字典形式 `{"command": ":CHANnel1:SCALe", "value": 0.1}`。
3. 结果解析：查询返回的是 ASCII 文本，用结果解析配置的
   `dec` / `string` / `hex` 类型按起始位取值即可。
