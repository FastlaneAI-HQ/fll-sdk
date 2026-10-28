/** Pure theme v2 resolver: no DOM access. Mirrors fastlanelabs_sdk.themes (resolve_theme,
 *  contrast_report, derive_dark, validate_shell, normalise_shell, shell_from_layout, validate_brand); shared golden fixtures keep the two in step.
 *  Inputs are assumed valid: the server validates, and the editor validates before it applies. */
import registryData from './theme-registry.json'
import vocabularyData from './layout-vocabulary.json'
import type {
  ColorMode, ColorScheme, LayoutV2, LayoutVocabulary, ResolvedShellContainer, ResolvedShellNode, ResolvedShellRegion, ResolvedShellTree,
  BrandImage, BrandLogoLimits, ResolvedBrand, ResolvedTheme, ShellProblem, ShellSize, ShellTree, ThemeBrand, ThemeManifestV2, TokenLayers,
} from './theme-contract'

interface TokenSpec {
  name: string; layer: 'primitive' | 'semantic' | 'component'; type: string
  default: string | { dark: string; light: string }
  tone?: string; v1?: boolean; min?: number; max?: number; options?: string[]
  optional?: boolean
}
interface Registry {
  registry_revision: number
  tokens: TokenSpec[]
  /** The palette a new theme starts from where it differs from a token's `default` (the CSS fallback). */
  new_theme_defaults: Record<string, string>
  shades: number[]
  panel_sidebar_width: number
  layout_defaults: LayoutV2
  layout: { content: { max_width: { max: number } } }
  contrast_pairs: { id: string; fg: string; bg: string; min: number; level: 'error' | 'warning'; group?: string; unless?: string }[]
  component_contrast_pairs: { id: string; fg: string; bg: string }[]
  nav_bars: { bar: 'sidebar' | 'navbar'; tone: string; bg: string }[]
  webfonts: { family: string; weights: number[] }[]
  modes: { names: string[]; overridable: string[]; required: string[]; ramps: string[] }
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

/** The modes a theme offers: light only, dark only, or both. */
export function offeredModes(theme: { color_scheme?: ColorScheme }): ColorMode[] {
  return theme.color_scheme === 'dark' ? ['dark'] : theme.color_scheme === 'auto' ? ['light', 'dark'] : ['light']
}

/** The mode to show: the only one a theme offers, else the user's choice (`system`/undefined follows the OS). */
export function effectiveMode(theme: { color_scheme?: ColorScheme }, preference?: string | null, systemDark = false): ColorMode {
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

/** What the host applies for a theme. `shell.tree` is the normalised layout tree (see `shellTreeOf`); `shell.attrs` and `shell.vars`
 *  are the classic data-* attributes and variables of the layout options. */
export function resolveTheme(theme: ThemeManifestV2, mode?: ColorMode | null, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedTheme {
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
      tree: shellTreeOf(theme, vocabulary),
    },
    brand: brandOf(theme, vocabulary),
    fonts,
    enums: Object.fromEntries(registry.tokens.filter(t => t.type === 'enum').map(t => [t.name, resolved[t.name] ?? (t.default as string)])),
  }
  if (scheme !== 'light') {
    attrs['data-fl-mode'] = chosen
    result.scheme = { offered: offeredModes(theme), mode: chosen }
  }
  return result
}

/** The default of a token for a new theme. */
export function defaultFor(spec: TokenSpec): string | { dark: string; light: string } {
  return registry.new_theme_defaults[spec.name] ?? spec.default
}

export function defaultThemeV2(id = 'fastlane', version = '2.0.0', label = 'Fastlane', scheme: ColorScheme = 'light'): ThemeManifestV2 {
  const layer = (name: string) => Object.fromEntries(registry.tokens.filter(t => t.layer === name).map(t => [t.name, defaultFor(t) as string]))
  const theme: ThemeManifestV2 = {
    api_version: 2, registry_revision: REGISTRY_REVISION, id, version, label, color_scheme: 'light',
    tokens: { primitives: layer('primitive'), semantic: layer('semantic'), components: {} },
    layout: JSON.parse(JSON.stringify(registry.layout_defaults)),
  }
  if (scheme !== 'light') {
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

// --- Layout tree: the same rules as themes.validate_shell, step for step. ---------------------------
//
// docs/layout-tree.md is the specification; every limit, enum, default and region option is read from the layout
// vocabulary (layout-vocabulary.json), so a newer vocabulary changes what is accepted without a code change. Messages,
// paths and their ORDER match the Python twin: tests/test_layout_tree_parity.py runs both over the same trees.

/** The built-in layout vocabulary (a generated copy of the Themes app's file). A host with a newer one passes it instead. */
export const layoutVocabulary = vocabularyData as unknown as LayoutVocabulary

/** size.min and size.max may be this large on the content path: the range of layout.content.max_width (the vocabulary may
 *  say otherwise with limits.content_path_px.max). */
export const CONTENT_PATH_MAX_PX = registry.layout.content.max_width.max
const SHELL_KINDS = ['container', 'region', 'spacer']

type Obj = Record<string, unknown>
const isObject = (value: unknown): value is Obj => typeof value === 'object' && value !== null && !Array.isArray(value)
const has = (owner: object, key: string) => Object.prototype.hasOwnProperty.call(owner, key)
const isInt = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value)
const enumMessage = (options: string[]) => 'Must be one of ' + options.join(', ')
const rangeMessage = (low: number, high: number) => `Must be a whole number ${low}-${high}`
const contentPathMax = (vocabulary: LayoutVocabulary) => vocabulary.limits.content_path_px?.max ?? CONTENT_PATH_MAX_PX

class ShellCheck {
  nodes = 0
  stopped = false
  readonly limits: LayoutVocabulary['limits']
  constructor(readonly vocab: LayoutVocabulary, readonly errors: ShellProblem[]) { this.limits = vocab.limits }

  node(node: unknown, path: string, depth: number): void {
    const limits = this.limits
    if (this.stopped) return
    if (depth > limits.max_depth) { this.errors.push({ path, message: `A shell is at most ${limits.max_depth} levels deep` }); return }
    this.nodes += 1
    if (this.nodes > limits.max_nodes) { this.errors.push({ path, message: `A shell has at most ${limits.max_nodes} nodes` }); this.stopped = true; return }
    if (!isObject(node)) { this.errors.push({ path, message: 'A node must be an object' }); return }
    const kind = node.type
    if (depth === 1 && kind !== 'container') { this.errors.push({ path, message: 'The root of a shell must be a container' }); return }
    if (typeof kind !== 'string' || !SHELL_KINDS.includes(kind)) {
      this.errors.push({ path: `${path}.type`, message: 'type must be ' + SHELL_KINDS.slice(0, -1).join(', ') + ' or ' + SHELL_KINDS[SHELL_KINDS.length - 1] })
      return
    }
    if (kind === 'container') this.container(node, path, depth)
    else if (kind === 'region') this.region(node, path)
    else this.unknown(node, path, ['type'])
  }

  unknown(node: Obj, path: string, allowed: string[]): void {
    for (const key of Object.keys(node).filter(k => !allowed.includes(k)).sort()) this.errors.push({ path: `${path}.${key}`, message: `Unknown key ${key}` })
  }

  container(node: Obj, path: string, depth: number): void {
    const spec = this.vocab.container
    this.unknown(node, path, ['type', 'size', 'children', ...Object.keys(spec)])
    for (const [name, field] of Object.entries(spec)) this.field(node, name, field, `${path}.${name}`)
    if (has(node, 'size')) this.size(node.size, `${path}.size`)
    const children = node.children
    const high = this.limits.max_children
    if (!Array.isArray(children) || children.length < 1 || children.length > high) {
      this.errors.push({ path: `${path}.children`, message: `A container has 1 to ${high} children` })
      return
    }
    children.forEach((child, index) => this.node(child, `${path}.children[${index}]`, depth + 1))
  }

  /** One container field, by the vocabulary's own description of it (enum, step or int). */
  field(owner: Obj, name: string, field: LayoutVocabulary['container'][string], path: string): void {
    if (!has(owner, name)) {
      if (!has(field, 'default') && !field.optional) this.errors.push({ path, message: 'Required' })
      return
    }
    const value = owner[name]
    if (field.enum) {
      if (typeof value !== 'string' || !field.enum.includes(value)) this.errors.push({ path, message: enumMessage(field.enum) })
    } else if (field.step) {
      if (typeof value !== 'string' || !this.vocab.steps.includes(value)) this.errors.push({ path, message: enumMessage(this.vocab.steps) })
    } else if (field.int) {
      const bounds = (this.limits as unknown as Record<string, { min: number; max: number }>)[name]
      if (!isInt(value) || value < bounds.min || value > bounds.max) this.errors.push({ path, message: rangeMessage(bounds.min, bounds.max) })
    }
  }

  size(size: unknown, path: string): void {
    if (!isObject(size)) { this.errors.push({ path, message: 'size must be an object' }); return }
    this.unknown(size, path, ['basis', 'min', 'max'])
    const px = this.limits.size_px
    const bases = this.vocab.size.bases
    const named = bases.filter(base => base !== 'px')
    if (!has(size, 'basis')) this.errors.push({ path: `${path}.basis`, message: 'Required' })
    else {
      const basis = size.basis
      const valid = (typeof basis === 'string' && named.includes(basis)) || (bases.includes('px') && isInt(basis) && basis >= px.min && basis <= px.max)
      if (!valid) this.errors.push({ path: `${path}.basis`, message: 'Must be ' + named.join(', ') + ` or a whole number of px ${px.min}-${px.max}` })
    }
    const high = contentPathMax(this.vocab)
    const good: Record<string, number> = {}
    for (const key of ['min', 'max']) {
      if (!has(size, key)) continue
      const value = size[key]
      if (isInt(value) && value >= px.min && value <= high) good[key] = value
      else this.errors.push({ path: `${path}.${key}`, message: rangeMessage(px.min, high) })
    }
    if ('min' in good && 'max' in good && good.min > good.max) this.errors.push({ path: `${path}.max`, message: 'max must be at least min' })
  }

  region(node: Obj, path: string): void {
    this.unknown(node, path, ['type', 'region', 'size', 'options'])
    const regions = this.vocab.regions
    const name = node.region
    const known = typeof name === 'string' && has(regions, name)
    if (!has(node, 'region')) this.errors.push({ path: `${path}.region`, message: 'Required' })
    else if (!known) {
      const names = Object.keys(regions)
      this.errors.push({ path: `${path}.region`, message: 'region must be ' + names.slice(0, -1).join(', ') + ' or ' + names[names.length - 1] })
    }
    if (has(node, 'size')) this.size(node.size, `${path}.size`)
    if (!known) return
    const spec = regions[name as string].options
    const given = has(node, 'options') ? node.options : {}
    if (has(node, 'options') && !isObject(given)) { this.errors.push({ path: `${path}.options`, message: 'options must be an object' }); return }
    for (const key of Object.keys(given as Obj).filter(k => !has(spec, k)).sort()) this.errors.push({ path: `${path}.options.${key}`, message: `Unknown option ${key}` })
    for (const [option, field] of Object.entries(spec)) this.option(given as Obj, option, field, `${path}.options.${option}`)
  }

  option(given: Obj, name: string, field: LayoutVocabulary['regions'][string]['options'][string], path: string): void {
    if (!has(given, name)) {
      if (!has(field, 'default') && !field.optional) this.errors.push({ path, message: 'Required' })
      return
    }
    const value = given[name]
    if (field.enum) {
      if (typeof value !== 'string' || !field.enum.includes(value)) this.errors.push({ path, message: enumMessage(field.enum) })
    } else if (field.pattern !== undefined) {
      if (typeof value !== 'string' || !new RegExp(`^(?:${field.pattern})$`).test(value)) this.errors.push({ path, message: 'Must match ' + field.pattern })
    } else if (field.json) {
      if (!isObject(value)) { this.errors.push({ path, message: 'Must be a JSON object' }); return }
      const high = this.limits.custom_props_bytes
      let size: number
      try { size = new TextEncoder().encode(JSON.stringify(value)).length } catch { this.errors.push({ path, message: 'Is nested too deeply' }); return }
      if (size > high) this.errors.push({ path, message: `Must be at most ${high} bytes of JSON` })
    }
  }
}

function normaliseNode(node: Obj, vocabulary: LayoutVocabulary): ResolvedShellNode {
  const kind = node.type
  if (kind === 'spacer') return { type: 'spacer' }
  const size = clone(has(node, 'size') ? node.size : vocabulary.size.default) as ShellSize
  if (kind === 'container') {
    const out: Obj = { type: 'container' }
    for (const [name, field] of Object.entries(vocabulary.container)) {
      if (has(node, name)) out[name] = node[name]
      else if (has(field, 'default')) out[name] = field.default
    }
    out.size = size
    out.children = (node.children as Obj[]).map(child => normaliseNode(child, vocabulary))
    return out as unknown as ResolvedShellContainer
  }
  const given = (has(node, 'options') ? node.options : {}) as Obj
  const options: Obj = {}
  for (const [name, field] of Object.entries(vocabulary.regions[node.region as string].options)) {
    if (has(given, name)) options[name] = clone(given[name])
    else if (has(field, 'default')) options[name] = field.default
  }
  return { type: 'region', region: node.region, size, options } as unknown as ResolvedShellRegion
}

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value))

/** A valid shell with every default filled in (the tree a host renders). The input is not changed.
 *  Every container carries direction, gap, padding, align, justify, chrome, surface, size, behavior and children (and
 *  collapse_below when it set one); every region carries size and the full set of its options (a `custom` region keeps
 *  `module`, and `props` only when it set it); a spacer is just its type. Behaviour for an invalid tree is undefined:
 *  run validateShell first. */
export function normaliseShell(shell: ShellTree, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedShellTree {
  return { version: shell.version, root: normaliseNode(shell.root as unknown as Obj, vocabulary) as ResolvedShellContainer }
}

type Located = [ResolvedShellNode, string]

function shellRules(tree: ResolvedShellTree, path: string, vocabulary: LayoutVocabulary, scroll: string | null | undefined,
  installed: Set<string> | null, errors: ShellProblem[], warnings: ShellProblem[]): void {
  const limits = vocabulary.limits, regions = vocabulary.regions
  const pxMax = limits.size_px.max
  const rootPath = `${path}.root`
  const counts: Record<string, number> = {}
  const chrome: Record<string, number> = {}

  const walk = (node: ResolvedShellNode, nodePath: string): void => {
    if (node.type === 'container') {
      if (node.chrome !== 'none') {
        chrome[node.chrome] = (chrome[node.chrome] ?? 0) + 1
        if (chrome[node.chrome] > limits.max_chrome_per_family) {
          errors.push({ path: `${nodePath}.chrome`, message: `At most ${limits.max_chrome_per_family} container${limits.max_chrome_per_family === 1 ? '' : 's'} may have chrome ${node.chrome}` })
        }
      }
      if (node.behavior !== 'fixed' && scroll != null && scroll !== 'page') {
        warnings.push({ path: `${nodePath}.behavior`, message: `behavior ${node.behavior} has no visible effect while scroll is ${scroll}; use scroll page or fixed` })
      }
      let fills = 0
      node.children.forEach((child, index) => {
        if (child.type !== 'spacer' && child.size.basis === 'fill') {
          fills += 1
          if (fills > 1) errors.push({ path: `${nodePath}.children[${index}].size`, message: 'At most one child of a container may fill (basis fill)' })
        }
      })
      node.children.forEach((child, index) => walk(child, `${nodePath}.children[${index}]`))
    } else if (node.type === 'region') {
      const name = node.region
      counts[name] = (counts[name] ?? 0) + 1
      if (counts[name] > regions[name].max) {
        errors.push({ path: nodePath, message: `At most ${regions[name].max} ${name} region${regions[name].max === 1 ? '' : 's'}` + (regions[name].required ? ' (a shell has exactly one)' : '') })
      }
      const module = (node.options as { module?: string }).module
      if (name === 'custom' && installed !== null && module !== undefined) {
        if (!installed.has(module)) {
          warnings.push({ path: `${nodePath}.options.module`, message: `module not installed: ${module}; the region renders nothing until the pack that ships it is installed and approved` })
        }
      }
    }
  }
  walk(tree.root, rootPath)
  const needs: Record<string, string> = {
    content: 'A shell needs a content region (the page itself)',
    navigation: 'A shell needs a navigation region, so the user can always navigate',
  }
  for (const [name, spec] of Object.entries(regions)) {
    if (spec.required && !counts[name]) errors.push({ path: rootPath, message: needs[name] ?? `A shell needs the ${name} region` })
  }

  // The content path: the first content region and every container above it.
  const find = (node: ResolvedShellNode, nodePath: string): Located[] | null => {
    if (node.type === 'region' && node.region === 'content') return [[node, nodePath]]
    if (node.type === 'container') {
      for (let index = 0; index < node.children.length; index++) {
        const found = find(node.children[index], `${nodePath}.children[${index}]`)
        if (found !== null) return [[node, nodePath] as Located, ...found]
      }
    }
    return null
  }
  const trail = find(tree.root, rootPath)
  const onPath = new Set<string>()
  if (trail !== null) {
    let parent: ResolvedShellContainer | null = null
    for (const [node, nodePath] of trail) {
      onPath.add(nodePath)
      if (parent !== null && (node as ResolvedShellContainer | ResolvedShellRegion).size.basis !== 'fill' && parent.children.length !== 1) {
        errors.push({ path: `${nodePath}.size`, message: 'The content region, and every container on the way to it, must fill (basis fill) or be the only child, so the page is never squeezed away' })
      }
      if (node.type === 'container' && node.collapse_below !== undefined) {
        errors.push({ path: `${nodePath}.collapse_below`, message: 'The container that holds the content cannot collapse into a drawer' })
      }
      if (node.type === 'container') parent = node
    }
  }

  const sizes = (node: ResolvedShellNode, nodePath: string, horizontal: number, vertical: number, parent: ResolvedShellContainer | null): void => {
    if (node.type === 'spacer') return
    if (parent !== null) {
      const size = node.size
      if (typeof size.basis === 'number') {
        const row = parent.direction === 'row'
        let over: boolean
        if (row) { horizontal += size.basis; over = horizontal > limits.max_fixed_path_px && limits.max_fixed_path_px >= horizontal - size.basis }
        else { vertical += size.basis; over = vertical > limits.max_fixed_path_px && limits.max_fixed_path_px >= vertical - size.basis }
        if (over) errors.push({ path: `${nodePath}.size`, message: `Fixed sizes on one root-to-leaf path add up to at most ${limits.max_fixed_path_px}px along the ${row ? 'row' : 'column'} axis` })
      }
      if (!onPath.has(nodePath)) {
        for (const key of ['min', 'max'] as const) {
          const value = size[key]
          if (value !== undefined && value > pxMax) errors.push({ path: `${nodePath}.size.${key}`, message: `Off the content path a size is at most ${pxMax}px` })
        }
      }
    }
    if (node.type === 'container') node.children.forEach((child, index) => sizes(child, `${nodePath}.children[${index}]`, horizontal, vertical, node))
  }
  sizes(tree.root, rootPath, 0, 0, null)
}

/** Check a `layout.shell` tree against the layout vocabulary: `{ errors, warnings }`, each `{ path, message }`.
 *  `vocabulary` is the built-in one unless the host has a newer one from the Themes app. `path` is where the tree sits in
 *  the theme; every problem names its node under it (`layout.shell.root.children[1].size`). `scroll` is layout.scroll: a
 *  container whose behavior is not `fixed` only warns when it is known not to be `page`. `installedModules` is the set of
 *  reviewed module ids the HOST has installed: when given, a `custom` region that names another one produces a "module not
 *  installed" warning (a pack still imports); at the SDK level (null) every well-formed module id is valid. */
export function validateShell(shell: unknown, vocabulary: LayoutVocabulary = layoutVocabulary, path = 'layout.shell',
  scroll: string | null = null, installedModules: Iterable<string> | null = null): { errors: ShellProblem[]; warnings: ShellProblem[] } {
  const errors: ShellProblem[] = [], warnings: ShellProblem[] = []
  if (!isObject(shell)) return { errors: [{ path, message: 'Shell must be an object with version and root' }], warnings }
  for (const key of Object.keys(shell).filter(k => k !== 'version' && k !== 'root').sort()) errors.push({ path: `${path}.${key}`, message: `Unknown key ${key}` })
  if (!has(shell, 'version')) errors.push({ path: `${path}.version`, message: 'Required' })
  else if (!isInt(shell.version) || shell.version !== vocabulary.shell_version) errors.push({ path: `${path}.version`, message: `version must be ${vocabulary.shell_version}` })
  if (!has(shell, 'root')) errors.push({ path: `${path}.root`, message: 'Required' })
  else new ShellCheck(vocabulary, errors).node(shell.root, `${path}.root`, 1)
  if (errors.length === 0) {
    shellRules(normaliseShell(shell as unknown as ShellTree, vocabulary), path, vocabulary, scroll,
      installedModules === null ? null : new Set(installedModules), errors, warnings)
  }
  return { errors, warnings }
}

/** The tree a theme's layout options describe (normalised), what a theme without `layout.shell` renders; the same mapping as themes.shell_from_layout, see
 *  docs/layout-tree.md ("From the options to a tree"). A sidebar carries the brand, the navigation and (with no navbar) the
 *  actions; a navbar sits above or below the content and carries the brand and the navigation only when there is no sidebar. */
export function shellFromLayout(layout: LayoutV2, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedShellTree {
  const { sidebar, navbar, content } = layout
  const sideOn = sidebar.side !== 'hidden', barOn = navbar.position !== 'hidden'
  const region = (name: string, options?: Obj, size?: ShellSize): Obj => {
    const node: Obj = { type: 'region', region: name }
    if (size !== undefined) node.size = size
    if (options !== undefined) node.options = options
    return node
  }
  const page: Obj = content.max_width
    ? { type: 'container', direction: 'row', justify: content.align === 'center' ? 'center' : 'start', size: { basis: 'fill' },
        children: [region('content', undefined, { basis: 'fill', max: content.max_width })] }
    : region('content', undefined, { basis: 'fill' })
  const sidebarNode = (): Obj => {
    const rail = sidebar.style === 'rail'
    const children = [
      region('brand', { name: rail ? 'hide' : 'auto' }),
      region('navigation', { style: rail ? 'icons' : 'icons-labels', orientation: 'vertical' }, { basis: 'fill' }),
    ]
    if (!barOn) children.push(region('actions', { style: rail ? 'icons' : 'labels', orientation: 'vertical' }))
    const node: Obj = {
      type: 'container', direction: 'column', chrome: 'sidebar', surface: sidebar.surface, size: { basis: sidebar.width },
      behavior: sidebar.behavior, collapse_below: sidebar.collapse_below, padding: 'sm', gap: 'xs', children,
    }
    if (rail) node.align = 'center'
    return node
  }
  const navbarNode = (): Obj => {
    const children: Obj[] = []
    if (navbar.show_brand && !sideOn) children.push(region('brand', { name: 'show' }))
    if (!sideOn) children.push(region('navigation', { style: 'icons-labels', orientation: 'horizontal', overflow: 'menu' }))
    if (navbar.align === 'between') children.push({ type: 'spacer' })
    children.push(region('actions', { style: 'labels', orientation: 'horizontal' }))
    return {
      type: 'container', direction: 'row', chrome: 'navbar', surface: 'flush', size: { basis: navbar.height }, behavior: navbar.behavior,
      align: 'center', justify: navbar.align === 'center' ? 'center' : 'start', padding: 'md', gap: 'md', children,
    }
  }
  const column = (firstBar: boolean, size?: ShellSize): Obj => {
    const node: Obj = { type: 'container', direction: 'column', children: firstBar ? [navbarNode(), page] : [page, navbarNode()] }
    if (size !== undefined) node.size = size
    return node
  }
  let root: Obj
  if (sideOn) {
    const main = barOn ? column(navbar.position === 'top', { basis: 'fill' }) : page
    root = { type: 'container', direction: 'row', children: sidebar.side === 'left' ? [sidebarNode(), main] : [main, sidebarNode()] }
    if (sidebar.surface === 'floating') Object.assign(root, { padding: content.padding, gap: content.gap })
  } else if (barOn) root = column(navbar.position === 'top')
  else {
    root = { type: 'container', direction: 'column', children: [region('navigation', { style: 'icons-labels', orientation: 'horizontal', overflow: 'menu' }), page] }
  }
  return normaliseShell({ version: vocabulary.shell_version as 1, root } as unknown as ShellTree, vocabulary)
}

/** The normalised tree a host renders for a valid theme: its own `layout.shell` when it has one, otherwise
 *  the tree its layout options describe (`shellFromLayout`). Same as `resolveTheme(theme).shell.tree`. */
export function shellTreeOf(theme: ThemeManifestV2, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedShellTree {
  if (theme.layout.shell !== undefined) return normaliseShell(theme.layout.shell, vocabulary)
  return shellFromLayout(theme.layout, vocabulary)
}

// --- The brand (logo). The same rules as themes.validate_brand, step for step. -----------------------
//
// docs/brand-logo.md is the specification; the limits come from the layout vocabulary's `brand.logo_limits`. Messages, paths and
// their ORDER match the Python twin (tests/test_brand.py runs both over the same cases), so everything here avoids what differs
// between the languages: ASCII-only case folding, explicit whitespace classes, code point counts.

const BRAND_KEYS = ['logo', 'logo_dark', 'mark', 'tagline']
const IMAGE_KEYS = ['src', 'alt']
const B64 = /^[A-Za-z0-9+/]*={0,2}$/
const ALT_CONTROL = /[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]/
const TRIM = /^[ \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+|[ \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+$/g
const SVG_CONTROL = /[\x00-\x08\x0b\x0c\x0e-\x1f]/
const svgTag = () => /<(?:[A-Za-z0-9_.-]+:)?(script|foreignobject|iframe|image|use)(?![A-Za-z0-9_:.-])/gi
const svgHref = () => /(?:^|[^A-Za-z0-9_.:-])(?:[A-Za-z0-9_.-]+:)?href[ \t\r\n]*=[ \t\r\n]*(?:"([^"]*)"|'([^']*)')/gi
const svgAttr = () => /(?:^|[^A-Za-z0-9_.:-])((?:[A-Za-z0-9_.-]+:)?[A-Za-z_][A-Za-z0-9_.-]*)[ \t\r\n]*=[ \t\r\n]*(?:"([^"]*)(?=")|'([^']*)(?='))/g
const SVG_DOCTYPE_SUBSET = /<!doctype[^>[]*\[/i
const svgScheme = () => /(?:^|[^A-Za-z0-9+.-])(javascript|data|https?):/gi
const svgUrlFunction = () => /url\([ \t\r\n]*["']?[ \t\r\n]*(javascript|data|https?)[ \t\r\n]*:/gi
const SVG_NAMED: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
const SVG_SIGNATURES: Record<string, [number[], string]> = { 'image/png': [[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 'PNG'], 'image/jpeg': [[0xff, 0xd8, 0xff], 'JPEG'] }
const SVG_FORBIDDEN_TAGS = ['script', 'foreignObject', 'iframe', 'image']

const logoLimits = (vocabulary?: LayoutVocabulary | null): BrandLogoLimits => vocabulary?.brand?.logo_limits ?? layoutVocabulary.brand!.logo_limits
const sizeText = (count: number) => (count % 1024 === 0 ? `${count / 1024} KiB` : `${count} bytes`)
const asciiLower = (text: string) => text.replace(/[A-Z]/g, c => String.fromCharCode(c.charCodeAt(0) + 32))
const trimText = (text: string) => text.replace(TRIM, '')
const codePoints = (text: string) => Array.from(text).length
const stripControl = (text: string) => text.replace(/[\x00-\x20]/g, '')
const rstripSvg = (text: string) => text.replace(/[ \t\r\n]+$/, '')

function decodeEntities(text: string): string {
  return text.replace(/&(?:#[xX]([0-9a-fA-F]{1,8})|#([0-9]{1,8})|(amp|lt|gt|quot|apos));/g, (_m, hex: string | undefined, dec: string | undefined, name: string | undefined) => {
    if (name) return SVG_NAMED[name]
    const point = hex ? parseInt(hex, 16) : parseInt(dec as string, 10)
    return point === 0 || point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff) ? '\ufffd' : String.fromCodePoint(point)
  })
}

/** Why a decoded SVG text is not acceptable (empty when it is). Order: structure, then each forbidden construct. */
function svgProblems(source: string): string[] {
  const problems: string[] = []
  if (SVG_CONTROL.test(source)) problems.push('An SVG must be well-formed text, with no control characters')
  let index = 0
  const size = source.length
  for (;;) {
    while (index < size && ' \t\r\n'.includes(source[index])) index++
    if (source.startsWith('<?', index)) { const end = source.indexOf('?>', index + 2); index = end < 0 ? size + 1 : end + 2 }
    else if (source.startsWith('<!--', index)) { const end = source.indexOf('-->', index + 4); index = end < 0 ? size + 1 : end + 3 }
    else if (asciiLower(source.slice(index, index + 9)) === '<!doctype') {
      let end = source.indexOf('>', index)
      const bracket = source.indexOf('[', index)
      if ((bracket >= 0 && bracket < end) || (bracket >= 0 && end < 0)) {
        const close = source.indexOf(']', bracket)
        end = close < 0 ? -1 : source.indexOf('>', close)
      }
      index = end < 0 ? size + 1 : end + 1
    }
    else break
  }
  if (index > size || !(source.startsWith('<svg', index) && index + 4 < size && ' \t\r\n/>'.includes(source[index + 4]))) {
    problems.push('An SVG must start at <svg (an XML prolog and comments may come before it)')
  }
  let tail = rstripSvg(source)
  while (tail.endsWith('-->') && tail.lastIndexOf('<!--') >= 0) tail = rstripSvg(tail.slice(0, tail.lastIndexOf('<!--')))
  if (!(tail.endsWith('</svg>') || (tail.endsWith('/>') && tail.indexOf('>', index) === tail.length - 1))) problems.push('An SVG must be well-formed: it must end with </svg>')
  const text = decodeEntities(source)
  const found = new Set<string>()
  let externalUse = false
  for (const match of text.matchAll(svgTag())) {
    const name = match[1].toLowerCase()
    found.add(name)
    if (name === 'use') {
      const end = text.indexOf('>', match.index! + match[0].length)
      for (const href of text.slice(match.index! + match[0].length, end < 0 ? text.length : end).matchAll(svgHref())) {
        externalUse = externalUse || !stripControl(href[1] !== undefined ? href[1] : href[2]).startsWith('#')
      }
    }
  }
  for (const name of SVG_FORBIDDEN_TAGS) if (found.has(name.toLowerCase())) problems.push(`An SVG must not contain <${name}>`)
  if (externalUse) problems.push('An SVG <use> may only point at an element in the same file (an href starting with #)')
  if (/<!entity/i.test(text)) problems.push('An SVG must not declare entities (<!ENTITY)')
  if (SVG_DOCTYPE_SUBSET.test(text)) problems.push('An SVG must not have a DOCTYPE with an internal subset')
  if (/@import/i.test(text)) problems.push('An SVG must not use @import')
  let events = false, script = false, external = false
  for (const match of text.matchAll(svgAttr())) {
    const name = match[1]
    if (name === 'xmlns' || name.startsWith('xmlns:')) continue
    if (asciiLower(name.slice(name.lastIndexOf(':') + 1)).startsWith('on')) events = true
    const value = stripControl(match[2] !== undefined ? match[2] : match[3])
    for (const scheme of value.matchAll(svgScheme())) {
      if (asciiLower(scheme[1]) === 'javascript') script = true
      else external = true
    }
  }
  for (const match of text.matchAll(svgUrlFunction())) {
    if (asciiLower(match[1]) === 'javascript') script = true
    else external = true
  }
  if (events) problems.push('An SVG must not have event attributes (on*=)')
  if (script) problems.push('An SVG must not contain javascript: URLs')
  if (external) problems.push('An SVG must not load external or data: URLs (http:, https: or data:)')
  return problems
}

/** The problems of one image `src` (the first failing step, or the SVG's list) and its decoded size. */
function imageSource(src: unknown, limits: BrandLogoLimits): { problems: string[]; size: number } {
  const fail = (message: string, size = 0) => ({ problems: [message], size })
  if (typeof src !== 'string') return fail('Must be a data: URI string')
  if (!src.startsWith('data:')) return fail("Must be a data: URI (data:image/png;base64,...); a theme's images are never fetched")
  const comma = src.indexOf(',')
  if (comma < 0) return fail('Malformed data URI: expected data:<type>;base64,<payload>')
  const header = src.slice(5, comma), payload = src.slice(comma + 1)
  if (!header.endsWith(';base64')) return fail('The data URI must be base64: data:<type>;base64,<payload>')
  const mime = header.slice(0, -7)
  if (!limits.types.includes(mime)) return fail('Type must be one of ' + limits.types.join(', '))
  if (payload.length % 4 !== 0 || !B64.test(payload)) return fail('The payload is not valid base64')
  const size = payload.length / 4 * 3 - (payload.length - payload.replace(/=+$/, '').length)
  if (size === 0) return fail('The image is empty')
  if (size > limits.max_image_bytes) return fail(`The image is ${size} bytes; at most ${sizeText(limits.max_image_bytes)}`, size)
  const binary = atob(payload)
  const data = Uint8Array.from(binary, c => c.charCodeAt(0))
  if (mime === 'image/svg+xml') {
    let text: string
    try { text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(data) } catch { return fail('An SVG must be UTF-8 text', size) }
    return { problems: svgProblems(text), size }
  }
  let valid: boolean, label: string
  if (mime === 'image/webp') {
    valid = data.length >= 12 && binary.startsWith('RIFF') && binary.slice(8, 12) === 'WEBP'
    label = 'WebP'
  } else {
    const [signature, name] = SVG_SIGNATURES[mime]
    valid = signature.every((byte, i) => data[i] === byte)
    label = name
  }
  return valid ? { problems: [], size } : fail(`The data is not a ${label} image (wrong file signature)`, size)
}

function textProblem(value: unknown, limit: number): string | null {
  if (typeof value !== 'string') return 'Must be text'
  if (ALT_CONTROL.test(value)) return 'Must not contain control characters'
  const length = codePoints(trimText(value))
  return length >= 1 && length <= limit ? null : `Must be 1 to ${limit} characters`
}

/** Check a theme's `brand`: `{ errors, warnings }` with the path of every problem (`brand.logo.src`). Never throws.
 *  `vocabulary` supplies `brand.logo_limits` (the built-in one when omitted). Problems come in a fixed order: unknown keys
 *  (alphabetical), then `logo`, `logo_dark`, `mark`, `tagline`; inside an image its unknown keys, `src`, `alt`, `height`; last the
 *  size of all the images together. `logo_dark` (the logo drawn on dark backgrounds) follows the rules of `logo` and needs a `logo`. */
export function validateBrand(brand: unknown, vocabulary: LayoutVocabulary = layoutVocabulary, path = 'brand'): { errors: ShellProblem[]; warnings: ShellProblem[] } {
  const errors: ShellProblem[] = [], warnings: ShellProblem[] = []
  if (!isObject(brand)) return { errors: [{ path, message: 'Brand must be an object with logo, mark and tagline' }], warnings }
  const limits = logoLimits(vocabulary), height = limits.height
  const error = (where: string, message: string) => { errors.push({ path: where, message }) }
  for (const key of Object.keys(brand).filter(k => !BRAND_KEYS.includes(k)).sort()) error(`${path}.${key}`, `Unknown key ${key}`)
  if (Object.keys(brand).length === 0) error(path, 'Brand must set logo, mark or tagline')
  let total = 0
  for (const key of ['logo', 'logo_dark', 'mark']) {
    if (!has(brand, key)) continue
    const image = brand[key], where = `${path}.${key}`
    if (key === 'logo_dark' && !has(brand, 'logo')) error(where, 'logo_dark needs a logo')
    if (!isObject(image)) { error(where, 'Must be an object with src and alt'); continue }
    const allowed = key !== 'mark' ? [...IMAGE_KEYS, 'height'] : IMAGE_KEYS
    for (const name of Object.keys(image).filter(k => !allowed.includes(k)).sort()) error(`${where}.${name}`, `Unknown key ${name}`)
    if (!has(image, 'src')) error(`${where}.src`, 'Required')
    else {
      const found = imageSource(image.src, limits)
      for (const message of found.problems) error(`${where}.src`, message)
      if (found.problems.length === 0) total += found.size
    }
    if (!has(image, 'alt')) error(`${where}.alt`, 'Required')
    else {
      const message = textProblem(image.alt, limits.alt_max)
      if (message) error(`${where}.alt`, message)
    }
    if (key !== 'mark' && has(image, 'height') && (!isInt(image.height) || image.height < height.min || image.height > height.max)) {
      error(`${where}.height`, rangeMessage(height.min, height.max))
    }
  }
  if (has(brand, 'tagline')) {
    const message = textProblem(brand.tagline, limits.tagline_max)
    if (message) error(`${path}.tagline`, message)
  }
  if (total > limits.max_total_bytes) error(path, `The images of a brand add up to ${total} bytes; at most ${sizeText(limits.max_total_bytes)}`)
  return { errors, warnings }
}

/** The brand a host draws: `{ logo, logo_dark, mark, tagline }` with the defaults filled (`logo.height`; `logo_dark.height` follows the
 *  logo's height, else the vocabulary's default) and the text trimmed, an absent part null; null for a theme without a brand.
 *  Assumes a valid brand (see `validateBrand`). */
export function normaliseBrand(brand: ThemeBrand | null | undefined, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedBrand | null {
  if (brand === null || brand === undefined) return null
  const { logo, mark, tagline } = brand, dark = brand.logo_dark
  const logoHeight = logo === undefined ? logoLimits(vocabulary).height.default : logo.height ?? logoLimits(vocabulary).height.default
  return {
    logo: logo === undefined ? null : { src: logo.src, alt: trimText(logo.alt), height: logoHeight },
    logo_dark: dark === undefined ? null : { src: dark.src, alt: trimText(dark.alt), height: dark.height ?? logoHeight },
    mark: mark === undefined ? null : { src: mark.src, alt: trimText(mark.alt) },
    tagline: tagline === undefined ? null : trimText(tagline),
  }
}

/** The logo to draw on a background: on a dark one (a dark header, a dark palette) `logo_dark` when the brand has one, else `logo`;
 *  on a light one `logo`. `brand` is a normalised brand (`resolveTheme(...).brand`) or null; the result is null when there is
 *  nothing to draw. Core calls it with the container's tone or the palette mode. */
export function brandLogoFor(brand: ResolvedBrand | null, onDark: boolean): (BrandImage & { height: number }) | null {
  if (brand === null) return null
  return onDark && brand.logo_dark !== null ? brand.logo_dark : brand.logo
}

/** The normalised brand of a valid theme, or null for a theme without one. Same as `resolveTheme(theme).brand`. */
export function brandOf(theme: ThemeManifestV2, vocabulary: LayoutVocabulary = layoutVocabulary): ResolvedBrand | null {
  return normaliseBrand(theme.brand, vocabulary)
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
  /** `ui` for a pair the interface really paints with; absent for the role pairs. */
  group?: string
  /** Present only for a theme with a dark palette. */
  mode?: ColorMode
}

/** Every contrast pair judged for a theme (same rows as contrast_report in Python): a light-only
 *  theme's rows carry no mode, a theme with a dark palette also has its dark rows. */
export function contrastReport(theme: ThemeManifestV2): ContrastRow[] {
  const scheme = theme.color_scheme ?? 'light'
  if (scheme === 'light') return contrastRows(theme, 'light', false)
  if (scheme === 'dark') return contrastRows(theme, 'dark', true)
  return [...contrastRows(theme, 'light', true), ...contrastRows(theme, 'dark', true)]
}

function contrastRows(theme: ThemeManifestV2, mode: ColorMode, label: boolean): ContrastRow[] {
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
  // `unless` names a role that replaces the pair.
  for (const p of registry.contrast_pairs) {
    if (!(p.unless && p.unless in resolved)) pair(p.id, p.fg, p.bg, p.min, p.level, undefined, p.group)
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

/** The dark accent tints the interface prints a text step on (a selected row, a chip, a tile). */
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

/** Re-solve the dark ramp's text steps against the dark surface, the page and the dark accent tints, in place: the surface
 *  and page first, then the tints are settled, then what is still short is lifted. */
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

/** The `modes.dark` block derived from a theme's own (light) tokens: every ramp reversed, the
 *  surface between the page and ink-100, readable `on-primary`, a dark scrim, stronger shadows, the
 *  `light` bar tone (the dark-looking one on reversed ramps), text steps re-solved to read and the brand's text and
 *  indicator steps lifted. Complete in color, sparse elsewhere. */
export function deriveDark(theme: { tokens: TokenLayers }): TokenLayers {
  const tokens = theme.tokens
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
