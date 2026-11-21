# Leg: 04a-mcp-server-kind

**Status**: planning
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Make MCP servers a proposable kind on the server side:
- an HTTP-free write service extracted from the MCP routes, with the routes left thin;
- repository hooks so a proposal's stale check and status mark ride in the write's own
  transaction;
- the `mcp_server` kind (proposals now, fills in Leg 4b);
- the `target` parameter on both tools;
- the outside-value guard marks on its fields;
- the guide topic;
- the MCP part of squawk 0398.

## Context

- **Flight DD9** (MCP servers) is the authority. This leg also uses DD3 (`ApplyError`,
  `KindDeps`), DD5 (ids and `target`), DD7 (the declared fields), DD10 (warnings live in
  `Kind.warnings`) and DD12 (descriptions name kinds).
- **Split.** Leg 4 is split into **4a (server)** and **4b (client: the editor seam, applier,
  follow-through and key-value note)**, under the flight's acceptable variations and the Flight
  3 Leg 6 precedent: the server half and the browser write seam are separate risks.
  - Until 4b lands, `mcp_server` has an empty `fillable`. `fill_form` does not offer it, and a
    fill of it is refused by the existing "not fillable" path.
- **Decisions made at this leg's design (FD, 2026-11-21):**
  - **Changing a server's `type` is fill-only.** A proposal that changes `type` on an existing
    server is refused with a handoff ("change the type in the editor"). The editor owns which
    old-type keys and Sensitive rows are dropped on a switch, and a proposal would have to guess
    that. A create proposal sets `type` freely. This narrows DD9's "a type change writes the
    editor's Save body" for proposals; the log records it.
  - **The write happens inside the transaction through a mutator, not via a retry loop.** The
    repository gains `update_in_txn(source_id, mutate, on_commit)`: it re-reads the row inside
    the write transaction, calls `mutate(current) -> updated` (which may raise), and writes the
    result. The change service's mutator merges only the named fields onto the **freshly read**
    row. This satisfies DD9's "re-read and re-pin `_cache` and the OAuth secrets inside the
    transaction" without `change_agent`'s retry, because there is no read-outside-write gap.
  - **The `target` tool parameter lands here** (deferred from Leg 1b): the first id-targeted
    kind uses it.
  - **Tool descriptions name kinds, not fields** (DD12). This happens now, because adding the MCP
    fields to the registry breaks `test_the_description_stays_thin`, which requires every field
    of every kind in the description. The pin is rewritten to require every kind name. The text
    is provisional platform text, measured in Legs 6 and 7.
- **The route code today** (read in full at design): `create_mcp_source` (`api.py:3370`) and
  `update_mcp_source` (`api.py:3420`). The update performs, in order:
  - the surface-row 409;
  - the per-key `__MASKED__` resolution of `secrets`;
  - the OAuth-managed key pinning;
  - the `_cache` strip and preserve;
  - `model_dump() | data` → `model_validate`, with `_checked_name` on a name change;
  - `_reject_reserved_surface_name` and `_validate_mcp_source_config`;
  - the `server_changed` `_cache` pruning;
  - `repo.update`, then `forget_era`;
  - on a config or secrets change, `_evict_all_for_source` and
    `_drop_source_agent_tool_cache`;
  - on a rename, `carry_mcp_rename` and `carry_mcp_rename_into_secrets`.

## Inputs

- Legs 1a, 1b, 2 and 3 landed (Batch A, committed before this leg starts).
- `api.py` MCP routes and helpers (`_validate_mcp_source_config` `:3202`,
  `_reject_reserved_surface_name`, `_config_without_cache`, `_drop_source_agent_tool_cache`,
  `_mcp_source_response`, `_agent_store`, `_secret_repo`); `db/repositories.py`
  `MCPSourceRepository` (`:1326`); `self_configuration_manage.is_surface_row`;
  `kinds/` (Legs 1a and 1b); `outside.py` (Leg 3); `gleepglorp/guide/mcp-servers.md`.

## Outputs

- **`the_one/mcp/service.py`** (new; no `gleepglorp` and no `fastapi` imports):
  - `McpWriteError(items, status=422)`, `McpSourceNotFound` and `McpStaleError(fields)`;
  - `McpWriteDeps` (the repository, plus late-bound getters for the agent store and the secret
    repository);
  - `create_mcp_source(deps, data, *, on_commit=None)`;
  - `replace_mcp_source(deps, source_id, data)`, the PUT semantics exactly;
  - `change_mcp_source(deps, source_id, changes, *, base=None, override=False, on_commit=None)`,
    which merges named fields inside the transaction (Context).

  The helpers move with them, kept importable from `api.py` if tests import them there (grep):
  `validate_config`, `reject_reserved_name` and `config_without_cache`. Post-commit side
  effects run in the service, only after a successful commit.
- **`db/repositories.py`:**
  - `MCPSourceRepository.create(source, *, on_commit=None)`;
  - `update_in_txn(source_id, mutate, *, on_commit=None)` (re-read, mutate, write, `on_commit`,
    all in one `write_transaction`).

  `update(source)` stays for the other callers.
- **`api.py`:** `create_mcp_source` and `update_mcp_source` call the service and map its errors
  to today's status codes and details.
- **`the_one/gleepglorp/kinds/mcp_server.py`** registered in `REGISTRY` after `routine`. It has:
  - fields (stored key → path):
    - `name` → `name`;
    - `type` → `type` (create-only for proposals);
    - `command` → `config.command`, and `args` → `config.args` (a list);
    - `env` → `config.env` and `headers` → `config.headers` (`rows`);
    - `url` → `config.url`.
  - `address_or_command` set on `command`, `args`, `url`, `env` and `headers`;
  - `operator_only`: `cwd`, `sandbox`, `secrets`, `mcp_overrides`;
  - `fillable = ()` (Leg 4b sets it);
  - `resolve_target`, using `kinds.resolve_by_id_or_name` over non-surface rows;
  - `exists`, `normalize`, `base`, `apply` (through the service, translating to `ApplyError`);
  - `summary_text`, `title` ("Create MCP server “x”" / "Change MCP server “x”") and
    `card_title`;
  - `warnings(view)` (DD9: the URL move with stored secrets or OAuth tokens; a command or args
    change with stored Sensitive env; the `npx`/`pipx` first-run note on a stdio create);
  - `needs_secret`, which returns `None`: an MCP create never needs a secret to apply.
- **`target` on `propose_change` and `fill_form`** (the parameter, the alias for agent, the
  refusal for rule and routine), as Leg 1b's deferred AC8 specified.
- **Tool descriptions name the kinds.** The `set(props)` pins and
  `test_the_description_stays_thin` are rewritten to require each kind name. The token pins (120
  for `propose_change`, plus a new 90 for `fill_form`) stay, with a character cap beside each.
- **`proposal_view`** carries `warnings: [str]` from `Kind.warnings`. `display_values` shows
  `rows` dicts as one row per key ("Header Accept", "Env LOG_LEVEL") for the card. Rendering is
  Leg 4b.
- **`gleepglorp/guide/mcp-servers.md`** gains how GleepGlorp proposes and fills MCP servers (the
  Sensitive-row handoff, sign-in on the page, the type switch in the editor).
  `tests/test_gleepglorp_guide.py` passes.
- **Squawk 0398, MCP part:** `the_one/mcp/README.md:15/354/398/491`, `the_one/mcp/__init__.py:8`
  and `the_one/self_configuration/credentials.py:42` cite `the_one/agents.md` sections that
  exist. The squawk artifact is marked completed with its corrective action, verification and
  sign-off at the Batch B commit. The `db/schema.py` part was done in Leg 1b.
- **Docs:** `the_one/agents.md` (the MCP service, `update_in_txn`, the `mcp_server` kind) and
  `SECURITY-MODEL.md` (MCP fields GleepGlorp may set and never sets).

## Acceptance Criteria

- [ ] **AC1. The MCP routes are behaviour-identical.**
  - Every existing MCP route test passes with its assertions unedited:
    - `tests/test_mcp_sources_api*.py`, `tests/test_oauth_secrets_api.py`;
    - the rename-carry tests and the surface-row tests;
    - any test touching `create_mcp_source` or `update_mcp_source`; grep `mcp-sources` under
      `tests/`.
  - The Developer lists the files run.
- [ ] **AC2. The service has no web or `gleepglorp` imports.** An `ast` check, the kind
  `test_the_seam_modules_do_not_import_interfaces` uses, covers `the_one/mcp/service.py`.
- [ ] **AC3. `update_in_txn`.**
  - The mutator sees the row as it is inside the transaction. A concurrent `merge_cache` write
    (simulated by writing `_cache` and an OAuth secret between the service's first read and the
    call) is preserved in the stored row after a `change_mcp_source`.
  - `on_commit` runs inside the transaction.
  - A mutator exception rolls back and writes nothing.
  - A test covers each.
- [ ] **AC4. `change_mcp_source` changes only the named fields.**
  - **Rows merge per row.** A named env or header row is added or its value set. Other rows,
    `secrets`, `_cache`, `cwd` and `sandbox` are untouched.
  - **A Sensitive key stays sensitive.** A row whose key is stored in `secrets` is refused
    (`McpWriteError` at `loc` `["headers", key]` or `["env", key]`) rather than written as plain
    text.
  - **Stale.** With `base`, a named field whose stored value differs raises `McpStaleError`
    (unless `override`).
  - **Validation and side effects.** The name rule, the reserved-name refusal, the surface-row
    refusal and the config validation all apply. The side effects (`forget_era`, eviction, the
    tool-cache drop, the rename carry) run after commit exactly when the route would run them.
  - A test covers each.
- [ ] **AC5. The `mcp_server` kind.**
  - It is registered, and `describe("mcp_server")` lists its fields.
  - `normalize` refuses:
    - `operator_only` fields;
    - an empty or missing `url` or `command` on a create of that type;
    - a `type` change on a change action, with the handoff sentence;
    - a surface row as target;
    - an unknown key.
  - It resolves `target` id-first, and refuses a duplicate name listing "name (id)".
  - Its `base` snapshots exactly the named stored keys (a `rows` field snapshots only the named
    rows). `target_key` uses `kinds.target_key`.
  - A test covers each refusal and the happy create and change.
- [ ] **AC6. Approve applies through the service.**
  - `apply_proposal` on an `mcp_server` create and change writes via the service, marks the
    proposal applied in the same transaction, and pushes `config_changed` with `kind`
    `mcp_server` and `target_id`.
  - Stale gives the 409 `stale` rows. A deleted target withdraws.
  - A validation failure marks it failed with the service's items.
  - `KindDeps` supplies the MCP repository, lazily from `conn` and the encryptor when it was
    built from a bare `AgentWriteDeps`, so `evals/harness.py` is unchanged.
- [ ] **AC7. The guard on MCP fields** (DD7 per-kind falsification). Through the real
  `propose_change` on an untrusted turn:
  - a `url` from an operator-linked page → allowed;
  - from an unlinked page → refused;
  - a stdio `command` and `args` from a linked README in JSON config form → allowed;
  - a command from a search result → refused;
  - an `env` row `NODE_OPTIONS` from a linked page → refused;
  - the same, typed → allowed.

  **`guard.check` must-pass cases** (it was tuned on agent text) on these field values must
  pass:
  - `ghcr.io/acme/mcp@sha256:<64 hex>`;
  - `https://api.example.test/v1/mcp/3f2a9c1b-…` (a UUID path);
  - `npx -y @modelcontextprotocol/server-github`;
  - `uvx mcp-server-fetch`.

  If `guard.check` refuses one, narrow it **only** for `address_or_command` fields, keep it
  unchanged on agent text, and add a test that a real key-shaped string in a declared field is
  still refused.
- [ ] **AC7b. Carried from the Batch A review.**
  - **`None` row values.** `outside.check`'s declared-rows branch skips a `None` row value
    instead of turning it into the string `"None"`. A test covers it.
  - **Wider loader denylist.** `LOADER_KEY_GLOBS` gains `NODE_TLS_REJECT_UNAUTHORIZED`, `HOME`,
    `XDG_*`, `PYTHONINSPECT`, `BUN_*`, `DENO_*`, `GEM_*`, `BUNDLE_*`, `JAVA_HOME`, `MAVEN_OPTS`
    and `GRADLE_OPTS`. Its pin test is updated.
  - **New residuals documented.** `SECURITY-MODEL.md`'s residual list adds IDN and homograph
    domains, and TLDs outside the allowlist, in free text.
- [ ] **AC8. Warnings.** `Kind.warnings` returns the DD9 sentences for:
  - a URL change on a server with a stored sensitive header or OAuth tokens;
  - a command or args change with stored Sensitive env;
  - a stdio create with an `npx` or `pipx` runtime.

  `proposal_view` carries them. A test covers each, and covers none on a plain change.
- [ ] **AC9. `target` and descriptions.**
  - Both tools accept `target`. For agent it behaves exactly as `agent`, and conflicting values
    are refused. Rule and routine refuse `target`.
  - The descriptions name every registered kind. The rewritten pins require each kind name
    (from `kinds.REGISTRY`) to appear, within a character cap.
  - `propose_change` stays at or under 120 tokens (o200k_base) and `fill_form` at or under 90.
  - The `set(props)` pins include `target`.
- [ ] **AC10. Guide and squawk.** The guide drift test passes. The squawk 0398 grep
  (`grep -rn 'CLAUDE.md' the_one/ scripts/ evals/`) shows no citation of a section `CLAUDE.md`
  lacks, and each repointed heading exists in `the_one/agents.md`.
- [ ] **AC11. No regression.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips, and ruff is clean.
  - The `mcp` and `mcp-connection` browser lanes pass. They are the routes' browser consumers;
    run them one at a time.
  - `tests/test_evals_gleepglorp*.py` and `tests/test_evals_freeze.py` pass. If a scenario
    test enumerates `describe()` kinds or tool `parameters`, update it only if it is not
    digest-frozen. If it is frozen, stop and report.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_mcp_service.py tests/test_gleepglorp_kind_mcp.py <every MCP route test file> tests/test_gleepglorp_*.py tests/test_evals_gleepglorp*.py tests/test_evals_freeze.py -x --timeout 60`.
- `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane mcp`, then
  `--lane mcp-connection`, then `THE_ONE_TEST_NETNS=1 make test-unit`. Run them one at a time,
  in the background.

## Implementation Guidance

1. **The repository hooks** first, with tests (AC3).

2. **The service.**
   - Move the route bodies into `create_mcp_source` and `replace_mcp_source` as they are,
     raising the service errors where the routes raise `HTTPException`. Keep the exact detail
     strings. The routes catch and re-raise them as `HTTPException(status, detail)`.
   - Keep the post-commit side effects in the same order. Move `_drop_source_agent_tool_cache`
     into the service, or reach it through deps.
   - Then write `change_mcp_source` on `update_in_txn`. Its mutator:
     - copies the current row;
     - applies the named fields, per-row for `rows`;
     - refuses Sensitive keys;
     - runs the stale check against `base`;
     - validates (`model_validate`, the name rule, the reserved name, the config validation).

     After commit, it runs the same side effects `replace` would, given the before and after
     rows.

3. **Thin routes.** Run the AC1 suites before going further.

4. **The kind module** (AC5, AC6, AC8), with `KindDeps` extended.

5. **`target` and the descriptions** (AC9).

6. **The guard marks and cases** (AC7).

7. **Guide, squawk 0398 and docs** (AC10). Leave the squawk artifact's status for the FD at
   commit, but write its Corrective Action and Verification.

8. **Gates** (AC11).

## Edge Cases

- **A create proposal names `cwd` or `sandbox`:** refused (`operator_only`). The operator sets
  them in the editor after approving.
- **A change proposal naming a header row that exists in plain `config.headers`:** its value is
  replaced. Under the guard, the new value must be operator-sourced.
- **The self-configuration surface row:** never a target (`resolve_target` excludes it), and the
  reserved name is refused on create.
- **Two servers with the same name:** resolution by name is refused, listing both ids. The id
  works.
- **A proposal approved after the server was deleted:** the service raises
  `McpSourceNotFound`, which becomes `ApplyError(gone=True)` and withdraws the proposal.
- **A rename by proposal:** the rename carry runs after commit, as the route does. A test pins
  that an attached agent's override key follows.

## Files Affected

- `the_one/mcp/service.py` (new), `the_one/db/repositories.py`, `the_one/interfaces/web/api.py`.
- `the_one/gleepglorp/kinds/mcp_server.py` (new), `kinds/__init__.py` (`REGISTRY`), `kinds/deps.py`.
- `the_one/gleepglorp/proposals/tool.py`, `fill/tool.py` (`target`, descriptions),
  `proposals/store.py` (`warnings`, row display).
- `the_one/gleepglorp/outside.py` or `guard.py` only if AC7 requires the narrowing.
- `the_one/gleepglorp/guide/mcp-servers.md`.
- `the_one/mcp/README.md`, `the_one/mcp/__init__.py`, `the_one/self_configuration/credentials.py`
  (comments).
- `squawks/0398-stale-claude-md-citations.md` (Corrective Action, Verification).
- **Tests:** `tests/test_mcp_service.py` (new), `tests/test_gleepglorp_kind_mcp.py` (new), and the
  tool tests (the description and `set(props)` pins).
- **Docs:** `the_one/agents.md`, `SECURITY-MODEL.md`.
- **Registries and pins:**
  - `tests/test_gleepglorp_kinds.py` (`REGISTRY` exactly three becomes four);
  - `tests/browser/test_flow_gleepglorp_kinds.py` (client names; unchanged here, because the
    client kind is Leg 4b);
  - the tool description and `set(props)` pins;
  - the seam-import guard;
  - the guide topics.

## Citation Audit

Verified against the working tree with Batch A landed:
- `api.py:3370` `create_mcp_source` (`_checked_name`, id `uuid4().hex[:12]`, `model_validate`, `_reject_reserved_surface_name`, `_validate_mcp_source_config`, `repo.create`); `:3420` `update_mcp_source`, whose step order is in Context; `:3202` `_validate_mcp_source_config` (stdio: `command` required, `args` a list of strings, `cwd` a string, `env` a dict of strings, an optional `sandbox`; HTTP: `url` required, `headers` a dict of strings) — verified.
- `db/repositories.py:1326` `MCPSourceRepository`: `create` (one `write_transaction`, no hooks), `update` (existence check outside the transaction, no hooks), and `merge_cache` (read and write in one transaction, config only) — verified.
- `db/repositories.py:270` `AgentStore.save(..., precheck=, on_commit=)`, the hook precedent — verified.
- `tests/test_gleepglorp_proposals_tool.py:74` `test_the_description_stays_thin`, `:83` the token budget (120, o200k_base) — verified.
- `gleepglorp/guide/mcp-servers.md` exists — verified.
- `kinds/`, `outside.py`, `status_rows.py`: re-check after Batch A commits (they were written by Legs 1a-3).
