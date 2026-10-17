import {
  ApiOutlined,
  DashboardOutlined,
  AppstoreAddOutlined,
  CodeOutlined,
  RobotOutlined,
  OrderedListOutlined,
  SettingOutlined,
  FolderOpenOutlined,
  FileTextOutlined,
  PlayCircleOutlined,
  FileDoneOutlined,
  DiffOutlined,
} from '@ant-design/icons'
import type { ReactNode } from 'react'

/**
 * Navigation definition — shared by the sidebar, the top bar dropdowns and the
 * ⌘K command palette so the three can never drift apart.
 */

export interface NavItem {
  key: string
  icon: ReactNode
  labelKey: string
  /** Extra terms the ⌘K palette should match on (pinyin-ish / English). */
  aliases?: string[]
}

export interface NavGroup {
  key: string
  labelKey: string
  items: NavItem[]
}

/** Left sidebar: 3 groups / 8 items (issue #20). */
export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'g-config',
    labelKey: 'nav.group.config',
    items: [
      { key: '/devices', icon: <ApiOutlined />, labelKey: 'nav.devices', aliases: ['device', '设备'] },
    ],
  },
  {
    key: 'g-design',
    labelKey: 'nav.group.design',
    items: [
      { key: '/testcases', icon: <DiffOutlined />, labelKey: 'nav.testcases', aliases: ['case', '用例'] },
      { key: '/ai', icon: <RobotOutlined />, labelKey: 'nav.ai', aliases: ['assistant', 'AI'] },
      { key: '/execution-plans', icon: <OrderedListOutlined />, labelKey: 'nav.plans', aliases: ['plan', '计划'] },
      { key: '/debug-terminal', icon: <CodeOutlined />, labelKey: 'nav.debugTerminal', aliases: ['terminal', '终端'] },
    ],
  },
  {
    key: 'g-system',
    labelKey: 'nav.group.system',
    items: [
      { key: '/plugins', icon: <AppstoreAddOutlined />, labelKey: 'nav.pluginCenter', aliases: ['plugin', '插件', 'skill'] },
      { key: '/model-config', icon: <SettingOutlined />, labelKey: 'nav.modelConfig', aliases: ['model', '模型'] },
      { key: '/projects', icon: <FolderOpenOutlined />, labelKey: 'nav.projects', aliases: ['project', '工程'] },
    ],
  },
]

/** Top bar dropdowns (issue #20: dashboards + tools). */
export const TOP_MENUS: { key: string; labelKey: string; items: NavItem[] }[] = [
  {
    key: 'dashboards',
    labelKey: 'top.dashboards',
    items: [
      { key: '/', icon: <DashboardOutlined />, labelKey: 'nav.dashboard', aliases: ['overview', '总览'] },
      { key: '/dashboards', icon: <AppstoreAddOutlined />, labelKey: 'nav.customDashboard', aliases: ['custom', '自定义'] },
    ],
  },
  {
    key: 'tools',
    labelKey: 'top.tools',
    items: [
      { key: '/logs', icon: <FileTextOutlined />, labelKey: 'nav.logs', aliases: ['log', '日志'] },
    ],
  },
]

/** Right-hand output dock tabs. */
export const DOCK_TABS: NavItem[] = [
  { key: 'dock:executions', icon: <PlayCircleOutlined />, labelKey: 'dock.executions', aliases: ['run', '执行'] },
  { key: 'dock:reports', icon: <FileDoneOutlined />, labelKey: 'dock.reports', aliases: ['report', '报告'] },
]

/** Flat list consumed by the command palette. */
export const ALL_NAV_ITEMS: NavItem[] = [
  ...NAV_GROUPS.flatMap((g) => g.items),
  ...TOP_MENUS.flatMap((m) => m.items),
  ...DOCK_TABS,
]
