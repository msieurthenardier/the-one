# Flight Debrief: Daily Automatic Purge

**Date**: 2026-06-06
**Flight**: [Daily Automatic Purge](flight.md)
**Status**: completed
**Duration**: 2026-06-06 (single session, agentic-workflow)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved

The flight delivered the **automated** half of Mission 13's purge capability — completing the mission's structured-flight arc (F1 setting + F2 manual purge + F3 daily sweep):

- A new `the_one/retention.py` pure sweep service: `is_purge_due`, `get_last_purge_at`, `run_purge_sweep(conn)` — enumerates agents via a `(name, retention_days)` projection, computes a per-agent cutoff, deletes each agent's sessions older than its window, advances a global `last_purge_at`, and returns `{deleted, ids, last_purge_at}`.
- `ChatSessionRepository.delete_older_than(agent, cutoff) -> list[str]` — age-filtered, id-returning sibling of F2's `delete_all_for_agent` (lexical ISO cutoff; SELECT-snapshot-then-DELETE).
- A v31 migration + `app_metadata` kv table + `AppMetadataRepository` (holds `last_purge_at`).
- A FastAPI-lifespan loop/start/shutdown-drain mirroring the M12 F05 web-session reaper, with **three-phase** `_sessions` eviction (pop under lock → `session_locks.pop` + `agent.aclose()` outside) closing the DD2a staleness gap for the automated path.
- A dual-gated `POST /api/_test/purge-sweep` dev seam for deterministic behavior-gate triggering.

Behavior gate `agent-history-auto-purge` passed **6/6** (Witnessed, batched mode; independent Validator confirmed every load-bearing assertion via its own fresh curls). Verified live on `localhost:8484`, including the connector-keyed aged sweep and cross-agent (per-window) isolation.

### Mission Criteria Advanced

- ✅ "A daily automated process removes every conversation whose last interaction predates the agent's retention window, while leaving conversations within the window intact." (now checked)
- ✅ "Purge (both manual and automated) removes entire conversations — including connector-originated ones — and never affects another agent's conversations." (F2 manual half + F3 automated half; both behavior-tested — now checked)

All four In-Flight checkpoints met. Mission 13's structured flights (1–3) are complete; only the optional Flight 4 (Alignment) remains.

## What Went Well

- **Leg specs were heavily and accurately cited.** Every Inputs section carried exact `file:line` anchors (reaper template `app.py:485–509`, upsert idiom, the drain-order spy `test_mcp_pool.py:528`) that held at implementation time. L1 and L2 each cleared design review in one cycle (citation/wording only).
- **The L3 two-cycle design review caught the single highest-value defect of the flight** — a guard-masked silent failure. The first implementation framing would have referenced `AppMetadataRepository` in `app.py` (whose import block at `:57–62` doesn't include it), `NameError`-ing inside `_purge_due` — and that error would be **swallowed by the DD6 `try/except Exception` startup guard**, leaving the daily purge **silently dead in production while every unit test passed green** (the unit tests drove `retention.run_purge_sweep` directly, never the app's `_purge_due` path). The fix (route the read through `retention.get_last_purge_at`; add a `_purge_due`-against-a-real-connection test) is the correct structural countermeasure.
- **The pure-service + app-wrapper split paid off.** `retention.py` (DB logic returning ids, no FastAPI) is unit-testable in isolation (`test_retention.py`, 9 tests); the `_sessions` eviction lives in the app-layer wrapper (`test_chat_history_purge.py`, 5 tests). Cleaner than F2's inline-in-app purge.
- **The three-phase eviction upgrade.** The flight body said "two-phase" (an incomplete reading of the reaper, which is itself three-phase); leg design upgraded it to include `await agent.aclose()` outside the lock — without which evicting a warm session would leak its Agent's MCP subprocesses / connector sockets.
- **Flight Director recovered a real state discrepancy cleanly.** F2 (PR #100) was still open at flight start — `main` lacked F2's `delete_all_for_agent` that F3 builds on. Surfaced to the operator, who chose to merge F2 first; branched off the updated main. (The spec's "Flight 2 … landed **and merged**" prerequisite was optimistic — "landed" ≠ "merged.")
- **The behavior gate's independent Validator earned its keep.** It re-curled the GET endpoints itself and fired its own third sweep to confirm idempotency — verifying every survivor/victim by id rather than trusting the Executor's report.

## What Could Be Improved

### Process

- **Flight-doc vs leg-doc drift went un-reconciled.** Two design decisions were silently superseded by leg-level corrections and implementation reality but never back-propagated into `flight.md`: DD2 still reads "SELECT-then-DELETE **in one transaction** … no concurrent writer can slip between them" (factually wrong — the bare SELECT is outside any transaction; the real safety is *serial connection + monotonic `updated_at`*, as the L2 leg corrected), and DD5 claims step 7 reads the "**unchanged** `last_purge_at`" observable (wrong — the always-force endpoint advances `last_purge_at` every run; the gate correctly fell back to asserting `deleted: 0`). A future reader of the flight doc alone would re-derive the wrong guarantees. **An errata block has been added to `flight.md`'s Design Decisions pointing here.** Recommend a standing debrief practice: back-propagate leg-design corrections into the flight DDs (or an explicit errata) before marking completed.
- **The restart-catch-up (Variant A) was authored but not run live.** The catch-up *logic* is unit-tested (`test_purge_loop_catch_up_sweeps_due_db` drives a real loop task against a real DB) and the lifespan integration was confirmed by inspecting container logs at Leg 4 — but no automated assertion proves the loop runs the catch-up during real uvicorn startup. Thin gap; named for honesty.

### Technical

- **The pre-existing `repositories` import cycle is now load-bearing debt.** `the_one.db.repositories` is not cold-importable standalone (`repositories → agent.config → agent → mcp → _pool → repositories`; verified failing on `main` too). `retention.py` works around it with function-local repo imports (`retention.py:20–26,43,52`), and `app.py` must keep `import the_one.retention` before `from the_one.agent import Agent`. The workaround is well-documented but spreads the trap to every future pure-service module. **Route the cycle fix to the end-of-mission maintenance flight.**
- **`_purge_due` and `_run_purge_sweep_and_evict` each acquire `get_connection()` separately** (`app.py:605,614`). Benign (cached singleton, single-task loop), but the due-check→sweep is a read-then-act with a re-acquire between; a one-line note suffices, no fix needed.
- **The endpoint's gated-ON 200 happy path has no unit test** — only the two 403 (gate-off) paths are unit-tested; the 200 contract is verified *only* by the live behavior gate. Cheap insurance: a `dev_mode=True` + env-set 200 unit test.

### Documentation

- Three reusable patterns are documented only at their code sites / in this flight's DDs and deserve a short project design note: (1) the pure-service/app-wrapper split for background sweeps, (2) the dual-gated `/_test/` seam, (3) the SELECT-snapshot + monotonic-column **superset-safety** invariant for id-returning age-deletes.

## Test Metrics

**Unit suite** (`pytest -m "not browser and not live and not pixel"`):

| Flight | Passed | Skipped | Deselected | Wall (s) |
|--------|--------|---------|------------|----------|
| M12 F01 (dep-bump) | 2935 | 4 | 538 | 289.5 |
| M13 F01 (retention-setting) | 2957 | 4 | 544 | 293.4 |
| M13 F02 (purge-now) | 2964 | 9 | 540 | 286.0 |
| **M13 F03 (daily-purge)** | **2990** | **9** | **540** | **298.85** |

**+26 passed vs F2** (2964 → 2990) — exactly the 26 new L1–L3 tests (6 + 6 + 14). Skip count stable at 9. Wall 298.85s (+12.85s vs F2, ~+4.5%) — at the edge of but consistent with the historical ±25s band, partly the 26 added tests; **not a regression**.

**Browser suite** (`pytest tests/browser -m browser`): **478 passed, 35 skipped, 12 deselected, 563.18s** — **identical pass count to the F2 baseline (478), zero regression** (expected: no browser-facing changes). Wall 563s vs F2's 570s, within noise.

**Recurring warning — now overdue:** the `aiosqlite` "Event loop is closed" teardown warning (`test_db_migration.py::TestSchemaV17`) — present in **every debrief since F11**, re-flagged in F1 and F2, has now survived **three** Mission-13 flights untouched. Promote from recurring footnote to a **named scope item** in the end-of-mission maintenance flight.

**Browser-suite environment note:** recreating the container to load the new lifespan wiring wiped the runtime-installed Playwright chromium (the `/root/.cache/ms-playwright` cache does not persist across recreate — documented in the Makefile `_ensure-playwright` target). First two browser runs mass-errored (474 errors — chromium-not-installed, then chromium-crash-on-launch). Restored via `playwright install chromium` **and** `install-deps chromium` (`make rebuild-browsers` does both); re-run matched the F2 baseline exactly. Not a code issue.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `retention.py` repo imports deferred to function scope | Pre-existing `repositories→agent→mcp→repositories` import cycle would crash startup at module level | No — it's a workaround; **fix the cycle** in maintenance |
| Eviction upgraded flight's "two-phase" → reaper's full **three-phase** (`+agent.aclose()`) | Flight body under-read the reaper template; warm-session resource leak without `aclose()` | Yes — three-phase is the correct reaper-eviction shape |
| DD2 "in one transaction" atomicity claim softened to "serial connection + monotonic `updated_at`" | Original correctness argument was wrong (bare SELECT is un-transactioned); the monotonic-superset invariant is the real guarantee | Yes — document the superset-safety pattern |
| Reviewer run at **Sonnet**, not crew-default Haiku | Concurrency/lifespan diff is the highest-risk surface; methodology forbids only Opus for the Reviewer | Situational — escalate model for concurrency-heavy diffs |
| F2 (PR #100) merged at flight start before branching | F3 depends on F2's `delete_all_for_agent`; F2 was landed but not merged | n/a — remediation, operator-approved |

## Key Learnings

1. **Guard-masked failures are this mission's recurring highest-value review catch.** F1 used `assert CURRENT_VERSION == 29`-style pins; F3's catch was a `NameError` that the DD6 `except Exception` would have converted into a silently-dead feature with green tests. The durable countermeasure shipped here — a test that drives the guarded path (`_purge_due`) through a *real connection*, not just the inner pure function — is worth standardizing project-wide.
2. **The behavior gate's unique value is live composition the unit tests structurally cannot reach** — the connector active-session surviving via the *real* `update_last_inbound` bump (vs the unit tests' recent-`updated_at` proxy), driven through real HTTP against a running lifespan.
3. **A landed flight doc can carry superseded reasoning.** Two DDs were corrected at leg/impl altitude but the flight doc was never reconciled. The standalone flight doc is a reference others read; drift in its correctness arguments is a real trap.
4. **"Landed" ≠ "merged."** Prerequisites that assert an upstream flight is "merged to main" should be verified against git state, not flight lifecycle state.

## Recommendations

1. **Route the `repositories` import cycle to the end-of-mission maintenance flight.** It's now load-bearing for two modules' import ordering; every future pure-service module inherits the deferred-import workaround. Likely fix: stop `agent.config` from transitively pulling `repositories`.
2. **Standardize "test the path behind the catch-all guard directly."** Any code under a broad `except Exception` (especially lifespan/background loops) needs a test that drives it through the guarded wrapper — green unit tests on the inner service prove nothing about the swallowed path.
3. **Add the `aiosqlite` teardown warning as named maintenance-flight scope** (three flights overdue) — a `filterwarnings` entry or a real fix.
4. **Add a gated-ON 200 unit test for `/_test/purge-sweep`** so the endpoint's success contract isn't behavior-gate-only.
5. **Adopt errata back-propagation in the debrief workflow** — reconcile leg/impl corrections into the flight DDs (or an explicit errata block) before marking a flight completed. (Done here for DD2/DD5.)

## Methodology Feedback (mission-control skills)

- **Flight skill**: (a) prerequisites that reference an upstream flight should phrase the git dependency precisely — "F2 merged to `main`" is a git fact to verify, distinct from "F2 landed." (b) Consider a debrief step that back-propagates leg-design corrections into the flight's Design Decisions so the standalone flight doc doesn't carry superseded reasoning (DD2/DD5 here).
- **Leg skill**: the heavy `file:line` citation discipline worked well and the design-review caught a guard-masked silent failure — worth reinforcing that legs touching code behind a catch-all guard explicitly require a test through the guarded entry point.
- **agentic-workflow**: the Flight Director's F2-merge remediation (surface the discrepancy, get an operator decision, branch off updated main) and the Reviewer-model escalation (Haiku→Sonnet for the concurrency surface) both worked — worth codifying "escalate the Reviewer model for concurrency/lifespan-heavy diffs" as explicit guidance.

## Action Items

- [ ] End-of-mission maintenance flight: **fix the `repositories` import cycle**; the **`aiosqlite` teardown warning**; the still-open F2 items (`extractApiError`→`App.extractApiError` + `handlePurgeHistory` + `e.detail||fallback` audit; the `agents.md` `Field(ge/le)`+same-leg-migration convention doc).
- [ ] Add a gated-ON 200 unit test for `/_test/purge-sweep`.
- [ ] Write a short project design note for the three reusable patterns (pure-service/app-wrapper split; dual-gated `/_test/` seam; SELECT-snapshot superset-safety invariant).
- [ ] **Known Issue stays OPEN**: the manual-half DD2a staleness (F2's HTTP `DELETE` endpoint still does not evict `_sessions`) — F3 closed only the automated half. Already annotated in the mission Known Issues; carry to Flight 4 / maintenance.
- [ ] (Optional) Add an automated assertion for the lifespan startup catch-up (Variant A) if a future flight touches the loop.
