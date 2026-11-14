# Leg: alignment-hat

**Status**: completed
**Flight**: [Professional README](../flight.md)

## Objective

Cold-read alignment HAT on the README. Operator (or a fresh-context model on the operator's behalf) reads `/README.md` as if landing on the repository for the first time. Any confusing, inaccurate, stylistically off, or drift-prone content gets fixed inline. The install snippet is explicitly cross-verified against current `pyproject.toml`. When the operator is satisfied, the leg closes — and with it, the flight, and the mission.

## Context

Final leg of Flight 8, final flight of Mission 08. L01 landed the README content and the `gated-debug-instrumentation` convention; L02 landed three dark-theme screenshots and the README image-wiring. L03 is the alignment / cold-read pass — the README is now visually complete; this leg verifies it READS as intended for a fresh external audience.

The leg is **interactive** — the FD cannot judge "does this read clearly cold" by itself; that's the operator's role. The FD guides the operator through the alignment steps and applies any inline fixes the operator requests.

## Inputs

**State before this leg runs**:
- L01 + L02 committed (commits `814f8d3` and `dad2b21` on branch `flight/08-professional-readme`)
- `/README.md` exists with: hero mascot, tagline, "what this is" paragraph, three embedded screenshots (chat → studio → admin), dual-path quickstart, six-paragraph architecture overview, security link, Mission Control pointer
- `docs/screenshots/` contains 3 PNGs
- `the_one/agents.md` has the `gated-debug-instrumentation` convention entry
- Mission 08 has 11 of 12 criteria checked; criterion 12 (top-level documentation) becomes checked at this leg's close

## Outputs

**Files possibly modified** (the alignment cycle may or may not require edits):
- `/README.md` — wording polish, factual corrections, link fixes if the cold-read surfaces any
- `mission.md` — criterion 12 checked off (this leg's primary state change)

## Acceptance Criteria

- [x] Operator has read `/README.md` cold and signaled "no changes" (after multiple rounds of inline fixes — see Implementation notes)
- [x] Install snippet (`pip install -e ".[all-llms,dev]"`) verified verbatim against current `pyproject.toml` `[project.optional-dependencies]` section (`all-llms` and `dev` extras both present at the cited form)
- [x] All inline-fix requests from the alignment pass applied (5 substantive fixes + 1 Architect-flagged dependency-list expansion)
- [x] Architect agent (Opus) ran a final accuracy audit — `[HANDOFF:confirmed]` after one medium fix applied; no critical issues
- [x] README renders correctly with all embedded images
- [x] Mission 08 criterion 12 checked off in `mission.md`
- [x] Flight 8 status updated from `in-flight` to `landed` in `flight.md`
- [x] Flight 8 entry in `mission.md`'s `## Flights` list checked off

## Verification Steps

- **Install snippet pin check**: `grep -A 1 "optional-dependencies" ~/projects/the-one/pyproject.toml | head` should show `all-llms = [...]` and `dev = [...]` matching the README's `pip install -e ".[all-llms,dev]"` claim
- **README link sanity** (operator visually inspects): SECURITY-MODEL.md link resolves, missions/ relative path link resolves, Mission Control https URL is correct
- **All checkboxes ticked**: re-confirm flight.md and mission.md state via `grep` for criterion 12 + Flight 8 in `mission.md`

## Implementation Guidance

### Step 1: Cold-read

Operator opens `/README.md` (VS Code preview, GitHub web UI, or any markdown previewer) and reads it as if they're seeing the project for the first time. Specifically watch for:

- **Tagline**: does "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." feel right under the mascot?
- **Hero asset**: does the medium mascot at 280px feel right, or should the width adjust?
- **One-paragraph "what this is"**: warm enough? Too long? Too short? Misses anything important?
- **Screenshots**: do they read clearly at the embedded size? Captions sufficient via `alt` text alone, or does the README need a one-line caption per shot?
- **Quickstart**: are both paths (pip-editable + Docker) clear to someone who's never seen the project? Anything missing or extraneous?
- **Architecture six paragraphs**: each layer's description accurate? Anything confusing? Anything to add or trim?
- **Security pointer**: does the one-line section feel right, or should it expand slightly?
- **Mission Control pointer**: clear enough? Too brief?
- **Overall tone**: consistent? Anything that jars?

### Step 2: Install snippet pin check

The FD runs `grep -A 1 "optional-dependencies" pyproject.toml` and confirms `all-llms` + `dev` extras are present in the current form the README cites. If they've drifted, update the README to match.

### Step 3: Apply inline fixes

Operator reports findings to the FD; FD applies fixes via `Edit` tool. After each batch, operator re-reads the affected sections to confirm.

### Step 4: Close out

When the operator is satisfied:
- FD updates this leg's status from `ready` to `completed`
- FD checks off the leg in flight.md
- FD updates flight.md status `in-flight` → `landed`
- FD checks off Flight 8 in mission.md's `## Flights` list
- FD checks off criterion 12 in mission.md's `## Success Criteria` list
- FD commits as the final leg of the flight

## Edge Cases

- **Operator wants major restructuring**: this would exceed L03 scope. Pause, note the divergence in the flight log, and consider whether to abort L03 and create a follow-up leg or flight.
- **Install snippet has drifted**: update the README to match `pyproject.toml`. Document the drift in the flight log as a "drift caught at alignment HAT" note — useful evidence for whether the L01 design decision to crib install was right.
- **Screenshots look wrong on GitHub but fine in local preview** (or vice versa): may indicate a width or relative-path issue. Tweak the `<img width=>` or path; recheck.
- **A new mission criterion suddenly looks unmet**: pause, surface to operator, do not auto-tick.

## Files Affected

- `~/projects/the-one/README.md` — possible wording / link / image-width edits
- `~/projects/the-one/missions/08-gleepglorp-rebrand/mission.md` — criterion 12 ticked, Flight 8 entry ticked
- This leg artifact — status updated to `completed`
- The flight artifact — status updated to `landed`, leg checked off
- The flight log — alignment HAT entry, mission close note

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] Cold-read complete; all operator findings addressed
- [x] Install snippet cross-verified against pyproject.toml
- [x] Architect accuracy audit run; one medium fix applied; confirmed
- [x] Set this leg's status to `completed`
- [x] Check off this leg in flight.md
- [x] **Final leg** — update flight.md status to `landed`
- [x] Check off Flight 8 in mission.md's `## Flights` list
- [x] Check off criterion 12 in mission.md's `## Success Criteria` list
- [x] Update flight log with L03 entry
- [x] Commit all changes (README edits + artifact-state updates) as a single commit

## Citation Audit

3 code-location citations verified against current code at leg design time:

| Citation | Classification | Notes |
|---|---|---|
| `pyproject.toml` `[project.optional-dependencies]` `all-llms` + `dev` extras | OK | Verified at flight design (lines 33, 36) and L01 implementation |
| `README.md` install snippet `pip install -e ".[all-llms,dev]"` at line ~30 | OK | Verified post-L01 commit and post-L02 commit |
| `mission.md` criterion 12 (top-level documentation) | OK | Verified at flight design; criterion is currently `[ ]` |

All citations verified clean. No drift.
