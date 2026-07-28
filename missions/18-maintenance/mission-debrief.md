# Mission Debrief: Post-Mission-16 Maintenance

**Date**: 2026-07-27
**Mission**: [Post-Mission-16 Maintenance](mission.md)
**Status**: completed
**Duration**: 2026-07-10 (single-day execution, PRs #154–#157)
**Flights Completed**: 4 of 4

## Outcome Assessment

### Success Criteria Results

| Criterion | Status | Notes |
|-----------|--------|-------|
| D1 — runtime CVE patches, uv.lock clean | Met | pip-audit 24→2 (remaining 2 dev/toolchain-only); runtime-closure audit clean. Flight review extended the fix to `pyproject.toml` floors so the Windows-installer re-resolve binds too — verified via `--dry-run` on the Windows-platform resolve. |
| S1+S2 — malformed `images` payload can't crash the WS loop | Met | Three layered guards (shape validation → caps → narrow content-build guard), all using the same `{"type": "system"} + continue` rejection shape; `ImageContent` guard survives `python -O`. Real loop-survival tests, not source scans. |
| S3 — image size/count cap, client + server | Met | 10 MB/image, max 10/turn; server rejects before auto-join; client cap is batch-aware (`plannedCount` handles async FileReader multi-select). Browser tests cover both rejections. |
| C1+C4 — pre-merge CI gate restored without undoing cost-shift | Met | `pr-lint.yml` (ruff + blocking runtime pip-audit), green on all six PRs #154–#159. Heavy lanes untouched. One latent defect found during this debrief — see Action Items. |
| A1+A2+A3 — attach-UI accessibility gaps closed | Met | Delta live-region separate from the innerHTML-rebuilt row; 1-based distinct accessible names; `--status-danger` resting contrast + new composited-contrast regression gate (worst case ≥4.6:1 both themes). |
| T1 — aiosqlite teardown durably fixed | Met | Root cause was one deterministic leak (`test_db_migration.py:1798`) + one fragile shared fixture, not a blanket close problem (83/85 sites were already correct). Warning absent across permuted runs and full suite; daemonize backstop retained as defense-in-depth. Oldest carried item (six cycles) cleared. |
| DOC1+DOC2+T2+T3 — doc/coverage hygiene | Met | `visibility` live-emit mirrors codec projection (connector-timing caveat documented in-code — partial parity by design, don't re-report next cycle); two `agents.md` M16 promotions follow the M10/M11 ladder; both behavior-test specs authored. |

### Overall Outcome

Achieved in full, in one day. The codebase returned to Flight Ready with the debt cluster from the 2026-07-10 maintenance report cleared, and the mission's regression nets started paying out immediately: the first `vision-round-trip` behavior-test run (PR #158, ~2h after mission close) surfaced a real bug — per-message timestamps lost on session replay — fixed same-day in PR #159. Post-close fallout worth recording: PR #158 (both behavior specs first-run, both pass; specs now `active`) and PR #159 (`Message.created_at` added, `None`-default, preserving the `str`-identical fast path and codec byte-identity invariants).

Architect verdict on the system: **improved**. No structural change attempted (correct for maintenance); every touched seam is strictly more defensive, and design decisions were consistent across all four flights.

## Flight Summary

| Flight | Status | Key Outcome |
|--------|--------|-------------|
| 1 — Supply-chain & CI gate | landed | 7 runtime CVE clusters cleared with dual-binding (uv.lock + pyproject floors, verified to bind); `pr-lint.yml` pre-merge gate live. |
| 2 — Input robustness | landed | WS message branch crash-proofed with layered guards + caps; review fix closed a re-opened crash class (cap block ran before the Leg-1 guard, unguarded against malformed shapes). |
| 3 — Attach-UI accessibility | landed | A1/A2/A3 closed in one pass; composited-contrast regression gate added; hover affordance restored via existing danger wash. Browser 9/9, token-a11y 145. |
| 4 — Test-infra & doc hygiene | landed | Six-cycle aiosqlite flake fixed at root cause; visibility emit parity; two agents.md promotions; two behavior specs authored (both validated post-close). |

## What Went Well

- **Flight review earned its keep twice.** F1's review caught that the initial CVE leg repeated the exact "release artifact re-resolves from pyproject, not uv.lock" gap M12 had closed — and pushed the fix to verified-binding floors. F2's review caught the cap block reintroducing the crash class Leg 1 fixed. Both were the difference between "looks done" and "is done."
- **Design-review-corrected diagnosis on T1.** The AST sweep (83/85 sites already correct) turned a blanket-rewrite instinct into a three-line-cause surgical fix, keeping the diff minimal while actually killing a six-cycle-old flake.
- **The behavior-test recommendation validated itself same-day.** `vision-round-trip`'s first run found the replay-timestamp bug. Strongest possible evidence for authoring specs during planning.
- **Pattern consistency.** One rejection shape across all WS guards; reuse of existing mechanisms (`.visually-hidden`, danger wash, codec projection mirror) instead of parallel inventions; second instance of the composited-contrast test makes it a reusable template.
- **Suite health at its best**: 3976→3997 tests, wall-clock flat, oldest warning gone.

## What Could Be Improved

- **The M12 lesson recurred because it lived only in an old leg artifact.** "A CVE fix is not landed until both the lockfile and the pyproject floors bind — verify the release-artifact resolve path" needs to be a durable convention (agents.md or the maintenance checklist), not tribal knowledge a reviewer happens to re-derive.
- **Behavior-test first runs happened outside the mission window.** Both specs ran ~2h post-close and immediately produced a bug fix (#159) that landed outside any mission/flight structure. Next time, first-runs belong inside the mission (a leg acceptance step or a close-out gate).
- **Hand-mirrored client/server cap constants** (`chat.js:147-148` ↔ `app.py:475-476`) have cross-referencing comments but no sync guard, in a codebase that already has the `test_ui_guards.py` sync-guard pattern to copy.
- **`websocket_endpoint` is accreting inline validation** (~110 lines in the message branch across shape/count/size/content guards). Each addition honored the no-opportunistic-refactor constraint correctly, but the next mission touching this surface should budget a payload-validation extraction as an explicit leg, not add a fourth inline block.

## Lessons Learned

- **Dual-binding rule for dependency fixes**: lockfile + manifest floors, verified to bind on the release-artifact resolve path. (Promote to convention — Action Item.)
- **Composited-contrast testing is the named pattern** for any translucent-fill token gate: reconstruct the rendered fill (alpha wash over ladder surfaces), don't test token pairs in isolation.
- **Delta live-region separate from innerHTML-rebuilt containers** — reasoning documented in-code at `chat.js`; reusable anywhere the UI rebuilds a row wholesale.
- **A debrief written before a same-day fix lands, or on an over-strong static claim, must be verified — not inherited — by the next maintenance pass** (carried from the maintenance report; F4 confirmed both M16 corrections were already applied and recorded verification rather than silently skipping).
- **Scaling watch item (not actionable now)**: attachments ride base64-in-JSON through one `receive_text` — worst case ~130 MB/turn. Fine under the single-user local posture the caps were sized for; a posture change makes this a streaming/multipart redesign, not a cap retune.

## Methodology Feedback

- **`/routine-maintenance` should stop pre-planning all flights.** Operator: the scaffolded-mission flow "is a little off with regular missions — originally meant to speed things up, but is just confusing." Ruling requested: the skill should produce the **mission plan only**, then the regular `/flight` (and `/leg`) skills run per-flight as work progresses, matching the normal one-flight-at-a-time cadence. This is a mission-control skill change, not a project change.
- **Per-flight debriefs were skipped for all four flights** (prior maintenance missions 09/12 wrote them). Operator wants this **considered as a new convention** for maintenance missions — small, single-day, checklist-shaped flights where the mission debrief carries the retrospective load — rather than recorded as a process miss. Candidate ruling for mission-control; not yet adopted.

## Action Items

- [ ] **Fix `pr-lint.yml` pip-audit install line** (defect found during this debrief's Architect spot-check): `pip install pip-audit>=2.7` is unquoted, so bash parses `>=2.7` as a redirect — pip-audit installs unpinned and a stray `=2.7` file is written. Quote it or (better) pin an exact version, matching the file's own pinned-ruff standard. Minutes; first item on the next maintenance list.
- [ ] **Add a cap-constant sync guard** pinning `chat.js` ↔ `app.py` attachment cap pairs equal (copy the `test_ui_guards.py` source-scan pattern). Minutes.
- [ ] **Promote the CVE dual-binding rule to a durable convention** (agents.md or maintenance checklist) so the M12 lesson can't recur a third time. Minutes.
- [ ] **C3 — SHA-pin GH Action refs** as one batch across all workflows (`pr-lint.yml` added two more floating-major refs); fold the pip-audit pin fix into the same pass.
- [ ] **A4 — reduced-motion (AAA)** — fold into the next CSS-touching flight (the deferred surface grew slightly: transition now covers `background-color` too, and the hover wash has no browser-test assertion).
- [ ] **Y1 — static type checker** — still its own future initiative; `pr-lint.yml` is now the natural home for a fast type-check lane when it lands.
- [ ] **Next capability mission (agent-level config surface, seeded by the M16 debrief)**: cite `seed-before-overlay` in leg specs up front; author an analogous behavior spec inline (use `tests/behavior/save-preserves-config.md` as the template); budget the WS payload-validation extraction as an explicit leg if new message types land; note `Message` now carries `created_at` (PR #159) alongside its existing invariants.
- [ ] **Methodology (mission-control): rework `/routine-maintenance`** to emit the mission plan only and defer flight planning to the regular skills.
- [ ] **Methodology (mission-control): decide the maintenance per-flight-debrief convention** (skip by design vs. required).
