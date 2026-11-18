# Leg: patient-discover

**Status**: completed
**Flight**: [Local-command MCP servers: newest protocol and Forget](../flight.md)

## Objective
A local-command MCP server that has not answered `server/discover` yet is asked again until a deadline before the client falls back to the older handshake, and a fallback caused by no answer is recorded on the client, in the era memory's rule and in the stored cache.

## Context
- Flight decisions DD1 (the patient probe and what counts as "no answer"), DD2 (the window), DD3 (remembered only the second time in a row), DD4 (the fallback fact, on the client and in `_cache`) and DD6 (tests). Read them first; this leg builds exactly those.
- The cause being fixed: `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` (10.0) runs from the spawn of a local-command server. A server that starts later than that has not answered, `_negotiate.py::_full_policy` calls `session.initialize()`, and the started server answers on the older revision: a new server version beside protocol 2025-11-25, with fewer tools, and no error (squawk 0372).
- The policy in `_negotiate.py` is a branch-for-branch port of the SDK's private `negotiate_auto`, on public names only, with a parity test that runs both. With no deadline given, this leg must leave it byte-for-byte equal in behaviour.
- Facts from the Architect's review that the build depends on:
  - A second `send_discover` on one session is safe: a new request id each time, the abandoned waiter removed, a late answer dropped with a debug log. The SDK sends no cancel notification for discover.
  - A probe timeout is `MCPError(code=REQUEST_TIMEOUT)` (-32001, `from mcp.types import REQUEST_TIMEOUT`). A server may send that code itself, so the code alone does not mean "no answer".
  - A Python-SDK dual-era server commits to the modern era on the first request it reads and then refuses `initialize` with -32022. `_full_policy` already recovers by probing once more, but only when `attempt == 0`.
  - `initialize()` has no timeout of its own; the whole connect is under `_connect_once`'s `asyncio.timeout(self.timeout_seconds)`, and the spawn (the sandbox included) is inside that block.
- The editor does not change in this leg. Leg 2 reads the `protocol_fallback` key this leg stores.

## Inputs
- Branch `sortie/19-local-mcp-servers-newest-protocol`, cut from `main` at `032f27cc`.
- `the_one/mcp/_negotiate.py`, `_era.py`, `client.py`, `__init__.py`; `the_one/interfaces/web/api.py`; `tests/test_mcp_negotiate.py`, `tests/test_mcp_negotiation_fallback.py`; `tests/fixtures/mcp/hello_server.py`.
- `mcp==2.3.0` in the repo venv.

## Outputs
- The patient probe, the outcome object, the era count, the client property, the stored key and its deletes, a start-delay option on the stdio fixture, tests, and documents, as listed under Files Affected.
- No change to any file under `the_one/interfaces/web/static/`.

## Acceptance Criteria
- [ ] **AC1 (signature, and nothing changes without a deadline).** `negotiate(session, *, remembered, patient_until=None, outcome=None, clock=None) -> str`. With the three new keywords absent, every existing test in `tests/test_mcp_negotiate.py` passes unmodified, the SDK parity test included.
- [ ] **AC2 (what "no answer" is, and only with a deadline).** The "no answer" verdict exists only when `patient_until` is not `None`. Then a probe got no answer when `send_discover` raised `MCPError` with code `REQUEST_TIMEOUT` and at least `PROBE_NO_ANSWER_FLOOR_SECONDS` (a named constant, 1.0, in `the_one/mcp/__init__.py`) passed on `clock` between sending it and the error, or when the probe was cut off by the deadline (AC3). An `MCPError` with code `REQUEST_TIMEOUT` that arrives sooner than the floor is an ordinary error. With no deadline (every HTTP connect, and a local-command connect whose limit is at or below the reserve) no probe is ever "no answer": the fallback is never set and the era memory behaves exactly as today, a timed-out probe included.
- [ ] **AC3 (the re-send).** With a deadline given: while the last probe got no answer and `clock()` is before the deadline, the probe is sent again at the same version. Each re-sent probe (every probe after the first) is bounded by the time left to the deadline, and the bound is armed only when that time is greater than zero; its expiry counts as no answer, ends the window unconditionally (the loop does not read the clock again to decide), and is told apart from any other timeout or cancellation, which propagate unchanged. The re-send is an inner loop: it never changes or consumes the policy's `attempt` counter.
- [ ] **AC4 (after the window, today's path).** A no-answer once the deadline has passed takes the existing path for an `MCPError` from discover (the 401-record check, then `session.initialize()`, with the existing handling of an `initialize` refused with -32022). An instant -32001 with a deadline sends exactly one probe and falls back.
- [ ] **AC5 (recovery is kept).** A scripted session whose probes get no answer until the deadline, whose `initialize()` is then refused with -32022 listing a modern version, and whose next probe answers, ends on the modern revision with the fallback not set (the "last probe got no answer" fact belongs to the last probe and is carried across the policy's `continue`; the answered probe clears it), and at the client level the era count is reset.
- [ ] **AC6 (the outcome).** `_negotiate.py` defines a small public class (`NegotiationOutcome`, one attribute `fallback: str | None`, default `None`). When an `outcome` is passed, the policy sets `fallback = "no_answer"` if, and only if, a deadline was given, the last probe got no answer and the session's final revision is a handshake revision; otherwise it sets it to `None`.
- [ ] **AC7 (the client).** `MCPClient._connect_once` passes `patient_until` only when `self.source.type == "stdio"` and `timeout_seconds` is a real number (`int` or `float`, not `bool`, not `None`) greater than `HANDSHAKE_RESERVE_SECONDS` (a named constant, 10, in `the_one/mcp/__init__.py`, read at connect time through the module, as `_HANDSHAKE_OFFER_VERSION` is). The deadline is the loop time read immediately before the existing `async with asyncio.timeout(self.timeout_seconds)` plus `timeout_seconds - HANDSHAKE_RESERVE_SECONDS`. In every other case `patient_until` is `None`. `MCPClient.negotiation_fallback` is a read-only property: reset to `None` in `connect()` after the already-connected guard and before `_connect_once` (a refused second `connect` must not wipe a live connection's value), and set from the outcome at the commit point beside `self._protocol_version = negotiated`, after the version and capability gates. A failed connect therefore leaves it `None`. No caller opts in: the pool's clients, the Test routes and the agent Test route get it through `_connect_once`.
- [ ] **AC8 (the era memory).** `_era.py` holds a per-source count of consecutive no-answer fallbacks behind one function the client calls in place of today's `remember_era` call (the client passes the revision and whether the connect was a no-answer fallback, which by AC2 is only ever true for a connect that had a deadline). A no-answer fallback raises the count; while the count is below 2 it also removes any revision already remembered for the source (the count is kept), so `era_for` returns `None`; when the count reaches 2 the handshake revision is remembered. Any other result resets the count and remembers the revision as today. `forget_era` clears the count as well as the revision (so a failed connect between two fallbacks means they are not "in a row"); `_clear_for_test` clears both maps. Nothing is recorded when `record_era` is false. `remember_era` and `era_for` keep working for their other callers and tests.
- [ ] **AC9 (the stored key, local-command servers).** `api.py::_build_and_test_stdio_mcp` writes `protocol_fallback: "no_answer"` in the same `merge_cache` call as `protocol_version` when the client reports it, and otherwise deletes the key in that same call (`delete=("protocol_fallback",)`). It reads the client's property inside the `async with MCPClient(...)` block, beside `negotiated_protocol_version`, through one helper that returns `"no_answer"` only when the attribute exists and equals that string, and `None` otherwise (a fake client with no such attribute, or a mock that returns a mock, never writes a key). When `cache_write == "none"` nothing is written, as today.
- [ ] **AC10 (the key cannot go stale).** `api.py::_build_and_test_no_auth_mcp` and `::_connect_with_tokens` delete `protocol_fallback` in their cache write (no client read). `update_mcp_source`'s server-changed rule drops `protocol_fallback` together with `last_check` and `auth_posture`.
- [ ] **AC11 (the fixture).** `tests/fixtures/mcp/hello_server.py` accepts `--start-delay=<seconds>`: in `--stdio` mode it sleeps that long before it serves anything, and combines with `--legacy-only` and `--drop-discover`. The module docstring documents it.
- [ ] **AC12 (a slow server ends modern).** With the real fixture started later than the SDK's probe timeout and inside the window (both shortened by patching, see Verification), `MCPClient.connect()` ends on `2026-07-28`, `negotiation_fallback` is `None`, a tool call works, and more than one probe was sent.
- [ ] **AC13 (a real fallback is recorded).** With the real fixture run `--legacy-only` and started later than the window, the connect ends on the handshake revision with `negotiation_fallback == "no_answer"`; through the Test route the stored `_cache` holds `protocol_fallback: "no_answer"` beside `protocol_version`; a later Test against the same source with a prompt start removes the key.
- [ ] **AC14 (second chance, then memory).** For one source id with `record_era` true: after the first no-answer fallback `era_for(id)` is `None` and the next connect probes again; after a second no-answer fallback in a row the handshake revision is remembered and the next connect sends no probe; a connect that ends modern in between resets the count.
- [ ] **AC15 (a prompt server is no slower).** A real dual-era fixture with no delay sends exactly one probe and stores no key; a real `--legacy-only` fixture with no delay answers the probe with an error at once, falls back with one probe and `negotiation_fallback` is `None` (an error answer is not "no answer"), and its revision is remembered at once.
- [ ] **AC16 (HTTP is unchanged).** Every HTTP test in `tests/test_mcp_negotiation_fallback.py` passes unmodified; a test shows that a `streamable-http` client's connect calls `negotiate` with `patient_until=None`; and a test shows that an HTTP source whose single probe times out after **longer than the floor** (faked or with the floor patched below the probe timeout; the existing `drop` tests time out at 0.5 s, under the 1.0 s floor, so they do not prove this) ends with `negotiation_fallback` `None` and its handshake revision remembered at once.
- [ ] **AC17 (the test that changes meaning).** `test_stdio_silent_drop_falls_back_and_second_connect_skips_discover` is rewritten in place (renamed to say what it now proves; not deleted and re-added), on the same apparatus it uses today, `--legacy-only --drop-discover` with no start delay and a shortened window: the first connect falls back after the window with the fallback recorded and more than one probe sent; the connect after it probes again; the connect after that second fallback sends no probe. Three connects in about ten seconds of wall time, not sixty.
- [ ] **AC18 (documents).** Updated: the `_negotiate.py` module docstring (branch map rows for the re-send and for the recovery after a no-answer window; the new keywords), the `_era.py` module docstring (it describes one map today), a comment on each new constant, `the_one/agents.md` "MCP F2 Client Foundation" (the negotiation paragraph: its sentence "one that silently ignores discover costs up to the 10 s discover timeout, once per run per source" changes for local-command servers; the count rule; the stored key; the parity-scenario count if it changes), `the_one/mcp/README.md`'s negotiation section, and the "Automatic protocol negotiation" passage of `CLAUDE.md`.
- [ ] **AC19 (gates).** `THE_ONE_TEST_NETNS=1 make test-unit` is green with the expected skip count; `ruff check` and `ruff format --check` are clean on `the_one/ tests/ scripts/ evals/`; the `library` and `mcp-connection` browser lanes are green.

## Verification Steps
- AC1: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_mcp_negotiate.py -x --timeout 30` before adding any test: all pass with the existing test bodies untouched (`git diff` of that file shows additions only).
- AC2 to AC6: new scripted tests in `tests/test_mcp_negotiate.py`, with a fake clock passed as `clock` and scripted sessions whose `send_discover` advances the fake clock and raises or returns at once. These tests do not sleep and no real timer fires in them (a bound armed with a large fake "time left" around a probe that returns at once is cancelled on exit). One exception, for AC3's bound and falsification 3: a scripted probe that really blocks (`await asyncio.sleep(3600)`) with a time left of about 0.05 s, so the real bound fires; it shows the cut-off ends the window even though the fake clock did not move. Include: repeated no-answers until the deadline then an answer (probe count, `attempt` untouched); the era function and count in `tests/test_mcp_era.py`.
- AC7, AC12 to AC17: tests with the real stdio fixture in `tests/test_mcp_negotiation_fallback.py` (or a sibling file if that reads better). `_connect_list_echo` hard-codes `timeout_seconds=30`, so these tests build their own client or the helper gains a parameter. To keep them fast, shorten four things together: `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` (about 0.5), `the_one.mcp.PROBE_NO_ANSWER_FLOOR_SECONDS` (about 0.2, below the probe timeout), `the_one.mcp.HANDSHAKE_RESERVE_SECONDS` (3 or 4) and the client's `timeout_seconds` (about 8; for the route test patch `the_one.mcp.MCP_DEFAULT_TIMEOUT_SECONDS`). Patching the SDK constant alone does not shorten the window. Each spawn of the fixture costs 0.7 to 1.5 s of interpreter start-up before any delay, more on a loaded host, so leave two seconds of slack: window + start-up + delay + handshake must stay under `timeout_seconds`.
- Which apparatus for which criterion: `--start-delay` only for AC12 (a delay of about 1 s, inside the window) and AC13 (a delay of about the window plus 1.5 s, with `--legacy-only`). AC14 and AC17 use `--legacy-only --drop-discover` with **no** delay: the window passes with the server up, which proves the count and the memory at a third of the cost (every connect spawns the fixture again and would pay a delay again). Expect the real-fixture tests to add about 25 to 35 s to the unit tier in total; say the measured figure in the flight log.
- AC13's route part and AC9/AC10: in the API test files that already cover these writers (`tests/test_mcp_stdio_test_connect.py`, `tests/test_mcp_test_connection_negotiation.py`, `tests/test_mcp_connection_reset.py` or the file that covers `update_mcp_source`'s cache rule). At least one route test uses the real client and the real fixture; the fake-client tests stay unmodified and green.
- Falsification, each by editing the mechanism out, seeing the named test fail, and editing it back (report yes or no for each):
  1. the floor check in AC2 removed → the instant -32001 test (AC4) fails (it would loop or send more than one probe);
  2. the re-send written to consume `attempt` → the recovery test (AC5) fails;
  3. the bound on re-sent probes removed → a test that the last probe ends at the deadline, not a full probe timeout after it, fails;
  4. the count rule replaced by "remember at once" → AC14 fails;
  5. the delete in the stdio writer removed → AC13's "a later Test removes the key" fails.
- AC19: the unit tier once at the end; then `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane library` and `--lane mcp-connection`, one at a time, never while another test run is on the host.

## Implementation Guidance

1. **Before editing, re-run the two consumer searches** recorded in the flight's Prerequisites (`negotiate(`, `DISCOVER_TIMEOUT_SECONDS`, `--drop-discover`, `remember_era(`, and exact pins of a source's `_cache` keys in `tests/`), and say in the flight log if anything new turned up.

2. **Constants** in `the_one/mcp/__init__.py`: `HANDSHAKE_RESERVE_SECONDS = 10` and `PROBE_NO_ANSWER_FLOOR_SECONDS = 1.0`, each with a one-line comment that says what it bounds. `the_one/mcp/__init__.py` imports `client`, which imports `_negotiate`, so `_negotiate.py` must not import the floor by name at module level (a circular import, and tests could not patch it): read it at call time inside the helper (`from the_one import mcp as …`), as `client.py` reads `_HANDSHAKE_OFFER_VERSION`.

3. **The policy** (`_negotiate.py`).
   - Add `NegotiationOutcome` and the three keywords. `clock` defaults to the running loop's `time`.
   - Replace only the line `raw = await session.send_discover(version)` inside the existing `try` of `_full_policy` with a call to a helper; the per-attempt 401 baseline above it and the `except MCPError as e:` body below it stay as they are, apart from recording the helper's verdict. The helper's contract in one line: it returns the raw result or raises the last `MCPError`, and reports whether the last probe got no answer. It sends the first probe unbounded by the policy (it has the SDK's own timeout), which keeps the no-deadline path identical; then, with a deadline, it loops per AC2 and AC3.
   - For a deadline cut-off there is no `MCPError` in hand: raise `MCPError(REQUEST_TIMEOUT, "server/discover got no answer before the deadline")`, so the caller's existing `except MCPError` path runs (`e.code` and `e.error.data` both work on an `MCPError` built that way).
   - The bound on a re-sent probe: `asyncio.timeout` with the time left, armed only when that is greater than zero, and its own expiry told from any other `TimeoutError` or cancellation by the context manager's `expired()`, so the connect's outer timeout and a caller's cancellation pass through untouched. Cancelling `send_discover` this way is safe (the SDK re-raises the cancellation and removes the waiter; the outer connect timeout already does the same). After an expired bound, stop: do not read the clock again to decide.
   - Thread "the last probe got no answer" to the end of the policy and set `outcome.fallback` only after the final revision is known (AC6). The remembered-handshake shortcut in `negotiate` sends no probe and reports no fallback; when it falls through to the full policy the same rules apply.
   - The 401 record does not exist for stdio sessions; do not add a branch for it.
   - Keep imports to public SDK names; the guard test bans `from mcp.client`.

4. **The era memory** (`_era.py`): one new function for the client's use (for example `record_result(source_id, version, *, no_answer)`) implementing AC8, the count map, and the clears. Keep the module a leaf (standard library only).

5. **The client** (`client.py`): compute the deadline immediately before the timeout block (AC7's rule); pass `patient_until` and an outcome only when there is a deadline (with none, call `negotiate` as today, so HTTP cannot get the verdict); reset and set the property where AC7 says; replace the `remember_era` call with the new function, passing "no-answer fallback" only from the outcome. `MCPClient.__init__` stores a passed `timeout_seconds` verbatim, so a test can make it `None` (`asyncio.timeout(None)` means no limit): no patience then.

6. **The routes** (`api.py`): the helper and the stdio writer (AC9); the two HTTP writers and the update rule (AC10). `merge_cache` takes `delete=` (an iterable of keys) and applies it after the merge.

7. **The fixture**: parse `--start-delay=<seconds>` beside the other flags and add it to the list that strips flags from `args` (by prefix, as `--legacy-only` is); sleep after the discover middleware is inserted and before `mcp_app.run("stdio")` / the legacy runner. Update the docstring's flag list.

8. **Tests**, then **documents** (AC18), then the gates (AC19). The lint pair before reporting.

9. **Stop and report** rather than widen the leg if: a second `send_discover` misbehaves against the real fixture; the dual-era fixture does not recover to the modern era after a no-answer window; or keeping the no-deadline path identical needs a change to the policy's structure. Those are the flight's divert conditions.

## Edge Cases
- **`timeout_seconds` at or below the reserve**: no deadline; one probe, as today.
- **The server exits while the client waits**: `CONNECTION_CLOSED`, not a timeout; today's path (the connect fails plainly). No re-send.
- **The connect's outer timeout fires during a re-sent probe**: it propagates as today (the connect fails with the existing timeout error); it is never counted as "no answer" and never recorded as a fallback.
- **A caller cancels the connect during the wait**: `CancelledError` propagates; "cancellation is not an era verdict" still holds (no count change, no forget).
- **A failed connect after a no-answer window** (the handshake also fails): `connect` already calls `forget_era`, which now clears the count too.
- **`record_era=False`** (a Test with unsaved changes to the server): the count and the memory are untouched; the property and the stored-key rule still apply as `cache_write` allows.
- **`fresh_negotiation=True`** (every Test): the memory is not read, but the result goes through the same count rule when `record_era` is true.
- **A late answer to an abandoned probe arrives after the handshake**: dropped by the SDK. No handling needed; do not add any.
- **An HTTP source that was a local-command source with a stored key**: the update rule drops the key at the type change; the HTTP writers delete it at the next Test.

## Files Affected
- `the_one/mcp/__init__.py` - two constants
- `the_one/mcp/_negotiate.py` - keywords, the inner loop, the outcome, docstring
- `the_one/mcp/_era.py` - the count and the result function
- `the_one/mcp/client.py` - the deadline, the outcome, the property, the era call
- `the_one/interfaces/web/api.py` - the helper, three cache writers, the update rule
- `tests/fixtures/mcp/hello_server.py` - `--start-delay`
- `tests/test_mcp_negotiate.py`, `tests/test_mcp_negotiation_fallback.py` and the API test files named under Verification - new and rewritten tests
- `the_one/agents.md`, `the_one/mcp/README.md`, `CLAUDE.md` - documents
- `sorties/19-local-mcp-servers-newest-protocol/flight-log.md` - the leg's entry

## Citation Audit

Checked against the working tree at `c78cbb5c`.

- `the_one/mcp/_negotiate.py::_full_policy` - one `await session.send_discover(version)` inside `for attempt in range(2)`; `except MCPError` then the 401-record check, the -32022 branches and `await session.initialize()`; the `initialize` -32022 recovery requires `attempt == 0` - verified
- `the_one/mcp/_negotiate.py::negotiate` - `(session, *, remembered) -> str`; a remembered handshake revision calls `initialize()` first - verified
- `the_one/mcp/client.py::_connect_once` - `async with asyncio.timeout(self.timeout_seconds)` wraps the transport enter and `await negotiate(session, remembered=remembered)`; `the_one_mcp` is imported lazily there for `_HANDSHAKE_OFFER_VERSION`; `_era.remember_era(self.source.id, negotiated)` under `if self.record_era` after the gates - verified
- `the_one/mcp/client.py::connect` - `except BaseException` calls `_era.forget_era` when `record_era`; `CancelledError` is re-raised before it - verified
- `the_one/mcp/_era.py` - `_ERAS` dict, `era_for`, `remember_era`, `forget_era`, `_clear_for_test`; standard library only - verified
- `the_one/mcp/__init__.py` - `MCP_DEFAULT_TIMEOUT_SECONDS = 30`, read in `MCPClient.__init__` when `timeout_seconds` is the default - verified
- `the_one/interfaces/web/api.py::_build_and_test_stdio_mcp` - one `repo.merge_cache(source_id, {...})` with `protocol_version`, under `if cache_write != "none"` - verified
- `api.py::_build_and_test_no_auth_mcp`, `::_connect_with_tokens` - each has one `merge_cache` that writes `protocol_version` - verified
- `api.py::update_mcp_source` - `server_changed` keeps every `_cache` key except `last_check` and `auth_posture` - verified
- `the_one/db/repositories.py::merge_cache` - `(source_id, fields, delete=())`; deletes after the merge - verified
- `tests/test_mcp_negotiation_fallback.py::test_stdio_silent_drop_falls_back_and_second_connect_skips_discover` - patches `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` to 0.5, runs `--legacy-only --drop-discover`, asserts one probe and that the second connect sends none - verified
- `tests/fixtures/mcp/hello_server.py` (main) - flags are filtered from `args` by prefix or membership; `--stdio` runs `mcp_app.run("stdio")` or `anyio.run(_run_legacy_only, ...)` - verified
- `mcp/client/session.py::send_discover` (mcp 2.3.0) - `opts["timeout"] = DISCOVER_TIMEOUT_SECONDS`, `cancel_on_abandon: False`; `mcp.types.REQUEST_TIMEOUT == -32001`; a late answer is dropped by the dispatcher - verified by the Architect's reading of the SDK, not re-read here
- `mcp/server/runner.py::serve_dual_era_loop` - the first request decides the era; a modern connection refuses `initialize` with -32022 - verified by the Architect's reading, not re-read here

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
