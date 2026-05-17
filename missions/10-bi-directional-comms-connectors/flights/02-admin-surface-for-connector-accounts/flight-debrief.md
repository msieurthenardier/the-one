# Flight Debrief: Admin Surface for Connector Accounts

**Date**: 2026-05-17
**Flight**: [Admin Surface for Connector Accounts](flight.md)
**Status**: landed
**Duration**: 2026-05-17 (single orchestrated session)
**Legs Completed**: 6 of 6

## Outcome Assessment

### Objectives Achieved

Shipped the full operator-facing REST + Studio admin surface for connector accounts:

- Schema v15 migration adds `idle_timeout_seconds INTEGER NULL` to `connector_accounts`; Pydantic validator enforces `1 ≤ value ≤ 604800` (catches ms-vs-s typos); repository round-trip in place; `_resolve_ttl_seconds(override: int | None = None)` threads the per-account value through the pool's TTL resolver at `acquire()` time.
- `/api/connector-accounts` REST surface: GET (list / by-id / types), POST (with 201 on create), PUT (with per-key `__MASKED__` resolution mirroring `api.py:910-926` minus the OAuth/cache blocks), DELETE (with eviction-before-delete). 12 tests in `tests/test_db_api.py::TestConnectorAccountAPI` pin the masked-secret regression nets and the eviction semantics.
- `POST /api/connector-accounts/{account_id}/test/connect` doctor probe returns `{status, message, details}` (design adjustment from the flight spec's `{status, details}` — `message` is mandatory on `DoctorReport`). Error envelopes for unknown-type and `ConnectorClientError` both return HTTP 200 so the UI banner renders inline. 7 tests in `TestConnectorAccountDoctor`.
- Pool eviction wired into the encryption-rotation transaction at `rotate_encryption_key`: AFTER `await conn.commit()`, BEFORE the on-disk key replace, OUTSIDE the existing commit `try/except`, with its own log-and-continue handler. F1 debrief carry-forward closed; `test_rotation_evicts_warm_pool_entries` is the regression net.
- Studio "Connector Accounts" section as the fourth nav entry: `connector-accounts-grid.js` (entity-tile grid, parallel to `mcp-servers-grid.js`); full `connector-account-editor.js` (898 LoC) with editor-header / Connection / Credentials / Lifecycle / Test Connection / Danger Zone sections; "Create & Test" combined-action button on create-mode via the `_pendingProbeReport` module-level one-shot hand-off; labeled k/v details renderer with secret-shaped-value passthrough.
- 22 new browser tests across three new files + targeted updates to leg-5's nav file and to `test_flow_studio_navigation.py`'s keyboard-nav assertions; design-language screenshots filed under `tests/browser/__snapshots__/connector-account-editor/` (gitignored).

### Mission Criteria Advanced

This flight advances five of the mission's success criteria:

- **"An operator can register, edit, and remove connector accounts ... through an Admin surface ..."** — REST surface + Studio editor land the operator-visible mechanics. Fully satisfied for Flight 2's scope; `/api/connector-accounts/types` returns `[]` in production until Flight 8 registers Discord.
- **"A doctor-style probe accessible from each connector account's Admin detail page ..."** — `POST /api/connector-accounts/{account_id}/test/connect` ships; the UI banner renders the `DoctorReport` envelope; the stub-plugin probe runs end-to-end against the F1 fixture.
- **"Credentials never appear in plaintext outside the encryption boundary ..."** — masked-on-response + `__MASKED__`-sentinel-on-request implemented; `raw_value not in resp.text` regression nets in every secret-creating test.
- **"Each connector-attached session has a defined lifecycle ... surfaces from the connector account's Admin detail page as a configurable parameter"** — Flight 2 surfaces the **connector-pool idle-TTL** per the disambiguation Design Decision; the chat-session lifecycle is Flight 3's territory and lands next to this field.
- **"Each layer of the integration has automated coverage ..."** — REST-surface coverage and browser-flow coverage land on top of Flight 1's pool-level regression baseline.

The mission criterion "The Admin connector-account surface ... meets the M04/M06 design-language quality bar without alignment-flight rework" is advanced but is gated by human review of the design-language screenshots filed during leg 6. No alignment rework triggered during the flight.

## What Went Well

- **Bottom-up sequencing paid off.** Each leg's outputs were the next leg's inputs (schema → model → repo → REST → doctor → frontend). Zero backtracking across six legs.
- **Convention adherence is uniformly clean.** `function-local-import-to-break-load-cycle` (codified in L1) reads as a true convention now — cited inline at every new import site that breaks a cycle (`api.py:2236-2238` for PUT eviction, `:2256-2258` for DELETE eviction). `verbatim-message-equality` holds across the 404 / unknown-type / `ConnectorClientError` envelopes. `structural-Protocol-satisfaction` extended cleanly via the StubPlugin's new `doctor_should_raise` ClassVar without inheritance.
- **The architect-refined resolver shape (Idle-TTL persist + wire + `int | None` override) is the strongest decision in the flight.** The pool layer stays ignorant of which model field drives the override; the model owns the field name; the resolver owns the precedence. Any future flight that wants to swap the source of the override (e.g. an agent-level override) only edits the call site.
- **The L5→L6 placeholder-editor pattern was a small forward-looking deviation that decoupled routing-bug detection from editor-shape detection.** Leg 5 shipped a 35-LoC placeholder mount; leg 6 wholesale-replaced with the 898-LoC real editor. The handoff was a 2-line mechanical rename of two browser-test selectors. Worth lifting to a methodology note.
- **Per-leg first-scoped-test-run deviations cadence worked.** All six leg deviations (L2: TestSchemaV13 column-set, L3: `_load_account` autouse-fixture binding, L4: `DoctorReport.message`, L5: roving-tabindex symmetry, L6: PUT validator bypass, L6: stub test-seam) surfaced on the first scoped-test run rather than in code review. Each was documented inline in the flight log within the same leg-completion cycle.
- **Masked-secret regression nets validate behavior, not lines.** The `no_op_put_does_not_evict` / `dropping_a_key_evicts` / `secrets_change_evicts` / `adding_a_new_key_evicts` quartet, plus the `raw_value not in resp.text` checks scattered across the leg-3 test class, are textbook examples of acceptance criteria becoming named test functions.

## What Could Be Improved

### Process

- **Planning-audit grep should run two passes.** L5's design review surfaced that the leg artifact's pre-implementation grep missed `test_flow_studio_navigation.py` (the test enumerated section buttons by `data-section` attribute, not by literal `to_have_count(3)`). L6 had the same shape: the audit caught the literal `connector-account-editor-placeholder` selector but didn't pre-enumerate all keyboard-nav wrap-around targets pinned in adjacent tests. **Codify a two-pass grep in the leg-planning checklist**: (1) literal pattern match; (2) any test file that touches the same DOM testids / table columns / route prefixes.
- **L6 should retroactively have been split.** The spec flagged L6 as a candidate for 5a/5b if browser-fixture plumbing got non-trivial. It did — the `THE_ONE_REGISTER_STUB_CONNECTOR=1` env-var test seam added to the production lifespan is significant enough that bundling it with 22 browser tests + the full editor JS + the PUT validator fix obscured it. The test seam is sound, but adding a production-code env-var gate without its own design-review surface area is the kind of decision a debrief should catch. Methodology lesson, not a fire.
- **Schema column ALTER discipline now has two occurrences (F1 L2 v14 `name`, F2 L1 v15 `idle_timeout_seconds`); formalize.** Each time a column ALTER lands, the planning audit must check **both** the head-version assertion (`assert CURRENT_VERSION == N`) AND the column-set assertion sites (`TestSchemaV{N-2}::test_v{N-2}_*_columns`). L2 surfaced a `TestSchemaV13` column-set miss on first run, identical in shape to F1 L2's near-miss. **Action**: add a meta-bullet to `agents.md` "Connector type extension checklist" enumerating both assertion families.

### Technical

- **The MCP and provider PUT routes carry the same `model_copy(update=data)` validator-bypass that L6 fixed for connectors.** `the_one/interfaces/web/api.py:2393` (`update_mcp_source`) and `:2606` (`update_provider`) both still use the pattern that silently bypasses Pydantic v2 field validators. This means an out-of-range value submitted to `PUT /api/mcp-sources/{id}` or `PUT /api/providers/{id}` for any validated field today silently stores instead of returning 422. The L6 fix proves the gap is real. **Recommendation**: a maintenance leg (M10 end-of-mission, or earlier maintenance flight) does the symmetric fix at both sites. ~10 LoC each, behavior-preserving for valid payloads.
- **Shared-pool extraction got harder, not easier.** The connector pool tracks `last_activity` on the `_RegistryEntry` while the MCP pool tracks it on the client (`mcp/_pool.py:338` vs `connectors/_pool.py:318`). The divergence is documented inline and justified per-pool, but a shared-pool abstraction has to either bridge two activity-source conventions or pick one and migrate the other. F1's "deferred shared-pool extraction" Known Issue is now more expensive to discharge than it was on `main` — scope is clearer, cost is higher.
- **Stub-visibility stance shifted by another name.** The flight spec says "stub plugin is NOT exposed via `/api/connector-accounts/types` in production." Literally still true — production never sets `THE_ONE_REGISTER_STUB_CONNECTOR=1`. But the L6 test seam means the stub is **registerable in dev mode** via a single env var, which is a different threat surface than "registered only from test fixtures." Before Flight 8, this needs to be pinned down: either accept "stub is dev-mode opt-in" (and update the spec language + `connectors/README.md`) or add a runtime guard refusing stub registration when any non-stub connector is also present.

### Documentation

- **`connectors/README.md` §3 needs an API-edge contract paragraph.** The L1 skeleton-plugin block landed there, but the new `__MASKED__`-at-API-edge invariant lives only in `api.py:2181-2207` inline comments and the `_connector_account_response` docstring. A one-paragraph addition describing the masked-on-response / `__MASKED__`-sentinel-on-request contract would make the surface discoverable for Flight 8's per-type config validation.
- **`connectors/README.md` skeleton plugin's `doctor()` returns `details={}` — needs a non-empty `message` example.** The doctor-probe envelope inherited by future flights is `{status, message, details}`; the skeleton currently shows an empty-details path but doesn't demonstrate the `message` field carrying operator-facing summary text. Small update; small impact, but pre-empts a Flight 8 misstep.
- **README's persistence/subsystem section now mentions connector accounts** (single line added post-flight, commit `7c45c74`). Sufficient for now.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L2: `TestSchemaV13` column-set assertion update added beyond the spec's "Files Affected" list | The leg artifact enumerated head-version assertion sites but not column-set assertion sites; surfaced on first scoped-test run. Second occurrence of this pattern (F1 L2 had the v13 equivalent miss). | **Yes** — codify the column-set audit as part of the schema-ALTER planning checklist in `agents.md`. |
| L3: `_load_account` monkeypatch added to the `_isolation` autouse fixture | The function-local-import-to-break-load-cycle convention means `_load_account`'s `get_connection` binding can't be patched from `api.py`'s namespace; patching at the function source is required for `acquire()`-touching tests. Genuinely emergent — only discoverable by running. | **Yes** — add a planning note: "any test that calls `acquire(...)` must patch `_load_account` directly." |
| L4: doctor-probe response envelope is `{status, message, details}`, not the spec's `{status, details}` | `DoctorReport.message: str` is a required field on the F1-frozen dataclass; omitting it would leave the UI banner without a one-sentence summary. | No — accept the adjustment and update the spec wording. Future flights inherit `{status, message, details}`. |
| L5: 4th-tabindex assertion added to `test_studio_section_nav_roving_tabindex` | The leg artifact's grep heuristic (`to_have_count(3)`) didn't catch enumeration-by-`data-section`-attribute. Test passed before the addition (no failure), added for symmetry. | **Yes** — see "two-pass grep" methodology note above. |
| L6: PUT validator-bypass fix (`model_copy(update=data)` → `model_validate(existing.model_dump() \| data)`) | Pydantic v2's `model_copy(update=...)` bypasses field validators, silently storing `idle_timeout_seconds=0` instead of surfacing the canonical 422. Real bug, surfaced by a real test. | **Yes** — apply the symmetric fix to MCP + provider PUT routes in maintenance. |
| L6: `THE_ONE_REGISTER_STUB_CONNECTOR=1` test-seam env var added to `app.py` lifespan | Browser tests run in a subprocess; class-level `StubPlugin.doctor_response =` mutation doesn't reach the server. Needed a server-side opt-in to register the stub for browser tests. | Partially — see "stub-visibility" debt item above; pin down the policy before Flight 8 lands. |
| Post-flight: L6's planning grep missed `test_flow_studio_navigation.py` similar to L5 | Methodology not yet codified. | **Yes** — the two-pass-grep convention is now flagged twice. |

## Key Learnings

- **Bottom-up sequencing is the right default for a flight that builds vertically through a stack** — persistence → service → REST → frontend. Six legs without backtracking proves the pattern.
- **Two-pass planning grep catches enumeration-by-other-pattern.** First pass: literal pattern. Second pass: any test file touching the same DOM testids / column sets / route prefixes. Two near-miss occurrences in F2 (L5, L6) plus one F1 occurrence — methodology, not coincidence.
- **A short placeholder leg can decouple routing-bug detection from form-shape detection.** L5's 35-LoC placeholder editor cost ~50 LoC of throwaway in exchange for catching routing regressions one leg earlier. Worth lifting to a flight-planning pattern.
- **Untested edge cases inherited by Flight 10 (hardening):**
  - Rotation-while-`shutdown_drain` race (no test asserts safe interaction).
  - Concurrent `acquire` during `_evict_all_for_account` (likely correct, unasserted).
  - Doctor-probe under network partition (uncoverable with stub; tag on Flight 8 L-doctor).
  - Eviction-on-`idle_timeout_seconds`-change semantics (not implemented; bounded worst case; Flight 3 should decide explicitly for the chat-session lifecycle field).
- **Architect spec-time recon failed twice (doctor `message` field, stub test-seam policy).** Both are small, both are correct adjustments, but both could have been caught by reading the F1-frozen `DoctorReport` dataclass + thinking through "how do browser tests register the stub?" at spec time. Spec-time recon should include a "what does the test seam look like?" pass.

## Test Metrics Capture

**`make test`** (unit suite): **1805 passed, 4 skipped, 382 deselected, 2 warnings, 106.69s** wall-clock. Pass count delta from `main` baseline (1774): **+31** (L1: 0, L2: +11, L3: +12, L4: +8, L5: 0, L6: 0 — browser tests excluded from `make test` via pyproject `addopts`). Suite throughput ~16.9 tests/s, roughly flat against F1's 100.36s for 1774 tests (~17.7 tests/s) — the marginal slowdown tracks with the new tests' shape (eviction tests exercise real pool worker tasks), not infrastructure drag.

**`make test-browser`** (browser suite): **345 passed, 35 skipped, 12 deselected, 295.21s** wall-clock. Pass count delta from leg-5 baseline (323): **+22**. The 35 skips are the pre-existing M07 F8 deferrals; the 12 deselected are pixel-marker visual-snapshot tests (gitignored baselines per the user-global rule). One environmental note: `make rebuild` (required after JS edits to bake into the image) wipes `~/.cache/ms-playwright/`; `make _ensure-playwright` precondition restored it transparently on first `make test-browser` run.

**`make lint`** (ruff): clean across all six legs. No new findings.

**Carry-forward warnings**: 2 `AsyncMock-never-awaited` warnings on `tests/test_provider_api.py::TestModelDiscovery::test_ollama_models`. This is the third consecutive flight carrying these (M07 → F1 → F2). **Recommendation**: clear in the next maintenance flight rather than carry into Flight 3.

**Flakes**: none observed on single full runs of both suites. Recommend a 3x rerun in maintenance for nondeterminism check on the new `_pendingProbeReport` module-level hand-off pattern.

## Recommendations

1. **Maintenance fix: symmetric `model_copy(update=data)` → `model_validate(existing.model_dump() | data)` on MCP and provider PUT routes** (`api.py:2393`, `:2606`). ~10 LoC each, behavior-preserving for valid payloads, surfaces 422 for silent-bypass paths today.
2. **Codify the two-pass planning-grep convention** in `agents.md` "Project Conventions" or as a meta-bullet in the leg-planning workflow: (a) literal pattern match for the touched surface, (b) cross-reference any test file pinning the same DOM testids / column sets / route prefixes.
3. **Codify the schema-column-ALTER planning audit** in `agents.md` "Connector type extension checklist": every column ALTER must check the head-version assertion AND every column-set assertion site in `tests/test_db_migration.py`.
4. **Pin down the stub-visibility policy before Flight 8.** Either accept "stub is dev-mode opt-in via `THE_ONE_REGISTER_STUB_CONNECTOR=1`" and update the spec language + `connectors/README.md`, or add a runtime guard refusing stub registration when any non-stub connector is also present.
5. **Update `connectors/README.md` §3** with: (a) the API-edge `__MASKED__`-sentinel contract paragraph; (b) the skeleton plugin's `doctor()` returning a non-empty `message` field example.
6. **Clear the 2 carry-forward `AsyncMock-never-awaited` warnings on `test_provider_api.py`** in the next maintenance flight (third consecutive flight carrying these).
7. **Flight 3 must decide eviction semantics explicitly for the new chat-session lifecycle field.** Don't inherit the F2 "secrets-change-only" eviction shape silently; the operator's mental model on a session-lifecycle change ("takes effect next session") is different from a credentials change ("takes effect immediately").

## Action Items

- [ ] **(Maintenance, next maintenance flight)** Symmetric PUT validator-bypass fix on MCP + provider routes; clear AsyncMock warnings on `test_provider_api.py`.
- [ ] **(Methodology, mission-control)** Codify two-pass planning grep + schema-ALTER column-set audit as named conventions / leg-planning checklist items.
- [ ] **(Flight 3 planning input)** Decide eviction trigger for chat-session lifecycle field explicitly; revisit the `_pendingProbeReport` pattern if a second module-level handoff surfaces.
- [ ] **(Flight 8 planning input)** Pin down stub-visibility policy before adding `'discord'` to the registry; clarify whether stub coexists with real connectors in dev mode.
- [ ] **(Documentation)** `connectors/README.md` §3 paragraph on API-edge masked-sentinel contract + skeleton-plugin `message`-field example.
- [ ] **(Mission known issues — log under `mission.md`)** Document the rotation-inter-commit-and-`install_key` race and the shared-pool divergence cost; both are unchanged-but-clarified by F2.
- [ ] **(Design-language gate, this flight)** Human review of the screenshots filed under `tests/browser/__snapshots__/connector-account-editor/` before marking the mission criterion "M04/M06 design-language quality bar without alignment-flight rework" as satisfied.
