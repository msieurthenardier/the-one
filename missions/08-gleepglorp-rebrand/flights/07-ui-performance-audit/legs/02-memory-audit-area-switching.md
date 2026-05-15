# Leg: memory-audit-area-switching

**Status**: completed
**Flight**: [UI Performance Audit](../flight.md)

## Objective

Investigate the L01-surfaced retention growth (+30.88% heap across 150 area-switches; exceeds 20% budget) and produce a retainer-delta report identifying the specific leak roots in the codebase. Investigative leg — no fixes. The fixes land in L03, conditional on what L02 finds. Developer ships a code-reading-based hypothesis list (likely leak sources with file:line citations); Flight Director runs the MCP heap-diff to validate which hypotheses are real.

## Context

- **L01 finding**: +30.88% heap growth across 150 area-switches; p50/p95 area-switch.full both sub-millisecond. The latency is fine; the retention is the issue.
- **Area lifecycle invariant** (verified in L01 recon): `app.js:99` only calls `init()` once per area; subsequent cross-area switches toggle `.active` classes and call `deactivate()` on the outgoing area. So the leak surface is NOT "init runs N times and stacks closures" — it's something WITHIN the once-per-area init that holds references across deactivate→activate boundaries OR something WS-related that accumulates per session-join.
- **Recon (F7 flight-log row #18)**: all three areas have effectively-empty `deactivate()` impls. chat keeps WS alive intentionally; studio + admin do nothing. None release listeners, timers, or DOM references.
- **L01 instrumentation**: `App.perf` is in place — measures + heap snapshots available via `mcp__chrome-devtools__evaluate_script(function='() => App.perf.dump()')`.
- **Methodology** (mission spec): DevTools heap snapshots + allocation timeline. Chrome DevTools MCP exposes `take_memory_snapshot` (operator-side); for finer-grained retainer analysis, MCP can `evaluate_script` running `performance.memory` repeatedly during the cycle.

## Hypothesis surface (Developer-deliverable)

Developer agent reads the following files and identifies CANDIDATE leak roots with file:line citations + reasoning, ranked by likely impact:

1. **`the_one/interfaces/web/static/js/areas/chat.js`** — `init()` body (lines 27-944) creates many closures and event listeners. Likely candidates:
   - WS message handler attachment — does the WS object live across deactivate? Is the `addEventListener('message', ...)` ever cleaned up?
   - DOM listener registrations on `welcomeListEl`, `inputEl`, `sendBtn`, `agentSelect`, `headerNewBtn` — these survive deactivate because the DOM elements are kept (panels just toggle `.active`)
   - The `traceShells` registry (`chat.js:417`) — grows per session-join's parent_message_id; does it shrink?
   - `inFlightSessions`, `sessions`, `sourceNames`, `oauthPopups` — closure-scoped objects that accumulate per session

2. **`the_one/interfaces/web/static/js/areas/studio.js`** — `init()` body and `deactivate()` empty. Look for:
   - `modelCapsBy`, `modelCtxBy` (F6.5 L04) dicts — reset per fetchModelsForProvider but never released on area switch
   - The agent-list rendering — does each render attach new listeners without removing old ones?
   - `_modelsFetchController` (AbortController) — does it leak Promise references?

3. **`the_one/interfaces/web/static/js/areas/admin.js`** — `init()` body and `deactivate()` empty. Look for:
   - Provider-grid render — listener leaks per row
   - The Test-connection button handler chains

4. **`the_one/interfaces/web/static/js/app.js`** — `performCrossAreaSwitch` and panel mount logic. Look for:
   - Sidebar/content panel DOM nodes — once created, do they ever get removed? Or just toggle `.active`? (Toggle `.active` is fine; full DOM remove would be unusual.)

5. **Hash-routing**: 150 hashchanges may each trigger a small allocation that compounds. Look at `app.js:67-77` (hashchange handler) — any cached objects per hash?

6. **Detached DOM nodes** (cycle-1 reviewer): the classic SPA leak — DOM nodes that get replaced via `innerHTML = ''` or `element.removeChild(...)` but are still referenced by closure-scoped variables (`messagesEl.children` snapshots, cached node-list refs). Look for closures that capture a `querySelector` result and outlive the DOM node's tenure.

7. **Perf-instrumentation buffers themselves** (cycle-1 reviewer): `performance.mark`/`performance.measure` entries accumulate in the browser's internal buffer indefinitely unless explicitly cleared. L01's instrumentation fires hundreds of marks per scenario. If the operator never calls `App.perf.reset()`, the buffer grows unbounded. Verify: do any scenarios in agents.md skip `reset()`? Does any production code path leave perf marks accumulating? (The gate prevents production from emitting marks at all, so this is HAT-scope-only — but worth noting.)

Developer ships a **Retainer-Hypothesis Report** as a NEW section in the flight log:

```markdown
## L02 Retainer-Hypothesis Report

| Rank | Source | File:Line | Reasoning | Expected fix area | Heap-diff verification status (FD) |
|---|---|---|---|---|---|
| H1 | chat WS message handler | chat.js:NNN | Each session-join adds a handler that's never removed | Add cleanup in WS-close path | TBD |
| H2 | chat traceShells registry | chat.js:417 | Per-message-id keys never released on session change | Clear traceShells on session_left | TBD |
| ... | ... | ... | ... | ... | ... |
```

Flight Director then runs MCP heap-diff (separate post-Developer step) and fills the "verification status" column with `confirmed | not-confirmed | needs-deeper-investigation` per hypothesis.

## Inputs

Files that exist before this leg runs:
- L01 outputs: `the_one/interfaces/web/static/js/perf.js` + `agents.md` Performance Measurement section
- `the_one/interfaces/web/static/js/areas/chat.js` — primary suspect (largest init body)
- `the_one/interfaces/web/static/js/areas/studio.js` — secondary suspect
- `the_one/interfaces/web/static/js/areas/admin.js` — tertiary suspect
- `the_one/interfaces/web/static/js/app.js` — area-lifecycle orchestrator
- L01-landed flight log with the +30.88% heap-delta finding

State that must be true:
- L01 landed; perf instrumentation in place; broad pytest 1669p/4s/374d unchanged
- Chrome DevTools MCP connected (used by FD for heap-diff validation, not by Developer)

## Outputs

Files modified:
- `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-log.md` — append `## L02 Retainer-Hypothesis Report` section with the candidate-leak table above

No code changes in L02. (Fixes go to L03.)

State after:
- A code-reading-derived hypothesis list of likely leak roots, file:line cited
- L03 has a prioritized fix target list (subject to FD's MCP heap-diff validation)

## Acceptance Criteria

- [ ] **[Developer]** Read chat.js, studio.js, admin.js, app.js in their entirety. For each, identify candidate leak roots with file:line citations.
- [ ] **[Developer]** Append `## L02 Retainer-Hypothesis Report` to the flight log with **5+ ranked hypotheses (H1-H5+); low-confidence candidates EXPLICITLY flagged so quantity-over-quality padding doesn't dilute the FD's worklist** (cycle-1 reviewer). Each hypothesis carries a `tier` field: `statically-confirmed` (e.g., grep shows zero `removeEventListener` for this handler) OR `requires-heap-diff` (needs FD's MCP run to validate). The FD prioritizes `statically-confirmed` for L03 since those are unambiguous.
- [ ] **[Developer]** Each hypothesis row includes: source file, line range OR symbol name, reasoning (1-2 sentences), and expected fix-area (specific function/line in the same file or another file).
- [ ] **[Developer]** Hypothesis ranking is by likely impact (H1 = most likely to be the +30.88% culprit, descending).
- [ ] **[Flight Director, post-Developer]** Run MCP heap-diff between pre-cycle and post-cycle snapshots; identify the dominant retainer-growth nodes via the Chrome DevTools Comparison view (or direct heap-snapshot data). Fill the verification-status column with `confirmed | not-confirmed | needs-deeper-investigation` per hypothesis.
- [ ] **[Flight Director]** Append a "verified leak roots" summary at the end of the report — ranked list of CONFIRMED leak roots that L03 will fix.
- [ ] No code changes. `git diff --stat the_one/` returns empty after this leg.
- [ ] Broad pytest exits 0; pass count unchanged from L01-landed 1669.

## Verification Steps

- **Hypothesis report exists**: `grep "L02 Retainer-Hypothesis" missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-log.md` returns the section header.
- **At least 5 hypotheses**: the report table has at least 5 rows.
- **Cite-only**: `git diff --stat the_one/` (i.e. only flight-log.md changed, no source-code changes).
- **Broad pytest preserved**: `docker exec the-one pytest -x --timeout 30` exits 0 with 1669p/4s/374d.

## Implementation Guidance

1. **Read each suspect file completely** — chat.js, studio.js, admin.js, app.js. Note every `addEventListener` call, every closure-scoped Object/Array that grows, every WebSocket handler attachment, every interval/timer. **Then grep for negative evidence** (cycle-1 reviewer): for each `addEventListener` callsite, grep for a matching `removeEventListener`. Absence = `statically-confirmed` leak candidate. Same pattern for `ws.addEventListener('message', ...)` vs cleanup-in-close-path. This grep-pass produces the "confidence tier" data the hypothesis report needs.

2. **For chat.js specifically**, look at:
   - `init()` body around lines 27-944 — the bulk of the closure state
   - Look for `ws.addEventListener('message', ...)` or `ws.onmessage = ...` — how is the WS reconnect path handled? Are old handlers detached?
   - The `traceShells` registry — `delete traceShells[key]` calls in `clearLoginRequiredButton` (chat.js:380-389) handle ONE path but not session-change
   - `oauthPopups` — `delete oauthPopups[sourceId]` in clearLoginRequiredButton handles cleanup
   - `sourceNames` — set in renderLoginRequiredButton but never cleared

3. **For studio.js specifically**:
   - `modelCapsBy`, `modelCtxBy` — F6.5 L04 dicts, reset per-fetch (good)
   - Agent-list rendering — does each render attach NEW listeners to NEW DOM nodes (good — old DOM is GC'd) or to long-lived containers (bad — listeners stack)?
   - `_modelsFetchController` — AbortController per fetch; old ones discarded (good)

4. **For admin.js specifically**:
   - Empty `deactivate()` — same pattern as studio
   - Provider-grid render — listener registration pattern

5. **For app.js**:
   - `performCrossAreaSwitch` — toggles `.active` classes; doesn't create/destroy DOM. So per-call allocation is minimal.
   - hashchange handler — any closure that captures large objects?

6. **Write the hypothesis table** into flight-log.md.

7. **STOP** — do NOT attempt to validate via heap-diff (Developer agents have no MCP access). The Flight Director runs the validation pass after Developer lands.

8. **Do NOT commit** — Flight Director batches commits after L05.

## Edge Cases

- **Some hypothesized leaks may turn out to be GC-traceable**: Chrome's heap diff may show a 500KB growth in `(string)` retainer that has no clear code-location ownership — this happens when the leak is "many small objects" rather than "one large object." The Developer notes such cases as needs-deeper-investigation in the report.
- **The +30.88% may be partly normal warm-up retention**: V8 JIT inlining, framework lazy-init, etc. The Developer's hypothesis should attempt to distinguish "Chrome's natural warm-up" from "our code retaining references." The FD's MCP validation will confirm or refute.
- **The 50-loop scenario may exercise different code paths than a real long session**: e.g., it doesn't open OAuth popups, doesn't render markdown, doesn't trigger many DOM mutations. The hypothesis report should note that L01's scenario captures area-switch-specific leaks specifically — other leak surfaces (message rendering, OAuth popups, MCP tool calls) need separate scenarios in HAT.
- **`traceShells` survives session-change**: a user switching between two chat sessions will accumulate trace shells from both. The L03 fix would `Object.create(null)`-reset `traceShells` on `session_joined` or `session_left`.

## Files Affected

- `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-log.md` — append `## L02 Retainer-Hypothesis Report` section

---

## Post-Completion Checklist

**Complete ALL steps before marking the leg landed:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (broad pytest 1669p/4s/374d preserved; no code changes so nothing should regress)
- [ ] Update flight-log.md with leg progress entry + the hypothesis report
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet — that happens during the post-L05 commit batch
- [ ] Do NOT commit — Flight Director batches commits after L05

---

## Citation Audit

4 source-code citations verified against current code at leg design time:
- `the_one/interfaces/web/static/js/app.js:99` (init-once invariant) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:417` (traceShells registry) — OK
- `the_one/interfaces/web/static/js/areas/chat.js:380-389` (empty-trace-shell cleanup) — OK
- L01 flight-log entry for +30.88% finding — OK (cited as the seed for this leg's investigation)
