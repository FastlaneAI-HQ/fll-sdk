/** SDK-owned theme contract: the props of the host's themed components and the theme manifest (API v2, registry
 *  revision 4). Application behavior remains in the host. */
import type { InputHTMLAttributes, ReactNode } from 'react'
export interface WorkspaceAction {
  id: string
  label: string
  icon: ReactNode
  disabled?: boolean
  onActivate: () => void
}
export interface NavigationItem extends WorkspaceAction {
  active?: boolean
  group: 'primary' | 'secondary'
}
export interface WorkspaceNavigation {
  tenantName: string
  badge: string
  items: NavigationItem[]
  actions: WorkspaceAction[]
}
export interface ThemeProps {
  /** `pageTitle` (the title of the page on screen) is read by the `title` region of a layout tree. */
  'layout.workspace': WorkspaceNavigation & { children: ReactNode; pageTitle?: string }
  /** `style`, `side` and `collapsed` follow the theme's layout. */
  'navigation.sidebar': Omit<WorkspaceNavigation, 'actions'> & {
    actions?: WorkspaceAction[]; style?: 'rail' | 'panel'; side?: 'left' | 'right'; collapsed?: boolean
  }
  'navigation.item': { item: NavigationItem | WorkspaceAction; mode: 'icon' | 'label' }
  /** `items` carries the primary navigation when the layout hides the sidebar. */
  'navigation.topbar': Pick<WorkspaceNavigation, 'tenantName' | 'actions'> & { items?: NavigationItem[] }
  'page.header': { title: string; description?: ReactNode; actions?: ReactNode }
  'surface.card': { children: ReactNode; title?: string; className?: string }
  'control.button': { children: ReactNode; onClick?: () => void; type?: 'button' | 'submit'; disabled?: boolean; loading?: boolean; tone?: 'primary' | 'quiet' | 'danger' }
  'control.input': InputHTMLAttributes<HTMLInputElement>
  'control.field': { label: string; hint?: ReactNode; children: ReactNode }
  'feedback.notice': { tone?: 'bad' | 'good' | 'info'; children: ReactNode }
  'chat.message': { role: 'user' | 'assistant'; children: ReactNode; streaming?: boolean }
  'chat.composer': { children: ReactNode; busy?: boolean; disabled?: boolean }
}
export type ThemeComponentId = keyof ThemeProps

/** Theme API v2 (registry revision 4): data only, three token layers plus layout variants, an optional layout tree and brand.
 *  The field list lives in theme-registry.json; theme-resolve.ts applies it. */
export const THEME_API_VERSION_V2 = 2 as const
export type LayoutStep = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl'
export type BarBehavior = 'fixed' | 'sticky' | 'static'
export interface LayoutV2 {
  density: 'comfortable' | 'compact'
  scroll: 'panel' | 'page'
  sidebar: {
    side: 'left' | 'right' | 'hidden'; style: 'rail' | 'panel'; surface: 'floating' | 'flush'
    width: number; behavior: BarBehavior; collapse_below: number
  }
  navbar: { position: 'hidden' | 'top' | 'bottom'; behavior: BarBehavior; height: number; align: 'start' | 'center' | 'between'; show_brand: boolean }
  content: { max_width: number; align: 'start' | 'center'; padding: LayoutStep; gap: LayoutStep }
  /** Optional: the shell as a validated tree (docs/layout-tree.md). When absent the host renders `shellFromLayout(layout)`. */
  shell?: ShellTree
}

// --- Layout tree. The limits, enums and defaults live in layout-vocabulary.json. ---------------
export type ShellRegionName = 'brand' | 'navigation' | 'actions' | 'title' | 'content' | 'custom'
/** Along the parent's main axis. `basis` a number is px (40 to 640). `min` and `max` apply to any basis (`max` may reach the
 *  content-path limit, 1920, on the content path). */
export interface ShellSize { basis: 'fill' | 'content' | number; min?: number; max?: number }
export interface ShellContainer {
  type: 'container'
  direction: 'row' | 'column'
  /** 1 to 8. */
  children: ShellNode[]
  gap?: LayoutStep
  padding?: LayoutStep
  align?: 'start' | 'center' | 'end' | 'stretch'
  justify?: 'start' | 'center' | 'end' | 'between'
  /** Which component-token family paints it: sidebar-* or navbar-*. */
  chrome?: 'none' | 'sidebar' | 'navbar'
  /** floating: inset with the panel radius and shadow; flush: edge to edge, ruled. */
  surface?: 'floating' | 'flush'
  size?: ShellSize
  /** Only with `layout.scroll: 'page'`; a warning otherwise. */
  behavior?: BarBehavior
  /** px of workspace width, 480 to 1280: below it the container becomes a drawer behind a menu button. */
  collapse_below?: number
}
export interface ShellRegion {
  type: 'region'
  region: ShellRegionName
  size?: ShellSize
  /** Per region; see ResolvedShellRegion for the keys. */
  options?: Record<string, unknown>
}
export interface ShellSpacer { type: 'spacer' }
export type ShellNode = ShellContainer | ShellRegion | ShellSpacer
export interface ShellTree { version: 1; root: ShellContainer }

/** A node with every default filled in (what `normaliseShell`, `shellFromLayout` and `ResolvedTheme.shell.tree` carry). */
export interface ResolvedShellContainer {
  type: 'container'
  direction: 'row' | 'column'
  gap: LayoutStep
  padding: LayoutStep
  align: 'start' | 'center' | 'end' | 'stretch'
  justify: 'start' | 'center' | 'end' | 'between'
  chrome: 'none' | 'sidebar' | 'navbar'
  surface: 'floating' | 'flush'
  size: ShellSize
  behavior: BarBehavior
  /** Present only when the container collapses. */
  collapse_below?: number
  children: ResolvedShellNode[]
}
interface ResolvedRegionBase { type: 'region'; size: ShellSize }
export type ResolvedShellRegion =
  | (ResolvedRegionBase & { region: 'brand'; options: { name: 'show' | 'hide' | 'auto'; logo: 'auto' | 'hide' | 'only' } })
  | (ResolvedRegionBase & { region: 'navigation'; options: { style: 'icons' | 'labels' | 'icons-labels' | 'launcher'; orientation: 'vertical' | 'horizontal'; groups: 'all' | 'primary' | 'secondary'; overflow: 'menu' | 'wrap' } })
  | (ResolvedRegionBase & { region: 'actions'; options: { style: 'icons' | 'labels'; orientation: 'vertical' | 'horizontal' } })
  | (ResolvedRegionBase & { region: 'title'; options: { size: 'sm' | 'md' | 'lg' } })
  | (ResolvedRegionBase & { region: 'content'; options: Record<string, never> })
  | (ResolvedRegionBase & { region: 'custom'; options: { module: string; props?: Record<string, unknown> } })
export type ResolvedShellNode = ResolvedShellContainer | ResolvedShellRegion | ShellSpacer
export interface ResolvedShellTree { version: 1; root: ResolvedShellContainer }

/** The shape of layout-vocabulary.json (owned by the Themes app; the SDK ships a built-in copy). */
export interface LayoutVocabulary {
  vocabulary_version: number
  shell_version: number
  steps: string[]
  limits: {
    max_nodes: number; max_depth: number; max_children: number
    size_px: { min: number; max: number }; collapse_below: { min: number; max: number }
    max_fixed_path_px: number; max_custom_regions: number; max_chrome_per_family: number; custom_props_bytes: number
    /** Optional: how far size.min and size.max may reach on the content path (default 1920, the range of content.max_width). */
    content_path_px?: { max: number }
  }
  container: Record<string, { enum?: string[]; step?: boolean; int?: boolean; default?: string; optional?: boolean }>
  size: { bases: string[]; default: ShellSize }
  regions: Record<string, { max: number; required?: boolean; options: Record<string, { enum?: string[]; pattern?: string; json?: boolean; default?: string; optional?: boolean }> }>
  presets: { id: string; label: string; use_when: string; tree: ShellTree }[]
  /** The limits of a theme's `brand`. Absent in a vocabulary that predates the brand: the built-in one applies. */
  brand?: { logo_limits: BrandLogoLimits }
}
/** `brand.logo_limits` of the layout vocabulary: what `validateBrand` accepts. */
export interface BrandLogoLimits {
  /** The MIME types of a `data:` URI, e.g. `image/png`, `image/svg+xml`. */
  types: string[]
  /** The decoded size of one image, and of every image of a brand together. */
  max_image_bytes: number
  max_total_bytes: number
  alt_max: number
  tagline_max: number
  height: { min: number; max: number; default: number }
  /** The host never draws a logo wider than this (px); the width follows the aspect ratio. */
  max_logo_width_px: number
}
/** One error or warning: where (`layout.shell.root.children[1].size`) and why. */
export interface ShellProblem { path: string; message: string }
/** `light` and `dark` themes have one palette (the tokens); an `auto` theme's tokens are its light
 *  palette and `modes.dark` overrides them. */
export type ColorScheme = 'light' | 'dark' | 'auto'
export type ColorMode = 'light' | 'dark'
export interface TokenLayers {
  /** Every primitive is required and literal. */
  primitives: Record<string, string>
  /** Every semantic role is required; a value is a literal or a `{token}` reference. */
  semantic: Record<string, string>
  /** Sparse: an unset component token follows its registry fallback. */
  components: Record<string, string>
}
/** One image of a brand: a `data:image/(png|jpeg|webp|svg+xml);base64,` URI and its accessible name. */
export interface BrandImage { src: string; alt: string }
/** A theme's brand as written (optional): at least one of the three. */
export interface ThemeBrand {
  /** A wide logo; `height` (px, 16 to 64, default 32) is the height the host draws it at. */
  logo?: BrandImage & { height?: number }
  /** The logo drawn on dark backgrounds (a dark header, a dark palette). Needs `logo`; same rules; `height` defaults to the logo's. */
  logo_dark?: BrandImage & { height?: number }
  /** An optional square mark for a narrow region (a rail, a collapsed bar). */
  mark?: BrandImage
  /** Shown on the sign-in page and the pages like it. */
  tagline?: string
}
/** `ResolvedTheme.brand`: the brand normalised (`normaliseBrand`): every part present or null, `logo.height` filled, the text trimmed. */
export interface ResolvedBrand {
  logo: (BrandImage & { height: number }) | null
  /** The logo for dark backgrounds, `height` filled from the logo's; use `brandLogoFor(brand, onDark)` to pick one. */
  logo_dark: (BrandImage & { height: number }) | null
  mark: BrandImage | null
  tagline: string | null
}
export interface ThemeManifestV2 {
  api_version: 2
  registry_revision: number
  id: string
  version: string
  label: string
  color_scheme: ColorScheme
  /** `color_scheme: 'auto'` only. Each layer is a sparse override of `tokens`;
   *  the dark palette must set every color ramp and `surface`. */
  modes?: { dark: TokenLayers }
  tokens: TokenLayers
  layout: LayoutV2
  /** Optional (docs/brand-logo.md). */
  brand?: ThemeBrand
}
/** What the host applies; produced by resolveTheme with no DOM access. */
export interface ResolvedTheme {
  api_version: 2
  /** CSS custom properties for the root (colors as `r g b`). */
  vars: Record<string, string>
  /** Attributes for the root element (data-density, data-theme, data-fl-contract). */
  attrs: Record<string, string>
  layout: Record<string, unknown>
  /** Attributes and variables for the workspace frame's own root element, and the layout tree the host renders: the theme's
   *  own `layout.shell` or the tree its layout options describe, normalised, plain data. */
  shell: { attrs: Record<string, string>; vars: Record<string, string>; tree: ResolvedShellTree }
  /** The theme's logo, mark and tagline, normalised; null for a theme without a brand. Draw it as an `<img>`: the sources are `data:` URIs the validator has checked. */
  brand: ResolvedBrand | null
  /** Allow-listed webfont families the theme names. */
  fonts: { family: string; weights: number[] }[]
  /** Effective value of every variant/tone/position token. */
  enums: Record<string, string>
  /** Present only for a theme with a dark palette: the modes it offers and the one resolved. */
  scheme?: { offered: ColorMode[]; mode: ColorMode }
}
