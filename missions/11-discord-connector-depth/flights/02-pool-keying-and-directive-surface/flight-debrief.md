# Flight Debrief: Pool-Keying Refactor + Per-Account System-Prompt Directive Surface

**Date**: 2026-05-22
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](flight.md)
**Status**: landed
**Duration**: 2026-05-21 → 2026-05-22 (planning + execution + HAT same-session under `/agentic-workflow`)
**Legs Completed**: 6 of 6 (L1-L5 autonomous + L6 required HAT)

## Outcome Assessment

### Objectives Achieved

Both contributing-to-criteria items met:

- ✅ Pool-keying refactor closed M10 F8 debrief critical action item: clean-break two-primitive split (`agent_acquire` + `account_acquire`); `_CONNECTOR_POOL_AGENT_SENTINEL` deleted from the public API; warm-entry-continuity contract preserved at private `_ACCOUNT_POOL_AGENT_SLOT`. The footgun the M10 debrief flagged is structurally impossible now.
- ✅ Operator-editable system-prompt directive closed the second M10 debrief critical action item: `account.config["system_prompt_directive"]` field, APPEND-mode composer extension, Studio General-tab UI with verbatim-Python read-only disclosures and reactive "(this account's current)" annotation.

### Mission Criteria Advanced

- M11 criterion #14 (pool-keying refactor to account-keyed primitive at connector layer): closed.
- M11 criterion #13 (operator-editable connector system-prompt directive with default visible): closed.
- F2 also folded in five F1 debrief recommendations (codification of `optional-registry-entry-hook` + `registry-dispatch-create-mode-AC`; `MASKED_SENTINEL` lift; `_resolveAccountFromContainer` hash-parse → `data-account-id` refactor; F1 L2's deferred `_probe_gateway_connect` intents lift).

Two commits shipped: `f6969b4` (L1-L5 atomic batch) + `9b6908a` (L6 HAT + flight-landed). PR #70 ready for review, stacked on F1 PR #69.

## What Went Well

- **F1-debrief Architect-checklist methodology delivered.** Cycle-1 HIGH-severity issues dropped from F1's 4 of 6 legs to F2's 2 of 5 source-touching legs. The drop is methodology-driven, not scope-driven: L4 (largest source-touching leg of either flight) passed cycle-1 clean; L2 (similar blast-radius to F1 L2-L6 combined) only had one HIGH catch. The architect was explicitly told to apply "grep cited symbols, walk delegation paths, verify computed constants" at every cycle.
- **L2's clean-break refactor landed atomically without breakage.** 6 production sites + 6 test files + multiple READMEs updated lockstep per `atomic-leg-pattern`. Zero regressions on the substrate's lifecycle invariants (race-fix, eviction, reaper, encryption-rotation all byte-identical pre/post). L2's `_keys_for_test()` HAT seam earned its keep at L6.
- **APPEND-mode held in HAT.** Operator emoji-signing directive saved, persisted via `config.system_prompt_directive`, omitted on clear — no friction with the substrate-contract constraint. `mechanical-fallback-prompt-truth-pairing` is now operational vocabulary that bound L3 design from the start.
- **n=4 of `optional-registry-entry-hook` convention.** F1 L1 codified the pattern; F2 L4 added `renderDirectiveSection` as the 4th optional hook with no spec ambiguity. The convention is proving its abstraction — L4 spec went "this is registry-mediated UI dispatch with reactive state; here are the hooks" rather than re-deriving each integration.
- **Verbatim Python↔JS constant equality pinned by runtime test.** L4's `test_three_default_disclosures_render_verbatim_python_text` imports the Python constants directly and compares to live JS textContent. Any future drift fails on the spot. Right defensive shape for the duplication-debt window.
- **HAT walk surfaced concrete artifacts.** All 10 verification steps green: `data-account-id` set on the right element; `App.studio.MASKED_SENTINEL === '__MASKED__'`; section-placement matches DOM order; directive save/clear/empty round-trips; auto-relay annotation reactivity works across-tab. The section-ordering wording divergence (flight spec said "between Pairing and Test Connection"; actual DOM order made "between Pairing and Attached Agents" correct) was caught at L4 cycle-1 — saved by the methodology.

## What Could Be Improved

### Process

- **Important — primitive-rename test classification rule.** L2 cycle-1 found 3 test files mischaracterized as docstring-sweep that actually had functional code (`tests/test_connectors_inbound.py` monkeypatch + sentinel filter at 5 lines; `tests/test_lifespan.py` getattr/setattr 5 sites + assertion; `tests/test_connectors_e2e_platform_send.py` monkeypatch + assertion + function rename). The cycle-0 default of "docstring-sweep until proven otherwise" inverts the safe direction. **Codify**: when a leg spec touches a primitive's name, default-classify every test file containing the primitive's name as `code-update`, downgrade to `docstring-sweep` ONLY after grep verifies it appears solely in `"""..."""` blocks.
- **Important — Architect-checklist items still uncodified in mission-control skills.** F1 debrief's Critical action item ("codify three Architect-checklist items at design review") is still open. F2 applied them in spirit at every cycle and the HIGH-rate dropped. Getting them into `.claude/skills/leg/SKILL.md`'s Architect prompt makes the discipline durable across flight authors. Before M11 F3.
- **Minor — flight-spec wording drift from DOM order.** L4 cycle-1 caught "between Pairing and Test Connection" in `flight.md` Design Decisions §3 — but the actual current order has Attached Agents between them. The reviewer recommended either amending the flight spec or rewording the leg spec; the leg spec was reworded. No structural harm done, but the symptom is that the flight spec was written without a fresh DOM-order audit. **Codify**: at flight-design time, the architect re-walks DOM order before claiming section adjacency.

### Technical

- **Important — recurring `test_connector_test_connection_button` cluster is now 3 flights deep.** Present at M10 F8, M11 F1, M11 F2. F1 debrief recommended "/routine-maintenance post-M11"; F2's debrief identifies a specific root-cause hypothesis: the fail-fast capture today showed `details_wrap` resolving to a `<div hidden="" ...>` 9 times before the 5000ms expect timeout — consistent with a missing `details_wrap.hidden = false` on the success-with-no-details branch in `renderTestConnectionBanner` or equivalent. **Recommendation**: do NOT wait for post-M11. A small triage leg between F3 and F4 (or fold into F3 if F3 touches the test-connection button surface) likely closes it in one commit. Small surface, high signal.
- **Important — Python↔JS directive constant duplication is real debt.** `connector-form-discord.js:_DIRECTIVE_AUTO_RELAY_DEFAULT / _DIRECTIVE_TOOL_ENABLED_DEFAULT / _DIRECTIVE_TOOL_DISABLED_DEFAULT` (lines 57-114) duplicate the three Python `agent/config.py` constants. The verbatim test pins drift but doesn't eliminate it. **Long-term fix**: small `/api/connector-directive-defaults` endpoint (read-once at editor mount, cacheable). Not F3 or F4 scope (unrelated UX); F5 may touch the directive substrate and could absorb the lift; otherwise post-M11 routine-maintenance.
- **Minor — `optionalFns` array at n=4 evaluation point.** F1 L4 + L5 added 3 hooks; F2 L4 added a 4th. Sustainable as a flat list today, but at n=5 (likely F3's live-data dropdown or F5's mentions-policy hook) the substrate should evaluate switching to an object map `{hookName: validatorSignature}` so per-hook arity/signature checking becomes possible. **Trigger condition codified**: when the next optional hook lands, pause and assess.
- **Minor — PUT handler full-replace config-merge.** L4 cycle-1 verified that `update_connector_account` does `merged = existing.model_dump(); merged.update(data)` — wholesale replace, not partial-merge. Brittle as field count grows; every new field is gated on the UI emitting it. F2's `collect`-omit-when-empty pattern compounds the contract surface. **Recommendation**: before F5 adds a 5th state, audit whether a partial-merge mode (or a "fields-the-form-owns" allowlist) makes more sense than the current full-replace model.

### Test Coverage

- **HAT step 7 substrate-verification shortcut.** Multi-agent pool-keying real-traffic verification was substrate-verified (L2 unit tests + probe-OK) rather than running actual Discord messages from two agents. Acceptable for F2 because L2's unit tests pin the slot semantics, but the same reasoning shape — "substrate logic implies behavior" — is what produced the M10 F8 sentinel-wrapper footgun F2 just refactored away. **Do not repeat in F3+**. The mission's tentative HAT-script flight (M11 F8) is the natural home; **promote priority once F3-F5 ship** so the chronic browser-test-flake cluster also gets an automated regression gate.
- **Multi-account directive composition path is thinly tested.** Only one factory test (`test_multi_account_directives_collected_in_sorted_order`) exercises the cross-account join. HAT didn't exercise it (gleepglorp is one-account). The `sorted()` deterministic-order benefit is theoretically correct but currently un-exercised in practice.

### Documentation

- **Important — connector-form-registry public contract still spread across leg artifacts.** F1 debrief flagged this; F2 added a 4th optional hook without consolidating. The contract is now in `connector-form-registry.js:_validateEntry` plus 5 leg artifacts (F1 L3, F1 L4, F1 L5, F2 L4 — and F2 L1 in the codified convention). **One-line fix**: extend the top comment of `connector-form-registry.js` with the optional-hook table (one line per hook: name, signature, when called). Cheaper than reading 5 leg specs for the next M12 connector author.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L3 directive collection iterates `sorted(connector_account_ids)` instead of `config.connector_account_ids` list-order (existing factory pattern) | Prompt-cache stability across restarts; deterministic order | **Yes** — but as a convention only for prompt-cache-sensitive iterations, not as a blanket override of list-order semantics |
| L4 directive section placement "between Pairing and Attached Agents" not "between Pairing and Test Connection" as flight spec said | Current DOM has Attached Agents between them; flight spec wording predated this leg's audit | **Yes** — at flight-design time, architect re-walks DOM order before claiming section adjacency |
| L4 inline JS constants duplicating Python directive text | Avoid API-round-trip latency; atomic-leg-pattern enforces both-side updates | **No** — keep the verbatim test as defense; pursue API-endpoint lift in F5 or post-M11 |
| L4 dropped the dead `pool_acquire` alias entirely (cycle-1 reviewer recommendation) | Clean-break ethos; no callers of the alias name | **Yes** — clean-break > deprecation when no external consumers exist |
| L5 `_StubDiscordClient.last_intents` → `instances[-1].intents` (cycle-1 catch) | The fictional `last_intents` attribute doesn't exist; the stub uses per-instance `intents` captured in `instances` array | n/a — test-pattern correction; the established fixture pattern was honored |
| HAT step 7 substrate-verified, not real-traffic-tested | Real Discord traffic outside what Chrome MCP can drive without operator-side activity | **No** — acceptable for F2; explicit recommendation to NOT repeat. F8's repeatable HAT script is the proper home |

## Key Learnings

1. **The F1-debrief Architect-checklist methodology moved the needle empirically.** F1: 4 of 6 cycle-1 HIGHs. F2: 2 of 5 source-touching legs. The drop is real and scope-controlled (L4 was the largest source leg of either flight). Three checklist items — grep cited symbols; walk delegation/dirty-tracker/lifecycle paths; verify computed constants — generated the catches at design time that F1 would have surfaced at implementation. **Codify before F3.**

2. **Convention codification compounds.** F1 L1 codified 6 conventions from M10 debrief; F2 L1 codified 2 more from F1 debrief; both flights cited them by name in subsequent legs. The pattern (codify-as-L1-doc-only-leg) is becoming the standard cross-flight bridging mechanism. n=2 of the pattern's own use.

3. **Substrate-contract reasoning is a footgun risk.** HAT step 7 was substrate-verified ("if `account_acquire` uses one composite-key slot AND probe-OK THEN multi-agent shares one entry"). The same shape of reasoning produced the M10 F8 sentinel-wrapper this flight just refactored. **Use sparingly**; promote M11 F8 (HAT-script flight) priority.

4. **Optional-hook extension is at evaluation point.** Four hooks today. The next addition (likely F3) triggers a substrate-validator restructure consideration. The convention scales; the validator's structure may not.

5. **Recurring browser failures decay into chronic debt fast.** The `test_connector_test_connection_button` cluster has now persisted across three full flights with the same signature. Deferring to "post-M11" risks a fourth. Specific root-cause hypothesis identified during the F2 debrief test capture (`details_wrap` stays hidden on the success-with-no-details branch). A small targeted triage is high-leverage now.

## Test Metrics

Capture method: split runs at flight-end commit `9b6908a`. Full-suite `--timeout 60 -q -m "not pixel"` invocation hung at >480s wall (browser tier appears to hang under load — likely related to the same long-running studio tests pushing F1 to 605-610s).

| Tier | Result | Wall |
|---|---|---|
| Non-browser (`--ignore=tests/browser`) | **2443 passed, 7 skipped, 4 failed** | 205.85s |
| Browser-only (full) | hung beyond 480s; fail-fast variant tripped on `test_connector_test_connection_button` | n/a |
| Fail-fast browser smoke (`-x --timeout 30`) | 1 failed, 9 passed before stop | 20.28s |

**Non-browser failures (all 4)**: the same `tests/test_aiat.py` LLM-flaky AIAT cluster F1 documented — `test_basic_chat`, `test_tool_use_file_read`, `test_self_awareness`, `test_multi_step`. Non-browser tier is **regression-free** at F2 ship.

**Per-leg progress** (per flight log):
- L2 ship: 2806 (+2 over F1's 2804)
- L3 ship: 2814 (+12)
- L4 ship: 2827 (+13)
- L5 ship: 2834 (+3 + 4 re-included)

**Recurring `test_connector_test_connection_button` cluster — STILL PRESENT, signature unchanged across 3 flights** (M10 F8 → M11 F1 → M11 F2). The fail-fast captured one of the 3 documented variants verbatim (`details_wrap to_be_visible / Actual value: hidden`). Hypothesis from the F2 debrief: the success-with-no-details branch likely lacks a `details_wrap.hidden = false` toggle.

**F1 → F2 wall-clock comparison**: F1 full-suite at flight-end was 610s (browser-included); F2's hangs suggest the browser tier may have grown a new hang condition, but it's also possible the same long-running tests pushed past a threshold. Worth investigating during the F3-F4 triage leg.

## Recommendations

### Critical — codify three Architect-checklist items in mission-control skills

The F1 debrief recommended this; F2 demonstrated the methodology works empirically. Codify in `.claude/skills/leg/SKILL.md` (or wherever the Architect prompt is loaded from in this skill stack) with the three explicit checks: (a) grep every cited symbol's actual shape; (b) walk event-delegation / dirty-tracker / lifecycle paths the new code participates in; (c) compute and verify numeric constants. Apply at M11 F3 design review.

### Important — codify two methodology rules as agents.md project conventions

1. **`primitive-rename-test-classification`**: when a leg spec touches a primitive's name, default every test file containing the name to `code-update` classification; downgrade to `docstring-sweep` only after grep verifies it appears solely in `"""..."""` blocks. F2 L2 cycle-1's three mischaracterized test files are the n=1 codification trigger.
2. **`flight-spec-dom-order-audit`**: at flight-design time when claiming section placement adjacencies, the architect must re-walk the actual DOM order. F2 L4 cycle-1's "between Pairing and Test Connection" vs actual "between Pairing and Attached Agents" is the trigger.

### Important — triage the recurring `test_connector_test_connection_button` cluster between F3 and F4

3 flights deep. Specific hypothesis: the `details_wrap.hidden = false` toggle may be missing on the success-with-no-details branch. Small triage leg; high leverage; closes a chronic debt before it persists into M11 F4+.

### Important — promote M11 F8 (HAT-script flight) priority once F3-F5 ship

The substrate-verified-not-traffic-verified HAT gap is now documented chronic shortcut. A repeatable Chrome-MCP-driven HAT script lands the multi-agent-on-one-Discord-account verification AND automates the recurring browser-button-flake regression gate.

### Forward-looking for M11 F3-F5

- **F3 (live-data discoverable dropdowns)**: will likely add a 5th optional registry-entry hook. At that point, evaluate whether `optionalFns` should become an object map `{hookName: validatorSignature}` to support per-hook arity/signature validation. Apply `cross-subsystem-pattern-premise-revalidation` at design review (the dropdown-data pattern inherits from Studio's existing chip-list shape; re-walk the premise).
- **F4 (peer-name attribution)**: touches inbound dispatch path — apply `cross-subsystem-pattern-premise-revalidation` (L1-codified F1) at design review.
- **F5 (mentions-aware response policy)**: any new prompt directive added here must COMPOSE with the F2 directive surface, not replace it. `mechanical-fallback-prompt-truth-pairing` is the binding convention. Also: F5 may add a 4th state to the `(connector_attached, send_tool_enabled, auto_relay)` triple — the directive-section's 3 disclosures will need to become 4 (or fold the new state into one of the existing); the verbatim-text parity test will rotate; renegotiate the disclosure-count contract.

## Action Items

- [ ] **Codify three Architect-checklist items** in `.claude/skills/leg/SKILL.md`. Apply at M11 F3.
- [ ] **Codify `primitive-rename-test-classification` + `flight-spec-dom-order-audit`** as agents.md project conventions (recommend folding into M11 F3 L1 if F3 uses the L1-codification pattern, OR a doc-only follow-up leg).
- [ ] **Triage `test_connector_test_connection_button` cluster** between F3 and F4 (or fold into F3 if F3 touches the test-connection button surface). Specific hypothesis to investigate: missing `details_wrap.hidden = false` on success-with-no-details branch.
- [ ] **Extend `connector-form-registry.js` top comment** with the optional-hook table consolidating the contract spread across F1 L3, F1 L4, F1 L5, F2 L4 leg artifacts.
- [ ] **Investigate full-suite browser-tier hang** that emerged between F1 (610s wall) and F2 (>480s timeout). May be the same long-running studio tests; may be a new hang condition. Likely small surface; uncertainty high.
- [ ] **Promote M11 F8 (HAT-script flight)** priority once F3-F5 ship; lands multi-agent traffic verification + automates the chronic browser-button-flake regression.
- [ ] **Audit PUT handler config-merge semantics** before F5 lands a 5th state — full-replace vs partial-merge decision needed at field-count growth threshold.
- [ ] **Python↔JS directive constant lift** to a small `/api/connector-directive-defaults` endpoint (F5 or post-M11; not F3/F4 scope).
- [ ] **Evaluate `optionalFns` array → object map** at n=5 (likely F3's first new hook).
