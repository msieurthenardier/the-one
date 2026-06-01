# Leg: settings-removal-and-dispatcher-inference-source-refactor

**Status**: completed
**Flight**: [Audit-log inspector + per-connector inference config + slash-command HAT](../flight.md)

## Objective

Retire `Settings.inference_provider_config_id` + `Settings.inference_model` from `the_one/config.py`, change `_resolve_inference_provider`'s signature from a `Settings` parameter to two new `connector_inference_*` keyword arguments, refactor the dispatcher's policy-gate inference call at `_inbound.py` to read from `account.config` instead of `settings`, add a FastAPI lifespan-hook startup warning when either deprecated env var is set, cull the now-impossible settings-partial test branches in `tests/test_connectors_inference.py`, rewrite every other Settings-shaped test under the new signature, add connector-kwarg-path coverage tests, and add one lifespan-warning test in `tests/test_lifespan.py` — paired with L2 across the v26 commit boundary as the runtime-side of the connector-scope inference relocation.

## Context

- **Flight Technical Approach L3 sub-parts (a)–(d)** in `flight.md`: runtime-path-only leg pairing with L2. L2 (just landed at 2790 backend tests passing) extended the `connector.config` validator to accept `inference_provider_config_id` + `inference_model` as optional `str | None` keys and added the v26 migration that backfills `None` defaults. L3 is the runtime consumer side: the dispatcher reads from those new connector-config keys instead of from Settings; the Settings fields are deleted; the unit-test surface that pinned the now-removed "settings-wins-shadows-fallback" semantic is culled.
- **`Settings Removed Entirely` Design Decision** (`flight.md`): both env vars become no-ops; a single one-time-at-startup `logger.warning` (in the FastAPI lifespan hook, NOT module load) informs the operator that the values won't apply and directs them to the Studio connector editor. Lifespan was chosen over module load because module load runs on every test-suite import (would log spuriously per-test); lifespan fires once per app start.
- **`_resolve_inference_provider` Signature Change Design Decision** (`flight.md`): F7's helper at `the_one/connectors/_inference.py:141-228` takes `settings: Settings` first-positional and implements settings-wins-shadows-fallback. F13 L3 changes this to: drop the `settings` parameter; add two new kwargs `connector_inference_provider_config_id: str | None` + `connector_inference_model: str | None`. New resolution order: connector kwarg pair (both set) → `fallback_provider_config_id` (routed agent's LLM, both must be set) → silence with audit log entry. Same shape (two paths + silence), but the precedence is per-connector instead of project-wide.
- **`v26 Backfill is None` Design Decision** (`flight.md`): existing always_listen connectors silently shifted at L2 land from "uses env-var-configured inference model" → "uses routed agent's LLM" (since `account.config.inference_provider_config_id` is now `None` everywhere post-migration unless operator hand-edits). The L2 migration's `logger.info` per always_listen connector surfaces this at startup. L3 honors the shift: the runtime path reads from `account.config`, which is `None` for all existing rows, so all such connectors fall through to the routed agent's LLM at the inference gate. L4 (connector-editor UI) gives the operator the surface to set the per-connector values.
- **L2 post-state (verified via Flight Log L2 LANDED entry)**:
  - Backend: 2790 passed / 4 skipped / 0 errors / 0 failures.
  - Browser: 443 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures.
  - `connector.config` accepts new keys: `Connector(config={"inference_provider_config_id": "p1", "inference_model": "m1"})` round-trips via Pydantic.
  - v26 migration adds `None` defaults to every connector's config (verified via `test_v26_connector_config_inference_fields_added`).
  - L2's docstring update at `the_one/db/models.py:254-260` already says "operators set them per-connector via the Studio connector editor (F13 L4); `None` at the dispatcher policy gate (F13 L3) falls through to the routed agent's LLM" — L3 makes that promise true.
- **Recon-confirmed Settings consumer sites** (the grep run during L3 recon — `grep -rn "settings\.inference\|Settings(inference\|inference_provider_config_id\|inference_model" the_one/ --include='*.py'`):
  - `the_one/config.py:31-32` — the two fields themselves (L3 deletes).
  - `the_one/connectors/_inference.py:13-14, 39, 151-152, 167-168, 173, 240, 263-264` — module docstring + `from the_one.config import Settings` + the `_resolve_inference_provider` signature + body reads + the `run_engagement_inference` `settings: Settings` parameter + its docstring reference. ALL L3 surface.
  - `the_one/connectors/_inbound.py:179, 254, 258, 268-275` — the `_policy_gate_decision` helper's `settings: Any` parameter + the `run_engagement_inference` invocation + the `policy.inference_provider_id` + `policy.inference_model` audit-entry-build sites at 268-275. ALL L3 surface.
  - `the_one/db/models.py:629-642` — L2's validator-block reads (the validator itself stays; L3 doesn't touch).
  - `the_one/db/schema.py:1578-1657` — L2's v26 migration block (L3 doesn't touch).
- **L3 is the ONLY consumer of `Settings.inference_*` outside L2's surface**: the recon grep against `tests/` returned ZERO hits in non-inference test files. No other test file pins the Settings inference fields. Risk surface is bounded to the four enumerated files plus the new lifespan-warning test.
- **Pulled-Forward methodology lessons applied** (per `flight-log.md` "Pulled-Forward F12 Debrief Methodology Lessons"):
  - #1 (grep-gate scope is a design decision) — L3 post-state grep gates enumerate allowed residue (lifespan-warning `os.environ.get` is NOT a Settings reference; only `settings.inference_*` is forbidden).
  - #2 (Phase 5c architect cycle for grep-gate flights) — AC-9 + AC-10 run the literal greps post-implementation.
  - #3 (separate test-surface from production-surface recon) — `_resolve_inference_provider` recon enumerates the 17 individual test bodies in `test_connectors_inference.py` separately from the production-side surface, with explicit CULL / REWRITE / ADD classification.
  - #5 (operator-local-state preservation) — operator's `docker-compose.yml` `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` + `THE_ONE_INFERENCE_MODEL` env vars stay UNSTAGED; L3's lifespan warning surfaces the dead-weight on next startup. The operator removes them from their `docker-compose.yml` on their own schedule.

## Inputs

What exists before this leg runs:

- Branch `flight/13-audit-log-inspector-and-connector-inference-config` checked out with L1 + L2 uncommitted-since-`26a0ddf` edits carried forward in the working tree (per `/agentic-workflow` Phase 2d batching protocol).
- Backend test suite passes at **2790 passed / 4 skipped / 0 errors / 0 failures** (per Flight Log L2 LANDED entry).
- Browser test suite passes at **443 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures** (unchanged).
- `the_one/config.py:31-32` — the two `Settings.inference_*` fields, plus the explanatory comment block at `:21-30`.
- `the_one/connectors/_inference.py:39` — `from the_one.config import Settings`.
- `the_one/connectors/_inference.py:141-228` — `_resolve_inference_provider(settings: Settings, provider_repo: LLMProviderRepository, fallback_provider_config_id: str | None, fallback_llm_model: str | None) -> LLMProvider | None`. Body reads `settings.inference_provider_config_id` + `settings.inference_model` at `:167-168`; implements "settings-wins-shadows-fallback" at `:170-193`.
- `the_one/connectors/_inference.py:236-243` — `run_engagement_inference(account, envelope, session_messages, settings: Settings, provider_repo, fallback_provider_config_id, fallback_llm_model) -> bool`. Forwards `settings` to `_resolve_inference_provider` at `:300-305`.
- `the_one/connectors/_inbound.py:169-180` — `_policy_gate_decision(*, envelope, account, agent_config, plugin, decision, session_messages, conn, encryptor, settings: Any)`; `settings` is the project-wide Settings singleton.
- `the_one/connectors/_inbound.py:248-262` — the `run_engagement_inference` invocation passing `settings=settings`.
- `the_one/connectors/_inbound.py:268-275` — the `policy.inference_provider_id` + `policy.inference_model` audit-entry build reading `settings.inference_provider_config_id or agent_config.provider_config_id` + `settings.inference_model or agent_config.llm_model`.
- `the_one/connectors/_inbound.py:765-775` — the `_policy_gate_decision` call passing the top-level `settings` singleton.
- `the_one/connectors/_inbound.py:314` — `from the_one.config import settings` (used both for `data_dir` at `:329` AND fed through `_policy_gate_decision` at `:774`).
- `the_one/interfaces/web/app.py:81-237` — the FastAPI `lifespan` async-context-manager (decorated `@asynccontextmanager`). Startup code runs through line 173 then hits `yield` at `:175`; shutdown code follows. The lifespan already imports `os` at `:113` (inside the dev-mode stub-connector block) — L3 may re-use that import or pull it to the module top.
- `tests/test_connectors_inference.py:125-134` — `_empty_settings()` helper. 24 test bodies total in the file (verified via section comment blocks); 7 of them construct `Settings(inference_provider_config_id=..., inference_model=...)` directly at lines 131-134 (helper body), 230-233, 256-259, 276-279, 317-320, 569-572, 616-619.
- `tests/test_lifespan.py:1-50+` — existing FastAPI lifespan tests using `async with lifespan(app):` directly. `_isolated_data_dir` fixture at `:81-101` monkeypatches `settings.data_dir` to a tmp path. The L3 lifespan-warning test will follow the same pattern (potentially adding a `monkeypatch.setenv` / `monkeypatch.delenv` for the two deprecated env vars).
- `tests/test_config.py:1-40+` — exists but is for `the_one.agent.config.AgentConfig` (NOT `the_one.config.Settings`); the lifespan-warning test does NOT belong here.

## Outputs

What exists after this leg completes:

- **`the_one/config.py`**:
  - The two `inference_provider_config_id` + `inference_model` fields at `:31-32` REMOVED.
  - The explanatory comment block at `:21-30` (the "M11 F7 L7" paragraph documenting the inference pair) REMOVED.
  - The `Settings` class body now has only `host`, `port`, `dev_mode`, `data_dir` fields plus the `agents_dir` / `db_path` / `ensure_dirs` helpers. No reference to `inference_*` remains.
- **`the_one/interfaces/web/app.py`** (`lifespan`):
  - Inside `lifespan(app)` AFTER the existing startup block but BEFORE the `yield` at `:175` (precise insertion point: between the connector warm-acquire `try:` block ending at `:173` and the `yield` at `:175`), a new env-var deprecation-warning block is added. The block reads `os.environ.get("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID")` + `os.environ.get("THE_ONE_INFERENCE_MODEL")` and emits a single `logger.warning` if either is set (truthy). One log line names BOTH env vars + directs the operator at the Studio connector editor + mentions per-connector config keys `inference_provider_config_id` + `inference_model`.
  - `import os` either at module-top (preferred — already imported function-locally at `:113`) OR re-uses the existing `:113` function-local import. Implementing-agent picks the more ergonomic shape; the function-local import at `:113` happens UNCONDITIONALLY before the dev-mode `if` check at `:115`, so it's reachable via module-local scope by the time the new warning block runs only if the test-seam dev-mode condition matched (NOT always). RECOMMENDATION: add a top-of-file `import os` (mirroring `import json` at `:5`) and let the existing `:113` `import os` stay as a redundant-but-harmless local; the implementing agent may instead move `import os` to module-top and drop the `:113` line. Either is acceptable; tests verify behavior, not import topology.
- **`the_one/connectors/_inference.py`**:
  - `from the_one.config import Settings` at `:39` REMOVED.
  - Module docstring at `:11-21` (paragraph beginning "Provider resolution (Flight DD §9 + L7 model-source extension)…" through "…Partial pairs on either path → log + None…") rewritten to describe the post-L3 resolution order:
    - "Provider resolution (M11 F13 L3 — connector-scope inference): the inference provider is configured per-connector via two paired `connector.config` keys — `inference_provider_config_id` (auth + base_url scope, the `LLMProviderConfig` row id) AND `inference_model` (per-call model name). Both must be set, or both unset. When both are set on the connector, the helper uses them. When both are unset, the helper falls back to the routed agent's LLM (the L8 dispatcher passes the agent's `provider_config_id` AND `llm_model` to :func:`run_engagement_inference` so this module never reaches into the agent factory). Partial pairs on either path → log + None (operator misconfiguration surfaced as silence per the safe-default discipline)."
    - Drop any remaining references to `Settings` from the module docstring.
  - `_resolve_inference_provider` signature change at `:141-145`:
    - OLD: `async def _resolve_inference_provider(settings: Settings, provider_repo: LLMProviderRepository, fallback_provider_config_id: str | None, fallback_llm_model: str | None) -> LLMProvider | None:`
    - NEW: `async def _resolve_inference_provider(provider_repo: LLMProviderRepository, *, connector_inference_provider_config_id: str | None, connector_inference_model: str | None, fallback_provider_config_id: str | None, fallback_llm_model: str | None) -> LLMProvider | None:` — note the `*,` keyword-only marker for the four resolution-input kwargs (`provider_repo` stays positional to match the existing call-site shape; the four resolution-input kwargs are keyword-only for self-documenting call sites and to prevent positional-arg confusion at the new call site).
  - `_resolve_inference_provider` body rewrite at `:147-228`:
    - Read `connector_inference_provider_config_id` + `connector_inference_model` instead of `settings.inference_provider_config_id` + `settings.inference_model` at the head of the function.
    - Same pairing-invariant check ("if one is None and the other isn't, log + None"); rename the log line to say `connector_inference_provider_config_id=%r connector_inference_model=%r` instead of the old settings-named labels.
    - Same shadowing-doesn't-escalate semantic: when connector kwarg pair is fully set, fallback is ignored (failures during connector-path resolution OR construction return None, do NOT escalate to fallback). This preserves the safe-default discipline — operator misconfiguration surfaces as silence whether the operator misconfigured the per-connector setting or the project-wide setting (the consumer doesn't change; only the source of the misconfigured value did).
    - Docstring rewrite — the three-path explanation ("Settings path / Settings partial / Fallback path") becomes "Connector path / Connector partial / Fallback path"; same paragraphs, same outcomes, only renaming.
  - `run_engagement_inference` signature change at `:236-243`:
    - OLD: `async def run_engagement_inference(account: Connector, envelope: InboundEnvelope, session_messages: list[Message], settings: Settings, provider_repo: LLMProviderRepository, fallback_provider_config_id: str | None, fallback_llm_model: str | None) -> bool:`
    - NEW: `async def run_engagement_inference(account: Connector, envelope: InboundEnvelope, session_messages: list[Message], provider_repo: LLMProviderRepository, *, connector_inference_provider_config_id: str | None, connector_inference_model: str | None, fallback_provider_config_id: str | None, fallback_llm_model: str | None) -> bool:` — drop `settings`; add the two connector kwargs as keyword-only.
  - `run_engagement_inference` body update at `:300-305`:
    - The internal call to `_resolve_inference_provider(settings, provider_repo, fallback_provider_config_id, fallback_llm_model)` becomes `_resolve_inference_provider(provider_repo, connector_inference_provider_config_id=connector_inference_provider_config_id, connector_inference_model=connector_inference_model, fallback_provider_config_id=fallback_provider_config_id, fallback_llm_model=fallback_llm_model)`.
  - `run_engagement_inference` docstring update at `:255-272`:
    - Drop the `settings` parameter description.
    - Add `connector_inference_provider_config_id` + `connector_inference_model` descriptions: "the per-connector inference LLM pair (sourced from `account.config` at the dispatcher call site)".
- **`the_one/connectors/_inbound.py`** (`_policy_gate_decision` + the call site at `:765-775`):
  - `_policy_gate_decision` parameter `settings: Any` at `:179` REMOVED (no longer needed — the helper sources both the dispatcher-passed kwargs AND the audit-entry-build values from `account.config` directly).
  - The `run_engagement_inference` invocation at `:254-262` updated:
    - Drop the `settings=settings` line at `:258`.
    - Add `connector_inference_provider_config_id=account.config.get("inference_provider_config_id")` and `connector_inference_model=account.config.get("inference_model")` to the kwarg list.
  - The audit-entry build at `:268-275` updated:
    - `"inference_provider_id"`: change `settings.inference_provider_config_id or agent_config.provider_config_id` → `account.config.get("inference_provider_config_id") or agent_config.provider_config_id`.
    - `"inference_model"`: change `settings.inference_model or agent_config.llm_model` → `account.config.get("inference_model") or agent_config.llm_model`.
  - The `_policy_gate_decision` call at `:765-775` updated: drop `settings=settings` at `:774`.
  - **CRITICAL — the top-level `from the_one.config import settings` at `:314` MUST STAY**: it is still used at `:329` (`encryptor = get_encryptor(settings.data_dir)`). Do NOT remove this import; only the `settings=settings` kwarg passthroughs go.
- **`tests/test_connectors_inference.py`** — comprehensive rework. Net delta: **-2 cull + 4 add + 0 from rewrites = +2** (overrides flight spec's −5 to −7 estimate; see "Cycle-1 recon finding: test-cull count revised lower" in the Notes for the Implementing Agent section at the bottom).
  - **Module-level import `from the_one.config import Settings` at `:19` REMOVED** (no longer used).
  - **`_empty_settings()` helper at `:125-134` DELETED** (Settings has no inference fields; no callers post-rework).
  - **CULL — 2 tests (the only tests that pin a now-structurally-impossible semantic)**:
    - `test_resolve_inference_provider_returns_none_when_settings_id_set_but_model_unset` at `:252-269` — settings-partial-pair-with-id-only-set; post-L3 there is no `Settings.inference_*` to set partially.
    - `test_resolve_inference_provider_returns_none_when_settings_model_set_but_id_unset` at `:272-289` — symmetric partial.
    - The connector-partial-pair tests are added back as NEW tests (see ADD section) — same shape, just at the new layer.
  - **REWRITE — 1 helper + 17 tests** (signature-change-only; no semantic change in coverage):
    - `_patch_resolver_returning` helper at `:374-392`: the fake-resolver signature drops `_settings: Settings`, gains the four kwarg parameters (use `**_kwargs: Any` for permissive forward-compat).
    - `test_resolve_inference_provider_uses_settings_when_both_id_and_model_set` at `:225-249` → rename to `test_resolve_inference_provider_uses_connector_kwargs_when_both_set`; replace the `settings = Settings(...)` construction with passing `connector_inference_provider_config_id="prov-a", connector_inference_model="model-a"` to `_resolve_inference_provider`.
    - `test_resolve_inference_provider_falls_back_when_settings_both_unset` at `:292-309` → rename to `test_resolve_inference_provider_falls_back_when_connector_kwargs_both_unset`; drop the `settings = _empty_settings()` and pass `connector_inference_provider_config_id=None, connector_inference_model=None`.
    - `test_resolve_inference_provider_returns_none_on_settings_resolution_failure_no_fallback` at `:312-334` → rename to `test_resolve_inference_provider_returns_none_on_connector_resolution_failure_no_fallback`; replace `Settings(inference_provider_config_id="missing-prov", inference_model="model-a")` with the connector-kwarg equivalents. The "doesn't escalate to fallback" assertion stands — the connector-path's safe-default-discipline is identical to the old settings-path's.
    - `test_resolve_inference_provider_returns_none_when_fallback_id_missing` at `:337-349` → drop `settings = _empty_settings()`; pass `connector_inference_provider_config_id=None, connector_inference_model=None`.
    - `test_resolve_inference_provider_returns_none_when_fallback_model_missing` at `:352-366` → same as above.
    - All 8 `run_engagement_inference` tests (`test_run_engagement_inference_*` at `:395-585` + `:605-781`) — drop `_empty_settings()` argument from the call; convert to passing `connector_inference_provider_config_id=None, connector_inference_model=None` as keyword arguments. The 2 tests that pass non-None Settings (`test_run_engagement_inference_returns_false_on_provider_resolution_failure` at `:559-585` constructs `Settings(inference_provider_config_id="missing", inference_model="model-a")`; `test_run_engagement_inference_end_to_end_happy_path` at `:605-645` constructs `Settings(inference_provider_config_id="prov-a", inference_model="model-a")`) — convert each Settings construction into the equivalent connector-kwarg pair.
  - **ADD-NEW — 4 tests** (target the L3 spec's "Add new tests for the connector-kwarg-wins-over-fallback path + the both-None-falls-to-silence path. Likely 4-6 new tests post-cull."):
    - `test_resolve_inference_provider_returns_none_when_connector_id_set_but_model_unset` — connector-partial-pair-with-id-only (parallel to the culled settings-partial test, at the new layer; covers the partial-pair-invariant on the new path).
    - `test_resolve_inference_provider_returns_none_when_connector_model_set_but_id_unset` — symmetric to the above.
    - `test_resolve_inference_provider_uses_connector_kwargs_over_working_fallback` — connector kwargs fully set AND fallback fully set; the connector pair wins; the fallback is ignored even when both would resolve cleanly. Same shape as the OLD `test_resolve_inference_provider_uses_settings_when_both_id_and_model_set` but adds the explicit "fallback is ignored even when working" assertion (the OLD test had this assertion in prose only; the new test makes it executable).
    - `test_resolve_inference_provider_returns_none_when_both_paths_unconfigured` — connector kwargs None AND fallback None → None (full both-paths-silence coverage). Bridges what's currently scattered across the per-path partial tests.
- **`tests/test_lifespan.py`** — 1 new test appended (`test_lifespan_warns_on_deprecated_inference_env_vars`):
  - Uses the existing `_isolated_data_dir` fixture for the data dir + DB singleton setup.
  - Uses `monkeypatch.setenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", "p1")` (and/or `THE_ONE_INFERENCE_MODEL`) BEFORE entering `async with lifespan(app):`.
  - Captures `caplog.at_level(logging.WARNING, logger="the_one.interfaces.web.app")`.
  - Asserts exactly one `WARNING`-level record matching the inference-deprecation message text fires within the lifespan-startup block.
  - A second test `test_lifespan_does_not_warn_when_inference_env_vars_unset` mirrors with `monkeypatch.delenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", raising=False)` + same for the model var; asserts ZERO matching records fired.
  - **Two tests** in this file, not one (the spec said "+1 settings-warning lifespan test"; the +/- presence/absence pair is the natural shape for a `caplog`-based warning test — adding both costs minimal extra code and locks the warning's idempotency in both directions).
- **Test count totals**:
  - Backend: **2790 + 2 = 2792 ± 2** (L2 baseline 2790; `test_connectors_inference.py` −2 cull / 0 net from rewrites / +4 add = +2; `test_lifespan.py` +2 = +4 total; final 2794 ± 2). **NB**: the flight spec's L3 backend test count target was `2784 ± 2`. The architect cycle-1 enumeration assumed "10-12 settings-path tests" would be culled. Recon surfaced that only 2 tests actually pin the settings-path semantic in a structurally-now-impossible way; the rest are mechanical-signature-rewrites. The L3 target is **superseded**; see "Cycle-1 recon finding: test-cull count revised lower" in the Notes for the Implementing Agent section for the implementing agent's expected total. **Reconciliation with the L3 target**: this is a Flight-level Acceptable variations item — flight spec line 257 says "L3 may discover that `test_connectors_inference.py`'s settings-path tests have already been partially rewritten by some prior flight (unlikely); reduce cull scope correspondingly" — apply that variance clause: the cull scope was over-estimated at flight-spec time, recon revealed the true cull scope, the leg target is adjusted upward by ~10 tests vs the flight target.
  - Browser: **443 unchanged** (no browser tests added in L3; no UI surface this leg).

## Acceptance Criteria

- [x] **AC-1** (Settings fields removed): `git grep -nE "inference_provider_config_id|inference_model" the_one/config.py` returns ZERO hits. `docker exec the-one python -c "from the_one.config import Settings; assert 'inference_provider_config_id' not in Settings.model_fields; assert 'inference_model' not in Settings.model_fields; print('ok')"` succeeds. (Pydantic class-level field-presence check.)
- [x] **AC-2** (`_resolve_inference_provider` signature change): `python -c "import inspect; from the_one.connectors._inference import _resolve_inference_provider; sig = inspect.signature(_resolve_inference_provider); params = list(sig.parameters); assert 'settings' not in params and 'connector_inference_provider_config_id' in params and 'connector_inference_model' in params and 'fallback_provider_config_id' in params and 'fallback_llm_model' in params and 'provider_repo' in params"` succeeds.
- [x] **AC-3** (`run_engagement_inference` signature change): `python -c "import inspect; from the_one.connectors._inference import run_engagement_inference; sig = inspect.signature(run_engagement_inference); params = list(sig.parameters); assert 'settings' not in params and 'connector_inference_provider_config_id' in params and 'connector_inference_model' in params"` succeeds.
- [x] **AC-4** (dispatcher reads from `account.config`): `git grep -nE "account\.config\.get\(.inference_provider_config_id.\)|account\.config\.get\(.inference_model.\)" the_one/connectors/_inbound.py` returns at least 4 hits (2 for the `run_engagement_inference` kwarg passthrough at the L2 site + 2 for the audit-entry build at the L2 site).
- [x] **AC-5** (`_policy_gate_decision` `settings` parameter removed): `git grep -nE "def _policy_gate_decision" the_one/connectors/_inbound.py` finds the def line; verify by `python -c "import inspect; from the_one.connectors._inbound import _policy_gate_decision; sig = inspect.signature(_policy_gate_decision); assert 'settings' not in sig.parameters"`.
- [x] **AC-6** (lifespan warning fires): `docker exec the-one pytest tests/test_lifespan.py::test_lifespan_warns_on_deprecated_inference_env_vars -x --timeout 30 -q` → PASS. `docker exec the-one pytest tests/test_lifespan.py::test_lifespan_does_not_warn_when_inference_env_vars_unset -x --timeout 30 -q` → PASS.
- [x] **AC-7** (`_empty_settings` helper deleted): `git grep -nE "_empty_settings" tests/` returns ZERO hits.
- [x] **AC-8** (Settings import removed from `_inference.py` + `test_connectors_inference.py`): `git grep -nE "^from the_one\.config import Settings" the_one/connectors/_inference.py tests/test_connectors_inference.py` returns ZERO hits.
- [x] **AC-9** (Phase 5c grep-gate — production source has no `settings.inference_*` reads): `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" the_one/` returns ZERO hits. Allowed residue (which the regex DOES NOT match): the lifespan-warning code that reads via `os.environ.get` directly. **If the grep returns hits in `the_one/`, the implementing agent investigates and folds the additional sites in-leg per Adaptation Criteria (flight.md "L3 may discover more settings-path tests than the architect cycle-1 enumeration").**
- [x] **AC-10** (Phase 5c grep-gate — test source has no `settings.inference_*` reads): `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" tests/` returns ZERO hits.
- [x] **AC-11** (Phase 5c grep-gate — `_inbound.py` uses `account.config` not `settings` for inference lookups): `git grep -nE "inference_provider_config_id|inference_model" the_one/connectors/_inbound.py` returns ONLY hits in the form `account.config.get("inference_provider_config_id")` or `account.config.get("inference_model")` (4 hits expected per AC-4). NO `settings.inference_*` hits.
- [x] **AC-12** (`test_connectors_inference.py` direct regression green): `docker exec the-one pytest tests/test_connectors_inference.py -x --timeout 30 -q` → all collected tests PASS (cull + rewrite + add net per the "Outputs" enumeration).
- [x] **AC-13** (`test_lifespan.py` direct regression green): `docker exec the-one pytest tests/test_lifespan.py -x --timeout 30 -q` → all collected tests PASS.
- [x] **AC-14** (broader dispatcher regression — direct consumers of touched files green): `docker exec the-one pytest tests/test_connectors_inference.py tests/test_lifespan.py tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py tests/test_connectors_inbound.py tests/test_connectors_policy_gate.py tests/test_connectors_discord.py -x --timeout 30 -q` all green; no regressions from the signature changes. **`test_connectors_policy_gate.py` is the primary semantic-correctness surface for the dispatcher's `run_engagement_inference` invocation** — `TestPolicyGateInferenceFallbacks` monkeypatches `run_engagement_inference` with `async def _capture(**kwargs: Any)` fakes; the `**kwargs` form survives the signature change structurally and the existing `fallback_*` kwarg assertions stay valid. Optional polish: append `assert captured["connector_inference_provider_config_id"] is None` + `assert captured["connector_inference_model"] is None` to lock the new wiring contract executably.
- [x] **AC-15** (full backend regression at target count): `docker exec the-one pytest tests/ --timeout 30 -q` ends at **2794 ± 2 passed** / 4 skipped / 0 errors / 0 failures (L2 baseline 2790 + 2 cull + 4 add + 2 lifespan tests = 2794, ± 2 for any minor delta from cycle-1's enumeration estimates). See "Cycle-1 recon finding: test-cull count revised lower" in the Notes for the Implementing Agent section below for the count reconciliation vs the flight spec's 2784 target. **If the count lands materially outside the 2792-2796 envelope, the implementing agent verifies the variance is from a counted-source (rewrite-renamed test that lost its prior parametrization, or an ADD test whose count was off-by-one) before signaling [HANDOFF:review-needed].**
- [x] **AC-16** (browser regression preserved): `docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q` ends at **443 passed** / 35 skipped / 12 deselected / 2 pre-existing failures unchanged (no new browser failures; L3 has no UI surface).

## Verification Steps

How to confirm each criterion is met:

- **AC-1**: `git grep -nE "inference_provider_config_id|inference_model" the_one/config.py` — expect zero hits. Also `docker exec the-one python -c "from the_one.config import Settings; s = Settings(); assert not hasattr(s, 'inference_provider_config_id'); assert not hasattr(s, 'inference_model'); print('ok')"`.
- **AC-2**: `docker exec the-one python -c "import inspect; from the_one.connectors._inference import _resolve_inference_provider; sig = inspect.signature(_resolve_inference_provider); params = list(sig.parameters); assert 'settings' not in params; assert 'connector_inference_provider_config_id' in params; assert 'connector_inference_model' in params; assert 'fallback_provider_config_id' in params; assert 'fallback_llm_model' in params; assert 'provider_repo' in params; print('ok')"`.
- **AC-3**: `docker exec the-one python -c "import inspect; from the_one.connectors._inference import run_engagement_inference; sig = inspect.signature(run_engagement_inference); params = list(sig.parameters); assert 'settings' not in params; assert 'connector_inference_provider_config_id' in params; assert 'connector_inference_model' in params; print('ok')"`.
- **AC-4**: `git grep -nE 'account\.config\.get\(.(inference_provider_config_id|inference_model).\)' the_one/connectors/_inbound.py` — expect ≥4 hits.
- **AC-5**: `docker exec the-one python -c "import inspect; from the_one.connectors._inbound import _policy_gate_decision; sig = inspect.signature(_policy_gate_decision); assert 'settings' not in sig.parameters; print('ok')"`.
- **AC-6**: `docker exec the-one pytest tests/test_lifespan.py::test_lifespan_warns_on_deprecated_inference_env_vars tests/test_lifespan.py::test_lifespan_does_not_warn_when_inference_env_vars_unset -x --timeout 30 -q`.
- **AC-7**: `git grep -nE "_empty_settings" tests/` — expect zero hits.
- **AC-8**: `git grep -nE "^from the_one\.config import Settings" the_one/connectors/_inference.py tests/test_connectors_inference.py` — expect zero hits.
- **AC-9**: `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" the_one/` — expect zero hits.
- **AC-10**: `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" tests/` — expect zero hits.
- **AC-11**: `git grep -nE "inference_provider_config_id|inference_model" the_one/connectors/_inbound.py` — every hit is an `account.config.get(...)` access; no `settings.` prefix.
- **AC-12**: as above.
- **AC-13**: as above.
- **AC-14**: as above.
- **AC-15**: `docker exec the-one pytest tests/ --timeout 30 -q | tail -5`.
- **AC-16**: `docker exec the-one pytest tests/browser/ -m browser --timeout 30 -q | tail -5`.

## Implementation Guidance

> **CRITICAL ORDERING**: Steps 2 through 6 leave the working tree in a TRANSIENT BROKEN STATE — the Settings fields are removed (step 2) but the consumers (`_inference.py` at step 4, `_inbound.py` at step 5, the test file at step 7) still reference them until those steps land. Do NOT run pytest between steps 2 and 7. Run the regression gates only at step 9.

1. **Capture baseline test count snapshot.**
   - `docker exec the-one pytest --collect-only -q tests/ 2>&1 | tail -3` — capture the pre-L3 baseline collected count. Per L2 LANDED (2790 passed + 4 skipped + 509 deselected; total collected ≈ 2794), expect ≈ 2794 collected. The exact number from your `--collect-only` is the source of truth for AC-15's diff math.
   - `docker exec the-one pytest tests/test_connectors_inference.py tests/test_lifespan.py -x --timeout 30 -q | tail -5` — confirm both files are green pre-L3.

2. **Delete the two inference fields from `the_one/config.py:31-32`.**
   - Also delete the explanatory comment block at `:21-30` (the "M11 F7 L7: inference provider + model for the engagement-policy gate…" paragraph). The block is dead documentation post-removal.
   - The `Settings` class body should now read (after the `data_dir` field at `:19`): `agents_dir`, `db_path`, `ensure_dirs` helpers. Verify the `model_config` at `:9` still has `"extra": "ignore"` so any stray env vars (the operator's `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` from `docker-compose.yml`) are silently ignored — they MUST NOT cause `Settings()` instantiation to fail. `extra="ignore"` is the existing default; verify it still says `ignore`, not `forbid`.

3. **Add the FastAPI lifespan startup warning in `the_one/interfaces/web/app.py:lifespan`.**
   - Insertion point: between the connector warm-acquire `try:` block ending at `:173` and the `yield` at `:175`. The warning should be the LAST startup-side action before yielding control to the application body.
   - If preferred for code clarity, hoist `import os` to module-top (alongside `import json` at `:5`); the existing function-local `import os` at `:113` can stay (redundant-but-harmless) OR be removed.
   - The warning block:

     ```python
         # M11 F13 L3 — Settings.inference_provider_config_id +
         # Settings.inference_model were removed; per-connector inference
         # configuration now lives on the connector.config row (added by the
         # v26 migration; edited per-connector via the Studio connector
         # editor at F13 L4). If the operator's environment still sets either
         # legacy env var (e.g. carried over in docker-compose.yml from the
         # F7 L12 HAT), surface a one-time deprecation warning so the dead
         # env var is visible without breaking startup.
         # `import os` is already in function scope from the existing :113 local import; recommended cleanup is to hoist `import os` to module-top (alongside `import json` at :5) and remove the redundant :113 local — but the implementing agent's call.
         _legacy_pid = os.environ.get("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID")
         _legacy_model = os.environ.get("THE_ONE_INFERENCE_MODEL")
         if _legacy_pid or _legacy_model:
             logger.warning(
                 "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID and/or "
                 "THE_ONE_INFERENCE_MODEL is set in the environment, "
                 "but those env vars are no longer consulted (F13 L3 "
                 "removed Settings.inference_*). Per-connector "
                 "inference LLM configuration now lives on the "
                 "connector.config row; edit per-connector via the "
                 "Studio connector editor."
             )
     ```

   - **Why a single `logger.warning` call**: the lifespan-hook fires once per app start. A single combined warning naming both env vars + the new surface keeps the operator-facing message coherent; two separate warnings (one per env var) would produce a noisier log and the test would need two `caplog` matches.
   - **Why not module-load**: the leg-spec design decision (`flight.md` L3 sub-part (a)) — module-load runs on every test-suite import (would log spuriously per-test); lifespan fires once per app start.

4. **Refactor `the_one/connectors/_inference.py`.**

   Step-by-step:

   a. **Drop the Settings import** at `:39`: remove `from the_one.config import Settings`.

   b. **Module docstring rewrite** at `:11-21`: replace the "Provider resolution (Flight DD §9 + L7 model-source extension)" paragraph with the connector-scope rewrite per Outputs. The post-L3 paragraph follows the same shape as the pre-L3 paragraph (Provider resolution / both must be set or both unset / settings-style shadowing); only "settings" becomes "connector".

   c. **`_resolve_inference_provider` signature change** at `:141-145`:

      OLD:
      ```python
      async def _resolve_inference_provider(
          settings: Settings,
          provider_repo: LLMProviderRepository,
          fallback_provider_config_id: str | None,
          fallback_llm_model: str | None,
      ) -> LLMProvider | None:
      ```

      NEW:
      ```python
      async def _resolve_inference_provider(
          provider_repo: LLMProviderRepository,
          *,
          connector_inference_provider_config_id: str | None,
          connector_inference_model: str | None,
          fallback_provider_config_id: str | None,
          fallback_llm_model: str | None,
      ) -> LLMProvider | None:
      ```

      The `*,` keyword-only marker after `provider_repo` is intentional: forces all four resolution-input kwargs to be passed by name at the new call site, eliminating positional-arg confusion (which would be easy to introduce when the dispatcher passes 4 string-or-None kwargs in a row).

   d. **`_resolve_inference_provider` body update** at `:167-193`:

      OLD:
      ```python
          settings_id = settings.inference_provider_config_id
          settings_model = settings.inference_model
          # Pairing invariant for the settings path.
          if (settings_id is None) != (settings_model is None):
              logger.warning(
                  "inference: settings partial pair — "
                  "inference_provider_config_id=%r inference_model=%r "
                  "(both must be set or both unset)",
                  settings_id,
                  settings_model,
              )
              return None

          if settings_id is not None:
              # Settings path wins (and shadows the fallback). ...
              target_id, target_model = settings_id, settings_model
          elif (
              fallback_provider_config_id is not None
              and fallback_llm_model is not None
          ):
              target_id, target_model = fallback_provider_config_id, fallback_llm_model
          else:
              # ...
              return None
      ```

      NEW (preserves identical semantic; renames):
      ```python
          conn_id = connector_inference_provider_config_id
          conn_model = connector_inference_model
          # Pairing invariant for the connector path.
          if (conn_id is None) != (conn_model is None):
              logger.warning(
                  "inference: connector partial pair — "
                  "connector_inference_provider_config_id=%r "
                  "connector_inference_model=%r "
                  "(both must be set or both unset)",
                  conn_id,
                  conn_model,
              )
              return None

          if conn_id is not None:
              # Connector path wins (and shadows the fallback). Failures here
              # do NOT escalate to the fallback per DD §9 — operator
              # misconfiguration surfaces as silence, not as a silent fallback.
              target_id, target_model = conn_id, conn_model
          elif (
              fallback_provider_config_id is not None
              and fallback_llm_model is not None
          ):
              target_id, target_model = fallback_provider_config_id, fallback_llm_model
          else:
              # Either both connector kwargs unset AND fallback partial /
              # unset, or both connector kwargs unset with no fallback. No
              # inference provider.
              return None
      ```

      The provider-resolution + provider-construction blocks at `:195-228` stay byte-identical (they operate on the resolved `target_id` + `target_model`, which is layer-independent).

   e. **`_resolve_inference_provider` docstring update** at `:147-166`:

      Rewrite the three-path explanation (Settings path / Settings partial / Fallback path) → (Connector path / Connector partial / Fallback path). Same paragraphs, only the names change. Keep the `_PROVIDER_TYPE_MAP` cross-subsystem-import note unchanged (it's about the registry mechanism, not about Settings).

   f. **`run_engagement_inference` signature change** at `:236-243`:

      OLD:
      ```python
      async def run_engagement_inference(
          account: Connector,
          envelope: InboundEnvelope,
          session_messages: list[Message],
          settings: Settings,
          provider_repo: LLMProviderRepository,
          fallback_provider_config_id: str | None,
          fallback_llm_model: str | None,
      ) -> bool:
      ```

      NEW:
      ```python
      async def run_engagement_inference(
          account: Connector,
          envelope: InboundEnvelope,
          session_messages: list[Message],
          provider_repo: LLMProviderRepository,
          *,
          connector_inference_provider_config_id: str | None,
          connector_inference_model: str | None,
          fallback_provider_config_id: str | None,
          fallback_llm_model: str | None,
      ) -> bool:
      ```

      Same `*,` keyword-only marker pattern.

   g. **`run_engagement_inference` body update** at `:300-305`: rewrite the inner call:

      OLD:
      ```python
          provider = await _resolve_inference_provider(
              settings,
              provider_repo,
              fallback_provider_config_id,
              fallback_llm_model,
          )
      ```

      NEW:
      ```python
          provider = await _resolve_inference_provider(
              provider_repo,
              connector_inference_provider_config_id=connector_inference_provider_config_id,
              connector_inference_model=connector_inference_model,
              fallback_provider_config_id=fallback_provider_config_id,
              fallback_llm_model=fallback_llm_model,
          )
      ```

   h. **`run_engagement_inference` docstring update** at `:255-272`:

      - Drop the `settings` parameter description (the "``settings`` — :class:`the_one.config.Settings`…" bullet).
      - Add two new bullets for `connector_inference_provider_config_id` + `connector_inference_model`: "the per-connector inference LLM pair (sourced from `account.config` at the dispatcher call site; both None falls through to the fallback)."

5. **Refactor `the_one/connectors/_inbound.py`.**

   Step-by-step:

   a. **Drop the `settings: Any` parameter from `_policy_gate_decision`** at `:179`. The function body no longer needs it. The function header reads (post-edit, after the keyword-only `*` and before the return arrow):

      ```python
      async def _policy_gate_decision(
          *,
          envelope: InboundEnvelope,
          account: Connector,
          agent_config: AgentConfig,
          plugin: ConnectorPlugin,
          decision: RoutingDecision,
          session_messages: list[Message],
          conn: Any,
          encryptor: Any,
      ) -> tuple[bool, dict[str, Any]]:
      ```

   b. **Update the `run_engagement_inference` invocation** at `:254-262`:

      OLD:
      ```python
          engaged = await run_engagement_inference(
              account=account,
              envelope=envelope,
              session_messages=session_messages,
              settings=settings,
              provider_repo=provider_repo,
              fallback_provider_config_id=agent_config.provider_config_id,
              fallback_llm_model=agent_config.llm_model,
          )
      ```

      NEW:
      ```python
          engaged = await run_engagement_inference(
              account=account,
              envelope=envelope,
              session_messages=session_messages,
              provider_repo=provider_repo,
              connector_inference_provider_config_id=account.config.get(
                  "inference_provider_config_id"
              ),
              connector_inference_model=account.config.get("inference_model"),
              fallback_provider_config_id=agent_config.provider_config_id,
              fallback_llm_model=agent_config.llm_model,
          )
      ```

   c. **Update the audit-entry build at `:268-275`**:

      OLD:
      ```python
              "inference_provider_id": (
                  settings.inference_provider_config_id
                  or agent_config.provider_config_id
              ),
              "inference_model": (
                  settings.inference_model
                  or agent_config.llm_model
              ),
      ```

      NEW:
      ```python
              "inference_provider_id": (
                  account.config.get("inference_provider_config_id")
                  or agent_config.provider_config_id
              ),
              "inference_model": (
                  account.config.get("inference_model")
                  or agent_config.llm_model
              ),
      ```

   d. **Update the `_policy_gate_decision` call at `:765-775`**: drop the `settings=settings` line at `:774`. The call becomes:

      ```python
          should_engage, policy_audit = await _policy_gate_decision(
              envelope=working_envelope,
              account=account,
              agent_config=agent_config,
              plugin=plugin,
              decision=decision,
              session_messages=session_messages,
              conn=conn,
              encryptor=encryptor,
          )
      ```

   e. **DO NOT** remove `from the_one.config import settings` at `:314` — it's still consumed at `:329` for `get_encryptor(settings.data_dir)`. Verify post-edit: the `settings` symbol is reachable at `:329` (`data_dir`); only its `inference_*` usage at `:268-275, :258, :774` is removed.

6. **Update the docstring at `the_one/db/models.py:254-260`** (L2 docstring referenced "F13 L3"; L3 should leave that wording intact — the docstring already correctly describes the post-L3 state):
   - Verify the docstring at `:254-260` reads: "M11 F13 L2 — two new optional reserved flat keys: ``inference_provider_config_id`` and ``inference_model``… ``None`` at the dispatcher policy gate (F13 L3) falls through to the routed agent's LLM."
   - This is **L2 surface, intentionally referenced from L3** — the L2 docstring promised behavior that L3 ships. No edit needed UNLESS the recon at step 1 reveals drift. If drift: append a note to the L3 leg artifact "OPEN QUESTION for Flight Director" rather than silently editing L2's docstring.

7. **Rework `tests/test_connectors_inference.py`.**

   Step-by-step:

   a. **Module-level import cleanup**:
      - Remove `from the_one.config import Settings` at `:19`.
      - The other imports stay.

   b. **Delete `_empty_settings()` helper** at `:125-134`.

   c. **CULL the 2 settings-partial-pinning tests**:
      - Delete `test_resolve_inference_provider_returns_none_when_settings_id_set_but_model_unset` at `:252-269` (entire function body).
      - Delete `test_resolve_inference_provider_returns_none_when_settings_model_set_but_id_unset` at `:272-289`.

   d. **REWRITE `_patch_resolver_returning` helper** at `:374-392`:

      OLD:
      ```python
      async def _patch_resolver_returning(
          monkeypatch: pytest.MonkeyPatch,
          provider: LLMProvider | None,
      ) -> None:
          async def _fake_resolver(
              _settings: Settings,
              _repo: Any,
              _fb_id: str | None,
              _fb_model: str | None,
          ) -> LLMProvider | None:
              return provider

          monkeypatch.setattr(
              inference_mod, "_resolve_inference_provider", _fake_resolver
          )
      ```

      NEW:
      ```python
      async def _patch_resolver_returning(
          monkeypatch: pytest.MonkeyPatch,
          provider: LLMProvider | None,
      ) -> None:
          async def _fake_resolver(
              _repo: Any,
              **_kwargs: Any,
          ) -> LLMProvider | None:
              # **_kwargs absorbs all four keyword-only params
              # (connector_inference_*, fallback_*) without pinning their
              # names — keeps the fake forward-compatible with future kwarg
              # additions and avoids drift if the signature evolves.
              return provider

          monkeypatch.setattr(
              inference_mod, "_resolve_inference_provider", _fake_resolver
          )
      ```

   e. **REWRITE the 5 `_resolve_inference_provider` tests** (one rename per test):

      - `test_resolve_inference_provider_uses_settings_when_both_id_and_model_set` at `:225-249` → rename to `test_resolve_inference_provider_uses_connector_kwargs_when_both_set`; body changes:
        - Drop `settings = Settings(inference_provider_config_id="prov-a", inference_model="model-a")`.
        - Change the call to `_resolve_inference_provider` to pass kwargs:
          ```python
          provider = await _resolve_inference_provider(
              repo,  # type: ignore[arg-type]
              connector_inference_provider_config_id="prov-a",
              connector_inference_model="model-a",
              fallback_provider_config_id="prov-b",
              fallback_llm_model="model-b",
          )
          ```
        - Same final assertion: `assert isinstance(provider, MockProvider); assert provider.model == "model-a"`.

      - `test_resolve_inference_provider_falls_back_when_settings_both_unset` at `:292-309` → rename to `test_resolve_inference_provider_falls_back_when_connector_kwargs_both_unset`; same shape (`connector_inference_*=None`); final assertion `provider.model == "model-b"`.

      - `test_resolve_inference_provider_returns_none_on_settings_resolution_failure_no_fallback` at `:312-334` → rename to `test_resolve_inference_provider_returns_none_on_connector_resolution_failure_no_fallback`; `connector_inference_provider_config_id="missing-prov", connector_inference_model="model-a"`; same shape with the "working fallback exists but MUST NOT escalate" assertion.

      - `test_resolve_inference_provider_returns_none_when_fallback_id_missing` at `:337-349` → kwargs `connector_inference_*=None, fallback_provider_config_id=None, fallback_llm_model="model-b"`.

      - `test_resolve_inference_provider_returns_none_when_fallback_model_missing` at `:352-366` → kwargs `connector_inference_*=None, fallback_provider_config_id="prov-b", fallback_llm_model=None`.

   f. **REWRITE the 8+ `run_engagement_inference` tests** (one per test; mechanical signature change):

      For each test in the file body at `:395-781` calling `run_engagement_inference(...)`, the rewrite pattern is:

      OLD shape:
      ```python
      result = await run_engagement_inference(
          _account(),
          _envelope(),
          [],
          _empty_settings(),
          _StubProviderRepo(),  # type: ignore[arg-type]
          fallback_provider_config_id=None,
          fallback_llm_model=None,
      )
      ```

      NEW shape (drop settings arg, add connector kwargs):
      ```python
      result = await run_engagement_inference(
          _account(),
          _envelope(),
          [],
          _StubProviderRepo(),  # type: ignore[arg-type]
          connector_inference_provider_config_id=None,
          connector_inference_model=None,
          fallback_provider_config_id=None,
          fallback_llm_model=None,
      )
      ```

      Apply to: `test_run_engagement_inference_returns_true_on_yes` (`:395-415`), `…returns_false_on_no` (`:418-438`), `…returns_false_on_garbage` (`:441-461`), `…returns_false_on_multiword_response` (`:464-489`), `…returns_true_on_yes_with_surrounding_whitespace` (`:492-514`), `…returns_false_on_provider_exception` (`:539-556`), `…uses_channel_id_when_cache_miss` (`:648-681`), `…uses_cache_label_when_present` (`:684-727`), `…filters_history_before_prompt` (`:731-781`).

      Two `run_engagement_inference` tests construct non-empty `Settings`:
      - `test_run_engagement_inference_returns_false_on_provider_resolution_failure` at `:559-585`: replace `settings = Settings(inference_provider_config_id="missing", inference_model="model-a")` + `settings` argument with kwargs `connector_inference_provider_config_id="missing", connector_inference_model="model-a"`.
      - `test_run_engagement_inference_end_to_end_happy_path` at `:605-645`: replace `settings = Settings(inference_provider_config_id="prov-a", inference_model="model-a")` + `settings` argument with kwargs `connector_inference_provider_config_id="prov-a", connector_inference_model="model-a"`.

   g. **ADD 4 new tests** (place after the rewritten `_resolve_inference_provider` block, around `:367+` in the post-rewrite file):

      ```python
      async def test_resolve_inference_provider_returns_none_when_connector_id_set_but_model_unset() -> None:
          """Partial connector pair (id set, model unset) → log + None.
          Mirrors the F7-era settings-partial-pair test, at the new layer.
          Pairing invariant applies to the connector path.
          """
          repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

          provider = await _resolve_inference_provider(
              repo,  # type: ignore[arg-type]
              connector_inference_provider_config_id="prov-a",
              connector_inference_model=None,
              fallback_provider_config_id="prov-b",
              fallback_llm_model="model-b",
          )

          assert provider is None


      async def test_resolve_inference_provider_returns_none_when_connector_model_set_but_id_unset() -> None:
          """Partial connector pair (model set, id unset) → log + None.
          Symmetric to the id-set-only case.
          """
          repo = _StubProviderRepo({"prov-b": _mock_provider_config(provider_id="prov-b")})

          provider = await _resolve_inference_provider(
              repo,  # type: ignore[arg-type]
              connector_inference_provider_config_id=None,
              connector_inference_model="model-a",
              fallback_provider_config_id="prov-b",
              fallback_llm_model="model-b",
          )

          assert provider is None


      async def test_resolve_inference_provider_uses_connector_kwargs_over_working_fallback() -> None:
          """Connector kwargs fully set AND fallback fully set → connector
          path wins; the fallback is ignored even when both would resolve
          cleanly. This is the "connector-wins-shadows-fallback" semantic
          (renamed from F7's settings-wins shape; same precedence semantic
          at the new layer).
          """
          repo = _StubProviderRepo(
              {
                  "prov-a": _mock_provider_config(provider_id="prov-a"),
                  "prov-b": _mock_provider_config(provider_id="prov-b"),
              }
          )

          provider = await _resolve_inference_provider(
              repo,  # type: ignore[arg-type]
              connector_inference_provider_config_id="prov-a",
              connector_inference_model="model-a",
              fallback_provider_config_id="prov-b",
              fallback_llm_model="model-b",
          )

          assert isinstance(provider, MockProvider)
          assert provider.model == "model-a"


      async def test_resolve_inference_provider_returns_none_when_both_paths_unconfigured() -> None:
          """Connector kwargs None AND fallback None → None. Full both-paths-
          silence coverage (bridges what's currently scattered across the
          per-path partial tests).
          """
          repo = _StubProviderRepo({})

          provider = await _resolve_inference_provider(
              repo,  # type: ignore[arg-type]
              connector_inference_provider_config_id=None,
              connector_inference_model=None,
              fallback_provider_config_id=None,
              fallback_llm_model=None,
          )

          assert provider is None
      ```

   h. **Verify the file's section comment headers** (the dividers at `:39, :85, :137, :185, :220, :369, :517, :600`) still read accurately post-rework. Specifically the `# _resolve_inference_provider` section header at `:220` is unchanged; the function name didn't change, only its signature.

8. **Add the lifespan-warning tests to `tests/test_lifespan.py`.**

   Append after the existing tests (the file currently ends around the `test_lifespan_warm_acquires_*` block):

   ```python
   import logging as _logging
   import os as _os


   async def test_lifespan_warns_on_deprecated_inference_env_vars(
       _isolated_data_dir,
       monkeypatch: pytest.MonkeyPatch,
       caplog: pytest.LogCaptureFixture,
   ) -> None:
       """M11 F13 L3 — when either of the legacy ``THE_ONE_INFERENCE_*``
       env vars is set in the environment at startup, the lifespan emits
       exactly one ``WARNING``-level log line directing the operator to
       the Studio connector editor. The env vars are no longer consumed
       (Settings.inference_* was removed at F13 L3); the warning is a
       one-time-at-startup deprecation surface.
       """
       from the_one.interfaces.web.app import app, lifespan

       monkeypatch.setenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", "p1")
       monkeypatch.delenv("THE_ONE_INFERENCE_MODEL", raising=False)

       with caplog.at_level(_logging.WARNING, logger="the_one.interfaces.web.app"):
           async with lifespan(app):
               pass

       matching = [
           r for r in caplog.records
           if r.levelno == _logging.WARNING
           and "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID" in r.getMessage()
       ]
       assert len(matching) == 1, (
           "expected exactly one F13 L3 deprecation warning when "
           "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID is set in the "
           f"environment; saw {len(matching)} matches in "
           f"{[r.getMessage() for r in caplog.records]}"
       )


   async def test_lifespan_does_not_warn_when_inference_env_vars_unset(
       _isolated_data_dir,
       monkeypatch: pytest.MonkeyPatch,
       caplog: pytest.LogCaptureFixture,
   ) -> None:
       """M11 F13 L3 — when neither legacy env var is set, the lifespan
       does NOT emit the deprecation warning. Verifies the warning is
       silent in the common (post-cleanup) case.
       """
       from the_one.interfaces.web.app import app, lifespan

       monkeypatch.delenv("THE_ONE_INFERENCE_PROVIDER_CONFIG_ID", raising=False)
       monkeypatch.delenv("THE_ONE_INFERENCE_MODEL", raising=False)

       with caplog.at_level(_logging.WARNING, logger="the_one.interfaces.web.app"):
           async with lifespan(app):
               pass

       matching = [
           r for r in caplog.records
           if r.levelno == _logging.WARNING
           and (
               "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID" in r.getMessage()
               or "THE_ONE_INFERENCE_MODEL" in r.getMessage()
           )
       ]
       assert len(matching) == 0, (
           "expected zero F13 L3 deprecation warnings when both legacy "
           "env vars are unset; saw "
           f"{[r.getMessage() for r in matching]}"
       )
   ```

   - Both tests use the existing `_isolated_data_dir` fixture (defined at the top of the file at `:81-101`) for data-dir + DB-singleton setup.
   - Imports `logging` + `os` aliased to avoid clashing with any module-top imports the file may add later. The existing file's import block already imports `pytest`; alias is local-style consistency.
   - The matcher uses substring match on the env-var name to avoid pinning the exact warning-message wording — keeps the test resilient if the message wording is tweaked while still verifying the warning fires for the right cause.

9. **Run regression gates** (in this order; do NOT short-circuit on the first failure — collect all failures first for diagnosis).
   - `docker exec the-one pytest tests/test_connectors_inference.py -x --timeout 30 -q | tail -5` — expect green (cull + rewrite + add per spec).
   - `docker exec the-one pytest tests/test_lifespan.py -x --timeout 30 -q | tail -5` — expect green (existing tests + 2 new).
   - `docker exec the-one pytest tests/test_connectors_acl.py tests/test_connectors_routing.py tests/test_connectors_commands.py tests/test_connectors_inbound.py tests/test_connectors_discord.py -x --timeout 30 -q | tail -5` — expect green (no inference-related signature consumers in these files; verifies signature change didn't break unrelated dispatcher tests).
   - `docker exec the-one pytest tests/ --timeout 30 -q | tail -5` — full backend regression. Expect **2794 ± 2** passed. **NOTE on count reconciliation**: the flight spec's L3 target of **2784 ± 2** assumed 10-12 settings-path tests would be culled; recon (per the "Cycle-1 recon finding" below) revealed only 2 tests structurally pin the now-impossible settings-partial semantic, with the rest being mechanical signature-change rewrites. The revised target is **2794 ± 2** (L2 baseline 2790 − 2 cull + 4 add + 2 lifespan = 2794). If the count lands outside this envelope, the implementing agent investigates the variance (likely a missed rewrite or a parametrize-count delta) before signaling done.

10. **Phase 5c grep-gate verification** (per pulled-forward methodology lesson #1 + #2):
    - `git grep -nE "settings\.inference_provider_config_id|settings\.inference_model" the_one/ tests/` → expect ZERO hits. Allowed residue is NOT matched by the regex (lifespan-warning code uses `os.environ.get`, not `settings.inference_*`).
    - `git grep -nE "_empty_settings" tests/` → expect ZERO hits.
    - `git grep -nE "inference_provider_config_id|inference_model" the_one/connectors/_inbound.py` → every hit is `account.config.get("...")`; no `settings.*` prefix.
    - `git grep -nE "from the_one\.config import Settings" the_one/ tests/` → expect ZERO hits in `the_one/connectors/_inference.py` + `tests/test_connectors_inference.py`. The `Settings` symbol still exists (`the_one.config:Settings` is the class definition); other consumers may still import it (`tests/test_lifespan.py`'s `_isolated_data_dir` fixture monkeypatches `settings.data_dir` which doesn't require importing `Settings` — verify pre-edit). Any other imports of `Settings` are allowed if they don't reference `inference_*`.

11. **Flight-log update + leg status flip**.
    - Append a `### YYYY-MM-DD — L3 LANDED` entry to `missions/11-discord-connector-depth/flights/13-audit-log-inspector-and-connector-inference-config/flight-log.md` mirroring the L2 LANDED entry's shape:
      - Changes Made section enumerating the 6 source files touched + the 2 test files updated.
      - Notes section with Phase 5c grep-gate results.
      - Post-L3 totals (backend + browser).
      - Phase 2d deferral note (not committed; working tree carries L1+L2+L3 forward into L4).
    - Flip this leg's `**Status**: planning` → `landed` at the top of THIS leg artifact (the implementing agent does this as part of the post-completion checklist, AFTER all ACs PASS).
    - Mark the L3 entry in `flight.md` Checkpoints as `[x]` (line 236 currently `[ ] **L3 land**…`).
    - Mark the L3 entry in `flight.md` Legs list as `[x]` (line 266 currently `[ ] settings-removal-and-dispatcher-inference-source-refactor…`).

## Edge Cases

- **Operator's `docker-compose.yml` has the deprecated env vars set at runtime**: this is the EXPECTED case the lifespan warning addresses. The warning fires once at app start; the env vars remain in the operator's `docker-compose.yml` (operator-local-state preservation discipline); the dispatcher does NOT read them. The connector-config-set values (if any) take precedence; if no connector has them set (the post-v26 default), all always-listen connectors fall through to the routed agent's LLM. Acceptable per the v26 backfill Design Decision.

- **A test in `tests/test_lifespan.py` already monkeypatches `THE_ONE_*` env vars**: per recon, no existing test in `tests/test_lifespan.py` references `THE_ONE_INFERENCE_*`. But if a future test setting touches one, ensure the L3 lifespan-warning test still works (the test uses `monkeypatch.setenv` which is scoped to the test invocation; cross-test bleed is bounded).

- **The `from the_one.config import settings` at `_inbound.py:314` is still needed**: it's the source for `settings.data_dir` at `:329` (`encryptor = get_encryptor(settings.data_dir)`). Do NOT remove this import. The implementing agent's grep-gate verification at step 10 should explicitly check that `settings.data_dir` access at `_inbound.py:329` is preserved.

- **The `_resolve_inference_provider` function signature change is a breaking change for any direct external caller**: per recon, the ONLY caller is `run_engagement_inference` within the same module (`_inference.py:300-305`). The `tests/test_connectors_inference.py` has the only external callers (~8 tests via the helper + ~5 direct `_resolve_inference_provider` tests); all are rewritten in step 7. NO production-source consumer outside `_inference.py` calls `_resolve_inference_provider` directly (verified at recon via `grep -rn "_resolve_inference_provider" the_one/`).

- **`run_engagement_inference`'s signature change ripples to ALL test bodies that call it**: per recon, 11 tests call `run_engagement_inference` (one per `test_run_engagement_inference_*` body); all are rewritten in step 7. Production code calls it from exactly one site (`_inbound.py:254`), updated in step 5.

- **The lifespan warning is silenceable**: by design, since the operator may choose to leave the dead env vars in place until they next edit `docker-compose.yml`. The warning fires every restart UNTIL the operator removes the env vars; that's the intended UX (loud nag = operator acts). No env-var-suppression mechanism is added (would be over-engineering for a deprecation surface).

- **Pydantic `extra="ignore"`** at `the_one/config.py:9` is the existing default. After step 2, ANY env var prefixed `THE_ONE_*` that doesn't match a known field is silently ignored. This means `THE_ONE_INFERENCE_PROVIDER_CONFIG_ID` won't cause `Settings()` instantiation to raise — it just gets ignored. The lifespan warning is the operator-visible surface; Pydantic's strictness is unchanged.

- **`_empty_settings` helper is referenced ZERO times outside `test_connectors_inference.py`**: per recon, the helper is local to the file. No cross-file consumer to update.

- **A `tests/test_*.py` outside the enumerated list creates a `Settings(inference_*=...)` post-L3**: this would fail at `Settings()` construction with a Pydantic error (the field doesn't exist anymore). Per recon, NO such test exists. If a future commit between L2-LANDED and L3-design-time introduced one, the L3 implementing agent's step 1 baseline collection would expose it; fold the rewrite into L3 per Adaptation Criteria.

## Files Affected

- `the_one/config.py` — delete the 2 inference fields + their explanatory comment block.
- `the_one/interfaces/web/app.py` — add the lifespan startup deprecation-warning block (one new code section, ~12 lines inserted at the appropriate point in the `lifespan` async-context-manager).
- `the_one/connectors/_inference.py` — drop the Settings import; rewrite the module docstring's "Provider resolution" paragraph; change `_resolve_inference_provider` signature + body (preserving identical semantics, renaming to connector layer); change `run_engagement_inference` signature; update inner-call kwargs.
- `the_one/connectors/_inbound.py` — drop `settings: Any` parameter from `_policy_gate_decision`; update the `run_engagement_inference` invocation (drop `settings=settings`; add 2 connector kwargs sourced from `account.config.get`); update the audit-entry build at `:268-275` (replace `settings.inference_*` with `account.config.get(...)`); drop `settings=settings` from the `_policy_gate_decision` call. **Critical**: KEEP `from the_one.config import settings` at `:314` (still needed for `data_dir`).
- `tests/test_connectors_inference.py` — remove `from the_one.config import Settings`; delete `_empty_settings` helper; cull 2 tests; rewrite 1 helper + 17 tests for the new signature; add 4 new tests.
- `tests/test_lifespan.py` — append 2 new tests (warning fires + warning silent under unset).

## Notes for the Implementing Agent

- **Cycle-1 recon finding: test-cull count revised lower**: The flight spec's L3 target said "Cull approx 10-12 settings-path tests from `test_connectors_inference.py`" (flight.md `:167`). Recon performed at L3 design time enumerated all 24 test bodies in the file and classified each as CULL / REWRITE / ADD. The actual structurally-impossible test set is only 2 tests (the two `..._when_settings_id_set_but_model_unset` / `..._when_settings_model_set_but_id_unset` tests that pin a now-impossible settings-partial semantic). The other 17 tests that reference Settings only do so as a function-argument carrier; their semantic survives the signature change with a mechanical rewrite (drop `Settings(...)` construction; pass kwargs to the function directly). The architect cycle-1's "10-12 cull" estimate was based on a higher-level reading of "tests that reference Settings" rather than the structurally-tighter "tests whose assertion semantic becomes meaningless." The L3 leg target supersedes the flight target accordingly: net **+2** in `test_connectors_inference.py` rework (−2 cull + 0 from rewrites + 4 add) plus **+2** in `tests/test_lifespan.py` = **+4 net**, landing the total at **2794 ± 2** (vs the flight target of 2784 ± 2). The flight Adaptation Criteria's clause for "reduce cull scope correspondingly" (flight.md `:257`) explicitly covers this divergence; the leg artifact's AC-15 envelope (2792-2796) is the binding contract.

- **Operator visibility of the warning**: when the operator restarts the-one post-L3-land, they should see one log line in `docker logs the-one` indicating the env vars are dead weight. Manual verification (NOT an AC) — operator may run `docker logs the-one 2>&1 | grep -i "THE_ONE_INFERENCE_PROVIDER_CONFIG_ID"` and observe one hit per restart while their `docker-compose.yml` still carries the env var.

- **The lifespan-warning insertion point matters**: place AFTER the existing connector warm-acquire block at `:141-173` so any noise from connector-pool warm-acquire doesn't surround the warning. Place BEFORE `yield` at `:175` so it fires at startup (per design — module-load was rejected for being noisy across the test suite). The exact insertion line is between `:173` (end of the connector warm-acquire `try:` block) and `:175` (the `yield` statement).

- **The `connector_inference_*` kwarg names are intentionally verbose**: the dispatcher passes 4 string-or-None kwargs to `_resolve_inference_provider` (`connector_inference_provider_config_id`, `connector_inference_model`, `fallback_provider_config_id`, `fallback_llm_model`). Shortening to e.g. `conn_id` + `conn_model` would create ambiguity at the call site about WHICH connector field the kwarg refers to. Keeping the long names + `*` keyword-only marker forces named call sites and eliminates positional-arg confusion.

- **Reuse of the `_PROVIDER_TYPE_MAP` cross-subsystem import** at `_inference.py:38` is unchanged — that's a separate concern from Settings. Leave the import + the body section that uses it (`:213-220`) intact.

- **Docstring vs runtime code separation**: this leg's substrate edits touch real runtime code (NOT just docstrings, unlike L2's `_acl.py` byte-identical-only update). Mechanical step-by-step edits per the Implementation Guidance are the path forward; do NOT batch-rewrite the helpers without preserving every line.

- **The dispatcher invocation at `_inbound.py:765-775` calls the helper with `settings=settings` per L1 status quo**: L3's step 5d removes this kwarg. Verify post-edit the `_policy_gate_decision` call has 8 kwargs (`envelope`, `account`, `agent_config`, `plugin`, `decision`, `session_messages`, `conn`, `encryptor`), not 9.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All 16 acceptance criteria verified
- [x] Tests passing (backend 2794 ± 2; browser 443 unchanged)
- [x] Phase 5c grep gates pass (AC-9, AC-10, AC-11)
- [x] Update flight-log.md with L3 LANDED entry (changes-made, notes, post-L3 totals)
- [x] Set this leg's status to `landed` in this file's header
- [x] Check off this leg in flight.md Legs list (line 266)
- [x] Check off the L3-land Checkpoint in flight.md (line 236)
- [x] If final leg of flight: NO — L3 is mid-flight; L4 + L5 + L6 follow
- [x] Phase 2d deferral preserved (do NOT commit; working tree carries L1+L2+L3 forward into L4)

---

## Citation Audit

Citations verified against current code at leg design time (post-L2-LANDED; working-tree includes L1+L2 uncommitted edits):

| # | Citation in artifact | Current code | Status | Resolution |
|---|----------------------|--------------|--------|------------|
| 1 | `the_one/config.py:9` — `model_config = {..., "extra": "ignore"}` | `:9: model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}` | OK | — |
| 2 | `the_one/config.py:21-30` — explanatory comment block "M11 F7 L7: inference provider…" | `:21-30: # M11 F7 L7: inference provider + model for the engagement-policy gate. ...` | OK | — |
| 3 | `the_one/config.py:31-32` — the two `inference_*` fields | `:31: inference_provider_config_id: str | None = None` + `:32: inference_model: str | None = None` | OK | — |
| 4 | `the_one/interfaces/web/app.py:81-237` — `lifespan` async-context-manager | confirmed via Read offset 81-237 | OK | — |
| 5 | `the_one/interfaces/web/app.py:113` — `import os` (function-local) | `:113: import os` inside the lifespan body | OK | — |
| 6 | `the_one/interfaces/web/app.py:141-173` — connector warm-acquire `try:` block | confirmed | OK | — |
| 7 | `the_one/interfaces/web/app.py:175` — `yield` statement | `:175: yield` | OK | — |
| 8 | `the_one/connectors/_inference.py:11-21` — module-docstring Provider-resolution paragraph | confirmed via Read | OK | — |
| 9 | `the_one/connectors/_inference.py:39` — `from the_one.config import Settings` | `:39: from the_one.config import Settings` | OK | — |
| 10 | `the_one/connectors/_inference.py:141-145` — `_resolve_inference_provider` signature | `:141-146: async def _resolve_inference_provider(\n    settings: Settings,\n    provider_repo: LLMProviderRepository,\n    fallback_provider_config_id: str | None,\n    fallback_llm_model: str | None,\n) -> LLMProvider | None:` | OK | — |
| 11 | `the_one/connectors/_inference.py:147-166` — `_resolve_inference_provider` docstring three-path explanation | confirmed | OK | — |
| 12 | `the_one/connectors/_inference.py:167-168` — `settings_id = settings.inference_provider_config_id` + `settings_model = settings.inference_model` | confirmed | OK | — |
| 13 | `the_one/connectors/_inference.py:170-193` — settings-wins-shadows-fallback semantic body | confirmed | OK | — |
| 14 | `the_one/connectors/_inference.py:195-228` — provider-resolution + provider-construction blocks | confirmed (try/except chains) | OK | — |
| 15 | `the_one/connectors/_inference.py:236-243` — `run_engagement_inference` signature | `:236-244: async def run_engagement_inference(\n    account: Connector,\n    envelope: InboundEnvelope,\n    session_messages: list[Message],\n    settings: Settings,\n    provider_repo: LLMProviderRepository,\n    fallback_provider_config_id: str | None,\n    fallback_llm_model: str | None,\n) -> bool:` | OK | — |
| 16 | `the_one/connectors/_inference.py:255-272` — `run_engagement_inference` docstring (parameters) | confirmed | OK | — |
| 17 | `the_one/connectors/_inference.py:300-305` — internal call to `_resolve_inference_provider(settings, ...)` | `:300-305: provider = await _resolve_inference_provider(\n    settings,\n    provider_repo,\n    fallback_provider_config_id,\n    fallback_llm_model,\n)` | OK | — |
| 18 | `the_one/connectors/_inbound.py:141` — `from the_one.connectors._inference import run_engagement_inference` | confirmed | OK | — |
| 19 | `the_one/connectors/_inbound.py:169-180` — `_policy_gate_decision` signature with `settings: Any` parameter | confirmed `:179: settings: Any,` | OK | — |
| 20 | `the_one/connectors/_inbound.py:254-262` — `run_engagement_inference` invocation passing `settings=settings` | confirmed `:258: settings=settings,` | OK | — |
| 21 | `the_one/connectors/_inbound.py:268-275` — audit-entry build reading `settings.inference_*` | confirmed `:269: settings.inference_provider_config_id` + `:273: settings.inference_model` | OK | — |
| 22 | `the_one/connectors/_inbound.py:314` — `from the_one.config import settings` (function-local import) | `:314: from the_one.config import settings` | OK | — |
| 23 | `the_one/connectors/_inbound.py:329` — `get_encryptor(settings.data_dir)` | confirmed | OK | — |
| 24 | `the_one/connectors/_inbound.py:765-775` — `_policy_gate_decision` call passing `settings=settings` | confirmed `:774: settings=settings,` | OK | — |
| 25 | `the_one/db/models.py:254-260` — L2's docstring referencing "F13 L3" | confirmed (post-L2) | OK | — |
| 26 | `tests/test_connectors_inference.py:19` — `from the_one.config import Settings` | confirmed | OK | — |
| 27 | `tests/test_connectors_inference.py:125-134` — `_empty_settings()` helper | confirmed | OK | — |
| 28 | `tests/test_connectors_inference.py:225-249` — `test_resolve_inference_provider_uses_settings_when_both_id_and_model_set` (REWRITE) | confirmed | OK | — |
| 29 | `tests/test_connectors_inference.py:252-269` — `test_..._when_settings_id_set_but_model_unset` (CULL) | confirmed | OK | — |
| 30 | `tests/test_connectors_inference.py:272-289` — `test_..._when_settings_model_set_but_id_unset` (CULL) | confirmed | OK | — |
| 31 | `tests/test_connectors_inference.py:292-309` — `test_..._falls_back_when_settings_both_unset` (REWRITE) | confirmed | OK | — |
| 32 | `tests/test_connectors_inference.py:312-334` — `test_..._returns_none_on_settings_resolution_failure_no_fallback` (REWRITE) | confirmed | OK | — |
| 33 | `tests/test_connectors_inference.py:337-349` — `test_..._returns_none_when_fallback_id_missing` (REWRITE) | confirmed | OK | — |
| 34 | `tests/test_connectors_inference.py:352-366` — `test_..._returns_none_when_fallback_model_missing` (REWRITE) | confirmed | OK | — |
| 35 | `tests/test_connectors_inference.py:374-392` — `_patch_resolver_returning` helper (REWRITE) | confirmed | OK | — |
| 36 | `tests/test_connectors_inference.py:395-415` — `test_run_engagement_inference_returns_true_on_yes` (REWRITE) | confirmed | OK | — |
| 37 | `tests/test_connectors_inference.py:418-438` — `test_...returns_false_on_no` (REWRITE) | confirmed | OK | — |
| 38 | `tests/test_connectors_inference.py:441-461` — `test_..._returns_false_on_garbage` (REWRITE) | confirmed | OK | — |
| 39 | `tests/test_connectors_inference.py:464-489` — `test_..._returns_false_on_multiword_response` (REWRITE) | confirmed | OK | — |
| 40 | `tests/test_connectors_inference.py:492-514` — `test_..._returns_true_on_yes_with_surrounding_whitespace` (REWRITE) | confirmed | OK | — |
| 41 | `tests/test_connectors_inference.py:539-556` — `test_..._returns_false_on_provider_exception` (REWRITE) | confirmed | OK | — |
| 42 | `tests/test_connectors_inference.py:559-585` — `test_..._returns_false_on_provider_resolution_failure` (REWRITE) — constructs `Settings(inference_provider_config_id="missing", inference_model="model-a")` | confirmed at `:569-572` | OK | — |
| 43 | `tests/test_connectors_inference.py:605-645` — `test_..._end_to_end_happy_path` (REWRITE) — constructs `Settings(inference_provider_config_id="prov-a", inference_model="model-a")` | confirmed at `:616-619` | OK | — |
| 44 | `tests/test_connectors_inference.py:648-681` — `test_..._uses_channel_id_when_cache_miss` (REWRITE) | confirmed | OK | — |
| 45 | `tests/test_connectors_inference.py:684-727` — `test_..._uses_cache_label_when_present` (REWRITE) | confirmed | OK | — |
| 46 | `tests/test_connectors_inference.py:731-781` — `test_..._filters_history_before_prompt` (REWRITE) | confirmed | OK | — |
| 47 | `tests/test_lifespan.py:81-101` — `_isolated_data_dir` fixture | confirmed | OK | — |
| 48 | `tests/test_lifespan.py:104-130` — existing `test_lifespan_drains_session_registry` (model for new lifespan tests) | confirmed | OK | — |

48 citations verified against current code at leg design time. The L3 surface is well-bounded: every cited site exists at the cited line as described. **One semantic note**: the flight-spec citations `_inference.py:151-194` and `_inference.py:167-194` (flight.md L3 sub-part (b)) are slight under-counts — the actual `_resolve_inference_provider` body spans `:141-228` (declaration + body + provider-resolution try/except + provider-construction try/except). The leg artifact uses the post-recon exact ranges; no drift to repair (the flight spec's narrower range still encloses the semantic-change site at `:167-193`).
