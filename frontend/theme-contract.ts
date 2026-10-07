/** SDK-owned presentation contract v1. Application behavior remains in the host. */
import type { ComponentType, InputHTMLAttributes, ReactNode } from 'react'
export const TEMPLATE_API_VERSION = 1 as const
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
  'layout.workspace': WorkspaceNavigation & { children: ReactNode }
  /** `style`, `side` and `collapsed` are passed only while a v2 theme is active; v1 templates ignore them. */
  'navigation.sidebar': Omit<WorkspaceNavigation, 'actions'> & {
    actions?: WorkspaceAction[]; style?: 'rail' | 'panel'; side?: 'left' | 'right'; collapsed?: boolean
  }
  'navigation.item': { item: NavigationItem | WorkspaceAction; mode: 'icon' | 'label' }
  /** `items` carries the primary navigation when a v2 layout hides the sidebar. */
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
export type ThemeComponents = { [K in ThemeComponentId]?: ComponentType<ThemeProps[K]> }
export interface ThemeTemplate {
  api_version: 1
  id: string
  version: string
  components: ThemeComponents
}
export interface TemplateLibrary { api_version: 1; templates: ThemeTemplate[] }

/** Authoritative IDs used by build tools and the host resolver. */
export const THEME_COMPONENT_IDS = [
  'layout.workspace', 'navigation.sidebar', 'navigation.item', 'navigation.topbar', 'page.header', 'surface.card',
  'control.button', 'control.input', 'control.field', 'feedback.notice',
  'chat.message', 'chat.composer',
] as const satisfies readonly ThemeComponentId[]

/** Theme API v2 (registry revision 1): data only, three token layers plus layout variants.
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
}
export interface ThemeManifestV2 {
  api_version: 2
  registry_revision: number
  id: string
  version: string
  label: string
  /** Must be `light` in registry revision 1; dark mode is reserved. */
  color_scheme: 'light'
  tokens: {
    /** Every primitive is required and literal. */
    primitives: Record<string, string>
    /** Every semantic role is required; a value is a literal or a `{token}` reference. */
    semantic: Record<string, string>
    /** Sparse: an unset component token follows its registry fallback. */
    components: Record<string, string>
  }
  layout: LayoutV2
}
/** What the host applies; produced by resolveTheme with no DOM access. */
export interface ResolvedTheme {
  api_version: 1 | 2
  /** CSS custom properties for the root (colors as `r g b`). */
  vars: Record<string, string>
  /** Attributes for the root element (data-density, data-theme, data-fl-contract). */
  attrs: Record<string, string>
  layout: Record<string, unknown>
  /** Attributes and variables for the workspace frame's own root element. */
  shell: { attrs: Record<string, string>; vars: Record<string, string> }
  /** Allow-listed webfont families the theme names. */
  fonts: { family: string; weights: number[] }[]
  /** Effective value of every variant/tone/position token. */
  enums: Record<string, string>
}
