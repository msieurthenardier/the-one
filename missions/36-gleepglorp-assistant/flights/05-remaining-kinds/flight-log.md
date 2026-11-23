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
