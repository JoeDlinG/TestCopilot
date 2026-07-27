---
name: Mini Gateway 100
protocol: mini_gateway100
keywords: mini gateway, mini gateway 100, minigateway, mg100, 网关, gateway
---

# Mini Gateway 100 测试用例生成 Skill

本 Skill 指导 AI 为 Mini Gateway 100 设备生成可执行的测试用例。

## 命令生成规则

1. 所有命令必须符合格式 `@<ID>_<COMMAND>=<PARAMETERS>;`，默认板卡 ID 为 11（如 `@11_SYSID;`）。
2. 无参数命令省略 `=`，如 `@11_HELLO;`、`@11_TSTRT;`。
3. 请求 / 应答模式：每个测试步骤只发送一条命令，等待应答后再进行下一步。
4. 测试用例的每个 step 的 `action` 中应给出确切命令字符串，`device_type` 填 `gateway`，`devices_required` 包含 `mini_gateway100`。

## 测试场景模板

### 通信握手（冒烟测试）
- `@11_HELLO;` → 期望收到确认应答
- `@11_SYSID;` → 期望返回软件版本号

### 数字量测试
- 置高：`@11_SETDIG=<ch>;` → 用 `@11_GETDIG=<ch>;` 或外部设备验证电平
- 置低：`@11_CLRDIG=<ch>;` → 验证电平为低
- 边界：通道号取最小 / 最大值；错误场景：非法通道号应返回错误

### 模拟量测试
- 输出：`@11_SETVOLT=<ch>,<voltage>;` → 用万用表或回环 `@11_GETVOLT=<ch>;` 验证
- 输入：`@11_GETVOLT=<ch>;` → 与施加电压比较，误差在允许范围内
- 校准：`@11_CALBRT=VIN,<ch>,FS,<value>;`（Scale）/ `OF`（Offset）

### 继电器测试
- 闭合：`@11_CLOSE=R<ch>;`，断开：`@11_OPEN=R<ch>;`（通道 1-96）
- 支持多路：`@11_CLOSE=R1,R2,R3;`
- 边界：R1 与 R96；错误场景：R0 / R97 应返回错误

### CAN 总线测试（标准流程）
1. `@11_CONFIG=CAN1,BAUDRATE,500000;` — 配置波特率
2. `@11_CONFIG=CAN1,TX,msg1,STD,0x123;` — 配置发送消息
3. `@11_TSTRT;` — 启动配置
4. `@11_MSGTX=CAN1,msg1,0102030405060708;` — 发送
5. `@11_MSGRX=CAN2,msg2,8;` — 接收并校验数据
6. `@11_TSTOP;` — 复位配置

### 电源控制测试（RS-232 外接电源）
- 设定电压：`@11_PSUV=<voltage>;` → 回读 `@11_PSDV;` 验证
- 设定限流：`@11_PSUC=<current>;` → 回读 `@11_PSDC;` 验证
- 注意：PSU ON/OFF 命令未实现，不要生成。

## 生成要求

- 覆盖正常、边界、错误三类场景。
- 每条用例含明确的期望结果（应答内容或物理量范围）。
- CAN 用例必须遵循 CONFIG → TSTRT → MSGTX/MSGRX → TSTOP 顺序。
- 测试前必须先用 HELLO/SYSID 确认通信。
