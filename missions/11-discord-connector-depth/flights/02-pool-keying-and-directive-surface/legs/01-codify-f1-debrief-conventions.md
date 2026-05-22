# Leg: codify-f1-debrief-conventions

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Codify two F1-debrief-recommended conventions in `the_one/agents.md` so F2 legs 2-5 can reference them by name, mirroring the L1-codification pattern F1 itself established: add `optional-registry-entry-hook` (project-wide; n=3 from F1's three optional hooks `snapshot`/`wireEvents`/`renderInviteSection`) and `registry-dispatch-create-mode-AC` (project-wide; n=1 from F1 L7's HAT-caught create-mode-after-type-pick gap).

## Context

- **Why now**: F1 debrief Recommendation §2 (operator-confirmed) calls for codifying two new conventions: `optional-registry-entry-hook` (the F1 L4+L5 hooks proved the additive-extension shape) and `registry-dispatch-create-mode-AC` (the F1 L7 HAT-discovered create-mode-after-type-pick gap proved the AC pattern). F2 L4 will register a new optional hook (`renderDirectiveSection`) — citing both conventions by name in the L4 spec depends on them existing in `agents.md` first.
- **Source of conventions**: `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-debrief.md` — "Recommendations" section + "Key Learnings §3" (`optional-registry-entry-hook`) + "Action Items" (operator-confirmed at debrief).
- **Scope discipline**: doc-only change. No source modifications. Mirrors F1 L1's structure verbatim — Option C minimum-diff: append new entries under existing `### Project-wide` subsection at the end (after `atomic-leg-pattern`); do NOT renumber or restructure other entries. Preserves git blame.
- **Existing F1 L1 conventions are not edited.** The two new entries are appended at the natural cluster point (right after `atomic-leg-pattern`, before `### Mission-specific (M10)` marker at line 174).
- **Placement decision**: both new conventions are project-wide. `optional-registry-entry-hook` already has n=3 citations from F1 alone, well above the n=2 codification threshold the `function-local-import-to-break-load-cycle` precedent established. `registry-dispatch-create-mode-AC` has n=1 (F1 L7) — below the n=2 threshold technically — but it's promoted on the strength of being a methodology rule the F1 debrief explicitly elevated; the convention is "any registry-mediated typed-render path requires both ACs," not "this is a recurring code pattern." Document the n=1-by-methodology-promotion shape in the convention's body so future readers understand the codification rationale.

## Inputs

Files that must exist:
- `the_one/agents.md` (target — appends after `### \`atomic-leg-pattern\`` body, before `### Mission-specific (M10)` marker)
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-debrief.md` (source for the convention rationales + Recommendations §2 citation)
- F1's `connector-form-registry.js:_validateEntry` and the three optional-hook entries (`snapshot`, `wireEvents`, `renderInviteSection`) — read-only exemplar citations
- F1 L7's `tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form` — read-only exemplar citation for `registry-dispatch-create-mode-AC`

State that must be true:
- F1 is `completed` (confirmed)
- F2 branch `flight/02-pool-keying-and-directive-surface` checked out off F1's branch
- Conventions do NOT yet exist in `agents.md` (verified at design time: `grep "optional-registry-entry-hook\|registry-dispatch-create-mode-AC" the_one/agents.md` returns zero hits)

## Outputs

State changes after this leg:
- `the_one/agents.md` gains two new convention entries under `### Project-wide`, appended after `### \`atomic-leg-pattern\`` and before `### Mission-specific (M10)` marker. Each follows the established shape: heading (`### \`name\``) → definition (2-4 sentences) → applicability boundary ("applies when X; does NOT apply when Y") → exemplar citation(s) → source/back-reference to F1 debrief.
- No other source modifications. `git diff --name-only` shows only `the_one/agents.md` + F2 leg/flight-log artifacts.

## Acceptance Criteria

- [ ] `the_one/agents.md` `### Project-wide` subsection gains two new entries appended after `### \`atomic-leg-pattern\``: `### \`optional-registry-entry-hook\`` and `### \`registry-dispatch-create-mode-AC\``.
- [ ] Existing convention entries (`trust-the-runtime` through `atomic-leg-pattern`) are UNCHANGED — body byte-identical, no rename, no level-shift. Preserves git blame.
- [ ] The `### Mission-specific (M10)` marker and all its child entries remain in place after the two new project-wide entries.
- [ ] `optional-registry-entry-hook` entry contains: (a) 2-4 sentence definition naming the "required-fields-render-time-contract / optional-fields-substrate-integration-opt-ins" shape; (b) applicability boundary ("applies when a registry-mediated dispatch primitive lets per-type entries participate in substrate machinery — dirty tracking, namespace, lifecycle; does NOT apply when the dispatch is a simple value lookup with no substrate-integration surface"); (c) THREE exemplar citations of F1's optional hooks (`snapshot`, `wireEvents`, `renderInviteSection`) with their actual symbolic locations; (d) reference to the validator shape at `connector-form-registry.js:_validateEntry` showing the optionalFns array; (e) source pointer to F1 debrief Key Learnings §3 + Recommendations §2.
- [ ] `registry-dispatch-create-mode-AC` entry contains: (a) 2-4 sentence definition pinning the rule "any registry-mediated typed-render path requires BOTH 'create-mode-after-dispatch-key' AND 'edit-mode-with-key-set' as explicit ACs"; (b) applicability boundary (applies when a registry/dispatch primitive renders different content based on a dispatch key that may be absent on first render — operator-picked type, post-fetch resolved key; does NOT apply when the dispatch key is structurally guaranteed at mount); (c) exemplar citation of F1 L7's HAT-discovered bug at `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectionFields` (the pre-fix shape zeroed the dispatch key in create mode regardless of operator pick; the post-fix shape removed the create-mode zeroing and added a `forceCreate` 5th-arg type-change re-render path) + the resolution test (`tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form`); (d) explicit note that n=1 codification is by methodology-promotion (F1 debrief operator-confirmed), not by recurring-pattern threshold; (e) source pointer to F1 debrief Recommendations §2 + L7 methodology lesson.
- [ ] Each new convention's exemplar citations use SYMBOLIC anchors per F1 debrief Recommendation §3 (no bare line numbers; use `file:symbol` or `file:line — "snippet"` form where line numbers must appear).
- [ ] No source file under `the_one/{db,connectors,agent,tools,interfaces,llm,mcp}/`, `tests/`, or `static/` is modified. Only `agents.md` plus the leg/flight-log artifacts.

## Verification Steps

- `git diff --name-only` — shows only `the_one/agents.md`, the new leg artifact, and `flight-log.md` (plus this file).
- `git diff the_one/agents.md` — shows TWO new convention entries appended in the `### Project-wide` subsection; the diff is purely additive (no removals, no body edits to existing entries).
- `grep -n "^### \`optional-registry-entry-hook\`\|^### \`registry-dispatch-create-mode-AC\`" the_one/agents.md` — both return exactly one hit each.
- `diff <(git show HEAD:the_one/agents.md | grep -c '^### \`') <(grep -c '^### \`' the_one/agents.md)` returns a delta of exactly +2 (two new convention headings appended; no existing headings removed or renamed).
- Existing convention entry verification: `grep -A 1 "^### \`atomic-leg-pattern\`" the_one/agents.md` — first line of body matches the pre-L1 text byte-for-byte.
- `pytest --collect-only -q tests/test_agents_md.py 2>/dev/null || true` — no test file exists for this (no tests gate agents.md); doc-only diff cannot break the suite. Optionally run `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` once to confirm the broader suite stays at F1's 2804 passed baseline.

## Implementation Guidance

1. **Read the source artifacts**:
   - `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-debrief.md` — search for Key Learnings §3 (the `optional-registry-entry-hook` framing) and Recommendations §2 (the codification ask). Note the exact convention names — `optional-registry-entry-hook` (hyphenated) and `registry-dispatch-create-mode-AC` (mixed-case `AC` per F1 debrief verbatim).
   - F1's `connector-form-registry.js:_validateEntry` — the `optionalFns` array at the function body. Three hook names land in there: `'snapshot'`, `'wireEvents'`, `'renderInviteSection'`.
   - F1 L7 leg artifact + flight-log entry — the create-mode bug + the test fix that codified the AC pattern.

2. **Locate the insertion point** in `the_one/agents.md`. Search for `^### \`atomic-leg-pattern\`` (line ~162 at F1 ship; line numbers may drift — use the symbol). The new entries land BETWEEN `atomic-leg-pattern`'s last source-pointer paragraph AND the `### Mission-specific (M10)` marker. The cleanest insertion is immediately before `### Mission-specific (M10)`.

3. **Write the `optional-registry-entry-hook` entry**. Shape mirrors `atomic-leg-pattern` and `protocol-widening-for-required-capability`:
   ```markdown
   ### `optional-registry-entry-hook`

   When a registry entry needs to participate in substrate machinery — dirty tracking, namespace exposure, lifecycle hooks, render-time integrations — add OPTIONAL function fields to the entry's contract, validated as "must be a function IF present" but absent without error. Required entry fields are the render-time contract (the substrate calls them to produce the entry's per-type UI); optional fields are substrate-integration opt-ins (the substrate calls them when its machinery has work to dispatch to the entry, but absence means "this entry doesn't participate at that integration site"). The validator extends linearly: a new optional hook adds one name to an `optionalFns` list, no structural validator change.

   Applies when a registry/dispatch primitive owns substrate-touching machinery (event listeners, snapshot serialization, lifecycle callbacks) where some per-type entries opt in and others don't. Does NOT apply to dispatch tables where every entry must implement every method (use Protocol-widening then; see `protocol-widening-for-required-capability`).

   Citations (n=3 from M11 F1):
   - `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js:_validateEntry` — the `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection']` array; each name is an optional entry-shape hook.
   - F1 L4 added `snapshot(container) → object` (entry's typed-input state for dirty-tracker) + `wireEvents(container, checkDirty, account)` (entry's own listener wiring for typed inputs outside the substrate's delegation scope). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:snapshot` and `:wireEvents`.
   - F1 L5 added `renderInviteSection(account) → string` (entry-rendered detail-page section). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderInviteSection`.

   Source: M11 F1 flight-debrief "Key Learnings §3" (the F1 added three optional hooks; the additive-extension shape is generalizable) + "Recommendations §2" (operator-confirmed codification at debrief).
   ```

4. **Write the `registry-dispatch-create-mode-AC` entry**. Shape:
   ```markdown
   ### `registry-dispatch-create-mode-AC`

   Any registry-mediated typed-render path requires BOTH "create-mode-after-dispatch-key" AND "edit-mode-with-dispatch-key-set" as explicit acceptance criteria. The dispatch key (the value the registry uses to pick a per-type entry — connector type, provider type, plugin type) may be absent at first render in create mode and only populated when the operator picks it; the AC must verify that the post-pick render produces the typed entry's content, not the substrate's fallback. Edit-mode tests alone are insufficient — they exercise the dispatch-key-set path and miss the dispatch-key-absent-then-set transition that operators actually hit.

   Applies when a registry/dispatch primitive renders different content based on a dispatch key that may be absent on first render (operator-picked type in a create form; post-fetch resolved key in an async-populated editor). Does NOT apply when the dispatch key is structurally guaranteed at mount (e.g., the key is part of the URL route fragment and a renderer mounted at all only when the key is present).

   Citation (n=1 from M11 F1 L7, codified by methodology-promotion per F1 debrief Recommendations §2 — operator-confirmed): F1 L4's tests exercised only edit-mode-with-type-set; the create-mode-after-type-pick path was bug-prone because `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectionFields` zeroed the dispatch key (`connActiveType`) in create mode regardless of the operator's pick, so `registry.get('')` always returned undefined and the substrate fallback rendered instead of the typed entry. HAT-caught at F1 L7; the fix removed the create-mode zeroing and added a `forceCreate` 5th-arg type-change re-render path so picking Discord re-mounts the editor against the typed entry. The resolution test `tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form` now pins the AC.

   This is the first codification under the n=1-by-methodology-promotion shape — the F1 debrief elevated this convention on the strength of the methodology lesson (registry-mediated dispatch is a structural pattern that demands symmetric ACs), not on a recurring-pattern threshold. Future occurrences citing this convention re-validate the structural claim; if they don't, the convention is a candidate for retirement at a later mission debrief.

   Source: M11 F1 flight-debrief "Recommendations §2" + "Key Learnings §5" (HAT essential signal even at the end of autonomous flights) + F1 L7 leg-progress entry.
   ```

5. **Insert both entries** at the natural cluster point. The exact order: `optional-registry-entry-hook` first, then `registry-dispatch-create-mode-AC` — they're related (the second is the testing-side complement to the first) and the optional-hook convention is the broader one.

6. **DO NOT modify any other file**. The agents.md edit is the only source-file diff this leg produces. The leg artifact + flight-log are appended in the post-completion step per the v2-protocol shape.

## Edge Cases

- **Convention name typos**: the F1 debrief spells these names verbatim — `optional-registry-entry-hook` (all hyphens) and `registry-dispatch-create-mode-AC` (with uppercase `AC` at the end). Use the exact spellings; future references will grep by name.
- **Citation drift on the connector-form-registry.js optionalFns line**: the array literal sits in `_validateEntry`'s function body. F1 L5 added `renderInviteSection` to it; F2 L4 will add `renderDirectiveSection`. The L1 entry cites the array as it stands at F2-L1-ship time (three names); a future L4 update to the array does NOT invalidate the citation — the convention is about the SHAPE (optionalFns + per-name "must-be-function-IF-present" validation), not the specific membership.
- **Future entries appending after these two**: when F2 L2 or later ships, NONE of these new convention entries get edited inline. Subsequent flights extend the Project-wide list by appending new entries after `registry-dispatch-create-mode-AC`, before `### Mission-specific (M10)`.

## Files Affected

- `the_one/agents.md` — two new convention entries appended in the `### Project-wide` subsection.
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-log.md` — Leg Progress entry appended at leg-completion.
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/01-codify-f1-debrief-conventions.md` — status updates only.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] No source code, test, migration, static asset, or non-agents.md doc modified — `git diff --name-only` shows only `the_one/agents.md` + the two F2 leg/flight-log artifacts
- [ ] Each new convention's exemplar citations grepped against current code and confirmed live (every cited symbol exists in the post-F1 tree)
- [ ] Update `flight-log.md` with a Leg Progress entry (Started / Completed timestamps, Changes Made summary, Notes on any inline decisions)
- [ ] Set this leg's status to `landed` in this file's header
- [ ] Do NOT check off the leg in flight.md (single flight-end commit per agentic-workflow v2 — flight-commit step toggles to `completed`)
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-F1-ship):

- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js:_validateEntry` — verified: the `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection']` array sits in the function body.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:snapshot` + `:wireEvents` + `:renderInviteSection` — verified by `grep -n "function snapshot\|function wireEvents\|function renderInviteSection\|snapshot:\|wireEvents:\|renderInviteSection:" the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — all three present at the entry's registration site.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectionFields` — verified: the function exists; the `connActiveType` hardcoded-`''` shape was the F1 L7 bug; the F1 L7 fix introduced the `forceCreate` 5th-arg + type-select change-listener path.
- `tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form` — verified: the test exists; covers all 7 ACs from the F1 L7 fix per the F1 L7 flight-log Leg Progress entry.
- F1 flight-debrief at `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-debrief.md` — verified: Key Learnings §3 + Recommendations §2 carry the codification asks verbatim with the exact convention names.

Five citation clusters verified live against post-F1 code. No drift.
