/** Type declarations for the host-owned modules available to registry apps. */
declare module 'fastlanelabs/ui' {
  export const Workspace: import('./contracts').PlatformUI['Workspace']
  export const Sidebar: import('./contracts').PlatformUI['Sidebar']
  export const Topbar: import('./contracts').PlatformUI['Topbar']
  export const NavigationItem: import('./contracts').PlatformUI['NavigationItem']
  export const Message: import('./contracts').PlatformUI['Message']
  export const Composer: import('./contracts').PlatformUI['Composer']
  export const Field: import('./contracts').PlatformUI['Field']
  export const Button: import('./contracts').PlatformUI['Button']
  export const Notice: import('./contracts').PlatformUI['Notice']
  export const Input: import('./contracts').PlatformUI['Input']
  export const Card: import('./contracts').PlatformUI['Card']
  export const PageHeader: import('./contracts').PlatformUI['PageHeader']
  export const PageFrame: import('./contracts').PlatformUI['PageFrame']
  export const inputClass: string
  /** Present only on hosts that support theme API v2. */
  export const Badge: import('./contracts').PlatformUI['Badge']
  export const Modal: import('./contracts').PlatformUI['Modal']
  export const Tabs: import('./contracts').PlatformUI['Tabs']
}
declare module 'fastlanelabs/theme' {
  export function installPackTemplates(library: import('./theme-contract').TemplateLibrary): void
  export function ThemeSlot<K extends import('./theme-contract').ThemeComponentId>(props: {
    id: K; props: import('./theme-contract').ThemeProps[K]; fallback: import('react').ComponentType<import('./theme-contract').ThemeProps[K]>
  }): import('react').ReactNode
  /** A v1 pack previews by id, version and tokens. A v2 draft passes `theme`: its variables and layout are scoped to
   *  the wrapper (data-fl-theme-root) and its template key never matches a v1 template; `mode` previews its light or dark palette. */
  export function ThemePreview(props: ({id:string;version:string;tokens:Record<string,string>;density:string} | {theme: import('./theme-contract').ThemeManifestV2; mode?: import('./theme-contract').ColorMode}) & {children:import('react').ReactNode}): import('react').ReactNode
  export function themeStyle(tokens: Record<string,string>): import('react').CSSProperties
  /** The next three exist only on hosts that support theme API v2 (feature-detect `resolveTheme`). */
  export const resolveTheme: undefined | ((theme: import('./theme-pack-contract').ThemeManifest | import('./theme-contract').ThemeManifestV2, mode?: import('./theme-contract').ColorMode | null) => import('./theme-contract').ResolvedTheme)
  export const applyResolved: undefined | ((resolved: import('./theme-contract').ResolvedTheme) => void)
  /** Dark mode (registry revision 2): present only on hosts that support it (feature-detect `deriveDark`).
   *  `deriveDark` returns the `modes.dark` block for a theme's light tokens; `offeredModes` and `effectiveMode`
   *  say which palettes a theme has and which one a user's choice selects. */
  export const deriveDark: undefined | ((theme: { tokens: import('./theme-contract').TokenLayers }) => import('./theme-contract').TokenLayers)
  export const offeredModes: undefined | ((theme: { api_version: number; color_scheme?: import('./theme-contract').ColorScheme }) => import('./theme-contract').ColorMode[])
  export const effectiveMode: undefined | ((theme: { api_version: number; color_scheme?: import('./theme-contract').ColorScheme }, preference?: string | null, systemDark?: boolean) => import('./theme-contract').ColorMode)
  /** Scopes a layout for a preview, so a draft's layout renders without changing the tenant's. */
  export const ShellLayoutProvider: undefined | ((props: { layout: import('./theme-contract').LayoutV2; children: import('react').ReactNode }) => import('react').ReactNode)
}
