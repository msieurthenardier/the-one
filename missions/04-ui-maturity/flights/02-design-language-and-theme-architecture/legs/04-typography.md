# Leg: 04-typography

**Status**: completed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Self-host Geist Sans + Geist Mono variable-font WOFF2 files, define a typography scale (display/headline/body/caption/mono) as CSS custom properties, and apply across components — Geist Sans for UI/prose, Geist Mono for data (timestamps, numerics, IDs, tool messages, `// SECTION` headers). Minimal FOUC: fonts load with `font-display: swap` and metric-compatible fallbacks (`system-ui` for sans, `ui-monospace` for mono) so the brief fallback render before swap doesn't reflow noticeably. SIL OFL license preserved alongside the font files.

## Context

- This is the typography leg of F2. Pure additive: introduces new font assets + typography scale tokens; updates CSS rules to reference them.
- **Leg 03 outcome**: tron-style design language landed (cyan accent `#22d3ee`, glowing borders, translucent panels, `// ` section header prefixes via `::before`). Body still uses fallback monospace `'SF Mono', 'Fira Code', monospace`. This leg replaces that with Geist.
- **License**: Geist is published under SIL Open Font License 1.1 (per `vercel/geist-font` GitHub repo). Self-hosting permitted; we ship a `LICENSE.txt` alongside the WOFF2 files to satisfy the OFL's "preserve copyright and license notices" requirement.
- **File source**: WOFF2 variable-font files from `vercel/geist-font` GitHub repo. Two files: Geist Sans VF (~70-80KB) + Geist Mono VF (~70-80KB). Total ~150KB self-hosted.
- **No FOUC**: `font-display: swap` shows fallback while font loads, then swaps. No layout shift if metric-compatible fallbacks chosen (`system-ui` for sans, `ui-monospace` for mono).
- **Test constraint**: F1 browser tests pass. Tests don't make typography assertions (no font-family/size assertions in any flow test — verified during F1 review). Visual snapshots don't exist yet (leg 08 establishes them).
- **Variable fonts**: a single WOFF2 file contains all weights via the variation axis. Smaller than loading multiple static weight files. Browser support: Chrome 62+, Firefox 62+, Safari 11+ — all 2017-2018, well below Playwright's floor.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-03 landed (uncommitted)
- `the_one/interfaces/web/static/css/tokens.css` — has theme tokens; this leg adds typography tokens (theme-agnostic)
- `the_one/interfaces/web/static/css/{base,components,chat,studio,admin}.css` — currently use `font-family: inherit` mostly; body sets `'SF Mono', 'Fira Code', monospace` as the fallback
- `the_one/interfaces/web/static/index.html` — has `@layer` declaration + theme.js + tokens.css link + 5 component links
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing
- Network access available for downloading WOFF2 files from GitHub

## Outputs

**New files**:
- `the_one/interfaces/web/static/fonts/Geist-VF.woff2` — Geist Sans Variable Font (~70-80KB)
- `the_one/interfaces/web/static/fonts/Geist-Mono-VF.woff2` — Geist Mono Variable Font (~70-80KB)
- `the_one/interfaces/web/static/fonts/LICENSE.txt` — SIL Open Font License 1.1 text (preserve OFL copyright & license notices)
- `the_one/interfaces/web/static/css/fonts.css` (new) — `@font-face` declarations + typography scale tokens

**Files modified**:
- `the_one/interfaces/web/static/index.html` — add `<link rel="stylesheet" href="/static/css/fonts.css">` in `<head>` BEFORE tokens.css and the component CSS links (so font-face is registered early; keeps the layer declaration first)
- `the_one/interfaces/web/static/css/base.css` — `body` font-family changes from monospace fallback to `var(--font-family-sans)`
- `the_one/interfaces/web/static/css/{chat,studio,admin}.css` — apply Geist Mono explicitly to data-y contexts (timestamps, numerics, IDs, tool messages, etc.) via `font-family: var(--font-family-mono)`. Use `var(--font-size-*)` and `var(--font-weight-*)` tokens to replace hardcoded `font-size`/`font-weight` values across all rules.

## Acceptance Criteria

### Font assets
- [ ] `the_one/interfaces/web/static/fonts/Geist-VF.woff2` exists (~70-80KB)
- [ ] `the_one/interfaces/web/static/fonts/Geist-Mono-VF.woff2` exists (~70-80KB)
- [ ] `the_one/interfaces/web/static/fonts/LICENSE.txt` exists with SIL Open Font License 1.1 text + Vercel copyright (download from `vercel/geist-font` repo's LICENSE file)

### CSS file
- [ ] `the_one/interfaces/web/static/css/fonts.css` exists, opens with `@layer base { ... }` (font-face + typography tokens go in base layer — they precede everything)
- [ ] File contains TWO `@font-face` declarations (one each for `'Geist'` and `'Geist Mono'`), with `font-display: swap`, variable-font format (`format("woff2-variations")` or `format("woff2") tech("variations")`), `font-weight` range (e.g., `100 900`)
- [ ] File contains typography scale tokens at root level (since typography is theme-agnostic):
  - `--font-family-sans: 'Geist', system-ui, -apple-system, sans-serif`
  - `--font-family-mono: 'Geist Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', monospace`
  - Size scale: `--font-size-display` (24px), `--font-size-h1` (18px), `--font-size-h2` (16px), `--font-size-body-lg` (14px — used by chat messages), `--font-size-body` (13px), `--font-size-body-sm` (12px), `--font-size-caption` (11px), `--font-size-tiny` (10px)
  - Weights: `--font-weight-regular` (400), `--font-weight-medium` (500), `--font-weight-semibold` (600 — used by .save-btn, .app-flash, etc.), `--font-weight-bold` (700)
  - Line heights: `--line-height-tight` (1.2), `--line-height-normal` (1.5)

### HTML wiring
- [ ] `index.html` `<head>` has `<link rel="stylesheet" href="/static/css/fonts.css">` placed BEFORE the tokens.css link (so font-face is registered as early as possible)
- [ ] No other index.html changes

### Body font
- [ ] `base.css` `body` font-family is `var(--font-family-sans)` (was monospace fallback)

### Geist Mono application (explicit)
- [ ] `chat.css`: telemetry numerics (`.telemetry .value`, `.telemetry .t-ctx-pct`) use `font-family: var(--font-family-mono); font-variant-numeric: tabular-nums`
- [ ] `chat.css`: tool message body (`.msg.tool`) uses `font-family: var(--font-family-mono)` (it's code/output)
- [ ] `chat.css`: session-item-agent (the small agent badge in session list) uses `font-family: var(--font-family-mono)` (it's an identifier)
- [ ] `studio.css`: section titles (`.section-title`) use `font-family: var(--font-family-mono)` (the `//` cyberpunk prefix reads better in mono)
- [ ] `admin.css`: section titles (`.admin-section-title`, `.admin-pf-models-title`, `.admin-pf-section-label`) use Geist Mono (same rationale)
- [ ] `admin.css`: model row name + size, telemetry-like numerics use Geist Mono (`.admin-pf-model-name`, `.admin-pf-model-size`, `.admin-pf-vram-summary`, etc.)
- [ ] `admin.css`: provider type badge (`.admin-provider-badge`) uses Geist Mono (it's an identifier label)
- [ ] `admin.css`: env-var hints in admin field (`.admin-field-env`) use Geist Mono (they're code-like — env var names)

### Typography scale tokens applied
- [ ] All hardcoded `font-size: Npx` values across the 5 component CSS files replaced with `var(--font-size-*)` tokens (per the size scale above)
- [ ] All hardcoded `font-weight: N` values replaced with `var(--font-weight-*)` tokens
- [ ] All hardcoded `line-height: N` values replaced with `var(--line-height-*)` tokens (or kept if they're context-specific, e.g., 1.4 in vram-warning)
- [ ] Grep check: `grep -nE "font-size:\s*[0-9]" the_one/interfaces/web/static/css/*.css | grep -v fonts.css` returns minimal/zero matches (any remaining literal font-sizes are intentional exceptions; document inline)

### Behavioral
- [ ] All F1 browser tests still pass (`pytest -m browser tests/browser/` shows 8 passed)
- [ ] Default `pytest tests/` shows 350 passed, 16 deselected
- [ ] No `console.error` on page load (especially: no font-loading errors)
- [ ] Manual visual check: app renders with Geist Sans in body text, Geist Mono in data contexts; no FOUC observed (network throttled to slow 3G in DevTools should show fallback briefly then swap to Geist)

### License compliance
- [ ] `LICENSE.txt` is present in `static/fonts/` and contains the OFL 1.1 text + Vercel copyright (verbatim from upstream)
- [ ] WOFF2 files are not modified from upstream (per OFL "Reserved Font Name" clause — but since we're using the unmodified upstream we just include the license)

## Verification Steps

1. **Font assets present**:
   ```bash
   ls -la the_one/interfaces/web/static/fonts/
   # Expect: Geist-VF.woff2, Geist-Mono-VF.woff2, LICENSE.txt
   ```

2. **HTML wiring**:
   ```bash
   grep -n "fonts.css\|tokens.css\|@layer" the_one/interfaces/web/static/index.html
   # Expect order: <style>@layer ...> first, then theme.js, then fonts.css, then tokens.css, then component CSS files
   ```

3. **CSS file structure**:
   ```bash
   head -30 the_one/interfaces/web/static/css/fonts.css
   # Expect: @layer base { ... } wrapping @font-face + typography tokens
   ```

4. **Tests pass**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
   Expected: 350/16 deselected; 8 browser tests pass.

5. **Hex/rgba grep still clean** (no regression from leg 02/03):
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
   ```
   Expected: empty output.

6. **Manual visual check**:
   ```bash
   docker compose up -d --build
   ```
   Open http://localhost:8484:
   - Body text renders in Geist Sans (clean geometric, slightly more refined than the prior monospace)
   - Telemetry numerics, tool messages, section headers (`// IDENTITY` etc.), model names, env-var hints render in Geist Mono
   - DevTools → Network → throttle to "Slow 3G" and reload: should see fallback font briefly, then swap to Geist (no FOUC)
   - DevTools → Sources: confirm Geist-VF.woff2 and Geist-Mono-VF.woff2 load successfully
   - Computed style on `body`: `font-family` should resolve to "Geist" + fallback chain

## Implementation Guidance

### 1. Download Geist fonts

The `vercel/geist-font` GitHub repo's exact layout has shifted across releases (paths like `packages/geist-sans/dist/fonts/`, `packages/next/dist/fonts/`, etc.). Don't blindly copy URLs — verify the current layout first.

**Step 1: Discover the actual upstream paths.** Use the GitHub API or `gh` CLI to list the WOFF2 files:

```bash
# Option A: gh CLI
gh api repos/vercel/geist-font/contents/packages | grep '"name"'

# Option B: GitHub web UI
# Browse https://github.com/vercel/geist-font and navigate to find:
#   - Geist Sans Variable: packages/geist-sans/dist/fonts/geist-sans/Geist-Variable.woff2 (or similar)
#   - Geist Mono Variable: packages/geist-mono/dist/fonts/geist-mono/GeistMono-Variable.woff2 (or similar)

# Option C: search for woff2 files
gh search code --repo vercel/geist-font filename:*.woff2
```

**Step 2: Pin to a specific release tag** for reproducibility. Browse `https://github.com/vercel/geist-font/releases` and pick the latest stable release (e.g., `v1.4.x`). Record the tag in `fonts.css` as a comment.

**Step 3: Download.** Once you know the actual paths, download via `curl` against `raw.githubusercontent.com/vercel/geist-font/<TAG>/<PATH>`:

```bash
mkdir -p the_one/interfaces/web/static/fonts
cd the_one/interfaces/web/static/fonts

# Replace <TAG> and <PATH> with verified values:
TAG="<RELEASE_TAG>"  # e.g. v1.4.0
SANS_PATH="<UPSTREAM_PATH_TO_SANS_VF>"
MONO_PATH="<UPSTREAM_PATH_TO_MONO_VF>"

curl -fL -o Geist-VF.woff2 \
  "https://raw.githubusercontent.com/vercel/geist-font/${TAG}/${SANS_PATH}"
curl -fL -o Geist-Mono-VF.woff2 \
  "https://raw.githubusercontent.com/vercel/geist-font/${TAG}/${MONO_PATH}"

# License file — try common names in order:
curl -fL -o LICENSE.txt "https://raw.githubusercontent.com/vercel/geist-font/${TAG}/LICENSE" \
  || curl -fL -o LICENSE.txt "https://raw.githubusercontent.com/vercel/geist-font/${TAG}/LICENSE.md" \
  || curl -fL -o LICENSE.txt "https://raw.githubusercontent.com/vercel/geist-font/${TAG}/LICENSE.TXT"

ls -la
# Verify: Geist-VF.woff2 (~70-80KB), Geist-Mono-VF.woff2 (~70-80KB), LICENSE.txt (SIL OFL 1.1 text)
```

**Step 4: Verify file integrity.** Confirm the WOFF2 files are valid by checking magic bytes (`xxd -l 4 Geist-VF.woff2` should show `wOF2`). If `xxd` is unavailable, just confirm sizes are in the 50-100KB range (a 0-byte or HTML-error-page file is the most likely failure mode).

**Step 5: Record the pinned version in fonts.css.** Add a comment at the top of `fonts.css`:

```css
/* Geist + Geist Mono — pinned to vercel/geist-font@<TAG>
 * License: SIL Open Font License 1.1 (see fonts/LICENSE.txt)
 * Source: https://github.com/vercel/geist-font/tree/<TAG>
 */
```

If `curl` is unavailable, use `wget`, or download manually via browser and place the files in `static/fonts/`.

### 2. Create `the_one/interfaces/web/static/css/fonts.css`

```css
/* Geist + Geist Mono — self-hosted variable fonts.
 *
 * License: SIL Open Font License 1.1 (see fonts/LICENSE.txt).
 * Source: https://github.com/vercel/geist-font (pinned to current release).
 *
 * Variable fonts: a single WOFF2 file contains the full weight axis
 * (100-900). Browser samples weights via `font-weight: N` per rule.
 */

@layer base {
  @font-face {
    font-family: 'Geist';
    src: url('/static/fonts/Geist-VF.woff2') format('woff2-variations');
    font-weight: 100 900;
    font-style: normal;
    font-display: swap;
  }

  @font-face {
    font-family: 'Geist Mono';
    src: url('/static/fonts/Geist-Mono-VF.woff2') format('woff2-variations');
    font-weight: 100 900;
    font-style: normal;
    font-display: swap;
  }

  /* Typography scale — theme-agnostic (Geist is the same in dark and light).
     Lives in :root (NOT in [data-theme] blocks) since typography doesn't
     vary per theme. The flight design's "no :root for theme tokens" rule
     specifically excludes typography scale and color-scheme meta-property. */
  :root {
    --font-family-sans: 'Geist', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --font-family-mono: 'Geist Mono', 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace;

    --font-size-display: 24px;
    --font-size-h1: 18px;
    --font-size-h2: 16px;
    --font-size-body: 13px;
    --font-size-body-sm: 12px;
    --font-size-caption: 11px;
    --font-size-tiny: 10px;

    --font-weight-regular: 400;
    --font-weight-medium: 500;
    --font-weight-bold: 700;

    --line-height-tight: 1.2;
    --line-height-normal: 1.5;
  }
}
```

> **Note on `format('woff2-variations')` vs `format('woff2') tech('variations')`**: both are valid CSS Fonts Level 4 syntax. `format('woff2-variations')` is the older form, supported since Chrome 62. The newer `format('woff2') tech('variations')` is the spec-correct form (supported since Chrome 99+). Either works; the older form is broader-compatible and we already require Chrome 99+ for `@layer`, so either is safe. Going with `format('woff2-variations')` for the snippet — simplest.

### 3. Update `the_one/interfaces/web/static/index.html`

Add the fonts.css link BEFORE tokens.css. Current head (post-leg-02):

```html
<style>@layer tokens, base, components, areas, utilities;</style>
<script src="/static/js/theme.js"></script>
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/base.css">
... (other component links)
```

Becomes:

```html
<style>@layer tokens, base, components, areas, utilities;</style>
<script src="/static/js/theme.js"></script>
<link rel="stylesheet" href="/static/css/fonts.css">
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/base.css">
... (other component links)
```

(One line added; no other changes.)

### 4. Update `base.css`

Find the `body` rule and update font-family:

```css
@layer base {
  body {
    font-family: var(--font-family-sans);  /* was: 'SF Mono', 'Fira Code', monospace */
    background: var(--bg-gradient);
    color: var(--fg);
    height: 100vh;
    display: flex;
  }
}
```

### 5. Apply Geist Mono to data contexts

Walk through chat.css, studio.css, admin.css and add `font-family: var(--font-family-mono)` to the rules listed in Acceptance Criteria. Examples:

**chat.css**:
```css
.area-chat .telemetry .value {
  color: var(--fg-secondary);
  font-family: var(--font-family-mono);
  font-variant-numeric: tabular-nums;
}
.area-chat .msg.tool {
  /* ... existing properties ... */
  font-family: var(--font-family-mono);
}
.area-chat .session-item-agent {
  /* ... */
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
}
```

**studio.css**:
```css
.area-studio .section-title {
  font-family: var(--font-family-mono);
  font-size: var(--font-size-tiny);
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--fg-muted);
  margin-bottom: 12px;
}
```

**admin.css**:
```css
.area-admin .admin-section-title,
.area-admin .admin-pf-models-title,
.area-admin .admin-pf-section-label {
  font-family: var(--font-family-mono);
  /* ... */
}
.area-admin .admin-provider-badge {
  font-family: var(--font-family-mono);
  /* ... */
}
.area-admin .admin-pf-model-name,
.area-admin .admin-pf-model-size {
  font-family: var(--font-family-mono);
  /* ... */
}
.area-admin .admin-field-env {
  font-family: var(--font-family-mono);
  /* ... */
}
```

### 6. Replace hardcoded font-size / font-weight values

Walk through each component CSS file and replace literal sizes/weights with tokens. Use this mapping:

| Literal | Token | Notes |
|---|---|---|
| `font-size: 24px` | `var(--font-size-display)` | (rare) |
| `font-size: 18px` | `var(--font-size-h1)` | (rare) |
| `font-size: 16px` | `var(--font-size-h2)` | editor-title, admin-title |
| `font-size: 14px` | `var(--font-size-body)` (or h2 — pick contextually) | body text in chat/studio (consider promoting to var(--font-size-body) at 13px or keeping 14px and adding a body-lg token; recommend keep 14 for chat messages — add `--font-size-body-lg: 14px` if needed) |
| `font-size: 13px` | `var(--font-size-body)` | most common |
| `font-size: 12px` | `var(--font-size-body-sm)` | |
| `font-size: 11px` | `var(--font-size-caption)` | |
| `font-size: 10px` | `var(--font-size-tiny)` | section labels, badges |
| `font-weight: 400` | `var(--font-weight-regular)` | |
| `font-weight: 500` | `var(--font-weight-medium)` | |
| `font-weight: 600` | (add `--font-weight-semibold: 600` to scale OR keep 600 literal) | save-btn, app-flash use 600 — RECOMMEND adding the token rather than keeping literal |
| `font-weight: 700` | `var(--font-weight-bold)` | titles |

> **If `font-weight: 600` appears in styles, ADD a `--font-weight-semibold: 600` token** to fonts.css to cover it. Don't keep literal 600 unless intentional.

### 7. `chip-add` font handling

`.area-studio .chip-add` was previously inherited from sidebar; verify font-family inherits to `var(--font-family-sans)` (default body) — should be fine via cascade.

### 8. Run verification

```bash
# Tests
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60

# Hex/rgba grep (still must be clean)
grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
  | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"

# Hardcoded font-size grep (informational — should be near-zero, intentional exceptions OK)
grep -nE "font-size:\s*[0-9]+px" the_one/interfaces/web/static/css/*.css \
  | grep -v fonts.css
```

```bash
# Manual visual
docker compose up -d --build
# Open http://localhost:8484
# DevTools → Computed → body → font-family should resolve to Geist
# DevTools → Network → confirm Geist-VF.woff2 and Geist-Mono-VF.woff2 load
# Throttle to slow 3G, reload — fallback then swap to Geist
```

## Edge Cases

- **OFL license terms**: SIL OFL 1.1 requires preserving copyright/license notices when redistributing. We satisfy this by shipping `LICENSE.txt` alongside the WOFF2 files. The OFL's "Reserved Font Name" clause prohibits using "Geist" in a derivative font's name without permission — we don't derive, just redistribute the upstream files. ✓ Compliant.

- **CDN vs self-host trade-off**: self-hosting avoids cross-origin font loads on the critical path. Geist's npm package serves via Vercel's CDN if installed via Next.js. We're not using Next, and self-hosting is the project constraint per F2 mission requirements. The ~150KB total payload is acceptable for a localhost-or-private-deployment dev tool.

- **Font subsetting**: full Geist VF supports a wide character range. For a dev tool with English-only UI, we could subset to Latin only (~30KB savings). NOT in scope for leg 04 — the full VF is fine; subsetting can be a future optimization.

- **Variable font weight axis**: `font-weight: 100 900` declares the supported range. Browser computes intermediate weights smoothly. If a rule sets `font-weight: 500` and the browser interpolates, render quality is fine.

- **Fallback chain matters during load**: `system-ui` is a metric-aware fallback that minimizes layout shift when Geist swaps in. Same for `ui-monospace` for mono. These are designed to be close-enough metrics so font-display: swap doesn't reflow noticeably.

- **`font-display: swap` may show fallback for ~3 seconds** (browser default block period is short, swap period is up to 3s). On localhost, fonts load in <100ms — usually no visible swap. On a slow connection, brief fallback is fine; alternative `font-display: optional` shows fallback if font isn't cached, which is more aggressive but not what we want.

- **`font-feature-settings`**: Geist Mono supports tabular-nums, ligatures, etc. We use `font-variant-numeric: tabular-nums` explicitly on numeric data; other features (ligatures) are off by default — fine.

- **Existing tests**: F1 browser tests assert on text content and element presence, not on computed font-family. Switching to Geist doesn't break them.

- **`docker compose up --build` rebuilds the image**, which copies the new font files into the container. If a user has the old container cached, hard-reload the browser to pull new fonts.

- **Geist VF naming convention**: upstream may use `GeistVF.woff2`, `Geist-VF.woff2`, `Geist-Variable.woff2`, etc. The exact filename depends on the upstream release. The leg's `Geist-VF.woff2` is a target — implementer should rename or reference whatever the actual upstream filename is.

## State-Machine Reachability Audit

This leg introduces no new states. CSS rule additions only. Font assets added; no DB schema changes.

✓ Pass.

## Cache Freshness Contract

- **Browser font cache**: fonts are cached by the browser per URL. After deploy, browser fetches the new files automatically (HTTP cache headers may delay; `Ctrl+F5` clears).
- **No new in-process caches.**

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/fonts/Geist-VF.woff2` — new
- `the_one/interfaces/web/static/fonts/Geist-Mono-VF.woff2` — new
- `the_one/interfaces/web/static/fonts/LICENSE.txt` — new
- `the_one/interfaces/web/static/css/fonts.css` — new (~50 lines)
- `the_one/interfaces/web/static/index.html` — 1 line added (`<link>` for fonts.css)
- `the_one/interfaces/web/static/css/base.css` — `body` font-family changed
- `the_one/interfaces/web/static/css/chat.css` — Geist Mono on data contexts; font-size token replacements
- `the_one/interfaces/web/static/css/studio.css` — Geist Mono on section titles + data; font-size token replacements
- `the_one/interfaces/web/static/css/admin.css` — Geist Mono on section titles, badges, model rows, env-var hints; font-size token replacements
- `the_one/interfaces/web/static/css/components.css` — minor (`.app-flash` font-weight token replacement if applicable)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350/16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Hex/rgba grep returns zero matches (excluding tokens.css, fonts.css, SVG data URLs)
- [ ] Font assets present in `static/fonts/` with LICENSE.txt
- [ ] Manual visual check: Geist Sans renders in body text; Geist Mono renders in data contexts; no FOUC on slow-3G reload
- [ ] Update flight-log.md with leg progress entry (status, what was done, font filenames used, anomalies)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (happens at flight-level commit time)
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
