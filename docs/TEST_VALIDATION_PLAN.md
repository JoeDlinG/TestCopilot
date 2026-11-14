# AITestLab 发布验证计划（Issue #28）

> 适用版本：v2.3.7（`feature/flow-enhancements`）
> 目的：把「发布前该验证什么、用什么验证、什么条件算通过」固化成可重复执行的清单，避免只靠构建成功就发版。
> 本文只定义计划与判定口径；逐次执行结果记入「执行记录」章节或 CI 产物。

---

## 1. 环境前置

| 项 | Linux 验证机 | Windows 验证机（主分发形态） |
|---|---|---|
| Python | ≥ 3.11（CI 允许 3.8+ 跑纯逻辑门禁） | 3.11 / 3.13（venv `aitestlab`） |
| Node | ≥ 18 | 22（managed Node） |
| 后端 | `cd backend && python run.py` | 打包版 NSIS 安装后由 `AITestLab.exe` 启动 |
| 前端 | `npm run dev` / `npm run build` 产物覆盖 `backend/static/` | 同左（static 随包分发） |
| 端口 | 8000（占用时由 `run.py` 顺延并写入 `AITESTLAB_PORT`） | 同左 |
| 浏览器 | Playwright / Chromium `--no-proxy-server` | 同左 |

### 真实设备与接线

| 设备 | 协议 | 关键参数 |
|---|---|---|
| Mini Gateway 100 | `mini_gateway100` | USB-C CDC 虚拟串口（Linux `/dev/ttyACM0`、Windows `COM3`），115200；或以太网 `192.168.0.120:6025`；板卡 ID 默认 `11` |
| PCAN-USB | `peakcan` | `pcan` 接口 `PCAN_USBBUS1`，500K；Linux 也可走 SocketCAN `can0` |

```
[PCAN-USB] ---- CAN_H / CAN_L ---- [MG100 CAN1]        （需 120Ω 终端电阻）
     |                                   |
   USB                                USB-C / 以太网
     |                                   |
     +------------- 验证机 --------------+
```

- Linux 首次接 PCAN 需 `sudo bash backend/install/install_peakcan_rules.sh`；Windows 使用 PCAN-Basic，不需要也不要执行 udev/`.sh` 脚本。
- MG100 在 Windows 上没有 libusb 后端，原生 USB bulk 路径不可用；存量 `transport=usb` 由 `connect()` 自动降级到 COMx 串口。

### 数据安全前置

导出工程、通信日志、反馈内容均不得包含明文 API Key。导出前用 `Test/test_feedback.py` / 工程导出接口抽查 `api_key` 字段。

---

## 2. 测试矩阵（17 模块，P0/P1/P2）

| # | 模块 | 编号 | 优先级 | 关键验证点 | 自动化映射 |
|---|---|---|---|---|---|
| 1 | 设备连接与仪器控制 | TC-DEV | P0 | 新建/编辑接口/连接/断开/删除；插件协议不被覆盖；重连先关旧连接 | `test_issue33_peakcan_protocol.py`、`test_issue34_generic_can.py`、`test_device_delete.py`、`test_mgw100_connect.py` |
| 2 | 调试终端 | TC-TERM | P1 | python-can 语法翻译、多窗口、三栏历史 | 手工 + `test_can_comlog.py` |
| 3 | AI 用例生成 | TC-GEN | P1 | 文字/语音 → 结构化用例；解析项唯一校验 | `test_plan_case_validation.py` |
| 4 | 流程图编辑器 | TC-FLOW | P0 | 拖拽、撤销/重做、类型切换、条件/循环、标签可清空 | `test_flow_command_source.py` |
| 5 | 代码生成 | TC-CODE | P0 | **改流程图后重新生成**，旧指令不得残留；裸 SCPI 指令不丢失 | `test_codegen.py`、`test_flow_command_source.py`、`test_issue34_generic_can.py` |
| 6 | 用例管理 | TC-MGR | P1 | CRUD、重绑定、解析项名称唯一 | `test_plan_case_validation.py` |
| 7 | 执行引擎 | TC-EXEC | P0 | 顺序/并行/条件/循环/变量/WS 监控；命令语义错误不误判断链 | `test_ws_monitor.py`、`test_blocking.py`、`test_issue33_peakcan_protocol.py` |
| 8 | 结果解析与判定 | TC-PARSE | P0 | hex/bin/bool/dec/str、min/max/等于、空帧 unknown、趋势曲线每应答一个采样点 | `test_result_parsing.py`、`test_parser_unique_and_trend.py`、`test_dash_since.py` |
| 9 | 执行管理器 | TC-PLAN | P1 | 批次编排、失效用例运行前拦截、冲突检测 | `test_plan_case_validation.py` |
| 10 | 通信日志 | TC-LOG | P1 | SQLite+CSV 双写、keyset 分页、CSV 导出 | `test_can_comlog.py` |
| 11 | 测试报告 | TC-RPT | P2 | PDF/HTML/MD 输出、AI 结论 | 手工 |
| 12 | 自定义仪表盘与大屏 | TC-DASH | P1 | 7 种 Widget、snapshot 一次拉齐、大屏刷新 | `test_dash_since.py` |
| 13 | 插件系统 / Skill | TC-PLUG | P1 | 安装/启用/禁用、模板建设备、Skill 语法 | `test_mg100_skill_syntax.py`（需 MG100） |
| 14 | AI 助手 | TC-AI | P2 | 对话、记忆文件、模型配置 | `test_feedback.py` |
| 15 | 项目工程文件 | TC-PROJ | P0 | 导出 7 段、导入幂等、密钥不落盘、`counts` 缺失时现算、缓存淘汰 | `test_regression_guards.py` |
| 16 | 国际化 / 帮助 / 更新 / 反馈 | TC-SYS | P1 | 中文页面无英文残留、远程更新版本比较、损坏包拒绝安装 | `test_i18n_zh_pages.py`、`test_update_service.py`、`test_version_consistency.py` |
| 17 | 非功能 | TC-NFR | P0 | 首启时序、静态 MIME、bundle 无 2-环、阻塞 IO 线程化、`HEAD /` 200、启动自愈 | `test_boot_guards.py`、`test_static_runtime.py`、`test_startup_resilience.py` |

---

## 3. 关键端到端场景

- **E2E-01（P1）MG100 基础链路**：`HELLO` / `SYSID` / `GETDIG` / `SETDIG` / `GETVOLT` / 继电器 `OPEN` `CLOSE`，逐条断言应答格式与继电器状态。
- **E2E-02（P0）PCAN ↔ MG100 跨设备 CAN 联动**：PCAN `send_periodic(0x20, 01 02 03)` → MG100 `CONFIG CAN1 RX 0X20` + 循环 `MSGRX` 读到 `0X010203`；反向 `MSGTX` 由 PCAN 接收。该场景同时验证「编辑设备接口后 protocol 保持 `peakcan`」与「执行期间不误判断链」。
- **E2E-03（P0）全闭环**：AI 生成 → 修改流程图指令 → 重新生成代码 → 执行 → 解析判定 → 报告。断言生成代码中**不出现**被替换掉的旧 ID。
- **E2E-04（P1）执行管理器多设备并行批次**：同 `group_no` 的用例并行（受 `max_parallel` 限制），组间串行，循环内串行。

---

## 4. 发布通过标准（Release Gate）

1. P0 用例全部 PASS，无未解决 P0 缺陷；P1 通过率 ≥ 98%。
2. `bash Test/run_all.sh` 无 FAIL；`python -m compileall backend`、`cd frontend && npx tsc --noEmit`、`npm run build`（内含 `i18n-guard`）全部通过。
3. 白屏防护：真实浏览器渲染 6 条路由 `#root.innerHTML` 非空、`pageerror = 0`、失败请求 0、所有 JS 响应 `application/javascript`、boot guard 面板不误触发；生产 bundle 静态依赖图 0 个 2-环；`GET /` 带 `no-store`；`HEAD /` 返回 200；缺失 asset 与未知 `/api/*` 返回 JSON 404。
4. 版本口径：`APP_VERSION` / NSIS / HISTORY 首章 / KANBAN 抬头 / 运行时 `/api/health` 五者一致；`/api/health` 的 `degraded=false` 且 `boot_warnings=[]`。
5. 真实硬件 E2E-01/02/03 全部通过；未接硬件时相关套件必须明确 SKIP，不得伪装 PASS。
6. 数据安全：导出的工程文件、日志、反馈内容不含明文 API Key。
7. 异常关闭后重启：应用仍可启动，`/api/health` 有 `boot_warnings` 时仍返回 `status=ok`，工程可正常导入。

> Windows 条件项：安装版真机 E2E、PCAN-Basic 驱动下的 `peakcan` 连接。Linux 验证机无法覆盖，必须单独在 Windows 执行并记录；未执行时不得声称「全部通过」。

---

## 5. 自动化与平台策略

```bash
# 硬件无关全量门禁（需后端运行在 :8000；端口顺延时用 AITESTLAB_PORT）
bash Test/run_all.sh

# 单个门禁
python3 Test/test_static_runtime.py          # 无需后端，TestClient 直接跑
python3 Test/test_issue34_generic_can.py     # 无需硬件
```

`run_all.sh` 的诚实性约定：

- **数据 SKIP**：工作区固定用例被清空导致的 fixture 缺失，输出 `[SKIP]` 并由 runner 计入 `data-skipped`，不算 PASS 也不算 FAIL。
- **硬件 SKIP**：MG100/PCAN 未连接时跳过硬件套件，不误报产品回归。
- **平台 SKIP / 条件断言**：以下用例不得因操作系统不同恒定失败：
  | 套件 | 处理 |
  |---|---|
  | `test_peakcan_prepare` | 按平台断言错误提示（Linux 指向 `install_peakcan_rules.sh`，Windows 指向 PCAN-Basic） |
  | `test_i18n_zh_pages` | 用 `node` 调 esbuild 的 JS API，不直接执行平台相关的 `.bin/esbuild` 二进制 |
  | `test_mgw100_connect` | USB 原生传输用例固定 POSIX 语义（Windows 上该路径不存在） |
  | `test_result_parsing` / `test_parser_unique_and_trend` | DB 路径由 `__file__` 计算绝对路径，不依赖 CWD |
  | `test_update_service` | 按平台选择 `zip`(POSIX) / `nsis`(Windows) Release asset |

新增 `test_*.py` 必须同步登记到 `Test/run_all.sh`，否则门禁不会真正执行。

---

## 6. 缺陷模板

```markdown
## [TC-XXX / E2E-XX] 标题
- 严重度：P0 / P1 / P2
- 环境：OS / Python / Node / 版本 / 设备与固件
- 前置条件：
- 复现步骤：1. … 2. … 3. …
- 期望结果：
- 实际结果：
- 证据：日志路径、`/api/system/diag` 输出、截图、SQL 自查结果
- 关联模块 / Issue：
```

设备层问题请附一行自查结果：

```sql
SELECT id, name, protocol, connection_type, config, status FROM devices
WHERE protocol IN ('peakcan','can','mini_gateway100');
```

---

## 7. 执行记录

| 日期 | 环境 | 执行人 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-11-14 | Linux（本工作区） | 自动门禁 | `Test/run_all.sh` 全绿 | 见提交说明；Windows 安装版 E2E 与 PCAN-Basic 仍为条件项 |
|  | Windows 11 / Python 3.13 | 待执行 |  | 需覆盖 NSIS 安装版真机渲染与 PCAN-Basic |

---

## 8. 关联文档

- `HISTORY.md`：各版本修复记录
- `README.md`「回归测试」：门禁清单与运行方式
- `docs/PEAKCAN_PLUGIN.md`：PCAN 驱动与配置
- `docs/API_SPEC.md`：API 契约
