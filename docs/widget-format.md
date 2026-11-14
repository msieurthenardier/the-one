# The `widget` block

A `widget` block is a fenced code block with the language `widget` in an assistant reply. Its body
is a small, self-contained web page (HTML with inline style and script). The chat runs it in a
sandboxed frame, as a card headed "Widget by {agent}". This document is the language-neutral
specification of what the block may contain and what the frame does with it. The chart sibling is
[chart-format.md](chart-format.md). The security reasoning is in `SECURITY-MODEL.md` "Live visuals".

## The tag

````
```widget
<div id="out">hello</div>
<script>document.getElementById('out').textContent = 'world';</script>
```
````

- The language is exactly `widget`, case-sensitive. `html`, `javascript` and any other language are
  ordinary code blocks and never run.
- Only an **assistant reply** can carry a widget. A user message, a routine-run message, a tool result
  and a thinking item show the same text as a plain code block.
- A block with an empty or whitespace-only body is a plain code block.
- A block whose closing fence never arrives (the turn was stopped or cut off, or the reply ends inside the fence) is not run. The chat
  shows "This widget was cut off before it finished." with the source under "Widget source", in the reply or, for a stopped turn, in the turn's work group.
- Copy reply copies the raw markdown, widget source included.

## The body

- The body is **HTML**: a fragment (`<div>…</div><script>…</script>`) or a whole document
  (`<!doctype html><html>…`). It is appended after a fixed prelude and policy, so a whole document is
  accepted but cannot change what the frame enforces (a later policy `<meta>` can only tighten it).
- **Inline `<style>` and `<script>` only.** The frame allows `script-src` and `style-src` for inline
  code and `img-src data: blob:`. Everything else is closed: no network (`connect-src 'none'`), no
  remote script, style, font, image or media, no worker, no frame, no form submission, no `<base>`.
- **Size:** at most 64 KiB of UTF-8. A larger body is not run: the chat shows "Couldn't run this
  widget." with the reason and the source.
- **Height:** the card follows the content's height, clamped to 48-720 px (it starts at 240 px). The
  content scrolls inside the frame beyond 720 px.
- The card's title adds the widget's `<title>` text (first 8 KiB scanned, 60 characters) after
  "Widget by {agent}". A title is text, not markup.

## Theme

The frame carries the page's colours as CSS custom properties on its root, and keeps them current:

| Variable | Meaning |
|---|---|
| `--bg`, `--surface` | page and card backgrounds |
| `--fg`, `--fg-muted` | text and secondary text |
| `--border` | hairlines |
| `--accent` | the accent colour |
| `--danger` | the danger colour |
| `--chart-1` ... `--chart-8` | the chart palette (the same colours charts use) |

- The root also carries `data-theme="light"` or `"dark"` and the matching `color-scheme`.
- The frame's own base style sets the background to `--surface` and the text to `--fg`, removes the default `html` and `body` margin, and makes every
  element `box-sizing: border-box` (so a `width: 100%` element with a border or padding fits the
  frame without a scrollbar).
- Scripts run with the frame already laid out: `document.documentElement.clientWidth` and an
  element's `offsetWidth` are the frame's real width at start, so sizing a canvas once from them is safe.
- When the operator switches theme, the variables and `data-theme` are updated in place and the
  frame's `window` receives a **`themechange`** event (`window.addEventListener('themechange', fn)`).
  Read the variables again in the handler; do not cache computed colours.

## Pausing

A card is **paused** by the operator (the Pause button) or automatically (scrolled out of view, tab
hidden, or over the running cap). The frame's prelude gates the widget's clock:

- `requestAnimationFrame` callbacks queue; `setTimeout` and `setInterval` callbacks that fall due are
  deferred until resume; Web Animations and CSS animations are paused; `AudioContext` instances are
  suspended.
- `performance.now()` and the timestamps given to `requestAnimationFrame` subtract the time spent
  paused, so a time-based animation resumes without a jump. `Date.now()` and `new Date()` stay the
  wall clock.

Pause is **cooperative and cannot be enforced**. A widget that busy-loops keeps running. So does one
that schedules work through a path the gate does not wrap: `MessageChannel` loops,
`scheduler.postTask`, `requestIdleCallback`, `element.animate()` started after the pause,
`requestVideoFrameCallback`, `OfflineAudioContext`. Removal is the only real stop: the loaded ceiling
and the hang guard bound such a widget (see Limits).

## Focus

A widget never takes focus from the operator. Inside the frame, `focus()` (on elements and on the
window) runs only while the frame's own user activation is active **and** a trusted gesture happened
inside the frame within about 1 second. `autofocus` is ignored. So a widget may focus an input right
after the user clicks in it, but cannot grab focus on load, on a timer or while the operator types in
the composer.

## `<link>` tags

A `<link>` tag (a stylesheet, a preload, a preconnect or DNS prefetch) can open a connection the
policy cannot always stop, so every link tag is rewritten to an inert **`<x-link>`**, in the source
and in every string the widget turns into markup at run time (`innerHTML`, `outerHTML`,
`insertAdjacentHTML`, `document.write`, `DOMParser`, `Range.createContextualFragment`,
`setHTMLUnsafe`, `createElement('link')` and `createElementNS(…, 'link')`). The rewrite applies even
inside a script string that contains the text `<link`. Use `<style>` for styles.

## Other rules

- **`document.write` after load is a no-op** (before load it works, with its output scanned for link
  tags).
- `document.open` returns the document and does nothing else.
- **Blocked or absent:** network of any kind (fetch, XHR, WebSocket, EventSource, beacon, images,
  CSS `url()` and `@import`, workers, dynamic `import()`); WebRTC (`RTCPeerConnection` is undefined);
  access to the page (`parent.document`, `top.location`); cookies, `localStorage` and
  `sessionStorage`; `window.open`; `alert` and the other modal dialogs; form submission and
  navigation (a second load of the frame removes the card); `history.back`, `go`, `pushState` and
  `replaceState` (no-ops); `document.execCommand` (returns false); downloads and top-level popups.
- **Messages:** the frame's `window` may post messages to its parent, but the page reads only its
  own size message. Anything else is ignored. A flood of size messages is coalesced to one height
  write per animation frame.
- **Origin:** the frame's origin is the string `"null"`.

## Limits

| Limit | Value |
|---|---|
| Body size | 64 KiB (UTF-8) |
| Running at once | 3 widgets (more wait or are paused) |
| Loaded at once | 8 (further widgets stay unloaded until one is released) |
| Height | 48 to 720 px |

A widget runs only while its card is in view and the tab is visible. A card that scrolls out of view
is paused; a paused card stays loaded until the loaded ceiling needs the slot, then it is unloaded
(its slot keeps its height). The **hang guard** stops a loaded widget whose frame stops answering
(no heartbeat for 5 s while the page is responsive), stops every loaded widget when the page itself
stalls for 5 s or more, and, after a page that ended without a normal unload, shows the widgets that
were loaded then as "This widget stopped responding last time." A stopped card offers Start anyway. In some Chromium-based hosts, Start anyway right after a
busy-looping widget was stopped can land in the renderer that is still spinning, leaving the card
blank and the host's own "page not responding" prompt on screen; answer that prompt, or quit and
relaunch the desktop app.

A card's slot is 240 px until its widget first reports a size, so the first scroll through a long
chat may shift the layout once per card that was never loaded. A report of height 0 (sent before the
widget has laid out) is ignored, a stopped or capped card keeps its slot height, and the page
remembers each card's last height (in memory, per card key and slot width) so the same chat shown
again in the same page starts at the real heights.

## Keys

Each card has a key, `{session id}:{hash of the source}:{n}`, where `n` counts the earlier **closed**
widgets with the same source in the same transcript (the second copy of a widget is `…:1`). The
chat exposes it as `data-widget-key`. The hang guard uses it to recognise the same widget after a
reload. A reply that is received live and the same reply opened later get the same keys, because every text is rendered once.

## On chat platforms

A widget cannot run on Discord or Telegram. A top-level ```` ```widget ```` block, closed or not,
is replaced in the sent text by one line, "Interactive widget: open this chat in the app to see
it." Only top-level blocks convert: a widget fence nested in a quote or a list is sent as its
source text (a documented residual). See `the_one/connectors/README.md` "Visuals on platforms".

## Conformance

The frame, the card and the manager are `js/ui/widget-frame.js`, `js/ui/widget.js` and
`js/ui/widget-lifecycle.js`. The escape battery `tests/fixtures/widgets/escape.html` and the contract
files `tests/browser/test_ui_widget_*.py` hold them to this document. The end-to-end boundary check is
the behavior test `tests/behavior/widget-escape.md`.
