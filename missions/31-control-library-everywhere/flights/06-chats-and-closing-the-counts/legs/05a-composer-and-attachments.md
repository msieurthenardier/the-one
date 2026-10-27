# Leg: composer-and-attachments

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Move the composer side of the chat area onto the library:
- the composer onto `App.ui.composer` (leg 04);
- the staged-image and queued-message chips onto `App.ui.chip` with `lead` / `onRemove` (A6, A7);
- the deleted-agent health banner onto `App.ui.banner` (A5);
- the blocked state through `setBlocked` (B13 with 0.3: Attach disabled, the box dimmed);
- focus to the message box after an agent pick (0.1, DD11 1);
- the Chats empty state's text column centred (B6).

Delete the area composer renderer and the legacy composer, queued-chip and attachment classes, and retarget their test locators.

## Context
- **Flight decisions:** DD4 (the class handover: legacy names deleted, locators retargeted), DD7 (A5, A6, A7, B6, B13; ledger rows 5-7, 23, 25 and 27), DD11 (1 and 3), DD13 and DD15 (re-read `vision-round-trip`).
- **After leg 04:** `App.ui.composer(opts)` → `{el, input, setPlaceholder, setModel, setBusy, setBlocked, openFilePicker, getValue, setValue, focus, slots: {telemetry, attachments, attachmentsStatus, queued}, fit, destroy}`.
  - **Send semantics:** Enter calls `onSend(rawValue)` whenever the input is enabled, busy or not; the control never clears the input; Send's disabled state is `blocked || busy`.
  - **Attach:** Attach calls `onAttach()`, and the area calls `openFilePicker()`. The file input's `change` calls `onFiles(files)`.
  - **Slots:** attachments uses inline `style.display` plus its live status; queued and telemetry use `hidden`.
- **Today's wiring:**
  - **`chat.js`** builds `App.chat.composer.create()` (`:145`), takes `inputEl`, `fileInputEl`, `attachBtn`, `stopBtn` and `sendBtn` (`:155-159`) and passes them to the modules through `ctx` (`:189-193`). It also:
    - calls `composer.render({…})` and toggles `composer.telemetryRow.hidden` (`:278-282`);
    - computes `applyComposerState` (`:369-373`: `inputEl.disabled = blocked; sendBtn.disabled = blocked || busy`);
    - builds the hand-made health banner in `setSessionHealth` (`:406-421`, `div.chat-session-banner[role=status]` inserted before the composer; its clear path sets `inputEl.disabled = false; sendBtn.disabled = false` even while busy);
    - wires the keydown, `input` → `fit`, Send click and Stop click listeners (`:441-470`).
  - **The modules** write the controls directly through `ctx`: `send.js` (`:14-16`, `:33` `updateStopControl`, `:66`, `:84-92`), `attachments.js` (`:13-15`, `:54-55`, `:143-164`, including the attach click guard at `:150-152`), `socket.js` (`:239`, `:243`), `turn-frames.js` (`:74`, `:194`, `:222`), `session-flow.js` (`:299`, `:325-330`) and `sign-in.js` (`:313`, the focus hand-off to the input).
  - **The staged-image chip** (`attachments.js` `buildAttachmentChip`, about `:76-110`): `div.chat-attachment.chip[data-testid=chat-attachment][data-attachment-index]` with a thumbnail `img` and a hand-made `.chip-remove` "✕" button. It is the `js/areas/chat/attachments.js` `chip` ownership row (a leg 02 `MOVES` entry, `retire_by` 05a).
  - **The queued chip** (`hold-queue.js:31-60`): `div.pending-queued-chip[data-testid=pending-queued][aria-live=polite]` with a "Queued:" label, the text and a hand-made 22px "×" `pending-queued-cancel` button, mounted in `ctx.composer.queuedRegion`.
- **The CSS to delete** (`css/chat.css`):
  - the composer `:555-624` (`.composer`, `-telemetry`, `-box`, `-input`, `-toolbar`, `-model`, `-send`, `-stop`, `.chat-attachments`);
  - the queued chip `:630-643`;
  - the banner `:291`;
  - and any rule still naming them.

  `components.css:570-579` `.chip-remove` loses its last user here, so delete it and move its contrast gate (`tests/test_design_tokens_a11y.py:402-431`) to the new remove button.
- **Tests reaching these classes:**
  - `test_flow_chat_composer.py` (19);
  - `test_flow_chat_image_attach.py` (12);
  - `test_flow_chat_queued_render.py` (11);
  - `test_flow_chat_live_updates.py` (2), `test_flow_chat_start_flow.py` (2), `test_flow_chat_start_reconnect.py` (1);
  - `test_ui_chip_list_contract.py` (1, a `.chip-remove` reference; check it);
  - `tests/test_design_tokens_a11y.py` (3);
  - `tests/test_nav_helper.py` (3, retired-selector entries; check whether any new name must join `RETIRED_SELECTORS`).
- **0.1:** the agent picker returns focus to its opener in the modal's `onClose` (`agent-picker.js:195-200`), then `host.onPick(picked, {opener})` runs. Once the pick lands on the pending chat, focus must go to the message box. The pick path is in `session-flow.js` (`pickAgent` / `goPick` / `renderPending`).
- **0.3:** a deleted agent's chat is blocked by `setSessionHealth('agent_deleted')`. Attach stays enabled today, and `setBlocked` fixes that. The context-window 404 is in `socket.js:267` (`session_joined`). Leg 05c fixes it with DD11 5, because both live in the telemetry fetch. This leg does not touch it.
- **B6:** the Chats empty state is built in `chat-pane.js` (`renderWelcome`, `chat-welcome*`). Today the mascot is centred and the text is left-aligned. B6 (a) centres the text column. The guidance state and the "Hello." greeting keep their content.
- **The chip remove button's target size.** The accessibility review of batch B2 noted that the library's `chip-remove-btn` (leg 03c) is 22×22px, under WCAG 2.2's 24px target size. This leg makes it **24px** in the library (a ledger row), since A6 and A7 are its first consumers.
- **Line budget:** after the leg, `chat.js` stays at 800 lines or fewer, and so does every module.

## Inputs
- Leg 04 landed: the six controls, the parity test and the `contracts-chat` lane.

## Outputs
- **The composer on the library:**
  - `chat.js` builds `App.ui.composer({…})` with today's testids, and passes the handle to the modules (`ctx.composer`) instead of the raw elements.
  - Every direct write becomes a handle call: `inputEl.disabled` and `sendBtn.disabled` go through `setBusy` / `setBlocked`; `setInputValue` becomes `composer.setValue`; Stop's visibility goes through `setBusy`.
  - `applyComposerState` and `setSessionHealth` call `setBlocked(reason|null)`, so clearing the banner while busy keeps Send disabled (the intended fix, recorded as a ledger row).
  - `send.js`'s Enter and Send paths become the composer's `onSend`. The area's guards and its clearing on success stay in `send.js`.
  - Attach's guard (`attachments.js:150-152`) becomes `onAttach`, which calls `composer.openFilePicker()`.
  - The file input's `change` becomes `onFiles`.
  - `areas/chat/composer.js` is deleted, along with its script tag; the cache-busting order test still passes.
- **A6:** the staged-image chip is `App.ui.chip({label: {name or "Image n"}, lead: img, onRemove, removeLabel: 'Remove image {n}', testid: 'chat-attachment', dataset: {attachmentIndex}})`.
  - The row keeps today's inline `style.display` and live status.
  - The `chip` ownership row and its `MOVES` entry are deleted, and `TOTAL_USES` is lowered.
- **A7:**
  - the queued chip is `App.ui.chip({label: text, lead: a "Queued" label span, onRemove: cancelPendingQueued, removeLabel: 'Cancel queued message', testid: 'pending-queued'})` in the queued slot;
  - the label reads "Queued", without the colon;
  - it keeps the region's `aria-live` behaviour and the keyboard cancel.
- **The remove button at 24px:** the library `chip-remove-btn` takes a 24×24 target, with no negative margin that could clip the focus ring. Its contrast gate moves from `.chip-remove` to it.
- **A5:** the deleted-agent warning is `App.ui.banner({tone: 'warning', role: 'status', text})` in the same place. `.chat-session-banner` is deleted.
- **B13:** the blocked composer is dimmed through `setBlocked`, with Attach disabled (0.3).
- **0.1:** after an agent pick lands on the pending chat, `composer.focus()` runs, unless a leave-guard dialog was cancelled with Stay, which keeps focus at the opener.
- **B6:** the empty state's text column is centred under the mascot. That is area layout in `chat.css` (`chat-welcome*`), so it is not a library change.
- **The CSS and locators:** the legacy rules above are deleted, and the locators are retargeted to testids or the composer's `ui-composer-*` classes, never relaxed. The `RETIRED_SELECTORS` registry gains any removed class a test could reintroduce, if the registry's rules call for it.
- **The parity test** (leg 04) drops its composer pair, since the old renderer is gone.
- **Behavior spec:** `tests/behavior/vision-round-trip.md` is re-read for the attachment chip and re-authored if a step names `.chat-attachment` classes or the "✕" glyph.
- **Docs:** CLAUDE.md "Chat composer" (the composer is now `App.ui.composer`, built in `chat.js`) and `the_one/agents.md` "Chat composer"; the catalogue's Composer row names its consumer.
- **Ledger rows 5, 6, 7, 23, 25 and 27** confirmed, plus new rows for the 24px remove button and the `blocked || busy` Send fix.

## Acceptance Criteria
- [ ] `areas/chat/composer.js` is gone. `git grep -n "composer-box\|composer-input\|pending-queued-chip\|chat-session-banner\|chip-remove\b\|App.chat.composer" -- the_one/ tests/` finds nothing (the testids `chat-input`, `chat-send-btn`, `pending-queued`, `chat-attachment` and similar remain).
- [ ] **Every composer behaviour test passes:** `test_flow_chat_composer.py`, `test_flow_chat_image_attach.py`, `test_flow_chat_queued_render.py`, `test_flow_chat_start_flow.py`, `test_flow_chat_start_reconnect.py` and `test_flow_chat_live_updates.py`. Only locators are retargeted; no assertion is weakened.
- [ ] **New tests, failing first where marked:**
  - after picking an agent, `document.activeElement` is `chat-input` — **failing today** (0.1);
  - in a deleted agent's chat, Attach is disabled — **failing today** (0.3);
  - the banner is a `role=status` library banner;
  - the staged-image chip's remove button is named "Remove image 1" and is 24px;
  - the queued chip reads "Queued" with a "Cancel queued message" button;
  - clearing the banner while a turn runs keeps Send disabled — **failing today**;
  - the empty state's text column is centred (computed `text-align` or alignment check).
- [ ] **The ownership allowance** has no `js/areas/chat/attachments.js` row, its `MOVES` entry is gone, and `tests/test_ui_ownership.py` passes.
- [ ] **Line budget:** `chat.js` and every chat module are 800 lines or fewer (`tests/test_area_module_size.py`).
- [ ] **Static guards:** `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` (with the moved remove-button gate) pass.
- [ ] **A capture comparison** of the composer, staged-image, queued, deleted-agent, empty and pending states against the before set (PIL) shows only ledger rows 5-7, 23, 25 and 27 and the 24px button.
- [ ] **Lanes:** `chats`, `chats-transcript`, `contracts-chat` and `contracts-controls` (the chip remove size) pass, with `THE_ONE_REQUIRE_WEBKIT=1` for the contract lanes.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. The unit guards (`test_ui_ownership`, `test_ui_guards`, `test_area_module_size`, `test_token_definitions`, `test_design_tokens_a11y`, `test_index_asset_cache_busting`), `-q -x --timeout 120`.
2. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane chats-transcript -x --tb=short`, then `--lane chats`, then the contract lanes with `THE_ONE_REQUIRE_WEBKIT=1`.
3. `THE_ONE_TEST_NETNS=1 .venv/bin/python scripts/ui_capture.py --out <scratch> --surfaces <composer, staged, queued, ghost, empty, pending>`, then a PIL comparison with the before set.
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The failing-first tests** (0.1, 0.3, busy-while-banner-clears).
2. **The composer swap** in `chat.js`, then each module's writes become handle calls, one module at a time, running `--lane chats-transcript` after each.
3. **The chips** (A6, A7) and the 24px remove button; then the banner (A5) and the blocked state (B13).
4. **0.1 and B6.**
5. **The deletions** (`composer.js`, the CSS) and the locator retargets; the parity test's composer pair goes.
6. **The allowance, the spec re-read, docs, captures,** then the lanes and `make test-unit`.

## Edge Cases
- **The IME guard and the busy Enter** (the composer's contract): an Enter during an IME composition sends nothing; a busy Enter holds the message (`hold-queue.js`).
- **Send while staged images exist and the text is empty:** this still sends (`send.js` decides).
- **A guarded send** (idle, joining, a closed socket) keeps the text: the area clears only on success.
- **The attach guard:** `onAttach` keeps today's busy and blocked checks in the area. A blocked composer's Attach is disabled anyway.
- **The live status of the attachments row** must still announce one change per add or remove, never re-announce every chip.
- **The pending chat after a leave-guard Stay:** focus stays on the opener (the picker's contract). Only a completed pick moves focus to the input.
- **The deleted-agent drawer** and its context-window 404 are leg 05c's.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat.js`, `js/areas/chat/{send,attachments,hold-queue,socket,turn-frames,session-flow,sign-in,chat-pane}.js`; `js/areas/chat/composer.js` (deleted); `index.html`.
- `js/ui/feedback.js` (the 24px remove button), `css/components.css`, `css/chat.css`.
- The tests listed in Context, the parity test, `tests/test_design_tokens_a11y.py`, possibly `tests/test_nav_helper.py`.
- `tests/_ui_ownership_allowance.py`, `docs/ui-control-inventory.md`, CLAUDE.md, `the_one/agents.md`, `tests/behavior/vision-round-trip.md` (if re-authored), the flight log.

## Citation Audit
- `chat.js:145`, `:155-159`, `:177-178`, `:189-193`, `:278-282`, `:369-373`, `:406-421`, `:441-470`. FD grep after B2 (2026-10-27).
- `hold-queue.js:31-60`, `attachments.js:76-110`, `:143-164` (the guard at `:150-152`), `agent-picker.js:195-200`, `socket.js:267`. FD grep.
- `css/chat.css:291`, `:555-643`. FD grep.
- **Leg 04 has not landed at design time.** The composer handle and its slot shapes are taken from the leg 04 spec. The leg's Developer re-checks them against the landed control before starting.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence)
- **Small library additions this leg makes**, each with a contract test in both engines:
  - **`composer.fileInput`** on the handle, a read-only reference like `input`. `attachments.js:53-55` toggles `data-staged` on it, and tests assert that attribute on `[data-testid=chat-image-input]` (`test_flow_chat_image_attach.py:101`, `:169`; `test_flow_chat_start_flow.py:345`; `test_flow_chat_composer.py:587`).
  - **`slots.queued` becomes a persistent `aria-live="polite"` region** in the composer, so a newly placed queued chip is announced. A chip built together with its content is not reliably announced.
  - **`App.ui.chip` gains `labelHidden`** (the label is visually hidden but still names the chip) and **`truncate`** (one line with an ellipsis, `min-width: 0`).
  - **The remove button is 24×24 with no negative margin.** It reaches every `chip({onRemove})` consumer (the Library and MCP editors through `chipList`), so `contracts-controls` and the studio lanes (`library`, `mcp`, `mcp-connection`, `knowledge`, `agents`) run for layout shift.
- **A6 keeps today's names:**
  - the staged-image chip is `App.ui.chip({label: 'Staged image ' + n, labelHidden: true, lead: img, onRemove, removeLabel: 'Remove staged image ' + n, removeTestid: 'chat-attachment-remove', testid: 'chat-attachment', dataset: {attachmentIndex: …}})`, with the thumbnail's `alt=""` (the label names the chip);
  - the assertions at `test_flow_chat_image_attach.py:236-241` hold unchanged (FD answer: no visible "Image n" text);
  - check that `applyDataset` maps camelCase to `data-attachment-index`.
- **A7:**
  - `App.ui.chip({label: text, truncate: true, lead: 'Queued' span, onRemove, removeLabel: 'Cancel queued message', removeTestid: 'pending-queued-cancel', testid: 'pending-queued'})` in the live queued slot;
  - long queued text stays one line with an ellipsis, as today. The captures include a long-message case.
- **One blocked computation:**
  - `chat.js` defines `computeBlocked()` (the health banner active, or `pending && (setupIncomplete || validating)`) and one `applyComposerState()` that calls `composer.setBlocked(reason|null)` and `composer.setBusy(ctx.send.isCurrentBusy())`. `setSessionHealth` and every former `state.sessionBannerEl` guard call it: `send.js:92`, `attachments.js:151`, `socket.js:87`, `:239`, `:243`, `turn-frames.js:74`, `:194`, `:222`.
  - `session-flow.js:299` and `send.js:66` (`sendBtn.disabled = true`) become `setBusy(true)` through `updateStopControl`, which keeps calling `setBusy(isCurrentBusy())` on joins and rebinds.
  - `state.sessionBannerEl` becomes a banner handle plus a `bannerActive` flag.
  - This is written **before** any module is touched, so every guard changes in one pass.
- **A5:** one persistent `App.ui.banner({tone: 'warning', live: 'status'})`, mounted above the composer and driven by `set(text)` / `hide()`, never created and removed per change, so its text is announced reliably. The look changes from a top-rule bar to the library warning banner (ledger row 5, approved).
- **The handle mapping the leg left implicit:**
  - `composer.render({agent, model})` becomes `setPlaceholder('Message {agent}…' | 'Message…')` and `setModel(…)` (`chat.js:278`);
  - `telemetryRow` becomes `slots.telemetry` (`chat.js:177`, `:282`);
  - `sign-in.js:313` uses `composer.input` and `composer.focus()`;
  - `session-flow.js:325`, `:330` (`inputEl.value`) become `composer.getValue()`;
  - `ctx.send.setInputValue` (used by `session-flow.js`) becomes `composer.setValue`;
  - `send.js:89` trims the raw value from `onSend` in the area;
  - the old `chat.js:441` keydown guards (Enter while busy goes to the hold queue) move into `send.send`, since the control calls `onSend` for a busy or empty Enter;
  - the area passes the legacy testids: `chat-input`, `chat-send-btn`, `chat-stop-btn`, `chat-attach-btn`, `chat-image-input`, `chat-model`, `chat-attachments`, `chat-attachments-status`, `pending-queued-region`.
- **0.1, one-shot:** focus moves to the composer only after a **picker** pick resolves `true` (the `requestPick`/`go(...).then(ok)` result), so it also covers Jump to's "New chat…", which goes through the picker. It never moves from `renderPending` re-renders, the drawer's `chatWith` or direct hash entry. A leave-guard Stay resolves `false`, so focus stays on the opener. The test makes a valid pick with the input enabled.
- **B6:** `.chat-welcome-actions` gets `justify-content: center` too, and the guidance and notice are centred. The test checks the New chat button's horizontal centre, not just `text-align`.
- **The AC grep's exact legacy tokens** (avoiding the `ui-composer-*`, `ui-chip-remove` and `chip-remove-btn` collisions): `git grep -nE "\.area-chat \.composer|\.composer-(box|input|toolbar|model|send|stop|telemetry)\b|pending-queued-(chip|label|text|cancel)\b|chat-session-banner|\.chip-remove[ {,:]|App\.chat\.composer" -- the_one/ tests/`, which must find nothing. The old composer's CSS-class queries in tests (`test_flow_chat_composer.py:530`'s `.pending-queued-region` and `.chat-attachments`) are retargeted to testids.
- **`tests/test_index_asset_cache_busting.py:113`** (`test_static_ref_check_rejects_an_area_script_above_ui_core`) uses `areas/chat/composer.js` as its fixture. It is retargeted to `areas/chat/send.js`, and `index.html:76`'s tag is removed.
- **The moved contrast gate** checks the ghost remove button's icon colour (`--fg-secondary`) against the chip fill and the queued chip's fill, as a UI component at 3:1, replacing the `--status-danger` pair. The `.pending-queued-chip` comment at `test_design_tokens_a11y.py:161` is updated. The `.chip-remove` rules are at `components.css:573-582` (not `:570-579`).
- **The parity test** drops its composer section (about `:221-280`, which reads `.area-chat .composer`, `.composer-box` and so on), and its B13 check becomes this leg's real 0.3 test. Its docstring is updated.
- **`vision-round-trip.md:78`** names `chat-attachments` and the "✕" glyph. The glyph step changes (the library `x` icon), so the spec **is** re-authored.
- **Check before editing:** the catalogue Chip row (`docs/ui-control-inventory.md:81`) already carries B2 edits.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only, against the landed leg 04): approve with changes.** Applied as the amendments above. FD answers:
  - the composer exposes `fileInput`;
  - the queued slot is the live region;
  - staged chips keep their names, with no visible label (`labelHidden`);
  - the exact grep tokens;
  - the moved gate's colour pair.
- **No second cycle.** The additions are small library options inside the chips and composer this leg already consumes, each contract-tested, and the rest is precision on the existing plan.
