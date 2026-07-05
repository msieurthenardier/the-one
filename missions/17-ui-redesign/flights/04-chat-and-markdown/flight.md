# Flight: Chat Re-skin + Markdown Hardening

**Status**: landed
**Mission**: [UI Redesign — Clean, Professional, Consistent](../../mission.md)

## Contributing to Criteria

> Boxes stay unchecked — these are mission-end criteria, verified at the F7 hardening/verification gate. The annotations below record F4's delivered share toward each.

- [ ] SC1 — visual-language replacement (chat surface to the quiet vocabulary)
  - **F4 share**: the chat surface was re-skinned to the quiet vocabulary — the loud full-`--accent` user bubble retuned to a quiet tint, disclosures/code wells/composer to vocabulary chrome; SC1 spot-check swept the chat surface in both themes (509 elements each) → **0 alien remnants** (no glows/gradients/text-shadows/filters).
- [ ] SC3 — one component vocabulary (chat consumes it — buttons, fields, code wells)
  - **F4 share**: chat consumes the F3 primitives directly — composer input → `.field-input`, stop → `.btn-muted-destructive`, send stays `.btn-filled-primary` (no per-area variants); code well + inline-code pill on the shared quiet code surface.
- [ ] SC4 — modern chat experience (reading layout, streaming + stop, legible markdown/code, tool traces out of the reading flow)
  - **F4 share**: single-column reading layout with refined turn distinction (tinted user block, near-full-width agent prose, content-column max-width), streaming with a first-class stop affordance, legible markdown/code (hardened parser, quiet code well, always-visible-but-quiet copy button), tool-trace + thinking disclosures kept out of the reading flow behind quiet `<details>`.
- [ ] SC5 — keyboard/AT operability (composer, disclosures, stop affordance)
  - **F4 share**: composer/stop/disclosures keyboard-operable — the stop affordance is keyboard-focusable and operable live during streaming (2px accent focus ring, CDP-evidenced); the a11y-reviewer independently drove a real streaming turn confirming a keyboard-operable stop; copy button keyboard-reachable (not hover-reveal-only).

---

## Pre-Flight

### Objective

Re-skin the Chat area to the v3 quiet vocabulary — a focused single-column reading layout with clear user/agent turn distinction, a restyled composer with a first-class stop affordance, streaming with scroll-position awareness, legible markdown/code rendering, and tool-activity/thinking traces that stay out of the reading flow until expanded — AND deliver the mission's markdown-security intent *structurally*: harden the existing hand-rolled `markdown.js`, lock its no-HTML-string invariant with a guard, and land an XSS regression suite. **No third-party library is vendored** (see the mission's resolved Third-party constraint + the Design Decision below).

### Open Questions

- [x] Vendor marked+DOMPurify, or harden the existing parser? → Design Decisions (harden; no vendor — independently adjudicated)
- [x] Syntax highlighting? → Deferred (mission Open Question resolved)
- [x] Bubbles vs single-column reading layout? → Design Decisions

### Design Decisions

**No vendoring — harden the existing parser + deliver the security intent structurally** (mission-level reversal, independently confirmed; full rationale in flight log + mission constraint annotation):
- The Flight-4 survey found `markdown.js` (812 LOC) is already a DOM-building parser: ZERO `innerHTML`, `render()` returns a `DocumentFragment`, literal tag names only, untrusted data reaches only `textContent`/`createTextNode` and a fail-closed `safeHref()` scheme allowlist (js:/data:/vbscript: → `#`), links always `rel="noopener noreferrer"`. XSS is impossible by construction. The classic DOMPurify threat classes (mXSS, parser-differential, DOM clobbering) all require parsing an untrusted HTML string — which this pipeline never does.
- An independent security-architect review confirmed vendoring `marked` (which emits an HTML string) + DOMPurify would WORSEN posture: it forces an HTML-string→sanitize→fragment seam (reintroducing the `innerHTML`-class operation deliberately eliminated), breaks the streaming fragment/partial-buffer contract (`commitSafeBoundary`/`finalizeStreamingBubble`, chat.js:520-600), and is a large rewrite of a working, tested subsystem — for CommonMark-completeness that is UI-polish, not an impediment. Under the operator's default (no 3rd-party libs unless they clear the "impediment to a good UI" bar), it did not clear it.
- **Instead**: (a) harden `markdown.js` where the review found nits (protocol-relative `//host` → force `#` or lock the current allow-decision with a test; confirm `lang` class-attr injection is impossible); (b) **no-HTML-string invariant guard** (retargets the mission's "CI integrity verification"): a pytest asserting `markdown.js` `innerHTML`/`outerHTML`/`insertAdjacentHTML` count stays exactly 0 (scoped to those three literal tokens), and `render()` returns a DocumentFragment, and every `createElement` arg is a string literal **OR** a member of the proven-bounded allowlist `{h1..h6 (from `'h'+lvl`, lvl∈1..6), ol, ul (from the `ordered?'ol':'ul'` ternary)}` — the leg enumerates exactly these two dynamic-tag exceptions with a comment; the guard also carries a one-line allowance note for the trusted-icon `DOMParser().parseFromString(svg,'image/svg+xml')` line (injectIcon) so a future reader doesn't "tighten" it into a false failure. (c) **XSS regression suite** (the mission-required deliverable, expanded from the existing `test_markdown.py` safeHref tests, same parametrized `page.evaluate` pattern) — mXSS/script/onerror/iframe/svg-onload payloads AS markdown body assert to inert text (`textContent`, `querySelector('script,iframe,img')` null; framed as future-proofing tripwires — the class is structurally impossible today, but they fire the instant an `innerHTML` seam is reintroduced), safeHref boundary (whitespace/control-char/case-obfuscated schemes → `#`, valid schemes pass, rel set), code-fence lang-payload → class-attr-only, and streaming-specific (a half-written `[x](javascript:` at a render boundary never emits a live unsafe href). Land (b)+(c) in the SAME leg as any parser hardening.
- The `App.markdown` facade (`parse`→AST/**19 NodeTypes**, `render`→DocumentFragment, null/partial tolerant) is preserved verbatim; the 4 consumer call sites (message-bubble.js:89, chat.js:548/599, markdown-section.js:33) do not change. `test_markdown.py` (870 LOC) is the facade regression net — it must stay green.

**Chat reading layout — single-column, refined turn distinction** (SC4): keep the single-column `.messages` log (`role="log" aria-live="polite"`). Refine turn distinction to the quiet vocabulary: user turns as a compact right-aligned tinted block (`--accent-subtle`/translucent wash, not a saturated `--accent` fill — the current full-accent user bubble is loud; **preserve right-alignment** — the peer-attribution/visibility tests assert `alignSelf`, not background, and stay green if alignment holds), agent turns as near-full-width plain prose on the reading surface with a muted attribution meta line; content column max-width for readability. Tool bubbles and system messages keep their distinct-but-quiet treatment. Every washed surface carrying text (assistant-on-translucent, tool-on-surface-tool, peer-on-elevated, table zebra, telemetry-ghost) gets a **composited-a11y gate** per the F3 debrief (`_alpha_composite(fg,alpha,base)` reconstruct-and-assert-body-AA in `test_design_tokens_a11y.py`, both themes) — author each wash as rgba-over-a-single-known-surface (not wash-over-wash or `color-mix()`, which the one-layer helper can't reconstruct) and add its fg+alpha+base to the `design_tokens.py` mirror. **The tinted user-bubble text needs a NEW composite gate** (fg on the `--accent-subtle`/translucent wash, both themes); refresh the stale comment at `test_design_tokens_a11y.py:~188-191` that ties the `fg_on_accent`×`accent` pair to "the parent `.msg.user` rule" (the pair test stays valid — `.btn-filled-primary` still uses the accent fill — only the comment goes stale). Note for the implementer: `test_snapshot_chat_with_messages` (visual baseline) changes with the tint — this is a local-only `--snapshot-update` regen (gitignored), NOT a committed-baseline break; regenerate, don't chase.
- **Streaming-setup invariant** (implementation note, not a design change): if this leg wraps the bubble in a visual "bubble-container", the streaming setup (chat.js:~1213-1220) must keep `currentStreamingMsg = bubble` (the inner text-bearing element), never the wrapper — the `commitSafeBoundary`/`finalizeStreamingBubble` seam depends on `lastChild.nodeType===3`. The render seam itself is untouched by the visual work.

**Composer + stop affordance to vocabulary** (SC4/SC5): the composer input adopts the `.field`/vocabulary input styling; the send button is already `.btn-filled-primary` (keep); the existing `chat-stop-btn` (mission DD preserve-item — `chat.js:168`, `data-testid="chat-stop-btn"`, `aria-label="Stop"`, visibility via `isCurrentBusy()`) is restyled to a vocabulary variant (a `.btn-muted-destructive` or ghost-stop treatment) — stopping generation stays first-class, keyboard-operable, with the pinned focus ring. **If the stop button sits on `--*-danger-soft`, it gets the composite-a11y gate (stop-on-danger-soft, the exact F3 headline genre).** Streaming keeps its incremental render; add scroll-position awareness (auto-scroll only when the user is at the bottom; a "jump to latest" affordance when scrolled up) if achievable within the leg — else log as a follow-up.

**Code blocks + copy button to vocabulary**: the `--code-block-bg`/`--code-block-fg` well restyled to the quiet code surface (both themes, contrast-verified — **composite-a11y gate: code fg-on-bg both themes**); the `.markdown-copy-btn` (components.css:1145-1177, currently hover/focus-opacity-reveal) reconsidered against the F3 CTA lesson (hover-reveal-only affordances hurt discoverability — make it always-visible-but-quiet or keyboard-reachable at minimum). Inline `<code>` pill to the vocabulary.

**Tool-trace + thinking disclosures to vocabulary**: the `<details>` trace shell (trace-shell.js) and thinking disclosure restyled to the vocabulary disclosure treatment (quiet summary, hairline, no alien effects); they already keep tool activity out of the reading flow — preserve that, restyle the chrome.

**Button vocabulary consumed directly, field-group convention** (F3 debrief): chat instantiates the F3 button variants as-is (no per-area variants); any chat form control uses `.field-group` with the full label-association wiring (unique id, `label.for`, invalid→`aria-describedby`).

**Guard bookkeeping** (F3 debrief): re-baseline `DYNAMIC_SINK_BASELINE` to the live count (92, pruning the 3 stale F3 gallery entries) BEFORE this flight's chat churn; the 4 chat sink entries ratchet DOWN as the re-skin migrates static-template innerHTML to createElement where cheap; state expected direction per leg; the no-HTML-string invariant guard is net-new. Add the **JS-references-dead-CSS-var tripwire** (F3 debrief rec 5 — grep JS strings for `var(--token)` refs absent from tokens.css; this flight churns chat CSS+JS, the exact genre of the F3 Leg-1 dead-alias miss) in the leg-1 guard work. Fix the CLAUDE.md `stream_chunks` doc drift (documented as a number; impl + all tests use a list) while in the docs. **Browser-lane cost** (F3 rec 5): this flight adds the XSS corpus + composite gates + a behavior gate — accept the ~12.5min→growth consciously; measure browser wall-clock at the flight-close ledger and flag if a per-area lane is now due (decide at F4 debrief, not mid-flight).

**Behavior gate — chat round-trip with the mock provider** (SC7 down-payment): author a `chat-roundtrip` behavior spec driving the mock provider (`stream_chunks` is a LIST of strings, not a number; `config.response` for the final content; `seed_mock_provider`/`seed_mock_agent` POST over HTTP) through: send a message → streaming assistant reply renders → markdown (bold/code) renders on done → the stop affordance appears during streaming → a session survives reload. **Precondition (state in the spec preamble)**: the instance under test must be launched with `THE_ONE_DEV_MODE=true` for the `mock` provider type to be creatable (the 8485 mission instance already runs dev-mode per `.env`; the spec's precondition-check confirms it, and states a dev-mode relaunch step if a fresh instance is used). Run in BOTH themes at flight close (delegated orchestrator). This is distinct from `shell-navigation-smoke` (navigation) — it verifies the chat *interaction* on the redesigned surface.

### Prerequisites

- [x] Flights 1-3 completed (vocabulary + tokens + shell live; button/field vocabulary available)
- [x] Chat + markdown surface surveyed (facade contract, streaming coupling, sink surface, mock-provider mechanics)
- [x] Independent security adjudication of the vendoring decision (DO NOT VENDOR — confirmed)
- [x] 8485 mission dev instance; mock provider available via dev mode

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Markdown hardening + the invariant guard + XSS suite land first (they protect the facade the re-skin's streaming depends on and are independent of the visual work). Then the chat re-skin proceeds surface by surface (reading layout + turn distinction → composer + stop → code blocks + copy → disclosures), each with composited-a11y gates and both-theme verification. Then flight verification + the delegated chat-roundtrip behavior gate. `test_markdown.py` stays green throughout (facade unchanged).

### Checkpoints

- [x] markdown.js hardened; no-HTML-string invariant guard + XSS suite green; test_markdown.py still green (facade intact)
- [x] Chat reading layout + turn distinction in the vocabulary, both themes; composited-a11y gates green
- [x] Composer + stop affordance + code blocks + disclosures restyled; stop stays first-class; copy button discoverable
- [ ] Suites green; chat-roundtrip behavior gate passes both themes; sink baseline ratcheted honestly *(suites green + sink baseline honest at 92 ✓; the chat-roundtrip Witnessed RUN is deferred to Flight 7's SC7 gate — spec authored + active, runtime interaction already evidenced by the a11y live-verification + the leg-4 dual-theme visual pass)*

### Adaptation Criteria

**Divert if**: the streaming re-integration or a facade change breaks `test_markdown.py` in a way that can't be fixed within the leg (the facade is load-bearing — stop and re-scope rather than weaken the contract).

**Acceptable variations**: exact chat CSS within the vocabulary; scroll-position-awareness deferred to a follow-up if it balloons; leg order among the visual surfaces.

### Legs

> **Note:** Tentative; created one at a time as the flight progresses.

- [x] `markdown-hardening-and-xss-suite` - safeHref hardening; no-HTML-string invariant guard (with the 2 bounded-dynamic-tag + DOMParser allowances); XSS regression suite; JS-dead-CSS-var tripwire; CLAUDE.md stream_chunks fix; sink re-baseline to 92
- [x] `chat-reading-layout` - single-column reading layout, user/agent turn distinction to vocabulary (tinted user bubble, right-align preserved), composited-a11y gates for washed surfaces incl. the NEW tinted-user-bubble gate + stale-comment refresh; snapshot regen note
- [x] `composer-streaming-codeblocks` - composer + stop affordance to vocabulary (+ stop-on-danger-soft a11y gate), code-block well + copy button (+ code fg-on-bg a11y gate), inline code, disclosures (trace + thinking) chrome. *(Fattest leg — split into composer+stop | code+disclosures if it balloons.)*
- [x] `chat-verification` - suites (incl. test_markdown.py facade net green) + dual-theme visual pass (focus via CDP) + author + delegate `chat-roundtrip` behavior spec (mock provider, dev-mode precondition) + sink/registry ledger + browser wall-clock measure *(landed 2026-07-04; `chat-roundtrip` spec authored + active — behavior-gate RUN is FD-pending, delegated at flight close, both themes)*

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Tests passing
- [x] Flight log updated (incl. the no-vendor decision record)
- [x] Documentation updated (CLAUDE.md `stream_chunks` doc drift fixed in Leg 1; no `agents.md` chat/markdown note warranted — the re-skin was CSS-led and the `App.markdown` facade/API + chat contracts are unchanged by the no-vendor path)

### Verification

`test_markdown.py` green (facade intact); the no-HTML-string invariant guard + XSS suite green; chat renders the quiet vocabulary in both themes (no alien effects, no loud full-accent user bubble); stop affordance first-class + keyboard-operable; `chat-roundtrip` behavior spec passes both themes; `shell-navigation-smoke` still passes; sink baseline honest.
