# Leg: rest-doctor-and-rotation-eviction

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Ship the operator-facing doctor-probe REST endpoint (`POST /api/connector-accounts/{account_id}/test/connect`) and wire `_evict_all_for_account` into the encryption-rotation transaction so that warm pool entries are flushed after a key rotation. Closes the Flight 1 debrief carry-forward action item on rotation-while-pool-warm.

## Context

### Why this leg

Two intertwined deliverables driven by mission criteria + the F1 debrief:

- Mission criterion: "A doctor-style probe accessible from each connector account's Admin detail page verifies the connection lifecycle (token validity, expected permissions, reachability of the platform's API and gateway endpoints), surfaces the result in the same diagnostic shape M07's MCP inspector established, and runs without dispatching any messages to peers." Flight 2 surfaces this through the new REST endpoint + the UI banner (leg 5); production runs the stub doctor probe until Flight 8 registers Discord.
- Mission criterion: "Failures isolated to the connector layer ... do not take the chat session down — the affected connector account surfaces a degraded status in its Admin detail page, the agent runtime continues to serve the remaining connectors and the rest of its tool registry, and the operator can re-enable the connector without restarting the-one." The probe is the operator-visible diagnostic surface for this isolation pattern.
- F1 debrief action item #2: `_evict_all_for_account` was wired into the test seam but NOT into the rotation transaction. After a credential rotation, warm pool entries kept serving the OLD ciphertext-key-cached credentials until they idle-evicted (30 min default). The rotation-while-pool-warm test that nails this down is the natural pairing with the eviction wiring in this leg.

The flight Design Decision "Pool eviction wired into BOTH rotation AND per-account PUT (secrets change); rotation eviction lives OUTSIDE the commit try/except" already laid out the precise placement. Leg 3 shipped the per-account PUT half; this leg ships the rotation half.

### Relevant design decisions

- **"Pool eviction wired into BOTH rotation AND per-account PUT ... rotation eviction lives OUTSIDE the commit try/except"** — drives the rotation-eviction placement: AFTER `await conn.commit()`, BEFORE the on-disk key replace, OUTSIDE the existing commit-try/except. Eviction failure is logged but does NOT abort rotation (rationale: DB is already committed in the new-key state; refusing to replace the on-disk file would leave the DB unreadable on next process restart; worst case "eviction failed, key file replaced" is that warm entries serve stale credentials until their idle TTL elapses — exactly the pre-F1-debrief baseline).
- **"Doctor-probe response shape"** — explicit Design Decision: `POST /api/connector-accounts/{account_id}/test/connect` calls `plugin.doctor(account, encryptor)` and returns `{status: <DoctorReport.status>, details: <DoctorReport.details>}`. **Design adjustment for this leg**: the flight wording omits `DoctorReport.message`, but `message` is a required field on the dataclass (`connectors/base.py:125`) and the UI banner needs a one-sentence summary. This leg returns `{status, message, details}` — the additional `message` field is a logged design adjustment, not a deviation. Mirrors the operator-facing summary the MCP `/test/connect` route surfaces; the UI renders `message` as the LED-adjacent banner text and `details` as the labeled k/v block.
- **"No in-flight override body in Flight 2"** — the doctor probe accepts NO request body. Route signature is `(account_id: str)` only. The MCP `/test/connect` Flight 8 L4 override body was a retrofit driven by specific operator demand on a mature surface; the create-before-test workflow established by the Flight 2 UI (leg 5's "Create & Test" combined-action button) is the established muscle-memory pattern. This leg ships the route minus the override.
- **"Unknown type returns `{status: 'error', ...}` with HTTP 200"** — the doctor probe returns 200 with an error-shaped envelope when the registry doesn't know the account's `type` (mirror of the MCP "unknown transport" error shape). Returning 200 lets the UI render the banner inline rather than triggering a global error handler. The endpoint returns 4xx only on the "account not found" case (404).

### Key learnings from prior flights

- **F1 leg 6 docstring shape** — the rotation transaction's docstring is the canonical precedent for documenting key-rotation invariants: "all three surfaces commit atomically — a partial rotation that handled only a subset would leave the others encrypted under a key that no longer exists on disk." This leg's eviction wiring lives OUTSIDE that atomicity contract (post-commit, log-and-continue on failure).
- **F2 L3 established the `_evict_all_for_account` import pattern in api.py** — function-local import inside the handler body, per the `function-local-import-to-break-load-cycle` convention codified in F2 L1. The rotation eviction wiring follows the same pattern.
- **F2 L3 established the autouse `_isolation` fixture pattern for tests touching the connector pool** — this leg's tests reuse the same pattern.
- **`DoctorReport` invariants** — `connectors/base.py:111-140` defines `DoctorReport` as a frozen-slotted dataclass with `status: Literal["ok", "degraded", "failed"]`, `message: str` (required), and `details: dict[str, Any]` (required, may be empty). The stub's default doctor returns `DoctorReport(status="ok", message="stub probe ok", details={})`.

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/api.py:rotate_encryption_key` (~L2951-3091) — the rotation transaction. `decrypted_connectors` is built at L3017-3028 (list of `(account_id, secrets_dict)` tuples). The single `await conn.commit()` at L3068 is the authoritative commit point. The on-disk key file is written via temp-file + `os.replace` at L3077-3086. `encryptor.install_key(new_key)` at L3089 is the in-memory cutover.
- `the_one/interfaces/web/api.py` — no connector doctor-probe route yet. The MCP doctor probe at L1307+ (`POST /mcp-sources/{source_id}/test/connect`) is the structural template; the connector version is much simpler (no two-call dance, no OAuth, no override body, no in-flight cache management).
- `the_one/connectors/registry.py:99` — module-level `resolve(type_name: str) -> ConnectorPlugin` helper; raises `ConnectorRegistrationError` if the type isn't registered.
- `the_one/connectors/base.py:111-140` — `DoctorReport` dataclass.
- `the_one/connectors/errors.py:15-69` — `ConnectorClientError` (base) + 5 subclasses including `ConnectorRegistrationError`.
- `the_one/connectors/_stub.py:146-158` — stub `doctor` method; default returns `DoctorReport(status="ok", message="stub probe ok", details={})`. `StubPlugin.doctor_response: ClassVar[DoctorReport | None]` allows tests to override the response. `StubPlugin.doctor_calls: ClassVar[list[tuple[str, str]]]` records each call as `(account_id, account_type)`.
- `the_one/connectors/_pool.py:244-266` — `_evict_all_for_account(account_id)`; the function this leg wires into rotation.
- `the_one/connectors/_pool.py:396-451` — `acquire(agent_name, account_id)`; the function whose post-rotation behavior the new test validates.
- `tests/test_provider_api.py` — existing rotation tests (10 sites that POST to `/api/encryption/rotate`). These pin LLM + MCP rotation behavior; they should remain byte-identically green after this leg's eviction wiring (the eviction call is a no-op when no warm pool entries exist).
- `tests/test_db_api.py:TestConnectorAccountAPI` (from F2 L3) — the autouse `_isolation` fixture + the established connector-pool-acquire test patterns are reused.

## Outputs

What exists after this leg completes:

- **Route: `POST /api/connector-accounts/{account_id}/test/connect`** — added to the "Connector Accounts" section in `interfaces/web/api.py`, placed AFTER the DELETE route (so the section's CRUD-then-action ordering mirrors MCP's `/test/connect` placement after `delete_mcp_source`).
  - Signature: `async def test_connector_connection(account_id: str) -> dict[str, Any]:` — NO `request` parameter (no in-flight override body in Flight 2).
  - Body:
    1. `repo = await _connector_repo(); account = await repo.get(account_id)` → 404 with `f"Connector account not found: {account_id}"` on KeyError.
    2. Resolve the plugin: `try: plugin = registry_resolve(account.type)` (where `registry_resolve` is `the_one.connectors.registry.resolve`); on `ConnectorRegistrationError`, return `{"status": "error", "message": f"Unknown connector type: {account.type}", "details": {"error": "type not registered", "type": account.type}}` (HTTP 200).
    3. Call the probe inside a `try/except ConnectorClientError` block: `try: report = await plugin.doctor(account, get_encryptor(settings.data_dir))`. On `ConnectorClientError as e`, return `{"status": "error", "message": str(e) or f"{type(e).__name__}", "details": {"error": str(e), "exception_type": type(e).__name__}}` (HTTP 200).
    4. On success: `return {"status": report.status, "message": report.message, "details": report.details}` (HTTP 200).
  - **No catch-all `except Exception:`** — connector plugins are expected to wrap their failure modes in `ConnectorClientError` (per the F1 typed-exception hierarchy). An escaping `Exception` indicates a real bug and SHOULD surface as a 500 so it's visible. This is a deliberate divergence from MCP `test_mcp_connection` at L1296-1304 (which has a catch-all to handle stdio teardown leaking `asyncio.CancelledError` from `MCPClient._safe_cleanup` — an MCP-specific transient that architect was fixing). Connectors have no analogous transient; if one surfaces, the typed-exception contract is the right place to capture it.
- **Rotation eviction wiring** in `rotate_encryption_key` (`api.py:rotate_encryption_key`):
  - INSERT a new block AFTER `await conn.commit()` at L3068 (post step-4, pre step-5 in the existing numbered comments) and BEFORE the temp-file write at L3077.
  - **Block placement**: OUTSIDE the existing `try/except` that wraps the commit block (L3052-3071). The new block has its own narrow `try/except` per the failure-mode rationale below.
  - Body:
    ```python
    # 4b. Evict warm connector pool entries so the next acquire reloads
    #     credentials decrypted under the new key. Lives OUTSIDE the
    #     commit try/except (Flight 2 Design Decision): the DB is already
    #     in the new-key state; refusing to replace the on-disk key file
    #     because eviction failed would leave the DB unreadable on the
    #     next process restart. Worst case "eviction failed, key file
    #     replaced" is that warm entries serve stale credentials until
    #     idle-TTL elapses — exactly the pre-F1-debrief baseline.
    #
    #     Failure mode: log + continue. Eviction is idempotent and
    #     self-bounded (per-entry 10s timeout in `_evict`).
    from the_one.connectors._pool import _evict_all_for_account
    for aid, _ in decrypted_connectors:
        try:
            await _evict_all_for_account(aid)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "rotation: connector pool eviction for account %r failed; "
                "continuing on-disk key replace. Warm entries (if any) "
                "will serve stale credentials until idle-TTL elapses.",
                aid,
            )
    ```
- **Tests** — the F2 L3 `_isolation` autouse fixture is class-scoped (declared inside `TestConnectorAccountAPI`). It includes the load-bearing `monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)` step that makes `acquire(...)` work inside the test client's isolated DB. Any test that calls `acquire(...)` (i.e. all eviction tests AND the rotation test) MUST run with that fixture active.

  **Placement choice (firmed up at design review)**:
  - Doctor-probe tests: NEW class `TestConnectorAccountDoctor` in the same file, redeclaring the `_isolation` fixture verbatim (~30 LoC). The doctor probe doesn't call `acquire()` so technically only the registry + StubPlugin reset are needed, but mirroring the F2 L3 fixture keeps the test class shape consistent.
  - Rotation-eviction test: **PIN IT INSIDE `TestConnectorAccountAPI`** (not a separate `TestConnectorAccountRotation` class). The test calls `acquire("test-agent", account_id)` which depends on the `_load_account` monkeypatch in the existing `_isolation` fixture. Extracting the rotation test into a new class would require redeclaring the entire fixture; pinning inside `TestConnectorAccountAPI` reuses it cleanly. A `# Rotation eviction:` section header inside the class delimits the test.
  - `test_doctor_probe_success` — stub-typed account; POST; assert `{status: "ok", message: "stub probe ok", details: {}}`.
  - `test_doctor_probe_configured_failure` — `StubPlugin.doctor_response = DoctorReport(status="failed", message="bot token revoked", details={"reason": "401"})`; POST; assert that envelope round-trips.
  - `test_doctor_probe_degraded_status` — `StubPlugin.doctor_response = DoctorReport(status="degraded", message="...", details={...})`; POST; assert status is "degraded" (regression net for the third Literal branch).
  - `test_doctor_probe_unknown_type` — POST a new account via `/api/connector-accounts` with `type="unregistered-platform"` (verified at design review: `ConnectorAccount.type` is currently unconstrained `str`, so the POST succeeds without validation rejection). The autouse fixture pre-registers only `"stub"`; the registry has no entry for `"unregistered-platform"`. POST the doctor probe; assert `{status: "error", message: "Unknown connector type: unregistered-platform", details: {"error": "type not registered", "type": "unregistered-platform"}}` with HTTP 200. **Forward-compat note**: if a future leg tightens `ConnectorAccount.type` to a `Literal[...]`, this test's POST step will need updating (insert via the repo to bypass the Pydantic gate, or refactor the test to use a different mechanism).
  - `test_doctor_probe_connector_client_error` — `StubPlugin.doctor_should_raise = ConnectorClientError("simulated probe failure")`. **Audit at design time**: the stub MAY not have a `doctor_should_raise` knob yet — check `connectors/_stub.py`. If absent, ADD it as part of this leg (extends the existing scenario-knob pattern, same shape as `connect_should_fail`). Document the addition.
  - `test_doctor_probe_unknown_account_returns_404` — POST to a made-up id; assert 404 with the canonical detail string.
  - `test_doctor_probe_records_the_call` — POST; assert `StubPlugin.doctor_calls == [(account_id, "stub")]`. Regression net for the "probe was actually dispatched" path.
  - `test_rotation_evicts_warm_pool_entries` — the F1 debrief carry-forward test. Setup: register stub, POST a stub account with `secrets={"BOT_TOKEN": "original"}`, acquire a warm pool entry for `("agent1", account_id)`, assert the entry is in `pool_mod._pool`. Trigger: POST `/api/encryption/rotate`. Assert: the original key in `pool_mod._pool` is GONE (eviction fired). Assert: a fresh `acquire` after rotation returns a new entry that decrypts under the new key. The "decrypts under the new key" assertion is satisfied transitively — `acquire` calls `_load_account` which uses the live encryptor; if rotation succeeded, the encryptor's `install_key` has updated the cached key; if eviction succeeded, the old entry is gone; the fresh acquire reads the row (encrypted under the new key, written in step 4 of the rotation) via the live encryptor.
- Flight log "Leg Progress" entry + "Design Adjustments" entry (the `message` field inclusion).
- Flight artifact's leg-4 checkbox ticked.

## Acceptance Criteria

- [ ] `POST /api/connector-accounts/{account_id}/test/connect` route exists in the "Connector Accounts" section of `api.py`.
- [ ] Route signature is `(account_id: str)` — NO request body parameter.
- [ ] Route returns 404 with `f"Connector account not found: {account_id}"` for unknown account ids.
- [ ] Route returns HTTP 200 with `{status: "error", message: <unknown-type str>, details: {...}}` for accounts whose `type` is not in the registry.
- [ ] Route returns HTTP 200 with `{status: "error", message: str(e), details: {error: str(e), exception_type: type(e).__name__}}` when `plugin.doctor` raises `ConnectorClientError`.
- [ ] Route returns HTTP 200 with `{status: <DoctorReport.status>, message: <DoctorReport.message>, details: <DoctorReport.details>}` on success.
- [ ] Route does NOT have a catch-all `except Exception:` — escaping non-`ConnectorClientError` exceptions surface as 500.
- [ ] `rotate_encryption_key` includes the eviction loop AFTER `await conn.commit()` and BEFORE the on-disk key replace.
- [ ] Eviction loop lives OUTSIDE the existing commit try/except; its own narrow try/except logs + continues on failure.
- [ ] Eviction loop iterates `decrypted_connectors` (the list already built in step 1 of rotation), calling `_evict_all_for_account` per account.
- [ ] All 8 new tests land green (7 doctor-probe + 1 rotation-eviction).
- [ ] No regression on existing rotation tests in `tests/test_provider_api.py` (the eviction call is a no-op when no warm pool entries exist).
- [ ] No regression on existing connector-account REST tests in `tests/test_db_api.py::TestConnectorAccountAPI`.
- [ ] `make test` clean (delta: +8 tests; no regressions); `make lint` clean.
- [ ] Design adjustment logged in flight log: `DoctorReport.message` included in the response envelope (the flight Design Decision said `{status, details}`; the implementation ships `{status, message, details}` for UI banner needs).

## Verification Steps

How to confirm each criterion:

- `grep -n "/api/connector-accounts.*test/connect\|test_connector_connection" the_one/interfaces/web/api.py` — route definition lights up.
- `grep -n "_evict_all_for_account\|decrypted_connectors" the_one/interfaces/web/api.py` — three sites total: the F2 L3 PUT, the F2 L3 DELETE, and the new rotation block; `decrypted_connectors` appears in the build loop AND in the new eviction loop.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestConnectorAccountDoctor` — 7 tests green.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestConnectorAccountAPI::test_rotation_evicts_warm_pool_entries` — 1 test green (or if added under a separate class, that path).
- `docker exec the-one pytest -x --timeout 30 tests/test_provider_api.py` — all existing rotation tests still green.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestConnectorAccountAPI` — F2 L3's 12 tests still green.
- `make test` — full suite clean. Pass-count delta from leg-3's 1797: +8 tests.
- `make lint` — clean.

## Implementation Guidance

1. **Audit the stub for `doctor_should_raise` knob**
   - `cat the_one/connectors/_stub.py` — look for an existing failure-injection ClassVar that drives the doctor path to raise. If absent (likely), ADD it:
     ```python
     # In the class body, alongside connect_should_fail and doctor_response:
     doctor_should_raise: ClassVar[BaseException | None] = None
     """If set, doctor() raises this exception INSTEAD of returning a
     DoctorReport. Tests use it to drive the ConnectorClientError path
     of the doctor probe endpoint. ``reset_for_test()`` clears this.
     """
     ```
   - Extend `reset_for_test()` to set `cls.doctor_should_raise = None`.
   - Extend the `doctor()` method body:
     ```python
     async def doctor(self, account, encryptor) -> DoctorReport:
         type(self).doctor_calls.append((account.id, account.type))
         if type(self).doctor_should_raise is not None:
             raise type(self).doctor_should_raise
         if type(self).doctor_response is not None:
             return type(self).doctor_response
         return DoctorReport(status="ok", message="stub probe ok", details={})
     ```

2. **Add the doctor-probe route** (`the_one/interfaces/web/api.py`, "Connector Accounts" section, AFTER `delete_connector_account`)
   - Skeleton:
     ```python
     @router.post("/connector-accounts/{account_id}/test/connect")
     async def test_connector_connection(account_id: str) -> dict[str, Any]:
         """Run the connector plugin's doctor probe against the account.

         Returns 404 if the account is not found, else returns an HTTP-200
         envelope shaped ``{status, message, details}``. The route does
         NOT raise non-typed exceptions to the client — `ConnectorClientError`
         is converted to ``{status: "error", ...}``; other exceptions
         surface as 500.

         Unknown connector types (registry has no entry for the account's
         `type`) return ``{status: "error"}`` with HTTP 200 — mirrors the
         MCP "unknown transport" pattern so the UI banner renders inline.

         No in-flight override body in Flight 2 (Design Decision). The
         create-before-test workflow established by leg 5's "Create &
         Test" combined-action button is the established muscle-memory
         pattern.
         """
         from the_one.connectors.errors import (
             ConnectorClientError,
             ConnectorRegistrationError,
         )
         from the_one.connectors.registry import resolve as _resolve_plugin

         repo = await _connector_repo()
         try:
             account = await repo.get(account_id)
         except KeyError:
             raise HTTPException(
                 status_code=404,
                 detail=f"Connector account not found: {account_id}",
             )

         try:
             plugin = _resolve_plugin(account.type)
         except ConnectorRegistrationError:
             return {
                 "status": "error",
                 "message": f"Unknown connector type: {account.type}",
                 "details": {
                     "error": "type not registered",
                     "type": account.type,
                 },
             }

         try:
             report = await plugin.doctor(account, get_encryptor(settings.data_dir))
         except ConnectorClientError as e:
             return {
                 "status": "error",
                 "message": str(e) or type(e).__name__,
                 "details": {
                     "error": str(e),
                     "exception_type": type(e).__name__,
                 },
             }

         return {
             "status": report.status,
             "message": report.message,
             "details": report.details,
         }
     ```

3. **Wire eviction into the rotation transaction** (`the_one/interfaces/web/api.py:rotate_encryption_key`)
   - Locate the existing `await conn.commit()` at L3068 (inside the commit-block try/except at L3052-3071).
   - Add a new numbered comment block AFTER `except: rollback; raise` (L3069-3071) and BEFORE the on-disk key write (L3073's `# 5.` comment / L3077's `tmp_path = ...`).
   - Body (verbatim from Outputs above):
     ```python
     # 4b. Evict warm connector pool entries so the next acquire reloads
     #     credentials decrypted under the new key. Lives OUTSIDE the
     #     commit try/except (Flight 2 Design Decision): the DB is already
     #     in the new-key state; refusing to replace the on-disk key file
     #     because eviction failed would leave the DB unreadable on the
     #     next process restart. Worst case "eviction failed, key file
     #     replaced" is that warm entries serve stale credentials until
     #     idle-TTL elapses — exactly the pre-F1-debrief baseline.
     #
     #     Failure mode: log + continue. Eviction is idempotent and
     #     self-bounded (per-entry 10s timeout in `_evict`).
     from the_one.connectors._pool import _evict_all_for_account
     for aid, _ in decrypted_connectors:
         try:
             await _evict_all_for_account(aid)
         except Exception:
             import logging
             logging.getLogger(__name__).exception(
                 "rotation: connector pool eviction for account %r failed; "
                 "continuing on-disk key replace. Warm entries (if any) "
                 "will serve stale credentials until idle-TTL elapses.",
                 aid,
             )
     ```

4. **Add the `TestConnectorAccountDoctor` test class** (`tests/test_db_api.py`)
   - Class-scoped `_isolation` autouse fixture mirroring `TestConnectorAccountAPI`'s pattern from F2 L3.
   - 7 tests as enumerated in Outputs.
   - Each eviction or doctor-probe test follows the same skeleton: ensure stub registered (autouse handles), POST an account, exercise the probe path, assert the envelope.
   - For `test_doctor_probe_unknown_type`: bypass the registry by directly inserting a `ConnectorAccount` row with `type="unregistered-platform"` via the repository (the autouse fixture pre-registers "stub", so any other type is "unregistered"). Use `await _connector_repo().create(ConnectorAccount(...))` from inside the test OR POST normally and accept that Pydantic validation may not reject it (since `ConnectorAccount.type` is currently `str`, unconstrained).
   - For `test_doctor_probe_connector_client_error`: set `StubPlugin.doctor_should_raise = ConnectorClientError("simulated probe failure")` BEFORE the POST. The autouse fixture's teardown `StubPlugin.reset_for_test()` clears it.

5. **Add the rotation-eviction test**
   - **MUST be placed inside `TestConnectorAccountAPI`** (not a separate `TestConnectorAccountRotation` class). The test calls `acquire("test-agent", account_id)`, which depends on the class-scoped `_isolation` autouse fixture's `monkeypatch.setattr(pool_mod, "_load_account", _patched_load_account)` step. Moving the test outside the class would require redeclaring the entire fixture (~30 LoC, including the patched-`_load_account` closure pattern). Pinning inside the existing class reuses the fixture cleanly.
   - Skeleton:
     ```python
     async def test_rotation_evicts_warm_pool_entries(self, client):
         from the_one.connectors import _pool as pool_mod
         from the_one.connectors._pool import acquire

         # Setup: stub-typed account with non-empty secrets.
         resp = await client.post(
             "/api/connector-accounts",
             json={
                 "name": "rotation-target",
                 "type": "stub",
                 "secrets": {"BOT_TOKEN": "original_value"},
             },
         )
         account_id = resp.json()["id"]

         # Acquire warm pool entry.
         await acquire("test-agent", account_id)
         key = ("test-agent", account_id)
         assert key in pool_mod._pool, "pool seed failed"

         # Trigger rotation.
         rot = await client.post("/api/encryption/rotate")
         assert rot.status_code == 200
         assert rot.json() == {"status": "ok"}

         # Eviction fired.
         assert key not in pool_mod._pool, (
             "rotation should have evicted warm pool entry for the rotated "
             "account; eviction wiring at rotate_encryption_key step 4b is "
             "the regression net"
         )

         # Fresh acquire works under the new key.
         await acquire("test-agent", account_id)
         assert key in pool_mod._pool
     ```

6. **Run scoped tests then full suite**
   - `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — full file green (includes the new classes + the existing F2 L3 class).
   - `docker exec the-one pytest -x --timeout 30 tests/test_provider_api.py` — existing rotation tests still green (no regression).
   - `make test` — full suite green. Expected delta from 1797: +8 tests.
   - `make lint` — clean.

7. **Update artifacts and flight log**
   - Set this leg's status to `landed`.
   - Append a "Leg Progress" entry summarizing: doctor-probe route, rotation eviction wiring, stub `doctor_should_raise` knob (if added), test deltas.
   - Append a "Design Adjustments" entry: `DoctorReport.message` field included in the response envelope (flight Design Decision said `{status, details}`; ship `{status, message, details}` because `message` is mandatory on `DoctorReport` and the UI banner needs a one-sentence summary).
   - Check off leg 4 in `flight.md`.
   - Do NOT commit.

## Edge Cases

- **`DoctorReport.message` field inclusion** — flight Design Decision said `{status, details}`; this leg ships `{status, message, details}`. Logged as a Design Adjustment. If a future reader questions the divergence, the justification is in this leg's Context section. The frontend in leg 5 will read `message` for the banner text and `details` for the labeled k/v block.
- **`ConnectorRegistrationError` is a subclass of `ConnectorClientError`** — `connectors/errors.py:55-67`. The doctor-probe route catches `ConnectorRegistrationError` FIRST (around the `_resolve_plugin` call); if it leaked into the second `try/except ConnectorClientError`, it would still be caught — but the response shape would be the generic "exception" shape, not the specific "unknown type" shape. The two-try-block ordering is deliberate; do not consolidate.
- **`get_encryptor` is module-level imported** — verify with `grep -n "from the_one.encryption" the_one/interfaces/web/api.py`. If imported at module top, the route uses the module-level name. If function-local-imported elsewhere, follow the same pattern. Most likely already at module top.
- **Stub `doctor_should_raise` may not exist yet** — Implementation step 1 explicitly handles this. If you skip the audit and write the test against a non-existent knob, the test will fail at import time with `AttributeError`. Audit FIRST.
- **`decrypted_connectors` is in scope at the eviction-loop insertion point** — yes; it's a local variable built at L3017-3028 and used at L3040-3043 for re-encryption. Still in scope at L3072+ where the eviction loop lands.
- **Rotation test interaction with `_isolation` fixture** — the F2 L3 autouse fixture calls `_clear_for_test()` in setup AND teardown. The rotation test's `acquire` step happens INSIDE the test body, after setup, so the pool starts empty as expected. After rotation, the test's own `acquire` call seeds the pool again; the autouse teardown's `_clear_for_test()` cleans it up.
- **`/api/encryption/rotate` race with warm pool acquire** — between the rotation's `commit()` and the eviction loop, a concurrent `acquire` could read the DB row (encrypted under the NEW key, written in step 4) and try to decrypt with the OLD in-memory encryptor (NOT YET cut over via `install_key` — that happens at step 7 / L3089). Decryption would fail with `InvalidToken`. **This is the pre-F1-debrief baseline**; THIS leg doesn't change it. The eviction loop closes the post-`install_key` staleness window, not the inter-commit-and-install-key race. Document this in the flight log "Decisions" section so it surfaces in M10 mission debrief alongside the other rotation invariants.
- **`get_encryptor(settings.data_dir)` shape** — confirmed at design review: imported at module top of `interfaces/web/api.py:34` (`from the_one.encryption import Encryptor, get_encryptor`). The same call appears in `rotate_encryption_key` at L2969 and in `_connector_repo` (F2 L3). No import additions needed.
- **`test_db_api.py` `client` fixture does NOT pre-write the encryption key file** (unlike `test_provider_api.py`'s fixture, which calls `key_path.write_bytes(test_key)` at L67). Verified at design review. `os.replace(tmp, key_path)` in the rotation transaction tolerates a missing destination, so rotation succeeds in the `test_db_api.py` fixture even without the pre-write. The leg's rotation test exercises this path; no fixture change required.
- **`ConnectorRegistrationError.reason` / `.type_name` are dropped from the response** — the route's unknown-type envelope uses `account.type` directly rather than the exception's structured fields. Deliberate: the exception's reason string is implementation-detail ("registration failed for type X"); the operator-facing message uses the account's type verbatim, which is what they configured. Log this as a Design Adjustment in the flight log so future readers know it's not an oversight.
- **No catch-all `except Exception:` in the route** — deliberate divergence from MCP. If a plugin's `doctor` method raises an exception NOT subclassed from `ConnectorClientError`, the 500 surfaces. This is the right call: the F1 contract on plugins is "wrap your failure modes in the typed-exception hierarchy"; an escaping plain `Exception` is a plugin bug, not an operator-actionable state. Document this in the route's docstring (the skeleton already does).
- **Provider rotation tests in `tests/test_provider_api.py`** — they POST `/api/encryption/rotate` against fixtures that have NO connector_accounts rows. The eviction loop iterates over `decrypted_connectors` which is empty. No-op. Existing tests stay green.

## Files Affected

- `the_one/interfaces/web/api.py` — new `test_connector_connection` route (~60 LoC) + eviction block in `rotate_encryption_key` (~15 LoC).
- `the_one/connectors/_stub.py` — IF `doctor_should_raise` knob is absent: add the ClassVar, extend `reset_for_test()`, extend `doctor()` (~6 LoC).
- `tests/test_db_api.py` — new `TestConnectorAccountDoctor` class with 7 tests + 1 rotation-eviction test (in `TestConnectorAccountAPI` or a new `TestConnectorAccountRotation` class) (~200 LoC).
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — Leg Progress entry + Design Adjustments entry.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — leg-4 checkbox.

## State-Machine Reachability Audit

This leg adds two surfaces — the doctor-probe route and the rotation eviction step. Neither introduces new lifecycle states; both consume the existing connector pool state.

- **Pool entry eviction triggers** post-leg: (1) idle TTL elapses, (2) `shutdown_drain` on FastAPI lifespan, (3) operator PUT with secrets change (F2 L3), (4) operator DELETE (F2 L3), (5) **encryption rotation** (this leg). All five paths converge on `_evict_all_for_account` (the existing function). No new state added.
- **`DoctorReport.status` Literal** — three values: `"ok"`, `"degraded"`, `"failed"` (plus the route's wrapped error envelope adding `"error"` as a fourth status). The frontend in leg 5 must render all four. The leg-5 design will pin the rendering shape; this leg's tests cover the three Literal values + the wrapped error.
- **No FK / CHECK / cache-invalidation surface changes**.

## Cache Freshness Contract

For warm pool entries' cached credentials:

- **Source of truth**: `connector_accounts.secrets` (encrypted at rest), decrypted via the live encryptor.
- **Rebuild trigger**: explicit invalidation events. Post-leg-4 events: (1-5 listed above).
- **Maximum staleness acceptable to the operator**: zero across operator-visible state changes. After rotation OR per-account PUT, the next conversation turn MUST use the new credentials. This leg closes the rotation-side of the contract.
- **User-action invalidation map** (post-leg-4):
  - Rotation → eviction (THIS leg).
  - PUT with secrets change → eviction (F2 L3).
  - DELETE → eviction (F2 L3).
  - Idle TTL elapses → eviction (F1 L6).
  - `shutdown_drain` → eviction (F1 L6).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` passing (pass-count delta from 1797: +8 expected; report actual)
- [ ] `make lint` clean
- [ ] Flight log updated with a "Leg Progress" entry AND a "Design Adjustments" entry naming the `DoctorReport.message` inclusion
- [ ] This leg's status updated to `landed` (in this file's header)
- [ ] This leg checked off in `flight.md` Legs list
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

8 code-location citations verified against current code at leg design time:

- `the_one/interfaces/web/api.py:2951-3091 — rotate_encryption_key` — **OK** (verified; `decrypted_connectors` built at L3017-3028, commit at L3068, on-disk write at L3077, `install_key` at L3089).
- `the_one/interfaces/web/api.py:1307-1410+ — test_mcp_connection` — **OK** (structural template for the new connector route; mostly NOT mirrored due to MCP-specific concerns).
- `the_one/connectors/registry.py:99 — module-level resolve` — **OK** (verified).
- `the_one/connectors/base.py:111-140 — DoctorReport` — **OK** (verified; `status: Literal["ok", "degraded", "failed"]`, `message: str`, `details: dict[str, Any]` — `message` is REQUIRED, hence the design adjustment to include it in the response envelope).
- `the_one/connectors/errors.py:15-69 — ConnectorClientError hierarchy` — **OK** (`ConnectorRegistrationError` is a subclass; route handles it separately for the specific "unknown type" envelope).
- `the_one/connectors/_stub.py:146-158 — stub doctor method` — **OK** (`doctor_response` ClassVar overrides the default; `doctor_calls` records dispatches; the `doctor_should_raise` knob does NOT yet exist — Implementation step 1 covers adding it).
- `the_one/connectors/_pool.py:244-266 — _evict_all_for_account` — **OK** (function exists; per-entry 10s timeout in `_evict`; idempotent on no-match).
- `tests/test_db_api.py — TestConnectorAccountAPI (F2 L3) + _isolation fixture` — **OK** (verified via the leg-3 implementation report; the autouse fixture pattern is the template for `TestConnectorAccountDoctor`).

0 citations drifted, 0 unverifiable.
