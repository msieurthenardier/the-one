# Flight: Design Language — Glass + Control Panel

**Status**: landed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [ ] The visual identity has a deliberate aesthetic direction (robot / control-panel) documented in a live design-language gallery page that's reachable in dev mode and shows tokens, typography, every component variant, controls, indicators, and motion samples in concentrated form
- [ ] A coherent visual identity anchored to the new logo and a purple-led palette is present and consistent across all three areas, in both light and dark themes *(the aesthetic seam lands here mission-wide; per-area polish flights apply it page-by-page)*
- [ ] Color contrast meets WCAG AA across the rebranded palette for text, interactive elements, and focus indicators *(re-verified after aesthetic-context retune of `--accent-api` and any glass tints that touch text-on-color slots)*
- [ ] All existing functionality (M01–M07 capabilities) continues working after the rebrand and polish passes *(no functional change in this flight; aesthetic + scaffolding only)*

---

## Pre-Flight

### Objective

Establish the deliberate aesthetic direction for GleepGlorp AI — **reflective glass within a light-hearted control-panel view, futuristic-cartoon but crisp** — and apply it through canonical components so it surfaces everywhere downstream area-polish flights will work. Land a dev-mode-only design-language gallery page under Admin that consolidates the entire design vocabulary (tokens, typography ladder, every primitive variant, status indicators, motion samples) onto a single canvas; use that canvas as the vibe-coding workspace for the aesthetic itself. Iterate the aesthetic across three axes — glass surface treatment, control-panel chrome / bezels, indicators + motion — applying changes back into `tokens.css` + `components.css` so the gallery and every existing area surface evolve together. Retune `--accent-api` in aesthetic context (closes Flight 1 debrief action item). Extract `.checkbox-primary` primitive in the same pass (closes Flight 1 debrief action item, debt before Flight 3/4). Close with a regenerated visual-snapshot baseline and an alignment HAT.

### Open Questions

- [x] **Dev-mode gate mechanism** → New `GET /api/config` endpoint returning `{dev_mode: bool, version: str}`. Client **boot-blocks** on the fetch before invoking the first `switchTo(...)` so areas have `App.config` available at `init()` time. Becomes the canonical channel for any future "configuration the client needs to know" data. Recorded in Design Decisions.
- [x] **Light-theme glass treatment** → "Frosted-white glass" — low-alpha white surface + visible top-edge highlight + backdrop-saturate (not just blur). Same token names as dark theme, theme-tuned values. Recorded in Design Decisions.
- [x] **Aesthetic surface scope** → Chrome (topbar, app-picker popover, modal overlay, sidebar/section-nav, entity tiles, editor-header, page-header) + interactive primitives (buttons, fields, selects, checkboxes). Drops `.checkbox-primary` extraction into scope alongside. Recorded in Design Decisions.
- [x] **Visual-snapshot regeneration cadence** → Once at flight close (mirrors Flight 1). Vibe legs run against stale baselines; final regen happens in the alignment leg. Recorded in Design Decisions.
- [x] **Vibe-leg sequencing** → Three vibe legs in dependency order: (3) Glass, (4) Chrome / bezels, (5) Indicators + motion. Earlier work informs later. Recorded in Design Decisions.
- [x] **`.checkbox-primary` extraction** → Piggyback on this flight rather than defer to Flight 3/4. Closes Flight 1 debrief Action Item #1 before the gallery samples a checkbox. Recorded in Design Decisions.
- [ ] **Concrete glass token values** (`--glass-bg`, `--glass-blur`, `--glass-border`, `--glass-highlight`, `--glass-saturate`) for both themes → Resolved interactively in Leg 03; final values committed to `tokens.css` and mirrored into `tests/browser/design_tokens.py` if any of them participate in contrast pairs.
- [ ] **Bezel / chrome treatment specifics** — directional light convention (top-left vs ambient), corner machining (rounded vs subtly chamfered), raised-edge stroke width and tint → Resolved interactively in Leg 04.
- [ ] **`--accent-api` aesthetic retune** — current value is recycled cyan (`#22d3ee` dark / `#0e7490` light), placed as a complementary "secondary" hue. Open: do we keep the teal as the deliberate "data-channel" indicator color (a stable convention) or shift it to a tertiary aesthetic-driven hue? → Resolved interactively in Leg 06 once the dominant aesthetic has settled (decision is design-language-dependent, not value-dependent).
- [ ] **Motion primitives** — easing curves (`--ease-tactile`, `--ease-overshoot`?), durations (`--motion-fast`, `--motion-base`, `--motion-slow`?), `prefers-reduced-motion` posture → Resolved interactively in Leg 05.
- [ ] **Indicator / telemetry primitives** — LED dot (with glow), telemetry strip eyebrow, status pill, dial/meter analogues if any → Resolved interactively in Leg 05. Net-new primitives only land if a downstream polish flight is the natural consumer; speculative additions stay in the gallery as samples without graduating to `components.css`.
- [x] **`// section-title` eyebrow vs `.telemetry-strip` relationship** → Resolved in Leg 02 design: Leg 02 uses existing `.section-title` for the gallery's section eyebrows (`// TOKENS`, `// TYPOGRAPHY`, …). Leg 05 introduces `.telemetry-strip` as a **sibling primitive** with its own gallery sample — different semantic role (status readout vs. section header). The two coexist.
- [ ] **Performance posture on `backdrop-filter`** — Modern Chromium/Firefox/Safari handle it well; Linux/Wayland with software compositing can struggle. Working assumption: ship `backdrop-filter` as the canonical glass treatment with a `prefers-reduced-transparency` (or a feature-detect fallback) downgrade path to solid-tinted surface. Resolved interactively in Leg 03.

### Design Decisions

**`GET /api/config` endpoint for client-visible configuration, with boot-blocking client fetch**: Add a small read-only endpoint returning `{dev_mode: bool, version: str}` that the JS client fetches BEFORE its first `switchTo(...)` invocation. The current `app.js:225-230` `DOMContentLoaded` handler synchronously calls `switchTo(area, parsed.sub)`, which calls `areas[areaId].init(...)` on first activation (`app.js:158-168`) — `admin.init()` builds the hardcoded `categories` list and `validIds` array (`admin.js:108-117, :88`) inside its closure at that moment. So `App.config.dev_mode` MUST be available before `switchTo` runs.
- Implementation: `DOMContentLoaded` handler becomes `fetch('/api/config').then(r => r.json()).then(config => { window.App.config = config; switchTo(area, parsed.sub); }).catch(() => { window.App.config = {dev_mode: false, version: 'unknown'}; switchTo(area, parsed.sub); })`. The catch path defaults to safe values (no gallery) so a failed config fetch never breaks boot.
- Server reads `the_one.__version__` via `from the_one import __version__` (no hardcoded version string), matching the Flight 1 dynamic-version convention.
- Rationale: Centralizes "configuration the client needs to know" through a single channel. Boot-blocking keeps the init contract synchronous (no init-order race). Cold-load adds <100ms blank-screen window; warm cache eliminates it.
- Trade-off: One new GET route + slight cold-load delay. Negligible cost; opens the door for future config keys to land here without re-litigating the channel or re-engineering init order.
- Alternatives rejected: (a) Render-time gate (re-render sidebar when config resolves) — works but pushes complexity into `admin.js` for a server-side near-static flag; (b) Server-render config into `index.html` via template substitution — cleaner but requires Jinja or similar wiring not currently used for the static SPA shell.

**Frosted-white glass for light theme**: Light-theme glass uses low-alpha white surface (e.g., `rgba(255,255,255,0.55)`) + backdrop-blur + backdrop-saturate, with a visible top-edge highlight as a 1px linear-gradient overlay or `box-shadow inset 0 1px 0 rgba(255,255,255,0.8)`. Same token names as dark theme (`--glass-bg`, `--glass-blur`, `--glass-saturate`, `--glass-highlight`), theme-tuned values.
- Rationale: Carries the design language symmetrically across themes without inventing a light-only surface treatment.
- Trade-off: Light theme already has subtle drop shadows from `--panel-shadow-glow`; glass + shadow needs balancing so it doesn't read as "heavy frosted blob."

**Glass + existing shadow stack composition rule**: When a chrome surface gains the glass treatment, `--panel-shadow-glow` is **replaced** by the new glass-edge composition (top-edge `--glass-highlight` + bottom-edge `--bezel-shadow`), **not composited with it**. The 3 current `--panel-shadow-glow` consumers (`components.css:144 .list-item.active`, `:421 .entity-tile[aria-selected=true]/.active`, `:607 .section-nav-item[aria-current="page"]` + `chat.css:155`) get the substitution as part of Leg 03; non-chrome consumers of `--panel-shadow-glow` (if any surface) keep the existing token.
- Rationale: Light theme `--panel-shadow-glow` already composites a 2-layer drop-shadow (`tokens.css:191`). Adding glass + bezel on top stacks 4 shadow layers and reads as "heavy frosted blob" — the trade-off the prior decision flagged. Substitution keeps the chrome readable as a single integrated surface treatment.
- Trade-off: Loses the "active state has accent-tinted glow" affordance for the substituted surfaces. Compensated by the glass treatment itself carrying the active-state visual differentiation through the highlight + bezel + (optionally) `--accent-translucent` background tint.

**Aesthetic surface scope = chrome + interactive primitives**: Topbar, app-picker popover, modal overlay, sidebar/section-nav, entity tiles, editor-header, page-header, **plus** buttons (`.btn-{outlined,filled,muted-destructive}-primary`), form fields (`.field-input/textarea/select`), and the new `.checkbox-primary` primitive.
- Rationale: Captures every panel surface a control-panel metaphor wants to express AND the affordances that compose onto those panels. Goes broader than chrome-only without sprawling to every leaf primitive.
- Trade-off: Bigger blast radius than chrome-only (more places to verify post-treatment), but matches the user's intent that the aesthetic surface "everywhere downstream polish flights need it."

**Snapshot regen at flight close, mirroring Flight 1**: Vibe legs do NOT regenerate baselines mid-flight. Final regen happens once in the alignment leg via `UPDATE_SNAPSHOTS=1 pytest -m pixel`. Baselines remain gitignored (local regression artifact only).
- Rationale: Aesthetic iteration produces many small visual changes; baselines mid-stream would rot fast and add noise to the vibe sessions. Single regen at end captures final state.
- Trade-off: If a vibe leg accidentally breaks an unrelated screen, we don't catch it until the closing leg. Mitigated by the operator HAT being part of the close.

**Vibe-leg sequencing — Glass → Chrome → Indicators+Motion**: Three sequential vibe legs. Glass establishes surface treatment tokens that chrome composes onto; chrome establishes the panel-as-substrate that indicators sit on top of; motion is layered last because it depends on the static states being stable.
- Rationale: Each axis informs the next. Reordering risks rework (e.g., motion before chrome means motion curves get tuned against placeholder panels).
- Trade-off: Three legs instead of one combined vibe leg. Tradeoff is commit granularity (easier to back out one axis) vs vibe-session continuity (operator may flow across axes naturally). Vibe legs may organically blend in practice; the boundary is for artifact organization, not for forced phase-gates.

**`.checkbox-primary` extraction piggybacks on this flight; iOS-toggle stays separate**: Lift the studio.css MCP-tab checkbox treatment from Flight 1 Leg 05 into a `.checkbox-primary` primitive in `components.css`, scoped to the area-agnostic primitive layer. The admin iOS-toggle pattern (`admin.css:144-224` `.tool-enable-switch`) is a **distinct primitive** (slide-toggle, different affordance semantics — "currently on/off" reading) and is OUT OF SCOPE for this flight; it stays in `admin.css` and gets its own extraction pass in a future flight if a polish pass needs it. The gallery samples both as separate primitives so the design vocabulary distinguishes them.
- Rationale: Closes Flight 1 debrief Action Item #1 (the actual checkbox debt) in the natural home. Avoids conflating checkbox and toggle — they're different affordances for different state semantics (multi-select bool vs single binary feature flip).
- Trade-off: Defers the toggle-primitive extraction to a future flight. Acceptable — only 2 known consumers today (admin tool list, studio tool list, both already sharing via `.area-admin, .area-studio` selectors), so the duplication risk is bounded.

**Dev-mode-only gallery category surfaces in Admin sidebar**: The category id is `design-language`; the URL is `#admin/design-language`. When dev_mode is off, direct-loading `#admin/design-language` falls back to the default `system` category — the fallback path is **load-bearing on `app.js:syncUrlFromState()` (currently `app.js:123-130`)** which runs after `hydrateState` and corrects the URL hash via `history.replaceState`. `admin.js:hydrateState`'s `validIds` whitelist check (`admin.js:84` `if (validIds.indexOf(sub) === -1) return`) leaves `currentCategory` at its initialized default (`'system'`), and `serializeState` then returns `'system'`, prompting `syncUrlFromState` to rewrite the hash. Persists as live infrastructure — per-area polish flights align against it.
- Rationale: Admin is the natural home (System / Providers / Tools is a clean adjacency); dev-mode gate prevents non-dev installs from being cluttered. Reusing the existing validation+serialization mechanism keeps the change surface tiny.
- Trade-off: Adds a sidebar category that vanishes when dev mode is off; users who toggle dev mode mid-session need to refresh to see the change appear or disappear (acceptable for a dev-tool). Implicit dependency on `syncUrlFromState`-corrects-the-hash behavior is now documented here so future readers don't re-derive it.

**Gallery module organization — per-section subdirectory**: The gallery page is implemented as a *container* module (`static/js/areas/admin/design-language-page.js` — page header, section scroll container, top-level layout) plus *one file per gallery section* under `static/js/areas/admin/design-language/` (e.g., `tokens-section.js`, `typography-section.js`, `buttons-section.js`, `surfaces-section.js`, `indicators-section.js`, etc.). Each section module exports a single `render(host)` function that the container iterates. Wired into `App.admin` namespace via the same pattern as the existing admin sub-modules (`provider-editor.js`, `tools-editor.js`).
- Rationale: A 10-section gallery packed into one file produces a 600+-line module that's hostile to vibe-coding edits. Splitting matches the directory convention already established under `static/js/areas/admin/` for the admin area itself. Each vibe leg (03/04/05) edits the sections relevant to its axis without touching unrelated sections.
- Trade-off: ~10 small files instead of 1 medium file. Cheap; the directory already exists; the import pattern is established.

**Affordance patterns codification** (carried forward from Flight 1 debrief and from M04 F02 debrief action items): As this flight defines the new aesthetic vocabulary, codify the affordance patterns explicitly in `agents.md` as a **real reference section** (~60-100 lines, one paragraph + example per pattern — NOT a 30-line placeholder). **Folded into the closing alignment leg (Leg 06)**, not a separate documentation leg.
- Rationale: Two debriefs have flagged the missing affordance-patterns subsection; this is the third deferred pass. Writing it at the right size signals to downstream polish flights that this section is the canonical reference. Folding into Leg 06 keeps the doc + aesthetic-final-state commits coherent.
- Trade-off: Leg 06 grows in scope; doc-only addition is low-risk and small enough to not warrant a separate leg.

### Prerequisites

- [x] Mission 08 active; Flight 1 (Brand Foundation) completed and merged to main
- [x] Palette substrate from Flight 1 in place (`tokens.css` violet `--accent` + recycled-cyan `--accent-api`)
- [x] `pyproject.toml` `addopts` excludes `-m pixel` from default `pytest` (verified in Flight 1) so legs 1-5 can run narrow gates without stale-baseline failures
- [x] M04 design-system substrate (`@layer tokens / components / utilities`, `.area-{id}` scoping, `App` namespace) intact
- [x] `make brand-assets` available (Flight 1 Leg 01) — mascot icons regenerate on demand
- [x] `tests/test_design_tokens_a11y.py` audit and `tests/browser/design_tokens.py` Python mirror in place
- [ ] `App.config` namespace does not yet exist on the client; created in Leg 01 alongside the `/api/config` endpoint
- [ ] Narrow-test-gate fallback documented for use in legs 1-2 + 6 (broad pytest hangs against live uvicorn DB per Flight 1's SQLite WAL anomaly; same gate works)

### Pre-Flight Checklist

- [ ] All open questions in this flight's scope resolved before Leg 03 vibe sessions begin (concrete glass tokens, bezel specifics, motion primitives, indicator primitives, `--accent-api` retune are explicitly deferred to in-leg resolution and are NOT pre-flight blockers)
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined
- [ ] Legs defined

---

## In-Flight

### Technical Approach

The flight is structured around a **gallery-driven design loop**: build the canvas first (legs 1-2), then iterate the aesthetic on that canvas with continuous visual feedback (legs 3-5), then push the aesthetic from the gallery back into the canonical components and verify (leg 6). The first two legs are autonomous Developer-agent legs (scaffolding work with clear acceptance criteria); legs 3-5 are interactive vibe legs (Flight Director presents micro-iterations to the operator, applies changes, re-renders, iterates); leg 6 returns to a mix of autonomous (retune `--accent-api`, regen WCAG, regen snapshots) and interactive (HAT, agents.md affordance-patterns codification).

**Scaffolding (Legs 01-02)**:

*Leg 01 — Gallery page scaffold + dev-mode plumbing*. Server: add `GET /api/config` returning `{dev_mode: bool, version: str}` (FastAPI router, reads `settings.dev_mode` and imports `__version__` via `from the_one import __version__` — no hardcoded version string). Client: modify `app.js:225-230` `DOMContentLoaded` handler to boot-block on `fetch('/api/config')` before invoking `switchTo(...)`, populating `window.App.config` (catch path defaults to `{dev_mode: false, version: 'unknown'}` so a failed fetch never breaks boot). The existing admin sidebar `categories` list and `hydrateState` `validIds` array (`admin.js:108-117` and `:84`) get a conditional fourth entry `{id: 'design-language', label: 'Design Language'}` gated on `App.config.dev_mode`. Both the in-init `categories` push AND the `validIds` whitelist read from the same condition. Scaffold gallery as a container module `static/js/areas/admin/design-language-page.js` exporting `App.admin.renderDesignLanguagePage(contentEl)`; renders a placeholder layout (page header + section scroll container + empty body); the per-section subdirectory `static/js/areas/admin/design-language/` is created as an empty directory ready for Leg 02. The route `#admin/design-language` resolves correctly in dev mode (loads the page) and resolves to default `system` category if dev_mode is off (`validIds` rejects the sub, `syncUrlFromState` rewrites the hash to `#admin/system`).

*Leg 02 — Vocabulary inventory in gallery*. Populate the gallery body with one section per design-vocabulary axis, rendered as live demos (not screenshots), reading directly from the same CSS classes the rest of the app uses (so a token change in Leg 03 immediately reflects in the gallery):
- **Tokens**: chips showing color swatches with hex values, panel-radius samples, font-size ladder samples, motion-duration samples (TBD post-Leg 05)
- **Typography**: `h1` through `h3`, body, body-sm, body-lg, caption, tiny, mono variants, the `// section-title` eyebrow
- **Buttons**: `.btn-outlined-primary`, `.btn-filled-primary`, `.btn-muted-destructive` × sizes (default, `.btn-sm`, `.btn-lg`, `.btn-xl`) × states (default, hover-simulated via class, focus-visible, disabled)
- **Form fields**: `.field-input`, `.field-textarea`, `.field-select`, `.field-info-icon`, the new `.checkbox-primary` (from Leg 02b or Leg 03)
- **Surfaces / chrome**: `.entity-tile` (single + grid), `.section-nav-item` (default + active), `.app-picker-button` (closed + open), `.modal-dialog` static preview, `.list-item` (default + active + confirm-delete)
- **Status indicators**: `.test-result-{ok,fail,warning,pending}`, `.app-flash` (success + error), `.action-blocked-message`, `.chip` + `.chip-remove`, `.empty-state`, `.empty-canvas`
- **Tabs**: a 3-tab `tablist` sample
- **Modal** : a triggerable button that opens a representative modal
- **Markdown affordances**: code block with `.markdown-copy-btn` overlay

Each section composes the actual primitive classes; the gallery is a passive consumer of the design system, not a parallel implementation. A "section-title" eyebrow (`// TOKENS`, `// TYPOGRAPHY`, etc.) precedes each section.

**Topbar and app-picker popover are rendered as STATIC MINIATURES** inside their gallery cells — not by re-mounting the real chrome. The real `position: fixed` topbar (mounted by `renderTopBar()` in `app.js`) stays as the only live topbar in the document; the gallery samples are read-only visual previews of the chrome treatment. Same applies to the modal-dialog static preview — rendered as a non-interactive scaled-down sample, with one *separate* "Open modal" button elsewhere in the gallery section that mounts the real `App.confirmDialog` for live behavior verification.

**`// section-title` eyebrow vs `.telemetry-strip`**: At Leg 02 design time, decide whether `.telemetry-strip` is a variant of `.section-title` (composes a `--telemetry-strip-suffix` slot for the status readout) or a sibling primitive. The decision affects whether Leg 02 emits the gallery's section eyebrows from `.section-title` and Leg 05 evolves them OR Leg 05 introduces `.telemetry-strip` from scratch with its own gallery sample. Either path is acceptable; pick one in Leg 02's design so the vocabulary stays coherent.

**Vibe legs (Legs 03-05)** — interactive iteration. The Flight Director walks the operator through micro-iterations: presents 2-4 concrete options or a draft state, applies a change to tokens.css / components.css, has the operator reload the gallery to see the result, iterates. The end of each vibe leg has the operator confirm "we're done with this axis"; the leg artifact is committed with the final state. Mid-leg artifacts and dead-end experiments stay uncommitted (reverted or stashed).

*Leg 03 — Glass surface treatment*. Add new glass tokens to `tokens.css`: `--glass-bg`, `--glass-border`, `--glass-blur`, `--glass-saturate`, `--glass-highlight`. Compose them onto the in-scope chrome surfaces. Add a feature-detect or `prefers-reduced-transparency` fallback path so the design degrades gracefully (solid-tinted surface) where `backdrop-filter` is unsupported or transparency is suppressed. Iterate values until the operator confirms "this is glass." Re-run WCAG audit at leg close (glass tints can shift effective text-on-color contrast).

*Leg 04 — Chrome / bezel treatment*. Add bezel tokens to `tokens.css`: `--bezel-highlight` (top-edge), `--bezel-shadow` (bottom-edge), `--bezel-stroke` (1px outline). Establish the directional-light convention (top-left or ambient). Adjust corner machining if needed (current `--panel-radius` is 10px; tweak if the chrome feels under- or over-rounded). Compose bezels onto tiles, panels, sidebar/section-nav, picker popover, modal dialog. Iterate until the operator confirms "this reads as control-panel chrome."

*Leg 05 — Indicators + motion*. Add LED-indicator pattern (`.indicator-led` with size variants + status-color compositions: `.indicator-led--success/warning/danger/idle`). Add telemetry-strip eyebrow (`.telemetry-strip` — refines / extends `.section-title`'s `//` pattern with a mono-uppercase status readout). Add motion tokens to `tokens.css`: `--ease-tactile`, `--motion-fast`, `--motion-base`. Apply LED indicators to status surfaces (test-result, OAuth status, MCP-source connection state — survey at leg time and pick); apply telemetry-strip to one or two places where eyebrow text reads "system-y" (page headers? area-switch transitions?). Implement `prefers-reduced-motion` reset for any motion that animates layout / scale / translate. Iterate until the operator confirms "this feels alive."

**Application + close (Leg 06)** — push aesthetic back into canonical components, retune `--accent-api`, regen WCAG audit, regen snapshots, HAT.

*Leg 06 — `--accent-api` retune + WCAG + snapshot regen + HAT + affordance-patterns codification*. The vibe legs land all aesthetic values directly in `tokens.css` / `components.css` (gallery and rest-of-app evolve together), so this leg is the closing pass. **Step order is load-bearing** — each step's output is the next step's input:

1. **Retune `--accent-api`** in aesthetic context (decide if teal stays as the data-channel indicator or shifts to a tertiary aesthetic-driven hue). Apply to both themes in `tokens.css`.
2. **Mirror retuned values into `tests/browser/design_tokens.py`** (Python mirror used by the WCAG audit).
3. **Pre-flight grep sweep** (carried from Flight 1 debrief): `grep -E '#[0-9a-f]{3,6}' tokens.css` to confirm no hardcoded brand-aligned hex slipped past the retune; `grep -rIn -i 'teal\|cyan\|nexus' the_one/agents.md CLAUDE.md the_one/interfaces/web/static/css/` if the retune drops the teal entirely — annotate or update any prose references.
4. **Run WCAG audit** (`pytest tests/test_design_tokens_a11y.py -v`); iterate steps 1-3 if any glass tint or accent-api shift pushed a slot under threshold. Audit must be green BEFORE snapshot regen — otherwise snapshots capture a non-AA-compliant state.
5. **`make rebuild`** to bake the final CSS / Python mirror state into the running container.
6. **`make _ensure-playwright`** to re-install the browser dependencies (the named volume survives rebuild but the deps go missing — Flight 1 debrief Action Item #4).
7. **`UPDATE_SNAPSHOTS=1 pytest -m pixel tests/browser/test_visual_snapshots.py`** to regenerate baselines (expected: 10/12 pass; the 2 Flight 1 Known Issue blockers — `chat_with_messages` × dark + light — remain blocked by the `app_with_agent` seeder bug until Flight 5 fixes it).
8. **Walk operator through HAT** in light + dark themes, covering Chat / Studio / Admin / `#admin/design-language` gallery / OAuth callback preview. Capture any visual issues as tactical fixes inline or Known Issues if structural.
9. **Codify affordance patterns subsection in `agents.md`** as a real reference section (~60-100 lines, NOT a placeholder stub — two prior debriefs have deferred this): one paragraph + an example per pattern. Patterns: filled-primary (primary CTA), outlined-primary (secondary affordance), muted-destructive (confirm-delete), checkbox-primary (multi-select bool), the iOS-toggle pattern (kept as-is in `admin.css` — documented as a sibling primitive deferred for future extraction), indicators-as-status (test-result family, LED dots if landed in Leg 05), section-title eyebrow / telemetry-strip if landed in Leg 05.
10. **Snapshot stability re-run** without `UPDATE_SNAPSHOTS=1` to confirm new baselines stable on rerun (10/12 pass — same as step 7).

**Narrow-test-gate fallback** (carried from Flight 1): autonomous legs use `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` as the verification gate. Broad pytest may be attempted in Leg 06 once but is expected to hang on the SQLite WAL anomaly until a future maintenance pass.

### Checkpoints

- [x] Leg 1 done: `/api/config` endpoint returns `{dev_mode, version}`; `#admin/design-language` route resolves in dev mode and renders the empty page scaffold
- [x] Leg 2 done: gallery body populated with every primitive in scope; reads from canonical CSS classes; visually consistent with rest of app (pre-aesthetic-changes)
- [x] Leg 3 done: glass tokens land in `tokens.css`; chrome surfaces carry the glass treatment; degrade-gracefully fallback verified; operator confirms aesthetic
- [x] Leg 4 done: bezel tokens land; chrome reads as control-panel; operator confirms aesthetic
- [x] Leg 5 done: indicator primitives + motion tokens land; LED indicators applied to test-result family via ::before retrofit; telemetry strip gallery-only; `prefers-reduced-motion` respected; interactive primitives pass (buttons / fields / checkbox / chip / app-picker) carried V3b family treatment; operator confirms aesthetic
- [x] Leg 6 done: `--accent-api` reviewed (no retune needed); WCAG audit green (45 parametrizations); 10/12 visual-snapshot baselines regenerated cleanly (2 by Flight 1 Known Issue); agents.md Mission 08 F2 Design Language Layer subsection added; HAT walkthrough operator-confirmed

### Adaptation Criteria

**Divert if**:
- `backdrop-filter` performance is unacceptable on the operator's reference platform AND no fallback achieves the aesthetic intent — escalate to user to redesign the glass treatment as static layered surfaces (linear-gradient + drop-shadow stacks) rather than runtime blur.
- WCAG audit cannot be passed after glass + accent-api retune within two iterations — escalate to user; may require tuning glass-bg alpha higher or accepting non-AA-passing edge cases as a debt entry.
- A vibe leg organically discovers that the aesthetic is fighting the existing layout primitives (e.g., chrome bezels need a panel-radius change that breaks tile-grid layout) — pause, surface the conflict, decide whether to expand scope, defer, or abandon the change.
- The dev-mode-gated category surfaces a deeper architectural gap (e.g., the validIds whitelist in `hydrateState` is a copy-paste pattern that should be a registered-categories registry) — log as out-of-scope and continue with the minimal change for this flight.

**Acceptable variations**:
- Per-leg ordering within Leg 05 (indicators before motion vs motion before indicators) — both are independent.
- Whether motion tokens get fully fleshed-out in Leg 05 or only the primitives that have an immediate consumer; speculative motion tokens stay in the gallery as samples without graduating.
- Whether `.checkbox-primary` extraction happens in Leg 02 (as part of vocabulary inventory) or Leg 03 (alongside glass) — Leg-time call.
- Final glass / chrome / motion token names; the proposed names above are working drafts.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `01-gallery-scaffold` — Added `GET /api/config` server endpoint; client boot-blocks on fetch + `App.config` cache; conditional `design-language` Admin category gated on dev_mode; route renders empty scaffold. Plus opportunistic fix: `/api/info`'s stale `"0.1.0"` literal swapped to dynamic `__version__`.
- [x] `02-vocabulary-inventory` — Populated gallery with 9 section modules (tokens / typography / buttons / fields / surfaces / status / tabs / modal / markdown). Lifted `.checkbox-primary` primitive into `components.css` (closes Flight 1 debrief Action Item #1). Updated `mcps-tab.js` to compose the new primitive class.
- [x] `03-glass-surfaces` *(vibe)* — Added 6 glass tokens both themes. Dark = C2 violet-accent glass + gleam reflection. Light = M2 silver-chrome with violet bottom-fade. Applied to entity-tile, app-picker-popover, modal-dialog (full glass), list-item-active, section-nav-active, chat-welcome-hover (mini-glass). `prefers-reduced-transparency` fallback at token layer.
- [x] `04-chrome-bezels` *(vibe)* — Added `--bezel-shadow` (4-layer stacked-depth top-left directional) + `--bezel-shadow-mini` (2-layer edge-only). `--panel-radius` 10px → 6px. Post-close pullback retune (operator: "we went a little hard"): dropped P2 values (blur 20px → 12px, saturate dropped, gleam alphas halved, bezel dropped 10px outer glow). Reduced-transparency fallback extended.
- [x] `05-indicators-and-motion` *(vibe)* — Added `.indicator-led` primitive with `--success/warning/danger/idle` modifiers (10px reflective-crescent dots); `::before` retrofit on `.test-result-*` so existing connection-test consumers display LED automatically. `.telemetry-strip` gallery-only sample. Motion tokens (`--ease-tactile`, `--motion-fast: 150ms`, `--motion-base: 250ms`) + reduced-motion fallback. Asymmetric in/out transition pattern locked. **Interactive primitives pass** (operator-surfaced gap): buttons (V3b family applied to outlined / filled / muted-destructive / app-picker), fields (`--bezel-shadow-inset` recessed feel), checkbox (16px square, no border-radius, no gradient), chips (accent-tinted flat). Bug fix: nested-scrollbar on `#admin/design-language` page resolved.
- [x] `06-retune-accent-api-and-alignment` — 10-step ordered close. `--accent-api` reviewed and kept at recycled-cyan (aesthetic works, no retune needed). Three-dimensional grep clean. WCAG audit green (45 parametrizations). `make rebuild` clean. 10/12 visual-snapshot baselines regenerated cleanly (2 by Flight 1 Known Issue). HAT walkthrough operator-confirmed. `agents.md` Mission 08 F2 Design Language Layer subsection added (~75-line reference). Stability re-run + narrow gate 56/56.

---

## Post-Flight

### Completion Checklist

- [ ] All 6 legs completed
- [ ] `GET /api/config` endpoint exists, returns `{dev_mode, version}`; tested
- [ ] `#admin/design-language` route renders the gallery in dev mode; resolves cleanly when dev_mode is off (falls back to default category)
- [ ] Gallery shows live demos of every in-scope primitive — same CSS classes as the rest of the app
- [ ] Glass + bezel + indicator/motion tokens defined in `tokens.css` for both themes; consumed by chrome + interactive primitives
- [ ] `.checkbox-primary` primitive exists in `components.css`; consumers updated; old per-area treatment removed if migrated, or annotated as preserved-for-reason
- [ ] `--accent-api` retuned in aesthetic context (mirrored into `tests/browser/design_tokens.py`)
- [ ] WCAG audit green (all parametrizations pass)
- [ ] Visual-snapshot baselines regenerated locally; 10/12 pass on rerun without `UPDATE_SNAPSHOTS=1` (the 2 `chat_with_messages` blockers remain Flight 1 Known Issue scope — only flip to 12/12 if Flight 5 has incidentally landed, which it has not at the time of this flight design)
- [ ] `prefers-reduced-motion` and `prefers-reduced-transparency` posture verified — degrades to static / solid fallback
- [ ] `agents.md` has an affordance-patterns section codifying filled-primary / outlined-primary / muted-destructive / checkbox-primary / indicator-status semantic roles
- [ ] HAT walkthrough complete in both themes, all three areas + gallery + OAuth callback preview
- [ ] Code merged; flight status updated to `landed`

### Verification

- **Gallery reachability check**: With `THE_ONE_DEV_MODE=true`, load the app; Admin sidebar shows "Design Language" as a 4th category; clicking opens `#admin/design-language` showing the full vocabulary. With `THE_ONE_DEV_MODE=false` (default), the category does not appear in the sidebar and direct-loading `#admin/design-language` falls back to the default `system` category.
- **Aesthetic application check**: Across Chat / Studio / Admin, every chrome surface (topbar, sidebar, popovers, tiles, modals, editor headers) carries the new glass + chrome aesthetic. Every interactive primitive (buttons, fields, checkboxes) carries the new treatment. The aesthetic reads consistently in light and dark themes.
- **WCAG check**: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v` — all parametrizations pass; new glass-related parametrizations added if any text sits on a glass surface.
- **Snapshot stability check**: After regeneration in Leg 6, re-run `pytest -m pixel tests/browser/test_visual_snapshots.py` without `UPDATE_SNAPSHOTS=1`; passes cleanly (modulo the 2 Flight 1 Known Issue blockers if those persist).
- **Reduced-preference check**: With `prefers-reduced-motion: reduce` and `prefers-reduced-transparency: reduce` simulated in DevTools (or via OS toggle), the UI degrades to solid / static fallbacks without losing structural visibility.
- **agents.md check**: An "Affordance Patterns" section exists with at least 5 patterns codified (filled-primary, outlined-primary, muted-destructive, checkbox-primary, indicator-status).
