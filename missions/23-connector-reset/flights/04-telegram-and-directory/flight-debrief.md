# Flight Debrief: Telegram and the Name Directory

**Date**: 2026-09-02
**Flight**: [Telegram and the Name Directory](flight.md)
**Status**: landed
**Duration**: 2026-09-02 (single continuous orchestration session, planning → HAT)
**Legs Completed**: 4 of 4

## Outcome Assessment

### Objectives Achieved
Everything the flight objective named, plus one HAT-promoted feature: Telegram as the second real platform (a 575-line long-poll client incl. formatted rendering, on the existing httpx, through the unchanged Flight 2 contract); the mission's final authorized migration (v39: type CHECK + `connector_directory`) executed and proven idempotent/rewind-tolerant; the name directory — passively populated, connector-level scoped, admission-gated for peers and deliberately ungated for channels — with a lookup tool the model chains into sends, proven at the model floor by the `directory-lookup-send` stub gate (3/3) and live on BOTH platforms from one console chat in the HAT; the `keying_to_target` debt closed before a third copy existed; directory-named session titles; the per-connector setup help file; and, from the HAT, deterministic markdown→Telegram-HTML rendering with a structural no-raise guard and a mechanical plain-text fallback.

### Mission Criteria Advanced
- **Telegram round-trip through the same contract; additive-seam (reworded)**: **MET, with the strongest evidence yet** — DD-1's (a)–(g) enumeration names every shared-code touch and the actual diff touches exactly those files and nothing else outside the subpackage/tests/docs; each touch is small and platform-agnostic. The reworded criterion (named/minimal/platform-agnostic, not "zero touches") proved to be the right bar. ✔
- **Name-directory send targeting (RQ11)**: observed live, multi-connector (Telegram + Discord + stub), ambiguity surfaced not guessed. Operator verdict: **validated as designed**. ✔
- **A live HAT for Telegram** (criterion 10's Telegram half): executed from the operator's own account. ✔
- **Budgets**: connector Python **~2,964 / 3,000** after the HAT feature (review-corrected arithmetic — see Process); JS +0 this flight (generic form covered Telegram; ~720/1,000 mission). ✔
- Migration budget now definitively closed at v39 (RQ10). ✔

## What Went Well

- **The Flight 3 lessons transferred**: the three review-time questions, run as a mandatory charter at flight design, found **zero DD-to-DD contradictions** (vs. three discovered live in Flight 3) and traced both happy paths clean — the reply hop correctly reused Flight 3's DD-10 unmodified. This flight had exactly ONE live-only finding (raw markdown in Telegram, a perception gap) versus Flight 3's three mechanism gaps.
- **Both review tiers earned their keep, on different defect classes** (operator ruling: keep both). Flight-level caught a contract-shape error (generic `platform_id` breaking literal copy-the-ids at the floor). Leg-level caught wiring gaps flight-level structurally can't see: an inert tool (no `_TOOL_CLASSES` entry — every pin test would fail), a silently-dropped JOIN column (pydantic `extra="ignore"` — green SQL, no-op feature), the disabled→disabled-class rename claim that was false TWICE (the cache survives reconnects by contract).
- **Front-loading the shared surface into one high-risk leg paid off**: leg 1 absorbed 100% of the shared-code risk; leg 2 was then honestly tierable LOW (zero shared touches, twice-proven template) and landed clean without per-leg review; leg 3's failures were cleanly attributable.
- **The stub gate before the HAT** (RQ8's lesson applied up front) surfaced the floor-model patterns cheaply — connector-id-vs-type confusion, one elided argument — and proved authorization contained every invented target before any platform effect, in every attempt.
- **Zero Developer stalls in legs 1–2** (two in legs 3/HAT — eleven mission-wide); the flight-end Reviewer independently re-derived the budget and corrected my arithmetic.
- **The HAT's fix-vs-feature gate worked as designed**: the rendering request was called a FEATURE out loud, went through a scoped review that materially strengthened it (structural no-raise guard, broad fallback healing length overflow, fixture capability, bullet/italic collision), and shipped with independent review — in one session.
- **Plugin-boundary rendering adaptation is a clean precedent** (Architect): per-platform send-side degradation without touching the contract's canonical text — the template for the next platform's formatting quirks.

## What Could Be Improved

### Process
- **Named findings must become squawks, every time** (both interviews flagged it): this flight logged ONE squawk (0037) and left four named, small, tracked-worthy items as flight-log prose — the unclamped 429 `retry_after`, `LIKE` wildcard escaping, the group-DM capture test gap, and the `connector_id`-description sharpening the gate's own findings called for. Flights 1–3 converted 4–6 each. Corrected in this debrief (squawks 0038–0041).
- **Budget arithmetic must be re-derived, not summed**: my per-leg running total (2,894/106 slack) double-counted leg-1/leg-3 overlap on shared files; the true figure was 2,739/~261 (`git diff --numstat` against the flight's start commit). Conservative direction, but the FD flew a wrong number into leg-4 planning. Rule: when legs touch overlapping files, the budget authority is the diff, not the sum.
- **The personal-account near-miss**: the FD drove the operator's PERSONAL Telegram account for several test messages under the mistaken premise (from an earlier note) that it was a dedicated test account. Benign, self-corrected on the operator's flag, continued only with explicit permission — but the rule is clear: **confirm whose account a logged-in browser session belongs to before driving it**, and record it in the environment note with the operator's own words, not an inference.
- **Behavior-spec authoring calibration** (recurring from Flight 3): the stub gate's step 2 needed a sanctioned re-author — a 120s window calibrated to the happy path (floor-model recovery loops legitimately run 160–290s) and a "top-level `[platform-send-ok]` bubble" clause that was an FD spec error (promotion is gated on platform-bound sessions by Flight 2's design; the step runs in an unbound chat). Both belong in AUTHORING.md as rules, not rediscoveries.
- **Subagent stall pattern** persists (two this flight; eleven mission-wide); the resume-with-foreground-directive recovery remains the standing play.

### Technical
- **Peer/channel admission asymmetry is sound but not yet doctrine** (Architect): "rooms are not people" holds for Discord and Telegram; a future platform where "channel" can mean a private 1:1 needs the rule stated mechanically before its plugin decides. → mission debrief / next platform's flight design.
- **No automated Telegram live gate can exist** (bots cannot see other bots' messages) — the fixture + manual HAT are Telegram's permanent coverage; the fixture is protocol-complete (real offset semantics) but structurally cannot see rendering, which is exactly what the HAT found.
- **Telegram subpackage at 575** — the rendering feature overran the 350 target by design under the standing ruling; any future touch in the subpackage should treat it as at-ceiling.
- Debt now tracked: squawk 0037 (token in httpx log URLs — the Bot API's token-in-path shape), 0038–0041 (below).

### Documentation
- AUTHORING.md needs: the unbound-session promotion rule; generous recovery-loop windows on first draft; the "model-tier finding" confound now has TWO flights of instances (F3: confirm-before-acting; F4: id-vs-type confusion, elided arguments).
- `agents.md` could name the budget-driven-closure pattern (nested `_run` closure, dataclass client) leg 2 used to fit its ceiling, if it recurs.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| v39 authorized mid-planning (RQ10) — a second migration step | `'telegram'` cannot exist without a CHECK change; v38 spent | No — the ledger closes at v39; a mission-owner decision, correctly escalated before spec text |
| Directory joined the mission (RQ11) | Operator: validate multi-connector architecture | Yes — the two-platform proof was the right forcing function |
| Budget targets overrun (shared 607 vs 350; Telegram 575 vs 350) | House doc density + a HAT-promoted feature; reported per the standing ruling | Yes — sub-buckets are targets; the mission ceiling is the trigger; re-derive from the diff |
| Stub-gate row re-authored (window, final-state outbound, promotion clause) | Happy-path calibration + an FD spec error | Yes — AUTHORING.md rules (above) |
| Model rebind not needed this flight | gpt-oss:20b was the floor from the start | Confirms the F3 posture |
| Leg 2 skipped per-leg review (LOW tier) | Zero shared touches; template twice-proven; protocol facts pre-validated | Yes — the tiering rule applied honestly, with rationale recorded |

## Key Learnings

1. **Two review tiers, two defect classes.** Flight-level review catches design contradictions (zero this flight, thanks to the F3 questions); leg-level review catches wiring completeness — reachability of a registration seam, model fields matching enrichment columns, claims about caches that survive what you think they don't. Both are cheap relative to shipping an inert tool.
2. **Three NEW review-time questions** (Architect), to join Flight 3's three: (a) *reachability*: "for every new tool/capability, trace its registration seam — is it reachable, not just implemented?"; (b) *permissive-parsing drop*: "for every enrichment added to an existing return type, does the model declare a field for every returned column?"; (c) *budget re-derivation*: "when legs overlap on files, is the running total from `git diff --numstat` against the flight's start commit, not a hand sum?"
3. **The additive-seam criterion, reworded, is the right bar** — and Telegram met it more cleanly than Discord met the original. Naming every shared touch in the introducing DD turned out to be both achievable and auditable.
4. **A floor-model agent needs tools whose error messages steer** — every recovery in the gate was driven by `[error]`/`[no-match]` text, and every bad guess was contained by authorization. Design tools for the model that flails, not the one that doesn't.
5. **Perception gaps survive protocol-complete fixtures**: raw markdown in a real Telegram client was invisible to a fixture that models Telegram's offset semantics perfectly. Live HATs stay mandatory for anything a human reads.

## Test Metrics

`make test-unit` (debrief run): **3,910 passed, 10 skipped, 553 deselected, 17 warnings, 454.55s**. Studio lane: **147 passed / 3 skipped, 271.18s**, no flake this run (squawk 0035's standing disposition on file). Trend: F1 3,561 @ 352s → F2 3,669 @ 398s → F3 3,758 @ 456s → **F4 3,910 @ 455s** — the mission's largest test-count jump (+152) at FLAT wall time, breaking the count-scales-time trend: the new tests are fixture-mocked (httpx `MockTransport`, in-memory repositories) with no network/subprocess I/O, unlike F3's gateway-adjacent fixture work. Studio lane −42s.

## Recommendations

1. **Mission debrief → mission-control**: the six review-time questions (F3's three + this flight's three); the third apparatus axis; the AUTHORING.md rules (unbound-session promotion; recovery-window calibration; the two-flight model-tier-finding confound); the "confirm whose account" rule for browser-driven HATs; budget re-derivation from the diff.
2. **Before the next platform**: state the peer/channel admission doctrine mechanically (rooms vs. people), so a plugin for a platform with 1:1 "channels" can apply it without a ruling.
3. **Turnaround**: squawks 0037–0041 (token logging, 429 clamp, LIKE escaping, group-DM capture test, `connector_id` description) — all routine, one batch.
4. **Flight 5 (optional alignment)**: with all four mission-carried criteria advanced, the remaining mission criteria to verify at mission-debrief time are the closure/docs/packaged-build items (criteria 1, docs, Concourse) — a closing pass should audit those rather than add features.

## Action Items
- [x] Squawk 0037 — Telegram token in httpx INFO log URLs (logged mid-HAT)
- [x] Squawk 0038 (logged) — clamp `retry_after` from 429 responses in `telegram/_api.py`
- [x] Squawk 0039 (logged) — escape `%`/`_` in `ConnectorDirectoryRepository.search`'s LIKE query
- [x] Squawk 0040 (logged) — Discord group-DM (`type=3`) channel-name capture test gap
- [x] Squawk 0041 (logged) — sharpen `find_platform_destination`'s `connector_id` description ("opaque id, never the platform type")
- [ ] Mission debrief: carry the methodology items above to mission-control
- [ ] Next-platform flight design: admission-asymmetry doctrine
