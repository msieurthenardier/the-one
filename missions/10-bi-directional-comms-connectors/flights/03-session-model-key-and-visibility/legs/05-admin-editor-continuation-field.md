# Leg: admin-editor-continuation-field

**Status**: completed
**Flight**: [Session Model — Schema, Key Normalization, Visibility](../flight.md)

## Objective

Surface the per-account `session_continuation_seconds` field in the Studio editor's Lifecycle section as a sibling to F2's `idle_timeout_seconds` field, wire the round-trip through the existing field-agnostic REST PUT path, and add a regression test confirming that changing ONLY this field does NOT trigger pool eviction. Also remove the now-stale forward-reference comment at the existing helper-text site (the F2 hint at `studio/connector-account-editor.js:137` says "Flight 3 will add a chat-session continuation window field next to this one" — Flight 3 IS adding it; remove the forward reference).

## Context

- **Parent flight design decisions** (see `flight.md`):
  - The chat-session continuation window is consumed by leg-3's `resolve_session` at inbound-dispatch time. Operator-configurable per-account, populated by the operator via the Studio editor.
  - Eviction trigger on the new field: NONE. Pool entries represent the warm gateway connection; `session_continuation_seconds` is consulted by the resolver at inbound-dispatch time and is NOT cached in pool state. A change takes effect on the next inbound after the PUT commits.
  - REST PUT route is field-agnostic (`interfaces/web/api.py:2215-2218` per F2's verification — `merged = existing.model_dump(); merged.update(data); ConnectorAccount.model_validate(merged)`). The new field round-trips for free via Pydantic — no new API code, no new route.
- **F2's idle_timeout field landing pattern** (`connector-account-editor.js:120-140`): a single `editor-section` Lifecycle wrapper containing field-row + helper-text. F3 L5 adds a SECOND field-row + helper-text pair to the SAME wrapper — operator sees both timeouts adjacent in one section. Helper text disambiguates them so the operator understands "pool TTL is about the gateway warm-keep; continuation window is about when a new platform message starts a fresh chat session."
- **F2's `test_no_op_put_does_not_evict` at `tests/test_db_api.py:626`** is the structural template for `test_session_continuation_change_does_not_evict`. The new test creates an account, warm-acquires a pool entry, PUTs ONLY the new field, asserts the pool entry survives.
- **Form-snapshot tracking pattern** at `connector-account-editor.js:329` (`staticFields = ['name', 'type', 'idle_timeout_seconds']`): F3 L5 adds `'session_continuation_seconds'` to this array so the dirty-form gates see the new field. The form-data extraction at line 743+ needs a parallel `session_continuation_seconds` block (parse-as-number, fallback to raw string on parse failure so the backend returns 422 with a clean error).
- **Pre-existing F1+F2 carry-forward maintenance** noted in flight log: the F2 Lifecycle helper text contains a now-stale forward reference. Leg 5 retires it.

## Inputs

State that must exist before this leg runs:

- Legs 1+2+3+4 of this flight are `landed` (1877 tests passing on `flight/03-session-model-key-and-visibility`; uncommitted per batched-review model).
- `the_one/db/models.py:ConnectorAccount.session_continuation_seconds` (leg 1 — `int | None = None` with `1 ≤ value ≤ 604800` validator).
- `the_one/db/repositories.py:ConnectorAccountRepository.create/update/_row_to_model` (leg 1 — round-trips the new field).
- `the_one/interfaces/web/api.py:2215-2218` — field-agnostic PUT route (F2; verified by leg-1 + leg-3 design reviews).
- `the_one/interfaces/web/api.py` PUT eviction-on-secrets-change logic (F2 leg 2; line ~2223 per architect verification — `if existing.secrets != resolved_secrets`).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:120-140` — F2's Lifecycle section (the template for the new field-row + helper-text pair).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:329` — `staticFields` array (F3 L5 extends).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:743` — `idleEl` extraction + payload-dict assembly (F3 L5 mirrors).
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:137` — stale forward-reference comment ("Flight 3 will add ..." — to be removed).
- `tests/test_db_api.py:626` — `test_no_op_put_does_not_evict` (template for new test).
- `tests/browser/test_flow_studio_connector_account_editor.py` — F2 browser test file for the editor flow (extension target for the new round-trip browser test).
- Working tree on branch `flight/03-session-model-key-and-visibility` with leg 1-4 changes uncommitted.

## Outputs

State that must exist after this leg completes:

- `connector-account-editor.js` Lifecycle section has a NEW second field-row + helper-text pair for `session_continuation_seconds`:
  - Label: `Chat-session continuation window (s)` (operator-facing copy decided at implementation — leg author may adjust if a better phrasing surfaces).
  - Input: `data-field="session_continuation_seconds"` `data-testid="connector-account-continuation-input"`, `type="number"`, `placeholder="Use default (24 hours)"`. No frontend min/max — backend Pydantic validator owns the truth.
  - Helper text: `Inbounds on the same conversation continue an existing chat session within this window. After this many seconds of platform silence, the next inbound starts a fresh session. Leave empty to use the system default (24 hours). Distinct from the pool idle timeout above (which controls gateway warm-keep, not session lifecycle).`
- `staticFields` array (`connector-account-editor.js:329`) extended to include `'session_continuation_seconds'`.
- Form-data extraction (`connector-account-editor.js:743+`) parses the new field parallel to `idle_timeout_seconds` and includes it in the payload dict.
- The F2 helper-text comment at line 137 ("Flight 3 will add a chat-session continuation window field next to this one.") is REMOVED — leg 5 is landing it.
- `getAccountForRender` / display-mode rendering (`connector-account-editor.js:~85-90` where `ttlSummary` is set) — extended OR a parallel `continuationSummary` is rendered in the editor header. Leg-5 author's call based on what fits the existing header pattern.
- New test `test_session_continuation_change_does_not_evict` in `tests/test_db_api.py` (after `test_no_op_put_does_not_evict` at line 626 — natural placement) covering:
  - Create account with `session_continuation_seconds=null`, no secrets-change.
  - Warm-acquire the pool entry.
  - PUT `{"session_continuation_seconds": 3600}`.
  - Assert response 200.
  - Assert `("test-agent", account_id) in pool_mod._pool` STILL TRUE (entry not evicted).
- **Validator boundary tests: SKIP.** The design-review confirmed leg-1 already added these at `tests/test_db_repositories.py:925, :933, :943` (`test_session_continuation_seconds_validator_rejects_zero`, `_rejects_one_week_plus_one`, `_accepts_bounds`). Adding REST-level parametrized duplicates would inflate maintenance cost without new coverage. Leg 5 does NOT add validator boundary tests.
- New browser test scenario in an existing studio connector-account browser test file (`tests/browser/test_flow_studio_connector_account_editor.py` is the natural home — leg-5 author's call): open the editor, fill the new field, save, reopen, verify the value round-trips. Assert helper text is visible and distinguishable from the pool-TTL helper text (different `data-testid` or different DOM neighborhood).
- Flight log gains "Leg Progress: admin-editor-continuation-field" entry.
- Leg status flipped to `landed`. This leg ticked off in `flight.md` under `### Legs`.

## Acceptance Criteria

- [ ] `connector-account-editor.js` Lifecycle section renders TWO field-row + helper-text pairs (idle_timeout_seconds + session_continuation_seconds). Visually adjacent in the same `editor-section` wrapper.
- [ ] New input element: `data-field="session_continuation_seconds"`, `data-testid="connector-account-continuation-input"`, `type="number"`, `placeholder="Use default (24 hours)"` (exact placeholder text minor — author may polish; the data attributes are the testable contract).
- [ ] New helper text element with `data-testid="connector-account-continuation-hint"`. Text distinguishes the continuation field from the pool-TTL field explicitly.
- [ ] F2's forward-reference comment at line 137 ("Flight 3 will add a chat-session continuation window field next to this one.") is REMOVED. The remaining F2 helper text reads as a self-contained description of the pool-TTL field.
- [ ] `staticFields` array at line 329 includes `'session_continuation_seconds'`.
- [ ] Form-data extraction at line 743+ has a parallel `continuationEl` / `continuationValue` block mirroring the `idleEl` / `idleValue` pattern, with:
  - Empty input → `null` payload (Pydantic interprets as "no per-account override").
  - Non-empty integer → integer payload.
  - Non-empty non-integer string → pass-through; backend Pydantic returns 422.
- [ ] Payload dict at line 758-764 includes `session_continuation_seconds: continuationValue`.
- [ ] `test_session_continuation_change_does_not_evict` in `tests/test_db_api.py` passes: PUT with ONLY `session_continuation_seconds` change preserves the warm pool entry.
- [ ] Browser test scenario for the round-trip lands in an existing studio editor browser test file (leg-5 author picks which one — the editor.py file is the natural home, but a navigation/create-and-test file may also work).
- [ ] `make test` clean (no regressions; new test count is added).
- [ ] `make test-browser` clean (the new browser-flow scenario passes).
- [ ] `make lint` clean.
- [ ] Flight log updated with leg-completion entry.
- [ ] Leg status flipped to `landed`. This leg ticked off in `flight.md`.

## Verification Steps

- **New field renders** — `grep -n "session_continuation_seconds\|continuation-input\|continuation-hint" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` shows the new element + helper-text + form-extraction sites.
- **Forward-reference removed** — `grep -n "Flight 3 will add" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returns NO matches.
- **`staticFields` updated** — `grep -n "staticFields.*session_continuation" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` shows the new entry.
- **Backend round-trip works** — already verified at leg 1 (repository round-trip + Pydantic validator); F3 L5 verifies end-to-end via REST + browser.
- **Eviction non-trigger** — `docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountAPI::test_session_continuation_change_does_not_evict -xvs --timeout 30` passes.
- **Validator boundary tests** — if added at REST level: `docker exec the-one pytest tests/test_db_api.py -k "session_continuation_seconds" -xvs --timeout 30` passes.
- **Browser round-trip** — `docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -xvs --timeout 60` includes the new scenario.
- **Full suite** — `docker exec the-one pytest -x --timeout 30` green (1877 + new tests).
- **Lint** — `docker exec the-one ruff check the_one/ tests/` clean.

## Implementation Guidance

1. **Update the Lifecycle section in `connector-account-editor.js`**. The current block at lines 120-140 looks like:

   ```javascript
   // ── Lifecycle section ─────────────────────────────────────────────
   var idleValue = (!isCreate && account.idle_timeout_seconds != null) ? account.idle_timeout_seconds : '';
   html += '<div class="editor-section">';
   html += '<div class="section-title">Lifecycle</div>';
   html += '<div class="field-row admin-pf-row">';
   html += '<label for="cf-idle-timeout">Pool idle timeout (s)</label>';
   html += '<input class="field-input admin-pf-input" id="cf-idle-timeout" type="number" ' +
           'data-field="idle_timeout_seconds" data-testid="connector-account-idle-timeout-input" ' +
           'value="' + escapeAttr(String(idleValue)) + '" placeholder="Use default (30 min)" />';
   html += '</div>';
   html += '<div class="field-row admin-pf-row">';
   html += '<label></label>';
   html += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
           'Warm connector connections are reaped after this many seconds of inactivity. ' +
           'Leave empty to use the system default (30 min). ' +
           'Flight 3 will add a chat-session continuation window field next to this one.' +
           '</small>';
   html += '</div>';
   html += '</div>';
   ```

   Replace with:

   ```javascript
   // ── Lifecycle section ─────────────────────────────────────────────
   var idleValue = (!isCreate && account.idle_timeout_seconds != null) ? account.idle_timeout_seconds : '';
   var contValue = (!isCreate && account.session_continuation_seconds != null) ? account.session_continuation_seconds : '';
   html += '<div class="editor-section">';
   html += '<div class="section-title">Lifecycle</div>';

   // Pool idle timeout (F2)
   html += '<div class="field-row admin-pf-row">';
   html += '<label for="cf-idle-timeout">Pool idle timeout (s)</label>';
   html += '<input class="field-input admin-pf-input" id="cf-idle-timeout" type="number" ' +
           'data-field="idle_timeout_seconds" data-testid="connector-account-idle-timeout-input" ' +
           'value="' + escapeAttr(String(idleValue)) + '" placeholder="Use default (30 min)" />';
   html += '</div>';
   html += '<div class="field-row admin-pf-row">';
   html += '<label></label>';
   html += '<small class="form-hint" data-testid="connector-account-idle-hint">' +
           'Warm connector connections are reaped after this many seconds of inactivity. ' +
           'Leave empty to use the system default (30 min).' +
           '</small>';
   html += '</div>';

   // Chat-session continuation window (F3 L5)
   html += '<div class="field-row admin-pf-row">';
   html += '<label for="cf-continuation-window">Chat-session continuation window (s)</label>';
   html += '<input class="field-input admin-pf-input" id="cf-continuation-window" type="number" ' +
           'data-field="session_continuation_seconds" data-testid="connector-account-continuation-input" ' +
           'value="' + escapeAttr(String(contValue)) + '" placeholder="Use default (24 hours)" />';
   html += '</div>';
   html += '<div class="field-row admin-pf-row">';
   html += '<label></label>';
   html += '<small class="form-hint" data-testid="connector-account-continuation-hint">' +
           'Inbounds on the same conversation continue an existing chat session within this window. ' +
           'After this many seconds of platform silence, the next inbound starts a fresh session. ' +
           'Leave empty to use the system default (24 hours). ' +
           'Distinct from the pool idle timeout above, which controls gateway warm-keep — not chat-session lifecycle.' +
           '</small>';
   html += '</div>';

   html += '</div>';
   ```

   Note the removal of the "Flight 3 will add ..." forward-reference. The pool-TTL hint becomes self-contained.

2. **Update `staticFields` at line 329**:

   ```javascript
   var staticFields = ['name', 'type', 'idle_timeout_seconds', 'session_continuation_seconds'];
   ```

3. **Update the form-data extraction at line 743+**. The current block extracts `idleEl` / `idleValue`; mirror it for `session_continuation_seconds`:

   ```javascript
   var idleEl = container.querySelector('[data-field="idle_timeout_seconds"]');
   var idleRaw = idleEl ? (idleEl.value || '').trim() : '';
   var idleValue = null;
   if (idleRaw !== '') {
     var parsed = Number(idleRaw);
     if (!isNaN(parsed) && isFinite(parsed)) {
       idleValue = Math.trunc(parsed);
     } else {
       idleValue = idleRaw;
     }
   }

   var contEl = container.querySelector('[data-field="session_continuation_seconds"]');
   var contRaw = contEl ? (contEl.value || '').trim() : '';
   var contValue = null;
   if (contRaw !== '') {
     var contParsed = Number(contRaw);
     if (!isNaN(contParsed) && isFinite(contParsed)) {
       contValue = Math.trunc(contParsed);
     } else {
       contValue = contRaw;
     }
   }

   return {
     name: name,
     type: typeValue,
     config: config,
     secrets: secrets,
     idle_timeout_seconds: idleValue,
     session_continuation_seconds: contValue
   };
   ```

4. **Header summary rendering** (`connector-account-editor.js:~85-90` — the `ttlSummary` site). Decide whether to add a `continuationSummary` to the editor header. Two options:
   - (a) Leave header showing only `ttlSummary` (the existing F2 idle-TTL summary); the new field is visible in the Lifecycle section but not in the header chip.
   - (b) Add a second summary chip alongside `ttlSummary` showing the continuation window.

   **Recommendation**: option (a) for leg 5 minimal scope. The header is a glance-summary, not exhaustive; adding a second chip risks crowding. Operator who cares about the continuation value scrolls to the Lifecycle section. If user feedback says otherwise, option (b) is a cheap follow-up.

5. **Add `test_session_continuation_change_does_not_evict`** to `tests/test_db_api.py` after `test_no_op_put_does_not_evict` (line 626). Mirror the existing template's shape:

   ```python
   async def test_session_continuation_change_does_not_evict(self, client: AsyncClient) -> None:
       """PUT changing ONLY session_continuation_seconds MUST NOT evict the warm pool entry.

       Pool entries represent the gateway warm-keep; session_continuation_seconds
       is consulted by the resolver at inbound-dispatch time and is NOT cached
       in pool state. A change takes effect on the next inbound after the PUT
       commits; no in-memory invalidation is needed.

       M10 F03 L05 — design-decision verification (see flight 03 Design
       Decisions: "Eviction trigger for session_continuation_seconds change
       — NONE").
       """
       from the_one.connectors import _pool as pool_mod
       from the_one.connectors._pool import acquire

       create = await client.post(
           "/api/connector-accounts",
           json={
               "name": "Bot",
               "type": "stub",
               "secrets": {"BOT_TOKEN": "real"},
           },
       )
       account_id = create.json()["id"]

       await acquire("test-agent", account_id)
       assert ("test-agent", account_id) in pool_mod._pool

       resp = await client.put(
           f"/api/connector-accounts/{account_id}",
           json={"session_continuation_seconds": 3600},
       )
       assert resp.status_code == 200

       # Pool entry survives — the new field is NOT part of the eviction trigger.
       assert ("test-agent", account_id) in pool_mod._pool

       # And the new value round-tripped (one extra assertion vs. F2's template).
       getrr = await client.get(f"/api/connector-accounts/{account_id}")
       assert getrr.json()["session_continuation_seconds"] == 3600
   ```

6. **Validator boundary tests — DO NOT ADD.** Design-review verified that leg 1 already added them at `tests/test_db_repositories.py:925-963`. Adding REST-level parametrized tests would duplicate without new coverage. Skip.

7. **Browser test scenario**. Extend `tests/browser/test_flow_studio_connector_account_editor.py` with a new test method (or add a sibling file if cleaner). The scenario:
   - Create a connector account.
   - Open the editor.
   - Verify both Lifecycle fields are visible with the right `data-testid` attributes.
   - Fill the `connector-account-continuation-input` with `3600`.
   - Click Save.
   - Reopen the editor.
   - Verify the input value is `3600` (round-trip success).
   - Verify the helper text under the input contains the disambiguating language ("distinct from the pool idle timeout").

   Use the existing F2 editor browser test as the template — same pattern of `page.fill`, `page.click`, `page.locator(...).input_value()` assertions.

8. **Test execution**:
   ```
   docker exec the-one pytest tests/test_db_api.py::TestConnectorAccountAPI -x --timeout 30 -v
   docker exec the-one pytest tests/browser/test_flow_studio_connector_account_editor.py -x --timeout 60 -v
   docker exec the-one pytest -x --timeout 30                # full unit suite
   ```

9. **Update flight log** with "Leg Progress: admin-editor-continuation-field" entry. Capture: timestamps, summary, test-count delta from leg 4's 1877 unit + the browser test count from leg 4's baseline.

10. **Flip leg status to `landed`**. Tick leg 5 in `flight.md`. Signal `[HANDOFF:review-needed]`. Do NOT commit.

## Edge Cases

- **Empty input on create**: operator creates an account without filling the continuation field. JS form-snapshot returns `null` for `session_continuation_seconds`. Backend Pydantic accepts None. Account is created with the field NULL; resolver falls through to env-var/default at inbound time. Expected.

- **Operator clears an existing value (sets the field empty)**: JS sends `null`. Backend Pydantic accepts. Repository writes NULL. Resolver falls through to env-var/default. Expected.

- **PUT with a `session_continuation_seconds` change that ALSO changes a secret**: the F2 secrets-change eviction logic at `api.py:~2223` fires for the secrets change; the new field rides along. Eviction happens because of the secret, not because of the new field. Confirm by writing a test that PUTs both changes in one request — eviction fires (because secrets changed) AND the new field round-trips. **Optional** — leg-5 author's call whether to add this combined-change test or rely on the orthogonality of the eviction-trigger logic.

- **Out-of-range value at PUT time**: backend Pydantic validator returns 422 with the model-defined error message. Frontend currently doesn't surface 422 cleanly for the existing `idle_timeout_seconds` field either — both share the same backend-validation-only path. If this is a UX concern, it's a F2-and-F3 cross-cutting fix, NOT F3 L5 scope.

- **JS form-extraction passes a non-integer string** (operator types "abc"): JS sends `"abc"`. Backend Pydantic validator returns 422. Same path as out-of-range — backend owns the validation.

- **Pre-existing `getAccountForRender` / display-mode rendering of the field**: confirm the display-mode (non-edit) rendering of an account also shows the new field if it's set. Read the existing `ttlSummary` / display-mode code at `connector-account-editor.js:~85-90` for the pattern; mirror or skip per leg-5 author's call.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — Lifecycle section gains second field-row + helper text; staticFields, form-data extraction, payload-dict assembly extended; F2 forward-reference comment removed
- `tests/test_db_api.py` — new `test_session_continuation_change_does_not_evict` + (optional) validator boundary tests
- `tests/browser/test_flow_studio_connector_account_editor.py` — new browser test scenario for round-trip
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight-log.md` — leg-completion entry
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/flight.md` — tick leg 5
- `missions/10-bi-directional-comms-connectors/flights/03-session-model-key-and-visibility/legs/05-admin-editor-continuation-field.md` — this file's status → `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (scoped + full unit + browser)
- [ ] Lint clean
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md's Legs list
- [ ] Do NOT commit — agentic-workflow batched-review model defers commit to flight end
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

8 citations verified against current code at leg design time:

- `connector-account-editor.js:120-140` — Lifecycle section block (verified).
- `connector-account-editor.js:137` — "Flight 3 will add a chat-session continuation window field next to this one." (verified — the stale forward reference to retire).
- `connector-account-editor.js:329` — `staticFields = ['name', 'type', 'idle_timeout_seconds']` (verified).
- `connector-account-editor.js:743-764` — `idleEl` extraction + payload-dict assembly (verified).
- `connector-account-editor.js:~85-90` — `ttlSummary` display-mode site (approximate; verified by reading the file's header-summary rendering).
- `tests/test_db_api.py:626` — `test_no_op_put_does_not_evict` (verified at line 626).
- `tests/browser/test_flow_studio_connector_account_editor.py` — extant browser test file (verified).
- F2 PUT eviction logic at `api.py:~2223` — verified by F2 architect's reference and by leg-3 design review.
