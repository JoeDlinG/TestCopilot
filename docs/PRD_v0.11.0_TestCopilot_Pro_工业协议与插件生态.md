# TestCopilot Pro 可行性研究与建设方案（第三版 · 协议中心）

> 日期：2026-10-23 ｜ 状态：**核心决策已确认，分类主轴已按协议重构**
> 目标：支撑「更多工业仪器与设备（插件库 + Skill 库）」「更多通信协议（Modbus 等）」「工业自动化设备协议（PLC / 工业相机 / 机械臂）」
>
> **已确认决策**：① 闭源商业发行 ② 汽车电子实验室 + 工业产线并行 ③ 双轨分发 + 必须支持离线导入 ④ 有 Modbus 设备 + PLC 可联调
> **⑤ PLC 与机械臂统一走 Modbus TCP 优先**（用户 PLC 支持 Modbus TCP，2026-10-23）
>
> **第三版核心变更（2026-10-23 用户澄清）**：
> **本程序不对 PLC 编程，只做通信层的交互与控制。因此不按品牌/设备品类分类，一律以「通信协议」为分类主轴。**
> 同理适用于相机、机械臂：不按厂商 SDK 分类，按「取流 / 控制协议」分类。
> → 连带影响：取消「点位表 / PLC 工程变量」这一层概念，改为**协议原语 + 裸地址**。

---

## 0. 结论先行

| # | 判断 | 依据 |
|---|---|---|
| 1 | **协议层面基本都能做**，没有技术禁区 | 逐个查证：Modbus / S7 / EtherNet/IP / MC / FINS / ADS / DoIP 均有 MIT/BSD/Apache 级许可的纯 Python 或预编译方案 |
| 2 | **瓶颈不在"协议库"，在"抽象"** | 现有管线是**字符串问答模型**：`send(str) → str` → `ResponseParser`（全程 `str()` 处理）→ `assert float(response) op x`。这套模型装得下 SCPI 文本和 CAN 帧，**装不下 PLC 的寄存器/DB 地址读写、机器人状态流、相机图像帧** |
| 3 | **风险集中在许可证 + 打包体积** | 海康/大华 SDK 禁再分发；`asyncua` 是 LGPL-3；`opencv` wheel 内含 LGPL FFmpeg；当前安装包 **21MB**，一个 OpenCV 就变 ~200MB |
| 4 | **以协议为中心反而简化了架构** | 不做 PLC 编程 → 不需要点位表/工程变量/符号表 → 一个协议驱动服务所有品牌，设备 = 协议 + 连接参数 + 能力声明 |

**一句话**：Pro 版的工程量 20% 在写驱动，80% 在把「字符串收发」升级为「协议原语 + 类型化返回值」，以及插件的分打包与分发。

---

## 0.1 四项决策带来的连锁约束（**硬要求**）

### A. 闭源商业发行 → 依赖许可红线

| 级别 | 依赖 | 处置 |
|---|---|---|
| 🚫 禁止打包 | `someipy`(GPL-3)、`scapy`(GPL-2) | SOME/IP 不做；底层抓包走 winpcap 自写或采购 |
| 🚫 禁止打包 | 海康/大华 MVS SDK（专有，§3.1 禁分销、禁与其他产品合并） | **只能**客户自装 MVS → 我们的插件 `sys.path.append` 调用；文档写明为客户侧前置条件 |
| ⚠️ 需隔离 | `asyncua`(LGPL-3) | 见 OPC UA 路线，**不可直接入主 exe** |
| ⚠️ 需声明 | `opencv-python`（Apache-2.0，wheel 内含 LGPLv2.1 FFmpeg） | ① 用 headless ② 不用视频时不打包 ffmpeg DLL（省 ~25MB）③「关于」页列第三方许可 + 提供 FFmpeg 可替换途径 |
| ⚠️ 需合规 | `pypylon`（wheel 110.8MB） | 外置可选包，遵守 EULA 8 项条件（不用 Basler 商标、保留版权、附免责） |
| ✅ 可用 | `pymodbus`(BSD-3)、`python-snap7`(MIT)、`doipclient`(MIT)、`pycomm3`(MIT)、`pyads`(MIT)、`pymcprotocol`(MIT)、`pysoem`(MIT) | 无限制 |

**OPC UA 路线（闭源下重定）**：
1. **优先：不做主通道**，话术引导走 Modbus TCP / S7 直连（免证书、免安全策略，体验更好）
2. 设备只支持 OPC UA 时：**open62541（MPL-2.0）编成独立 DLL + ctypes 绑定**，动态链接满足 MPL
3. 兜底：`asyncua` 独立子进程 + IPC，中风险，需法务确认

### B. 双轨 + 离线导入 → 工程要求

| 要求 | 落点 |
|---|---|
| 插件可依赖 exe 内没有的库 | 安装期 `pip install --target=<plugin>/_vendor`，运行时插入 `sys.path` |
| 离线导入 | `.aitestlab-plugin`（zip：manifest + driver + `_vendor` + skill + manual + selftest），UI 提供「导入离线包」 |
| 插件目录必须用户可写 | 迁出 `Program Files\...\_internal` → `%LOCALAPPDATA%\TestCopilot\plugins`，**NSIS 需同步调整** |
| 插件自证可用 | manifest 的 `deps` + `selftest.py`，安装后立即自检，失败标记 DISABLED 并给出原因 |

### C. 真机 → 验证策略

- P1 每个**协议**必须真机跑通完整链路：连接 → 原语读写 → 断言 → 生成代码 → 回放
- 真机记录进 `HISTORY.md`（参考 v0.8.3 PeakCAN 端到端跑通的记法）
- 无真机的协议交付时标注「未经真机验证」

---

## 1. 现状盘点（基于实际代码）

### 1.1 已有能力

| 能力 | 落点 | 备注 |
|---|---|---|
| 通信抽象层 | `app/communication/__init__.py`（524 行） | `CommunicationInterface` + 6 实现（SCPI/CAN/Serial/Ethernet/USB/Mock） |
| 原生协议集合 | `device_service.py:30` `_STANDARD_PROTOCOLS` | **硬编码**，加协议必须改这里 + `create_interface`（`:501-524`） |
| 插件契约 | `plugin_service.py:24` `BaseProtocolPlugin` | connect/disconnect/send/receive + `get_config_schema`/`get_device_template`/`get_commands` |
| 插件加载 | `plugin_service.py:213` `_exec_module()` | 每次 `connect_device()` 都遍历全部插件并逐个 exec（`device_service.py:239`），无缓存 |
| 插件编辑器 | `api/plugin_editor.py` + `pages/PluginEditor.tsx` + 4 模板 | 协议/设备驱动/数据解析/报告模板，支持在线 validate |
| Skill 库（雏形） | `plugins/skills/*_skill.md` + `plugins/manuals/*.md` | frontmatter(name/protocol/keywords)，`match_skills_for_text` 供 AI 挂载 |
| Modbus 状态 | `skills/modbus_rtu_skill.md` + `manuals/modbus_rtu.md` + `example_plugin.py`（**返回模拟数据**） | ⚠️ 有文档有 demo，**无真实实现** |

### 1.2 五个结构性缺口

| 缺口 | 现状 | 后果 |
|---|---|---|
| **G1 单值字符串契约** | `send(data) -> str`；`ResponseParser` 全程 `str()` | Modbus 寄存器数组、S7 字节块、相机帧无法进入判定与断言；硬塞 JSON 会污染日志、回放、趋势图 |
| **G2 无 manifest** | 插件 = 裸 `.py`，无依赖/能力/平台声明 | 装了依赖 `pymodbus`/`cv2` 的插件，exe 里没这些包 → 运行时 ImportError |
| **G3 无隔离、无签名** | 主进程 importlib 直接 exec 第三方代码 | 插件可任意读写宿主文件；一个插件 import 失败拖垮服务 |
| **G4 无分发通道** | "插件库" = 本地一个目录 | 无法交付给客户 |
| **G5 四层概念揉在一起** | `BaseProtocolPlugin` 同时承担 Transport + Protocol + 设备能力 + 类型语义 | 协议数量上涨后必然爆炸 |

---

## 2. 协议族矩阵（**分类主轴**）

> 一切以协议为准。设备 = 「某协议的一个连接实例」。同协议不同品牌**共用同一驱动**，差异只在连接参数与可选能力声明。

### 2.1 工业现场 / PLC 侧

| 协议 | 承载设备 | 协议原语 | 返回数据形态 | 库 | 许可 | Py3.13 | 档位 |
|---|---|---|---|---|---|---|---|
| **Modbus TCP** ⭐ | **PLC / 机械臂 / IO 模块 / 电力表 / 温控表** | FC01/02/03/04 读，FC05/06/15/16 写 | 16-bit 寄存器数组 / 位数组 | `pymodbus` 3.16.1 | **BSD-3** | ✅ | **P1 首个落地** |
| **Modbus RTU** | 串口仪表、PLC 串口口 | 同 TCP（共用原语，仅换 Transport） | 同上 | `pymodbus` + `pyserial`（已在依赖里） | **BSD-3** | ✅ | **P1**（紧随 TCP，复用同一驱动） |
| Modbus ASCII | 老仪表 | 同上 | 同上 | `pymodbus` | BSD-3 | ✅ | P2（顺带） |
| **S7comm（以太网）** | 西门子 S7-300/400/1200/1500 | 按区域读写：DB/M/I/Q/计数器/定时器 | 字节块 → 按类型解析 | `python-snap7` 3.3.0 | **MIT**（3.0 起纯 Python，无需 snap7.dll） | ✅ | **P1** |
| EtherNet/IP CIP | 罗克韦尔等 | tag 读写（按名字） | 类型化 tag 值 | `pycomm3` 1.2.16 | MIT（**已停止开发**） | ⚠️ 官方只到 3.10 | P2 + fork |
| FINS (UDP/TCP) | 欧姆龙 | 内存区读写 | 字节块 | 自研（帧格式公开） | — | ✅ | P2 |
| MC 协议 3E/4E | 三菱 | 软元件读写 | 字节块 | `pymcprotocol` 0.3.0 | MIT（末版 2021） | ⚠️ | P2 |
| ADS | Beckhoff | 符号/地址读写 + 通知 | 类型化 | `pyads` 3.6.0 | MIT（**客户机须预装 TwinCAT**） | ✅ | P3 |
| OPC UA | 仅当设备只提供它 | browse/read/write/subscribe | 类型化节点 | open62541 DLL | MPL-2.0 | — | P3（按 §0.1-A） |

> 说明：**不做 PLC 编程**意味着不需要点位表与工程变量。地址以**裸地址**表达即可——
> Modbus 用寄存器号 / `4xxxx` 引用，S7 用 `DB1.DBD0`，CIP 用 tag 名。用户在用例里直接写地址，不建映射表。

### 2.2 车载 / 仪器侧

| 协议 | 承载设备 | 协议原语 | 返回形态 | 库 | 许可 | 档位 |
|---|---|---|---|---|---|---|
| **DoIP + UDS** | 车载 ECU（以太网诊断） | 诊断请求/响应（0x10/0x22/0x2E/0x31…） | 字节帧 + 解析后信号 | `doipclient` + `udsoncan` | **MIT** | **P1** |
| CAN / CAN FD | 车载与工业 | 收发帧 + DBC 解析 | 帧 | `python-can`（**已在用**） | — | 已有 |
| SCPI（VISA/TCP/串口） | 通用仪器 | query / write | 文本 | `pyvisa-py`（**已在用**） | — | 已有 |
| SOME/IP | 车载以太网服务 | — | — | `someipy` | **GPL-3** | **不做** |
| LIN | 车身 | — | — | 无成熟 Windows 方案 | — | 不做 |

### 2.3 相机（**按取流协议分类，不按品牌**）

| 取流协议 | 承载设备 | 协议原语 | 返回形态 | 方案 | 约束 | 档位 |
|---|---|---|---|---|---|---|
| **UVC / DirectShow** | USB 工业相机、普通摄像头 | 打开设备、取帧、设曝光/增益/分辨率 | 图像帧 | `opencv-python-headless` | +80~120MB；内含 LGPL FFmpeg | **P1** |
| **RTSP / ONVIF** | 网络相机（含海康/大华/宇视） | 取流、抓图、云台、参数读写 | 视频帧/图像帧 | `opencv` + ffmpeg；ONVIF 走 zeep | 与品牌解耦，**不触碰专有许可** | **P1** |
| GigE Vision / GenTL | Basler、海康工业面阵 | 触发取帧、曝光、IO | 图像帧 | `pypylon` 外置包 | 110.8MB；EULA 8 项条件 | P2 |
| 厂商私有 SDK | 海康/大华 MVS | — | — | ❌ 禁止打包 | 只能客户自装后调用 | 不做内置 |

### 2.4 机械臂（**按控制协议分类**）

| 控制协议 | 承载设备 | 协议原语 | 返回形态 | 方案 | 约束 | 档位 |
|---|---|---|---|---|---|---|
| **Modbus TCP（IO/寄存器协作）** ⭐ | 支持 Modbus 的机械臂、产线 PLC、夹具/变位机 | 寄存器读写 + 线圈读写 | 寄存器/位 | `pymodbus` | **与 PLC 共用同一个 Modbus TCP 驱动，零额外成本** | **P1**（随驱动一起交付） |
| **TCP 私有协议 / 明文指令** | 多数国产品牌（遨博/JAKA/节卡/大族） | 点位下发、到位查询、IO 读写、状态查询 | 文本/JSON | 自研适配层 | 各家报文不同，需逐个适配 | **P2** |
| RTDE | UR | 状态订阅、IO、脚本下发 | 结构化 | `ur-rtde` | **无 cp313 wheel**（最高 3.12） | P3 或降级 3.12 |

> **机器人不做插补/力控/示教**。只做三件事：① 下发点位或触发动作 ② 等待到位信号 ③ 读状态与 IO。
> 这三项刚好是「请求 + 应答 + 超时断言」能覆盖的，不需要为机器人重建执行模型。

### 2.5 明确不做

| 方向 | 原因 |
|---|---|
| EtherCAT / PROFINET / CANopen **主站** | Windows 非实时 OS（延迟 1–50ms）；`pysoem` 需 Npcap + 管理员且仅软实时；PROFINET IRT 需认证硬件 |
| PLC 编程 / 点位表 / 工程变量 | 用户明确：本程序只做通信层交互与控制 |
| SOME/IP、LIN | 分别是 GPL-3 与 Windows 无成熟方案 |

---

## 3. 存疑清单

| # | 存疑点 | 影响 | 处置 |
|---|---|---|---|
| ✅ D1 | Pro 交付形态 | 闭源商业发行 | §0.1-A 红线清单 |
| ✅ D2 | 真机 | 有 Modbus 设备 + PLC | §0.1-C 验证策略 |
| ✅ D5 | OPC UA 的 LGPL | 不可直接打包 | §0.1-A 三选一 |
| ✅ D6 | 分发策略 | 双轨 + 离线导入 | §0.1-B |
| ✅ D7 | 分类主轴 | **以协议为中心，不做 PLC 编程** | 第三版已重构 |
| **D3** | `ur-rtde` 无 cp313 wheel | UR 机器人在 Py3.13 下阻塞 | 优先做国产 TCP 协议与 Modbus TCP；UR 走 P3 或降级 |
| **D4** | `pycomm3` 已停止开发 | EtherNet/IP 需自维护 | 锁 1.2.16 + fork 内部分支 |
| **D8** | 相机取帧后的**判定能力边界** | 只做帧差分/亮度/尺寸这类轻量算子，还是上模板匹配/OCR？ | 建议先做前三类（够用且无额外依赖），模板匹配用 OpenCV 自带，OCR 不做 |

---

## 4. 架构：四层拆开（第三版调整）

```
┌─ Skill（skill.md + manual.md）        → AI 用例生成/调试助手知识，不写代码
├─ Capability（可选 JSON 声明）          → 这台设备在该协议上开放哪些原语与地址范围（非点位表）
├─ Protocol（Python 驱动）              → Modbus RTU/TCP、S7comm、CIP、FINS、MC、DoIP、UVC/RTSP、机器人 TCP
└─ Transport（Python）                  → 串口 / TCP / UDP / USB / 板卡 SDK
```

**第三版对第二版的关键修正**：
- **删除 `DeviceProfile` 里的点位表概念**。对 PLC 只保留「裸地址 + 协议原语」；`DeviceProfile` 仅对 **SCPI 仪器**保留（命令表）
- **Capability 是可选的**：不写也能用（用户直接输入地址/功能码），写了才能让前端下拉选择、让 AI 生成更准的用例
- **同协议多品牌共用驱动**：Modbus 驱动同时服务温控表、电力表、IO 模块、机器人——不需要为每个品牌写插件

**P0 关键改造点**：

| 编号 | 改造 | 落点 | 说明 |
|---|---|---|---|
| P0-1 | `TypedResult{kind,value,meta}`：`text\|bytes\|regs\|bits\|frame\|series\|ack` | `communication/`、`plugin_service.py`、`response_parser.py`、`codegen_service.py` | **必须做**，否则非字符协议全是空中楼阁；`kind=text` 向后兼容 |
| P0-2 | `_STANDARD_PROTOCOLS` + `create_interface` 改注册表 | `models.py:46-53`、`communication/__init__.py:501`、`device_service.py:30` | `Device.protocol` 是 `String(20)`，够用 |
| P0-3 | `PluginManifest`（format/deps/capabilities/platform/py_min/hash） | 新增 `plugins/<name>/manifest.json` + `install_plugin()` | 解决 G2 |
| P0-4 | `.aitestlab-plugin` 包格式 + 离线导入 UI | 新增 `plugin_pack.py` | 解决 G4/D6 |
| P0-5 | 安装期依赖自检 → 失败即 DISABLED 并给出原因 | `_exec_module` 之前 | 现状是装了才发现跑不起来 |
| P0-6 | 断言算子按**协议原语**扩展 | `codegen_service.assertion_stmt()`（现在只处理 `float`/`in`/`==`） | Modbus：寄存器值域/位状态/超时无响应；S7：字节块解析后值域；相机：帧差分/亮度/尺寸；机器人：到位状态位/坐标容差/超时 |
| P0-7 | 插件目录迁至 `%LOCALAPPDATA%\TestCopilot\plugins` | `core/config.py` + `aitestlab.nsi` | 双轨分发与离线导入的前置条件 |

---

### 4.1 首个驱动落地设计：Modbus TCP（PLC / 机械臂 / 仪表共用）

> 定位：**P1 第一号交付物**。它同时是 PLC 通道、机械臂 IO/寄存器通道、工业仪表通道——**一个驱动覆盖三类设备**，是"协议中心"架构的第一个实证。
>
> **✅ 状态：已实现（2026-10-24）**。驱动 + 手册 + Skill + 自检已落地，20 项自检**全部通过**（跑在内置模拟从站上）。
> 交付物见下表 A1–A6；**尚未连接用户实际 PLC 真机**，真机验收按 §4.1-F 的 V1–V8 执行。
>
> **顺带修复（同一批）**：结果解析新增 **`text` 单位**——纯文本数值响应直接取整体值。
> 原因是既有 `ResponseParser.to_bytes()` 会把 `1700` 这类响应按十六进制解析成 `0x17 0x00`（实测 5888），
> Modbus / SCPI 数值响应必须走 `text`。`response_parser.py` 与 `codegen_service.py:139` 两份实现已同步。

#### A. 交付物清单

| # | 文件 | 内容 |
|---|---|---|
| 1 | `backend/plugins/modbus_tcp_plugin.py` | 真实驱动（基于 `pymodbus`，非 demo） |
| 2 | `backend/plugins/modbus_rtu_plugin.py` | 换 Transport 复用（紧随其后） |
| 3 | `backend/plugins/manuals/modbus_tcp.md` | 原语手册：功能码、地址写法、数据类型、错误码 |
| 4 | `backend/plugins/skills/modbus_tcp_skill.md` | AI 用例生成知识（含机械臂场景示例） |
| 5 | `backend/plugins/selftest/modbus_tcp_selftest.py` | 自检：无真机时跑本地 Modbus 从站模拟器 |
| 6 | `backend/requirements.txt` | 新增 `pymodbus==3.16.1`（BSD-3、纯 Python、**可直接进核心包**，无需外置） |

#### B. 连接参数（config schema）

| 字段 | 默认 | 说明 |
|---|---|---|
| `host` | — | PLC / 机械臂 IP |
| `port` | `502` | Modbus TCP 端口 |
| `slave_id` | `1` | 从站号 1–247（TCP 下即 Unit ID，网关后挂串口设备时必填） |
| `timeout` | `3.0` s | 单次请求超时；超时即判定失败，不重试 |
| `byte_order` | `big` | 32-bit 及以上数据的**字节序**（默认大端 = Modbus 标准） |
| `word_order` | `big` | 32-bit 及以上数据的**字序**（部分 PLC 为小端，如西门子/倍福常见 `little`） |
| `retry` | `0` | 失败重试次数；默认 0，保证测试判定可复现 |

> `byte_order` / `word_order` 必须可配：这是 Modbus 跨平台联调时**最常见的踩坑点**（读 float32 出来是乱数，九成是字序反了）。

#### C. 协议原语（8 个，全部覆盖）

| 原语 | FC | 用途 | 返回形态 |
|---|---|---|---|
| `read_coils` | 01 | 读线圈（可读写位，机械臂 IO 输出） | `bits` |
| `read_discrete_inputs` | 02 | 读离散输入（只读位，如到位信号、传感器） | `bits` |
| `read_holding_registers` | 03 | 读保持寄存器（**主力**，参数/状态/坐标） | `regs` |
| `read_input_registers` | 04 | 读输入寄存器（只读，如测量值） | `regs` |
| `write_single_coil` | 05 | 写单线圈（触发动作、置位） | `ack` |
| `write_single_register` | 06 | 写单寄存器（下发参数/目标点位号） | `ack` |
| `write_multiple_coils` | 15 | 写多线圈 | `ack` |
| `write_multiple_registers` | 16 | 写多寄存器（下发坐标数组 / 点位序列） | `ack` |

**用例步骤里的写法（两种都支持）**：

```
# 紧凑写法
FC03:40001:2              → 读保持寄存器，起始 40001，长度 2
FC03:0:2                  → 同上（0-based 协议地址，40001 ≡ 0）
FC06:40010:1              → 写单个寄存器
FC01:00001:8              → 读 8 个线圈

# 结构化写法（JSON，支持数据类型解码）
{"fc": 3, "addr": 100, "count": 2, "dtype": "float32"}   → 返回 1 个 float32
{"fc": 3, "addr": 100, "count": 4, "dtype": "string", "len": 8}
```

**地址约定**：内部一律用 **0-based 协议地址**；用例里写 `4xxxx` / `0xxxx` / `1xxxx` / `3xxxx` 形式时自动换算（`40001 → 0`、`00001 → 0`、`10001 → 0`、`30001 → 0`）。这样无论用户手册写哪种，都能直接用。

**`dtype` 解码表**：`uint16` / `int16` / `uint32` / `int32` / `uint64` / `int64` / `float32` / `float64` / `bool` / `string(ascii)` / `raw`。

#### D. 返回值的两阶段策略（与 P0-1 衔接）

| 阶段 | `send()` 返回 | 说明 |
|---|---|---|
| **阶段一（P0-1 之前）** | `str`：寄存器数组的稳定文本表示，如 `"[17000, 0]"`；`write` 返回 `"OK"` | 兼容现有 `ResponseParser` 与 `assert float(response) op x`，**先让真机能跑通** |
| **阶段二（P0-1 落地后）** | `TypedResult{kind:"regs", value:[...], meta:{fc, addr, dtype, slave_id, elapsed_ms}}` | 结构化进入判定、趋势图、回放；`kind=text` 路径保持向后兼容 |

> 阶段一不是"将就"：Modbus 的判定 90% 是数值比较，字符串通道够用。但**必须提前在驱动里把 `meta` 字段准备好**，否则 P0-1 落地时要回头改所有驱动。

#### E. 断言算子（P0-6 的 Modbus 部分）

| 算子 | 语义 | 典型场景 |
|---|---|---|
| 值域 | `40001 ∈ [min, max]` | 温度、电流、压力阈值 |
| 位状态 | `00001 == true` | 机械臂到位信号、夹具夹紧 |
| 等于/不等于 | `40005 == 3` | 状态码、模式字 |
| 变化率 | `Δ40002/Δt ≤ x` | 升温速率、转速爬升 |
| 稳定性（N 次采样方差/极差） | `range(40003, 10 samples) ≤ x` | 稳态判定 |
| **超时无响应** | `request(FC03:40099) → timeout` | 负向用例：地址不存在 / 从站离线 |
| 序列轮询 | `sample(40001, 100ms, 50) → series` | 曲线趋势与超调判定 |

#### F. 真机验收清单（跑完才算交付）

| # | 用例 | 通过标准 |
|---|---|---|
| V1 | 连接 PLC（IP + 502） | 连接成功，状态页显示在线 |
| V2 | `FC03` 读一个已知寄存器 | 返回值与 PLC 监控表一致 |
| V3 | `FC06` 写一个保持寄存器后读回 | 写后读回一致（回环验证） |
| V4 | `float32` 跨 2 寄存器读 | 切换 `word_order` 后能拿到正确浮点值（**验证字序开关真的有用**） |
| V5 | `FC01` 读线圈 + `FC05` 写线圈 | 位状态读写一致 |
| V6 | 超时用例：读不存在的地址 | 按 `timeout` 返回失败，服务不卡死、不崩溃 |
| V7 | 机械臂（若已接入）：写点位寄存器 → 轮询到位位 → 断言 | 完整「触发 → 等待 → 断言」闭环 |
| V8 | 生成代码 → 脱离 UI 回放 | 生成的脚本独立运行，结果与 UI 执行一致 |

> V1–V6 用你手上的 PLC 即可完成，不需要机械臂到场；V7 等机械臂联调时补。

---

## 5. 实施路线

| 阶段 | 内容 | 产出 | 前置 |
|---|---|---|---|
| **P0 架构**（2–3 周） | P0-1 ~ P0-7，**不新增任何协议** | 类型化返回值 + 协议注册表 + manifest + 插件包 + 断言算子 | 无，可立即开工 |
| **P1 第一批协议**（3–4 周）<br>**排序已定** | ① **Modbus TCP**（PLC + 机械臂 + 仪表，一驱动三类）<br>② Modbus RTU（换 Transport 复用）<br>③ S7comm<br>④ DoIP+UDS<br>⑤ 相机 UVC / RTSP | 5 个协议驱动 + 3 类非字符数据闭环（寄存器/字节块/图像帧） | 需真机（已有 Modbus TCP PLC） |
| **P2** | Modbus ASCII、EtherNet/IP(fork)、FINS 自研、MC、机器人 TCP 私有协议适配、GigE/GenTL 外置包 | 主流 PLC 协议覆盖 + 机械臂私有协议 | P1 真机经验 |
| **P3** | ADS、OPC UA（按 §0.1-A）、RTDE、插件/Skill 商店、License 校验、代码签名 | 可商业交付 | — |

**P1 排序理由（2026-10-23 按用户真机情况重排）**：
- **Modbus TCP 排第一**：你手上的 PLC 与机械臂都走它 → **同一个驱动同时打通三类设备**，是真机覆盖率最高、投入产出比最好的一条；且它不依赖任何新硬件采购。
- **Modbus RTU 紧随**：与 TCP 共用全部协议原语，只换 Transport（串口），边际成本极低。
- **S7 降为第③位**：不再是你手上设备的首选通道，但仍是工业侧最大盘之一，`python-snap7` 纯 Python + MIT，成本低，保留 P1。
- **DoIP + 相机**保持原位：DoIP 是既有 CAN/DBC/UDS 能力轴的延长线（**加长板**）；相机用来验证「非字符数据」通道真能跑通。

---

## 6. 决策记录与待确认

### 6.1 已确认

| # | 决策 | 日期 |
|---|---|---|
| Q1 | Pro 为**闭源商业发行** | 2026-10-21 |
| Q2 | 目标客户：**汽车电子实验室 + 工业产线并行** | 2026-10-21 |
| Q3 | **双轨分发 + 必须支持离线导入** | 2026-10-21 |
| Q4 | 有 **Modbus 设备 + PLC** 可联调 | 2026-10-21 |
| Q9 | **以通信协议为分类主轴；不对 PLC 编程，不做点位表；相机/机械臂同理按取流与控制协议分类** | 2026-10-23 |
| **Q7'** ✅ | **PLC 与机械臂统一走 Modbus TCP 优先**；用户 PLC 支持 Modbus TCP | 2026-10-23 |

### 6.2 仍需你补充

| # | 需要的信息 | 为什么现在就要 |
|---|---|---|
| ~~Q7'~~ | ~~PLC 对外开哪个协议口~~ | ✅ 已答：**Modbus TCP**（PLC 与机械臂统一） |
| **Q8'** | 相机与机械臂**现在有没有实物**，还是先做协议层？ | 决定 P1 相机部分是否要标注「未经真机验证」；机械臂 Modbus TCP 部分**不等实物**（与 PLC 共用驱动） |
| **Q5** | 机械臂品牌（避开 UR，优先遨博/JAKA/节卡） | 影响 P2 排期与是否讨论 Python 降级 |
| **Q6** | 版本命名：延续 `v0.11.0` 还是开 `Pro 1.0` 序列 | 建议 Pro 独立序列，社区版继续 v0.x |

### 6.3 P0 可立即开工的七件事（不依赖 Q5-Q8）

1. `TypedResult{kind,value,meta}` 落地，`kind=text` 向后兼容 —— 后续一切的前提
2. `_STANDARD_PROTOCOLS` 与 `create_interface` 改为协议注册表
3. `PluginManifest` schema（deps/capabilities/py_min/hash）+ 安装期依赖自检
4. `.aitestlab-plugin` 包格式 + **离线导入 UI**（含 `_vendor` 机制）
5. 插件目录迁至 `%LOCALAPPDATA%\TestCopilot\plugins`，NSIS 同步调整
6. `assertion_stmt()` 扩展到 regs / bytes / frame 三类算子
7. ✅ **已完成**：真实 Modbus TCP 驱动（见 §4.1），含 manual / skill / selftest；20 项自检全部通过。
   （`example_plugin.py` 的假 demo 保留作模板，但已加显式警示并标注协议名待改名。）

> **建议的两条并行线**：线 A（P0-1~P0-6 架构改造）与线 B（§4.1 Modbus TCP 驱动）**可以并行**——
> 线 B 按 §4.1-D 阶段一先返回字符串，不依赖线 A；线 A 落地后线 B 切到 `TypedResult` 即可。
> 这样真机验证不会被架构改造阻塞。

---

## 7. 参考来源（2026-10-21 查证）

- pymodbus 3.16.1（BSD-3-Clause，纯 Python，支持 Py3.13）：https://pypi.org/project/pymodbus/
- python-snap7 3.3.0（自 3.0 起纯 Python，无原生依赖）：https://github.com/gijzelaerr/python-snap7
- asyncua 2.1.0（LGPL-3.0）：https://pypi.org/project/asyncua/
- pycomm3 1.2.16（MIT，已停止积极开发）：https://pypi.org/project/pycomm3/
- pyads 3.6.0（MIT，需 TwinCAT）：https://pyads.readthedocs.io/
- opencv-python 5.0.0（Apache-2.0，wheel 内置 LGPL FFmpeg）：https://pypi.org/project/opencv-python/#files
- pypylon（wheel 110.8MB，EULA 8 项条件）：https://docs.baslerweb.com/pylon-end-user-license-agreement
- 海康软件许可协议 3.1（禁止分销/禁止与其他产品合并）：https://www.hikvision.com/en/policies/software-license-agreement/
- doipclient（MIT，ISO-13400-2）：https://github.com/jacobschaer/python-doipclient
- ur-rtde（官方 wheel 最高 cp312）：https://pypi.org/project/ur-rtde/
- pysoem（MIT，需 Npcap + 管理员，仅软实时）：https://pypi.org/project/pysoem
