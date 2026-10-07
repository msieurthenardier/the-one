# Leg: chat-polish

**Status**: completed
**Flight**: [Alignment](../flight.md)

## Objective

Three operator-reported fixes:
- **Local times (DD14).** Show clock times as people read them: local time, 12-hour, with
  AM/PM. Two surfaces change: the Chats list's Today rows, and the message attributions
  in a chat.
- **The composer's width (DD16).** The message box fills the pane's width instead of
  stopping at 760px, so the context-percentage readout above it lines up with the box's
  right edge.
- **Text selection in the desktop app (DD17).** The main window lets the operator
  highlight and copy text, such as a reply in a chat.

## Context

- **The operator's report** (2026-10-06): "The time on todays chats is military time. We
  should format that normally with am/pm."
- **The Chats list.** `areas/chat/chats-list.js` `timeOf()` (about line 91) returns
  `pad2(d.getHours()) + ':' + pad2(d.getMinutes())` for the Today bucket. The file's
  header comment (about lines 10–20) documents `HH:MM (24-hour)`, and says times are
  formatted by hand (never `toLocaleString`) so every engine and locale draws the same
  English labels. **Keep the hand formatting.**
- **The message attributions.** `areas/chat/message-bubble.js` `fmtTs()` (about line 107)
  returns `HH:MM:SS UTC`, rendered by `renderAttribution` as the `.msg-attribution-ts`
  suffix (" · 14:32:10 UTC"). Its comment defers a time-zone preference to "a future
  settings flight". DD14 makes it local time, which also answers decision-sheet item B5.
- **Out of scope** (DD14):
  - the Knowledge inventory's `Indexed: {indexed_at}` line (`knowledge-section.js` about
    lines 875 and 1029). It is a precise freshness signal:
    `test_flow_studio_knowledge_inventory.py` (about line 1168) and `kb-studio-round-trip`
    step 8 compare it before and after a re-index;
  - the Self-configuration tab's relative times;
  - any time-zone setting.

## Context: the composer's width (DD16)

- **The operator's report** (2026-10-06): "the message input box has a max width, but it
  looks a little strange because the context % indicator is pinned to the right. I think
  we just allow the message box to expand to the max width."
- **Today** (`css/chat.css`, the composer block, about lines 511–541):
  - `.composer` pads `12px 24px 20px`;
  - the telemetry row (`.composer-telemetry`) is `justify-content: flex-end` across the
    wrapper, so its readout sits 24px from the pane's right edge;
  - `.composer-box`, `.chat-attachments` and `.pending-queued-region` are capped at
    `max-width: 760px` and centred (`margin: 0 auto`).

  On a pane wider than 808px, the readout therefore floats right of the box.
- The message log (`.messages`) already spans the pane (`padding: 20px`).

## Context: text selection (DD17)

- **The operator's report** (2026-10-06): "the regular response message box has no copy
  option, and you cant even highlight to copy paste. The code box does but not the
  regular message."
- **The cause.** pywebview's `create_window` defaults to `text_select=False`. Its bundled
  `webview/js/customize.js` then injects `body { user-select: none; cursor: default }`
  into every page. This was confirmed in the installed v0.10.0 at
  `C:\Program Files\GleepGlorp AI\_internal\webview\js\customize.js`, line 4:
  `var disableText = '%(text_select)s' === 'False'`.
- **Where.** `the_one/interfaces/desktop/shell.py` builds the main window's
  `_create_kwargs` (about line 637: `frameless`, `resizable`, `background_color`, `hidden`,
  `min_size`) and passes no `text_select`. A browser tab is unaffected; the app's own CSS
  selects normally.
- **The code block's Copy button** (`markdown.js` about line 779) still works, because it
  copies through `navigator.clipboard` and needs no selection.
- **A per-message Copy button is out of scope** (new behaviour, DD7). It is GitHub issue
  [#224](https://github.com/msieurthenardier/the-one/issues/224).

## Acceptance Criteria

- [ ] **One formatter.** A single hand-written function formats a `Date` as a local
  12-hour clock time: `h:mm AM` / `h:mm PM`.
  - The hour has no leading zero, and the minutes have two digits. There is one space
    before an uppercase `AM` or `PM`.
  - **The edges:** midnight is `12:00 AM`, `12:05 AM` follows it, noon is `12:00 PM`,
    `1:00 PM` follows `12:59 PM`, and `11:59 PM` is the last minute.
  - Both surfaces use it. Put it where both files can reach it, loaded before either (for
    example a small `App.time` helper, or an existing shared module), and add it to
    `index.html` if it is a new file.
- [ ] **The Chats list.** A Today row's time reads like `3:45 PM`. The other buckets
  (weekday, month and day) and the pending row's "now" are unchanged.
  - The row's time slot fits the longest value (`12:59 PM`) at the list's 300px width
    without truncating or wrapping the title.
  - The header comment describes the new format.
- [ ] **The message attributions.** The suffix reads ` · 3:45 PM` in **local** time,
  without seconds and without "UTC".
  - Live turns and replayed history both use it; the timestamp source is unchanged.
  - A missing or invalid timestamp still renders no suffix.
  - `fmtTs`'s and `renderAttribution`'s comments are updated (drop "UTC" and the
    future-settings note, or point it at GitHub issue #223, the time tool and time-zone setting).
- [ ] **The composer's width (DD16).** `.composer-box`, `.chat-attachments` and
  `.pending-queued-region` lose their 760px cap and centring, and fill the wrapper's
  content width.
  - The telemetry readout's right edge and the box's right edge match within 1px, at 1024,
    at 1280 with the drawer open, and at 1920 with the drawer closed.
  - The box's left edge, the staged-image row's and the queued chip's left edge match.
  - Nothing else in the composer changes: the textarea growth, the toolbar, the focus
    ring.
  - The chat.css comments ("share the box's 760px column") are updated.
- [ ] **Text selection (DD17).** The main window is created with `text_select=True`. The
  splash keeps pywebview's default (it has no text to select).
  - The app's own `user-select: none` rules (the disclosure summaries, the mascot and so
    on) are unchanged, so those controls stay unselectable.
  - **The unit test** sits in `tests/test_desktop_shell.py`, beside the existing
    `main_call.kwargs` assertions (about lines 447 and 1089). It asserts
    `main_call.kwargs["text_select"] is True` on both the first-launch and the
    restored-state paths, and that the splash call does not pass `text_select=True`.
  - **The live check** belongs to the walk (leg 5) on a Windows test copy:
    `getComputedStyle(document.body).userSelect` is not `none`, and a drag over a reply
    selects it. Record it as a walk item in the flight log; no Linux browser test can
    reach it.
  - `the_one/agents.md`'s "Desktop launcher" notes gain one line on why `text_select=True`
    is set.
- [ ] **Tests.**
  - **The composer pin** in `tests/browser/test_flow_chat_composer.py` (about lines
    176–180: `box["maxW"] == "760px" and box["centred"]`,
    `box["width"] == min(760, box["column"])`) is updated in place. It now asserts the box
    fills the column and its right edge meets the telemetry readout's, at a wide viewport
    (drawer closed, so the pane is wider than 808px). Update the module docstring (lines
    10–11).
  - **A new browser test** (the `chats` lane, for example in
    `tests/browser/test_flow_chat_list.py`) evaluates the formatter in the page at the
    edge times above, plus one morning and one afternoon time.
  - **Pins updated in place,** each noted in the flight log:
    - `tests/browser/test_flow_chat_list.py`'s Today expectation (it builds the expected
      `HH:MM` from `h` and `m`, about line 51 onward);
    - `tests/browser/test_flow_chat_peer_attribution.py`'s three attribution regexes
      (about lines 182, 202 and 223: `\d{2}:\d{2}(:\d{2})? UTC`);
    - any other test that pins either format (grep `tests/` for `UTC`, `getHours`,
      `msg-attribution-ts` and `HH:MM`).
- [ ] **Specs and docs.**
  - `tests/behavior/start-a-chat.md` step 2 ("Today `HH:MM`") is re-authored to the new
    format, with an `Updated` line. Grep `tests/behavior/` for any other spec naming
    either format, and update it the same way.
  - Update `the_one/agents.md`: the Chats list "Times" bullet (about line 1401) and the
    `Message.created_at` note (about line 434, "· HH:MM UTC").
  - Update `CLAUDE.md`'s "Chats list and agent picker" paragraph ("Today `HH:MM`").
  - **For DD16:** `CLAUDE.md`'s "Chat composer" paragraph ("max 760px") and
    `the_one/agents.md`'s composer "Layout" bullet (about line 1426: "max 760px,
    centred", "share the box's 760px column").
  - `docs/ui-testid-registry.md` needs no change unless a testid changes. None should.
- [ ] **Gates:**
  - `ruff check` and `ruff format --check` pass;
  - `TEST_TIMEOUT=3000 make test-unit` passes, including `tests/test_desktop_shell.py`;
  - the `chats` lane passes, and so does `shared` (`TEST_TIMEOUT=3600`), which holds
    several chat-adjacent files.

  All with `THE_ONE_TEST_NETNS=1`.

## Verification Steps

- The new formatter test, then the `chats` lane.
- A screenshot of the Chats list with a Today row at an afternoon time and a chat's
  attributions, in both themes, and the composer with the telemetry readout at 1920 and
  1024. These are flight-log evidence only, never committed.

## Implementation Guidance

1. Read both formatters and every pin found by the greps above.
2. Write the shared formatter and switch both surfaces to it.
3. The new test, and the pins.
4. Specs and docs.
5. The lanes; then mark the leg `landed` and signal `[LAND:leg]`.

## Edge Cases

- **A row updated at local midnight** (`12:00 AM`) is still in Today. The bucket logic
  is unchanged.
- **A daylight-saving change:** local `getHours()` already follows the OS zone; nothing
  extra is needed.
- **A connector message from another time zone** shows in the operator's local time. That
  is intended.

## Files Affected

- `the_one/interfaces/web/static/css/chat.css` (the composer block).
- `the_one/interfaces/desktop/shell.py` (`_create_kwargs`), `tests/test_desktop_shell.py`.
- `the_one/interfaces/web/static/js/areas/chat/chats-list.js`,
  `areas/chat/message-bubble.js`, the shared formatter's home, and `index.html` if a new
  script is added (a restart is needed for `index.html`).
- `tests/browser/test_flow_chat_list.py`, `tests/browser/test_flow_chat_peer_attribution.py`,
  `tests/browser/test_flow_chat_composer.py`,
  and any other pin.
- `tests/behavior/start-a-chat.md`, `the_one/agents.md`, `CLAUDE.md`; the flight log.

## Citation Audit

Checked on 2026-10-06 in the working tree:
- `chats-list.js`: the header comment (lines 10–20), `timeOf` (line 91).
- `message-bubble.js`: `fmtTs` (line 107), `renderAttribution` (line 121).
- `test_flow_chat_list.py`: `_STAMPS_JS` (line 44).
- `test_flow_chat_peer_attribution.py`: the regexes (lines 182, 202 and 223).
- `start-a-chat.md`: step 2 (line 112).
- `agents.md`: lines 434, 1401 and 1426.
- `chat.css`: the composer block (lines 511–541) and `.pending-queued-region` (line 597).
- `test_flow_chat_composer.py`: the docstring (lines 10–11) and the width pin (lines
  176–180).

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
