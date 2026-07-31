# Leg: oauth-foundation-and-registration

**Status**: completed
**Flight**: [Anthropic Plan Provider End-to-End](../flight.md)

## Objective

Land the `anthropic-plan` provider type foundation in one green commit-unit: the PKCE OAuth flow module, migration v33 (encrypted `secrets` column + regenerated type CHECK), the indivisible type-registration atom, the three-direction secrets API contract, and the start-auth/submit-code endpoints — gated by an up-front spike confirming the OAuth endpoint premises.

## Context

- **DD-1 (flight)**: hand-rolled PKCE against Anthropic's fixed public consumer-OAuth client; code-paste consent (consent page displays a code the operator pastes). No MCP SDK OAuth machinery. The spike below is the flight's divert gate.
- **DD-2 (flight)**: `secrets` column on `llm_providers`, whole-dict Fernet blob via existing helpers; managed keys `access_token`, `refresh_token`, `token_expires_at` (unix epoch), `scope`, `token_type`. Strip-on-create / strip-in-response / preserve-on-PUT; UI-facing `oauth_active` boolean.
- **DD-4 (flight, partial here)**: only the `AnthropicPlanProvider` *skeleton* lands in this leg (subclass constructing `AsyncAnthropic(auth_token=..., default_headers={"anthropic-beta": "oauth-2025-04-20"})`); refresh mechanics, `_before_request`, and the credential source are Leg 2.
- The type-registration atom is indivisible because `the_one/db/models.py` and `the_one/agent/factory.py` carry module-load asserts pinned to `PROVIDER_TYPES` — tuple, Literal, factory map, and registry loader must move together or the suite fails at import.

**Planning assumptions the spike verifies** (from public knowledge of Anthropic's consumer OAuth as used by Claude Code and other third-party apps — treat as unverified until the spike):
- Authorize endpoint: `https://claude.ai/oauth/authorize` with `client_id` (well-known public client `9d1c250a-e61b-44d9-88ed-5944d1962f5e`), `response_type=code`, `redirect_uri=https://console.anthropic.com/oauth/code/callback` (Anthropic-hosted code-display page), `scope=org:create_api_key user:profile user:inference`, `code=true`, PKCE `code_challenge`/`code_challenge_method=S256`, `state`.
- Token endpoint: `POST https://console.anthropic.com/v1/oauth/token` (JSON body) with `grant_type=authorization_code` + `code` + `state` + `client_id` + `redirect_uri` + `code_verifier`; refresh via `grant_type=refresh_token` + `refresh_token` + `client_id`.
- The displayed code may arrive in `code#state` form — the paste parser must tolerate and split it.

## Inputs

- Flight spec DD-1/DD-2/DD-4/DD-7 (this leg implements the server side of DD-7: exchange persists tokens to the saved row).
- Schema at `CURRENT_VERSION = 32` (`the_one/db/schema.py:15`); migration rebuild ceremony precedent in existing CHECK-changing migration blocks (e.g. the v12 block; `DROP TABLE IF EXISTS ..._new` prelude pattern near `schema.py:463`).
- `PROVIDER_TYPES` tuple at `the_one/db/_provider_types.py:20`; module-load asserts at `the_one/db/models.py:60` and `the_one/agent/factory.py:131` (`_PROVIDER_TYPE_MAP` at `factory.py:122`).
- Registry lazy loader `_try_load_builtin` at `the_one/llm/registry.py:24` with the openrouter→openai pip-extra alias at `registry.py:37`.
- Secrets-blob helpers `_encrypt_secrets_blob`/`_decrypt_secrets_blob` at `the_one/db/repositories.py:35` (used via repository methods ~`repositories.py:412`; consumer precedent: `MCPSourceRepository`).
- Provider CRUD in `the_one/interfaces/web/api.py`: create validates raw body via `LLMProviderConfig.model_validate` (~api.py:3988), `_provider_response` starts from `model_dump()` (~api.py:3905), strip-and-preserve precedent for OAuth-managed keys (~api.py:1314).
- `AnthropicProvider` at `the_one/llm/anthropic_provider.py` (client built in `__init__`, ~line 134).

## Outputs

- New `the_one/llm/anthropic_oauth.py`: PKCE helpers (verifier/challenge/state), `build_authorize_url()`, `exchange_code()`, `refresh_token()` — plain `httpx`, fixed endpoints, typed errors.
- Migration v33 in `the_one/db/schema.py` (`CURRENT_VERSION = 33`): `llm_providers` rebuild adding `secrets TEXT NOT NULL DEFAULT '{}'` with type CHECK regenerated from `PROVIDER_TYPES`.
- `anthropic-plan` registered: `PROVIDER_TYPES` tuple, `LLMProviderConfig.type` Literal, `_PROVIDER_TYPE_MAP`, registry loader entry (+ pip-extra alias `anthropic-plan`→`anthropic`), `the_one/diagnostics.py` module-import list.
- New `the_one/llm/anthropic_plan_provider.py`: `AnthropicPlanProvider(AnthropicProvider)` skeleton (bearer + OAuth beta header; accepts `provider_config_id` kwarg for Leg 2's credential source; no refresh logic yet).
- `LLMProviderConfig.secrets: dict = {}` field; `LLMProviderRepository` encrypts/decrypts the blob.
- API: create forces `secrets={}`; `_provider_response` strips `secrets` and adds `oauth_active` (true iff a non-expired-or-refreshable token set is stored — presence of `access_token` + `refresh_token` suffices here); PUT preserves managed keys from the stored row; new `POST /api/providers/{provider_id}/oauth/start` (generates verifier/state, holds them in an in-process pending map keyed by provider id, returns the authorize URL) and `POST /api/providers/{provider_id}/oauth/code` (accepts pasted code, tolerates `code#state`, exchanges via `anthropic_oauth.exchange_code`, persists managed keys to the row's secrets, evicts the pending entry, returns the updated masked provider response).
- Tests: spike record in flight log; migration tests; PKCE/exchange/refresh unit tests against mocked HTTP; repository ciphertext-at-rest test; API contract tests; consistency test at 7 members.

## Acceptance Criteria

- [x] **Spike (HARD STOP — first task)**: probing the built authorize URL (real network, no login) produces **no OAuth protocol error** (`invalid_client`, `redirect_uri` mismatch, unsupported `code_challenge_method`). A Cloudflare challenge or login redirect is NOT a failure — if the raw HTTP probe is inconclusive, fall back to loading the URL in the browser apparatus (goldfinch / chrome-devtools MCP) and judge the rendered page. Result recorded in the flight log with the exact URL parameters used. On a genuine OAuth protocol error, STOP the leg and signal `[BLOCKED:spike-contradicts-DD-1]` — do not begin migration or contract work.
- [x] `anthropic-plan` present in `PROVIDER_TYPES`, the `LLMProviderConfig.type` Literal, `_PROVIDER_TYPE_MAP`, the registry lazy loader (with pip-extra alias to `anthropic`), and the diagnostics module list; the full unit suite imports cleanly (no assert trips).
- [x] `tests/test_provider_types_consistency.py` updated to the 7-member set and green.
- [x] Migration v33 exists following the rebuild ceremony (copy the v12 block at `schema.py:443-488`: foreign_keys OFF/ON inside one `executescript`, `_new` drop prelude, `schema_version` insert last) **and** the fresh-DB DDL in `SCHEMA_V1` (`schema.py:36-45`) also gains the `secrets` column; tests cover: populated v32→v33 upgrade preserving rows and the `agents.provider_config_id` FK, an `anthropic-plan` row inserting successfully into the **migrated** DB, fresh-DB creation, and idempotent re-run — all **new** `aiosqlite.connect` usages via `async with` (existing bare usages in `test_db_migration.py` are out of scope).
- [x] Encryption key rotation covers the new surface: `POST /api/encryption/rotate` (`api.py:4441`) re-encrypts `llm_providers.secrets` as a fourth surface inside the same atomic transaction (alongside `llm_providers.api_key`, `mcp_sources.secrets`, `connectors.secrets`), with the same tolerant-`InvalidToken` handling for plaintext-`'{}'` migration residue; a rotation test proves plan-provider tokens survive rotation (precedent: rotation tests in `tests/test_provider_api.py` ~574-1066).
- [x] Legacy-row read path: a pre-migration row (plaintext `'{}'` in `secrets`) reads back without raising, and GET returns `oauth_active: false` for it.
- [x] `anthropic_oauth.py` unit tests pass against mocked HTTP: authorize-URL construction (S256 challenge derived from verifier, state present), successful code exchange maps the token response to the managed-keys shape with absolute `token_expires_at`, `code#state` paste form parsed, refresh grant returns rotated tokens, and 4xx token-endpoint responses raise a typed error (not a bare exception).
- [x] Repository round-trip test proves ciphertext at rest: after storing secrets, the raw `secrets` column read via direct SQL is neither `'{}'` nor contains any token substring; decrypted read returns the original dict.
- [x] API contract tests: POST create with a `secrets` payload stores `{}`; GET response contains no `secrets` key and an `oauth_active` boolean; PUT without secrets preserves stored managed keys; PUT cannot overwrite managed keys from the client side.
- [x] `POST /api/providers/{id}/oauth/start` returns an authorize URL for a saved `anthropic-plan` provider (404 unknown id, 409 or 400 for non-plan types); `POST .../oauth/code` with a mocked exchange persists tokens (subsequent GET shows `oauth_active: true`) and returns the masked provider; invalid/expired code surfaces a 4xx with an actionable message; missing pending state (start never called) surfaces a clear 4xx.
- [x] `get_provider("anthropic-plan", model=..., api_key=None, config=..., provider_config_id=..., access_token="test-token")` returns an `AnthropicPlanProvider` whose client carries `auth_token="test-token"` (bearer mode — the `x-api-key` path unused) and the `anthropic-beta: oauth-2025-04-20` default header, and which stored `provider_config_id` (assert on client/instance config, no network). The skeleton takes the token as an explicit constructor kwarg in this leg; Leg 2 replaces that feed with the credential source. Constructing without `access_token` succeeds (client with `auth_token=None`, failing at request time) — no raise requirement in this leg.
- [x] Full unit suite green (`make test-unit` band ~3997+ passed, 0 failed).

## Verification Steps

- Spike: run the URL probe (curl or httpx script), paste the redacted result + verdict into the flight log Leg Progress entry.
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_types_consistency.py tests/test_db_migration.py tests/test_anthropic_oauth.py tests/test_provider_api.py tests/test_provider_repository.py -x --timeout 30` for the focused loop.
- `make test-unit` once at leg end; confirm import-time cleanliness and totals.
- Manual check of migration on a copy of a real v32 DB if one is present in the dev data dir (optional, note result).

## Implementation Guidance

1. **Spike first (hard stop).** Build the authorize URL from the planning assumptions and probe it. Record outcome in the flight log. Only proceed on pass.
2. **Type-registration atom in one change-set**: tuple → Literal → factory map → registry loader (+ extra alias at the `registry.py:37` pattern) → diagnostics list → provider skeleton module (so the loader has a target) → consistency-test 7-member update.
3. **Migration v33**: copy the latest CHECK-rebuild block's ceremony; new column `secrets TEXT NOT NULL DEFAULT '{}'`; bump `CURRENT_VERSION`; write migration tests per criteria (note the fresh-DB CHECK is auto-derived — the populated-upgrade test is the one that catches a missing migration).
4. **Model + repository**: add `secrets: dict = {}` to `LLMProviderConfig` (Pydantic edit — server restart needed in dev, see CLAUDE.md); encrypt/decrypt in `_to_row`/`_row_to_model` via the blob helpers.
5. **OAuth module**: pure functions + a small dataclass for the token set; no DB access; typed error hierarchy (`OAuthExchangeError` etc.); httpx client injected or constructed per-call for testability.
6. **API contract**: force-empty on create; strip + `oauth_active` in `_provider_response` (`oauth_active` rule: `access_token` AND `refresh_token` both present — stricter than MCP's any-key rule at ~api.py:949; pin the chosen rule in a test); preserve managed keys on update (mirror ~api.py:1314 pattern); then the two oauth endpoints. Token persistence uses a dedicated `update_secrets()`-style repository method — NOT a full-model `update()` — so PUT-preserve logic and token writes stay independent. Pending verifier/state map is process-local (dict keyed by provider id, replaced on repeated /start; entry TTL optional — note if skipped). "Provider deleted between /start and /code" is handled by re-checking row existence at /code time — no delete-hook plumbing.
7. **Provider skeleton**: subclass overriding client construction only; accept and store `provider_config_id`; raise a clear error if constructed without stored credentials AND without api-key fallback (final wording leg 2 refines).
8. **Leg-end**: flight log Leg Progress entry (spike verdict, migration id, test counts), leg status → `landed`, propagate artifact updates. Do NOT commit; signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Pasted code variants**: bare code, `code#state`, surrounding whitespace — normalize; mismatched state → 4xx, do not exchange.
- **Repeated /start**: replaces the pending verifier (old code becomes unexchangeable — acceptable; message should say to use the newest window).
- **Provider deleted between /start and /code**: 404, pending entry evicted.
- **Existing rows during migration**: all six legacy types plus NULL/legacy api_key values must survive the rebuild byte-identical.
- **Encryption key rotation**: rotation is centralized in `POST /api/encryption/rotate` (`api.py:4441`), which hardcodes three surfaces re-encrypted atomically before the key file is replaced — `llm_providers.secrets` must become the fourth, or the next rotation bricks stored tokens (see acceptance criterion).
- **Deferred to Leg 3 (explicitly out of scope here)**: the `/providers/types` UI-selectable list is a separate hardcoded literal (`api.py:3946-3965`) pinned by tests (`tests/test_provider_api.py:2024-2043`, incl. a `len == 6` dev-mode assertion) — it moves in the admin-UI leg so the type doesn't appear in the picker before its editor support exists.
- **`oauth_active` on legacy `anthropic` providers**: field appears for all providers in the response — must be `false`/absent-equivalent for non-plan types without breaking the frontend (choose `false`; frontend ignores unknown fields today).

## Files Affected

- `the_one/db/_provider_types.py` — add `anthropic-plan`
- `the_one/db/models.py` — Literal + `secrets` field
- `the_one/db/schema.py` — v33 migration, `CURRENT_VERSION`
- `the_one/db/repositories.py` — secrets blob on `LLMProviderRepository` (+ key-rotation coverage)
- `the_one/llm/anthropic_oauth.py` — new
- `the_one/llm/anthropic_plan_provider.py` — new (skeleton)
- `the_one/llm/registry.py` — loader entry + extra alias
- `the_one/agent/factory.py` — `_PROVIDER_TYPE_MAP` entry
- `the_one/diagnostics.py` — module list
- `the_one/interfaces/web/api.py` — secrets contract + two oauth endpoints
- `tests/test_provider_types_consistency.py`, `tests/test_db_migration.py`, `tests/test_anthropic_oauth.py` (new), `tests/test_provider_api.py`, `tests/test_provider_repository.py`

## Citation Audit

2026-07-28 (Flight Director): verified against working tree @ 91d82e4 — `schema.py:15` (`CURRENT_VERSION = 32`), `_provider_types.py:20` (tuple), `models.py:60` (assert), `factory.py:122/131` (map + assert), `registry.py:24/37` (loader + extra alias), `repositories.py:35/412` (blob helpers). `api.py` anchors (~3905, ~3988, ~1314) verified by Architect review same day; treat as approximate — locate by symbol (`_provider_response`, `create_provider`, OAuth managed-keys preserve block).

---

## Post-Completion Checklist

**Batched-commit mode: do NOT commit at leg end.**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit`)
- [x] Flight log Leg Progress entry written (incl. spike verdict)
- [x] Leg status set to `landed` (this file's header)
- [x] Signal `[HANDOFF:review-needed]` — review and commit happen at flight end
