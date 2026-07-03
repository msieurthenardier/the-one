# Leg: verify-and-hat

**Status**: completed
**Flight**: [Extended-Thinking / Reasoning Support (A1)](../flight.md)

> **Interactive / HAT leg** — run by the Flight Director *with* the operator, one step at a time.
> No autonomous Developer/Reviewer agents. Issues found are fixed inline (a Developer may be
> spawned for a code fix), then the failing step is re-verified before moving on.

## Objective

Verify extended thinking end-to-end on a **live Anthropic (adaptive) model** and tune the
operator-facing UX: run the `extended-thinking-tool-turn` behavior test (the acceptance gate for
the two mission thinking criteria), then a short guided HAT of the disclosure + admin toggle.

## Acceptance Criteria (verification steps, not implementation)

- [x] **Environment ready** (FD-verified via read API, 2026-07-03): app up on :8485; Anthropic
      provider `config.thinking_enabled == True`; agent "Antropic" on `claude-sonnet-5`
      (adaptive-capable), `enabled_tools=None` → inherits all 24 enabled tools (incl.
      `python_exec`/`shell`). UI polish committed (`7735b88`), operator-approved. Chosen live
      prompt: the **bill-split** ("$247.83 among 7 with 18% tip — think it through, then use a tool
      to compute the exact per-person amount") — induces reasoning + a `python_exec`/`shell` tool
      call in one turn.
- [x] **Behavior test PASS:** `/behavior-test extended-thinking-tool-turn` → **PASS 6/6** (run
      `2026-07-03-12-14-26`). Live thinking+tool turn + its follow-up complete with no API error
      (criterion #1); the thinking `<details>` disclosure renders collapsed with reasoning text that
      matches persistence; survives a chat reopen; multi-turn replay stable. Surfaced + fixed two
      live defects (stale backend restart; `display:"summarized"` — see Decisions).
- [~] **Disabled variant:** live run **skipped** (operator, 2026-07-03) — covered by the hermetic
      Leg 03 test (`thinking_enabled=False` → no `thinking` kwarg, disabled-passthrough).
- [~] **Mixed-session variant (DD8):** live run **skipped** (operator) — covered by the hermetic
      Leg 04 strip-when-off tests (`thinking_active=False` → thinking stripped, no replay onto the
      thinking-off request).
- [x] **Guided HAT:** operator approved the disclosure UX + the admin toggle; the three toggle UX
      findings (iPhone switch / `label (i)` icon / "a model" tooltip) were fixed inline and
      re-verified (commit `7735b88`).
- [x] **Full suite green** (minus the known aiosqlite teardown flake); behavior-test spec marked
      `active`; thinking-field convention noted in `agents.md`.

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

**2026-07-03 — Behavior-test run #1 (`2026-07-03-12-14-26`): stale-backend environment finding
(NOT a code defect).** CP1 (chat loaded) PASS; CP3 (thinking+tool turn completes, no error, no
Anthropic 400) PASS — but two probes (bill-split + a reasoning-heavy compound-interest prompt)
both produced **zero thinking blocks, zero thinking tokens, and no `.thinking-disclosure`** in the
DB and DOM. Root cause found by the Orchestrator: the `:8485` dev process (pid 2094218) started
**Jul 2 09:54**, ~14h BEFORE the flight-10 backend code was written (anthropic_provider.py/codec.py/
app.py mtimes Jul 2 23:26–23:55; committed `b2785d9` Jul 3 00:48), with **no `--reload`**. So the
running app served the NEW static frontend (JS/CSS reload on browser hard-refresh → the toggle
appeared + saved `thinking_enabled=true`) while executing the OLD backend Python (no adaptive
enablement, no capture, no codec thinking round-trip). CP3's "no 400" was trivially safe precisely
because the stale backend never sent thinking → no signed blocks to replay. **Resolution: restart
the dev instance to load the flight-10 backend, then re-run.** Methodology lesson (→ debrief): a HAT
against a long-lived dev process must confirm the BACKEND is current — static assets reload on
browser refresh and mask a stale Python process; consider `--reload` for dev, or a startup
version/build log line. The flight CODE is correct (unit + browser suites green); this was purely
an environment staleness in the operator's running instance.

**2026-07-03 — Behavior-test run #1 continued (after :8485 restart): backend replay CONFIRMED
live; disclosure-empty root-caused to `display:"omitted"` default → inline fix.** On the fresh
backend, a reasoning+tool turn (compound-interest) produced **signed thinking blocks on the 3
tool_use turns, captured + persisted + replayed with NO Anthropic 400** — mission **criterion #1
(thinking+tool replay) is LIVE-CONFIRMED** on Sonnet 5. BUT the web-UI disclosure still didn't
render. Diagnosed in layers: (1) NOT stale assets — `renderThinking` + `.thinking-disclosure` CSS
are loaded in the browser; (2) DB check: the persisted thinking blocks have a **384/336/628-char
signature but ZERO `thinking`-text** → `thinking_display_text` correctly returns `""` → no event →
no disclosure (the display path is correct given the data). (3) **Root cause (confirmed vs
Anthropic docs):** on Sonnet 5 / Opus 4.8/4.7 / Fable 5, `thinking.display` **defaults to
`"omitted"`** (empty `thinking` text; signature-only for replay). The app sent `{"type":
"adaptive"}` with no `display` → signature-only blocks. **Fix (inline HAT):** request
`{"type": "adaptive", "display": "summarized"}` so the model returns readable summarized reasoning
text → the disclosure populates. Signature is identical across display modes (docs) → replay/
capture unaffected; no per-model branching (valid on all adaptive models). Fix + test update in
progress; backend to be restarted (Python changed) and the turn re-verified.

**2026-07-03 — Behavior test PASS 6/6; flight verified end-to-end.** After the `display:"summarized"`
fix + backend restart, the full spec re-ran clean on session `04cb7a2732b5`: CP3 (turn completes,
no 400) PASS; CP4 (disclosure renders collapsed with reasoning text matching persistence, a11y)
PASS; CP5 (all four present + telemetry non-zero) PASS; CP6 (reload → history replay re-renders the
disclosure from persistence, byte-identical text) PASS; CP7 (second thinking+tool turn — multi-turn
signed-replay stability across accumulating history, no 400) PASS. Both Mission 16 extended-thinking
criteria confirmed live on `claude-sonnet-5`. Run log: `runs/2026-07-03-12-14-26.md`. Optional
disabled + mixed-session(DD8) variants skipped per operator (hermetic-unit-test-covered). Leg 07 →
`completed`; flight → `landed`.

## Files (verification only — no planned source changes unless a HAT fix is needed)

- Behavior-test spec: `tests/behavior/extended-thinking-tool-turn.md` (run via
  `/behavior-test extended-thinking-tool-turn`; run log lands at
  `tests/behavior/extended-thinking-tool-turn/runs/{ts}.md`).
- Any inline HAT fix touches the relevant leg's files (adapter / web UI / admin) and is committed
  separately (no amend).

---

## Post-Completion Checklist

- [x] All verification steps pass (behavior test PASS 6/6; optional variants skipped per operator,
      unit-covered)
- [x] Behavior-test run log committed (`runs/2026-07-03-12-14-26.md`); flight-log Run Notes reference it
- [x] Leg status → `completed`; checked off in `flight.md`
- [x] Flight status → `landed`; flight checked off in `mission.md`
- [x] Mission criteria #1 (thinking+tool turn) + the `ThinkingPart` criterion checked off in `mission.md`
- [x] Commit (`5e16796`); **draft PR #149** opened per the git workflow (ready-for-review after debrief)
