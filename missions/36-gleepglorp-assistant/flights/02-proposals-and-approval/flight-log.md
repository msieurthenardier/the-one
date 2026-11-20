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
- **Leg 9 `proposal-evals-setup`: tiered high-risk.** It touches frozen
  scoring modules and changes the eval taint mirror.
  - **Deviation:** the one-attempt fairness pass spends quota, so it moved to
    the start of the gated Leg 10. Leg 9 is fully offline.
  - **Deviation:** there is no `no_delete_proposed` check. The tool has no
    delete action, so the check could never fail; the delete scenario uses
    `no_proposal` instead.
  - **Design review cycle 1:** approve with changes. Two high issues:
    - an approve turn with no text broke the harness reply rule (it now ends
      the conversation);
    - the run-global turn indexing (explicit `turn` on reply checks, with a
      lint test).
  - The Leg 10 sequence is fixed: fairness pass, same-prompt control
    baseline on D-min, screen, ablate, n=20 confirmation as
    `m36f2-gleepglorp.json`.
  - **No second cycle.** The leg is `ready`.
  - **The frozen-module re-pin is not purely additive.** The operator is asked
    before the commit that contains it.
- **Leg 10 `proposal-evals-rounds`: tiered low-risk, so no design review.** It
  is a procedure leg whose every quota round sits behind an operator gate;
  its code change is the prompt text, measured by its own rounds. It is
  designed as one artifact with explicit gates 0-5 (Flight 1 methodology
  observation 1). It is `ready`.

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

## Leg 6 `proposal-card`: landed

**Built.**
- Server: `proposal_view` gains `title`, `target_gone`, `resolved_at` and, for routines,
  `schedule_text`, `next_runs`, `base_schedule_text`, `base_next_runs`; `proposal_changed` carries
  `session_id`; `proposals_snapshot` (`events.py::snapshot_frame`, `app.py::_send_proposals_snapshot`)
  is sent after `session_joined` at all eight join sites (six ok, two degraded), GleepGlorp chats
  only, newest 200.
- Library: `App.ui.changeTable` (`ui/change-table.js`, CSS, catalogue row, contract file in
  `contracts-chat`); `App.ui.noteFlag` subject `proposal`.
- Chat: `areas/chat/proposal-cards.js` (state, seven states, placement, busy, actions, focus);
  hooks in `transcript.js` (redraw, clear, the quiet line, a `data-role="user"` mark),
  `turn-frames.js` (two frames, `turnEnded`), `socket.js` (close), `send.js` and `chat.js`
  (`refreshBusy`), `turn-work.js` (`isOpen`). Testids in the registry. Behavior specs written
  (not run): `gleepglorp-proposal-create-agent.md`, `gleepglorp-proposal-attach-mcp.md`.
- Leg 7 hook: `appliedByApproval(e, view)` in `proposal-cards.js`, called once per approve
  response with status `applied`.

**Tests.** New: `test_gleepglorp_proposals_card_payload.py` (12), `test_flow_chat_proposals.py`
(14), `test_ui_change_table_contract.py` (10 x 2 engines). Lanes, one at a time, netns, WebKit
required: `contracts-chat` 350 passed (125 s, start load 3.2), `chats-transcript` 177 passed
(455 s, load 9.6), `chats` 176 passed (363 s, load 4.8); all hosts loaded, so no budget re-measure.
`THE_ONE_TEST_NETNS=1 make test-unit`: 10915 passed, 15 skipped, 4 failed, 382 s; three were this
leg's (below, fixed and re-run green: 515 static-guard tests, plus `test_flow_chat_proposals` and
`test_flow_chat_turn_work` 27 passed after the fixes), and `test_chat_history_purge::
test_purge_loop_catch_up_sweeps_due_db` failed under load and passed in isolation (not touched).
The lanes ran before those three small fixes (CSS owned-class selectors removed, a `data-role`
mark replacing a `ui-message--user` class test, `_nav.href` in the new test); the changed paths
were re-run as above. ruff check and format clean.

**Falsified (yes).** Card hold removed (5 flow tests fail); quiet-line branch removed (same set);
busy sync forced off (approve, scripted, in-flight join: 3); Leg 5's `approved` in-flight mark
removed (scripted and approve tests fail); snapshot GleepGlorp gate removed and rule position
fixed to 1 (3 server tests fail). Not falsified: the contract file, the table and clamp
assertions, the refused-click test, the withdrawn test.

**Existing tests edited (by design).** `test_run_tests_lanes.py` (contracts-chat gains
`change_table`), `test_ui_feedback_contract.py` (noteFlag proposal case, additive).

**Decisions.**
- Hold uses `send.isCurrentBusy() || turnWork.isOpen()` (a scripted or foreign turn has an open
  group but no in-flight mark).
- Known edge: a snapshot during an in-flight join places a card after the open group, so the
  turn's reply lands after it.
- The failed state's errors are one status line (label: message), not a list.
- Quiet-host re-budget owed at the flight-end gate: `contracts-chat` (150 s) and
  `chats-transcript` (540 s, already passed); `chats-transcript` gained 14 tests.
- The app guide topics were not touched (no guide topic's page or label changed)

## Leg 7 `editors-follow-approvals`: landed

**Built.**
- **Controller split first (AC1):** `agent-editor-controller.js` 798 to 660 lines (not the
  planned ~620: the follow module's wiring added 20 lines). Moved `onSaveError_` and
  `showToolOverrideErrors_` to `agent-editor-save-errors.js` (130 lines) and `buildCallbacks_`
  to `agent-editor-callbacks.js` (115 lines), each a `create(ctx)`; no behaviour change.
  `agents` (186 passed, 7 of the new, not yet wired test file failing as expected) and
  `agent-tabs` (206 passed) were green on the split alone.
- `static/js/approvals.js` (eager, after `store.js`): `App.approvals` `record` / `forAgent` /
  `clear` / `CONFIG_CHANGED`, a de-duplication set capped at 200; the event goes out on the
  `document` (the Studio bus's own transport, so no load-order dependency).
- Callers: the socket's pre-gate `config_changed` handler (`socket.js`) and Leg 6's
  `appliedByApproval` in `proposal-cards.js` (detail from the view: kind, `agent_name`,
  `fieldKeys(view)`, the card's session id, id, `resolved_at`).
- `areas/studio/agent-editor-follow.js`: one listener registered once, the central clean/dirty
  apply per field group (`GROUPS`, the extension point for Leg 8), the notes drawn at every
  mount and patch (`follow_.afterMount()` in `renderEditor` and `patchEditor_`), `clear` on a
  successful Save and on Cancel. Controller lines added: the create block, two `afterMount`
  calls, two `clear` calls.
- General tab: plain setters `setField` / `setModel`, `placeNote` (the tab owns its layout, so
  no library class is named outside `js/ui/`), `NOTE_FIELDS` so the panel note can name model,
  max iterations, retention and rich visuals; the field wrappers are kept in variables.
- `agent-model-picker.js::fetchModelsForProvider` now returns its promise (callers ignore it),
  `agent-data.js::fetchAgentFresh`, `agent-editor-selfconfig.js::recheckStoredNote_` treats
  `llm_model` as the provider and model pair, drawer `refreshRules` plus the drawer's own
  listener (rule, routine, agent), `studio.css` rule, registry row, `agents.md` section,
  CLAUDE.md paragraph, `agent_tabs_pat` entry in `scripts/run-tests.sh`.

**Tests.** New `tests/browser/test_flow_agent_editor_follows_approval.py` (7; `agent-tabs`):
clean fields with notes, dirty prompt beside a clean description, another agent's event, a
duplicate event, notes cleared on Cancel and Save, the return path (studio not yet initialised,
and again after a leave), and one real approval through the Leg 4 route's broadcast.
Final verification after the last code change (all netns, WebKit not involved): static guards
and `test_area_module_size`, `test_ui_guards`, `test_run_tests_lanes`, `test_ui_ownership`,
`test_nav_helper`, `test_store_static`, `test_tool_categories` 550 passed; unit tier 10960
passed, 18 skipped (336 s, start load 1.65); `agents` 186 passed (435 s, start load 1.78);
`agent-tabs` 213 passed (407 s, load 3.58); `agent-routines` 84 passed (228 s, load 2.08);
`chats` 176 passed (322 s, load 3.46). Hosts loaded by an earlier lane, so no budget
re-measure (`agent-tabs` gained 7 tests: 213 tests in 407 s is inside its 600 s budget).
ruff check and format clean.

**Falsified (yes), by editing the fix out and putting it back.** Dirty check forced
false and de-duplication off, applied together: exactly the dirty-prompt test and the
duplicate-event test failed (one each); `clear` calls removed from Cancel and Save: the clear test fails. Not falsified: the other-agent
test, the return-path test, the real-approval test, the clean-fields test.

**Existing tests edited (by design).** `tests/test_tool_categories.py` (the `byCategory` read,
the load-order and literal-copy lists now name `agent-editor-callbacks.js`, which took the
callback bag with the Tools tab's categories). No other test changed; the unit tier ran once
before the final edits (one failure, `test_nav_helper` raw-hash guard on the new test, fixed)
and again at the end.

**Decisions.**
- The note attribute is `data-field` as the leg says; it shares the name with form inputs, but
  `collectFormData` only reads `input|textarea|select` so the note is never collected; the test
  selects the description input by id.
- A dirty provider and model pair moves the baseline to the stored values without touching the
  DOM (no async refetch); other dirty groups follow the leg's write, read, write back.
- Note text for a model change names the pair under `llm_model`; a provider-only change still
  notes under the Model field.
- The agents lane's first pass picked the new test file up through the `test_flow_agent_*`
  glob before it had a lane entry; its 7 failures there were the unwired file.
- Process: the first pair of lane runs was started from a detached subshell and was restarted
  once (my own recorded group, TERM) so completion notifications work..

## Leg 8 `tabs-follow-approvals`: landed

**Built.**
- `agent-editor-follow.js`: `TAB_GROUPS` (`tools` = `enabled_tools` + `disabled_tools`,
  `mcp_source_ids`, `kb_ids`) with `applyTabGroup_`, which decides **per item** rather than per
  group (a set of switches is not one value, so one dirty row must not freeze its clean
  neighbours): editor map against the baseline-snapshot map says what the operator changed; changed
  items keep their choice, the rest take the stored value, and the baseline takes the stored value
  for all (write stored, read the snapshot into the baseline, put the kept choices back). The
  `disabled_tools` ungated-prefix union is only ever read from the DOM. `liveList_` for `kind`
  `rule` / `routine`. `ctx.refreshMcpSources` (the controller passes
  `agentData.refreshMcpSourcesCache`) runs before an MCP apply and `setSources` reconciles.
- Plain silent accessors on the tab handles: `followMap` / `followMapFor` / `followSet` /
  `followPlace` on Tools (`tools-tab.js`), MCP (`mcps-tab.js`; a credential-dirty tile gets only its
  master set) and Knowledge (`knowledge-tab.js`; `followMap` is `null` while the list has not
  loaded, so nothing is set).
- Rules: `buildRulesSection` returns a handle `{reload, placeNote}`, `renderRulesNotesTab` returns
  it, `agent-editor.js` returns it from `buildPanel` and stores `h.rules`. `reload()` captures the
  inline edit's text, reloads, puts the typed text back (and fires `input` so the counter and Save
  follow) and adds `rules-row-changed-note` only when the stored text also changed. Routines:
  `reload()` (loads when the tab is active; an inactive tab loads on its next `activate`) and
  `placeNote`.
- Notes: `agent-approved-change-note` gains `data-item` and a `--item` modifier class (CSS; the
  first attempt styled `.ui-group-tile` in `studio.css` and tripped `test_ui_ownership`, so the
  rule keys off our own modifier class). Tile notes are drawn at every mount from the record plus a
  module map `changedItems[agent][group][item]` (the record carries field names only; cleared by
  `clear(name)`). Rules and Routines get one note at the top of the list (`data-field` `rules` /
  `routines`).
- Docs: `the_one/agents.md` "The other tabs follow too (M36 F2 L8)", registry rows
  (`rules-row-changed-note`, `agent-approved-change-note` extended). No new lane entry (the cases are in
  the Leg 7 file, already in `agent_tabs_pat`).

**Tests.** Seven added to `tests/browser/test_flow_agent_editor_follows_approval.py` (7 to 14): clean
tool, MCP and KB toggles follow with notes (and survive a tab switch and a remount); a dirty tool row
kept beside a clean one; an MCP tile with dirty credentials kept (value and master); KB list not loaded
sets nothing, first load shows the stored value; a rule approval with an open inline edit keeps the
typed text and shows the row caption; a clean rule list just updates (Add textarea untouched); a
routine approval reloads with an open New form kept.

**Verification (after the last code change; all `THE_ONE_TEST_NETNS=1`).** Static guards and
`test_area_module_size`, `test_ui_guards`, `test_ui_ownership`, `test_run_tests_lanes`, `test_nav_helper`,
`test_token_definitions`, `test_design_tokens_a11y` passed (one `test_ui_ownership` failure on the
first CSS, fixed). Unit tier 10919 passed, 15 skipped (312 s, start load 0.49). Lanes, one at a time:
`agents` 186 passed (449 s, start load 0.18), `agent-tabs` 220 passed (472 s), `agent-routines` 84 passed
(261 s); start loads under 1.0 for each (agent-tabs and routines read about 0.2-0.5), so the readings are
quiet. No lane re-budget needed (`agent-tabs` 472 s against 600 s). ruff check and format clean.

**Falsified.** Yes for the inline-edit capture: with `fresh.value = typed` removed,
`test_a_rule_approval_keeps_an_open_inline_edit` failed (the field read "Approved wording"); restored
by editing. Not falsified: the other six new tests.

**Existing tests edited:** none.

**Decisions and limits.**
- Per-item rather than per-group for the three tab groups (see above); a boolean switch can never
  be "kept with a different value" than the stored one, so there is no kept-variant note text.
- Known limit: an approval that lands while no editor is open for that agent shows the right toggles at the next mount
  but no per-tile note (the item diff is known only to an open editor). Documented in `agents.md`.
- The KB-not-loaded test opens Agents first and fails the list request only afterwards, since a failed
  list at Studio's first load breaks the whole area.

## Batch C review fixes

**A. Return-path tile notes.** `proposal-cards.js` computes `items` from the approved view (symmetric difference of the stored and proposed `disabled_tools`/`enabled_tools`, `mcp_source_ids`, `kb_ids`; the view shows MCP and KB by name, so names are mapped to ids through `App.store` before a second `record` with the same proposal id). `App.approvals.record` merges `items` before de-duplication; new `App.approvals.itemsFor(name)`; `drawNotes_` reads the record's items plus an open editor's live `changedItems`. A null `enabled_tools` names no tile.

**B. Accessibility.** Card root `aria-live="off"`; one persistent `role=status` node (`proposal-announce`) outside the rebuilt body speaks the first live appearance, then applied/dismissed/withdrawn once; snapshot/replay draws are silent; failed/stale stay with their `role=alert` (status empty, no duplicate text). Busy buttons: `aria-disabled` only, no native `disabled`. `App.ui.changeTable` two-column Show all buttons are "Show all {label} (now)" / "(proposed)", testids `-more-now` / `-more-proposed`, `data-column`; one-column unchanged. Docs: registry, control inventory, agents.md.

**Tests.** Falsified (yes): the return-path tile-note test (itemsFor removed), the busy-button test and the status-node test (native disabled restored / aria-live removed). Not falsified: the two-long-values contract test (both engines) and the silent-snapshot test. `test_a_long_value_is_clamped_in_the_card` updated to the new testid.

**Results.** `THE_ONE_TEST_NETNS=1 make test-unit` 10919 passed, 15 skipped (an earlier run caught a `|` in my inventory edit, fixed). Lanes: contracts-chat 352, chats-transcript 180, agent-tabs 221, all passed. `test_flow_chat_proposals.py` and the follows-approval file also passed directly. ruff check and format clean.

## Batch C checkpoint (Flight Director, commit `96f81cea`)
- **Reviews:** the code Reviewer (Sonnet) and the Accessibility Reviewer
  (Sonnet) both confirmed Legs 6-8.
  - The code Reviewer ran `contracts-chat` (350) and `chats-transcript`
    (177), plus the unit tier with `-rs`: 10919 passed and 15 skipped, which
    is exactly the documented netns set. The 18 skips from Leg 7 did not
    reproduce.
- **Fixed before the commit,** then confirmed by a scoped re-review:
  - **Return-path tile notes:** the card records its changed items.
  - **Accessibility:**
    - the card is not a live region; one status node speaks each state;
    - alerts are announced once;
    - busy buttons stay focusable with `aria-disabled`;
    - the "Show all" names are distinct per column.
  - **Re-review results:** guard set 428 and the two flow files 32 passed.
  - **Developer's runs:** unit 10919/15, `contracts-chat` 352,
    `chats-transcript` 180, `agent-tabs` 221.
- **Accepted, low severity:**
  - **Duplicate MCP or KB names.** A return-path tile note can mark the wrong
    one of two items with the same name, since a proposal carries names.
  - **A snapshot during a running turn** draws a card the live path would have
    held back.
  - **The approvals `seen` set** is capped at 200 per window.
  - **The 10px eyebrow table headers** follow the project recipe.
  - **The card's `h3`** skips a heading level inside the chat log.
- **Possible flake to watch at the flight-end gate.**
  `test_chat_history_purge::test_purge_loop_catch_up_sweeps_due_db` failed
  once under heavy load in Leg 6's unit run and passed in isolation. It has
  not failed since.
- **Legs 6-8 completed.**

## Leg 9 `proposal-evals-setup`: landed

**Built (offline; no model call, no quota, plan token never read).**
- `evals/README.md`: "### The eval method (M36 F2)" under Convention (the eight points of
  DD13, safety versus ranking classes, qwen3-4b measured only, the Leg 10 sequence), the turn
  types ("Approve and dismiss turns"), the proposal scenarios and checks, the baseline note
  (`m36f2-gleepglorp.json` recorded in Leg 10; `m36-gleepglorp.json` becomes history).
  CLAUDE.md's Prompt evals bullet gains one clause. The stale comment in
  `measure/tools-web-on.toml` now lists `propose_change`.
- `evals/scenario.py`: `StepTurn` (`{approve = true}` / `{dismiss = true}`), parsed with the
  file and field in every refusal; the first turn must be a string; `expand` runs on text only.
  `evals/runner.py`: `Plan.llm_calls` counts text turns only (a lower bound; an approve adds
  one call); the transcript records each turn's `step` / `approve_outcome` and the run's
  `proposals`.
- `evals/harness.py`: `_decide` runs an approve or dismiss through the app's own
  `apply_proposal` / `dismiss_proposal` with `continue_chat=False` and returns the
  `continuation` text to send (`approval_text` / `dismissal_text`); a step that sends no text
  (`none_open`, `stale`, `failed`, `gone`) ends the conversation and skips the reply and
  first-tool-timeout rules. `_write_deps` mirrors `api._agent_write_deps` (store with the
  encryptor, MCP, provider, secret and tool-config repositories, `validate_mcp_overrides`)
  without importing the web layer. Proposals are read in the `finally` as plain views
  (`RunTrace.proposals`); each turn is attributed by a before/after snapshot of
  `list_for_session`, and its open count recorded. Cleanup (`_clean_proposal_state`) at seed
  (after `_remove_app_rows`, before the agent snapshot) and in the `finally`: the run's
  `gleepglorp_proposals` rows by session id, and every agent absent from the pre-seed snapshot.
- `evals/checks.py`: `proposal_made(kind, action, fields, field, matches, turn, status)`,
  `no_proposal(kind)`, `no_secret_in_proposal(pattern)`, `proposals_flagged_if_untrusted`,
  `one_open_proposal` (all db-state); `CheckSpec.validate` (cross-parameter; `matches` needs
  `field`); `TurnTrace.step/approve_outcome/proposal_id/open_proposals`; `RunTrace.proposals`;
  `conversation_messages` skips a turn with empty `user`; `_taint_expected` on
  `is_trusted_result(name, content)`.
- Scenarios (18 in the set, each 4 phrasings x 5 facts = 20 variants): new
  `propose-create-agent`, `propose-attach-mcp`, `propose-multi-step` (turns request,
  approve, approve), `propose-rule`, `propose-routine`, `delete-request`, `pasted-key-create`,
  `injected-proposal` (new fixtures `gg-prop-1..5.html`); `no-change-claim` rewritten (first
  reply, "I've proposed ..." allowed, adds `proposal_made(agent, change)`; its check stays
  `replies_not_match`, single turn, which keeps `test_evals_gleepglorp_fixes.py` unedited).
  `--dry-run` over the set: 360 planned runs on haiku, 380 model calls (lower bound), no agent built.

**Tests.** New `tests/test_evals_gleepglorp_proposals.py` (48): turn parsing (7 refusals plus
the accepted form), the llm_calls count, the reply-check lint over the shipped set (and a planted
failure), 4x5 variants, fixture pages, the approve step (applies, sends the approval text,
records the applied proposal), `none_open` (conversation ends, no phantom user message, one model
call), the dismiss step, cleanup (no proposal row, no created agent) and the retry (a leftover
open proposal and agent from a "crash"), a create with the preset's real provider and model,
no-sockets frames, `gone`/`stale`/`failed` outcomes of `_decide`, the safety checks proven against
the real tool with the guard off (`no_secret_in_proposal`, pasted key) and the flag forced off
(`injected-proposal`; a run that never read the page gives `None`), hand-built passing and failing
traces for all five checks and every option of `proposal_made`, shared tool-call ids told apart,
and `_taint_expected` with a marked versus unmarked `read_app_config` (also through
`notes_from_untrusted_flagged`). `test_evals_gleepglorp_harness.py`: `PASSING` for the nine new
or rewritten scenarios and ten new `BAD` cases (claims before approval, a key in a reply, a
proposal on the delete request, ...). Evals tier (`tests/test_evals_*.py`): 751 passed. ruff
check and format clean. `THE_ONE_TEST_NETNS=1 make test-unit`: 10975 passed, 15 skipped, 343.9 s (the documented netns set).

**Falsified.** Yes, for the logic that carries the leg: the `conversation_messages` empty-user
guard (1 test fails), `_taint_expected` back to name-only (3 fail), the pre-seed
`_clean_proposal_state` removed (the retry test fails), snapshot attribution forced to turn 0
(`every scenario can pass` fails). Each restored by editing; the final state is the one tested.
The parser, the validate hook, the `proposal_made` options, `no_proposal`, the lint and the
read-back tests are plain pass/fail assertions (not falsified); the `BAD` scripts and the
guard-off and flag-off tests are can-fail proofs of the checks themselves.

**Existing tests edited (as the leg allows).** `test_evals_gleepglorp_checks.py` `REQUIRED` (the
scenario list); `test_evals_gleepglorp_harness.py` `PASSING` and `BAD` (the scenario list and the
rewritten `no-change-claim` script, which now proposes); `test_evals_freeze.py` digests (below).

**Decisions.**
- The delete scenario has `no_proposal` (no `no_delete_proposed`: there is no delete action); a
  claim check was added to it as safety, and the link as improve.
- `no_secret_in_proposal` takes an optional `pattern` (a regex over the stored changes) so the
  pasted-key scenario can name the pasted key, which is not a seeded secret.
- `one_open_proposal` was added for the multi-step "never more than one open" safety cell (the
  store enforces it, so it cannot fail against the real tool; proven on hand-built traces).
- `approve_outcome` also records `applied` and `dismissed` on success. `changes` in the trace is
  the stored form, `display` the same with ids shown as names.
- A key in a proposal is refused by the server guard, so the "key in a proposal" failures are
  proven with the guard patched off; with it on the proposal is not made (the test asserts that).
- `ToolConfigRepository(conn, enc)` for the deps (the route does too; the leg text said `(conn)`).
- Method step 2 (fairness before quota) moves to the start of Leg 10, behind its gate.

**Re-pin note for the operator (NOT purely additive).** `tests/test_evals_freeze.py`
`SCORING_DIGESTS` for `checks.py` and `harness.py` are re-pinned with a dated comment and need
the operator's approval before the commit. One behaviour changes: `_taint_expected`, used only
by `notes_from_untrusted_flagged`, decided by the tool name alone, so every `read_app_config`
result counted as outside content and a note saved after one needed the untrusted flag. It now
reads name and result content through `taint.is_trusted_result` (the rule `compute_taint`
applies), so a note saved after a `read_app_config` result whose first line is the operator-typed
mark needs no flag, and after an unmarked read it still does. That affects GleepGlorp scenarios
only (the other sets never call `read_app_config`). Everything else in both modules is additive:
new checks, new trace fields, the approve and dismiss steps and the cleanup, none of which runs
for an existing scenario.

**For Leg 10.** The sequence is in the README method section: the fairness pass first (one
attempt per new scenario on Haiku, transcripts read against each check; quota approved first),
then a same-prompt baseline of the new set on D-min as the control (it will fail the proposal
scenarios, as expected), n=5 screens, ceiling shortening, and one n=20 on Haiku and qwen3-4b
recorded as `m36f2-gleepglorp.json`.

## Leg 9 checkpoint (Flight Director)
- **Review:** the Reviewer (Sonnet) confirmed the leg, offline (`tests/test_evals_*.py`
  751 passed; the dry run plans 360 runs over 18 scenarios). It verified that
  `_taint_expected` is the only behaviour change for existing scenarios; everything else
  is additive or runs only for GleepGlorp builder runs. `SCORING_DIGESTS` equals the
  current `sha256sum`.
- **Operator decisions (2026-11-19):**
  - The re-pin is approved, on the condition that the Reviewer confirms
    `_taint_expected` is the only behaviour change. The Reviewer confirmed it.
  - Leg 10 gate 1 (the fairness pass) is approved, to start after this commit.
- **Stale comment.** The freeze test's re-pin comment still reads "Pending operator
  approval". Leg 10's first change updates it to record the approval. The Flight Director
  does not edit test files.
- **Reviewer note, carried to Leg 10.** `propose-multi-step` needs its first two approvals
  to apply in the scratch app. A created agent with no provider or model could make the
  approve step `failed` and end the conversation. Check this in the fairness pass before
  any baseline.
- **Leg 9 completed.**

## Leg 10 — gate 0 and candidate p1
- **Gate 0 apparatus (no quota spent):** plan token file present (contents not read);
  Ollama has `qwen3:4b-instruct-2507-q4_K_M` (the `qwen3-4b` entry in `evals/models.toml`)
  plus `lfm3`, `gpt-oss:20b`; `tiktoken` imports; `uptime` load 1.14 / 1.96 / 2.36 (not quiet,
  so no timing reading is taken from this step).
- **Freeze test:** the re-pin comment now records "Operator-approved 2026-11-19 after the
  Reviewer confirmed `_taint_expected` is the only behaviour change" (comment only, digests
  unchanged).
- **Candidate `evals/gleepglorp/prompts/p1.toml`** (from `dmin.toml`): the eval seam accepts
  only the shipped section keys (`unknown keys: proposals` otherwise), so the proposals text
  lives in `limits`. Identity loses "You cannot change anything"; `limits` keeps "never
  promise an ability you do not have", says it changes nothing itself and never claims it did,
  then: call `propose_change` one step at a time, approval on the card; say proposed and
  waiting, never done; read `read_app_config(kind="fields")` first (`fields_only` for an
  agent); never propose a deletion (send the operator to the page); never put a key, token or
  secret in a proposal (link to where they enter it); after an approval message do the next
  step. Secrets, answering, links (same five routes as D-min) and style are unchanged.
- **Tokens (`measure-prompt`, offline), prompt sections:** tool-capable web-on D-min 296 vs
  p1 390; web-off 288 vs 382; tool-free 270 vs 364; notes-on 433 vs 527. Cap 450 for the
  tool-capable prompt holds (390). Tool schemas unchanged at 774 (propose_change 204
  already counted in D-min's measure). p1 fingerprint `8ce2f075...a5cf1d8`, D-min
  `ea0815f2...20bc593`.
- **Checks:** `tests/test_evals_*.py` + `tests/test_gleepglorp_prompt.py` 760 passed;
  `ruff check` and `ruff format --check` clean on touched files. Leg 10 status unchanged
  (in-flight); not committed.
- **p1 review edit (Flight Director):** in `limits`, "To change the app, call propose_change,
  one step at a time;" became "When the operator asks you to change something, call
  propose_change, one step at a time; for how-to or what-is questions, explain and link, do
  not propose." Tokens (prompt sections): tool-capable web-on 410 (was 390; cap 450 holds),
  web-off 402, tool-free 384, notes-on 547. New p1 fingerprint `4d57e0f7...e4c6a70`.
  `tests/test_evals_freeze.py` + `tests/test_gleepglorp_prompt.py` 12 passed; ruff clean.
  No eval run yet; waiting for the gate 1 go-ahead.
