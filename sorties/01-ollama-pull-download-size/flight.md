# Sortie: Ollama Pull shows the download size first

**Status**: in-flight

## Charter

### Outcome
Before you pull an Ollama model, the Models panel shows exactly how big the download is and asks you to confirm, so a model that is too big is never pulled by accident.

### Why Now
v0.10.2 (squawk 0053) grew the Pull Model list from about 18 models to about 251, but only about 14 of them show a size. One click on any of the other ~237 could start a multi-GB download unannounced, and some cloud-model weights run to hundreds of GB. The operator raised it on 2026-10-07.

### Success Criteria
- [ ] For the chosen model, the exact download size (from Ollama's registry manifest) is shown before Pull is enabled.
- [ ] Every pull needs an explicit confirmation that names its download size. *(Operator decision 2026-10-07: always confirm, no threshold.)*
- [ ] If the size can't be determined, you're told so, and nothing downloads unless you explicitly agree to pull without knowing its size.
- [ ] You can choose a variant, such as `llama3.2:1b` instead of `llama3.2:3b`, not only `:latest`.

### Constraints
- The pull mechanism itself (`POST /api/providers/{id}/models/pull` streaming) is unchanged; the size step comes before it.
- Outbound requests go only to fixed Ollama hosts, with the model name and tag validated, so no URL is user-controlled.
- No new dependency.
- The Ollama server may be on another machine, so nothing is claimed about its free disk space.

---

## Pre-Flight

### Objective
Rebuild the Ollama provider's Pull Model control around exact download sizes.
- **Server:** lists every pullable variant of every library model (`llama3.2:1b`, `llama3.2:3b`, …), fetches each one's exact download size from the Ollama registry manifest, caches the sizes on disk, and returns them with the list.
- **Panel:** shows one flat list whose entries read `llama3.2:3b (2.0 GB)`, and greys out entries that can't be downloaded.
- **Pull:** the button shows the size; clicking it re-checks that one size and asks for confirmation naming it before any pull starts.

The approved mockup is the canvas "Ollama Pull sizes" (https://claude.ai/artifact/TCDURcrSPbtCcHN63irs7j), row A.

### Open Questions
- [x] List shape → one flat list, every entry with its size (DD1; operator chose option A over model-then-variant, 2026-10-07)
- [x] Confirmation threshold → none; every pull confirms (DD6)
- [x] Size unknown → confirm, never block (DD6)
- [x] First-load wait → a disabled list with a clear message; no progressive fill (DD4)
- [x] Cloud-only models → shown, greyed out, not downloadable; cloud-model support is a later sortie (DD3)
- [x] HAT → yes (leg 2)
- [x] Does Refresh bypass the size cache? → No. The Pull click re-checks the chosen entry's size (DD6), so the confirmation is always current. Refresh keeps its meaning: installed and running models.
- [x] TTL for `missing` → 1 day, so a false `missing` clears quickly. `ok` and `cloud` stay 7 days (DD4).
- [x] Where `/api/tags`-only names sort → inside their model's group, after the page's tags, in `/api/tags` order (DD9).
- [x] Shutdown versus a running fill → the fill is detached from requests; the route waits at most about 8 s and otherwise answers "still loading", and the panel re-requests (DD4, DD9). There is no global `timeout_graceful_shutdown`, which would also cut pull streams.
- [x] Pull re-check returns `unknown` but a cached `ok` size within its TTL exists → the modal shows the cached size (DD6).
- [x] `GET /size?model=nomic-embed-text` → echoes the requested string as `name` (bare stays bare); the cache key is normalised to `name:latest` internally (DD9).
- [x] Entries left unsettled by the budget → not negatively cached; the next fill retries them (DD4).

### Design Decisions

**DD1: One flat list of `name:tag` entries, each with its size.**
- **Page entries:** each library model contributes one entry per parameter-size tag the library page lists for it (`llama3.2:1b`, `llama3.2:3b`), in the page's order, which is ascending size.
- **No size tags:** a model the page lists with none contributes its bare name, which pulls `:latest` (`nomic-embed-text`).
- **`/api/tags`-only names** (for example `deepseek-v4-pro:0813`) are added as written, within their model's group (DD9).
- Rationale: the operator chose this over model-then-variant after comparing both mockups. The size is visible while scanning, and the tag order puts the big variants last.
- Trade-off: a long native `<select>` of about 445 entries (type-to-jump still works), and every size must be known up front (DD4).
- Measured 2026-10-07, and confirmed independently by the Architect: 245 library models → 417 size tags across 217 models, plus 28 models with none: 445 entries.

**DD2: The exact download size comes from the Ollama registry manifest.**
- **Request:** `GET https://registry.ollama.ai/v2/library/{name}/manifests/{tag}` with `Accept: application/vnd.docker.distribution.manifest.v2+json`.
- **Size:** the sum of `layers[].size` plus `config.size`. This is the data `ollama pull` downloads.
- **Measured 2026-10-07:**
  - `llama3.2:1b`: 1,321,097,844 B of layers plus a 485 B config, so 1,321,098,329 B;
  - `gpt-oss:120b`: 65,369,818,451 B of layers;
  - `deepseek-r1:671b`: 404,430,189,771 B of layers.
  - Test fixtures must compute layers plus config.
- **No tag listing:** `/v2/library/{name}/tags/list` is a 404, so tags come from the library page (DD1). Manifests are served over HTTP/1.1 with no redirect, and httpx's default User-Agent gets the same responses as curl.
- **`/api/tags` sizes are no longer used.** They are cloud-weight sizes. `/api/tags` remains a name source and a cloud signal (DD3).

**DD3: Entry status, and what greys out.**
Each entry carries exactly one status:
- `ok`: the manifest was a 200, and its size is known.
- `cloud`: the manifest was a 404, and the model carries a cloud signal: either the library page's cyan `cloud` badge on its entry (`text-cyan-500`, 17 entries today, `mistral-large-3` among them) or a listing in `/api/tags`. The entry is labelled "(cloud only, not downloadable)" and disabled. No `:cloud` probe is made.
- `missing`: the manifest was a 404 and there is no cloud signal. The entry is labelled "(not downloadable)" and disabled.
- `unknown`: any other outcome — a transport error, a timeout, any status other than 200 or 404 (3xx, 403, 429, 5xx), or an unparseable body. The entry is labelled "(size unknown)" and stays selectable (DD6).

This fixes v0.10.2's entries that showed "1.5 TB" and could not be pulled. Cloud-model support (a signed-in local Ollama, or an ollama.com API-key provider) is a separate, later sortie.

**DD4: Size cache — disk-backed, filled by a detached task, incremental.**
- **Storage:** `{settings.data_dir}/ollama-sizes.json`.
  - It holds the sizes, keyed `name:tag` with bare names normalised to `name:latest` (`/api/tags` and the page both list `kimi-k3` bare, and they must dedupe), each `{size, status, fetched_at}`. It also holds the last parsed library listing with its `fetched_at`, so an ollama.com outage after a restart still shows the full list.
  - It is written atomically: a temp file then `os.replace`, synchronously, with no `await` between the two. This follows `model_catalog.refresh_catalog_cache`.
  - The default path is computed lazily from `settings.data_dir`, not at import.
  - The file stays in memory after the first load.
  - A corrupt file, or an `os.replace` failure such as a Windows `PermissionError`, degrades to "no disk cache" with a logged warning, never a 500.
- **One shared map, per-key writes.** The fill and the size route (DD6) both write per key into one in-memory dict. There is no fill-local snapshot swapped in at the end.
  - An `unknown` result never overwrites a known `ok`, `cloud` or `missing` entry that is still within its TTL, from either writer.
  - Persistence writes the whole current dict.
  - Pruning removes entries for names no longer listed. It happens only in a fill whose library-page fetch and parse succeeded, never otherwise. The size route never prunes. Pruning after a failed page fetch would wipe about 430 valid sizes when only the 18 `/api/tags` names were listed.
- **Lifetimes:**
  - `ok` and `cloud`: 7 days on disk.
  - `missing`: 1 day on disk.
  - `unknown`, meaning the request actually failed: never on disk. It is kept in memory for 300 s (matching `_LIBRARY_CACHE_TTL`), so a degraded network or a 403/429 is not re-hammered by every panel render. The panel renders on load, Refresh, Test connection, and after every Load, Unload, Delete and Pull.
  - Entries the budget left unsettled are NOT negatively cached; the next fill retries them.
- **A detached fill.**
  - The fill runs as a module-level `asyncio.Task`, not inside the request. It covers the library-page fetch, the `/api/tags` fetch and the size fetches.
  - A request that finds sizes missing or stale starts a fill if none is running, or joins the running one.
  - It awaits `asyncio.shield(fill)` for at most about 8 s. Without the shield, one cancelled waiter cancels the shared fill for everyone.
  - After the wait, the request reads the shared map, never the task's return value. If the fill is still running, the route answers "still loading" (DD9).
- **Fetch limits:**
  - one `httpx.AsyncClient` per fill, with `Limits(max_connections=16)`, and the concurrency semaphore also created per fill — no module-level semaphore, lock or client, so nothing is bound to an old event loop;
  - a 10 s timeout per manifest request;
  - a 45 s overall budget per fill — everything settled by then is persisted, and the rest stays unsettled.
- **Early stop:** the first wave is the first 16 requests, awaited before any further request starts. If every one of them fails at the transport level or with a 403 or 429, the fill stops and marks those `unknown`. The rest stay unsettled and are not requested.
- **Shutdown:** `ollama_library.shutdown_drain()` runs at the top of the lifespan shutdown block in `the_one/interfaces/web/app.py`, beside the in-flight-task cancel, in its own `try/except Exception: logger.exception(...)` like the other drains.
  - It cancels the fill, suppresses `CancelledError`, and persists what settled, using the path captured when the fill started.
  - It is a no-op when there is no fill, when the fill is done, or when the fill is bound to another loop; the unit suite cycles `TestClient(app)` lifespans hundreds of times.
  - The fill is detached and requests wait at most about 8 s, so uvicorn's request drain, which runs before lifespan shutdown, never holds `make down` behind a fill.
- **First-load UX (operator decision):**
  - the select stays disabled, reading "Loading models and sizes. The first load takes a little while…", while the route answers "still loading";
  - the panel re-requests every 2 s until the list is ready;
  - there is no progressive fill, and the copy carries no number.
- Measured: 43 manifests in 1.2 s at concurrency 16, so a cold fill takes about 13 s on the planning host. Leg 1 measures one full cold fill early (see Legs).

**DD5: Outbound requests are fixed-host and validated.**
- **Validation:** manifest URLs are built only from a `name` and a `tag` that each pass an anchored allowlist (applied with `re.fullmatch`, because `re.match` with `$` accepts a trailing newline) before interpolation, following SECURITY-MODEL.md's operator-supplied identifier rule (exemplar `_VALID_NPX_PKG_RE`):
  - `name`: `^[a-z0-9][a-z0-9._-]{0,127}$`, a single segment only. Namespaced models live at a different registry path and are out of scope.
  - `tag`: `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
  - Every one of today's 245 names and 92 distinct tags passes (`e2b`, `0.6b`, `1.5b`, `567m`, `128x17b`, `8x22b`).
- **Rejects:** the variant parser skips any library link with a second path segment (`/library/x/tags`). An entry that fails validation is dropped and logged.
- **Fixed host:** the host is the constant `https://registry.ollama.ai`, with `follow_redirects=False` for manifests, so a 3xx is `unknown`.
- **Pull route:** its own name handling is unchanged (a charter constraint).
- **Docs:** SECURITY-MODEL.md gains a short note on what the app fetches from ollama.com and the registry, and that names are validated.

**DD6: Pull re-checks the size, then always confirms in an `App.ui.modal`. An unknown size confirms but never blocks.**
- **Re-check:** clicking Pull calls `GET /api/ollama-library/size?model={entry}` (DD9).
  - The route validates the name and tag exactly as DD5, fetches that one manifest with a 5 s timeout, and writes the result into the shared map under DD4's rules.
  - It never joins, starts or cancels a fill, and never prunes.
  - It takes its cloud signal from the last-known library data, whatever its age, or from the entry's prior status; it does not refetch the page.
  - While the re-check runs, the button shows "Checking size…" and is disabled.
  - A 4xx from the re-check is an error, shown in `admin-pf-pull-error`. It is not treated as `unknown`, so it never leads to "Pull anyway".
- **When the re-check settles:**
  - Re-enable Pull and restore its label.
  - If this render's controls are no longer live (`pullGoBtn.isConnected` false), do nothing; the panel has re-rendered in place, so flash "The panel refreshed; choose the model again".
  - Otherwise open the modal with `modal.open(pullGoBtn)`. Pull is enabled again at this point, so Cancel restores focus to it.
- **The modal**, driven by the re-checked result:
  - **`ok`**, or **`unknown` with a cached `ok` size within its TTL** (which is then used):
    - title "Pull {entry}?";
    - body "This downloads {size} to {provider name} ({host}).";
    - actions Cancel (autofocused) and "Pull {size}".
  - **`unknown` with no cached size:**
    - title "Pull {entry} without knowing its size?";
    - body "The Ollama registry couldn't be reached, so the download size is unknown. It could be very large.";
    - confirm action "Pull anyway".
  - **`cloud` or `missing`** (the registry changed since the list loaded): no modal. Re-run `loadLibraryOptions` only, not a full panel re-render that would wipe the message, then set the status line to say the entry is no longer downloadable.
- **Starting the pull:**
  - It starts only from the modal's `onClose` with the confirm value, and only if this render's controls are still live; the panel re-renders in place on Refresh, Test connection, and after a Load, Unload, Delete or Pull, and a Load can take tens of seconds. "Container still connected" is the wrong guard.
  - The confirmed entry is passed in: `startPull(entry)`, not re-read from the select.
  - After the pull starts, focus moves to the progress Cancel button.
- **Plumbing:** `renderOllamaModels` takes the provider object, for its name and host. `provider-editor.js` already passes the provider to `renderProviderModels(host, provider)` and needs no change. The id-only calls are internal to `provider-models.js` and all change: `renderProviderModels`' dispatch, the Refresh handler, `finishPull`, `wireOllamaActions` and `ollamaAction`. If `ollamaAction` is missed, its re-render produces a modal reading "undefined (undefined)".
- **`App.confirmDialog` is NOT used.** `tests/test_nav_guard_static.py` pins its callers, and it carries leave-guard meaning.

**DD7: Pull button and status line.**
- **Pull button:** with a known size it reads "Pull · {size}". With an `unknown` entry it reads "Pull". With nothing selected, during the re-check, or during a pull, it is disabled.
- **Status line** (testid `admin-pf-pull-size`, `aria-live="polite"`) under the row:
  - known: "Download: {size}, from the Ollama registry.";
  - unknown: "Size unknown: the Ollama registry couldn't be reached. Pull will ask before it starts.", using the existing `.test-result-warning` class.
- `cloud` and `missing` entries can't be selected.

**DD8: Sizes in decimal units, across the whole panel.**
- A new local helper in `provider-models.js` formats them: `< 1e9` → whole MB ("523 MB"), else one decimal GB ("2.0 GB", "404.4 GB"). This matches ollama.com and `ollama pull`.
- It is used for the Pull list, the button, the status line, the modal, and the same panel's installed-model and VRAM sizes. Otherwise the same model would read "2.0 GB" in the list and "1.9 GB" once installed.
- The VRAM summary line is rebuilt with DOM APIs, and its baseline entry in `tests/test_ui_guards.py` is pruned. Its sink statement (`vramEl.innerHTML = '<span class="admin-pf-vram-value">' + escapeHtml(formatBytes…`) ends its 80-character snippet in `formatBytes`, so swapping the formatter there would read as a new sink and fail the ratchet.
- `App.formatBytes` (binary maths labelled "GB") is not changed in this sortie; its other callers are logged as a squawk at flight close.

**DD9: Route shapes, sort and module layout.**
- **`GET /api/ollama-library/search`** returns `{"loading": bool, "models": [{"name": str, "size": int | null, "status": "ok"|"cloud"|"missing"|"unknown"}]}`.
  - `loading` is true while a fill is still running after the route's bounded wait (DD4); the panel then keeps its loading state and re-requests.
  - The route stays annotated `dict[str, Any]`. No `TypedDict` is used in a route annotation: Pydantic raises at import on Python 3.11 for a `typing.TypedDict` (`PydanticUserError`, it requires `typing_extensions.TypedDict` below 3.12). CI and the Windows build run 3.11, while the dev venv is 3.12, so it would pass locally and break everywhere else. `typing_extensions` is not a declared dependency.
  - `name` is the pullable `name:tag`, or the bare name.
  - `size` is in bytes when `status == "ok"`, else `null`.
  - `q` is a case-insensitive substring filter, as today.
- **Sort:** a stable sort keyed on the model-name part only (before the `:`), case-insensitive. Inside a model, entries keep the page's tag order, followed by any `/api/tags`-only names in `/api/tags` order. The old full-string sort (`results.sort(key=lambda r: r["name"].lower())`, `api.py:5370`) would order `gemma3:12b` before `gemma3:1b` and interleave `llama3.2-vision:*` with `llama3.2:*`. It is replaced, and `test_basic_search`'s lexical expectation is rewritten.
- **`GET /api/ollama-library/size?model=…`** (DD6) returns one entry `{name, size, status}`. `name` echoes the requested string, so a bare name stays bare; the cache key is normalised to `name:latest` internally.
  - An invalid `model` gets `HTTPException(422, detail="…")` with a plain-string detail, which matches the API's convention and renders through the panel's `e.detail`. Not `Query(pattern=…)`, whose list-shaped detail would render as "[object Object]".
- **Only consumer:** `provider-models.js:loadLibraryOptions`, confirmed by the Architect's grep. Nothing else imports or patches `_fetch_library_models` or `_library_cache` (only `tests/test_provider_api.py`).
- **Module layout:**
  - A new `the_one/llm/ollama_library.py` owns the library-page fetch and parsing, the `/api/tags` merge, the variants, the sizes, the cache and the single-flight.
  - It gets a variant-aware parser scoped to each entry's own `<a>…</a>` block, which captures the name, the size tags (the `text-blue-600` spans) and the cloud badge (`text-cyan-500`). Without that scoping, spans bleed into the next entry.
  - This parser replaces `ollama_api.parse_library_html` and `_LIBRARY_LINK_RE`, which are deleted with `TestParseLibraryHtml`, so no dead code is left.
  - `api.py`'s two routes become thin.
  - It exposes `_reset_for_tests(cache_path=…)`, which cancels a pending fill, then resets the fill handle, the library cache and the size cache and points the cache path at a test directory. An autouse fixture in both test files calls it before and after each test (`asyncio_mode = "auto"`, one event loop per test). This mirrors `db/_write_lock.reset_for_test` and `model_catalog._reset_for_tests`. Without it, the shared unit-session data dir (`tests/conftest.py`) leaks `ollama-sizes.json` between tests, and Python 3.12 loop-bound primitives raise across pytest-asyncio loops.

**DD10: The test seam, and no live network in tests.**
- **The seam:** `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` supplies the catalog, the `models` list (the search route then answers with `loading: false`), and backs the size route by looking an entry up in it, so no ollama.com or registry request is made.
  - It is honoured only when `settings.dev_mode` is true. When dev mode is off, a warning is logged and the variable is ignored.
  - This mirrors `openrouter_api.list_models`' `THE_ONE_OPENROUTER_TEST_MODELS_JSON` seam.
  - `q` filtering applies to the seam data too.
  - It is documented in `.env.example` beside the OpenRouter seam. There is no CLAUDE.md paragraph, following the precedent.
- **Browser default:** `tests/browser/conftest.py`'s shared app spawn sets the variable by default to a small canned catalog covering all four statuses. It is set before `env.update(extra_env)`, so a test can override it. About 1 KB is a non-issue as an env var.
  - Browser tests that open an Ollama provider then never reach the network. Today `test_flow_settings_visible_fixes.py` and `test_flow_settings_focus_after.py` do, and would now trigger a ~445-request fill.
  - The `extra_env` callers (the OpenRouter fixtures and `test_flow_context_overlay_thresholds.py`) pass unrelated keys.
- **Pull browser test:** it also fulfils `/api/providers/*/models`, `/models/status` and `/models/pull` (`text/event-stream`) through Playwright `page.route`, so no Ollama server is needed.

**DD11: The pull controls get testids, and nearby defects are fixed in passing.**
- **New testids**, registered in `docs/ui-testid-registry.md`: `admin-pf-pull-select`, `admin-pf-pull-btn`, `admin-pf-pull-size`, `admin-pf-pull-progress`, `admin-pf-pull-cancel`, `admin-pf-pull-error`, and the modal's `admin-pf-pull-confirm`, `admin-pf-pull-confirm-cancel` and `admin-pf-pull-confirm-go`.
  - They are set where the registry guard sees them: `data-testid="…"` inside the existing template, after its first 80 characters (the opening that identifies the sink must not change); `setAttribute('data-testid', '…')` with single quotes; or a `testid:` option.
  - `el.dataset.testid` is not seen by the guard.
- **Options** are built with `createElement`. The removed `pullNameInput.innerHTML = html` sink's baseline entry in `tests/test_ui_guards.py` is pruned as a leg step; the guard tolerates a stale entry, so it won't force this.
- **Same-surface fixes:**
  - double-escaped progress and error text (`textContent = escapeHtml(...)`);
  - Pull re-enabled after Cancel with an empty selection.
  - Refresh during a pull re-renders the panel and orphans an uncancellable pull. Refresh is disabled while a pull runs.

### Citation Audit

Verified against the working tree at `f770947`, and spot-checked independently by the Architect:

| Citation | Status |
|---|---|
| `the_one/interfaces/web/api.py::search_ollama_library` — `GET /ollama-library/search`, module cache `_library_cache` with `_LIBRARY_CACHE_TTL = 300`, sources `_OLLAMA_LIBRARY_URL` / `_OLLAMA_TAGS_URL` via `_fetch_library_models`, full-string sort (DD4, DD9) | verified |
| `the_one/llm/ollama_api.py::parse_library_html` / `_LIBRARY_LINK_RE` — names only, optional `/segment`, size and badge spans ignored (DD5, DD9) | verified |
| `the_one/interfaces/web/api.py` pull route `POST /providers/{provider_id}/models/pull` — `model = data.get("model", "").strip()`, no other validation (DD5) | verified |
| `the_one/interfaces/web/static/js/areas/admin/provider-models.js::loadLibraryOptions` — option string, `pullNameInput.innerHTML = html` (DD9, DD11) | verified |
| `provider-models.js::renderOllamaModels(providerId, container)` — receives the id only; re-rendered in place by Refresh, `finishPull(true)`, `ollamaAction`, and Test connection through `renderProviderModels`; `provider-editor.js` already passes the provider object to `renderProviderModels(host, provider)` (DD6) | verified |
| `the_one/interfaces/web/app.py::lifespan` — shutdown block with the in-flight-task cancel and per-drain `try/except` (DD4); uvicorn drains requests before lifespan shutdown | verified (Architect, cycle 2) |
| `tests/test_ui_guards.py` — `provider-models.js` VRAM sink `vramEl.innerHTML = '<span class="admin-pf-vram-value">' + escapeHtml(formatBytes…` in the baseline (DD8) | verified (Architect, cycle 2) |
| `tests/test_ui_guards.py` — `"areas/admin/provider-models.js"` sink baseline entry; removing a site does not fail the guard (DD11) | verified |
| `provider-models.js::startPull` — `POST …/models/pull` with `JSON.stringify({ model: model })`, SSE via `getReader()` (DD6: mechanism unchanged) | verified |
| `the_one/interfaces/web/static/js/ui/modal.js` — `title`, `body`, `actions[{label, variant, value, testid, autofocus}]`, `dismissible`, `onClose(value)` once after close and focus restore, `testid` (DD6) | verified |
| `tests/test_nav_guard_static.py` — pins the set of files calling `App.confirmDialog(` (DD6) | verified |
| `the_one/interfaces/web/static/js/app.js::formatBytes` — divides by 1024, labels "GB" (DD8) | verified |
| `the_one/llm/model_catalog.py::refresh_catalog_cache` — atomic `<cache>.tmp` then `os.replace` under `settings.data_dir` (DD4) | verified |
| `the_one/llm/openrouter_api.py::list_models` — `THE_ONE_OPENROUTER_TEST_MODELS_JSON` honoured only when `settings.dev_mode`, warning otherwise (DD10) | verified |
| `tests/browser/conftest.py` — shared spawn env sets `THE_ONE_DATA_DIR`, `THE_ONE_DEV_MODE=true`, then `env.update(extra_env)` (DD10) | verified |
| `tests/test_provider_api.py::TestOllamaLibrarySearch` — `_mock_httpx` routes non-`/library` URLs to the tags payload; `test_cache_hit` asserts `mock_cls.call_count == 2`; class autouse `_reset_cache` (DD9: rewritten) | verified |
| `the_one/interfaces/web/static/css/components.css` — `.test-result-warning` (DD7) | verified |
| `scripts/run-tests.sh` — `settings_pat=('test_flow_admin_*' 'test_flow_provider_*' 'test_flow_settings_*')` (Verification lane) | verified |
| Registry and library-page behaviour (DD1–DD3, DD5) — counts, manifest sizes, the 404 pattern, the cyan cloud badge; probed live 2026-10-07 | verified (external; re-probed at each leg start) |

### Prerequisites
- [x] No active mission overlaps; no other open sortie
- [ ] **At the start of each leg (external, re-verified per leg):**
  - the Ollama registry serves v2 manifests (`llama3.2:1b` → 200; `kimi-k3:latest` → 404);
  - the library page still carries per-entry size tags and the cloud badge.

  These are the checks behind the Divert criteria.
- [ ] **HAT only:**
  - the operator's local Ollama at `http://localhost:11434` is running;
  - the operator agrees to pull, then delete, `qwen3:0.6b` (523 MB).

  Re-verify at the start of the HAT leg.
- [ ] **HAT only:** a dev instance on a non-default port, never 8484, with:
  - a fresh scratch data directory, never the default one, for the cold load;
  - `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` unset (with dev mode on, a leaked variable would silently swap in the canned catalog);
  - an Ollama provider pointed at the operator's Ollama.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [x] Prerequisites verified (planning-time ones; the per-leg and HAT ones are re-verified at their time)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Backend (new `the_one/llm/ollama_library.py`):**
   - The entry-scoped variant parser: name, size tags, cloud badge; single-segment names only.
   - The `/api/tags` merge as a name source and cloud signal.
   - The validated manifest fetch with DD3's status mapping.
   - The disk-backed size cache with in-memory `unknown`, single-flight task, budget, early stop, pruning and graceful degradation.
   - The seam and `_reset_for_tests`.
   - In `api.py`: the search route (DD9's shape and sort, with `loading`) and the new size route. In `the_one/interfaces/web/app.py`: `shutdown_drain()` at the top of the lifespan shutdown block (DD4).
   - `ollama_api.parse_library_html`, `_LIBRARY_LINK_RE` and their tests are deleted.
2. **Frontend (`provider-models.js` only; `provider-editor.js` already passes the provider):**
   - `renderOllamaModels(provider, container)`, and its internal id-only callers (DD6).
   - The `loading` re-request loop (DD4).
   - `loadLibraryOptions` builds options with DOM APIs, using DD3's labels and disabled states and DD4's first-load copy.
   - The decimal formatter is used across the panel (DD8).
   - Selection updates the Pull label and status line (DD7).
   - Pull re-checks the size, then opens the modal (DD6). Confirm calls `startPull(entry)` with the live-controls guard, then moves focus to Cancel.
   - Testids and same-surface fixes (DD11).
3. **Tests:**
   - **Unit:** a new `tests/test_ollama_library.py` covers:
     - the parser on the extended fixture;
     - validation;
     - each status mapping, including 403/429/3xx → `unknown`;
     - the cache TTLs, the in-memory unknown, the incremental fill and pruning;
     - the corrupt-file and replace-failure degradation;
     - the budget, unsettled entries not being negatively cached, and the early stop (transport failures and 403/429);
     - the detached fill: concurrent callers share one task through `asyncio.shield`, a cancelled waiter does not cancel the fill, and a bounded wait returns `loading`;
     - the size route writing mid-fill without the fill overwriting it, and `unknown` never overwriting a known entry within its TTL;
     - pruning only after a successful page parse;
     - `shutdown_drain()` cancelling a running fill and persisting what settled, and being a no-op with no fill;
     - the seam gating and `q` on seam data.

     `tests/test_provider_api.py::TestOllamaLibrarySearch` is rewritten for the new shapes and sort. Its httpx mock routes registry URLs explicitly; patching `api.httpx` patches the global module, so routing is what matters.
   - **Parser tolerance:** port the old parser's cases (`?tab=tags`, `#top`, an absolute URL, a trailing slash) into the new parser's tests.
   - **Fixture:** extend `tests/fixtures/ollama_library_excerpt.html` with one cloud-badged entry that has `e2b`-style tags (gemma4) and one cloud-badged entry with no tags (kimi-k3).
   - **Browser:** one new settings-lane file, `tests/browser/test_flow_provider_ollama_pull.py`, plus the conftest default seam.
4. **Docs:**
   - `the_one/agents.md` gains an "Ollama pull catalog" note: sources, statuses, the cache file and lifetimes, single-flight, the size route, and the seam.
   - SECURITY-MODEL.md gains the outbound-fetch note (DD5).
   - `.env.example` gains the seam entry.

### Checkpoints
- [ ] The search route returns `name:tag` entries in DD9's sort, with sizes and statuses, from a cold cache, and instantly from a warm one
- [ ] The panel lists `llama3.2:3b (2.0 GB)`-style entries, greys out cloud/missing, re-checks the size on Pull and confirms every pull with it
- [ ] No browser test reaches ollama.com
- [ ] HAT: the operator pulls a small model against the real Ollama and is satisfied

### Adaptation Criteria

**Divert if**:
- The registry rate-limits or blocks a ~445-request cold fill. Then fall back to per-selection fetching, which is a design change, so re-plan with the operator.
- The library page no longer exposes per-entry size tags or the cloud badge. Then the variant or cloud source must change, so re-plan.

**Acceptable variations**:
- Exact concurrency, timeout, budget and TTL numbers, if measurement shows better values.
- Exact copy of the status line and dialog, within DD6/DD7's meaning, if the HAT prefers different wording.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `pull-size-flow` - First, before building on DD4, run one full ~445-request cold fill against the live registry with a throwaway script and record timing and any 403/429 responses (the Divert check). Then the whole feature slice: the backend catalog module (variants, registry sizes, disk cache, single-flight, test seam); the search and size routes; the panel's flat list, Pull label, status line, size re-check and confirmation modal; testids and same-surface fixes; unit and settings-lane browser tests; docs.
- [ ] `hat-and-alignment` *(optional, opted in)* - A guided HAT against the operator's real Ollama on a fresh scratch dev instance. Walk:
  - the cold load;
  - scanning the list;
  - a cloud entry;
  - confirm and Cancel;
  - a real pull of `qwen3:0.6b`, then deleting it;
  - a restart, then the warm reload, which proves the disk cache.

  Fix what surfaces.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
- **Unit (`make test-unit`):**
  - `tests/test_ollama_library.py`;
  - the rewritten `tests/test_provider_api.py::TestOllamaLibrarySearch`;
  - the static guards: `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`, and the testid registry guard.
- **Browser (settings lane):** `tests/browser/test_flow_provider_ollama_pull.py`, run via `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane settings`. It covers:
  - the list labels and order, with `1b` before `3b`;
  - disabled cloud and missing entries;
  - the Pull label carrying the size;
  - the size re-check;
  - the modal naming the size;
  - Cancel sends no pull request;
  - Confirm sends `{"model": "llama3.2:3b"}` and focus lands on the progress Cancel button. The `/models/pull` route is held unfulfilled until after that assertion, because a completed stream re-renders the panel at once;
  - the `loading` response keeps the select disabled with the loading copy, then the list appears;
  - the unknown entry's "Pull anyway" path.

  The whole settings lane must stay green with the conftest default seam.
- **No behavior-test spec.** The real-environment observation (live registry, real Ollama, a real pull) is the HAT's job, and a behavior spec would hit ollama.com on every run.
- **HAT:** each charter criterion is observed against the operator's real Ollama.
