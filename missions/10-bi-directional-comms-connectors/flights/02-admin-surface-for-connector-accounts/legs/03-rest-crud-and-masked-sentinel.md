# Leg: rest-crud-and-masked-sentinel

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Ship the operator-facing REST surface for connector accounts: GET (list / by-id / types), POST (create), PUT (update with per-key `__MASKED__` resolution and eviction-on-secrets-change), and DELETE (eviction-then-delete). Mirrors the MCP-source CRUD section verbatim minus the OAuth-managed-keys handling that's MCP-specific.

## Context

### Why this leg

Per the flight's leg breakdown and the mission criterion "An operator can register, edit, and remove connector accounts ... through an Admin surface that follows the existing design language and the existing LLM-providers / MCP-sources patterns, with all sensitive fields persisted under the same encryption pipeline that already protects LLM and MCP credentials":

- Flight 2 surfaces the operator mechanics. The REST surface is the first surface a frontend can address; without it, the Studio editor + grid in legs 4-5 has nothing to talk to.
- The MCP-source CRUD at `interfaces/web/api.py:840-1064` is the structural template — same shape: list / types / get-by-id / create / update / delete, masked secrets in responses, per-key `__MASKED__` PUT resolution, eviction wiring on credential changes and delete.
- What does NOT transfer from MCP: the `_OAUTH_MANAGED_SECRET_KEYS` strip-on-GET + preserve-on-PUT block (OAuth is MCP-specific), the `_cache` server-managed config-key block (MCP-specific), the lazy-install runtime cache cleanup (MCP-specific). The connector PUT is the "core" MCP shape minus the OAuth + cache add-ons.

### Relevant design decisions

- **"Pool eviction wired into BOTH rotation AND per-account PUT (secrets change); rotation eviction lives OUTSIDE the commit try/except"** — this leg owns the per-account PUT eviction half (rotation eviction lives in leg 4). Two explicit edge cases on PUT eviction:
  - `no_op_all_masked_does_not_evict` — operator opens the form and saves without changing anything; every secret round-trips as `__MASKED__` and resolves back to the existing stored values, so `existing.secrets == resolved_secrets` and eviction is skipped.
  - `dropping_a_key_evicts` — operator drops a key by omitting it from the incoming secrets dict (REST replace semantic per the MCP precedent at `api.py:903-905`); the resolved dict is shorter than existing — `existing.secrets != resolved_secrets` and eviction MUST fire even though no value changed in-place.
- **`config` shape validation gating** — this leg does NO per-type `config` validation. The stub plugin (F1) accepts arbitrary config; per-type validation lands per-connector in Flights 8 / 9 (mirror of `_validate_mcp_source_config` which is type-aware). The leg-3 acceptance criteria document the deferral explicitly so future readers don't think it was forgotten.
- **No reference-check on DELETE** — Flight 4 of the mission adds `connector_account_ids` to `AgentConfig`, so a "are any agents attached?" guard belongs at that point, not here. Leg-3 DELETE calls `_evict_all_for_account` BEFORE the row delete (mirror of MCP's eviction step at L1016) and trusts the operator's intent. A comment notes the future check.
- **Stub plugin is NOT exposed via `/api/connector-accounts/types` in production** — leg 1 of this flight has already established the empty-tuple baseline; this leg's `/types` route returns `[{value, label}]` derived from `the_one.connectors.registry.types()`. In production: empty list. In tests that pre-register the stub via `register_for_test`: `[{"value": "stub", "label": "Stub"}]`.

### Key learnings from prior flights

- **`_MASKED_API_KEY_SENTINEL` forward-reference works** — the MCP PUT block at L919 uses `_MASKED_API_KEY_SENTINEL` even though the constant is defined at L2157. Python resolves the name at call time, not at definition time. The connector PUT follows the same pattern — no need to hoist the constant.
- **Route registration order matters for `/types` vs `/{account_id}`** — `/types` MUST be registered BEFORE `/{account_id}` because FastAPI matches in registration order. The MCP precedent at L848 (right after L840 list and right before L863 get-by-id) carries the explicit comment; the connector section mirrors verbatim.
- **F2 L1 already lifted the Fernet helpers** — repository's encryption envelope is module-level free functions; this leg does NOT touch the helpers, only consumes the repository surface.
- **F2 L2 already added `idle_timeout_seconds`** — `ConnectorAccount` now carries the field; the round-trip is in place via leg 2. PUT requests including `idle_timeout_seconds` round-trip transparently; PUT requests omitting it leave the existing value intact (model_copy update merges, doesn't replace).

## Inputs

What exists before this leg runs:

- `the_one/interfaces/web/api.py:23-33` — imports `MCPSourceRepository` and friends from `the_one.db.repositories`; does NOT yet import `ConnectorAccountRepository` or `ConnectorAccount`.
- `the_one/interfaces/web/api.py:58-61` — `_mcp_repo()` helper. No `_connector_repo()` yet.
- `the_one/interfaces/web/api.py:623-1064` — the MCP Sources section: helpers, routes (list / types / get / post / put / delete), and connection-reset / OAuth-callback routes that come AFTER the basic CRUD.
- `the_one/interfaces/web/api.py:626-673` — `_mask_secret_value`, `_OAUTH_MANAGED_SECRET_KEYS` (imported from `mcp.oauth.storage`), `_mask_secrets`. **`_mask_secret_value` and `_mask_secrets` are generic** and reusable for connectors — they apply per-key masking without any MCP-specific knowledge.
- `the_one/interfaces/web/api.py:676-712` — `_mcp_source_response` — the MCP-specific response shape that strips `_OAUTH_MANAGED_SECRET_KEYS` before masking and surfaces `oauth_active` / `has_access_token` flags. Connectors' version is simpler: model_dump + replace `secrets` with `_mask_secrets(...)`.
- `the_one/interfaces/web/api.py:840-1064` — the MCP CRUD routes section, the structural template for this leg's edits.
- `the_one/interfaces/web/api.py:891-966` — `update_mcp_source`: the per-key `__MASKED__` resolution block (L901-942), the `_cache` preservation block (L944-958), `model_copy(update=data)` + `model_validate` re-validation (L960-963), and the eviction-less commit (MCP does not evict warm pool entries on PUT; only on DELETE — connectors will diverge from MCP HERE per the flight Design Decision on pool eviction).
- `the_one/interfaces/web/api.py:2157` — `_MASKED_API_KEY_SENTINEL = "__MASKED__"`. Used by both LLM-provider and MCP-source PUT; this leg's connector PUT consumes it too.
- `the_one/connectors/_pool.py:244-266` — `_evict_all_for_account(account_id)` — function already exists from F1; this leg imports and calls it from the PUT (on secrets change) and DELETE handlers.
- `the_one/connectors/registry.py` — `types()` lookup; consumed by `/api/connector-accounts/types`.
- `the_one/db/repositories.py:432-559` — `ConnectorAccountRepository` with `list / get / create / update / delete / _row_to_model`. Round-trips all 8 fields (incl. `idle_timeout_seconds` per F2 L2).
- `the_one/db/models.py:118-137` — `ConnectorAccount` Pydantic model (8 fields after F2 L2).
- `tests/test_db_api.py:197-...` — `TestMCPSourceAPI` is the structural precedent for the new connector REST tests.

## Outputs

What exists after this leg completes:

- **Imports** (`the_one/interfaces/web/api.py:23-33`) — `ConnectorAccount` added to the `db.models` import; `ConnectorAccountRepository` added to the `db.repositories` import. Alphabetical insertion in both lists.
- **Helper: `_connector_repo`** — module-level async helper placed alongside `_mcp_repo` (at L58, before / after / wherever the placement matches the existing helpers' alphabetic-or-grouping convention; visually consistent with `_mcp_repo`). Implementation: `conn = await get_connection(); encryptor = get_encryptor(settings.data_dir); return ConnectorAccountRepository(conn, encryptor)`.
- **Helper: `_connector_account_response`** — placed in the new "Connector Accounts" section. Implementation: `data = account.model_dump(); data["secrets"] = _mask_secrets(account.secrets); return data`. No `_OAUTH_MANAGED_SECRET_KEYS` strip (connectors don't have OAuth-managed keys in this leg); no `oauth_active` / `has_access_token` flags (no OAuth surface). Just the canonical masked-secrets shape.
- **New section header**: `# ── Connector Accounts ───────────────────────────────────────────────────` — placed AFTER the MCP-related section terminus and BEFORE the next existing section header (likely the OAuth callback section at L1622). Visually mirrors the MCP section header.
- **Six routes**, registered in this order (so `/types` matches before `/{account_id}`):
  1. `GET /api/connector-accounts` → list. Calls `_connector_repo()` → `repo.list()` → `[_connector_account_response(a) for a in accounts]`.
  2. `GET /api/connector-accounts/types` → `[{value, label}]` from `the_one.connectors.registry.types()`. Label is the value with first-letter-uppercased (mirror MCP's "Stdio" / "Streamable HTTP" pattern; for "stub" it would be "Stub", for "discord" it would be "Discord").
  3. `GET /api/connector-accounts/{account_id}` → get-by-id; 404 on `KeyError`.
  4. `POST /api/connector-accounts` (status_code=201) → mints `data["id"] = uuid.uuid4().hex[:12]` if not provided; `ConnectorAccount.model_validate(data)` (422 on `ValidationError`); `repo.create(account)`; returns masked response. No `config`-shape validation in this leg (deferred per Design Decisions).
  5. `PUT /api/connector-accounts/{account_id}` → load existing → resolve per-key `__MASKED__` in `secrets` (verbatim mirror of api.py:910-926 minus the OAuth-managed-keys block at L927-942) → `model_copy(update=data)` → `repo.update(...)` → **eviction on secrets-change**: if `existing.secrets != resolved_secrets`, call `await _evict_all_for_account(account_id)`. Returns masked response.
  6. `DELETE /api/connector-accounts/{account_id}` → load existing (404 if missing) → `await _evict_all_for_account(account_id)` BEFORE the row delete (mirror of MCP `delete_mcp_source` step 2 at L1016) → `await repo.delete(account_id)` → returns `{"status": "ok"}`. A leg-test comment notes the future per-agent-reference-check (Flight 4 adds `connector_account_ids` to `AgentConfig`).
- **Tests** in `tests/test_db_api.py` — a new `TestConnectorAccountAPI` class mirroring `TestMCPSourceAPI`. Eight required tests (all from the flight spec):
  1. `test_crud_round_trip` — POST → GET → PUT → DELETE; assert each transition returns the right status.
  2. `test_list_returns_masked_secrets` — POST a row with `secrets={"BOT_TOKEN": "secret_real_value"}`; GET list; assert `secrets["BOT_TOKEN"]` is masked (≥4 chars: `"***...alue"`); assert raw plaintext not anywhere in `resp.text`.
  3. `test_put_masked_sentinel_preserves_secret` — POST with secret; PUT with `secrets={"BOT_TOKEN": "__MASKED__"}`; GET assert masked form unchanged (proves the stored ciphertext still decodes to the original); plaintext not in response.
  4. `test_no_op_put_does_not_evict` — register the stub plugin (`register_for_test("stub", StubPlugin)`); POST a stub-typed account; acquire a warm pool entry; PUT the same secrets dict with every value as `__MASKED__`; assert that the warm pool entry STILL EXISTS afterward (no eviction).
  5. `test_dropping_a_key_evicts` — same setup; PUT with `secrets={}`; assert the warm pool entry is GONE.
  6. `test_secrets_change_evicts` — same setup; PUT with `secrets={"BOT_TOKEN": "new_value"}`; assert the warm pool entry is GONE.
  7. `test_delete_evicts_then_deletes` — same setup; DELETE; assert the warm pool entry is GONE; assert the row no longer exists via GET.
  8. `test_unknown_account_returns_404` — GET / PUT / DELETE on a made-up id return 404.
- **Required regression nets** (promoted from optional during design review — they cover paths the eight mandatory tests don't):
  9. `test_types_returns_empty_in_production` — without `register_for_test`, GET `/api/connector-accounts/types` returns `[]`.
  10. `test_types_returns_registered_in_test` — with `register_for_test("stub", StubPlugin)`, GET `/api/connector-accounts/types` returns `[{"value": "stub", "label": "Stub"}]`.
  11. `test_create_with_invalid_payload_returns_422` — POST with missing required field (e.g. no `type`) returns 422 with a `ValidationError`-shaped detail.
  12. `test_adding_a_new_key_evicts` — design-review-recommended regression net for the "operator adds a NEW secret while masking an existing one" path: POST with `secrets={"BOT_TOKEN": "real"}`, acquire a warm entry, PUT with `secrets={"BOT_TOKEN": "__MASKED__", "OTHER_KEY": "new_value"}`. Resolved dict = `{"BOT_TOKEN": "real", "OTHER_KEY": "new_value"}` ≠ existing. Eviction MUST fire.
- Flight log "Leg Progress" entry appended.
- Flight artifact's leg-3 checkbox ticked.

## Acceptance Criteria

- [ ] `interfaces/web/api.py` imports `ConnectorAccount` from `db.models` and `ConnectorAccountRepository` from `db.repositories`.
- [ ] `_connector_repo()` async helper exists and is structurally identical to `_mcp_repo()`.
- [ ] `_connector_account_response(account)` helper exists and produces `{...model_dump fields..., secrets: <masked>}` with no plaintext secret values.
- [ ] Six new routes exist at the documented paths, registered in the documented order (so `/types` matches before `/{account_id}`).
- [ ] POST mints `id` if not provided; returns 201; returns masked response.
- [ ] PUT resolves per-key `__MASKED__` sentinel (preserve from existing); resolves omitted-key (drop-by-omission); rejects non-dict `secrets` with 422.
- [ ] PUT calls `_evict_all_for_account` if-and-only-if `existing.secrets != resolved_secrets`.
- [ ] DELETE calls `_evict_all_for_account` BEFORE `repo.delete`; returns `{"status": "ok"}`; race-deletes through to 404 if the row is gone mid-call (mirror of MCP's step-4 retry pattern).
- [ ] Unknown `account_id` on GET-by-id, PUT, and DELETE returns 404 with a clear detail string.
- [ ] The 8 mandatory + 4 design-review-promoted tests land in `tests/test_db_api.py::TestConnectorAccountAPI` and all pass (12 tests total).
- [ ] `test_secrets_change_evicts` and `test_dropping_a_key_evicts` are the two explicit failure-mode regression nets; `test_no_op_put_does_not_evict` is the corresponding positive regression net.
- [ ] **No plaintext secret value appears anywhere in any response payload** (`raw_secret not in resp.text` assertion in every test that creates a secret).
- [ ] `make test` clean (delta: +at least 8 tests; no regressions on existing surface); `make lint` clean.
- [ ] No changes to MCP routes, LLM-provider routes, or the rotation transaction (rotation eviction lives in leg 4).

## Verification Steps

How to confirm each criterion:

- `grep -n "ConnectorAccount\|ConnectorAccountRepository\|_connector_repo\|_connector_account_response\|/api/connector-accounts" the_one/interfaces/web/api.py | head -30` — every expected import + helper + route site lights up.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestConnectorAccountAPI` — all 8-11 tests green.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestMCPSourceAPI` — MCP routes unchanged (no regressions).
- `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — full API tests green.
- `make test` — full suite clean. Pass-count delta from leg-2's 1785: +at least 8 tests.
- `make lint` — clean.
- Manual smoke: `docker exec the-one curl -s http://localhost:8080/api/connector-accounts | jq` — returns `[]` (production has no rows, no types).

## Implementation Guidance

1. **Import additions** (`the_one/interfaces/web/api.py:23-33`)
   - Add `ConnectorAccount` to the `db.models` import (alphabetically before `KBItem` or after — match the existing list's ordering convention).
   - Add `ConnectorAccountRepository` to the `db.repositories` import (alphabetically; it will sit before `KBItemRepository`).

2. **Helper: `_connector_repo`**
   - Place AFTER `_mcp_repo` at api.py:58-61 (so the helpers are visually grouped):
     ```python
     async def _connector_repo() -> ConnectorAccountRepository:
         conn = await get_connection()
         encryptor = get_encryptor(settings.data_dir)
         return ConnectorAccountRepository(conn, encryptor)
     ```

3. **Helper: `_connector_account_response`**
   - Place in the new "Connector Accounts" section (see step 4 for section placement):
     ```python
     def _connector_account_response(account: ConnectorAccount) -> dict[str, Any]:
         """Render a ConnectorAccount into the masked HTTP response shape.

         Mirrors ``_mcp_source_response`` minus the OAuth-managed-keys
         strip (connectors have no OAuth-managed keys this flight) and
         minus the ``_cache`` server-managed-key flag (no equivalent for
         connectors). Just model_dump + replace ``secrets`` with the
         per-key masked form.

         INVARIANT (mirror of ``_mcp_source_response``): ``model_dump()``
         populates ``data["secrets"]`` with the decrypted plaintext
         dict; we OVERWRITE that key with the masked form before
         returning. Any future refactor that removes the overwrite would
         leak plaintext via the API. The
         ``test_list_returns_masked_secrets`` assertion
         ``"<raw-secret>" not in resp.text`` is the regression net.
         """
         data = account.model_dump()
         data["secrets"] = _mask_secrets(account.secrets)
         return data
     ```
   - **DO NOT** import / reuse `_OAUTH_MANAGED_SECRET_KEYS` or the `_cache` block in this helper. Connectors don't have those concerns in Flight 2.

4. **Section placement**
   - Add a new section header `# ── Connector Accounts ────────────────────────────────────────────────────` AFTER the MCP-source section terminus (currently the MCP `oauth_start` route group ends somewhere around L2069; the next existing section header is `# ── Chat Sessions ─────────────────────────────────────────────────────────` at L2070). Place the connector section between MCP-related routes and Chat Sessions.
   - Inside the section: `_connector_account_response` first, then the 6 routes.
   - **Be deliberate about where in the file** — the section terminus may have moved since the cited line numbers. Use the section dividers (the `# ── Name ────` markers) to locate placement; do not rely on line numbers alone.

5. **Routes — registration order MATTERS**
   - The MCP precedent at api.py:840-847 (list before types before get-by-id) is the authoritative ordering. If `/{account_id}` registers BEFORE `/types`, a GET on `/types` will resolve to `get_connector_account` with `account_id="types"` and 404 (or worse, succeed-then-fail-validation in a confusing way).
   - **Order**:
     1. `GET /api/connector-accounts` → list
     2. `GET /api/connector-accounts/types` → types
     3. `GET /api/connector-accounts/{account_id}` → get-by-id
     4. `POST /api/connector-accounts` → create
     5. `PUT /api/connector-accounts/{account_id}` → update
     6. `DELETE /api/connector-accounts/{account_id}` → delete

6. **Route: `list_connector_accounts`** (`GET /api/connector-accounts`)
   - Verbatim shape of `list_mcp_sources` at api.py:840-844 — call `_connector_repo()` → `repo.list()` → `[_connector_account_response(a) for a in accounts]`.

7. **Route: `list_connector_account_types`** (`GET /api/connector-accounts/types`)
   - `the_one.connectors.registry.types()` ALREADY EXISTS (verified at design review, `connectors/registry.py:104`). Do NOT add a wrapper. Import as `from the_one.connectors.registry import types as _connector_types` (module-level or function-local; module-level is fine — `connectors/registry.py` has a clean import surface).
   - Return `[{"value": t, "label": t.capitalize()} for t in _connector_types()]`. Empty in production; `[{"value": "stub", "label": "Stub"}]` after `register_for_test("stub", StubPlugin)`. Add a docstring that mirrors the MCP precedent's NOTE about registration-order.

8. **Route: `get_connector_account`** (`GET /api/connector-accounts/{account_id}`)
   - Verbatim shape of `get_mcp_source` at api.py:863-870 — call `_connector_repo().get(account_id)`; raise 404 on `KeyError(f"Connector account not found: {account_id}")`.

9. **Route: `create_connector_account`** (`POST /api/connector-accounts`, `status_code=201`)
   - Mirror `create_mcp_source` at api.py:873-888 — `data = await request.json()`; `if "id" not in data: data["id"] = uuid.uuid4().hex[:12]`; `account = ConnectorAccount.model_validate(data)` (422 on `ValidationError`); `repo = await _connector_repo()`; `await repo.create(account)`; return `_connector_account_response(account)`.
   - **NO `_validate_mcp_source_config`-style call here** — leg-3 Design Decision defers per-type config validation to Flights 8 / 9.

10. **Route: `update_connector_account`** (`PUT /api/connector-accounts/{account_id}`)
    - Mirror `update_mcp_source` at api.py:891-966, MINUS:
      - The `_OAUTH_MANAGED_SECRET_KEYS` block at L927-942 (delete it).
      - The `_cache` preservation block at L944-958 (delete it).
      - The `_validate_mcp_source_config(updated)` call at L964 (delete it).
    - Add:
      - The eviction call AFTER `repo.update(updated)`:
        ```python
        if existing.secrets != resolved_secrets:
            # Warm pool entries cache plaintext credentials inside their
            # ConnectorClient. On any actual secrets change (including
            # operator dropping a key via REST replace), the entry must
            # be evicted so the next acquire reloads with the new
            # credentials. No-op PUT (all-masked round-trip) skips
            # eviction because resolved_secrets is byte-identical to
            # existing.secrets.
            from the_one.connectors._pool import _evict_all_for_account
            await _evict_all_for_account(account_id)
        ```
      - Note the `resolved_secrets` variable is the dict produced by the per-key `__MASKED__` resolution loop. Initialize it to `existing.secrets` if `data.get("secrets")` is None (operator didn't send a secrets key at all → no change → no eviction).
    - **No race-handling on PUT** — matches MCP precedent at `api.py:891-966`, which doesn't try/except the `repo.update(updated)` call. The connector PUT follows the same shape.
    - **`updated_at` is repository-managed** — `ConnectorAccountRepository.update()` writes `_now_iso()` server-side (per F2 L2 round-trip). PUT body should NOT set `updated_at`; if the operator includes it in `data`, `model_copy(update=data)` would overwrite the server value, but the repository then re-writes it. No special handling needed.
    - The full shape (skeleton):
      ```python
      @router.put("/connector-accounts/{account_id}")
      async def update_connector_account(account_id: str, request: Request) -> dict[str, Any]:
          data = await request.json()
          data["id"] = account_id
          repo = await _connector_repo()
          try:
              existing = await repo.get(account_id)
          except KeyError:
              raise HTTPException(status_code=404, detail=f"Connector account not found: {account_id}")

          # Per-key __MASKED__ resolution: verbatim mirror of api.py:910-926
          # minus the OAuth-managed-keys block (MCP-specific).
          # NOTE: resolved_secrets is initialized OUTSIDE the if-branch so
          # the post-update eviction check (`existing.secrets != resolved_secrets`)
          # works uniformly when the operator omits the `secrets` field entirely
          # (intent: "I only changed the name, don't touch credentials" → no
          # eviction). This is a deliberate divergence from the MCP precedent,
          # which scopes resolved_secrets inside the `is not None` branch.
          incoming_secrets = data.get("secrets")
          resolved_secrets: dict[str, Any] = existing.secrets
          if incoming_secrets is not None:
              if not isinstance(incoming_secrets, dict):
                  raise HTTPException(status_code=422, detail="secrets must be a dict.")
              resolved_secrets = {}
              for key, value in incoming_secrets.items():
                  if value == _MASKED_API_KEY_SENTINEL:
                      if key in existing.secrets:
                          resolved_secrets[key] = existing.secrets[key]
                  else:
                      resolved_secrets[key] = value
              data["secrets"] = resolved_secrets

          try:
              updated = existing.model_copy(update=data)
          except ValidationError as e:
              raise HTTPException(status_code=422, detail=e.errors(include_context=False))
          await repo.update(updated)

          if existing.secrets != resolved_secrets:
              from the_one.connectors._pool import _evict_all_for_account
              await _evict_all_for_account(account_id)

          return _connector_account_response(updated)
      ```
    - **NOTE**: The function-local import of `_evict_all_for_account` follows the `function-local-import-to-break-load-cycle` convention codified in F2 L1 — `interfaces/web/api.py` is a high-level module; importing `the_one.connectors._pool` at module top would extend the import surface unnecessarily.

11. **Route: `delete_connector_account`** (`DELETE /api/connector-accounts/{account_id}`)
    - Verify the account exists first (404 on miss), THEN evict, THEN delete:
      ```python
      @router.delete("/connector-accounts/{account_id}")
      async def delete_connector_account(account_id: str) -> dict[str, str]:
          """Delete a connector account and evict warm pool entries.

          Flight 2 leg 3: ships the delete handler against the F1 stub plugin
          baseline. Mirror of MCP delete shape minus the runtime-cache
          cleanup (connectors don't have a lazy-install cache to refcount).
          Future flight 4 (mission 10) adds `connector_account_ids` to
          `AgentConfig`; at that point this handler will gain a
          "no agent references this account" guard before the eviction
          step. Until then, delete is unconditional.
          """
          from the_one.connectors._pool import _evict_all_for_account
          repo = await _connector_repo()
          try:
              await repo.get(account_id)
          except KeyError:
              raise HTTPException(status_code=404, detail=f"Connector account not found: {account_id}")

          # Evict warm pool entries BEFORE the row delete so any
          # concurrent acquire-in-flight observes the deletion at the
          # repo layer rather than serving from a stale cache.
          await _evict_all_for_account(account_id)

          try:
              await repo.delete(account_id)
          except KeyError:
              # Race: another caller deleted between our get and delete.
              raise HTTPException(status_code=404, detail=f"Connector account not found: {account_id}")

          return {"status": "ok"}
      ```

12. **Tests in `tests/test_db_api.py`**
    - Add a new `class TestConnectorAccountAPI` AFTER `TestMCPSourceAPI`. Use the existing `async def client(...)` AsyncClient fixture (verified live at `tests/test_db_api.py:18-44` — function-scoped, isolated DB, encryption key seeded, `ensure_schema(conn)` runs at fixture setup).
    - **Test isolation MUST be explicit in this class.** The autouse `_clear_pool_after_each_test` fixture at `tests/test_connectors_pool.py:62-67` is module-local and does NOT propagate to `tests/test_db_api.py`. Add a class-scoped (or module-scoped) autouse fixture INSIDE `TestConnectorAccountAPI` that runs BEFORE each test:
      ```python
      @pytest.fixture(autouse=True)
      async def _isolation(self):
          # Reset connector pool + registry + stub class-level state between
          # tests so eviction-detection tests see a clean baseline. The
          # autouse fixture in tests/test_connectors_pool.py is module-local
          # and does NOT propagate here.
          from the_one.connectors import _pool as pool_mod
          from the_one.connectors.registry import (
              clear_for_test,
              register_for_test,
              restore_to_baseline_for_test,
          )
          from the_one.connectors._stub import StubPlugin

          await pool_mod._clear_for_test()
          restore_to_baseline_for_test()
          StubPlugin.reset_for_test()  # ClassVar lists/flags reset
          # Pre-register stub for tests that need it; tests that need an
          # empty-types response can call clear_for_test() inside the test
          # to invert.
          register_for_test("stub", StubPlugin)
          yield
          await pool_mod._clear_for_test()
          clear_for_test()
      ```
    - **`StubPlugin.reset_for_test()` is REQUIRED** — `StubPlugin.connect_calls`, `connect_should_fail`, `disconnect_calls`, etc. are class-level ClassVar state. Without resetting, prior-test state poisons later tests. Verified live at `connectors/_stub.py:62-105`.
    - **`test_types_returns_empty_in_production`** — this is the one test that needs `clear_for_test()` (no stub registered). The autouse fixture pre-registers the stub; this test calls `clear_for_test()` after entering, performs the assertion, and the autouse teardown handles the rest.
    - For the eviction tests (4-7, 12), the fixture sequence is:
      1. The autouse fixture has already registered the stub plugin.
      2. POST a stub-typed account.
      3. Acquire a warm pool entry: `from the_one.connectors._pool import acquire; client = await acquire("test-agent", account_id)`. The pool now has an entry keyed `("test-agent", account_id)`.
      4. Assert presence: `from the_one.connectors import _pool as pool_mod; assert ("test-agent", account_id) in pool_mod._pool`.
      5. Do the PUT or DELETE under test.
      6. Assert post-state: `assert ("test-agent", account_id) in pool_mod._pool` (no-op case) OR `assert ("test-agent", account_id) not in pool_mod._pool` (eviction case).
    - **`test_no_op_put_does_not_evict`** — after the no-op PUT, the key MUST still be in `_pool`.
    - **`test_dropping_a_key_evicts`**, **`test_secrets_change_evicts`**, **`test_adding_a_new_key_evicts`**, **`test_delete_evicts_then_deletes`** — after the operation, the key MUST be GONE.

13. **Run tests + lint**
    - `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py::TestConnectorAccountAPI` — all green.
    - `docker exec the-one pytest -x --timeout 30 tests/test_db_api.py` — full file green.
    - `make test` — full suite clean. Expected delta: +8 to +11 tests on the 1785 baseline.
    - `make lint` — clean.

14. **Update artifacts and flight log**
    - Set this leg's status to `landed`.
    - Append a "Leg Progress" entry summarizing: 6 routes, 2 helpers, 1 section header, 8-11 new tests, pass-count delta.
    - Check off this leg in `flight.md`.
    - Do NOT commit.

## Edge Cases

- **`registry.types()` is already exposed** — verified at design review: `the_one/connectors/registry.py:104` exports `types() -> tuple[str, ...]`. The leg does NOT modify `registry.py`. The Files Affected list correctly omits it.
- **Section placement** — line numbers cited above (L2070, L1622) are subject to drift since this file is the busiest in the project. Use the `# ── Name ────` section dividers as the anchor; the new section sits between MCP-related routes (everything from L623 forward) and Chat Sessions.
- **Test-isolation: pool state across tests** — verified live: `tests/test_connectors_pool.py:62-67`'s autouse fixture is module-local and does NOT propagate to `tests/test_db_api.py`. The leg's autouse fixture (Implementation step 12) is mandatory, not optional.
- **Stub registration in test fixtures** — `register_for_test("stub", StubPlugin)` is idempotent across tests (overwrites). The autouse fixture pre-registers it; `test_types_returns_empty_in_production` is the one test that inverts by calling `clear_for_test()` inside the test body.
- **StubPlugin class-level state** — `_stub.py:62-105` defines ClassVar lists (`connect_calls`, `disconnect_calls`, `doctor_calls`) and flags (`connect_should_fail`, `doctor_response`). The autouse fixture's `StubPlugin.reset_for_test()` call resets these. Without the reset, a prior test that set `connect_should_fail=Exception("nope")` poisons later acquires.
- **`test_dropping_a_key_evicts` semantics** — operator sends `secrets={"BOT_TOKEN": "real"}` initially, then PUT with `secrets={}` (empty dict). The per-key loop runs over an empty dict, so `resolved_secrets = {}`. `existing.secrets = {"BOT_TOKEN": "real"}` ≠ `{}`. Eviction fires. **Edge of this edge**: operator sends `secrets={"BOT_TOKEN": "__MASKED__", "OTHER_KEY": "newvalue"}` where `OTHER_KEY` is NEW (not in existing). `resolved_secrets = {"BOT_TOKEN": "real", "OTHER_KEY": "newvalue"}`. `existing.secrets = {"BOT_TOKEN": "real"}` ≠ resolved. Eviction fires (an actual change happened — adding a key). Add a 12th test `test_adding_a_new_key_evicts` to pin this case if you have appetite; the leg artifact lists 8 mandatory + 3 optional, and this would be optional 4.
- **`existing.secrets != resolved_secrets` dict equality** — Python `dict == dict` is order-independent, so dict-ordering after `__MASKED__` resolution is not a false-positive concern. Same key set + same values per key = equal. The leg artifact's flight Design Decisions document this explicitly; tests don't need to pin it.
- **PUT with `secrets` key OMITTED from JSON entirely** — `data.get("secrets")` returns `None`; the resolution loop is skipped; `resolved_secrets = existing.secrets`; `existing.secrets == resolved_secrets`; no eviction. This is the "operator changed only the name field" path. The 12th optional test could be `test_put_with_no_secrets_field_does_not_evict` if you want to pin it.
- **`AsyncClient` fixture location** — `tests/test_db_api.py` likely has an `async def client(...)` fixture or imports one from `tests/conftest.py`. Verify before writing tests; reuse the existing fixture to keep DB/encryption-key setup consistent.
- **Eviction call import path** — function-local import inside both `update_connector_account` and `delete_connector_account` per the convention. DO NOT add `from the_one.connectors._pool import _evict_all_for_account` at module top.
- **`model_dump` and the new `idle_timeout_seconds` field** — `ConnectorAccount.model_dump()` will include `idle_timeout_seconds` in the dict. `_connector_account_response` doesn't strip it; the GET response surfaces the field. Tests should verify it round-trips correctly (POST → GET → assert the value) as part of `test_crud_round_trip`.

## Files Affected

- `the_one/interfaces/web/api.py` — 2 import additions, 2 helpers, 1 section header, 6 routes (~250 LoC net).
- `tests/test_db_api.py` — new `TestConnectorAccountAPI` class with 12 tests (~250 LoC).
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — Leg Progress entry.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — leg-3 checkbox.

## State-Machine Reachability Audit

This leg adds REST routes but no new lifecycle states. The only state-shape change is:

- The warm pool entry keyed `(agent_name, account_id)` is now evictable via the REST PUT (on secrets change) and DELETE handlers. Before this leg, entries were evicted only by:
  - Idle TTL elapsing (the reaper, F1 L6)
  - `shutdown_drain` on FastAPI lifespan shutdown (F1 L6)
  - The `_evict_all_for_account` test seam (test code only)
- Post-leg-3, eviction is operator-driven via the REST surface. **No FK / CHECK / cache-invalidation surface is touched in the DB layer** — the eviction is in-memory only.

No test pins a behavior that this leg breaks. The MCP routes section is left untouched.

## Cache Freshness Contract

For warm pool entries' cached credentials (consumed inside `ConnectorClient` instances at acquire-time):

- **Source of truth**: `connector_accounts.secrets` for the account row.
- **Rebuild trigger**: explicit invalidation event — operator PUT with changed secrets OR DELETE — fires `_evict_all_for_account`. Idle-TTL eviction is the secondary trigger.
- **Maximum staleness acceptable to the operator**: zero. An operator updating secrets MUST see the new credentials honored on the next conversation turn, not after a 30-min idle wait.
- **User-action invalidation map**:
  - PUT with secrets change → eviction (this leg).
  - PUT with secrets no-op (all-masked round-trip) → no eviction (this leg) — correct: nothing changed.
  - PUT with no `secrets` field at all (e.g. operator renamed the account) → no eviction (this leg) — correct: nothing changed in the credentials.
  - PUT with `idle_timeout_seconds` change but no secrets change → no eviction (this leg). The new TTL applies on the next acquire after the warm entry naturally evicts. **Acceptable** per the F2 L2 flight-log "Decisions" entry; revisit at L3 design (this leg) — chose NOT to evict on TTL change, since the change semantics is "next conversation uses the new TTL," and the old TTL is bounded.
  - DELETE → eviction (this leg).
  - Encryption-key rotation → eviction (leg 4).

## Files Affected (re-stated)

See the explicit list above.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` passing (pass-count delta from 1785: +8 to +11 expected; report actual)
- [ ] `make lint` clean
- [ ] Flight log updated with a "Leg Progress" entry summarizing the routes, helpers, eviction wiring, and test deltas
- [ ] This leg's status updated to `landed` (in this file's header)
- [ ] This leg checked off in `flight.md` Legs list
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

10 code-location citations verified against current code at leg design time:

- `the_one/interfaces/web/api.py:23-33 — db.models + db.repositories imports` — **OK** (verified).
- `the_one/interfaces/web/api.py:58-61 — _mcp_repo helper` — **OK** (verified).
- `the_one/interfaces/web/api.py:626-712 — _mask_secret_value / _mask_secrets / _mcp_source_response / _OAUTH_MANAGED_SECRET_KEYS import` — **OK** (verified; OAuth-managed-keys import block at L660 with the placement comment).
- `the_one/interfaces/web/api.py:840-870 — list/types/get-by-id MCP routes` — **OK** (verified; registration-order comment at L851).
- `the_one/interfaces/web/api.py:873-888 — create_mcp_source` — **OK** (verified).
- `the_one/interfaces/web/api.py:891-966 — update_mcp_source with __MASKED__ + OAuth + cache blocks` — **OK** (verified; the per-key resolution at L910-926; the OAuth block at L927-942; the cache block at L944-958).
- `the_one/interfaces/web/api.py:969-1064 — delete_mcp_source with eviction-before-delete` — **OK** (verified; the eviction step at L1016).
- `the_one/interfaces/web/api.py:2157 — _MASKED_API_KEY_SENTINEL = "__MASKED__"` — **OK** (verified).
- `the_one/connectors/_pool.py:244-266 — _evict_all_for_account` — **OK** (verified; function exists from F1).
- `tests/test_db_api.py:197-... — TestMCPSourceAPI` — **OK** (verified; precedent for the new TestConnectorAccountAPI class).

0 citations drifted, 0 unverifiable.
