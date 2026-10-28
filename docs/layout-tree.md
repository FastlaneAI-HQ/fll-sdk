# Layout tree

A theme can describe its whole shell as a small validated tree instead of choosing from a fixed list of sidebar
and navbar options. A client's pack carries its own layout; the default layout is the fallback.

Status: implemented in `fastlanelabs_sdk.themes` (Python) and `frontend/theme-resolve.ts` (TypeScript twin). A theme without
`shell` resolves exactly as its layout options describe: its `resolveTheme` output (`attrs`, `vars`) is the classic one, and its tree is
the one `shell_from_layout` derives.

## Why

`layout` without a tree is a fixed list of options: sidebar side, style and surface, a navbar position, content
padding. A theme can only pick among them, so every theme has the same skeleton. A client who needs a different
skeleton (a top bar with the navigation in it and no sidebar, a two-bar shell, a navigation drawer only) cannot have it.

## Shape

A theme may carry `layout.shell`. When it is present the host renders the tree. When it is absent the host
derives the tree from the other `layout` keys with `shell_from_layout` (below), so one renderer serves every theme and
the default theme is simply the tree its options describe.

```jsonc
"layout": {
  "density": "comfortable",   // unchanged: density, scroll, sidebar, navbar, content stay required
  "scroll": "panel",          //   (a theme with a tree still supplies them: they are the fallback for a host
  "sidebar": { ... },         //   without the renderer; the builder derives them)
  "navbar":  { ... },
  "content": { ... },
  "shell": { "version": 1, "root": <Node> }   // optional
}
```

`layout` supplies exactly the existing keys plus, optionally, `shell`. `check_theme` reports `Layout must supply exactly ... and may add shell`
otherwise. The existing keys stay validated as before (including "at least one of the sidebar and the navbar must be visible"): they are the
fallback for a host that cannot draw the tree.

### Nodes

```ts
type Node = Container | Region | Spacer

interface Container {
  type: 'container'
  direction: 'row' | 'column'
  children: Node[]                      // 1 to 8
  gap?: Step                            // 'none'|'xs'|'sm'|'md'|'lg'|'xl'      default 'none'
  padding?: Step                        //                                    default 'none'
  align?: 'start' | 'center' | 'end' | 'stretch'     // cross axis             default 'stretch'
  justify?: 'start' | 'center' | 'end' | 'between'   // main axis              default 'start'
  chrome?: 'none' | 'sidebar' | 'navbar'  // which component-token family paints it: sidebar-* / navbar-*. default 'none'
  surface?: 'floating' | 'flush'        // floating: inset with the panel radius and shadow; flush: edge to edge, ruled. default 'flush'
  size?: Size                           // along the parent's main axis
  behavior?: 'fixed' | 'sticky' | 'static'   // only with scroll 'page'          default 'fixed'
  collapse_below?: number               // px of workspace width, 480 to 1280. Below it the container becomes a drawer
                                        // behind a menu button (see Collapse)
}

interface Region {
  type: 'region'
  region: 'brand' | 'navigation' | 'actions' | 'title' | 'content' | 'custom'
  size?: Size
  options?: RegionOptions               // per region, below
}

interface Spacer { type: 'spacer' }     // takes the free space on the parent's main axis

type Size = { basis: 'fill' | 'content' | number; min?: number; max?: number }
// a number is px, 40 to 640. 'fill' shares the free space (one fill per container, see Rules). 'content' is the natural size.
// min and max (whole px, 40 up) bound the size along the parent's main axis for any basis. Off the content path they are at most 640;
// on it (the content region and the containers above it) max may reach 1920, the range of layout.content.max_width, which
// shell_from_layout puts there.
```
`size` is along the main axis of the **parent** (a row parent: the width, a column parent: the height). The root has no parent, so a `size` on
it is accepted and ignored by every rule.

### Regions (the vocabulary)

| region | what the host draws | options |
| --- | --- | --- |
| `brand` | the tenant's badge, and its name; the theme's logo or mark when it has a `brand` (docs/brand-logo.md) | `name`: `show` / `hide` / `auto` (auto: the name shows when the region is wide enough, 160px or more); `logo`: `auto` (the logo when the theme has one) / `hide` (never: badge and name) / `only` (the logo alone, no name) |
| `navigation` | the authorised products as nav items | `style`: `icons` / `labels` / `icons-labels` / `launcher`; `orientation`: `vertical` / `horizontal`; `groups`: `all` / `primary` / `secondary`; `overflow`: `menu` (default) / `wrap` |
| `actions` | Settings, appearance, Sign out | `style`: `icons` / `labels`; `orientation`: `vertical` / `horizontal` |
| `title` | the title of the page on screen | `size`: `sm` / `md` / `lg` |
| `content` | the page itself | none |
| `custom` | a reviewed module a client pack ships | `module`: a reviewed module id (`client-acme/header@1`); `props`: a small JSON object |

`navigation` with `style: launcher` shows only a button (an app-launcher, "waffle" menu) that opens the list of the authorised products, instead of the
items themselves; the host decides how the menu looks. It needs no size and works in a horizontal or a vertical container (so no rule is specific to it:
sizes, fill, the one-navigation-region count and the drawer rule judge it like any other style). The vocabulary's sixth preset, `launcher-header`, is a slim
navbar holding the launcher, the brand, the page title, a spacer and the actions, over the content. `shell_from_layout` never emits `launcher`: a layout's options
cannot say it, and a host without the renderer falls back to the options the theme builder derived, which for `launcher-header` is a top navbar
of 56px with no sidebar, carrying the navigation items in the classic way.

`custom` renders the reviewed module when the pack carrying it is installed and approved, and nothing otherwise. A theme
that names a module that is not installed validates with a warning, not an error, so a pack still imports.

### Rules (validation)

* `shell.version` is 1; the root is a Container; nodes at most 24; depth at most 5; children 1 to 8.
  A node is a container, a region or a spacer, and all three count; the root is depth 1 and the deepest node of a path counts, so
  a root holding a container holding a container holding a container holding the content is five levels. Nodes are counted in
  document order (a container, then its children in turn); the first node over the limit is the error, and nothing after it is judged.
  A node at depth 6 is the error and is not descended into.
* Exactly one `content` region. It, and every container on the path to it (the root is exempt: it has no parent), has
  `size.basis: 'fill'` along its parent's main axis or is the only child of its parent (so the page is never squeezed to nothing). The
  error names that node's `size`. A numeric basis, however large, and the default `content` are not a fill.
* At most one `fill` child per container (the second is the error, at its `size`; a `spacer` takes the free space too but is not a
  fill child); at most one each of `brand`, `navigation`, `actions`, `title`; `custom` at most 4. The counts are the vocabulary's
  `regions.*.max`; the extra region is the error.
* The user must always be able to navigate: there is a `navigation` region (the error names the root), and it is not inside a
  container with `collapse_below` unless that container's drawer is reachable. A collapse container always shows its menu button,
  so a navigation region inside one is fine, with one exception that makes the drawer unreachable: the menu button goes to the nearest
  *remaining* container, so a container on the content path (the root included) must not collapse, or the page would vanish
  (error at its `collapse_below`).
* Fixed sizes (a numeric `size.basis`) along any root-to-leaf path sum to at most 960px on one axis. The two axes are summed apart: a
  node counts toward the width when its parent is a row and toward the height when its parent is a column. The node whose
  `size` makes a path cross the limit is the error (once per path, not once per descendant). The "no container is wider than
  640px unless it is the `content` path" clause is the size range above: a numeric basis is 40 to 640 everywhere, and `min`/`max` are at
  most 640 off the content path (error at `size.min` or `size.max`) and 1920 on it.
* `size.min` is at most `size.max` (error at `size.max`).
* `behavior` other than `fixed` needs `layout.scroll: 'page'` (as for the sidebar and navbar today); validation warns otherwise
  (a warning at the container's `behavior`; nothing is said when the scroll model is not known).
* `chrome: 'sidebar'` and `chrome: 'navbar'` each at most twice (the third is the error, at its `chrome`).
* A `custom` region's `module` matches `^[a-z0-9-]+/[a-z0-9-]+@[0-9]+$` (it is required); its `props` is a JSON object of at most
  2 KB: the bytes of its compact JSON in UTF-8.
* Unknown keys are errors (`Unknown key x`, and `Unknown option x` inside `options`). Every error carries the path of the node
  (`layout.shell.root.children[1].size`; a missing required region names `layout.shell.root`). Problems come in a fixed order
  (structure first, depth first, unknown keys in alphabetical order; then the rules), the same in Python and TypeScript.
* Every enum, step, range, default and pattern above is read from the vocabulary, never written in code.

Validation is two passes: the structure pass (keys, types, enums, ranges, limits) and, only on a tree with no structural error, the
rules. `custom` is valid at the SDK level whenever its module id is well formed; a **host** that passes the module ids it has
installed (`installed_modules`) gets a `module not installed: <id>` warning for any other, so a pack still imports.

### Collapse

A container with `collapse_below` collapses when the workspace is narrower than that many px. A collapsed container is
removed from the tree and shown as a drawer opened by a menu button the host adds to the start of the nearest remaining
container (the same behaviour the sidebar has today). Focus moves into the drawer on open, Escape closes it, and focus
returns to the menu button.

### Scroll

`layout.scroll` keeps its meaning. With `panel`, every page scrolls in its own panel and `behavior` has no visible effect.
With `page`, the content scrolls as a whole and a `sticky` or `static` container goes inside the scroller.

## From the options to a tree: `shell_from_layout`

The Python and TypeScript twins both implement it, and the goldens pin the output. For a theme without `layout.shell`:

* **Sidebar visible** (`sidebar.side` is not `hidden`): a root `container` row (`gap` and `padding` from `content.gap` and
  `content.padding` when `sidebar.surface` is `floating`, none when flush) holding, in the order of `sidebar.side`, the sidebar and
  the main part. The sidebar is a `column` container with `chrome: 'sidebar'`, `surface` from `sidebar.surface`, `size.basis`
  from `sidebar.width`, `behavior` from `sidebar.behavior`, `collapse_below` from `sidebar.collapse_below`, `padding: 'sm'`,
  `gap: 'xs'`, holding `brand`, `navigation` (`size.basis: 'fill'`, vertical) and, when there is no navbar, `actions` at the foot.
  A **rail** (`sidebar.style: 'rail'`) has `align: 'center'`, `brand.name: 'hide'`, `navigation.style: 'icons'` and `actions.style: 'icons'`; a
  **panel** has `brand.name: 'auto'`, `navigation.style: 'icons-labels'` and `actions.style: 'labels'`.
* **Navbar visible** (`navbar.position` is not `hidden`): a `row` container with `chrome: 'navbar'`, `surface: 'flush'`,
  `size.basis` from `navbar.height`, `behavior` from `navbar.behavior`, `align: 'center'`, `padding: 'md'`, `gap: 'md'`, `justify: 'center'` for
  `navbar.align: 'center'` and `'start'` otherwise, holding: `brand` (`name: 'show'`) when `show_brand` **and there is no sidebar** (a shell
  has one `brand`, and the sidebar carries it; the host's two-brand rendering is not expressible), `navigation` (horizontal, `overflow: 'menu'`)
  only when there is no sidebar, a `spacer` when `navbar.align` is `between`, and `actions` (labels, horizontal). It sits above
  (`top`) or below (`bottom`) the content, in a `column` container: the root when there is no sidebar, otherwise the main part
  (`size.basis: 'fill'`) beside the sidebar.
* **Both hidden**: a `column` root of a horizontal `navigation` region and the content (the host's existing fallback). The layout
  validator still rejects such a layout; the mapping is total.
* **The content**: a `content` region with `size.basis: 'fill'`. With `content.max_width` other than `0` it sits in a `row` container
  (`size.basis: 'fill'`) whose `justify` is `center` for `content.align: 'center'` and `start` otherwise, and the region carries
  `size.max` from `content.max_width`; the row, not the region, is the child of the root or of the main column, because `size` runs
  along the parent's main axis.

The mapping is total and always valid: every layout the options can express maps to a tree with no error and no warning at
`layout.scroll: 'page'` (`tests/test_layout_tree.py` checks a grid of more than a hundred). Two facts pin it:

* the registry default layout (`default_layout()`, a floating rail) maps to the vocabulary preset **`rail`**;
* the platform default release (`fastlane 2.1.0`, a flush panel with no navbar and no tree) maps to **`panel-flush`**;

and a panel on the right with a floating sidebar maps to `right-sidebar`. The sixth preset, `launcher-header`, is not the image of any layout: nothing maps to it. `tests/golden/layout-tree` and `tests/golden/shell-from-layout.json`
hold the trees; the TypeScript twin produces them byte for byte.

## Resolution (what the host receives)

`resolveTheme` (`resolve_theme` in Python) returns `shell: { attrs, vars, tree }` and, next to it, `brand` (see docs/brand-logo.md). `attrs` and `vars` are the existing attributes and CSS variables,
computed from the other `layout` keys, with or without a tree (so classic rendering is unchanged). `tree` is the normalised tree with
every default filled in: the theme's own `layout.shell`, otherwise `shell_from_layout(layout)`. The tree is plain data: it never contains markup,
class names, styles or URLs. Core renders `shell.tree`; `shell.attrs` and `shell.vars` remain for the classic frame.

A normalised container carries `direction, gap, padding, align, justify, chrome, surface, size, behavior, children` (and `collapse_below` when
set); a region carries `size` and every option of its kind (a `brand` region has `name` and `logo`; a `custom` region keeps `module`, and `props` only when it set it); a spacer is
`{ type: 'spacer' }`.

### API

| | Python (`fastlanelabs_sdk.themes`) | TypeScript (`theme-resolve.ts`) |
| --- | --- | --- |
| check a tree | `validate_shell(shell, vocabulary=None, path="layout.shell", scroll=None, installed_modules=None) -> {errors, warnings}` | `validateShell(shell, vocabulary?, path?, scroll?, installedModules?) => { errors, warnings }` |
| defaults filled | `normalise_shell(shell, vocabulary=None)` | `normaliseShell(shell, vocabulary?)` |
| from the options | `shell_from_layout(layout, vocabulary=None)` | `shellFromLayout(layout, vocabulary?)` |
| for a theme | `shell_tree_of(theme, vocabulary=None)` | `shellTreeOf(theme, vocabulary?)` |
| in a theme | `check_theme(theme, vocabulary=None, installed_modules=None)`, `validate_theme(...)`, `resolve_theme(theme, mode=None, vocabulary=None)` | `resolveTheme(theme, mode?, vocabulary?)` |
| the built-in data | `theme_registry.layout_vocabulary()` | `layoutVocabulary` |

Each problem is `{path, message}`. `check_theme` reports shell problems with their node paths and warnings beside the layout ones; the contrast report
does not depend on the tree and is produced even when the shell has errors.

## Ownership

The vocabulary above (the region list, the option enums, the numeric limits and the rules) lives in one data file, the
**layout vocabulary**. The Themes app owns it (`apps/fll-themes/layout-vocabulary.json`) and serves it from its backend;
the SDK ships a generated built-in copy (`registry_data/layout-vocabulary.json`, and `frontend/layout-vocabulary.json` for the TypeScript
twin, which core vendors with the other generated files) as the fallback so core validates and renders without the Themes app
installed. `scripts/gen_theme_registry.py` writes both copies as byte copies of the Themes app's file when it sits beside the SDK
(or `--vocabulary PATH`); in the SDK's standalone CI `--check` only proves the two copies are identical and parse. The Themes app's
`scripts/sync_layout_vocabulary.py` pushes its file into an SDK checkout. `limits.content_path_px.max` is an optional vocabulary entry for
the content-path `size` bound (default 1920). When the Themes app is installed and offers a newer vocabulary version that
the host's renderer supports, the Themes app's copy wins. The renderer only draws regions it knows: a vocabulary can
describe a region the host cannot draw yet, and such a theme is rejected at apply time with a message that names the
region.

## What stays code

The behaviours of the known regions (how a drawer opens, what a sticky container does) are host code. New behaviour is a
core change. Data can describe new combinations and new option values the host already understands.
