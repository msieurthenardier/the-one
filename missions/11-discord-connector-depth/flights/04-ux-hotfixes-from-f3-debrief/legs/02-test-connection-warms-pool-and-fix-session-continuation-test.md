# Leg: test-connection-warms-pool-and-fix-session-continuation-test

**Status**: completed
**Flight**: [UX Hotfixes from F3 Debrief](../flight.md)

## Objective

Bundle two Python touch points: (A1) extend `test_connector_connection` at `the_one/interfaces/web/api.py:test_connector_connection` to call `await account_acquire(account_id)` AFTER `plugin.doctor()` succeeds, surfacing `pool_warmed` + `pool_warm_error` fields on the response envelope while isolating any warmup failure from the doctor's verdict; (C1) update the one-line text assertion in `tests/browser/test_flow_studio_connector_account_editor.py:417` from `"Distinct from the pool idle timeout"` to `"Inbound continues the same chat session within this window."` so the test matches the source string at `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:368`.

## Context

- F4 flight.md Design Decision "A1 — Test Connection wires `account_acquire` AFTER doctor succeeds, with isolated error surface" pins: placement-after-doctor (skip warmup if doctor fails); inner try/except around `account_acquire` that converts any warmup failure into structured `details.pool_warmed=false` + `details.pool_warm_error=<str(exc)>` fields WITHOUT escalating to top-level `status='error'`; the doctor's verdict is the source of truth for the envelope's `status` regardless of warmup outcome.
- The leg artifact's own architect-cycle-2 refinement (F4 flight-log Session Notes 2026-05-23 cycle 2): narrow the inner try/except from `BaseException` to `Exception` — let `CancelledError` / `SystemExit` / `KeyboardInterrupt` propagate per cooperative-cancellation discipline. The cycle-2 refinement was logged for absorption at leg-author time and is the binding wording here.
- The L1 codification `pool-warming-entrypoints-are-finite-and-named` is now in `the_one/agents.md` (F4 L1). This leg is the n=1 application: the Test Connection handler now becomes an explicitly-named pool-warming entrypoint, eliminating the L4-design-time gap.
- The L1 codification `two-concurrent-callers-reasoning` is also now in `the_one/agents.md`. The inner try/except + partial-success shape on the warmup path is exactly the discipline that convention requires: explicitly enumerate the partial-failure shape before committing.
- C1 is operator-decision `match-tests-to-code-when-code-is-operator-friendly` precedent from F3 L2 (operator-friendly text wins; test moves to match). The source string `"Inbound continues the same chat session within this window."` is operator-friendly; the test was written before the source landed at its current shape.
- F3 flight.md's L4 design-time assumption at line 55 ("…populates the pool entry via the lifespan-listener-warmup path") is the documented site of the gap A1 closes. Per F4 Design Decision + agentic-workflow `SKILL.md:47` ("annotate at the artifact header") + the L1-codified `cross-flight-ux-debt-reconciliation` discipline, the L4 body stays byte-identical as a snapshot; the correction lands as a one-line annotation under F3 flight.md's Status block at the top.
- F3 mission criterion #18 + #19 (fresh-operator + full-day-driver) contributing-criteria framing depends on A1 closing the cold-restart dropdown 404 friction. C1 is operator-debt cleanup (5 flights deep chronic) folded into this leg because it's in the same Python tier and trivially small.

## Inputs

- `the_one/interfaces/web/api.py:test_connector_connection` exists at the handler position confirmed by F4 recon table R1 — the function body runs from approximately line 2573 to line 2638. The current body calls `plugin.doctor(account, get_encryptor(settings.data_dir))` inside a `try` that catches `ConnectorClientError` and converts it to `status='error'`; it does NOT call `account_acquire` anywhere.
- `account_acquire` is exported from `the_one/connectors/_pool.py` at the `async def account_acquire(account_id: str) -> ConnectorClient` definition (F4 recon table R10 confirmed). The function delegates internally to `agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)`.
- `ConnectorClientError` is importable from `the_one.connectors.errors` — the current handler already imports it via function-local-import at the top of the handler body.
- `tests/browser/test_flow_studio_connector_account_editor.py:417` exists with the assertion `expect(cont_hint).to_contain_text("Distinct from the pool idle timeout")` (F4 recon table R3 confirmed).
- The source string at `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:368` is `'Inbound continues the same chat session within this window.'` (F4 recon table R3 confirmed).
- `tests/test_db_api.py` contains `class TestConnectorAccountDoctor` (line 971) with autouse `_isolation` fixture that resets the pool, registry, and StubPlugin class-state per test. New tests for the warmup behavior go into this class — the fixture is already in place.
- `the_one/connectors/_stub.py:StubPlugin` exists and can have `doctor_response` / `doctor_should_raise` class attributes monkeypatched per the existing test pattern (`tests/test_db_api.py:test_doctor_probe_configured_failure`).
- F3 `flight.md` exists at `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` with the L4 assumption text at line 55 and a Status block at lines 3-4.

## Outputs

- `the_one/interfaces/web/api.py:test_connector_connection`:
  - After the existing `plugin.doctor()` call succeeds (i.e., after the `try`/`except ConnectorClientError` block that returns the `status='error'` envelope), the handler runs a new best-effort warmup step:
    - The warmup step is GATED on `report.status == "ok"` — if the doctor returned `status='failed'` or `status='degraded'`, the warmup is SKIPPED entirely. Rationale: no point warming a pool entry the operator hasn't proven works; degraded is treated as not-yet-proven for warmup purposes.
    - Inside a dedicated try/except that catches `Exception` (NOT `BaseException` — `CancelledError`/`SystemExit`/`KeyboardInterrupt` propagate per cooperative-cancellation discipline), the handler calls `await account_acquire(account_id)`.
    - On success: the response envelope's `details` dict grows two new fields: `"pool_warmed": True` + `"pool_warm_error": None`.
    - On failure (`Exception` caught): the response envelope's `details` dict grows `"pool_warmed": False` + `"pool_warm_error": str(exc)`. The doctor's `status='ok'` verdict is preserved — the warmup failure does NOT escalate to `status='error'`.
    - On SKIP (doctor returned non-ok): the response envelope's `details` dict grows `"pool_warmed": False` + `"pool_warm_error": None`. The non-ok rows still carry the field shape so consumers can rely on the schema being uniform.
  - Function-local import: `from the_one.connectors._pool import account_acquire` added inside the function body (matches the existing function-local-import convention in this file).
  - The doctor's existing `report.details` dict is shallow-copied before mutation (since `report.details` may be the plugin's-owned dict; pre-existing fields preserved verbatim, plus the two new keys appended).
- `tests/test_db_api.py:TestConnectorAccountDoctor` grows three new tests:
  - `test_doctor_probe_success_warms_pool`: doctor returns `status='ok'` → envelope `details.pool_warmed` is `True`, `details.pool_warm_error` is `None`. Asserts the pool entry exists after the call by checking `(_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool` — matches the existing test idiom at `tests/test_db_api.py:647,656,686,695`.
  - `test_doctor_probe_failed_skips_warmup`: doctor returns `status='failed'` → envelope `details.pool_warmed` is `False`, `details.pool_warm_error` is `None` (skipped, not failed). Asserts `pool_mod._pool == {}` after the call (warmup was skipped, not attempted).
  - `test_doctor_probe_ok_warmup_failure_does_not_escalate`: doctor returns `status='ok'`; `account_acquire` raises (monkeypatched to raise `ConnectorClientError("simulated warmup failure")`) → envelope `status='ok'`, `details.pool_warmed` is `False`, `details.pool_warm_error == "simulated warmup failure"`. The doctor's verdict is preserved despite warmup failure. Asserts `pool_mod._pool == {}` after the call (the monkeypatched `account_acquire` raises before touching the pool, so the dict stays empty). The test confirms the partial-success isolation contract.
- `tests/browser/test_flow_studio_connector_account_editor.py:417`:
  - The single line `expect(cont_hint).to_contain_text("Distinct from the pool idle timeout")` updates to `expect(cont_hint).to_contain_text("Inbound continues the same chat session within this window.")` (full-stop included; the source string ends with a period).
  - The surrounding comment at line 414 (`# Helper text under the continuation input disambiguates from pool-TTL.`) updates to reflect the new assertion semantic — the new comment reads `# Helper text under the continuation input describes the session-continuation behavior.` so the comment intent matches what the assertion now pins.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md`:
  - A single new annotation line lands under the existing Status block (between line 4 and line 5 — i.e., immediately before the blank line separator and `## Contributing to Criteria`): `**Subsequent corrections**: L4's Test-Connection-warms-pool assumption corrected at F4 L2; see `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/02-test-connection-warms-pool-and-fix-session-continuation-test.md` (and F4 flight-debrief once landed).`
  - The L4 body text at line 55 is NOT modified — stays byte-identical as the snapshot per the F4 Design Decision + agentic-workflow `SKILL.md:47` discipline.
- No other source files touched.
- Sibling artifact bookkeeping (explicit scope): F4 `flight.md`'s L2 Checkpoints entry + L2 Legs checklist item checked off; F4 `flight-log.md`'s Leg Progress section grows an L2 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `the_one/interfaces/web/api.py:test_connector_connection` body, after the existing `plugin.doctor()` call and its associated `ConnectorClientError` handler, contains a new block that conditionally runs `await account_acquire(account_id)` ONLY when the doctor's `report.status == "ok"`.
- [x] The new warmup block is wrapped in `try / except Exception as exc:` (NOT `BaseException` — `CancelledError`/`SystemExit`/`KeyboardInterrupt` propagate per cooperative-cancellation discipline).
- [x] The new warmup block's import of `account_acquire` from `the_one.connectors._pool` is function-local (added inside `test_connector_connection`'s body, matching the existing function-local-import convention used by `ConnectorClientError` + `ConnectorRegistrationError` + `_resolve_plugin` at the top of the function body).
- [x] On warmup success: the response envelope's `details` dict contains `"pool_warmed": True` and `"pool_warm_error": None`. All pre-existing keys from `report.details` are preserved verbatim (no clobbering).
- [x] On warmup failure (caught `Exception`): the response envelope's `status` is the doctor's `report.status` (`"ok"`), `details["pool_warmed"]` is `False`, and `details["pool_warm_error"]` is `str(exc)`. The envelope does NOT promote to `status='error'`.
- [x] On warmup skip (doctor's `report.status != "ok"`): the response envelope's `details` dict contains `"pool_warmed": False` and `"pool_warm_error": None`. The envelope's `status`, `message`, and pre-existing `details` keys remain unchanged from the doctor's verdict.
- [x] The existing `ConnectorClientError` handler around `plugin.doctor(...)` remains byte-identical (the warmup block lands AFTER the doctor try/except, NOT inside it). The `Unknown connector type` early return for `ConnectorRegistrationError` also remains byte-identical.
- [x] The handler does NOT clobber the plugin's `report.details` dict in-place — it shallow-copies before mutation (e.g. `details = dict(report.details); details["pool_warmed"] = ...; details["pool_warm_error"] = ...`) so the plugin's-owned dict is not mutated cross-call.
- [x] `tests/test_db_api.py:TestConnectorAccountDoctor` contains three new tests with the names locked in the Outputs section: `test_doctor_probe_success_warms_pool`, `test_doctor_probe_failed_skips_warmup`, `test_doctor_probe_ok_warmup_failure_does_not_escalate`.
- [x] `test_doctor_probe_success_warms_pool` asserts: response `status == "ok"`; `details["pool_warmed"] is True`; `details["pool_warm_error"] is None`; `(_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool` after the call (proves the warmup actually executed, not just that the field was set). The test imports `_ACCOUNT_POOL_AGENT_SLOT` from `the_one.connectors._pool` to match the clean tuple assertion idiom used at `tests/test_db_api.py:647` and elsewhere.
- [x] `test_doctor_probe_failed_skips_warmup` asserts: response `status == "failed"`; `details["pool_warmed"] is False`; `details["pool_warm_error"] is None`; `pool_mod._pool == {}` after the call (warmup was skipped, not attempted-then-failed).
- [x] `test_doctor_probe_ok_warmup_failure_does_not_escalate` asserts: response `status == "ok"` (NOT `"error"`); `details["pool_warmed"] is False`; `details["pool_warm_error"] == "simulated warmup failure"`; `pool_mod._pool == {}` after the call (the monkeypatched `account_acquire` raises immediately without ever touching the real pool machinery, so the dict stays empty by construction).
- [x] All three new tests use the existing `TestConnectorAccountDoctor._isolation` autouse fixture's pool/registry reset — they do NOT introduce a new fixture.
- [x] Only the third test (`test_doctor_probe_ok_warmup_failure_does_not_escalate`) monkeypatches `account_acquire` itself; the first two tests exercise the real warmup path. The third test monkeypatches `account_acquire` on the source module (`monkeypatch.setattr(pool_mod, "account_acquire", _failing_acquire)`) — the handler's function-local import resolves `pool_mod.account_acquire` at call time, so the patch is in effect when the handler runs. No double-patch on `the_one.interfaces.web.api` is needed since `account_acquire` has no module-level binding there.
- [x] All existing tests in `TestConnectorAccountDoctor` (`test_doctor_probe_success`, `test_doctor_probe_configured_failure`, `test_doctor_probe_degraded_status`, `test_doctor_probe_unknown_type`, `test_doctor_probe_connector_client_error`, `test_doctor_probe_unknown_account_returns_404`, `test_doctor_probe_records_the_call`) continue to pass without modification — except for the three that assert exact-equality on the envelope (`test_doctor_probe_success`, `test_doctor_probe_configured_failure`, `test_doctor_probe_degraded_status`), which must be updated to either (a) match the new `pool_warmed` + `pool_warm_error` fields in the asserted dict, OR (b) loosen from `assert resp.json() == {...}` to `assert resp.json()["status"] == ...; assert resp.json()["details"]["..."] == ...` (per-field assertions). The leg implements option (a) — extend the equality dict to include the new fields with the expected values: `test_doctor_probe_success` adds `"pool_warmed": True` + `"pool_warm_error": None`; `test_doctor_probe_configured_failure` + `test_doctor_probe_degraded_status` add `"pool_warmed": False` + `"pool_warm_error": None` (warmup skipped on non-ok).
- [x] The `test_doctor_probe_records_the_call` test (which asserts `StubPlugin.doctor_calls == [(account_id, "stub")]`) continues to pass — the new warmup path does not invoke `plugin.doctor` a second time.
- [x] `tests/browser/test_flow_studio_connector_account_editor.py:417` (the line currently asserting `"Distinct from the pool idle timeout"`) is updated to assert `"Inbound continues the same chat session within this window."` (full-stop included). The surrounding comment at line 414 is also updated to match the new assertion intent (per Outputs).
- [x] `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` grows ONE new annotation line under the Status block, exactly: `**Subsequent corrections**: L4's Test-Connection-warms-pool assumption corrected at F4 L2; see `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/02-test-connection-warms-pool-and-fix-session-continuation-test.md` (and F4 flight-debrief once landed).` The L4 body text at line 55 is NOT modified — verified via `git diff` showing only the header insertion.
- [x] `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountDoctor -x --timeout 30` passes all tests (the 7 existing + 3 new = 10).
- [x] `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip -x --timeout 30` passes (C1 closure).
- [x] `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -x --timeout 30` passes (existing 7 tests; none break under the new envelope shape — the page.route() mocks in this file return a manually-crafted body without `pool_warmed`, which the UI ignores at present).
- [x] No source files beyond `the_one/interfaces/web/api.py` are touched (the JS source at `connector-account-editor.js:368` is NOT modified — C1 chose test-side fix). The only test files modified are `tests/test_db_api.py` and `tests/browser/test_flow_studio_connector_account_editor.py`.

## Verification Steps

- `grep -n "account_acquire" the_one/interfaces/web/api.py` returns at least one hit inside the `test_connector_connection` function body (verifies A1's call landed).
- `grep -n "pool_warmed" the_one/interfaces/web/api.py` returns at least 3 hits inside `test_connector_connection` (success path, failure path, skip path).
- `grep -n "except Exception" the_one/interfaces/web/api.py` includes at least one hit inside `test_connector_connection` for the warmup try/except.
- `grep -n "Distinct from the pool idle timeout" tests/browser/test_flow_studio_connector_account_editor.py` returns zero hits (C1's stale string is gone).
- `grep -n "Inbound continues the same chat session within this window" tests/browser/test_flow_studio_connector_account_editor.py` returns exactly one hit at the line that previously asserted the stale string.
- `grep -n "Subsequent corrections" missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` returns exactly one hit under the Status block.
- `git diff missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` shows ONLY the new annotation line near the top — no diff hunks elsewhere in F3 flight.md.
- `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountDoctor -x --timeout 30 -v` shows 10 tests passing.
- `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip tests/browser/test_connector_test_connection_button.py -x --timeout 60 -v` passes all 1 + 7 = 8 tests.
- `docker exec the-one pytest tests/test_db_api.py tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py -x --timeout 60` passes the broader file scope without regression.

## Implementation Guidance

1. **Read `the_one/interfaces/web/api.py:test_connector_connection`** (current body approximately lines 2573-2638). Confirm:
   - The function-local imports at the top of the body (`ConnectorClientError`, `ConnectorRegistrationError`, `_resolve_plugin`).
   - The early-return paths (404 on unknown `account_id`; `status='error'` envelope on `ConnectorRegistrationError`).
   - The `plugin.doctor(...)` call inside a try/except `ConnectorClientError`.
   - The final `return {"status": report.status, "message": report.message, "details": report.details}` at the end.

2. **Extend the imports**. Inside the function body, add a function-local import `from the_one.connectors._pool import account_acquire` colocated with the existing function-local imports (right after `from the_one.connectors.registry import resolve as _resolve_plugin`). The function-local-import convention is documented at `the_one/agents.md:### \`function-local-import-to-break-load-cycle\``.

3. **Insert the warmup block AFTER the doctor try/except, BEFORE the final return**. Pattern:

   ```python
   # Shallow-copy report.details so we don't mutate the plugin's-owned dict.
   details = dict(report.details)
   pool_warmed = False
   pool_warm_error: str | None = None

   if report.status == "ok":
       try:
           await account_acquire(account_id)
       except Exception as exc:  # noqa: BLE001 — best-effort warmup; explicit
           pool_warm_error = str(exc)
       else:
           pool_warmed = True

   details["pool_warmed"] = pool_warmed
   details["pool_warm_error"] = pool_warm_error

   return {
       "status": report.status,
       "message": report.message,
       "details": details,
   }
   ```

   Note: the `except Exception` is deliberately broad here per the F4 cycle-1 architect catch — the warmup is best-effort and never escalates to top-level error. Add a `noqa: BLE001` (or whatever the project's linter expects for explicit-broad-except) with a one-line WHY comment so a future reader doesn't tighten the catch.

4. **Update the three existing-equality tests in `tests/test_db_api.py:TestConnectorAccountDoctor`**:
   - `test_doctor_probe_success`: change the asserted envelope from `{"status": "ok", "message": "stub probe ok", "details": {}}` to `{"status": "ok", "message": "stub probe ok", "details": {"pool_warmed": True, "pool_warm_error": None}}`.
   - `test_doctor_probe_configured_failure`: change the asserted envelope from `{"status": "failed", "message": "bot token revoked", "details": {"reason": "401"}}` to `{"status": "failed", "message": "bot token revoked", "details": {"reason": "401", "pool_warmed": False, "pool_warm_error": None}}`.
   - `test_doctor_probe_degraded_status`: change the `body["details"]` assertion from `{"latency_ms": 1200}` to `{"latency_ms": 1200, "pool_warmed": False, "pool_warm_error": None}`.

5. **Add the three new tests to `TestConnectorAccountDoctor`**. Place them after `test_doctor_probe_records_the_call` (the current last test in the class, around line 1190), before `class TestConnectorAccountPairingCodeAndAttached` at line 1196. Suggested test bodies:

   ```python
   async def test_doctor_probe_success_warms_pool(
       self, client: AsyncClient
   ) -> None:
       """OK doctor → pool gets warmed; envelope advertises pool_warmed=True.

       Closes M11 F4 A1 (Test Connection warms pool). The L4-design-time
       assumption that lifespan-warmup populated the pool entry was
       structurally false; F4 L2 explicitly wires account_acquire after
       doctor() succeeds. Convention reference: ``pool-warming-entrypoints-
       are-finite-and-named`` (agents.md Project-wide).
       """
       from the_one.connectors import _pool as pool_mod
       from the_one.connectors._pool import _ACCOUNT_POOL_AGENT_SLOT

       account_id = await self._create_stub_account(client)
       resp = await client.post(
           f"/api/connector-accounts/{account_id}/test/connect"
       )
       assert resp.status_code == 200
       body = resp.json()
       assert body["status"] == "ok"
       assert body["details"]["pool_warmed"] is True
       assert body["details"]["pool_warm_error"] is None
       # Pool actually warmed — entry exists at the canonical key tuple.
       assert (_ACCOUNT_POOL_AGENT_SLOT, account_id) in pool_mod._pool

   async def test_doctor_probe_failed_skips_warmup(
       self, client: AsyncClient
   ) -> None:
       """Non-ok doctor → warmup is SKIPPED; envelope advertises
       pool_warmed=False + pool_warm_error=None (skipped, not failed)."""
       from the_one.connectors import _pool as pool_mod
       from the_one.connectors._stub import StubPlugin
       from the_one.connectors.base import DoctorReport

       StubPlugin.doctor_response = DoctorReport(
           status="failed",
           message="bot token revoked",
           details={"reason": "401"},
       )

       account_id = await self._create_stub_account(client)
       resp = await client.post(
           f"/api/connector-accounts/{account_id}/test/connect"
       )
       assert resp.status_code == 200
       body = resp.json()
       assert body["status"] == "failed"
       assert body["details"]["pool_warmed"] is False
       assert body["details"]["pool_warm_error"] is None
       assert pool_mod._pool == {}

   async def test_doctor_probe_ok_warmup_failure_does_not_escalate(
       self, client: AsyncClient, monkeypatch
   ) -> None:
       """OK doctor + raising account_acquire → envelope STILL status=ok;
       warmup failure isolated to pool_warm_error field.

       Convention reference: ``two-concurrent-callers-reasoning`` (agents.md
       Project-wide) — the partial-success shape was worked out before
       commit, not after."""
       from the_one.connectors import _pool as pool_mod
       from the_one.connectors.errors import ConnectorClientError

       async def _failing_acquire(account_id: str):
           # ConnectorClientError chosen because it's the realistic
           # production failure mode; any Exception subclass would prove
           # the same partial-success isolation contract.
           raise ConnectorClientError("simulated warmup failure")

       # The handler's function-local `from ._pool import account_acquire`
       # resolves pool_mod.account_acquire at handler-entry time, so
       # patching the source-module attribute is in effect when the
       # handler runs.
       monkeypatch.setattr(pool_mod, "account_acquire", _failing_acquire)

       account_id = await self._create_stub_account(client)
       resp = await client.post(
           f"/api/connector-accounts/{account_id}/test/connect"
       )
       assert resp.status_code == 200
       body = resp.json()
       # CRITICAL: doctor's verdict is preserved despite warmup failure.
       assert body["status"] == "ok"
       assert body["details"]["pool_warmed"] is False
       assert body["details"]["pool_warm_error"] == "simulated warmup failure"
       assert pool_mod._pool == {}
   ```

6. **Update `tests/browser/test_flow_studio_connector_account_editor.py:417`**:
   - Change line 417 from `expect(cont_hint).to_contain_text("Distinct from the pool idle timeout")` to `expect(cont_hint).to_contain_text("Inbound continues the same chat session within this window.")`.
   - Change the comment at line 414 from `# Helper text under the continuation input disambiguates from pool-TTL.` to `# Helper text under the continuation input describes the session-continuation behavior.`.

7. **Annotate F3 `flight.md`** under the Status block (i.e., immediately after `**Mission**: [Discord Connector Depth & Robustness](../../mission.md)` at line 4, before the blank line + `## Contributing to Criteria` at line 6):
   - Insert a new blank line + `**Subsequent corrections**: L4's Test-Connection-warms-pool assumption corrected at F4 L2; see `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/02-test-connection-warms-pool-and-fix-session-continuation-test.md` (and F4 flight-debrief once landed).`
   - Then preserve the original blank line separator before `## Contributing to Criteria`.
   - The L4 body at line 55 (now line 57 after the 2-line insertion) is NOT touched.

8. **Run tests** (per the F4 leg-execution prompt protocol: `docker exec the-one pytest …` NOT `docker compose exec` — TTY hang):
   - First: `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountDoctor -x --timeout 30 -v` (focused class)
   - Then: `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip -x --timeout 60` (C1 closure)
   - Then: `docker exec the-one pytest tests/browser/test_connector_test_connection_button.py -x --timeout 60` (existing 7 tests stay green under new envelope)
   - Then (at leg-end, broader sweep): `docker exec the-one pytest tests/test_db_api.py tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_connector_test_connection_button.py -x --timeout 60`

9. **Update F4 `flight.md` Checkpoints + Legs** — check off L2.

10. **Append L2 leg-progress entry** to F4 `flight-log.md`.

11. **Update this leg artifact's Status header** progressively: `planning` → `ready` → `in-flight` → `landed`.

## Edge Cases

- **Pool already warm from a prior test in the same session**: the `_isolation` fixture's `_clear_for_test()` runs before each test, so the pool is guaranteed empty at test entry. The success-path test can assert non-empty post-call without worrying about leaked state.
- **`account_acquire` raises `ConnectorRegistrationError`** (e.g., type registry was cleared between doctor and acquire): the inner `except Exception` catches it. Envelope reports `pool_warmed=False` + `pool_warm_error="<message>"`. Doctor's `status='ok'` is preserved. The test `test_doctor_probe_ok_warmup_failure_does_not_escalate` exercises this via monkeypatch (the raised exception is `ConnectorClientError`; could equally be any `Exception` subclass — the catch is intentionally broad).
- **`report.details` is None or unexpected type**: the existing `report.details` is a dict per `DoctorReport`'s contract (`the_one/connectors/base.py:DoctorReport`). The leg trusts the contract; `dict(report.details)` raises `TypeError` if violated, which propagates as 500 per the existing handler's "deliberately NOT caught" docstring claim. Don't add defensive code for a contract violation.
- **The page.route()-mocked tests in `tests/browser/test_connector_test_connection_button.py`**: these fulfill `/test/connect` from the test process and never invoke the real handler. They are unaffected by the api.py change. The leg's verification step confirms they still pass — no new test additions required in that file.
- **Concurrent calls to `test_connector_connection` for the same `account_id`**: `account_acquire` is single-flight per account by design — it routes through `agent_acquire(_ACCOUNT_POOL_AGENT_SLOT, account_id)` which serializes per-key under the `_pool`-module `_lock`. The second concurrent call either gets the same warm entry or waits briefly while the first finishes warming; both succeed; both report `pool_warmed=True`. No new race surface introduced by this leg.
- **The `_ACCOUNT_POOL_AGENT_SLOT` constant**: the pool's key tuple is `(_ACCOUNT_POOL_AGENT_SLOT, account_id)`. The success-path test imports the constant from `_pool` to match the clean-tuple-in idiom used at existing test sites (`tests/test_db_api.py:647,656,686,695`); the underscore prefix is a private-by-convention marker only, not a hard access barrier.
- **C1's text drift in OTHER test files**: `grep -rn "Distinct from the pool idle timeout" tests/` is expected to return ONLY the one site at line 417. Verify before edit; if other sites surface, expand scope (but F4 recon table R3 + the recent F3 work confirm single-site).
- **F3 flight.md annotation placement**: the annotation lands BETWEEN the Status block and the `## Contributing to Criteria` heading. This matches the agentic-workflow `SKILL.md:47` "annotate at the artifact header" framing. Do NOT modify any other part of F3 flight.md.
- **The `noqa: BLE001` comment** (or equivalent linter-marker): if the project's `pyproject.toml` does not configure a `BLE001` rule (broad-except check), the noqa is harmless. If a different linter rule applies (e.g. `B901`), use that ruleset's marker. Verify with `grep -rn "BLE001\|noqa.*broad" the_one/` to see what convention the project uses; if unclear, default to `# noqa: BLE001` (Ruff default) plus a one-line WHY comment.

## Files Affected

- `the_one/interfaces/web/api.py` — `test_connector_connection` body extended with the warmup block (gated on `report.status == "ok"`; inner try/except Exception; shallow-copy `report.details`; new `pool_warmed` + `pool_warm_error` keys).
- `tests/test_db_api.py` — three new tests added to `TestConnectorAccountDoctor` (`test_doctor_probe_success_warms_pool`, `test_doctor_probe_failed_skips_warmup`, `test_doctor_probe_ok_warmup_failure_does_not_escalate`); three existing tests updated (`test_doctor_probe_success`, `test_doctor_probe_configured_failure`, `test_doctor_probe_degraded_status`) to extend their asserted dicts with the new fields.
- `tests/browser/test_flow_studio_connector_account_editor.py` — line 417 assertion text updated to match source; comment at line 414 updated to match new intent (C1 closure).
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — one-line header annotation under the Status block (L4 body NOT modified).
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight.md` — L2 checkpoint + L2 leg checklist checked off.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight-log.md` — L2 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/02-test-connection-warms-pool-and-fix-session-continuation-test.md` — this artifact's status header updated through the lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; pytest runs green; F3 flight.md byte-diff confirmed)
- [x] `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountDoctor tests/browser/test_flow_studio_connector_account_editor.py::test_edit_session_continuation_round_trip tests/browser/test_connector_test_connection_button.py -x --timeout 60` passes
- [x] Update `flight-log.md` with L2 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L2 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F4 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23):

- `the_one/interfaces/web/api.py:test_connector_connection` — handler symbol confirmed at line 2573 with body running through ~2638 (read 2026-05-23). The body's structure (function-local imports → 404 path → unknown-type path → doctor try/except → final return) is locked.
- `the_one/connectors/_pool.py:account_acquire` — definition confirmed (`async def account_acquire(account_id: str) -> ConnectorClient` at the source line; F4 recon table R10 referenced line 830 but actual line is approximately 829 — minor drift; the symbol-form citation `_pool.py:account_acquire` is durable).
- `tests/browser/test_flow_studio_connector_account_editor.py:417` — assertion text `"Distinct from the pool idle timeout"` confirmed at line 417; surrounding comment at line 414 confirmed.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:368` — source text `"Inbound continues the same chat session within this window."` confirmed at line 368.
- `tests/test_db_api.py:TestConnectorAccountDoctor` — class confirmed at line 971; autouse `_isolation` fixture at line 983; `_create_stub_account` helper at line 1020; existing tests `test_doctor_probe_success` (line 1033), `test_doctor_probe_configured_failure` (line 1047), `test_doctor_probe_degraded_status` (line 1071), `test_doctor_probe_unknown_type` (line 1094), `test_doctor_probe_connector_client_error` (line 1142), `test_doctor_probe_unknown_account_returns_404` (line 1167), `test_doctor_probe_records_the_call` (line 1179) all confirmed. `class TestConnectorAccountPairingCodeAndAttached` at line 1196 is the insertion boundary for the three new tests.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — Status block at lines 3-4; L4 body at line 55 confirmed (text matches the F4 Design Decision citation verbatim).
- `the_one/agents.md` — `pool-warming-entrypoints-are-finite-and-named` and `two-concurrent-callers-reasoning` conventions exist post-L1 (referenced in test docstrings; verification at leg-implementation time depends on L1 having landed).

7 citation sites verified clean. One minor drift noted (`_pool.py:account_acquire` line 829 vs F4 recon table's `830` — single-line off-by-one; the symbol-form citation is durable across the drift). No structural drift.
