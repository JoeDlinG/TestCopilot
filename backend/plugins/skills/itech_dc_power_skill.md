---
name: ITECH 艾德克斯可编程直流电源
protocol: itech_dc_power
keywords: itech, 艾德克斯, 可编程直流电源, IT6800, IT6860A, IT6500, SCPI, RS232, RS485, LAN
---

# ITECH 艾德克斯可编程直流电源测试用例生成 Skill

## 适用范围

- 设备协议固定为 `itech_dc_power`，`device_type = power_supply`。
- 接口：串口 RS-232 / RS-485 或 LAN（默认串口；LAN 端口 IT6500 等机型选配）。
- 机型：IT6800 / IT6860A / IT6500 系列。

## 命令生成规则

1. 每个 action 写 **SCPI 字符串**或字典，二选一：
   - 字符串：`"*IDN?"`、`"VOLT 12"`
   - 字典：`{"action": "set_voltage", "value": 12}`；查询用 `{"action": "measure_voltage"}`
2. 查询必须带 `?`（字典 action 会自动生成）；设置命令不带。
3. 数值必须有限，禁止 NaN / Infinity；电压单位 V、电流单位 A。
4. `devices_required` 填 `itech_dc_power`，并引用已连接的可编程电源设备。

## 推荐步骤模板

| 步骤 | 命令 | 预期 / 判定 |
|---|---|---|
| 1 识别 | `*IDN?` | 应答包含 `ITECH` |
| 2 设电压 | `VOLT 12` | 无异常（返回 OK） |
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
- 设置电压电流时输出应处于 OFF；输出状态可用 OUTP? 回读。IT6800 帧格式协议与 SCPI 是两套命令，须在面板把 CMD 设为 SCPI。
- 不要生成 `*RST` / `CALibration` 类命令到常规测试流程，除非用例明确要求。
