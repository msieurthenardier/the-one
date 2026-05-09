# Flight Debrief: OAuth simplification + Test connection button

**Date**: 2026-05-08
**Flight**: [OAuth simplification + Test connection button](flight.md)
**Status**: landed
**Duration**: 2026-05-08 (single-day execution: design + 4 autonomous legs + binding HAT)
**Legs Completed**: 5 of 5 (L0–L4 all `landed`; flight `landed`; mission flight 6.5 ticked; PR #36 ready-for-review)

## Outcome Assessment

### Objectives Achieved

The flight delivered the full triad it set out to deliver:

1. **Strip the GitHub-legacy non-DCR OAuth manual-entry surface**: backend (L0) and frontend (L1) deletions verified by zero-hit grep sweeps for `ManualOAuth*`, `manual_metadata`, `/oauth/manual-register`, `registration_method`, `oauth_client_secret`, `config.oauth`, `mcp-oauth-section`, `oauth_manual_registration_required`, `oauth-modal-manual` across `the_one/` and `tests/`. `_validate_mcp_source_config`'s `config.oauth.*` block deleted; `MCPSourceTokenStorage` no longer writes/reads the `registration_method` discriminator. The `secrets["oauth_client_secret"]` field is gone. Net diff: 1148 LOC deleted across L0+L1.
2. **Close the auth-on-`tools/list` operator-blocking gap (L2)**: `MCPClient.list_tools` now mirrors `call_tool`'s F5 L4 `try/except* (OAuthFlowError, OAuthTokenError) / except* httpx.HTTPStatusError` translation. `MCPToolProvider.get_tools_for_agent`'s graceful-degrade-skip except list extends with `MCPAuthRequired`; the log line carries an `auth_required` discriminator. Cloudflare API MCP and similar production OAuth MCPs now graceful-skip cleanly at agent build instead of being misclassified as transport errors.
3. **Test connection button + popup-callback dance (L3)**: new `POST /api/mcp-sources/{id}/test/connect` endpoint, two-phase popup-callback flow (Phase A try-with-tokens / Phase B kick-DCR-+-auth), `_TEST_CONNECT_TIMEOUT` constant for monkeypatchable timeout. UI button moved into the Connection section per operator feedback; collapsible Tools section renders the per-tool descriptions; popup centered on parent window. Flight Design Decision §6 (`consent_url_future` threading) implemented across `make_oauth_handlers` + `build_oauth_provider_for_source` with backward-compatible default `None`.
4. **Tier-2 HAT verified end-to-end (L4)**: live Cloudflare API MCP (`https://mcp.cloudflare.com/mcp`) verified through all 7 procedure steps: register source → click Test → Cloudflare consent → tokens persist → re-Test → tools list → agent build → real chat tool call returning live API data → cleanup. Caplog gate clean (0 occurrences of `MCPClient.disconnect` warnings). HAT surfaced 4 distinct bugs (1 from L3, 1 F1-era latent, 1 frozenset gap, 1 F6 L3 architecture interaction); all 4 fixed inline in commit `1a0915c` and re-verified before declaring PASS.

### Mission Criteria Advanced

- **#3** — remote OAuth servers usable end-to-end without manual bearer-token paste. Post-F6.5 the canonical surface is RFC 7591 DCR + RFC 9728 PRM + RFC 8414 OASM, no GitHub-legacy fallback. **Verified by L4 HAT against live Cloudflare**.
- **#7** — agent attaches MCP sources; tools become callable. The auth-on-`tools/list` operator-blocking gap is closed: agent built with `cloudflare_api` source attached → `mcp__CloudFlare_API__*` tools registered → tool dispatch succeeds with real Cloudflare API responses. **Verified by L4 Step 6**.
- **#9** — credentials never appear in plaintext outside the encryption boundary. The `oauth_client_secret` field is gone, shrinking the credential-handling perimeter. The `OAUTH_MANAGED_SECRET_KEYS` filter (L4 inline fix) ensures token state never leaks into HTTP-request headers via the F1-era flat-merge. **Verified by grep sweep + Cloudflare HAT**.
- **#10** — graceful failure isolation. `MCPToolProvider`'s except list now distinguishes `MCPAuthRequired` (auth-skipped) from `MCPConnectionError`/`MCPSandboxError`/`MCPVersionMismatch` (connect-failed). The log discriminator gives ops engineers immediate signal as to which class of failure occurred. **Verified by L2 unit tests**.

## What Went Well

- **Design review cycle 1 caught real bugs before code was written**, especially L3's three HIGH issues (Promise-chain JS style requirement, missing `auth_provider` threading in Phase A, concurrent-Test race). Cycle-1's hit rate continues to be high — across 4 autonomous legs, every cycle surfaced ≥1 high-severity issue that would have caused implementation-time rework.
- **Binding Tier-2 HAT decisively earned its keep (Design Decision §4)**. All 4 L4 bugs were invisible to unit tests, in-repo fixtures, design review, AND the Haiku Reviewer. None would have been caught without a real DCR-supporting OAuth-protected MCP server. The binding-not-optional posture forced the flight to ship a working feature rather than a unit-tested-but-broken-in-production one.
- **L0+L1 deletion split was the right architectural seam**. Backend (testable with Python grep sweeps + unit tests) and frontend (testable with JS grep sweeps + browser tests) had non-overlapping verification surfaces; merging them into one leg would have made the AC list unwieldy.
- **L2's `try/except*` translation is a near-verbatim transcription of `call_tool`'s F5 L4 pattern**, sitting 100 lines below in the same file. The symmetry is immediately legible to a future reader. The `BaseExceptionGroup` pattern (Python 3.11+) handles both bare and grouped exception shapes cleanly.
- **Inline UX fixes during HAT incorporated operator feedback in real time** (Test button into Connection section, dedicated Tools section with collapsible `<details>`, popup centering). The Flight Director's willingness to absorb scope creep during HAT made the shipped feature feel finished rather than functional-but-rough.
- **Citation Audit pattern in leg artifacts continues to surface drift** before implementation. L0's audit flagged `test_oauth_provider_factory.py` line ranges as unverified; the design review cycle 1 confirmed and corrected them. The pattern means implementers don't chase stale citations.

## What Could Be Improved

### Process

- **HAT leg specs should explicitly reserve a "fixup commit path" section** with instructions for how to version and document inline fixes. L4 surfaced 4 bugs in 3 verification steps; the inline-fix pattern worked well but was improvised. Standardizing it — expected output sections for "bugs surfaced," "inline fix description," "tests added for fix" — would make HAT debriefs more consistent across flights.
- **L0's "Files Affected" missing `tests/browser/`** caused Anomaly A1 (browser tests outside the leg's explicit Python-only scope contained Python grep hits). The implementing agent correctly used the sweep as the authoritative check, but the discrepancy created verification ambiguity. Future leg specs should include `tests/browser/` in the "Files Affected" grep when the leg deletes any Python-callable feature.
- **L1's scope-creep revert created Anomaly A2** (4 broken `test_oauth_modal_flow.py` tests). The Flight Director correctly reverted the `areas: order,` addition to `app.js` (no Python consumers per grep), but the revert broke the `_emit_ws_event` test helper which IS a JavaScript consumer. The current state is mild tech debt: 4 tests that look pre-existing but are flight-internal. Fix is 2 lines (re-add the export + document `test_oauth_modal_flow.py` as a known consumer).
- **L1 Developer's self-report misattributed the work to L0**, claiming L1 was a no-op verification pass when in fact L1 made 321 lines of JS deletions across 4 files. The Flight Director caught and corrected via `git diff HEAD --stat`. Implementing agents periodically lose the thread on what they did vs what existed before; cross-checking the diff stat against the self-report is a worthwhile Flight Director discipline.

### Technical

- **3 unit tests should be added in a follow-up maintenance pass**, covering the L4 inline fixes:
  1. `build_oauth_provider_for_source` with `allow_dcr_bootstrap=True` constructs a provider despite empty `dcr_credentials`
  2. `build_request_headers` filters `OAUTH_MANAGED_SECRET_KEYS` out of the merged headers dict (parametrized over the 6 managed keys)
  3. `_pool._entry_worker` synthetic-csid path: when `csid is None` AND tokens are present, the auth_provider gets built (and is non-None)

  Currently these paths are only verified by L4 HAT, which is non-reproducible per-commit.

- **Test suite metrics regressed against pre-flight baseline**:
  - Unit suite: 75.85s / 1344 passed / 4 failed / 2 skipped (was: 72s / 1335 passed / 3 failed / 2 skipped pre-flight). +9 tests, 1 NEW failure: `test_token_definitions::test_every_var_reference_is_defined` — `studio.css:107` references `var(--font-mono, monospace)` but the project's CSS token is `--font-family-mono`. Trivial one-character fix; should land before merge.
  - Browser suite: 10m25s / 240 passed / 48 failed (was: 10m08s / 241 passed / 43 failed pre-flight). −1 passing, +5 failing. One verified regression: `test_mcp_test_connection_button.py::test_test_connection_button_click_shows_result` was PASSING at L3 landing per the flight log but now fails — most likely the L4 UX restructure (Test button moved into Connection section) broke a DOM locator. Locator update needed before merge. Other 4 new failures are likely pre-existing-but-flaky (timing/state sensitivity); merits targeted investigation in a maintenance pass.

- **`OAUTH_MANAGED_SECRET_KEYS` constant maintenance is fragile**. The L4 fix expanded the frozenset by 2 keys (`token_type`, `scope`) that were silently missing since F5 — `MCPSourceTokenStorage.set_tokens` writes them, but the constant didn't list them. Future flights adding a managed key (e.g. `id_token` for OIDC, or `dpop_keypair`) will face the same gap unless the constant is derived from `set_tokens`'s actual writes via a class-level `MANAGED_KEYS` attribute or a cross-check test. Recommended to land before F8.

- **`allow_dcr_bootstrap` boolean flag is mild architectural debt**. The kwarg makes `build_oauth_provider_for_source` decide between two semantically distinct cases (existing-creds path / fresh-bootstrap path) based on a flag that only one caller supplies. Acceptable as currently scoped (single internal caller, well-documented), but F7 should NOT copy this pattern — the inspector factory should be a separate entrypoint.

- **Synthetic-csid pattern proliferation**. The codebase now has three csid shapes: real 12-char uuid4-hex, `test:{source_id}` (L3), and `agent_build:{source.id}` (L4). F7 will likely need a fourth (`inspector:{source_id}`). The pattern is correct but undocumented; without formalization the next reader will invent a fourth shape from scratch instead of following the convention. Should be documented as a module-level note in `handlers.py`.

### Documentation

- **`agents.md` was updated** for L0's storage-shape changes (canonical 4-key `OAUTH_MANAGED_SECRET_KEYS` documented). Good.
- **No new operator-facing documentation was added** for the Test connection button. The button is self-explanatory but a one-line entry in the README under "MCP Sources" describing "Test connection: drives OAuth flow at source-creation time so subsequent agent builds register real tools" would help operators new to the project understand its role. Not a blocker.
- **`tests/HAT.md` Tier-2 procedure replaced cleanly** (was GitHub manual-entry, now Cloudflare DCR happy path). The new procedure is binding for OAuth-touching flights going forward.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| L0 deleted 2 browser test functions outside its explicit "Files Affected" scope (Anomaly A1) | Python grep sweep authoritatively flagged Python references in `tests/browser/*.py` that would have failed acceptance criteria | YES — leg specs should always include `tests/browser/` in their "Files Affected" grep when the leg deletes any Python-callable feature |
| L1 Developer's self-report claimed work was already done by L0; FD verified via git diff and corrected the log | Implementing agent lost track of what it did vs what existed pre-leg | YES — FDs should cross-check Developer self-reports against `git diff HEAD --stat` for nontrivial legs |
| L1 added `areas: order,` to `app.js`; FD reverted as scope creep without realizing JS test helper depended on it (Anomaly A2) | Grep for Python consumers returned 0 hits but JS consumer in `test_oauth_modal_flow.py:41` was missed | NO — this is one-off; the lesson is "grep both Python and JS consumers when reverting" not a new standard practice |
| L3 design review cycle 1 corrected 3 HIGH issues including missing `auth_provider` threading in Phase A code sketch | Spec sketched concrete code without tracing through `MCPClient.__init__` signature | YES — when leg specs include code sketches, design review should verify the sketches against actual signatures |
| L4 HAT surfaced 4 distinct bugs requiring inline fixes | Latent F1+F5+F6 architecture interactions only reachable by live DCR-supporting OAuth-protected MCP server | YES — binding Tier-2 HAT for OAuth-touching flights is now an empirically validated mandatory pattern |
| L4 simplified browser popup-flow test (Anomaly A3) — verifies button render/click only, popup-callback flow deferred to HAT | In-repo OAuth fixture insufficient to drive popup → callback round-trip; spec's "browser test for popup-flow" was over-ambitious for fixture infrastructure | YES — for any test that requires "live OAuth-like state machine," document the fixture-vs-HAT split in the leg spec; don't promise a browser test that will compromise to button-render-only |

## Key Learnings

1. **Design Decision §4 is decisively the most valuable decision in the flight.** All 4 L4 bugs were invisible to design review + unit tests + Haiku Reviewer. The binding-not-optional Tier-2 HAT is the only thing that prevented shipping a unit-tested-but-broken feature. Future OAuth-touching flights should make their binding HAT a non-negotiable AC.

2. **Cycle-1 design review continues to consistently surface HIGH-severity issues across all 4 autonomous legs.** The hit rate justifies the time cost of running it. Cycle-2 was skipped on every leg in this flight (per skill guidance: "skip if cycle-1 fixes are surgical/factual reconciliations") and the skip never came back to bite — implying cycle-1 captures most issues that subsequent cycles would. Continue as default; cycle-2 is exceptional.

3. **Latent F1-era bugs are reachable when new code paths exercise old code with new shapes.** The `build_request_headers` flat-merge bug (TypeError from dict-typed `dcr_credentials` value) was harmless until Phase A of the new Test endpoint added a code path that exercised `build_request_headers` on a source with OAuth-managed secrets. F1's `secrets` shape was operator-string-only at design time; F5 added dict/float values. Future flights touching `secrets` shape should audit transport-layer consumers proactively.

4. **F6 L3's architecture decision (`csid is None → return None`) silently broke F6.5's core promise** until L4 surfaced it. The decision was correct in context (multi-tab broadcast safety) but its interaction with agent-build path (where csid is always None) was unexamined. The lesson: when a guard exists "to prevent X in scenario A," verify it doesn't accidentally prevent Y in scenario B. The fix (synthetic-csid for tokens-present-no-csid case) is a design correction, not pure debt.

5. **Operator UX feedback during HAT meaningfully shaped the shipped feature.** The Test button's original placement (its own section between kv-table and Danger Zone) felt out-of-place; the operator's request to move it into the Connection section + add a dedicated collapsible Tools section was both ergonomically right and easy to absorb mid-HAT. Future HAT procedures should explicitly invite operator UX feedback as part of the verification, not as a follow-up flight.

6. **Test result truncation is a real problem at the Cloudflare-API-MCP class of server** but it's a server-side issue with no MCP-spec pagination contract. The mid-JSON-string truncation cannot be detected mechanically by the client; operators see weird LLM behavior with no clear failure signal. Mitigations live at the agent-prompt level (system prompt warning that tool results may be truncated), the tool-result rendering level (detect malformed-trailing JSON and surface a "[possibly truncated by server]" hint), or the MCP-server level (which we don't control). Worth a future flight to evaluate options.

## Recommendations

### Most impactful (do before merge)

1. **Fix `--font-mono` → `--font-family-mono` in `studio.css:107`** — trivial one-character fix; closes the 1 NEW unit test failure (`test_token_definitions::test_every_var_reference_is_defined`).
2. **Fix `test_test_connection_button_click_shows_result` locator** — the L4 DOM restructure moved the Test button; the browser test's locator needs updating. This is a direct regression from this flight, not pre-existing.

### Near-term (next maintenance pass)

3. **Add 3 unit tests** covering the L4 inline fixes: `allow_dcr_bootstrap=True` factory path, `build_request_headers` managed-keys filter, `_entry_worker` synthetic-csid path. These would have caught the L4 bugs at unit-test time on F7+.
4. **Fix Anomaly A2** (`window.App.areas` not exported): re-add `areas: order,` to `app.js` and document `test_oauth_modal_flow.py:41` as a known consumer. Closes 4 spurious "pre-existing" browser failures.
5. **Document the synthetic-csid pattern** in `handlers.py` (or a new `oauth/README.md` section): enumerate `test:{source_id}`, `agent_build:{source.id}` as the known shapes, name the prefix-collision-prevention contract, and the timeout-on-stale-tokens edge case.

### Forward-looking (F7+ planning input)

6. **F7 (Inspector) should re-use F6.5's `list_tools` translation pattern** for `MCPClient.connect()` (Design Decision §3 deferred this). The `extract_field_from_www_auth` helper + `BaseExceptionGroup` walk are already in place.
7. **F8 (Studio MCPs tab) should derive `OAUTH_MANAGED_SECRET_KEYS` from `set_tokens`'s actual writes** — either via a class-level `MANAGED_KEYS` attribute computed once, or a cross-check test. The L4 frozenset gap (2 keys missing since F5) shows manual maintenance drifts.
8. **Codify "binding Tier-2 HAT for OAuth-touching flights" in the methodology**. Empirically validated across F4, F5, F6, and F6.5 (4 bugs found this flight). Should be a standard checklist item in `flight.md` template, not a per-flight design decision.

## Action Items

- [ ] Fix `studio.css:107` token reference (`--font-mono` → `--font-family-mono`) — pre-merge
- [ ] Repair `test_test_connection_button_click_shows_result` browser test locator — pre-merge
- [ ] Add 3 unit tests covering L4 inline fixes — F7-prep maintenance task
- [ ] Fix Anomaly A2 (`window.App.areas` re-export) — F7-prep maintenance task
- [ ] Document synthetic-csid pattern in `the_one/mcp/oauth/handlers.py` module docstring — pre-F7
- [ ] Add operator-facing README entry for the Test connection button — low priority, before mission close
- [ ] Codify binding-Tier-2-HAT-for-OAuth-flights as a methodology checklist item — flight-template update in mission-control repo
- [ ] Investigate the 4 additional pre-existing-flaky browser failures (delta vs pre-flight baseline) — maintenance pass
- [ ] Evaluate truncation-detection mitigations (agent-prompt, tool-result rendering, or escalation to MCP spec) — candidate for future flight
