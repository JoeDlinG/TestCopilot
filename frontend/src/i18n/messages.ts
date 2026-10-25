/**
 * UI message catalogues.
 *
 * ``zh-CN`` is the source of truth (it is what the UI was originally written
 * in). ``en-US`` is filled in incrementally: :func:`t` falls back to Chinese
 * for any key that has no English entry yet, so a partially translated screen
 * still renders sensibly instead of showing raw keys.
 */
import type { Locale } from './index'
import { EXTRA, EXTRA2, EXTRA3 } from './extraKeys'
import { EXTRA4 } from './extraKeys4'
import { EXTRA5 } from './extraKeys5'
import { EXTRA6 } from './extraKeys6'
import { EXTRA7 } from './extraKeys7'
import { EXTRA8 } from './extraKeys8'
import { EXTRA9 } from './extraKeys9'
import { EXTRA10 } from './extraKeys10'
import { EXTRA11 } from './extraKeys11'
import { EXTRA12 } from './extraKeys12'
import { HELP_KEYS } from './extraKeys13'

export const messages: Record<Locale, Record<string, string>> = {
  'zh-CN': {
    // ---- navigation ----
    'nav.dashboard': '仪表盘',
    'nav.customDashboard': '自定义仪表盘',
    'nav.devices': '设备管理',
    'nav.debugTerminal': '调试终端',
    'nav.ai': 'AI 助手',
    'nav.testcases': '测试用例',
    'nav.executions': '测试执行',
    'nav.plans': '执行管理器',
    'nav.logs': '通信日志',
    'nav.reports': '测试报告',
    'nav.plugins': '插件管理',
    'nav.pluginEditor': '插件编辑器',
    'nav.skillEditor': 'Skill 编辑器',
    'nav.modelConfig': '模型配置',
    'nav.projects': '项目工程',
    'nav.pluginCenter': '插件中心',

    // ---- navigation groups (issue #20: 3 groups) ----
    'nav.group.config': '配置与接入',
    'nav.group.design': '设计与编写',
    'nav.group.system': '系统',

    // ---- top bar ----
    'top.dashboards': '看板',
    'top.tools': '工具',

    // ---- global status bar ----
    'status.backend': '后端在线',
    'status.devices': '已连接设备',
    'status.running': '运行中',

    // ---- output dock ----
    'dock.title': '输出 / 交付',
    'dock.executions': '测试执行',
    'dock.reports': '输出报告',

    // ---- common actions ----
    'common.refresh': '刷新',
    'common.add': '添加',
    'common.delete': '删除',
    'common.save': '保存',
    'common.cancel': '取消',
    'common.confirm': '确定',
    'common.search': '扫描设备',
    'common.export': '导出',
    'common.import': '导入',
    'common.edit': '编辑',
    'common.run': '运行',
    'common.stop': '停止',
    'common.connect': '连接',
    'common.disconnect': '断开',
    'common.rename': '重命名',
    'common.download': '下载',
    'common.overwrite': '覆盖',
    'common.close': '关闭',

    // ---- common nouns ----
    'common.name': '名称',
    'common.status': '状态',
    'common.actions': '操作',
    'common.type': '类型',
    'common.description': '描述',
    'common.address': '连接地址',
    'common.connected': '已连接',
    'common.disconnected': '未连接',
    'common.language': '语言',

    // ---- app chrome ----
    'app.restart': '重启软件',
    'app.restarting': '正在重启软件，刷新界面…',
    'app.restartFailed': '重启失败，请手动重启服务',

    // ---- devices ----
    'device.title': '设备管理',
    'device.add': '添加设备',
    'device.configureInterface': '配置设备接口（串口 / USB / 以太网 / PCIe / PXI …）',
    'device.interfaceType': '接口类型',
    'device.confirmDelete': '确定删除此设备？',
    'device.sendCommand': '发送命令',
    'device.quickAdd': '快速添加',
    'device.deviceType': '设备类型',
    'device.portAddress': '端口/地址',

    // ---- interfaces ----
    // Labels originate from the backend registry (Chinese); a key present here
    // wins, otherwise the backend label is shown verbatim.
    'iface.configTitle': '配置设备接口',
    'iface.type': '接口类型',
    'iface.switchHint': '切换到「{label}」会清空其它接口对应的地址字段，并替换相关参数',
    'iface.t.serial': '串口 (RS-232 / RS-485)',
    'iface.t.usb': 'USB',
    'iface.t.ethernet': '以太网',
    'iface.t.pcie': 'PCIe',
    'iface.t.pxi': 'PXI / PXIe',
    'iface.t.can': 'CAN',
    'iface.t.gpib': 'GPIB',
    'iface.f.serial_port': '串口号',
    'iface.f.baudrate': '波特率',
    'iface.f.data_bits': '数据位',
    'iface.f.parity': '校验位',
    'iface.f.stop_bits': '停止位',
    'iface.f.flow_control': '流控',
    'iface.f.timeout': '读取超时 (秒)',
    'iface.f.vid': 'VID (厂商 ID)',
    'iface.f.pid': 'PID (产品 ID)',
    'iface.f.serial_number': '序列号 (可选)',
    'iface.f.ip_address': 'IP 地址',
    'iface.f.port': '端口号',
    'iface.f.protocol': '传输协议',
    'iface.f.connect_timeout': '连接超时 (秒)',
    'iface.f.simulate': '模拟模式',
    'iface.f.bdf': 'BDF 地址',
    'iface.f.device_index': '设备序号 (可选)',
    'iface.f.resource': '资源描述符 (可选)',
    'iface.f.chassis': '机箱号',
    'iface.f.slot': '槽位号',
    'iface.f.visa_address': 'VISA 资源串',
    'iface.f.can_channel': 'CAN 通道',
    'iface.f.bitrate': '波特率 (bps)',
    'iface.f.fd': 'CAN FD',
    'iface.f.gpib_address': 'GPIB 地址 (可选)',

    // ---- project section names (issue #27: these used to be hard-coded in
    // PROJECT_SECTIONS, so the catalogue could never translate them) ----
    'section.models': '模型配置',
    'section.devices': '设备配置',
    'section.plugins': '插件配置',
    'section.skills': 'Skill 配置',
    'section.testCases': '测试用例',
    'section.executionPlans': '执行管理器',
    'section.dashboards': '仪表盘配置',

    // ---- punctuation that differs by locale ----
    'punct.colon': '：',
    'punct.enum': '、',
    'punct.countParen': '（{n}）',

    // ---- device / interface type names (issue #27: were hard-coded in types/) ----
    'deviceType.powerSupply': '可编程电源',
    'deviceType.oscilloscope': '示波器',
    'deviceType.multimeter': '万用表',
    'deviceType.signalGenerator': '信号发生器',
    'deviceType.spectrumAnalyzer': '频谱分析仪',
    'deviceType.canTool': 'CAN 工具',
    'deviceType.gateway': '网关',
    'deviceType.generic': '通用设备',
    'iface.scpi': 'SCPI',
    'iface.can': 'CAN',
    'iface.usb': 'USB',
    'iface.serial': '串口',
    'iface.ethernet': '以太网',
    'iface.gpib': 'GPIB',
    'iface.pcie': 'PCIe',
    'iface.pxi': 'PXI / PXIe',
    'iface.custom': '自定义',
    'iface.miniGateway100': 'Mini Gateway 100',

    // ---- dashboard widget metadata (issue #27: was hard-coded in registry.tsx) ----
    'widget.parsed_value.label': '解析数值卡片',
    'widget.parsed_value.desc': '盯一个解析量：最新值 + PASS/FAIL 判定徽标，越界变红',
    'widget.parsed_value.title': '解析数值',
    'widget.trend_chart.label': '趋势曲线',
    'widget.trend_chart.desc': '解析值随时间变化，FAIL 点标红（长稳测试看漂移）',
    'widget.trend_chart.title': '解析值趋势',
    'widget.judge_summary.label': '判定结果汇总',
    'widget.judge_summary.desc': '各字段 PASS/FAIL 统计 + 最近 FAIL 明细（判定结果，非告警）',
    'widget.judge_summary.title': '判定结果汇总',
    'widget.device_status.label': '设备状态',
    'widget.device_status.desc': '设备在线/离线、协议、连接地址',
    'widget.device_status.title': '设备状态',
    'widget.execution_stats.label': '执行统计',
    'widget.execution_stats.desc': '总执行次数 / 通过 / 失败 / 运行中 / 通过率',
    'widget.execution_stats.title': '执行统计',
    'widget.comm_log.label': '通信日志',
    'widget.comm_log.desc': '最新收发报文记录',
    'widget.comm_log.title': '通信日志',
    'widget.note.label': '文本备注',
    'widget.note.desc': '接线说明 / 操作 SOP，支持 Markdown',
    'widget.note.title': '备注',
    'widget.status.emptyFrame': '空帧',
    'widget.status.error': '错误',
    'widget.status.connected': '已连接',
    'widget.status.disconnected': '未连接',

    // ---- projects ----
    'project.title': '项目工程文件',
    'project.new': '新建项目工程',
    'project.saveAs': '另存为工程…',
    'project.export': '导出当前配置（下载文件）',
    'project.importFile': '导入工程文件…',
    'project.merge': '合并导入',
    'project.replace': '替换导入',
    'project.saved': '已保存的工程文件',
    'project.sections': '包含的配置段：',
    'project.newTitle': '新建项目工程',
    'project.newResult': '新建项目结果',
    'project.importResult': '导入结果',
    'project.clearedTotal': '共清空 {n} 项配置',
    'project.kept': '已保留：',
  },

  'en-US': {
    // ---- navigation ----
    'nav.dashboard': 'Dashboard',
    'nav.customDashboard': 'Custom Dashboard',
    'nav.devices': 'Devices',
    'nav.debugTerminal': 'Debug Terminal',
    'nav.ai': 'AI Assistant',
    'nav.testcases': 'Test Cases',
    'nav.executions': 'Executions',
    'nav.plans': 'Execution Manager',
    'nav.logs': 'Communication Logs',
    'nav.reports': 'Reports',
    'nav.plugins': 'Plugins',
    'nav.pluginEditor': 'Plugin Editor',
    'nav.skillEditor': 'Skill Editor',
    'nav.modelConfig': 'Model Config',
    'nav.projects': 'Project Files',
    'nav.pluginCenter': 'Plugins',

    // ---- navigation groups (issue #20: 3 groups) ----
    'nav.group.config': 'Configure',
    'nav.group.design': 'Design',
    'nav.group.system': 'System',

    // ---- top bar ----
    'top.dashboards': 'Dashboards',
    'top.tools': 'Tools',

    // ---- global status bar ----
    'status.backend': 'Backend online',
    'status.devices': 'Devices',
    'status.running': 'Running',

    // ---- output dock ----
    'dock.title': 'Output',
    'dock.executions': 'Executions',
    'dock.reports': 'Reports',

    // ---- common actions ----
    'common.refresh': 'Refresh',
    'common.add': 'Add',
    'common.delete': 'Delete',
    'common.save': 'Save',
    'common.cancel': 'Cancel',
    'common.confirm': 'OK',
    'common.search': 'Scan Devices',
    'common.export': 'Export',
    'common.import': 'Import',
    'common.edit': 'Edit',
    'common.run': 'Run',
    'common.stop': 'Stop',
    'common.connect': 'Connect',
    'common.disconnect': 'Disconnect',
    'common.rename': 'Rename',
    'common.download': 'Download',
    'common.overwrite': 'Overwrite',
    'common.close': 'Close',

    // ---- common nouns ----
    'common.name': 'Name',
    'common.status': 'Status',
    'common.actions': 'Actions',
    'common.type': 'Type',
    'common.description': 'Description',
    'common.address': 'Address',
    'common.connected': 'Connected',
    'common.disconnected': 'Disconnected',
    'common.language': 'Language',

    // ---- app chrome ----
    'app.restart': 'Restart',
    'app.restarting': 'Restarting, refreshing the page…',
    'app.restartFailed': 'Restart failed — please restart the service manually',

    // ---- devices ----
    'device.title': 'Devices',
    'device.add': 'Add Device',
    'device.configureInterface': 'Configure interface (Serial / USB / Ethernet / PCIe / PXI …)',
    'device.interfaceType': 'Interface',
    'device.confirmDelete': 'Delete this device?',
    'device.sendCommand': 'Send command',
    'device.quickAdd': 'Quick add',
    'device.deviceType': 'Device type',
    'device.portAddress': 'Port / Address',

    // ---- interfaces ----
    'iface.configTitle': 'Configure interface',
    'iface.type': 'Interface type',
    'iface.switchHint': 'Switching to "{label}" clears the address fields of other interfaces and replaces their parameters',
    'iface.t.serial': 'Serial (RS-232 / RS-485)',
    'iface.t.usb': 'USB',
    'iface.t.ethernet': 'Ethernet',
    'iface.t.pcie': 'PCIe',
    'iface.t.pxi': 'PXI / PXIe',
    'iface.t.can': 'CAN',
    'iface.t.gpib': 'GPIB',
    'iface.f.serial_port': 'Serial port',
    'iface.f.baudrate': 'Baud rate',
    'iface.f.data_bits': 'Data bits',
    'iface.f.parity': 'Parity',
    'iface.f.stop_bits': 'Stop bits',
    'iface.f.flow_control': 'Flow control',
    'iface.f.timeout': 'Read timeout (s)',
    'iface.f.vid': 'VID (vendor ID)',
    'iface.f.pid': 'PID (product ID)',
    'iface.f.serial_number': 'Serial number (optional)',
    'iface.f.ip_address': 'IP address',
    'iface.f.port': 'Port',
    'iface.f.protocol': 'Transport protocol',
    'iface.f.connect_timeout': 'Connect timeout (s)',
    'iface.f.simulate': 'Simulation mode',
    'iface.f.bdf': 'BDF address',
    'iface.f.device_index': 'Device index (optional)',
    'iface.f.resource': 'Resource descriptor (optional)',
    'iface.f.chassis': 'Chassis',
    'iface.f.slot': 'Slot',
    'iface.f.visa_address': 'VISA resource',
    'iface.f.can_channel': 'CAN channel',
    'iface.f.bitrate': 'Bitrate (bps)',
    'iface.f.fd': 'CAN FD',
    'iface.f.gpib_address': 'GPIB address (optional)',

    // ---- project section names ----
    'section.models': 'Model Config',
    'section.devices': 'Devices',
    'section.plugins': 'Plugins',
    'section.skills': 'Skills',
    'section.testCases': 'Test Cases',
    'section.executionPlans': 'Execution Manager',
    'section.dashboards': 'Dashboards',

    // ---- punctuation that differs by locale ----
    'punct.colon': ': ',
    'punct.enum': ', ',
    'punct.countParen': ' ({n})',

    // ---- device / interface type names ----
    'deviceType.powerSupply': 'Programmable Power Supply',
    'deviceType.oscilloscope': 'Oscilloscope',
    'deviceType.multimeter': 'Multimeter',
    'deviceType.signalGenerator': 'Signal Generator',
    'deviceType.spectrumAnalyzer': 'Spectrum Analyzer',
    'deviceType.canTool': 'CAN Tool',
    'deviceType.gateway': 'Gateway',
    'deviceType.generic': 'Generic Device',
    'iface.scpi': 'SCPI',
    'iface.can': 'CAN',
    'iface.usb': 'USB',
    'iface.serial': 'Serial',
    'iface.ethernet': 'Ethernet',
    'iface.gpib': 'GPIB',
    'iface.pcie': 'PCIe',
    'iface.pxi': 'PXI / PXIe',
    'iface.custom': 'Custom',
    'iface.miniGateway100': 'Mini Gateway 100',

    // ---- dashboard widget metadata ----
    'widget.parsed_value.label': 'Parsed Value',
    'widget.parsed_value.desc': 'Watch one parsed value: latest reading + PASS/FAIL badge, turns red when out of range',
    'widget.parsed_value.title': 'Parsed Value',
    'widget.trend_chart.label': 'Trend Chart',
    'widget.trend_chart.desc': 'Parsed values over time; FAIL points marked red (watch drift in endurance runs)',
    'widget.trend_chart.title': 'Value Trend',
    'widget.judge_summary.label': 'Judgement Summary',
    'widget.judge_summary.desc': 'Per-field PASS/FAIL counts plus recent FAIL details (a judgement, not an alarm)',
    'widget.judge_summary.title': 'Judgement Summary',
    'widget.device_status.label': 'Device Status',
    'widget.device_status.desc': 'Device online/offline, protocol and address',
    'widget.device_status.title': 'Device Status',
    'widget.execution_stats.label': 'Execution Stats',
    'widget.execution_stats.desc': 'Total runs / passed / failed / running / pass rate',
    'widget.execution_stats.title': 'Execution Stats',
    'widget.comm_log.label': 'Communication Log',
    'widget.comm_log.desc': 'Most recent sent and received frames',
    'widget.comm_log.title': 'Communication Log',
    'widget.note.label': 'Note',
    'widget.note.desc': 'Wiring notes / operating SOP, Markdown supported',
    'widget.note.title': 'Note',
    'widget.status.emptyFrame': 'Empty frame',
    'widget.status.error': 'Error',
    'widget.status.connected': 'Connected',
    'widget.status.disconnected': 'Disconnected',

    // ---- projects ----
    'project.title': 'Project Files',
    'project.new': 'New Project',
    'project.saveAs': 'Save as…',
    'project.export': 'Export current configuration',
    'project.importFile': 'Import project file…',
    'project.merge': 'Merge import',
    'project.replace': 'Replace import',
    'project.saved': 'Saved project files',
    'project.sections': 'Sections to include:',
    'project.newTitle': 'New Project',
    'project.newResult': 'New project result',
    'project.importResult': 'Import result',
    'project.clearedTotal': '{n} configuration entries cleared',
    'project.kept': 'Kept: ',
  },
}

// Bulk entries (table columns, tabs, statuses) live in ./extraKeys so the
// hand-written catalogue above stays readable. Merged once at module load.
for (const extra of [EXTRA, EXTRA2, EXTRA3, EXTRA4, EXTRA5, EXTRA6, EXTRA7, EXTRA8, EXTRA9, EXTRA10, EXTRA11, EXTRA12, HELP_KEYS]) {
  for (const [zh, [key, en]] of Object.entries(extra)) {
    messages['zh-CN'][key] = zh
    messages['en-US'][key] = en
  }
}
