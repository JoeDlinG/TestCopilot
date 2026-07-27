---
name: Modbus RTU
protocol: modbus_rtu
keywords: modbus, modbus rtu, 寄存器, 线圈
---

# Modbus RTU 测试用例生成 Skill

本 Skill 指导 AI 为 Modbus RTU 设备生成测试用例。

## 命令生成规则

1. 每个测试步骤的 action 使用 JSON 载荷描述：`{"function_code": <fc>, "register_address": <addr>, "count": <n>}`。
2. `device_type` 填 `modbus`，`devices_required` 包含 `modbus_rtu`。
3. 从站地址（slave_id）在连接配置中指定，命令内无需重复。

## 测试场景模板

### 读操作
- 读保持寄存器：`{"function_code": 3, "register_address": 0, "count": 2}` → 期望返回寄存器数组
- 读输入寄存器：`{"function_code": 4, ...}`；读线圈：`{"function_code": 1, ...}`

### 写操作
- 写单个寄存器：`{"function_code": 6, "register_address": 0, "value": 1234}` → 回读验证
- 写多个寄存器：`{"function_code": 16, "register_address": 0, "values": [1, 2, 3]}`

### 边界与错误场景
- 非法寄存器地址（超出映射范围）→ 期望异常码 02（Illegal Data Address）
- 非法功能码 → 期望异常码 01（Illegal Function）
- count 超过 125（读寄存器上限）→ 期望异常码 03（Illegal Data Value）
- 从站无响应（错误 slave_id）→ 期望超时

## 生成要求

- 覆盖读、写、回读验证、边界、异常五类场景。
- 每条用例包含明确的期望结果（返回值 / 异常码 / 超时）。
