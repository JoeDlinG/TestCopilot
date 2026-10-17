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
  conditionBg: string
  conditionBorder: string
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
  // White text needs a slightly deeper blue in light mode.
  conditionBg: blue[600],
  conditionBorder: blue[700],
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
  conditionBg: blue[700],
  conditionBorder: blue[600],
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
    // ---- Node surfaces (issue #22 follow-up) ---------------------------- //
    // Fill is graphite, NOT near-black: #1C2228 read as pure black on screen.
    // Text is white on every surface, which is only safe because *every* type
    // now has a real fill (开始 / 延时 used to be transparent).
    `    --flow-node-bg: ${graphite[700]};`,      // 标准
    `    --flow-node-bg-alt: ${graphite[600]};`,  // 初始化 — 浅一档
    `    --flow-node-bg-dim: ${graphite[800]};`,  // 结束 — 深一档
    `    --flow-node-fg: #FFFFFF;`,
    `    --flow-node-fg-dim: rgba(255, 255, 255, 0.72);`,
    `    --flow-node-border: ${graphite[500]};`,
    // 开始 / 初始化 — instrument-blue outline on the graphite fill.
    `    --flow-node-outline-bg: ${graphite[700]};`,
    `    --flow-node-outline-border: ${blue[500]};`,
    // 判断 — instrument blue (was graphite); the diamond is the only blue type.
    `    --flow-condition-bg: ${v.conditionBg};`,
    `    --flow-condition-border: ${v.conditionBorder};`,
    // 延时 — dashed border, de-emphasised.
    `    --flow-node-dashed-bg: ${graphite[700]};`,
    `    --flow-node-dashed-border: ${graphite[300]};`,
    // Selection ring (blue) is a *state* layer, independent of node type.
    `    --flow-selected: ${rgba(blue[500], 0.45)};`,
    // 循环 — the only amber type (1px ring + 3px left bar).
    `    --flow-loop-bar: ${amber[500]};`,
    `    --flow-loop-fg: ${amber[500]};`,
    // Connection points are uniformly instrument blue and brighten on
    // hover / selection, so they read as "grab me" on every node type.
    `    --flow-handle: ${blue[500]};`,
    `    --flow-handle-active: ${blue[300]};`,
    `    --flow-handle-halo: ${rgba(blue[500], 0.35)};`,
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
