# Leg: 05a-provider-kind

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Make model providers a proposable kind on the server side, following Leg 4a's MCP patterns:
- an HTTP-free write service extracted from the provider routes, with the routes left thin;
- an in-transaction re-read write. Leg 4a built this for MCP. Here it also fixes today's race,
  in which saving a provider while its OAuth token refreshes overwrites the fresh token;
- a server-side table of per-type defaults, pinned to the client;
- the `provider` kind, for proposals now (Leg 5b adds fills);
- the type-change rules and warnings (DD10);
- the guard marks;
- richer read views;
- the guide topic.

## Context

- **Flight DD10** (model providers) is the authority, refined by the operator decision of
  2026-11-21 ("type changes allowed with a warning") and the FD calls recorded in the flight
  log, cycle 2.
- **Split.** Leg 5 is split into **5a (server)** and **5b (client)**, like Leg 4. Batch B
  commits 4a, 4b, 5a and 5b together, so 5a never ships alone. Until 5b lands, the client fails
  soft on the unknown `provider` kind.
- **The template is Leg 4a as landed:**
  - `the_one/mcp/service.py`: `McpWriteError(status, detail)`, `McpSourceNotFound`,
    `McpStaleError`, `McpWriteDeps` with late-bound getters, `create`, `replace` and `change`,
    `_after_write(before, after)`, and the validators moved with exact details;
  - `MCPSourceRepository.update_in_txn(source_id, mutate, *, on_commit)` and
    `create(..., on_commit=)`;
  - `kinds/mcp_server.py`, with the `Kind` members `warnings`, `card_extras`, `needs_secret`,
    `relaxed_guard_keys`, `create_only_message` and `resolve_target`;
  - `kinds.find` and `kinds.target_args`;
  - `guard.check(..., relaxed=)`;
  - `proposal_view` `warnings` and the applied create's `target_id`.

  Copy the shapes; do not reinvent them.
- **The provider routes today** (survey, 2026-11-21; line numbers are the working tree's, and
  shifted by Leg 4a):
  - **`create_provider`:**
    1. the raw `type == "mock"` check without dev mode (400);
    2. `_checked_name`;
    3. a client-suppliable `id` (a duplicate gives a 500);
    4. `secrets = {}`;
    5. `model_validate`;
    6. for `anthropic-plan-token`, `_check_plan_token` and the `token_set_at` stamp;
    7. for the Claude types, the `thinking_enabled` default of true;
    8. `_is_safe_provider_url`, unless the type is `mock` or `ollama`;
    9. `repo.create`.
  - **`update_provider`:**
    1. `existing` is read **outside** the transaction (404);
    2. the mock check;
    3. `fresh_key_supplied`, and the masked `api_key` preserve;
    4. `secrets = {}`;
    5. the merge, with `config` replaced whole;
    6. `_checked_name` if `name` is in the body;
    7. `model_validate`;
    8. the per-type rules:
       - `anthropic-plan`: pin the OAuth keys from `existing`, and `api_key = None`;
       - `anthropic-plan-token`: a 422 when entering the type without a fresh key, the plan
         check, and the stamp rules;
       - otherwise `secrets = {}`;
    9. the URL check;
    10. `repo.update`;
    11. `evict_credential_source`.
  - **The race:** the OAuth keys are pinned from the out-of-transaction `existing`, then the
    whole secrets blob is written. An `update_secrets` from
    `plan_credentials.get_access_token` in between is lost.
- **FD decisions at this leg's design (2026-11-21):**
  1. **The update route also uses `update_in_txn`,** with a mutator that runs today's merge on
     the **fresh** row. This keeps the route's HTTP behaviour identical and fixes the race for
     operator saves too, not only proposals. A new route test pins it: an OAuth refresh written
     after the request starts survives a PUT.
  2. **Type changes, for proposals and fills** (DD10 plus the operator decision). Two terms:
     - **Key-taking** comes from the defaults table's `shows_api_key`: `openai-compatible`,
       `openai`, `anthropic`, `anthropic-plan-token` and `openrouter`.
     - **Keyless:** `ollama`, `anthropic-plan` and `mock`.

     `kinds.normalize` takes the `mode` argument (`"propose"` | `"fill"`) that Leg 4b adds, and
     the provider kind uses it.
     - **Key-taking to a *different* key-taking type** (including `anthropic-plan-token` to
       `anthropic`, which would carry the setup token as an API key):
       - **proposal** (`mode="propose"`): refused, with the handoff "change the type in the
         editor and enter the new key";
       - **fill** (`mode="fill"`): allowed, and the client clears the key field (Leg 5b);
       - **service:** `change_provider` **also refuses** it, as a defence, since it runs on
         approve after the stale window.
     - **Into `anthropic-plan`:** allowed, and `change_provider` clears `api_key`. Warning:
       "the stored key is cleared; sign in after approving".
     - **Out of `anthropic-plan`:** allowed, and the OAuth secrets are dropped, as today's route
       does. Warning: "this signs the provider out".
     - **Into `ollama`:** allowed, and `api_key` is cleared. Warning: "the stored key is
       cleared".
     - **Keyless (`ollama` or `anthropic-plan`) to key-taking:** allowed. Warning: "enter its API
       key on the page after approving".
     - **Into `anthropic-plan-token`, or creating one:** refused for a proposal (it needs a fresh
       token); allowed for a fill.
     - **Creating a key-taking type:** allowed, with the "enter its API key" warning.
     - **A change that keeps the type** (name or options only, including on
       `anthropic-plan-token`): keeps `api_key` and the `token_set_at` stamp. Pinned.
     - **`mock`:** a proposal or fill with `type: "mock"` is refused, and so is a target whose
       stored type is `mock`. `change_provider` takes no `dev_mode` and does not gate changes on
       it.
     - **Every type change** also says how many agents use the provider ("3 agents use this
       provider; their model names stay as they are"), via `list_by_provider`, and whether
       GleepGlorp does. Models are not cleared.
     - **On a type change, `change_provider` mirrors the editor's type-select handler:**
       - a hidden-URL target type takes its default `base_url`; naming one is refused;
       - `ollama` and `openrouter` take their default unless `base_url` is named;
       - `openai-compatible` (default `''`) requires `base_url` to be named, or it is refused;
       - into `ollama`, `config.num_ctx` is seeded with the editor's `DEFAULT_NUM_CTX` (32768)
         when absent;
       - into a Claude type, `config.thinking_enabled` is seeded true when absent;
       - `reasoning_effort` is stored exactly as the editor writes it (read `collectFormData`:
         `''` means the provider default).
  3. **`base_url` and the defaults.** A `PROVIDER_TYPE_DEFAULTS` table in
     `db/_provider_types.py` holds, per type: `base_url`, `base_url_shown`, `shows_api_key`,
     `shows_num_ctx`, `shows_thinking`, `shows_reasoning_effort` and `plan_sign_in`.
     - **Pinned to the client.** A test reads
       `the_one/interfaces/web/static/js/areas/studio/providers-section.js` `TYPE_DEFAULTS`,
       as `tests/test_admin_reasoning_effort_field.py` does. The parser tolerates the
       `apiKeyHelp` strings.
     - **One source.** `api.py`'s `_CLAUDE_PROVIDER_TYPES` is derived from the table, or
       asserted equal to it.
     - **Hidden-URL types.** A proposal or fill of one takes the default. A `base_url` named
       for such a type is refused.
     - **The guard exemption.** Any `base_url` whose `normalize_url` equals **any** type's
       default URL is exempt from the outside-value guard (DD7: these are the app's own
       values). This is a small hook in `outside.check` and needs no row access.
  4. **Moving `base_url`** on a provider with a stored key warns that the key will be sent to
     the new address.
  5. **Read views.** `providers` detail gains `options` (`num_ctx`, `thinking_enabled`,
     `reasoning_effort`) and `key_stored` (a boolean), declared in `OPERATOR_PATHS`, so
     GleepGlorp can propose a change without guessing current values. No key material.
  6. **`agent_name` is `None`** for provider proposals, and `config_changed` carries `agent:
     null` and `target_id`, as for MCP.

## Inputs

- Leg 4a landed (uncommitted): see Context.
- `api.py` `create_provider`, `update_provider`, `_check_plan_token`, `_is_safe_provider_url`,
  `_URL_VALIDATION_SKIPPED_TYPES`, `_CLAUDE_PROVIDER_TYPES`, `_PLAN_OAUTH_MANAGED_KEYS`,
  `_looks_masked`, `_provider_response`; `db/repositories.py` `LLMProviderRepository`;
  `db/_provider_types.py`; `llm/plan_credentials.py`; `gleepglorp/view_library.py`
  `providers_view`, `view_core.py`; `gleepglorp/guide/model-providers.md` (571 of 600 words).

## Outputs

- **`the_one/llm/provider_service.py`** (new; no `fastapi`, `the_one.interfaces` or
  `the_one.gleepglorp` imports):
  - `ProviderWriteError(status, detail)`, `ProviderNotFound` and `ProviderStaleError(fields)`;
  - `ProviderWriteDeps`;
  - `create_provider(deps, data, *, dev_mode, on_commit=None)`;
  - `replace_provider(deps, provider_id, data, *, dev_mode)`, the PUT exactly, on
    `update_in_txn`;
  - `change_provider(deps, provider_id, changes, *, base=None, override=False,
    on_commit=None)`, with decision 2's rules;
  - the moved validators (`check_plan_token`, `is_safe_provider_url`, the name check), with
    exact details; `api.py` keeps wrappers where other callers or tests use the old names
    (grep);
  - after commit, `evict_credential_source`, exactly as today.
- **`LLMProviderRepository`:** `create(provider, *, on_commit=None)` and
  `update_in_txn(provider_id, mutate, *, on_commit=None) -> (before, after)`. The api key and
  secrets are encrypted as `update` does, and the same re-entrancy docstring applies.
- **`db/_provider_types.py`:** `PROVIDER_TYPE_DEFAULTS`, with a key-equality assert against
  `PROVIDER_TYPES`.
- **`api.py`:** thin `create_provider` and `update_provider`.
- **`kinds/provider.py`** (new), registered after `mcp_server`:
  - **fields:**

    | Field | Type | Path | Notes |
    |---|---|---|---|
    | `name` | `text` | | |
    | `type` | `text` | | |
    | `base_url` | `text` | | `address_or_command` |
    | `num_ctx` | `integer` | `("config", "num_ctx")` | at least 1 |
    | `thinking_enabled` | `boolean` | `("config", "thinking_enabled")` | |
    | `reasoning_effort` | `text` | `("config", "reasoning_effort")` | `""`, `low`, `medium` or `high` |

  - **`operator_only`:** `api_key` and `secrets`;
  - **`fillable = ()`** (Leg 5b sets it);
  - **`relaxed_guard_keys = {"base_url"}`;**
  - **`resolve_target`:** id-first;
  - **`normalize`:**
    - refuses `mock`, operator-only keys, unknown keys, and an option the type does not show
      (`num_ctx` outside `ollama`; `thinking_enabled` outside the Claude types;
      `reasoning_effort` where the client does not show it);
    - refuses a `base_url` for a hidden-URL type, and fills the default instead;
    - applies decision 2's refusals through `needs_secret`;
  - **`base`**, **`card_extras`** (the name and `target_gone` by id), **`warnings`**
    (decisions 2 and 4, on pending and failed cards only), **`apply`** (with a pre-generated
    id on create), **`summary_text`** and **`title`**.
- **`kinds/errors.py`** maps the provider errors.
- **The outside-value guard:** a `base_url` equal to `PROVIDER_TYPE_DEFAULTS[type]["base_url"]`
  is exempt (decision 3). This is a small hook in `outside.check`, or the kind passes it as
  trusted. Test both ways.
- **`providers_view` detail** gains `options` and `key_stored` (decision 5), plus the
  `OPERATOR_PATHS` and provenance test.
- **The guide topic** `model-providers.md` gains the proposal and fill behaviour: keys and
  sign-in happen on the page, with the type-change warnings. It stays within 600 words, with
  prose trimmed.
- **Docs:**
  - `the_one/agents.md`: the provider service, `update_in_txn`, the race fix, the kind and the
    defaults table;
  - `SECURITY-MODEL.md`: the provider fields GleepGlorp may and never may set, the
    key-never-follows rule, and the race fix.

## Acceptance Criteria

- [ ] **AC1. The provider routes are behaviour-identical.** These pass with their assertions
  unedited:
  - `tests/test_provider_api.py`;
  - `test_api_secret_mask_roundtrip.py`, `test_api_name_rule.py`, `test_api_invalid_json.py`;
  - `test_api_agent_provider_check.py`, `test_gleepglorp_settings.py`;
  - `test_admin_reasoning_effort_field.py`, `test_provider_types_consistency.py`;
  - plus every other hit of `grep -rln "/api/providers\|create_provider\|update_provider" tests/`.

  Run them before writing the change path or the kind. If any assertion needs an edit, stop
  with `[BLOCKED:route-behaviour-changed]`.
- [ ] **AC2. The race is fixed.** The test recipe, which is deterministic:
  1. start from a signed-in `anthropic-plan` provider;
  2. in the test, hold `async with write_transaction(conn)` (`the_one/db/_write_lock.py`);
  3. start the PUT (a name change) as a task;
  4. yield with `asyncio.sleep(0)` until the task is blocked on the lock;
  5. inside the held lock, write a new `refresh_token` with raw `conn.execute` plus
     `_encrypt_secrets_blob` (**not** `update_secrets`, whose re-entrancy guard raises);
  6. release the lock, await the PUT, and assert the stored `refresh_token` is the new one.

  The same recipe applies to `change_provider`. **Falsification:** temporarily restore the old
  read outside the transaction (`repo.get` before the write), and confirm both tests fail.
- [ ] **AC3. `update_in_txn`** has the same contract and tests as Leg 4a's: re-read under the
  lock, a mutator exception writes nothing, `on_commit` runs inside the transaction,
  `(before, after)` is returned, and `updated_at` moves.
- [ ] **AC4. `change_provider` changes only the named fields,** merging `config` keys per key,
  not replacing the whole `config`. Decision 2's rules apply, each with a test:
  - clearing the key on a change into `ollama`;
  - the refusals;
  - the OAuth keys kept on a change that stays `anthropic-plan`;
  - the OAuth secrets dropped on a change out of it, as today's route does;
  - the `token_set_at` rules.

  The stale check works against `base`. The name rule and the URL check apply. Eviction runs
  after commit.
- [ ] **AC5. Defaults.**
  - `PROVIDER_TYPE_DEFAULTS` equals the client's `TYPE_DEFAULTS` (`base_url`, `showBaseUrl`)
    for every type. Test it by reading `providers-section.js`.
  - A proposal for `anthropic` with no `base_url` stores `https://api.anthropic.com`.
  - A proposal naming a `base_url` for `anthropic` is refused.
- [ ] **AC6. The `provider` kind.**
  - It is registered and described.
  - Every `normalize` refusal has a test.
  - Id-first resolution, `base`, `card_extras`, `warnings` (each sentence, and none on a plain
    change) and approve through the service.
  - `config_changed` carries `kind` `provider`, `agent` null and `target_id`.
  - A stale change gives stale rows, and a deleted target withdraws.
- [ ] **AC7. The guard on `base_url`** (DD7 per-kind falsification), through the real
  `propose_change` on an untrusted turn:
  - a URL from a linked page → allowed;
  - from an unlinked page → refused;
  - the type default → allowed with no source.

  `guard.check` passes a `base_url` with a UUID path. The safety cases are falsified.
- [ ] **AC8. Read views.** The detail shows `options` and `key_stored`, never the key, and the
  provenance test covers them.
- [ ] **AC9. Pins this leg trips,** each updated and none weakened:
  - `REGISTRY` count (4 becomes 5) and the `operator_only` set;
  - the description pin (it must name `provider`, within the token and character caps);
  - the kind list and the "Valid names" message;
  - the seam-import list;
  - the guide drift test;
  - the `view_core` allowlists.
- [ ] **AC10. Guide.** `model-providers.md` is at most 600 words and passes the drift test.
- [ ] **AC11. No regression.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips, and ruff is clean.
  - These lanes pass, one at a time: `providers` and `gleepglorp`.
  - `tests/test_evals_gleepglorp*.py` and `tests/test_evals_freeze.py` pass.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_provider_service.py tests/test_gleepglorp_kind_provider.py <the AC1 list> tests/test_gleepglorp_*.py tests/test_evals_gleepglorp*.py tests/test_evals_freeze.py -x --timeout 60`.
- Lanes `providers`, then `gleepglorp`, one at a time, in the background. Then the unit tier.

## Implementation Guidance

1. **`update_in_txn` and `create(on_commit=)`** on `LLMProviderRepository` (AC3).
2. **The service's `create` and `replace`**, verbatim, on `update_in_txn` for `replace`, with
   thin routes. Run the AC1 list. Add the AC2 route test.
3. **`change_provider`** (AC4).
4. **The defaults table** and its pin (AC5).
5. **`kinds/provider.py`** (AC6), the `errors.py` mapping, and the guard exemption (AC7).
6. **Read views** (AC8).
7. **Pins** (AC9), the guide (AC10), docs, and the gates (AC11).

## Edge Cases

- **A provider GleepGlorp itself uses** (`gleepglorp.settings.provider_config_id`): a change
  proposal is allowed. Its type-change warning also says "GleepGlorp uses this provider" when
  that is so.
- **A client-supplied `id` on create:** the service keeps today's behaviour. The duplicate-id
  500 is pre-existing and out of scope; the FD logs a squawk.
- **`config` keys not shown by the editor** (unknown keys from older versions): `change_provider`
  keeps them, because it merges per key. The route's whole-`config` replace is unchanged.
- **A change naming only `thinking_enabled` on a non-Claude type:** refused, because the editor
  does not show it.

## Files Affected

- `the_one/llm/provider_service.py` (new), `the_one/db/repositories.py`,
  `the_one/db/_provider_types.py`, `the_one/interfaces/web/api.py`.
- `the_one/gleepglorp/kinds/provider.py` (new), `kinds/__init__.py`, `kinds/errors.py`.
- `the_one/gleepglorp/outside.py` (the default exemption), `view_library.py`, `view_core.py`.
- `the_one/gleepglorp/guide/model-providers.md`.
- **Tests:** `tests/test_provider_service.py` and `tests/test_gleepglorp_kind_provider.py` (new),
  a defaults pin test, the AC2 route test, and the AC9 pins.
- `the_one/agents.md`, `SECURITY-MODEL.md`.

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** These resolutions bind wherever this
leg's earlier text is less specific:
- **AC2 recipe.** The race test as first worded passed on today's code. It is now deterministic,
  and its falsification is stated.
- **Propose versus fill.** This uses `kinds.normalize`'s `mode` argument, the one Leg 4b adds,
  not a dead `needs_secret` hook. `Kind.needs_secret` is either used through `mode` or removed.
- **Type-change rules** for `base_url`, `num_ctx`, `thinking_enabled` and `reasoning_effort`
  mirror the editor (decision 2).
- **The key-taking definition** comes from the table's `shows_api_key`, with a service-level
  defence.
- **Defaults table columns, pinned.** `_CLAUDE_PROVIDER_TYPES` becomes a single source.
- **The guard exemption** is "equals any type's default URL".
- **The mock rule.**
- **The route on `update_in_txn`:**
  - the mock check runs inside the mutator, after the 404, keeping the 404-before-400 order;
  - `fresh_key_supplied` is computed from the raw body, before the transaction;
  - `dev_mode` is a parameter, and the service never reads `settings`, so
    `patch("the_one.interfaces.web.api.settings")` keeps working;
  - the mutator raises `ProviderWriteError`;
  - eviction runs after commit, on success only;
  - **one observable change:** the PUT response's `updated_at` is now the written value (today
    it is the stale pre-write value). The Developer checks no test pins the old value, and
    records it.
- **`provider_service.py` imports.** `plan_credentials` stays DB-free at module level: the
  repository goes behind `TYPE_CHECKING`, injected via deps. An `ast` import-boundary test is
  added.
- **Pins, the complete list:**
  - `ProposeChangeTool.description`'s `target` wording now covers MCP servers **and**
    providers; run the token test;
  - `tests/test_gleepglorp_proposals_tool.py:60,75`;
  - `tests/test_gleepglorp_kinds.py:38-39`;
  - `tests/test_gleepglorp_proposals_shape.py:111,125,131`;
  - the seam-import list (add `kinds/provider.py`);
  - `tests/test_gleepglorp_views_provenance.py` `REVIEWED_ALLOWED["providers"]["detail"]`, plus
    `view_core.py` `ALLOWED` and `OPERATOR_PATHS`;
  - `tests/test_evals_freeze.py` must pass with no digest edits.

  The description change is provisional platform text, measured in Legs 6 and 7.
- **Agents warning.** Type changes count the agents using the provider.
- **`reasoning_effort`** is stored as the editor stores it.
- **The `create_provider` service keeps its `uuid4().hex[:12]` default.** The kind pre-generates
  the id on create.
- **`api.py` wrappers.** Keep only `_is_safe_provider_url` (imported by
  `tests/test_provider_api.py:643`). Re-export `_PLAN_OAUTH_MANAGED_KEYS` and
  `_URL_VALIDATION_SKIPPED_TYPES` (used by `reset_provider_oauth` and `test_provider`).
- **Citations (working tree):**
  - `create_provider` `api.py:5677`, `update_provider` `:5720`, `_checked_name` `:236`;
  - `LLMProviderRepository` `repositories.py:3682`, `create` `:3702`, `update` `:3710`;
  - `providers-section.js` is under `static/js/areas/studio/`.
- **Guide budget.** `model-providers.md` (571 of 600 words) trims the Ollama "Pull / Running"
  list or the Claude subscription paragraph to make room.
- **Depends on Leg 4b's `mode` argument.** Leg 5a is implemented after 4b lands.

There is no second cycle: these are specifications of rules already decided, not new design.

## Citation Audit

From the provider survey (2026-11-21) and Leg 4a's landed code, re-checked at leg start:
- `api.py` `create_provider` / `update_provider`, whose step order is in Context;
  `_PLAN_OAUTH_MANAGED_KEYS` (`= anthropic_oauth.OAUTH_MANAGED_SECRET_KEYS`) — verified
  (survey).
- `db/repositories.py` `LLMProviderRepository`: `create` and `update` (existence checked outside
  the transaction), `update_secrets` and `delete_forcing` (the read-inside-the-transaction
  precedent) — verified (survey).
- `llm/plan_credentials.py:135-210`: `get_access_token` refreshes and calls `update_secrets` —
  verified (survey).
- `providers-section.js:53-70` `TYPE_DEFAULTS`; `tests/test_admin_reasoning_effort_field.py:130`
  reads it — verified (survey).
- `db/_provider_types.py` has `PROVIDER_TYPES` and `PROVIDER_TYPE_LABELS` only — verified
  (survey).
- `view_library.py` `providers_view` (id, name, type, address, `oauth_active`, agents,
  `used_by_gleepglorp`) — verified (survey).
- `the_one/mcp/service.py` function list; `MCPSourceRepository.update_in_txn` signature; the
  `Kind` optional members — verified (Leg 4a, landed).
- `guide/model-providers.md`: 571 words — verified.
