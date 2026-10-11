# Mission Debrief: Agents Know the Date and Time

**Date**: 2026-10-11
**Mission**: [Agents Know the Date and Time](mission.md)
**Status**: completed
**Duration**: 2026-10-10 to 2026-10-11
**Flights Completed**: 2 of 2
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|---|---|---|
| Agents can tell the time from the first turn | met | `agent-tells-the-time` 8/8 on live `gpt-oss:20b`: web, connector, and an agent trimmed to `read_file`. |
| Agents can convert between zones | met | Tokyo conversion in behavior step 3; an unknown zone raises an `is_error` result. Unit tests. |
| Every conversation carries the current date | met | Refreshed on every build. Tool-aware wording, settle path included. One rare corner is open: if the build-time probe times out ("yes") and a chat-only model then turns out to be tool-less, the line names `current_time`. Squawk candidate. |
| The operator sets the zone once, and it holds | met | `/api/time-settings` plus the Date and time page; persists across restarts; a stored alias resolves. |
| The operator sees what agents see | met | The "What agents see" preview, from the server's own strings. |
| A browser/server mismatch is caught | met | Canonical comparison; the Kolkata and Oslo alias cases are tested. |
| The app and its agents agree on the time | met | `App.time` plus a static guard; Chats, messages and notes follow the zone. One corner: a zone the browser engine's Intl lacks falls back to browser-local, not the server offset. Squawk candidate. |
| Named zones work on every supported platform | met | Frozen Windows doctor, 11/11, `time zones: OK - 345 zones (tzdata 2026d); system zone: America/Chicago`. WebKitGTK is not probed. |
| The operator controls the time tool | met | The global toggle and the per-agent untick work on trimmed agents too (browser tests). |
| Upgrades need nothing | met | No migration; defaults to system mode; every agent gains the tool. |

### Overall Outcome

**Achieved.** Every success criterion is met. The two corners noted above are
edge cases, not failures of a criterion's main path. The outcome stayed the
right goal: the operator approved at the PR with "nothing notable", and it
shipped the same day as **v0.11.1**:

- PR #265, merged as `c6bbdc2`;
- PR #266, the version bump;
- tag `v0.11.1`, with `the-one-setup-0.11.1.exe` published.

## Flight Summary

| Flight | Status | Key Outcome |
|---|---|---|
| 1: Agents know the time | completed | `current_time` (exempt from trimmed lists, seeded); a date layer on every build; the setting API; tzdata and tzlocal plus the `time zones` doctor gate; a behavior test at 8/8; the frozen Windows build passes. |
| 2: The Date and time page | completed | The Settings page from the canvas; `App.time` zone-aware clocks with a bounded boot load; `App.ui.radioGroup`; canonical names from the server; a static local-time guard; the final gate `rc=0`. |

**Patterns across the flights:**

- **Both went smoothly against their design.** No divert criterion fired, and
  no leg aborted.
- **Both had their real escapes in data, environment or UX**, not in code
  logic:
  - Flight 1: numeric abbreviations (found by the behavior test) and the WSL
    netns gate setting (found after two red gates);
  - Flight 2: tzdata 2026 merged-city aliases (found by Architect cycle 2) and
    the "ko" search ranking (found by the FD's canvas comparison).

## What Went Well

- **The shape the operator chose: a canvas review first, then autonomous to
  one PR.**
  - The operator reviewed only at the design canvas and at the PR (plus a
    preview instance), and said it "worked well".
  - The canvas settled every visual decision before any code. Unlike Mission
    27's HAT reversals of autonomous UX calls (about 500 lines rewritten), no
    UX decision was reversed.
  - This directly answered Mission 27's top methodology observation
    ("autonomous UX judgement calls flow straight to implementation").
- **Design reviews that read real data.**
  - The Architect cycles found several defects by inspecting tzdata and the
    engines' Intl output, not just the code:
    - the Windows `strftime` failure that would have silently dropped the date
      layer;
    - the 30-second join stall;
    - `localtime` accepted as a zone name;
    - legacy browser aliases;
    - merged-city aliases.
  - The leaf-module design let Flight 2 extend Flight 1 purely additively.
- **Real-environment gates.** The live behavior test and the frozen Windows
  doctor each proved a criterion end to end. The doctor gate asserts exact
  output, which is what made the date layer's fail-soft catch safe to ship.

## What Could Be Improved

- **The host test environment didn't carry across missions.**
  - Mission 27 ran its gates with `THE_ONE_TEST_NETNS=1`; Mission 28 started
    without it.
  - Two red gates followed, with one wrong "host load" diagnosis.
  - About an hour of re-runs.
- **Design-time data sweeps were missing.**
  - Formatter and search rules were designed against exemplars.
  - Running them over the full zone set at design time, with a golden-query
    table for search, would have found the numeric abbreviations, the POSIX
    zones and the "ko" ranking before any code.
- **The crew can't see the canvas, and the gate is outgrowing its budget.**
  - The Developer's visual check was circular (against DD4's text), so UX
    defects surfaced only at flight end.
  - The local gate is about 21 minutes against a 20-minute target. Chats is
    over budget, agents is at 96%, settings at 88%.

## Lessons Learned

**Technical**
- **One authority, one seam.** One authority for zone identity (the server's
  `time_zones.py`) and one client rendering seam (`App.time`), with a CI guard,
  makes "the app follows your zone" an enforced property.
- **Four boundary couplings are still loose** (mission Architect):
  - the client regex-parses a display label (`UTC+05:30`) to get a machine key;
  - the clock format is implemented twice, Python and JS, with no parity pin;
  - an Intl `RangeError` falls back to browser-local instead of the server
    offset;
  - "can this agent call tools?" is decided twice, at build time capped and
    failing open, and again at turn time.

  The rule to keep: **prompt wording must be true under every fallback.**
- **"Frozen `core.py`: extend through the factory"** is now used three times
  (M23 connectors, M27 notes, M28 time). The baseline toolset is declared in
  three unconnected places (the seed tuple, the notes loop, the BASE_PROMPT
  prose). Consolidate them before #234 agent-to-agent adds a fifth tool family.

**Process**
- **Carry host prerequisites forward.** Write the gate environment into crew
  prompts and CLAUDE.md "Testing", not only into flight logs.
- **Visual review belongs to whoever can see the design.** Either export the
  canvas boards to images for the crew, or make the FD's screenshot comparison
  an explicit leg step.
- **Two Architect cycles plus per-leg Developer reviews paid off on shared
  state and UI legs** (the leg 2b save path, the F2 leg 3 view mode). They were
  partly redundant on additive server legs.

**Domain**
- **tzdata is not stable data.** 2026 releases merge cities into links (Oslo
  → Berlin) and reclassify POSIX zones. Browsers report legacy aliases
  (`Asia/Calcutta`, `UTC`), and engines differ (Chromium canonicalises an
  explicit `timeZone`, WebKit keeps it as given).
- **Store the name the operator chose, compare canonical names, and let only
  the server decide what is canonical.**

**Reusable patterns** (for `agents.md` Project Conventions, next maintenance
pass):
- a leaf domain module with seams read at call time, plus an ast
  import-direction pin;
- an app-wide setting as an `app_metadata` key, `GET`/`PUT`, and a server
  preview;
- preview strings come from the production function;
- one client seam plus a static guard;
- doctor gates assert exact output;
- client-mirrored constants and formatters carry a parity pin;
- prompt wording must be true under every fallback.

**Documentation**
- **CLAUDE.md:** the stale M28 lines are squawk 0173. The "Testing" section
  needs `THE_ONE_TEST_NETNS=1` as a standing gate prerequisite, and an updated
  skip count (squawk 0167).
- **README** was updated in Flight 2. Nothing further is needed.

## Methodology Feedback

| # | Finding | Flights | Destination |
|---|---|---|---|
| 1 | The flight skill carries no host-environment prerequisite across missions | F1 (paid), F2 (carried by hand) | Methodology observation |
| 2 | No gate-flake triage rule in leg execution | F1, F2 | Methodology observation |
| 3 | Crew agents cannot open claude.ai design canvases | F2 (and the F1 canvas premise) | Methodology observation |
| 4 | The pinned-count sweep is unreliable when done by reading | F2 | Methodology observation |
| 5 | Per-leg Developer reviews partly redundant after two Architect cycles | F1 | Local lesson |
| 6 | Leg identity drifts when a leg is split mid-design | F1 | Local lesson |
| 7 | The Review prompt omits `-m browser` for browser file paths | F2 | Local fix (squawk 0181) |
| 8 | Canvas review plus autonomous-to-one-PR resolved M27's "autonomous UX calls" observation | F1, F2 | Reference point (positive) |

These restate observations the flight debriefs already hold. A sweep should
count each once.

### 1. No host-environment prerequisite across missions
- **What happened:** at Pre-Flight, the flight skill and the agentic-workflow
  spawn prompts re-verified external sessions (Ollama, the Windows desktop).
  They did not carry the gate environment Mission 27 had established
  (`THE_ONE_TEST_NETNS=1`).
- **Expected:** a standing "host test environment" prerequisite, inherited
  from the previous mission or from CLAUDE.md.
- **Cost:** about 3 extra full gates (about an hour), plus one wrong
  root-cause diagnosis in a leg's flight-log entry.
- **Skill:** flight (Pre-Flight prerequisites); agentic-workflow (Phase 2b
  spawn prompts). Plugin 1.2.0.
- **Recurrence:** 1 paid occurrence (F1). F2 carried it by hand as an FD host
  rule.

### 2. No gate-flake triage rule
- **What happened:** each red parallel gate needed FD improvisation: an
  isolated lane re-run, then single tests, then a disposition.
- **Expected:** a written rule. A known squawk counts as accepted; anything
  else is a regression until an isolated re-run clears it.
- **Cost:** inconsistent dispositions. F1 leg 4 called it "host load"; it was
  networking.
- **Skill:** agentic-workflow, Phases 2b and 2d. Plugin 1.2.0.
- **Recurrence:** F1 (3 red gates), F2 (2 gates with known flakes).

### 3. Crew agents cannot open design canvases
- **What happened:** the mission's UI criterion depended on an approved
  claude.ai canvas. F2 leg 3's AC14 comparison was assigned to the Developer,
  who could only compare against DD4's text. The FD then compared the
  screenshots with the canvas and found the search-ranking defect and the
  hint-placement deviation.
- **Expected:** the flight skill either exports the canvas boards as images
  for the crew, or assigns visual comparison to the FD in the leg.
- **Cost:** two UX defects found only at flight end, and one extra review and
  fix round.
- **Skill:** flight (verification design); agentic-workflow (leg assignment).
  Plugin 1.2.0.
- **Recurrence:** F2.

### 4. The pinned-count sweep is unreliable when done by reading
- **What happened:** the leg design-review prompts asked for "every pinned
  list". Two count pins (asset refs, the palette cap) were still missed and
  found by the gate.
- **Expected:** a mechanical grep for numeric pins tied to the changed
  collection, as a 2a risk check.
- **Cost:** one extra gate run.
- **Skill:** agentic-workflow 2a (leg risk checks). Plugin 1.2.0.
- **Recurrence:** F2. A similar miss in F1, the badge-count contract test, was
  also found by the gate.

### 5 to 8
- **5 (local lesson):** keep two Architect cycles for flights that cross a
  shared interface, and make the per-leg Developer review conditional on the
  leg changing approach or touching shared state or UI.
- **6 (local lesson):** renumber leg files when a split happens.
- **7 (local fix):** squawk 0181.
- **8 (reference point):** evidence that front-loading a visual review fixes
  Mission 27's observation 1, with zero UX reversals.

## Action Items

- [ ] **Next step (operator decision):** a squawk turnaround. Open squawks:
  - 0168 and 0171 (gate flakes);
  - 0172 to 0181 (this mission's follow-ups);
  - 0167, 0169.
- [x] **Logged as squawks** (operator approved, 2026-10-11):
  - **0182:** date-line truth under a probe fallback, and preview clock parity;
  - **0183:** client zone fallback to the server offset, and a structured zone
    key;
  - **0184:** invalid JSON returns 500 on most API routes.
- [ ] **The base-prompt "only `search_tools` and `continue`" sentence**
      (operator decision): route it with **#259 prompt evals**, not a
      standalone squawk.
  - The mission Architect dissented. It would have preferred a minimal
    factual squawk now, with #259 owning any broader rewrite.
  - #259 should take it as an early eval case, together with the date-line
    wording and the `current_time` description.
  - `agent-tells-the-time` is a ready seed scenario.
- [ ] **Maintenance mission, after the squawk turnaround:**
  - lane re-budget or split (chats, agents, settings) to get back under the
    20-minute gate;
  - server-sent tool-gating policy plus one declared baseline toolset, tied to
    BASE_PROMPT by a test, **before #234**;
  - owner-scoped subscriptions for `App.store`/`App.time`;
  - the `searchList` options and a shared ranking helper;
  - a WebKitGTK probe of `App.time`;
  - document the conventions listed above in `agents.md`;
  - `THE_ONE_TEST_NETNS=1` in CLAUDE.md "Testing";
  - consider making `frozen_clock` autouse in the prompt and factory test
    modules.
- [ ] **Local crew file:** add `THE_ONE_TEST_NETNS=1`, the `-m browser` note
      and a gate-flake triage rule to `.flightops/agent-crews/leg-execution.md`
      (with squawk 0181).
