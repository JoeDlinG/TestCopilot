#!/usr/bin/env node
/**
 * i18n guard (issue #27, sub-task P1).
 *
 * The v2.2.0 "English completion" pass was done by hand, page by page, and it
 * missed two whole classes of string — with no way to notice afterwards:
 *
 *   A. **Hard-coded CJK display text** living in constants/registries
 *      (``PROJECT_SECTIONS``, ``DEVICE_TYPE_LABELS``, card metadata…). ``t()``
 *      was never involved, so the catalogue could never translate them.
 *   B. **``t('x')`` written into JSX text / template literals / attribute
 *      strings** instead of a ``{}`` expression. React renders it literally, so
 *      users see ``t('label.sourceColon')`` on screen. ``tsc`` happily accepts
 *      it (any text is valid JSX) which is how 59 of these shipped.
 *
 * This script turns both into a build gate:
 *
 *   * B is **zero tolerance** — every hit is a user-visible bug.
 *   * A is a **ratchet** — the count may only go down. Recorded in
 *     ``scripts/i18n-baseline.json`` so a refactor cannot quietly add more.
 *
 * Usage:
 *   node scripts/i18n-guard.mjs                 # check (exit 1 on failure)
 *   node scripts/i18n-guard.mjs --update-baseline
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as parser from '@babel/parser'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const SRC = path.resolve(HERE, '..', 'src')
const BASELINE_FILE = path.join(HERE, 'i18n-baseline.json')

const CJK = /[一-鿿　-〿＀-￯]/
// Require the call to actually look like a key lookup. A bare /t\(/ also
// matches prose such as "repeat(" and produces false positives.
const T_CALL = /t\(\s*['"`]/

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules') continue
      walk(full, out)
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.d\.ts$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

function parse(file, code) {
  return parser.parse(code, {
    sourceType: 'module',
    allowImportExportEverywhere: true,
    allowReturnOutsideFunction: true,
    plugins: [
      'typescript',
      'jsx',
      ['decorators', { decoratorsBeforeExport: true }],
      'classProperties',
      'optionalChaining',
      'nullishCoalescingOperator',
      'dynamicImport',
    ],
  })
}

/** Depth-first walk over every node, reporting nodes that match ``pred``. */
function visit(node, pred, out) {
  if (!node || typeof node !== 'object') return out
  if (Array.isArray(node)) {
    for (const child of node) visit(child, pred, out)
    return out
  }
  if (typeof node.type === 'string') {
    if (pred(node)) out.push(node)
  }
  for (const key of Object.keys(node)) {
    if (key === 'loc' || key === 'leadingComments' || key === 'trailingComments') continue
    visit(node[key], pred, out)
  }
  return out
}

/** Does this source position sit inside a comment? (comments must not count) */
function inComment(code, comments, index) {
  return comments.some((c) => c.start <= index && index < c.end)
}

function scanFile(file) {
  const code = fs.readFileSync(file, 'utf8')
  let ast
  try {
    ast = parse(file, code)
  } catch {
    return { bHits: [], cjk: 0, parseError: true }
  }
  const comments = ast.comments || []
  const bHits = []
  let cjk = 0

  const rel = path.relative(SRC, file).split(path.sep).join('/')
  const inI18n = rel.startsWith('i18n/')

  // ---- B: t( ... ) rendered as literal text ----
  const isTextish = (n) =>
    n.type === 'JSXText' ||
    n.type === 'TemplateElement' ||
    (n.type === 'StringLiteral' && n.extra?.raw?.startsWith('"'))

  const textNodes = visit(ast.program, isTextish, [])
  for (const n of textNodes) {
    const raw = n.type === 'TemplateElement'
      ? (n.value?.raw ?? '')
      : n.type === 'JSXText'
        ? (n.value ?? '')
        : (n.value ?? '')
    if (!T_CALL.test(raw)) continue
    const idx = n.start ?? 0
    if (inComment(code, comments, idx)) continue
    bHits.push(`${rel}:${n.loc?.start?.line ?? '?'}: ${raw.trim().slice(0, 90)}`)
  }

  // ---- A: hard-coded CJK strings outside src/i18n ----
  if (!inI18n) {
    const lits = visit(
      ast.program,
      (n) => n.type === 'StringLiteral' || n.type === 'TemplateElement',
      [],
    )
    for (const n of lits) {
      const raw = n.type === 'TemplateElement' ? (n.value?.raw ?? '') : (n.value ?? '')
      if (!CJK.test(raw)) continue
      const idx = n.start ?? 0
      if (inComment(code, comments, idx)) continue
      cjk++
    }
  }

  return { bHits, cjk }
}

function main() {
  const update = process.argv.includes('--update-baseline')
  const files = walk(SRC)

  let cjkTotal = 0
  const bHits = []
  let parseErrors = 0
  for (const f of files) {
    const r = scanFile(f)
    cjkTotal += r.cjk
    bHits.push(...r.bHits)
    if (r.parseError) parseErrors++
  }

  const previous = fs.existsSync(BASELINE_FILE)
    ? JSON.parse(fs.readFileSync(BASELINE_FILE, 'utf8'))
    : null

  if (update) {
    fs.writeFileSync(
      BASELINE_FILE,
      JSON.stringify({ cjk: cjkTotal, updated: new Date().toISOString() }, null, 2) + '\n',
    )
    console.log(`baseline updated: cjk=${cjkTotal}`)
    return
  }

  const lines = []
  lines.push(`scanned ${files.length} files (parse errors: ${parseErrors})`)
  lines.push('')
  lines.push(`A. hard-coded CJK strings outside src/i18n: ${cjkTotal}` +
    (previous ? `  (baseline ${previous.cjk})` : ''))
  lines.push(`B. literal t('...') rendered as text:      ${bHits.length}  (must be 0)`)

  let failed = false

  if (bHits.length) {
    failed = true
    lines.push('')
    lines.push('B hits — wrap them in {} or ${}:')
    for (const h of bHits) lines.push(`   ${h}`)
  }
  if (previous && cjkTotal > previous.cjk) {
    failed = true
    lines.push('')
    lines.push(`A regression: ${previous.cjk} -> ${cjkTotal}. ` +
      `Only decreases are allowed; re-run with --update-baseline if intended.`)
  }
  if (!previous) {
    lines.push('')
    lines.push('no baseline yet — run with --update-baseline to record one')
  }

  console.log(lines.join('\n'))
  if (failed) process.exit(1)
}

main()
