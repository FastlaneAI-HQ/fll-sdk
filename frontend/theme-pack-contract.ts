/** Data-only theme pack formats 1 and 2. Uploaded files never supply executable components. */
import type { ThemeManifestV2, ThemeTemplate } from './theme-contract'
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
export interface ThemePackDefinitionV1 {theme:ThemeManifest;presentation:ThemePackPresentation}
/** Format 2 packs carry their layout in the manifest, so there is no presentation. */
export interface ThemePackDefinitionV2 {theme:ThemeManifestV2;presentation:null}
export type ThemePackDefinition = ThemePackDefinitionV1 | ThemePackDefinitionV2
export type ThemePackTemplateFactory = (packs:ThemePackDefinition[]) => ThemeTemplate[]
