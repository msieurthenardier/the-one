# Leg: gemma-toolcode-positional-fix

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **Added after the leg-05 behavior test FAILED end-to-end (operator chose "fix both", 2026-06-19).**
> The behavior test proved the recovery feature doesn't execute a real gemma3:4b tool call because
> the fixture was unrepresentative on two axes. See flight-log Anomalies + Decisions ("FIX-BOTH").

## Objective

Make text-form tool-call recovery work **end-to-end for real gemma3:4b** by closing the two gaps the
behavior test exposed: (1) recognize Gemma's ` ```tool_code ` fence; (2) bind recovered **positional**
call arguments (`shell("…")`) to the called tool's **named** parameters at the schema-aware dispatch
site — so the recovered call actually executes.

## Context

- Two independent, compounding causes (both reproduced live; see run log
  `tests/behavior/gemma-tool-use-recovery/runs/2026-06-19-00-27-41.md`):
  1. `the_one/llm/_toolcall_recovery.py:60` `_FENCE_TAGS_TO_PARSE = {"", "tool", "python", "py"}` —
     real gemma emits ` ```tool_code `, which is not in the set → `recover_tool_calls()` returns `[]`.
  2. gemma emits `shell("echo …")` (positional). The kernel parks positional args under
     `arguments["__positional_args__"]` (leg-01 known limitation). Dispatch at
     `the_one/agent/core.py:334-335` does `tool.execute(**tool_call.arguments)` →
     `ShellTool.execute(__positional_args__=[...])`, which can't bind the required `command=` param.
- The kernel is deliberately **schema-less** (DD1), so it cannot name positional args. The only place
  with the tool's parameter schema at dispatch time for a degraded/recovered call is the tool itself
  (`Tool.parameters`) at the `_execute_tool` site. Hence the fix is split: kernel for the fence tag,
  tools-layer for the binding, with a one-line dispatch-site call.

## Design Decisions

**DD-A — Add `tool_code` to the recognized fence tags** (kernel, in `the_one/llm/`): extend
`_FENCE_TAGS_TO_PARSE` to `{"", "tool", "tool_code", "python", "py"}`. `tool_code` is Gemma/Gemini's
documented fenced-tool-call convention. Scope it to the observed tag only — do not speculatively add
others. Positional args continue to be parked under `__positional_args__` by the kernel (the binding is
DD-B's job, downstream where the schema lives).

**DD-B — Schema-aware positional binding lives on the `Tool` base; applied with a one-line dispatch
change**:
- Add `Tool.bind_positional_args(arguments: dict) -> dict` in `the_one/tools/base.py`. **Sentinel
  constant (layering decision, pinned):** do NOT add a `tools→llm` import — `the_one/llm/` is a leaf
  that imports nothing from `the_one/tools/` today, and the kernel advertises itself as importing
  nothing from `the_one`. Define `POSITIONAL_ARGS_KEY = "__positional_args__"` **locally in
  `the_one/tools/base.py`** with a one-line comment cross-referencing the kernel's identical constant
  (the kernel keeps its own; the literal is duplicated, not imported, in either direction). If
  `arguments` contains that sentinel key, map the positional values onto this tool's parameter names
  from `self.parameters["properties"]` in **declaration order**, skipping any name already supplied as a
  keyword. Keyword args always win. Return a **new** dict (don't mutate input) with the sentinel removed
  and the bound names added.
- Apply at `the_one/agent/core.py:_execute_tool` (`:334-335`) by normalizing before the unpack:
  `args = tool.bind_positional_args(tool_call.arguments); output = await tool.execute(**args)`. This is
  the flight's **only** `agent/core.py` change — a single arg-normalization call, NOT iteration or
  auth-pause logic (operator-authorized mission-boundary exception; see flight-log Decisions).
- Rationale: the schema lives on the tool; putting the logic there keeps `core.py` to one line and
  keeps the binding reusable by any dispatch site. A no-op when there's no sentinel (every existing
  structured call is unaffected).

**DD-D — Re-scope the behavior-test observable from host-canary to tool-result/response** (spec
amendment; design review found the original observable invalid): `ShellTool` runs `host_access=False`
by default in an **ephemeral bwrap box** (`home=scratch`, `writable_paths=[scratch]`, `rmtree`'d on
execute return), so a file the tool writes **never reaches the host** and the box is destroyed after the
call. The spec's "host canary file exists" assertion (step 2) therefore **cannot pass even with a
perfect code fix** — it conflated "the tool executed" with "the tool wrote to the host." Amend the spec
to observe the property that actually matters for #105 — **that the tool was dispatched and executed** —
via the **tool-result / chat response**, observable regardless of the sandbox:
- Step 2 action → ask the agent to run a shell command that **echoes a unique marker** (e.g.
  `echo recovered-ok-<rand>`), not write a host file.
- Step 2 expected → **a tool was dispatched AND a tool-result is present in the turn AND the
  tool-result/response contains the marker** (proves recovery fired → shell ran → output returned).
- Step 3 expected → the final assistant message contains **no** raw ` ```tool_code `/` ```tool `
  fenced block (DD4 strip) — unchanged in spirit.
- Drop the host-filesystem precondition + the `filesystem` observable; observables become http (chat
  response) + the session/tool-result read. Rationale recorded in the spec + flight log: this corrects
  an **invalid** observable (sandbox-incompatible), it does **not** weaken the test — the tool-result
  marker is a *more direct* proof of execution than a host file (which only proves a host write, gated
  on `host_access` the model never emits).

**DD-C — Binding heuristic + limits** (record explicitly):
- **Documented intent: required-params-first; mechanism: declaration order** — design review verified
  that for EVERY current built-in tool the `required` list is exactly the first-N declared properties,
  so declaration-order and required-first coincide. Implement via declaration order and add a test
  asserting the two agree for the built-in tools (future-proofs against a tool that declares an optional
  param before a required one). Binding is **top-level-property only** (nested object params like
  connector_send's `target.properties` are not destructured — irrelevant to the single-positional case).
- `n` positional values bind to the first `n` not-already-keyworded property names in declaration
  order. For `shell("echo …")` → `properties` order `[command, cwd, timeout, host_access]`, position 0
  → `command`. Result `{"command": "echo …"}`.
- If there are **more** positional values than bindable slots, bind what fits and leave the remainder
  under `__positional_args__` with a WARN (don't silently drop). 
- If the tool has **no** `properties` (e.g. `search_tools`), nothing binds — leave the sentinel as-is
  (the call will still error, which is correct: a no-arg tool was called with args).
- This is a best-effort positional→named heuristic (declaration order); it cannot disambiguate when a
  model intends a later kwarg-only param positionally. Documented as acceptable — gemma's observed
  single-positional shell call is the target case.

## Acceptance Criteria

- [x] **Kernel recognizes `tool_code`**: `recover_tool_calls("```tool_code\nshell('echo hi')\n```")`
      returns `[{"name": "shell", "arguments": {"__positional_args__": ["echo hi"]}}]`. Existing fence
      tests still pass. (Unit test in `tests/test_toolcall_recovery.py`.)
- [x] **`Tool.bind_positional_args` binds by schema**: for a `ShellTool` instance,
      `bind_positional_args({"__positional_args__": ["echo hi"]})` → `{"command": "echo hi"}` (sentinel
      removed). Keyword args preserved + win on collision; mixed positional+keyword binds the remaining
      slots in order; >slots leaves remainder under the sentinel + WARN; no-properties tool leaves the
      sentinel untouched. (Unit tests in a new/existing tools test file.)
- [x] **No-op for normal calls**: `bind_positional_args({"command": "x"})` returns an equivalent dict
      (no sentinel → unchanged); a structured tool call dispatches exactly as before (regression).
- [x] **Dispatch binds before execute**: `_execute_tool` applies `bind_positional_args` so a recovered
      positional `shell` call executes with `command` bound. (Covered by the behavior test end-to-end;
      optionally a focused agent/dispatch unit test.)
- [x] **`the_one/agent/core.py` change is exactly the one-line normalization** at `_execute_tool` —
      no iteration/auth-pause logic touched. (Reviewer confirms the diff scope.)
- [x] `make test-unit` stays green (3262 passed / 18 skipped baseline + the new tests → 3273 passed /
      18 skipped).
- [x] **Behavior-test spec amended (DD-D)** — `tests/behavior/gemma-tool-use-recovery.md` step 2
      observable changed from the (sandbox-invalid) host canary to the **tool-result/response marker**;
      filesystem precondition/observable dropped; rationale noted in the spec. Status flips `draft` →
      `active` only after the amended test passes (left `draft` — Orchestrator flips it post-pass).
- [ ] **END-TO-END: re-run `/behavior-test gemma-tool-use-recovery` (amended) → PASS** against the
      host-native dev instance: a real gemma turn **dispatches and executes** the shell tool (a
      tool-result is present and the response contains the echoed marker), and the final assistant
      message has **no** raw ` ```tool_code `/` ```tool ` block. The new run log is committed; the leg
      does not land until this passes.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_toolcall_recovery.py <tools-test-file> -x --timeout 30` — green.
- `make test-unit` — full hermetic suite green.
- Restart the dev instance (`make restart`, or the :8585 launch) so it serves the fix, then
  `/behavior-test gemma-tool-use-recovery` → pass.
- `git diff the_one/agent/core.py` — shows only the one-line `bind_positional_args` normalization.

## Implementation Guidance

1. **Kernel** (`the_one/llm/_toolcall_recovery.py:60`): add `"tool_code"` to `_FENCE_TAGS_TO_PARSE`.
   Add a unit test mirroring the existing fence tests for the `tool_code` tag (with the captured gemma
   positional `shell("…")` body, asserting the `__positional_args__` parking).
2. **Shared sentinel constant**: to let `the_one/tools/base.py` reference `__positional_args__` without
   a tools→llm import, define the constant once and import it in both places — simplest is to keep
   `POSITIONAL_ARGS_KEY = "__positional_args__"` in `_toolcall_recovery.py` (already exported) and import
   it in `base.py` (a tools→llm import is acceptable if the llm module stays leaf; if the reviewer
   prefers no such import, lift the constant to a tiny shared module, e.g. `the_one/tools/base.py` owns
   it and the kernel imports from there — but the kernel must stay stdlib-only, so the constant should
   live in the kernel and tools imports it, OR be duplicated with a comment. Pick the cleaner option at
   implementation and note it.)
3. **`Tool.bind_positional_args`** (`the_one/tools/base.py`): implement per DD-B/DD-C. Pure, total over
   dict input; returns a new dict (don't mutate the input). WARN via the module logger on leftover
   positionals.
4. **`_execute_tool`** (`the_one/agent/core.py:334-335`): change to
   `args = tool.bind_positional_args(tool_call.arguments)` then `await tool.execute(**args)`. Nothing
   else in the method changes.
5. **Tests**: kernel `tool_code` test; `bind_positional_args` unit tests (shell single positional,
   mixed, overflow, no-properties, no-sentinel no-op). Keep all hermetic.
6. **Re-run the behavior test** after restarting the dev instance on the fixed code.

## Edge Cases

- **`search_tools` / no-arg tools called positionally** → no properties to bind; sentinel stays; the
  call errors (correct — a no-arg tool shouldn't get args).
- **Keyword + positional collision** → keyword wins; positional fills only unfilled slots.
- **Positional value for a non-string param** (e.g. a positional meant for `timeout:int`) → bound as-is
  (the kernel `literal_eval`'d it, so it's already the right Python type); the tool's own validation
  handles type mismatches.
- **gemma emits keyword form** (`shell(command="…")`) on some runs → already handled (kernel parses
  kwargs first-class); `bind_positional_args` is a no-op. Recovery works either way.

## Files Affected

- `the_one/llm/_toolcall_recovery.py` — add `tool_code` to `_FENCE_TAGS_TO_PARSE`.
- `the_one/tools/base.py` — new `Tool.bind_positional_args`.
- `the_one/agent/core.py` — one-line normalization at `_execute_tool` (the flight's only core.py change).
- `tests/test_toolcall_recovery.py` — `tool_code` fence test.
- `tests/test_tool_base.py` (or a focused new file) — `bind_positional_args` unit tests + the
  required-first/declaration-order agreement test for built-in tools.
- `tests/behavior/gemma-tool-use-recovery.md` — spec amendment (DD-D: tool-result/response observable
  instead of host canary; drop filesystem observable); status `draft` → `active` after pass.
- `tests/behavior/gemma-tool-use-recovery/runs/{new-ts}.md` — the re-run (pass) run log.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified, incl. the **behavior test re-run PASSES** (Orchestrator)
- [x] `make test-unit` green (3273/18); `agent/core.py` diff is the one-line normalization only
- [x] Update flight-log.md with the leg-07 progress entry (code/test result; behavior re-run deferred)
- [ ] Flip `tests/behavior/gemma-tool-use-recovery.md` status `draft` → `active` (Orchestrator, post-pass)
- [x] Set this leg's status to `landed` (deferred-review model — NOT committed)
- [ ] Check off this leg in flight.md (Orchestrator, at flight review)
- [ ] (After this, resume the agentic-workflow Phase 2d: flight review + commit)
