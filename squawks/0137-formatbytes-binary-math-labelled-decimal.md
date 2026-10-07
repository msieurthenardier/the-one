# Squawk 0137: `App.formatBytes` divides by 1024 but labels the result "GB"

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

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
*(written at completion)*

## Verification
- `App.formatBytes(13793441244)` gives "13.8 GB", the same as the provider panel.
- The VRAM warning's existing tests are updated, and the static guards pass: the warning's `warningEl.innerHTML = msg` sink is in the baseline, so check its 80-character snippet is unchanged.
- `make test-unit` and the agents browser lane are green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
