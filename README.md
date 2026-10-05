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

App CI runs `frontend/build-app.mjs` and publishes `app.js` and `app.css` with a frontend API version and SHA-256 hashes. The bundle uses the host's React, JSX runtime and platform API. Shared form primitives are available as `fastlanelabs/ui` (Field, Button, Notice and inputClass); the public types live in `frontend/contracts.ts`. Do not bundle a separate React instance or import core's private source paths.

`AppPlugin.unload` is optional for stateless apps and required when an app owns connection pools, transport tasks, workers or caches. It must stop/release those resources without deleting persistent content. Disabled app routes and graph references are removed; in-flight calls retain their references until they finish. Native dependencies shared with the platform are not process-isolated.

Themes use `themes.validate_theme`, API v1. They supply the complete ink/accent palettes, surface, primary text, font stacks, radius and supported layout choices. They cannot execute code or replace authentication/application behavior. Theme source and publishing rules live in the separate `fll-themes` repository.

### Default, removable applications

AppSpec and RegistryEntry support `default_enabled` independently of `always`. A default app is installed and enabled during new-tenant setup but can subsequently be disabled in Admin. An explicit disabled row must not be overwritten on restart. Themes is a default app maintained in fll-themes; its code is fetched from the app registry, not bundled into the SDK or core image. The SDK retains only the theme contract, catalog metadata and built-in fallback manifest.
