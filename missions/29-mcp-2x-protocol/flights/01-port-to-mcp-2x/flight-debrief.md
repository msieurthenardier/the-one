# Flight Debrief: Port to the mcp 2.x SDK at parity

**Date**: 2026-10-12
**Flight**: [Port to the mcp 2.x SDK at parity](flight.md)
**Status**: completed (landed and merged to main as `06e1e39`, PR #275)
**Duration**: 2026-10-11 (squawk attempt → sortie → mission planning) - 2026-10-12 (landed, merged)
**Legs Completed**: 3 of 3 (`sdk-port`, `packaging-and-doctor`, `hat`)
**Plugin version**: mission-control 1.2.0

## Outcome Assessment

### Objectives Achieved
The MCP client, OAuth sign-in, self-configuration loopback server and MCP test fixtures moved from `mcp==1.28.1` to `mcp==2.3.0` at parity. Every server still connects on the initialize handshake.

The four accepted behaviour changes each fail with a plain error (DD8, DD12):
- a 1 MiB SSE event cap;
- same-origin redirects only;
- authorization-server issuer validation;
- no self-heal on a stateless server's 404.

What this flight delivered:
- **Sign-in detection was redesigned.** 2.x swallows HTTP 401, so DD1 uses a response hook plus a sequenced per-session record. It was proven against real HTTP fixtures: 26 tests.
- **RFC 9207 `iss` flows through the OAuth callback.** Proven live: Cloudflare's callback carried `iss=https://mcp.cloudflare.com` and sign-in succeeded.
- **Self-configuration refusals keep their one-line text** under `MCPServer`, as dual-typed `ToolError`s.
- **The Windows packaged build carries the new closure.** A twelfth doctor gate, `mcp sdk`, proved it in a real frozen build on the Concourse Windows worker.
- **One fix from the HAT:** the MCP editor's OAuth consent wait went from 15 s to 2 minutes.

All servers still show "protocol 2025-11-25". That is by design: Flight 2 adds automatic negotiation of 2026-07-28.

### Mission Criteria Advanced
| Mission criterion | This flight |
|---|---|
| 2026-07-28 server connects on it, editor shows it | **Groundwork only.** The SDK that speaks it is in place, and the Sonos server works on it at the handshake era. Flight 2 delivers this criterion. |
| Older-revision servers still connect over stdio and HTTP | **Parity half met.** The full unit and browser suites are green and the Sonos server works. The "no noticeable added delay after first connect" half belongs to Flight 2, since only negotiation adds the delay. |
| OAuth sign-in still works end to end, including RFC 9207 | **Met for sign-in**, live against Cloudflare plus real-fixture tests. The "tools run afterwards" part was accepted as covered by tests, not run live (HAT V4, operator's call). Flight 2's Cloudflare re-run should include a live tool run. |
| Self-configuration tools work, refusals read as one line | **Met.** Refusal assertions are unchanged and the parity audit found nothing else that reaches the client. |
| Plain errors for no shared revision / input-required / oversized event | **Partly.** The oversized event is met (DD8). No shared revision and input-required belong to Flight 2. |
| Windows packaged build builds and doctor passes | **Met** (HAT V1). Caveat: the gate doesn't yet prove `httpcore2` (see Technical). |
| Unit and browser suites pass; changed expectations listed | **Met.** Unit 6068/12/0; browser `rc=0 lanes=9 failed=-`. Every changed expectation is listed in the flight log. |

## What Went Well
- **The escalation gates did their job.** The squawk gate rejected an "upgrade the SDK" fix once the target turned out to be a breaking 2.x. The sortie gate re-check then surfaced the second cluster (sign-in detection, RFC 9207, the dual HTTP stack). The work was re-homed as a mission before any code existed. The operator found the gating useful, not friction.
- **Reconnaissance from extracted wheels, read as text, before any design.** One read-only interrogation of the 2.3.0, `mcp-types` and `httpx2` sources found most of what would break, with citations. Both Architect cycles then spot-checked it instead of re-deriving it.
- **The design reviews caught real defects before code.**
  - Cycle 1 caught DD1's wrong record scope, the wrong DD8 error surface, and three unacknowledged forced behaviour changes.
  - Cycle 2 caught DD1's misfire after a mid-operation sign-in, which led to the last-status rule.
  - The leg review caught three `api.httpx.AsyncClient` patch sites that would have silently stopped intercepting, plus under-specified fixture work.

  None of these reached implementation.
- **Real-fixture testing over injected exceptions.** The prior A8/A9 tests injected `HTTPStatusError` and would have passed against broken code. The new sign-in tests run real 401s, real OAuth flows and real redirects.
- **Real `mcp.types` models instead of `MagicMock`s** exposed wire-shape changes the mocks hid: `extensions` and `tasks` in capabilities, and `_meta` vs `meta`.
- **A HAT against a real OAuth server found what tests could not.** The 15 s consent ceiling failed on a real human, as prior missions' HATs have found something every time.
- **The atomic leg with internal checkpoints worked.** Servers first restored app import early, and the five checkpoints gave the Developer a clean progression through a roughly 30-file change.
- **The worktree isolation held.** Main's unrelated WIP was never touched across the whole flight.

## What Could Be Improved

### Process
- **The worktree venv drifted on creation.** `uv pip install -e ".[all-llms,dev]"` resolved fresh and pulled `openai` 3.29.0 where the lock has 2.32.0. That produced 5 spurious baseline failures and cost a rebuild. Any flight that creates a venv should sync from the lock: `uv export --frozen … | uv pip sync`, then `uv pip install --no-deps -e .`.
- **Consumers of pinned lists were found late.**
  - `scripts/windows_test_copy.py::NEEDLES`, which mirrors the CI needle list, was found only when the unit suite failed.
  - `tests/test_imports.py`'s layering pin forced an unplanned leaf module.

  A pre-design grep for "mirrors of this list" and "import-graph pins" would have caught both.
- **Stale numbers in the leg.** "The `requires_bwrap` set (12 tests)" came from `CLAUDE.md`, but the marker set is now 41 tests plus 3 skips. The leg trusted a doc number instead of measuring.
- **HAT V3 (stale tokens) and V4 (live Cloudflare tool run) were not run live.** Both were accepted as covered by tests. V3 is exactly the behaviour the flight changed (see Technical), so it is the one most worth seeing live.
- **The commit agent's report was blocked by auto mode as "Self-Modification"** because the commit touched `CLAUDE.md`. The change was legitimate operator-manual content the leg required. The Flight Director inspected the diff before pushing.

### Technical
- **The stale-token behaviour changed and should be revisited.** With DD1, a timeout whose last MCP-POST response was a 401 reads as `MCPAuthRequired`. So Test connection with revoked tokens skips `api.py`'s `looks_like_token_failure` branch and keeps the stale OAuth secrets until a new sign-in replaces them. The operator still gets a fresh consent URL, but an abandoned sign-in leaves stale secrets that every later Test hits first.
- **The doctor gate does not prove `httpcore2`.**
  - `_probe_mcp_sdk` imports `mcp`, `mcp.types.version` and the surface, but `httpx2` imports `httpcore2` lazily at `AsyncClient()` construction.
  - Combined with the spec's `on_error="warn"`, a frozen build missing `httpcore2` would pass doctor and fail on the first remote MCP connection.
  - Fix: construct and close an `httpx2.AsyncClient()` in the gate.
- **DD1's translation is three near-copies.** `connect`, `list_tools` and `call_tool` each carry an ordered ladder: record, SSE cap, session-terminated, generic. Flight 2 adds a −32022 arm to `connect`. A single `_translate_failure(...)` helper would stop the copies drifting apart.
- **`list_tools`/`call_tool` now translate `CancelledError`.** A real outer cancellation, such as an agent turn cancelled while a sign-in is pending, can become `MCPAuthRequired` when the last response was a 401. Consider gating on `asyncio.current_task().cancelling() == 0`.
- **DD6 is only partly era-agnostic.** `connect` still reads `_meta` from the `InitializeResult`. Under negotiation that result is absent, so `_meta` would silently become `None`.
- **DD8 matches SDK message text** ("SSE stream failed:", "byte limit"). It is pinned by a tripwire, but it is a second SDK-text dependency to re-check on every SDK bump.
- **Smells in `_signin_record.py`.** The transport writes the private `_AUTH_RECORDS` directly, and the module also owns `MAX_SSE_EVENT_BYTES`. A `register_auth_record()` function and a neutral module name would tidy this.
- **Debt carried, not introduced:**
  - anyio cross-task cancel-scope noise at `asyncio.run()` shutdown for a connect that fails outside the pool (Mission 07 F06/F08, unresolved);
  - `AsyncMockMixin._execute_mock_call` "never awaited" RuntimeWarnings in unit output (squawk 0027's family).

### Documentation
- Stale after the port:
  - `the_one/mcp/__init__.py`'s docstring still says "mcp==1.27.0";
  - `_probe_auth_posture`'s docstring still says "a bare `httpx` POST";
  - `CLAUDE.md` still says the `requires_bwrap` set is "12 tests".
- `the_one/agents.md` would benefit from a short dual-HTTP-stack rule: which side uses `httpx` and which `httpx2`, plus the patch-target gotcha that `api.httpx.AsyncClient` patches stop intercepting `api.httpx2` drivers.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| Squawk → sortie → mission escalation before any code | Each gate surfaced a real decision cluster: the SDK was a breaking 2.x, then sign-in detection and RFC 9207 formed a second cluster | Yes, as practice: the gates worked |
| Sortie number collided with a sortie 03 merged meanwhile | Main moved during planning; resolved by escalating to a mission | Rebase the planning worktree and re-check sequence numbers before persisting |
| 14-day dependency soak waived by the operator at flight start | Operator decision; DD10 rewritten, original framing kept inline, mission constraints struck through | No; the waiver was case-specific |
| `sdk-port` split, DD11 moved to a new `packaging-and-doctor` leg | The leg design review's single-pass feasibility finding | Yes: split out work that doesn't depend on import health |
| New leaf module `the_one/mcp/_signin_record.py` | Importing the transport from the client broke the `test_imports` layering pin | Yes: the leaf-module pattern for shared state across layers |
| AC8 adapted (revoked token plus dead refresh token instead of a literal refresh failure) | The SDK never refreshes stored tokens at startup in 1.x or 2.x | No |
| HAT fix: consent wait 15 s → 2 min | A real Cloudflare sign-in outlasted the UI ceiling; Flight Director's call: fix, not feature | — |
| HAT V3/V4 accepted as test-covered | Operator's call | No: run V3 live when the flight changed that behaviour |
| Worktree venv rebuilt from the lock | A fresh resolve drifted `openai` | Yes: always sync a new venv from `uv.lock` |

## Key Learnings
- **When an SDK swallows a transport signal, recover it on the client the-one owns.** Use a response hook, a weak-keyed per-session record and a per-operation "last status since baseline" rule, not exception walking. The rule survived redirects, a successful mid-operation sign-in, stale 401s, and, per the Architect's analysis, a discover-then-initialize fallback unchanged.
- **Mocks of SDK result types hide wire-shape breaks.** Build test results from the SDK's real models.
- **A dual HTTP stack needs a guard and a patch-target rule.** `httpx` stays importable, so a leftover `except httpx.*` or a `patch("…api.httpx.AsyncClient")` fails silently, not loudly.
- **A frozen-build gate proves only what it imports.** Lazy imports, such as `httpx2` → `httpcore2`, need to be exercised: construct the object.
- **Test metrics:**
  - Unit: **6068 passed / 12 skipped / 0 failed, 194.7 s.** Against the sortie 03 debrief (6019 / 12 / 194.8 s) that is +49 tests with time flat. The new tests are `test_mcp_signin_detection.py` 26, `test_mcp_wire_shapes.py` 13, `test_mcp_httpx_guard.py` 5, the stale-tokens test 1, callback/timeouts +2 each, doctor +2, net of the removed A9 test.
  - Browser: **`PARALLEL_RESULT rc=0 total=1055s lanes=9 failed=-`**, against sortie 03's 1023 s (+3%, host variance; the flight added no browser tests). Per lane against budget:

    | Lane | Seconds / budget |
    |---|---|
    | routing | 521/600 |
    | **agents** | **508/510** |
    | chats | 351/360 |
    | mcp | 315/360 |
    | providers | 293/300 |
    | shared | 291/300 |
    | contracts | 261/270 |
    | settings | 263/300 |
    | library | 256/300 |

    **Five of nine lanes are within 10% of budget, and `agents` has 2 s of headroom.** Sortie 03's re-budget recommendation is still open.
  - No flakes. The `requires_bwrap` set is 41 passed / 3 skipped.

## Methodology Observations
- **Sortie skill, Plan → re-check gate (1.2.0).** The sortie's qualification passed on the charter. Code interrogation then found a second decision cluster: the security-sensitive sign-in redesign forced by the SDK. The skill's re-check gate fired correctly and the work escalated to a mission. Cost: one extra planning pass (mission interview plus Architect validation) and re-homing the artifacts. That was correct behaviour, recorded as working as designed. The operator found the gating fine.
- **Sortie skill, Plan step 3 (1.2.0).** Sequence numbers were assigned against a planning worktree based on a main that had since moved, and another session merged a sortie 03 in the meantime. The collision only surfaced when main was re-fetched. Cost: a rename. The escalation absorbed it, but a non-escalating sortie would have had to renumber. Expected: re-fetch the default branch and re-scan sequence numbers just before persisting a new numbered artifact.
- **Agentic-workflow skill, Phase 1/2a (1.2.0).** Neither the skill nor the crew file mentions creating or syncing a venv when a flight runs in a fresh worktree. Here the Flight Director's fresh resolve produced 5 spurious baseline failures. Cost: one rebuild plus a re-run. Expected: a worktree-strategy note to build the environment from the lock before taking the baseline.
- **Agentic-workflow skill, Phase 2d commit (1.2.0).** The crew file has a Developer commit. Under auto mode, the commit agent's hand-back was flagged "Self-Modification" because the diff touched `CLAUDE.md`, the project's operator manual, which the leg was required to update. Cost: a Flight Director inspection of the diff before push, with no rework. Recorded so a sweep can see whether doc-touching commits by agents repeatedly trip this.
- **Flight skill, Phase 5b (1.2.0).** Two Architect cycles were the maximum, and cycle 2 still produced a high-severity finding (the last-status rule), which the Flight Director applied without a third review. It worked here because the fix was well specified by the reviewer. Recorded as a data point on whether two cycles suffice for security-sensitive flights.
- **Flight and leg skills (1.2.0).** Numbers copied from project docs into acceptance criteria ("`requires_bwrap` 12 tests") were stale. The leg design review did not catch it, and the Developer reported the discrepancy. Low cost.

## Recommendations
1. **Fold the Flight 1 follow-ups that touch Flight 2's surface into Flight 2's design.** These are:
   - make DD6 fully era-agnostic (`_meta` from `initialize_result or discover_result`, with the serverInfo de-dup);
   - extend the `mcp sdk` doctor gate to construct an `httpx2.AsyncClient`, which proves `httpcore2`;
   - consolidate DD1's translation ladder into one helper before adding the −32022 arm;
   - decide the timeout-versus-401 stale-token behaviour;
   - gate `CancelledError` translation on real outer cancellation.
2. **For Flight 2's negotiation design**, per the Architect:
   - re-implement the negotiation policy from the public `send_discover`, `initialize` and `adopt` (or wrap the private `negotiate_auto` behind one seam with a tripwire);
   - cache the negotiated era per source, since the 10 s discover timeout otherwise breaks the "under 1 s" criterion for silently-dropping legacy servers;
   - make `_probe_auth_posture` tolerate modern-only servers;
   - gate on HANDSHAKE+MODERN, split `_PINNED_PROTOCOL_VERSION`, and add legacy-only stdio and HTTP fixtures;
   - in its HAT, run V3 (stale tokens) and a live Cloudflare tool run.
3. **Re-budget the `agents` browser lane** (508/510 s) from a fresh measurement before any flight adds agent-editor browser tests. It is carried from sortie 03.
4. **Standardize venv creation in worktree flights:** sync from `uv.lock`, never a fresh resolve.
5. **Fix the stale docs** listed above.

## Action Items
- [ ] Flight 2 planning: carry Recommendations 1 and 2 into its design decisions.
- [x] Squawk **0199** logged: stale MCP docs (the `mcp/__init__.py` docstring, the `_probe_auth_posture` docstring, `CLAUDE.md`'s `requires_bwrap` count) plus the dual-HTTP-stack rule for `agents.md`.
- [ ] Re-budget the `agents` lane. The operator chose not to log it as a squawk, so it stays Recommendation 3 (carried from sortie 03).
- [x] Squawk 0198 logged and deferred during the flight (`make verify-serving` checks a moved file).
- [x] Dual-HTTP-stack rule for `the_one/agents.md`: folded into squawk 0199.
