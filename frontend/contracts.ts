/** Frontend app contract v1. The host owns React and platform UI primitives. */
import type { ComponentType, ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export const FRONTEND_API_VERSION = 1 as const
export interface AppModule {
  themeTemplates?: import('./theme-contract').TemplateLibrary
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
  Input: ComponentType<import('./theme-contract').ThemeProps['control.input']>
  Card: ComponentType<import('./theme-contract').ThemeProps['surface.card']>
  PageHeader: ComponentType<import('./theme-contract').ThemeProps['page.header']>
  Field: ComponentType<{ label: string; hint?: ReactNode; children: ReactNode }>
  Button: ComponentType<{ children: ReactNode; onClick?: () => void; type?: 'button' | 'submit'; disabled?: boolean; loading?: boolean; tone?: 'primary' | 'quiet' | 'danger' }>
  Notice: ComponentType<{ tone?: 'bad' | 'good' | 'info'; children: ReactNode }>
  inputClass: string
}
