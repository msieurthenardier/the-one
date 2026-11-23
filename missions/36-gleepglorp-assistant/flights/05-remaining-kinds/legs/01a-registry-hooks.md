# Leg: 01a-registry-hooks

**Status**: completed
**Flight**: [The remaining kinds](../flight.md)

## Objective

Every place outside the kind modules that branches on a kind's name moves into a declared `Kind`
member or hook. A new kind then needs no edit outside its own module and one registry line. The
five existing kinds behave byte-identically, and `the_one/agents.md` gains the "Adding a kind"
checklist.

## Context

- **Flight DD2** (the registry's gaps), **DD13** (pins) and the Flight 4 debrief's
  recommendation 2.
- **What the flight recon found:** eight branch sites, not three:
  - `fill/store.py:264/314-341`;
  - `kinds/__init__.py:121-132/173-179`;
  - `proposals/shape.py:142-161`;
  - `proposals/store.py:322-361`;
  - `kinds/errors.py:88-99`;
  - `fill/tool.py:116`.

  The worst is `proposals/store.py:340`. Its `else` treats any kind without `card_extras` as a
  routine.
- **The pin pattern follows Flight 4 Leg 1a:**
  - the owning suites pass with their assertion lines unedited;
  - a one-off before/after capture runs in the session scratchpad (never committed, by the
    user-global no-golden-files rule), and its diff is reported.
- **Leg-design refinements of DD2.** The FD records each in the flight log.
  1. **DD2's `stale` and `fill_extras` become one hook,** `fill_extras(conn, fill, labels) ->
     {title, target_gone, stale, clears_key}`.
     - Today `fill_view` derives those four from three sources: the agent inline block, the
       kind's `card_extras` plus the per-kind stale functions, and `_clears_key`.
     - One hook per fillable kind removes every kind test from `fill_view`.
     - **Required for every kind with a non-empty `fillable`.** Rule and routine are not
       fillable and leave it `None`.
  2. **The fields-view attribute for per-tool and per-page fields (DD2, DD11) moves to Leg 4a.**
     Its shape depends on how Leg 4a computes a tool's settable set, and adding it now would be
     guessing (debrief recommendation 4: design against landed code).
  3. **`FieldSpec.path` becomes load-bearing through two helpers.** `stored_get(spec, obj)` and
     `stored_set(spec, obj, value)` go in `shape.py`, with unit tests.
     - The existing kinds adopt them only where that removes code and keeps output identical.
     - Their real consumers are Legs 3a and 4a. The stale docstring is rewritten.
  4. **The bare-`KeyError → gone` clause** is limited by a declared `Kind` flag,
     `keyerror_is_gone: bool = False`. The five existing kinds set it `True`. A new kind that
     leaves the default gets a `KeyError` re-raised, not a silent withdrawal.
- **The rest of DD2 lands as written:**
  - `addressing`;
  - the `REFS` table;
  - required `card_extras`;
  - `errors.py:99` reading `addressing`;
  - the `fill_refused` field attribute;
  - `operator_only_message`;
  - the mode-aware action gate.

## Inputs

- Branch `flight/05-remaining-kinds` at `180c4c40` plus the planning artifacts (uncommitted:
  `missions/36-…/mission.md`, `flights/05-remaining-kinds/`).
- The five kinds: `the_one/gleepglorp/kinds/{agent,rule,routine,mcp_server,provider}.py`, with
  `base.py` (the `Kind` dataclass) and `errors.py`.

## Outputs

- **`kinds/base.py` `Kind`:**
  - a required `addressing` member, one of `"agent"`, `"agent-owned"`, `"id"` or `"page"`;
  - required `card_extras` (a callable, never `None`);
  - `fill_extras`, required for every fillable kind and `None` for rule and routine
    (`validate_kind`);
  - `target_noun`, required for `"id"` kinds;
  - optional `operator_only_message` and `action_refused`;
  - `keyerror_is_gone: bool = False`.
- **`proposals/shape.py`:**
  - `FieldSpec.fill_refused: str = ""`;
  - the `REFS` table, replacing `_kind_label` and the `ref ==` branch in `_ref_entries`;
  - `stored_get` and `stored_set`;
  - the `path` docstring rewritten.
- **`kinds/{agent,rule,routine}.py`:** each gains its `card_extras`, moved from
  `proposals/store.py::_card_extras`; `agent.py` also gains `fill_extras`.
- **`kinds/{mcp_server,provider}.py`:** each gains `fill_extras`, built from today's `fill_view`
  branch, `_mcp_stale` / `_provider_stale` (`fill/store.py`) and `_clears_key`.
- **`kinds/__init__.py`:**
  - `target_args` reads `addressing`;
  - `describe` reads `REFS`;
  - `_check_keys` uses `operator_only_message` when set;
  - `normalize` gains the action gate.
- **`proposals/store.py::_card_extras`:** reduced to `kinds.get(p.kind).card_extras(conn, p)`.
- **`fill/store.py::fill_view`:** reads `kind.fill_extras` only. `_mcp_stale`, `_provider_stale`
  and `_clears_key` move out.
- **`kinds/errors.py`:** `_is_gone` reads `keyerror_is_gone` and `addressing`. There is no other
  kind literal.
- **`fill/tool.py`:** the notes refusal reads `fill_refused`. `agent.py`'s `notes_enabled` spec
  carries the `NO_NOTES` sentence.
- **Tests:** a new `tests/test_gleepglorp_kind_hooks.py` (step 8).
- **`the_one/agents.md`:**
  - the "Adding a kind: the checklist" subsection;
  - the stale "`Kind` members present now" bullet rewritten;
  - the prompt-text boundary added to Project Conventions.
- **`CLAUDE.md`:** the prompt-text boundary, as one clause in the "Prompt evals" rule.

## Acceptance Criteria

- [ ] **AC1. No kind-name branch outside the kind modules.** The grep below over
  `the_one/gleepglorp/` (excluding `kinds/{agent,rule,routine,mcp_server,provider}.py`)
  returns no branch that tests a specific kind name:

  ```
  grep -rnE "(kind|\.kind|name) *(==|!=|in) *[\(\[{]?[\"'](agent|rule|routine|mcp_server|provider)[\"']" the_one/gleepglorp
  grep -rnE "ref *(==|!=|in) *[\(\[{]?[\"']" the_one/gleepglorp
  ```

  Today's hits, which must all be gone:
  - `proposals/store.py:327/331`;
  - `shape.py:159/161`;
  - `errors.py:99`;
  - `fill/store.py:264/338/340`;
  - `kinds/__init__.py:121/126/130/132/173`;
  - `fill/tool.py:116`.

  `kinds/agent.py:176` (`f.ref == "tool"`) is inside an excluded file and stays.

  - **Allowed hits:** the `REGISTRY` tuple, imports, docstrings, and `"agent"` used as a field
    or parameter name rather than a kind test.
  - **Report:** the grep output and each hit's justification.
- [ ] **AC2. The `Kind` members exist with the stated defaults.** A registry test in
  `test_gleepglorp_kind_hooks.py` fails when any of these holds for a kind in `REGISTRY`:
  - its `card_extras` is `None`;
  - it is fillable with no `fill_extras`;
  - its `addressing` is not one of the four values.

  The test is falsified by building a `dataclasses.replace(...)` kind that breaks each rule.
- [ ] **AC3. The action gate.** `kinds.normalize`, right after the `ACTIONS` check and before
  `_check_keys`:
  - refuses an action not in `actions` (`mode="propose"`) or not in `fillable` (`mode="fill"`);
  - uses `action_refused(action, mode)` when set, else one generic sentence.

  **No change for the existing kinds:**
  - agent, MCP server and provider have both tuples equal to `("create", "change")`;
  - rule and routine are never normalized with `mode="fill"`. The fill tool refuses them first,
    and the Developer greps every `mode="fill"` caller, including `evals/`.

  A test with a fake kind whose `actions` is `("change",)` shows both modes, and it is
  falsified.
- [ ] **AC4. `operator_only_message`.** When a kind sets it and `changes` names any of its
  `operator_only` fields, `_check_keys` raises `operator_only_message(names)` instead of the
  generic sentence. No existing kind sets it. A test with a fake kind covers it, and it is
  falsified.
- [ ] **AC5. `fill_refused`.** The fill tool returns the first named field's `fill_refused`
  sentence as its result, at the same point in the order as today's notes check. `fill_form`
  with `notes_enabled` still returns exactly `NO_NOTES`, and the existing test passes unedited.
- [ ] **AC6. `keyerror_is_gone`.**
  - **Existing kinds:** `errors._is_gone` returns `True` for a bare `KeyError` only when the
    proposal's kind sets `keyerror_is_gone`. All five existing kinds set it, so their behaviour
    is unchanged.
  - **A new kind:** a fake kind without the flag gets the `KeyError` re-raised by `translate`.
    The test is falsified.
  - **The foreign-key check:** `p.kind in ("rule", "routine")` (`errors.py:99`) reads
    `addressing == "agent-owned"`.
- [ ] **AC7. `stored_get` / `stored_set`.**
  - `stored_get(spec, obj)` reads `obj[spec.stored]` when `path` is `None`, else walks `path`.
  - `stored_set(spec, obj, value)` writes at the same place and returns a new dict, leaving the
    input unmutated.
  - `stored_set` shallow-copies only the levels it walks.
  - Unit tests cover the flat case, a nested path and a missing intermediate key. They also show
    that the input is not mutated and that sibling values are shared.
- [ ] **AC8. Byte-identical before and after** (step 1). The scratchpad capture diff is empty
  for every item listed in step 1. The Developer reports the diff command and its empty
  output, and saves the capture script in the scratchpad, not the repo.
- [ ] **AC9. No behaviour change in the suites.** These pass with their assertion lines unedited.
  Imports and monkeypatch targets of moved helpers may be re-targeted, each listed in the
  report.
  - `tests/test_gleepglorp_*.py`
  - `tests/test_evals_gleepglorp_*.py`
  - `tests/test_gleepglorp_proposals_*.py`
  - `tests/test_gleepglorp_fill_*.py`
  - `tests/test_gleepglorp_kind_mcp.py` and `tests/test_gleepglorp_kind_provider.py`
  - `tests/test_gleepglorp_kinds.py`
  - `tests/test_gleepglorp_apply_error.py`
  - `tests/test_gleepglorp_targets.py`
  - `tests/test_evals_freeze.py`. If a frozen evals file changes, stop and report it. This leg
    should touch none.
- [ ] **AC10. The full unit tier and the browser lane pass.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with the expected 15 skips.
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane gleepglorp`
    passes. That lane is the client contract of `fill_view` and `proposal_view`.
- [ ] **AC11. The docs.**
  - **`the_one/agents.md`:**
    - "Adding a kind: the checklist" under "GleepGlorp kinds registry (M36 F4)" lists every
      `Kind` member, required or optional, with one line each on what it does, plus a pointer
      for each of: the client spec (Flight 4 L2 section), the write-service pattern (`precheck=`
      / `on_commit=` / `update_in_txn`, services free of `gleepglorp` imports), names through
      `check_name` in `normalize`, and the registries and pins to update (flight DD13's list).
    - The stale "`Kind` members present now" bullet (`:3398`) is rewritten.
    - Project Conventions gains "A kind's fill and proposal reply sentences are tool-result text,
      not platform prompt text, and need no eval run."
  - **`CLAUDE.md`:** the "Prompt evals" rule gains the same exclusion as one clause. It is not
    a new paragraph (CLAUDE.md is size-limited, squawk 0397).
- [ ] **AC12. Lint.** `ruff check` and `ruff format --check` pass on `the_one/ tests/ scripts/
  evals/`.

## Verification Steps

- **AC1:** run the grep and paste the output, with a justification per hit.
- **AC2-AC7:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_gleepglorp_kind_hooks.py -x --timeout 60`. Report, per new test, whether it was
  falsified.
- **AC8:** run the before and after captures, then `diff` them. Report the command and the empty
  output.
- **AC9:** run the listed files, then `git diff --stat -- tests/`. For each touched test file,
  `git diff` shows only import or monkeypatch-target lines.
- **AC10:** run `make test-unit` (in the background, waiting for completion) and the
  `gleepglorp` lane. Report the counts and the wall time.
- **AC11:** quote the new sections.
- **AC12:** run ruff and report its output.

## Implementation Guidance

1. **Capture "before" first, before editing anything.**
   - **Never touch the real data directory.** `fill_view` calls
     `get_encryptor(settings.data_dir)` for a pending fill of a kind with `warnings`, and the key
     file is created on first use. The capture must point `settings.data_dir` at a scratch
     directory, either by `monkeypatch.setattr(settings, "data_dir", tmp_path)` as the `world`
     fixtures do, or by `THE_ONE_DATA_DIR` set to a scratch directory under `$HOME` before
     `the_one.config` is imported. Before running it, check that the real default data
     directory's key file and mtime are unchanged afterwards
     (`python -c "from the_one.config import settings; print(settings.data_dir)"` gives the
     path; do not print any file contents).
   - **Write it as a throwaway pytest file in the session scratchpad,** never under `tests/`.
     - **Reuse the fixtures** (`world`, `seed()`, `norm(...)`, `make_fill(...)`) from
       `tests/test_gleepglorp_kind_mcp.py`, `tests/test_gleepglorp_kind_provider.py` and
       `tests/test_gleepglorp_fill_provider.py`, plus the rule and routine helpers in
       `tests/test_gleepglorp_proposals_apply.py` / `test_gleepglorp_apply_error.py`.
     - **Output:** JSON written to a path from an env var (`CAPTURE_OUT`).
     - **How to run it:** `-p no:cacheprovider`, from the repo root, with `--rootdir` set so
       `tests.*` imports resolve. The same file runs before and after.
   - **What it seeds:** one agent, one rule, one routine (with a schedule), one MCP server
     (stdio and HTTP) and providers (a key-taking type, `ollama`, `anthropic-plan`).
   - **What it dumps (JSON):**
     - `kinds.describe()`, and `describe(k)` for each kind;
     - `kinds.target_args(...)`: every refusal sentence and every alias case, for each kind
       with and without `agent` and `target`;
     - `kinds.normalize(...)` for a create and a change of every kind (and `mode="fill"` for
       the fillable ones), plus the error sentence of an unknown kind, an unknown action, an
       unknown field and a create-only field on a change;
     - `proposal_view(conn, p)` for a create and a change of every kind, including:
       - a routine with a schedule;
       - a rule change whose rule was deleted (`target_gone`);
     - `fill_view(conn, fill)` for a create and a change of each fillable kind (an agent create
       with `agent_name` set and with it `None`, and a provider create), including:
       - a stale change (the stored field moved after the fill);
       - a gone target;
       - a provider type change between key-taking types (`clears_key: true`);
       - a provider change into `ollama`;
     - `errors.translate` for one instance of each exception type it maps (each stale error,
       `AgentWriteError(404)`, the MCP and provider not-found errors, `KeyError`, a rule-create
       `IntegrityError`, `NameRuleError`, `RoutineNameTaken`, and an unmapped `RuntimeError`,
       which must come back as itself);
     - `fill_form` called with `notes_enabled` (its returned string).
   - Volatile fields (ids, timestamps) are normalised in the dump, never skipped.
   - After step 9, run the same file against the new code and `diff -u` the two outputs (AC8).
     Report both files' line counts, so an empty diff cannot come from two empty captures.

2. **`Kind` members** (`kinds/base.py`).
   - Add `addressing: str` as a required field. A dataclass needs required fields before
     defaulted ones, so place it after `summary_text`, and pass it in every `KIND = Kind(...)`:
     - agent: `"agent"`;
     - rule and routine: `"agent-owned"`;
     - MCP server and provider: `"id"`.

     `"page"` is declared for Leg 4a and accepted by the registry test.
   - **Make `card_extras` required through one validation function.** A module-level
     `validate_kind(k)` raises `ValueError` when any of these holds:
     - `card_extras` is `None`;
     - `fillable` is non-empty and `fill_extras` is `None`;
     - `addressing` is not one of the four values;
     - `addressing == "id"` and `target_noun` is empty.

     Both `Kind.__post_init__` and the registry test call it. A frozen dataclass whose
     `__post_init__` only reads fields works, and `dataclasses.replace` re-runs it.
   - **Add `target_noun: str = ""`,** the declared subject of the `"id"` refusal sentence:
     `"An MCP server"`, `"A model provider"`. Do not derive it from `label`: "a" or "an" depends
     on pronunciation.
   - Add the optional members:
     - `fill_extras: FillExtrasFn | None = None`;
     - `operator_only_message: Callable[[list[str]], str] | None = None`;
     - `action_refused: Callable[[str, str], str] | None = None`;
     - `keyerror_is_gone: bool = False`.

     Type aliases go next to the existing ones, and each member gets a docstring line.

3. **Move the built-in card extras** (`proposals/store.py:322-361`) into `agent.py`, `rule.py`
   and `routine.py` as each kind's `card_extras(conn, p)`.
   - Keep the exact title wording, `target_gone` logic and routine schedule keys.
   - `_schedule_bits`, `_quoted` and `_NEXT_RUNS_SHOWN` may stay in `proposals/store.py` and be
     imported lazily inside the routine function (the kinds already import store helpers
     lazily). Or they move to `kinds/routine.py` with a re-export if a test imports them: grep
     first.
   - `_card_extras` becomes `return await kinds.get(p.kind).card_extras(conn, p)`.

4. **`fill_extras`** for the three fillable kinds.
   - **Agent:** what `fill_view` computes for an agent fill today:
     - the title from `kind.card(fill.action, fill.agent_name)`. It must **not** delegate to
       the new proposal-style `card_extras`: `default_card_title` gives `Create agent “None”`
       for a create with `agent_name` `None`, while the card's `_quoted(p.agent_name or "")`
       differs. The capture's agent-create-`None` case pins it;
     - `target_gone` from `_agent_names`;
     - `stale` from the inline block (`fill/store.py:314-330`);
     - `clears_key: False`.
   - **MCP server and provider,** through one shared helper `id_fill_extras(card_extras,
     stale_fn=None, clears_key_fn=None)` in `kinds/base.py` or `kinds/__init__.py`, which Legs
     3a and 4a reuse:
     - title and `target_gone` from their `card_extras(conn, fill)`;
     - `stale` from `_mcp_stale` / `_provider_stale` (moved into the kind modules), only on a
       change with a base and not gone; `[]` on a create or a gone target, as today;
     - `clears_key` from `_clears_key` (provider), or `False` (MCP).
   - **`fill_view`** calls `extras = await kind.fill_extras(conn, fill, labels)` and reads the
     four keys. The returned dict's other keys and their order stay exactly as today; the
     capture diff proves it.
   - **The edge:** an agent fill with `agent_name is None` (a create) must keep `gone = False`
     and `stale = []`.

5. **`target_args`** reads `get(kind).addressing` when `kind` is a known kind. An unknown kind
   passes through unchanged: `normalize` refuses it later with today's sentence. Keep each
   refusal sentence byte-identical.
   - `"agent-owned"` gives today's rule and routine sentence. It names `kind` and `rule` /
     `routine`, so derive the second word from the kind name exactly as today.
   - `"agent"` keeps the alias logic.
   - `"id"` refuses `agent` with `f"{k.target_noun} is named with target, not agent."`. That
     reproduces "An MCP server is named with target, not agent." and "A model provider is named
     with target, not agent." exactly.
   - `"page"`, for Leg 4a: refuse both `agent` and `target` with "App settings take no agent or
     target; name the fields to change." No existing kind uses it.

6. **`REFS`** in `shape.py`: `REFS = {ref: Ref(label, describe_label, loader)}` for `provider`,
   `mcp` and `kb`.
   - `_kind_label`, `_resolve_one` and `_ref_entries` read it. The surface-row exclusion stays
     inside the MCP loader.
   - `describe`'s `reference` reads `REFS[f.ref].describe_label` for refs in `REFS`. `tool`
     stays without a reference, as today.

7. **The error, fill-tool and check hooks.**
   - **`errors._is_gone`:**
     - the bare `KeyError` clause becomes `isinstance(exc, KeyError) and (k :=
       kinds.find(p.kind)) is not None and k.keyerror_is_gone`, with a lazy import to avoid a
       cycle (`errors.py` is imported by `kinds/__init__`). Use `find`, not `get`, which would
       raise `KeyError` inside the handler;
     - the `IntegrityError` clause reads `addressing == "agent-owned"`;
     - set `keyerror_is_gone=True` on all five `KIND`s.
   - **The fill tool:** `FieldSpec.fill_refused` holds the sentence, and agent's
     `notes_enabled` spec carries `NO_NOTES`.
     - **Where `NO_NOTES` lives:** it moves to `kinds/agent.py`, because `fill/tool.py`
       imports `kinds` (a cycle the other way), and `fill/tool.py` re-exports it
       (`from the_one.gleepglorp.kinds.agent import NO_NOTES`), so
       `tests/test_gleepglorp_fill_tool.py:22` stays unedited.
     - **Not in the fields view:** `fill_refused` is not exposed by `describe()`, and the
       propose path never reads it. `fill/tool.py` replaces the `kind == "agent"` test with: for the
     first key in `changes` whose spec has `fill_refused`, return that sentence. Keep the
     `isinstance(changes, dict)` guard and the position (after the `FILLABLE` check, before
     `get_connection`).
   - **`_check_keys`:** when the kind's `operator_only_message` is set and any unknown key is
     in `kind.operator_only`, raise `ShapeError(message(those keys))`. Otherwise keep today's
     sentence.
   - **The action gate** in `normalize`, after the `ACTIONS` check:

     ```
     k = get(kind)
     allowed = k.actions if mode == "propose" else k.fillable
     if action not in allowed:
         raise ShapeError(k.action_refused(action, mode) if k.action_refused else
                          f"A {k.label} can't be {'created' if action == 'create' else 'changed'} "
                          f"{'by a proposal' if mode == 'propose' else 'by filling its form'}.")
     ```

     The Developer may improve the generic wording; no existing path reaches it. An action
     `ACTIONS` itself rejects keeps today's unknown-action sentence: the gate runs after it, and
     `action_refused` is not consulted. `"page"` addressing needs no flag for "no create". Leg 4a
     sets `actions=("change",)`, and the gate does the rest.

8. **`FieldSpec.path` helpers.** Add `stored_get` and `stored_set` (AC7) and rewrite the
   docstring: "`path`: the stored location when it is nested or differs from `stored` (read and
   written through `stored_get` / `stored_set`)".
   - The MCP and provider kinds may adopt them where a hand-written nested read or write is
     replaced one for one, with the capture proving no change. If unsure, leave the kinds
     alone: Legs 3a and 4a are the consumers.

9. **Tests: `tests/test_gleepglorp_kind_hooks.py`.**
   - the registry invariants (AC2);
   - the action gate in both modes (AC3);
   - `operator_only_message` (AC4);
   - `fill_refused` through the tool with a fake spec, plus the existing `NO_NOTES` path (AC5);
   - `keyerror_is_gone` (AC6);
   - the path helpers (AC7).

   - **Fake kinds** are built with `dataclasses.replace(agent.KIND, ...)` or a minimal
     `Kind(...)`.
   - **Patch all four views:**
     - `monkeypatch.setitem(kinds._BY_NAME, ...)` and `monkeypatch.setitem(kinds.SPECS, ...)`;
     - `monkeypatch.setattr(kinds, "KINDS", ...)` and `monkeypatch.setattr(kinds, "FILLABLE",
       ...)`, because those are tuples.

     A small helper in the test file does it. Never edit `REGISTRY`.
   - **AC2's falsification:**
     - `pytest.raises(ValueError)` on a `replace(...)` that breaks each `validate_kind` rule;
     - `validate_kind` run over a `types.SimpleNamespace` stand-in, so the registry test's own
       loop is shown to catch a bad entry.
   - **AC3** shows both the `action_refused` sentence and the generic one. Each safety-relevant test (AC2, AC3, AC4 and AC6) is falsified by editing,
   reported per test.

10. **Docs** (AC11). Keep the agents.md checklist to one bullet per member. The client half
    points to "GleepGlorp client kinds registry (M36 F4 L2)" rather than repeating it.

11. **Run** AC9's files, then lint, then `make test-unit`, then the `gleepglorp` lane. Update the
    flight log's Leg Progress with what was done and verified, mark the leg `landed`, and signal
    `[LAND:leg]`.

## Edge Cases

- **Import cycles.** `kinds/errors.py` and `kinds/base.py` are imported by `kinds/__init__.py`,
  so a hook that needs `kinds.get` imports it inside the function. `shape.py` must still import
  nothing from `kinds` at module level.
- **`fill_view` for an unknown kind.** The fill store already refuses kinds outside `FILLABLE`
  at insert, so `kinds.get` cannot miss for a stored fill. Do not add a fallback.
- **An agent fill with `target_id` set.** Not possible today (agent fills key by name). Keep it
  so.
- **The routine card computes the zone per call** (`time_zones.load_effective_zone`). Keep that
  inside the moved function. Do not hoist it.
- **`dataclasses.replace` on a `Kind` with `__post_init__`** re-runs the check. That is
  intended: the registry test relies on it.
- **Monkeypatched names in existing tests.** Grep `tests/` for `monkeypatch` targets of
  everything moved:
  - `_card_extras`, `_mcp_stale`, `_provider_stale`, `_clears_key`, `_kind_label`,
    `_ref_entries` and `_is_gone`;
  - `fill_view`'s imports.

  Re-target them to where the code now looks them up (the Flight 4 L1a rule: patch where it is
  looked up). Each is listed in the report (AC9).

## Files Affected

- `the_one/gleepglorp/kinds/base.py` — new members and `__post_init__`
- `the_one/gleepglorp/kinds/{agent,rule,routine,mcp_server,provider}.py` — `addressing`,
  `card_extras`, `fill_extras`, `keyerror_is_gone`, and agent's `fill_refused`
- `the_one/gleepglorp/kinds/__init__.py` — `target_args`, `describe`, `_check_keys` and the
  action gate in `normalize`
- `the_one/gleepglorp/kinds/errors.py` — `_is_gone`
- `the_one/gleepglorp/proposals/shape.py` — `FieldSpec.fill_refused`, `REFS`, the path helpers
  and the docstring
- `the_one/gleepglorp/proposals/store.py` — `_card_extras` reduced
- `the_one/gleepglorp/fill/store.py` — `fill_view` reads `fill_extras`; the stale and
  `clears_key` helpers move
- `the_one/gleepglorp/fill/tool.py` — the `fill_refused` check
- `tests/test_gleepglorp_kind_hooks.py` — new
- `tests/*` — only import or monkeypatch-target lines, if any (AC9)
- `the_one/agents.md`, `CLAUDE.md` — AC11
- **Registries and pins checked** (DD13). None changes in this leg:
  - the `fill_form` and `propose_change` enum and description pins;
  - `REGISTRY` and the `KINDS` / `FILLABLE` pins (`test_gleepglorp_kinds.py:45/82`,
    `test_gleepglorp_kind_provider.py:153`);
  - the seam-import guard (`test_gleepglorp_proposals_continuation.py:278-296`; no new module);
  - the evals freeze digests (no evals file is touched).

## Citation Audit

Checked by the FD against the working tree at `180c4c40` (2026-11-23).

- `kinds/base.py::Kind` — frozen dataclass; `card_extras` optional (`= None`); no `addressing`,
  `fill_extras`, `keyerror_is_gone`; `actions` default `("create", "change")` - verified
- `kinds/__init__.py:111-134` `target_args` — the four kind branches and their sentences -
  verified
- `kinds/__init__.py:141-180` `describe` — the `f.ref in ("provider", "mcp", "kb")` map -
  verified
- `kinds/__init__.py:183-193` `_check_keys`; `:196-234` `normalize` (the ACTIONS check at
  `:215`, then `_check_keys`; `mode` passed through) - verified
- `fill/store.py:226-254` `_mcp_stale`, `:262-272` `_clears_key`, `:275-296` `_provider_stale`,
  `:299-391` `fill_view` (the agent inline stale at `:314-330`; `card_extras` at `:333`; per-kind
  stale at `:338-341`; `clears_key` at `:390`) - verified
- `proposals/store.py:311-361` `_card_extras` — the `card_extras` short-circuit then `if agent /
  elif rule / else` (routine) - verified
- `kinds/errors.py:88-99` `_is_gone` — the bare `KeyError` clause at `:95`; `p.kind in ("rule",
  "routine")` at `:99`; `:182-200` `translate`; `reraise` - verified
- `proposals/shape.py:44-73` `FieldSpec` (the `path` docstring "reserved for the kinds that
  follow"); `:142-161` `_kind_label`, `_resolve_one`, `_ref_entries` - verified
- `fill/tool.py:32` `NO_NOTES`; `:114-117` the `FILLABLE` check then the `kind == "agent"` notes
  check; `:121-131` `kinds.normalize(..., mode="fill")` - verified
- `kinds/mcp_server.py:528-546` `KIND = Kind(...)`, `label="MCP server"` - verified
- `kinds/agent.py:95` the `notes_enabled` FieldSpec - verified
- `mode="fill"` callers outside `kinds/`: only `fill/tool.py:130` (grep over `the_one/` and
  `evals/`) - verified
- `agents.md:3393-3401`, the "GleepGlorp kinds registry (M36 F4)" section and the stale members
  bullet - verified
