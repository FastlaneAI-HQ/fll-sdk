/** Pure theme v2 resolver: no DOM access. Mirrors fastlanelabs_sdk.themes (resolve_theme,
 *  upgrade_v1, project_v1, contrast_report); shared golden fixtures keep the two in step.
 *  Inputs are assumed valid: the server validates, and the editor validates before it applies. */
import registryData from './theme-registry.json'
import type { LayoutV2, ResolvedTheme, ThemeManifestV2 } from './theme-contract'
import type { LayoutNode, ThemeManifest, ThemePackPresentation } from './theme-pack-contract'

interface TokenSpec {
  name: string; layer: 'primitive' | 'semantic' | 'component'; type: string
  default: string | { dark: string; light: string }
  tone?: string; v1?: boolean; min?: number; max?: number; options?: string[]
}
interface Registry {
  registry_revision: number
  tokens: TokenSpec[]
  v1_tokens: string[]
  shades: number[]
  panel_sidebar_width: number
  layout_defaults: LayoutV2
  contrast_pairs: { id: string; fg: string; bg: string; min: number; level: 'error' | 'warning' }[]
  component_contrast_pairs: { id: string; fg: string; bg: string }[]
  nav_bars: { bar: 'sidebar' | 'navbar'; tone: string; bg: string }[]
  webfonts: { family: string; weights: number[] }[]
}
const registry = registryData as unknown as Registry
const index = new Map(registry.tokens.map(token => [token.name, token]))
const REF = /^\{([a-z][a-z0-9-]*)\}$/

export const REGISTRY_REVISION = registry.registry_revision
export const tokenSpecs = registry.tokens as readonly TokenSpec[]

const triplet = (color: string) => [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)).join(' ')
const isColor = (value: string) => /^#[0-9a-fA-F]{6}$/.test(value)

/** Follow `{ref}`s to the literal; every reference points at a token the theme sets. */
function flatten(theme: ThemeManifestV2): Record<string, string> {
  const raw: Record<string, string> = { ...theme.tokens.primitives, ...theme.tokens.semantic, ...theme.tokens.components }
  const out: Record<string, string> = {}
  const follow = (name: string): string => {
    if (!(name in out)) {
      const match = REF.exec(raw[name])
      out[name] = match ? follow(match[1]) : raw[name]
    }
    return out[name]
  }
  for (const name of Object.keys(raw)) follow(name)
  return out
}

function cssValue(spec: TokenSpec, literal: string, raw: string): string {
  if (spec.type === 'color') return triplet(literal)
  if (spec.type === 'font-size' && spec.layer === 'component') {
    const match = REF.exec(raw)
    return match ? `var(--fl-fs-${match[1].slice('size-'.length)})` : `calc(${literal} * var(--fl-size-scale, 1))`
  }
  return literal
}

export function resolveTheme(theme: ThemeManifest | ThemeManifestV2): ResolvedTheme {
  if (theme.api_version === 1) {
    return {
      api_version: 1,
      vars: Object.fromEntries(Object.entries(theme.tokens).map(([name, value]) => [`--fl-${name}`, isColor(value) ? triplet(value) : value])),
      attrs: { 'data-density': theme.layout.density, 'data-theme': theme.id },
      layout: { ...theme.layout }, shell: { attrs: {}, vars: {} }, fonts: [], enums: {},
    }
  }
  const resolved = flatten(theme)
  const vars: Record<string, string> = {}
  for (const layer of ['primitives', 'semantic', 'components'] as const) {
    for (const [name, raw] of Object.entries(theme.tokens[layer])) vars[`--fl-${name}`] = cssValue(index.get(name)!, resolved[name], raw)
  }
  const { sidebar, navbar, content } = theme.layout
  const step = (name: string) => (name === 'none' ? '0px' : `var(--fl-space-${name})`)
  const allow = new Map(registry.webfonts.map(font => [font.family.toLowerCase(), font]))
  const fonts: ResolvedTheme['fonts'] = []
  for (const name of ['font-sans', 'font-mono', 'font-display']) {
    const font = allow.get(resolved[name].split(',')[0].trim().replace(/^['"]|['"]$/g, '').toLowerCase())
    if (font && !fonts.some(item => item.family === font.family)) fonts.push({ family: font.family, weights: [...font.weights] })
  }
  return {
    api_version: 2, vars,
    attrs: { 'data-density': theme.layout.density, 'data-theme': theme.id, 'data-fl-contract': '2' },
    layout: JSON.parse(JSON.stringify(theme.layout)),
    shell: {
      attrs: {
        'data-fl-sidebar-side': sidebar.side, 'data-fl-sidebar-style': sidebar.style,
        'data-fl-sidebar-surface': sidebar.surface, 'data-fl-sidebar-behavior': sidebar.behavior,
        'data-fl-navbar': navbar.position, 'data-fl-navbar-behavior': navbar.behavior,
        'data-fl-navbar-align': navbar.align, 'data-fl-navbar-brand': navbar.show_brand ? 'true' : 'false',
        'data-fl-scroll': theme.layout.scroll, 'data-fl-content-align': content.align,
      },
      vars: {
        '--fl-sidebar-w': `${sidebar.width}px`, '--fl-sidebar-collapse-below': `${sidebar.collapse_below}px`,
        '--fl-navbar-h': `${navbar.height}px`,
        '--fl-content-max-w': content.max_width === 0 ? 'none' : `${content.max_width}px`,
        '--fl-content-pad': step(content.padding), '--fl-content-gap': step(content.gap),
      },
    },
    fonts,
    enums: Object.fromEntries(registry.tokens.filter(t => t.type === 'enum').map(t => [t.name, resolved[t.name] ?? (t.default as string)])),
  }
}

export function defaultThemeV2(id = 'fastlane', version = '2.0.0', label = 'Fastlane'): ThemeManifestV2 {
  const layer = (name: string) => Object.fromEntries(registry.tokens.filter(t => t.layer === name).map(t => [t.name, t.default as string]))
  return {
    api_version: 2, registry_revision: REGISTRY_REVISION, id, version, label, color_scheme: 'light',
    tokens: { primitives: layer('primitive'), semantic: layer('semantic'), components: {} },
    layout: JSON.parse(JSON.stringify(registry.layout_defaults)),
  }
}

export function defaultLayout(style: 'rail' | 'panel' = 'rail'): LayoutV2 {
  const layout: LayoutV2 = JSON.parse(JSON.stringify(registry.layout_defaults))
  layout.sidebar.style = style
  layout.sidebar.width = style === 'panel' ? registry.panel_sidebar_width : 56
  return layout
}

/** The 27 v1-named tokens in a v1 manifest, as the v2 layers they live in. */
const V1_COLOR_TOKENS = ['ink', 'accent'].flatMap(palette => registry.shades.map(shade => `${palette}-${shade}`))
const STYLE_TOKENS: Record<string, string> = {
  'page.header': 'page-header-variant', 'surface.card': 'card-variant', 'control.button': 'button-variant',
  'control.input': 'input-variant', 'control.field': 'field-variant', 'chat.message': 'chat-message-variant',
  'chat.composer': 'composer-variant',
}

type Trail = [LayoutNode, number][]
function slotTrails(node: LayoutNode, trail: Trail, out: Record<string, Trail>) {
  if (node.type === 'slot') { out[node.name] = trail; return }
  node.children.forEach((child, i) => slotTrails(child, [...trail, [node, i]], out))
}
function relation(trails: Record<string, Trail>, first: string, second: string): ['row' | 'column', boolean] {
  const a = trails[first], b = trails[second]
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i][0] === b[i][0] && a[i][1] !== b[i][1]) return [(a[i][0] as { type: 'row' | 'column' }).type, a[i][1] < b[i][1]]
  }
  return ['column', true]
}
function findSlot(node: LayoutNode, name: string): (LayoutNode & { type: 'slot' }) | undefined {
  if (node.type === 'slot') return node.name === name ? node : undefined
  for (const child of node.children) { const found = findSlot(child, name); if (found) return found }
  return undefined
}

export function upgradeV1Report(theme: ThemeManifest, presentation?: ThemePackPresentation | null): { theme: ThemeManifestV2; notes: string[] } {
  const notes = ['A v2 fork approximates the v1 original; compare them before publishing.']
  const result = defaultThemeV2(theme.id, theme.version, theme.label)
  const { primitives, semantic, components } = result.tokens
  for (const name of [...V1_COLOR_TOKENS, 'font-sans', 'font-mono', 'radius']) primitives[name] = theme.tokens[name]
  primitives['font-display'] = theme.tokens['font-sans']
  semantic['surface'] = theme.tokens['surface']
  semantic['on-primary'] = theme.tokens['on-primary']
  const layout = defaultLayout(theme.layout.navigation === 'sidebar' ? 'panel' : 'rail')
  layout.density = theme.layout.density
  result.layout = layout
  if (presentation) upgradePresentation(presentation, layout, components, notes)
  return { theme: result, notes }
}

function upgradePresentation(presentation: ThemePackPresentation, layout: LayoutV2, components: Record<string, string>, notes: string[]) {
  const styles = presentation.styles, workspace = presentation.workspace
  const trails: Record<string, Trail> = {}
  slotTrails(workspace, [], trails)
  const { sidebar, navbar, content } = layout
  sidebar.surface = 'flush'
  components['sidebar-radius'] = '0px'
  components['sidebar-border-width'] = '{border-width}'
  components['sidebar-brand-radius'] = '{radius-sm}'
  const nav = styles['navigation.sidebar']
  if (nav) {
    sidebar.style = nav.variant
    sidebar.width = nav.variant === 'panel' ? registry.panel_sidebar_width : 56
  }
  components['sidebar-tone'] = nav ? nav.tone : 'light'
  const topbar = styles['navigation.topbar']
  components['navbar-tone'] = topbar ? topbar.tone : 'light'
  // nav-item-fg is shared by both bars, so it is only pinned when they agree.
  if (components['sidebar-tone'] === 'dark' && components['navbar-tone'] === 'dark') components['nav-item-fg'] = '{ink-200}'
  let [kind, before] = relation(trails, 'navigation', 'content')
  if (kind === 'row') {
    sidebar.side = before ? 'left' : 'right'
    const slot = findSlot(workspace, 'navigation')
    if (slot && slot.width !== undefined) sidebar.width = slot.width
    ;[kind, before] = relation(trails, 'actions', 'content')
    navbar.position = before ? 'top' : 'bottom'
    if (kind === 'row') notes.push('The actions slot sits beside the content; it was mapped to a navbar at the top.')
  } else {
    // The navbar carries the navigation items, so it follows where the navigation sat.
    sidebar.side = 'hidden'
    navbar.position = before ? 'top' : 'bottom'
    notes.push('Navigation sits above or below the content, so it was mapped to a navbar that carries the navigation items and actions.')
  }
  if (workspace.type !== 'slot' && ['none', 'sm', 'md', 'lg'].includes(workspace.gap)) {
    content.gap = workspace.gap
    if (workspace.gap === 'lg') notes.push('Workspace gap lg (20px) was approximated by the lg step (16px).')
  }
  const item = styles['navigation.item']
  if (item) {
    components['nav-item-radius'] = item.variant === 'pill' ? '{radius-pill}' : '{radius-sm}'
    components['nav-item-variant'] = item.variant
  }
  for (const [key, token] of Object.entries(STYLE_TOKENS)) {
    const style = (styles as Record<string, { variant: string } | undefined>)[key]
    if (style) components[token] = style.variant
  }
  const button = styles['control.button']
  if (button) {
    Object.assign(components, {
      'button-height': '44px', 'button-weight': '{weight-semibold}', 'button-pad-x': '16px', 'button-size': '{size-base}',
      'button-radius': button.radius === 'square' ? '{radius-sm}' : '{radius}',
      'button-secondary-border': '{border-strong}', 'button-secondary-fg': '{ink-800}', 'button-secondary-hover-bg': '{ink-100}',
      'button-danger-border': '{danger-700}', 'button-danger-fg': '{danger-800}',
    })
  }
  if (styles['control.input']) Object.assign(components, { 'input-height': '44px', 'input-border': '{ink-400}', 'input-placeholder': '{ink-500}', 'input-size': '{size-base}' })
  if (styles['control.field']) {
    Object.assign(components, {
      'field-label-fg': '{ink-800}', 'field-label-size': '{size-base}', 'field-label-weight': '{weight-semibold}',
      'field-hint-fg': '{ink-600}', 'field-hint-size': '{size-sm}',
    })
  }
  if (styles['surface.card']) {
    Object.assign(components, { 'card-border': '{border-strong}', 'card-radius': '{radius}', 'card-title-size': '{size-base}' })
    if (styles['surface.card'].variant === 'raised') components['card-shadow'] = '{shadow-sm}'
  }
  if (styles['page.header']) components['page-header-rule-color'] = '{border-strong}'
  if (styles['chat.message']) Object.assign(components, { 'chat-message-user-bg': '{primary}', 'chat-message-user-radius': '{radius}' })
  notes.push('Layout, tones and component variants were mapped from presentation.json; unmapped details use registry defaults.')
}

export function upgradeV1(theme: ThemeManifest, presentation?: ThemePackPresentation | null): ThemeManifestV2 {
  return upgradeV1Report(theme, presentation).theme
}

/** The v1 manifest an old client can apply: 27 literal tokens, density and navigation. */
export function projectV1(theme: ThemeManifestV2): ThemeManifest {
  const tokens: Record<string, string> = {}
  for (const name of [...registry.v1_tokens].sort()) {
    tokens[name] = (index.get(name)!.layer === 'semantic' ? theme.tokens.semantic : theme.tokens.primitives)[name]
  }
  return {
    api_version: 1, id: theme.id, version: theme.version, label: theme.label, tokens,
    layout: { density: theme.layout.density, navigation: theme.layout.sidebar.style === 'panel' ? 'sidebar' : 'rail' },
  }
}

const luminance = (color: string) => {
  const linear = [1, 3, 5].map(i => {
    const c = parseInt(color.slice(i, i + 2), 16) / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722
}
export function contrastRatio(first: string, second: string): number {
  const [low, high] = [luminance(first), luminance(second)].sort((a, b) => a - b)
  return (high + 0.05) / (low + 0.05)
}

export interface ContrastRow {
  id: string; fg: string; bg: string; fg_value: string; bg_value: string
  ratio: number; min: number | null; level: 'error' | 'warning'; pass: boolean
}

/** Every contrast pair judged for a v2 theme (same rows as contrast_report in Python). */
export function contrastReport(theme: ThemeManifestV2): ContrastRow[] {
  const resolved = flatten(theme)
  const enumValue = (name: string) => resolved[name] ?? (index.get(name)!.default as string)
  const effective = (name: string, tone?: string, depth = 0): string | undefined => {
    if (name in resolved) return resolved[name]
    const spec = index.get(name)
    if (!spec || depth > 8) return undefined
    let fallback = spec.default
    if (typeof fallback !== 'string') fallback = fallback[(tone ?? enumValue(spec.tone!)) as 'dark' | 'light']
    const match = REF.exec(fallback)
    return match ? effective(match[1], tone, depth + 1) : fallback
  }
  const rows: ContrastRow[] = []
  const pair = (id: string, fgName: string, bgName: string, min: number, level: 'error' | 'warning', tone?: string) => {
    const fg = effective(fgName, tone), bg = effective(bgName, tone)
    if (!fg || !bg || !isColor(fg) || !isColor(bg)) return
    const ratio = contrastRatio(fg, bg)
    rows.push({ id, fg: fgName, bg: bgName, fg_value: fg, bg_value: bg, ratio: Math.round(ratio * 100) / 100, min, level, pass: ratio >= min })
  }
  for (const p of registry.contrast_pairs) pair(p.id, p.fg, p.bg, p.min, p.level)
  const { sidebar, navbar } = theme.layout
  const visible = { sidebar: sidebar.side !== 'hidden', navbar: navbar.position !== 'hidden' }
  for (const bar of registry.nav_bars) if (visible[bar.bar]) pair(`nav-item-fg-on-${bar.bg}`, 'nav-item-fg', bar.bg, 4.5, 'error', enumValue(bar.tone))
  if (visible.navbar) pair('navbar-fg-on-navbar-bg', 'navbar-fg', 'navbar-bg', 4.5, 'warning', enumValue('navbar-tone'))
  for (const p of registry.component_contrast_pairs) pair(p.id, p.fg, p.bg, 4.5, 'warning')
  return rows
}
