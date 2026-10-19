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
  /** Reviewed modules: components that a theme pack's `custom` layout region may draw, by id (`<author>/<name>@<major>`, e.g.
   *  `fastlane/brand-strip@1`).
   *
   *  The review gate: a pack is data, so it never carries code. A module's code lives in the app's own repo, passes that repo's
   *  review and tests, and ships through the app's release like any other component; the pack only NAMES it
   *  (`layout.shell` ... `{ type: 'region', region: 'custom', options: { module, props } }`). The host draws the module when the app
   *  that exports it is installed and approved, and nothing otherwise. The app's backend lists the ids it ships, with a schema
   *  for each one's props, so an unknown id is a warning and bad props an error when the pack is checked.
   *
   *  A module renders `props` (a small JSON object the host has already limited to 2 KB) as text, uses only the host's design
   *  tokens and classes, makes no network request and injects no HTML. */
  reviewedModules?: Record<string, ComponentType<{ props: Record<string, unknown> }>>
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
/** The minimum a host must offer for the pieces that predate the component library. The full surface of `fastlanelabs/ui` (antd components, `DataTable`,
 *  `Page`, `Stack`, ...) is declared in platform.d.ts and listed once in ui-exports.mjs; a host older than the library lacks those names. */
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
    title: string; description?: ReactNode; actions?: ReactNode; tabs?: ReactNode; breadcrumb?: ReactNode; highlights?: ReactNode
    width?: 'reading' | 'standard' | 'full'; fill?: boolean; className?: string; children: ReactNode
  }>
  Field: ComponentType<{ label: string; hint?: ReactNode; children: ReactNode }>
  Button: ComponentType<{ children: ReactNode; onClick?: () => void; type?: 'button' | 'submit'; disabled?: boolean; loading?: boolean; tone?: 'primary' | 'quiet' | 'danger' }>
  Notice: ComponentType<{ tone?: 'bad' | 'good' | 'info'; children: ReactNode }>
  inputClass: string
  /** Badge and Modal exist only on hosts that support theme API v2; apps feature-detect them. */
  Badge?: ComponentType<{ children: ReactNode; tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info' }>
  Modal?: ComponentType<{ open: boolean; title?: string; onClose: () => void; children: ReactNode; footer?: ReactNode }>
  /** The signed-out frame: a centred card under the tenant's logo (or its initials badge and name), drawn in the applied theme. */
  Gate: ComponentType<{ title: string; lede?: ReactNode; footer?: ReactNode; children?: ReactNode }>
  Tabs: ComponentType<{ tabs: { id: string; label: string; badge?: ReactNode }[]; value: string; onChange: (id: string) => void; children?: ReactNode; idPrefix?: string; label?: string; className?: string }>
}
