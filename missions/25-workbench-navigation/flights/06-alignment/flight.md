# Flight: Alignment

**Status**: ready
**Mission**: [Workbench Navigation and Control Library](../../mission.md)

## Contributing to Criteria

- [ ] **SC8: Matches the approved samples.** The operator walks every redesigned surface
  in both themes against the approved B3 board, and each deviation is fixed or explicitly
  accepted. The pre-accepted deviations D1–D5 (reference spec §13) stand.
- [ ] **SC9: The window belongs to the product.** The operator walks their own installed
  v0.10.0 using `windows-native-frame-splash` steps 11–19: theme tint in both themes, a
  real OS theme flip, inactive dimming, snap layouts, Win+arrows, the upgrade keeping
  their size, Ctrl K and the splash.
- [ ] **SC10: Operable and regression-safe** (the remainder):
  - accessible names for the Tools-tab master toggles and the editor info icons
    (squawks 0113, 0114);
  - focus that no longer drops to the page after Create, Save or Test (Flight 3 Q7);
  - a page `h1` at the Agents and Library roots;
  - suites, guards and the affected behavior specs green at close.
- [ ] **Known Issue: Ctrl K in WebView2** closes with the operator's confirmation in the
  installed build.
- **The carried squawks** 0112–0116 and 0119–0125, all confirmed live by reconnaissance,
  are completed in this flight (operator decision, 2026-10-06).

---

## Pre-Flight

### Objective

Close Mission 25 with the operator. First a crew pass fixes every known, confirmed item:
the visible ones, the chat-connection edge cases, and the test and documentation
servicing. Then the Flight Director walks the operator through each surface in the running
app and their installed Windows build. Each thing the operator sees is fixed inline or
explicitly accepted, and the open product decisions are settled live. A short close-out
then leaves the mission's success criteria checkable and the suites and behavior specs
green.

### Open Questions

- [x] **How the session runs.** Fixes first, then a guided walk (operator, 2026-10-06).
- [x] **Carried squawks.** They are fixed in this flight (operator, 2026-10-06).
- [x] **Windows install.** The operator has already installed v0.10.0, and the walk uses
  it (operator, 2026-10-06).
- [x] **Window widths 640–1023.** "Show me first": decided during the walk (DD6).
- [ ] **A release at mission close.** Asked at the end of the close leg (DD9). It does not
  block planning.

### Design Decisions

**DD1: Fixes first, then the walk, then close-out.** Three autonomous legs clear the known
items before the operator's time is spent:
- **Leg 1, `visible-fixes`:** what the operator would see.
- **Leg 2, `chat-and-test-fixes`:** the chat connection and test robustness.
- **Leg 3, `servicing`:** documentation, specs and the helper.

Leg 4, `alignment-walk`, is the interactive session (HAT). Leg 5, `mission-close`, records
acceptance and runs the gates. The operator chose this order.

**DD2: Focus after an in-place action** (Flight 3 checkpoint Q7). It is one shared
rule, implemented once.
- **Scope.** Only actions that re-render or disable an editor in place: **Save**,
  **Test** (provider) and the edit-mode **Cancel**, which reverts in place and then
  disables itself. A create that turns into edit mode in place is also covered.
- **Out of scope:** closing actions (create-mode Cancel, Delete, the breadcrumb close).
  They keep Flight 3's DD8 ("nearest surviving row, else the primary action"), pinned by
  `test_flow_provider_editor.py` and `list-and-detail` steps 6 and 8.
- **The knowledge-base exception:** creating a knowledge base keeps focusing its
  folder-path input (squawk 0101; `test_flow_studio_library_list.py`, `list-and-detail`
  step 12).
- **The rule:**
  - the control that was activated is recorded when the action **starts**, before
    anything disables it;
  - after the re-render or re-enable, focus returns to that control, or its replacement
    with the same `data-testid`;
  - otherwise focus goes to the editor's `.editor-title`, with `tabindex="-1"` added
    where it is missing (heading levels unchanged: the agent and Library editors keep
    `h1`, the provider and tool editors `h2`);
  - Test connection, which only disables, returns focus to its button when it is
    re-enabled.
- **Mechanism:**
  - it lands after `nav.js`'s post-Continue `setTimeout(focusMain)`;
  - it is guarded by the same editor-generation check `admin.js` already uses (`editorGen`
    in `revealItem` and `mountProviderItem`);
  - it **replaces** the existing `keepFocus`/`hadFocus` path, which fails because Save is
    disabled before `hadFocus` reads `document.activeElement`.
- **Status messages** keep using the existing live regions.
- **Editors covered:** agent, knowledge base, MCP server, connector, provider and tool.
  Leg 1's design names every call site.

**DD3: The Settings tile title row** (squawk 0116).
- **The fix:** a flex title row, so the name truncates beside the badge in both tile
  kinds.
- **It is not CSS-only.** It needs a wrapper element around the name and badge in both
  builders: `providers-list.js` (DOM) and `tools-grid.js` (HTML strings, so check the
  sink-ratchet baseline).
- **Verification:** the squawk's bounding-box tests in both themes, at 1024 and 1440.
- **No new `App.ui` factory:** completing the tile coverage belongs to the next mission's
  control work.

**DD4: Create routes return 422 for invalid input** (squawks 0112 and 0081).
- **The routes.** `create_provider` and `create_chat_session` catch Pydantic's
  `ValidationError` and return a 422.
- **No echo.** The 422 body uses `e.errors(include_context=False, include_input=False)`.
  For a missing field, Pydantic's `input` is the whole request, `api_key` included, so it
  must never be echoed.
- **The display.** The provider form's save path goes through `App.api.fetchJson`, which
  flattens a Pydantic error list to "field: message". Today `provider-editor.js` throws
  `e.detail` and shows "[object Object]", which also affects `update_provider`'s
  existing 422s.
- **The test** uses a `page.route`-intercepted 422, since the form always sends
  `base_url`.
- **The seeder docstring** that claims a 422 becomes true.

**DD5: The chat connection's edge cases** (squawks 0119 and 0120).
- **0119:** a degraded `join` of the already-bound session unsubscribes the socket.
- **0120:** a `cancel` processed before a spawned turn starts still sends `cancelled`.

Both are backend-only changes to the WebSocket handler, with unit tests in the
existing harness (`tests/test_ws_start_session.py`). Neither changes a message's shape.
- **0119:** follow the `not_found` branch's existing pattern: remove the subscriber in the
  degraded branch when the socket is bound to that id.
- **0120:**
  - also covers a queued task cancelled while it waits on the session lock (`async with
    session_locks[...]`), outside `_process_and_broadcast`'s `except CancelledError`;
  - **at most one `cancelled` per cancel**, even when one cancel hits a running task and a
    never-started one;
  - the squawk's browser check (Stop at once, then Send re-enables) is included if it can
    be made deterministic, and otherwise explicitly dropped, with the reason in the
    squawk.

**DD6: The walk** (leg 4).
- **Apparatus.** A dev instance on port 8486 with a fresh scratch data dir, in dev mode
  (mock providers), seeded with realistic content:
  - about 30 agents across several provider types;
  - chats spread over Today, Yesterday, Last 7 days, Last 30 days and Older, including a
    connector-platform chat;
  - knowledge bases, MCP servers and connectors.

  The operator opens it in their own Windows browser through a handoff link: mirrored
  networking makes WSL's `127.0.0.1:8486` reachable from Windows. A fresh link is minted
  for each new browser context.
- **The reference** is the approved prototype canvas
  (`https://claude.ai/artifact/787XyAuiyoA969YSF5ZnFc`; the reference of record is the
  copy in `missions/25-workbench-navigation/reference/`), plus `reference-spec.md`.
- **Order of the walk**, each surface in Light then Dark:
  - the rail;
  - Chats: list, picker, new-chat state, thread, composer, drawer at 1440 and at
    1024–1279;
  - the jump-to palette;
  - Agents (list, filter, editor chrome);
  - Library (grouped list, Add menu, editors);
  - Settings (nav, pages, Providers tiles, Built-in tools);
  - then the narrow widths 640, 800 and 1000, shown in the browser and in the desktop
    app.
- **The decision sheet** is settled on the surface where each item appears:
  - Flight 5 DD12, questions 1–5;
  - Flight 4: B1, the faint Dark pending-row wash; B2, the focus ring after a pointer
    close of the palette; B3, focus on `<main>` after Continue; B4, message timestamps
    after a reload (reproduce live); B5, UTC bubble times against local list times;
  - the narrow widths.
- **Shared state** (HAT guidance): the walk includes a second tab on the same instance
  (cross-tab theme sync) and a connector chat the operator did not start.
- **SC9:** the operator walks their installed v0.10.0, guided step by step through
  `windows-native-frame-splash` steps 11–19, plus Ctrl K.
  - **Step 16** (the first launch after the upgrade) has already happened. It is judged
    from the operator's recollection, asked during the walk, and recorded as such.
  - **Steps 17 and 19** act on the operator's real profile (renaming `window-state.json`,
    quitting and relaunching). They are operator-only; the Flight Director never touches
    that directory.
- **Operating rules for the walk instance:**
  - **Reachability first.** The operator opens `http://127.0.0.1:8486/api/live` from
    Windows before the first handoff.
  - **The handoff.** It is minted against `127.0.0.1:8486`, the host the Windows browser
    uses. The default Origin allowlist covers it, and the cookie is per host, so
    `localhost` is a different context.
  - **Seeing a fix:**
    - JS and CSS fixes need a hard reload (Ctrl+Shift+R), because `/static` is
      cache-busted by version (squawk 0085);
    - Python and `index.html` fixes need a `make restart` of 8486. The session cookie
      survives a restart.
  - **Re-verifying fixes.** Inline fixes are re-verified with the Flight Director's own
    probe (computed style or DOM) as well as the operator's eye.
  - **8485** is the Flight Director's Flight 4 preview instance; stopping it is the
    operator's call.
- **The decision sheet** records, next to each item, what changes if the operator says
  "change it". For example, B3 lives in `nav.js` and interacts with DD2's ordering.
- **SC8's evidence:** the operator's per-surface verdicts, plus the computed-style probe
  records from Flights 3 and 4's behavior runs, cited in leg 5.
- **The record:** every verdict (accepted, fixed or changed) goes in the flight log per
  surface. The Flight Director's screenshots are flight-log evidence only and are never
  committed.

**DD7: The fix-versus-feature gate during the walk.**
- **Look-and-feel fixes** ride inline: a Developer spawn, re-verified on the spot. A fix
  that spans more than one surface gets a quick Developer design review first.
- **Behaviour changes** get a scoped design review before implementation.
- **Anything that needs real design work** is offered as a separate leg in this flight,
  if the operator wants it now, or recorded for the next mission. Examples: a narrow
  layout, a tile factory.

**DD8: The contracts the behavior specs depend on.** The specs pin testids, routes and
payload shapes. These include:
- `start-a-chat`, `jump-to-palette`, `workbench-navigation`, `shell-navigation-smoke` and
  `chat-roundtrip`;
- `list-and-detail`, `system-provider-config` and `studio-agent-crud`, which reach the
  surfaces leg 1's focus and heading changes touch;
- the Windows specs.

A walk change to any of these is a spec re-author, made deliberately in leg 5, not an
inline edit. The one exception is a change decided at planning: DD11's `h1` re-authors
`list-and-detail` step 2 in leg 1. Leg 5 re-runs every listed spec that a leg touched.

**DD10: The provider page's Models list gets a label.**
- **What the operator found** (planning, 2026-10-06): "you can't select a model on the
  provider page".
- **What the list is.** It shows the models a provider offers. It is not a picker: each
  agent chooses its model in the agent editor's Model section, as the B3 board's
  Providers intro says.
- **The fix,** as the operator chose:
  - a label on the list explaining that these are the available models, and that one is
    selected per agent (with a link to Agents);
  - the rows styled as plain information, not options.

  It is a look-and-feel fix in leg 1. No provider-level model is added.

**DD11: A page `h1` at the Agents and Library roots** (the Flight 3 carry, SC10).
- **The heading.** A visually hidden `h1` that names the destination ("Agents",
  "Library") is present only while no editor is open. With an editor open, its
  `.editor-title` stays the page's one `h1`, so there is one `h1` per state.
- **What stays the same:** the empty states keep `headingLevel: 2`, and nothing changes
  on screen.
- **A contract change, decided at planning:** `list-and-detail` step 2 ("no editor and no
  `h1`" at `#agents`) is re-authored in leg 1.

**DD12: Review and commit for each phase.**
- **Legs 1–3:** the flight-end Reviewer, then one commit, pushed and opened as the draft
  PR, all **before** the walk, so the walk runs on reviewed code.
- **Leg 4:** its inline fixes get a batched Reviewer pass (plus an Accessibility Reviewer
  for UI changes), then leg 4's own commit, as with Flight 3's leg 7.
- **Leg 5** (autonomous after the HAT): its own review and commit.
- **The flight goes `landed`** only after leg 5.
- **Leg 5's behavior re-runs** use ports 8487 and up, or stop the walk instance first.

**DD9: A release at mission close is the operator's call.** v0.10.0 already carries
Flights 1–5. Leg 5 asks whether the alignment changes warrant v0.10.1 or v0.11.0, and cuts
it only on a yes.

### Prerequisites

- [x] Flight 5 merged (PR #221), and v0.10.0 released (PR #222, tag `v0.10.0`). The branch
  `flight/06-alignment` is at `main` `aaee705`.
- [x] The operator has installed v0.10.0 on their Windows machine (2026-10-06).
- [x] The reconnaissance is in the flight log; every carried item is confirmed live or
  classified.
- [ ] Port 8486 is free on both sides when leg 4 starts. 8485 is still the Flight 4
  preview instance: re-check at leg 4, and stop that instance by PID if it is no longer
  needed.
- [x] The operator is present for leg 4. They started this flight interactively.

### Pre-Flight Checklist

- [x] All open questions resolved, or deferred with a decision point (the release at
  DD9)
- [x] Design decisions documented
- [x] Citation Audit complete (in the flight log's Reconnaissance Report)
- [ ] Prerequisites verified (the port check at leg 4)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

- **Leg 1:**
  - `api.py` `create_provider` catches `ValidationError` and returns a 422;
  - accessible names in `tools-tab.js` and in the five info-icon sites (squawk 0114);
  - the `admin.css` tile title row;
  - a shared focus helper (DD2) wired into the editors' action handlers;
  - an initial `aria-label` on `index.html`'s `#app-sidebar` (A5);
  - a page `h1` at the Agents and Library roots;
  - browser and unit tests for each.
- **Leg 2:**
  - `app.py`'s WebSocket `join` (degraded same-id) and `cancel` (before the turn
    starts), with unit tests;
  - the Knowledge re-index test waiting on a real non-indexed state (0115);
  - a deleted-agent heal browser test for a restored `#chats/~new/{agent}`.
- **Leg 3:**
  - the behavior crew file's CDP recipe and run rules (0121);
  - the five Flight 4 specs' wording (0122) and `windows-window-chrome`'s (0123);
  - the helper's closure pin test (0124);
  - the pywebview 6.x note in `agents.md` and `pyproject.toml` (0125).

  Each squawk is completed, with its corrective action and verification written in it.
- **Leg 4:** interactive (DD6, DD7).
- **Leg 5:**
  - the reference spec §15 status column swept from the flight logs;
  - the mission's SC checkboxes;
  - affected behavior specs re-run (at least `start-a-chat` and `chat-roundtrip` after
    leg 2, plus any spec a walk change touched);
  - all six browser lanes and the unit suite;
  - the DD9 release question.

### Checkpoints

- [ ] Legs 1–3 landed, each with its tests and the squawks (including 0081) completed.
- [ ] The flight-end review of legs 1–3 confirmed, and committed before the walk, so the
  walk runs on reviewed code.
- [ ] The walk is complete: every surface's verdict and every decision-sheet item is
  recorded, and the inline fixes are re-verified.
- [ ] SC9 walked and accepted by the operator on their installed build.
- [ ] Close-out: specs re-authored where needed, gates green, criteria checked, and the
  release question answered.

### Adaptation Criteria

**Divert if:**
- **The walk turns up a structural problem.** If an issue needs redesign rather than a
  fix (for example, the operator rejects a surface's layout), stop the walk for that
  surface. Agree with the operator whether it becomes a new leg here or next-mission
  scope.
- **The operator cannot continue the session.** The walk resumes later from the last
  recorded surface. The flight stays in flight.

**Acceptable variations:**
- **More inline fixes than expected:** add them as numbered inline-fix entries under leg
  4, each re-verified before moving on.
- **The narrow-width decision** becomes its own leg if the operator chooses a narrow
  layout now.
- **A Windows step can't be performed on the operator's setup** (for example, only one
  monitor): record it as not applicable, with the reason.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `visible-fixes`:
  - 0112 and 0081 (the create routes' 422 and the form's error display, DD4);
  - 0113 and 0114 (accessible names; six info-icon sites);
  - 0116 (the tile title row, DD3);
  - Flight 3 Q7 (focus after an in-place action, DD2);
  - A5 (an initial label on `index.html`'s `#app-sidebar`, which needs a restart);
  - the root `h1` (DD11, with `list-and-detail` step 2 re-authored);
  - a label on the provider page's Models list (DD10);
  - tests and docs.
- [ ] `chat-and-test-fixes`:
  - 0119 and 0120 (WebSocket edge cases);
  - 0115 (the Knowledge test race);
  - the deleted-agent heal test.
- [ ] `servicing`: 0121, 0122, 0123, 0124 and 0125, each squawk completed.
- [ ] `alignment-walk` (HAT, interactive): the guided walk of every surface against B3 in
  both themes, the decision sheet, the narrow widths and the operator's SC9 walk, with
  inline fixes under DD7.
- [ ] `mission-close`:
  - the §15 status sweep;
  - spec re-authors from walk changes;
  - affected behavior specs re-run;
  - all lanes and the unit suite;
  - the SC checkboxes;
  - the release question (DD9).

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing: the unit suite, the six browser lanes, the UI guards, and the
  affected behavior specs
- [ ] Squawks 0081, 0112–0116 and 0119–0125 completed
- [ ] The Known Issue "Ctrl K in WebView2" closed
- [ ] SC8, SC9 and SC10 checked in `mission.md` (and SC1–SC7 confirmed)
- [ ] Documentation updated: `CLAUDE.md` and `the_one/agents.md` for every behaviour the
  walk changed

### Verification

- **Unit and browser:**
  - each fix leg carries its tests;
  - leg 5 runs `make test-unit`, all six browser lanes (`THE_ONE_TEST_NETNS=1`;
    `contracts` with `THE_ONE_REQUIRE_WEBKIT=1`; `shared` with `TEST_TIMEOUT=3600`) and
    the static guards.
- **Behavior:**
  - `start-a-chat` and `chat-roundtrip` after leg 2's WebSocket changes;
  - any spec a walk change touched (re-authored first);
  - `windows-native-frame-splash` (operator-driven) in leg 4.
- **Operator acceptance:** recorded per surface in the flight log. That record is SC8's
  and SC9's evidence.
