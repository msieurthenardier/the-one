# Flight Log: Accessibility Carry-forward + F1 Tech-Debt Cleanup

**Flight**: [Accessibility Carry-forward + F1 Tech-Debt Cleanup](flight.md)

## Reconnaissance Report

**Date**: 2026-05-16 (during flight design, post-F1-close)
**Source artifacts**:
- [Maintenance Report 2026-05-15](../../../../maintenance/2026-05-15.md) — the original a11y findings (A.1-A.13)
- [F1 Flight Debrief](../../01-integrity-gate-restoration/flight-debrief.md) — sourced the new "F1 tech-debt carry-forward" bundle (non-methodology items only per operator direction)

**Method**: Each scope item verified against current code on `flight/01-integrity-gate-restoration` HEAD (post-F1-close at `c70b73b`). F1's a11y items (A.1-A.13) were already verified during mission-design recon (2026-05-15); re-verified the most critical ones (welcome listbox shape, history-buckets listbox shape, tools-grid `role="list"`, form-field error markup, light-theme token values). F1 carry-forward items (6 non-methodology recommendations) verified fresh.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| Welcome agent picker has `role="listbox"`/`role="option"` (needs roving-tabindex) | confirmed-live | re-confirmed on F1 HEAD | Proceed with F2 Leg 1 |
| Session list has `role="listbox"`/`role="option"` containing `<button>` (structural fix needed) | confirmed-live | `tests/browser/test_flow_keyboard.py:50, 63, 67` asserts the current shape | Proceed with F2 Leg 1 |
| Tools-grid uses `role="list"`/`role="listitem"` (NOT a listbox — verify-only) | confirmed-live | `the_one/interfaces/web/static/js/areas/admin/tools-grid.js:62` `role="listitem"`; `:101` `role="list"` | Proceed with F2 Leg 1 verify-only path |
| Form-field errors lack `aria-invalid`/`aria-describedby`/`role="alert"` | confirmed-live | `tools-form-helpers.js:517-519` appends `.field-error` span; no aria wiring | Proceed with F2 Leg 2 |
| Light-theme `--fg-muted: #64748b`, `--fg-faint: #94a3b8`, `--shell-chrome-bg: #d4d8df`, `--fg-tertiary: #475569` | confirmed-live | `tokens.css:246-248, :447` | Proceed with F2 Leg 2 scope-the-usage approach |
| `agents.md ### live-read-across-lazy-resolver-boundary` cites non-existent test | confirmed-live | `agents.md:233` cites `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py`; neither exists. Actual test: `test_usage_event_reflects_live_max_context_tokens_at_emission` at `tests/test_process_and_broadcast_live_read.py:98`. | Proceed with F2 Leg 3 (a) |
| `Makefile doctor` target uses bare `python -c` (sub-shell PATH foot-gun) | confirmed-live | `Makefile` around L148 `@python -c "import asgi_lifespan, ..."` | Proceed with F2 Leg 3 (b) |
| `Makefile` has no `rebuild-browsers` target | confirmed-live | `grep -c rebuild-browsers Makefile` → 0 | Proceed with F2 Leg 3 (c) |
| `Makefile` has no `audit-bytes` target | confirmed-live | `grep -c audit-bytes Makefile` → 0 | Proceed with F2 Leg 3 (d) |
| `agents.md ## Project Conventions` has no `### host-side-bench-drift-detection` entry | confirmed-live | `grep -n "host-side-bench" the_one/agents.md` → 0 matches | Proceed with F2 Leg 3 (e) |
| No documented npm-spec regex as a security primitive | confirmed-live | `grep -n "_VALID_NPX_PKG_RE\|npm.spec" the_one/agents.md SECURITY-MODEL.md` → only the existing code reference in cache_cleanup.py, no doc treatment | Proceed with F2 Leg 3 (f) |
| `Makefile audit` target's "Non-blocking by design" rationale | already-satisfied | `Makefile` L153 has `## Run pip-audit against host venv (non-blocking; surfaces advisories)` help-string carrying the rationale | F1 debrief item #9 — close as satisfied; no Leg 3 sub-fix needed |
| Browser/pixel suite blocked by missing Chromium in container | needs-human-recheck | F1 debrief confirmed 312 ERRORS at setup; recurring foot-gun. Operator action required: `docker exec the-one playwright install chromium`. | **PRE-FLIGHT PREREQUISITE — operator must run before F2 leg execution begins** |

**Net disposition**: 12 of 13 items `confirmed-live` (proceed to legs); 1 `already-satisfied` (close, no Leg 3 sub-fix — F1 debrief item #9 absorbed by existing Makefile help-string); 1 `needs-human-recheck` and PROMOTED to pre-flight prerequisite (Chromium restoration — blocking).

**Observations beyond the scope**:
- F1's flight debrief is dated 2026-05-16 but reflects work landed 2026-05-15. F2 design (this recon) happens 2026-05-16 same-day. No drift risk.
- The `rebuild` target's exact invocation needs reading at implementation time (Leg 3 sub-fix (a) chains on top of it).
- The npm-spec doc placement (agents.md vs SECURITY-MODEL.md) is intentionally left to implementer judgment; both are valid homes.

---

## Summary

(Populated during execution.)

---

## Flight Director Notes

### 2026-05-16 — Flight start (agentic-workflow kickoff)

- **Phase file loaded**: `the-one/.flightops/agent-crews/leg-execution.md` (project-side, same as F1).
- **Branch**: `flight/02-accessibility-and-cleanup` created off `flight/01-integrity-gate-restoration` (F1 PR #56 not yet merged; F2 legs reference F1 commits as preconditions). Rebase onto `main` after PR #56 merges.
- **Flight status transition**: F2 `ready` → `in-flight`. Mission 09 stays `active` (Flight 1 completed; Flight 2 in-flight).
- **Pre-flight cleanup**: removed a stale empty `the_one/_probe_lsep.py` from git index (created by Architect's design-review probe; never committed; safe to unstage).
- **Initial commit on F2 branch**: planning scaffold additions (revised F2 flight.md, expanded flight-log.md, new Leg 3 spec). Subsequent commits will be leg work; flight-close commit handles status transitions.
- **3 legs planned**: Leg 1 (welcome picker + session-list + tools-grid verify), Leg 2 (form errors + tokens + sweep), Leg 3 (F1 tech-debt bundle). Estimated ~2.5-4 days total.

### 2026-05-16 — Flight design + design review

- **F2 originally designed during mission scaffolding (2026-05-15)** with 2 legs (a11y carry-forward); reshape today incorporates the F1 debrief's 6 non-methodology recommendations as a new Leg 3 per operator direction.
- **Recon report at top of this log** verified all scope items confirmed-live; 1 item already-satisfied (Makefile `audit` non-blocking rationale already in help-string); 1 item promoted to pre-flight prerequisite (Chromium restoration).
- **Architect design review on revised F2 (Opus)**: approve with changes. 3 high + 2 medium + 2 low issues raised.
- **High-severity fixes applied**:
  1. **`_ensure-playwright` already exists at `Makefile:39-46`** — Architect spot-check caught this. Leg 3 sub-fix (a) reframed from "implement `rebuild-browsers` with raw `playwright install chromium`" to "chain `rebuild + _ensure-playwright` using existing machinery." F1 debrief's "312 ERRORS at setup" came from bypassing `make` and calling raw `docker exec the-one pytest -m browser` — the foot-gun is mostly already mitigated; this leg adds a convenience alias.
  2. **Pre-Flight Chromium prereq downgraded** from BLOCKING-operator-action to "run `make _ensure-playwright` once at flight start." All F2 browser-test verification commands switched from raw `docker exec the-one pytest -m browser` to `make test-browser` (which chains `_ensure-playwright` automatically).
  3. **`make audit-bytes` git-grep tracked-only contract documented** — `git grep` scans the index, not the working tree. Files unstaged won't be scanned. Added as explicit Edge Case + Implementation Guidance note.
- **Medium-severity fixes applied**:
  4. **`make audit-bytes` pathspec broadened** to `the_one/**/*.py` `tests/**/*.py` (recursive `**`) — original `the_one/*.py` would have missed nested modules.
  5. **`.venv/bin/python` clarification**: the venv interpreter is a symlink chain → `python3` → `/bin/python3`. The fix is functionally correct but framing was imprecise. Updated `doctor` target spec to use `.venv/bin/python3` (matches `.venv/bin/pip-audit` shape in `audit` target).
- **Low-severity fixes applied**:
  6. **`### host-side-bench-drift-detection` placement made explicit**: between `### gated-debug-instrumentation` (M08 F7) and `### live-read-across-lazy-resolver-boundary` (F1 M09 Leg 3) — chronologically correct.
  7. **npm-spec regex doc placement corrected to `SECURITY-MODEL.md ## Tool Execution Boundary`** (Architect-preferred over the original `agents.md` recommendation). That section already enumerates per-category allowlists (filesystem-path, subprocess-env, web-SSRF); npm-package-name allowlist is the same class — defensive control at a tool boundary.
- **Branch strategy resolved**: F2 branches off `flight/01-integrity-gate-restoration` directly with name `flight/02-accessibility-and-cleanup`. Rebase onto `main` after PR #56 merges. (Branching off `main` would require waiting for merge or cherry-picking F1 commits — wasteful.)
- **Skipped 2nd review cycle**: all fixes were corrective (no new design). Per skill's "Skip if only minor/cosmetic fixes were applied" guidance — these are clarifications + corrections, not redesign.

---

## Leg Progress

(Populated during execution.)

---

## Decisions

(Populated during execution.)

---

## Deviations

(Populated during execution.)

---

## Anomalies

(Populated during execution.)

---

## Session Notes

(Populated during execution.)
