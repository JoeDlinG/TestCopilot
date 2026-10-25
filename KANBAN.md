# 项目看板 — AITestLab

> 项目进展与计划同步看板。本文件用于快速同步各模块状态，详细变更见 `HISTORY.md`，使用说明见 `README.md`。
> 最后更新：2026-10-17

---

## 📌 看板总览

| 状态 | 含义 |
|------|------|
| 🔲 待办 (To Do) | 已规划，尚未开始 |
| 🔧 进行中 (In Progress) | 正在开发/调试 |
| ✅ 已完成 (Done) | 已实现并通过验证 |

---

## 🔲 待办 (To Do)

- [x] **自定义仪表盘**（用户自行定义需要查看的界面）— 设计草案见 `docs/CUSTOM_DASHBOARD_IDEAS.md`
      - [x] P1：栅格布局（`react-grid-layout`，拖拽移动/缩放）+ Widget 注册表 + 基础 Widget（设备状态/执行统计/通信日志/文本备注）+ 持久化 + 编辑锁定
      - [x] P2：**解析数值卡片** + 判定结果标记（FAIL 是判定结果，非告警）+ **趋势曲线** + **判定结果汇总**
      - [x] P3：内置模板（长稳视图/调试视图）、导入导出 JSON、多仪表盘、大屏模式
      - 🔲 尚未做：大屏自动轮播、响应式断点（当前固定 12 列）
      - 已定：不做权限体系；趋势数据复用 `parsed_results` 不单独建表；需大屏模式
      - 已交付：仪表盘**大屏模式**（超大字号 + 深色投屏 + 实时时钟 + 自动刷新 + 无权限）

- [x] **性能优化**（启动速度、大数据量日志渲染）— v0.12.0：移除 `CommunicationLog` 与 `idx_logs_*`
      重复的 3 个索引（9→6，日志写入放大减半）；新增 SQLite PRAGMA 调优（WAL / NORMAL / 16MB 缓存 /
      temp MEMORY，FK 保持 OFF）；`lifespan` 分段计时可归因；日志表格开启虚拟滚动 + 页大小 20~200
- [x] **修复「用例无法执行 + 通信窗口无消息」** — v0.12.1：根因是**流程里硬编码的 `device_id` 失效**
      （设备删除后重新添加会拿到新 id）。执行引擎改为先校验绑定有效性：悬空 id 回退到协议推断、
      存在但未连接则明确报错而非静默改投别的设备；新增 `/api/testcases/stale-devices` 与
      `/rebind-devices` 清理存量（本次修复 93 个节点）；协议推断补上 `can.Bus` 并改 `search`；
      前端在检测到失效绑定时弹告警 + 「重新绑定设备」按钮
- [x] **国际化**（中英文界面切换）— v0.12.0：新增 `src/i18n/`（`LanguageProvider` / `useI18n` / `t()`），
      顶栏语言切换 + localStorage 记忆 + antd locale 与 dayjs 同步；未翻译键回退中文（可增量翻译）。
      已译 103 键 100% 覆盖（导航 15 项、通用动作、设备管理、项目工程、接口参数）；
      尚未接入的页面保持中文
- [ ] 打包与安装程序制作
- [ ] 更多仪器驱动适配（示波器/万用表/信号发生器等真实型号）
- [ ] 插件进程隔离沙箱（当前为同步加载，无独立进程）
- [ ] 语音输入对接（当前仅占位，未接浏览器录音上传）
- [ ] **GitHub Issue 增强项**（详见下方 Issues 表，均在 `feature/flow-enhancements` 分支推进）
      - [x] #1 流程图编辑器：节点复制/粘贴 + 节点类型切换（判断⇄循环⇄操作）
      - [x] #5 新增「初始化 / 重置」节点：自定义变量并赋值
      - [x] #4 所有节点支持输入参数与输出返回值（节点间数据串联）

- [x] **Skill 编辑器**：导入 / 修改 / 保存插件 Skill（Markdown）
      - 左侧列表选 Skill，右侧编辑名称 / 协议标识 / 关键词 / 正文；改协议标识自动重命名文件
      - 支持上传或粘贴 `.md` 导入，protocol 从 frontmatter 或文件名推断
      - 后端新增 `POST/PUT/DELETE /api/plugins/skills[/...]`、`POST /api/plugins/skills/import`

- [x] **插件编辑器 + 插件模板**：新建插件自动套用模板与示例
      - 4 套模板（通信协议 / 设备驱动 / 数据解析 / 报告模板），占位符自动填充
      - 在线编辑 `plugins/*.py`，语法校验 + 插件类识别
      - 后端新增 `/api/plugin-editor/*`（templates / files / validate），前端页 `/plugin-editor`

---

## 🐛 GitHub Issues（2026-10-05 从 GitHub 同步）

| Issue | 类型 | 标题 | 状态 |
|-------|------|------|------|
| #6 | bug | PeakCAN USB 连接失败：Windows 下 auto 错误回退 socketcan（WinError 10047） | ✅ 已修复 → v0.4.0；v0.7.1 加固（多候选重试 + 错误可读化 + `diagnose`） |
| #2 | bug | 循环节点缺少「执行命令 / 预期结果」配置（与操作节点不一致） | ✅ 已修复 → v0.4.0 |
| #3 | bug | while 循环缺少进入/跳出条件；条件表达式缺示例与可用变量说明 | ✅ 已修复 → v0.4.0 |
| #1 | enhancement | 流程图编辑器交互增强：节点复制/粘贴 + 节点类型切换 | ✅ 已实现 → v0.5.0（分支 `feature/flow-enhancements`） |
| #5 | enhancement | 新增「初始化 / 重置」节点：自定义变量并赋值 | ✅ 已实现 → v0.6.0（分支 `feature/flow-enhancements`） |
| #4 | enhancement | 所有节点支持输入参数与输出返回值，后续节点可引用前序输出 | ✅ 已实现 → v0.7.0（分支 `feature/flow-enhancements`） |

- **v0.4.0**（bug 修复版，master）：#6 / #2 / #3，备份 tag `backup-2026-10-05`
- **v0.5.0**（增强版，分支 `feature/flow-enhancements`）：#1 节点复制/粘贴（Ctrl+C/V、Ctrl+D）+ 节点类型就地切换
- **v0.6.0**（增强版，同分支）：#5 新增「初始化 / 重置」节点 — 变量定义（名称/类型/初始值/说明，支持增删改序），代码生成输出变量声明
  - 注：变量引用目前在**生成代码**路径生效；运行时执行引擎的变量解析随 #4 统一落地
- **v0.7.0**（增强版，同分支）：#4 输入参数 / 输出返回值 + Skill 编辑器 + 插件编辑器（模板）
  - #4 落地后，变量引用在**生成代码**与**运行时执行引擎**两条路径上行为一致
- **v0.7.2**（增强版，同分支）：延时节点（ms）+ 节点复制按钮 + 用例生成多设备并行拆流程 +
  执行界面双监控窗口 / 按设备多列步骤
- **v0.7.3**（增强版，同分支）：执行界面用例名标题 + 启动/停止按钮；流程图全屏编辑 + 选中节点/连线高亮；
  测试用例重命名 + 一键清空
- **v0.7.4**（修复版，同分支）：修复「启动后不实际运行」—— 后台执行任务改用独立 DB 会话，
  消除与请求会话的并发冲突；顺带清理残留 running 执行
- **v0.8.0**（增强版，同分支）：PeakCAN「只收不发」修复 + 生成设备回填 + PeakCAN 周期发送(period_ms 参数化) +
  运行时按 edges 执行（condition 分支 / loop 迭代）
- **v0.8.1**（修复版，同分支）：调试终端识别 python-can 语法（`bus.send_periodic(...)` 等）——
  插件翻译层 + 执行引擎命令提取/协议识别，消除 `Invalid CAN string format`
- **v0.8.2**（修复版，同分支）：MG100 RX 过滤/监控逻辑 + 收发时序对齐写入生成 skill（`send_periodic` 窗口 + 循环 `MSGRX` 重叠）
- **v0.8.3**（修复版，同分支）：peakcan skill 补「禁止生成 open/close」；真实硬件端到端跑通（MG100 读到 `0X010203`）
- **v0.8.4**（修复版，同分支）：PeakCAN `receive()` 过滤自回环帧（消息不再显示在发送方自己的终端，Issue #14）
- **v0.8.5**（修复版，同分支）：修复「AI 生成测试用例必失败」（前端 `devicePayload` 分页解析 bug，Issue #13）+ 错误提示解析（#15）+
  NaN/Infinity 序列化防御（#13）+ 新增执行日志（per-execution 文件夹 + 全局程序/通信日志，10MB 轮转）
- **v0.8.6**（优化/修复版，同分支）：启动按钮补 loading 反馈（实测后端仅 43~179ms，观感问题）+
  代码生成回退下发原文时输出 ⚠️ 提示 + 修复 `test_codegen` 三处过期断言（既有失败）
- **v0.9.0**（新功能，同分支）：**测试用例执行管理器** — 多用例编排（顺序/并行分组/循环/延时）+ 设备与端口静态冲突检测告警；
  顺带修复 Issue #7 时区（时间统一为带 UTC 偏移，前端显示不再差 8 小时）
- **v0.10.0**（新功能 + 修复版，同分支）：**AI 助手增强**（生成用例预览 / 一键添加 / 对话式修改用例 /
  项目记忆文件 `Project_xxx Memory.md`）+ **项目工程文件**（7 类配置打包成一个 JSON，支持另存为/导入/导出/重命名）；
  修复「流程图编辑后重新生成代码失败」（保存失败被裸 catch 吞掉，仍用旧版本生成）；
  版本号统一：`APP_VERSION` 与安装包版本同步到看板口径
- **v0.11.0**（新功能 + 修复版，同分支）：**MG100 插件支持以太网**（TCP，默认 `192.168.0.120:6025`，串口/以太网双传输）+
  **设备接口可手动配置**（新增 PCIe / PXI 及各自参数，接口注册表驱动前端动态表单）+
  修复以太网「连接失败却假装已连接」；并清理 GitHub Open Issue（实际修复 #8/#9/#10/#11/#12，
  核对 #1–#7/#13–#16 为历史已修）
- **v0.12.0**（新功能 + 待办清理，同分支）：**新建项目工程**（清空配置但保留 AI 模型设置）+
  **AI 助手改版**（输出在上、输入在下；支持文本与图片附件，视觉模型实测可用，不支持时自动降级）+
  **性能优化**（重复索引清理、SQLite PRAGMA 调优、日志虚拟滚动、启动分段计时）+
  **国际化**（中英文切换，103 键 100% 覆盖）
  - **v0.13.0**（新功能 + 性能优化，同分支）：**设备ID号**（用户可指定的稳定唯一标识 `DEV-00x`，
  用例按它关联设备，换硬件时复用同一个号即可）+ **切换设备接口**（按ID号重绑定并原子地重新生成代码）+
  **加载性能优化**（dev 依赖预打包 deps 0→32；执行页 WS 消息批量合并渲染）
  - **v0.14.0**（GUI 重构，同分支）：**Issue #20 三区布局 P0–P2** —— 主题 Token（3 主色 + 1 状态色）、
    左侧 3 组 8 项 + 顶栏下拉 + 状态条、右侧「输出/交付」抽屉（三态 / 双 Tab / pin / 启动自动展开 / 运行徽标）、
    组件规范 `DataTable`/`StatusTag`/`PageContainer`/`EmptyState`/`MonoText`（闭环 #17 / #19）；
    `.big-dash` 的 !important 清零、烧杯图标全站清除
- **v0.15.0**（GUI 收尾，同分支）：**Issue #21（P3 页面级优化）已实现并关闭** —— 抽屉宽度 420→720px
  且单击展开/双击全屏、插件三路由合并为单一 `/plugins`（Tab）、⌘K 命令面板、调试终端补第三栏
  「指令/历史」、流程图沉浸模式、项目向导、剩余表格页 `DataTable` 收尾、焦点环与减弱动效
  - 增强功能（#1 → #5 → #4 → Skill/插件编辑器 → 延时/并行执行）在新分支 `feature/flow-enhancements` 上逐个版本推进

## 🔧 进行中 (In Progress)

- Issue #1 流程图编辑器交互增强（节点复制/粘贴 + 节点类型切换）— 分支 `feature/flow-enhancements`

---

## ✅ 已完成 (Done) — 最近更新

### v2.3.2 — Issue #27（i18n 盲区收口）+ AI 助手未配置提示（2026-10-25，分支 `feature/flow-enhancements`）

- [x] **#27 P0-1 常量里的显示文案**：`PROJECT_SECTIONS` 改 `labelKey` + 8 处渲染点过 `t()`；
      抽出 `sectionLabel(key)` helper；新增 `section.*` 词条；**中文标点也按语言切换**
      （`punct.colon`/`punct.enum`/`punct.countParen`）
- [x] **同类同构一并治理**：`types/index.ts` 的 `DEVICE_TYPES`/`INTERFACE_TYPES` 改 key 驱动
      （新增 `deviceType.*`/`iface.*`）；`dashboard/registry.tsx` 的 `WIDGET_META`/`STATUS_LABEL`
      改 **`t` 工厂**（`makeWidgetMeta`/`makeWidgetList`/`makeStatusLabel`，`newWidget(type, t)`）
- [x] **#27 P0-2 `t()` 纯文本泄漏 59 处**：用 `@babel/parser` 写一次性修复脚本按 AST 跨度精确
      包裹（自动 58 处 + 手工 3 处：DelayNode 补 hook、属性串误写、Python 代码模板内误替换）
- [x] **#27 P1 守门脚本** `frontend/scripts/i18n-guard.mjs`：B 类（裸 `t('`）**零容忍**、
      A 类（硬编码 CJK）**棘轮只降不升**；接入 `"build": "tsc && node scripts/i18n-guard.mjs && vite build"`
- [x] **AI 助手未配置提示**：顶部醒目 Alert（加载完成且为空才显示，避免闪烁）+ **「去配置模型」**
      直达 `/model-config` + 「重新检测」
- [x] 验证：英文配置段 = `Model Config / Devices / Plugins / Skills / Test Cases /
      Execution Manager / Dashboards`；中文仍中文；页面裸 `t()` 0 处；守门 B=0、A=221（原 268）；
      `tsc`+`build`（含闸门）通过；`Test/` 7 个全 PASS；端点 19/19；仪表盘未回归

### v2.3.0 — Logo / 帮助中心 / 首次引导 + Issue #25 #26（2026-10-22，分支 `feature/flow-enhancements`）

- [x] **替换 Logo**：白底用边缘洪水填充去除（保住剪贴板内部白）；图标靠**连通域**分离
      （勾的笔画与字母 T 在 x 上交错，矩形裁切做不到）；产出 full/mark/32/64/180 + 触屏图标；
      接入侧栏（展开字标·折叠图标）、标签图标、标题、关于页；品牌文案统一为 TestCopilot
- [x] **帮助菜单**：重新观看导航 / 使用文档 / 快捷键 / 检查更新 / 问题反馈 / 关于
- [x] **帮助文档走后端** `GET /api/help/docs`，`docs/` 为唯一数据源；只暴露白名单 3 篇；
      markdown 表格用零依赖方案（文本段 + AntD Table），29 张表渲染正常
- [x] **首次运行引导**：AntD Tour 8 步，只跑一次（跳过也记标记），帮助菜单可重放
- [x] **#25 远程更新**：清单/GitHub 双来源；语义化比对；启动非阻塞提示 + 对话框；
      后台下载 + **强制 SHA256 校验**；`update_helper.py` 备份→替换→重启→健康检查→回滚；
      客户端不传 URL/路径，安装只认服务端签发的 token；**需两次确认**
- [x] **#26 问题提交**：`feedback_reports` 表；通用异常处理器（顺带关 #13）+ excepthook；
      崩溃按签名去重；前端 ErrorBoundary + onerror + unhandledrejection；异常退出标记；
      反馈表单；自动脱敏；无 Token 时本地留存 + 下次启动补发
- [x] 验证：新增 `Test/test_update_service.py`(10) 与 `Test/test_feedback.py`(10) 全 PASS；
      浏览器实测 6 项功能；`Test/` 7 个全 PASS；端点 16/16；`tsc`+`build` 通过
- [x] **Issue #20 已关闭**（其余验收项此前已交付）

### v2.2.1 — 修复自定义仪表盘不显示数据：`since` 参数 400（2026-10-21，分支 `feature/flow-enhancements`）

- [x] **根因定位**：`dashboards.py` 用裸 `datetime.fromisoformat(since)`，而前端起始时间由
      `Date.toISOString()` 写入、带 `Z` 后缀；Python 3.8 的 `fromisoformat` 不支持 `Z`
      （3.11 才支持）→ **设置过起始时间的仪表盘 snapshot 恒定 400**；
      前端 `catch` 又静默吞错 → 组件一律显示「请先选择测试用例」，数据其实一直都在
- [x] **后端修复**：改用项目已有的 `app.core.timeutils.parse_iso_utc()`
      （`Z` 归一为 `+00:00`，兼容 naive / 带偏移），与 `logs.py` 保持一致；
      非法输入仍返回 400，不静默忽略
- [x] **前端修复**：`loadSnapshot` 失败改用 `handleApiError` 弹出提示，不再静默吞掉
- [x] **新增回归测试 `Test/test_dash_since.py`**：10/10 通过（`Z`/naive/`+00:00`/非UTC偏移/
      仅日期 均接受；非法值仍 400；未来时间过滤为 0 条；两个既有仪表盘均 200）
- [x] **无头浏览器实测**：4 个组件全部出数（byte1 PASS·2·采样20 / 趋势曲线 / 判定汇总
      byte0~byte2 全 PASS / 执行统计 36·26·10·72.2%）；控制台 400 消失，Empty 提示 0 个
- [x] 回归：`Test/` 7 个全 PASS；端点 **16/16**；用例 89 条；DEV-002 / DEV-004 仍 connected

### v2.2.0 — 英文界面补全：逐页治理 + 复查（2026-10-19，分支 `feature/flow-enhancements`）

- [x] **界面中文（排除注释）858 → 0**；接入 i18n 的页面 2/16 → **16/16**
- [x] **词条分层**：`messages.ts` 只留手写 115 条；批量词条拆到
      `extraKeys.ts`(181) + `extraKeys4~12.ts`(855)，模块加载时合并进 zh/en（幂等）
      总计 **115 手写 + 1036 批量，en-US 缺失 0**
- [x] **逐页推进 16 页**：Logs → Dashboard → DebugTerminal → Reports → CustomDashboard →
      SkillEditor → Plugins → ModelConfig → Devices → ExecutionPlanner → TestCases →
      AIChat → Executions → ProjectManager → TestFlowEditor → PluginEditor，每页翻译后单独编译
- [x] **工程性处理**：模块级常量改工厂（Plugins.columns / TestFlowEditor.PALETTE·VALUE_TYPE_OPTIONS /
      ProjectManager.WIDGET_TYPE_LABEL·ON_ERROR_LABEL / PluginEditor.TEMPLATE_TYPE_LABEL /
      SkillEditor.SKILL_SCAFFOLD / AIChat.BUILTIN_SKILLS）；非组件函数加 `t` 形参
      （DebugTerminal.createWebSocket / AIChat.readFileAsBase64）；9 个子组件补 hook；
      PluginEditor 模板回调 `t` 改名 `tpl` 避免遮蔽
- [x] **误替换防护**：JSON 键名负向预查 `(?!\s*:)`；混合串转模板字符串；
      每批替换后统一归一 `attr=t('k')` → `attr={t('k')}`；修复 6 处未闭合模板字符串
- [x] 验证：界面中文 0；`tsc` + `build` 通过；dev 编译 5/5 `200`；反引号配对全偶数；
      `Test/` 7 个 + `test_blocking` 6 项全 PASS；端点 **16/16**；用例 89 条；
      PeakCAN 与 MG100 均 connected
- [x] **第二遍复查已执行**：排除注释后界面中文 **0**，各页均为 0

### v2.1.0 — 执行管理器完善 + 自定义仪表盘优化（2026-10-18，分支 `feature/flow-enhancements`）

**执行管理器**
- [x] **新建测试计划**：顶部「新建计划」一键清空草稿（不动已保存计划）
- [x] **撤销 Ctrl+Z / ⌘Z**：快照栈（items + 计划名 + 循环 + 并行 + 失败策略），
      最多 50 步；加入用例/移动/删除/合并组/拆分组/改属性/批量复制删除/新建 均入栈；
      输入框内不拦截（保留原生撤销）；按钮显示可撤销步数
- [x] **计划项多选**：勾选列 + 全选/取消；**复制选中**（克隆追加，新 id）/ **删除选中**
- [x] **已有计划可操作**：点击整行选中并编辑（当前计划高亮）；行内**复制**
      （`/duplicate` 后自动打开副本）与**删除**（Popconfirm；删的是当前计划则回到新建态）

**自定义仪表盘**
- [x] **限值改琥珀色**：趋势线本已琥珀，文案「参考」→「**限值**」；
      数据组件 `detail` 仅 `status==='fail'` 用红，其余用琥珀；
      数据组件**新增限值徽标**（琥珀描边 `≥x · ≤y`）；
      配置抽屉给数据组件补上「限值下限/上限」（此前没有）
- [x] **执行统计：清零 + 可选起始时间**：DatePicker(showTime, 可清空) + 「清零」
      按钮（起始时间设为当前时刻，计数归零）；窗口生效时琥珀提示「统计自 … 起（N 条）」
- [x] 后端配套：`GET /dashboards/snapshot` 新增 `since`（ISO-8601）按 created_at 过滤，
      非法值 **400 / 40017**；落在 `data_source.since`，刷新后保留

**验证**：计划 新建201/复制/校验valid=True/删除200 无残留；since 115→0→115，非法 400；
`Test/` 7 个 + `test_blocking` 6 项全 PASS；`tsc` + `build` 通过

### v2.0.1 — PeakCAN 连接回归修复 + 英文版补全（2026-10-18，分支 `feature/flow-enhancements`）

**1）修复：PeakCAN 无法连接（v2.0.0 自引入回归）**
- [x] 根因：v2.0.0 线程化时写成 `run_blocking(can.interface.Bus, **bus_kwargs)`，
      而 `run_blocking` 只收 `*args` → `TypeError: unexpected keyword argument 'interface'`；
      被 `except Exception` 兜住后经 `_explain()` 误报成「内核模块没加载」
- [x] 修根因：给 `run_blocking` 补 `**kwargs` 转发（对齐 `asyncio.to_thread` 语义）
- [x] 堵误导：`connect()` 异常分支拆两类 —— CAN/OS 错误走人话解释；
      **其余异常 `logger.exception` 后原样抛出**，不再包装成硬件问题
- [x] 验证：`POST /devices/connect` → **200 / status: connected**

**2）防复发：新增 `Test/test_blocking.py`（6 项全 PASS）**
- [x] kwargs 被正确转发（本次故障直接回归点）/ 位置参数仍生效 / 混用 /
      阻塞调用在其它线程 / 阻塞期间事件循环未被卡住 / 异常向上传播
- [x] 教训：给"转发调用"类工具函数补参数能力时，必须同步补覆盖新签名的测试

**3）英文版补全**
- [x] 新增 `src/i18n/extraKeys.ts`：三批共 **181 条** `中文 → [key, 英文]`
      （EXTRA 表格列名/状态/标签页/节点/数据类型；EXTRA2 卡片弹窗区块标题；EXTRA3 操作反馈/按钮/空状态）
- [x] 原 16 页中仅 2 页接入 i18n → **现 16/16 全部接入**（含子组件 PluginManagement /
      TerminalWindow / SectionTable / PlanPreview / ComMonitorCard）
- [x] 模块级常量改工厂：`Plugins.columns`、`TestFlowEditor.PALETTE` / `VALUE_TYPE_OPTIONS`
- [x] **词条 296（115 手写 + 181 批量），en-US 缺失 0**
- [x] 待办：页面内仍有约 1587 处长尾中文（长句提示/tooltip/告警正文），建议按页拆小批推进

**4）验证**：`test_blocking` 6/6 PASS；原 7 个脚本全 PASS；PeakCAN+MG100 均 connected；
命令期间 `/health` 最大 111 ms；`tsc` + `build` 通过；用例 89 条

### v2.0.0 — 执行卡死修复 + 响应性能优化 + Issue #23 硬编码色 token 化（2026-10-17，分支 `feature/flow-enhancements`）

**1）修复：执行中的测试突然卡住（P0）**
- [x] 根因：`MiniGateway100Plugin.send()` 是 `async def` 却在事件循环里直接调 pyserial
      `write/read`——同步 `read()` 阻塞整个 asyncio 事件循环，进度推不出去、所有 API 排队
- [x] 实证：发命令时轮询 `/health`，最大延迟 **2024 ms**（= 插件 timeout 2.0s），空闲时仅 114 ms
- [x] 新增 `app/core/blocking.py`：16 线程 `BLOCKING_POOL` + `run_blocking()`
- [x] `communication/__init__.py` 的 `_run_in_thread()` 改为委托，不再另建线程池
- [x] MG100：write / read / reset_input_buffer / Serial() 构造 / close() 全线程化
- [x] PeakCAN：Bus() 构造 / bus.send() / bus.shutdown() 线程化
- [x] 效果：命令期间 `/health` 最大延迟 **2024 → 16 ms**，6s 内请求数 243 → **915**（吞吐 ~3.8×）

**2）优化：按键卡顿 / 加载等待**
- [x] 新增 `frontend/src/hooks/usePolling.ts`：`document.hidden` 时跳过轮询、
      上一次未结束不发起新的、回到页签立即补一次
- [x] 接入 6 处：Executions(2s) / ExecutionPlanner(2s) / Logs(5s) / DebugTerminal(5s) /
      Dashboard / CustomDashboard

**3）Issue #23：172 处硬编码色 token 化**
- [x] 扫描 207 处，扣除调色板定义 29 处，实际治理 **170 处**
- [x] 新增应用级语义变量：表面/描边/文字/交互/状态/场景 + 图表色序 `--app-series-1…8`
      + 终端常量 `--term-*`（调试终端恒深色，不随主题翻转）
- [x] 绿色 `#52c41a` → `--app-pass`（仪器蓝），**绿色彻底退出**；红/琥珀/蓝各自归位
- [x] `main.tsx` 的 `colorPrimary` 引用 `blue[500]`；`theme/index.tsx` Layout 背景用 `graphite`
- [x] **结果：除 `theme/tokens.ts` 外硬编码色归零**

**4）验证**
- [x] `Test/` 7 个脚本全 PASS；16 个端点全通过
- [x] `tsc --noEmit` + `npm run build` 通过；dev 可编译 5 个新/改模块
- [x] 数据完整：用例 89 条、设备 DEV-001~004
- [x] **Issue #23 已关闭**（24 个弹窗规范部分未做，已在 Issue 中说明）

### v0.17.1 — 工程配置可视化：仪表盘画 layout 图、执行计划展开用例（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **仪表盘改为 layout 缩略图**：12 列栅格按 `x/y/w/h` 绝对定位，行高 26px，
      框内显示挂件标题 + 中文类型名（解析值/趋势图/判定汇总/执行统计/设备状态/通信日志）；
      配色走 `--flow-*` 变量，深浅主题都正常
      —— 实测「长稳视图」4 挂件 12 行 → 320px，「调试视图」3 挂件 14 行 → 372px
- [x] **原始参数未丢**：折叠面板「查看原始参数」仍可展开完整 `layout` + `widgets` JSON
- [x] **执行计划展开计划项**：列 = 组 / 序 / **测试用例名称**（由 bundle 内 `test_cases`
      解析 `testcase_id`）/ 循环 / 前置延时 / 后置延时 / **设备名称**（解析 `resolved_device_ids`）/ 节点数；
      顶部补整体循环、最大并行、出错策略、计划项数
- [x] 验证：2 个仪表盘**越界挂件 0、缺标题 0**；2 个计划 4 个计划项**用例名未解析 0**；
      `tsc` + `build` 通过；dev 可编译 `ProjectManager`

### v0.17.0 — 项目工程树状展开 + 主页面展示工程配置（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **左侧工程树**：顶层 = 工程名（版本 Tag + 配置总项数 + 损坏标记），
      子节点 = 7 个配置段各带条数；可展开/收起，选中态高亮
- [x] **点击工程名 → 右侧主页面展示该工程全部配置**（调 `GET /api/projects/{name}`）
- [x] **点击单个配置段只看该段**；点工程名看全部
- [x] **打开页面自动选中最近保存的工程**，不必先点一下才有内容
- [x] **通用配置表 `SectionTable`**：列从数据自动推导（前 30 行字段并集，最多 8 列），
      对象/数组 JSON 化后截断 60 字符 + `title` 悬停看完整值；布尔→是/否，空值→`-`；
      `api_key_encrypted`/`password`/`secret`/`token` 一律不展示；>20 行分页、最多 200 行
- [x] **操作按钮上移到详情标题栏**：导入 / 下载 / 覆盖同步 / 重命名 / 删除；
      删除当前工程时同步清空详情面板
- [x] **清理**：删除失效的旧表格 `columns`（87 行）与 `Table` 导入；
      按钮文案改用已有 i18n 键
- [x] 验证：`tsc` + `build` 通过；dev 可编译 `ProjectManager`；
      `GET /api/projects/CANTestPeakCANandMGW` 200（545 KB），7 段完整（1/4/3/5/89/2/2）

### v0.16.1 — 流程图节点配色细化：莫兰迪色调（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **面板菱形块补底色**：此前「判断」是 `clip-path` 菱形 + 透明底，看着像什么都没有；
      现改为菱形块**直接用该类型填充色**（与画布一致），菱形改由 `rotate(45deg)` 小方块标识
      —— 边框不再被裁掉，文字也不被切角
- [x] **底色重排（莫兰迪色调）**：低饱和中明度；**文字统一改白色**，循环例外（浅琥珀底+深琥珀字）
      - 开始 `#1D5B75` 深莫兰迪蓝 · 初始化 `#427A94` 蓝灰 · 操作 `#3D4752` 石墨灰（**不再是近黑**）
      - 判断 `#246F90` 仪器蓝（偏浅）· 循环 `#F9E9CE` 浅琥珀 + `#875D21` 深琥珀字
      - 延时 `#5A6672` 中灰+虚线 · 结束 `#232A31` 深灰
- [x] **白字对比度全部达 WCAG AA（≥4.5:1）**：循环原本 3.01 不达标，已压暗至 4.86
- [x] **连接点统一仪器蓝 `#2296C4` + 浅色轮廓线**，不再随节点类型变色
- [x] **选中时连接点高亮**（变 `blue[300]` + 外圈蓝环）
- [x] **判断的是/非出口保留深浅对比**且同属蓝色系：是 `#156B8C`（深）· 非 `#8FCBEA`（浅）
- [x] 验证：7 种底色对比度脚本核算 0 不达标；`tsc` + `build` 通过；硬编码色仍为 0

### v0.16.0 — 流程图编辑器 UI 统一：方案 A + 循环改用琥珀（Issue #22）（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **新增 `src/theme/cssVars.ts`**：把 `tokens.ts` 色阶派生为 CSS 变量（`--g-*/--b-*/--a-*/--r-*` +
      `--flow-*` 语义层），由 `ThemeProvider` 注入；取值全部由 token 计算（`mix()` 混色），
      **不二次硬编码**；浅/深两套表面值随主题切换
- [x] **48 处硬编码色全清零**：`TestFlowEditor.tsx` 内已无 `#xxxxxx` 与 `rgba()`
- [x] **节点类型编码（方案 A）**：开始=描边空心蓝 / 初始化=低饱和蓝底 / 操作=石墨实心 /
      判断=菱形（形状编码，颜色不参与）/ 延时=虚线 / 结束=弱化深底（**不再是红色**）
- [x] **循环=唯一使用琥珀的类型**：深底 + 1px 琥珀描边 + **左侧 3px 琥珀色条** + 琥珀图标文字；
      脚本校验 `nodeSurface()` 7 个分支中**只有 `loop` 引用琥珀**
- [x] **琥珀边界**：循环（类型）= 静态描边+色条；运行中（状态）= `NodeRuntimeRing` 外圈
      **脉冲光晕** + `SyncOutlined` 旋转角标 —— 静态 vs 动态，形态上不会混淆
- [x] **圆角统一 ≤ 6px**（取消开始/结束 20px 胶囊）
- [x] **撤销/重做换原生图标**：`UndoOutlined` / `RedoOutlined`，**删除镜像翻转 hack**
      （此前"返回"与"撤销"共用 ArrowLeft，重做是同一个箭头水平翻转）
- [x] **工具栏 5 组**：① 历史 · ② 编辑 · ③ 危险（删除）· ④ 视图 · ⑤ 提交
- [x] **去紫色**：「生成代码」按钮的 `#722ed1` 改为与保存一致的单一主色
- [x] **画布/全屏/代码区改 token**：全屏不再出现白色孤岛；`<pre>` 不再是写死 VSCode 深色
- [x] **节点面板**：120 → **148px**，深色卡片 + hover 抬升 + 拖拽手型
- [x] **AntD 预设语义色清除**：`cyan`/`geekblue`/`purple`/`blue`/`green` Tag 全改中性或主题变量
- [x] 验证：脚本逐条核对验收清单通过；`tsc` + `build` 通过；`Test/` 7 个全 PASS；
      含 2 循环的 7 节点流程保存+生成代码均 200（6343 字符）；**Issue #22 已关闭**

### v0.15.0 — 抽屉展开面积 + P3 页面级优化（Issue #21，从 #20 拆分）（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **抽屉宽度与交互**：展开宽度 420px → `min(720px, 58vw)`（按视口收敛）；
      收起态**单击展开、双击直接全屏**；**全屏按钮保留**（`Esc` 退出）
- [x] **插件中心三路由合并**：`/plugins` + `/plugin-editor` + `/skill-editor` → 单一 `/plugins` 路由内三个 Tab；
      编辑器面板 `lazy()` 懒加载；**旧路由保留并自动落到对应 Tab**
- [x] **⌘K / Ctrl+K 命令面板**：搜索导航 12 项 + 设备（按设备ID号/名称）+ 用例（直达流程图）；
      `↑↓`/`Enter`/`Esc` 全键盘可达；导航定义抽到 `src/config/navigation.tsx` 供侧栏/顶栏/面板共用
- [x] **三栏布局**：执行计划复核为**原本已是三栏**（6/13/5），补齐缺 width 的「用例」列；
      调试终端由两栏扩为三栏，新增「指令 / 历史」列（按设备记录，点击填入输入框）
- [x] **流程图沉浸模式**：进入 `/testcases/:id/flow` 自动收起侧栏并让输出区让位，顶栏提供「退出沉浸」
- [x] **项目向导**：三步「选配置段 → 命名 → 生成」，复用另存为能力；不改动当前系统配置
- [x] **P2 收尾**：Logs / Reports / Plugins / ExecutionPlanner / Executions / TestCases 全部改用
      `DataTable` 并补齐列宽，消除列宽告警
- [x] **无障碍**：新增 `:focus-visible` 焦点环（仪器蓝）、`prefers-reduced-motion` 关闭动画
- [x] 验证：`tsc` + `npm run build` 通过；dev 可编译全部新模块；`Test/` 7 个全 PASS；
      15 端点失败数 0；用例 89 条、设备 DEV-001~004 完整；**Issue #21 已关闭**

### v0.14.0 — GUI 三区布局重构（Issue #20，P0–P2）（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **P0 主题 Token**：`src/theme/tokens.ts`（primitives → semantic → component）+ `ThemeProvider`
      （darkAlgorithm、localStorage 持久化、顶栏切换）。配色 3 主色 + 1 状态色
      （石墨灰 / 仪器蓝 `#2296C4` / 琥珀 `#E8A33D` / 信号红 `#FF7B72`）
- [x] **P1 布局导航**：`AppLayout` 重写。左侧 208/56，3 组 8 项（配置与接入 1 / 设计与编写 4 / 系统 3）；
      顶栏看板▾ + 工具▾ + 语言/主题/重启；状态条 32px（后端/已连设备/运行中）常驻
- [x] **P1·B 输出/交付抽屉**：`OutputDock.tsx` + Zustand 全局 store。三态（收起 34 / 展开 420 / 全屏），
      双 Tab（测试执行 / 输出报告），pin 持久化，未 pin 切页自动收起，**点「启动」自动展开**，
      收起态琥珀色运行数徽标，`Esc` 退全屏；路由为 /executions 或 /reports 时让位避免重复渲染
- [x] **P2 组件规范**：`DataTable`（强制列宽 + scroll.x + dev 告警）、`StatusTag`（图标+文字+颜色）、
      `PageContainer`、`EmptyState`、`MonoText`；已在设备管理页落地示范（闭环 #17 / #19）
- [x] **其它验收项**：`.big-dash` 的 4 处 `!important` 全部删除（改提高选择器特异性）；
      全站无残留 `ExperimentOutlined` 烧杯（统一 `DiffOutlined`）
- [x] 验证：`tsc` + `npm run build` 通过；dev 可编译全部新模块；`Test/` 7 个全 PASS；15 端点失败数 0
- [ ] **未完成（P3 页面级优化，约 2 人日）**：总览重构、执行计划三栏、调试终端三栏、流程图沉浸模式、
      插件三页路由合并、⌘K 搜索、项目向导，以及 P2 剩余表格页改造 —— **Issue #20 保持开启**

### v0.13.0 — 设备ID号 + 切换设备重生成代码 + 加载性能优化（2026-10-17，分支 `feature/flow-enhancements`）

- [x] **设备ID号（稳定标识）**：新增 `Device.device_key`（唯一索引），启动迁移按创建顺序自动回填
      `DEV-001/002/…`；用例改按 **设备ID号** 关联。解析顺序：device_key → 旧 device_id（兼容）
      → 命令推断协议。重复 ID 号创建/更新 → **409**
- [x] **存量迁移**：`POST /api/testcases/backfill-device-keys` 把旧 `device_id` 绑定翻译成
      `device_key`（**93 个节点**，幂等）；`stale-devices` 已支持按 device_key 判定
- [x] **切换设备接口**：`POST /api/testcases/{id}/switch-device`（按设备ID号重绑定，
      可选 `from_device_key` 限定范围），**切换后原子地重新生成并返回代码**，消除"换设备后代码还是旧的"漂移
- [x] **前端**：用例列表新增「切换设备」按钮（选目标/来源设备ID号，完成后显示切换数与重新生成代码）；
      设备列表新增「设备ID号」列（可点击修改，提示"换硬件时把同一个号赋给新设备"）
- [x] **性能优化①（主因）**：`node_modules/.vite/deps` **为空**，dev 下每开一页要逐文件拉
      antd/图标/reactflow 等数千模块。新增 `optimizeDeps.include` 后 **deps 0 → 32**，页面切换请求数骤降
- [x] **性能优化②**：`Executions.tsx`(1382 行) 每条 WS 消息都触发整页重渲染 → 改为 **100ms 批量合并**，
      暂停缓冲与卸载兜底 flush 保留
- [x] 验证：设备ID号/切换 **15/15**（含切回还原）；真实执行 `tc_9158200f` **passed** 且通信日志 +42；
      `Test/` 7 个全 PASS；套件 29/29、32/32、7/7、工程闭环 PASS；15 端点失败数 0；`tsc`+`build` 通过

### v0.12.1 — 修复「用例无法执行 + 通信窗口无消息」（2026-10-16，分支 `feature/flow-enhancements`）

- [x] **根因**：流程节点把设备写死在 `config.device_id`，而**设备删除后重新添加会拿到新 id**
      → 89 个流程中 9 个绑定了设备且**全部悬空**；`_resolve_device()` 无条件返回该 id →
      `send_command()` 抛 `is not connected` → 步骤失败、**一条指令都没下发 → 通信窗口空白**
- [x] **引擎**：`_resolve_device()` 先查库校验绑定。悬空 id → WARNING + 回退协议推断；
      存在但未连接 → 返回 None 并点名该设备（**绝不静默改投别的设备**，避免 CAN 报文发给网关）
- [x] **存量清理**：新增 `GET /api/testcases/stale-devices`（只读报告）与
      `POST /api/testcases/rebind-devices`（按节点命令推断的协议重绑定）。本次修复 **93 个节点**，修复后失效绑定 **0**
- [x] **协议推断补漏**：`_PYCAN_FN_RE` 增加 `can\.Bus|Bus`，并把 `match` 改为 `search`
      （`打开 PCAN 通道：can.Bus(...)` 这类中文前缀命令此前识别不到）
- [x] **前端预防**：测试用例页检测失效绑定 → 告警条说明"为什么通信窗口没消息" + 「重新绑定设备」按钮
- [x] **测试稳定性**：`Test/test_ws_monitor.py` 偶发失败已修——状态轮询抢在 WS 终帧前退出
      （改为收尾排空在途消息）；200ms 周期用例 60s 窗口不够（改为等至终态，上限 300s）
- [x] 验证（真实硬件）：4 个原本失效的用例全部 **passed** 且产生通信日志（+42/+4/+34/+36）；
      WebSocket 收到完整事件序列；`Test/` 7 个脚本**连续两轮全 PASS**；
      功能套件 29/29、32/32、7/7；15 个端点失败数 0

### v0.12.0 — 新建项目工程 + AI 助手改版 + 性能优化与国际化（2026-10-14，分支 `feature/flow-enhancements`）

- [x] **新建项目工程**：`POST /api/projects/new`，清空设备/插件/Skill/测试用例(含流程图)/执行计划/仪表盘，
      **默认保留 AI 模型配置**；执行历史与通信日志不删；需显式 `confirm`；返回各段清除条数与 `kept` 列表
- [x] **AI 助手布局**：输出区（对话/用例/记忆/查询）在**上方**，输入区（含附件）固定在**下方**
- [x] **附件**：文本文件内联为带标记正文块（超长截断）；图片按 provider 组装多模态内容
      （OpenAI 系 `image_url` data URI / Anthropic `source.base64`）；模型不支持视觉时**自动降级重试**并提示
- [x] **性能优化**：`CommunicationLog` 移除与 `idx_logs_*` 重复的 `index=True` 并 DROP 遗留 `ix_*`（索引 9→6）；
      SQLite PRAGMA 调优（WAL / NORMAL / 16MB / temp MEMORY，FK 保持 OFF）；`lifespan` 分段计时；
      日志表格虚拟滚动 + 页大小 20~200
- [x] **国际化**：`src/i18n/`（messages + `LanguageProvider` + `useI18n`），顶栏语言切换、
      localStorage 记忆、antd locale 与 dayjs 同步；未翻译键回退中文；**103 键 100% 覆盖**
- [x] 验证：新建项目 21/21（含还原）、附件 7/7（模型支持视觉）、接口 32/32、MG100 29/29、
      `Test/` 7 个全 PASS、14 端点失败数 0、索引 9→6 且 `journal_mode=wal`、
      启动 db 68ms / stale reset 197ms、`tsc` + `npm run build` 通过

### v0.11.0 — MG100 以太网 + 设备接口可配置 + 修复 GitHub Open Issue（2026-10-14，分支 `feature/flow-enhancements`）

- [x] **MG100 插件双传输**：新增 `transport` 配置（`serial` 默认 / `ethernet`）；以太网默认
      `host=192.168.0.120`、`tcp_port=6025`（**串口号已占 `port` 键，TCP 端口另用 `tcp_port`**）；
      抽出 `_write_frame` / `_read_frame` / `_flush_input` 三原语供两种传输共用；
      以太网收帧带回退缓冲，超时返回已收部分不挂死；连接失败给出可操作报错
- [x] **PeakCAN 不改**（用户确认硬件不支持以太网）
- [x] **接口注册表** `app/core/interfaces.py`：串口 / USB / 以太网 / **PCIe** / **PXI** / CAN / GPIB
      共 7 种接口的参数单一数据源；能落列的用列，其余进 `config` JSON
- [x] **设备接口可编辑**：`GET /api/devices/interfaces`、`GET|PUT /api/devices/{id}/interface`；
      切换接口会清空其它接口的地址列与其它接口的 config 键
- [x] **前端**：新增 `InterfaceConfigModal`，按接口类型动态渲染参数；设备列表每行加「配置接口」按钮
- [x] **通信层**：新增 `PCIeInterface` / `PXIInterface`（明确模拟模式，收发带 `[Simulated …]` 标记）；
      修复 `EthernetInterface` 连接失败却 `_is_connected = True` 返回假数据的隐患（模拟改为显式 `simulate`）
- [x] **GitHub Open Issue 清理**（16 个）：实际修复 **#8**（9 个集合路由无尾斜杠 307 → 中间件内部改写）、
      **#9**（`os.chdir` → `sys.path`；`Test/_testutil.py` 消除 `StopIteration` 并支持 SKIP；修正 3 处过期断言）、
      **#10**（WS 地址 `/ws` 不存在 → 改为真实端点，同步修 4 处文档）、
      **#11**（RIGOL `usbtmc` 默认 `/dev/usbtmc0` → 必须显式填 `device`）、
      **#12**（单一 2.33MB chunk → 路由级 lazy + manualChunks，路由块 1.5–30 kB）
- [x] 核对 #1 #2 #3 #4 #5 #6 #7 #13 #14 #15 #16 为**历史已修**（v0.7.0~v0.10.0 已落地）
- [x] 验证：MG100 以太网 29/29（mock TCP）；设备接口 32/32；工程文件闭环幂等；
      **`Test/` 全部 7 个脚本全 PASS**；10 个集合路径无尾斜杠 200；`tsc` + `npm run build` 通过

### v0.10.0 — AI 助手增强 + 项目工程文件 + 流程图代码生成修复（2026-10-13，分支 `feature/flow-enhancements`）

- [x] **版本号统一（遗留项）**：`config.py` 的 `APP_VERSION` 与 `aitestlab.nsi` 安装包版本同步到看板口径
- [x] **修复「流程图编辑后重新生成代码失败」**：根因是 `handleSaveFlow()` 的**裸 `catch`** 把 `PUT /flow` 的任何失败
      都当成「流程不存在」并回退 `POST`（同样 400）→ 弹出「保存失败」后 **`handleGenerateCode()` 并未中止**，
      继续用库里**上一版旧流程**生成，于是"生成成功却是旧代码"。改为：仅 404 回退创建、其余错误如实上报并返回 `false`，
      **保存失败即中止生成**并在抽屉里说明原因
- [x] **后端加固**：`generate_python()` 空流程 `nodes[0]` 抛 `IndexError` → 500，改为防御式归一化；
      `generate-code` 空流程返回 **400 + `40013`** 明确提示
- [x] **AI 助手 · 预览**：新增 `TestCasePreviewModal`，展示名称/描述/整体预期/设备/标签 + 步骤表
      （命令、参数、预期、`flow_type`），弹窗内可直接「添加到测试用例列表」
- [x] **AI 助手 · 一键添加**：保留「一键添加全部」，单项按钮改名为「添加」
- [x] **AI 助手 · 对话式修改**：新增 `ai_service.refine_test_cases()` + `POST /api/ai/refine-testcases`——
      把完整用例集 + 自然语言指令交给模型，返回**完整修订集**（非 diff）；模型返回不可解析 JSON 或空集时
      **保留原用例**并告警，绝不静默清空。实测：延时 1000→500ms 且新增步骤 3
- [x] **项目记忆文件**：新增 `memory_service.py` + `app/api/memory.py`（`backend/memory/Project_<名> Memory.md`）；
      `POST /api/ai/memory/extract` 由 AI 提炼**决策/约定/事实/约束与风险**四类要点（带已有记忆去重），
      前端**先审阅修改再写入**；支持追加/覆写、查看、删除
- [x] **项目工程文件**：新增 `project_service.py` + `app/api/projects.py`（`backend/projects/Project_<名>.json`），
      打包**插件 / Skill / 测试用例（含流程图）/ 执行管理器 / 设备 / 仪表盘 / 模型** 7 段；
      **`api_key_encrypted` 永不写入**；导入按 `id` → 自然键匹配，**重复导入零新增（幂等）**；
      `merge`/`replace` 两种模式；跳过机器相关字段（插件 `file_path`、设备 `status`）
- [x] **前端新增「项目工程」页**（路由 `/projects`）：导出下载 / 上传导入 / 另存为 / 覆盖同步 / 重命名 / 删除，
      展示各段条数与导入结果统计
- [x] **踩坑**：`Column.key` 不可信——`extra_meta = Column("metadata")` 的 `key` 仍是 `"metadata"`，
      `getattr` 取到 SQLAlchemy `MetaData` 导致 `jsonable_encoder` **无限递归（裸 500）**；
      改用 mapper `get_property_by_column(col).key`
- [x] 验证：工程文件 7 段导出（模型1/设备6/插件3/Skill5/用例88/计划2/仪表盘2）；另存为→读取→导入→重命名→删除全 200；
      **二次导入 7 段 `created=0`（幂等）**；全文**不含** `api_key_encrypted`；空流程生成 **400（修复前 500）**；
      节点编辑后生成正常且反映修改；回归 **12 个端点失败数 0**；`tsc --noEmit` / `npm run build` / `compileall` 全通过

### v0.9.0 — 测试用例执行管理器（2026-10-09，分支 `feature/flow-enhancements`）

> 依据 `docs/PRD_执行管理器_ExecutionManager - Copy.md` 实施。用户拍板：只做最小可用闭环（不做运行时设备租约 FR8、不做 WS 监控）；
> 时区 Issue #7 先修再动工；冲突判定按设备粒度，**且两个不同设备共用同一端口也算冲突**。

- [x] **P0 时区（Issue #7）**：新增 `app/core/timeutils.py`（`utc_now()` / `from_timestamp()` / `parse_iso_utc()` /
      `UTCDateTime` 列类型）；58 处 `datetime.utcnow` 全量替换；存库仍为 naive UTC 串（兼容老数据与排序），
      读出为 aware UTC → API 输出带 `+00:00`，前端 `new Date()` 解析正确（原先慢 8 小时）
- [x] **数据模型**：新增 `execution_plans` / `execution_plan_items` / `execution_plan_runs` 三表；
      `test_executions` 扩展 `plan_run_id`/`plan_item_id`/`iteration`/`group_no`（单用例执行为 NULL，行为不变）
- [x] **设备解析**：`resolve_item_devices()` 按「显式指定 > 流程内 device_id > 协议推断」三级解析，返回**集合**；
      新增设备资源键（device/serial/can/visa/net），支持**同端口冲突**判定
- [x] **校验引擎**：`DEVICE_CONFLICT` / `PORT_CONFLICT` / `UNRESOLVED_DEVICE_IN_PARALLEL` /
      `PARALLEL_LIMIT_EXCEEDED` / `DUPLICATE_CASE_IN_GROUP` 为 Error（阻断）；设备离线/多候选/空流程为 Warning；含时长预估
- [x] **调度器**：组间串行、组内并行（受 `max_parallel` 限制）、迭代串行（含 `loop_interval_ms`）、前后置延时（可中断）；
      每次迭代生成独立 `TestExecution` 带批次归属；失败策略 `abort_all`/`continue`/`abort_group`
- [x] **API**：计划 CRUD + 复制 + 草稿校验 `/validate`（免保存）+ `/resolve-devices` + `/run`（**409 阻断**）+ 批次详情/列表/停止
- [x] **前端**：新增 `ExecutionPlanner` 页（路由 `/execution-plans`，菜单「执行管理器」）——三栏布局、
      多选用例加入、上下排序、并行分组、循环/延时、设备三态、冲突面板（含自动串行化）、运行监控抽屉（轮询）
- [x] 验证：同设备冲突 / **异设备同端口冲突** / 并行组内未确定设备 / 组大小超限 均正确检出；
      绕过前端 `POST /run` 返回 **409 不启动**；真实硬件批次 3/3 passed（组内并行同刻开始、迭代 2 次、组2 串行在后）

### v0.8.6 — 启动反馈 + 代码生成提示 + 过期断言修复（2026-10-09，分支 `feature/flow-enhancements`）

- [x] **启动「像卡住」**：实测 `POST /executions/run` 仅 43~179ms，真因是 `TestCases.handleRun` 没有 loading
      状态。修复：新增 `runningId`，按钮点击即挂 spinner（`loading={runningId === record.id}`）
- [x] **新增分支后生成代码「没指令」**：非 bug —— MG100 节点「执行命令」填的是中文描述，
      `_extract_commands` 取不到指令，生成器回退为下发原文。改进：回退时输出
      `# ⚠️ 未能解析出结构化设备指令…` 注释（该回退对 SCPI/串口是必需的，不能删）
- [x] **正确操作**（告知用户）：节点命令填真实指令 `@11_TSTOP;` / `@11_CONFIG=CAN1,BAUDRATE,500K;` /
      `@11_TSTRT;`；「保持 4000ms 窗口」节点应建成延时节点而非动作节点
- [x] **修复 `Test/test_codegen.py` 过期断言**（既有失败）：`if voltage > 10:` → `if _cond(...)`；
      `send_command('@11_HELLO;')` → `send_command(_r(...))`。生成器行为是有意且更优的，故改断言不改产品
- [x] 验证：`tsc` 通过；`test_codegen` 5 组全绿；`tc_7653d5b2 passed 4/4`；生成代码语法合法且带 ⚠️ 提示

### v0.8.5 — 修复「AI 生成测试用例必失败」+ 新增执行日志（2026-10-08，分支 `feature/flow-enhancements`）

- [x] **Issue #13 根因**：前端 `AIChat.loadDevices()` 用 `extractData` 解析**分页**的 `/api/devices/`，`devices` 变成对象，
      `devicePayload()` 调 `.map()` 抛 `TypeError`（发生在调用生成 API 之前）→ 默认文案「生成测试用例失败」。
      修复：改用 `extractItems` + `Array.isArray` 兜底。实测后端接口本身 HTTP 200。
- [x] **Issue #15**：`_errorMessage` 支持解析 422 数组 detail / 非 JSON 错误体 / 本地 JS 异常，不再退化成默认文案
- [x] **Issue #13 防御**：`ai_service._sanitize_json()` 把 NaN/Infinity 换成 null，避免响应序列化 500
- [x] **Issue #14**（v0.8.4）：`peakcan_plugin.receive()` 过滤 `is_rx=false` 自回环帧
- [x] **执行日志**：`logs/program/`（全局程序日志 10MB 轮转）+ `logs/communication/`（全局通信）+ `logs/executions/<id>/`
      （每次执行一个文件夹，program + communication，10MB 轮转）；新增浏览 API `/api/logs/program/files`、
      `/api/logs/executions/{id}/files`、`/api/logs/executions/{id}/file/{name}`
- [x] 验证：后端生成 200（2 用例）；`tc_7653d5b2 passed 4/4`；自回环帧 +0；per-execution 日志生成；`compileall` + `tsc` 通过

### v0.8.3 — PeakCAN skill 补「禁止 open/close」+ 真实硬件端到端跑通（2026-10-08，分支 `feature/flow-enhancements`）

- [x] **peakcan skill**：通道开关由平台「设备管理」负责；插件只支持 `send/send_periodic/stop_periodic/receive/scan/diagnose`，
      **禁止生成 `open`/`close`**（三处写明：连接配置 / 测试场景模板 / 命令必须写进结构化字段）
- [x] **真实硬件端到端**：PeakCAN `send_periodic` 4/4 通过；MG100 `CONFIG RX 0X20` + loop 10× `MSGRX` 11/12 通过，
      **读到 `0X010203`**（PeakCAN 发的 ID 0x20 / data 01 02 03）——整条链路发→收跑通

### v0.8.2 — MG100 RX 过滤/监控逻辑 + 收发时序对齐写入生成 skill（2026-10-07，分支 `feature/flow-enhancements`）

- [x] **MG100 内在逻辑写入 skill**：定义 RX ID 后只过滤锁存该 ID、仅在 `MSGRX` 时读取返回；
      未定义 RX 时监控总线上所有报文
- [x] **收发时序对齐写入生成 skill**（`ai_service` 提示词 + MG100 skill 生成要求）：
      接收命令只读执行那一刻的报文 → 禁止「先发一次再读一次」；发送方周期/重复发送、接收方同窗口反复轮询
- [x] 验证：`compileall` 通过；真实生成（DeepSeek）产出 PeakCAN `send_periodic(period_ms=200)` + 3s 窗口 /
      MG100 `CONFIG RX 0X20` + loop 反复 `MSGRX`，同属并行组——时序对齐

### v0.8.1 — BugFix：调试终端识别 python-can 语法（2026-10-07，分支 `feature/flow-enhancements`）

> 现象：终端输入 `bus.send_periodic(can.Message(...), 0.2)` 报 `Invalid CAN string format`，命令未进发送逻辑。

- [x] **根因**：PeakCAN 插件只认 JSON 字典 / `ID#DATA` / `{` 开头字符串，python-can 库调用（`bus.send_periodic` /
      `bus.send` / `bus.recv` / `can.Message`）被当 CAN 字符串解析而报错
- [x] **修复**：插件 `send()` 顶部加 `_translate_python_can()` 翻译层（周期按秒参数×1000，非写死；支持 `bus.`/`self._bus.`
      前缀、`0x` ID、`data=[...]`、`is_extended_id/is_fd/dlc`，括号平衡处理嵌套）；执行引擎 `_extract_commands` 加
      `_python_can_commands()`（去重嵌套）+ `_infer_protocol` 识别 → `peakcan`
- [x] 验证（真实 can0）：WebSocket 终端原命令返回 `periodic_started`；`bus.send`→`sent`；`stop_periodic`→`periodic_stopped`；
      回环自检单发帧 `112233`、周期发每 200ms 回环 `32 0102` 均成功收到——软件/驱动链路跑通；`compileall` 通过
- [ ] 待硬件侧排查：`can0` `berr-counter tx≈100`（无节点 ACK），帧已发出但需确认对端 MG100 在总线/波特率/终端电阻

### v0.8.0 — PeakCAN「只收不发」修复 + 生成设备回填 + 运行时按图执行（2026-10-06，分支 `feature/flow-enhancements`）

- [x] **根因**：生成→流程图时设备信息被丢弃（`device_id` 写死 None）+ PeakCAN 命令无法从文本提取 +
      设备解析静默回退到第一个已连接设备 + 运行时 loop 假通过——四者叠加导致 PeakCAN 一条不发却被判通过
- [x] **P0**：生成时按 `device_type`/名称/`devices_required` 匹配真实设备回填 `device_id`/`device_protocol`；
      命令识别支持 PeakCAN JSON 与 `ID#DATA`；设备按「device_id→协议→任意」解析，协议不匹配直接报错不再错发
- [x] **P1**：PeakCAN 插件新增 `send_periodic`/`stop_periodic`（`period_ms` 参数化，非写死 200ms，支持 `count`/`key`）；
      skill/prompt 同步（周期默认用设备周期能力、命令写 `parameters.command`、禁伪代码；MG100 PROCESS 默认但非必须+槽位上限）
- [x] **P2**：运行时引擎改为沿 edges 走图——condition 真分支 / loop 真迭代（复用步骤行、带"第 N 轮"标记、防死循环上限）
- [x] 验证（真实硬件 MG100 + PeakCAN）：20 项逻辑断言 + 线性/循环/条件执行 + PeakCAN 单发与周期发(`period_ms=500`) 全过；
      `compileall` 与 `tsc --noEmit` 通过

### v0.7.4 — BugFix：启动执行后不实际运行（2026-10-06，分支 `feature/flow-enhancements`）

> 回归来源：v0.7.3 为标题显示用例名，在 `create_task()` 之后又用了请求会话。

- [x] **根因**：后台执行任务与请求处理器共用同一个 `AsyncSession`（v0.7.3 新增的 `_testcase_names()`
      在 `asyncio.create_task()` 之后 `await db.execute(...)`，与任务内 `async with db` 的 `close()` 并发）
      → `IllegalStateChangeError`，任务在写第一条步骤前就死掉，执行永久卡在 `running`、终端无任何消息
- [x] **修复**
      - `start_execution()`：后台任务改用**独立会话** `async_session()`，不再共享请求会话
      - `_run_execution()` 拆成包装（负责 `finally` 关闭会话）+ `_execute_flow()`（原逻辑）
      - `executions.py`：用例名查询移到 `start_execution()` 之前，`create_task` 后不再触碰 `db`
      - `main.py` 启动：新增 `reset_stale_executions()`，把残留 `running` 执行标 `error`、卡住的用例回 `draft`
        （否则重启后「启动」按钮永久禁用）
- [x] 验证（真实硬件 Mini Gateway 100）：执行 `passed`（9 步 8 通过）；`/ws/executions/{id}` 20 条事件、
      `/ws/devices/{id}` 21 条事件（终端不再空白）；停止→再次启动正常；3 条卡住的执行被清理；
      `tsc --noEmit` 与 `compileall` 通过

### v0.7.3 — 执行界面启动/停止 + 流程图全屏高亮 + 用例重命名/清空（2026-10-06，分支 `feature/flow-enhancements`）

- [x] **测试执行界面**
      - 标题显示**当前执行的测试用例名称**：后端 `executions.py` 新增 `_testcase_names()` 批量查名，
        `/run`、`GET /`、`GET /{id}` 统一回传 `testcase_name`；前端 `TestExecution` 类型补齐字段，列表无名字时按 id 回查
      - 新增「**启动**」按钮：Modal 选测试用例 → `executionAPI.run()` → 自动跟踪该执行
      - 新增「**停止**」按钮：停当前跟踪的执行或列表中运行中的执行；无运行中时提示
- [x] **流程图编辑器**
      - 新增「**全屏 / 退出全屏**」按钮（画布 `position: fixed` 铺满视口，Esc 退出）
      - **选中高亮**：选中节点蓝色外发光描边 + 提升层级；选中连线蓝色加粗 + 流动动画 + 标签高亮
- [x] **测试用例界面**
      - 每个用例支持**重命名**（Modal 输入新名称 → `update(id, {name})`）
      - 新增「**一键清空**」按钮（Popconfirm 二次确认，循环删除并统计失败数）
- [x] 验证：`npx tsc --noEmit` 通过；`python -m compileall app` 通过

### v0.7.2 — 延时节点 / 复制按钮 / 并行流程生成 / 执行界面多列（2026-10-05，分支 `feature/flow-enhancements`）

- [x] **延时节点（单位 ms）**
      - 画布新增「延时」节点（橙色 ⏱），节点弹窗用 InputNumber 配置毫秒数；节点卡片显示 `延时 N ms`
      - **代码生成器**：`delay` 输出 `_cast(_r(...,ctx),'float')` + `time.sleep(/1000)`，并计入 passed 步骤
      - **运行时执行引擎**：新分支 `asyncio.sleep`，支持 `{占位符}` 引用初始化变量 / 前序输出
      - 用例生成 `_description_to_flow` 支持 `flow_type=delay`（`duration_ms`）
- [x] **节点复制入口**：工具栏新增「复制 / 粘贴 / 创建副本」按钮（原有 Ctrl+C / Ctrl+V / Ctrl+D 保留）
- [x] **「测试用例生成」Skill 更新**：新增 `delay` 节点类型；**多设备默认拆分为并行独立流程**
      （不同设备的操作与指令分成各自独立的 test case，`devices_required` 单设备，共享 `并行:<组名>` tag）
- [x] **测试执行界面**
      - 实时通信监控拆成 **A / B 两个独立窗口**（各自设备选择、WebSocket 订阅、暂停/清空，默认不重复选同一设备）
      - 执行步骤按**执行设备**分列显示（列数取决于并行流程用到的设备数，不限 2 列），每列带头部的通过/失败统计
      - 节点编辑弹窗新增「执行设备」选择（绑定到指定设备，留空自动选择）
- [x] 验证：`tsc --noEmit` 与 `npm run build` 通过；延时节点生成代码实测总时长 502 ms（300+200）；
      通过 API 真实执行（start→初始化 `wait_ms=300`→延时 `{wait_ms}`→延时 200→end）→ 3 步 passed、耗时 1.1s

### v0.7.1 — PeakCAN 连接鲁棒性加固（2026-10-05，分支 `feature/flow-enhancements`）

> 针对 Issue #6 的残余问题：Windows 上仍报 `[WinError 10047] 使用了与请求的协议不兼容的地址`，
> 且错误信息里看不到任何可定位的原因。

- **根因**：`connect()` 只“盲试”一个组合，且只捕获 `can.exceptions.CanError`；
  当 SocketCAN 在 Windows 上创建 AF_CAN socket 时 python-can 抛出的是裸 `OSError`，
  直接穿透到 `device_service` → 前端只看到 `[WinError 10047]`。同时 `auto` 检测一旦
  选错接口（例如 `can0` 存在但未 UP）就没有任何回退。
- **修复**（`backend/plugins/peakcan_plugin.py` 1.1.0）：
  - 改为**按序尝试候选列表**：显式 channel（按名字猜驱动）→ 已 UP 的 SocketCAN 接口 →
     其它 SocketCAN 接口 → 检测到的 PCAN 通道 → 平台默认；Windows 上 SocketCAN 永不入选
  - 捕获 `Exception`（不再只捕 `CanError`），**每个候选的失败原因逐条汇总**后抛出
    `ConnectionError`，附平台修复提示 → 裸 `OSError` 不再可能到达 UI
  - 新增 `_explain()`：把 `10047` / `Network is down` / 缺 PCAN DLL 等翻译成可操作的中文原因
  - 新增 `{"action": "diagnose"}` 与 `{"action": "scan"}`（**断开状态可用**），
    返回平台、python-can 版本、候选顺序、检测到的通道与上次失败原因
  - 前端「连接失败」提示因此直接显示“尝试了哪些组合 + 各自为什么失败”
  - 修复手册/Skill 里 `{"action": ...}` JSON 字符串命令在 UI 下发时被当成 `id#data` 解析
    而报 `Invalid CAN string format` 的问题（现自动识别 JSON 对象命令）
- 验证：插件文件语法/结构检查通过；候选顺序逻辑覆盖 Linux/Windows 两条分支
  （受限于无 Windows + 无 PCAN 硬件，实际硬件连接需在设备机上按 `diagnose` 输出确认）

### v0.7.0 — 节点输入/输出 + Skill 编辑器 + 插件编辑器（2026-10-05，分支 `feature/flow-enhancements`）

- [x] **Issue #4：所有节点支持输入参数与输出返回值**
      - 新增 `app/services/flow_context.py`：`{占位符}` 渲染、类型强转、安全表达式求值、
        上下文播种（初始化节点变量）、输入解析（优先取前序同名输出，回退默认值）、输出收集
      - **代码生成器**：注入 `_r / _cast / _p / _out / _cond` 运行时助手；命令与预期结果支持占位符；
        条件/while/进入/跳出条件改用 `_cond()` 以流程上下文为变量求值
      - **运行时执行引擎**：每一步先解析输入、渲染命令/预期，再按 `response / parsed_N / 解析字段名`
        收集输出写入上下文；`step_completed` 广播附带 `context`
      - **前端**：节点编辑弹窗新增「输入参数 / 输出返回值」Form.List（名称/类型/默认值或表达式/说明）
        与「可用变量」标签（点击复制 `{变量名}`）；画布节点显示 in/out 徽标
- [x] **Skill 编辑器**（`/skill-editor`）：列表 → 编辑 → 保存；`.md` 导入；改名即重命名文件
- [x] **插件编辑器**（`/plugin-editor`）：4 套插件模板 + 占位符填充 + 源码编辑 + 语法/插件类校验
- [x] 验证：4 套模板渲染后可编译；Skill 增改删 + 导入实测通过；`tsc --noEmit` 与 `npm run build` 通过

---

## ✅ 已完成 (Done)

### 基础设施 (M0)
- [x] 后端 FastAPI 框架、配置、数据库（SQLite WAL）、ORM 模型（11 表）
- [x] 前端 Vite + React + TS + Ant Design 脚手架、路由、布局、状态管理
- [x] 通信协议层：SCPI / CAN / 串口 / 以太网
- [x] 设备管理服务与 CRUD API、前端设备管理页
- [x] AI 服务抽象层（Provider 工厂）、对话、用例生成、NL 查询
- [x] 测试用例系统（CRUD + ReactFlow 流程图）
- [x] 测试执行引擎（顺序/并行/条件/循环、变量、钩子、WebSocket 监控）
- [x] 通信日志系统（SQLite + CSV 双写、查询、导出）
- [x] 测试报告系统（Jinja2 / docx、模板管理）
- [x] 插件系统（SDK、管理器、API、前端页、Modbus 示例）

### 调试终端 (2026-07-09 ~ 07-10)
- [x] WebSocket 终端端点 `/ws/terminal/{device_id}` 与前端多窗口终端
- [x] Python 3.8 兼容（`asyncio.to_thread` → `run_in_executor`）
- [x] 串口发送阻塞修复（`read_until` + fallback `read`）

### 日志与诊断 (2026-07-11)
- [x] 通信文件日志 `com_logger.py`（旋转、线程安全）
- [x] 前端时间戳毫秒级显示
- [x] 设备连接诊断（串口权限、Mock 设备）

### 自定义协议插件 + AI 模型配置前端 (2026-07-20 上午)
- [x] `BaseProtocolPlugin` 基类补齐（原被引用但未定义）
- [x] Mini Gateway 100 协议插件（22 条命令，板卡 ID 默认 11，波特率默认 115200）
- [x] `device_service` 路由非标准协议到插件实例
- [x] `POST /api/plugins/{id}/add-device` 按模板一键创建设备
- [x] 前端插件管理：已发现插件一键安装、添加设备
- [x] 前端「模型配置」页（CRUD / 测试 / 设为默认）

### AI 模型增强 + 对话修复 (2026-07-20)
- [x] 新增供应商：**DeepSeek**、**MiniMax**（均 OpenAI 兼容，已加入后端 `ProviderFactory` 与前端 `PROVIDERS`）
- [x] 前端「模型配置」新增**对话测试窗口**（Drawer，可直接与该模型对话验证）
- [x] **修复 AI 助手发送无响应**
- [x] 前端 `tsc --noEmit` 通过

### 修复插件「Plugin class not found」+ 插件 Skill 体系 (2026-07-25)
- [x] 修复 `_load_plugin_module` 返回值语义错误
- [x] 插件类 4 级解析回退 + 文件路径 4 级解析回退
- [x] 插件手册与 Skill 体系（manuals/ + skills/）
- [x] AI 助手集成插件 Skill（前端多选器 + 后端关键词自动检测注入）
- [x] 真实硬件端到端验证

### 修复 AI 模型「连接失败」+ 重置/Key 问题 (2026-07-25 ~ 07-27)
- [x] `ProviderFactory` 新增 `DEFAULT_BASE_URLS`；JoeAI 指向 DeepSeek
- [x] `AIModelConfigUpdate` 增加 `provider`、`model_name` 字段
- [x] `test_model` 返回真实错误；`custom` 缺 Base URL 后端拒绝
- [x] `PROVIDERS.deepseek` 提示更新为 `deepseek-v4-pro / deepseek-v4-flash`
- [x] **修复重置软件进程未完全关闭**：`restart_helper.py` 按端口 + 进程树 kill（解决 reload 模式 worker 残留）
- [x] **修复 API Key 显示为空**：前端编辑时以掩码显示已保存 Key，提交时保留原 Key 不变
- [x] **修复模型测试 400**：动态 placeholder 按供应商提示有效模型名，切换供应商清空旧名

### 测试用例流程图增强 (2026-07-27)
- [x] **AI 驱动流程图生成**：AI 从自然语言需求生成含判断/循环/分支的完整流程图节点
- [x] **流程图编辑器重写**：自定义 ReactFlow 节点（Start/Action/Condition/Loop/End），左侧节点面板拖拽添加
- [x] **判断节点**：菱形渲染，支持条件表达式编辑、true/false 分支
- [x] **循环节点**：for/while 循环，条件表达式编辑
- [x] **可执行代码输出**：`POST /api/testcases/{id}/generate-code` 从流程图生成 Python 测试脚本
- [x] **代码生成器**：遍历流程图拓扑结构，生成完整的 if/else/for/while 和执行步骤的 Python 代码

### 流程图编辑器增强 + 代码生成修复 (2026-08-01)
- [x] **BugFix: 连线选中后无法删除**：边删除过滤条件写反（`e.selected` → `!e.selected`），且添加了 Delete 键直接触发
- [x] **撤销/重做功能**：历史栈（50 步上限），Ctrl+Z 撤销 / Ctrl+Y 重做，工具栏按钮，操作前自动保存快照
- [x] **代码生成器修复**：修复函数体缩进错误（indent=2 → indent=1）、修复 f-string 引号嵌套导致语法错误、修复条件分支汇聚点被错误嵌套在 if 分支内部
- [x] **代码生成测试**：5 类流程图全覆盖测试（顺序/while 循环/中文标签/YesNo/无标签）、API 端到端验证通过、生成代码编译合法

### AI Token 预算与 JSON 输出优化 (2026-08-05)
- [x] **System Prompt 优化**：测试用例生成 prompt 从 ~2500 字符压缩到 ~800 字符，节省约 700 tokens
- [x] **前端默认 max_tokens 提升**：新建模型默认值 2048 → 16384，placeholder 同步更新
- [x] **Chat min_tokens 提升**：对话场景 token 下限 4096 → 16384
- [x] **reasoning_content 提取**：`OpenAIProvider.chat()` 返回结果增加 `reasoning_content` 字段，增强可观测性

### AI 测试用例生成超时修复 + 鲁棒性增强 (2026-08-05)
- [x] **根因定位**：前端 axios 默认超时 30s，DeepSeek V4 推理模型生成用例耗时 60-120s（reasoning_tokens 占比 70%+），前端提前 timeout
- [x] **前端超时优化**：AI 类 API（chat/generate/query/test）切换为 300s 长超时实例；基础 API 超时 120s
- [x] **后端 httpx 超时**：OpenAIProvider SDK 调用超时 120s → `httpx.Timeout(300s, connect=30s)`
- [x] **超时友好提示**：`apiHelper.ts` 检测 ECONNABORTED/ETIMEDOUT，提示"推理模型可能需要 1-3 分钟"
- [x] **日志增强**：`generate_test_cases` 增加耗时 + token 统计日志（含 reasoning_tokens 单独计数）
- [x] **验证**：用户需求"mini-Gateway100 读 DIG1 → CAN1 发送 0x850102 → 超时提示"生成 7 个测试用例验证通过

### 结果解析 + 代码生成修复 + 趋势曲线 (2026-09-26)
- [x] **代码生成修复**：未连线节点被丢弃、无标签分支全判为 true、下发整句自然语言 —— 三处均已修复
- [x] **结果解析能力**：hex/bin/bool/dec/string + 起始位/长度/单位(bit/byte) + 最小值/最大值/等于(或运算)
- [x] **解析配置界面**：用例展开即见步骤，步骤旁配置按钮，粘贴真实响应即时预览解析值与 PASS/FAIL
- [x] **执行页**：显示流程全部步骤（执行前即可见）+ 每步判定结果
- [x] **解析数据曲线**：执行时勾选实时显示；历史趋势从已落库 `parsed_results` 读回，不单独建表；支持大屏模式
- [x] **名称唯一校验**：解析项名称全用例唯一，前后端双重校验，重复提示重新命名
- [x] **语义澄清**：超出上下限 = 判定 FAIL（测试结果），不是系统/设备告警

### 解析正确性修复 (2026-09-26)
- [x] **每条应答都解析**：原先只解析步骤内最后一条响应，重复下发 50 次的步骤只出 1 个点；
      现 `parsed_results` 改为 `{count, samples[], last}`，每条应答一个采样点
- [x] **空帧识别**：`CAN1,RPLY1,0X`（无数据/超时）不再被当成 ASCII 文本切分
      （此前把 `,`=`0x2C`、`X`=`0x58` 当成了解析值），改为显示 **unknown**、跳过判定
- [x] 解析结果新增 `status`：ok / fail / unknown / error，UI 分别显示 PASS / FAIL / UNKNOWN / ERROR
- [x] **HEX 字段选择**：报文含多个 `0x` 字段时（`1,STD,0X11,0X0102030000000000`）可指定用哪一个，
      避免"全部拼接"导致偏移整体错位
- [x] 解析配置预览显示实际参与切分的字节；代码生成器与运行时判定保持一致

### SCPI 协议 Skill + RIGOL 示波器插件 (2026-09-26)
- [x] **SCPI 通用协议**：下载 SCPI-1999 官方规范（IVI Foundation，卷一 Syntax & Style）到 `docs/scpi/`
- [x] 新增 `scpi` Skill（`backend/plugins/skills/scpi_skill.md`）+ 手册（`backend/plugins/manuals/scpi.md`）：
      命令树/语法规则、参数类型（Bool/Discrete/NR1/NR2/NR3）、单位后缀、
      IEEE488.2 通用命令、状态报告模型、IEEE 明确长度块解析
- [x] **RIGOL 示波器插件** `rigol_oscilloscope`：SCPI over LAN(5555) / USB-TMC / VISA，
      含波形读取（PREamble + DATA + 电压换算）、屏幕截图、测量动作
- [x] 下载 RIGOL 官方编程手册（DS1000Z-E、MSO5000）到 `docs/rigol/`，
      整理为可机读手册 `backend/plugins/manuals/rigol_oscilloscope.md`
- [x] 插件已在后端安装并启用（`plg_9410ada9`），`/api/plugins/discovered` 可见
- [x] 排错修正：查询前清空接收缓冲（避免读到上一次应答）；
      `:MEASure:ITEM? VPP,CHAN1` 这类 `?` 在参数前的命令也能正确识别为查询
- 注：RIGOL 中国区支持站（supportcn.rigol.com）在当前网络不可达，
      手册改由 rigol.com 国际站公开直链下载，**未使用账号登录**

### 自定义仪表盘 (2026-09-26)
- [x] 新表 `dashboards`（layout / widgets / data_source 只存**描述**，不存数值）+ CRUD / 复制 / 设为默认 / 导入导出
      首次访问自动内置两个模板：**长稳视图**（解析卡片+趋势+判定汇总+统计）、**调试视图**（设备+统计+通信日志）
- [x] `GET /api/dashboards/snapshot`：一次请求拉齐所有 Widget（设备 + 执行统计 + 解析序列 + 判定汇总），
      N 个 Widget 只轮询一次而不是 N 次
- [x] 解析趋势逻辑抽到 `app/services/trend_service.py`，`/api/testcases/{id}/parsed-trend` 与仪表盘共用；
      点数据新增 `step_label` 便于定位来源步骤
- [x] **7 种 Widget**：
      - **解析数值卡片**：最新值大字号 + PASS/FAIL/空帧判定徽标，越界变红，附 min/max/均值/采样数/FAIL 次数
      - **趋势曲线**：按 (执行, 步骤, 第几次应答) 对齐铺点，FAIL 点标红，可加参考上下限参考线
      - **判定结果汇总**：判定总数/PASS/FAIL/空帧 + 通过率进度条 + 分字段表格 + 最近 FAIL 明细（含原因与步骤）
      - 设备状态 / 执行统计 / 通信日志 / 文本备注（Markdown）
- [x] 交互：编辑/锁定（锁定后不可拖动）、组件库抽屉、每个 Widget 独立配置、删除/复制、
      多仪表盘切换、新建/复制/设为默认/导入/导出 JSON、大屏模式（深色投屏 + 自动刷新）
- [x] 删除默认仪表盘后自动把最早的一个补为默认，保证始终有落地页
- [x] 验证：`tsc --noEmit`、`npm run build` 通过；`/dashboards/snapshot` 实测返回 813 个判定点
      （ok 49 / fail 13 / unknown 751）；Chromium 无头截屏 4 张确认渲染与交互正常

### 仪表盘大屏模式 (2026-09-26)
- [x] 仪表盘新增「大屏模式」入口：全视口深色投屏布局、超大字号统计卡（设备/用例/执行/通过率）
- [x] 实时时钟 + 自动刷新（5/10/30/60 秒可选）+ 立即刷新
- [x] 调用浏览器全屏 API（被拒绝时仍以全视口覆盖层渲染）；ESC 退出自动同步状态
- [x] **无权限控制**，任意用户均可进入投屏

---

### 仪表盘实时刷新 + 配置弹窗修复 + 端到端集成测试 + CI/CD (2026-09-27)
- [x] **自定义仪表盘实时刷新**：Widget 订阅运行中执行的 WebSocket（`/ws/executions/{id}`），`step_completed` / `execution_completed` / `step_failed` / `execution_stopped` / `execution_error` 事件驱动防抖刷新快照；保留 HTTP 轮询作为兜底心跳
- [x] **齿轮配置弹窗修复**：操作按钮（设置/复制/删除）移出拖拽手柄并加 `draggableCancel`，修复点击无响应；标题栏作为唯一拖拽手柄
- [x] **端到端集成测试**：新增 `Test/e2e_integration_test.py`，打通「设备(Mini Gateway 100) → AI 生成用例 → 执行 → 报告」全链路；实测生成 6 个用例、执行 `status=passed`、报告 HTML 可下载
- [x] **CI/CD 流水线**：新增 `.github/workflows/ci.yml`（后端导入/编译校验 + 前端 `npm ci` + `npm run build` + 构建产物上传）、`.github/workflows/e2e.yml`（手动触发，需自托管 Runner + 设备 + AI Key）
- [x] 全部改动已提交并推送至 GitHub `master`

### 稳定性 / 安全 / 体验优化 (2026-09-27)
- [x] **调试终端多窗口增强（后台轮询稳定性）**：监控循环加宽异常兜底（单条异常不再导致监控进程永久退出）；支持自定义轮询间隔；引入多窗口监听引用计数，单个窗口 `stop_receive` 不再误杀全设备共享监控
- [x] **通信日志导出性能**：CSV 导出改为分批游标拉取，避免大数据量一次性全量加载
- [x] **API Key 加密存储**：新增 `app/core/crypto.py`（Fernet），建/改模型时加密、调用时解密，并对存量明文兼容回退；`ai_service` 的 `TODO: encrypt` 已消除
- [x] **判定结果汇总表格时间戳**：FAIL 列表新增可见时间戳（原仅在 tooltip 显示）

## 🗺️ 近期计划 (Roadmap)

| 优先级 | 计划项 | 说明 |
|--------|--------|------|
| P1 | **插件编辑器增强** | 模板自定义（用户保存自己的模板）、插件一键安装/重载、手册（manuals）编辑 |
| P1 | 节点 I/O 可视化 | 画布上连线标注传递的变量、未定义变量实时提示 |
| P1 | **自定义仪表盘增强** | 大屏自动轮播、响应式断点、Widget 内实时 WS 订阅 |
| P0 | 端到端集成测试（已完成） | 打通"需求 → AI 用例 → 执行 → 报告"主链路 |
| P0 | API Key 加密（已完成） | 生产环境必须，避免明文存储 |
| P1 | 更多仪器驱动 | 真实型号 SCPI 指令集适配 |
| P1 | 插件进程隔离 | 提升稳定性与安全性 |
| P2 | 国际化 | 中英界面 |
| P2 | 打包分发 | 安装程序 / 容器镜像 |
| P3 | CI/CD（已完成） | 自动化测试与发布 |

---

## 📊 进度统计（估算）

- 核心模块完成度：~90%（9 大模块均已落地；端到端集成测试与 CI/CD 已补齐）
- 后端 API 端点：~45 个
- 数据库表：11 张
- 已接入 AI 供应商：OpenAI / Anthropic / Ollama / LocalAI / vLLM / 混元 / 通义 / 文心 / **DeepSeek** / **MiniMax** / 自定义
- 自定义协议插件：Modbus RTU（示例）、Mini Gateway 100
