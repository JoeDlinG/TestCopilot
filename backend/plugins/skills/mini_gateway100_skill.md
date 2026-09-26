---
name: Mini Gateway 100
protocol: mini_gateway100
keywords: mini gateway, mini gateway 100, minigateway, mg100, 网关, gateway
---

# Mini Gateway 100 测试用例生成 Skill

本 Skill 指导 AI 为 Mini Gateway 100（MG100）生成**可被设备真实识别**的测试用例。
以下规则均在真实设备（固件 MGW100_V1.4.8）上验证过，生成命令时必须逐条遵守。

## 1. 命令格式（硬性）

1. 命令帧：`@<ID>_<COMMAND>=<PARAMETERS>;`，默认板卡 ID 为 **11**。
2. **必须以 `@` 开头、以 `;` 结尾**；无参数命令省略 `=`，如 `@11_HELLO;`。
3. 响应帧：`[yy/mm/dd,hh:mm:ss.msec,size]#<ID>_<COMMAND>=<RESULT>;`
4. 请求 / 应答模式：**必须收到上一条命令的应答后才能发送下一条**（设备侧 1.5 s 无应答则取消该命令）。
5. 每个测试步骤的 `action` 中给出**确切命令字符串**，`device_type` 填 `gateway`，`devices_required` 包含 `mini_gateway100`。

### 1.1 十六进制必须大写前缀 `0X`（关键）

所有十六进制值必须写成 **大写 `0X`** 前缀，例如 `0X13`、`0X10`、`0X850201`。
小写 `0x13` 设备**不识别**（无应答，2 s 超时）。

### 1.2 命令执行顺序（关键）

- 修改任何 `CONFIG` 之前**必须先发 `@11_TSTOP;`** 复位配置。
- 一旦执行 `@11_TSTRT;`（配置生效），再发 `CONFIG` 会返回 `UNAVAILABLE`。
- 正确顺序：**`TSTOP` → `CONFIG`(波特率) → `CONFIG`(消息 ID) → `TSTRT` → `MSGTX`/`MSGRX` → `TSTOP`**

## 2. CAN 总线测试

### 2.0 CAN 正常工作的前提条件（易遗漏，必须写进用例）

设备有 2 路高速 CAN（ISO 11898-2），通过前面板 **DB-9 母头**引出：

| 信号 | DB-9 引脚 |
|---|---|
| CAN1_L | Pin 2 |
| CAN1_H | Pin 7 |
| CAN2_L | Pin 1 |
| CAN2_H | Pin 8 |

- **必须通过 `@11_TSTRT;` 使配置生效**，否则 CAN 通道不工作（手册明确警告）。
- **终端电阻通过跳线激活**：CAN1 = **JP901**，CAN2 = **JP900**。与外部 CAN 工具通信时，
  两端都要有 120Ω 终端电阻，否则总线无 ACK、对端一帧也收不到。
- 两端波特率必须一致（如均为 500K）。
- 若对端收不到报文，优先排查：终端电阻跳线、CANH/CANL 是否接反或接错通道（CAN1/CAN2）、波特率。

### 2.1 波特率（关键）

语法：`@11_CONFIG=CAN<ch>,BAUDRATE,<baudrate>;`

**仅支持以下取值（大写 K / M）**：
`10K`、`20K`、`33.3K`、`40K`、`83.3K`、`100K`、`125K`、`250K`、`500K`、`1000K`（等价 `1M`）

- 正确：`@11_CONFIG=CAN1,BAUDRATE,500K;`
- 错误：`@11_CONFIG=CAN1,BAUDRATE,500000;` → 设备返回 `NOT_SUPPORT`
- 错误：`@11_CONFIG=CAN1,BAUDRATE,500k;`（小写 k）→ 设备返回 `NOT_SUPPORT` / `UNAVAILABLE`

### 2.2 配置消息 ID（TX / RX 别名）

语法：`@11_CONFIG=CAN<ch>,<direction>,<alias>,<ID type>,<ID>;`

- `<direction>`：`TX`（发送）或 `RX`（接收）。
- `<alias>`：消息别名，**不含空格，长度 < 12 字节**。
- `<ID type>`：`STD`（11 位）或 `EXT`（29 位）。
- `<ID>`：`0X` + 十六进制，STD 范围 `0X00`–`0X7FF`。

```
@11_CONFIG=CAN1,TX,MSG13,STD,0X13;
@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;
```

### 2.3 发送（MSGTX）

语法：`@11_MSGTX=CAN<ch>,<alias>,<message>;`

- `<alias>` 必须先用 `CONFIG` 定义为 **TX**。
- `<message>`：**以 `0X` 开头**的十六进制数据，**最长 8 字节**。
- 正确：`@11_MSGTX=CAN1,MSG13,0X850201;` → 应答 `CAN1,MSG13,3B_DATASENT`
- 错误：`@11_MSGTX=CAN1,MSG13,850201;`（缺 `0X`）→ 设备无应答

### 2.4 接收（MSGRX）

语法：`@11_MSGRX=CAN<ch>,<alias>,<size>;`

- `<alias>` 必须先用 `CONFIG` 定义为 **RX**（用 TX 别名读取不到数据）。
- `<size>`：要读取的字节数，最大 8。
- 应答：`CAN1,RPLY1,0X850102`（有数据）或 `CAN1,RPLY1,0X`（**空数据 = 未收到报文**）。
- **判定超时**：应答中 `0X` 后无数据字节，即视为未收到回复，用例应输出 `time out`。

### 2.5 标准 CAN 用例流程

```
@11_HELLO;
@11_TSTOP;
@11_CONFIG=CAN1,BAUDRATE,500K;
@11_CONFIG=CAN1,TX,MSG13,STD,0X13;
@11_CONFIG=CAN1,RX,RPLY1,STD,0X20;
@11_TSTRT;
@11_MSGTX=CAN1,MSG13,0X850201;
@11_MSGRX=CAN1,RPLY1,8;
@11_TSTOP;
```

## 3. 周期 / 定时发送（PROCESS）

每隔固定时间重复执行某个动作时，**必须**使用 PROCESS 功能（MG100 无其它定时发送手段）。

### 3.1 定义进程

`@11_PROCESS=<id>,DEFINE,<granularity>,<totalsteps>;`

- `<id>`：1–255，最多 32 个进程。
- `<granularity>`：步进粒度（ms），**必须是 10 的倍数**（10/20/30 ...）。
- `<totalsteps>`：总步数 1–4294967295。
- **循环周期 = granularity × totalsteps**（实测：100×2 → ~200 ms）。

### 3.2 添加动作

`@11_PROCESS=<id>,<step>,<command>;`

- `<command>`：动作命令，**不带 `@11_` 前缀，不带结尾 `;`**，可用命令：
  `CLOSE`、`OPEN`、`SETDIG`、`CLRDIG`、`GETDIG`、`SETVOLT`、`GETVOLT`、`MSGTX`、`MSGRX`。
- `<step>`：**有效范围 `1` ~ `totalsteps-1`**
  - `0` → `WRONGPARA`
  - 等于或大于 `totalsteps` → `OUTOFRANGE`

### 3.3 结束定义与控制

```
@11_PROCESS=<id>,END;     结束定义（START 之前必须发送）
@11_PROCESS=<id>,START;   启动
@11_PROCESS=<id>,STOP;    停止
@11_PROCESS=<id>,DELETE;  删除
@11_PROCESS=<id>,DEFINE;  查询参数，返回 ...,LOOP=<n>
```

### 3.4 「每 200 ms 发送一条 CAN 报文」完整示例

```
@11_HELLO;
@11_TSTOP;
@11_CONFIG=CAN1,BAUDRATE,500K;
@11_CONFIG=CAN1,TX,MSG13,STD,0X13;
@11_TSTRT;
@11_PROCESS=1,DEFINE,100,2;                       周期 = 100 x 2 = 200 ms
@11_PROCESS=1,1,MSGTX,CAN1,MSG13,0X850201;
@11_PROCESS=1,END;
@11_PROCESS=1,START;
... 运行一段时间后 ...
@11_PROCESS=1,STOP;
@11_TSTOP;
```

> 注意：动作里的 `MSGTX` 数据同样必须带 `0X` 前缀。

## 4. 数字量

- 数字**输入**（5 路，1–5）：`@11_GETDIG=<ch>;` → `#11_GETDIG=<ch>,<state>;`，`1` 高 / `0` 低。
- 数字**输出**（5 路，1–5）：置高 `@11_SETDIG=<ch>;`，置低 `@11_CLRDIG=<ch>;`，
  应答返回全部通道的十六进制掩码，如 `#11_SETDIG=0X13;`。
- 边界：通道 1 与 5；错误场景：通道 0 / 6 应返回错误。

## 5. 模拟量

- 模拟**输入**（板载 2 路，加 A20 扩展板为 1–50）：`@11_GETVOLT=<ch>;` → `#11_GETVOLT=<ch>,<voltage>;`
- 模拟**输出**（板载无，需 V10 扩展板，1–48）：`@11_SETVOLT=<ch>,<voltage>;`
- 校准：`@11_CALBRT=VIN,<ch>,FS,<value>;`（Scale）/ `OF`（Offset）
  模拟输出用 `VOUT`：`@11_CALBRT=VOUT,<ch>,FS,<value>;`

## 6. 继电器（需 RM10 扩展板，1–96）

```
@11_CLOSE=R1,R2,R3;    闭合（每个通道都要带 R 前缀）
@11_OPEN=R15,R65;      断开
```
应答返回全部继电器状态掩码，如 `#11_CLOSS=0X41;`。边界：R1 / R96；错误场景：R0 / R97。

## 7. 电源控制（RS-232 外接电源，SCPI）

```
@11_PSUV=<voltage>;    设定输出电压 (V)
@11_PSUC=<current>;    设定输出限流 (A)
@11_PSDV;              回读电压
@11_PSDC;              回读电流
```
注意：`PSU`（电源 ON/OFF）命令未实现，**不要生成**。

## 8. 其它命令

```
@11_SYSID;                                        读取软件版本
@11_ETH=SOURCE,192.168.0.131;                     设置 IP（SOURCE/GATEWAY/MASK）
@11_ETH;                                          读取 IP 配置
@11_RTC=SET,23,8,30,3,8,21,1;                     设置 RTC
@11_RTC=GET;                                      读取 RTC
@11_STORAGE=DLSTART; / @11_STORAGE=DLSTOP;        SD 卡配置下载
```

### 8.1 固件不支持、禁止生成的命令

- `@11_SYNCHRO=...`（硬件同步）：手册有记载，但 **V1.4.8 固件无任何应答**，不要生成。
- `@11_PSU=...`（电源 ON/OFF）：未实现，不要生成。

## 9. 生成要求

- 覆盖正常、边界、错误三类场景，每条用例给出明确期望结果。
- **测试开头必须用 `@11_HELLO;` 握手确认通信**（可加 `@11_SYSID;`）。
- CAN 用例：`TSTOP` → `CONFIG` → `TSTRT` → `MSGTX`/`MSGRX` → `TSTOP`。
- 定时 / 周期场景用 PROCESS，且周期 = `granularity × totalsteps`，动作步号 `1..totalsteps-1`，`END` 后再 `START`。
- 所有十六进制统一用大写 `0X`；波特率统一用 `500K` / `1000K` 这类大写写法。
- 接收判定：MSGRX 返回空数据（`0X`）即提示 `time out`。
