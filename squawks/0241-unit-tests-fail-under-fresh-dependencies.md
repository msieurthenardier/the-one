# Squawk 0241: 7 unit tests fail under freshly resolved dependencies

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-23
**Completed**: 2026-11-03
**Related**: 0225: the same defect logged twice (unit tests fail on an unlocked install); complete together. CI and every package build install from the lock, so only contributors following CLAUDE.md's `pip install -e` hit it ([maintenance 2026-10-30](../maintenance/2026-10-30.md), finding #22).

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
Reproduced 2026-11-02 in `$HOME/the-one-scratch-venvs/s0241` (Python 3.12.3, `pip install -e '.[all-llms,dev]'`; freezes saved as `freeze-main.txt`, `freeze.txt`, `freeze2.txt` there). First run: 9 failed, 175 passed across the five files. Causes, one per release:
- **openai 3.x** (fresh 3.42.1 vs lock 2.32.0): 3.x moved its HTTP layer to `httpx2`, so the `httpx.AsyncClient.__init__` MockTransport seam in `tests/test_openrouter_wire_level.py` never reaches it (the 4 tests got a real 401). Fixed by a ceiling, `openai>=2.16,<3` (extras `openai` and `all-llms`, `pyproject.toml`), with the reason in a comment. Migrating the app's httpx seams to openai 3 is a separate piece of work. (Resolves to 2.54.0 in a fresh venv.)
- **usearch 2.26.5 / 2.26.6** (lock 2.26.4): f16 index of 50 vectors intermittently fails to return a stored vector as its own nearest neighbour (`test_vector_store.py::...test_query_returns_self_first_for_every_vector[usearch-f16]`, 5/25 on 2.26.6, 4/25 on 2.26.5, 0/25 on 2.26.4 and in `.venv`). A recall regression, so the test was not loosened: ceiling `usearch>=2.16,<2.26.5` with a comment.
- **FastAPI 0.162 / Starlette 1.10** (lock 0.136 / 1.3): `include_router` is now one lazy `_IncludedRouter` without a `path`, so `tests/test_credential_gate.py` found no `/api/oauth/callback` route. The test now walks `original_router.routes` (plus the include prefix) as well as flat routes; works on both versions. Product code unaffected.
- **httpx2 2.16 / httpcore2 2.16** (lock 2.13): on Linux the default context is a plain `ssl.SSLContext` loading the OS CA paths; `truststore` is used only on Windows/macOS. `test_httpx2_uses_the_os_trust_store_unless_overridden` now asserts truststore on Windows/macOS, and elsewhere accepts truststore (old httpx2) or a plain context with a populated store (new). SECURITY-MODEL.md's "OS trust store" claim still holds (not edited; another crew has uncommitted edits in that file).
- **PyGObject not installed** (not a version delta: the `gui` extra is not in `.[all-llms,dev]`; the main venv has it): `tests/test_desktop_host.py` 3 tests call `missing_desktop_piece()`, which imports `gi` first. `_fake_fs` now stubs a `gi` module, since those tests are about the file probes.
- `test_vector_store`'s `usearch-i8` failure and the knowledge browser test from the report did not reproduce today. The browser test was NOT re-checked under the fresh venv (needs `playwright install chromium`); it passed in M34 F1's quiet-host lane run.
- `uv lock` re-run: it records the two new ceilings and, because the tree already carried this batch's other `pyproject.toml` edits, also those (certifi floor, tzdata cap lifted, playwright 1.64.0). `uv lock --check` passes. No dependency-policy decision (lock/constraints file for contributors) was needed or made.

## Verification
Ran (after the changes): `PYTHON=<fresh>/bin/python bash scripts/run-tests.sh tests/test_credential_gate.py tests/test_mcp_wire_shapes.py tests/test_openrouter_wire_level.py tests/test_vector_store.py tests/test_desktop_host.py --timeout 60` in the fresh venv: 184 passed; in `.venv`: 184 passed. `ruff check` and `ruff format --diff` clean on the three touched tests. No new tests, so no falsification; the changed tests were seen failing before the change. `THE_ONE_TEST_NETNS=1 make test-unit` in `.venv`: 8729 passed, 15 skipped.

Original plan:
- Reproduce in a scratch venv outside the repo: `python3 -m venv <scratch>`, `pip install -e '.[all-llms,dev]'`, then diff its `pip freeze` against a known-good venv.
- Find the package behind each of the four failing files.
- Fix the code or tests for the new releases, or add a floor/ceiling pin with a comment naming the reason.
- Done when the four files pass in a fresh venv.
- If the fix needs a dependency-policy decision (a lockfile or constraints file for the project), escalate rather than choose one here.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs. The new ceilings are `openai<3` (the openai 3 / httpx2 migration is a separate piece of work) and `usearch<2.26.5`, which new squawk 0319 will lift.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.

- **2026-11-02 (Mission 34 Flight 1 Leg 2):** `test_detail_view_indexing_poll_reindex_and_search` passed in the `knowledge` lane of the quiet-host `--parallel 3` run (65 passed). Stays open.

## Disposition
- **2026-11-02 triage (Flight Director, Mission 34 squawk turnaround):** primary record for 0225 too. Second wave of the burn-down: reproduce in a scratch venv outside the repo, diff `pip freeze`, and fix per file. Escalate if it needs a lockfile/constraints policy decision.
