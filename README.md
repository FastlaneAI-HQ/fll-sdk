# fll-sdk

The SDK and app registry for FastlaneLabs deployments.

FastlaneLabs deploys one instance per client, each with a hand-picked bundle
of apps (Contacts, Power Tools, RFQ Drafter, ...). Historically every app's
code lived permanently inside the core platform repo. This repo exists so an
app can instead be its own versioned, installable unit — built once, pulled
into any deployment that wants it, without touching core again.

## What lives here

- **`fastlanelabs_sdk`** — the Python plugin contract every app repo builds
  against: `AppSpec` (what an app is, for the entitlements UI),
  `AppPlugin` (what an app hands back to core once assembled), and
  `PlatformDeps` (the platform services an app is allowed to depend on —
  `get_conn`, `get_store`, `current_user`, `require_app`, `get_settings`,
  `runtime`). An app repo must not import core's internal module paths
  directly; it depends on this shape instead, and core hands it something
  that satisfies it structurally at install time.
- **`fastlanelabs_sdk/registry_data/apps.yaml`** — the catalog: which apps
  exist, and which git repo + ref their code lives at. This is deliberately a
  static, hand-maintained file today — the point of this first pass is
  proving that an app's code can be pulled in and bound into a deployment at
  install time at all. Discovery beyond a flat YAML file, and a real "which
  apps has every client been offered" catalog, is explicitly future work.

## The frontend contract

There is no separate JS SDK package yet. An app's frontend package default-
exports one plain object matching this shape (documented here rather than
typed in a shared package, since TypeScript only needs the shape to match
structurally):

```ts
interface AppModule {
  id: string
  label: string
  short: string
  icon: LucideIcon        // from 'lucide-react'
  purpose: string
  Component: React.ComponentType
  group?: 'primary' | 'secondary'
}
```

An app frontend package may only import platform utilities (the API client,
shared types) through the aliases `fastlanelabs/api` and `fastlanelabs/types`,
which core's `vite.config.ts` resolves to its own `src/api.ts`/`src/types.ts`.
Anything else is a dependency the app repo has to bring itself.

Core types this against its own `AppModule` interface once the app is
installed, so a plain literal like `group: 'secondary'` needs `as const` (or
an explicit type annotation) in the app's own `index.tsx` -- otherwise
TypeScript widens it to `string` there, before core ever sees it, and the
generated binding fails to compile with a type mismatch nothing in the app
repo itself would have caught.

## Installing an app

Core's `deploy/install_apps.py` reads `apps.yaml`, `pip install`s each
requested app's `backend/` subdirectory and `npm install`s its (repo-root)
frontend package, then generates the binding files core reads at startup. See
that script, and the main FastlaneLabs repo's plan doc, for the full flow.

## Registry runtime contract v1.1

Production apps are published wheels and browser-ready ESM/CSS, not core image dependencies. Catalog metadata carries registry selectors separately from runtime app IDs. `FASTLANELABS_REGISTRY_REMOTE=true` reads `catalog.json`; the last validated catalog remains cached on the persistent data volume. Local catalog overrides remain supported for development.

### Registry access (v1.2)

The registry's storage account is private. Tenant installs read it only through the fll-registry HTTP service, via `fastlanelabs_sdk.registry_client` (`get_blob`, `get_json`, `whoami`): `GET {base}/v1/files/<path>` with `Authorization: Bearer <key>`. The base URL is `registry.url` in `apps.yaml`, overridden by `FASTLANELABS_REGISTRY_URL`; the key is `FASTLANELABS_REGISTRY_KEY` (`flr_<tenant>_<8 hex>_<48 hex>`, issued per tenant). The key is access control only: callers keep checking every artifact's sha256 against `versions.json`. `registry.storage()` remains for operator publishing tooling that writes with its own `az` credentials.

App CI runs `frontend/build-app.mjs` and publishes `app.js` and `app.css` with a frontend API version and SHA-256 hashes. The bundle uses the host's React, JSX runtime and platform API. Shared form primitives are available as `fastlanelabs/ui` (Field, Button, Notice and inputClass); the public types live in `frontend/contracts.ts`. Do not bundle a separate React instance or import core's private source paths.

`AppPlugin.unload` is optional for stateless apps and required when an app owns connection pools, transport tasks, workers or caches. It must stop/release those resources without deleting persistent content. Disabled app routes and graph references are removed; in-flight calls retain their references until they finish. Native dependencies shared with the platform are not process-isolated.

Themes use `themes.validate_theme` (theme API v2; see below). The JSON manifest cannot execute code: authentication and application behavior remain host-owned. Theme source and publishing rules live in the separate `fll-themes` repository.

`theme_packs.create_theme_pack_v2` and `validate_theme_pack` provide the data-only ZIP contract for client uploads. A pack is three root JSON entries (`pack.json`, `theme.json`, `sources.json`): an immutable client identity, a checksummed manifest that carries its own layout, and source evidence. `ThemePackError.errors` identifies invalid files/fields. No uploaded code executes.

### Theme API v2

`themes.validate_theme` accepts exactly one manifest shape: `api_version: 2` at `registry_revision` 4 (anything else, older or newer, is refused with an error at `api_version` or `registry_revision`). A manifest layers **primitives** (every ramp, font family, type size, weight, spacing step, radius, shadow, motion and focus value; all required, literal), **semantic roles** (surfaces, text, lines, brand and four status families; required, literal or `{token}` references, four of them optional) and **component tokens** (optional; an unset token follows its registry fallback live). `layout` selects enumerated variants: sidebar side, style, surface, width, behavior and collapse breakpoint; navbar position, behavior, height and alignment; content width, alignment, padding and gap; scroll model and density. A theme may add a layout tree (`layout.shell`) and a brand (`brand`), below. There is no free CSS: values come from a closed grammar and reach the DOM only as validated custom properties.

`fastlanelabs_sdk/theme_registry.py` is the single source of truth for every token, its type, range and fallback. `scripts/gen_theme_registry.py` generates `registry_data/theme-registry-v2.json`, `registry_data/default-theme.json`, `frontend/theme-registry.json`, `frontend/theme-defaults.css`, `frontend/tailwind-preset.mjs` and `docs/theme-v2-tokens.md`; a test fails when any is stale. The 27 tokens flagged `v1` (the ink and accent ramps, `surface`, `on-primary`, the sans and mono stacks, `radius`) take literal values only.

`themes.check_theme` returns every error and warning with a field path and the contrast report; `validate_theme` returns a copy of a valid manifest and never injects defaults. `resolve_theme` flattens a manifest into CSS variables, root attributes, workspace-frame attributes, the layout tree, the brand and allow-listed webfonts. `frontend/theme-resolve.ts` is the TypeScript twin; shared fixtures in `tests/golden` keep the two in step.

The platform default is `registry_data/default-theme.json` (`fastlane` 2.1.0: the new-theme palette with a flush, labelled panel sidebar). Core serves it to a tenant with no theme, and the Themes app lists the same file as its built-in release.

#### Dark mode

Dark mode is data, not code, and adds no token. A theme declares `color_scheme`:

| `color_scheme` | Palettes | Who chooses |
| --- | --- | --- |
| `light` | the theme's `tokens` | nobody |
| `dark` | the theme's `tokens` are a dark palette | nobody; the workspace is dark |
| `auto` | `tokens` are the light palette, `modes.dark` overrides them | the user: light, dark or system |

`modes.dark` has the same three layers as `tokens` (`primitives`, `semantic`, `components`), each a sparse override. It must set every colour ramp (`ink`, `accent`, `success`, `warning`, `danger`, `info`), `surface` and `on-primary`; beyond that it may override any colour, any shadow, the two bar tones (`sidebar-tone`, `navbar-tone`) and the scrim opacities, and nothing else (type, spacing, radius and layout are one design in both modes). Values use the same closed grammar and reference rules as the base, and may refer to base tokens. The validator judges the dark palette with the same contrast pairs and thresholds as the light one (errors point at `modes.dark.*`), requires lighter text than surface, and warns on a light scrim.

`themes.derive_dark(theme)` (and `deriveDark` in `theme-resolve.ts`, step for step) derives a dark block from a theme's light tokens: it is not a naive inversion. Each ramp is reversed so the existing `ink-*`/`accent-*` classes land on coherent dark values; the surface sits between the page and `ink-100`; `on-primary` is the end of the ramp that reads on the primary colour (the reversed accent is lifted, when a brand needs it, until link, focus ring and primary-button pairs hold); the scrim is black; shadows are stronger; both bars use the `light` tone, which on reversed ramps is the dark-looking one; literal colours are mapped to the ramp step they equal or have their lightness reflected. The text steps are then solved rather than left reversed (below). `default_theme_v2(scheme='auto'|'dark')` is the default palette built this way.

`resolve_theme(theme, mode)` resolves a mode (`"light"` or `"dark"`; a `dark` theme is always dark, a light-only theme ignores the argument) and, for themes with a dark palette only, adds `scheme: {offered, mode}` and the `data-fl-mode` attribute. `effective_mode(theme, preference, system_dark)` is the host's rule: the only mode a theme offers, else the user's choice, else the operating system's.

The generated defaults also declare the platform hue ramps (`--fl-hue-*`: Tailwind's other palettes) and `--fl-black` for both modes, and the shared preset maps them (plus `white` for borders, rings and glyphs, and `text-black`) to those variables with Tailwind's own values as defaults, so light rendering is identical while a dark mode recolours classes that were hard-coded. See `docs/theme-v2-dark-mode.md`.

#### Fit for every theme: the palette, the UI pairs and the optional roles

The checks cover the colours the interface really paints with: apps colour text with raw ramp steps (`text-ink-400`, `text-accent-600`) and `text-white` on dark fills, which the role-based checks alone never saw. Full rationale and numbers in `docs/theme-v2-palette.md`.

* **A palette for new themes.** `theme_registry.NEW_THEME_DEFAULTS` makes `ink-400` 4.5:1 on the page and on `accent-50` and `ink-300` 3:1 on the page (`ink-500` one step darker), `border-input` the `ink-300` step (3:1), and the `-600` steps of success, warning and info carry text and white text at 4.5:1. `default_theme_v2()` (and the Themes editor and the builder) start from it (`theme_registry.default_for`). A token's `default` is the generated CSS fallback and does not move, so a host without a theme renders as before.
* **UI contrast pairs.** 33 pairs (`group: "ui"` in the contrast rows): `ink-400`/`ink-500` on `surface` and `surface-page`, `ink-400`/`ink-500` on `accent-50` and `ink-500` on `accent-100` (a caption in a selected row), `accent-600`/`accent-700` on `surface` and `accent-50`, `on-primary` on `ink-900`/`ink-800`/`danger-600`/`success-600`, the status `-600` steps on `surface`, the status `-700` step on the status `-100` and `-50` tints (`bg-amber-100 text-amber-700`: a chip, an avatar's initials), and the pairs of the optional roles. All warnings except `on-inverse` on `inverse`. A pair marked `unless` is not judged for a theme that sets the role that replaces it.
* **Four optional roles**: `inverse`/`on-inverse` (a dark fill and its text; fallback `ink-900`/`surface`) and `accent-text` (4.5:1 on `surface` and `accent-50`)/`accent-ui` (3:1) (fallback `accent-600`), with Tailwind keys `bg-inverse`, `text-on-inverse`, `text-accent-text`, `bg-accent-ui`, `ring-focus`. The surface-inverse role is `bg-surface-inverse`. `text-white`, `bg-ink-900` and `text-accent-600` resolve exactly as before.
* **Dark text is solved, not reversed** (`derive_dark`, `deriveDark` in the twin): `ink-300` to `ink-700` get at least the contrast the light palette gives them on its own surface (never less than 3:1 for 300, 4.5:1 for the text steps), the same steps also reach 4.5:1 on the dark accent tints (a saturated brand's tints are darkened first, never closer than 1.15:1 and 1.3:1 to the surface, so the steps keep their order), `accent-text` and `accent-ui` are lifted until they read on the dark surface.
* **Font stacks**: a family whose name has a word starting with a digit must be quoted (`'Source Sans 3', ui-sans-serif, ...`); the validator warns when it is not.

#### The layout tree

A theme may add `layout.shell`: the whole workspace shell as a small validated tree of containers (`row`/`column`, with gap, padding, alignment, `chrome: sidebar|navbar`, a `size`, a `collapse_below` drawer breakpoint), regions (`brand`, `navigation`, `actions`, `title`, `content`, `custom`) and spacers, instead of a choice among a fixed list of sidebar and navbar options. The existing `layout` keys stay required and validated (they are the fallback for a host without the renderer, and a theme without a tree renders the tree they describe). A tree adds no contrast pair or palette change.

* **Rules and vocabulary.** `docs/layout-tree.md` is the specification. Every limit, enum, default, region option and preset lives in one data file, the layout vocabulary, owned by the Themes app (`apps/fll-themes/layout-vocabulary.json`); the SDK ships two generated byte copies (`fastlanelabs_sdk/registry_data/layout-vocabulary.json`, `frontend/layout-vocabulary.json`) written by `scripts/gen_theme_registry.py` (`--vocabulary PATH`, else the Themes app beside the SDK, else the checked-in copy). The Themes app's `scripts/sync_layout_vocabulary.py` pushes its file into an SDK checkout.
* **Python.** `themes.validate_shell(shell, vocabulary=None, path, scroll=None, installed_modules=None)` returns `{errors, warnings}` with the node path of every problem (`layout.shell.root.children[1].size`); `normalise_shell` fills every default; `shell_from_layout(layout)` is the tree a theme's layout options describe (the registry default is the `rail` preset, the platform release the `panel-flush` preset); `shell_tree_of(theme)` is the tree a host renders. `check_theme`/`validate_theme` run `validate_shell` for a theme with a tree; a `custom` region naming a module is valid in the SDK and warns `module not installed` only when a host passes `installed_modules`.
* **TypeScript.** `frontend/theme-resolve.ts` has the same functions (`validateShell`, `normaliseShell`, `shellFromLayout`, `shellTreeOf`) with identical results, and `resolveTheme(theme).shell` is `{ attrs, vars, tree }`: `attrs` and `vars` are the classic attributes and variables of the layout options, `tree` is the normalised tree core renders. The types (`ShellTree`, `ShellNode`, `ResolvedShellTree`, ...) are in `theme-contract.ts`.
* **Tests.** `tests/golden/layout-tree` pins the results for themes with a tree (the default, the six presets, a tree with `custom` regions); `tests/golden/shell-from-layout.json` the trees the layout options of the other goldens describe; `tests/test_layout_tree.py` has a negative test with the exact path for every rule; `tests/test_layout_tree_parity.py` runs more than 400 valid and invalid trees through both languages and requires identical problems, order included.

#### The brand: a logo in the manifest

A theme may add one optional top-level key, `brand`: `{ logo: { src, alt, height? }, mark?: { src, alt }, tagline? }`, small `data:image/(png|jpeg|webp|svg+xml);base64,` images the host draws as `<img>` (no other scheme: nothing is fetched on a theme's behalf), with magic-byte checks, an SVG safety scan, 192 KiB per image and 320 KiB in all (the limits are the layout vocabulary's `brand.logo_limits`). `docs/brand-logo.md` is the specification. The contrast report ignores it.

* **API.** `themes.validate_brand(brand, vocabulary=None)` returns `{errors, warnings}` with paths like `brand.logo.src` (also reported by `check_theme`/`validate_theme`); `normalise_brand` fills `logo.height` and trims the text; `resolve_theme(theme)["brand"]` is the normalised brand or `None` for a theme without one. `theme-resolve.ts` has `validateBrand`, `normaliseBrand`, `brandOf` and `resolveTheme(theme).brand` with identical results (`tests/test_layout_tree_parity.py` runs 280 valid and invalid brands through both).
* **Registry.** `nav-item-variant` offers `tab` and `page-header-variant` offers `panel`, and the sign-in card has `gate-shadow`, `gate-title-fg` and `gate-tagline-fg` (fallbacks equal to what the sign-in page drew before they existed).
* **Tests.** `tests/test_brand.py` (a negative test with the exact path for every rule, the size limits derived from the vocabulary, the registry tokens), `tests/golden/brand` (a theme with a logo, a mark and a tagline, a logo alone and an invalid brand).

### Default, removable applications

AppSpec and RegistryEntry support `default_enabled` independently of `always`. A default app is installed and enabled during new-tenant setup but can subsequently be disabled in Admin. An explicit disabled row must not be overwritten on restart. Themes is a default app maintained in fll-themes; its code is fetched from the app registry, not bundled into the SDK or core image. The SDK retains only the theme contract, catalog metadata and built-in fallback manifest.

### Theme contract

`frontend/theme-contract.ts` types the props of the host's themed components (`ThemeProps`: workspace, sidebar, navigation item, topbar, page header, card, button, input, field, notice, chat message and composer) and the theme manifest, the resolved theme, the layout tree and the brand. Apps never replace those components: a theme changes how they look only through its tokens, layout options, layout tree and brand.

Core compiles against a generated copy of the SDK contract (and the resolver, registry, layout vocabulary, default CSS and Tailwind preset): `python scripts/sync_theme_contract.py /path/to/FastlaneLabs`. Core's CI clones the SDK tag its `requirements.txt` pins and fails when `frontend/src/generated` differs from it (the Themes app does the same for its skill's vendored validator). This avoids shipping developer build tooling in the production frontend image. App packages compile against the SDK directly and use `frontend/platform.d.ts` for the host UI/theme module declarations.

Workspace receives typed authorized product items, account actions and tenant metadata separately from its app-content children. Callbacks, permissions, data and app mounting remain in core.

## Tests

`pip install -e . pytest && npm ci && python -m pytest tests`. The tests that run the TypeScript twin and the Tailwind preset need node 20+ and `npm ci`; a local run without them skips those tests, but with `CI` or `JENKINS_URL` set (as in the Jenkinsfile) they fail instead, so a tag build always covers the TS twin. `package-lock.json` pins the dev dependencies; refresh it with `npm install` when `package.json` changes.
