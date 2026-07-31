# Leg: credential-source-and-provider-mechanics

**Status**: completed
**Flight**: [Anthropic Plan Provider End-to-End](../flight.md)

## Objective

Make the `anthropic-plan` provider fully operational for inference: a self-resolving, single-flight credential source feeds fresh access tokens to every construction site (agents, connectors, `/test`, `/models`), tokens auto-refresh with rotation-safe write-back, terminal refresh failure surfaces as an actionable re-auth error end-to-end, and the provider passes the cross-provider conformance suites.

## Context

Ground truth from Leg 1 (flight log Leg Progress + handoff):
- `AnthropicProvider` now has a `_build_client(api_key)` seam (`the_one/llm/anthropic_provider.py:137` call site, `:156` definition); `AnthropicPlanProvider` overrides only that seam, takes `access_token` + `provider_config_id` constructor kwargs, and forces `api_key=None` post-construction so the env fallback can't flip auth mode. **`_before_request` does not exist yet** — this leg adds it (flight DD-4).
- Token persistence goes through `LLMProviderRepository.update_secrets(provider_id, secrets)` — independent of full-model `update()`/PUT-preserve. Keep using it.
- `anthropic_oauth.refresh_token()` returns a `TokenSet` and **keeps the old refresh token when the response doesn't rotate it**; managed-keys constants: `anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS` (aliased in `api.py` as `_PLAN_OAUTH_MANAGED_KEYS`; pending map `_plan_oauth_pending`).
- `oauth_active` rule (pinned by test): `access_token` AND `refresh_token` both present.
- Flight DD-3: self-resolving source (provider looks itself up by `provider_config_id`), process-wide registry with module-level accessor, asyncio-lock single-flight, **re-read-inside-lock adoption** (adopt newer stored tokens instead of refreshing — the two-process dev+installed pattern), eviction on provider update/delete/reset, typed re-auth-required error on terminal failure. Single-process lock guarantee is explicit and accepted.
- Flight DD-5: `/test` and `/models` get tokens from the credential-source accessor; live model listing with static-catalog fallback; `context_window_for` must be called with provider name `"anthropic"` (the catalog's `_TARGET_PROVIDERS` doesn't know `anthropic-plan`).

## Inputs

- Leg 1 landed (uncommitted on `flight/01-plan-provider-end-to-end`): `anthropic_oauth.py`, `anthropic_plan_provider.py` skeleton, `update_secrets()`, oauth endpoints, migration v33, registration complete.
- `/test` per-type branch chain in `the_one/interfaces/web/api.py` (anthropic arm at ~`api.py:4276`); `/models` chain (anthropic arm at ~`api.py:4451`) — locate by the `provider.type == "anthropic"` comparisons within the test/models handlers; line numbers have drifted since Leg 1's edits.
- Second `get_provider()` caller: `the_one/connectors/_inference.py` (~:215-231) — duplicates the `_PROVIDER_TYPE_MAP` lookup, wraps construction in `except Exception: logger.warning(...); return None` (silent-failure risk that motivated self-resolution).
- Conformance suites: `tests/test_llm_provider_cross_provider_conformance.py` (`PROVIDER_FACTORIES`), `tests/test_llm_provider_cross_provider_history.py`, `tests/test_llm_provider_tool_result_serialization.py`, `tests/test_llm_provider_user_content_projection.py`.
- Circular-import discipline: modules that transitively reach `db.repositories` are lazy-imported inside function bodies in `agent/factory.py` — the credential-source module must follow it.

## Outputs

- New `the_one/llm/plan_credentials.py` (name at implementer's discretion, referenced here as such): per-provider-config credential source + process-wide registry.
- `AnthropicProvider._before_request()` no-op hook, awaited at the top of `complete()` and `stream()`; `AnthropicPlanProvider` override that ensures a fresh token before every request.
- Typed re-auth-required error surfacing end-to-end (credential source → provider → agent-facing message; API → 4xx on `/test`).
- `DELETE /api/providers/{provider_id}/oauth` — reset-connection endpoint (clears managed keys via `update_secrets`, evicts credential source + pending entry); backend half of the Leg 3 reset control.
- Eviction wired into provider update/delete (and the new reset endpoint).
- `/test` and `/models` branches for `anthropic-plan` using the accessor; static-catalog fallback for `/models`.
- Conformance-suite parametrization for `anthropic-plan`; connector-path and two-config-independence tests.
- `_PROVIDER_TYPE_MAP` lifted into `the_one/llm/registry.py` (the code's own forward-note; deferrable per flight Acceptable Variations — record either way).

## Acceptance Criteria

- [x] **Credential source**: `get_credential_source(provider_id)` returns a process-wide per-id singleton whose `get_access_token()` (a) returns the stored token when not near expiry, (b) refreshes proactively when `token_expires_at` is within a 120s margin, (c) is single-flight — N concurrent callers during an expired-token window produce exactly ONE refresh HTTP call (asserted with a mocked endpoint and a call counter), (d) re-reads stored secrets inside the lock and ADOPTS a newer stored token instead of refreshing (asserted by mutating stored secrets between acquire and lock-entry in a test), and (e) persists rotated tokens via `update_secrets` so a fresh read sees them.
- [x] **Rotation safety**: after a refresh whose response rotates the refresh token, the stored `refresh_token` is the new one; when the response omits a new refresh token, the old one is preserved (delegating to `anthropic_oauth.refresh_token` semantics — pinned by test at the source level).
- [x] **Terminal failure**: a refresh rejected with an invalid-grant-style 4xx raises a typed re-auth-required error carrying the provider id; the source does NOT clear stored secrets (the operator may retry / re-auth; `oauth_active` semantics unchanged). The error's message names the provider and says to re-authenticate in Administration.
- [x] **Hook**: `AnthropicProvider._before_request()` exists as an awaited no-op at the top of both `complete()` and `stream()` (note: `stream()` is an async generator — the hook runs at first iteration, and the typed re-auth error therefore surfaces during iteration; this is correct, do not convert to an eager coroutine); existing API-key provider behavior is unchanged (existing anthropic suites green with no test edits beyond additions). `AnthropicPlanProvider._before_request()` obtains a token from its source and applies it via **in-place `client.auth_token` mutation** — design-review verified against anthropic SDK 0.96.0 (`_bearer_auth` property read per-request via `_build_headers`; nothing cached at construction); a unit test pins this premise against SDK upgrades by asserting the client's auth-header generation reflects the mutation without rebuilding.
- [x] **Provider without credentials**: an `anthropic-plan` provider whose config has no stored tokens raises the typed re-auth error at `_before_request` time (not a bare SDK auth error) — the message is actionable.
- [x] **Construction sites**: (a) `AgentFactory.create` builds a working plan provider passing `provider_config_id` (and no static `access_token`); (b) the `connectors/_inference.py` path constructs one successfully in a test with stored secrets fixture — and a companion test asserts that when the credential source raises re-auth-required at request time, the error is NOT swallowed into the constructor's `return None` path (construction succeeds; failure surfaces at call time); (c) `/test` for a plan provider returns success with a mocked live call and a fresh token from the accessor; when re-auth is required it follows the **established `/test` contract** (HTTP 200 + status field) with a distinct `status: "reauth_required"` value and an actionable detail — NOT a 4xx (deliberate alignment with the existing 200-on-provider-failure family; Leg 3's editor keys the re-auth affordance on `oauth_active` and may additionally branch on this status); (d) `/models` returns live models when the mocked call succeeds and falls back to the static Anthropic catalog entries when it fails — the fallback uses a NEW public enumeration accessor on `model_catalog.py` (e.g. `models_for(provider)`; the anthropic section is currently only reachable via private `_get_catalog()`), returns the full catalog section for `"anthropic"`, and resolves context windows via provider name `"anthropic"`.
- [x] **Eviction**: updating a provider via PUT, deleting it, and calling the new `DELETE /api/providers/{id}/oauth` reset endpoint each evict the cached credential source (next accessor call builds a fresh one — asserted by identity or by observing a re-read); reset additionally clears managed keys (subsequent GET: `oauth_active: false`) and evicts any pending verifier.
- [x] **Two-config independence**: two `anthropic-plan` rows with distinct stored tokens yield distinct sources with independent locks; refreshing one does not touch the other's stored secrets.
- [x] **Conformance**: `anthropic-plan` added to `PROVIDER_FACTORIES` in the cross-provider conformance suite ONLY — constructed with a static test token + dummy `provider_config_id`, patching `prov.client.messages.create/.stream` per the `make_anthropic` pattern (`tests/fixtures/scripted_transport.py:193`). The history/projection suites use direct `AnthropicProvider` fixtures exercising inherited code, and the serialization suite has no provider parametrization — they are covered by inheritance; record that reasoning in the flight log rather than parametrizing them redundantly.
- [x] **Map lift**: `_PROVIDER_TYPE_MAP` moved to `the_one/llm/registry.py` with `agent/factory.py` and `connectors/_inference.py` consuming it from there (module-load assert intact), OR a flight-log Deviation recording the deferral rationale.
- [x] Full unit suite green (`make test-unit`, ≥ Leg 1's 4071 passed / 0 failed), `make lint` + `make format-check` clean. *(4148 passed / 0 failed / 10 skipped in 354s; lint + format-check clean.)*

## Verification Steps

- Focused loop: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_plan_credentials.py tests/test_anthropic_provider.py tests/test_provider_api.py tests/test_llm_provider_cross_provider_conformance.py -x --timeout 30` (plus factory/connector test files as touched).
- Single-flight assertion: concurrency test with `asyncio.gather` over ≥5 callers and a counting mock endpoint.
- `make test-unit` at leg end; `make lint`; `make format-check`.

## Implementation Guidance

1. **Credential source module** first: dataclass/state (provider id, lock, cached secrets snapshot), module-level registry dict + `get_credential_source()` + `evict_credential_source()`. Lazy-import `LLMProviderRepository`/encryptor inside functions (factory's documented circular-import convention). Repository construction mirrors existing call sites (settings data dir + `get_encryptor`).
2. **Refresh flow inside the lock**: re-read stored secrets → if stored token differs from the snapshot that triggered refresh and is not near expiry, adopt it and return → else call `anthropic_oauth.refresh_token()` → **merge the new token set OVER the existing stored secrets** (never write `to_secrets()` wholesale — it omits None-valued keys and would silently drop stored `scope`/`token_type`, and a response missing `expires_in` would drop `token_expires_at` → refresh-every-request) → persist via `update_secrets` → return. Map invalid-grant/4xx to the typed re-auth error; network errors re-raise as their existing typed OAuth errors (transient — do not demand re-auth for a network blip).
3. **Hook**: add the no-op to `AnthropicProvider`, await it first in `complete()` and `stream()`; override in the plan provider. Spike the in-place `auth_token` mutation with a unit test before wiring (SDK-internal premise per DD-4).
4. **Factory + connectors**: the factory does NOT thread arbitrary kwargs — `AgentFactory.create` builds a fixed `provider_kwargs` dict (`factory.py:273-287`) and `connectors/_inference.py:222-228` has its own fixed list; add `provider_config_id` explicitly at BOTH sites (unconditional passing is safe — all five provider constructors accept `**kwargs` — or scope it to the plan type like `native_api`). Do the map lift early if taking it — both callers change anyway.
5. **API branches**: `/test` and `/models` arms for `anthropic-plan` next to the `anthropic` arms; acquire token via accessor with try/except re-auth → 200 + `status: "reauth_required"` per the established `/test` contract. Reset endpoint beside the other two oauth routes, reusing `_get_plan_provider_or_raise` (api.py:4123) for consistent 404/409 semantics; wire eviction into PUT/DELETE handlers, and ALSO evict in `/oauth/code` after a successful exchange (fresh sign-in over a cached source — one line, simpler than relying on re-read adoption). Test fixtures for plan rows need a valid `https` base_url (`anthropic-plan` is deliberately not URL-validation-skipped and `TYPE_DEFAULTS` lands in Leg 3).
6. **Conformance**: follow the existing anthropic entries' mocking pattern in `PROVIDER_FACTORIES`; construct with `access_token="conformance-token"` and a dummy `provider_config_id` (no source resolution needed when a static token is supplied — keep the Leg 1 kwarg as the test/back-door feed and document that precedence: explicit `access_token` wins over source resolution).
7. **Leg-end**: flight log entry (decisions: rotation strategy, map lift taken/deferred), leg status `landed`, no commit, signal `[HANDOFF:review-needed]`.

## Edge Cases

- **Concurrent terminal failure**: N callers waiting on one failed refresh must ALL receive the re-auth error (not one error + N-1 hangs).
- **Clock skew / missing `token_expires_at`**: treat missing/zero expiry as expired → refresh path (which may adopt or fail typed) rather than serving a possibly-dead token.
- **Explicit `access_token` kwarg precedence**: a provider constructed with a static token (tests, conformance) never consults the registry — `_before_request` short-circuits.
- **Reset while an agent chats**: source evicted mid-conversation → next `_before_request` builds a fresh source, finds no tokens, raises the actionable re-auth error (no crash loop).
- **Refresh response missing `expires_in`**: store a conservative short expiry rather than never-expiring.

## Files Affected

- `the_one/llm/plan_credentials.py` — new
- `the_one/llm/anthropic_provider.py` — `_before_request` no-op + await sites
- `the_one/llm/anthropic_plan_provider.py` — override, token application
- `the_one/llm/registry.py` — `_PROVIDER_TYPE_MAP` lift (if taken)
- `the_one/agent/factory.py` — pass `provider_config_id`; consume lifted map
- `the_one/connectors/_inference.py` — consume lifted map / thread kwarg
- `the_one/interfaces/web/api.py` — `/test` + `/models` arms, reset endpoint, eviction wiring
- `the_one/llm/model_catalog.py` — new public enumeration accessor for the static fallback
- Tests: `tests/test_plan_credentials.py` (new), `tests/test_anthropic_provider.py`, `tests/test_provider_api.py`, conformance suites, factory/connector tests

## Citation Audit

2026-07-28 (Flight Director): `anthropic_provider.py:137/156` (`_build_client` call/def) verified via grep post-Leg-1. `api.py` branch anchors (~4276 `/test` anthropic arm, ~4451 `/models` anthropic arm) located by `provider.type == "anthropic"` grep — drifted from pre-Leg-1 numbers, locate by symbol. `connectors/_inference.py:215-231` and conformance-suite paths carried from Architect review @ 91d82e4 (pre-Leg-1; Leg 1 did not touch those files).

---

## Post-Completion Checklist

**Batched-commit mode: do NOT commit at leg end.**

- [x] All acceptance criteria verified
- [x] Tests passing (`make test-unit` 4148/0/10), lint + format clean
- [x] Flight log Leg Progress entry written (incl. rotation-strategy and map-lift decisions)
- [x] Leg status set to `landed` (this file's header)
- [x] Signal `[HANDOFF:review-needed]` — review and commit happen at flight end
