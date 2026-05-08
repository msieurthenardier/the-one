# Leg: 03-api-endpoint-extension

**Status**: completed
**Flight**: [Encrypted MCP Source Persistence + Settings Page](../flight.md)

## Objective

Extend the existing `/api/mcp-sources` REST endpoints with transport-aware field validation, per-key `__MASKED__` sentinel handling on PUT, per-decoded-value masking on GET responses, and add a `/api/mcp-sources/types` endpoint.

## Context

L2 wired field-segregated encryption through the model and repository. L3 surfaces that shape at the HTTP API:

- **Response shape**: GET responses now expose the storage split — `{config: {...plaintext...}, secrets: {key: "***...{tail4}", ...}}`. Sensitive values are masked at the per-decoded-VALUE level (after Fernet decryption inside the repository), NOT at the ciphertext or JSON-blob level. The masking semantic mirrors `_mask_api_key` at `api.py:667-672` — short values (≤4 chars) → `***`; longer values → `***...{tail4}`.
- **Per-key `__MASKED__` sentinel on PUT**: any `secrets[key] == "__MASKED__"` in the incoming body preserves the existing stored value for that key. Keys with non-sentinel values overwrite. Keys absent from the incoming `secrets` dict are dropped (replace, not merge — REST PUT convention). The provider precedent at `api.py:788-791` does this for a single `api_key` column; L3 generalizes to per-key handling inside a JSON dict.
- **Transport-aware validation**: per `MCPSource.type`, the `config` dict must contain the right shape — stdio: `command` (str, required), `args` (list[str], default `[]`), `cwd` (str, optional); streamable-http: `url` (str, required), `headers` (dict[str,str], default `{}`), OAuth client static config under `config.oauth = {issuer_url, client_id, scopes, redirect_uri}`. The OAuth `client_secret` and any sensitive headers go in `secrets`. Validation lives at the API endpoint layer (POST/PUT bodies); model validation is a thin Pydantic check; the cross-field transport-aware shape is API-level so it can return clean 422s.
- **`/api/mcp-sources/types` endpoint**: peer to `/api/providers/types`. Returns `[{value: 'stdio', label: 'Stdio'}, {value: 'streamable-http', label: 'Streamable HTTP'}]`. **Route registration order matters** — must be registered BEFORE `/api/mcp-sources/{source_id}` (the provider precedent at `api.py:721-725` documents this — FastAPI matches routes in registration order; `/types` would otherwise resolve to `get_mcp_source` with `source_id="types"`).

L3 does NOT touch the UI (that's L5/L6), does NOT touch the repository (that's L2), does NOT touch encryption rotation (that's L4). Pure REST surface work.

## Inputs

- L1 + L2 have landed
- `the_one/interfaces/web/api.py` — current `/api/mcp-sources` endpoints (list, get, post, put, delete) at lines 482–534. Anchor by symbol name: `list_mcp_sources`, `get_mcp_source`, `create_mcp_source`, `update_mcp_source`, `delete_mcp_source`. (Implementer: regrep before edits — do NOT trust historical line numbers.)
- `the_one/interfaces/web/api.py` — `/api/providers/types` endpoint precedent. Anchor by symbol: `list_provider_types`. The route-ordering comment lives in that function's docstring.
- `the_one/interfaces/web/api.py` — `_MASKED_API_KEY_SENTINEL = "__MASKED__"` (existing constant — reuse, do NOT redeclare). Anchor by name.
- `the_one/interfaces/web/api.py` — `_mask_api_key` masking function precedent. Anchor by name.
- `the_one/interfaces/web/api.py` — `_provider_response` precedent for shaping a Pydantic model into a masked dict. Anchor by name.
- `the_one/interfaces/web/api.py` — `update_provider` precedent for `__MASKED__` sentinel handling + `model_copy(update=data)` pattern. Anchor by name.
- `the_one/interfaces/web/api.py` — `include_context=False` ValidationError-encoding pattern (documented in CLAUDE.md "JSON-encoding of `ValidationError.errors()`"). Anchor by phrase grep.
- `the_one/db/models.py::MCPSource` — model with `config`, `secrets`, `merged_config()` (post-L2 shape).
- `tests/test_db_api.py::TestMCPSourceAPI` — class header at line 197; existing single `test_crud` at lines 198–217. (Implementer: confirm by `grep -n "TestMCPSourceAPI\|async def test_crud" tests/test_db_api.py` before extending.)

## Outputs

- `the_one/interfaces/web/api.py` updates:
  - New `/api/mcp-sources/types` endpoint (registered BEFORE the `{source_id}` routes)
  - New helper `_mask_secrets(secrets: dict)` mirroring `_mask_api_key` shape but per-key
  - New helper `_mcp_source_response(source: MCPSource)` mirroring `_provider_response` shape
  - New helper `_validate_mcp_source_config(source: MCPSource)` for transport-aware validation
  - `list_mcp_sources` returns the masked response shape
  - `get_mcp_source` returns the masked response shape
  - `create_mcp_source` validates transport-aware fields
  - `update_mcp_source` honors per-key `__MASKED__` inside `secrets`, validates transport-aware fields, returns the masked shape
- `tests/test_db_api.py` updates:
  - Extend `TestMCPSourceAPI` with per-field masking shape tests, per-key `__MASKED__` round-trip, transport-aware validation rejection cases, types endpoint shape

## Acceptance Criteria

- [ ] `GET /api/mcp-sources` returns a list of `{id, name, type, config, secrets, created_at, updated_at}` where every value in `secrets` is masked per-decoded-value (`***...{tail4}` for >4-char values, `***` for ≤4-char values)
- [ ] `GET /api/mcp-sources/{id}` returns the same masked shape for a single source
- [ ] `POST /api/mcp-sources` accepts a body with `config` and `secrets` dicts and validates transport-aware fields per `type`:
  - For `type='stdio'`: `config.command` is a non-empty string (required); `config.args` is `list[str]` (optional, default `[]`); `config.cwd` is a string if present
  - For `type='streamable-http'`: `config.url` is a non-empty string (required); `config.headers` is `dict[str, str]` (optional, default `{}`); `config.oauth` if present is `{issuer_url: str, client_id: str, scopes: list[str], redirect_uri: str}` (any of those required if `oauth` is present)
  - Validation failures return 422 with a clear `detail` message naming the missing/invalid field
- [ ] `PUT /api/mcp-sources/{id}`:
  - Honors per-key `__MASKED__` inside `secrets`: any `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; non-sentinel values overwrite; keys absent from the incoming `secrets` are dropped (REST PUT replace semantic, applied per-key — operator-controlled drop is the explicit "I want this key gone")
  - Re-validates transport-aware fields on the merged result
  - Returns the masked response shape
- [ ] `GET /api/mcp-sources/types` returns `[{value: 'stdio', label: 'Stdio'}, {value: 'streamable-http', label: 'Streamable HTTP'}]`
- [ ] `/api/mcp-sources/types` is registered BEFORE `/api/mcp-sources/{source_id}` in route definition order (verified by inspecting the source file — FastAPI matches in declaration order)
- [ ] Per-decoded-value masking is implemented at the API layer (NOT the repository layer) — the repository continues to return the decrypted plaintext dict; the API layer's response helper is the only place that applies masking
- [ ] No `secrets` plaintext value appears in any GET response — verified by a test that creates a source with a known secret value and asserts the value's substring does not appear anywhere in the JSON response body
- [ ] All existing `TestMCPSourceAPI::test_crud` assertions still pass (the test uses `type='stdio'` and reads `config.command` which remains accessible in the new shape)
- [ ] New `TestMCPSourceAPI` tests added (10 total): per-field masking shape on list/get, per-key `__MASKED__` round-trip preserves stored secrets across edit, PUT with empty secrets dict drops keys, transport-aware validation rejection (stdio missing command → 422, streamable-http missing url → 422, unknown type → 422), types endpoint two-transport shape, types endpoint route-ordering anti-collision, PUT transport-type switch with stale config → 422
- [ ] Full unit suite passes: `pytest tests/ --tb=short -q --timeout=60` — 0 failures

## Verification Steps

- `pytest tests/test_db_api.py::TestMCPSourceAPI -v` — all original + new tests green
- `pytest tests/ --tb=short -q --timeout=60` — full suite green (1084+ from L2 + new L3 tests)
- Manual: create a stdio source with `secrets={"GITHUB_TOKEN": "ghp_realsecretvalue"}` via POST; GET that source by ID; assert response `secrets.GITHUB_TOKEN == "***...alue"`; assert no occurrence of `"ghp_realsecretvalue"` anywhere in the response body
- Manual: PUT that same source with `secrets={"GITHUB_TOKEN": "__MASKED__"}` and a changed `name`; the stored secret value remains `"ghp_realsecretvalue"` on subsequent GET; the name change applies
- Manual: PUT with `secrets={}` drops `GITHUB_TOKEN` from the stored secrets — confirms the per-key replace semantic
- Manual: POST with `type='stdio'` and missing `command` returns 422 with detail naming the missing field
- Manual: GET `/api/mcp-sources/types` returns the two-entry list

## Implementation Guidance

1. **Add the route ordering note as a code comment**: before adding any new routes to `the_one/interfaces/web/api.py`, locate the existing MCP block (anchor: `list_mcp_sources` through `delete_mcp_source`). The new `/api/mcp-sources/types` endpoint MUST be inserted between `list_mcp_sources` and `get_mcp_source`. Mirror the route-ordering comment in `list_provider_types`'s docstring to document the invariant. Implementer: `grep -n "@router\.\(get\|post\|put\|delete\).*mcp-sources" the_one/interfaces/web/api.py` to find current line positions.

2. **Add helpers near the existing MCP block** (above `list_mcp_sources`):

   ```python
   def _mask_secret_value(value: Any) -> Any:
       """Mask a single secret value mirroring `_mask_api_key`'s shape.

       Type signature is `Any -> Any` (not `str -> str`) because the
       secrets dict is `dict[str, Any]` per L2's MCPSource model — a
       client could in principle send a non-string value, and we want
       to mask it defensively rather than crash. Empty/None passes
       through unchanged; ≤4-char string values mask as `***`; longer
       string values mask as `***...{tail4}`; non-string values mask
       wholesale as `***` (no leakage of nested structure). Same
       per-decoded-value semantic as `_mask_api_key`, kept separate so
       future MCP-secret shape changes don't drift LLM-provider behavior.
       """
       if not value:
           return value
       if not isinstance(value, str):
           # Non-string secret values (e.g., a nested dict for OAuth tokens
           # in F5) — mask wholesale to avoid leaking nested structure.
           # F5 will revisit this when access/refresh tokens land.
           return "***"
       if len(value) <= 4:
           return "***"
       return f"***...{value[-4:]}"


   def _mask_secrets(secrets: dict[str, Any]) -> dict[str, Any]:
       """Apply per-key masking to a decoded secrets dict.

       Iterates the dict; replaces each value with its masked form via
       `_mask_secret_value`. Returns a NEW dict — does not mutate the
       input. Used by `_mcp_source_response` to produce the masked GET
       response shape.
       """
       return {k: _mask_secret_value(v) for k, v in secrets.items()}


   def _mcp_source_response(source: MCPSource) -> dict[str, Any]:
       """Render an MCPSource into the masked HTTP response shape.

       Mirrors `_provider_response` — the response contains masked
       secret values per `_mask_secrets`; `config` is passed through
       unchanged (operator-marked-non-sensitive).

       INVARIANT: `model_dump()` populates `data["secrets"]` with the
       decrypted plaintext dict; we OVERWRITE that key with the masked
       form before returning. Any future refactor that removes the
       overwrite would leak plaintext via the API. The
       `test_list_returns_masked_secrets` assertion `"ghp_realsecretvalue"
       not in resp.text` is the regression net.
       """
       data = source.model_dump()
       data["secrets"] = _mask_secrets(source.secrets)
       return data
   ```

3. **Add transport-aware validation helper** in the same area:

   ```python
   def _validate_mcp_source_config(source: MCPSource) -> None:
       """Transport-aware shape validation for MCPSource.config.

       Raises HTTPException(422, detail=...) on shape mismatch. Validation
       lives at the API layer so the error path returns a clean 422 with a
       human-readable detail string; Pydantic's literal validation already
       gates the `type` field at model validation time.

       Stdio: config.command is required (non-empty string); config.args
         must be a list[str] if present; config.cwd must be a string if
         present.
       Streamable-HTTP: config.url is required (non-empty string);
         config.headers must be a dict[str, str] if present; config.oauth
         if present must include {issuer_url, client_id, scopes (list),
         redirect_uri} as strings (oauth.scopes is a list[str]).
       """
       cfg = source.config

       if source.type == "stdio":
           command = cfg.get("command")
           if not isinstance(command, str) or not command.strip():
               raise HTTPException(
                   status_code=422,
                   detail="MCP source of type 'stdio' requires config.command (non-empty string).",
               )
           args = cfg.get("args", [])
           if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
               raise HTTPException(
                   status_code=422,
                   detail="MCP source config.args must be a list of strings.",
               )
           cwd = cfg.get("cwd")
           if cwd is not None and not isinstance(cwd, str):
               raise HTTPException(
                   status_code=422,
                   detail="MCP source config.cwd must be a string if present.",
               )

       elif source.type == "streamable-http":
           url = cfg.get("url")
           if not isinstance(url, str) or not url.strip():
               raise HTTPException(
                   status_code=422,
                   detail="MCP source of type 'streamable-http' requires config.url (non-empty string).",
               )
           headers = cfg.get("headers", {})
           if not isinstance(headers, dict) or not all(
               isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
           ):
               raise HTTPException(
                   status_code=422,
                   detail="MCP source config.headers must be a dict of string-to-string.",
               )
           oauth = cfg.get("oauth")
           if oauth is not None:
               if not isinstance(oauth, dict):
                   raise HTTPException(
                       status_code=422,
                       detail="MCP source config.oauth must be a dict if present.",
                   )
               for key in ("issuer_url", "client_id", "redirect_uri"):
                   if key in oauth and not isinstance(oauth[key], str):
                       raise HTTPException(
                           status_code=422,
                           detail=f"MCP source config.oauth.{key} must be a string.",
                       )
               if "scopes" in oauth:
                   scopes = oauth["scopes"]
                   if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
                       raise HTTPException(
                           status_code=422,
                           detail="MCP source config.oauth.scopes must be a list of strings.",
                       )

       else:
           # Defensive exhaustiveness — Pydantic's Literal validator
           # already rejects unknown types at MCPSource.model_validate
           # time, so this branch is unreachable for properly-validated
           # input. But if a future contributor adds a new transport
           # literal to the model and forgets to extend this helper,
           # that omission would silently permit any config shape. This
           # raise locks the contract: a new transport must add a
           # validation block here, or this raise fires.
           raise HTTPException(
               status_code=422,
               detail=f"Unsupported MCP source type: {source.type}",
           )
   ```

4. **Insert the `/types` endpoint** between `list_mcp_sources` and `get_mcp_source`:

   ```python
   @router.get("/mcp-sources/types")
   async def list_mcp_source_types() -> list[dict[str, str]]:
       """Return the list of MCP source transport types selectable in the UI.

       NOTE: This route MUST be registered BEFORE ``/mcp-sources/{source_id}``
       because FastAPI matches routes in registration order. If reordered, a
       GET to ``/mcp-sources/types`` would resolve to ``get_mcp_source`` with
       ``source_id="types"`` and 404. Mirrors the provider precedent at
       api.py:716-735.
       """
       return [
           {"value": "stdio", "label": "Stdio"},
           {"value": "streamable-http", "label": "Streamable HTTP"},
       ]
   ```

5. **Update `list_mcp_sources`** to use the response helper:

   ```python
   @router.get("/mcp-sources")
   async def list_mcp_sources() -> list[dict[str, Any]]:
       repo = await _mcp_repo()
       sources = await repo.list()
       return [_mcp_source_response(s) for s in sources]
   ```

6. **Update `get_mcp_source`** to use the response helper:

   ```python
   @router.get("/mcp-sources/{source_id}")
   async def get_mcp_source(source_id: str) -> dict[str, Any]:
       repo = await _mcp_repo()
       try:
           source = await repo.get(source_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")
       return _mcp_source_response(source)
   ```

7. **Update `create_mcp_source`** to validate transport-aware fields:

   ```python
   @router.post("/mcp-sources", status_code=201)
   async def create_mcp_source(request: Request) -> dict[str, Any]:
       data = await request.json()
       if "id" not in data:
           data["id"] = uuid.uuid4().hex[:12]
       try:
           source = MCPSource.model_validate(data)
       except ValidationError as e:
           raise HTTPException(status_code=422, detail=e.errors(include_context=False))
       _validate_mcp_source_config(source)
       repo = await _mcp_repo()
       await repo.create(source)
       return _mcp_source_response(source)
   ```

   Note: explicit `try/except ValidationError` is needed so the JSON-encoding fix at `api.py:236-247` (the `include_context=False` pattern) applies — `model_validator` paths populate `ctx['error']` with raw exceptions that aren't JSON-serializable. This is the canonical pattern documented in `CLAUDE.md` "JSON-encoding of `ValidationError.errors()`".

8. **Update `update_mcp_source`** with per-key `__MASKED__` handling and transport-aware validation. Per-key sentinel handling differs from the provider's single-`api_key` approach because the secrets dict has multiple operator-marked keys:

   ```python
   @router.put("/mcp-sources/{source_id}")
   async def update_mcp_source(source_id: str, request: Request) -> dict[str, Any]:
       data = await request.json()
       data["id"] = source_id
       repo = await _mcp_repo()
       try:
           existing = await repo.get(source_id)
       except KeyError:
           raise HTTPException(status_code=404, detail=f"MCP source not found: {source_id}")

       # Per-key __MASKED__ handling inside the secrets dict — a sentinel
       # value preserves the corresponding existing stored value; non-sentinel
       # values overwrite. Keys absent from the incoming secrets dict are
       # dropped (REST PUT replace semantic, applied per-key — operator
       # explicitly drops a secret by omitting its key).
       incoming_secrets = data.get("secrets")
       if incoming_secrets is not None:
           if not isinstance(incoming_secrets, dict):
               raise HTTPException(
                   status_code=422,
                   detail="secrets must be a dict.",
               )
           resolved_secrets = {}
           for key, value in incoming_secrets.items():
               if value == _MASKED_API_KEY_SENTINEL:
                   if key in existing.secrets:
                       resolved_secrets[key] = existing.secrets[key]
                   # else: client sent __MASKED__ for a key we don't have;
                   # drop it silently — same as if the client had omitted
                   # the key entirely.
               else:
                   resolved_secrets[key] = value
           data["secrets"] = resolved_secrets

       try:
           updated = existing.model_copy(update=data)
       except ValidationError as e:
           raise HTTPException(status_code=422, detail=e.errors(include_context=False))
       _validate_mcp_source_config(updated)
       await repo.update(updated)
       return _mcp_source_response(updated)
   ```

9. **Verify the route ordering** by visual inspection of the source file: `list_mcp_sources` → `list_mcp_source_types` → `get_mcp_source` → `create_mcp_source` → `update_mcp_source` → `delete_mcp_source`. The `types` endpoint MUST come after the bare-list route and BEFORE the `{source_id}` route. Run `pytest tests/test_db_api.py -v` to confirm; a route-ordering bug surfaces as a 404 on `/mcp-sources/types` with an unexpected `MCP source not found: types` payload.

10. **Extend `tests/test_db_api.py::TestMCPSourceAPI`** with new test methods:

    ```python
    async def test_list_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/mcp-sources masks secret values per-key."""
        await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "github-mcp"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        resp = await client.get("/api/mcp-sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # per-decoded-value mask: ***...{tail4} for long values
        assert data[0]["secrets"]["GITHUB_TOKEN"] == "***...alue"
        # plaintext config passes through unchanged
        assert data[0]["config"]["command"] == "github-mcp"
        # raw plaintext does not appear anywhere in the response
        assert "ghp_realsecretvalue" not in resp.text

    async def test_get_returns_masked_secrets(self, client: AsyncClient) -> None:
        """GET /api/mcp-sources/{id} masks secret values per-key."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"K": "abc"},  # short value: masks as ***
            },
        )
        sid = create.json()["id"]
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.status_code == 200
        assert resp.json()["secrets"]["K"] == "***"
        # Mirror the plaintext-not-in-response assertion from the list test
        assert "abc" not in resp.json()["secrets"]["K"]

    async def test_put_masked_sentinel_preserves_secret(self, client: AsyncClient) -> None:
        """PUT with secrets[key]='__MASKED__' preserves the stored value."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        sid = create.json()["id"]
        await client.put(
            f"/api/mcp-sources/{sid}",
            json={
                "name": "GH-renamed",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "__MASKED__"},
            },
        )
        # The masked tail (***...alue) confirms the stored ciphertext still
        # decrypts to the original "ghp_realsecretvalue" — preservation
        # round-trip locked without needing a back-channel into the repo.
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.json()["secrets"]["GITHUB_TOKEN"] == "***...alue"
        assert resp.json()["name"] == "GH-renamed"
        # Belt-and-braces: raw plaintext does not appear in the response
        assert "ghp_realsecretvalue" not in resp.text

    async def test_put_drops_omitted_secret_key(self, client: AsyncClient) -> None:
        """PUT with secrets={} drops all stored secret keys (REST replace)."""
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {"GITHUB_TOKEN": "ghp_realsecretvalue"},
            },
        )
        sid = create.json()["id"]
        await client.put(
            f"/api/mcp-sources/{sid}",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {},
            },
        )
        resp = await client.get(f"/api/mcp-sources/{sid}")
        assert resp.json()["secrets"] == {}

    async def test_validation_rejects_stdio_missing_command(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "stdio", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422
        assert "config.command" in resp.json()["detail"]

    async def test_validation_rejects_streamable_http_missing_url(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "streamable-http", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422
        assert "config.url" in resp.json()["detail"]

    async def test_validation_rejects_unknown_transport_type(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/mcp-sources",
            json={"name": "X", "type": "websocket", "config": {}, "secrets": {}},
        )
        assert resp.status_code == 422  # Pydantic Literal rejection

    async def test_types_endpoint_returns_two_transports(self, client: AsyncClient) -> None:
        resp = await client.get("/api/mcp-sources/types")
        assert resp.status_code == 200
        data = resp.json()
        assert {entry["value"] for entry in data} == {"stdio", "streamable-http"}
        assert all("label" in entry for entry in data)

    async def test_types_endpoint_route_order_does_not_collide_with_get_by_id(
        self, client: AsyncClient
    ) -> None:
        """Locks the route ordering invariant.

        If `/types` were registered AFTER `/{source_id}`, a GET to /types
        would resolve to get_mcp_source(source_id='types') and return 404.
        This test ensures the ordering stays correct.
        """
        resp = await client.get("/api/mcp-sources/types")
        assert resp.status_code == 200
        # If the order regresses we'd get 404 with the get_mcp_source
        # detail format
        assert "MCP source not found" not in resp.text

    async def test_put_transport_type_switch_revalidates_config(
        self, client: AsyncClient
    ) -> None:
        """Switching type=stdio→streamable-http with stale config 422s.

        A PUT that flips the transport literal but keeps the old config
        shape (e.g., command-only) must be rejected at the validation
        helper because the merged result lacks the new transport's
        required fields. Locks that the helper runs on the merged
        post-copy state, not just the request body, and that operators
        get a clear 422 instead of a half-migrated source.
        """
        create = await client.post(
            "/api/mcp-sources",
            json={
                "name": "GH",
                "type": "stdio",
                "config": {"command": "x"},
                "secrets": {},
            },
        )
        sid = create.json()["id"]
        resp = await client.put(
            f"/api/mcp-sources/{sid}",
            json={"type": "streamable-http"},  # config still has only command
        )
        assert resp.status_code == 422
        assert "config.url" in resp.json()["detail"]
    ```

11. **Update the existing `test_crud`** at lines 198–217 (regrep the line numbers before editing — `grep -n "async def test_crud" tests/test_db_api.py`). The test asserts `resp.json()["config"]["command"] == "python"` — this still works post-L3 because `config` passes through unchanged. Add a 1–2-line baseline assertion for the new `secrets` shape, e.g. `assert resp.json()["secrets"] == {}` after the GET, so the post-L3 default-empty-secrets contract is locked. The PUT body `{"name": "Updated"}` continues to work because the existing `type='stdio'` and `config={"command": "python"}` survive the merge and pass `_validate_mcp_source_config`.

12. **Run the test suite**:

    ```
    pytest tests/test_db_api.py::TestMCPSourceAPI -v
    pytest tests/ --tb=short -q --timeout=60
    ```

    Expected: full green. The new tests bring the count to ~1093+.

13. **Update the flight log** at `flight-log.md` with `### 03-api-endpoint-extension` entry: status `landed`, started/completed timestamps, "Changes Made" listing the api.py + test_db_api.py edits, "Notes" entry confirming route ordering invariant is locked.

14. **Set leg status to `landed`** in this leg's frontmatter.

15. **Do NOT commit**. Per agentic-workflow protocol commit happens at flight end.

16. **Signal `[HANDOFF:review-needed]`** when complete.

## Edge Cases

- **Empty secrets dict on POST**: `secrets={}` is valid — encrypts as `Fernet.encrypt(b"{}")` per L2's contract. The masking helper returns `{}` unchanged. No special handling needed.
- **Nested non-string values in secrets**: `_mask_secret_value` returns `***` for non-string values. Documented inline. F5 will revisit when access/refresh tokens land (those are token strings, so the existing string mask applies).
- **Unicode tail in masked values**: `value[-4:]` on a Unicode string slices by code point — for typical secrets (ASCII tokens) this is fine; for emoji-laden strings the tail might not render correctly. Acceptable — secrets are operationally ASCII.
- **PUT without `secrets` key in body**: the `incoming_secrets is not None` guard skips the per-key processing; `model_copy(update=data)` then leaves the stored secrets unchanged (the existing repo's `existing.secrets` is preserved through the copy because `data` doesn't include the key). Documented inline.
- **PUT with secrets containing only `__MASKED__` values**: every key resolves to its existing stored value; no overwrite happens. The result is equivalent to omitting `secrets` from the PUT body. Documented as "no-op preserve" in the test cases.
- **PUT with secrets containing a `__MASKED__` value for a key that doesn't exist in stored secrets**: silently drop that key (matches the "client sent __MASKED__ for an unknown key" comment in the implementation). The test doesn't exercise this case — it's a defensive branch. Rationale: the UI is the only legitimate emitter of `__MASKED__`, and it only does so for keys it just rendered from a GET — meaning the key existed at GET time. A non-existent key with `__MASKED__` indicates either a UI bug or a concurrent delete; silent drop is the forgiving optimistic-concurrency choice. Re-evaluate if F5/F6 surface a complaint.
- **PUT with non-string secret values** (e.g., `secrets = {"K": ["__MASKED__"]}` or nested dict): the per-key sentinel comparison `value == _MASKED_API_KEY_SENTINEL` returns False for non-strings, so the value is stored as-is. The masking helper later returns `***` for any non-string value (no leakage). Trade-off: the operator who sent a list/dict has no signal that "preserve the existing value" was misinterpreted as "overwrite with this list". Acceptable for L3 because no current caller emits non-string secret values; F5 OAuth-token work will revisit if nested token blobs land in `secrets`.
- **PUT that switches transport type with stale config**: a PUT body of `{"type": "streamable-http"}` against a stdio source with `config={"command": "x"}` is rejected with 422 because the merged result lacks `config.url`. Locked by `test_put_transport_type_switch_revalidates_config`. The helper runs on the merged-post-`model_copy` state, not on the request body alone — that's what makes the cross-field re-validation correct.
- **Unknown `type` literal**: Pydantic `Literal` rejects at `model_validate` time with a ValidationError; the endpoint returns 422 via the existing exception handler. Test `test_validation_rejects_unknown_transport_type` locks this. The `_validate_mcp_source_config` helper also has a defensive `else: raise` for the unreachable case where the model literal expands without the helper being updated — see Step 3.

## Files Affected

- `the_one/interfaces/web/api.py` — new `/api/mcp-sources/types` endpoint, new `_mask_secret_value`/`_mask_secrets`/`_mcp_source_response`/`_validate_mcp_source_config` helpers, updated list/get/post/put endpoints
- `tests/test_db_api.py` — extended `TestMCPSourceAPI` with masking shape, sentinel round-trip, validation rejection, types endpoint, route-ordering tests

## State-Machine Reachability Audit

States introduced or affected:
- HTTP response shape: GET response now includes `secrets` key (was absent pre-L3; the underlying field existed on the model post-L2 but the CRUD endpoints used `model_dump()` which included the plaintext secrets in responses — L3 is the first time the API explicitly masks them). Any consumer reading `data["secrets"]["KEY"]` post-L3 sees a masked string. The only known consumer is the L5/L6 Studio MCPs surface (not yet built); the existing `studio.js` `fetchMcpSources` call sites (multiple, including a `Promise.all(...)` block) only read `.id` and similar plaintext fields per a render-path grep. Implementer must re-verify with `grep -n "fetchMcpSources\|mcpSources\|mcp_sources" the_one/interfaces/web/static/js/areas/studio.js` to confirm no consumer dereferences `.secrets.<key>` (none expected — the rendered grid only shows plaintext metadata). No regression.
- HTTP request body: POST/PUT now require transport-aware shape inside `config`. The existing `test_crud` at `tests/test_db_api.py` (class `TestMCPSourceAPI` at line 197, body 198–217) sends `type='stdio'` with `config={"command": "python"}` — passes the new validation. The PUT body `{"name": "Updated"}` (line 211 in current code) merges into the existing `type='stdio'` + `config={"command": "python"}`, which passes `_validate_mcp_source_config`. No external consumers exist pre-L3.
- `__MASKED__` sentinel value space: previously meaningful only for `llm_providers.api_key`; L3 extends to per-key inside `mcp_sources.secrets`. Both surfaces use the same constant `_MASKED_API_KEY_SENTINEL = "__MASKED__"` — name is now slightly misleading (it's not just for API keys). Renaming is out of scope for L3 — that's a cosmetic refactor. Documented inline as a note.

Tests that pin pre-L3 state and would contradict L3:
- `test_crud` at `tests/test_db_api.py` (line 198+) `assert resp.json()["config"]["command"] == "python"` (around line 208) — still passes post-L3 (config passes through unchanged). The new `secrets == {}` baseline addition (Step 11) extends the assertion set without breaking it.

No FK behaviors to audit. No application caches in L3 (response helpers are stateless).

## Cache Freshness Contract

- L3 introduces no caches. The response helpers run per-request and read fresh from the repository each call.

## Citation Audit

Citations re-verified against the current codebase post-design-review. Line numbers refresh per a regrep run at design time; the implementer should re-grep before edits because the `api.py` block is large and prior leg landings may have shifted lines.

Cited references (anchor-by-symbol when possible — line numbers are advisory):
- `the_one/interfaces/web/api.py` `/api/mcp-sources` endpoints (block at lines 482–534) — anchors: `list_mcp_sources` (~485), `get_mcp_source` (~492), `create_mcp_source` (~502), `update_mcp_source` (~513), `delete_mcp_source` (~525). Re-verified.
- `the_one/interfaces/web/api.py::list_provider_types` — `/api/providers/types` precedent including the route-ordering docstring comment. Re-verified.
- `the_one/interfaces/web/api.py::_MASKED_API_KEY_SENTINEL` constant — single source of truth, do NOT redeclare. Re-verified.
- `the_one/interfaces/web/api.py::_mask_api_key` — masking-shape precedent. Re-verified.
- `the_one/interfaces/web/api.py::_provider_response` — masked-response-shape precedent. Re-verified.
- `the_one/interfaces/web/api.py::update_provider` — `__MASKED__` + `model_copy(update=data)` pattern. Re-verified.
- `the_one/interfaces/web/api.py` ValidationError JSON-encoding pattern — grep `include_context=False` to locate. Re-verified.
- `the_one/db/models.py::MCPSource` post-L2 shape (`type: Literal["stdio","streamable-http"]`, `config: dict[str, Any]`, `secrets: dict[str, Any]`, `merged_config()`). Re-verified.
- `tests/test_db_api.py::TestMCPSourceAPI` — class header at line 197; `test_crud` body at lines 198–217 (PUT body at line 211; config-command assertion at line 208). Re-verified post-design-review (earlier leg drafts cited 188–209, which was stale).
- `the_one/interfaces/web/static/js/areas/studio.js` — `fetchMcpSources` invoked at multiple call sites (verified via grep; original draft only cited line 266, but the design review surfaced an additional `Promise.all(...)` call site around line 354). Render-path consumer reads only plaintext metadata fields — no `.secrets.<key>` deref. Implementer to re-grep at edit time.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] `pytest tests/test_db_api.py::TestMCPSourceAPI -v` green (existing test_crud + 10 new tests)
- [x] `pytest tests/ --tb=short -q --timeout=60` green
- [x] Manual: `grep -n "MCPSource\|mcp-sources" the_one/interfaces/web/api.py` confirms route order (`list` → `types` → `get_by_id` → `create` → `update` → `delete`)
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed` (frontmatter line 3)
- [ ] Do NOT check off this leg in flight.md (commit at flight end)
- [ ] Do NOT commit
