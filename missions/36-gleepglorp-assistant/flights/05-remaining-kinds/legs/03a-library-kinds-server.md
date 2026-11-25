# Leg: 03a-library-kinds-server

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

Add the `knowledge_base` and `secret` kinds on the server. Each gets:
- a write service extracted from its routes, with in-transaction hooks;
- its kind module on the Leg 1a hooks;
- the new `typed_items` guard mode, for a secret's added tools;
- ids in the read views;
- the guide.

The two kinds can be proposed and their fills recorded. Their editor seams are Leg 3b.

## Context

- **Flight decisions:**
  - DD3 (the service pattern);
  - DD5 (knowledge bases);
  - DD6 (secrets' metadata);
  - DD10 (the guard on the new fields);
  - DD11 (provisional names in the descriptions);
  - DD13 (pins).

  Leg 1a gave the hooks: `addressing`, `fill_extras` / `id_fill_extras`, `target_noun`,
  `action_refused`, `operator_only_message`, `keyerror_is_gone`, `stored_get` / `stored_set`
  and the action gate. The checklist is "Adding a kind: the checklist" in `the_one/agents.md`.
- **Batch A is committed** (`7627373a`). This leg starts Batch B. Leg 3b's editor seams are
  designed after this leg lands.
- **Knowledge bases today:**
  - **Routes** (`api.py`):
    - `POST /knowledge-bases` (`:2136`): name check, a generated id, the model's charset check
      on a client id, `repo.create`, then the embedding warm-up;
    - `PUT /knowledge-bases/{kb_id}` (`:2161`): `repo.get` **outside** a transaction, merge and
      `model_validate`, then `repo.update`, then `carry_kb_rename` after the commit on a
      rename.
  - **Repository:** `KnowledgeBaseRepository.update` (`db/repositories.py:667`) checks existence
    before its `write_transaction`. There are no hooks.
  - **Names:** not unique (`db/schema.py:68`).
  - **Fields:** `KnowledgeBase` (`db/models.py:81`) holds only `id`, `name` and `description`
    as editable fields.
- **Secrets today:**
  - **Routes** (`interfaces/web/secrets_api.py`): `POST /secrets` (`:203`) and `PUT
    /secrets/{id}` (`:220`), validated by `_parse` (`:159`). It does the name through
    `_api._checked_name`, the description, `_check_allowed_tools` (`:81-108`, which includes
    `is_refused_tool`) and `_check_values`.
  - **Repository:** `SecretRepository.update` (`:2363`) is a partial update that re-reads and
    checks the name inside its transaction. `create` requires values.
  - **Errors:** `SecretNameConflict` gives 409 and `SecretInvalid` gives 422.
  - **Names:** `UNIQUE COLLATE NOCASE` (`schema.py:3401`).
- **Leg-design decisions,** refining the flight spec. The FD records them in the log.
  1. **The secret service lives in `the_one/secret_store/service.py`** (cycle-2 Architect: not
     beside `secrets_api.py`, which would break the seam-import guard).
     - `_parse` and its helpers move there and raise `SecretWriteError(status, detail)`, which
       the route maps.
     - The name check calls `the_one.naming.check_name` directly, mapped to the same 422 as
       `_api._checked_name`, following `mcp/service.py::checked_name` (`:197`).
     - `secrets_api.py` re-exports nothing it no longer uses, but keeps the names tests import.
       Grep `tests/` for `secrets_api._`.
  2. **The knowledge-base service lives in `the_one/knowledge/service.py`.** Its deps carry the
     repository, the agent-store factory `carry_kb_rename` needs, and the warm-up function
     (`the_one.embeddings.schedule_warm_up`), injectable so unit tests stub it (cycle-2
     Architect).
  3. **A fill `create` of a secret** records only `name`, `description` and `allowed_tools`.
     - Values are not a field of the kind, and the create form's own first row is the value
       handoff (DD6).
     - The kind's `normalize` in fill mode does not require values; the service is never
       called for a fill.
     - A **proposal** `create` is refused by the action gate with DD6's sentence through
       `action_refused`.
  4. **`allowed_tools` is replaced whole** on a change, through the service's own
     `_check_allowed_tools` rules (non-empty, so a change can't empty the list).
     - The kind's `normalize` runs the same check, so a refused tool is refused at proposal or
       fill time with the route's sentence, not at apply.
  5. **The `typed_items` guard mode** (DD6, cycle-2 Architect). This is a new mode, not a reuse
     of an existing one:
     - `FieldSpec.typed_items: bool = False`;
     - `outside.check(kind, changes, sources, base=None)` gains `base`;
     - for a `typed_items` field, the items added are those in `changes` and not in `base`
       (all items when `base` is `None`, as on a create);
     - each added item must `token_match` at least one text in `sources.typed`;
     - with `sources is None` (no anchor), any added item is refused, failing closed;
     - removing items is never refused.

     Both tools pass `norm.base` (`fill/tool.py:144`, `proposals/tool.py:141`). Existing
     callers and tests that omit `base` are unchanged, because no existing field sets the flag.

## Inputs

- The tree at `7627373a` (Batch A committed).
- **Key files:**
  - `the_one/gleepglorp/kinds/{base,__init__,provider,mcp_server,errors,deps}.py`;
  - `the_one/gleepglorp/outside.py`;
  - `the_one/gleepglorp/view_library.py` and `view_core.py` (`OPERATOR_PATHS`, `_list_or_detail(...,
    id_of=)`);
  - `the_one/interfaces/web/api.py` (the knowledge-base routes) and `secrets_api.py`;
  - `the_one/db/repositories.py` (`KnowledgeBaseRepository`, `SecretRepository`);
  - `the_one/knowledge/kb_rename.py`;
  - the guide topics `the_one/gleepglorp/guide/knowledge-bases.md` and `secrets.md`.

## Outputs

- **`the_one/knowledge/service.py`:**
  - `KbWriteDeps`;
  - `KbWriteError(status, detail)`, `KbNotFound`, `KbStaleError(fields)`;
  - `create_knowledge_base(deps, data, *, on_commit=None)`;
  - `replace_knowledge_base(deps, kb_id, data)`, the PUT;
  - `change_knowledge_base(deps, kb_id, changes, *, base=None, override=False, on_commit=None)`;
  - `stale_fields(...)` for the fill view.

  Post-commit work: `carry_kb_rename` on a rename, for both the PUT and a change, and the
  warm-up on a create.
- **`db/repositories.py`, `KnowledgeBaseRepository`:**
  - `create(kb, *, on_commit=None)`;
  - `update_in_txn(kb_id, mutate, *, on_commit=None) -> (before, after)`, on the MCP
    repository's pattern (`:1380`);
  - `update` keeps working for its other callers (grep), or moves its existence check inside
    the transaction.
- **`the_one/secret_store/service.py`:**
  - `SecretWriteDeps`;
  - `SecretWriteError(status, detail)`, `SecretNotFound`, `SecretStaleError(fields)`;
  - `parse_secret(data, *, creating)`, which moves `_parse` and its helpers;
  - `create_secret(deps, data)`;
  - `replace_secret(deps, secret_id, data)`, the PUT, partial as today;
  - `change_secret_metadata(deps, secret_id, changes, *, base=None, override=False,
    on_commit=None)`.

  `SecretRepository.update` gains `precheck=` and `on_commit=`, run inside its existing
  transaction.
- **Thin routes** in `api.py` and `secrets_api.py`, with the same statuses and details.
- **`the_one/gleepglorp/kinds/knowledge_base.py` and `secret.py`,** one `KIND` each, appended
  to `REGISTRY` after `provider`.
- **`outside.py`:** the `typed_items` mode.
- **The views:** ids in `knowledge_bases_view` and `secrets_view`; `OPERATOR_PATHS` and the
  provenance test updated.
- **The descriptions:**
  - `propose_change` appends `knowledge_base` and `secret` to its kind list, provisionally
    (DD11);
  - `fill_form`'s enum grows, through `kinds.FILLABLE`.
- **The guide:** `knowledge-bases.md` and `secrets.md` say what GleepGlorp can and can't do
  there.
- **Tests:**
  - `tests/test_knowledge_service.py` and `tests/test_secret_service.py` (new);
  - `tests/test_gleepglorp_kind_knowledge_base.py` and `tests/test_gleepglorp_kind_secret.py`
    (new);
  - `typed_items` guard tests;
  - the pins updated (Files Affected).
- **`the_one/agents.md`:** the two services and kinds, and the `typed_items` mode.
  `SECURITY-MODEL.md`: the secret metadata proposals and fills, and the added-tools rule.

## Acceptance Criteria

- [ ] **AC1. Knowledge-base service.**
  - `POST` and `PUT /knowledge-bases` behave as today: same statuses, details, warm-up and
    rename carry. Every existing route test file that drives them passes with its assertion
    lines unedited (grep `knowledge-bases` in `tests/`).
  - The PUT reads and writes inside one `update_in_txn`.
  - **The race test: a name-only PUT keeps a description committed while it waited.** Falsify
    it against the old read-outside code.
    1. Hold `write_transaction(conn)`.
    2. Start `replace_knowledge_base` as a task, with a body holding only `name`.
    3. Wait until it waits on the lock (the `_wait_for_waiter` pattern of
       `tests/test_mcp_service.py`).
    4. Run `UPDATE knowledge_bases SET description='X'` with raw SQL.
    5. Release.

    The final row has description `X` and the PUT's name. The old code, which merges over a
    stale pre-read row, writes the stale description back: a lost update. Only
    `KnowledgeBaseRepository.create`, `update` and `delete` write the row (and `name_repair`'s
    `update`), so a concurrent PUT is the real race.
  - **The response's `updated_at`** is now the stored value (`update_in_txn` returns the
    `after` model). The old PUT returned the pre-write `updated_at`. This is more correct.
    Grep the route tests for an `updated_at` assertion; none is expected.
- [ ] **AC2. Secret service.** `POST` and `PUT /secrets` behave as today: the same 201, 404, 409
  and 422 details, including every `_check_values` and `_check_allowed_tools` message. Every
  existing secret route test passes with its assertion lines unedited (grep `/api/secrets` in
  `tests/`). `secrets_api.py` contains no validation logic.
- [ ] **AC3. The `knowledge_base` kind.**
  - **Fields:** `name` (required on create) and `description`. Addressing is `id`; the
    `target_noun` is "A knowledge base". Names go through `check_name`.
  - **Targets:** `resolve_target` uses `resolve_by_id_or_name`, so an ambiguous name lists
    "name (id)".
  - **Proposal and fill:** create and change are both allowed.
  - **Operator-only:** folders, items and reindexing are not fields. A `changes` naming
    `folders`, `items` or `path` is refused through `operator_only_message`, with a sentence
    linking the knowledge base's page.
  - **Warnings:**
    - a create: "Add its folders on the page after approving." / "…after saving." in fill
      mode;
    - a rename of a base that agents use: DD5's sentence, naming the agents, read through
      `AgentStore.list_*` or a query of agents' `knowledge_bases`.
  - **Approve:** applies through `change_knowledge_base` / `create_knowledge_base` with the
    mark in the transaction.
    - A stale `base` gives `ApplyError(stale=…)`.
    - A deleted base gives `gone` (a typed `KbNotFound`; `keyerror_is_gone` stays `False`).
    - A rename carries into agents' `disabled_tools` after the commit.
- [ ] **AC4. The `secret` kind.**
  - **Fields:** `name`, `description` and `allowed_tools` (type `names`, `typed_items=True`, in
    `relaxed_guard_keys`).
  - **Actions:** proposals `("change",)`; fills `("create", "change")`.
    - A proposal create is refused with "Create a secret on the [Secrets] page; I can fill its
      name, description and allowed tools there.", the link being `#library/secrets/~new`.
  - **Targets:** `resolve_target` matches the name ignoring case (names are `NOCASE`-unique)
    and the id exactly.
  - **Operator-only:** `values`, `keys` and `secret_ids`, each refused through
    `operator_only_message` ("Secret values are entered only on the secret's page.").
  - **Checks at normalize:** `allowed_tools` uses the service's rules, so a refused tool such
    as `send_to_platform_channel` is refused with the route's sentence, and an empty list is
    refused. (Correction at the Batch B review: this line first named `write_file`, which is
    not refused; the set is in `secret_store/refused.py`.)
  - **Warnings:**
    - adding tools: "{keys} can then be sent to {added tools}.", with the keys read from the
      stored row;
    - a rename: DD6's sentence.
  - **Approve:** applies through `change_secret_metadata`. Values are never read, written or
    returned by the kind: no `get_values` or `all_values` call anywhere in `kinds/secret.py` or
    the service's change path. A grep pins it.
  - **Stale and gone:** as AC3.
- [ ] **AC5. The `typed_items` guard.** A table-driven test, each case falsified by editing,
  covers four situations, each on a turn that has read outside content:
  - **Added name in the operator's text:** the operator's typed text names `fetch_url`, and
    `allowed_tools` adds `fetch_url`. It passes.
  - **Added name only in fetched text:** the name appears only in a fetched page. It is
    refused.
  - **A removal:** a tool is removed. It passes.
  - **No anchor:** `sources is None`. Any addition is refused.

  It also covers **a trusted turn,** where the guard does not run, so additions pass.

  Long MCP tool names (`mcp__goldfinch__captureScreenshot`) are not refused by
  `guard.check`'s key-shape rule for `allowed_tools`. A test covers it.

  Existing guard tests pass unedited.
- [ ] **AC6. Ids in the reads.**
  - `read_app_config` for knowledge bases and secrets includes `id` per entry and in the detail
    (through `_list_or_detail(..., id_of=...)`).
  - The ids are declared in `ALLOWED` and `OPERATOR_PATHS`.
  - `test_gleepglorp_views_provenance.py` passes with the new paths. Secret views still never
    contain a value.
- [ ] **AC6b. Error translation** (`kinds/errors.py`). `translate` / `_is_gone` /
  `_failure_items` learn the two services' errors, so each apply records the right outcome:
  - `KbStaleError` and `SecretStaleError` give `ApplyError(stale=rows)`. The rows go through
    `display_values`, as `_agent_or_rule_stale` does.
  - `KbNotFound`, `SecretNotFound` and a write error with status 404 give `gone`.
  - `KbWriteError` and `SecretWriteError` (422) give items on their `loc`. A secret's 409
    name conflict gives items on `["name"]`.

  An unmapped exception still re-raises, as today. Tests cover each mapping, falsified for the
  stale and gone cases.
- [ ] **AC7. Registry and tool pins.**
  - `REGISTRY` ends `…, provider, knowledge_base, secret`.
  - Both kinds set `keyerror_is_gone=False`: their services raise typed not-found errors.
  - **The pins, updated** (design review list):
    - `test_gleepglorp_kinds.py:38-45`: the registry list literal, `KINDS` and the "five kinds"
      wording;
    - `test_gleepglorp_kinds.py:63-75`: the exact `OPERATOR_ONLY_FIELDS` tuple, which gains
      `folders`, `items`, `path`, `values`, `keys` and `secret_ids`, in registry order;
    - `test_gleepglorp_kinds.py:82`: `FILLABLE`;
    - `test_gleepglorp_kind_hooks.py:85-92`:
      - the exact addressing dict gains the two kinds;
      - `all(k.keyerror_is_gone for k in REGISTRY)` becomes "the five kinds whose services
        raise a bare `KeyError` set it; the two new ones do not";
    - `test_gleepglorp_kind_provider.py:153`: `REGISTRY[-1] is provider` becomes `REGISTRY[4]`
      or "after `mcp_server`";
    - `test_gleepglorp_proposals_shape.py:113` and `:127`: the `fields` listing of kind names;
    - `test_gleepglorp_views.py:316-323`, `test_secret_detail_shows_key_names_never_values`:
      the exact key set gains `id`;
    - `test_gleepglorp_views_provenance.py:132-146` `REVIEWED_ALLOWED`: `knowledge_bases` and
      `secrets` gain `id` in list and detail, as `providers` has;
    - `test_gleepglorp_fill_tool.py:79` (the enum);
    - `test_gleepglorp_proposals_tool.py:66` (the enum).
  - **`KIND_SUMMARIES`:** each new kind's `summary` text is model-read through the `fields`
    view. Keep it one plain line, as the existing kinds' are.
  - **`propose_change`'s description** names both kinds. Its 520-character and 120-token pins
    still pass, and the token test ran, not skipped (show `-rs`).
  - **The seam-import guard** (`test_gleepglorp_proposals_continuation.py:278-296`) lists
    `kinds/knowledge_base.py` and `kinds/secret.py`. The AST import-boundary tests cover the two
    new services (they import nothing from `gleepglorp`).
  - **The guide drift gate** (`tests/test_gleepglorp_guide.py`) passes.
- [ ] **AC8. The allowlist and no-write tests** (the tool-set allowlist and "a GleepGlorp turn
  writes nothing" tests; grep `allowlist` in `tests/test_gleepglorp_*`) pass and cover the two
  kinds. A fill and a proposal of either kind write no row in `knowledge_bases` or `secrets`
  before an Approve.
- [ ] **AC9. The full unit tier and lanes pass.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected 15 skips).
  - **The browser lanes that drive these routes pass,** each run alone. The design review's grep
    hits:
    - `test_flow_studio_knowledge_inventory.py`, `test_flow_studio_secrets.py` and
      `test_flow_agent_secrets.py`;
    - `test_store*.py`, `test_nav_guard.py`, `test_router_guard.py` and `test_flow_jump_to.py`;
    - `test_agents_library_isolation.py`.

    Map each to its lane with `--lane X --list` and run every lane that holds one (squawk 0334).
    That is at least `knowledge` and `library`.
- [ ] **AC10. The docs** (Outputs) are updated, and `ruff check` / `ruff format --check` are
  clean.

## Verification Steps

- **AC1, AC2:** run the route test files; `git diff -- tests/` shows only new files, the AC7
  pin lines and the provenance test.
- **AC3, AC4, AC5:** run the new kind, service and guard tests. Report, per safety test,
  whether it was falsified: the operator-only refusals, the refused tool, the value-free grep,
  the `typed_items` cases, and the stale and gone cases.
- **AC6, AC7, AC8:** run the files named, with `-rs` for the token test.
- **AC9:** run the unit tier in the background, then each lane alone.
- **AC10:** quote the doc changes and the ruff output.

## Implementation Guidance

1. **Read the template.** `kinds/provider.py` is the closest id-targeted kind. Read it, plus
   `kinds/mcp_server.py`'s `operator_only` use, `kinds/base.py` and the Adding-a-kind checklist
   in `agents.md`.

2. **The knowledge-base service and repository.**
   - Add `on_commit=` to `KnowledgeBaseRepository.create`, and `update_in_txn` (sync `mutate`,
     `updated_at` set, `KeyError` for an unknown id, raw `conn.execute` only).
   - Move the PUT's merge and validate into `mutate`.
   - `carry_kb_rename(existing, updated, get_agent_store=deps.agent_store)` runs after the
     commit when the name changed, on both the PUT and the change paths.
   - Keep the route's charset 422 for a bad client id: the service raises `KbWriteError(422,
     validation_detail(e))`.
   - `api.py`'s `_schedule_embedding_warm_up` is an alias of
     `the_one.embeddings.schedule_warm_up` (`api.py:97`). The service calls it through its
     deps, the route passes the real one, and tests pass a stub.

3. **The secret service.**
   - Move `_parse`, `_check_allowed_tools`, `_check_values`, `_err` and the constants they use
     into `secret_store/service.py`.
   - **Imports without `the_one.interfaces`:**
     - `SECRET_MASK`, `SecretNameConflict`, `SecretInvalid` and `Secret` from
       `db.repositories`;
     - `is_refused_tool` from `secret_store.refused`;
     - `NAME_CONFLICT_SECRET` from `the_one.naming`;
     - the 409 detail from `the_one.agent.write_checks.name_conflict_detail`, which `api.py:38`
       re-imports;
     - the name check from `naming.check_name` plus `name_rule_detail` (find its home module;
       never import it from `api`).
   - `KEY_PATTERN`, `TOOL_NAME_MAX` and `_err` move with the helpers. Nothing outside imports
     `secrets_api._…`.
   - **Order kept in `replace_secret`:** 404 (`repo.get is None`) before `parse_secret`'s 422,
     as the PUT does today.
   - `change_secret_metadata` calls `repo.update(secret_id, name=…, description=…,
     allowed_tools=…, precheck=…, on_commit=…)`, never `values=`.
   - The precheck compares `base` against the row read inside the transaction (raising
     `SecretStaleError`) unless `override`.
   - `SecretRepository.update` raises `KeyError` for an unknown id. The service turns it into
     `SecretNotFound`.

4. **The `knowledge_base` kind** (`kinds/knowledge_base.py`), on `provider.py`'s shape:
   - `FIELDS`, `OPERATOR_ONLY = ("folders", "items", "path")`, `normalize`
     (`check_name`, `resolve_target`, `base` of the named fields from the fresh row,
     `target_key(...)`);
   - `exists`, `apply` (create with a generated id in `result["target_id"]`, or change),
     `summary_text`, `title`, `card_title`, `card_extras`;
   - `fill_extras = id_fill_extras(card_extras, stale_fn=…)`, `warnings`, `addressing="id"`,
     `target_noun="A knowledge base"` and `operator_only_message`.
   - **Repositories,** with no deps change:
     - `KnowledgeBaseRepository(conn)` from the `conn` every kind function receives (as
       `page.py` and `view_library.py` build it);
     - the `carry_kb_rename` store factory from `deps.agent.store`, as `mcp_server._write_deps`
       does.

     `AgentWriteDeps` already carries `store`, `mcp_repo`, `provider_repo`, `secret_repo` and
     `tool_config_repo`. Both approve entry points build it: `api._agent_write_deps`, via
     `gleepglorp_proposals_api.py:67`, and `evals/harness.py:636`. So `deps.py` and the frozen
     harness are untouched; if either would need a change, stop and report it.
   - **Error translation** (AC6b): extend `kinds/errors.py` `translate`, `_is_gone` and
     `_failure_items` for the six new error types (plus `SecretNameConflict`'s 409 on
     `["name"]`), with a stale-row renderer through `display_values`. The services import
     nothing from `gleepglorp`. `errors.py` already imports the other services at module level,
     so the direction holds.

5. **The `secret` kind** (`kinds/secret.py`):
   - **Fields:** `name` (`create_required`), `description`, and `allowed_tools`
     (`type="names"`, `typed_items=True`).
   - **Members:** `actions=("change",)`, `fillable=("create", "change")`, `action_refused`
     (DD6's sentence for `("create", "propose")`, the generic wording otherwise),
     `OPERATOR_ONLY = ("values", "keys", "secret_ids")`, `operator_only_message`,
     `relaxed_guard_keys=frozenset({"allowed_tools"})`, `addressing="id"` and `target_noun="A
     secret"`.
   - **`resolve_target`:** an exact id first, then a `casefold()` name match, through a small
     wrapper over `resolve_by_id_or_name`, or its own loop with the same sentences.
   - **The warnings' key names** come from `SecretRepository.get(id).values[*].key` (key names
     only, never `value`).
   - **`secret` comes from `deps.agent.secret_repo`.**
   - **`allowed_tools` at normalize.** It runs the service's `_check_allowed_tools`, which
     returns a `{loc, msg}` list. Raise `ShapeError` with the first `msg` (it names the tool,
     for example "send_to_platform_channel stores or publishes what it receives, so it can't
     receive secrets."; corrected at the Batch B review from `write_file`, which is not refused).
   - **The base holds the list itself,** not a joined string, so the guard can compute the
     added items.

6. **The `typed_items` mode** (`outside.py`).
   - Add `FieldSpec.typed_items` (`shape.py`, with a docstring line).
   - **In `plan()`:** a `typed_items` field gets a new mode, placed **before** the
     `address_or_command` branch, and exclusive of the free-text scan, so tool names are not
     scanned twice. Today a `names` field with no `ref` is `_FREE`.
   - **In `check()`:**
     - fold (NFKC, `fold`) and strip both sides;
     - `added = [i for i in items if i not in (base or {}).get(stored, [])]`, so every item is
       added when `base` is `None`;
     - each added item needs `any(token_match(item, t) for t in sources.typed)`;
     - use `sources.typed` only, never `_texts()`, which includes linked pages;
     - `sources is None` refuses any addition.

     `token_match`'s token characters include `_-./@:%~`, so `fetch_url` matches "use
     fetch_url." but not inside `fetch_url2`, and a bare "fetch" does not match. That is
     intended.
   - **The refusal sentence** names the tool and asks the operator to name it ("Say which tool
     may receive this secret: name it yourself."), and ends with `REFUSAL_TAIL`, as `_refusal`
     and `_no_source` do.
   - Pass `base=norm.base` from both tools.
   - **The `describe()` hint:** a `typed_items` field carries a `provenance` line in the fields
     view, "each tool you add must be named by you", as `address_or_command` fields do. It is
     emitted only when set, so the existing kinds' `describe()` is unchanged.
   - **Accepted residual:** with `relaxed_guard_keys`, the token-prefix rule still applies, so
     an MCP tool name that starts like a key prefix (`x__hf_` + 16 characters) is refused.
     Record it in `SECURITY-MODEL.md` with the other residuals.

7. **Views.** Add `id_of` to the two `_list_or_detail` calls, the paths to `ALLOWED` and
   `OPERATOR_PATHS`, and update the provenance test.

8. **The descriptions and pins** (AC7). Append the two kind names to `propose_change`'s "kind:"
   list. Leave the rest of its wording for Leg 5. Update the enum pins.

9. **The guide** (two topics), plus `agents.md` and `SECURITY-MODEL.md`.
   - The drift gate caps each topic at 600 words. `knowledge-bases.md` is about 495 and
     `secrets.md` about 509, so each addition is about 100 words or less.
   - Links must resolve in the router: `#library/secrets/~new` and `#library/knowledge/{id}`
     are valid.
   - **`fill_form`'s description** still says "agent, MCP server or provider" while its enum now
     lists the two new kinds. That is provisional platform text, left for Leg 5 (DD11); this
     leg edits only `propose_change`'s kind list.
   - **Accepted until Leg 3b:** a knowledge-base or secret proposal approved from the card does
     not invalidate the client store, so the page shows stale data until reload.
     `proposal-cards.js` and `approvals.js` null-guard an unregistered kind, and `fill.js`
     reports `editor_unavailable`.

10. **Run** the new and touched unit files, lint, then `make test-unit` in the background, then
    the `knowledge` and `library` lanes one at a time. Update the flight log, mark the leg
    `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **A knowledge-base rename to a name another base has.** Names are not unique, so it is
  allowed, as today. The DD5 warning still names the agents.
- **A rename whose slug is unchanged** (only case or punctuation): `carry_kb_rename` checks the
  slug itself, so it is a no-op.
- **A secret `allowed_tools` change that only reorders** is not an addition. The guard sees no
  added items, and the card shows the new order.
- **A secret rename that differs only by case.** `NOCASE` uniqueness treats it as the same
  name, and the repository's name check allows the same row. Confirm with a test.
- **`allowed_tools` naming an MCP tool that doesn't exist yet.** It is allowed, as the route
  allows it today. The guard's added-item rule still applies.
- **A fill create of a secret with `allowed_tools`:** with `base` `None`, every item is an
  added item, so the `typed_items` rule applies to each after outside content.
- **A proposal that names `values`:** `operator_only_message`, before the action gate. Order:
  the unknown-key check runs inside `_check_keys`, after the gate. A proposal create with
  `values` therefore gets the create refusal first. Either order is acceptable; pin the one you
  get.

## Files Affected

- `the_one/knowledge/service.py` (new), `the_one/secret_store/service.py` (new)
- `the_one/db/repositories.py` — the knowledge-base hooks and `update_in_txn`; the secret
  `update` hooks
- `the_one/interfaces/web/api.py` — the thin knowledge-base routes
- `the_one/interfaces/web/secrets_api.py` — the thin routes
- `the_one/gleepglorp/kinds/knowledge_base.py`, `secret.py` (new);
  `kinds/__init__.py` (`REGISTRY`); `kinds/deps.py` if needed (with defaults)
- `the_one/gleepglorp/kinds/errors.py` — the six new error types (AC6b)
- `the_one/gleepglorp/outside.py`, `proposals/shape.py` (`typed_items`),
  `fill/tool.py` and `proposals/tool.py` (pass `base`)
- `the_one/gleepglorp/proposals/tool.py` — the description's kind list
- `the_one/gleepglorp/view_library.py`, `view_core.py` — ids and paths
- `the_one/gleepglorp/guide/knowledge-bases.md`, `secrets.md`
- **New tests:**
  - `tests/test_knowledge_service.py`, `tests/test_secret_service.py`;
  - `tests/test_gleepglorp_kind_knowledge_base.py`, `tests/test_gleepglorp_kind_secret.py`;
  - the guard tests (a new file, or added to the outside-guard test file).
- **Pin updates:**
  - `tests/test_gleepglorp_kinds.py`, `tests/test_gleepglorp_kind_provider.py:153`;
  - `tests/test_gleepglorp_fill_tool.py:79`, `tests/test_gleepglorp_proposals_tool.py:66`;
  - `tests/test_gleepglorp_proposals_continuation.py` (the seam list);
  - `tests/test_gleepglorp_views_provenance.py`;
  - any AST boundary test list.
- `the_one/agents.md`, `SECURITY-MODEL.md`
- **Registries checked:**
  - **No change expected:** the evals freeze digests (no evals file changes), `REQUIRED` /
    `PASSING` (no new scenario this leg), and the client registry (Leg 3b);
  - **Grep before adding:** `tests/_app_routes.py`, for the route tables, if a route's handler
    name changes.

## Citation Audit

Checked by the FD against `7627373a` (2026-11-23).

- `api.py:2136-2158` `create_knowledge_base` (name check, uuid, charset 422, `repo.create`,
  `_schedule_embedding_warm_up`); `:2161-2195` `update_knowledge_base` (`repo.get` outside a
  transaction, merge, `model_validate`, `repo.update`, then `carry_kb_rename` on rename) -
  verified
- `db/repositories.py:659-673` `KnowledgeBaseRepository.create` / `update` (existence check
  before `write_transaction`; no hooks) - verified
- `secrets_api.py:81-108` `_check_allowed_tools`; `:110-157` `_check_values`; `:159-187` `_parse`;
  `:203-237` the POST and PUT routes, the 409 via `_api._name_conflict_detail(NAME_CONFLICT_SECRET)`
  - verified
- `db/repositories.py:2295` `SecretRepository.create` (values required); `:2363` `update`
  (partial; re-reads inside its transaction) - verified (survey and FD)
- `kinds/provider.py:344-396` `_write_deps` from `deps.agent.provider_repo`, `apply` with a
  generated id and `reraise`; `kinds/deps.py` `KindDeps(agent)` only - verified
- `outside.py:255-267` `Sources.typed`; `:390` `plan`; `:495` `check(kind, changes, sources)`
  with no `base`; callers `fill/tool.py:144`, `proposals/tool.py:141`, plus three test files -
  verified
- `mcp/service.py:197` `checked_name` wrapping `naming.check_name` - verified
- `the_one/secret_store/` holds `__init__.py`, `refused.py` and `runtime.py`, with no service yet
  - verified
- `view_library.py:62/127` the views without `id_of` - survey (re-checked by Architect cycle 2)
