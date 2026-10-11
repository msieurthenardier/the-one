# Flight Debrief: Agents Know the Time

**Date**: 2026-10-11
**Flight**: [Agents Know the Time](flight.md)
**Status**: landed
**Duration**: 2026-10-10 to 2026-10-11
**Legs Completed**: 4 of 4. Leg 2 was split at design review into 2a
(server) and 2b (client), and the files are numbered 01-04.
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved

Every agent now has a reliable "now", controlled by one operator time-zone
setting.

- **`current_time` built-in tool.**
  - It is seeded into every agent's starting toolset and exempt from a trimmed
    `enabled_tools` list.
  - It still honours `disabled_tools` and the global toggle.
- **Date prompt layer.**
  - It is appended on every build (new chat, rejoin, connector message, settle).
  - It names the tool only when the agent can call it.
- **Setting and API.** The setting is stored in `app_metadata`, behind
  `GET`/`PUT /api/time-settings` and `GET /api/time-zones`. Zone names are
  validated against tzdata's name set, never resolved as paths.
- **Windows.** `tzdata` and `tzlocal` are bundled into the PyInstaller build,
  and a new unconditional `time zones` doctor gate checks the data **and** the
  formatted strings.
- **"Time" tool category** on Settings › Built-in tools and the agent Tools tab.
- Merged in PR #265 (`c6bbdc2`), released as v0.11.1.

### Mission Criteria Advanced

These were met and checked in the mission:

- agents can tell the time from the first turn;
- agents can convert between zones;
- every conversation carries the current date;
- named zones work on every platform;
- the operator controls the time tool;
- upgrades need nothing.

**Evidence:**

- `agent-tells-the-time` passed 8/8 against live `gpt-oss:20b`;
- the frozen Windows doctor passed all 11 gates, with `time zones: OK - 345
  zones (tzdata 2026d); system zone: America/Chicago`;
- unit tests.

## What Went Well

- **The design reviews caught three defects that would have shipped silently**
  (Architect cycle 1):
  - `strftime` `%-d`/`%A`/`%p` would have raised on Windows, or localised the
    output. The date layer's catch-all would then have hidden it, and every
    Windows user would have silently lost the date line.
  - An uncapped `supports_tools` call could stall every join and connector
    message by up to 30 seconds.
  - `localtime`/`posixrules` were accepted as zone names on Linux.

  Cycle 2 caught "opened" versus "last loaded" in the wording, which would
  have told the model something false.
- **The doctor gate asserts exact output, not presence.** It proved formatting
  and data on the frozen Windows build first time, with no packaging fix
  needed.
- **A leaf module with seams read at call time** (`time_zones.utcnow`,
  `detect_system_zone`) made the tests deterministic with no mock libraries.
  Flight 2 extended it purely additively.
- **The behavior test discriminated where it mattered.**
  - The far zone, Kiritimati +14, separated the host date from the zone date.
  - Step 5 proved the tool-free wording alone gives the right date.
  - Step 4 proved the whitelist exemption live.
  - It also found the numeric-abbreviation defect.
- **The operator's working shape was confirmed:** a canvas review first, then
  autonomous execution to one PR, reviewed at the end. The operator said it
  "worked well".

## What Could Be Improved

### Process
- **The gate environment was not carried forward from Mission 27.**
  - Mission 27's green gates ran with `THE_ONE_TEST_NETNS=1`; this flight's
    gates did not.
  - Two gates (leg 2b, leg 4) came back red with scattered `wait_settled`
    timeouts. Leg 4 attributed them to host load, wrongly.
  - The FD rejected that and re-ran on a quiet host (still red), then with
    netns (green apart from squawk 0168).
  - **Cost:** about three extra full gates (roughly an hour) and one wrong
    diagnosis.
- **Gate-flake triage was improvised** (an isolated lane re-run, then single
  tests). No written rule exists.
- **Leg numbering drifted** after the split (flight says 2a/2b, files say
  02/03, the log says "Leg 3 (leg 2b)"). This is cosmetic, but it confused
  cross-references.
- **Line-number citations went down to individual assertions** (a 760-line
  flight.md). They go stale fast and roughly double the review surface.

### Technical
- **`WHITELIST_EXEMPT_TOOLS` is the fourth tool-gating special case**, and the
  client copies the rule in three places:
  - `whitelistExempt` is pinned against Python;
  - `UNGATED_PREFIXES` in `agent-drawer.js` is not pinned;
  - the Tools-tab note is time-specific.
- **Every built system prompt now depends on the clock and the zone.** Any
  whole-prompt assertion needs `frozen_clock`, and `load_effective_zone`'s
  never-raise guard hides `AsyncMock` wiring mistakes as RuntimeWarnings.
- **Numeric-abbreviation handling is split.** The server drops it only in the
  tool formatter, while the `/api/time-settings` and `zone_rows` abbreviation
  fields return raw `tzname()`, and Flight 2 drops it again on the client.
- **`tzdata<2026.5` cap** (the soak rule) has no tracked follow-up.
- **Per-build latency floor:** `time_tool_available` awaits `supports_tools`
  (capped at 2 s, failures not cached) on every build.

### Documentation
- **Stale CLAUDE.md text:**
  - "Nothing here changes how agents are built yet" (since leg 2);
  - "seeded into every turn", which should read "starting toolset".
- The base prompt's "only `search_tools` and `continue`" is now inexact for
  three seeded tool categories. It was flagged at the PR and left unchanged.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Leg 2 split into server and client at Architect cycle 1 | Leg 2 touched about 15 test files plus a UI surface | Yes: split at a shared-interface/UI seam |
| Windows half of leg 4 run in parallel with leg 2b | It only depended on packaging, and saved a sequential slot | Yes, when the dependency is genuinely disjoint |
| Numeric-abbreviation fix-forward in leg 4 | The behavior test exposed it | Yes: the AC5 fix-forward rule worked |
| `THE_ONE_TEST_NETNS=1` adopted mid-flight | WSL mirrored networking | Yes: make it a standing gate prerequisite |
| A trimmed agent keeps the time tool (operator decision) | A new built-in otherwise misses trimmed agents | Yes, documented in `agents.md` |

## Key Learnings

- **Design-time data sweeps find what design reading doesn't.** Running the
  formatter over every canonical zone's `tzname()` would have found the
  numeric abbreviations and the POSIX zones at planning.
- **Flight 1 locked the `/api/time-zones` shape without alias metadata.** The
  mission already knew the browser and server zone lists differ. Design server
  contracts that feed a browser with engine divergence in mind.
- **Host-environment prerequisites must carry across missions** like any other
  prerequisite. A host rule that lives only in an earlier mission's logs is
  lost.
- **Test metrics** (final gate on merged `main`, netns, WebKit required):
  - **Unit:** 5932 passed, 14 skipped, 218 s. Against Mission 26 (about
    190 s, 5625 tests) that is +5% tests and +15% time; the new static and
    tzdata tests, and per-build date work in the factory tests, explain part of
    it.
  - **Browser:** `rc=0`, 1055 s. Lanes:

    | Lane | Wall (s) | Budget (s) |
    |---|---|---|
    | routing | 489 | 600 |
    | settings | 477 | 540 |
    | agents | 489 | 510 |
    | chats | **364** (over) | 360 |
    | mcp | 332 | 360 |
    | library | 253 | 300 |
    | shared | 269 | 300 |
    | contracts | 234 | 270 |

  - **Total:** about 21 minutes, against Mission 26's 20-minute target, which
    is no longer met.
  - **Flakes:** none this run. Squawks 0168 and 0171 recurred in earlier
    mission gates.
  - **Skips:** 14 = 10 baseline + 1 new locale skip + the netns root-only
    skips. CLAUDE.md's "10" is stale; squawk 0167 already exists.

## Methodology Observations

- **The flight skill's prerequisites carry no host-environment section.**
  - **What happened:** at Pre-Flight, the flight skill and the agentic-workflow
    crew prompts verified external sessions (Ollama, the Windows desktop). They
    did not carry the gate environment Mission 27 had established
    (`THE_ONE_TEST_NETNS=1`).
  - **Expected:** a standing "host test environment" prerequisite, read from
    the previous flight or mission logs or from CLAUDE.md.
  - **Cost:** about three extra full gates (about an hour) and one wrong
    root-cause diagnosis.
  - **Skill:** flight (Pre-Flight prerequisites), and agentic-workflow (the
    Developer spawn prompts). Plugin 1.2.0.
- **No gate-flake triage protocol.**
  - **What happened:** each red parallel gate needed the FD to improvise: an
    isolated lane re-run, then single tests, then a disposition.
  - **Expected:** a written rule in leg-execution: re-run failures in
    isolation; a known squawk counts as accepted; anything else is a
    regression until proven otherwise.
  - **Cost:** inconsistent dispositions between legs. Leg 4 called load where
    the cause was networking.
  - **Skill:** agentic-workflow, Phase 2b/2d. Plugin 1.2.0.
- **Per-leg Developer design reviews were partly redundant after two Architect
  cycles.**
  - **What happened:** leg 1 and leg 2a reviews returned "approve with
    changes, detail only", which was real but small. The leg 2b review (UI
    save path) earned its cost.
  - **Expected:** a lighter checklist review for legs that don't change
    approach or touch shared state.
  - **Cost:** about 2 reviews' worth of tokens and time.
  - **Skill:** agentic-workflow 2a (risk tiering). Plugin 1.2.0.
  - **Note:** this was one flight, so it is recorded rather than judged.
- **Leg identity drifts when a leg is split mid-design.**
  - **What happened:** the flight says 2a/2b, the files say 02/03, and the log
    uses both.
  - **Expected:** the skill renumbers leg files when a split happens.
  - **Cost:** cosmetic confusion.
  - **Skill:** flight, Phase 5b. Plugin 1.2.0.
- **The reviewer prompt does not say browser tests need `-m browser` when
  passed by path.** (Seen in Flight 2's review, recorded here as a
  project-crew gap.) It is a local crew-file fix.

## Recommendations

1. **Make `THE_ONE_TEST_NETNS=1` a standing gate prerequisite.** Put it in
   `.flightops/agent-crews/leg-execution.md`'s Implement prompt and CLAUDE.md
   "Testing". Better still, have `run-tests.sh` warn or refuse on WSL mirrored
   networking when it is unset.
2. **Move tool gating to server-sent policy**, following the M24
   `compute_tool_names` precedent, before a fifth special case lands. Until
   then, pin `UNGATED_PREFIXES` the way `whitelistExempt` is pinned.
3. **Add a design-time "data sweep" step** for any formatter or rule over a
   dataset (time zones, locales, providers): run it over the whole set, not one
   exemplar.
4. **Write a gate-flake triage rule** in leg-execution.md.
5. **Lane budgets:** re-budget or split `chats` (over budget), `agents` (96%)
   and `settings` (88%), and refresh CLAUDE.md's "measured" column.

## Action Items

- [x] Logged as squawks (operator approved, 2026-10-11):
  - **0172** lift the `tzdata<2026.5` cap;
  - **0173** the stale CLAUDE.md M28 lines;
  - **0174** pin `UNGATED_PREFIXES`;
  - **0175** unify numeric-abbreviation handling server-side.
- [ ] Squawk 0167 (existing): the CLAUDE.md skip count. It is now 14 under
      netns.
- [ ] Next maintenance pass:
  - lane re-budget or split;
  - the gating-policy refactor;
  - document "doctor gates assert exact output", "preview strings come from
    the production function" and "client-mirrored constants carry a parity
    pin" in `agents.md` Project Conventions.
- [ ] Mission debrief: decide whether to reword the base prompt's "only
      `search_tools` and `continue`" sentence.
