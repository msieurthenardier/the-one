# Leg 3: Verify Integration

**Status**: completed
**Flight**: [Agent Query](../flight.md)
**Risk tier**: **low** — changes no source file. The code it verifies was
covered by the flight-end review (`[HANDOFF:confirmed]`, zero findings), and
the behavior spec it executes went through three Architect cycles plus two
revisions. Per-leg design review skipped; rationale recorded in the flight
log. *(If the premise audit in AC-1 forces a spec change beyond a typo, that
is a spec re-author and comes back for review — see AC-2.)*

## Objective

Prove the flight against the real environment: run
`kb-agent-query-round-trip` on a dedicated dev instance, run every gate by
hand (there is no CI lane on mission-branch PRs), confirm the frozen Windows
build still passes with its installer size unmoved, and close the flight's
mission-facing artifacts.

## Scope

**Creates**
- `tests/behavior/kb-agent-query-round-trip/runs/{timestamp}.md` — the run log

**Modifies**
- `tests/behavior/kb-agent-query-round-trip.md` — status `draft` → `active`,
  `Last Run`, plus any premise corrections from AC-1
- `missions/24-knowledge-bases/mission.md` — Flight 5 checked off, criteria
  updated
- `missions/24-knowledge-bases/flights/05-agent-query/flight.md` — status
  → `landed`, checkpoints and completion checklist
- `.../flight-log.md` — Leg 3 entry, gate results, the run's outcome

**Out of scope**: any source change. If a gate fails inside this flight's own
files, one fix iteration is budgeted and it returns through the Reviewer; a
failure **outside** them is raised to the operator rather than fixed here
(the Flight 2/3/4 rule).

## Acceptance Criteria

### Premise audit (before any run)

- [x] **AC-1** Re-verify each of the behavior spec's premises against current
  code, not against the planning-time record:
  - `/ws` authorizes on the bearer credential —
    `CredentialGateMiddleware._handle_websocket` resolves the cookie then
    falls back to `_resolve_header`; `OriginAllowlistMiddleware` rejects an
    upgrade only when an `Origin` header is **present** and disallowed, and a
    Python `websockets` client sends none.
  - The `/ws` protocol is as pinned: `{"action":"join","session_id":…}` →
    `{"type":"session_joined",…}`; `{"action":"message","message":"…"}` — the
    key is `message`, not `content`; the turn ends on `{"type":"done"}`.
  - `MockProvider` requires `id`, `name` and `arguments` on each scripted
    `tool_calls` entry.
  - `max_iterations: 1` still dispatches the tool and persists its result
    (the budget is consumed at the *top* of the iteration body).
  - `PUT /api/agents/{name}` is a full replace preserving only
    `mcp_overrides` and `self_revision_requires_approval`, so `kb_ids` must
    be re-sent.
  - `GET /api/chat/sessions/{id}` returns `messages` carrying `tool_calls`
    and `tool_result{content, is_error}`.
  - The unknown-tool path yields `is_error: true` with content naming the
    tool and carrying neither the fixture identifier nor fixture text.
- [x] **AC-2** Any correction the audit finds is applied to the spec **before
  the first run**. A correction that changes what a checkpoint *asserts*
  (rather than how it is driven) is a spec re-author: stop and bring it back
  for review rather than editing it mid-run.
- [x] **AC-3** External-session prerequisites re-verified **on the day**, not
  from planning: `fly -t the-one status` logged in and `windows-worker`
  `running` (squawk 0068's rule — the token expired mid-flight in Flight 4).

### Behavior test

- [x] **AC-4** A dedicated dev instance is up: `THE_ONE_DEV_MODE=true
  THE_ONE_PORT=8485 THE_ONE_DATA_DIR=<scratch>`, credential minted with
  `rotate-api-credential` **before** the first `make up`. **Never port 8484,
  never the operator's default data directory.**
- [x] **AC-5** `/mission-control:behavior-test kb-agent-query-round-trip`
  runs to completion. Every checkpoint PASSES. A FAIL or INCONCLUSIVE is an
  unmet acceptance criterion: the leg does not land while it stands, and the
  disposition (fix and re-run, or an operator-accepted known issue) is
  recorded in the flight log beside the run-log path.
- [x] **AC-6** The four load-bearing observations, called out because they
  are the flight's mission criteria rather than incidental steps:
  1. an attached agent's turn produces a call to `kb__KBQ-test__search`
     whose **tool result carries text from the indexed fixture** and the
     child file's path;
  2. `search_tools` surfaces the tool under a `kb:` group;
  3. an **unattached** agent's identical scripted call returns
     `is_error: true` carrying neither the fixture identifier nor fixture
     text;
  4. an agent whose `enabled_tools` is a narrow built-in list **keeps** its
     knowledge-base tool, and `disabled_tools` still removes it by name.
- [x] **AC-7** The run log is committed at
  `tests/behavior/kb-agent-query-round-trip/runs/{ts}.md`; evidence stays at
  the ephemeral `/tmp/behavior-tests/...` path and is **never** committed.
- [x] **AC-8** The spec moves `draft` → `active` with its `Last Run` set.
- [x] **AC-9** The dev instance is torn down and the scratch data directory
  and fixture folder removed. No machine username or absolute home path
  appears in any committed artifact.

### Gates (by hand — there is no CI lane on mission-branch PRs)

- [x] **AC-10** `make lint` clean.
- [x] **AC-11** `make test-unit` **verbatim, alone, foreground** — the
  canonical gate. Record the pass/skip counts and wall-clock. *(Run it
  backgrounded with a log if a long foreground call risks a tool-call
  ceiling, but the command itself is unmodified.)*
- [x] **AC-12** `pip-audit` against the unchanged closure — this flight adds
  no dependency, so a new finding is upstream news, not this flight's.
- [x] **AC-13** One frozen Windows run, detached:
  `(setsid nohup fly -t the-one execute -c ci/tasks/windows-installer-build.yml -i repo=. -o installer=<dir> > <log> 2>&1 < /dev/null &)`,
  watched with anchored greps `^RESULT: (PASS|FAIL)` and
  `^(succeeded|failed|errored|aborted)$`.
- [x] **AC-14** The frozen run reports `RESULT: PASS` with **nine** doctor
  gates `OK` (the ninth, `file watcher`, landed in Flight 4), and the
  installer size is recorded against Flight 4's close — **134,938,414 bytes**
  (build 612549). Expected unchanged: no dependency and no package data was
  added. A material move is an anomaly to explain, not to wave through.

### Closing artifacts

- [x] **AC-15** `mission.md`: Flight 5 checked off; the retrieval and
  agent-query criteria updated to reflect what landed, including that the
  Studio attach surface remains Flight 6's.
- [x] **AC-16** `flight.md`: status → `landed`, all checkpoints and the
  completion checklist checked.
- [x] **AC-17** `flight-log.md`: the Leg 3 entry with every gate's result,
  the behavior run's outcome and log path, plus deviations and anomalies.
- [x] **AC-18** PR #204 marked ready for review, its body updated with the
  Leg 3 results (`gh pr edit` fails with a GraphQL error on this repo — use
  `gh api -X PATCH repos/msieurthenardier/the-one/pulls/204 -F body=@file`
  then `gh pr ready 204`).

## Verification

Each criterion above is its own verification. Constraints that apply
throughout: never `-m live`; never port 8484 or the operator's default data
directory; browser tests only via `scripts/run-tests.sh`; pair any ad-hoc
pytest with `-x --timeout`.

## Environment notes (verified at leg design, 2026-09-17)

- `fly -t the-one status` → logged in; `windows-worker` → `running` (2d).
- **Both Linux workers (`de5299cf212d`, `worker2`) are `stalled`.** The
  Windows installer task runs on `windows-worker`, so AC-13 is unaffected —
  but anything needing a Linux worker would fail, and that is worth knowing
  before blaming this flight's code for a CI failure.

## Post-Completion Checklist

- [x] All acceptance criteria checked off
- [x] Leg status → `completed`
- [x] Leg checked off in `flight.md`
- [x] Flight log updated
