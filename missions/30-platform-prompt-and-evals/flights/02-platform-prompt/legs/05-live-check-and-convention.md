# Leg: live-check-and-convention

**Status**: in-flight
**Flight**: [The platform prompt](../flight.md)

## Objective
Prove the final platform prompt live (the Discord link behavior test and the four prompt-sensitive behavior specs), record the evals convention in the project docs (DD11), and pass the full local gate.

## Context
- Flight DD9 and DD11 are authoritative. Leg 2 landed the final wording (candidate 3) and `evals/baselines/m30-platform.json`, provided its `compare` showed no hard-gate failure.
- **Behavior tests are run by the Flight Director** with `/mission-control:behavior-test <slug>`, which orchestrates its own Executor and Validator. They are not implemented by a Developer. There are five:
  1. `discord-markdown-links` (new, DD9)
  2. `agent-notes-round-trip`
  3. `agent-rules-round-trip`
  4. `agent-tells-the-time`
  5. `agent-self-revision-propagation` (`draft`; a defect in the spec itself is corrected at run time, not counted as a regression)
- **Before each run,** a Developer updates any expected wording in the spec that quotes platform text changed in this flight: the notes and rules headings, the tool-free notes heading and `base_prompt`. Those specs record what they assert. **Model:** the existing specs ran on `gpt-oss:20b`; they keep their model, and only `discord-markdown-links` uses Haiku 4.5.
- **Dev instances** use port 8486 (or 8487 or higher for concurrent specs) and scratch data directories under `$HOME`. Never 8484 or 8485.
- **The convention (DD11)** goes into CLAUDE.md's "Prompt evals" section and `evals/README.md`:
  - A change to platform prompt text (`the_one/agent/platform_prompt.py`, the rules and notes layers in `the_one/db/_rules.py` and `_notes.py`, the date-line templates, the starting tool descriptions) lands with an eval run compared against the current baseline (`evals/baselines/m30-platform.json`), including its token cost.
  - Evals stay out of CI and the test gate.
  - A changed scenario set requires a same-prompt re-baseline.
  - `the_one/agents.md` gets the "Platform prompt" section (structure, capabilities, the two prompts, conditional seeding, where each consumer reads it), if leg 1b/1c did not already add it in full.

## Acceptance Criteria
- [ ] **Behavior specs reviewed.** Each of the five specs is checked against the final platform text, and any spec quoting changed text is updated, with the change listed in the flight log.
- [ ] **`discord-markdown-links` passes.** The run log is at `tests/behavior/discord-markdown-links/runs/{ts}.md` and is referenced in the flight log. The spec status becomes `active`.
- [ ] **The other four specs pass.** `agent-notes-round-trip`, `agent-rules-round-trip`, `agent-tells-the-time` and `agent-self-revision-propagation` each pass, with run logs referenced. A failing spec blocks the leg until it is fixed, with a new commit and a re-run, unless the failure is a spec defect, which is corrected in place and recorded.
- [ ] **Docs.** CLAUDE.md's "Prompt evals" section states the convention, names `m30-platform.json` as the current baseline, and lists what counts as platform prompt text. `evals/README.md` matches it. `the_one/agents.md` has the "Platform prompt" section.
- [ ] **Full gate.** `make gate` under `THE_ONE_TEST_NETNS=1` (unit, then all browser lanes at `--parallel 3`) passes. Known squawk flakes that pass when re-run in isolation are recorded and accepted. `make lint` is clean.

## Verification Steps
- The run logs under `tests/behavior/*/runs/`.
- `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 make gate`, started detached with `setsid nohup` (the M27 lesson), with its `PARALLEL_RESULT` line recorded.
- `grep -n "m30-platform" CLAUDE.md evals/README.md`

## Implementation Guidance
1. **A Developer pass first:**
   - Update the specs' quoted wording.
   - Write the DD11 docs.
   - Run `make test-unit` and `make lint`.
   - Leave changes uncommitted.
2. **The Flight Director then runs the five behavior tests,** one at a time, each on its own dev instance.
3. **Last, the full gate.** A Developer runs `make gate` detached, monitors it, and triages any failure.

## Edge Cases
- **Plan-token refusals during `discord-markdown-links`:** re-probe and re-run. A refusal is not a product failure.
- **gpt-oss non-determinism in the round-trip specs:** those specs seed fixtures for their security steps (the M27 lesson). A behavioral miss on a step that relies on model initiative is investigated before it counts as a regression.

## Files Affected
- `tests/behavior/*.md` (quoted wording), plus the new runs directories
- `CLAUDE.md`, `evals/README.md`, `the_one/agents.md`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.

## Citation Audit
Checked against the flight spec (DD9, DD11) and the existing behavior specs' slugs in `tests/behavior/`, 2026-10-14.
