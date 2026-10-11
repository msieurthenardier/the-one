# Mission: Agents Know the Date and Time

**Status**: active

## Outcome

An agent always knows what day it is and can tell the current time, in the
time zone the operator means. Asked "what's today's date?", "what time is it in
Tokyo?" or "how long until 5 PM?", it answers correctly from the first turn of
any conversation, in the app and in connector channels, without guessing or
asking.

The operator chooses that time zone once, on a Settings page:

- the zone of the machine running the-one (the default), or
- any named zone.

The page shows what agents will see before and after a change. It warns when
the browser and the server disagree, which is common under WSL, in a container
or on a remote server, and fixes that in one step. The times the app shows (the
Chats list, messages) follow the same setting, so the app and its agents never
disagree about the time.

Source: GitHub issue [#223](https://github.com/msieurthenardier/the-one/issues/223).
Design canvas (approved by the operator, 2026-10-10):
[Date and time settings](https://claude.ai/artifact/A89sjcpKfxd9j1BedBvkYx).
It has three boards: the page in dark theme in the WSL mismatch case
(interactive), the page in light theme while choosing a zone, and what the
agent sees.

## Context

Today an agent has no reliable way to know "now".

- **Nothing injects the date.** The prompt is assembled in one place,
  `build_system_prompt` (`the_one/agent/prompt_layers.py`): base prompt,
  persona, rules, notes. None of these carries a date.
- **No built-in tool returns the time** (`the_one/tools/builtins.py::_TOOL_CLASSES`).
- **Server-side `datetime.now` calls write UTC storage timestamps.** A sampled
  grep shows `datetime.now(timezone.utc)` in retention, models, connectors and
  the web app. None of them answers "what time is it for the operator".
- **The client shows clock times in the browser's zone** through
  `App.time.formatClock` (M25 F6, DD14). That flight ruled a time-zone setting
  out of scope, to be designed together with this tool.

Facts about the codebase that shape the design (verified at `afa7855`):

- **There is precedent for a starting toolset.** Mission 27 seeds the notes
  tools into the starting toolset of every agent whose notes switch is on
  (`the_one/agent/factory.py:534-539`). Without that, an agent reaches tools
  only through `search_tools`, and a weak local model is unlikely to think of
  searching for "time". The notes tools are not built-ins, though. They are
  registered outside the built-in whitelist (`factory.py:499-508`). A built-in
  can't simply copy that, because of the next point.
- **A new built-in tool misses trimmed agents.** The agent Tools tab saves its
  choice one of two ways (`static/js/areas/studio.js:3424-3437`). With most
  tools on, it saves the tools turned off (`disabled_tools`). With most off, it
  saves the tools turned on (`enabled_tools`). `AgentConfig.is_tool_enabled`
  (`the_one/agent/config.py:196`) drops any built-in missing from a saved
  `enabled_tools` list, and the factory registers built-ins through that filter
  (`factory.py:455`). The starting-toolset seed only seeds tools already
  registered. An agent the operator trimmed to a few tools would therefore never
  get `current_time`.
  - **Operator decision:** the time tool is exempt from the `enabled_tools`
    list, as `kb__` and `mcp__` tools already are (`UNGATED_TOOL_PREFIXES`,
    `config.py:16`).
  - The per-agent `disabled_tools` list still applies, and so does the global
    Built-in tools toggle. The operator can still remove it from one agent or
    from all of them.
- **The prompt doesn't know which tools an agent has.**
  `build_system_prompt(agent_name, persona, conn=)` sees no tool list, and it
  has two callers:
  - the factory (`factory.py:542`), after the registry is built;
  - the self-configuration settle path (`the_one/self_configuration/pending.py:106`),
    which recomposes the prompt with no tool knowledge at all.

  The chat-only degraded path swaps only the base-prompt prefix and keeps every
  later layer (`the_one/agent/core.py:459-465`). A date line that names the tool
  would reach a model that cannot call tools.
  - **Operator decision:** the date line names the tool only when the agent has
    it.
  - Both callers must therefore know the tool state, so the settle path can't
    revert the wording.
  - A chat-only model must get the wording that doesn't name the tool, without
    changing the frozen loop in `core.py`.
- **The agent is rebuilt often.** It is built for a new conversation, on every
  web rejoin (`_restore_session`, `app.py`) and on every incoming connector
  message (`the_one/connectors/inbound.py:444`). Each build composes a fresh
  system prompt. A restored session keeps the freshly built system message and
  drops any stored one (`app.py:1562-1568`), so saved history never carries an
  old date. A connector channel's conversation can run for months, so a date
  fixed at conversation start would go stale.
  - **Operator decision:** the date is set on every build. The prompt changes at
    most once a day.
  - An open web chat that crosses midnight keeps its date until it is reopened.
  - The project sets no explicit prompt-cache markers (no `cache_control`).
    Putting the date last keeps the part an implicit prefix cache loses as small
    as possible.
- **App-wide settings already have a home.** `knowledge-settings` keeps its
  values in the `AppMetadataRepository` key-value table behind a `GET`/`PUT`
  pair. A time-zone setting fits the same pattern and needs no schema
  migration.
- **Windows has no time-zone database.** Python's `zoneinfo` falls back to the
  `tzdata` package on Windows.
  - Neither `tzdata` nor a detection library is in `pyproject.toml` or
    `uv.lock`.
  - The PyInstaller spec (`packaging/windows/the-one.spec`) bundles neither.
  - Nothing in `the_one/` uses `zoneinfo` yet.

  Every named zone would fail in the packaged Windows app, and only a native
  Windows build can prove the fix works.
  - `the-one doctor` is the established place to prove a frozen-runtime
    capability (M15 F5, M24 F4, M25 F5). The gate list is in
    `the_one/diagnostics.py`.
  - The new gate checks that **zone data is present**, never that detection
    succeeded. Detection can legitimately find nothing, for example in a bare
    container.
  - A native Windows run is a **Flight 1 exit gate** (operator decision).
- **The standard library cannot name the system zone.**
  `datetime.now().astimezone()` gives an offset and an abbreviation, not an
  IANA name, and Windows reports its own zone names. The operator chose a small
  detection dependency so the page and the tool show `America/Los_Angeles`, not
  only `UTC−07:00`.
- **The browser and the server know different zone lists.**
  - Python's `zoneinfo.available_timezones()` lists 498 zones on this host,
    legacy aliases included, with no alias metadata.
  - `Intl.supportedValuesOf('timeZone')` in Node lists 418. Chromium and WebKit
    may differ again.

  The picker is therefore served from the server, so a chosen zone always
  resolves where the server uses it. The client needs a fallback for a zone its
  own `Intl` does not know (a `RangeError`).
- **The app's own clocks read the browser's local time throughout.**
  - `App.time.formatClock` (`static/js/time.js:8-15`) uses
    `getHours`/`getMinutes`.
  - The Chats list's recency groups and weekday and `Mon D` labels
    (`areas/chat/chats-list.js:60-101`) use the local `getFullYear`/`getMonth`/`getDate`/`getDay`
    getters and a local start of day.
  - The notes list's "today" test (`areas/studio/rules-notes-tab.js`,
    `formatWhen`) uses the same getters.
  - Elapsed-time labels ("3 hours ago") are not affected by the zone.

  **Operator decision:** the client formats with the zone (`Intl.DateTimeFormat`
  with `timeZone`), so this is a rework of `App.time` and its callers, not a
  single change. The zone must reach the client before the first render, and a
  change must re-render.
- **Settings › Prompts shows every built-in prompt layer read-only**, in
  assembly order (M27 F3 L3, from `GET /api/info` examples). The new date line
  must appear there too.
- **The UI reuses existing pieces.** The page uses the existing control library
  (`App.ui.searchList` for the zone chooser) and the one Settings page table
  (`App.settingsPages`). The Settings nav, the router labels and the Jump to
  palette pick up a new page from that table.

## Success Criteria

- [x] **Agents can tell the time from the first turn.** In a new or resumed
      conversation, web or connector, an agent asked for the current date or
      time answers correctly in the operator's time zone. It does not need to
      search for a capability first. This holds for every agent, including
      agents the operator trimmed to a few tools, unless the operator turned the
      time tool off. *(Behavior-test-backed: needs a live model turn.)*
  *Evidence: behavior test `agent-tells-the-time` passed 8/8 on a live model (tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md); unit tests for the whitelist exemption and seeding.*
- [x] **Agents can convert between zones.**
  - An agent asked for the time in another named zone gets it, together with
    the operator's own time.
  - A zone name that doesn't exist gets a clear error the agent can act on.
  *Evidence: behavior test 8/8 (tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md); `tests/test_time_tool.py` covers named zones and the unknown-zone error.*
- [x] **Every conversation carries the current date.**
  - The agent's instructions state today's date and the operator's zone.
  - The date is brought up to date whenever the agent is built for a new chat,
    a rejoined chat or an incoming connector message.
  - The wording tells the agent the date may be as of when the conversation was
    opened.
  - It points the agent at the time tool for the current time only when the
    agent actually has that tool.
  - It still names the tool correctly after the agent's own self-configuration
    edit is applied.
  - A model running without tools never sees the tool named.
  - Settings › Prompts shows this layer in its assembly position, in both
    wordings.
  *Evidence: behavior test 8/8 (tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md); `tests/test_prompt_layers.py` and `tests/test_factory.py` cover the date layer on every build, tool-aware.*
- [x] **The operator sets the zone once, and it holds.**
  - The operator can choose the system time zone (the default) or any named
    zone.
  - The choice survives a restart.
  - It applies to the time tool, the prompt's date and the times the app shows.
  - An unknown zone is refused.
  - A legacy alias that someone stores still resolves.
  *Evidence: `tests/browser/test_flow_settings_date_time.py` (pick, persist across reload, unknown zone refused, alias names) with the Flight 1 server tests; final gate green.*
- [x] **The operator sees what agents see.**
  - The Date and time page shows the zone detected on the machine running
    the-one.
  - It shows the zone in effect.
  - It shows the exact text the time tool and a new chat's prompt would produce.
  - All three update as soon as the choice changes.
  - The page says when a change reaches the tool (at once) and when it reaches
    an open conversation (when it is next opened).
  *Evidence: `tests/browser/test_flow_settings_date_time.py` (detected zone, zone in effect, What agents see preview updating on change, timing note); final gate green.*
- [x] **A browser/server mismatch is caught.**
  - When the browser's zone differs from the zone in effect, the page says so.
  - The page offers a one-step fix that adopts the browser's zone.
  *Evidence: `tests/browser/test_flow_settings_date_time.py` (mismatch hint and one-step adopt-browser-zone fix); final gate green.*
- [x] **The app and its agents agree on the time.** Clock times the app shows
      (the Chats list, messages and every other `formatClock` site) follow the
      operator's zone, not the browser's.
  *Evidence: `tests/browser/test_flow_chat_time_zone.py` (Chats list and messages follow the operator zone, not the browser's) and `tests/browser/test_ui_time_contract.py`; final gate green (unit 5932 passed, 8 browser lanes rc=0).*
- [x] **Named zones work on every supported platform.** That includes the
      packaged Windows desktop app.
  - A named zone resolves there.
  - The system zone is reported by name there.
  - The built-in diagnostic proves the zone data is present in a packaged
    build.
  *Evidence: frozen Windows `the-one doctor` `time zones` gate PASS (flight log); `tests/test_time_zones.py` and `tests/test_doctor.py`.*

  *(Needs a native Windows build: verified through the Windows test copy or
  packaged-smoke CI, not on Linux alone.)*
- [x] **The operator controls the time tool.**
  - It appears on Settings › Built-in tools and can be turned off there for
    every agent.
  - On an agent's Tools tab it can be turned off for that agent alone.
  - Trimming an agent to a list of other tools does not remove it.
  - Wherever it is off, the prompt never points the agent at it.
  *Evidence: behavior test 8/8 (tests/behavior/agent-tells-the-time/runs/2026-10-11-01-02-39.md); `tests/test_tool_categories.py`, `tests/test_time_tool.py` and `tests/browser/test_flow_studio_time_tool.py`.*
- [x] **Upgrades need nothing.**
  - Existing installs keep working with the system time zone and no operator
    action.
  - Every existing agent gains the time tool.
  - No data is lost.
  *Evidence: unit tests for seeding and the system-zone default (`tests/test_time_zones.py`, `tests/test_time_settings_api.py`, `tests/test_factory.py`).*

## Stakeholders

- **Operator (device owner)**, the only human.
  - Gains agents that can handle "today", "in two hours" and "what time is it
    there".
  - Must never see the app and an agent disagree about the time.
  - Must be able to fix a wrong server zone without knowing what WSL or a
    container does to it.
- **Connector peers**, people talking to an agent in Discord or Telegram.
  - They get the operator's time zone, not their own. Per-peer or per-connector
    zones are out of scope (operator decision).
  - The agent can still answer "what time is it for me in Berlin?" through the
    tool's `zone` option.

## Constraints

- **One zone for the whole app.** The operator's setting is the only one. There
  is no zone per agent, per connector or per peer (operator decision, deferred
  to a later issue if wanted).
- **The tool has no side effects.** It reads the clock and the setting and
  returns a string, following the built-in tool contract. It needs no sandbox,
  no network and no new Config surface. It still needs a way to read the stored
  zone: `BuiltinToolProvider.get_tools` passes tool configs, not a database
  connection.
- **Exempt from the trimmed list, not from the operator.** Only the
  `enabled_tools` list is bypassed. The per-agent `disabled_tools` list and the
  global Built-in tools toggle still turn the tool off.
- **Existing prompt layers keep their order and wording.**
  - The date layer is added last, after rules and notes.
  - The composed prompt still starts with the base prompt, so the chat-only
    degraded path keeps working.
  - The frozen dispatch loop in `the_one/agent/core.py` is not touched.
- **The page saves as soon as the operator chooses.** There is no Save button
  and no unsaved state for the leave guard. Choosing "Choose a time zone" saves
  nothing until a zone is picked.
- **UI rules.**
  - New controls go through the `App.ui` library contract: a factory, a demo on
    Design language, an inventory row, and contract tests in both engines.
  - Pages are DOM-built, with no HTML-string sinks.
  - Browser tests navigate through `_nav.py` and `_lists.py`, and run through
    `scripts/run-tests.sh` lanes.
- **Security model unchanged.** The new routes sit behind the existing local-API
  credential gate. Nothing in the setting reaches a subprocess, the filesystem
  or the network.
- **Testing rules.**
  - No mock libraries: the tool takes its clock as an injected callable for
    tests.
  - Snapshot baselines stay gitignored.
  - Live and behavior checks never target port 8484 or the operator's default
    data directory.

## Environment Requirements

- Host-native dev on the WSL host: `.venv`, `make up` on a non-default port with
  a scratch data dir for manual checks, `make gate` for the full local gate.
- **Native Windows** for the packaged-build criterion. Use
  `scripts/windows_test_copy.py` (setup, freeze, launch, observe) or the Windows
  packaged-smoke CI lane on the Concourse `platform: windows` worker.
- A live local model (Ollama, for example `gpt-oss:20b` as in Mission 27) for
  the behavior test of an agent telling the time. The mock provider's scripted
  `tool_calls` drive the deterministic tool-call tests.
- WebKit userland for the contract lane, if a new `App.ui` factory or option is
  added (`THE_ONE_REQUIRE_WEBKIT=1`).

## Open Questions

- **Which detection library?** It must:
  - name the system zone on Linux, macOS and Windows;
  - behave in a frozen build, with a PyInstaller hook or none needed;
  - fall back sanely when the OS reports nothing (a bare container, `TZ`
    unset).

  `tzlocal` is the obvious candidate, but its frozen behaviour is unverified.
  What do the page and the tool show when nothing is detected?
- **Which zone database is used, and where the "real zones" list comes from.**
  - Python on Linux uses the host's zone database, and Windows uses `tzdata`.
    Making `tzdata` the single source on every platform would make the zone
    list consistent everywhere.
  - The `tzdata` package also ships the link lines that tell real zones from
    aliases like `US/Pacific`. The other options are a checked-in list or a
    heuristic.
- **How the tool state reaches the prompt.** The settle path in `pending.py`
  must not revert the tool-naming wording. Two ways are open:
  `build_system_prompt` takes the agent's tool names, or the settle path passes
  the live agent's state.
  - Chat-only models must get the wording that doesn't name the tool, while the
    frozen loop in `core.py` stays untouched.
  - The likely seam is the factory, which can see the provider's tool support.
- **Getting the zone to the client before the first render.** The options are a
  field on `/api/info`, an `App.store` entry or both. Changing the setting must
  re-render open lists, and an unknown zone must fall back in Chromium, WebKit
  and the desktop WebKitGTK.
- **The tool's output format.** It should be one line for the requested zone
  plus one for the operator's (canvas board 3). Does a weak local model handle
  that reliably? Does the line also carry the weekday, which models often get
  wrong when they compute it themselves?
- **Prompt wording.** The exact text of the date line, in both the wording that
  names the tool and the one that doesn't. It is shown on Settings › Prompts
  and changed only together with the operator.
- **Mismatch hint scope.** Should the hint also show on pages other than Date
  and time (for example a one-time notice), or only there? The current design
  shows it only there.
- **The full list of client date logic.** The Architect found three sites that
  read the browser's local time (Context, "The app's own clocks"). Flight 2
  starts with a complete sweep, `message-bubble.js` included, before the
  `App.time` rework is designed.

## Known Issues

*(none yet)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] **Flight 1: Agents know the time.**
  - The `current_time` built-in tool:
    - in every agent's starting toolset;
    - exempt from the trimmed `enabled_tools` list, but honouring
      `disabled_tools` and the global toggle;
    - with an optional `zone` and a Built-in tools entry.
  - The operator time-zone setting, stored and served (`GET`/`PUT` settings, the
    zone list, 422 on an unknown zone).
  - The date prompt layer:
    - refreshed on every agent build;
    - naming the tool only when the agent has it, with the settle path and the
      chat-only path included;
    - shown on Settings › Prompts in both wordings.
  - Detecting the system zone.
  - Zone data on Windows: a dependency, bundled in the packaged build, proven by
    a new doctor gate. A native Windows run is this flight's exit gate.
  - A behavior test of a live agent telling the time, web and connector.
  - Boundary: the operator sees a working server-side result (agents answering
    correctly, and the API set by hand) before the page is built on it.
- [x] **Flight 2: The Date and time page.**
  - The Settings › General › Date and time page from the approved canvas:
    - the system and chosen-zone radio buttons;
    - the inline zone chooser, searchable by city, zone name or offset and
      grouped by region;
    - the browser/server mismatch hint with its one-step fix;
    - the "What agents see" preview, formatted by the server;
    - the note on when a change applies.
  - The `App.time` rework, so every clock time, day group and weekday label the
    app shows follows the setting. It starts with a sweep of every piece of
    client date logic.
  - The page is reachable from the Settings nav and Jump to.
  - No HAT leg (operator decision, 2026-10-10): the operator reviews the
    whole mission at the PR.
