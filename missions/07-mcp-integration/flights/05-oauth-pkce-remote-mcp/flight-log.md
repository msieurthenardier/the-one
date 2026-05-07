# Flight Log: Lazy OAuth 2.1 + PKCE for Remote MCP Servers

**Flight**: [Lazy OAuth 2.1 + PKCE](flight.md)

## Summary

Pre-execution. Phase 1 + 1b context-gathering complete; F4 debrief feedback pulled forward (citation-audit gap in `leg/SKILL.md` Phase 2 item 7 — landed in mission-control PR #5; F2-known-issue follow-on owned by F5 L1; constraint #6 mission amendment for agent-loop pause/resume primitive landed at design time). UX shifted from original Settings-driven OAuth config to lazy/discovery-driven (RFC 9728 PRM + RFC 8414 AS metadata + RFC 7591 DCR + auth-code-with-loopback at first 401) per user direction. Awaiting Architect cycle-1 design review.

---

## Phase 1b Reconnaissance Report

F5 sources work items from TWO prior artifacts: F4 flight debrief (which itself sourced from F4 execution) + Mission 07 Open Questions (the OAuth-shape and client-registration questions assigned to F5).

### Reconnaissance Table

| # | Item | Source | Classification | Evidence | Recommendation |
|---|------|--------|----------------|----------|----------------|
| 1 | F4 R1 [Critical]: F2-known-issue follow-on (parallel non-CM transport helpers; retire `RuntimeError: generator didn't stop` swallow log noise) | F4 debrief | `confirmed-live` | `the_one/mcp/transports/streamable_http.py:55-110` is `@asynccontextmanager`; consumed by 1 prior test (`tests/test_mcp_client.py::TestConnectStreamableHttpProduction`). Stdio symmetric. F2-known-issue still present per HAT Finding #1 | F5 L1 owner — lands BEFORE OAuth backend so refresh path uses clean dispatcher contract |
| 2 | F4 R3: bwrap subprocess `wait()` gap (HAT Finding #2) | F4 debrief | `not-applicable-to-F5` | F5 is streamable-HTTP only; no bwrap | Defer to F6 or routine maintenance |
| 3 | F4 R4: `procps` Dockerfile (HAT Finding #3) | F4 debrief | `confirmed-live` | Dockerfile lacks `procps`; F5 HAT may benefit | Roll into F5 L0 (small infra leg) |
| 4 | F4 R5/R6/R7: fifth Project Convention; README drift fix; safety-net log message | F4 debrief | `confirmed-live` (low) | Cosmetic doc + log-string edits | Defer to routine maintenance — not F5-load-bearing |
| 5 | F4 R10 [Forward]: F5 design constraint — do NOT add NEW direct callers of `connect_streamable_http` as `async with` | F4 debrief | `confirmed-live` (constraint) | Existing 1 caller is what blocks the F2-known-issue fix; F5 must not add more | Encoded as a hard constraint in F5 §3 + L1 acceptance criteria |
| 6 | Q-OAUTH-FLOW: device-code vs auth-code-with-loopback-redirect | mission Open Questions | `resolved-at-design` | Desktop-app form factor; loopback is OAuth 2.1 spec-canonical | Auth-code-with-loopback is the floor; device-code deferred to a future flight if SSH-only operator demand surfaces |
| 7 | Q-CLIENT-REG: pre-registered / CIDM / DCR | mission Open Questions | `resolved-at-design` | User design call: "MCP maker owns OAuth flow correctness" → DCR is the natural primary path; pre-registered table is irrelevant for spec-compliant servers | DCR-first with user-entered fallback for non-DCR-supporting AS (rare); pre-registered table dropped |
| 8 | Mission constraint #16: "No agent-loop semantic changes beyond tool-registry composition" | mission constraint | `resolved-at-design` (amend) | The lazy-OAuth UX requires a pause/resume primitive in the loop. User confirmed (2026-05-07): "B is what we want for sure, that constraint is wrong." | Constraint amended in mission.md at flight design time; F5's `auth_required` ToolResult type is the only sanctioned loop-level extension in this mission |
| 9 | Citation-audit gap (F4 debrief R2) | F4 debrief | `already-satisfied` | Codified in `mission-control` PR #5 (`leg/SKILL.md` Phase 2 item 7 sharpened with explicit grep command for direct-caller search) | Retired — methodology improvement landed; F5 leg authors apply the new gate |

### Open Questions Carried Forward to F5 Design

All 8 design-decision items resolved at flight design (Phase 3 user input 2026-05-07). See flight.md §§Open Questions.

### Action Items NOT Carried Into F5 (with justification)

| Item | Reason |
|------|--------|
| F2 zombie bwrap subprocess `wait()` gap | F5 is streamable-HTTP only; no bwrap subprocesses. Defer to F6 or routine maintenance. |
| F4 README drift (60s → 30s) | One-character edit; doesn't earn a flight commit on its own. Defer to routine maintenance. |
| F4 safety-net log message extension | F5 L1 actually RETIRES the safety-net's normal-flow firing; the log-message extension becomes lower priority post-L1. Defer. |
| F4 fifth Project Convention `same-task-anyio-cm-ownership` | Documentation-only; defer to routine maintenance. |
| F4 R8 (`UrlElicitationRequiredError` propagation test) | Already deferred in F4 — orthogonal to F5. |
| Pre-registered OAuth provider table | User explicitly dropped at design time (DCR-first). |
| Settings UI per-source OAuth status badge | User explicitly dropped at design time (chat-only surface). |

---

## Flight Director Notes

> Populated by the orchestrator during agentic-workflow execution.

### Phase 5b Architect Design Review

#### Cycle 1 — overall assessment: **needs rework**

Architect raised 3 high + 4 medium + 3 low + 8 questions.

**High-severity issues (load-bearing)**:

1. **H1 — SDK already ships OAuth machinery (~350 LOC saved if consumed)**: `mcp.client.auth.OAuthClientProvider` (in pinned `mcp==1.27.0`) provides PKCE generation, RFC 9728 PRM discovery, RFC 8414 AS metadata discovery (with OIDC fallback), RFC 7591 DCR registration, RFC 8707 audience validation, pre-emptive token refresh, and httpx integration via `auth=` kwarg. F5's draft re-implemented all of this in `pkce.py` + `discovery.py` + `registration.py` + `flow.py` + `_state.py` (~400-600 LOC).
2. **H2 — L1's stack-ownership claim contradicts `the_one/mcp/README.md §3`**: README states AsyncExitStack alone does NOT solve cross-task disconnect; F5's L1 claim that the dispatcher-owned-stack pattern retires the F2-known-issue is too broad without scoping.
3. **H3 — Citation drift**: F5 referenced `the_one/agent/types.py::ToolResult` for the new `is_auth_required` field; that path does NOT exist. `ToolResult` lives at `the_one/llm/base.py:25` (verified). Adding domain-specific OAuth fields to a provider-neutral LLM type is also an architectural call.

**Medium-severity issues**:
- M1 — multi-tool-call iteration semantic gap (defer / drop / re-invoke?)
- M2 — OAuth-token re-save through PUT corrupts secrets (masking returns `"***"` for non-string secrets, doesn't round-trip)
- M3 — HAT target's AS metadata + DCR are NOT spec-compliant; GitHub MCP's AS at `https://github.com/login/oauth` does NOT serve `oauth-authorization-server` or `openid-configuration` `/.well-known/` endpoints AND does NOT implement DCR (probed empirically 2026-05-07 16:21 UTC)
- M4 — citation-audit gap: F5 only flagged L5; L1, L4, L6 also touch public-symbol signatures and need the audit per `leg/SKILL.md` Phase 2 item 7

**Low-severity issues**:
- L1 — discovery fallback ordering (irrelevant if SDK consumed)
- L2 — loopback port hardcoded `8484` (should derive from runtime config)
- L3 — token-expiry pre-emptive-vs-reactive refresh (free if SDK consumed)

#### Cycle 1 disposition (resolved 2026-05-07, user picks):

User picked: **H1=A (consume SDK), H2=C (two-tier HAT, accept GitHub manual-path non-compliance), H3=B (generic `metadata: dict | None` field on `ToolResult`), M1=defer-and-re-dispatch, M2=strip-from-GET, M3=codify-citation-audit-on-L1/L4/L6**.

Inline rework applied to flight artifact:
- §§7-8 collapsed into §7 ("Discovery + DCR + PKCE — delegated to SDK's `OAuthClientProvider`"). Module placement (§11) shrunk to `storage.py` + `handlers.py` + `_state.py` + `manual_metadata.py` + `errors.py` (~250 LOC; was ~600).
- §3 (L1) reframed to scope the F2-known-issue retirement to F4-pool-routed path; direct cross-task usage outside the pool still hits the safety net.
- §4 + L3 updated: generic `metadata: dict | None = None` field on `the_one/llm/base.py::ToolResult`; multi-tool-call deferral semantic locked (preceding tool-call results land in messages normally; current + remaining tool calls deferred to `_deferred_tool_calls`; on resume, re-dispatch in order).
- §5 + L2 updated: GET strips OAuth-managed keys (access_token, refresh_token, token_expires_at, dcr_credentials) from response entirely; PUT merge preserves them from `existing.secrets` regardless of incoming payload.
- §10 + L6 updated: two-tier HAT — Tier-1 in-repo FastMCP-shaped AS fixture (CI), Tier-2 GitHub MCP via manual-entry path (manual / documented in `tests/HAT.md`).
- §11 (module placement) rewritten with shrunk module list + cross-references to SDK primitives.
- L1, L4, L6 (renumbered as L4 in new layout) acceptance criteria extended to require `grep -rn` citation audit per `leg/SKILL.md` Phase 2 item 7.
- Loopback port derived from runtime config (`settings.port`) at flow-start time.

Legs renumbered: L0 (bootstrap), L1 (transport-stack helper), L2 (OAuth SDK adapter — collapses old L2+L3+L4), L3 (agent-loop pause/resume — was L5), L4 (transport OAuth integration — was L6), L5 (chat UI — was L7), L6 (HAT — was L8). 7 legs total (was 9).

Cycle 2 verification: spawn Architect to verify the inline rework resolved the 3 highs + 4 mediums correctly without introducing new high-severity issues.

---

## Leg Progress

> Populated as legs land.

---

## Decisions

> Runtime decisions not in original plan. Populated during execution.

---

## Deviations

> Departures from planned approach. Populated during execution.

---

## Anomalies

> Populated as encountered during execution.

---

## Session Notes

> Chronological notes from work sessions.

#### Cycle 2 — overall assessment: **needs rework** → resolved inline

Architect raised 2 NEW high + 4 medium + 3 low. The NEW highs were:

- **H4 (mechanical)**: §7's SDK API citations were fabricated. Real `mcp.client.auth` exports exactly 6 symbols; my submodule references (`mcp.client.auth.discovery`, `mcp.client.auth.registration`, `mcp.client.auth.utils.get_protected_resource_metadata_url`) don't exist. **Fix**: §7 simplified to a one-paragraph "we consume `OAuthClientProvider` + implement `TokenStorage`; everything else is internal to `async_auth_flow`" — the actual integration contracts live in §1, §2, §11 which were already correct.
- **H5 (design call)**: SDK's `OAuthClientProvider.__init__` has no parameter to inject pre-known AS metadata. `async_auth_flow` always runs discovery; manual-entry path can't complete via stock SDK. **User picked B (subclass)**: `ManualOAuthClientProvider(OAuthClientProvider)` overrides the metadata-discovery method to short-circuit when manual fields are present. Cleanest of the 5 options offered (no private-attr mutation, no extra HTTP service, doesn't abandon the GitHub-MCP HAT).

Mediums + lows resolved inline:
- M4 — `continue` virtual signal carve-out (added to §4)
- M5 — handler-closure capture documentation (added to §4)
- M6 — `connect_streamable_http` test-seam adapter for `auth=` (added to L4 acceptance criteria)
- M7 — `:8484` callback URL deterministic-default reconciled with §1's runtime-port resolution (added to §10 Tier-2)
- L4 — touchpoints outside `oauth/` (added to §11)
- L5 — `agents.md:52` → `agents.md:53-56` citation precision
- L6 — flight-vs-leg citation-convention boundary documented in §Legs Note

Cycle-2 disposition: rework correctly resolves H4 + H5 + 4 mediums + 3 lows inline. No cycle 3 (max 2 cycles per agentic-workflow). Pre-Flight Checklist marks cycle 2 complete.

### Phase 6 — User approval (pending)

Spec is design-review-approved; awaiting user walkthrough + approval before commit + L0 implementation.
