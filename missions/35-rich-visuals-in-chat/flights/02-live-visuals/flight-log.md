# Flight Log: Live Visuals

**Flight**: [Live Visuals](flight.md)

## Summary
Ready. The flight was designed on 2026-11-09 on `flight/02-live-visuals`, from `main` at `3dc20800` (Flight 1 merged). Both Architect review cycles are folded in, and the mockups (six boards) and explicit OKs are approved. The operator approved the flight and marked it ready on 2026-11-09. It has seven legs; leg 1 ends in a go/no-go.

---

## Planning Notes

### Operator decisions (2026-11-09)
- Go ahead with live visuals as planned, after the planning explanation of what they deliver and cost.
- Block tag: `widget`.
- Freeze risk: the hang guard (DD7). Widgets auto-start everywhere; a widget running when the page froze comes back stopped.
- Carry-over: all three items from the Flight 1 debrief. The `chart.js` split with measured text width, the transcript streaming split, and the eval re-baseline first.
- Mockups before legs, and a HAT leg.
- Mockup review: Pause/Resume added to the card header beside Restart, as a cooperative pause:
  - the frame's prelude gates animation frames, timers, Web/CSS animations and its clocks;
  - removal stays the enforcement.
- Off screen, a widget now **pauses** instead of stopping. That reverses the mission's earlier "stop and restart" decision, and the mission criterion is amended. A ceiling on loaded frames bounds memory.
- Recorded as mission follow-ups, not in this flight:
  - Expand (in-app pop out);
  - Copy source;
  - Download/save and a separate pop-out window. The desktop app has no download support today: pywebview `ALLOW_DOWNLOADS` is False, and the app has no download code.

Mockup canvas: https://claude.ai/artifact/RarECj12aPxfKNH81o4UAX (private to the operator). It has five boards: a reply (dark), light with source open and Paused, stopped states, streaming, and notices.

### Planning probes (Flight Director, scratchpad, not committed)
These are Playwright scripts under the session scratchpad (`probe.py`, `iso.py`, `nav.py`), run against a local `http.server` sink. The engines were Playwright Chromium (headless shell and `channel="chromium"`) and WebKit through the repo's userland wrapper (`tests/browser/_ui_engines.py::_webkit_launch_kwargs`).

**1. Escape battery.** The frame was `<iframe sandbox="allow-scripts">` with `srcdoc` and a leading `<meta>` CSP.
- **Zero sink requests** from fetch, XHR, image, `sendBeacon`, WebSocket, form POST, `<link rel=prefetch>` and CSS `url()`, in both engines.
- **Refused:**
  - Parent DOM, `top.location`, `localStorage` → `SecurityError` (both engines).
  - `document.cookie` → `SecurityError` in Chromium; `""` in WebKit.
  - `window.open` → `null`.
  - `alert` → no dialog event.
  - Top navigation → `SecurityError`.
- **Allowed:**
  - `self.origin` → `"null"`, and the parent saw `event.origin === "null"`.
  - `new Worker('data:…')` was constructed, but it fetches nothing.

**2. Self-navigation.** The frame navigated itself by `location.href`, meta refresh and a link click.
- It **reached the sink** in both engines with no page policy, and with page `frame-src 'self'`.
- It was **blocked** with the page header `Content-Security-Policy: frame-src 'none'`, while the srcdoc document still loaded and ran.
- Removing the frame's `<meta>`, or adding a looser second one, loosened nothing (zero sink hits).

**3. Runaway.** A 3-4 s busy loop ran in the frame; the measure is the parent's maximum `setInterval` gap.

| Engine | srcdoc | same-site `src` | cross-site `src` (`localhost`) |
|---|---|---|---|
| Chromium headless shell | 3005 ms | 3007 ms | 3014 ms |
| Chromium full (`channel="chromium"`) | 51 ms | 51 ms | 57 ms |
| WebKit | 3171 ms | 3007 ms | 3007 ms |

Full Chromium isolates sandboxed frames out of process, so the page is unaffected. WebKit runs them on the page's thread, and a separate origin does not help. WebView2 is unmeasured, for leg 1.

### Research passes (read-only, 2026-11-09)
- **Seam map:** `markdown.js` `codeBlockRenderers`, the `transcript.js` commit, hold and pacing, `chart-stream.js` hard-coding, the `chart.js` section map, `message.js` `setTailHold`. Committed markdown has no control teardown. `theme.js` has no OS-flip event. There are no observers or iframes today.
- **Security premises:**
  - There are no CSP or frame headers anywhere.
  - The page never holds the credential; the cookie is `HttpOnly; SameSite=Strict`.
  - The `/` route is the place for a header; the OAuth callback page has inline scripts.
  - The pywebview 5.4 bridge handlers check no frame (reachability from a frame is unverified, so it goes to leg 1).
  - `webkitgtk_probe.py` is plain WebKit2, with no pywebview.
  - `windows_test_copy.py --cdp-port` allows Playwright CDP into the real WebView2.
  - The hosted macOS run cannot read the DOM.

---

## Leg Progress

*(none yet)*

---

## Flight Director Notes

### Design review cycle 1 (Architect, Opus, 2026-11-09): needs rework
Probes are in the scratchpad (`arch/p1-p4.py`). Everything below was folded into `flight.md`.

**High-severity findings and fixes:**
- **The spec was stale against the operator's Pause decisions.** Fix: DD7 lifecycle states, DD8 pause, the mission criterion amended.
- **WebRTC STUN reached a UDP listener in all engines**, even with `webrtc 'block'`. Fix: DD6, the prelude neuters it; the escape sink gains UDP.
- **On WebKit, `history.back()` in the frame moved the page's route.** Fix: DD6, the prelude neuters the History methods.
- **DD14's eval order was self-contradictory.** Fix: DD16, the A1 → B1 → A2 → B2 order with named commits, and the old-four compare.

**Medium-severity findings and fixes:**
- Chromium focus theft → DD10's focus guard.
- `execCommand('copy')` pastejacking → DD6.
- Crash-record false positives (`pagehide`, multiple tabs, suspend) → DD9: per-page keys, a stale rule, the tick reset, and `pagehide` measured in leg 1.
- The load count depends on insertion order → DD2: `srcdoc` is set before insert.
- Undefined lifecycle states → DD7.
- No macOS bridge probe → DD13 and leg 6.

**Low-severity findings and fixes:**
- The OAuth citation corrected to `:187`.
- `sweep()` drops only once-connected instances.
- WebView2 isolation recorded per runtime version.
- Size messages coalesced.
- Title spoofing and Tab trapping documented as residuals.

**Suggestions taken:**
- Leg 3 is split into `widget-control` and `widgets-in-chat`, giving seven legs.
- DD14's guard notes: non-factory helpers, load order, the `visualNotice` row and its contract file, lane lists, the paired `visibilitychange` listener.
- The prelude is a pinned constant.
- Per-leg re-verification of external prerequisites.

**Architect's questions, answered by the Flight Director:**
1. The re-baseline comes first *within* the eval leg, before the widget text, which is the operator's stated meaning.
2. The cap of three counts running frames; the loaded ceiling is eight.
3. Neutering in the prelude is adopted as defence in depth, with residuals documented. It is presented to the operator.
4. Yes: the stall detection and the crash record cover every loaded frame, paused ones included.

Mockup board 6 (Details) was added for the surfaces the review listed.

**Operator, mid-review:** "looks good to me so far", on boards 1-5.

**Operator, after the rework:** "all good". This approves board 6 and the three explicit OKs (the chart placeholder unchanged, the measured text width, the widened hint).

### Design review cycle 2 (Architect, Opus, 2026-11-09): approve with changes
Probes are in the scratchpad (`arch2/`). Everything below was folded into `flight.md`. This was the second and last design cycle; nothing is left unresolved, so there is no escalation.

**High-severity findings and fixes:**
- **DD10's focus guard could not work as written.** On a steal the parent page gets no `focusin`, and a click inside the frame sends no `pointerdown` to the parent. Fix: a `focusout`/`blur` mechanism, a discriminator probed and decided in leg 1, removal after more than 3 restores in 1 s ("kept taking focus" notice), and the leftover Chromium keystrokes documented as a residual.
- **WebKit `<link rel=preconnect>` in the frame opens TCP to any host.** Fix: DD6 states it as an open item; the sink gains TCP and DNS; leg 1 measures it in real WebKitGTK; the gate chooses a mitigation.

**Medium-severity findings and fixes:**
- Leg 1 gated on focus, which lands in leg 3 → focus is measured, not gating, in leg 1.
- The B2 compare of the old four was impossible, because the fingerprint covers the whole directory → widgets get their own scenario set, `evals/widgets/`.
- `SCORING_DIGESTS` changes in A1 → operator approval at A1.
- A1 changes prompt text → B1 compares against the m35 baselines first.
- Hidden-tab throttling and suspend → checks suspended while hidden, a reset on visible, suspend measured on Windows.
- The unbounded GTK `evaluate_js` could hang Quit → the fallback uses a bounded call; leg 1 measures whether the key is gone at the next launch.

**Low-severity findings and fixes:**
- DD7's leftover pre-pause text → oldest-started; resume order; the ceiling fallback; the waiting card; the Chats-destination note.
- Reduced motion → one animation-frame round passes.
- DD13 → the desktop test-patch rule.

**Suggestions taken:**
- The heartbeat timer ids are protected from `clearTimeout`/`clearInterval`.
- Only `performance.now` and animation-frame timestamps are offset by a pause.
- The pause-bypass residuals are named.
- Leg 1 pins the prelude order with an empty pause slot.

**Question answered:** leg 6 must not widen `release.yml`'s `macos_mode` choices (pinned by `tests/test_release_workflow.py`).
