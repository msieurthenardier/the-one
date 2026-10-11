# Flight Log: Agents Know the Time

**Flight**: [Agents Know the Time](flight.md)

## Summary

Planned 2026-10-10. The operator pre-authorized autonomous execution of the
whole mission through to one PR, reviewed at the PR (no per-flight HAT).

---

## Leg Progress

---

### Leg 1: time-zone-core-and-setting

- **Status**: landed (flight-end review passed; committed in the flight/1 commit). Started and completed 2026-10-10.
- **Locked dependencies** (AC1):
  - `tzdata` 2026.4, uploaded 2026-09-12. The newest release, 2026.5, was uploaded 2026-10-03 (7 days before the leg), so `pyproject.toml` caps it: `tzdata>=2025.2,<2026.5`. Lift the cap once 2026.5 is 14 days old.
  - `tzlocal` 5.4.4, uploaded 2026-06-29 (`tzlocal>=5.3`).
  - `uv.lock` regenerated (adds only those two). `.venv` has both installed at the locked versions via `pip`. `uv export --no-dev --extra gui --extra all-llms --no-hashes` lists both.
- **Changes Made**:
  - `the_one/time_zones.py` (new leaf module), `GET`/`PUT /api/time-settings` and `GET /api/time-zones` in `api.py`, `/api/info` date-line examples in `app.py`.
  - `_probe_time_zones` doctor gate, eleventh and last; docstring rewritten.
  - Windows spec: tzdata data files plus tzdata/tzlocal hidden imports. `"time zones: OK"` appended last to `NEEDLES`, the CI task `foreach` list (and its comment) and `.github/workflows/windows-installer.yml`.
  - Tests: `tests/test_time_zones.py`, `tests/test_time_settings_api.py`, doctor and windows_test_copy updates, `frozen_clock` fixture in `tests/conftest.py`.
  - Docs: CLAUDE.md (doctor sentence, "Time zone setting (M28)" paragraph), `agents.md` (eleven gates, new "Time zones (M28)" section), SECURITY-MODEL.md.
- **Verification**:
  - `tests/test_time_zones.py`, `tests/test_time_settings_api.py`, `tests/test_doctor.py`, `tests/test_windows_test_copy.py`: green.
  - `make test-unit`: 5883 passed, 12 skipped. The baseline is 10 skips; the extra two are the new `test_locale_neutral` (no `fr_FR`/`de_DE` locale on this host) and one timing-conditional skip of the documented watcher kind (squawk 0132). `ruff check` and `ruff format --check` clean.
  - `.venv/bin/python -m the_one doctor` on WSL: `time zones: OK - 345 zones (tzdata 2026d); system zone: America/Chicago`, `RESULT: PASS`, exit 0.
- **Decisions / deviations**:
  - The tzdata upper bound above (AC1's own fallback, not a deviation).
  - `zone_label` for an unnamed zone is `system time zone, UTC+HH:MM` and is used by both `tool_lines` and `date_line`, so an unnamed zone's date line reads `(system time zone, UTC+00:00)`.
  - `system.offset` in GET is the offset of the detected system zone (or the host's fixed offset when none is detected), independent of the chosen mode.
  - Both the tzdata `IANA_VERSION` (2026d) and the Windows frozen result are untested here: the frozen doctor is the CI judge.
- **Anomalies**: none.

### Leg 2: current-time-tool-server

- **Status**: landed (flight-end review passed; committed in the flight/1 commit). Started and completed 2026-10-10.
- **Changes Made**:
  - `the_one/tools/time_tool.py` (new `CurrentTimeTool`); `"current_time"` appended last to `_TOOL_CLASSES` (23 built-ins).
  - `agent/config.py`: `WHITELIST_EXEMPT_TOOLS`, `is_tool_enabled` and docstring, `compose_system_prompt(..., date_line=None)`.
  - `agent/prompt_layers.py`: `SUPPORTS_TOOLS_TIMEOUT_S`, async `time_tool_available`, `build_system_prompt(..., tool_available=False, now=None)` (date layer built in its own try, WARNING and omit on failure).
  - `agent/factory.py`: seed tuple gains the tool; `tool_available` passed. `self_configuration/pending.py`: computed in its own try/except before the recompose try. `db/_notes.py` docstring.
  - `static/js/tool-categories.js`: Time row last, frozen `whitelistExempt`, header comment.
  - `agents.md`: "current_time and the date layer (M28)" section; the M27 layer-order text updated.
  - Tests: new `tests/test_time_tool.py`; `conftest.py::expected_date_layer`; edited `test_prompt_layers.py` (date layer, `time_tool_available` matrix, factory seeding/disable/chat-only cases), `test_config.py`, `test_factory.py`, `test_builtins.py`, `test_search_tools.py`, `test_self_configuration_write.py` (stub gets `tools` and `supports_tools`, autouse `frozen_clock`, two new settle tests, fallback asserted date-free), `test_self_configuration_projection.py`, `test_connectors_inbound.py`, `test_connector_routes.py` (comment), `test_tool_categories.py` (Time last, `whitelistExempt` parity).
- **Verification**: `make test-unit`-equivalent (`pytest -m 'not browser and not live and not pixel'`): 5955 passed, 15 skipped (12 at the default `-m`; the extra 3 are `test_mcp_sandbox_integration` skips that my explicit `-m` un-deselects; baseline 12 = 11 Windows/PTY + `test_locale_neutral`). Ruff check and format clean. Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) green.
- **AC14 per-file triage**: `test_connectors_inbound.py` changed (frozen clock, with-tool line). `test_self_configuration_write.py` changed. `test_prompt_layers.py` changed. `test_telegram_plugin.py`, `test_telegram_api.py`, `test_agent_rename.py`, `test_web_session_reaper.py`, `test_session_lifecycle.py`, `test_ws_storage_edge_shim_visibility.py`, `test_self_configuration_api.py`: unaffected (no whole-prompt equality). `test_agent_degraded_injection.py`: unaffected (builds `Agent` directly with its own `compose_system_prompt`, not via the factory).
- **Decisions / deviations**:
  - `search_tools` "Found 3 tools" with `current_time` listed in `built-in:`; `loaded_names` unchanged (dedupe against the seed), as expected.
  - `test_factory.py`'s disabled-pair agent now still shows `current_time` after the two baseline schemas (not disabled), so the exact-list assertion became a prefix plus name check.
  - Tests using `AsyncMock` connections now emit a RuntimeWarning (un-awaited coroutine in the app_metadata read inside `load_effective_zone`, which falls back to the system zone); harmless, no failures.
  - Browser tests not touched (leg 2b).
- **Anomalies**: none.

### Leg 3 (leg 2b): current-time-tool-client

- **Status**: landed (flight-end review passed; committed in the flight/1 commit). Started and completed 2026-10-10.
- **Changes Made**:
  - Badge: `--badge-time: #2e6b3f` and `--badge-ink-time: #ffffff` in both theme blocks of `tokens.css`; `.badge--time` (`components.css`), `.admin-tool-badge--time` (`admin.css`); `'time'` in `BADGE_KINDS` (15); mirrors in `tests/browser/design_tokens.py`; `time` in the two lists in `test_design_tokens_a11y.py`; count 14 -> 15 in `test_ui_badge_kinds.py` and in `tests/browser/test_ui_choice_contract.py` (found by the gate, not listed in the leg).
  - Client exemption: `agent-drawer.js::isToolEnabled`, `tools-tab.js` (`enabledSet` rule plus the `time-tool-note` line on the tool row) and `studio.js::collectFormData` (exempt toggles leave the branch choice; unticked goes to `disabled_tools` in every branch, order: non-exempt disabled, exempt off, stored ungated), all reading `App.toolCategories.whitelistExempt`.
  - Prompts page: Date layer with two captioned `<pre>` blocks, new intro and Notes help, `fetchPrompts` takes five targets.
  - `tests/browser/_lists.py::TOOL_TABS` gained `current_time` -> `time`.
  - Docs: `docs/ui-testid-registry.md` (3 testids), CLAUDE.md paragraph, `agents.md` client-mirror bullet. `docs/ui-control-inventory.md` lists no badge kinds: unchanged.
  - Tests: new `test_flow_studio_time_tool.py` (7 cases: whitelisted agent shows checked + note + clean dirty state, untick/save/reload/retick, blocklist branch, category master, create mode, globally disabled, Settings tile toggle round trip); edited `test_flow_chat_drawer.py` (parity, counts, Bare, new globally-off case), `test_flow_admin_tools_grid.py`, `test_flow_studio_tools_overrides.py`, `test_flow_admin_settings_nav.py`.
- **Verification**:
  - Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_badge_kinds`, `test_tool_categories`, `test_nav_helper`): 345 passed. Ruff check and format clean.
  - Targeted browser runs green: time tool, tools grid, overrides, settings nav (49), drawer + knowledge_attach (40, including `test_disabled_tools_union_survives_three_branches`).
  - `make gate` (REQUIRE_WEBKIT=1, TEST_TIMEOUT=3600), unit tier green, then: routing rc=0 560s, settings rc=0 502s, agents rc=0 570s (OVER BUDGET 510), chats rc=1 399s (OVER BUDGET 360), mcp rc=0 371s (OVER BUDGET 360), library rc=0 266s, shared rc=1 291s, contracts rc=1 271s (OVER BUDGET 270). `PARALLEL_RESULT rc=1 total=1172s lanes=8 failed=chats,shared,contracts`.
  - The three failures, each handled:
    - contracts: real, `test_ui_choice_contract.py::test_badge_kinds_text_and_throws` pinned 14 kinds; fixed to 15; the file passes in both engines with REQUIRE_WEBKIT=1.
    - chats: one ERROR, `test_flow_chat_picker.py::test_new_chat_opens_the_picker_focused...`, a 401 from `seed_mock_provider` (credential seeding, before any app code); passes on isolated re-run.
    - shared: `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker` (route `chats` vs auto-joined `chats/<id>`); passes on three isolated runs and in the whole file (24 passed); a load-sensitive auto-join race, unrelated to this leg. It failed once more in one earlier combined run, so it is worth a squawk.
  - No full gate re-run after the contracts fix; the fix was verified on the file.
- **Decisions / deviations**: none beyond the extra `test_ui_choice_contract.py` count; the tile note sits on the tool row per the FD call.
- **Anomalies**: the two flakes above. No packaging, `time_zones.py` or `diagnostics.py` changes.

## Decisions

---

## Deviations

---

## Anomalies

---

### Flight Director Notes

- **2026-10-10.** The `leg-execution.md` phase file loaded, and its structure is
  valid. Branch `flight/01-agents-know-the-time` was created from `main`
  (`afa7855`), and the flight is in flight.
- **Leg 1 `time-zone-core-and-setting` is tiered HIGH.** It adds two runtime
  dependencies and a lock change, changes the Windows PyInstaller spec, and
  creates an API contract (`/api/time-settings`, `/api/time-zones`) that
  Flight 2 consumes. Zone-string validation is also security-adjacent: agent-
  and operator-supplied strings must never become paths. A Developer
  design-review pass runs before implementation.
- **Leg 1 design review** (Developer, Sonnet): approve with changes. Applied:
  - the pip-managed venv install;
  - the `uv export` check;
  - the fixed-offset abbreviation rule, keeping the host's `tzname`;
  - malformed JSON returns 422;
  - 422 sentences classified by `loc`/`type`, with no `_validation_detail`;
  - the `tool_configs` `KeyError`;
  - the doctor test list;
  - the full doc and CI sites (the GitHub break-glass file uses `grep -q`
    lines);
  - `tzlocal` reloaded at most once every 60 seconds;
  - the leaf-import AC20.

  **FD calls on the reviewer's questions:**
  - an unnamed system zone keeps the host abbreviation;
  - malformed JSON returns 422;
  - the zone is re-read once a minute, not process-lifetime.

  No second review: the changes were guidance and detail, with no change of
  approach. Leg status: ready.
- **Leg 1 landed** (Developer, Sonnet).
  - The FD verified the new tests (141 passed, 1 skipped: the locale).
  - The suite's 12 skips are 10 baseline + the locale skip + 1
    timing-conditional watcher skip (squawk 0132 documents both
    possibilities). The flight-end Reviewer re-checks this.
  - The as-built names match the leg 2a plan: `render_date_line(date_text,
    zone_text, *, tool_available)` and `frozen_clock` taking `request.param`.
- **Leg 2a `current-time-tool-server` is tiered HIGH.** It changes a shared
  interface with many consumers (`compose_system_prompt` and
  `build_system_prompt` signatures), tool-gating semantics (`is_tool_enabled`)
  and the self-configuration settle path (lifecycle). A Developer
  design-review pass runs first.
- **Leg 2a design review** (Developer, Sonnet): approve with changes. Applied:
  - the `is_error` content prefix;
  - the exact fail-open rules (a broken registry gives False; a failed provider
    call gives True; the whole helper is guarded; the settle call has its own
    `try`; the timeout is read at call time);
  - the file list for whole-prompt triage;
  - the known `search_tools` "Found 3" expectation;
  - the degraded-request assertion;
  - the tool-count sites;
  - positional recovery is handled upstream;
  - a non-tautological literal test.

  **FD calls:**
  - a registry lookup failure means the tool is absent (False);
  - the per-agent opt-out is `disabled_tools` only (through the Tools tab,
    leg 2b), which is intended (DD6).

  No second review: detail only, with no change of approach. Leg status: ready.
- **Leg 2b `current-time-tool-client` is tiered HIGH.** It changes the agent
  editor's save branches and dirty snapshot (shared state), and a UI leg was
  under-tiered in M27 (methodology observation 2). Its design review ran
  concurrently with leg 2a's implementation (read-only, on surfaces 2a does
  not touch).
  - **Outcome:** approve with changes. Applied:
    - the Prompts `nth` off-by-one (blocks 4 and 5);
    - four more drawer assertion sites;
    - the Tools-tab count form `1 / 1 enabled`;
    - the tools-grid tab-count line;
    - the knowledge-attach union test to run;
    - the exact `disabled_tools` order;
    - verifiable dirty-state assertions, and the create-mode, master-toggle
      and globally-disabled cases;
    - the token keys and sorted insertion;
    - no Design language or inventory change.
  - **FD calls:**
    - the note goes on the `current_time` tool row (`time-tool-note`);
    - the Settings toggle selector is named;
    - the hue is `#2e6b3f` (DD7 text amended to match).
  - Leg status: ready.
- **The behavior test `agent-tells-the-time` PASSED 8/8** (2026-10-11
  01:02Z; live mode; local `gpt-oss:20b`; a scratch instance on port 8492,
  since stopped). Run log:
  `tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md`.
  - The spec is now `active`, and its step 6 wording is tightened (outbound
    records have no timestamp).
  - One cosmetic defect: a numeric abbreviation repeated in tool line 2
    (`+14 (UTC+14:00)`). It is handed to the leg 4 fix-forward Developer
    with the full gate re-run.
- **The leg 2b gate flake** `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`
  is the existing **squawk 0168**, which now records the M28 occurrence and
  links its likely root cause, squawk 0169. It is deferred and was not
  folded into this flight.
- **Leg 4 landed** (the fix-forward of the numeric abbreviation, plus the gate).
  - The gate run was red: about 10 scattered render timeouts across 6 lanes,
    each passing on an isolated re-run. They are attributed to host load
    (another session's pytest and a loaded Ollama model ran concurrently).
  - **FD call:** that is not accepted as a clean signal. The FD re-ran
    `make gate` on a quiet host (load about 2/20). The result is recorded
    below.
  - Origin `main` was fast-forwarded into the branch (`664d10f`, PR #264,
    README rebuild). It does not overlap this flight's changes.
- **Flight-end Reviewer: Sonnet tier.** The diff touches the tool-gating
  semantics (the whitelist exemption) and adds credential-gated routes that
  validate untrusted zone strings, both security-adjacent per the crew file.
  The Reviewer was told not to run browser lanes while the gate runs.
- **Flight-end Reviewer: `[HANDOFF:confirmed]`.** No blocking issues. The
  static guards (264) and the targeted unit files (279 passed, 1 skipped)
  pass. One non-blocking nit: CLAUDE.md names
  `AgentConfig.WHITELIST_EXEMPT_TOOLS`, but it is a module-level constant in
  `agent/config.py`. It is fixed in the commit.
- **FD gate re-run 1** (quiet host, no netns): unit 5918 passed, 12 skipped.
  - Browser: `PARALLEL_RESULT rc=1 total=1035s failed=routing,settings,chats,mcp,shared`.
  - 9 scattered failures, a different set from leg 4's. Most are
    `wait_settled` timeouts at 30 s, meaning a fetch never went quiet.
  - All 9 (14 cases) **passed in one isolated run, in 37 s**.
  - Mission 27's green gates all ran with `THE_ONE_TEST_NETNS=1` (the
    documented WSL mirrored-networking remedy), and this flight's gates did
    not.
- **FD gate re-run 2** with `THE_ONE_TEST_NETNS=1`:
  - unit: 5916 passed, 14 skipped (the documented netns count: 12, plus 2
    root-only permission skips);
  - browser: `PARALLEL_RESULT rc=1 total=1008s lanes=8 failed=shared`;
  - every lane within budget: routing 498/600, settings 450/540, agents
    500/510, chats 328/360, mcp 313/360, library 236/300, shared 258/300,
    contracts 230/270;
  - the only failure was `test_flow_jump_to.py::test_new_chat_opens_the_agent_picker`,
    the pre-existing squawk 0168 (also seen in M27 gates).
  - **Disposition:** the gate is accepted as green apart from known squawk
    0168. The earlier scattered `wait_settled` failures were the WSL
    mirrored-networking issue that `THE_ONE_TEST_NETNS=1` exists for.
    Future gates on this host must set it.
- **PR timing:** per the operator's instruction (one mission PR), no draft
  PR is opened for Flight 1 alone. Flight 2 branches from this flight's
  commit, and the mission PR opens from Flight 2's branch, as Mission 27 did
  (#260).

## Session Notes

### 2026-10-10: Flight design

- Two Architect review cycles (Opus). Both returned **approve with changes**,
  and every finding was applied.
- **Cycle 1:**
  - (high) Locale- and platform-neutral formatting, with the doctor gate also
    proving the formatted strings.
  - (high) A deterministic clock and zone seam (`frozen_clock`), plus the list
    of whole-prompt tests to update.
  - (medium) A 2-second cap on `supports_tools`, checked only when the tool is
    present.
  - (medium) The zone-name check pinned to tzdata, so `localtime` is refused.
  - (medium) The DD7 badge ripple, missing test-count updates, the Prompts
    page, and leg 2 split into 2a and 2b.
  - The behavior-spec timing window corrected.
- **Cycle 2:**
  - The DD7 contradiction resolved (add `.badge--time`, and `BADGE_KINDS` goes
    from 14 to 15).
  - The flag is named `tool_available` throughout.
  - The settle-path call sits outside the `try`, and the test stand-ins get the
    real shape.
  - The date line says "last loaded", not "opened": rejoin, inbound and settle
    rebuild it.
  - The Prompts page has 5 blocks.
  - Smaller fixes: the needle order, `EffectiveZone` in the doctor gate, the
    behavior spec's outbound snapshot.
- **Flagged for the operator's PR review:**
  - The date-line wording.
  - The base prompt's "only `search_tools` and `continue`" sentence, left as
    it is.
  - The "Time" category and badge, a deviation from the canvas.

### Leg 4 (verify-live-and-windows) — Windows half

- **Interop:** `cmd.exe /c ver` answered `Microsoft Windows [Version 10.0.26200.9457]`. `doctor-host` exited 0 (mirrored networking, operator data dir cross-check ok, operator app running and untouched).
- **Pre-session snapshot:** `snapshot --out` written (scratch `m28-pre.json`).
- **setup:** 57.7 s (stamp warm). **freeze:** 192.1 s (PyInstaller 190.8 s); both exes built.
- **Frozen doctor** (`doctor --frozen --data-dir <root>\data-m28`): exit 0, `RESULT: PASS`, 11 gates:
  - child spawn: OK (spawned via cmd.EXE, round-trip OK)
  - python interpreter: OK (C:\Python311\python.exe)
  - desktop shell: OK (pystray + PIL importable)
  - llm providers: OK (all 6 provider modules importable)
  - model catalog: OK (seed resolves claude-sonnet-4-6 -> 1000000)
  - usearch: OK (HNSW round-trip returned key 7; numkong=no, simd=serial)
  - fts5: OK (SQLite 3.45.1; porter+unicode61 MATCH round-trip)
  - embedding model: OK (512-dim float16 -> float32, norm 1.0000, peak RSS 247.4 MiB)
  - file watcher: OK (native change notification round-trip)
  - window chrome: OK (caption colours supported, build 26100)
  - **time zones: OK (345 zones (tzdata 2026d); system zone: America/Chicago)**
- **snapshot --compare:** `ok: true`, no allowed changes, no failures; operator app still running (pid 52296).
- **Defects:** none; no packaging/time-zone fix needed (DD8 collection works in the frozen build).

### Leg 4 (verify-live-and-windows) — close-out

- **AC1 / AC3 / AC4**: recorded above in the Windows-half entry (Ollama models present, Windows interop, packaged/Windows checks).
- **AC2 (behavior test)**: `agent-tells-the-time` passed 8/8; run log `tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md`.
- **AC5 fix-forward**: the run showed zones with a numeric `tzname()` (Pacific/Kiritimati `+14`, America/Sao_Paulo `-03`, Asia/Kathmandu `+0545`) repeating the offset on tool line 2 (`... 3:05 PM +14 (UTC+14:00)`). `the_one/time_zones.py::_abbreviation` now also omits an abbreviation matching `^[+-]\d{2,4}$` (`_NUMERIC_ABBREVIATION`); alpha abbreviations (PDT, IST) are unchanged. New unit test `TestFormatters::test_tool_lines_numeric_abbreviation_omitted` (Kiritimati, Kathmandu at the frozen instant) in `tests/test_time_zones.py`; `the_one/agents.md` "Time zones (M28)" abbreviation sentence updated. time_zones / time_settings_api / doctor / prompt_layers unit files: 174 passed, 1 skipped; `ruff check` and `ruff format --check` clean.
- **Full gate** (`THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 make gate`, run once to completion): unit tier 5918 passed, 12 skipped (the documented loaded-host variance), 198.6s. Browser tier `PARALLEL_RESULT rc=1 total=1103s lanes=8 failed=routing,settings,agents,chats,mcp,shared`:

  | lane | rc | wall / budget |
  |---|---|---|
  | routing | 1 | 565 / 600 |
  | settings | 1 | 510 / 540 |
  | agents | 1 | 554 / 510 OVER BUDGET |
  | chats | 1 | 369 / 360 OVER BUDGET |
  | mcp | 1 | 323 / 360 |
  | library | 0 | 236 / 300 |
  | shared | 1 | 258 / 300 |
  | contracts | 0 | 226 / 270 |

  The gate-run failures were 10 scattered one-per-area tests, all "element not found"/timeout on a page that never rendered (no `ERR_NETWORK_CHANGED`), none touching the time work: chat_pane start-failure, library_list delete/create-cancel, admin_knowledge_settings load-failure, admin_navigation, admin_settings_nav, agents_chat_action create-mode, router_announce, jump_to unit cases.
- **Isolated re-runs** (`scripts/run-tests.sh --lane <l> --tb=short`, TEST_TIMEOUT=1500, sequential): shared rc=0, chats rc=0, mcp rc=0, routing rc=0, settings rc=1 (1 failure, `test_flow_settings_visible_fixes::test_provider_info_icons_have_accessible_names`, a different test from the gate run), agents rc=1 (1 failure, `test_agents_chat_action::test_chat_from_a_clean_editor_starts_a_pending_chat`, also different). Both re-run singly with the gate's other failures from those lanes (`-k`): 2 passed (agents) and 4 passed (settings). Verdict: load/render-timing flakes (host also running another session's pytest), not regressions; the failing set changes every run and every failure passes alone.
- **Budgets**: not changed. Over budget again: agents 554/510 (isolated 423s, within), chats 369/360 (isolated within). Left to the flight-end reviewer and FD.

## Flight close

The flight-end review confirmed all four legs and the flight was committed in the flight/1 commit (branch flight/01-agents-know-the-time).
