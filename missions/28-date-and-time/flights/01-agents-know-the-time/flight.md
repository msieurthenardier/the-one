# Flight: Agents Know the Time

**Status**: landed
**Mission**: [Agents Know the Date and Time](../../mission.md)

## Contributing to Criteria

- [ ] **Agents can tell the time from the first turn.** Every agent, trimmed
      ones included, unless the time tool is off. *(Behavior test
      `agent-tells-the-time`)*
- [ ] **Agents can convert between zones.**
- [ ] **Every conversation carries the current date.** It is refreshed on every
      build. The tool is named only when present, the settle path and the
      chat-only path included, and Settings › Prompts shows both wordings.
- [ ] **The operator sets the zone once, and it holds.** Server side: stored,
      served, validated, and applied to the tool and the prompt. The app's
      displayed times are Flight 2.
- [ ] **The operator controls the time tool.**
- [ ] **Named zones work on every supported platform.** Native Windows proof is
      this flight's exit gate.
- [ ] **Upgrades need nothing.**

Flight 2 carries the rest: the Date and time page ("sees what agents see", the
mismatch hint) and the app's displayed times following the zone. This flight
builds the server data that page renders, including the preview strings.

---

## Pre-Flight

### Objective

Give every agent a reliable "now", controlled by one operator time-zone setting.

- **The tool.** A side-effect-free `current_time` built-in tool, visible from
  the first turn, returns the current date and time in the operator's zone, or
  in a named zone on request.
- **The date line.** Every agent build appends a date line, the last prompt
  layer. It names the tool only when the agent can actually call it.
- **The setting.** It is stored in the existing key-value table and served by
  new `GET`/`PUT /api/time-settings` and `GET /api/time-zones` routes. It
  defaults to the system zone, which a small detection dependency names.
- **Zone data on every platform.** It ships through `tzdata` on every platform
  and is bundled into the PyInstaller build. A new unconditional `time zones`
  doctor gate proves it, and a native Windows run is the exit gate.

### Open Questions

- [x] Detection library → DD8 (`tzlocal`)
- [x] Zone database and "real zones" list → DD2 (`tzdata` is the list; the
      `Z` lines of `tzdata.zi`)
- [x] How the tool state reaches the prompt → DD5
- [x] Tool output format → DD1
- [x] Category on Settings › Built-in tools → DD7
- [x] What a zone with no detected name shows → DD2 (offset label)
- [x] Zone to the client before first render → Flight 2. This flight serves
      `/api/time-settings`; Flight 2 decides the client seam.

### Design Decisions

**DD1: The tool is `current_time`, with an optional `zone` argument, returning
two lines per zone.**

- **Module and class.** `the_one/tools/time_tool.py::CurrentTimeTool`, with the
  name constant `CURRENT_TIME_TOOL_NAME = "current_time"`. It is appended at the
  END of `_TOOL_CLASSES` (`the_one/tools/builtins.py:43-77`) with the default
  `_EmptyConfig`, which the ordering assertion at `builtins.py:89` allows.
- **Parameters.** `{"zone": {"type": "string", "description": "Optional IANA
  time zone name, e.g. Asia/Tokyo. Omit for the operator's time zone."}}`, with
  no required fields.
- **Output for the operator's zone** (no `zone`, or `zone` equal to it):

  ```
  2026-10-10T15:45:12-07:00 (America/Los_Angeles)
  Saturday, October 10, 2026, 3:45 PM PDT (UTC-07:00)
  ```

- **Output for another zone:** that zone's two lines, then a blank line, then
  `Operator's time zone:` and the operator's two lines.
- **Why two lines.** Line 1 is machine-precise ISO 8601 with seconds. Line 2
  carries the weekday and the 12-hour clock, so a weak model never has to work
  out the weekday itself.
- **When the system zone has no name** (DD2), the label is `(system time zone,
  UTC+00:00)`.
- **Errors.** An unknown `zone` raises `ValueError("Unknown time zone
  '<value>'. Use an IANA name such as Asia/Tokyo or Europe/Paris.")`. The agent
  loop wraps it as an `is_error` tool result, as the notes tools' refusals are.
  - "Unknown" is decided by DD2's `is_known_zone` (the `tzdata` name set). An
    agent-supplied string therefore never causes a file open under TZPATH.
  - A legacy alias (`US/Pacific`) is accepted, because it is in the name set.
- **Formatting is platform- and locale-neutral** (Architect review, high).
  - Build the text with f-strings over `dt.year`/`dt.day`, `dt.hour % 12 or 12`
    and `dt.minute`, plus fixed English weekday and month tables.
  - Never use `strftime` with `%-d`/`%-I` (glibc-only; Windows raises
    `ValueError`) or `%A`/`%B`/`%p` (they follow the locale, which a GTK or
    pywebview process may set with `setlocale`).
  - The offset is formatted by hand from `utcoffset()`, and the abbreviation
    comes from `dt.tzname()`.
- **Constructor and test seams.** `get_tools` builds every tool as `cls(cfg,
  cross_configs=…, agent_name=…)` (`builtins.py:~209`). The constructor
  therefore keeps the base signature and adds keyword-only extras: `now:
  Callable[[], datetime] | None = None` and `zone_source: Callable[[],
  Awaitable[EffectiveZone]] | None = None`. When an argument is `None`, the
  tool looks up `time_zones.utcnow` and `time_zones.load_effective_zone` **at
  call time**, never binding them at construction, so a test's monkeypatch
  applies. There are no mock libraries.
- **The name constant lives where it can be imported cheaply.**
  `CURRENT_TIME_TOOL_NAME` is defined in `the_one/time_zones.py`, a leaf module,
  so `agent/config.py` can import it without a cycle into `tools/`. The tool
  module re-exports it.
- **No side effects:** no sandbox, no network, no Config.
- *Rationale:* the canvas board 3 shape, already agreed with the operator.
- *Trade-off:* a second line costs a few tokens per call.

**DD2: One module owns zones: `the_one/time_zones.py`.**

- **The setting.** `TimeZoneSetting` (pydantic): `mode: Literal["system",
  "zone"] = "system"` and `zone: str | None = None`. A validator requires `zone`
  when `mode == "zone"`. It applies `is_known_zone` (the `tzdata` name set, never
  "`ZoneInfo` resolves") to `zone` in **both** modes whenever it is non-null.
  The model uses `extra="forbid"`. The PUT handler turns validation failures
  into plain-sentence 422 details, as `knowledge-settings` does with
  `_validation_detail`, never FastAPI's list-shaped default.
- **Storage.** It is stored as JSON under the `app_metadata` key `time_zone`
  through `AppMetadataRepository` (`the_one/db/repositories.py:2393`).
  - A missing or unparsable value loads as the default (system), with a logged
    warning for an unparsable one.
  - No schema migration.
- **`detect_system_zone() -> str | None`.** Returns `tzlocal.get_localzone_name()`
  inside a try, and `None` on any exception, on an empty result, or on a result
  that fails `is_known_zone`. `tzlocal`'s environment path can return a `TZ`
  value that isn't a zone name.
- **Module-level seams.** `utcnow()` and `detect_system_zone()` are read through
  module attributes, never bound early, so tests can monkeypatch
  `the_one.time_zones.utcnow` / `.detect_system_zone`. This makes factory,
  settle and inbound prompt assertions deterministic (DD4).
- **`load_effective_zone(conn=None) -> EffectiveZone`.** Loads the setting
  (default `get_connection()`) and resolves it. This is the one function the
  tool, the prompt layer and the routes call.
- **`resolve(setting) -> EffectiveZone`.** A frozen dataclass: `key: str | None`
  (the IANA name, or `None` for an unnamed system zone) and `tzinfo`.
  - **Zone mode:** `ZoneInfo(zone)`.
  - **System mode, detected name:** `ZoneInfo(name)`.
  - **System mode, no name:** the host's fixed local offset,
    `datetime.now().astimezone().tzinfo`.
  - A zone that fails to load at resolve time (data removed) falls back to the
    system path with a logged warning. Agent builds never fail on it.
- **`label(eff, at)`.** The IANA name, or `system time zone, UTC±HH:MM` when
  there is none.
- **`canonical_zones() -> list[str]`.** The `Z` lines of the `tzdata` package's
  `zoneinfo/tzdata.zi`, excluding the `L` alias lines. Read once with
  `importlib.resources` and cached.
  - About 341 at 2025b. The locked version may differ, so tests assert
    structure: more than 300 entries, `Asia/Kolkata` present, `US/Pacific`
    absent. Never an exact count.
- **`is_known_zone(key)`.** True when `key` is in the `tzdata` name set (`Z` ∪
  `L` lines), identical on every platform. Aliases pass. Host-only database
  files such as `localtime` or `posixrules` do **not**, even though `ZoneInfo`
  would load them on Linux (Architect review: TZPATH reads the host first).
- **Resolving.** `ZoneInfo(key)` is used only after `is_known_zone` passes.
  - On Linux the rules may come from the host database. The **name set** is
    pinned to `tzdata`, and the rules for a valid name agree across a release or
    two.
  - `zoneinfo.reset_tzpath([])`, which would force `tzdata` everywhere, is
    noted as the all-in option and not taken. It is process-global.
- **`zone_rows(at)`.** For `/api/time-zones`: `{zone, region, city, offset,
  abbreviation}`, built from `canonical_zones()` with these rules:
  - `Factory` is excluded.
  - `Etc/UTC` is kept, as region `UTC` and city `UTC`.
  - The `Etc/GMT±N` zones and other `Etc/*` entries are excluded from the list,
    because their POSIX-inverted signs mislead. They are still accepted if
    stored or typed, being in the name set.
  - `region` is the part before the first `/`, and `city` is the last segment
    with `_` turned into a space.
  - `offset` is `UTC±HH:MM` at `at`, formatted by hand, and `abbreviation` is
    `tzname()`.
- **Formatters, pure and given `now`.** `tool_lines(now, eff)` gives DD1's two
  lines. `date_line(now, eff, *, tool_available)` (DD4) delegates to a
  string-only `render_date_line(date_text, zone_label, *, tool_available)`, so
  `/api/info` can render placeholders through the same function. The flag is
  named `tool_available` everywhere (DD4, DD5).
- *Rationale:* one seam for the tool, the prompt, the API, the doctor gate and
  Flight 2.
- *Trade-off:* `ZoneInfo` on Linux reads the host database first and only falls
  back to `tzdata`. The **list** always comes from `tzdata`, so it is identical
  on every platform. A host database a release behind could resolve one key
  differently, which is accepted.

**DD3: Two new routes behind the existing credential gate, in
`the_one/interfaces/web/api.py`, beside `knowledge-settings` (`api.py:2410`).**

- **`GET /api/time-settings`** returns:

  ```json
  {"mode": "system"|"zone", "zone": str|null,
   "system": {"zone": str|null, "offset": "UTC-07:00"},
   "effective": {"zone": str|null, "label": str, "offset": str, "abbreviation": str},
   "preview": {"tool": str, "prompt": str, "prompt_without_tool": str, "clock": "3:45 PM"}}
  ```

  - `preview.tool` is exactly `tool_lines` for the operator's zone.
  - `prompt` and `prompt_without_tool` are exactly `date_line(…, tool_available=True|False)`.
  - `clock` is the local 12-hour `h:mm AM/PM` in the effective zone, the DD14
    format of M25 F6.
  - The GET also carries `tool_enabled` (bool): whether `current_time` is
    globally enabled (its `tool_configs` row is missing or enabled), so Flight
    2's preview can pick the right wording.
  - Flight 2 renders these strings verbatim.
- **`PUT /api/time-settings`** takes the body `{"mode": …, "zone": …}`. It
  returns 422 for any of:
  - a body that is not an object, or has extra keys;
  - an unknown mode;
  - `mode: "zone"` without a zone, or with an unknown zone.

  Each 422 detail is a plain sentence. The route saves and returns the GET
  shape.
  - A `zone` sent with `mode: "system"` is kept if it is valid (422 if not)
    and ignored for resolution, so Flight 2's "Choose a time zone" radio can
    restore the last chosen zone.
  - `null` clears it.
- **`/api/info`** gains `date_prompt_example` and `date_prompt_example_without_tool`.
  These are **static placeholders**, as the rules and notes examples are:
  `render_date_line("{today's date}", "{time zone}", …)`. There is no database
  or `tzlocal` read in that handler, because `/api/info` is the desktop
  launcher's one-second "is this ours" probe (`desktop/shell.py:~290`).
- **`GET /api/time-zones`** returns `{"zones": [rows…]}`, canonical only,
  ordered by region, then city.
- *Rationale:* it mirrors the `knowledge-settings` shape. The preview strings
  come from the same functions the tool and prompt use, so the page cannot
  drift from what agents see.
- *Trade-off:* the GET is computed per request; it is cheap.

**DD4: The date line is the last prompt layer, built on every agent build.**

- **Composition.** `compose_system_prompt` (`the_one/agent/config.py:93`) gains
  `date_line: str | None = None`. When it is set, the line is appended after
  notes with the usual `---` separator.
  - With `date_line=None` the output is byte-identical to today, so every
    existing composer test holds.
  - The result still starts with `BASE_PROMPT`.
- **Building.** `build_system_prompt` (`the_one/agent/prompt_layers.py:20`)
  gains the keywords `tool_available: bool = False` and `now: datetime | None =
  None` (default `time_zones.utcnow()`). It calls `load_effective_zone(conn)`
  and passes `date_line(…)`.
  - Any exception there is logged at **warning, with the traceback**, and the
    layer is omitted. A date failure never fails a build.
  - The doctor gate (DD9) is what catches a platform-wide formatting failure
    that this catch would otherwise hide.
- **Existing tests that compare a whole prompt will change** (Architect review,
  high). The composer tests stay byte-identical because `date_line=None` is the
  default. These sites build through `build_system_prompt`, the factory, the
  settle path or inbound:
  - `tests/test_prompt_layers.py` ~145, 151, 161, 195-196, 282, 290, 300;
  - `tests/test_connectors_inbound.py` ~600;
  - `tests/test_self_configuration_write.py` ~447-456, 636-638, 675;
  - any further hits from `grep -rn "system_prompt" tests/` that assert
    equality, or `endswith` on the last layer.

  Each is updated deterministically, by one of:
  - monkeypatching `time_zones.utcnow` and `time_zones.detect_system_zone` and
    building the expected value with the same function;
  - asserting on the prompt with its final date layer stripped.

  Either way, no assertion may depend on the wall clock or the host zone. A
  shared fixture in `tests/conftest.py` (`frozen_clock`) pins both.
- **`parse_notes_block`** (`the_one/db/_notes.py:~149`). Its docstring says
  notes are the final layer. Its `rfind`/`find` logic still works with a
  trailing date layer, but the docstring is updated, and a regression test
  parses a prompt that has the date layer after notes.
- **"Last loaded", not "opened"** (second-pass review). Every web rejoin
  (`app.py:~1560-1568`), every connector inbound message (`inbound.py:~443-452`)
  and the settle path rebuild the system message. A resumed chat or a
  multi-day connector thread therefore shows the date of its last load, which
  says nothing about when earlier turns happened. This is flagged for the
  operator's PR review together with the wording.
- **The base prompt's sentence is left as it is.** `BASE_PROMPT` says agents
  start with only `search_tools` and `continue`. Seeding `current_time` makes
  that inexact. It is already inexact for the seeded connector pair and notes
  tools, and the mission forbids rewording existing layers, so it stays. The
  date line names the tool. This is flagged for the operator's PR review.
- **Wording (provisional; shown on Settings › Prompts, operator reviews at the
  PR).** With the tool:

  ```
  Today is Saturday, October 10, 2026 (America/Los_Angeles). This date is as of when this conversation was last loaded. For the current date and time, call current_time.
  ```

  Without the tool:

  ```
  Today is Saturday, October 10, 2026 (America/Los_Angeles), as of when this conversation was last loaded.
  ```

  An unnamed system zone renders `(system time zone, UTC+00:00)`.
- *Rationale:* the operator's decisions (date on every build; name the tool
  only when present). It sits last so an implicit prefix cache loses the
  smallest span. There are no `cache_control` markers anywhere.
- *Trade-off:* the prompt text changes once a day per agent.

**DD5: "Tool available" is computed in one helper and passed by both callers.**

- **The helper.** `prompt_layers.time_tool_available(registry, llm) -> bool`
  checks `CURRENT_TIME_TOOL_NAME in registry.tool_names` **first**. If the tool
  is absent it returns False without touching the provider. Otherwise it
  returns `await asyncio.wait_for(llm.supports_tools(), timeout=2.0)`.
  - A timeout or any exception counts as **True**, failing open like the loop
    does: it sends tools when capabilities are unknown.
  - Architect review, medium: `OllamaProvider.supports_tools` reaches
    `show_model` with `httpx timeout=30` (`ollama_api.py:~140`), and failures
    are not cached. OpenRouter's is a network call too. Without the cap, an
    unreachable remote provider would stall every join, rejoin and connector
    message for up to 30 seconds.
- **The factory** calls it after the registry and seeding blocks, just before
  `build_system_prompt` (`factory.py:542`), and passes `tool_available=`.
  `time_tool_available` is an `async def`, because it awaits the provider.
- **The settle path** (`the_one/self_configuration/pending.py:106`) calls it
  with `agent.tools` and `agent.llm` (`core.py:173-174`), so a self-revision
  never reverts the wording.
  - The call sits **before and outside** the existing `try` (`pending.py:~105`).
    It is itself guarded by `getattr(agent, "tools", None)`, so a missing
    registry counts as tool-absent (False) and never raises into the
    rules-read fallback.
  - Test stand-ins gain the real shape:
    - `tests/test_self_configuration_write.py::_StubAgent` (~462-483) gets
      `tools = ToolRegistry()`, and its `_LLMShim` gets an `async
      supports_tools`;
    - the mirrored `StubAgent` in `tests/test_app_websocket_pause_resume.py`
      gets the same, if it reaches the settle path.
  - Its exception fallback (`pending.py:114`, base + persona) stays date-free.
    It is a rules-read failure path, and that is accepted.
- **Chat-only models.** `supports_tools()` is the predicate the frozen loop
  itself uses (`core.py:271`), so a chat-only model gets the tool-free wording.
  `core.py` is untouched.
  - Ollama's `supports_tools` is cached per model on success
    (`ollama_api.get_model_capabilities`, ~195, `_CAPABILITIES_TTL`), so the
    extra await is usually a cache hit.
  - `FakeLLM` and `MockProvider` inherit the base `True`, so unit tests are
    unaffected.
- *Rationale:* one predicate, used by both callers, with no change to the frozen
  loop.
- *Trade-off:* a model swapped between builds is reflected only on the next
  build, which is the existing staleness contract.

**DD6: `current_time` is exempt from the trimmed `enabled_tools` list, but
honours `disabled_tools` and the global toggle (operator decision).**

- **The constant.** `the_one/agent/config.py` gains `WHITELIST_EXEMPT_TOOLS =
  frozenset({CURRENT_TIME_TOOL_NAME})`, imported from the leaf
  `the_one/time_zones.py`.
  - Its docstring and the `is_tool_enabled` docstring are updated: an empty
    whitelist no longer "blocks all built-in tools", because the exempt tool
    survives it.
  - So is the matching comment or assertion at
    `tests/test_connector_routes.py:~434`.
- **The rule.** `AgentConfig.is_tool_enabled` (`config.py:196`) treats such a
  name exactly like an `UNGATED_TOOL_PREFIXES` name: the whitelist branch is
  skipped, and `disabled_tools` still applies.
  - The factory's global filter (`disabled_names` from `tool_configs.enabled`,
    `factory.py:386,456`) is unchanged.
  - `self_configuration/projection.py:96` uses `is_tool_enabled`, so
    `describe_my_capabilities` agrees automatically.
- **Seeding.** The tool is added to the existing baseline seed tuple
  (`factory.py:522-531`, the `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME` loop), which
  seeds only when registered. A disabled tool is therefore never seeded.
- **The client copies the exemption in three places,** all driven by one new
  frozen field `App.toolCategories.whitelistExempt = ['current_time']` in
  `static/js/tool-categories.js`:
  1. `areas/chat/agent-drawer.js::isToolEnabled` (line ~129) treats an exempt
     name as ungated.
  2. `areas/studio/tools-tab.js` `enabledSet` (line ~58): an exempt tool's
     checkbox is checked iff it is not in `disabled_tools`, whatever the
     whitelist says.
  3. The `areas/studio.js` agent save (lines ~3404-3437):
     - an **unchecked** exempt tool goes into `disabled_tools` in **every**
       branch, the whitelist branch included;
     - an exempt name is never written into `enabled_tools`;
     - the list-or-blocklist choice counts only non-exempt toggles.

     Otherwise an operator who unticks it on a trimmed agent would silently fail
     to disable it.
- `tests/test_tool_categories.py` pins `whitelistExempt` against the Python
  constant, as it already pins the category table against `_TOOL_CLASSES`.
  - The frozen `whitelistExempt` field is **added in leg 2a**, together with the
    Time row and the pin test.
  - Leg 2b only consumes it, at the three sites.
- *Rationale:* every agent can tell the time after the upgrade, and the operator
  can still remove the tool.
- *Trade-off:* a fourth special case in the tool-gating story. It is named,
  pinned and documented in `agents.md`.

**DD7: A new built-in tool category, "Time" (a deviation from the canvas's "no
badge").**

- **Why it's needed.** Every built-in must appear exactly once in
  `App.toolCategories`, and `tests/test_tool_categories.py` enforces it.
  Without a category the tool shows on no Settings tab and no Tools-tab tile.
  The canvas assumed a badge-free tile; that is structurally impossible here.
- **The category.** `{ id: 'time', label: 'Time', tools: ['current_time'] }` is
  appended after Connectors.
- **Badge tokens, in both themes** (`css/tokens.css`):
  - `--badge-time` is a dark green, distinct from filesystem's cyan and from
    ollama. The final value is set in leg 2b (`#2e6b3f`).
  - Badge ink is **theme-stable** (`tokens.css:~177-193`, `~326-341`), so a
    single `--badge-ink-time` must clear 4.5:1 on **both** theme fills.
  - Mirrored in both theme palettes of `tests/browser/design_tokens.py`.
  - Gated by `tests/test_design_tokens_a11y.py`: `_TOKEN_BADGE_KINDS` (~1184)
    and `_BADGE_INK_PAIRS` (~1332) gain the `time` entry.
    `_TOKEN_BADGE_KINDS` drives `test_badge_kind_rules_consume_the_gated_pair`
    (~1200-1206), which reads `.badge--{kind}` in `components.css`.
- **Classes, consistent with the four sibling categories** (second-pass review):
  - `.badge--time` in `components.css`, beside `.badge--filesystem` …
    `.badge--connectors` (~1906-1915);
  - `.admin-tool-badge--time` in `admin.css` (~317);
  - `'time'` in `ui/feedback.js::BADGE_KINDS` (~8-23). This is an `App.ui`
    library file, so the contracts lane runs under WebKit.
  - `tests/test_ui_badge_kinds.py::test_badge_kind_count` goes from 14 to 15.
  - The Design language page's status section shows it, if it enumerates
    `BADGE_KINDS`.
- **Tests that enumerate categories or tabs** gain Time:
  - `tests/test_tool_categories.py::test_categories_and_labels_in_tab_order`;
  - `tests/browser/test_flow_admin_tools_grid.py` (~89-106): the target is
    five tabs, with `expected` gaining `"time": 1`;
  - `tests/browser/test_flow_studio_tools_overrides.py` (~93-112): the target
    is five tiles and 23 tools.
- *Rationale:* the smallest change that satisfies the existing invariant.
- *Trade-off:* a one-tool category. A later utility tool can join it or rename
  it.

**DD8: `tzdata` and `tzlocal` become base dependencies.**

- **`pyproject.toml`.** `tzdata>=2025.2` is unconditional, because it is the
  canonical-list and name-set source on every platform (DD2). `tzlocal>=5.3` is
  added too.
- **Locking.** `uv.lock` is regenerated with `uv lock`. Plain `uv lock` does
  not enforce the "two weeks old" rule, so the Developer:
  - checks the resolved versions' PyPI upload dates (`pip index versions` or
    the PyPI JSON `upload_time`);
  - if the newest is less than 14 days old, pins the previous release in
    `pyproject.toml` (`tzdata>=2025.2,<X`, or `==`);
  - records the versions and dates in the flight log.
- **Installing.** `.venv` has neither package today, so leg 1 runs `uv sync`
  (or `pip install -e ".[all-llms,dev]"`) before the WSL doctor check and
  before any dev instance.
- **`packaging/windows/the-one.spec`** gains these, with a comment block in the
  spec's existing style:
  - `tzdata_datas = collect_data_files("tzdata")`, added to `datas`;
  - `collect_submodules("tzdata")` and `collect_submodules("tzlocal")` added to
    the hidden imports.

  Why the hidden imports: `collect_data_files` skips `.py` files, and
  `canonical_zones()` reaches `tzdata` by string through `importlib.resources`,
  so nothing in the module graph imports it. They may duplicate
  `hook-zoneinfo`/hooks-contrib, which is harmless, and the frozen doctor (DD9)
  decides. `tzlocal/__init__` imports its `win32` module under a platform `if`.
- **The detection fallback.** `tzlocal` raises or warns when it cannot name the
  zone (a bare container, or `TZ` set to a value that isn't a zone name), and
  DD2 maps that to `None`.
- *Rationale:* the operator's decision (a detection library). `tzlocal` maps
  Windows zone names to IANA names using its own table.
- *Trade-off:* two new dependencies. Both are tiny and maintained, and
  `tzlocal` itself depends on `tzdata` on Windows.

**DD9: An unconditional `time zones` doctor gate.**

- **What it checks.** `the_one/diagnostics.py::_probe_time_zones`:
  - `canonical_zones()` returns more than 300 entries, and `is_known_zone`
    rejects `localtime`.
  - **The tzdata package itself is loaded, pinned before the result is
    trusted.** `ZoneInfo.from_file(importlib.resources.files("tzdata.zoneinfo.America").joinpath("Los_Angeles").open("rb"))`
    converts `2026-01-15T20:00:00Z` to `12:00` at `-08:00`, and
    `2026-07-15T19:00:00Z` to `12:00` at `-07:00`. On Linux a plain
    `ZoneInfo(...)` would prove the host database, not the bundle.
  - **The formatters work on this platform.** `tool_lines()` and
    `render_date_line()`/`date_line()` on that fixed instant equal hard-coded
    expected strings: `"Thursday, January 15, 2026, 12:00 PM PST (UTC-08:00)"`
    and `"Today is Thursday, January 15, 2026 (America/Los_Angeles)…"`. The
    gate builds `EffectiveZone(key="America/Los_Angeles", tzinfo=<the from_file
    zone>)` explicitly, because `from_file` yields `key=None`, which would label
    it as an unnamed system zone. So the
    frozen Windows doctor proves the formatting, not only the data (Architect
    review, high).
- **What it reports but never fails on.** The detected system zone name, or
  "none detected".
- **Placement.** Added to `run_doctor` (`diagnostics.py:880`) as the eleventh
  gate. Gates unconditionally, every host, like `fts5`.
- **Every place that lists the gates is updated:**
  - the `run_doctor` docstring count;
  - `tests/test_doctor.py`;
  - **this pinned pair**, which must change together:
    `scripts/windows_test_copy.py::NEEDLES` and the needle list in
    `ci/tasks/windows-installer-build.yml:114` (`"time zones: OK"`), appended
    **last** in both, since the pin compares tuples in order.
    `tests/test_windows_test_copy.py::test_needles_match_ci_foreach_list`
    asserts they are equal;
  - the break-glass `.github/workflows/windows-installer.yml` (~118), if it
    carries the same list;
  - CLAUDE.md's gate sentence ("ninth gate … tenth …");
  - `agents.md` (~1636, "The ten gates").
- *Rationale:* the established frozen-capability proof seam (M15 F5, M24, M25
  F5).
- *Trade-off:* none.

**DD10: The native Windows run is this flight's exit gate.**

- **What it is.** The `verify-live-and-windows` leg freezes the branch on the
  operator's Windows desktop through `scripts/windows_test_copy.py` (setup,
  then freeze, then `doctor`, frozen) and records the `time zones: OK` line and
  the detected zone name.
- **Fallback.** If the Windows desktop or interop is unavailable at leg time,
  run the Concourse `windows-installer-build` task instead.
- **If neither is reachable,** the leg records BLOCKED with the exact command to
  run. The flight does not land as complete with the criterion silently
  unchecked.
- **Which instances.** `windows_test_copy.py` itself refuses ports 8484 and
  8485 and the operator's data dir. Only `doctor` runs in this leg; no server
  is launched.

**DD11: Behavior test `agent-tells-the-time`. Apparatus: browser, http, shell
and the stub connector seam, against a live local model.**

- **Act path.**
  - Browser: Chats, New chat, pick, send.
  - http: `PUT /api/time-settings` to set a far zone, `Pacific/Kiritimati`
    (UTC+14), whose calendar date differs from UTC for 14 hours of every day
    and from the host's for most of it.
  - The agent edit (`PUT /api/agents/{name}` with an `enabled_tools` /
    `disabled_tools` payload).
  - The stub seam: `POST /api/_test/stub/inbound`.
- **Read path, audited.**
  - Each fresh session's stored system message: `chat_sessions.messages`
    element 0 through `sqlite3` on the scratch DB, as in `agent-rules-round-trip`.
  - Tool calls and results in the same stored list.
  - The reply text in the transcript DOM, and the stub seam's
    `GET /api/_test/stub/outbound`.
  - The Validator works out the expected date independently with
    `TZ=Pacific/Kiritimati date +%A,%B,%d,%Y`. It never reads the instance for
    the expected value.
- **Model.** Local Ollama `gpt-oss:20b` (or `qwen3:30b`). Both are present on
  the host (`/api/tags`, checked 2026-10-10). Re-check per run.
- The spec is at `tests/behavior/agent-tells-the-time.md`, drafted with this
  flight.

### Citation Audit

Verified against the working tree at `afa7855`.

| Citation | Status |
|---|---|
| `the_one/tools/builtins.py::_TOOL_CLASSES` (43-77): dict, end-append convention with `_EmptyConfig`; ordering assertion at ~89 constrains only the first `FilesystemConfig` tool | verified |
| `the_one/agent/config.py::UNGATED_TOOL_PREFIXES` (17): a tuple used with `str.startswith` | verified |
| `the_one/agent/config.py::AgentConfig.is_tool_enabled` (196): whitelist skipped for ungated; `disabled_tools` always applies | verified |
| `the_one/agent/config.py::compose_system_prompt` (93): keyword-only `rules`, `notes`; layers joined with `"\n\n"` and `"---"`; result starts with `base` | verified |
| `the_one/agent/factory.py` (386-387): `disabled_names` = configs with `enabled` False; (456) built-in filter `not in disabled_names and is_tool_enabled` | verified |
| `the_one/agent/factory.py` (522-531): seed tuple loop, seeds only `if name in registry.tool_names` | verified |
| `the_one/agent/factory.py` (542): `build_system_prompt(config.name, config.system_prompt, conn=conn)` after the registry is built | verified |
| `the_one/agent/prompt_layers.py::build_system_prompt` (20): `(agent_name, persona, *, conn=None)`, async | verified |
| `the_one/self_configuration/pending.py` (106-116): recomposes with `build_system_prompt(agent_name, system_prompt)`; fallback `compose_system_prompt(BASE_PROMPT, system_prompt)`; sets `agent.system_prompt` and `messages[0]` | verified |
| `the_one/agent/core.py` (173-174): `self.llm`, `self.tools` attributes; (271) loop awaits `self.llm.supports_tools()`; (459-465) chat-only swap keeps the suffix after `BASE_PROMPT` | verified |
| `the_one/llm/ollama_api.py::get_model_capabilities` (195): cached per (url, model) for `_CAPABILITIES_TTL` on success only; `None` on error, not cached; `show_model` uses `httpx` timeout 30 | verified (Architect) |
| `the_one/tools/base.py::ToolRegistry.tool_names` (200): property, list of names | verified |
| `the_one/db/repositories.py::AppMetadataRepository` (2393): async `get`/`set`/`delete`, string values | verified |
| `the_one/interfaces/web/api.py` (2410, 2417): `knowledge-settings` GET/PUT; PUT validates the body shape and raises `HTTPException(422)` | verified |
| `the_one/interfaces/web/app.py` (2621-2633): `/api/info` returns `base_prompt`, `rules_prompt_example`, `notes_prompt_example` | verified |
| `static/js/areas/admin/system-page.js::renderPromptsPage` (67): layers built from `promptLayer` plus `/api/info` fields, testids `*-prompt-content` | verified |
| `static/js/tool-categories.js` (TABLE, frozen `App.toolCategories`), pinned by `tests/test_tool_categories.py` | verified |
| `static/js/areas/chat/agent-drawer.js` (95, 129-138): `UNGATED_PREFIXES` and `isToolEnabled` copy of the whitelist rule | verified |
| `static/js/areas/studio/tools-tab.js` (56-64): `enabledSet` from `enabled_tools`, else `disabled_tools` | verified |
| `static/js/areas/studio.js` (3404-3437): save, with list-or-blocklist branches by majority; ungated stored names appended | verified |
| `the_one/diagnostics.py::run_doctor` (880): ten gates; `ProbeResult(name, ok, detail)`; ASCII-safe emit | verified |
| `ci/tasks/windows-installer-build.yml` (114): needle list of `"<gate>: OK"` strings | verified |
| `packaging/windows/the-one.spec` (117, 131): `collect_data_files` pattern for package data | verified |
| `tzdata` package: `zoneinfo/tzdata.zi` with `Z` and `L` lines (341/257 at IANA 2025b from a user-site tzdata 2025.2; the locked version may differ, so tests assert structure) | verified (structure) |
| `scripts/windows_test_copy.py::NEEDLES` equals the CI foreach list, pinned by `tests/test_windows_test_copy.py::test_needles_match_ci_foreach_list` | verified (Architect) |
| `the_one/interfaces/desktop/shell.py` (~290): `/api/info` is the launcher's one-second ownership probe | verified (Architect) |

### Prerequisites

- [x] Mission 28 active and agreed (2026-10-10).
- [x] Local Ollama with a tool-capable model (`gpt-oss:20b`, `qwen3:30b`):
      present 2026-10-10. **Re-verify at the start of the verify leg.**
- [ ] The operator's Windows desktop is reachable through WSL interop for
      `scripts/windows_test_copy.py`, or the Concourse Windows worker is up.
      **Re-verify at the start of the verify leg** (DD10). It is an external
      session.
- [x] `uv` is available for `uv lock`. The leg confirms it.
- [x] No port conflicts: tests spawn their own uvicorn. The behavior test uses a
      dev instance on 8490 or higher with a scratch data dir. It never uses 8484
      or 8485.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified (Windows and Ollama re-verified at the verify leg, DD10)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

1. **Zone core and setting (leg 1).**
   - Dependencies and lock (DD8), then `the_one/time_zones.py` (DD2): the
     name set, the canonical list, detection, resolution, the locale-neutral
     formatters and the module-level seams.
   - The routes (DD3, with `/api/info`'s static placeholders), the doctor gate
     (DD9) with its pinned needle pair, and the PyInstaller spec changes (DD8).
   - Unit tests:
     - the setting round-trip: default, zone, alias, `localtime` refused,
       unknown;
     - every 422, and a kept zone in system mode;
     - the preview strings under a frozen clock;
     - the canonical list's structure (`Factory`/`Etc/GMT+5` excluded, `Etc/UTC`
       kept);
     - detection failure and a non-name `TZ`;
     - the formatters under a non-English `setlocale`, where the locale is
       available, else skip;
     - the doctor gate.
   - New DB tests use `tests/_schema_template.py`.
2. **The tool and the date layer, server side (leg 2a).**
   - The tool (DD1).
   - The Time row in `tool-categories.js`, needed for `test_tool_categories`
     (DD7).
   - `WHITELIST_EXEMPT_TOOLS` and the docstrings (DD6).
   - Seeding.
   - The date layer and `time_tool_available` in the factory and the settle
     path (DD4, DD5).
   - `parse_notes_block`'s docstring and its regression test.
   - Unit tests:
     - the tool for its zone, another zone, an unknown zone, an alias and an
       unnamed system zone;
     - composition with and without the tool;
     - the chat-only predicate, with a fake LLM whose `supports_tools` is False;
     - the 2-second cap, with a fake LLM whose `supports_tools` sleeps;
     - no provider call when the tool is absent;
     - the settle path keeping the tool sentence;
     - factory gating: a trimmed agent gets it; `disabled_tools:
       ["current_time"]` and a globally disabled tool do not; the seed follows;
     - projection agreement;
     - `whitelistExempt` pinned against `WHITELIST_EXEMPT_TOOLS`;
     - a `frozen_clock` fixture.
   - **Existing tests updated:**
     - DD4's prompt-equality list;
     - `tests/test_builtins.py:64, 72, 123` (22 → 23);
     - `tests/test_factory.py:~1143` (`_loaded_schemas` 2 → 3);
     - `tests/test_search_tools.py:~960` ("Found 2 tools:");
     - `tests/test_tool_categories.py::test_categories_and_labels_in_tab_order`;
     - `tests/test_connector_routes.py:~434`;
     - every further hit of `make test-unit` (run it, don't guess).
3. **The client side (leg 2b).**
   - The `--badge-time`/`--badge-ink-time` tokens, the mirror, the a11y gate
     entries and `.admin-tool-badge--time` (DD7).
   - The three JS exemption sites driven by `App.toolCategories.whitelistExempt`
     (DD6).
   - The Prompts page "Date" layer showing both placeholder wordings, with
     testids `date-prompt-content` and `date-prompt-content-without-tool`
     registered in `docs/ui-testid-registry.md`. The page intro ("…then rules
     and notes") and the Notes help ("Added last…") become "…rules, notes, then
     the date".
   - A one-line note on the agent Tools tab that `current_time` is always
     loaded, since that tab's intro says tools load on demand.
   - **Browser tests** (in files the lane globs pick up: `test_flow_studio_*`,
     `test_flow_admin_*`, `test_flow_chat_*`; no new file in `shared`):
     - unticking on a trimmed agent persists to `disabled_tools`, and a reload
       shows it unchecked;
     - ticking it back clears it;
     - the drawer count;
     - the Settings › Built-in tools Time tab;
     - the Prompts Date layer.
   - **Existing browser tests updated:**
     - `test_flow_admin_settings_nav.py:~283-295` (3 → **5** `<pre>` blocks and 3 → 4 exact titles: "Base prompt", "Rules", "Notes", "Date". The Date layer holds two blocks, labelled "With the time tool" and "Without it");
     - `test_flow_admin_tools_grid.py:~89-106`;
     - `test_flow_studio_tools_overrides.py:~93-112`;
     - `test_flow_chat_drawer.py:~420` (the parity case gains `current_time`
       and a trimmed config).
   - **Docs:**
     - `agents.md`: the zone module, the tool, the exemption, the date layer, the
       doctor gate;
     - CLAUDE.md: the gate sentence and a short paragraph;
     - SECURITY-MODEL.md: the new routes behind the gate, and agent-supplied
       zone strings never opening files.
4. **Live and Windows proof (leg 3).**
   - Re-verify Ollama and Windows reachability.
   - Run `/mission-control:behavior-test agent-tells-the-time` against a
     scratch dev instance (`uv sync` first).
   - Run the native Windows freeze and doctor (DD10).
   - Fix forward anything small, and record results in the flight log.

### Checkpoints

- [x] Leg 1: `make test-unit` green, the routes answer through `TestClient`,
      and `the-one doctor` shows `time zones: OK` on the WSL host after `uv sync`.
- [x] Leg 2a: `make test-unit` green.
- [x] Leg 2b: `make gate` green, and the `contracts` lane green under
      `THE_ONE_REQUIRE_WEBKIT=1`.
- [x] Leg 3: `agent-tells-the-time` passes, and the frozen Windows doctor shows
      `time zones: OK`.

### Adaptation Criteria

**Divert if**:

- `tzlocal` cannot be frozen, or misbehaves on Windows in a way a hidden import
  doesn't fix. Fall back to stdlib detection (`TZ`, `/etc/localtime`), with
  offset-only on Windows, and tell the operator. That reverses an operator
  decision.
- The live model ignores the date line *and* never calls the tool in the
  behavior test. Then the wording or the seeding approach needs an operator
  conversation, not a fix forward.

**Acceptable variations**:

- The exact badge hex values. The exact `time zones` gate detail text.
- The region bucketing of single-segment zones.
- Merging legs 2a and 2b if 2a lands small.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `time-zone-core-and-setting`: dependencies and lock, `time_zones.py`, the
      setting routes, preview strings and `/api/info` placeholders, the doctor
      gate, the needle pair, and the PyInstaller spec.
- [x] `current-time-tool-server`: the tool, the Time category row, the
      whitelist exemption (server), seeding, the date layer in the factory and
      the settle path, and the unit-test updates.
- [x] `current-time-tool-client`: the badge tokens and a11y gate, the three
      client exemption sites, the Prompts Date layer, the Tools tab note, the
      browser tests, and the docs.
- [x] `verify-live-and-windows`: the `agent-tells-the-time` behavior test, the
      native Windows frozen doctor, and fix-forward.

No HAT leg in this flight. The operator reviews the whole mission at the PR
(operator instruction, 2026-10-10).

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [ ] Code merged (one mission PR, after Flight 2)
- [x] Tests passing (`make gate`, the contracts lane with WebKit)
- [x] Documentation updated:
  - `agents.md`: the time-zone module, the tool, the whitelist exemption, the
    date layer, the doctor gate;
  - CLAUDE.md: the gate count, plus a short "Time zone and `current_time`"
    paragraph;
  - SECURITY-MODEL.md: new routes behind the gate, with no new boundary.

### Verification

- `make gate` green, with the contracts lane run under `THE_ONE_REQUIRE_WEBKIT=1`.
- The `agent-tells-the-time` run log shows pass.
- The frozen Windows doctor output, with `time zones: OK`, is recorded in the
  flight log.
