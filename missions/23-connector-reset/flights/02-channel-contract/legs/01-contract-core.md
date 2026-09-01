# Leg: contract-core

**Status**: completed
**Flight**: [Channel Contract](../flight.md)

## Objective
Build the platform-agnostic connector core — Protocol, registry, listener manager, inbound pipeline (admission, pairing, `/new`, session resolution, dispatch, reply policy), stub plugin, config validator, lifespan hooks — and re-attach the send tool (with binding-derived authorization) and the last-N history tool, unit-tested and green, within the line budget.

## Context
- Flight DD-1..DD-8 and DD-11 govern this leg; read them in full (../flight.md). Key facts re-verified today:
  - `tools/builtins.py:get_tools` constructs tools as `cls(cfg, cross_configs=..., agent_name=...)` — `agent_name` is server-derived per bound agent, the trust anchor for DD-4's authorization. The `_TOOL_CLASSES` ordering assertion (`builtins.py:71`) is load-bearing: append new tools at the END of the dict, never before `read_file`.
  - `set_factory`/`get_factory` live at `agent/factory.py:156,:167` — the kept accessor the inbound pipeline uses to dispatch.
  - `llm/base.py` holds `OPERATOR_VISIBILITY` (`:147`) and `tag_post_step_visibility` (`:326`) — **the latter hardcodes the tool name `"send_to_platform_channel"`; per the Flight 1 debrief this is the one armed landmine: define the name ONCE as a shared constant (natural home: the send tool module exporting it, `llm/base.py` importing or asserting it) and add a test pinning the registered tool name to that constant.**
  - Lifespan: startup body ends before the `yield` at `app.py:255`; the MCP evict/drain block now sits at ~`app.py:305-325` and remains UNTOUCHABLE (squawk 0025). Add the connector manager start just before the yield and the manager drain in shutdown as a separate try/except placed so the MCP block's ordering is unchanged.
  - Kept seams (verified by Flight 1's targeted tests): `Connector` model + `_CONNECTOR_TYPES ("discord","stub")` (`db/models.py:169`), `ConnectorRepository` (`db/repositories.py:632-724`), `ChatSession` keying fields + `find_most_recent_by_external_key` + `TestConnectorSessionContinuation` (existing tests), rotation over `connectors.secrets`.
- **Recon step zero (Flight 1 debrief lesson)**: before writing code, content-grep the tree for every symbol you're about to (re)introduce (`send_to_platform_channel`, `fetch_channel_history`, `the_one.connectors`) to find dormant consumers — `tag_post_step_visibility` is one known; find any others (e.g. comments promising shapes) and reconcile.
- **Pre-reset reference material** (consult, don't copy): `git show 138025e^:the_one/tools/connector_send.py` (send tool contract, `[platform-send-ok]` prefix, visibility), `git show 138025e^:the_one/connectors/_session.py` (session reuse rules; port its test scenarios), `git show 138025e^:the_one/connectors/_stub.py` (stub shape).
- **Per-session serialization (design review 2026-08-31, high)**: the kept `the_one/sessions/` module (`_locks.py`) exists to serialize the WS handler's operator-typed messages against peer-inbound dispatch on the SAME `chat_sessions` row — `app.py:550` does `async with session_locks[session.id]:`, and the dangling comment at `app.py:1473-1475` still describes the contract against the deleted `_inbound.py`. `inbound.py`'s dispatch stage MUST acquire `session_locks[session_id]` around the agent-dispatch call, and that stale `app.py` comment gets updated to cite the new module.
- **Known-affected pinned test**: `tests/test_mcp_pool.py::test_lifespan_shutdown_drain_order` drives the REAL `lifespan()` against a `MagicMock()` conn with 4 spied shutdown targets; a bare `manager.start_all(repo)` would query the mock conn and break it. Fix: (a) wrap the lifespan manager start in its own `try/except` with `logger.exception` (mirroring the other startup blocks — a connector startup failure must not kill app startup), and (b) spy/mock the new manager start + drain hooks in that test like the existing four, updating its docstring/ordering assertion.
- **The shared constant covers BOTH literals**: `llm/base.py` hardcodes the tool name AND `platform_send_ok_prefix = "[platform-send-ok]"`. The send tool module exports both as constants; `llm/base.py` consumes them (or a pin test asserts equality for both) — the prefix is the same landmine class as the name.
- Line budget (DD-11): this leg's target keeps the whole `the_one/connectors/` package + both tools comfortably under the flight's 1,500 ceiling — **check the count mid-leg** (the flight names this leg the likely trip point); report the number at close. If approaching 1,500 before the pipeline is feature-complete, STOP and report `[BLOCKED:line-budget]` rather than trimming admission/pairing correctness.

## Inputs
- Branch `flight/02-channel-contract` from `main` @ `71bc500`; suite green (3,561 / 10 skips / ~6m10s).

## Outputs
- New package `the_one/connectors/`: `base.py` (Protocol `connect/disconnect/send/doctor` + optional `history`; `InboundEnvelope` with explicit `is_dm`/`mentions_bot`; channel-keyed and peer-keyed send-target types), `registry.py`, `manager.py` (listener tasks, jittered-backoff reconnect, pairing-code store, lifespan start/drain), `inbound.py` (pipeline + session resolver), `stub.py` (records outbound; sets envelope flags directly).
- `the_one/tools/connector_send.py` (re-attached, DD-4 authorization, shared name constant) and `the_one/tools/connector_history.py` (last-N, ~40 lines target), both registered at the END of `_TOOL_CLASSES`.
- Compact config validator on the `Connector` model (DD-2 keys; unknown keys rejected).
- Lifespan hooks in `app.py` per Context.
- Unit tests: pipeline (admission/pairing/reply-policy//new), session-resolution scenarios ported from the pre-reset module's tests, send-tool authorization matrix (channel mapped/unmapped/DM/allowlisted/not/dangling default_agent), manager reconnect (stub-driven), config validator, tool-name pin test.
- NO routes, NO Studio UI, NO test seams, NO docs rewrite (legs 2–3).

## Acceptance Criteria
- [x] `the_one/connectors/` imports cleanly; the stub plugin registers and a unit test drives a full in-process round-trip: paired-peer envelope → reply recorded on the stub, unknown-peer envelope → no reply, nothing persisted
- [x] Pairing: one-time code with TTL; correct code appends peer to `allowlist.peers` (persisted) and is consumed; second use fails silently; expiry honored; wrong guesses persist nothing (asserted against the DB)
- [x] Reply policy: unit matrix over `is_dm` / `mentions_bot` / `always_listen` / none-of-the-above; `/new` ends the session (next inbound gets a fresh `chat_sessions` row); unknown `/foo` reaches the agent as text
- [x] Session resolution: keyed on the kept columns with COALESCE'd thread_id; continuation window honored (scenarios ported from `git show 138025e^:.../_session.py` tests); `peer_id` stored
- [x] Send tool authorization — the EXPLICIT matrix passes, positive and negative rows: mapped channel + mapped agent → allowed; mapped channel + any other agent (incl. default_agent) → refused; unmapped channel + default_agent → allowed; unmapped channel + non-default agent → refused; DM + default_agent + allowlisted peer → allowed; DM + default_agent + non-allowlisted peer → refused; DM + non-default agent → refused; dangling `default_agent` → unmapped-channel and DM sends refused with clear error, but **mapped-channel sends by the mapped agent still succeed** (resolution never touches default_agent). Result carries the `[platform-send-ok]` prefix; visibility tagging fires end-to-end — both the tool NAME and the PREFIX pinned by the shared-constant test
- [x] Concurrency: a unit test proves inbound dispatch and a concurrent operator WS-path write on the same session serialize via `session_locks` (no interleaved agent step)
- [x] `manager.stop(account_id)` exists and a unit test pins it (stops the listener task; idempotent on unknown id) — leg 2's DELETE route depends on the shape
- [x] History tool: returns last N via the Protocol's optional `history`; clean "not supported" when absent
- [x] Agent loop untouched: `git diff main -- the_one/agent/core.py` empty; `factory.py` diff empty or comment-only
- [x] MCP drain block byte-identical: `git diff main -- the_one/interfaces/web/app.py` shows no hunk overlapping ~`:305-325`
- [x] `make test-unit` green, no new skips/xfails; `ruff check` and `ruff format --check` clean
- [x] Line count reported in the flight log: `the_one/connectors/` + `tools/connector_send.py` + `tools/connector_history.py` total, vs the 1,500 flight ceiling
- [x] Flight log Leg Progress entry appended

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_*.py tests/test_connector_*.py -x --timeout 30` (new files) during iteration; full `make test-unit` at close — FOREGROUND with adequate timeout, never backgrounded.
- Line count: `wc -l the_one/connectors/*.py the_one/tools/connector_send.py the_one/tools/connector_history.py`.
- The two `git diff` checks above, plus `grep -n "send_to_platform_channel" the_one/ -r` showing the name defined in exactly one constant.

## Implementation Guidance
1. `base.py` first (Protocol, envelope, target types, errors) — small and typed.
2. `registry.py` + `stub.py` — stub records `sent: list` and exposes a driver hook for tests.
3. Config validator on `Connector` (DD-2) + its tests.
4. `inbound.py` — pipeline stages as small functions in one module; session resolver per DD-5 with ported scenarios; dispatch via `get_factory()`.
5. `manager.py` — task-per-connector, backoff with jitter, pairing store, `start_all(repo)` / `drain()`.
6. Tools — send (DD-4 authorization + shared name constant + prefix) and history; register at END of `_TOOL_CLASSES`; pin-name test.
7. Lifespan hooks (Context placement rules).
8. Mid-leg line-count check; full suite; flight-log entry.

## Edge Cases
- **Pairing race**: two peers submit the same live code — first wins, second gets silence (code consumed atomically).
- **Connector disabled/deleted while listener runs**: manager must stop the task before repository delete completes (the route lands in leg 2, but the manager API must support `stop(account_id)` now).
- **Reply policy on a paired peer in a non-always-listen channel without mention**: silence — paired ≠ always answered.
- **`/new` from an unpaired peer**: admission runs FIRST; unknown senders get silence even for commands.
- **Stub in unit tests must not leak tasks**: manager tests use explicit start/stop; conftest teardown pattern mirrors the old `_clear_for_test` hook Flight 1 removed from `tests/conftest.py:362-389` (re-add a minimal equivalent if needed).

## Files Affected
New: `the_one/connectors/{__init__,base,registry,manager,inbound,stub}.py`, `the_one/tools/connector_send.py`, `the_one/tools/connector_history.py`, new unit test files.
Edited: `the_one/db/models.py` (config validator), `the_one/tools/builtins.py` (two registrations at END), `the_one/interfaces/web/app.py` (two lifespan hooks + the stale `:1473-1475` comment), `the_one/llm/base.py` (shared-constant reconciliation, name + prefix), `tests/conftest.py` (teardown hook if needed), `tests/test_builtins.py` (three hardcoded `len(tools) == 19` assertions + the 19-name set → 21), `tests/test_mcp_pool.py` (lifespan-ordering test gains manager start/drain spies).

---

## Post-Completion Checklist

**Complete ALL steps before handoff:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`)
- [x] Update flight-log.md with leg progress entry (incl. line count)
- [x] Set this leg's status to `landed` — commit happens at flight end
- [x] Check off this leg in flight.md
