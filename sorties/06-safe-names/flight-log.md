# Flight Log: Safe names

**Flight**: [Safe names](flight.md)

## Summary
Landed 2026-10-26: four legs (server rule, rename carries, forms and load-failure toast, startup repair), one flight review (Sonnet) plus an accessibility review, one fix pass, full gate green apart from pre-existing environment failures. Sortie planned 2026-10-26 from an operator report on the macOS build: an agent named with a `/` could not be loaded, edited, renamed or deleted (every `/api/agents/{name}…` route 404s on a decoded `%2F`). Logged first as a squawk candidate; it failed the squawk gate (several items, design decisions, a migration) and was chartered as a sortie. The operator widened the naming rule from agents to agents, model providers, knowledge bases and MCP servers (2026-10-26).

---

## Leg Progress

### Flight Director Notes
- 2026-10-26: execution started. Worktree `.claude/worktrees/sortie-safe-names`, branch `sortie/06-safe-names` from `main` at `2e82aaa`; its own `.venv` (`pip install -e ".[all-llms,dev]"`, Playwright 1.58.0). Crew file `.flightops/agent-crews/leg-execution.md` loaded (Developer: Sonnet; Reviewer: Haiku, or Sonnet on a security-sensitive surface).
- Leg 1 `name-rule-server` tiered **high**: it changes the shape of existing API errors (the rename route's details) and touches a path-building surface (the boxed scratch directory). Developer design review runs before implementation.
- Baseline `make test-unit` in the worktree (fresh venv, `2e82aaa`, no changes): 10 failed, 7650 passed, 20 skipped, 371 s. Pre-existing, environment-related (fresh dependency resolution; squawk 0241's class): `test_credential_gate::TestExemption::test_exempt_paths_are_get_only_on_the_real_app`, `test_desktop_host` (3: GTK/WebKit present/missing), `test_mcp_wire_shapes::test_httpx2_uses_the_os_trust_store_unless_overridden`, `test_openrouter_wire_level` (4), `test_vector_store` usearch-f16 self-first. Legs compare against this list; any other failure is a regression.
- Leg 1 design review: approve with changes, all adopted (see the leg's closing note). Not re-reviewed: the changes apply the reviewer's own fixes and add no new design. One deviation from flight DD4 recorded here: the three PUT routes check `name` only when the body carries it, so a legacy bad row stays editable until leg 4 repairs it; DD2's "trimmed on its next save" therefore means a save that sends the name (every form does).

- Leg 1 landed (Developer report: 10 failed / 7726 passed / 20 skipped, failures = baseline list; the vector-store failure flipped between its `usearch-f16` and `usearch-i8` parametrisations, same test, accepted as baseline). Flight Director spot-checked the `api.py` diff against the leg.
- Leg 2 `rename-carries` tiered **high**: it changes `SQLiteAgentStore.rename` (a shared store interface with existing callers) and rewrites encrypted `mcp_overrides` through the store. Developer design review runs before implementation.
- Leg 2 design review: approve with changes, all adopted (see the leg's closing note); not re-reviewed (clarifications and test recipes, no new design). Confirmed: no connector code caches `default_agent`/`channel_map` (inbound re-reads the connector per message), so the DB rewrite needs no listener restart; `api.py`'s `rename_agent` is the only caller of `SQLiteAgentStore.rename`. Known limits accepted: a `disabled_tools` rewrite can also disable a same-named tool of another attached source that normalises to the new prefix (already a prefix-collision error state), and `mcp__foo__` also prefixes a `foo__bar` source's tools.
- Leg 2 landed (Developer report: 10 failed / 7741 passed / 20 skipped, failures = baseline list).
- Leg 3 `name-rule-forms` tiered **high**: it moves a testid that browser tests pin (`agent-load-error`, the frame test's first-children assertion) and changes the agent editor's save/error state handling. Developer design review runs before implementation.
- Leg 3 design review: approve with changes, all adopted; not re-reviewed. **Deviation from flight DD10**: DD10 (from Architect review 2) said to write `shell.errorEl.textContent` directly to avoid `setError`'s re-announce flicker on every `patch`; the leg review showed a direct write leaves the slot `data-empty` (collapsed, invisible). The leg instead calls `shell.setError` only on a load-state transition (tracked in `h.loadFailed`), which avoids both the flicker and the invisible line, as the knowledge-settings page does.
- Leg 4 `name-repair` tiered **high** (rewrites stored data at startup). Its design review ran in parallel with leg 3's implementation (read-only, server files only): approve with changes, all adopted; not re-reviewed. Implementation waits for leg 3 to land (one working tree; unit and browser runs never concurrent).
- Leg 3 landed after a second Developer finished verification (the first stopped mid-verification; its handover is in this log). The knowledge-inventory indexing-poll failure reproduced only with the worktree venv's `usearch` 2.26.6 (fresh resolution of `usearch>=2.16`); it passes on base and with this sortie's code under `usearch` 2.26.4 (the main venv's). The Flight Director pinned the worktree venv to `usearch==2.26.4` (environment only, no source change) so the landing gate reads this sortie's code, not dependency drift. Candidate squawk for the debrief: a fresh install resolves a `usearch` that fails a knowledge browser test (squawk 0241's class).
- Leg 4 landed (Developer report: 9 failed / 7767 passed / 20 skipped, all baseline; the vector-store parametrisation passed after the `usearch` pin).
- Flight review: Reviewer on **Sonnet** (the diff touches security-sensitive surfaces: encrypted `mcp_overrides` re-keying, the self-configuration surface marker, the boxed scratch path, startup ordering around the key reconcile). Accessibility Reviewer (Sonnet) spawned in parallel because leg 3 changed user-facing forms; it reads code only so test runs stay within the host policy.
- Review fixes re-reviewed (Sonnet): [HANDOFF:confirmed].
- **Landing gate (2026-10-26, worktree, `THE_ONE_TEST_NETNS=1`, `THE_ONE_REQUIRE_WEBKIT=1`):** lint (`ruff check` + `ruff format --check` on `the_one/ tests/ scripts/ evals/`) clean. Unit tier: 9 failed / 7765 passed / 23 skipped (334 s); the 9 are the baseline list (the vector-store parametrisation passed); 23 = this worktree's 20 + the 3 root-only skips under the network namespace. `make gate` stops after a non-zero unit tier, so the browser lanes were run directly: `scripts/run-tests.sh --parallel 3` → `PARALLEL_RESULT rc=1 total=1805s lanes=13 failed=knowledge`; 12 lanes green; the one knowledge failure reproduces on the base code with this venv (see Anomalies) and is accepted as pre-existing. Lane walls: mcp 535, routing 554, agents 490, contracts-controls 470, chats 467, library 423, knowledge 361, providers 377, shared 377, agent-tabs 310, settings 285, settings-tools 259, contracts-overlay 174.

### Leg: name-rule-server
**Status**: landed
**Changes**
- New `the_one/naming.py` (`check_name`, `NameRuleError`, message constants, `name_rule_detail`).
- `api.py`: `_checked_name` / `_name_conflict_detail` helpers; checks on `create_agent`, `rename_agent` (list-shaped details, 409 `name_conflict`), provider/KB/MCP create and update (PUTs only when `name` is in the body, on the merged dict); `create_agent` 409 on an existing name.
- `db/migration.py`: skips a bad body name with one WARNING, and skips when the body name already exists.
- `tools/sessions.py`: `_scratch_slug` for the boxed scratch directory.
- Tests: new `tests/test_naming.py`, `tests/test_api_name_rule.py` (40, incl. route classification); additions to `tests/test_db_migration.py`; `tests/test_db_api.py` slug-collision test now uses `"My Notes"`/`"My_Notes"`. No browser test or seeder used a refused name.
- Docs: `the_one/agents.md` "Naming rule"; `rename_agent` docstring.
**Verification**: the 27 API-touching test files ran green apart from the pre-existing `test_credential_gate` failure; ruff check and format clean. `make test-unit`: 10 failed, 7726 passed, 20 skipped (baseline 10 failed, 7650 passed, 20 skipped). The 10 failures are the baseline's pre-existing set; the vector-store one is the `usearch-i8` parametrization where the baseline had `usearch-f16` (same test, same environmental class).

### Leg: rename-carries
**Status**: landed
**Changes**
- `db/repositories.py`: `_parse_connector_binding_config` (shared with `connector_bindings`); `SQLiteAgentStore.rename` rewrites connector `default_agent`/`channel_map` in its transaction (fresh `updated_at`, `json.dumps`, malformed rows skipped with the existing WARNING); new `list_by_mcp_source`.
- New `the_one/mcp/rename_references.py::carry_mcp_rename` (copy-vs-move for shared names, no clobber, saves only changed agents, never raises, returns failed agents); `update_mcp_source` calls it after `repo.update` when the raw name changed, store acquisition guarded.
- `knowledge/kb_rename.py::carry_kb_rename` holds the tool-name computation, slug-unchanged early return and guarded acquisition; `update_knowledge_base` calls it with `get_agent_store=_agent_store` (resolved at call time); WARNING text unchanged.
- Docs: `the_one/agents.md` "Renames carry their references"; `rename` docstring. Known limits recorded there (`foo__bar` prefix ambiguity; rewriting to a prefix another attached source already normalises to).
**Verification**: new `tests/test_rename_carries.py` (15 tests); existing KB-rename tests unchanged and green. ruff check/format clean. `make test-unit`: 10 failed, 7741 passed, 20 skipped; failures are exactly the baseline list (vector store on `usearch-f16`).

### Leg: name-rule-forms
**Status**: landed
**Changes**
- Field errors (the 422 detail on the field via `App.api.fieldErrors`) on the agent, provider, KB create and KB edit forms; agent editor moved onto `fetchJson` + `fieldErrors`; load failure shows a toast and a header line (`agent-load-error` in the header error slot). `provider-editor.js` trimmed back to its 896-line ceiling (`test_area_module_size`).
- New `tests/browser/test_flow_name_rule_forms.py` (9 tests). Updated for intended wording changes: `test_flow_agent_editor_frame.py`, `test_flow_studio_knowledge_attach.py`, `test_flow_provider_visible_fixes.py`, `test_flow_provider_focus_after.py`, `test_flow_studio_knowledge_inventory.py` (`boom` -> `boom.`). Docs: `docs/ui-testid-registry.md`, `the_one/agents.md`.
- Leg-1 side effect: `test_shell_rail.py` seeded a 125-character KB name that leg 1's 64-character rule now refuses; shortened to 64.
**Verification**: full `--parallel 3` browser run (1539 s, 13 lanes): agents, agent-tabs, mcp, library, chats, routing, settings, settings-tools, contracts-overlay, contracts-controls passed; knowledge/providers/shared failures were fixed and the targeted rerun gave 69 passed, 1 failed (the indexing-poll case, see triage). Whole knowledge-inventory file rerun: 64 passed, 1 failed (same case). Static guards + lane/nav tests 451 passed; ruff check and format clean. `make test-unit`: 9 failed, 7742 passed, 20 skipped; failures are all on the baseline list (the flaky vector-store parametrisation passed this run).
**Triage of `test_detail_view_indexing_poll_reindex_and_search[chromium]`**: fails deterministically in the worktree (3/3, plus the file rerun; "indexed: 2" instead of 3), passes on base in the main checkout, and passes with this sortie's code under the main checkout's venv (`PYTHONPATH=<worktree>` with `<main checkout>/.venv/bin/python`). Cause is the environment, not the sortie: the worktree venv has `usearch` 2.26.6, the main venv 2.26.4. Not a sortie defect; no code change.

### Leg: name-repair
**Status**: landed
**Changes**
- `naming.py::repair_name(value, *, kind, taken)` (DD12). New `db/name_repair.py::repair_unsafe_names(conn, *, agent_store, mcp_repo, kb_repo)`: raw scans per table; agents via `rename` + `cascade_rename` (own try), MCP via raw surface skip, `mcp_repo.get/update` + `carry_mcp_rename`, KBs via `kb_repo.update` + `carry_kb_rename`, providers via raw `UPDATE`; per-row and per-step try/except; one WARNING per rename.
- `app.py` lifespan: the MCP repo is built before the repair and reused for `reconcile_on_startup`; the pass runs after `migrate_json_to_sqlite`, wrapped in try/except. The signature takes no `provider_repo` (providers use the raw UPDATE, per the leg).
- Tests: `tests/test_name_repair.py` (9 unit + 1 lifespan test), `repair_name` cases in `tests/test_naming.py`. Docs: `agents.md` "The startup repair".
- Test note: the KB case uses a bidi-character name, because `My/Notes` and `My Notes` derive the same tool slug (the carry correctly no-ops).
- Release notes: `docs/releases/` has no unreleased file; the next release notes should tell operators that unsafe names are renamed once at startup (logged).
**Verification**: test_naming, test_name_repair, test_lifespan 65 passed; ruff check and format clean. `make test-unit`: 9 failed, 7767 passed, 20 skipped; the 9 failures are exactly the baseline set (credential_gate 1, desktop_host 3, mcp_wire_shapes 1, openrouter_wire_level 4); the vector-store parametrisation passed.

### Review fixes
- a11y: `agent-editor.js` `setLoadError` now sets `aria-describedby` on Save to the header error line's id (`agent-editor-header-error`) while the load has failed and removes only that token when it clears; Save stays `disabled`. The load-failure browser test asserts both.
- `carry_kb_rename` wraps the `compute_tool_names` computation: a failure logs a WARNING naming the kb_id and returns (new unit test with a monkeypatched raise).
- `name_repair.py`: `carry_mcp_rename` and `carry_kb_rename` calls each sit in their own try with a WARNING, so one row cannot abort the step.
- Verification: see the final report of the review-fix run (unit, browser, static guards, ruff).

---

## Decisions

### Scope widened to four entities
**Context**: The operator asked whether the rule should cover more than agents (2026-10-26).
**Decision**: One rule for agents, model providers, knowledge bases and MCP servers; connectors stay out (display-only names).

### Related holes folded in
**Context**: The code map found create overwriting an existing agent, rename dropping connector bindings, MCP rename orphaning overrides, and `default`'s special role.
**Decision**: The operator folded in all four; after Architect review 1 showed a stored `default` configures every no-agent chat, the operator withdrew the reservation (`default` stays legal, never repaired; DD6).

### Architect review 1: approve with changes
**Context**: Two contradictions (DD11/DD12 on `default`; rename `loc`), the JSON-migration re-import loop, startup safety, non-unique MCP names, Windows paths in the boxed scratch dir, trim/guard ordering.
**Decision**: All adopted (DD4, DD5, DD8, DD11, DD13); legs re-cut into server, forms and repair (three legs, no HAT) so the trim-on-save rename has its carry in the same leg and browser time stays out of the server legs.

### Architect review 2: approve with changes
**Context**: The route walk could not infer which routes accept a name; the MCP carry had no never-raise contract; PUT bodies may omit `name`; the repair's failure example could not fail and the scan must not decrypt; the JSON import must stay skip-only; legacy surface rows; `disabled_tools` copy symmetry; a citation drift (`connector_bindings`).
**Decision**: All adopted (DD2, DD4, DD8, DD10, DD11, DD12). Leg 1 cut at DD8 into `name-rule-server` and `rename-carries` (four legs, no HAT: one decision cluster and one commit at the end; the cut is for review focus on the MCP carry). Sortie marked `ready` (2026-10-26); the operator had already asked for execution to start once the review returned.

---

## Deviations

---

## Anomalies

- **Superseded by the landing gate (below):** the leg-3 diagnosis that `usearch` 2.26.6 alone causes the indexing-poll failure was incomplete. Original entry kept: Worktree venv has `usearch` 2.26.6 against 2.26.4 in the main venv; with 2.26.6 `tests/browser/test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search` indexes 2 of 3 files (deterministic), and passes with 2.26.4 on the same sortie code. Pre-existing environment difference, related to the known usearch-dependent vector-store flake. Evidence: leg 3 triage above.
- **Landing gate, knowledge lane (2026-10-26):** with the worktree venv pinned to `usearch==2.26.4`, `test_flow_studio_knowledge_inventory.py::test_detail_view_indexing_poll_reindex_and_search[chromium]` still fails ("indexed: 2" where 3 is expected, line 517). The Flight Director ran the same test on the **base code** (a temporary detached worktree at `2e82aaa`, removed afterwards) with the worktree's venv (`PYTHONPATH` to the base tree): it fails identically. It passes on base with the main checkout's venv. So it is caused by the freshly resolved dependency set (many packages differ between the two venvs, not only `usearch`), not by this sortie. Accepted as pre-existing for this landing; squawk candidate for the debrief (squawk 0241's class: a fresh install does not reproduce a green suite).
- **Landing gate, budgets:** `chats` 467/450 s and `library` 423/420 s read OVER BUDGET; the host was not quiet (1-minute load about 2.0 at start, another session active), so per the quiet-host rule (squawk 0259) these are not re-budget evidence. This sortie added no chats tests and no library tests.
