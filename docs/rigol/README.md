# RIGOL 示波器资料

本目录存放从 RIGOL（普源精电）官网下载的示波器**编程手册**（SCPI 远程控制），
供 AITestLab 平台的 `rigol_oscilloscope` 插件 / Skill 编写与校对使用。

## 文件清单

| 文件 | 型号 / 系列 | 来源 |
|------|------------|------|
| `DS1000ZE_ProgrammingGuide_EN.pdf` | DS1000Z-E 系列（DS1202Z-E / DS1102Z-E），2020-04，文档号 PGA27101-1110 | <https://www.rigol.com/dam/global/downloads/brochures/en/program-guide/oscilloscopes/DS1000ZE_ProgrammingGuide_EN.pdf> |
| `MSO5000_ProgrammingGuide_EN.pdf` | MSO5000 系列 | <https://www.rigol.com/dam/global/downloads/brochures/en/program-guide/oscilloscopes/MSO5000_ProgrammingGuide_EN.pdf> |

中文版可从 <https://download.rigol.com/cn/Manual/Digital%20Oscilloscope/…> 获取；
更多型号见官网手册下载页 <https://www.rigol.com/intl/support.html>（Manual Download → Programming Manual）。

## 手册结构（以 DS1000Z-E 编程手册为例）

| 章节 | 内容 |
|------|------|
| Chapter 1 | 远程通信建立（USB / LAN）、SCPI 语法、符号、参数类型、缩写规则 |
| Chapter 2 | 命令系统：`:AUToscale` `:RUN` `:STOP` `:ACQuire` `:CHANnel<n>` `:CURSor` `:DECoder` `:DISPlay` `:ETABle` `:FUNCtion` `:LAN` `:MASK` `:MATH` `:MEASure` `:REFerence` `:STORage` `:SYSTem` `:TIMebase` `:TRIGger` `:WAVeform` + IEEE488.2 通用命令 |
| Chapter 3 | Excel / Matlab / LabVIEW / VB6 / VC6 编程示例（基于 VISA） |

## 平台内的可机读版本

- 手册（给 AI / 插件用）：`backend/plugins/manuals/rigol_oscilloscope.md`
- 用例生成 Skill：`backend/plugins/skills/rigol_oscilloscope_skill.md`
- 插件使用说明：`docs/RIGOL_OSCILLOSCOPE_PLUGIN.md`

## 提取正文的命令

```bash
pdftotext -layout DS1000ZE_ProgrammingGuide_EN.pdf ds1000ze.txt
```
