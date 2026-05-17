# Flight: Admin Surface for Connector Accounts

**Status**: completed
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

- [ ] *(advances toward COMPLETE)* "An operator can register, edit, and remove connector accounts (a Discord bot identity, a Slack workspace app identity) through an Admin surface that follows the existing design language and the existing LLM-providers / MCP-sources patterns, with all sensitive fields persisted under the same encryption pipeline that already protects LLM and MCP credentials" — this flight lands the REST surface, the Studio admin UI, and `__MASKED__`-sentinel handling at the API edge. **Caveat**: the criterion will only be fully satisfied once a real connector type is registered (Flight 8, Discord) — Flight 2 ships the operator-visible mechanics, but `/api/connector-accounts/types` returns the empty list in production until Flight 8 lands. The surface is fully exercised end-to-end against the Flight-1 stub in tests.
- [ ] *(advances)* "A doctor-style probe accessible from each connector account's Admin detail page verifies the connection lifecycle ... and runs without dispatching any messages to peers" — this flight wires the `POST /api/connector-accounts/{id}/test/connect` route that dispatches to `plugin.doctor(account, encryptor)` and renders `DoctorReport` as the operator-visible status surface. Same caveat: only the stub doctor probe runs in production until Flight 8.
- [ ] *(advances)* "Credentials never appear in plaintext outside the encryption boundary — not in API responses, not in logs, not in the doctor-probe output, not in connector connection-state inspection panes — and the existing edit-form `__MASKED__` sentinel pattern is preserved so an operator can re-save a connector account without retyping its secrets" — this flight implements the per-key `__MASKED__` resolution at the API edge (mirror of `api.py:901-942` for MCP), the masked-secrets response shape (mirror of `_mcp_source_response`), and the masked-edit round-trip in the editor JS (mirror of `studio/mcp-server-editor.js`).
- [ ] *(advances)* "Each connector-attached session has a defined lifecycle ... surfaces from the connector account's Admin detail page as a configurable parameter" — this flight surfaces the **pool idle-TTL** as a per-account configurable. The chat-session lifecycle (24h-default-hybrid per the mission Open Questions) is a Flight 3 concern (requires Flight 3's session-key schema migration to even have a place to store it); Flight 2 surfaces only the connector-pool idle-TTL that already exists in Flight 1's env-var form.
- [ ] *(advances)* "The Admin connector-account surface ... meets the M04/M06 design-language quality bar without alignment-flight rework" — this flight's frontend legs apply the M04/M06 tokens, layout primitives, and accessibility patterns directly so the surface lands at the bar in one pass.
- [ ] *(advances)* "Each layer of the integration has automated coverage proving its contract — the encrypted persistence layer for connector accounts, the connector-plugin contract on at least one stub implementation, ... the doctor probe's success and failure paths" — this flight adds the REST-surface coverage and the browser-flow coverage on top of Flight 1's pool-level regression baseline.

---

## Pre-Flight

### Objective

Ship the operator-visible surface — REST + Studio UI — for managing connector accounts as standalone entities, mirroring the MCP-server admin pattern that already lives under Studio. Flight 2 produces the CRUD endpoints, the doctor-probe endpoint, the masked-sentinel resolution at the API edge, the per-account idle-TTL configurable, and the vanilla-JS Studio surface (grid + editor + test/connect button) that meets the M04/M06 design-language bar. The Flight-1 stub plugin is the test fixture: every code path exercised end-to-end against the stub. **No real platform code lands here** — Flight 8 (Discord) is the first time `/api/connector-accounts/types` returns a non-empty list in production. Flight 2 also bundles five carry-forward items from the Flight 1 debrief that touch the surfaces this flight will edit (Fernet helper lift, `agents.md` convention, README skeleton, F1 leg-6 bullet patch, rotation pool-eviction wiring).

### Open Questions

- [x] **Studio vs. Admin placement** — resolved in Design Decisions (Studio — many bot identities, mirror MCP precedent at `static/js/areas/studio/mcp-servers-grid.js` + `mcp-server-editor.js`, not the single-LLM-provider shape at `admin/providers-grid.js`)
- [x] **Pre-leg maintenance bundling** — resolved (bundle five F1 debrief carry-forward items into the first leg; touches surfaces Flight 2 edits anyway)
- [x] **HAT / alignment leg** — resolved in Design Decisions (skip — Flight 2 is well-bounded admin work; mission-level vibing belongs at the end of the mission after the second connector lands)
- [x] **Idle-TTL scope** — resolved in Design Decisions (Flight 2 owns both persistence AND threading through `_pool._resolve_ttl_seconds()` so the field isn't vestigial; mission criterion explicitly says the parameter is configurable from the Admin detail page, which means it has to flow into pool behavior)
- [x] **"Session-lifecycle parameter (idle-timeout)" mission-text disambiguation** — resolved in Design Decisions (this is the **connector-pool idle-TTL**, 30 min default per F1; the **chat-session lifecycle** 24h-hybrid is Flight 3 — it requires the Flight 3 schema migration to even have a column)
- [x] **Doctor-probe response shape** — resolved in Design Decisions (return `DoctorReport` rendered as `{status, details}` JSON; UI banner mirrors the MCP `mcp-tools-status` shape but renders the `details` dict as a labeled key/value block since connectors don't have a tools list)
- [x] **Schema-version sequencing for the new `idle_timeout_seconds` column** — resolved in Design Decisions (Flight 2 lands v15; Flight 8's CHECK migration renumbers from v15 to v16 — mirror of the Flight 1 leg-2 v14 renumber precedent)
- [x] **Stub visibility in production** — resolved in Design Decisions (NOT exposed via `/api/connector-accounts/types`; mirror of Flight 1's "stub is test-only, never registered via `register_builtin_connectors`" stance — different from the LLM `mock` provider which IS dev-mode-visible)
- [x] **`idle_timeout_seconds` validation bounds** — resolved post-architect-review: nullable `INTEGER` with Pydantic validator `1 <= value <= 604800` (7 days). The upper bound exists to catch the milliseconds-instead-of-seconds typo (`idle_timeout_seconds: 31_536_000_000` is suspiciously high); 7 days is comfortably more than any plausible "keep the connection warm" semantic.
- [x] **Exact route prefix for the doctor probe** — resolved: `POST /api/connector-accounts/{account_id}/test/connect` (exact mirror of MCP's `/api/mcp-sources/{source_id}/test/connect`). Alternative `…/probe` was considered but `test/connect` is the established muscle memory for operators.
- [ ] **Connector-account `config` shape validation gating** — finalized at leg planning for `rest-crud-and-masked-sentinel`; tentative: Flight 2 does NO per-type config validation (the stub plugin accepts any config), and per-type validation is deferred to whichever flight ships the first real connector (Flight 8 — Discord). This mirrors `_validate_mcp_source_config` which is type-aware. The leg-2 acceptance criteria document the deferral.

### Design Decisions

**Studio placement, not Admin**

- **Choice**: All Flight 2 frontend lands under `the_one/interfaces/web/static/js/areas/studio/` (new files `connector-accounts-grid.js`, `connector-account-editor.js`, plus integration into `studio.js`). The Studio area gains a new section alongside `mcp-sources`. Admin retains LLM providers + built-in tools; Studio holds connector accounts + MCP sources + agent editor.
- **Rationale**: Connector accounts are many-to-many identities (the operator may have 3 Discord bots, 2 Slack workspace apps, etc.) — the structural shape matches MCP sources, not the single-source-of-truth LLM provider list. The mission criterion text says "Admin surface" but in this repo "admin" is the LLM-providers + built-ins area while many-bot identity registration lives in Studio post-F2-retrofit (see comment at `static/js/areas/studio.js:2-3`). Placing connectors in Studio mirrors the MCP precedent operators already use.
- **Trade-off**: The mission text reads "Admin surface" verbatim; this flight's spec uses "Studio admin surface" to bridge. The mission criterion is about operator-visible mechanics (register/edit/remove/probe), not the URL prefix; the criterion is satisfied either way.

**Bundle the Flight 1 carry-forward maintenance into leg 0**

- **Choice**: Leg 0 of Flight 2 lands five items from the F1 debrief that touch surfaces this flight will edit anyway:
  1. Lift `_secrets_to_ciphertext` / `_ciphertext_to_secrets` to a shared helper pair in `db/repositories.py` (was duplicated between `MCPSourceRepository:301-326` and `ConnectorAccountRepository:456-479`)
  2. Patch the F1 flight.md leg-6 bullet to reflect that lifespan wiring shipped in F1 (was originally "deferred to Flight 2")
  3. Add the `function-local-import-to-break-load-cycle` convention to `agents.md` Project Conventions (3rd occurrence; pattern is stable)
  4. Add a "Skeleton for a real plugin" code block to `connectors/README.md` §3
  5. (Defer to leg 3) wire `_evict_all_for_account` into the rotation transaction — this touches `interfaces/web/api.py:rotate_encryption_key` and is the natural home for the rotation-while-pool-warm test; the eviction also wires into per-account PUT in leg 2
- **Rationale**: Per the `/flight` skill's shared-surface bundling guidance, small carry-forward debt that touches the same files as the new work should bundle into the new flight rather than scheduling a separate maintenance flight. Items 1 + 2 + 3 + 4 are small, behavior-preserving, and a maintenance-only leg keeps them auditable as a unit. Item 5 lives in leg 3 because the rotation eviction logically belongs with the rotation test.
- **Trade-off**: Leg 0 is a "bundle of unrelated documentation + one repository refactor" leg — slightly fuzzy in its acceptance criteria. Acceptable: each item has a clear test or grep-able outcome.

**HAT / alignment leg skipped**

- **Choice**: No optional `uat-and-alignment` leg in this flight.
- **Rationale**: Flight 2 is well-bounded REST + UI work with a clear automated test net (REST + browser flow). The mission-level vibe / alignment session belongs after the second real connector lands (Flight 9) so the operator can drive both connectors end-to-end and surface anything missing. Adding HAT here would be premature — the surface has no real platform to talk to until Flight 8.
- **Trade-off**: If the M04/M06 design-language bar isn't hit in one pass, an alignment cycle may surface in the flight debrief. Mitigation: design-language verification is a first-class leg acceptance criterion (leg 5), not a deferred concern.

**Idle-TTL: persist + wire through the pool, not persist-only; pool resolver takes an `int | None` override, NOT the whole account**

- **Choice**: Flight 2 (a) adds `idle_timeout_seconds: int | None` to `ConnectorAccount` (v15 migration + Pydantic field + repository round-trip + admin form), AND (b) threads the per-account value through `connectors/_pool.acquire()` so the warm entry's `ttl_seconds` reflects the account's configured value. The resolver signature becomes `_resolve_ttl_seconds(override: int | None = None) -> int`; resolution order is **explicit override → env var override → 1800 default**. The caller in `acquire()` does `_resolve_ttl_seconds(override=account.idle_timeout_seconds)`.
- **Rationale**: The mission criterion says the parameter is "configurable per-account from the Admin detail page" — operator-visible without behavior-changing means a vestigial field. The wiring through the pool is small (~10 LoC + 3 tests) and keeps the field semantically meaningful. The env var `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` becomes the fallback for accounts that don't set the field. **Architect challenge accepted**: an earlier version of this decision threaded the whole `ConnectorAccount` object into `_resolve_ttl_seconds(account=...)`. The cleaner shape is the bare `int | None` override — the pool stays ignorant of which model field drives the override; the model owns the field name; the resolver owns the precedence. The env-var-read-at-call-time live-read invariant (`agents.md` `live-read-across-lazy-resolver-boundary`) is preserved.
- **Trade-off**: `acquire` reads `account.idle_timeout_seconds` directly and passes the value through. `_load_account` already loads the full account via function-local import per the load-cycle convention; no new layering.

**"Session-lifecycle parameter (idle-timeout)" in the mission text means the connector-pool idle-TTL, not the chat-session lifecycle**

- **Choice**: The Flight 2 mission entry's "Session-lifecycle parameter (idle-timeout default, configurable per account)" is read as **the connector-pool idle-TTL** (the 30-min default from Flight 1). The chat-session lifecycle (when an inbound message starts a fresh `chat_sessions` row vs. continues an existing one — the 24h hybrid default from the mission Open Questions) is Flight 3 territory: it requires Flight 3's session-key schema migration to have a column to store it.
- **Rationale**: Flight 1 ships the only timeout that currently exists (`THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS`, env-var only); making it per-account is the natural Flight 2 progression. The chat-session lifecycle has no column to land into until Flight 3 runs its migration. Trying to surface both in Flight 2 would force pre-committing Flight 3's schema decisions. The wording in the mission is ambiguous; this disambiguation is recorded so Flight 3 can pick up the chat-session lifecycle without confusion.
- **Trade-off**: The admin form ships with one timeout field this flight; a second (chat-session lifecycle) lands in Flight 3 right next to it. Operators see two fields with related names — that's a Flight 3 design problem (e.g. distinct labels: "Pool idle timeout" vs. "Session continuation window"), not a Flight 2 blocker.

**Doctor-probe response shape: render `DoctorReport` as `{status, details}` JSON; UI banner mirrors MCP `mcp-tools-status`**

- **Choice**: `POST /api/connector-accounts/{account_id}/test/connect` calls `plugin.doctor(account, encryptor)` and returns `{status: <DoctorReport.status>, details: <DoctorReport.details>}` directly. The frontend renders a status banner with the same `data-testid="connector-test-status"` shape MCP uses (`mcp-test-status`), but the body of the banner renders `details` as a labeled k/v block (connectors don't have a tools list to render).
- **Rationale**: `DoctorReport` is already the Flight-1 contract (`connectors/base.py`, frozen-slotted dataclass with `status: str` + `details: dict[str, Any]`). The MCP `/test/connect` route returns ad-hoc `{status, tools, capabilities, ...}`; the connector route returns the canonical Flight 1 shape. The UI banner is structurally identical to MCP — same `entity-tile` adjacent layout, same status LED, same banner element — only the body content differs.
- **Trade-off**: Connectors and MCP have slightly different test-result shapes — a future "unified inspector" abstraction may want to unify them. Out of scope; Flight 10 (hardening) is the place to revisit if useful.

**Schema version v15 for `idle_timeout_seconds`; Flight 8's CHECK migration renumbers from v15 to v16**

- **Choice**: Leg 1 of Flight 2 introduces a v15 migration: `ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL`. Flight 8 (Discord), which was originally scheduled to land v15 (table-rename + CHECK constraint on `type`), renumbers to v16.
- **Rationale**: Mirrors the precedent set by Flight 1 leg 2 (which took v14 for the `name` column and renumbered Flight 8's CHECK to v15). The renumbering is mechanical; the Flight 1 leg-2 design-adjustment entry in the F1 flight log is the template for documenting it here.
- **Trade-off**: One more migration to test against; brittle tests in `tests/test_db_migration.py::TestSchemaV8` etc. that hardcode the head version need bumping (the existing test docstring already calls out that the assertion is intentionally regression-loud-fail on every schema bump). All of this is already-paved territory from F1 leg 2.

**Stub plugin is NOT exposed via `/api/connector-accounts/types` in production**

- **Choice**: The types route returns `[{value, label}]` derived from `the_one.connectors.registry.types()` — which is empty in production (Flight 1 ships `register_builtin_connectors()` with an empty body; Flight 8 adds 'discord'). The stub is registered ONLY via `register_for_test` from test fixtures. No `dev_mode` carve-out.
- **Rationale**: Mirror of Flight 1's stance ("stub is test-only, never registered via `register_builtin_connectors`"). The LLM `mock` provider IS dev-mode-visible because operators write tests against it interactively; the connector stub is purely a Flight-test fixture that has no operator value.
- **Trade-off**: The admin grid renders the empty-state CTA in production until Flight 8 lands. Acceptable — the surface is documented as "ready for the first real connector" in the leg artifacts, and the empty-state copy can mention "no connector types registered yet."

**Pool eviction wired into BOTH rotation AND per-account PUT (secrets change); rotation eviction lives OUTSIDE the commit try/except**

- **Choice**: Leg 2 (REST PUT) calls `await _evict_all_for_account(account_id)` after a successful `repo.update(...)` IF the post-`__MASKED__`-resolved secrets dict differs from the existing one. Leg 3 (rotation) appends a `for aid, _ in decrypted_connectors: await _evict_all_for_account(aid)` loop AFTER `await conn.commit()` and BEFORE the on-disk key replace in `rotate_encryption_key` — **outside** the `try/except` that wraps the commit. Both call sites are the F1 debrief's action item #2.
- **Rationale**: Warm pool entries cache plaintext credentials inside their `ConnectorClient`. After a credential change (rotation OR per-account update), the warm entry would keep serving the stale credentials until idle-TTL eviction (30 min default). The eviction call is idempotent and cheap; calling it on every secrets-change is safer than trying to detect "did this update change secrets?" **Failure mode (architect Q)**: if `_evict_all_for_account` raises after a successful commit, the on-disk key replace proceeds anyway — eviction failure is logged but does not abort rotation. The alternative (abort the on-disk key replace) is structurally worse: the DB is already committed in the new-key state; refusing to replace the on-disk file would leave the DB unreadable on next process restart. Worst case of "eviction failed, key file replaced" is that warm entries serve stale credentials until their idle TTL elapses — exactly the pre-F1-debrief baseline. Worst case is bounded.
- **Trade-off**: PUT diff check has two false-positive cases to test for explicitly: (a) a no-op PUT (operator opens the form and saves without changing anything, all secrets round-trip as `__MASKED__`) MUST NOT evict; (b) operator drops a key by omitting it from the incoming dict (REST PUT replace semantic per the MCP block at `api.py:903-905`) MUST evict, even though the resolved dict is *shorter* not *different in values*. The leg-2 acceptance criteria call out both shapes: `no_op_all_masked_does_not_evict` AND `dropping_a_key_evicts`. Python `dict == dict` is order-independent, so dict-ordering is not a false-positive concern.

**Create form's primary action is "Create & Test" — save and probe in one click; departs from MCP precedent**

- **Choice**: The create form's primary button does a two-step sequential action: `POST /api/connector-accounts` (save) → on success, immediately `POST /api/connector-accounts/{new_id}/test/connect` (probe) → render the `{status, details}` result inline as the UI transitions from create-mode to edit-mode for the freshly-created account. The button label is "Create & Test" (final wording subject to leg-5 UX judgment). The edit form's Save button and Test Connection button stay separate (matches MCP precedent in edit-mode); only the create flow gets the combined action.
- **Rationale**: Connector account credentials (bot tokens, app secrets) have a single failure mode that's invisible until the bot actually tries to talk to the platform — "I pasted the token but did I get it right?" is the operator's primary uncertainty at create time. Forcing a separate Test click after navigating into edit mode adds friction without operator value. The combined action makes the create flow self-validating: if the probe fails immediately, the operator knows to fix the token before walking away thinking they're done. This deliberately differs from MCP's create flow (which has no Test button on the create form per `studio/mcp-server-editor.js:472`); the difference is justified by the connector context (single bot identity per account, no OAuth dance, no streamable-http vs stdio split — the credentials are simpler and the probe is fast).
- **Trade-off**: If the probe takes a while (real connectors with network round-trips), the operator waits longer at create time. Mitigation: the Create button shows a loading state during both the save and the probe (loading copy: "Creating…" then "Testing…" — leg-5 detail). If the operator wants to skip the probe (e.g. seeding accounts for offline testing), they can: account is persisted before the probe runs, so canceling/closing mid-probe still leaves the account on disk; the probe is best-effort. The two-call sequence is NOT atomic on the backend — a server-side combined endpoint was considered and rejected: keeping create and probe as separate endpoints preserves clean failure semantics (operator knows which step failed) and avoids inventing a one-off combined route.

**Browser tests use Playwright snapshots, kept locally (gitignored)**

- **Choice**: New browser-flow tests in `tests/browser/test_flow_studio_connector_account_*.py` mirror the existing MCP browser-flow pattern. Visual snapshot baselines (`tests/browser/__snapshots__/`) are already gitignored per the user-global instruction; new snapshots are local artifacts only.
- **Rationale**: Existing browser tests (`test_flow_studio_mcp_editor.py`, `test_flow_studio_mcp_navigation.py`, `test_mcp_test_connection_button.py`) are the precedent and use this exact pattern. The gitignore at `tests/browser/__snapshots__/` is already in place.
- **Trade-off**: Each developer regenerates baselines locally with `pytest --snapshot-update`. CI does not compare against committed baselines (none exist).

### Prerequisites

- [ ] Flight 1 status is `completed` (confirmed: F1 debrief shows `landed → completed`, mission flights list shows `[x] Flight 1`)
- [ ] Schema version on `main` is 14 (confirmed: F1 leg-2 landed v14 with the `name` column ALTER)
- [ ] `connector_accounts` table exists with `(id, type, config, secrets, created_at, updated_at, name)` columns and NO CHECK constraint on `type` (confirmed in F1 leg-2 and leg-1 flight log)
- [ ] `the_one/connectors/` package is on `main` with: `base.py` (4-method `ConnectorPlugin` Protocol + `ConnectorClient` Protocol + `InboundEnvelope` + `OutboundTarget` + `SessionKey` + `DoctorReport`), `errors.py` (6 typed exceptions), `_pool.py` (lifecycle pool with idle-TTL reaper + `_evict_all_for_account` + `shutdown_drain` wired into FastAPI lifespan), `registry.py` (singleton with empty production baseline), `_stub.py` (StubPlugin + StubClient with configurable doctor response + recording buffers), `README.md`, `__init__.py` (12 exports)
- [ ] `ConnectorAccountRepository` round-trips encrypted accounts with `__MASKED__`-sentinel comment at `db/repositories.py:446` (verified by recon)
- [ ] Encryption rotation transaction at `interfaces/web/api.py:rotate_encryption_key` (~L2745) re-encrypts three corpora atomically (LLM + MCP + connector secrets) — verified by recon; this flight ADDS the eviction-after-commit loop, does NOT change the atomic-commit structure
- [ ] Studio area scaffolding at `static/js/areas/studio.js` + `static/js/areas/studio/` exists with the MCP sub-section, the editor pattern, and the test/connect button pattern as the precedent (verified by recon)
- [ ] LLM providers admin pattern at `static/js/areas/admin/providers-grid.js` + `provider-editor.js` exists as the design-language reference (verified by recon)
- [ ] Browser-test framework set up at `tests/browser/` with `seeders.py` + `design_tokens.py` + existing MCP-flow test files as the precedent (verified by recon); snapshot directory is gitignored
- [ ] `agents.md` has the "Project Conventions" section (around L24-85 per recon) — Leg 0 appends the function-local-import convention there
- [ ] No conflicting in-flight work on `interfaces/web/api.py` (rotation transaction or MCP routes), `db/repositories.py`, `db/schema.py`, `connectors/_pool.py`, or any file under `static/js/areas/studio/` on `main`
- [ ] Container test entry points (`make test`, `make lint`, browser tests via `make` recipe per the F1 leg pattern) operating cleanly on `main`

### Pre-Flight Checklist

- [ ] All open questions resolved (eight closed in Design Decisions; two intentionally deferred to leg planning)
- [ ] Design decisions documented above with rationale and trade-offs
- [ ] Prerequisites verified
- [ ] Validation approach defined (see In-Flight § Verification below)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

**Bottom-up**: the small carry-forward maintenance and the persistence-layer field land first, then the REST surface, then the doctor probe and rotation-eviction wiring, then the frontend grid + editor + browser tests on top.

- **Leg 0 — maintenance bundle (carry-forward from Flight 1 debrief)**:
  - `db/repositories.py`: lift `_secrets_to_ciphertext` and `_ciphertext_to_secrets` to a shared `_encrypt_secrets_blob(encryptor, secrets) -> str` / `_decrypt_secrets_blob(encryptor, ciphertext) -> dict[str, Any]` pair (module-level free functions, NOT methods of either repository). Update `MCPSourceRepository` and `ConnectorAccountRepository` to call the shared helpers. The `__MASKED__` sentinel API-edge comment at `db/repositories.py:446` stays as-is (it documents the boundary, not the envelope).
  - `the_one/agents.md`: under "Project Conventions" (existing list around L24-L85), append a new entry: `function-local-import-to-break-load-cycle` with a brief explanation and the three citation points (`mcp/_pool.py:196`, `db/repositories.py:398`, `connectors/_pool.py:158-167`).
  - `the_one/agents.md` "Connector type extension checklist" (~L277-283) updates:
    - **Item 4** (SQLite CHECK constraint): the parenthetical "v14 is already claimed by leg 02's `name` column" becomes "v14 → `name` (F1 L2); v15 → `idle_timeout_seconds` (F2 L1); Flight 8's CHECK migration is **v16**, not v15."
    - **Item 6** (Frontend): the literal reference to `interfaces/web/static/js/areas/admin.js` is rewritten to reflect Flight 2's Studio-placement decision: "Connector accounts grid + editor land under `static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + integration in `static/js/areas/studio.js`; Flight 8 supplies the Discord-specific badge styles and any per-type form fields. Admin only if a future surface needs it."
  - `the_one/connectors/README.md`: under §3 (Protocol decomposition), insert a "Skeleton for a real plugin" fenced code block — a ~30-line example showing how Flight 8 / Flight 9 will satisfy the 4-method `ConnectorPlugin` Protocol against a hypothetical platform SDK, including the `DoctorReport` return shape.
  - `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md`: patch the leg-6 bullet (around L175) to reflect that lifespan wiring shipped in Flight 1, not Flight 2.

- **Leg 1 — `idle_timeout_seconds` field + pool wiring**:
  - `the_one/db/schema.py`: bump `CURRENT_VERSION` from 14 to 15. Add a v15 migration block: `ALTER TABLE connector_accounts ADD COLUMN idle_timeout_seconds INTEGER NULL`. Mirror the v11 / v14 ALTER pattern. `INSERT OR IGNORE INTO schema_version (version) VALUES (15)` LAST before commit.
  - `the_one/db/models.py`: add `idle_timeout_seconds: int | None = None` to the `ConnectorAccount` Pydantic model. Pydantic field validator: must satisfy `1 <= value <= 604800` if not None (operators wanting "use default" leave it null; the upper bound catches milliseconds-vs-seconds typos).
  - `the_one/db/repositories.py`: extend `ConnectorAccountRepository._row_to_model`, `create`, and `update` to round-trip the new column.
  - `the_one/connectors/_pool.py`: change `_resolve_ttl_seconds()` signature from `() -> int` to `(override: int | None = None) -> int`. Resolution order: `override` (if not None) → `THE_ONE_CONNECTOR_POOL_IDLE_TTL_SECONDS` env var (read at call time, if set + parseable) → `_DEFAULT_TTL_SECONDS` (1800). Update `acquire()` to call `_resolve_ttl_seconds(override=account.idle_timeout_seconds)`. The pool stays ignorant of which model field drives the override (architect-flagged shape refinement).
  - **Schema-version renumber site enumeration** — every location that references the v14/v15 schema head version is updated coherently this leg:
    - `the_one/db/_connector_types.py:11-13` docstring: the "v14 is claimed by leg 02's `name` column" wording becomes "v14 → `name` (F1 L2); v15 → `idle_timeout_seconds` (F2 L1); Flight 8's CHECK migration is v16."
    - `tests/test_db_migration.py:226-231` (`TestSchemaV8.test_v8_fresh_db_includes_tool_configs_and_tool_overrides`): bump `assert CURRENT_VERSION == 14` to `== 15`, AND update the error-message string ("must be 14 after the connector_accounts.name v14 migration") to reference v15 + the F2-L1 migration so the assertion message doesn't lie.
    - `tests/test_db_migration.py:1230-1243` (`TestSchemaV14` docstring): the "Flight 08 ... that renumbers to v15" wording becomes "renumbers to v16."
    - `the_one/agents.md` connector-type checklist item 4 (already enumerated under Leg 0; cross-referenced here).
  - This is the canonical place for the renumber bookkeeping; future flights that move the schema head reuse this enumeration pattern.

- **Leg 2 — REST CRUD + masked-sentinel resolution + per-account PUT eviction**:
  - `the_one/interfaces/web/api.py`: add the connector-account routes section parallel to the MCP-source routes section. Routes (registered in this order so `/types` is matched before `/{account_id}`):
    - `GET /api/connector-accounts` → list (masked secrets in response via `_connector_account_response`)
    - `GET /api/connector-accounts/types` → returns `[{value, label}]` from `the_one.connectors.registry.types()` (empty in production; `'stub'` only when test-side-registered)
    - `GET /api/connector-accounts/{account_id}` → get-by-id (masked response)
    - `POST /api/connector-accounts` → create (Pydantic `ConnectorAccount.model_validate` for shape; 422 on unknown type ONLY when the registry would later reject — defer registry resolution to `POST /test/connect` and `PUT` semantics-validation; create does not need plugin presence)
    - `PUT /api/connector-accounts/{account_id}` → update with per-key `__MASKED__` resolution in `secrets`. The resolution logic is the **exact mirror** of `api.py:901-942` for MCP — the same per-key loop, the same non-dict guard. Connectors do NOT have an OAuth-managed-keys preservation step (the M07 `_OAUTH_MANAGED_SECRET_KEYS` block is MCP-specific). After successful `repo.update(...)`, IF the post-`__MASKED__`-resolved secrets dict differs from the pre-existing one (`existing.secrets != resolved_secrets`), call `await _evict_all_for_account(account_id)` so warm pool entries don't keep using stale credentials. Edge cases: no-op PUT (all secrets round-trip as `__MASKED__`) MUST NOT evict; **dropping a key by omission** (operator removes a secret entirely; resolved dict is shorter) MUST evict — both tested explicitly.
    - `DELETE /api/connector-accounts/{account_id}` → delete. Calls `await _evict_all_for_account(account_id)` BEFORE the row delete (mirror of MCP's `delete_mcp_source` which evicts before delete at `api.py:1016`). No "agents reference this account" guard yet — Flight 4 adds `connector_account_ids` to `AgentConfig`, so the reference-check belongs at that point. Add a leg-test comment noting the future check.
  - Helpers: `_connector_account_response(account: ConnectorAccount) -> dict[str, Any]` parallel to `_mcp_source_response` — calls `_mask_secrets(account.secrets)` (the existing generic helper at `api.py:665`, NOT MCP-specific — `_mask_secrets` is a pure per-key masker; the OAuth-managed-keys stripping in `_mcp_source_response` happens BEFORE `_mask_secrets` is called and is therefore not inherited). Returns the dict. `_connector_repo() -> ConnectorAccountRepository` parallel to `_mcp_repo` / `_provider_repo`.
  - No special validation for `config` shape in this leg — the Flight 1 stub accepts arbitrary config, and per-type config validation lands per-connector in Flights 8 / 9 (mirror of `_validate_mcp_source_config` which is type-aware). Leg-2 acceptance criteria explicitly document the deferral.
  - **Acceptance-criteria tests (mandatory)**: `test_crud_round_trip` (POST → GET → PUT → DELETE) + `test_list_returns_masked_secrets` (regression net: raw secret value never appears anywhere in response payload) + `test_put_masked_sentinel_preserves_secret` + `test_no_op_put_does_not_evict` + `test_dropping_a_key_evicts` + `test_secrets_change_evicts` + `test_delete_evicts_then_deletes` + `test_unknown_account_returns_404`.

- **Leg 3 — REST doctor probe + rotation eviction wiring**:
  - `POST /api/connector-accounts/{account_id}/test/connect`:
    - Load the account via `_connector_repo().get(account_id)` → 404 if missing
    - Resolve the plugin via `the_one.connectors.registry.resolve(account.type)` → on `ConnectorRegistrationError`, return `{status: "error", details: {"error": "Unknown connector type: <type>"}}` (mirror of the MCP "unknown transport" error shape — keep 200-with-status-error, not 4xx, so the UI banner renders the error inline)
    - Call `report = await plugin.doctor(account, get_encryptor(settings.data_dir))` inside `try/except ConnectorClientError as e:` → wrap as `{status: "error", details: {"error": str(e), "exception_type": type(e).__name__}}`
    - Return `{status: report.status, details: report.details}` on success
    - **No in-flight override body in Flight 2** — mirror MCP's launch shape (create-before-test workflow). MCP's F8 L4 override body was a retrofit driven by specific operator demand on a mature surface; the create-before-test flow is the established muscle-memory pattern for operators on this codebase. If a future operator-experience flight wants to add the override body for both MCP and connectors symmetrically, the surface is still cheap to add later (~40 LoC + tests). Leg 3 explicitly does NOT accept an optional JSON body; the route signature is `(account_id: str)` only.
  - **Rotation eviction wiring** in `interfaces/web/api.py:rotate_encryption_key`: AFTER `await conn.commit()` (~L2862) succeeds and BEFORE the on-disk key replace, add a `for aid, _ in decrypted_connectors: await _evict_all_for_account(aid)` loop. The loop lives **outside** the existing `try/except` that wraps the commit — if eviction raises after a successful commit, log and continue (do not abort the on-disk key replace). The Design Decisions section ("Pool eviction wired into BOTH rotation AND per-account PUT") documents the failure-mode rationale.
  - Order matters: commit succeeds first (database is in the new-key state), THEN warm pool entries are evicted (so the next `acquire` reloads the account row + decrypts with the soon-to-be-canonical new key). The on-disk key replace runs AFTER eviction; if `install_key` (the in-memory encryptor cutover) happens AFTER the on-disk replace as today, an `acquire` between eviction and `install_key` could load the row, decrypt with the still-installed OLD encryptor, succeed, and cache plaintext — that's correct (the plaintext is what was there before; nothing changed). After `install_key`, subsequent decrypts use the new key; before it, the in-memory encryptor still has the OLD key but the on-disk file has the NEW key — that's the **existing** rotation invariant Flight 1 inherited, not something Flight 2 changes.
  - Add the `rotation-while-pool-warm` test (F1 debrief carry-forward action item): seed an account, acquire a pool entry, run rotation, assert that a subsequent `acquire` (after the in-memory `install_key`) hands back a fresh entry that decrypts under the new key. The test naturally pairs with the eviction wiring in this leg.

- **Leg 4 — Frontend: grid view + types route consumer + studio integration**:
  - `the_one/interfaces/web/static/js/areas/studio/connector-accounts-grid.js`: new file structurally analogous to `admin/providers-grid.js`. Renders the `entity-tile-grid` of connector accounts with `entity-tile-badge` showing the type. Empty-canvas state when there are no accounts. New-entity button.
  - `the_one/interfaces/web/static/js/areas/studio.js`: integrate a new `connector-accounts` section parallel to `mcp-sources`. Routing: `studio/connector-accounts`, `studio/connector-accounts/new`, `studio/connector-accounts/{id}`. Selection state. Form-mode state. Mirror the existing `_activeSection === 'mcp-sources'` block.
  - Empty-canvas state copy explicitly mentions "no connector types registered yet — Flight 8 will add Discord" so operators understand WHY the grid is empty in production.

- **Leg 5 — Frontend: editor (form + masked round-trip + doctor-probe button + design-language pass)**:
  - `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js`: new file structurally analogous to `studio/mcp-server-editor.js`. Sections: editor-header, Connection (name + type + config kv editor), Credentials (secrets kv editor with per-key `__MASKED__` round-trip — `data-original-masked` attribute mirror), Lifecycle (nullable `idle_timeout_seconds` input with placeholder "Use default (30 min)" plus a brief design comment noting "Flight 3 will add the chat-session-lifecycle field next to this one"), Test Connection (button + `connector-test-status` banner), Danger Zone (delete on edit mode only).
  - The Test Connection button POSTs to `/api/connector-accounts/{id}/test/connect` with **no body** (create-before-test workflow per Design Decisions); renders the `{status, details}` response into the banner. The **edit form's** Test button only renders in edit-mode (`!isCreate`) — mirroring `studio/mcp-server-editor.js:472`. The **create form's primary action button** is "Create & Test" per the dedicated Design Decision: on click, fires `POST /api/connector-accounts` → on success, immediately fires `POST /api/connector-accounts/{new_id}/test/connect` → renders the probe result inline as the UI transitions to edit-mode for the freshly-created account. Loading copy on the button: "Creating…" during the first call, "Testing…" during the second. If the create call fails (422 / 500), the probe is skipped and the operator stays on the create form with the error surfaced. If the create succeeds but the probe fails, the account is persisted and the operator lands in edit mode with the failed `{status: "error"}` banner — they can fix the credentials, save, and re-test from edit mode. Status LED color matches MCP precedent (green ok, amber warning, red error). The **`details`-block rendering shape** is a sub-deliverable of this leg with its own design-token treatment:
    - The `details` dict is rendered as a labeled k/v block under the LED — left column shows the key as a `field-label`-style token; right column shows the value
    - Long string values wrap on token boundaries; truncated values use the M04/M06 `text-muted` overflow ellipsis
    - **Secret-shaped values** in `details` (any value matching the `_mask_secret_value` shape — strings starting with `***...` or wholesale `***`) are passed through as-is; no double-masking; no plaintext leakage path
    - Non-string values (numbers, booleans, nested dicts) are rendered as JSON-stringified text with monospace styling, preserving the M04/M06 `font-mono` token
    - The block has its own data-testid `connector-test-details` so browser tests can pin the rendering shape
  - Design-language pass: every element uses the M04/M06 tokens (background, surface, border, text-primary, accent, etc.). Layout primitives (`page-header`, `entity-tile-grid`, `editor-section`, `field-input`, `kv-value-input`, etc.) are reused — no new CSS classes invented unless a connector-specific need surfaces (and then it's namespaced `connector-account-*` to keep grep-able).
  - The editor's "kv editor for secrets" uses the same `data-original-masked` shape MCP uses (`studio/mcp-server-editor.js:17-20`); the masked-sentinel round-trip is byte-identical to MCP's behavior.

- **Leg 6 — Browser tests + design-language sanity**:
  - `tests/browser/test_flow_studio_connector_account_navigation.py` — parallel to `test_flow_studio_mcp_navigation.py`. Covers: open Studio → click Connector Accounts → empty canvas renders → click New → form opens → cancel returns to empty canvas → back to Studio.
  - `tests/browser/test_flow_studio_connector_account_editor.py` — parallel to `test_flow_studio_mcp_editor.py`. Covers: create → "Create & Test" button → both calls fire sequentially → UI lands in edit-mode with probe banner rendered → list shows new tile → edit → masked-secret round-trip → save → no actual secret change preserves stored value → delete → tile gone.
  - `tests/browser/test_connector_test_connection_button.py` — parallel to `test_mcp_test_connection_button.py`. Covers: stub plugin registered for the test, configurable doctor response → button click → status banner renders ok / error.
  - `tests/browser/test_flow_studio_connector_account_create_and_test.py` — covers the combined create+test action with three permutations: (a) create succeeds + probe succeeds → operator lands in edit mode with green banner; (b) create succeeds + probe fails → operator lands in edit mode with red banner showing the configured stub failure response (account is persisted, fixable from edit mode); (c) create fails with 422 → operator stays on the create form with the error surfaced, probe never fires (assert via network log that the test/connect call did NOT happen).
  - Browser-test seeders: extend `tests/browser/seeders.py` with a `seed_connector_account(account_id, type='stub', secrets={...})` helper that wraps the POST to `/api/connector-accounts` from the test's HTTP client (no need to fixture-inject the stub plugin registration — that's a separate concern handled in conftest if needed).
  - Design-token sanity: a small unit test in `tests/browser/test_visual_snapshots.py`-style asserts that the rendered DOM uses the canonical M04/M06 class names; visual snapshot baselines are local (gitignored) per the user-global rule.

### Checkpoints

- [ ] **Checkpoint A** (after leg 0): Fernet helper lifted; both repositories pass their existing test suites unchanged; `agents.md` has the new convention; `connectors/README.md` §3 has a skeleton block; F1 flight.md leg-6 bullet patched.
- [ ] **Checkpoint B** (after leg 1): v15 migration applies cleanly to v14; `ConnectorAccount.idle_timeout_seconds` round-trips through the repository; `_pool._resolve_ttl_seconds(account)` returns the per-account value, then env var, then default; `acquire` threads the account through.
- [ ] **Checkpoint C** (after leg 2): REST CRUD round-trips through TestClient with masked secrets in responses; per-key `__MASKED__` PUT preserves; per-account PUT (with actual change) evicts the warm pool entry; per-account PUT (no-op) does NOT evict; DELETE evicts then deletes.
- [ ] **Checkpoint D** (after leg 3): Doctor probe dispatches to `plugin.doctor` and renders `DoctorReport` as JSON; unknown-type returns `{status: "error"}` with 200; rotation transaction calls `_evict_all_for_account` post-commit; rotation-while-pool-warm test asserts fresh entry under new key.
- [ ] **Checkpoint E** (after leg 4): Studio admin grid renders empty-state and populated-state correctly; types route returns `[]` in production and `[{value: 'stub', ...}]` when test-side-registered; navigation between Studio sections preserves dirty-form gates (existing pattern).
- [ ] **Checkpoint F** (after leg 5): Editor form renders all sections; masked-secret round-trip works in browser; idle-timeout field validates; doctor-probe button renders status banner; M04/M06 design tokens applied without alignment-flight rework needed.
- [ ] **Checkpoint G** (post-flight, verified per-leg and at flight end): `make test`, `make lint`, browser tests all clean; no regression in MCP, LLM provider, agent factory, encryption-rotation surfaces.

### Adaptation Criteria

**Divert if**:
- The pre-leg maintenance bundle uncovers an unexpectedly large refactor surface (e.g. the Fernet helper lift cascades into a wider repository refactor) — surface as a flight-level redirect; this flight should land focused admin work, not a structural payment-down
- The rotation eviction wiring surfaces a race condition between `install_key` and `_evict_all_for_account` that requires rethinking the rotation transaction order — pause and escalate
- The MCP `__MASKED__` pattern at `api.py:901-942` has been refactored on `main` since the recon (verified live this flight) — re-cross-reference before mirroring
- A leg of work exceeds 1 day's planned scope by more than 50% — split the leg, log the deviation
- The browser-test framework requires non-trivial fixture changes to register the stub plugin (e.g. the production discovery path needs to be patched for the duration of a browser test) — surface and decide whether to add a test-mode injection hook to `register_builtin_connectors` or take a different test-fixture path

**Acceptable variations**:
- Exact field placement in the editor form (Connection vs. Credentials vs. dedicated Lifecycle section for idle-TTL) can shift based on UX feel during leg 5; the criterion is "operator can find and edit the idle-TTL value from the detail page"
- The optional in-flight override body on the doctor probe (parallel to MCP F8 L4) can be deferred to a follow-on flight if the leg-3 author feels it complicates the launch shape
- The `connectors/README.md` skeleton plugin code block can sketch against a Discord-shaped or Slack-shaped or fully-hypothetical platform — the goal is to show the Protocol shape concretely
- The doctor-probe response shape's `details` rendering in the UI is open to leg-5's UX judgment as long as no plaintext secret values appear in the banner

### Legs

> **Note:** Tentative leg breakdown (6 legs). Legs are planned in detail one at a time as the flight progresses; this list will evolve based on discoveries during implementation. Each leg gates on `make test` + `make lint` clean before signaling completion, per the M07 / F1 debrief lesson — no separate "verify everything" closer.

- [x] `pre-leg-maintenance-from-f1` — Bundle Flight 1 debrief carry-forward: (1) lift `_secrets_to_ciphertext`/`_ciphertext_to_secrets` to a shared helper pair in `db/repositories.py`; both `MCPSourceRepository` and `ConnectorAccountRepository` call the shared helpers (~30 LoC behaviour-preserving refactor); (2) add `function-local-import-to-break-load-cycle` to `agents.md` Project Conventions with the three citation points; (3) patch `agents.md` connector-type checklist item 4 (v14→v15→v16 renumber) AND item 6 (Studio-placement correction, not `admin.js`); (4) add a "Skeleton for a real plugin" code block to `connectors/README.md` §3 (~30 lines); (5) patch the F1 flight.md leg-6 bullet to reflect that lifespan wiring shipped in F1. Verification: existing repository tests pass byte-identically; `agents.md` grep finds the new convention AND the corrected checklist items; README §3 has the new code block; F1 flight.md no longer says "wired into app.py only in Flight 2."

- [x] `idle-ttl-field` — v15 migration adds `idle_timeout_seconds INTEGER NULL` to `connector_accounts`. `ConnectorAccount.idle_timeout_seconds: int | None = None` with `1 <= value <= 604800` validator (7-day upper bound catches ms-vs-s typos). Repository round-trip on create / update / list / get. `_resolve_ttl_seconds(override: int | None = None) -> int` resolution order: explicit override → env var (read at call time) → 1800 default. `acquire()` calls `_resolve_ttl_seconds(override=account.idle_timeout_seconds)`. Schema-version renumber sites updated (all four sites enumerated in Technical Approach): `_connector_types.py:11-13` docstring, `tests/test_db_migration.py:226-231` (value + message), `tests/test_db_migration.py:1230-1243` (`TestSchemaV14` docstring), `agents.md` checklist item 4 (already done in leg 0). Test: v15 migration is idempotent and crash-safe; explicit override beats env var; env var beats default; resolution is live-read at call time (monkeypatch in test changes resolution behavior without process restart).

- [x] `rest-crud-and-masked-sentinel` — Add `/api/connector-accounts` GET / POST / PUT / DELETE + `/types` to `interfaces/web/api.py` mirroring the MCP-sources section. `_connector_account_response` calls the existing generic `_mask_secrets` helper at `api.py:665` (NOT MCP-specific — OAuth-stripping happens in `_mcp_source_response` BEFORE `_mask_secrets`, so no inheritance concern). PUT implements per-key `__MASKED__` resolution as a verbatim mirror of `api.py:901-942` minus the OAuth-managed-keys block. On PUT with actual secrets change (resolved dict differs from existing): call `_evict_all_for_account`. On DELETE: call `_evict_all_for_account` BEFORE `repo.delete`. No `config` shape validation in this leg (deferred to per-connector flights). Test: end-to-end CRUD round-trip through httpx AsyncClient; masked-secrets-never-leak regression net (`"raw-secret-value" not in resp.text`); explicit `test_no_op_put_does_not_evict` (all-masked round-trip); explicit `test_dropping_a_key_evicts` (REST replace semantic — operator removes a key entirely → must evict); explicit `test_secrets_change_evicts`; DELETE evicts then deletes.

- [x] `rest-doctor-and-rotation-eviction` — Add `POST /api/connector-accounts/{account_id}/test/connect`: load account → resolve plugin via registry (unknown type → `{status: "error", details: {...}}` with 200) → `await plugin.doctor(account, encryptor)` inside `try/except ConnectorClientError` → return `{status, details}` from the `DoctorReport`. **No in-flight override body** — mirror MCP's launch shape (create-before-test). Route signature is `(account_id: str)` only; the editor's Test Connection button POSTs with no body. Wire `_evict_all_for_account` into `rotate_encryption_key` AFTER `await conn.commit()` (~L2862) and BEFORE the on-disk key replace: `for aid, _ in decrypted_connectors: await _evict_all_for_account(aid)`. The loop sits **outside** the existing commit `try/except` — eviction failure is logged but does not abort rotation (failure-mode rationale in Design Decisions). Test: doctor probe success / configured-failure / unknown-type / `ConnectorClientError` paths against the test-registered stub plugin; rotation-while-pool-warm (acquire → rotate → next acquire returns a fresh entry that decrypts under the new key — the F1 debrief carry-forward action item).

- [x] `frontend-grid-and-types` — `static/js/areas/studio/connector-accounts-grid.js` parallel to `admin/providers-grid.js`. `studio.js` gains a `connector-accounts` section with the routing (sub-paths `new` and `{id}`), selection state, and form-mode state mirroring the MCP block. Empty-canvas copy explicitly mentions "no connector types registered yet — Flight 8 will add Discord" so operators understand the production empty state. Frontend consumes `/api/connector-accounts/types` (empty in production); registered types render badges via a class allowlist analog to the `KNOWN_BADGE_TYPES` in `providers-grid.js`. Test (browser-flow): navigate to Studio → connector-accounts section renders empty state → New button opens form → Cancel returns to empty state.

- [x] `frontend-editor-and-browser-tests` — `static/js/areas/studio/connector-account-editor.js` parallel to `studio/mcp-server-editor.js`. Sections: editor-header, Connection (name / type / config kv editor), Credentials (secrets kv editor with per-key `__MASKED__` round-trip via `data-original-masked` attribute), Lifecycle (nullable `idle_timeout_seconds` input with "Use default (30 min)" placeholder + design-comment note about the Flight-3 chat-session lifecycle field landing next to this one), Test Connection (button → POST → status banner rendering `{status, details}` with the M04/M06 LED + labeled-kv body — `details`-block rendering shape is its own sub-deliverable per Technical Approach: secret-shaped values pass through without double-masking, non-string values render JSON-stringified in `font-mono`, `data-testid="connector-test-details"` for browser-test pinning), Danger Zone (delete on edit mode). M04/M06 design tokens throughout; no new CSS classes unless a connector-specific need surfaces (and then namespaced). Browser tests: `tests/browser/test_flow_studio_connector_account_navigation.py`, `test_flow_studio_connector_account_editor.py`, `test_connector_test_connection_button.py`, AND `test_flow_studio_connector_account_create_and_test.py` (the combined-action coverage) paralleling the MCP equivalents plus the new create-and-test flow. Snapshot baselines local-only per the gitignore + user-global rule. **Scope-flag at leg planning** (architect-flagged): four browser-test files + a design-language pass is at the upper end of leg scope; the leg author may propose splitting into 5a (editor JS + design-language audit) and 5b (browser-test quartet) if browser-fixture plumbing for stub-plugin registration turns out non-trivial. Verification: full browser-flow suite passes; the design-language quality bar is met without alignment-flight rework (a screenshot review at the end of the leg is the human-judgment gate).

---

## Post-Flight

### Completion Checklist

- [ ] All 6 legs completed
- [ ] Leg 0 maintenance bundle landed: Fernet helper lifted, `agents.md` convention added, `connectors/README.md` §3 skeleton block added, F1 flight.md leg-6 bullet patched
- [ ] v15 migration applies cleanly to v14; `idle_timeout_seconds` round-trips through the repository; pool `_resolve_ttl_seconds` honors per-account override
- [ ] REST CRUD routes (`/api/connector-accounts` GET / POST / PUT / DELETE + `/types`) follow the MCP-source pattern; `__MASKED__` sentinel resolution at the API edge mirrors `api.py:901-942` verbatim
- [ ] `_evict_all_for_account` wired into both per-account PUT (on actual secrets change) and rotation transaction (post-commit, pre-on-disk-key-replace)
- [ ] Doctor probe route returns `DoctorReport` as `{status, details}` JSON; unknown-type and `ConnectorClientError` paths return `{status: "error", ...}` with HTTP 200 (so the UI banner renders inline)
- [ ] Studio admin grid + editor land at the M04/M06 design-language bar without alignment-flight rework
- [ ] Per-key `__MASKED__` round-trip works end-to-end in the editor: re-saving a form without changing secrets preserves stored values
- [ ] Browser-flow tests pass: navigation, editor CRUD, test-connection button, masked-secret round-trip
- [ ] Rotation-while-pool-warm test (F1 debrief carry-forward) lands and passes
- [ ] `make test`, `make lint`, browser-test recipe all clean
- [ ] No regression on the existing MCP source / LLM provider / agent factory / encryption rotation surfaces; specifically: `_compute_visible_schemas` byte-identical for non-connector-attached agents; MCP `/test/connect` byte-identical; LLM provider `/test` byte-identical
- [ ] Flight log captures any deviations from the planned approach (including the deferred-decision flag on the doctor-probe in-flight override body)
- [ ] Code merged
- [ ] Mission flight checkbox ticked for Flight 2

### Verification

End-to-end verification of Flight 2 has three layers:

1. **REST layer** (Python tests against the FastAPI TestClient):
   - Stand up an in-memory SQLite at schema version 15 with a stub `ConnectorAccount` row
   - Exercise the full CRUD cycle (POST → GET → PUT → DELETE) and assert masked secrets in responses
   - Drive a per-key `__MASKED__` PUT and assert the stored secret round-trips
   - Patch the registry with the stub plugin via `register_for_test`; drive the doctor probe and assert `{status, details}` matches the configured stub response
   - Drive rotation; assert that warm pool entries are evicted post-commit; assert the next acquire returns a fresh entry that decrypts under the new key

2. **Frontend layer** (browser-flow tests via the existing Playwright recipe):
   - Navigate Studio → Connector Accounts → empty state → New → form → Cancel
   - Create a new account → list shows the tile → click tile → edit form → save with no changes → secrets preserved
   - Click Test Connection → status banner renders the configured stub doctor response
   - Delete the account → tile gone → grid empty-state returns

3. **Cross-cutting** (regression net):
   - `_compute_visible_schemas` byte-identical for non-connector-attached agents
   - MCP `/test/connect` byte-identical against snapshot-style assertions
   - LLM provider `/test` byte-identical
   - `make test` clean (the F1 baseline of 1774 unit tests grows by ~25-40 for Flight 2; the exact number lands during execution)
   - `make lint` clean
   - Browser-test recipe green

The Flight 1 stub-plugin end-to-end test (`tests/test_connectors_e2e.py::test_e2e_full_lifecycle`) is the regression baseline; this flight ADDS coverage on top, it does NOT change F1's contract.
