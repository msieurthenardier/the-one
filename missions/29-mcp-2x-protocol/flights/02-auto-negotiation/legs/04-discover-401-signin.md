# Leg: discover-401-signin

**Status**: completed
**Flight**: [Automatic negotiation of protocol 2026-07-28](../flight.md)

## Objective
A 401 on the `server/discover` probe means "sign-in required", not "this server is older". `negotiate()` stops and lets the existing sign-in translation raise `MCPAuthRequired`, instead of falling back to `initialize()`. As a result, a server that only speaks 2026-07-28, requires sign-in, and rejects `initialize` with 400 gets a sign-in prompt instead of a slow, generic failure.

The leg also corrects the latency wording in `the_one/agents.md`.

## Context
- **Found at leg 3's landing** (flight log, `### auto-negotiation-api` deviations; FD note).
  - Today `negotiate()` falls back to `initialize()` on any `MCPError` from discover except -32022. That mirrors the SDK's `negotiate_auto`.
  - With no auth provider attached (the pool's first connect, or Test connection's no-auth path), a discover answered 401 falls back.
  - If `initialize()` is then answered 400, the last MCP-POST status is 400. Flight 1's last-status rule then no longer sees a sign-in requirement.
  - The user gets a generic `MCPConnectionError`, observed after the 30 s connect budget, instead of `MCPAuthRequired`.
- **This is a deliberate departure from SDK parity.** It is the-one's sign-in detection reading its own record, which the SDK has no equivalent of. With no record present (stdio, mock sessions), the behaviour is unchanged, so the parity scenarios in `tests/test_mcp_negotiate.py` are unaffected.
- **With a provider attached**, the SDK's OAuth flow runs inside the discover request (401 → sign-in → retry), so no `MCPError` reaches `negotiate` from a 401 that the flow handled. This change only affects the no-provider path.

## Inputs
- Legs 1-3 landed, uncommitted, in the working tree. Unit suite: 6216 passed, 12 skipped.
- `the_one/mcp/_negotiate.py::negotiate` and `the_one/mcp/_signin_record.py::saw_401_since` / `auth_record_for` (added in leg 2).

## Outputs
- `the_one/mcp/_negotiate.py`, tests, `the_one/agents.md` (and `the_one/mcp/README.md` if it repeats the policy), and a flight-log entry.

## Acceptance Criteria
- [x] AC1:
  - Before each `send_discover` call, `negotiate()` takes the sign-in record's sequence number, via `auth_record_for(session)`. A record of `None` means "nothing to check".
  - When discover raises an `MCPError` (other than the -32022 handling) and `saw_401_since(record, that_seq)` is true, `negotiate()` re-raises that `MCPError` instead of falling back. `connect`'s classifier, row 2, then raises `MCPAuthRequired`.
  - A code comment states the deliberate departure from `negotiate_auto` and why.
- [x] AC2: real-fixture tests, using `Auth401Wrapper` / `tests/_mcp_signin_helpers.py::serve_asgi`.
  - (a) discover 401, then `initialize` 400 (no provider) → `MCPAuthRequired` with the `resource_metadata` URL, raised promptly (well under the connect budget).
  - (b) discover 401, then `initialize` 401 → `MCPAuthRequired` (unchanged).
  - (c) discover 400 or 404 with no 401 → still falls back to the handshake (unchanged).
  - The existing `tests/test_mcp_signin_detection.py::test_connect_discover_401_then_initialize_ok_connects_on_the_handshake` changes expectation: a discover 401 now yields `MCPAuthRequired`. Rename it to match, and log it as a changed expectation with the reason.
- [x] AC3:
  - The parity tests in `tests/test_mcp_negotiate.py` still pass.
  - A new unit test with a record showing a 401 asserts the re-raise.
  - A new unit test with a record of `None` asserts the SDK-parity fallback.
- [x] AC4:
  - `the_one/agents.md`'s negotiation bullet (~1066) states the 401-on-discover rule.
  - Its "Trade-offs" wording is corrected. Fallback from a handshake-only server that answers discover with an error costs milliseconds. A server that silently ignores discover costs up to the 10 s discover timeout, once per run per source.
  - `the_one/mcp/README.md` is updated if it repeats either point.
- [x] AC5: the following pass:
  - `make test-unit` (plain mode);
  - `pytest -m requires_bwrap -x --timeout 120`;
  - `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`;
  - `tests/test_mcp_test_connection_negotiation.py`, `tests/test_mcp_signin_detection.py` and `tests/test_mcp_negotiation_fallback.py` specifically.

  The flight log gets a `### discover-401-signin` entry, and the leg status goes to `landed`.

## Design-Review Resolutions (authoritative where they differ from the sections above)

The leg's Developer design review returned "approve with changes" (2026-10-12). The FD's decisions follow.

1. **Deferral, not a hard stop.**
   - **The problem.** A hard stop would break a working server shape: discover gated behind sign-in, `initialize` public. `tests/test_mcp_signin_detection.py::test_connect_discover_401_then_initialize_ok_connects_on_the_handshake` pins that shape, and it stays **unchanged and passing**.
   - **The rule.** On a discover `MCPError` where the record shows a 401 since this attempt's baseline, `negotiate()`:
     - captures the record's `resource_metadata` value at that moment;
     - still tries `initialize()`.
   - **The outcomes:**

     | `initialize()` result | What happens |
     |---|---|
     | Succeeds | Today's behaviour: the connection stays on the handshake era. |
     | Raises an `MCPError` | `negotiate()` raises a module-level `DiscoverSignInRequired(resource_metadata_url)` (a small exception in `_negotiate.py`). |
     | Raises anything else | It propagates, as today. |

   - **Why a marker exception.** `initialize`'s 400 overwrote the record's `last_status`, so the classifier can't see the 401 any more. `connect`'s `_classify_failure`, row 2, therefore also matches `DiscoverSignInRequired` and raises `MCPAuthRequired(resource_metadata_url=<captured>)`.
   - **The AC2 test changes:**
     - (a), discover 401 then `initialize` 400: assert `MCPAuthRequired` **and** the captured `resource_metadata` URL. Drop the "promptly" clause; the failure is already prompt without the fix.
     - Add (d), discover 401 then `initialize` 200: it still connects on the handshake. This is the existing test, unchanged.
   - **The doc comment** states that this departs from `negotiate_auto` only when the sign-in record shows a 401 on discover.
2. **Order inside the discover `except MCPError` block.** The 401 check comes **first**, before the -32022 branch. The record is the authority, even if a 401 response's JSON-RPC body carries -32022. A test uses `Auth401Wrapper` with a JSON-RPC body on discover.
3. **A fresh baseline per attempt.** Inside the loop, take `baseline = record.seq if record else 0` immediately before **each** `send_discover`, including the second attempt after a -32022 re-probe. A 401 from attempt 0 must not count for attempt 1.
4. **Unit tests need a registered record.**
   - `_AUTH_RECORDS` is a `WeakKeyDictionary` keyed by the session. The test registers an `AuthRecord` for its fake session, and the scripted `send_discover` bumps `seq` and sets `last_status = 401` during the call.
   - **Negative case:** a pre-seeded 401 with an unchanged `seq` must **not** trigger the deferral path.
   - **Record of `None`:** the SDK-parity fallback, unchanged.
5. **With a provider attached.** A 401 that the OAuth flow could not resolve (for example, a retry after sign-in still answered 401) reaches `negotiate` as an `MCPError` with a 401 in the record. It now ends as `MCPAuthRequired` with `consent_url=None`, and the caller re-runs sign-in. Add one test using the OAuth stub. Correct the Context line that says no `MCPError` reaches `negotiate` from a 401 the flow handled: one the flow *handled* doesn't, but one it *could not resolve* does.
6. **The 30 s observation.**
   - It was not reproduced: a 400 on `initialize` fails at once with a generic error. Remove the "observed after the 30 s connect budget" and "slow" claims from the Objective and Context. The defect is the **wrong outcome** (no sign-in prompt), not slowness.
   - Leg 3's 30 s probably came from its layered wrapper or the dual-era fixture refusing `initialize` after committing to modern. It is out of scope; don't chase it unless it reproduces cleanly, in which case note it for a squawk.
7. **Docs.** Update `_negotiate.py`'s module docstring and branch table, which currently say the loop mirrors the SDK. Make the same AC4 corrections to `the_one/agents.md` (~1066) and to `the_one/mcp/README.md` if it repeats them.

## Verification Steps
- AC1-AC3: run the named tests.
- AC4: read the diff.
- AC5: run the commands and record their exit codes in the flight log.

## Edge Cases
- **The re-probe after -32022** keeps its own logic; the 401 check applies to each `send_discover` attempt.
- **The DD2 shortcut** (`initialize()` first for a remembered handshake era) is unchanged. It already lets a 401 propagate.
- **Test connection's DD9 fall-through.** A server that 400s the probe's bare `initialize` but 401s discover now raises `MCPAuthRequired` from the no-auth path. That path's fall-through then returns the sign-in sentinel and goes to Phase B's discover-driven sign-in. Confirm `tests/test_mcp_test_connection_negotiation.py`'s AC2(b) test still passes. Leg 3 built its wrapper to 401 both methods; it may now be simplified to 401 only discover, as leg 3's resolution 5(b) originally intended. Note whichever is done.

## Files Affected
- `the_one/mcp/_negotiate.py`
- `tests/test_mcp_negotiate.py`, `tests/test_mcp_signin_detection.py`, `tests/test_mcp_test_connection_negotiation.py`
- `the_one/agents.md`, `the_one/mcp/README.md`
- The flight log

## Citation Audit
Checked against the working tree:
- `the_one/agents.md:1066`: the negotiation bullet, including "about 1 s worst case through the failed-discover timeout", which is wrong; the measured fallback is milliseconds, and up to 10 s only for a silent drop.
- `_negotiate.py` and `_signin_record.saw_401_since`: added in leg 2 (flight log, checkpoint 2a).

**Risk tier: HIGH.** The leg changes sign-in detection (a security-sensitive surface) and departs from SDK parity. A quick Developer design review comes first.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
