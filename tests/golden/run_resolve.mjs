/** Run frontend/theme-resolve.ts over golden fixtures and print the results as JSON.
 *  Usage: node tests/golden/run_resolve.mjs [theme-resolve|frozen-r1|frozen-r2]  (needs the SDK's esbuild dev dependency)
 *  `frozen-r1` and `frozen-r2` are what SDK 1.3 and 1.4 produced for registry revisions 1 and 2: v1 upgrades are pinned to them. */
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
const revision = set === 'frozen-r1' ? 1 : set === 'frozen-r2' ? 2 : undefined
const dir = join(here, set)
for (const file of readdirSync(dir).filter(name => name.endsWith('.json')).sort()) {
  const golden = JSON.parse(readFileSync(join(dir, file), 'utf8'))
  const manifest = golden.input
  const result = {}
  let v2 = manifest
  if (manifest.api_version === 1) {
    result.upgrade = lib.upgradeV1Report(manifest, golden.presentation, revision)
    result.resolve_v1 = lib.resolveTheme(manifest)
    v2 = result.upgrade.theme
    result.project = lib.projectV1(v2)
  }
  result.resolve = lib.resolveTheme(v2)
  result.contrast = lib.contrastReport(v2)
  if (v2.color_scheme && v2.color_scheme !== 'light') {
    result.resolve_dark = lib.resolveTheme(v2, 'dark')
    result.derive = v2.color_scheme === 'auto' ? lib.deriveDark(v2) : null
  }
  results[file] = result
}
console.log(JSON.stringify(results))
