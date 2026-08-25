# Leg: self-revision-write-path

**Status**: completed
**Flight**: [Self-Configuration Surface](../flight.md)

## Objective

Let an agent revise its own description and system prompt through the
surface — two write tools, one per field, each stating whether the revision
takes effect from the next turn of the open conversation or from the next
conversation — with `next_turn` applied at turn exit (never mid-turn),
`next_session` riding the existing rebuild-on-rejoin path, and the
`agent-self-revision-propagation` behavior test executed against a live
agent.

## Context

- **DD6** — the write allowlist is the catalog's shape: `update_my_description(text, apply)`
  and `update_my_system_prompt(text, apply)`, `apply ∈ {"next_turn",
  "next_session"}`. No tool takes a field name; a future `AgentConfig` field
  is unwritable because nothing addresses it. A revision restates the whole
  value — no append, no partial edit.
- **DD7** — `_run_iterations` re-binds `request_messages = self.messages`
  inside its `while` loop (`agent/core.py:_run_iterations`, ~:276) and tool
  dispatch happens in that loop, so mutating `messages[0]` from a tool call
  would land on the *next iteration of the same turn*. `next_turn` is a
  deliberate deferral to turn exit; the mechanism is `Agent.reset()`'s two
  lines (`agent/core.py:reset` — `self.system_prompt` and
  `self.messages = [Message.system(...)]`) minus the history wipe.
- **DD8** — propagation is verified behaviorally: no read path exposes a
  running agent's prompt (`session_joined` carries no prompt; `GET /api/agents/{name}`
  is the stored row). The behavior test
  `tests/behavior/agent-self-revision-propagation.md` (drafted with the
  flight; steps 1–8) is this leg's acceptance for the propagation criteria,
  run via `/behavior-test agent-self-revision-propagation` by the Flight
  Director, not by the implementing Developer.
- **Leg 2 outcome** — the surface package (`the_one/self_configuration/`),
  the credential source and registry, `_calling_agent(ctx)` with the DD9
  refusal, the projections, and the enable path that populates
  `_cache.tools`. **Prior-leg learnings (Leg 2, landed 2026-08-24,
  uncommitted)**: the package is `the_one/self_configuration/` —
  `surface.py` holds the `FastMCP` instance `mcp`, the tools as
  `@mcp.tool()` async functions taking `ctx: Context`, `_calling_agent(ctx)
  -> str` (:55; raises a plain `PermissionError` on any failure, and the
  module converts escaping exceptions to `isError` results — reuse it, do
  not add a second refusal path), and `list_surface_tools()` (:140);
  `manage.py` holds `SURFACE_ROW_NAME_TEMPLATE` (:29), `is_surface_row`,
  `owner_of`, `enable`, `disable`, `reconcile_on_startup(mcp_repo)` (:221),
  `cascade_rename`, `_fresh_cache(tools)` (:96, the `_cache` shape);
  `credentials.py` holds the registry. `app.py` wraps the lifespan in
  `_self_configuration_session_scope()` (:134) and calls
  `reconcile_on_startup` at :197. Stateless HTTP held; the shutdown-drain
  warning is handled by pre-drain eviction but was not re-verified against the
  probe's log line (Leg 2 caveat — AC10 here re-checks it on a real start/stop).
  Full unit lane: 4344 passed / 10 skipped (~6 min); browser lane runs in this
  environment (15 passed on the two Leg 2 files).
- **Flight open question owned here** — a pending `next_turn` revision when
  the agent object is rebuilt before the turn's loop exits. Resolved by LD3
  below: the revision is persisted *immediately* by the tool, so a rebuild
  (which always reads the stored row) applies it; only the in-memory
  deferral is lost, and by then it is moot.

### Leg decisions

**LD1 — Contextvars do not cross the loopback hop; the deferral is keyed by
agent name and applied at the turn-settle sites in the web layer.** The write
tool runs in the loopback request's task, so `current_chat_session_id` /
`current_tool_call_id` (set in `app.py` around `agent.step`) are not visible
to it, and the `Agent` object has no name. The tool therefore (a) persists
the revision to the stored row and (b) records a pending `next_turn` entry
`{agent_name → {"system_prompt": ..., "description": ...}}` in an in-process
registry (`the_one/self_configuration/pending.py`); `record()` **merges** into
any existing entry for that agent, so two different-field revisions in one
turn both apply at the same settle. The two non-paused turn-settle sites in
`app.py` — the `if not paused:` block in `_process_and_broadcast` (:1896) and
the `if not re_paused:` block in `_resume_paused_session` (:1980; **not** the
unconditional save/usage tail after it, which also runs when the resume
re-pauses) — call `apply_pending_revision(session.agent_name or "default",
session.agent)`. The `or "default"` is load-bearing: `Session.agent_name` is
stored as `None` for the default agent (`app.py` ~:1016) while the registry and
`_calling_agent` use the literal `"default"` (the normalization
`session.agent_name or "default"` already exists at `app.py` ~:1362) — a
skip-on-`None` guard would silently degrade `next_turn` to `next_session` for
single-agent installs. The hook pops the entry and mutates
`agent.system_prompt` and `agent.messages[0]` in place (description is not in
the message list; it is stored only). A paused or re-paused turn is not over —
the hook runs only on the non-paused settle, so a revision made before an auth
pause lands when the resumed turn finally settles.

**LD2 — Persist first, defer second.** Both `apply` modes write the stored
row immediately via `SQLiteAgentStore.load → model_copy(update=…) → save`,
so a concurrent Studio edit to another field is not clobbered and
`next_session` needs no further machinery (`_get_or_restore_session` always
rebuilds from the row). `next_turn` adds only the in-memory deferral.

**LD3 — Rebuild-before-exit discards the deferral, and that is correct.** If
the session is rebuilt mid-turn (a rejoin), the new `Agent` is constructed
from the already-persisted row, so the revision is live; the pending entry is
then a no-op and is cleared on the next settle. Multiple open sessions of the
same agent: the first to settle consumes the entry; others pick the revision
up on rejoin (that is `next_session` semantics for them, documented). Connector
inbounds rebuild the agent per message (`connectors/_inbound.py:933`) and
therefore always see the stored row.

**LD4 — The tool's result is truthful and non-retry-inducing.** It returns
`{"applied_to_store": true, "effective": "next_turn" | "next_session",
"field": ..., "length": N}` and a one-sentence explanation of when the change
becomes visible. It never claims the running conversation has changed. (Flight
2's approval mode will add a `"queued"` outcome to the same shape.)

**LD5 — Input bounds, not content policy.** Both tools reject an empty or
non-string `text`, a `text` over 64 KiB (no cap exists anywhere today —
`AgentConfig`, the Studio textarea, the API — so this is the first bound, not
a mirror), and an `apply` outside the two literals. Rejection uses the
module's one error mechanism: raise a plain `ValueError` with a one-line
message and let the surface module convert it to an `isError` result, exactly
as `_calling_agent`'s `PermissionError` does — no second signalling path. The leg does not rate-limit revisions; the flight's
"revision loop" question is answered by the revision log in Flight 2, and
this leg records the count of revisions per agent per process in a log line
so a loop is at least visible.

**LD6 — Adding the write tools changes the surface's tool list, so the
`_cache.tools` payload every enabled row carries must be refreshed.** Startup
reconcile (Leg 2) is extended to rewrite `_cache.tools` from the FastMCP
instance's current list for every surface row, so a row enabled under Leg 2
gains the write tools on the next start — and the operator's per-tool
checkboxes on the MCPs tab show them.

**LD7 — The surface row's name becomes the constant `self-configuration`
(closes Anomaly A11).** `MCPClientTool` prefixes every tool as
`mcp__{normalized source name}__{tool}` and silently drops names over 64
chars (`mcp/_tool.py:_TOOL_NAME_MAX_LEN`). Leg 2's template
`self-configuration (<agent>)` left ~11 chars of agent name before
`describe_my_capabilities` was dropped; this leg's `update_my_system_prompt`
(23 chars) is longer still. `mcp_sources.name` carries no UNIQUE constraint
(`db/schema.py` v10 table: `name TEXT NOT NULL`), the ownership marker — not
the name — identifies the owner, and `mcp_overrides` is keyed per agent, so
every agent's row can share one name. With the constant, the four prefixed
surface tool names are fixed at 45–49 chars. `cascade_rename` stops renaming
the row (marker only). **The literal name is reserved**: override application
is keyed by source *name* (`_tool_provider.py` `(config.mcp_overrides or
{}).get(source.name)`, mirrored in `mcps-tab.js` and in
`manage.reject_surface_credential_overrides`'s name-keyed dict), so an
operator's own ordinary source named `self-configuration` attached to the
same agent would collide. `create_mcp_source` and `update_mcp_source` reject
(409) any non-surface source whose name equals the constant, mirroring the
existing "cannot edit a marked row" guard. Startup reconcile renames
legacy-template rows **and migrates each owner's `mcp_overrides` key** from
the old name to the constant (so per-tool checkboxes set under Leg 2 survive);
a unit test pins the four fixed prefixed names at ≤ 64 chars and another pins
`mcps-tab.js`'s `_slugify` in agreement with `mcp/_tool.py`'s source-name
normalization for the constant.

## Inputs

- Leg 2 landed: `the_one/self_configuration/{constants,credentials,surface,projection,manage}.py`,
  the enable path, `reconcile_on_startup`, `_calling_agent(ctx)`.
- `the_one/agent/core.py` — `Agent.__init__` (`self.system_prompt`,
  `self.messages = [Message.system(system_prompt)]`), `step`,
  `_run_iterations`, `reset`.
- `the_one/interfaces/web/app.py` — `Session` (`agent`, `agent_name`),
  `_process_and_broadcast` settle (`if not paused:` → `_persist_last_usage`
  → `done`), `_resume_paused_session` tail, `_get_or_restore_session` /
  `_restore_session` (always rebuilds).
- `the_one/db/repositories.py:SQLiteAgentStore` (`load`, `save`; encryptor
  per Leg 1).
- `tests/behavior/agent-self-revision-propagation.md` — status `draft`;
  `.flightops/agent-crews/behavior-tests-execution.md` — Executor/Validator
  crew; goldfinch browser apparatus per the mission's environment notes.
- Dev-instance prerequisites (flight): a non-8484 port, scratch data dir,
  gate enforced, a test agent with a real provider that can complete a turn,
  surface enabled with `update_my_system_prompt` left enabled.

## Outputs

- Two write tools on the surface; `pending.py` registry; `apply_pending_revision`
  hook wired at both settle sites; reconcile refreshes `_cache.tools`.
- Unit tests: catalog shape (exactly four tools; no tool parameter names a
  field), input bounds, persist-then-defer, hook applies exactly once and only
  at the non-paused settle, mid-turn non-application (a fake LLM that calls
  the tool then continues one more iteration observes the *old* prompt in the
  second request's `messages[0]`), rebuild-discards-safely, next_session
  untouched in the open agent, reconcile refreshes `_cache.tools`.
- Behavior test run log at `tests/behavior/agent-self-revision-propagation/runs/…`
  with a PASS verdict (or a recorded, operator-accepted disposition).
- Docs: `SECURITY-MODEL.md` (the self-configuration surface and its
  indirect-prompt-injection residual risk — flight Completion Checklist),
  `the_one/agents.md` (write path + deferral contract), `CLAUDE.md` (the four
  tools, `apply` semantics).

## Acceptance Criteria

- [x] **AC1 — catalog shape is the allowlist.** The surface exposes exactly
      four tools; the two write tools' input schemas have parameters `text`
      and `apply` only; a unit test asserts no tool schema contains a
      parameter that names an `AgentConfig` field (the "by construction"
      assertion the flight's Verification demands).
- [x] **AC2 — writes persist the two fields and nothing else.** After a
      revision, the stored row differs from before in exactly the revised
      field (and `updated_at`); every other field, including `mcp_source_ids`
      and the surface's own row, is byte-identical.
- [x] **AC3 — `next_turn` does not land mid-turn.** With a scripted LLM that
      calls `update_my_system_prompt(apply="next_turn")` and then makes one
      more iteration in the same turn, the second LLM request still carries
      the old system message; the *following* `step()` carries the new one,
      with the conversation history intact (no wipe).
- [x] **AC4 — the hook runs at the non-paused settle only, once.** A turn that
      pauses for auth does not apply the revision; a resume that re-pauses
      does not either; the resumed turn's final settle does; the entry is
      consumed (a second settle is a no-op). The default agent
      (`Session.agent_name is None`) applies exactly like a named agent.
- [x] **AC5 — `next_session` leaves the open agent alone** and a rebuilt
      agent (`_restore_session`) carries the revision.
- [x] **AC6 — description revisions persist and never touch `messages`.**
- [x] **AC7 — input bounds** per LD5 return error results; the stored row is
      unchanged on every rejected call.
- [x] **AC8 — reconcile refreshes `_cache.tools`, the row name, and the
      override key** so a row enabled before this leg lists four tools after
      restart, is named `self-configuration`, and its owner's per-tool
      overrides keyed by the old name are carried to the new key; this happens
      even when the URL did not change; the MCPs tab shows four checkboxes; a
      unit test pins the four fixed prefixed names at ≤ 64 chars and
      `_slugify`/`_normalize_source_name` parity for the constant (LD7).
- [x] **AC8b — the constant name is reserved.** `POST /api/mcp-sources` and
      `PUT /api/mcp-sources/{id}` with `name: "self-configuration"` on a
      non-surface source → 409; existing guards on marked rows unchanged.
- [x] **AC9 — behavior test executed and passing.**
      `/behavior-test agent-self-revision-propagation` run against a scratch dev
      instance (port 8485). First run (`runs/2026-08-25-02-39-45.md`) was 6/8
      and surfaced a suspected `next_session` defect; server-side instrumentation
      proved the propagation mechanism correct and identified the two failures as
      a spec-observability confound (the sentinel-in-reply oracle is only reliable
      on the first turn of a fresh conversation). The spec was corrected to
      measure `next_session` via a fresh conversation; the corrected re-run
      (`runs/2026-08-25-14-13-57.md`) is **8/8 PASS**. See flight log A12/A13.
- [x] **AC10 — suites green, docs updated** (`make test-unit`, ruff; the three
      doc files above, including the residual-risk statement).

## Verification Steps

- AC1–AC8: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_self_configuration_write.py tests/test_self_configuration_surface.py -x --timeout 60`
  — the mid-turn test uses the mock provider with a scripted tool call
  (`stream_chunks` / scripted responses per `CLAUDE.md` "Dev mode and the
  mock provider") or a stub `LLMProvider` that records each request's
  messages.
- AC9: Flight Director invokes `/behavior-test agent-self-revision-propagation`
  after the Developer lands the code; the run log path goes in the flight-log
  entry.
- AC10: `make test-unit && make lint && .venv/bin/ruff format --check the_one/ tests/`.

## Implementation Guidance

1. **Pending registry** — `the_one/self_configuration/pending.py`:
   `record(agent_name, *, system_prompt=None, description=None)`,
   `apply_pending_revision(agent_name, agent) -> bool`, `clear_for_test()`.
   Apply mutates `agent.system_prompt` and replaces `agent.messages[0]` with
   `Message.system(new_prompt)` (index 0 is always the system message — see
   `Agent.__init__` and `reset`). Log at INFO with the agent name and field.
2. **Write tools** — `surface.py`: `update_my_description` and
   `update_my_system_prompt`, each: resolve caller (Leg 2 helper, DD9
   refusal) → validate (LD5) → `store.load(name)` → `model_copy(update=…)`
   → `store.save` → if `apply == "next_turn"`: `pending.record(...)` → return
   the LD4 shape. Keep the `apply` literal and the error strings in one
   place; the behavior test's step 2/6 expectations ("reports that it
   revised … and that the change applies from …") depend on the tool result
   being explicit enough for the agent to relay.
3. **Hook wiring** — `app.py`: in `_process_and_broadcast`'s `if not paused:`
   block (:1896), before `_send_to_session(session, {"type": "done"})`; and in
   `_resume_paused_session` inside the `if not re_paused:` block (:1980) next
   to its `done` broadcast — **not** in the unconditional tail. Both calls:
   `apply_pending_revision(session.agent_name or "default", session.agent)`.
   Connector inbound (`_inbound.py`) and `/api/selftest` build fresh agents
   and need no hook.
3b. **Reserved name guard** — `api.py`: in `create_mcp_source` and
   `update_mcp_source`, a non-surface source whose `name` equals the constant
   → 409 with a message naming the Self-configuration tab. Surface rows
   themselves are still created only by `manage.enable`.
4. **Reconcile** — extend `manage.reconcile_on_startup` so that, for every
   marked row and on every startup **unconditionally** (not inside the
   existing `if url != fresh_url:` branch): rewrite `_cache.tools` from
   `surface.list_surface_tools()`; if the row's name is not the constant,
   rename it and move the owner's `mcp_overrides[old_name]` to
   `mcp_overrides[constant]` via the store (skip if the constant key already
   exists — log it); persist only when something changed.
5. **Tests**, then **docs**. Do not touch the behavior test spec except to
   correct a demonstrable drift; note any such change in the flight log.

## Edge Cases

- **Revision while the agent is mid-turn in *another* open session** →
  persisted; that session applies it at its own next settle if it holds the
  entry, else on rejoin. Documented; not a defect.
- **Operator edits the prompt in Studio between the revision and the settle**
  → the store holds the operator's later write (last-writer-wins at the row);
  the pending in-memory entry still applies the agent's text to the live
  conversation until rejoin, when the row wins. Recorded as the known
  divergence Flight 2's staleness handling is for; the leg logs it, does not
  solve it.
- **Two `next_turn` revisions of the same field in one turn** → the second
  overwrites the first in the registry; both persisted in order; the last wins
  everywhere. **Two different-field revisions in one turn** → merged; both
  apply at the same settle (tested).
- **Connector-driven agents** → rebuilt fresh per inbound message
  (`_inbound.py:933`), so `next_turn` and `next_session` coincide there; the
  pending entry, if any, is consumed by a web session's settle or discarded at
  exit. Documented, not a defect.
- **`next_turn` with no live session** (external client, Flight 3) → the
  entry is harmless; it is consumed by the next settle of any session of that
  agent or cleared at process exit.
- **Prompt text containing the sentinel the behavior test looks for** → the
  spec's preconditions require it absent beforehand; the test agent must be
  seeded fresh.
- **`system_prompt` revised to empty** → rejected (LD5); an agent cannot blank
  itself.

## Files Affected

- `the_one/self_configuration/pending.py` — new.
- `the_one/self_configuration/surface.py`, `manage.py` — write tools,
  reconcile extension, `SURFACE_ROW_NAME_TEMPLATE` → constant name (LD7),
  `cascade_rename` narrowed to the marker.
- `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js` /
  `self-configuration-tab.js` — only if either displays the row name in a way
  the constant breaks (verify; likely none).
- `the_one/interfaces/web/app.py` — two hook calls.
- `the_one/interfaces/web/api.py` — reserved-name guard in
  `create_mcp_source` / `update_mcp_source`.
- `tests/test_self_configuration_write.py` — new; `tests/test_self_configuration_surface.py`,
  `tests/test_self_configuration_api.py` — extended (LD7 name change, reconcile
  rename of legacy rows, 64-char pin).
- `tests/behavior/agent-self-revision-propagation.md` — status → `active`
  after the first run; run log directory created by the run.
- `SECURITY-MODEL.md`, `the_one/agents.md`, `CLAUDE.md` — docs.

## Risk Checks

- **Schema**: none.
- **State-machine**: the pending entry has two states (present/absent) and
  one consumer; lower layers cannot foreclose it (it is process memory). The
  `Agent.reset()` path clears history and rebuilds `messages[0]` from
  `self.system_prompt` — after the hook has mutated `system_prompt`, reset
  keeps the new prompt, which is correct.
- **Cache freshness**: `_cache.tools` — source of truth is the FastMCP tool
  list; rebuild triggers are enable (Leg 2) and startup reconcile (this leg);
  staleness bounded to one restart after a code change to the catalog.
- **Interface changes**: none to shared signatures; two call sites added in
  `app.py`.
- **Security**: the write tools are reachable only through the confined
  surface; the residual risk (an injected agent shedding its guardrails while
  keeping its tools) is the mission's named one and is documented, not
  mitigated, here.

## Citation Audit

Checked against the working tree with Legs 1–2 landed (uncommitted),
2026-08-24:

- `agent/core.py` — `self.messages = [Message.system(system_prompt)]` :178,
  `step` :205, `_run_iterations` :239 with `request_messages = self.messages`
  :289, `reset` :635 — live.
- `interfaces/web/app.py` — `_self_configuration_session_scope` :134,
  `reconcile_on_startup` call :197, `_restore_session` :1050,
  `_get_or_restore_session` :1184, `_process_and_broadcast` :1587 with
  `if not paused:` :1896 and `done` broadcast :1914, `_resume_paused_session`
  :1918 with its `done` broadcast :1980 — live.
- `connectors/_inbound.py` — `factory.create(decision.agent)` :933 — live.
- `self_configuration/surface.py` — `_calling_agent` :55, `get_my_configuration`
  :101, `describe_my_capabilities` :118, `list_surface_tools` :140 — live.
- `self_configuration/manage.py` — `SURFACE_ROW_NAME_TEMPLATE` :29,
  `_fresh_cache` :96, `enable` :114, `disable` :184, `reconcile_on_startup`
  :221, `cascade_rename` :244 — live.
- `mcp/_tool.py` — `_TOOL_NAME_MAX_LEN = 64` :39 — live.
- `db/schema.py` — `mcp_sources` rebuild DDL `name TEXT NOT NULL` ~:399, no
  UNIQUE — live.
- `tests/behavior/agent-self-revision-propagation.md` — steps 1–8, status
  `draft` — live.
- Design-review verified: `_build_degraded_messages` reads `self.system_prompt`
  live (`core.py` ~:427); `_restore_session` (~:1121) and connector inbound
  (~:936) splice the fresh agent's system message over persisted history;
  `messages_to_ui_events` skips `Role.SYSTEM`; `save()` re-encrypts both
  override columns (`repositories.py` ~:230); `_resume_paused_session`'s tail
  after :1980 is unconditional; `Session.agent_name` is `None` for the
  default agent (`app.py` ~:1016) and normalized at ~:1362; override
  application keyed by name at `_tool_provider.py` ~:283 and `mcps-tab.js`
  :257/:516/:531; `mcps-tab.js:_slugify` parallels
  `mcp/_tool.py:_normalize_source_name`.

Design review (2026-08-24, Developer/Sonnet): approve with changes — the
resume-path hook gated on `re_paused`, default-agent name normalization made
explicit, reserved-name guard added, `record()` merge semantics stated,
reconcile made unconditional with override-key migration, LD5 aligned to the
module's single error mechanism, arithmetic and test wording corrected.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [x] Update flight.md status to `landed`
  - [x] Check off flight in mission.md
- [x] Commit all changes together (code + artifacts)
