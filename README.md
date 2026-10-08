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

Themes use `themes.validate_theme` (API v1 and v2; see Theme API v2 below). A v1 theme supplies the complete ink/accent palettes, surface, primary text, font stacks, radius and supported layout choices. The JSON manifest cannot execute code. Separately reviewed JSX templates may rearrange registered presentation slots while authentication and application behavior remain host-owned. Theme source and publishing rules live in the separate `fll-themes` repository.

`theme_packs.create_theme_pack` and `validate_theme_pack` provide the data-only ZIP contract for client uploads. The four root JSON entries carry an immutable client identity, checksummed manifest, bounded layout tree, supported component variants and source evidence. `ThemePackError.errors` identifies invalid files/fields. No uploaded code executes. `frontend/theme-pack-contract.ts` types validated definitions; only the enabled Themes app's optional `createThemePackTemplates` factory compiles them into reviewed presentation components. The host merges imported components separately from its reviewed library and offloads both when Themes is removed.

### Theme API v2

`themes.validate_theme` accepts API v1 (frozen: its output is hashed into published releases) and API v2. A v2 manifest (`api_version: 2`, `registry_revision`) layers **primitives** (every ramp, font family, type size, weight, spacing step, radius, shadow, motion and focus value; all required, literal), **semantic roles** (surfaces, text, lines, brand and four status families; all required, literal or `{token}` references) and **component tokens** (optional; an unset token follows its registry fallback live). `layout` selects enumerated variants: sidebar side, style, surface, width, behavior and collapse breakpoint; navbar position, behavior, height and alignment; content width, alignment, padding and gap; scroll model and density. There is no free CSS: values come from a closed grammar and reach the DOM only as validated custom properties.

`fastlanelabs_sdk/theme_registry.py` is the single source of truth for every token, its type, range, fallback and the revision that introduced it. `scripts/gen_theme_registry.py` generates `registry_data/theme-registry-v2.json`, `registry_data/default-theme-v2.json`, `frontend/theme-registry.json`, `frontend/theme-defaults.css`, `frontend/tailwind-preset.mjs` and `docs/theme-v2-tokens.md`; a test fails when any is stale. The registry grows by `registry_revision` (new tokens are optional and reproduce the previous rendering), never by tightening an existing rule, so a stored release stays valid under every later validator. Registry revision 2 adds dark mode (below); revision 1 themes keep `color_scheme: light` and no `modes`, exactly as before.

`themes.check_theme` returns every error and warning with a field path and the contrast report; `validate_theme` returns a copy of a valid manifest and never injects defaults. `resolve_theme` flattens a manifest into CSS variables, root attributes, workspace-frame attributes and allow-listed webfonts; `upgrade_v1` views a v1 theme (and optionally its presentation) as v2 at read time, and `project_v1` produces the v1 manifest an older client can apply. `frontend/theme-resolve.ts` is the TypeScript twin; shared fixtures in `tests/golden` keep the two in step. v1 themes keep their own render path; an upgrade is an approximation used by editors and forks.

#### Dark mode (registry revision 2, SDK 1.4)

Dark mode is data, not code, and adds no token. A revision 2 theme declares `color_scheme`:

| `color_scheme` | Palettes | Who chooses |
| --- | --- | --- |
| `light` | the theme's `tokens` | nobody (every revision 1 theme is this) |
| `dark` | the theme's `tokens` are a dark palette | nobody; the workspace is dark |
| `auto` | `tokens` are the light palette, `modes.dark` overrides them | the user: light, dark or system |

`modes.dark` has the same three layers as `tokens` (`primitives`, `semantic`, `components`), each a sparse override. It must set every colour ramp (`ink`, `accent`, `success`, `warning`, `danger`, `info`), `surface` and `on-primary`; beyond that it may override any colour, any shadow, the two bar tones (`sidebar-tone`, `navbar-tone`) and the scrim opacities, and nothing else (type, spacing, radius and layout are one design in both modes). Values use the same closed grammar and reference rules as the base, and may refer to base tokens. The validator judges the dark palette with the same contrast pairs and thresholds as the light one (errors point at `modes.dark.*`), requires lighter text than surface, and warns on a light scrim.

`themes.derive_dark(theme)` (and `deriveDark` in `theme-resolve.ts`, step for step) derives a dark block from a theme's light tokens: it is not a naive inversion. Each ramp is reversed so the existing `ink-*`/`accent-*` classes land on coherent dark values; the surface sits between the page and `ink-100`; `on-primary` is the end of the ramp that reads on the primary colour (the reversed accent is lifted, when a brand needs it, until link, focus ring and primary-button pairs hold); the scrim is black; shadows are stronger; both bars use the `light` tone, which on reversed ramps is the dark-looking one; literal colours are mapped to the ramp step they equal or have their lightness reflected. `default_theme_v2(scheme='auto'|'dark')` is the default palette built this way.

`resolve_theme(theme, mode)` resolves a mode (`"light"` or `"dark"`; a `dark` theme is always dark, a light-only theme ignores the argument) and, for themes with a dark palette only, adds `scheme: {offered, mode}` and the `data-fl-mode` attribute. `effective_mode(theme, preference, system_dark)` is the host's rule: the only mode a theme offers, else the user's choice, else the operating system's. `project_v1` gives old clients the light palette of an `auto` theme.

Light-only themes are untouched by all of this: `tests/golden/frozen-r1` holds what SDK 1.3 produced for revision 1 and `tests/test_theme_frozen_r1.py` proves every byte is still produced (resolve, contrast report, upgrade with `registry_revision=1`, projection). The generated defaults also declare the platform hue ramps (`--fl-hue-*`: Tailwind's other palettes) and `--fl-black` for both modes, and the shared preset maps them (plus `white` for borders, rings and glyphs, and `text-black`) to those variables with Tailwind's own values as defaults, so light rendering is identical while a dark mode recolours classes that were hard-coded. See `docs/theme-v2-dark-mode.md`.

#### Fit for every theme (registry revision 3, SDK 1.5)

Revision 3 is about the colours the interface really paints with. The audit that led to it found that apps colour text with raw ramp steps (`text-ink-400`, `text-accent-600`) and `text-white` on dark fills, which the role-based checks never saw. It adds, and freezes revisions 1 and 2 against, the following (full rationale and numbers in `docs/theme-v2-revision-3.md`):

* **A new palette for new themes.** `theme_registry.REVISION_DEFAULTS[3]` makes `ink-400` 4.5:1 and `ink-300` 3:1 on the page (`ink-500` one step darker), `border-input` the `ink-300` step (3:1), and the `-600` steps of success, warning and info carry text and white text at 4.5:1. `default_theme_v2()` (and the Themes editor and the builder) start from it; `registry_revision=1|2` still reproduce SDK 1.3 and 1.4. A token's `default` is the generated CSS fallback and does not move, so every published theme, and a host without a theme, renders as before. The platform default release is `registry_data/default-theme-v2.json` (`fastlane` 2.0.0); `default-theme.json` stays `fastlane` 1.0.0.
* **UI contrast pairs.** 22 pairs (`group: "ui"` in the contrast rows): `ink-400`/`ink-500` on `surface` and `surface-page`, `accent-600`/`accent-700` on `surface` and `accent-50`, `on-primary` on `ink-900`/`ink-800`/`danger-600`/`success-600`, the status `-600` steps on `surface`, and the pairs of the new roles. All warnings except `on-inverse` on `inverse`. A pair marked `unless` is not judged for a theme that sets the role that replaces it.
* **Four optional roles**: `inverse`/`on-inverse` (a dark fill and its text; fallback `ink-900`/`surface`) and `accent-text` (4.5:1 on `surface` and `accent-50`)/`accent-ui` (3:1) (fallback `accent-600`), with Tailwind keys `bg-inverse`, `text-on-inverse`, `text-accent-text`, `bg-accent-ui`, `ring-focus`. `bg-inverse` used to be `surface-inverse` (unused by core and the apps); that is now `bg-surface-inverse`. `text-white`, `bg-ink-900` and `text-accent-600` resolve exactly as before.
* **Dark text is solved, not reversed** (`derive_dark` for revision 3 themes, `deriveDark` in the twin): `ink-300` to `ink-700` get at least the contrast the light palette gives them on its own surface (never less than 3:1 for 300, 4.5:1 for the text steps), `accent-text` and `accent-ui` are lifted until they read on the dark surface.
* **Font stacks**: a family whose name has a word starting with a digit must be quoted (`'Source Sans 3', ui-sans-serif, ...`); revision 3 warns when it is not. The grammar already accepted single quotes.

`tests/golden/frozen-r2` holds what SDK 1.4 produced for revision 2; `tests/test_theme_frozen_r2.py` and the TypeScript twin prove every byte is still produced.

Packs: format 2 carries `theme.json` and `sources.json` only (the layout lives in the manifest); `create_theme_pack_v2` builds it and `validate_theme_pack` accepts both formats.

### Default, removable applications

AppSpec and RegistryEntry support `default_enabled` independently of `always`. A default app is installed and enabled during new-tenant setup but can subsequently be disabled in Admin. An explicit disabled row must not be overwritten on restart. Themes is a default app maintained in fll-themes; its code is fetched from the app registry, not bundled into the SDK or core image. The SDK retains only the theme contract, catalog metadata and built-in fallback manifest.

### JSX theme template contract

`frontend/theme-contract.ts` defines stable presentation IDs and their typed properties. Templates are optional replacements for `layout.workspace`, `navigation.sidebar`, `navigation.item`, `navigation.topbar`, `page.header`, `surface.card`, `control.button`, `control.input`, `control.field`, `feedback.notice`, `chat.message` and `chat.composer`. An AppModule can provide `themeTemplates: { api_version: 1, templates: [...] }`. The enabled Themes app supplies this library; other apps cannot replace it.

Core compiles against a generated copy of the SDK contract (and the v2 resolver, registry, default CSS and Tailwind preset): `python scripts/sync_theme_contract.py /path/to/FastlaneLabs`. Core's CI clones the SDK tag its `requirements.txt` pins and fails when `frontend/src/generated` differs from it (the Themes app does the same for its skill's vendored validator). This avoids shipping developer build tooling in the production frontend image. App packages compile against the SDK directly and use `frontend/platform.d.ts` for the host UI/theme module declarations.

Workspace receives typed authorized product items, account actions and tenant metadata separately from its app-content children. Themes can compose different sidebar/topbar layouts with the host UI wrappers; callbacks, permissions, data and app mounting remain in core.

The host's theme resolver retains default components and callbacks, isolates preview selection, and falls back on missing or failed presentation components. New slot IDs or breaking property changes require a coordinated contract release. Only reviewed application code may supply JSX templates; this is not a sandbox for arbitrary code.

## Tests

`pip install -e . pytest && npm ci && python -m pytest tests`. The four tests that run the TypeScript twin and the Tailwind preset need node 20+ and `npm ci`; a local run without them skips those tests, but with `CI` or `JENKINS_URL` set (as in the Jenkinsfile) they fail instead, so a tag build always covers the TS twin. `package-lock.json` pins the dev dependencies; refresh it with `npm install` when `package.json` changes.
