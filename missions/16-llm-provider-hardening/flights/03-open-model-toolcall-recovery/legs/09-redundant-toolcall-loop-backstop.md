# Leg: redundant-toolcall-loop-backstop

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

> **CP4 fix — operator-directed (2026-06-19). Touches the agent loop's iteration/dispatch logic** — a
> further, operator-authorized expansion of the flight/mission boundary (the prior legs deliberately
> avoided the iteration logic; this one enters it). Rationale: after leg-08 made gemma reliably *execute*
> tools, the model loops re-emitting the same call and terminates with an empty message (no closing
> answer) — a gemma3:4b synthesis-capability floor the Validator judged **not** prompt-tunable. The
> model-agnostic fix is a dispatch-side backstop. See run logs `…-03-35-08.md` + `…-03-51-38.md`.

## Objective

Stop the degraded-mode loop where the model re-emits a tool call whose result it already has and ends
with an empty message. Detect the redundant re-emission in the agent loop, suppress the wasteful
re-dispatch, and **guarantee a non-empty closing answer** by deterministically surfacing the already-
obtained tool result(s) when the model itself produces neither new tool calls nor closing text.

## Context

- **Failure signature** (CP4, two runs): the model emits the SAME `(name, arguments)` tool call several
  times; each runs and returns a result into history (`self.messages`); eventually the model emits an
  empty response with no `tool_calls`, so `_run_iterations` exits (`core.py:225-226` `if not
  response.tool_calls: return`) leaving an **empty final assistant message** — no answer for the user.
- **Why model-agnostic, not more prompt**: the leg-08 post-tool-STOP directive changed nothing — gemma
  fails at *composition*, not instruction-following. A loop-side guard works regardless of model.
- **Where**: `_run_iterations` (`core.py:179-241`) — the dispatch decision. This is the iteration logic
  the flight has so far kept untouched; entering it is the operator-authorized expansion this leg makes.
  The change is bounded to redundancy-detection + a closing-synthesis fallback; it does NOT alter the
  auth-pause/`_deferred_tool_calls` flow or the per-iteration budget mechanics.

## Design Decisions

**DD-A — Executed-map keyed by `(name, canonical-json(RAW arguments)) → result content`.** Build a
turn-local `dict[(str,str), str]` (reset per `_run_iterations` entry). After a call is **successfully
dispatched** (NOT paused, NOT the `continue` virtual signal), record `key → its ToolResult content`.
Key on the call's **raw `tc.arguments`** (e.g. a recovered gemma call is `{"__positional_args__":
["echo hi"]}` here — `bind_positional_args` runs later inside `_execute_tool` and does NOT mutate the
ToolCall, so each re-emission recovers to the identical raw shape → the key matches across iterations).
Storing the result **content** in the map (not looking it up later by id) is required because a
re-emitted redundant call carries a **freshly synthesized id** (`f"{name}_{i}"`) that will NOT match the
original dispatch's `tool_call_id` — so id-based lookup of the prior result fails; the map sidesteps it.
*(Cross-representation note: a structured `{"command":"echo hi"}` and a recovered
`{"__positional_args__":["echo hi"]}` key differently — harmless; both CP4 re-emissions come from the
same degraded recovery path → same shape.)*

**DD-B — Partition each response's `tool_calls` into new vs redundant; only dispatch the NEW ones.** If
the model re-emits an already-satisfied call alongside genuinely new calls, drop the redundant ones and
dispatch the rest normally (the legitimate multi-step path is unaffected — new calls always dispatch).

**DD-C — Backstop trigger ends the turn by REPLACING the empty terminal message — not appending.** When,
after dropping redundant calls, **no new calls remain** AND `response.content` is empty/whitespace, the
model is stuck. **Critical:** `response` was already appended to `self.messages` and yielded at
`core.py:225-226` *before* this decision, and `self.messages` is persisted verbatim
(`encode_messages(agent.messages)`). Appending a closing would leave the **empty terminal response in
history still carrying its redundant `tool_calls`** — which on replay emits **orphaned `tool_call`
events with no following `tool_result`** (codec content-gates the assistant *text* event, so it's not a
blank bubble — it's the dangling tool_call entries that are the real artifact). Therefore **replace** it:
`self.messages[-1] = Message.assistant(content=closing); yield self.messages[-1]; return`. The
replacement carries no `tool_calls`, so no orphaned events. At the all-redundant point `response is self.messages[-1]` (nothing was dispatched/appended in
between), so in-place replacement is safe and realizes "replace the empty terminal message" without
moving the append site. The `closing` is synthesized from the executed-map's stored result(s) for the
redundant call(s): *"Done. The output of `{name}` was:\n{result}"* (single) or a compact list; if a
surfaced result `is_error`, mark it as a failure in the closing so the user isn't misled.

**DD-C2 — Redundant-calls-but-has-text → clear the redundant `tool_calls`, then `return`.** If after
dropping redundant calls no new calls remain but `response.content` is **non-empty**, the model answered:
the response (already appended+yielded with its text) IS the answer. **Clear its now-undispatched
`tool_calls`** (`self.messages[-1].tool_calls = []`) before `return` so replay doesn't emit orphaned
`tool_call` events, then `return` without dispatching or appending anything.

**DD-D — Scope the backstop to the degraded path (`not supports_tools`) to eliminate capable-model false
positives.** The CP4 loop is gemma/degraded-specific. A capable model may *legitimately* re-emit an
identical call to re-poll changing state (`shell("date")`, `shell("ls")`) — short-circuiting that with a
stale result would be wrong. So **gate the whole backstop on the `not supports_tools` branch** (already
resolved at `core.py:185`). This removes the polling false-positive entirely and shrinks the blast radius
on the sensitive iteration logic. (Trade-off: the fix is degraded-path-scoped, not globally
model-agnostic — acceptable; that's where the problem lives.) Within the degraded path the trigger is
still tightly bounded: fires ONLY on all-redundant + no-text.

**DD-E — Mission/flight boundary record.** This leg edits `the_one/agent/core.py` iteration/dispatch
logic — beyond even the leg-08 expansion. Operator-authorized (see flight-log). It does NOT add a
framework, change the auth-pause logic, or alter the `LLMProvider` contract. Annotated at the mission
header alongside the leg-08 note.

## Inputs

- `the_one/agent/core.py:179-241` (`_run_iterations`: the stream → `if not response.tool_calls: return`
  → `_dispatch_tool_calls` flow), `:319+` (`_dispatch_tool_calls`), `base.py` (`Message`, `ToolCall`,
  `ToolResult`, `Role`). The leg-08 degraded path + leg-01/07 recovery are unchanged.

## Outputs

- `the_one/agent/core.py` — redundancy detection + the all-redundant closing-synthesis backstop in
  `_run_iterations` (plus a small helper for the executed-set / closing text).
- Unit tests: redundant detection, partition (new vs redundant), the all-redundant closing synthesis,
  and no-false-positive (capable multi-step + repeated-with-text).
- A passing behavior-test re-run (CP4 now green).

## Acceptance Criteria

- [x] **Redundant detection**: a `(name, arguments)` already dispatched-with-result this turn is
      detected as redundant regardless of `arguments` key order (canonical-json compare). Unit-tested.
- [x] **Partition / dispatch only new**: a response mixing one redundant + one new call dispatches ONLY
      the new call; the redundant one is dropped (not re-executed). Unit-tested.
- [x] **All-redundant backstop REPLACES the empty message**: a response whose tool calls are ALL
      redundant AND whose content is empty ends the turn with a **non-empty** synthesized assistant
      message surfacing the prior result(s). The turn does NOT loop further. **Assert directly on
      `agent.messages`** after the backstop fires: NO `Role.ASSISTANT` message with empty content, AND no
      assistant message carrying leftover undispatched `tool_calls` (i.e. no orphaned tool_call → no
      following tool_result). (Asserting only that `messages_to_ui_events` shows no blank assistant bubble
      is vacuous — the codec content-gates that regardless; the bite is the messages-shape + no-orphaned-
      tool_calls invariant.) Unit-tested (mock provider: same call twice → 2nd triggers the closing).
- [x] **Degraded-path scoped**: the backstop runs ONLY when `not supports_tools`. A capable-model run
      (supports_tools True) that re-emits an identical call is NOT short-circuited (today's behavior).
      Unit-tested.
- [x] **Redundant-but-text (DD-C2)**: a response with redundant calls + non-empty text exits with that
      text (no synthesized closing, no duplicate message). Unit-tested.
- [x] **No false positives**: (a) a capable multi-step flow (distinct new calls across iterations)
      dispatches all of them normally; (b) a response that repeats a call BUT includes real text exits
      normally with that text (not the synthesized closing); (c) a normal single tool call → result →
      text answer is unaffected. Unit-tested.
- [x] **Auth-pause untouched**: the `_deferred_tool_calls` / `is_auth_required` path is unchanged
      (verify the backstop sits before/around dispatch without altering the pause flow).
- [x] `make test-unit` stays green (3288 baseline + new tests). → **3302 passed / 18 skipped**.
- [ ] **END-TO-END: re-run `/behavior-test gemma-tool-use-recovery` → PASS (all 5 checkpoints)**: the
      real gemma turn executes the tool (CP2/CP3), CP5 stays clean, and **CP4 now passes** — the loop is
      caught and the turn ends with a coherent answer surfacing the result (non-empty final message). New
      run log committed; spec status flips `draft` → `active`. The flight does not land until this passes.

## Verification Steps

- `PYTHON=.venv/bin/python bash scripts/run-tests.sh <new-tests> -x --timeout 30` — green.
- `make test-unit` — green.
- `git diff the_one/agent/core.py` — change confined to `_run_iterations` redundancy/backstop + helper;
  no auth-pause/budget changes.
- Restart :8585; `/behavior-test gemma-tool-use-recovery` → all 5 checkpoints pass.

## Implementation Guidance

1. **Executed-map** in `_run_iterations`: before the `while` loop, `executed: dict[tuple[str, str], str]
   = {}` (key → result content). Key helper: `(tc.name, json.dumps(tc.arguments, sort_keys=True))` on
   the **raw** `tc.arguments` (DD-A). Populate it **only after a successful, non-paused dispatch**:
   after the `_dispatch_tool_calls(new)` iterator drains AND `self._deferred_tool_calls is None`, record
   each dispatched call's key → the content of its `ToolResult` (read the just-appended `Role.TOOL`
   messages, match by `tool_call_id`). Do not record the `continue` virtual signal.
2. **Gate the whole backstop on the degraded branch** (DD-D): only run the partition/backstop when
   `not supports_tools` (the existing branch at `core.py:185-188`). The capable path keeps today's
   behavior exactly (dispatch all `response.tool_calls`).
3. **At the dispatch decision** (degraded path, after `if not response.tool_calls: return`): partition
   `response.tool_calls` into `new = [tc for tc if key(tc) not in executed]` and redundant (the rest).
   - `new` non-empty → `_dispatch_tool_calls(new)` (existing path), record their keys→results, continue.
   - `new` empty AND `response.content` blank → **backstop (DD-C)**: build `closing` from the
     executed-map's stored result(s) for the redundant calls; **`self.messages[-1] =
     Message.assistant(content=closing)`** (replace the empty terminal response — do NOT append), `yield
     self.messages[-1]`, `return`.
   - `new` empty AND `response.content` non-blank → **DD-C2**: the response (already appended+yielded) is
     the answer; just `return` (no dispatch, no append).
4. **Closing text helper** (pure, unit-testable): given the redundant call name(s) + their stored result
   content (+ `is_error` flag), render a concise non-empty message; mark errors as failures. The stored
   result is the `ToolResult.content` (already `str`-normalized); **truncate** an oversized result in the
   closing (cap to a sane length, e.g. reuse the codec's truncation helper or a simple cap) so the
   surfaced answer can't dump a huge payload.
5. **Keep the backstop OUT of the auth-pause path**: redundant detection is on the *response's* calls
   before dispatch; the pause logic is inside `_dispatch_tool_calls` / the `_deferred_tool_calls` check
   and is unchanged. Recording into the executed-map only after a non-paused dispatch ensures a paused
   call is never treated as redundant (it stays re-dispatchable on resume).
5. **Tests**: use a mock/stub provider (extend `the_one/llm/mock.py` or a local stub) that returns a
   scripted sequence: same `shell(command="echo hi")` call twice (2nd → backstop closing); a
   mixed-redundant+new case; a repeated-call-with-text case; a clean multi-step case. Assert dispatch
   counts + the final assistant content.

## Edge Cases

- **Empty `arguments`** (no-arg tool repeated) → still keyed by `(name, "{}")`; detected.
- **Multiple distinct redundant calls in one response** → closing surfaces each result (compact).
- **First-ever call** is never redundant (executed-set empty) → dispatches normally.
- **Result was an error** (`is_error`) → still surface it in the closing (the user should see the error,
  not an empty message); the backstop guarantees *an* answer, not a successful one.
- **Capable models** rarely hit this (they compose their own answer), but the backstop is model-agnostic
  and harmless for them (only fires on the exact stuck signature).

## Files Affected

- `the_one/agent/core.py` — `_run_iterations` redundancy detection + closing-synthesis backstop + helper.
- `tests/` — backstop unit tests (mock provider).
- `the_one/agents.md` — note the degraded loop now has a redundant-call backstop (brief).
- `tests/behavior/gemma-tool-use-recovery.md` — status `draft` → `active` after the full-pass re-run.
- `tests/behavior/gemma-tool-use-recovery/runs/{new-ts}.md` — the passing run log.
- `missions/16-…/mission.md` — header annotation (iteration-logic expansion).

---

## Post-Completion Checklist

**Complete ALL before `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified, incl. the **behavior-test re-run PASSES all 5 checkpoints**
      (END-TO-END re-run is the Orchestrator's job — left UNCHECKED here)
- [x] `make test-unit` green; `core.py` diff confined to the backstop; auth-pause untouched
- [x] Mission header annotated (iteration-logic expansion)
- [x] Flight log leg-09 entry (the re-run result is pending the Orchestrator)
- [ ] Behavior-test spec `draft` → `active`; mark leg 05 + leg 08 landed (Orchestrator, after re-run)
- [x] Set this leg `landed`; check off in flight.md
- [ ] (After this: resume agentic-workflow Phase 2d — flight review + commit)
