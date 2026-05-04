# Leg: 07-posture-documentation

**Status**: completed
**Flight**: [Pre-Mission-06 Quick Wins](../flight.md)

## Objective

Convert the project's implicit no-auth posture into explicit documented intent. Create `SECURITY-MODEL.md` describing single-user local-only deployment context, no-auth-by-design, dev-mode `0.0.0.0` bind expectation, and the Origin-allowlist mitigation that landed in Leg 05. Also fix `agents.md:3` "Structural Foundation mission" temporal phrasing and absorb the M04 F5 deferred heading-hierarchy a11y refinement (three specific call-outs).

## Context

Maintenance report findings 1.4, 6.1, 6.2, 6.6 (see `maintenance/2026-05-04.md`). **Design-review pass adjustments incorporated** (see flight-log).

- **1.4** (Pass-with-doc): No auth on any HTTP/WebSocket route is the documented threat model (F3 Decision 10: "operator-trusted setup, NOT malicious actor"). Action: write the posture down so it's an inheritable contract, not an implicit decision. Per Architect calibration: this is the action item for SEC-1, not "add auth."
- **6.1**: `agents.md:3` describes itself as "during the Structural Foundation mission" (M01) — temporal phrasing now misleading post-M05. One-line edit.
- **6.2** (RE-SCOPED): The M04 F5 debrief flagged "lines 263-264" as describing pre-HAT tile-X design. The line numbers drifted post-F6 — the actual entries (Agent tile + Confirm-delete) are now at `agents.md:426-427` AND have already been updated to reflect the post-HAT design (line 426: "F5 HAT removed the per-tile X delete in favor of editor-only Danger Zone deletion"; line 427: "The agent-tile per-tile X-button is gone"). **Action**: verify no residual stale fragments at lines 420-460; if clean, mark 6.2 as already-resolved in the maintenance report.
- **6.6** (NARROWED): M04 F5 debrief line 124 specifies three call-outs for the deferred heading-hierarchy work: (a) editor title (`.editor-title` → consider `<h2>` instead of `<h1>` per editor as nested context), (b) section-title heading level review, (c) `.section-nav-header` as `<h2>`. **Time-box**: 15 minutes for these three specific items only; broader audit deferred to a future a11y-polish flight.

This is the smallest leg by file impact but highest by future-contributor value. Documenting the posture explicitly converts a load-bearing implicit decision into a citation-able contract.

## Inputs

- `the_one/agents.md` (existing; 1142 lines)
- `CLAUDE.md` (existing; 373 lines)
- `the_one/interfaces/web/templates/index.html` (existing; for heading hierarchy review)
- M04 F5 debrief at `missions/04-ui-maturity/flights/05-studio-alignment/flight-debrief.md` (existing; for the deferred heading-hierarchy item context)

## Outputs

- `SECURITY-MODEL.md` at repo root (or new section in `agents.md`) documenting:
  - Threat model: single-user local-only; operator-trusted setup; not a malicious-actor scenario
  - No auth: by design; HTTP and WebSocket are unauthenticated; routes include state-mutating endpoints
  - Bind expectations: 127.0.0.1 default; `0.0.0.0` in `docker-compose.yml` is intentional for the dev container; reverse proxy is the deployment-context-dependent surface
  - Origin-allowlist (from Leg 05): same-origin enforcement on state-mutating routes is the cheap mitigation
  - SSRF protection: M05 F5 default; the operator's allowlist only widens with explicit consent
  - Subprocess env: M05 F4 hardcoded allowlist; secrets-manager mission is the future
  - F3 D10 threat model statement inherited
- `agents.md:3` updated: temporal "during the Structural Foundation mission" phrasing replaced
- `agents.md:263-264` updated: pre-HAT tile-X description removed/replaced
- (Optional, if cheap) M04 F5 heading-hierarchy a11y refinement: `<h2>`/`<h3>` consistency in admin/Studio templates

## Acceptance Criteria

- [x] `SECURITY-MODEL.md` exists at repo root with the sections listed in Outputs. Where mechanism details overlap with CLAUDE.md (subprocess env allowlist, SSRF two-layer enforcement, Encryptor 0o600), `SECURITY-MODEL.md` should **summarize and link back to CLAUDE.md** — not duplicate — to avoid drift surface.
- [x] `agents.md:3` no longer says "during the Structural Foundation mission". Replacement uses **mission-agnostic** phrasing (no temporal anchor like "as of M05" — that drifts too). E.g. "describes the **target architecture** of the system. It is updated as missions extend or refactor it."
- [x] `grep "Structural Foundation" the_one/agents.md` returns zero matches after the fix.
- [x] **6.2 verification**: `sed -n '420,460p' the_one/agents.md` shows no residual pre-HAT tile-X language; if clean, no edit needed (already-resolved). If residual fragments found, update them.
- [x] `CLAUDE.md` references `SECURITY-MODEL.md` in a new "Security posture" section inserted **after** the existing "Configuration" section (around line 308) — single-line link, not a long restatement.
- [x] Heading-hierarchy a11y refinement (three specific call-outs from F5 debrief line 124): editor title level, section-title level, `.section-nav-header` as `<h2>`. If any single call-out exceeds the 15-min time-box, defer with a flight-log note and surface as a follow-up.
- [x] No regression in browser tests (heading edits should be a11y-positive, not visual-breaking).
- [x] **Final-leg post-completion**: this leg is the LAST autonomous leg of Flight 1. Per the deferred-commit pattern, the wrap-up commit absorbs all 7 legs' work together (driven by Phase 2d Reviewer pass after this leg lands, not in this leg's scope).

## Verification Steps

- `cd /home/cprch/projects/the-one && ls SECURITY-MODEL.md` — file exists (OR `grep "## Threat Model" the_one/agents.md` returns a section)
- `cd /home/cprch/projects/the-one && head -10 the_one/agents.md` — line 3 no longer says "Structural Foundation mission"
- `cd /home/cprch/projects/the-one && sed -n '260,270p' the_one/agents.md` — lines 263-264 reflect current design
- `cd /home/cprch/projects/the-one && grep "SECURITY-MODEL" CLAUDE.md` — link present
- `cd /home/cprch/projects/the-one && pytest -m browser tests/browser/ -q 2>&1 | tail -10` — no regression

## Implementation Guidance

1. **Write `SECURITY-MODEL.md`** (recommended over agents.md section for citability)
   - Suggested skeleton:
     ```markdown
     # Security Model

     This project is a single-user local development tool. The threat model and
     security posture below are deliberate design choices, not gaps to fix.

     ## Threat Model

     - **Audience**: solo developer/operator running the agent on their own
       machine. No multi-user scenarios. No internet exposure. No untrusted
       LLM-supplied tool inputs from external clients.
     - **Trust boundary**: the operator is trusted. Tool inputs from agents are
       constrained by per-tool config (resolver-narrowed) but are NOT treated as
       hostile.
     - **F3 Decision 10**: "operator-trusted setup, NOT malicious filesystem
       actor." Inherited by F4/F5/F6.

     ## Authentication

     - **No auth on HTTP/WebSocket routes by design.** Every endpoint, including
       state-mutating routes (`POST /api/encryption/rotate`, `PUT /api/agents/{name}`,
       etc.), is unauthenticated. Adding auth would violate the single-user posture.
     - The Origin-allowlist middleware (M06 F1 L5) enforces same-origin requests on
       state-mutating methods to close the drive-by-LAN attack surface without
       adding auth.

     ## Network Bind

     - Default `host=127.0.0.1` (localhost only).
     - `docker-compose.yml` overrides to `0.0.0.0` to be reachable from the host.
       Dev-mode is intentional; the operator owns the docker bridge network.
     - Production form factor (desktop app, future) reverts to localhost-only.

     ## Tool Execution Boundary

     - **Filesystem**: per-tool path allowlist (NarrowPrefix), denylist
       (NarrowSuperset), read-size cap, binary-file refusal, scope-first
       ordering. M05 F3.
     - **Execution**: hardcoded subprocess env allowlist
       (`PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TERM`, `TZ`); no
       widening surface. Per-call timeout/output caps. Per-agent PTY session
       isolation `(agent_name, session_id)`. M05 F4.
     - **Web**: SSRF resolve-then-pin against loopback/RFC1918/link-local/
       cloud-metadata; SNI preservation; IP-literal short-circuit; per-call
       redirect/response caps. M05 F5.

     ## Secrets

     - LLM provider API keys: encrypted at rest via `Encryptor` (`AES-GCM`).
       Encryption key file is mode `0o600`.
     - `.env` gitignored.
     - `THE_ONE_CONCOURSE_PASS` is a local-Concourse-only credential; rotation
       happens out-of-band.
     - No secrets in `.env.example`, `Dockerfile`, `docker-compose.yml`, or
       `ci/pipeline.yml`.

     ## What This Model Excludes

     - Multi-user / multi-tenant deployments
     - Public internet exposure (without a reverse proxy adding auth)
     - Hostile LLM provider scenarios (the LLM provider's responses are trusted)
     - Hostile filesystem actor scenarios (operator owns the local environment)

     ## Future Work (NOT in scope today)

     - Secrets manager (replaces `THE_ONE_CONCOURSE_PASS` style env vars)
     - MCP server trust boundaries (each MCP is a separate trust domain)
     - Multi-user form factor (would require auth + per-user tool isolation)
     ```
   - Adjust to match what's actually in the codebase. Cross-check against `agents.md` and `CLAUDE.md` to avoid duplication.

2. **Fix `agents.md:3` temporal phrasing**
   - Open `agents.md`. Line 3 currently says: "Development-facing architecture reference for the-one. This file describes the **target architecture** — the structure being implemented during the Structural Foundation mission. It is not loaded at runtime."
   - Replace with mission-agnostic phrasing: "Development-facing architecture reference for the-one. This file describes the **target architecture** of the system. It is updated as missions extend or refactor it. It is not loaded at runtime."
   - **Verify**: `grep "Structural Foundation" the_one/agents.md` returns zero matches.

3. **Verify `agents.md:420-460` for residual stale tile-X language**
   - The M04 F5 debrief flagged lines 263-264 at debrief time. The same content (Agent/entity tile + Confirm-delete entries) is now at `agents.md:426-427`, and inspection shows both have already been updated post-HAT.
   - Read `sed -n '420,460p' the_one/agents.md`. Confirm no residual fragments mention per-tile X-button as a current design (post-HAT, the X-button is gone — `entity-tile` is a single `<button>` with no sibling-X wrap).
   - If clean: no edit needed. Note "6.2 already-resolved" in the flight-log entry.
   - If residual fragments found: update them inline.

4. **Reference SECURITY-MODEL.md from CLAUDE.md**
   - Open `CLAUDE.md`. Locate the existing "Configuration" section (around line 308).
   - Add a new section AFTER it titled "## Security posture" with a single line: "See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the project's threat model and intentional security choices (no-auth-by-design, single-user local-only, Origin-allowlist mitigation, SSRF/subprocess boundaries)."
   - Do NOT duplicate the policy details in CLAUDE.md — the SECURITY-MODEL.md is the single source of truth; CLAUDE.md links to it.

5. **M04 F5 heading-hierarchy a11y refinement (narrowed scope)**
   - Read `missions/04-ui-maturity/flights/05-studio-alignment/flight-debrief.md` lines 64 and 124 for the original deferred item.
   - Three specific targets (15-min time-box; defer the rest):
     a. **Editor title**: `.editor-title` is currently `<h1>`. Studio/admin editors are nested inside the area panel, not the page root. Audit: is `<h1>` correct for an editor's title, or should it be `<h2>`? Decision criterion — what's the page-level `<h1>` for these areas? If the area itself has no semantic `<h1>`, then `.editor-title` as `<h1>` is fine; the F5 debrief preference of `<h2>` would apply only if a page-level `<h1>` is being added/standardized.
     b. **Section-title**: review the `.section-nav-header` rendering in `static/js/areas/layout/section-nav.js` — if it's currently a `<div>` or `<span>`, change to `<h2>`. If already a heading, verify level.
     c. **Skipped levels**: spot-check the dynamically-rendered HTML in `studio/` and `admin/` — no `<h1>` followed directly by `<h3>` (intermediate `<h2>` required).
   - If a single call-out balloons beyond 15 min (e.g., requires multi-file refactor or visual regression review), defer it; document the call-out + reason in the flight-log entry.

## Edge Cases

- **`SECURITY-MODEL.md` vs `agents.md` section**: implementer's choice. `SECURITY-MODEL.md` at repo root is more citable from external links and operator onboarding. `agents.md` section is more discoverable for Claude Code sessions. Either is fine; pick one and commit.
- **Heading-hierarchy refinement may snowball**: time-box at 15 min. If you find more than 3-4 skipped-level instances, document the count + locations in flight-log.md and defer the rest.
- **M04 F5 debrief description of "tile-X design"**: I have not loaded the precise lines 263-264 content from `agents.md`. The implementer should read the actual content first; the description above ("pre-HAT tile-X") is the M04 debrief's framing.

## Files Affected

- `SECURITY-MODEL.md` — NEW file at repo root (or new section in `the_one/agents.md`)
- `the_one/agents.md` — line 3 phrasing update; lines 263-264 cleanup
- `CLAUDE.md` — reference to SECURITY-MODEL.md
- (Optional) `the_one/interfaces/web/templates/*.html` — heading-hierarchy fixes if cheap
- (Optional) `the_one/interfaces/web/static/js/areas/admin/*.js` and/or `studio/*.js` — heading-tag adjustments if needed

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] `SECURITY-MODEL.md` (or agents.md section) covers all 7 elements
- [ ] `agents.md` stale lines updated
- [ ] CLAUDE.md references the security model
- [ ] (Optional) heading-hierarchy refinement done OR explicitly deferred with note
- [ ] No regression in browser tests
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] **Final leg of flight**: update flight.md status to `landed` and check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
