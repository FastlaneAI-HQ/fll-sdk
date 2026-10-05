/** Data-only theme pack format v1. Uploaded files never supply executable components. */
import type { ThemeTemplate } from './theme-contract'
export interface ThemeManifest {
  api_version: 1; id: string; version: string; label: string
  tokens: Record<string,string>
  layout: {density:'comfortable'|'compact';navigation:'rail'|'sidebar'}
}
export type LayoutNode =
  | {type:'row'|'column';gap:'none'|'sm'|'md'|'lg';children:LayoutNode[]}
  | {type:'slot';name:'content'|'navigation'|'actions';width?:number}
export interface PresentationStyles {
  'navigation.sidebar'?: {variant:'panel'|'rail';tone:'light'|'dark'}
  'navigation.item'?: {variant:'square'|'pill';mode:'icon'|'label'}
  'navigation.topbar'?: {tone:'light'|'dark'}
  'page.header'?: {variant:'plain'|'ruled'}
  'surface.card'?: {variant:'bordered'|'raised'}
  'control.button'?: {variant:'solid'|'outline';radius:'theme'|'square'}
  'control.input'?: {variant:'outline'|'filled'}
  'control.field'?: {variant:'stacked'|'inline'}
  'chat.message'?: {variant:'bubble'|'ruled'}
  'chat.composer'?: {variant:'panel'|'plain'}
}
export interface ThemePackPresentation {api_version:1;workspace:LayoutNode;styles:PresentationStyles}
export interface ThemePackDefinition {theme:ThemeManifest;presentation:ThemePackPresentation}
export type ThemePackTemplateFactory = (packs:ThemePackDefinition[]) => ThemeTemplate[]
