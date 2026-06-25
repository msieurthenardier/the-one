# Leg: search-backend-registry

**Status**: completed
**Flight**: [Agent-loop Resource Governance & Context-budget Management](../flight.md)

## Objective
Replace the single hardcoded DuckDuckGo scrape with a **registry of selectable search
backends** (DDG keyless default + SearXNG + Google PSE + Brave + Tavily) whose active
engine is chosen from the `web_search` tool's own config, and give every backend an
**honest-empty contract** — raise typed errors on blocked/throttled/parse-failure, return
`[]` only for a genuinely empty result — so the model stops mistaking a broken search for
"the web has nothing" and guessing URLs.

## Context
- **DD3 + refinement** (flight): pluggable backend widened to a configurable engine
  registry inside the `web_search` tool config. This leg is the **backend half only** —
  no admin UI, no secret encryption (that's leg `search-config-admin`). Engine selection
  works via saved config / env here; the pretty form + encrypted-at-rest keys come next.
- **HIGH-3 (binding — the substance)**: `DDGSearchBackend.search`
  (`_search_backends.py:167-187`) currently returns `[]` for non-200, no-result-marker
  (interstitial/parse-fail), AND genuine-empty alike; `WebSearchTool.execute`
  (`web.py:497`) collapses every `[]` to `"No results found."` The fix is a **return-
  contract change**: raise a typed `SearchBlockedError`/`SearchUnavailableError` on non-200
  & missing markers; return `[]` ONLY for a valid page with zero hits. The tool then
  surfaces the raised error honestly (`[error] …`) instead of a false "no results."
- **Open WebUI lineage** (researched this session): one backend per engine returning a
  shared result model; DDG is the keyless special-case; keyed engines fail when their key
  is missing; backends `raise` on HTTP errors and return `[]` only for genuine-empty —
  the same contract this leg adopts. We keep the-one's `SearchBackend` **Protocol** (with
  `name` ClassVar) rather than Open WebUI's loose bare-function convention.
- **Codebase facts (verified):**
  - `WebSearchTool` (`web.py:459`, `name="web_search"`, registered `builtins.py:66`) sets
    `Config = WebConfig` but `execute()` reads ONLY `self._cross_configs[SearchBackend]`
    (`web.py:495`) — it does NOT read WebConfig fields. → moving it to a dedicated config
    is safe.
  - `cross_configs[SearchBackend]` is hardcoded to `DDGSearchBackend()` at
    `builtins.py:~182`; `get_tools` resolves the `WebConfig` **model** into cross_configs
    BEFORE constructing tools, but it does **NOT** build an httpx client or transport.
    **CORRECTION (design review):** there is no shared SSRF-guarded `AsyncClient` at
    provider level — each web tool builds `SSRFGuardedTransport(extra_allowed_hosts=
    cfg.extra_allowed_hosts)` **per-call** via `_build_transport(cfg)` (`web.py:150,259,
    382`) and `DDGSearchBackend` owns a **per-call** `async with httpx.AsyncClient(...)`.
    So the factory passes the SSRF **policy** (`extra_allowed_hosts` from the resolved
    `WebConfig`), NOT a live client; each backend opens/closes its own per-call client
    with an `SSRFGuardedTransport` — matching DDG's existing owned-client pattern and
    avoiding any client-lifecycle/close hook that `get_tools` doesn't have.
  - `SearchResult` (`_search_backends.py`) is a frozen dataclass `(title, url, snippet)` —
    keep it; the JSON engines map their fields onto it.
  - `SearchBackend` Protocol: `name: ClassVar[str]` + `async search(query, max_results)
    -> list[SearchResult]`. Backend owns its httpx client (injected SSRF-guarded one in the
    wired path, or a per-call client in isolation).
  - The tools-admin form is **schema-driven** (`api.py` `/tools/configs/{name}` serves
    `cls.Config.model_json_schema()` enriched with markers) — so engine fields placed on
    `WebSearchTool.Config` auto-render. The `ui_hint:"dropdown"`+`ui_choices` convention
    (see `_web_config.py` `timeout_seconds_default`, `execution.py` `output_cap_bytes`)
    gives the engine selector for free. `ui_hint:"password"` does NOT yet render in tools-
    admin — that's leg 3; this leg just MARKS secret fields.

## Inputs
- `the_one/tools/_search_backends.py` — `SearchResult`, `SearchBackend` Protocol,
  `DDGSearchBackend` (returns `[]` on all failure modes today).
- `the_one/tools/web.py` `WebSearchTool.execute` (`:488-510`) — backend call + result
  formatting; `ConstraintError`/`Exception` clauses.
- `the_one/tools/builtins.py` — `cross_configs[SearchBackend] = DDGSearchBackend()`
  hardcode; `WebConfig` resolved into cross_configs before tool construction.
- `the_one/tools/_web_config.py` `WebConfig` (8 fields post-leg-1) — the web SSRF/transport
  config shared by `http_request`/`fetch_url`/`download_file` (stays as-is).

## Outputs
- Typed errors in `_search_backends.py`: `SearchError` base + `SearchBlockedError`,
  `SearchUnavailableError`.
- `DDGSearchBackend.search` raises on non-200 / missing markers; `[]` only for genuine
  empty.
- 4 new backends: `SearxngSearchBackend`, `GooglePSESearchBackend`, `BraveSearchBackend`,
  `TavilySearchBackend` — each `SearchBackend`-conformant, honest-empty.
- A registry + factory `build_search_backend(config, *, extra_allowed_hosts) ->
  SearchBackend` mapping the selected engine name to a constructed backend; each backend
  owns its per-call SSRF-guarded client built from `extra_allowed_hosts` (NOT a shared
  live client — see the SSRF correction above).
- New `WebSearchConfig` (= `WebSearchTool.Config`) with `search_backend` selector +
  per-engine fields; secret fields MARKED (`ui_hint:"password"`, `secret: true`) for leg 3.
  Secret fields are plain `str` with NO resolver `Narrow` marker (`Narrow` on `str` raises
  `NotImplementedError` in `_check_narrow`) — use no marker / `Substitute` only.
- `builtins.py` constructs the active backend from the resolved `WebSearchConfig`, passing
  `extra_allowed_hosts` from the resolved shared `WebConfig`, replacing the DDG hardcode.
- `WebSearchTool.execute` surfaces `SearchError` honestly; `[]` → "No results found."
- Per-backend + registry + honest-empty unit tests (mocked httpx).

## Acceptance Criteria
- [x] `SearchBlockedError` / `SearchUnavailableError` (under a `SearchError` base) exist;
      `DDGSearchBackend` raises `SearchBlockedError` on non-200. For a 200 with no
      `result__a` marker, **distinguish genuine-empty from blocked (option b)**: if DDG's
      positive no-results marker is present (e.g. the `no-results`/"No results." block),
      return `[]`; if NEITHER results NOR the no-results marker is present, raise
      `SearchBlockedError` (interstitial/parse-fail). Do not blanket-raise on no-marker —
      that would misreport a legitimately empty search as blocked.
- [x] `SearxngSearchBackend` (GET `{base_url}/search?q=&format=json`),
      `GooglePSESearchBackend` (key + cse id), `BraveSearchBackend` (key),
      `TavilySearchBackend` (key) each implement `SearchBackend`, map their payloads onto
      `SearchResult(title,url,snippet)`, raise `SearchUnavailableError` when required
      config (url/key/cse) is missing, raise `SearchBlockedError`/`SearchUnavailableError`
      on non-2xx per provider semantics, and return `[]` only for genuine empty.
- [x] `WebSearchConfig` is `WebSearchTool.Config`: `search_backend` enum dropdown
      (`duckduckgo`|`searxng`|`google_pse`|`brave`|`tavily`, default `duckduckgo`,
      `ui_hint:"dropdown"`+`ui_choices`) + `searxng_base_url`, `google_pse_api_key`,
      `google_pse_cse_id`, `brave_api_key`, `tavily_api_key`. Secret fields carry
      `json_schema_extra={"ui_hint":"password","secret":true}`. DDG selected → no fields
      required.
- [x] `build_search_backend(config, *, extra_allowed_hosts)` returns the configured backend
      (default DDG when unset); a selected-but-unconfigured keyed engine still constructs
      and raises `SearchUnavailableError` at call time with a clear "configure X" message
      (do NOT silently fall back to DDG — that hides misconfig). Each backend opens/closes
      its own per-call client with an `SSRFGuardedTransport(extra_allowed_hosts=…)`.
- [x] `builtins.py` uses `build_search_backend` with the resolved `WebSearchConfig` and
      `extra_allowed_hosts` from the resolved shared `WebConfig`; the `DDGSearchBackend()`
      hardcode is gone. DDG still works with zero config (regression).
- [x] `WebSearchTool.execute` catches `SearchError` and returns an honest `[error] …`
      (distinguishing blocked/unavailable from a real empty); a valid empty result still
      returns "No results found." The generic `except Exception` backstop remains.
- [x] Unit tests (mocked httpx, no live network): each backend's success / non-2xx→raise /
      genuine-empty→`[]` / missing-config→raise; the registry selects the right backend per
      `search_backend`; `WebSearchTool.execute` maps raised→`[error]` and `[]`→"No results
      found." A `WebSearchConfig` field-count + secret-marker guard mirroring
      `test_web_config.py::test_field_count_is_eight` (assert field count N + assert each
      secret field carries `secret:true` in `json_schema_extra`).
- [x] **Existing `tests/test_search_backends.py` is REWRITTEN, not added** — its
      `test_no_results_returns_empty` (`:199-211`) and `test_anti_bot_interstitial_returns_empty`
      (`:213-228`) assert the OLD `[]`-on-failure contract; update them to the new contract
      (interstitial/non-200 → raise; genuine no-results marker → `[]`).
- [x] **The generic PUT-validation tests in `tests/test_api_tool_configs.py`** that target
      `web_search` with WebConfig-shaped fields (`test_put_validates_config_against_schema`,
      `test_put_422_..._model_validator`, `test_put_persists_enabled_and_config`,
      `test_put_replaces_config_wholesale`, ~`:153-224`) are **re-pointed to a tool that
      still uses `WebConfig`** (`http_request`/`fetch_url`) so they keep exercising the
      generic 422/persist path — web_search no longer has `timeout_seconds_max` etc.
- [x] FULL unit suite (`make test-unit`) green at/above the M16 baseline, no new flakes.
- [x] No secret is logged; backends log at warning without the key/url payload.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_search_backends.py -x --timeout 30`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_web_tools.py -x --timeout 30`
  (honest-empty surfacing through `WebSearchTool.execute`).
- `make test-unit` once at leg-end — green, no new flakes.
- Manual sanity (optional): with no config, `web_search` still returns DDG results;
  selecting `tavily` with no key yields an honest `[error] … configure Tavily API key`.

## Implementation Guidance
1. **Typed errors + DDG contract change** (`_search_backends.py`).
   - Add `SearchError(Exception)`, `SearchBlockedError(SearchError)`,
     `SearchUnavailableError(SearchError)`. In `DDGSearchBackend.search`: non-200 → raise
     `SearchBlockedError(f"DDG returned {status} …")`. 200 with results → parse + return.
     200 with NO `result__a` but WITH DDG's positive no-results marker (`no-results` block
     / "No results." text) → return `[]`. 200 with NEITHER → raise
     `SearchBlockedError("DDG interstitial / no result markers")`. (Option b — don't
     misclassify a real empty as blocked.)
2. **New backends** (one class each, `SearchBackend`-conformant; each owns a per-call
   `async with httpx.AsyncClient(transport=SSRFGuardedTransport(extra_allowed_hosts=…))`).
   - **SearXNG**: GET `{base_url}/search` params `q`, `format=json`; missing `base_url` →
     `SearchUnavailableError`; map `results[]` `{title,url,content}` → `SearchResult`.
   - **Google PSE**: GET `https://www.googleapis.com/customsearch/v1` params `key`, `cx`,
     `q`; missing key or cse → `SearchUnavailableError`; map `items[]`
     `{title,link,snippet}`.
   - **Brave**: GET `https://api.search.brave.com/res/v1/web/search` headers
     `X-Subscription-Token` AND `Accept: application/json` (some endpoints 4xx without the
     Accept header); missing key → `SearchUnavailableError`; map `web.results[]`. Treat
     429 as `SearchBlockedError`.
   - **Tavily**: POST `https://api.tavily.com/search` json `{api_key, query, max_results}`
     (in-body key form; still supported); missing key → `SearchUnavailableError`; map
     `results[]` `{title,url,content}`.
   - All: non-2xx (other than the provider-specific blocked codes) →
     `SearchUnavailableError`; genuine zero-hit → `[]`.
3. **Registry + factory.** `SEARCH_BACKENDS: dict[str, ...]` keyed by engine name; a
   `build_search_backend(config: WebSearchConfig, *, extra_allowed_hosts) -> SearchBackend`
   that reads `config.search_backend` and constructs the matching backend with its config
   (api_key/base_url/cse_id) + the SSRF `extra_allowed_hosts` (each backend builds its own
   per-call client). Default DDG when name unknown/empty.
4. **`WebSearchConfig`.** New pydantic model (its own module or in `_web_config.py`),
   set `WebSearchTool.Config = WebSearchConfig`. Fields per the AC; secret fields carry
   `json_schema_extra={"ui_hint":"password","secret":true}` and NO resolver marker
   (`Narrow` on `str` raises `NotImplementedError`; use no marker or `Substitute`). Keep
   `WebConfig` untouched (web_fetch et al. still use it). Add a field-count/secret-marker
   guard test for `WebSearchConfig`.
5. **`builtins.py` wiring.** Resolve `WebSearchConfig` for `web_search` (via the existing
   `resolve(cls.Config, tool_configs.get(name), …)` path — `WebSearchTool.Config` is now
   `WebSearchConfig`), read `extra_allowed_hosts` off the resolved shared `WebConfig`
   (`cross_configs[WebConfig]`), and set `cross_configs[SearchBackend] =
   build_search_backend(web_search_cfg, extra_allowed_hosts=web_cfg.extra_allowed_hosts)`.
6. **`WebSearchTool.execute`** (`web.py`). Add `except SearchError as e:` before the
   generic `except` → return a clear `[error] web_search ({backend}) unavailable: {e}` (or
   "blocked/throttled" for `SearchBlockedError`). Keep `[]` → "No results found." Keep the
   `ConstraintError` and generic `Exception` clauses.

## Edge Cases
- **Selected engine missing its key/url**: construct anyway; raise `SearchUnavailableError`
  at call with an actionable message. No silent DDG fallback (hides misconfig).
- **Persisted pre-existing `web_search` config** previously validated against `WebConfig`:
  CONFIRMED (design review) — `model_validate`/`resolve` use Pydantic `extra="ignore"`, so
  legacy keys load fine (no migration needed). Note: the PUT handler persists
  `validated.model_dump()`, so the first re-save of an old web_search row silently drops the
  legacy WebConfig keys from storage — intended/harmless (web_search never read them).
- **Secret leakage**: never log api_key/base_url values; redact in warnings.
- **SearXNG without JSON format enabled** (operator's instance): non-JSON/HTML response →
  `SearchUnavailableError("enable JSON format in SearXNG settings")`.
- **Leg-3 dependency**: secret fields are plaintext in `config` until leg 3 adds the
  encrypted `secrets` split; acceptable because the flight batch-commits at the end (no
  intermediate release). Leg 3 MUST land the encryption before flight commit.

## Files Affected
- `the_one/tools/_search_backends.py` — typed errors; DDG contract; 4 new backends;
  registry + `build_search_backend`.
- `the_one/tools/_web_config.py` (or new `_web_search_config.py`) — `WebSearchConfig`.
- `the_one/tools/web.py` — `WebSearchTool.Config = WebSearchConfig`; `except SearchError`.
- `the_one/tools/builtins.py` — backend construction from config (drop the DDG hardcode).
- `tests/test_search_backends.py` (MODIFIED — exists) — rewrite the 2 old `[]`-on-failure
  tests (`:199-228`) to the new raise-contract; add the 4 new backends + registry +
  honest-empty.
- `tests/test_web_tools.py` — `execute` surfacing (raised→`[error]`, `[]`→no-results).
- `tests/test_api_tool_configs.py` — re-point the 4 generic PUT-validation tests
  (~`:153-224`) off `web_search` onto a WebConfig tool (`http_request`/`fetch_url`).
- `tests/` — `WebSearchConfig` field-count/secret-marker guard.
- Docs: `.env.example` / config docs — engine selection + the new config fields (note
  keys are admin-config in leg 3; env/config here).

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing (full unit suite) — 3550 passed / 0 failed
- [x] Update flight-log.md with leg progress (engines shipped, the WebSearchConfig
      decision, honest-empty contract, the leg-3 secret-encryption dependency)
- [x] Set this leg's status to `landed` (commit deferred to flight end)
- [x] Check off this leg in flight.md
- [x] (Not the final leg — do not land the flight here)
