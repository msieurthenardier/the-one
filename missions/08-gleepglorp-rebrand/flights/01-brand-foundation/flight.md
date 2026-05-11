# Flight: Brand Foundation

**Status**: in-flight
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] The product's user-facing identity reads as "GleepGlorp AI" consistently across every screen, browser-level surface (tab title, favicon), and server-rendered metadata *(this flight covers the core brand-text surfaces; per-area polish flights catch any incidental references that surface during polish)*
- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas, in both light and dark themes *(palette and assets land here mission-wide; per-area flights are responsible for compositional polish)*
- [ ] Color contrast meets WCAG AA across the rebranded palette for text, interactive elements, and focus indicators
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes

---

## Pre-Flight

### Objective

Replace the existing cyan-accented "the-one" visual identity with the new GleepGlorp AI purple-led identity. Land the brand foundation that every subsequent polish flight builds on: rebranded product strings, mascot-derived favicon and topbar icon assets, a purple `--accent` palette in both themes verified to WCAG AA, and a one-shot mechanical rename of the misnamed `btn-filled-cyan` / `btn-outlined-cyan` CSS class names to semantic equivalents so future flights aren't typing "cyan" in HTML strings that render purple. Closes with a regenerated local visual-snapshot baseline and an alignment HAT.

### Open Questions

- [x] **Token-value change vs token rename** → Change the *value* of `--accent` (and related accent-* tokens); keep token names. Touching token names would cascade across 164 CSS references and the `agents.md` design-system docs without semantic gain. Recorded in Design Decisions.
- [x] **CSS class-rename target** → `.btn-filled-primary` / `.btn-outlined-primary`. Semantic, color-agnostic, future-proof. Recorded in Design Decisions.
- [x] **Class-rename strategy: aliases vs hard cutover** → Hard cutover (no temporary `btn-filled-cyan` alias). Internal codebase, all consumers are in-repo, no external CSS depending on these names. Recorded in Design Decisions.
- [x] **MCP `clientInfo.name` rebrand** → Keep `"the-one"`. Protocol-level identifier sent to MCP servers during initialization; not user-visible, churning it adds operational confusion without value. Recorded in Design Decisions.
- [x] **SVG vector trace of mascot** → Out of scope. AI-generated PNG has complex glow / circuit detail that doesn't vector-trace cleanly. PNG-resized variants ship in this flight; SVG trace is a future enhancement if it's ever needed.
- [x] **Anthropic purple-badge clash with new purple accent** → Accept the visual proximity; flag for HAT review. Provider badges are small chip elements (~16-20px tall); the app accent dominates buttons, borders, focus rings. If alignment leg surfaces a real readability problem, tune the badge color as a follow-up (badge colors are theme-stable per the existing tokens.css comment).
- [x] **`/docs` Swagger UI reachability** → Confirmed reachable by default (no `docs_url` override on `FastAPI()` at `app.py:123`). Rebranding the FastAPI title surfaces to the auto-generated `/docs` page; user-visible — keep in the brand-text sweep.
- [x] **Snapshot tests during legs 1-4** → Confirmed `pyproject.toml` `addopts` includes `-m "not ... and not pixel ..."` (line ~60); `@pytest.mark.pixel` tests are excluded from the default `docker exec the-one pytest tests/` run. Legs 1-4 will not see stale-baseline failures; baselines are only exercised when leg 5 explicitly invokes them.
- [ ] **Specific purple/violet hex values for `--accent`** in dark and light themes → Resolved in Leg 02 with WCAG AA verification. Working candidates: dark = violet-400 `#a78bfa` or fuchsia-400 `#e879f9`; light = violet-600 `#7c3aed` or violet-700 `#6d28d9`. Final values picked once the existing `tests/test_design_tokens_a11y.py` audit passes against both `--bg` and `--surface` for all body / large / UI thresholds.
- [ ] **Topbar wordmark composition** → Decided in Leg 01. Working assumption: small emblem icon (~24px round mascot crop, explicit `width="24" height="24"` attributes plus scoped CSS `.app-topbar-title img { width: 24px; height: 24px; vertical-align: middle; }` to prevent layout shift on load) to the left of HTML-rendered "GleepGlorp AI" wordmark text in Geist Sans. Final visual settled in the alignment leg.
- [ ] **`--accent-api` token retune** → Decided in Leg 02. The token is currently `#7c4dff` (dark) / `#6d28d9` (light) — already a purple/violet used as the background for API-provider chat messages at `chat.css:94` (`.area-chat .msg.user.api`). When `--accent` becomes purple, `--accent-api` loses its differentiation role and reads as a near-duplicate. Working assumption: shift `--accent-api` to a complementary hue (e.g., teal `#0d9488` / cyan-700 — the retired-cyan recycled into a secondary slot) so user-vs-API message distinction survives. Final values picked alongside the primary accent retune.
- [ ] **OAuth callback page HAT trigger in Leg 5** → Direct-render preview by visiting the rebranded callback URL with seeded query params; full end-to-end OAuth flow HAT defers to Flight 3 (Studio Polish) where an MCP source is set up. Confirmed in Leg 5 design.

### Design Decisions

**Palette transition strategy**: Retune `--accent` token values; preserve token names. The CSS layer already routes all primary-color expression through `var(--accent)` (164 references); changing the value at the token level is the minimal-blast-radius approach. Updating `tests/browser/design_tokens.py` Python mirror in the same leg keeps the WCAG audit in sync.
- Rationale: Token names like `--accent` are color-agnostic; renaming them to `--primary` adds zero semantic value while exploding the diff and increasing the risk of breakage.
- Trade-off: Future readers will see "accent" in CSS and "GleepGlorp purple" in the rendered UI — the mental model "accent means primary brand color" carries.

**CSS class-name target**: `.btn-filled-cyan` → `.btn-filled-primary`, `.btn-outlined-cyan` → `.btn-outlined-primary`. Semantic naming decoupled from any specific color.
- Rationale: Mission constraint explicitly calls for this rename so subsequent polish flights don't re-litigate color in code. Semantic "primary" maps to the role (the dominant interactive affordance) rather than the hue, which makes future palette changes a token-only edit.
- Trade-off: Brief churn across 10 JS files + components.css + admin.css comments + agents.md design-system docs. Worth it once.

**Hard cutover for class rename**: No temporary `.btn-filled-cyan` CSS alias retained during the transition. The replace is mechanical and atomic — one PR-equivalent diff updates every call site and the rule definitions in the same flight.
- Rationale: All consumers are in-repo (no external stylesheets, no published design-system package). Aliases would create a long tail where future devs grep "btn-filled-cyan" and find half the codebase using it.
- Trade-off: If a single grep miss makes it through review, the affected button renders unstyled until the miss is patched. Mitigation: post-rename grep verification leg requires zero hits for the old names.

**MCP `clientInfo.name` stays `"the-one"`**: The string is sent to MCP servers during the `initialize` handshake at `the_one/interfaces/web/api.py:1436` and `:1821`. It is not user-visible; it's how MCP servers identify the client in their own logs.
- Rationale: Churning a protocol identifier creates operational confusion (server logs split across two client names) for zero user-facing value.
- Trade-off: The MCP-server side will continue showing "the-one" in audit trails. Acceptable — the repo and CLI binary still carry that name too; consistency with the internal identifiers.

**Brand-text per-surface decisions**:

| Surface | Today | Rebrand to | Rationale |
|---|---|---|---|
| `static/index.html:6` `<title>` | `the-one` | `GleepGlorp AI` | Browser tab — user-visible |
| `static/js/app.js:17` topbar `<h1>` | `the-one` | `GleepGlorp AI` | Primary product header — user-visible |
| `the_one/interfaces/web/app.py:123` `FastAPI(title=...)` | `the-one` | `GleepGlorp AI` | Surfaces in auto-generated `/docs` page — user-visible if exposed |
| `the_one/interfaces/cli.py:30,32` Rich welcome panel | `the-one` | `GleepGlorp AI` | CLI splash — user-visible |
| `the_one/main.py:25` `the-one v{__version__}` | `the-one` | `GleepGlorp AI` | `the-one --version` output — user-visible (binary name stays `the-one`) |
| `the_one/main.py:27` `Usage: the-one [...]` | `the-one` | `the-one` (unchanged) | Refers to the actual CLI binary name; do not change |
| `the_one/__init__.py:1` package docstring | `the-one: A personal agentic system.` | `GleepGlorp AI: A personal agentic system. (Python package: the_one)` | Exported via help() and API consumers |
| `the_one/interfaces/web/api.py:1579` OAuth callback eyebrow | `the-one // oauth` | `gleepglorp ai // oauth` | User-visible OAuth completion page |
| `the_one/interfaces/web/api.py:1436,1821` MCP `clientInfo.name` | `the-one` | `the-one` (unchanged) | Protocol-level identifier; not user-visible |
| Python package name `the_one` | (no change) | (no change) | Repo + Python module names explicitly out of scope per mission |
| CLI binary name `the-one` | (no change) | (no change) | Binary name preserved per mission constraint |

**Snapshot regeneration cadence**: All baselines regenerate at end of Leg 5, not per-leg. Legs 1-4 will each diff against stale baselines; that is expected and not a failure. Leg 5 runs `UPDATE_SNAPSHOTS=1 pytest -m pixel` once over the rebranded final state.

### Prerequisites

- [x] Mascot PNGs present at `the_one/interfaces/web/static/brand/gleepglorp_med.png` and `gleepglorp_small.png`
- [x] Mission 08 active; no prior flights in this mission
- [x] M07 (MCP Integration) landed; chat OAuth surfaces stable
- [x] M04 design-system substrate (tokens.css, components.css, WCAG audit, Python mirror, visual-snapshot harness) intact and tests green on `main`
- [x] Pillow (PIL) available in dev environment — already used by visual snapshot tests via `importorskip`

### Pre-Flight Checklist

- [ ] All open questions resolved (one still pending palette hex values — resolved in Leg 02)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

The flight is a sequence of small, mostly-mechanical changes culminating in a baseline regeneration and a human alignment pass. The order matters in one place only: brand-text and class-rename legs commit before snapshot regeneration so the regenerated baselines capture the final state. Otherwise legs are independent.

**Asset processing (Leg 01)**: Use Pillow to derive resized variants from `gleepglorp_med.png` (or `_small.png` — pick at leg time): 16x16, 32x32, 48x48 PNGs for browser favicon; 180x180 apple-touch-icon; 192x192 and 512x512 for PWA manifest readiness (though no manifest in this flight). All variants go to `static/brand/`. The derivation runs from a Makefile target (`make brand-assets`) — single command, future logo refreshes regenerate cleanly, derived PNGs commit to the repo so the running container serves them without a build-time step. Pillow is already declared in `pyproject.toml` `dev` extras (line ~36) so it's available in the dev container. Wire the favicon set into `static/index.html` via `<link rel="icon">` tags. The topbar gets a separate small mascot crop (~24px round) embedded as `<img>` next to the wordmark in `app.js:17`; the `<img>` MUST carry explicit `width="24" height="24"` attributes AND a scoped CSS rule (e.g., `.app-topbar-title img { width: 24px; height: 24px; vertical-align: middle; margin-right: 8px; }`) to prevent the wordmark from reflowing during image decode.

**Palette retune (Leg 02)**: Update `[data-theme="dark"]` and `[data-theme="light"]` `--accent` and related accent-* values (`--accent-glow`, `--accent-glow-strong`, `--accent-translucent`, `--accent-translucent-hover`, `--accent-api`, and the dependent `--panel-shadow-glow` cyan-tint composition) in `static/css/tokens.css`. Mirror the relevant values into `tests/browser/design_tokens.py`; extend the mirror to cover `--accent-api` (currently absent from the Python mirror, despite being used as a chat-message background at `chat.css:94` `.area-chat .msg.user.api`) and add a parametrized contrast pair for `accent_api` vs `fg_on_accent` in both themes — `--accent-api` is a load-bearing text-on-color slot today and the audit has been silent on it. Run the existing WCAG audit (`docker exec the-one pytest tests/test_design_tokens_a11y.py -v`); iterate palette until all parametrizations pass. Document final hex values in the leg artifact.

**CSS class rename + design-system documentation sweep (Leg 03)**: Mechanical sweep replacing `btn-filled-cyan` → `btn-filled-primary` and `btn-outlined-cyan` → `btn-outlined-primary` across:
- `static/css/components.css` — rule definitions and intra-file comments
- `static/css/admin.css` — comment references
- `static/css/studio.css` — `.area-studio .tool-actions .btn-outlined-cyan` size override
- All JS files in `static/js/` carrying the class strings (re-grep at leg start; do not rely on a pre-baked count)
- `the_one/agents.md` design-system section — class names AND the affordance-pattern descriptors that currently say "Outlined-cyan" / "Filled-cyan CTA"; rename to "Outlined primary" / "Filled primary CTA" so the design-language vocabulary stays color-agnostic alongside the class names
- `the_one/interfaces/web/static/css/tokens.css` historical comments at lines ~3, 115, 138-141 currently referencing "NEXUS-style cyan" / "cool-tinted off-white, coordinates with cyan accent" / "cyan-700" — update or annotate as historical so future readers aren't confused

Verification: `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/` returns zero hits, AND `grep -rn -i "cyan\|nexus" the_one/interfaces/web/static/css/ the_one/agents.md` returns only deliberate historical-context comments.

**Brand-text sweep (Leg 04)**: Update each surface per the per-surface decision table above. Also update the stale internal comment at `the_one/interfaces/web/api.py:1478` ("perceives continuity with the rest of the-one — dark-mode cyan-accent palette") which post-Leg-02 will be factually wrong about both the brand name and the palette. Verification: targeted greps confirm each user-visible surface contains `GleepGlorp AI` and the protocol-level / binary-name surfaces remain `the-one`.

**Baseline regeneration + alignment (Leg 05)**: Run `make rebuild` to bake the updated assets and CSS into the container; regenerate all 12 visual-snapshot baselines with `UPDATE_SNAPSHOTS=1 pytest -m pixel tests/browser/test_visual_snapshots.py`. Walk the operator through a HAT covering the three areas in both themes; capture any visual issues that emerge as in-flight notes; fix immediately if tactical, or log as Known Issues for downstream flights if structural.

### Checkpoints

- [x] Leg 1 done: favicon set generated, wired into `index.html`, topbar icon rendering next to wordmark
- [x] Leg 2 done: palette retuned, WCAG audit green, Python mirror in sync
- [x] Leg 3 done: zero hits for `btn-filled-cyan` / `btn-outlined-cyan` across the repo; all buttons still render correctly
- [x] Leg 4 done: all user-visible brand-text surfaces read "GleepGlorp AI"; protocol identifiers preserved
- [ ] Leg 5 done: 12 snapshot baselines regenerated; HAT walkthrough complete; alignment notes captured

### Adaptation Criteria

**Divert if**:
- WCAG audit cannot be passed with a recognizably-purple palette after two iterations (purple at the contrast levels needed may end up too dark/muted to read as "purple"). If this happens, escalate to user for a paler-purple-with-cyan-accents-as-secondary alternative.
- The PNG-to-favicon Pillow pipeline produces visibly degraded 16x16/32x32 (mascot detail unreadable at small sizes). Switch the favicon to a simplified icon-only crop or fall back to a wordmark-initial favicon.
- Hard cutover surfaces external consumers of the old class names (any test asserting on `btn-filled-cyan`). Update those consumers in the same leg.

**Acceptable variations**:
- Per-leg ordering of palette vs class-rename — both are independent.
- Choice of small vs medium source PNG for the favicon pipeline (lower-res may downsample cleaner for tiny sizes).
- Final palette gradient direction (lighter-purple-in-dark-theme vs deeper-purple-in-dark-theme) — picked in Leg 02.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses.

- [x] `01-brand-assets` — Pillow-derive favicon set + topbar icon from the source PNG; wire favicon `<link>` tags into index.html; embed topbar icon next to wordmark in app.js
- [x] `02-palette-tokens` — Retune `--accent` and related accent-* values in tokens.css for both themes; mirror into tests/browser/design_tokens.py; iterate until WCAG audit is green
- [x] `03-cyan-class-rename` — Mechanical rename `btn-filled-cyan` / `btn-outlined-cyan` → `*-primary` across components.css, admin.css comments, 10 JS files, and agents.md design-system docs; verify zero hits remain
- [x] `04-brand-text-sweep` — Apply per-surface brand-text decisions across index.html, app.js topbar, FastAPI title, CLI Rich panel, main.py version print, package docstring, and OAuth callback eyebrow; preserve internal identifiers
- [ ] `05-snapshot-rebaseline-and-alignment` — `make rebuild`; regenerate 12 visual-snapshot baselines with `UPDATE_SNAPSHOTS=1`; HAT walkthrough across Chat / Studio / Admin in both themes; capture alignment notes and tactical fixes

---

## Post-Flight

### Completion Checklist

- [ ] All 5 legs completed
- [ ] Test suite green: `docker exec the-one pytest tests/` passes; WCAG audit green; browser flows green
- [ ] Visual snapshot baselines regenerated locally and visible-snapshot tests green when re-run
- [ ] `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/` returns zero hits in the repo
- [ ] `grep -rIn "the-one"` returns no user-visible hits in static/, index.html title, app.js topbar, cli.py panel, main.py version print, OAuth callback page, or FastAPI title; remaining hits are only in: Python imports/code (`from the_one...`), CLI binary name in usage strings (`Usage: the-one`), MCP `clientInfo.name` (protocol identifier), internal code comments referencing file paths, and test-internal fixture identifiers (`tmp_path / "the-one-data"` in `tests/browser/conftest.py` and a handful of test-internal references — these are not user-visible)
- [ ] HAT alignment complete; any structural issues surfaced are logged as Known Issues or in-flight notes for downstream flights
- [ ] Flight log records the final palette hex values, the favicon variant sizes shipped, and any HAT-surfaced follow-ups
- [ ] Code merged; flight status updated to `landed`

### Verification

- **Visual identity check**: Load the app in both themes; the topbar reads "GleepGlorp AI" with the mascot icon, the browser tab favicon is the mascot, every primary button is purple-accented, every form focus ring is purple.
- **Functional regression check**: Run the full browser flow suite (`docker exec the-one pytest -m browser tests/browser/`); all tests pass.
- **WCAG audit check**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — all parametrizations pass.
- **Snapshot stability check**: After regeneration in Leg 5, re-run `pytest -m pixel tests/browser/test_visual_snapshots.py` without `UPDATE_SNAPSHOTS=1`; should pass cleanly.
- **Brand-text completeness check**: The grep verifications in the Completion Checklist confirm complete coverage.
