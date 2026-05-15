# Flight Log: Professional README

**Flight**: [Professional README](flight.md)

## Summary

Final flight of Mission 08 (GleepGlorp Rebrand & UX Polish). Delivers the top-level `README.md`, three dark-theme screenshots under `docs/screenshots/`, and a small `agents.md` convention addition promoting the `?perf=1`/localStorage debugging-gate pattern introduced by F7's `App.perf` module.

---

## Reconnaissance Report

Phase 1b recon walked every cited item from the Mission 08 spec's Flight 8 line ("Now that every screen reflects the new identity and the app is performant, write a top-level `README.md`…") plus the F7 debrief's action-item list. All items classified `confirmed-live` or `confirmed-live (in-scope as side scope)`. Zero retirements.

| Source item | Classification | Evidence | Recommendation |
|---|---|---|---|
| No top-level README exists | confirmed-live | `find -maxdepth 2 -name 'README*'` returns only `.flightops/README.md` (gitignored) and `.pytest_cache/README.md` (auto-generated) | In scope — write `/README.md` |
| Brand assets present | confirmed-live | `the_one/interfaces/web/static/brand/` contains `gleepglorp_med.png`, `gleepglorp_small.png`, `gleepglorp_icon.png`, `gleepglorp_banner.png`, favicon set | Reference `gleepglorp_med.png` as the hero |
| No screenshots dir yet | confirmed-live | No `docs/screenshots/`, no `assets/`. `tests/browser/__snapshots__/` exists but is gitignored per `.gitignore:19` | Create `docs/screenshots/` (non-gitignored) |
| FastAPI title rebranded | confirmed-live | `the_one/interfaces/web/app.py:129` `app = FastAPI(title="GleepGlorp AI", lifespan=lifespan)` | Reference in README; no rebrand work needed |
| Index HTML title rebranded | confirmed-live | `the_one/interfaces/web/static/index.html:11` `<title>GleepGlorp AI</title>` | Reference in README; no rebrand work needed |
| Topbar wordmark rebranded | confirmed-live | `the_one/interfaces/web/static/js/app.js:29` uses `gleepglorp_banner.png` as topbar banner | Reference in README; no rebrand work needed |
| `SECURITY-MODEL.md` exists at root | confirmed-live | `SECURITY-MODEL.md` (141 lines) | README links to it directly |
| `CLAUDE.md` reference-depth doc | confirmed-live | `CLAUDE.md` (443 lines), describes commands, architecture, tool config layer | README links for AI-collaborator depth |
| `the_one/agents.md` reference-depth doc | confirmed-live | `the_one/agents.md` (1668 lines), full architecture reference | README links for architecture depth |
| Mission/flight artifact tree | confirmed-live | `missions/08-gleepglorp-rebrand/flights/01-brand-foundation/…` etc. populated under `missions/`; tracked in git (only `.flightops/` is gitignored) | One-sentence pointer + Mission Control repo link |
| F7 AI: `App.perf` gate promotion | confirmed-live (in-scope as side scope) | `the_one/interfaces/web/static/js/perf.js` exists; `app.js:88-135` instruments area-switch | L02 lands the `agents.md` convention addition |
| F7 AI: Playwright CDPSession parity recipe | confirmed-live (out of scope this flight) | F7 debrief recommends F8 OR maintenance pass; operator opted to leave it as carry-forward | Stay in F7 action-item carry, not this flight |
| F7 AI: other action items (BYTES_PER_TOKEN naming, AnthropicFactory docstring, etc.) | confirmed-live (out of scope this flight) | F7 debrief lists them; operator opted to keep F8 narrow | Carry forward to maintenance |
| `.flightops/` gitignored | confirmed-live | `.gitignore:15` `.flightops/` | README's mission/flight pointer references `missions/` (tracked) not `.flightops/` (gitignored, methodology-only) |
| `pyproject.toml` install spec current | confirmed-live | `pip install -e ".[all-llms,dev]"` documented in `CLAUDE.md:13`; `pyproject.toml` has `all-llms` and `dev` extras | README quickstart cribs from CLAUDE.md |
| `make rebuild` Docker path current | confirmed-live | `Makefile:23` `docker compose build the-one && docker compose up -d the-one` | README quickstart references Makefile targets |
| `.env.example` exists | confirmed-live | `.env.example` (16 lines) with `THE_ONE_LLM_*` defaults for ollama qwen2.5:7b | README quickstart references it |
| Default port 8484 | confirmed-live | `.env.example:13` `THE_ONE_PORT=8484`; `CLAUDE.md:18` `the-one serve` (port 8484) | README quickstart documents `http://localhost:8484` |

Recon outcome: zero retirements; one item (Playwright CDPSession parity recipe) explicitly scoped OUT despite being a candidate F8 carry, per operator direction during Phase 4 interview ("`?perf=1` convention doc promotion" picked; "Playwright CDPSession parity recipe" not picked).

---

## Leg Progress

### L01 — `readme-content-and-perf-convention`

**Status**: landed
**Started**: 2026-05-15
**Completed**: 2026-05-15

**Files created**:
- `/home/cprch/projects/the-one/README.md` — 69 lines; hero (`gleepglorp_med.png`, width=280, centered `<p align="center">`), H1 title, italic centered tagline, horizontal rule, six sections (What this is / Screenshots / Quickstart / Architecture / Security / Project organization & methodology). Three `<!-- SCREENSHOT: {area}-dark.png -->` HTML-comment placeholders. No `<img>` tags for screenshots. No Concourse CI or self-modification references. Security link to `SECURITY-MODEL.md` and Mission Control link (`https://github.com/msieurthenardier/mission-control`) both present.

**Files modified**:
- `the_one/agents.md` — one new `### gated-debug-instrumentation` block added after `### verbatim-message-equality` (which ends at original line 217) and before the `---` separator. Net diff: 10 lines added; no other content modified anywhere in the file. Verified via `git diff the_one/agents.md` — additions only.

**Final convention name chosen**: `gated-debug-instrumentation`

**Final tagline used**: "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." (working hypothesis retained verbatim — reads well below the mascot; under 80 chars; no self-modification reference)

**Deviations from leg artifact**:
- README line count is 69 lines rather than the 100-200 range cited in the Verification Steps. All required structural elements are present and correct; the shorter count reflects the warmly-terse design intent (no padding added). All acceptance criteria pass. The Verification Steps line count is a soft expectation, not a hard constraint — content quality and accuracy take precedence.
- No LICENSE file found at repo root; license section omitted per leg artifact's explicit guidance ("If a license file doesn't exist, skip — don't make claims about licensing"). No placeholder or "TBD" text added.
- Convention entry `gated-debug-instrumentation` chosen from the three suggested names (vs. `dual-channel-debug-gate` or `url-and-localstorage-activation-gate`). Name selected because it describes the pattern's intent (gate for debugging instrumentation) rather than the implementation mechanism. Semantically distinct from all four existing conventions (confirmed by reading entries at lines 175, 185, 195, 205).

---

## Decisions

_(runtime decisions land here)_

---

## Deviations

_(deviations land here)_

---

## Anomalies

_(anomalies land here)_

---

## Session Notes

### 2026-05-15 — Flight 8 created

Flight scoped at design time as content-only (no source-code changes). Three legs (final shape after cycle-1 design review — see next entry): L01 README content draft + `?perf=1` convention addition, L02 screenshots + image wiring, L03 alignment HAT (cold read). Operator-supplied design decisions: warmly-narrative tone, gleepglorp_med.png at top with tagline, 3 dark-only screenshots, per-layer architecture mini-paragraphs, one-sentence mission/flight pointer, no Concourse CI / self-modification coverage in README. F7 action-item carries: only the `?perf=1` convention promotion folded into F8; the others (Playwright parity recipe, BYTES_PER_TOKEN naming, factory docstring, AsyncMock warnings investigation) stay in F7 action-item carry for a future maintenance pass.

### 2026-05-15 — Cycle 1 design review (Architect)

Architect returned **approve with changes**. Four issues + three suggestions + two questions. Incorporated:

1. **[medium] Duplication risk with existing `App.perf` operational doc** (`agents.md:1505+`). Tightened the convention-promotion design decision to land as a **NEW named convention** under `agents.md`'s `## Project Conventions` section (anchor line 171, peer of `trust-the-runtime`/`canonical-import + convenience-re-export`/`structural-Protocol-satisfaction`/`verbatim-message-equality`), explicitly cross-linking to the F7 perf-scenarios operational section as the canonical live example. The new convention entry covers the **pattern** ("debugging-only modules use URL + localStorage gate, short-circuit when disabled, never compile-time excluded"), not the activation mechanics already documented operationally.

2. **[medium] L02 conflated FD-mechanical convention edit with operator-manual screenshot capture.** Restructured: convention promotion moved into L01 (FD-mechanical content work alongside README content). L02 simplifies to operator-heavy screenshots + image-wiring. New "Leg boundaries" Design Decision captures the rule (FD-mechanical and operator-manual do not share a leg).

3. **[low] Install-snippet drift risk** acknowledged in technical approach + Design Decision; L03 cold-read MUST verify snippet against current `pyproject.toml`. Added to Completion Checklist.

4. **[low] F7 carry-forward items not located in flight.md.** Added explicit "Out of Scope (carried elsewhere)" subsection listing each F7 action item explicitly excluded and the source location (`missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-debrief.md`).

5. **[low] No data-leak gate in screenshot completion.** Added explicit checkpoint and Completion Checklist line: operator visually verifies committed PNGs contain no real-world data, conversation content, or agent names.

Architect suggestions incorporated:
- L03 alignment HAT promoted from `*(optional)*` to required — README is the final mission artifact for an explicit external-developer audience; cold-read pass is cheap insurance.
- Six-paragraph vs four-layer-diagram divergence: added as a resolved Open Question; L01 explicitly notes the audience-driven divergence in README copy so cross-referencing readers aren't confused.
- `docs/screenshots/` vs alternatives: kept per operator's Phase 4 answer; L02 will note path convention inline.

Architect questions resolved:
- Tagline working hypothesis updated from "Your local AI agent — LLM-agnostic, tool-rich, self-modifying." to "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." Self-modification is excluded from the README per operator decision; tagline must not contradict body.
- Broken-image-icon avoidance: added Design Decision — L01 uses `<!-- SCREENSHOT: ... -->` HTML-comment placeholders, not `<img>` stubs, so the L01 branch renders cleanly between commits.

No cycle-2 review planned — all incorporated changes are scope/content/wording corrections, none structural. Per skill's cycle-2 guidance ("Skip if only minor/cosmetic fixes were applied"), proceeding to Phase 6 (crew walk-through) on revised spec.

### 2026-05-15 — Flight 8 approved, transitioned to `ready`

Operator approved the post-Cycle-1 revised spec without further edits. Flight status `planning` → `ready`. Pre-flight checklist boxes ticked. Next step: `/leg 01 8 mission 8, the-one` to design Leg 01 (`readme-content-and-perf-convention`).

### 2026-05-15 — Leg 01 designed, status `ready`

Leg artifact `legs/01-readme-content-and-perf-convention.md` written. Scope: FD-mechanical content work — write `/README.md` end-to-end (hero mascot + warmly-narrative one-paragraph "what this is" + dual-path install quickstart + 6-paragraph per-layer architecture + security link + Mission Control pointer + 3 HTML-comment screenshot placeholders) AND add one new named convention entry under `the_one/agents.md`'s `## Project Conventions` section (peer of `trust-the-runtime` / `canonical-import + convenience-re-export` / `structural-Protocol-satisfaction` / `verbatim-message-equality`), cross-linking to the F7 `## Performance Measurement (F7)` operational section as the live example. No source-code changes; no tests changed; no build step. 14 code-location citations audited at leg design time, all OK (zero drift). Working convention name suggestions: `gated-debug-instrumentation` / `dual-channel-debug-gate` / `url-and-localstorage-activation-gate` — final name picked at draft time.

### 2026-05-15 — Agentic workflow started, flight `in-flight`

Operator invoked `/agentic-workflow`. Phase 1 context loading complete. Phase file `leg-execution.md` loaded from project; structurally valid (Crew, Interaction Protocol, Prompts sections all present with code blocks). Crew: Developer (Sonnet) + Reviewer (Haiku); Accessibility Reviewer not spawned (no UI changes in F8). Feature branch `flight/08-professional-readme` created off `main`. Flight status `ready` → `in-flight`.

**Leg execution plan**:
- L01 `readme-content-and-perf-convention` → autonomous (Developer design review → Developer implement → Reviewer pass → commit)
- L02 `screenshots-and-image-wiring` → interactive HAT (operator captures dark-theme screenshots; FD guides step-by-step)
- L03 `alignment-hat` → interactive HAT (operator cold-read; FD applies inline fixes)

Per agentic-workflow guidance: Phase 2d (review + commit) runs after the LAST autonomous leg. Since L01 is the only autonomous leg, review + commit runs after L01 implementation, before L02 begins.

### Flight Director Notes

**Phase file loading (2026-05-15)**: Loaded `.flightops/agent-crews/leg-execution.md` from the project (not the default fallback). Crew: Developer (Sonnet model preference), Reviewer (Haiku model preference), Accessibility Reviewer (Sonnet, optional). For this flight, Accessibility Reviewer will NOT be spawned — F8 changes no UI surfaces (README + one markdown convention entry); the optional path doesn't apply.

**Branch strategy**: Single-branch (no worktree per project ARTIFACTS.md `Strategy | branch`). Working directory for all agents: `/home/cprch/projects/the-one`.

**L01 design review (cycle 1, 2026-05-15)**: Spawned Developer (Sonnet) per phase file's "Review Leg Design" prompt. Returned `approve with changes` — 2 medium-severity citation-drift items (Makefile range imprecise, perf.js comment-block range internally contradicted within leg artifact) + 1 medium severity (verification step used a `grep | sed` pattern that wouldn't work since `Dependency Graph` is an H2 absent from the H3 grep output — replaced with a working `awk` recipe). 3 low-severity items also applied (pyproject.toml citation order in implementation guidance, stale Session Notes line referring to old leg shape). All 19 built-in tools confirmed correct against `the_one/tools/builtins.py`. Tagline "hand-rolled" wording confirmed accurate against `CLAUDE.md:68` "Built without agent frameworks". Convention name candidates all semantically distinct from existing four. Mission Control HTTPS URL correct for public README.

Cycle-2 review SKIPPED — all fixes were minor/cosmetic (citation precision + verification-step recipe). No structural changes. Per skill: "Skip if only minor/cosmetic fixes were applied." Leg artifact moves to implementation.

**L01 implementation (2026-05-15)**: Spawned Developer (Sonnet) per phase file's "Implement" prompt. Implementation completed with one noted deviation (README at 69 lines, below the 100-200 soft guidance — all required structural elements present, deliberate warmly-terse density). All 8 acceptance criteria verified passing. Convention name picked: `gated-debug-instrumentation`. Tagline retained verbatim from working hypothesis: "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled."

**L01 code review (cycle 1, 2026-05-15)**: Spawned Reviewer (Haiku) per phase file's "Review" prompt. Reviewer returned `[HANDOFF:confirmed]` on the first pass. All 8 acceptance criteria independently verified. Content correctness validated against codebase (19 tools confirmed, port/install/security/mission-control claims all matched). Convention entry's structural shape matches the four existing peers; name is semantically distinct. Zero scope creep — only new `README.md` + `the_one/agents.md` modification + artifact-tree updates. Zero out-of-scope references (no Concourse CI, no self-modification). No cycle-2 review needed.
