# Squawk 0137: `App.formatBytes` divides by 1024 but labels the result "GB"

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-13

## Report

`App.formatBytes` uses binary maths (÷1024) but labels the result with decimal units ("MB", "GB"). Sortie 01 (DD8) moved the Ollama provider panel to a local decimal formatter, so the panel now matches ollama.com and `ollama pull`: `gpt-oss:20b` reads 13.8 GB there.

The agent editor's VRAM warning still uses `App.formatBytes`, so the same model reads 12.8 GB there. The same model now shows two different sizes in two places.

The fix is to make `App.formatBytes` decimal, matching the panel's formatter, so the app says one thing everywhere. The alternative is to keep binary maths and relabel the units "GiB", but that would no longer match Ollama's own numbers. Either way, check that sortie 01's panel and the shared helper agree.

Deferred from sortie 01 by design (DD8: "`App.formatBytes` is not changed in this sortie; its other callers are logged as a squawk at flight close").

## Evidence

- **The helper:** `the_one/interfaces/web/static/js/app.js:258` `formatBytes`: `while (val >= 1024 …) { val /= 1024; i++; }` with `units = ['B', 'KB', 'MB', 'GB', 'TB']`.
- **The remaining caller:** `the_one/interfaces/web/static/js/areas/studio.js:3735` (`var formatBytes = App.formatBytes;`), used in the VRAM warning at `:3813` and `:3815`.
- **The decimal formatter it should match:** `provider-models.js::formatSize` (sortie 01), `< 1e9` → whole MB, else one-decimal GB.

## Corrective Action
`App.formatBytes` (`static/js/app.js`) now divides by 1000, so the label matches the maths and sizes agree with ollama.com and `ollama pull` (decimal chosen over relabelling "GiB", which would no longer match Ollama). Its only caller is the agent editor's VRAM warning (`areas/studio.js`, two uses), a size display where decimal is right. The Ollama panel's `formatSize` was left separate: its output differs (whole MB under 1 GB, empty string for an unknown size, no TB tier, versus `formatBytes`' B/KB whole, MB onward one decimal, '0 B' for unknown), so it is not a drop-in. Its comment was updated to say so. Added `tests/test_format_bytes_static.py` (runs the real function under node).

## Verification
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_format_bytes_static.py tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py -x --timeout 30`: 286 passed. `App.formatBytes(13793441244)` gives "13.8 GB". The `warningEl.innerHTML = msg` line is untouched.
- ruff check/format clean on the new test. No existing test referenced formatBytes, "12.8" or "13.8".
Planned at logging (`make test-unit` and the agents lane run in the batch gate):
- `App.formatBytes(13793441244)` gives "13.8 GB", the same as the provider panel.
- The VRAM warning's existing tests are updated, and the static guards pass: the warning's `warningEl.innerHTML = msg` sink is in the baseline, so check its 80-character snippet is unchanged.
- `make test-unit` and the agents browser lane are green.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the batch includes the OAuth sign-in path, 0202), batch review of the 2026-10-13 squawk turnaround
**Verdict**: confirmed
**Commit**: the `squawk: turnaround 2026-10-13` commit on `squawk/turnaround-2026-10-13`. The final gate passed: unit 6287 passed and 14 skipped (the expected count under `THE_ONE_TEST_NETNS=1`); `PARALLEL_RESULT rc=0 total=998s lanes=9 failed=-`, every lane within budget.
