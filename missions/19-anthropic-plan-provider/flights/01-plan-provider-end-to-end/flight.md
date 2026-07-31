# Flight: Anthropic Plan Provider End-to-End

**Status**: completed
**Mission**: [Anthropic Individual Plan Provider](../../mission.md)

## Contributing to Criteria

- [x] An operator can create an Anthropic individual-plan provider in Administration and complete authentication by signing in with their Anthropic account in a browser — no API key is ever entered. *(behavior-test-backed: `anthropic-plan-signin`)*
- [x] An agent bound to a plan provider completes chat turns — including streaming, tool use, and extended thinking — with parity to the existing Anthropic API-key provider. *(behavior-test-backed: `anthropic-plan-chat-parity`; extended thinking via a plan-provider variant of the existing `extended-thinking-tool-turn` spec, run at HAT)*
- [x] Plan credentials survive application restarts and are stored encrypted at rest, never appearing unmasked in API responses or logs. *(unit: repository test asserts raw DB column is ciphertext; API strip tests)*
- [x] Expired short-lived credentials are renewed automatically during normal operation, with no operator intervention. *(unit: credential-source refresh tests against mocked token endpoint)*
- [x] When renewal is no longer possible, the operator sees a clear re-authenticate affordance in Administration, and agents fail with an actionable error rather than silently. *(browser test: seeded revoked-token state renders re-auth affordance; unit: typed re-auth error path)*
- [x] Multiple plan providers (distinct Anthropic accounts) can coexist and be independently bound to different agents. *(integration test: two plan configs, independently keyed credential sources)*
- [x] The provider's connection test and model listing work in Administration, consistent with other provider types. *(behavior-test-backed: `anthropic-plan-signin` step 6, `anthropic-plan-chat-parity` step 1; unit: `/test` + `/models` branch tests per DD-5)*

---

## Pre-Flight

### Objective

Deliver the `anthropic-plan` provider type end-to-end: an operator signs in with an Anthropic Pro/Max account from Administration (PKCE OAuth, code-paste consent), tokens are stored encrypted on the provider config and auto-refreshed by a shared single-flight credential source, and agents bound to the provider chat with full parity to the API-key Anthropic provider. Closes all seven mission success criteria in one flight.

### Open Questions

- [x] Redirect-URI acceptance → see DD-1: code-paste consent is the primary flow; the loopback callback is not relied upon. Leg 1 opens with an empirical spike confirming the authorize-URL parameters and token-exchange shape; if the spike contradicts DD-1's premise, divert.
- [x] Model listing under plan tokens → see DD-5: live listing with static-catalog fallback.
- [x] Where `/test` and `/models` get their token → see DD-3: the module-level credential-source accessor; they do not construct tokens independently.
- [x] Connector-bound plan providers → in scope structurally (the self-resolving credential source makes `connectors/_inference.py` work without changes); covered by a unit test on the connector construction path. The `connector-inference-provider-config-roundtrip` behavior spec is NOT re-run at HAT (no changes to connector code).
- [x] Save-before-sign-in ordering → the provider row must be saved before sign-in; the editor enforces this (DD-7). The exchange endpoint persists tokens server-side — no second Save is needed for tokens.

### Design Decisions

**DD-1 — Auth flow: hand-rolled PKCE with code-paste consent, launched via frontend popup**
- The flow: the provider editor opens Anthropic's authorization URL via `window.open` (mirroring the MCP server editor's consent popup at `mcp-server-editor.js`), **and** renders the authorize URL as copyable text as a first-class fallback (popup blocked, or consent completed in a different browser). Consent lands on Anthropic's own code-display callback page (public well-known client ID, PKCE S256); the operator copies the displayed code and pastes it into the provider editor; the backend exchanges code + verifier at the token endpoint and stores the token set.
- Rationale: Anthropic's consumer OAuth uses a fixed public client with a pre-registered redirect-URI allowlist — an arbitrary-port loopback is not ours to register. Code-paste works regardless of local port and is less code (no callback-route generalization, no pending-flow state race). There is **no** "open system browser" backend path — the one `webbrowser.open` in the codebase is a desktop-shell startup fallback not reachable from the API; the frontend popup is the established precedent (note: MCP editor abandoned `postMessage` for polling due to COOP; we don't need either — the code comes back by paste, not by redirect). The copyable-URL fallback also keeps the consent page reachable by the browser-MCP apparatus at HAT.
- The MCP SDK's `OAuthClientProvider` is NOT reused — it is coupled to RFC 8414 discovery + dynamic client registration, which consumer OAuth doesn't do.
- Trade-off: one manual paste at connect time (rare operation) for a dramatically simpler, port-independent flow. Loopback auto-redirect is out of scope unless the Leg 1 spike shows it works with zero extra machinery.
- Empirical premise (spike-verified at Leg 1 start, before any migration/contract work): authorize/token endpoints, client ID, scopes, and code-paste callback behave as expected for a PKCE public client. Full exchange is verified with the operator's real account at HAT.

**DD-2 — Credential storage: encrypted `secrets` column on `llm_providers` (migration v33)**
- Add `secrets TEXT NOT NULL DEFAULT '{}'` to `llm_providers`, encrypted as a whole-dict Fernet blob via the existing `_encrypt_secrets_blob`/`_decrypt_secrets_blob` helpers (precedent: `mcp_sources`, `tool_configs`, `connectors`). Managed keys: `access_token`, `refresh_token`, `token_expires_at` (absolute unix epoch), `scope`, `token_type`.
- Migration follows the established table-rebuild ceremony: `DROP TABLE IF EXISTS llm_providers_new` prelude, `PRAGMA foreign_keys=OFF/ON` inside a single `executescript`, `INSERT OR IGNORE INTO schema_version` last, `CURRENT_VERSION` 32 → 33. The same rebuild regenerates the type CHECK from `PROVIDER_TYPES` (picking up `anthropic-plan`) — one migration covers column + type, which is why the full type-registration atom lands in the same leg (see Legs).
- API contract, all three directions: **create** forces `secrets = {}` regardless of client-supplied body (no POSTing token material); **read** strips `secrets` in `_provider_response` (which starts from `model_dump()` and would otherwise include it) and exposes an `oauth_active` boolean instead; **update** preserves managed keys from the existing row (strip-and-preserve, mirroring the MCP source contract at `api.py` ~1314). The existing `__MASKED__` api_key sentinel path is untouched.
- Migration tests: v32→v33 upgrade on a populated DB (including inserting an `anthropic-plan` row into the **migrated** DB, not just a fresh one — the consistency test's fresh-DB CHECK can't catch a missing upgrade path), fresh-DB, idempotent re-run; all `aiosqlite.connect` via `async with`.

**DD-3 — Refresh: self-resolving, process-wide, per-provider-config single-flight credential source**
- A credential-source registry keyed by provider-config id, with a module-level accessor (`get_credential_source(provider_id)`-style). The source owns token reads and refreshes behind an asyncio lock: proactive refresh within an expiry margin, single-flight so concurrent consumers never race a rotation, write-back through `LLMProviderRepository` after each successful refresh.
- **Self-resolving, not factory-injected**: `AnthropicPlanProvider` receives its provider-config id as a kwarg and looks up its source in the registry. This makes every construction site work uniformly — `AgentFactory`, the second `get_provider()` caller in `connectors/_inference.py` (which swallows construction errors and would fail *silently* under an injection-only design), and the `/test` + `/models` API branches (which call the accessor directly instead of constructing tokens inline).
- **Invalidation contract**: the registry evicts a source on provider update, delete, and reset-connection/re-sign-in (analogue: MCP's `_evict_all_for_source`). Additionally, the source re-reads stored secrets **inside the lock** before refreshing and adopts a newer stored token instead of refreshing — cheap insurance for the documented dev-instance + installed-app pattern (two processes sharing one SQLite file), where the asyncio lock alone cannot arbitrate.
- Single-process assumption is explicit: the lock guarantees single-flight within a process; cross-process safety relies on the re-read-and-adopt rule reducing (not eliminating) rotation races. Acceptable for a local single-operator app.
- When refresh fails terminally (refresh token expired/revoked), the source surfaces a typed re-auth-required error; the provider maps it to an actionable agent-facing error, and the API/UI expose the state as the re-authenticate affordance.
- Import discipline: the credential-source module imports `LLMProviderRepository` lazily inside function bodies (the factory's documented circular-import convention).

**DD-4 — Provider: `AnthropicPlanProvider(AnthropicProvider)` subclass, type `anthropic-plan`, via a `_before_request` hook**
- `AnthropicProvider` gains an explicit `async def _before_request(self) -> None` no-op hook, awaited at the top of both `complete()` and `stream()` — behavior-preserving for the API-key provider (satisfies the mission's no-change constraint). Rationale: the `AsyncAnthropic` client is built eagerly in a sync `__init__`, so there is no seam to `await` a refresh, and the only existing async pre-call hook (`_resolve_max_context_tokens_if_needed`) swallows all exceptions, which would silently eat the re-auth-required error.
- `AnthropicPlanProvider` overrides client construction (`AsyncAnthropic(auth_token=<access token>, default_headers={"anthropic-beta": "oauth-2025-04-20"})` — bearer + OAuth beta header replace `x-api-key`) and `_before_request` (ensure fresh token via its credential source; on rotation, update client auth). Whether rotation mutates `client.auth_token` in place or rebuilds-and-closes the client is a leg-level decision — if in-place, spike it first (SDK-internal assumption); if rebuild, close the old client (`aclose()` covers exactly one client).
- Everything else — `_build_kwargs`, streaming, thinking capture/replay, tool schema sanitization, temperature retry — is inherited. Mirrors the `OpenRouterProvider(OpenAIProvider)` precedent. The rule-of-three OpenAI-compat duplication lift is NOT triggered (not a `/v1`-shaped provider).
- `base_url` remains required on the config model; `anthropic-plan` is **not** added to `_URL_VALIDATION_SKIPPED_TYPES` (explicit decision), and its `TYPE_DEFAULTS` entry must carry the non-empty Anthropic API base URL — the editor force-submits `defaults.base_url` when the field is hidden, and the model requires it.
- Registry pip-extra error path: alias `anthropic-plan` → the `anthropic` extra (like the existing openrouter→openai special case), so a missing-dependency ImportError doesn't suggest installing a nonexistent `the-one[anthropic-plan]` extra.

**DD-5 — Model listing: live with static fallback**
- `/api/providers/{id}/models` for `anthropic-plan` attempts a live `models.list()` using a token from the credential-source accessor; on plan-token-specific failure, falls back to the static Anthropic entries in the model catalog so the Studio picker always has options. Context-window lookups pass provider name `"anthropic"` to `context_window_for` (the catalog's `_TARGET_PROVIDERS` doesn't know the new type string). Connection test (`/test`) makes a minimal authenticated call with a token from the same accessor.

**DD-6 — Verification apparatus: browser MCP + HTTP against the dev instance**
- Behavior tests drive the real Administration/Chat UI in a browser (chrome-devtools or goldfinch MCP — both registered on this device) against the dev-mode instance, with `curl` for HTTP observables and shell for the restart step (declared in the spec).
- Act path (audited): Administration and Chat are plain web surfaces served by FastAPI, reachable in any browser at the dev port — the pywebview shell is not required. The consent popup is reachable by the apparatus because DD-1 renders the authorize URL as copyable text (the apparatus can navigate to it in its own tab). Read path (audited): sign-in state is observable in the rendered editor (`oauth_active`-driven UI) and via `GET /api/providers/{id}` (`oauth_active` field, secrets stripped); chat output is observable in the rendered transcript.
- Both specs require a real Pro/Max account sign-in, which only the operator can perform → they run in the HAT leg with the operator present. Implementation legs carry unit/integration coverage with a mocked token endpoint.

**DD-7 — Sign-in UX ordering and persistence**
- *(Amended 2026-07-31, HAT step 6 operator feedback: the disabled-until-saved gate was awkward in practice. The affordance is now enabled in create mode and performs an auto-save-then-start — the editor creates/saves the row first, then calls `/oauth/start` on the new id. The backend requirement below is unchanged; only the UX ordering moved from manual to automatic.)*
- ~~The sign-in affordance is disabled (with a hint) until the provider row is saved~~ The sign-in flow ensures the row is saved before starting — start-auth and submit-code are `/api/providers/{id}/...` endpoints and need the row to exist (the MCP editor solved the same ordering with its post-create path). The submit-code exchange persists tokens server-side to the saved row; the operator does not need a second Save for credentials, and the editor must not present an unsaved-changes trap after connecting. `anthropic-plan` inherits the reasoning-capable config surface in `TYPE_DEFAULTS` (`showThinkingEnabled`, `showReasoningEffort` as applicable to the anthropic type) — without it, extended-thinking parity would be unreachable from the UI.

### Prerequisites

- [x] Mission 19 approved and active.
- [x] Schema at v32; migration ceremony precedent in `the_one/db/schema.py`.
- [x] Encryption infrastructure (`Encryptor`, `_encrypt_secrets_blob`) present in `the_one/db/repositories.py`.
- [x] Browser apparatus available (chrome-devtools / goldfinch MCP registered); Playwright browser suite runnable via `make test-browser`.
- [ ] Operator has a Claude Pro/Max account and can complete a browser sign-in — needed at HAT, not before.
- [ ] Dev instance runnable (`make restart`, dev port) at HAT time; no port conflicts expected (no new network services are introduced by this flight).

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified (HAT-time items flagged)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

New module `the_one/llm/anthropic_oauth.py` (or similar) implements the PKCE flow: authorize-URL builder, code+verifier exchange, refresh call — plain `httpx` against fixed endpoints, ~200 lines, no MCP SDK. Migration v33 rebuilds `llm_providers` with the `secrets` column and the type CHECK regenerated from `PROVIDER_TYPES`; because `models.py` and `factory.py` carry module-level asserts pinned to that tuple, the **type-registration atom is indivisible and lands in Leg 1**: tuple + `Literal` + migration + `_PROVIDER_TYPE_MAP` entry + `registry.py` lazy-loader entry + an `AnthropicPlanProvider` skeleton + the 7-member update to `test_provider_types_consistency.py`. Leg 2 adds the mechanics: self-resolving credential source with eviction + re-read-inside-lock, the `_before_request` hook pair, refresh/rotation, typed re-auth error, `/test` + `/models` branches via the accessor, catalog passthrough, conformance parametrization, and (adopting the code's own forward-note, now that a third caller exists) lifting `_PROVIDER_TYPE_MAP` into `registry.py`. Administration UI mirrors the MCP server editor's OAuth UX (popup + copyable URL + paste-code field, connected/re-auth/reset states), honoring seed-before-overlay for partial-field saves.

Carry-forwards from prior debriefs applied to this flight:
- Any migration test using `aiosqlite.connect` must use `async with` (M18 F04 flake-fix convention).
- Admin-editor legs ship with `tests/browser/test_flow_provider_editor.py` green (M16 F09 discipline).
- `provider-editor.js` edits invalidate the `system-provider-config` **and** `save-preserves-config` behavior specs — both re-run at HAT (M17 F07 cite-vs-rerun rule).
- If any leg touches `the_one/llm/base.py`, fix the bare `assert` in `ImageContent.__post_init__` (base.py:77) in passing (M16 F12 action item).
- Unit-suite baseline: ~3997 passed / ~338s; budget accordingly, no new slow suites expected.

### Checkpoints

- [ ] Spike confirms PKCE authorize/token parameters and code-paste consent shape (Leg 1 start, **before** migration/contract work — this is the flight's divert gate)
- [ ] Migration v33 applies cleanly to a populated v32 DB (including inserting an `anthropic-plan` row post-migration) and a fresh DB; secrets round-trip encrypted; raw column asserted non-plaintext
- [ ] Type-registration atom lands green in one commit: consistency test passes with 7-member set; suite imports cleanly
- [ ] Token exchange + refresh + single-flight + re-read-adopt pass unit tests against a mocked token endpoint
- [ ] Provider passes cross-provider conformance suites; connector-inference construction path covered; two-config independence test green
- [ ] Admin UI sign-in flow complete; browser suite green including seeded re-auth-affordance test
- [ ] Behavior tests pass live at HAT with a real account

### Adaptation Criteria

**Divert if**:
- The Leg 1 spike shows the code-paste consent flow is unavailable or the token endpoint rejects PKCE public-client exchange — the auth-flow design decision reopens (return to planning).
- Plan tokens are rejected by the inference endpoint despite correct headers — the mission premise itself is at risk; stop and consult the operator.

**Acceptable variations**:
- Loopback auto-redirect added alongside code-paste if the spike shows it works with zero extra machinery.
- Exact endpoint paths/scopes discovered at spike differing from planning assumptions (record in flight log).
- Static-catalog-only model listing if live listing proves unreliable under plan tokens (DD-5 fallback becomes primary; record as deviation).
- In-place `client.auth_token` mutation vs rebuild-and-close on rotation (leg-level, spike if in-place).
- Deferring the `_PROVIDER_TYPE_MAP` lift into `registry.py` if it balloons Leg 2 (record as deviation; it is an improvement, not a requirement).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `oauth-foundation-and-registration` - PKCE spike (first task; **hard stop** — if the spike contradicts DD-1, divert before any migration/contract work begins; the leg spec must restate this), PKCE flow module, migration v33 (secrets column + regenerated CHECK), indivisible type-registration atom (tuple, Literal, factory map, registry loader entry + pip-extra alias, `AnthropicPlanProvider` skeleton, consistency-test 7-member update), repository secrets encryption with strip-on-create / strip-in-response / preserve-on-PUT + `oauth_active`, start-auth + submit-code endpoints (exchange persists tokens), migration + contract unit tests (incl. ciphertext-at-rest assertion)
- [x] `credential-source-and-provider-mechanics` - self-resolving credential-source registry (single-flight, eviction on update/delete/reset, re-read-inside-lock adoption), `_before_request` no-op hook in `AnthropicProvider` + plan override, refresh/rotation strategy, typed re-auth-required error path end-to-end, `/test` + `/models` branches via accessor with catalog passthrough + static fallback, conformance-suite parametrization, connector-inference construction test, two-config independence test, `_PROVIDER_TYPE_MAP` lift into registry
- [x] `admin-ui-signin` - provider editor sign-in UX (save-gated affordance, popup + copyable URL, paste-code field, connected/re-auth/reset states, no unsaved-changes trap), `/providers/types` literal-list entry + its pinned tests (`test_provider_api.py:2024-2043`, deferred from Leg 1 so the type doesn't appear in the picker before editor support exists), `TYPE_DEFAULTS` (incl. base_url + thinking/reasoning surface), badges across ALL token sites (tokens.css both theme blocks, `tests/browser/design_tokens.py` mirror, `_BADGE_INK_PAIRS` a11y parametrization, admin.css, providers-grid `KNOWN_BADGE_TYPES`, status-section swatch), testid registry, browser tests (incl. seeded revoked-token re-auth affordance), docs updates
- [x] `uat-and-alignment` *(HAT)* - Guided session with the operator: live sign-in with a real Pro/Max account, run `/behavior-test anthropic-plan-signin` and `/behavior-test anthropic-plan-chat-parity`, run the plan-provider variant of `extended-thinking-tool-turn` (add the Variant entry to that spec at HAT prep), re-run `system-provider-config` and `save-preserves-config` (provider-editor.js changed), fix issues iteratively until the operator is satisfied

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (`make test` green; browser suite green)
- [x] Documentation updated (CLAUDE.md LLM-layer note, testid registry)

### Verification

- Unit/integration: migration tests (v32→v33 populated-DB upgrade + post-migration `anthropic-plan` insert, fresh-DB, idempotent re-run), OAuth flow tests against mocked endpoints, credential-source tests (single-flight, eviction, re-read-adopt, terminal re-auth error), ciphertext-at-rest repository test, conformance suites parametrized for `anthropic-plan`, provider API tests (strip-on-create/read, preserve-on-PUT, `oauth_active`), connector-inference construction test, two-config independence test, `test_provider_types_consistency.py` (consider also pinning the `/providers/types` literal list and the `/test` + `/models` branch fallthroughs).
- Browser: `make test-browser` including `test_flow_provider_editor.py` and the seeded revoked-token re-auth affordance test.
- Live (HAT): `/behavior-test anthropic-plan-signin`, `/behavior-test anthropic-plan-chat-parity`, `extended-thinking-tool-turn` (plan-provider variant), `system-provider-config` and `save-preserves-config` re-runs — all green with a real account.
