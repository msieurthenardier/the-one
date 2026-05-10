# Leg: 02-stdio-mcp-create-and-test

**Status**: completed
**Flight**: [Alignment — MCPs working well end-to-end](../flight.md)

## Objective

Vibe-code-walk the operator workflow for creating and testing a stdio MCP source from scratch in the Studio MCP Servers area, against the in-repo FastMCP fixture (per F9 §3 default). Surface and fix any bugs, UX gaps, or polish issues inline. Verify that the F1/F3/F4/F8/F9-L1 surfaces (create form, sandbox config, idle-TTL behavior, env-var KV table, capability flags one-liner, collapsible input schemas, `__MASKED__` round-trip, trash icon, toggle switch, info icon polish) feel good end-to-end on the stdio path.

## Context

- **Flight Design Decision §1** — multi-leg vibe-coding, this leg is L2 (stdio create+test analog of L1's HTTP create+test).
- **Flight Design Decision §2** — fix-inline default; Sizing Thresholds table governs LOC bars per anomaly type.
- **Flight Design Decision §3** — in-repo Python FastMCP fixture (`tests/fixtures/mcp/hello_server.py`) as L2 default. L4/L6 may switch to a real third-party stdio MCP (e.g., `npx @modelcontextprotocol/server-everything`) or operator-stack stdio MCP if L2 surfaces a strong reason to broaden the surface.
- **Flight Design Decision §4** — done-criteria is operator-felt + caplog gate (HAT-only, F6 baseline pattern: 0 `MCPClient.disconnect` warnings across this leg's exercises). Stdio caplog measurement is the **first stdio-path re-assertion since F6** per the leg artifact's Design Decision §4 note — anomalies here are high-signal.
- **Flight Design Decision §5** — F8 carve-outs default to defer. The `_pool.py` test isolation issue (Anomaly A1) is in this category — if it surfaces during stdio vibing, document and continue.
- **Flight Design Decision §7** — inline fixes touching `MCPClient` lifecycle, `_open_*_transport_stack`, OAuth flows, pool worker spawn-path, `MCPToolProvider`, resolver, or `errors.py` get a ≤5-min architect pass before implementation. Adding stdio Test connection support touches MCPClient lifecycle → architect pass required at leg start.
- **Flight Design Decision §8** — single bundled fresh-context Sonnet review at flight close; this leg's inline-fix LOC contributes to the L8 review queue, no per-leg review.
- **Flight Design Decision §9** — all code-change work delegated to subagents. Parent context = vibing + triage only.
- **L1 outcome carry-forward**: operator-felt sign-off on the streamable-http create+test workflow with 7 anomaly classes resolved inline. F8 A6 (no-auth HTTP MCP detection) was absorbed via Shape C — the same `_probe_auth_posture` pattern is **not applicable to stdio** (no HTTP probe surface; stdio's "auth posture" is degenerate — no auth concept). L2 inherits no Shape-C-like work.
- **Methodology insight from L1's flight log** (logged for L8 mission-close): exploratory vibing surfaces operator-felt polish issues more effectively than scripted scenarios. L2 follows the exploratory framing as primary mode; the scenario list below is **coverage check / fallback**, not a strict script.

## L2 Design Choice — Cloudflare-state-equivalent for stdio

For stdio there's no fresh-DCR / leftover-state choice (no OAuth state). The equivalent design choice is **which targets to vibe against**. Post-Deliverable-2 (generic-runtime container), L2 has access to ANY pip-resolvable or npm-resolvable MCP via `uvx` / `npx` / `pipx run`. Recommended canonical targets to vibe both the in-repo path AND the generic-runtime path:

- **Primary (in-repo, hermetic)**: FastMCP fixture at `tests/fixtures/mcp/hello_server.py`. Already-bundled; no install step. Stdio invocation: `python -m tests.fixtures.mcp.hello_server --stdio`. Validates the stdio Test workflow on the fixture path.
- **Secondary (real-world, runtime install)**: `mcp-server-time` via `uvx`. Stdio invocation: `command=uvx args=[mcp-server-time]`. First spawn fetches via `uv` cache (~5-15s); subsequent spawns are fast. Validates the generic-runtime container model end-to-end. Pure compute; no network needed beyond the install fetch; minimal sandbox-permission complexity.
- **Tertiary (operator-stack, optional)**: anything operator wants — `npx -y @playwright/mcp` for browser automation (would need `npx playwright install` first to fetch browsers; significant setup), `npx -y @modelcontextprotocol/server-everything` for broad reference surface, or operator's own stdio MCP. Optional per leg's appetite.

L2 leaves the registered stdio source(s) in place at leg close — handed off to L4 (stdio attach) and L6 (stdio in chat) to inherit. At minimum the FastMCP fixture source; recommended also the `mcp-server-time` source for L4's "real-world MCP attach" coverage.

## Structural prerequisite — three coordinated deliverables

L2 cannot vibe its stated outcome ("create + test stdio MCPs") under the current code state. Three coordinated deliverables ship as the prerequisite leg before operator vibing begins:

### Deliverable 1 — Add stdio Test connection support

**The current state**: Refresh connection button is **streamable-http only**. Verified at:
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:205 — "source.type === 'streamable-http'"` (button-render gate)
- `the_one/interfaces/web/api.py:1048 — "if source.type != \"streamable-http\""` (endpoint early-return)
- `tests/browser/test_mcp_test_connection_button.py:84-98` — test asserting button absence for stdio

**The gap**: stdio sources cannot be tested from the source-edit page; tools-list discovery only happens at agent-attach time (L4). This breaks L2's stated outcome and is a soft Mission Criterion #6 gap ("each MCP source's Settings detail page lets the operator verify the connection lifecycle…").

**The fix shape** (architect pass required per §7; spawn at leg start):
- Backend: ungate `test_mcp_connection` for stdio. Build a transient `MCPClient` with stdio transport (sandbox-spawn → initialize → list_tools → teardown), persist tools cache to `source.config["_cache"]` (mirroring HTTP path), return same `{status:"ok", tools, capabilities}` shape. Stdio doesn't have OAuth, so no Phase 0 / Phase B / `auth_posture` decisions — it's effectively the no-auth path equivalent.
- Frontend: ungate `mcp-server-editor.js:205` to render the Refresh button for stdio too. The post-test render path is shared; capability flags + collapsible schemas should automatically apply to stdio on the same code path.
- Test isolation: per `tests/conftest.py::pytest_configure`, only `THE_ONE_TEST_MODE=1` is auto-set; `THE_ONE_SANDBOX_DISABLED=1` is set ONLY by the Playwright browser-test CI workflow (per the docstring in `the_one/mcp/transports/stdio.py:241-249`). For non-browser unit tests of the stdio Test path, the test file MUST explicitly `monkeypatch.setenv("THE_ONE_SANDBOX_DISABLED", "1")` OR run under bwrap (which works in the dev container per F3 §10). Architect pass + implementer brief should call this out so tests don't silently hit the bwrap path when they meant to bypass.
- Anyio risk per §7: stdio teardown is the F4 cleanup-deadlock surface (F6.6 fixed worst of these). The architect pass must verify the transient-client teardown path doesn't reintroduce disconnect-noise in caplog.

**Sizing**: ~110-175 LOC (backend ~50-80, frontend ~5-15, tests ~50-80).

### Deliverable 2 — Generic-runtime container (`pipx`/`uv`/`node`/`npm`)

**The model**: instead of pre-baking specific MCP packages into the image, the container hosts the package-manager runtimes (`pipx`/`uv` for Python, `node`/`npm`/`npx` for JS). Operator's `command + args` is self-describing and self-installing on first spawn. Subsequent spawns hit the cache. Container stays generic; operators bring their own MCPs by declaring them.

**Concretely**:
- Operator registers `command=uvx args=[mcp-server-time]` → first Refresh runs `uvx`, which fetches `mcp-server-time` into a managed cache, then runs it. Subsequent Refreshes hit cache → instant spawn.
- Operator registers `command=npx args=[-y, @playwright/mcp]` → first Refresh runs `npx`, fetches `@playwright/mcp` into npm cache, runs it. (Playwright browsers are a separate one-time `npx playwright install` setup if the operator wants browser automation; the npm package itself fetches without browsers.)
- For pure-Python operator-stack MCPs that prefer pip → `command=pipx args=[run, mcp-server-time]` works equivalently.

**The fix shape** (cache paths + image growth verified empirically by the L2 design-review architect via live container probe):
- `Dockerfile`: add `nodejs npm` to the apt install line (~250 MB); add `pip install pipx uv` to the project's pip-install layer (`uv` ~60 MB single binary; `pipx` ~10 MB Python package). **Total image growth: ~320 MB.**
- `docker-compose.yml`: mount **named Docker volumes** (NOT bind-mounts — bind-mounts recreate the F8 UID-drift papercut since the container runs as root and the operator's host user typically isn't) for runtime caches so they survive `make rebuild` cycles. Three named volumes covering the verified cache locations:
  - `the_one_uv_cache` → `/root/.cache/uv` (covers BOTH `uv` and `uvx` — `uvx` is `uv tool run`, no separate uvx cache exists)
  - `the_one_pipx_state` → `/root/.local/share/pipx` (pipx venvs; persistent payload)
  - `the_one_npm_cache` → `/root/.npm` (npm + npx package cache)
  
  Add corresponding entries to the top-level `volumes:` block alongside the existing `the_one_data` volume; use the `the_one_` prefix to match convention.
- Tests: smoke test (in `scripts/` invoked from `make rebuild`, NOT pytest — pytest-in-container Docker-image smoke tests are awkward) that `uvx --version`, `pipx --version`, `npx --version` resolve inside the container; runs `uvx mcp-server-time --help` end-to-end to verify the install pipeline works; verifies cache volume persists across `docker compose restart the-one`.

**First-spawn latency** trade-off (calibrated against empirical probe of `uvx mcp-server-time` on fresh cache + good network):
- Typical small Python MCPs (e.g., `mcp-server-time`): ~2-10s. First-spawn well within the existing `_TEST_CONNECT_TIMEOUT=15.0s` HTTP timeout (which the stdio Test will mirror).
- Heavyweight packages (ML stacks, full Playwright with `playwright install` for browsers): 30s+ to several minutes. Document as "first refresh may take longer; if timeout fires, manually warm cache via `docker compose exec the-one uvx <package> --help` then click Refresh again." Don't extend the timeout — that increases UX latency for the common case.

Operator-felt: first Refresh shows the existing "Testing connection…" loading state for slightly longer; subsequent Refreshes are fast (cache-hit). No new UI indicator needed in this leg.

**Concurrent first-spawn safety** (architect-verified empirically): both `uv` (file-locked at `/root/.cache/uv/.lock`) and `npm` (file-locked at `~/.npm/_locks/`) handle concurrent install correctly. The F4 pool's per-`(agent_id, source_id)` keying additionally serializes spawns within an agent. No additional locking needed in the leg.

**Network requirement** at install time: first spawn requires network egress to fetch the package. If a stdio source's sandbox profile has `network_allowed=False`, the install fails. This intersects the bwrap-vs-no-bwrap question (separately under operator consideration). For this leg, the recommendation is: stdio sources that use a runtime-fetch command (`uvx`, `npx`, `pipx run`) need `network_allowed=True` for the first spawn at minimum. Document in flight log if operator surfaces friction.

**Sizing**: ~25-40 LOC (Dockerfile ~5-10; docker-compose.yml ~5-10; smoke test ~15-20).

### Deliverable 3 — Clear error surfacing on spawn failures (improvement #1)

**The gap**: today, if an operator's stdio command isn't resolvable (e.g., `command=npx` when node isn't installed; `command=python args=[-m, mcp_server_nonexistent]`), the spawn fails and the error rendered to the operator is generic and cryptic ("process exited with code N", or anyio cleanup noise).

**The fix shape**: wrap the stdio spawn error path in `the_one/mcp/transports/stdio.py` to translate common failure modes into operator-actionable messages:
- `FileNotFoundError` / `command not found` → "The command '%s' is not available in the container. Add it to the Dockerfile and run `make rebuild`, or install via `docker compose exec the-one <package-manager> install <pkg>`."
- `ModuleNotFoundError` (Python `python -m foo` when foo isn't installed) → "The Python module '%s' is not installed. Use `command=uvx args=[%s]` for runtime install, or pre-install via `pip install %s`."
- Generic non-zero exit → preserve current error display but include the full stderr in a collapsible details element.

**Critical interaction with F3's bwrap-stderr discriminator** (architect-flagged at L2 design review): `the_one/mcp/transports/stdio.py` already has a `_translate_bwrap_stderr` discriminator using `_BWRAP_OWN_PREFIX_RE` per the F3 §6 directionality contract — distinguishing bwrap's own errors (e.g., bwrap can't exec the inner command) from the inner process's errors. Deliverable 3's translation MUST run AFTER the existing bwrap-stderr discriminator AND must check `not _BWRAP_OWN_PREFIX_RE.search(stderr_text)` before applying these new translations. Otherwise a sandbox-side `FileNotFoundError` (bwrap can't find the command) would be mistranslated as a "missing in container" message when the actual root cause is sandbox profile misconfiguration. Architect pass for Deliverable 3 must verify the placement preserves the directionality contract.

**Sizing**: ~20-30 LOC (error translation + message templating; possibly small UI enhancement to show stderr in collapsible details).

### Combined prerequisite sizing (calibrated by L2 design-review architect)

| Deliverable | LOC | Notes |
|---|---|---|
| 1. Stdio Test connection feature add | ~115-180 | Backend ~60-90, frontend ~5-10, tests ~50-80 |
| 2. Generic-runtime container additions | ~40-65 | Dockerfile ~3-6, docker-compose ~6-10, smoke test in `scripts/` ~30-50 (cache-persistence-across-restart assertion bumps this) |
| 3. Clear error surfacing | ~30-50 | +~15 LOC for bwrap-discriminator interplay (architect-flagged) |
| **Total prerequisite** | **~185-295** | |

§2 compliance: at the ~295 LOC high end, this is above the >200 LOC "single inline fix to F1-F8 functionality" divert threshold — but §2's threshold table explicitly applies to a **single fix**, not three coordinated structural deliverables. Treating the bundle as a unified prerequisite (which it is — no deliverable ships standalone for L2 to start vibing) keeps it within F9 §1's "structural prerequisite" classification, not as a regression-class fix.

**Methodology note for L8 / mission debrief**: the prereq scope grew from "one structural prerequisite" (stdio Test connection) to "three coordinated deliverables" once the architectural conversation about deps + sandbox surfaced. Useful signal — the mid-design course-correction was driven by operator-felt friction, not by initial design discovery. Worth surfacing as a methodology insight at L8.

**Acceptance criteria for the structural prerequisite** (verified BEFORE operator vibing begins):
- [ ] Operator can navigate to Studio → MCP Sources → create a stdio source → click Refresh connection → tools list renders within ~5s (or longer for first-spawn runtime install) with capability flags one-liner + collapsible input schemas
- [ ] Caplog clean (0 `MCPClient.disconnect`) across the stdio Test path
- [ ] `uvx mcp-server-time`, `npx -y @playwright/mcp` (or any other pip/npm-resolvable MCP) usable as a stdio source's `command + args` without Dockerfile changes
- [ ] Cache volume persists across container restart (verified by registering an `uvx`-based source, refreshing once, restarting `the-one`, refreshing again — second refresh should be fast / cache-hit)
- [ ] Spawn failures from missing commands or missing modules surface operator-actionable error messages
- [ ] All prior 49+ browser tests pass; updated/new tests for stdio Test pass
- [ ] No regression to L1's HTTP path or the `_cache.auth_posture` Shape C logic

## Inputs

What exists before this leg runs:
- Dev container running on `http://localhost:8484`; web UI loads
- F1-F8 + F9 L1 deliverables in production (HTTP create+test workflow polished, OAuth themed, Reset connection in place, tools cache persisted, `_cache.auth_posture` hint working for HTTP)
- Sandbox layer (F3): `bubblewrap` available in dev container; `the_one/mcp/transports/stdio.py:38-59 — "BubblewrapSandbox.prepare_spawn"` wires sandbox profile per `MCPSource.config["sandbox"]`
- Idle-TTL pool (F4): `the_one/mcp/_pool.py:57-129` — `_DEFAULT_TTL_SECONDS = 300`, `_REAPER_INTERVAL_SECONDS = 30.0`, per-`(agent_id, source_id)` keyed registry
- In-repo FastMCP fixture (F2): `tests/fixtures/mcp/hello_server.py:55-63 — "echo, add"` core tools; `:147-150 — "FastMCP.run('stdio')"` entry point; spawn invocation `python -m tests.fixtures.mcp.hello_server --stdio`
- Pre-leg housekeeping: warm-pool clear via `docker compose restart the-one`; F8 baseline as the regression diff target; L1's `cloudflare_api` source still registered with cached state for non-interference verification

## Outputs

What exists after this leg completes:
- A registered stdio MCP source pointing at the FastMCP fixture (or operator-chosen alternative) — handed off to L4 + L6
- Stdio Test connection feature add shipped (backend + frontend + tests)
- Any inline fixes to stdio form polish, sandbox config UX, or idle-TTL surfacing — captured in the diff and logged in the flight log under "L2 → Inline Fixes Implemented"
- Flight log appended with: per-scenario operator-felt notes, anomalies + triage + resolution, caplog count, fixture-vs-override decision

## Acceptance Criteria

- [ ] Structural prerequisite landed: stdio Test connection works on the source-edit page (capability flags + collapsible schemas render; caplog clean; tools cache persists)
- [ ] All operator scenarios walked (exploratory or scripted); operator reports the create-and-test stdio workflow "works well" overall
- [ ] Caplog gate clean: 0 `MCPClient.disconnect` warnings across this leg's HAT exercises (high-signal — first stdio re-assertion since F6 baseline)
- [ ] Sandbox spawn verified: stdio source spawns under bubblewrap with the documented 8-key env allowlist + operator-defined env overlay; operator-felt no friction
- [ ] Idle-TTL behavior verified: stdio source warm pool reaped after disuse (verifiable via caplog or via re-Test latency — first call cold, second call within ~30s warm)
- [ ] Any anomaly surfaced is triaged per Flight Design Decisions §2 + §5 and recorded in the flight log
- [ ] Stdio source registered + tools cache populated at leg close (default outcome): documented in flight log; ready for L4/L6 to inherit

## Verification Steps

For each scenario, the operator reports the observed outcome in plain language. The Flight Director (Claude) compares against the expected outcome and asks the operator to confirm "works well" before moving to the next scenario. Any divergence triggers triage + fix-or-defer.

Caplog gate check: at any anomaly + at leg close, run `docker compose logs --tail 200 the-one 2>&1 | grep -c "MCPClient.disconnect"` — count should remain at 0.

## Implementation Guidance

### Phase 0 — Structural prerequisite (before vibing)

1. **Architect pass** (per §7, ≤5 min) — spawn an Architect subagent to design the stdio Test connection feature add. Architect reads:
   - `the_one/interfaces/web/api.py:962 — "async def test_mcp_connection"` (current HTTP-only flow)
   - `the_one/interfaces/web/api.py:1048 — "if source.type != \"streamable-http\""` (early-return guard to remove)
   - `the_one/mcp/transports/stdio.py:38-59 — "BubblewrapSandbox.prepare_spawn"` (sandbox spawn integration point)
   - `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:205` (Refresh button render gate)
   - `the_one/mcp/_pool.py:57-129` (idle-TTL pool — does Test path use the warm pool, or transient client?)
   - `tests/conftest.py::pytest_configure` (sandbox bypass dual-flag)
   - F4 + F6.6 disconnect cleanup history (caplog risk surface)
   
   Architect produces: shape (transient client vs warm-pool integration), LOC estimate, risk per §7, anyio-cleanup-noise risk, acceptance criteria, file:symbol citations.
   
2. **Implementer dispatch** — spawn an Implementer subagent with the architect's plan. Files affected:
   - `the_one/interfaces/web/api.py` — `test_mcp_connection` extension
   - `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — Refresh button ungate
   - `tests/browser/test_mcp_test_connection_button.py:84-98` — invert "absent" assertion
   - New test in `tests/test_*.py` — integration test for stdio Test path
   
3. **Operator re-verification** — operator confirms stdio Test connection works on a quick smoke (create FastMCP source → Refresh → tools render → no caplog noise). Once confirmed, proceed to vibing.

### Procedure shape (Flight Design Decision §1's structured pattern, exploratory mode)

1. **Setup** — operator confirms dev container up; warm-pool cleared; FastMCP fixture available (or operator override declared); ready to drive the web UI.
2. **Walk operator scenarios** (exploratory primary, coverage list as fallback) — Flight Director presents one scenario at a time OR lets operator drive freely.
3. **Capture issues** — anomalies logged immediately into the flight log under "Anomalies Captured" for L2.
4. **Triage** — per §2 + §5: inline-fix (default for ≤100 LOC + leg-scope) / absorb-into-sibling / defer-to-follow-up. Architect pass per §7 if the fix touches a known-problematic-path.
5. **Fix or document** — inline fixes implemented immediately via Implementer subagent (per §9); absorbs/defers logged with target-leg or follow-up-flight reference.
6. **Re-verify** — re-walk affected scenarios to confirm fix.
7. **Close leg** — operator-felt sign-off + caplog gate verification + flight log finalization for L2.

### Operator scenarios (8 total, coverage check for exploratory mode)

**Scenario 1 — List view sanity (post-L2 polish carry-over check).**
Operator: navigate to Studio → MCP Sources (`#studio/mcp-sources`).
Expected: list view renders cleanly; existing `cloudflare_api` source visible from L1; transport-type badges scannable; "Create" affordance prominent.
Vibing prompts: Are stdio and streamable-http badges visually distinct? Does the list mix transport types cleanly?

**Scenario 2 — Create form: stdio path navigation + transport switching from L1's HTTP-default.**
Operator: click Create → form opens (likely defaults to streamable-http per L1's flow). Toggle the transport selector to stdio.
Expected: form fields swap appropriately. Stdio fields visible: command (`mcp-server-editor.js:372-377`), working directory (`:379-384`), arguments chip-list (`:386-390`), environment variables KV-table (`:306-312`), sandbox section (`:228-256` with Network toggle + writable paths chip-list). HTTP fields hidden.
Vibing prompts: Do the fields swap cleanly without state bleed (e.g., URL field doesn't carry over)? Is the sandbox section's purpose discoverable? Is "Allow network access" toggle's default (off) appropriate?

**Scenario 3 — Create form: stdio fixture configuration + validation.**
Operator: fill in the FastMCP fixture config:
- Name: `local_fastmcp`
- Transport: stdio
- Command: `python` (or absolute path if needed)
- Args: `-m`, `tests.fixtures.mcp.hello_server`, `--stdio`
- Environment variables: leave default (8-key allowlist applies via sandbox)
- Sandbox: Allow network access OFF; writable paths empty
Try save with required fields empty first → validation messages clear.
Then save the full config.
Expected: validation messages near offending fields; successful save → redirect to detail/edit page; source appears in list.
Vibing prompts: Are validation messages clear for stdio-specific fields (e.g., empty command)? Does the args chip-list editor feel right (add chip, edit chip, remove chip)?

**Scenario 4 — Refresh connection (post-prerequisite feature add).**
Operator: on the stdio source detail page, click Refresh connection.
Expected: stdio subprocess spawns under bubblewrap → initialize → list_tools returns `[echo, add]` → response renders Tools section with capability flags one-liner + collapsible input schemas + "Last updated: just now" line. Sandbox confined the process (no host-FS writes outside scope; no network egress).
Vibing prompts: Does the spawn feel snappy or laggy? Are echo + add tools visible with their input schemas? Does the capability flags display make sense for a minimal FastMCP server (likely just `tools` capability)?

**Scenario 5 — Edit cycle with sensitive env var + `__MASKED__`.**
Operator: edit the source — add an environment variable marked sensitive (e.g., `FAKE_API_KEY=test-secret-value`), save. Reload. Verify the value renders as `__MASKED__`. Save again without retyping. Reload. Verify the original value is preserved.
Expected: env-var KV table sensitive toggle works (matches L1's polish); `__MASKED__` round-trip lossless.
Vibing prompts: Does the env-var sensitive toggle feel right (was retrofitted from L1's Custom Headers polish)? Does the encryption-at-rest tooltip on the Sensitive column header read clearly?

**Scenario 6 — Sandbox boundary verification (lightweight).**
Operator: edit the source's args to add `--with-naughty-tools` (the F3 escape-attempt fixture). Save → Refresh.
Expected: tools list now includes 5 tools (`echo, add, write_outside_sandbox, dump_env, try_connect`). Sandbox profile blocks the escape attempts when called from agent (L4's job to verify; L2 just confirms the tools list).
Vibing prompts: The naughty-tools opt-in is for F3 verification — does the operator-facing tools list display feel like a faithful representation of what the server exposes?

**Scenario 7 — Idle-TTL + warm-pool sanity.**
Operator: click Refresh once → tools render. Wait > 30s (idle-TTL reaper interval) without re-Test. Click Refresh again → verify tools render (warm or cold spawn — both should work cleanly).
Expected: caplog clean throughout. The first Refresh after a long idle may show a "spawn" event in logs; that's expected and not a `MCPClient.disconnect` warning.
Vibing prompts: Is there any UX surfacing of "this is a fresh spawn vs warm reuse"? (None expected; just operator-felt smoothness.)

**Scenario 8 — Generic-runtime install model (uvx mcp-server-time).**
Operator: create a second stdio source pointing at a runtime-fetched MCP. Config:
- Name: `local_time`
- Transport: stdio
- Command: `uvx`
- Args: `mcp-server-time`
- Env: leave default
- Sandbox: `network_allowed=True` (required for first-spawn install fetch); writable paths empty
Save → click Refresh.
Expected: first Refresh takes ~5-15s (uvx fetches `mcp-server-time` and caches it); tools list renders with the time-server tools (timezone conversion, get-current-time, etc.); capability flags + collapsible schemas render. **Then**: restart the the-one container (`docker compose restart the-one`); click Refresh again → second Refresh is fast (cache volume persisted).
Vibing prompts: Is the first-spawn latency acceptable for the operator-felt experience? Is there any visible feedback during the install (loading state)? Does the cached second spawn feel materially faster? Does the operator's `command=uvx args=[mcp-server-time]` feel like a natural way to declare an MCP, or is the runtime-install model surprising?

**Cleanup**: leave both sources registered + tools-cached for L4/L6 to inherit. If operator added the `--with-naughty-tools` arg in Scenario 6, decide whether to keep it (helpful for L6 chat scenarios that want to test sandbox enforcement) or revert.

### Per-anomaly procedure (matches L1)

When an anomaly surfaces:
1. Operator describes what happened in plain language.
2. Flight Director logs it in the flight log under "Anomalies Captured" for L2.
3. **If root cause unclear** → spawn an Investigator subagent (per §9). Subagent returns diagnosis. Parent does NOT read investigation trace.
4. Triage from the diagnosis: per §2's Sizing Thresholds. If touches a known-problematic-path per §7 (especially stdio teardown / anyio cleanup paths), spawn an Architect subagent for ≤5-min review.
5. Decision: inline-fix / absorb-into-sibling-leg / defer-to-follow-up.
6. **If inline-fix**: spawn Implementer subagent with the bug description, target file(s) + line ranges, fix shape, and acceptance criterion. Subagent returns structured summary; full diffs in git.
7. **If absorb / defer**: log in flight log; continue L2.

**Subagent return summaries** are appended to the flight log under L2's "Inline Fixes Implemented" section.

### Caplog gate

Throughout the leg, monitor `docker compose logs -f the-one` (sidecar terminal or periodic check) for `MCPClient.disconnect` warnings. Surface immediately to Flight Director if any appear. **L2 is the first stdio re-assertion since F6** — a new disconnect warning is high-signal (potential regression in stdio teardown since F4-L1's dispatcher rewrite). At leg close: `docker compose logs the-one 2>&1 | grep -c "MCPClient.disconnect"` should return `0`.

## Edge Cases

- **Stdio Test connection feature add hits anyio cleanup-deadlock risk** — the F4/F6.6 transport-stack lifecycle is fragile; if architect pass identifies elevated risk, defer the feature add to a dedicated follow-up flight and document L2 closure with the workflow gap (per §5 carve-out policy). However: HTTP path uses the same transport-stack lifecycle and works cleanly, so risk should be mitigable.
- **FastMCP fixture spawn requires `python` in dev container** — verified at L2 setup (operator runs `docker compose exec the-one python -m tests.fixtures.mcp.hello_server --stdio` to confirm fixture works manually before vibing).
- **Operator-override stdio target requires non-default sandbox config** — e.g., npx-launched server needs `node` in env-allowlist + network access for npx fetch. Document the config in flight log; if it requires sandbox profile changes, that's potentially scope creep — defer to L4/L6 if needed.
- **F8 carve-out A1 (`_pool.py` test isolation) surfaces during L2** — pre-existing known issue; document in flight log under "Anomalies Captured" with severity classification, defer per §5.
- **Sandbox bypass needed for non-default operator-stack stdio MCP** — if operator's chosen stdio target genuinely cannot run under bubblewrap (e.g., requires `CAP_SYS_ADMIN` or unprivileged user-namespaces unavailable in dev container), the F3 sandbox-bypass dual-flag (`THE_ONE_SANDBOX_DISABLED=1 AND THE_ONE_TEST_MODE=1`) is **NOT for production-mode operator-driven Refresh**. Production-mode requires the source to fit the sandbox model. Document the gap in flight log; defer to L4/L6 design.
- **Args chip-list editor has known UI quirks from F1** (per existing browser tests at `tests/browser/test_flow_studio_mcp_editor.py`) — if operator surfaces a chip-list issue, triage per §2.

## Files Affected

This is a vibing leg with three coordinated structural prerequisites. The file set is determined by what the operator surfaces; predicted touch points:

**Structural prerequisite — Deliverable 1 (stdio Test connection):**
- `the_one/interfaces/web/api.py:962 — "async def test_mcp_connection"` — extend for stdio
- `the_one/interfaces/web/api.py:1048 — "if source.type != \"streamable-http\""` — remove the early-return guard
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:205` — ungate Refresh button render
- `tests/browser/test_mcp_test_connection_button.py:84-98` — invert "absent for stdio" assertion
- New integration test for stdio Test path (file TBD per architect)

**Structural prerequisite — Deliverable 2 (generic-runtime container):**
- `Dockerfile` — add `nodejs npm` to apt install line; add `pip install uv pipx` to pip install layer
- `docker-compose.yml` — add three named Docker volumes (NOT bind-mounts) for runtime caches: `the_one_uv_cache:/root/.cache/uv`, `the_one_pipx_state:/root/.local/share/pipx`, `the_one_npm_cache:/root/.npm`. Add corresponding entries to top-level `volumes:` block.
- `scripts/` — new bash smoke test (invoked from `make rebuild` or as a standalone target) that verifies `uvx --version`, `pipx --version`, `npx --version` resolve in container, runs `uvx mcp-server-time --help` end-to-end, and verifies cache persistence across `docker compose restart the-one`. (Pytest-in-container Docker-image smoke is awkward — bash script is simpler.)

**Structural prerequisite — Deliverable 3 (clear error surfacing):**
- `the_one/mcp/transports/stdio.py` — error-translation wrapper for `FileNotFoundError` / `ModuleNotFoundError` / generic non-zero exit
- Possibly `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — collapsible-details element for stderr display
- Tests for error-translation paths

**Predicted vibing-driven inline fixes** (likely sites for polish issues):
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` — sandbox section UX, args chip-list, env-var table polish parity with L1
- `the_one/interfaces/web/static/css/studio.css` — possible CSS polish for stdio-specific surfaces
- `the_one/mcp/transports/stdio.py` — possible inline fix to error message wording or sandbox config validation
- Browser tests in `tests/browser/test_flow_studio_mcp_editor.py` — regression coverage for inline fixes
- Flight log + this leg's status field — always

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] Structural prerequisite (stdio Test connection) shipped + verified
- [ ] All operator scenarios walked (exploratory or scripted) + operator-felt sign-off
- [ ] Caplog gate clean (0 `MCPClient.disconnect` warnings across leg HAT)
- [ ] Anomalies captured in flight log with triage + resolution
- [ ] Inline fixes (if any) implemented; their unit/browser regression coverage added per inline-fix scope
- [ ] Stdio source state at leg close documented in flight log (registered + tools-cached; or anomaly-deferred)
- [ ] Stdio target choice (FastMCP fixture vs override) documented in flight log
- [ ] Update flight-log.md L2 section with: status `landed`, scenarios walked, anomalies + resolutions, caplog count, files touched
- [ ] Set this leg's status to `completed` in this file's header
- [ ] Check off L2 in flight.md's Legs list
- [ ] Inline-fix LOC added to L8 bundled-review queue (running tally in flight log)
- [ ] Commit all changes together (code + leg artifact + flight log)

---

## Citation Audit

15 code-location citations re-verified against current code at L2 design-review time (2026-05-09, post-L1 close on `flight/09-alignment`):

**Drift repaired** (caught by L2 design-review architect's empirical re-verification):

- `the_one/interfaces/web/api.py:962 — "async def test_mcp_connection"` — **drifted from L822 → L962**, repaired. Original recon was stale post-F9 L1 commits.
- `the_one/interfaces/web/api.py:1048 — "if source.type != \"streamable-http\""` — **drifted from L980 → L1048**, repaired. Original recon was stale post-F9 L1 commits.

**Verified (no drift)**:

- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:205` — Refresh button render gate — **OK**.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:228-256` — Sandbox section — **OK**.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:306-312` — Env vars KV table — **OK**.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:372-377` — Command field — **OK**.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:379-384` — Working Directory field — **OK**.
- `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js:386-390` — Args chip-list — **OK**.
- `tests/fixtures/mcp/hello_server.py:55-58 — "echo"` — **OK**.
- `tests/fixtures/mcp/hello_server.py:60-63 — "add"` — **OK**.
- `tests/fixtures/mcp/hello_server.py:147-150 — "FastMCP.run('stdio')"` — **OK**.
- `the_one/mcp/transports/stdio.py:38-59 — "BubblewrapSandbox.prepare_spawn"` — **OK**.
- `the_one/mcp/transports/stdio.py:241-249 — "THE_ONE_SANDBOX_DISABLED docstring"` — **OK** (architect-cited).
- `the_one/mcp/_pool.py:57-129` — pool / idle-TTL constants and `_RegistryEntry` dataclass — **OK**.
- `tests/browser/test_mcp_test_connection_button.py:84-98` — current "absent for stdio" assertion (will be inverted) — **OK**.

**Verified runtime cache locations (empirical, container-as-root)**:

- `/root/.cache/uv` — covers BOTH `uv` and `uvx` (uvx is uv tool run; no separate cache). Contains `archive-v0/`, `builds-v0/`, `environments-v2/`, `interpreter-v4/`, `.lock` — verified.
- `/root/.local/share/pipx` — pipx venv root. Verified.
- `/root/.npm` — npm + npx package cache. Verified.
- (`/root/.cache/pipx` — pipx download cache, optional; venvs at `.local/share/pipx` are the persistent payload.)
- `/root/.cache/uvx` and `/usr/local/share/.cache/pipx` — **NOT REAL paths**; original leg artifact was wrong. Repaired.
