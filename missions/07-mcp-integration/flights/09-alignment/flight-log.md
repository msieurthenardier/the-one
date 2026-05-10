# Flight Log: Alignment — MCPs working well end-to-end

**Flight**: [Alignment — MCPs working well end-to-end](flight.md)

## Summary

Flight log for the eight-leg alignment flight closing Mission 7 (MCP Integration). Captures per-leg execution notes, anomalies surfaced during vibing, triage decisions (inline-fix / absorb / defer), runtime decisions, deviations from the planned approach, and reconnaissance findings.

---

## Reconnaissance Report

Phase 1b reconnaissance against the F8 debrief's eight action items (the source artifact for F9, since F9 closes the mission F8 was the penultimate flight of). Walked at flight design time (2026-05-09).

| # | Action item (F8 debrief) | Classification | Evidence | Recommendation |
|---|--------------------------|----------------|----------|----------------|
| 1 | Mission-control flight: codify "binding HAT for OAuth-touching flights" methodology constraint | out-of-project | F8 debrief Recommendations §1; mission-control work, not the-one | Out-of-scope for F9 — that's mission-control's plate |
| 2 | Mission-control flight: codify "fresh-context independent review after HAT inline fixes" agentic-workflow step | out-of-project | F8 debrief Recommendations §2; agentic-workflow skill update | Out-of-scope for F9 — F9 *uses* the pattern internally (Design Decision §8) but doesn't codify it upstream |
| 3 | Mission-control flight: add "HAT step inversion" protocol to leg skill | out-of-project | F8 debrief Recommendations §5 | Out-of-scope for F9 — F9 *uses* the pattern (Design Decision §2) but doesn't codify it upstream |
| 4 | the-one flight: per-agent OAuth re-auth toggle + per-(agent, source) credential storage (replaces F8 A4 + A5 surfaces) | confirmed-live (deferred) | F8 debrief Recommendations §3 sized as "similar to F8 (4-5 legs, ~1500-2000 LOC + binding HAT)"; `mcps-tab.js:245-249` shows credential-override fields explicitly REMOVED with rationale comment pointing to A5 | Defer per F8 carve-out (Design Decision §5). If a leg surfaces it as a blocker, decide per-anomaly. |
| 5 | the-one flight: no-auth MCP server detection (A6 — anyio cross-task cancel-scope leak) | confirmed-live (deferred) | F8 debrief What-Could-Be-Improved §3; design choice between `auth_required: bool \| None` hint vs `anyio.create_task_group()`-isolated probe is unresolved; same SDK behavior bites F6 + F6.6 + F8 | Defer per F8 carve-out. May surface in F9 L1/L2 (no-auth MCP probe path); per-anomaly decision at the time. |
| 6 | the-one maintenance leg: introduce typed `MCPInitializeTimeout(MCPConnectionError)` exception; replace message-pattern guard | partially-satisfied | `the_one/interfaces/web/api.py:968-969` — message-pattern guard `"did not respond" OR "cancelled during initialize"` is live and working; F8 debrief flagged the architectural debt but the function-level behavior is correct today | Candidate for L8 bundled carry-forward if it survives F1-F7 inline pressure. ~30 LOC; fits L8's "small carry-forwards" criterion. |
| 7 | the-one maintenance leg: derive `OAUTH_MANAGED_SECRET_KEYS` from `set_tokens` writes (F6.5 carry-forward, still open after F8 L0 cross-check) | already-satisfied | `the_one/mcp/oauth/storage.py:51-60` constant manually defined with full inventory comment; F8 L0 added `test_set_tokens_writes_only_managed_secret_keys` cross-check test that fails-loud if a future PR writes a key absent from the frozenset | Retire — close as resolved by F8 L0 cross-check. The architectural ideal (auto-derivation) is nice-to-have but the cross-check provides the equivalent guarantee. Mark in mission known-issues update at L8. |
| 8 | the-one architectural flight: `_pool.py` test isolation (Anomaly A1 — `_shutting_down` flag leak; pre-existing pool worker spawn-path hang under pristine state) | confirmed-live (pre-existing, deferred) | `the_one/mcp/_pool.py:24,104,398,550` — module-level flag documented; `tests/test_mcp_pool.py:113` test failure pre-existing per F8 debrief Test Metrics line 44 | Defer per F8 carve-out. Pre-existing; not an F9 issue. Carry forward to mission known-issues at L8. |

**User-presented summary at flight design (2026-05-09)**: 3 out-of-project (mission-control work), 3 deferred-to-future-flight (F8 carve-outs), 1 candidate for L8 bundle (`MCPInitializeTimeout`), 1 already-satisfied (OAUTH_MANAGED_SECRET_KEYS via cross-check test). User confirmed disposition; F9 design proceeds with these classifications baked into Design Decisions §5 (carve-out policy) and §6 (L8 bundle scope).

---

## Leg Progress

### L1 — `01-http-mcp-create-and-test`
**Status**: completed
**Started**: 2026-05-09
**Completed**: 2026-05-09

#### Operator Scenarios Walked

The leg artifact enumerated 10 scripted scenarios; operator drove via **exploratory vibing** rather than the strict script (acceptable variation per Flight Design Decision §1's structured pattern + leg artifact's "Edge Cases" section noting acceptable variations). Operator surfaced issues organically across multiple Refresh/Reset/OAuth/Create cycles. Coverage achieved across all 10 nominal scenarios via the exploratory flow:

- **List view + delete + create + transport switch + validation + fresh creation**: covered via the iterative source-creation cycles (Cloudflare API + Cloudflare docs MCP + bogus-URL probe paths).
- **Test connection / OAuth consent / tools render**: covered via Cloudflare API live OAuth flow; tools + capabilities + collapsible schemas verified post-rebrand of OAuth callback.
- **Edit cycle with `__MASKED__`**: covered via header edits + secret round-trip across multiple Save/reload cycles.
- **Deep-link / hash routing**: implicitly exercised via repeated navigation between source-edit and Studio MCP Sources list.
- **Error path — bogus URL**: covered via Shape C testing path (probe `"error"` verdict surfaces inline without engaging OAuth flow).

Operator-felt sign-off: "tested and works, lets close L1."

#### Anomalies Captured

Operator surfaced 7 distinct anomaly classes during exploratory vibing; all triaged inline-fix or absorb. Cross-referenced into Anomalies index below.

1. **A-L1-1**: Custom headers section formatting issues (positioning, table headers visibility, sensitive tooltip pattern, sensitive control type, delete control glyph) — triage: inline-fix / Implementer batch 1+2 — resolution: shipped.
2. **A-L1-2**: "Test connection" button copy didn't reflect persist-and-render behavior — triage: inline-fix / Implementer batch 1+2 — resolution: renamed to "Refresh connection" + refresh-cw icon.
3. **A-L1-3**: Sensitive-column toggle not visible (cascade-layer source-order trap) + Custom Headers table full-width — triage: inline-fix / Implementer batch 1+2 follow-up — resolution: specificity bump to `.mcp-kv-sensitive-cell .tool-enable-switch` (0,3,0); table `width: 100%` → `auto`.
4. **A-L1-4**: Reset button placement in Danger Zone treated reset as dangerous; Reset button stayed hidden after fresh OAuth until page reload (frontend didn't refetch source); creating a source required manual Refresh click — triage: inline-fix / Implementer batch 5 — resolution: Reset moved next to Refresh in `.mcp-connection-actions` flex; post-OAuth refetch wires `syncResetButtonVisibility()` via targeted DOM mutation; create-form Save dispatches `dataset.autoRun='1'` synthetic Refresh click; `noAutoPopup` opts flag suppresses auto-popup on auth_required.
5. **A-L1-5**: OAuth callback success page generic-looking + didn't auto-close — triage: inline-fix / Implementer batch 6 — resolution: themed via `_render_oauth_callback_page()` helper; success path auto-closes after 1.2s; failure path themed but does NOT auto-close.
6. **A-L1-6**: "Last updated" label render location + source-level Delete button missing trash glyph — triage: inline-fix / Implementer batch 7 — resolution: relocated to `.mcp-connection-actions` trailing element; Delete gains `App.icon('trash')` outside the `data-confirm-title` span.
7. **A-L1-7 (F8 A6 carry-forward)**: No-auth HTTP MCPs (Cloudflare docs MCP) failed with `consent_url_timeout` after 15s. **F8 originally carved out as Shape B, deferred per F9 §5.** Operator surfaced as blocking L1's "MCPs working well" gate. Architect re-evaluated, identified **Shape C** (HTTP-level pre-flight detection via bare httpx — no SDK engagement on probe path → zero anyio risk surface) which the original architect pass had not considered. Triage: **F9 absorbed Shape C** (~120-150 LOC production + ~120 LOC tests; under §2 alignment-flight scope; zero §7 risk). F8 Action Item "the-one flight: no-auth MCP server detection (A6)" → **resolved by F9 L1**. Shape B remains correctly deferred (still mission-sized; ~250-400 LOC + anyio cleanup). Implementer batch 9.

#### Inline Fixes Implemented

Nine batches dispatched via subagents per Flight Design Decision §9 (parent context = vibing + triage; all code-change work goes to subagents):

| Batch | Subagent role | Files modified | Net production LOC | Test LOC |
|-------|---------------|----------------|--------------------|---------:|
| 1 | Architect (items 3+4 design) | — | — | — |
| 2 | Implementer (items 1+2 UI bundle) | mcp-server-editor.js (+78 -31); studio.css (+67); test_mcp_test_connection_button.py (+9 -6); test_flow_studio_mcp_editor.py (+161) | ~114 | ~164 |
| 3 | Implementer (CSS follow-up: toggle visibility + table width) | studio.css (+12 -3) | ~9 | 0 |
| 4 | Implementer (items 3+4: cache + Reset + render) | api.py (+101 -4); mcp-server-editor.js (~+150); test_mcp_connection_reset.py (NEW, 310); test_flow_studio_mcp_editor.py (+browser tests) | ~247 | ~310 |
| 5 | Implementer (Reset placement + post-OAuth visibility + auto-test on create) | mcp-server-editor.js (~+90 -14); studio.js (+28); studio.css (+5); test_flow_studio_mcp_editor.py (+~270) | ~109 | ~270 |
| 6 | Implementer (OAuth callback rebrand + auto-close) | api.py (+108 -10) | ~98 | 0 |
| 7 | Implementer (Last updated relocation + Delete trashcan) | mcp-server-editor.js (+~30 -14); studio.css (+~20); test_flow_studio_mcp_editor.py (+7) | ~36 | ~7 |
| 8 | Architect (Shape A vs B) → recommended Shape A; operator pushed back on operator burden | — | — | — |
| 8b | Architect (Shape C re-evaluation) → recommended Shape C; operator confirmed | — | — | — |
| 9 | Implementer (Shape C: auto-detect auth posture) | streamable_http.py (+85 -2); api.py (+97 -16); _pool.py (+18 -11); test_auth_posture_probe.py (NEW, 160); test_mcp_connection_reset.py (+219); test_mcp_pool.py (+87); test_oauth_test_connection_endpoint.py (+19) | ~171 | ~485 |

**Cumulative production LOC (excluding seven vibing-surface UI files per §2)**: api.py (~306) + streamable_http.py (~85) + _pool.py (~18) = **~409 LOC**. Under the §2 cumulative ceiling of ~600 LOC. ✓

**Cumulative production LOC in vibing-surface UI files** (mcp-server-editor.js + studio.css + studio.js): ~452 LOC. Excluded from §2 ceiling per the carve-out for the seven vibing surfaces.

**Cumulative test LOC**: ~1236 LOC across 4 test files (1 new, 3 extended).

#### Caplog Gate

`docker compose logs the-one 2>&1 | grep -c "MCPClient.disconnect"` at leg close: **0** ✓ (target: 0).

#### Cloudflare source state at leg close

- `cloudflare_api` (streamable-http, OAuth): registered, OAuth-authed via fresh-DCR + consent flow + `_cache.auth_posture: "oauth"` persisted. Tools list cached. **Ready for L3 (HTTP attach) and L5 (HTTP in chat) to inherit.**
- Cloudflare docs MCP (streamable-http, no-auth — added during A-L1-7 absorption): registered, `_cache.auth_posture: "no_auth"` persisted, tools list cached. **Available for L3/L5 if operator wants no-auth HTTP coverage in those legs.**

#### L8 bundled fresh-context review queue

Per Flight Design Decision §8, all L1 inline-fix LOC contributes to the L8 bundled review. Specific items to flag for the L8 reviewer:

- **Implementer batch 4's `oauth_active: bool` GET response field** — minor API surface addition not in original architect spec; justified at the time because the architect's "frontend checks for OAuth-prefixed key" instruction couldn't work post-strip. Reviewer should ratify.
- **Implementer batch 9's defensive `except Exception` catch in `_probe_auth_posture`** — wider than `httpx.RequestError + asyncio.TimeoutError`; mirrors cancel-scope-leak avoidance principle. Reviewer should second-opinion.
- **Shape C absorbed against §5's original "absorb branch empirically unreachable for A6" framing** — §5's reasoning was sound for Shape B; Shape C bypasses Shape B's anyio risk entirely via no-SDK-engagement probe. The §5 framing should be updated at L8 to reflect that the carve-out exclusion was specific to Shape B, not all auto-detect approaches.

#### Notes

- Branch state at leg start: `main`. Implementer batch 2's first run noted that the F9 branch wasn't checked out and worked on `main`; Flight Director created `flight/09-alignment` carrying uncommitted changes after batch 2 returned (no rework needed; uncommitted changes follow branch checkout).
- Workflow validated: parent context stayed in vibing-and-triage role per §9; ALL code-change work dispatched to subagents. F9 §9 design-decision pattern empirically vindicated — parent context never read full diffs or investigation traces, only return summaries.
- Architect-pass-for-known-problematic-paths per §7 fired three times (batch 1 architect for items 3+4 design; batch 8 architect for Shape A vs B; batch 8b architect for Shape C re-evaluation). All three caught real architectural issues that affected the implementer's plan.
- The exploratory-vibing-vs-scripted-walk variation should be noted at L8 mission close as a methodology insight: in this leg, scripted scenarios were a less-effective frame than exploratory operator-driven vibing for surfacing real polish/UX issues. Future alignment legs may adopt exploratory framing as the primary mode with scripted scenarios as fallback / coverage check.

---

## Decisions

### Shape C absorption (L1, batch 8b)
**Context**: Operator surfaced F8 A6 (no-auth HTTP MCPs fail) during L1 vibing. Architect's first pass (batch 8) recommended Shape A (operator-declares `auth_required` field). Operator pushed back on operator burden.
**Decision**: Flight Director proposed Shape C (HTTP-level pre-flight detection via bare httpx — no SDK engagement on probe path). Architect re-evaluated and confirmed Shape C dominates A and B. Operator approved absorb.
**Impact**: F9 absorbs auto-detect that F8 carved out as Shape B-shaped; Shape B (anyio-isolated SDK probe, mission-sized) remains correctly deferred to a future flight if ever needed. F8 Action Item "no-auth MCP server detection" → resolved by F9 L1.

### Branch creation post-batch-2
**Context**: Implementer batch 2 noted no F9 branch existed; worked on `main`.
**Decision**: Flight Director created `flight/09-alignment` carrying uncommitted changes after batch 2 returned.
**Impact**: All subsequent L1 work landed on the correct branch.

---

## Deviations

### Exploratory vibing instead of scripted 10-scenario walk
**Planned**: L1 leg artifact specified 10 scripted operator scenarios.
**Actual**: Operator drove via exploratory vibing — created sources, tested connections, surfaced UX issues organically across multiple Refresh/Reset/OAuth/Create cycles.
**Reason**: Exploratory framing surfaces operator-felt polish issues more effectively than scripted scenarios for vibing legs. Each polish-issue surface drove a subagent dispatch + re-verification cycle.
**Follow-up flight scaffolding**: Methodology insight captured for L8 mission-close note: future alignment legs may adopt exploratory framing as primary, scripted scenarios as fallback/coverage check.

### F9 §5 framing exception for Shape C
**Planned**: F9 §5 declared the absorb branch "empirically unreachable" for F8 A6 carve-out.
**Actual**: Architect identified Shape C (HTTP-level pre-flight, no SDK engagement) which §5's framing did not consider — §5's reasoning was sound for Shape B (anyio-isolated SDK probe) but Shape C bypasses Shape B's risk surface entirely.
**Reason**: §5's "unreachable" claim was Shape-B-specific, not all auto-detect approaches. Shape C is structurally different.
**Follow-up flight scaffolding**: F9 flight artifact §5 should be updated at L8 to clarify the framing was Shape-B-specific. No new flight needed.

---

## Anomalies

> Cross-leg index. L1 anomalies mirrored from "L1 → Anomalies Captured" above.

### A-L1-1 — Custom headers section formatting
**Observed**: Section above Tools (should be below); table headers always-visible (should hide when empty); sensitive tooltip on value field (should be info icon on header); sensitive checkbox (should be toggle); delete button (should be trash icon).
**Severity**: cosmetic
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 1+2)
**Resolution**: shipped — see L1 Inline Fixes table.

### A-L1-2 — "Test connection" copy didn't reflect persist behavior
**Observed**: Button labeled "Test connection" but post-F8 behavior persists tools cache, not just probes.
**Severity**: cosmetic
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 1+2)
**Resolution**: renamed to "Refresh connection" + refresh-cw icon.

### A-L1-3 — CSS cascade-layer source-order trap on Sensitive toggle + table width
**Observed**: Sensitive-column toggle invisible (positioned absolutely outside cell); Custom Headers table spans full width.
**Severity**: cosmetic
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 1+2 follow-up)
**Resolution**: specificity bump to `.mcp-kv-sensitive-cell .tool-enable-switch` (0,3,0); table `width: 100%` → `auto`.

### A-L1-4 — Reset placement + post-OAuth visibility + manual create-then-Refresh
**Observed**: Reset in Danger Zone (not actually dangerous); Reset stays hidden after fresh OAuth until page reload; create-form Save lands on edit page but operator must manually click Refresh.
**Severity**: degraded (reset visibility), cosmetic (placement, auto-test)
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 5)
**Resolution**: Reset moved next to Refresh in `.mcp-connection-actions` flex container; post-OAuth refetch via `syncResetButtonVisibility()` targeted DOM mutation; create-form Save dispatches `dataset.autoRun='1'` synthetic Refresh click; `noAutoPopup` opts flag suppresses auto-popup on auth_required.

### A-L1-5 — Generic OAuth callback success page
**Observed**: OAuth callback success page generic-looking, doesn't match studio theme; doesn't auto-close.
**Severity**: cosmetic
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 6)
**Resolution**: themed via `_render_oauth_callback_page()` helper sharing studio CSS tokens via `/static/css/{fonts,tokens}.css` + `/static/js/theme.js`; success path auto-closes after 1.2s; failure path themed but does NOT auto-close.

### A-L1-6 — "Last updated" location + Delete glyph
**Observed**: "Last updated" rendered above Tools list (operator wanted next to Refresh/Reset); source-level Delete button missing trash glyph (per-row already had it).
**Severity**: cosmetic
**Surfaced in**: L1
**Triage**: inline-fix (Implementer batch 7)
**Resolution**: relocated to `.mcp-connection-actions` trailing element via `margin-left: auto`; Delete button gains `App.icon('trash')` outside the `data-confirm-title` span.

### A-L1-7 — F8 A6 carry-forward: no-auth HTTP MCPs fail with consent_url_timeout
**Observed**: Cloudflare docs MCP (no auth required) returned 200 OK to bare initialize; current code expected 401 to trigger OAuth flow; `consent_url_future` never resolved → 15s timeout → `{"status":"error", "error":"consent_url_timeout"}` rendered in UI.
**Severity**: blocking (workflow gap; no-auth HTTP MCPs unusable)
**Surfaced in**: L1
**Triage**: F8 had carved out as Shape B (mission-sized; deferred). Operator directed F9 to absorb. Architect re-evaluated → identified Shape C (HTTP-level pre-flight detection bypassing SDK entirely → zero anyio risk surface). Inline-fix / Implementer batch 9.
**Resolution**: shipped — `_probe_auth_posture` helper in `streamable_http.py` (~85 LOC); Phase 0 in `test_mcp_connection`; `_cache.auth_posture` hint persisted in `source.config["_cache"]`; pool worker reads hint to skip OAuth provider construction. F8 Action Item resolved-by-F9-L1.

---

## Session Notes

### 2026-05-09 — L1 vibing session
Single-day leg execution. Operator drove exploratory vibing across 8-9 subagent dispatch batches. Caplog clean throughout (verified at batch transitions and at leg close: 0 occurrences of `MCPClient.disconnect`).

Highlights:
- Operator-felt sign-off achieved across all surfaced anomalies.
- F8 A6 (no-auth HTTP MCP detection) absorbed via Shape C — empirically validated the §9 subagent-isolation pattern under a §7 architect-pass-required scenario (architect ran twice for the A6 design re-evaluation).
- Polish-density was high: 7 distinct UI/UX anomalies surfaced and fixed across batches 2, 3, 5, 6, 7. Each was operator-felt at re-verification.
- The 9-batch dispatch count stayed within F9 §2's cumulative LOC ceiling (~409 production LOC outside vibing-surface UI files; ~452 LOC inside vibing surfaces; ~1236 LOC of test additions).
