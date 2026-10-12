# Sortie: Claude Plan (Token) provider

**Status**: in-flight

## Charter

### Outcome
An operator can add a "Claude Plan (Token)" model provider by pasting a token from `claude setup-token` and have agents chat on their Claude subscription with no sign-in flow; the existing OAuth provider is relabelled "Claude Plan (OAuth)" and otherwise unchanged.

### Why Now
Claude can now mint one-year subscription tokens (`claude setup-token`). Today the only path to a subscription is the OAuth sign-in (popup or URL + code paste).

### Success Criteria
- [ ] Library › Model providers' Add flow offers both "Claude Plan (OAuth)" and "Claude Plan (Token)"; creating a Token provider asks only for the token (no sign-in), and its editor shows when the token was added and when it expires around.
- [ ] An agent on a Token provider completes a streamed chat turn against the live API using a real `setup-token` token.
- [ ] The provider's Test and the model picker work with that token (Test reports ok; the picker lists models).
- [ ] The token is stored encrypted and never returned unmasked by any API response; existing `anthropic-plan` providers and their OAuth tokens keep working through the schema migration.

### Constraints
- `anthropic-plan` keeps its slug; existing rows are not migrated or altered.
- The operator's real test token is never written to any tracked file, flight artifact, log, run log or fixture; it is used only against a dedicated dev instance (port ≥ 8486, scratch data dir) and revoked by the operator when the sortie completes.
- Automated tests use synthetic tokens; only the live verification uses the real one.

---

## Pre-Flight

### Objective
Add a second Claude-subscription provider type, `anthropic-plan-token` ("Claude Plan (Token)"), that authenticates with a long-lived token pasted from `claude setup-token` instead of an OAuth sign-in. The token is the same consumer-OAuth bearer credential the OAuth type obtains (bearer `Authorization` + `anthropic-beta: oauth-2025-04-20`), minus the refresh token, so the request path is reused unchanged: the work is a new type wired through the type list, a v44 `llm_providers` rebuild, the factory, the API's create/update/`/test`/`/models` paths and the provider editor, plus a server-stamped "token added" date that drives an "expires around" line in the editor. The existing `anthropic-plan` type is relabelled "Claude Plan (OAuth)" and is otherwise untouched.

### Open Questions
- [x] One type with an auth-mode switch, or two types? → two types (operator; charter)
- [x] Slug and labels → `anthropic-plan-token`, "Claude Plan (Token)"; `anthropic-plan` relabelled "Claude Plan (OAuth)" (operator; charter)
- [x] Expiry presentation → a line in the editor with warning states (within 30 days; past), editor only (operator; DD6)
- [x] Leg shape → one build leg plus a live-verification leg (operator)
- [x] Token validation strictness → reject API keys (`sk-ant-api…`) only (operator; DD4)
- [x] Can a `setup-token` token call `GET /v1/models`, and which models will it run? → yes, 200 with 14 models; only `claude-haiku-4-5` ran, every Sonnet/Opus/Haiku 5.5 tried returned 429 `rate_limit_error` "Error" (premise check 2026-10-12, flight log; DD5)
- [x] What does the app do about the bare-429 model block? → a clearer error for both plan types (operator; DD10)

### Design Decisions

**DD1 — A new type, `anthropic-plan-token`, reusing `AnthropicPlanProvider`'s bearer path through a thin subclass.**
- `PROVIDER_TYPES` (`db/_provider_types.py`), the `LLMProviderConfig.type` Literal (`db/models.py`), `PROVIDER_TYPE_MAP` and `_try_load_builtin` (`llm/registry.py`, extra alias `anthropic`) all gain `anthropic-plan-token`. `tests/test_provider_types_consistency.py` pins the four in sync, including the live CHECK constraint.
- `AnthropicPlanTokenProvider(AnthropicPlanProvider)` in `llm/anthropic_plan_provider.py`, `name = "anthropic-plan-token"`, registered under that name. It is constructed with `access_token=<stored api_key>`, so the parent's `_before_request` short-circuits (`anthropic_plan_provider.py:94`) and the credential-source registry is never consulted. Its own `_before_request` raises a typed `PlanTokenMissingError` (actionable: "paste a token in Library › Model providers") when no token is stored, rather than letting the SDK send an empty bearer.
- **Rejected-token translation:** one wrapper, in `AnthropicPlanProvider` (DD10), calls an overridable hook `_translate_plan_error(exc) -> Exception | None` before the first chunk. The token subclass overrides it: `anthropic.AuthenticationError` (401) → `PlanTokenRejectedError` naming the provider and the fix ("the token was rejected; it may have expired or been revoked; run `claude setup-token` and paste the new token"), then defers to the base hook. A 403 passes through unchanged. The subclass does not wrap `complete()`/`stream()` itself.
- The typed errors (`PlanTokenMissingError`, `PlanTokenRejectedError`, `PlanRequestRefusedError`) are plain `Exception` subclasses in `llm/anthropic_plan_provider.py` (not `APIStatusError`, whose constructor needs `response=`/`body=`); their `str()` is what the chat shows (`"Agent error: {exc}"`, `interfaces/web/app.py::_process_and_broadcast`). Raised `from` the SDK error.
- `agent/factory.py:364`: a sibling branch, `elif registry_name == "anthropic-plan-token": provider_kwargs["access_token"] = provider_config.api_key`. No `provider_config_id` is passed (the token type has no credential source).
- Rationale: the runtime path is already proven by the OAuth type; a subclass keeps `name` honest (telemetry, errors) and keeps token-specific error translation out of the OAuth type.
- Trade-off: a third Anthropic class in the hierarchy.

**DD2 — The token lives in the encrypted `api_key` column, with the existing mask and preserve contract.**
- `llm_providers.api_key` is already Fernet-encrypted (`db/repositories.py:2855`, `encrypt_optional`), masked on every response (`api.py::_mask_api_key` → `_emit_mask`, `***...{tail4}`), and preserved on a PUT that sends `__MASKED__` or a mask shape (`api.py::_looks_masked`, `update_provider`). The token type uses all three unchanged.
- **Create:** `create_provider` refuses (422, one plain sentence) a token-type body with no `api_key`. **Update:** after masked-key resolution, a token-type row whose resolved `api_key` is `None` is refused the same way. This covers a type change from `anthropic-plan` (which has no `api_key`) into the token type without a token.
- **"Resolved" means after validation:** the resolved type and key are `updated.type` / `updated.api_key`, after the `model_dump() | data → model_validate` round-trip (`api.py` ~l.5117-5119), so an omitted `api_key` resolves to the stored key and the `api_key` strip validator (`models.py:48-67`) has run. The DD2 missing-token check, the DD4 prefix check and the DD3 stamp comparison against `existing.api_key` all run on `updated`, before `repo.update`.
- **Every** update whose resolved type is the token type runs DD4 on the resolved key.
- **A type change into the token type** (`existing.type != "anthropic-plan-token"`) must carry a freshly pasted token in the request: an omitted or masked `api_key` is refused (422, "Paste a token from `claude setup-token`"), so another type's key never masks through as a token.
- `/test` and `/models` check for a missing token before building a client: with `auth_token=None` the SDK would fall back to `ANTHROPIC_AUTH_TOKEN` from the environment.
- `base_url` is force-defaulted by the editor to `https://api.anthropic.com` as for `anthropic-plan`; the URL-safety check applies (the type is not in `_URL_VALIDATION_SKIPPED_TYPES`).
- Rationale: no new secret storage, and the masked-key contract every editor already speaks.

**DD3 — The server stamps when the token was set, in `secrets`, and exposes it read-only.**
- `secrets["token_set_at"]` (ISO-8601 UTC) is written by the server only, under its own constant `_PLAN_TOKEN_MANAGED_KEYS = ("token_set_at",)` in `api.py` (NOT added to `anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS`, which the OAuth sign-out path and the credential source also use).
- **Pin:** `update_provider`'s managed-keys loop (`api.py` ~l.5101-5110) rebuilds `secrets` from the request and would drop any key it does not pin; the editor's PUT carries no `secrets` (`provider-editor.js:1078`). The loop therefore pins `_PLAN_TOKEN_MANAGED_KEYS` from `existing.secrets` too, so a PUT that omits `secrets` keeps the stamp and a client-sent value never seeds or overwrites it.
- **Stamp** (on `updated`, DD2), written with `now_iso()` (`db/models.py:15`, the `created_at`/`updated_at` format), when the resolved type is the token type and any of: the stored type differs (a type change into the token type), the resolved key differs from the stored key, or no stamp exists. A re-paste of the identical token keeps the old stamp. Create of a token-type row always stamps.
- **Type changes out of a plan type (DD11)** are handled in the same block.
- `_provider_response` adds two keys, present on every row, non-null only when `type == "anthropic-plan-token"`: `token_set_at` and `token_expires_around` (set + `PLAN_TOKEN_LIFETIME_DAYS = 365`, one constant beside `OAUTH_BETA_HEADER`). `oauth_active` is gated on `type == "anthropic-plan"` (today it reads secrets regardless of type, `api.py:4949-4951`).
- Why `secrets` and not `config`: the editor rebuilds `config` from the form on every save (`provider-editor.js` save path ~l.1078), so a stamp in `config` would be overwritten or forgeable; `secrets` is already server-owned and stripped from every response.
- "Around" because the token is opaque: the paste date is the closest observable to when `claude setup-token` minted it.
- Trade-off: a pre-existing row of this type cannot exist (new type), so there is no back-fill case; a row whose type is changed into the token type gets its stamp at that update (the stored-type-differs rule).

**DD4 — Token validation: reject API keys only.**
- On create and on every update whose resolved type is the token type (DD2), a resolved `api_key` starting with `sk-ant-api` is refused (422): "That is an Anthropic API key. Use the Anthropic provider type for API keys; Claude Plan (Token) takes a token from `claude setup-token`." Any other non-empty string is accepted, so a future change to the token format does not break saving (operator).
- The 422 detail never echoes the submitted value (`include_input=False` precedent, squawks 0112/0081).

**DD5 — `/test` and `/models` for the token type (premise verified).**
- `/models`: with no stored token, serve the static catalog without a live call. Otherwise a branch mirroring `anthropic-plan`'s (`api.py` ~l.5579-5612) with the stored token through `_plan_bearer_client(anthropic, provider.api_key)`, falling back to the static Anthropic catalog on any failure, context windows via provider name `anthropic`.
- `/test`: `models.list()` with the stored token; `anthropic.AuthenticationError` → `{"status": "error", "detail": <the DD1 rejected-token sentence>}`; other `AnthropicError` → `{"status": "error", "detail": str(e)}`; no token → the DD2 sentence. The HTTP-200-with-status contract of the other branches is kept.
- **Premise verified (2026-10-12, operator's token, flight log):** `GET /v1/models` with bearer + `anthropic-beta: oauth-2025-04-20` + `anthropic-version` returns 200 and 14 model ids, so `models.list()` is a valid `/test` probe and the live `/models` listing works; no inference fallback probe is needed. A 1-token `messages.create` to `claude-haiku-4-5` returned 200 through the same headers the OAuth type sends, so the request path is reuse, not new (the Divert criterion did not fire).

**DD6 — The editor: token field, no sign-in, expiry line.**
- `providers-section.js` `TYPE_DEFAULTS` gains `'anthropic-plan-token': { base_url: 'https://api.anthropic.com', showBaseUrl: false, showApiKey: true, showThinkingEnabled: true, showReasoningEffort: true, apiKeyLabel: 'Token', apiKeyPlaceholder: 'sk-ant-oat01-…', apiKeyHelp: 'Run claude setup-token in a terminal and paste the token it prints. It lasts about a year.' }`. No `showPlanSignIn`.
- `provider-editor.js`: the API-key row's label, placeholder and a help line read `apiKeyLabel`/`apiKeyPlaceholder`/`apiKeyHelp` (defaults "API Key", "sk-...", none), and the type-change handler (~l.747-766) updates them with `textContent`/`setAttribute`, so switching type in create mode relabels the field. No new `innerHTML` sink: `tests/test_ui_guards.py`'s frozen list for `provider-editor.js` (~l.107-114) does not change.
- **Expiry line** (edit mode, token type, `token_set_at` present), testid `provider-token-expiry`, built with DOM APIs under the token field: "Token added {Mon D, YYYY} · expires around {Mon D, YYYY}". Within 30 days of `token_expires_around` it gains a warning style and reads "Expires around {date}. Run claude setup-token and paste a new token."; after it, "This token may have expired (around {date}). Run claude setup-token and paste a new token." Dates are formatted in the operator zone by a new `App.time.formatDate(d)` (tested zone-aware in `tests/browser/test_ui_time_contract.py`, one UTC instant near midnight read in two zones on either side of the date line; documented in `the_one/agents.md` "`App.time` (M28 F2)") → "Oct 12, 2026" in `time.js` (the sanctioned date module; avoids a third `MONTHS` copy beside `rules-notes-tab.js:526` and `chats-list.js:58`, which are left as they are), so no `Date` getters appear outside `time.js` (`tests/test_time_getters_static.py`); the state is chosen by comparing `Date.parse(token_expires_around)` with `Date.now()`, through a pure helper `App.studio.planTokenExpiry(setAtIso, expiresIso, nowMs)` → `{state: 'ok'|'soon'|'past', text}` so the thresholds are testable without a clock: `past` when `nowMs >= expiresMs`; else `soon` when `expiresMs - nowMs <= 30 * 86400000`; else `ok`. Tested exactly at both edges.
- **Refresh after Save:** an edit-mode Save does NOT re-mount (`providers-section.js:166` re-renders only on create; `provider-editor.js` `performSave` edit branch ~l.866-886 rewrites only title and subtitle, and its `provider` closure stays stale). So a `renderTokenExpiry(container, row)` helper is called at mount and again in the edit branch of `performSave` with the PUT response row; it keeps the last saved row locally, hides the line when `row.type` is not the token type, and re-renders from the kept row when the type select returns to the token type. **Browser test apparatus:** `page.route`-patch the provider row's `token_set_at`/`token_expires_around` to an older date for the mount, then paste a new token and save through the real PUT, and assert the line now shows today's date (the line is day-granular, so an unpatched create-then-edit would show the same date). The re-stamp rules are covered by unit tests.
- The expiry line hides when the type select moves away from the token type in edit mode. The help line is tied to the input with `aria-describedby`, cleared when the new type has no `apiKeyHelp`.
- The registry (`docs/ui-testid-registry.md`) gains `provider-token-expiry`.

**DD7 — Labels and badge.**
- `/providers/types` (`api.py:5024`): `anthropic-plan` → "Claude Plan (OAuth)"; new `{"value": "anthropic-plan-token", "label": "Claude Plan (Token)"}` directly after it. `tests/test_provider_api.py`, `tests/browser/test_flow_provider_plan_signin.py`, `README.md` and `tests/behavior/extended-thinking-tool-turn.md` follow the relabel (6 references today).
- Badge: `--badge-anthropic-plan-token` / `--badge-ink-anthropic-plan-token` in both theme blocks of `tokens.css`, the same terracotta and ink as `anthropic-plan` (same subscription family; the badge text, the type slug, tells them apart); `.badge--anthropic-plan-token` in `components.css`; `BADGE_KINDS` in `ui/feedback.js`; `KNOWN_BADGE_TYPES` in `studio.js:593`; the contrast audit rows in `tests/test_design_tokens_a11y.py` (~l.1177, ~l.1329) and `tests/browser/design_tokens.py`; the kind counts in `tests/test_ui_badge_kinds.py::test_badge_kind_count` (15 → 16) and `tests/browser/test_ui_choice_contract.py:345` (`"kinds": 15`); `REASONING_CAPABLE_TYPES` in `tests/test_admin_reasoning_effort_field.py`; `test_provider_types_tuple_has_expected_members`; the `/providers/types` counts `test_returns_6_types_when_dev_mode_off` / `test_returns_7_types_when_dev_mode_on` (`tests/test_provider_api.py` ~l.2823, 2852) become 7/8 and are renamed.
- `README.md:145`'s stale "Settings › Providers" (since sortie 02) becomes Library › Model providers, and `README.md:157`'s provider table gains a Claude Plan (Token) row (not just the relabel). `the_one/agents.md`'s "adding a provider type" checklist (~l.1699-1705, which still names `admin.js` and the admin badge) is brought current while the docs are edited. The admin-scoped `.admin-provider-badge--*` rules are not extended (admin no longer hosts providers since sortie 02).

**DD8 — Migration v44: rebuild `llm_providers` so the CHECK admits the new type.**
- `CURRENT_VERSION` 43 → 44. A `version < 44` block repeats the v33 ceremony (`schema.py` ~l.1983-2037): `executescript` with `PRAGMA foreign_keys=OFF` in the same script (`agents.provider_config_id` references the table), `DROP TABLE IF EXISTS llm_providers_new` prelude, CREATE with `CHECK (type IN ({_PROVIDER_TYPES_SQL}))` and the current column set, and `INSERT INTO llm_providers_new SELECT` of **every** column including `secrets` (v33 did not copy `secrets` because it was adding it; v44 must, or every OAuth token set is lost). `INSERT OR IGNORE INTO schema_version` last. Same defensive skip when the table is absent.
- `SCHEMA_V1` and the v12/v33 rebuilds (`schema.py` ~l.455-493, ~l.1983-2037) already render `_PROVIDER_TYPES_SQL`, so a fresh database admits the type from creation and v44 is a no-op rebuild for it.
- The `CURRENT_VERSION == 43` pins in `tests/test_db_migration.py` (~l.4988, 5344, 5490) move to 44.
- Tests (`tests/test_db_migration.py`, one of the three files allowed to call `ensure_schema` directly): a v43 database with an `anthropic-plan` row carrying encrypted `secrets` and an agent referencing it migrates to v44 with the row, its decrypted secrets and the agent's `provider_config_id` intact, and then accepts an `anthropic-plan-token` insert; a crash-between-CREATE-and-RENAME retry is idempotent.
- Rationale: SQLite cannot alter a CHECK; this is the established path for `llm_providers` (v6, v12, v33).

**DD9 — The real token never enters a tracked file or an agent transcript.**
- Automated tests use synthetic tokens (`sk-ant-oat01-test…`) and stubbed SDK clients.
- The live behavior test (`anthropic-plan-token-chat`) reads the token only through a shell command that reads the operator's file (`python3` reading the path) and posts it to the dev instance's `POST /api/providers`; no agent types, prints or quotes it. The UI paste path is covered by browser tests with a synthetic token.
- The dev instance runs on port 8487 with a scratch data directory outside the repo; the operator revokes the token at sortie completion.

**DD10 — A clearer error when a plan rejects a request with a bare 429, for both plan types.**
- Observed (premise check): a plan token gets `429 {"type":"error","error":{"type":"rate_limit_error","message":"Error"}}` for every model except `claude-haiku-4-5`. It reads as a rate limit and says nothing. The OAuth type's live run recorded the same block (`tests/behavior/anthropic-plan-chat-parity.md`, "Sonnet/Opus blocked account-side"). This is Anthropic's restriction on subscription tokens in third-party apps; the app does not work around it (no imitation of another client's identity or prompt).
- **One wrapper**, in `AnthropicPlanProvider` (so both plan types): `complete()` and `stream()` are overridden with the parent's exact signature (`messages, tools=None, temperature=0.0, max_tokens=16384, *, enable_thinking=None`) to call the parent inside `try`; `stream()` iterates the parent through `async with contextlib.aclosing(super().stream(...)) as it:` so an early `aclose()` by the consumer closes the inner stream promptly. The catch is `anthropic.AnthropicError` only, so `PlanTokenMissingError` and `ReauthRequiredError` from `_before_request` pass through untouched; and on an SDK exception call `self._translate_plan_error(exc)`; a non-`None` result is raised `from exc`, otherwise the original propagates. `stream()` translates only before its first yielded chunk (a `yielded` flag, as the parent's `yielded_any`), and after a chunk the original error propagates. The parent catches only `BadRequestError` and `TypeError` (`anthropic_provider.py` ~l.332, 349, 425, 441), so `RateLimitError`/`AuthenticationError` reach the wrapper untouched.
- **The base hook** maps `anthropic.RateLimitError` to `PlanRequestRefusedError` **only when** `exc.body` is a `dict` whose `body["error"]` is a `dict` with `message == "Error"` (`isinstance` guards: `body` may be a `str` or `None`). It must not read `exc.message`/`str(exc)`, which are `"Error code: 429 - {…}"` (`anthropic/_base_client.py:425`). Message: "Your Claude plan didn't allow this request to {model}. It may be a usage limit, or this model may not be available to plan tokens in third-party apps. Try another model; older Haiku models are the most likely to work." (The premise check had `claude-haiku-5-5` refused too, so "a Haiku model" would be wrong.) A 429 with any other message passes through unchanged.
- The SDK retries a 429 twice by default (`_base_client.py:803-830`), so the refusal arrives after about three requests and a few seconds. Accepted; no retry change.
- Charter amendment (operator, 2026-10-12): the OAuth type gains this error text; its behaviour is otherwise unchanged.
- Trade-off: matches on an undocumented message string. If Anthropic changes it, the bare error simply comes through as today; nothing breaks.

**DD11 — Type changes: pin by the resolved type.**
- The editor's type select is enabled in edit mode (`provider-editor.js:197-205`), so a provider can change type.
- **Rule, on `updated.type` (DD2):** `update_provider` pins the OAuth-managed keys (`_PLAN_OAUTH_MANAGED_KEYS`) from `existing.secrets` **only when** the resolved type is `anthropic-plan`, and the stamp (`_PLAN_TOKEN_MANAGED_KEYS`) only when it is `anthropic-plan-token`; otherwise both are dropped. This also cleans up a legacy non-plan row that still carries OAuth keys. The credential source is evicted after every update already.
- **Into `anthropic-plan`:** `api_key` is forced to `None`. The OAuth type never uses it (`_build_client` ignores it), and the editor would otherwise send the hidden token field's `__MASKED__` (`provider-editor.js:1062-1077`) and leave the token stored, invisible and unclearable.
- **Into `anthropic-plan-token`:** a freshly pasted token is required (DD2), then DD4 and the DD3 stamp apply.
- Rationale: a subscription credential is never left behind under a type that does not use it.
- Unit tests cover each direction (`anthropic-plan` ↔ `anthropic-plan-token`, `anthropic` → token with a masked key refused, token → `anthropic-plan` clears the key).

### Citation Audit

Verified against the working tree at `cd7c7f6`:

| Citation | Status |
|---|---|
| `llm/anthropic_plan_provider.py::AnthropicPlanProvider._before_request` — returns early when `self._access_token is not None`, never touching the credential source | verified |
| `llm/anthropic_plan_provider.py::_build_client` — bearer `auth_token`, `api_key=None` forced, `anthropic-beta: oauth-2025-04-20` default header | verified |
| `llm/anthropic_provider.py::complete` / `stream` — both await `_before_request()` first; `stream` is an async generator wrapping `_stream_inner` in try/except | verified |
| `agent/factory.py:364` — plan-type kwarg scoping by `registry_name` | verified |
| `db/repositories.py:2855,2902,2918` — `api_key` encrypted with `encrypt_optional` / decrypted with `decrypt_optional` | verified |
| `interfaces/web/api.py::update_provider` — masked key → existing key; `_PLAN_OAUTH_MANAGED_KEYS` pinned from stored row; `model_dump()|data → model_validate` round-trip; `evict_credential_source` after update | verified |
| `interfaces/web/api.py::create_provider` — forces `secrets = {}`; 422 with `include_input=False` on validation error | verified |
| `interfaces/web/api.py::_provider_response` — strips `secrets`, adds `oauth_active` (access AND refresh token) | verified |
| `interfaces/web/api.py` `/test` (~l.5370) and `/models` (~l.5579) — `anthropic-plan` branches; `/models` falls back to `models_for("anthropic")` on any exception | verified |
| `db/schema.py` — `_PROVIDER_TYPES_SQL` rendered into `SCHEMA_V1` and the v33 rebuild; v33 copies columns without `secrets`; `CURRENT_VERSION = 43` | verified |
| `tests/test_provider_types_consistency.py` — pins Literal, `PROVIDER_TYPE_MAP` and the live CHECK against `PROVIDER_TYPES` | verified |
| `static/js/areas/studio/providers-section.js:57-63` — `TYPE_DEFAULTS` keyed by type, `showApiKey`/`showPlanSignIn` flags | verified |
| `static/js/areas/studio/provider-editor.js:216-223, 747-766` — API-key row built in the HTML string; type change toggles rows by class | verified |
| `tests/test_ui_guards.py:107-114` — frozen `innerHTML` sinks for `provider-editor.js` | verified |
| `static/js/time.js::parts` — zone-aware `{year, month, day…}`; `tests/test_time_getters_static.py` forbids `Date` getters elsewhere | verified |
| `static/js/ui/feedback.js::BADGE_KINDS`, `studio.js:593 KNOWN_BADGE_TYPES`, `tokens.css` badge tokens, `test_design_tokens_a11y.py` ~l.1177/1329 | verified |

### Prerequisites
- [x] DD5 premise checked with the operator's token (`GET /v1/models` and 1-token messages), outcome recorded in the flight log
- [x] The operator's token is in a file outside the repo (`~/.config/the-one-hat/plan-token`, mode 600; path only, never the token)
- [ ] **Leg 2 start re-verify** (external state can change after planning):
  - port 8487 is free (`ss -ltn`);
  - goldfinch is running and can reach `http://127.0.0.1:8487/api/live` from its tab;
  - the token still works: a shell probe reads the file and makes one `GET /v1/models` and one 1-token `claude-haiku-4-5` message, printing status codes only; and records which models still 429;
  - none of `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY` is set in the dev instance's environment (checked by name only from `/proc/<pid>/environ`, values never printed): the provider does not pass `base_url`, so the SDK would honour `ANTHROPIC_BASE_URL` (`anthropic/_client.py:341`).
- Note: `jq` is not installed on this host; the behavior test's shell steps use `python3`.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Leg 1 carries the whole slice in one pass: the type (DD1, DD7), migration (DD8), API (DD2-DD5), editor (DD6), badge (DD7), tests and docs. Leg 2 is live verification: run `anthropic-plan-token-chat` on a dev instance with the operator's real token, then a short operator walk of the editor, fixing anything that surfaces.

Tests in leg 1:
- Unit: `test_provider_api.py` (create/update 422s; masked preserve; `token_set_at` stamped on create, re-stamped only on a changed token, never client-seedable; response keys; `/test` ok / rejected / missing; `/models` live and fallback, with the SDK stubbed through `sys.modules` as the plan tests do), `test_anthropic_provider.py` (token subclass sends bearer + beta header, never `x-api-key`, never consults the credential source; 401 → `PlanTokenRejectedError` in both `complete` and `stream`; missing token → `PlanTokenMissingError`; for both plan types a bare-`"Error"` 429 → `PlanRequestRefusedError`, a described 429 passes through, and a 429 after a yielded chunk is not translated), `test_factory.py` (token type gets `access_token`, no `provider_config_id`), `test_llm_provider_cross_provider_conformance.py` (the token subclass in `PROVIDER_FACTORIES`), the DD11 type-change directions, a PUT with no `secrets` keeping `token_set_at`, `test_db_migration.py` (DD8), the consistency and contrast pins.
- Browser (`providers` lane, new `tests/browser/test_flow_provider_plan_token.py`): the type list shows both labels; creating a token provider shows the Token field and no sign-in, and saves; edit mode shows `provider-token-expiry` with today's date; editing the token and saving changes the line's date with no reload; the soon and past states render from a `page.route`-patched `GET /api/providers` row; `App.studio.planTokenExpiry` thresholds via `page.evaluate`; Test with a mocked `/test` response shows ok.

### Checkpoints
- [x] DD5 premise recorded
- [ ] v44 migration test green against a v43 database with OAuth secrets
- [ ] `make test-unit` (expected 12 skipped) and the `providers`, `contracts` and `settings` lanes green; then the full gate. On this WSL host every browser lane and the gate run with `THE_ONE_TEST_NETNS=1` (and `THE_ONE_REQUIRE_WEBKIT=1` for `contracts`)
- [ ] `anthropic-plan-token-chat` passes live

### Adaptation Criteria

**Divert if**:
- The premise check shows a `setup-token` token cannot run inference through the bearer path at all, or needs a different header or client identity than the OAuth type: the request path is no longer "reuse", and the design is re-planned with the operator.
- The v44 rebuild cannot preserve `secrets` byte-for-byte.

**Acceptable variations**:
- The exact wording of help, error and expiry strings.
- Placing the expiry helper in `provider-editor.js` or a small sibling module, as long as it is pure and testable.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `plan-token-provider` - The `anthropic-plan-token` type end to end: registry and subclass, the plan error translation (DD1, DD10), factory, v44 migration, API create/update/test/models and `token_set_at`, editor token field and expiry line, labels and badge, unit and browser tests, docs (`the_one/agents.md` LLM layer, `CLAUDE.md` LLM-layer paragraph, `SECURITY-MODEL.md` credential storage, the testid registry)
- [ ] `live-verification` - Run `anthropic-plan-token-chat` on a dev instance (port 8487, scratch data dir) with the operator's token, then a guided operator walk of the editor; fix what surfaces

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Operator has revoked the test token

### Verification
- Charter criteria 1 and 4: leg 1's unit and browser tests, and the code review.
- Charter criteria 2 and 3: `tests/behavior/anthropic-plan-token-chat.md`, run live in leg 2.
