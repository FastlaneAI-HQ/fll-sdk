/** Type declarations for the host-owned modules available to registry apps. */
declare module 'fastlanelabs/ui' {
  export const Field: import('./contracts').PlatformUI['Field']
  export const Button: import('./contracts').PlatformUI['Button']
  export const Notice: import('./contracts').PlatformUI['Notice']
  export const Input: import('./contracts').PlatformUI['Input']
  export const Card: import('./contracts').PlatformUI['Card']
  export const PageHeader: import('./contracts').PlatformUI['PageHeader']
  export const inputClass: string
}
declare module 'fastlanelabs/theme' {
  export function ThemeSlot<K extends import('./theme-contract').ThemeComponentId>(props: {
    id: K; props: import('./theme-contract').ThemeProps[K]; fallback: import('react').ComponentType<import('./theme-contract').ThemeProps[K]>
  }): import('react').ReactNode
  export function ThemePreview(props: {id:string;version:string;tokens:Record<string,string>;density:string;children:import('react').ReactNode}): import('react').ReactNode
  export function themeStyle(tokens: Record<string,string>): import('react').CSSProperties
}
