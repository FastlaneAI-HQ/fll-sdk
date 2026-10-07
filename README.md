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

Themes use `themes.validate_theme`, API v1. They supply the complete ink/accent palettes, surface, primary text, font stacks, radius and supported layout choices. The JSON manifest cannot execute code. Separately reviewed JSX templates may rearrange registered presentation slots while authentication and application behavior remain host-owned. Theme source and publishing rules live in the separate `fll-themes` repository.

`theme_packs.create_theme_pack` and `validate_theme_pack` provide the data-only ZIP contract for client uploads. The four root JSON entries carry an immutable client identity, checksummed manifest, bounded layout tree, supported component variants and source evidence. `ThemePackError.errors` identifies invalid files/fields. No uploaded code executes. `frontend/theme-pack-contract.ts` types validated definitions; only the enabled Themes app's optional `createThemePackTemplates` factory compiles them into reviewed presentation components. The host merges imported components separately from its reviewed library and offloads both when Themes is removed.

### Theme API v2

`themes.validate_theme` accepts API v1 (frozen: its output is hashed into published releases) and API v2. A v2 manifest (`api_version: 2`, `registry_revision`) layers **primitives** (every ramp, font family, type size, weight, spacing step, radius, shadow, motion and focus value; all required, literal), **semantic roles** (surfaces, text, lines, brand and four status families; all required, literal or `{token}` references) and **component tokens** (optional; an unset token follows its registry fallback live). `layout` selects enumerated variants: sidebar side, style, surface, width, behavior and collapse breakpoint; navbar position, behavior, height and alignment; content width, alignment, padding and gap; scroll model and density. There is no free CSS: values come from a closed grammar and reach the DOM only as validated custom properties.

`fastlanelabs_sdk/theme_registry.py` is the single source of truth for every token, its type, range, fallback and the revision that introduced it. `scripts/gen_theme_registry.py` generates `registry_data/theme-registry-v2.json`, `frontend/theme-registry.json`, `frontend/theme-defaults.css`, `frontend/tailwind-preset.mjs` and `docs/theme-v2-tokens.md`; a test fails when any is stale. The registry grows by `registry_revision` (new tokens are optional and reproduce the previous rendering), never by tightening an existing rule, so a stored release stays valid under every later validator. `color_scheme` must be `light` and `modes` is reserved.

`themes.check_theme` returns every error and warning with a field path and the contrast report; `validate_theme` returns a copy of a valid manifest and never injects defaults. `resolve_theme` flattens a manifest into CSS variables, root attributes, workspace-frame attributes and allow-listed webfonts; `upgrade_v1` views a v1 theme (and optionally its presentation) as v2 at read time, and `project_v1` produces the v1 manifest an older client can apply. `frontend/theme-resolve.ts` is the TypeScript twin; shared fixtures in `tests/golden` keep the two in step. v1 themes keep their own render path; an upgrade is an approximation used by editors and forks.

Packs: format 2 carries `theme.json` and `sources.json` only (the layout lives in the manifest); `create_theme_pack_v2` builds it and `validate_theme_pack` accepts both formats.

### Default, removable applications

AppSpec and RegistryEntry support `default_enabled` independently of `always`. A default app is installed and enabled during new-tenant setup but can subsequently be disabled in Admin. An explicit disabled row must not be overwritten on restart. Themes is a default app maintained in fll-themes; its code is fetched from the app registry, not bundled into the SDK or core image. The SDK retains only the theme contract, catalog metadata and built-in fallback manifest.

### JSX theme template contract

`frontend/theme-contract.ts` defines stable presentation IDs and their typed properties. Templates are optional replacements for `layout.workspace`, `navigation.sidebar`, `navigation.item`, `navigation.topbar`, `page.header`, `surface.card`, `control.button`, `control.input`, `control.field`, `feedback.notice`, `chat.message` and `chat.composer`. An AppModule can provide `themeTemplates: { api_version: 1, templates: [...] }`. The enabled Themes app supplies this library; other apps cannot replace it.

Core compiles against a generated copy of the SDK contract (and the v2 resolver, registry, default CSS and Tailwind preset): `python scripts/sync_theme_contract.py /path/to/FastlaneLabs`. Its local contract synchronization test detects drift. This avoids shipping developer build tooling in the production frontend image. App packages compile against the SDK directly and use `frontend/platform.d.ts` for the host UI/theme module declarations.

Workspace receives typed authorized product items, account actions and tenant metadata separately from its app-content children. Themes can compose different sidebar/topbar layouts with the host UI wrappers; callbacks, permissions, data and app mounting remain in core.

The host's theme resolver retains default components and callbacks, isolates preview selection, and falls back on missing or failed presentation components. New slot IDs or breaking property changes require a coordinated contract release. Only reviewed application code may supply JSX templates; this is not a sandbox for arbitrary code.
