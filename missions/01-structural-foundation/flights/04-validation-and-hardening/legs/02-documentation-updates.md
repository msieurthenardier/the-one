# Leg: documentation-updates

**Status**: completed
**Flight**: [Validation & Hardening](../flight.md)

## Objective

Add testing conventions to CLAUDE.md, backfill flight 03 log sections from its debrief, and audit all 11 mission success criteria against the codebase.

## Context

- Flight 03 debrief identified missing CLAUDE.md testing docs and empty flight log sections as action items
- The flight 03 log (at `missions/01-structural-foundation/flights/03-test-infrastructure-and-ci/flight-log.md`) has empty Decisions, Deviations, and Anomalies sections despite the debrief documenting content for all three
- Mission has 11 success criteria, all currently unchecked — need to audit each against actual codebase state

## Inputs

- `CLAUDE.md` — current project documentation (no testing section)
- Flight 03 log at `missions/01-structural-foundation/flights/03-test-infrastructure-and-ci/flight-log.md` — empty sections
- Flight 03 debrief at `missions/01-structural-foundation/flights/03-test-infrastructure-and-ci/flight-debrief.md` — has deviations, key learnings, recommendations
- Mission artifact at `missions/01-structural-foundation/mission.md` — 11 unchecked success criteria

## Outputs

- `CLAUDE.md` with new Testing section
- Flight 03 log with populated Decisions, Deviations, Anomalies sections
- Mission success criteria checked off (or noted as known issues if unmet)

## Acceptance Criteria

- [x] CLAUDE.md has a Testing section documenting: `THE_ONE_TEST_URL` env var, `@pytest.mark.live` marker convention, `pytest -m live` command, unit vs AIAT separation, FakeLLM/StubTool pattern
- [x] Flight 03 log Decisions section has at least the leg reordering decision (decided to execute legs 4/5 out of order since they were independent)
- [x] Flight 03 log Deviations section has the 4 deviations from the debrief table, formatted using the flight log's `### {Title}` / Planned / Actual / Reason structure
- [x] Flight 03 log Anomalies section has at least the Concourse offline and regex bug entries
- [x] All 11 mission success criteria are individually assessed — each either checked off with a brief inline note (e.g., `- [x] Criterion — met via Flight 02/03`) or noted as a known issue
- [x] No source code files modified (documentation-only leg)

## Verification Steps

- Read CLAUDE.md and confirm Testing section is present with all required content
- Read flight 03 log and confirm sections are populated
- Read mission.md and confirm all criteria are addressed
- Run `git diff --name-only` to confirm only .md files changed

## Implementation Guidance

1. **Add Testing section to CLAUDE.md** — insert after the Conventions section:
   - `THE_ONE_TEST_URL` env var (default `http://localhost:8484`)
   - `@pytest.mark.live` marker for AIAT tests
   - `pytest -m live tests/test_aiat.py` to run live tests
   - Unit tests run by default (`pytest tests/`), AIAT excluded via `addopts`
   - FakeLLM/StubTool pattern in `tests/conftest.py` for deterministic testing
   - Add `pytest -m live tests/test_aiat.py` to the Commands section

2. **Backfill flight 03 log** — populate from debrief content:
   - **Decisions**: Leg 4/5 executed out of order (decided they were independent, no impact on correctness)
   - **Deviations**: Adapt the 4 rows from the debrief's Deviations table into the flight log's `### {Title}` / Planned / Actual / Reason format
   - **Anomalies**: `extract_tool_calls()` regex bug (discovered in leg 01, resolved by removal); Concourse offline during leg 06 verification

3. **Audit mission success criteria** — check each against codebase:
   - Read through each criterion, verify against actual code/docs
   - Check off met criteria with `[x]`
   - Note any unmet criteria inline

## Edge Cases

- **Criteria that are "mostly met"**: If a criterion is functionally met but could be argued as incomplete, check it off and add a brief note. The debrief is the place for nuanced assessment.

## Files Affected

- `CLAUDE.md` — Add Testing section
- `missions/01-structural-foundation/flights/03-test-infrastructure-and-ci/flight-log.md` — Backfill Decisions, Deviations, Anomalies
- `missions/01-structural-foundation/mission.md` — Check off success criteria

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (no source changes, but confirm tests still pass)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
