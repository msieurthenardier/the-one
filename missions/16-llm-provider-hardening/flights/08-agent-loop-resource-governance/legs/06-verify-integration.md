# Leg: verify-integration

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Close the flight's verification: confirm the generalized "what the model receives" governor
tests (already in leg 1), author + run the **Witnessed behavior test** that exercises the
whole chain live (engine config UI → web_search honest-empty → governor-bounded results →
overlay fullness signal), and record the deferred **context-compaction** work as a
mission-level backlog seed.

## Context
- **DD5 (binding)**: unit tests for the governor generalized across tool types — DONE in
  leg 1 (`tests/test_governor.py` cross-tool: web/filesystem/shell large-valid→bounded,
  small→unchanged, scales-with-window, error bounded, shell tail kept). This leg VERIFIES
  that coverage exists + passes; it does not re-add it.
- **DD5 behavior test**: a live `:8485` run for the overlay transitions + "a stream-hunt
  conversation no longer degenerates." Authored as `tests/behavior/agent-governance-and-search.md`,
  run via `/behavior-test`. The Witnessed pattern fits: the governor bound, the honest-empty
  search, and the overlay color/aria are only observable by driving a live chat + UI.
- **DD2 deferral**: context **compaction** (evict/summarize) is explicitly its own future
  mission — record the backlog seed in `mission.md` so it isn't lost.
- Suites currently green: unit **3574/0**, browser **486/0** (full `make test-browser`
  baseline captured in leg 5).

## Inputs
- Legs 1-5 landed (uncommitted): governor, search registry, secret persistence, admin UI,
  overlay thresholds.
- `.env`: `ANTHROPIC_API_KEY` + `OPENROUTER_API_KEY` present; dev server runnable on :8485
  (`THE_ONE_DEV_MODE=true`); Ollama local (`qwen2.5:7b`, `ministral-3:8b`).
- chrome-devtools MCP = the browser apparatus.

## Outputs
- `tests/behavior/agent-governance-and-search.md` — the Witnessed spec.
- A committed run log at `tests/behavior/agent-governance-and-search/runs/{ts}.md`.
- A context-compaction backlog seed recorded in
  `missions/16-llm-provider-hardening/mission.md` (the section the project uses for
  cross-flight known issues / backlog).
- Confirmation: full unit + browser suites green at/above baseline.

## Acceptance Criteria
- [ ] The generalized governor tests (leg 1) exist and pass (`tests/test_governor.py`
      cross-tool) — verified, not re-added.
- [ ] `tests/behavior/agent-governance-and-search.md` authored (Zephyr-style Action |
      Expected table) covering: (UI) engine dropdown + show_if + masked key + eye-toggle;
      (governor) a large valid fetch returns a BOUNDED result and the turn completes (no
      hang, no context-poison); (overlay) the context bar colors + the container aria-label
      conveys fullness without color; (search) web_search surfaces results or an honest
      `[error]` — never a silent "No results found" that drives URL-guessing.
- [ ] `/behavior-test agent-governance-and-search` runs against a live :8485 instance with a
      tool-capable agent; a run log is written. A PASS lands the leg; a FAIL is investigated
      and fixed (new commit, no amend) OR recorded as a known issue with operator
      disposition per the flight-end policy.
- [ ] The context-compaction deferral is recorded as a backlog seed in `mission.md`.
- [ ] `make test-unit` (≥3574) and `make test-browser` (≥486) both green.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_governor.py -x --timeout 30`
  (governor cross-tool tests pass).
- `/behavior-test agent-governance-and-search` (Flight Director orchestrates the Witnessed
  run directly — Executor + Validator; not a Developer agent).
- `make test-unit` + `make test-browser` — green.

## Implementation Guidance
1. **Verify leg-1 governor tests** — run `tests/test_governor.py`; confirm cross-tool
   coverage exists. If a gap is found, add it here (otherwise no change).
2. **Author the behavior spec** — `tests/behavior/agent-governance-and-search.md` (done in
   this leg's design; see the spec file). Preconditions: dev server on :8485; a web-tool
   agent on a tool-capable model (e.g. a Sonnet agent using `ANTHROPIC_API_KEY`, mirroring
   the F07 `sonnet-loop-test` precedent); to make the overlay threshold reliably observable,
   the instance may run with a LOW `THE_ONE_CONTEXT_WARN_PCT` (e.g. 5) so a few turns cross
   it.
3. **Run** `/behavior-test agent-governance-and-search`; the FD drives Executor + Validator,
   writes the run log, references it in the flight log.
4. **Record the compaction backlog seed** in `mission.md` (semantic destination: the
   project's cross-flight known-issues / backlog area) — one entry: "Context compaction
   (evict old tool results / summarize earlier turns) — deferred from F08 DD2 to its own
   future mission; the governor (F08) bounds per-result size and the overlay warns at
   fullness, but no recovery/eviction exists near the limit."
5. **Confirm suites** green.

## Edge Cases
- **Live model variance**: use a capable agent (Sonnet) for the governor/search steps so the
  behavior is reliable; a flaky local-model turn is not a flight defect — re-run or switch
  the agent per the run-skill's operator-intervention flow.
- **DDG live state**: web_search may genuinely return results OR be blocked; both are PASS as
  long as the surfacing is HONEST (results or `[error]`, never a silent false-empty). The
  test judges honesty, not a specific result count.
- **Governor observability**: the bound is visible as a coherent completed turn on a large
  page (no hang/poison) + optionally the tool-result content carrying the truncation marker;
  the precise byte bound is asserted in the unit tests, not re-measured live.

## Files Affected
- `tests/behavior/agent-governance-and-search.md` (new spec).
- `tests/behavior/agent-governance-and-search/runs/{ts}.md` (run log, written by the run).
- `missions/16-llm-provider-hardening/mission.md` (compaction backlog seed).
- Flight artifacts (leg status, flight.md checkbox, flight-log run reference).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] Generalized governor tests verified passing
- [ ] Behavior spec authored + `/behavior-test` run (PASS, or FAIL dispositioned)
- [ ] Compaction backlog seed recorded in mission.md
- [ ] `make test-unit` + `make test-browser` green
- [ ] Update flight-log.md (run-log reference + verdict)
- [ ] Set this leg's status to `landed` (commit deferred to flight end)
- [ ] Check off this leg in flight.md
- [ ] (Last autonomous leg — flight-end review + commit follows; optional HAT leg 7 after)
