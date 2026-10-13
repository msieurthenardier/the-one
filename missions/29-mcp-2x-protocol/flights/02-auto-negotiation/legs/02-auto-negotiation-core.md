# Leg: auto-negotiation-core

**Status**: completed
**Flight**: [Automatic negotiation of protocol 2026-07-28](../flight.md)

## Objective
Switch `MCPClient.connect` from `session.initialize()` to automatic negotiation, behind one seam (DD1), and add in-memory era memory (DD2).

- **Session reads (DD3, DD4):** server metadata is read the same way in both eras, with the serverInfo de-dup. The version gate accepts the modern revision, and the pinned constant is renamed, with re-pinned tripwires.
- **Input-required fixture (DD8):** a real modern-era fixture for the input-required case.
- **Older-revision fixtures (DD13):** fixtures that speak only older revisions, so every older revision is proven on a real server, with fallback and second-connect latency proven structurally.

When this leg lands, `hello_server` and the self-configuration loopback report 2026-07-28, and every legacy-only fixture falls back to its own revision.

## Context
- **The flight spec is the design.** Read `../flight.md` in full first, especially DD1, DD2, DD3, DD4, DD8 and DD13. The DD5 matrix as amended was implemented in leg 1. Where this file and the flight spec disagree, the flight spec wins: report it in the flight log.
- **Leg 1 already landed** (uncommitted, same tree). Read its flight-log entry first. It added:
  - `MCPClient._classify_failure` with the matrix;
  - `_owner_task` (set at `connect` ~492, cleared at `disconnect` ~734);
  - `the_one/mcp/_era.py` with `era_for` / `remember_era` / `forget_era` / `_clear_for_test`, and an autouse clear fixture;
  - `TOKEN_FAILURE_MARKERS` in `errors.py`;
  - the stale-token clear helper in `api.py`;
  - `allow_input_required=True` in `call_tool`.

  Do not regress any of it.
- **Out of scope (leg 3, `auto-negotiation-api`):**
  - `api.py`'s probe fall-through (DD9);
  - the flow drivers' header (DD10);
  - era clearing on update, delete and Reset in `api.py`;
  - the probe docstring;
  - the negotiation docs in `the_one/agents.md`, `the_one/mcp/README.md` and `CLAUDE.md`.

  This leg renames the constant everywhere it is referenced (including `transports/streamable_http.py:260` and its docstring mention at `:235`), but makes no behaviour change in `api.py`. `fresh_negotiation=True` at the three Test-connection construction sites (`api.py:3321, 3416, 3644`) IS in this leg: it is a constructor keyword the client must honour, and those sites are where it is passed.
- **Evidence in the flight log:**
  - Reconnaissance Report Part B (B1-B4, B6, B8), and both design-review cycles.
  - Probes: `scratchpad/f2probe/` (`probe_legacy.py`, `probe_http.py`, `probe_drop.py`, `probe_ir.py`) and `scratchpad/archprobe/oldrev.py`. Read them; don't run them against the dev instance.

## Inputs
- Leg 1 landed in the working tree. Unit suite: 6117 passed, 12 skipped, 0 failed (plain mode). `requires_bwrap`: 41 passed, 3 skipped.
- Installed `mcp` 2.3.0 (`.venv`), whose `mcp/client/_probe.py::negotiate_auto` is the reference policy.

## Outputs
- `the_one/mcp/_negotiate.py` (new), `the_one/mcp/client.py`, `the_one/mcp/__init__.py` (rename), `the_one/mcp/transports/streamable_http.py` (rename only), and `the_one/interfaces/web/api.py` (only `fresh_negotiation=True` at the three Test-connection sites).
- Fixtures: `tests/fixtures/mcp/hello_server.py` (`--legacy-only[=<revision>]`, a silent-drop middleware switch, a pipe-close switch, and an input-required tool), plus an HTTP legacy wrapper beside `tests/fixtures/mcp/asgi_401.py`.
- Tests: described in the acceptance criteria.
- A flight-log `### auto-negotiation-core` entry with every changed test expectation and its reason.

## Acceptance Criteria
- [x] AC1 (DD1, the policy): `the_one/mcp/_negotiate.py::negotiate(session, *, remembered) -> str` follows `negotiate_auto`:
  - `send_discover(LATEST_MODERN_VERSION)` is called at most twice; the version is read at call time.
  - -32022 with a mutual modern version re-probes at that version once.
  - -32022 whose `supported` parses and lists no handshake version raises (DD5 row 3 then maps it).
  - -32022 with unparseable data falls back to `initialize()`.
  - Any other `MCPError` falls back to `initialize()`.
  - An `initialize()` that itself answers -32022 re-probes discover once, at a mutual version.
  - Exceptions that are not `MCPError` propagate.
  - A discover result that fails validation, or names no modern version, falls back to `initialize()`.
  - Otherwise `session.adopt(result)` is called.
  - It returns `session.protocol_version` and imports only public SDK names (no `mcp.client._probe`).
  - Unit tests drive every branch against an in-memory or mock session; the parity cases are named after the SDK branches they mirror.
- [x] AC2 (DD1/DD2, the shortcut): when `remembered` is in `HANDSHAKE_PROTOCOL_VERSIONS`, `negotiate` calls `initialize()` directly.
  - If that fails with an `MCPError` and `_signin_record.auth_record_for(session)` shows no 401 since the sequence taken just before it, `negotiate` runs the full policy in the same call. A record of `None` means no 401.
  - A shortcut `initialize()` answered 401 propagates. `connect`'s row 2 then raises `MCPAuthRequired`. A test with a real 401 fixture proves this.
- [x] AC3 (DD2, era memory):
  - `MCPClient.__init__` gains `fresh_negotiation: bool = False`.
  - `connect` passes `remembered = None if self.fresh_negotiation else _era.era_for(self.source.id)` to `negotiate`.
  - After a successful connect it calls `remember_era(source.id, session.protocol_version)`, and on any failed connect it calls `forget_era` (leg 1 already forgets on a mid-session -32022).
  - The three Test-connection sites pass `fresh_negotiation=True`. The pool and the self-configuration path use the default.
  - Leg 3 adds the body-override exception (a Test with an override records nothing). Leave a `TODO(leg3)`-free seam: a keyword `remember: bool = True` on the client, which those sites can pass, is acceptable. Note what you chose in the flight log.
- [x] AC4 (DD3): `connect` reads `_meta` from `(session.initialize_result or session.discover_result).meta`, dumped by alias, with `mcp.types.SERVER_INFO_META_KEY` removed, and stores `None` if the result is empty.
  - The mock-session helpers (`tests/test_mcp_client.py::_set_init`, `tests/test_mcp_wire_shapes.py::_fake_session`) set `initialize_result` / `discover_result` explicitly.
  - Tests cover `_meta` in both eras, including the de-dup.
- [x] AC5 (DD4):
  - The version gate accepts `HANDSHAKE_PROTOCOL_VERSIONS + MODERN_PROTOCOL_VERSIONS`.
  - `_PINNED_PROTOCOL_VERSION` is renamed `_HANDSHAKE_OFFER_VERSION` everywhere: `__init__.py:12, 65` and its docstring, `client.py`, `transports/streamable_http.py:235, 260`, `MCPVersionMismatch(pinned=…)` callers, and `tests/test_mcp_client.py:718-737`.
  - The tripwires (`tests/test_mcp_client.py:~44-56`, `tests/test_mcp_wire_shapes.py:102-106`) pin `_HANDSHAKE_OFFER_VERSION == LATEST_HANDSHAKE_VERSION == "2025-11-25"` and `LATEST_MODERN_VERSION == "2026-07-28"`. The `LATEST_PROTOCOL_VERSION != …` assertion is deleted.
  - The real-server expectations that move to "2026-07-28" are updated and logged: `tests/test_mcp_integration.py:79, 170` and `tests/test_mcp_wire_shapes.py:78, 88`.
- [x] AC6 (DD1, mock fixtures): every mock-session fixture used with `patch_transport` (`tests/test_mcp_client.py:176-182` and any others found) gains `send_discover=AsyncMock(side_effect=MCPError(METHOD_NOT_FOUND, …))` and `adopt`, so existing tests keep exercising the handshake path with no `TypeError`. A grep confirms no fixture is missed.
- [x] AC7 (DD8, real fixture): a `hello_server` tool returning `InputRequiredResult(request_state="x")` reaches `MCPClient.call_tool` over a real modern-era connection and raises leg 1's `MCPCallError` with the exact message.
- [x] AC8 (DD13, every older revision): `hello_server.py --legacy-only[=<revision>]` runs 2.3.0's handshake-only `mcp.server.runner.serve_loop`. The fixture process patches `mcp.server.runner.HANDSHAKE_PROTOCOL_VERSIONS = (rev,)` and `LATEST_HANDSHAKE_VERSION = rev`.
  - A parametrized test over 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25 connects a real `MCPClient` over stdio, asserts `negotiated_protocol_version == rev`, lists tools and calls `echo`.
  - 2025-11-25 is also proven over streamable HTTP.
- [x] AC9 (DD13, fallback modes): each mode connects on the handshake.
  - Over stdio: fast error (`--legacy-only`) and silent drop (a server middleware that never answers `server/discover`; the test patches `mcp.client.session.DISCOVER_TIMEOUT_SECONDS` low).
  - Over HTTP: fast 400 with a 1.x-style JSON-RPC body, bare 404, and silent drop, via an ASGI wrapper modelled on `Auth401Wrapper`.
  - The stdio pipe-close mode fails plainly as `MCPConnectionError` (asserted, documented as accepted).
- [x] AC10 (DD13, latency, structurally): for every fallback mode in AC9, a second connect of the same source sends **no** `server/discover`, checked by a spy or a fixture counter. A generous timing bound is applied relative to a plain handshake connect of the same fixture, not an absolute stopwatch.
- [x] AC11 (dual-era, real servers):
  - `hello_server` over stdio and HTTP, and the self-configuration loopback (`tests/test_self_configuration_surface.py`'s real-client tests), now negotiate 2026-07-28. Those tests pass, including caller resolution and refusal text.
  - `tests/test_mcp_signin_detection.py` passes with `server/discover` added to `fail_methods` (~64), and its tests still prove `MCPAuthRequired` on a real 401.
  - The OAuth-stub tests pass (the stub answers an authorized discover with 202, i.e. a fast fallback).
- [x] AC12: the following all pass.
  - `make test-unit` (plain mode), with the skip count explained.
  - `.venv/bin/python -m pytest -m requires_bwrap -x --timeout 120`. The bwrap rejection path now meets discover first; confirm it still surfaces `SandboxError` or the existing translation.
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`.
  - These browser files with `THE_ONE_TEST_NETNS=1` and `-m browser`: `tests/browser/test_mcp_test_connection_button.py`, `tests/browser/test_oauth_modal_flow.py`, `tests/browser/test_studio_mcps_tab.py`, `tests/browser/test_studio_self_configuration_tab.py`.
- [x] AC13: the flight log's `### auto-negotiation-core` entry lists every changed test expectation (with its reason), every new fixture and test file, and the AC3 seam choice. The leg status is `landed`.

## Design-Review Resolutions (authoritative where they differ from the criteria above)

The leg's Developer design review (approve with changes, 2026-10-12) settled the following.

1. **Two passes, with a hard checkpoint between them.**
   - **Pass 2a:** AC1-AC6, the rename and the mock hook (resolution 5). Gate: unit suite green, recorded in the flight log as `#### checkpoint 2a`. The Flight Director reviews the 2a entry before spawning pass 2b.
   - **Pass 2b:** AC7-AC11 (fixtures and real-server tests), then AC12 and AC13.
   - Each pass is a separate Developer spawn on this same leg. Pass 2a leaves the leg `in-flight` and signals `[HANDOFF:review-needed]`; pass 2b lands it.
2. **Where `negotiate` sits.** It replaces only the `await session.initialize()` line inside `connect`'s inner `try`, under the `except* (OAuthFlowError, OAuthTokenError)` arm and before `except RuntimeError`.
   - `negotiate` catches only `MCPError`. OAuth flow errors and exception groups from a discover that triggers the OAuth flow propagate to the `except*` arm unchanged.
   - A -32022 that `negotiate` re-raises reaches the outer generic arm, so `_classify_failure` row 3 applies.
   - **Accepted gap:** `negotiate` raises when `supported` lists no handshake version (the SDK's criterion), but `_shares_no_version` counts handshake plus modern. A -32022 on the re-probe that lists a mutual modern version yields the generic "MCP connect failed: …". That case is accepted; pin it with a unit test.
   - **`UrlElicitationRequiredError` from discover** is an `MCPError` subclass, so it falls back to `initialize()` (SDK parity). Pin it with a one-line test.
3. **Era writes are one gated flag, and forgetting is one wrapper.**
   - `MCPClient.__init__` gets two booleans:
     - `fresh_negotiation: bool = False` — skip the read;
     - `record_era: bool = True` — when False, suppress **both** `remember_era` and `forget_era`.

     Implement `record_era` now, with a unit test that it suppresses both calls, and leave no TODO. Leg 3 passes `record_era=False` for a Test with a body override.
   - Place `remember_era` right after the capability gate passes, next to `_is_alive = True`.
   - Wrap everything after the "already connected" guard so any raise calls `forget_era` (when `record_era`) and re-raises. A `connect()` → `_connect_once()` split or a try/except both work.
   - **Excluded from forgetting:** the already-connected guard (a test asserts it leaves the memory intact) and `asyncio.CancelledError`, since cancellation is not an era verdict.
4. **References corrected.**
   - The third Test-connection `MCPClient` site is `api.py:3686`; leg 1 shifted it from 3644. The other two are `api.py:3321` and `:3416`.
   - The rename covers every `_PINNED_PROTOCOL_VERSION` reference, the docs included (this is mechanical, so it happens in this leg):
     - `client.py:67` (comment), `:424`, `:434` (`_classify_failure`) and `:485-488`;
     - `__init__.py:9, 12, 30-31, 65`;
     - `transports/streamable_http.py:235, 260`;
     - `the_one/mcp/README.md:49, 224-256`;
     - `the_one/agents.md:1050, 1057, 1160`;
     - `tests/test_mcp_client.py:50` and `:718-737`;
     - `tests/test_mcp_wire_shapes.py:102-106`.

     `tests/test_mcp_client.py:451`'s value is unchanged. The hard-coded "2025-11-25" at `api.py:3819, 4686` belongs to leg 3 (DD10). Leave it.
5. **The mock hook is centralised.** `tests/test_mcp_client.py::_set_init` (~134) feeds `mock_session`, `patch_transport` and `tests/test_mcp_failure_matrix.py::_session`. Add `send_discover` (an `AsyncMock` raising `MCPError(METHOD_NOT_FOUND)`), `adopt`, `initialize_result` and `discover_result` **there**, as one edit that covers AC4 and AC6.
   - Also fix the raw sessions that bypass it: `tests/test_mcp_client.py:982` (`bad_session`), which would otherwise pass for the wrong reason via `TypeError`, and `tests/test_mcp_wire_shapes.py:137` (`_fake_session`).
   - Grep for `MagicMock()` sessions that reach `_transport_connect`, not only `patch_transport`.
   - The fake `MCPClient` classes in `test_mcp_stdio_test_connect.py`, `test_mcp_connection_reset.py` and `test_oauth_test_connection_endpoint.py` take `**kwargs`, so they need no change.
6. **AC4 guard.** Read the result with `res = session.initialize_result or session.discover_result`, then `getattr(res, "meta", None)` with an `isinstance(dict)` check, as the existing code does; both results can be `None` on mocks.
   - **Intended change, logged:** the modern-era serverInfo stamp's `version` is `''` where the handshake reports the real version, so a modern server's editor line may show no version. Accepted for this leg; HAT H1 observes it for Sonos.
7. **A shared 401 predicate.** Hoist a pure `_signin_record.saw_401_since(record, baseline) -> bool`, used by both `MCPClient._auth_required_since` and `negotiate`'s shortcut.
8. **Fixture mechanics (pass 2b).**
   - **`hello_server.py` argv flags:** `--legacy-only[=rev]`, `--drop-discover` and `--close-on-discover`. `main()` strips them before the `mode = args[0]` parse, as `--with-naughty-tools` already does.
   - **Legacy mode:** `stdio_server()`, then `low.lifespan(low)`, then `serve_loop(...)`, with `mcp.server.runner.HANDSHAKE_PROTOCOL_VERSIONS` and `LATEST_HANDSHAKE_VERSION` patched to the revision.
   - **Pipe-close is unprobed.** Run a short probe before writing its test. If it doesn't end in a plain `MCPConnectionError`, emit `[BLOCKED:legacy-fixture]`.
   - **HTTP:** reuse and extract `tests/test_mcp_signin_detection.py::_wrapped_asgi` (wrapper → `LifespanManager` → `httpx2.ASGITransport`, set as `sh._test_http_client_override`), for example into `tests/_mcp_signin_helpers.py`. The wrapper intercepts only `server/discover` POSTs and passes `initialize` through to the dual-era app. That proves 2025-11-25 over HTTP, not a handshake-only HTTP server; state this in the test docstring. Assert a clean teardown for the silent-drop mode.
9. **Latency (AC10), structural only.** Spy with `monkeypatch` on `mcp.client.session.ClientSession.send_discover` in the test process; the client is in-process even when the server is a subprocess. The primary assertion is zero calls on the second connect. Drop the relative stopwatch.
10. **Extra tests.**
    - `Auth401Wrapper(fail_methods={"server/discover"})` (discover answered 401, initialize answered 200) connects on the handshake.
    - An end-to-end -32022 through `connect` with no shared version gives `MCPVersionMismatch`.
    - A parity-drift test runs `negotiate` and the SDK's private `negotiate_auto` (imported **in the test only**) against the same scripted fake sessions and compares outcomes, so SDK policy drift fails loudly on upgrade.
    - Rename stale test names and docstrings (for example `..._reports_the_handshake_era_version`).
11. **Timeouts.** All three Test-connection sites use the default `timeout_seconds` (30 s), which fits the 10 s discover timeout. Don't lower them.

## Verification Steps
- AC1-AC11: the named tests pass, and each new test is named in the flight log.
- AC12: run the commands and record their exit codes in the flight log.
- AC1: `grep -n "mcp.client._probe" the_one/` returns nothing.

## Implementation Guidance
1. **`_negotiate.py` plus its unit tests (AC1, AC2)**, with no wiring yet. Mirror `negotiate_auto` branch by branch and keep a comment table mapping each branch to its SDK line.
2. **Mock fixtures (AC6)**, before wiring, so the suite doesn't explode with `TypeError`.
3. **Wire into `connect` (AC3-AC5)**: era memory, `fresh_negotiation`, `_meta`, the gate and the rename. Run `test_mcp_client`, `test_mcp_wire_shapes`, `test_mcp_integration`, `test_mcp_signin_detection`, `test_self_configuration_surface`, `test_mcp_pool` and `test_mcp_failure_matrix`. **Checkpoint: unit suite green.**
4. **Fixtures and real-server tests (AC7-AC11).** Write a stdio and an HTTP test for each mode.
5. **Full verification (AC12).** Then the flight-log entry (AC13).

## Edge Cases
- **Sign-in baseline across fallback.** `connect`'s sign-in baseline is 0 for the whole negotiation. A discover answered 401 followed by an initialize answered 401 still gives `MCPAuthRequired`. A discover answered 4xx followed by an initialize answered 200 does not.
- **Provider attached.** The OAuth flow now starts from the discover POST. That is fine, and is covered by the existing OAuth-stub tests.
- **The HTTP silent-drop fixture.** The abandoned discover POST stays in flight until the transport closes (`cancel_on_abandon=False`), so make sure the test tears the transport down cleanly.
- **`DISCOVER_TIMEOUT_SECONDS` is a module global read at call time.** Patch it with `monkeypatch` in the test, never at import.
- **The era map is keyed by `source.id`.** Tests that reuse a source id across cases rely on the autouse clear fixture from leg 1.
- **Abandoned stdio processes.** A `--legacy-only` stdio process whose `initialize` is never sent (for example in pipe-close mode) must not orphan. Use the existing stdio transport teardown, and assert no leftover process if the existing tests have that pattern.
- **Stop conditions.**
  - If negotiation against the self-configuration loopback breaks caller resolution in the modern era: `[BLOCKED:selfconfig-modern-caller]`.
  - If 2.3.0's `serve_loop` cannot be made to answer an older revision as `oldrev.py` showed: `[BLOCKED:legacy-fixture]`.

## Files Affected
- `the_one/mcp/_negotiate.py` (new), `the_one/mcp/client.py`, `the_one/mcp/__init__.py`, `the_one/mcp/transports/streamable_http.py` (rename only), `the_one/interfaces/web/api.py` (`fresh_negotiation=True` at three sites only)
- `tests/fixtures/mcp/hello_server.py`, `tests/fixtures/mcp/` (new HTTP legacy wrapper)
- `tests/test_mcp_client.py`, `tests/test_mcp_wire_shapes.py`, `tests/test_mcp_integration.py`, `tests/test_mcp_signin_detection.py`, plus new test files, for example `tests/test_mcp_negotiate.py` and `tests/test_mcp_negotiation_fallback.py`
- The flight log

## Citation Audit
Checked at leg design against the working tree (leg 1 landed, uncommitted):
- `client.py`: `connect` (~459), `_owner_task` set (~492), `session.initialize()` (~531), `_era.forget_era` (~429), `_owner_task = None` in `disconnect` (~734).
- `_era.py`: `era_for` (16), `remember_era` (21), `forget_era` (26), `_clear_for_test` (31).
- `_PINNED_PROTOCOL_VERSION` references: `__init__.py:9, 12, 30-31, 65`; `client.py:424, 434, 488`; `transports/streamable_http.py:235, 260`; `tests/test_mcp_wire_shapes.py:102-106`; `tests/test_mcp_client.py:50` and `:718-737`.
- The SDK side was verified at flight design: `negotiate_auto`, `send_discover`/`initialize`/`adopt`, and `DISCOVER_TIMEOUT_SECONDS` read at call time.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
