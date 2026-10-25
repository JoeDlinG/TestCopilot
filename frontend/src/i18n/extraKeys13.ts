/**
 * Help centre / onboarding tour / updater / feedback strings.
 *
 * Keyed by the Chinese source text, like the other EXTRA batches, so the same
 * literal can be looked up from `t()` without a second indirection table.
 */
export const HELP_KEYS: Record<string, [string, string]> = {
  // ---- 帮助菜单 ----
  帮助: ['help.menu', 'Help'],
  '帮助中心': ['help.center', 'Help centre'],
  使用文档: ['help.docs', 'Documentation'],
  快速入门: ['help.quickStart', 'Quick start'],
  重新观看导航: ['help.tourAgain', 'Replay the tour'],
  '快捷键': ['help.shortcuts', 'Keyboard shortcuts'],
  关于: ['help.about', 'About'],
  '关于 TestCopilot': ['help.aboutApp', 'About TestCopilot'],
  问题反馈: ['help.feedback', 'Send feedback'],
  检查更新: ['help.checkUpdate', 'Check for updates'],
  使用手册: ['help.manual', 'User manual'],
  '选择左侧文档开始阅读': ['help.pickDoc', 'Pick a document on the left'],
  '帮助文档不可用：未找到 docs 目录': ['help.offline', 'Manuals unavailable: docs folder not found'],
  帮助文档加载失败: ['help.loadFailed', 'Failed to load the manual'],
  更新于: ['help.updatedAt', 'Updated'],
  字号: ['help.fontSize', 'Text size'],

  // ---- 快捷键 ----
  '全局快捷键': ['help.sc.global', 'Global'],
  '流程编辑器': ['help.sc.editor', 'Flow editor'],
  '打开命令面板': ['help.sc.palette', 'Open the command palette'],
  '关闭弹窗 / 面板': ['help.sc.esc', 'Close a dialog or panel'],
  '展开 / 收起输出抽屉': ['help.sc.dock', 'Expand or collapse the output dock'],
  '撤销': ['help.sc.undo', 'Undo'],
  '重做': ['help.sc.redo', 'Redo'],
  '复制选中节点': ['help.sc.copy', 'Copy the selected node'],
  '粘贴节点': ['help.sc.paste', 'Paste nodes'],
  '删除选中': ['help.sc.delete', 'Delete the selection'],
  '全屏 / 退出全屏': ['help.sc.fullscreen', 'Toggle full screen'],
  '保存流程图': ['help.sc.save', 'Save the flow'],

  // ---- 关于 ----
  '版本': ['help.version', 'Version'],
  后端版本: ['help.backendVersion', 'Backend'],
  前端构建: ['help.frontendBuild', 'Frontend build'],
  '运行平台': ['help.platform', 'Platform'],
  '开源地址': ['help.repo', 'Source'],
  '问题跟踪': ['help.issues', 'Issues'],
  '本软件用于硬件自动化测试：接入设备、编写用例、执行并产出报告。':
    ['help.aboutBody', 'A hardware test automation workbench: connect instruments, author cases, run them and produce reports.'],

  // ---- 首次运行引导 ----
  '欢迎使用 TestCopilot': ['tour.welcome', 'Welcome to TestCopilot'],
  '用三步认识界面：左侧配置、顶栏观察、右侧输出。':
    ['tour.welcomeBody', 'Three zones: configuration on the left, observation on top, output on the right.'],
  跳过: ['tour.skip', 'Skip'],
  上一步: ['tour.prev', 'Back'],
  下一步: ['tour.next', 'Next'],
  开始使用: ['tour.done', 'Get started'],
  '第 {n} / {total} 步': ['tour.progress', 'Step {n} of {total}'],
  '示例工程': ['tour.demo', 'Demo project'],
  '当前版本': ['update.current', 'Current version'],
  '第一步先接入仪器：串口、CAN、SCPI 都在这里管理。连上之后，设备状态会显示在顶栏。':
    ['tour.step.config', 'Start by connecting hardware here — serial, CAN and SCPI. Once connected, the device count appears in the top bar.'],
  '「测试用例」用流程图编写步骤；「AI 助手」可以把自然语言变成用例；「执行管理器」编排批量执行；「调试终端」直接收发命令。':
    ['tour.step.design', 'Test cases are authored as flow charts; the AI assistant turns plain language into cases; the execution manager orchestrates batches; the debug terminal talks to hardware directly.'],
  '「插件中心」导入协议驱动，「模型配置」填入大模型密钥，「项目工程」把整套配置打包带走。':
    ['tour.step.system', 'The plugin centre imports protocol drivers, model config holds your LLM keys, and project files package the whole setup.'],
  '看板进入监控视图，工具里是通信日志与报告。':
    ['tour.step.top', 'Dashboards open the monitoring view; Tools holds the communication log and reports.'],
  '全局搜索（⌘K）': ['tour.step.searchTitle', 'Global search (⌘K)'],
  '任何页面按 ⌘K / Ctrl+K，输入设备名、用例名或页面名就能直接跳过去。':
    ['tour.step.search', 'Press ⌘K / Ctrl+K anywhere and type a device, case or page name to jump straight there.'],
  '帮助菜单里放着使用手册、快捷键、检查更新和问题反馈。':
    ['tour.step.help', 'The Help menu holds the manual, keyboard shortcuts, update checks and feedback.'],
  '输出 / 交付': ['tour.step.dockTitle', 'Output & delivery'],
  '测试执行进度和报告都收在右侧抽屉：单击展开，双击全屏。':
    ['tour.step.dock', 'Run progress and reports live in the right-hand dock — click to expand, double-click for full screen.'],

  // ---- 远程更新 ----
  '正在检查更新…': ['update.checking', 'Checking for updates…'],
  '已是最新版本': ['update.upToDate', 'You are up to date'],
  '发现新版本': ['update.available', 'Update available'],
  '立即更新': ['update.now', 'Update now'],
  '稍后': ['update.later', 'Later'],
  '不再提示此版本': ['update.ignore', 'Skip this version'],
  '正在下载…': ['update.downloading', 'Downloading…'],
  '正在校验…': ['update.verifying', 'Verifying…'],
  '正在安装，程序即将重启…': ['update.applying', 'Installing — the app will restart'],
  '检查更新失败': ['update.checkFailed', 'Could not check for updates'],
  '下载失败': ['update.downloadFailed', 'Download failed'],
  '校验失败：文件可能已损坏，已丢弃': ['update.checksumFailed', 'Checksum mismatch — the download was discarded'],
  '安装失败': ['update.applyFailed', 'Install failed'],
  '最新版本': ['update.latest', 'Latest'],
  '更新内容': ['update.notes', 'What’s new'],
  '自动检查更新': ['update.autoCheck', 'Check for updates automatically'],
  '自动下载（仍需你确认安装）': ['update.autoDownload', 'Download automatically (install still needs your go-ahead)'],
  '已忽略版本': ['update.ignored', 'Skipped version'],
  '没有可用的更新源': ['update.noFeed', 'No update feed configured'],
  '更新源': ['update.feed', 'Feed'],
  '该安装包不适合当前平台': ['update.wrongPlatform', 'The package does not match this platform'],

  // ---- 问题反馈 ----
  '反馈中心': ['fb.title', 'Feedback'],
  '反馈类型': ['fb.kind', 'Type'],
  想法: ['fb.idea', 'Idea'],
  问题: ['fb.problem', 'Problem'],
  其他: ['fb.other', 'Other'],
  '标题': ['fb.subject', 'Subject'],
  '详细描述': ['fb.body', 'Details'],
  '请描述你遇到的问题或想要的功能': ['fb.bodyPh', 'Describe the problem or the feature you want'],
  '允许通过邮箱联系我（可选）': ['fb.contact', 'You may contact me by email (optional)'],
  '附带最近的运行日志': ['fb.attachLogs', 'Attach the recent runtime log'],
  '附带系统信息（版本 / 平台）': ['fb.attachSys', 'Attach system info (version / platform)'],
  提交: ['fb.submit', 'Submit'],
  '提交成功，感谢反馈': ['fb.ok', 'Thanks — your feedback was submitted'],
  '提交失败，已保存到本地，联网后会补发': ['fb.queued', 'Submit failed — saved locally and will be retried'],
  '请填写标题与描述': ['fb.needFields', 'Please fill in a subject and a description'],
  '崩溃自动上报': ['fb.autoReport', 'Report crashes automatically'],
  '崩溃自动上报已关闭，手动反馈仍可用': ['fb.autoOff', 'Automatic crash reporting is off; manual feedback still works'],
  '上次异常退出': ['fb.lastCrash', 'Last session ended unexpectedly'],
  '是否发送这次崩溃报告？': ['fb.lastCrashAsk', 'Send the crash report from that session?'],
  发送: ['fb.send', 'Send'],
  不发送: ['fb.dontSend', "Don't send"],
  '反馈记录': ['fb.history', 'Submitted reports'],
  '尚未配置 GitHub Token，反馈已保存在本地': ['fb.noToken', 'No GitHub token configured — the report was stored locally'],
  '重复崩溃已合并计数': ['fb.deduped', 'Same crash as before — occurrence counted'],
  '页面渲染出错': ['fb.renderFailed', 'This page crashed while rendering.'],
  重试: ['common.retry', 'Retry'],
  '尚未配置 AI 模型': ['ai.noModelTitle', 'No AI model configured yet'],
  'AI 助手需要一个模型才能工作。请到「模型配置」添加一个模型（填入厂商、API Key 等），然后回到本页即可使用。':
    ['ai.noModelDesc', 'The AI assistant needs a model before it can do anything. Add one under Model Configuration (vendor, API key, …) and come back to this page.'],
  '重新检测': ['btn.recheck', 'Re-check'],
}
