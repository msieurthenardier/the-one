# Leg: theme-sync-guards-docs (Leg 3)

**Status**: completed
**Flight**: [Design Language v3 — Tokens and Type](../flight.md)

## Objective

Add cross-tab theme synchronization (both directions) with a browser regression test; land the banned-token guard and backtick tripwire (probe-tested); fix the `verify-serving` port-ownership false-success; update the design gallery's token showcase for v3; rewrite the `agents.md` design-system section and promote the goldfinch apparatus doctrine into durable docs.

## Context

- Flight DDs: "Cross-tab theme sync ADDED (not amended)", "Guards" (banned-token + tripwire land here; mirror-sync landed Leg 1), "Docs land in-flight", "Design gallery updated minimally".
- Mission Known Issues: `make restart`/`verify-serving` false-success when a foreign server holds the port (F2 L1 finding; FD assigned the fix here).
- Verified ground truth: NO `storage` listener exists in `static/js`; `App.theme.set` (theme.js:90-102) writes localStorage + dispatches a same-document CustomEvent only; choosing auto REMOVES the key (so the cross-tab unset event arrives as `newValue === null`).
- Legs 1–2b (landed, uncommitted): v3 tokens live; retired families + shell tokens deleted; `prefers-reduced-transparency` gone.

## Inputs

- `the_one/interfaces/web/static/js/theme.js`; `tests/browser/` (regression test home); `tests/test_ui_guards.py` + `tests/_ui_guard_helpers.py`; `Makefile` (`verify-serving`); `the_one/interfaces/web/static/js/areas/admin/design-language/tokens-section.js`; `the_one/agents.md`

## Outputs

1. **theme.js**: `window.addEventListener('storage', …)` on `theme-preference` events. Exact semantics (design-review reconciled): `apply(resolve(e.newValue === null ? 'auto' : e.newValue))` — read the EVENT's newValue, never re-read localStorage (`reapply()` re-reads — do not use it here); garbage values degrade to auto via `resolve`. The listener MUST also dispatch `theme-preference-changed` so a mounted System-page toggle in the receiving tab updates its checked state. (Verified: internal `apply()` at theme.js:51-53; storage events never fire in the originating tab — no echo guard needed, note it in a comment.) FIRST verify current behavior live (two tabs on 8485) and record it in the flight log.
2. **Browser regression test**: two pages in the SAME BrowserContext (`page.context.new_page()` — storage events do not cross contexts; never `browser.new_context()`). The context uses `color_scheme="no-preference"` → auto resolves dark, so sequence light→auto to make the null-path observable. Assert page B's `data-theme` AND the page-B theme-toggle checked state (data-theme alone passes even if the CustomEvent dispatch is forgotten). Use expect polling, not sleeps. Drive page A via the System theme control (realism); registry updated if new testids.
3. **Banned-token guard** in `test_ui_guards.py`: fails on any occurrence in `static/css/*.css` of retired vocabulary: `--accent-glow`, `--status-*-glow`, `--glass-`, `--bezel-`, `--btn-v3`, `--panel-shadow`, `--shell-`, `backdrop-filter`, `clip-path: polygon` (chamfer geometry — EXCEPT a documented allowlist entry for `components.css` tab L-bracket until Flight 3 removes it), `prefers-reduced-transparency`. Comments count as hits (they were cleaned in 2a; keep them out). **Probe-test** (plant a banned name in a CSS comment → fails naming file+line → revert).
4. **Backtick tripwire** in `test_ui_guards.py`: fails on template literals containing `data-testid` and on backtick innerHTML RHS anywhere in `static/js` (comments scan like live code, per project convention). **In-scope prep**: reword the four existing backtick-quoted `data-testid` comments (`agent-editor.js:107`, `connector-form-discord.js:137`, `connector-editor.js:413,840`) to use quotes — fix the comments, do not carve a comment exclusion. **Probe-test** both patterns.
5. **verify-serving ownership check + port plumbing** (Makefile), three parts (design-review corrected):
   - Parameterize the ENTIRE target's base URL on `THE_ONE_PORT` (both curl loops currently hardcode 8484 at Makefile:81-96 — today this false-FAILS against our healthy 8485 instance, the inverse polarity of the original bug).
   - **Port-suffixed pidfile (FD decision)**: default `THE_ONE_PIDFILE ?= .the-one.$(THE_ONE_PORT).pid` so two make-managed instances can't kill each other (`make restart` for 8485 must never kill an instance recorded by another port's pidfile). Keep a migration note; update `.gitignore` pattern if needed; `make down`/`logs` read the same variable.
   - Ownership check: after the 200-check, assert the pid listening on the target port (`ss -tlnp`, fall back `lsof`) equals the pidfile pid; on mismatch OR unresolvable pid, FAIL loudly (never skip) naming what was found.
   - **Negative probe (FD-approved apparatus)**: the original squatter is gone — spawn a disposable second the-one instance (separate data-dir + its own pidfile) on a probe port, point verify-serving at that port with a pidfile that does NOT match, assert it fails naming the foreign pid; kill and clean up. Positive probe: passes against our 8485 instance.
6. **tokens-section.js**: add spacing-scale, radius, and shadow swatch rows for the v3 tokens (`--space-*`, `--radius-*`, `--shadow-*`); COLOR_TOKENS list already glow-free (2a).
7. **agents.md design-system section rewritten for v3**: token roles + ladder semantics, accent restraint rule (interactive/selected states only), weight discipline (400/500-600, no 700 chrome), both-themes-designed contract, full-palette AA audit contract + deliberate-exception policy, focus-visible pinned form + sanctioned variants, two-shadow system, spacing/radius scales, section-title quiet treatment. Prune stale alien-console references. **Apparatus doctrine** added to the testing docs area of agents.md: goldfinch as canonical browser apparatus; printToPDF provenance-certain pixel fallback (print CSS mutes fills — judge active states via a11y checked-state); multi-tab provenance discipline (unattributed frames are non-evidence); a11y rendered/notRendered discrimination; run-tab foregrounding before computed-style probes after theme flips; versioned-URL stylesheet caching after `make restart` (hard-reload the tab); port-ownership pitfall (the squatter class of failure).

## Acceptance Criteria

- [x] Both-direction cross-tab sync works live (manual verify on 8485) AND the browser regression test passes via `scripts/run-tests.sh`
- [x] Banned-token guard green on the swept tree; probe-tested (planted comment fails naming file+line)
- [x] Backtick tripwire green; probe-tested (both patterns)
- [x] `verify-serving` negative probe fails naming the foreign pid (disposable-instance apparatus); positive probe passes against 8485; `make up`/`restart`/`down` work end-to-end with THE_ONE_PORT + port-suffixed pidfiles
- [x] Gallery shows spacing/radius/shadow swatches (visual check on 8485, dev-mode)
- [x] agents.md: no stale alien-console design guidance remains (grep for glow/glass/bezel/chamfer in the design section); apparatus doctrine present
- [x] `make test-unit` green; targeted browser slice green (the new theme-sync test + test_theme_toggle_cleanup.py); `ruff` clean; testid/sink guards green (registry updated if new testids — none added; the test drives the toggle via its existing `data-theme-pref` attributes)

## Verification Steps

- Live two-tab check; pytest guard slice + probes; Makefile checks against both ports; gallery visual; agents.md greps; suites

## Implementation Guidance

1. theme.js: keep the listener tiny; delegate to the existing internal apply function; guard against same-tab echo (storage events don't fire in the originating tab — no guard needed; note this).
2. Browser test: Playwright two-page pattern — `context.new_page()` twice against the same app fixture; drive via the System page theme control or `App.theme.set` evaluate (prefer UI control for realism at page A; assert `data-theme` at page B).
3. Banned-token guard: reuse the file-walking helpers; clip-path allowlist as per-file + expected-count-1 (components.css — count-anchored, not line-anchored); keep prefix-anchored patterns (`--bezel-` etc. — a bare-word pattern would false-positive on the components.css:437 comment). Opportunistic: fix the stale `prefers-reduced-transparency` docstring at `tests/_ui_guard_helpers.py:212`.
4. verify-serving: current implementation curls module URLs — add the ownership assert after; keep output format consistent.
5. agents.md: rewrite the design section in place; keep unrelated sections untouched; the apparatus doctrine cites the F1 run log + F2 L1/L2a apparatus findings as sources.

## Edge Cases

- **storage event ordering**: rapid set→unset sequences; the listener reads the EVENT's newValue, not a re-read of localStorage (avoids racing a subsequent write).
- **Browser test flakiness**: storage events are async — use expect polling on `data-theme`, not fixed sleeps.
- **ss/lsof availability**: prefer a method present in the dev environment (WSL2); fall back gracefully with a clear message if the tool is missing (but do NOT silently pass).

## Files Affected

- `the_one/interfaces/web/static/js/theme.js`; new/extended `tests/browser/test_theme_*.py`; `tests/test_ui_guards.py` + helpers; `Makefile` (verify-serving); `tokens-section.js`; `the_one/agents.md`; `docs/ui-testid-registry.md` (if new testids)

---

## Citation Audit

theme.js:90-102 behavior and the no-listener fact verified by the F2 architect review (2026-07-03); verify-serving mechanism verified live during the F2 L1 anomaly (200s from foreign process); tokens-section.js state per 2a's flight-log entry (same day).

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Check off this leg (`theme-sync-guards-docs`) in flight.md
