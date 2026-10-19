/**
 * The names `fastlanelabs/ui` exposes to an app: the one list the esbuild shim in build-app.mjs is generated from.
 * Keep it in step with `platform.d.ts` (the types) and the host's `frontend/src/ui/index.ts` + `components/Field.tsx` (the
 * values); the host's tests/unit/ui-exports.test.ts fails when the three disagree.
 */
/** The pieces that existed before the component library (their prop contracts are unchanged; antd draws most of them now). */
export const SHELL_EXPORTS = [
  'Workspace', 'Sidebar', 'Topbar', 'NavigationItem', 'Message', 'Composer',
  'Field', 'Button', 'Notice', 'Input', 'Card', 'PageHeader', 'PageFrame', 'inputClass', 'Badge', 'Modal', 'Tabs', 'Gate',
]
/** The component library: antd behind typed wrappers (no `style`), themed by the host's ThemeBridge. */
export const LIBRARY_EXPORTS = [
  // data entry
  'InputNumber', 'Checkbox', 'Radio', 'Switch', 'Slider', 'DatePicker', 'RangePicker', 'Upload', 'Select', 'AutoComplete', 'Segmented', 'Form',
  // data display
  'Pagination', 'Menu', 'Dropdown', 'Breadcrumb', 'Steps', 'Tag', 'Tooltip', 'Popover', 'Popconfirm', 'Descriptions', 'Statistic',
  'Collapse', 'Timeline', 'List', 'Tree', 'Avatar',
  // feedback
  'Drawer', 'Alert', 'Progress', 'Spin', 'Skeleton', 'Empty', 'Result', 'message', 'notification', 'modal',
  // layout and typography
  'Divider', 'Space', 'Flex', 'Row', 'Col', 'Typography', 'Text', 'Title', 'Paragraph', 'Link',
  // helpers
  'useBreakpoint', 'dayjs', 'useChartColors', 'useFeatures',
]
/** What the library adds on top of antd: enterprise defaults and the layout primitives. */
export const PATTERN_EXPORTS = [
  'DataTable', 'StatusTag', 'EmptyState', 'KeyValue', 'StatCard', 'Stack', 'Toolbar', 'Page', 'PageSection', 'CardSection',
  // table cells
  'CellText', 'Clip', 'numberColumn',
  // forms
  'FormField', 'FormSection', 'FormFooter', 'ColorField', 'FileDrop',
  // surfaces
  'ClickableCard', 'MasterDetail', 'MasterList', 'CodeBlock', 'DropdownPanel',
]
export const UI_EXPORTS = [...SHELL_EXPORTS, ...LIBRARY_EXPORTS, ...PATTERN_EXPORTS]
