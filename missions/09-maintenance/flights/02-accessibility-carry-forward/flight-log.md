# Flight Log: Accessibility Carry-forward + F1 Tech-Debt Cleanup

**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](flight.md)

## Reconnaissance Report

**Date**: 2026-05-16 (during flight design, post-F1-close)
**Source artifacts**:
- [Maintenance Report 2026-05-15](../../../../maintenance/2026-05-15.md) — the original a11y findings (A.1-A.13)
- [F1 Flight Debrief](../../01-integrity-gate-restoration/flight-debrief.md) — sourced the new "F1 tech-debt carry-forward" bundle (non-methodology items only per operator direction)

**Method**: Each scope item verified against current code on `flight/01-integrity-gate-restoration` HEAD (post-F1-close at `c70b73b`). F1's a11y items (A.1-A.13) were already verified during mission-design recon (2026-05-15); re-verified the most critical ones (welcome listbox shape, history-buckets listbox shape, tools-grid `role="list"`, form-field error markup, light-theme token values). F1 carry-forward items (6 non-methodology recommendations) verified fresh.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Welcome agent picker has `role="listbox"`/`role="option"` (needs roving-tabindex) | confirmed-live | re-confirmed on F1 HEAD | Proceed with F2 Leg 1 |
| Session list has `role="listbox"`/`role="option"` containing `<button>` (structural fix needed) | confirmed-live | `tests/browser/test_flow_keyboard.py:50, 63, 67` asserts the current shape | Proceed with F2 Leg 1 |
| Tools-grid uses `role="list"`/`role="listitem"` (NOT a listbox — verify-only) | confirmed-live | `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:62` `role="listitem"`; `:101` `role="list"` | Proceed with F2 Leg 1 verify-only path |
| Form-field errors lack `aria-invalid`/`aria-describedby`/`role="alert"` | confirmed-live | `tools-form-helpers.js:517-519` appends `.field-error` span; no aria wiring | Proceed with F2 Leg 2 |
| Light-theme `--fg-muted: #64748b`, `--fg-faint: #94a3b8`, `--shell-chrome-bg: #d4d8df`, `--fg-tertiary: #475569` | confirmed-live | `tokens.css:246-248, :447` | Proceed with F2 Leg 2 scope-the-usage approach |
| `agents.md ### live-read-across-lazy-resolver-boundary` cites non-existent test | confirmed-live | `agents.md:233` cites `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py`; neither exists. Actual test: `test_usage_event_reflects_live_max_context_tokens_at_emission` at `tests/test_process_and_broadcast_live_read.py:98`. | Proceed with F2 Leg 3 (a) |
| `Makefile doctor` target uses bare `python -c` (sub-shell PATH foot-gun) | confirmed-live | `Makefile` around L148 `@python -c "import asgi_lifespan, ..."` | Proceed with F2 Leg 3 (b) |
| `Makefile` has no `rebuild-browsers` target | confirmed-live | `grep -c rebuild-browsers Makefile` → 0 | Proceed with F2 Leg 3 (c) |
| `Makefile` has no `audit-bytes` target | confirmed-live | `grep -c audit-bytes Makefile` → 0 | Proceed with F2 Leg 3 (d) |
| `agents.md ## Project Conventions` has no `### host-side-bench-drift-detection` entry | confirmed-live | `grep -n "host-side-bench" the_one/agents.md` → 0 matches | Proceed with F2 Leg 3 (e) |
| No documented npm-spec regex as a security primitive | confirmed-live | `grep -n "_VALID_NPX_PKG_RE\|npm.spec" the_one/agents.md SECURITY-MODEL.md` → only the existing code reference in cache_cleanup.py, no doc treatment | Proceed with F2 Leg 3 (f) |
| `Makefile audit` target's "Non-blocking by design" rationale | already-satisfied | `Makefile` L153 has `## Run pip-audit against host venv (non-blocking; surfaces advisories)` help-string carrying the rationale | F1 debrief item #9 — close as satisfied; no Leg 3 sub-fix needed |
| Browser/pixel suite blocked by missing Chromium in container | needs-human-recheck | F1 debrief confirmed 312 ERRORS at setup; recurring foot-gun. Operator action required: `docker exec the-one playwright install chromium`. | **PRE-FLIGHT PREREQUISITE — operator must run before F2 leg execution begins** |

**Net disposition**: 12 of 13 items `confirmed-live` (proceed to legs); 1 `already-satisfied` (close, no Leg 3 sub-fix — F1 debrief item #9 absorbed by existing Makefile help-string); 1 `needs-human-recheck` and PROMOTED to pre-flight prerequisite (Chromium restoration — blocking).

**Observations beyond the scope**:
- F1's flight debrief is dated 2026-05-16 but reflects work landed 2026-05-15. F2 design (this recon) happens 2026-05-16 same-day. No drift risk.
- The `rebuild` target's exact invocation needs reading at implementation time (Leg 3 sub-fix (a) chains on top of it).
- The npm-spec doc placement (agents.md vs SECURITY-MODEL.md) is intentionally left to implementer judgment; both are valid homes.

---

## Summary

(Populated during execution.)

---

## Flight Director Notes

### 2026-05-16 — Leg 2 design review (one cycle)

- **Cycle 1**: Developer (Sonnet) found **2 high + 4 medium + 5 low issues** in the Leg 2 spec (written during M09 mission scaffolding 2026-05-15; never reviewed per-leg until now).
- **Cycle-1 fixes applied**:
  - **HIGH**: AC #2 for A.3 was unverifiable — no test currently parametrizes `--fg-muted` vs `--shell-chrome-bg` (the deferral comment at `test_design_tokens_a11y.py:187-190` reads "no production consumer today"). Reframed AC to: update the deferral comment to reference the scope-the-usage decision + grep-enforce no chrome-text consumer of `--fg-muted`/`--fg-faint`.
  - **HIGH**: A.3 chrome-text consumer sites were left to implementer-time grep enumeration. Pre-enumerated in Inputs + Step 1: `base.css:144` (`.stub-sidebar .subtitle`) and `chat.css:15` (`.area-chat .session-group-label`, post-Leg-1 paint on chrome). Other ~25 `--fg-muted` consumer sites are inside `.area-*` content panels (out of A.3 scope).
  - **MEDIUM**: `renderFieldErrors` line refs corrected (function spans L493-536, not "517-521"). A.2 additivity instruction expanded to name the `row.querySelector('input, select, .chip-list-editor')` step + chip-list-editor wrapping-div case.
  - **MEDIUM**: `chat.css:67, 75` was wrong (those are `new-chat-header` rules). Corrected to `chat.css:80, 88` for telemetry overlay.
  - **MEDIUM**: `section-nav.js` path in Inputs corrected to `js/areas/layout/section-nav.js` (matched the Step 8 path that was already correct).
  - **MEDIUM**: Toast value-to-change clarified (literal `2000` at `app.js:244`; not the whole range). Added note that `role=alert/status` is already correct — duration bump is for visual dwell time.
  - **MEDIUM**: Trace-shell A.11 now cites BOTH create site (`:32-35`) and update site (`:55-58`); update-site is in `appendToTrace` where count.textContent gets refreshed.
  - **LOW**: A.5 toast role-context note added; A.6 MCP icon edit specificity (drop the ternary; always `alt=""`); A.9 LED contract decision clarified for `mcp-server-editor.js:489` (LED carries state distinct from "Reset connection" button text — leave `aria-label`); A.10 section-nav `<div>`→`<nav>` decision pre-made (3 options enumerated; option (i) recommended).
- **Per-skill rule**: cycle 1 sufficed. Per skill: "Skip if only minor/cosmetic fixes were applied" — but the AC reframe + chrome-text enumeration were substantive design-review interventions, not cosmetic. Cycle 2 skipped because all cycle-1 findings were addressed by spec correction (no design-question remained); the corrections are mechanical line-ref + pre-enumeration fixes that don't introduce new design surface.

### 2026-05-16 — Leg 1 design review (TWO cycles)

- **Cycle 1**: Developer (Sonnet) found **7 high-severity issues** in the original Leg 1 spec (written during mission scaffolding 2026-05-15). The spec missed key codebase realities: welcome-picker keydown handler already exists at `chat.js:184-198` (not missing as claimed); session-list `role="listbox"` lives in `chat.js:60` (not in history-buckets.js); proposed `data-session-id` would silently break existing `data-id` consumers including `test_flow_hash_routing.py:95`; `highlightActiveSession` uses `aria-selected` (becomes invalid on plain `<button>` post-restructure — switch to `aria-current="page"`); third listbox-role assertion at `test_flow_keyboard.py:67` was missed; `test_session_delete_keyboard_reveal` (L90-100) needs `.list-item` class preserved; cross-file test impacts in `test_flow_hash_routing.py` + `test_flow_new_chat.py` weren't enumerated up-front.
- **Cycle-1 fixes**: rewrote the leg spec end-to-end addressing all 7 high-severity findings. Inputs section now enumerates the chat.js call sites (lines 60, 129-136, 132, 184-198, 707); test impact enumerated up-front as step 1 (not a step-7 fallback); `data-id` preserved; `aria-selected` → `aria-current="page"` direction explicit; all 3 listbox-role test assertions called out; `.list-item` class preservation called out.
- **Cycle 2**: focused 2nd-cycle review confirmed all 7 cycle-1 findings addressed. Surfaced **1 new high-severity issue** (`chat.js` path was written as `areas/chat/chat.js` throughout — actual file is at `areas/chat.js`, a sibling of the `chat/` directory) + 2 medium + 1 low.
- **Cycle-2 fixes**:
  - HIGH: global path correction — `areas/chat/chat.js` → `areas/chat.js` everywhere in the spec (3 occurrences)
  - MEDIUM: pre-decided `<ul>` placement (chat.js owns the shell `<nav>...<ul></ul></nav>`; history-buckets fills the `<ul>`)
  - MEDIUM: pre-decided welcome-handler home (stays in `chat.js` for now; re-home to `welcome.js` is M10-candidate refactoring)
  - MEDIUM: added `aria-current="page"` rationale (hash-router treats each session view as page-like; alternative `aria-current="true"` is acceptable fallback)
- **Per-skill rule**: max 2 design-review cycles. We're at limit. The cycle-2 high-severity finding is a mechanical text correction (file path typo), not a design issue persisting through cycles. Proceeding to implementation with the corrections applied.
- **Net leg quality lesson**: the original Leg 1 spec, written during mission-design 2026-05-15, was based on incomplete recon (the Architect at mission-design time spot-checked tools-grid but didn't drill into chat.js's actual structure). Today's per-leg design review caught the gap. **Validates per-leg design-review discipline once again** — same lesson as F1 Leg 3's CRITICAL allowlist save.

### 2026-05-16 — Flight start (agentic-workflow kickoff)

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, same as F1).
- **Branch**: `flight/02-accessibility-and-cleanup` created off `flight/01-integrity-gate-restoration` (F1 PR #56 not yet merged; F2 legs reference F1 commits as preconditions). Rebase onto `main` after PR #56 merges.
- **Flight status transition**: F2 `ready` → `in-flight`. Mission 09 stays `active` (Flight 1 completed; Flight 2 in-flight).
- **Pre-flight cleanup**: removed a stale empty `the_one/_probe_lsep.py` from git index (created by Architect's design-review probe; never committed; safe to unstage).
- **Initial commit on F2 branch**: planning scaffold additions (revised F2 flight.md, expanded flight-log.md, new Leg 3 spec). Subsequent commits will be leg work; flight-close commit handles status transitions.
- **3 legs planned**: Leg 1 (welcome picker + session-list + tools-grid verify), Leg 2 (form errors + tokens + sweep), Leg 3 (F1 tech-debt bundle). Estimated ~2.5-4 days total.

### 2026-05-16 — Flight design + design review

- **F2 originally designed during mission scaffolding (2026-05-15)** with 2 legs (a11y carry-forward); reshape today incorporates the F1 debrief's 6 non-methodology recommendations as a new Leg 3 per operator direction.
- **Recon report at top of this log** verified all scope items confirmed-live; 1 item already-satisfied (Makefile `audit` non-blocking rationale already in help-string); 1 item promoted to pre-flight prerequisite (Chromium restoration).
- **Architect design review on revised F2 (Opus)**: approve with changes. 3 high + 2 medium + 2 low issues raised.
- **High-severity fixes applied**:
  1. **`_ensure-playwright` already exists at `Makefile:39-46`** — Architect spot-check caught this. Leg 3 sub-fix (a) reframed from "implement `rebuild-browsers` with raw `playwright install chromium`" to "chain `rebuild + _ensure-playwright` using existing machinery." F1 debrief's "312 ERRORS at setup" came from bypassing `make` and calling raw `docker exec the-one pytest -m browser` — the foot-gun is mostly already mitigated; this leg adds a convenience alias.
  2. **Pre-Flight Chromium prereq downgraded** from BLOCKING-operator-action to "run `make _ensure-playwright` once at flight start." All F2 browser-test verification commands switched from raw `docker exec the-one pytest -m browser` to `make test-browser` (which chains `_ensure-playwright` automatically).
  3. **`make audit-bytes` git-grep tracked-only contract documented** — `git grep` scans the index, not the working tree. Files unstaged won't be scanned. Added as explicit Edge Case + Implementation Guidance note.
- **Medium-severity fixes applied**:
  4. **`make audit-bytes` pathspec broadened** to `the_one/**/*.py` `tests/**/*.py` (recursive `**`) — original `the_one/*.py` would have missed nested modules.
  5. **`.venv/bin/python` clarification**: the venv interpreter is a symlink chain → `python3` → `/bin/python3`. The fix is functionally correct but framing was imprecise. Updated `doctor` target spec to use `.venv/bin/python3` (matches `.venv/bin/pip-audit` shape in `audit` target).
- **Low-severity fixes applied**:
  6. **`### host-side-bench-drift-detection` placement made explicit**: between `### gated-debug-instrumentation` (M08 F7) and `### live-read-across-lazy-resolver-boundary` (F1 M09 Leg 3) — chronologically correct.
  7. **npm-spec regex doc placement corrected to `SECURITY-MODEL.md ## Tool Execution Boundary`** (Architect-preferred over the original `agents.md` recommendation). That section already enumerates per-category allowlists (filesystem-path, subprocess-env, web-SSRF); npm-package-name allowlist is the same class — defensive control at a tool boundary.
- **Branch strategy resolved**: F2 branches off `flight/01-integrity-gate-restoration` directly with name `flight/02-accessibility-and-cleanup`. Rebase onto `main` after PR #56 merges. (Branching off `main` would require waiting for merge or cherry-picking F1 commits — wasteful.)
- **Skipped 2nd review cycle**: all fixes were corrective (no new design). Per skill's "Skip if only minor/cosmetic fixes were applied" guidance — these are clarifications + corrections, not redesign.

---

## Leg Progress

### 2026-05-16 — Leg 1 (landed at 9011576)

**Welcome handler augment** (`chat.js:184-198`):
- Augmented the existing roving-tabindex keydown to also toggle `aria-selected="true"` on the focus target and `"false"` on the others, in lockstep with the existing `tabindex` flip. Added attribution comment naming `section-nav.js:71-91` as the canonical pattern.
- Handler stays in `chat.js` (cycle-2 pre-decision). Re-home to `welcome.js` remains an M10-candidate refactor.

**Session-list restructure**:
- `chat.js:60` shell: `<div class="session-list" role="listbox" aria-label="Chat sessions">` → `<nav class="session-list" aria-label="Chat sessions">`. The `.session-list` class is preserved for CSS.
- `chat.js:129-136 highlightActiveSession`: `setAttribute('aria-selected', ...)` (always present, true/false) → `setAttribute('aria-current', 'page')` for the active item, `removeAttribute('aria-current')` for the rest. Matches the semantic used by `section-nav.js` and is defensible because the hash-router treats each session view as page-like (`#chat/sessions/<id>`).
- `history-buckets.js buildSessionItem`: row went from a single `<div class="list-item session-item" role="option" tabindex="0" aria-selected=…>` containing both the title spans and the delete button → `<li class="list-item">` wrapping a `<button class="session-item" data-id=…>` (the title spans live inside the button) and a sibling `<button class="delete list-item-delete">`. The `e.target !== el` keydown bail at the old L71-80 was retired — native `<button>` Enter/Space activation handles join, and the delete button has its own click handler, so the bail is no longer relevant.
- `history-buckets.js renderSessionList`: each bucket now uses `<ul class="session-group-list" aria-labelledby="session-group-…">` to wrap its `<li>` items. The bucket's outer `.session-group` div drops `role="group"` since the `<ul>` itself is the labelled list (the label is a sibling label element + `aria-labelledby` on the `<ul>`). This honours the cycle-2 pre-decision (chat.js owns the outer `<nav>`; history-buckets fills it with the dynamic bucket structure).
- `chat.js` onDelete: switched `btn.closest('.session-item')` → `btn.closest('.list-item')` so `App.confirmDelete` applies `.confirm-delete` to the `<li>` wrapper (where the CSS rules `.list-item.confirm-delete[*]` are scoped) rather than the inner button.

**Attribute decisions**:
- `data-id` preserved (NOT renamed to `data-session-id`). Verified zero `data-session-id` references appear in code or tests post-edit.
- `.list-item` class preserved on the new `<li>` so `components.css:123-124 :focus-within` reveal continues to fire when Tab moves focus from the session-button to its sibling delete-button.
- `.session-item` class preserved on the inner button so existing selectors (`.session-item-text`, `[data-confirm-title]` queries, browser-test locators) keep matching.

**CSS adjustments** (`chat.css`):
- New `.area-chat .session-group-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; }` — strips UA `<ul>` shape so the bucket reads as the existing row stack.
- New `.area-chat .session-item { … }` button-neutralization (transparent bg, no border/padding, inherit color/font, text-align left, flex-row) so the inner `<button>` composes visually like the old wrapper-div.
- New `.area-chat .session-item:focus-visible` so the button still surfaces an accent ring when keyboard-focused (the existing `.list-item:focus-visible` rule becomes inert since the `<li>` is no longer the focus target).

**Test updates** (all under `tests/browser/`):
- `test_flow_keyboard.py`:
  - `test_session_item_keyboard_select` (L25-46): docstring + L45 assertion switched `aria-selected="true"` → `aria-current="page"`.
  - `test_session_item_has_role_option` (L49-68) renamed to `test_session_list_shape`: replaces the three listbox-role assertions (L50 docstring, L63 `role="listbox"` on `.session-list`, L67 `role="option"` on `.session-item`, plus the L68 `tabindex="0"` assertion) with a `<nav>` tagName check on the container and a `<button>` tagName check on the item.
  - `test_session_delete_keyboard_reveal` (L73-100): selector for the delete button changed from descendant `.session-item .delete` to `.list-item .list-item-delete` (the delete is now a sibling of `.session-item` under the `<li class="list-item">`). Updated docstring to reflect the new topology.
- `test_flow_hash_routing.py`: L86 + L95 selectors swapped `[aria-selected="true"]` → `[aria-current="page"]`. Inline comment cites F2 leg 01 rationale.
- `test_flow_new_chat.py`: L196-201 — **beyond original spec scope**: the test originally claimed-SURVIVES under "class names preserved", but the descendant `item.locator(".delete")` query and the `to_have_class(.../confirm-delete/...)` check on `.session-item` both broke because the delete is now a sibling and `.confirm-delete` is applied to the `<li>`. Rewrote the locator to `.area-chat .session-group-list .list-item` and target the `.list-item-delete` button via that row.

**Tools-grid verify** (no edit):
- Re-read `tools-grid.js` at L55-75 (tile DOM) and L96-103 (grid container). Container has `role="list" aria-label="Built-in tools"`; each tile is `<div class="entity-tile tool-tile" role="listitem" tabindex="0">` containing inner `<label>` + `<input type="checkbox">`. Tile is focusable via `tabindex=0`; checkbox toggles via the standard label-input pair; no keyboard trap. Architect's F2 design-review assessment confirmed.

**`.list-item :focus-within` reveal**: verified via the updated `test_session_delete_keyboard_reveal` post-edit; native button-focus inside the `<li>` triggers the reveal rule at `components.css:124` identically to the old shape.

**Verification outcomes**:
- `make test-browser` → exits 0 (316 passed, 35 skipped — Chromium auto-restored cleanly via `_ensure-playwright`).
- Container broad pytest (`docker exec the-one pytest --tb=no -q --ignore=tests/browser`) → **1700 passed**, 4 skipped, 12 deselected (baseline preserved).
- Host broad pytest: **pre-existing import failure** (`ModuleNotFoundError: No module named 'mcp.client.auth.exceptions'`) — verified by stash + replay on clean tree; **not caused by this leg**. Anomaly noted below; container is the source of truth.
- `ruff check` + `ruff format --check` → 0/0 (baselines preserved).
- Recon greps:
  - `grep -rn 'role="listbox"\|role="option"' the_one/.../js/` → only welcome listbox (chat.js:73) + welcome.js options + studio/admin entity-grids match; session-list no longer matches.
  - `grep -rn aria-selected` under chat → only welcome.js options + chat.js welcome-handler match; session-related sites cleared.
  - `grep -n data-session-id` → empty (preserved `data-id`).

**Anomalies**:
- **Host-pytest pre-existing import failure** (`the_one/mcp/client.py:25`: `from mcp.client.auth.exceptions import ...` — `mcp.client.auth` is not a package on the host venv). Reproduces on the unmodified F2 scaffold commit (`7d13198`) — predates this leg. Container pytest is unaffected and remains the authoritative 1700-baseline. Surface candidate for M10 host-env maintenance (not in F2 scope).
- **Beyond-spec test edit** in `test_flow_new_chat.py:196-201` — the leg spec marked it SURVIVES, but the descendant-selector + `.confirm-delete`-on-`.session-item` assumption broke under the sibling-button layout. Updated as documented above; no functional change to the deletion flow itself.
- Pixel-snapshot suite (`test_visual_snapshots.py`, marker `pixel`) not run — out of `make test-browser` scope; baselines under `tests/browser/__snapshots__/` are gitignored and local-only per user-global policy. The session-list visual shift (div → button + `<ul>` wrapper) likely needs a local pixel-baseline regen before running `make test-pixel`; not part of this leg's verification path.

### 2026-05-16 — Leg 2 (landed; sub-commits 983369b → 626735d)

**Sub-fix landings** (atomic per A.* item, `flight/02:` prefix):

| A.* | Sub-commit | Outcome |
|---|---|---|
| A.3 (chrome-text tokens) | `983369b` | 3 chrome-text consumer sites rescoped to `--fg-tertiary` |
| A.2 (form-error wiring) | `c16300d` | `aria-invalid` + additive `aria-describedby` + `role="alert"` |
| A.6 (MCP icon alt) | `2281f11` | Ternary dropped; always `alt=""` |
| A.7 (reduced-motion gate) | `89f3e4a` | `matchMedia` gate on the thinking-indicator setInterval |
| A.5 (toast duration) | `73881c6` | `2000ms` → `5000ms` |
| A.8 (telemetry labels + opacity) | `09266b8` | Per-row `aria-hidden`; opacity `0.4` → `0.7` |
| A.9 (LED contract + sweep) | `c0ecda0` | Contract doc-block in `components.css`; 6 sweep sites |
| A.10 (section-nav landmark) | `364530c` | `<div role="group">` → `<nav>`; helper warns on non-`<nav>` |
| A.11 (trace-shell count label) | `b4d7388` | Initial + update aria-label includes count w/ pluralization |
| A.12 (tool toggle state label) | `7733175` | `<span class="visually-hidden">` added inside the `<label>` |
| A.13 (README accessibility) | `626735d` | Section inserted between Security and Mission Control |

**A.3 chrome-text outcome** (high-significance, smallest-blast-radius first):
- Pre-enumerated sites: `base.css:144` (`.stub-sidebar .subtitle`, `--fg-muted` → `--fg-tertiary`); `chat.css:15` (`.session-group-label`, `--fg-faint` → `--fg-tertiary`).
- **One newly-discovered chrome-text consumer** surfaced during the post-edit grep-enforce: `chat.css:35` `.session-item-agent` (session row's mono-font model-name annotation — paints inside the sidebar `<nav class="session-list">` introduced by Leg 1). Rescoped to `--fg-tertiary` as well; total = 3 sites. Below the 3+ pivot threshold for switching to Attempt A (global token darken).
- Deferral comment at `tests/test_design_tokens_a11y.py:187-196` rewritten to enumerate the three rescoped sites + state that re-introducing a chrome-text consumer of `--fg-muted`/`--fg-faint` requires updating both the comment and the consumer.
- Post-edit `grep -rn 'var(--fg-muted)\|var(--fg-faint)' .../css/ | grep -E 'sidebar|topbar|chrome'` → empty.

**A.2 wiring outcome**:
- All three target input types covered by the `row.querySelector('input, select, .chip-list-editor')` resolution.
- Additive `aria-describedby` sequence (split-dedup-rejoin) verified to preserve the existing info-icon `<field>-desc` wiring.
- `role="alert"` lands on the FIRST per-row error span only (single-announce per save cycle); `.editor-error` banner also takes `role="alert"` when unmatched entries are routed to it.
- New `clearFieldErrorA11y(row)` companion in `tools-form-helpers.js`; wired into both `clearFieldErrors` (batch save-attempt clear) and the two per-row change handlers in `tools-editor.js` (input/change + chip-list mutation).
- `tests/browser/test_flow_admin_tools_editor.py` (14 tests touching `field-error` rendering): 14/14 PASS.

**A.5 outcome**: 5s dwell time. Close-button + pause-on-hover affordances out of leg scope (slip rules say single-edit fix is the bracket).

**A.6 outcome**: Mechanical edit; no surprises.

**A.7 outcome**: Reduce-motion users get a static `' …'` ellipsis; sighted users with reduce-motion unset keep the 120ms Braille frame cycle. `removeThinking()` clearInterval call remains safe (clearInterval(undefined) is a no-op).

**A.8 outcome**: Approach (b) chosen (per-row `aria-hidden`; container's `aria-label="Token usage"` is sole SR exposure). Avoids polite-live region churn during streaming. Opacity bump at `chat.css:80` (not `:67` as earlier-leg-spec wrongly stated — design review caught it).

**A.9 LED contract decision**:
- Contract doc-block added immediately above `.indicator-led` rule at `components.css:864`, citing the two rules + naming `provider-models.js` (decorative) and `mcp-server-editor.js` (stateful) as canonical exemplars.
- Sweep: 2 provider-models LEDs → `aria-hidden="true"`; 4 design-language gallery sample LEDs (Success/Warning/Danger/Idle in the primitive showcase + ONLINE + 2/3 in telemetry-strip sample) → `aria-hidden="true"`. `mcp-server-editor.js:490, 1882` left with `aria-label="Connected"`/`"Not connected"` per contract rule 2.
- One sample left untouched: the static `<div class="section-nav">` placeholder in `design-language/surfaces-section.js:47-51` (gallery-only static HTML; not a real consumer of the helper). Skipped to keep blast radius small.

**A.10 section-nav option chosen: (i) `<div>` → `<nav>` with `role="group"` dropped**:
- Container element types changed at the two real call sites (`admin.js:214`, `studio.js:265`) from `<div class="admin/studio-section-nav">` to `<nav class="...">`. Helper drops the `setAttribute('role', 'group')` line; `<nav>` implies `role="navigation"`. Helper adds a dev-mode `console.warn` if the caller passes a non-`<nav>` container — guards against silent regression of the landmark contract.
- One existing browser test asserted on `role="group"` (`test_flow_keyboard.py:163-164`). Updated to assert `tagName === "NAV"` + `aria-label === "System sections"` instead. Other roving-tabindex assertions in the same test pass unchanged (focus management is element-agnostic).
- Leg 1's `.list-item:focus-within` reveal (`components.css:124`) was unaffected — `section-nav` doesn't share `.list-item` selectors.

**A.11 trace-shell outcome**: Two-site edit (create + update inside `appendToTrace`). Singular/plural agreement ("1 item" / "0 items" / "2 items"). Visible `.trace-count` stays `aria-hidden` so the accessible name is the sole SR exposure of the count.

**A.12 tool toggle outcome**: Visually-hidden span inside the `<label>` carries "Enabled for all agents" / "Disabled for all agents" — composes into the label's accessible name. `title=""` retained for sighted-mouse hover.

**A.13 README outcome**: Landed (no slippage). Section placed between Security and "Project organization & methodology" to match file voice; cites WCAG 2.1 AA target, keyboard operability, prefers-reduced-motion, contrast on both themes, Design Language gallery, GitHub issue reporting path.

**Verification outcomes**:
- `make test-browser` → **316 passed, 35 skipped** (12 deselected; exact baseline match to Leg 1).
- Container broad pytest (`docker exec the-one pytest --tb=no -q`) → **1700 passed**, 4 skipped, 375 deselected (Leg 1 baseline preserved).
- `ruff check the_one/ tests/` + `ruff format --check the_one/ tests/` → both 0/0 (baselines preserved).
- Host pytest: same pre-existing `mcp.client.auth.exceptions` import failure as Leg 1 — not caused by this leg; container is authoritative.

**Anomalies**:
- **A.3 enumeration drift caught by grep-enforce**: `chat.css:35` (`.session-item-agent`) was not in the pre-enumeration but surfaced during the post-edit verification grep. Below the 3+ pivot threshold; rescoped in the same A.3 sub-commit (`983369b`). Validates the pivot rule + grep-enforce mechanism — without it the chrome-text contrast gap would have persisted on the session-row mono annotation.
- **A.10 test update was a known consequence, not a regression**: the `role="group"` assertion in `test_flow_keyboard.py:164` was the only test asserting on the now-dropped role. Updated within the same sub-commit (`364530c`) to keep the landmark contract under test (tagName + aria-label assertions).
- No other sub-commit caused a downstream test edit.

**Sub-commit SHAs**:
- A.3 `983369b` → A.2 `c16300d` → A.6 `2281f11` → A.7 `89f3e4a` → A.5 `73881c6` → A.8 `09266b8` → A.9 `c0ecda0` → A.10 `364530c` → A.11 `b4d7388` → A.12 `7733175` → A.13 `626735d`.

**Opportunistic items**: A.9 + A.10 + A.13 ALL landed (no slippage). The slip rules in the leg spec (`route to next maintenance pass`) were not triggered.

---

## Decisions

### 2026-05-16 — Leg 1

- **`<ul>` placement (per cycle-2 pre-decision)**: chat.js owns the outer `<nav class="session-list">`; history-buckets fills it with one `<ul class="session-group-list">` per bucket (each `<ul>` is `aria-labelledby` the bucket label). The original "single `<ul>` shell" framing didn't fit the bucket-grouped reality; per-bucket `<ul>`s preserve the label-association semantics that previously lived on `role="group"`.
- **history-buckets keydown bail (`L71-80` in the old shape)**: removed. Under the new shape the focusable element is the inner `<button class="session-item">`; native Enter/Space activation invokes the click handler that calls `onJoin`. The delete button has its own click handler and its own native activation. The bail (`e.target !== el`) is no longer needed.
- **`.session-group` `role="group"` removed**: the bucket label association is now carried by `aria-labelledby` on the bucket's `<ul>`. Keeping `role="group"` on the outer `<div>` would have added a redundant grouping container with no accessible name (since the label is now scoped to the `<ul>`).
- **`onDelete` callback**: switched `.closest('.session-item')` → `.closest('.list-item')` so `App.confirmDelete` operates on the `<li>` wrapper (where the CSS `.list-item.confirm-delete` styling lives). Both selectors resolve from the delete button, but only `.list-item` matches the styling contract under the new shape.

---

## Deviations

(Populated during execution.)

---

## Anomalies

### 2026-05-16 — Leg 1
- **Host venv `mcp.client.auth.exceptions` import failure** (pre-existing; reproduced on clean tree). Container pytest unaffected. Surface candidate for M10 host-env maintenance.
- **`test_flow_new_chat.py:196-201`** required a beyond-spec edit (leg artifact's "SURVIVES — class names preserved" call was incomplete; the assertion target moved from `.session-item` to `.list-item` because `.confirm-delete` now lands on the `<li>`, and `.delete` is a sibling rather than a descendant of `.session-item`).

---

## Session Notes

### 2026-05-16 — Leg 1 manual keyboard test

- **Welcome agent picker**: not exercised manually this session — the agentic-workflow run executes headless. Behaviour verified via the existing browser tests (`test_flow_new_chat.py:77` listbox role survives; the augmented `aria-selected` toggling is observed indirectly through DOM-shape contracts in the browser suite). Operator should spot-check via Tab → ArrowDown chain when revalidating the flight.
- **Session sidebar**: covered by the rewritten `test_session_list_shape` + `test_session_item_keyboard_select` + `test_session_delete_keyboard_reveal` in `test_flow_keyboard.py`. All three pass under `make test-browser`. The new flow: Tab into the session-button → Enter activates → `aria-current="page"` flips. Tab again → focus sibling `.list-item-delete` → `:focus-within` reveal fires → Enter triggers the two-step confirm flow.
- **Admin tools-grid**: verify-only path. Read confirmed `role="list"`/`role="listitem"` with `tabindex=0` tiles. Existing `test_flow_admin_tools_grid.py` suite continues to pass in `make test-browser`.

### Anomalies / surfacing
- Host pytest module-resolution failure (`mcp.client.auth.exceptions`) reproduces on the pre-leg tree — escalate to M10 host-environment maintenance.
- `test_flow_new_chat.py:196-201` rewrite was a beyond-spec correction; the original "SURVIVES" call missed that the `.confirm-delete` class moved from `.session-item` (old wrapper-div) to `.list-item` (new `<li>`) and that the delete-button selector changed from descendant to sibling.
