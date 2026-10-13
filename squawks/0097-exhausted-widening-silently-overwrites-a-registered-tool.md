# Squawk 0097: Exhausted collision-widening returns a colliding name, which silently overwrites a registered tool

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-22
**Completed**: 2026-10-13

## Report

When `compute_tool_names`' widening loop exhausts every length in
`_HASH_LENGTHS`, it returns the last computed set best-effort rather than
raising — deliberately, so the rest of the attachment still builds. But that set
may contain two identical names, and tool registration is a plain dict
assignment with no duplicate check. The second registration overwrites the
first, so an agent **silently loses one knowledge base's search tool** with no
error anywhere — no raise, no log at the registration site, nothing in the UI.

Astronomically unlikely to fire. Trivially cheap to make loud. The failure mode
is silence, which is what makes it worth closing rather than tolerating.

## Evidence

- `the_one/knowledge/tool_provider.py:202-205` — "Exhausted widening —
  astronomically unlikely … Best-effort: return the last computed set rather
  than raising", returning a possibly-colliding mapping.
- `the_one/tools/base.py:189` — `self._tools[tool.name] = tool`, an unguarded
  dict assignment: last writer wins, silently.

## Corrective Action

In `the_one/knowledge/tool_provider.py::compute_tool_names`, the exhausted-widening
path still returns the best-effort set, but first groups the final names and logs
one ERROR per colliding name, naming every colliding kb_id and the shared tool
name. ERROR (not WARNING) because a tool is silently lost. `ToolRegistry` and the
best-effort return are untouched. Original plan:

Make the exhausted-widening path loud — a WARNING/ERROR naming both colliding
kb_ids at the point the colliding set is returned. Scoped to that path; this
squawk does **not** change `ToolRegistry.register`'s general contract, which
other callers depend on.

## Verification

Added `tests/test_kb_tool_provider.py::TestComputeToolNames::test_exhausted_widening_logs_error_naming_colliding_ids`
(discriminator monkeypatched to collapse at every length; asserts one ERROR via caplog
naming both colliding ids and not an unrelated one). Ran
`PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_kb_tool_provider.py -x --timeout 30`:
37 passed. With the source change stashed, the new test fails (1 failed, 14 passed).
`ruff check` and `ruff format --check` clean. Stash list empty afterward.

Original plan: Force the collision the way the Mission 24 Architect did — monkeypatch the
discriminator to collapse at every length — and assert the diagnostic fires.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.
