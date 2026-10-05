/** SDK-owned presentation contract v1. Application behavior remains in the host. */
import type { ComponentType, InputHTMLAttributes, ReactNode } from 'react'
export const TEMPLATE_API_VERSION = 1 as const
export interface ThemeProps {
  'layout.workspace': { children: ReactNode }
  'navigation.sidebar': { children: ReactNode; badge: string }
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
