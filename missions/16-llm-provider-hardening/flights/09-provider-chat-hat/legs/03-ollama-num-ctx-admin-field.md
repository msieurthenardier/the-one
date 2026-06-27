# Leg: ollama-num-ctx-admin-field

**Status**: completed
**Flight**: [HAT — Provider Chat Sweep](../flight.md)

> **Completed (2026-06-27, shipping in 0.2.12).** Editable per-provider Ollama
> "Context Window" field (info-icon tooltip, required, default 32768), precedence
> per-provider → env → default clamped to advertised. Verified live on the dev
> instance by the operator; unit + browser tests green. Per-model num_ctx noted for
> the deferred compaction mission. Ships in 0.2.12.

## Objective
Make the Ollama runtime context window (`num_ctx`) an editable per-provider field in the
Administration UI, so the operator can trade window size for decode speed without setting an
environment variable.

## Context
- HAT finding **F09-05**: a long local-model conversation (ministral-3:8b on Ollama, model
  only partially in VRAM) slows to ~1 token / 5 s at ~91% of a 32k window — partial CPU
  offload + a large KV cache. A smaller `num_ctx` lets more model layers fit in VRAM (faster
  decode) at the cost of shorter conversations. This leg is a **mitigation**, not a cure —
  the real fix (conversation compaction) stays deferred (mission Known Issue).
- Today `num_ctx` is resolved only from env `THE_ONE_OLLAMA_NUM_CTX` (default 32768),
  clamped to the model's advertised window (`effective_num_ctx`, `ollama_provider.py:62-79`).
  There is no per-provider control and no UI.
- `LLMProviderConfig.config` (`db/models.py:18-31`) is already a free-form dict persisted as
  JSON (`llm_providers.config`), and the OpenRouter provider already stores
  `config.referer`/`config.title` there — same pattern to follow. **No model/schema change.**

## Inputs
- `the_one/llm/ollama_provider.py` — `effective_num_ctx(advertised)` (`:62-79`),
  `_resolve_max_context_tokens` (`:172`), `OllamaProvider.__init__` (takes `config`).
- `the_one/interfaces/web/app.py:1205` (`_ensure_ollama_model_loaded`) and
  `the_one/interfaces/web/api.py:4368` (`load_model`) — both call `effective_num_ctx`.
- Admin form: `static/js/areas/admin.js` `TYPE_DEFAULTS` (`:182-189`),
  `static/js/areas/admin/provider-editor.js` `renderConnectionFields` (`:114-161`) +
  `collectFormData` (`:438-510`, OpenRouter `config.*` precedent at `:484-507`).

## Outputs
- `config.num_ctx` (optional positive int) on an Ollama provider, editable in Admin,
  persisted, and used as the highest-precedence source for the runtime window.
- Precedence (low→high): default → env `THE_ONE_OLLAMA_NUM_CTX` → **per-provider
  `config.num_ctx`**; the result is clamped to the model's advertised window.

## Acceptance Criteria
- [ ] An Ollama provider in Administration shows a **"Context Window"** integer field
      (shown ONLY for `ollama`-type providers), with an **info-icon tooltip** (reusing the
      `field-info-icon` pattern): "A larger window allows longer conversations but will slow
      down on partial-GPU setups because fewer layers fit in VRAM".
- [ ] The field is **required** and pre-filled with the default **32768** (or the provider's
      existing `config.num_ctx`); empty is rejected client-side. (No more "blank = default".)
- [ ] Setting it persists (`config.num_ctx`) across reload and round-trips through the
      provider create/update API.
- [ ] When set, it is used as the runtime `num_ctx` for native `/api/chat` and model
      preload, taking precedence over `THE_ONE_OLLAMA_NUM_CTX`, still clamped to the
      advertised window; when unset, behavior is unchanged (env → default → clamp).
- [ ] Invalid input (non-positive / non-integer) is rejected client-side (and ignored/refused
      server-side) rather than persisting a bad value.
- [ ] `max_context_tokens` / the telemetry overlay denominator reflect the effective value
      (so % context tracks the window actually allocated).
- [ ] Tests: provider config `num_ctx` round-trip + precedence resolution; `ruff` clean;
      `make test` green. If the admin form gets a browser test, DOM assertions only.

## Implementation Guidance
1. **Resolution (ollama_provider.py).** Extend `effective_num_ctx` to accept an optional
   per-provider value, e.g. `effective_num_ctx(advertised, configured=None)`: if `configured`
   is a positive int, use it (clamped to `advertised`); else fall back to the existing
   env→default logic. Have `OllamaProvider` read `config.get("num_ctx")` (coerce/validate to
   positive int or None) in `__init__` and feed it into `_resolve_max_context_tokens`.
2. **Web call sites.** `_ensure_ollama_model_loaded` (`app.py:1205`) and `load_model`
   (`api.py:4368`) must pass the provider's `config.num_ctx` into `effective_num_ctx` so the
   preloaded runner and the gauge use the same value the provider will generate with.
3. **Admin form.** Add `showNumCtx: true` to `TYPE_DEFAULTS['ollama']`; render an optional
   integer field (`data-field="config.num_ctx"`) in `renderConnectionFields` gated on
   `defaults.showNumCtx`; collect it in `collectFormData` following the OpenRouter
   `config.*` precedent (parse int, validate > 0, add to `payload.config` only when present).
   Show/hide on type-change like base_url/api_key.
4. **Validation.** Reject non-positive/non-int both client-side and server-side (coerce in
   the provider; don't crash on a stray string in `config`).
5. **Tests.** Add to `tests/test_provider_repository.py` (config round-trip with num_ctx) and
   a resolution/precedence unit test near the ollama provider tests; verify clamp-to-advertised.

## Edge Cases
- **num_ctx > advertised window** → clamp to advertised (never exceed model support).
- **Empty/removed field** → falls back to env/default (no persisted `num_ctx` key).
- **Stale runner**: changing num_ctx should take effect on the next model (re)load; document
  that an already-loaded runner keeps its window until reloaded (the preload path handles new
  sessions). Do not force a disruptive reload here.
- **Non-ollama providers** never show or store the field.

## Files Affected
- `the_one/llm/ollama_provider.py` — resolution + config read.
- `the_one/interfaces/web/app.py`, `the_one/interfaces/web/api.py` — pass config num_ctx.
- `the_one/interfaces/web/static/js/areas/admin.js` + `admin/provider-editor.js` — form field.
- `tests/` — repository round-trip + resolution/precedence tests.

---

## Post-Completion Checklist
- [ ] Acceptance criteria verified (unit + manual)
- [ ] Update flight-log.md (F09-05 mitigation shipped)
- [ ] Set leg status `completed` (after live re-verify on 0.2.11)
- [ ] Check off / add this leg in flight.md
- [ ] Commit (batched into the 0.2.11 release)
