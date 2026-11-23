# Leg: 01a-kind-registry

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Move the GleepGlorp change shape onto a registry of kinds (`the_one/gleepglorp/kinds/`) and
replace the apply path's per-kind error chains with one `ApplyError` protocol. There is no
behaviour change for the three existing kinds (agent, rule, routine).

## Context

- **Flight DD2** (one registry of kinds) and **DD3** (`ApplyError`, `KindDeps`). This leg is a
  pure refactor. DD2's other parts land later:
  - schema v56, the shared status-row base, `target`, ids, the page-line route and the lane:
    Leg 1b;
  - client registries: Leg 2;
  - the `address_or_command` behaviour: Leg 3;
  - the new kinds: Legs 4-5.
- **Why first.** The Flight 2 and 3 debriefs asked for this split before a fourth kind.
  - `shape.py` is 620 lines and dispatches by if/else.
  - `apply.py` maps errors with isinstance chains.
- **Two leg-design decisions that refine the flight spec:**
  1. **No committed golden file for the "byte-identical" pin.** The user-global rule keeps
     golden or snapshot artifacts out of git, so the pin is:
     - the existing suites running with their assertions unedited (they already assert the
       `describe()` output, normalize results, card labels and summaries);
     - a one-off before/after comparison the Developer runs in a scratch directory outside
       the repo and reports (step 1).
  2. **`apply_proposal` accepts the existing `AgentWriteDeps` as well as `KindDeps`.** It wraps
     an `AgentWriteDeps` with `KindDeps.of(deps)`. This leaves `evals/harness.py`, which is
     digest-pinned by `tests/test_evals_freeze.py`, and the two test fixtures that build
     `AgentWriteDeps` untouched. It avoids the Flight 3 Leg 4 `[BLOCKED]` on the freeze digest.
     This supersedes flight DD3's "re-pinned in Leg 1a" note; the FD records it in the log.
- **`describe` moves into `kinds/`,** with a lazy re-export from `shape`. It reads the registry,
  so keeping it in `shape.py` would bring back the import cycle DD2 avoids.

## Inputs

- `main` at `9597b0f4`, plus the uncommitted Flight 4 planning artifacts.
- `the_one/gleepglorp/proposals/shape.py` (620 lines), `apply.py` (530), `continuation.py`,
  `store.py`, `tool.py`; `the_one/gleepglorp/fill/store.py`, `fill/tool.py`;
  `the_one/gleepglorp/view_fields.py`.

## Outputs

- A new package, `the_one/gleepglorp/kinds/`:
  - **`__init__.py`:**
    - the registry `REGISTRY: tuple[Kind, ...] = (agent.KIND, rule.KIND, routine.KIND)`, an
      explicit tuple with no registration on import;
    - `get(name)`;
    - the views `KINDS`, `SPECS`, `KIND_SUMMARIES` and `OPERATOR_ONLY_FIELDS` (the union of
      the kinds' `operator_only`, in today's order);
    - `FILLABLE` (the kinds with a non-empty `fillable`; `("agent",)` today);
    - `normalize` (dispatch by registry);
    - `describe` (moved).
  - **`base.py`:** the `Kind` dataclass (frozen):
    - `name`, `label`, `summary`, `fields`, `operator_only`, `fillable` and `actions`;
    - `normalize`, `exists`, `apply`, `summary_text`, `title` and `card_title`.

    Members for later legs (`resolve_target`, `editor_route`, `warnings`, `needs_secret`,
    `type_defaults`) are **not** added in this leg.
  - **`errors.py`:** `ApplyError(items, *, stale=None, gone=False)`.
  - **`deps.py`:** `KindDeps(agent: AgentWriteDeps)` with `KindDeps.of(deps)`, which accepts
    either type. Leg 4 adds repository fields.
  - **`agent.py`, `rule.py`, `routine.py`:** each kind's `FieldSpec` tuple, its normalize
    implementation (moved from `shape._agent`, `_agent_base`, `_rule` and `_routine`), its
    `exists`, its `apply` (moved from the `apply_proposal` branches and `_apply_routine`), its
    summary text, and the error translation into `ApplyError`.
- **`shape.py`** reduced to the primitives:
  - `FieldSpec`, now with `path: tuple[str, ...] | None = None` and
    `address_or_command: bool = False` (both unused in this leg);
  - `ShapeError`, `ACTIONS`, `RESERVED_AGENTS`, `_ECHO_MAX` and the value checks (`_q`,
    `_bad`, `_check_text`, `_check_int`, `_check_names`, `_check_schedule`, `_resolve_one`,
    `_ref_entries`, `_kind_label`);
  - `Normalized` and `dumps`;
  - a module `__getattr__` that lazily re-exports what moved (step 3).
- **What moves out of `shape.py`:**
  - `spec_for` and `_check_keys` move into `kinds/__init__.py`, because both read the spec
    table. `spec_for` is re-exported lazily from `shape`.
  - `_agent_base` becomes `kinds.agent.agent_base`, re-exported lazily from `shape` under its
    old name.
- **Every kind's `operator_only`.** `agent.KIND.operator_only` holds all six of today's
  `OPERATOR_ONLY_FIELDS`, in today's order. `rule` and `routine` have `()`.
- **`apply.py`:**
  - dispatches through `kinds.get(p.kind).apply(...)`, `.exists(...)` and `.summary_text(...)`;
  - folds `ApplyError` in one `except` branch;
  - re-raises any exception that is neither `ApplyError` nor `_AlreadyResolved`.
- **`continuation.proposal_title`, `fill/store.py` (`KINDS`, the title) and `fill/tool.py`'s
  `kind` enum** read the registry. Their output is unchanged.
- New tests (step 6); `the_one/agents.md` updated.

## Acceptance Criteria

- [ ] **AC1.** `the_one/gleepglorp/kinds/` exists with the modules listed in Outputs. `REGISTRY`
  is an explicit tuple of exactly `agent`, `rule` and `routine`, in that order.
- [ ] **AC2.** `shape.py` holds no kind's field tuple, normalize body or `describe`. Every
  attribute that tests or production code reach through `shape.` today still resolves,
  through the lazy re-export. `python -c "import the_one.gleepglorp.proposals.shape as s;
  [getattr(s, n) for n in (...)]"` over the step 3 list succeeds.
- [ ] **AC3.** Production code (`apply.py`, `proposals/tool.py`, `proposals/store.py`,
  `fill/tool.py`, `fill/store.py`, `view_fields.py`, `continuation.py`) imports kind-level
  names from `the_one.gleepglorp.kinds`, not through `shape`'s re-export. A grep for
  `shape\.(SPECS|KINDS|KIND_SUMMARIES|OPERATOR_ONLY_FIELDS|normalize|describe|AGENT_FIELDS|_agent_base)`
  under `the_one/` returns nothing.
- [ ] **AC4.** `failure_errors`, `_is_gone`, `_agent_or_rule_stale` and `_routine_stale` no
  longer exist in `apply.py`. Each kind's `apply` raises `ApplyError`, and `apply_proposal`
  folds it:
  - `stale` → `ProposalApplyResult("stale", stale=...)`, with today's row shape `{field, label,
    current, proposed}`;
  - `gone` → withdrawn;
  - `items` → `failed`.

  The order of checks is unchanged: already applied, then `_AlreadyResolved`, then stale, then
  gone, then failed.
  - **One translation function, not three.** The translation is a single
    `translate(exc, p, *, conn, zone)` in `kinds/errors.py` that every kind's `apply` calls.
    It reproduces today's `failure_errors` and `_is_gone` chain verbatim, for every kind:
    - `KeyError` → gone;
    - `AgentWriteError(404)` → gone, and other `AgentWriteError` → items;
    - `sqlite3.IntegrityError` → gone only for a rule or routine create;
    - the routine errors and `NameRuleError` → items for any kind.

    Anything else, including an agent-create `IntegrityError`, is returned unchanged, so it
    propagates.
  - **One small timing difference.** The stale rows (`display_values`, `await zone()`) are now
    built inside the kind, before `apply_proposal`'s "row already applied" re-read, instead of
    after it. Both are read-only, and the rows are discarded if the row was applied meanwhile,
    so this is not a behaviour change.
- [ ] **AC5.** An exception that is neither `ApplyError` nor `_AlreadyResolved` propagates out of
  `apply_proposal`, as today. A new test pins it.
- [ ] **AC6.** `apply_proposal` accepts an `AgentWriteDeps` (wrapped by `KindDeps.of`) or a
  `KindDeps`. `evals/harness.py`, `tests/test_evals_freeze.py` and the `AgentWriteDeps`
  fixtures in `test_gleepglorp_proposals_apply.py` and `test_gleepglorp_proposals_continuation.py`
  are unchanged (`git diff --stat` shows none of them).
- [ ] **AC7.** No behaviour change. These suites pass with their assertion lines unedited:
  - `tests/test_gleepglorp_proposals_*.py` and `tests/test_gleepglorp_fill_*.py`;
  - `tests/test_gleepglorp_views*.py` and `tests/test_gleepglorp_guide.py`;
  - `tests/test_evals_gleepglorp*.py` and `tests/test_evals_freeze.py`.

  The only permitted edits in existing tests are the three monkeypatch sites in step 5.
  - **`test_gleepglorp_proposals_apply.py:484` stays unedited.** It patches
    `proposal_apply.agent_service.change_agent`, which works because:
    - `apply.py` keeps `from the_one.agent import service as agent_service`, marked
      `# noqa: F401`, with a comment that tests patch the service through it;
    - `kinds/agent.py` calls `agent_service.change_agent(...)` and
      `agent_service.create_agent(...)` through the module attribute, never through a `from`
      import of the function.

    Both names refer to the same module object, so the patch reaches the kind.
- [ ] **AC8.** The before/after comparison (step 1) shows identical output for every item it
  captures. The Developer reports the command and the result. Nothing from it is committed.
- [ ] **AC9.** New tests (step 6) pass, and each safety-relevant one is reported as falsified
  (yes or no).
- [ ] **AC10.** `THE_ONE_TEST_NETNS=1 make test-unit` passes, with the expected 15 skips.
  `ruff check` and `ruff format --check` are clean on the touched paths.
- [ ] **AC11.** `the_one/agents.md` gains a "GleepGlorp kinds registry (M36 F4)" section:
  - the layout and the `Kind` members present now;
  - "explicit tuple, no import-time registration";
  - the `ApplyError` protocol;
  - `KindDeps.of`;
  - "a service never imports `gleepglorp`".

  Every existing agents.md reference to `shape.py` symbols that moved is repointed.

## Verification Steps

- AC1-AC3: list the package. Run the AC2 one-liner and the AC3 grep.
- AC4-AC5: `grep -n 'def failure_errors\|def _is_gone\|_agent_or_rule_stale\|_routine_stale'
  the_one/gleepglorp/proposals/apply.py` returns nothing. Run the new tests.
- AC6: `git diff --stat -- evals/ tests/test_evals_freeze.py tests/test_gleepglorp_proposals_apply.py tests/test_gleepglorp_proposals_continuation.py`
  shows no change to those files' fixtures. The monkeypatch edits are not in these two files.
- AC7: `git diff -U0 -- tests/` shows only the three patch-site edits and the new test files.
  Run the listed suites:
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_gleepglorp_proposals_*.py tests/test_gleepglorp_fill_*.py tests/test_gleepglorp_views*.py tests/test_gleepglorp_guide.py tests/test_evals_gleepglorp*.py tests/test_evals_freeze.py -x --timeout 60`.
- AC8: the step 1 comparison output.
- AC10: `THE_ONE_TEST_NETNS=1 make test-unit` and `ruff check the_one/ tests/` and
  `ruff format --check the_one/ tests/`.

## Implementation Guidance

1. **Capture "before" first, before editing anything.**
   - Write a small script in the session scratchpad (outside the repo, never under `tests/`).
     It imports the current `shape` and dumps JSON of:
     - `describe()`, and `describe(k)` for each kind;
     - `KINDS`, `ACTIONS` and `KIND_SUMMARIES`;
     - `OPERATOR_ONLY_FIELDS`;
     - every `FieldSpec` as `dataclasses.asdict`, without the two new attributes;
     - `continuation.proposal_title` for a create and a change of each kind (fake `Proposal`
       rows);
     - `fill_form`'s `parameters`;
     - one agent stale payload and one routine stale payload, through real services on a
       template database;
     - the `result` dict from a routine create and a routine change.
   - Save it to the scratchpad. After step 7, run the same script against the new code (the
     same attribute access through `shape`, plus `kinds`) and diff.
   - This is AC8. The script is a tool, not a test, so it is not committed. It writes only to
     the scratchpad.

2. **Create `kinds/`.**
   - Move the field tuples (`AGENT_FIELDS`, `RULE_FIELDS`, `ROUTINE_FIELDS`, `SCHEDULE_EXAMPLE`,
     `_schedule_hint`) into the kind modules, and the normalize bodies (`_agent`, `_agent_base`,
     `_existing_agent`, `_not_reserved`, `_rule`, `_routine`) with them.
   - The kind modules import the primitives from `shape`. `shape` imports nothing from `kinds`
     at module level, which keeps the dependency one way.
   - `normalize(kind, action, target, changes, *, conn, now, zone, enc?)` keeps today's exact
     signature and error sentences. An unknown kind gives the same `ShapeError` text
     `_check_keys` or `normalize` gives today. Read the current unknown-kind sentence and keep
     it.
   - `describe` moves verbatim and reads `REGISTRY`.

3. **The lazy re-export in `shape.py`.**
   - A module-level `__getattr__(name)` maps every moved public or semi-private name to
     `kinds` or the kind module: `normalize`, `describe`, `KINDS`, `SPECS`, `KIND_SUMMARIES`,
     `OPERATOR_ONLY_FIELDS`, `AGENT_FIELDS`, `RULE_FIELDS`, `ROUTINE_FIELDS`,
     `SCHEDULE_EXAMPLE`, `_agent_base`, `routine_service`, `comparable_value` and `_ECHO_MAX`
     (if moved).
   - **Derive the final list by grep** (`grep -rhoE '\bshape\.[A-Za-z_]+' the_one tests evals
     scripts | sort -u`), and also grep for `setattr(shape, "...")`. Today that list is:
     `normalize`, `describe`, `SPECS`, `AGENT_FIELDS`, `ShapeError`, `OPERATOR_ONLY_FIELDS`,
     `_ECHO_MAX`, `SCHEDULE_EXAMPLE`, `KINDS`, `ACTIONS`, `routine_service`, `_agent_base`,
     `spec_for`, and `comparable_value` (patched by name).
   - Names that stay in `shape` need no entry: `ShapeError`, `ACTIONS` and `_ECHO_MAX`. If
     `shape` still imports `routine_service` for `_check_schedule`, it stays a real attribute,
     marked as a re-export so ruff F401 does not flag it.
   - Unknown names raise `AttributeError` as normal.
   - **Why step 5's retargets are required.** `monkeypatch.setattr(shape, "<moved name>", …)`
     would succeed through `__getattr__`, but it would set a real attribute on `shape`, and the
     undo would leave that attribute in place for the rest of the session, shadowing the lazy
     re-export.
   - **`kinds.get(name)` and `describe(name)` raise `KeyError`** for an unknown kind, as
     `SPECS[kind]` does today.

4. **`apply.py`.**
   - `apply_proposal(conn, deps, proposal_id, *, override, now, zone, continue_chat=True)` keeps
     its signature. Its first line is `deps = KindDeps.of(deps)`.
   - Dispatch: `kind = kinds.get(p.kind)`.
     - `_target_exists` → `await kind.exists(conn, deps, p)`.
     - The summary → `kind.summary_text(p, routine_name, sentence)`, the same dict
       `_summary` returns today. Move the per-kind wording; keep the `{"summary", "agent",
       "fields"}` keys and the routine extras.
     - The write → `await kind.apply(conn, deps, p, changes=..., base=..., override=..., now=...,
       zone=..., mark=..., result=...)`. Pass whatever today's branches use. The routine kind
       needs `now`, `zone`, `result` and `routine_name`, so let `apply` return the routine name
       (or `None`).
   - **Errors.** Inside each kind's `apply`, catch that kind's service errors and raise
     `ApplyError`. The mapping today:
     - `AgentWriteError(status=404)` → `gone`; other `AgentWriteError` → `items`;
     - `AgentStaleError` → `stale` rows built as `_agent_or_rule_stale` does (it needs `conn`
       for `display_values`);
     - `RoutineFieldError`, `RoutineScheduleError`, `RoutineLimitError`, `RoutineNameTaken`,
       `NameRuleError` → `items` exactly as `failure_errors` does;
     - `KeyError` → `gone`;
     - `sqlite3.IntegrityError` on a rule or routine create → `gone`;
     - routine `ProposalStaleError` → `stale` rows as `_routine_stale` does.
   - **Do not catch `_AlreadyResolved`** in a kind: let it propagate.
   - In `apply_proposal`'s `except` block, after the "row already applied" and
     `_AlreadyResolved` checks:

     ```
     if isinstance(exc, ApplyError):
         if exc.stale is not None: return ProposalApplyResult("stale", stale=exc.stale)
         if exc.gone: return await _withdraw_gone(...)
         ...mark failed with exc.items...
     raise
     ```
   - `config_changed`'s broadcast payload and `continuation.on_approved` are unchanged.

5. **The three monkeypatch sites** (the only edits to existing test lines):
   - `tests/test_gleepglorp_proposals_shape.py:474` patches `shape.comparable_value`. Re-target
     it to the module whose code now calls `comparable_value` (`kinds.agent` or wherever it is
     called).
   - `tests/test_gleepglorp_fill_tool.py:197` and `tests/test_gleepglorp_proposals_tool.py:162`
     patch `shape.normalize`. The tools now call `kinds.normalize`, so re-target to the name
     the tool module actually looks up.
     - Both tools must import the module (`from the_one.gleepglorp import kinds`) and call
       `kinds.normalize(...)` through it.
     - The retarget is then `monkeypatch.setattr(kinds, "normalize", boom)`.
     - A `from ...kinds import normalize` in a tool would make the patch a silent no-op.
   - The `comparable_value` site works only if `kinds/agent.py` imports
     `from the_one.agent.service import comparable_value` and calls it as a module global, in
     both `agent_base` and normalize. Then retarget the patch to `kinds.agent`.
   - Keep each test's name and assertions.

6. **New tests:**
   - **`tests/test_gleepglorp_kinds.py`:**
     - `REGISTRY` is a tuple of exactly the three kinds, in order;
     - `kinds.get` refuses an unknown name;
     - every kind's `operator_only` names appear in no kind's fields (the "never in a spec"
       test, now per kind), and `OPERATOR_ONLY_FIELDS` equals the union in today's order;
     - `FILLABLE == ("agent",)`;
     - `shape` re-exports every name on the step 3 grep list (a parametrized `getattr`), and
       no moved name is a real attribute (`name not in shape.__dict__`);
     - `kinds` does not import from `the_one.interfaces`. Add `gleepglorp/kinds/*.py` to the
       existing seam-import guard's parametrization,
       `test_the_seam_modules_do_not_import_interfaces`
       (`tests/test_gleepglorp_proposals_continuation.py:279`). This adds a parameter only; the
       assertion is unchanged.
   - **`tests/test_gleepglorp_apply_error.py`** (or added to `test_gleepglorp_proposals_apply.py`
     as new test functions only):
     - an `ApplyError(stale=[...])` from a kind's `apply` gives `stale`, with the rows passed
       through;
     - `ApplyError(gone=True)` withdraws;
     - `ApplyError(items)` marks failed with those items;
     - a `RuntimeError` from a kind's `apply` propagates (AC5; falsify it by catching
       `Exception` temporarily and confirming the test fails);
     - `apply_proposal` accepts a bare `AgentWriteDeps` and a `KindDeps`.

     Use a stub `Kind` substituted in the registry for the duration of a test (monkeypatch
     `kinds.get`), so the folding is tested independently of any real service. A stub raising
     `_AlreadyResolved` must pass through to `apply_proposal`'s existing handling.
   - **`translate` with real services:**
     - a rule create against a missing agent (`IntegrityError`) → gone;
     - a `KeyError` from a routine change → gone;
     - an `IntegrityError` raised from the agent kind → propagates.

7. **Docs.** The `the_one/agents.md` section (AC11).
   - Grep `the_one/agents.md` and `SECURITY-MODEL.md` for `shape.py`, `shape._agent`,
     `failure_errors`, `_is_gone` and `SPECS`, and repoint them.
   - The "Proposal lifecycle (M36 F2)" section names the error mapping: update it to the
     `ApplyError` wording.

8. **Run** the AC7 suites, then the AC10 commands, then the step 1 comparison.

## Edge Cases

- **Import cycle.** `kinds/agent.py` needs `view_core` (`_agent_names`, `_names`,
  `_surface_owners`), `naming`, `agent.service.comparable_value`, `routines.*`. `shape.py`
  needs `view_core` only if a primitive uses it (`_ref_entries` does). Keep `shape` free of any
  `kinds` import at module level; the lazy `__getattr__` imports inside the function.
- **`from the_one.gleepglorp.proposals.shape import X`** (a `from` import of a moved name)
  works through module `__getattr__` in Python 3.7+. Verify with the AC2 one-liner, including
  `from ... import ShapeError`, which stays.
- **`describe(kind)` for an unknown kind** raises today (`KeyError` from `SPECS[kind]`), so keep
  that behaviour. `view_fields.py` relies on it, so read how it guards.
- **Routine `apply` returns the name** used in `result["routine"]`. Keep the exact mutation
  order of `result` (`_apply_routine` sets `result["routine"]` before the write).
- **`_HIDDEN_FIELDS`, `OPEN_STATUSES`, `_mark_applied` and `_MarkRunner`** stay in `apply.py`,
  or move to a neutral spot if a kind module needs them. Kinds receive `mark` and the runner,
  and do not import `apply.py`.
- **`fill/tool.py` enum.** `"enum": list(kinds.FILLABLE)` must equal `["agent"]`.
  `tests/test_gleepglorp_fill_tool.py:79` pins it, and it must pass unedited.

## Files Affected

- `the_one/gleepglorp/kinds/__init__.py`, `base.py`, `errors.py`, `deps.py`, `agent.py`,
  `rule.py`, `routine.py`: new.
- `the_one/gleepglorp/proposals/shape.py`: reduced, with the lazy re-export.
- `the_one/gleepglorp/proposals/apply.py`: registry dispatch, `ApplyError` folding.
- `the_one/gleepglorp/proposals/continuation.py`, `proposals/store.py`, `proposals/tool.py`:
  imports and title via the registry.
- `the_one/gleepglorp/fill/store.py`, `fill/tool.py`, `the_one/gleepglorp/view_fields.py`:
  imports via `kinds`.
- `tests/test_gleepglorp_kinds.py`, `tests/test_gleepglorp_apply_error.py`: new.
- `tests/test_gleepglorp_proposals_shape.py:474`, `tests/test_gleepglorp_fill_tool.py:197`,
  `tests/test_gleepglorp_proposals_tool.py:162`: patch target only.
- `the_one/agents.md`: new section and repointed references.
- **Registries and pins checked** (none needs a change in this leg):
  - `tests/test_gleepglorp_fill_tool.py:79` (enum `["agent"]`);
  - `tests/test_gleepglorp_proposals_tool.py:75/91` (the description, unchanged);
  - `tests/test_evals_freeze.py` (no evals file touched);
  - the tool allowlist (no tool added).

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** All changes are folded in above:
- **Kept unedited:** `test_gleepglorp_proposals_apply.py:484`, through `apply.py`'s
  `agent_service` re-import.
- **Moved:** `spec_for` and `_check_keys` into `kinds`.
- **Translation:** one shared `translate`.
- **Noted:** the stale-row timing.
- **Raising `KeyError`:** unknown kinds.
- **The six fields:** `operator_only` for agent.
- **Hazard:** monkeypatching `shape`, with the `__dict__` assertion added.
- **Tools:** call `kinds.normalize` through the module.
- **The re-export list:** corrected.
- **AC8:** captures more.
- **The seam guard:** parametrized for `kinds`.

There was no second cycle: these were clarifications, not new design.

## Citation Audit

Verified against the working tree at `9597b0f4` (plus planning artifacts):

- `proposals/shape.py:35` `KINDS`, `:36` `ACTIONS`, `:37` `RESERVED_AGENTS`; `FieldSpec` `:50`
  (frozen dataclass: `name`, `type`, `label`, `stored`, `hint`, `min`, `max`,
  `create_required`, `create_only`, `ref`); `SPECS`, `KIND_SUMMARIES`, `OPERATOR_ONLY_FIELDS`;
  `Normalized` `:212`; `spec_for` `:226`; `describe` `:230`; `normalize` `:395` — verified.
- `proposals/shape.py` imports `comparable_value` (`agent.service`), `view_core._agent_names`,
  `_names`, `_surface_owners`, and `routines.service as routine_service` — verified (head of
  file).
- `proposals/apply.py:137` `failure_errors`, `:155` `_is_gone`, `:212`
  `_agent_or_rule_stale`, `:229` `_routine_stale`, `:254` `_target_exists`, `:296`
  `apply_proposal(conn, deps: AgentWriteDeps, proposal_id, *, override, now, zone,
  continue_chat=True)`; the `except` block ends in `if errors is None: raise` — verified.
- `proposals/apply.py:427` `_apply_routine` sets `result["routine"]` before
  `update_routine` — verified.
- `proposals/continuation.py:38` `proposal_title(p)` — verified.
- `fill/store.py:244` lazy `from ...proposals import shape`; `shape.SPECS` and
  `shape._agent_base` used in `fill_view` — verified.
- `proposals/store.py:365` lazy `shape` import, `labels` from `shape.SPECS` — verified.
- Monkeypatch sites: `test_gleepglorp_proposals_shape.py:474` (`comparable_value`),
  `test_gleepglorp_fill_tool.py:197` and `test_gleepglorp_proposals_tool.py:162`
  (`normalize`) — verified.
- `AgentWriteDeps` constructed in `evals/harness.py:627`, `tests/test_gleepglorp_proposals_apply.py:40`,
  `tests/test_gleepglorp_proposals_continuation.py:233`, `tests/test_agent_service.py:57`,
  `interfaces/web/api.py:275` — verified (none needs a change, by AC6).
