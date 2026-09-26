---
name: SCPI 通用协议
protocol: scpi
keywords: scpi, scpi协议, 程控仪器, ieee488.2, 仪器控制, visa, usbtmc, 远程控制, 自动化测量
---

# SCPI 测试用例生成 Skill

本 Skill 指导 AI 为**任意 SCPI 程控仪器**（示波器、电源、信号源、万用表、电子负载…）
生成 AITestLab 测试用例。

## 适用范围

- 仪器通过 SCPI 命令远程控制（GPIB / USB-TMC / LAN / RS-232 / VISA）。
- 已有具体仪器插件时（如 `rigol_oscilloscope`），优先使用**该仪器的 Skill**；
  本 Skill 作为通用兜底，或用于尚未提供专用插件的 SCPI 仪器。

## 命令生成规则

1. 每个测试步骤的 action 直接写 **SCPI 命令字符串**（推荐）或字典：
   - 字符串：`"*IDN?"`、`":MEASure:ITEM? VPP,CHANnel1"`、`":CHANnel1:SCALe 0.1"`
   - 字典：`{"command": ":CHANnel1:SCALe", "value": 0.1}`
2. 查询命令必须带 `?`；设置命令不带。
3. `device_type` 按仪器种类填（`oscilloscope` / `power_supply` / `dmm` …），
   `devices_required` 包含对应协议名。
4. 命令**大小写不敏感**；使用缩写时必须写全所有大写字母（`:MEAS:ITEM?` 合法，
   `:MEASU:ITEM?` 非法）。

## 标准测试流程模板

一个健壮的程控测试序列应按此顺序：

```
*IDN?                  ; 1. 识别仪器，确认型号与固件
*RST                   ; 2. 复位到已知状态
*CLS                   ; 3. 清状态与错误队列
<配置命令…>             ; 4. 设置量程 / 时基 / 触发 / 通道
*OPC?                  ; 5. 等待配置生效
<触发 / 启动命令>        ; 6. :INITiate:IMMediate、:TRIGger:SINGle
*OPC?                  ; 7. 等待采集完成
<读取命令…>             ; 8. :MEASure:ITEM? / :FETCh? / :WAVeform:DATA?
SYSTem:ERRor?          ; 9. 检查是否产生错误（期望 0,"No error"）
```

## 测试场景模板

### 连接与识别
- `*IDN?` → 期望返回 `厂商,型号,序列号,固件版本` 四段，厂商名匹配
- `*TST?` → 期望 `0`（自检通过）

### 设置与回读验证（最重要）
- 设置 → 回读 → 比对。例：
  - 写 `:CHANnel1:SCALe 0.1`，读 `:CHANnel1:SCALe?`，期望 ≈ 0.1
  - 写 `:TIMebase:SCALe 1e-3`，读 `:TIMebase:SCALe?`，期望 ≈ 1e-3
- 每个设置类命令都应配一条回读步骤。

### 测量与判定
- 测量命令返回 ASCII 数值，用**结果解析配置**取值并设上下限。
- 例：`:MEASure:ITEM? VPP,CHANnel1` → 解析为 `dec`，判 `最小值/最大值`。

### 边界与错误场景
- 参数取 `MINimum` / `MAXimum` → 回读应为极值，不报错
- 参数越界（超出量程）→ 期望 `SYSTem:ERRor?` 返回非 0 错误
- 拼错关键字 → 期望 `SYSTem:ERRor?` 返回命令错误（bit5）
- 仪器未连接 / 错误资源串 → 期望连接超时

### 同步与时序
- 长操作后未同步就读 → 期望读到旧值或不确定值（用于验证 `*OPC?` 的必要性）

## 结果解析配置建议

| 返回内容 | 数据类型 | 说明 |
|---------|---------|------|
| `8.888889e-03` | `dec` / `string` | 科学计数法，建议用 `string` 再看是否需要数值化 |
| `RIGOL TECHNOLOGIES,DS1202Z-E,…` | `string` | 按字节偏移截取字段 |
| `1` / `0` | `bool` / `dec` | 布尔或状态位 |
| `#800001200<data>` | — | 二进制块，交给插件的波形动作处理，不要手工解析 |

## 生成要求

- 覆盖 **识别 → 复位 → 配置 → 回读 → 触发 → 测量 → 判错** 七个环节。
- 每个设置步骤都配一条回读验证步骤（写读一致性）。
- 每条用例包含明确的期望结果（数值范围 / 错误码 / 超时）。
- 长操作前加 `*OPC?` 同步，避免竞态。
- 结束前用 `SYSTem:ERRor?` 确认无错误残留。
