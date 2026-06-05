# Flight Log: Purge Now

**Flight**: [Purge Now](flight.md)

## Summary

In flight under `/agentic-workflow` on branch `flight/02-purge-now`. Two autonomous legs
(`agent-purge-backend`, `purge-now-button`) plus two behavior-test acceptance gates
(`agent-purge-now-clears-history` new; `agent-retention-setting-roundtrip` F1-deferred entry gate).

---

### Flight Director Notes

- **2026-06-05 — Context loaded, flight started.** Read mission 13, flight 02 spec, flight log,
  ARTIFACTS.md, and the `leg-execution.md` crew file (well-formed: Crew / Interaction Protocol /
  Prompts all present). F1 confirmed merged to `main` (PR #99) — Leg-1 prerequisite satisfied.
- **Branch:** created `flight/02-purge-now` off `main`. The flight-02 planning artifacts and the
  `agent-purge-now-clears-history.md` spec were untracked on `main`; they ride onto this branch and
  will be committed at flight-review time.
- **Status transition:** flight was `planning`, not `ready`, when invoked — but every Pre-Flight
  checklist item is checked (questions resolved, DDs documented, prerequisites verified, validation
  approach defined, legs defined). Treated as effectively `ready` and transitioned to `in-flight`.
- **Crew/model plan:** Developer = Sonnet (design review + implement + fix + commit), Reviewer =
  Haiku (single end-of-flight review over all uncommitted changes). Leg 2 touches UI, so an
  Accessibility Reviewer (Sonnet) will run in parallel at flight review — especially relevant given
  the bundled `system_prompt` a11y label (DD6).
- **Behavior-test gates:** both require a live rebuilt instance on `localhost:8484` + Chrome MCP +
  the `mock` provider + curl. Per the flight's prerequisite, this session is continuation-capable
  (SendMessage available), so `/behavior-test` runs the full Witnessed crew rather than degrading to
  re-spawn-per-step. Environment readiness probed before running the gates, after both legs land.
- **2026-06-05 — Behavior gates run (operator chose "run both gates now").** Live instance on
  `:8484` confirmed reflecting F2 (new endpoint responding `{deleted:0}`; static JS bind-mounted).
  **Correction to the note above:** this session in fact lacked the SendMessage continuation tool
  (the same gap that deferred the F1 gate). Rather than defer again, ran both gates in **batched
  Witnessed mode** — a single Executor drives the full step flow with per-step evidence, then an
  independent Validator (a different agent — the actor never judges) renders per-step verdicts and
  takes its own fresh observations. Both on Sonnet (Validator never Opus). Used throwaway agents
  (`bt-*-13f2`) so no real chat history was touched.
  - **Gate `agent-purge-now-clears-history` (F2's own gate): PASS** (5 pass / 1 inconclusive, 0 fail;
    run `2026-06-05-20-16-35`). Confirm-gate holds (first click arms only, count stays 2), the
    confirming click sweeps both the interactive AND the connector-keyed session to 0, the bystander
    stays at 1 (cross-agent isolation), and a clean reload shows the Chat surface history-gone. The
    inconclusive is a list-endpoint observability gap (summary projection omits connector fields), not
    a behavior fault — the sweep is proven by 2→0 and pinned by Leg 1 unit tests.
  - **Gate `agent-retention-setting-roundtrip` (F1-deferred entry gate): FAIL→PASS.** First run
    (`2026-06-05-20-06-29`) failed Step 4: out-of-range retention saves rendered the validation error
    as `[object Object]`. Operator chose "fix it now in F2". Fixed (see Deviations) and re-ran
    (`2026-06-05-20-42-09`): **6/6 PASS**. The F1 live-acceptance gap is closed.
- **Spec maintenance:** both specs moved `draft`→`active` with Last Run stamped. The purge spec's
  Step 1 (connector-field observability) and Step 6 (it assumed a per-agent session list; the UI is a
  flat cross-agent list) were corrected to match the real measurable surface. The observed post-purge
  WS `session_list` staleness (the DD2a accepted boundary) was filed as a Mission 13 Known Issue.
- **Throwaway-agent cleanup:** the `bt-*-13f2` agents created for the gates were deleted from the live
  instance after the runs (instance left as found).

---

## Reconnaissance Report

Source items pulled in from Mission 13 Known Issues + the Flight 1 debrief action list, verified
against current `main` (post-F1 merge).

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Agent-wide delete repo method | confirmed-live | only per-session `delete(session_id)` at `repositories.py:1030`; no `WHERE agent_name=?` primitive | F2 Leg 1 |
| Agent-wide purge API endpoint | confirmed-live | only `DELETE /chat/sessions/{id}` (`api.py:3649`) + per-session `/purge` (`:3659`) | F2 Leg 1 |
| "Purge now" button + confirm | confirmed-live | Danger Zone has only Delete Agent (`general-tab.js:135`); `App.confirmDelete` (`confirm.js:38`) reusable | F2 Leg 2 |
| DD6 inline comment (shared surface) | confirmed-live | `studio.js:1930–1932` branch has no comment | F2 Leg 2 (bundled) |
| `system_prompt` a11y label (shared surface) | confirmed-live | textarea `general-tab.js:113` has no `<label for>`/`id` (WCAG 1.3.1/4.1.2) | F2 Leg 2 (bundled) |
| Run deferred `agent-retention-setting-roundtrip` | confirmed-live | spec `draft`, Last Run `never` | F2 entry-gate verification |
| `aiosqlite` teardown warning | confirmed-live but **out of surface** | pytest/test-infra (`test_db_migration.py::TestSchemaV17`); no shared surface with Purge Now | Excluded — end-of-mission maintenance flight |
| `agents.md` convention docs (Field ge/le, same-leg migration) | confirmed-live but **out of surface** | documentation, not F2 code surface | Excluded — maintenance / docs pass |

Verified mechanics: connector sessions are `chat_sessions` rows with `agent_name` set
(`connectors/_session.py:181–195`) → `DELETE WHERE agent_name=?` sweeps them; FK dropped at v5 → no
cross-agent bleed. Rename re-points `chat_sessions.agent_name` in the same transaction
(`repositories.py:219–222`) → name-keyed purge is rename-safe. Read path for "history gone" exists:
`GET /api/chat/sessions?agent_name=X` (`api.py:3597`). Seeding path exists: `POST /api/chat/sessions`
(`api.py:3624`, accepts connector fields). No migration required.

---

## Leg Progress

### Leg 01 — agent-purge-backend — `landed` (2026-06-05)

**Changes made:**
- `the_one/db/repositories.py` — added `ChatSessionRepository.delete_all_for_agent(agent_name: str) -> int`
  immediately after `delete(session_id)`. Runs `DELETE FROM chat_sessions WHERE agent_name = ?`, reads
  `cur.rowcount` inside the open-cursor `async with self.conn.execute(...) as cur:` block, commits, returns
  the count. No existence check, no 404 — idempotent (DD1).
- `the_one/interfaces/web/api.py` — added `DELETE /agents/{name}/chat/sessions`
  (`delete_agent_chat_sessions`, return type `dict[str, Any]`) returning `{"status": "ok", "deleted": N}`,
  placed with the chat-session routes (just before the per-session `/purge` route). Mirrors `_chat_repo()`
  access; no try/except/404.
- `tests/test_db_repositories.py::TestChatSessionRepository` — added 4 tests: connector+interactive sweep
  (returns 2), cross-agent isolation, empty no-op (returns 0), and rename-then-purge composition (rename
  a1→a1-renamed, purge by new name returns 2, BOTH new-name and old-name lists empty, bystander a2 intact).
- `tests/test_db_api.py::TestChatSessionAPI` — added `test_delete_agent_chat_sessions_returns_count`:
  asserts 200 + `{"status":"ok","deleted":2}` then GET-by-agent returns `[]`, AND the no-session case
  returns 200 `{"deleted":0}` without 404.

**Test results:**
- `tests/test_db_repositories.py` — 191 passed.
- `tests/test_db_api.py -k ChatSessionAPI` — 5 passed, 113 deselected.
- Broader unit suite (`-m "not browser and not live and not pixel"`) — 2964 passed, 9 skipped.
- `ruff check` + `ruff format --check` on all four touched files — clean.

**Notes:** Container bind-mounts `./the_one` and `./tests` live (per `docker-compose.yml`), so no `make
rebuild` was needed for pytest to see the edits. `rowcount` semantics on DELETE confirmed working under
aiosqlite (read before commit while cursor open).

**Deviations / anomalies:** None. The `aiosqlite` "Event loop is closed" teardown warning observed in the
broader run is the pre-existing, out-of-surface known issue already logged in this flight's Reconnaissance
Report — not introduced by this leg.

---

### Leg 02 — purge-now-button — `landed` (2026-06-05)

**Changes made:**
- `the_one/interfaces/web/static/js/areas/studio/general-tab.js` — added a "Purge now" button to the
  Danger Zone (after Delete Agent), classes `btn-muted-destructive delete-btn purge-history-btn`,
  `data-testid="purge-history-btn"`, `data-name`, with a `<span data-confirm-title>Purge now</span>` child;
  wired its click to `callbacks.onPurge` via the unique `.purge-history-btn` selector. DD6 a11y: gave the
  `system_prompt` textarea `id="studio-system-prompt"` and a `<label for="studio-system-prompt"
  class="visually-hidden">System Prompt</label>` (programmatic label association, no duplicate visible label).
- `the_one/interfaces/web/static/js/areas/studio/agent-editor.js` — forwarded `onPurge: callbacks.onPurge`
  in the `renderGeneralTab(...)` call (the load-bearing bridge) and added `onPurge` to the callbacks
  doc-comment.
- `the_one/interfaces/web/static/js/areas/studio.js` — added `handlePurgeHistory(purgeBtn)` mirroring
  `handleDeleteEditor`: two-step `App.confirmDelete(..., {confirmLabel:'Confirm Purge?'})` →
  `DELETE /api/agents/{name}/chat/sessions`, flashes the deleted count (`isError=false`), keeps the agent
  selected (no `loadAll()`/`selectAgent`/`renderEmptyEditor`); reverts + error-flashes on transport failure.
  Registered `onPurge: handlePurgeHistory` in the `renderAgentEditor` options bag. Added the DD6 inline
  comment at the `collectFormData` `chat_history_retention_days` branch (raw-value preservation; no
  `|| default`, so an out-of-range value reaches the server for a surfaced 422).
- `tests/browser/test_flow_studio_purge_now_button.py` — new `@pytest.mark.browser` test: purge button
  present in Danger Zone, text-distinct from Delete Agent, carries the `data-confirm-title` "Purge now"
  span; single click arms (label → "Confirm Purge?") without firing the DELETE.

**Test results (Flight Director re-verified after the implementing agent ended its closeout early):**
- `tests/browser/test_flow_studio_purge_now_button.py -m browser` — 2 passed.
- Full browser suite (`tests/browser -m browser`) — 477 passed, 35 skipped, 12 deselected (the 9 pre-existing
  skip files stay skipped; no regression).
- `ruff check` + `ruff format --check` on the new browser test — clean.
- JS diffs reviewed by the Flight Director against the leg spec — exact match (button classes, three-file
  callback chain, `.visually-hidden` label, DD6 comment).

**Design-review notes:** Two design-review cycles. Cycle 1 raised (a) the a11y snippet using a nonexistent
`sr-only` class — corrected to the project's real `.visually-hidden` utility; and (b) the destructive
armed-state (red) being keyed to `.delete-btn.confirm-delete`, which the purge button would miss —
resolved by giving the purge button the `delete-btn` class too (inherits resting + armed styling;
wiring stays order-safe because Delete Agent is emitted first, so `querySelector('.delete-btn')` still
resolves to it). A focused cycle-2 review confirmed both fixes and found no new issues.

**Deviations / anomalies:**
- **Anomaly (process, non-blocking):** the implementing Developer agent completed all code + tests and
  marked the leg `landed` with criteria checked, but ended its run on a mid-thought ("wait for the monitor
  to notify me when the suite finishes") **before** writing this flight-log entry and before confirming the
  browser-suite result. The Flight Director treated the `landed` status as unverified, re-ran the new test
  AND the full browser suite (both green), reviewed the diffs, and authored this entry. No code rework was
  needed — the implementation itself was complete and correct; only the agent's self-closeout was truncated.
- No code deviations from the leg spec.

---

## Decisions

_None yet._

---

## Deviations

### Added an out-of-scope error-rendering fix (entry-gate driven)
**Planned**: Flight 2 was scoped to two legs (purge backend + purge button) plus the DD6 shared-surface
pull-ins. No retention error-rendering work was planned.
**Actual**: The F1-deferred entry-gate behavior test surfaced a pre-existing F1 defect — the agent
editor rendered save/validation errors as `[object Object]` (because `studio.js` did
`throw new Error(e.detail || 'Save failed')`, and a FastAPI 422 `detail` is a Pydantic **array**, not a
string). Added an `extractApiError(e, fallback)` helper to `studio.js` that pulls `loc`/`msg` out of the
detail array, and applied it to the save, create, and rename catch paths. Added a regression browser
test `tests/browser/test_flow_studio_retention_error_message.py` (sets retention 400, saves, asserts the
`.editor-error` text is readable and not `[object Object]`).
**Reason**: The flight lists "entry gate `agent-retention-setting-roundtrip` passes" as a Completion
Checklist item; the gate failed on this defect. The fix is small and lives in `studio.js` — a file this
flight already edits — consistent with the DD6 shared-surface philosophy. Operator explicitly chose
"fix it now in F2" over recording it as F1 debt. After the fix the entry gate re-ran 6/6.

---

## Anomalies

### Implementing agent (Leg 2) ended its closeout prematurely
**Observed**: The Leg-2 Developer agent completed all code + browser tests and marked the leg `landed`
with criteria checked, but its final message was a mid-thought ("wait for the monitor to notify me when
the suite finishes") — it did not write the flight-log Leg-2 entry or confirm the browser-suite result.
**Severity**: cosmetic (no code impact).
**Resolution**: The Flight Director treated the `landed` status as unverified, re-ran the new purge test
and the full browser suite (both green: 2 passed / 477 passed), reviewed the diffs against the leg spec,
and authored the Leg-2 flight-log entry. No rework needed.

### Behavior-test apparatus quirk — chrome-devtools click hit the button's child span
**Observed**: In the purge gate, the chrome-devtools `click` tool dispatched to the Purge-now button's
inner `<span>` and did not arm the two-step confirm; a direct `button.click()` via `evaluate_script`
armed it correctly.
**Severity**: cosmetic (test-apparatus only — native user clicks bubble span→button, so the product
behavior is correct).
**Resolution**: Executor used the scripted `.click()` path and verified arming via DOM state. Recorded
in the purge run log and the spec's Step 3 note for future runs.

### Post-purge WS session_list staleness (DD2a)
**Observed**: A hard reload immediately after purge briefly received a WS `session_list` push still
containing the purged sessions; the REST API (authoritative) returned 0, and a clean reload did not
reproduce it.
**Severity**: degraded (niche; concurrent WS client during the purge window only).
**Resolution**: Consistent with DD2a's explicitly accepted boundary (purge deletes DB rows, does not
evict in-memory `_sessions`). Filed as a Mission 13 Known Issue; candidate follow-up for Flight 3/4. Not
fixed in F2 (out of the manual-purge scope).

---

## Session Notes

_None yet._
