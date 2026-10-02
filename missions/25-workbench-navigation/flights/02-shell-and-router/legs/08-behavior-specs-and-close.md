# Leg: behavior-specs-and-close

**Status**: completed
**Flight**: [Shell and Router](../flight.md)

## Objective

Bring the behavior-test corpus onto the workbench and close the flight:
- update the data-independent `shell-navigation-smoke` spec for the rail;
- author the new `workbench-navigation` spec, the flight's behaviour gate;
- update the step text of every spec that names the old navigation;
- run the full flight-close verification.

The Flight Director runs the behavior tests themselves after this leg lands. Crews
cannot invoke the behavior-test skill.

## Context

- **Flight decision:** DD10 is this leg's spec: which specs are updated, rewritten or
  authored, what `workbench-navigation` covers, and which specs run in this flight.
  Read it in `flight.md`.
- **Spec format:** `.flightops/ARTIFACTS.md` "Behavior Test — Spec". Authoring guide:
  `~/.claude/plugins/cache/flight-control/mission-control/1.2.0/skills/behavior-test/AUTHORING.md`
  (read it as a file; do not load skills). Project conventions: CLAUDE.md
  "Behavior-test credential convention" (dedicated dev instance, handoff mint, never
  8484) and `the_one/agents.md` "Browser apparatus doctrine" (goldfinch limits).
  Flight 1's run noted that screenshots were unavailable on this host, so the PDF,
  accessibility tree and computed-style evidence paths are expected.
- **Existing specs:** `tests/behavior/*.md`. The router research and DD10 list which
  steps name the old places:
  - `#admin/…`, `#studio/…`;
  - "Agent Studio", "System", "Administration";
  - the top-bar picker.
- **The final UI after legs 1–7:** read the leg entries in the flight log. The specs
  must match what the app actually renders: rail labels, section-nav labels, routes and
  the copy strings.

## Inputs

- `tests/behavior/shell-navigation-smoke.md` and its last run log, which carries
  spec-quality notes from the Validator: rephrase the step-6 "banner"; list Connectors.
- The specs: `system-provider-config`, `save-preserves-config`,
  `stub-connector-round-trip`, `studio-agent-crud`, `agent-retention-setting-roundtrip`,
  `agent-purge-now-clears-history`, `anthropic-plan-signin`,
  `agent-governance-and-search`, `kb-studio-round-trip`, `anthropic-plan-chat-parity`.
  Soft mentions: `chat-roundtrip`, `extended-thinking-tool-turn`,
  `windows-native-frame-splash` (`#app-topbar` → the rail), and any others a grep finds.
- The running app (dev instance on 8485, scratch data dir, dev mode). Use it to confirm
  labels and routes as you write steps.

## Outputs

- **`tests/behavior/shell-navigation-smoke.md`** updated: rail with four destinations,
  each one's section navigation or empty state, theme flip and restore (Settings ›
  General), and a cold deep link through a legacy and a new route. It stays
  data-independent and read-only.
- **`tests/behavior/workbench-navigation.md`** (new), per DD10. It covers:
  - **Setup:** seed through the API one mock provider, one agent and one KB.
  - **Navigation:**
    - each destination's section navigation;
    - Back stepping between two opened items;
    - the rail restoring the last-open item;
    - legacy deep links redirecting (`#admin/providers`, `#studio/agents/{name}/tools`).
  - **Leave guard:**
    - a dirty editor asks before leaving via the rail and via browser Back;
    - Stay keeps the edit, focus returns, and the URL is unchanged;
    - Continue discards: re-opening shows the saved value.
  - **Variants:** dark and light themes.
- **Step text updated** in every listed spec, plus the soft mentions. Only navigation
  wording and routes change; each spec's intent and its other steps stay.
- **`tests/behavior/README.md`**, or the spec index if one exists: updated.
- **Flight-close verification**, recorded in the flight log:
  - `make lint`;
  - `make test-unit`;
  - all five lanes, one at a time;
  - every `test_ui_*` in both engines;
  - the WebKitGTK probe at `#agents` and `#settings/general`.
- **Flight log:** the leg entry. List every spec touched and what changed.

## Acceptance Criteria

- [x] **AC1 — `shell-navigation-smoke` updated.**
  - Its steps reference the rail, never "Agent Studio" or "System" as areas.
  - It folds in the Validator's notes: the step-6 wording, Connectors listed (or the
    Library sections).
  - Cold deep links cover `#settings/providers` and the legacy `#admin/providers`
    (redirects).
  - It stays data-independent: every step accepts populated or empty state.
  - `Status: active`.
- [x] **AC2 — `workbench-navigation` authored** to the ARTIFACTS.md format.
  - Every Expected Result names an observable, and steps are state transitions in the
    CLAUDE.md HAT style.
  - Setup rows seed via the API using the credential convention.
  - The Preconditions name a dedicated dev instance (port and scratch data dir), never
    8484.
  - It has a dark/light **Variants** section.
  - Focus-related checks state the apparatus: goldfinch cannot observe
    `:focus-visible`, so assert `document.activeElement` identity.
- [x] **AC3 — Step-text updates.** Every listed spec and soft mention references the new
  navigation:
  - destinations: Chats, Agents, Library, Settings;
  - routes: `#settings/providers`, `#agents/{name}/…`, `#library/…`;
  - section labels as rendered.

  `grep -rn "Agent Studio\|#admin/\|#studio/\|app-topbar\|Administration" tests/behavior/*.md`
  returns only deliberate legacy-redirect references. Each of those is explicitly
  labelled as a redirect check.
- [x] **AC4 — Labels verified against the app.** A short table in the flight log maps
  each label and route used in the specs to where it was observed in the running dev
  instance (DOM text or `aria-label`).
- [x] **AC5 — Flight-close verification.** All gates are green and recorded with counts
  and durations. Failures are re-run alone, and environmental network flakes are
  classified as such.

## Verification Steps

- AC1–AC3: read the specs, then run the grep in AC3.
- AC4: the flight-log label table.
- AC5: the commands listed.

## Implementation Guidance

1. **Start the dev instance** (8485, scratch, dev mode; create the credential first) and
   walk the rail to collect the exact labels and routes.
2. **Update `shell-navigation-smoke`**, then author `workbench-navigation`.
3. **Sweep the other specs** with the grep, updating navigation wording only.
4. **Flight-close gates.**
5. **Stop the instance** and remove the scratch directory.

## Edge Cases

- **Live-credential specs** (`anthropic-plan-*`, `discord-live-round-trip`): update the
  wording only. They are run at mission end by the operator.
- **Archived specs:** leave them alone.
- **A spec with no navigation wording:** leave it untouched.

## Files Affected

- `tests/behavior/shell-navigation-smoke.md`, `tests/behavior/workbench-navigation.md`
  (new), and the listed specs
- `missions/25-workbench-navigation/flights/02-shell-and-router/flight-log.md`

## Citation Audit

The spec list comes from the router research (`fe595cc`) and DD10. Re-grep
`tests/behavior/*.md` at the start of the leg.

---

## Post-Completion

Completion steps — status transitions, flight-log update, checking off in the parent
flight, and commit — are Flight Control protocol, driven by the execution workflow. Not
repeated here.
