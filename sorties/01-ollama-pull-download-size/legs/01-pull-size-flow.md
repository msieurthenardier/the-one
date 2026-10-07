# Leg: pull-size-flow

**Status**: completed
**Flight**: [Ollama Pull shows the download size first](../flight.md)

## Objective
Rebuild the Ollama provider's Pull Model control around exact download sizes, end to end:
- a new backend catalog module lists every pullable `name:tag`, fetches each one's registry manifest size, and caches it on disk;
- two thin routes, `GET /api/ollama-library/search` (new shape) and `GET /api/ollama-library/size`;
- the panel's flat list, Pull label, status line, size re-check and confirmation modal;
- testids, the same-surface fixes, unit and settings-lane browser tests, and docs.

## Context
- **Design:** the flight spec's DD1–DD11 are the design, and this leg implements all of them. Where this artifact and a DD seem to disagree, the DD wins; raise it in the flight log rather than guessing.
- **Divert check:** run by the Flight Director at leg design, 2026-10-07, with a throwaway scratch script, not committed. It passed, so DD4 stands as designed.
  - **Library page:** 245 models, 217 with size tags (417 tags), 28 with none, and 17 cloud-badged. `/api/tags` lists 18 names. That makes **445 page entries**.
  - **Cold fill:** 445 manifests in **8.0 s** (a second run: 7.6 s) at concurrency 16 with a 10 s timeout. Latency p50 0.27 s, p95 0.43 s, max 0.65 s. Fetching the page and `/api/tags` took 1.7 s. There were **no** 403, 429 or transport errors.
  - **Results:** 430 × 200 and 15 × 404.
    - 13 of the 404s are cloud-badged, so `cloud`.
    - 2 are not: `wizardlm` and `qwen3.8-flash-next`, so `missing`. These are useful HAT and fixture examples.
    - 4 cloud-badged entries return 200, because the model has a cloud tag and local weights, so they are `ok`. The cloud badge only matters on a 404 (DD3).
  - **Largest:** `cogito-2.1:671b` at 1,342.3 GB, then several `*:671b` at about 404 GB. **Smallest:** `all-minilm:22m` at 46 MB. DD8's formatter has no TB unit, so the largest reads "1342.3 GB"; that is accepted.
  - **What the timing means:** a cold fill, about 10 s with the page, overruns the route's 8 s bounded wait. So the panel's `loading` path and its 2 s re-request (DD4) *will* be exercised on a real first load, not only in tests.
- **`/api/tags` names today:** `kimi-k2.7-code`, `gemma4:31b`, `glm-5.2`, `glm-5.3-flash`, `nemotron-3-nano:30b`, `minimax-m2.7`, `glm-5.3`, `deepseek-v4.1-flash`, `nemotron-3-ultra`, `kimi-k2.6`, `gpt-oss:120b`, `mistral-large-3:675b`, `mistral-large-4`, `deepseek-v4-pro:0813`, `kimi-k3`, `gpt-oss:20b`, `minimax-m3`, `nemotron-3-super`.
  - Bare ones normalise to `name:latest` and dedupe against the page's bare entries (DD4).
  - Tagged ones not on the page (for example `deepseek-v4-pro:0813`, `mistral-large-3:675b`) join their model's group after the page's tags (DD1, DD9).
- **Prior legs:** none. This is the first leg. The flight log carries the charter and design decisions.
- **Environment:** host-native, repo `.venv` (Python 3.12). CI and the Windows build run 3.11, so do not use `typing.TypedDict` in a route annotation (DD9).

## Inputs
- `main` at `f770947` (v0.10.2), on branch `sortie/01-ollama-pull-download-size`.
- Today's implementation, which this leg replaces:
  - `the_one/interfaces/web/api.py` — `_library_cache`, `_LIBRARY_CACHE_TTL`, `_OLLAMA_LIBRARY_URL`, `_OLLAMA_TAGS_URL`, `_fetch_library_models`, and `search_ollama_library` (`@router.get("/ollama-library/search")`, around lines 5306–5375).
  - `the_one/llm/ollama_api.py::parse_library_html` and `_LIBRARY_LINK_RE`.
  - `the_one/interfaces/web/static/js/areas/admin/provider-models.js::renderOllamaModels(providerId, container)` — `loadLibraryOptions` builds its `<option>` HTML string into `pullNameInput.innerHTML = html`; `startPull()` reads the select.
- `tests/test_provider_api.py::TestOllamaLibrarySearch` (around line 2616) and `::TestParseLibraryHtml` (around line 2828); `tests/fixtures/ollama_library_excerpt.html`.

## Outputs
- **New:**
  - `the_one/llm/ollama_library.py`;
  - `tests/test_ollama_library.py`;
  - `tests/browser/test_flow_provider_ollama_pull.py`.
- **Modified:**
  - `api.py` (two thin routes; the old cache, URLs and fetcher are removed);
  - `app.py` (a lifespan `shutdown_drain()`);
  - `ollama_api.py` (the parser is removed);
  - `provider-models.js`;
  - `tests/test_provider_api.py` (the search class is rewritten, the parser class removed);
  - the fixture (extended);
  - `tests/browser/conftest.py` (the default seam);
  - `tests/test_ui_guards.py` (the baseline pruned);
  - `docs/ui-testid-registry.md`;
  - `the_one/agents.md`, `SECURITY-MODEL.md`, `.env.example`.
- **Runtime state:** `{data_dir}/ollama-sizes.json` is created on the first fill.

## Acceptance Criteria

Backend:
- [x] **AC1 — module.** `the_one/llm/ollama_library.py` exists and owns:
  - the library-page fetch and the entry-scoped parser (name, size tags, cloud badge; single-segment names only);
  - the `/api/tags` merge;
  - validation;
  - the manifest fetch and status mapping;
  - the disk cache;
  - the single-flight fill;
  - the seam, `_reset_for_tests(cache_path=…)` and `shutdown_drain()`.

  `ollama_api.parse_library_html`, `_LIBRARY_LINK_RE` and `TestParseLibraryHtml` are gone, and `grep -rn "parse_library_html\|_LIBRARY_LINK_RE\|_fetch_library_models\|_library_cache" the_one tests` returns nothing.
- [x] **AC2 — entries (DD1, DD5).**
  - Each page model yields one `name:tag` per size tag, in page order, or its bare name when it has none.
  - `/api/tags`-only names are added within their model's group after the page's tags.
  - Bare and `:latest` dedupe.
  - Names and tags pass `re.fullmatch` against DD5's patterns before any URL is built, and a failing entry is dropped and logged.
  - A `/library/x/tags` link is skipped.
  - The old parser's tolerance cases (`?tab=tags`, `#top`, an absolute URL, a trailing slash) parse.
- [x] **AC3 — size and status (DD2, DD3).**
  - The size is `sum(layers[].size) + config.size`.
  - 200 → `ok`.
  - 404 with the cyan badge or an `/api/tags` listing → `cloud`.
  - 404 without either → `missing`.
  - Anything else → `unknown`: a transport error, a timeout, 3xx (`follow_redirects=False`), 403, 429, 5xx, or a bad body.
  - The host is the constant `https://registry.ollama.ai`.
- [x] **AC4 — cache (DD4).**
  - It lives at `{settings.data_dir}/ollama-sizes.json`, with the path resolved lazily, and is written atomically (tmp then `os.replace`, no `await` between them). It also holds the last library listing.
  - TTLs: `ok`/`cloud` 7 d, `missing` 1 d. `unknown` is in memory only, for 300 s. Budget-unsettled entries are not cached.
  - The map is shared, with per-key writes. An `unknown` never overwrites a known entry within its TTL.
  - Pruning happens only after a successful page parse.
  - A corrupt file, or a failing `os.replace`, logs a warning and never raises to the route.
- [x] **AC5 — fill (DD4).**
  - One detached module task, shared by concurrent callers through `asyncio.shield`, with a bounded wait of about 8 s, after which the route reads the shared map. A cancelled waiter does not cancel the fill.
  - Per fill: one `httpx.AsyncClient(limits=Limits(max_connections=16))` and one semaphore (nothing module-level is bound to a loop).
  - A 10 s per-request timeout and a 45 s budget.
  - Early stop when all of the first 16 fail with transport/403/429.
- [x] **AC6 — shutdown (DD4).** `ollama_library.shutdown_drain()` runs at the top of `app.py`'s lifespan shutdown block, in its own `try/except Exception: logger.exception(...)`. It cancels a running fill and persists what settled. It is a no-op with no fill, a finished fill, or a fill on another loop.
- [x] **AC7 — routes (DD9).**
  - **Search:** `GET /api/ollama-library/search[?q=]` returns `{"loading": bool, "models": [{"name", "size": int|null, "status"}]}`, annotated `dict[str, Any]`. It uses a stable sort on the case-insensitive model-name part, so `gemma3:1b` comes before `gemma3:12b` and `llama3.2:*` is not interleaved with `llama3.2-vision:*`. `q` is a case-insensitive substring filter.
  - **Size:** `GET /api/ollama-library/size?model=` returns one `{name, size, status}`, with `name` echoed as requested. It uses a 5 s timeout, never joins, starts or cancels a fill, and never prunes. An invalid model gets `HTTPException(422, detail=<str>)`.
  - **Python 3.11:** `api.py` imports on Python 3.11. `uv` (`~/.local/bin/uv`) and `cpython-3.11.14` are installed on this host, so the check is `uv run --python 3.11 --with-editable . python -c "import the_one.interfaces.web.api; import the_one.llm.ollama_library"`.
- [x] **AC8 — seam (DD10).**
  - `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` is honoured only with `settings.dev_mode`; otherwise it logs a warning and is ignored. It backs both routes with no network, and it neither reads nor writes `ollama-sizes.json`.
  - **The pinned shape** is `{"models": [{"name": str, "size": int | null, "status": "ok"|"cloud"|"missing"|"unknown"}, …]}`. `q` applies to it.
    - The search route returns the models in DD9's sort, with `"loading": false`.
    - The size route validates first (422 as AC7), then looks the requested name up with bare and `:latest` treated as equal, and echoes the name. A name not in the catalog is `missing`.
    - The seam is **stateless**: no counters, no per-call state. "Loading, then ready" and the size route's 4xx are driven per test with Playwright `page.route` (AC15).
  - It is documented in `.env.example` beside the OpenRouter seam.
  - `tests/browser/conftest.py`'s shared spawn sets it by default, before `env.update(extra_env)`, to a small catalog covering all four statuses.

Frontend (`provider-models.js`):
- [x] **AC9 — plumbing (DD6).**
  - `renderOllamaModels(provider, container)` takes the provider object (it has `id`, `name` and `base_url`, confirmed in `provider-editor.js:67`). Every internal id-only caller is updated:
    - the definition at `provider-models.js:98`;
    - the `renderProviderModels` dispatch at `:50`;
    - Refresh at `:123`;
    - `finishPull` at `:274`;
    - `ollamaAction`'s re-render at `:460`, with `wireOllamaActions(…)` and `ollamaAction(…)` taking the provider too.
  - `provider-editor.js` is unchanged.
  - No re-render can produce "undefined" in the modal.
- [x] **AC10 — list (DD1, DD3, DD4, DD8).**
  - Options are built with DOM APIs:
    - `ok` → `name (size)`;
    - `cloud` → `name (cloud only, not downloadable)`, disabled;
    - `missing` → `name (not downloadable)`, disabled;
    - `unknown` → `name (size unknown)`, selectable.
  - While the route answers `loading: true`, the select is disabled and reads "Loading models and sizes. The first load takes a little while…", and the panel re-requests every 2 s until it is ready. Re-requests stop if the panel's controls are no longer live.
  - The `pullNameInput.innerHTML = html` sink is gone, and its baseline entry is pruned from `tests/test_ui_guards.py`.
- [x] **AC11 — label and status (DD7, DD8).**
  - **Pull button:**
    - `ok`: "Pull · {size}";
    - `unknown`: "Pull";
    - disabled with nothing selected, during the re-check, and during a pull.
  - **Status line:** `admin-pf-pull-size`, `aria-live="polite"`, reading "Download: {size}, from the Ollama registry." or, with `.test-result-warning`, "Size unknown: the Ollama registry couldn't be reached. Pull will ask before it starts."
  - **Formatter:** one local decimal formatter (`< 1e9` → whole MB, else one-decimal GB) is used for the list, button, status line, modal, installed sizes and VRAM.
  - **VRAM line:** rebuilt with DOM APIs, with its baseline entry pruned.
  - `App.formatBytes` is unchanged.
- [x] **AC12 — re-check and modal (DD6).**
  - **Re-check:** Pull shows "Checking size…" (disabled) and calls the size route. A 4xx shows in `admin-pf-pull-error` with no modal.
  - **After the re-check:**
    - Pull is re-enabled.
    - If `pullGoBtn.isConnected` is false, flash "The panel refreshed; choose the model again" and stop.
    - Otherwise `App.ui.modal` opens with `modal.open(pullGoBtn)`.
  - **Modal wiring** (`App.ui.modal`, `ui/modal.js`):
    - the dialog's `testid` is `admin-pf-pull-confirm`;
    - `body` is a plain string (the factory sets it as text);
    - Cancel is `{label: 'Cancel', value: null, autofocus: true, testid: 'admin-pf-pull-confirm-cancel'}`, so it agrees with Escape and the backdrop (`cancelValue` defaults to `null`);
    - the confirm action is `{label: 'Pull {size}' | 'Pull anyway', variant: 'primary', value: 'pull', testid: 'admin-pf-pull-confirm-go'}`.

    `onClose(value)` runs after the modal has restored focus to the opener, so `startPull(entry)` and the focus move to the progress Cancel happen inside `onClose`, in that order.
  - **`{host}`** is `new URL(provider.base_url).host` (for example `localhost:11434`; the `/v1` path is not shown), falling back to `provider.base_url` verbatim if it doesn't parse.
  - **Modal — `ok`, or `unknown` with a cached `ok` size within TTL** (the size route already returns that cached `ok`, see step 1):
    - title "Pull {entry}?";
    - body "This downloads {size} to {provider name} ({host}).";
    - actions Cancel (autofocus) and "Pull {size}".
  - **Modal — `unknown` with no cached size:**
    - title "Pull {entry} without knowing its size?";
    - DD6's body;
    - the action "Pull anyway".
  - **`cloud`/`missing`:** no modal; re-run `loadLibraryOptions` only, and the status line says the entry is no longer downloadable.
  - **Starting the pull:** only from `onClose` with the confirm value, and only if the controls are still live. It calls `startPull(entry)` (the confirmed entry, not re-read from the select), and focus moves to the progress Cancel.
  - `App.confirmDialog` is not used.
- [x] **AC13 — testids and same-surface fixes (DD11).**
  - **Testids:** `admin-pf-pull-select`, `-btn`, `-size`, `-progress`, `-cancel`, `-error`, `admin-pf-pull-confirm`, `-confirm-cancel` and `-confirm-go` are present where the registry guard can see them. The guard's extractor is `tests/_ui_guard_helpers.py`.
    - Every id is a **single-quoted string literal**: `data-testid="…"` inside a single-quoted template string, `setAttribute('data-testid', '…')`, or a `testid: '…'` option. None may be built from a variable.
    - Each id is registered in `docs/ui-testid-registry.md`'s literal table (sorted), with Surface `admin`.
  - **Fixes:**
    - progress and error text are no longer double-escaped;
    - Pull stays disabled after Cancel with an empty selection;
    - Refresh is disabled while a pull runs.

Tests and docs:
- [x] **AC14 — unit.**
  - `tests/test_ollama_library.py` covers every item listed in the flight spec's Technical Approach § 3 "Unit".
  - `tests/test_provider_api.py::TestOllamaLibrarySearch` is rewritten for the new shape and sort; its httpx mock routes registry URLs explicitly.
  - An autouse fixture calls `ollama_library._reset_for_tests(cache_path=tmp_path/…)` before and after each test in both files.
  - The fixture gains a cloud-badged, `e2b`-tagged entry (gemma4) and a cloud-badged, untagged entry (kimi-k3).
  - Fixture sizes are layers plus config.
  - `make test-unit` passes with the expected skip count of 10, and no test reaches the network.
- [x] **AC15 — browser.** `tests/browser/test_flow_provider_ollama_pull.py` covers each bullet of the flight spec's Verification → Browser list.
  - **Provider:** seeded with the existing `_seed_ollama_provider` helper (`tests/browser/conftest.py:567`, `base_url` `http://localhost:11434/v1`).
  - **Stubbed with `page.route`:**
    - `/api/providers/*/models`, `/models/status` and `/models/pull`. The pull route is held until the focus assertion.
    - `/api/ollama-library/search`, **only** in the loading test: the first response is `{"loading": true, "models": []}`, then the request falls through to the seam with `route.continue_()`.
    - `/api/ollama-library/size`, **only** in the 4xx test: a 422 with a string `detail`.
  - **From the default seam:** everything else, including the `unknown` path (a seam entry with status `unknown`).
  - **The Pull button's states** are asserted as a small table: nothing selected, an `ok` entry, an `unknown` entry, during the re-check, and during a pull. The whole **settings** lane and the **shared** lane pass. No browser test reaches ollama.com.
- [x] **AC16 — docs.**
  - `the_one/agents.md` gains an "Ollama pull catalog" section: sources, statuses, the cache file and TTLs, single-flight, the size route, the seam.
  - `SECURITY-MODEL.md` gains DD5's outbound-fetch note.
  - `.env.example` gains the seam.

## Verification Steps
- **AC1:** `grep -rn "parse_library_html\|_LIBRARY_LINK_RE\|_fetch_library_models\|_library_cache" the_one tests` returns no output.
- **AC2–AC6, AC8 (backend):** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ollama_library.py -x --timeout 30`.
- **AC7:**
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py -k "OllamaLibrary" -x --timeout 30`.
  - Python 3.11 import: `uv run --python 3.11 --with-editable . python -c "import the_one.interfaces.web.api; import the_one.llm.ollama_library"`.
- **AC10, AC11, AC13 static:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_ui_guards.py tests/test_token_definitions.py tests/test_design_tokens_a11y.py tests/test_ui_mechanism_testids.py tests/test_nav_guard_static.py -x --timeout 60`.
- **AC14:** `make test-unit`, with 10 skipped.
- **AC15:**
  - `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=1800 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings -x`;
  - then `THE_ONE_TEST_NETNS=1 TEST_TIMEOUT=3600 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane shared -x`.
  - The netns run cannot reach the internet, so it proves no browser test needs ollama.com.
- **Lint:** `ruff check the_one/ tests/ scripts/` and `ruff format --check the_one/ tests/ scripts/`.
- **AC16:** read the three docs.

## Implementation Guidance

1. **Backend module first** (`the_one/llm/ollama_library.py`).
   - **Constants:** `LIBRARY_URL`, `TAGS_URL`, `REGISTRY = "https://registry.ollama.ai"`, `ACCEPT`, the two `re.compile` patterns (used with `.fullmatch`), the TTLs, `_UNKNOWN_TTL = 300`, the concurrency 16, the timeouts 10 s / 5 s, the budget 45 s and the wait 8 s.
   - **Parser:** split on `<li\s[^>]*items-baseline` (the previous session's whitespace lesson: a literal-class split found 0 blocks). Within each block, scope to its `<a href="…/library/{name}…">…</a>` and take:
     - the name from the first path segment after `/library/` (reject a second segment; tolerate `?…`, `#…`, an absolute URL and a trailing slash);
     - size tags from `text-blue-600` spans;
     - `cloud` from `text-cyan-500`.
   - **State:** module-level `_sizes: dict[str, dict]` keyed `name:tag` (normalised); `_library: dict | None` (entries plus `fetched_at`); `_fill: asyncio.Task | None`; `_fill_loop`; `_cache_path_override`; `_loaded_from_disk: bool`.
   - **The one map:** the fill and the size route both write per key through one helper, `_record(key, status, size)`. That helper enforces "`unknown` never overwrites a known entry within its TTL" and stamps `fetched_at`.
   - **`_persist(path)`:** synchronous; write `path.with_suffix(".json.tmp")`, then `os.replace`, with no `await`. On `OSError`, log a warning and continue. Never persist `unknown`, and never persist an entry that was not settled.
   - **`async search(q) -> dict`:**
     - load the disk cache once;
     - if the listing is stale (300 s, as `_LIBRARY_CACHE_TTL`) or any listed entry is missing or expired, start a fill or join the running one;
     - `await asyncio.wait({asyncio.shield(_fill)}, timeout=8)`, or an equivalent that never cancels the fill;
     - build the response from the shared map;
     - `loading = _fill is not None and not _fill.done()`.

     When the page is unreachable, fall back to the last persisted listing whatever its age (DD4). With no listing at all, return the `/api/tags` names only, or an empty list. Never raise to the route.
   - **`async size(model) -> dict`:** validate (a `ValueError` → the route's 422); fetch one manifest with a 5 s timeout, using its own short-lived client; take the cloud signal from the last listing or the prior status; `_record`; persist; then return the shared map's entry for that key **after** recording, with `name` echoed as requested. Because `_record` never lets an `unknown` overwrite a known entry within its TTL, a failed re-check with a cached `ok` returns that `ok` size. This is DD6's "cached `ok` is used" with no extra response field; the panel needs no special case. A failed re-check with nothing known returns `unknown`, which goes in memory for 300 s.
   - **`shutdown_drain()`:** an async no-op unless `_fill` is running on the current loop. Otherwise cancel it, suppress `CancelledError`, and persist to the path captured at fill start.
   - **`_reset_for_tests(cache_path=None)`:** cancel any pending fill on the current loop (ignore other loops), and clear `_fill`, `_library`, `_sizes` and `_loaded_from_disk`; set `_cache_path_override`.
   - **Seam:** read `os.environ.get("THE_ONE_OLLAMA_LIBRARY_TEST_JSON")` per call, as `openrouter_api.list_models` does. Suggested shape: `{"models": [{"name", "size", "status"}, …]}`.
2. **Routes** (`api.py`). Delete the old cache, URLs and fetcher.
   - `search_ollama_library(q: str = "") -> dict[str, Any]` delegates to `ollama_library.search(q)`.
   - Add `@router.get("/ollama-library/size")`, with `model: str = ""` → `ollama_library.size(model)`; a `ValueError` → `HTTPException(422, detail=str(e))`.
   - Both routes sit behind the existing credential gate (no exemption).
3. **Lifespan** (`app.py`). Add `from the_one.llm import ollama_library` (or an aliased `shutdown_drain`, matching the file's import style), and call it immediately after `yield`, before the in-flight-task cancel, in its own `try/except Exception: logger.exception("ollama library fill shutdown failed")`.
4. **Frontend** (`provider-models.js`). Work through DD6–DD8 and DD11 in order:
   - the signature and callers;
   - the formatter;
   - the template (testids, a status line `<div class="admin-pf-pull-size" data-testid="admin-pf-pull-size" aria-live="polite">`; the existing template's opening 80 characters must not change);
   - `loadLibraryOptions` with the loading loop (a timer stored per render, cleared when `!pullNameInput.isConnected`);
   - the change handler (label and status);
   - the Pull click (re-check, modal);
   - `startPull(entry)`;
   - the fixes.

   **The formatter** carries a one-line comment saying why it is local and decimal, not `App.formatBytes`, so a later cleanup does not "simplify" it away.

   **CSS:** add a rule for `.admin-pf-pull-size` beside the existing pull rules in `the_one/interfaces/web/static/css/admin.css` (the `/* === Pull UI === */` block, around line 242). Match `.admin-pf-pull-error`'s caption size and padding, and use `--fg-secondary` for the known-size line. The unknown line takes the existing `.test-result-warning` (`components.css:1390`). Disabled `<option>`s keep native styling. Use only defined tokens; `tests/test_token_definitions.py` checks this.

   **Modal:** read `the_one/interfaces/web/static/js/ui/modal.js` for the `App.ui.modal({title, body, actions, onClose, testid, dismissible})` and `open(opener)` API. The body text goes in through a text node, never HTML. Name the provider from `provider.name` and the host from `provider.base_url` (both confirmed; `{host}` per AC12).
5. **Guards.**
   - Prune exactly two entries from `tests/test_ui_guards.py`'s `"areas/admin/provider-models.js"` baseline: `"pullNameInput.innerHTML = html;"` at line 118 and `"vramEl.innerHTML = '<span class=\"admin-pf-vram-value\">' + escapeHtml(formatBytes"` at line 119.
   - **Keep** the `container.innerHTML = '<div class="admin-pf-models-header">' + …` entry at line 117 (the template stays), and both `listEl.innerHTML …` pairs (the installed-model list keeps them).
   - Add nothing before the template's `admin-pf-models-header` opening, or a new baseline entry appears and the ratchet fails.
   - Add the registry rows.
   - Run the static guards (see Verification).
6. **Tests.** Unit as in AC14. Browser as in AC15:
   - give the new file the settings lane's `test_flow_provider_*` glob (it is already covered, so there is no `run-tests.sh` change);
   - seed the provider with `_seed_ollama_provider` (`tests/browser/conftest.py:567`);
   - use the shared app and the default seam;
   - drive the loading and 4xx cases with `page.route` exactly as AC15 says.

   Do **not** add a stateful seam field, and do not spawn a separate app for these cases.

   The default seam catalog lives in `tests/browser/conftest.py`. It holds a handful of entries in the AC8 shape covering all four statuses, for example:
   - `llama3.2:1b` and `llama3.2:3b` `ok`;
   - `nomic-embed-text` `ok` (bare);
   - `kimi-k3` `cloud`;
   - `wizardlm` `missing`;
   - one `unknown`.
7. **Docs** (AC16), then the flight log: leg progress, with the Python 3.11 import check's output recorded.

## Edge Cases
- **A bare name:**
  - `nomic-embed-text` in the list pulls `:latest`;
  - the size route echoes `nomic-embed-text`;
  - the cache key is `nomic-embed-text:latest`.
- **Cloud signals:**
  - a cloud-badged model whose tag returns 200 is `ok`, not `cloud` (4 live cases);
  - an `/api/tags`-listed name whose manifest 404s is `cloud`.
- **Errors and degradation:**
  - a 3xx from the registry is `unknown` (no redirect followed);
  - the page fetch fails with no persisted listing: show the `/api/tags` names only (or "Library unavailable" if empty), and do not prune;
  - an `unknown` entry is then re-requested after 300 s, not on every render.
- **Interactions:**
  - a panel re-render while the modal is open, or during a re-check: guard on `pullGoBtn.isConnected`, never on `container.isConnected`. When the opener is gone, `modal.js` restores focus to `#main-content` (`modal.js:121-122`). That is accepted, and the flash names what happened;
  - the loading loop must stop when the panel is re-rendered or the editor is closed (no orphan timers);
  - Refresh while a pull runs is disabled (DD11).
- **Event loops:** the unit suite cycles `TestClient(app)` lifespans hundreds of times. `shutdown_drain()` and `_reset_for_tests` must tolerate a `_fill` bound to a closed loop (compare `_fill.get_loop()` with `asyncio.get_running_loop()`).

## Files Affected
- **New:**
  - `the_one/llm/ollama_library.py` — the catalog, sizes, cache, single-flight, seam and test hooks;
  - `tests/test_ollama_library.py`;
  - `tests/browser/test_flow_provider_ollama_pull.py`.
- **Backend:**
  - `the_one/interfaces/web/api.py` — two thin routes; the old library code is removed;
  - `the_one/interfaces/web/app.py` — the lifespan `shutdown_drain()`;
  - `the_one/llm/ollama_api.py` — `parse_library_html` and `_LIBRARY_LINK_RE` are removed.
- **Frontend:**
  - `the_one/interfaces/web/static/js/areas/admin/provider-models.js` — the panel rebuild;
  - `the_one/interfaces/web/static/css/admin.css` — the `.admin-pf-pull-size` rule.
- **Tests:**
  - `tests/test_provider_api.py` — the search class is rewritten, and the parser class removed;
  - `tests/fixtures/ollama_library_excerpt.html` — the gemma4 and kimi-k3 entries;
  - `tests/browser/conftest.py` — the default seam;
  - `tests/test_ui_guards.py` — two baseline entries pruned.
- **Docs:**
  - `docs/ui-testid-registry.md` — nine rows;
  - `the_one/agents.md`, `SECURITY-MODEL.md`, `.env.example` — the doc notes.

## Citation Audit
Checked against the working tree on `sortie/01-ollama-pull-download-size` at `f770947`, the same commit the flight spec's audit verified, on 2026-10-07:

| Citation | Status |
|---|---|
| `api.py` around lines 5306–5375 — `_library_cache`, `_LIBRARY_CACHE_TTL = 300`, the two URLs, `_fetch_library_models`, `search_ollama_library` | verified (grep) |
| `provider-models.js:98` — `function renderOllamaModels(providerId, container)`; `:136` `loadLibraryOptions`; `:155` `pullNameInput.innerHTML = html;`; `:164` `startPull()` with no argument; `:195`/`:239`/`:261` the double `escapeHtml` in `textContent`; `:324` the VRAM sink | verified (read) |
| `tests/test_ui_guards.py:113` — the `"areas/admin/provider-models.js"` baseline holds both `pullNameInput.innerHTML = html;` and `vramEl.innerHTML = '<span class="admin-pf-vram-value">' + escapeHtml(formatBytes` | verified (read) |
| `app.py` around lines 381–394 — `yield`, then the in-flight-task cancel loop at the top of the shutdown block | verified (read) |
| `.env.example:110` — `# THE_ONE_OPENROUTER_TEST_MODELS_JSON=[]` | verified (grep) |
| `docs/ui-testid-registry.md` — the literal table, sorted, with no `admin-pf-*` rows yet | verified (grep) |
| `tests/browser/conftest.py:567` `_seed_ollama_provider` (base_url `http://localhost:11434/v1`); `:188` `_spawn_app`, with `env.update(extra_env)` at `:221-222` | verified (design review) |
| `ui/modal.js` — text `body` (`:185-186`), actions `{label, variant, value, testid, autofocus}` (`:199-208`), `cancelValue` default `null` (`:88`), focus restored then `onClose` (`:140-143`), `open(opener)` (`:298-301`), dialog `testid` (`:239`) | verified (design review) |
| `admin.css` around line 242 — the `/* === Pull UI === */` block; `components.css:1390` — `.test-result-warning` | verified (read) |
| Live registry and library page (the Context section above) | verified (probe, 2026-10-07) |

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
