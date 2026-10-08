/** Pure theme v2 resolver: no DOM access. Mirrors fastlanelabs_sdk.themes (resolve_theme,
 *  upgrade_v1, project_v1, contrast_report); shared golden fixtures keep the two in step.
 *  Inputs are assumed valid: the server validates, and the editor validates before it applies. */
import registryData from './theme-registry.json'
import type { ColorMode, ColorScheme, LayoutV2, ResolvedTheme, ThemeManifestV2, TokenLayers } from './theme-contract'
import type { LayoutNode, ThemeManifest, ThemePackPresentation } from './theme-pack-contract'

interface TokenSpec {
  name: string; layer: 'primitive' | 'semantic' | 'component'; type: string
  default: string | { dark: string; light: string }
  tone?: string; v1?: boolean; min?: number; max?: number; options?: string[]
  since?: number; optional?: boolean
}
interface Registry {
  registry_revision: number
  tokens: TokenSpec[]
  /** The palette a new theme starts from, by registry revision (a token's `default` is the CSS fallback and never changes). */
  revision_defaults: Record<string, Record<string, string>>
  v1_tokens: string[]
  shades: number[]
  panel_sidebar_width: number
  layout_defaults: LayoutV2
  contrast_pairs: { id: string; fg: string; bg: string; min: number; level: 'error' | 'warning'; since: number; group?: string; unless?: string }[]
  component_contrast_pairs: { id: string; fg: string; bg: string }[]
  nav_bars: { bar: 'sidebar' | 'navbar'; tone: string; bg: string }[]
  webfonts: { family: string; weights: number[] }[]
  modes: { names: string[]; since: number; overridable: string[]; required: string[]; ramps: string[] }
  hues: Record<string, string[]>
  black: { light: string; dark: string }
}
const registry = registryData as unknown as Registry
const index = new Map(registry.tokens.map(token => [token.name, token]))
const REF = /^\{([a-z][a-z0-9-]*)\}$/

export const REGISTRY_REVISION = registry.registry_revision
export const tokenSpecs = registry.tokens as readonly TokenSpec[]

const triplet = (color: string) => [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)).join(' ')
const isColor = (value: string) => /^#[0-9a-fA-F]{6}$/.test(value)

const LAYERS = ['primitives', 'semantic', 'components'] as const

/** The modes a theme offers: light only, dark only, or both (a v1 theme offers light). */
export function offeredModes(theme: { api_version: number; color_scheme?: ColorScheme }): ColorMode[] {
  if (theme.api_version !== 2) return ['light']
  return theme.color_scheme === 'dark' ? ['dark'] : theme.color_scheme === 'auto' ? ['light', 'dark'] : ['light']
}

/** The mode to show: the only one a theme offers, else the user's choice (`system`/undefined follows the OS). */
export function effectiveMode(theme: { api_version: number; color_scheme?: ColorScheme }, preference?: string | null, systemDark = false): ColorMode {
  const offered = offeredModes(theme)
  if (offered.length === 1) return offered[0]
  if (preference === 'light' || preference === 'dark') return preference
  return systemDark ? 'dark' : 'light'
}

/** Every token the theme sets, with modes.dark applied when the dark palette of an auto theme is wanted. */
function rawTokens(theme: ThemeManifestV2, mode: ColorMode): Record<string, string> {
  const raw: Record<string, string> = { ...theme.tokens.primitives, ...theme.tokens.semantic, ...theme.tokens.components }
  if (mode === 'dark' && theme.color_scheme === 'auto' && theme.modes) {
    for (const layer of LAYERS) Object.assign(raw, theme.modes.dark[layer])
  }
  return raw
}

/** Follow `{ref}`s to the literal; every reference points at a token the theme sets. */
function flatten(theme: ThemeManifestV2, mode: ColorMode = 'light'): Record<string, string> {
  return flattenRaw(rawTokens(theme, mode))
}

function flattenRaw(raw: Record<string, string>): Record<string, string> {
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

export function resolveTheme(theme: ThemeManifest | ThemeManifestV2, mode?: ColorMode | null): ResolvedTheme {
  if (theme.api_version === 1) {
    return {
      api_version: 1,
      vars: Object.fromEntries(Object.entries(theme.tokens).map(([name, value]) => [`--fl-${name}`, isColor(value) ? triplet(value) : value])),
      attrs: { 'data-density': theme.layout.density, 'data-theme': theme.id },
      layout: { ...theme.layout }, shell: { attrs: {}, vars: {} }, fonts: [], enums: {},
    }
  }
  const scheme = theme.color_scheme ?? 'light'
  const chosen = effectiveMode(theme, mode)
  const raw = rawTokens(theme, chosen)
  const resolved = flattenRaw(raw)
  const vars: Record<string, string> = {}
  for (const [name, content] of Object.entries(raw)) vars[`--fl-${name}`] = cssValue(index.get(name)!, resolved[name], content)
  const { sidebar, navbar, content } = theme.layout
  const step = (name: string) => (name === 'none' ? '0px' : `var(--fl-space-${name})`)
  const allow = new Map(registry.webfonts.map(font => [font.family.toLowerCase(), font]))
  const fonts: ResolvedTheme['fonts'] = []
  for (const name of ['font-sans', 'font-mono', 'font-display']) {
    const font = allow.get(resolved[name].split(',')[0].trim().replace(/^['"]|['"]$/g, '').toLowerCase())
    if (font && !fonts.some(item => item.family === font.family)) fonts.push({ family: font.family, weights: [...font.weights] })
  }
  const attrs: Record<string, string> = { 'data-density': theme.layout.density, 'data-theme': theme.id, 'data-fl-contract': '2' }
  const result: ResolvedTheme = {
    api_version: 2, vars, attrs,
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
  if (scheme !== 'light') {
    attrs['data-fl-mode'] = chosen
    result.scheme = { offered: offeredModes(theme), mode: chosen }
  }
  return result
}

/** The default of a token for a new theme that targets `revision` (the current one when omitted). */
export function defaultFor(spec: TokenSpec, revision = REGISTRY_REVISION): string | { dark: string; light: string } {
  let value = spec.default
  for (const step of Object.keys(registry.revision_defaults).map(Number).sort((a, b) => a - b)) {
    if (step <= revision && spec.name in registry.revision_defaults[String(step)]) value = registry.revision_defaults[String(step)][spec.name]
  }
  return value
}

export function defaultThemeV2(id = 'fastlane', version = '2.0.0', label = 'Fastlane', scheme: ColorScheme = 'light', registryRevision = REGISTRY_REVISION): ThemeManifestV2 {
  const layer = (name: string) => Object.fromEntries(registry.tokens.filter(t => t.layer === name && (t.since ?? 1) <= registryRevision).map(t => [t.name, defaultFor(t, registryRevision) as string]))
  const theme: ThemeManifestV2 = {
    api_version: 2, registry_revision: registryRevision, id, version, label, color_scheme: 'light',
    tokens: { primitives: layer('primitive'), semantic: layer('semantic'), components: {} },
    layout: JSON.parse(JSON.stringify(registry.layout_defaults)),
  }
  if (scheme !== 'light') {
    if (registryRevision < 2) throw new Error('Dark mode needs registry revision 2')
    const dark = deriveDark(theme)
    theme.color_scheme = scheme
    if (scheme === 'auto') theme.modes = { dark }
    else for (const key of LAYERS) Object.assign(theme.tokens[key], dark[key])
  }
  return theme
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

export function upgradeV1Report(theme: ThemeManifest, presentation?: ThemePackPresentation | null, registryRevision = REGISTRY_REVISION): { theme: ThemeManifestV2; notes: string[] } {
  const notes = ['A v2 fork approximates the v1 original; compare them before publishing.']
  const result = defaultThemeV2(theme.id, theme.version, theme.label, 'light', registryRevision)
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

export function upgradeV1(theme: ThemeManifest, presentation?: ThemePackPresentation | null, registryRevision = REGISTRY_REVISION): ThemeManifestV2 {
  return upgradeV1Report(theme, presentation, registryRevision).theme
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
  /** `ui` for a pair the interface really paints with (registry revision 3); absent for the role pairs. */
  group?: string
  /** Present only for a theme with a dark palette. */
  mode?: ColorMode
}

/** Every contrast pair judged for a v2 theme (same rows as contrast_report in Python): a light-only
 *  theme's rows as registry revision 1 produced them, a theme with a dark palette also its dark rows. */
export function contrastReport(theme: ThemeManifestV2): ContrastRow[] {
  const scheme = theme.color_scheme ?? 'light'
  if (scheme === 'light') return contrastRows(theme, 'light', false)
  if (scheme === 'dark') return contrastRows(theme, 'dark', true)
  return [...contrastRows(theme, 'light', true), ...contrastRows(theme, 'dark', true)]
}

function contrastRows(theme: ThemeManifestV2, mode: ColorMode, label: boolean): ContrastRow[] {
  const revision = theme.registry_revision
  const resolved = flatten(theme, mode)
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
  const pair = (id: string, fgName: string, bgName: string, min: number, level: 'error' | 'warning', tone?: string, group?: string) => {
    const fg = effective(fgName, tone), bg = effective(bgName, tone)
    if (!fg || !bg || !isColor(fg) || !isColor(bg)) return
    const ratio = contrastRatio(fg, bg)
    const row: ContrastRow = { id, fg: fgName, bg: bgName, fg_value: fg, bg_value: bg, ratio: Math.round(ratio * 100) / 100, min, level, pass: ratio >= min }
    if (group) row.group = group
    if (label) row.mode = mode
    rows.push(row)
  }
  // A pair is judged only for a theme that targets the revision that introduced it; `unless` names a role that replaces it.
  for (const p of registry.contrast_pairs) {
    if (p.since <= revision && !(p.unless && p.unless in resolved)) pair(p.id, p.fg, p.bg, p.min, p.level, undefined, p.group)
  }
  const { sidebar, navbar } = theme.layout
  const visible = { sidebar: sidebar.side !== 'hidden', navbar: navbar.position !== 'hidden' }
  for (const bar of registry.nav_bars) if (visible[bar.bar]) pair(`nav-item-fg-on-${bar.bg}`, 'nav-item-fg', bar.bg, 4.5, 'error', enumValue(bar.tone))
  if (visible.navbar) pair('navbar-fg-on-navbar-bg', 'navbar-fg', 'navbar-bg', 4.5, 'warning', enumValue('navbar-tone'))
  for (const p of registry.component_contrast_pairs) pair(p.id, p.fg, p.bg, 4.5, 'warning')
  return rows
}

// --- Dark palette derivation: the same arithmetic as themes.derive_dark, step for step. -------------

const channels = (color: string): [number, number, number] => [parseInt(color.slice(1, 3), 16), parseInt(color.slice(3, 5), 16), parseInt(color.slice(5, 7), 16)]
const toHex = (r: number, g: number, b: number) => '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('')
const midpoint = (first: string, second: string) => {
  const a = channels(first), b = channels(second)
  return toHex(...([0, 1, 2].map(i => Math.floor((a[i] + b[i] + 1) / 2)) as [number, number, number]))
}

function hueChannel(p: number, q: number, t: number) {
  if (t < 0) t += 1
  if (t > 1) t -= 1
  if (t < 1 / 6) return p + (q - p) * 6 * t
  if (t < 1 / 2) return q
  if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
  return p
}

/** The same hue and saturation with lightness 1 - L (HSL). */
function reflectLightness(color: string): string {
  const [r, g, b] = channels(color).map(c => c / 255)
  const high = Math.max(r, g, b), low = Math.min(r, g, b)
  let lightness = (high + low) / 2
  let hue = 0, saturation = 0
  if (high !== low) {
    const delta = high - low
    saturation = lightness > 0.5 ? delta / (2 - high - low) : delta / (high + low)
    if (high === r) hue = ((g - b) / delta + (g < b ? 6 : 0)) / 6
    else if (high === g) hue = ((b - r) / delta + 2) / 6
    else hue = ((r - g) / delta + 4) / 6
  }
  lightness = 1 - lightness
  let values: number[]
  if (saturation === 0) values = [lightness, lightness, lightness]
  else {
    const q = lightness < 0.5 ? lightness * (1 + saturation) : lightness + saturation - lightness * saturation
    const p = 2 * lightness - q
    values = [hueChannel(p, q, hue + 1 / 3), hueChannel(p, q, hue), hueChannel(p, q, hue - 1 / 3)]
  }
  const [x, y, z] = values.map(v => Math.floor(v * 255 + 0.5))
  return toHex(x, y, z)
}

const percent = (hundredths: number) => {
  const whole = Math.floor(hundredths / 100), part = hundredths % 100
  return part ? `${whole}.${String(part).padStart(2, '0')}`.replace(/0+$/, '') : String(whole)
}

/** Stronger, black shadows: a shadow that reads on white vanishes on a dark surface. */
function boostShadow(text: string): string {
  return text.replace(/rgba\( *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]{1,3}) *, *([0-9]*\.?[0-9]+) *\)/g,
    (_all, _r, _g, _b, alpha) => `rgba(0,0,0,${percent(Math.min(Math.floor(parseFloat(alpha) * 2.5 * 100 + 0.5), 85))})`)
}

/** `color` moved toward `target` in tenths until it reaches `minimum`:1 against `against` (or is `target`). */
function moveUntil(color: string, target: string, against: string, minimum: number): string {
  if (contrastRatio(color, against) >= minimum) return color
  const from = channels(color), to = channels(target)
  for (let tenth = 1; tenth <= 10; tenth++) {
    const moved = toHex(...([0, 1, 2].map(i => Math.floor((from[i] * (10 - tenth) + to[i] * tenth + 5) / 10)) as [number, number, number]))
    if (contrastRatio(moved, against) >= minimum) return moved
  }
  return target
}

/** `color` moved toward white in whole percents until it reaches `minimum`:1 against every background. */
function lightenUntil(color: string, backgrounds: string[], minimum: number): string {
  return lightenUntilAll(color, backgrounds.map(background => [background, minimum] as [string, number]))
}

/** `color` moved toward white in whole percents until it has each background's own minimum contrast. */
function lightenUntilAll(color: string, needs: [string, number][]): string {
  if (needs.every(([background, minimum]) => contrastRatio(color, background) >= minimum)) return color
  const from = channels(color)
  for (let percent = 1; percent <= 100; percent++) {
    const moved = toHex(...([0, 1, 2].map(i => Math.floor((from[i] * (100 - percent) + 255 * percent + 50) / 100)) as [number, number, number]))
    if (needs.every(([background, minimum]) => contrastRatio(moved, background) >= minimum)) return moved
  }
  return '#ffffff'
}

/** The ink steps the interface paints text and icons with, and the least contrast each may have on a dark surface. */
export const DARK_TEXT_STEPS: readonly [number, number][] = [[300, 3.0], [400, 4.5], [500, 4.5], [600, 4.5], [700, 4.5]]

/** The dark accent tints the interface prints a text step on (a selected row, a chip, a tile). Revision 3 and later. */
export const DARK_TEXT_TINTS: Record<number, readonly string[]> = {
  400: ['accent-50'], 500: ['accent-50', 'accent-100'], 600: ['accent-50', 'accent-100'], 700: ['accent-50', 'accent-100'],
}

/** How far a dark tint may be darkened to carry its text steps: its contrast against the dark surface stays at least this. */
export const DARK_TINT_FLOORS: Record<string, number> = { 'accent-50': 1.15, 'accent-100': 1.3 }

/** `color` moved toward black by `percent`: hue and saturation kept, every channel scaled. */
function darken(color: string, percent: number): string {
  const from = channels(color)
  return toHex(...([0, 1, 2].map(i => Math.floor((from[i] * (100 - percent) + 50) / 100)) as [number, number, number]))
}

/** Darken a dark accent tint, in place, until the text steps printed on it reach their minimum there, but no further than
 *  DARK_TINT_FLOORS from the surface and, with `cap`, never as light as `cap`. */
function settleTint(primitives: Record<string, string>, tint: string, surface: string, cap?: string): void {
  const steps = Object.entries(DARK_TEXT_TINTS).filter(([, tints]) => tints.includes(tint)).map(([shade]) => Number(shade))
  const start = primitives[tint]
  let best = start
  for (let percent = 0; percent <= 100; percent++) {
    const moved = percent ? darken(start, percent) : start
    if (percent && contrastRatio(moved, surface) < DARK_TINT_FLOORS[tint]) break
    best = moved
    if (steps.every(shade => contrastRatio(primitives[`ink-${shade}`], moved) >= 4.5)) break
  }
  if (cap !== undefined && luminance(best) >= luminance(cap) * 0.93) {
    for (let percent = 0; percent <= 100; percent++) {
      best = darken(start, percent)
      if (luminance(best) < luminance(cap) * 0.93) break
    }
  }
  primitives[tint] = best
}

/** Re-solve the dark ramp's text steps against the dark surface, the page and the dark accent tints, in place (registry
 *  revision 3 and later): the surface and page first, then the tints are settled, then what is still short is lifted. */
export function solveDarkText(primitives: Record<string, string>, lightRatios: Record<number, number>, surface: string, page: string): void {
  const wanted: Record<number, number> = {}
  for (const [shade, minimum] of DARK_TEXT_STEPS) wanted[shade] = Math.max(minimum, lightRatios[shade] ?? minimum)
  for (const [shade] of DARK_TEXT_STEPS) {
    const name = `ink-${shade}`
    primitives[name] = lightenUntilAll(primitives[name], [[surface, wanted[shade]], [page, wanted[shade]]])
  }
  settleTint(primitives, 'accent-100', surface)
  settleTint(primitives, 'accent-50', surface, primitives['accent-100'])
  for (const [shade, minimum] of DARK_TEXT_STEPS) {
    const name = `ink-${shade}`
    const needs: [string, number][] = [[surface, wanted[shade]], [page, wanted[shade]], ...(DARK_TEXT_TINTS[shade] ?? []).map(tint => [primitives[tint], minimum] as [string, number])]
    primitives[name] = lightenUntilAll(primitives[name], needs)
  }
}

/** The `modes.dark` block derived from a v2 theme's own (light) tokens: every ramp reversed, the
 *  surface between the page and ink-100, readable `on-primary`, a dark scrim, stronger shadows and the
 *  `light` bar tone (the dark-looking one on reversed ramps). Complete in color, sparse elsewhere. */
export function deriveDark(theme: { tokens: TokenLayers; registry_revision?: number }): TokenLayers {
  const tokens = theme.tokens
  const revision = typeof theme.registry_revision === 'number' ? theme.registry_revision : 1
  const primitives: Record<string, string> = {}
  const rampStep = new Map<string, string>()
  for (const palette of registry.modes.ramps) {
    const light = registry.shades.map(shade => tokens.primitives[`${palette}-${shade}`])
    registry.shades.forEach((shade, i) => { primitives[`${palette}-${shade}`] = light[light.length - 1 - i] })
    registry.shades.forEach((shade, i) => { const key = light[i].toLowerCase(); if (!rampStep.has(key)) rampStep.set(key, `${palette}-${shade}`) })
  }
  for (const spec of registry.tokens) {
    if (spec.layer === 'primitive' && spec.type === 'shadow' && spec.name in tokens.primitives) primitives[spec.name] = boostShadow(tokens.primitives[spec.name])
  }
  const mapped = (color: string) => { const step = rampStep.get(color.toLowerCase()); return step ? primitives[step] : reflectLightness(color) }
  const overridable = new Set(registry.modes.overridable)
  const semantic: Record<string, string> = { surface: midpoint(primitives['ink-50'], primitives['ink-100']), scrim: '#000000' }
  const components: Record<string, string> = { 'sidebar-tone': 'light', 'navbar-tone': 'light', 'modal-scrim-alpha': '0.6', 'drawer-scrim-alpha': '0.6' }
  for (const [layer, out] of [['semantic', semantic], ['components', components]] as const) {
    for (const [name, value] of Object.entries(tokens[layer])) {
      const spec = index.get(name)!
      if (overridable.has(name) && spec.type === 'color' && /^#[0-9a-fA-F]{6}$/.test(value) && !['surface', 'on-primary', 'scrim'].includes(name)) out[name] = mapped(value)
      else if (spec.type === 'shadow' && !REF.test(value) && value !== 'none') out[name] = boostShadow(value)
    }
  }
  for (const [name, value] of [['nav-item-active-bg', '{ink-200}'], ['nav-item-active-fg', '{text}'], ['chat-message-user-bg', '{ink-200}'],
    ['chat-message-user-fg', '{text}'], ['input-placeholder', '{ink-500}']]) {
    if (!(name in tokens.components)) components[name] = value
  }
  // Text a theme set as `{text-inverse}` sits on a fill that is now a quiet dark one, so it becomes the plain text colour.
  for (const [name, fill] of [['navbar-fg', null], ['nav-item-hover-fg', null], ['nav-item-active-fg', 'nav-item-active-bg'], ['chat-message-user-fg', 'chat-message-user-bg']] as const) {
    if (tokens.components[name] === '{text-inverse}' && (fill === null || !(fill in tokens.components))) components[name] = '{text}'
  }
  for (const bar of ['sidebar', 'navbar']) if (`${bar}-bg` in tokens.components) components[`${bar}-bg`] = '{surface}'
  // A reversed accent can land mid-way, too dark to read as a link or too light for white text. The steps the
  // theme's own roles point at are moved toward white or black, in tenths, until the validator's pairs hold.
  const surface = semantic['surface']
  const steps: Record<string, string> = {}
  for (const role of ['text-link', 'focus-ring', 'primary']) {
    const match = REF.exec(tokens.semantic[role] ?? '')
    if (match && match[1] in primitives && index.get(match[1])!.type === 'color') steps[role] = match[1]
  }
  for (const [role, minimum] of [['text-link', 4.5], ['focus-ring', 3.0]] as const) {
    if (role in steps) primitives[steps[role]] = moveUntil(primitives[steps[role]], '#ffffff', surface, minimum)
  }
  if (revision >= 3) {
    const lightSurface = flattenRaw({ ...tokens.primitives, ...tokens.semantic, ...tokens.components })['surface']
    const lightRatios: Record<number, number> = {}
    for (const [shade] of DARK_TEXT_STEPS) lightRatios[shade] = contrastRatio(tokens.primitives[`ink-${shade}`], lightSurface)
    solveDarkText(primitives, lightRatios, surface, primitives['ink-50'])
    // The brand as text and as an indicator: the step the role points at moves toward white until it reads on the dark
    // surface and on the (dark) tint behind a chip.
    for (const [role, minimum] of [['accent-text', 4.5], ['accent-ui', 3.0]] as const) {
      const match = REF.exec(tokens.semantic[role] ?? '')
      if (match && match[1].startsWith('accent-') && match[1] in primitives) {
        primitives[match[1]] = lightenUntil(primitives[match[1]], role === 'accent-text' ? [surface, primitives['accent-50']] : [surface], minimum)
      }
    }
  }
  // Text on the primary color: the darker or the lighter end of the dark ramp, whichever reads better.
  const primary = flattenRaw({ ...tokens.primitives, ...tokens.semantic, ...tokens.components, ...primitives, ...semantic, ...components })['primary']
  const ends = [primitives['ink-50'], primitives['ink-950']]
  const end = contrastRatio(ends[1], primary) > contrastRatio(ends[0], primary) ? ends[1] : ends[0]
  const toward = end === ends[0] ? '#ffffff' : '#000000'
  for (const name of [...new Set(['accent-600', ...('primary' in steps ? [steps['primary']] : [])])].sort()) {
    primitives[name] = moveUntil(primitives[name], toward, end, 4.5)
  }
  semantic['on-primary'] = end
  return { primitives, semantic, components }
}
