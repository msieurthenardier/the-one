# Flight Log: Chat Re-skin + Markdown Hardening

**Flight**: [Chat Re-skin + Markdown Hardening](flight.md)

## Summary

In flight. Leg 1 (markdown-hardening-and-xss-suite) landed: `markdown.js` safeHref
hardened, no-inner-HTML invariant guard + JS-dead-CSS-var tripwire added, XSS
regression suite landed, sink baseline re-baselined to the honest live count, and the
`stream_chunks` CLAUDE.md doc drift fixed — all with the `App.markdown` facade unchanged
(`test_markdown.py` stayed green throughout).

Leg 2 (chat-reading-layout) landed: user turns retuned from the loud full-`--accent`
fill to a quiet `--accent-translucent` tint (right-alignment preserved), the API-source
user bubble kept as a distinct saturated marker with a pinned text color, agent turns
widened to near-full-width prose (`min(100%, 46rem)`); four composited-a11y gates added
(tinted-user-bubble, assistant-on-translucent, table-zebra, telemetry-ghost) plus the
`fg_on_accent × accent_api` stale-comment refresh; pixel baselines regenerated locally.
CSS + test only (no JS diff → sink baseline unchanged, no new tokens).

Leg 4 (chat-verification) landed: full unit + browser suites green (one unrelated
discord-connector-form flake dispositioned per the F2/F3 rule — no chat/markdown
failures), browser wall-clock measured, dual-theme visual pass recorded across the
enumerated chat surfaces with CDP focus evidence + a clean SC1 spot-check, the
`chat-roundtrip` behavior spec authored (active; RUN delegated to the FD at flight
close), and the sink/registry + browser-lane ledger recorded. Flight stays in-flight
pending the delegated behavior-gate run.

Leg 3 (composer-streaming-codeblocks) landed: composer input adopts the `.field-input`
vocabulary; the stop button consumes the `.btn-muted-destructive` primitive directly; the
markdown copy button changed from hover-reveal-only to always-visible-but-quiet (rest
opacity 0.6); code-well radius aligned to `--radius-sm`; disclosures already conformed
(no change). Both required a11y gates (code fg-on-bg, danger-on-soft-fill) pre-existed and
stayed green — the restyled stop button is a new consumer of the exact gated danger-soft
pair. One regression found and fixed: the shorter vocabulary composer slid the transient
pending-queued chip's × button under the z-index:1 telemetry HUD — fixed by stacking the
queued region above the HUD (`z-index:2`). No leg split (stayed one commit's worth). Dual-
theme verified via CDP computed-style evidence + focus-order; pixel baselines regenerated.

---

## Leg Progress

### Leg 1 — markdown-hardening-and-xss-suite (landed, 2026-07-04)

**safeHref decision (protocol-relative → `#`)**: The old allow-list
(`/^(https?:|mailto:|tel:|\/|#)/i`) let protocol-relative `//host` URLs pass, because a
leading `/` satisfied the root-relative branch. A `//host` link inherits the page scheme
and resolves off-site — not clearly what a markdown author intends — so it now force-maps
to `#` via a `^\s*\/\//` check evaluated BEFORE the allow-list. Root-relative `/path`
(single slash) still passes. The allow-list stays anchored + fail-closed, so obfuscated
schemes (leading whitespace / tab / newline / control chars, mixed case) already fell
through to `#`; the XSS suite now locks that boundary explicitly. No existing
`test_markdown.py` case covered `//host`, so the facade net stayed green. The
module-header XSS-guarantee doc comment was updated to record the protocol-relative + 
fail-closed behavior.

**No-inner-HTML invariant guard mechanics** (`tests/test_ui_guards.py::
test_markdown_no_html_string_invariant`, helpers in `tests/_ui_guard_helpers.py`): a
static read of `markdown.js` asserting (a) ZERO literal `innerHTML`/`outerHTML`/
`insertAdjacentHTML` tokens (camelCase — the file's prose uses the hyphenated
"inner-HTML" spelling, which does not match), and (b) every `createElement` argument is a
bare string literal OR one of exactly two bounded dynamic-tag expressions —
`'h' + lvl` (h1..h6, clamped by the ATX parser) and `ordered ? 'ol' : 'ul'` (ol|ul). The
trusted-icon `DOMParser().parseFromString(svg,'image/svg+xml')` line in injectIcon carries
an explicit allowance note (it is the sanctioned no-inner-HTML glyph path, parses no
untrusted data, and is not scanned) so a future reader will not "tighten" it into a false
failure. The `render()`-returns-DocumentFragment leg of the invariant is covered by the
existing runtime assertion in `test_markdown.py`. **Probe-tested**: planting `innerHTML =`
and `createElement(userVar)` each made the guard fail naming the offending line; reverted.

**JS-dead-CSS-var tripwire** (`test_js_string_css_var_refs_are_defined`): scans JS STRING
literals (comments excluded via a quote/comment-state walker) for `var(--token)`
references whose token is absent from `tokens.css`/`fonts.css` — closing the F3 Leg-1
dead-alias-in-JS miss class (`test_token_definitions.py` only scans `*.css`). Comment
exclusion matters: the F4 survey found a prose `var(--space-N)` mention in a
`tokens-section.js` `//` comment that is NOT a real reference. **Probe-tested**: planting
`'var(--nonexistent-probe-xyz)'` in a JS string made the guard fail naming token + file;
reverted.

**XSS regression suite categories** (additive to `tests/browser/test_markdown.py`, same
parametrized `page.evaluate` pattern, +29 cases): (1) active-content payloads as markdown
BODY — script / img-onerror / iframe-javascript / svg-onload / mXSS-noscript → inert text
(no live `script,iframe,img,svg` element; `alert(1)` survives in `textContent`); (2)
safeHref boundary — leading-whitespace/tab/newline/control-char/mixed-case obfuscated
`javascript:`/`vbscript:`, plus `data:`/`file:`/protocol-relative → `#`; valid
`https:`/`http:`/`mailto:`/`tel:`/root-relative/`#frag` pass; every link
`rel="noopener noreferrer"`; (3) code-fence lang payload (`js" onmouseover="alert(1)`) →
class attribute value only (setAttribute never parses it into an event handler or a new
element); (4) streaming-boundary — half-written `[x](javascript:` sliced at a commit
boundary never emits a live unsafe href (malformed → literal text; complete → safeHref
strips). Framed as future-proofing tripwires: structurally impossible today, they fire the
instant an inner-HTML seam is reintroduced.

**Sink re-baseline (95 → 92)**: pruned the 3 stale F3 design-language gallery entries
(`fields-section.js`, `surfaces-section.js`, `tabs-section.js` — their dynamic innerHTML
sinks were already gone from source) from `DYNAMIC_SINK_BASELINE` so the freeze reflects
the live 92 sites / 27 files before F4's chat churn. Removals never fail the ratchet; this
just makes the baseline honest. No NEW sinks introduced by this leg.

**CLAUDE.md `stream_chunks` fix**: corrected the §"Dev mode" wording from "number of
streaming chunks" to "a LIST of strings whose elements are the literal chunk texts"
(matches `the_one/llm/mock.py` + all browser tests).

**Verification**: `test_markdown.py` green after the safeHref touch and again with the XSS
suite (120 browser cases); `test_flow_markdown_chat.py` green (5); guard/token/a11y unit
slice green (123); full `make test-unit` green (3751 passed, 10 skipped); ruff check +
format clean. Facade (`parse`→AST/19 NodeTypes, `render`→DocumentFragment) unchanged.

### Leg 2 — chat-reading-layout (landed, 2026-07-04)

**Turn-distinction decisions**:
- **User bubble → tinted, not full-accent** (chat.css `.msg.user`): the loud
  saturated `--accent` fill + `--fg-on-accent` text was retuned to an
  `--accent-translucent` wash (rgba accent — 0.10 dark / 0.08 light) with
  primary `--fg` text and a hairline `--accent-translucent-hover` border for
  definition. **Right-alignment preserved** (`align-self: flex-end`) — the
  peer-attribution/visibility tests assert `alignSelf`, not background, and
  stayed green (verified: `test_flow_chat_peer_attribution.py` peer→flex-start,
  operator→flex-end). No `--accent-subtle` token exists; `--accent-translucent`
  IS the subtle-accent wash and was reused (no new token, no tokens.css change).
- **API-sourced user bubble kept a DISTINCT saturated marker** (`.msg.user.api`):
  it previously *inherited* `color` from `.msg.user`. Since `.msg.user` now
  carries `--fg`, a naive change would have made the saturated `--accent-api`
  (bright cyan) bubble inherit near-white `--fg` → an unreadable dark-theme
  regression (~1.2:1). Resolved by keeping `.msg.user.api` a saturated
  `--accent-api` fill and **pinning `color: var(--fg-on-accent)` explicitly**.
  Rationale: the API-source fill is a deliberate "not-operator-typed" signal
  (analogous to the peer-bubble border); keeping it saturated preserves that
  distinction AND keeps the existing `fg_on_accent × accent_api` a11y gate
  valid (its consumer is exactly this rule). Only the plain operator bubble —
  the DD's "loud" complaint — went quiet.
- **Agent turns → near-full-width prose** (`.msg.assistant`): the shared `.msg`
  85% cap was lifted to a readable content-column measure `min(100%, 46rem)`;
  the quiet `--surface-translucent` wash + hairline border stay (they carry the
  assistant-on-translucent gate and keep the assistant bubble distinct from the
  `--surface-elevated` peer bubble). User bubbles keep the compact 85% cap — the
  width asymmetry is the refined turn distinction. Muted `.from-agent`
  attribution line unchanged.

**Composite-a11y gates added** (`test_design_tokens_a11y.py`, `_alpha_composite`
over the single known base surface `--bg` = the `.messages` log background;
both themes; alphas spelled as test-local constants tracking tokens.css, per the
`_STATUS_DANGER_SOFT_ALPHA` precedent — the mirror deliberately does not store
rgba/alpha, only their bases, which are all already present):
- **`test_tinted_user_bubble_text_passes_body_aa`** (NEW headline gate): `--fg`
  on `--accent-translucent` over `--bg` ≥ 4.5. Measured: dark **14.1:1**,
  light ~10:1 (live-computed in-browser on 8485 corroborated dark = 14.14:1).
- **`test_translucent_surface_prose_passes_body_aa`** (assistant-on-translucent
  + GFM table-zebra, both = `--fg` on `--surface-translucent` over `--bg`;
  zebra modeled single-layer per the "one known surface" rule) ≥ 4.5 — passes
  with wide margin (the 0.03 wash barely lifts `--bg`).
- **`test_telemetry_ghost_value_holds_annotation_floor`**: the telemetry
  overlay's `--fg-secondary` value readout ghosted at the resting `opacity: 0.7`
  over `--bg` ≥ **3.0** (annotation floor, matching the deliberate `--fg-faint`
  band philosophy) — the readable state is the hover/focus `opacity: 1.0`, fully
  body-AA via the fg-ladder sweep. Measured resting: dark 4.16:1, light 3.62:1.
- **Solid surfaces NOT re-gated** (documented in the test module): tool-on-
  surface-tool (`fg_tool_msg × surface_tool`) and peer-on-elevated
  (`fg × surface_elevated`) are non-rgba solids already covered by the fg-ladder
  × surface sweep; compositing them would be wrong (no alpha).

**Stale-comment refresh** (`test_design_tokens_a11y.py` text-on-color table):
the `fg_on_accent × accent_api` comment tied "`--fg-on-accent` inherits from the
parent `.msg.user` rule" — stale once `.msg.user` carries `--fg`. Refreshed to
note `.msg.user.api` now PINS its own `--fg-on-accent`; also annotated the
`fg_on_accent × accent` pair that `.msg.user` no longer uses it (the pair stays
gated via `.btn-filled-primary`).

**Snapshot regen**: `test_snapshot_chat_with_messages` (+ the other 11 pixel
baselines) regenerated locally via `pytest -m pixel --snapshot-update` through
run-tests.sh (not as root; `tests/browser/__snapshots__/` confirmed gitignored /
untracked). Expected local-only churn from the tint + width, not a committed
baseline break.

**Verification**: a11y+guard+token unit slice green (131); chat-flow + markdown
browser slice green via run-tests.sh (164, incl. peer-attribution `alignSelf`,
visibility distinction, and the markdown facade + XSS suite — facade intact);
full `make test-unit` green (exit 0); pixel baselines regenerated (12); ruff
check + format clean. Both themes visually verified on the 8485 mission instance
(hot-swapped the versioned `chat.css?v=…` with a cache-buster since CSS isn't
version-bumped on restart): user bubble tint + `flex-end` + `--fg` text +
`min(100%,46rem)` agent prose confirmed in light AND dark; theme preference
recorded (`auto`) and restored; own tab closed. **No JS diff** (CSS + test only)
→ sink baseline unchanged. No new tokens.

### Leg 3 — composer-streaming-codeblocks (landed, 2026-07-04)

**Composer + stop decisions**:
- **Composer input → `.field-input` vocabulary** (chat.js: added `field-input`
  class; chat.css: retired the bespoke `.area-chat .input-area input` body-lg
  rules). The prior deliberate divergence ("chat input sized differently from
  `.field-input`") is reversed per the flight DD "composer input adopts the
  `.field`/vocabulary input styling" — form-control consistency wins. The input
  keeps its `aria-label="Message"` accessible name (a single-input send
  affordance, not a labeled form; the DD's `.field-group`-with-visible-label
  convention applies to multi-field chat forms, not the composer). `.input-area`
  gained `align-items: center` to vertically center the ~33px vocabulary input
  against the 32px vocabulary buttons.
- **Stop button → `.btn-muted-destructive` consumed directly** (chat.js: class
  `btn-stop-turn` → `btn-muted-destructive`, and the `stopBtn` querySelector;
  chat.css: the bespoke `.btn-stop-turn` block deleted). No per-area variant, per
  the F3-debrief "button vocabulary consumed directly" rule. **Critical
  re-assertion**: the primitive sets `display: inline-flex`, which overrides the
  UA `[hidden]{display:none}` — so a scoped `.btn-muted-destructive[hidden]
  {display:none}` rule was added (this codebase re-asserts `[hidden]` per-selector;
  there is no global button `[hidden]` reset). `isCurrentBusy()`→`updateStopControl`
  toggles `stopBtn.hidden` unchanged.

**Stop-on-danger-soft a11y gate**: the required gate ALREADY EXISTS
(`test_danger_text_on_soft_fill_passes_body_aa` — `--status-danger` on the
composited `--status-danger-bg-soft`, both themes). The `.btn-muted-destructive`
stop button is exactly `--status-danger` ink on the `--status-danger-bg-soft`
fill, so it is a new consumer of that gated pair — no new gate authored, gate
stays green. Live-measured on 8485: light fill `rgba(185,28,28,0.06)` / ink
`rgb(185,28,28)`; dark fill `rgba(248,113,113,0.08)` / ink `rgb(248,113,113)`.

**Code blocks + copy decisions**:
- **Copy button → always-visible-but-quiet** (components.css `.markdown-copy-btn`
  rest `opacity: 0` → `0.6`; wrap-hover / focus-within / own hover+focus still
  lift to 1). Fixes the F3 CTA "hover-reveal-only hurts discoverability" lesson.
  **CSS-only — `markdown.js` `renderCodeBlock` untouched** (the copy-button +
  code-well markup is DOM-built there; the Leg-1 no-HTML-string invariant guard +
  XSS suite are unaffected, and `test_markdown.py`'s exact-markup assertions stay
  valid). The button is a real keyboard-reachable `<button aria-label="Copy code">`
  (tabIndex 0, matches `:focus-visible`, 2px accent ring — CDP-confirmed).
- **Code-well** already used the quiet `--code-block-bg`/`--code-block-fg` tokens;
  its `border-radius: var(--space-1)` was aligned to `var(--radius-sm)` to match
  the shared `.code-block`. **Code fg-on-bg a11y gate ALREADY EXISTS**
  (`test_text_on_color[code_block_fg × code_block_bg]`, 4.5, both themes) — tokens
  unchanged, stays green. Inline `<code>` pill (`--surface-elevated`, mono)
  already vocabulary — unchanged.

**Disclosures**: the `<details>` trace shell + thinking disclosure ALREADY
conform to the quiet vocabulary (hairline `border-left`, muted-mono summary,
custom disclosure triangle, pinned `:focus-visible` ring, no alien effects). No
change needed; `test_flow_chat_thinking_disclosure.py` (DOM-shape only) green.

**Scroll-position awareness**: smart-scroll (`scrollToBottomIfPinned`, auto-scroll
only when the user is near the bottom) was ALREADY implemented (M08 F6 L06). The
optional "jump to latest when scrolled up" affordance was NOT added — logged as a
follow-up per the DD's "if achievable within the leg — else log as a follow-up."

**No leg split**: the leg did not balloon (mostly CSS + one JS class swap + one
z-index fix), so it stayed one commit's worth under this single leg artifact.

**Verification**: guard/token/a11y unit slice green (131, incl. both pre-existing
gates + the no-HTML-string invariant + sink baseline); markdown facade + XSS +
copy-button + thinking-disclosure + queued-render browser slice green via
run-tests.sh (130); remaining chat-flow browser slice green (21); full
`make test-unit` green (3800 passed, 18 skipped); ruff check + format clean; pixel
baselines regenerated locally (12, gitignored/untracked — confirmed via
`git check-ignore`). Dual-theme verified on the 8485 instance via a fresh
uncached CDP page: computed-style evidence for stop/code-well/copy/input/inline/
disclosure tokens in BOTH light and dark, and keyboard focus-order evidence
(input → Stop → Send, each a 2px accent ring; copy button `:focus-visible` +
accent ring). Theme preference recorded (`auto`) and restored; own tabs closed;
8484 untouched. **JS diff is class-string-only inside the existing `content.
innerHTML` composer template — no new/removed dynamic sink → sink baseline
unchanged (honest).**

### Leg 4 — chat-verification (landed, 2026-07-04)

**Suite counts + timing**:
- **Unit** (`make test-unit`): **3759 passed, 10 skipped** (651 deselected) — 322.28s
  pytest / 5:34 wall. Green.
- **Browser FULL** (`TEST_TIMEOUT=3600 make test-browser`, run ONCE): first pass
  **561 passed, 6 skipped** (12 deselected), **1 failed** —
  `test_flow_studio_connector_discord_form.py::
  test_no_change_save_roundtrip_omits_intents_when_absent` (a Discord-connector-form
  Save button that stayed `disabled` — **unrelated to the chat/markdown surface**).
- **Flake disposition applied** (pre-specified F2/F3 rule): the failing test **passed
  in isolation (1/1)** AND on **one clean rerun of its full module (12/12,
  `test_flow_studio_connector_discord_form.py`)** → **flake, logged**. Only **1 module
  flaked (< 2 threshold)** → **no full-suite rerun**. Effective browser result:
  **562 pass / 6 skip / 0 genuine failures.**

**Browser wall-clock** (F3 debrief asked to measure): **12:45 pytest / 13:08.85 total
wall-clock** for the full browser suite. Modestly up from the ~12.5min F3 baseline
despite F4 adding the XSS corpus (+29 cases → 120 markdown cases) + composite gates.
**Per-area-lane flag**: growth is single-digit-% over baseline, not a step change — a
per-area browser lane is worth *considering* but not yet mandated; **decision deferred
to the F4 debrief per the flight DD** (not decided mid-flight).

**Facade net + guards + XSS + tripwire** (all green, confirmed in isolation for the
ledger):
- `tests/browser/test_markdown.py` — **120 passed** (the `App.markdown` facade
  regression net + the L1 XSS regression suite, combined in one file; facade intact).
- Unit guard/a11y/token slice — **131 passed**, including the L1
  `test_markdown_no_html_string_invariant` (no-HTML-string guard) + the
  `test_js_string_css_var_refs_are_defined` tripwire (both re-confirmed **2/2** in a
  targeted run) + all composite-a11y gates (tinted-user-bubble, assistant-on-
  translucent, table-zebra, telemetry-ghost, code-fg-on-bg, danger-on-soft).

**Sink/registry ledger**: `DYNAMIC_SINK_BASELINE` = **92 sites / 27 files** (the honest
live count re-baselined in L1). The invariant/ratchet guard is **green**, i.e. the live
dynamic-sink count matches the frozen 92 exactly. **The anticipated L2/L3 ratchet-DOWN
did not materialize** — the re-skin was CSS-led (L2 = CSS + test only; L3 = a
class-string swap *inside* the existing `content.innerHTML` composer template), so no
static-template `innerHTML` was migrated to `createElement` and no dynamic sink was
added or removed. Honest direction: **baseline held at 92 through the whole flight**,
not lowered. No new tokens. **ruff check + format clean** (397 files).

**Dual-theme visual pass** (8485, `THE_ONE_PORT=8485`; hard-reload doctrine — CSS not
cache-busted on restart; goldfinch for surfaces + a `printToPDF`-pixel capture per
surface, a CDP chrome-devtools page for focus; evidence PDFs live in the run scratchpad,
gitignored/not committed):
- **Rich existing session** (user tinted bubble + agent prose + 8 tool-trace
  `<details>` + thinking disclosures), BOTH themes: muted-mono summaries
  (`rgb(133,135,143)` dark / `rgb(110,110,119)` light), **2px hairline `border-left`,
  `box-shadow: none`** (no alien effects), tool msgs on `--surface-tool`.
- **Mock done-state** (seeded a throwaway `vpass-mock` provider + `vpass-mock-agent`,
  paced stream via `delay_ms`), BOTH themes: **`**bold**` → `<strong>`, `` `inline
  code` `` → `<code>`, fenced block → `<pre><code class="language-python">`** (real
  markup, not literal); copy button present at rest `opacity: 0.6`, `tabIndex 0`,
  aria "Copy code"; user tint `rgba(109,40,217,0.08)` light / `rgba(167,139,250,0.10)`
  dark with **`--fg` text + `align-self: flex-end`** (tinted, NOT loud full-accent);
  agent prose `max-width: min(100%, 736px)`; code-well fg/bg with `6px`
  (`--radius-sm`).
- **Streaming stop affordance**: authoritative computed-style during a live stream —
  stop `hidden:false`, `display:flex`, ink `rgb(185,28,28)` on `rgba(185,28,28,0.06)`
  (the `.btn-muted-destructive` danger-on-soft pair), aria "Stop". (The `printToPDF`
  for this surface settled to the done state by capture time — pixel evidence is weak
  there; the computed-style probe + the live CDP focus below are the authoritative
  evidence.)
- **Focus via CDP** (chrome-devtools page): composer input, Send (`.btn-filled-primary`),
  Copy, and Stop (focused live during streaming) each show `:focus-visible` with a
  **2px solid `rgb(109,40,217)` accent ring**; the Stop affordance is keyboard-operable
  during streaming (SC5).
- **Empty/welcome**: `.chat-welcome` ("Which agent would you like to chat with?")
  present + styled primary-fg; the true empty-DB state was **not** forced on the
  populated mission instance (318 sessions) — the regenerated `chat-empty-{light,dark}
  .png` pixel baselines are the regression net for that surface.
- **SC1 spot-check**: the chat surface swept in BOTH themes (509 elements each) for
  alien remnants (heavy glows / gradients / text-shadows / filters) → **0 found**. No
  alien console remnants on the redesigned chat surface.
- **Hygiene**: theme preference recorded (`auto`) and restored (`auto`) — theme is
  ephemeral (not persisted to localStorage/cookie), so the operator's own tabs were
  never affected; own goldfinch tab + CDP page closed; the seeded mock
  provider/agent/session **deleted (verified gone)**; **8484 never touched**.

**Pixel snapshots**: regenerated locally (final flight-wide regen, 12 baselines, as
non-root) via `run-tests.sh -m pixel --snapshot-update`; `tests/browser/__snapshots__/`
confirmed **gitignored + absent from `git status`** (not committed).

**Behavior spec authored** (NOT run — the FD delegates the run at flight close):
`tests/behavior/chat-roundtrip.md`, status **active**, well-formed per ARTIFACTS.md
(Intent / Preconditions / Observables Required / Steps table / Out of Scope / Variants).
Mock-provider round-trip: a dev-mode precondition-check (probe `mock` in
`/api/providers/types`) + relaunch note; seed a mock provider (`stream_chunks` = a LIST,
`response.content` markdown, `delay_ms` to pace so the Stop affordance is observable) +
mock agent over HTTP; steps: open chat → new session with the mock agent → send →
(streaming) Stop appears → on done bold + inline-code render as real markup → hard-reload
survives; a both-theme variant; references SC7. Complements `shell-navigation-smoke`
(which defers chat round-trips to this spec).

---

## Decisions

### No-vendor reversal (mission-level, Flight Director, 2026-07-04)

**Context**: The mission-planning phase wrote a Design Decision to vendor `marked` + `DOMPurify` for the chat markdown pipeline, drawing on Flight-1-era research that assumed the renderer produced an untrusted HTML string needing sanitization.

**Discovery**: The Flight-4 code survey found `markdown.js` is a hand-rolled DOM-building parser — ZERO `innerHTML`, `render()` returns a `DocumentFragment`, literal `createElement` tag names, untrusted data reaching only `textContent`/`createTextNode` + a fail-closed `safeHref()` scheme allowlist, links always `rel="noopener noreferrer"`. XSS is impossible by construction.

**Independent adjudication**: A security-architect review (spawned per the operator's "use independent agents to research, look at best practices, then make the judgement call" directive) recommended **DO NOT VENDOR**, decisively: the classic DOMPurify threat classes (mXSS, parser-differential, DOM clobbering) all require parsing an untrusted HTML string, which this pipeline never does; vendoring `marked` (an HTML-string emitter) + DOMPurify would *worsen* posture by introducing an HTML-string→sanitize→fragment seam (reintroducing the `innerHTML`-class operation the codebase deliberately eliminated) and breaking the streaming fragment/partial-buffer contract, for a CommonMark-completeness gain that is UI-polish, not an impediment.

**Decision**: No library is vendored. The mission's third-party-loosening is NOT exercised. The security intent is delivered structurally: harden `markdown.js`, add a **no-HTML-string invariant guard** (retargeting the mission's "CI integrity verification" from vendored-file hash-pinning to invariant-guarding), and land the required **XSS regression suite** (expanded safeHref + mXSS-payloads-as-text + streaming-boundary tests). Syntax highlighting deferred.

**Rationale for reversal authority**: The operator delegated judgment calls ("make it by using independent agents to research... and ultimately you make the judgement call") and framed the third-party loosening as conditional ("can be loosened if it's an impediment to a good UI"). The existing parser is not an impediment. Reversing a planning DD on ground truth discovered during execution — with independent confirmation and full documentation — is correct Flight Director behavior. Mission constraint annotated (not silently rewritten); original framing preserved as commentary.

**Impact**: Flight 4 is primarily a chat RE-SKIN (the mission's actual outcome) plus markdown hardening, not a parser rewrite. Lower risk, delivers the security intent, respects the operator's supply-chain default.

---

## Deviations

### Leg 3 — telemetry-HUD / queued-chip z-index collision (found + fixed)

**Planned**: Leg 3 was scoped as a composer/stop/code/copy/disclosure re-skin — no
change to the telemetry overlay or the pending-queued region.

**Actual**: Adopting the `.field-input` vocabulary made the composer ~7px shorter,
which shifted the transient pending-queued chip down enough that its × cancel
button slid under the `position:absolute; z-index:1` telemetry HUD. The HUD then
intercepted pointer events and `test_flow_chat_queued_render.py::
test_cancel_chip_discards_held_message_no_turn_runs` failed (Playwright click
timeout — "telemetry-overlay subtree intercepts pointer events").

**Reason**: The overlap was a latent fragility (the HUD floats over the composer
zone at a fixed `bottom:76px`); the shorter composer merely exposed it. Confirmed
causal by reverting only the composer edits — the test passed on the Legs-1-2
baseline and failed with the vocabulary composer. Fixed robustly by stacking the
interactive queued region above the passive HUD (`.pending-queued-region {
position: relative; z-index: 2 }`) rather than tuning pixel heights — an
interactive affordance must always win pointer events over a decorative readout.
Full targeted + chat-flow browser slices green after the fix.

---

## Anomalies

### Leg 3 — CDP screenshot stale-layer artifact (dark theme, cosmetic, non-blocking)

**Observed**: Under chrome-devtools `emulate colorScheme:dark` (and again after the
app's own `App.theme.set('dark')`), CDP viewport screenshots rendered the
pre-existing large assistant prose bubbles with a light fill + dark text, while
the freshly-injected code-well + disclosures painted correctly dark.

**Severity**: cosmetic (screenshot-capture only). Authoritative computed-style
probes confirmed the actual DOM is correctly dark in both themes — the assistant
bubbles compute `background: rgba(255,255,255,0.03)` over `--bg #101114` with
`color: #ededf0` (light ink). The mismatch is a Chromium compositor stale-texture
quirk on already-painted layers under CDP capture, not a CSS-correctness issue.

**Resolution**: Verification relied on computed-style evidence (both themes, all
Leg-3 surfaces) as authoritative; the Playwright pixel regen (fresh page loads,
not subject to the stale-layer quirk) is the pixel regression net. No product
change warranted.

---

## Session Notes

**Flight complete — landed 2026-07-05.** All 4 legs completed: markdown hardening + no-HTML-string invariant guard + XSS suite (Leg 1), chat reading layout + turn distinction (Leg 2), composer/stop/code-blocks/disclosures to vocabulary (Leg 3), flight-wide verification + authored `chat-roundtrip` spec (Leg 4). The mission's planned "vendor `marked`+DOMPurify" Design Decision was **reversed** on ground truth discovered during execution (the parser is already a fail-closed DOM-builder, XSS impossible by construction) with an independent security-architect confirmation; the security intent was delivered structurally instead (harden + invariant guard + XSS suite), and the **mission constraint was annotated** (not silently rewritten). Both closing reviews **confirmed**: the general Reviewer `[HANDOFF:confirmed]` and the Accessibility Reviewer `[HANDOFF:confirmed]` (independently drove a real streaming turn — keyboard-operable stop, markdown rendering, both themes). The `shell-navigation-smoke` behavior gate **re-passed 6/6** after the chat re-skin (run log `tests/behavior/shell-navigation-smoke/runs/2026-07-04-22-27-35.md`). The `chat-roundtrip` Witnessed RUN is **deferred to Flight 7's SC7 gate** — the spec is authored + active, and the chat interaction is already evidenced by the a11y reviewer's live streaming-turn verification and the Leg-4 dual-theme visual pass (mock done-state: bold/inline-code/fenced-block real markup, live stop affordance, both themes), so no interaction claim rides on the deferred run. Commit hash to follow.
