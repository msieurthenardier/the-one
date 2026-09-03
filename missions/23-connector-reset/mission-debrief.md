# Mission Debrief: Connector Reset

**Date**: 2026-09-03
**Mission**: [Connector Reset](mission.md)
**Status**: completed
**Duration**: 2026-08-30 (planning) → 2026-09-03 (final turnaround)
**Flights Completed**: 4 of 4 (Flight 5 alignment not needed — each flight carried its own HAT)

## Outcome Assessment

### Success Criteria Results

Audited by the mission-debrief Architect against the code and repository state, not against the flight logs' self-reports (which nonetheless checked out).

| Criterion | Status | Notes |
|-----------|--------|-------|
| `discord.py`/`aiohttp` absent from the runtime closure; no chat SDK in base deps | **met** | `pyproject.toml` carries only a retirement comment; `uv.lock` has zero `discord*`/`aiohttp` entries |
| Discord live round-trip (DM/@mention reply, agent-initiated send, auto-resume) | **met** | Flight 3: `discord-live-round-trip` 6/6 + guided HAT; resume proven forensically (the `/users/@me` re-identify signature) |
| Telegram round-trip; additive seam (reworded 2026-09-02) | **met** | Flight 4: DD-1's (a)–(g) shared-touch enumeration matches the diff exactly — cleaner than Discord met the *original* wording |
| Name-directory send targeting (added 2026-09-02, RQ11) | **met** | Stub gate 3/3 at the model floor; HAT: name-addressed sends to Telegram AND Discord from one console chat |
| Chat UI unified history; operator messages never reach the platform | **met** | Flight 2 behavior test 7/7; the visibility semantic retained, not rebuilt |
| Credentials Fernet-encrypted, masked, rotation-enrolled | **met** | Flight 2; rotation now restarts listeners (caught and fixed in-flight) |
| Flat allowlist + pairing; silence for unknowns; no gate/ACL/queue | **met** | Grep-clean across the five docs for the forbidden concepts; verified live three times (stub, Discord, Telegram HATs) |
| One default agent + optional channel map; no routing engine | **met** | — |
| Single migration retiring legacy tables/columns/rows; clean upgrade | **met** | v38 (Flight 1, 84/84 migration tests incl. chained legacy path); plus v39 authorized narrowly (RQ10) and scoped exactly — the ledger closes at 39 |
| Connectors ≤3,000 Python / ≤1,000 JS | **met — at the edge** | **2,970 / 3,000 Python** (package 2,553 + tools 417); JS ~720 / 1,000 *(see the correction annotation below)*. The Python ceiling is now a live constraint, not a margin |
| Tests pass; deletions not skips; `discord_hat` gone; new live HATs exist | **met** | 3,910 unit + all lanes; marker and target gone (comment remains); Discord and Telegram HATs executed. One cosmetic leftover: root-owned stray `.pyc` files in the deleted `tests/live/discord_hat/` dir (untracked, gitignored, un-removable from this session) |
| Five docs describe the new contract with no stale references | **met** (one completeness gap fixed in this debrief) | Forbidden-term grep clean; the top-level README's architecture paragraph was two facts behind (missing the third tool; "replies never auto-forward" predated DD-10) — corrected in this debrief's commit |
| Windows packaged build + smoke with the smaller closure | **met on Flight 1's evidence** (operator ruling) | Flight 1 built and smoke-passed (installer 62→59 MiB); the pipeline auto-triggers on every green `main`; later builds were not re-confirmed from this session (Concourse unreachable at debrief time) — the operator accepted Flight 1's proof plus the auto-trigger design as sufficient |

### Overall Outcome

**Achieved.** The operator's verdict on the outcome statement: "exactly right." 9,050 lines of platform-agnostic machinery became 2,970 lines doing one job — a 67% reduction — while *adding* a second platform, a name directory, and formatted rendering the old system never had. The daily driver works on Discord and Telegram with zero chat SDKs in the closure. The contract established in Flight 2 was genuinely frozen through Flights 3–4: `PermanentConnectorFailure` (born in Flight 3 under live pressure) was reused verbatim by Telegram; the auto-reply fallback (DD-10, also born live) carried Telegram's replies with zero platform-specific code; `keying_to_target` was extracted before a third copy could exist. The mission also caught one of its own success criteria being wrong (the additive-seam wording) and fixed the criterion rather than gaming it.

Stakeholder value: the operator paired their own Telegram account with their bot, watched replies arrive formatted, and name-addressed people across two platforms — the "same bot, same channels, same private console" promise kept, at a third of the weight.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1 — Remove | completed | −67,382 lines; the 9,050-line subsystem deleted with reverse-dependency recon as step zero; v38; Windows build proven on the smaller closure; the feared split trigger never fired |
| 2 — Channel Contract | completed | The 1,060-line core (Protocol pair, manager, inbound pipeline, stub, send tool); stub behavior test 7/7 on run 2 after four real fixes; the dual-gate seam convention |
| 3 — Discord Client | completed | Hand-rolled Gateway v10 + REST (767 lines); the carve-out (27 sanctioned loop lines); `enabled`; live gate 6/6 after THREE mid-run design findings (DD-4 amendment, DD-10, DD-11); guided HAT |
| 4 — Telegram + Directory | completed | v39; the directory + lookup chain (stub gate 3/3); Telegram long-poll (575 lines incl. rendering); HAT from the operator's own account with cross-connector name sends; the Flight 3 review questions applied — zero DD contradictions on paper |

### Flight Patterns
- **Every flight's live/behavior gate found something paper review missed** — the operator's named biggest surprise. Flight 2: four attribution/visibility fixes. Flight 3: three design gaps (an apparatus the pipeline dropped by design; no reply mechanism; undiscoverable targets). Flight 4: one perception gap (raw markdown) and a spec miscalibration. The gates were never noise: the Validators' closing assessments in both live runs record zero apparatus-noise verdicts.
- **Paper reviews caught a different class**: sequence-number omission, a listener restart on disabled connectors, an unimplementable test re-aim, an inert tool, a silently-dropped column, a cache-lifetime claim false twice. Neither tier substitutes for the other (operator ruling: keep both).
- **The mid-run amendment loop held under pressure** three times in Flight 3 and once in Flight 4 — operator decision, DD amended in place with rationale, superseded contracts re-authored deliberately, sanctioned rerun — with zero silent breakage of prior specs.
- **Friction that recurred**: the subagent stall (eleven occurrences mission-wide, always at a long test run, always recoverable by a resume-with-foreground directive); budget arithmetic that needed independent re-derivation twice; findings left as prose instead of squawks (Flight 4, corrected in its debrief).

## What Went Well

- **Deletion done right.** Flight 1's reverse-dependency recon and "no tracked files / zero LOC" verification language prevented the dangling-reference class entirely, and the split trigger it feared was pre-defused by planning.
- **A contract that held.** Two structurally different platforms (push gateway, long-poll) through one frozen Protocol; every shared-code touch named in a DD; contract-level additions (`PermanentConnectorFailure`, DD-10, `peer_username`, `keying_to_target`) reused rather than duplicated.
- **Mechanical fallbacks over prompt engineering**, applied three times (DD-5 visibility seeding, DD-10 auto-reply, DD-11 session-default targets) — each proven by a gate against a floor-model agent whose flailing was steered by tool error messages and contained by authorization every time.
- **The methodology learned inside the mission.** Flight 3's three review-time questions were applied in Flight 4 planning and found zero contradictions on paper. Flight 4 then contributed three more. The additive-seam criterion was reworded on evidence.
- **Squawk discipline (mostly).** 41 squawks over the mission, four turnarounds, every one independently reviewed — even the bulb swaps.

## What Could Be Improved

- **Too many decision points for the operator** (interview). The functional decisions were theirs and welcome (RQ8–RQ11, gate dispositions on model behavior, HAT verdicts); the noise was elsewhere: "log these as squawks?" (just log them — cheap and reversible), and highly technical calls (candidate key shapes, JOIN vs. per-row lookup, fixture mechanics) that the FD and Architect can settle with a recorded rationale. **Rule going forward: functional → operator; technical → FD + Architect, recorded; squawk logging → automatic.**
- **Budget arithmetic must be derived, not summed.** Flight 4's hand total was 150 lines wrong (conservative direction); the flight-end Reviewer corrected it from `git diff --numstat`. The mission ends at 2,970/3,000 — a third platform does not fit without an explicit trim-or-raise decision.
- **"Gone" claims need the right verification language** (Flight 1's own lesson, then a root-owned `__pycache__` survived four flights): "no tracked files" is the check, not "directory absent."
- **CI-exact lint locally.** PR #190 failed CI twice on pre-existing lint debt (both from earlier merges) because the local gate ran `ruff check` without `ruff format --check`. Every Developer spawn now carries both halves; two "pre-existing, untouched" reviewer notes should have been fixes.
- **Confirm whose account a logged-in browser session belongs to before driving it** (Flight 4's personal-account near-miss — benign, self-corrected, but a rule now).
- **Behavior-spec calibration** recurred across two flights: windows sized to the happy path; a promotion clause that didn't apply to unbound sessions; process invariants asserted as per-step observables. AUTHORING.md rules, not rediscoveries.
- **Subagent stalls** (eleven): harness feedback filed; the resume play works but costs a round-trip each time.

## Lessons Learned

**Technical**
- A floor-model agent (~20B) works when the tools do the steering: every recovery in two gates was driven by `[error]`/`[no-match]` text and every bad guess was contained by authorization. Design tools for the model that flails. Below ~20B (ministral-class), confirm-before-acting blocks even mechanically-sound chains — the supported floor is gpt-oss:20b-class.
- Protocol-complete fixtures cannot see perception: Telegram's fake Bot API models offset semantics exactly and could never have shown raw markdown in a real client. Live HATs stay mandatory for anything a human reads.
- Platform quirks belong at the plugin's send boundary (Telegram's markdown→HTML), never in the contract's canonical text — the template for the next platform.
- Peer/channel admission asymmetry ("rooms are not people") is sound for Discord and Telegram but is precedent, not doctrine — state it mechanically before a platform where a "channel" can be a private 1:1 (Matrix).

**Process**
- Two review tiers, two defect classes. Six review-time questions now exist (below); they are cheap relative to an inert tool or a live-gate rerun.
- The apparatus premise-audit has three axes: act, observe, **admit**.
- Some behavior-test findings are model-tier findings, not code findings — two flights of instances now.
- Named findings become squawks immediately, not debrief bullets.

**Domain**
- Telegram bots cannot see other bots' messages — no automated live gate is possible there; the fixture + HAT are permanent coverage. Discord's driver-bot apparatus needs Message Content intent on the *reading* bot.
- The Bot API puts the token in the URL path; any INFO-level HTTP logging leaks it (the `anthropic`/`openai` SDKs set httpx to INFO at import under `*_LOG=info` — the actual leak mechanism, now pinned to WARNING unconditionally).

## Methodology Feedback

For mission-control (carry to the skills):

1. **Decision routing** (`agentic-workflow`, `flight`): functional decisions (behavior a user notices, scope, posture) → operator via AskUserQuestion; technical decisions (data shapes, mechanics, fixture design) → FD + Architect/Developer review, recorded in the log; squawk logging → automatic on any named finding, no confirmation prompt.
2. **Six review-time questions** for flight and leg design review charters: (a) DD-to-DD contradiction sweep — does any DD's actor/apparatus fail another DD's admission/drop rule?; (b) trace-the-happy-path through the DDs as written — which DD carries each hop?; (c) tool parameter-source audit — every required parameter's source: prompt, conversation, tool result, or must-guess?; (d) registration reachability — is every new capability reachable through its seam, not just implemented?; (e) permissive-parsing drop — does the model declare a field for every returned/enriched column?; (f) budget from the diff — `git diff --numstat` against the flight's start commit, never a hand sum, when legs overlap on files.
3. **`behavior-test` AUTHORING.md**: the third apparatus axis (admit); the model-tier-finding confound with the two-flight evidence; calibrate recovery-loop windows for the floor model on first draft; never assert top-level bubble promotion for unbound-session steps; process invariants belong in Preconditions/attestation, not per-step Expected Results; required platform intents belong in Preconditions.
4. **`agentic-workflow` Developer discipline**: run CI's exact lint gate (check + format); a "pre-existing lint issue" note is a fix, not a pass; "gone" claims verify as "no tracked files"; confirm account ownership before driving a logged-in browser session in a HAT.
5. **Validator proof patterns worth canonizing** (from the Flight 3 run): `edited_timestamp`-style creation-vs-edit checks to separate read-side redaction from data change; DOM parent-chain containment to settle top-level-vs-nested rendering; log-signature uniqueness matching to prove a reconnect was genuine.
6. **The subagent stall** remains a harness issue (feedback filed); until fixed, the preemptive foreground instruction plus the resume-with-directive recovery is the standing play.

## Action Items

- [x] README architecture paragraph corrected (third tool; auto-reply) — this debrief's commit
- [ ] Operator: remove the root-owned stray `tests/live/discord_hat/__pycache__` (`sudo rm -rf`) — untracked, cosmetic
- [ ] Next connector-touching work: explicit trim-or-raise decision on the 3,000-line ceiling BEFORE planning (2,970 used); Matrix (sync, no SDK) is the cheaper next platform to prove the seam a third time; Slack needs an SDK-exception mission conversation per the mission's own constraint
- [ ] Next platform flight design: state the peer/channel admission doctrine mechanically
- [ ] Mission-control: adopt items 1–5 of Methodology Feedback into the skills (a mission-control-side change; not this project's work)
- [ ] Release v0.8.0 — Connector Reset (operator-requested; follows this debrief's merge)

---

## Correction (annotated 2026-09-03, post-close)

The JS figure in the Success Criteria table ("~720 / 1,000") was a carried-forward
running estimate, never re-derived from the diff. The 2026-09-03b turnaround's batch
Reviewer measured it: `connector-editor.js` was **514** lines at this mission's close
(`e5edc4a`), not ~720. The criterion holds either way — both readings are comfortably
under 1,000 — so the verdict is unchanged.

Annotated rather than rewritten: a debrief is a snapshot of what was known at close,
and the error is itself evidence for the lesson the debrief already drew ("budget
arithmetic must be re-derived, not summed" — What Could Be Improved → Process). Two
instances of that class now: Flight 4's leg-summed Python total (corrected at
flight-end review) and this JS estimate (corrected post-close). The rule stands and
its cost is now measured twice.

For anyone reading forward: the connector JS surface after the 2026-09-03b UI
turnaround is **710** lines in `connector-editor.js` (+196 that batch), plus the
connector-related touches in the shared Studio files. Well under 1,000; measure from
the diff before planning any further connector UI work.
