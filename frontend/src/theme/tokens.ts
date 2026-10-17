/**
 * Design tokens — single source of truth for colour, spacing and semantics.
 *
 * Three layers, so a change propagates instead of being copy-pasted:
 *
 *   primitives  raw palette (never referenced directly by components)
 *     ↓
 *   semantic    intent ("what does this colour mean?")
 *     ↓
 *   component   antd theme tokens (what the library actually consumes)
 *
 * Issue #20: the UI must show **3 brand colours + 1 status colour** only, and
 * every status must be encoded by icon + text + colour (never colour alone).
 */

// --------------------------------------------------------------------------- //
// 1. Primitives — raw palette
// --------------------------------------------------------------------------- //

export const graphite = {
  950: '#0E1114',
  900: '#151A1F',
  850: '#1C2228',
  800: '#232A31',
  700: '#2E363F',
  600: '#3D4752',
  500: '#5A6672',
  400: '#7C8894',
  300: '#A4AEB8',
  200: '#C9D1D9',
  100: '#E3E8ED',
  50: '#EDF1F5',
  0: '#FFFFFF',
} as const

/** Instrument Blue — the ONLY interactive colour. */
export const blue = {
  700: '#156B8C',
  600: '#1A7FA8',
  500: '#2296C4', // primary
  400: '#4FADDB',
  300: '#8FCBEA',
  100: '#D9EDF7',
} as const

/** Amber — running / needs attention. */
export const amber = {
  700: '#B87A22',
  600: '#D08B2C',
  500: '#E8A33D', // primary
  400: '#EFBB6D',
  100: '#F9E9CE',
} as const

/** Signal Red — status-only (FAIL / ERROR). Never used for actions. */
export const red = {
  700: '#D9534A',
  600: '#EC645B',
  500: '#FF7B72', // primary
  400: '#FF9E97',
  100: '#FFE2DF',
} as const

export const primitives = { graphite, blue, amber, red } as const

// --------------------------------------------------------------------------- //
// 2. Semantic — intent
// --------------------------------------------------------------------------- //

export const semantic = {
  // Surfaces
  bgBase: graphite[950],
  bgElevated: graphite[900],
  bgSunken: graphite[850],
  border: graphite[800],
  borderStrong: graphite[700],

  // Text
  textPrimary: graphite[50],
  textSecondary: graphite[300],
  textTertiary: graphite[400],

  // Interaction (Instrument Blue)
  accent: blue[500],
  accentHover: blue[400],
  accentActive: blue[600],
  accentSubtle: blue[100],
  focusRing: blue[400],

  // Status
  running: amber[500],
  attention: amber[500],
  pass: blue[500], // PASS uses the interactive blue per #20
  fail: red[500],
  error: red[500],
  warn: amber[500],
} as const

// --------------------------------------------------------------------------- //
// 3. Component tokens consumed by antd
// --------------------------------------------------------------------------- //

export const componentTokens = {
  // Layout
  siderWidth: 208,
  siderCollapsedWidth: 56,
  outputDockCollapsed: 34,
  outputDockWidth: 420,
  headerHeight: 56,
  statusBarHeight: 32,

  // Radius / spacing
  radiusSm: 4,
  radiusMd: 6,
  radiusLg: 10,

  // Table contract (closes #17 / #19)
  // Every column MUST declare an explicit width and the table a scroll.x.
  tableScrollX: 1200,
  tableRowHeight: 40,
} as const

/** antd theme token overrides shared by both algorithms. */
export function antdTokens(mode: 'light' | 'dark') {
  const isDark = mode === 'dark'
  return {
    colorPrimary: semantic.accent,
    colorInfo: semantic.accent,
    colorSuccess: semantic.pass,
    colorWarning: semantic.warn,
    colorError: semantic.error,
    colorLink: semantic.accent,
    borderRadius: componentTokens.radiusMd,
    fontSize: 13,
    // Dark surfaces come from the algorithm; these keep contrast predictable.
    colorBgContainer: isDark ? graphite[900] : graphite[0],
    colorBgElevated: isDark ? graphite[850] : graphite[0],
    colorBorder: isDark ? graphite[800] : graphite[100],
    colorBorderSecondary: isDark ? graphite[850] : graphite[50],
    colorText: isDark ? graphite[50] : graphite[950],
    colorTextSecondary: isDark ? graphite[300] : graphite[600],
    colorTextTertiary: isDark ? graphite[400] : graphite[500],
  }
}

export type ThemeMode = 'light' | 'dark'
