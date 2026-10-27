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

### Sortie 06 evidence (2026-10-26/27)
- A fresh worktree venv (`pip install -e ".[all-llms,dev]"` on 2026-10-26) failed 10 unit tests at base `2e82aaa`: the four files above (`test_vector_store` intermittently, either `usearch-f16` or `usearch-i8`) plus `tests/test_desktop_host.py` (3: GTK/WebKit present/missing).
- It also fails the browser test `tests/browser/test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search[chromium]` ("indexed: 2", expected 3, line 517) — reproduced on the **base code** with that venv, passing with the main checkout's venv. Pinning `usearch` to the main venv's 2.26.4 did not fix it, so the cause is elsewhere in the resolved set.
- Record: `sorties/06-safe-names/flight-log.md` (Flight Director Notes, Anomalies) and `flight-debrief.md` (recommendation 1). The browser failure makes this squawk's "four files pass" done-condition incomplete: add the knowledge test to it.

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
