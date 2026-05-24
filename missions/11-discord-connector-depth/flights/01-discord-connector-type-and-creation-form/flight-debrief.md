# Flight Debrief: Discord Connector-Type Registration + Discord-Shaped Creation Form

**Date**: 2026-05-21
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](flight.md)
**Status**: landed
**Duration**: 2026-05-21 (planning + execution + HAT all same day under `/agentic-workflow` orchestration)
**Legs Completed**: 7 of 7 (L1-L6 autonomous + L7 HAT)

## Outcome Assessment

### Objectives Achieved

F1 closed the "operator sees Discord shape, not substrate shape" promise at the creation and detail surfaces. The two contributing-to-criteria items both met:

- ✅ The existing `'discord'` connector-type registration grew a Discord-shaped UI surface (typed BOT_TOKEN with masked-edit, three intent checkboxes with safe defaults, optional guild scoping, presence editor, always-mounted Invite section with computed OAuth2 URL, Advanced kv-table disclosure).
- ✅ Every Discord-touching user-facing surface (Allowlist labels + hints, Attached Agents headers, Routing-scope dropdown textContent) speaks Discord vocabulary. Substrate code (`_VALID_ROUTING_SCOPES`, ACL field names, Pydantic models, audit-log keys) unchanged — verified by `grep` parity pre/post L6.

### Mission Criteria Advanced

- M11 criterion #1 (Discord connector-type six-layer checklist): closed at the API-gating layer (L2) and the default-config / Discord-shaped form layer (L4).
- M11 criterion #2 (Discord vocabulary on user-facing surfaces): closed for the Allowlist + Attached-agents + Routing-scope dropdown surfaces; chip-input placeholders flagged as non-blocking polish.

Two commits shipped: `40660a1` (L1-L6 atomic per agentic-workflow v2) + `94a10a6` (L7 walk + create-mode fix). PR #69 ready for review.

## What Went Well

- **Substrate-neutrality constraint held end-to-end.** L6's grep parity (`'"peer"'` over `db/models.py`, `connectors/_acl.py`, `_inbound.py`, `_routing.py`) confirmed identical hit counts pre/post. The "internal scope values stay generic; display labels switch" line proved the right architectural boundary.
- **L1's codification of M10 conventions paid off immediately.** `atomic-leg-pattern` was cited by name in L2 to bind validator + plugin + tests; `prompt-discipline-needs-mechanical-fallback` was cited at L7-fix-time to confirm the create-mode re-render fix did NOT reverse a substrate contract. Convention names became operational vocabulary, not aspirational notes.
- **Registry-mediated approach (Path B) decisively beat substrate-level type-gated branching (Path A).** L4's dirty-tracker gap (HIGH cycle-1) was resolved by adding ONE optional registry-entry hook (`wireEvents`), not by extending the substrate's `attachStaticListeners` with type-gated branches. L5 added the invite section the same way. Path A would have meant `if (type === 'discord')` branches in three substrate functions.
- **L5 implementer caught the spec's permissions-integer math error** (spec said `2147552768`; correct value `2147552256` because JS `1<<31` is signed-int32 negative). Empirically validated at L7 against gleepglorp's real `application_id`. Net: the methodology surfaced a design-time math error before it shipped.
- **L7 HAT methodology found the create-mode-after-type-pick bug** that no automated test caught. The HAT-fix-inline path (Developer agent + browser test added) preserved the L1 `prompt-discipline-needs-mechanical-fallback` substrate-contract-reversal check.
- **Two-cycle design review caught HIGH-severity issues in every code-touching leg** (L2, L3, L4, L5, L6). Cycle-2 approved clean each time. The process worked; it's now load-bearing.

## What Could Be Improved

### Process

- **Critical — design-review cycle-1 was catching what cycle-0 should have caught.** Pattern across L2-L6: HIGH-severity issues were "you cited symbol X, but X's actual shape is Y" or "you assumed event delegation reaches input Z, but the dirty-tracker scope-selector excludes Z." The architect's first pass relied on the leg author's claims; the second pass actually grepped. **Codify three Architect-checklist items**: (a) grep every cited symbol's actual shape; (b) walk the event-delegation / dirty-tracker / lifecycle paths the new code participates in; (c) compute and verify every numeric constant.
- **Important — L4 size signal was missed at flight design.** L4 shipped ~620 LOC source + 200 LOC tests because it landed (a) registry-entry shape extension, (b) Discord entry with 6 functions, (c) substrate `snapshot`/`wireEvents`/namespace-exposure extensions, (d) 11 browser tests. The atomic-leg-pattern correctly bound it — splitting would have shipped a broken interim state. But the substrate-registry contract (3 optional hooks) wasn't fully scoped at flight-design time; had they been, L3 would have shipped them and L4 would be ~400 LOC. **Recommendation**: at flight design, walk the planned-leg's downstream substrate touches and pull them into the foundation leg.
- **Important — L7 UAT was nominally optional but caught a HIGH-severity create-mode bug** that L4's tests (all-edit-mode) didn't exercise. The L4 leg's Edge Cases section mentioned "Operator creates a new Discord account" but no AC pinned create-mode-after-type-pick as a verification gate. **Codify**: any registry-mediated typed-render path requires BOTH 'create-mode-after-dispatch-key' AND 'edit-mode-with-key-set' as explicit ACs.
- **Minor — citation drift recurred across L1, L4, L5.** Leg specs that pin line numbers drifted as preceding legs landed. Fix consistently applied: anchor to symbol or section-separator, not line number. Worth promoting from per-leg fix to flight-wide methodology.

### Technical

- **Minor — `MASKED_SENTINEL` string-literal duplication** between `connector-account-editor.js:47` and `connector-form-discord.js:38`. IIFE-closure scoping forced re-declaration. Candidate for a shared studio-namespace constant.
- **Minor — `_resolveAccountFromContainer` parses `window.location.hash`** because the editor's mount lacks a `data-account-id` attribute. Works today; couples to route shape. Two-line refactor: add `data-account-id` at editor mount, replace the hash parse.
- **Minor — `_probe_gateway_connect` at `_discord.py:1421`** still uses hardcoded intents (out of L2 scope). The L2 contract was "lines 619-622 only"; the doctor probe's parity-test path is unaffected operationally but the convention `cross-subsystem-pattern-premise-revalidation` would have flagged it.
- **Minor — `wireEvents` signature grew from `(container, checkDirty)` to `(container, checkDirty, account)` mid-flight.** Extra-args-are-ignored backward compat is fine in JS but the protocol is now positional + grows-positionally. If a fourth context arg is needed, consider switching to a single options-object.
- **Non-blocking — chip-input placeholders not vocabulary-substituted.** L6 substituted Allowlist section labels and hints to "Users / Servers / etc." but missed the chip inputs inside those sections (still show "Add peer..." / "Add guild..."). Deferred to M11 F10 Alignment.
- **Non-blocking — Discord create-form visual rhythm is cramped.** Step 2 screenshot showed intent checkboxes + help text wrapping tightly; Guilds + Presence labels squashed. Vibe-coding territory; deferred to M11 F10 Alignment.

### Test Coverage

- **L4 missed create-mode-after-type-pick as an AC.** Tests covered edit-mode only. L7-fix added `test_create_mode_pick_discord_renders_typed_form`.
- **Probe-to-invite-URL flow has no end-to-end test.** L5 tests stub the route response; no test exercises the real `handleTestConnection` success-path callback → `setApplicationId` → URL re-render.
- **`auto_relay_platform_replies` reserved-key gap untested.** L3 explicitly deferred the kv-table-shows-it-twice bug; no test pins current behavior.

### Documentation

- **Important — connector-form-registry public contract is spread across L3+L4+L5 leg artifacts.** Future entry authors (M12 second connector) shouldn't need to read 3 leg specs. Consolidate into a short doc — recommended: extend `connector-form-registry.js` top comment with the optional-hook table, or add `static/js/areas/studio/README.md`.
- **Minor — vocabulary substitution coverage map missing.** L7 surfaced the chip-input placeholder gap empirically; a written audit of "which surfaces consult `connectorVocabulary`; which don't" would catch it earlier.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L4 `wireEvents` signature grew from 2-arg to 3-arg mid-flight | L5 invite-section needed `account` for hash-derived account_id lookup | **No** — JS positional-grow is fragile; switch to options object before the 4th arg |
| L5 permissions integer `2147552768` → `2147552256` (math error in spec) | JS `1<<31` is signed-int32; even unsigned, spec's stated sum was off by 512 | **Yes — codify "pin computed constants at design time"** as an Architect-checklist item |
| L4 didn't ship the `renderConfigKvTable` namespace exposure proactively | Pre-existing IIFE-local function; spec hedged "expose if not already" | **Yes — pre-existing IIFE encapsulation is a design-time concern**; explicit exposure decisions should land at flight-design |
| L7 fixed create-mode bug inline (not deferred to follow-up flight) | Caught at HAT; small fix surface (~55 LOC source + 78 LOC test); didn't reverse a substrate contract | **Conditional** — inline-fix-at-HAT is correct when the fix passes the substrate-reversal check (`prompt-discipline-needs-mechanical-fallback`); else pause and re-review |

## Key Learnings

1. **The cycle-1 → cycle-2 design-review process is the system's strength, not its weakness, but it currently does work cycle-0 should do.** HIGH-severity issues in 4 of 6 legs' cycle-1 reviews were "actually walk the runtime path" findings the architect's first pass missed. Adding three checklist items to the design-review prompt (grep cited symbols; walk delegation paths; verify computed constants) moves these catches earlier without removing the second pair of eyes.

2. **Substrate-neutrality is preserved by registry-mediated dispatch, NOT by spec discipline alone.** L6's grep-parity pre/post is the empirical proof. The architectural lesson: when a constraint is "substrate stays neutral; per-type knowledge stays in the entry," ship a registry/dispatch primitive (L3) before the per-type entries (L4-L6) and the constraint enforces itself structurally.

3. **Optional-registry-entry-hook is the right extension shape.** F1 added three (`snapshot`, `wireEvents`, `renderInviteSection`) across L4-L5 without breaking any required-contract entry. Pattern: "required fields are render-time contract; optional fields are substrate-integration opt-ins."

4. **Pin computed constants at design time.** L5's `2147552768` → `2147552256` was a math error that the design-review process didn't catch because the spec stated the value as a literal. Treat any spec-stated numeric constant as a verification gate.

5. **HAT remains an essential signal even at the end of a six-leg autonomous flight.** L7 caught both a structural bug (create-mode re-render) and several polish observations (chip-input placeholders, intent layout rhythm) that no automated test could have surfaced. The "L7 optional" framing should be promoted to "required when a flight touches registry-mediated UI dispatch."

6. **Mission criteria advancement was clean.** F1's two contributing criteria are met without ambiguity. The Discord-shaped UX promise lands at the creation + detail surface; the wire-layer substrate stays intact.

## Test Metrics

Full suite (`docker exec the-one pytest --timeout 60 -q -m "not pixel"`) at flight-end (`94a10a6`):

| Metric | Value |
|---|---|
| Passed | 2804 (+473 over the M10 F8 baseline of 2331) |
| Failed | 10 (same 10 as M10 F8 baseline + L3-L7 verifications — pre-existing) |
| Skipped | 42 |
| Deselected | 12 |
| Wall clock | 610.22s |

**Comparison vs M10 F8 baseline**: F8's debrief cited "14.4 → 12.5 t/s" computed against the `-x --timeout 30` set (which excludes browser tests). F1's `-m "not pixel"` invocation includes browsers — different denominator. F1's `-m "not pixel"` wall-clock was 605s at L5, 605s at L6, 610s at flight-end — stable. F1 added tests at roughly the same per-test marginal cost as the existing browser tier; **no new regression detectable beyond the M10 F8 baseline.** Confirming the M10 F8 throughput regression's actual depth remains a routine-maintenance concern.

**10 pre-existing baseline failures** (documented across L3-L7 entries; confirmed unchanged at this debrief):
- 3× `test_connector_test_connection_button` (recurring across M10 F8 + M11 F1 — deserves triage, not "flake"; suggest routine-maintenance)
- 4× `test_aiat.py` (LLM-flaky; M10 F8 also documented these)
- 1× `test_flow_agent_tabs::test_tablist_renders_with_three_tabs` (test expects 4 tabs, prod has 5)
- 1× `test_flow_studio_navigation::test_studio_section_round_trip_preserves_agent_selection`
- 1× `test_edit_session_continuation_round_trip` (one-line hint-text drift, deferred since L3)

## Recommendations

### Critical — codify three Architect-checklist items (operator-confirmed)

Extend the design-review prompt with explicit checks. Cycle-1 HIGH-severity catches across L2-L6 cluster around "didn't grep the cited symbol; didn't walk the runtime path; didn't verify the constant."

1. **Grep every cited symbol's actual shape.** L2 cycle-1 HIGH ("`_make_account` doesn't accept `config` kwarg") + L4 cycle-1 HIGH ("`attachStaticListeners` delegation excludes typed inputs") + L5 cycle-1 HIGH ("`accountId` source in `renderTestConnectionBanner` is broken") all fit the pattern.
2. **Walk event-delegation / dirty-tracker / lifecycle paths.** L4 cycle-1 HIGH (dirty-tracker gap) + L7 HAT bug (create-mode re-render) both fit.
3. **Compute and verify numeric constants.** L5 cycle-1 missed the `2147552768`-vs-`2147552256` math error because the spec stated it as a literal. Treat any bit-mask / sum / shift expression as a verification gate.

**Implementation**: amend the Architect prompt in `.claude/skills/leg/SKILL.md` (or wherever the design-review prompt is loaded from in this skill stack) with the three explicit checks. Apply at M11 F2 design review.

### Important — codify two patterns as agents.md project conventions

1. **`optional-registry-entry-hook`**: "When a registry entry participates in substrate machinery (dirty tracking, namespace exposure, lifecycle), add OPTIONAL function fields validated as 'must be a function IF present.' Required fields are render-time contract; optional fields are substrate-integration opt-ins." F1's three hooks (`snapshot`, `wireEvents`, `renderInviteSection`) are the n=3 evidence.
2. **`registry-dispatch-create-mode-AC`**: "Any registry-mediated typed-render path requires BOTH 'create-mode-after-dispatch-key' AND 'edit-mode-with-key-set' as explicit ACs." Direct from L7; generalizes beyond connector-form-registry.

### Important — promote citation-anchor methodology

Switch leg-spec default citations from line numbers to symbolic anchors (function name, section heading, `---` separator, `data-testid` value). Line numbers drift as preceding legs land; symbols don't.

### Important — triage the recurring 3× `test_connector_test_connection_button` failure

This has now persisted across two full flights (M10 F8 + M11 F1). It's not LLM-flaky — it's real test/implementation drift. Scope to `/routine-maintenance` post-M11.

### Forward-looking for M11 F2 (pool-keying + system-prompt-directive)

- F2 will touch `_pool.py:512-530` `connector_acquire` (the M10 F8 Fix #6 sentinel wrapper). Apply `cross-subsystem-pattern-premise-revalidation` at design review: walk "MCP uses agent-keyed; gateway-protocol uses account-keyed; substrate primitive must distinguish."
- F2's per-account system-prompt-directive surface likely needs a new optional registry-entry hook (`renderDirectiveSection`). Don't reinvent; extend the L4-L5 pattern.
- Apply `mechanical-fallback-prompt-truth-pairing` at any directive-rewording — the directive's wording must match what the dispatcher actually does.

## Action Items

- [ ] **Codify three Architect-checklist items** in the design-review prompt (per operator decision). Apply at M11 F2.
- [ ] Codify `optional-registry-entry-hook` + `registry-dispatch-create-mode-AC` in `the_one/agents.md` Project Conventions (recommend folding into M11 F2 L1 or as a doc-only follow-up leg).
- [ ] Add the M11 F1 L7 HAT-discovered chip-input placeholder gap + Discord create-form visual rhythm to M11 F10 Alignment scope.
- [ ] Triage 3× `test_connector_test_connection_button` recurring failure under `/routine-maintenance` post-M11.
- [ ] Fix `test_edit_session_continuation_round_trip` hint-text drift (one-line; deferred since L3).
- [ ] Consolidate connector-form-registry public-contract docs (top-comment in `connector-form-registry.js`, or new `static/js/areas/studio/README.md`).
- [ ] Lift `MASKED_SENTINEL` to a shared studio constant.
- [ ] Replace `_resolveAccountFromContainer`'s hash-parse with a `data-account-id` attribute at editor mount.
- [ ] `_probe_gateway_connect` hardcoded intents at `_discord.py:1421` — flag for M11 F2 or F10 to lift to config-driven.
