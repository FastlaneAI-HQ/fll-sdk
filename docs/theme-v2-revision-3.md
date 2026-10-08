# Theme v2 revision 3 (SDK 1.5): fit for every theme

Written after a UI/UX audit of the default theme and of 14 generated themes (and 4 dark renders) found that the
validator said "ready" for themes in which 200 to 290 text runs failed WCAG AA. Decisions, in the order they were made.

## What the audit found

* The default theme's secondary text (`text-ink-400`, 3.1:1 on white, at 10.5 to 11.5px) caused most of its 355 AA failures, and form
  controls had 1.4:1 borders (the default was still a v1 theme, so `border-input` fell back to `ink-200`).
* Apps and core colour text with raw ramp steps (`text-ink-400/500`, `text-accent-600/700`) and `text-white` (an alias of
  `on-primary`) on `bg-ink-800/900` fills; the semantic roles the validator checks have no uses at all.
* The builder kept HLS lightness constant, so for yellow, green, teal and orange brands `ink-500` landed at 3.6 to 3.8:1.
* A dark palette was a mechanical reversal: `ink-400`/`ink-500` became 2.5 and 3.6:1 on the dark surface.

## Rules for a published revision

A revision never tightens. Revision 3 adds optional tokens (their fallback reproduces today's rendering), pairs that only a
theme that targets revision 3 is judged against (`Pair.since`), and a palette that only a NEW theme starts from
(`REVISION_DEFAULTS`). `Token.default` stays what it was: it is the generated CSS fallback, so a v1 theme (which sets 27
tokens and takes the rest from the fallback), every published v2 release and a host without a theme render as before.
`tests/golden/frozen-r1` and `tests/golden/frozen-r2` pin that, byte for byte, in Python and in the TypeScript twin.

## The new default palette

| step | revision 1 and 2 | revision 3 | on white | on `surface-page` |
| --- | --- | --- | --- | --- |
| `ink-300` | `#b8bac2` | `#898c98` | 3.35 (was 1.94) | 3.13 |
| `ink-400` | `#8f929e` | `#6b6e7d` | 5.06 (was 3.10) | 4.72 |
| `ink-500` | `#6c6f7d` | `#5f626e` | 6.07 (was 4.99) | 5.67 |
| `ink-600` and up | unchanged | unchanged | 7.16 | 6.69 |
| `border-input` | `{ink-200}` (1.4:1) | `{ink-300}` | 3.35 | 3.13 |
| `success-600` | `#059669` (3.77) | `#04855f` | 4.64 | |
| `warning-600` | `#d97706` (3.19) | `#bb5908` | 4.62 | |
| `info-600` | `#0284c7` (4.10) | `#027bbb` | 4.61 | |

`ink-300` is the icon, separator-with-boundary and control-boundary step (3:1 wherever a control draws its edge: apps
hard-code `border-ink-300`); `ink-200` stays the divider (1.4:1, decorative). `ink-400` and `ink-500` are text. The ramp stays
monotone in luminance, `ink-600` upward is untouched, and `danger-600` already met 4.5:1. Because apps read `var(--fl-ink-400)`
at run time, a tenant that pins the new `fastlane` 2.0.0 gets these values in every installed app without a rebuild.
A dark-tone navigation rail uses `ink-300` for its idle text; on the dark rail that is now 5.5:1 (it was 9:1).

## The UI pairs

Group `ui` in the contrast rows. All are warnings except `on-inverse` on `inverse` (a fill and its own text), judged for both palettes
of a theme with a dark palette.

| Pair | Minimum | Judged unless the theme sets |
| --- | --- | --- |
| `ink-400`, `ink-500` on `surface`, on `surface-page` | 4.5 | |
| `ink-400`, `ink-500` on `accent-50`; `ink-500` on `accent-100` (a caption in a selected row, a chip, a tile) | 4.5 | |
| `accent-600`, `accent-700` on `surface`, on `accent-50` | 4.5 | `accent-text` |
| `on-primary` on `ink-900`, `ink-800`, `danger-600`, `success-600` | 4.5 | `on-inverse` |
| `success-600`, `warning-600`, `danger-600`, `info-600` on `surface` | 4.5 | |
| `accent-text` on `surface`, on `accent-50` | 4.5 | |
| `accent-ui` on `surface` | 3 | |
| `on-inverse` on `inverse` (error), `danger-600`, `success-600` | 4.5 | |

The `unless` rule is the honest answer to a conflict a theme cannot resolve: with a yellow brand `on-primary` is dark, so
`text-white` on `bg-ink-900` cannot be readable, and `text-accent-600` on white cannot be both the brand fill and legible text.
A theme that sets `on-inverse` or `accent-text` says it has provided the role that the interface should use there; until core and the
apps move their classes to `bg-inverse text-on-inverse` and `text-accent-text`, those raw classes still render the old way.

## Roles and Tailwind keys

| Role | Fallback | Tailwind | Replaces |
| --- | --- | --- | --- |
| `inverse` | `{ink-900}` | `bg-inverse`, `border-inverse` | `bg-ink-900`, `bg-ink-800` as a dark fill |
| `on-inverse` | `{surface}` | `text-on-inverse` | `text-white` on a dark fill or a solid status fill |
| `accent-text` | `{accent-600}` | `text-accent-text` | `text-accent-600`, `text-accent-700` on a light surface |
| `accent-ui` | `{accent-600}` | `bg-accent-ui`, `border-accent-ui` | brand-coloured indicators (a selected border, a bar) |
| `focus-ring` (exists) | `{accent-500}` | `ring-focus`, `outline-focus` | |

`bg-inverse` was already a Tailwind key for `surface-inverse` (ink-950) and no class in core or the apps used it; it now follows
the new role and the old one is `bg-surface-inverse`. Every other existing class (`text-white`, `bg-ink-900`, `text-accent-600`)
resolves as before; `tests/test_theme_frontend.py` compares them with the 1.2 preset.

## Dark palette

`derive_dark` for a revision 3 theme re-solves `ink-300` to `ink-700` against the dark surface, the dark page and the dark accent tints: each
step gets at least the contrast the light palette gives it on its own surface (so the three-step hierarchy survives: 5.06, 6.12, ... on
the default), and never less than its floor (3:1 for `ink-300`, 4.5:1 for the text steps); a step that already reads is untouched. The steps
move toward white in whole percents (integer arithmetic, mirrored in `theme-resolve.ts`).

The text steps are also judged on the tints a selected row, a chip or a tile is filled with (`ink-400` on the dark `accent-50`; `ink-500` to
`ink-700` on `accent-50` and `accent-100`). A saturated brand (a green, a yellow) reverses into tints that are far brighter than the surface,
and lifting the text until it reads on them would put `ink-400` to `ink-700` on one near-white. So the tints are settled first: each is darkened
(channels scaled toward black, hue kept) until the steps that sit on it read, but never closer to the surface than 1.15:1 (`accent-50`) and 1.3:1
(`accent-100`), and `accent-50` stays darker than `accent-100`; only what is still short is lifted. `accent-text` and `accent-ui`, when they
point at an accent step, are lifted until they read on the dark surface (and on the dark `accent-50` for the text). The derived default palette
now has no contrast warning (revision 2: five).

## Fonts

A family with a word that starts with a digit (`Source Sans 3`, `Source Serif 4`) is not a valid unquoted CSS name: the browser drops the whole
`font-family`, and the UI renders in Times. The v2 grammar already allows single quotes. Revision 3 warns when such a family is unquoted;
the builder and the editor quote them.
