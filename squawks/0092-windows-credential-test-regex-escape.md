# Squawk 0092: a Windows-only test failure — `pytest.raises(match=)` given an unescaped Windows path

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-20
**Completed**: 2026-10-09

## Report

`tests/test_api_credential.py:390` passes a raw filesystem path as a **regex**:

```python
with pytest.raises(CredentialFileError, match=str(path)):
```

On POSIX that is harmless — the path's `/` separators mean nothing to the
regex engine. On Windows the separators are backslashes, so the path is parsed
as a pattern full of escape sequences and the test fails before it can assert
anything:

```
E   Failed: Invalid regex pattern provided to 'match': bad escape \T at position 10
```

The test is **correct about the behaviour it intends to pin** (that
`CredentialFileError` names the offending file). Only the matching mechanism is
wrong. The production code is not implicated.

**This runs in CI.** `tests/test_api_credential.py` is in
`ci/tasks/windows-tests.yml`'s curated Windows subset, so the Windows lane
carries this failure. Found during Mission 24 Flight 7 Leg 3's AC-1 worker
re-verification: **549 passed / 21 skipped / 2 xfailed / 1 failed**, the one
failure being this test. Everything else about the worker — choco toolchain,
the per-run venv, `pip install`, 572 tests collected — ran correctly, which is
what made it legible as a test bug rather than a worker problem.

## Evidence

- `tests/test_api_credential.py:385-391` — `match=str(path)` with no escaping
- `ci/tasks/windows-tests.yml` — lists `tests/test_api_credential.py` in the
  curated subset
- Worker run log (Flight 7 Leg 3, AC-1):
  `tests\test_api_credential.py:390: … E Failed: Invalid regex pattern provided
  to 'match': bad escape \T at position 10`

## Disposition

Qualified against the squawk gate: **one coherent item** ✅ (one unescaped
argument on one line); **no design decisions** ✅ (`re.escape` is the standard
answer, and the test's intent is unchanged); **bounded blast radius** ✅ (a
single test, no production code); **verifiable** ✅ (the existing test passes on
both platforms afterwards).

**Not folded into Flight 7 Leg 3.** That leg is chartered to measure, and its
Files Affected does not include `tests/test_api_credential.py`. Logged and
deferred per the flight workflow's out-of-scope-defect rule — the same
disposition as squawk 0091, filed earlier in the same flight.

**Worth checking at completion**: whether the `main` branch's Windows lane has
been carrying this failure, and for how long. The mission branch has no CI lane
(Concourse tracks `main`), so this flight's by-hand run is the first Windows
execution in this mission's history.

## Corrective Action

Wrapped the pattern: `tests/test_api_credential.py:391` now `match=re.escape(str(path))`; added `import re` (line 14). Grepped all of `tests/` for `match=str(` / `match=f"...{...}` path interpolation: this was the only occurrence. No production code touched.

## Verification

**Target:** `windows-tests` returns 0 failures, and the test still fails, for the right reason, if `CredentialFileError` stops naming the path.

**Results:**
- **Linux:** `tests/test_api_credential.py` 40 passed. `ruff check` and `ruff format --check` are clean on `tests/`.
- **Windows:** build 692704, `fly -t the-one execute -c ci/tasks/windows-tests.yml` on a clean export. 550 passed, 21 skipped, 2 xfailed, 1 deselected, **0 failed** (pytest 85 s, wall 166 s). The previous build, 692683, had 549 passed and 1 failed, on this test.
- **Still meaningful (Reviewer, scratch script with `PureWindowsPath(r"C:\Users\Test\data\api-credential")`):**
  - `match=re.escape(str(p))` passes when the message contains the path.
  - It raises `AssertionError` when the message omits it.
  - The old unescaped `match=str(p)` reproduces the bad-escape failure.

## Sign-Off

**Reviewer**: independent Reviewer (Sonnet tier: credentials test file). It confirmed the change is confined to `tests/test_api_credential.py` (`import re`, `match=re.escape(str(path))`) with no production credential code touched. Its scratch-script falsification shows the escaped match still pins that the error names the file.
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-09 (0092)` on branch `squawk/turnaround-2026-10-09`
