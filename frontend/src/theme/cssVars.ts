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

export const cssVars: string = `  :root {
${scale('g', graphite)}
${scale('b', blue)}
${scale('a', amber)}
${scale('r', red)}

    /* ---- Flow editor surfaces (light) ---- */
${flowVars(LIGHT)}
  }

  :root[data-theme='dark'] {
    /* ---- Flow editor surfaces (dark) ---- */
${flowVars(DARK)}
  }
`
