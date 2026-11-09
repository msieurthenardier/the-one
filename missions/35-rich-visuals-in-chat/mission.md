# Mission: Rich Visuals in Chat

**Status**: active

## Outcome

An agent can answer with a picture, not only with text. When a chart says it
better than a table, the reply shows a real chart. When an idea is easier to see
moving, the reply runs a small animation or an interactive widget, right in the
chat. The visual appears when it is ready, looks at home in both themes, and is
safe to show even when the model was steered by content it read.

- In the app, a chart in a reply is drawn in place: bar, line, area, scatter,
  pie and sparkline.
- In the app, a live visual (an animation, a small simulation, an interactive
  widget the model wrote) runs inside the reply, walled off from the app.
- On Discord and Telegram, a chart arrives as an image beside the reply's text.
  A live visual cannot run there, so it arrives as a short note that points to
  the app.
- Each agent has a "Rich visuals" switch on its General tab, on by default.

## Context

This mission comes from a sortie that did not qualify. The work failed three of
the sortie's four tests: it has more than one cluster of design decisions (the
chart format and renderer, the sandbox's security boundary, the streaming
display, the toggle and its prompt cost, and server-side images with connector
attachments), it needs more than one flight, and it adds a new security
boundary and changes the contract every connector shares.

Facts about the codebase that shape the design (verified at `293a81d2`; flight
designs re-verify line numbers):

- **The markdown renderer is hand-rolled and builds DOM only.**
  - `static/js/markdown.js` never passes HTML through. A fenced block's first
    info-string token becomes its language if it matches
    `^[A-Za-z0-9_+#.-]{1,32}$` (`:169-176`), and `renderCodeBlock` builds
    `div.markdown-code-wrap > pre > code.language-<lang>` with a copy button
    (`:923-958`).
  - `render(text, options)` takes one option, `copyLiveEl` (`:962-975`). It has
    no hook for swapping a block for a control, so one must be added.
  - An unclosed fence parses leniently, as a code block that runs to the end of
    the input (`:181`).
- **Streaming never re-renders committed text.**
  - A streaming reply appends raw text to a tail node on a 16 ms timer
    (`areas/chat/transcript.js:271-279`).
  - Text up to the last blank line outside a fence is rendered and committed,
    and committed DOM is never rebuilt (`commitSafeBoundary`, `:263-270`;
    `ui/message.js:128-132`). The rest is rendered at finalize
    (`finalizeStreamingBubble`, `:301-313`).
  - An open fence therefore stays raw text in the tail. A block is committed
    only after a blank line that follows its closing fence, or at finalize when
    the reply ends with it, so a "Rendering" label needs its own detection of
    an open visual fence in the raw tail. A visual can be built once, when its
    block is committed, and is never torn down by later chunks. The same block
    is rendered again, whole, when the chat is reopened.
  - The stream's fence detector (`findSafeRenderBoundary`, `:244-258`) accepts
    indented fences; the parser does not. That mismatch matters once a fence
    becomes a control.
- **The "Thinking…" indicator can be reused for "Rendering".** `App.ui.thinking`
  (`ui/thinking.js`) animates braille spinner frames on a 120 ms timer, has a
  static fallback under reduced motion, and takes a free-text label. Its root
  carries the bubble classes, so a "Rendering" label inside a reply needs the
  dots without the bubble.
- **Copy reply copies the raw markdown** (`transcript.js:96`, `:312`). Rendering
  a block does not change what is copied.
- **There is no frame or content-security policy anywhere.** No
  Content-Security-Policy, X-Frame-Options or `<meta http-equiv>` in `the_one/`
  or `index.html`, and no `<iframe>` in `static/`. The only middleware is the
  Origin allowlist and the credential gate (`app.py:778-791`). The main page
  holds the local-API credential, and that credential can run shell commands.
  Every route except `GET /api/live` needs the credential, and a sandboxed frame
  with an opaque origin sends no cookies and an `Origin: null` header, so a
  frame that loads its document from a route conflicts with both gates; a
  `srcdoc` frame avoids them but carries its policy only in a `<meta>` tag.
- **A live visual cannot be paused, only removed.** In WebView2, WebKitGTK and
  WKWebView an opaque-origin `srcdoc` frame is not guaranteed its own process,
  so a runaway script in one can freeze the app's page. The parent cannot
  pause script it does not control; it can only avoid mounting a frame and
  remove one. Messages from an opaque origin arrive with `origin === "null"`,
  so the page must identify a frame by its window, not its origin.
- **There are no chart colours.** `css/tokens.css` has no categorical or series
  palette; the nearest are the provider badge colours, status and accent
  tokens. Token hex values are mirrored in `tests/browser/design_tokens.py` and
  pinned by contrast tests. `App.theme.resolved()` reads `data-theme`; an OS
  theme change in auto mode fires no event (`theme.js:139-143`), so a visual
  that follows the theme must watch the attribute.
- **Per-agent switches have a known path.**
  - `notes_enabled` went in as an `agents` column through a schema step
    (`db/schema.py:3030-3074`), the repository's `save` and read
    (`repositories.py:281-357`, `:542`), and a PUT that keeps the stored value
    when the field is omitted (`api.py:1545-1546`). The schema is at v51.
  - The General tab (`areas/studio/general-tab.js`) has no switch today, and
    the form collector reads `input[data-field]` values as strings
    (`agent-form-data.js:86-110`), so a boolean needs its own branch.
- **The platform prompt already has conditional sections.**
  `platform_prompt.py` declares `Section(id, title, applies_when, applies, text)`
  over a `Capabilities` dataclass (`:30-62`, `:142-181`), and Settings › Prompts
  lists every section with its "Applies when" line. Capabilities are built in
  three places (`agent/factory.py:688-703`, `db/prompt_layers.py:147-155`,
  `self_configuration/pending.py:132-167`). A visuals flag fits there. Platform
  prompt text falls under the eval rule (CLAUDE.md "Prompt evals"), and its
  size gate is "no larger than the baseline", so any added text fails that gate
  by construction and needs a recorded decision.
- **Connectors send text only.**
  - `ConnectorClient` is a structural Protocol with `is_alive()` and
    `send(target, content: str)` (`connectors/base.py:152-165`). Optional
    abilities are found with `getattr` (`history`, Discord's `sever_for_test`).
  - The reply goes out through `delivery.deliver_final_reply`
    (`delivery.py:72-144`), which sends the final assistant text raw and
    changes only its `visibility`. The agent tool `send_to_platform_channel`
    calls `client.send` raw (`tools/connector_send.py:195`). Routine runs reach
    a platform only through that tool. `delivery.py` is the envelope-free
    module both can share.
  - Discord posts JSON to REST v10 with no multipart support
    (`discord/_rest.py:86-127`). Telegram has `sendMessage` only, converts
    markdown to HTML in its own renderer, and sends a fenced block as `<pre>`
    (`telegram/_api.py:61-105`, `_render.py`).
  - No path splits long messages. That stays out of scope.
  - The stored chat keeps the agent's text verbatim (`inbound.py:460-462`), so
    the app's view of a connector chat can still show the real visual, as long
    as any rewriting is done on a copy at send time.
  - The stub connector records `(target, content)` tuples
    (`stub.py:41`, `:53`), read by about 35 tests and
    `GET /api/_test/stub/outbound` (`api.py:5233-5254`). A new record shape must
    not break them.
- **Image drawing on the server needs a dependency move and a font.**
  - Pillow ships in every installer (Linux and Windows build with
    `--extra gui`), but it is only in the `gui` and `dev` extras, not the base
    dependencies (`pyproject.toml:164`, `:169`).
  - The repo has no TrueType fonts. Pillow 13 loads the bundled
    `static/fonts/Geist-VF.woff2` on Linux; Windows and macOS are unchecked.
    All three freeze specs bundle the static tree.

## Success Criteria

- [ ] **Charts appear in the app.** An agent reply can carry a chart (bar,
      line, area, scatter, pie, sparkline) that the chat draws in place, in
      the current theme, following a theme change without a reload. Each chart
      has a text alternative a screen-reader user can read (its title and
      data).
- [ ] **Live visuals run in the app, walled off.** An agent reply can carry a
      live visual (animation or interactive widget) that runs inside the reply.
      It cannot reach the network, read or change anything in the app, use the
      app's credential, open windows or navigate the app. The boundary and its
      remaining risks are written up in the security model.
      *(Behavior-test-backed: the escape attempts are proved against the real
      app.)*
- [ ] **A visual appears when it is ready.** While a visual's block is still
      streaming, the reply shows the raw block under a "Rendering" label with
      the same animated dots as "Thinking…". When the block completes, the
      visual replaces it. A block the app cannot draw shows a plain error with
      the source under "Technical details". Copy reply still copies the
      original text.
- [ ] **Long chats stay responsive.** Reopening a chat with many live visuals
      does not start them all: a live visual starts when it comes into view
      and stops when it leaves (starting again from the beginning when it
      returns), and the number running at once is capped. A visual that hangs
      or runs away is a documented residual risk with a stated limit, not a
      silent one.
- [ ] **Operators choose per agent.** The agent's General tab has a "Rich
      visuals" switch, on for new agents and for agents that already exist.
      When it is on, the agent is told how to write visuals. When it is off,
      the agent is not told, but any visual block in its replies still renders.
- [ ] **The prompt cost is measured and accepted.** The description of the
      formats goes only to agents with the switch on. Its token cost is
      measured, an eval comparison against the current platform baseline shows
      no pass-rate regression, and the size increase is recorded as an
      operator-accepted exception or a new baseline.
- [ ] **Charts reach chat platforms as images.** When a reply with a chart goes
      out through Discord or Telegram (an automatic reply or the agent's own
      send), the chart arrives as an image and the rest of the text arrives as
      before. A live visual arrives as a short note pointing to the app. The
      stored chat is unchanged, so the app shows the real visual.
      *(Behavior-test-backed: a live connector round trip.)*
- [ ] **Chart images work on every install.** Any install of the app, packaged
      or not, can draw chart images, with the same text rendering on Windows,
      Linux and macOS.
- [ ] **Visuals work in the desktop app.** Charts and live visuals render and
      behave the same in the desktop window on each platform as in a browser.

## Stakeholders

- **The operator**, who reads agents' replies in the app and on Discord or
  Telegram, and wants data and ideas shown, not only described.
- **Agents' readers on chat platforms**, who see the replies a connector sends.
- **Small local models**, which must be able to write a chart that renders: the
  format has to be simple enough for them, and the prompt text that explains
  it has to stay cheap.

## Constraints

- **No HTML from model output ever reaches the app's own page.** Model output is
  attacker-influenced (prompt injection through web pages, knowledge bases, MCP
  results and notes). A live visual runs only inside a walled-off frame with an
  opaque origin, no network and no way to navigate the app or open windows: the
  frame's sandbox grants scripts only (no same-origin, popups, top navigation,
  forms or modals), and its content policy comes before any model bytes and
  closes every fetch, image, font, media, frame, form and base-URL path
  explicitly, not through a default alone. Its only channel back to the page
  carries size, nothing else, and the page identifies the sender by its frame
  window. Any route that serves frame content without the credential serves
  fixed content only, never chat or user data.
- **A visual cannot pass for the app.** A live visual can draw anything,
  including a fake sign-in or "paste your key" prompt. It sits inside a visible
  frame marked as made by the agent, so it never looks like the app's own UI.
  The frame and its marking are the whole control: a visual runs and takes
  clicks and typing at once, with no click to activate (operator decision).

Operator decisions taken while planning: Pillow becomes a base dependency; the
"Rich visuals" switch is on by default for new and existing agents, and turning
it off only stops the agent being told about visuals (visual blocks still
render); live visuals start on their own when in view, and stop and restart
from the beginning rather than pause, because pausing cannot be enforced.
- **Ordinary code samples stay code.** A reply that shows HTML source, or JSON,
  must still render as a code block. Visuals use their own block tags that do
  not collide with any language a model would use for a code sample.
- **Offline and dependency-light.** The desktop app works offline, so nothing
  loads from a CDN. The chart control has no third-party JavaScript. Server-side
  chart images use Pillow, which becomes a base dependency (operator decision),
  and the app's own bundled font.
- **One chart format, two renderers.** The app draws charts in the browser and
  the server draws them as images for connectors. The format is defined once,
  in a language-neutral document, with a shared set of sample specs that both
  renderers and both validators are tested against, so the two cannot drift.
- **The stored chat is never rewritten.** Rendering and connector conversion
  work on copies. The stored message is the agent's text, verbatim.
- **Existing project rules apply.** New `App.ui` controls get catalogue rows,
  owned classes and Chromium + WebKit contract tests; no HTML-string sinks; the
  new palette tokens pass the WCAG contrast audit; a schema change is a new
  versioned step; platform prompt text lands with an eval run (CLAUDE.md "Prompt
  evals"); the connector change keeps the structural-Protocol pattern and does
  not break the stub's existing record readers.

## Environment Requirements

- Host-native dev environment with the repo `.venv` (`pip install -e ".[all-llms,dev]"`).
- Playwright Chromium and WebKit (`scripts/setup-webkit-userland.sh`), with
  `THE_ONE_REQUIRE_WEBKIT=1` for the contract lanes and `THE_ONE_TEST_NETNS=1`
  for browser runs on this WSL host.
- The real desktop engines: `scripts/webkitgtk_probe.py` for WebKitGTK,
  `scripts/windows_test_copy.py` for WebView2, and a hosted macOS run for
  WKWebView.
- The prompt evals: `pip install -e ".[evals]"`, the plan token in
  `~/.config/the-one-evals/plan-token`, and a local Ollama with the default
  eval models.
- For the connector flight's live check, the Discord HAT driver bot
  (`tests/behavior/.env.hat`) and a Telegram test bot.

## Open Questions

- What are the block tags? A chart tag (`chart`) and a live-visual tag that
  cannot collide with an ordinary `html` code sample.
- What is the exact chart format, and how far does it go? Axes, labels, units,
  stacked or grouped bars, multiple series, a size limit on data points.
- Do visuals render in the operator's own messages, or only in agent replies?
- How does the sandbox learn the theme, and does a running live visual follow a
  theme change?
- What is the cap on running live visuals, and how does a paused one look?
- How do the text alternatives work: a hidden data table, a visible "Show data"
  disclosure, or both?
- Which theme does a connector's chart image use?
- Where does a live visual's document come from: a `srcdoc` frame with its
  policy in a leading `<meta>` tag, or a fixed, credential-free frame route with
  a real policy header that receives the visual by message? (Decide before
  Flight 2's first leg.)
- What are the limits: data points per chart, bytes per live visual, live
  visuals running at once?
- Does the server draw chart text with the bundled `.woff2`, or with a bundled
  plain TrueType subset (safer across Pillow builds, and simpler for weights)?
  What happens to text the font cannot draw (non-Latin, emoji)?
- Does the stream's fence detector change to match the parser for every fence,
  or only for visual fences?
- How do Discord and Telegram place the image relative to the text (one message
  with an attachment, or the text then the image), and what happens when an
  upload fails (fall back to the text with the block as code)?
- Does the step-limit line or any other system line ever carry a visual? (It
  should not.)

## Known Issues

*(none yet)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [ ] Flight 1: **Charts in chat.** The language-neutral chart format and its
      sample specs, the SVG chart control and its palette tokens, the markdown
      hook that turns a visual block into a control, the streaming "Rendering"
      state and the error notice, the per-agent "Rich visuals" switch (schema,
      API, General tab, on by default), and the platform prompt section with its
      eval comparison as the flight's last implementation leg (its size gate
      fails by construction, so it needs the operator's decision at the end).
- [ ] Flight 2: **Live visuals.** The walled-off frame control: opaque origin,
      no network, size-only messages, the theme passed in, run in view and pause
      out of view, a cap on running visuals, the agent-made frame marking, the
      security model section and the escape behavior test, and checks in the
      three desktop engines. This is the mission's risk seam: its first leg
      proves the frame in all three engines (escape attempts and a runaway
      script) and ends in an explicit go/no-go before the rest is built.
- [ ] Flight 3: **Visuals on chat platforms.** Pillow as a base dependency, the
      server-side chart image renderer tested against the shared sample specs,
      an optional attachment-capable send on the connector contract, Discord
      and Telegram image uploads, the stub record that tests can observe, the
      live-visual note, one shared conversion step for the automatic reply and
      the agent's send tool, and the font check on all three platforms.
- [ ] Flight 4 *(optional)*: **Alignment.** A hands-on session tuning palette,
      sizing, spacing and animation feel with the operator.
