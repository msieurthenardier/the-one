# Squawk 0141: Pin the Ollama shutdown-drain wiring and the panel's decimal sizes

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-11-03

## Report

Two behaviours sortie 01 shipped have no test that would fail if they regressed:

1. **Lifespan wiring.** `app.py`'s lifespan calls `ollama_library.shutdown_drain()`, and that is what keeps `make down` from waiting on a fill (DD4). The tests exercise only the module function, so deleting the call from `app.py` would pass every test.
2. **Decimal sizes on installed models and the VRAM line.** DD8 moved the whole Models panel to decimal units, matching ollama.com and `ollama pull`, so the same model reads the same size in the Pull list and once installed. The browser tests assert the Pull list, button and modal sizes only. The installed-model sizes and the VRAM summary line have no assertion. The VRAM line was rebuilt from `innerHTML` to DOM APIs without one.

Add one pin for each. Found in the sortie 01 debrief (Developer).

## Evidence

- `the_one/interfaces/web/app.py:85` `from the_one.llm import ollama_library`; `:387` `await ollama_library.shutdown_drain()`.
- `provider-models.js:101` `formatSize` (decimal); its installed-model and VRAM uses come after `:490`. `tests/browser/test_flow_provider_ollama_pull.py` has no assertion on `.admin-pf-model-size` or `.admin-pf-vram-summary`.

## Corrective Action
Tests only. (a) `tests/test_lifespan.py::test_lifespan_drains_ollama_library_fill_on_shutdown` runs the real lifespan with `ollama_library.shutdown_drain` replaced by a recorder and asserts it ran on shutdown and not at startup. Falsified: replacing the call in `app.py` with `pass` makes it fail; restored (git diff of app.py is empty). (b) `tests/browser/test_flow_provider_ollama_pull.py::test_installed_sizes_and_vram_line_are_decimal` stubs `/models` (13,793,441,244 B installed; 5 GB model running with 2,000,000,000 B VRAM) and asserts "13.8 GB" on the installed row, "2.0 GB" on the running row, and "2.0 GB loaded" on `.admin-pf-vram-summary`. Note the squawk's `.admin-pf-model-size` no longer exists; the row size class is `.ui-model-size`. Falsified both ways (installed size and VRAM line each switched to raw bytes in `provider-models.js`: fails each; restored, git diff of the file empty).

## Verification (results)
Lifespan file and the new browser test green; `providers` lane and unit tier results in the batch report; ruff clean.

## Verification (spec)
- A unit test fails when the `shutdown_drain()` call is removed from the lifespan: falsify it, then revert. For example, run a `TestClient(app)` lifespan with a fill pending, then assert the drain ran.
- A browser test with a stubbed `/models` and `/models/status` (for example, 13,793,441,244 B installed with 2,000,000,000 B in VRAM) asserts "13.8 GB" in the installed list and "2.0 GB loaded" on the VRAM line.
- `make test-unit` and the settings lane are green.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet: the batch touches the shell-write hook, `App.safeUrl`, the encryption status count and the credential docs), batch review of the 2026-11-02-2 squawk turnaround, scoped to the diff. Its one blocking finding (0135's Dockerfile `uv venv` line) and the non-blocking items were fixed in a fix pass, which a Haiku Reviewer re-checked: `[HANDOFF:confirmed]`. An Accessibility Reviewer (Sonnet) confirmed the UI changes (0239, 0289, 0290, 0291, 0254). The final gate on the batch tree: `THE_ONE_TEST_NETNS=1 make test-unit` 8738 passed, 15 skipped (219 s, start load 0.48); browser `--parallel 3` `PARALLEL_RESULT rc=1 total=1774s lanes=17 failed=chats-transcript` (start load 0.72). The one failure is new squawk 0315, which passed 3 of 3 isolated runs.
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-11-02-2` commit on `squawk/turnaround-2026-11-02-2`.
