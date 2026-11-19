# Leg: proposal-apply

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
Let the operator approve or dismiss a GleepGlorp proposal over the API.
- Approve applies exactly the proposed fields through Leg 1's services. The
  proposal is marked in the same transaction, so it applies at most once.
- A stale proposal is refused unless overridden.
- A failed apply is recorded on the proposal with its errors.
- After an apply, open clients are told what changed.

## Context
- **Flight design:**
  - DD7: routes and the apply.
  - DD4: the status transitions, stale handling and withdrawn.
  - DD3: the services, including routine flag carry-through and
    `created_by="operator"`.
  - DD9: a flagged routine stays flagged.
  - DD10: the `config_changed` event. Its client side is Leg 7.
- **Prior legs:**
  - Leg 1 built `change_agent(deps, name, changes, *, base, override,
    on_commit)`, `create_agent(deps, data)`, `rules_service.create_rule(repo,
    agent, …, position, on_commit)` and `change_rule(repo, agent, rule_id,
    changes, *, base, override, on_commit)`, with `AgentWriteError` and
    `AgentStaleError`. `api.py` has `_agent_write_deps()` (~L271) and
    `_agent_write_errors()` (~L204).
  - Leg 2 built `GleepGlorpProposalRepository` (`get`, `list_for_session`,
    `mark(id, status, *, result, from_statuses)` plus its in-transaction op
    form), the `view` serialiser and `push_proposal_changed`.
  - Read both legs' flight-log entries for the names they actually used.
- **Out of scope:**
  - **Leg 5** adds the approval message and the continuation turn. This leg's
    approve route ends after the frames and returns. Leg 5 adds one call at
    the marked spot.
  - **Leg 6** draws the card.

## Inputs
- `the_one/interfaces/web/routines_api.py`: the separate-router precedent
  (`router.include_router(_routines_router)` in `api.py` ~L7117) and the
  approve route's error mapping (stale 409, gone 409, name 422/409).
- `the_one/routines/service.py`:
  - `create_routine(repo, agent, data, *, now, zone, created_by, agent_caps,
    flag, proposal, schedule_pair)` (L222);
  - `update_routine(repo, agent, current, data, *, now, zone, flag, proposal,
    precheck, schedule_pair)` (L278).

  The repository's `proposal` parameter is now the `ProposalRunner` Protocol
  (Leg 1: `run(conn, routine_id)`).
- `the_one/sessions/_locks.py::is_session_busy(session_id)` (L49).
- `the_one/sessions/_broadcast.py::broadcast_to_all` (L44).
- Leg 1's and Leg 2's modules, as above.

## Outputs
- `the_one/gleepglorp/proposals/apply.py`: `apply_proposal`,
  `dismiss_proposal` and `ProposalApplyResult`.
- `the_one/interfaces/web/gleepglorp_proposals_api.py`, a new router included
  from `api.py`.
- `create_agent(deps, data, *, on_commit=None)`: Leg 1's create service gains
  the hook.
- Tests and docs.

## Acceptance Criteria
1. **The routes**, behind the credential gate, in a router included from
   `api.py` like the routines and secrets routers. The router is reachable
   through `tests/_api_app.py::shared_app()`.
   - `GET /api/gleepglorp/proposals?session_id=` returns `{"proposals":
     [view…]}` for that chat, by id. An unknown or empty `session_id` gets an
     empty list.
   - `POST /api/gleepglorp/proposals/{id}/approve[?override=true]`:
     - On an apply, it returns `{"proposal": view}` with `status: "applied"`.
     - On a failed apply, it returns the same body with `status: "failed"`.
       The `result.errors` value is the detail list in `[{loc, msg}]` form.
     - Status is 200 in both cases.
   - `POST /api/gleepglorp/proposals/{id}/dismiss` returns `{"proposal":
     view}`.
   - An unknown id is a 404 with the detail "Proposal not found: {id}".
2. **The refusals** are all 409, and none of them writes anything:
   - `{"error": "busy"}` when `is_session_busy(row.session_id)`. Approve and
     dismiss both check it, server-side.
   - `{"error": "stale", "fields": [{"field", "label", "current",
     "proposed"}]}` when a touched field changed since `base` and `override`
     is false. The status is unchanged.
     - Agents and rules raise `AgentStaleError`.
     - Routines use a precheck built from `base` the same way as
       `routines/service.py::_stale_precheck`.
     - Labels come from the change shape. Values are display-normalised: ids
       become names, and the surface id is stripped.
   - `{"error": "gone"}` when the target no longer exists (a missing agent, or
     a missing rule or routine). The row is marked `withdrawn` with `result =
     {"reason": "gone"}`.
   - `{"error": "closed", "status": s}` for a dismissed or withdrawn row.

   An `applied` row answers 200 with its view. Approving twice returns
   "already applied" through the view, with no second write.
3. **`apply_proposal`** (`proposals/apply.py::apply_proposal(conn, deps, id, *,
   override, now, zone) -> ProposalApplyResult`) is a shared function. The
   route calls it, and so does Leg 8's eval harness. By kind and action:
   - **Agent create:** `create_agent(deps, data, on_commit=mark_applied)`,
     where `data` is the stored `changes`. `create_agent` gains an `on_commit`
     keyword that it forwards to `save`; Leg 1's create 409 precheck stays.
   - **Agent change:** `change_agent(deps, agent, changes, base=base,
     override=override, on_commit=mark_applied)`.
   - **Rule create:** `create_rule(repo, agent, text, enabled,
     position=position-1 or None, on_commit=mark_applied)`.
   - **Rule change:** `change_rule(repo, agent, rule_id, changes, base=base,
     override=override, on_commit=mark_applied)`.
   - **Routine create:** `create_routine(repo, agent, data, now=…, zone=…,
     created_by="operator", agent_caps=False, flag=("merge", sources) when the
     proposal is untrusted else None, proposal=mark_runner,
     schedule_pair=(schedule, anchor_at))`.
   - **Routine change:** `update_routine(repo, agent, current, data, …,
     flag=…, proposal=mark_runner, precheck=stale_precheck,
     schedule_pair=…)`. The pair is passed only when the schedule is among the
     changes.
   - **Routine plumbing:**
     - `current` is loaded by the caller (`repo.get(agent, routine_id)`); if
       it is `None`, the result is `gone`.
     - `stale_precheck` comes from a small new public builder in
       `routines/service.py`, `stale_precheck_for(base, touched_keys,
       override)`. It reuses `_base_of`, `_BASE_KEYS`, `_touched_base_keys` and
       the `_PAYLOAD_TO_BASE` rule (a schedule touches `schedule`, `anchor_at`
       and `finished_at`), and raises `ProposalStaleError`. It exists because
       `_stale_precheck` takes a `RoutineProposal`.
     - Leg 2's routine `base` must use the `_base_of` keys (`name`, `prompt`,
       `schedule`, `anchor_at`, `enabled`, `finished_at`). If Leg 2 stored the
       shape's field names, this leg converts them in one place and records it.
     - `schedule_pair` is `(dict, datetime | None)`, built from the stored
       `schedule` and `parse_anchor(anchor_at)` through `_approval_pair(changes,
       zone)`, made public, which re-zones the start for the current zone.
     - `data` carries `name`, `prompt` and `enabled` as given, never
       `schedule` or `anchor_at`, so the pair is the only schedule input.
     - A passed `schedule_pair` skips `resolve_now_start`, so
       `created_by="operator"` with `agent_caps=False` is safe.
     - `create_routine` and `update_routine`'s `proposal` annotation widens to
       Leg 1's `ProposalRunner`.
     - The routine service already pokes the scheduler after commit. The agent
       and rule paths add nothing.

   `mark_applied` and `mark_runner` are Leg 2's in-transaction mark, with
   `from_statuses=("pending", "failed")` and a row-count check. The mark also
   writes the `result` summary (AC6) in the same UPDATE. On a zero row count
   it raises a private `_AlreadyResolved(Exception)`; it does not use
   `KeyError` or `ValueError`, which the services map to 404 or 422. Every
   service lets that exception through: `change_agent`'s loop catches only its
   retry error, the rule services catch only `RuleLimitError` and `KeyError`,
   and the routines repository catches only `IntegrityError`. So the apply
   transaction rolls back, and the change lands once.

   **The order inside `apply_proposal`:**
   - **(a) Before the lock:** read the row. `applied` returns its view
     ("already applied"). `dismissed` or `withdrawn` is 409 `closed`. A busy
     chat is 409 `busy`.
     - For a change, a missing target is `gone`.
     - For a rule or routine create, a missing agent is `gone`
       (`agent_rules.agent_name` has a foreign key to `agents`, so the write
       would otherwise raise `IntegrityError`; that is also caught
       defensively and mapped to `gone`).
   - **(b)** Run the service call.
   - **(c) On any exception from the call, `_AlreadyResolved` included,**
     re-read the row first. If it is now `applied`, return its view ("already
     applied"): no `failed` mark, no stale answer, no frames.
   - **(d) Only otherwise** map the error to stale, failed or gone (AC2, AC4).

   The re-read in (c) is what makes a concurrent double approve answer
   "already applied". There, the loser sees stale, a name conflict or
   `_AlreadyResolved`. The row-count mark is what guarantees one apply.
4. **A failed apply.** Validation errors mark the row `failed` with `WHERE
   status IN ('pending', 'failed')` (never over `applied`) and `result =
   {"errors": [{loc, msg}]}`. One helper maps every error type:
   - **`AgentWriteError` 422 or 409:** its detail list as is. A string detail
     becomes `[{"loc": [], "msg": …}]`. `RuleLimitError` already arrives as
     `AgentWriteError(422)` from the rule services.
   - **`RoutineFieldError(field, message)`:** `[{"loc": [field], "msg":
     message}]`.
   - **`RoutineScheduleError` and `RoutineLimitError`:** a string detail
     becomes `[{"loc": ["schedule" | []], "msg": detail}]`. The routine caps
     error from `check_routine_caps` is the class `limits.py` defines; confirm
     it is `RoutineLimitError`.
   - **`RoutineNameTaken`:** `[{"loc": ["name"], "msg": …}]`.
   - **`NameRuleError`:** `[{"loc": ["name"], "msg": e.message}]`.

   **Gone, not failed:**
   - `AgentWriteError(404)` from `change_agent`;
   - a 404 from `change_rule`;
   - a `KeyError` from the routine repository;
   - `IntegrityError` on a create (AC2).

   **Stale:** `AgentStaleError` and `ProposalStaleError` (AC2).

   **Unexpected exceptions** are not caught. They are a 500 with no `failed`
   mark, and no traceback is stored.

   A later Approve on a `failed` row tries again, which is the Try again
   button.
5. **After an apply,** in this order, after the commit:
   1. `push_proposal_changed` (to the chat);
   2. `broadcast_to_all({"type": "config_changed", "kind": kind, "agent":
      agent_name, "fields": [changed field names], "session_id": …,
      "proposal_id": …, "at": now ISO})`;
   3. `App.store`-relevant invalidation is the client's job (Leg 7);
   4. the route returns.

   On dismiss, a failed apply, or withdrawn, only `push_proposal_changed` is
   sent. An "already applied" answer sends no frames, so the clicking window
   never gets a second `config_changed`. A comment `# Leg 5: continuation` marks the one place Leg 5 adds its
   call, after the frames on an apply.
6. **`result` on an apply** holds a short summary for the card and for Leg 5's
   message, for example `{"summary": "Created agent Issue digest", "agent":
   "Issue digest", "fields": [...]}`. A routine also gets its schedule
   sentence. The summary is built from the shape's labels.
7. **Dismiss** (`apply.dismiss_proposal`) marks `dismissed` `WHERE status IN
   ('pending', 'failed')`, sets `resolved_at`, and pushes the frame. A busy
   chat gets 409 `busy`, and a closed row gets 409 `closed`.
8. **Tests** (`tests/test_gleepglorp_proposals_apply.py`,
   `tests/test_gleepglorp_proposals_api.py`), falsified where marked. Each
   test seeds a proposal through Leg 2's repository.
   - **Applies:**
     - Each kind and action applies exactly its fields. The agent case is
       checked against every other field, the switches and `mcp_overrides`.
   - **Stale and override:**
     - A stale agent, rule and routine proposal gets 409 `stale` with labels
       and leaves the status unchanged. Falsified by skipping the base.
     - `override=true` applies.
   - **Applied once:**
     - Double approve, done sequentially and with two concurrent tasks, for an
       agent change, an agent create and a routine create, applies once and
       returns "already applied" with no `failed` mark and one
       `config_changed`.
     - Falsified twice: once by dropping the re-read in step (c), and once by
       dropping the row-count check, using a rule create, which has no
       precheck.
     - A `failed` mark over `applied` is a no-op.
     - A rule or routine create for a deleted agent gives `gone`.
   - **Failures and retries:**
     - A name taken since the proposal was made gives `failed` with the
       name's `[{loc, msg}]`, and a retry after a fix applies.
     - `failed` never overwrites `applied`.
   - **Refusals:**
     - Gone gives `withdrawn` and 409.
     - Busy gives 409 with nothing written. Falsified by removing the check.
   - **Routine flags:**
     - An untrusted routine proposal gives a routine stored with
       `untrusted=1` and the sources. Falsified by dropping the flag.
     - It is stored with `created_by="operator"`.
   - **Frames:** `config_changed` is broadcast once per apply and never on a
     failure.
   - **Dismiss:** a dismissed row gives 409 `closed`.
   - **Routes:** the auth gate holds (a 401 without credentials), and an
     unknown id gives 404.
   - **The guard:** every existing agent, rule, routine and GleepGlorp test
     stays green.
     - `tests/test_api_name_rule.py`'s `PREFIXES` already cover
       `/api/gleepglorp`, and the test walks the included routers. So the two
       new POST routes must be added to `EXEMPT`, as a required step:
       - approve: "applies an operator-approved proposal by id; a proposed
         agent name goes through `check_agent_name` in `create_agent`";
       - dismiss: "dismisses a proposal by id; writes no configuration".
9. **Docs.**
   - The `the_one/agents.md` proposals section gains the routes, the apply
     order, the status transitions and the `config_changed` frame (in the
     WebSocket table too).
   - `CLAUDE.md`'s GleepGlorp proposals paragraph gains the three routes.
   - `SECURITY-MODEL.md` records that the routes are operator-only, behind
     the credential gate, POST-only for writes, and unreachable from
     GleepGlorp's tools.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_*.py tests/test_agent_service.py tests/test_rules_service.py tests/test_api_name_rule.py tests/test_credential_gate.py -x --timeout 60`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh $(grep -rlE 'routines/service|routine_service|/routines' tests/*.py) -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `ruff check` and `ruff format --check` on the touched files.

## Implementation Guidance
1. Read Leg 1's and Leg 2's flight-log entries and code for the actual names.
2. Add `on_commit` to `create_agent`.
3. Write `apply.py`: the dispatch by kind, the error mapping to `[{loc, msg}]`
   (one helper), the stale payload with labels, gone and withdrawn, and the
   summary.
4. Write the router module and include it from `api.py`. Build deps with
   `await _api._agent_write_deps()`, and use `_api.get_connection()` as
   `routines_api.py` does, so tests that patch `api` keep governing.
5. Add the frames (`push_proposal_changed`, `config_changed`) and the `# Leg 5`
   marker.
6. Write the tests, falsify the ones marked, run the guard set and the unit
   tier, then update the docs.

## Edge Cases
- **The target agent was renamed after the proposal.** Leg 2's rename cascade
  rewrote `agent_name` and `target_key`, so apply finds it under the new name.
- **A proposal from another chat**: the routes are keyed by proposal id. The
  chat id is used only for the busy check and the frame.
- **GleepGlorp turned off** since the proposal: apply still works (DD8, the
  operator's action). Leg 5 decides the continuation.
- **A rule proposal whose agent's rules hit the total-chars limit** since:
  `failed` with the limit's own detail.
- **A routine create whose start has passed** by the time of approval: the
  routine service's own refusal (`no runs left`) gives `failed`.
- **`create_agent` reserved names**: the proposal shape already refuses them.
  If one gets through, the service's check gives `failed`.
- **The approve response and the broadcast both reach the clicking window**:
  Leg 6/7 handle that idempotently, keyed by proposal id and status.

## Files Affected
- `the_one/gleepglorp/proposals/apply.py` (new).
- `the_one/interfaces/web/gleepglorp_proposals_api.py` (new); `api.py` (one
  `include_router` line).
- `the_one/agent/service.py` (`create_agent` `on_commit`).
- Possibly `the_one/routines/service.py` (export a reusable stale-precheck
  builder from `base`, if `_stale_precheck` is too tied to
  `RoutineProposal`).
- Tests: two new files, and possibly `tests/test_api_name_rule.py`.
- `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md`.

## Citation Audit
Checked against the working tree with Leg 1 landed (uncommitted) and Leg 2 in
progress. Re-check Leg 2's names after it lands.
- `api.py::_agent_write_errors` ~L204 and `_agent_write_deps` ~L271 —
  verified.
- `service.py::create_agent(deps, data)` L154 has no `on_commit`, and
  `change_agent` takes `on_commit` (L297) — verified.
- `service.py::AgentWriteDeps` L95 and `AgentStaleError(fields)` L108 —
  verified.
- `rules_service.py::create_rule` L26 and `change_rule` L42 — verified (the
  exact signatures come from Leg 1's log).
- `routines/service.py::create_routine` L222 and `update_routine` L278 (with
  `precheck`, `proposal`, `flag`, `schedule_pair`), `approve_proposal` L683
  (already-applied returns the row) — verified.
- `routines_api.py::approve_routine_proposal` (~L312): error mapping for stale
  and gone (409), `NameRuleError` (422), `RoutineNameTaken` (409 through
  `_name_conflict_detail`), `RoutineLimitError` (422) — verified.
- `sessions/_locks.py::is_session_busy` L49 — verified.
- `api.py` includes the routines and secrets routers at ~L7117 and ~L7122 —
  verified.
- **Design review** (Developer, Sonnet), approve with changes. Folded in
  above:
  - **(high)** As first written, the precheck blocks the "already applied"
    path, so the re-read was added in step (c).
  - **(high)** `test_api_name_rule.py` `PREFIXES` cover `/api/gleepglorp`.
  - The error types and their shapes.
  - Gone for 404s and `KeyError`.
  - `_stale_precheck` takes a `RoutineProposal`.
  - `_approval_pair` and `parse_anchor`.
  - `agent_rules` has a foreign key to `agents`.
  - `change_agent` catches only its retry error; the rule services catch
    `RuleLimitError` and `KeyError`; the routines repository catches
    `IntegrityError`.
  - Leg 7 must handle `config_changed` before the join gate.

  No second cycle: the fixes are the reviewer's own mechanisms, with no new
  design.
