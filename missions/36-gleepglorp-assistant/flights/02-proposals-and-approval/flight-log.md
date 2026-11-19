# Flight Log: Proposals and approval

**Flight**: [Proposals and approval](flight.md)

## Summary
In flight (planning commit `6f073dd4`). Branch `flight/02-proposals-and-approval` from `main` at `b3ee1b91`
(after the Flight 1 merge, #380).

### Flight Director Notes
- Planning, 2026-11-19. Operator decisions:
  - **Scope:** agents with their rules and routines in this flight; the other
    kinds come with form filling later.
  - **Approve** starts GleepGlorp's next turn.
  - **Eval method:** adopted as outlined (flight DD12).
  - **qwen3-4b** is measured only.
  - **Board choices:** card A, approval B, editor note A, states as drawn.
- Carried from the Flight 1 debrief:
  - The "grep tests for exact-dict pins" rule was added to the
    `leg-execution.md` Fix Review Issues prompt during planning.
  - The quiet-host gate re-measure is still owed (squawk 0389) and is taken at
    this flight's first full gate that starts on a quiet host.
  - Squawk 0385 is still open, outside this flight.
- **Design review, cycle 1** (Architect, Opus): approve with changes. Five
  high issues:
  - the compare and the save can't share a transaction;
  - no per-result taint marker is possible without the frozen `core.py`;
  - the view summaries are writable by agents;
  - Leg 2 was too coarse;
  - Leg 3 was too coarse.

  The medium issues covered the error surface, the PUT's omit traps, names to
  ids, the marked-message primitive and its seam, a busy 409, one open
  proposal per chat, the routine flag carried through, the secret guard
  helpers, and the editor event. All were folded in, and the legs grew from 7
  to 10.
- **Design review, cycle 2** (Architect, Opus): approve with changes. No high
  issues. The medium issues were:
  - Approve would add the approval message twice; the prompt now rides on
    `spawn_turn`;
  - the status transitions were inconsistent; Try again, double Approve and
    `failed` versus `applied` are now defined;
  - what `override` covers; untouched-field races are now re-merged and never
    shown as stale;
  - the evals' copy of the taint rule; there is now one predicate,
    `is_trusted_result`.

  The low items were:
  - a stale DD reference;
  - the rule repository's `on_commit`;
  - `session_joined` being synchronous;
  - purging a chat's messages;
  - the secret guard covering every string;
  - "pure" corrected to "shared".

  All were applied. That was the second and last review cycle, so the spec now
  goes to the operator.
- **Execution start, 2026-11-19.**
  - The operator approved the spec. Planning commit `6f073dd4`; flight status
    set to `in-flight`.
  - Phase file `.flightops/agent-crews/leg-execution.md` loaded and valid
    (Crew, Interaction Protocol, Prompts).
  - Crew models:
    - Developer: Sonnet.
    - Reviewer: Sonnet, because the flight touches security-sensitive
      surfaces (the agent write path, taint, the secret guard).
    - Accessibility Reviewer: Sonnet, for Batch C (UI).
  - Batches:
    - A: Legs 1-3.
    - B: Legs 4-5.
    - C: Legs 6-7.
    - Each batch is reviewed and committed as a checkpoint. Then Leg 8, Leg 9
      under its gate, and Leg 10 (HAT).
- **Leg 1 `agent-and-rule-services`: tiered high-risk.** It changes the shared
  agent write path, five routes and a test importer, and repository write
  hooks. A Developer design review was spawned.
  - **Cycle 1:** approve with changes. Three high issues:
    - the services must take their dependencies as an argument (about 10 test
      files patch `api.get_connection`/`get_encryptor`);
    - the retry mechanism was underspecified;
    - the moved helpers raise a new exception type.

    The medium issues were `_validation_detail` (19 sites), create's 409
    under the lock, the other `save` callers, rule `position`, and the body
    models.
  - **Cycle 2:** approve with changes. Stale guidance lines, the Protocol's
    real name (`AgentConfigStore`, which is left unchanged so the four test
    fakes stay untouched), and the untouched-compare column list.
  - Both cycles were folded in, and the leg is `ready`. Implementation
    Developer spawned.
- **Leg 2 `proposal-store-and-tool`: tiered high-risk** (schema v54, a new
  write, the taint rule's trusted set). It was designed while Leg 1 was being
  implemented; only artifacts were written.
  - **Design review cycle 1:** approve with changes. The one high issue:
    `propose_change` must be in `TRUSTED_TOOL_NAMES`, or every next step is
    flagged. The medium issues were name resolution by `list()` plus a filter,
    the surface row by `SURFACE_ROW_NAME`, the built-in names source, the
    exact views and build test edits, and the size test.
  - All were folded in. Flight Director call: a model-only agent change keeps
    the current provider; a provider alone is refused.
  - **No second cycle.** The changes are the reviewer's own fixes plus that
    one clarified rule, with no new mechanism.
  - The leg is `ready` and waits for Leg 1 to land (shared working tree).
- **Leg 3 `proposal-guards`: tiered high-risk** (the shared `taint.py`, the
  model-facing views, a security guard). Two design-review cycles, both
  approve with changes:
  - **Cycle 1:** the override blobs were too broad, the nested OAuth blobs,
    an incomplete provenance list, the per-path tag mechanism, and UUIDs.
  - **Cycle 2:** the tool-config secrets were missing (high), the
    `plain_names` scope, a stale guidance step, and `mcp__` tool-list entries.
  - **Flight Director calls:**
    - Provenance is decided by who can write a value. Operator-only free text
      is trusted.
    - Server-cache MCP connection values and `mcp__` tool-list entries are
      outside.
    - Rule text stays outside, per DD9.
    - Approved values become operator values, a residual recorded in
      SECURITY-MODEL.
  - The leg is `ready`.
- **Leg 4 `proposal-apply`: tiered high-risk** (the write boundary). It was
  designed while Leg 2 was being implemented.
  - **Design review cycle 1:** approve with changes. Two high issues:
    - the precheck blocked "already applied"; a re-read after any failure now
      answers it, and the row-count mark guarantees one apply;
    - the name-rule test covers `/api/gleepglorp`, so `EXEMPT` entries are
      required.

    The rest was the full error-type mapping, gone for 404/`KeyError`/
    `IntegrityError`, the routine plumbing (`stale_precheck_for`, a public
    `_approval_pair`), and Leg 7 handling `config_changed` before the join
    gate.
  - **No second cycle.** The fixes are the reviewer's own mechanisms. The leg
    is `ready`.
- **Leg 5 `approval-continuation`: tiered high-risk** (the turn lifecycle, a
  moved shared protocol).
  - **Design review cycle 1:** approve with changes. Two high issues:
    - the client marks a server-started turn busy only for routines, so a
      small client change was added to this leg;
    - `track_turn` would flash busy and double-push, so the append takes
      `session_locks` directly.

    The rest was the append sequence (repair, event, save, one notify), the
    race branch with no `error`, an explicit `proposal` parameter on
    `_bind_turn_user_marks`, no provider merge needed, the host name kept,
    and reuse of `tests/_routine_app.py`.
  - **No second cycle.** The leg is `ready`.

- **Leg 5 amended before build (Flight Director).** `proposal_event` gains
  `approved_no_turn`, so Leg 6's quiet line can tell an approval with a
  continuation from one without. The client's in-flight tweak checks
  `approved` only.
- **Leg 6 `proposal-card`: tiered high-risk** (a new library control, server
  frames, chat placement). It was designed after a read-only survey of the
  chat client.
  - **Design review, cycle 1:** approve with changes. The three high issues:
    - only `done` appends a reply, so a `turnEnded` hook now flushes held
      cards on every ending;
    - the snapshot arrives after the history render, so cards are drawn on
      the snapshot;
    - the degraded join sites have no `Session`, so the snapshot helper is
      keyed by `session_id`.

    The medium issues: the busy state is polled (`refreshBusy` from the Stop
    updates), the Leg 5 ordering, late-card anchoring, the real tab routes,
    `App.focusAfter`, and testid literals.
  - **No second cycle:** the reviewer's own mechanisms. The leg is `ready`.
  - **Lane budgets:** the `contracts-chat` and `chats-transcript` budgets need
    a quiet-host re-budget at the flight-end gate.
- **Leg 7 `editors-follow-approvals`: tiered high-risk** (editor dirty state,
  a shared studio controller at its size cap).
  - **Design survey finding.** The leave guard means one window cannot hold
    unsaved edits in Agents while approving in Chats. So in one window the
    path is approve, then return; live follow-through with unsaved edits
    applies to a second window or Flight 3's overlay.
  - **The socket gap, accepted.** A window opened straight into Agents has no
    chat socket until Chats is visited.
  - **Design review cycle 1:** approve with changes. Three high issues:
    - the notes record needs an eager owner (now `App.approvals`, loaded
      before `socket.js`);
    - the notes must be drawn at every mount;
    - one central clean/dirty decision from the snapshot replaces per-tab
      return values.

    The review also recommended a split, which was applied (the flight's
    acceptable variation).
  - **Leg change, recorded here per the in-flight rule.** Leg 7 became
    `07-editors-follow-approvals` (core plus the General tab) and
    `08-tabs-follow-approvals` (tiles and tabs). The evals and HAT legs were
    renumbered 9, 10 and 11. Batch C is now Legs 6-8.
  - Both legs are `ready`. Leg 7 also owns the one `App.approvals.record`
    call in Leg 6's card.

## Leg 1 `agent-and-rule-services`: landed

- **Built.** `the_one/agent/service.py` (`AgentWriteError`, `AgentStaleError`,
  `AgentWriteDeps`, `create_agent`, `replace_agent`, `change_agent`),
  `write_checks.py` (the moved validation helpers), `rules_service.py`
  (`create_rule`, `change_rule`), and `the_one/secret_mask.py` (leaf holder of
  `looks_masked` and the mask constants, so the services need no `api` import).
  `SQLiteAgentStore.save` gained `precheck`/`on_commit`;
  `AgentRuleRepository.create`/`update` gained the hooks and `create` a `position`;
  routines' `proposal` is typed as the `ProposalRunner` Protocol. `api.py` went
  7537 to 7122 lines; routes call the services inside `_agent_write_errors()`; old
  helper names stay as wrappers or aliases. `the_one/agents.md` has an "Agent write
  services (M36 F2 L1)" section.
- **Tests.** `THE_ONE_TEST_NETNS=1 make test-unit`: 10735 passed, 15 skipped,
  318.9 s (start load 0.87). Guard set (every file with `/api/agents` or touching
  api internals): 2741 passed. Lanes one at a time, netns on: `agents` 186 passed
  442.6 s (start load 2.19), `agent-tabs` 206 passed 396.8 s (load 2.64),
  `agent-routines` 84 passed 232.5 s (load 2.46). Hosts were loaded, so no budget
  reading. ruff check and format clean.
- **Existing tests unchanged.** `git diff --stat main -- tests/` is empty; the only
  test changes are the two new untracked files `tests/test_agent_service.py` (27
  tests) and `tests/test_rules_service.py` (12).
- **Falsified (yes).** writes-only-named-fields (body built the PUT way: 3 fail);
  stale compare skipped (2 fail); retry removed (4 fail); `on_commit` moved after
  the transaction (rollback test fails); create 409 precheck removed (1 fails); rule
  `position` ignored (2 fail); rule `on_commit` moved out (1 fails). Not falsified:
  refused-keys, 404, surface-id, import-boundary and 422-no-echo tests (plain
  behaviour assertions).
- **Deviations and decisions.**
  - `tests/test_mcp_agent_credentials.py` patches `api.validate_mcp_overrides`, so
    `AgentWriteDeps` carries an optional `override_validator` that `api.py` fills
    with its own reference (keeps that test green unchanged).
  - `update_agent` still does a `store.load` 404 check before reading the body, to
    keep the 404-before-422-bad-JSON order.
  - The rule services take the repository as their first argument.
  - `AgentWriteError` is defined in `write_checks.py` and re-exported from
    `service.py` (avoids an import cycle).
  - A stale compare skips a changed field that has no `base` entry.

## Leg 2 `proposal-store-and-tool`: landed
Implemented by a Developer (Sonnet). The Developer handed back before writing
this entry, so the Flight Director wrote it from the Developer's report.

**What was built:**
- Schema v54: `gleepglorp_proposals`, with no foreign keys and two indexes.
- `the_one/gleepglorp/proposals/`:
  - `shape.py`: the field tables, `normalize`, `describe`;
  - `store.py`: `GleepGlorpProposalRepository`, `mark_op`, `proposal_view`;
  - `tool.py`: `ProposeChangeTool`, with a marked guard slot for Leg 3;
  - `events.py`: `push_proposal_changed`.
- `the_one/gleepglorp/view_fields.py`: the `fields` kind, added to `KINDS`,
  `ALLOWED` and `LIST_KINDS`.
- The factory registers and binds `propose_change` for GleepGlorp only, and
  the tool is in `TRUSTED_TOOL_NAMES`.
- `builtin_tool_names()` in `tools/builtins.py`.
- The chat-delete, purge and rename cascades in `repositories.py`.
- **Shared normaliser:** Leg 1's private `_strip_own` became the public
  `service.comparable_value(field, value, surface_ids)`. Leg 1's precheck and
  `shape.py` both use it.
- **Docs:** `the_one/agents.md` gains "GleepGlorp proposals (M36 F2 L2)";
  CLAUDE.md gains a paragraph.

**Tests:**
- **New:** 50 tests.
  - `test_gleepglorp_proposals_shape.py` (19), `_store.py` (16), `_tool.py`
    (14).
  - A v54 class in `test_db_migration.py` (3).
- **Targeted run:** 336 pass across the proposal, build, views, read-tool,
  migration and template files.
- **Falsified, yes:**
  - the trusted set;
  - the one-open refusal;
  - the same-target replace;
  - the replace-failed path;
  - the `mark` status clause;
  - the chat-delete cascade;
  - the no-write test (the tool made to save an agent).
- **Not falsified** (plain behaviour assertions):
  - the shape refusals and name resolution;
  - the other cascades;
  - the forbidden-keys pin;
  - the description limits (513 characters; the 120-token check passed).
- **Existing tests edited on purpose** (pins this leg changes by design):
  - `test_gleepglorp_build.py`: the tool set;
  - `test_gleepglorp_views.py`: 11 kinds and `PARITY_DRIVER`;
  - `test_gleepglorp_read_tool.py`: the enum count;
  - `test_db_migration.py`: 53 becomes 54;
  - `test_notes_tools.py::test_trusted_set_is_exactly_the_documented_names`:
    `propose_change` added.
- **Unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, start load 0.61):
  - 10787 passed, 15 skipped, 321.46 s;
  - 1 failed: the trusted-set pin above, fixed afterwards;
  - a green full re-run comes with Leg 3's end-of-leg run.
- **Other checks:** ruff is clean. No static file changed.

**Decisions the leg left open:**
- **Rule position** is stored 1-based, as the model gave it. Leg 4 subtracts
  1.
- **Stored `changes`** use `AgentConfig` field names with ids.
- **Routines:** the `schedule` is stored with `anchor_at`, and the routine
  `base` uses the shape's names. Leg 4 converts to `_base_of` keys.
- **Name resolution** reuses `view_core._names` and `_surface_owners`, with
  no decrypts.
- **Extra refusals:** `normalize` also refuses a routine name the agent
  already has, and a rename onto another routine's name.
- **Text bounds:** description 1000, prompt 20000, model id 200, lists 100.
- **`push_proposal_changed(session_id, view)`** takes a built view.
- **The `read_app_config` description** is left unchanged. Its prompt text is
  Leg 9's.

## Leg 3 `proposal-guards`: landed
Implemented by a Developer (Sonnet).

**What was built:**
- `the_one/agent/taint.py`: `OPERATOR_TYPED_MARK`, `READ_APP_CONFIG_NAME` and
  `is_trusted_result(name, content)`; `compute_taint`'s TOOL branch uses it
  (sources unchanged: the tool name, `routine:listed`, `unknown tool`).
- Provenance: `OPERATOR_PATHS`, `OUTSIDE_PATHS` and `OUTSIDE_VALUE_PREFIXES`
  beside `ALLOWED` in `view_core.py`; `Ctx.fields_only`;
  `views.read_with_provenance` plus the walker (`walk_paths`,
  `path_provenance`, `is_operator_only`). `views.read` keeps its signature and
  returns the data.
- View changes: the agents list summary is operator fields only; the detail's
  rules carry `number`; `fields_only` drops `description`, `system_prompt` and
  the rules' `text`. `read_app_config` gained the boolean `fields_only` (the
  description grew by about 40 characters) and prefixes the mark when the walk
  finds no outside value. (Note: this edits the tool description, so Leg 9's
  eval run covers it.)
- `encryption_corpora.secret_leaves(c, *, min_len=8)`, per column as AC7.
- `proposals/guard.py` (`check`, `REFUSAL`, `KEY_PREFIXES`, `KEY_MIN_LEN`,
  `KEY_MIN_ENTROPY`), called by `propose_change` after normalise and before the
  taint and insert.
- Docs: `SECURITY-MODEL.md` (provenance paragraph with the accepted residual,
  and the guard paragraph with its trade-offs) and `the_one/agents.md`. No guide
  topic mentioned the agents list summary; `test_gleepglorp_guide.py` is green.

**AC5 table as built** (marked = the result starts with the mark):

| Read | Marked |
|---|---|
| `agents` list | yes |
| `agents` detail `fields_only` | yes |
| `agents` detail, an agent with no description, prompt or rules | yes |
| `agents` detail full (description, prompt or rule present) | no |
| `agents` detail with an `mcp__` entry in a tool list | no |
| `mcp_servers` list | yes |
| `mcp_servers` detail, stdio with no cache | yes |
| `mcp_servers` detail with tools or cached protocol values | no |
| `routines` for an agent with no routines | yes |
| `routines` with any routine | no |
| `overview`, `providers`, `knowledge_bases`, `connectors`, `secrets`, `built_in_tools`, `settings`, `fields` (list and detail) | yes |
| any failure or plain message | no |

The outside sets are pinned by tests: agents `description`, `system_prompt`,
`rules[].text` (and `mcp__` list entries); routines `name`, `prompt`; MCP
`tools[]`, `connection.protocol_version`, `auth_posture`,
`protocol_fallback`.

**Tests:**
- New: `test_taint_results.py` (11), `test_gleepglorp_views_provenance.py`
  (16), `test_gleepglorp_proposals_guard.py` (12): 39 tests.
- Unit tier, `THE_ONE_TEST_NETNS=1 make test-unit`: 10827 passed, 15 skipped,
  325.68 s (start load about 0.5). Green; this also confirms Leg 2's pin fix.
  Doc-pin tests re-run after the doc edits: 818 passed. ruff check and format
  clean. No file under `evals/` or `static/` changed.

**Falsified:**
- Marker check replaced by "trust `read_app_config` by name": yes (4 of
  `test_taint_results.py` fail).
- Corpora check dropped: yes (6 of the guard tests fail).
- Entropy rule dropped: yes (the prefix-and-entropy test fails).
- The other tests (drift tables, outside-set pins, AC5 table, `secret_leaves`
  columns, UUID and prose passes): not falsified, plain behaviour assertions.

**Existing tests edited on purpose:** `test_gleepglorp_views.py::test_agent_detail`
(rule `number`); `test_gleepglorp_read_tool.py` (a `body()` helper strips the
mark before `json.loads` in four places, and the never-raises test patches
`views.read_with_provenance`).

**Decisions:**
- Tables use broad prefixes for kinds with no outside field (`providers`,
  `knowledge_bases`, `connectors`, `secrets`, `built_in_tools`, `settings`,
  `fields`, and `overview.detail`'s dynamic `counts`/`names`); a new key there
  is operator by default. The drift test still requires every emitted path to
  resolve.
- The guard scans `norm.changes` (the stored form, with ids), not the raw
  arguments. `sk-ant-` is redundant with `sk-` (its tail counts `ant-`).
- The prefix rule needs a non-alphanumeric character before it, so `task-...`
  is not a key.
- A non-`true` `fields_only` is ignored (never trusted).
- `evals/checks.py::_taint_expected` is untouched (Leg 8).

## Batch A review fixes

- **Provenance tables explicit.** `view_core.py::OPERATOR_PATHS` no longer trusts whole
  kinds: every current key of `overview`, `providers`, `knowledge_bases`, `connectors`,
  `secrets`, `built_in_tools`, `settings` and `fields` is declared as its own path, so a
  new key falls to outside (fail closed). The only prefix kept is
  `built_in_tools.detail.settings` (a tool's own Config field names, dynamic). New tests in
  `tests/test_gleepglorp_views_provenance.py`: `test_the_formerly_broad_kinds_have_a_reviewed_key_set`
  (pins `ALLOWED` per kind and level to a reviewed frozenset) and
  `test_no_whole_kind_prefix_is_declared_operator`. Falsified: a dummy `"dummy"` key added to
  `ALLOWED["secrets"]["detail"]` failed the pin and
  `test_every_list_and_detail_key_is_covered_by_a_table`; removed by editing.
- **Guard hex rule.** `proposals/guard.py` gains `HEX_KEY_MIN_LEN = 32`: a run of 32 or more
  hex characters bounded by non-alphanumerics is refused (after the hyphenated-UUID
  exemption, so a UUID passes, a bare 32-hex run and a 40-character git SHA are refused).
  Trade-off noted in the module docstring and `SECURITY-MODEL.md`. New test
  `test_the_hex_run_rule`; falsified (rule disabled by editing, test failed, restored). The
  low-entropy case in `test_prefixes_and_the_entropy_rule` now uses `"z" * 80` (`"a" * 80`
  is hex).
- **`propose_change` output.** Verified: the success and open-proposal sentences carry only
  ids; the refusals come from `shape.py` and echoed model-supplied names/field keys
  unbounded. The model's own arguments are not outside content, so echoing is acceptable,
  but each is now cut to a 40-character quote (`shape._q`). New test
  `test_a_refusal_quotes_a_model_supplied_value_only_short`; falsified (cut removed, failed,
  restored). No refusal echoes a tool result, web or MCP text.
- Unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`): 10831 passed, 15 skipped, 0 failed
  (313.86 s). No static file changed, so no browser lane applies.

## Batch A checkpoint (Flight Director)
- **Review:** the Reviewer (Sonnet, security-sensitive tier) confirmed Legs
  1-3 with three non-blocking findings:
  - broad `OPERATOR_PATHS` prefixes;
  - hex-only keys missed by the guard;
  - a check that `propose_change` refusals echo no outside text.

  All three were fixed, and a scoped re-review confirmed them (91 passed).
  One nit was accepted: the routine-name refusal at `shape.py:567/586`
  interpolates an already-validated name of at most 64 characters, unquoted.
- **Legs 1-3 completed;** checkpoint commit follows. No Accessibility Reviewer:
  no UI change in Batch A.

## Leg 4 `proposal-apply`: landed

**Built.**
- `the_one/gleepglorp/proposals/apply.py`: `apply_proposal`, `dismiss_proposal`,
  `ProposalApplyResult` (outcomes `applied`, `already_applied`, `failed`, `stale`,
  `gone`, `busy`, `closed`, `dismissed`), `ProposalNotFound`, `failure_errors`.
  Order (a) pre-checks, (b) service call with the mark in its transaction,
  (c) re-read on any exception, (d) map to stale, gone or failed. Frames are sent
  from inside `apply_proposal` (so the eval harness gets them too).
- `the_one/interfaces/web/gleepglorp_proposals_api.py` (GET list, POST approve,
  POST dismiss), included from `api.py`.
- `create_agent(..., on_commit=)`; `routines/service.py`: `approval_pair` public,
  new `stale_precheck_for(base, touched, override, proposed)` (`_stale_precheck`
  delegates to it), `proposal` annotations widened to `ProposalRunner`.
- `store.py::display_values` (ids to names, shared with `proposal_view`).
- `tests/test_api_name_rule.py` EXEMPT gained the approve and dismiss routes.
- Docs: `agents.md` (routes, apply order, `config_changed` in the WebSocket table,
  `approval_pair` rename), `CLAUDE.md`, `SECURITY-MODEL.md`.
- `# Leg 5: continuation` markers left after the apply frames and after the
  dismiss frame in `apply.py`.

**Tests.** New: `test_gleepglorp_proposals_apply.py` (34) and
`test_gleepglorp_proposals_api.py` (7). `THE_ONE_TEST_NETNS=1 make test-unit`:
10872 passed, 15 skipped, 342.3 s (start load 1.80, loaded host). ruff check and
format clean. No static file changed.

**Falsified (yes).** Base skipped (3 fail); re-read in step (c) dropped (agent-change
concurrent test fails); row-count check dropped (rule-create concurrent test fails);
busy check removed (2 fail); routine flag dropped (2 fail). Others are plain
behaviour assertions (not falsified).

**Existing tests edited.** Only `test_api_name_rule.py` EXEMPT (required).

**Decisions.**
- Spec's `position=position-1 or None` would turn position 1 into "append";
  used `None if pos is None else pos - 1` and pinned it by a test.
- Routine `base` already uses the `_base_of` keys (name, prompt, schedule,
  anchor_at, enabled), so no conversion was needed; touched keys absent from
  `base` (`finished_at`) are not compared.
- `config_changed.fields` are stored field names (the routine's `anchor_at` hidden);
  `result.fields` are labels.
- `RoutineLimitError` (and `RoutineScheduleError`, loc `["schedule"]`) map to
  `failed`; `RoutineLimitError` has `loc []`.
- Tests reset the module write lock (`_write_lock.reset_for_test`) because it binds
  to the first loop that contends for it.
- Fixed a pre-existing E501 in `shape.py` (a split string; format only).

## Leg 5 `approval-continuation`: landed

**Built.**
- `the_one/sessions/turn_host.py` (new): `TurnHost` Protocol (gains
  `append_marked_message`), `set_turn_host`, `get_turn_host`; `routines/runner.py`
  re-exports the old names, and `runner._host` still reads through a module
  `__getattr__` (a routine test reads it).
- `Message.proposal_id` / `proposal_event`; codec stores, decodes (unknown event value
  dropped) and projects them on the `user` history event, only when set.
- `app.py`: `_RoutineTurnHost.append_marked_message` and `spawn_turn` routing a
  `turn_info["proposal"]` to `_spawn_proposal_turn` (source `proposal`); the lock-free
  `_append_marked_user_message`; `_process_and_broadcast` marks the live `user` frame;
  `_bind_turn_user_marks(..., proposal)` at both save sites; the race branch in
  `_locked_message_processing`.
- `the_one/gleepglorp/proposals/continuation.py` (new): texts, `proposal_title`,
  `is_ready`, `on_approved(conn, p, summary)`, `on_dismissed(p)`. No host: quiet
  no-op. `apply_proposal` / `dismiss_proposal` take `continue_chat: bool = True`.
- Client: `turn-frames.js` treats `proposal_event === 'approved'` as in flight;
  `transcript.js` adds no source prefix when `proposal_id` is set.
- Docs: `agents.md` (continuation block, WebSocket `user` row), `CLAUDE.md`.

**Tests.** New: `test_gleepglorp_proposals_continuation.py` (27) and
`test_turn_host.py` (5). `THE_ONE_TEST_NETNS=1 make test-unit` (start load about 1.3):
10903 passed, 15 skipped, 1 failed, 323 s; the one failure was
`test_track_turn_guard.py` (below), fixed, and the guard plus the new, routine runner
and static-guard files re-run green (448 passed). Lanes, one at a time, netns and
WebKit required: `chats` 176 passed (327.6 s), `chats-transcript` 163 passed (363 s).
Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`)
green. ruff check and format clean.

**Falsified (yes, for the marked ones).** Dropping `turn_info` in the spawn fails 4
tests (approve spawn, end-to-end, stop, reaped approval); restoring the early return
in the race branch (`if False and ...`) fails the race test and the same four.
Dismissal, no-op, texts, codec, providers and host tests are plain behaviour
assertions (not falsified).

**Existing tests edited.** None.

**Decisions.**
- `tests/test_track_turn_guard.py` bans `session_locks[...]` outside `_locks.py`, and
  the leg needs the lock without `track_turn`; added `hold_session_lock` to
  `sessions/_locks.py` (the allowed module: same lock, no push, no turn count) rather
  than editing the guard.
- `_save_session_to_db` already calls `notify_sessions_changed` through the
  repository update, so the append makes no extra call (one push, asserted).
- `on_approved` takes `(conn, p, summary)` and `on_dismissed` `(p)` (the proposal row,
  not a view, which has no `session_id`); the `approved_no_turn` fallback covers both
  not-ready and a raising spawn.
- No provider merge code: every builder converts per message (tests per provider
  type pin two user entries and no mark leakage).
- Unrelated: the spawned turn's source label is `proposal`.

## Batch B checkpoint (Flight Director)
- **Review:** the Reviewer (Sonnet, security-sensitive tier) confirmed Legs
  4-5 with no blocking issues.
- **Full unit tier** (`THE_ONE_TEST_NETNS=1 make test-unit`, run by the
  Reviewer): 10904 passed, 15 skipped, 317 s. The static JS guards ran green.
- **Accepted nits:**
  - **The two client tweaks** (`turn-frames.js`, `transcript.js`) have no JS
    test yet. Leg 6's browser tests exercise the approval turn's busy state
    and the quiet line, which covers them.
  - **The busy check is advisory and not atomic** with the write. The
    row-count mark guarantees one apply either way.
  - **`_is_gone` treats any `KeyError` as gone.**
- **Crew rule slip (recurring, Flight 1 methodology observation 4).** The Leg 5
  Developer left five backgrounded `sleep 1500`-`1790` timers after handing
  back. The Flight Director stopped the agent's task (TaskStop), which ended
  them; no test run was affected.
- **No Accessibility Reviewer.** The Batch B client change is a two-line
  behaviour tweak with no new UI. Batch C carries the accessibility review.
- **Legs 4-5 completed**; the checkpoint commit follows.
