# Mission: Chat History Retention

**Status**: completed

> **Re-validated 2026-06-05, pulled off the backlog as Mission 13.** Drafted (as `XX-`)
> behind Mission 12 (Maintenance, Post-M11, now completed). Every dependency surface the
> backlog banner flagged was re-checked against the current post-M12 `main` and **all
> draft assumptions hold** (the M12 changes to these files were ruff-format reflow only,
> no semantic change):
> - **Migration version:** `CURRENT_VERSION = 29` (`db/schema.py:15`); M12 added no
>   migration → **v30 is still the correct next version**.
> - **AgentConfig** persists as dedicated SQLite columns; `max_iterations`
>   (`agent/config.py:265`, DDL `db/schema.py:55`) is the field precedent; the
>   model + migration + `save()` (`db/repositories.py:121`) + `_row_to_config()`
>   (`:226`) atomic-leg requirement is real (in-code IndexError note at `:240`).
> - **General-tab Behavior section** intact (`general-tab.js:116-121`); the Danger-Zone
>   `App.confirmDelete` arm-then-fire pattern (`:123-132`) is reusable for "Purge now".
> - **ChatSessionRepository** (`db/repositories.py:905`): single `delete()` by id exists;
>   no agent-wide / by-age primitive (both new). Sessions key on `agent_name`.
> - **`updated_at`** is bumped on engaged turns only — interactive (`:1020`) and connector
>   (`update_last_inbound`, `:1073`, called at `_inbound.py:928`); silenced/denied inbounds
>   do **not** bump (`_inbound.py:854`). No new bumping logic needed.
> - **Connector sessions** are keyed by `agent_name` (`connectors/_session.py:183`), so an
>   agent-scoped DB delete sweeps connector conversations too. (F05's reaper is web-UI-only;
>   connector sessions are DB-direct — unaffected.)
> - **Lifespan precedent (favorable drift):** M12 F05 added a lifespan-wired web-session
>   idle reaper with a shutdown drain (`app.py` loop `:512`, start `:113`, drain `:539`,
>   wired `:232`) — a closer precedent for the daily-purge task than the `mcp/oauth` sweep
>   originally cited. **Flight 3 mirrors the F05 reaper shape.**
>
> The architect viability re-check (Phase 4b) returned **feasible** — all three flights
> remain viable; no draft file:line target was invalidated. New gate to satisfy: M12's
> ruff lint/format CI now blocks PRs, so all new code must pass `ruff check` + `ruff format --check`.

## Outcome

Each agent automatically forgets old conversations. An operator can set, per agent, how
many days of inactive chat history to keep, and can wipe an agent's history on demand. Old
conversations no longer accumulate indefinitely — the platform prunes them without manual
intervention, giving operators control over how long an agent's chat memory persists.

## Context

Conversations in the-one accumulate forever. Every interactive Chat session and every
connector-originated conversation (Discord DMs, channel threads) is persisted as a
`ChatSession` row and never expires. Over time this grows unbounded, retains stale
history operators may not want kept, and offers no per-agent control over memory lifetime.

The agent General tab already exposes a small "Behavior" section (currently just Max
Iterations). Retention is a natural behavior-level knob to add there. The chat session
model records an `updated_at` timestamp that is bumped on each engaged turn — for both
interactive and connector sessions — which is the "last interaction" signal a retention
policy needs (see the refinement in Constraints below for what does and does not count as
an interaction). The purge plumbing partly exists (`ChatSessionRepository.delete()` and
single-session delete/purge endpoints), but there is **no** agent-wide delete-all and no
delete-by-age primitive. Agent config is persisted as **dedicated SQLite columns** (not a
JSON blob), so adding the retention field requires a schema migration. What's missing is a
per-agent retention setting, an agent-wide purge, and a daily process that enforces the
policy.

## Success Criteria

- [ ] Each agent exposes a chat-history retention setting (an integer number of days,
  constrained to 1–365, defaulting to 30) in the General tab's Behavior section,
  positioned above Max Iterations.
- [ ] The retention value persists across save and reload, and out-of-range values
  (below 1 or above 365) are rejected with a validation error rather than silently
  accepted or clamped.
- [ ] A "Purge now" control deletes all of that agent's conversations, but only after the
  operator explicitly confirms the destructive action.
- [x] A daily automated process removes every conversation whose last interaction predates
  the agent's retention window, while leaving conversations within the window intact.
  *(Flight 3 — due-based catch-up lifespan sweep; behavior-tested 6/6.)*
- [x] Purge (both manual and automated) removes entire conversations — including
  connector-originated ones — and never affects another agent's conversations.
  *(F2 manual half + F3 automated half; both behavior-tested. F3 verified aged interactive AND
  superseded-connector rows swept, recent/active-connector/other-agent kept.)*

## Stakeholders

- **Operator (primary)** — wants control over how long each agent retains chat memory, and
  a way to wipe history immediately. Benefits from bounded storage and privacy hygiene.
- **Agents (indirect)** — their persisted conversation history is the substance being
  retained or pruned; retention policy shapes what an agent can recall across sessions.

## Constraints

- Retention is expressed in whole days, 1–365 inclusive; there is no "keep forever" /
  unlimited option and no zero/immediate-expiry option. Out-of-range values are rejected
  (validation error), not clamped.
- "Last interaction" is the conversation's most recent **engaged turn** (the `updated_at`
  timestamp), **not** its creation time — an old conversation touched recently must be
  kept. Silenced/denied connector inbounds that the agent never engages with do **not**
  reset the retention clock (consistent with current behavior, no new bumping logic).
- A connector channel may have several historical `ChatSession` rows where only the active
  one receives interaction bumps; superseded rows age out independently under retention.
  This is the intended consequence — pruning old channel history while the active session
  survives is acceptable.
- Planning skills produce documentation only; implementation happens via flights under
  `/agentic-workflow`. No source changes during planning.
- The automated purge must integrate with the existing FastAPI lifespan lifecycle (started
  at startup, cancelled cleanly at shutdown), mirroring the M12 F05 web-session-reaper
  pattern (`app.py` loop `:512` / start `:113` / drain `:539` / wired `:232`). No new
  scheduler dependency unless a flight justifies it.
- The daily purge is **due-based with startup catch-up**: it persists a global
  `last_purge_at` and runs only when ≥24h have elapsed since the last run — so it is not
  re-run on every restart, but a window missed during downtime is honored on next startup.
- Destructive operations (manual and automated) must scope strictly to the target agent;
  no cross-agent bleed.

## Environment Requirements

- Existing the-one dev environment: Python 3.11+, FastAPI, SQLite, Docker via the project
  Makefile (`make rebuild` after `the_one/` changes on the image-baked path).
- Studio web UI reachable for the General-tab and Purge-now behavior verification.
- A running instance with at least one configured agent and provider (the dev `mock`
  provider suffices) for behavior-test verification.

## Open Questions

- [x] **Storage shape of the retention field** → Resolved by architect review: AgentConfig
  persists as dedicated SQLite columns (no free-form JSON blob exists on the `agents`
  table). Adding `chat_history_retention_days` **requires a schema migration (v30)**. The
  Pydantic field, the migration, the `save()` column, and the `_row_to_config()` decode
  must all land in the **same leg** (atomic-leg pattern) to avoid an `IndexError` on load.
- [x] **Daily cadence trigger** → Resolved: a **due-based catch-up scheduler**, not a naive
  interval-from-startup. Persist a single global `last_purge_at` timestamp; **check it on
  startup** and run the purge only if `now - last_purge_at >= 24h`. This means: NOT purged on
  every startup (a recent run is skipped), but a missed window self-heals (if the app was down
  when a run was due, it runs on next startup). After running, update `last_purge_at`; the
  lifespan loop then re-checks on a cadence (sleep until next-due, or a coarse periodic wake)
  and purges-if-due. The loop is wired into the FastAPI lifespan mirroring the **M12 F05
  web-session reaper** shape (start at `app.py:113`, shutdown-drain at `:539`/`:232`). The
  storage for `last_purge_at` (a small metadata row vs a settings store) is a Flight-3 design
  decision — it is global (one daily sweep covers all agents), not per-agent.
- [x] **Applying retention to pre-existing history on first ship** → Resolved: existing
  conversations simply become subject to the default 30-day policy going forward. The v30
  migration backfills `chat_history_retention_days = 30` on existing agents; no backfill or
  special handling of existing chat data is needed.

## Known Issues

- [x] **Flight 1 behavior-test live acceptance deferred** — RESOLVED in Flight 2. The
  `agent-retention-setting-roundtrip` Witnessed behavior test was run during F2 execution as the
  flight's entry gate and passed **6/6** (run `2026-06-05-20-42-09`). The first F2 run found a
  pre-existing F1 error-rendering defect (out-of-range saves displayed `[object Object]` instead of a
  readable message); that was fixed in F2 (`extractApiError` helper in `studio.js`) and the gate
  re-run clean. The live-acceptance gap is closed. (Run mode was batched-Witnessed — this session
  also lacked SendMessage continuation — but the act/judge separation was preserved.)
- [x] **Pre-existing a11y gap (observed during F1 review)** — RESOLVED in Flight 2 (DD6). The
  General-tab `system_prompt` textarea now has `id="studio-system-prompt"` and an associated
  `<label for="studio-system-prompt" class="visually-hidden">` (WCAG 1.3.1/4.1.2), verified by the F2
  accessibility review.
- [ ] **Post-purge WebSocket `session_list` staleness (DD2a consequence)** — discovered in Flight 2,
  affects the Chat-area session list under concurrent WS subscription. The "Purge now" endpoint deletes
  DB rows but does not evict in-memory `_sessions` (F2 DD2a, an explicitly accepted boundary). During
  the F2 purge behavior test, a hard reload immediately after purge briefly received a WS `session_list`
  push still containing the just-purged sessions, even though the REST API (authoritative) returned 0; a
  clean reload did not reproduce it. Niche (a concurrent client during the purge window) and consistent
  with the documented DD2a trade-off, but a tidier fix would have purge broadcast an invalidating
  `session_list` to subscribers. Candidate for Flight 3 (which already touches the purge/lifespan path)
  or Flight 4.
  **Partially addressed in Flight 3 (DD4):** the *automated* sweep runs in-process and **does** evict
  matching `_sessions` entries (three-phase, mirroring the F05 reaper — pop under `_sessions_lock`, then
  `session_locks.pop` + `agent.aclose()` outside), so the background reaper does not leave stale
  in-memory sessions. The *manual* F2 "Purge now" HTTP endpoint still does not evict `_sessions` (it
  runs in the repo/HTTP layer where reaching into app-state would be a boundary crossing) — so the
  original niche-staleness window remains only for the manual path. Remaining scope: retrofit eviction
  (or a `session_list` invalidation broadcast) onto the F2 endpoint, if judged worth it — Flight 4 or
  the end-of-mission maintenance flight.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and
> created one at a time as work progresses. This list will evolve based on discoveries
> during implementation.

- [x] Flight 1: **Retention Setting** — add the `chat_history_retention_days` field to
  `AgentConfig` together with its v30 schema migration, `save()` column, `_row_to_config()`
  decode, and a server-side 1–365 reject-validator (default 30) — all in one atomic leg —
  then render the input in the General tab Behavior section above Max Iterations and wire
  save/load. Behavior-test the set-persists-across-reload flow.
- [x] Flight 2: **Purge Now** — add an agent-wide "delete all conversations for this agent"
  repository method (parameterized `WHERE agent_name = ?`) and API endpoint, add the
  "Purge now" button with a confirmation step to the General tab (reusing the existing
  confirm-delete UI pattern), and wire it up. Behavior-test the confirm-then-history-gone
  flow. *(Landed 2026-06-05; both behavior gates green — purge 5/6, retention entry gate 6/6.)*
- [x] Flight 3: **Daily Automatic Purge** — add a daily background process wired into the
  FastAPI lifespan (mirroring the **M12 F05 web-session reaper** shape — loop + `create_task`
  start + shutdown-drain at `app.py:512/113/539/232`), using the **due-based catch-up**
  trigger (persist a global `last_purge_at`; on startup and on each cadence wake, purge only
  if ≥24h elapsed; update the timestamp after). It deletes each agent's conversations whose
  last engaged interaction (`updated_at`) predates that agent's retention window; verify
  newer conversations, other agents, and the active connector session are untouched
  (behavior-tested by seeding interactive and connector sessions with aged `updated_at`
  timestamps, plus a restart-catch-up case: down-through-a-due-window → purge runs on next
  startup; recent-run → startup skips).
- [ ] Flight 4 *(optional)*: **Alignment** — a vibe-coding session to tune the retention UX
  hands-on after the structured flights land (e.g. the input's placement/labeling/help text,
  the default value's feel, the purge-now confirm wording, any empty-state messaging).
  Creative collaboration, not structured execution; run only if the operator wants the polish pass.
  *(**Declined** at mission debrief 2026-06-06 — UX was acceptable as built; mission completed on F1–F3.)*
