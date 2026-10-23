# Squawk 0241: 7 unit tests fail under freshly resolved dependencies

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: —

## Report
On 2026-10-22, a fresh `pip install -e '.[all-llms,dev]'` into a new venv (sortie 05's worktree) resolved newer versions of unpinned dependencies than the main checkout's venv. Under that install, 7 unit tests outside the sortie's scope failed. After pinning the venv to the main venv's `pip freeze`, all of them passed (149 passed across the four files).

The next fresh install, CI image rebuild or new developer machine will hit the same failures. A fresh install of the project is not reproducible today.

## Evidence
- Failing under the fresh install:
  - `tests/test_credential_gate.py::test_exempt_paths_are_get_only_on_the_real_app`, reporting `/api/oauth/callback` not registered.
  - `tests/test_mcp_wire_shapes.py`, one test (trust store).
  - `tests/test_openrouter_wire_level.py`, 4 tests.
  - `tests/test_vector_store.py`, one test (`usearch-i8`).
- Example version deltas noted at the time: MarkupSafe, cffi, chardet, click. The full delta was not kept.
- Recorded in `sorties/05-live-chats/flight-log.md` ("Anomaly: worktree venv dependency drift") and `sorties/05-live-chats/flight-debrief.md` (recommendation 1).

## Corrective Action
*(written at completion)*

## Verification
- Reproduce in a scratch venv outside the repo: `python3 -m venv <scratch>`, `pip install -e '.[all-llms,dev]'`, then diff its `pip freeze` against a known-good venv.
- Find the package behind each of the four failing files.
- Fix the code or tests for the new releases, or add a floor/ceiling pin with a comment naming the reason.
- Done when the four files pass in a fresh venv.
- If the fix needs a dependency-policy decision (a lockfile or constraints file for the project), escalate rather than choose one here.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
