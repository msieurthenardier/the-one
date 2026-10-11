# Leg: time-zone-core-and-setting

**Status**: completed
**Flight**: [Agents Know the Time](../flight.md)

## Objective

Add zone data and detection dependencies and one zone module, `the_one/time_zones.py`.
Serve the operator time-zone setting over `GET`/`PUT /api/time-settings` and
`GET /api/time-zones`, with preview strings, plus static date-line
placeholders on `/api/info`. Prove the zone data and the formatters on every
host with a new unconditional `time zones` doctor gate, and bundle both
packages into the Windows PyInstaller build.

## Context

- Read [flight.md](../flight.md) first. The decisions this leg implements:
  - **DD2** in full (the module);
  - **DD3** (the routes and `/api/info`);
  - **DD8** (dependencies, lock, spec);
  - **DD9** (the doctor gate);
  - **DD1's formatting rules**. `tool_lines` lives in `time_zones.py`, but the
    tool itself is leg 2.
- **Nothing in this leg changes how agents are built.** Leg 2 wires the module
  into the tool, the factory and the prompt. Leg 1 must leave every existing
  test green with no prompt change.
- Constants:
  - `CURRENT_TIME_TOOL_NAME = "current_time"` lives in `time_zones.py` now
    (flight suggestion: a cycle-free leaf module). Leg 2 imports it.
  - The storage key is `time_zone` in `app_metadata`.
- The formatters are pure and **locale- and platform-neutral**:
  - no `strftime` with `%-d`, `%-I`, `%A`, `%B` or `%p`;
  - f-strings over datetime fields;
  - fixed English weekday and month tables;
  - the offset formatted by hand from `utcoffset()`, as `UTC+05:30`,
    `UTC-07:00` and `UTC+00:00` (ASCII hyphen-minus in all server strings).
- **Module-level seams.** Code inside the module calls `utcnow()` and
  `detect_system_zone()` through the module namespace at call time, so tests
  can `monkeypatch.setattr(time_zones, "utcnow", ...)` and
  `monkeypatch.setattr(time_zones, "detect_system_zone", ...)`. The routes do
  the same: `time_zones.utcnow()`, never `from ... import utcnow`.

## Inputs

- Branch `flight/01-agents-know-the-time` at `afa7855` plus the uncommitted
  Mission 28 planning artifacts.
- `.venv` exists but has neither `tzdata` nor `tzlocal`.
- `uv` is on PATH, and `uv.lock` is checked in.

## Outputs

- **`pyproject.toml`**: `tzdata` and `tzlocal` in the base `dependencies`.
- **`uv.lock`**: regenerated.
- **`the_one/time_zones.py`** (new):
  - `CURRENT_TIME_TOOL_NAME`, `SETTING_KEY = "time_zone"`;
  - `TimeZoneSetting`, `EffectiveZone`;
  - `utcnow`, `detect_system_zone`;
  - `zone_names`, `canonical_zones`, `is_known_zone`;
  - `resolve`, `load_setting`, `save_setting`, `load_effective_zone`;
  - `offset_label`, `zone_label`, `tool_lines`, `render_date_line`,
    `date_line`, `clock_text`, `zone_rows`.
- **`the_one/interfaces/web/api.py`**: `GET`/`PUT /api/time-settings` and
  `GET /api/time-zones`.
- **`the_one/interfaces/web/app.py`**: `/api/info` gains
  `date_prompt_example` and `date_prompt_example_without_tool`.
- **`the_one/diagnostics.py`**: `_probe_time_zones`, wired into `run_doctor` as
  the eleventh gate, with the docstring updated.
- **`packaging/windows/the-one.spec`**: the tzdata data files, plus hidden
  imports for tzdata and tzlocal.
- **`scripts/windows_test_copy.py::NEEDLES`** and
  **`ci/tasks/windows-installer-build.yml`**: `"time zones: OK"` appended last
  in both. Also `.github/workflows/windows-installer.yml`, if it carries the
  same needle list.
- **Tests:**
  - `tests/test_time_zones.py` (new): the module;
  - `tests/test_time_settings_api.py` (new): the routes and `/api/info`;
  - `tests/test_doctor.py`: updated, and the new gate tested;
  - `tests/conftest.py`: a `frozen_clock` fixture.
- **Docs:**
  - CLAUDE.md: the doctor sentence (the ninth/tenth gate text) and a short
    "Time zone setting (M28)" paragraph in Architecture;
  - `the_one/agents.md`: the doctor gate list ("The ten gates" → eleven), plus a
    new "Time zones (M28)" section covering the module contract, the storage
    key, the routes and the seams.
- **Flight log**: the leg 1 entry, with the dependency versions and their PyPI
  upload dates.

## Acceptance Criteria

**Dependencies**

- [ ] **AC1.** `pyproject.toml`'s base `dependencies` list `tzdata` and
      `tzlocal` with lower bounds (`tzdata>=2025.2`, `tzlocal>=5.3`).
      `uv.lock` is regenerated and resolves both. Each locked version was
      uploaded to PyPI at least 14 days before 2026-10-10; if the newest one
      wasn't, an upper bound or pin in `pyproject.toml` keeps the lock on an
      older release. The flight log records each locked version with its
      upload date. `.venv` has both installed.
  - `uv export --no-dev --extra gui --extra all-llms --no-hashes` lists both
    packages. The Windows CI builds from that export.
  - `tests/test_packaging_locked_closure.py` passes.

**The zone module**

- [ ] **AC2. `zone_names()` and `canonical_zones()`.**
  - `zone_names()` returns the frozenset of every name in the tzdata package's
    `zoneinfo/tzdata.zi`: its `Z` lines' second field plus its `L` lines' third
    field (link name).
  - `canonical_zones()` returns the sorted `Z` names.
  - Both read through `importlib.resources.files("tzdata")` once and are
    cached.
  - Tests check structure, never exact counts:
    - `canonical_zones()` has more than 300 entries and includes
      `Asia/Kolkata`, `America/Los_Angeles` and `Etc/UTC`;
    - it excludes `US/Pacific`;
    - `zone_names()` includes `US/Pacific`.
- [ ] **AC3. `is_known_zone(key)`.**
  - True for `America/Los_Angeles` and `US/Pacific`.
  - False for `localtime`, `posixrules`, `Mars/Olympus_Mons`, `""`, `None`, a
    non-string, `../etc/passwd` and `America/../../x`.
  - It never touches the filesystem beyond the cached tzdata read.
- [ ] **AC4. `detect_system_zone()`.**
  - Returns `tzlocal.get_localzone_name()` when that is a non-empty string that
    passes `is_known_zone`.
  - Otherwise returns `None`: when it raises any exception, or returns `None`,
    `""`, `"localtime"` or `"Not/AZone"`.
  - Tests monkeypatch `time_zones.tzlocal` (the module attribute) or a seam
    function. No mock libraries; `monkeypatch` only.
  - **Freshness.** `tzlocal` caches its answer for the process. The function
    calls `tzlocal.reload_localzone()` when its last reload is more than 60
    seconds old, tracked with a module-level timestamp, so a desktop app left
    running for days follows a host zone change within a minute. The call
    runs inside `warnings.catch_warnings()` with warnings ignored.
  - `is_known_zone("UTC")` is True, through the `L Etc/UTC UTC` link. One test
    covers it.
- [ ] **AC5. `TimeZoneSetting`.**
  - It is a pydantic model with `extra="forbid"`: `mode: Literal["system",
    "zone"] = "system"` and `zone: str | None = None`.
  - The validator:
    - rejects `mode == "zone"` with `zone` null;
    - rejects any non-null `zone` that fails `is_known_zone`, in either mode.
  - `load_setting(conn)` returns the stored setting. On an absent key it
    returns the default. On unparsable JSON or an invalid stored value it
    returns the default and logs a warning once per call.
  - `save_setting(conn, s)` stores `s.model_dump_json()` under `time_zone`
    through `AppMetadataRepository`.
  - Round-trip tests use a DB built from `tests/_schema_template.py`.
- [ ] **AC6. `resolve(setting) -> EffectiveZone`.** `EffectiveZone` is a frozen
      dataclass with `key: str | None` and `tzinfo: tzinfo`.
  - **Zone mode:** `EffectiveZone(zone, ZoneInfo(zone))`. If loading fails,
    fall back to the system path and log a warning.
  - **System mode with a detected name:** `EffectiveZone(name, ZoneInfo(name))`.
  - **System mode with no name:** `EffectiveZone(None, timezone(offset,
    name))`. `offset` and `name` come from
    `datetime.now().astimezone()`'s `utcoffset()` and `tzname()`, so the host's
    own abbreviation (for example `CDT`) is kept.
  - `load_effective_zone(conn=None)` loads (with `get_connection()` when `conn`
    is None) and resolves. It never raises: on any exception it logs, then
    returns the system resolution.
- [ ] **AC7. Formatters, exact strings.** Under a frozen instant,
      `2026-10-10T22:45:12Z`:

  | Call | Result |
  |---|---|
  | `tool_lines(now, EffectiveZone("America/Los_Angeles", …))` | `["2026-10-10T15:45:12-07:00 (America/Los_Angeles)", "Saturday, October 10, 2026, 3:45 PM PDT (UTC-07:00)"]` |
  | `tool_lines` for `Asia/Kolkata` | `["2026-10-11T04:15:12+05:30 (Asia/Kolkata)", "Sunday, October 11, 2026, 4:15 AM IST (UTC+05:30)"]` |
  | `tool_lines` for an unnamed `timezone.utc` zone | `["2026-10-10T22:45:12+00:00 (system time zone, UTC+00:00)", "Saturday, October 10, 2026, 10:45 PM UTC (UTC+00:00)"]` |
  | `date_line(now, la, tool_available=True)` | `Today is Saturday, October 10, 2026 (America/Los_Angeles). This date is as of when this conversation was last loaded. For the current date and time, call current_time.` |
  | `date_line(now, la, tool_available=False)` | `Today is Saturday, October 10, 2026 (America/Los_Angeles), as of when this conversation was last loaded.` |
  | `render_date_line("{today's date}", "{time zone}", tool_available=…)` | The same two templates with those placeholders substituted |
  | `clock_text(now, la)` | `3:45 PM` |
  | `clock_text` at midnight and at noon | `12:00 AM` and `12:00 PM` |

  - The abbreviation and its following space are omitted from line 2 when
    `tzname()` is `None` or empty, or starts with `UTC+` or `UTC-` (Python's
    default name for a nameless fixed offset). Never `PM UTC-07:00
    (UTC-07:00)`.
  - An extra test row: an unnamed `timezone(timedelta(hours=-5), "CDT")` gives
    `"…, 5:45 PM CDT (UTC-05:00)"`, and `timezone(timedelta(hours=-5))` gives
    `"…, 5:45 PM (UTC-05:00)"`.
  - A test runs `tool_lines` with `locale.setlocale(LC_TIME, "fr_FR.UTF-8")` (or
    `de_DE.UTF-8`), skipped if neither locale is available, and gets the same
    English output. The test restores the locale afterwards.
- [ ] **AC8. `zone_rows(at)`.**
  - Returns the list of `{zone, region, city, offset, abbreviation}` for the
    canonical zones, sorted by region and then city.
  - **Excluded:** `Factory`, and every `Etc/*` except `Etc/UTC`.
  - **`Etc/UTC`** has region `UTC` and city `UTC`. For every other zone,
    `region` is the text before the first `/` and `city` is the last segment
    with `_` turned into a space (`America/Argentina/Buenos_Aires` gives
    region `America`, city `Buenos Aires`).
  - `offset` uses the same `UTC±HH:MM` format as AC7.
  - Asserted: `Asia/Kolkata`'s row at the frozen instant is `{"zone":
    "Asia/Kolkata", "region": "Asia", "city": "Kolkata", "offset": "UTC+05:30",
    "abbreviation": "IST"}`.

**The routes**

- [ ] **AC9. `GET /api/time-settings`** returns exactly these keys:

  ```
  mode, zone,
  system: {zone, offset},
  effective: {zone, label, offset, abbreviation},
  tool_enabled,
  preview: {tool, prompt, prompt_without_tool, clock}
  ```

  - `preview.tool` is `"\n".join(tool_lines(...))`.
  - `prompt` and `prompt_without_tool` are `date_line(..., tool_available=True|False)`.
  - `clock` is `clock_text(...)`.
  - All of these use `time_zones.utcnow()` and the effective zone.
  - `tool_enabled` is False only when a `tool_configs` row named
    `current_time` exists with `enabled` False.
    `ToolConfigRepository.get(name)` raises `KeyError` for a missing row
    (`repositories.py:~2318`); catch it, and treat a missing row as enabled.
    There are tests for a missing row, an enabled row and a disabled row.
  - A stored value that is garbage JSON, or names a zone not in the name set,
    makes the GET return the default (mode `system`). There is a test for each.
  - Tested with a monkeypatched clock and system zone, so assertions are exact.
- [ ] **AC10. `PUT /api/time-settings`**:
  - `{"mode": "zone", "zone": "Asia/Tokyo"}` saves and returns the GET shape,
    with `effective.zone` `Asia/Tokyo`.
  - `{"mode": "zone", "zone": "US/Pacific"}` is accepted, as an alias.
  - `{"mode": "system", "zone": "Asia/Tokyo"}` is accepted. The zone is kept
    in `zone`, and `effective` follows the system zone.
  - `{"mode": "system", "zone": null}` clears it.
  - **422 cases.** Each returns a `detail` that is a single plain-sentence
    string, never a list, and never echoes more than the offending zone value:
    - a malformed JSON body (not 500: `request.json()` is wrapped);
    - a non-object body;
    - extra keys;
    - an unknown mode;
    - `mode: "zone"` without a zone;
    - an unknown zone (`Mars/Olympus_Mons`, `localtime`);
    - a non-string zone (for example `5`), which gets the "Unknown time zone"
      sentence without echoing the value.
  - After a 422 the stored setting is unchanged, confirmed by a GET.
- [ ] **AC11. `GET /api/time-zones`** returns `{"zones": zone_rows(time_zones.utcnow())}`.
- [ ] **AC12. The routes sit behind the existing credential gate.** A request
      without a credential gets 401, tested like the neighbouring routes' auth
      tests (`tests/_credential_helpers.py`).
- [ ] **AC13. `/api/info`** gains these two keys, and its handler does no
      database or `tzlocal` read:
  - `date_prompt_example`: `render_date_line("{today's date}", "{time zone}", tool_available=True)`;
  - `date_prompt_example_without_tool`: the same with `tool_available=False`.

**Doctor**

- [ ] **AC14. `_probe_time_zones()`** returns
      `ProbeResult("time zones", ok, detail)`, never raises, and has an
      ASCII-only detail. `ok` is True only when all of these hold:
  - `canonical_zones()` has more than 300 entries;
  - `is_known_zone("localtime")` is False;
  - a `ZoneInfo` loaded explicitly from the tzdata package converts the
    instants correctly. It is loaded with
    `ZoneInfo.from_file(importlib.resources.files("tzdata.zoneinfo.America").joinpath("Los_Angeles").open("rb"))`,
    and `key=` set when the Python version supports it; otherwise it is wrapped
    in `EffectiveZone("America/Los_Angeles", that_zone)`. It must convert:
    - `2026-01-15T20:00:00Z` to 12:00 at `-08:00`;
    - `2026-07-15T19:00:00Z` to 12:00 at `-07:00`;
  - `tool_lines(<2026-01-15T20:00:00Z>, EffectiveZone("America/Los_Angeles", that_zone))[1]`
    equals `"Thursday, January 15, 2026, 12:00 PM PST (UTC-08:00)"`;
  - `date_line` of the same, with `tool_available=True`, starts with
    `"Today is Thursday, January 15, 2026 (America/Los_Angeles)."`.

  On success the detail reads like `"<N> zones (tzdata <IANA_VERSION>); system
  zone: <name or 'none detected'>"`. Detection never affects `ok`.
- [ ] **AC15. `run_doctor`** runs the gate unconditionally, prints it in the
      same format as the others, and includes it in the overall pass/fail.
  - The docstring is rewritten, not just re-counted: "Of those eleven … The
    other seven …", with the new gate in the unconditional list.
  - `tests/test_doctor.py`'s ordered gate-name list (~874-885) gains
    `"time zones"` last. The gate is left unstubbed: it is cheap. Direct tests
    cover an ok case, a failure (monkeypatch `canonical_zones` to a short list)
    and a never-raises case (monkeypatch it to raise). On the WSL host,
      `.venv/bin/python -m the_one doctor` prints `time zones: OK` and exits 0
      (if other gates pass on this host as before; compare with `main`).
- [ ] **AC16. The needle pair.** `"time zones: OK"` is appended **last** to
      `scripts/windows_test_copy.py::NEEDLES` and to the `foreach` list in
      `ci/tasks/windows-installer-build.yml`, and to
      add `grep -q "time zones: OK" doctor.out` after the window-chrome
      `grep -q` line in `.github/workflows/windows-installer.yml` (~132), where
      the needles are separate lines, not a list. Update the CI task's needle
      comment block too.
      `tests/test_windows_test_copy.py` passes. Any test there that counts
      gates (`gate_count`) is updated.

**Packaging**

- [ ] **AC17. `packaging/windows/the-one.spec`** collects
      `collect_data_files("tzdata")` into `datas`, and adds
      `collect_submodules("tzdata")` and `collect_submodules("tzlocal")` to the
      hidden imports. It carries a comment block in the spec's style explaining
      why: `importlib.resources` string access, `collect_data_files` skipping
      `.py`, `tzlocal`'s Windows module, and the frozen doctor as the judge. Any
      existing unit test that parses the spec still passes, including
      `tests/test_packaging_winpty_spec.py` and
      `tests/test_packaging_locked_closure.py`.

**Gates and docs**

- [ ] **AC18.** `make test-unit` is green, with the expected skip count
      unchanged apart from any new locale-skip, which the flight log explains.
      `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/` are
      clean.
- [ ] **AC19.** The docs are updated:
  - CLAUDE.md's doctor sentence names the new gate;
  - a CLAUDE.md Architecture paragraph names the module, the storage key, the
    three routes and `/api/info`'s two new keys;
  - `agents.md`'s gate list has the gate, plus the new "Time zones (M28)"
    section;
  - SECURITY-MODEL.md notes the routes sit behind the credential gate, and
    that zone strings are validated against a fixed name set, never used as
    paths.
  - The doc sites, in full:
    - CLAUDE.md line ~82 ("ninth gate … tenth");
    - `agents.md` ~1636 ("The ten gates"), the gate table (~1649, add a row)
      and the prose at ~1651 ("The ten gates", the "unconditionally" list,
      "separate from the ten gates").
- [ ] **AC20. The leaf check.** `the_one/time_zones.py` imports nothing from
      `the_one.agent`, `the_one.tools` or `the_one.interfaces` at module level.
      A test parses its imports with `ast` and asserts this.

## Verification Steps

- **AC1:**
  - `grep -n "tzdata\|tzlocal" pyproject.toml uv.lock`.
  - `curl -s https://pypi.org/pypi/<pkg>/<ver>/json | python3 -c "import json,sys; print(json.load(sys.stdin)['urls'][0]['upload_time'])"`.
  - `.venv/bin/python -c "import tzdata, tzlocal; print(tzdata.IANA_VERSION)"`.
- **AC2-AC8:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_time_zones.py -x --timeout 30`.
- **AC9-AC13:** `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_time_settings_api.py -x --timeout 30`.
- **AC14-AC16:**
  - `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_doctor.py tests/test_windows_test_copy.py -x --timeout 60`;
  - `.venv/bin/python -m the_one doctor; echo $?`, compared against
    `git stash`-free reasoning. Record the output in the flight log.
- **AC17:** read the spec diff, and run `grep -rn "the-one.spec" tests/` for
  any test that parses it.
- **AC18:** `make test-unit`, then `ruff check the_one/ tests/ scripts/ && ruff format --check the_one/ tests/ scripts/`.
- **AC19:** read the diffs.

## Implementation Guidance

1. **Dependencies first.**
   - Add the two lines to `pyproject.toml`, then run `uv lock` (`uv` is at
     `~/.local/bin/uv`) and check the upload dates (AC1).
   - If a version is under 14 days old, constrain it and re-lock.
   - **`.venv` is pip-managed.** Install only the two packages:
     `.venv/bin/pip install "tzdata>=2025.2" "tzlocal>=5.3"`, at the locked
     versions. Never run `uv sync` against it (it would reconcile and prune the
     venv), and never recreate the venv.
2. **`the_one/time_zones.py`.**
   - Keep it a leaf: the stdlib, pydantic, `tzlocal` and `tzdata` (lazily via
     `importlib.resources`). The DB repository is imported lazily inside
     `load_setting`/`save_setting`/`load_effective_zone`, as
     `prompt_layers.py` does.
   - Parse `tzdata.zi` line by line: lines start with `Z <name> …` or
     `L <target> <link>`; ignore everything else.
   - Use `functools.lru_cache` for the name set and the list.
   - `utcnow()` returns `datetime.now(timezone.utc)`.
   - Each formatter takes an aware `datetime` and converts with
     `now.astimezone(eff.tzinfo)`.
3. **The host-offset fallback for an unnamed system zone.** Use
   `datetime.now().astimezone().tzinfo` converted to a fixed
   `timezone(offset)`, evaluated at resolve time.
4. **The routes.**
   - Place them near `knowledge-settings` in `api.py`, using the same
     connection helper pattern as `_knowledge_settings_conn`/`get_connection`.
   - PUT:
     - Wrap `await request.json()` in try/except; malformed JSON gets 422.
     - Check the body is a dict and check its key set.
     - Construct `TimeZoneSetting` inside `try/except ValidationError`.
     - **Do not reuse `_validation_detail`** (`api.py:~134`): it returns a
       list. Classify each error by `e.errors()[0]`'s `loc` and `type`
       (literal error on `mode`; a string-type error on `zone`; the model
       validator's own errors, raised as `ValueError`s with stable message
       prefixes the model defines). Never match free-form message text you
       did not write.
     - Map the failure to one plain sentence:
     - "Unknown time zone 'X'. Use an IANA name such as Asia/Tokyo.";
     - "Choose a time zone when mode is 'zone'.";
     - "mode must be 'system' or 'zone'.";
     - "Body may contain only 'mode' and 'zone'."

     Truncate any echoed zone to 64 characters.
   - Use `ToolConfigRepository` (or the existing tool-config access in
     `api.py`) for `tool_enabled`.
5. **`/api/info`** (`app.py`, ~2621): import `render_date_line` and add the
   two keys.
6. **The doctor gate.**
   - Follow `_probe_fts5`'s shape and the ASCII-safe detail rule.
   - Find any test or CI step that hard-codes the gate count or the ordered
     gate list:
     `grep -rn "window chrome" tests/ ci/ scripts/ .github/ the_one/ CLAUDE.md`
     (the CLAUDE.md and agents.md sentences included). Update each.
7. **The spec.** Add beside the model-catalog block, with the same comment
   style.
8. **The `frozen_clock` fixture** in `tests/conftest.py`, **function-scoped**:
   - it monkeypatches `the_one.time_zones.utcnow` to return a fixed aware
     datetime (default `2026-10-10T22:45:12Z`), and
     `the_one.time_zones.detect_system_zone` to return `"America/Los_Angeles"`;
   - it yields the instant;
   - it is parametrisable through `request.param` or a small factory.

   Leg 2 relies on it. One test in `test_time_zones.py` proves
   `load_effective_zone` honours the patch.
9. **Docs** last: CLAUDE.md, `agents.md`, SECURITY-MODEL.md.

## Edge Cases

- **tzlocal on WSL** may return `Etc/UTC`, a real zone, or warn about a `TZ`
  mismatch. That is fine: return what it gives if known. Silence its warnings
  through `warnings.catch_warnings()`, so doctor output stays clean.
- **A stored setting naming a zone later removed from tzdata.** Load returns the
  default and logs a warning. The GET then shows mode system, and the stored
  value is not overwritten until the next PUT.
- **A PUT with a valid zone but `mode` missing** uses the model default,
  `system`. That is acceptable: the zone is kept.
- **`Etc/UTC`'s abbreviation** is `UTC`.
- **`clock_text` near the half-hour zones** (`Asia/Kathmandu`, +05:45): the
  minutes come from the converted datetime.
- **`tzlocal` freshness:** see AC4. An I/O call at most once a minute, on the
  event loop, is accepted.
- **`ZoneInfo.from_file` with `key=`** is Python 3.12+ only. The project floor
  is 3.11, so build the `EffectiveZone` wrapper instead of relying on the key.

## Files Affected

- `pyproject.toml`, `uv.lock`: the dependencies.
- `the_one/time_zones.py`: new.
- `the_one/interfaces/web/api.py`: the three routes.
- `the_one/interfaces/web/app.py`: the `/api/info` keys.
- `the_one/diagnostics.py`: the gate.
- `packaging/windows/the-one.spec`: data and hidden imports.
- `scripts/windows_test_copy.py`, `ci/tasks/windows-installer-build.yml`,
  possibly `.github/workflows/windows-installer.yml`: the needles.
- `tests/test_time_zones.py`, `tests/test_time_settings_api.py`: new.
- `tests/test_doctor.py`, `tests/test_windows_test_copy.py`, `tests/conftest.py`:
  updated.
- `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`: the docs.
- `missions/28-date-and-time/flights/01-agents-know-the-time/flight-log.md`:
  the leg entry.

## Citation Audit

Checked against `afa7855` while designing:

- `api.py::update_knowledge_settings` (2417) manual body checks and 422s;
  `_validation_detail` exists (used at ~2455).
- `app.py` `/api/info` return dict (2621-2633).
- `diagnostics.py::_probe_fts5` (476) shape; `run_doctor` (880).
- `scripts/windows_test_copy.py::parse_doctor` (545) gate regex.
- The CI needle `foreach` (`windows-installer-build.yml:114`).
- The spec's `collect_data_files` usage (117, 131).
- `AppMetadataRepository` (`repositories.py:2393`).

All present as cited.

---

## Post-Completion

Completion steps are Flight Control protocol, driven by the execution
workflow. They are not repeated here.
