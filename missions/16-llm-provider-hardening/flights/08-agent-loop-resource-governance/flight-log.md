# Flight Log: Agent-loop Resource Governance & Context-budget Management

**Flight**: [Agent-loop Resource Governance & Context-budget Management](flight.md)

## Summary

Flight created (planning). Implements Flight 07 debrief Recommendation 1: a single
context-budget governor at the tool-dispatch boundary, conversation-level accounting
surfaced (color-coded) in the telemetry overlay, and a reliable/configurable
`web_search` backend. Context compaction (eviction/summarization) is deferred to its
own future mission. No execution yet.

---

## Reconnaissance Report

Source: `flights/07-chat-loop-robustness/flight-debrief.md` (Recommendation 1 +
Key Learnings) and the operator's scoping this session. Cited locations walked against
current `main`.

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| No central context-budget governor over tool results | `confirmed-live` | `the_one/agent/core.py:535` `_execute_tool`; `:555` `return ToolResult(content=output)` — output passed through unbounded | Add governor here (DD1, leg 1) |
| Per-tool LLM caps inconsistent / wrong axis | `confirmed-live` | web `tool_text_cap_bytes`=48 KB (`_web_config.py:196`); filesystem `read_size_cap_bytes`=1 MB **file size** (`filesystem.py:91,266`); execution `output_cap_bytes` (~100 MB ceiling) | Unify under governor; retire LLM-facing caps, keep safety caps (DD1) |
| Model context window reachable from the agent | `already-satisfied` | `self.llm.max_context_tokens` (`base.py:250`, catalog-resolved via `_resolve_max_context_tokens_if_needed`) | Governor derives budget from it (DD1/DD4) |
| No tokenizer; only byte-per-token heuristic | `confirmed-live` | `BYTES_PER_TOKEN_*` in providers / `_streaming.py`; no tiktoken dep | Budget in bytes-with-heuristic (DD4) |
| `web_search` = unauthenticated DDG scrape, silent empty | `confirmed-live` | `the_one/tools/_search_backends.py` `DDGSearchBackend` (HTML scrape of `html.duckduckgo.com`); `SearchBackend` Protocol already exists | Pluggable backend + honest-empty + optional keyed (DD3, leg 2) |
| Telemetry overlay already renders a context fraction | `already-satisfied` | `chat.js` `updateTelemetry`/`setTelemetryMax`; renders `context_tokens / max_context_tokens` bar (F6/F7); `.telemetry-overlay` in `chat.css` | Add threshold coloring on top (DD2, leg 3) — accounting is mostly already present |
| Web 1 MB streaming cap + file-size read cap are SAFETY guards | `confirmed-live` | `response_size_cap_bytes` streaming hard-abort (`web.py`); `read_size_cap_bytes` file-size guard (`filesystem.py:266`) | KEEP (transport/OOM axis); do NOT retire as part of unifying LLM caps (DD1) |

No `drifted`/`partially-satisfied`. The two `already-satisfied` rows (model window
reachable; overlay fraction present) shrink the flight: the governor's input and the
accounting's display both already exist — the work is the governor logic + the coloring.

**Lineage**: F07 fixed the single-oversized-result case (0.2.6 `tool_text_cap_bytes`);
this flight generalizes it to a model-derived governor over ALL tools and adds the
cumulative-pressure signal. The F07 debrief's verification miss (tested the pathological
infinite-stream input but never a large *valid* page) is the test-discipline this
flight's DD5 corrects: assert "what the model receives" for a large valid input, across
tool types.

---

## Flight Director Notes

- **2026-06-23** — Flight planned via `/flight`. Operator design decisions: central
  governor that retires per-tool LLM-facing caps (safety caps stay); full conversation
  accounting + warn via overlay color (orange/red), NO eviction; configurable search
  backend with honest-empty default; bytes-with-heuristic budgeting. Context compaction
  (evict/summarize) deferred to its own future mission per operator ("almost feels like
  its own mission").

- **2026-06-23 — Execution started via `/agentic-workflow`.** Flight `ready`→`in-flight`;
  branch `flight/08-agent-loop-resource-governance`. Batch model: legs designed +
  implemented sequentially, single code review + commit at flight end (no per-leg commit).

- **2026-06-23 — Leg 1 (`context-budget-governor`) designed + design-reviewed.** Developer
  design review (Sonnet) returned approve-with-changes against real source; all citations
  confirmed. Locked two decisions the review surfaced: (HIGH-2) reclassify
  `output_cap_bytes` as a **safety ceiling** [option b] rather than removing the field —
  lower blast radius (the field's range/Substitute/UI tests stay), governor layers the
  model-derived tail-bound on top; (MEDIUM-1) promote the existing
  `_bytes_per_token_for_interim()` to a **single public `bytes_per_token`** accessor on the
  base shared by governor + stream accumulator (not a parallel property). Corrected LOW-4:
  the F07 cancel path builds an assistant `Message` (`app.py:1601`), NOT an out-of-band
  `ToolResult` — document the deliberate non-coverage. Skipped a 2nd design-review cycle:
  the edits adopt the reviewer's own explicit recommendations verbatim; no new design.
  Leg → `ready`.

- **2026-06-23 — ★ Mid-flight scope pivot: search work expanded to a configurable engine
  registry + admin surface (operator-directed).** While scoping the original
  `search-backend-pluggable` leg, the operator asked whether a generic, user-configurable
  search-engine setup was feasible — "everything from DuckDuckGo to Google to a paid
  provider to SearXNG." Researched how Open WebUI does it (read its
  `retrieval/web/` subsystem live): ~27 backends, one async function per engine returning
  a shared `SearchResult`; dispatch is an engine-name if/elif; **DuckDuckGo is the keyless
  special-case, keyed engines raise when their key is missing; backends `raise` on HTTP
  errors and return `[]` only for genuine-empty** — independently validating the honest-
  empty contract HIGH-3 already prescribed. the_one already has a *better* seam than Open
  WebUI's loose functions: the `SearchBackend` Protocol (+ `name` ClassVar) whose docstring
  explicitly reserved "F6 admin will let operators pick the active backend." 

  Operator decisions: (1) ship roster = DuckDuckGo (keyless default) + SearXNG (self-hosted
  URL, no secret) + Google PSE (key + CSE id) + Brave (key) + Tavily (key); (2) configure
  it **inside the `web_search` tool's own config**, surfaced by the EXISTING schema-driven
  tools-admin section — NOT a new settings page; (3) take BOTH halves (backend + admin) in
  THIS flight. Mapped the tools-admin surface (Explore): the engine dropdown is free
  (`ui_hint:"dropdown"` already rendered), but three items are NEW work — `ui_hint:
  "password"` secret rendering (exists only in the provider editor today), conditional per-
  engine field visibility, and tool-config **secret-at-rest** (`ToolConfigRepository`
  stores plaintext `config` only; needs the `config`+`secrets` split `MCPSource`/`Connector`
  already use). 

  Result — `search-backend-pluggable` splits into two legs along the backend/UI seam:
  `search-backend-registry` (this flight, backend: contract + registry + 5 engines +
  config-driven selection) then `search-config-admin` (secret-field UI + conditional fields
  + encrypted tool-config persistence). Original DD3 framing preserved; refinement appended
  in flight.md DD3 + the tentative leg list updated. Governor leg (1) unaffected. The
  flight's footprint grows but its purpose (govern what tools pull into context; fix the
  upstream search-unreliability that triggers URL-guessing) is intact.

- **2026-06-24 — Leg 2 (`search-backend-registry`) designed + design-reviewed → `ready`.**
  Developer design review (Sonnet) against the live working tree returned approve-with-
  changes; caught three HIGHs the design got wrong and one semantic ambiguity, all folded
  in (adopting the reviewer's recommended fix for each, so no 2nd cycle): (1) **SSRF client
  premise was false** — there is no shared provider-level `AsyncClient`; the SSRF transport
  is built per-tool/per-call. Fix: `build_search_backend` takes `extra_allowed_hosts` (SSRF
  *policy*), each backend owns a per-call `SSRFGuardedTransport` client (matches DDG today),
  sidestepping the missing client-close hook. (2) **`tests/test_search_backends.py` already
  exists** asserting the OLD `[]`-on-failure contract — two tests rewritten to the new
  raise-contract, not "added new." (3) **`tests/test_api_tool_configs.py`** has 4 generic
  PUT-validation tests targeting `web_search` with WebConfig fields that break when
  `WebSearchTool.Config` → `WebSearchConfig`; re-point them onto `http_request`/`fetch_url`
  (still WebConfig). (4) **DDG no-marker ambiguity** — a genuine-empty DDG page also lacks
  `result__a`; chose option (b): return `[]` only when DDG's positive no-results marker is
  present, raise `SearchBlockedError` only when neither results nor that marker appear.
  Also: secret fields are plain `str` with NO `Narrow` marker (`Narrow`-on-`str` raises);
  Brave needs `Accept: application/json`; legacy web_search config loads via `extra=ignore`
  (no migration; model_dump write-back drops legacy keys, intended). Roster confirmed:
  DDG default + SearXNG + Google PSE + Brave + Tavily. Leg 3 (`search-config-admin`) owns
  the secret-at-rest encryption (this leg marks secret fields; plaintext until leg 3, fine
  under batch-commit).

- **2026-06-24 — `search-config-admin` split into TWO legs (FD decision).** Grounding the
  admin work (Explore) showed it bundles a DB migration + repository change + API masking +
  resolver merge AND frontend (password fields, conditional visibility, a11y) — too much
  blast radius for one agent under a single end-of-flight review. Split along the
  persistence/UI seam: **leg 3 `search-config-persistence`** (secrets-at-rest, masking,
  resolver merge — headless-testable) then **leg 4 `search-config-admin-ui`** (password
  rendering + eye-toggle + conditional per-engine fields + a11y). The `__MASKED__` masking
  contract defined in leg 3's API is what leg 4's UI consumes. Flight tentative-leg list
  updated; overlay/verify/uat shift down accordingly.

- **2026-06-24 — Leg 3 (`search-config-persistence`) designed + design-reviewed (2 cycles)
  → `ready`.** First review returned **needs-rework**: the design's keystone — "merge
  decrypted secrets in `ToolConfigRepository.list_all()`" — targets a method with **zero
  production callers**, so backends would never get the real keys. The real resolver feed is
  `factory.py:292-294` (`repo.list()` → `{c.name: c.config}`). Reworked to the reviewer's
  fix: add `ToolConfig.merged_config()` (mirroring `MCPSource.merged_config()`,
  `models.py:98-108`) and rewire `factory.py:294` to `{c.name: c.merged_config()}` + thread
  the encryptor into the factory's repo (the `encryptor` var already exists at
  `factory.py:255`). Other corrections: `upsert(name, config, secrets=None, enabled=True)` —
  DEFAULTED kwarg so no existing caller breaks (none pass a 3rd positional); PUT split must
  **remove** secret keys from the persisted `config` (not just copy), reusing the MCP/
  connector masked-preserve precedent (`api.py:1229`/`:2605`); `_secret_field_names`
  null-guards `json_schema_extra`. Second-pass review confirmed all six corrected items
  against source → **approve** (no downstream re-persist of merged secrets; no broken
  caller; encryptor already in factory scope). Migration v32 (`tool_configs.secrets TEXT
  DEFAULT '{}'`, mirroring v10 mcp_sources); `CURRENT_VERSION` 31→32. Generic over any
  built-in tool's `secret:true` fields; web_search is the first consumer. Leg 4 (UI) follows.

- **2026-06-24 — Leg 4 (`search-config-admin-ui`) designed + design-reviewed → `ready`.**
  Developer design review (Sonnet) → approve-with-changes; resolved two things: (1)
  **Studio parity is NOT applicable** — `renderField` early-returns `''` in agent mode for
  markerless non-boolean fields, and all `WebSearchConfig` fields are markerless `str`
  (operator-only), so Studio renders nothing for web_search → the eye-toggle + `show_if`
  wiring lands ONLY in admin `tools-editor.js`. (2) **HIGH — `tests/browser/test_flow_admin_
  tools_editor.py` is ALREADY broken by legs 2-3**: it still asserts the old `WebConfig`
  fields (`timeout_seconds_max`/`host_allowlist`/`default_user_agent`) for `web_search`,
  which moved to `WebSearchConfig`. Legs 2/3 ran `make test-unit` only — the BROWSER suite
  was never run and is RED. This leg owns fixing it (re-target field-enum + save/cancel/dirty
  to `WebSearchConfig` fields; re-home the 422-model-validator test to a `WebConfig` tool).
  Folded in: password input must carry `data-field-type="string"` (load-bearing for
  `readFieldValue` round-trip); eye handler selects by `.api-key-wrap` structure not the
  provider-specific `.admin-pf-password`; `.api-key-*`/`.is-hidden` CSS is already global
  (no new CSS); `show_if` flattens into `prop.show_if` (confirmed); the leg-2/3 WebSearchConfig
  guard is unaffected by adding `show_if`. **Flight-level note**: leg 6 (verify) must run
  `make test-browser` as a gate — the unit-only "green" claims in legs 1-3 did not cover it.

- **2026-06-24 — Leg 5 (`context-fullness-overlay`) designed + design-reviewed → `ready`.**
  Developer design review (Sonnet) → approve-with-changes; all refs confirmed (coloring at
  telemetry-overlay.js:83/:136 already ships; container `role="status"` + static aria-label
  :20-21; `window.App.config` available — non-module IIFE loaded after app.js; `/api/config`
  at api.py:163-171 has ZERO test coverage today; `Settings` is `BaseSettings` env-prefix
  `THE_ONE_`, no field-count guard; nothing asserts the "Token usage" label or the 70/90
  literals). Folded in: (MED-1) thresholds validated via a `@model_validator(mode="after")`
  in config.py that CLAMPS invalid `0<warn<crit<=100` back to 70/90 + logs (must not raise —
  boot crash); single source of truth so `/api/config` always emits sane values. (MED-2)
  capture a true `make test-browser` green baseline FIRST (prior legs only ran single files).
  a11y primary signal = dynamic `aria-label` ("Token usage: {pct}% of context, approaching
  limit / context nearly full"), keeping "Token usage" prefix; optional `aria-live` reuses
  `.visually-hidden` (chat.css:382) on transitions only. New `tests/test_api_config.py`;
  `.env.example` gets the two THE_ONE_CONTEXT_*_PCT vars. Coloring is verify-and-keep, NOT
  rebuilt (architect MEDIUM-2/LOW-1).

- **2026-06-25 — Leg 6 (`verify-integration`) executed → `landed`. Behavior test 9/9 PASS.**
  Generalized governor tests (leg 1 `tests/test_governor.py` cross-tool) confirmed present +
  passing. Authored + ran the Witnessed behavior test `agent-governance-and-search`
  (run log: `tests/behavior/agent-governance-and-search/runs/2026-06-25-19-37-47.md`) against
  an ISOLATED flight-08 instance on :8485 (separate data dir so the v32 migration + seeded
  test data never touched the operator's real DB; their daily-driver on :8484 left untouched),
  with a real Anthropic `claude-sonnet-4-6` web-tool agent, overlay thresholds set low (5/20).
  Live two-agent run (Executor + Validator, SendMessage continuation). **All 9 checkpoints
  PASS**, each on a hard observable, not model self-report:
  - Admin UI (C1-5): engine `<select>` default DuckDuckGo; Brave→masked-password+eye-toggle
    (aria Show/Hide round-trip); Google PSE 2-field reveal; show_if engine-scoped; and a
    **strengthened** leg-3 masked round-trip — a saved Brave key reloaded `***...2345` (never
    plaintext), independently curl-verified.
  - Governor (C7): a ~535 KB `fetch_url` body bounded to **exactly 262,144 bytes** with the
    verbatim marker, cross-checked to `_governor.py:51,153-154`. Turn completed, no hang.
  - Overlay (C8): reached **warn** at 11% — `.context-bar.warn` (color) AND container
    `aria-label="Token usage: 11% of context, approaching limit"` with numeric spans
    `aria-hidden` (the non-color SR path — leg-5's a11y fix); aria-label evolved baseline
    0% → 11%+qualifier (threshold-driven).
  - Honest search (C9): web_search (DDG) returned 5 real results; the 5 cited URLs exactly
    match the tool result — zero fabricated URLs; not a silent "No results found".

  **Run findings folded back in**: spec hardened (status→active; step 5 masked round-trip made
  REQUIRED; step 7 URL pinned to the deterministic 256 KB–1 MiB window with the tool-result
  marker as the pass criterion; precondition notes on served model id + session model-pinning +
  window-relative threshold math). Env artifacts (NOT product defects), all Orchestrator-
  remediated mid-run: stale model id `claude-sonnet-4-20250514` 404 → `claude-sonnet-4-6`; the
  gutenberg book timed out at the tool layer; `/photos` (~1 MiB) correctly hard-refused at the
  1 MiB TRANSPORT cap (a flight-08 KEEP, distinct from the governor). One product nit in
  Anomalies (residual Stop button — pre-existing, carry to debrief). Compaction backlog seed in
  `mission.md` confirmed still-deferred post-F8. Suites unchanged from leg 5 (this leg added no
  source: unit 3574/0, browser 486/0).

- **2026-06-23 — Leg 1 (`context-budget-governor`) implemented → `landed`.**

  **What shipped:**
  - New pure helper `the_one/agent/_governor.py::govern_tool_content(content,
    max_context_tokens, *, fraction, floor, ceiling, direction, bytes_per_token)` —
    byte-boundary slice + `decode(errors="replace")`; truncation marker sits OUTSIDE
    the budget; head-preserve (marker appended) by default, tail-preserve (marker
    prepended) for shell/exec. `max_context_tokens` ≤0/None/<128k floors to 128k (LOW-2).
  - Wired into `Agent._execute_tool` via a `self._govern(...)` helper: governs the
    normal-path `output` (with the tool's `truncation_direction`) and both error
    strings (timeout, generic-except, head); the MCP `<auth required>` sentinel is NOT
    governed (LOW-3). LLM attrs read with `getattr` defaults so a minimal/custom
    provider can't crash dispatch.
  - Direction mechanism: `Tool.truncation_direction: Literal["head","tail"]` (default
    `"head"`), overridden to `"tail"` on `ShellTool`, `PythonExecTool`,
    `ShellSessionSendTool`.
  - **MEDIUM-1:** promoted a single public `bytes_per_token` accessor onto
    `LLMProvider` base (default 4.0); anthropic 3.7, ollama 3.5, openai/openrouter 4.0
    set it as a class attr; removed both `_bytes_per_token_for_interim()` overrides and
    repointed all three `_StreamAccumulator(bytes_per_token=self.bytes_per_token)`
    call-sites. Governor + accumulator now read one value.
  - **HIGH-1:** removed `tool_text_cap_bytes` from `WebConfig`, all 3 `_cap_tool_text`
    web.py call sites, the `_cap_tool_text` helper + its import. `WebConfig.model_fields`
    9→8; renamed `test_field_count_is_nine`→`test_field_count_is_eight` (==8).
    `grep -rn tool_text_cap_bytes the_one/ tests/` returns nothing. All
    `response_size_cap_bytes` sites untouched.
  - **HIGH-2 (option b):** KEPT `output_cap_bytes` + `_truncate_output` formatting
    (stdout+stderr combine, `[stderr]` marker, `[exit code: N]` suffix, tail
    preservation); reclassified its ROLE from a model-sized LLM cap to a transport/safety
    **ceiling** — updated the field description + the UI dropdown labels (dropped the
    "Opus headroom"/model-sized framing → "safety ceiling"/"large logs"). The governor
    now layers the model-derived tail-bound on top (tail direction for shell/exec).
    Default stays 262_144; `tests/test_execution_config.py` unchanged + passing.
  - Tests: new `tests/test_governor.py` (21 tests) — pure-helper (large→capped,
    small→unchanged, scales-with-window, floor/ceiling clamp, max_context floor, head vs
    tail, marker-outside-budget, multibyte) + env-override + cross-tool boundary tests
    (web/filesystem REAL tools + tail-direction tool through `_execute_tool`: large-valid
    bounded, small unchanged, scales-with-window, error-string bounded, shell tail/exit
    code preserved, auth sentinel not governed). Replaced the obsolete `TestToolTextCap`
    in `tests/test_web_tools.py` with `TestWebToolNoLongerSelfCaps` (asserts the web tool
    no longer self-caps).
  - Docs: `.env.example` (the 3 governor env vars + a coupling-coincidence note),
    `the_one/agents.md` (Tool-authorship `truncation_direction` bullet, a
    "Context-budget governor" paragraph, bytes-per-token note, constraint-table
    `output_cap_bytes` reclassification).

  **Budget defaults chosen (env-overridable):** fraction **1/8** (`0.125`), floor
  **8_192** (8 KB), ceiling **262_144** (256 KB). With a 128k window + 4.0 bytes/token
  the computed budget is 64 KB; a 200k-window Anthropic at 3.7 → ~92 KB; both well within
  [8 KB, 256 KB]. NOTE the 256 KB ceiling equals the `output_cap_bytes` default by
  coincidence of sane sizing, not coupling (commented in both places).

  **Full-suite result:** `make test-unit` → **3512 passed, 10 skipped, 595 deselected,
  0 failed** in ~334s. Baseline (this session, pre-change) collected the same set with 3
  failures introduced mid-implementation (a minimal `_StubLLM` test double lacking the new
  LLM attrs), resolved by reading them with `getattr` defaults; final run is clean at
  +21 net (the new governor tests) over the M16 baseline, no new flakes. Lint + format
  clean.

- **2026-06-24 — Leg 2 (`search-backend-registry`) implemented → `landed`.**

  **Engines shipped (5, all `SearchBackend`-conformant, honest-empty):**
  - `DDGSearchBackend` (keyless default — contract changed, see below), `SearxngSearchBackend`
    (GET `{base_url}/search?q=&format=json`; maps `results[] {title,url,content}`),
    `GooglePSESearchBackend` (GET `googleapis.com/customsearch/v1` key+cx+q; maps
    `items[] {title,link,snippet}`), `BraveSearchBackend` (GET `api.search.brave.com/res/v1/web/search`,
    headers `X-Subscription-Token`+`Accept: application/json`; maps `web.results[]`; **429 →
    `SearchBlockedError`**), `TavilySearchBackend` (POST `api.tavily.com/search` json
    `{api_key,query,max_results}`; maps `results[] {title,url,content}`).
  - Each owns a **per-call** `async with httpx.AsyncClient(transport=SSRFGuardedTransport(
    extra_allowed_hosts=…))` client — even DDG now respects the SSRF policy (the design-review
    "no shared client" correction). DDG keeps its injected-client path for the legacy mock test.
  - Registry + factory `build_search_backend(config, *, extra_allowed_hosts) -> SearchBackend`
    keyed on `config.search_backend`; default DDG for unset/unknown; **a selected-but-
    unconfigured keyed engine still constructs and raises `SearchUnavailableError` at call
    time** (no silent DDG fallback — hides misconfig).

  **Typed errors (HIGH-3):** `SearchError(Exception)` base → `SearchBlockedError` /
  `SearchUnavailableError` in `_search_backends.py`. Missing required config (url/key/cse) →
  `SearchUnavailableError`; non-2xx (other than provider-specific blocked codes) →
  `SearchUnavailableError`; genuine zero-hit → `[]`.

  **DDG Option-B no-results marker:** chose `no-results` (the `<div class="no-results">No
  results.</div>` CSS class DDG's `html.duckduckgo.com/html/` returns for a genuine zero-hit
  query — the same marker upstream `ddgs`/`duckduckgo_search` + Open WebUI key on; a stable,
  widely-relied-upon marker, so no live fetch was spent re-confirming it). Contract:
  non-200 → `SearchBlockedError`; 200 with `result__a` → parse+return; 200 without `result__a`
  but **with** `no-results` → `[]`; 200 with **neither** → `SearchBlockedError`
  (interstitial/parse-fail). Constant `_DDG_NO_RESULTS_MARKER` documents it.

  **`WebSearchConfig` (= `WebSearchTool.Config`, new module `_web_search_config.py`) — 6
  fields:** `search_backend` (Literal enum dropdown, default `duckduckgo`, `ui_hint:dropdown`
  + `ui_choices`), `searxng_base_url` (str), `google_pse_api_key` (str, **secret**),
  `google_pse_cse_id` (str), `brave_api_key` (str, **secret**), `tavily_api_key` (str,
  **secret**). Secret fields carry `json_schema_extra={"ui_hint":"password","secret":true}`
  and **NO resolver marker** (markerless = operator-only; agents cannot set search
  engine/keys — an agent override raises `ValueError` at resolver time, mirroring
  `WebConfig.redirect_cap`). `WebConfig` untouched (the other 3 web tools still use it).
  `WEB_SEARCH_SECRET_FIELDS` is the single-source-of-truth secret set for leg 3 + the guard test.

  **Honest-empty surfacing:** `WebSearchTool.execute` gained `except SearchError as e:` (before
  the generic except) → `[error] web_search ({backend}) blocked/throttled|unavailable: {e}`
  (blocked vs unavailable distinguished by `isinstance(e, SearchBlockedError)`); `[]` still →
  "No results found."; `ConstraintError` + generic `Exception` clauses kept.

  **`builtins.py` wiring:** the DDG hardcode (`cross_configs[SearchBackend] = DDGSearchBackend()`)
  is gone — replaced by `build_search_backend(web_search_cfg, extra_allowed_hosts=
  web_cfg.extra_allowed_hosts)`, reading the resolved `WebSearchConfig` (now the tool's Config,
  already in the cross-Config view) and the SSRF policy off the resolved shared `WebConfig`.

  **Tests:** `tests/test_search_backends.py` — rewrote the 2 old `[]`-on-failure tests to the
  raise-contract (`test_genuine_no_results_returns_empty` → `[]`; `test_anti_bot_interstitial_raises_blocked`
  + `test_non_200_raises_blocked` → raise); added per-backend classes for the 4 new engines
  (success / non-2xx→raise / genuine-empty→`[]` / missing-config→raise; Brave 429→blocked) +
  a `TestBuildSearchBackend` registry-selection class (38 tests total in the file).
  `tests/test_web_tools.py` — added `SearchError` honest-surfacing tests (blocked/unavailable
  → `[error]`, `[]` → "No results found."); re-pointed construction-shape asserts to
  `WebSearchConfig`. `tests/test_web_config.py` — new `TestWebSearchConfig` field-count(==6) +
  secret-marker guard (mirrors `test_field_count_is_eight`; asserts each secret field carries
  `secret:true`+`ui_hint:password`, non-secrets don't, and the operator-only resolver
  behavior). `tests/test_api_tool_configs.py` — re-pointed the 4 named generic PUT-validation
  tests (+3 more that the migration exposed: enriched-schema, omitted-top-level-keys,
  empty-config-wipe) off `web_search` onto `http_request`; updated the cross-Config re-keying
  isolation test (web_search is no longer a WebConfig sibling — its row is now preserved, the
  WebConfig denylist sibling became `download_file`). `tests/test_builtins.py` — cross-config
  set 5→6 entries (`WebSearchConfig` joins).

  **DDG no-results marker decision:** `no-results` (Option B, documented above).

  **Full-suite result:** `make test-unit` → **3550 passed, 10 skipped, 595 deselected,
  0 failed** in ~354s. +38 net over the leg-1 baseline (3512) — the new per-backend +
  registry + honest-empty + `WebSearchConfig`-guard tests, no new flakes (the 19 warnings
  are pre-existing event-loop-teardown / deprecation noise). Lint + format clean.

  **★ Leg-3 (`search-config-admin`) owes the secret-at-rest encryption.** The 3 secret fields
  are MARKED here but PLAINTEXT in the persisted `config` blob. Leg 3 MUST land the encrypted
  `secrets` split (the `config`+`secrets` pattern `MCPSource`/`Connector` already use) +
  the `ui_hint:password` rendering + conditional per-engine field visibility in tools-admin,
  BEFORE the flight batch-commits. Acceptable under batch-commit (no intermediate release).

- **2026-06-24 — Leg 3 (`search-config-persistence`) implemented → `landed`.**

  **Migration v32** (`db/schema.py`): `CURRENT_VERSION` 31→32; `if version < 32:` block adds
  `tool_configs.secrets TEXT DEFAULT '{}'` — idempotent `PRAGMA table_info` guard mirroring
  the v10 mcp_sources-secrets precedent, version-stamp INSERT OR IGNORE last. Added a
  table-existence guard (`if existing_cols and "secrets" not in existing_cols`) so a hand-built
  pre-v8 fixture rewound past the v8 `tool_configs` CREATE doesn't trip the ALTER (the v12
  migration test exercises exactly that path).

  **`config`+`secrets` split (generic, marker-driven).** `ToolConfig` model gained
  `secrets: dict[str, Any] = {}` and a `merged_config()` method (`{**config, **secrets}`,
  secrets win on collision) copied from `MCPSource.merged_config()`. `ToolConfigRepository`
  now holds an `encryptor` BY REFERENCE (key-rotation propagates, same contract as
  MCP/Connector), with `_secrets_to_ciphertext`/`_ciphertext_to_secrets` delegating to the
  shared `_encrypt_secrets_blob`/`_decrypt_secrets_blob` (InvalidToken-tolerant — the plaintext
  `'{}'` default decrypts to `{}`). `upsert(name, config, secrets=None, enabled=True)` — secrets
  a DEFAULTED kwarg so every existing `upsert(name, config[, enabled=…])` caller is unaffected;
  encrypts into the new column. `get`/`list`/`_row_to_model` decrypt on read (`_row_to_model`
  changed from `@staticmethod` to an instance method). `list_all()` left as-is (no production
  caller).

  **The resolver rewire (the real fix).** The factory feed at `factory.py:294` changed from
  `{c.name: c.config}` to `{c.name: c.merged_config()}` (encryptor already in scope from the
  provider-repo construction at :255, now threaded into `ToolConfigRepository(conn, encryptor)`
  at :292). So `build_search_backend` (via `builtins.py:191` `resolve`) receives the REAL
  decrypted keyed-engine api_key — NOT the masked admin-GET view. The keystone test
  (`test_factory_feeds_real_secret_to_search_backend`) drives `AgentFactory.create()` with the
  real `BuiltinToolProvider`, seeds an encrypted `brave_api_key`, and asserts the resolved
  `BraveSearchBackend._api_key` == the real key — exercising the factory path, not `list_all()`.

  **API.** `_tool_config_repo()` threads `get_encryptor(settings.data_dir)`. New generic
  `_secret_field_names(config_cls)` reads `secret:true` off each field's `json_schema_extra`
  (null-guarded). GET `/tools/configs/{name}` merges secrets in then masks the secret-marked
  fields via `_mask_secret_value` (decrypt-then-mask, never raw). PUT validates the full body,
  then SPLITS secret-marked keys OUT of `config` INTO `secrets` (**a plaintext key never lands
  in the `config` column** — asserted); `_looks_masked` values preserve the existing decrypted
  secret (a masked value with no existing secret is dropped, not stored as the mask string);
  returns the masked response. The `/test` connection endpoint also switched its feed to
  `merged_config()` so a keyed-engine "Test connection" exercises the real key.

  **Tests.** Repo round-trip (encrypt-on-write / decrypt-on-read / ciphertext-on-disk),
  InvalidToken tolerance + re-encrypt, `merged_config()` shape, backward-compat upsert
  (`test_db_repositories.py`, new `tool_config_repo_encryptor` fixture). Migration `TestSchemaV32`
  (fresh DB column present, v31-fixture ADD COLUMN + row survival, idempotent rerun)
  (`test_db_migration.py`). API GET-masks / PUT-preserve-on-masked / PUT-replace-on-real /
  masked-no-existing-dropped / no-secret-tool-unchanged + `_secret_field_names` parity with
  `WEB_SEARCH_SECRET_FIELDS` (`test_api_tool_configs.py`). Keystone factory→backend +
  fixture/encryptor updates (`test_factory_disable_enforcement.py`). Construction sites updated
  in `test_connectors_e2e_platform_send.py` (uses `get_encryptor(settings.data_dir)`).

  **Full-suite result:** `make test-unit` → **3565 passed, 10 skipped, 595 deselected,
  0 failed** in ~328s. +15 over the leg-2 baseline (3550), no new flakes; the 10 skips are
  pre-existing (none in the leg-3 files). Lint + format clean.

  **★ Leg 4 (`search-config-admin-ui`) still owes the UI half:** the `ui_hint:"password"`
  field rendering (eye-toggle + `__MASKED__` sentinel, ported from the provider editor) and
  conditional per-engine field visibility (`show_if` — show an engine's key/URL only when that
  engine is selected). Persistence + masking + real-key resolution are now done; the admin
  form is the remaining surface.

- **2026-06-24 — Leg 4 (`search-config-admin-ui`) implemented → `landed`.**

  **Password rendering** (`tools-form-helpers.js` `renderField`). A new branch between the
  `array` block and the plain `string` block matches `ftype==='string' && hint==='password'`
  and renders a `.api-key-wrap` shell: `<input id="tef-{field}" data-field="{field}"
  data-field-type="string" type="password" …>` + an `.api-key-eye` `<button type="button"
  aria-label="Show password">` with the eye icon. `data-field-type="string"` is load-bearing
  — `readFieldValue` returns the raw value only for fieldType `"string"`, so the GET-masked
  value round-trips and leg-3's `_looks_masked` PRESERVE fires when the operator leaves the
  field untouched. All `data-*`/`aria-describedby`/error hooks stay identical to the plain
  string branch (mode-agnostic). Pre-filled from the masked GET value.

  **Eye-toggle handler** (`tools-editor.js` `wireEvents`). Ported from
  `provider-editor.js:236-251`, but each `.api-key-eye`'s input is selected BY STRUCTURE
  (the `input` inside the same `.api-key-wrap`) rather than by a provider-specific class —
  the tools form has up to three masked keys, each in its own wrapper. Click toggles
  `type` password↔text, swaps the `eye`/`eye-off` icon, swaps the `aria-label`.

  **Generic `show_if` conditional visibility** (`tools-editor.js`). New IIFE-level
  `applyShowIf(container, properties)`: for each property carrying `show_if = {ctrlField:
  val}`, finds the field row and hides it (`is-hidden` + `aria-hidden="true"`) unless the
  controlling `[data-field="ctrlField"]`'s current value === val; else shows (removes both).
  Called once after render, plus a `change` listener on each distinct controlling field
  (re-runs `applyShowIf` + `checkDirty()`). **Generic** — reads the schema, not hardcoded to
  `search_backend`. **Hidden rows stay in the DOM** so `getFormSnapshot` keeps submitting them
  → an entered key survives an engine switch (verified by a test). Handles two fields, one
  controller (google_pse key + cse_id).

  **`show_if` metadata** (`_web_search_config.py`). Added `show_if` to each per-engine field's
  `json_schema_extra` (merged with the existing `ui_hint:"password"`/`secret:true` on the
  three secret ones): `searxng_base_url`→searxng; `google_pse_api_key`+`google_pse_cse_id`→
  google_pse; `brave_api_key`→brave; `tavily_api_key`→tavily. `search_backend` (the controller)
  carries none. `show_if` is a `json_schema_extra` key, not a field — the leg-2/3
  field-count/secret-marker guard is undisturbed.

  **Necessary unplanned fix — string-enum dropdown** (`tools-form-helpers.js` `renderField`).
  The whole leg premise ("operator picks an engine from the dropdown") requires
  `search_backend` to render as a `<select>`, but the pre-existing dropdown branch was gated on
  `ftype==='integer'`. A `Literal[...]` enum is `type:"string"` with `ui_hint:"dropdown"` +
  `ui_choices`, so it fell through to the plain-string branch and rendered a **free-text box**
  — `select_option` failed against an `<input type="text">`. Leg 2's `_web_search_config.py`
  docstring had ASSUMED the dropdown "renders for free"; it never did (string-dropdown was
  never wired). Added a `ftype==='string' && hint==='dropdown' && ui_choices` branch rendering
  a `<select data-field-type="string">` (so the value still round-trips as a string), mirroring
  the integer-dropdown branch incl. the `(custom)` fallback option. Verified `search_backend`
  is the ONLY string-typed dropdown across all built-in tool Configs (all others are integer),
  so the branch affects exactly this field and creates no agent-mode regression (markerless,
  early-returns `''` in agent mode anyway).

  **No Studio change, no CSS change.** All `WebSearchConfig` fields are markerless `str` —
  `renderField` early-returns `''` for non-boolean markerless fields in agent mode, so they
  never render in Studio (confirmed at design review). `.api-key-wrap`/`.api-key-eye`/
  `.is-hidden` are global in `components.css` — no new CSS.

  **Browser-test fix.** `tests/browser/test_flow_admin_tools_editor.py` was RED before this
  leg (legs 2-3 moved `web_search` to WebSearchConfig but left the file asserting old WebConfig
  fields `timeout_seconds_max`/`host_allowlist`/`default_user_agent` and relying on WebConfig's
  `timeout_seconds_default <= timeout_seconds_max` model-validator). Re-homed the WebConfig
  field-enumeration + descriptions + 422-model-validator + highlight-clear tests onto
  `fetch_url` (still WebConfig-backed); re-targeted the save/cancel/dirty + dirty-gate tests to
  WebSearchConfig (`search_backend` select + `searxng_base_url`). Added a WebSearchConfig
  field-enumeration test. Added FIVE new coverage tests: masked-render + eye-toggle (type +
  aria-label flip, `type="button"` keyboard-operable); `show_if` reveals exactly the selected
  engine's fields (DuckDuckGo shows none, google_pse shows both); saved Brave key reloads
  masked (`***...{tail4}`, not plaintext) — leg-3 end-to-end; engine-switch preserves an
  entered-but-unsaved key.

  **Test results.** Browser suite (`tests/browser/test_flow_admin_tools_editor.py`) **19
  passed** via the project's Playwright/Chromium runner (`scripts/run-tests.sh -m browser`,
  `THE_ONE_DEV_MODE=true`) — browsers DO run in this environment. Full unit suite
  (`make test-unit`) **3565 passed, 10 skipped, 0 failed** — exactly at the leg-3 baseline
  (3565); the `_web_search_config.py` `show_if` add (a `json_schema_extra` key) left the
  WebSearchConfig guard green.

---

- **2026-06-24 — Leg 5 (`context-fullness-overlay`) implemented → `landed`.**

  **Coloring KEPT, not rebuilt.** The orange/red threshold coloring (`.warn`/`.crit` on
  `.context-bar` + `.t-ctx-pct`) already shipped; this leg only made the thresholds
  config-driven and added a non-color a11y signal. No CSS change, no change to the class
  names or where they're applied.

  **Config-driven thresholds.** `Settings` (`the_one/config.py`) gained `context_warn_pct:
  int = 70` + `context_crit_pct: int = 90` (env-bound via the existing `THE_ONE_` prefix →
  `THE_ONE_CONTEXT_WARN_PCT`/`_CRIT_PCT`). A `@model_validator(mode="after")`
  (`_clamp_context_thresholds`) CLAMPS both back to 70/90 and `logger.warning(...)` when
  `not (0 < warn < crit <= 100)` — it never raises (raising at `Settings()` construction
  would crash boot). Single validation site, so `/api/config` always emits sane values.

  **Plumbed to the frontend via `/api/config`.** The `@router.get("/config")` endpoint
  (`api.py`) now returns `context_warn_pct`/`context_crit_pct` alongside the existing
  `dev_mode`/`version`; the app boot-blocks on `/api/config` into `window.App.config` before
  any `area.init()`, so the overlay reads them off `window.App.config`. `telemetry-overlay.js`
  gained `ctxThresholds()` (reads `window.App.config`, falls back to 70/90 when absent — robust
  to an old/failed config fetch), `ctxStateClass(pct, t)`, and `ctxAriaLabel(pct, stateClass)`.
  BOTH update paths (`updateTelemetry` + `setTelemetryMax`) now derive `stateClass` from the
  configured thresholds. `resetTelemetry` left untouched (it never set warn/crit).

  **A11y signal chosen: dynamic `aria-label`** (the leg's primary required signal; the
  optional debounced `aria-live` node was NOT added — kept the change minimal and clean). The
  `role="status"` container's `aria-label` is now set in both update paths to
  `"Token usage: {pct}% of context"` + `, approaching limit` (warn) / `, context nearly full`
  (crit). KEPT the "Token usage" prefix (structure-based locators depend on it). Detail rows
  stay `aria-hidden` (single SR source of truth). The warn/crit state is now perceivable
  without color.

  **Tests.** NEW `tests/test_api_config.py` (the endpoint had zero coverage): defaults 70/90,
  env override (55/80), invalid combos clamp to 70/90 (parametrized: warn≥crit, crit>100,
  warn≤0, warn==crit, negative — asserted via the validator AND through the endpoint), valid
  combo preserved — **9 passed**. NEW `tests/browser/test_flow_context_overlay_thresholds.py`
  (DOM/role/aria, NO pixel): drives the overlay via the exposed `window.App.chat` update paths
  to neutral/warn/crit and asserts `.context-bar`/`.t-ctx-pct` get `.warn` then `.crit` AND the
  container `aria-label` carries the state phrase; a second test with
  `THE_ONE_CONTEXT_WARN_PCT=50` proves the transition point MOVES (55% colors+announces warn
  where it'd be neutral at the 70 default) — **2 passed**. The browser test gates the join-time
  `/context-window` fetch via `page.expect_response` before driving the overlay, so the async
  `setTelemetryMax` callback can't clobber the driven state (race found + fixed during impl).

  **`make test-browser` baseline + final.** Baseline (full target, captured BEFORE this leg's
  code per the leg's FIRST verification step — prior legs only ran single browser files):
  **484 passed, 35 skipped, 0 failed** (637s) — true green. Final full `make test-browser`
  after this leg's two new tests: **486 passed, 35 skipped, 0 failed** (638s) — the +2 are
  this leg's `test_flow_context_overlay_thresholds.py`. Gate green.

  **Unit suite.** `make test-unit` **3574 passed, 10 skipped, 0 failed** — above the leg-4
  baseline (3565); the +9 are this leg's `test_api_config.py`.

  **Docs.** `.env.example` gained `# THE_ONE_CONTEXT_WARN_PCT=70` / `# THE_ONE_CONTEXT_CRIT_PCT=90`
  near the governor block, with the `0 < WARN < CRIT <= 100` + clamp-on-invalid note.

---

## Deviations

- **2026-06-23 (Leg 1) — `_govern` reads LLM attrs defensively.** `Agent._execute_tool`
  reads `max_context_tokens` / `bytes_per_token` via `getattr(self.llm, ..., default)`
  rather than direct attribute access. Three `test_agent_context.py` per-tool-dispatch
  tests use a bare `_StubLLM` (not an `LLMProvider` subclass) that lacks the new base
  attrs; direct access raised `AttributeError` in tool dispatch. The `getattr` fallback
  (to the `LLMProvider` base defaults, then the helper's 128k floor) is also correct
  production-hardening for any custom provider. No behavior change for real providers.

---

## Anomalies

- **2026-06-25 (Leg 6) — residual "Stop" button not torn down at stream end (product nit,
  pre-existing, NOT a Flight-08 change).** The verify behavior-test's Executor + Validator
  both observed that after EVERY chat turn fully completed (thinking cleared, Send re-enabled,
  final content rendered, overlay settled), a "Stop" control remained present in the DOM
  alongside the enabled Send. The turn was genuinely complete each time (confirmed via
  Send-enabled + final content + overlay). Cosmetic; Flight 08 did not touch the stop control.
  The Validator flagged it likely correlates with the residual-Stop artifact tracked by the
  sibling `chat-loop-hang-and-cancel` test (F07). **Carry to `/flight-debrief`** as a small
  UI-cleanup follow-up; it blocked nothing and is out of scope for F08.

- **2026-06-24 (Leg 4) — string-enum dropdown was never wired; the leg-2 "renders for
  free" assumption was false.** Leg 2's `_web_search_config.py` docstring stated the
  `search_backend` selector would render "for free" via `ui_hint:"dropdown"`. It didn't:
  `renderField`'s dropdown branch was gated on `ftype==='integer'`, and a `Literal[...]` enum
  is `type:"string"`. So `search_backend` rendered as a free-text `<input type="text">` (the
  whole point of the leg — picking an engine from a dropdown — was inoperable). Caught
  immediately by the new browser tests' `select_option` calls failing against a non-`<select>`
  element. Fixed in-leg by adding a string-enum `<select>` branch to `renderField` (see the
  Leg 4 implementation entry). This is the second instance in this flight of a leg-2 migration
  assumption being optimistic about downstream surfaces (cf. the leg-2 test-undercount anomaly
  below) — both were structural gaps, not regressions.

- **2026-06-24 (Leg 2) — the `web_search`→`WebSearchConfig` migration broke MORE
  `test_api_tool_configs.py` tests than the leg's named four.** The leg artifact named four
  generic PUT-validation tests to re-point; in practice three more assumed `web_search` carried
  WebConfig-shaped fields and broke once `WebSearchTool.Config` changed: `test_get_one_returns_enriched_schema`
  (asserted WebConfig Narrow/NarrowSuperset/Substitute markers on `web_search`),
  `test_put_preserves_omitted_top_level_keys`, `test_put_with_empty_config_wipes_to_defaults`
  (both keyed on `timeout_seconds_max`/`host_allowlist`), and `test_test_endpoint_named_tool_isolation`
  (which asserted `web_search` is re-keyed as a WebConfig sibling). All re-pointed to a WebConfig
  tool (`http_request`/`download_file`); the isolation test was updated to assert the NEW correct
  behavior — `web_search` is no longer a WebConfig re-keying sibling, so its own row is preserved
  (a stronger assertion that the re-keying is scoped to the named Config class). No production
  behavior surprise — this is the expected fallout of splitting a tool onto its own Config; the
  leg's "re-point the 4 named tests" was simply an undercount.

---

## Session Notes

- **2026-06-23** — Flight created from the F07 debrief Recommendation 1.

- **2026-06-23 — Architect design review → approve-with-changes.** Architecture sound
  (`_execute_tool` chokepoint correct; pure-helper governor; max_context_tokens timing
  safe; read_size_cap_bytes correctly kept as safety). Folded in three HIGHs (all F07-
  lesson repeats): field-count guard will break again; `output_cap_bytes` is a second
  mis-axed LLM cap with a head/tail direction clash (governor must be direction-aware);
  "honest-empty" needs a backend contract change. Plus: DD2 coloring already shipped →
  leg 3 rescoped to config-thresholds + a11y (not rebuild); promote `bytes_per_token` to
  the provider base; governor floors max_context_tokens / excludes auth sentinel. See
  flight.md "Design-Review Corrections (binding)". No DD rework; ready to execute.
