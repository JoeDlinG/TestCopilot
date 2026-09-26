# Mini Gateway 100 使用手册

## 1. 设备概述

Mini Gateway 100 是一款多功能测试网关，通过 USB-C（CDC 虚拟串口）或 UART 与上位机通信，提供：

- 数字量输入 / 输出（DIG）
- 模拟量输入 / 输出（VOLT，含校准）
- 继电器矩阵（96 路，OPEN/CLOSE）
- 双通道 CAN 总线（配置、收发）
- RS-232 外接电源控制（电压 / 电流设定与回读）
- 以太网参数、RTC 实时时钟、SD 卡存储管理

## 2. 连接参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| port | USB-C CDC 串口设备路径 | /dev/ttyACM0 |
| baudrate | 波特率（用户可选） | 115200 |
| board_id | 板卡 ID（0-99） | 11 |
| timeout | 读取超时（秒） | 2.0 |

串口参数固定为：8 数据位、无校验、1 停止位。

## 3. 协议格式

- 命令帧：`@<ID>_<COMMAND>=<PARAMETERS>;`，以 `@` 开头、`;` 结尾。
- 响应帧：`[yy/mm/dd,hh:mm:ss.msec,size]#<ID>_<COMMAND>=<RESULT>;`
- 请求 / 应答模式：必须收到上一条命令的应答后才能发送下一条（设备侧超时 1.5 s）。

### 3.1 取值格式硬性要求（已在真机验证）

- **十六进制必须大写 `0X` 前缀**：`0X13`、`0X850201`。小写 `0x13` 设备不识别（无应答）。
- **CAN 波特率只支持**：`10K / 20K / 33.3K / 40K / 83.3K / 100K / 125K / 250K / 500K / 1000K(1M)`，
  必须大写 K。`500000` 或 `500k` 均返回 `NOT_SUPPORT`。
- **CONFIG 之前必须先 `TSTOP`**；`TSTRT` 生效后再 `CONFIG` 会返回 `UNAVAILABLE`。
- `MSGTX` 的数据必须带 `0X`；`MSGRX` 必须使用 `CONFIG` 定义为 `RX` 的别名。

## 4. 命令参考

| 命令 | 语法 | 说明 |
|------|------|------|
| HELLO | `@<ID>_HELLO;` | 与板卡握手，确认通信正常 |
| SYSID | `@<ID>_SYSID;` | 获取设备软件版本 / 系统 ID |
| PSUV | `@<ID>_PSUV=<voltage>;` | 设置 RS-232 外接电源输出电压 (V) |
| PSUC | `@<ID>_PSUC=<current>;` | 设置 RS-232 外接电源输出电流限制 (A) |
| PSDV | `@<ID>_PSDV;` | 读取外接电源输出电压反馈 |
| PSDC | `@<ID>_PSDC;` | 读取外接电源输出电流反馈 |
| ETH | `@<ID>_ETH=<TYPE>,<value>;` / `@<ID>_ETH;` | 设置 / 读取以太网 IP（SOURCE/MASK/GATEWAY） |
| RTC | `@<ID>_RTC=SET,<Y>,<M>,<D>,<WD>,<h>,<m>,<s>;` / `@<ID>_RTC=GET;` | 设置 / 读取实时时钟 |
| STORAGE | `@<ID>_STORAGE=<op>;` | 管理 SD 卡（DLSTART/DLSTOP/...） |
| SETDIG | `@<ID>_SETDIG=<channel>;` | 将指定数字输出置高 |
| CLRDIG | `@<ID>_CLRDIG=<channel>;` | 将指定数字输出置低 |
| GETDIG | `@<ID>_GETDIG=<channel>;` | 读取指定数字输入状态 |
| CALBRT | `@<ID>_CALBRT=VIN,<ch>,<FS\|OF>,<value>;` | 校准模拟输入/输出的 Scale/Offset |
| GETVOLT | `@<ID>_GETVOLT=<channel>;` | 读取模拟输入通道电压 |
| SETVOLT | `@<ID>_SETVOLT=<channel>,<voltage>;` | 设置模拟输出通道电压 |
| OPEN | `@<ID>_OPEN=R<ch1>[,R<ch2>...];` | 断开一个或多个继电器 (1-96) |
| CLOSE | `@<ID>_CLOSE=R<ch1>[,R<ch2>...];` | 闭合一个或多个继电器 (1-96) |
| CONFIG | `@<ID>_CONFIG=CAN<ch>,BAUDRATE,<baud>;` / `@<ID>_CONFIG=CAN<ch>,<dir>,<alias>,<IDtype>,<ID>;` | 配置 CAN 总线波特率 / 消息 ID |
| TSTRT | `@<ID>_TSTRT;` | 验证并启动当前配置 |
| TSTOP | `@<ID>_TSTOP;` | 复位当前配置 |
| MSGTX | `@<ID>_MSGTX=CAN<ch>,<alias>,<message>;` | 在指定 CAN 通道发送消息 |
| MSGRX | `@<ID>_MSGRX=CAN<ch>,<alias>,<size>;` | 在指定 CAN 通道接收消息 |
| PROCESS | `@<ID>_PROCESS=<id>,DEFINE,<granularity>,<totalsteps>;` | 定义实时进程（周期 = granularity × totalsteps） |
| PROCESS | `@<ID>_PROCESS=<id>,<step>,<command>;` | 添加进程动作（命令不带 `@11_` 与 `;`；step 取 1..totalsteps-1） |
| PROCESS | `@<ID>_PROCESS=<id>,END\|START\|STOP\|DELETE\|DEFINE;` | 结束定义 / 启动 / 停止 / 删除 / 查询进程 |
| SYNCHRO | `@<ID>_SYNCHRO=<OUT\|IN>,<START\|STOP>;` | 硬件同步（OUT 主模式 / IN 从模式）。**注意：V1.4.8 固件实测无应答，暂不可用，不要下发。** |

注：RS-232 外接电源 ON/OFF 命令（PSU）当前未实现（暂无应用场景）。

### 4.1 PROCESS（定时 / 周期执行）说明

- 可用动作命令：`CLOSE`、`OPEN`、`SETDIG`、`CLRDIG`、`GETDIG`、`SETVOLT`、`GETVOLT`、`MSGTX`、`MSGRX`。
- 动作命令在 PROCESS 中**不带** `@11_` 前缀，也**不带**结尾 `;`，例如：
  `@11_PROCESS=1,1,MSGTX,CAN1,MSG13,0X850201;`
- `<step>` 有效范围 `1` ~ `<totalsteps>-1`：`0` 返回 `WRONGPARA`，`>= totalsteps` 返回 `OUTOFRANGE`。
- `END` 必须在 `START` 之前发送；`DEFINE` 查询返回 `...,LOOP=<n>`（已执行循环数）。
- 「每 200 ms 发送一帧」示例：`@11_PROCESS=1,DEFINE,100,2;`（100 × 2 = 200 ms）+ 第 1 步动作。

## 5. 典型使用流程

1. 在「插件管理」中安装并启用 Mini Gateway 100 插件。
2. 点击「添加设备」自动创建设备，检查串口路径 / 波特率 / 板卡 ID。
3. 连接设备，用 `HELLO` 握手、`SYSID` 读取版本确认通信。
4. 按测试需求下发命令（数字量 / 模拟量 / 继电器 / CAN / 电源）。
5. CAN 测试流程：`CONFIG`（波特率与消息 ID）→ `TSTRT` → `MSGTX`/`MSGRX` → `TSTOP`。
