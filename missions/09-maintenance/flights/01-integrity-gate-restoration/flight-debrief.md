# Flight Debrief: Code Hygiene + Concourse Removal

**Date**: 2026-05-16
**Flight**: [Code Hygiene + Concourse Removal](flight.md)
**Status**: landed
**Duration**: 2026-05-15 (single calendar day; planning + 4 design-review cycles + 4 implementation cycles + 1 flight review + 1 flight-close commit)
**Legs Completed**: 4 of 4 (1 added mid-flight per operator pivot)

## Outcome Assessment

### Objectives Achieved

Every contributing success criterion is checked. Concretely:

- **Ruff zero-baseline restored** (69 lint errors → 0; 81 reformat-candidate files → 0). Production-side hits at `agent/core.py:98`, `interfaces/web/api.py:660`, `mcp/_tool_provider.py:38`, `mcp/client.py:263` all resolved; the `api.py:660` E402 received an inline `# noqa` with a documented reason (10-line forward-reference-avoidance comment block).
- **Test infrastructure hardening**: `asgi-lifespan` installed in host venv; `make doctor` host-side drift-detection target added; `_can_unshare_user_namespace()` sibling probe added to `tests/test_mcp_sandbox_integration.py:200-229` so `test_sandbox_eperm_on_unshare_raises_mcp_sandbox_error_msg3` correctly SKIPs on WSL2 / unprivileged-Linux hosts (Case B) rather than failing.
- **Security one-liners landed**: `_safe_script_json` in `the_one/interfaces/web/api.py:1625-1648` closes the OAuth callback `</script>` + `<!--` + U+2028 + U+2029 injection across all three `post_message=` flow sites (`:1868, :1891, :1943`). `_clean_npx` allowlist (`mcp/cache_cleanup.py:71-83`) rejects `../etc/passwd` and 10 other attack-shape inputs using the npm package-name spec `^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$` — chosen at design review after the original draft `[A-Za-z0-9._@/-]` was found NON-functional (every character in that string is individually allowed, so `../etc/passwd` passes the draft regex).
- **`pip-audit` adopted** as a `make audit` host-side target (`.venv/bin/pip-audit --skip-editable || true`) — non-blocking by design.
- **M08 doc carry-forwards closed**: `agents.md` `## Provider type extension checklist` includes `_init_provider_state` hook entry; `agents.md` `## Project Conventions` codifies the `### live-read-across-lazy-resolver-boundary` pattern; `.env.example` documents `THE_ONE_DEV_MODE`; `SECURITY-MODEL.md` Future Work names the MCP `streamable-http` URL gating asymmetry; OpenRouter `_APP_NAME = "GleepGlorp AI"` (URL retained per repo-name-unchanged constraint).
- **Concourse + self-modification framing removed** (Leg 4, added mid-flight): `ci/` directory deleted (-160 lines); `THE_ONE_CONCOURSE_PASS` removed from `.env` (gitignored); `CLAUDE.md:56` parenthetical revised; `SECURITY-MODEL.md` 3 sites edited (bullet removed, `ci/pipeline.yml` enumeration item removed, "Secrets Manager" Future Work generalized); `mission-control/projects.md` description rewritten locally (file gitignored); `maintenance/2026-05-15.md` annotated with `## Note: Post-Report Pivot (2026-05-15)` header section. `README.md`, `the_one/agents.md`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `.env.example` verified clean during recon — no edits needed.

### Mission Criteria Advanced

All 17 of Flight 1's contributing criteria checked (3 explicitly DROPPED per pivot, 14 satisfied with commit refs). Mission 09 Flight 1 checkbox checked in mission.md.

## What Went Well

**Per-leg design-review discipline is the methodology's highest-ROI control — validated for the second consecutive flight.** Every one of the four legs went through a design-review pass before implementation. Severity counts: Leg 1 (3 high + 4 med + 2 low), Leg 2 (4 high + 4 med + 3 low), Leg 3 (**1 critical** + 2 high + 6 med + 2 low), Leg 4 (2 high + 4 med + 4 low). The Leg 3 CRITICAL save — catching that the original `_clean_npx` allowlist `[A-Za-z0-9._@/-]` did NOT block `../etc/passwd` — would have shipped a non-functional security fix had per-leg design review been skipped. This is the clearest single-flight data point yet that the protocol is correctly calibrated: design-review concretization forces test-vector thinking that flight-level design at the "allowlist for npm package names" abstraction cannot.

**Mid-flight pivot was absorbed cleanly.** The Leg 1 `fly` auth blocker triggered an operator-led reconsideration of whether Concourse was still serving its original purpose. The pivot decision (remove Concourse + self-improvement framing entirely; add Leg 4 to absorb the work) was reached in conversation, captured in flight-log Flight Director Notes, propagated to mission outcome paragraph + flight contributing-criteria + each pre-pivot leg spec, and executed without scope explosion. Flight grew from 3 legs (~1.5-2 days estimate) to 4 legs (~2.5-3.5 days revised); actual execution completed in a single calendar day. The decisive factor was that the pivot decision rested on a sound architectural question ("is this infrastructure still serving its purpose?"), not on a tactical blocker — once the question was asked, the answer was clear.

**Net architectural direction: simplification.** This flight is a REDUCTION mission: -160 source lines (Leg 4 alone), -1 secret rotation surface, -1 cognitive framing thread ("self-modifying agent + Concourse CI + rollback"), -2 cross-system trust boundaries, -3 stale `SECURITY-MODEL.md` anchors, -9 maintenance-report findings retired wholesale. The operator no longer has to track 8 categories of cognitive overhead (Concourse upgrade cadence, password rotation cadence, auto-rollback selftest, CI build I/O waste, git-revision binding, AIAT gating, pip-audit-in-CI question, lint+format gate-evasion). The lint+format zero-baseline restoration in Leg 1 is the one piece of value that survived the pivot — and notably, it survived because code hygiene is independent of CI substrate. **Structural decoupling lesson**: don't bundle "run tests" with "enforce tests via pipeline X."

**Test metrics held cleanly through the flight.** Broad pytest landed at 1700 passed (host + container, identical counts) with zero failures and zero new flakes. The +21 test delta from F7 close is exactly accounted for by Leg 3's additions: 2 `TestSafeScriptJSON` + 8 accept-list `_clean_npx` parametrize + 11 reject-list parametrize = 21. No silent test creep. Wall-clock unchanged from F7 baseline (95s container, 103s host).

**Reconnaissance Report pattern proved its value.** The Phase 1b recon at the top of the flight log (14 items, all `confirmed-live`) anchored every subsequent design review against current-state evidence. When line numbers drifted post-Leg-1 format pass (api.py +2 lines, cache_cleanup.py -2 lines), the design reviews caught the drift and rewrote location refs from numeric to symbol-based. Without the recon, those drifts would have surfaced as implementation-time confusion.

**Leg 3 commit split (security/CI vs docs) preserved per-class revert hygiene.** Two commits `e092eb9` (security + CI) + `daf24e2` (docs) keep each class's blast radius proportional to its risk profile. A future "revert the pip-audit step" wouldn't pull back the OpenRouter rebrand strings with it. Worth adopting as a default pattern for any leg that bundles security one-liners with documentation carry-forwards.

**Code-quality observations were uniformly positive.** Commit messages narrative and trailer-tagged (`Mission: 09 / Flight: 01`); helper docstrings explain *why* each escape pattern is required (not just *what* it does); `_VALID_NPX_PKG_RE` carries an extended comment block documenting *why* the looser draft was wrong (so future maintainers won't be tempted to "simplify" it); section headers in `Makefile` make the host-vs-container asymmetry legible inline.

## What Could Be Improved

### Process

- **Pre-flight prerequisites should be runtime probes, not checkboxes.** The flight's pre-flight prerequisites listed `fly -t local status` as a checkbox — nobody ran it during pre-flight design. The Leg 1 design-review Developer caught the auth gap; had this run at flight design, the pivot conversation could have happened on day -1 rather than mid-Leg-1. Update the flight template's Pre-Flight section to distinguish "static assumption (verified at design)" from "runtime probe (verified at flight start)" — probes must be EXECUTED during pre-flight, not just listed.
- **Mission-design Architect missed the pivot signal.** The maintenance report's Cat-8 findings included C7 ("password drift between `.env` and server") as a current-state issue — diagnostic evidence that nobody had run the pipeline recently. The signal was there; the Architect (at flight design) did not connect "infrastructure has drifted from purpose" with "should this infrastructure still exist?" Going forward, mission-design and flight-design should include a pre-flight question: **"Is each piece of work in this flight still serving its original purpose? Or has the underlying infrastructure/concept drifted since the work was scoped?"**
- **Mid-flight pivots are NORMAL for maintenance missions, not rare exceptions.** A maintenance mission inspects scope; scope decisions get questioned during execution; "remove X" becomes a new option that wasn't on the table at mission-design time. The methodology should treat mid-flight pivots as a NORMAL outcome for maintenance missions, with a templated pivot-annotation pattern (original framing preserved as commentary; new framing as live spec; durable record in flight log Flight Director Notes).
- **Line-number drift from format-pass legs needs explicit accounting.** Leg 2 and Leg 3 specs both had stale line numbers caused by Leg 1's `ruff format` pass. Future flights that include a format-pass leg should explicitly enumerate "all downstream legs must locate by symbol, not line number" as a precondition in the flight spec itself, not rely on per-leg design reviews to catch it.

### Technical

- **`make doctor` sub-shell `python` resolution gotcha** (NEW debt this flight). From Leg 3 anomaly notes: `make doctor` invoked from a sub-shell that lacks bare `python` on `$PATH` (only `python3` + `.venv/bin/python` present) exits non-zero. Works fine in operator's interactive shell. The target's `python -c ...` is sub-shell-sensitive. Recommended fix: `.venv/bin/python -c ...` instead of `python -c ...`, matching the pattern of `make audit`'s `.venv/bin/pip-audit`. Low impact, ~1-min fix, bundles into M10's first Makefile-touching leg.
- **Documentation accuracy bug in `agents.md` live-read convention** (NEW debt this flight). The new `### live-read-across-lazy-resolver-boundary` entry at `the_one/agents.md:229-238` cites `test_max_context_tokens_live_read_across_resolver` in `tests/test_agent_core.py` — *neither name nor file exists*. The actual F6.5 L04 / F7 L05 regression test is `test_usage_event_reflects_live_max_context_tokens_at_emission` in `tests/test_process_and_broadcast_live_read.py`. 2-line correction needed. Bundle into M10's first agents.md-touching leg.
- **Browser/pixel test suite blocked by missing Chromium in container.** `docker exec the-one pytest -m browser tests/browser/` produces 312 ERRORS at setup — `/root/.cache/ms-playwright/chromium_headless_shell-1208/` is absent. NOT a regression introduced by F1; this is the recurring "`make rebuild` wipes Playwright Chromium" foot-gun called out in F5/F6/F6.5/F7 debriefs and now F1 too. **Pre-requisite for M09 F2 (Accessibility) kickoff** — restore via `docker exec the-one playwright install chromium` before F2 design begins. Consider adding a `make rebuild-browsers` target that combines `make rebuild` + `playwright install chromium` so this stops recurring.
- **Pre-existing 2-test working-tree delta unresolved.** Leg 3 reported broad pytest at 1702; Legs 1/2/4 + flight reviewer + this debrief all observed 1700. The Leg 4 stash-revert experiment proved the 2-test delta is pre-existing in the working tree, not caused by Leg 4. Root cause never identified; not reproduced in this debrief run. M10 awareness only — don't chase unless it recurs.
- **`pip-audit` surfaced 6 CVEs** — 4 in `pip` 24.0 (installer infrastructure, NOT in `pyproject.toml` `dependencies`), 2 in `urllib3` 2.6.3 (transitive of `requests`/`cachecontrol`, only pulled in by dev-only `pip-audit`/`pytest-base-url`). Neither lands on a runtime dep; no divert triggered. Captured for M10 awareness.
- **Replacement enforcement substrate for lint/format gate is undefined.** With Concourse gone, the M06 lint+format zero-baseline restoration in Leg 1 has no automated enforcement gate. Pre-commit hooks, GitHub Actions migration, or "operator runs `make lint format test` before push" are all viable but none are codified. Open architectural question deferred to M10.
- **Two pre-existing pytest warnings persist** (not new this flight): `test_provider_api::test_ollama_models` `AsyncMock` coroutine-never-awaited (F6.5 carry); `.pytest_cache` permission denied (root-owned cache from container-exec, prior maintenance 7.3 carry). Both unchanged.

### Documentation

- **Host-side `make doctor` / `make audit` convention not codified.** The deliberate asymmetry with container-first `make lint`/`make format`/`make test` is documented only by a single section-header comment in the Makefile. Should be codified as a peer to `### gated-debug-instrumentation` and `### live-read-across-lazy-resolver-boundary` in `the_one/agents.md ## Project Conventions`. Pattern name suggestion: `### host-side-bench-drift-detection`. Contract: targets whose purpose is to detect drift between the operator's bench and the canonical container should run on host, must surface clean diagnostic on failure, must be invoked manually (not on every dev iteration).
- **npm-spec regex pattern as a security primitive not documented.** Worth a sentence in `SECURITY-MODEL.md` or `agents.md`: "operator-supplied identifiers that flow into filesystem paths or subprocess argv must be validated against a spec-grounded allowlist regex, not a permissive character class — see `_VALID_NPX_PKG_RE` for the exemplar."
- **LSEP/PSEP source-byte avoidance not documented.** The Leg 3 implementation anomaly (raw U+2028/U+2029 bytes accidentally embedded by an Edit pass that "looked right") deserves a one-line note in agents.md or a pre-commit hook check. Shape: `git grep -lP "[\x{2028}\x{2029}]" -- 'the_one/*.py' 'tests/*.py'` should return empty. ~5 min as a new `make audit-bytes` target.
- **`make audit` non-blocking contract is implicit only.** The `|| true` shape is intentional but a future maintainer could reasonably ask "why doesn't `make audit` fail on findings?" Add a one-line comment above the target: `# Non-blocking by design — findings print for awareness; runtime-dep severity triggers manual investigation per leg-spec divert criteria`.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Concourse removal added as new Leg 4 mid-flight | Leg 1 `fly` auth blocker triggered operator reconsideration of whether Concourse was serving its original purpose; answer was no. Removal absorbed into this maintenance flight rather than a separate M10 mission. | Yes — codify "mid-flight pivot pattern" for maintenance missions: original framing preserved as commentary, new framing as live spec, durable record in FD Notes |
| Leg 3 split into 2 commits (security/CI + docs) instead of 1 | Per-class revert hygiene — bundling 8 unrelated files in one commit means a revert-for-one-regression pulls back everything | Yes — adopt as default for legs that bundle security one-liners with documentation carry-forwards |
| `mission-control/projects.md` treated as local-only edit (gitignored) | Mid-implementation discovery: `projects.md` is in mission-control's `.gitignore`. Leg 4 spec assumed it was tracked. Operator clarified file is intentionally local-only. | No — project-specific. Future cross-repo legs should re-verify gitignore status during recon. |
| `.env` edit was local-only (no commit) | `.env` is gitignored per project convention (and per `.env.example`'s coexistence pattern). Removing `THE_ONE_CONCOURSE_PASS` from `.env` is a local-state change, not a tracked-file change. | No — already standard practice |
| Maintenance report annotated (header note) rather than rewritten | Inspection-record integrity: the maintenance report is the snapshot at inspection time, not a living plan. Rewriting findings would muddle the historical record and erase the supersession trail. | Yes — codify "maintenance reports are append-only at the header; when findings are superseded by a subsequent mission, annotate at the report header with a 'Post-Report Pivot' section linking to the resolution." |
| Leg 1 slug retained (`01-lint-format-restoration-and-gate-audit`) after dropping the gate-audit half | Re-slugging mid-flight would have invalidated the branch name, the leg-spec file path, and several artifact backlinks. Cost is a minor archaeological footnote; benefit is no broken refs. | Yes — slugs are immutable post-creation; annotate scope changes inline instead of renaming |
| Skipped second design-review cycle on each leg (per-skill rule) | Each design review's fixes were corrective (not substantive new design) — per skill's "Skip if only minor/cosmetic fixes were applied" guidance | Yes — already standard; reaffirmed |

## Key Learnings

### Technical

1. **`[A-Za-z0-9._@/-]` is NOT an allowlist for paths.** Every character in that class is permitted individually, so `../etc/passwd` passes the regex. Spec-grounded allowlists (npm package-name spec, RFC-grounded URL schemes, etc.) are the correct shape. The CRITICAL design-review save in Leg 3 establishes this concretely.

2. **Source files must NOT carry raw U+2028 / U+2029 characters.** Both terminate JavaScript statements when literal in source. Use Python escape sequences `" "` / `" "`. The Leg 3 anomaly (first `_safe_script_json` Edit pass accidentally embedded raw bytes; caught by byte-level grep) establishes this as a real foot-gun, not a theoretical one.

3. **Host-side drift detection is a distinct architectural concern from container-first tooling.** `make doctor` (probes host venv for declared dev extras) and `make audit` (runs pip-audit on host venv) deliberately diverge from `make lint`/`make format`/`make test` (which run via `docker exec`). The asymmetry catches developer-environment drift that container-first tooling cannot.

4. **OAuth callback `<script>` bodies need 4 escape patterns** to be safe against IdP-supplied content: `</` (script termination), `<!--` (HTML comment start), ` ` (LSEP), ` ` (PSEP). Three is the common case; four covers the JS-parser-statement-terminator edge cases that conservative scanners miss.

5. **Code hygiene is independent of CI substrate.** Removing Concourse didn't invalidate the lint+format zero-baseline restoration — it just removed the automated enforcement. The cleanup work survived as standalone code hygiene. Don't bundle "run tests" with "enforce tests via pipeline X" — they're separable concerns with different audiences.

### Process

1. **Pre-flight prerequisites that are runtime probes must be EXECUTED at pre-flight time, not just listed.** A checkbox is not a probe. The Leg 1 auth gap would have surfaced at flight-design time had `fly -t local status` been executed during pre-flight verification rather than treated as a checkbox.

2. **Per-leg design reviews catch bugs that implementation alone cannot.** Implementation runs against a spec; a wrong spec produces correctly-implemented wrong code. Design-review discipline is the differential between "we shipped a regex that allows `../etc/passwd`" and "we caught it before any code was written." Lock this in as non-skippable even for "trivial security one-liners."

3. **Mid-flight pivots are NORMAL for maintenance missions.** Maintenance scope decisions get questioned during execution because the act of inspecting scope surfaces options that weren't visible at mission-design time. The methodology should support clean pivots with a templated annotation pattern.

4. **Maintenance reports' findings can be wholesale-retired by subsequent missions.** When the underlying infrastructure goes away, the findings about it dissolve. Annotate at the report header (append-only); don't rewrite findings in place.

5. **Reconnaissance reports are the recon-time evidence baseline.** Every cited scope item should be categorized as `confirmed-live` / `already-satisfied` / `drifted` / `retired` with evidence + recommendation. This flight's recon (14/14 `confirmed-live`) anchored every subsequent design review against current-state truth.

### Domain

1. **Concourse drifted from being a tool the agent uses to being maybe-CI-someday infrastructure.** The drift was diagnostic evidence (password-server mismatch in `.env`) — but nobody connected the diagnostic to the architectural question until it forced its way to attention. Other infrastructure in the project may be drifting similarly: the `concourse-local` repo (now stranded), the `THE_ONE_DEV_MODE` env gate, the Playwright browser-test infrastructure (5 module-skipped tests since M08). M10 should explicitly audit "maybe-someday" infrastructure.

2. **The npm-spec package-name regex is reusable.** Future call paths that take operator-supplied identifiers into filesystem operations should use the same pattern. Lift to `agents.md` Project Conventions as a security primitive.

## Recommendations

1. **Restore Chromium in the dev container before M09 F2 kickoff.** `docker exec the-one playwright install chromium`. F2 (Accessibility) requires functional browser tests. Recurring foot-gun — consider a `make rebuild-browsers` target that combines `make rebuild` + `playwright install chromium`. **Blocking on M09 F2.**

2. **Fix the `agents.md` live-read entry's test-name + file-path citation.** Change `test_max_context_tokens_live_read_across_resolver` → `test_usage_event_reflects_live_max_context_tokens_at_emission` and `tests/test_agent_core.py` → `tests/test_process_and_broadcast_live_read.py`. NEW debt introduced by F1; 2-line correction; bundle with M10's first agents.md-touching leg.

3. **Codify the host-side drift-detection convention** in `the_one/agents.md ## Project Conventions` as a peer of `### gated-debug-instrumentation`. Suggested name: `### host-side-bench-drift-detection`. ~10 min.

4. **Fix `make doctor` sub-shell `python` resolution.** Change `python -c ...` → `.venv/bin/python -c ...` to match `make audit`'s `.venv/bin/pip-audit` shape. Removes the sub-shell foot-gun. ~1 min.

5. **Add `make audit-bytes` target** for the raw U+2028/U+2029 source-byte avoidance check. Shape: `git grep -lP "[\x{2028}\x{2029}]" -- 'the_one/*.py' 'tests/*.py'` should return empty. Catches the Leg 3 implementation anomaly class going forward. ~5 min.

6. **Document the npm-spec regex as a reusable security primitive** in `SECURITY-MODEL.md` or `agents.md`. Reference `_VALID_NPX_PKG_RE` as the exemplar. ~5 min.

7. **Update flight template's Pre-Flight section** to distinguish "static assumption (verified at design)" from "runtime probe (verified at flight start)." Skill-level methodology change; bundle with `/flight` skill update if the mission-debrief proposes it.

8. **Methodology**: codify "mid-flight pivot pattern" for maintenance missions in the `flight-debrief` and `mission-debrief` skill prompts. The pattern that worked here: original framing preserved as commentary, new framing as live spec, durable record in FD Notes Track, maintenance-report header annotation rather than body rewrite.

9. **Methodology**: codify per-leg design review as non-skippable even for trivial security one-liners. The Leg 3 broken-allowlist save is a strong data point.

10. **M10 maintenance audit** should include a "maybe-someday infrastructure" question for: `concourse-local` repo (stranded), `THE_ONE_DEV_MODE` env gate (vestigial?), Playwright browser-test infrastructure (5 module-skipped tests since M08), encrypted-credentials-at-rest rotation/migration story.

## Action Items

### High priority (blocking M09 F2 or imminent)

- [ ] **Restore Chromium in container**: `docker exec the-one playwright install chromium` — before M09 F2 kickoff
- [ ] **Add `make rebuild-browsers` target** combining `make rebuild` + `playwright install chromium` so the recurring foot-gun stops recurring (called out in F5/F6/F6.5/F7/F1 debriefs)

### Medium priority (bundle into M10's first opportunistic agents.md / Makefile leg)

- [ ] Fix `agents.md` live-read entry citation (2-line correction)
- [ ] Codify `### host-side-bench-drift-detection` convention in `agents.md ## Project Conventions`
- [ ] Fix `make doctor` sub-shell `python` resolution (`.venv/bin/python -c`)
- [ ] Add `make audit-bytes` target for LSEP/PSEP byte-level check
- [ ] Document npm-spec regex as a security primitive
- [ ] Add `# Non-blocking by design` comment above `make audit` target

### Low priority (informational / methodology)

- [ ] Carry forward 2-test pytest delta to M10 awareness; don't chase unless it recurs
- [ ] Carry forward 6 pip-audit CVEs (pip + urllib3, dev-only) to M10 awareness
- [ ] M10 maintenance audit: include "maybe-someday infrastructure" question for `concourse-local`, `THE_ONE_DEV_MODE`, Playwright infra, encrypted-credentials rotation story

### Methodology improvements (for mission-debrief consumption)

- [ ] Update `/flight` skill: distinguish "static assumption" from "runtime probe" in Pre-Flight section; runtime probes must be EXECUTED at pre-flight time
- [ ] Update `/flight-debrief` and `/mission-debrief` skill prompts: codify "mid-flight pivot pattern" for maintenance missions
- [ ] Update `/routine-maintenance` skill prompts: include a "is this infrastructure still serving its original purpose?" question in the Inspector's framing
- [ ] Lock in per-leg cycle-1 design reviews as non-skippable even for "trivial" legs — Leg 3 broken-allowlist save establishes the precedent
