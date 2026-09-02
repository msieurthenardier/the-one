# Leg: discord-client

**Status**: completed
**Flight**: [Discord Client](../flight.md)

## Objective

Implement the hand-rolled Discord Gateway v10 + REST client as `the_one/connectors/discord/`, register it as the first production plugin, and prove the whole protocol surface against a fake in-process gateway — no live Discord traffic in this leg.

## Context

- Flight DD-1 (subpackage shape), DD-2 (gateway opcodes + close-code policy + `PermanentConnectorFailure`), DD-3 (REST + rate limiting), DD-4 (envelope translation), DD-8 (fake-gateway fixture), DD-9 (budget ≤1,100 Python for the subpackage).
- Flight 2 landed the contract this plugin fills: `ConnectorPlugin`/`ConnectorClient` Protocols in `the_one/connectors/base.py`, supervised by `ConnectorManager._run` (`the_one/connectors/manager.py`). The stub plugin (`the_one/connectors/stub.py`) is the structural reference — per-account state in a class-level account-id-keyed dict (`StubPlugin._live`).
- The manager owns ALL retry: `_run` loops connect → hold-while-alive → backoff, re-fetching a fresh row via `repo` before every reconnect (rotation fix). The plugin never retries internally.
- `Connector.secrets` reaches the plugin already decrypted (`ConnectorRepository._ciphertext_to_secrets` decrypts on read) — read the bot token from `account.secrets["token"]`; the `encryptor` parameter is unused by this plugin (keep the Protocol signature).
- `Connector.type` Literal already includes `"discord"` (`db/models.py:152`) — no model or schema change. The v19 CHECK constraint already allows it.
- DD-7's `sever_for_test` client hook and the dual-gated test route are **leg 3**, not here — unit-test resume scenarios are driven server-side by the fixture (abrupt close from the fake gateway), which needs no client hook.

## Inputs

- `the_one/connectors/{base,registry,manager,inbound,stub}.py` as landed by Flight 2 (820 lines total).
- `websockets` and `httpx` already in base dependencies (verify in `pyproject.toml`; **no new deps** — mission criterion).
- App lifespan in `the_one/interfaces/web/app.py` — the dual-gated stub-registration block (`app.py:275-280`) and the `ConnectorManager()` start just below it mark the registration site pattern.

## Outputs

- `the_one/connectors/discord/` — new subpackage: suggested `__init__.py`, `_gateway.py`, `_rest.py`, `plugin.py` (file boundaries are the implementer's; budget is the subpackage total).
- `the_one/connectors/base.py` — new `PermanentConnectorFailure(ConnectorClientError)`.
- `the_one/connectors/manager.py` — narrow permanent-failure handling in `_run`/`_connect_once`.
- `the_one/connectors/registry.py` — production `register()` function.
- `the_one/interfaces/web/app.py` — unconditional Discord registration in lifespan.
- `tests/_discord_gateway_fixture.py` — fake gateway (DD-8, shared tests root).
- New unit test file(s), e.g. `tests/test_discord_gateway.py`, `tests/test_discord_rest.py`, `tests/test_discord_plugin.py` (naming free; content pinned below).

## Acceptance Criteria

- [x] **AC-1 Gateway happy path**: against the fake gateway, the client completes hello → identify (intents `GUILDS | GUILD_MESSAGES | DIRECT_MESSAGES | MESSAGE_CONTENT` = 37377) → READY (captures `session_id` + `resume_gateway_url` into the plugin's account-keyed state) → dispatches MESSAGE_CREATE to `on_inbound`; unit-asserted.
- [x] **AC-2 Heartbeat discipline + sequence tracking**: the client persists the last-seen dispatch sequence number `s` in per-account state; every heartbeat payload is `{"op": 1, "d": <last_seq_or_null>}` (fixture asserts the `d` value, not just the opcode); first heartbeat after `jitter * heartbeat_interval`; subsequent beats on the interval; a missed heartbeat-ACK (op 11) closes the socket and lets the connection die (`is_alive()` → False) so the manager reconnects; unit-asserted with a fixture scenario that withholds the ACK.
- [x] **AC-3 Resume path — payload AND address proven**: after an abrupt server-side close (fixture-driven, no close handshake), the NEXT `connect()` sends resume (op 6) with payload `{"token", "session_id", "seq"}` — `seq` = the last dispatch `s` — and the fixture asserts the FULL payload content, not just the opcode. The fixture serves this scenario on TWO listeners (READY on listener A advertises listener B's address as `resume_gateway_url`); the test asserts the resume attempt lands on listener B, so a client that ignores `resume_gateway_url` cannot pass incidentally. On op 9 invalid-session (`d: false`) the client re-identifies on the same connection after Discord's recommended 1–5s random delay (delay injectable/near-zero in tests). All unit-asserted.
- [x] **AC-3b op 7 RECONNECT**: an op 7 frame is handled directly — the client closes the connection promptly (no waiting for Discord's follow-up force-close) and the next connect resumes; fixture-scripted and unit-asserted.
- [x] **AC-4 Close-code policy**: fixture closes with 4004 (and one of 4010–4014) → `connect()` raises `PermanentConnectorFailure`; `manager._run` catches it narrowly, logs, and STOPS retrying (task ends; no backoff loop); any other close code follows the normal reconnect path. The failure marker is recorded in the plugin's account-keyed state, `plugin.doctor()` short-circuits to `status="failed"` with the reason, and `connect()` clears the marker unconditionally at its top (lifecycle rule — the only reset point). All unit-asserted, including a manager-level test that a `PermanentConnectorFailure` listener task terminates while an ordinary failure keeps backing off. **Stated behavior (not an oversight)**: a permanent close code detected MID-SESSION (post-READY, after `connect()` returned) surfaces at the NEXT handshake — the connection dies, `_run` reconnects once, and that handshake re-hits the same close code and raises — i.e. one backoff cycle of latency, accepted deliberately (design review 2026-09-01: the read-loop-signals-`_run` alternative adds machinery for no recovery benefit; the token is equally bad one cycle later). Document this in a code comment at the raise site. Also acknowledged: `_run`'s permanent-failure `return` leaves the `_ListenerEntry` in `self._listeners` — correct today because every recovery path (`update_connector` PUT, rotation restart) calls `stop()` before `start()`; note it in a comment so it doesn't read as a leak.
- [x] **AC-5 `_connect_once` re-raise**: `manager._connect_once` gains `except PermanentConnectorFailure: raise` ahead of its catch-all `except Exception` (`manager.py:217`), and `_run` alone converts it to stop+log; existing manager tests still pass unmodified.
- [x] **AC-6 REST rate limiting**: per-bucket serialization honoring `X-RateLimit-Bucket/Remaining/Reset-After`, the global limit, and 429 `retry_after` with bounded retries — unit-asserted against a mocked httpx transport (no live REST calls). Endpoint helpers cover ~10: Get Gateway Bot, Get Current User, Create Message, Create DM, Get Channel, Get Channel Messages, Trigger Typing, Get Guild Channels (±2 acceptable per flight variations).
- [x] **AC-7 Envelope translation**: MESSAGE_CREATE → `InboundEnvelope` with `is_dm` from channel type, `mentions_bot` from the mentions array containing the bot's user id, `peer_name` from author global/display name, `thread_id` for thread messages; messages authored by the bot itself or ANY bot (webhooks included) are dropped before `on_inbound`; unit-asserted per field and per drop case.
- [x] **AC-8 Protocol conformance**: `DiscordPlugin` structurally satisfies `ConnectorPlugin`, its client satisfies `ConnectorClient`, implements the optional `history(target, limit)` hook via Get Channel Messages, and `disconnect()` is idempotent; `doctor()` reports ok/failed with gateway+binding detail; unit-asserted (isinstance checks against the runtime-checkable Protocols + behavior tests).
- [x] **AC-9 Production registration**: `registry.register()` (production name, docstring distinguishing it from `register_for_test`) exists; app lifespan registers `"discord"` unconditionally BEFORE `ConnectorManager()`/`start_all` (so persisted rows find the plugin at startup), with symmetric unregistration at shutdown mirroring the stub hook's hygiene; asserted by a lifespan-cycle unit test.
- [x] **AC-10 Budget + purity**: `wc -l the_one/connectors/discord/*.py` total ≤1,100; `git diff` shows no changes to `pyproject.toml`/`uv.lock` (no new deps); unit tests import no real network (fixture only, `websockets.serve` on localhost ephemeral port).
- [x] **AC-11 Suite green**: `make test-unit` passes with no new warnings; the fake-gateway tests run inside it (not marker-deselected).

## Verification Steps

- AC-1..AC-8 (incl. AC-3b): `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_discord_*.py -x --timeout 30` — all green, run FOREGROUND.
- AC-4 manager stop: the test asserts the listener task completes (not cancelled, not retrying) within the fixture's fast backoff window.
- AC-9: lifespan test drives `async with lifespan(app):` directly, twice, following the established sibling pattern in `tests/test_connector_stub_registration_hook.py` (no `TestClient` HTTP round-trip needed); `registry.get_plugin("discord")` is non-None inside a cycle and None after teardown.
- AC-10: run the `wc -l` count and record it in the flight log (mission running total: 1,060 used of 3,000).
- AC-11: `make test-unit` once at leg end, foreground, timeout up to 600000 ms.

## Implementation Guidance

1. **`PermanentConnectorFailure` first** (`base.py`): subclass `ConnectorClientError`; docstring naming the close codes and the manager stop semantics. Then the manager edits (AC-5's re-raise carve-out in `_connect_once`; in `_run`, wrap the `_connect_once` call so `PermanentConnectorFailure` → log + `return`).
2. **Fake gateway** (`tests/_discord_gateway_fixture.py`): `websockets.serve` double with scriptable scenarios — send hello with a short `heartbeat_interval`, assert identify/resume payloads, emit READY/MESSAGE_CREATE dispatches, close with a chosen code, abrupt-close. Keep scenarios data-driven so each test composes its script.
3. **`_gateway.py`**: single connection object owning the ws + heartbeat task; tracks the last dispatch sequence number `s` and feeds it to heartbeat and resume payloads (AC-2/AC-3); expose enough seams (injectable gateway URL, injectable re-identify delay) for the fixture. The gateway URL comes from Get Gateway Bot in production but MUST be overridable via the plugin's account-keyed state or constructor for tests.
4. **`_rest.py`**: one `AsyncClient` per client instance against `https://discord.com/api/v10` (base URL injectable for tests); a small bucket-limiter class keyed by `X-RateLimit-Bucket` with a global gate.
5. **`plugin.py`**: type-keyed singleton holding `_state: dict[str, _AccountState]` (session_id, resume_gateway_url, failure marker, live client) — the `StubPlugin._live` shape. `connect()` clears the failure marker at the top, builds REST + gateway, returns a client whose `is_alive()` reflects the gateway task.
6. **Registration**: add `registry.register()`; wire app lifespan (own guarded try/except block mirroring the neighbors at `app.py:255+`).
7. **Test-run discipline**: run tests foreground with explicit timeouts (up to 600000 ms tool timeout); never background a test run; scope iterations to the touched files and run `make test-unit` once at leg end. Any `uv sync` MUST include `--extra dev`.

## Edge Cases

- **Heartbeat race on close**: cancelling the heartbeat task must not swallow the close reason the reconnect decision needs.
- **Resume rejected mid-replay**: op 9 can arrive after resume with `d: false` → fresh identify on the SAME connection per protocol, after the 1–5s randomized delay (fixture scripts this with the delay injected to ~0).
- **Stale `resume_gateway_url`**: if CONNECTING to the stored resume URL fails (connection error to that host — the single, concretely testable trigger; resume *rejections* are op 9's already-specified same-connection re-identify path, not this case), the client CLEARS `resume_gateway_url` + `session_id` in the per-account state and, within the SAME `connect()` call, falls back to the default gateway URL with a fresh identify — the state clear guarantees a subsequent `connect()` never retries the dead host. Unit-asserted with a fixture scenario where the advertised resume listener is closed.
- **op 7 close is self-initiated**: the client-initiated close responding to op 7 RECONNECT must NOT run through the close-code-policy check for server-sent 4004/4010–4014 — no accidental `PermanentConnectorFailure` on a close the client chose itself.
- **MESSAGE_CREATE before READY finishes processing**: buffer or drop cleanly — never dispatch an envelope with an unknown bot-user-id (mentions_bot would be wrong).
- **DM channel detection**: MESSAGE_CREATE lacks a channel-type field reliably — resolve DM-ness via the READY private-channel data or a Get Channel lookup cached per channel id (unbounded growth acceptable at personal-bot scale; note in code).
- **429 with `global: true`**: gate ALL buckets, not just the offending one.
- **stop() during backoff**: existing manager cancellation semantics must hold — no new cleanup paths that break `drain()`.

## Files Affected

- `the_one/connectors/discord/{__init__,_gateway,_rest,plugin}.py` — new
- `the_one/connectors/base.py` — `PermanentConnectorFailure`
- `the_one/connectors/manager.py` — `_connect_once` re-raise + `_run` narrow catch
- `the_one/connectors/registry.py` — `register()`
- `the_one/interfaces/web/app.py` — lifespan registration block
- `tests/_discord_gateway_fixture.py`, `tests/test_discord_*.py` — new

## Citation Audit (2026-09-01)

Verified against the working tree at branch cut (`9245047`): `base.py:84` `ConnectorClientError`; `manager.py:202-219` `_connect_once` with catch-all at `:217`; `manager.py:144-200` `_run` supervisor loop; `registry.py:17` `register_for_test` (no production register — confirmed absent); `stub.py:61` `_live` account-keyed dict; `db/models.py:152` `type: Literal["discord", "stub"]`; `app.py:275-280` dual-gated stub hook. All live.

---

## Post-Completion Checklist

**This flight uses the flight-end commit model — do NOT commit and do NOT signal `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` foreground)
- [x] Flight log updated with leg progress entry (include the Discord Python line count)
- [ ] Leg status set to `landed` (in this file's header)
- [ ] Signal `[HANDOFF:review-needed]` — review and commit happen at flight end
