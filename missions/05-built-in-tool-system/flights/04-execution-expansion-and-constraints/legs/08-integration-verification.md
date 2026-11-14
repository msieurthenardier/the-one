# Leg: 08-integration-verification

**Status**: landed
**Flight**: [Execution Expansion & Constraints](../flight.md)

## Objective

Final autonomous leg before the batch commit. Run the full unit + browser + AIAT suites, execute the F4 regression sweeps from the flight spec's Verification section, refresh `agents.md` and `CLAUDE.md` to reflect the F4 surface (17 tools, 5 constraint types, env-allowlist invariant, trip-wire framing, PTY session lifecycle, uvicorn-restart-after-source-change note), and append any small-model artifacts surfaced by the HAT to mission Known Issues. Mark mission-level Open Questions resolved for F4-assigned items.

## Context

- **L1a-L7 landed** (uncommitted). HAT cleared all 10 scenarios with no inline fixes; one orchestration finding (uvicorn cache) recorded in flight log Anomalies.
- **No new code in this leg** — verification, documentation refresh, and mission-level housekeeping only.
- **Mission Open Questions assigned to F4** (per mission.md):
  - "Interactive shell session lifecycle: session addressing (per-agent, per-conversation, per-explicit-handle), TTL, max concurrent sessions per agent, what happens to a session when the agent's turn ends. Resolved in Flight 4 design." — RESOLVED via Decisions 4, 5.
- **Pre-existing CSS-token red** (`tests/test_token_definitions.py::test_every_var_reference_is_defined`) is OUT of scope; deselect throughout.
- **Browser tests** were skipped during L6 implementation due to Playwright-binary env issue. L8 attempts them; if they fail for env reasons (not F4 regressions), document and accept.
- **AIAT live smoke**: `pytest -m live tests/test_aiat.py` if the live mark is configured. If not available in the dev container, accept and note.

## Inputs

- All F4 source code (L1a-L6).
- All F4 test code.
- `agents.md`, `CLAUDE.md` — top-level project docs.
- `Makefile` — knows `test-unit`, `test-browser`, possibly `test-aiat`.
- `mission.md` for Open Questions to mark resolved.

## Outputs

- **No source code changes**.
- `agents.md` updated to reflect:
  - Tool count: 17 (was 13 in F3).
  - Five constraint types: path-scope (F3), read-size cap (F3), output cap (F4), timeout caps (F4), command denylist (F4), URL/host scope (F5 — note "future").
  - Env-allowlist invariant: 8-key hardcoded allowlist (`PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ`) for all 3 execution call sites.
  - Trip-wire-not-fence threat model framing (F4 Decision 3).
  - PTY session lifecycle: per-agent isolation, idle-reap (default 5min TTL), max-concurrent (default 5), idle-mark prompt detection.
  - Uvicorn restart note for dev iteration.
- `CLAUDE.md` updated:
  - Tool Configuration Layer section gains `ExecutionConfig` shape + cross-Config dispatch description.
  - Note: container restart needed when changing tool source mid-iteration (uvicorn caches imports).
- `mission.md`:
  - Mark "Interactive shell session lifecycle" Open Question resolved (link to F4 Decisions 4, 5).
  - Append any small-model artifacts to Known Issues (none surfaced in HAT — but note section update if any).
- Flight log: append L8 final entry summarizing verification results.

## Acceptance Criteria

- [x] **Full unit suite green** (modulo pre-existing CSS-token red): `pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined` exits 0 with > 825 tests passing. *(825 passed, 1 skipped, 239 deselected — boundary; flagged in handoff)*
- [x] **F4 regression sweeps return expected counts**:
  - `grep -rn 'class ConstraintError' the_one/` → exactly **1** (in `the_one/tools/base.py`). ✓
  - `grep -rn 'os\.environ\.copy()' the_one/tools/` → **0**. ✓
  - `grep -rn 'env=None' the_one/tools/` → **0**. ✓
  - `grep -rn 'NarrowSuperset' the_one/tools/` → **2+** (`execution.py` + `filesystem.py` + `resolver.py`). ✓
- [x] **Browser test attempt** — Playwright Chromium binary missing (`Executable doesn't exist at /root/.cache/ms-playwright/chromium_headless_shell-1217/...`); pre-existing env gap, documented and accepted.
- [x] **AIAT live smoke attempt** — 4 fail / 2 pass; failures all keyed on default agent's missing `provider_config_id`; pre-existing env gap, documented.
- [x] `agents.md` reflects F4: 17 tools, 5 constraint types, env-allowlist invariant, trip-wire framing, PTY session lifecycle, uvicorn-restart note. Verified by sanity grep for the new tool names.
- [x] `CLAUDE.md` reflects F4: `ExecutionConfig` + cross-Config dispatch in the Tool Configuration Layer section; uvicorn-restart subsection.
- [x] `mission.md` Open Questions: "Interactive shell session lifecycle" marked resolved (F4 Decisions 4 + 5).
- [x] Flight log: L8 entry appended above L7 (newest first).

## Verification Steps

```bash
# Unit suite
docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined 2>&1 | tail -5

# F4 regression sweeps
echo "=== ConstraintError defined sites ==="
docker exec the-one grep -rn 'class ConstraintError' the_one/

echo "=== os.environ.copy() uses ==="
docker exec the-one grep -rn 'os\.environ\.copy()' the_one/tools/ || echo "(none)"

echo "=== env=None at tool call sites ==="
docker exec the-one grep -rn 'env=None' the_one/tools/ || echo "(none)"

echo "=== NarrowSuperset uses ==="
docker exec the-one grep -rn 'NarrowSuperset' the_one/tools/

# Browser tests
cd ~/projects/the-one && make test-browser 2>&1 | tail -20 || echo "browser-test-failed"

# AIAT (if available)
docker exec the-one pytest -m live tests/test_aiat.py -x -q 2>&1 | tail -5 || echo "aiat-live-not-available"
```

## Implementation Guidance

1. **Run the verification suite** first to surface any regressions before doc updates.

2. **Update `agents.md`**:
   - Read current `agents.md`.
   - Update tool count and category list.
   - Add a "Constraint surface" subsection naming the 5 types and pointing to `ExecutionConfig` for the per-tool defaults.
   - Add a "Subprocess environment" subsection with the 8-key allowlist.
   - Add a "Threat model" note: trip-wire framing (Decision 3).
   - Add a "PTY session lifecycle" subsection: per-agent isolation, default TTL/cap.
   - Add a "Dev iteration" note: restart container after tool source changes (uvicorn caches imports).

3. **Update `CLAUDE.md`**:
   - Find the Tool Configuration Layer section (or equivalent).
   - Add `ExecutionConfig` shape (timeout default/max, output cap, command denylist, pty TTL/cap).
   - Add cross-Config dispatch one-liner: tools may declare `Requires = (FilesystemConfig,)` to receive the resolved fs config via `cross_configs`.
   - Add the uvicorn-restart note to the dev workflow section.

4. **Update `mission.md`**:
   - Find the Open Questions section.
   - Mark "Interactive shell session lifecycle" question resolved (`- [x]`) with a brief reference to F4 Decisions 4, 5.

5. **Append L8 entry to flight log**.

6. **Mark this leg landed and check off in flight.md**. Set flight.md status to `landed`.

## Edge Cases

- **`grep -rn` may match in test files or docs** — narrow scopes to `the_one/` for the regression sweeps.
- **`env=None` may legitimately appear** in `the_one/platform/shell.py` and `the_one/platform/interpreter.py` SIGNATURES (default kwarg). The sweep targets `the_one/tools/` to catch missed-allowlist call sites only.
- **Browser tests may fail for env reasons unrelated to F4** (Playwright binary, headless Chrome, etc.). Document but don't block.
- **`agents.md` may have project-specific terminology** — preserve the project's voice; don't rewrite, just add F4-relevant sections.
- **`CLAUDE.md` is in the project's repo root** — verify location before editing.

## Files Affected

- `agents.md` — F4 surface refresh.
- `CLAUDE.md` — Tool Configuration Layer + dev iteration note.
- `missions/05-built-in-tool-system/mission.md` — mark Open Question resolved.
- `missions/05-built-in-tool-system/flights/04-execution-expansion-and-constraints/flight-log.md` — append L8 entry.
- `missions/05-built-in-tool-system/flights/04-execution-expansion-and-constraints/flight.md` — mark L8 leg + flight status to `landed`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests run (results documented even if some fail for env reasons)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Set FLIGHT status to `landed` in flight.md (this is the final leg)
- [x] Check off this leg in flight.md
- [x] Mark mission-level Open Questions resolved
- [ ] (Flight Director will commit + open PR after Reviewer pass)
