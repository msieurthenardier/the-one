# Flight Log: The remaining kinds

**Flight**: [The remaining kinds](flight.md)

## Summary

Planning (2026-11-23). No legs started.

---

## Reconnaissance Report

**Source:** the Mission 36 Flight 4 debrief (Technical, Documentation, Recommendations and Action
Items) and the open squawks on this flight's surfaces.
**Checked against:** `180c4c40` by two read-only survey agents, with FD spot checks
(2026-11-23). The operator confirmed the squawk scope. The retirement below is recorded and goes
to the operator with the spec.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Per-kind branches in `fill/store.py`, `kinds/__init__.py` and `shape.py` | confirmed-live, wider than listed | `fill/store.py:264/338/340`; `kinds/__init__.py:121-132/173-179`; `shape.py:142-161`; also `fill/tool.py:116`, `kinds/errors.py:88/99/182`, `proposals/store.py:322-345` (unknown kind falls to the routine branch) | Leg 1 (DD2) |
| `Kind` wide and optional-heavy | confirmed | `kinds/base.py:63-102`. `agent` also sets `resolve_target` (`agent.py:288`) | DD2: an `addressing` value, not a sub-protocol |
| Client per-kind duplication | confirmed-live; the Sensitive row has drifted (one copy) | `mcp-editor-fill.js` 349 lines and `provider-editor-fill.js` 317 lines, about 150 near-identical; follow note ×3; `onEvent`/`attach` identical | Leg 2 (DD4) |
| `provider-editor.js` at its ceiling | confirmed-live | 894 of the 895 allowance (`tests/test_area_module_size.py:24`) | Leg 2 (DD4) |
| `chat.js` +618 and `instance.js` +506 as Flight 4 growth | drifted | Both from Flight 3 (`f1607fc4`), untouched by `180c4c40` | No action; noted for the record |
| Kind registry contract in `agents.md` | partially-satisfied | `agents.md:3393`, `:3415`, `:3409` (id-then-name), `:1427/1440` (`warnings`/`normalize` modes); no checklist; `:3398` stale | Leg 1 (DD2) |
| Narrowed DD9 behaviours undocumented | **already-satisfied** | MCP type: `agents.md:1399` "`type` (`create_only`; never changed on an existing server…)". Provider: `agents.md:1426`, `SECURITY-MODEL.md:1413`, guide `model-providers.md:44` | **Retire** (recorded as done in the spec) |
| "Fill warnings are tool-result text" convention | partially-satisfied | One sentence at `agents.md:1427`; absent from `CLAUDE.md` Prompt evals and Project Conventions | Leg 1 (DD2) |
| Split the `gleepglorp` lane | confirmed-live | `scripts/run-tests.sh:71/205-209`; 157 tests, every test boots a server (`conftest.py:311-526`) | Leg 1 (DD13) |
| Budget the description pins | confirmed-live | `fill_form` 89/90 tokens (`test_gleepglorp_fill_tool.py:101`); `propose_change` 83/120 | DD11, Leg 5 |
| Fill vs proposal per kind | open, decided at planning | Date and time saves on choice (`date-time-page.js:9`) | DD5-DD8 |
| Squawk 0400 | confirmed-live | `mcp/service.py:410/417/469` | Leg 1 (operator: in) |
| Squawk 0382 | confirmed-live, location drifted | Now `mcp/service.py:309/313`, no longer `api.py` | Leg 1 (operator: in); the squawk's evidence path is updated at completion |
| Squawk 0401 | confirmed-live | `provider-editor-follow.js:64-68` | Leg 2 (operator: in) |
| Squawk 0402 | confirmed-live | `llm/provider_service.py:277` | Leg 1 (operator: in) |
| Squawks 0403, 0404, 0405 | confirmed-live, not this flight's surface | `agents.md:3054`; `CLAUDE.md:162-165`; `.flightops/agent-crews/flight-debrief.md:57` | Next turnaround. 0404's recipe is applied by hand in the HAT (DD15) |
| Prompt regression attribution, control, baseline | out of scope | Operator, 2026-11-23: alignment flight | Flight 6 |

---

## Leg Progress

### 01a-registry-hooks
**Status**: completed (Batch A checkpoint commit)
**Started**: 2026-11-23

#### Changes Made
- `Kind` (`kinds/base.py`): required `addressing` and `card_extras`; `fill_extras`, `target_noun`, `operator_only_message`, `action_refused`, `keyerror_is_gone`; `validate_kind` (run by `__post_init__`); `id_fill_extras` helper.
- Kinds: `card_extras` moved into agent/rule/routine; `fill_extras` for agent, mcp_server, provider (`_mcp_stale`, `_provider_stale`, `_clears_key` moved into the kind modules as `fill_stale` / `clears_key`); `NO_NOTES` moved to `kinds/agent.py` (re-exported by `fill/tool.py`); all five set `keyerror_is_gone=True`.
- `shape.py`: `FieldSpec.fill_refused`, `REFS` table (replaces `_kind_label` and the `ref ==` branch), `stored_get` / `stored_set`, `path` docstring.
- `kinds/__init__.py`: `target_args` reads `addressing` (incl. `"page"`), `describe` reads `REFS`, `_check_keys` uses `operator_only_message`, `normalize` has the action gate. `errors._is_gone` reads `keyerror_is_gone` / `addressing`. `fill_view` reads `fill_extras` only; `_card_extras` reduced to a dispatch; fill tool reads `fill_refused`.
- New `tests/test_gleepglorp_kind_hooks.py` (18 tests). Docs: agents.md checklist, rewritten members bullet, convention `reply-sentences-are-not-platform-prompt-text`; CLAUDE.md clause.

#### Verification
- AC8 capture (scratchpad `leg01a-capture/test_capture.py`, before.json 4116 lines, after.json 4120 lines): the diff is empty except four expected entries, `normalize` of rule and routine with `mode="fill"` (create and change), which the new action gate now refuses ("A rule can't be created by filling its form."); no caller reaches that (the fill tool refuses non-fillable kinds first). Real data dir listing unchanged.
- AC1 grep: no hits outside the five kind modules (the `'rule' if kind == 'rule'` in `target_args` became `{kind}`).
- Falsified by editing (then restored): action gate (3 tests fail), `operator_only_message` (1), `keyerror_is_gone` (1), `validate_kind` card_extras rule (2). `fill_refused`, path helpers: not falsified separately (fill_refused covered by the existing NO_NOTES test unedited).
- Full unit tier (`THE_ONE_TEST_NETNS=1 make test-unit`): 11916 passed, 15 skipped, 429 s. `gleepglorp` browser lane: 167 passed, 478 s. (A first lane start overlapped the unit run by mistake and was killed by its own PGID; both were then run alone.)
- Owning suites (`test_gleepglorp_*`, `test_evals_gleepglorp_*`, `test_evals_freeze`): 1332 passed, no test file edited. ruff check and format clean.

#### Notes
- **Design review** (Developer, Sonnet): approve with changes, 3 high and 6 medium findings,
  all applied:
  - the capture runs as a scratch pytest file on the existing fixtures, with `settings.data_dir`
    patched (it could otherwise have created a key file in the real data directory);
  - `NO_NOTES` moves to `kinds/agent.py` and is re-exported (an import cycle);
  - `validate_kind()` backs `__post_init__` and the registry test;
  - all four registry views are patched for the fake kinds;
  - the agent fill title keeps `kind.card(...)` (the `“None”` quirk);
  - a wider AC1 grep;
  - a declared `target_noun`;
  - an `id_fill_extras` helper.
- **No second review cycle:** the fixes are the reviewer's own points and change no design.
  Flight DD2's `fill_extras` text was updated to match.
- **FD acceptance of the AC8 diff:** the capture differed in four entries only. Each is
  `kinds.normalize` with `mode="fill"` for a rule or routine create or change, and now returns
  the new action gate's sentence. No production path reaches it: the fill tool refuses
  non-fillable kinds first, and `fill/tool.py` is the only `mode="fill"` caller. The FD accepts
  it as the gate working as designed.
- **Process slip (Developer, self-reported):** the `gleepglorp` lane was started while the unit
  tier was still running, against host policy. The Developer killed the lane by its own process
  group and re-ran both alone; the recorded numbers come from those clean runs.

### 01b-squawks-and-lanes
**Status**: completed (Batch A checkpoint commit)
**Started**: 2026-11-23

#### Verification
- `THE_ONE_TEST_NETNS=1 make test-unit`: 11930 passed, 15 skipped, rc=0 (494.85 s).
- Lanes, each alone (solo readings, no budget moved): `gleepglorp-chat` rc=0 wall 216 s,
  `gleepglorp-fill` rc=0 wall 125 s, `gleepglorp-kinds` rc=0 wall 129 s.
- `ruff check` and `ruff format --check` clean; `bash -n scripts/run-tests.sh` clean.

#### Notes
- **Design review** (Developer, Sonnet): approve with changes, 1 high and 4 medium findings, all
  applied.
  - **High:** two `tests/test_mcp_last_check.py` tests pin squawk 0382's defect. The FD
    authorized inverting them in this leg, under the skill's rule that tests pinning behaviour
    the design breaks are inverted in the same leg, and because the operator chose the fix.
  - **Medium:**
    - the proposal create path does pass an id;
    - 0402 is detected by catching `IntegrityError`, then `repo.get`, and only for a
      client-supplied id;
    - AC6 is tested by `fnmatch` over the pattern text;
    - the exact `args` normalisation.
  - **The reviewer's questions, answered by the FD:**
    - yes to the two inversions;
    - the 409 applies only when the id was client-supplied;
    - the service-level MCP race test is enough (the route is a thin call).
- **No second review cycle:** the fixes are scoped clarifications.
- **Designed after 1a landed;** 1a touched none of its files.
- **`[BLOCKED]` mid-implementation:** the Developer found a third test pinning squawk 0382's
  defect, `tests/test_mcp_service.py::test_only_the_named_fields_change_and_rows_merge_per_row`
  (an args change on a stdio server asserting `last_check` survives).
  - **The FD authorized inverting it** on the same grounds as the other two.
  - **Preferred edit:** the call changes `env` rather than `args`, so the untouched-key
    assertion stays.
  - **Fallback:** the one cache assertion changes, citing the squawk.
  - Three test inversions in total; a fourth would stop the leg again.
- **Implementation (Developer):**
  - 0400: `replace_mcp_source` runs on `update_in_txn` (sync `mutate` on copies). Race test
    `test_a_refresh_written_while_a_replace_waits_for_the_lock_survives`; falsified by feeding
    `mutate` a stale pre-read row.
  - 0382: `_prune_cache_on_server_change` treats a changed stdio `command` or `args` as a server
    change. New parametrized prune tests (put and change), env/sandbox keeps, absent-to-empty
    args; falsified (disabling the branch fails them and the inverted last-check test).
  - Three inversions: the two in `test_mcp_last_check.py`, and
    `test_only_the_named_fields_change_and_rows_merge_per_row`, done by the preferred edit (the
    call changes `env` only, and the `args` assertion reads `["-y", "pkg"]`).
  - 0402: `create_provider` catches `IntegrityError` and answers 409 for a client-supplied id.
    Three service tests, one route test; falsified by disabling the catch.
  - Lane split: three canonical lanes plus the `gleepglorp` alias, budgets 330/210/210 s,
    `tests/test_run_tests_lanes.py` rewritten (`test_gleepglorp_lanes_are_chat_fill_and_kinds`,
    the alias-not-scheduled test and the AC6 `fnmatch` test; the last two not falsified).
  - Docs: `CLAUDE.md` lane line, `the_one/agents.md` lanes, budget history and the stale bullets.
- **Tiered high:** a write-boundary race fix and a shared runner script.
- **Leg-design refinement:** `gleepglorp` stays as an alias of the three new lanes, so existing
  docs and commands keep working.

---

### 02-client-groundwork
**Status**: completed (Batch A checkpoint commit)
**Started**: 2026-11-23

#### Changes Made
- New `areas/shared/gleepglorp-fill-core.js` (`App.gleepglorpFill`: `module`, `libraryRoute`, `prepare`, `notes`, `writer`) and `gleepglorp-follow-core.js` (`App.gleepglorpFollow`: `buildNote`, `matches`, `listen`, `refetchThen`); `registerLibraryKind` in `gleepglorp-kinds.js`.
- `mcp-editor-fill.js` 349 -> 227 lines, `provider-editor-fill.js` 317 -> 182; MCP and provider follow modules, `agent-editor-follow.js` (note builder only) and `mcp-kinds.js` / `provider-kinds.js` rewritten on the helpers. MCP does not opt into the `skipIfUnchanged` short-circuit.
- Plan sign-in split to `provider-sign-in.js` (282 lines); `provider-editor.js` 894 -> 628. Token-expiry helpers stay.
- Squawk 0401: `blockSave` / `saveBlock` on the provider controller, set by the follow's dirty type-change branch, honoured in `performSave`; the rebase branch clears it (and drops the stale Cancel hook).
- `index.html` script order; `agents.md` paragraph + checklist pointer; squawk 0401 file `in-progress` with Corrective Action.
- Authorized existing-test edits: `tests/test_area_module_size.py` ALLOWANCE emptied; `tests/test_store_static.py` invalidation count over `provider-editor.js` + `provider-sign-in.js`. New: `tests/test_gleepglorp_client_helpers.py`; two 0401 browser tests beside the existing one (the only other browser-file change is the `_count` import).

#### Verification
- Static guards (ui_guards, token_definitions, design_tokens_a11y, ui_ownership, ui_control_inventory, store_static, area_module_size, client_helpers, + two provider readers): 512 passed.
- `make test-unit` (NETNS=1): 11934 passed, 15 skipped. ruff check and format clean.
- Lanes, each alone: gleepglorp-chat 82, gleepglorp-fill 45, gleepglorp-kinds 42 (41 + the 0401 test after a fix), mcp 105, mcp-connection 102, providers 144 (includes plan sign-in, plan token, provider editor), agents 186, agent-tabs 221: all passed. Solo walls 4:09, 4:32, 3:06, 6:02, 5:27, 5:47, 8:31, 8:10.
- 0401 tests falsified: yes (both fail with the `performSave` check removed, pass restored).

#### Notes
- The provider editor's error row has no `role=alert`, so the 0401 test locates it by `.ui-editor-error-row` and does not assert the role (no placement change).
- Design review** (Developer, Sonnet): approve with changes, 4 medium and 3 low findings, all
  applied.
  - **The FD's answers:**
    - MCP opts out of the `drawnSig` short-circuit (its rows re-render and drop the notes);
    - a later same-type rebase clears the 0401 Save block;
    - the error line is located by `role=alert`, with no new testid.
  - **Other fixes:**
    - the AC1 greps are scoped;
    - the testids stay extractable for the registry guard;
    - `buildNote(detail, text)` keeps its signature;
    - the token-expiry helpers stay in place.
  - **No second review cycle.**
- **Designed after Legs 1a and 1b landed**, and **tiered high** (shared client modules with
  existing consumers).
- **Leg-design decisions:**
  - the fill core takes a `routeIs(key)` from the kind, because Leg 4b's editors are under
    `#settings`;
  - the agent follow adopts only the shared note builder;
  - the Plan sign-in moves to `provider-sign-in.js`, which takes `provider-editor.js` under
    800 lines so its `ALLOWANCE` entry is removed;
  - squawk 0401's block uses the editor's existing save-error line;
  - one authorized test re-target: `test_store_static.py`'s invalidation count spans both
    provider files.

---

### Batch A checkpoint review (Legs 1a, 1b, 2)
**Status**: completed. The FD checked the one-line fix's diff (`errorRole: 'alert'`) and
accepted it without a second review cycle. Legs 1a, 1b and 2 and squawks 0400, 0382, 0402 and
0401 were marked `completed`, and the checkpoint commit followed. Its ref is recorded in the
next batch's notes.
- **A second crew-hygiene slip:** the fix Developer also left a self-matching wait loop
  (`pgrep -f "lane providers"`), PID 240218, and wrote its lane log to the home folder
  (`~/the-prov.out`) instead of the scratchpad. The FD stopped the task with `TaskStop`, which
  ended the loop, and removed the log after reading it (`providers` 144 passed). A third process
  seen at the same time belonged to another Claude session (another project's CI watch) and was
  left alone.
- **A11y fix (WCAG 4.1.3/3.3.1):** `provider-editor.js` now passes `errorRole: 'alert'` to `editorShell`, matching the eight other editors; one `role=alert` assertion added to the 0401 browser test (not falsified). No existing test pinned the role-less state. Results: `make test-unit` 11934 passed, 15 skipped; `providers` lane 144 passed; `gleepglorp-kinds` lane 42 passed; static guards 396 passed.
- **The squawk 0334 sweep, run by the FD** (Leg 2's Developer skipped it). Four browser files
  outside the eight lanes Leg 2 ran read the provider or MCP editor markup:
  - `test_flow_admin_tools_editor.py` and `test_flow_settings_visible_fixes.py`
    (`settings-tools`);
  - `test_flow_studio_knowledge_inventory.py` (`knowledge`);
  - `test_flow_chiplist_label_resolver.py` (`shared`).
- **The Reviewer was asked** to run those four, plus the whole `gleepglorp-kinds` lane, which Leg 2
  re-ran only partly after a late fix.
- **The crew:**
  - Reviewer: Sonnet (security-sensitive: MCP OAuth secrets, the provider create path, the
    gone translation);
  - Accessibility Reviewer: Sonnet, a static review, in parallel (Leg 2 changes UI).
- **Results:** both reviewers gave `[HANDOFF:confirmed]`.
  - **Reviewer runs:** `gleepglorp-kinds` 42 passed; the four sweep files 107 passed; 852
    unit and guard tests passed.
  - **The 0400 race test** would fail on the pre-fix code (reasoned from `git show`).
  - **The three inversions** keep their subjects.
  - **Leg 2's extra Cancel-hook drop** is judged correct and in scope.
- **The Accessibility Reviewer's non-blocking finding** (WCAG 4.1.3): the provider editor's
  error line has no `role="alert"`, a gap from before this flight. It matters more now that
  squawk 0401's refusal goes there. The FD took the one-line fix (`errorRole: 'alert'`, as the
  eight other editors do) in a fix pass before the commit.
- **Crew hygiene (anomaly, cosmetic).** The Reviewer left a wait loop,
  `while pgrep -f "run-tests.sh -m browser"`, which matches its own command line and so never
  ends. The FD found it by PID (100813, its command checked) and stopped the Reviewer task with
  `TaskStop`, which ended it. It is the same class of slip as Flight 4's self-matching wait loop.

---

### Batch A commit
- **`7627373a`** "flight/5: Batch A groundwork — kind hooks, squawks 0400/0382/0402/0401, lane
  split, client cores": 51 files. Not pushed; the push waits for the PR.

### 03a-library-kinds-server
**Status**: completed (Batch B checkpoint commit)
**Started**: 2026-11-23

#### FD notes on landing
- **A mid-leg nudge.** The Developer reported "waiting on background work" while no test
  process was running. The FD sent a status nudge, and the run went on to finish normally:
  12,069 unit tests passed, and six browser lanes or files passed, each run alone.
- **Carried to the Batch B review:**
  - **The leg text was wrong about `write_file`.** It is not a refused tool (the refused set is
    `send_to_platform_channel`, `continue`, `search_tools`, the notes and routine tools, and the
    self-configuration prefix). The tests use those instead.
  - **The knowledge-base operator-only refusal links `[Library](#library)`,** because
    `operator_only_message` receives no id.
  - **The end-to-end gone tests pass either way,** since `exists` withdraws first. Only the
    unit test covers `translate`'s gone mapping.
  - **The guide topics say GleepGlorp can fill these forms one leg ahead of the client seams**
    (Leg 3b). Batch B commits both together.

#### Changes Made
- New services `the_one/knowledge/service.py` and `the_one/secret_store/service.py`; thin
  routes in `api.py` and `secrets_api.py`; repository hooks (`KnowledgeBaseRepository.create`
  `on_commit`, `update_in_txn`; `SecretRepository.update` `precheck`/`on_commit`).
- Kinds `knowledge_base` and `secret` appended to `REGISTRY`; `typed_items` guard mode
  (`FieldSpec`, `outside.plan`/`check(base=)`, both tools pass `norm.base`, `describe` provenance);
  `errors.translate` learns the six new errors; ids in the two read views and the paths tables;
  `propose_change` description kind list; guide topics, `agents.md`, `SECURITY-MODEL.md`.
- New tests: `test_knowledge_service.py`, `test_secret_service.py`,
  `test_gleepglorp_kind_knowledge_base.py`, `test_gleepglorp_kind_secret.py`,
  `test_gleepglorp_typed_items.py`.
- Pins updated: the AC7 list, plus `test_gleepglorp_targets.py::test_other_kinds_get_no_id`
  (kinds with ids), `test_gleepglorp_proposals_shape.py` (`OPERATOR_ONLY_FIELDS` set, the
  `describe`/fields listings and "Valid names", and the unknown-kind probe `secret` -> `widget`).

#### Verification
- `make test-unit` (netns): 12069 passed, 15 skipped. Token-budget test ran (not skipped).
- Browser lanes alone: knowledge 65, library 122, agent-tabs 221, agents 186, routing 193,
  `test_flow_jump_to.py` (shared) 26: all passed.
- Falsified (edit, run, restore): the lost-update race, stale (kb and secret), typed_items
  fetched-only/no-anchor/removal, relaxed keys, operator-only `values`, refused tool, value-reader
  grep, `translate` gone mapping. Not falsified: the trusted-turn case (the guard simply does not run).
- Leg text slip: `write_file` is not a refused tool; tests use `send_to_platform_channel`,
  `continue`, `search_tools`.

#### Notes
- **Design review** (Developer, Sonnet): approve with changes, 3 high and 4 medium findings,
  all applied.
  - **High:**
    - AC1's race is reworded to the real lost update (a name-only PUT losing a concurrent
      description);
    - `kinds/errors.py` translation added (AC6b), without which a stale or gone target would
      have been a 500;
    - six more pins listed.
  - **Medium:**
    - no deps change is needed (the knowledge-base repository is built from `conn`; the secret
      repository comes from `deps.agent`);
    - `typed_items` placement, folding, and `sources.typed` only;
    - the secret service's imports avoid `interfaces`;
    - `allowed_tools` errors flattened to a `ShapeError`.
  - **The reviewer's questions, answered by the FD:**
    - `keyerror_is_gone=False` for both new kinds;
    - `name` and `description` stay free-text guarded;
    - ids go in `OPERATOR_PATHS` for list and detail.
  - **No second review cycle:** the fixes are the reviewer's own and change no design.
- **Batch B's first leg, tiered high** (write boundary; secret metadata is
  security-sensitive).
- **Leg-design decisions:**
  - the services go in `knowledge/service.py` and `secret_store/service.py`;
  - a secret fill create records metadata only;
  - `allowed_tools` is replaced whole and checked at normalize;
  - `typed_items` is a new guard mode, with `base` passed to `outside.check`.

---

### 03b-library-kinds-editors
**Status**: completed (Batch B checkpoint commit)
**Started**: 2026-11-23

#### FD notes on landing
- **Host clean on landing:** no pytest, `run-tests.sh` or uvicorn process left; no wait loop.
  Load was about 5.6 from outside this flight, so no lane reading here counts toward a budget.
- **Batch-end sweep (FD):** no selector, class or testid was removed in Batch B
  (`git diff 7627373a` over `static/`). The kind-list pins outside the legs' files
  (`test_evals_freeze.py`, `test_evals_gleepglorp_kinds.py`, `evals/harness.py`,
  `evals/scenario.py`) pin the eval side, which Leg 5 owns; the unit run covers them and passed.
- **Unverified after the fix:** the Developer re-ran only the two failing unit tests after its
  fix, not the whole unit tier. The Batch B Reviewer runs it.
- **Carried to the Batch B review:** the loose router-name assertion in the secret follow test;
  the `gleepglorp-kinds` lane at 71 tests (about 250 s on a loaded host, provisional budget
  210 s; Leg 7 re-measures).

#### Changes Made
- **Cores:** `App.gleepglorpFill.link` / `unlink` exposed (`notes()` now uses them);
  `App.gleepglorpFollow.fieldNotes(place, {testid})` is the per-field follow note;
  `registerLibraryKind` takes optional `beforeNavigate` / `afterNavigate`.
- **Editors:** `knowledge-create.js`, `knowledge-detail.js` and `secret-editor.js` gained a
  `saving` flag and idle waiters (flushed when a Save ends; a create's stays true) and return
  `controller`. New: `knowledge-editor-{controller,fill,follow}.js` (one controller for the
  create and edit forms), `secret-editor-{controller,fill,follow}.js`, `knowledge-kinds.js`,
  `secret-kinds.js` (script tags in `index.html`, kinds after `provider-kinds.js`).
- **Glue:** `knowledge-glue.js` and `secret-glue.js` keep `current`, `attach` the fill and
  follow modules; the secret glue's `followed(row)` is the follow path (not `onSaveSuccess`).
  `_focusKbCreate` consumes the one-shot suppression flag (`knowledgeEditorFill`), set by
  `knowledge-kinds.js` in `beforeNavigate` (create only) and cleared in `afterNavigate`.
- **Notes (DD14):** per-field `kb-filled-note` / `secret-filled-note` and follow notes
  `kb-approved-change-note` / `secret-approved-change-note`; the chips note "Filled by
  GleepGlorp: added X, Y."; the handoff note under the values table, linked to row 0's value
  input and redrawn from `recomputeDirty`. No placement beyond the DD14 list.
- **Docs:** `docs/ui-testid-registry.md` (4 rows), `the_one/agents.md` (client kinds registry /
  shared helpers), `guide/secrets.md` (one sentence: the form's first key follows the name).
- **Tests:** four new browser files (8 + 6 + 9 + 6 tests, `gleepglorp-kinds` lane by glob);
  `test_gleepglorp_client_helpers.py` (tuples + the client-order-equals-`kinds.KINDS` test);
  pins: `test_flow_gleepglorp_kinds.py` (script order, names x2, shape table) and
  `tests/test_run_tests_lanes.py` (`gleepglorp-kinds` file set, four files added).

#### Verification
- Guards (ui_guards, token_definitions, design_tokens_a11y, ui_ownership, area_module_size,
  store_static, guide, lanes, client_helpers): 543 passed; no file over 800 lines, no `ALLOWANCE`.
- `THE_ONE_TEST_NETNS=1 make test-unit`: first run 2 failed (guide `secrets` 609 words over the
  600 limit; the lanes test pin), both fixed and re-run green; nothing else failed (12068 passed).
- Lanes, each alone: `gleepglorp-kinds` 71, `gleepglorp-fill` 45, `gleepglorp-chat` 82,
  `knowledge` 65, `library` 122, `agents` 186, all passed.
- Falsified (each safety test failed with its fix removed, then restored): value input stays
  empty (create + value-ignored tests), masked rows and keys untouched, kept field (secret and
  KB), dirty follow (secret and KB), leave-guard Stay (secret, KB, KB suppression leak).
- The leg text said "you kept your unsaved edits"; the real Stay receipt reads "You chose to
  stay on the page you were editing.", and the tests pin that.
- Weak spot: the secret follow test's check that the router name followed a rename is loose
  (`page.title()` or body text); the list row and title assertions beside it are strict.

#### Notes
- **Design review** (Developer, Sonnet): approve with changes, 3 medium and 5 low findings, all
  applied. Each question was answered by the FD:
  - **The focus flag** lives on `knowledgeEditorFill` and is consumed by the glue's
    `_focusKbCreate` wrapper, not `library-pane`.
  - **The secret follow** uses a dedicated `followed(row)` glue method (`onSaveSuccess` would
    clear the leave guard's dirty mirror).
  - **Follow notes** are linked on `aria-describedby` through the core's exposed link helpers,
    and `clearNotes` removes both note families.
  - **The handoff note** with no row 0 or an empty key reads "Enter a key and value, then
    Create.", is redrawn on input and is linked to row 0's value input.
  - **Notes are event-only.**
- **No second review cycle.**
- **Designed after Leg 3a landed,** from a read-only survey of the knowledge-base and secret
  editors. None of the three editors had a controller, a `saving` flag or idle waiters, and the
  knowledge-base create form autofocuses on mount.
- **Tiered high:** secrets are in the editor, and the shared Studio modules change.
- **Leg-design decisions:**
  - one controller per editor family;
  - the core's `create` / `edit:{id}` keys;
  - a one-shot focus suppression through optional nav hooks in `registerLibraryKind`;
  - a failed KB detail load times out (accepted);
  - per-field follow notes (DD14).

---

### Batch B checkpoint review (Legs 3a, 3b)
**Status**: completed. Legs 3a and 3b were marked `completed`, and the checkpoint commit followed.
Its ref is recorded in the next batch's notes.
- **The crew:**
  - Reviewer: Sonnet (security-sensitive: secret metadata, the `typed_items` guard, the write
    services);
  - Accessibility Reviewer: Sonnet, a static review, in parallel (Leg 3b changes UI).
- **Accessibility Reviewer:** `[HANDOFF:confirmed]`, no blocking issue. Its one open point, whether
  the note icon is hidden from screen readers, the FD confirmed: `App.ui.icon` sets
  `aria-hidden="true"` and `focusable="false"` (`static/js/ui/core.js:229`). Non-blocking: the
  fill and follow notes are read on focus, not announced as they appear, which matches DD14.
- **Reviewer:** code and artifacts read in full, no blocking issue, but **no test run finished**.
  It stopped its own unit run after about a minute (its whole run lasted about 78 s) and so could
  not confirm. Its verdicts on the carried items:
  - `write_file`: not in any code or test. The leg text was corrected by the FD (two lines in
    `legs/03a-library-kinds-server.md`).
  - The knowledge-base operator-only link to `#library`: acceptable.
  - Gone coverage: adequate (`test_translate_maps_the_new_services_errors`).
  - Guide topics: match the client and server.
  - The loose router-name assertion: tighten it (done in the fix pass).
  - A nit: two statements on one line in `secret-editor-controller.js` (done).
- **Verification moved to the fix pass** (below), which ran the full unit tier, the guards and
  the four lanes one at a time. The FD read the fix diff and accepted it without a second review
  cycle: a tightened assertion (falsified) and a line split, no design change.
- **No stray processes.** The pytest process the Reviewer saw had exited by the time the FD
  checked. Load was 5.6-8 from other projects' sessions throughout.

Batch B fix pass (Reviewer found no blocking issue; two non-blocking items fixed):

- `tests/browser/test_flow_gleepglorp_follow_secret.py`: the vacuous "router's name followed" check now asserts `page.title()` ends with ` — Api renamed · GleepGlorp AI` (document.title is router-owned, set only through `App.router.sync(..., {name})`). Falsified: yes. With the `{ name: row.name }` option removed from `followed(row)` in `secret-glue.js`, the test failed (title stayed `Library — Secrets — Api access · GleepGlorp AI`); the option was restored by editing.
- `secret-editor-controller.js` `setField`: the two statements sharing a line are split onto their own lines.

Verification (netns, one at a time):

- `THE_ONE_TEST_NETNS=1 make test-unit`: 12070 passed, 15 skipped, 5017 deselected (8m11s).
- Static guards (test_ui_guards, test_token_definitions, test_design_tokens_a11y, test_ui_ownership, test_area_module_size): 421 passed.
- Browser lanes (wall time informational, host loaded): gleepglorp-kinds 71 passed (3m43s); gleepglorp-fill 45 passed (2m02s); knowledge 65 passed (5m06s); library 122 passed (6m21s). No failures, no flakes.

---

## Decisions

### Planning decisions (operator, 2026-11-23)
**Context**: Flight 5 planning interview.
**Decision**:
- **Squawks:** 0400, 0382, 0401 and 0402 ride this flight.
- **Evals:** new cells and one n=20 pass, with no baseline.
- **Tool configs:** ordinary fields only.
- **HAT:** one closes the flight.
**Impact**: DD1, DD7, DD12 and DD15.

---

## Deviations

*(none yet)*

---

## Anomalies

*(none yet)*

---

## Session Notes

### 2026-11-23 — Planning
- Flight 4 merged (PR #384, `180c4c40`). Branch `flight/05-remaining-kinds` created.
- Two read-only survey agents ran: one on the four kinds' surfaces, one on the debrief
  carry-forward items.

### Flight Director Notes
- Planned against `180c4c40`.
- **Architect cycle 1:** approve with changes, 2 high and 12 medium findings. All were applied:
  - **DD7 reworked.** Tool settings are stored per tool. The FD confirmed it at
    `builtins.py:228-237`. The first draft's shared-row resolution was a misreading of the
    `cross_configs` rule.
  - **DD14 mockups.** The operator chose four new placements on 2026-11-23.
  - **DD2:** the action gate; `translate` as a per-kind callable; `FieldSpec.path` kept and made
    load-bearing; the byte-identical pin widened.
  - **DD3:** the tool-config helpers and the impact pair move out of `api.py`; app metadata gets
    an in-transaction setter.
  - **DD6:** `allowed_tools` is relaxed for key-shape checks, and an added tool needs the
    operator's own text after outside content.
  - **DD8:** page-keyed targets and the `App.time` follow.
  - **DD11 and DD13:** provisional kind names, plus the missing pins.
  - **Legs:** Leg 1 split into 1a and 1b.
- **Architect cycle 2 (the last allowed):** approve with changes, 2 high and 7 medium findings.
  All were applied:
  - **The tool-config merge keeps stored secrets.** A proposal would otherwise have erased the
    search API keys (`api.py:922-938`).
  - **The Tools grid follow.** The operator chose "a quiet note" on 2026-11-23 (DD14, choice 5).
  - **Leftover shared-row text** was removed from DD1, DD11 and Leg 4a.
  - **DD6's added-tool rule** is now named as a new guard mode (`typed_items`, with `base`).
  - **DD3's side effects:**
    - the scheduler poke and the warm-up already delegate;
    - the monitoring hook stays on the route;
    - the rename carry gets a store factory.
  - **The secret service** goes in `secret_store/`.
  - **No `Kind.translate`.** The bare-`KeyError` clause is limited to the existing kinds.
  - **Re-exports** for the moved helpers.
  - **`operator_only_message`,** the refusal with a link to the Tools page.
  - **A fields-view attribute.**
  - **Smaller items:**
    - page keys are the route sections;
    - a zone-only change sets the mode;
    - secret names match ignoring case;
    - the seam-guard list and both lane expansions are named;
    - the turn-on and private-address warnings.
- **FD decisions taken without the operator** (these are the conservative readings, open to
  override):
  - `redirect_cap` is operator-only, as its own docstring says;
  - added `allowed_tools` names need tier-1 text after outside content;
  - the operator-only refusal links `#settings/tools`, which is on `p5d`'s route list.

### 2026-11-23 — Execution start (agentic-workflow)
- **Operator approval.** The operator approved the spec ("looks good, run agentic-workflow").
  The flight went `ready`, then `in-flight`.
- **Crew file:** `.flightops/agent-crews/leg-execution.md` was loaded, and its structure is
  valid.
- **Crew models:**
  - Developer: Sonnet.
  - Reviewer: Sonnet, because this flight touches secrets and tool security fields
    (security-sensitive per the crew file).
  - Accessibility Reviewer: spawned for the UI legs.
- **Batch mode** (crew file, the operator's standing preference for UI flights). Each batch ends
  with a review and a checkpoint commit:
  - **A:** 1a, 1b, 2 (groundwork);
  - **B:** 3a, 3b (Library kinds);
  - **C:** 4a, 4b (Settings kinds);
  - **D:** 5 (eval setup, committed before quota).

  Then 6 (quota round) and 7 (HAT and gate).
- **Leg 1a design, tiered high** (shared modules with existing consumers). Four refinements of
  DD2 were made at leg design, against the landed code; each is written up in the leg's Context:
  1. `stale` and `fill_extras` become one `fill_extras` hook.
  2. The fields-view attribute moves to Leg 4a, where its shape is known.
  3. `FieldSpec.path` becomes load-bearing through `stored_get` / `stored_set`.
  4. Bare `KeyError → gone` is gated by a declared `keyerror_is_gone` flag.
- Per the Flight 4 debrief (recommendation 4), dependent legs (1b, 2, 3b, 4b and 6) are
  designed after their predecessor lands.
