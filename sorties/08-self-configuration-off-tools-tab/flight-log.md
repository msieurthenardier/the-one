# Flight Log: Self-configuration leaves the Tools tab

**Flight**: [Self-configuration leaves the Tools tab](flight.md)

## Summary
Sortie planned 2026-11-03 from an operator request: the self-configuration row on the agent editor's Tools tab and its per-tool checkboxes no longer make sense now that Self-configuration has its own tab with two items. Charter agreed the same day. No HAT; the Flight Director runs a behavior test instead.

---

## Planning Notes

### Qualification (2026-11-03)
All four sortie criteria pass: one outcome (the Tools tab stops showing the server; the Self-configuration tab is the only control), one cluster of decisions (stored selections, Save carrying the attachment, what the API accepts), one leg, no new subsystem. No open mission or sortie overlaps.

### Findings from code interrogation (at `503d9751`)
- **Removing the tile alone would detach the surface on the next Save.** Studio builds `mcp_source_ids` from the checked `[data-mcp-source-toggle]` inputs (`agent-form-data.js:171-184`). This drove DD2.
- **A stored selection survives a Studio Save.** `_merge_preserved_mcp_credentials` keeps a stored source entry that the body omits (`api.py:355-357`), so the 422 has to check the raw body (DD3), and stored entries need an explicit cleanup (DD4).
- **Disabling self-configuration leaves the override behind.** `manage.disable` does not touch `mcp_overrides`, so the startup cleanup scans every agent (DD4).
- **Three build sites apply overrides by source name**: the tool provider, the `search_tools` index and the `describe_my_capabilities` projection (DD4).
- **SECURITY-MODEL.md names the per-tool checkboxes as a mitigation** when approval mode is off (DD5). The operator accepted losing the read-only posture in the charter.

### Architect review 1 (2026-11-03): approve with changes
All findings taken:
- **High:** five orphan-via-PUT tests were missing from the audit. They now build the orphan state by direct store save and keep their security assertions (DD2).
- **High:** an every-agent scan inside the unguarded `reconcile_on_startup` could stop startup on one undecryptable row. It is now a separate `strip_surface_overrides`, guarded per agent and in the lifespan (DD4).
- **Medium:** `AgentConfig.disabled_tools` is a second per-tool withhold. It is closed by DD7, a Flight Director call that follows from the charter ("all four tools", "can no longer disable individual tools").
- **Medium:** removing keys by name could wipe an ordinary server's overrides. The legacy-prefix removal is dropped, since those keys are inert at build. The first fix, which required that no non-surface row have that name, was superseded by review 2.
- **Medium:** missed doc and comment sites are added.
- **Low-medium:** `agent-editor-selfconfig.js::rebaseBaseline_` is added.
- **Low:** an empty or `null` entry is treated as absent, not refused (DD3). The behavior test pins `THE_ONE_LOG_LEVEL=INFO` and the step 8 commit/close. Browser negatives avoid the retired testid.
- **Suggestions taken:** the carried id keeps its stored position; the deep-link no-op is recorded as a known effect.

### Architect review 2 (2026-11-03): approve with changes
- **Medium:** an ordinary row named exactly `self-configuration` was handled four ways. It is now declared unsupported (Flight Director call): it already collides with the surface's tool names, and the name has been reserved since M21 F01 L03. DD3, DD4 and DD7 have no carve-out.
- **DD7 build hook:** `MCPClientTool.is_platform_surface`, read with `getattr(..., False)` so injected stubs keep the old behaviour, with a test pinning the fallback. A narrow boolean was chosen over a general `source` property. Architect review 2 found no other site that applies `disabled_tools` to MCP tools.
- **Low:** the lifespan position is pinned, the audit row says `patchEntry`, DD7 and DD8 are renumbered to read in order, and the known effects (a leftover legacy key with its WARNING; `updated_at` bumps) are recorded. The carry position is `min(stored_index, len(incoming))`.
- Two review cycles used. The changes after review 2 are precision fixes, so no third pass.

### Gate re-check and ready (2026-11-03)
- Still one cluster of decisions: everything about the surface on an agent is owned by the server, not the form. DD7 is the same rule applied to a second field.
- Still one leg, with no HAT. Status set to `ready`.

### Operator decisions
- Charter agreed, including the 422 and restoring all four tools to agents that had one unchecked (2026-11-03).
- No HAT. The Flight Director runs its own behavior tests on the surface (2026-11-03).

---

## Flight Director Notes
- 2026-11-03: execution started (`/mission-control:agentic-workflow sortie 08`). Loaded `.flightops/agent-crews/leg-execution.md`, which is well-formed. Branch `sortie/08-self-configuration-off-tools-tab` created from `main` at `503d9751`. Flight status set to `in-flight`.
- Leg 01 `self-configuration-leaves-tools-tab` designed. **Risk tier: high.** It touches a security-sensitive surface (self-configuration identity), changes shared interfaces with existing consumers (the agent write routes, `MCPClientTool`, the factory's registration filter), adds a startup lifecycle step, and reverses pinned tests. A Developer design review runs before implementation (Sonnet, per the crew file).
- Reviewer tier for the flight review: **Sonnet**, because the diff touches self-configuration identity. The Accessibility Reviewer is spawned too, because the Tools tab changes.

- Leg 01 design review, Developer (Sonnet): **approve with changes**, all taken.
  - Added AC3b: a PUT that omits `mcp_source_ids` still keeps the surface, and the other ids still reset.
  - After the merge, the stored entry is popped (AC7), so any Save cleans it.
  - AC2 narrowed to the dead surface branches only.
  - `SURFACE_ROW_NAME` moves to `constants.py`, re-exported from `manage`, with a literal tool prefix pinned by a test.
  - Imports come from `constants` only.
  - `strip_surface_overrides(agent_store)` takes no `mcp_repo`, a deviation from flight DD4's suggested signature.
  - Added tests: mixed-list strip, marker-not-name in `override_for`.
  - Grep hits listed in the leg.
  - Flight Director call on the review's question: any non-empty dict entry is refused, `{"disabled_tools": []}` included.
  - These are clarifications with no structural change, so there is no second design-review pass. Leg status set to `ready`. [HANDOFF:review-needed]
- Implementation: the first Developer pass handed back partial, with the code done but the gates, falsification and log unfinished. The same Developer was resumed to finish rather than replaced, since it held the context. It then landed with every gate green. [LAND:leg]
- Flight review, run in parallel:
  - Reviewer (Sonnet, security tier): **[HANDOFF:confirmed]**, no issues. It re-ran 662 tests across 12 files and ruff, and checked own-vs-foreign carry, the raw-body 422 on both routes, marker-not-name spoofing, startup-strip safety, and that no write path stores a retired entry. One cosmetic over-long docstring line in `_reject_reserved_surface_name` is accepted.
  - Accessibility Reviewer (Sonnet): **[HANDOFF:confirmed]**, no blocking issues. Two non-blocking notes, both accepted: a deep link to a surface id now does nothing (already a known effect in DD1), and the empty-state title "No MCP sources registered yet." stays true for operator-registered sources.
- Leg 01 status set to `completed`. The flight is committed by a Developer (crew file: commit once per flight).

## Leg Progress

### Leg 01 `self-configuration-leaves-tools-tab`: landed (Developer, 2026-11-03)
**Implemented.** Server: `constants.py` (`SURFACE_ROW_NAME` moved here, `SURFACE_TOOL_PREFIX`, `override_for`); `manage.py` (`carry_surface_attachment`, `strip_surface_overrides(agent_store)`, `SURFACE_OVERRIDE_REFUSAL`; deleted `_migrate_override_key` and `reject_surface_credential_overrides`); `api.py` (`_normalize_surface_fields` on the raw body in create and update: 422, `disabled_tools` strip, carry incl. omitted `mcp_source_ids`; `_drop_surface_override` after the merge); `app.py` (guarded strip right after `reconcile_on_startup`); `mcp/_tool.py` (`is_platform_surface`); `override_for` at `_tool_provider.py`, `factory._build_source_index`, `projection.py`; factory MCP loop exempts surface tools. UI: `mcps-tab.js` skips every marked row (locked branch deleted), `agent-editor-selfconfig.js` dead branches removed, `self-configuration-tab.js` comment. Tests: new `tests/test_self_configuration_agent_writes.py` (36), a factory test, rewritten orphan/credential/reconcile/AC8 tests, browser tests updated, hint testid retired. Docs: `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md`, `docs/ui-testid-registry.md`.

**Grep hits (step 1, before edits).** `isSelfConfiguration` and the hint testid: `mcps-tab.js`; hint testid also `tests/browser/test_studio_self_configuration_tab.py:85`, `docs/ui-testid-registry.md`. `reject_surface_credential_overrides`: `api.py` (two calls), `manage.py`. `_migrate_override_key`: `manage.py`. `SURFACE_ROW_NAME`: `manage.py`, `api.py`, `test_self_configuration_write.py`, `test_self_configuration_api.py`. `mcp__self-configuration__`: only the behavior spec (steps 8-10, left by design). Orphan-via-PUT tests: the five named in the leg, all rewritten.

**Gates.** `THE_ONE_TEST_NETNS=1 make test-unit`: 8777 passed, 15 skipped. Static guards (`test_nav_helper`, `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_ui_ownership`, `test_ui_emitted_classes`, `test_ui_control_inventory`): 447 passed. `ruff check` clean, `ruff format --check` 825 files already formatted. Lane `agent-tabs`: 163 passed twice (the second after all source edits). Lane `agents`: 179 passed, 1 failed (`test_flow_agents_focus_after.py::test_form_is_clean_and_shows_the_stored_model_while_loading`, a model-picker loading-state timing assert, unrelated to this leg); it passed in isolation, and the whole file passed (14) on a re-run, so it is recorded as a timing flake.

**Falsification** (fix removed by edit, test failed, fix restored by edit): carry (`TestAttachmentCarry`, 4 failed): yes. 422 (`TestOverrideRefusal`, 7 params, plus the API credential test): yes. Factory exemption (`test_platform_surface_tools_ignore_disabled_tools_but_stubs_do_not`): yes. `override_for` at the projection site (2 failed): yes. Startup strip (5 failed): yes. Not falsified: the `disabled_tools` strip tests, `override_for` at the provider and index sites, `is_platform_surface`, the prefix pin, empty-entry drop, the omitted-key cleanup, and the browser tests.

---

## Decisions

---

## Deviations

---

## Anomalies
