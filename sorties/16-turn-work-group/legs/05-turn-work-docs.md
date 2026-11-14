# Leg: turn-work-docs

**Status**: completed
**Flight**: [One work line per chat turn](../flight.md)

## Objective
Bring the capture tool, the behavior specs and the docs in line with the new turn shape, now that the code is final.

## Context
- Legs 1 to 4 built the new shape, its tests, and deleted the old code. This leg changes no product behaviour.
- The work is specified in sections 3, 4 and 5 of [`04-turn-work-cleanup.md`](04-turn-work-cleanup.md) ("Capture surfaces", "Behavior specs", "Docs"). They were written for one cleanup leg and split off at its design review. Read them there; the additions below come from that review and take precedence where they differ.
- Flight DD2 to DD8 are what the docs must describe; DD11 lists the specs.
- Nothing is committed in this leg. It is the last autonomous leg; the flight review follows.

## Inputs
- Legs 1 to 4 landed, uncommitted; the chat lanes and the unit tier green at the end of leg 4 (read its flight-log entry, and leg 3's "Open for the Flight Director" list).
- The final interface of `areas/chat/turn-work.js` and of `App.ui.turnWork` as they are in the tree (read the code, not the leg artifacts, when the two differ).

## Additions to the three sections

### Capture surfaces (section 3)
- `scripts/ui_capture.py --surfaces a,b` filters the run and `--list` lists the surfaces. The tool starts its own scratch instance and refuses ports 8484 and 8485, the default data directory and an `--out` inside the repo.
- Surfaces that script the old shape, to rewrite or remove: `chat-live-streaming` (line 2388; its `_stream_text` helper at 2086 waits for an assistant bubble with streamed text), `chat-live-after-stop` (2409, uses the same helper), `chat-joined-rich-top`, `-mid`, `-bottom` and `-disclosures-open` (2298-2320: their descriptions name tool activity and thinking; `_rich_scroll` opens every `details` in the log, which still works for the group, so these mostly need new descriptions and a check that the seeded chat still shows what they claim), and `chat-live-thinking` (2394; leg 2 already pointed its ready selector at the group, but its name and description still say "thinking"). `chat-live-queued` is probably fine; check it.
- The three new surfaces: a turn working, a finished turn with the group open, a stopped turn.
- Run only the changed and new surfaces: `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <dir outside the repo, under $HOME> --surfaces <names>`. Record the directory and the surface names. Then **look at the PNGs** (both themes) for the three new surfaces and say in the flight log, in a sentence each, what they show; a capture that ran but shows the wrong state is a failure.

### Behavior specs (section 4)
Exact places found at the design review:
- `chat-loop-hang-and-cancel.md:29, 40, 42` (streamed text, "Thinking…", step 4).
- `extended-thinking-tool-turn.md:41-42, 54-56` ("tool-trace shells", the "`Thinking` `<details>` disclosure").
- `anthropic-plan-chat-parity.md:36` (step 3; also line 11).
- `anthropic-plan-token-chat.md:34`.
- `chat-roundtrip.md:27, 37-38`.
- `agent-governance-and-search.md:47` ("streamed assistant text"; line 63 is only a URL and needs no change).
- `stub-connector-round-trip.md:127-128`.
- `agent-step-limit-notice.md`: read it; its selectors (`chat-step-limit`, `chat-agent-error`) are unchanged, so it may need only the steps that mention a reply bubble or tool activity.
- `start-a-chat.md:134` is a pointer and needs no change. Hits for "placeholder" as an input attribute or "trace" as a verb are false positives.

### Docs (section 5)
- Add `README.md`: line 57 says "Every reply that used a tool gets a **Tool activity** panel" and line 66 "Replies stream in". Reword both for the new shape.
- `CLAUDE.md`: the "Chats pane" paragraph (the transcript, "Charts in chat", "Widgets in chat"), the chart paragraph near line 308, the lane bullets. The sentence "a Stop mid-block leaves the cut-off notice and the source never runs" is here, in "Widgets in chat".
- `the_one/agents.md`: lines 1648 ("Chat module map"), 1654 (Tail hold), 1656 (Boundaries), 1657 (Placeholder lifecycle), 1669 and 1672 ("Chat transcript on the library", Streaming), 2354 ("Adding a factory"). Line numbers will have moved; find them by heading.
- `SECURITY-MODEL.md` "Live visuals" (line 471): the review found no sentence there about the streaming hold. Read the section; change it only if it describes a state that no longer exists, and add one sentence that pending text is shown only as plain text in the preview and that a stopped turn's unclosed widget block never runs.
- `docs/widget-format.md:23` ("stream was stopped or cut off") and `:146` ("A reply that is streamed and the same reply opened later") may still hold; read and fix only what is wrong. `docs/chart-format.md:13` is a false positive.
- Check `evals/README.md` and `the_one/connectors/README.md` with the same grep; the review found nothing relevant there.

## Acceptance Criteria
- [ ] `scripts/ui_capture.py --list` shows the three new surfaces and no surface whose name or description claims the old shape (a streaming bubble, a "Tool activity" trace, a thinking disclosure, a visual placeholder).
- [ ] One capture run of the changed and new surfaces succeeded; the flight log records the output directory, the surface names, and what each of the three new surfaces shows in both themes.
- [ ] Each listed behavior spec is re-authored where it described the old shape; `grep -nE 'Tool activity|trace-shell|tool-trace|thinking-indicator|Thinking…|progressively|strictly growing|streamed assistant text' tests/behavior/*.md` finds nothing that describes current behaviour. No file under `tests/behavior/*/runs/` is edited.
- [ ] `CLAUDE.md`, `the_one/agents.md`, `README.md`, `SECURITY-MODEL.md` and the format docs describe the new shape; `the_one/agents.md` has a "Turn work group (sortie 16)" section as section 5 specifies; "Adding a factory" no longer has the stale asset-count step.
- [ ] `grep -rnE 'stream-commit|visual-stream|streamCommit|visualStream|App\.ui\.trace\b|setTailHold|chart\.placeholder|trace-shell|thinking-disclosure|thinking-indicator|chat-chart-placeholder|chat-widget-placeholder' CLAUDE.md README.md SECURITY-MODEL.md the_one/agents.md docs/ scripts/` shows only "retired" or history mentions.
- [ ] `THE_ONE_TEST_NETNS=1 make test-unit` passes (some unit tests read `CLAUDE.md`, the docs and `scripts/`); `ruff check` and `ruff format --check` on `scripts/` are clean.
- [ ] No file under `the_one/` other than `the_one/agents.md` changed in this leg, and no test file changed except where a unit test pins doc text this leg rewrote.

## Verification Steps
- `.venv/bin/python scripts/ui_capture.py --list`.
- The capture run above; open the PNGs with the image reader.
- The two greps in the acceptance criteria.
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `git status --short` against the state at the start of the leg (record `git status --short | wc -l` first).

## Implementation Guidance
1. Read sections 3 to 5 of the cleanup leg, this leg's additions, the flight's DD2 to DD8 and DD11, and the code of `areas/chat/turn-work.js` and `js/ui/turn-work.js`.
2. Capture surfaces, then the run, then look at the output.
3. Behavior specs.
4. Docs: `the_one/agents.md` first (the deep reference), then `CLAUDE.md` (compact, pointing to it), then the rest.
5. Gates and the flight-log entry.

## Edge Cases
- **The capture tool's seeded chats** (`seed_chat()`) may hold history shaped for the old view (several assistant messages per turn): that is fine and useful, since replay groups them; check what the "rich" surfaces now show.
- **A scripted live state** is injected socket frames through the tool's `SocketScript` helper, never a real send.
- **`CLAUDE.md` is long and dense**: change the paragraphs named; do not reflow or reorder others.
- **A unit test that pins a doc sentence** this leg rewrites: update the pin in the same step and say so.

## Files Affected
- `scripts/ui_capture.py`.
- `tests/behavior/agent-step-limit-notice.md`, `chat-loop-hang-and-cancel.md`, `extended-thinking-tool-turn.md`, `stub-connector-round-trip.md`, `chat-roundtrip.md`, `anthropic-plan-token-chat.md`, `anthropic-plan-chat-parity.md`, `agent-governance-and-search.md`.
- `CLAUDE.md`, `README.md`, `SECURITY-MODEL.md`, `the_one/agents.md`, `docs/widget-format.md` (if needed).
- `sorties/16-turn-work-group/flight-log.md`.

## Citation Audit
Checked on 2026-11-13 by the leg 4 design reviewer (read-only) against the tree with legs 1 and 2 landed. Legs 3 and 4 do not edit the files below except `CLAUDE.md`'s lane bullets and `scripts/ui_capture.py` (leg 2, one selector), so line numbers may have moved by a few lines; find by name.

- `scripts/ui_capture.py:2086` (`_stream_text`), `2298-2320` (the `chat-joined-rich-*` surfaces), `2388` (`chat-live-streaming`), `2394` (`chat-live-thinking`), `2409` (`chat-live-after-stop`); `--surfaces` and `--list` exist; the tool guards its ports, data directory and `--out` - verified (reviewer)
- The behavior-spec lines listed above - verified (reviewer)
- `README.md:57, 66` - verified (reviewer)
- `the_one/agents.md:183, 1648, 1654, 1656, 1657, 1669, 1672, 2354` - verified (reviewer)
- `SECURITY-MODEL.md:471` "Live visuals" has no streaming-hold sentence - verified (reviewer)
- `docs/widget-format.md:23, 146`; `docs/chart-format.md:13` - verified (reviewer)

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
