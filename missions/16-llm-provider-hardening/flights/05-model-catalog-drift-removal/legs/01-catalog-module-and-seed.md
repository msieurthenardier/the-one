# Leg: catalog-module-and-seed

**Status**: completed
**Flight**: [Model-Catalog Drift Removal](../flight.md)

## Objective

Add the leaf model-catalog module (typed, fail-open `context_window_for()` lookup),
its bundled seed JSON, the models.dev generator script + `make` target, and the
package-data wiring — the foundation every later leg builds on. **No provider or
endpoint is rewired in this leg** (that's legs 3–5) and **no runtime refresh loop
is added** (that's leg 2).

## Context

- Flight DD1/DD2: context windows for OpenAI and Anthropic come from a catalog
  generated from **models.dev** (their own `/models` APIs expose no
  `context_length`). This leg ships the catalog as a committed **seed**; leg 2
  adds the on-disk cache + daily refresh that layer *over* this seed.
- Flight DD3: drift must be loud — a **whole-catalog parse/load failure** logs
  WARN (this leg). The per-model-miss WARN lives at the provider resolvers (legs
  3–4), not here; `context_window_for()` returns `None` on a miss without logging,
  so the caller owns the fallback decision and there's no double-logging.
- Flight DD6: the seed must ship in non-editable installs → add it to
  `[tool.setuptools.package-data]` (today only globs `interfaces/web/static/**` at
  `pyproject.toml:71`).
- **Reference shape to mirror**: `the_one/llm/openrouter_api.py` —
  `OpenRouterModelEntry` (Pydantic, `extra="allow"`), `get_model_context_length`
  fail-open returning `None` (`:165-192`). Match that idiom (typed entries,
  `None` on miss, no exceptions escape).
- The seed must, at minimum, **not regress** the windows the current
  `OPENAI_MODEL_CONTEXT` table resolves (`openai_provider.py:46-59`) — leg 3
  deletes that table and relies on this seed. Capture Anthropic too (current
  default `claude-sonnet-4-6` is natively 1M; Haiku-class is 200k).

## Inputs

- `the_one/llm/openrouter_api.py` exists (the fail-open/typed reference).
- `the_one/llm/openai_provider.py` `OPENAI_MODEL_CONTEXT` (the windows the seed
  must cover for OpenAI).
- `scripts/derive_brand_assets.py` + the `brand-assets` Makefile target (the
  generator-script + `make`-target convention to mirror, `Makefile:100-105`).
- `pyproject.toml` `[tool.setuptools.package-data]` (`:70-71`).
- Network access to models.dev (to generate the seed; see Edge Cases for the
  offline fallback).

## Outputs

- `the_one/llm/model_catalog.py` — the loader + `context_window_for()` lookup.
- `the_one/llm/data/model_catalog.json` — the committed seed (with `generated_at`
  + `source` stamp).
- `scripts/refresh_model_catalog.py` — regenerates the seed from models.dev.
- `Makefile` — a `refresh-model-catalog` target.
- `pyproject.toml` — package-data updated to ship `the_one/llm/data/*.json`.
- `tests/test_model_catalog.py` — unit tests.

## Acceptance Criteria
- [x] `the_one/llm/model_catalog.py` exposes `context_window_for(provider: str,
      model: str) -> int | None` that returns the correct window for a known
      OpenAI model, a known Anthropic model, and `None` for an unknown model —
      never raising. **Both** miss shapes return `None` and are tested: (a) the
      provider section exists but the model is absent; (b) the provider section
      itself is absent.
- [x] OpenAI **longest-prefix-wins** matching is preserved: a dated/variant id
      (e.g. `gpt-4o-2024-05-13`) resolves to the same window the current
      `OPENAI_MODEL_CONTEXT` table would give (`128000`), and explicit variants
      don't collapse onto a shorter prefix. Test **both** discriminating cases:
      `gpt-4-turbo` → `128000` (not the `gpt-4` 8192 entry) **and**
      `gpt-4-turbo-preview` → `128000` (a model that starts with `gpt-4-turbo`,
      not bare `gpt-4` — proves the longest-prefix port didn't collapse).
- [x] The seed `model_catalog.json` covers **all twelve** current
      `OPENAI_MODEL_CONTEXT` entries with **no regression** — every one of
      `gpt-4o`, `gpt-4-turbo`, `gpt-4-32k`, `gpt-4-vision-preview`,
      `gpt-4-0125-preview`, `gpt-4-1106-preview`, `gpt-4`, `gpt-3.5-turbo-instruct`,
      `gpt-3.5-turbo-16k`, `gpt-3.5-turbo`, `o1`, and **`o3-mini`** resolvable to
      its existing window — plus Anthropic entries including `claude-sonnet-4-6`
      → `1000000` and a Haiku-class entry → `200000`.
- [x] A malformed/unparseable catalog file makes `context_window_for()` return
      `None` (fail-open) **and** logs a WARN (the DD3 whole-catalog-failure path).
- [x] The seed carries a `generated_at` (date) and `source` field.
- [x] `scripts/refresh_model_catalog.py` regenerates the seed from models.dev
      (filtered to openai + anthropic), is idempotent, and is wrapped by `make
      refresh-model-catalog` (mirroring `brand-assets`).
- [x] `pyproject.toml` ships `the_one/llm/data/*.json` via package-data —
      **extend** the existing list (do not replace it), resulting line:
      `the_one = ["interfaces/web/static/**/*", "llm/data/*.json"]`. The existing
      static glob must still be present.
- [x] `tests/test_model_catalog.py` covers: known-openai, known-anthropic,
      longest-prefix variant, unknown→None, malformed→None+WARN, and seed-shape
      validity. All pass.
- [x] No provider or endpoint behavior changes in this leg (grep confirms
      `OPENAI_MODEL_CONTEXT` is still present and untouched — leg 3 removes it).

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_model_catalog.py -x --timeout 30` → all green.
- `python -c "from the_one.llm.model_catalog import context_window_for; print(context_window_for('openai','gpt-4o-2024-08-06'), context_window_for('anthropic','claude-sonnet-4-6'), context_window_for('openai','nonexistent-xyz'))"` → `128000 1000000 None`.
- `make refresh-model-catalog` (with network) regenerates the seed; `git diff` shows only `generated_at`/data churn, no schema break.
- `python -c "import json; d=json.load(open('the_one/llm/data/model_catalog.json')); assert 'generated_at' in d and 'providers' in d"` → no assertion error.
- Confirm the existing suite still imports cleanly: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_llm_max_context.py -x --timeout 30` → unchanged (leg 1 must not touch provider behavior).

## Implementation Guidance

1. **Define the catalog data shape** (`model_catalog.json`). Shape (the `openai`
   section must contain **all twelve** current table entries — shown in full):
   ```json
   {
     "generated_at": "2026-06-19",
     "source": "models.dev",
     "providers": {
       "openai": {
         "gpt-4o": 128000, "gpt-4-turbo": 128000, "gpt-4-32k": 32768,
         "gpt-4-vision-preview": 128000, "gpt-4-0125-preview": 128000,
         "gpt-4-1106-preview": 128000, "gpt-4": 8192,
         "gpt-3.5-turbo-instruct": 4096, "gpt-3.5-turbo-16k": 16385,
         "gpt-3.5-turbo": 16385, "o1": 200000, "o3-mini": 200000
       },
       "anthropic": {"claude-sonnet-4-6": 1000000, "claude-3-5-haiku-latest": 200000}
     }
   }
   ```
   Keys are **bare** canonical model ids (no `provider/` namespace) → context
   window (ints). Confirm the exact models.dev field name for the window when
   writing the generator (it may nest limits, e.g. `limit.context`); adapt the
   generator to project it to this flat shape. The runtime loader reads only this
   flat shape, decoupling it from models.dev's wire structure. **If models.dev has
   `null`/absent context for a model that appears in `OPENAI_MODEL_CONTEXT`, use
   the table value — never omit a currently-covered model or shrink its window.**

   > **This seed is committed source data, NOT a test snapshot.** The global
   > "don't commit golden files" rule (visual/jest snapshots) does **not** apply —
   > this JSON ships as package-data (DD6) and must be in git. Do not gitignore
   > `the_one/llm/data/`.

2. **Write `model_catalog.py`**:
   - A typed loader (Pydantic or a small validated parse) mirroring
     `openrouter_api.OpenRouterModelEntry`'s `extra="allow"` tolerance.
   - **Document the contract in the module docstring**: callers pass the **bare**
     model id (no `provider/` prefix); the runtime lookup never strips — stripping
     is the generator's job only.
   - Module-level memoization of the parsed seed (load once). Expose the reset
     seam as a **bare module-level function** (e.g. `_reset_for_tests(catalog=None)`
     that replaces the memoized instance) — NOT a class attribute — so tests can
     `monkeypatch` it without importing internals. **Leave a clear seam** for leg 2
     to insert cache→seed precedence (e.g. a `_load_catalog()` that leg 2 extends
     to check `settings.data_dir / "model_catalog.json"` first; `config.py` exposes
     `settings.data_dir`).
   - `context_window_for(provider, model)`: look up `providers[provider]`; try
     **exact match**, then **longest-prefix-wins** over that provider's keys
     (sort keys by length desc — same algorithm as the resolver at
     `openai_provider.py:94-104`, loop body `:100-103`). Return the int or `None`.
   - Wrap the load in try/except: on any parse/IO failure log
     `logger.warning(...)` once and treat the catalog as empty (so lookups
     return `None`). Do **not** let exceptions escape.

3. **Write `scripts/refresh_model_catalog.py`** mirroring
   `scripts/derive_brand_assets.py`'s structure (module docstring, `if __name__`
   guard, host-native via venv): fetch models.dev (`httpx.get`), filter to
   `openai` + `anthropic`, project to the flat shape, stamp `generated_at` (pass
   the date in or read from the system — this is a dev script, not runtime, so
   `datetime` is fine here), write `the_one/llm/data/model_catalog.json` with
   stable key ordering (`sort_keys=True`) for clean diffs.

4. **Add the Makefile target** `refresh-model-catalog` (`.PHONY`, `## ` help
   line) running the script via the repo venv, mirroring `brand-assets`
   (`Makefile:100-102`).

5. **Update `pyproject.toml`** package-data — `mkdir -p the_one/llm/data/` first
   (the dir doesn't exist yet; setuptools needs the file present), then **extend**
   the existing single-entry list (don't drop the static glob):
   `the_one = ["interfaces/web/static/**/*", "llm/data/*.json"]`
   (`pyproject.toml:70-71`). No `__init__.py` is needed in `data/` —
   `packages.find` already includes `the_one.llm` and package-data globs
   non-package subdirs.

6. **Tests** (`tests/test_model_catalog.py`): the six cases in the acceptance
   criteria. For malformed→WARN, point the loader at a temp bad file (via the
   leg-1 reset/override seam) and assert `caplog` captured a WARNING and the
   lookup returned `None`.

## Edge Cases
- **models.dev unreachable when generating the seed**: the agent's environment
  may not have network. If `make refresh-model-catalog` can't reach models.dev,
  **hand-author** the seed covering (a) every model in the current
  `OPENAI_MODEL_CONTEXT` with its existing window, and (b) the Anthropic entries
  (`claude-sonnet-4-6` 1M, a Haiku-class 200k, plus the other current Claude
  families at their real windows) — and record in the flight log that the seed
  was hand-authored because models.dev was unreachable, with the script left
  ready for a later real refresh. Acceptance does not require a live fetch in this
  leg; it requires a correct seed + a runnable script.
- **models.dev gives a smaller window than the current table** for some OpenAI
  model: prefer the current table's value if models.dev would *regress* a known
  model, and note the discrepancy in the flight log (models.dev may lag). Never
  ship a seed that shrinks a currently-correct window.
- **Provider key casing / id drift** (`gpt-4o` vs `openai/gpt-4o`): models.dev may
  namespace ids; strip any `provider/` prefix when projecting so runtime lookups
  use bare model ids (the ids the SDKs return).
- **Empty/missing provider section**: `context_window_for('openai', x)` when the
  `openai` section is absent returns `None`, not an error.

## Files Affected
- `the_one/llm/model_catalog.py` - new module (loader + lookup)
- `the_one/llm/data/model_catalog.json` - new committed seed
- `scripts/refresh_model_catalog.py` - new generator
- `Makefile` - new `refresh-model-catalog` target
- `pyproject.toml` - package-data adds `llm/data/*.json`
- `tests/test_model_catalog.py` - new tests

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

> **Deferred-commit flight**: do NOT commit or signal `[COMPLETE:leg]` at the end
> of this leg. After implementation, update the flight log + leg status to
> `landed` and signal `[HANDOFF:review-needed]`. The single flight-wide review +
> commit happens after the last autonomous leg.

- [x] All acceptance criteria verified
- [x] Tests passing (`tests/test_model_catalog.py`; `test_llm_max_context.py`
      unchanged)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed` (in this file's header)
- [x] Check off this leg in flight.md
