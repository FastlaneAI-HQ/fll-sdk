/** Run frontend/theme-resolve.ts's layout-tree functions over cases written by tests/test_layout_tree_parity.py.
 *  Usage: node tests/golden/run_shell.mjs CASES.json  (needs the SDK's esbuild dev dependency)
 *  CASES.json: { cases: [{ id, shell, scroll, installed, vocabulary }], layouts: [layout, ...], themes: [theme, ...],
 *  brands: [{ id, brand, vocabulary }] }.
 *  Prints { results: { id: { errors, warnings, tree } }, layouts: [tree, ...], themes: [{ resolved, tree }, ...] }; `tree` of a case is the
 *  normalised shell, only when it has no error; `brands` is { id: { errors, warnings, brand } }, `brand` the normalised brand, only when it has no error; `logo_for` is { light, dark }, `brandLogoFor(brand, false/true)`, with the same condition. */
import { build } from 'esbuild'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'

const here = fileURLToPath(new URL('.', import.meta.url))
const out = join(mkdtempSync(join(tmpdir(), 'fll-shell-')), 'resolve.mjs')
await build({ entryPoints: [resolve(here, '../../frontend/theme-resolve.ts')], outfile: out, bundle: true, format: 'esm', platform: 'node', logLevel: 'silent' })
const lib = await import(pathToFileURL(out).href)
const input = JSON.parse(readFileSync(process.argv[2], 'utf8'))
const results = {}
for (const item of input.cases) {
  const vocabulary = item.vocabulary ?? undefined
  const found = lib.validateShell(item.shell, vocabulary, 'layout.shell', item.scroll ?? null, item.installed ?? null)
  results[item.id] = { errors: found.errors, warnings: found.warnings, tree: found.errors.length ? null : lib.normaliseShell(item.shell, vocabulary) }
}
const themes = (input.themes ?? []).map(theme => ({ resolved: lib.resolveTheme(theme), tree: lib.shellTreeOf(theme) }))
const brands = {}
for (const item of input.brands ?? []) {
  const vocabulary = item.vocabulary ?? undefined
  const found = lib.validateBrand(item.brand, vocabulary)
  const brand = found.errors.length ? null : lib.normaliseBrand(item.brand, vocabulary)
  brands[item.id] = { errors: found.errors, warnings: found.warnings, brand, logo_for: brand === null ? null : { light: lib.brandLogoFor(brand, false), dark: lib.brandLogoFor(brand, true) } }
}
console.log(JSON.stringify({ results, layouts: (input.layouts ?? []).map(layout => lib.shellFromLayout(layout)), themes, brands }))
