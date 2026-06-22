# Leg: behavior-test-gemma-tool-use

**Status**: completed
**Flight**: [Open-Model Tool-Use Robustness (#105)](../flight.md)

## Objective

Run the end-to-end acceptance behavior test `gemma-tool-use-recovery` against the **running
the-one agent** (`POST /api/chat`) to confirm that a real gemma3:4b turn which emits a text-form
tool call **executes** the tool (host canary appears) with **no** raw ` ```tool ` block in the final
assistant message — proving the whole path (model → provider recovery → agent loop → tool → result →
follow-up turn) holds together live.

## Context

- This is a **behavior-test leg**, not a code leg. Its acceptance criterion **is** the behavior
  test: the Flight Director runs `/behavior-test gemma-tool-use-recovery` directly (the run skill
  orchestrates its own Executor + Validator crew using the Witnessed pattern — this leg does **not**
  spawn a Developer).
- The spec already exists at `tests/behavior/gemma-tool-use-recovery.md` (authored + refined during
  flight/leg planning; status `draft`). This leg does not re-author it; it **runs** it and, on pass,
  flips its status to `active`.
- Distinct from leg 04: leg 04 is the provider-level `@pytest.mark.live` unit (does `Message` carry
  a recovered `ToolCall`?). This leg is the full-loop end-to-end (does the agent actually *execute*
  the tool and finish the turn?), including the degraded follow-up round-trip validated in leg 03.

## Prerequisites (verify before running)

- [x] **the-one instance running** and `POST /api/chat` reachable (`http://localhost:8484`, HTTP 200).
- [x] **The running instance is serving the flight/03 recovery code** — the-one runs **host-native**
      (operator-confirmed; NOT in Docker — disregard the `docker-compose.yml` in the tree, it does
      not describe how this instance runs). The host process serves the working tree directly (the
      `pip -e` editable install / `--reload` picks up `the_one/` edits), so leg-02's
      `ollama_provider.py` recovery wiring and the new `the_one/llm/_toolcall_recovery.py` are live.
      Because there is **no container boundary**, the behavior test's host canary file is directly
      observable by the Executor (the original spec apparatus holds — no path adaptation needed).
- [ ] **Ollama + gemma3:4b reachable**; `supports_tools("gemma3:4b")` → `False` (degraded path under
      test). An agent configured for the Ollama gemma3:4b provider **with the shell tool enabled**
      exists, or the Executor creates one (spec step 0).
- [ ] Host filesystem read access for the canary checkpoint.

## Acceptance Criteria

- [ ] `/behavior-test gemma-tool-use-recovery` runs to completion and the run log records **pass**
      (all judged steps PASS; the core step-2 canary assertion holds: the host canary file exists
      with content `recovered-ok`, i.e. the text-form call was recovered AND executed).
- [ ] Step 3 holds: the final assistant message contains **no** raw ` ```tool ` block (DD4 strip),
      and a tool was actually invoked.
- [ ] Step 4 holds: the turn **completed** (coherent final answer; no 400 / no stall — DD5 degraded
      round-trip works live, consistent with leg 03's finding).
- [ ] Step 5 holds: an ordinary no-tool message triggers **no** tool dispatch and no canary side
      effect (DD2 high-precision — no false-positive recovery on prose).
- [ ] The run log is written to `tests/behavior/gemma-tool-use-recovery/runs/{ts}.md` and
      **committed** (evidence dir is gitignored). The behavior-test spec status is flipped
      `draft` → `active` on pass.
- [ ] A **failing** behavior test blocks the leg: investigate + fix in a new commit, re-run; OR, if
      the operator accepts a failure as a known issue, record that disposition in the flight-log
      entry alongside the run-log path.

## Verification Steps

- Run `/behavior-test gemma-tool-use-recovery`; read the resulting run log verdict.
- `ls tests/behavior/gemma-tool-use-recovery/runs/` — a new `{ts}.md` run log exists.
- Confirm `tests/behavior/gemma-tool-use-recovery.md` status is `active` after a pass.

## Implementation Guidance

1. **Verify prerequisites** (above) — especially that the running instance has the recovery code.
2. **Invoke** `/behavior-test gemma-tool-use-recovery` (Flight Director runs it directly).
3. **Interpret the run log**: pass → proceed; fail → the leg does not land. Diagnose (is it a setup
   failure — wrong model / missing shell tool — or a genuine recovery failure?), fix in a new commit
   (no amend), re-run. A model-declined-to-call-a-tool run is INCONCLUSIVE (re-run / rephrase), not a
   code FAIL.
4. **On pass**: flip the spec status to `active`; record the run-log path in the flight log.

## Edge Cases

- **Running instance is stale** (pre-recovery code) → false FAIL. Restart on the branch and re-run.
- **No gemma agent / shell tool** → the Executor creates the agent (step 0) / the step-1 guard stops
  with a setup-failure verdict (not a recovery FAIL).
- **gemma declines to attempt a tool call** → INCONCLUSIVE; the spec's one-shot directive re-prompt
  covers it; re-run if needed.
- **Sandbox/host canary path mismatch** — the shell tool may execute in a sandbox seam; the canary
  path must be one the test can both have-the-tool-write and read back. The Executor resolves the
  concrete reachable path at run time (spec step 2 picks it).

## Files Affected

- `tests/behavior/gemma-tool-use-recovery.md` — status `draft` → `active` on pass (no body change
  unless the run reveals spec drift).
- `tests/behavior/gemma-tool-use-recovery/runs/{ts}.md` — new run log (committed).
- (evidence dir `tests/behavior/gemma-tool-use-recovery/runs/{ts}/` — gitignored, not committed.)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] Behavior test run; run log committed; verdict recorded
- [ ] Spec status flipped to `active` on pass
- [ ] Update flight-log.md with the leg progress entry + run-log path
- [ ] Set this leg's status to `landed` (deferred-review model — final autonomous leg before the
      flight review/commit step)
- [ ] Check off this leg in flight.md
- [ ] (This is the last planned execution leg; the flight review + commit + landing happen next in
      the agentic-workflow Phase 2d/3 — do NOT commit here beyond what the behavior-test skill commits
      for its run log)
