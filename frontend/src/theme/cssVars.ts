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
    // Node surfaces — encoding is by fill / outline / dash, not by hue.
    `    --flow-node-solid-bg: ${graphite[850]};`,
    `    --flow-node-solid-fg: ${graphite[200]};`,
    `    --flow-node-weak-bg: ${graphite[800]};`,
    `    --flow-node-weak-fg: ${graphite[400]};`,
    `    --flow-node-outline-bg: transparent;`,
    `    --flow-node-outline-fg: ${v.accentFg};`,
    `    --flow-node-outline-border: ${v.accentFg};`,
    // 12% blue wash — derived, so it stays correct in both themes.
    `    --flow-node-tint-bg: ${mix(blue[500], v.canvasBg, 0.12)};`,
    `    --flow-node-tint-fg: ${v.tintFg};`,
    `    --flow-node-dashed-fg: ${graphite[400]};`,
    `    --flow-node-dashed-border: ${graphite[500]};`,
    `    --flow-node-dim-bg: ${graphite[800]};`,
    `    --flow-node-dim-fg: ${graphite[400]};`,
    // Selection ring (blue) is a *state* layer, independent of node type.
    `    --flow-selected: ${rgba(blue[500], 0.45)};`,
    `    --flow-selected-solid: ${graphite[850]};`,
    // Loop is the only node type allowed to use amber (issue #22).
    `    --flow-loop-bar: ${amber[500]};`,
    `    --flow-loop-fg: ${amber[500]};`,
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
