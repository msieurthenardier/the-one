# Flight Log: Visuals on Chat Platforms

**Flight**: [Visuals on Chat Platforms](flight.md)

## Summary
Planned 2026-11-11. Not yet started.

---

## Leg Progress

*(none yet)*

---

## Decisions
Runtime decisions not in original plan.

### Planning decisions (2026-11-11, operator)
**Context**: Flight 3 planning interview.
**Decision**:
- Fake both platforms, with no real bots ("we can't really control what they see, we can only control what we send").
- Light theme for images.
- Text, then images.
- Mockup A: the 📊 marker and the 🧩 widget note.
- The block as code on failure.
- No HAT.
**Impact**: DD2, DD5, DD6, DD7. The mission's "Charts reach chat platforms as images" criterion is backed by a round trip against fake platforms instead of a live connector, recorded as an amendment in `mission.md`.

---

## Deviations
Departures from planned approach.

*(none yet)*

---

## Flight Director Notes
- 2026-11-11: Planning. The code recon was delegated to one Explore agent, and its findings are folded into the flight's Citation Audit (verified at `6d22eabc`). No HAT leg (operator choice). The mockup was approved as option A.
- 2026-11-12: Design review cycle 1 (Architect, Opus) returned "approve with changes", with 3 high, 9 medium and 6 low issues. All were applied:
  - **High:**
    - The text layout engine is pinned to BASIC (RAQM depends on the host's FriBiDi; measured as AV 16.0 vs 14.75).
    - `send_visual` carries per-image fallbacks, and `VisualUploadError` moves the whole-message resend into the shared helper.
    - An operator-approved sample sheet of the chart images is Leg 1's exit gate.
  - **Medium:**
    - `mission.md` is amended for the fakes.
    - The stub's images go in a dict keyed by record index, and the `images` key appears only on records that have images.
    - The fake's protocol details are listed (`GET /channels/{id}`, READY `user.id`, heartbeat ACK, RESUME, Telegram offset and long-poll).
    - Behavior-test step 9 sets `max_iterations` to 1.
    - `OutboundImage` lives in `visuals` and is re-exported by `connectors`.
    - Plain replies stay byte-identical.
    - Nested blocks are a residual (operator choice, 2026-11-12).
    - The three-platform check moves to Leg 2.
    - The time bound is now tested on a synthetic at-limit spec.
  - **Low:** the font lock, lazy Pillow import and an AST guard, citation fixes, no re-send after a transport error, and an upload 429 clamp of 10 s.
  - **Suggestions taken:**
    - The seam lives in the lifespan with keyword `register()` URLs.
    - A shared tick corpus.
    - Palette constants pinned to `tokens.css`.
    - Pixel-hash comparisons.
    - Leg 4 split into `fake-platforms` and `seam-and-round-trip`.
    - The browser-lane check is dropped (`contracts-chat` stays, for the tick corpus).
    - The fonts move to `the_one/visuals/fonts/`.
- 2026-11-12: Design review cycle 2 (Architect, Opus) returned "approve with changes", with 2 high, 5 medium and 5 low issues. It confirmed the cycle-1 fixes are consistent and the citations hold on `f76efdd3`. All issues were applied; this was the last cycle allowed, and nothing needed escalating.
  - **High:**
    - `evals/checks.py` is frozen (`tests/test_evals_freeze.py`), so it stays untouched, with a parity test against `blocks.py`.
    - The tick corpus shares only the width-independent y ticks; each renderer pins its own x-label thinning.
  - **Medium:**
    - Text is measured in design units, not BASIC's hinted advances (which vary with the FreeType build), so the doctor gate's width is a property of the font file.
    - The stub's images ride on a `tuple` subclass record.
    - The plan is segment-based, with `render(drawn)`.
    - A per-call 429 policy, including the fallback resend, and a 45 s Telegram photo budget against its 110 s liveness window.
    - Transport errors are mapped on both platforms, and 5xx or timeouts are never re-sent.
  - **Low:**
    - Behavior-test stale text.
    - The `visuals` docstring and AST guard.
    - `packaging/windows/README.md` and an ASCII-only gate detail.
    - `gateway_url` passed explicitly, with loopback IP literals only.
    - The fallback log line, and step 8 injecting a 413.
  - **Suggestions taken:** a CJK title on the sample sheet, the fake's tests on port 0, timing-test headroom, and a Leg 6 start check that agent and provider changes apply per inbound message.
- 2026-11-12: PR #365 is merged (`f76efdd3`). The branch `flight/03-visuals-on-chat-platforms` was created from `origin/main` with no upstream.
- 2026-11-12: The operator approved the final spec (Phase 6). Status: `ready`.
