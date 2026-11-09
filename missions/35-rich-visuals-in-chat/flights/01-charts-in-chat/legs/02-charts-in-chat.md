# Leg: charts-in-chat

**Status**: completed
**Flight**: [Charts in Chat](../flight.md)

## Objective
Draw ```` ```chart ```` blocks as charts inside assistant replies in the chat. History and live replies both draw them. While a top-level chart block streams, the reply shows the glimmering placeholder; the chart replaces it the moment its closing fence arrives. A broken block shows the error notice, and a cut-off block shows the muted notice. Commit boundaries are confirmed by the parser, so no fence is ever split.

## Context
- Flight design decisions: **DD6** (the per-call `codeBlockRenderers` option, a re-entrant `renderOptions`, try/catch, `meta.closed`), **DD8** (the streaming placeholder, the tail-hold seam and its invariants, top-level only, the anchored type match, destroy points), **DD9** (the error and cut-off notices, built by leg 1's `App.ui.chart.block`), **DD10** (the over-detect rule, parser-confirmed boundaries, three candidate kinds, waiting for the opener's newline), **DD14** (mock-driven flow tests in `chats-transcript`), **DD15** (frozen testids).
- Leg 1 (landed) provides:
  - `App.ui.chart.block(source, {closed, testid})` (`js/ui/chart.js:1425`): the chart for a valid spec, even when `closed === false`; otherwise a danger notice, or a muted cut-off notice when `closed === false`.
  - `App.ui.chart.placeholder({type, testid}) -> {el, setType, setSource, destroy}` (`js/ui/chart-placeholder.js:64`).
  - Derived testids, so with `testid: 'chat-chart'`: `chat-chart-plot`, `chat-chart-tooltip`, `chat-chart-data`, `chat-chart-error` (and `-error-details`). The placeholder's "Show source" is `chat-chart-placeholder-source`.
  - `markdown.js` and `message.js` were not touched by leg 1 (`git status`).
- Only assistant replies render markdown (`transcript.js:74`), so charts never appear in user, routine-run, tool or thinking text.
- Copy reply keeps copying the raw received text (`transcript.js:96`, `:312`).

## Inputs
- Leg 1 landed: `js/ui/chart.js`, `js/ui/chart-placeholder.js`, the `--chart-*` tokens and the corpus under `tests/fixtures/charts/`.
- `markdown.js`, `ui/message.js`, `areas/chat/transcript.js` as at `293a81d2` (leg 1 does not touch them).

## Outputs
- `js/markdown.js`: the `codeBlockRenderers` option, a re-entrant `renderOptions`, a guarded renderer call, `meta.closed` on CODE_BLOCK nodes.
- `js/ui/message.js`: `setTailHold(offset, node | null)` on the streaming handle; catalogue text updated.
- `js/areas/chat/transcript.js`: the chart renderer in `mdOpts()`; parser-confirmed commit boundaries; open-chart detection; the placeholder lifecycle.
- `tests/browser/test_flow_chat_charts.py` (new), in `chats_transcript_pat`.
- Additions to `tests/browser/test_ui_message_contract.py` (the hold) and `tests/browser/test_markdown.py` (the option, re-entrancy, `meta.closed`).
- `the_one/agents.md`: a "Charts in chat" section. CLAUDE.md: one line in the Chats pane / transcript paragraph and the lane table if budgets move.

## Acceptance Criteria

**Renderer option (markdown.js)**
- [ ] AC1. `App.markdown.render(text, {codeBlockRenderers: {chart: fn}})` calls `fn(source, {lang, closed})` for each CODE_BLOCK whose lang is exactly `chart`, and appends the returned Node in place of the code well. A falsy return, a non-Node return, or a throw falls back to the normal code well (with its copy button). The lang match is the parser's own token: the first whitespace-separated token, case-sensitive (`markdown.js:171`). So ```` ```chart extra ```` is a chart and ```` ```Chart ```` is not, in both the renderer and the stream scanner. Other langs are unaffected. With no option, **rendered HTML** is byte-identical to today. The three `parse` pins in `tests/browser/test_markdown.py` (`:167`, `:177`, `:187`) that assert `"meta": {"lang": ...}` exactly gain `"closed": True`; that is the only edit to that file's existing tests.
- [ ] AC2. `render` restores the previous `renderOptions` in its `finally` (`markdown.js:971-976`). A test where a renderer itself calls `App.markdown.render` (with other options) shows the outer render's later blocks still get the outer options.
- [ ] AC3. CODE_BLOCK nodes carry `meta.closed`: `true` when a closing fence line was consumed (`markdown.js:176-182`), `false` when the input ran out first. A nested fence ended by the end of its list item is also `false`, deliberately (DD6). `parse` output for existing tests changes only by that key.

**Tail hold (message.js)**
- [ ] AC4. The streaming handle gains `setTailHold(offset, node | null)`. Contract tests (both engines) pin the DD8 invariants:
  - the handle keeps the logical tail string;
  - `tail()` always returns the full text, and `appendText` appends to it with or without a hold;
  - with a hold, the visible text node shows only `tail.slice(0, offset)`, and `node` sits right after it;
  - `commit(fragment, consumed)` with `consumed > offset` clears the hold (removing `node` from the bubble, never destroying it); with `consumed ≤ offset`, the hold stays and `offset` shifts down by `consumed`;
  - `commit` still returns early on an empty or null fragment without consuming, and the hold shift happens only **after** that early-return check (a contract test: an empty-fragment commit leaves the offset unshifted);
  - `finalize` clears the hold before appending, which also covers a hold left stale by `drainPacing` (it appends without committing);
  - `setTailHold(…, null)` clears it;
  - with a hold set, `el.lastChild` is the hold node, not the tail text node. This is deliberate and pinned by a new test;
  - with no hold, the DOM is byte-identical to today: `tailNode.nodeValue` is assigned only through one `syncTail()`, and `tail()` stays `finalized ? '' : logical`;
  - the existing message contract tests (`test_ui_message_contract.py:233-307`) pass unchanged.

**Chat wiring (transcript.js)**
- [ ] AC5. `mdOpts()` adds `codeBlockRenderers: {chart: …}`, calling `App.ui.chart.block(source, {closed: meta.closed, testid: 'chat-chart'})`. History replies (`addMsg`), committed stream prefixes and finalize all draw charts. A reply with two charts draws both.
- [ ] AC6. **Parser-confirmed boundaries.** `findSafeRenderBoundary` is replaced by a scanner that proposes candidates of three kinds:
  1. a blank line outside a fence;
  2. the end of a **newline-terminated** top-level (column-0) closing-fence line. A streamed ```` ``` ```` with no newline yet can still become ```` ```python ```` and stop being a closer (`markdown.js:177`), so it is never a candidate until its newline arrives. A close that is the last characters of the stream is handled by finalize, never by this candidate;
  3. the start of a complete (newline-terminated) top-level ```` ```chart ```` opener line, where top-level means column 0, as the parser requires for top-level openers (`markdown.js:170`).

  The scanner's nested opener stays permissive (`^\s*```` after optional indentation). Its closer regex is exactly `^\s{0,n}```\s*$`, where n is the opener's indent: it never matches a line with an info string, so ```` ```python ```` inside an open fence is content, as for the parser (`markdown.js:176`). Do not reuse the old `indexOf('```') === 0` toggle (`transcript.js:252`). The scanner and the parser can disagree about nested fences (the cycle-2 case); **parse confirmation is the authority**.

  **Known limit, accepted:** after a nested fence the parser leaves unclosed (`closed === false`), every later candidate prefix is rejected, so the rest of that reply is held until finalize. Record this in the `agents.md` section.

  The furthest candidate is accepted only when `App.markdown.parse(prefix)` contains no CODE_BLOCK with `meta.closed === false` at any depth. Otherwise at most the next two candidates are tried, then none.

  **The cache, so the cost stays linear:**
  - It maps candidate offset → verdict (accepted or rejected) within the current committed generation. An accepted candidate whose commit was an empty fragment (a whitespace prefix) is cached too, so it is never re-parsed.
  - A kind-3 candidate at offset 0 has an empty prefix and is accepted with no parse.
  - **Poisoned prefix:** once a rejection is caused by an unclosed CODE_BLOCK that starts before offset X, every later candidate in the same generation is rejected without a parse, because its prefix contains the same block.
  - The cache resets on every successful (non-empty) `commit`, on `resetStream` and on finalize.
  - **Perf tests** spy on `App.markdown.parse`. One streams a long reply with many blank lines after the cycle-2 disagreement (a nested fence the parser leaves unclosed) and asserts the parse count stays bounded, with no growth per tick and at most a few calls in all after the poisoning. A second streams one long unclosed top-level fence and asserts no parses (no candidates).
- [ ] AC7. **Placeholder lifecycle.** A placeholder is raised **only after a kind-3 candidate at that opener has been accepted** (its prefix parse was clean), so it never sits on text the parser treats as code. Its offset is wherever the opener lies in the tail after that commit: 0, or more when the commit returned early on an empty fragment such as whitespace. After each commit attempt, if the tail continues an open top-level chart block raised this way (waiting for the opener's newline, so ```` ```charts ```` never matches), transcript.js:
  - creates one `App.ui.chart.placeholder({type: null, testid: 'chat-chart-placeholder'})` per open block and calls `streamMsg.setTailHold(offset, placeholder.el)`;
  - on each pacing tick calls `placeholder.setSource(tail.slice(offset))`, and `setType(t)` once `^\s*\{\s*"type"\s*:\s*"(bar|line|area|scatter|pie|sparkline)"` matches the block body after the opener line.

  It destroys the placeholder (calling `placeholder.destroy()` and nulling `chartHold`) in three places:
  - when a commit consumes past the hold;
  - in `finalizeStreamingBubble`, before rendering the tail. Every finalize caller goes through that one function (`turn-frames.js:45`, `:89`, `:109`, `:132`, `:170`, `:180`, `:221`; `sign-in.js:276`), so one destroy there covers them all;
  - in `resetStream()` (`transcript.js:137-144`). `resetStream` only nulls `streamMsg`, the DOM wipe comes later in `clearLog`, and `App.ui.message`'s `destroy` (`message.js:141`) does not remove the hold node, so `resetStream` must destroy the placeholder itself.

  `onAssistantChunk` (`:581`) starting a new streaming bubble defensively destroys and nulls any stale `chartHold` (never throws). A chart nested in a list item gets no placeholder and streams raw.

  `setTailHold` is called once when the hold is created. A repeat call with the same node and offset is idempotent: `syncTail` never re-inserts a node already in place, which would restart its CSS animation and dots. Every consumer of the tail reads `tail()` (the logical text), never `tailNode.nodeValue`; the only external callers are `transcript.js:265` and `:310`.
- [ ] AC8. Flow tests (`tests/browser/test_flow_chat_charts.py`, mock provider with `stream_chunks`, `THE_ONE_TEST_NETNS=1`) prove:
  1. **Stream a chart:** text, then a chart whose chunks split mid-opener, mid-`"type"` and mid-closing-fence, then text. Assert:
     - the text before the fence is committed;
     - the placeholder appears with "Rendering chart", then "Rendering line chart";
     - "Show source" holds the partial JSON;
     - no raw ```` ``` ```` or `{"type"` text is visible in the bubble while the placeholder shows;
     - when the closing fence arrives the placeholder is gone and `chat-chart` is present, before the stream ends (the text after the fence still streaming);
     - the final reply holds text, chart, text, in order.
  2. A reply ending with a chart (no text after): the chart is drawn at finalize.
  3. A broken chart: `chat-chart` absent; the danger notice with "Couldn't draw this chart." and the validator sentence; the source under Technical details; the rest of the reply rendered.
  4. A cut-off chart (Stop mid-block, or a stream that ends inside the block) whose JSON is incomplete: the muted "This chart was cut off before it finished." notice (`chat-chart-error`) and no placeholder left behind. A stream that ends without its closing fence but with complete, valid JSON still draws the chart (leg 1's `block` rule, accepted).
  5. Reopening the chat (history replay) draws the same charts, with no placeholder.
  6. Copy reply copies the raw markdown including the ```` ```chart ```` block.
  7. **Fence regression cases:**
     - a numbered step with a nested python block containing a blank line;
     - the design-review cycle-2 case (`"- Step:\n  ```python\n  x = 1\n```\n\nSome text\n\nmore\n```"`);
     - an indented ```` ``` ```` line inside a top-level block;
     - a ```` ```chart ```` line inside an open ```` ``` ```` block (stays code, no placeholder);
     - a chart nested in a list item (raw while streaming, drawn at the end).

     Each renders identically to a non-streamed render of the same text.
     - **Normalized comparison.** Render the reference in the page the same way the streamed path does (`mdOpts()`, into a detached `App.ui.message` body). In both trees, replace each `[data-testid="chat-chart"]` subtree with a stub carrying only its chart type and its data-table text (leg 2 may add a `data-chart-type` attribute to the chart root in `chart.js` for this). Strip `id`, `for`, `aria-labelledby`, `aria-describedby` and `style`, then compare `innerHTML`. Assert the chart count and order separately.
     - The cycle-2 case must also end correctly committed, or at worst held until finalize, with no split block.
     - Negative cases: a ```` ```charts ```` opener (a code block, no placeholder) and a chart fence quoted inside blockquote text.
     - Kind-3 split cases: a chart opener directly after a list item, after a blockquote and after a table, each with no blank line between. Each is compared to the non-streamed render.
  - In 1., the closing-fence chunk carries its newline or the following text (`"```\n…"`). A bare final ```` ``` ```` is finalize-only (case 2).
  8. A theme switch with a chart on screen keeps the chart's series painted from the new theme's tokens.
- [ ] AC9. The chart table inside a real reply is styled by its own classes, not the bubble's markdown table rules (`css/components.css:2906-2909`): one assertion on the computed style of a header cell.
- [ ] AC10. Scroll: when the transcript is pinned to the bottom, it stays pinned after a chart replaces the placeholder and after the chart's first layout. It is never forced down when the reader has scrolled up.
  - `scrollToBottomIfPinned` (`transcript.js:42`) measures *after* growth, so a chart that adds more than 80 px would read as "not pinned". Sample the pinned state **before** a commit that swaps the placeholder, and scroll if it was pinned.
  - For later layout: transcript.js keeps a `pinned` flag, set when content is inserted while pinned and cleared by a user scroll away from the bottom. The `onLayout` callback scrolls only if the flag is set, without re-measuring.
  - `onLayout` is a new callback option on `App.ui.chart` / `block`. It fires after the first layout and on width changes, through the chart's own `ResizeObserver` (`chart.js:1341`), not a second observer. It is a no-op once the figure is detached. A sparkline has no observer (`chart.js:1340`), so `onLayout` fires once after it attaches.
  - A flow test starts pinned and streams a chart taller than 80 px, and the transcript ends at the bottom.
  - `data-chart-type` on the chart root (used by the AC8.7 normalization) is documented in the `App.ui.chart` catalogue row as a stable attribute.
- [ ] AC11. Docs: `the_one/agents.md` gains "Charts in chat" (the option, the hold, the boundary rules, the placeholder lifecycle, the testids). The `App.ui.message` catalogue row mentions `setTailHold`. CLAUDE.md's transcript paragraph gets one sentence.
- [ ] AC12. Gate:
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes.
  - `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1` lanes `chats-transcript`, `chats` and `contracts-chat` pass, plus `tests/browser/test_markdown.py` and `test_flow_streaming.py` / `test_flow_markdown_chat.py` wherever their lanes put them.
  - The static guards pass, and `ruff` is clean.
  - `chats-transcript`'s wall time is checked against its 390 s budget and re-budgeted (measured + 25%, rounded up to 30 s) if a solo-lane reading shows it over. The flight's closing gate takes the quiet-host reading.

## Verification Steps
- AC1-AC3: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_markdown.py -m browser -x --timeout 60`.
- AC4: `THE_ONE_REQUIRE_WEBKIT=1 THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_ui_message_contract.py -m browser -x --timeout 60`.
- AC5-AC10: the same with `tests/browser/test_flow_chat_charts.py`.
- AC11: read the docs.
- AC12: the lane commands, with `PARALLEL`-free single-lane runs: `--lane chats-transcript`, `--lane chats`, `--lane contracts-chat`.

## Implementation Guidance

1. **markdown.js.**
   - Record `closed` in the fence branch: `var closed = i < endIdx;` before the skip at `:182`, and `meta: {lang: lang, closed: closed}`.
   - In `renderCodeBlock`, before building the well, if `renderOptions && renderOptions.codeBlockRenderers && node.meta.lang` and the map has an own property for that lang, call it inside try/catch. If it returns a Node (`nodeType`), return that. Otherwise fall through.
   - In `render`, `var prev = renderOptions; renderOptions = options || null; try {...} finally { renderOptions = prev; }`.

2. **message.js.**
   - Keep a closure `logical` string and `holdOffset`/`holdNode`. `appendText` appends to `logical`.
   - Write the visible part with a `syncTail()` helper: `tailNode.nodeValue = holdNode ? logical.slice(0, holdOffset) : logical`, inserting `holdNode` right after `tailNode` when set.
   - `commit` slices `logical`, shifts or clears the hold per AC4, then syncs.
   - `finalize` clears the hold (removing `holdNode` from the bubble) before its current steps.
   - `tail()` returns `logical`.

3. **transcript.js.**
   - **Scanner.** Write `scanTail(text)`: one pass over lines, tracking fence state (opener indent, top-level or not), collecting candidate offsets of the three kinds, and noting whether the tail ends inside an open top-level chart block (and its opener offset).
   - **Commit.** `commitSafeBoundary` takes the furthest candidate whose prefix parse has no unclosed CODE_BLOCK (a small recursive walk over `ast.children`), trying at most three candidates and using the AC6 per-generation cache of rejected offsets, then commits.
   - **Hold.** Then handle the placeholder per AC7. Keep `chartHold = {placeholder, offset}` in the transcript closure. After a commit, if `consumed > chartHold.offset`, destroy and null it; otherwise shift its offset.
   - **Finalize.** In `finalizeStreamingBubble`, destroy any `chartHold` before rendering the tail.
   - **Reset.** In `resetStream`, destroy it.

4. **Flow tests.**
   - Configure the mock provider through the existing seeding helpers (pattern: `tests/browser/test_flow_streaming.py:31-40`, `response.content` plus `stream_chunks`) and drive chats through `tests/browser/_chats.py`.
   - `stream_chunks` is a list of literal strings with `delay_ms` between them (`the_one/llm/mock.py:43-44`, `:95-97`). The browser's 16 ms pacing drains each chunk quickly, so use `delay_ms` ≥ 400 to hold the placeholder state observable. Write chunk lists explicitly, so the opener, `"type"` and the closing fence fall in separate entries.
   - **Stop mid-block:** wait for `chat-chart-placeholder`, click `chat-stop-btn` (pattern `tests/browser/test_flow_chat_queued_render.py:233`), and assert the muted `chat-chart-error`. Split the JSON so the cut falls mid-string.
   - **"Valid JSON, no closing fence":** end the chunk list there.
   - Use the leg 1 corpus files as chart bodies, so the test data stays valid.
   - Add the file to `chats_transcript_pat` (`scripts/run-tests.sh:190`).

## Edge Cases
- **A chart opener on the very first line of a reply:** prefix empty, so commit is a no-op and the hold offset is 0.
- **Two charts back to back with no text between them:** the second opener is a new block and gets a new placeholder after the first is committed.
- **A chart whose closing fence is the last characters of the stream (no newline):** it is never a stream commit candidate (AC6 kind 2 needs the newline). Finalize renders it, and since `^```\s*$` matches the last line without a newline, `closed` is true and the chart draws.
- **Indented ```` ```chart ```` inside a list:** no placeholder; raw text; drawn at commit or finalize.
- **The operator switches conversation mid-chart:** `resetStream` destroys the placeholder, with no interval left (leg 1's dots stop rules).
- **A Stop while the placeholder shows:** finalize renders the cut-off notice.
- **Very long JSON in "Show source":** the code well handles overflow (leg 1).
- **`pendingChars` drained at finalize:** the hold logic must not run after `streamMsg` is nulled.

## Files Affected
- `the_one/interfaces/web/static/js/markdown.js`
- `the_one/interfaces/web/static/js/ui/message.js`
- `the_one/interfaces/web/static/js/areas/chat/transcript.js`
- `tests/browser/test_markdown.py` (three `meta` pins gain `closed`, plus new tests), `tests/browser/test_ui_message_contract.py` (new hold tests only), `tests/browser/test_flow_chat_charts.py` (new)
- `the_one/interfaces/web/static/js/ui/chart.js` (small: the `onLayout` option and an optional `data-chart-type` on the root), `tests/browser/test_ui_chart_contract.py` (a test for `onLayout`)
- `scripts/run-tests.sh` (`chats_transcript_pat`, maybe a budget)
- `docs/ui-control-inventory.md` (the Message row), `the_one/agents.md`, `CLAUDE.md`
- The flight log

## Citation Audit
Verified at `293a81d2` by the Flight Director at leg design. Re-check `markdown.js` and `message.js` after leg 1 lands (leg 1 should not touch them; confirm with `git diff`).
- `js/areas/chat/transcript.js:53` — `function mdOpts() { return { copyLiveEl: ctx.copyLiveEl }; }` - verified
- `js/areas/chat/transcript.js:74` — `body: role === 'assistant' ? App.markdown.render(text, mdOpts()) : null` - verified
- `js/areas/chat/transcript.js:127-144` — `clearLog()` calls `resetStream()`; `resetStream` stops pacing and nulls `streamMsg`/`streamSource` - verified
- `js/areas/chat/transcript.js:244-258` — `findSafeRenderBoundary`: `line.replace(/^\s+/, '').indexOf('```') === 0` toggles `inFence`; blank-line boundary - verified
- `js/areas/chat/transcript.js:263-270` — `commitSafeBoundary` renders the prefix and calls `streamMsg.commit(frag, prefix.length)` - verified
- `js/areas/chat/transcript.js:272-280` — `pacingTick`: `appendText`, `commitSafeBoundary`, `scrollToBottomIfPinned` - verified
- `js/areas/chat/transcript.js:301-313` — `finalizeStreamingBubble`: drain, null the stream, `bubble.finalize(render(tail))`, `attr.setCopy(source)` - verified
- `js/areas/chat/transcript.js:581-610` — `onAssistantChunk` creates the streaming `App.ui.message`, appends to `streamSource` and `pendingChars` - verified
- `js/ui/message.js:116-142` — tail text node; `appendText`; `commit` early-returns on an empty fragment, then `insertBefore` and `slice(consumed)`; `finalize`; `tail()` - verified
- `js/markdown.js:169-188` — fence parse; `if (i < endIdx) i++` skips the close; node `{type, meta: {lang}, value}` - verified
- `js/markdown.js:962-976` — `renderOptions` module variable; `finally { renderOptions = null; }` - verified
- `tests/browser/test_ui_message_contract.py:233-300` — streaming tail/commit/finalize pins - verified
- `tests/browser/test_flow_streaming.py:31-40` — mock `stream_chunks` seeding pattern - verified
- `scripts/run-tests.sh:190` — `chats_transcript_pat` explicit list - verified
- `css/components.css:2906-2909` — bubble table rules - verified (Architect)
