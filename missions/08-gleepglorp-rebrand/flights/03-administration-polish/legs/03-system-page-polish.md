# Leg: 03-system-page-polish

**Status**: completed
**Flight**: [Administration Polish](../flight.md)

## Objective

Polish the System page to the Flight 2 design language vocabulary. **Operator-surfaced scope expansion during HAT**: 8 polish items spanning System + cross-page primitive extraction + bug fixes. Two new shared primitives extracted into `components.css` (`.banner`, `.code-block`) so adjacent pages (Tools editor, Providers editor delete-blocked, Design Language gallery) inherit the same vocabulary.

## Context

- **Leg originally scoped as System-only**, but operator listed 8 items at HAT kickoff spanning System (theme toggle, encryption warning, base prompt, section ordering), Providers (test-result redundant glyph), Tools (prompt header eyebrow, chip-list-editor formatting), and Design Language (nested scrollbar, dead topbar miniature). Adopted as scope expansion per the Flight 1 + 2 debrief pattern of "opportunistic adjacent fixes at HAT-caught moments." Mirrors the Flight 2 Leg 05 precedent (operator-surfaced interactive primitives pass).
- **Two new shared primitives** emerged: `.banner` (3 variants — error / warning / info) and `.code-block` (chat-style terminal aesthetic). Both extracted into `components.css` so future polish flights can compose rather than re-derive.
- **Body-level scrollbar bug** (item 8) was a classic flex layout pathology: `body { height: 100vh }` with `display: flex; flex-direction: column` children defaulting to `min-height: auto` (content-sized) pushed body content past 100vh, surfacing a document-level scrollbar that ran the full viewport height. Fix needed `body { overflow: hidden }` + `min-height: 0` on the entire flex-column chain (`#main-content`, `.content-panel`, `.admin-content`).

## Inputs (pre-leg state)

- `static/js/areas/admin/system-page.js` — 3 sections in order Appearance → Encryption → Base Prompt; theme toggle delegated to `App.theme.renderToggle`; encryption warning used bespoke `.admin-system-warning` class; base prompt used bespoke `.admin-base-prompt` styling (surface bg + 1px border).
- `static/js/areas/admin/provider-editor.js:339, :351, :360, :367` — test result `span.textContent` carried glyph prefixes (`'✓ '`, `'⚠ '`, `'✗ '`) — redundant with the `.test-result-*::before` LED retrofit landed in Flight 2 Leg 05.
- `static/js/areas/admin/tools-editor.js:118-121` — prompt block rendered as `<span class="editor-prompt-label">// prompt</span>` (lowercase mono eyebrow, ad-hoc) + `<p class="editor-prompt-text">` body.
- `static/css/admin.css:288-307` — bespoke `.editor-prompt-block` + `.editor-prompt-label` + `.editor-prompt-text` styles.
- `static/css/admin.css:340-352` — `.chip-list-editor` used `--border-strong` + hardcoded 4px radius + flat `--surface` (no bezel-inset, no glass-border) — diverged from `.field-input` family.
- `static/css/components.css:932-942` — `.action-blocked-message` bespoke styled (destructive left-border + soft bg).
- `static/css/admin.css` — `.admin-system-warning` bespoke styled with bg + full border + 16px margin-bottom.
- `static/css/base.css:4` — `body { height: 100vh; display: flex; flex-direction: column }` (NO `overflow: hidden`).
- `static/css/base.css:41-43` — `#main-content`, `.content-panel`, `.area-admin .admin-content` flex chain — none had `min-height: 0`.
- `static/js/areas/admin/design-language/surfaces-section.js:67-77` — `.app-topbar-title` miniature sample (now dead since Leg 02 swapped wordmark for banner image).
- `static/js/areas/admin/design-language/status-section.js:65-69` — `.action-blocked-message` gallery sample (bespoke).

## Outputs (post-leg state)

**New shared primitives** (canonical, in `components.css`):
- **`.banner`** with `.banner-error` / `.banner-warning` / `.banner-info` variants. Lifted shape from prior `.action-blocked-message`: 3px solid variant-color left border + variant-tinted `linear-gradient(to right, …bg-soft, transparent)` + asymmetric corner-radius (sharp left, `--panel-radius-sm` right). Supports `[hidden]`. Replaces bespoke `.action-blocked-message` styling + `.admin-system-warning` styling.
- **`.code-block`** chat-style terminal aesthetic: `background: #000` + `color: var(--status-warning)` + `--panel-radius-sm` + mono. Consumers: System page base prompt, Tools editor prompt body.

**System page** (`system-page.js`):
- Section order: Appearance → Base Prompt → Encryption (encryption moved to bottom).
- Encryption warning now `<div class="banner banner-warning">` (canonical primitive).
- Base prompt now `<pre class="admin-base-prompt code-block">` (composes the code-block primitive; admin-side adds max-height: 24rem + overflow-y: auto).
- Theme toggle (`admin.css`): container carries bezel-mini + glass-border + V3b gradient. Active option keeps the **solid filled** look (`var(--accent)` background + V3b gradient + `--fg-on-accent` text), matching `.btn-filled-primary` family. Inactive options accent-translucent on hover. Removed the prior outer-glow remnant.

**Providers editor** (`provider-editor.js`):
- Test result `span.textContent` no longer carries `'✓ '` / `'⚠ '` / `'✗ '` prefixes — the `.test-result-*::before` LED retrofit (from Flight 2 Leg 05) already conveys status visually.
- Delete-blocked message markup migrated to `class="action-blocked-message banner banner-error"` — keeps the JS-query handle (`provider-editor.js:379`) while adopting the new primitive's styling.

**Tools editor** (`tools-editor.js`):
- Prompt block: `<span class="editor-prompt-label">// prompt</span>` + `<p class="editor-prompt-text">` → `<div class="section-title">Prompt</div>` + `<pre class="editor-prompt-text code-block">`. Uses the canonical `.section-title` primitive (renders as `// PROMPT` via the existing `::before` rule) + composes the code-block primitive for the body.
- Chip-list editor (`admin.css`) — `.chip-list-editor` now composes `.field-input` design language: `--bezel-shadow-inset` + `--glass-border` + `--panel-radius-sm`. Adds `:focus-within` ring. Chips inside use accent-translucent (canonical `.chip` shape). Affects all array-typed tool config fields (e.g., `host_allowlist` on `http_request` / `fetch_url` / `download_file`).

**Design Language gallery**:
- `surfaces-section.js`: removed the `app-topbar-title (miniature)` row entirely. The pattern is dead since Leg 02's banner-image swap retired the wordmark.
- `status-section.js`: replaced the single `.action-blocked-message` sample with a 3-variant banner showcase (error / warning / info).

**Layout fix** (body-level scrollbar):
- `base.css`: `body { overflow: hidden }` added. body is the SPA shell — never scrolls itself; inner area scroll containers handle page-level scrolling.
- `base.css`: `min-height: 0` added to `#main-content` + `.content-panel`. Allows flex-column children to shrink below their content's intrinsic min-content size (mandatory for `.admin-content`'s `overflow-y: auto` to actually clip rather than propagate up the flex chain to body).
- `admin.css`: `min-height: 0` added to `.area-admin .admin-content`.
- `admin.css`: `.admin-form` lost its redundant `overflow-y: auto` — `.admin-content` is now the sole scroll container per Admin page.

**Retired CSS** (no longer needed):
- `.action-blocked-message` bespoke styling rule (banner-error owns the look now; class kept as a JS-query handle).
- `.admin-system-warning` rule (banner-warning owns the look now; class removed from markup).
- `.editor-prompt-label` rule (canonical `.section-title` owns the eyebrow now).
- `.editor-prompt-text` original ad-hoc styling (code-block + max-height bound).

## Acceptance Criteria

- [x] **Theme toggle** — solid-filled active option (V3b gradient + accent fill + `--fg-on-accent` text); container bezel-mini; no double-glow remnant; operator confirmed
- [x] **System section order** — Appearance → Base Prompt → Encryption
- [x] **Encryption warning** — composes `.banner.banner-warning`; reads on-brand with left-border + gradient bg
- [x] **Base prompt** — composes `.code-block`; black bg + warning text + mono + panel-radius-sm
- [x] **Providers test result** — no glyph prefix; LED dot retrofit-only conveys status
- [x] **Tools editor prompt heading** — canonical `// PROMPT` section-title eyebrow
- [x] **Tools editor prompt body** — composes `.code-block` (terminal aesthetic)
- [x] **Tools chip-list-editor** — design-language treatment (bezel-inset + glass-border + accent-translucent chips)
- [x] **Design Language gallery** — topbar-title miniature removed; action-blocked sample replaced with 3-variant banner showcase
- [x] **Body-level scrollbar** — gone; single scrollbar on `.admin-content` only
- [x] **WCAG audit** green: 45/45 (no contrast pair changes — banner uses already-audited soft-bg + status-color pairs)
- [x] **Narrow gate** green: 56/56 (no behavioral regressions)
- [x] Operator visual verification confirmed ("looks good")

## Files Modified

- `the_one/interfaces/web/static/css/components.css` — new `.banner` primitive (3 variants) + new `.code-block` primitive + retired `.action-blocked-message` standalone rule
- `the_one/interfaces/web/static/css/base.css` — `body { overflow: hidden }` + `min-height: 0` on `#main-content` and `.content-panel`
- `the_one/interfaces/web/static/css/admin.css` — theme toggle V3b + solid-filled active; `.chip-list-editor` design-language treatment; `.editor-prompt-block` simplified for section-title + code-block consumers; `.admin-base-prompt` simplified for code-block consumer; `.admin-form` lost redundant overflow-y; `.admin-content` gained min-height: 0; `.admin-system-warning` retired
- `the_one/interfaces/web/static/js/areas/admin/system-page.js` — section reorder + banner-warning markup + code-block consumer
- `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` — glyph prefixes removed from test result + delete-blocked markup composes banner-error
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js` — prompt block uses section-title + code-block composers
- `the_one/interfaces/web/static/js/areas/admin/design-language/surfaces-section.js` — topbar-title miniature removed
- `the_one/interfaces/web/static/js/areas/admin/design-language/status-section.js` — action-blocked sample → 3-variant banner showcase

## Iteration Trail (operator-driven HAT)

1. **v1**: System page polish per original spec (theme toggle bezel-mini + accent-translucent active, encryption bezel-inset, base prompt bezel-inset). Operator surfaced 8 issues at HAT kickoff:
   1. Theme picker not styled like the rest of the app
   2. Move encryption section to bottom
   3. Encryption warning callout doesn't match design language
   4. Provider test result has redundant green check
   5. Tools fields not properly formatted (host_allowlist etc.)
   6. Tools `// prompt` not a proper header + body should be chat-style code block
   7. Base prompt should be chat-style code block
   8. Design language page still has 2 nested scrollbars
2. **v2**: Knocked through all 8 in a single batch. Operator returned with 3 corrections:
   1. Theme toggle active should be SOLID button (not accent-translucent)
   2. Tools prompt should be canonical `// PROMPT` section-title eyebrow (not `<h3>`)
   3. Scrollbar still present — full-height document scrollbar visible behind topbar
3. **v3**: Solid-filled active + canonical section-title + body-level overflow fix.
4. **v4** (operator follow-up): Remove dead topbar-title miniature + extract banner primitive (error/warning/info) + apply to encryption warning. Operator initially rejected v4 banner styling (full border + bezel-inset) — wanted "previous version with solid left border and gradient." Reapplied with 3px left-border + linear-gradient-to-transparent + asymmetric corner-radius.

**Key methodology lesson**: When the operator surfaces cross-page polish items mid-HAT, absorbing them into the active leg with a scope-expansion note in the artifact is cheaper than deferring to their planned legs — provided the items cluster around shared primitives (here, banner + code-block).

## Citation Audit

12 citations verified against current code at leg close:
- `system-page.js:11-50` body — verified section reorder + banner-warning markup + code-block class.
- `provider-editor.js:96` — verified `.action-blocked-message banner banner-error` composition.
- `provider-editor.js:336-369` — verified glyph prefixes removed from `span.textContent`.
- `tools-editor.js:118-121` — verified `<div class="section-title">Prompt</div>` + `<pre class="editor-prompt-text code-block">`.
- `surfaces-section.js` — verified `.app-topbar-title` miniature block removed.
- `status-section.js` — verified 3-variant banner showcase replaces single `.action-blocked-message` sample.
- `admin.css :11` — verified `.admin-form` no overflow-y.
- `admin.css :30-67` — verified theme-toggle V3b family + solid-filled active.
- `admin.css :340-355` — verified chip-list-editor design-language treatment.
- `base.css :4` — verified `body { overflow: hidden }`.
- `base.css :41-44` — verified `min-height: 0` on `#main-content` + `.content-panel`.
- `components.css .banner` + `.code-block` — verified new primitives present with declared variants.

All citations clean. No new mirror updates needed (`tests/browser/design_tokens.py` doesn't track banner/code-block tokens).
