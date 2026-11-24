# Leg: 04a-settings-kinds-server

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

Add the `tool_config` and `app_settings` kinds on the server. The leg delivers:
- two write services extracted from their routes, with in-transaction hooks:
  `the_one/tools/config_service.py` and `the_one/app_settings_service.py`;
- the two kind modules on the Leg 1a hooks;
- the first real implementation of `page` addressing;
- the fields-view attribute (`FieldSpec.applies_to`) that Leg 1a deferred here;
- the tool name in the Settings page line;
- the guide.

Both kinds can be proposed and their fills recorded. Their editor seams, follows and client
kind registrations are Leg 4b.

## Context

- **Flight decisions:**
  - DD2 (the hooks; the fields-view attribute);
  - DD3 (the service pattern);
  - DD7 (tool configs);
  - DD8 (app settings);
  - DD9 (`config_changed`);
  - DD10 (the guard);
  - DD11 (provisional names, the fields view);
  - DD13 (pins).

  Leg 1a landed the hooks: `addressing` (with `page`), the mode-aware action gate
  (`kinds/__init__.py:239`), `operator_only_message`, `action_refused`, `FieldSpec.fill_refused`,
  `keyerror_is_gone`, `stored_get` / `stored_set` and `id_fill_extras`. Leg 3a added
  `typed_items` and the two Library services. The checklist is "Adding a kind: the checklist" in
  `the_one/agents.md`.
- **Batch C.** Batch B (Legs 3a, 3b) is committed before this leg starts. Leg 4b is designed
  after this leg lands; Batch C commits both together.
- **The templates to copy:** `the_one/knowledge/service.py` and `kinds/knowledge_base.py` (Leg 3a)
  for the service shape (`WriteDeps`, `WriteError(status, detail)`, `NotFound`,
  `StaleError(fields)`, a local `validation_detail` copy, `precheck=` / `on_commit=`), the AST
  import-boundary test (`tests/test_knowledge_service.py:54-66`) and the deterministic race test
  (`tests/test_provider_service.py`: hold `write_transaction`, then write raw).
- **Tool configs today** (`the_one/interfaces/web/api.py`; the flight spec's line numbers have
  drifted by 15-30 lines, these are current):
  - `GET /tools/configs/{name}` (`:840`) merges `{**row.config, **row.secrets}` and masks the
    secret fields;
  - `PUT /tools/configs/{name}` (`:1021`): `existing = await repo.get(name)` **outside** any
    transaction (`:1053`), then `_compute_tool_config_update` (`:876-958`), then `repo.upsert`
    (`:1059`). This is the read-outside-the-transaction race DD3 fixes.
  - `_compute_tool_config_update` raises `HTTPException(422, _validation_detail(e))` (`:931`),
    has a fallback retry without stored hidden values (`:906-925`), and **drops every secret
    field that is missing or empty** in the incoming config; only a masked value keeps the stored
    one (`:941-958`). It also materialises every Config default into the stored `config`
    (`model_dump()` of the validated model).
  - `_merge_hidden_fields` (`:736`), `_narrowing_added` (`:960`), `_impact_of` (`:973`, sync and
    blocking; the impact route runs it in `asyncio.to_thread` at `:1017` and returns
    `{"agents": []}` early when no agent has an override for the tool, `:1015`).
  - `_secret_field_names` at `api.py:3118` and a twin at `gleepglorp/view_core.py:521`.
  - `ToolConfigRepository` (`db/repositories.py:3144`): `get` raises `KeyError` (`:3179-3184`);
    `upsert(name, config, secrets=None, enabled=True)` (`:3186`) opens its own
    `write_transaction`. No hooks. A missing row means `enabled=True, config={}`.
  - **Per-tool rows** (DD7): `tools/builtins.py:228-240` resolves each tool from its own row.
    `config_fields` (`tools/base.py:77`; `None` = all fields shown, `()` = none).
- **The settable set per tool** (DD7's rule: the allowlist ∩ the fields the tool shows − secrets;
  measured by the survey; this table corrects DD7's, which listed only the path-list tools):

  | Tool | Settable (besides `enabled`) |
  |---|---|
  | `shell`, `python_exec`, `shell_session_send` | `timeout_seconds_default`, `timeout_seconds_max`, `output_cap_bytes` |
  | `shell_session_start` | `pty_session_idle_ttl_seconds`, `max_concurrent_sessions` |
  | `shell_session_close`, `shell_session_list` | none (`config_fields=()`) |
  | `read_file`, `edit_file`, `grep` | `read_size_cap_bytes` (`config_fields=None`: they show all four Filesystem fields) |
  | `write_file`, `delete_file`, `move_file`, `mkdir`, `glob`, `list_dir` | none (path lists only) |
  | `http_request`, `fetch_url`, `download_file` | `timeout_seconds_default`, `timeout_seconds_max`, `response_size_cap_bytes` |
  | `web_search` | `search_backend`, `searxng_base_url`, `google_pse_cse_id` |
  | `send_to_platform_channel`, `fetch_channel_history`, `find_platform_destination`, `current_time` | none (`_EmptyConfig`) |

  Bounds are the same in every Config class that has a field (`timeout_*` 1-3600,
  `output_cap_bytes` / `read_size_cap_bytes` / `response_size_cap_bytes` 1024-104857600,
  `pty_session_idle_ttl_seconds` 10-3600, `max_concurrent_sessions` 1-50), so one `FieldSpec` per
  field name works. `timeout_seconds_default <= timeout_seconds_max` is a cross-field validator
  (`execution.py:321`, `_web_config.py:295`).
- **App settings today:**
  - **Date and time:** `PUT /time-settings` (`api.py:~2800`) guards the body keys (`mode`, `zone`
    only), validates `TimeZoneSetting` (`time_zones.py:171`; `mode` `system`|`zone`), maps a
    `ValidationError` to one sentence through `_time_settings_error` (`:2773-2791`), then
    `time_zones.save_setting` (`:234`, through `AppMetadataRepository.set`, its own transaction)
    and `_poke_scheduler()` (`:1819`).
  - **Knowledge indexing:** `PUT /knowledge-settings` (`api.py:~2950`) guards top-level keys
    (`embedding`, `chunking`, `monitoring`, each an object), merges partials over the current
    models, validates (`ChunkingSettings` `knowledge/settings.py:108`, `MonitoringSettings`
    `:179`), calls `save_knowledge_settings` (`:252`: **three separate transactions**, and it
    rewrites the untouched `embedding` key), then `await _after_monitoring_settings_changed(...)`
    **unconditionally** (`:3015`; `tests/test_db_api.py:3252/3270` monkeypatch it on the api
    module, and `~3290` pins the call even for a chunking-only body).
  - The page saves chunking and monitoring in one PUT
    (`static/js/areas/admin/knowledge-settings-page.js:338-355`).
  - `AppMetadataRepository` (`db/repositories.py:3254`): `get` is a plain read (safe inside
    another `write_transaction` on the shared connection); `set` (`:3272`) opens its own
    transaction, and same-task re-entry raises (`db/_write_lock.py:52`).
  - The embedding warm-up is not part of app settings (it serves only knowledge-base create).
- **`page` addressing is declared only.** Its sole behaviour is the `target_args` refusal
  (`kinds/__init__.py:150`). `kinds.target_key` (`:95`) knows only `{kind}:{target_id}` and
  `{kind}:new:{name}`. The `config_changed` frame (`proposals/apply.py:231-243`) passes
  `target_id` through, so a page key works there unchanged.
- **`FieldSpec.path` is read by no production code.** `stored_get` raises `KeyError` on an absent
  nested key, and a never-saved tool row has `config == {}`.
- **`_check_keys` runs before the kind's `normalize`,** against the union of the kind's fields,
  and `operator_only_message(names)` gets names only, not the target.
- **The page line:** `page.py` drops the Settings item in `_route` (`:177-179`) and
  `_resolve_item` (`:254-255`); `tests/test_gleepglorp_page.py:134-143` pins "never the item".
- **Description budgets** (measured with the cached `o200k_base` at `evals/.cache/tiktoken`, so
  the token tests run here): `propose_change` 95/120 tokens, 396/520 characters; `fill_form`
  89/90 tokens, 397/440 characters.
- **Guide budgets** (`tests/test_gleepglorp_guide.py:32`, 600 words per file): `settings.md` 494,
  `agent-tools.md` 588.
- **Leg-design decisions,** refining the flight spec. The FD records them in the log.
  1. **`page` addressing is implemented in the `app_settings` kind,** not in `kinds.target_key`.
     Its `normalize` derives the page key from the fields named and returns
     `target_id = <page key>` and `target_key = "app_settings:<page key>"`. `exists` returns
     `True`; there is no `resolve_target`. The page keys are the route sections `date-and-time`
     and `knowledge-indexing` (`page.py:40-48`).
  2. **The fields-view attribute is `FieldSpec.applies_to: tuple[str, ...] = ()`.** `describe()`
     emits `applies_to` (a list) only when it is non-empty, so every existing kind's output is
     unchanged. For `tool_config` it lists the tools that expose the field (computed from
     `_TOOL_CLASSES` at import; `enabled` leaves it empty, meaning every tool). For
     `app_settings` it holds the page key.
  3. **Per-tool refusals live in the kind's `normalize`,** after the tool is resolved:
     - a field on the allowlist that this tool does not show: "The {tool} tool has no
       {label} setting.";
     - every Config field of any built-in tool that is **not** on the allowlist is in
       `operator_only` (computed at import as the union of all Config fields − the allowlist,
       iterating `builtin_tool_names()`, deduplicated, then `sorted()`, so the pinned
       `OPERATOR_ONLY_FIELDS` tuple has a deterministic order), so `_check_keys` refuses it
       through `operator_only_message` before `normalize`. A new Config field is operator-only
       until someone adds it to the allowlist. `test_gleepglorp_kinds.py` pins the real
       resulting names.
  4. **`operator_only_message`** for `tool_config`: when any name is a secret field
     (`google_pse_api_key`, `brave_api_key`, `tavily_api_key`): "Only you enter API keys, on the
     [Built-in tools](#settings/tools) page. I never take or fill them."; otherwise: "Only you can
     change {labels}, on the [Built-in tools](#settings/tools) page." (`#settings/tools` is on
     `p5d`'s route list, the FD's planning decision.)
  5. **The turn-on warning's tools come from a server-side set,** since the categories exist only
     in `static/js/tool-categories.js`: `TURN_ON_WARNED` = the `execution` and `web` categories
     plus the file-writing tools `write_file`, `edit_file`, `delete_file`, `move_file`, `mkdir`.
     A parity test reads the JS `TABLE` (reuse `tests/test_tool_categories.py`'s parser) and
     asserts the set equals `execution ∪ web ∪ {the five}` and that the five are in
     `filesystem`.
  6. **The narrowing warning is proposal-only and gated before any agent load** (design review).
     - The kind's `warnings` runs on every open card render (`proposal_view`, and `fill_view`
       for fills), and `agents.tool_overrides` is encrypted, so even the route's early return
       (`api.py:1015`) comes after loading every agent.
     - So the warning runs only in `mode="propose"` (a fill's operator sees the editor's own
       impact dialog on Save), and only when a named numeric field moves **below** its base.
       Path lists, which are what else can narrow, are operator-only here. For `enabled`,
       `search_backend`, `searxng_base_url`, `google_pse_cse_id` and any numeric value at or
       above its base, no agent is loaded.
     - When it does run, it loads the agents and runs `impact_of` in `asyncio.to_thread`, as the
       route does. Its sentence reuses the editor's impact-dialog wording (`tools-editor.js`;
       read it and pin the sentence).
  7. **The private-address warning checks the literal host only, with no DNS.** It fires when a
     new `searxng_base_url`'s host is `localhost` or an IP literal that
     `_web_config._is_ssrf_blocked` blocks, and the host is not already in the effective
     `extra_allowed_hosts` of the row the provider resolves the shared `WebConfig` from: the
     first tool in `_TOOL_CLASSES` whose Config is `WebConfig` (`http_request` today;
     `builtins.py:195-224`). Resolve it the same way the provider does, not by name. A test
     stores the host only on `fetch_url`'s row and expects the warning.
  8. **The tool-config base holds effective values** (the stored value over **that tool's own**
     `cls.Config` default; `enabled` defaults to `True`), never the raw stored `config`, so a
     never-saved row works. `built_in_tools_view` is not used for the base (it shows stored
     values only).
  9. **Validation at normalize, in two steps** (design review).
     - **First the shape-level type check** (`shape.py`'s integer, boolean and text checks with
       the `FieldSpec` bounds), which refuses `True` for an integer and `"30"` for a number.
       The checked values are what is stored.
     - **Then a dry run of the real write,** `compute_tool_config_update(cls, name, candidate,
       existing)` over the effective row (for `app_settings`, the page's pydantic models over the
       stored values). This applies bounds, the `search_backend` choices, the cross-field
       timeout rule and the same hidden-field fallback the PUT uses, so an unrelated bad stored
       hidden value does not refuse the proposal.
     - **The message:** the first error's `msg`, with pydantic's `"Value error, "` prefix
       stripped and stored names mapped to the model-facing field names (`size_chars` →
       `chunk_size_chars`, `overlap_chars` → `chunk_overlap_chars`, `zone` → `time_zone`,
       `mode` → `time_zone_mode`), raised as `ShapeError`. `time_zone_mode: "zone"` with no zone
       stored or named is refused with `time_zones.ERR_ZONE_REQUIRED`'s sentence.
  10. **Routes stay as they are, minus the race.**
      - The tool-config PUT and the impact route call the service; their statuses and details
        are unchanged, and `ToolConfigWriteError(status, detail)` maps to today's 422.
      - The time PUT keeps its body-key guard and `_time_settings_error` mapping on the route
        and calls the service to write. The knowledge PUT keeps its guards and its unconditional
        `_after_monitoring_settings_changed` call on the route.
      - `save_knowledge_settings` becomes one transaction (through the new setter; it needs a
        `write_transaction` import), keeping its `conn` signature and still writing all three
        keys for its existing callers (`test_kb_manager.py`, `test_knowledge_settings.py`).
      - **Known gap, recorded not fixed:** the knowledge PUT still reads
        `load_knowledge_settings` outside any transaction and rewrites `embedding`. The kind's
        own change path does not share that race (it reads and writes in one transaction).
      - `api._poke_scheduler` stays (`tests/test_routines_scheduler.py:451` calls it).
  13. **Post-commit side effects never fail an applied proposal** (design review).
      `apply_proposal` passes only `mark` as `on_commit` (run inside the repository's
      transaction). A raise after commit would leave the row `applied` while step (c) re-reads it
      and returns `already_applied`, with no `proposal_changed` or `config_changed` frame and no
      continuation. So the services run their post-commit hooks inside `try` / `except` with a
      logged warning. The hooks are injected through `AppSettingsWriteDeps` as `poke` and
      `apply_monitoring` callables (`apply_monitoring` is async, through `get_watch_manager()`).
      The routes keep their own `_poke_scheduler` and `_after_monitoring_settings_changed`
      calls, so the `tests/test_db_api.py:3245-3270` monkeypatch tests stay valid.
  14. **The stale check lives in `mutate`, with no `precheck`,** as in
      `KnowledgeBaseRepository.update_in_txn`. `update_in_txn` takes `mutate` and `on_commit`
      only.
  15. **Kind surface, spelled out** (design review):
      - `tool_config`: `label="built-in tool"`, `target_noun="A built-in tool"` (so
        `target_args` reads "A built-in tool is named with target, not agent."), `exists` is
        `name in builtin_tool_names()` (never the repository: a never-saved row raises
        `KeyError`), the not-found sentence "There is no built-in tool named {name}.", and
        `title` / `card_title` / `summary_text` naming the tool ("Change the web_search tool"),
        never `agent_name` (it is `None`).
      - `app_settings`: `label="app settings"`, titles from the page label ("Change Date and
        time", "Change Knowledge indexing"), and an `operator_only` entry for the fixed
        embedding settings, the model-facing names `embedding_backend`, `embedding_model_id`,
        `embedding_dim` and `vector_store` (from `EmbeddingSettings`, `knowledge/settings.py:82-84`,
        and `VECTOR_STORE_KEY`, `:35`), with "The embedding model and vector store are fixed;
        they can't be changed." None of them may collide with any kind's field name. A Knowledge indexing fill reports
        `stale` rows through a `stale_fn`, as the id kinds do.
      - Use the public `builtin_tool_names()` wherever a name set is needed, not
        `_TOOL_CLASSES`.
      - `search_backend` carries a `hint` listing its five choices, since `describe()` has no
        enum.
      - The services import `validation_detail` from `the_one.agent.write_checks`, as `api.py`
        does, rather than keeping a copy.
  11. **`agent-tools.md` gets no edit** (12 words spare). The GleepGlorp sentences for Tools,
      Date and time and Knowledge indexing go in `settings.md` only. This refines DD7's guide
      line.
  12. **The client-registry pin is relaxed provisionally.**
      `tests/test_gleepglorp_client_helpers.py:57-75` asserts the client kinds equal
      `kinds.KINDS`. This leg widens its script regex from `areas/studio/` to `areas/[a-z]+/` (Leg
      4b's files are under `areas/admin/`) and compares against `kinds.KINDS` minus a named
      `_PENDING_CLIENT_KINDS = ("tool_config", "app_settings")`, asserting those are the
      registry's last two. A comment names Leg 4b, which empties the tuple.

## Inputs

- The tree with Batch B committed.
- **Key files:**
  - `the_one/gleepglorp/kinds/{base,__init__,errors,deps,knowledge_base,secret}.py`;
  - `the_one/gleepglorp/proposals/shape.py` (`FieldSpec`, `stored_get` / `stored_set`);
  - `the_one/gleepglorp/outside.py`, `page.py`, `view_core.py`, `view_fields.py`;
  - `the_one/interfaces/web/api.py` (tool-config, time and knowledge-settings routes);
  - `the_one/db/repositories.py` (`ToolConfigRepository`, `AppMetadataRepository`);
  - `the_one/tools/{builtins,base,execution,filesystem,_web_config,_web_search_config}.py`;
  - `the_one/time_zones.py`, `the_one/knowledge/settings.py`;
  - `the_one/gleepglorp/guide/settings.md`.

## Outputs

- **`the_one/tools/config_service.py`:**
  - `ToolConfigWriteDeps` (the repository; the agent-store factory for the impact computation);
  - `ToolConfigWriteError(status, detail)`, `ToolConfigStaleError(fields)`;
  - `compute_tool_config_update(cls, name, data, existing)` (moved; raises
    `ToolConfigWriteError` instead of `HTTPException`), `merge_hidden_fields`,
    `secret_field_names`, `narrowing_added`, `impact_of` (moved);
  - `effective_values(name, row) -> dict` (stored over defaults, plus `enabled`);
  - `replace_tool_config(deps, name, data)`, the PUT, read and written in one transaction;
  - `change_tool_config(deps, name, changes, *, base=None, override=False, on_commit=None)`,
    merging the named fields over `{**config, **secrets}` so no stored secret is dropped.

  `api.py` re-exports the moved helpers under their old names (`_secret_field_names`,
  `_merge_hidden_fields`, ...) for the route tests (`canonical-import + convenience-re-export`).
  `view_core.py`'s twin of `_secret_field_names` imports the service's.
- **`db/repositories.py`:**
  - `ToolConfigRepository.update_in_txn(name, mutate, *, on_commit=None) -> (before, after)`,
    where `before` is `None` for a missing row (an upsert);
  - `AppMetadataRepository.set_in_txn(conn, key, value)`, a raw `INSERT ... ON CONFLICT` for use
    inside an open `write_transaction`.
- **`the_one/app_settings_service.py`:**
  - `AppSettingsWriteDeps` (the connection, plus the injected `poke` and async
    `apply_monitoring` callables, decision 13), `AppSettingsWriteError(status, detail)`,
    `AppSettingsStaleError(fields)`;
  - `save_time_setting(deps, setting)` (the route's write, one transaction, scheduler poke after
    commit);
  - `save_knowledge_settings_in_txn` or equivalent for the route (one transaction);
  - `change_time_settings(deps, changes, *, base=None, override=False, on_commit=None)`;
  - `change_knowledge_settings(deps, changes, *, base=None, override=False, on_commit=None)`,
    writing only the keys it changes (`knowledge.chunking` and / or `knowledge.monitoring`).

  Post-commit side effects: the scheduler poke after a time change; the watcher's
  `apply_settings` (through `get_watch_manager()`) after a monitoring change. Never after a
  rollback.
- **`the_one/gleepglorp/kinds/tool_config.py` and `app_settings.py`,** one `KIND` each, appended
  to `REGISTRY` after `secret`, in that order.
- **`FieldSpec.applies_to`** and its `describe()` emission; `view_core.ALLOWED` (the fields
  view's nested keys), `OPERATOR_PATHS` and `tests/test_gleepglorp_views_provenance.py`
  `REVIEWED_ALLOWED` updated.
- **`page.py`:** `settings/tools/{name}` carries the tool name when it resolves against
  `_TOOL_CLASSES`.
- **`kinds/errors.py`:** `translate`, `_is_gone` and `_failure_items` learn the new services'
  errors.
- **Descriptions:** `propose_change` appends `tool_config` and `app_settings` to its kind list,
  provisionally (DD11). `fill_form`'s text is **not** touched; its enum grows through
  `kinds.FILLABLE`.
- **Guide:** `settings.md`.
- **Docs:** `the_one/agents.md` (the two services and kinds, `applies_to`, `page` addressing,
  the page-line item rule); `SECURITY-MODEL.md` (the tool-config allowlist, the key handoff).
- **Tests:** listed under Files Affected.

## Acceptance Criteria

- [ ] **AC1. Tool-config service and the PUT race.**
  - `GET`, `PUT /tools/configs/{name}` and `POST /tools/configs/{name}/impact` behave as today:
    same statuses and details. Every existing route test file that drives them passes with its
    assertion lines unedited (grep `/tools/configs` in `tests/`).
  - The PUT reads and writes inside one `update_in_txn`. **Race test:** with the write lock held,
    a raw write commits a different `timeout_seconds_max`; a PUT that read before it must not
    write over it with stale data (copy the provider service's pattern). Falsify by moving the
    read back outside the transaction.
  - `tests/test_api_tool_configs.py` and `tests/test_tool_config_text.py` still import the
    helpers from `api` and pass.
- [ ] **AC2. A change never drops a stored secret.** A `change_tool_config` of `search_backend`
  and of `timeout_seconds_max` on a `web_search` row with all three keys stored keeps every key
  byte for byte (read raw from the row). Falsify by merging over `config` alone. A second test
  pins that a **config-field** change on a never-saved row materialises the Config defaults
  (today's PUT behaviour, kept and documented), while an `enabled`-only change on a never-saved
  row leaves `config == {}`. `enabled` is split from the named fields into the top-level
  `data["enabled"]` before the merge.
- [ ] **AC3. The settable set is pinned per tool.** A test walks every tool in `_TOOL_CLASSES` and
  asserts its exact settable set (the Context table plus `enabled`). Another asserts
  `operator_only` equals the union of all Config fields minus the allowlist, and contains at
  least the DD7 list (`path_allowlist`, `path_denylist`, `allow_binary_files`,
  `command_denylist`, `sandbox_network_allowed`, `host_allowlist`, `host_denylist`,
  `extra_allowed_hosts`, `default_user_agent`, `redirect_cap` and the three API keys).
- [ ] **AC4. `tool_config` normalize.**
  - Target: an exact tool name (after `strip().lower()`) in `builtin_tool_names()`; anything
    else is refused with "There is no built-in tool named {name}." `agent` is refused by
    `target_args` with "A built-in tool is named with target, not agent." (pinned).
  - Integer fields refuse `True` and `"30"` (the shape-level check runs first, decision 9).
  - `create` is refused by the action gate in both modes.
  - An operator-only field is refused with decision 4's sentences (the key sentence for a secret
    field). A field the tool does not show is refused with "The {tool} tool has no {label}
    setting." Each is falsified.
  - A value out of bounds, a bad `search_backend` and `timeout_seconds_max` below the effective
    default are refused at normalize with the model's message.
  - `base` holds the effective values of the named fields (decision 8).
- [ ] **AC5. `tool_config` warnings,** each with a test:
  - narrowing (proposals only, decision 6): names the agents, matching the impact dialog's
    sentence; **no agent is loaded** for `enabled`, the text fields, or a numeric value at or
    above its base (a test counts `store.load` calls), and none in `mode="fill"`;
  - turn-off (`enabled: false`): "Turning {tool} off removes it from every agent until it is
    turned back on.";
  - turn-on (`enabled: true`, a `TURN_ON_WARNED` tool, row currently off): "Turning {tool} on
    lets every agent that allows it use it.";
  - backend handoff (`google_pse`, `brave`, `tavily` with no stored key): "Enter the {backend} API
    key on the [Built-in tools](#settings/tools) page; search fails until then." Not shown when
    the key is stored;
  - private address (decision 7), not shown when the host is already in `extra_allowed_hosts`.
  - The `TURN_ON_WARNED` parity test against `tool-categories.js`.
- [ ] **AC6. `tool_config` apply, stale and the guard.**
  - Approve writes through `change_tool_config`; `enabled` is the row's top-level column.
  - Another write between proposal and approval to a named field makes it stale
    (`ToolConfigStaleError` → `translate` → stale); a write to another field does not.
  - `searxng_base_url` and `google_pse_cse_id` are `address_or_command`; `searxng_base_url` is in
    `relaxed_guard_keys`. Falsification both ways per field: a value seen only in outside content
    is refused; one the operator typed (tier 1) or a page they linked (tier 2) passes.
  - A fill of `enabled` and of a numeric field records with `target_id` = the tool name and
    `fill_extras` from `id_fill_extras`.
- [ ] **AC7. `app_settings`: page addressing.**
  - The page key comes from the fields named: Date and time fields → `date-and-time`, Knowledge
    indexing fields → `knowledge-indexing`; `target_key` is `app_settings:<page>`.
  - Fields from both pages: "One proposal changes one Settings page; propose Date and time and
    Knowledge indexing separately."
  - `agent` or `target` passed: the existing `target_args` sentence.
  - An approved proposal's `config_changed` frame carries `kind: "app_settings"` and
    `target_id` = the page key (an end-to-end test through apply).
- [ ] **AC8. `app_settings` fields and validation.**
  - The six DD8 fields, each with `applies_to` = its page key and a `path` to its stored key.
  - `time_zone` is validated as an IANA name (`TimeZoneSetting`); chunking through
    `ChunkingSettings` (200-2000, overlap at most half); monitoring through `MonitoringSettings`
    (10-86400). Refused at normalize with the model's message.
  - A `time_zone` change alone while the stored mode is `system` also sets `time_zone_mode` to
    `zone`; the card shows both rows. Tests pin the stored mode explicitly.
  - **Fill:** the two Date and time fields carry `fill_refused` ("Date and time saves as soon as
    you choose; I'll propose it instead."); a Knowledge indexing fill records with `target_id` =
    `knowledge-indexing`.
- [ ] **AC9. `app_settings` service and side effects.**
  - `change_knowledge_settings` writes only the keys it changes, in one transaction; `embedding`
    is untouched (read raw).
  - The time change pokes the scheduler after commit; a monitoring change calls the watcher's
    `apply_settings` after commit; neither runs when the apply is refused (stale or already
    resolved).
  - **A raising post-commit hook** (the injected `apply_monitoring` raises) still yields an
    `applied` proposal with its `proposal_changed` and `config_changed` frames, and the error is
    logged (decision 13). Falsify by removing the `try`.
  - Stale: another write to a named field between proposal and approval makes it stale. When
    the kind adds `time_zone_mode` to a `time_zone` change, both are touched fields and both are
    in `base`.
  - A Knowledge indexing fill reports `stale` rows when the stored value moved after the fill.
  - `PUT /time-settings` and `PUT /knowledge-settings` behave as today; their route tests,
    including the `tests/test_db_api.py` monkeypatch tests, pass unedited.
  - `save_knowledge_settings` writes in one transaction; `tests/test_knowledge_settings.py`
    passes unedited.
- [ ] **AC10. `app_settings` warnings:** the zone, chunking and `watch_enabled: false` sentences
  of DD8, each with a test.
- [ ] **AC11. Fields view.** `read_app_config(view="fields", name="tool_config")` shows
  `applies_to` on each tool-specific field and none on `enabled`; for `app_settings` each field
  shows its page. Every existing kind's `describe()` output is byte-identical: capture
  before/after in the session scratchpad and report the diff (Leg 1a's method; no golden file is
  committed). `ALLOWED`, `OPERATOR_PATHS` and `REVIEWED_ALLOWED` are updated and the provenance
  test passes.
- [ ] **AC12. The page line carries the tool.** `settings/tools/{name}` with a name in
  `_TOOL_CLASSES` gives `(#settings/tools/{name})`; an unknown name gives `(#settings/tools)`;
  every other Settings section still drops the item. `tests/test_gleepglorp_page.py:134-143` and
  its docstring move; the agents.md bullet is reworded.
- [ ] **AC13. Boundaries.** Each new service and kind module is in the seam-import guard
  (`tests/test_gleepglorp_proposals_continuation.py:278-296`), and each service's test file
  carries the AST import-boundary test (no `fastapi`, `starlette`, `the_one.interfaces`,
  `the_one.gleepglorp`; no module-level `repositories` import).
- [ ] **AC14. Descriptions and pins.** `propose_change` names both new kinds within 520
  characters and 120 tokens; `fill_form`'s text is byte-unchanged. `-rs` shows
  `test_the_description_token_budget` ran in both tool test files. Every pin in Files Affected is
  updated.
- [ ] **AC15. Guide.** `settings.md` says, in at most 70 words, what GleepGlorp can propose and
  fill on Built-in tools, Date and time and Knowledge indexing, and that it never sets allowed
  folders, hosts or API keys. `guide/gleepglorp.md:19`, which still says GleepGlorp proposes
  changes only for agents, rules and routines, is reworded to cover every kind it can now propose
  or fill (within that file's word limit). `tests/test_gleepglorp_guide.py` passes.

## Verification Steps

1. `THE_ONE_TEST_NETNS=1 make test-unit`: all pass, 15 skipped (read `-rs`).
2. The new and changed test files, run alone with `-x --timeout 60` while iterating.
3. Static guards are not needed unless a static file changes (none should).
4. Browser lanes, one at a time (`THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash
   scripts/run-tests.sh --lane <lane>`): `settings-tools` (the tools editor, impact and grid
   flows over the thinned routes), `settings` (Date and time, Knowledge indexing), `gleepglorp-fill`
   and `gleepglorp-chat` (registry and page-line consumers). Squawk 0334 sweep: grep
   `tests/browser/` for `Built-in tools ›` and `settings/tools` page-line strings and run the
   owning lane of any hit.
5. Falsification as each criterion names it: remove the fix by editing, run, see it fail,
   restore by editing. Report yes or no per safety test.

## Implementation Guidance

1. **Repositories first.** Add `ToolConfigRepository.update_in_txn` (copy
   `KnowledgeBaseRepository.update_in_txn`, `:677-710`: sync `mutate`, raw `conn.execute` only,
   `(before, after)`, here `before=None` for a missing row; `mutate` and `on_commit` only, no
   `precheck`, decision 14) and
   `AppMetadataRepository.set_in_txn`. Keep `upsert` and `set` for their other callers.
2. **`tools/config_service.py`.** Move the helpers out of `api.py` and stop raising
   `HTTPException`. Re-export from `api.py`. Thin the PUT and impact routes. Then
   `effective_values` and `change_tool_config` (split `enabled` out to `data["enabled"]`; merge
   the config fields over `{**config, **secrets}`; stale check against `base` inside `mutate`
   unless `override`; `on_commit` passed through to `update_in_txn`, as
   `change_knowledge_base` does).
3. **`app_settings_service.py`** and the two thinned routes. `save_knowledge_settings` moves to
   one transaction (it may call the service's setter). Keep `_after_monitoring_settings_changed`
   and `_time_settings_error` on the routes.
4. **`FieldSpec.applies_to`** and `describe()`; the scratchpad before/after capture of every
   existing kind's `describe()` **before** adding the new kinds.
5. **`kinds/tool_config.py`.** Fields: `enabled` (boolean, `path=("enabled",)`) and the ten
   allowlisted fields (`path=("config", <field>)`, bounds from the Configs, `applies_to`
   computed). `operator_only` computed (decision 3). `addressing="id"`, `target_noun="built-in
   tool"`, `fillable=("change",)`, `actions=("change",)`, `keyerror_is_gone=False`,
   `relaxed_guard_keys={"searxng_base_url"}`. `normalize`, `warnings`, `apply`, `card_extras`,
   `fill_extras = id_fill_extras(card_extras, stale_fn)`.
6. **`kinds/app_settings.py`.** `addressing="page"`, `actions=("change",)`,
   `fillable=("change",)`; the page derivation in `normalize` (decision 1); `fill_refused` on the
   two time fields; `exists` returns `True`; `card_extras` titles "Date and time" / "Knowledge
   indexing"; `fill_extras` from `id_fill_extras`.
7. **`kinds/errors.py`, `REGISTRY`, `__all__`,** then `page.py`, the description, the guide, the
   docs.
8. **Pins** (Files Affected), then the full verification.

## Edge Cases

- A never-saved tool row (`KeyError` from `get`): base and apply use defaults; the first change
  creates the row.
- `enabled` alone on a tool whose Config is `_EmptyConfig`: allowed, writes the column only.
- `search_backend` to `duckduckgo` or `searxng`: no key handoff warning.
- `searxng_base_url: ""` (clearing it): allowed; no private-address warning.
- A proposal naming `timeout_seconds_default` above the stored max: refused at normalize.
- A `time_zone_mode: "system"` change with a stored zone: allowed (the model keeps the zone).
- A Knowledge indexing change naming only `chunk_overlap_chars` above half the stored size:
  refused at normalize.
- Two open proposals for the same page: the store's existing supersede rule on `target_key`.
- A tool name with different case or spaces: normalised by `strip().lower()`, then exact.
- `time_zone_mode: "zone"` alone with no stored zone: refused with `ERR_ZONE_REQUIRED`'s
  sentence (pinned).
- A card or fill view for a never-saved tool row renders: `warnings` and `card_extras` never
  raise `KeyError` (a test).
- An app-settings proposal naming `embedding_model_id`: refused with the fixed-settings
  sentence.

## Files Affected

- **New:** `the_one/tools/config_service.py`, `the_one/app_settings_service.py`,
  `the_one/gleepglorp/kinds/tool_config.py`, `the_one/gleepglorp/kinds/app_settings.py`;
  `tests/test_tool_config_service.py`, `tests/test_app_settings_service.py`,
  `tests/test_gleepglorp_kind_tool_config.py`, `tests/test_gleepglorp_kind_app_settings.py`.
- **Edited:** `the_one/interfaces/web/api.py`, `the_one/db/repositories.py`,
  `the_one/knowledge/settings.py`, `the_one/time_zones.py` (only if the service needs a
  transaction-aware save), `the_one/gleepglorp/kinds/{__init__,errors}.py`,
  `the_one/gleepglorp/proposals/{shape,tool}.py`, `the_one/gleepglorp/{page,view_core}.py`,
  `the_one/gleepglorp/guide/settings.md`, `the_one/gleepglorp/guide/gleepglorp.md`,
  `the_one/agents.md`, `SECURITY-MODEL.md`.
- **Pins to update:**
  - `tests/test_gleepglorp_proposals_tool.py:66-74` (enum), `:76-89` (every kind named);
  - `tests/test_gleepglorp_fill_tool.py:79` (fill enum gains `tool_config`, `app_settings`);
  - `tests/test_gleepglorp_kinds.py:36-58` (registry list, `KINDS`, the test name's count),
    `:67-96` (`OPERATOR_ONLY_FIELDS` exact tuple), `:99-100` (`FILLABLE`);
  - `tests/test_gleepglorp_kind_hooks.py:84-102` (addressing dict, `keyerror_is_gone` set),
    `:241-248` (`fill_refused` list gains the two time fields);
  - `tests/test_gleepglorp_kind_secret.py:146` (`REGISTRY[-1]` → `REGISTRY[6]`);
  - `tests/test_gleepglorp_proposals_shape.py:118-130`, `:145-160` (kind listings and the
    "Valid names" sentence);
  - `tests/test_gleepglorp_client_helpers.py:57-75` (decision 12);
  - `tests/test_gleepglorp_proposals_continuation.py:278-296` (seam-import list);
  - `tests/test_gleepglorp_views_provenance.py` (`REVIEWED_ALLOWED`);
  - `tests/test_gleepglorp_page.py:3-11`, `:134-143`;
  - grep `tests/` and `tests/browser/` for any other enumeration of the registry or of
    `#settings/tools` page lines (squawk 0334) and list what you changed.
- **Not touched:** `fill_form`'s description text; `tests/browser/test_flow_gleepglorp_kinds.py`
  (client names, Leg 4b); `scripts/run-tests.sh`; any file under `static/`.

## Citation Audit

Citations come from a read-only survey of the working tree on 2026-11-23 (Batch A committed,
Legs 3a and 3b uncommitted), saved at the session scratchpad's `leg4a-survey.md`. The flight
spec's DD3/DD7 line numbers had drifted 15-30 lines; this leg uses the current ones. Corrections
to the spec found by the survey and folded in here: DD7's settable table (the three read tools,
the empty-config tools); the turn-on categories are client-only; `page` addressing and
`FieldSpec.path` are declared but unused; the embedding warm-up is not an app-settings side
effect; the client-registry pin breaks as soon as server kinds are appended. Line numbers in
`api.py` near the settings routes are given as `~` because Batch B's commit precedes this leg;
the design reviewer re-checks them.

**Design review (Developer, Sonnet), 2026-11-23:** approve with changes; 5 medium and 4 low
findings, all applied (decisions 6, 7, 8, 9, 10, 13, 14, 15; AC2, AC4, AC5, AC9; Edge Cases).
The reviewer confirmed the `api.py` and `repositories.py` citations, the settable-set table (by
introspection), that no Config field collides with any kind's field, and that `page` addressing
passes through every consumer unchanged. Unrelated drift it noticed and left out of scope:
`guide/gleepglorp.md:19` still says GleepGlorp proposes only for agents, rules and routines
(stale since Flight 4; the guide test cannot catch it).
