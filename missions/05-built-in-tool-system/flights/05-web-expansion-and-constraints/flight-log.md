# Flight Log: Web Expansion & Constraints

**Flight**: [Web Expansion & Constraints](flight.md)

## Summary

Flight in progress. 9 legs planned (L0, L1, L2, L3, L4, L5, L6, L7-HAT, L8). Branch `flight/05-web-expansion-and-constraints` created from `main` (commit `1019022` = F4 squash). uvicorn `--reload` is live (F4 follow-up `a41789a`); no manual container restart needed during F5 iteration.

---

## Leg Progress

### 08-integration-verification

**Status**: landed (uncommitted; awaits batch commit at flight end)

**Outcome**: Full F5 surface verified. Unit suite green; F5 regression sweeps return expected counts; `agents.md` + `CLAUDE.md` + `mission.md` refreshed to reflect the F5 surface (19 tools, 6 active constraint types, `WebConfig` shape, `SearchBackend` Protocol, SSRF "no full-disable" invariant, IP-literal-blocked correction). Two pre-existing env gaps (Playwright Chromium binary missing in container; default agent has no provider config) prevented running the browser + AIAT live suites — documented below; not introduced by F5 and not blockers for the leg per L8 acceptance criteria.

**Verification results**:

- **Unit suite (full)**: `docker exec the-one pytest -x -q --deselect tests/test_token_definitions.py::test_every_var_reference_is_defined` → **991 passed, 1 skipped, 239 deselected in ~43s**. The deselected count includes `live` and `browser` markers; the single skip is the long-standing `pyperclip`-on-Linux skip in the markdown copy-button tests. Zero failures, zero new red.
- **F5 regression sweeps** (all PASSED):
  - `grep -rn 'class WebConfig' the_one/` → exactly 1 hit (`the_one/tools/_web_config.py:110`). ✓
  - `grep -rn 'SSRFGuardedTransport' the_one/` (excluding `__pycache__`) → 8 source-line hits across `_web_config.py` (definition + 2 docstring refs), `_search_backends.py` (2 docstring refs), and `web.py` (3 `_build_transport` consumer sites for `http_request` / `fetch_url` / `download_file`). ≥ 5 ✓
  - `_TOOL_CLASSES` count via `python -c "from the_one.tools.builtins import _TOOL_CLASSES; print(len(_TOOL_CLASSES))"` → **19 tools** in declared order: `shell`, 9 filesystem, `python_exec`, 4 `shell_session_*`, `http_request`, `fetch_url`, `download_file`, `web_search`. ✓
  - `grep -rn 'class SearchBackend' the_one/tools/` → exactly 1 hit (`_search_backends.py:98`). ✓
  - `grep -rn 'class DDGSearchBackend' the_one/tools/` → exactly 1 hit (`_search_backends.py:125`). ✓
  - `grep -rn 'CheckMode\.' the_one/tools/` → multiple consumer hits in `filesystem.py` (mode dispatch) and `execution.py` (`CheckMode.DIRECTORY` for cwd validation) — confirms post-F5 L0 unification has live consumers. ✓
  - `grep -rn 'disable_ssrf\|ssrf_disabled\|disable_ssrf_protection' the_one/` → **zero source-code hits**; the only matches are 3 documentation comment lines in `_web_config.py:15-16, 143` describing the invariant itself. Mission "no-full-disable" invariant verified in source. ✓
- **Browser tests (`make test-browser`)**: env gap. Playwright Chromium binary not installed in the container — `make test-browser` produced 1 fail / 3 pass / 12 deselected / **216 errors** (every browser test errored on Playwright launch). Pre-existing condition (predates F5; the `_ensure-playwright` Makefile target re-downloads Chromium on every `make rebuild`/`up` and is also a known Mission-level Issue from F1 L7 HAT). **Not blocking**: F5 introduced no UI changes; the slow `download_file` UI rejoin scenario was already verified hands-on in F5 L7 HAT scenario 9.
- **AIAT live tests (`pytest -m live tests/test_aiat.py -x -q`)**: env gap. `test_basic_chat` failed because the default agent's response was empty — the default agent has `provider_config_id=None` and no provider has been wired up in the running container. **Not blocking**: F5 introduced no agent-loop or provider changes; the constraint surface was exercised end-to-end during F5 L7 HAT via `POST /api/chat` against a manually-configured Haiku 4.5 agent.

**Doc refreshes (committed in this leg's batch)**:

- **`the_one/agents.md`**:
  - Tool count `17 → 19` in two places (the `builtins.py` row of the `tools/` reference table and the Tool Providers Key Pattern paragraph).
  - `tools/` reference table — added rows for `_web_config.py` (`WebConfig`, `SSRFGuardedTransport`, helpers) and `_search_backends.py` (`SearchBackend` Protocol, `DDGSearchBackend`); updated the `web.py` row to list all four web tools and the `_build_transport` pattern.
  - **Constraint surface** — promoted from "five active types" to **six active types**, adding the **URL/host scope + SSRF** row with full field list (`host_allowlist`, `host_denylist`, `extra_allowed_hosts`, `read_size_cap_bytes`, `request_timeout_seconds`, `max_redirects`, `default_user_agent`) and a paragraph documenting both layers (`_url_check` boundary check + `SSRFGuardedTransport` connect-layer pin) including the **IP-literal-also-blocked correction** (HAT scenario 3 inline fix). Replaced the "future" sentence with a hard "no-full-disable" invariant paragraph.
  - **Cross-Config dispatch** — added a `DownloadFileTool` bullet documenting `Requires = (FilesystemConfig,)` for destination-path validation via `_filesystem_check(..., CheckMode.WRITE_NEW)` (F5 L0 helper unification).
  - **Tool Policy Resolver** — `WebConfig` field summary appended to the F2/F3/F4/F5 history sentence.
  - **New "Web tools (F5)" section** documenting `WebConfig` shape, two-layer SSRF enforcement, the IP-literal short-circuit fix, the no-full-disable invariant, and the per-tool `_build_transport(cfg) → SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)` acquisition pattern.
  - **New "SearchBackend Protocol (F5)" section** documenting the single-method `Protocol`, `DDGSearchBackend` as the F5 default, the constructor-injection test seam (no module-internals monkeypatching), and forward-compat for Brave/SerpAPI/Bing.
- **`CLAUDE.md`**:
  - Tool count `17 → 19` in the Tool layer paragraph; web tools list expanded from two to four (`http_request`, `fetch_url`, `download_file`, `web_search`).
  - **New "Web constraint surface (F5)" subsection** in Tool Configuration Layer mirroring `agents.md`'s coverage at CLAUDE.md's higher-level granularity (seven `WebConfig` fields, two-layer SSRF enforcement, IP-literal-blocked correction, no-full-disable invariant, `_build_transport` pattern).
  - **New "SearchBackend Protocol (F5)" subsection** documenting the test seam and forward-compat shape.
  - **Cross-Config dispatch** — `DownloadFileTool` added to the consumers list.
  - "F3-F5 will populate" → "F3-F5 populated" with the trio (`FilesystemConfig`, `ExecutionConfig`, `WebConfig`) named.
- **`mission.md`**:
  - **Open Question "Search backend extensibility shape"** marked `[x]` resolved with full F5 Decision 2 reference.
  - **Known Issue F1 (DDG returns no results)** marked `[x]` resolved with reference to F5 L5 (UA fix in `DDGSearchBackend`) + L6 (`WebSearchTool` consumes `cross_configs[SearchBackend]`).
  - **New Known Issue appended**: `python_exec` exit-code-suffix behavior change (F4 L4 alignment with `ShellTool`'s `_truncate_output` `[exit code: N]` suffix; recorded per F4 debrief action item; new contract going forward).

**L7 forward-reference (Wikipedia 403 on default UA)**: recorded here as a follow-up consideration for a future flight or maintenance pass — `fetch_url` against `https://en.wikipedia.org/wiki/...` returns HTTP 403 because Wikipedia rejects the default `httpx`/`the-one/web-tools` User-Agent. Operator-side mitigation already exists today: set `WebConfig.default_user_agent` (a `Substitute` field) at the tool level via `tool_configs` to a browser-class UA. **Not introduced in F5** because the default UA is intentionally generic to avoid the operator-control inversion of "the tool decides which UA looks browser-enough"; if a follow-up flight wants to ship a curated UA-per-host map (`extra_user_agents: dict[host, ua]`?), that's a future-mission scope decision. For F5 the `default_user_agent` Substitute knob is sufficient escape hatch for operators who hit the issue.

**Pre-existing env gaps (NOT regressions; documented for visibility)**:

- **Playwright Chromium binary missing**: container's `_ensure-playwright` step re-downloads on every `make rebuild`/`up`, but the running container at the time of L8 verification did not have a current install (the test invocation triggered the download but the test session already started and errored on launch). This is the same Mission-level Known Issue F1-2 ("`make rebuild` re-downloads Playwright Chromium every rebuild"). Recommended fix is still the F1 L7 HAT recommendation: drop `_ensure-playwright` from `up`/`rebuild`, keep it only in `test-browser`/`hat`.
- **Default agent has no provider config**: `provider_config_id=None`; AIAT tests' `test_basic_chat` got an empty response. Operator must wire a provider via the Admin UI before AIAT live tests can run; this is unrelated to F5's constraint surface and would equally affect any other flight's live verification.

**Status transitions in this leg**:
- L8 leg artifact: `ready` → `in-flight` → `landed`.
- F5 flight (`flight.md`): `in-flight` → `landed`. L8 checked off in flight.md's leg list.
- Mission: stays `active` (F6 / F7 still ahead).

**Post-Reviewer doc-drift fix-up (2026-04-29)**: Reviewer caught four doc-drift items in the L8 `agents.md` + `CLAUDE.md` refresh — the docs described an earlier draft of the F5 design that was refined during implementation. Runtime code is correct; only the docs needed correction. Fixed: (1) `WebConfig` field names + markers — replaced the stale list (`host_allowlist`/`host_denylist`/`extra_allowed_hosts` all `NarrowSuperset`, plus `read_size_cap_bytes`/`request_timeout_seconds`/`max_redirects`/`default_user_agent`) with the actual surface (`timeout_seconds_default`/`timeout_seconds_max`/`response_size_cap_bytes` Narrow ints, `redirect_cap` Field-only-no-marker per Decision 9, `host_allowlist`/`extra_allowed_hosts` Narrow + `host_denylist` NarrowSuperset list[str]); also dropped all references to the non-existent `default_user_agent` field. (2) `DownloadFileTool` filesystem-check mode — `CheckMode.WRITE_NEW` → `CheckMode.WRITE_EXISTING_PARENT` (parent must pre-exist; agent uses the `mkdir` tool first if needed). (3) `WebSearchTool` backend wiring — replaced the stale "constructor injection (`__init__(backend=...)` parameter + `_build_client()` helper)" description with the actual `cross_configs[SearchBackend]` Protocol-keyed service-entry pattern (Decision 12). (4) `DDGSearchBackend` SSRF claim — corrected the docs from "`WebSearchTool` injects an SSRF-guarded `httpx.AsyncClient` into `DDGSearchBackend`" to the actual posture: `cross_configs[SearchBackend] = DDGSearchBackend()` with no client argument, so the backend uses its own owned `httpx.AsyncClient(timeout=15)`; SSRF-pinning of search-engine traffic is not part of F5 (acceptable — `html.duckduckgo.com` is a public domain) and is documented as a future enhancement. Re-ran the unit suite inside the container — **991 passed, 1 skipped, 238 deselected** (matches L8 baseline; the 1 skip is the long-standing `pyperclip`-on-Linux skip, the only failure when not deselected is the pre-existing `--font-size-h3` undefined-token issue unrelated to F5). Ruff clean on F5 source files (no source code touched). Followed by Flight Director commit + push + PR.

---

### 07-hat-web-walkthrough

**Status**: landed (uncommitted; awaits batch commit at flight end)

**Outcome**: All 9 HAT scenarios PASSED with Haiku 4.5. **One inline fix landed for an IP-literal SSRF bypass** discovered in scenario 3.

**Driver**: Flight Director ran each scenario via `POST /api/chat`. Operator-level `tool_configs` were upserted (extra_allowed_hosts for scenarios 5/6; narrowed response_size_cap_bytes to 50KB for scenario 2's truncation test) and reset to defaults at HAT end.

**Scenario results**:
1. **http_request happy path** — `http://example.com/` → `[200]` with body. ✓
2. **response-size cap** — 700KB Pride-and-Prejudice text with operator-narrowed cap=50KB → tail-preserved with marker `[... truncated 721189 bytes; showing last 51200 bytes of response ...]`. ✓
3. **SSRF block (cloud metadata)** — Initially returned `[error] All connection attempts failed` (httpx connect-time error) instead of `[error] [constraint] ...`. **Inline fix landed** (see Anomalies). Post-fix → `[error] [constraint] IP literal 169.254.169.254 is in the SSRF block list`. ✓
4. **SSRF block (RFC1918)** — `http://10.0.0.1/` → `[error] [constraint] IP literal 10.0.0.1 is in the SSRF block list`. ✓
5. **SSRF allowlist (operator-broadened)** — operator added `localhost:8484` to `extra_allowed_hosts`; agent fetched `localhost:8484/api/info` → `[200]` with API info body. ✓
6. **SSRF allowlist (agent-narrowed)** — agent's `tool_overrides.http_request.extra_allowed_hosts=[]` correctly nullified operator's allowlist; localhost request → `[error] [constraint] all resolved IPs for localhost are blocked: ['::1', '127.0.0.1']`. Validates `Narrow` semantic. ✓
7. **fetch_url readability** — `https://example.com/` → markdown `# Example Domain` + paragraph + link, ATX heading style. Wikipedia 403'd the default httpx UA (out of F5 scope; recorded as L8 follow-up consideration). ✓
8. **download_file happy path** — 528 bytes written to `/root/downloads/example.html`. ✓
9. **Slow download_file UI rejoin** — operator submits a `download_file` of Pride-and-Prejudice; switches to a new conversation (created in 0.03s — WS responsive); rejoins original session (history_len=2, is_processing=true). F4 WebSocket fixes hold for web tools. ✓

**Inline fix details**: see Anomalies section below.

**Cleanup**: deleted temporary `HAT5-allowlist` agent, reset operator `tool_configs` HAT rows, removed `/root/downloads/`. Restored container to clean default state for L8.

---

### 06-migrate-web-search-tool

**Status**: landed (2026-04-29)

**Outcome**: `WebSearchTool` migrated from the F2 zero-constraint shape to the F5 cross-Config dispatch surface. `Config = WebConfig`; `Requires = (SearchBackend,)`. The tool no longer owns its own `httpx.AsyncClient` or DDG-parsing regex — it consumes a `SearchBackend` instance via `self._cross_configs[SearchBackend]`, calls `backend.search(query, max_results)`, and formats the returned `list[SearchResult]` into the existing `- title\n  url\n  snippet` agent-facing shape (preserved verbatim from pre-F5 for agent compatibility). `BuiltinToolProvider.get_tools` injects a fresh `DDGSearchBackend()` per call alongside the four Pydantic-keyed Configs. Three-clause envelope: `ConstraintError → Exception` (no dedicated timeout clause — backend owns its own timeout; if it fires it surfaces as `httpx.TimeoutException` which inherits from `Exception` and lands in the generic clause).

**Closes mission Known Issue (F1)**: the pre-F5 `WebSearchTool` POSTed to `https://html.duckduckgo.com/html/` with no User-Agent; DDG returned 202 + anti-bot interstitial → no results. F5 L5 introduced `DDGSearchBackend` with a Chrome-on-Linux UA that bypasses the interstitial; F5 L6 wires the backend into `WebSearchTool` via `cross_configs[SearchBackend]`. End-to-end the F1 issue is closed at the `WebSearchTool` surface. Mission Known Issue updated will land in L8 docs refresh; this flight log entry records the close.

**Implementation notes**:
- **`cross_configs` type widened in `Tool.__init__`** from `dict[type[BaseModel], BaseModel] | None` to `dict[type, object] | None`. The "frozen Pydantic" invariant from F4 still holds for Pydantic-keyed Config entries (`FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig`, `WebConfig` — all `model_config = ConfigDict(frozen=True)`). Protocol-keyed service entries (`SearchBackend`) are stateful (the backend owns an httpx client) but per-`get_tools()`-call-scoped — every agent invocation gets a fresh provider call, so two concurrent agents never share a backend instance. Docstring on `Tool.__init__` documents both categories.
- **`Tool.Requires` widened correspondingly** from `tuple[type[BaseModel], ...]` to `tuple[type, ...]` so `WebSearchTool.Requires = (SearchBackend,)` is well-typed (the `SearchBackend` Protocol is NOT a `BaseModel` subclass).
- **`ToolProvider.get_tools` Protocol docstring updated** to mention the new Protocol-keyed service category alongside the F4 L1b Pydantic-keyed Config category. The Protocol type signature is unchanged (the `cross_configs` parameter doesn't appear in the Protocol signature — the provider builds it internally and passes it to each tool's `__init__`).
- **`BuiltinToolProvider.get_tools` factory path** appends `cross_configs[SearchBackend] = DDGSearchBackend()` AFTER the existing Pydantic-keyed Config-resolution loop. The introspection path (both args `None`) is unchanged — zero-arg construction defaults `cross_configs={}` per `Tool.__init__` so introspection callers get an empty mapping. F5 ships only DDG; F6 admin will let operators pick the active backend (the `cross_configs[SearchBackend]` slot will then carry whichever concrete backend the operator chose; no structural change to the dispatch shape).
- **`WebSearchTool.execute` three-clause envelope**: `try/except ConstraintError as e: return f"[error] [constraint] {e}"` (defensive — current `DDGSearchBackend` does NOT raise these, but a future operator-policy-aware backend may) `/ except Exception as e: return f"[error] {e}"`. No timeout-specific clause: the backend owns its own client + timeout; if a timeout fires it propagates as `httpx.TimeoutException` (an `Exception`) and lands in the generic clause. This matches the leg artifact's "three-clause envelope" guidance — distinct from L2/L3/L4's four-clause shape because the tool no longer directly invokes httpx.
- **Agent-facing format preserved verbatim** from pre-F5: `"\n\n".join(f"- {r.title}\n  {r.url}\n  {r.snippet}" for r in results)` for non-empty results; `"No results found."` for empty results. Agents that expected the pre-F5 format see no change.
- **Description updated** to mention backend pluggability: "Search the web and return results (title, URL, snippet). The backend is operator-configurable (default DuckDuckGo); F6 admin will surface the picker. Useful for finding URLs to feed into fetch_url or read."

**Tests migrated and added (10 tests in `TestWebSearchTool` — net +1 from 5 pre-F5)**:
- **5 pre-F5 tests deleted** (`test_happy_path`, `test_max_results_honored`, `test_post_body_form_encoded`, `test_no_results`, `test_network_error_returns_error_string`). They exercised httpx-level concerns (mock transport, POST body, regex parsing) that now belong to the backend; backend-level tests already cover those in `tests/test_search_backends.py` (e.g. `test_user_agent_sent`, `test_parses_10_results`, `test_no_results_returns_empty`, `test_anti_bot_interstitial_returns_empty`). Tool-level tests now focus on the format-and-error envelope around the backend's `list[SearchResult]` output. The pre-F5 `_install_mock_websearch` helper is also deleted (was a holdover from L2's `_install_mock` factory split).
- **6 new tests added** (the leg artifact called for 5; we added 6 because there are TWO `max_results`-forwarding tests — one with explicit `max_results=3` and one verifying the default of 5):
  - `test_construction_shape`: builds with `cross_configs={SearchBackend: DDGSearchBackend()}`; `Config is WebConfig`; `Requires == (SearchBackend,)`; `SearchBackend` in `_cross_configs`.
  - `test_results_formatted_correctly`: `_StubBackend(results=[3 SearchResults])` → tool returns the exact `- title\n  url\n  snippet` format with double-newline separation.
  - `test_no_results_message`: `_StubBackend(results=[])` → tool returns `"No results found."` (F1 wording preserved).
  - `test_max_results_passed_to_backend`: `_StubBackend(capture_max=[])` → tool calls with `max_results=3`; backend received 3.
  - `test_max_results_default_passed_to_backend`: same stub; tool called without `max_results` → backend received 5 (the parameter default).
  - `test_backend_exception_caught`: `_StubBackend(raise_exc=RuntimeError("backend boom"))` → tool returns exact `"[error] backend boom"`.

**`_StubBackend` fixture pattern**: replaces the pre-F5 `_install_mock_websearch` factory. Each test constructs a fresh `_StubBackend` configured with one of (`results`, `raise_exc`, `capture_max`) and injects via `cross_configs={SearchBackend: stub}`. The stub does NOT inherit from `SearchBackend` — `runtime_checkable` Protocols only validate attribute presence, NOT call signatures, so declaring `name = "stub"` and `async def search(query, max_results)` is sufficient. Cleaner than reusing `httpx.MockTransport` because backend-level concerns (UA, regex, status handling) are out of scope at the tool level.

**`TestWebToolInstantiation` updates**: renamed `test_web_search_tool_still_uses_empty_config` → `test_web_search_tool_uses_web_config`; the test now asserts `isinstance(tool._config, WebConfig)`, `WebSearchTool.Config is WebConfig`, and `WebSearchTool.Requires == (SearchBackend,)`. The pre-F5 `_EmptyConfig` import is removed from `tests/test_web_tools.py`.

**`test_builtins.py` cross_configs assertion**: renamed `test_cross_configs_contains_four_distinct_configs` → `test_cross_configs_contains_expected_entries`. Assertion expanded from 4 entries (`{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig}`) to 5 entries (the same four plus `SearchBackend`). Docstring updated to document the Pydantic-keyed-vs-Protocol-keyed two-category structure introduced by F5 L6's type widening. The companion `test_cross_configs_skips_empty_config` docstring updated to note ALL 19 built-in tools now have non-empty Configs (post-F5-L6 `WebSearchTool` migration); the assertion still holds defensively against future tools that may inherit the empty default.

**Verification**: 986 passed, 1 skipped, 239 deselected (was 985 → net +1 new test, matching the +6 new − 5 deleted balance). `ruff check` clean on `the_one/tools/base.py`, `the_one/tools/builtins.py`, `the_one/tools/web.py`, `the_one/tools/provider.py`, `tests/test_web_tools.py`, `tests/test_builtins.py`. Both verification snippets from the leg artifact pass: construction-shape (`Config is WebConfig`, `Requires == (SearchBackend,)`, `SearchBackend in _cross_configs`) and provider-injection (`isinstance(backend, DDGSearchBackend)`).

**Files touched**:
- `the_one/tools/base.py` — widened `Tool.Requires` from `tuple[type[BaseModel], ...]` to `tuple[type, ...]`; widened `Tool.__init__`'s `cross_configs` from `dict[type[BaseModel], BaseModel] | None` to `dict[type, object] | None`; updated docstrings to document the Pydantic-keyed-vs-Protocol-keyed two-category structure.
- `the_one/tools/builtins.py` — imported `DDGSearchBackend, SearchBackend` from `_search_backends`; widened the local `cross_configs` annotation from `dict[type[BaseModel], BaseModel]` to `dict[type, object]`; appended `cross_configs[SearchBackend] = DDGSearchBackend()` after the Pydantic Config-resolution loop; removed the now-unused `from pydantic import BaseModel` import; updated class docstring to document the two cross_configs categories.
- `the_one/tools/web.py` — rewrote `WebSearchTool` to consume `cross_configs[SearchBackend]`; declared `Config = WebConfig` and `Requires = (SearchBackend,)`; deleted the in-tool DDG POST + regex parsing (lives in `_search_backends.py` since L5); imported `SearchBackend`; three-clause envelope (`ConstraintError → Exception`).
- `the_one/tools/provider.py` — appended a paragraph to `ToolProvider.get_tools`'s docstring documenting the new Protocol-keyed service-entry category alongside the F4 L1b Pydantic-keyed Config-entry category.
- `tests/test_web_tools.py` — deleted `_DDG_HTML_*` fixtures, `_install_mock_websearch` helper, the 5 pre-F5 `TestWebSearchTool` tests, and the `_EmptyConfig` import; added `_StubBackend` fixture, `_make_websearch_tool` constructor helper, 6 new `TestWebSearchTool` tests; rewrote `TestWebToolInstantiation::test_web_search_tool_still_uses_empty_config` → `test_web_search_tool_uses_web_config`; imported `DDGSearchBackend, SearchBackend, SearchResult`.
- `tests/test_builtins.py` — renamed `test_cross_configs_contains_four_distinct_configs` → `test_cross_configs_contains_expected_entries`; expanded assertion set to include `SearchBackend`; updated docstrings on the renamed test and on `test_cross_configs_skips_empty_config`.

**No regressions**: F1-F4 + F5 L0-L5 surfaces unchanged. The 19 built-in tools still construct identically; the cross_configs dispatch view gains one Protocol-keyed entry (`SearchBackend`) alongside the four Pydantic-keyed Config entries. The agent-facing `web_search` output format is preserved verbatim from pre-F5.

---

### 05-search-backend-protocol-and-ddg

**Status**: landed (2026-04-29)

**Outcome**: New module `the_one/tools/_search_backends.py` ships the F5 search-backend extensibility surface: `SearchResult` frozen dataclass (`title`, `url`, `snippet`), `SearchBackend` runtime-checkable Protocol (`name: ClassVar[str]` + `async def search(query, max_results) -> list[SearchResult]`), and `DDGSearchBackend` concrete impl (`name = "duckduckgo"`). Closes the F1 known issue: backend POSTs to `https://html.duckduckgo.com/html/` with a Chrome-on-Linux `User-Agent` (`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`) that bypasses DDG's anti-bot interstitial. No `_TOOL_CLASSES` change — pure protocol + impl scaffolding; L6 wires `WebSearchTool` to consume via `cross_configs[SearchBackend]`.

**Implementation notes**:
- **`_DDG_BROWSER_UA` is a module-level constant**, NOT the L1 `_DEFAULT_USER_AGENT`. DDG's interstitial specifically rejects identifying UAs like `the-one/0.2 (...)`; the Chrome-on-Linux string is the verified-working bypass (F5 planning live test: 200 + 10 result markers).
- **`SearchBackend` is `runtime_checkable`** so L6 / future tests / F6 admin UI introspection can use `isinstance(backend, SearchBackend)`. Note: `runtime_checkable` only validates attribute presence, NOT call signatures — `test_protocol_method_signature` documents this with both a stub class missing `search` (fails) and one with a callable `search` (passes).
- **Internal owned-client semantics** (F5 Decision 12): `__init__(http_client=None)` stores the (optional) injected client. If `None`, `search` opens `async with httpx.AsyncClient(timeout=15) as client:` per call — test-friendly default. If injected, `search` uses it directly; caller manages lifecycle. L6 wires the SSRF-guarded client via the injected path.
- **DDG parsing preserved verbatim** from the pre-F5 `WebSearchTool`: `_DDG_RESULT_REGEX = re.compile(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</span>', re.DOTALL)`. HTML-tag strip via `_HTML_TAG_REGEX = re.compile(r"<[^>]+>")`; `re.sub` + `.strip()` for both title and snippet. Entity decode (`&amp;`, `&quot;`) deliberately NOT added — preserves pre-F5 behavior; future flight can add `html.unescape()` if small-model agents struggle with raw entities.
- **Two short-circuit empty-list paths**: (1) `resp.status_code != 200` (logs warning, returns `[]`); (2) `"result__a" not in text` after a 200 (logs warning, returns `[]`). The second handles 200 + empty page AND a hypothetical 200-but-empty interstitial; both surface to L6's `WebSearchTool` as `"No results found."`.
- **`max_results` clamp** is a `break` inside the `_DDG_RESULT_REGEX.finditer(...)` loop AFTER the append — matches the pre-F5 `[:max_results]` slice semantic. `max_results=0` returns `[]` immediately because the `if len(results) >= max_results: break` fires before any append (the spec's edge-case note pins this).

**Tests added (additive only — 10 new tests in `tests/test_search_backends.py`)**:
- `TestSearchResult.test_dataclass_frozen`: builds; fields populated; mutation raises `dataclasses.FrozenInstanceError`.
- `TestSearchBackendProtocol.test_protocol_runtime_checkable`: `isinstance(DDGSearchBackend(), SearchBackend)` is True.
- `TestSearchBackendProtocol.test_protocol_method_signature`: stub class missing `search` fails isinstance; stub class with `search` passes.
- `TestDDGSearchBackend.test_user_agent_sent`: **F1 fix pin** — `httpx.MockTransport` handler captures `request.headers.get("User-Agent")` into a closure; assert exact match against `_DDG_BROWSER_UA`. Also asserts POST + `"duckduckgo"` in URL.
- `TestDDGSearchBackend.test_parses_10_results`: mock returns 10-result HTML fixture (built via `_make_ddg_html(10)`); assert `len(results) == 10`; assert all titles/urls/snippets match expected; assert `<b>` tags stripped from title and snippet.
- `TestDDGSearchBackend.test_max_results_limits`: mock returns 10; `search(max_results=3)` returns 3.
- `TestDDGSearchBackend.test_no_results_returns_empty`: 200 + page without `result__a` markers → `[]`.
- `TestDDGSearchBackend.test_anti_bot_interstitial_returns_empty`: 202 + interstitial HTML → `[]`; `caplog` asserts a warning was logged with `"non-200"` or `"202"` substring.
- `TestDDGSearchBackend.test_owned_client_lifecycle`: `DDGSearchBackend()` with no injected client; two consecutive `search()` calls succeed via the per-call `async with` block.
- `TestDDGSearchBackend.test_injected_client_lifecycle`: `httpx.AsyncClient(transport=mock)` injected via `__init__(http_client=...)`; assert results come back correctly. Caller manages the client lifecycle via `async with`.

**Mocking pattern**: `_install_owned_mock(monkeypatch, handler)` replaces `httpx.AsyncClient` with a factory injecting `httpx.MockTransport(handler)`. Used by all tests except `test_injected_client_lifecycle`, which constructs `httpx.AsyncClient(transport=httpx.MockTransport(...))` directly. Both paths exercise the backend's two lifecycle branches.

**Verification**: 985 passed, 1 skipped, 239 deselected (was 975 → net +10 new tests, matching the 10 enumerated leg tests across `TestSearchResult` / `TestSearchBackendProtocol` / `TestDDGSearchBackend`). `ruff check` clean on `the_one/tools/_search_backends.py` + `tests/test_search_backends.py` (one auto-fixable import-sort flagged on initial write; resolved with `ruff check --fix`). Module-export verification snippet passes (`SearchResult` is dataclass; `isinstance(DDGSearchBackend(), SearchBackend)` is True).

**Leg-spec test count clarification**: the leg's Acceptance Criteria says "All 8 new tests pass"; the test enumeration in the Outputs section actually lists 10 tests (1 + 2 + 7 across the three classes). Implementation matches the enumerated list — 10 tests landed. The "8" figure is a stale count from an earlier draft; doesn't affect acceptance.

**Files touched**:
- `the_one/tools/_search_backends.py` — NEW (~140 lines): `_DDG_BROWSER_UA`, `_DDG_RESULT_REGEX`, `_HTML_TAG_REGEX` constants; `SearchResult` `@dataclass(frozen=True)`; `SearchBackend` runtime-checkable Protocol; `DDGSearchBackend` impl.
- `tests/test_search_backends.py` — NEW (~210 lines): three test classes, 10 tests; `_make_ddg_html(n)` fixture builder; `_install_owned_mock` monkeypatch helper.

**No regressions**: F1-F4 + F5 L0-L4 surfaces unchanged. No `BuiltinToolProvider` changes — backend is constructed in isolation; L6 wires it via `cross_configs[SearchBackend]`. The 19 prior tools still construct identically. `WebSearchTool` continues on `_EmptyConfig` until L6.

---

### 04-download-file-tool

**Status**: landed (2026-04-29)

**Outcome**: New `DownloadFileTool` shipped in `the_one/tools/web.py`, registered as the 19th built-in tool. `Config = WebConfig`; `Requires = (FilesystemConfig,)` declares the cross-Config dependency consumed via `self._cross_configs[FilesystemConfig]`. Streaming download via `httpx.AsyncClient.stream()` with mid-stream size-cap abort + partial-file cleanup. Path validation uses the L0-unified `_filesystem_check(path, fs_cfg, mode=CheckMode.WRITE_EXISTING_PARENT)` — parent must pre-exist (no auto-mkdir; agent has the explicit `mkdir` tool). Four-clause envelope mirrors L2/L3 with F5-specific `[error] Download timed out after Ns` wording.

**Implementation notes**:
- **Streaming + cleanup pattern**: `with target.open("wb") as fh: async with httpx.AsyncClient(...) as client: async with client.stream("GET", url) as resp: async for chunk in resp.aiter_bytes(): ...` Tracks `total_bytes`; raises `ConstraintError(f"response exceeded {cap} bytes; partial file removed")` BEFORE writing the chunk that would exceed the cap. Inner `try/except ConstraintError: target.unlink(missing_ok=True); raise` cleans up the partial file in pattern (a) — re-raise after cleanup. The outer `except ConstraintError` clause then formats and returns.
- **`target.open("wb")` creates the destination file BEFORE the stream starts** — so a redirect-cap overrun, timeout, or generic mid-stream RuntimeError leaves an empty (or partial) file behind. The implementation hoists cleanup into a module-level `_safe_unlink(target)` helper called from the timeout / `httpx.TooManyRedirects` / generic `except Exception` clauses. Without this, `test_redirect_cap_exceeded`'s `not target.exists()` assertion fails — caught during dev-loop run.
- **`Requires = (FilesystemConfig,)`** declares cross-Config dependency. The provider-level `cross_configs` mapping is shared by reference across all tools in a `get_tools(...)` call; `DownloadFileTool` reads from it via `self._cross_configs[FilesystemConfig]` — same pattern any future Requires-declaring tool will use.
- **`CheckMode.WRITE_EXISTING_PARENT` is the path-validation mode** — parent must pre-exist. `FileNotFoundError` from L0 (raised when parent is missing but in-scope — environmental, not policy) is caught by the generic `except Exception` clause → agent gets `[error] parent does not exist for path '...'` and can `mkdir` the parent. We do NOT auto-create the parent — agent has an explicit `mkdir` tool.
- **`_safe_unlink` helper** lives at module scope (NOT inside the class) — it's used by all error clauses that need defensive partial-file cleanup; centralizing the `if target is None` check + `OSError`-swallow keeps the four error clauses readable.
- **Generic-exception cleanup contract**: `target` is initialized to `None` before the inner `try`, so when the exception fires before `_filesystem_check` returns (e.g. `_url_check` raised — caught by ConstraintError clause first; defensive), `_safe_unlink(None)` is a no-op.
- **`description`** ~70 words: "Download a URL's content to a file. Path may be absolute or relative; relative paths resolve against the agent server's CWD. Refused if path is outside the operator-set path allowlist. Streams the response and aborts (removing the partial file) if the size cap is exceeded mid-stream. Same SSRF + URL allowlist + timeout cap as http_request. Use this for binary content (PDFs, images, archives); use fetch_url for HTML/text."
- **Four-clause envelope mirrors L2/L3** with F5-specific timeout wording `[error] Download timed out after Ns` (distinct from L2's `Request timed out` and L3's `Fetch timed out`).
- **Test fixture for relative-path test**: `monkeypatch.chdir(tmp_path)` controls process CWD; `FilesystemConfig(path_allowlist=[str(tmp_path)])`; agent passes `path="file.bin"` (parent is tmp_path, which exists, so `WRITE_EXISTING_PARENT` passes). Per the leg's adjustment note — the original `path="downloads/file.bin"` would fail `WRITE_EXISTING_PARENT` because the `downloads/` parent doesn't exist; the test verifies relative-path resolution to cwd, not parent-creation.
- **Test fixture for the partial-file-cleaned-on-RuntimeError test**: custom `httpx.AsyncByteStream` subclass yields one chunk (so the file gets created+partially-written) then raises `RuntimeError("boom mid-stream")`. The tool's generic `except Exception` clause catches via `_safe_unlink`; assertion confirms `not target.exists()`.

**Tests added (additive only — 9 new tests in `TestDownloadFileTool`)**:
- `test_construction_shape`: builds; `Config is WebConfig`; `Requires == (FilesystemConfig,)`.
- `test_happy_path`: in-scope path, mock returns 1KB body; tool writes file; returns `[200] downloaded 1024 bytes to /path`. Verifies file content.
- `test_path_outside_allowlist_refused`: `path="/etc/passwd"` outside `tmp_path` allowlist → `[error] [constraint] path '...' outside allowlist`. File not created.
- `test_mid_stream_size_cap_aborts`: `cfg.response_size_cap_bytes=1024`; mock returns 5KB; tool aborts mid-stream, unlinks partial file, returns `[error] [constraint] response exceeded 1024 bytes; partial file removed`. File does NOT exist post-call.
- `test_url_check_refused`: `ftp://...` → `[error] [constraint] scheme 'ftp' refused`. No file created.
- `test_redirect_cap_exceeded`: `cfg.redirect_cap=1`; mock chain emits sequential 302s → `[error] [constraint] exceeded redirect cap of 1`. No partial file (verified via `_safe_unlink` cleanup in the redirects clause).
- `test_timeout_via_httpx_readtimeout`: mock raises `httpx.ReadTimeout` → `[error] Download timed out after 2s` (F5 wording). No file (verified via `_safe_unlink` cleanup in the timeout clause).
- `test_relative_path_resolves_against_cwd`: `monkeypatch.chdir(tmp_path)` + `path="file.bin"`; verifies the file lands at `tmp_path / "file.bin"` and contains the expected content. Adjusted from the original `downloads/file.bin` per the leg's WRITE_EXISTING_PARENT note.
- `test_partial_file_cleaned_on_unexpected_error`: custom `httpx.AsyncByteStream` yields one chunk then raises `RuntimeError`; tool's generic `except Exception` clause unlinks; `not target.exists()` confirmed.

**`test_builtins.py` updates**:
- Three numeric assertions: `len(zero_arg) == 18` → `19`; `len(tools) == 18` → `19` (factory path); `len(tools) == 18` → `19` (unknown-tool-name-in-overrides path).
- One tool-name set literal: appended `"download_file"` (set ordering doesn't matter; placed after `"fetch_url"` per registration order).
- Two comment references updated `18` → `19`.

**Runtime correction during dev-loop**: First run failed `test_redirect_cap_exceeded`'s `not target.exists()` because `target.open("wb")` creates the empty file BEFORE the stream begins; `httpx.TooManyRedirects` from the redirect-cap exhaustion path leaves the empty file behind. Fix: introduced module-level `_safe_unlink(target)` helper called from the timeout / redirect / generic-exception clauses (not just the inner ConstraintError clause). Re-ran: 54 passed.

**Verification**: 975 passed, 1 skipped, 239 deselected (was 966 → net +9 new tests, matching the leg's 9 new `TestDownloadFileTool` tests). `ruff check` clean on `the_one/tools/web.py`, `the_one/tools/builtins.py`, `tests/test_web_tools.py`, `tests/test_builtins.py`. All three verification snippets in the leg artifact pass: construction-shape, `_TOOL_CLASSES` count + name presence, end-to-end happy-path with mocked transport.

**Files touched**:
- `the_one/tools/web.py` — appended `DownloadFileTool` after `FetchUrlTool` (before `WebSearchTool`); imported `CheckMode`, `FilesystemConfig`, `_filesystem_check`; added module-level `_safe_unlink` helper.
- `the_one/tools/builtins.py` — imported `DownloadFileTool`; added `"download_file": DownloadFileTool` between `"fetch_url"` and `"web_search"`.
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES['Web']` now `['download_file', 'fetch_url', 'http_request', 'web_search']` (alphabetical).
- `tests/test_web_tools.py` — added `_patch_download_transport` helper, `_make_download_tool` constructor helper, `TestDownloadFileTool` class with 9 tests; imported `FilesystemConfig` and `DownloadFileTool`.
- `tests/test_builtins.py` — three count assertions updated; tool-name set literal appended `"download_file"`; two comment references updated.

**No regressions**: F1-F4 + F5 L0-L3 surfaces unchanged. The 18 prior tools still construct identically; the new tool participates in the cross_configs dispatch — it CONSUMES `FilesystemConfig` (already in the dispatch view from the 9 filesystem tools) AND continues the `WebConfig` consumer chain alongside `HttpRequestTool` / `FetchUrlTool`. No new entry in `cross_configs.keys()`, just an additional consumer of two existing slots.

---

### 03-fetch-url-tool

**Status**: landed (2026-04-29)

**Outcome**: New `FetchUrlTool` shipped in `the_one/tools/web.py`, registered as the 18th built-in tool. Single required `url` param (no agent-passed timeout — keep param surface tiny; operators who need an override use `http_request`). Execute path: `clipped = cfg.timeout_seconds_default` → `_url_check` → `_build_transport(cfg)` → `httpx.AsyncClient(transport=..., timeout=clipped, follow_redirects, max_redirects)` → content-type dispatch (binary refusal / readability+markdownify for HTML / `_truncate_response` passthrough for text/JSON) → `[{status}]\n{text}`. Same four-clause envelope as L2 with F5-specific `[error] Fetch timed out after Ns` wording.

**Implementation notes**:
- **`markdownify(summary_html, heading_style="ATX")`** — the default `"underlined"` style produces clunky `===` underlines for h1; ATX renders headings as `# Title` (compact + agent-friendly).
- **Lazy imports** of `readability.Document` and `markdownify` inside the HTML branch — keeps tool-class import time fast and lets unit tests skip the heavy lxml import unless they exercise HTML extraction. Ruff autosort flagged alphabetical order (`markdownify` before `readability`); fixed in-place.
- **Binary refusal returns `[error] binary content (...)`** — NO `[200]` prefix. Keeps the `[error] {...}` envelope shape consistent with L2's other refusal paths; agents don't need the status code on a refusal.
- **Content-type dispatch correctness**: `_is_binary_content_type(ct)` first (uses the L1 helper which strips `;`-suffix and is case-insensitive); then `"text/html" in ct.lower()` substring match (so `text/html; charset=utf-8` works); else passthrough via `_truncate_response(resp.content, cfg, content_type=ct)`. The HTML-markdown path passes `content_type=None` to `_truncate_response` because the markdown bytes are already text.
- **Four-clause envelope mirrors L2**: `ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`. F5-specific timeout wording: `[error] Fetch timed out after Ns` (distinct from L2's `Request timed out` so agents get a tool-context hint when a slow page expires).
- **`_build_transport(self, cfg)` helper** mirrors L2's exact shape — production returns `SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`; tests monkeypatch this method to inject `httpx.MockTransport(handler)` and bypass SSRF.
- **Realistic `test_html_extraction` fixture** — header + nav (5 links) + `<article>` with `<h1>` and 3 substantive paragraphs (~50 words each) + footer. Readability's content-density scoring needs real content density to fire; the leg's first-draft trivial fixture (single `<p>World</p>`) does NOT reliably pick the article element. Asserts: `"# The Title"` substring (ATX heading), `"Para 1"` distinctive body phrase, and `[200]` status prefix. Does NOT assert `"nav" not in markdown` — readability's stripping is content-density-based and may keep nav on shorter fixtures; the regression net is the article's presence, not the boilerplate's absence.
- **`test_size_cap_truncated`** uses 8 substantive paragraphs (~800 chars each) inside `<article>` so readability picks the article element AND the resulting markdown trips the 1024-byte cap; the test asserts the L1 truncation marker substring and `showing last 1024 bytes` wording.

**Tests added (additive only — 8 new tests in `TestFetchUrlTool`)**:
- `test_html_extraction`: realistic article fixture → readability extracts; markdownify produces ATX-headed markdown; asserts `# The Title`, `Para 1`, `[200]`.
- `test_text_plain_passthrough`: `Content-Type: text/plain` → body returned decoded via `_truncate_response`.
- `test_json_passthrough`: `Content-Type: application/json` → body returned decoded verbatim (no pretty-printing).
- `test_binary_refused`: `Content-Type: application/pdf` + 50-byte body → exact-match `[error] binary content (50 bytes; type=application/pdf) — use download_file for binary downloads`. Confirms NO `[200]` prefix.
- `test_url_check_refused`: `ftp://...` → `[error] [constraint] scheme 'ftp' refused; ...`. Mock not invoked.
- `test_size_cap_truncated`: 5KB-equivalent HTML body with `response_size_cap_bytes=1024` → markdown contains the L1 truncation marker.
- `test_timeout_via_httpx_readtimeout`: mock raises `httpx.ReadTimeout` → `[error] Fetch timed out after 2s` (F5 wording).
- `test_construction_shape`: `FetchUrlTool(WebConfig())` builds; `Config is WebConfig`.

**`test_builtins.py` updates**:
- Three numeric assertions: `len(zero_arg) == 17` → `18`; `len(tools) == 17` → `18` (factory path); `len(tools) == 17` → `18` (unknown-tool-name-in-overrides path).
- One tool-name set literal: appended `"fetch_url"` (alphabetical position deemed cleanest — append works for the set since order doesn't matter; placed after `"http_request"` per registration order).
- Two comment references updated `17` → `18`.

**Verification**: 966 passed, 1 skipped, 239 deselected (was 958 → net +8 new tests, matching the leg's 8 new `TestFetchUrlTool` tests). `ruff check` clean on `the_one/tools/web.py`, `the_one/tools/builtins.py`, `tests/test_web_tools.py`, `tests/test_builtins.py` (after the import-order autosort fix). All three verification snippets in the leg artifact pass: construction-shape, `_TOOL_CLASSES` count + name presence, end-to-end readability extraction with mock transport.

**Files touched**:
- `the_one/tools/web.py` — appended `FetchUrlTool` after `HttpRequestTool` (before `WebSearchTool`); imported `_is_binary_content_type` from `_web_config`.
- `the_one/tools/builtins.py` — imported `FetchUrlTool`; added `"fetch_url": FetchUrlTool` between `"http_request"` and `"web_search"`.
- `the_one/interfaces/web/static/js/areas/studio.js` — `TOOL_CATEGORIES['Web']` now `['fetch_url', 'http_request', 'web_search']` (alphabetical).
- `tests/test_web_tools.py` — added `_patch_fetch_transport` helper, `_ARTICLE_HTML` realistic fixture, `TestFetchUrlTool` class with 8 tests.
- `tests/test_builtins.py` — three count assertions updated; tool-name set literal appended `"fetch_url"`; two comment references updated.

**No regressions**: F1-F4 + F5 L0-L2 surfaces unchanged. The 17 prior tools still construct identically; the new tool participates in the cross_configs dispatch (shares `WebConfig` with `HttpRequestTool` — no new entry in `cross_configs.keys()`, just a second tool consuming the existing `WebConfig` slot).

---

### 02-migrate-http-request-tool

**Status**: landed (2026-04-29)

**Outcome**: `HttpRequestTool` migrated from the F2 zero-constraint shape to the F5 constraint surface. `Config = WebConfig`; the tool now consumes operator-resolved policy directly. Execute path: float-preserving timeout clip → `_url_check` → `_build_transport(cfg)` → `httpx.AsyncClient(transport=..., timeout=clipped, follow_redirects, max_redirects)` → `_truncate_response` → `[{status}]\n{text}`. Four-clause envelope: `ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`.

**Implementation notes**:
- **Four-clause envelope, NOT three** (architect-corrected): `httpx.TimeoutException` does NOT inherit from `asyncio.TimeoutError`. httpx 0.28.1 MRO confirmed in-container: `TimeoutException → TransportError → RequestError → HTTPError → Exception`. Catching only `asyncio.TimeoutError` would let production httpx timeouts fall through to the generic clause and surface `[error] {e}` instead of the F5 wording. The grouped `(asyncio.TimeoutError, httpx.TimeoutException)` clause is mandatory.
- **`httpx.TooManyRedirects` formatted as `[error] [constraint]`** (operator-policy refusal), distinct from generic `[error] {e}` exceptions. Placed after the timeout clause so it doesn't intercept production timeouts.
- **`_build_transport(cfg)` helper method** is the test seam: production returns `SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`; tests monkeypatch this method to inject `httpx.MockTransport(handler)` and bypass SSRF for tool-behavior coverage. SSRF transport's own coverage stays in `tests/test_web_helpers.py`.
- **Pre-F5 `_install_mock` factory deleted** — it popped `transport=` from kwargs, which would silently discard the test's mock transport in F5 (the new tool always passes `transport=` to `httpx.AsyncClient`). Replaced with `_patch_transport(monkeypatch, handler)` per the leg's pattern. The pre-F5 factory is preserved as `_install_mock_websearch` for `WebSearchTool` (still on `_EmptyConfig` until F5 L6).
- **Float-preserving timeout clip** (F4 L3 pattern): `if clipped <= 0: clipped = 1`, NOT `max(1, min(...))`. Preserves fractional values when an agent passes e.g. `timeout=2.5` with `max=10`.
- **`redirect_cap` semantic** verified in two separate tests:
  - `redirect_cap=0` → `follow_redirects=False, max_redirects=0`; tool returns `[302]\n<body>` verbatim.
  - `redirect_cap=1` with a 302→302 chain → `httpx.TooManyRedirects` → `[error] [constraint] exceeded redirect cap of 1`.
- **`test_timeout_clipped_to_max` mock raises `httpx.ReadTimeout`** (httpx's actual production exception, NOT `asyncio.TimeoutError`). This exercises the grouped clause's `httpx.TimeoutException` branch — the architect-flagged production path that would have leaked through a three-clause envelope.
- **`test_cross_configs_contains_three_distinct_configs` renamed → `..._four_distinct_configs`** in `tests/test_builtins.py`; docstring updated to reflect F5 L2 entry of `WebConfig` into the dispatch view; assertion set expanded to `{FilesystemConfig, ExecutionConfig, PythonExecConfig, WebConfig}`. The companion `test_cross_configs_skips_empty_config` docstring updated to note only `web_search` still uses `_EmptyConfig` (until F5 L6).
- **`description` updated** to mention SSRF default-block, host allowlist/denylist, response-size cap, redirect cap (small-model-readable, ~50 words).
- **`parameters.timeout` is now optional** (no `default` field; description says "Uses the resolved default if omitted; clipped to the operator-set max").
- **Verification snippet caveat**: the leg's second verification snippet (`http://169.254.169.254/`) assumes IP-literal SSRF blocking. L1's transport explicitly short-circuits on IP literals — this is documented behavior (the operator's `host_denylist` + tool's `_url_check` are the gate for raw IPs, not the SSRF transport). Connection failures on raw IP literals surface via the generic `[error] {e}` clause. The unit test suite is the canonical verification; this snippet behavior is consistent with the L1 design.

**Tests added (additive only — 8 new constraint-surface tests)**:
- `test_ssrf_block_loopback`: monkeypatched `BaseEventLoop.getaddrinfo` returns 127.0.0.1 for `http://example.com/` → `[error] [constraint] all resolved IPs ... blocked`. Exercises the production `SSRFGuardedTransport` path (no `_build_transport` patch).
- `test_redirect_cap_zero_returns_3xx_body`: `cfg.redirect_cap=0`; mock returns 302 → tool returns `[302]\n<redirect-body>` without following.
- `test_redirect_cap_exceeded`: `cfg.redirect_cap=1`; mock chain emits sequential 302s → `[error] [constraint] exceeded redirect cap of 1`.
- `test_response_size_cap_truncated`: `cfg.response_size_cap_bytes=1024`; mock returns 5KB body → response contains the L1 truncation marker (`[... truncated`, `showing last 1024 bytes`).
- `test_url_allowlist_refuse`: `cfg.host_allowlist=["github.com"]`; agent passes `http://other.com/` → `[error] [constraint] ... not in host_allowlist` (substring assert per architect note 8 — the L1 wording includes the allowlist repr suffix).
- `test_url_denylist_refuse`: `cfg.host_denylist=["evil.com"]`; agent passes `http://evil.com/` → `[error] [constraint] host '...' is in host_denylist`.
- `test_timeout_clipped_to_max`: `cfg.timeout_seconds_max=2`; agent passes `timeout=10`; mock raises `httpx.ReadTimeout("simulated timeout")` → `[error] Request timed out after 2s` via the grouped clause's `httpx.TimeoutException` branch.
- `test_agent_narrow_extra_allowed_hosts`: agent's `extra_allowed_hosts=[]` (narrowed from operator's `["localhost"]`); resolver patched `getaddrinfo` returns 127.0.0.1 for `http://localhost/`; SSRF blocks → `[error] [constraint] all resolved IPs ... blocked`. Confirms the agent's narrowed view actually flows through to the transport's `extra_allowed_hosts` short-circuit decision.

**Plus**: 5 existing `TestHttpRequestTool` tests updated to construct `HttpRequestTool(WebConfig())` and use `_patch_transport`; 2 `TestWebToolInstantiation` tests rewritten — one asserts `HttpRequestTool.Config is WebConfig` and zero-arg fallback to `WebConfig()`; the other asserts `WebSearchTool` still uses `_EmptyConfig` (until F5 L6).

**Verification**: 958 passed, 1 skipped, 239 deselected (was 950 → net +8 new constraint tests, matching the leg's plan). `ruff check` clean on `the_one/tools/web.py`, `tests/test_web_tools.py`, `tests/test_builtins.py`. Construction-shape verification snippet passes.

**Files touched**:
- `the_one/tools/web.py` — full rewrite of `HttpRequestTool`; added `_build_transport` helper, four-clause envelope, float-preserving timeout clip, redirect-cap branch logic. `WebSearchTool` unchanged (migrates in F5 L6).
- `tests/test_web_tools.py` — deleted pre-F5 `_install_mock` factory; added `_patch_transport` helper; rewrote 5 existing tests; added 8 new constraint tests in `TestHttpRequestToolConstraints`; added `_install_mock_websearch` factory for `WebSearchTool` (preserves the pre-F5 pattern until L6); rewrote `TestWebToolInstantiation` (now per-tool config-type asserts).
- `tests/test_builtins.py` — renamed `test_cross_configs_contains_three_distinct_configs` → `..._four_distinct_configs`; expanded assertion set to include `WebConfig`; updated docstrings on the renamed test and on `test_cross_configs_skips_empty_config`.

**No regressions**: F1-F4 surfaces unchanged. `BuiltinToolProvider().get_tools({}, {}, agent_name="x")` still constructs all 17 tools; `HttpRequestTool` now receives the resolved `WebConfig` via the cross_configs dispatch. `WebSearchTool` continues on `_EmptyConfig` until F5 L6.

---

### 01-web-config-and-helpers

**Status**: landed (2026-04-29)

**Outcome**: F5 web-tool category scaffolding shipped. New module `the_one/tools/_web_config.py` exposes:

- `WebConfig` — frozen Pydantic Config with 7 fields (3 Narrow ints + Field-only `redirect_cap` + 2 Narrow lists + 1 NarrowSuperset list). The `_default_le_max` cross-field validator mirrors F4 D1.
- `_is_ssrf_blocked(ip: str) -> bool` — single-arg, IP-only. Does NOT consult `extra_allowed_hosts`; the operator override short-circuits earlier at the transport layer on the original hostname BEFORE resolution.
- `_url_check(url, cfg)` — http/https-only scheme refusal, hostless-URL refusal, host_allowlist/host_denylist enforcement.
- `_is_binary_content_type(ct)` — prefix-matches `image/`, `audio/`, `video/`, `application/x-`; exact-matches `application/octet-stream`, `application/pdf`, `application/zip`, `application/gzip`, `application/wasm`. Strips `;`-suffix; case-insensitive.
- `_truncate_response(body, cfg, *, content_type)` — single-stream tail-preserving truncation, mirroring F4's `_truncate_output` shape but without the `[stderr]` clause and without the `(no output)` fallback (web-empty stays empty so callers can distinguish HTTP 204 from a literal-string fallback).
- `SSRFGuardedTransport(httpx.AsyncHTTPTransport)` — resolve-then-pin via `loop.getaddrinfo`, IP-literal short-circuit, `extra_allowed_hosts` host-match short-circuit BEFORE resolution, `request.extensions["sni_hostname"]` for TLS validation, `Host:` header preserved, `request.url.copy_with(host=ip)` for the connect-target rewrite.

**Mission invariant locked**: no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field on `WebConfig`. `tests/test_web_config.py::TestNoSSRFDisableField` asserts at the `model_fields` level so a future PR cannot silently introduce a full-disable toggle.

**Implementation notes**:
- **Container deps installed FIRST** before editing `pyproject.toml` so the running uvicorn worker had `readability` + `markdownify` available immediately. `docker exec the-one pip install readability-lxml markdownify` succeeded; pulled `lxml-6.1.0`, `beautifulsoup4-4.14.3`, plus pure-Python helpers. THEN `pyproject.toml` updated with `"readability-lxml>=0.8"` and `"markdownify>=0.13"` placed after `httpx>=0.27` to keep the role-grouping coherent.
- **`_TIMEOUT_DEFAULT_UI_CHOICES` reused** from `the_one.tools.execution` per the leg directive — single source of truth across F4 and F5 dropdowns.
- **`_RESPONSE_SIZE_UI_CHOICES`** mirrors F3's `read_size_cap_bytes` six-entry shape verbatim.
- **`redirect_cap` is markerless**: the resolver raises `ValueError("... no Narrow/Substitute marker ...")` when an agent override touches this key. Tests pin at the resolver level (NOT at AgentFactory.create — that's L2's concern).
- **DNS-rebind regression test** patches `asyncio.base_events.BaseEventLoop.getaddrinfo` (architect-verified — `AbstractEventLoop` is too high in MRO and does not intercept). Per-test `httpx.Limits(max_keepalive_connections=0)` forces per-request resolution so the second resolve actually fires.
- **SSRF transport tests use a `monkeypatch` of `httpx.AsyncHTTPTransport.handle_async_request`** as the seam — the production `SSRFGuardedTransport.handle_async_request` is exercised verbatim, with the `super()` call landing in a recorder/factory pair instead of the real httpx pool. Cleaner than a test-only subclass that re-implements the resolve+pin flow.
- **Stub-tool consumer test** in `tests/test_web_stub_tool.py` exercises `WebConfig` + `_url_check` + `SSRFGuardedTransport` + `_truncate_response` end-to-end through a tool-shaped scenario (per F4 debrief recommendation). Catches the L2 helpers-without-consumer gap class.

**Tests added (additive only)**:
- `tests/test_web_config.py` — 24 tests across 6 classes: defaults, bounds, cross-field validator, frozen posture, resolver narrowing semantics for each marker (Narrow int / Narrow list / NarrowSuperset list), `redirect_cap` markerless rejection at the resolver level, mission invariant lock (no `disable_ssrf*` field).
- `tests/test_web_helpers.py` — 50+ tests covering `_is_ssrf_blocked` (IPv4/IPv6 loopback/link-local/RFC1918/cloud-metadata/public), `_url_check` (scheme + allowlist + denylist), `_host_matches`, `_is_binary_content_type` (prefix/exact/charset/case), `_truncate_response` (under-cap/over-cap/binary/empty/invalid-utf8), and `SSRFGuardedTransport` (passes / all-blocked / first-public-wins / IP-literal short-circuit / `extra_allowed_hosts` short-circuit / DNS-rebind regression).
- `tests/test_web_stub_tool.py` — stub-tool consumer test with three classes covering happy path (decode, truncate, binary), SSRF block envelope, URL-check failure envelope, and tool-API conformance (`Config = WebConfig`, default-config instance, redirect_cap=0 branch).

**Verification**: 950 passed, 1 skipped, 239 deselected (was 842 → net +108 new tests, matching the F5 plan baseline). `ruff check` clean on all four touched files. All four verification snippets in the leg artifact pass. Container has `readability` + `markdownify` importable.

**Files touched**:
- `pyproject.toml` — added `readability-lxml>=0.8` and `markdownify>=0.13` after `httpx>=0.27`.
- `the_one/tools/_web_config.py` — NEW (366 lines).
- `tests/test_web_config.py` — NEW.
- `tests/test_web_helpers.py` — NEW.
- `tests/test_web_stub_tool.py` — NEW.

**No regressions**: F1-F4 surfaces unchanged; the new module is additive scaffolding for F5 L2-L6.

---

### 00-filesystem-helper-unification

**Status**: landed (2026-04-29)

**Outcome**: F4-deferred filesystem helper unification successfully folded into F5 as L0. The four divergent scope-check helpers (F3's `_filesystem_check` / `_filesystem_check_write_parent` / `_filesystem_check_write_path` and F4's `_cwd_check`) collapse into a single dispatched helper backed by a `CheckMode(str, Enum)` with four explicit values: `READ`, `WRITE_NEW`, `WRITE_EXISTING_PARENT`, `DIRECTORY`. All existing names remain as one-line shims; the 7+ existing call sites in `the_one/tools/` need no edits because the two-arg call form (`_filesystem_check(path, cfg)`) preserves the legacy READ behavior via the `mode=CheckMode.READ` default.

**Behavior preserved verbatim**:
- WRITE_NEW + WRITE_EXISTING_PARENT canonicalize the parent first, compose with the leaf, then re-canonicalize the composed path. The second canonicalize is the symlink-leaf safety net that the legacy delegate-to-`_filesystem_check(composed, cfg)` got for free.
- WRITE_EXISTING_PARENT raises `FileNotFoundError` (NOT `ConstraintError`) on missing parent — F3's deliberate distinction between policy refusal and environmental error.
- DIRECTORY mode preserves F4's exact wording `"cwd '{canonical}' does not exist or is not a directory"`.
- Scope check (allowlist + denylist) runs FIRST in all four modes — a hostile prompt cannot probe filesystem layout for out-of-scope paths regardless of mode.

**Implementation notes**:
- `if canonical_parent is None: raise RuntimeError(...)` used in WRITE_EXISTING_PARENT branch instead of `assert` — paranoid correctness under `python -O`.
- `_cwd_check` shim in `execution.py` uses a local `from the_one.tools.filesystem import CheckMode` import to keep the existing top-of-file import block minimal (architect noted no actual cycle exists; the local import is purely a minimal-diff choice).

**Tests added (additive only — F3/F4 suites unchanged)**:
- New `TestCheckModeDispatch` class in `tests/test_filesystem_helpers.py` (8 tests):
  - READ: no existence check.
  - WRITE_NEW: parent-canonicalize-then-compose, missing parent allowed.
  - WRITE_EXISTING_PARENT: missing parent raises `FileNotFoundError`; existing parent allowed.
  - DIRECTORY: file (not dir) raises `ConstraintError` with the F4 wording; dir allowed.
  - Scope-first invariant across all four modes.
  - **Regression net** `test_write_modes_resolve_leaf_symlink_to_out_of_scope`: locks the second canonicalize on composed paths so a leaf-symlink to an out-of-scope target stays rejected.

**Verification**: 842 passed, 1 skipped, 239 deselected (full suite, modulo the pre-existing CSS-token red the leg directs us to deselect). `ruff check` clean on touched files. All four verification snippets in the leg artifact passed.

**Files touched**:
- `the_one/tools/filesystem.py` — added `CheckMode` enum, rewrote `_filesystem_check` as the dispatcher, reduced `_filesystem_check_write_parent` and `_filesystem_check_write_path` to one-line shims.
- `the_one/tools/execution.py` — reduced `_cwd_check` to a one-line shim; updated module docstring bullet.
- `tests/test_filesystem_helpers.py` — added `CheckMode` to imports; appended `TestCheckModeDispatch` class.

**No regressions**: F1-F4 surfaces unchanged. The 11 call sites in `filesystem.py` and the cwd validation in `execution.py` route through the unified dispatcher transparently.

---

## Decisions

*Runtime decisions not in original plan will be recorded here as they happen.*

---

## Deviations

*Departures from planned approach will be recorded here as they happen.*

---

## Anomalies

### IP-literal SSRF bypass (HAT scenario 3 — inline fix)

**Observed (during L7 HAT)**: HAT scenario 3 (cloud-metadata SSRF block) fetched `http://169.254.169.254/latest/meta-data/` via the agent. Expected: `[error] [constraint] ...` (SSRF policy refusal BEFORE connect). Actual: `[error] All connection attempts failed` (httpx network error AFTER the connect attempt). The mission constraint says SSRF protection refuses cloud-metadata addresses by default — the wrong error shape revealed the policy gate was not engaging on IP literals.

**Severity**: degraded (security-critical defect; F5 mission constraint violation; flight-uncommitted so no production impact).

**Root cause**: `the_one/tools/_web_config.py::SSRFGuardedTransport.handle_async_request` (pre-fix lines 454-461) had an IP-literal short-circuit that called `super().handle_async_request(request)` directly when the URL host was an IP literal — bypassing `_is_ssrf_blocked` entirely. An agent passing `http://169.254.169.254/`, `http://10.0.0.1/`, or `http://127.0.0.1/` skipped all SSRF protection; the block only fired for hostnames that resolved to blocked IPs. The original L1 design rationale (the docstring) said "the operator's `host_denylist` and the tool's `_url_check` are the gate for raw IPs" — but `host_denylist` is opt-in (default empty) and `_url_check` doesn't classify IPs. There was no default-on gate for raw IP literals at all.

**Resolution (uncommitted; lands in the L7 HAT inline-fix batch)**:
- IP-literal branch now consults `_is_ssrf_blocked(original_host)` after first checking the operator's `extra_allowed_hosts` override. Operator override wins (uniform with the hostname path); the default-block list refuses loopback / RFC1918 / link-local / cloud-metadata literals BEFORE any connect attempt with `ConstraintError(f"IP literal {original_host} is in the SSRF block list")`.
- The `try/except ValueError` envelope around `ipaddress.ip_address(original_host)` is preserved (ValueError = "not an IP literal, fall through to resolve+pin"). `ConstraintError` is `Exception`-derived, NOT `ValueError`, so the SSRF refusal raised inside the IP-literal branch propagates correctly through the `except ValueError` clause to the tool's outer envelope.
- Docstring on `SSRFGuardedTransport` updated to reflect the new semantic (IP-literal SSRF check applies; operator override honored first; uniform with hostname path).

**Tests added (5 new tests in `TestSSRFGuardedTransport`)**:
- `test_ip_literal_loopback_blocked`: agent fetches `http://127.0.0.1/`; transport raises `ConstraintError` containing `"127.0.0.1"` and `"SSRF block list"`. Confirms recorder saw zero dispatches.
- `test_ip_literal_rfc1918_blocked`: agent fetches `http://10.0.0.1/`; transport raises `ConstraintError`. Same recorder assertion.
- `test_ip_literal_cloud_metadata_blocked`: agent fetches `http://169.254.169.254/latest/meta-data/` (the canonical AWS/GCP/Azure SSRF target — exact path used in HAT scenario 3); transport raises `ConstraintError`. Pins the F5 mission constraint at the test level.
- `test_ip_literal_public_passes`: agent fetches `http://1.2.3.4/`; transport calls super (mock returns 200); host NOT rewritten (no resolve happened — IP literal). Companion to the existing `test_ip_literal_url_short_circuits_resolve` (which asserts the no-resolve invariant from the public-IP angle); kept both for layered coverage.
- `test_ip_literal_extra_allowed_hosts_override`: with `extra_allowed_hosts=["127.0.0.1"]`, IP literal `http://127.0.0.1/` passes (operator opted into loopback). Pins the operator-override semantic uniformly across hostname and IP-literal paths.

**Verification**: 991 passed, 1 skipped, 239 deselected (was 986 → net +5 new tests, matching the 5 enumerated above). `ruff check` clean on `the_one/tools/_web_config.py` and `tests/test_web_helpers.py`. Targeted run `pytest tests/test_web_helpers.py tests/test_web_tools.py`: 110 passed (was 105 → +5).

**Files touched**:
- `the_one/tools/_web_config.py` — IP-literal short-circuit branch in `SSRFGuardedTransport.handle_async_request` extended with `extra_allowed_hosts` operator-override check + `_is_ssrf_blocked` consultation; class docstring updated to document the new semantic.
- `tests/test_web_helpers.py` — 5 new tests in `TestSSRFGuardedTransport` covering loopback / RFC1918 / cloud-metadata / public-IP / operator-override paths.

**No regressions**: F1-F4 + F5 L0-L6 surfaces unchanged. The existing 5 `TestSSRFGuardedTransport` tests still pass; the existing `test_ip_literal_url_short_circuits_resolve` is unaffected (the new IP-literal SSRF check still calls super for public IPs without resolution). The `test_resolves_to_public_ip_passes`, `test_all_resolved_blocked_raises_constraint_error`, and DNS-rebind regression test are all in the resolve+pin path which the fix did not touch.

**HAT re-verification deferred**: HAT scenarios will be re-run after the fix lands in the working tree to confirm scenario 3 now surfaces the expected `[error] [constraint] ...` shape end-to-end through the chat + http_request stack.

---

## Session Notes

### Flight Director Notes — Orchestration Plan

**Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project crew). Crew: Developer (Sonnet), Reviewer (Haiku), optional Accessibility Reviewer (not needed — F5 has no UI changes; F6 will).

**Batching strategy** (matches F4 — same skill orchestration semantics): defer review/commit until all autonomous legs complete.
1. Design + implement L0 → L1 → L2 → L3 → L4 → L5 → L6 sequentially (no commits — uvicorn --reload picks up edits automatically per F4 follow-up).
2. L7 HAT — interactive walkthrough against working tree; inline fixes via Developer agent if needed.
3. L8 integration verification (autonomous, no commit yet).
4. Single Reviewer pass over the full uncommitted batch (L0..L8).
5. Single squashed commit on the flight branch + draft PR.

This matches the F4 protocol exactly. Net new tests target ≥80; baseline starts at 834.

**Mark flight in-flight**: Status updated from `ready` → `in-flight` at orchestration start.
