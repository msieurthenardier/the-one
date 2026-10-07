# Flight Log: Ollama Pull shows the download size first

**Flight**: [Ollama Pull shows the download size first](flight.md)

## Summary
Sortie 01, in flight (execution started 2026-10-07). Leg 1 `pull-size-flow` completed and committed after review; leg 2 (HAT) next. Charter agreed with the operator on 2026-10-07; the flight spec was approved by the operator on 2026-10-07 after two Architect design-review cycles.

---

## Leg Progress

### pull-size-flow
**Status**: completed
**Started**: 2026-10-07
**Completed**: 2026-10-07

#### Changes Made
- **Backend:** new `the_one/llm/ollama_library.py` (page parser, `/api/tags` merge, validation, manifest fetch and status mapping, shared size map with disk cache `{data_dir}/ollama-sizes.json`, single-flight detached fill with 8 s bounded wait, 45 s budget, early stop, `shutdown_drain()`, the `THE_ONE_OLLAMA_LIBRARY_TEST_JSON` seam, `_reset_for_tests`). `api.py`: the old cache, URLs and fetcher removed; thin `GET /api/ollama-library/search` (new shape, model-name sort) and `GET /api/ollama-library/size`. `app.py`: `ollama_library.shutdown_drain()` at the top of the lifespan shutdown block. `ollama_api.parse_library_html` and `_LIBRARY_LINK_RE` removed (`grep` for the four old names returns nothing).
- **Frontend:** `provider-models.js` rebuilt around `renderOllamaModels(provider, container)`: flat DOM-built list with statuses, loading loop (2 s), Pull label and `admin-pf-pull-size` status line, size re-check, `App.ui.modal` confirmation, decimal `formatSize` panel-wide, VRAM line via DOM APIs, `startPull(entry)` from the modal's `onClose` with the `isConnected` guard and focus to the progress Cancel; fixes: no double-escape, Pull disabled after Cancel with empty selection, Refresh disabled during a pull. `admin.css`: `.admin-pf-pull-size`.
- **Tests:** new `tests/test_ollama_library.py` (88), rewritten `TestOllamaLibrarySearch` (15 in the `-k OllamaLibrary` selection), `TestParseLibraryHtml` removed, fixture gained gemma4 (cloud, `e2b`/`e4b`/`31b`) and kimi-k3 (cloud, untagged); new `tests/browser/test_flow_provider_ollama_pull.py` (11); `tests/browser/conftest.py` default seam catalog (`OLLAMA_LIBRARY_TEST_CATALOG`, set before `extra_env`); `tests/test_ui_guards.py` baseline pruned by the two entries.
- **Docs:** `docs/ui-testid-registry.md` (nine rows), `the_one/agents.md` "Ollama pull catalog", `SECURITY-MODEL.md` "Ollama library and registry fetches", `.env.example`.

#### Verification
- Python 3.11 import check: `~/.local/bin/uv run --python 3.11 --with-editable . python -c "import the_one.interfaces.web.api; import the_one.llm.ollama_library; print('py311 import ok')"` printed `py311 import ok`.
- `tests/test_ollama_library.py`: 88 passed. `tests/test_provider_api.py -k OllamaLibrary`: 15 passed. Both files together: 275 passed, five consecutive runs.
- Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_mechanism_testids`, `test_nav_guard_static`, `test_run_tests_lanes`): all passed.
- Unit suite (`-m 'not browser and not live and not pixel and not requires_bwrap'`): 5570 passed, 10 skipped (the expected count), 11 failed. The same 11 fail on a clean `main` worktree (see Anomalies): `test_credential_gate::test_exempt_paths_are_get_only_on_the_real_app`, 5 in `test_mcp_integration`, 4 in `test_openrouter_wire_level`. A first full run showed 12 failures; the 12th did not recur in a second full run or in five repeats of the changed unit files.
- Browser (all with `THE_ONE_TEST_NETNS=1`): new file 11 passed; settings lane 214 passed (6m50s); shared lane 465 passed (12m14s). No browser test reaches ollama.com (the namespace has no internet).
- `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/`: clean.

#### Notes
- Divert check holds: no change to DD4.
- The cache-key normalisation (`name:latest`) is used for every lookup, including the seam's size route.
- `cloud` flag source: the page badge flags every entry of a model; an `/api/tags` listing flags only that exact `name:tag`.
- An early stop sets a 300 s in-memory cooldown (`_cooldown_until`) so a failing registry is not re-requested on each panel render; the spec says the rest "stay unsettled", and without a cooldown every search would immediately start another fill. Recorded under Deviations.

---

## Decisions

### Charter decisions (2026-10-07, operator)
**Context**: Open questions put to the operator at charter time.
**Decision**:
- List variants (name plus parameter size) as well as the bare name.
- Every pull asks for confirmation, naming its size; there is no size threshold.
- If the size can't be fetched, Pull asks "Pull without knowing its size?" instead of blocking.
**Impact**: Success criteria 2–4 as written in the charter.

### Design choices (2026-10-07, operator)
**Context**: Two mockups were compared on the canvas "Ollama Pull sizes" (https://claude.ai/artifact/TCDURcrSPbtCcHN63irs7j): A, one flat list with sizes; B, model then variant.
**Decision**:
- Option A, a flat list, with every entry showing its size, for example `gemma4:31b (20.4 GB)`.
- Cloud-only models are greyed out as not downloadable, and support for them is a later sortie.
- First load waits behind a clear message, with no progressive fill.
- A HAT leg is included.
**Impact**: DD1, DD3, DD4 and leg 2.

### Design review, cycle 1 (2026-10-07, Architect)
**Context**: The Architect (Opus) reviewed the first spec. The assessment was "approve with changes"; no redesign was needed, and every Citation Audit row re-checked held.
**Decision**: All issues were folded into the spec:
- the DD9 sort now agrees with DD1;
- DD4 gained single-flight via a shared task, an in-memory `unknown` for 300 s, an early stop, partial persistence and a shutdown cancel;
- DD6 now guards on the render's own controls, passes the entry into `startPull`, moves focus to Cancel, and passes the provider object through;
- the unit-test rewrite and `_reset_for_tests` hook are specified;
- the DD3 cloud signal comes from the library badge or `/api/tags`;
- DD5 accepts a single segment only;
- an entry-scoped parser replaces `parse_library_html`;
- citation fixes.

The designer answered the Architect's three questions:
- Refresh keeps the size cache; instead, a new size route re-checks the entry on Pull.
- `missing` lives 1 day.
- `/api/tags`-only names sort after the page's tags.

Two suggestions were adopted: the decimal formatter is used panel-wide, and the seam is documented in `.env.example`.
**Impact**: The changes were substantive (a new route, a lifespan hook, the parser replacement), so a second review cycle was run.

### Design review, cycle 2 (2026-10-07, Architect)
**Context**: The Architect (Opus) reviewed the revised spec. The assessment was "approve with changes": the cycle-1 items were addressed and none was mis-addressed, but the revision introduced two high issues.
- **TypedDict:** a `TypedDict` route annotation crashes `api.py` at import on Python 3.11, which CI and the Windows build use.
- **Shutdown:** the lifespan cancel runs only after uvicorn's request drain, so it could not unblock `make down`.
**Decision**: All issues were folded into the spec. The route annotation stays `dict[str, Any]`.
- **DD4:**
  - a detached fill task, awaited through `asyncio.shield` with a bounded wait of about 8 s;
  - a `loading` response with a re-request loop;
  - `shutdown_drain()` in `app.py`'s lifespan;
  - per-key writes into one shared map, and `unknown` never overwriting a known entry;
  - pruning only after a successful page parse;
  - a per-fill client and semaphore;
  - early stop on transport, 403 or 429 failures;
  - unsettled entries not negatively cached;
  - persisting the library listing.
- **DD6:** the plumbing points at the internal callers; Pull is re-enabled before the modal opens; the live-controls guard also runs before opening; a 4xx is an error, not `unknown`.
- **DD8:** the VRAM sink is rebuilt with DOM APIs.
- **DD9:** a plain-string 422; the bare name is echoed.
- **DD5:** `re.fullmatch`.
- **Leg 1:** a full live cold fill is measured early, as the Divert check.

The designer answered cycle 2's four questions:
- **Shutdown:** a bounded wait with re-request, not a global `timeout_graceful_shutdown`.
- **Failed re-check:** a cached `ok` within its TTL is shown in the modal.
- **Bare names:** echoed as requested.
- **Budget-unsettled entries:** retried on the next fill, not negatively cached.

Of the suggestions, these were adopted: port the parser tolerance tests, one client per fill, a 5 s re-check timeout, `aria-live` on the status line, re-run only `loadLibraryOptions` in the cloud/missing branch, disable Refresh during a pull, and persist the library listing. This one was declined: splitting the leg into backend and frontend. That would be a split by task type, and the agentic workflow reviews once per flight, so it adds no review checkpoint.
**Impact**: The maximum of 2 design-review cycles is reached. The spec goes to the operator for approval.

---

## Deviations

### Early-stop cooldown (pull-size-flow)
**Planned**: after an early stop the rest of the entries "stay unsettled and are not requested" (DD4).
**Actual**: the same, plus a 300 s in-memory cooldown (`_cooldown_until`) during which `search` starts no new fill.
**Reason**: unsettled entries are not negatively cached, so without it every panel render would start a fresh fill against a registry that just failed its first 16 requests.
**Impact**: none on any DD; the entries read `unknown` meanwhile.

### Environment: no repo `.venv` (pull-size-flow)
**Planned**: run tests with the repo `.venv` (Python 3.12).
**Actual**: the repo had no usable `.venv` (system `python3` 3.12 has an old `mcp` that cannot import the app). Running the leg's mandated `uv run --python 3.11 --with-editable .` created a Python 3.11 `.venv` in the repo root (gitignored, no pytest). Deleting it was denied by the permission classifier, so it was left in place and tests were run from a throwaway 3.12 venv in the session scratchpad (`pip install -e ".[all-llms,dev]"`).
**Impact**: `make test-unit` (which hardcodes `.venv/bin/python`) will not work until the Flight Director removes or rebuilds `.venv`. No tracked file is affected.

---

## Anomalies

- **Pre-existing unit failures on `main`** (reproduced in a clean `main` worktree, not caused by this leg): `tests/test_credential_gate.py::TestExemption::test_exempt_paths_are_get_only_on_the_real_app` (`/api/oauth/callback` not registered on the real app in this environment), 5 tests in `tests/test_mcp_integration.py` (stdio), and 4 in `tests/test_openrouter_wire_level.py` ("missing 'data' key"). Likely a dependency-version difference in the fresh venv; worth a squawk.
- The `uv run` side effect on `.venv` (see Deviations).

---

## Session Notes

---

## Flight Director Notes

### Execution start (2026-10-07)
- **Setup:** loaded the crew file `.flightops/agent-crews/leg-execution.md` (all sections present). Branch `sortie/01-ollama-pull-download-size` created from `main` at `f770947`. Status `ready` → `in-flight` (ARTIFACTS.md defines no transition-time handling).
- **Legs:** 2 in total.
  - `pull-size-flow` is autonomous.
  - `hat-and-alignment` is interactive and guided by the Flight Director.
- **The leg 1 Divert check** was run by the Flight Director during leg design: a throwaway script in the session scratchpad, not committed and not project source.
  - **Results:** 445 manifests in 8.0 s, and 7.6 s on a re-run, at concurrency 16. 430 × 200 and 15 × 404 (13 cloud-badged, 2 not: `wizardlm` and `qwen3.8-flash-next`). **No 403, 429 or transport errors.**
  - **Prerequisites:** the per-leg checks are met. `llama3.2` tags return 200 and `kimi-k3:latest` returns 404; the page still carries size tags and the cloud badge.
  - **Verdict:** no Divert, so DD4 stands.
  - **Side observations:** the cold fill plus the page fetch (about 10 s) exceeds the 8 s bounded wait, so the `loading` path will be exercised on a real first load. The largest entry is `cogito-2.1:671b` at 1,342.3 GB.
- **Leg 1 tiered HIGH.** It changes:
  - cache/freshness behaviour (a disk cache with TTLs);
  - a shared interface with existing consumers (the search route's response shape);
  - a lifecycle hook (lifespan shutdown);
  - a security-sensitive surface (outbound fetches built from parsed names).

  So it runs the per-leg Developer design review. That review checks the leg artifact against the code, not the design, which two Architect cycles already settled.
- **One design clarification at leg design.** DD6's "cached `ok` used when the re-check is `unknown`" is implemented server-side: the size route returns the shared map's entry after recording, and `unknown` never overwrites a known entry within its TTL. The size route's shape stays exactly DD9's `{name, size, status}`.

### Leg 1 design review (2026-10-07, Developer, Sonnet)
- **Assessment:** "approve with changes". There were no high issues: 4 medium and 4 low, plus suggestions. All were applied to the leg artifact.
  - **Seeding:** the test reuses `_seed_ollama_provider`.
  - **Loading and 4xx cases:** driven by `page.route`. The seam stays stateless, with its shape pinned in AC8.
  - **Modal:** the testid placement and action values are spelled out, the order of focus restore then `onClose` is stated, and a re-render falling back to `#main-content` is accepted.
  - **CSS:** an `admin.css` step for the status line.
  - **Guards:** the exact baseline lines to prune and keep, and testids as single-quoted literals with Surface `admin`.
  - **Call sites:** listed by line.
  - **Python 3.11 check:** `uv` with cpython-3.11.14 is installed, so the check is mandatory with no fallback.
- **The designer's answers:**
  - the modal names `new URL(base_url).host` (`localhost:11434`), not the `/v1` URL;
  - `page.route` is used for the loading case, not a `loading_polls` seam field. A stateful seam would leak between tests on the shared app.
- **No second review cycle.** Every item was medium or low and applied as specified. The two answers settle ambiguities the review raised; neither changes the backend design or contradicts a DD. Leg status → `ready`.

### Leg 1 landed; the repo `.venv` was replaced (2026-10-07)
- **What happened:** the Developer's AC7 check, `uv run --python 3.11 --with-editable .`, ran inside the project, so uv rebuilt the repo's `.venv` as Python 3.11.14. The pre-existing 3.12 dev venv was destroyed: the Flight Director had used `.venv/bin/python` earlier this session. The new venv was created at 14:55 and has no pytest.
- **What the Developer did:** it tried `rm -rf .venv`, the permission classifier denied it, and it ran the tests from a scratch 3.12 venv instead.
- **Its report** is 5570 passed, 10 skipped and 11 failed. It calls the failures pre-existing, because they reproduce on a clean `main` worktree under the same scratch venv. They are in `test_credential_gate`, `test_mcp_integration` and `test_openrouter_wire_level`.
  - **The Flight Director's read:** they are likely a dependency-resolution difference in the scratch venv, not real regressions. That is unverified until the repo venv is rebuilt.
- **Decision:** the denied deletion is not re-attempted by the Flight Director, since that would be permission laundering. It is raised to the operator, and the flight review is held until the venv question is settled.
- **Lesson for the debrief:** a uv cross-version check must use `--no-project` or a scratch `UV_PROJECT_ENVIRONMENT`, never the project's own `.venv`.
- **Resolution (operator-approved, 2026-10-07).** The operator said "go ahead and rebuild with 3.12".
  - **Rebuild:** `rm -rf .venv && uv venv --python 3.12 .venv`.
  - **First install was unlocked:** `uv pip install -e ".[all-llms,dev]"` resolved the *latest* packages (`openai` 3.26.0 against the lock's 2.32.0). `make test-unit` then gave 5576 passed, 10 skipped and 5 failed (`test_credential_gate`'s oauth-callback route check and 4 `test_openrouter_wire_level`).
  - **Fix:** `uv sync --all-extras --frozen` restored the locked versions (`openai` 2.32.0, `fastapi` 0.136.0). Both failing files then gave 87 passed.
  - **Verdict:** the Developer's "11 pre-existing failures" were dependency drift in its unlocked scratch venv, not regressions and not pre-existing on a locked environment. No squawk is needed for them.
- **The operator decided to move the project to Python 3.12 permanently.** Logged as squawk 0135 (servicing, routine), deferred until this sortie lands. It covers the CI images, the Windows choco toolchain, the GitHub workflows, `requires-python`, ruff's `target-version` and `uv.lock`.
- **Locked environment, full run:** `make test-unit` gave 5580 passed, 10 skipped and 1 failed, `tests/test_kb_watcher.py::TestStopAndDrain::test_drain_three_live_entries_under_a_second`.
  - That class passed 5 of 5 in isolation, and this sortie touches no knowledge code.
  - The test asserts a wall-clock `< 1.0 s`, so this is a load flake. Logged as squawk 0136 (routine), deferred.
  - It is probably also the Developer's unidentified "12th failure".
  - Verdict: the unit tier is clean for this leg.

### Flight review, cycle 1 (2026-10-07)
- **Reviewer tier: Sonnet.** The diff touches a security-sensitive surface: outbound fetches whose URLs are built from parsed names (DD5's validation and fixed host) and SECURITY-MODEL.md.
- **Fixes (Developer, review items 1-3).**
  - `_load_disk` now validates every cached listing name and size-map key through `_key`/`split_model`, dropping invalid ones with one logged warning (DD4: a hand-edited `ollama-sizes.json` degrades, never 500s). Test: `TestCache::test_invalid_names_in_cache_file_are_dropped_not_raised`.
  - `_settle` cancels and awaits any not-done child `_fetch_one` tasks in a `finally`, so a `shutdown_drain` cancel of the fill leaves no task behind when the client closes. Test: `TestShutdownDrain::test_no_child_task_left_pending_after_drain`.
  - SECURITY-MODEL.md's outbound-fetch note reworded: manifests are fixed-host with no redirects; the listing fetches (`/library`, `/api/tags`) use fixed URLs, follow redirects, and are only parsed (every name and tag validated before a manifest URL is built). Module docstring says "fixed URLs". `agents.md`'s "Ollama pull catalog" never made the loose claim, so it is unchanged. Code redirect behaviour untouched.
- **Fixes, cycle 2.** `_load_disk` can no longer raise: parsing moved to a pure `_parse_disk` (committed to the maps only on success), any `Exception` from the file (incl. `RecursionError`) logs one warning and leaves no disk cache, and a per-entry `_timestamp` guard drops non-finite, negative or overflowing `fetched_at` without losing the rest; module docstring states the fixed-host/no-redirect vs followed-redirect split; tests: `TestCache::test_corrupt_cache_shapes_never_raise` (15 shapes, search + size), `test_bad_timestamp_drops_only_that_entry`, `test_unparseable_file_logs_one_warning_and_stays_empty`.
- **Review result:** cycle 1 confirmed the flight. Cycle 2 was a scoped re-review of the nit fixes and was NOT confirmed: corrupt-file raise paths (`OverflowError`, `RecursionError`) remained through `size()`, and the docstring wording was missing. Cycle 3 was a scoped re-review and is **confirmed** (`[HANDOFF:confirmed]`), within the 3-cycle limit.
- **Accepted as non-blocking (cycle 3).** These only arise from a hand-edited cache file in the app's own data directory, which is trusted local state, and none can make a route raise:
  - a cached negative `ok` size;
  - an `ok` entry with no size (the panel shows "size unknown");
  - a far-future `fetched_at` never expiring;
  - listing names not de-duplicated or trimmed after normalisation;
  - no cache-file size cap.

  These are not logged as squawks: the app writes this file itself, and DD4's requirement ("never a 500") holds. They can be revisited if the cache ever reads data from outside the app.
- **Leg 1 → `completed`.** All 16 acceptance criteria are ticked, and the flight spec's leg list is checked off. Commit next, then a draft PR.
