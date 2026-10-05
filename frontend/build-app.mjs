/** Build an independently installable app with the host's React instance. */
import { build } from 'esbuild'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
const cwd = process.cwd()
mkdirSync('dist', { recursive: true })
const reactExports = ['Children','Component','Fragment','Profiler','PureComponent','StrictMode','Suspense','cloneElement','createContext','createElement','createRef','forwardRef','isValidElement','lazy','memo','startTransition','useCallback','useContext','useDebugValue','useDeferredValue','useEffect','useId','useImperativeHandle','useInsertionEffect','useLayoutEffect','useMemo','useReducer','useRef','useState','useSyncExternalStore','useTransition','version']
await build({
  entryPoints: [resolve(cwd, 'src/index.tsx')], outfile: 'dist/app.js',
  nodePaths: [fileURLToPath(new URL('../node_modules', import.meta.url))],
  bundle: true, format: 'esm', platform: 'browser', target: 'es2020',
  jsx: 'automatic', minify: true,
  plugins: [{ name: 'platform-contract', setup(b) {
    b.onResolve({ filter: /^(react(?:\/jsx-runtime)?|fastlanelabs\/(?:api|ui|theme))$/ }, args => ({ path: args.path, namespace: 'platform' }))
    b.onLoad({ filter: /.*/, namespace: 'platform' }, args => {
      if (args.path === 'react') return { contents: `const r=globalThis.__FASTLANE_PLATFORM__.react; export default r; ${reactExports.map(name=>`export const ${name}=r.${name};`).join('')}` }
      if (args.path === 'react/jsx-runtime') return { contents: 'const r=globalThis.__FASTLANE_PLATFORM__.jsx; export const jsx=r.jsx, jsxs=r.jsxs, Fragment=r.Fragment;' }
      if (args.path === 'fastlanelabs/theme') return { contents: 'const theme=globalThis.__FASTLANE_PLATFORM__.theme; export const ThemeSlot=theme.ThemeSlot, ThemePreview=theme.ThemePreview, themeStyle=theme.themeStyle;' }
      if (args.path === 'fastlanelabs/ui') return { contents: 'const ui=globalThis.__FASTLANE_PLATFORM__.ui; export const Workspace=ui.Workspace, Sidebar=ui.Sidebar, Topbar=ui.Topbar, NavigationItem=ui.NavigationItem, Message=ui.Message, Composer=ui.Composer, Field=ui.Field, Button=ui.Button, Notice=ui.Notice, Input=ui.Input, Card=ui.Card, PageHeader=ui.PageHeader, inputClass=ui.inputClass;' }
      return { contents: 'export const api=globalThis.__FASTLANE_PLATFORM__.api;' }
    })
  }}],
})
writeFileSync('dist/frontend-contract.json', JSON.stringify({ api_version: 1, entry: 'app.js', css: 'app.css' }))
const { default: postcss } = await import('postcss')
const { default: tailwindcss } = await import('tailwindcss')
const shades = [50,100,200,300,400,500,600,700,800,900,950]
const palette = name => Object.fromEntries(shades.map(shade => [shade, `rgb(var(--fl-${name}-${shade}) / <alpha-value>)`]))
const css = await postcss([tailwindcss({
  content: [resolve(cwd, 'src/**/*.{ts,tsx}')], corePlugins: { preflight: false },
  theme: { extend: {
    colors: { ink: palette('ink'), accent: palette('accent') },
    backgroundColor: { white: 'rgb(var(--fl-surface) / <alpha-value>)' },
    textColor: { white: 'rgb(var(--fl-on-primary) / <alpha-value>)' },
    borderRadius: { lg: 'var(--fl-radius, 8px)', xl: 'calc(var(--fl-radius, 8px) * 1.5)', '2xl': 'calc(var(--fl-radius, 8px) * 2)' },
    fontFamily: { sans: ['var(--fl-font-sans)', 'system-ui'], mono: ['var(--fl-font-mono)', 'monospace'] },
  } },
})]).process('@tailwind utilities;', { from: undefined })
writeFileSync('dist/app.css', css.css)
