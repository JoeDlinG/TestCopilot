---
name: TDK-Lambda GENESYS+ 可编程直流电源
protocol: tdk_lambda_dc_power
keywords: tdk, tdk-lambda, lambda, genesys+, 可编程直流电源, SCPI, RS232, RS485, LAN
---

# TDK-Lambda GENESYS+ 可编程直流电源测试用例生成 Skill

## 适用范围

- 设备协议固定为 `tdk_lambda_dc_power`，`device_type = power_supply`。
- 接口：串口 RS-232 / RS-485 或 LAN（默认串口；LAN 端口 TCP socket 端口 8003（手册原文），UDP 8005）。
- 机型：GENESYS+ G+ / GH / GSP / GSPL 系列。

## 命令生成规则

1. 每个 action 写 **SCPI 字符串**或字典，二选一：
   - 字符串：`"*IDN?"`、`"VOLT 24"`
   - 字典：`{"action": "set_voltage", "value": 12}`；查询用 `{"action": "measure_voltage"}`
2. 查询必须带 `?`（字典 action 会自动生成）；设置命令不带。
3. 数值必须有限，禁止 NaN / Infinity；电压单位 V、电流单位 A。
4. `devices_required` 填 `tdk_lambda_dc_power`，并引用已连接的可编程电源设备。

## 推荐步骤模板

| 步骤 | 命令 | 预期 / 判定 |
|---|---|---|
| 1 识别 | `*IDN?` | 应答包含 `TDK-Lambda` |
| 2 设电压 | `VOLT 24` | 无异常（返回 OK） |
| 3 设电流 | `VOLT <A>` 对应品牌的 CURR 命令 | 无异常 |
| 4 开输出 | 品牌 output_on | 无异常 |
| 5 回读电压 | 品牌 measure_voltage | 数值在设定值 ±容差内 |
| 6 回读电流 | 品牌 measure_current | 数值 ≤ 限流值 |
| 7 关输出 | 品牌 output_off | 无异常 |

## 判定与解析

- 回读类步骤的结果解析选 `dec`，按 `min` / `max` 设容差，例如 12 V ±0.1 V → `min=11.9, max=12.1`。
- FAIL 是判定结果，不是设备告警；不要把它写进步骤的 `expected` 文本。
- 用例里不要假定设备已处于远程模式；连接后的 `*IDN?` 探测失败不影响连接。

## 安全约束

- **先设电压/电流，再开输出；先关输出，再改接线或量程。**
- 输出开关用 OUTP:STAT（不是 OUTP）；电压保护阈值用 VOLT:PROT:LEV。RS-485 多机从站地址由主电源负责寻址。
- 不要生成 `*RST` / `CALibration` 类命令到常规测试流程，除非用例明确要求。
