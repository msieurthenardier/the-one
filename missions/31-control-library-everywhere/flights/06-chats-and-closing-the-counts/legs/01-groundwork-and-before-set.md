# Leg: groundwork-and-before-set

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Prepare the flight with no product behaviour change:
- the chat and model-picker surfaces in `scripts/ui_capture.py`, on a seed pinned against the clock and the zone, and the before captures;
- the five `innerHTML = ''` clears in `chat.js` replaced, bringing the sink allowance to zero;
- the allowance bookkeeping reset to Flight 6's start;
- the lanes: a quiet-host re-measure, `chats` split, squawk 0271's MCP test-file split and an `mcp` lane split;
- squawk 0249's test fix.

## Context
- **Flight decisions:**
  - DD2 (groundwork) and DD12 (captures);
  - DD13 (standing rules) and DD15 (lanes);
  - squawks 0249, 0259 and 0271.
- **Order matters.** The before set is taken while `git diff main -- the_one/` is still empty. Only then does the sink change land.
- **The capture tool today** (`scripts/ui_capture.py`, 2,320 lines):
  - **Surfaces** are `Surface(name, hash, ready, description, prepare, shot, stubs, skipped, tz, restore, widths, needs_mcp)` entries (`:254-271`), appended to `SURFACES` (`:784`). `skipped` records a state the tool cannot produce, with its reason.
  - **The environment is already pinned:**
    - the clock: `page.clock.set_fixed_time(FIXED_NOW)` (`:2042`), with `FIXED_NOW = 2026-03-01 12:00 UTC` (`:85`);
    - `DETERMINISM_JS`;
    - the browser zone per surface (`Surface.tz`) and the seed's operator zone (`SEED_ZONE`, `_put_time_settings` `:632`);
    - the plan-token stamp (`:86-87`).

    `set_fixed_time` (not `install`) leaves timers running, which streaming needs.
  - **Seeding** is `seed()` (`:1692`), `seed_tabs_agent()` (`:1729`), `seed_library()` (`:1788`), `seed_mcp()` (`:1852`) and `seed_settings()` (`:1966`), through the API with the instance's credential. `seed_mcp()` runs only when a `needs_mcp` surface is selected.
  - **Stubs:** `_ollama_stubs` (`:276`) for the models panel; `_stub_test` (`:286`); `_stub_signin` (`:1234`).
  - `maybe_reexec_in_netns()` (`:2137`).
  - **Refusals:** ports 8484 and 8485 and anything below 8490; the default or a configured data dir; an `--out` inside the repo.
  - **Chat:** the tool has no chat surfaces. `chat-consent-link` is skipped.
- **The planning survey's driver** is the starting point: `$HOME/.cache/the-one-ui-capture/m31-f6-planning/f6/driver.py` (seed) and `scenes.py` (states), outside the repo.
  - It seeds mock providers (rich markdown with thinking, streaming at 60 × 400 ms, slow at 60 s), an unreachable `openai-compatible` provider and a stubbed Ollama provider.
  - Its other seed: 5 agents (one with a long name), sessions in every date group, a Discord session with peers and an operator-only reply, a deleted-agent session and an empty one.
  - It injects WebSocket frames (`page.route_web_socket`) for the sign-in block.
  - Read it for what worked, and port it into the tool. Never import from the cache directory.
  - Its sessions were dated from the real clock. The tool's must be dated relative to `FIXED_NOW` in `SEED_ZONE`.
- **The sinks** (`tests/test_ui_guards.py`):
  - `HTML_SINK_ALLOWANCE = {"areas/chat.js": 5}` (`:118-120`), `SINK_TOTAL = 5` (`:144`);
  - `SINK_START_FILES = {"areas/chat.js", "areas/studio/mcp-server-editor.js"}` (`:147`), `SNIPPET_START_FILES = {"areas/studio/mcp-server-editor.js"}`;
  - `test_chat_area_has_no_baselined_sink` (`:511-519`) and its docstring.
  - The five sites are `chat.js:215` (`attachmentsEl.innerHTML = '';`), `:685`, `:743`, `:924` (`messagesEl.innerHTML = '';`) and `:1647` (`loadingMsg.innerHTML = '';`, followed by a `textContent` write).
- **Ownership** (`tests/_ui_ownership_allowance.py`):
  - `OWNERSHIP_ALLOWANCE` has 25 rows / 36 uses;
  - `START_ROWS` still lists the Flight 5 start set ("as of M31 F5 L01", `:47`);
  - `MOVES` is empty.
- **Lanes** (`scripts/run-tests.sh`):
  - `LANE_LIST` / `CANON_LANES` (`:57-58`) and `BUDGET` (`:64-78`);
  - `chats_pat` (`:178-180`), `mcp_pat` (`:192`);
  - `resolve_lane` (`:244`) and the `shared` complement (`:261`);
  - the `chat` alias, and `tests/test_run_tests_lanes.py` (`LANES`, disjointness, the union, the budget table);
  - CLAUDE.md's lane bullets and budget table.
- **Squawk 0249.** `tests/browser/test_oauth_modal_flow.py:188` `test_second_auth_required_event_navigates_popup_to_consent_url` clicks "Log in" with no stub.
  - **The race:** the real `POST /api/oauth/start` answers 404 for the made-up source (`api.py:5001-5004`). `abandon()` (`chat.js:1306-1309`) then closes and drops the popup. When the 404 beats the test's second emitted frame, the popup is never navigated.
  - **The false pass:** `:244` `test_popup_closes_on_auth_resolved_event` passes even if `auth_resolved` closed nothing, because `abandon()` closes the popup anyway.
  - **Possibly racy too:** `:151` `test_button_click_opens_popup_with_window_open_features` is unstubbed as well.
  - **The fix pattern:** `_stub_oauth_start(page)` (`:276`) already exists.
- **The MCP editor test file** (`tests/browser/test_flow_studio_mcp_editor.py`, 4,920 lines, 149 tests) carries section banners by concern. Examples:
  - `:1614` resp.ok;
  - `:1680` the stdio runtime dropdown;
  - `:2016` sortie 04 sign-in;
  - `:2272` onward: the lifecycle helpers and poll;
  - `:2678` / `:2862` chip lists and fields;
  - `:3128` onward: key/value;
  - `:3594` connection status;
  - `:4039` server info.

  Its module-level helpers (`_seed_mcp_source` `:40`, `_get_source`, `_list_sources`, `_open_editor` `:2068`, `_open` `:3629`, …) are shared across sections. Lanes are basename globs over `tests/browser/test_*.py`, so the split stays flat files plus a `_`-prefixed helper module (the `_nav.py` / `_lists.py` convention), not a package.

## Inputs
- The branch `flight/06-chats-and-closing-the-counts` from `main` at `3b3d42a`, with the flight's planning artifacts uncommitted.
- WebKit userland and `THE_ONE_TEST_NETNS=1` working (re-verify first).

## Outputs
- **`scripts/ui_capture.py`:**
  - **`seed_chat()`,** run only when a new `needs_chat` surface is selected (mirroring `needs_mcp`), so existing surfaces and their comparability with earlier sets are unchanged. It seeds:
    - the survey's mock providers;
    - an unreachable `openai-compatible` provider at a dead loopback port (never 8484, 8485 or 8491);
    - agents, one with a long name;
    - sessions through `POST /api/chat/sessions`, with `updated_at` values **relative to `FIXED_NOW`** so that each group shows in `SEED_ZONE`: Today, Yesterday, Last 7 days, Last 30 days and Older.

    It also seeds a connector-platform session with a peer and an operator-only reply, a deleted-agent session (an `agent_name` with no agent) and an empty session.
  - **The chat and model-picker surfaces** (DD12), one `Surface` per state, at 1280 and 1024 in both themes:
    - Chats empty, the guidance state, the pending new chat (normal and long name), and the agent picker (open, search, no match);
    - joined chats: rich markdown (top, middle and bottom, with the disclosures open), long names, peer, deleted agent, empty;
    - the Chats list: row hover, delete armed;
    - the composer: focused, multi-line, staged images, queued;
    - telemetry, resting and expanded;
    - live states: streaming with Stop visible, the thinking indicator, after Stop, an agent error;
    - the code-copy toast; the sign-in button and consent block (injected frames);
    - Jump to open;
    - the Ollama panel (`ollama` stubs), Pull progress (a stubbed stream), the generic provider models list;
    - the agent editor General tab and the provider editor (for D7), and a toast from the agent editor and the provider editor.
  - **Skipped states.** A state the shared seed cannot produce (for example the guidance state, which needs no agents) uses `Surface.skipped` with its reason, or a surface-level `prepare` that stubs the store routes. A guidance capture must not mutate the shared seed.
  - **A pre-navigation hook.** `capture_one` (`:2007-2095`) has only `prepare`, which runs after `goto` and the `ready` wait. A socket route must be installed before `goto`. So `Surface` gains a `setup` callback, called after `set_fixed_time` and the provider routes and before `goto`. It holds the `page.route_web_socket` handler and any `/api/oauth/start` stub, and may return a holder for the `ws` object. Playwright is 1.58.0, so `route_web_socket` and `connect_to_server()` are available; the survey's `login_block` proves the pattern. **One shared socket-frame helper**, a fixed frame list plus `connect_to_server`, serves every live and sign-in surface.
  - **Live states come from scripted socket frames, never real sends** (FD decision at the leg's design review). The states are streaming with Stop visible, the thinking indicator, after Stop, an agent error and queued. Each surface connects to the real server for the join and its history, then injects a fixed frame sequence: chunks, `thinking`, `system`, `cancelled`, `done`, and so on.
    - Nothing is sent to the agent, so no session's `updated_at` is re-stamped with the real clock (`repositories.py:2685` stamps `now_iso()` on every save), and no session is created.
    - Each surface's pixels must be identical across two runs, or every differing region masked under the existing mask rule. Never capture mid-stream on a timer.
  - **A surface that does change server state** (delete armed, a toast after a Save) restores it through `Surface.restore`, which runs after every capture. A seeded Chats-list surface must be unaffected by any surface captured before it.
  - **The retention purge.** `chat_history_retention_days` defaults to 30. Sessions dated against `FIXED_NOW` (2026-03-01) are months older than the scratch server's real clock, so a purge sweep would delete them. The startup sweep runs on an empty database, before `seed_chat`. For the chat surfaces, the scratch instance starts with a large `THE_ONE_PURGE_CHECK_INTERVAL_SECONDS` (`app.py:1362-1372`, for example 30 days), so no later sweep runs during a capture. `seed_chat` asserts that every seeded session is still listed after seeding.
  - **The existing skipped `chat-consent-link` surface** (`:980`) is replaced by the new sign-in consent-block surface under the same name, now produced, not skipped. `mcp-consent-link` is unaffected.
  - **The deleted-agent session** uses an `agent_name` that never existed ("Ghost agent", as in the survey). The foreign key on `chat_sessions.agent_name` was dropped, so the POST succeeds.
  - **The manifest records the seed's session ids and their expected group,** so the groups criterion can be checked mechanically.
  - **Run-to-run text masked:** times, loopback ports, scratch paths.
- **The before set** at `$HOME/.cache/the-one-ui-capture/m31-f6-before`, outside the repo, taken **before** any file under `the_one/` changes. The flight log records the count, the command and the manifest's git SHA.
- **The sinks** (after the before set):
  - the four clears at `chat.js:215`, `:685`, `:743` and `:924` become `replaceChildren()`;
  - `:1647` is deleted, since the next line's `textContent` write already clears it;
  - `HTML_SINK_ALLOWANCE = {}`, `SINK_TOTAL = 0`, `SINK_START_FILES` and `SNIPPET_START_FILES` empty;
  - `test_chat_area_has_no_baselined_sink`'s docstring updated: no chat sink remains, clears included. Its assertions tighten to "no sink of any kind in `areas/chat*`".
- **Ownership:** `START_ROWS` is rewritten to the 25 current `OWNERSHIP_ALLOWANCE` keys, with its comment updated to "as of M31 F6 L01". `TOTAL_USES` stays exact, and `MOVES` stays empty.
- **Squawk 0271: the MCP editor test file split by concern** into flat files with a shared helper module:
  - `tests/browser/_mcp_editor.py` holds the module-level helpers that more than one file uses;
  - `test_flow_studio_mcp_editor_*.py` files each hold one concern (the leg's Developer proposes the grouping from the section banners and records it in the flight log), each under about 1,200 lines.
  - **The grouping:**
    - `mcp` takes create, fields, chips and key/value;
    - `mcp-connection` takes sign-in, lifecycle and poll, connection status, server info, and the tail (`:4293-4920`, the Batch B4 review fixes and Leg 10 controller tests, which use helpers from every group).

    The Developer names the files from that clustering and records the mapping in the flight log.
  - **The helper module rule.** Every non-test module-level name (helper, constant, fixture) used by more than one new file moves to `_mcp_editor.py`; the others stay with their single user. There are about 69 module-level names. Heavily shared ones include `_seed_mcp_source`, `_get_source`, `_list_sources`, `_OK_TOOLS`, `_seed_oauth_source`, `_stub_signin_routes`, `_open_editor`, `_install_counter`, `_count`, `_hold_requests`, `_wait_held`, `_fake_open`, the `_kv_*` family, `_open_source`, `_http_source` and `_add_chip`. `_CLOCK` (unused) may be dropped, and the drop is recorded.
  - **The file headers.** Each new file and the helper starts with the source file's header: `# ruff: noqa: E501` (inline JS) and `from __future__ import annotations`. Imports are explicit (`from browser._mcp_editor import ...`, matching `from browser import _lists, _nav`), never `*`.
  - **Every test keeps its exact name and body,** apart from the imports. The file has **149 test functions and 178 collected items** (11 parametrizations). The `--collect-only -q` node ids, with the path stripped, must be identical before and after.
  - `test_flow_studio_mcp_editor.py` is deleted. The live comments that name it are updated to the new file: `tests/browser/conftest.py:37`, `:43` (including `::test_create_stdio_source`), `tests/browser/test_flow_agent_tabs.py:325`, `tests/browser/test_flow_studio_knowledge_inventory.py:237`, and CLAUDE.md. After that, a grep of `tests/`, `scripts/`, `docs/`, `ci/`, CLAUDE.md and `the_one/agents.md` for the old name finds only history records (flight logs, squawks, run logs, behavior-run logs), which stay as written.
- **Lanes:**
  - **`chats` splits.** `chats-transcript` is an explicit list (`chats_transcript_pat`): `test_flow_chat_composer.py`, `test_flow_chat_image_attach.py`, `test_flow_chat_queued_render.py`, `test_flow_chat_visibility_distinction.py`, `test_flow_chat_peer_attribution.py`, `test_flow_chat_thinking_disclosure.py`, `test_flow_chat_time_zone.py`, `test_flow_markdown_chat.py`, `test_flow_streaming.py`, `test_flow_context_overlay_thresholds.py` and `test_flow_usage_restore.py`. `chats` is the chats globs minus that list, through a new `chats_files()` helper like `agents_files()` and `settings_files()`, so a new `test_flow_chat_*` file lands in `chats` by default. The `chat` alias maps to the full `chats_pat` expansion (both lanes).
  - **`mcp` splits into two lanes** along the new files: `mcp` (create, fields, chips, key/value) and `mcp-connection` (connection status, sign-in, OAuth poll, server info). The final grouping follows the file split. `mcp_pat` and the new lane's pattern are explicit lists.
  - **Bookkeeping, together:**
    - `scripts/run-tests.sh`:
      - `LANE_LIST`, `CANON_LANES`, `BUDGET`, the patterns, `resolve_lane` and the help text;
      - `agents_files()`, which must subtract the new `mcp-connection` list, or its `test_flow_studio_mcp_editor_*` files land in `agents` through `test_flow_studio_*`;
      - the `chats|chat` and `system|studio` alias handling;
      - the `shared` complement is fine as it is, since it unions `chats_pat` and `studio_pat`.
    - `tests/test_run_tests_lanes.py`:
      - the `LANES` tuple;
      - the hard-coded lane string in `test_list_with_unknown_lane_exits_2_naming_every_lane`, which must match the new `LANE_LIST` exactly;
      - new by-file tests for the `chats`/`chats-transcript` and `mcp`/`mcp-connection` pairs, like `test_settings_tools_lane_is_the_built_in_tools_files`.
    - **CLAUDE.md:** the lane bullets, aliases and budget table, plus the lane counts at about `:367`, `:428` ("twelve named lanes") and `:430` ("thirteen lanes … twelve named lanes"). With two new lanes there are fifteen lanes and fourteen named ones.
    - `the_one/agents.md:179` (the lane summary) and `ci/tasks/browser.yml:10-11` ("thirteen canonical lanes now"; a comment, since the CI task runs every lane through `--parallel 1`).
  - **Budgets** come from run 2 below (measured lane time plus 25%, rounded up to 30 s). Lanes that did not split keep their budget unless they moved more than 15% or ran over 1.3×.
- **Squawk 0249:**
  - stub `POST /api/oauth/start` with `_stub_oauth_start(page)` in the three unstubbed tests, each test's assertions unchanged:
    - `:188` is the racy one;
    - `:244` needs the stub so its falsification means something (it cannot otherwise tell `auth_resolved`'s close from `abandon()`'s);
    - `:151` only asserts the synchronous `window.open`, so it is not racy. Stub it for consistency, with that reason in a comment.
  - confirm that nothing in `chat.js` reads `consent_url` from the `/api/oauth/start` response, so the stub's `{}` body is safe (the stubbed tests from `:300` already rely on this);
  - one deterministic demonstration of the root cause, recorded in the flight log with its output: the unstubbed test made to fail on demand, for example by holding the second emitted frame until the 404 has been answered;
  - a falsification check that the sibling now fails when `auth_resolved` closes nothing: a temporary local edit to the global popup close, reverted, with `git diff` clean afterwards.
- **Squawk 0259:** closed with its corrective action (this leg's runs and the split) and verification. Its status stays `in-progress` until the flight's commit, which the flight-end Reviewer signs off.
- **The flight log:** this leg's entry, with the run 1 and run 2 `PARALLEL_RESULT` lines, start loads and per-lane times, and a Flight Director Notes line.

## Acceptance Criteria
- [ ] **The before set is taken while `git diff main -- the_one/` and `git status --porcelain the_one/` are both empty.** The manifest's git SHA, the empty `the_one/` status and a hash of the uncommitted `scripts/ui_capture.py` are recorded in the flight log.
- [ ] `scripts/ui_capture.py --list` shows every new chat and model-picker surface with a description. Skipped ones show their reason.
- [ ] **A capture run** under `THE_ONE_TEST_NETNS=1` writes every new surface at 1280 and 1024 in both themes, with no surface failing.
- [ ] **A second run of the chat surfaces** produces images identical to the first (PIL `ImageChops.difference(...).getbbox()` is `None`), or each differing region is masked by a recorded rule. No instance or fixture process from either run is left alive afterwards.
- [ ] **The sessions land in the right groups** under the pinned clock and zone. Each group (Today, Yesterday, Last 7 days, Last 30 days, Older) shows its seeded row, checked against the manifest's expected placements. A Chats-list surface taken after every live surface still shows the seed unchanged. The FD spot-checks the Chats list, the rich chat, the Ollama panel and one live state.
- [ ] **The safety refusals still hold:** ports 8484, 8485 and below 8490; the default data dir; `--out` inside the repo. `tests/test_ui_capture_safety.py` passes.
- [ ] **The sinks:** the sink tests report zero (`classify_sinks()` through `tests/test_ui_guards.py`; a plain grep also matches comments). `HTML_SINK_ALLOWANCE` is `{}`, `SINK_TOTAL` is 0, and the sink tests pass. The `chats` and `chats-transcript` lanes pass.
- [ ] `START_ROWS` equals the current allowance keys, and `tests/test_ui_ownership.py` passes.
- [ ] **The MCP split:** 149 test functions and 178 collected items across the new files, with node ids identical apart from the path (the collect-only diff). `ruff check tests/` passes on the new files. The `mcp` and `mcp-connection` lanes pass.
- [ ] **Lanes:** `bash scripts/run-tests.sh --lane chats --list` and `--lane chats-transcript --list` together equal the old `chats` list, and `--lane agents --list` contains no `test_flow_studio_mcp_editor*` file. `tests/test_run_tests_lanes.py` passes with the new lanes: disjoint, the union is the suite, every canonical lane has a budget, and the new by-file pair tests pass.
- [ ] **Run 1 (before the lane splits) and run 2 (after)** are quiet-host `--parallel 3` runs with rc=0. A known flake (for example squawk 0249's test in run 1, before its fix) gets an isolated re-run plus a full re-run on a quiet host; the test is never skipped. Their start loads and per-lane times are in the flight log. In run 2, no lane is over budget once the budgets are set. CLAUDE.md's table matches `scripts/run-tests.sh` (a grep step).
- [ ] **Squawk 0249:** the three tests are stubbed and pass. The root-cause demonstration and the falsification check are recorded, with the tree clean afterwards. `shared` passes.
- [ ] **Static and unit gates:** `make test-unit` passes with the expected skip count for this host and mode, after the browser runs and never during them. The static guards pass (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`). `ruff check` and `ruff format --check` pass on `scripts/` and `tests/`.

## Verification Steps
1. `git diff --stat main -- the_one/` and `git status --porcelain the_one/` (both empty), then take the before set:
   `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out $HOME/.cache/the-one-ui-capture/m31-f6-before` (or with the chat and model-picker surfaces selected).
2. Run it again into a scratch directory, and compare the chat surfaces with a short PIL script (in the session scratchpad, not the repo).
3. `.venv/bin/python -m pytest tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_run_tests_lanes.py tests/test_ui_capture_safety.py -q -x --timeout 120`.
4. The MCP collect-only diff:
   `.venv/bin/python -m pytest --collect-only -q -m browser tests/browser/test_flow_studio_mcp_editor*.py`
   before and after, comparing node ids with the path stripped (178 items).
5. **The quiet-host procedure** (both runs):
   - **Check the host first.** `uptime` shows a 1-minute load below about 1.0. `ps -eo pid,user,etime,args` shows no other `pytest`, `run-tests.sh`, `playwright`, `chromium` or `uvicorn` / `the-one serve` processes apart from long-lived idle app instances, each recorded and left alone.
   - **Nothing else runs during a run:** no capture run, no unit suite.
   - **If the host is not quiet,** stop and report `[BLOCKED:host-not-quiet]` with what you found.
   - **The run:** `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`. Record the start load and the `PARALLEL_RESULT` line.
6. `grep -nE "chats|mcp" CLAUDE.md scripts/run-tests.sh` (the two tables agree).
7. `make test-unit`; `ruff check scripts/ tests/`; `ruff format --check scripts/ tests/`.

## Implementation Guidance
1. Re-verify the namespace (`unshare -rn true`) and WebKit (a one-line `sync_playwright` WebKit launch and close, or `scripts/webkitgtk_probe.py`'s launch check). Run no browser test before run 1.
2. **The capture surfaces and `seed_chat()`,** ported from the survey driver, then the before set. Check `git diff main -- the_one/` is empty first. Run the determinism check.
3. **Run 1:** the quiet-host `--parallel 3` run on today's lanes. It is the flight's baseline, and it measures the tree with the before-set capture code only (no product change).
4. **The sinks and `START_ROWS`.** Then the static guards, plus `--lane chats` as a scoped check. A solo lane is fine for correctness, but never for a budget.
5. **Squawk 0249:** the stubs, the demonstration, the falsification check (reverted). Then `--lane shared`.
6. **Squawk 0271:** the helper module first, then move the sections into the new files without editing test bodies, then the collect-only diff.
7. **The lane splits:** patterns, the lanes unit test, CLAUDE.md. Then **run 2** under the quiet-host procedure, and set the new and changed budgets from it.
8. `make test-unit`, ruff, squawk 0259's close-out text and the flight log.

## Edge Cases
- **The guidance state** needs a store with no agents or no providers. Stub the store routes in the surface's `prepare`; never delete seeded agents.
- **A deleted-agent session** makes the drawer fetch the agent's `/context-window` and log a 404. That is defect 0.3, fixed in leg 05a; the capture must tolerate it.
- **`page.route_web_socket`** must be installed before `page.goto`. A socket opened earlier is not intercepted.
- **The streaming mock's `delay_ms`** applies between chunks. A surface that waits for "Stop visible" waits for the state, never a fixed time.
- **A run 2 lane over 1.3× its new budget** is split again or re-balanced in this leg, never carried.
- **`test_flow_studio_mcp_editor.py` may have module-level fixtures or constants** that tests read through globals. Move them to the helper and import them explicitly, never by `*`.
- **The two quiet-host runs take about an hour of host time.** If the host turns noisy mid-run, the reading does not count. Re-run rather than budget from it.

## Files Affected
- `scripts/ui_capture.py`.
- `the_one/interfaces/web/static/js/areas/chat.js` (the five clears only; after the before set).
- `tests/test_ui_guards.py`, `tests/_ui_ownership_allowance.py`.
- `tests/browser/test_oauth_modal_flow.py`.
- `tests/browser/test_flow_studio_mcp_editor.py` (deleted), `tests/browser/test_flow_studio_mcp_editor_*.py` and `tests/browser/_mcp_editor.py` (new).
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `CLAUDE.md`, `the_one/agents.md` (the lane summary only), `ci/tasks/browser.yml` (a comment only).
- `tests/browser/conftest.py`, `tests/browser/test_flow_agent_tabs.py`, `tests/browser/test_flow_studio_knowledge_inventory.py` (comments naming the old MCP file).
- `squawks/0249-oauth-popup-consent-url-flake.md`, `squawks/0259-chats-lane-at-budget.md`, `squawks/0271-split-mcp-editor-browser-tests.md`.
- The flight log.

## Citation Audit
- `scripts/ui_capture.py`, verified by grep at `3b3d42a`: `Surface` `:254`; `SURFACES` `:784`; `seed` `:1692`; `seed_mcp` `:1852`; `_put_time_settings` `:632`; `FIXED_NOW` `:85`; `page.clock.set_fixed_time(FIXED_NOW)` `:2042`; `maybe_reexec_in_netns` `:2137`; `_stub_test` `:286`; `_stub_signin` `:1234`.
- `tests/test_ui_guards.py`, verified (read): `HTML_SINK_ALLOWANCE` `:118`, `SINK_TOTAL = 5` `:144`, `SINK_START_FILES` `:147`, `test_chat_area_has_no_baselined_sink` `:511`.
- `scripts/run-tests.sh`, verified (read): `LANE_LIST` `:57`, `BUDGET` `:64-78`, `chats_pat` `:178`, `mcp_pat` `:192`, `resolve_lane` `:244`.
- `tests/browser/test_oauth_modal_flow.py`, verified (grep): `:151`, `:188` and `:244` (the three tests) and `_stub_oauth_start` `:276`.
- `chat.js` sink lines `:215`, `:685`, `:743`, `:924` and `:1647`: verified by grep at planning, unchanged by `3b3d42a`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27): approve with changes.** Applied in place:
  - **[high] test counts:** 149 functions and 178 collected items, compared by node id;
  - **[high] the pre-`goto` `Surface.setup` hook,** with a shared socket-frame helper;
  - **[high] live states:** scripted socket frames only, never real sends (FD answer to the reviewer's question), so nothing re-stamps `updated_at`; `restore` for surfaces that change state; a Chats-list check after the live surfaces;
  - **[medium] the purge race:** a large `THE_ONE_PURGE_CHECK_INTERVAL_SECONDS`, plus a post-seed assertion;
  - **[medium] the MCP split:** the grouping, including the `:4293-4920` tail; the helper-module rule; the file headers and explicit imports;
  - **[medium] references:** the live comments naming the old file (FD answer: update live comments, keep history records); the lane counts in CLAUDE.md, `agents.md` and `ci/tasks/browser.yml`;
  - **[medium] lane machinery:** `chats_files()`, the aliases, `agents_files()` subtracting `mcp-connection`, the hard-coded lane string in the lanes test, and the by-file pair tests;
  - **[medium] squawk 0249 specifics,** and flake handling in run 1;
  - **the lows:** a WebKit check that actually launches; `git status --porcelain`; the tool's file hash; the sink check through `classify_sinks()`; `chat-consent-link` produced in place of skipped; the "Ghost agent" note; the manifest's group placements.
- The FD judged these clarifications and additions within the leg's design, not a change of approach, so there is no second cycle.

## Citation Audit (design review additions)
- `scripts/ui_capture.py:2007-2095` (`capture_one`; `prepare` runs after `goto`) and `:980` (the skipped `chat-consent-link`): reviewer-verified.
- `the_one/interfaces/web/app.py:1362-1372`: `_get_purge_check_interval` reads `THE_ONE_PURGE_CHECK_INTERVAL_SECONDS`. FD-verified.
- `the_one/db/repositories.py:2685`: the repository update stamps `updated_at=now_iso()`. Reviewer-verified.
