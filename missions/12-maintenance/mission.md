# Mission: Maintenance (Post-M11)

**Status**: active

## Outcome

Resolve the codebase-health issues identified in the [2026-06-04 maintenance report](../../maintenance/2026-06-04.md), triggered by the completion of Mission 11 (Discord Connector Depth). After this mission lands: the four runtime-dependency CVEs are patched and the lockfile regenerated; a **lint/format enforcement gate** (pre-commit + CI fail-on-violation) is installed so the ruff-baseline drift stops recurring; the connector error-taxonomy gaps are wired through (collapsed broad-except narrowed, ephemeral-followup HTTPException mapped, `ConnectorAuthRequired` either wired or removed); the new Mission-11 connector-editor UI meets WCAG Level-A operability (keyboard reorder, named toggle, live-region announcements, labeled controls, heading structure); the web `_sessions` cache gains an idle reaper so a long-lived process stops growing unboundedly; and a cleanup grab-bag lands the streaming-parser extraction, a shared JS fetch helper, the documentation/env scrubs, and git/asset hygiene.

## Context

This is the third routine-maintenance mission for `the-one` (after M06 post-M05, and M09 post-M08). It is triggered by Mission 11 (Discord Connector Depth & Robustness, 17 flights — the deepest mission to date), which completed 2026-06-03. The inspection focused on the M11 changed surface (91 source files, ~28k insertions across `connectors/`, `interfaces/web/`, and `db/`).

The connector subsystem itself came through clean on security (inbound XSS, ACL enforcement, secrets masking, injection, SSRF all traced solid) and tests (2935 passed / 0 failures). The work in this mission is the surrounding hygiene the 17-flight push accreted:

- **The lint/format gate is the centerpiece** — this is the *third* recurrence of ruff-baseline drift (M06 established 0 → M07/M08 drifted → M09 restored → drifted again to 78 violations + 97 unformatted). Roundtable confirmed the root cause: there is no CI and no pre-commit hook; `make lint`/`make format` are manual targets nothing depends on. Re-formatting a third time has a proven 100% recurrence rate, so the deliverable is the *gate*, with the cleanup as a one-time side effect.
- **The architectural cluster** deferred since the 2026-05-04 and 2026-05-15 reports was re-evaluated against M11's completion. Two items are pulled in: the web `_sessions` eviction (P4 — single-user does not bound it; one operator accumulates sessions over a long-lived process) and the streaming-parser extraction (P5 — cleanest win, zero behavior change). The rest (P1 connect-error persistence, P2 httpx pooling, P3 WS migration, P8 singleton aiosqlite pool, I1 migration atomicity) stay deferred — they remain correct under the single-process posture with no compounding cost.

**Out of scope (deferred, captured in the report for a future cycle):** P1, P2, P3, P8, I1 (architectural cluster, still serving their purpose); Q3 `api.py` god-module split and Q5 `connector-editor.js` IIFE split (refactors warranting a dedicated planned flight with behavior-test coverage, not maintenance legs); Q6 `_acl.py` axis-level extraction (now 809 LOC, worsening) — flagged for the next ACL-touching flight to carry as a prerequisite. The backlogged **Chat History Retention (XX)** mission was deferred behind this maintenance cycle and is re-evaluated after this mission lands.

## Success Criteria

- [x] `pip-audit` reports no CVEs in shipped runtime dependencies; runtime `aiohttp`/`idna`/`starlette` bumped to fix versions (via explicit `pyproject.toml` floors, since the image builds from `pyproject.toml`, not `uv.lock`); toolchain-only `urllib3` also bumped (dev-tree, not shipped — reclassified during Flight 01 design review); `uv.lock` regenerated; suite green (D1)
- [x] A pre-commit hook AND a CI check both run `ruff check` + `ruff format --check` and **fail** on violations; `ruff check the_one/ tests/` returns 0 and `ruff format --check` reports all-formatted on `main` (Q1) — gate landed in Flight 02; the on-`main` CI green run completes when the PR merges
- [ ] `api.py:2463` broad-except narrowed to expected connector error types, programming errors propagate, the `# noqa: BLE001` crutch removed (T2)
- [ ] The ephemeral-followup non-401 path maps its `discord.errors.HTTPException` to a typed `ConnectorConnectionError` like the other send paths (T1)
- [ ] `ConnectorAuthRequired` is either raised from the Discord auth-failure path it documents, or removed along with its export and docstring promise (Q2)
- [ ] Routing-rule reorder is operable by keyboard (move buttons or arrow-key reorder on a focusable handle) (A2)
- [ ] The connector attach/enable toggle has an accessible name (A3)
- [ ] The connector live-status region announces state changes to screen readers via `role="status"`/`aria-live` (A1)
- [ ] Discord "Bot status" presence select + name input are labeled; editor section titles are programmatic headings (A4, A5)
- [ ] Custom-dropdown focus indicator meets 3:1; `studio.css` transitions respect `prefers-reduced-motion` (A6, A7)
- [ ] web `_sessions` (`app.py:340`) has an idle-TTL reaper (or size cap) modeled on the PTY `_session_registry`; long-lived process no longer grows unboundedly (P4)
- [ ] A shared `_StreamAccumulator` removes the OpenAI/Ollama streaming-parser duplication (and the triplicated byte-emitter); no behavior change (P5)
- [ ] A shared `App.api.fetchJson` helper replaces the duplicated fetch-error-parsing blocks in the studio JS (Q4)
- [ ] Documentation scrubbed: `agents.md:578` phantom event corrected (DOC1), stale Slack/F9 refs removed (DOC2), `.env.example` dead vars dropped + real vars added (DOC3), `os.environ` tunables documented (DOC4), agents.md anchors added (DOC5)
- [ ] 3 stale merged remote branches deleted (G1); oversized brand PNGs re-exported (G2)
- [ ] Maintenance report at `maintenance/2026-06-04.md` carries a backlink to this mission (done at scaffold time)

## Stakeholders

The operator (single-user, local-only). No external stakeholders.

## Constraints

- All work preserves the single-user / single-process / local-only posture documented in `SECURITY-MODEL.md` — do not introduce multi-worker assumptions.
- Read-only inspection has already happened; this mission *implements* fixes. Each leg is atomic (one finding, one fix) and verified before commit.
- No behavior change for P5 (streaming extraction) — the refactor must be provably equivalent (existing provider tests must stay green unchanged).

## Environment Requirements

- Local toolchain (Python 3.11+, `uv`/`pip`, ruff) and the committed `docker compose` dev path (`make` targets). Container `the-one` for the canonical test command (`docker exec the-one pytest …`).
- Browser tests for the a11y flight (`pytest -m browser`, needs `THE_ONE_DEV_MODE=true`).
- Network access for the dependency bump (Flight A) and for deleting remote branches (Flight F / G1).

## Open Questions

N/A — all findings have concrete, Architect-recommended fixes. Any per-leg design choices are noted inline in the leg files.

## Known Issues

- [ ] Q6 `_acl.py` at 809 LOC is worsening — not fixed here; the next ACL-touching flight must carry an axis-level extraction as a prerequisite (flagged for next mission's flight planning).

## Flights

> **Note:** These are scoped from the user-confirmed maintenance shortlist. Flights are ready for execution; the architectural-cluster refactors (Q3/Q5/Q6) are deliberately excluded.

- [x] Flight 01: Dependency CVE Refresh (D1)
- [x] Flight 02: Lint/Format Enforcement Gate (Q1)
- [ ] Flight 03: Connector Error-Handling Correctness (T2, T1, Q2)
- [ ] Flight 04: Mission-11 UI Accessibility Pass (A2, A3, A1, A4, A5, A6, A7)
- [ ] Flight 05: Long-Lived Session Hygiene (P4)
- [ ] Flight 06: Cleanup Grab-Bag (P5, Q4, DOC1–DOC5, G1, G2)
