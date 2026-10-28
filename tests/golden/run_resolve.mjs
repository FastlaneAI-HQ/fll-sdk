/** Run frontend/theme-resolve.ts over golden fixtures and print the results as JSON.
 *  Usage: node tests/golden/run_resolve.mjs [theme-resolve|layout-tree|brand|shell-from-layout]  (needs the SDK's esbuild dev dependency)
 *  `theme-resolve` holds themes without a tree or a brand (tokens, dark palettes, layout options); `layout-tree` themes with a
 *  tree (resolved trees, shell validation); `brand` themes with a brand (validation, and for a valid theme the resolved brand);
 *  `shell-from-layout` maps layouts to trees. */
import { build } from 'esbuild'
import { mkdtempSync, readdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL, fileURLToPath } from 'node:url'

const here = fileURLToPath(new URL('.', import.meta.url))
const out = join(mkdtempSync(join(tmpdir(), 'fll-resolve-')), 'resolve.mjs')
await build({ entryPoints: [resolve(here, '../../frontend/theme-resolve.ts')], outfile: out, bundle: true, format: 'esm', platform: 'node', logLevel: 'silent' })
const lib = await import(pathToFileURL(out).href)
const results = {}
const set = process.argv[2] ?? 'theme-resolve'
if (set === 'shell-from-layout') {
  const golden = JSON.parse(readFileSync(join(here, 'shell-from-layout.json'), 'utf8'))
  for (const [name, item] of Object.entries(golden)) results[name] = lib.shellFromLayout(item.layout)
  console.log(JSON.stringify(results))
  process.exit(0)
}
const dir = join(here, set)
for (const file of readdirSync(dir).filter(name => name.endsWith('.json')).sort()) {
  const golden = JSON.parse(readFileSync(join(dir, file), 'utf8'))
  const theme = golden.input
  const result = {}
  if (set === 'brand') {
    result.validate = lib.validateBrand(theme.brand)
    if (golden.resolve) { result.resolve = lib.resolveTheme(theme); result.contrast = lib.contrastReport(theme) }
    results[file] = result
    continue
  }
  result.resolve = lib.resolveTheme(theme)
  result.contrast = lib.contrastReport(theme)
  result.tree = lib.shellTreeOf(theme)
  if (set === 'layout-tree') {
    result.validate = theme.layout.shell ? lib.validateShell(theme.layout.shell, undefined, 'layout.shell', theme.layout.scroll) : null
  }
  if (theme.color_scheme && theme.color_scheme !== 'light') {
    result.resolve_dark = lib.resolveTheme(theme, 'dark')
    result.derive = theme.color_scheme === 'auto' ? lib.deriveDark(theme) : null
  }
  results[file] = result
}
console.log(JSON.stringify(results))
