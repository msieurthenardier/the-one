# Leg: routes-and-studio

**Status**: completed
**Flight**: [Channel Contract](../flight.md)

## Objective
Expose the leg-1 core over HTTP — seven masked routes, the two dual-gated stub test seams — and give it a minimal Studio form with registered testids and browser tests, keeping all lanes green and the connector JS within its ≤650-line flight scope.

## Context
- Governing DDs: DD-2 (config keys the form edits), DD-3 (pairing route → manager's in-memory store), DD-7 (seven routes, `__MASKED__` sentinel round-trip per the provider-route pattern, DELETE stops the listener first), DD-9 (form fields + budget scope: ALL connector-attributable JS incl. shared-file additions), DD-10 (seams dual-gated on `dev_mode` AND `THE_ONE_STUB_TEST_ENDPOINT=1`; the `_EXPECTED_SEAMS` set in `tests/test_seam_routes_403_sweep.py` is deliberately hardcoded — extend it in this leg, that's the design), DD-11 (JS count at leg close).
- Leg 1 ground truth (flight log): manager API is `start_all(repo)` / `stop(account_id)` / `drain()` + the pairing store; plugin signature is `connect(account, encryptor, on_inbound)`; doctor exists on the Protocol. The three pre-existing `TestConnectorRepository` tests were already updated to DD-2 config shapes.
- **PUT semantics**: a save that changes credentials, `enabled`, or type must restart the listener (stop → start via the manager) — the pre-reset "save-reconnects-the-gateway" convention (`agents.md` history) holds; a config-only change (allowlist edit) may hot-apply or restart, implementer's choice, but MUST NOT leave a listener running on stale credentials.
- **Doctor surfaces binding health** (DD-4 trade-offs): report when the bound `default_agent` doesn't exist or lacks the send tool — the operator's foot-gun warnings live here.
- **Flight-1-debrief tripwire discipline (additive direction)**: new testids land in `docs/ui-testid-registry.md` in the SAME change as the JS that renders them (`test_ui_guards.py` diffs bidirectionally); new `index.html` script tags update `test_index_asset_cache_busting.py`'s exact count in the same pass; new seams extend `_EXPECTED_SEAMS`.
- Masking reference (design review correction): `Connector.secrets` is a free-form dict like `MCPSource.secrets` — reuse the generic per-key helpers `_looks_masked`/`_mask_secrets` (`api.py` ~1516-1935), NOT the LLM-provider single-column `_mask_api_key` pattern. Add connector rows to `tests/test_api_secret_mask_roundtrip.py`.
- **Manager surface confirmed sufficient** (design review): `manager.py` already has single-connector `start(account, encryptor)` alongside `stop(id)`/`start_all(repo, encryptor)`/`drain()` — PUT's restart is `stop` + fresh-row `start`; no API growth needed.
- **Stub registration in a live process (design review Q1, resolved)**: a dual-gated startup hook — at lifespan startup, iff `dev_mode` AND `THE_ONE_STUB_TEST_ENDPOINT=1`, register the stub plugin in the registry (the new-gate successor to the retired `THE_ONE_REGISTER_STUB_CONNECTOR` hook). Without it the leg-3 behavior test can never get a working stub listener. Owned by THIS leg with the seams.
- **`type: "stub"` reachability (Q2, resolved)**: add a tiny eighth route `GET /api/connectors/types` returning the types creatable on this instance — `"discord"` always, `"stub"` only when the dual gate is active; the create route enforces the same server-side; the Studio dropdown sources this route. (Mirrors the provider/MCP `/types` precedent; keeps the behavior test's Studio-created stub connector possible on the dev instance while unreachable in production.)
- **Rotation restart (Q3, resolved — in scope)**: `POST /api/encryption/rotate` must restart connector listeners after re-encrypting `connectors.secrets`, AND `manager._run()` re-fetches a fresh connector row before each reconnect attempt (the leg-1 snapshot capture means a rotated key strands the old ciphertext in the backoff loop → silent permanent reconnect failure). Both fixes + a test proving a listener survives rotation. The `manager.py` edit is deliberate leg-2 scope (same flight, uncommitted tree).

## Inputs
- Leg 1 landed (uncommitted): core package + tools, suite green 3,630 / 10 / 542.

## Outputs
- Seven routes in `api.py` (list/get/create/update/delete/test/pairing-code) + two `_test/stub` seams (inbound POST, outbound GET), all under the existing `/api` router.
- Studio `connector-editor` section: one new JS file + minimal shared-file wiring (`index.html` script tag, `studio.js` section registration/nav); fields per DD-9; doctor + pairing-code buttons.
- Testid registry rows; browser tests for the form (create/save-masked/doctor/pairing UI); seam-403 sweep extended; secret-mask round-trip tests for connectors.
- CSS: reuse existing Studio form classes; add connector-specific rules only if unavoidable (JS/CSS both count toward the ceiling's spirit).

## Acceptance Criteria
- [x] All seven routes behave per DD-7: masked secrets in every response; `__MASKED__` sentinel on PUT preserves the stored secret (round-trip test in `test_api_secret_mask_roundtrip.py`); create/update run the DD-2 validator (bad config → 422 with actionable message); DELETE stops the listener before the row dies (test via stub + manager spy)
- [x] PUT restarting semantics: credential/enabled/type change restarts the listener (test with stub: old listener stopped, new started); no stale-credential listener survives a save — implemented as an UNCONDITIONAL restart on every successful PUT (Edge Cases explicitly permits this variation); see Deviations re: no persisted "enabled" field
- [x] `POST /{id}/test` (doctor) returns plugin doctor output plus binding warnings (missing agent / agent lacks send tool / dangling default_agent); **with no plugin registered for the type — the NORM this flight, since Discord lands in Flight 3 — it returns a clean degraded/failed report ("no plugin registered for type X"), never a crash**
- [x] `GET /api/connectors/types` returns creatable types ("discord" always; "stub" iff dual gate); create rejects a type not in that set; the Studio dropdown sources it
- [x] `POST /{id}/pairing-code` 404s on an unknown connector id (repo-checked first), returns a code + expiry from the manager store otherwise; unit/route test proves one-time consumption through the HTTP path; a second request replaces (invalidates) the first
- [x] Rotation: after `POST /api/encryption/rotate`, a running stub listener reconnects successfully with the re-encrypted secrets (test: rotate, force a reconnect, assert live) — via the rotation-restart hook and `_run`'s fresh-row re-fetch
- [x] The dual-gated startup hook registers the stub plugin iff `dev_mode` AND `THE_ONE_STUB_TEST_ENDPOINT=1`; unregistered otherwise (asserted)
- [x] Both `_test/stub` seams 403 unless `dev_mode` AND `THE_ONE_STUB_TEST_ENDPOINT=1`; `test_seam_routes_403_sweep.py`'s `_EXPECTED_SEAMS` extended and green
- [x] Studio form: creates/edits a connector with the DD-2 fields (name, type, token masked, default agent dropdown from live agents list, allowlist peers+channels, always_listen, channel→agent map rows — NO "enabled" field, see Deviations), doctor button renders results, pairing button shows code+expiry; all rendered testids present in `docs/ui-testid-registry.md`; `test_ui_guards.py` and `test_design_tokens_a11y.py` green
- [x] `test_index_asset_cache_busting.py` updated with the new script tag and green
- [x] All four browser lanes green (`scripts/run-tests.sh --lane studio|chat|system|shared`); `make test-unit` green, no new skips/xfails; ruff clean
- [x] JS line count reported: new file + shared-file additions, vs the ≤650 flight scope (and the running ≤1,000 mission ceiling)
- [x] Flight log Leg Progress entry appended

## Verification Steps
- Route tests + mask round-trip + seam sweep via targeted `scripts/run-tests.sh` runs (FOREGROUND, `-x --timeout 30`); browser lanes after the form lands; full `make test-unit` at close.
- JS count: `wc -l` on the new file plus `git diff main --numstat` additions in `index.html`/`studio.js`/CSS.

## Implementation Guidance
1. Routes first (they're testable without UI): follow the provider-route masking pattern; place the connector block coherently in `api.py`; wire DELETE/PUT through the manager.
2. Seams next, with the `_EXPECTED_SEAMS` edit in the same change.
3. Form: register the section like existing Studio sections; keep it one file; agents dropdown sources the existing agents list API.
4. Testids + registry + guard expectations together (one pass).
5. Browser tests: form CRUD + masked redisplay + doctor + pairing; keep count small — the behavior test (leg 3) covers the end-to-end flow.
6. Lanes + suite + counts + flight log.

## Edge Cases
- **Create with `enabled: true`**: listener must start on create, not only on app restart.
- **Doctor on a disabled connector**: still runs (doctor is diagnosis, not traffic).
- **Pairing code requested twice**: second request replaces the first (old code invalidated) — one live code per connector.
- **Masked sentinel on create** (not just update): reject — there's no stored secret to preserve.
- **Deleting a connector with live sessions**: sessions and history remain (kept columns); only the listener and row go.
- **Pairing code on a connector whose listener isn't running**: allowed — the code simply expires unused (harmless by TTL); state it, don't leave it implicit.
- **Stale docstring cleanup**: `test_seam_routes_403_sweep.py::test_discovered_seam_set_matches_expected`'s "four known seams" docstring predates this leg (set has 2) — correct it while editing the file.

## Files Affected
New: `the_one/interfaces/web/static/js/areas/studio/connector-editor.js`, new route/browser test files.
Edited: `the_one/interfaces/web/api.py`, `index.html`, `js/areas/studio.js`, `docs/ui-testid-registry.md`, `tests/test_seam_routes_403_sweep.py`, `tests/test_api_secret_mask_roundtrip.py`, `tests/test_index_asset_cache_busting.py`, guard helpers if prefix lists need rows, CSS only if unavoidable.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` + all four lanes)
- [x] Update flight-log.md with leg progress entry (incl. JS count)
- [x] Set this leg's status to `landed` — commit happens at flight end
- [x] Check off this leg in flight.md
