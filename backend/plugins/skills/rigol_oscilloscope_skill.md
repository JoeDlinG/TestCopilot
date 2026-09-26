---
name: RIGOL 示波器
protocol: rigol_oscilloscope
keywords: rigol, 普源, 示波器, oscilloscope, ds1000z, ds1000z-e, ds1202z-e, mso5000, 波形, 测量, 触发, scpi
---

# RIGOL 示波器测试用例生成 Skill

本 Skill 指导 AI 为 **RIGOL（普源精电）数字示波器**生成 AITestLab 测试用例。
设备协议名 `rigol_oscilloscope`，插件见 `docs/RIGOL_OSCILLOSCOPE_PLUGIN.md`。

## 命令生成规则

1. 每个测试步骤的 action 写 **SCPI 命令字符串**（推荐）或字典：
   - 字符串：`"*IDN?"`、`":MEASure:ITEM? VPP,CHANnel1"`、`:CHANnel1:SCALe 1`
   - 字典：`{"command": ":CHANnel1:SCALe", "value": 1}`
   - 波形：`{"action": "waveform", "channel": "CHANnel1", "include_data": false}`
2. `device_type` 填 `oscilloscope`，`devices_required` 包含 `rigol_oscilloscope`。
3. 设置类参数**只写纯数值**（如 `0.16` 表示 160 mV），不要带单位。
4. 查询命令必须带 `?`；测量值返回科学计数法（如 `8.888889e-03`）。

## 标准测试流程

```
*IDN?                          ; 识别仪器
*RST                           ; 复位
:CHANnel1:PROBe 10             ; 探头比
:CHANnel1:SCALe 1              ; 垂直刻度
:TIMebase:SCALe 1e-3           ; 时基
:TRIGger:MODE EDGE             ; 触发模式
:TRIGger:EDGe:SOURce CHANnel1  ; 触发源
:TRIGger:EDGe:LEVel 0.16       ; 触发电平
:TRIGger:SWEep NORMal          ; 触发方式
:MEASure:ITEM VPP,CHANnel1     ; 开启测量项
:RUN                           ; 启动
:MEASure:ITEM? VPP,CHANnel1    ; 读测量值 → 结果解析判定
SYSTem:ERRor?                  ; 确认无错误
```

## 测试场景模板

### 连接与识别
- `*IDN?` → 期望含 `RIGOL`、型号、序列号、固件版本四段
- `*TST?` → 期望 `0`

### 设置与回读（写读一致性）
- `:CHANnel1:SCALe 1` → `:CHANnel1:SCALe?` 期望 `1.000000e+00`
- `:TIMebase:SCALe 1e-3` → `:TIMebase:SCALe?` 期望 `1.000000e-03`
- `:CHANnel1:PROBe 10` → `:CHANnel1:PROBe?` 期望 `10`
- `:TRIGger:EDGe:LEVel 0.16` → `:TRIGger:EDGe:LEVel?` 期望 `1.600000e-01`

### 测量与判定
- `:MEASure:ITEM VPP,CHANnel1` 后 `:MEASure:ITEM? VPP,CHANnel1`
  → 结果解析取 `dec`，设上下限判 PASS/FAIL
- `:MEASure:ITEM? FREQuency,CHANnel1` → 频率判定
- 统计量：`:MEASure:STATistic:RESet` 后多次读取，考察一致性

### 波形采集
- `:STOP` → `{"action":"waveform","channel":"CHANnel1"}` → 期望 `points > 0`
- 比对不同时基下的 `points` 变化
- 用波形数据的 `vpp` / `vmax` / `vmin` 与 `:MEASure:ITEM? VPP` 交叉校验

### 触发场景
- `:TRIGger:SWEep SINGle` + `:TFORce` → 单次强制触发后能读到波形
- 触发电平设在信号幅值之外 → 期望无触发 / 测量值异常（边界场景）

### 边界与错误
- 垂直刻度设为量程外（如 500 V @10X）→ 期望 `SYSTem:ERRor?` 非 0
- 未开微调时设非 1-2-5 步进刻度 → 期望被就近取整（回读比对）
- 拼错命令 → 期望 `SYSTem:ERRor?` 报错
- 仪器断电 / 错误 IP → 期望连接超时

## 结果解析配置建议

| 返回 | 类型 | 说明 |
|------|------|------|
| `8.888889e-03` | `dec` / `string` | 科学计数法数值 |
| `RIGOL TECHNOLOGIES,DS1202Z-E,…` | `string` | 按偏移截取型号 / 固件 |
| `1` / `0` | `bool` / `dec` | 开关状态 |
| 波形动作返回 | JSON 对象 | 插件返回 dict，含 `points`/`vpp`/`vmax`/`vmin`/`vavg`/`vrms` |

## 生成要求

- 覆盖 **识别 → 复位 → 配置 → 回读 → 触发 → 测量 → 判错** 七个环节。
- 每个设置步骤配一条回读验证（写读一致性）。
- 长操作前后用 `*OPC?` 同步；读波形前先 `:STOP`。
- 结束前用 `SYSTem:ERRor?` 确认无错误残留。
- 测量用例给出明确的数值上下限，而不是"有返回值即可"。
