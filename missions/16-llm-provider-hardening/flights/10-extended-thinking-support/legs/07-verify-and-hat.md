# Leg: verify-and-hat

**Status**: in-flight
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

> **Interactive / HAT leg** — run by the Flight Director *with* the operator, one step at a time.
> No autonomous Developer/Reviewer agents. Issues found are fixed inline (a Developer may be
> spawned for a code fix), then the failing step is re-verified before moving on.

## Objective

Verify extended thinking end-to-end on a **live Anthropic (adaptive) model** and tune the
operator-facing UX: run the `extended-thinking-tool-turn` behavior test (the acceptance gate for
the two mission thinking criteria), then a short guided HAT of the disclosure + admin toggle.

## Acceptance Criteria (verification steps, not implementation)

- [ ] **Environment ready:** the app is running + reachable; an Anthropic key is stored; an agent
      uses the Anthropic provider on a **Sonnet 4.6+** model with the **Extended thinking** toggle
      **ON** and **≥1 tool** enabled.
- [ ] **Behavior test PASS:** `/behavior-test extended-thinking-tool-turn` passes — a live
      thinking+tool turn completes with no API error, its **follow-up** (tool-result) turn also
      completes (the criterion-#1 witness that signed thinking was replayed correctly), the
      thinking `<details>` disclosure renders collapsed with reasoning text, and it survives a
      chat reopen (history replay).
- [ ] **Disabled variant:** with the toggle OFF, the same prompt completes normally with no
      thinking disclosure (the toggle truly gates enablement).
- [ ] **Mixed-session variant (DD8):** turning the toggle OFF mid-chat (after thinking+tool turns)
      and continuing completes with **no API error** (stored signed blocks are stripped, not
      replayed onto the thinking-off request).
- [ ] **Guided HAT:** operator is satisfied with the disclosure UX (collapsed default, placement,
      readability) and the admin toggle; any tweaks applied inline and re-verified.
- [ ] **Full suite green** (minus the known aiosqlite teardown flake); docs updated as needed
      (the thinking-field convention note in `agents.md`; the behavior-test spec marked `active`).

## Run Notes

**2026-07-03 — HAT setup (app on :8485). Three UX/consistency findings on the Leg 06 toggle
(fixing inline before the behavior test):**
1. The Extended-thinking control should be an **iPhone-style toggle switch**, not a plain
   checkbox.
2. The toggle is **per-provider, not per-model** — operator accepts per-provider, but the tooltip
   should say **"a model"** (not "the model") since a provider serves many models.
3. The info icon should follow the established **`label (i) field`** pattern from other screens
   (Leg 06 mirrored `num_ctx`, which puts the icon *after the input*).

_Fix + re-verify below, then proceed to the behavior test._

## Files (verification only — no planned source changes unless a HAT fix is needed)

- Behavior-test spec: `tests/behavior/extended-thinking-tool-turn.md` (run via
  `/behavior-test extended-thinking-tool-turn`; run log lands at
  `tests/behavior/extended-thinking-tool-turn/runs/{ts}.md`).
- Any inline HAT fix touches the relevant leg's files (adapter / web UI / admin) and is committed
  separately (no amend).

---

## Post-Completion Checklist

- [ ] All verification steps pass (or failures dispositioned with operator sign-off)
- [ ] Behavior-test run log committed; flight-log Run Notes reference it
- [ ] Leg status → `completed`; checked off in `flight.md`
- [ ] Flight status → `landed`; flight checked off in `mission.md`
- [ ] Mission criteria #1 (thinking+tool turn) + the `ThinkingPart` criterion checked off
- [ ] Commit; then draft PR marked ready (or opened) per the git workflow
