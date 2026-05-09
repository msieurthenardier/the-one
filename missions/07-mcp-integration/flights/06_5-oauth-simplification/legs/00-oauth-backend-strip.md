# Leg: 00-oauth-backend-strip

**Status**: landed
**Flight**: [OAuth simplification + Test connection button](../flight.md)

## Objective

Delete every backend code path that supported the GitHub-legacy non-DCR OAuth manual-entry flow, leaving F5's RFC 7591 DCR happy path as the only OAuth surface in the Python layer.

## Context

F5 added a `ManualOAuthClientProvider` and the `dcr_credentials.registration_method == "manual"` branch to support GitHub's pre-2014 OAuth shape (no RFC 7591 DCR). F6's debrief addendum 2 §3 identifies this surface as dead-letter for the spec-compliant happy path; the only modern OAuth-protected MCP servers under consideration (Cloudflare API MCP and the like) implement DCR. F6.5's flight artifact (Design Decisions §1, §7, §8) commits to ripping the manual surface out everywhere.

This leg is the backend half. L1 (frontend strip) lands in lockstep with this leg's deliverables — both must merge before the codebase is consistent. The two legs are split only because the file scopes don't overlap (L0 = `*.py` + `agents.md`, L1 = `*.js` + browser tests).

Key learnings from prior legs (flight log Phase 1b recon):

- Architect cycle-1 added 4 items the initial recon missed — `_validate_mcp_source_config`'s `config.oauth.*` validator block (`api.py:680-699`), the `registration_method` writer at `storage.py:147-156`, the masking-contract test file scope-error in `test_oauth_secrets_api.py` (REWRITE — do NOT delete), and the `build_oauth_provider_for_source` signature extension scope (deferred to L3, not relevant here). All four are folded into this leg's scope.
- F1↔F5 storage-shape mismatch: `mcp-server-editor.js` (F1) writes `config.oauth.{issuer_url, client_id, redirect_uri, scopes}` and `secrets.oauth_client_secret`; `provider_factory.py` (F5) reads `secrets["dcr_credentials"]` only. Zero overlap. The L0 deletion + L1 deletion close the mismatch by removing the F1 producer surface entirely.

## Inputs

What exists before this leg runs:

- Branch `flight/6_5-oauth-simplification` at HEAD `c375979` (the flight-spec commit; flight 6 already merged into the branch's history)
- `the_one/mcp/oauth/manual_metadata.py` — 220-line module containing `ManualOAuthMetadata` dataclass + `ManualOAuthClientProvider` class
- `the_one/mcp/oauth/provider_factory.py` with the `dcr.get("registration_method") == "manual"` branch at line 115
- `the_one/mcp/oauth/storage.py` writing `registration_method` on `set_client_info` at lines 147-156, and stripping it on `get_client_info` at line 123
- `the_one/mcp/oauth/__init__.py` re-exporting `ManualOAuthClientProvider` + `ManualOAuthMetadata`
- `the_one/interfaces/web/api.py:959-1006` — `/oauth/manual-register` endpoint
- `the_one/interfaces/web/api.py:680-699` — `_validate_mcp_source_config`'s `config.oauth.*` validator block
- `the_one/interfaces/web/api.py:576-578` — docstring lines describing the `config.oauth.*` shape
- `the_one/interfaces/web/api.py:1063-1067` — `oauth_start`'s precondition error referencing "manual registration"
- Five docstring locations referencing `ManualOAuthClientProvider`: `client.py:139`, `streamable_http.py:83`, `streamable_http.py:102`, `streamable_http.py:177`, plus the broader docstrings inside `provider_factory.py` (lines 1, 8-10, 12-13, 73-77) and `storage.py` (lines 10, 113-115, 137-143)
- `tests/test_oauth_manual_metadata.py` — 220-LOC test suite for `ManualOAuthClientProvider`
- `tests/test_oauth_manual_register_endpoint.py` — 104-LOC test suite for `/api/oauth/manual-register`
- `tests/test_oauth_secrets_api.py` — masking-contract test suite. 14 references to `oauth_client_secret`; the contracts (mask-on-GET, preserve-on-PUT-with-`__MASKED__`-sentinel) are F1 production semantics that survive F6.5 — only the field name changes.
- `tests/test_oauth_storage.py:152` — assertion `assert ...["registration_method"] == "dcr"`
- `tests/test_oauth_provider_factory.py` — manual-branch tests at lines 82-100 (cycle-2 recon) and fixture references at lines 64-68 + 115
- `tests/test_oauth_start_endpoint.py:100` — fixture using `"registration_method": "manual"`
- `the_one/agents.md:52,56` — references to `oauth_client_secret` and the F1 OAuth-config-editor block
- `pyproject.toml` / repo install: `mcp` SDK pinned at the version F6 finalized (1.27.0+ per provider_factory docstring)

## Outputs

What exists after this leg completes:

- `the_one/mcp/oauth/manual_metadata.py` — DELETED
- `the_one/mcp/oauth/provider_factory.py` — manual branch + import + manual-relevant docstring text gone; the function body's only auth-shape branch is the standard `OAuthClientProvider` construction
- `the_one/mcp/oauth/storage.py` — `registration_method` writer at lines 147-156 stripped; `get_client_info` no longer strips a discriminator on read; docstrings updated to describe `dcr_credentials` as the canonical "OAuth client registration record" with no manual-vs-DCR discriminator
- `the_one/mcp/oauth/__init__.py` — `ManualOAuth*` imports + re-exports gone; module docstring's "manual_metadata" bullet at line 21 removed
- `the_one/interfaces/web/api.py` — `/oauth/manual-register` endpoint removed (lines 959-1006); `config.oauth.*` validator block removed (lines 680-699); docstring lines describing `config.oauth` removed (lines 576-578); `oauth_start`'s precondition error message rewritten to no longer reference manual registration
- `tests/test_oauth_manual_metadata.py` — DELETED
- `tests/test_oauth_manual_register_endpoint.py` — DELETED
- `tests/test_oauth_secrets_api.py` — REWRITTEN to use `secrets["dcr_credentials"]` (or `secrets["access_token"]`) as the masking sample; the four masking-contract tests retained with the new field name
- `tests/test_oauth_storage.py` — `registration_method == "dcr"` assertion at line 152 deleted; surrounding test still verifies that `set_client_info` persists DCR-registered client_info correctly
- `tests/test_oauth_provider_factory.py` — manual-branch test cases at lines 82-100 deleted; fixture entries at lines 64-68 and 115 referencing `registration_method` cleaned up
- `tests/test_oauth_start_endpoint.py:100` — `"registration_method": "manual"` fixture entry removed
- `the_one/agents.md:52,56` — updated to drop `oauth_client_secret` references and clarify the post-strip storage model (`secrets["dcr_credentials"]` + `secrets["access_token"]` + `secrets["refresh_token"]`)
- Five docstring locations cleaned up to drop ManualOAuthClientProvider mentions: `client.py:139`, `streamable_http.py:83,102,177`
- All retained pytest suites still pass under `docker compose exec the-one pytest` (full suite, per F6 lesson #5)
- `grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register\|registration_method\|oauth_client_secret\|config\.oauth" the_one/ tests/ --include="*.py"` returns 0 hits (excluding deletion-PR commit messages and CHANGELOG entries; flight log entries are not in scope)

## Acceptance Criteria

- [ ] `the_one/mcp/oauth/manual_metadata.py` no longer exists (`test -f the_one/mcp/oauth/manual_metadata.py` returns false)
- [ ] `tests/test_oauth_manual_metadata.py` no longer exists
- [ ] `tests/test_oauth_manual_register_endpoint.py` no longer exists
- [ ] `provider_factory.py` no longer imports from `the_one.mcp.oauth.manual_metadata`; the function `build_oauth_provider_for_source` body has no `if dcr.get("registration_method") == "manual":` branch; only the standard `OAuthClientProvider` return path remains
- [ ] `storage.py::set_client_info` no longer reads or writes the `registration_method` key; `storage.py::get_client_info` no longer filters out `registration_method` (because nothing writes it anymore — but the comprehension `{k: v for k, v in creds.items() if k != "registration_method"}` is replaced with a plain `dict(creds)` or equivalent, so legacy DB rows with the field still parse cleanly via Pydantic ignoring extras)
- [ ] `the_one/mcp/oauth/__init__.py` no longer imports `ManualOAuthClientProvider` or `ManualOAuthMetadata`; `__all__` no longer lists them; the module docstring's "manual_metadata" bullet is removed
- [ ] `POST /api/oauth/manual-register` returns 404 (no route registered); `the_one/interfaces/web/api.py` no longer contains the `oauth_manual_register` function definition
- [ ] `_validate_mcp_source_config` no longer rejects malformed `config.oauth.{issuer_url, client_id, redirect_uri, scopes}` — the validator block at lines 680-699 is removed; the docstring lines 576-578 describing `config.oauth` are removed
- [ ] `oauth_start`'s precondition error message at api.py:1063-1067 no longer says "manual registration"; it says something like "Server does not support DCR; OAuth flow not available" (operator-facing message reflecting reality post-strip)
- [ ] All five docstring locations no longer mention `ManualOAuthClientProvider`: `client.py:139`, `streamable_http.py:83,102,177`. Each says "OAuthClientProvider" only.
- [ ] `tests/test_oauth_secrets_api.py` exists and its 4 masking-contract tests pass against `secrets["dcr_credentials"]` (or `secrets["access_token"]`) as the masking sample — the file is REWRITTEN, not deleted
- [ ] `tests/test_oauth_storage.py:152` assertion deleted; the surrounding test (`test_set_client_info_persists_dcr_default` or similar) still asserts that `set_client_info` writes the OAuthClientInformationFull payload correctly and `get_client_info` returns an equal value
- [ ] `tests/test_oauth_provider_factory.py` no longer contains the manual-branch test cases (originally at lines 82-100); fixture entries that referenced `registration_method` are cleaned up; the file's remaining tests cover only the DCR happy path + `chat_session_id is None` short-circuit + `dcr_credentials` absent → returns None
- [ ] `tests/test_oauth_start_endpoint.py:100` fixture no longer contains `"registration_method": "manual"`
- [ ] `the_one/agents.md` lines 52 and 56 no longer reference `oauth_client_secret`; the storage-shape paragraph clarifies that the canonical secret keys are `access_token`, `refresh_token`, `token_expires_at`, `dcr_credentials` (no `oauth_client_secret` anywhere). Adjacent prose mentioning the F1 OAuth-config-editor block is cut.
- [ ] `grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register" the_one/ tests/ --include="*.py"` returns 0 hits
- [ ] `grep -rn "registration_method" the_one/ tests/ --include="*.py"` returns 0 hits
- [ ] `grep -rn "oauth_client_secret" the_one/ tests/ --include="*.py"` returns 0 hits **inside this leg's scope** (Python). The JS-side hits remain as L1's responsibility — this leg's grep is `--include="*.py"` only.
- [ ] `grep -rn "config\.oauth" the_one/ tests/ --include="*.py"` returns 0 hits **inside the production path**. Test files may retain references inside docstrings or commented-out fixtures but no live test code references the field.
- [ ] Full test suite passes inside the dev container: `docker compose exec the-one pytest` exits 0 (no skipped tests caused by missing modules; no import errors)

## Verification Steps

How to confirm each criterion is met:

- **File deletions**: `test ! -f the_one/mcp/oauth/manual_metadata.py && test ! -f tests/test_oauth_manual_metadata.py && test ! -f tests/test_oauth_manual_register_endpoint.py && echo "OK"` — must print `OK`
- **Symbol-level grep sweep**:
  ```bash
  grep -rn "ManualOAuth\|manual_metadata\|/oauth/manual-register" the_one/ tests/ --include="*.py" && echo FAIL || echo OK
  grep -rn "registration_method" the_one/ tests/ --include="*.py" && echo FAIL || echo OK
  grep -rn "oauth_client_secret" the_one/ tests/ --include="*.py" && echo FAIL || echo OK
  ```
  All three must print `OK` (the `&& echo FAIL || echo OK` idiom prints FAIL only when grep finds a match)
- **Endpoint removal**: `curl -X POST http://localhost:8484/api/oauth/manual-register -H "Content-Type: application/json" -d '{}'` must return HTTP 404 (after `make rebuild`)
- **Validator removal**: `curl -X POST http://localhost:8484/api/mcp-sources -H "Content-Type: application/json" -d '{"name":"test","type":"streamable-http","config":{"url":"https://example.com","oauth":{"client_id":12345}}}'` must NOT return 422 with `config.oauth.client_id must be a string` (the validator is gone). It may 422 for other reasons (e.g. transport literal mismatch) but the `config.oauth.*` clause is dead.
- **Test suite**: `docker compose exec the-one pytest tests/test_oauth_secrets_api.py tests/test_oauth_storage.py tests/test_oauth_provider_factory.py tests/test_oauth_start_endpoint.py -v` exits 0
- **Full suite**: `docker compose exec the-one pytest` exits 0
- **Module-import smoke**: `docker compose exec the-one python -c "from the_one.mcp.oauth import build_oauth_provider_for_source, MCPSourceTokenStorage, MCPAuthRequired, make_oauth_handlers; print('OK')"` prints OK (and does NOT print `ImportError` for ManualOAuth* — the package no longer exports them)
- **Provider factory smoke**: `docker compose exec the-one python -c "import inspect; from the_one.mcp.oauth.provider_factory import build_oauth_provider_for_source; src = inspect.getsource(build_oauth_provider_for_source); assert 'registration_method' not in src and 'ManualOAuth' not in src; print('OK')"` prints OK

## Implementation Guidance

Order matters — module deletions and `__init__.py` updates ripple into import-time errors if done out of order. Follow this sequence:

### Step 1: Delete `manual_metadata.py`

```bash
rm the_one/mcp/oauth/manual_metadata.py
```

### Step 2: Update `the_one/mcp/oauth/__init__.py`

Remove the `manual_metadata` import (line 29) and the two entries in `__all__` (lines 36-37). Remove the `manual_metadata: ManualOAuthClientProvider for non-DCR providers (L2)` bullet at line 21.

After edits, the file should re-export only: `MCPAuthRequired`, `MCPSourceTokenStorage`, `build_oauth_provider_for_source`, `make_oauth_handlers`, `start_periodic_sweep`, `stop_periodic_sweep`.

### Step 3: Simplify `provider_factory.py`

- Delete the `from the_one.mcp.oauth.manual_metadata import ManualOAuthClientProvider, ManualOAuthMetadata` import at line 54
- Delete the `if dcr.get("registration_method") == "manual": ... return ManualOAuthClientProvider(...)` branch (lines 115-128 — 14 lines including the manual block)
- Delete the docstring text describing the manual branch:
  - Module docstring: drop the parenthetical `(or ManualOAuthClientProvider)` at line 1 and the `- registration_method == "manual"` bullet at lines 8-10
  - Function docstring: drop the `When dcr_credentials is populated:` two-bullet block at lines 73-77 (since only the DCR path remains, the docstring becomes a single paragraph: `When ``dcr_credentials`` is populated, returns a standard ``OAuthClientProvider`` that goes through full RFC 9728 PRM + RFC 8414 OASM + RFC 7591 DCR`)
- Leave the `chat_session_id is None` short-circuit (lines 92-93) and the `dcr` absence/empty check (lines 94-96) intact
- Leave the standard `OAuthClientProvider` construction (lines 129-135) intact, but unindent it (it's now the only return path, no longer inside an `else` of the deleted `if`)

### Step 4: Strip `registration_method` from `storage.py`

`set_client_info` (lines 134-159):

- Replace the `prior` lookup + conditional discriminator preserve+default block (lines 147-156) with a single line:
  ```python
  secrets["dcr_credentials"] = payload
  ```
- The `payload = client_info.model_dump(...)` line at 147 stays
- The trailing `source.secrets = secrets; await self._repo.update(source)` stays (lines 158-159 in current code; renumbered after deletions)

`get_client_info` (lines 109-132):

- Replace the comprehension `payload = {k: v for k, v in creds.items() if k != "registration_method"}` at line 123 with `payload = dict(creds)`. The SDK's `OAuthClientInformationFull` (via `OAuthClientMetadata` → Pydantic `BaseModel`) does NOT set `model_config = ConfigDict(extra="forbid")` — Pydantic's default is `extra="ignore"`, so legacy DB rows that still have `registration_method` baked in will silently drop the field on `model_validate`. No backward-compat shim needed; the comprehension is gone outright.
- Update the docstring block at lines 113-115 to drop the discriminator description; say `Stored under secrets["dcr_credentials"] as a JSON dict (the OAuthClientInformationFull payload).`

Update module docstring at line 10: change `dcr_credentials — dict | None (full OAuthClientInformationFull JSON, plus a registration_method discriminator so L4 can pick the right provider class)` to `dcr_credentials — dict | None (full OAuthClientInformationFull JSON)`.

Update `set_client_info` docstring (lines 137-143): remove the "ManualOAuthClientProvider overrides set_client_info..." paragraph; reduce to a one-line description.

### Step 5: Delete `/api/oauth/manual-register` endpoint

In `the_one/interfaces/web/api.py`:

- Delete lines 959-1006 (the `@router.post("/oauth/manual-register")` decorator and entire function body, plus the trailing blank line if needed for spacing)
- Update the `oauth_start` docstring's `must call /api/oauth/manual-register first` clause at line 1018 to reflect post-strip reality (e.g., "the AS must support DCR — surfaces a 400 if `secrets['dcr_credentials']` is absent")
- Update the `oauth_start` precondition error message at line 1066: change `"Configure manual registration or use a DCR-supporting AS"` to `"DCR-supporting AS required; OAuth flow not available for this source"` (or similar — KEEP the substring "DCR" so the test assertion at `test_oauth_start_endpoint.py:72` can be narrowed to `assert "DCR" in resp.json()["detail"]` without losing meaning)

In `tests/test_oauth_start_endpoint.py`:

- Line 72 contains `assert "Configure manual registration" in resp.json()["detail"]` (or similar substring on the old precondition error). Change the substring to `"DCR"` (or whatever stable substring the new message contains). The test name `test_start_400_when_dcr_credentials_absent` (or equivalent) stays — only the assertion's substring changes.
- Test docstring/comment block on the same test may quote the old message verbatim — update to match.

### Step 6: Delete `_validate_mcp_source_config`'s `config.oauth.*` validator

In `_validate_mcp_source_config`:

- Delete lines 680-699 (the `oauth = cfg.get("oauth")` block and all four `config.oauth.{issuer_url, client_id, redirect_uri, scopes}` shape checks)
- Update the function docstring to remove the `config.oauth if present must include {issuer_url, client_id, scopes (list), redirect_uri} as strings (oauth.scopes is a list[str]).` clause at lines 576-578. The streamable-http section becomes: `Streamable-HTTP: config.url is required (non-empty string); config.headers must be a dict[str, str] if present.`

### Step 7: Update production-code docstrings

Five files reference `ManualOAuthClientProvider` in non-deleted docstrings/comments:

- `the_one/mcp/client.py:139` — comment `# and instantiates OAuthClientProvider/ManualOAuthClientProvider) is`. Change to `# and instantiates OAuthClientProvider) is`. Read 5 lines of surrounding context to confirm sentence flow.
- `the_one/mcp/transports/streamable_http.py:83` — docstring `and instantiates OAuthClientProvider/ManualOAuthClientProvider with`. Change to `and instantiates OAuthClientProvider with`.
- `the_one/mcp/transports/streamable_http.py:102` — comment `# and instantiates OAuthClientProvider/ManualOAuthClientProvider with`. Same edit.
- `the_one/mcp/transports/streamable_http.py:177` — comment `# and instantiates OAuthClientProvider/ManualOAuthClientProvider with`. Same edit.

### Step 8: Test changes

Delete (`rm`) the entire files:

```bash
rm tests/test_oauth_manual_metadata.py
rm tests/test_oauth_manual_register_endpoint.py
```

REWRITE `tests/test_oauth_secrets_api.py`:

- The 4 masking-contract tests test:
  1. GET strips managed keys + masks one operator-supplied secret
  2. PUT with `__MASKED__` sentinel preserves the prior plaintext value
  3. PUT with new value writes the new plaintext
  4. PUT omitting a previously-stored secret REPLACES it (REST replace semantics)
- Replace every `oauth_client_secret` literal with a different operator-supplied secret-key name. **Recommended sample**: an env-var-style secret key like `"github_token"` or a fictitious header secret like `"x_api_key"` — anything that's still plausibly an operator-supplied sensitive value but is NOT the now-deleted `oauth_client_secret`. This keeps the test exercising the masking contract on operator-data without coupling to the deleted field.
- DO NOT use `dcr_credentials` or `access_token` as the masking sample even though the leg suggests it — those are OAuth-MANAGED keys that the API layer's `_OAUTH_MANAGED_SECRET_KEYS` strip+preserve logic handles separately from operator-supplied secrets. The masking contract under test is for OPERATOR-supplied secrets specifically. Use a fresh operator-supplied secret key. (Implementing agent: read `_OAUTH_MANAGED_SECRET_KEYS` definition in `api.py` to confirm; if `dcr_credentials` is in the managed set, choose an operator-supplied key instead.)
- Test function names should drop `oauth_client_secret` and use a generic descriptor like `test_get_strips_managed_keys_and_masks_operator_secret`, `test_put_preserves_masked_sentinel`, etc.
- File header docstring updated to reflect the new sample field choice.

Edit `tests/test_oauth_storage.py`:

- Find the assertion at line 152 (`assert ...["registration_method"] == "dcr"`) and delete it
- Read 20 lines of surrounding context. The test itself (likely named `test_set_client_info_persists_dcr_default` or similar) should still verify that `set_client_info` writes the OAuthClientInformationFull payload correctly. If the only assertion in the test was the deleted one, the test name should be renamed to reflect the new contract (e.g., `test_set_client_info_persists_oauth_client_information`) and a new assertion should verify the persisted payload deserializes back via `get_client_info` and equals the input.

Edit `tests/test_oauth_provider_factory.py`:

- **First**: run `grep -n "registration_method\|manual_metadata\|ManualOAuth\|manual" tests/test_oauth_provider_factory.py` to get current line numbers. Cycle-2 recon flagged ~lines 82-100 for the manual-branch test, but the file may have drifted. Edit by symbol match, not by hardcoded ranges.
- Delete the import of `ManualOAuthClientProvider` (currently around line 16). If left in place, the file `ImportError`s at collection time after `manual_metadata.py` is deleted.
- Delete the manual-branch test function (currently `test_factory_returns_manual_provider_for_manual_method` or similar around lines 81-100) entirely.
- In the retained DCR test (currently `test_factory_returns_oauth_client_provider_for_dcr_method` or similar around lines 70-80), find and delete any `assert not isinstance(result, ManualOAuthClientProvider)` line (currently around line 76). The remaining `assert isinstance(result, OAuthClientProvider)` is sufficient.
- Find every fixture entry containing `"registration_method": "dcr"` (currently around lines 68, 115) and remove just the `registration_method` field — leave the rest of the fixture's `dcr_credentials` shape (e.g., `client_id`, `client_secret`) intact.
- After edits, the file's tests should cover: (1) returns None when `chat_session_id is None`, (2) returns None when `dcr_credentials` is absent or has no `client_id`, (3) returns a standard `OAuthClientProvider` instance when `dcr_credentials` is populated, (4) any closure/handler invariants the file already covers (loopback redirect URI bound to `settings.port`, `token_endpoint_auth_method="none"`, etc.)
- Run `docker compose exec the-one pytest tests/test_oauth_provider_factory.py -v` to confirm no broken imports or removed-symbol references

Edit `tests/test_oauth_start_endpoint.py`:

- Find line 100 (`"registration_method": "manual"`) and delete that line; the surrounding fixture should still have a valid `dcr_credentials` shape with `client_id` populated. If the fixture's `dcr_credentials` had ONLY `client_id` + `registration_method`, add `"client_secret": "..."` or other DCR-shape fields to keep the fixture realistic; if it had a full DCR shape and the manual discriminator was vestigial, just delete the line.

### Step 9: Update `agents.md`

Read lines 50-60 of `the_one/agents.md`. The `oauth_client_secret` references at lines 52 and 56 are inside a paragraph describing `MCPSourceRepository` storage shape and a callout box about the secret payload key.

**Read `_OAUTH_MANAGED_SECRET_KEYS` first.** The frozenset definition lives in `the_one/interfaces/web/api.py`. Before editing prose, confirm its contents — at design time it is `{"access_token", "refresh_token", "token_expires_at", "dcr_credentials"}`. The agents.md prose MUST match this set exactly. Do NOT add `scope` or `token_type` to the prose — those are stored under `MCPSource.secrets` but are NOT in the managed frozenset; including them would create new doc drift.

Edit:
- Line 52: drop `, oauth_client_secret,` from the example secret-key list. Keep the rest of the storage-shape paragraph intact.
- Line 56: delete the entire `**OAuth client_secret payload key** is locked to ...` callout. Replace it with a one-line statement of the canonical secret keys post-F6.5, listing exactly the four members of `_OAUTH_MANAGED_SECRET_KEYS`: `**OAuth managed secret keys** post-F6.5: `secrets["dcr_credentials"]` (the OAuthClientInformationFull payload from RFC 7591 DCR), `secrets["access_token"]`, `secrets["refresh_token"]`, `secrets["token_expires_at"]`. Operator-supplied env-var values, headers, etc. are stored under their own operator-chosen keys; the four managed keys are written exclusively by `MCPSourceTokenStorage` (F5) and are stripped+preserved on PUT by the API layer's `_OAUTH_MANAGED_SECRET_KEYS` logic.`

Note: `agents.md` is Markdown, not Python — it is in scope for L0 but does NOT show up in the Python-only grep sweep in the Verification Steps. The implementing agent must edit `agents.md` even though `grep --include="*.py"` won't surface its `oauth_client_secret` references.

If a different prose framing fits better, it's at the implementing agent's discretion — the binding contract is just "no references to `oauth_client_secret` or `config.oauth.*` remain in agents.md."

### Step 10: Verify and run tests

After all edits, run the verification steps from the section above. The order:

1. `grep` sweep — three commands, all must print `OK`
2. Module-import smoke — must print OK
3. `docker compose exec the-one pytest tests/test_oauth_*.py -v` — exits 0
4. `docker compose exec the-one pytest` — full suite exits 0

If any test fails, fix in place — do NOT skip or `xfail`. Common failure modes:

- ImportError from a stale import of `ManualOAuthClientProvider` in a test fixture — grep test files for any remaining import and remove
- AssertionError in `test_oauth_secrets_api.py` if the rewrite missed updating a fixture seed that had `oauth_client_secret` baked in
- AttributeError in `test_oauth_provider_factory.py` if the deleted manual-branch test was depending on a fixture that the cycle-2 cleanup removed

## Edge Cases

- **Pydantic extras handling for legacy DB rows**: legacy rows written by F5 had `secrets["dcr_credentials"]["registration_method"] = "dcr"` (or `"manual"`). Post-strip `get_client_info` must parse those rows cleanly. The SDK's `OAuthClientInformationFull` (via `OAuthClientMetadata` → `BaseModel`) does NOT set `extra="forbid"` — Pydantic's default `extra="ignore"` applies, so `OAuthClientInformationFull.model_validate(legacy_dict_with_registration_method)` succeeds and silently drops the unknown field. Therefore `payload = dict(creds)` (Step 4) is correct unconditionally; no backward-compat shim is needed.
- **`oauth_start` precondition message**: the post-strip message must be honest — "DCR-supporting AS required" — but not blame the operator (the operator has no way to MAKE an AS support DCR; if their target AS doesn't, this product simply doesn't work for them post-F6.5). The error message should say what's wrong, not what the operator should do.
- **`agents.md` storage paragraph alignment with code**: the canonical secret-key list in the rewritten paragraph MUST match what `_OAUTH_MANAGED_SECRET_KEYS` actually contains in `api.py`. Read that constant before drafting the prose. Drift between the prose and the code is exactly the kind of dead-letter doc state F6 debrief lesson #1 calls out.
- **Test file deletion vs rewrite distinction**: `test_oauth_manual_metadata.py` and `test_oauth_manual_register_endpoint.py` are tests for code that's being deleted — they go too. `test_oauth_secrets_api.py` is a masking-contract test file whose contracts survive the strip — only the field name under test changes. The implementing agent must NOT delete the third file.
- **`provider_factory.py` simplification preserves behavior**: post-strip, when `dcr_credentials` is populated AND `chat_session_id` is bound, the factory returns an `OAuthClientProvider` instance. When `dcr_credentials` is absent OR `chat_session_id` is None, the factory returns None. There is no third return path. `tests/test_oauth_provider_factory.py` should cover both branches.
- **Test count delta**: F6.5 expects test count to decrease (deleted manual-branch tests) but not increase yet — L2's 4 new tests are L2's leg, not L0's. If the implementing agent finds itself adding NEW tests in L0, that's scope creep; the only tests changing in L0 are deletions and the `test_oauth_secrets_api.py` rewrite.
- **`storage.py::get_client_info` test coverage**: if the `registration_method` filter at line 123 is removed (vs. kept as legacy-row shim), and the test suite previously had a test that depended on the filter (e.g. testing that a legacy row with the discriminator parses cleanly), confirm coverage gap is acceptable. Per F6.5 design, legacy DB rows with the field are out-of-scope — F6.5 is a clean-slate strip. But this leg's `dict(creds)` form will pass either way (Pydantic ignores extras by default in the SDK's auth models).

## Files Affected

- `the_one/mcp/oauth/manual_metadata.py` — DELETE entire file
- `the_one/mcp/oauth/__init__.py` — drop ManualOAuth* import + re-exports + docstring bullet
- `the_one/mcp/oauth/provider_factory.py` — drop manual import + manual branch + docstring text describing manual flow
- `the_one/mcp/oauth/storage.py` — drop `registration_method` writer + docstring scrub
- `the_one/interfaces/web/api.py` — DELETE `/oauth/manual-register` endpoint + `config.oauth.*` validator block + docstring lines + update `oauth_start` precondition error message
- `the_one/mcp/client.py:139` — drop ManualOAuthClientProvider mention in comment
- `the_one/mcp/transports/streamable_http.py:83,102,177` — drop ManualOAuthClientProvider mentions in docstring/comments
- `tests/test_oauth_manual_metadata.py` — DELETE entire file
- `tests/test_oauth_manual_register_endpoint.py` — DELETE entire file
- `tests/test_oauth_secrets_api.py` — REWRITE to use a different operator-supplied secret-key field as the masking sample
- `tests/test_oauth_storage.py:152` — DELETE assertion; verify surrounding test still has a meaningful contract
- `tests/test_oauth_provider_factory.py` — DELETE the `ManualOAuthClientProvider` import (~line 16); DELETE the manual-branch test function (~lines 81-100); DELETE the `assert not isinstance(result, ManualOAuthClientProvider)` line (~line 76) in the retained DCR test; clean up `"registration_method": "dcr"` fixture entries (~lines 68, 115)
- `tests/test_oauth_start_endpoint.py:100` — DELETE the `"registration_method": "manual"` line from fixture
- `tests/test_oauth_start_endpoint.py:72` — UPDATE the assertion substring on `oauth_start`'s precondition error from `"Configure manual registration"` to `"DCR"` (or the stable substring of the new error message); update any test docstring quoting the old message
- `the_one/agents.md` — drop `oauth_client_secret` references at lines 52, 56; rewrite the secret-payload-key callout to reflect post-F6.5 reality

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing inside the dev container (`docker compose exec the-one pytest`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`; the flight-level review + commit happens after L3 lands
- [ ] Check off this leg in flight.md
- [ ] **DO NOT commit** — flight 6.5 uses the per-flight (not per-leg) commit cadence per `/agentic-workflow` protocol; the Reviewer + commit run after L3 (the last autonomous leg)

## Citation Audit

24 citations verified against current code on branch `flight/6_5-oauth-simplification` HEAD `c375979` at leg design time (2026-05-08), updated post-design-review (1 cycle):

- `manual_metadata.py` (file existence) — OK; 220 LOC at design time
- `provider_factory.py:1,8-10,54,73-77,115-128` — OK; symbol/snippet match
- `storage.py:10,113-115,123,137-143,147-156` — OK
- `__init__.py:21,29,36-37` — OK
- `api.py:576-578,680-699,959-1006,1018,1063-1067` — OK
- `client.py:139` — OK
- `streamable_http.py:83,102,177` — OK
- `agents.md:52,56` — OK
- `tests/test_oauth_secrets_api.py:66-203` (8 references) — OK; manual citation count matches grep output
- `tests/test_oauth_storage.py:152` — OK
- `tests/test_oauth_provider_factory.py:16` (`ManualOAuthClientProvider` import) — OK; added in design review cycle 1
- `tests/test_oauth_provider_factory.py:68,115` (`registration_method` fixture entries) — OK; line 92 also flagged in review (same surgical edit pattern)
- `tests/test_oauth_provider_factory.py:76` (`assert not isinstance(result, ManualOAuthClientProvider)`) — OK; added in design review cycle 1
- `tests/test_oauth_provider_factory.py:81-100` (manual-branch test function) — OK; symbol-match recommended (function name like `test_factory_returns_manual_provider_for_manual_method`)
- `tests/test_oauth_start_endpoint.py:72` (precondition error assertion) — OK; added in design review cycle 1 (high-severity fix)
- `tests/test_oauth_start_endpoint.py:100` — OK
- `tests/test_oauth_manual_metadata.py` (file existence + 220 LOC) — OK
- `tests/test_oauth_manual_register_endpoint.py` (file existence + 104 LOC) — OK
- `_OAUTH_MANAGED_SECRET_KEYS` frozenset in `api.py` — OK; canonical members are `{"access_token", "refresh_token", "token_expires_at", "dcr_credentials"}` (4 keys; `scope` and `token_type` are NOT members)

**Design review cycle 1 (2026-05-08)**: Reviewer flagged 2 high + 1 medium issues, all incorporated:
- HIGH: `test_oauth_start_endpoint.py:72` assertion would break when precondition message changes — added to Files Affected and Step 5; new message phrasing keeps "DCR" substring so test assertion stays meaningful.
- HIGH: Pydantic extras handling reconciled — confirmed `OAuthClientInformationFull` uses default `extra="ignore"`, so `dict(creds)` is correct unconditionally; removed the conditional hedging in Step 4 and Edge Cases.
- MEDIUM: `test_oauth_provider_factory.py` additional cleanup — added explicit instructions for the `ManualOAuthClientProvider` import (~line 16) and the `assert not isinstance(...)` line (~line 76); both would `ImportError`/`NameError` post-strip if missed.

Edit by symbol match in `test_oauth_provider_factory.py` per the recommendation in Step 8 — line numbers are guidance, not contract.
