# Squawk 0141: Pin the Ollama shutdown-drain wiring and the panel's decimal sizes

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: —

## Report

Two behaviours sortie 01 shipped have no test that would fail if they regressed:

1. **Lifespan wiring.** `app.py`'s lifespan calls `ollama_library.shutdown_drain()`, and that is what keeps `make down` from waiting on a fill (DD4). The tests exercise only the module function, so deleting the call from `app.py` would pass every test.
2. **Decimal sizes on installed models and the VRAM line.** DD8 moved the whole Models panel to decimal units, matching ollama.com and `ollama pull`, so the same model reads the same size in the Pull list and once installed. The browser tests assert the Pull list, button and modal sizes only. The installed-model sizes and the VRAM summary line have no assertion. The VRAM line was rebuilt from `innerHTML` to DOM APIs without one.

Add one pin for each. Found in the sortie 01 debrief (Developer).

## Evidence

- `the_one/interfaces/web/app.py:85` `from the_one.llm import ollama_library`; `:387` `await ollama_library.shutdown_drain()`.
- `provider-models.js:101` `formatSize` (decimal); its installed-model and VRAM uses come after `:490`. `tests/browser/test_flow_provider_ollama_pull.py` has no assertion on `.admin-pf-model-size` or `.admin-pf-vram-summary`.

## Corrective Action
*(written at completion)*

## Verification
- A unit test fails when the `shutdown_drain()` call is removed from the lifespan: falsify it, then revert. For example, run a `TestClient(app)` lifespan with a fill pending, then assert the drain ran.
- A browser test with a stubbed `/models` and `/models/status` (for example, 13,793,441,244 B installed with 2,000,000,000 B in VRAM) asserts "13.8 GB" in the installed list and "2.0 GB loaded" on the VRAM line.
- `make test-unit` and the settings lane are green.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
