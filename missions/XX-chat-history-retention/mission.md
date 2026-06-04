# Mission: Chat History Retention

**Status**: planning (backlogged)

> **Backlogged — re-evaluate before scheduling.** This mission is deferred behind a
> maintenance cycle. The `XX-` prefix is a placeholder; assign the next available
> sequence number when it is pulled off the backlog. Because the maintenance cycle is
> likely to change parts of the codebase this mission depends on (the `AgentConfig`
> model and its persistence/migration path, the General-tab Studio JS, the
> `ChatSession` repository and its purge primitives, the connector session semantics,
> and the FastAPI lifespan), the architect viability check and the file:line references
> below must be re-validated against the post-maintenance codebase before flight design.
> Treat the storage-shape determination, the "engaged-turn" interaction semantics, and
> the migration version (v30) as findings-at-time-of-drafting, not commitments.

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
- [ ] A daily automated process removes every conversation whose last interaction predates
  the agent's retention window, while leaving conversations within the window intact.
- [ ] Purge (both manual and automated) removes entire conversations — including
  connector-originated ones — and never affects another agent's conversations.

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
  at startup, cancelled cleanly at shutdown), consistent with existing periodic-task
  precedent. No new scheduler dependency unless a flight justifies it.
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
- [ ] **Daily cadence trigger** — a 24h interval loop from startup (mirroring the existing
  `mcp/oauth/_state.py` periodic-sweep precedent) is the planned approach. Confirm during
  the automated-purge flight whether a specific wall-clock time-of-day is required instead.
- [x] **Applying retention to pre-existing history on first ship** → Resolved: existing
  conversations simply become subject to the default 30-day policy going forward. The v30
  migration backfills `chat_history_retention_days = 30` on existing agents; no backfill or
  special handling of existing chat data is needed.

## Known Issues

_None yet — emergent blockers will be recorded here as flights surface them._

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and
> created one at a time as work progresses. This list will evolve based on discoveries
> during implementation.

- [ ] Flight 1: **Retention Setting** — add the `chat_history_retention_days` field to
  `AgentConfig` together with its v30 schema migration, `save()` column, `_row_to_config()`
  decode, and a server-side 1–365 reject-validator (default 30) — all in one atomic leg —
  then render the input in the General tab Behavior section above Max Iterations and wire
  save/load. Behavior-test the set-persists-across-reload flow.
- [ ] Flight 2: **Purge Now** — add an agent-wide "delete all conversations for this agent"
  repository method (parameterized `WHERE agent_name = ?`) and API endpoint, add the
  "Purge now" button with a confirmation step to the General tab (reusing the existing
  confirm-delete UI pattern), and wire it up. Behavior-test the confirm-then-history-gone
  flow.
- [ ] Flight 3: **Daily Automatic Purge** — add a daily background process, wired into the
  FastAPI lifespan (mirroring the `mcp/oauth` periodic-sweep module shape, started at
  startup and cancelled cleanly at shutdown), that deletes each agent's conversations whose
  last engaged interaction predates that agent's retention window; verify newer
  conversations, other agents, and the active connector session are untouched
  (behavior-tested by seeding interactive and connector sessions with aged `updated_at`
  timestamps).
