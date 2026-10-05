/** Frontend app contract v1. The host owns React and platform UI primitives. */
import type { ComponentType, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export const FRONTEND_API_VERSION = 1 as const
export interface AppModule {
  themeTemplates?: import('./theme-contract').TemplateLibrary
  createThemePackTemplates?: import('./theme-pack-contract').ThemePackTemplateFactory
  id: string
  label: string
  short: string
  icon: LucideIcon
  purpose: string
  Component: ComponentType
  group?: 'primary' | 'secondary'
  persistent?: boolean
  artifacts?: Record<string, ComponentType<{ data: any; messageKey: string }>>
}
export interface PlatformUI {
  Workspace: ComponentType<import('./theme-contract').ThemeProps['layout.workspace']>
  Sidebar: ComponentType<import('./theme-contract').ThemeProps['navigation.sidebar']>
  Topbar: ComponentType<import('./theme-contract').ThemeProps['navigation.topbar']>
  NavigationItem: ComponentType<import('./theme-contract').ThemeProps['navigation.item']>
  Message: ComponentType<import('./theme-contract').ThemeProps['chat.message']>
  Composer: ComponentType<import('./theme-contract').ThemeProps['chat.composer']>
  Input: ComponentType<import('./theme-contract').ThemeProps['control.input']>
  Card: ComponentType<import('./theme-contract').ThemeProps['surface.card']>
  PageHeader: ComponentType<import('./theme-contract').ThemeProps['page.header']>
  Field: ComponentType<{ label: string; hint?: ReactNode; children: ReactNode }>
  Button: ComponentType<{ children: ReactNode; onClick?: () => void; type?: 'button' | 'submit'; disabled?: boolean; loading?: boolean; tone?: 'primary' | 'quiet' | 'danger' }>
  Notice: ComponentType<{ tone?: 'bad' | 'good' | 'info'; children: ReactNode }>
  inputClass: string
}
