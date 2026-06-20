# Flight: Model-Catalog Drift Removal

**Status**: landed
**Mission**: [LLM Provider Layer Hardening & Capability Completeness](../../mission.md)

## Contributing to Criteria
- [x] Model context-window limits for OpenAI and Anthropic are sourced without a
      hand-maintained per-model table that silently drifts. (The sourcing
      mechanism — live fetch with caching vs. a generated/cached catalog — is
      deliberately left to the open question; OpenAI in particular cannot be
      live-fetched the way Ollama/OpenRouter are, since its API exposes no
      context-window field.) **MET** — built-in catalog (bundled seed + daily
      models.dev refresh into an on-disk cache), resolved locally cache→seed→default.
- [x] No agent framework is added and the provider layer still wraps official
      SDKs; the `LLMProvider` contract and the provider-shape-portability
      convention are preserved. *(verified-as-boundary: this flight adds a data
      module + a background refresh loop, no framework, SDKs still wrapped.)*

---

## Pre-Flight

### Objective

Replace the two hand-maintained, silently-drifting context-window sources for
OpenAI and Anthropic — the `OPENAI_MODEL_CONTEXT` longest-prefix table (and its
duplicate in the Studio model-list endpoint) and Anthropic's flat `200_000`
constant — with a single **built-in model catalog that refreshes itself on a
regular cadence at runtime**, so installs stay current without a redeploy. OpenAI
and Anthropic publish no `context_length` through their own `/models` APIs, so a
catalog (sourced from models.dev) is the only viable source for them. The catalog
ships as a **bundled seed** (always present, offline-safe) and is kept fresh by a
**daily background refresh loop** that pulls models.dev into an on-disk cache in
the per-user data dir — mirroring the existing chat-history purge loop. Because
the cache persists on disk and the seed is always bundled, context-window
reporting **survives restarts offline**: reopening an old chat resolves the right
window with no network call. The Anthropic "all models are 200k" assumption — now
false, since current Claude models are natively 1M — is corrected simply by
reporting the catalog's per-model window (no special-casing required).

### Open Questions
- [x] **Catalog mechanism: live fetch vs. generated artifact vs. runtime refresh**
      → see DD1. Resolved (operator, mid-planning): **built-in, runtime-refreshed
      on a daily cadence** — bundled seed + on-disk cache fetched from models.dev
      by a background loop. Not a build-time-only artifact (would require a
      redeploy to update); not a per-call live fetch (OpenAI/Anthropic expose no
      context field, and it would break offline).
- [x] **Upstream data source** → see DD2. Resolved: `models.dev` (operator
      deferred to "best practice, long-term"; LiteLLM JSON is the documented
      fallback).
- [x] **Freshness machinery scope** → see DD3. Resolved (operator): runtime daily
      refresh loop is the primary mechanism; plus a loud unknown-model WARN, a
      loud whole-catalog-parse-failure WARN, and a `fetched_at`/`generated_at`
      stamp; `make refresh-model-catalog` regenerates the committed seed (dev
      convenience). No CI staleness gate.
- [x] **Anthropic 1M scope** → see DD4. **Resolved (operator, mid-planning):
      catalog-only now, header-gated 1M revisited later.** Design-review found that
      current Claude models (incl. the default `claude-sonnet-4-6`) have a 1M
      window **natively — no `context-1m` beta header, no above-200k premium**,
      reversing the planning-interview premise. This flight **reports the catalog's
      per-model window and sends no header**; evaluating header-gated 1M (for any
      model that still requires the dated header) is folded into the planned
      extended-thinking/capability flight, where request-path capability work
      already lives (recorded as a mission Open Question).
- [ ] **models.dev response shape / endpoint URL** — exact field names and the
      fetch URL must be confirmed against the live dataset when the refresh
      loop/script are written (leg 01/02). Fallback: LiteLLM
      `model_prices_and_context_window.json`.
- [ ] **OpenAI model-id matching strategy** — catalog stores canonical ids, but
      the OpenAI API returns dated/variant ids (`gpt-4o-2024-08-06`). Decide
      exact-match-then-family-prefix-fallback vs. pure longest-prefix in leg 03
      design (preserve today's longest-prefix-wins outcomes at minimum).
- [x] **Cache location** → resolved: `settings.data_dir / "model_catalog.json"`
      (`config.py:68` — `platformdirs.user_data_dir("the-one")`, same writable dir
      as `the-one.db` and `agents/`). Persists across restarts; per-user; never
      the read-only package dir.
- [x] **Refresh cadence** → resolved: daily (24h), due-based with startup
      catch-up, mirroring `_get_purge_check_interval` / `_chat_history_purge_loop`
      (`app.py:609-680`). Interval env-overridable like the purge loop. Confirm if
      a different cadence is wanted.

### Design Decisions

**DD1 — Built-in catalog, runtime-refreshed on a cadence (seed + on-disk cache)**:
Context windows for OpenAI and Anthropic come from a catalog that is (a) **bundled
as a committed seed** inside the package (e.g. `the_one/llm/data/model_catalog.json`),
and (b) **refreshed at runtime on a daily cadence** by a background loop that
fetches models.dev and writes an on-disk cache at `settings.data_dir /
"model_catalog.json"`. The resolver reads **cache → seed → class default**, never
blocking on the network.
- Rationale: the operator wants installs to "stay up-to-date without a new
  deploy," which a build-time-only artifact can't do (it would need a redeploy to
  refresh). A per-call live fetch is impossible for OpenAI/Anthropic (their
  `/models` APIs expose no `context_length` — `openai_provider.py:37-38`;
  `api.py:4250` already falls back to a constant) and would break offline. A
  bundled seed + persisted cache satisfies the operator's **"survive restarts on
  an old chat, offline"** requirement: the `/context-window` endpoint
  (`api.py:472`) and the usage WS event (`app.py:1355/1391`) resolve from local
  files every time.
- Trade-off: a background task + a writable cache file + a network call on a
  cadence. All three have direct in-repo precedent (the chat-history purge loop;
  `settings.data_dir`; `openrouter_api.py`'s cached fetch).

**DD2 — Upstream source is `models.dev`**: Both the committed seed and the runtime
refresh are *generated from* models.dev (a community-maintained, openly-licensed,
multi-provider models dataset), filtered to OpenAI and Anthropic entries.
- Rationale: operator deferred the choice to "best practice, long-term."
  models.dev is openly licensed and covers all providers in play; we vendor a
  snapshot as the seed and fetch the same shape at runtime — there is **no
  framework dependency** (neither models.dev nor litellm is imported as a library;
  the runtime fetch is a plain `httpx` GET like `openrouter_api.py`).
- Trade-off: a community dataset can lag or restructure. LiteLLM's
  `model_prices_and_context_window.json` is the documented fallback source.

**DD3 — Freshness made loud, not silent**: The runtime daily refresh loop is the
primary freshness mechanism. Plus: (a) a **WARN log** when a model is not found in
the catalog and the resolver falls back to the class default — today that fallback
is silent (the "silently drifts" the criterion names); (b) a **WARN log** when the
whole catalog (cache or seed) fails to parse/validate — distinct from a per-model
miss, so a corrupt fetch is observable rather than silently defaulting (closes the
design-review's blanket-`except` concern at `base.py:293`); (c) a `fetched_at` /
`generated_at` stamp in the JSON; (d) `make refresh-model-catalog` to regenerate
the committed seed from models.dev.
- Rationale: turns drift from invisible to observable and self-healing on cadence.
- Trade-off: no CI staleness gate (operator chose not to fail a test on catalog
  age) — staleness is surfaced and auto-refreshed, not enforced in CI.

**DD4 — Report the catalog's per-model window; send no beta header** *(resolved:
catalog-only now, header-gated 1M deferred to the capability flight)*: The catalog
(from models.dev) carries
the correct per-model window — 1M for current Claude models, 200k for Haiku-class,
the right value for each OpenAI model — and the providers simply report it. No
`context-1m` beta header is sent.
- Rationale: design-review verified that current Claude models (incl. the default
  `claude-sonnet-4-6`, `anthropic_provider.py:79`) have a **native 1M window with
  no beta header and no above-200k premium**. The planning-interview premise ("we
  don't send the header, so 1M isn't real") was wrong for these models. Reporting
  the catalog value is therefore both correct and truthful with zero request-path
  change.
- Trade-off / scope note: this **drops** the header-sending sub-project the
  planning interview opted into. If a specific model is later found to require the
  dated `context-1m-*` header to unlock 1M, that becomes a deferred capability
  follow-up (a request-path change, out of this flight's catalog-sourcing scope).
  Keeps this flight a data-sourcing flight, not a request-path change.

**DD5 — One catalog lookup, both consumers unified**: The OpenAI prefix table
lives in two places today — the provider resolver (`openai_provider.py:94-104`)
and a verbatim re-implementation in the Studio model-list endpoint
(`api.py:4216-4233`, `_openai_ctx`). Both are replaced by a single shared lookup in
the new leaf catalog module; `OPENAI_MODEL_CONTEXT` is deleted. The Anthropic
Studio branch (`api.py:4250`, reads `AnthropicProvider.max_context_tokens`) also
moves to the catalog lookup.
- Rationale: a duplicated table is two drift surfaces. The catalog module is a
  leaf imported by both the llm providers and the web layer — design-review
  confirmed this introduces **no new layering direction and no import cycle**
  (`api.py` already imports from `the_one.llm.*` at `:4216` and `:4242`); it's
  strictly an improvement over reaching into a provider class constant.
- Trade-off: none meaningful.

**DD6 — Bundled seed ships as package-data**: The committed seed JSON is added to
`[tool.setuptools.package-data]` in `pyproject.toml` (which today only globs
`interfaces/web/static/**` — `pyproject.toml:71`), so the seed is present in
non-editable/wheel installs, not just the editable dev tree.
- Rationale: without this, an installed (non-editable) build would ship without
  the seed and every model would fall back to the class default on a cold cache —
  the exact host-env gap class the `pyproject.toml` packaging comments warn about.
- Trade-off: none.

### Prerequisites
- [ ] Network access to models.dev on the dev machine to generate the initial
      committed seed (`make refresh-model-catalog`), and reachable from a running
      install for the runtime refresh loop. **The app must work fully offline** via
      the seed when models.dev is unreachable — verified in leg 06.
- [ ] OpenAI API key (or recorded fixture) for the Studio model-list endpoint
      test path. Existing `tests/test_api_context_window.py` already fixtures this.
- [ ] Confirm the models.dev dataset exposes a usable per-model context-window
      field for OpenAI + Anthropic ids (leg 01); else fall back to the LiteLLM JSON.
- [ ] No new network *service* / port introduced — the refresh loop is an outbound
      fetch only; no environment-conflict check needed.
- [x] *(Dropped per DD4)* ~~Anthropic 1M-capable model + live header-acceptance
      check~~ — not needed; no header is sent (catalog-only).

### Pre-Flight Checklist
- [x] All open questions resolved (the 3 remaining are impl-detail questions that
      resolve inside their legs by design: models.dev shape → L01/L02, OpenAI
      id-matching → L03; the 1M-scope question is resolved — catalog-only)
- [x] Design decisions documented (DD1–DD6)
- [x] Prerequisites verified (network/offline-fallback, OpenAI key/fixture, seed
      packaging; the 1M live-header prereq is dropped per DD4)
- [x] Validation approach defined (see Verification — unit/fixtured, refresh-loop,
      offline-restart, regression net; no behavior test needed)
- [x] Legs defined (6 + optional HAT)

---

## In-Flight

### Technical Approach

A new **leaf catalog module** (`the_one/llm/model_catalog.py` + a bundled
`data/model_catalog.json` seed) loads the catalog and exposes a single fail-open
lookup (`context_window_for(provider, model) -> int | None`), mirroring the typed,
`extra="allow"`, returns-`None`-on-miss shape of `openrouter_api.py:165-192`. The
loader reads the on-disk cache (`settings.data_dir / "model_catalog.json"`) if
present and valid, else the bundled seed, else signals "unknown" so the caller
keeps the class default. A whole-catalog parse failure logs WARN.

A **background refresh loop** in the web app — modeled directly on
`_chat_history_purge_loop` (`app.py:646-680`): startup catch-up, due-based daily
recheck, shutdown-drained — fetches models.dev via `httpx` (like
`openrouter_api.list_models`), validates, and atomically writes the cache file
with a `fetched_at` stamp. Failures are swallowed-and-logged; the app keeps
serving from cache/seed.

Both OpenAI and Anthropic providers' `_resolve_max_context_tokens()` overrides
call the shared lookup and set `self.max_context_tokens`, logging a WARN on miss —
slotting into the existing lazy, failure-cached `_resolve_max_context_tokens_if_needed()`
hook (`base.py:281-301`) with **no contract change**. Anthropic reports the
catalog's per-model window (1M / 200k) directly; no beta header is sent (DD4). The
Studio model-list endpoint (`api.py`) drops its duplicate `_openai_ctx` table and
the Anthropic class-constant read in favour of the same shared lookup.

Reporting is unchanged downstream: `max_context_tokens` flows to the UI through
`/agents/{name}/context-window` (`api.py:472`) and the usage WS event
(`app.py:1355/1391`) — both already wired. Because the catalog is local, those
paths resolve correctly on an offline restart of an old chat.

### Checkpoints
- [x] Leaf catalog module + bundled seed + typed fail-open lookup + package-data
      wiring + `make refresh-model-catalog` exist; loader + miss/parse-failure
      WARNs unit-tested (L01)
- [x] Background daily refresh loop fetches models.dev → on-disk cache, with
      startup catch-up + shutdown drain; resolver reads cache→seed→default;
      offline-fallback-to-seed tested (L02)
- [x] OpenAI **provider** resolver sources from the catalog; unknown-model WARN
      fires; longest-prefix outcomes preserved. `OPENAI_MODEL_CONTEXT` is
      **retained** here and **deleted in L05** (it still feeds the Studio endpoint
      + table-import tests until then — FD sequencing note in the flight log);
      the table-import test rewrites move to L05 too (L03)
- [x] Anthropic windows resolve from the catalog (1M reported where native, no
      header sent); class constant no longer the source of truth (L04)
- [x] Studio model-list endpoint uses the shared lookup for both OpenAI and
      Anthropic; no duplicate table remains (L05)
- [x] Offline-restart test proves the endpoint returns **catalog-driven** values
      (a 1M model reads 1M, not the default); conformance + full suite green at/
      above the F4 baseline, no new flakes (L06)

### Adaptation Criteria

**Divert if**:
- models.dev proves unusable (gone, relicensed, or no usable context field) AND
  the LiteLLM JSON fallback also fails — escalate the source decision to the
  operator rather than reverting to a hand-maintained table.

**Acceptable variations**:
- Catalog file path / module name (`the_one/llm/model_catalog.py`,
  `data/model_catalog.json` are suggestions, not contracts).
- OpenAI id-matching strategy, provided today's longest-prefix-wins outcomes are
  preserved for the currently-tabled models.
- Refresh-loop placement (web-app lifespan vs. a shared scheduler) and the exact
  cadence/interval env var, provided the purge-loop pattern (startup catch-up,
  shutdown drain) is followed.
- Whether the loader and the refresh fetch live in one module or two —
  design-review's call.

### Legs

> **Note:** Tentative suggestions, not commitments. Legs are planned and created
> one at a time as the flight progresses; this list will evolve.

- [x] `catalog-module-and-seed` - Add the leaf catalog module with a typed
      fail-open `context_window_for()` lookup (mirroring `openrouter_api.py`), the
      bundled `data/model_catalog.json` seed, the `[tool.setuptools.package-data]`
      wiring (DD6), the `generated_at` stamp, the unknown-model→`None`+WARN and
      whole-catalog-parse-failure→WARN paths (DD3), and the
      `scripts/refresh_model_catalog.py` generator (models.dev → seed) + the
      `make refresh-model-catalog` target. Unit-test the loader, the miss path, and
      the parse-failure path.
- [x] `runtime-refresh-loop` - Add the background daily refresh loop (mirror
      `_chat_history_purge_loop`: startup catch-up, due-based recheck, shutdown
      drain) that fetches models.dev via `httpx`, validates, and atomically writes
      the on-disk cache at `settings.data_dir / "model_catalog.json"` with a
      `fetched_at` stamp. Wire the loader to prefer cache→seed→default. Test the
      due logic, the atomic cache write, and the offline-fallback-to-seed path.
- [x] `openai-window-from-catalog` - Replace `OPENAI_MODEL_CONTEXT` + the prefix
      resolver in `openai_provider.py` with the shared catalog lookup; emit the
      DD3 WARN on miss; preserve longest-prefix-wins outcomes; delete the dead
      table. **Rewrite** (not merely extend) the parametrized cases in
      `test_llm_max_context.py` that import/assert the table directly.
- [x] `anthropic-window-from-catalog` - Replace the hard-coded `200_000` in
      `anthropic_provider.py` with the catalog lookup; report the catalog's
      per-model window (1M where native, 200k for Haiku-class). No beta header
      (DD4 — catalog-only). Fixtured unit tests for the catalog-sourced window.
- [x] `unify-studio-model-list` - Point the Studio model-list endpoint (`api.py`
      OpenAI + Anthropic branches, ~`:4212-4258`) at the shared catalog lookup;
      remove the duplicate `_openai_ctx` table and the Anthropic class-constant
      read. Extend `test_api_context_window.py`.
- [x] `verify-integration` - Conformance + freshness tests: the catalog covers the
      models the app ships/uses; the unknown-model and parse-failure WARNs fire; an
      **offline/no-network** resolve through `/context-window` returns
      **catalog-driven** values for OpenAI and Anthropic (assert a 1M model reads
      1M, not the default — proving the catalog, not the fallback, drove it); the
      refresh loop integrates end-to-end (fetch→cache→resolve). Full suite green
      at/above the F4 baseline, no new flakes.
- [x] `uat-and-alignment` *(optional)* - Guided HAT **— RUN, and high-value.**
      Surfaced a **critical defect the automated pipeline missed**: the runtime
      refresh was built blind (models.dev unreachable in Leg 1), so `project_raw`
      parsed the wrong `api.json` shape → extracted zero models → cache never
      written. Fixed inline (commit `9f152b9`): parser traverses the real
      `raw[provider]["models"]` shape; seed regenerated from authoritative
      models.dev (also corrected over-reported windows — `sonnet-4-5`/`opus-4-5`
      are 200k, not 1M). Re-verified live: refresh writes the cache; Studio
      endpoint returns correct per-model windows against the real Anthropic API.
      Also surfaced an **out-of-scope** gap → split to **Flight 6** (telemetry
      overlay *used-token* state doesn't persist on chat reopen; the *max* does).

---

## Post-Flight

### Completion Checklist
- [x] All 6 autonomous legs completed + HAT (leg 07) run
- [x] Code committed on `flight/05-model-catalog-drift-removal` (`03f3a61` legs,
      `9f152b9` HAT fix); PR opened at landing
- [x] Tests passing — full suite `3422 passed / 10 skipped / 594 deselected`
      (baseline `3347/10/594`; +75 hermetic tests this flight), 0 failures, no flakes
- [x] `OPENAI_MODEL_CONTEXT` and the Anthropic `200_000` constant no longer the
      source of truth (catalog is) — table deleted; `ImportError` confirmed
- [x] The bundled seed ships in a non-editable install (package-data `llm/data/*.json`)
- [~] Documentation: `make refresh-model-catalog` is discoverable via the Makefile
      `##` help line; the `THE_ONE_CATALOG_REFRESH_CHECK_INTERVAL_SECONDS` env var
      is documented in-code. Fuller dev-doc note is a debrief follow-up (low risk).

### Verification

- **Unit / fixtured** (default `make test`, hermetic): loader returns correct
  windows for tabled OpenAI + Anthropic models and `None`/default-with-WARN for
  unknown models; whole-catalog-parse-failure WARNs; OpenAI longest-prefix
  outcomes preserved; Anthropic catalog-sourced window (1M where native); Studio
  endpoint returns catalog-sourced `context_length` for both providers.
- **Refresh loop** (hermetic): due logic, atomic cache write, startup catch-up,
  shutdown drain, and **offline fallback to seed** (models.dev unreachable → seed
  serves, app keeps working).
- **Offline-restart** (the operator's explicit requirement): with no network
  reachable, `/agents/{name}/context-window` resolves OpenAI and Anthropic windows
  from the local cache/seed — and the asserted value is the **catalog's** value
  (e.g. 1M for a 1M model), not the class default, proving the catalog drove it.
- **Regression net**: the cross-provider conformance suite (Flight 4) and the
  existing `test_api_context_window.py` / `test_llm_max_context.py` continue to
  pass (the latter with its table-import cases rewritten).
- **Not behavior-test-backed**: this is data-sourcing logic; the criterion is
  *test-backed*, and the observable (`max_context_tokens`) is read through two
  already-existing surfaces — the `/context-window` endpoint and the usage WS
  event. No new measurement apparatus is required, so no behavior-test spec is
  authored. (Optional HAT leg covers the human-eyeball UI pass.)
