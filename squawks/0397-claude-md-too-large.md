# Squawk 0397: CLAUDE.md is too large; pare it back to pointers

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

## Report
The operator reported on 2026-11-21 that `CLAUDE.md` is flagged as too large to load comfortably. It
has grown with a detailed paragraph per mission feature: the GleepGlorp legs, the widgets, the
desktop shells, the lane tables. That detail duplicates `the_one/agents.md`, `SECURITY-MODEL.md` and
`evals/README.md`.

Pare it back to the always-needed operational manual: commands, safety rules (ports, data dir,
credentials), test entry points and the quiet-host rule. Replace each feature paragraph with a
one-line pointer to its `the_one/agents.md` section. Move the per-lane budget prose to
`scripts/run-tests.sh` (already the source of truth) or `the_one/agents.md`.

Keep every rule that prevents harm:
- never port 8484 or 8485;
- never the default data dir;
- the plan token;
- browser tests only through `run-tests.sh`;
- the shell-write rule.

Doc-only: no code changes.

## Evidence
- `CLAUDE.md`: 666 lines, 182,468 bytes (2026-11-21).
- `the_one/agents.md` already holds the deep reference for most feature paragraphs. `CLAUDE.md` says
  of it: "Don't duplicate that material here".

## Corrective Action
Rewrote `CLAUDE.md` as the operational manual: What This Is, Commands (exact ruff lines kept), Local dev
and `make` targets, a short Architecture orientation (the `__MASKED__`, agent-PUT credential and naming
contracts as one-liners, then one pointer line per feature family), a new "Safety rules" section
(ports 8484/8485, default data dir, plan token, shell-write rule, snapshots gitignored, credential gate,
test seams), "Prompt evals (Mission 30)" (rule plus what counts as platform prompt text plus baselines),
Conventions, a condensed HAT guidance, Testing (rules only), a short "Per-area browser test lanes",
the whole "Behavior-test credential convention" section (headings unchanged, prose tightened, every
rule kept) and "Flight Operations" unchanged. Detail that lived only in CLAUDE.md moved to
`the_one/agents.md` as two new subsections before "Performance instrumentation": "Browser test lanes,
budgets and run policy" (host policy, quiet-host rule, full re-budget history, lane definitions, 0334,
skip counts, `requires_bwrap` set, pixel/AIAT notes) and "Dev mode seams and HAT env" (mock provider
pointer, test-seam flags, `THE_ONE_FAKE_PLATFORMS_URL`, HAT env, origin allowlist). Stale references
to headings that no longer exist were repointed: `SECURITY-MODEL.md` (six references, now to agents.md
"Tool authorship contract (F4+)", "Constraint surface", "Encryption-rotation invariant", "`__MASKED__`
sentinel (LLM providers)") and `the_one/mcp/README.md` (F2 reference). Review round: added the
missing "Frozen-runtime seam (M15 F5)" subsection and the M15 F5 spec sentence under "Windows
packaging (M32 F4)", restored two dropped test details, and moved the behavior-test recipe to port
8486. Doc-only.

## Verification
1. Size: `CLAUDE.md` 182,468 bytes / 666 lines -> 28,117 bytes / 223 lines (about 15%).
2. Where each removed block lives (grep of distinctive symbols in `the_one/agents.md`, all present
   unless noted): Watch-outs and per-agent MCP credentials (`agent_mcp_tool_cache`, "Per-agent MCP
   credentials (sortie 09)", "Agent override ..."); LLM layer (`supports_adaptive_thinking`,
   `cache_read_tokens`, "Anthropic prompt caching (sortie 14)", "Claude Plan providers ..."); Secrets
   ("Secrets (sortie 10)"); Self-configuration (`agent_revisions`, `self_revision_requires_approval`);
   GleepGlorp M36 paragraphs (`read_app_config`, `propose_change`, `fill_form`, `gleepglorp_notes`,
   `gleepglorp_proposals`, `gleepglorp_fills`, `gg-` drawer sections: every cited heading exists);
   Knowledge M24 (`close_vector_store`, `walk_skip_counters_key`, `content_freshness`,
   `confirm-lapsed`, `windows-vector-bench`, `KBToolProvider`); Desktop launcher (`_select_port`,
   `_graceful_shutdown`, `DesktopSession`, `window-state.json`, `macos_dock`); packaging and release
   (`release_check.py`, `product.toml`, `rthook_host_gtk`, "Release workflow (M32 F4)"); MCP 2.x
   (`httpx2`, `MCPCredentialsRejected`, `negotiation_fallback`); routines (`RoutineScheduler`,
   `resolve_now_start`); boxed execution/PTY/frozen runtime (`host_access`, `PassthroughSandbox`,
   `read_blocking`, `clean_subprocess_env`, `prime_login_shell_path`); router, shell, Chats, Jump to,
   time zones, tool exposure, Settings and Library pages, focus-after, store, control library, charts,
   widgets (every cited heading and symbol present). Mock provider options: `MockProvider` docstring in
   `the_one/llm/mock.py` already lists `response`, `responses`, `stream_chunks`, `delay_ms`,
   `input_tokens` and the `models` note is now in agents.md "Dev mode seams and HAT env". Probes that
   were ABSENT from agents.md were moved there (new subsections above): `THE_ONE_FAKE_PLATFORMS_URL`,
   `THE_ONE_HAT_DRIVER_TOKEN`, `THE_ONE_REQUIRE_ISOLATED_CHROMIUM`, the quiet-host rule, expected skip
   counts, 0334, lane lists and the re-budget history. `strip_bundle_dir_from_path`, `FRAME_POLICY`
   and `gg-corner-button` are in code, `SECURITY-MODEL.md`/`docs/ui-control-inventory.md` and
   `scripts/probe`, not lost detail (agents.md covers "Order (`clean_subprocess_env`...)" for the first).
   The test-seams table was shortened to a one-line safety index in CLAUDE.md with the full text in agents.md.
3. Pointers: every quoted heading in CLAUDE.md was checked against `^#` headings of agents.md; the
   only non-heading hits were bold lead-ins that exist in agents.md ("Charts in chat", "Widgets in
   chat", "Native bridge removal and the widget crash record"), "Authentication" and "Live visuals"
   (headings in `SECURITY-MODEL.md`) and "The eval method (M36 F2)" (`evals/README.md`).
4. Safety strings present in CLAUDE.md: `8484`, `8485`, `data_dir`, `plan-token`, `run-tests.sh`,
   `THE_ONE_TEST_NETNS`, `-m live`, quiet-host rule ("Quiet-host rule"), `--no-project`,
   `block_shell_writes`, `__MASKED__`, `SAFETY RULE`, "Behavior-test credential convention",
   `m36f3-gleepglorp`, `scripts/ evals/`. Headings other docs cite are kept: "Per-area browser test
   lanes", "Prompt evals (Mission 30)", "SAFETY RULE", "Behavior-test credential convention" (and its
   subsections 1-4, `.flightops/agent-crews/behavior-tests-execution.md`, ~30 `tests/behavior/*.md`).
5. Tests: `run-tests.sh tests/test_evals_cli.py tests/test_shell_write_hook.py -x --timeout 120`:
   133 passed. Other tests that mention the docs (`test_design_tokens_a11y`, `test_store_static`,
   `test_studio_editor_contracts_static`, `test_routine_log_vocabulary`): 386 passed; none read
   CLAUDE.md except `test_evals_cli.py` (the `scripts/ evals/` string).
6. `git diff --stat`: CLAUDE.md 599 lines changed (165 ins / 535 del across the four files
   below), `the_one/agents.md` +2 subsections (the file also carries the batch's other uncommitted
   sections), `SECURITY-MODEL.md` 18 lines, `the_one/mcp/README.md` 4 lines.
7. Review fixes: (a) the old "Frozen-runtime seam (M15 F5)" paragraph had no home; added
   `the_one/agents.md` "### Frozen-runtime seam (M15 F5)" (symbols checked against
   `platform/env.py`, `platform/interpreter.py`, `config.py::_resolve_env_file`; links the macOS
   runtime seam section) and the CLAUDE.md pointer names it. (b) "Windows packaging (M15 F5)": the
   M32 F4 section already held `build.ps1`, `[windows]` in `product.toml` and the installer quit
   sequence; added the missing M15 F5 sentence (spec and frozen entries in `packaging/windows/`,
   never imported, native Windows) there. (c) Swept every backticked token of the old CLAUDE.md
   against CLAUDE.md, agents.md, SECURITY-MODEL.md, evals/README.md, run-tests.sh, the control
   inventory and the Windows README: the remainder was code or API shapes, run-result lines and
   test names, with nothing else needing a move. Restored `PRAGMA synchronous=OFF` (session
   template section) and `isolated_chromium_policy` (Engine env bullet). (d) The behavior-test
   recipe, curl examples and "Port alone" line now use 8486 (also the `make down` example in Local
   dev); the apologising parenthetical is gone. The `tests/behavior/*.md` specs hard-coding 8485
   are left for a separate squawk. `CLAUDE.md` is now about 28.5 KB.
   Left unresolved (pre-existing, not caused here): `the_one/mcp/README.md` and
   `the_one/mcp/__init__.py` cite "CLAUDE.md F3 contracts §5/§7" and a "F2 ... Contracts" heading
   that no longer existed before this squawk; the F3 sandbox catalog text exists in neither doc.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed after one fix pass (homes in agents.md for the frozen-runtime seam and the M15 F5 Windows packaging detail, two small restored details, the behavior-test recipe moved to port 8486), re-review confirmed; stale CLAUDE.md citations in code and the MCP README logged as squawk 0398, behavior specs on port 8485 as squawk 0399
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
