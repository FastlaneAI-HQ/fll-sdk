# Brand logo (registry revision 4)

A theme can carry the client's logo. It is data: a small image embedded in the manifest, drawn by the host as an `<img>`.
Nothing a theme carries can run code.

Status: part of registry revision 4 (not yet released), together with the layout tree. Implemented in `fastlanelabs_sdk.themes`
(`validate_brand`, `normalise_brand`, `brand_of`, `brand_logo_for`) and `frontend/theme-resolve.ts` (`validateBrand`, `normaliseBrand`, `brandOf`, `brandLogoFor`); the two
give identical results (same errors, paths, messages and order: `tests/test_layout_tree_parity.py` runs both over the cases of
`tests/test_brand.py`).

## Shape

A revision 4 theme may carry an optional top-level `brand` object. A theme at revision 3 or earlier must not (error at `brand`).

```jsonc
"brand": {
  "logo":    { "src": "data:image/png;base64,....", "alt": "Precision Hose", "height": 36 },  // wide logo
  "logo_dark": { "src": "data:image/png;base64,....", "alt": "Precision Hose" },               // optional: the logo drawn on dark backgrounds
  "mark":    { "src": "data:image/png;base64,....", "alt": "Precision Hose" },               // optional square mark
  "tagline": "Hose & expansion joints"                                                      // optional, shown on the sign-in page
}
```

* `logo.src` / `logo_dark.src` / `mark.src`: a `data:` URI, `data:image/(png|jpeg|webp|svg+xml);base64,<payload>`. No other scheme (no http, no
  relative path, no blob): the host never fetches anything on a theme's behalf. The scheme and the type are lowercase and exact
  (`DATA:` and `image/PNG` are errors); the payload is strict base64 (the standard alphabet, padded to a multiple of 4, no whitespace).
* Size: the **decoded** image is at most `max_image_bytes` (192 KiB) per image, and the decoded images of the whole `brand` together are at
  most `max_total_bytes` (320 KiB; the alt text and the tagline are not counted). An image over the limit is reported at its `src`; the total
  is reported at `brand`, counting only images with no other problem. The numbers come from the vocabulary, never from code.
* The payload must match its declared type by its magic bytes (PNG `89 50 4E 47 0D 0A 1A 0A`, JPEG `FF D8 FF`, WebP `RIFF`, any 4 bytes,
  `WEBP`). An empty payload is an error.
* An SVG is checked as text, and every problem is reported at its `src`, in this order (each at most once):
  1. It must be UTF-8 (`An SVG must be UTF-8 text`; a BOM is kept, so it fails the next step).
  2. *Structure.* No control characters other than tab, line feed and carriage return. It starts at `<svg` (lowercase, followed by a space,
     `/` or `>`) after any number of whitespace, `<?...?>` prolog, `<!--...-->` comments and one `<!DOCTYPE ...>`; it ends, after trailing
     whitespace and comments, with `</svg>` (or the whole root is one self-closing `<svg .../>`). This is the whole "well-formed" check: the
     SDK has no XML parser in common between Python and TypeScript.
  3. *Forbidden constructs*, found case-insensitively (ASCII) on the text **after decoding entities** (`&amp; &lt; &gt; &quot; &apos;` and
     numeric `&#106;` / `&#x6A;`, one pass; an invalid code point becomes U+FFFD): the tags `<script>`, `<foreignObject>`, `<iframe>`, `<image>`
     (with or without a namespace prefix); a `<use>` whose `href` or `xlink:href` does not start with `#`; `<!ENTITY`; a `<!DOCTYPE` with an
     internal subset (a `[` before its `>`; a plain DOCTYPE, as Illustrator writes it, is allowed); `@import`; any attribute whose local name
     starts with `on` (`onload`, `ONCLICK`, `xlink:onclick`); an attribute value, or a CSS `url(...)`, that holds a `javascript:` scheme
     (ASCII control characters and spaces are removed first, so `java&#9;script:` is caught); and one that holds a `data:`, `http:` or
     `https:` scheme (a scheme counts at the start of the value or after a character that is not a letter, digit, `+`, `.` or `-`, so the
     word `metadata:` is not one). `xmlns` and `xmlns:*` attributes are exempt (every SVG carries `xmlns="http://www.w3.org/2000/svg"`).
     The scan reads the text, not a parse tree, so text that merely looks like an attribute (`<title>onload="x"</title>`) is reported too:
     it errs on the side of rejecting. Strip `<metadata>` and editor namespaces (`rdf:about="http://..."`) before embedding.
  (It is drawn only through `<img>`, where browsers run no script and load nothing; the checks are defence in depth.)
* `alt`: 1 to `alt_max` (80) characters **after trimming**, counted in code points (an emoji is one), and no control characters (C0, DEL, C1,
  the line and paragraph separators U+2028/U+2029 and the bidirectional controls U+202A-202E and U+2066-2069). It is the image's accessible
  name. A logo is never decorative. Trimming removes spaces, no-break and other Unicode spaces and U+FEFF at both ends.
* `logo_dark` (optional): the logo drawn on **dark** backgrounds: a dark header or sidebar, a dark palette. It has the shape and every rule of
  `logo` (`{src, alt, height?}`; `alt` required; the same type, size, magic-byte and SVG checks, reported at `brand.logo_dark.src` and so on), and its
  decoded size counts toward the per-image and the total limits. It needs a `logo`: without one the error is at `brand.logo_dark` (`logo_dark needs a logo`),
  and the image itself is judged as well, right after. `logo_dark.height` is optional and defaults to the **logo's** height (the logo's own default when it
  has none), so the two logos swap without the layout shifting; give it a height only when the dark artwork needs another one.
* `logo.height`: an integer `height.min` to `height.max` (16 to 64 px), default `height.default` (32): the height the host draws the logo at in
  a bar or sidebar; the width follows the image's aspect ratio, capped at `max_logo_width_px` (240px). `logo_dark` has the same `height` rule. `mark` is drawn square at the host's
  brand-badge size, so it has no `height`.
* `tagline`: 1 to `tagline_max` (80) characters after trimming, same rules as `alt`.
* A brand must set at least one of `logo`, `mark`, `tagline` (`{}` is an error at `brand`; `logo_dark` alone does not count, it needs a `logo`). Unknown keys are errors, at every level
  (`brand.zzz`, `brand.logo.zoom`).
* Every error carries a path (`brand.logo.src`). Problems come in a fixed order: unknown keys of the brand (alphabetical), then `logo`, `logo_dark`, `mark`
  and `tagline` in that order (inside an image: its unknown keys, `src`, `alt`, `height`), then the size of all the images together.
* Revisions: `brand` in a theme that targets revision 3 or earlier is an error at `brand` (`brand needs registry_revision 4 or later`) and
  its content is not judged. `validate_theme` returns a valid theme unchanged (nothing is trimmed or defaulted in the manifest). The v1
  projection (`project_v1`) and the contrast report ignore the brand.

## What the host does with it

* `resolveTheme` returns `brand: { logo, logo_dark, mark, tagline } | null` next to `shell`. A theme with a brand gets all four keys, an absent part is
  `null`, `logo.height` and `logo_dark.height` are filled (the latter from the logo's height) and `alt` and `tagline` are trimmed (`normalise_brand`); a theme without a brand, every theme of revision 3
  or earlier and every v1 theme gets `null`. The goldens of revisions 1 to 3 do not contain the key and are compared without it.
* The layout tree's `brand` region (and the classic sidebar/navbar brand) draws `logo` when present, else `mark` in a narrow
  region (a rail, a collapsed bar), else the tenant's initials badge and name as before. The region option `logo` is
  `auto` (default: the logo, when the theme has one) / `hide` (never the logo: badge and name) / `only` (the logo alone, no name).
* The sign-in page, the invitation page, the first-run page and the session-expired dialog draw the logo and tagline, and follow the
  theme's colours, fonts and shape. These pages read the tenant's applied theme without signing in (see `GET /api/themes/public`).
* Dark backgrounds: the host asks `brandLogoFor(brand, onDark)` (Python `brand_logo_for(brand, on_dark)`) which logo to draw. On a dark background (a
  container whose tone is dark, a palette in dark mode) it returns `logo_dark` when the brand has one and `logo` otherwise; on a light one it returns `logo`;
  it returns `null` when there is no logo (a mark-only or tagline-only brand, or no brand). The result is `{src, alt, height}`. A theme whose one logo reads on
  both backgrounds needs no `logo_dark`.

## Ownership

The limits above live in the layout vocabulary file (the Themes app owns it): `brand.logo_limits` with `types`, `max_image_bytes`,
`max_total_bytes`, `alt_max`, `tagline_max`, `height: { min, max, default }` and `max_logo_width_px` (the host's drawing cap, not checked by
the validator). The SDK reads them from the vocabulary like every other limit; a vocabulary without `brand` (an older Themes app) falls back to
the built-in copy.

## API

| | Python (`fastlanelabs_sdk.themes`) | TypeScript (`theme-resolve.ts`) |
| --- | --- | --- |
| check a brand | `validate_brand(brand, vocabulary=None, path="brand") -> {errors, warnings}` | `validateBrand(brand, vocabulary?, path?) => { errors, warnings }` |
| defaults filled | `normalise_brand(brand, vocabulary=None)` | `normaliseBrand(brand, vocabulary?)` |
| for a theme | `brand_of(theme, vocabulary=None)` | `brandOf(theme, vocabulary?)` |
| the logo for a background | `brand_logo_for(brand, on_dark) -> {src, alt, height} \| None` | `brandLogoFor(brand: ResolvedBrand \| null, onDark: boolean) => (BrandImage & { height: number }) \| null` |
| in a theme | `check_theme`, `validate_theme` (path `brand...`), `resolve_theme(...)["brand"]` | `resolveTheme(theme).brand` |

Types (`theme-contract.ts`): `ThemeBrand` (as written), `BrandImage`, `ResolvedBrand` (normalised, with `logo_dark`), `BrandLogoLimits`, `ThemeManifestV2.brand?`
and `ResolvedTheme.brand`. `validateBrand` never throws; `normaliseBrand` assumes a valid brand. There are no warnings today (the key is there
for symmetry with `validate_shell`).

## Registry additions that came with it (revision 4)

A branded theme usually also wants these; they are ordinary registry entries, `since: 4`, and a revision 4 theme written before them stays valid.

* `nav-item-variant` gains `tab`: a horizontal navigation tab with no fill; the active item is marked by a thick bottom border in the active
  colour. `page-header-variant` gains `panel`: the page header sits in its own bordered card (a highlights panel); core draws it.
  The token entry carries `option_since` (`{ "tab": 4 }`): a theme that targets revision 3 or earlier gets the error it always got
  (`must be one of square, pill`). `Token.options_for(revision)` / `optionsFor(spec, revision)` give the options a revision offers.
* The sign-in card (`gate`) already had `gate-page-bg`, `gate-bg`, `gate-border`, `gate-radius`, `gate-max-width` and `gate-title-size`. New:
  `gate-shadow` (fallback `{shadow-sm}`), `gate-title-fg` (`{ink-900}`) and `gate-tagline-fg` (`{ink-600}`): what the sign-in page drew before they
  existed (the card's `shadow-sm`, the heading's `text-ink-900`, the lede's `text-ink-600`).
