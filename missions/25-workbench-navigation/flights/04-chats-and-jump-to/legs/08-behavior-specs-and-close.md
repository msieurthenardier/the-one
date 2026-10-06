# Leg: behavior-specs-and-close

**Status**: completed
**Flight**: [Chats and Jump-to](../flight.md)

## Objective

Close the flight. This leg covers:
- the **non-blocking operator preview** (DD13);
- the two new behavior specs (`start-a-chat`, `jump-to-palette`), finalized against the
  shipped build;
- the affected existing specs, re-authored against testids;
- the full gate run;
- the behavior-test crew-file update the Flight 3 debrief asked for.

The Flight Director then runs the flight-end review and the close-gate behavior runs.

## Context

- **Flight decisions:** DD12 (author specs against testids and roles), DD13 (the preview)
  and DD16 (specs and apparatus).
- **Who does what.** The Developer does the spec text, the crew-file edit and the gates.
  The **Flight Director** prepares and publishes the preview (crews cannot publish
  artifacts), and runs the close-gate behavior tests with live Executor and Validator
  pairs.
- **Spec drafts** were written at flight planning: `tests/behavior/start-a-chat.md` and
  `tests/behavior/jump-to-palette.md`, both `draft`. They were revised after both flight
  design cycles.

## Acceptance Criteria

- [ ] **AC1. The new specs finalized.** In `start-a-chat.md` and `jump-to-palette.md`,
  every step is checked against the shipped build: testids, copy, and the routes
  `#chats/~new/{agent}`, `#chats/{id}` and the palette picks. Each spec:
  - names its fixture seeding through the API (with `seed_session`-equivalent `POST`s);
  - names its apparatus (the CDP-driven Chromium with real input), its evidence notes, and
    its Light and Dark variants (switched inside the variant's own fresh context);
  - is set to status `active`.
- [ ] **AC2. The affected specs re-authored.** Re-grep `tests/behavior/*.md` for the retired
  surfaces: `chat-welcome-item`, the welcome agent list, `agent-select`, the dropdown,
  `new-chat-btn`, `session-agent-badge`, `.session-item` and "start a new chat with". Then
  re-author against the new surfaces:
  - `workbench-navigation`, step 2;
  - `shell-navigation-smoke`, step 3;
  - `chat-roundtrip`, step 3;
  - `vision-round-trip`, step 1;
  - `agent-purge-now-clears-history`, step 6;
  - `stub-connector-round-trip`, step 5;
  - the generic "start a new chat" steps in `agent-governance-and-search` (step 6),
    `chat-loop-hang-and-cancel` (step 1) and `extended-thinking-tool-turn` (step 1), from
    the leg 4b hand-off;
  - **`extended-thinking-tool-turn` step 5**, from the leg 5 hand-off. It compares against
    "the empty-chat baseline (0% at Step 1)", but a pending chat now shows **no**
    telemetry, so the baseline is re-worded to the first joined reading;
  - every other hit.

  Each changed spec gets an `Updated` line.
- [ ] **AC3. The crew file.** `.flightops/agent-crews/behavior-tests-execution.md` gains,
  in its Executor and Validator prompts, the rules the Flight Director has been carrying
  by hand (Flight 2 debrief recommendation 1, Flight 3 recommendation 5):
  - per-run scratch subdirectories for concurrent runs;
  - no unrequested state-changing actions;
  - an input-delivery probe at the start: a click reaches a capture-phase listener;
  - "you are resumed by SendMessage after each step; do not end your run";
  - the variant rule: set the variant inside the variant's own fresh context, before the
    first checkpoint;
  - the toast evidence rule: a screenshot, not `offsetParent`.

  The file's required sections and fenced prompts stay intact.
- [ ] **AC4. Gates.**
  - `make lint` and format;
  - every static guard;
  - `make test-unit`;
  - **all six browser lanes**, `contracts` with `THE_ONE_REQUIRE_WEBKIT=1`, each through
    `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1` (`shared` with
    `TEST_TIMEOUT=3600`).
  - The numbers go in the flight log, beside leg 1's baseline.
- [ ] **AC5. Docs sweep.** Each of these reflects the flight:
  - `CLAUDE.md`: the lanes, the Chats list and picker, the drawer, Chat, the palette, and
    `_chats.py`;
  - `the_one/agents.md`: the protocol, the start flow, the drawer, the palette, the store
    `sessions` collection and the editor contract;
  - `docs/ui-control-inventory.md` and `docs/ui-testid-registry.md`.

  Fix any drift found.
- [ ] **AC6. The squawks.** 0110, 0111, 0117 and 0118 each carry their Corrective Action
  and Verification, and are ready for the flight-end Reviewer's sign-off.

## Flight Director steps (not the Developer's)

1. **The DD13 preview, after leg 7 lands.**
   - Seed a fresh dev instance (port 8486 or higher, scratch data dir, dev mode,
     `/proc/<pid>/environ` verified) with:
     - 30+ agents across providers;
     - sessions across agents and ages;
     - a connector session;
     - knowledge bases and MCP servers.
   - Capture Chats (list, picker, pending, joined, drawer push and overlay), the palette
     and the agent editor's Chat, in both themes at 1440×900 and 1024×768.
   - Publish a comparison page beside the B3 board, with the DD13 questions, and notify
     the operator. **Do not wait** for a reply.
2. **Flight-end review.** Reviewer (Haiku or Sonnet per the crew file; Sonnet here,
   because the protocol and session lifecycle are involved) and an Accessibility
   Reviewer (Sonnet), in parallel. Then fix, re-review and commit.
3. **The close-gate behavior runs:**
   - `start-a-chat` and `jump-to-palette`, Light and Dark;
   - `workbench-navigation`;
   - `shell-navigation-smoke`;
   - `chat-roundtrip`;
   - `vision-round-trip`, if the mock vision path works, else recorded as not run.

   Use live Executor and Validator pairs on CDP Chromium, each spec on its own instance.
4. **Fold in any preview feedback** that arrived, as a leg with targeted spec re-runs.
   Then land the flight and mark the PR ready.

## Verification Steps

- AC4's commands.
- `grep -rn "chat-welcome-item\|agent-select\|new-chat-btn\|session-agent-badge"
  tests/behavior/*.md`. The only hits left should be ones that **describe** a retirement.

## Files Affected

- `tests/behavior/start-a-chat.md`, `tests/behavior/jump-to-palette.md`, and the
  re-authored `tests/behavior/*.md`.
- `.flightops/agent-crews/behavior-tests-execution.md`.
- Doc fixes from the sweep.
- The squawk files.
