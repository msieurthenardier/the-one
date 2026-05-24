# Leg: codify-f3-debrief-conventions-and-criterion-coverage

**Status**: completed
**Flight**: [UX Hotfixes from F3 Debrief](../flight.md)

## Objective

Codify the four F3-debrief-recommended methodology conventions (`pool-warming-entrypoints-are-finite-and-named`, `frozen-snapshot-for-cross-lock-read`, `slot-getter-bridge-for-dropdown-collect-path`, `two-concurrent-callers-reasoning`) as project-wide entries in `the_one/agents.md`, append the two mission-control-targeted recon-discipline notes (`cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding`) as project-side fallbacks under the same `### Project-wide` subsection, and seed `missions/11-discord-connector-depth/criterion-coverage.md` as the M11 living criterion → evidence map so F4-F10 legs can invoke conventions by name and mechanically track criterion coverage.

## Context

- This is the F4 L1 codification leg. It mirrors the F1 L1, F2 L1, and F3 L1 codification precedents — doc-only; no source modifications; conventions land before any source-touching leg so L2-L4 can invoke them by name.
- F3 debrief (`missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-debrief.md`) Recommendations §"Methodology — codify new conventions in agents.md" enumerates conventions 12, 13, 15, 16 (`frozen-snapshot-for-cross-lock-read`, `slot-getter-bridge-for-dropdown-collect-path`, `pool-warming-entrypoints-are-finite-and-named`, `two-concurrent-callers-reasoning`) as the four landing here. Convention 14 (`stub-fixture-extension-via-plugin-connect`) is deliberately deferred — n=2 from F3 alone, awaiting a third citation; F3 debrief's Action Items "Methodology (before F4 planning)" list omits it.
- F4 flight.md Design Decision "Codifications ordering — agents.md L1-style first" pins the placement: all four under `### Project-wide`, with `two-concurrent-callers-reasoning` landing as a regular project-wide convention (NOT a new "Architect-checklist" subsection — agents.md has none; inventing one for n=1 is over-structure). The convention's body describes the architect-checklist application directly (mirrors `flight-spec-dom-order-audit`'s shape — a flight-design-time discipline expressed as a project-wide convention).
- F4 flight.md Design Decision also pins the two recon-discipline notes as project-side fallbacks: `cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding`. F3 debrief Action Items "Methodology (before F4 planning)" lists both as `/flight` skill-prompt changes — out of project scope. The project-side text codifies them in `agents.md` Project-wide as the binding fallback that holds even if mission-control's skill prompts are out of date.
- The seed artifact `missions/11-discord-connector-depth/criterion-coverage.md` realises M10 mission-debrief Recommendation #5 ("Add `criterion → evidence/test` map as a mandatory mission artifact"), un-actioned since M10 close, and explicitly carried forward in the F3 debrief Action Items "Methodology (before F4 planning)" list.
- All four convention entries follow the established 4-block structure: heading → definition paragraph(s) → "Applies … Does NOT apply …" paragraph → `Citation(s):` block (using the inline-parenthetical label shape that names n-count and source flight/leg/cycle) → one-line `Source:` line pointing to the F3-debrief section that triggered codification. The structural reference points are `optional-registry-entry-hook` (`Citations (n=3 from M11 F1):`), `registry-dispatch-create-mode-AC` (`Citation (n=1 from M11 F1 L7, codified by methodology-promotion ...):`), and the F3 L1 outputs `primitive-rename-test-classification` + `flight-spec-dom-order-audit` (the latter is the closest structural twin to `two-concurrent-callers-reasoning` — both express flight-design-time disciplines as project-wide conventions).

## Inputs

- `the_one/agents.md` exists with `### Project-wide` subsection. The current bottom-of-Project-wide entry is `### \`flight-spec-dom-order-audit\`` (last codified at F3 L1; ends at line 222 with its `Source:` line). The next heading at line 224 is `### Mission-specific (M10)`. All four new convention entries plus the two project-side recon-discipline notes insert between line 222 and line 224.
- F3 debrief documents all four conventions plus the two recon-discipline notes with definitions, applicability hints, and citation hints (L4 race-safety catches × 3; L4 `_DiscoverableCacheSnapshot` pattern; L6a/L6b `_xxxValues` getters × 3; L4 pool-warming-assumption miss × 1; F3 recon-table walk discipline; F3 L6b touched-surface miss).
- F3 L1's codification pattern (`missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/legs/01-codify-f2-debrief-conventions.md`) is the immediate structural reference — same shape, same insertion point pattern, same status-progression lifecycle.
- `missions/11-discord-connector-depth/` directory exists; F4 flight directory already exists. The new `criterion-coverage.md` file goes at `missions/11-discord-connector-depth/criterion-coverage.md` (sibling to `mission.md`, not under any flight).

## Outputs

- `the_one/agents.md`'s `### Project-wide` subsection grows four new convention entries plus a final closing project-side note. In source order (matches F3 debrief Recommendations enumeration §12-§16):
  1. `### \`pool-warming-entrypoints-are-finite-and-named\`` (was §15 in debrief; surfaced first in this leg to honor the F4 "A1 closes this gap" framing)
  2. `### \`frozen-snapshot-for-cross-lock-read\`` (was §12)
  3. `### \`slot-getter-bridge-for-dropdown-collect-path\`` (was §13)
  4. `### \`two-concurrent-callers-reasoning\`` (was §16)
  5. `### \`cross-flight-ux-debt-reconciliation\`` (project-side note)
  6. `### \`touched-surface-ux-debt-folding\`` (project-side note)

  All six insert between `### \`flight-spec-dom-order-audit\`` (line 222) and `### Mission-specific (M10)` (line 224). Order is locked above; do not reshuffle.
- The four convention entries follow the established 4-block structure (definition / applicability / `Citation(s):` / `Source:`). The two project-side recon-discipline notes follow the SAME 4-block structure but with the `Citation(s):` block calling out that the convention's primary destination is a mission-control skill prompt and the agents.md entry is the project-side fallback (matches the project-versus-mission-control split documented in F4 flight.md Design Decisions).
- `missions/11-discord-connector-depth/criterion-coverage.md` is created with:
  - Header naming the document, the mission, and the maintenance contract (per-flight debrief updates affected rows; failure to update is a methodology violation surfaced at flight-debrief time — applies the `mechanical-fallback-prompt-truth-pairing` convention recursively).
  - Table with one row per M11 mission criterion (19 rows, mirroring `mission.md` lines 25-43 verbatim-summarized into one-line excerpts).
  - Columns: `# | Criterion (excerpt) | Status | Evidence | Last touched`.
  - Status vocabulary: `closed-by-Fn` / `partially-closed-by-Fn` / `structurally-complete-pending-HAT` / `open`. Document the vocabulary in the header.
  - Initial status reflects flight progress at F3 close (seed as-of 2026-05-23): criteria #1 (Discord-shaped form) `closed-by-F1`; criteria #14 (operator-editable directive) `closed-by-F2`; criterion #16 (pool refactor) `closed-by-F2`; criteria #3 + #4 (allowlist + routing dropdowns) `partially-closed-by-F3` (structurally complete; stale-entry deferred); all other criteria `open`. F4 itself does NOT prefill its own contributions — those land at F4 debrief gate per the maintenance contract.
  - Evidence column for `closed-by-Fn` rows cites the named flight + key test file(s) from the relevant flight debrief. F3-touched rows cite F3 L4-L6b leg numbers + the L7 HAT outcome.
  - Last-touched column makes drift-detection mechanical at debrief time.
- No source code modifications. No test modifications.
- Sibling artifact bookkeeping (explicit scope): F4 `flight.md`'s L1 Checkpoints entry + L1 Legs checklist item checked off; F4 `flight-log.md`'s Leg Progress section grows an L1 entry; this leg artifact's Status header progresses through its lifecycle (`planning` → `ready` after design review approves → `in-flight` when Developer starts → `landed` when Developer signals review-needed → `completed` after flight-end code review passes and commit lands).

## Acceptance Criteria

- [x] `the_one/agents.md` contains a new heading `### \`pool-warming-entrypoints-are-finite-and-named\`` placed immediately after the `\`flight-spec-dom-order-audit\`` entry (heading currently at line 214; entry ends at its `Source:` line at 222).
- [x] `the_one/agents.md` contains a new heading `### \`frozen-snapshot-for-cross-lock-read\`` placed immediately after the new `pool-warming-entrypoints-are-finite-and-named` entry.
- [x] `the_one/agents.md` contains a new heading `### \`slot-getter-bridge-for-dropdown-collect-path\`` placed immediately after the new `frozen-snapshot-for-cross-lock-read` entry.
- [x] `the_one/agents.md` contains a new heading `### \`two-concurrent-callers-reasoning\`` placed immediately after the new `slot-getter-bridge-for-dropdown-collect-path` entry.
- [x] `the_one/agents.md` contains a new heading `### \`cross-flight-ux-debt-reconciliation\`` placed immediately after the new `two-concurrent-callers-reasoning` entry.
- [x] `the_one/agents.md` contains a new heading `### \`touched-surface-ux-debt-folding\`` placed immediately after the new `cross-flight-ux-debt-reconciliation` entry and immediately before `### Mission-specific (M10)`. (The six new entries appear in this exact order: pool-warming → frozen-snapshot → slot-getter → two-concurrent-callers → cross-flight-ux-debt → touched-surface-ux-debt.)
- [x] The `pool-warming-entrypoints-are-finite-and-named` entry contains a definition paragraph stating: any subsystem with a pool primitive must explicitly enumerate the entrypoints that warm the pool; design-time reasoning may not assume that any operator-triggered action implicitly populates the pool unless the action's handler explicitly calls one of the named entrypoints. `grep` for the entrypoint name in the candidate handler is the mechanical fallback that converts assumed-warming into verified-warming. (Specific code references — `account_acquire`, `pool_acquire`, the lifespan listener-warmup path — land in the citation block, not the definition.)
- [x] The `pool-warming-entrypoints-are-finite-and-named` entry contains an applicability paragraph: applies whenever a flight or leg artifact's design assumes a pool entry is warm at a given UX-trigger point. Does NOT apply to read-only pool inspection paths or to lifespan-driven warmup (which is structurally-guaranteed at startup, not operator-triggered).
- [x] The `pool-warming-entrypoints-are-finite-and-named` entry uses the citation-label shape `Citation (n=1 from M11 F3 L4 design-time + L7 HAT anomaly #1, codified by methodology-promotion per the same F1-L7-derived precedent as \`registry-dispatch-create-mode-AC\`):` and documents: F3 L4's design assumed Test Connection populated the pool via the lifespan-listener-warmup path (a named entrypoint in `the_one/connectors/_pool.py`); the assumption was structurally false — Test Connection's handler at `the_one/interfaces/web/api.py:test_connector_connection` calls `plugin.doctor()` but never `account_acquire`; HAT step caught the gap at F3 L7 (dropdowns 404 immediately after Test Connection succeeded); the F4 L2 leg is closing the underlying code-side mismatch by wiring `account_acquire` after `doctor()` succeeds. The convention codifies the methodology fallback that prevents recurrence: enumerate-and-grep at design time.
- [x] The `pool-warming-entrypoints-are-finite-and-named` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Critical §3" + "Key Learnings §2" + "What Could Be Improved §Process — recon should default-walk L1 codifications."`
- [x] The `frozen-snapshot-for-cross-lock-read` entry contains a definition paragraph stating: when handler code reads multi-field cache state outside the lock that protects mutation, build a frozen-snapshot dataclass inside the lock and return the snapshot for outside-the-lock consumption. The pattern prevents inconsistent-multi-field-read races without requiring all readers to hold the lock for the entire read window.
- [x] The `frozen-snapshot-for-cross-lock-read` entry contains an applicability paragraph: applies whenever a cache or shared mutable state exposes multiple correlated fields that callers may read outside the mutation lock. Does NOT apply to single-field atomic reads or to fully-immutable shared state.
- [x] The `frozen-snapshot-for-cross-lock-read` entry uses the citation-label shape `Citation (n=1 from M11 F3 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as \`registry-dispatch-create-mode-AC\`):` and documents the F3 L4 architect cycle-1 catch: the cache exposes `(client_id, entities, last_refresh)` triple that handler code reads outside the lock; cycle-1 introduced `_DiscoverableCacheSnapshot` as the frozen-triple dataclass returned from a lock-held read.
- [x] The `frozen-snapshot-for-cross-lock-read` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Methodology §12" + "Deviations and Lessons Learned" table (L4 \`_DiscoverableCacheSnapshot\` row).`
- [x] The `slot-getter-bridge-for-dropdown-collect-path` entry contains a definition paragraph stating: when a new editor shape (e.g., a dropdown chip-list) must integrate with an existing DOM-walking collect path that expects a specific child-element shape (e.g., text nodes), install a function-valued property (a slot getter) on the slot's container element that the collect path can invoke to retrieve the editor's current values. The getter bridges the new editor shape to the existing collect path without rewriting either side.
- [x] The `slot-getter-bridge-for-dropdown-collect-path` entry contains an applicability paragraph: applies whenever a new UI editor surface must integrate with a pre-existing DOM-walking collect/serialize path that doesn't natively understand the new editor's DOM shape. Does NOT apply when the collect path can be cleanly rewritten in lockstep with the new editor.
- [x] The `slot-getter-bridge-for-dropdown-collect-path` entry uses the citation-label shape `Citations (n=3 from M11 F3 L6a + L6b):` and documents the three sites: `_allowlistValues` (L6a allowlist), `_routingMatchValues` (L6b routing match-value), `_overlayChipValues` (L6b per-agent overlay) — each installed as a function-valued property on a slot container element so the existing `collectAllowlistFromContainer` text-node walk can extract dropdown selections without rewriting the collect path.
- [x] The `slot-getter-bridge-for-dropdown-collect-path` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Methodology §13" + "Deviations and Lessons Learned" table (L6a/L6b row).`
- [x] The `two-concurrent-callers-reasoning` entry contains a definition paragraph stating: at design-review time, when a leg touches code that may be invoked by two or more concurrent callers (handler + background task; refresh-loop + read-loop; lifespan-warmup + operator-triggered acquire), the architect must walk the two-concurrent-callers thought experiment for every shared mutable state the leg touches. Sketch-based reasoning about a single caller is not naturally extended to two concurrent callers; the discipline is to explicitly enumerate the second caller, the interleaving point, and the partial-success / partial-failure shape.
- [x] The `two-concurrent-callers-reasoning` entry contains an applicability paragraph: applies whenever a leg touches code that may be invoked by two or more concurrent callers and the leg modifies or reads shared mutable state (in-process caches, locks, pool entries, refresh loops). Does NOT apply to leg-internal pure functions or to single-caller-by-design paths (e.g., startup-only initialization that the runtime guarantees against re-entry).
- [x] The `two-concurrent-callers-reasoning` entry uses the citation-label shape `Citation (n=3 from M11 F3 L4 cycle-1 within a single leg, codified by methodology-promotion per the same F1-L7-derived precedent as \`registry-dispatch-create-mode-AC\`):` and enumerates the three F3 L4 cycle-1 catches: (1) `prior_cache` race between refresh-loop and operator-triggered read; (2) `_shutting_down` bail interleaving with re-acquire; (3) identity-check on `client` to detect mid-refresh reconnection. All three would have been cycle-0-discoverable had the architect explicitly walked the two-concurrent-callers thought experiment.
- [x] The `two-concurrent-callers-reasoning` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Methodology §16" + "Key Learnings §4 — cycle-1 race-reasoning has limits."`
- [x] The `cross-flight-ux-debt-reconciliation` entry contains a definition paragraph stating: every flight's reconnaissance phase MUST include a section walking the prior 2-3 flight debriefs' AND the parent mission-debrief's deferred-UX items, classifying each as "in-scope-for-this-flight" / "out-of-scope-with-reason" / "structurally-blocked-by-X." The discipline arrests the "fold into F8/F10/follow-on-mission" structural source of UX-debt accumulation by forcing each new flight to explicitly cross-check the deferred queue rather than passively inheriting it.
- [x] The `cross-flight-ux-debt-reconciliation` entry contains an applicability paragraph: applies to every flight reconnaissance phase. Does NOT apply to the first flight of a mission (no prior debriefs to cross-check) — though that flight should still cross-check the mission-debrief of any predecessor mission whose work it inherits.
- [x] The `cross-flight-ux-debt-reconciliation` entry uses the citation-label shape `Citation (n=1 from M11 F3 debrief root-cause analysis, codified by methodology-promotion):` and documents: F3 debrief surfaced an n=1 trigger of the 4-step UX-debt-accumulation pattern (HAT discovers → deferred → subsequent flight touches surface → deferral not folded). The primary codification destination is mission-control's `/flight` skill prompt (out of project scope); this agents.md entry is the project-side binding fallback that holds even if the mission-control skill prompts are out of date. The F4 `flight-log.md`'s Reconnaissance Report (Recon table R1-R11) is the n=1 application of this discipline.
- [x] The `cross-flight-ux-debt-reconciliation` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Critical §1" + "UX-Debt Accumulation §Root cause of the accumulation pattern."`
- [x] The `touched-surface-ux-debt-folding` entry contains a definition paragraph stating: when a flight touches a code surface (file or component), the architect MUST enumerate all open UX-debt items against that surface from prior debriefs and either fold them in or explicitly state why they're left. The discipline prevents the "touched the file but missed the gap" failure mode (F3 L6b touched `connectors-tab.js` but missed A2's raw-id checkbox-mode rendering because the leg's contributing-criteria framing was narrow).
- [x] The `touched-surface-ux-debt-folding` entry contains an applicability paragraph: applies whenever a leg's Files Affected list includes a source file with open UX-debt items in prior debriefs. Does NOT apply to files with no prior-debrief UX-debt entries.
- [x] The `touched-surface-ux-debt-folding` entry uses the citation-label shape `Citation (n=1 from M11 F3 L6b miss, codified by methodology-promotion):` and documents the F3 L6b case: the leg touched `connectors-tab.js:_renderAccountTile` for per-agent overlay dispatch but did not fold A2 (checkbox-mode raw-id rendering) into scope; A2 surfaced at F3 L7 HAT and is now closed by F4 L3. The primary codification destination is mission-control's `/flight` skill prompt (out of project scope); this agents.md entry is the project-side binding fallback.
- [x] The `touched-surface-ux-debt-folding` entry ends with a one-line `Source:` line: `Source: M11 F3 flight-debrief "Recommendations §Critical §2" + "What Could Be Improved §Process — touched-surface UX-debt folding."`
- [x] `missions/11-discord-connector-depth/criterion-coverage.md` exists as a new file (the path did not exist before this leg).
- [x] The file's header contains: title (`# M11 Criterion Coverage`); a one-sentence purpose statement ("Living artifact mapping each M11 mission criterion to evidence (specific tests, leg references, debrief sections, HAT outcomes)."); the status vocabulary (`closed-by-Fn` / `partially-closed-by-Fn` / `structurally-complete-pending-HAT` / `open`) defined inline; the maintenance contract (each flight's debrief updates affected rows; the `Last touched` column makes drift-detection mechanical; failure to update is a methodology violation that the flight-debrief skill should surface in its own debrief).
- [x] The file's main body is a Markdown table with 19 rows (one per M11 mission criterion, in `mission.md` source order), with columns `# | Criterion (excerpt) | Status | Evidence | Last touched`.
- [x] Initial status values: row 1 (Discord-shaped form) `closed-by-F1`; rows 2 (vocabulary substitution) `partially-closed-by-F1+F3`; rows 3 (allowlist dropdowns) + 4 (routing dropdowns) `partially-closed-by-F3` with the stale-entry-indicator caveat noted; row 14 (operator-editable directive) `closed-by-F2`; row 16 (pool refactor) `closed-by-F2`; all other 13 rows `open`.
- [x] Evidence column entries for closed rows cite the flight number + 1-3 key test names or leg references (e.g., row 1: `F1 L1-L7; tests/browser/test_flow_studio_discord_account_creation.py`).
- [x] `Last touched` column entries match the flight that most recently moved the row's status (e.g., row 1: `F1`; row 3: `F3`; open rows: `—` or blank).
- [x] `git diff the_one/agents.md` shows only insertions between `### \`flight-spec-dom-order-audit\``'s `Source:` line and `### Mission-specific (M10)`; the rest of the file is byte-identical (no whitespace adjustments, no reflow, no linter-driven adjustments to existing entries).
- [x] `git diff --stat` shows changes only in `the_one/agents.md`, the new `missions/11-discord-connector-depth/criterion-coverage.md`, plus F4 sibling artifacts (`flight.md`, `flight-log.md`, this leg artifact). No `*.py`, `*.js`, `*.ts`, `*.tsx`, `*.json`, `*.sql`, or other source files in the diff.

## Verification Steps

- `git diff the_one/agents.md` shows six new sections inserted between `### \`flight-spec-dom-order-audit\``'s last line and `### Mission-specific (M10)`. No other diff hunks in `agents.md`.
- `git status` shows `missions/11-discord-connector-depth/criterion-coverage.md` as a new file.
- `git diff --stat` for the working tree shows changes ONLY in `the_one/agents.md`, the new `criterion-coverage.md`, and F4 sibling artifacts. No source files (`*.py`, `*.js`, `*.ts`, `*.tsx`, `*.json`, `*.sql`) in the diff.
- `grep -nE "^### \`(pool-warming|frozen-snapshot|slot-getter|two-concurrent|cross-flight-ux-debt|touched-surface-ux-debt)" the_one/agents.md` returns exactly six hits, in the expected order (the broadened prefix tolerates accidental hyphen-variant drift while still pinning each new convention).
- `grep -n "^## \|^### " the_one/agents.md` heading list shows the six new entries in the expected positions (between `flight-spec-dom-order-audit` and `Mission-specific (M10)`).
- `wc -l missions/11-discord-connector-depth/criterion-coverage.md` returns a non-trivial line count (>= 30 lines: header + 19 criterion rows + table header + separator + maintenance-contract paragraph).
- `grep -c "^| [0-9]" missions/11-discord-connector-depth/criterion-coverage.md` returns 19 (one numbered row per criterion).
- `pytest` is NOT required for this leg (doc-only, markdown-only changes). The `git diff --stat` step above is the defensive verification that no source files were inadvertently touched.

## Implementation Guidance

1. **Read the current state of `the_one/agents.md` around the insertion point** (lines 214-226).
   - Confirm `### \`flight-spec-dom-order-audit\`` runs from line 214 with its `Source:` line at line 222 followed by a blank line and `### Mission-specific (M10)` at line 224.
   - Confirm the convention-entry format from `optional-registry-entry-hook`, `registry-dispatch-create-mode-AC`, `primitive-rename-test-classification`, and `flight-spec-dom-order-audit` as the structural reference.

2. **Insert the six new entries between line 222 and line 224, in this exact order:**
   1. `pool-warming-entrypoints-are-finite-and-named`
   2. `frozen-snapshot-for-cross-lock-read`
   3. `slot-getter-bridge-for-dropdown-collect-path`
   4. `two-concurrent-callers-reasoning`
   5. `cross-flight-ux-debt-reconciliation`
   6. `touched-surface-ux-debt-folding`

3. **For each entry, follow the established 4-block structure**:
   - Heading: `### \`<convention-name>\``
   - Definition paragraph(s) — content from the AC list above (lock the wording to the AC; do not paraphrase loosely).
   - Applicability paragraph: "Applies whenever … Does NOT apply to …"
   - Citation block: use the citation-label shape locked in the AC list. For conventions with multiple citation sites (slot-getter-bridge has n=3), enumerate each site with a one-phrase note.
   - One-line `Source:` line: use the exact text locked in the AC list.

4. **Special handling for the two project-side recon-discipline notes** (`cross-flight-ux-debt-reconciliation` + `touched-surface-ux-debt-folding`):
   - Same 4-block structure.
   - The Citation block calls out explicitly that the primary codification destination is a mission-control skill prompt (out of project scope) and this agents.md entry is the project-side fallback. This framing matches F4 flight.md Design Decisions and prevents future confusion about why a "recon discipline" lives in agents.md instead of (or in addition to) `/flight` skill prompts.

5. **Create `missions/11-discord-connector-depth/criterion-coverage.md`** as a new file at the path `missions/11-discord-connector-depth/criterion-coverage.md` (sibling to `mission.md`, not under any flight directory).
   - Header structure (in order): `# M11 Criterion Coverage` (h1) → one-sentence purpose statement → status-vocabulary paragraph → maintenance-contract paragraph → blank line → table.
   - Table header: `| # | Criterion (excerpt) | Status | Evidence | Last touched |` then the separator row.
   - Table body: 19 rows, one per M11 criterion. Row order matches `mission.md` lines 25-43 (Discord-shaped form → vocabulary substitution → allowlist dropdowns → routing dropdowns → multi-user routing → multi-channel routing → multi-peer/agent routing → pairing → detach → slash commands → HAT script → mentions-aware policy → peer-name attribution → operator-editable directive → pool refactor → audit-log inspector → rate-limiting → 15-minute walkthrough → full-day robust).
   - For each row's "Criterion (excerpt)" cell, summarize the criterion in ONE-LINE (~10-15 words) — operator must be able to identify the criterion without consulting `mission.md`, but the cell must NOT bloat the table.
   - Initial Status + Evidence + Last-touched values per the AC list. F4 itself does not prefill its own row contributions; those land at F4 debrief gate.

6. **Update F4 `flight.md`'s Checkpoints checkbox for L1.**
   - The L1 checkpoint at flight.md Checkpoints already has its description; check it off (the `- [x]` becomes `- [x]`).

7. **Update F4 `flight.md`'s Legs checklist for L1.**
   - The L1 entry in the Legs section: check off the `- [x]`.

8. **Update F4 `flight-log.md`'s Leg Progress section with a new L1 entry.**
   - Heading: `### L1 — codify-f3-debrief-conventions-and-criterion-coverage`
   - Status: `landed` (when post-completion checklist runs); becomes `completed` after the flight-end commit lands per the agentic-workflow batched-review protocol.
   - Brief Changes Made / Notes / outcomes: 4 conventions + 2 project-side notes inserted; criterion-coverage.md seeded with 19 rows.

9. **Update this leg artifact's Status header** progressively: `planning` → `ready` (after design review approves) → `in-flight` (when Developer agent starts) → `landed` (when Developer signals review-needed) → `completed` (after final code review at flight gate).

## Edge Cases

- **Existing convention names collide**: `grep` `the_one/agents.md` for each of the six new names BEFORE inserting to confirm zero hits. F4 recon table R4-R8 already verified this; re-verify defensively because the developer may run against a state that drifted.
- **Markdown-linter-driven reflow**: do NOT run a markdown linter or formatter against the file. The existing entries were hand-formatted to a consistent style; an automated reflow may rewrap lines and introduce spurious diff noise that would violate the byte-identity AC.
- **F3 debrief citation specificity**: the debrief documents the four conventions at "Recommendations §Methodology §12-§16" (line 152 onward) and the two recon-discipline notes at "Recommendations §Critical §1-§2" (line 145 onward). Use the section-pointer wording exactly as locked in the AC `Source:` lines.
- **`agents.md` size threshold**: the file is currently ~731 lines. Six new entries add ~80-100 lines. No risk of triggering any size threshold the project enforces.
- **Order-within-leg between the six new entries**: F3 debrief Recommendations enumerates §12 (frozen-snapshot), §13 (slot-getter), §14 (stub-fixture — excluded), §15 (pool-warming), §16 (two-concurrent-callers). F4 flight.md Design Decision reorders to surface pool-warming first (honors the F4 "A1 closes this gap" narrative) and groups the two recon-discipline notes at the tail (they're not conventions in the F1-precedent sense — they're project-side fallbacks). Honor the F4-flight-design order locked in the AC list.
- **Citation count for `pool-warming-entrypoints-are-finite-and-named`**: the convention has n=1 evidence from L4 design + L7 HAT (same flight; one root cause). The citation-label uses "L4 design-time + L7 HAT anomaly #1" wording to surface both surfaces without inflating the n-count.
- **Citation count for `frozen-snapshot-for-cross-lock-read`**: n=1 from L4 cycle-1. The convention codifies on the methodology-promotion precedent (matches `registry-dispatch-create-mode-AC`'s n=1 + `primitive-rename-test-classification`'s n=1 trigger). The citation-label uses the F1-L7-derived precedent reference.
- **Citation count for `slot-getter-bridge-for-dropdown-collect-path`**: n=3 within F3 alone (L6a allowlist + L6b routing match + L6b per-agent overlay). The citation-label uses `Citations (n=3 from M11 F3 L6a + L6b):` matching `optional-registry-entry-hook`'s n=3 shape.
- **Citation count for `two-concurrent-callers-reasoning`**: n=3 within L4 alone (the three architect-cycle-1 race-safety catches). The citation-label uses `Citation (n=3 from M11 F3 L4 cycle-1 within a single leg, codified by methodology-promotion ...):` to surface that the three sites are all within one leg (not three independent flights).
- **`criterion-coverage.md` row count**: M11 mission.md lines 25-43 enumerate 19 criteria (confirmed by `sed -n '25,43p' missions/11-discord-connector-depth/mission.md | grep -c '^- \[ \]'`). The seed file table has exactly 19 numbered rows.
- **`criterion-coverage.md` placement**: the file lives at `missions/11-discord-connector-depth/criterion-coverage.md` (sibling to `mission.md`), NOT under any flight directory. The file is mission-scoped; flights update it at debrief time per the maintenance contract.
- **F4 row-prefill discipline**: F4 itself does NOT mark its own contributions in the initial seed (e.g., does not pre-mark rows #18 + #19 as `partially-closed-by-F4`). Those land at F4 debrief gate. The seed captures state at F3 close + F4 start.

## Files Affected

- `the_one/agents.md` — six new convention entries inserted under `### Project-wide`, placed between `### \`flight-spec-dom-order-audit\``'s last line (current line 222) and `### Mission-specific (M10)` (current line 224).
- `missions/11-discord-connector-depth/criterion-coverage.md` — new file; living criterion → evidence map for M11 with 19 rows + maintenance contract.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight.md` — L1 checkpoint + L1 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/flight-log.md` — L1 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/04-ux-hotfixes-from-f3-debrief/legs/01-codify-f3-debrief-conventions-and-criterion-coverage.md` — this artifact's status header updated through the leg's lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified (grep checks pass; diff is markdown-only; no source files modified; criterion-coverage.md has 19 numbered rows)
- [x] Tests not required for this leg (doc-only); `git diff --stat` confirms no source files touched
- [x] Update `flight-log.md` with L1 leg-progress entry
- [x] Set this leg's status to `landed` (Developer signals review-needed; status reaches `completed` after the flight-end code review passes and the final commit lands)
- [x] Check off L1 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F4 batches review + commit at flight end per the agentic-workflow protocol)

---

## Citation Audit

All code-location citations in this leg artifact verified against current code at leg design time (2026-05-23):

- `the_one/agents.md:214` — `### \`flight-spec-dom-order-audit\`` confirmed at line 214.
- `the_one/agents.md:222` — `flight-spec-dom-order-audit` `Source:` line confirmed at line 222.
- `the_one/agents.md:224` — `### Mission-specific (M10)` confirmed at line 224.
- `the_one/interfaces/web/api.py:test_connector_connection` — symbol cited in `pool-warming-entrypoints-are-finite-and-named` body; verified in F4 recon table R1 against current source (`sed -n '2573,2638p'` confirms zero `account_acquire` references in the handler).
- `missions/11-discord-connector-depth/mission.md` lines 25-43 — 19 `- [x]` rows confirmed (`sed -n '25,43p' | grep -c '^- \[ \]'` = 19 as-of 2026-05-23).
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-debrief.md` — section headings (Recommendations §Critical §1-§3; §Methodology §12-§16; Key Learnings §2 + §4; UX-Debt Accumulation §Root cause) confirmed against current source.

5 code-location citations + 1 line-range count verified clean. No drift repaired.

**Deferred convention tracking** (does not affect this leg's ACs): `stub-fixture-extension-via-plugin-connect` (F3 debrief Recommendation §14) is deliberately omitted from this leg — n=2-from-F3-alone awaits a third citation per the methodology-promotion threshold. The deferral is recorded in F4 `flight-log.md`'s Session Notes so future flights can re-evaluate when they touch the stub fixture surface.
