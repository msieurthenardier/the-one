# Leg: plan-token-provider

**Status**: completed
**Flight**: [Claude Plan (Token) provider](../flight.md)

## Objective
Ship the `anthropic-plan-token` provider type end to end: type plumbing, the v44 `llm_providers` rebuild, the token provider subclass and the shared plan error translation, the API create/update/`/test`/`/models` paths with the server-owned `token_set_at` stamp, the editor's token field and expiry line, the relabel and badge, with unit and browser tests and docs.

## Context
- The flight spec's DD1-DD11 are the design; this leg implements all of them. Where this leg and the flight disagree, the flight's DDs win and the disagreement is a bug in this leg to report in the flight log.
- Premise (flight log, 2026-10-12): a `setup-token` token works through the exact bearer + `anthropic-beta: oauth-2025-04-20` path the OAuth type uses; `GET /v1/models` returns 200; only `claude-haiku-4-5` runs, other models return 429 `rate_limit_error` with message "Error".
- **Never read, print or use** `~/.config/the-one-hat/plan-token`: it is the operator's live credential, used only in leg 2. Every test here uses synthetic tokens (`sk-ant-oat01-test…`) and stubbed SDK clients. No real Anthropic call is made in this leg.
- Prior debriefs: the `providers` browser lane was measured at 217/300 s (sortie 02); the agent-rules focus test (squawk 0187) and the confirm-lapse test (squawk 0166) are known flakes.

## Inputs
- `main` at `cd7c7f6` plus the uncommitted sortie 03 planning artifacts on branch `sortie/03-claude-plan-token`.
- `CURRENT_VERSION = 43` (`the_one/db/schema.py`).

## Outputs
- The new type selectable in Library › Model providers as "Claude Plan (Token)", and `anthropic-plan` labelled "Claude Plan (OAuth)".
- Schema v44; every existing provider row and its encrypted `secrets` preserved.
- Unit and browser tests; docs updated. Nothing committed.

## Acceptance Criteria

**Type and provider (DD1, DD10)**
- [ ] AC1: `anthropic-plan-token` is in `PROVIDER_TYPES`, the `LLMProviderConfig.type` Literal, `PROVIDER_TYPE_MAP` and `_try_load_builtin` (extra alias `anthropic`); `tests/test_provider_types_consistency.py` passes, including the live CHECK pin.
- [ ] AC2: `AnthropicPlanTokenProvider(AnthropicPlanProvider)`, `name = "anthropic-plan-token"`, registered under that name; built by `AgentFactory` with `access_token=provider_config.api_key` and no `provider_config_id`. It sends bearer `auth_token` + the OAuth beta header, never `x-api-key`, and never consults `plan_credentials`. With no token, `_before_request` raises `PlanTokenMissingError` before any HTTP call.
- [ ] AC3: `AnthropicPlanProvider` overrides `complete()` and `stream()` with the parent's exact signature; `stream()` iterates the parent through `contextlib.aclosing`; on `anthropic.AnthropicError` only, it calls `self._translate_plan_error(exc)` and raises a non-`None` result `from exc`, else re-raises the original. `stream()` translates only before its first yielded chunk.
- [ ] AC4: the base `_translate_plan_error` maps `anthropic.RateLimitError` to `PlanRequestRefusedError` only when `exc.body` is a `dict` whose `"error"` is a `dict` with `"message" == "Error"`; the text begins "Your Claude plan didn't allow this request to {model}." and ends with the DD10 hint. A 429 with any other message, or a non-dict body, passes through unchanged. A test shows that `aclose()` on the wrapper's stream closes the inner generator. The token subclass's override maps `anthropic.AuthenticationError` to `PlanTokenRejectedError` (the DD1 text), then defers to the base. All three error classes are plain `Exception` subclasses.
- [ ] AC5: the OAuth type's behaviour is unchanged apart from AC3/AC4 (existing `tests/test_anthropic_provider.py`, `tests/test_plan_credentials.py`, `tests/test_anthropic_oauth.py` pass unmodified, except tests whose expectations this leg intentionally changes, each named in the flight log).

**Schema (DD8)**
- [ ] AC6: `CURRENT_VERSION = 44`; the `version < 44` block rebuilds `llm_providers` per the v33 ceremony, copying **every** column including `secrets`. A v43 database with an `anthropic-plan` row (encrypted `secrets`) referenced by an agent migrates with the row, its decrypted secrets and the agent's `provider_config_id` intact, then accepts an `anthropic-plan-token` insert, and the raw `secrets` column bytes are unchanged by the migration; a fresh database (SCHEMA_V1 then migrated) also admits the type; a rerun from a crash between CREATE and RENAME is idempotent. The `CURRENT_VERSION == 43` pins in `tests/test_db_migration.py` move to 44.

**API (DD2-DD5, DD11)**
- [ ] AC7: `/providers/types` lists "Claude Plan (OAuth)" (`anthropic-plan`) then "Claude Plan (Token)" (`anthropic-plan-token`); the count tests are renamed to 7/8.
- [ ] AC8: create of a token-type row without `api_key` → 422; with an `sk-ant-api…` key → 422 with the DD4 sentence, never echoing the value; otherwise 201 with `secrets["token_set_at"]` stamped (`now_iso()`).
- [ ] AC9: update rules run on `updated` (after `model_validate`): a PUT that omits `api_key` or `secrets` keeps the stored token and `token_set_at`; a changed token re-stamps; an identical re-paste (even with surrounding whitespace) does not; a client-sent `secrets.token_set_at` never seeds or overwrites the stamp; a resolved `sk-ant-api…` key → 422.
- [ ] AC10 (DD11): OAuth keys are pinned only when the resolved type is `anthropic-plan`, the stamp only when it is `anthropic-plan-token`, otherwise both dropped. Into `anthropic-plan`: `api_key` forced to `None`. Into `anthropic-plan-token` from any other type: an omitted or masked `api_key` → 422 ("Paste a token from `claude setup-token`"), decided by a `fresh_key_supplied` flag captured from the raw request (see Guidance step 3). An explicit `api_key: null` or `""` on an existing token row → 422 (missing token). Tested in each direction.
- [ ] AC11: `_provider_response` returns `token_set_at` and `token_expires_around` (+365 days) non-null only for the token type; `oauth_active` is true only for `anthropic-plan` with both OAuth tokens. No provider response contains the stored token: asserted by searching the bodies of create, update, GET list and GET one for the synthetic token string.
- [ ] AC12: `/test` for the token type: no token → `{"status":"error"}` with the DD2 sentence and no client built; `models.list()` ok → `{"status":"ok"}`; `AuthenticationError` → `{"status":"error"}` with the rejected-token sentence; other `AnthropicError` → `{"status":"error","detail":str(e)}`. `/models`: no token → static catalog, no client built (a stub-based assertion that no SDK client is constructed, so `ANTHROPIC_AUTH_TOKEN` can never be read); live listing via `_plan_bearer_client`; any failure → static catalog.

**Editor and badge (DD6, DD7)**
- [ ] AC13: creating a "Claude Plan (Token)" provider shows a "Token" field (placeholder `sk-ant-oat01-…`, help line tied with `aria-describedby`), no base URL and no sign-in section; switching the type select in create mode relabels the field and toggles the help.
- [ ] AC14: in edit mode, `provider-token-expiry` reads "Token added {date} · expires around {date}" (dates by `App.time.formatDate`); it shows the soon and past wordings and styles per the DD6 thresholds (`past` when `now >= expires`, `soon` when `expires - now <= 30 days`); `App.studio.planTokenExpiry` is tested at both edges. After an edit-mode Save of a new token the line shows today's date with no reload (browser test with a `page.route`-patched older stamp on mount). The line hides when the type select leaves the token type.
- [ ] AC15: no new `innerHTML`/`outerHTML`/`insertAdjacentHTML` sink (`tests/test_ui_guards.py` unchanged for `provider-editor.js`); no `Date` getter outside `time.js`; `App.time.formatDate` has a zone-aware case in `tests/browser/test_ui_time_contract.py`.
- [ ] AC16: the `anthropic-plan-token` badge (DD7: tokens in both theme blocks, `.badge--anthropic-plan-token`, `BADGE_KINDS`, `KNOWN_BADGE_TYPES`) passes the contrast audit and the kind-count pins (16).

**Docs and gates**
- [ ] AC17: docs updated: `the_one/agents.md` (LLM layer / plan provider section, the "adding a provider type" checklist brought current, `App.time.formatDate`), `CLAUDE.md`'s LLM-layer paragraph (the new type, one sentence), `SECURITY-MODEL.md` (the token is a subscription bearer credential stored encrypted in `api_key`), `README.md` (:145 Library › Model providers; :157 a Token row; the relabel), `docs/ui-testid-registry.md` (`provider-token-expiry`), the relabel in `tests/behavior/extended-thinking-tool-turn.md`, `tests/behavior/anthropic-plan-chat-parity.md` and `tests/behavior/anthropic-plan-signin.md` (historical run logs under `runs/` are left untouched). Stale comments enumerating plan/reasoning types (`provider-editor.js` ~l.103, 291, 320; `providers-section.js` ~l.58) updated in passing.
- [ ] AC18: `make test-unit` passes with the expected skip count (12); `ruff check` and `ruff format --check` clean; the static guards pass; the `providers`, `contracts` and `settings` lanes pass, then the full gate (`THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`). Any failure outside this leg's tests is re-run in isolation; a known squawk flake that passes in isolation is recorded and accepted.

## Verification Steps
- AC1-AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_types_consistency.py tests/test_anthropic_provider.py tests/test_factory.py tests/test_llm_provider_cross_provider_conformance.py tests/test_plan_credentials.py tests/test_anthropic_oauth.py -x --timeout 30`
- AC6: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/test_schema.py tests/test_schema_template.py -x --timeout 60`
- AC7-AC12: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py tests/test_provider_repository.py -x --timeout 30`
- AC13-AC16: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane providers -x`; `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane contracts -x` (covers `tests/browser/test_ui_time_contract.py`; a bare browser file needs `-m browser`); `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_time_getters_static.py tests/test_ui_badge_kinds.py tests/test_admin_reasoning_effort_field.py -x --timeout 30`
- AC17: read the diff of each named doc.
- AC18: `make test-unit`; ruff; the gate command above.

## Implementation Guidance

1. **Types and migration first** (AC1, AC6). Add the type to the four places; write the v44 block by copying the v33 block (`schema.py` ~l.1983-2037) and naming all nine columns explicitly in both INSERT column lists (`id, name, type, base_url, api_key, config, secrets, created_at, updated_at`; v33 listed eight). Write the migration test before moving on: it is the hard-to-reverse step.
2. **Provider classes** (AC2-AC5). In `llm/anthropic_plan_provider.py`: the three error classes, `PLAN_TOKEN_LIFETIME_DAYS = 365`, the base wrapper and hook, then `AnthropicPlanTokenProvider` and its registration. Note `stream()` must remain an async generator in the override. Then the factory branch (`agent/factory.py:364`). Add the subclass to `PROVIDER_FACTORIES` in `tests/test_llm_provider_cross_provider_conformance.py`.
3. **API** (AC7-AC12). In `interfaces/web/api.py`:
   - `_PLAN_TOKEN_MANAGED_KEYS = ("token_set_at",)` beside `_PLAN_OAUTH_MANAGED_KEYS`.
   - **`create_provider`:** `secrets = {}` stays forced before validation; the missing-token and DD4 checks and the stamp run **after** `model_validate`, on `provider.api_key` (stripped there).
   - **`update_provider`, in this order:**
     1. From the raw request, before masked-key resolution (~l.5094): `fresh_key_supplied = "api_key" in data and isinstance(data["api_key"], str) and data["api_key"].strip() != "" and not _looks_masked(data["api_key"])`.
     2. Masked-key resolution (unchanged), then `data["secrets"] = {}` (a dict must go into validation; the client never supplies managed keys, and any non-managed client keys are not used by any provider type).
     3. `merged = existing.model_dump(); merged.update(data); updated = LLMProviderConfig.model_validate(merged)` (unchanged).
     4. On `updated`: build the secrets by the resolved type (OAuth keys from `existing.secrets` only for `anthropic-plan`, the stamp only for `anthropic-plan-token`); force `api_key=None` for `anthropic-plan`; for the token type, the checks (missing token, DD4 prefix, type change into the token type without `fresh_key_supplied`) and the stamp. Apply with `updated = updated.model_copy(update={...})` (no `validate_assignment` on the model; the values are already validated).
     5. The URL-safety check, `repo.update`, `evict_credential_source` (unchanged).
   - `_provider_response`; the `/test` and `/models` branches (reuse `_plan_bearer_client`, check for a missing token first). Keep 422 details free of submitted values.
   - **Checkpoint:** after steps 1-3 and their unit tests, run `make test-unit` and record the result in the flight log before starting the editor.

4. **Editor** (AC13-AC15). `providers-section.js` `TYPE_DEFAULTS`; `provider-editor.js` label/placeholder/help from defaults (initial HTML string is fine; live changes by `textContent`/`setAttribute`), `renderTokenExpiry(container, row)` built with DOM APIs, called at mount and in `performSave`'s edit branch (~l.858-883) with the response row; the pure `App.studio.planTokenExpiry`; `App.time.formatDate` in `time.js`. Run `tests/test_ui_guards.py` early.
5. **Badge and labels** (AC7, AC16) and every pin named in DD7.
6. **Browser tests**: new `tests/browser/test_flow_provider_plan_token.py` (lands in the `providers` lane by glob). Use `_nav`/`_lists` helpers and `_providers.py`; no raw route hashes. Stub `/test` and `/models` with `page.route` where a live call would otherwise happen.
7. **Docs** (AC17), then the gates (AC18). Record results, intended test changes and any deviation in the flight log under a `### plan-token-provider` heading.

## Edge Cases
- **`apiKeyHelp` text** must contain no `}`: `tests/test_admin_reasoning_effort_field.py` reads a `TYPE_DEFAULTS` entry up to the next `}`.
- **Whitespace around a pasted token**: the `api_key` validator strips it; comparisons use `updated.api_key`.
- **An `anthropic-plan` row with OAuth secrets switched to the token type**: OAuth keys dropped, token required, stamp written.
- **Token type switched to `anthropic`**: the stamp dropped; `api_key` keeps the token per masked rules (DD11); `anthropic` will then reject it at use, which is the operator's visible choice.
- **429 body as a string or `None`**: no translation.
- **Stream error after the first chunk**: original error propagates.
- **Day-granular expiry dates across zones**: formatted in the operator zone via `App.time`.

## Files Affected
- `the_one/db/_provider_types.py`, `the_one/db/models.py`, `the_one/db/schema.py`
- `the_one/llm/registry.py`, `the_one/llm/anthropic_plan_provider.py`, `the_one/agent/factory.py`
- `the_one/interfaces/web/api.py`
- `the_one/interfaces/web/static/js/areas/studio/providers-section.js`, `.../studio/provider-editor.js`, `.../static/js/time.js`, `.../static/js/ui/feedback.js`, `.../static/js/areas/studio.js`
- `the_one/interfaces/web/static/css/tokens.css`, `.../css/components.css` (and `studio.css` for the expiry line's styles)
- Tests: `tests/test_provider_types_consistency.py`, `tests/test_anthropic_provider.py`, `tests/test_factory.py`, `tests/test_llm_provider_cross_provider_conformance.py`, `tests/test_db_migration.py`, `tests/test_provider_api.py`, `tests/test_design_tokens_a11y.py`, `tests/browser/design_tokens.py`, `tests/test_ui_badge_kinds.py`, `tests/browser/test_ui_choice_contract.py`, `tests/test_admin_reasoning_effort_field.py`, `tests/browser/test_ui_time_contract.py`, `tests/browser/test_flow_provider_plan_signin.py` (label, ~l.126, 136), new `tests/browser/test_flow_provider_plan_token.py`
- Docs: `the_one/agents.md`, `CLAUDE.md`, `SECURITY-MODEL.md`, `README.md`, `docs/ui-testid-registry.md`, `tests/behavior/extended-thinking-tool-turn.md`, `tests/behavior/anthropic-plan-chat-parity.md`, `tests/behavior/anthropic-plan-signin.md`

## Citation Audit
Developer design review (2026-10-12) re-checked the references against `cd7c7f6`: every named test file exists; `tokens.css` badge lines 162/188/313/338, `design_tokens.py` ~l.107/194, `test_ui_badge_kinds.py:35`, `test_ui_choice_contract.py:345`, `api.py:5024` and the `update_provider` masked-key line ~5094 confirmed. Citations carried from the flight spec were verified by two Architect cycles against `cd7c7f6` (flight log). Line numbers in this leg are approximate (`~`) and anchored by symbol; the design reviewer re-checks them.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
