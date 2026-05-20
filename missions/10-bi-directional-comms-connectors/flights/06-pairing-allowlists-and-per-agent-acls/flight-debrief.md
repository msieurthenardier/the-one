# Flight Debrief: Pairing, Allowlists, and Per-Agent ACLs

**Date**: 2026-05-19
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](flight.md)
**Status**: landed
**Duration**: 2026-05-18 (planning + autonomous legs 1a–6 + first commit `10fe471`) → 2026-05-19 (HAT iteration + semantic redesign + second commit `6e869e3`)
**Legs Completed**: 9 of 9 (8 autonomous + 1 HAT)

## Outcome Assessment

### Objectives Achieved

F6 landed the full gating substrate for connector-attached agents end-to-end:

- **Resolver hook + outcome ADT** (`connectors/base.py:174-232`) — `Permit | NeedsPairing | Deny` with `_default_permit` fallback discovered via `getattr` (no `ConnectorPlugin` Protocol widening).
- **Two-scope allowlist persistence** — account-scope on `ConnectorAccount.config["allowlist"]` (no migration; rides leg-1b validator); per-agent on `AgentConfig.connector_acls` (new v18 migration; per-axis tri-state post-redesign — null/inherit, []/explicit-empty, [items]/subset).
- **DM-pairing flow** — peer-side `PAIR <code> <message>` prefix at `connectors/_pairing.py`; dispatcher strips on success, persists `peer_id` into `account.config["allowlist"]["peers"]`, logs audit outcome to `session_metadata["audit"]` via the new narrow `ChatSessionRepository.append_to_session_metadata` primitive.
- **Inbound gating** — `connectors/_inbound.py:186-260` consults the resolver after `resolve_session` and before the per-session lock; three-arm branch (Permit / NeedsPairing / Deny) with audit-log writes for every outcome.
- **Outbound gating** — `tools/connector_send.py:144-220` consults account-scope + per-agent ACL channels per-call (function-local import pattern); F8-deferred DMs-only sentinel for `channels: []` documented in module docstring + pinned by test.
- **Studio surfaces** — Connectors account detail page (Pairing section, allowlist chip-list editors, attached-agents table with chip lists per agent); Agent Editor Connectors tab (attach toggles + per-axis chevron-toggle rows styled like MCP tools-list).
- **Live-broadcast visibility closure** — `interfaces/web/app.py:817-831` injects `visibility=operator` into the user-event dict-literal pre-broadcast on connector-attached sessions, closing the F5 carry-forward without modifying the agent loop.

### Mission Criteria Advanced

- **#4** Unknown senders gated by pairing/allowlist; approval state survives restart (audit-log persistence + dispatcher reads).
- **#6** Connector account attached to any agent through Studio; per-agent ACL substrate ready (F7 layers multi-agent routing rules on top).
- **#15** `platform-send` constrained to attached accounts + ACL-permitted channels (outbound consult).
- **#28** Studio Connectors detail page + Agent Editor Connectors tab meet design-language bar (after HAT iteration — see Anomaly).
- **#29** Automated coverage proving the contract — 91 new tests across `test_db_repositories`, `test_connector_send_tool`, `test_db_api`, `test_connectors_inbound`, `test_connectors_resolver`, `test_ws_storage_edge_shim_visibility`.

## What Went Well

- **Two-cycle design-review cadence (legs 1a–3, leg 6)** caught substantive issues at design time, not implementation time. Cycle-1 H2 closure (Pydantic v2 validator fires on direct `BaseModel(**kwargs)` — no `_row_to_model` rewrite needed) was verified empirically by the reviewer rather than papered over by re-architecting; that's the methodology working as designed.
- **F4 L5 atomic-leg pattern adoption (leg 1c)** — Pydantic field + ALTER TABLE + repository round-trip + ripple-site updates all in one leg, closing F4 debrief rec #1 with a clean precedent. Pattern is now n=2 in this project; worth codifying.
- **`optional-plugin-hook-via-getattr-sentinel`** survives intact. Stub plugin unchanged across the flight; `grep -rn "AllowlistResolver" the_one/` returned zero hits post-leg-3 (every F1-era predictive docstring reframed cleanly). The optional-hook convention was the right call — Protocol widening would have forced a stub `resolve` body and contaminated the F1-F5 regression net.
- **F4-debrief rec #4 deferral (per-call account fetch instead of `ToolProvider` widening)** held up post-ship. The factory branch at `agent/factory.py:315-331` is widened-kwargs-bag, not a third branch; deferral remains correct until F8 introduces a third *branch* (likely DM-classification handoff).
- **HAT working as designed for semantic discovery.** The allowlist semantic redesign (empty = unrestricted, per-axis tri-state) emerged at HAT from the operator's UX framing — exactly the axis design-review can't naturally cover. Net win: the system shipped with a cleaner mental model than the planning team would have arrived at unaided.
- **Live-broadcast WS-typed visibility closure (leg 6)** landed as a single dict-literal injection at one site (10 lines including comment + 2 tests). Smallest leg, highest precision-per-edit ratio in the flight.

## What Could Be Improved

### Process

- **Cadence-change at leg 4+ was net-negative for this flight.** The Flight Director cadence note (flight-log L39-41) skipped the pre-implementation Developer design-review for UI legs based on the F5 precedent that "design-review caught issues HAT also catches." F6 HAT surfaced 18+ design-language defects across 7 iteration rounds; several (`.tool-enable-switch` positioning, `.field-error` admin-scoping, hidden-class-vs-attribute) are *primitive-uptake* failures a strict "grep for new custom selectors" design-review check would have caught. Magnitude was bounded by HAT, but F8/F9 ship many operator-visible surfaces and will compound.
- **Post-redesign leg artifact prefaces (legs 1b/1c/3)** read coherently for an archaeologist but create methodological debt: the leg artifacts no longer describe the shipped contract; flight-log Deviations is the canonical source. Future readers scanning *just* the leg artifacts will see stale Outputs. The prefaces handle the redirect, but quantity will compound across flights. Recommendation: when HAT lands a contract flip, amend the leg's Outputs section in-place rather than appending a redirect — or extract a mission-level "ACL semantic timeline" doc that compacts multi-flight evolution.

### Technical

- **Chip-list-vs-checkbox dual-mode UI** (`connectors-tab.js:206-340`) is the substantive new debt from the redesign. Two render paths conditional on "is the parent scope bounded?" with `data-connector-acl-mode="chips"|"checkboxes"` data attributes propagating through `studio.js:2059-2063` collectFormData. Tests validate end-to-end JSON shape; the visual decision tree is not test-pinned. **Candidate for primitive promotion** as a `.scope-narrowing-editor` (the operator-flagged design-language Anomaly captures this).
- **v18-renumber ripple footprint** (flight-log leg 1c) — leg 1c touched 16+ docstring sites across `schema.py`, `_connector_types.py`, `agents.md`, `connectors/README.md`, `test_db_migration.py`. This is the 5th identical renumber pattern (v14/v15/v16/v17/v18). The forward-prediction comments themselves are the maintenance debt. **F10 candidate**: delete forward-reference v19/F8-CHECK predictions; pin a single canonical "F8 CHECK lands at CURRENT_VERSION+1" line.
- **`connectors/_pairing.py` is a single-function module.** Defensible for testability, but the file-per-function pattern doesn't compose if F8 wants Discord-native pairing or Slack wants its own. Decide at F8 planning whether to fold or keep separate.
- **`# F6: AllowlistResolver` marker pattern was the F4→F6 handoff site.** Leg 3 removed the marker (correct — it shipped); F6 should leave an equivalent `# F8: DM-classification consult lands here` at `tools/connector_send.py:202` so the F8 leg author has a grep target for the deferred DMs-only contract.

### Documentation

- **`agents.md` Connector subsystem section** is current post-leg-1a/1c/3 reframing — v18 = F6 L1c, v19 = F8 CHECK, optional-hook pattern documented in `optional-plugin-hook-via-getattr-sentinel`.
- **`connectors/README.md`** §4 (Optional hooks) describes `resolve`; §6 names v19 for F8 CHECK; §11 names the leg-3 consultation. Clean.
- **Untested: pairing-prefix whitespace edge cases.** `_validate_pairing_prefix` has NO dedicated unit test. The leg-2 flight-log claims case-sensitivity, byte-equality on code, and whitespace-in-code rejection — none of these claims is test-pinned. Three dispatcher integration tests exercise the helper indirectly. Recommendation: add `tests/test_pairing_prefix.py` with ~6 cases.
- **`connector-account-editor.js`** (1661 lines) may still reference the dropped Enable toggle in module docstrings/comments post-redesign. Worth a routine-maintenance scan.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Cadence change at leg 4+ (skip Developer design-review for UI legs) | Saved review cycles; HAT was assumed to be the operator-facing arbiter | No — net negative this flight; F5 precedent did not hold |
| Allowlist semantic redesign at HAT (empty = unrestricted; per-axis tri-state) | UX framing surfaced the dead-chip defect + the "I want a public bot" intent | Yes — codify `per-axis-tri-state-override` in `agents.md` Project Conventions at n=1 |
| Leg-1b/1c/3 post-redesign prefaces (historical body + redirect to Deviation) | Preserves the cycle-1/cycle-2 archaeology while marking the shipped contract elsewhere | Partial — fine for one-off; the pattern doesn't scale across many flights, so future contract flips should amend Outputs in-place or extract a timeline doc |
| Drop of `connector-account-editor.js` Enable toggle for the account-scope allowlist | Redesign collapsed lockdown-vs-default-permit into "empty = unrestricted"; toggle no longer needed | Yes — same `per-axis-tri-state-override` codification |
| Per-axis chevron-toggle pattern on Agent Editor Connectors tab (MCP-style "N tools ▸") | Operator iteration #4 — single ACL expand → two per-axis chevrons | Yes — mirror MCP-tab pattern is the canonical Studio idiom |

## Key Learnings

1. **HAT is the right axis for semantic discoveries.** The allowlist redesign emerged from operator framing ("I want a public bot," "the per-agent panel lets me type dead IDs"). Design-review naturally examines Pydantic shape, read-path validators, ripple footprint — the right things — but doesn't naturally answer "what does this empty value mean to operators." HAT working as designed.
2. **HAT is the wrong axis for UX discoveries.** Of 18+ HAT iterations, ~13 were primitive-uptake or coverage-gap defects (`.tool-enable-switch` positioning, `.field-error` admin-scoping, hidden-class-vs-attribute, dropdown-default-duplicate). A pre-implementation design-language audit gate (grep for new custom selectors, challenge each) would have caught most of these without burning HAT cycles. **The cadence-change decision (legs 4+) tested this hypothesis and the result was negative.**
3. **"Stub plugin not registered in production" is now load-bearing on HAT coverage.** F6 HAT explicitly skipped end-to-end inbound/outbound dispatch through Studio because the stub is `register_for_test`-only. Unit tests carry the integration story (2074-test suite). **F8 must decide before planning: ship a dev-mode stub register OR accept F8 HAT *is* the integration HAT.** F5 debrief already flagged this; F6 confirmed it.
4. **Atomic-leg pattern (F4 L5) is now n=2.** Field + migration + repository round-trip + ripple-site updates in one leg works. Codify in `agents.md` alongside connector-type extension checklist.
5. **Optional-plugin-hook-via-getattr-sentinel** is now n=2 (`display_channel` + `resolve`). Pattern is durable; future plugin extensions choose between optional-hook and Protocol-widening based on whether ALL plugins in scope must implement (widen) or only some benefit from implementing (hook).

## Test Metrics

**This flight (post-redesign):**
- 2074 passed, 4 skipped, 411 deselected, 1 warning
- Wall-clock: 159.27s (≈2:39)
- Throughput: ~13.0 tests/s (apples-to-oranges with F5 unit-only; included browser-deselected tests this run)
- Zero failures, zero observed flakes
- Surviving 1 warning: pre-existing aiosqlite teardown-loop warning (persisted since F3)

**Suite-by-suite delta vs prior flights:**

| Flight | Test count | Wall-clock | Notes |
|---|---|---|---|
| F3 | 1881 | 127.40s | M10 baseline |
| F4 | 1945 (+64) | 133.73s (+6.33s) | flat |
| F5 (unit-only) | 1983 (+38) | 131.69s (-2.04s) | throughput recovered |
| **F6 (full)** | **2074 (+91)** | **159.27s (+27.6s)** | apples-to-oranges; full suite incl. deselected |

The +91-test delta breakdown: leg 1a +6, leg 1b +25, leg 1c +29 (validator + migration + repo), leg 2 +13, leg 3 +9, leg 4 +10, leg 6 +2, HAT-redesign +6 (per-axis tri-state inversions). No infrastructure drag observed.

**Coverage adequacy (per-area):**

| Area | Test count | Adequacy |
|---|---|---|
| Pairing flow (4 critical paths) | 4 dispatcher integration tests | Adequate (`_validate_pairing_prefix` whitespace edge cases NOT pinned) |
| Allowlist tri-state validator | All 9 axis combinations | Adequate |
| Outbound gating | 11 cases incl. F8-deferred DMs-only | Adequate (exact-string assertion will catch F8 contract relaxation) |
| Attached-agents API | 10 cases including tri-state response shape | Adequate |
| `append_to_session_metadata` audit writer | 5 dedicated tests | Adequate for shape; concurrency story untested |

## Recommendations

1. **Install a design-language uptake audit gate in cycle-1 leg review for any leg touching `interfaces/web/static/`.** Grep for new custom selectors; challenge each one ("is there an existing primitive?"). If yes, mandate it. If no, the leg ships a new primitive in `components.css`/`studio.css`, not ad-hoc inline style. This is the highest-leverage change identified — coverage gaps are bounded but uptake discipline is unbounded. F8/F9 will compound F6's iteration density without it.
2. **Schedule a routine-maintenance pass** for the design-language coverage gaps the operator flagged: promote `.field-error` + `.editor-error-banner` from `.area-admin` scope to area-neutral; reshape `.tool-enable-switch` so default usage flows inline (tile-corner becomes the override); codify a `.kv-editor` primitive (header → rows → "Add row" button below); explore promoting the chip-list-vs-checkbox dual-mode UI into a `.scope-narrowing-editor` primitive.
3. **Codify `per-axis-tri-state-override` in `agents.md` Project Conventions at n=1.** The pattern (peers and channels are independently overrideable axes; null/inherit, []/explicit-empty-with-deferred-sentinel, [items]/subset) generalizes cleanly across the validator, the outbound check, the Studio UI, and the attached-agents response. F7 routing-rule precedence is the natural n=2 confirmation candidate.
4. **F8 prerequisite: decide stub-register-in-dev-mode OR accept F8 HAT *is* the integration HAT.** F6's HAT-coverage-gap workaround (skip end-to-end dispatch; rely on unit tests) is sustainable but the dependency on a real Discord bot for F8 HAT will introduce operator-account, network, and rate-limit dependencies. F5 debrief already flagged this; F6 confirmed it. Decide before F8 planning.
5. **F10 candidates** (already documented; rolling forward):
   - Race-on-concurrent-pairing on `config.allowlist.peers` (last-writer-wins on JSON column).
   - Race-on-concurrent-audit-writes on `session_metadata["audit"]` for the same `session_id` (the per-session lock at `_inbound.py:268` is taken AFTER the audit writes).
   - O(N) attached-agents API (`api.py:list_attached_agents_for_connector_account` iterates `list_agents()` + `load(name)` per agent).
   - Per-call account fetch in `tools/connector_send.py:160` is a profilable hardening candidate.
   - Schema-version forward-prediction cleanup (delete v19/F8-CHECK predictions from 12+ sites; pin a single canonical comment).

## Action Items

### F6 follow-ups (close before next mission)
- [ ] Add `tests/test_pairing_prefix.py` with whitespace + case-sensitivity edge cases (~6 tests). Pins claims the leg-2 flight-log makes about `_validate_pairing_prefix` semantics.
- [ ] Add a `# F8: DM-classification consult lands here` source-code marker at `tools/connector_send.py:202` (mirrors F4's `# F6:` marker pattern; gives F8 leg authors a grep target).
- [ ] Routine-maintenance pass: scan `connector-account-editor.js` for stale Enable-toggle references in module docstrings and comments post-redesign.

### F7 planning inputs
- [ ] Name the "first-attached or only-attached" temporary single-agent assumption substitution site in `_inbound.py` by file:line in F7's flight spec.
- [ ] F7 dispatcher consults routing AFTER the resolver but BEFORE the per-session lock — confirm this composition site in F7 design.
- [ ] F7 reuses `append_to_session_metadata` with `"routing"` key (sibling to F6's `"audit"`). Already supported; no primitive work needed.

### F8 planning inputs
- [ ] Decide: dev-mode stub-register OR F8 HAT is the integration HAT.
- [ ] Name the DM-classification surface (new `ConnectorPlugin` method? New `OutboundTarget` field?) before committing the flight spec.
- [ ] At recon, re-check `ToolProvider` Protocol widening — F8 may introduce a third *branch* (not just a third kwarg) which justifies widening.
- [ ] Update `test_deny_when_per_agent_acl_channels_is_empty_dms_only_stub` to either assert PERMIT on DM-classified channels or split into a permit-on-DM + deny-on-public-channel pair.

### Methodology improvements (apply to all future flights)
- [ ] Install the design-language uptake audit gate in cycle-1 leg review (grep new custom selectors; challenge each).
- [ ] Schedule a routine-maintenance pass for design-language coverage gaps.
- [ ] Codify `per-axis-tri-state-override` in `agents.md` Project Conventions.
- [ ] Codify the atomic-leg pattern (F4 L5 / F6 L1c) in `agents.md` — Pydantic field + ALTER TABLE + repository round-trip + ripple-site updates ship in one leg.

### Mission Known Issues (status)
- [x] Live-broadcast WS-typed visibility asymmetry — closed by leg 6.
- [x] Per-session lock unification (F3-flagged, F5-owned) — closed (no F6 work needed beyond audit-write ordering documentation).
- [ ] M07 `mcp/_pool.py` test-isolation debt (`_shutting_down` flag leak under shared event loop) — F1 deferral; not addressed in F6; revisit at mission close or F10.
