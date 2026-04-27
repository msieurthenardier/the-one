# Leg: 05-markdown-streaming-integration

**Status**: completed
**Flight**: [Chat Restructure — Components, Streaming & Markdown](../flight.md)

## Objective

Wire `App.markdown.render(...)` into the chat rendering path so assistant messages render as markdown. During streaming, the accumulated bubble keeps `textContent` semantics (per the streaming-rendering correctness contract); on the `done` event, swap the bubble's contents for the markdown-rendered version. Apply the same markdown rendering to non-streamed `assistant` events (direct-action shortcut path) and to session-rejoined historical assistant messages. User, tool, and system messages stay `textContent` (no markdown). This closes the F4 chat-rendering arc started in leg 03 (markdown library) and leg 04 (streaming infrastructure with option-B chunk rendering).

## Context

- F4 design decision (flight.md "Design Decisions"): markdown rendering is **assistant-only**. User messages, tool messages, and system messages stay `textContent`.
- F4 design decision: **streaming-during-markdown** = append `textContent` during stream; swap to markdown render on `done`. Mid-stream markdown rendering is fundamentally underdefined (partial syntax has no canonical semantics — `**bold` mid-token has no end). The leg uses the simplest correct approach.
- Leg 03 shipped `App.markdown.parse / render / NodeType` at `static/js/markdown.js`. Renderer constructs DOM via `document.createElement` + `textContent` — no `innerHTML`. Returns a `DocumentFragment`.
- Leg 04 pulled chunk rendering forward (option B): `currentStreamingMsg` holds the streaming bubble; per-chunk handler appends to its text node; `tool_call` / `tool_result` / `assistant` (direct-action) / `done` reset `currentStreamingMsg = null`. The bubble is created via `App.chat.renderMessage('assistant', '', { renderMarkdown: false })` — `renderMarkdown: false` forces textContent during accumulation.
- Leg 04's `App.chat.renderMessage(cls, text, opts)` currently ignores `opts.renderMarkdown` — every call returns a plain `<div>` with `textContent = text`. This leg wires the option into actual behaviour.
- Leg 04's chat.js has `addMsg` / `renderMessage` / `addMsg`-via-`renderHistory` paths that all currently pass through `textContent`. This leg flips assistant messages to markdown rendering DEFAULT (no opt-in needed — opt-OUT for the streaming-accumulation case via `renderMarkdown: false`).
- Persistence contract from leg 04: the synthesized assistant Message is added to session history server-side via `session.add_event(...)`. On session-rejoin, history is sent in `session_joined.history` and `renderHistory` walks it. **The assistant entries in history must render as markdown** so a rejoined session shows the same markdown-rendered text as the live session did pre-refresh. This is part of the F4 design's "streaming + markdown integration" goal.
- All F1-F3 + F4 legs 01-04 tests pass: 407 unit + 119 browser (32 baseline + 85 markdown + 2 streaming).

## Inputs

- `static/js/markdown.js` (post-leg-03; ~733 LOC) — `App.markdown.parse / render / NodeType`. `App.markdown.render(text)` returns a `DocumentFragment`.
- `static/js/areas/chat.js` (post-leg-04, ~448 LOC) — has `currentStreamingMsg` closure variable, the `assistant_chunk` accumulator, and the existing `addMsg` / `renderHistory` paths. The `assistant_chunk` handler creates the bubble via `App.chat.renderMessage('assistant', '', { renderMarkdown: false })`.
- `static/js/areas/chat/message-bubble.js` (post-leg-04, 27 LOC) — has `App.chat.renderMessage(cls, text, opts)` that currently ignores `opts.renderMarkdown` and always uses `textContent = text`.
- `tests/browser/test_flow_streaming.py` (post-leg-04, 2 cases) — exercises chunk arrival + final accumulated text in the DOM. Leg 05 extends with markdown-on-done assertions.
- `tests/browser/test_markdown.py` (post-leg-03, 85 cases) — exercises `App.markdown.parse / render` directly. Leg 05 doesn't add cases here; this leg's tests live in `test_flow_streaming.py` and a new `test_flow_markdown_chat.py` (or extend an existing flow file).

## Outputs

### `static/js/areas/chat/message-bubble.js`

- Update `renderMessage(cls, text, opts)` so assistant messages render via markdown by default; user/tool/system stay `textContent`. Concrete logic:
  ```js
  function shouldRenderAsMarkdown(cls, opts) {
    var firstToken = cls.split(' ')[0];
    return firstToken === 'assistant' && (!opts || opts.renderMarkdown !== false);
  }

  function renderMessage(cls, text, opts) {
    opts = opts || {};
    var el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.setAttribute('data-testid', 'message');
    if (shouldRenderAsMarkdown(cls, opts)) {
      el.appendChild(App.markdown.render(text));
    } else {
      el.textContent = text;
    }
    return el;
  }
  ```
- The cls detection uses `cls.split(' ')[0] === 'assistant'` (first-token whitespace split) — matches `'assistant'` exactly without accidentally matching hypothetical `'assistant-error'` or other dash-prefixed variants. The current cls strings in use are `'user'`, `'user api'`, `'assistant'`, `'tool'`, `'tool error'`, `'system'` (audited at chat.js:181-188, 226, 289, 292, 380, 389, 406, 413, 418); only the bare `'assistant'` triggers markdown rendering. The thinking indicator uses `'assistant model-loading thinking'` but is created via `App.chat.createThinking()`, NOT via `renderMessage`, so it doesn't reach this path.
- Document in agents.md: assistant messages render markdown by default; pass `{ renderMarkdown: false }` to force textContent (used during streaming accumulation).
- File grows from 27 → ~36 LOC.

### `static/js/areas/chat.js`

- Add a `finalizeStreamingBubble()` helper that swaps the streaming bubble's accumulated text for the markdown-rendered fragment. Idempotent — no-op if `currentStreamingMsg` is null. Use `textContent` rather than `firstChild.nodeValue` to extract the accumulated text — `textContent` is robust against future structural changes (e.g., if the bubble ever gains additional children, `firstChild.nodeValue` would silently truncate; `textContent` walks all descendants):
  ```js
  function finalizeStreamingBubble() {
    if (!currentStreamingMsg) return;
    var accumulated = currentStreamingMsg.textContent || '';
    while (currentStreamingMsg.firstChild) currentStreamingMsg.removeChild(currentStreamingMsg.firstChild);
    currentStreamingMsg.appendChild(App.markdown.render(accumulated));
    currentStreamingMsg = null;
  }
  ```
- Replace ALL four sites that currently do `currentStreamingMsg = null;` with `finalizeStreamingBubble();`. Use the function uniformly at every reset site for symmetry — the function's idempotent no-op behaviour handles the direct-action path (where `currentStreamingMsg` is null) safely, and uniform usage simplifies the verification grep:
  - `tool_call` handler (chat.js ~line 412)
  - `tool_result` handler (chat.js ~line 417)
  - `assistant` handler (direct-action path, chat.js ~line 405) — uniform call to `finalizeStreamingBubble()` (no-op when null)
  - `done` handler (chat.js ~line 426)

  Concretely: at the four reset sites, replace `currentStreamingMsg = null;` with `finalizeStreamingBubble();`. The function handles the no-op case and the streaming-active case uniformly.
- The `assistant_chunk` handler is unchanged: still creates the bubble via `App.chat.renderMessage('assistant', '', { renderMarkdown: false })` (the opt-out keeps textContent semantics during accumulation).
- The `assistant` handler (direct-action shortcut path) — currently calls `addMsg('assistant', data.content, currentAgentName || 'agent')`. After leg 05's `renderMessage` update, this path AUTOMATICALLY renders via markdown (assistant default). No code change needed in the handler itself — the leg gets markdown rendering "for free" via the `renderMessage` change.
- The `addMsg` orchestrator function in chat.js (~line 84) — currently `messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));`. This is unchanged; the markdown rendering happens inside `renderMessage` based on cls.
- The `renderHistory` function — currently `addMsg('assistant', ev.content, agentLabel);` for assistant events. After the `renderMessage` change, historical assistant messages render via markdown automatically. No code change in renderHistory.
- File grows by ~10-12 LOC (the new `finalizeStreamingBubble` helper).

### `static/css/chat.css`

- Add minimal block-element resets so markdown's structural elements don't introduce browser-default top/bottom margins inside assistant message bubbles. Without this, every paragraph response gains ~16 px of extra vertical margin from the default `<p>` styling, which would visibly shift bubble heights and break visual snapshot baselines unnecessarily:
  ```css
  /* Markdown rendering inside assistant bubbles — strip default block-level margins */
  .area-chat .msg.assistant > :first-child { margin-top: 0; }
  .area-chat .msg.assistant > :last-child { margin-bottom: 0; }
  .area-chat .msg.assistant p { margin: 0.5em 0; }
  .area-chat .msg.assistant ul,
  .area-chat .msg.assistant ol { margin: 0.5em 0; padding-left: 1.5em; }
  .area-chat .msg.assistant pre { margin: 0.5em 0; }
  .area-chat .msg.assistant blockquote { margin: 0.5em 0; padding-left: 1em; border-left: 3px solid var(--color-border); }
  ```
- The reset is scoped under `.area-chat .msg.assistant` so it doesn't affect other markdown surfaces (e.g., the agent profile page if any uses `.markdown-content`).
- File grows by ~8 LOC.
- **Visual snapshot impact**: `tests/browser/test_visual_snapshots.py::test_snapshot_chat_with_messages` baselines will shift slightly even with the resets (markdown rendering changes paragraph spacing semantics from a single text node to a `<p>` element with `0.5em` margins). Per project convention, snapshots are gitignored — each developer regenerates locally with `pytest --snapshot-update -m pixel`. Document in flight log.

### `tests/browser/test_flow_streaming.py`

- Update the existing 2 cases to add markdown-on-done assertions. After streaming completes, verify the assistant bubble's DOM structure includes the markdown-rendered HTML (e.g., `<strong>` tag if the test input had `**bold**`).
- Concrete extension example (one option — designer's choice between extending existing cases vs adding new ones):
  ```python
  @pytest.mark.browser
  def test_streaming_with_markdown_renders_on_done(app_with_provider, page):
      """Assistant message with **bold** in stream_chunks renders as <strong> on done."""
      # Seed agent with mock provider configured stream_chunks=["Hello, ", "**world**", "!"]
      # ... seeder setup ...
      page.goto(app_with_provider.base_url)
      # ... start session, send message ...
      
      # During streaming: bubble text accumulates as plain text (no <strong>)
      bubble = page.locator('[data-testid="message"].assistant').last
      # On done, the bubble's innerHTML should contain <strong>world</strong>
      expect(bubble.locator('strong')).to_have_text('world', timeout=5000)
      # And NO raw asterisks should be in the visible text
      expect(bubble).not_to_contain_text('**')
  ```
- Add a NEW case asserting `**bold**` in a USER message renders LITERALLY (textContent — no `<strong>` tag).
- Add a NEW case for code-block rendering: stream `"```js\\nconsole.log(1);\\n```"` and assert the rendered DOM contains a `<pre><code class="language-js">` element AND a `.markdown-copy-btn` (the copy affordance from leg 03).
- Add a NEW case for session-rejoin: send a streaming message with markdown content; refresh / rejoin; assert the historical assistant message renders via markdown (the `<strong>` etc. are present in the rendered DOM).

Total new browser tests: ~3-4 (depending on whether existing cases are extended or kept as-is).

### `tests/browser/test_flow_markdown_chat.py` (NEW — optional split file)

If the `test_flow_streaming.py` extensions feel cluttered, split markdown-chat-integration tests into a dedicated file. Otherwise, keep them in `test_flow_streaming.py`. **Designer's call** — implementation can pick.

### `the_one/agents.md`

- Update the existing "Markdown rendering" section (added in leg 03) with a sub-paragraph documenting the chat integration:
  - Assistant messages render via markdown by default in `App.chat.renderMessage(cls, text, opts)`.
  - Pass `{ renderMarkdown: false }` to force textContent (used during streaming accumulation).
  - The `done` event triggers `finalizeStreamingBubble()` which swaps the accumulated text for the markdown-rendered DocumentFragment.
  - User / tool / system messages stay `textContent` — markdown is assistant-only.
- Update the "Streaming protocol" section's "chat.js wire-up" paragraph (currently says "Markdown rendering on `done` is leg-05 scope") to past tense — describe the wire-up as DONE: `finalizeStreamingBubble()` swaps the textContent buffer for a markdown DocumentFragment on `done` (and on every streaming-bubble reset boundary).

### `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md`

- Append a `### markdown-streaming-integration` block under `## Leg Progress` summarising file deltas, test counts, and any deviations.

## Acceptance Criteria

- [x] `App.chat.renderMessage` renders assistant messages via `App.markdown.render(...)` by default (no opt-in needed). Passing `{ renderMarkdown: false }` forces textContent.
- [x] User, tool, system messages continue to render via textContent (no markdown). Verified by a test that asserts `**bold**` in a user message renders LITERALLY.
- [x] Streaming bubble accumulates as plain text during chunk arrival (no markdown rendering mid-stream). Verified by inspecting DOM mid-stream.
- [x] On `done` (or any streaming-bubble reset boundary — `tool_call`, `tool_result`), the streaming bubble's content swaps to the markdown-rendered DocumentFragment. Verified by asserting `<strong>` / `<em>` / `<pre><code>` etc. in the post-done DOM.
- [x] `finalizeStreamingBubble()` is idempotent — calling it when `currentStreamingMsg` is null is a safe no-op.
- [x] Session-rejoin renders historical assistant messages via markdown. Verified by a browser test that streams a markdown response, refreshes/rejoins, and asserts the rendered DOM still has the markdown structure.
- [x] Code blocks in streamed messages render as `<pre><code>` with the leg-03 copy-button affordance after `done`.
- [x] All existing 117 browser tests + 2 streaming tests still pass. The new tests in this leg are net additions. (`test_visual_snapshots.py` runs under `-m pixel` not `-m browser`, so visual baseline shifts do not affect this assertion.)
- [x] `pytest --timeout=60 tests/` passes 407/407 (no unit-test changes — leg 05 is purely client-side).
- [x] `pytest --timeout=120 -m browser tests/browser/` passes (119 + N)/(119 + N) where N is the count of new tests in this leg (target: 3-4).
- [x] CSS block-element resets for `.area-chat .msg.assistant` are added (paragraph margins, list margins, pre/blockquote margins) so default `<p>` / `<ul>` / `<pre>` / `<blockquote>` margins don't disrupt bubble spacing.
- [x] `the_one/agents.md` Markdown rendering section updated with the chat integration sub-paragraph; Streaming protocol cross-reference updated to past tense.
- [x] `finalizeStreamingBubble` extracts accumulated text via `currentStreamingMsg.textContent` (NOT `firstChild.nodeValue`) so the algorithm is robust to future structural changes.
- [x] All four `currentStreamingMsg = null;` reset SITES in chat.js are replaced with `finalizeStreamingBubble();` for symmetry. Bare `currentStreamingMsg = null;` does not appear at any reset site (the variable declaration at chat.js:209 is unaffected).
- [x] `shouldRenderAsMarkdown(cls, opts)` uses first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) to avoid matching hypothetical dash-prefixed variants like `'assistant-error'`.
- [x] No new external dependencies; no new files outside the test directory (unless the designer splits markdown-chat tests into a new file).

## Verification Steps

- `grep -cE 'finalizeStreamingBubble' static/js/areas/chat.js` returns exactly **5** (1 function definition + 4 call sites: `tool_call`, `tool_result`, `assistant` direct-action, `done`). Use of the helper at all four sites is required for symmetry — bare `currentStreamingMsg = null` should not remain at any reset SITE in chat.js.
- `grep -cE '^\s*currentStreamingMsg = null' static/js/areas/chat.js` returns **0** (all four bare reset SITES replaced with `finalizeStreamingBubble()` calls). The leading-whitespace anchor excludes the variable declaration `var currentStreamingMsg = null;` at chat.js:209, which is left intact (the closure variable still needs a default value; rewriting it to `var currentStreamingMsg;` would also work since `undefined` is falsy under `if (!currentStreamingMsg)`, but is unnecessary).
- `grep -cE 'currentStreamingMsg = null' static/js/areas/chat.js` (loose pattern, no anchor) returns **1** (the declaration line at chat.js:209). Today this loose pattern returns **5** (1 declaration + 4 reset sites); post-leg it returns **1** (declaration only).
- `grep -cE 'App\.markdown\.render' static/js/areas/chat/message-bubble.js` returns **1** (the assistant rendering path inside `renderMessage`).
- `grep -cE 'App\.markdown\.render' static/js/areas/chat.js` returns **1** (inside `finalizeStreamingBubble`).
- `grep -cE '\.area-chat \.msg\.assistant' static/css/chat.css` returns **≥6** (the new block-element resets).
- Tests: `pytest --timeout=120 -m browser tests/browser/` passes; new test count documented in flight log. Note that `test_visual_snapshots.py` runs under `-m pixel`, NOT `-m browser`, so visual baseline shifts do not affect this assertion.
- Manual smoke (Flight Director or human): send a streaming message containing `**bold**`, headings, code blocks, lists; observe chunk-by-chunk plain text during stream; on `done`, observe the swap to fully-rendered markdown including code-block copy buttons (visible on hover).

## Implementation Guidance

### 1. Update `renderMessage`

In `static/js/areas/chat/message-bubble.js`:

```js
function shouldRenderAsMarkdown(cls, opts) {
  // First-token whitespace split — matches 'assistant' exactly, not 'assistant-error'.
  var firstToken = cls.split(' ')[0];
  return firstToken === 'assistant' && (!opts || opts.renderMarkdown !== false);
}

function renderMessage(cls, text, opts) {
  opts = opts || {};
  var el = document.createElement('div');
  el.className = 'msg ' + cls;
  el.setAttribute('data-testid', 'message');
  if (shouldRenderAsMarkdown(cls, opts)) {
    el.appendChild(App.markdown.render(text));
  } else {
    el.textContent = text;
  }
  return el;
}
```

Update (or remove) the leg-03 comment about `opts.renderMarkdown` being "reserved for leg 05" to reflect the current behaviour.

### 2. Add `finalizeStreamingBubble` to chat.js

Place the helper near the `currentStreamingMsg` declaration (~line 209 in current chat.js). The function is closure-scoped over `currentStreamingMsg` since it both reads and writes it. Concretely, declare alongside the other closure helpers like `addMsg`, `showThinking`, etc.

Use `textContent` (not `firstChild.nodeValue`) for accumulated-text extraction — `textContent` walks the entire subtree and is robust to future structural changes:

```js
function finalizeStreamingBubble() {
  if (!currentStreamingMsg) return;
  var accumulated = currentStreamingMsg.textContent || '';
  while (currentStreamingMsg.firstChild) currentStreamingMsg.removeChild(currentStreamingMsg.firstChild);
  currentStreamingMsg.appendChild(App.markdown.render(accumulated));
  currentStreamingMsg = null;
}
```

### 3. Replace `currentStreamingMsg = null` reset sites with `finalizeStreamingBubble()`

At ALL 4 reset sites in chat.js's `ws.onmessage` switch — uniform call for symmetry:
- `tool_call` handler (~line 412)
- `tool_result` handler (~line 417)
- `assistant` handler (direct-action, ~line 405) — function is no-op when `currentStreamingMsg` is null, so this is safe
- `done` handler (~line 426)

The change is mechanical: `currentStreamingMsg = null;` → `finalizeStreamingBubble();`. After this change, `grep currentStreamingMsg = null` in chat.js should return ZERO hits (the reassignment to null happens only inside `finalizeStreamingBubble` itself).

### 4. Add CSS block-element resets

In `static/css/chat.css`, add resets so markdown's structural elements don't introduce browser-default margins inside assistant bubbles:

```css
/* Markdown rendering inside assistant bubbles — strip default block-level margins */
.area-chat .msg.assistant > :first-child { margin-top: 0; }
.area-chat .msg.assistant > :last-child { margin-bottom: 0; }
.area-chat .msg.assistant p { margin: 0.5em 0; }
.area-chat .msg.assistant ul,
.area-chat .msg.assistant ol { margin: 0.5em 0; padding-left: 1.5em; }
.area-chat .msg.assistant pre { margin: 0.5em 0; }
.area-chat .msg.assistant blockquote { margin: 0.5em 0; padding-left: 1em; border-left: 3px solid var(--color-border); }
```

The selectors are scoped under `.area-chat .msg.assistant` so they don't affect other markdown surfaces.

### 5. Verify `addMsg` and `renderHistory` automatically pick up markdown rendering

No code changes needed in `addMsg` (chat.js:84) — it already passes `(cls, text, opts)` through to `renderMessage`, which now does the right thing based on `cls`. Same for `renderHistory` — its `addMsg('assistant', ev.content, agentLabel)` calls now render assistant messages via markdown automatically.

### 6. Tests

Three concrete new browser tests (target — adjust as needed). **Recommended split**: put these in a new file `tests/browser/test_flow_markdown_chat.py` rather than extending `test_flow_streaming.py`, which is focused on the chunks-only contract:

#### Test A: Markdown renders on `done` for streaming assistant

```python
@pytest.mark.browser
def test_streaming_assistant_renders_markdown_on_done(app_with_provider, page):
    # Seed agent with mock provider stream_chunks=["Hello, ", "**world**", "!"]
    # Goto base_url, pick agent, send a message
    # Wait for done; assert the bubble has <strong>world</strong>
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator('strong')).to_have_text('world', timeout=5000)
    expect(bubble).not_to_contain_text('**')
```

#### Test B: User message stays literal

The user bubble is created LOCALLY via `addMsg('user', ...)` in chat.js:226 BEFORE the WS round-trip. The server may broadcast a redundant `user` event back (chat.js:378-380) but local-then-server produces the same textContent both times. Use `.first` to assert against the first-rendered bubble (deterministic across local-only vs local+broadcast paths):

```python
@pytest.mark.browser
def test_user_message_renders_textcontent_not_markdown(app_with_agent, page):
    # Send a user message containing "**bold**"
    # Assert the user bubble has visible text "**bold**" (not <strong>bold</strong>)
    user_bubble = page.locator('[data-testid="message"].user').first
    expect(user_bubble).to_have_text('**bold**')
    # Assert no <strong> child element
    expect(user_bubble.locator('strong')).to_have_count(0)
```

#### Test C: Code block renders with copy button

The seeder MUST emit a properly closed fence (final `"```"` chunk) so the rendered DOM contains a complete `<pre><code>` block. The `.markdown-copy-btn` is opacity-controlled (visible only on hover/focus per `components.css`), so use `to_have_count(1)` to assert presence rather than `to_be_visible()` which has CSS-dependent semantics:

```python
@pytest.mark.browser
def test_streaming_assistant_code_block_renders_with_copy_button(app_with_provider, page):
    # Seed agent with mock provider stream_chunks=["```js\\n", "console.log(1);\\n", "```"]
    # Send message; wait for done
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator('pre code.language-js')).to_have_text('console.log(1);\n', timeout=5000)
    expect(bubble.locator('.markdown-copy-btn')).to_have_count(1)
```

#### Test D (optional but recommended): Session rejoin renders markdown

```python
@pytest.mark.browser
def test_session_rejoin_renders_assistant_markdown(app_with_provider, page):
    # 1. Stream a markdown message (mock provider stream_chunks with **bold**)
    # 2. Wait for done
    # 3. Get the session id from the URL (#chat/sessions/abc123)
    # 4. Reload the page (or navigate away and back)
    # 5. Assert the historical assistant bubble has <strong>bold</strong>
    bubble = page.locator('[data-testid="message"].assistant').last
    expect(bubble.locator('strong')).to_have_text('bold', timeout=5000)
```

The session-rejoin test validates the persistence contract: the synthesized assistant event was added to session history server-side (leg 04), and now renders via markdown on rejoin (leg 05).

### 7. Update `the_one/agents.md`

Find the Markdown rendering section (added in leg 03). Add a new sub-paragraph:

```markdown
### Chat integration

`App.chat.renderMessage(cls, text, opts)` renders assistant messages via `App.markdown.render(text)` by default. User, tool, and system messages stay `textContent` (no markdown).

Pass `{ renderMarkdown: false }` to force textContent — used by the streaming-accumulation path so chunk-by-chunk text appends as plain text. On the `done` event, `finalizeStreamingBubble()` swaps the accumulated text for the markdown-rendered DocumentFragment.

The same default applies to historical assistant messages on session-rejoin (`renderHistory` → `addMsg('assistant', ...)` → `renderMessage` → markdown).

Mid-stream markdown rendering is intentionally NOT supported — partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation, then a single swap on `done`.
```

### 8. Run tests

```bash
pytest --timeout=60 tests/                       # 407/407 expected (no unit changes)
pytest --timeout=120 -m browser tests/browser/   # (119 + N)/(119 + N) expected
```

Existing browser tests must continue to pass. The pre-leg-05 chat tests assert `[data-testid="message"].assistant` renders text — after leg 05, this assertion still holds (Playwright's `to_have_text` reads accumulated text content recursively, so `<strong>bold</strong>` reads as "bold"). If a test does a strict-equals assertion on innerHTML, it will need updating — flag any such test.

`test_visual_snapshots.py` runs under `-m pixel`, NOT `-m browser`. Visual baseline shifts from markdown rendering (added `<p>` tags, paragraph margins) are EXPECTED. Per project convention, snapshots are gitignored — each developer regenerates locally with `pytest --snapshot-update -m pixel`. Document the expected visual shift in the flight log.

### 9. Update flight log

Append a `### markdown-streaming-integration` block under `## Leg Progress` summarising file deltas, test counts, deviations.

## Edge Cases

- **`finalizeStreamingBubble` called twice in a row**: idempotent — second call sees `currentStreamingMsg = null` and returns immediately.
- **Empty streaming bubble** (zero chunks emitted before `done`): `currentStreamingMsg` is null (the `assistant_chunk` handler never fired), so `finalizeStreamingBubble` is a no-op. The `done` event fires through normally.
- **Streaming bubble with empty accumulated text** (chunks emitted but content was all empty strings): `currentStreamingMsg.textContent` returns `""`; `App.markdown.render('')` returns an empty DocumentFragment (or a fragment with no meaningful children); the bubble is replaced with empty content. Acceptable — matches the empty-input markdown contract from leg 03. If the leg-03 renderer's empty-input contract changes (e.g., if it returns a single empty `<p>`), the bubble would gain a paragraph element with `0.5em 0` margin, which the new CSS reset suppresses for `:first-child` / `:last-child`.
- **Assistant message with tool_calls but no content**: streaming yielded zero content chunks (no `assistant_chunk` event); the agent's iteration emitted only tool_calls. `currentStreamingMsg` is null; `tool_call` handler's `finalizeStreamingBubble()` is a no-op. Tool message renders via `addMsg('tool', ...)` (textContent). All correct.
- **Direct-action shortcut path**: `assistant` event fires, `addMsg('assistant', text, attribution)` → `renderMessage('assistant', text)` → markdown rendered. No streaming involved. Correct.
- **Session-restore historical assistant message contains a `javascript:` link**: leg 03's renderer applies the href allow-list — `javascript:` is stripped to `#`. Markdown safety holds for restored messages too.
- **`App.markdown.render` on long accumulated text** (e.g., a 10KB streaming response): renderer is O(n); performance is fine. No specific concern.
- **Streaming with no closing fence on a code block** (`"```js\\nconsole.log(1);"` without trailing backticks): leg 03's tokenizer is lenient — treats the rest of the input as code-block content. The rendered bubble shows the code as a code block. Acceptable behaviour.
- **`addMsg('assistant model-loading', ...)` (the rare composite class)**: `cls.indexOf('assistant') === 0` matches; markdown rendering applies. But — wait, the model-loading class is only used by the thinking indicator (created via `App.chat.createThinking()`, not `renderMessage`) AND the `Loading model...` system inline (created via raw DOM in chat.js, not `renderMessage`). So this composite class never reaches `renderMessage`. Safe.
- **Assistant message containing a literal `<` or `>`**: `textContent` and markdown rendering both escape these correctly (markdown via `document.createTextNode`; textContent natively). No XSS risk.
- **CSS resets reaching the thinking indicator**: the thinking-indicator element is created with class `'msg assistant model-loading thinking'` (chat/thinking-indicator.js:13). The new `.area-chat .msg.assistant > :first-child { margin-top: 0 }` resets DO syntactically apply to its inline `<span>` children, but vertical margins on inline elements are no-ops, so the resets are harmless. Documented for future maintainers.

## Files Affected

- `the_one/interfaces/web/static/js/areas/chat/message-bubble.js` — UPDATED (renderMessage now markdown-renders for assistant cls; new `shouldRenderAsMarkdown` helper; ~9 LOC added)
- `the_one/interfaces/web/static/js/areas/chat.js` — UPDATED (new `finalizeStreamingBubble` helper; 4 reset sites updated; ~10-12 LOC added net)
- `the_one/interfaces/web/static/css/chat.css` — UPDATED (block-element resets for markdown-rendered assistant bubbles; ~8 LOC added)
- `tests/browser/test_flow_streaming.py` — UPDATED OR NEW dedicated file `tests/browser/test_flow_markdown_chat.py` (recommended split — keeps streaming tests focused on chunks-only contract); ~3-4 new tests
- `the_one/agents.md` — UPDATED (Markdown rendering "Chat integration" sub-paragraph; "Streaming protocol" cross-reference updated past-tense)
- `missions/04-ui-maturity/flights/04-chat-restructure/flight-log.md` — UPDATED (leg progress entry, including visual-snapshot baseline-shift note)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] `pytest --timeout=60 tests/` passes (407/407 — leg 05 is purely client-side; no unit-test changes expected)
- [x] `pytest --timeout=120 -m browser tests/browser/` passes ((119 + N)/(119 + N) with N documented in flight log)
- [x] All existing 119 browser tests still pass (leg 05's `renderMessage` change does not break the existing assertions because Playwright's text matchers read accumulated text content)
- [x] Update flight-log.md with leg progress entry under `## Leg Progress` (`### markdown-streaming-integration` heading)
- [x] Set this leg's status to `landed` (in this file's header) — DO NOT set to `completed` and DO NOT commit; the flight-level review and commit run after the last autonomous leg per `/agentic-workflow`. **This is the LAST autonomous leg** — leg 06 is the interactive HAT, and the flight-level review + commit run AFTER leg 05 lands and BEFORE leg 06.
- [x] Signal `[HANDOFF:review-needed]`
