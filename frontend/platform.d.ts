/** Type declarations for the host-owned modules available to registry apps. */
declare module 'fastlanelabs/ui' {
  // The host's component library: antd 5 behind typed wrappers (no `style`), themed by the host. Apps never bundle antd: `antd`,
  // `@ant-design/*` and `dayjs` resolve to this same module at build time (build-app.mjs), so import everything from here.
  // The names are listed once in ui-exports.mjs (the esbuild shim is generated from it).
  import type {
    ReactElement, ReactNode, Ref, Key, MouseEvent, KeyboardEvent, ForwardRefExoticComponent, RefAttributes,
  } from 'react'
  import type { TextProps as AntTextProps } from 'antd/es/typography/Text'
  import type { ParagraphProps as AntParagraphProps } from 'antd/es/typography/Paragraph'
  import type * as Antd from 'antd'
  import type { BaseOptionType, DefaultOptionType } from 'antd/es/select'
  import type { SegmentedValue } from 'antd/es/segmented'
  import type { MessageInstance } from 'antd/es/message/interface'
  import type { NotificationInstance } from 'antd/es/notification/interface'
  import type { HookAPI } from 'antd/es/modal/useModal'
  import type { Dayjs } from 'dayjs'

  /** Props that carry an inline style object: not accepted anywhere in the library (omitted here, stripped at runtime). `className` is allowed, as a layout hook only. */
  type StyleProp = 'style' | 'styles' | 'rootStyle' | 'bodyStyle' | 'headerStyle' | 'footerStyle' | 'contentStyle' | 'wrapperStyle' | 'maskStyle' | 'overlayStyle' | 'overlayInnerStyle' | 'dropdownStyle' | 'popupStyle' | 'drawerStyle' | 'labelStyle' | 'tableLayoutStyle' | 'headStyle'
  type DOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never
  type NoStyle<P> = DOmit<P, StyleProp>
  type Call<C> = C extends (props: infer P) => infer R ? (props: NoStyle<P>) => R : never
  type Locked<C, W extends keyof C = never> = Call<C> & { [K in keyof C]: K extends W ? Locked<C[K]> : C[K] }

  /** Spacing is a name on the 4px grid: xs 4, sm 8, md 12, lg 16, xl 24. */
  export type Gap = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

  // ---- the shell pieces (contracts unchanged) --------------------------------------------------------------------
  export const Workspace: import('./contracts').PlatformUI['Workspace']
  export const Sidebar: import('./contracts').PlatformUI['Sidebar']
  export const Topbar: import('./contracts').PlatformUI['Topbar']
  export const NavigationItem: import('./contracts').PlatformUI['NavigationItem']
  export const Message: import('./contracts').PlatformUI['Message']
  export const Composer: import('./contracts').PlatformUI['Composer']
  export const Field: import('./contracts').PlatformUI['Field']
  export const PageHeader: import('./contracts').PlatformUI['PageHeader']
  export const PageFrame: import('./contracts').PlatformUI['PageFrame']
  export const inputClass: string
  /** The signed-out frame (one centred card under the tenant's logo, drawn in the applied theme). Present only on hosts that export it. */
  export const Gate: import('./contracts').PlatformUI['Gate']

  // ---- names that predate the library; the old contract still works, the antd props are added --------------------
  /** What a button is for: `primary` (the page's one main action), `default` (secondary), `ghost` (quiet, no border), `danger` (destructive: the outlined red button), `link` (inline). */
  export type ButtonVariant = 'primary' | 'default' | 'ghost' | 'danger' | 'link'
  export type ButtonProps = DOmit<NoStyle<Antd.ButtonProps>, 'type' | 'htmlType' | 'onClick' | 'variant'> & {
    /** The preferred API: say what the button is for. Wins over `type` when both are given. */
    variant?: ButtonVariant
    /** `primary`, `default`, `dashed`, `text`, `link`. `button` / `submit` (the old HTML type) still work; the look is then `tone`, primary when neither is given. A bare `<Button danger>` is the outlined red button. */
    type?: 'primary' | 'default' | 'dashed' | 'text' | 'link' | 'button' | 'submit'
    htmlType?: 'button' | 'submit' | 'reset'
    /** Compatibility; new code uses `variant`. */
    tone?: 'primary' | 'quiet' | 'danger'
    onClick?: (event: MouseEvent<HTMLElement>) => void
  }
  export const Button: ForwardRefExoticComponent<ButtonProps & RefAttributes<HTMLButtonElement | HTMLAnchorElement>>
  export type InputProps = NoStyle<Antd.InputProps>
  export const Input: ForwardRefExoticComponent<InputProps & RefAttributes<Antd.InputRef>> & {
    Password: Locked<typeof Antd.Input.Password>; Search: Locked<typeof Antd.Input.Search>; TextArea: Locked<typeof Antd.Input.TextArea>; Group: Locked<typeof Antd.Input.Group>
  }
  export type CardProps = NoStyle<Antd.CardProps>
  export const Card: ForwardRefExoticComponent<CardProps & RefAttributes<HTMLDivElement>> & { Meta: Locked<typeof Antd.Card.Meta>; Grid: Locked<typeof Antd.Card.Grid> }
  export type NoticeProps = { tone?: 'bad' | 'good' | 'info'; children?: ReactNode } & Partial<DOmit<NoStyle<Antd.AlertProps>, 'type' | 'children'>>
  export function Notice(props: NoticeProps): ReactElement
  export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
  /** A label (`<Badge tone="success">Active</Badge>`), or antd's Badge when it has `count`, `dot`, `status` or `text`. */
  export type BadgeProps = { children?: ReactNode; tone?: BadgeTone; className?: string } | (NoStyle<Antd.BadgeProps> & { tone?: never })
  export const Badge: ((props: BadgeProps) => ReactElement) & { Ribbon: Locked<typeof Antd.Badge.Ribbon> }
  export interface ClassicModalProps {
    open?: boolean; title?: string; onClose: () => void; children: ReactNode; footer?: ReactNode
    /** Sizing for the panel. */ className?: string
    labelledBy?: string; label?: string; scrimClassName?: string; animation?: string; dismissOnScrim?: boolean; closeOnEscape?: boolean
    /** The panel's width by name: sm 400, md 560, lg 720, xl 960 (px). */
    size?: OverlaySize
  }
  /** The named widths of a dialog or a drawer. */
  export type OverlaySize = 'sm' | 'md' | 'lg' | 'xl'
  /** With `onClose`: the classic dialog. With `onCancel` / `onOk`: antd's Modal (centred; `size` is a name, `scrollBody` keeps the header and footer fixed while the body scrolls; `footer` takes a `FormFooter`). */
  export type ModalProps = ClassicModalProps | (NoStyle<Antd.ModalProps> & { size?: OverlaySize; scrollBody?: boolean; onClose?: never })
  export function Modal(props: ModalProps): ReactElement | null
  export interface ClassicTabsProps {
    tabs: { id: string; label: string; badge?: ReactNode }[]; value: string; onChange: (id: string) => void
    children?: ReactNode; idPrefix?: string; label?: string; className?: string
  }
  /** With `tabs`: the classic row (the page draws the panels). With `items`: antd's Tabs. */
  export type TabsProps = ClassicTabsProps | (NoStyle<Antd.TabsProps> & { tabs?: never })
  export function Tabs(props: TabsProps): ReactElement

  // ---- data entry -------------------------------------------------------------------------------------------------
  export const InputNumber: Locked<typeof Antd.InputNumber>
  export const Checkbox: Locked<typeof Antd.Checkbox, 'Group'>
  export const Radio: Locked<typeof Antd.Radio, 'Group' | 'Button'>
  export const Switch: Locked<typeof Antd.Switch>
  export const Slider: Locked<typeof Antd.Slider>
  export const DatePicker: Locked<typeof Antd.DatePicker, 'RangePicker'>
  export const RangePicker: Locked<typeof Antd.DatePicker.RangePicker>
  export const Upload: Locked<typeof Antd.Upload, 'Dragger'>
  export const Select: (<V = any, O extends BaseOptionType | DefaultOptionType = DefaultOptionType>(props: NoStyle<Antd.SelectProps<V, O>> & { ref?: Ref<unknown> }) => ReactElement) & { Option: typeof Antd.Select.Option; OptGroup: typeof Antd.Select.OptGroup }
  export const AutoComplete: <V = any, O extends BaseOptionType | DefaultOptionType = DefaultOptionType>(props: NoStyle<Antd.AutoCompleteProps<V, O>> & { ref?: Ref<unknown> }) => ReactElement
  export const Segmented: <V extends SegmentedValue = SegmentedValue>(props: NoStyle<Antd.SegmentedProps<V>> & { ref?: Ref<HTMLDivElement> }) => ReactElement
  /** Stacked labels, an asterisk on required fields (nothing on optional ones), validate on blur. */
  export type FormProps<Values = any> = NoStyle<Antd.FormProps<Values>>
  export type FormInstance<Values = any> = Antd.FormInstance<Values>
  export const Form: (<Values = any>(props: FormProps<Values> & { ref?: Ref<FormInstance<Values>> }) => ReactElement) & {
    Item: Locked<typeof Antd.Form.Item>; List: typeof Antd.Form.List; ErrorList: typeof Antd.Form.ErrorList; Provider: typeof Antd.Form.Provider
    useForm: typeof Antd.Form.useForm; useFormInstance: typeof Antd.Form.useFormInstance; useWatch: typeof Antd.Form.useWatch
  }

  // ---- data display -----------------------------------------------------------------------------------------------
  export type DataTableColumn<T> = NonNullable<Antd.TableProps<T>['columns']>[number]
  export interface DataTableSelection<T> { selectedRowKeys: Key[]; onChange: (keys: Key[], rows: T[]) => void; type?: 'checkbox' | 'radio'; isDisabled?: (record: T) => boolean }
  export interface DataTablePagination { current?: number; pageSize?: number; total?: number; onChange?: (page: number, pageSize: number) => void; showSizeChanger?: boolean; pageSizeOptions?: number[] }
  export type DataTableProps<T extends object> = NoStyle<Omit<Antd.TableProps<T>, 'columns' | 'rowKey' | 'dataSource' | 'size' | 'sticky' | 'pagination' | 'rowSelection' | 'loading' | 'locale' | 'scroll' | 'bordered' | 'title' | 'footer' | 'onRow'>> & {
    columns: DataTableColumn<T>[]
    dataSource: T[] | undefined
    /** Required: the field that identifies a row, or a function of the record. */
    rowKey: (keyof T & string) | ((record: T) => Key)
    loading?: boolean
    /** Shown when there are no rows. */
    empty?: ReactNode
    /** `false` for none; otherwise the pager at the foot, right-aligned (20 a page by default). */
    pagination?: false | DataTablePagination
    selection?: DataTableSelection<T>
    onRowClick?: (record: T) => void
    /** Off by default (the table fits its card; long cells clip with a tooltip). Give `x` (px or `max-content`) for a table that is wider on purpose. */
    scroll?: { x?: number | 'max-content' | 'auto' }
    /** The header sticks to the top of the scrolling region (default, except for `variant="embedded"`). */
    sticky?: boolean
    /** `embedded`: no outer border, 32px rows, quiet header, not sticky: for a chat message, a dialog, a panel. */
    variant?: 'default' | 'embedded'
    className?: string
  }
  /** Small table, sticky header, 40px rows (an icon button in a cell does not make them taller), built-in empty state and loading skeleton. A column with `width` or `ellipsis` makes the layout fixed. Put it in a flush `PageSection`. */
  export function DataTable<T extends object>(props: DataTableProps<T>): ReactElement
  export type CellTextProps = Omit<TextProps, 'size'> & { mono?: boolean }
  /** Text for a table cell: 13px, like the table. */
  export const CellText: (props: CellTextProps & { ref?: Ref<HTMLSpanElement> }) => ReactElement
  export interface ClipProps { children: string; max?: number; lines?: 1 | 2 | 3; className?: string }
  /** Long text that ends in an ellipsis where it runs out of room; the full text is the tooltip. */
  export function Clip(props: ClipProps): ReactElement
  export interface NumberColumnOptions<T> {
    title: ReactNode; dataIndex: keyof T & string; key?: string; width?: number; digits?: number; prefix?: string; suffix?: string
    format?: (value: number, record: T) => ReactNode; sortable?: boolean; empty?: ReactNode
  }
  /** A right-aligned numeric column with tabular figures. */
  export function numberColumn<T extends object>(options: NumberColumnOptions<T>): DataTableColumn<T>
  export const Pagination: Locked<typeof Antd.Pagination>
  export const Menu: Locked<typeof Antd.Menu>
  export const Dropdown: Locked<typeof Antd.Dropdown>
  export const Breadcrumb: Locked<typeof Antd.Breadcrumb>
  export const Steps: Locked<typeof Antd.Steps>
  export const Tag: Locked<typeof Antd.Tag, 'CheckableTag'>
  export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'primary'
  export interface StatusTagProps { tone?: StatusTone; children?: ReactNode; icon?: ReactNode; className?: string }
  export function StatusTag(props: StatusTagProps): ReactElement
  export type AvatarTone = 'neutral' | 'brand' | 'info' | 'success' | 'warning'
  /** `tone` picks a hue from the theme's roles; `seed` (a name, an email, an id) picks one deterministically, and supplies initials when there are no children. */
  export type AvatarProps = DOmit<NoStyle<Antd.AvatarProps>, 'size'> & { size?: 'small' | 'default' | 'large'; tone?: AvatarTone; seed?: string }
  export const Avatar: ((props: AvatarProps) => ReactElement) & { Group: Locked<typeof Antd.Avatar.Group> }
  export const Tooltip: Locked<typeof Antd.Tooltip>
  export const Popover: Locked<typeof Antd.Popover>
  export const Popconfirm: Locked<typeof Antd.Popconfirm>
  export const Descriptions: Locked<typeof Antd.Descriptions>
  export const Statistic: Locked<typeof Antd.Statistic>
  export const Collapse: Locked<typeof Antd.Collapse>
  export const Timeline: Locked<typeof Antd.Timeline>
  export const List: (<T>(props: NoStyle<Antd.ListProps<T>>) => ReactElement) & { Item: Locked<typeof Antd.List.Item> }
  export const Tree: <T extends object = any>(props: NoStyle<Antd.TreeProps<T>>) => ReactElement
  export interface KeyValueItem { key?: string; label: ReactNode; value: ReactNode; span?: 1 | 2 | 3 | 4 }
  export interface KeyValueProps {
    items: KeyValueItem[]; columns?: 1 | 2 | 3 | 4; layout?: 'vertical' | 'horizontal'
    /** The label column of a `horizontal` list: sm 96, md 144 (default), lg 200 (px). */
    labelWidth?: 'sm' | 'md' | 'lg'
    bordered?: boolean; title?: ReactNode; extra?: ReactNode; className?: string
  }
  /** Label/value pairs on a grid (even rows, shared baseline): a record's highlights or a details panel. */
  export function KeyValue(props: KeyValueProps): ReactElement
  export interface StatCardProps {
    label: string; value: string | number; unit?: string
    delta?: { text: string; tone?: 'positive' | 'negative' | 'neutral' }
    hint?: ReactNode; icon?: ReactNode; loading?: boolean
    /** `sm`: compact, for dialogs and side panels. */
    size?: 'md' | 'sm'
    className?: string
  }
  /** A dashboard number: label, big value, the change. */
  export function StatCard(props: StatCardProps): ReactElement
  export interface EmptyStateProps { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode; compact?: boolean; className?: string }
  /** Nothing here yet: an icon, one sentence, one primary action. */
  export function EmptyState(props: EmptyStateProps): ReactElement

  // ---- feedback -----------------------------------------------------------------------------------------------------
  export type DrawerProps = DOmit<NoStyle<Antd.DrawerProps>, 'size' | 'width' | 'height'> & {
    /** sm 400 (default), md 560, lg 720, xl 960 (px). `footer` takes a `FormFooter`. */
    size?: OverlaySize
  }
  export const Drawer: (props: DrawerProps) => ReactElement
  export type AlertProps = NoStyle<Antd.AlertProps> & { role?: 'alert' | 'status' | 'note' | 'region' }
  /** A message in the page. `action` sits at the end, `description` runs the full width under it. Errors and warnings are `role="alert"`, the rest `role="status"`. */
  export const Alert: (props: AlertProps) => ReactElement
  export type ProgressTone = 'brand' | 'neutral' | 'success' | 'warning' | 'danger' | 'info'
  export type ProgressProps = NoStyle<Antd.ProgressProps> & {
    /** The bar's colour from the theme's roles: `neutral` (steel, the default), `brand`, `info`, `success`, `warning`, `danger`. It never turns green by itself at 100%. */
    tone?: ProgressTone
  }
  export const Progress: (props: ProgressProps) => ReactElement
  export const Spin: Locked<typeof Antd.Spin>
  export const Skeleton: Locked<typeof Antd.Skeleton, 'Button' | 'Input' | 'Avatar' | 'Image'>
  export const Empty: Locked<typeof Antd.Empty>
  export const Result: Locked<typeof Antd.Result>
  /** Follow the theme (the host mounts antd's App). `message.success('Saved')`. */
  export const message: MessageInstance
  export const notification: NotificationInstance
  /** `modal.confirm({ title, content, onOk })`. */
  export const modal: HookAPI

  // ---- layout and typography ---------------------------------------------------------------------------------------
  export const Divider: Locked<typeof Antd.Divider>
  export type SpaceProps = DOmit<NoStyle<Antd.SpaceProps>, 'size'> & { size?: Gap | [Gap, Gap] }
  export const Space: ((props: SpaceProps) => ReactElement) & { Compact: Locked<typeof Antd.Space.Compact> }
  export type FlexProps = DOmit<NoStyle<Antd.FlexProps>, 'gap'> & { gap?: Gap | [Gap, Gap] }
  export function Flex(props: FlexProps): ReactElement
  export type RowProps = DOmit<NoStyle<Antd.RowProps>, 'gutter'> & { gutter?: Gap | [Gap, Gap] }
  export function Row(props: RowProps): ReactElement
  export const Col: Locked<typeof Antd.Col>
  export const Typography: Locked<typeof Antd.Typography, 'Text' | 'Title' | 'Paragraph' | 'Link'>
  /** `xs` 12px, `sm` 13px, `md` 14px; without it text inherits its container's size. */
  export type TextSize = 'xs' | 'sm' | 'md'
  export type TextProps = NoStyle<AntTextProps> & { size?: TextSize }
  export const Text: (props: TextProps & { ref?: Ref<HTMLSpanElement> }) => ReactElement
  export const Title: Locked<typeof Antd.Typography.Title>
  export type ParagraphProps = NoStyle<AntParagraphProps> & { size?: TextSize }
  export const Paragraph: (props: ParagraphProps & { ref?: Ref<HTMLDivElement> }) => ReactElement
  export const Link: Locked<typeof Antd.Typography.Link>
  export interface StackProps { gap?: Gap; align?: 'start' | 'center' | 'end' | 'stretch'; children?: ReactNode; className?: string }
  /** Children in a column with an even gap. */
  export function Stack(props: StackProps): ReactElement
  export interface ToolbarProps { left?: ReactNode; right?: ReactNode; children?: ReactNode; gap?: Gap; className?: string }
  /** A row with a left slot (search, filters) and a right slot (actions) that wraps. */
  export function Toolbar(props: ToolbarProps): ReactElement
  export interface PageSectionProps {
    title?: ReactNode; description?: ReactNode; extra?: ReactNode; flush?: boolean
    /** A bar at the foot of the card that sticks to the bottom of the scrolling region: a save bar (give it a `FormFooter`). */
    footer?: ReactNode
    children?: ReactNode; className?: string
  }
  /** A card with a 16px title, an optional description and `extra`, and an optional sticky `footer`. `flush` removes the body padding (tables). */
  export function PageSection(props: PageSectionProps): ReactElement
  export interface CardSectionProps { title?: ReactNode; extra?: ReactNode; children?: ReactNode; className?: string }
  export function CardSection(props: CardSectionProps): ReactElement
  export type PageWidth = 'reading' | 'standard' | 'full'
  /** One step of the path above a page title; without `href` or `onClick` it is the current page. */
  export interface BreadcrumbItem { label: ReactNode; href?: string; onClick?: () => void }
  export interface PageProps {
    title: string
    /** Text or nodes; rendered in a block. */
    description?: ReactNode
    actions?: ReactNode
    /** The path above the title, on the shared left edge. */
    breadcrumb?: BreadcrumbItem[]
    /** Key facts below the description, inside the header card: `KeyValue` items or your own node. */
    highlights?: KeyValueItem[] | ReactNode
    tabs?: ReactNode; width?: PageWidth; fill?: boolean; children: ReactNode; className?: string
  }
  /** The page anatomy: header (breadcrumb, title, description, actions, highlights, tabs) above `PageSection`s. */
  export function Page(props: PageProps): ReactElement

  // ---- forms the library adds -------------------------------------------------------------------------------------
  export interface FormFieldProps {
    label: ReactNode; hint?: ReactNode; error?: ReactNode
    /** Shows the asterisk and sets `aria-required`. Optional fields carry no mark. */
    required?: boolean
    /** Kept for older callers: not required (now the default). */
    optional?: boolean
    /** Spans both columns of a two-column `FormSection`. */
    wide?: boolean
    children: ReactNode; className?: string
  }
  /** A labelled control: label above, hint and error under, wired to the control (`id`, `aria-describedby`) without a `name`. */
  export function FormField(props: FormFieldProps): ReactElement
  export interface FormSectionProps { title?: ReactNode; description?: ReactNode; columns?: 1 | 2; children?: ReactNode; className?: string }
  /** A titled group of fields on a 1 or 2 column grid. */
  export function FormSection(props: FormSectionProps): ReactElement
  export interface FormFooterProps { primary?: ReactNode; secondary?: ReactNode; danger?: ReactNode; note?: ReactNode; className?: string }
  /** The save bar: danger at the left (separated), then a note, then secondary and primary at the right. For `PageSection footer`, `Modal footer`, `Drawer footer`. */
  export function FormFooter(props: FormFooterProps): ReactElement
  export interface ColorFieldProps {
    value?: string; defaultValue?: string; onChange?: (hex: string) => void
    /** What the colour is for ("Primary colour"): names the picker and the text field. */
    label: string
    disabled?: boolean; id?: string; 'aria-describedby'?: string; className?: string
  }
  /** A colour: native picker as a swatch beside a hex text field. `onChange` receives a valid `#rrggbb`. */
  export function ColorField(props: ColorFieldProps): ReactElement
  export interface FileRejection { file: File; reason: 'type' | 'size' }
  export interface FileDropProps {
    /** The accessible name and visible title. */
    label: string; hint?: ReactNode
    /** Like a file input's `accept`: `.png`, `image/*`, `image/svg+xml`. */
    accept?: string
    /** Largest file in bytes. */
    maxSize?: number
    multiple?: boolean; disabled?: boolean; loading?: boolean; icon?: ReactNode
    onFiles: (files: File[]) => void; onReject?: (rejections: FileRejection[]) => void; className?: string
  }
  /** A drop zone and a labelled file picker in one, reachable by keyboard; checks type and size before it hands the files over. */
  export function FileDrop(props: FileDropProps): ReactElement

  // ---- surfaces the library adds ----------------------------------------------------------------------------------
  export type ClickableCardProps = NoStyle<Omit<Antd.CardProps, 'onClick' | 'hoverable'>> & {
    onClick?: (event: MouseEvent<HTMLElement> | KeyboardEvent<HTMLElement>) => void
    /** The chosen one of a set: accent border and tint. */
    selected?: boolean; disabled?: boolean
  }
  /** A card you can press (Enter and Space work, focus ring, hover, selected state). */
  export const ClickableCard: ForwardRefExoticComponent<ClickableCardProps & RefAttributes<HTMLDivElement>>
  export interface MasterDetailProps {
    list: ReactNode; detail: ReactNode
    /** sm 280, md 320 (default), lg 400 (px). */
    listWidth?: 'sm' | 'md' | 'lg'
    /** Below 992px only one shows: the list, or the detail when true. */
    showDetail?: boolean
    /** The "Back" control, shown above the detail on the narrow layout only. */
    back?: ReactNode
    listHeader?: ReactNode; listFooter?: ReactNode; listLabel?: string; className?: string
  }
  /** A list column beside a detail area, each scrolling by itself; put it in `<Page fill>`. */
  export function MasterDetail(props: MasterDetailProps): ReactElement
  export interface MasterListProps<T> {
    items: T[]; itemKey: (keyof T & string) | ((item: T) => Key)
    selectedKey?: Key | null; onSelect?: (item: T, key: Key) => void
    renderItem: (item: T, state: { selected: boolean }) => ReactNode
    label: string; loading?: boolean; empty?: ReactNode; className?: string
  }
  /** The rows of a master list: a listbox; the chosen row wears the accent bar. */
  export function MasterList<T extends object>(props: MasterListProps<T>): ReactElement
  export interface CodeBlockProps {
    code: string; language?: string; title?: ReactNode
    /** sm 160, md 320, lg 480 (default), none. */
    maxHeight?: 'sm' | 'md' | 'lg' | 'none'
    defaultWrap?: boolean; copy?: boolean; className?: string
  }
  /** Read-only monospace text with a title, a language label, a Copy button and a Wrap toggle. */
  export function CodeBlock(props: CodeBlockProps): ReactElement
  export interface DropdownPanelProps { title?: ReactNode; children?: ReactNode; footer?: ReactNode; width?: 'sm' | 'md' | 'lg' | 'auto'; className?: string }
  /** The chrome of a custom dropdown: what `Dropdown`'s `popupRender` returns. */
  export function DropdownPanel(props: DropdownPanelProps): ReactElement
  export interface ChartColors {
    /** Series colours in drawing order: info, success, warning, steel, brand, danger, then six tints (12). */
    series: string[]
    muted: string; text: string; border: string; surface: string; font: string; mode: 'light' | 'dark'
  }
  /** The theme's chart palette as colour strings; re-read when a theme, the colour mode or the density changes. */
  export function useChartColors(root?: HTMLElement | null): ChartColors
  export function useBreakpoint(): Partial<Record<'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl', boolean>>
  /** What the signed-in person may do in an app (role-based access): `can('send')` says whether one of the app's declared features
   *  (`AppSpec.features`) is allowed. Use it to hide or disable a control; the route enforces it regardless (`deps.require_feature`).
   *  `features` is the allowed ids, or `null` for everything (an administrator, or a member with no limit in this app). */
  export interface Features { can: (feature: string) => boolean; features: string[] | null }
  export function useFeatures(appId: string): Features
  /** dayjs, the host's copy (also what `import dayjs from 'dayjs'` gives in an app). */
  export const dayjs: typeof import('dayjs')
  export type { Dayjs }
}
declare module 'fastlanelabs/theme' {
  /** A theme shown inside the page without applying it: its variables and layout are scoped to the wrapper
   *  (data-fl-theme-root); `mode` previews its light or dark palette. */
  export function ThemePreview(props: {theme: import('./theme-contract').ThemeManifestV2; mode?: import('./theme-contract').ColorMode; children:import('react').ReactNode}): import('react').ReactNode
  /** The next three exist only on hosts that support theme API v2 (feature-detect `resolveTheme`). */
  export const resolveTheme: undefined | ((theme: import('./theme-contract').ThemeManifestV2, mode?: import('./theme-contract').ColorMode | null) => import('./theme-contract').ResolvedTheme)
  export const applyResolved: undefined | ((resolved: import('./theme-contract').ResolvedTheme) => void)
  /** Dark mode: present only on hosts that support it (feature-detect `deriveDark`).
   *  `deriveDark` returns the `modes.dark` block for a theme's light tokens; `offeredModes` and `effectiveMode`
   *  say which palettes a theme has and which one a user's choice selects. */
  export const deriveDark: undefined | ((theme: { tokens: import('./theme-contract').TokenLayers }) => import('./theme-contract').TokenLayers)
  export const offeredModes: undefined | ((theme: { color_scheme?: import('./theme-contract').ColorScheme }) => import('./theme-contract').ColorMode[])
  export const effectiveMode: undefined | ((theme: { color_scheme?: import('./theme-contract').ColorScheme }, preference?: string | null, systemDark?: boolean) => import('./theme-contract').ColorMode)
  /** Scopes a layout for a preview, so a draft's layout renders without changing the tenant's. */
  export const ShellLayoutProvider: undefined | ((props: { layout: import('./theme-contract').LayoutV2; children: import('react').ReactNode }) => import('react').ReactNode)
  /** The layout tree (docs/layout-tree.md): present only on hosts that draw it (feature-detect `shellTreeOf`).
   *  `validateShell` checks a `layout.shell` against the vocabulary, `normaliseShell` fills its defaults, `shellFromLayout` is the tree
   *  a theme's layout options describe (when it has no `layout.shell`), `shellTreeOf` the tree a theme renders, and `layoutVocabulary` the vocabulary itself. */
  export const validateShell: undefined | ((shell: unknown, vocabulary?: import('./theme-contract').LayoutVocabulary, path?: string, scroll?: string | null, installedModules?: Iterable<string> | null) => { errors: import('./theme-contract').ShellProblem[]; warnings: import('./theme-contract').ShellProblem[] })
  export const normaliseShell: undefined | ((shell: import('./theme-contract').ShellTree, vocabulary?: import('./theme-contract').LayoutVocabulary) => import('./theme-contract').ResolvedShellTree)
  export const shellFromLayout: undefined | ((layout: import('./theme-contract').LayoutV2, vocabulary?: import('./theme-contract').LayoutVocabulary) => import('./theme-contract').ResolvedShellTree)
  export const shellTreeOf: undefined | ((theme: import('./theme-contract').ThemeManifestV2, vocabulary?: import('./theme-contract').LayoutVocabulary) => import('./theme-contract').ResolvedShellTree)
  export const layoutVocabulary: undefined | import('./theme-contract').LayoutVocabulary
  /** The brand (docs/brand-logo.md): present only on hosts that draw it (feature-detect `brandOf`).
   *  `validateBrand` checks a theme's `brand`, `normaliseBrand` fills its defaults and `brandOf` is the brand a theme resolves to
   *  (null without one). */
  export const validateBrand: undefined | ((brand: unknown, vocabulary?: import('./theme-contract').LayoutVocabulary, path?: string) => { errors: import('./theme-contract').ShellProblem[]; warnings: import('./theme-contract').ShellProblem[] })
  export const normaliseBrand: undefined | ((brand: import('./theme-contract').ThemeBrand | null | undefined, vocabulary?: import('./theme-contract').LayoutVocabulary) => import('./theme-contract').ResolvedBrand | null)
  export const brandOf: undefined | ((theme: import('./theme-contract').ThemeManifestV2, vocabulary?: import('./theme-contract').LayoutVocabulary) => import('./theme-contract').ResolvedBrand | null)
  /** The logo to draw on a background (docs/brand-logo.md): `logo_dark` on a dark one (a dark header or sidebar, a dark palette) when the brand has one, else `logo`;
   *  `logo` on a light one; `null` when there is no logo. Feature-detect it with `brandOf`. */
  export const brandLogoFor: undefined | ((brand: import('./theme-contract').ResolvedBrand | null, onDark: boolean) => (import('./theme-contract').BrandImage & { height: number }) | null)
  /** Try a font on the whole workspace at once, kept in this browser only (feature-detect `fontChoices`). `fontChoices` lists every reviewed
   *  web font and the system stacks, `currentFontTryout` is the id being tried (or null for the theme's own), and `applyFontTryout(id)` draws
   *  everything in it now (`null` goes back to the theme's font). It never changes the theme itself. */
  export interface FontChoice { id: string; label: string; stack: string; category: 'sans' | 'serif' | 'mono'; kind: 'web' | 'system'; weights?: number[] }
  export const fontChoices: undefined | (() => FontChoice[])
  export const currentFontTryout: undefined | (() => string | null)
  export const applyFontTryout: undefined | ((id: string | null) => void)
}
