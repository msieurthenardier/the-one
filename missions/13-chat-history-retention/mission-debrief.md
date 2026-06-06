# Mission Debrief: Chat History Retention

**Date**: 2026-06-06
**Mission**: [Chat History Retention](mission.md)
**Status**: completed
**Duration**: 2026-06-05 – 2026-06-06 (pulled off backlog and executed across two days)
**Flights Completed**: 3 of 3 structured (Flight 4 *Alignment* optional — declined)

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| 1. Per-agent retention setting (1–365, default 30) in General-tab Behavior section, above Max Iterations | **Met** | F1: `Field(ge=1, le=365, default=30)` (`agent/config.py:266`), General-tab number input; placement verified by browser `compareDocumentPosition` test + live instance |
| 2. Value persists across save/reload; out-of-range **rejected** (not clamped) | **Met** | F1: v30 migration + `save()`/`_row_to_config` round-trip; declarative `Field` → 422; raw-value-preserving `collectFormData` (DD6). Rendered reload + visible-error UX confirmed by the F2 entry-gate behavior test (6/6) — which caught a real `[object Object]` rendering defect |
| 3. "Purge now" deletes all of an agent's conversations, only after explicit confirm | **Met** | F2: `delete_all_for_agent` + `DELETE /agents/{name}/chat/sessions` + Danger-Zone two-step confirm; behavior-tested 5/6 (1 inconclusive spec-gap, 0 fail) |
| 4. Daily automated process removes conversations past the agent's window, leaves newer intact | **Met** | F3: due-based catch-up lifespan sweep; behavior-tested 6/6 |
| 5. Purge (manual + automated) removes whole conversations incl. connector-originated; never cross-agent | **Met** | F2 manual half + F3 automated half; both behavior-tested. F3 confirmed aged interactive AND superseded-connector swept; recent/active-connector/other-agent kept |

### Overall Outcome

**Fully achieved.** Each agent now forgets old conversations automatically: an operator sets a per-agent retention window (1–365 days, default 30), can wipe an agent's history on demand with a confirm step, and a daily background sweep prunes conversations past each agent's window — interactive and connector-originated alike — without manual intervention and without cross-agent bleed. The mission's stated outcome ("old conversations no longer accumulate indefinitely; operators control how long an agent's chat memory persists") is delivered end to end.

The outcome remained the right goal throughout — no mid-mission pivot. All three resolved Open Questions (storage shape, daily-cadence trigger, treatment of pre-existing history) held up in implementation exactly as planned at mission scope.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| F1 Retention Setting | completed | `chat_history_retention_days` field + v30 migration + General-tab input; atomic-leg discipline; behavior-test acceptance deferred (no SendMessage), closed as F2's entry gate |
| F2 Purge Now | completed | Agent-wide `delete_all_for_agent` + DELETE endpoint + Danger-Zone confirm button; entry gate caught a pre-existing F1 `[object Object]` error-rendering defect and fixed it (`extractApiError`) |
| F3 Daily Automatic Purge | completed | Pure `retention.py` sweep + due-based catch-up lifespan loop + `_sessions` eviction + dual-gated test seam; behavior gate 6/6; no regression |
| F4 Alignment *(optional)* | not run | Declined — UX was acceptable as built; no hands-on polish pass needed (operator decision, this debrief) |

### Flight Patterns

All three flights went smoothly and landed in single sessions. The common thread behind the smoothness: **per-leg design review caught the highest-value defects before any code shipped** — and notably, the same defect *class* recurred across flights and was caught each time:

- **Guard-masked / silent-false-green failures** were the mission's signature near-miss. F1: two literal `assert CURRENT_VERSION == 29` pins the v30 bump would break, plus the discovery that a bare `pytest tests/browser/...` runs **zero** tests (a silent false-green). F3: a `NameError` in `_purge_due` that the lifespan `try/except Exception` startup guard would have swallowed into a **silently-dead daily purge with all tests passing green**. Each was caught at design-review altitude, not in production.
- **Behavior gates earned their keep at the seam unit tests can't reach.** F2's entry gate (re-running F1's deferred test) surfaced a real user-facing `[object Object]` defect that 233 F1 automated tests missed. F3's gate verified the connector active-session surviving via the *real* `update_last_inbound` bump, not a unit-test proxy.

No flight struggled. The one cross-flight friction was environmental, not design: the running container's Playwright/Chromium setup drifted twice (F1 missing `.so` libs; F3's `--force-recreate` wiped the chromium cache) — each cost mid-flight recovery time but no rework.

## Process Analysis

### Planning Effectiveness

The initial three-flight breakdown (setting → manual purge → daily purge) was **accurate end to end** — zero flights added, removed, or resequenced. The mission's backlog re-validation (re-checking every dependency surface against post-M12 `main` before starting) paid off: every cited `file:line` target held, and the three flights' carry-forward action items (F1→F2's `delete_all_for_agent` design, F1→F3's `last_purge_at`/reaper-shape guidance) landed almost verbatim. This is the strongest planning-accuracy result in recent missions.

### Execution Patterns

The agentic-orchestration cadence — **per-leg design review + batched implementation + a single flight-level code review** — worked well and was rated "about right" by the operator for oversight. The Flight Director's discipline of *independently re-verifying* design-review findings (rather than trusting them) is what converted "approve with changes" into landed-correct in one or two cycles.

A candid signal from the human interview: **no single human decision felt load-bearing** — the operator's choices "mostly confirmed the recommended/obvious option." This is primarily a credit to spec/recommendation quality (the options presented were well-scoped with a clear default), and the operator still valued the gates as a safety net. But it's worth recording honestly: in this mission the human-in-the-loop functioned as *oversight/veto*, not *direction*. For a low-ambiguity, well-precedented feature like retention, that's the appropriate equilibrium; the gates are cheap insurance, not a decision forum.

### Methodology Assessment

The mission/flight/leg hierarchy fit this work cleanly — three flights of 2–4 legs each, each flight a coherent vertical increment. Briefings/debriefs were valuable: the per-flight debriefs' carry-forward action items directly shaped the next flight's design, making the debrief loop load-bearing rather than ceremonial.

## Lessons Learned

**Technical:**
- **The vertical slice is coherent and the architecture improved.** Retention spans schema → repo → service → lifespan → API → UI, and F3 *raised* structural quality by introducing the pure-service + app-wrapper split rather than extending F2's inline-in-endpoint approach. The migration idiom (v30, v31) and the name-keyed delete reasoning (F2 → F3) were applied identically across flights — genuine house conventions, not one-offs.
- **A latent defect can become load-bearing without being created.** Mission 13 didn't introduce the `repositories` import cycle (`repositories → agent.config → agent → mcp → _pool → repositories`, fails cold-import on `main` too) — but F3's `retention.py` made it load-bearing, working around it with function-local imports and an `app.py` import-ordering constraint. This is the mission's one piece of real structural debt.
- **A landed flight doc can carry superseded reasoning.** F3's DD2 ("in one transaction") and DD5 ("unchanged `last_purge_at`") were corrected at leg/impl altitude but not back-propagated; an errata block now reconciles them. The correctness-bearing insight — the SELECT-snapshot + **monotonic-`updated_at` superset-safety** invariant — currently lives only in a docstring and deserves a design note.

**Process:**
- **Test the path *behind* the catch-all guard, not just the inner function.** The F3 `NameError` would have been swallowed by a resilience guard into a silently-dead feature with green tests. The durable countermeasure (a `_purge_due` test through the guarded wrapper against a real connection) should be a stated project rule.
- **"Landed" ≠ "merged."** F3 started against a `main` lacking F2's merged work (PR #100 still open); the Flight Director caught and remediated it. Prerequisites asserting an upstream dependency is merged must verify git state.
- **Behavior-test execution has a *tooling* prerequisite (SendMessage continuation) distinct from its environmental ones.** F1 discovered this at the acceptance gate and deferred; F2/F3 ran in accepted **batched-Witnessed** mode (formalized this mission as a standard mode for non-branching specs).

**Domain:**
- "Last interaction" = the engaged-turn `updated_at`, not creation time; the active connector session survives purge *for free* because its `updated_at` is bumped, while superseded channel rows age out — the mission's intended consequence, confirmed live.

## Reusable Patterns (worth documenting as project conventions)

The mission established five patterns; three are subtle enough to deserve a short project design note so the next author inherits rather than re-derives them:
1. **Pure-service + app-layer-wrapper split** for background work that touches both the DB and in-memory registries (F3 `retention.py` + `app.py` wrapper) — keeps DB logic unit-testable without FastAPI.
2. **Dual-gated `/_test/` seam** (`dev_mode` AND env flag, gate-first 403) for behavior-test triggers production must never expose.
3. **SELECT-snapshot + monotonic-column superset-safety invariant** for id-returning age-filtered deletes — the genuinely subtle one (correctness rests on `updated_at` only moving forward).

Plus two already-established-but-undocumented conventions: the **atomic-leg same-leg-migration** discipline (now v30 + v31, two precedents) and the **lifespan loop/start/drain triad** (now 2 instances — F05 reaper + F3 purge — crossed from precedent into template-worthy).

## Methodology Feedback (Flight Control / mission-control skills)

- **`/flight`**: (a) phrase upstream-dependency prerequisites as verifiable git facts ("F2 merged to `main`"), distinct from flight lifecycle state ("landed"); (b) add a debrief step that back-propagates leg/impl corrections into the flight's Design Decisions (or an errata block) before a flight is marked completed — F3 needed this for DD2/DD5.
- **`/leg`**: legs touching code behind a catch-all `except` should explicitly require a test through the guarded entry point — the guard converts an obvious crash into a silent no-op.
- **`/agentic-workflow`**: the Flight Director's two judgment calls that worked — escalating the Reviewer model (Haiku→Sonnet) for the concurrency/lifespan diff, and the F2-merge remediation (surface → operator decision → branch off updated main) — are worth codifying as explicit guidance.
- **behavior-test**: batched-Witnessed (one Executor, one independent Validator that takes its own observations) was the de facto mode for all three gates and worked well for non-branching specs; the operator-rated oversight balance suggests it's the right default when SendMessage is unavailable.
- **Meta**: the human interview revealed decisions that were confirmatory rather than directional. Not a problem here (low-ambiguity feature), but a signal that for well-precedented work the gates can be lighter-touch; the value was veto-availability, not active steering.

## Action Items

These roll into the **end-of-mission maintenance flight** (scaffold via `/routine-maintenance`):

- [ ] **Fix the `repositories` import cycle** (the one structural debt; likely stop `agent.config` transitively pulling `repositories`) — removes the deferred-import trap for future pure-service modules.
- [ ] **Resolve the recurring `aiosqlite` "Event loop is closed" teardown warning** (`test_db_migration.py::TestSchemaV17`) — open since F11, untouched through all three M13 flights; a `filterwarnings` entry or a real fix.
- [ ] **Carried-forward F2 frontend debt**: promote `extractApiError` → `App.extractApiError`, fix `handlePurgeHistory`, and sweep the residual `e.detail || fallback` idiom (still live in `provider-models.js`, `provider-editor.js`, `mcp-server-editor.js`, `system-page.js`).
- [ ] **Manual-half DD2a `_sessions` staleness** (Known Issue, still open): F3 closed only the automated half; decide whether to retrofit eviction (or a `session_list` invalidation broadcast) onto F2's HTTP `DELETE` endpoint.
- [ ] **Document conventions** in `the_one/agents.md` / a design note: `Field(ge/le)` bounded-int + same-leg migration; the three reusable patterns above.
- [ ] **Add a gated-ON 200 unit test** for `POST /_test/purge-sweep` (success contract is currently behavior-gate-only).
- [ ] **(Optional, scale-only)** Note the per-agent N+1 sweep enumeration and the single global `last_purge_at` cadence as edges to revisit if agent counts grow or per-agent retention becomes time-sensitive.

**Not blocking mission completion** — all are debt/hardening, not outcome gaps. **PR #101 (Flight 3) remains to be merged to `main`.**
