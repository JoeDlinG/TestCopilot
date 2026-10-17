import { graphite, blue, amber, red } from './tokens'

/**
 * CSS custom properties derived from the design tokens (issue #22).
 *
 * The flow editor lives inside its own canvas where antd's JS theme objects are
 * awkward to reach (SVG fills, ReactFlow handles, ``<pre>`` blocks). Exposing the
 * palette as CSS variables lets those spots stay token-driven and follow the
 * light/dark switch without duplicating a single hex value here — everything is
 * computed from ``tokens.ts``.
 */

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ]
}

function toHex(rgb: [number, number, number]): string {
  return '#' + rgb.map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')
}

/** Linear blend: ``weightA`` = how much of colour A survives. */
function mix(a: string, b: string, weightA: number): string {
  const ra = hexToRgb(a)
  const rb = hexToRgb(b)
  return toHex([
    ra[0] * weightA + rb[0] * (1 - weightA),
    ra[1] * weightA + rb[1] * (1 - weightA),
    ra[2] * weightA + rb[2] * (1 - weightA),
  ])
}

function rgba(hex: string, alpha: number): string {
  const [r, g, b] = hexToRgb(hex)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function scale(prefix: string, palette: Record<string, string>): string {
  return Object.entries(palette)
    .map(([step, value]) => `    --${prefix}-${step}: ${value};`)
    .join('\n')
}

interface Surfaces {
  canvasBg: string
  grid: string
  panelBg: string
  panelBorder: string
  panelFg: string
  border: string
  codeBg: string
  codeFg: string
  accentFg: string
  tintFg: string
  badgeFg: string
  amberFg: string
}

const LIGHT: Surfaces = {
  canvasBg: graphite[0],
  grid: graphite[100],
  panelBg: graphite[50],
  panelBorder: graphite[100],
  panelFg: graphite[500],
  border: graphite[100],
  codeBg: graphite[50],
  codeFg: graphite[900],
  accentFg: blue[600],
  tintFg: blue[700],
  badgeFg: graphite[800],
  amberFg: amber[700],
}

const DARK: Surfaces = {
  canvasBg: graphite[950],
  grid: graphite[800],
  panelBg: graphite[900],
  panelBorder: graphite[800],
  panelFg: graphite[400],
  border: graphite[800],
  codeBg: graphite[950],
  codeFg: graphite[100],
  accentFg: blue[300],
  tintFg: blue[300],
  badgeFg: graphite[100],
  amberFg: amber[500],
}

function flowVars(v: Surfaces): string {
  return [
    `    --flow-canvas-bg: ${v.canvasBg};`,
    `    --flow-grid: ${v.grid};`,
    `    --flow-panel-bg: ${v.panelBg};`,
    `    --flow-panel-border: ${v.panelBorder};`,
    `    --flow-panel-fg: ${v.panelFg};`,
    `    --flow-border: ${v.border};`,
    `    --flow-code-bg: ${v.codeBg};`,
    `    --flow-code-fg: ${v.codeFg};`,
    // ------------------------------------------------------------------ //
    // Node surfaces — 莫兰迪（Morandi）色调
    //
    // Low-saturation, mid-value fills so the canvas reads as one muted family.
    // Every mix() below is derived from the primitives, so the palette stays
    // governed by tokens.ts. All types carry WHITE text except 循环, which is
    // deliberately light-amber-on-dark-amber.
    // ------------------------------------------------------------------ //
    `    --flow-node-solid-bg: ${graphite[700]};`,
    `    --flow-node-weak-bg: ${graphite[600]};`,
    // 开始 — 深莫兰迪蓝
    `    --flow-node-start-bg: ${mix(blue[700], graphite[700], 0.70)};`,
    `    --flow-node-start-fg: ${graphite[0]};`,
    `    --flow-node-start-border: ${mix(blue[700], graphite[500], 0.55)};`,
    // 初始化 — 蓝灰（低饱和，介于开始与判断之间）
    `    --flow-node-init-bg: ${mix(blue[500], graphite[500], 0.42)};`,
    `    --flow-node-init-fg: ${graphite[0]};`,
    `    --flow-node-init-border: ${mix(blue[600], graphite[400], 0.45)};`,
    // 操作 — 石墨灰（明确不是纯黑：#1C2228 太沉，改用 #3D4752）
    `    --flow-node-action-bg: ${graphite[600]};`,
    `    --flow-node-action-fg: ${graphite[0]};`,
    `    --flow-node-action-border: ${graphite[500]};`,
    // 判断 — 仪器蓝（偏浅）：比原先的深灰菱形亮，但仍够承载白字
    `    --flow-node-cond-bg: ${mix(blue[600], graphite[600], 0.72)};`,
    `    --flow-node-cond-fg: ${graphite[0]};`,
    `    --flow-node-cond-border: ${mix(blue[700], graphite[400], 0.60)};`,
    // 循环 — 浅琥珀底 + 深琥珀字（唯一不使用白字的类型）。
    // 直接用 amber[700] 对 #F9E9CE 只有 3.0:1，达不到 AA，故再向石墨压暗。
    `    --flow-node-loop-bg: ${amber[100]};`,
    `    --flow-node-loop-fg: ${mix(amber[700], graphite[900], 0.70)};`,
    `    --flow-node-loop-border: ${amber[500]};`,
    `    --flow-loop-bar: ${amber[500]};`,
    // 延时 — 中灰 + 虚线（弱化）
    `    --flow-node-delay-bg: ${graphite[500]};`,
    `    --flow-node-delay-fg: ${graphite[0]};`,
    `    --flow-node-delay-border: ${graphite[300]};`,
    // 结束 — 深灰（弱化，且绝不用红：红色专属 FAIL/ERROR）
    `    --flow-node-end-bg: ${graphite[800]};`,
    `    --flow-node-end-fg: ${graphite[0]};`,
    `    --flow-node-end-border: ${graphite[600]};`,
    // ------------------------------------------------------------------ //
    // 连接点（handles）：统一仪器蓝 + 轮廓线，选中高亮。
    // 判断的「是/非」两个出口仍保留深浅对比，但同属蓝色系。
    // ------------------------------------------------------------------ //
    `    --flow-handle-bg: ${blue[500]};`,
    `    --flow-handle-border: ${graphite[50]};`,
    `    --flow-handle-active: ${blue[300]};`,
    `    --flow-handle-true: ${blue[700]};`,
    `    --flow-handle-false: ${blue[300]};`,
    // Selection ring (blue) is a *state* layer, independent of node type.
    `    --flow-selected: ${rgba(blue[500], 0.45)};`,
    `    --flow-selected-solid: ${graphite[850]};`,
    // IO badges sit on every node surface, so they need a neutral that reads
    // on both the graphite fill and the light blue tint.
    `    --flow-badge-bg: ${mix(graphite[200], v.canvasBg, 0.25)};`,
    `    --flow-badge-fg: ${v.badgeFg};`,
    `    --flow-badge-border: ${mix(graphite[200], v.canvasBg, 0.45)};`,
    // Amber text/border that stays legible on both backgrounds.
    `    --a-fg: ${v.amberFg};`,
    // Running state: amber pulse, deliberately a different channel from the
    // static amber loop border so the two cannot be confused.
    `    --flow-running: ${amber[500]};`,
    `    --flow-failed: ${red[500]};`,
  ].join('\n')
}

// --------------------------------------------------------------------------- //
// Application surfaces (issue #23)
//
// Pages and shared components carried ~170 hard-coded hex values straight from
// the AntD palette. These cover every role those values were playing, mode
// aware, so a page can reference intent ("muted border") instead of a literal.
// --------------------------------------------------------------------------- //

interface AppSurfaces {
  bg: string
  surface: string
  surfaceMuted: string
  surfaceSunken: string
  hover: string
  border: string
  borderStrong: string
  fg: string
  fgMuted: string
  fgSubtle: string
  accentSubtle: string
  codeBg: string
  codeFg: string
  dangerBg: string
  series: string[]
}

const APP_LIGHT: AppSurfaces = {
  bg: graphite[0],
  surface: graphite[0],
  surfaceMuted: graphite[50],
  surfaceSunken: graphite[50],
  hover: graphite[50],
  border: graphite[100],
  borderStrong: graphite[200],
  fg: graphite[950],
  fgMuted: graphite[600],
  fgSubtle: graphite[500],
  accentSubtle: blue[100],
  codeBg: graphite[50],
  codeFg: graphite[900],
  dangerBg: mix(red[500], graphite[0], 0.06),
  series: [blue[600], blue[500], blue[400], amber[700], amber[500], red[600], graphite[600], graphite[500]],
}

const APP_DARK: AppSurfaces = {
  bg: graphite[950],
  surface: graphite[900],
  surfaceMuted: graphite[900],
  surfaceSunken: graphite[850],
  hover: graphite[850],
  border: graphite[800],
  borderStrong: graphite[700],
  fg: graphite[50],
  fgMuted: graphite[300],
  fgSubtle: graphite[400],
  accentSubtle: mix(blue[500], graphite[950], 0.18),
  codeBg: graphite[950],
  codeFg: graphite[100],
  dangerBg: mix(red[500], graphite[950], 0.14),
  series: [blue[400], blue[300], blue[500], amber[400], amber[500], red[500], graphite[300], graphite[400]],
}

function appVars(v: AppSurfaces): string {
  return [
    `    --app-bg: ${v.bg};`,
    `    --app-surface: ${v.surface};`,
    `    --app-surface-muted: ${v.surfaceMuted};`,
    `    --app-surface-sunken: ${v.surfaceSunken};`,
    `    --app-hover: ${v.hover};`,
    `    --app-border: ${v.border};`,
    `    --app-border-strong: ${v.borderStrong};`,
    `    --app-fg: ${v.fg};`,
    `    --app-fg-muted: ${v.fgMuted};`,
    `    --app-fg-subtle: ${v.fgSubtle};`,
    `    --app-accent: ${blue[500]};`,
    `    --app-accent-hover: ${blue[400]};`,
    `    --app-accent-subtle: ${v.accentSubtle};`,
    // PASS is the interactive blue; only FAIL/ERROR get red (#20).
    `    --app-pass: ${blue[500]};`,
    `    --app-fail: ${red[500]};`,
    `    --app-warn: ${amber[500]};`,
    `    --app-running: ${amber[500]};`,
    `    --app-code-bg: ${v.codeBg};`,
    `    --app-code-fg: ${v.codeFg};`,
    `    --app-danger-bg: ${v.dangerBg};`,
    // Big-screen / presentation backdrop — deep instrument navy.
    `    --app-bigscreen-bg: ${mix(blue[700], graphite[950], 0.30)};`,
    // Text that always sits on a dark backdrop (big-screen mode). Mode
    // independent on purpose: the backdrop is dark in both themes.
    `    --app-on-dark: ${graphite[50]};`,
    // Chart series: derived from the palette instead of AntD's rainbow.
    ...v.series.map((c, i) => `    --app-series-${i + 1}: ${c};`),
  ].join('\n')
}

/**
 * Terminal surfaces.
 *
 * The debug terminal is deliberately always dark — that is what engineers
 * expect from a serial console — so these are NOT mode dependent.
 */
function termVars(): string {
  return [
    `    --term-bg: ${graphite[950]};`,
    `    --term-chrome: ${graphite[900]};`,
    `    --term-chrome-alt: ${graphite[850]};`,
    `    --term-input-bg: ${graphite[800]};`,
    `    --term-input-border: ${graphite[700]};`,
    `    --term-border: ${graphite[800]};`,
    `    --term-fg: ${graphite[100]};`,
    `    --term-fg-muted: ${graphite[400]};`,
    `    --term-fg-subtle: ${graphite[500]};`,
    // Sent = instrument blue (an action we took); received = neutral (data).
    `    --term-sent: ${blue[400]};`,
    `    --term-recv: ${graphite[200]};`,
    `    --term-data: ${amber[400]};`,
    `    --term-error: ${red[500]};`,
    `    --term-system: ${graphite[500]};`,
  ].join('\n')
}

export const cssVars: string = `  :root {
${scale('g', graphite)}
${scale('b', blue)}
${scale('a', amber)}
${scale('r', red)}

    /* ---- Flow editor surfaces (light) ---- */
${flowVars(LIGHT)}

    /* ---- Application surfaces (light) ---- */
${appVars(APP_LIGHT)}
${termVars()}
  }

  :root[data-theme='dark'] {
    /* ---- Flow editor surfaces (dark) ---- */
${flowVars(DARK)}

    /* ---- Application surfaces (dark) ---- */
${appVars(APP_DARK)}
  }
`
