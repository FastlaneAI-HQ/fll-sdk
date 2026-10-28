# Theme v2 dark mode

Decisions, in the order they were made.

## Why this shape

* **Dark mode is data in the manifest, not a second theme.** A tenant pins one release; the user picks the mode. One id and version means one hash, one immutable release and one pin.
* **`color_scheme` says what a theme offers; `modes.dark` says how.** `light` and `dark` themes carry a single palette in `tokens`; an `auto` theme carries the light palette in `tokens` and a sparse dark override in `modes.dark`. The user's choice (light, dark or system) is local to the browser and is never part of a theme.
* **No new token.** A mode overrides existing tokens, so the registry's token counts and fallbacks are the same for a light theme and a dark one.
* **A dark palette is complete in colour and sparse elsewhere.** It must set all 66 ramp colours, `surface` and `on-primary`. A half-remapped palette (new ink, old status colours) produces glaring pastel boxes on a dark page, and a contrast check cannot see that. Everything else it may override is a colour, a shadow, a bar tone or a scrim opacity; type, spacing, radius and layout are one design.
* **Same checks, same thresholds.** Every pair judged for light is judged for dark, and a dark palette must also have lighter text than surface (contrast alone accepts the reverse).

## Resolution

`resolve_theme(theme, mode)` merges `modes.dark` over `tokens` layer by layer, then resolves references against the merged map. A key only the dark block sets (a bar tone) is present in the dark result and absent in the light one, so the host's stale-key removal clears it on the way back. Output for a `light` theme has no `scheme` key, no `data-fl-mode` and no `mode` on contrast rows.

The host sets `data-fl-mode` on the root. Static CSS (never tenant text) turns that into `color-scheme: dark` and the platform hue ramps' dark values. The mode itself is chosen by the host: the only one the theme offers, else the user's stored choice, else `prefers-color-scheme`.

## The derived palette

Reversing every ramp is the whole idea: `ink-50` is the page and `ink-950` the strongest text in light; in dark the same names hold the opposite ends, so `bg-ink-50`, `text-ink-900`, `border-ink-200`, `bg-accent-600` and the status classes render correctly dark with no new classes. Reversal alone gets these things wrong, which `derive_dark` sets by hand:

| Piece | Why reversal is wrong | Derived value |
| --- | --- | --- |
| `surface` | white reverses to black, flush with the page | midpoint of `ink-50` and `ink-100` (cards lift off the page) |
| `on-primary` | white on a now-light primary fails | the end of the ramp that reads best on the primary colour |
| accent steps | a brand's reversed `accent-600` can be too dark for a link or too light for white text | the steps the theme's `text-link`, `focus-ring` and `primary` roles point at are moved toward white or black in tenths until the pairs hold |
| `scrim` | `ink-950` is now the lightest colour | `#000000` (and 0.6 opacity) |
| shadows | a faint dark shadow vanishes on dark | alpha x2.5 (capped 0.85), black |
| sidebar and navbar | the `dark` tone is light-looking on reversed ramps | both bars use the `light` tone |
| active nav item, user message | `ink-800`/`ink-900` fills become the lightest colour on the page | a quiet `ink-200` fill with the plain text colour (only when the theme does not set them) |

A literal colour a theme sets outside its ramps is mapped to the dark value of the ramp step it equals, or has its HSL lightness reflected. A bar painted by hand (`sidebar-bg`, `navbar-bg`) falls back to the surface in dark; a derived palette cannot know which dark colour the brand wants there.

Reversal also leaves the secondary text steps at 2.5 to 3.6:1 on the dark surface, so `derive_dark` then re-solves `ink-300` to `ink-700` against the dark surface, the dark page and the dark accent tints, and lifts the steps `accent-text` and `accent-ui` point at (`docs/theme-v2-palette.md`, "Dark palette").

The Python and TypeScript implementations are the same arithmetic (integer midpoints, `floor(x + 0.5)` rounding, no locale formatting); `tests/golden/theme-resolve/*.json` holds the expected `derive` output and both languages must reproduce it.

## Hosts

A host whose SDK reads another registry revision refuses the manifest ("Update the workspace" for a newer one) and falls back to the default theme with a logged warning. Roll out the SDK, then core, then the Themes app.

## Platform hue ramps

Core and the apps use Tailwind's other palettes as decoration (a violet badge, a slate rule). Those are not theme tokens: a tenant cannot configure them. The generated defaults declare `--fl-hue-<name>-<shade>` for 18 hues, Tailwind's own values in light and the reversed ramp under `[data-fl-mode='dark']`, and the shared preset reads them. `text-black` follows the mode (`--fl-black`); `bg-black/NN` overlays stay black. The four status hues (`red`, `amber`, `emerald`, `sky`) remain theme tokens.
