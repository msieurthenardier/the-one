# Leg: external-credential-grant

**Status**: completed
**Flight**: [External Client Access](../flight.md)

## Objective

Stand up a distinct external-client credential principal for the self-configuration
surface: a new secrets-bearing store, its `CredentialSource` + in-memory registry +
startup reconcile, the operator mint/list/revoke/rotate endpoints, and the
external→agent routing in `_calling_agent` — so an operator can grant a scoped
credential, hand it to a loopback MCP client, and that client can **read** its one
agent's configuration, while a revoked or surface-disabled credential is refused on
the next request with no restart.

## Context

- Implements flight **DD1** (distinct `ext_` principal on the same confined mount),
  **DD2** (encrypted store + secret-free projection + secret returned once at mint),
  **DD7** (per-principal revoke-one + rotate), **DD8** (startup reconcile), and the
  routing half of **DD9** (external resolution gated on surface-enabled).
- **Design refinement of DD2/DD9 — key on the surface row, not `agent_name`.**
  Reading the lifecycle code (`manage.disable`/`cascade_delete` delete the surface
  row and `unregister(row.id)`) showed a cleaner mechanism than the flight's
  `agent_name` FK + re-implemented surface-enabled re-check: the store's FK is
  `source_id REFERENCES mcp_sources(id) ON DELETE CASCADE`, so:
  - **surface-disable and agent-delete auto-revoke** every external credential for
    that agent (the surface row is deleted → FK cascade), which is exactly DD9's
    governance intent — an external principal never outlives the operator closing
    the surface;
  - **resolution reuses the agent's own DD9 refusal.** An external identifier
    resolves identifier → `source_id` → `owner_of(row)`, then the SAME
    `_calling_agent` tail already refuses when `row.id not in
    config.mcp_source_ids` (surface disabled/detached, `surface.py`). No separate
    surface-enabled check to write or keep in step;
  - **agent rename is a non-event** — `manage.cascade_rename` keeps the surface
    row id stable (only the ownership marker changes), so `source_id`-keyed
    credentials survive a rename with no work (the `agent_name` FK would have needed
    `ON UPDATE CASCADE` or explicit handling).
  The only explicit teardown left is in-memory registry eviction — mirror the
  existing `unregister(row.id)` call in `manage.disable` and `manage.cascade_delete`
  with an external-registry eviction.
- **Hard-revoke, no `revoked_at`.** Revoke is a row DELETE (consistent with the
  cascade path, which also hard-deletes); the credential store carries no revoked
  history. Audit of "which external principal tuned this agent" lives in the
  revision log's `source_principal` (Leg 2, DD3), not here — so the store needs no
  soft-delete column. This drops `revoked_at` from the flight's DD2 sketch.
- `last_used_at` is **deferred** (flight Adaptation Criteria: droppable if it adds a
  per-request write on the hot resolve path). Not in this leg.
- **The `agt_` path is the template throughout.** `the_one/self_configuration/
  credentials.py` (registry, source, `register_credential_source_once` by list
  membership), `manage.enable`/`disable`/`reconcile_on_startup`, and the seam
  (`api_credential.py:register_source`/`resolve_caller`, prefix-routed
  `LocalApiCredential.parse`) are all mirrored, not re-invented.
- Prefix routing at the seam is free: `LocalApiCredential.parse(token,
  prefix="ext")` — `FileCredentialSource` (`loc`) and `SelfConfigurationCredentialSource`
  (`agt`) both reject an `ext_` token on prefix mismatch and fall through
  (`api_credential.py:LocalApiCredential.parse`).

## Inputs

- Flights 1 & 2 landed on `main` (v35): the surface, the four tools, the `agt_`
  credential + registry, `CONFINED_SOURCE_PATHS`, `manage.*`, the operator control
  plane, and `CredentialGateMiddleware` confinement all present.
- `get_encryptor(settings.data_dir)` and the `(conn, encryptor)` repository idiom
  (`repositories.py`, e.g. `MCPSourceRepository.__init__:495`).
- The v34 `CREATE TABLE` migration is the additive-migration template
  (`schema.py:1962-2000`).

## Outputs

- New table `agent_external_credentials` (migration **v36**; `CURRENT_VERSION` → 36).
- New module `the_one/self_configuration/external_credentials.py` — the external
  registry, `ExternalAgentCredentialSource`, `register`/`unregister`/`load_from_rows`/
  `register_credential_source_once`, mirroring `credentials.py`.
- New repository `AgentExternalCredentialRepository(conn, encryptor)` in
  `repositories.py`.
- Four operator endpoints under `/api/agents/{name}/self-configuration/external-credentials`
  (mint, list, revoke, rotate) + an `_agent_external_credentials_repo()` helper in
  `api.py`.
- `_calling_agent` (`surface.py`) routes an external caller (`caller.source ==
  EXTERNAL_SOURCE_NAME`) via the external registry, sharing the existing
  owner-resolution + surface-enabled refusal tail.
- External-registry eviction added to `manage.disable` and `manage.cascade_delete`;
  the external source registered + reconciled at lifespan startup (`app.py`).
- `EXTERNAL_SOURCE_NAME` + `EXTERNAL_CREDENTIAL_PREFIX` constants and a second
  `CONFINED_SOURCE_PATHS` entry in `constants.py`.

## Acceptance Criteria

- [x] **AC1 — Migration.** `CURRENT_VERSION == 36`; a fresh DB and a v35→v36 upgrade
      both yield `agent_external_credentials(identifier PK, source_id NOT NULL
      REFERENCES mcp_sources(id) ON DELETE CASCADE, secret NOT NULL, label NOT NULL,
      created_at NOT NULL)` plus an index on `source_id`. Migration is idempotent /
      partial-apply safe (`CREATE TABLE IF NOT EXISTS`, version stamp `INSERT OR
      IGNORE` last), verified against the live SQLite schema.
- [x] **AC2 — Secret encrypted at rest.** A minted credential's secret is stored
      only Fernet-encrypted (via the shared encryptor); the raw `secret` column
      value never equals the plaintext secret. Asserted by reading the column
      directly.
- [x] **AC3 — Mint returns the token once, scoped, and only when enabled.** `POST
      …/external-credentials` with `{label}` on an **enabled** agent (surface row
      present AND attached — `row.id in config.mcp_source_ids`) returns `{identifier,
      label, token: "ext_<id>.<secret>", url}` exactly once; the token authenticates
      (AC6). `POST` is **409** when the surface is not enabled — this includes both
      *no surface row* and an **orphaned** (detached-but-present) row (review Issue
      #1: gate on enabled, not on `find_surface_row is not None`, so a dormant
      credential can never be minted against a detached surface that would silently
      start working on re-attach). No other endpoint ever returns the secret.
- [x] **AC4 — List is secret-free (structural projection).** `GET
      …/external-credentials` returns a list of `{identifier, label, created_at}`
      built as a purpose-built dict — never serializing the `secret` column. A
      seeded literal secret is asserted absent from the response body.
- [x] **AC5 — Revoke is immediate and scoped; rotate reissues.** `DELETE
      …/external-credentials/{identifier}` removes the row and evicts the registry
      entry → the next request bearing that token is 401, no restart. `POST
      …/external-credentials/{identifier}/rotate` deletes the old and returns a new
      `{identifier, token}` once; the old token is 401, the new authenticates.
      Both 404 when `{identifier}` is not a credential of `{name}`'s surface (cross-ID
      guard). Neither disturbs the agent's own `agt_` credential or another external
      credential.
- [x] **AC6 — A loopback MCP client reads config with an `ext_` token.** A
      credential minted for agent A, presented as `Authorization: Bearer ext_…` by an
      out-of-process MCP client against `/mcp/self-configuration/`, resolves to A and
      `get_my_configuration` returns A's projection (the existing secret-free
      projection, unchanged). The response contains no secret and no approval-mode
      field.
- [x] **AC7 — Confinement holds for the new source.** The same `ext_` credential is
      403 on any path outside `/mcp/self-configuration` and on every WebSocket
      upgrade (the second `CONFINED_SOURCE_PATHS` entry drives the existing gate).
- [x] **AC8 — Cross-agent isolation.** An `ext_` credential for agent A never
      resolves to agent B: A's token cannot read B's configuration and vice versa,
      with both agents enabled and both credentials live.
- [x] **AC9 — Dies with the surface (DD9).** Disabling the surface for A (or deleting
      agent A) revokes A's external credentials — the FK cascade removes the rows and
      the registry is evicted — so A's `ext_` token is 401 on the next request, no
      restart. An **orphaned** surface (detached via `PUT /api/agents/{A}` without
      delete) refuses the `ext_` token's tool calls via the existing `_calling_agent`
      DD9 refusal.
- [x] **AC10 — Survives restart (DD8).** After a process restart, a non-revoked
      `ext_` credential still resolves (the startup reconcile rebuilds the external
      registry from the store); a revoked one does not (its row is gone).
- [x] **AC11 — Registered on the seam idempotently.** `ExternalAgentCredentialSource`
      is registered via `register_source` by actual list membership (mirroring
      `register_credential_source_once`), self-healing across `_sources` swaps in
      test fixtures.

## Verification Steps

- AC1: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_schema*.py -x
  --timeout 30` plus a new migration test asserting the table shape and
  `CURRENT_VERSION`; inspect `PRAGMA foreign_keys` fires on the real connection.
- AC2/AC4: a repository/endpoint test seeds a known secret literal and asserts it is
  absent from both the stored column (encrypted) and the list-endpoint body.
- AC3/AC5: endpoint tests over the mint/list/revoke/rotate lifecycle, asserting the
  401-after-revoke and the 409-when-not-enabled.
- AC6/AC7/AC8/AC9: out-of-process MCP-client tests using the `running_surface`
  uvicorn-on-loopback fixture in `tests/test_self_configuration_surface.py`.
  **Presentation-path note (review Issue #2):** the existing template derives the
  bearer from a surface **row** (`MCPClient(source=row, auth_provider=None)` reading
  `row.secrets["Authorization"]`) — an `ext_` credential is a **standalone bearer
  with no row**, so the test must present it explicitly: build a synthetic in-memory
  `MCPSource(type="streamable-http", config={"url": manage.surface_url()},
  secrets={"Authorization": "Bearer ext_<id>.<secret>"})` fed to `MCPClient`, OR a raw
  `mcp.client.streamable_http` client with an `Authorization` header. Budget for this
  new path — it is not a 1:1 reuse of the template.
- AC1/AC9: the cascade tests must run on a connection with `foreign_keys=ON`; assert
  `PRAGMA foreign_keys == 1` on the connection under test (the runtime singleton sets
  it at `connection.py:20`, and `isolated_db`'s side connection at `conftest.py:342`
  does too — but a test opening its own `aiosqlite` connection to assert the child-row
  deletion must issue the PRAGMA itself, or the cascade silently won't fire and AC9
  false-passes). Also assert list returns empty for a disabled agent (rows
  cascade-gone) and non-empty for an orphaned one.
- AC10: a test that rebuilds the registry via the reconcile hook and asserts
  resolve-before/after for a live vs revoked credential.
- AC11: assert membership-based idempotency across an `api_credential._sources` swap
  (mirror the `agt` precedent), not a boolean guard.
- Whole unit suite once at leg-end: `make test-unit`.

## Implementation Guidance

1. **Constants** (`constants.py`): add `EXTERNAL_SOURCE_NAME =
   "self-configuration-external"`, `EXTERNAL_CREDENTIAL_PREFIX = "ext"`, and a second
   `CONFINED_SOURCE_PATHS` entry `EXTERNAL_SOURCE_NAME: MOUNT_PATH`. Keep the module
   import-light (middleware imports it).
2. **Migration v36** (`schema.py`, mirror the v34 block): `CREATE TABLE IF NOT
   EXISTS agent_external_credentials (...)` with the FK to `mcp_sources(id) ON DELETE
   CASCADE`, an index on `source_id`, `INSERT OR IGNORE INTO schema_version` last,
   `commit`, `version = 36`. Bump `CURRENT_VERSION = 36`. `mcp_sources` is created
   far earlier in-sequence (v10), so the FK resolves.
3. **Repository** (`repositories.py`): `AgentExternalCredentialRepository(conn,
   encryptor)` with `create(source_id, label, credential)` (encrypt the encoded
   `ext_` header/secret — store the secret component, or the full encoded token,
   consistently with how it will be resolved), `list_for_source(source_id)` →
   secret-free rows, `get(identifier)`, `delete(identifier) -> bool`, and
   `load_all()` → decrypted `(identifier, source_id, secret)` for reconcile. Use the
   `_encrypt_secrets_blob`/`encryptor.encrypt` path already in the module.
4. **External module** (`external_credentials.py`, mirror `credentials.py`):
   `_ext_registry: dict[str, tuple[str, str]]` (identifier → (source_id, secret)),
   `register`/`unregister`/`source_id_for`/`load_from_rows`/`clear_for_test`,
   `ExternalAgentCredentialSource` (`name = EXTERNAL_SOURCE_NAME`, `resolve` parses
   with `EXTERNAL_CREDENTIAL_PREFIX` and constant-time-compares), and
   `register_credential_source_once` by list membership.
5. **Routing in `_calling_agent`** (`surface.py`): when `caller.source ==
   EXTERNAL_SOURCE_NAME`, resolve `source_id` from the **external** registry
   (`external_credentials.source_id_for`); otherwise the existing `agt` registry.
   Share the existing owner-resolution + `row.id in config.mcp_source_ids` refusal
   tail unchanged (this is what gives external callers the DD9 surface-enabled gate
   for free). Return `agent_name` as today (Leg 2 extends this for provenance).
6. **Endpoints** (`api.py`, mirror the enable/disable idiom): add
   `_agent_external_credentials_repo()` (via `get_encryptor(settings.data_dir)`), and
   the four routes. Mint/rotate resolve the agent's surface row and gate on
   **enabled** — `manage.status(...)['enabled']` (equivalently `row is not None and
   row.id in config.mcp_source_ids`), **409** otherwise (covers both no-row and
   orphaned/detached — review Issue #1; do NOT gate on `find_surface_row is not None`
   alone, which admits orphaned rows). Revoke/rotate enforce the cross-ID guard (the
   credential's `source_id` must equal `{name}`'s surface row id, else 404). Register
   + evict the external registry alongside the store writes.
7. **Teardown wiring**: in `manage.disable` and `manage.cascade_delete`, after the
   existing `unregister(row.id)`, evict the external registry for that `source_id`
   (the FK cascade already removed the rows; this drops the in-memory entries).
   `cascade_rename` needs nothing (row id stable).
8. **Lifespan** (`app.py`): register `ExternalAgentCredentialSource` via its
   `register_credential_source_once` (mirror the `agt` registration site) and rebuild
   the external registry from the store at startup (mirror `manage.reconcile_on_startup`
   → `load_from_rows`).

## Edge Cases

- **Mint before enable** → 409 (no surface row to scope to). Re-enable after a
  disable mints a fresh surface row (new id); prior external credentials were already
  cascade-deleted, so the operator re-grants.
- **Revoke/rotate a foreign identifier** (belongs to another agent's surface) → 404,
  never a cross-agent mutation.
- **Registry vs DB disagreement** (crash between store write and register) → the
  startup reconcile (`load_all` → rebuild) is the recovery path, exactly as
  `load_from_rows` is for `agt`.
- **Orphaned surface** (detached, not deleted) → registry still resolves the token
  but `_calling_agent`'s existing refusal blocks the tool call; defense-in-depth.
- **Circular import**: `external_credentials.py` must stay leaf-ish like
  `credentials.py` (function-local import of `api_credential` inside
  `register_credential_source_once`; inline the surface-row marker check if needed to
  avoid importing `manage`).
- **Malformed-marker delete fallback** (review Issue #3, `api.py:~2010`
  `delete_mcp_source`): a surface row whose `owner_of` is `None` (degenerate marker)
  falls to a bare `repo.delete(source_id)` that skips `manage.disable`'s
  external-registry eviction. Harmless today (mint requires a non-`None` owner, so no
  external credential can exist for an owner-less row, and the FK cascade cleans the
  DB rows regardless) — add a one-line defensive comment there so a future change to
  mint's gate can't reopen a stale-registry hole.

## Files Affected

- `the_one/db/schema.py` — v36 migration; `CURRENT_VERSION = 36`.
- `the_one/db/repositories.py` — `AgentExternalCredentialRepository`.
- `the_one/self_configuration/constants.py` — new source name, prefix, confinement
  entry.
- `the_one/self_configuration/external_credentials.py` — NEW registry + source.
- `the_one/self_configuration/surface.py` — `_calling_agent` external routing.
- `the_one/self_configuration/manage.py` — external-registry eviction in
  `disable`/`cascade_delete`.
- `the_one/interfaces/web/api.py` — `_agent_external_credentials_repo()` + four
  endpoints.
- `the_one/interfaces/web/app.py` — lifespan registration + reconcile.
- `tests/…` — migration test, repository/endpoint tests, out-of-process `MCPClient`
  tests (modeled on `tests/test_self_configuration_surface.py`).
- Docs: `SECURITY-MODEL.md` (the external-credential source + store + its scope) —
  may be deferred to the flight-end doc pass, but the store's secret handling is
  worth a note here.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` — 4481 passed, 10 skipped (pre-existing), 0 failed)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (per `/agentic-workflow`: `landed` at
      leg-end; `completed` is deferred to the flight-end review + commit)
- [x] Check off this leg in flight.md
- [x] (Not final leg — no flight-status change here)
- [x] Do NOT commit (deferred to flight-end review per `/agentic-workflow`)

## Citation Audit
*(verified against `main` @ b942395, 2026-08-27)*

- `schema.py:1962-2000` — v34 `agent_revisions` CREATE-TABLE migration template;
  `CURRENT_VERSION = 35` at `schema.py:15`. ✓
- `the_one/self_configuration/credentials.py` — full `agt` registry/source template
  (mint/encode/register/unregister/`load_from_rows`/`SelfConfigurationCredentialSource`/
  `register_credential_source_once`). ✓
- `manage.py:150 enable`, `:220 disable` (calls `unregister(row.id)` at `:263`),
  `:391 cascade_delete` (`unregister` at `:410`), `:370 cascade_rename` (row id
  stable), `:267 reconcile_on_startup`, `:81 find_surface_row`, `:60 owner_of`. ✓
- `api_credential.py` — `LocalApiCredential` (`:67`, `.parse` prefix routing `:92`),
  `CredentialSource` protocol (`:392`), `register_source` (`:442`), `resolve_caller`
  (`:450`). ✓
- `api.py:959 enable`, `:977 disable`, `:944 status`, `:821 cascade_delete` caller,
  `:936 cascade_rename` caller, `:1997` second disable path; repo helpers
  `_agent_store():80`, `_mcp_repo():243`, `_agent_revisions_repo():265`;
  `get_encryptor` at `:49`. ✓
- `surface.py:_calling_agent` (reads `CALLER_SCOPE_KEY` off the ASGI scope; DD9
  refusal `row.id not in config.mcp_source_ids`). ✓
- `repositories.py:36 _encrypt_secrets_blob`, `:495` MCPSourceRepo `(conn, encryptor)`
  idiom. ✓
