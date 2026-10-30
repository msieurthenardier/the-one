# Flight: HAT and Alignment

**Status**: landed
**Mission**: [Routines](../../mission.md)

## Contributing to Criteria

This flight closes the mission. Flights 1-3 built every criterion and landed
on automated gates and behavior tests, with no HAT legs of their own
(operator decision). No mission criterion is ticked yet: the walk with the
operator is what ticks them (DD7 names the step behind each verdict).

- [ ] The operator manages an agent's routines.
- [ ] Routines run on time, unattended (including across a restart).
- [ ] The reply lands in the target, **including a real Discord DM** (the
      behavior test proved only the stub connector, whose DM `channel_id`
      is `""`; Flight 1 debrief, Recommendation 4).
- [ ] A routine's message says it came from the routine.
- [ ] Unattended runs are honest (caught up, missed, still running, chat
      gone, interrupted, stopped, failed).
- [ ] The Self-configuration tab governs two things.
- [ ] An agent schedules its own routines when allowed.
- [ ] Agent routine changes are overseen.
- [ ] Injected content cannot plant a routine unnoticed, and routines are
      bounded.
- [ ] Routines follow their agent.
- [ ] Every open judgement call (Flight 1 *(autonomous judgement call)*,
      Flight 2 *(J)*, Flight 3 *(FD)*) is confirmed or reversed by the
      operator.

---

## Pre-Flight

### Objective

A guided human acceptance test of the whole Routines mission, with the
operator present and driving their own browser. The walk takes routines end
to end: the Routines tab and its recurrence form, unattended runs into web
chats and a real Discord DM, catch-up across a restart, an agent scheduling
its own follow-ups on a live model, approval mode, flagging, retention and
the agent lifecycle. It confirms or reverses every judgement call made
without the operator, the costly ones first. It fixes what surfaces:
look-and-feel fixes inline, new behaviour through the fix-vs-feature gate.
It ends on a green quiet-host gate, so the mission debrief can follow.

### Inputs

- `main` at `7dd144d5`: Flights 1-3 (Flight 1's merge `6ed89395`, PRs #336
  and #338) and the squawk turnaround #339 (0286, 0287), so HAT fix
  Developers run under the no-scripted-rewrites rule.
- **Judgement-call sources:**
  - Flight 1: `../01-operator-routines/flight.md` (DDs marked *(autonomous
    judgement call)*) and its debrief's Recommendation 4.
  - Flight 2: `../02-agent-routines/flight.md` (*(J)*) and its debrief's
    Action Items (the Architect's list of 16).
  - Flight 3: `../03-schedules-and-limits/flight.md` (*(FD)*), its flight log
    (leg 7's "Left for Flight 4's walk") and its debrief's Recommendation 2.
- **Behavior-test run logs** (the automated evidence the walk confirms):
  - `tests/behavior/routine-connector-delivery/runs/2026-10-29-20-59-19.md`
    (8/8, stub connector);
  - `tests/behavior/agent-schedules-follow-up/runs/2026-10-29-21-06-42.md`
    (7/7, `gpt-oss:20b`).

### Open Questions

- [x] **Provider** (operator, planning): Claude Haiku through the
      Anthropic API (the `anthropic` provider type). The operator enters
      the API key in the dev instance's provider form; the Flight Director
      never handles it.
- [x] **Discord** (operator, planning): the operator's own Discord account,
      and the bot of their installed instance, which they have quit
      (`127.0.0.1:8484/api/live` refused from WSL at planning) → DD3.
  - The HAT driver and main bots in `tests/behavior/.env.hat` are deleted:
    both tokens return 401 from `GET /users/@me` (checked at planning,
    tokens never printed).
- [x] **Squawks 0286 and 0287** (operator, planning): turned first, merged
      as #339.
- [x] **The bot token** (operator, at approval): the operator creates a new
      one in the Developer Portal, so the installed instance's connector
      needs the new token before it is next used. The operator pastes it
      into the dev instance's form; the connector's status in D2 is the
      check. Never pasted into this conversation.
- [x] **The upgrade clauses** ("every existing agent keeps exactly its current
      self-configuration behaviour through the upgrade"; "existing installs
      upgrade with no data loss") (operator, planning): the migration tests
      (`TestSchemaV45`-`V48`) are the evidence, recorded as such in the
      criterion verdicts. No upgrade walk.
- [ ] **Mid-walk decisions:** each judgement call in DD4, confirmed or
      reversed in the walk and recorded in the flight log.

### Design Decisions

#### DD1. One interactive leg, a state-transition walk

- The walk follows CLAUDE.md "HAT Design Guidance": each step names its
  transition and asserts the UI, the error area and the button states,
  with negative assertions ("no errors", "no second reply").
- **Costly calls first** (Flight 3 debrief, Recommendation 2). Part B
  settles the schedule rules that are expensive to reverse once routines
  exist. The form's preview line ("{sentence}", "Next: {date and time}",
  "Last: {date}", `routines-describe.js::describePreview`) and the routine
  rows show them, so they need little or no waiting. Each step gives a
  recipe whose two candidate rules give *different* observations.
- **Shared state the operator is not looking at.** At least one run lands
  in a chat open in a second tab, and the Discord runs land in a client
  that is not the app.
- **Time can't wait.** Runs are made due with **Run now**, a start a few
  minutes ahead, or a short repeat. No test seam is needed.
- **Every routine the walk makes is turned off or deleted once its step is
  done** (a one-off left in place really runs, e.g. B4's "tomorrow at
  9:00 AM"), so the instance's scheduler is quiet between steps.
- **Run history shows an outcome label, not the stored reason** for `ok`,
  stopped and interrupted runs (C14). Steps expect what the screen shows.
- The walk is long. It may span sessions; the flight log records where it
  stopped.

#### DD2. The environment

- A dev instance from this branch on **port 8490** (8484 and 8485 are
  refused), a scratch data dir `$HOME/the-one-hat-m33/data` and a scratch
  cwd `$HOME/the-one-hat-m33/cwd`. Its PID is recorded, and it is stopped by
  that PID. The FD reads `/proc/<pid>/environ` and `/proc/<pid>/cwd` before
  the walk, and the default data dir is read from settings, never guessed.
- `THE_ONE_DEV_MODE` is off, so the operator sees the product as shipped.
  No test seam is needed (DD1).
- The operator browses through a handoff link minted by the FD
  (`POST /api/session/handoff`, CLAUDE.md "Behavior-test credential
  convention"), in their own browser. A restart (Part H, or a Python fix)
  needs a fresh handoff link.
- **Provider:** Claude Haiku over the Anthropic API, entered by the
  operator. The time zone is the operator's (Settings › Date and time).
- **A Python change** to fix something needs a restart of this instance
  (CLAUDE.md "Local dev"); JS and CSS are live after a hard reload.
- **Secrets teardown.** The scratch data dir holds the operator's API key
  and bot token beside the Fernet key. At flight end, after the dev
  instance is stopped, `$HOME/the-one-hat-m33` is deleted (the FD confirms
  the path first).

#### DD3. Discord: the installed instance's bot, one gateway at a time

- Only the dev instance's gateway may be connected: two instances on one
  bot would both receive the DM and both reply. The operator has quit the
  installed (production) instance for the walk. Closing its window is not
  enough: it hides to the tray with its gateway connected. D1 checks it is
  really quit (`127.0.0.1:8484/api/live` refused from WSL, or no app
  process in Task Manager).
- The operator pastes the bot token into the dev instance's connector form
  (Library › Connectors). The FD never reads the installed instance's data
  directory or its stored secrets.
- **Pairing.** A new connector has an empty allowlist, and
  `connectors/inbound.py::is_admitted` silently drops a DM from a peer that
  is not on it. The operator generates a pairing code in the connector
  editor's Pairing section and DMs it to the bot (10-minute TTL, in memory;
  no reply is expected). Only then does a real DM get an answer.
- The DM resolves to the connector's `default_agent` (Flight 1: a DM channel
  is never in `channel_map`), so the routine's agent is the connector's
  default agent. That is also the agent that "answers the channel" (Flight
  1's pre-check).
- The dev connector is deleted at F2 (after the rename check), before the
  operator restarts the installed instance.
- **Allowlist check.** `update_connector` replaces `config` whole and the
  connector editor sends the allowlist from its form, so an editor opened
  before pairing would wipe the paired peer on Save (squawk 0288). At D2
  and D5, Allowlist peers must show the operator's Discord user id before
  any Save.

#### DD4. The judgement calls, grouped by cost

Each is confirmed or reversed in the walk at the step named, and recorded in
the flight log with the operator's words. A reversal that changes behaviour
goes through the fix-vs-feature gate (DD6); a reversal of C7, C8 or C9 also
touches `SECURITY-MODEL.md` "Routines" and the eval contract (DD5).

**Costly (data and behaviour; expensive to reverse once routines exist):**

| # | Call | Source | Walk |
|---|---|---|---|
| C1 | "Ends after N" counts every occurrence from the start: missed, off and pre-save ones included (the operator chose "count from start" in F3 planning; confirm it in use) | F3 DD2 | B2 |
| C2 | Turning a minute/hour routine back on continues its original grid | F3 DD2 *(FD)* | B3 |
| C3 | A zone change keeps a one-off's instant and the wall-clock time of daily-and-longer routines; pending proposals are rebased across it (no proposal exists in Part B: the rebase clause rests on the Flight 3 tests unless the operator asks to see it in Part E) | F3 DD12 *(FD for the rebase)* | B4 |
| C4 | "Every N weeks" counts weeks Sunday-first | F3 DD2 *(FD)* | B2 |
| C5 | A start that does not match its own rule only begins the series | F3 DD2 *(FD)* | B2 |
| C6 | Legacy request shapes are accepted on input (retirement is Mission 34+) | F3 DD5 *(FD)* | J |
| C7 | Every routine write from a connector chat carries `peer:{name}`, so a routine asked for in the operator's own DM is always "Check this" (the likeliest friction) | F2 DD7 *(J)* | D4 |
| C8 | Routines approval defaults to on | F2 DD5 *(J)* | D4 (first enable) |
| C9 | Trusted set: the four routine tools and `current_time` (which also stops `current_time` flagging notes); `list_my_routines` trusted only while nothing it listed was flagged; an agent write to an operator-made routine ORs its flag into the whole routine | F2 DD7 *(J)* | E2, E3 |
| C10 | A routine run's message is a user-side bubble named for the routine with a "Routine" chip | F1 *(ajc)* | C2 |
| C11 | A run fails with "{where} is now answered by {agent}." when the routine's agent no longer answers the channel (for a DM, `{where}` is the numeric channel id) | F1 *(ajc)* | D5 |
| C12 | Purge now deletes the agent's chats, **all** its finished run history and its resolved proposals; it never deletes routines (Done ones age out only in the daily sweep) or pending proposals | F1 DD1 *(ajc)*, F3 DD4 *(FD)* | G1 |
| C13 | An agent's proposal fixes its start when it is proposed; approving it after that start has passed is refused ("This schedule has no runs left.", 422) and it stays pending. A save, approval or re-enable with no runs left is refused the same way | F3 *(FD, review cycle 2 and leg 4)* | E2 |
| C14 | Run history hides the stored reason of `ok`, stopped and interrupted runs (`routines-describe.js::outcomeStatus`): "The chosen chat was gone, so this run started a new chat.", "The agent gave no reply to send.", "Stopped at the step limit.", "Stopped from the chat.", "The app stopped during this run." are returned by the API but never shown, so a gone chat reads only "Ran {time}" with "New chat" — against the mission's "records that it did". An own-chat target stores no sentence at all. Skipped and missed labels repeat their verb ("Skipped {time}: Skipped 3 times…", "Missed: Missed 1 run…") | F1 *(ajc)* | C1, C4, C5 |

**Cheaper (wording, defaults, display; settled as the walk passes them):**

| # | Call | Source | Walk |
|---|---|---|---|
| L1 | Routine tools seeded in the prompt when the item is on (945 tokens) | F2 DD1 *(J)* | E2 |
| L2 | Tool names, argument names, target shapes, result and refusal wording | F2 DD2 *(J)* | E2, E3 |
| L3 | Self-configuration labels; the h3/h4 heading asymmetry between Agent prompt and Routines | F2 DD5 *(J)* | D4 |
| L4 | Refused calls are not recorded as proposals; the stale check (the walk shows the update path; the delete path rests on tests); the pending cap (20) and dedup | F2 DD6 *(J)* | E3, E4 |
| L5 | Saving a flagged routine with its prompt clears the flag; toggling, Run now and approving do not | F2 DD7 *(J)* | D4 |
| L6 | Built-in tools before MCP servers on the Tools tab | F1 *(ajc)* | A2 |
| L7 | The edit form's unsaved draft is not leave-guarded | F1 *(ajc)* | B5 |
| L8 | "Custom…" is a modal (not inline) and opens on `change` (arrowing onto it opens it) | F3 DD7 *(FD)*; F3 leg 7 a11y review | B1 |
| L9 | The default Repeat, the preview line's announcement, the sentence wording | F3 DD7 *(FD)* | B1 |
| L10 | Purge now's wording: "Purge now", "Confirm purge?", "Purged N conversations" (never updated for C12; F3 DD4 said the confirm wording would say so) | F3 DD4 *(FD)* | G1 |
| L11 | "Still running" skips collapse into one row | F3 DD11 *(FD)* | C4 |
| L12 | The Flight 2 leg 3 and leg 4 deviations (its debrief's list), including "refusals don't count toward the 5-a-turn budget" | F2 | J |

*(ajc)* = Flight 1's *(autonomous judgement call)*. Calls the operator
settled in Flight 3 planning (caps, the 1-minute floor, proposal retention,
the `default` agent, the per-turn write cap of 5) are not reopened unless
the walk surfaces a problem.

#### DD5. Contracts pinned by external readers

A HAT change to any of these is a deliberate re-author, never an inline fix:
- **Behavior specs** `routine-connector-delivery`,
  `agent-schedules-follow-up` and, if C12/L10 changes Purge now,
  `agent-purge-now-clears-history`:
  - REST under `/api/agents/{name}/routines` (list/create/get/update/delete,
    `/{id}/runs`, `/{id}/run`, `/preview`) and
    `/api/agents/{name}/self-configuration/routines` (with `/proposals`,
    `/pending-count`, `/approve`, `/dismiss`);
  - the stored schedule shape `{start, repeat, ends}`, the legacy request
    shapes the connector spec sends, the run reason codes;
  - `/api/_test/stub/*`.
- **Agent tool contract:** `list_my_routines`, `schedule_routine`,
  `change_routine`, `cancel_routine` (`the_one/agent/tool_names.py`), their
  descriptions and refusal sentences. Tool text is platform prompt text:
  a change lands with an eval run compared against **both**
  `evals/baselines/m33-routines.json` and `m30-platform.json` (CLAUDE.md
  "Prompt evals"; needs the plan token and a local `gpt-oss:20b`).
- **Taint contract:** `taint.FLAGGED_CONTENT_MARK` is persisted in stored
  tool results, so changing its text silently unflags history;
  `TRUSTED_TOOL_NAMES` is pinned by `tests/test_notes_tools.py`'s exact-set
  test and mirrored in `evals/checks.py`.
- **Stored and wire fields:** `Message.routine_id` / `routine_name` /
  `routine_untrusted_sources`, `session_metadata.routine`, and the WebSocket
  frame `source: 'routine'`.
- **Library contracts:** `App.ui.message`'s `marker` option and
  `App.ui.noteFlag`'s `subject` option (contract lanes with
  `THE_ONE_REQUIRE_WEBKIT=1`).
- **Testids** `routine-*`, `routines-*`, `routine-form-*`, `routine-custom-*`,
  `chat-drawer-routine*` and the Self-configuration Routines testids
  (`docs/ui-testid-registry.md`).
- **Docs:** `SECURITY-MODEL.md` "Routines" and `the_one/agents.md`
  "Routines (M33)" for any reversal of C7, C8, C9 or C13.

If any changes, the affected spec or eval is re-run at the end of the flight
(DD6).

#### DD6. Fixes and the closing gate

- **Look-and-feel fixes** (wording, layout, focus) are made inline by a
  Developer and re-verified at the step.
- **A new or changed behaviour** (any reversal in DD4 that changes what the
  system does) goes through the fix-vs-feature gate: a scoped design
  review, then its own leg added to this flight. A C7 reversal (for example
  an allowlisted-peer exemption) is always this path, never inline.
- **A multi-surface fix** gets a lightweight Developer design review first.
- Every fix pass runs `THE_ONE_TEST_NETNS=1 make test-unit` and the owning
  browser lane of every file it touched (crew file, Fix Review Issues).
- **The closing gate** runs once, after the last fix, on one commit, on a
  quiet host, **with the HAT instance stopped** (its scheduler would make
  the host not quiet): `THE_ONE_TEST_NETNS=1 make test-unit` (15 skipped
  expected), then `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1
  PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh
  --parallel 3`. Lanes that moved more than 15% are re-budgeted under the
  quiet-host rule.
- **Re-runs** after the gate, once the HAT instance is stopped: a behavior
  spec whose DD5 contract changed, on its own dev instance (port 8491 or
  higher); an eval run if tool text changed.

#### DD7. Mission close

- The flight log records the operator's verdict per mission criterion and
  the step that showed it. The FD ticks the mission's criteria from that
  record. A clause the walk cannot show (the upgrade clauses, per the open
  question) records its evidence explicitly.
- Out-of-scope findings are squawks; design-sized ones are recorded for the
  mission debrief (e.g. retiring the legacy aliases, Flight 3
  Recommendation 3; the dead `.env.hat` bots behind `discord-live-round-trip`).
- `/mission-control:mission-debrief` follows this flight's debrief.

### Citation Audit

Verified against the working tree at `7dd144d5` (FD at planning; the six
original rows re-checked by the cycle-1 Architect; the rows it added are
from its review):

| Citation | Status |
|---|---|
| `the_one/interfaces/web/routines_api.py` — `POST /agents/{name}/routines/preview` (:105), `POST .../routines/{routine_id}/run` 202 (:375), `GET`/`PUT .../self-configuration/routines` (:263, :269), `/proposals`, `/pending-count`, `/approve`, `/dismiss` (:290-361) | verified |
| `the_one/agent/tool_names.py` — the four routine tool names (:16-19) | verified |
| `the_one/agent/taint.py::compute_taint` — a user message with `peer_name`, and the turn's current peer, add `peer:{name}`; operator-typed web text is not untrusted | verified |
| `the_one/connectors/inbound.py::is_admitted` — a DM from a peer not on the allowlist is dropped unless it is a pairing code | verified (Architect) |
| `the_one/interfaces/web/api.py::delete_agent_chat_sessions` — Purge now deletes chats, finished run history and resolved proposals, never routines | verified (Architect) |
| `the_one/routines/runner.py::_resolve_target` — `own` recreates with `note=None`; `chat` records the gone-chat sentence | verified (Architect) |
| `the_one/routines/recurrence.py::_sunday_offset` — weeks count from Sunday | verified (Architect) |
| `the_one/routines/service.py` — re-enable continues the grid (:332-348); a pending routine refuses agent changes (:452); proposals fix their start (~:500-505) | verified (Architect) |
| `static/js/areas/studio/agent-editor.js::TAB_ITEMS` — General, Rules and notes, Knowledge, Tools, Routines, Self-configuration | verified (Architect) |
| `static/js/areas/studio/general-tab.js` — "Purge now" (:229) | verified |
| `evals/baselines/m33-routines.json`, `m30-platform.json` exist | verified |
| `tests/behavior/.env.hat` main and driver tokens — `GET /users/@me` returns 401 for both | verified (planning) |

### Prerequisites

- [x] `main` carries Flights 1-3 and #339; this branch is cut from it.
- [x] Ollama is not needed for the walk; the operator supplies an Anthropic
      API key. (An eval re-run under DD5 would need the plan token and a
      local `gpt-oss:20b`; both were present in Flight 3.)
- [x] The installed instance is quit (port 8484 refused at planning); D1
      re-checks it.
- [x] The operator creates a new bot token (at approval).
- [ ] Port 8490 is free when the walk starts; the host is quiet when the
      closing gate starts (checked at the time).

### Pre-Flight Checklist

- [x] All open questions resolved (the bot token: the operator creates a new one;
      the mid-walk calls are the walk itself)
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The Flight Director starts the dev instance (DD2), mints the handoff link,
and walks the operator through the steps below one at a time. Each step's
result, and each judgement-call verdict, goes into the flight log as it
happens. Fixes route per DD6; added legs are recorded in the Legs list and
the flight log. After the last fix, the HAT instance is stopped and its
data dir deleted (DD2), then the closing gate and any re-runs DD5 requires.

### Legs

- [x] `hat-and-alignment` *(interactive)*: the guided walk below, the
      judgement-call verdicts, inline fixes, and the closing gate.
- [x] `new-chat-every-run-backend` *(added at the HAT, B3; a FEATURE through
      the gate, high-risk, design-reviewed)*: no routine targets; every run
      starts a new web chat; schema v49; no routine connector delivery; the
      agent tools lose `target` (tool text, evals re-run); dead code removed.
- [x] `new-chat-every-run-ui` *(added at the HAT, B3/B5; with the above)*: the
      Routines list on mockup A (caption row, ⋯ menu, expandable details,
      runs linked to their chats, reasons shown); the form without targets
      and with Save disabled until changed; the approval queue without
      "Runs in"; retired testids.
- [x] `start-immediately` *(added at the HAT, after C4; a FEATURE through the
      gate, high-risk, design-reviewed)*: the form's "Starts" radio group
      (On / In / Immediately, mockup S1) and an operator-only now-start whose
      first run is the save instant.
- [x] `approval-default-and-drawer` *(added at the HAT, E1/E2; split from the
      tab rebuild at design review)*: Routines approval off for new agents
      (C8 reversed); the drawer refreshes on a live routine tool write.
- [x] `self-config-tiles` *(added at the HAT, E1/E2; mockup SC2,
      design-reviewed)*: the Self-configuration tab as two cards with inline
      approval switches and Waiting/History expanders; External access at the
      bottom.
- [x] `remove-legacy-schedule-shapes` *(added at the HAT, Part J: C6
      reversed)*: canonical-only schedule input; fixtures, scripts and evals
      moved; the v48 frozen converter kept.

> **HAT pivot (2026-10-29, operator):** routine targets and routine connector
> delivery are removed, and Part D (a real Discord DM) is dropped. The walk's
> Parts C and E, DD4 rows C7, C10, C11 and C14, and DD5's
> `routine-connector-delivery` contract are read against that decision; see
> the flight log, "Operator decision: every run starts a new chat". The
> original text below is kept as planned.

#### Draft walk (state transitions)

**Part A — setup**

1. **[empty instance]** Open the handoff link.
   - Chats shows the guidance state; no errors.
   - Add the Anthropic provider (Haiku), then create agents `hat-agent` and
     `hat-other` (the second is needed in D5).
   - Settings › Date and time shows the operator's zone.
2. **[agent created]** Open `hat-agent`: the tabs read General, Rules and
   notes, Knowledge, Tools, Routines, Self-configuration.
   - Tools shows Built-in tools, then MCP servers (**L6**).
   - Routines shows the empty state; Self-configuration shows two items,
     Agent prompt and Routines, both off.
   - Start one web chat with `hat-agent` and send a first message, so it is
     a session the routine form's chat chooser lists (a target for Part C).

**Part B — the schedule rules (costly calls first, little waiting)**

1. **[form open]** New routine: the start defaults to the next whole hour in
   the operator zone.
   - Step through every Repeat preset; arrow onto "Custom…": it opens a
     modal on arrival (**L8**). Check the default Repeat and the preview's
     wording and announcement (**L9**).
   - A start on the 31st with "Monthly on day 31": the month-skip warning
     shows under Repeat.
2. **[the rules in the preview]**
   - **C4:** start on a **Sunday**, Custom "every 2 weeks on Monday": Next
     is the following day (Sunday-first). Monday-first would put it 8 days
     out.
   - **C5:** start on a **future Thursday** (e.g. Nov 5), "every 2 weeks on
     Mon, Wed": Next is the Monday 11 days after it; the Thursday start
     itself is not a run.
   - **C1:** "every day, ends after 5", start **today at a time already
     passed**: Last reads today + 4 (counted from the start); counting from
     the save would read today + 5. A past start is accepted for a
     repeating schedule.
   - Out-of-range numbers show field errors in the dialog; Cancel discards;
     Escape with the ends calendar open closes only the calendar.
3. **[re-enable keeps the grid]** Save "every 10 minutes" starting earlier
   today at a round time, targeting its own chat, with a short prompt (it
   really runs).
   - Turn it off across a grid point, then on again: the next run is on the
     grid (:x0), not now + 10 (**C2**). Then turn it off.
4. **[zone change]** With a one-off tomorrow at 9:00 AM and a daily at
   9:00 AM saved, change the zone in Settings › Date and time, then go back
   to Agents › `hat-agent` › Routines (the tab refetches on return).
   - The one-off keeps its instant (its local time moves); the daily stays
     at 9:00 AM in the new zone (**C3**). Change the zone back.
5. **[unsaved edit]** Edit a routine, type, leave the tab: the draft is
   discarded with no prompt (**L7**).

**Part C — web chat runs**

1. **[run into a web chat]** A routine targeting the Part A web chat, open
   in a second tab, with a long prompt ("use the shell to run `sleep 90`,
   then reply"). Run now.
   - The second tab streams the run live; Stop is enabled during it.
   - In the Routines tab, Run now is disabled and the row reads Running
     while it runs (the 409 "This routine is already running." shows only
     from a stale view, e.g. a second Routines tab loaded before the run).
   - On a second run, press Stop in the second tab: history shows "Stopped
     {time}" (the stored "Stopped from the chat." is not shown, C14).
2. **[transcript]** The run's message is a user-side bubble named for the
   routine with a "Routine" chip, never "You" (**C10**).
   - The drawer shows the "Routine" fact and the Routines group.
   - The Routines tab row shows the run in history, the next run and the
     outcome.
3. **[new chat each run / own chat]** One routine of each: Run now twice.
   - New chat each run makes two chats titled with the routine's name; own
     chat reuses one.
4. **[still running]** (**L11**) In Settings › Built-in tools, raise the
   shell's maximum timeout to 5 minutes. A routine every minute, targeting
   its own chat, prompted to run `sleep 200` with a 240-second timeout.
   - Turn the routine off at about 3.5 minutes (the next occurrence would
     start a new run and a later skip would open a second row). History
     shows one row "Skipped {time}: Skipped 3 times while the previous run
     was still going." (the doubled verb is a C14 wording finding). Keep
     the shell setting raised for Part H.
5. **[chat gone]** (**C14**)
   - Delete an existing-chat routine's target chat: before the run, its row
     reads "Chat gone, a new one starts on the next run". Run now: a new
     chat starts; history shows "Ran {time}" with "New chat" in the meta
     line, and no reason.
   - Delete an own chat: the row still reads "Its own chat". Run now: it is
     recreated; history looks the same.
   - Decide C14: show the stored reason for `ok`, stopped and interrupted
     runs (one display change covering chat gone, no reply, step limit and
     stopped), and whether own-chat should store one.

**Part D — a real Discord DM (DD3)**

1. **[installed instance closed]** The operator confirms the installed app
   is quit (tray Quit or `the-one quit`, not window close); the FD checks
   `127.0.0.1:8484/api/live` is refused.
2. **[connector up]** In the dev instance, add the Discord connector with
   the bot token, with `hat-agent` as its default agent. Save; in the
   Pairing section (edit mode) generate a code and DM it to the bot (no
   reply expected). Reopen the connector: Allowlist peers shows the
   operator's Discord user id. Then DM the bot a message: `hat-agent`
   replies once.
3. **[daily DM routine]** A routine targeting that DM chat, "Every day" at
   a time 2-3 minutes ahead.
   - At the time: the reply arrives in Discord, the routine's prompt is not
     posted, exactly one reply arrives, and the app's DM chat shows the run
     marked as the routine's.
   - Run now also delivers.
4. **[agent follow-up in the DM]** Turn the Routines self-configuration item
   on: **approval is on by default (C8)**. Check both items' labels and
   heading levels (**L3**). Switch approval off.
   - In the DM, ask the agent to check back in 2 minutes. The tool call is
     visible in the app's chat; the routine is "Made by the agent" and
     carries the warning-triangle flag, named "Check this routine: it was
     written after content that didn't come from you (peer:{name}). It may
     have been planted." (**C7**). Decide whether the operator's own DM
     should flag.
   - The follow-up arrives in Discord on time.
   - Once it has run (Done), open its edit form: the preview shows "This
     schedule has no runs left." under the schedule, but Save still works
     (it sends only the prompt). Save: the flag clears (**L5**). E2's
     unflagged check relies on this.
5. **[channel moved]** Reopen the connector (Allowlist peers still shows the
   operator's id) and set its default agent to `hat-other`;
   Run now on the DM routine: the run fails with "{channel id} is now
   answered by hat-other." (**C11**; judge the wording). Set it back.

**Part E — the agent schedules its own routines (web chat, approval on)**

1. **[approval on]** Switch the Routines item's approval back on.
2. **[pending]** Start a **new** web chat (an open chat picks up the routine
   tools only after its session is rebuilt), and ask for a reminder in 3
   minutes.
   - The tool call shows a pending result; the Routines item's "Waiting for
     approval" lists it; nothing is scheduled; the proposal is **not**
     flagged (`current_time` and `search_tools` are trusted, **C9**).
   - Review the tool names and result wording (**L1**, **L2**).
   - Approve **promptly**: the routine appears and runs on time. (A second
     request left pending past its start shows **C13**: Approve is refused
     with "This schedule has no runs left." and the proposal stays
     pending; dismiss it.)
3. **[flagging and refusals]** (**C9**, **L4**)
   - Have the agent `web_fetch` a page, then schedule something: the
     proposal carries "Check this". (Typed text in a web chat is trusted
     and does not flag.)
   - Refusals, in a **new** chat with no `web_fetch` in it, each asking the
     agent to make the call even if it expects a refusal:
     - change a reminder still pending: "That routine is still waiting for
       your operator's approval, so it can't be changed yet.";
     - a one-off at a time already passed today: "A one-time routine must
       be at least a minute away." (a past instant hits the minimum-ahead
       check first; decide whether it should say the time has passed —
       tool text, so DD5's evals apply);
     - each refused in the chat, and the queue unchanged.
   - Six reminders in one turn: the first five are added to Waiting for
     approval, the sixth is refused in the chat ("Routine change limit for
     this turn reached (5 changes)."). Dismiss the five.
4. **[stale approve]** With a pending change to a routine's prompt, edit
   **the same field** in the Routines tab, then Approve: the stale 409 and
   "Approve anyway".
5. **[item off]** Turn the item off: pending changes are withdrawn, and the
   agent has no routine tools in a new chat.

**Part F — the agent lifecycle**

1. **[rename]** Rename `hat-agent`: its routines, run history and proposals
   follow; the connector's default agent follows. Run now on the DM
   routine: it still delivers to Discord.
2. **[Discord cleanup]** Delete the dev connector (DD3).
3. **[delete]** Give `hat-other` a routine, delete `hat-other`, recreate an
   agent with that name: its Routines tab is empty.

**Part G — retention** (**C12**, **L10**)

1. **[a pending proposal]** Turn the Routines item back on (approval on) and
   have the agent propose one routine in a new chat, so a pending proposal
   exists (E5 withdrew the others).
2. **[Purge now]** On General, read the button, the armed label and the
   flash. Purge now: the agent's chats, finished run history and resolved
   proposals go; routines (Done ones included) and the pending proposal
   stay. Expect a wording finding.

**Part H — across a restart** (the "survive restarts" and "honest"
criteria)

1. **[caught up]** A routine every 10 minutes with its next run in about 1
   minute, short prompt. The FD stops the instance by PID before it is due
   and restarts it **between 1 and 5 minutes after the due time** (the
   grace for a 10-minute routine is `min(gap/2, 2h)` = 5 minutes; under a
   minute late it runs as Scheduled): history shows "Ran {time}" with
   "Caught up · {date time}" in the meta line.
2. **[missed]** Stop it again before the next due time and restart **more
   than 5 minutes after that due time**: history shows "Missed: Missed 1
   run while the app was closed." (or 2 if a further grid point passed),
   and no backlog runs.
3. **[interrupted]** Stop the instance during a run (the `sleep 200` prompt
   from C4, with the shell maximum still raised): after the restart,
   history shows "Interrupted {time}". Then restore the shell setting.
4. Each restart needs a fresh handoff link (DD2). Turn the routine off.

**Part J — the remaining calls**

Go through the DD4 rows not yet decided (C6, L12, anything deferred during
the walk) and confirm or reverse each. Record each mission criterion's
verdict (DD7), including the upgrade clauses' evidence.

**Optional — daylight saving.** Daylight saving ends Sunday, November 1,
2026 (America/Chicago). If the walk spans that night, a 1:30 AM daily left on
the running dev instance gives a real fall-back observation (one run, not
two).

### Checkpoints

- [ ] Walk complete with no open blocking findings.
- [ ] A real Discord DM routine delivered (Part D).
- [ ] Catch-up, missed and interrupted observed across restarts (Part H).
- [ ] Every DD4 call confirmed or reversed, recorded in the flight log.
- [ ] Every mission criterion has the operator's verdict.
- [ ] HAT instance stopped and its data dir deleted; closing gate green on
      one commit; DD5 re-runs done if needed.

### Adaptation Criteria

**Divert if**:
- A finding needs a design cluster of its own (for example retiring the
  legacy aliases, or reworking the `peer:` flag model): record it for the
  mission debrief, or plan it as a new flight, rather than growing this one.
- Delivery to a real Discord DM fails in a way the stub could not show:
  diagnose before continuing; a fix is a leg through the gate.

**Acceptable variations**:
- Step order within a part, steps combined, or a part spread over sessions.
- Fixes that change wording, layout or focus only.

---

## Post-Flight

### Completion Checklist
- [ ] HAT leg completed (and any added legs)
- [ ] Fixes committed, PR updated
- [ ] HAT data dir deleted
- [ ] Closing gate green
- [ ] Mission criteria ticked; mission debrief scheduled

### Verification
- The operator's sign-off on the walk, recorded in the flight log.
- The closing gate's `PARALLEL_RESULT` line and unit counts.
- Behavior specs and evals re-run if DD5 contracts changed.
