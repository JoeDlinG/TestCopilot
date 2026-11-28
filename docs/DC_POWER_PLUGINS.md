# 可编程直流电源插件（ITECH / TDK-Lambda / Chroma / Keysight）

四个品牌共用一份 SCPI 传输实现 `backend/app/services/scpi_power_transport.py`，
每个品牌一个独立插件文件 / 协议名（数据库注册、接口绑定、手册与 Skill 均以
`protocol` 为键，不能合并成一个插件）。默认支持 **RS-232 / RS-485 串口**与
**LAN TCP socket**，在「设备管理 → 配置接口」切换 serial / ethernet 即可。

## 1. 官方手册下载清单

原始 PDF 位于 `docs/dc_power/manuals/`（共 8 份，约 25 MB）：

| 品牌 | 协议 | 机型 | 串口默认 | LAN 默认 | 已下载手册 |
|---|---|---|---|---|---|
| ITECH | `itech_dc_power` | IT6800 / IT6860A / IT6500 系列 | 8 数据位 / 1 停止位 / 无校验（可 N/E/O） | IT6500 等机型选配 | `ITECH_IT6800_SCPI_CN.pdf`、`ITECH_IT6860A_UserManual_CN.pdf`、`ITECH_IT6800_UserManual_CN.pdf` |
| TDK-Lambda | `tdk_lambda_dc_power` | GENESYS+ G+ / GH / GSP / GSPL 系列 | 默认 115200（可用 SYST:BAUD 改） | TCP socket 端口 8003（手册原文），UDP 8005 | `TDK_GenesysPlus_UserManual.pdf`、`TDK_Genesys_LAN_Interface_Manual.pdf` |
| Chroma | `chroma_dc_power` | 62000P 系列（62006P / 62012P / 62024P / 62050P） | RS-232C 标准接口 | 以太网为选配卡（A620004 为 GPIB 卡） | `Chroma_62000P_Catalogue_CN.pdf` |
| Keysight | `keysight_dc_power` | E36300 / N5700 系列 | E36300 无原生 RS-232（USB/LAN/GPIB）；N5700 等带串口机型或 USB-串口适配器用此通道 | SCPI socket 标准端口 5025（手册原文），VXI-11 VISA 串为 TCPIP0::<IP>::inst0::INSTR | `Keysight_E36300_UsersGuide_EN.pdf` |

下载来源均为厂商官网：TDK `product.tdk.cn`、Keysight `www.keysight.com`、
Chroma `www.chromaate.com`、ITECH 官网资源镜像（IT6800 SCPI / IT6860A /
IT6800 用户手册）。Chroma 官网只公开型录，编程命令取自其 Operating &
Programming Manual 在线全文；Keysight N5700 编程命令取自官网支持页的
Language Reference 摘要。手册正文与命令出处逐条记录在各插件 docstring 和
`backend/plugins/manuals/<protocol>.md` 里。

> 打包说明：`aitestlab.spec` 会把整个 `docs/` 收进安装包，与既有的
> `docs/rigol/`、`docs/scpi/` 官方 PDF（约 17.9 MB）做法一致；新增 8 份约 25 MB。
> 插件运行只依赖 `backend/plugins/manuals/` 的 Markdown 摘要，不读取 PDF。
> 若后续要压缩安装包，可对 `docs/**/*.pdf` 统一做一层打包排除，而不是单独处理本目录。
>
> **版本库口径**：目标仓库是 public，`.gitignore` 排除 `/docs/dc_power/manuals/*.pdf`，
> 8 份 PDF 只在本地生成与保留；clone 后插件仍可用，按本表来源可重新下载。

## 2. 命令差异（同一 action → 各品牌 SCPI）

| action | ITECH | TDK-Lambda | Chroma | Keysight |
|---|---|---|---|---|
| 识别 | `*IDN?` | `*IDN?` | `*IDN?` | `*IDN?` |
| 设电压 | `VOLT {v}` | `VOLT {v}` | `SOUR:VOLT {v}` | `VOLT {v}` |
| 设电流 | `CURR {v}` | `CURR {v}` | `SOUR:CURR {v}` | `CURR {v}` |
| 开输出 | `OUTP ON` | `OUTP:STAT ON` | `CONF:OUTP ON` | `OUTP ON` |
| 关输出 | `OUTP OFF` | `OUTP:STAT OFF` | `CONF:OUTP OFF` | `OUTP OFF` |
| 实测电压 | `MEAS:VOLT?` | `MEAS:VOLT?` | `MEAS:VOLT?` | `MEAS:VOLT?` |
| 实测功率 | `MEAS:POW?` | — | `FETC:POW?` | — |
| 选通道 | — | — | — | `INST:SEL {ch}` |

## 3. 架构要点

- `ScpiPowerTransport`（`app/services/`）：串口经 `run_blocking` 走线程池、
  LAN 走 `asyncio` stream；三原语 `_write_line` / `_flush_input` / `_read_line`
  两条通道共用；`asyncio.Lock` 防止后台轮询抢走查询应答。
- `send()` 接受 SCPI 字符串、JSON 字符串、`{"command","value","query"}` 或
  `{"action","value"}`；查询返回应答文本，设置返回 `OK`。
- 异常分类：语义错 → `ValueError`（不断连）；断开/超时/OSError →
  `ConnectionError`（`device_service` 判为传输错并置离线），遵守 Issue #33 约束。
- `get_config_schema()` 的 `port` **只有 placeholder 无 default**（AST 门禁），
  并保留 `brand_key` / `idn_expect` 两个私有签名键供协议污染自愈识别。
- `PLUGIN_TRANSPORT_BINDINGS` / `PLUGIN_POLLUTION_TARGETS` 在
  `backend/app/core/interfaces.py` 各登记 4 条；不登记则界面切到 LAN 时
  `config.transport` 永远停在 `serial`（Issue #11 复发点）。串口绑定额外带
  `defaults.baudrate`（ITECH/Chroma/Keysight 9600、TDK-Lambda 115200）：
  LAN 切换会按接口规格清掉 `baudrate`，切回串口时若用户没重填，
  `apply_plugin_transport` 会恢复手册值，而不是通用串口的 115200。
- 「配置接口」写入的是接口规格键 `data_bits` / `stop_bits`，插件模板写的是
  驱动层键 `bytesize` / `stopbits`。`_connect_serial()` 优先读界面值，
  避免模板默认的 8N1 静默覆盖用户设置的 7E2。
- `manuals/<protocol>.md` 与 `skills/<protocol>_skill.md` 各 4 份，frontmatter
  的 `protocol` 与插件 `protocol_name` 一致，AI 助手按关键词自动挂载。

## 4. 启用步骤（运行时，必须做）

插件文件被扫描发现并不等于启用。数据库 `plugins` 表当前为空，需执行：

```text
GET  /api/plugins/discovered                 扫描 4 个新插件
POST /api/plugins/install                    protocol_type = <protocol_name>,
                                             module_name/class_name/file_path 取 discovered 结果
POST /api/plugins/{id}/enable                置 status = enabled
POST /api/plugins/{id}/add-device            用 get_device_template() 建设备
POST /api/devices/connect                    按 config 连接
```

也可在 `Test/fixtures/Project_TestDemo.json` 的 `plugins` 数组里补 4 条一次性导入。

## 5. 验证

`bash Test/run_all.sh` 中的两套电源回归：

- `test_dc_power_plugins`（249 项，纯 mock、无需硬件）：4 个协议唯一性、
  schema 门禁、串口与 LAN 双通道收发、action→SCPI 品牌差异、
  界面 `data_bits`/`stop_bits` 真正下传到 pyserial、双向传输绑定与品牌
  波特率恢复、异常分类、手册/Skill 资产与 frontmatter。
- `test_dc_power_api_chain`（78 项，需 `:8000` 后端）：走真实 HTTP 链路
  discovered → install → enable → add-device → 串口 → LAN → 切回串口，
  校验协议不被通用总线名覆盖、地址列镜像、旧接口键清理、手册波特率恢复；
  测试数据在 `finally` 中全部删除，服务未启动则打印 `[SKIP]` 并 exit 0。
