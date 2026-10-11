# Leg: verify-live-and-windows

**Status**: completed
**Flight**: [Agents Know the Time](../flight.md)

## Objective

Prove the flight in real environments:

- a live local model tells the time correctly, through the
  `agent-tells-the-time` behavior test;
- the packaged Windows build ships working zone data and formatters, shown by
  the frozen `the-one doctor` on the operator's Windows desktop reporting
  `time zones: OK`.

Fix forward anything small that either run turns up.

## Context

- Flight **DD10** (the Windows exit gate) and **DD11** (the behavior test's
  apparatus).
- The behavior test is run by the Flight Director with
  `/mission-control:behavior-test agent-tells-the-time`. That skill
  orchestrates its own Executor and Validator; no Developer is spawned for it.
- The Windows proof is run by a Developer through `scripts/windows_test_copy.py`
  (see `the_one/agents.md` "Windows test copy"):
  1. `snapshot --out`;
  2. `setup`;
  3. `freeze`;
  4. `doctor --frozen --data-dir <scratch under the root>`;
  5. `snapshot --compare`.

  `setup` and `freeze` run in the background. A first `setup` takes about 5.5
  minutes and a `freeze` about 1.5. The helper refuses ports 8484/8485 and the
  operator's data dir by construction. This leg launches no app; it only runs
  doctor.
- **Re-verify the external sessions at leg start** (a flight prerequisite):
  - Ollama: `curl -s localhost:11434/api/tags` lists `gpt-oss:20b` or
    `qwen3:30b`;
  - Windows interop: `cmd.exe /c ver` answers, and `windows_test_copy.py
    doctor-host` succeeds.

## Inputs

- Legs 1, 2a and 2b landed. `make gate` is green (leg 2b, AC9).
- The `tests/behavior/agent-tells-the-time.md` spec (draft).

## Outputs

- A behavior-test run log at `tests/behavior/agent-tells-the-time/runs/<ts>.md`,
  with a pass, and the spec's `Last Run` and `Status` lines updated.
- The frozen Windows doctor output, recorded in the flight log, with
  `time zones: OK` and `RESULT: PASS`, plus the snapshot compare result.
- Any fix-forward changes, with tests.
- The flight log: the leg entry.

## Acceptance Criteria

- [ ] **AC1.** Both external sessions are re-verified at leg start, and the
      result is recorded in the flight log.
- [ ] **AC2.** `/mission-control:behavior-test agent-tells-the-time` passes:
      all 8 steps, or every non-pass step has a recorded disposition that the
      Flight Director accepts as a model limitation, not a product defect. A
      run inside the 05:00-10:00 UTC window must note that the date checks
      could not tell the zones apart.
- [ ] **AC3.** The frozen Windows doctor prints `time zones: OK` and exits 0
      (`RESULT: PASS`). The flight log records:
  - the full gate list;
  - the detected Windows system zone name, or "none detected";
  - the tzdata version.
- [ ] **AC4.** `snapshot --compare` after the Windows session exits 0, or
      reports only allowed changes.
- [ ] **AC5.** Any defect either run reveals is fixed in this leg (with a
      unit test) if it is small and within the flight's DDs. Otherwise it is
      logged as a squawk, or raised to the operator. The run that found it is
      re-run after a fix.

## Verification Steps

- **AC1:**
  - `curl -s localhost:11434/api/tags`;
  - `cmd.exe /c ver`;
  - `.venv/bin/python scripts/windows_test_copy.py doctor-host`.
- **AC2:** the run log.
- **AC3, AC4:** the helper's printed output, copied into the flight log.

## Implementation Guidance

1. **Windows first.** It runs unattended in the background while the behavior
   test runs in parallel:

   ```
   snapshot --out <scratch>/pre.json
   setup
   freeze
   doctor --frozen --data-dir <root>\data-m28
   snapshot --compare <scratch>/pre.json
   ```

   Use `--root` defaults. If `doctor --frozen` exits 3 (hands-off: the
   operator is typing), wait and retry. Never fight the gate.
2. **The behavior test** needs a scratch dev instance on a port of 8490 or
   higher with a scratch data dir. It is started by the behavior-test skill's
   Executor per the spec's Preconditions.
3. **On any failure:** diagnose, fix with a test, re-run the failing check.

## Edge Cases

- **A PyInstaller freeze that misses tzdata files** shows as `time zones: FAIL`
  with a load error. Fix the spec's collection (DD8) and re-freeze.
- **A Windows host whose `tzlocal` returns no name** is still OK, because
  detection never fails the gate. Record it.
- **The model ignores the tool and the date line in step 2 or 4.** Per the
  flight's Adaptation Criteria, that is an operator conversation, not a fix
  forward.

## Files Affected

- `tests/behavior/agent-tells-the-time.md` (the `Last Run` and `Status`
  lines), plus its run log.
- Possibly `packaging/windows/the-one.spec` or `the_one/time_zones.py`, for a
  fix forward.
- The flight log.

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
