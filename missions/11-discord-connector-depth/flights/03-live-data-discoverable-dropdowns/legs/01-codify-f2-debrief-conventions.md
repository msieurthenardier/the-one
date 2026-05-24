# Leg: codify-f2-debrief-conventions

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Codify two F2-debrief-recommended methodology conventions (`primitive-rename-test-classification` + `flight-spec-dom-order-audit`) as project-wide entries in `the_one/agents.md`, so subsequent F3 legs can invoke them by name and so future flights inherit them as the project-wide vocabulary.

## Context

- F2's debrief (`missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-debrief.md`) Recommendations §"Important — codify two methodology rules as agents.md project conventions" enumerated the two conventions and tagged them for codification at F3 L1.
- F2 Action Items explicitly call out folding the codification into F3 L1 if F3 uses the L1-codification pattern (which it does — see F1 L1 + F2 L1 precedent in the flight-architect playbook).
- F1 L1 codified `optional-registry-entry-hook` and `registry-dispatch-create-mode-AC`; F2 L1 was a sibling-style codification. F3 L1 follows the same shape: doc-only, no source modifications, citations grounded in the triggering flight.
- Both conventions live under `### Project-wide` per the established pattern (`the_one/agents.md` is currently ~706 lines; `### Project-wide` spans roughly lines 28-198 with `### \`registry-dispatch-create-mode-AC\`` as the current bottom entry around line 187, followed by `### Mission-specific (M10)` around line 199). The two new entries are inserted AFTER `registry-dispatch-create-mode-AC` and BEFORE `### Mission-specific (M10)`. Order between the two new conventions: `primitive-rename-test-classification` first, `flight-spec-dom-order-audit` second (F2 debrief enumeration order; matches the F1 L1 "by appearance in source debrief" precedent).

## Inputs

- `the_one/agents.md` exists with `### Project-wide` subsection containing the established set of project-wide conventions (current bottom of the subsection is `### \`registry-dispatch-create-mode-AC\``, followed by the `### Mission-specific (M10)` subsection heading).
- F2 debrief documents both conventions with definition + applicability hints + citation hints (the three F2 L2 cycle-1 mischaracterized test files for the first; the F2 L4 cycle-1 wording-vs-DOM-order divergence for the second).
- F1 L1's codification pattern is the structural reference (`### \`convention-name\`` → 1-2 paragraph definition → "Applies when … Does NOT apply to …" applicability paragraph → "Citation(s):" with file:line or test references → "Source: …" line).

## Outputs

- `the_one/agents.md`'s `### Project-wide` subsection grows two new entries:
  - `### \`primitive-rename-test-classification\`` immediately after `### \`registry-dispatch-create-mode-AC\``
  - `### \`flight-spec-dom-order-audit\`` immediately after the new `primitive-rename-test-classification` entry (so the order is: rename-classification first, dom-order-audit second)
- Both entries follow the established 4-block structure (definition / applicability / `Citation(s):` / `Source:`) matching the format of `optional-registry-entry-hook` (`Citations (n=3 from M11 F1):`) and `registry-dispatch-create-mode-AC` (`Citation (n=1 from M11 F1 L7, codified by methodology-promotion ...):`).
- No source code modifications. No test modifications.
- Sibling artifact bookkeeping (explicit scope, not "modifications beyond"): F3 `flight.md`'s L1 Checkpoints entry + L1 Legs checklist item checked off; F3 `flight-log.md`'s Leg Progress section grows an L1 entry; this leg artifact's Status header progresses through its lifecycle.

## Acceptance Criteria

- [x] `the_one/agents.md` contains a new heading `### \`primitive-rename-test-classification\`` placed immediately after `### \`registry-dispatch-create-mode-AC\``.
- [x] `the_one/agents.md` contains a new heading `### \`flight-spec-dom-order-audit\`` placed immediately after the new `primitive-rename-test-classification` entry and immediately before `### Mission-specific (M10)`. (The two new entries appear in this exact order: rename-classification first, then dom-order-audit.)
- [x] The `primitive-rename-test-classification` entry contains a definition paragraph stating: when a leg spec touches a primitive's name (rename / split / consolidation), the default classification for every test file containing the primitive's name is `code-update`; downgrade to `docstring-sweep` only after grep verifies the name appears solely inside `"""..."""` docstring blocks. The cycle-0 default of "docstring-sweep until proven otherwise" inverts the safe direction.
- [x] The `primitive-rename-test-classification` entry contains an applicability paragraph: applies whenever a leg's scope includes renaming, splitting, or consolidating a named primitive (function, class, dataclass, constant, or method) that is referenced by tests; does NOT apply to leg-internal symbol renames whose names never appear in test files (grep returns zero hits in `tests/`).
- [x] The `primitive-rename-test-classification` entry uses the inline-parenthetical citation label shape `Citations (n=1 trigger, n=3 evidence files from M11 F2 L2 cycle-1):` matching the precedent at `optional-registry-entry-hook`'s `Citations (n=3 from M11 F1):` format.
- [x] The `primitive-rename-test-classification` entry's citation block names all three F2 L2 cycle-1 mischaracterized test files (`tests/test_connectors_inbound.py`, `tests/test_lifespan.py`, `tests/test_connectors_e2e_platform_send.py`) with a one-phrase note about the kind of functional code the cycle-0 classification missed (`monkeypatch + sentinel filter` / `getattr/setattr sites + assertion` / `monkeypatch + assertion + function rename`).
- [x] The `primitive-rename-test-classification` entry ends with a one-sentence `Source:` line in the brief form established by `registry-dispatch-create-mode-AC`'s precedent (one-line section-pointer; do not restate the threshold-justification — that belongs in the citation block above): `Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 1) + "What Could Be Improved §Important — primitive-rename test classification rule."`
- [x] The `flight-spec-dom-order-audit` entry contains a definition paragraph stating: at flight-design time when claiming section placement adjacencies (e.g., "between section X and section Y" wording in Design Decisions or leg specs), the architect must re-walk the current DOM order against the live source before committing the wording, NOT rely on memory of a prior DOM walk.
- [x] The `flight-spec-dom-order-audit` entry contains an applicability paragraph: applies whenever a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (Studio editor sections, Chat UI panels, settings sub-pages); does NOT apply to logical ordering claims that are not DOM-rendered (file ordering in a directory, leg execution ordering within a flight).
- [x] The `flight-spec-dom-order-audit` entry uses the inline-parenthetical citation label shape `Citation (n=1 from M11 F2 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as \`registry-dispatch-create-mode-AC\`):` matching the precedent at `registry-dispatch-create-mode-AC`'s `Citation (n=1 from M11 F1 L7, codified by methodology-promotion ...):` format.
- [x] The `flight-spec-dom-order-audit` entry's citation paragraph documents the F2 L4 cycle-1 divergence: F2 flight.md Design Decisions §3 originally said "between Pairing and Test Connection," but the current DOM order has Attached Agents between Pairing and Test Connection, so the correct placement of the directive section was "between Pairing and Attached Agents." The reviewer caught the divergence at L4 cycle-1; the leg spec was reworded to match the actual DOM.
- [x] The `flight-spec-dom-order-audit` entry ends with a one-sentence `Source:` line: `Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 2) + "What Could Be Improved §Minor — flight-spec wording drift from DOM order."`
- [x] `git diff the_one/agents.md` shows only insertions between `### \`registry-dispatch-create-mode-AC\`` and `### Mission-specific (M10)`; the rest of the file is byte-identical (no whitespace adjustments, no reflow, no linter-driven adjustments to existing entries).
- [x] No source code (`*.py`, `*.js`, `*.ts`, `*.tsx`, `*.json`, schema migrations, etc.) is modified. `git diff --stat` shows changes only in `the_one/agents.md` plus the F3 sibling artifacts (`flight.md`, `flight-log.md`, this leg artifact).

## Verification Steps

- `git diff the_one/agents.md` shows two new sections inserted between `### \`registry-dispatch-create-mode-AC\`` and `### Mission-specific (M10)`. No other diff hunks in `agents.md`.
- `git diff --stat` for the working tree shows changes ONLY in `the_one/agents.md` plus the F3 sibling artifacts (`flight.md`, `flight-log.md`, this leg artifact). No `*.py` / `*.js` / `*.ts` / `*.tsx` / `*.json` / `*.sql` files in the diff (defensive verification that no source file was inadvertently touched — covers the "no source code modified" AC).
- `grep -n "### \`primitive-rename-test-classification\`" the_one/agents.md` returns exactly one hit.
- `grep -n "### \`flight-spec-dom-order-audit\`" the_one/agents.md` returns exactly one hit.
- `grep -n "^## \|^### " the_one/agents.md` heading list shows the two new entries in the expected positions (after `registry-dispatch-create-mode-AC`, before `Mission-specific (M10)`, in the order rename-classification → dom-order-audit).
- `pytest` is NOT required by this leg (doc-only, markdown-only change). The `git diff --stat` step above covers defensive verification that the leg didn't touch source files.

## Implementation Guidance

1. **Read the current state of `the_one/agents.md` around the insertion point.**
   - Confirm `### \`registry-dispatch-create-mode-AC\`` ends at the line immediately before `### Mission-specific (M10)`. The current file has a blank line separator between `registry-dispatch-create-mode-AC`'s last paragraph and the mission-specific subsection heading.
   - Confirm the convention-entry format from `optional-registry-entry-hook` and `registry-dispatch-create-mode-AC` as the structural reference.

2. **Insert the `primitive-rename-test-classification` entry first.**
   - Heading: `### \`primitive-rename-test-classification\``
   - Definition paragraph (1-2 paragraphs):
     - When a leg spec touches a primitive's name (rename, split, consolidation), every test file that contains the primitive's name is default-classified as `code-update` (i.e., the leg must read the test to determine whether the rename ripples into functional code). Downgrade to `docstring-sweep` (i.e., the rename only changes prose in test docstrings) only AFTER `grep` verifies the name appears solely inside `"""..."""` docstring blocks across the entire file. The cycle-0 default of "docstring-sweep until proven otherwise" inverts the safe direction — it treats a name appearance as docstring noise until refuted, when the truth-table is the opposite (a name appearance is functional usage until refuted).
   - Applicability paragraph: "Applies whenever … Does NOT apply to …"
   - Citations block, using inline-parenthetical label `Citations (n=1 trigger, n=3 evidence files from M11 F2 L2 cycle-1):` matching the precedent at `optional-registry-entry-hook`. The trigger event is the one F2 L2 cycle-1 design review; the three test files are the evidence files mischaracterized at cycle-0:
     - `tests/test_connectors_inbound.py` — monkeypatch + sentinel filter (functional, ~5 lines)
     - `tests/test_lifespan.py` — getattr/setattr sites + assertion (functional, multi-site)
     - `tests/test_connectors_e2e_platform_send.py` — monkeypatch + assertion + function rename (functional)
   - One-line `Source:` per established precedent (do not restate the threshold justification — it lives in the Citations block above): `Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 1) + "What Could Be Improved §Important — primitive-rename test classification rule."`

3. **Then insert the `flight-spec-dom-order-audit` entry.**
   - Heading: `### \`flight-spec-dom-order-audit\``
   - Definition paragraph: at flight-design time, when a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (e.g., "between section X and section Y" in Design Decisions, leg objectives, or implementation guidance), the architect must re-walk the current DOM order in the live source before committing the wording. Memory of a prior DOM walk is unreliable across flight boundaries — sections may have been added, removed, or reordered between the original audit and the current flight-design session.
   - Applicability paragraph: applies to DOM-rendered adjacency claims (Studio editor sections, Chat UI panels, settings sub-pages, connector account detail page sub-surfaces); does NOT apply to non-DOM ordering claims (file ordering, leg execution ordering, mission flight ordering).
   - Citation block, using inline-parenthetical label `Citation (n=1 from M11 F2 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as \`registry-dispatch-create-mode-AC\`):` matching the precedent at `registry-dispatch-create-mode-AC`. The citation paragraph documents: F2 flight.md Design Decisions §3 originally claimed the directive section landed "between Pairing and Test Connection," but a fresh DOM walk at cycle-1 showed Attached Agents between Pairing and Test Connection in the current source, so the correct placement was "between Pairing and Attached Agents." The reviewer caught the divergence; the leg spec was reworded; no structural harm done at L4 itself, but the symptom indicates the flight spec was written without a fresh DOM-order audit.
   - One-line `Source:` per established precedent: `Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 2) + "What Could Be Improved §Minor — flight-spec wording drift from DOM order."`

4. **Preserve byte-identity for the rest of the file.**
   - The edit is purely insertional. No reflow of existing paragraphs. No whitespace adjustments.
   - The `### Mission-specific (M10)` heading and everything after it stays at byte-identical content.

5. **Update `flight.md`'s Checkpoints checkbox for L1.**
   - The L1 checkpoint at flight.md Checkpoints already has its description; check it off `- [x] L1 — Two F2-debrief conventions ...`.

6. **Update `flight.md`'s Legs checklist for L1.**
   - Check off the L1 bullet in the Legs section.

7. **Update `flight-log.md`'s Leg Progress section with a new L1 entry.**
   - Heading: `### L1 — codify-f2-debrief-conventions`
   - Status: completed (when post-completion checklist runs)
   - Brief Changes Made / Notes / outcomes.

8. **Update this leg artifact's Status header.**
   - `planning` → `ready` after design review approves; `in-flight` when the developer agent starts; `landed` when the developer signals review-needed; `completed` after the final code review at the flight gate.

## Edge Cases

- **Existing convention names collide**: grep `the_one/agents.md` for `primitive-rename-test-classification` and `flight-spec-dom-order-audit` BEFORE inserting to confirm they don't already exist. The F3 flight.md recon (R10 + R11) already verified zero hits; re-verify defensively because the developer may run against a state that drifted.
- **Markdown-linter-driven reflow**: do NOT run a markdown linter or formatter against the file. The existing entries were hand-formatted to a consistent style; an automated reflow may rewrap lines and introduce spurious diff noise that would violate the byte-identity AC.
- **F2 debrief citation specificity**: the debrief documents the three F2 L2 mischaracterized test files in "What Could Be Improved §Important — primitive-rename test classification rule" (line 39 of `flight-debrief.md`). Use these exact filenames. The DOM-order divergence is documented at "What Went Well §HAT walk surfaced concrete artifacts" (line 33) AND "What Could Be Improved §Minor — flight-spec wording drift from DOM order" (line 41); reference both wordings for fidelity.
- **`agents.md` size threshold**: the file is currently ~706 lines. Two new conventions add ~30-40 lines. No risk of triggering any size threshold the project enforces.
- **Order-within-leg between the two new conventions**: F2 debrief enumeration lists `primitive-rename-test-classification` first, `flight-spec-dom-order-audit` second. Honor that order (matches F1 L1's "by debrief enumeration order" precedent).

## Files Affected

- `the_one/agents.md` — two new convention entries inserted under `### Project-wide`, placed between `### \`registry-dispatch-create-mode-AC\`` (current bottom of project-wide) and `### Mission-specific (M10)` (current next subsection).
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — L1 checkpoint + L1 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-log.md` — L1 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/legs/01-codify-f2-debrief-conventions.md` — this artifact's status header updated through the leg's lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (grep checks pass; diff is markdown-only; no source files modified)
- [ ] Tests not required for this leg (doc-only); `git diff --stat` confirms no source files touched
- [ ] Update `flight-log.md` with L1 leg-progress entry
- [ ] Set this leg's status to `landed` (Developer signals review-needed; status reaches `completed` after the flight-end code review passes and the final commit lands)
- [ ] Check off L1 in `flight.md` (Checkpoints + Legs sections)
- [ ] Do NOT commit (F3 batches review + commit at flight end per the agentic-workflow protocol)
