/** Build an independently installable app with the host's React instance. */
import { build } from 'esbuild'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import preset from './tailwind-preset.mjs'
import { UI_EXPORTS } from './ui-exports.mjs'
const cwd = process.cwd()
mkdirSync('dist', { recursive: true })
const reactExports = ['Children','Component','Fragment','Profiler','PureComponent','StrictMode','Suspense','cloneElement','createContext','createElement','createRef','forwardRef','isValidElement','lazy','memo','startTransition','useCallback','useContext','useDebugValue','useDeferredValue','useEffect','useId','useImperativeHandle','useInsertionEffect','useLayoutEffect','useMemo','useReducer','useRef','useState','useSyncExternalStore','useTransition','version']
/** The module an app gets for `fastlanelabs/ui` (and for `antd`, `@ant-design/*`): one `export const X = ui.X` per name in ui-exports.mjs,
 *  read from the host's instance at load time. An app never bundles antd; a name that is not in the list is a build error. */
const uiShim = ['const ui=globalThis.__FASTLANE_PLATFORM__.ui;', ...UI_EXPORTS.map(name => `export const ${name}=ui.${name};`)].join('\n')
await build({
  entryPoints: [resolve(cwd, 'src/index.tsx')], outfile: 'dist/app.js',
  nodePaths: [fileURLToPath(new URL('../node_modules', import.meta.url))],
  bundle: true, format: 'esm', platform: 'browser', target: 'es2020',
  jsx: 'automatic', minify: true,
  plugins: [{ name: 'platform-contract', setup(b) {
    // antd, its packages and dayjs are the host's: they resolve to the same shim as `fastlanelabs/ui`, so there is one instance, one theme.
    b.onResolve({ filter: /^(react(?:\/jsx-runtime)?|fastlanelabs\/(?:api|ui|theme)|antd(?:\/.*)?|@ant-design\/.+)$/ }, args => ({ path: /^(antd|@ant-design)/.test(args.path) ? 'fastlanelabs/ui' : args.path, namespace: 'platform' }))
    b.onResolve({ filter: /^dayjs(?:\/.*)?$/ }, () => ({ path: 'dayjs', namespace: 'platform' }))
    b.onLoad({ filter: /.*/, namespace: 'platform' }, args => {
      if (args.path === 'react') return { contents: `const r=globalThis.__FASTLANE_PLATFORM__.react; export default r; ${reactExports.map(name=>`export const ${name}=r.${name};`).join('')}` }
      if (args.path === 'react/jsx-runtime') return { contents: 'const r=globalThis.__FASTLANE_PLATFORM__.jsx; export const jsx=r.jsx, jsxs=r.jsxs, Fragment=r.Fragment;' }
      if (args.path === 'fastlanelabs/theme') return { contents: 'const theme=globalThis.__FASTLANE_PLATFORM__.theme; export const ThemePreview=theme.ThemePreview, resolveTheme=theme.resolveTheme, applyResolved=theme.applyResolved, ShellLayoutProvider=theme.ShellLayoutProvider, deriveDark=theme.deriveDark, offeredModes=theme.offeredModes, effectiveMode=theme.effectiveMode, validateShell=theme.validateShell, normaliseShell=theme.normaliseShell, shellFromLayout=theme.shellFromLayout, shellTreeOf=theme.shellTreeOf, layoutVocabulary=theme.layoutVocabulary, validateBrand=theme.validateBrand, normaliseBrand=theme.normaliseBrand, brandOf=theme.brandOf, brandLogoFor=theme.brandLogoFor, fontChoices=theme.fontChoices, currentFontTryout=theme.currentFontTryout, applyFontTryout=theme.applyFontTryout;' }
      if (args.path === 'fastlanelabs/ui') return { contents: uiShim }
      if (args.path === 'dayjs') return { contents: 'export default globalThis.__FASTLANE_PLATFORM__.ui.dayjs;' }
      return { contents: 'export const api=globalThis.__FASTLANE_PLATFORM__.api;' }
    })
  }}],
})
writeFileSync('dist/frontend-contract.json', JSON.stringify({ api_version: 1, entry: 'app.js', css: 'app.css' }))
const { default: postcss } = await import('postcss')
const { default: tailwindcss } = await import('tailwindcss')
const css = await postcss([tailwindcss({
  presets: [preset], content: [resolve(cwd, 'src/**/*.{ts,tsx}')], corePlugins: { preflight: false },
})]).process('@tailwind utilities;', { from: undefined })
writeFileSync('dist/app.css', css.css)
