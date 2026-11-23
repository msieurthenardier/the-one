# Leg: 01b-squawks-and-lanes

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

Close squawks 0400, 0382 and 0402 on the MCP and provider write services, and split the
`gleepglorp` browser lane into three canonical lanes, keeping `gleepglorp` as an alias of their
union.

## Context

- **Flight DD13** (the lane split), the operator's squawk decision (2026-11-23), and the flight
  log's Reconnaissance Report.
- **Designed after Leg 1a landed** (debrief recommendation 4). Leg 1a touched none of this
  leg's files: `mcp/service.py`, `llm/provider_service.py`, `scripts/run-tests.sh`,
  `tests/test_run_tests_lanes.py`.
- **Squawk 0400.** `replace_mcp_source` (PUT `/api/mcp-sources/{id}`) reads the row with
  `repo.get` outside the write transaction, then writes with `repo.update`. An OAuth refresh or a
  Test's `merge_cache` landing in between is overwritten. `change_mcp_source` (proposals)
  already runs on `update_in_txn`. Flight 4 Leg 5a fixed the same race for providers, and that
  fix is the recipe.
- **Squawk 0382.** `_prune_cache_on_server_change` decides "a different server" by type and URL
  only. A local-command (stdio) server's identity is its command and arguments, so replacing
  them keeps the old server's `last_check`, `auth_posture` and `protocol_fallback`.
  - **The squawk's scope note:** command and arguments, not env or sandbox, and the dropped keys
    stay the same three. Anything more is a design change: escalate.
  - **The code has moved:** it is now in `mcp/service.py`, no longer `api.py`. Update the
    squawk's evidence.
- **Squawk 0402.** `create_provider` accepts a client-supplied `id`, and a duplicate fails on
  the primary key as a 500. The fix is a 409 with a plain detail.
- **The lane split** (DD13). `gleepglorp` is 10 files, 167 tests, wall 541 s on the Flight 4
  gate, and every test boots its own server.
  - **The new lanes:**
    - **`gleepglorp-chat`:** `test_flow_gleepglorp_drawer_chat.py`,
      `test_flow_gleepglorp_drawer_shell.py`, `test_flow_chat_gleepglorp.py` and
      `test_flow_chat_proposals.py`;
    - **`gleepglorp-fill`:** `test_flow_gleepglorp_fill.py` and `test_flow_gleepglorp_kinds.py`;
    - **`gleepglorp-kinds`:** the globs `test_flow_gleepglorp_fill_*.py` and
      `test_flow_gleepglorp_follow_*.py`. Today that is the four MCP and provider files; Legs
      3b and 4b add more.
  - **Leg-design refinement: `gleepglorp` stays as an alias** of the three. Every doc, crew note
    and earlier leg that says `--lane gleepglorp` keeps working, as `chat` does for the chats
    lanes. The FD records it in the log.
  - **Provisional budgets** come from the old lane's rate (541 s / 167 tests ≈ 3.2 s a test)
    × 1.25, rounded up to 30 s. They are re-measured at the closing gate:
    - `gleepglorp-chat`: 74 tests → 330 s;
    - `gleepglorp-fill`: 43 tests → 210 s;
    - `gleepglorp-kinds`: 40 tests → 210 s.

## Inputs

- The tree after Leg 1a (landed, uncommitted).
- **The squawk files:**
  - `squawks/0400-mcp-put-reads-outside-the-transaction.md`;
  - `squawks/0382-local-command-edit-is-not-a-server-change.md`;
  - `squawks/0402-provider-create-duplicate-id-500.md`.

## Outputs

- **`the_one/mcp/service.py`:**
  - `replace_mcp_source` runs on `repo.update_in_txn`;
  - `_prune_cache_on_server_change` also treats a changed stdio command or args as a server
    change.
- **`the_one/llm/provider_service.py`:** `create_provider` refuses a duplicate id with
  `ProviderWriteError(409, …)`.
- **Tests:**
  - the MCP race test, in `tests/test_mcp_service.py` (or whichever file holds the MCP service
    tests; grep first);
  - the 0382 prune tests;
  - a 0402 route test.
- **`scripts/run-tests.sh`:**
  - the three lane patterns;
  - `CANON_LANES`, `LANE_LIST`, the usage text and the alias list;
  - the `gleepglorp` alias;
  - the three budgets;
  - the two expansions that subtract or complement `gleepglorp_pat` (`:290`, `:339`), now over
    the union.
- **`tests/test_run_tests_lanes.py`:**
  - the canonical lane list pins (`:252`, and `:28` if it lists lanes);
  - the gleepglorp partition test, rewritten for three lanes plus the alias;
  - the chat-alias test (`:192-199`).
- **Docs:**
  - **`CLAUDE.md`:** the canonical lane list line (`:141`) names the three lanes, and adds
    `gleepglorp` to the aliases;
  - **`the_one/agents.md`:** the lanes section (`:3061` and `:3430`, the stale "provisional
    budget 360 s") and a budget-history note for the provisional three.
- **The three squawk files:**
  - status `in-progress`;
  - Corrective Action and Verification written;
  - 0382's evidence path updated.

  The FD marks them `completed` with the sign-off at the batch commit.

## Acceptance Criteria

- [ ] **AC1. Squawk 0400.** `replace_mcp_source` reads and writes inside one
  `update_in_txn`. A new race test fails with the old read restored by editing (falsified):
  - hold `write_transaction`;
  - start the replace task and wait until it waits on the lock, with `_wait_for_waiter` as in
    `tests/test_provider_service.py`;
  - write a new OAuth `refresh_token` into `secrets` and a new `_cache` key with raw SQL;
  - release.

  The stored row keeps the replace's name, the fresh `refresh_token` and the fresh `_cache`.
- [ ] **AC2. The MCP route suites pass with their assertion lines unedited:**
  - every test file that drives `PUT /api/mcp-sources/{id}` or `replace_mcp_source` (grep);
  - `tests/test_mcp_service.py`.

  **Except two tests that pin squawk 0382's defect.** Both are in `tests/test_mcp_last_check.py`,
  and the FD authorizes inverting them in this leg, because the operator chose the fix:
  - `test_put_server_change_drops_the_protocol_fallback_note` (~:417-423) PUTs a new `args`
    under `# same server: kept`.
    - Change that step to expect the three keys dropped.
    - Add a same-command, same-args PUT step that keeps them, so the "kept" half stays covered.
  - `test_sequence_keeps_every_key_then_reset_drops_all` (~:333-340) PUTs `args: ["y"]` over
    `args: []`. That test is about a PUT keeping the cache, not about server identity, so its
    PUT keeps `args: []`, and its assertions are unchanged.

  These two are the only edited test lines in `tests/test_mcp_*`, each called out in the
  report.
- [ ] **AC3. Squawk 0382.** On a stdio server whose `_cache` holds `last_check`, `auth_posture`
  and `protocol_fallback`:
  - a save that changes `command`, or changes `args`, drops those three keys and keeps every
    other `_cache` key;
  - a save that changes only `env` or the sandbox keeps all of them;
  - a change through `change_mcp_source` (a proposal) behaves the same.

  The tests fail with the old comparison restored (falsified).
- [ ] **AC4. Squawk 0402.**
  - `POST /api/providers` with a **client-supplied** `id` that already exists returns 409 with
    a plain sentence ("A model provider with id … already exists."). A `GET` after shows the
    stored row unchanged.
  - A create without an `id` is unchanged.
  - **Race-safe:** the `IntegrityError` from the insert is caught, then `repo.get(id)`
    confirms the clash. It is not only checked beforehand.
  - **A proposal create** passes a freshly generated id (`kinds/provider.py` `_create_body`,
    ~:351/:376). Its behaviour is unchanged, and on a 409 the `on_commit` mark rolls back (a
    service test modelled on `test_create_on_commit_rolls_the_insert_back`,
    `tests/test_provider_service.py:168`).
  - The tests are falsified.
- [ ] **AC5. The lane split.**
  - `--lane gleepglorp-chat|gleepglorp-fill|gleepglorp-kinds --list` print exactly the files
    above.
  - `--lane gleepglorp --list` prints their union, which is today's ten files.
  - `--parallel 3 --plan` schedules the three and not `gleepglorp`.
  - The partition tests pass:
    - `test_lanes_union_is_the_browser_suite` (~:78);
    - the pairwise-disjoint test.

    `chats`, `chats-transcript` and `shared` still exclude all ten files.
- [ ] **AC6. A new file joins without a pattern edit.** A test reads the
  `gleepglorp_kinds_pat=(...)` text out of `scripts/run-tests.sh` (a regex) and `fnmatch`es
  names against it:
  - `test_flow_gleepglorp_fill_secret.py` and `test_flow_gleepglorp_follow_x.py` match;
  - `test_flow_gleepglorp_fill.py` and `test_flow_gleepglorp_kinds.py` do not.
- [ ] **AC7.** `THE_ONE_TEST_NETNS=1 make test-unit` passes (expected 15 skips).
- [ ] **AC8. The three lanes pass,** each run on its own: `THE_ONE_TEST_NETNS=1
  PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane <lane>`, never while the unit tier
  runs. The walls are reported. They are solo readings and move no budget.
- [ ] **AC9. The docs and squawk files** are updated as listed in Outputs.
- [ ] **AC10.** `ruff check` and `ruff format --check` are clean, and `bash -n
  scripts/run-tests.sh` passes.

## Verification Steps

- **AC1, AC3, AC4:** run the new tests; report per test whether it was falsified.
- **AC2:** run the grepped files. `git diff -- tests/` shows only new tests, plus the two AC2
  inversions and the lane-test changes (AC5, AC6).
- **AC5, AC6:** run the `--list` and `--plan` commands, paste their output, and run
  `tests/test_run_tests_lanes.py`.
- **AC7, AC8:** run the unit tier in the background and wait for completion, then each lane
  alone. Report the counts and walls.
- **AC9:** quote the changed lines.
- **AC10:** run the commands and report their output.

## Implementation Guidance

1. **Squawk 0400** (`mcp/service.py::replace_mcp_source`).
   - **Move everything that reads `existing` into a sync `mutate(current)`,** passed to
     `repo.update_in_txn(source_id, mutate)`:
     - `reject_surface_row`;
     - the masked-secret resolution;
     - the OAuth-key pinning;
     - the `_cache` strip and preserve;
     - the merge and `model_validate`;
     - the name check;
     - `reject_reserved_surface_name`;
     - `validate_mcp_source_config`;
     - `_prune_cache_on_server_change`.
   - **Errors:** `McpWriteError` raised inside `mutate` rolls back. `KeyError` from
     `update_in_txn` becomes `McpSourceNotFound`, as today.
   - **Defensive copies:** `data` and `incoming_config` are copied before `mutate`, so a retry
     never sees a mutated input. The `_cache` pop currently mutates the caller's dict.
   - **After commit:** `_after_write(deps, before, after)` runs, and the function returns
     `after`.
   - **Check `updated_at`.** `update_in_txn` sets it, while `repo.update` may differ. Grep the
     PUT route test (`test_a_put_response_carries_the_written_updated_at` is the provider
     analogue) and keep the response's `updated_at` equal to the stored one.
   - **Keep `mutate` sync and free of anything that opens `write_transaction`**
     (`checked_name` and the validators are sync and pure; confirm).
   - **The race test** goes in `tests/test_mcp_service.py`, using its `world` fixture and
     `make_http` / `make_stdio`. It copies
     `test_a_refresh_written_while_a_replace_waits_for_the_lock_survives`
     (`tests/test_provider_service.py:210`).
     - **Seed an OAuth secret first** (a `refresh_token`), so the pin path runs and the test
       can fail on the old code.
     - **The raw-SQL write** uses `world.repo._secrets_to_ciphertext(...)`, as
       `test_a_write_landing_while_the_change_waits_for_the_lock_is_kept` (`:211`) does.
     - **`_wait_for_waiter`:** copy it into the MCP test file, since it is a private helper of
       the provider test file.
     - **Falsify** by restoring, through edits, `existing = await repo.get(source_id)` and
       `repo.update(updated)`; show the test fails; then put the fix back.
     - **The service-level test is enough.** No route-level variant is needed: the route is
       a thin call to the service.
   - **`updated_at`:** `update_in_txn` returns the model with the stored `updated_at`, so the
     PUT response now equals the stored value, which today's in-memory copy does not. This is an
     improvement; no MCP test asserts the old value.

2. **Squawk 0382** (`_prune_cache_on_server_change`). `server_changed` becomes:
   - the type changed;
   - **or** the `url` changed;
   - **or** `before.type == after.type == "stdio"` and (`command` changed, compared as-is,
     **or** `(cfg.get("args") or [])` changed).

   Nothing else changes: the same three keys are dropped. Add the AC3 tests in
   `tests/test_mcp_service.py` beside `test_a_url_change_prunes_the_old_servers_cache_keys`
   (`:380`). Invert the two pinning tests as AC2 authorizes. If any **other** test pins the
   defect, stop and report it.

3. **Squawk 0402** (`llm/provider_service.py::create_provider`).
   - Record `client_id = "id" in data` before the default is filled in.
   - Wrap `await deps.repo.create(...)` and catch `sqlite3.IntegrityError` (add `import
     sqlite3`). Then:
     - when `client_id` holds and `await deps.repo.get(provider.id)` finds a row, raise
       `ProviderWriteError(409, "A model provider with id … already exists.")`;
     - otherwise re-raise.
   - `llm_providers` has only `id TEXT PRIMARY KEY` (`db/schema.py:3203`) and no unique name, so
     nothing else raises there.
   - `write_transaction` rolls back before re-raising (`_write_lock.py:73-79`), so the
     `on_commit` mark is rolled back too.
   - The route maps `ProviderWriteError.status` straight through (`api.py:5656`
     `_provider_write_errors`). Confirm 409 passes.
   - **The proposal path** passes a generated id (`kinds/provider.py` ~:351/:376). It counts
     as `client_id` from the service's point of view, so a (practically impossible) collision
     would also give 409. That is acceptable, and it rolls back cleanly. AC4 tests it.

4. **The lane split** (`scripts/run-tests.sh`).
   - Replace `gleepglorp_pat` with three arrays: `gleepglorp_chat_pat`, `gleepglorp_fill_pat`
     and `gleepglorp_kinds_pat`. The globs stay single-quoted, as the file's comment at `:186`
     requires. Define `gleepglorp_pat=("${gleepglorp_chat_pat[@]}" "${gleepglorp_fill_pat[@]}"
     "${gleepglorp_kinds_pat[@]}")` so `:290` and `:339` keep working unchanged.
   - `CANON_LANES` and `LANE_LIST` get the three names in the position `gleepglorp` held, in
     the order chat, fill, kinds. `LANE_LIST`'s order is pinned as a contiguous substring by
     `tests/test_run_tests_lanes.py:252-256`.
   - Everything that schedules, plans, prints help or checks budgets iterates `CANON_LANES`
     (`schedule_lanes` `:353`, `--help` `:108`, `--plan` `:371`, the over-budget check `:534`).
     So the alias is never scheduled, and it needs no `BUDGET` entry. Every canonical lane does
     need one. The usage
     text (`:23`, `:97`) and the unknown-lane message (`:552`) list `gleepglorp` as an alias.
   - The case at `:312` gets three entries plus the alias.
   - `BUDGET`: remove `[gleepglorp]` and add the three provisional budgets, each with a comment
     `# M36 F5 L1b provisional (split of gleepglorp, 541 s / 167 tests); re-measured at the
     closing gate`. The alias has no budget, as `chat` has none.
   - Check how `--parallel` reads budgets and the alias list. An alias must never be scheduled.

5. **`tests/test_run_tests_lanes.py`.**
   - Update `LANES` (`:28`). It drives the plan, help, parallel-children, disjointness and CI
     tests, which then pass unchanged. Update the unknown-lane stderr string (`:252-256`).
   - Rewrite `test_gleepglorp_lane_is_the_drawer_fill_kinds_and_proposal_files` as three set
     equalities plus `_lane_files("gleepglorp") ==` their union. Its intent changes, so rename
     it (rename over delete-and-re-add) to
     `test_gleepglorp_lanes_are_chat_fill_and_kinds`.
   - The chat-alias test (`:192-199`) reads `lanes["gleepglorp"]`. Point it at
     `_lane_files("gleepglorp")` or at `gleepglorp-chat`, whichever keeps its meaning.
   - Add AC6.

6. **Docs.**
   - **`CLAUDE.md:141`:** in the lane list, replace "`gleepglorp` (the drawer, fill and
     proposal-card flow tests)" with the three lanes, with a few words each. Add `gleepglorp`
     to the aliases. Keep it one line's worth: the file is size-limited.
   - **`agents.md`:**
     - `:3061` describes the three lanes and the alias;
     - `:3430` loses "provisional budget 360 s" and points to the lanes section;
     - the budget history (`:3060`) gains "M36 F5 L1b: `gleepglorp` split into three;
       provisional budgets 330/210/210 s from the F4 rate";
     - the Canonical lanes bullet (`:3062`) gains the three lanes, and loses its stale "GleepGlorp
       proposals" under `chats-transcript`;
     - `:181`'s stale "sixteen lanes" is fixed while there.
   - Four browser files' docstrings say "Lives in the `gleepglorp` browser lane"
     (`test_flow_gleepglorp_follow_mcp.py:11`, `test_flow_gleepglorp_fill_provider.py:18`,
     `test_flow_gleepglorp_follow_provider.py:13`, `test_flow_gleepglorp_kinds.py:9`). They stay
     true through the alias, so leave them.

7. **Squawk files.** For each of the three:
   - set status `in-progress`;
   - write Corrective Action (what changed, with `file:symbol`) and Verification (the test
     names, and that each was falsified);
   - for 0382, replace the `api.py::update_mcp_source` evidence line with
     `mcp/service.py::_prune_cache_on_server_change`.

   Leave `Completed` and Sign-Off to the FD.

8. **Run** the new tests, the MCP and provider service and route files, lint, `bash -n`, then
   `make test-unit`. Then the three lanes one at a time, never concurrent with the unit tier.
   Update the flight log, mark the leg `landed`, and signal `[LAND:leg]`.

## Edge Cases

- **An OAuth key absent before and present after the race.** `mutate` sees the fresh row, so
  the pin keeps it. The race test should write a key the row already had (a rotation), plus a
  `_cache` key that is new.
- **A PUT that omits `secrets`.** `data` has no `secrets`, the merge from the fresh row keeps
  them, and no masked resolution runs. Same as today, now fresh.
- **A stdio save where `args` goes from absent to `[]`.** That is not a change (compare
  normalised). From `["-y", "a"]` to `["-y", "b"]` is a change.
- **A type change from stdio to HTTP** is already a server change. No double handling.
- **A duplicate-id create whose body is also invalid.** Validation runs first (422), as today.
  The 409 is only reachable for a valid body.
- **`--lane gleepglorp` in `--parallel` scheduling.** The alias must not appear in the plan, or
  the files would run twice.

## Files Affected

- `the_one/mcp/service.py` — `replace_mcp_source`, `_prune_cache_on_server_change`
- `the_one/llm/provider_service.py` — `create_provider`
- `tests/test_mcp_service.py` (or the MCP service test file found by grep) — the race and prune
  tests
- `tests/test_provider_service.py` or the provider route test file — the 409 test
- `scripts/run-tests.sh` — the lanes, budgets and alias
- `tests/test_run_tests_lanes.py` — the pins and the rewritten partition test
- `CLAUDE.md`, `the_one/agents.md` — the lane docs
- `squawks/0400-*.md`, `squawks/0382-*.md`, `squawks/0402-*.md` — in-progress, corrective
  action and verification
- **Registries and pins checked:**
  - `tests/test_run_tests_lanes.py` (above);
  - any crew or doc file naming `--lane gleepglorp` keeps working through the alias;
  - no browser test file moves or changes.

## Citation Audit

Checked by the FD against the working tree after Leg 1a (2026-11-23). Leg 1a did not touch
these files.

- `mcp/service.py:410-472` `replace_mcp_source` — `existing = await repo.get(source_id)` (`:417`),
  per-key mask resolution, OAuth pinning, `_cache` preserve, `model_validate`, `await
  repo.update(updated)` (`:469`), `_after_write` - verified
- `mcp/service.py:614-640` `change_mcp_source` on `deps.repo.update_in_txn(source_id, mutate,
  on_commit=)` - verified
- `db/repositories.py:1380-1424` `MCPSourceRepository.update_in_txn` — sync `mutate(before)`,
  sets `updated_at`, `KeyError` for an unknown id, the re-entrancy rule - verified
- `mcp/service.py:309-327` `_prune_cache_on_server_change` — type and `url` only;
  `_CACHE_KEYS_DROPPED_ON_SERVER_CHANGE = ("last_check", "auth_posture", "protocol_fallback")`
  (`:82`) - verified
- `llm/provider_service.py:263-298` `create_provider` — `if "id" not in data: data["id"] =
  uuid…` (`:276-277`), `await deps.repo.create(provider, on_commit=on_commit)` with no existence
  check - verified
- `llm/provider_service.py:88-98` `ProviderWriteError(status, detail)`; `api.py:5467` maps it -
  verified
- `tests/test_provider_service.py:199-251` `_wait_for_waiter` and the replace, change and PUT race
  tests - verified
- `scripts/run-tests.sh:59-60` `LANE_LIST` and `CANON_LANES`; `:71` `[gleepglorp]=690`; `:177-184`
  `expand_lane` (glob per pattern); `:205-209` `gleepglorp_pat`; `:290`, `:312`, `:339` its
  uses; `:552` the unknown-lane message - verified
- `tests/test_run_tests_lanes.py:28` `LANES`; `:78` `test_lanes_union_is_the_browser_suite`;
  `:192-199` (chat alias with `lanes["gleepglorp"]`); `:202-219` (the gleepglorp exact set);
  `:252-256` (the lane-list stderr string) - verified (design review corrected `:381`, which is
  the CI task test)
- `tests/test_mcp_last_check.py` ~`:333-340` and ~`:417-423`, the two tests that pin squawk
  0382's defect; `tests/test_mcp_service.py:211` (the raw-SQL race write), `:380` (the URL
  prune test) - design review
- `kinds/provider.py` ~`:351/:376` (the proposal create passes a generated id);
  `db/schema.py:3203` (`id TEXT PRIMARY KEY` only); `api.py:5656` `_provider_write_errors` -
  design review
- `CLAUDE.md:141` the canonical lane list; `agents.md:3060-3061`, `:3430` - verified
