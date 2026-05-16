# Mission: Maintenance (Post-M08)

**Status**: active

## Outcome

Resolve codebase health issues identified in the 2026-05-15 maintenance report, **AND remove Concourse + self-improvement framing from the project** (operator pivot 2026-05-15, mid-flight). After this mission lands: lint+format zero-baseline restored; `asgi-lifespan` dev-extra installed with a `make doctor` drift-detector; sandbox skip predicate tightened; OAuth callback same-origin script-injection path closed; `_clean_npx` package-name allowlist in place; documentation carry-forwards landed; OpenRouter rebrand gap closed; the three Action Required accessibility findings (form-field error association, listbox keyboard semantics, light-theme contrast) resolved; **AND the project no longer carries Concourse CI infrastructure or self-modification narrative — repo and module names preserved, but the "agent edits its own source + deploys via CI + rolls back" framing is removed from README, agents.md, CLAUDE.md, SECURITY-MODEL.md, and the mission-control project description.**

### Original framing (superseded mid-flight)

The mission's pre-pivot framing was "restore the integrity gate posture M06 established that M07/M08 silently eroded" — Concourse pipeline gate restoration was the centerpiece. Mid-flight (during Leg 1 implementation), the operator decided to remove Concourse + self-improvement from the project entirely (Concourse drifted from being a tool to being maybe-CI-someday; not pulling its weight). The lint+format work is still valuable and proceeds as planned; the deliberate-violation experiment is dropped; the CI/CD findings from the maintenance report become "remove, don't fix"; a new Flight 1 Leg 4 absorbs the removal. The maintenance report stays as-is (it's the inspection snapshot) but is annotated with a "post-write pivot" note.

Out of scope (routed to next mission post-this-maintenance, currently slotted as M10 since this maintenance takes slot 09): stop/cancel button + agent-loop reliability on local models (M08 KI #6/#7); the five module-skipped browser test files + paired `.new-entity-btn` DOM-visibility defect (M08 KI #3); the architectural cluster (singleton aiosqlite production lifecycle, per-call `httpx.AsyncClient` pooling, `_sessions` eviction, per-provider streaming-parser deduplication, MCP SSRF symmetry with LLM provider path, schema migration v7-v9 atomicity). **Repo rename**: the GitHub repo is still `the-one`; rename decision (if desired) is M10 fuel, not in this mission's scope.

## Context

This is the second routine-maintenance mission for `the-one`. The first was Mission 06 (Maintenance), triggered by the 2026-05-04 report after Mission 05 (Built-in Tool System). Since M06, three missions have landed: M06 itself (landed the Action Required items from the 2026-05-04 report), M07 (MCP Integration, 11 flights — ~4,444 LOC of new MCP/OAuth surface), and M08 (GleepGlorp AI Rebrand & UX Polish, 10 flights). M08 closed today, 2026-05-15.

The 2026-05-15 maintenance report ran a full inspection across all 10 categories plus accessibility, with explicit per-item disposition forced on the M08 mission-debrief carry-forward stack. The audit closed 2 stale items (`.checkbox-primary` and `tokens-section.js` panel-radius references — both already resolved but lingering in the M08 debrief notes), validated 5 routings to this mission, and identified one M08 over-claim (the debrief stated F5 L01.5 resolved the singleton aiosqlite concern; the Architect determined L01.5 was test-infrastructure-only and the production architecture is unchanged — re-opened as M10 fuel).

The single new security finding worth shipping this mission lives in M07's new attack surface: the OAuth callback page at `the_one/interfaces/web/api.py:1681-1688` renders `json.dumps(post_message)` directly inside a `<script>` body without HTML-escaping `</`. A malicious-or-compromised third-party OAuth Authorization Server can inject same-origin script that bypasses the Origin allowlist (it executes same-origin precisely because it loads from `127.0.0.1`). This was rated medium-under-operator-trusted by the Security Reviewer but Architect-escalated to Action Required: `SECURITY-MODEL.md` "Future Work" names the MCP server trust boundary as a *gap to close*, not a license to ship exploitable code that lives in that gap. One-line fix.

The three Action Required accessibility findings group naturally: a listbox-keyboard-semantics flight covering three call sites (chat welcome agent picker, session list, admin tools-grid tiles) plus a structural fix for the listbox-option-contains-button issue in `chat/history-buckets.js`, paired with a form-field error association + light-theme token contrast leg that also sweeps in the smaller a11y items (MIME-as-alt on MCP icons, toast 2s duration, telemetry overlay opacity).

## Success Criteria

- [x] `ruff check the_one/ tests/` returns 0 errors on `main` (restored from 69 — F1 Leg 1, commit `7cb3f99`)
- [x] `ruff format --check the_one/ tests/` returns "all files already formatted" (restored from 81 would-reformat — F1 Leg 1)
- [x] ~~CI lint+format gate proven to reject violations via deliberate-violation experiment~~ DROPPED — Concourse removed in F1 Leg 4 (operator decision 2026-05-15)
- [x] `asgi-lifespan` installed in the dev venv AND `make doctor` drift-detection target added (F1 Leg 2, commit `6f2e1f1`)
- [x] `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` skip predicate tightened (F1 Leg 2 — Case B SKIPPED on WSL2 host)
- [x] OAuth callback's `postMessage` JSON escaped against `</script>` injection across all three flow sites (F1 Leg 3 commit A, `e092eb9`)
- [x] `_clean_npx` package-name argument validated against npm-spec allowlist (F1 Leg 3 commit A — rejects `../etc/passwd`)
- [x] `pip-audit` added to dev extras + `make audit` local target (F1 Leg 3 commit A)
- [x] `agents.md ## Provider type extension checklist` includes `_init_provider_state` hook entry (F1 Leg 3 commit B, `daf24e2`)
- [x] `agents.md ## Project Conventions` codifies the "live-read across lazy-resolver boundary" pattern (F1 Leg 3 commit B)
- [x] `.env.example` documents `THE_ONE_DEV_MODE` (F1 Leg 3 commit B — variable survived Leg 4 cleanup)
- [x] `SECURITY-MODEL.md` Future Work section names the MCP `streamable-http` URL gating asymmetry with the LLM provider path (F1 Leg 3 commit B)
- [x] ~~`SECURITY-MODEL.md` documents Concourse team-password rotation cadence~~ DROPPED — Concourse removed in F1 Leg 4
- [x] OpenRouter `_APP_URL` / `_APP_NAME` updated to GleepGlorp AI identity (F1 Leg 3 commit B — `_APP_NAME = "GleepGlorp AI"`; URL retained for repo-name continuity)
- [x] Concourse infrastructure removed: `ci/` directory deleted; `THE_ONE_CONCOURSE_PASS` removed from `.env` (gitignored); `.env.example` already clean (F1 Leg 4, commit `56bfc71`)
- [x] Self-modification framing removed from live narrative: `CLAUDE.md` L56 + `SECURITY-MODEL.md` 3 sites edited; `README.md`, `agents.md`, `Dockerfile`, `docker-compose.yml`, `Makefile` verified clean during recon; mission-control `projects.md` description rewritten locally (file gitignored). Historical mission artifacts (M01-M08) left intact (F1 Leg 4)
- [x] Chat welcome agent picker has roving-tabindex + arrow keys + `aria-selected` toggling (F2 Leg 1, augmented existing handler at `chat.js:184-198`)
- [x] Session-list restructured to `<nav>` + `<ul>` of `<button>` items; `aria-selected` → `aria-current="page"` toggle for active item; tests in `test_flow_keyboard.py` + `test_flow_hash_routing.py` + `test_flow_new_chat.py` updated (F2 Leg 1)
- [x] Admin tools-grid verified keyboard-accessible — no role change (F2 Leg 1, button-grid confirmed)
- [x] Form-field errors carry `aria-invalid="true"` + additive `aria-describedby` + `role="alert"` on first per-row error; new `clearFieldErrorA11y` helper for clear cycle (F2 Leg 2)
- [x] Light-theme `--fg-muted`/`--fg-faint` chrome contrast resolved via scope-the-usage (3 sites rescoped to `--fg-tertiary`: `base.css:144`, `chat.css:15`, `chat.css:35` — F2 Leg 2)
- [ ] Maintenance report at `maintenance/2026-05-15.md` updated with a backlink to this mission (already done at scaffold time)

## Stakeholders

- **Primary user / operator**: relies on the CI gate as a guard against the next mission accumulating quiet drift; relies on a11y fixes for the small set of operators who use keyboard navigation or are screen-reader users
- **Future-self self-modification**: a clean lint baseline reduces noise when the agent edits its own source

## Constraints

- **No architectural change**: this mission is a quick-win bundle, not a refactor. The architectural cluster (singleton aiosqlite production lifecycle, per-call httpx pooling, `_sessions` eviction, streaming-parser dedup, MCP SSRF symmetry) is explicitly out of scope and routed to the next mission.
- **No feature work**: stop/cancel button + agent-loop reliability are out of scope (next mission priority #1).
- **No test-suite-cleanup of the M08-skipped browser modules**: also out of scope (next mission priority #2). The five `pytestmark = pytest.mark.skip` annotations stay in place.
- **All M06 F1 controls must remain intact**: Origin allowlist, https-refusal, SECURITY-MODEL.md doc, encrypted secrets at rest, `.dockerignore`, image pinning, auto-rollback re-verify. Confirm each at flight-debrief close.
- **No skipping CI hooks**: do not use `--no-verify` on commits during this mission. The mission's entire framing is restoring gate posture; bypassing locally would be self-defeating.
- **Output discipline**: per the M08 lesson that cycle-1 design reviews are the highest-ROI control, keep them as default for every leg.

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`); confirm `asgi-lifespan` installs cleanly as part of `[dev]`
- Docker + docker-compose for container testing; `make rebuild` after edits per the project's serving model
- Playwright Python binding for browser tests (no UI flights here, but a11y leg should regenerate any affected pixel baselines locally)
- `ruff` for lint and format (gate restoration is the mission's centerpiece)
- `fly` CLI for triggering Concourse pipeline runs (deliberate-violation experiment)

## Open Questions

> Phase-gate note: all open questions must resolve before flight design begins. Each flight may surface its own open questions during pre-flight; this list captures mission-level ones.

- **Should the deliberate-violation experiment land in a flight log, a maintenance report appendix, or both?** Resolved in Flight 1 design.
- **Drift-detection mechanism shape: `make doctor` target vs CI assertion vs pre-commit hook vs both?** Resolved in Flight 1 design.
- **Does the OpenRouter rebrand string update (`_APP_URL` / `_APP_NAME`) belong in the security/doc leg, or in a future rebrand-gap follow-up?** Working assumption: include this mission's security/doc leg opportunistically since it's one line and lives in the same file family as other M08 carry-forward items.

## Known Issues

> Emergent blockers and issues discovered during execution. Add items here as flights surface problems.

(None at scaffold time.)

## Flights

> **Note:** These are committed (not tentative) since the maintenance scope is concrete. Both flights are derived from the Architect's recommended bundling in the 2026-05-15 maintenance report.

- [x] Flight 1: **Code Hygiene + Concourse Removal** — lint/format restoration (baseline 0 → 0); test-infrastructure fixes (`asgi-lifespan` install + `make doctor`; sandbox skip-predicate); security one-liners (OAuth callback XSS escape, `_clean_npx` allowlist); documentation carry-forwards (`agents.md` `_init_provider_state` + lazy-resolver pattern; `.env.example` `THE_ONE_DEV_MODE` if survives; `SECURITY-MODEL.md` MCP SSRF asymmetry note); OpenRouter rebrand strings; `pip-audit` + `make audit` local CVE awareness; **and the removal of Concourse + self-modification framing (new Leg 4 added mid-flight per operator pivot 2026-05-15)**. Four legs. ~2.5–3.5 days (revised up to accommodate Leg 4 — narrative editing across README/agents.md/CLAUDE.md/SECURITY-MODEL.md is the largest unknown).

- [x] Flight 2: **Accessibility Carry-forward + F1 Tech-Debt Cleanup** — landed 2026-05-16. Three legs (a11y carry-forward + F1-debrief tech-debt bundle, added mid-mission per operator direction). All A.1-A.13 items resolved (firm + opportunistic; zero slippage). F1 tech-debt 6 sub-fixes landed (`make rebuild-browsers`/`audit-bytes`, `make doctor` venv-python3, `agents.md` citation fix + new convention, SECURITY-MODEL.md npm-spec regex doc). Container pytest 1700; ruff 0/0; `make test-browser` 316/35.
