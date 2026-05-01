# Flight Debrief: Web Expansion & Constraints

**Date**: 2026-04-30
**Flight**: [Web Expansion & Constraints](flight.md)
**Status**: completed
**Duration**: 2026-04-29 (start of L0) → 2026-04-30 (post-Reviewer doc fix-up)
**Legs Completed**: 9 of 9 (7 autonomous + 1 HAT + 1 integration verification)

## Outcome Assessment

### Objectives Achieved

The flight delivered the full F5 surface as designed:

- **`WebConfig`** — 7 fields (timeout pair with cross-field validator, response-size cap, redirect cap tool-level-only, host_allowlist + denylist, extra_allowed_hosts), all annotated with the right resolver markers per F2's contract.
- **Migrated tools** — `HttpRequestTool` and `WebSearchTool` migrated to F5 surface. Four-clause try/except envelope on web tools (`ConstraintError → (asyncio.TimeoutError, httpx.TimeoutException) → httpx.TooManyRedirects → Exception`) — a deliberate F4-pattern extension because httpx's `TimeoutException` does not inherit from `asyncio.TimeoutError`.
- **New tools** — `FetchUrlTool` (readability + markdownify pipeline; content-type dispatch) and `DownloadFileTool` (cross-Config on `FilesystemConfig`; streaming write with mid-stream cap abort and partial-file cleanup). 19 tools total (was 17).
- **SSRF protection on by default** — custom `httpx.AsyncHTTPTransport` resolves hostnames, blocks loopback / RFC1918 / link-local / cloud-metadata IPs, and connects to the resolved IP while preserving SNI via `request.extensions["sni_hostname"]`. IP literals also covered (HAT-discovered fix). DNS-rebind regression test patches `asyncio.base_events.BaseEventLoop.getaddrinfo`.
- **`SearchBackend` Protocol + `DDGSearchBackend`** — closes the F1 known issue via a Chrome-on-Linux User-Agent that bypasses DDG's anti-bot interstitial. Backend wired via `cross_configs[SearchBackend]` injection (F6 admin will surface the picker).
- **L0 unification** — F3 + F4 filesystem-scope helpers collapsed under a `CheckMode` enum dispatcher; existing names preserved as shims.
- **Documentation refreshed** — `agents.md`, `CLAUDE.md`, `mission.md` reflect the F5 surface.

### Mission Criteria Advanced

| Criterion | Status |
|---|---|
| Web tooling supports raw HTTP, reader-mode page retrieval, file download, and pluggable search; SSRF default-block with curated opt-out | ✓ shipped |
| URL/host scope + redirect cap + response-size cap as the third per-category constraint enforcement | ✓ shipped |
| Automated coverage for happy-path + every constraint type (path-scope, size cap, timeout cap, **SSRF**, binary refusals) | ✓ +157 net new tests |

## What Went Well

**Architect-review-per-leg paid off again.** Five high-severity catches at design time (three at L1, one at L2, one at L3) plus one at HAT (L7 IP-literal SSRF bypass) plus four doc-drift items at post-Reviewer. The L1 catches were all in one class — **library-API drift from training-cutoff knowledge**: SNI preservation via `request.extensions["sni_hostname"]` (not `Host:` header alone), `asyncio.get_running_loop()` (not deprecated `get_event_loop()`), `Narrow` (not `NarrowSuperset`) for the allowlist marker semantic. The pattern is now visible enough to prescribe — see Recommendations.

**L0 unification was the right call**, executed cleanly. Folding the F4-deferred maintenance into F5 added a 7th call site (`download_file`) and removed the temptation to write a 5th near-duplicate helper. F3 + F4 test suites passed unchanged. The shim pattern preserved 11 existing call sites without churn.

**Stub-tool consumer test in L1** (per F4 debrief recommendation) **caught real issues at the right time**. Without it, L2 would have been the first integration of `WebConfig` + `_url_check` + `SSRFGuardedTransport` + `_truncate_response`. L2's architect-corrected timeout-exception clause confirms integration-time is the wrong place to discover envelope mismatches. The F4 recommendation is paying off; codify it as a methodology default for any leg defining helpers without immediate consumers.

**HAT scope was more sophisticated than F4's**. The 9 operator-driven scenarios + DNS-rebind moved to L1 unit test (acknowledging it can't be exercised operator-driven) struck the right balance. Scenario 6 (agent-narrowed `extra_allowed_hosts` over operator's allowlist) validated the `Narrow` semantic end-to-end at the user-facing layer, not just at the resolver. Scenario 9 (slow `download_file` rejoin) confirmed F4's WebSocket fixes hold for web tools — useful regression check for cross-flight invariants.

**`_safe_unlink` defensive helper** (`the_one/tools/web.py:20-37`) — implementer-caught insight at L4 that the spec didn't anticipate: `target.open("wb")` creates the file BEFORE `client.stream()` begins, so unexpected errors (timeout, redirect-cap overrun, mid-stream RuntimeError) leave an empty or partial file behind. Module-level helper called from each error clause. Pattern worth canonizing for any future tool that creates an artifact before a streaming operation.

**Auto-reload (F4 follow-up `a41789a`) eliminated the F4 uvicorn-cache anomaly class** for F5. No HAT scenario required `docker compose restart` — every source edit propagated automatically.

## What Could Be Improved

### Process

**HAT rubric was not threat-vector-explicit.** The IP-literal SSRF bypass surfaced in HAT scenario 3 because the rubric tested cloud-metadata SSRF as a generic "violation" but didn't enumerate the threat-vector classes (DNS-rebind / IP-literal / hostname-resolves-blocked / extra_allowed_hosts override / operator-override-uniformity). Each of these is a distinct policy gate; defaulting to "assert error envelope shape" caught the bug, but a more explicit rubric would have caught the bypass at L1 design or test time. **Recommendation**: HAT scope for security-bearing surfaces must enumerate per-threat-vector scenarios.

**L8 doc-drift is a recurring class.** F4's L8 had similar fix-ups; F5 had four (WebConfig field shape, `DownloadFileTool` mode, `WebSearchTool` backend injection path, `DDGSearchBackend` SSRF claim). The drift happens because the L8 doc author works from the *spec* rather than the *as-built code*, and the spec drifts from implementation as architect catches accrue. **Recommendation**: doc-refresh leg should either (a) run AFTER the Reviewer pass so as-built code is the source of truth, or (b) generate doc claims from runtime introspection (e.g., `WebConfig.model_fields` produces the field table directly).

**Leg-spec library-API drift** — five catches in L1+L2+L3 were all in this class. The leg-design template doesn't currently include "verify third-party library APIs against installed-version docs." **Recommendation**: add a leg-design checklist item — for each third-party library touched, document the version and the API shape verified.

### Technical

**`cross_configs` widening to `dict[type, object]`** — F4's `dict[type[BaseModel], BaseModel]` was strict about frozen Pydantic; F5's Protocol-keyed `SearchBackend` injection required widening to `dict[type, object]`. The frozen invariant has bifurcated:
- **Pydantic-keyed entries** (`FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig`, `WebConfig`) — frozen.
- **Protocol-keyed entries** (`SearchBackend`) — stateful but per-`get_tools()`-call-scoped.

Acceptable: the per-call lifecycle replaces frozenness as the safety mechanism. **But the original L1b decision (F4) underspecified the long-term need.** Future typed-dispatch decisions should pre-declare the two categories. **Recommendation**: when introducing a typed dispatch slot, ask "will all values be frozen forever, or might per-call-fresh services arrive?"

**httpx-touching tools need a four-clause envelope** (vs F4's three-clause filesystem pattern). `httpx.TimeoutException` does NOT inherit from `asyncio.TimeoutError`. A future flight using httpx that copies F4's three-clause template will silently let httpx timeouts fall through to the generic `Exception` clause. **Recommendation**: document in `CLAUDE.md`'s tool authorship contract — "if the tool calls httpx, use the four-clause shape with the grouped `(asyncio.TimeoutError, httpx.TimeoutException)` clause."

**Unverified IPv6 IP-literal SSRF**: the L7 inline fix added regression tests for IPv4 IP literals (loopback / RFC1918 / cloud-metadata) but no IPv6 IP-literal test (e.g., `http://[::1]/`). The hostname-resolution path's IPv6 coverage is in `_is_ssrf_blocked` tests; the IP-literal short-circuit branch may not match `[::1]`-bracketed URL parsing. **Recommendation**: add an IPv6 regression test in a follow-up maintenance pass.

### Documentation

**Wikipedia 403 with default httpx UA** (HAT scenario 7). Operator-discoverable via `WebConfig.default_user_agent` Substitute knob — wait, F5 didn't actually ship that field. Operators set the User-Agent via `headers` parameter on each call, OR via `tool_configs` JSON if `WebConfig` had such a field (it doesn't). The flight log notes this as L8 forward-reference; should be promoted to mission Known Issues.

**`_build_transport` test seam pattern** (3-tool duplication) is intentional (per-tool test isolation) but not documented anywhere as a deliberate idiom. Future web-tool authors might be tempted to refactor it. **Recommendation**: add an "Explicit patterns" section to `agents.md` covering the test-seam idiom + the four-clause envelope + the snapshot-under-lock pattern from F4.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| `_truncate_output` extended to insert `[stderr]` marker (F4 retroactive) | F1 contract; helper-as-single-source-of-truth | (already standardized in F4 L3) |
| `cross_configs` widened from `dict[type[BaseModel], BaseModel]` to `dict[type, object]` | F4's L1b underspecified the long-term need | Yes — pre-declare the two-category split |
| `_safe_unlink` defensive cleanup helper | L4 implementer caught that `target.open("wb")` creates the file before streaming | Yes — leg-design checklist: "for tools that create artifacts before streaming, plan cleanup explicitly" |
| Four-clause try/except on httpx tools | `httpx.TimeoutException` not in `asyncio.TimeoutError` MRO | Yes — document in tool authorship contract |
| L4 mode refined `WRITE_NEW` → `WRITE_EXISTING_PARENT` | "Agent has explicit `mkdir` tool" mission stance | (already documented in L4 spec) |
| `extra_allowed_hosts` marker `NarrowSuperset` → `Narrow` | Allowlist-vs-denylist semantic | Yes — document marker-vs-list-semantic mapping |
| L8 doc drift fixed inline post-Reviewer | Doc author worked from spec, not as-built code | Yes — see Recommendations: doc-refresh ordering |
| HAT rubric extended to enumerate threat vectors (post-IP-literal-bypass insight) | Generic "happy + violation" rubric missed a class | Yes — see Recommendations: HAT rubric for security surfaces |

## Key Learnings

**Architect-review-per-leg has a sustained ~50% catch rate on leg specs.** Three at L1, one at L2, one at L3. Most catches are library-API drift (5 of 5). This is high but sustainable for security-bearing surfaces; the concern is leg-spec drafting becoming over-reliant on architect review as a safety net. Track the catch rate trend across F6+; if it stays >40% on non-security flights, leg-spec authoring needs an explicit "what could go wrong" section before architect review.

**HAT scope must explicitly enumerate threat-vector classes** for security-bearing surfaces. Generic "happy + violation" rubrics catch the obvious bug class but miss subclasses (here: IP-literal). The L7 HAT caught the IP-literal bypass by luck of URL choice, not by design.

**Doc-refresh after Reviewer, not before.** The L8 doc author working from spec rather than as-built code is the recurring class across F4 + F5. Either: (a) run doc-refresh AFTER Reviewer pass, OR (b) generate doc claims from runtime introspection. F6's larger doc surface (admin section) makes this worth fixing methodologically before it becomes a debt.

**Cross-Config widening lessons generalize**. Pre-declaring "Pydantic Configs are frozen; Protocol-keyed services are per-call-fresh" up front would have avoided the F5 widening exercise. When MCP integration arrives in a future mission, the same shape (operator-set Configs vs per-call-fresh service connections) will recur. Document the two-category split now in `agents.md` so the MCP flight inherits the pattern.

**Scaffolding-leg consumer test (F4 debrief recommendation) continues to pay off**. L1's `_StubWebTool` caught the L2 envelope-clause discovery surface that would have been a runtime issue. Methodology default candidate.

## Recommendations

1. **HAT scope rubric for security-bearing surfaces** — add to the `/flight` skill prompt: when the flight introduces or modifies a security boundary, the HAT rubric MUST enumerate per-threat-vector scenarios (e.g., for SSRF: DNS-rebind / IP-literal / hostname-resolves-blocked / extra_allowed_hosts override / agent-narrowing-uniformity). Generic "happy + violation" pairs are insufficient.

2. **Doc-refresh leg ordering** — change the methodology default: doc-refresh leg runs AFTER the Reviewer pass. Or: doc-refresh extracts canonical claims via runtime introspection (`WebConfig.model_fields` directly produces the field-list table). F6's admin section makes this urgent — admin doc surface is larger.

3. **Tool authorship contract section in `CLAUDE.md`** — codify: three-clause envelope (filesystem) vs four-clause envelope (httpx-touching), float-preserving timeout clip, two-phase lock-and-await, frozen Pydantic Configs vs per-call-fresh services for cross_configs, scaffolding-leg consumer-test requirement, library-API-version verification in leg specs, `_build_transport` test-seam idiom, `_safe_unlink` cleanup-before-streaming pattern.

4. **Library-API drift checklist in leg-design template** — for each third-party library touched, document the installed version and verify API shape against current docs (not training-cutoff knowledge). 5 of 5 high-severity L1-L3 catches were in this class.

5. **Promote Wikipedia 403 to mission Known Issues** — currently in L7 flight log + L8 forward-reference only. Operator-discoverable via headers parameter, but the agent surface error (`[403] ...user-agent...`) is opaque without the workaround being documented. Also consider adding a `default_user_agent` field to `WebConfig` (Substitute marker) in a future flight or maintenance pass.

## Action Items

- [ ] Update `/flight` skill prompt with security-bearing-surface HAT rubric requirement.
- [ ] Update `/leg` skill prompt: doc-refresh leg runs AFTER Reviewer.
- [ ] Update `/leg` skill prompt: library-API-version checklist item for any leg touching third-party libs.
- [ ] Add Tool Authorship Contract section to `CLAUDE.md` (project-specific) consolidating F2-F5 patterns.
- [ ] Promote Wikipedia 403 to mission Known Issues; consider `default_user_agent` field addition.
- [ ] Add IPv6 IP-literal SSRF regression test (loopback `[::1]`) in routine maintenance.
- [ ] (Optional, methodology-level) Track architect-catch rate across F6+ flights; revisit leg-spec authoring guidance if rate stays >40% on non-security flights.
