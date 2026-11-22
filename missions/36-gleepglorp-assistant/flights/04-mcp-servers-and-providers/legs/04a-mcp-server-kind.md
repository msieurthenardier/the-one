# Leg: 04a-mcp-server-kind

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Make MCP servers a proposable kind on the server side:
- an HTTP-free write service extracted from the MCP routes, with the routes left thin;
- a repository write that re-reads and mutates inside one transaction, so a proposal's stale
  check and status mark ride in the write;
- the `mcp_server` kind (proposals now; fills in Leg 4b);
- the `target` parameter on both tools;
- kind-named tool descriptions;
- the guard work for declared fields;
- the guide topic;
- the MCP part of squawk 0398.

## Context

- **Flight decisions:** DD9 (MCP servers) is the authority. This leg also uses DD3, DD5, DD7,
  DD10 (warnings) and DD12 (descriptions name kinds).
- **Split.** Leg 4 is split into **4a (server)** and **4b (client)**, an acceptable variation
  following the Flight 3 Leg 6 precedent.
  - **Leg 4a is never committed or shipped alone.** Batch B commits 4a, 4b and 5 together.
  - Between 4a and 4b, the client fails soft on the unknown `mcp_server` kind, through Leg 2's
    unknown-kind fallbacks.
  - Leg 4a sets `fillable = ()`; Leg 4b sets it.
- **FD decisions at this leg's design (2026-11-21), recorded in the flight log:**
  1. **Changing a server's `type` is fill-only.** A change proposal naming `type` is refused
     inside the kind with a handoff ("change the type in the MCP server editor"). Proposals
     set `type` only on a create. This narrows DD9 for proposals.
  2. **The write happens inside the transaction through a mutator, not a retry loop.**
     `update_in_txn(source_id, mutate, *, on_commit=None)` re-reads the row inside
     `write_transaction`, calls `mutate(current) -> updated`, sets `updated_at = now_iso()`,
     writes, runs `on_commit(conn)`, and returns `(before, after)`. This replaces DD9's
     `change_agent`-style retry wording: there is no gap between read and write, so `_cache` and
     the OAuth secrets are always fresh.
  3. **`target` and kind-named descriptions land here** (deferred from Leg 1b). Adding the MCP
     fields breaks the every-field description pin.
  4. **Secret-looking keys.** A proposal or fill, on a create or a change, is refused when a
     row with a **non-empty** value has a secret-looking key. The same applies to an `args`
     flag: an item `--name=value` or `-name=value`, or the item after a bare `--name`, when
     `name` is secret-looking.
     - **"Secret-looking" is one algorithm**, a named constant plus a function in
       `kinds/mcp_server.py`, pinned by a table-driven test:
       1. split the name on non-alphanumeric characters and on camelCase boundaries, and
          lowercase it;
       2. it is secret-looking if any whole segment is in `{authorization, token, tokens, secret,
          secrets, password, passwd, pwd, apikey, key, credential, credentials, bearer, cookie}`,
          or if the adjacent pair `api` + `key` or `private` + `key` occurs.
     - **Pinned:**
       - **refused:** `Authorization`, `X-Api-Key`, `apiKey`, `accessKey`, `GITHUB_TOKEN`,
         `DB_PASSWORD`, `PRIVATE_KEY` and `--api-key`, plus two accepted false positives:
         `X-Request-Key-Id` (segment `key`) and `MAX_TOKENS` (segment `tokens`);
       - **allowed:** `Accept`, `KEYBOARD_LAYOUT`, `MONKEY`, `TOKENIZERS_PARALLELISM` and
         `PRIVATE_NETWORK`.
     - The refusal hands off: "enter it in the editor and turn on Sensitive". `SECURITY-MODEL.md`
       states that the accepted false positives cost one handoff.
     - A fill may still add a secret-looking key with an **empty** value, which is the handoff
       (Leg 4b).
  5. **Header keys compare case-insensitively.** They are matched against `secrets`, against
     existing `config.headers` and against the OAuth-managed keys. Env keys compare exactly.
     This closes a bypass of the Sensitive rule (`authorization` beside a stored Sensitive
     `Authorization`).
  6. **`agent_name` is `None` for `mcp_server` proposals.** The card name, the title and
     `target_gone` come from a lookup by `target_id` at view time. `config_changed` for
     `mcp_server` carries `agent: null` and the `target_id`.
- **The route code today.** `create_mcp_source` (`api.py:3370`) and `update_mcp_source`
  (`api.py:3420`). The update's step order:
  1. the surface-row 409;
  2. the per-key `__MASKED__` resolution of `secrets`;
  3. the OAuth-managed key pinning;
  4. the `_cache` strip and preserve;
  5. `model_dump() | data` → `model_validate` (`_checked_name` on a name change);
  6. `_reject_reserved_surface_name`, then `_validate_mcp_source_config`;
  7. the `server_changed` `_cache` pruning (`last_check`, `auth_posture`,
     `protocol_fallback`);
  8. `repo.update`;
  9. `forget_era`, unconditional;
  10. `_evict_all_for_source` and `_drop_source_agent_tool_cache`, on a type, config or secrets
      change;
  11. on a rename, `carry_mcp_rename` and `carry_mcp_rename_into_secrets`, each guarded so a
      failure is a WARNING.

## Inputs

- Batch A, committed at `f4ee1a12`.
- `api.py` (the MCP routes and helpers above), `db/repositories.py` `MCPSourceRepository`
  (`:1326`), `self_configuration` surface helpers, `kinds/` (`base.py`, `__init__.py`,
  `errors.py`, `deps.py`), `proposals/store.py` (`proposal_view`, `_card_extras`,
  `display_values`), `proposals/guard.py`, `outside.py`, `gleepglorp/guide/mcp-servers.md`.

## Outputs

- **`the_one/mcp/service.py`** (new). It imports nothing from `fastapi`, `the_one.interfaces`
  or `the_one.gleepglorp`.
  - **Errors:**
    - `McpWriteError(status, detail)`, shaped like `AgentWriteError`. `detail` reproduces
      today's HTTP detail exactly, as a string or a list, and `.items` derives the `[{loc, msg}]`
      for `ApplyError`.
    - `McpSourceNotFound`.
    - `McpStaleError(fields)`, with fields `[{field, current, proposed}]` in the
      `AgentStaleError` shape.
  - **`McpWriteDeps`:** the repository, plus **late-bound getters** `agent_store()` and
    `secret_repo()`, resolved at call time inside the guarded rename-carry blocks.
    `tests/test_secrets_api.py:542` patches `api._agent_store` to raise and expects the carry
    to survive.
  - **Functions:**
    - `create_mcp_source(deps, data, *, on_commit=None)`;
    - `replace_mcp_source(deps, source_id, data)`, today's PUT exactly;
    - `change_mcp_source(deps, source_id, changes, *, base=None, override=False, on_commit=None)`,
      on `update_in_txn`. Its mutator merges named fields onto the **fresh** row, then applies
      the Sensitive rules, the stale check, validation and the `server_changed` pruning.

    Post-commit side effects run in the same order and conditions as today, from the
    `(before, after)` rows. `forget_era` stays unconditional. `_evict_all_for_source` stays a
    function-local import, because tests patch `the_one.mcp._pool._evict_all_for_source`.
  - **The service never catches `_AlreadyResolved`,** and runs no side effect if the write or
    `on_commit` raised.
  - **Shared helpers stay importable from `api.py`.** `_config_without_cache` and
    `_drop_source_agent_tool_cache` are also used by other routes (`api.py:~3772`), so they stay
    importable there, either moved and re-imported, or left in `api.py` and passed to the
    service.
  - **The validators move into the service** and raise `McpWriteError` with today's exact
    status and detail:
    - `_validate_mcp_source_config` (422 strings);
    - `_reject_reserved_surface_name` (409);
    - the name check: `naming.check_name`, plus the list-shaped detail `_checked_name` produces
      today;
    - the `ValidationError` detail (`_validation_detail`'s shape).

    `api.py` keeps thin wrappers under the old names, for its other callers and any test that
    imports or patches them (grep). The service never imports `api.py`.
  - **The surface-row refusal** is repeated inside `change_mcp_source`'s mutator on the fresh
    row, as well as in `resolve_target` and `normalize`.
- **`db/repositories.py`:**
  - `MCPSourceRepository.create(source, *, on_commit=None)`;
  - `update_in_txn(...)`, as in Context decision 2.

  `update(source)` stays.
  - **Re-entrancy.** The mutator and `on_commit` must not call any method that opens
    `write_transaction` (for example `merge_cache`), because the re-entrancy guard raises
    `RuntimeError`. They use raw `conn.execute`, as `mark_op` does. Docstring this.
- **`api.py`:** the two routes call the service and map `McpWriteError(status, detail)` and
  `McpSourceNotFound` (404) to today's exact responses.
- **`kinds/base.py`:** new **optional** `Kind` members, each defaulting to `None`:
  - `warnings: async (conn, enc, p) -> list[str]`;
  - `card_extras: async (conn, p) -> {title, target_gone, ...}`;
  - `needs_secret`, which stays `None` until Leg 5;
  - `editor_route`, unused on the server and not added.

  `proposal_view` gets `enc` via `get_encryptor(settings.data_dir)` when a kind has
  `warnings`.
- **`proposals/store.py`:**
  - `_card_extras` dispatches to `kind.card_extras` when it is set. The agent, rule and routine
    branches stay as they are, byte-identical.
  - `proposal_view` adds `warnings` (an empty list for kinds without the member).
  - `display_values` shows `rows` fields as one entry per key ("Header Accept", "Env
    LOG_LEVEL").
- **`kinds/mcp_server.py`** (new), registered in `REGISTRY` after `routine`.
  - **Fields** (`name` = `stored` = the change key; `path` for nested storage):

    | Field | Type | Path | Notes |
    |---|---|---|---|
    | `name` | `text` | | |
    | `type` | `text` | | `create_only`; the refusal sentence comes from the kind (decision 1), not the generic `create_only` message |
    | `command` | `text` | `("config", "command")` | `address_or_command`; it must be named `command`, as `outside.check` finds the companion field by that name; its hint says so |
    | `args` | `names`, no `ref` | `("config", "args")` | `address_or_command` |
    | `url` | `text` | `("config", "url")` | `address_or_command`; must be `http` or `https` |
    | `env` | `rows` | `("config", "env")` | `address_or_command` |
    | `headers` | `rows` | `("config", "headers")` | `address_or_command` |

  - **`operator_only`:** `cwd`, `sandbox` and `secrets`. Not `mcp_overrides`, which is an agent
    field and is already in the agent's list.
  - **`fillable = ()`.**
  - **`resolve_target(conn, ref)`:** a raw `SELECT id, name, config FROM mcp_sources`, minus the
    surface rows (the self-configuration surface check), through
    `kinds.resolve_by_id_or_name`.
  - **`normalize` refuses:**
    - `operator_only` keys;
    - unknown keys;
    - on a change, `type` (handoff);
    - fields of the other transport: on a create, by `type`; on a change, by the stored row's
      type;
    - a missing `url` or `command` on a create of that type;
    - non-string `args` items;
    - a non-`http(s)` URL;
    - a surface row as target;
    - a secret-looking row key with a non-empty value (decision 4);
    - a row key colliding with a stored Sensitive key or an OAuth-managed key (header keys
      case-insensitively, decision 5).
  - **`base`:** only the named stored keys. For `rows`, only the named rows that exist now. A
    named row absent now is **omitted** from `base`, and "absent at proposal, present at apply"
    counts as stale. `None` is never used, to avoid the AC7b collision.
  - **`target_key`:** `kinds.target_key`.
  - **`exists`, `apply`, `summary_text`, `title` and `card_title`.**
  - **`card_extras`:** the server's current name and `target_gone`, looked up by `target_id` and
    excluding surface rows.
  - **`warnings`:** DD9's three sentences, read from the stored row. They are computed **only
    for `pending` and `failed` proposals.** An applied, dismissed or withdrawn card gets `[]`,
    so it never describes the current state as if it were the proposal's.
  - **`apply`:**
    - it **pre-generates the id** for a create (`uuid4().hex[:12]`, as the route does) and puts
      it in `result["target_id"]` before calling the service, so the mark, the summary and
      `config_changed` carry it (the routine `_MarkRunner` precedent);
    - the mark stores `result` (JSON) on the row, as today. `proposal_view` exposes
      `target_id = p.target_id or (p.result or {}).get("target_id")`, so the card and a reload
      agree after a create is applied. A test pins it.
    - it builds `McpWriteDeps` from `deps.agent` (`AgentWriteDeps` already carries `mcp_repo`,
      `store` and `secret_repo`; `evals/harness.py` is unchanged);
    - it translates errors through `kinds/errors.py`.
- **`kinds/errors.py`:** `translate` and `_failure_items` map `McpWriteError` to items (or
  `gone` on 404), `McpSourceNotFound` to `gone`, and `McpStaleError` to stale rows through the
  existing agent stale builder.
- **`config_changed`** for `mcp_server` carries `kind`, `agent: null`, `target_id` (the
  pre-generated id for creates) and `fields`.
- **`proposals/guard.py` narrowing** (certain, not conditional).
  `guard.check(conn, enc, changes, *, relaxed=frozenset())` skips the **key-shape heuristics**
  (`_HEX_RUN_RE` and entropy, not `_PREFIX_RE`) only for the values of the stored keys in
  `relaxed`.
  - The MCP kind's `relaxed` is **`url`, `command` and `args` only**. `env` and `headers` values
    keep every heuristic, so a typed key under a benign header name is still refused.
  - The **stored-secret containment** rule and `_PREFIX_RE` still apply to every value.
  - Both tools pass `kind.relaxed_guard_keys`, a new optional `Kind` member defaulting to empty.
    The existing three-argument callers in `tests/test_gleepglorp_proposals_guard.py` keep
    working.
- **`target`** on `propose_change` and `fill_form`: the parameter, the agent alias, a refusal on
  conflict, and a refusal for rule and routine.
- **Descriptions.**
  - `propose_change`'s description names every kind, keeps the `read_app_config
    kind=fields name=<kind>` pointer and drops the inline field lists. It stays within 120
    tokens and 520 characters.
  - `fill_form` stays within 90 tokens. It is at 60 tokens and 295 characters today.
  - The `target` property text is minimal.
  - All of this is provisional platform text, measured in Legs 6-7.
- **`describe()`** shows a `rows` field's shape ("an object of name → value") and marks
  `address_or_command` fields ("must come from you or a page you linked"). The agent, rule and
  routine output stays byte-identical, because they have neither.
- **The guide topic** `gleepglorp/guide/mcp-servers.md` gains the proposal and fill behaviour:
  Sensitive values are entered by the operator with Sensitive turned on, sign-in happens on the
  page, and the type switch happens in the editor.
  - The topic is at 563 of 600 words, so **existing prose is trimmed** to fit.
  - No internal names, file names, `/api/` or test ids (the drift test's bans).
- **Squawk 0398, MCP part.** Repoint `the_one/mcp/README.md:15/354/398/491` and
  `the_one/mcp/__init__.py:8` to the existing `the_one/agents.md` sections:
  - "MCP F2 Client Foundation" (`:1216`);
  - "Sandbox seam" item 4 (`:1281`) for the sandbox catalog message, whose text lives in
    `the_one/mcp/errors.py`.

  Where a cited "F3 contract §5/§7" has no home, write the contract into `the_one/agents.md`
  from the code.
  - Also `the_one/self_configuration/credentials.py:42` and
    `static/js/areas/admin/system-page.js:86` ("attacker-influenced (CLAUDE.md)").
  - Write the squawk's Corrective Action and Verification. The FD marks it completed at the
    Batch B commit.
- **Carried from the Batch A review (AC7b):**
  - in `outside.check`'s declared-rows branch, `if v is None: continue`, with a test;
  - `LOADER_KEY_GLOBS` widened, with its pin updated;
  - IDN and homograph domains, and TLDs outside the allowlist, in free text added to
    `SECURITY-MODEL.md`'s residuals.
- **Docs:**
  - `the_one/agents.md`: the MCP service, `update_in_txn` and its re-entrancy rule, the
    `mcp_server` kind, and the `guard.check` narrowing;
  - `SECURITY-MODEL.md`: the MCP fields GleepGlorp may and never may set, the secret-looking key
    refusal, the case-insensitive header rule, that `env` and `headers` values sit in plain text
    in `gleepglorp_proposals` (safe because Sensitive and secret-looking keys are refused), and
    the residuals.

## Acceptance Criteria

- [ ] **AC1. The MCP routes are behaviour-identical.** These pass with their assertions
  unedited (the list from the design review's grep):
  - `tests/test_db_api.py`, `test_oauth_secrets_api.py`, `test_api_secret_mask_roundtrip.py`,
    `test_rename_carries.py`, `test_secrets_api.py`;
  - `test_self_configuration_api.py`, `test_self_configuration_external.py`,
    `test_self_configuration_surface.py`;
  - `test_api_name_rule.py`, `test_api_invalid_json.py`, `test_name_repair.py`;
  - `test_agent_mcp_tool_cache.py`, `test_mcp_last_check.py`, `test_mcp_cache_cleanup.py`,
    `test_mcp_connection_reset.py`, `test_mcp_agent_test_route.py`,
    `test_mcp_library_test_missing_values.py`, `test_mcp_stdio_test_connect.py`,
    `test_mcp_test_connection_negotiation.py`, `test_mcp_test_connection_stale_tokens.py`;
  - `test_oauth_test_connection_endpoint.py`, `test_mcp_pool_resolve.py`,
    `test_provider_api.py`, `test_store_static.py`;
  - plus any further hit of `grep -rln "mcp-sources\|create_mcp_source\|update_mcp_source" tests/`.
- [ ] **AC2. Import boundaries.** A new `ast` test asserts that `the_one/mcp/service.py` imports
  nothing from `fastapi`, `the_one.interfaces` or `the_one.gleepglorp`. The seam-import
  parametrization (`tests/test_gleepglorp_proposals_continuation.py:~296`) adds
  `gleepglorp/kinds/mcp_server.py`.
- [ ] **AC3. `update_in_txn`.** The test: read a row; then call `merge_cache` and write an OAuth
  secret through the token storage; then `change_mcp_source` with a stale-free change. Both the
  cache and the token are preserved.
  - A mutator exception writes nothing.
  - `on_commit` runs inside the transaction.
  - It returns `(before, after)`, and `updated_at` moves.
- [ ] **AC4. `change_mcp_source`.**
  - Only the named fields change. Rows merge per row. `secrets`, `_cache`, `cwd` and `sandbox`
    stay.
  - A URL or type change prunes `last_check`, `auth_posture` and `protocol_fallback` from
    `_cache`.
  - **Refused:**
    - a Sensitive-key collision, case-insensitive for headers;
    - an OAuth-managed key name;
    - a secret-looking key with a value.
  - **Stale:** a `base` mismatch, including an absent-then-present row, raises unless
    `override`.
  - The name rule, the reserved name, the surface refusal and the config validation apply.
  - The side effects run after commit, under exactly the route's conditions, and not on a
    failure.
  - A test covers each.
- [ ] **AC5. The `mcp_server` kind.**
  - Registered and described (`rows` and declared markers shown).
  - Every `normalize` refusal in Outputs has a test.
  - Id-first resolution, and a duplicate-name refusal.
  - The `base` rules.
  - `card_extras` gives the title and `target_gone` for a create, a change and a deleted target.
  - The agent, rule and routine card extras and `describe()` are byte-identical: their existing
    tests pass unedited.
- [ ] **AC6. Approve.**
  - A create and a change apply through the service, with the mark in the same transaction.
  - `config_changed` carries `kind: "mcp_server"`, `agent: null` and the `target_id`, which for
    a create is the pre-generated id, equal to the stored row's id.
  - A stale change gives the stale rows. A deleted target withdraws. A failure carries the
    service's items.
  - `evals/harness.py` is unchanged.
- [ ] **AC7. The guard on MCP fields** (DD7 per-kind falsification), through the real
  `propose_change` on an untrusted turn:
  - a URL from a linked page → allowed;
  - from an unlinked page → refused;
  - a stdio command and args from a linked README in JSON config form → allowed;
  - from a search result → refused;
  - `NODE_OPTIONS` from a linked page → refused, and typed → allowed.

  **`guard.check` with the relaxed keys** (`url`, `command`, `args`):
  - passes `ghcr.io/acme/mcp@sha256:<64 hex>` (command or args), a UUID-path URL, `npx -y
    @modelcontextprotocol/server-github` and `uvx mcp-server-fetch`;
  - **still refuses:**
    - `https://x.test/mcp?api_key=<a stored secret value>` (containment);
    - a `headers` row `X-Custom: sk-ant-…` or a 40-hex value under a benign name (rows keep
      the heuristics);
    - an `args` item `--token=abc123` (the secret-looking flag rule);
  - agent text with a hex run is still refused (agent behaviour unchanged).

  The safety cases are falsified.
- [ ] **AC7b. Carried from the Batch A review:** the `None` row skip (tested), the widened
  `LOADER_KEY_GLOBS` (pin updated), and the `SECURITY-MODEL.md` residuals.
- [ ] **AC8. Warnings.** DD9's three sentences, each tested, and none on a plain change.
  `proposal_view.warnings` is an empty list for the other kinds.
- [ ] **AC9. `target` and descriptions.** As in Outputs. These pins are updated:
  - `tests/test_gleepglorp_proposals_tool.py:67/69` and `tests/test_gleepglorp_fill_tool.py:77/80`
    (`set(props)` with `target`);
  - `test_the_description_stays_thin`, rewritten to require each kind name from `REGISTRY`,
    with the character cap;
  - the token pins (120, and a new `fill_form` 90).
- [ ] **AC10. Pins this leg trips** (each updated, none weakened):
  - `tests/test_gleepglorp_proposals_shape.py:56-64` (the operator-only set gains the MCP
    entries; the agent six stay);
  - `tests/test_gleepglorp_kinds.py:59` (the exact tuple) and its exactly-three `REGISTRY`
    test, which becomes four;
  - `tests/test_gleepglorp_proposals_shape.py:107/121` (the kind list and the "Valid names"
    message);
  - `tests/test_gleepglorp_targets.py:58` (parametrization: add `mcp_server` if the test is
    about every kind);
  - the seam-import list;
  - the guide drift test.
- [ ] **AC11. Guide and squawk.**
  - The guide test passes, with the topic at most 600 words.
  - The squawk 0398 grep (`grep -rn 'CLAUDE.md' the_one/ scripts/ evals/`) shows no citation
    of a missing section, and every repointed heading exists.
- [ ] **AC12. No regression.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips, and ruff is clean.
  - These lanes pass, one at a time: `mcp`, `mcp-connection` and `gleepglorp` (it holds the
    kinds, proposals and drawer files that assert on `proposal_view` and the kind list).
  - `tests/test_evals_gleepglorp*.py` and `tests/test_evals_freeze.py` pass. No frozen evals file
    enumerates kinds or tool parameters (confirmed at design).

## Verification Steps

- `.venv/bin/python -m pytest tests/test_mcp_service.py tests/test_gleepglorp_kind_mcp.py <the AC1 list> tests/test_gleepglorp_*.py tests/test_evals_gleepglorp*.py tests/test_evals_freeze.py -x --timeout 60`.
- Lanes `mcp`, `mcp-connection`, then `gleepglorp`, one at a time, in the background. Then the
  unit tier.

## Implementation Guidance

1. **The repository hooks** and their tests (AC3).
2. **The service.**
   - `create` and `replace` first, moved verbatim with exact details.
   - Thin routes, then run the AC1 list. Stop here if anything moved.
3. **`change_mcp_source`** on `update_in_txn` (AC4).
4. **The `Kind` members, `_card_extras` dispatch, `proposal_view` warnings and the row display,**
   with the agent, rule and routine outputs byte-identical.
5. **`kinds/mcp_server.py`** (AC5, AC6, AC8), `errors.py` mapping, and `config_changed`.
6. **The `guard.check` narrowing,** the declared keys passed from both tools, and the AC7 cases.
7. **`target`, the descriptions and the pins** (AC9, AC10).
8. **AC7b, the guide, squawk 0398 and the docs.**
9. **Gates** (AC12).

## Edge Cases

- **A create proposal naming `cwd` or `sandbox`:** refused (`operator_only`).
- **A change naming a plain header row that exists:** replaced. The guard applies to the new
  value.
- **Self-configuration surface rows:** never a target, and the reserved name is refused on
  create.
- **Two servers with one name:** a name is refused, listing both ids. The id works.
- **Approved after deletion:** gone, so the proposal is withdrawn.
- **A rename by proposal:** the carry runs after commit, and a test pins that an attached
  agent's override key follows.
- **`Authorization` proposed with an empty value:** a proposal cannot carry an empty handoff row
  (it would store an empty plain header), so it is refused. Only fills carry handoff rows
  (Leg 4b).

## Files Affected

- `the_one/mcp/service.py` (new), `the_one/db/repositories.py`, `the_one/interfaces/web/api.py`.
- `the_one/gleepglorp/kinds/base.py`, `kinds/__init__.py` (`REGISTRY`, `describe`),
  `kinds/errors.py`, `kinds/mcp_server.py` (new).
- `the_one/gleepglorp/proposals/store.py`, `proposals/guard.py`, `proposals/tool.py`,
  `fill/tool.py`, `the_one/gleepglorp/outside.py` (AC7b).
- `the_one/gleepglorp/guide/mcp-servers.md`.
- **Squawk 0398 targets:** `the_one/mcp/README.md`, `the_one/mcp/__init__.py`,
  `the_one/self_configuration/credentials.py`,
  `the_one/interfaces/web/static/js/areas/admin/system-page.js` (comment only), and
  `squawks/0398-stale-claude-md-citations.md`.
- **Tests:**
  - new: `tests/test_mcp_service.py`, `tests/test_gleepglorp_kind_mcp.py`, and an import-boundary
    test;
  - updated pins: the AC9 and AC10 files.
- **Docs:** `the_one/agents.md`, `SECURITY-MODEL.md`.

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** All folded in above:
- **High:**
  - `_card_extras` would have rendered MCP cards as routines, so dispatch moves to
    `Kind.card_extras`;
  - the new `Kind` members and their async signatures with the encryptor;
  - the pins this leg trips (AC10);
  - the guide topic's word headroom.
- **Medium:**
  - `McpWriteError(status, detail)`, with exact details;
  - `update_in_txn`'s re-entrancy, `(before, after)`, `updated_at`, the pruning and the
    `on_commit` signature;
  - late-bound getters, and the function-local `_evict_all_for_source`;
  - deps from `deps.agent`, with no lazy build;
  - the real AC1 test list;
  - row semantics: case-insensitive headers, OAuth key names, secret-looking keys, `base` for
    absent rows;
  - the missing normalize refusals;
  - a pre-generated create id for the mark and the frame;
  - the certain `guard.check` narrowing, with containment kept;
  - the `gleepglorp` lane in AC12;
  - 4a is never shipped alone.
- **Low:**
  - the real squawk 0398 targets;
  - the description budget notes;
  - the exact AC7b fix.

Cycle 2 (Developer, Sonnet): **approve with changes.** Every cycle-1 finding was resolved.
Folded in:
- **The secret-looking key rule is one algorithm,** pinned by a table, applied to `args` flags
  too, and to changes as well as creates.
- **The `guard.check` relaxation covers only `url`, `command` and `args`.** Rows keep their
  heuristics, which closes a typed-secret-in-a-header hole.
- **The validators move into the service,** with `api.py` keeping wrappers.
- **Warnings show only on pending and failed cards.**
- **A create's `target_id` reaches the view** through `result`.
- **The surface refusal is repeated in the mutator.**

The two-cycle cap is reached. These items are specific and mechanical.

## Citation Audit

Verified against `f4ee1a12` (design review cycle 1):
- `api.py:3370/3420` the MCP routes, with the step order in Context; `:3202`
  `_validate_mcp_source_config`; `:~3772` other users of `_config_without_cache` and
  `_drop_source_agent_tool_cache` — verified.
- `db/repositories.py:1326` `MCPSourceRepository` (`create`, `update`, `merge_cache` under
  `write_transaction`); `:270` `AgentStore.save(precheck=, on_commit=)` — verified.
- `kinds/base.py` `Kind` members (name, label, summary, fields, normalize, exists, apply,
  summary_text, operator_only, fillable, actions, title, card_title, resolve_target) — verified.
- `proposals/store.py` `_card_extras` (agent, rule, else routine) — verified.
- `proposals/guard.py` `check(conn, enc, changes)`, `_HEX_RUN_RE` — verified.
- `outside.py` declared-rows `str(v)` — verified.
- `tests/test_secrets_api.py:542` (patches `api._agent_store`); the `_evict_all_for_source` patch
  sites — verified.
- `guide/mcp-servers.md` 563 words; `tests/test_gleepglorp_guide.py` `MAX_WORDS = 600` and its
  bans — verified.
- `the_one/agents.md:1216` "MCP F2 Client Foundation", `:1281` "Sandbox seam" — verified.
