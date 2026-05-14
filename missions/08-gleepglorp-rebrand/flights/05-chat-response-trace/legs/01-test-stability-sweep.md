# Leg: test-stability-sweep

**Status**: completed
**Flight**: [Chat Response Trace](../flight.md)

## Objective

Eliminate the chronic test-suite hangs that have been bleeding into every flight since F1 — first by isolating the test process from the live container's SQLite database (the root cause of the broad-pytest hang documented across F1-F4 debriefs), then by sweeping every test in the tree individually with a 30s host-side timeout to catalog pass / fail / hang / error and quarantining (with documented Known Issues) anything that cannot be fixed inside the per-symptom-class investigation budget.

## Context

- **Flight design pre-commits**: tests run serial against the shared `the-one` container; parallelism is at the TRIAGE-ANALYSIS layer only (agents reasoning about different hangs simultaneously), never at test invocation. Per-symptom-class investigation budget (5 minutes per distinct hang signature, NOT per-test). New `pytest.mark.skip` markers capped at ≤5 above F4's 35-skipped baseline; escalate to operator if exceeded.
- **Root cause hypothesis (architecturally identified during flight planning)**: `the_one/config.py:19` sets `data_dir: Path = Path.home() / ".the-one"` — defaults to `/root/.the-one` inside the container. The live uvicorn process running in the `the-one` container holds `/root/.the-one/the-one.db` open in WAL mode. When pytest runs via `docker exec the-one pytest …`, it inherits the same `$HOME` and `THE_ONE_DATA_DIR` (env unset → default) → tests construct a `Settings()` instance pointing at the live DB → SQLite WAL contention → indefinite wait on the lock. `tests/browser/conftest.py:113-128` already addresses this for browser tests by setting `env["THE_ONE_DATA_DIR"] = str(data_dir)` on each subprocess spawn, but the broad pytest run (unit + integration tests that import `the_one` directly) has no such isolation.
- **Known hanger evidence pre-L01**:
  - `tests/browser/test_flow_provider_setup.py:22` — module-skipped with reason `"M08 F4 KI: hangs under post-Leg-02 markup; root cause unidentified"`
  - `tests/browser/test_flow_agent_crud.py:23` — module-skipped with reason `"M08 F4 KI: hangs under post-Leg-02 markup; root cause unidentified"`
  - F1 debrief: 17-minute hang on `futex_wait_queue` during broad pytest run; SQLite WAL contention identified but not fixed
  - F2-F4 debriefs: every flight ran narrow-gate substitute (`pytest tests/ -m 'not browser and not pixel'` substituted by per-module test runs); broad-suite "Not attempted" in test metrics tables
- **Existing skip topology** (re-derive baseline at leg-start; leg-design-time approximate counts):
  - ~25 lines across `tests/` matching `pytest.mark.skip` or `pytest.mark.skip(...)` or `pytestmark = pytest.mark.skip` (PLUS ~13 separate `pytest.mark.skipif` for platform/bwrap guards — `skipif` is NOT counted toward the leg's ≤5 cap because it's conditional, not unconditional quarantine)
  - Browser suite per F4 debrief (`missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-debrief.md`, test-metrics table): 315 passing / 35 skipped (the 35 include 5 module-skipped from F4 + miscellaneous platform/marker skips)
  - Pixel suite per F4: 10 passing / 2 failing (the 2 are `test_snapshot_chat_with_messages` × dark + light, gated by mission KI #1 — `app_with_agent` `.session-agent-badge` race; will be addressed in Leg 04, NOT here)
  - **Action for the implementing agent**: capture the EXACT pre-leg count via the same grep used for the cap (see Acceptance #4) BEFORE making any change; record it as the "L01 pre-sweep baseline" in the flight log. The leg's diff-against-`main` cap uses this captured baseline as the reference point, NOT the approximate counts here.
- **Flight director note**: This leg's success unlocks meaningful broad-suite measurement for L02's codec/round-trip + WebSocket integration tests. The flight verification step "the broad pytest runs to completion" is L01's headline deliverable.

## Inputs

What exists before this leg runs:

- Container `the-one` running and reachable via `docker exec` (verify with `docker exec the-one true && docker ps --filter name=the-one --format '{{.Status}}'`)
- Branch `flight/05-chat-response-trace` checked out, working tree clean except for untracked flight planning artifacts under `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/`
- `tests/conftest.py` (`the_one/tests/conftest.py:205 LOC`) — session-level pytest configuration, currently sets `THE_ONE_TEST_MODE=1` in `pytest_configure` but does NOT isolate `THE_ONE_DATA_DIR`
- `tests/browser/conftest.py:113-128` — already isolates `THE_ONE_DATA_DIR` per browser-test subprocess via `tmp_path` (this is the pattern to mirror at the broader suite level)
- `the_one/config.py:8-33` — `Settings` class with `data_dir` field, `env_prefix = "THE_ONE_"` (so `THE_ONE_DATA_DIR` env var controls it)
- `pyproject.toml:51-67` — pytest config with `addopts = "-m 'not live and not browser and not pixel and not requires_bwrap' --import-mode=importlib"` and `pythonpath = ["tests"]`
- F4 baseline test metrics (from `missions/08-gleepglorp-rebrand/flights/04-studio-polish/flight-debrief.md`):
  - Narrow gate (4 modules): 58 in 0.87s
  - WCAG audit: 47 in 0.05s
  - Broad pytest: hung (never measured cleanly)
  - Browser suite: 315 passed, 35 skipped, ~266s
  - Pixel suite: 10 passed, 2 failed (KIs), 27.12s

## Outputs

What exists after this leg completes:

- Broad pytest (`-m "not browser and not pixel"`) runs to completion (≤ 5 minutes wall clock; specific number captured) — first clean broad-suite measurement since F1
- `tests/conftest.py` modified to isolate `THE_ONE_DATA_DIR` to a session-scoped temp directory for non-browser tests
- Triage matrix appended to flight log: every test file in `tests/` enumerated with status `pass | fail | hang | error | skip` per its current behavior; per-symptom-class investigation notes for any hang found
- Up to 5 new `pytest.mark.skip` markers with precise `reason="…"` strings; corresponding new Known Issue entries appended to mission `08-gleepglorp-rebrand/mission.md` under the existing `## Known Issues` section (semantically: the project's mission-level "discovered during execution" enumeration — leave the existing KI authoring style intact)
- Browser suite verified still ≥ 315 passing on rerun
- Test-stability baseline captured for L02-L04 to validate against
- Flight log updated with L01 entry: status `landed`, triage matrix, root-cause notes, new skip count vs F4 baseline

## Acceptance Criteria

- [ ] **Broad pytest completes**: `timeout 600 docker exec the-one pytest tests/ -m "not browser and not pixel" --timeout=30 -x -q --tb=short 2>&1 | tail -20` exits non-zero only if real test failures, NOT if the broad suite hangs. The exit must occur within 600 seconds and the final line must be a pytest summary (e.g. `=== N passed, M skipped in T.Ts ===`), NOT a SIGTERM or hang stack trace.
- [ ] **Root cause isolation landed**: `tests/conftest.py` sets `THE_ONE_DATA_DIR` to an isolated temp path before any test in the non-browser suite constructs a DB connection. The isolation must NOT affect browser tests (their per-subprocess isolation via `tests/browser/conftest.py:113-128` already works correctly).
- [ ] **Every test file in `tests/` triaged**: the triage matrix in the flight log enumerates every `tests/**.py` file (both top-level and `tests/browser/`) with one of these statuses: `pass-all | partial-fail | hang | error | all-skip | mixed`. The matrix shows per-file evidence (counts + a representative test name for non-pass states).
- [ ] **New skip cap respected**: count of NEWLY-ADDED unconditional skips in this leg is ≤ 5. `skipif` does NOT count toward the cap (it's a conditional platform/dependency guard, not a quarantine). Measure via two greps to avoid the `skip`/`skipif` prefix collision:
  ```bash
  # Count newly-added @pytest.mark.skip (NOT skipif), tolerating a leading @:
  ADDED_DECORATOR=$(git diff main -- 'tests/**' | grep -cE '^\+\s*@?pytest\.mark\.skip(\(|\s|$)')
  # Count newly-added module-level pytestmark = pytest.mark.skip(...):
  ADDED_PYTESTMARK=$(git diff main -- 'tests/**' | grep -cE '^\+\s*pytestmark\s*=\s*pytest\.mark\.skip\b')
  echo "$((ADDED_DECORATOR + ADDED_PYTESTMARK))"
  ```
  If the sum > 5, leg halts and escalates via `[BLOCKED:skip-cap-exceeded]` BEFORE signaling `[HANDOFF:review-needed]`.
- [ ] **Acceptance #4 vs #6 relationship**: any new browser-suite skip counts toward BOTH the leg-wide cap (#4) and the browser-suite +5 cap (#6). They are not independent budgets — #6 is a subset constraint of #4 restricted to `tests/browser/`.
- [ ] **Every new skip has a precise `reason=` string AND a mission KI entry**: each new skip's `reason=` cites the symptom (e.g. `"hangs in fixture setup; SQLite WAL contention against /tmp/the-one-test-XXXXX/the-one.db — pre-existing, see M08 KI"`) and the mission's `## Known Issues` section gains a matching entry per the mission's existing KI authoring convention.
- [ ] **Browser-suite baseline preserved**: `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5` reports ≥ 315 passing. Skip count may grow by ≤ 5 vs F4's 35-skipped baseline. No new hangs.
- [ ] **Narrow gate still clean**: `timeout 60 docker exec the-one pytest tests/test_config.py tests/test_db_codec.py tests/test_agent.py tests/test_agent_context.py --timeout=30 -q 2>&1 | tail -3` reports the F4-baseline 58 passing in roughly 0.87s ± 0.3s (no significant slowdown introduced).
- [ ] **Per-symptom-class budget respected**: any hang whose signature matches another already-investigated hang in this leg does NOT consume a fresh 5-minute investigation budget. Triage matrix notes "same root cause as [previous hang]" and either fixes the class or quarantines all members in one batch.
- [ ] **Triage matrix is parsable**: the flight log entry includes a markdown table with columns `File | Tests | Status | Notes`. A reader scanning the table can identify in <30s which files are clean, which are quarantined, and where to look for hangs.
- [ ] **No source-code changes outside `tests/`, `tests/browser/`, and `pyproject.toml`/`tests/conftest.py`** unless the change is a confirmed product-bug fix surfaced during triage (in which case it is documented in the triage matrix with rationale). Specifically: NO chat surface changes, NO `the_one/interfaces/web/` changes, NO `the_one/db/codec.py` changes — those land in L02/L03.
- [ ] **Live DB untouched**: `md5sum /root/.the-one/the-one.db` inside the container matches its pre-leg value (modulo legitimate live-container traffic during the sweep window — if non-zero, the implementing agent confirms each modification matches a known live-container event, NOT a test bleed). If the md5 changed and there's no plausible live-container source, the isolation has a bug and the leg halts for diagnosis.

## Verification Steps

How to confirm each criterion is met:

1. **Broad pytest completion**:
   ```bash
   timeout 600 docker exec the-one pytest tests/ -m "not browser and not pixel" --timeout=30 -x -q --tb=short 2>&1 | tail -20
   echo "EXIT_CODE=$?"
   ```
   Expected: final line matches `=== N passed.*in T.Ts ===` AND `$EXIT_CODE` ∈ {0, 1, 2, 5} (pytest exit codes for pass / failures / interrupted / no-tests). NOT 124 (timeout) and NOT 143 (SIGTERM).

2. **Root cause isolation present**:
   ```bash
   grep -n "THE_ONE_DATA_DIR" tests/conftest.py
   ```
   Expected: ≥ 1 match showing the isolation mechanism (env var assignment in `pytest_configure` or session-scoped autouse fixture).

3. **Triage matrix completeness**:
   ```bash
   # Every test file is in the matrix (regex tolerates digits, dots, hyphens):
   diff <(find tests -maxdepth 2 -name 'test_*.py' -not -path '*/__pycache__*' | sort) \
        <(grep -oE 'tests/[a-zA-Z0-9_/.-]+\.py' missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md | sort -u)
   ```
   Expected: no diff output (every test file appears in the flight log triage matrix).

4. **New skip cap** (excludes `skipif` via tightened regex):
   ```bash
   ADDED_DECORATOR=$(git diff main -- 'tests/**' | grep -cE '^\+\s*@?pytest\.mark\.skip(\(|\s|$)')
   ADDED_PYTESTMARK=$(git diff main -- 'tests/**' | grep -cE '^\+\s*pytestmark\s*=\s*pytest\.mark\.skip\b')
   echo $((ADDED_DECORATOR + ADDED_PYTESTMARK))
   ```
   Expected: integer ≤ 5.

5. **Every new skip has reason + KI**: visual inspection — for each new skip added in the diff, find a corresponding `reason="…"` string AND a new bullet under `mission.md`'s `## Known Issues` section with overlapping wording. (`grep -A1 'pytest.mark.skip' tests/` shows skip + reason context; cross-reference against `mission.md`.)

6. **Browser suite preserved**:
   ```bash
   timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -3
   ```
   Expected summary line shows passed count ≥ 315 and skipped count ≤ 40.

7. **Narrow gate preserved**:
   ```bash
   timeout 60 docker exec the-one pytest tests/test_config.py tests/test_db_codec.py tests/test_agent.py tests/test_agent_context.py --timeout=30 -q 2>&1 | tail -3
   ```
   Expected summary line shows 58 passed in ≤ 2.0s (widened tolerance from F4's 0.87s baseline to account for container-load variance + isolation-fixture overhead).

8. **No out-of-scope source changes**:
   ```bash
   git diff main --name-only | grep -vE '^(tests/|pyproject\.toml|missions/)' | head -5
   ```
   Expected: empty output (no changes outside the allowed scope).

9. **Live DB md5 verification** (Acceptance — live DB untouched):
   ```bash
   docker exec the-one md5sum /root/.the-one/the-one.db | awk '{print $1}' > /tmp/L01-live-db-md5-after.txt
   diff /tmp/L01-live-db-md5-before.txt /tmp/L01-live-db-md5-after.txt
   ```
   Expected: no diff (md5 unchanged) — OR — if diff, the agent inspects `docker logs the-one --since "<pre-leg-timestamp>"` and confirms each modification corresponds to a legitimate live-container event (user-initiated request, scheduled task), not a test bleed.

## Implementation Guidance

1. **Verify environment + capture pre-leg state**
   - `docker ps --filter name=the-one --format '{{.Status}}'` — must show `Up …`. If not running, `make up` first.
   - `git status` — confirm `flight/05-chat-response-trace` branch with only the planning artifacts as untracked.
   - Capture live-DB pre-leg md5 (for Acceptance "Live DB untouched" verification):
     ```bash
     docker exec the-one md5sum /root/.the-one/the-one.db | awk '{print $1}' > /tmp/L01-live-db-md5-before.txt
     date -Iseconds > /tmp/L01-pre-leg-timestamp.txt
     ```
   - Capture pre-leg test baseline:
     ```bash
     timeout 60 docker exec the-one pytest tests/test_config.py tests/test_db_codec.py tests/test_agent.py tests/test_agent_context.py --timeout=30 -q 2>&1 | tail -3
     timeout 60 docker exec the-one pytest tests/test_design_tokens_a11y.py --timeout=30 -q 2>&1 | tail -3
     ```
   - Capture pre-leg skip count (the baseline against which the ≤5 cap is measured):
     ```bash
     PRE_DECORATOR=$(grep -rEn '^\s*@?pytest\.mark\.skip(\(|\s|$)' tests/ 2>/dev/null | wc -l)
     PRE_PYTESTMARK=$(grep -rEn '^\s*pytestmark\s*=\s*pytest\.mark\.skip\b' tests/ 2>/dev/null | wc -l)
     echo "pre-leg skip baseline (decorator + pytestmark): $((PRE_DECORATOR + PRE_PYTESTMARK))"
     ```
   - Append captured baselines (live-DB md5, test pass counts, skip baseline) to the flight log under the new `### L01 Pre-Sweep Baseline` subsection.

2. **Diagnose and fix the SQLite WAL root cause** (do this BEFORE the sweep — every other test's status depends on it)
   - Read `tests/conftest.py:1-50` and `tests/browser/conftest.py:113-180` to understand the existing isolation pattern for browser tests.
   - Read `the_one/config.py:1-33` to confirm `Settings` reads `THE_ONE_DATA_DIR` from env (via `env_prefix = "THE_ONE_"`). Confirm critical fact: line 33 instantiates `settings = Settings()` at module-import time — so any env-var override MUST be set before the first import of `the_one.config` in the test process.
   - **Implementation: extend the existing `pytest_configure` hook in `tests/conftest.py:19-41`** (which already sets `THE_ONE_TEST_MODE=1`):
     - Verified during design review: `tests/conftest.py:12` imports `from the_one.llm.base import LLMProvider, Message`; that chain does NOT transitively pull in `the_one.config`. So `pytest_configure` is the latest hook that still fires before any test or production-code import touches `the_one.config.settings`.
     - Pattern to add inside `pytest_configure`:
       ```python
       import tempfile, os
       os.environ.setdefault(
           "THE_ONE_DATA_DIR",
           tempfile.mkdtemp(prefix="the-one-pytest-"),
       )
       ```
     - `setdefault` preserves CI / browser-subprocess overrides (browser tests already set their own per-test isolated `THE_ONE_DATA_DIR` via `tests/browser/conftest.py:127`).
     - Session-persistent tmp dir (one path for the whole pytest run) is the right choice — matches the live-container pattern; tests that leave cruft behind are bugs not features.
   - **Why NOT alternatives** (documented in flight log for posterity):
     - Session-scoped autouse fixture: FIRES TOO LATE. Test modules are imported before fixtures run; if any test module does `from the_one.config import settings` at module scope, the singleton at `config.py:33` is already frozen pointing at `/root/.the-one`.
     - `pyproject.toml` `env = ["THE_ONE_DATA_DIR=…"]`: requires `pytest-env` (not in `dev` extras at `pyproject.toml:36`); adds a dep cost without benefit over `pytest_configure`.
     - `tests/conftest.py` module-level set (above the `from the_one.llm.base import …` line): works but is fragile — anyone reordering imports for ruff/isort could break the invariant silently. `pytest_configure` is the documented hook for this; prefer it.
   - **Validate the fix without breaking the live container**: run one DB-touching test against the live container and confirm:
     ```bash
     # Run a test that constructs a DB connection:
     timeout 30 docker exec the-one pytest tests/test_db_codec.py --timeout=30 -q 2>&1 | tail -5
     # Inspect: did the test write to the isolated tmp DB?
     docker exec the-one bash -c 'ls -la /tmp/the-one-pytest-*/the-one.db 2>/dev/null && echo "isolated DB exists"'
     # Inspect: did the live DB stay untouched (mtime)?
     docker exec the-one stat -c '%Y' /root/.the-one/the-one.db
     ```
     Capture the mtime BEFORE and AFTER; they should be equal (or differ only because of legitimate live-container activity). DO NOT stop the live container during this step — `docker exec the-one` requires it running.
   - Commit-readiness: this fix alone should make the broad pytest hang go away. The sweep proves it.

3. **Enumerate the test tree**
   ```bash
   # Top-level (default + non-browser markers):
   docker exec the-one pytest --collect-only -q tests/ -m "not browser and not pixel and not live" 2>&1 | grep -E "tests/.*\.py" | sort -u > /tmp/L01-tests-broad.txt
   # Browser:
   docker exec the-one pytest --collect-only -q tests/browser/ -m browser 2>&1 | grep -E "tests/.*\.py" | sort -u > /tmp/L01-tests-browser.txt
   # Pixel:
   docker exec the-one pytest --collect-only -q tests/browser/ -m pixel 2>&1 | grep -E "tests/.*\.py" | sort -u > /tmp/L01-tests-pixel.txt
   wc -l /tmp/L01-tests-*.txt
   ```
   Capture the total test count per suite into the flight log.

4. **Run the broad pytest sweep — the headline goal**
   - After the isolation fix is in place:
     ```bash
     timeout 600 docker exec the-one pytest tests/ -m "not browser and not pixel" --timeout=30 -x -q --tb=short 2>&1 | tee /tmp/L01-broad-sweep.txt | tail -30
     ```
   - If the sweep completes (success or test failures, but not timeout/hang): capture the pass/fail counts. THIS IS THE FLIGHT'S HEADLINE METRIC.
   - If the sweep still hangs: re-examine the isolation fix. The hypothesis may be wrong; check for OTHER shared resources (e.g. `the_one/db/connection.py` global singletons that persist across test imports).
   - If real test failures appear: triage each individually using `timeout 30 docker exec the-one pytest <file>::<test> -x -q --tb=short`. Fix tractable issues in place; quarantine pre-existing issues with skip + KI.

5. **Run per-file sweep for granular triage**
   - For each file in `/tmp/L01-tests-broad.txt` + `/tmp/L01-tests-browser.txt`, scale the outer host-side timeout to the file's test count:
     ```bash
     # Count tests in the file first, then size the budget:
     NUM_TESTS=$(docker exec the-one pytest <file> --collect-only -q 2>&1 | grep -cE '::test_')
     BUDGET=$((NUM_TESTS * 30 + 30))
     timeout $BUDGET docker exec the-one pytest <file> --timeout=30 -q --tb=line 2>&1 | tail -3
     ```
   - This composes correctly: outer `timeout` is SIGKILL-able from the host; inner `--timeout=30` is per-test; budget scales linearly with test count + 30s slack for collection/teardown.
   - For files that hang or fail unexpectedly: drop to per-test invocation with `<file>::<test>` and a strict 30s timeout to identify the specific offender.
   - Build the triage matrix as you go — append rows to the flight log under a new `### L01 Triage Matrix` subsection.

6. **Per-symptom-class investigation**
   - When a hang is found: compare its symptom to already-catalogued hangs in the triage matrix.
   - If the symptom matches: note "same class as `<previous-test>`; quarantining batch" and apply the same fix-or-skip decision.
   - If the symptom is NEW: open a 5-minute investigation window — `docker exec the-one py-spy dump --pid $(docker exec the-one pgrep -f pytest)` for live stack traces (note: `py-spy` may not be installed; alternative: `docker exec the-one strace -p <pid>` for syscall trace).
   - If root-caused in budget: fix in place. If not: quarantine with `pytest.mark.skip(reason="…")` + KI entry + symptom-class label.

7. **Triage `test_flow_provider_setup.py` and `test_flow_agent_crud.py`** (F4 debrief explicit recommendation)
   - These are already module-skipped at `tests/browser/test_flow_provider_setup.py:22` and `tests/browser/test_flow_agent_crud.py:23`. Read each file briefly.
   - Use `Edit` to temporarily comment out the `pytestmark = pytest.mark.skip(...)` line in each file (prefix with `# `); run `timeout 60 docker exec the-one pytest tests/browser/test_flow_provider_setup.py --timeout=30 -q --tb=short` to see if the SQLite WAL fix resolved the hang. Avoid `git stash` for this dance — it adds error surface in an autonomous agent context.
   - If the hang reproduces and is a Playwright-level issue (vs the SQLite WAL fix already resolving it): restore the comment-out → original line, leave the skip + KI in place, note the investigation outcome in the triage matrix.
   - If the SQLite WAL fix DID resolve the hang: delete the `pytestmark` line outright, run the file end-to-end to confirm full pass, document the resolution in the triage matrix and update mission KI #4's status. (This may net-DECREASE the skip count — that's good and doesn't violate the ≤5 ADDED cap.)

8. **Update mission KIs**
   - For each new `pytest.mark.skip` added: append a `- [ ] **<test>** — <reason>. Symptom class: <class>. Investigation outcome: <outcome>. Suggested follow-up: <follow-up>.` entry to `missions/08-gleepglorp-rebrand/mission.md`'s `## Known Issues` section (matching the existing entry style).
   - If `test_flow_provider_setup` / `test_flow_agent_crud` are now passing post-isolation-fix: update mission KI #4's status to reflect partial closure (the 2 hangs resolved, the other 4 module-skipped files still pre-rebrand UX issues).

9. **Verify all acceptance criteria pass**
   - Run each verification step from the section above. Capture the output of each command into the flight log under `### L01 Verification Output`.
   - If any criterion fails: do NOT signal `[HANDOFF:review-needed]`. Diagnose and fix. The escalation path is "halt and ask operator" if blocked.

10. **Update flight log + leg artifact**
    - Append `### L01 — test-stability-sweep` entry with status `landed`, full triage matrix, root-cause writeup, new-skip count, post-leg test metrics, and any session notes.
    - Update this leg artifact's status to `landed` (header line at top).
    - Check off this leg in `flight.md` (the `Legs` checklist).
    - DO NOT commit. DO NOT update `flight.md` status to `landed` (this is leg 1 of 4, not the final leg).
    - Signal `[HANDOFF:review-needed]`.

## Edge Cases

- **The isolation fix breaks an existing test that depends on the live DB**: this is unlikely (tests should be hermetic) but possible. Mitigation: per-test triage will surface it. Fix by making the test hermetic (use `tmp_path` + explicit `THE_ONE_DATA_DIR` override), NOT by re-coupling to the live DB.
- **A "hang" is actually a slow test that completes just past 30s**: bump that specific test's timeout to 60s in the per-test invocation; if it completes, document as `slow but not hung` and consider adding a `@pytest.mark.slow` marker (do NOT count toward the ≤5 skip cap; this is a non-skip mark).
- **Multiple tests in the SAME file hang at different points**: file-level skip is heavier than test-level skip. Default to test-level skips first; escalate to file-level only if every test in the file hits the same symptom class.
- **Browser tests start hanging after the isolation fix**: the per-subprocess isolation in `tests/browser/conftest.py:113-128` should be unaffected. If browser tests do hang: confirm the autouse fixture is properly scoped (`tests/conftest.py` autouse fixtures cascade to `tests/browser/conftest.py` subtests). If there's a conflict, scope the unit-suite isolation fixture to `tests` (not `tests/browser`) explicitly via `autouse=True` with a `request.node.get_closest_marker("browser") is None` guard.
- **`py-spy` or `strace` not available in container**: fall back to `docker exec the-one cat /proc/<pid>/stack` (if `/proc` is readable) or to Python-side debugging via `PYTHONFAULTHANDLER=1` + `kill -SIGSEGV <pid>` to trigger a stack dump.
- **The 5-skip cap is exceeded**: HALT. Do NOT signal `[HANDOFF:review-needed]`. Update the flight log with the count and the reason for each proposed skip, then surface a `[BLOCKED:reason]` signal asking the operator whether to raise the cap or descope the leg.
- **A "hang" turns out to be a real product bug from F1-F4**: this triggers the flight's Adaptation Criteria "Divert if" — a product bug from prior flights does NOT belong in L01's test-stability scope. Quarantine with a skip + KI marked `BUG: deferred to maintenance flight` and continue the sweep. Do NOT fix the product bug in L01.

## Files Affected

- `tests/conftest.py` — extend the existing `pytest_configure` hook (line 19-41) with the `THE_ONE_DATA_DIR` `os.environ.setdefault` per Implementation Guidance step 2; expected ~5-10 LOC delta
- `pyproject.toml` — no changes expected. The rejected `pytest-env` + `env = […]` alternative is documented in step 2's "Why NOT alternatives" subsection for posterity, but is NOT implemented.
- `tests/**.py` — up to 5 new `pytest.mark.skip` markers (each with `reason="…"`); plus potentially restoration of `test_flow_provider_setup.py` / `test_flow_agent_crud.py` module-skips if SQLite WAL fix resolves their hangs
- `missions/08-gleepglorp-rebrand/mission.md` — append entries to `## Known Issues` section for each new skip (and update KI #4 status if F4 hangs are resolved)
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md` — append `### L01 Pre-Sweep Baseline`, `### L01 Triage Matrix`, `### L01 Verification Output`, and a Leg Progress entry
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight.md` — check off `test-stability-sweep` in the Legs list
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/legs/01-test-stability-sweep.md` — update status header to `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (run every verification step; capture output to flight log)
- [ ] Tests passing (broad pytest completes; browser suite ≥ 315 passing; narrow gate clean)
- [ ] Update flight-log.md with leg progress entry (triage matrix + verification output + session notes)
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed`; the batch review at flight close transitions it to `completed`
- [ ] Check off this leg in flight.md
- [ ] Mission KIs updated for any new skips or resolved-hangs status changes
- [ ] DO NOT commit (per agentic-workflow: review + commit are batched at flight close)
- [ ] Signal `[HANDOFF:review-needed]`

---

## Citation Audit

9 source-code citations verified against current code at leg design time (one drift caught by cycle-1 design review and corrected):

| Citation | Class | Notes |
|---|---|---|
| `the_one/config.py:8-33` (`Settings` class with `data_dir`, `db_path` properties) | OK | Verified — `data_dir: Path = Path.home() / ".the-one"` at line 19; properties at 22-30; module-level `settings = Settings()` at line 33 |
| `the_one/config.py:19` (`data_dir` default) | OK | Verified at line 19 |
| `the_one/config.py:33` (module-level `settings = Settings()` instantiation) | OK | Verified — this is the load-bearing fact behind why `pytest_configure` (not autouse fixture) is required |
| `tests/conftest.py:205 LOC` | OK | Verified — `wc -l tests/conftest.py` reports 205 |
| `tests/conftest.py:19-41` (`pytest_configure` hook setting `THE_ONE_TEST_MODE`) | OK | Verified — `pytest_configure` defined at line 19 with `setdefault` for `THE_ONE_TEST_MODE`; this is the hook to extend |
| `tests/conftest.py:12` (imports `from the_one.llm.base import LLMProvider, Message`) | OK | Verified — import chain confirmed by cycle-1 reviewer NOT to transitively touch `the_one.config`, making `pytest_configure` a viable env-injection point |
| `tests/browser/conftest.py:113-128` (`app_clean` fixture sets `THE_ONE_DATA_DIR`) | OK | Verified — `app_clean` defined at line 113; `env["THE_ONE_DATA_DIR"] = str(data_dir)` at line 127 |
| `tests/browser/test_flow_provider_setup.py:22` (module-skip) | OK | Verified — `pytestmark = pytest.mark.skip(reason="M08 F4 KI: hangs under post-Leg-02 markup; root cause unidentified")` at line 22 |
| `tests/browser/test_flow_agent_crud.py:23` (module-skip) | OK | Verified — same pattern at line 23 |
| `pyproject.toml:51-67` (pytest config block) | drift-repaired | Originally cited as `:43-65`; cycle-1 reviewer caught it. Corrected to `:51-67` after re-reading the file — `[tool.pytest.ini_options]` header is at line 51, block ends at line 67. |
| `pyproject.toml:36` (`dev` extras) | OK | Verified — `dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "pytest-timeout>=2.4", "ruff>=0.6", "playwright==1.58.0", "pytest-playwright>=0.5", "pillow>=10.0", "pixelmatch>=0.3", "asgi-lifespan>=2.0"]` at line 36; confirms `pytest-env` is NOT a current dep |

All citations OK or drift-repaired. Cycle-1 design review (recorded in flight log) corrected the `pyproject.toml` range and exposed the `pytest_configure`-vs-autouse-fixture issue that drove the Implementation Guidance rewrite.
