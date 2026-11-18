# Flight Log: GleepGlorp exists and can answer

**Flight**: [GleepGlorp exists and can answer](flight.md)

## Summary
In flight. Branch `flight/01-gleepglorp-exists-and-answers` from `main` at
`9fea53cd`.

### Flight Director Notes
- Phase file `.flightops/agent-crews/leg-execution.md` loaded and valid (Crew,
  Interaction Protocol, Prompts). Developer: Sonnet. Reviewer: Sonnet (this
  flight touches a security-sensitive surface: GleepGlorp's read views of
  secret-bearing records, and the self-configuration surface row in the
  migration). Accessibility Reviewer: Sonnet (UI flight).
- Batches (the project's batch mode, and Mission 35's lesson that a
  quota-spending, operator-gated leg needs its own review and commit before its
  runs): **Batch A** = Legs 1-2 (`unit-tier-room`, `retire-default-agent`),
  then review, fix and a checkpoint commit. **Batch B** = Legs 3-5
  (`gleepglorp-settings-and-build`, `gleepglorp-in-chats`,
  `gleepglorp-knows-the-app`), then review (plus the Accessibility Reviewer),
  fix and a checkpoint commit. **Leg 6** (`prompt-and-evals`) runs after Batch
  B is committed, under the operator gate, committing each measured prompt text
  before its rounds. **Leg 7** (`hat`) is operator-guided.
- Leg 1 `unit-tier-room` tiered **low-risk** (test timings only, no product
  change, an established pattern): no design review. Developer (Sonnet) spawned.
  No other crew runs tests while it takes the quiet-host reading.
- Leg 2 `retire-default-agent` tiered **high-risk** (an irreversible schema
  step, shared validation, a security-adjacent surface row): design review by a
  Developer (Sonnet), read-only, run in parallel with Leg 1's implementation.
- Decision (Leg 2 design): the chat-surface "Default agent" labels and the
  picker/session-flow `default` checks move from Leg 2 to Leg 4. Until Leg 3
  the server can still create NULL-agent chats, so the labels still label
  something, and Leg 4 rewrites those surfaces for GleepGlorp anyway; the five
  browser tests pinning "Default agent" change once. Leg 2 keeps only the agent
  editor's routines checks for an agent named `default`, which v53 makes dead.
- Leg 2 design review (Developer, Sonnet): approve with changes. Applied:
  `test_name_repair.py`'s `default` seed and the routines browser tests that pin
  `routines-default-agent` are in scope; chats have no FK to agents (explicit
  deletes mandatory); no other hand-deletes needed (all `session_id` columns
  live in tables cascading from `agents`); `gleepglorp_notes` columns inlined
  with a unique index on `number`; rename loc is `["name"]`;
  `_checked_agent_name` only on the two agent routes; a shared
  `_reject_reserved_binding` for connectors (PUT revalidates the merged config);
  the import checks both stem and config name; exact version pins listed.
  Questions decided: `start_session` keeps "Invalid agent name."; routines
  refuse GleepGlorp on purpose. The fixes were clarifications with no change to
  the leg's shape, so no second review cycle. Leg 2 set `ready`; its
  implementation waits for Leg 1 to land (the quiet-host reading).
- Leg 1 landed: trims cut the five real-fixture tests from ~40 s to ~19 s, but
  the quiet-host tier read 303.74 s (start load 0.81; 10264 passed, 15
  skipped). The Developer moved the unit-tier target to 350 s (measured plus
  ~15%) in CLAUDE.md; **operator accepted 350 s (2026-11-18)**. Crew-rule
  lapses recorded (recurring per Mission 35's debrief): `sed -i` on source and
  on the leg file was attempted (refused by the classifier and the project
  hook) and a sleep wait loop was started, then stopped. Leg 2's spawn prompt
  repeated both rules explicitly.
- Leg 2 landed: unit tier 298.63 s under netns (10299 passed, 15 skipped);
  `agent-routines` lane green; static guards and ruff clean. Falsified: the
  reserved-name refusals and the v53 NULL-chat delete. Not falsified: the
  startup rename, connector 422s, inbound drop, `start_session`, routines
  guards, v53 idempotency/fresh-db tests (the Reviewer weighs these).
- **Batch A review**: Reviewer (Sonnet, security-sensitive tier: the migration
  deletes the self-configuration surface row and its external credentials).
  No Accessibility Reviewer for Batch A: its only UI change removes two dead
  branches and their testids; no user-facing surface is added or reshaped.
- Batch A review: [HANDOFF:confirmed], no blocking issues (18 files, 1138
  tests). Two non-blocking nits carried to the flight-end review: the
  duplicated `check_agent_name` message lookup in `_reject_reserved_binding`
  (`api.py` ~200-235) and the v53 agents delete also guarding on `mcp_sources`.
  Legs 1-2 set `completed`; squawk 0383 completed. Checkpoint commit by a
  Developer (Sonnet).

---

## Leg Progress

### unit-tier-room
- Trimmed the real-fixture MCP stdio tests: the slow-legacy client test and the
  route test now use window 2.5 s, delay 3 s, limit 7 s (4 s slack; both kept,
  so one real slow-start test remains, in fact two); the silent-drop and
  count-reset tests use a 1.5 s window of a 7 s limit (5.5 s slack). Same
  assertions. The slow dual-era test (window 5 s, delay 1 s, limit 8) is
  unchanged: it ends as soon as the fixture starts. No shared spawns were needed.
- Targeted files, three runs: 26.9 s, 26.6 s, 26.5 s pytest time (about 29.5 s
  wall each), 32 passed. The five tests dropped from about 40 s to about 19 s.
- Quiet-host unit tier (start load 0.81, no other test process, `THE_ONE_TEST_NETNS=1
  make test-unit`): **10264 passed, 15 skipped, 303.74 s**. It did not reach 285 s
  (sortie 19 read 299.4 s; the tier also grew by a few tests). A second run with
  `--durations` (start load 2.85, loaded by the previous run's tail, so not a
  reading) showed no other slow test: the slowest remaining is 6.8 s
  (`test_resolver_clip`), then the trimmed MCP tests at 3.6-4.2 s; the rest is
  about 10k tests of ordinary cost.
- Per the leg's fallback, the unit-tier target moved to 350 s (measured plus 15%)
  in CLAUDE.md "Full-gate target" and squawk 0383. The Flight Director should
  confirm this, as the leg requires telling them before landing.

### retire-default-agent
- Added `naming.py` reserved agent names (`GLEEPGLORP_AGENT_NAME`, `RESERVED_AGENT_NAMES`,
  `is_reserved_agent_name`, `check_agent_name`); used by agent create/rename
  (`api.py::_checked_agent_name`), the JSON import (stem and body name), connector
  create/update (`_reject_reserved_binding`, merged config on PUT), `dispatch_inbound`
  (drop before `resolve_session`), `start_session`, and the routines guards. The
  startup repair renames a stored reserved-name agent (reserved names seed `taken`).
- Schema v53 (`CURRENT_VERSION = 53`): retires the `default` agent and its data, its
  surface MCP row, connector bindings to `default`, NULL/`default` chats and an orphan
  `GleepGlorp` chat; creates `gleepglorp_notes` + `gleepglorp_notes_counter` `(1, 1)`.
  Each step guards on table existence, because hand-built partial databases in older
  migration tests lack tables (an FK-cascading `DELETE FROM agents` also needs
  `mcp_sources` to exist).
- Removed the dead `default` checks in `routines-tab.js` and `self-config-routines.js`,
  their two browser tests, and retired the two testids (registry + `RETIRED_SELECTORS`).
- Deviation (as the leg records): the chat-surface "Default agent" labels move to Leg 4.
  Factory fallback, app.py/CLI NULL-to-`default` paths untouched.
- Docs: CLAUDE.md naming-rule watch-out, `the_one/agents.md` "Naming rule".

---

## Decisions

---

## Deviations

---

## Anomalies

---

## Session Notes

### 2026-11-18 — Planning
- Mission 36 approved and set active. Flight 1 designed with the operator: no
  agents row for GleepGlorp, settings in app metadata, a new Assistant group in
  Settings, a Built in group in the picker, the setup state in the new-chat
  card, CLI and selftest use GleepGlorp, all switches on by default, a closing
  HAT, and squawk 0383 folded in as Leg 1.
- ASCII mockups approved, then a high-fidelity board of six screens on the
  GleepGlorp AI design system (https://claude.ai/artifact/JJaL55X2wc7KBkiyqKGcWV)
  approved by the operator.
- Architect design review, two passes (Opus), both "approve with changes".
  Pass 1: tools always seeded (exposure is environment-dependent), exact
  `default` in the migration with a casefold startup rename, no broken tree
  between legs, stricter masking for GleepGlorp's reads, GleepGlorp degraded
  statuses with an open chat re-joining, the full list of `default` special
  cases; Leg 3 split by capability (now seven legs). Pass 2: leg boundaries
  for the fallback's callers, `start_session` admitting `GleepGlorp` in Leg 4,
  Leg 3's GleepGlorp with notes and web off until Leg 5, the selftest tool
  check, a "which agent" helper with a settings href, the client source in
  Leg 3, an agent-only rename predicate. All applied.
- Operator approved the flight (2026-11-18); status set to ready and
  execution started with agentic-workflow.
