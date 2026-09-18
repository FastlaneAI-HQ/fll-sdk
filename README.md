# fll-hq

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

## Installing an app

Core's `deploy/install_apps.py` reads `apps.yaml`, `pip install`s each
requested app's `backend/` subdirectory and `npm install`s its (repo-root)
frontend package, then generates the binding files core reads at startup. See
that script, and the main FastlaneLabs repo's plan doc, for the full flow.
