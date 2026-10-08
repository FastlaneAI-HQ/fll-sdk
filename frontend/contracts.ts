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
  /** The page scrolls as a whole when the theme sets layout.scroll to `page`. It must drop its own scroll container. */
  pageScroll?: boolean
  artifacts?: Record<string, ComponentType<{ data: any; messageKey: string }>>
  /** A mail-client task pane (QuoteIQ in Outlook), rendered by core's
   *  quoteiq.html with the open message and the host's actions. */
  mailAddin?: ComponentType<MailAddinProps>
}
export interface MailContext {
  host: 'outlook' | 'preview'
  mode: 'read' | 'compose'
  conversationId: string
  itemId: string
  subject: string
  fromName: string
  fromAddress: string
  body: string
  mailbox: string
}
export interface MailAddinProps {
  mail: MailContext
  host: {
    /** Open a reply (reading) or insert at the cursor (composing). Never sends. */
    insertReply: (html: string) => Promise<void>
    openUrl: (url: string) => void
    connectedAs: { email: string; name: string }
    disconnect: () => Promise<void>
  }
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
  /** The panel every workspace page sits in: a themed header (title, description, actions), optional tabs on the
   *  same edge, and a body with a named width. `fill` hands the body to a page that scrolls for itself. */
  PageFrame: ComponentType<{
    title: string; description?: ReactNode; actions?: ReactNode; tabs?: ReactNode
    width?: 'reading' | 'standard' | 'full'; fill?: boolean; className?: string; children: ReactNode
  }>
  Field: ComponentType<{ label: string; hint?: ReactNode; children: ReactNode }>
  Button: ComponentType<{ children: ReactNode; onClick?: () => void; type?: 'button' | 'submit'; disabled?: boolean; loading?: boolean; tone?: 'primary' | 'quiet' | 'danger' }>
  Notice: ComponentType<{ tone?: 'bad' | 'good' | 'info'; children: ReactNode }>
  inputClass: string
  /** Badge and Modal exist only on hosts that support theme API v2; apps feature-detect them. */
  Badge?: ComponentType<{ children: ReactNode; tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info' }>
  Modal?: ComponentType<{ open: boolean; title?: string; onClose: () => void; children: ReactNode; footer?: ReactNode }>
  Tabs: ComponentType<{ tabs: { id: string; label: string; badge?: ReactNode }[]; value: string; onChange: (id: string) => void; children?: ReactNode; idPrefix?: string; label?: string; className?: string }>
}
