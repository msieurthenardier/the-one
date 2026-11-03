# Sortie: Self-configuration leaves the Tools tab

**Status**: in-flight

## Charter

### Outcome
An agent's Tools tab no longer lists the Self-configuration server or its tools. The Self-configuration tab is the only place this is controlled, and when Agent prompt is on, the agent has all four of its tools.

### Why Now
Self-configuration now has its own tab with two items, Agent prompt and Routines, each with its own enable and approval switches. The locked row on the Tools tab and its per-tool checkboxes repeat that control, and they can contradict it: Agent prompt can read "on" while its write tools are unchecked on the Tools tab.

### Success Criteria
- [ ] With Agent prompt on, the Tools tab's MCP servers section shows no self-configuration tile and no tool rows from it. With no other servers, it shows the empty state.
- [ ] Saving the agent from any tab keeps self-configuration attached. The Self-configuration tab still reads on, and the agent still gets its four tools.
- [ ] An agent that had a self-configuration tool unchecked before this change gets all four tools again. The stored tool selection is cleared, and the API refuses a new one for that server with a 422, the same way it already refuses credential overrides on it.
- [ ] `CLAUDE.md`, `agents.md` and `SECURITY-MODEL.md` describe the Self-configuration tab as the only control. None of them still says the Tools tab governs the server.

### Constraints
- The Self-configuration tab is unchanged: its switches, approval queues and history stay as they are. So are the server's credential scoping and its four tools.
- The Routines item and its native tools are out of scope.
- No platform prompt text changes, so no eval run is needed.
- Agents saved before this change still load. Stale entries are cleaned up or ignored, never a load failure.

Charter agreed with the operator 2026-11-03, including the 422 and the restored tools (an agent can no longer be given the read tools without the write tools; see DD5).

---

## Pre-Flight

### Objective
Take the agent's own self-configuration server off the Tools tab and make the server, not the Studio form, the owner of everything about it on an agent: whether it is attached (set only by the Self-configuration tab's enable/disable routes) and which of its tools the agent gets (always all four). A Studio Save that no longer sees the tile must not detach it, a stored per-tool selection from before must stop applying and be removed, and the API must refuse a new one.

### Open Questions
- [x] What happens to existing stored per-tool selections for the server? → DD4 (cleared once at startup, ignored at every build site)
- [x] How does a Save keep the attachment once the tile is gone? → DD2 (the server carries it)
- [x] Do the drawer and API responses still list the server? → DD8 (unchanged)
- [x] HAT? → No (operator, 2026-11-03). The Flight Director runs the behavior test in Verification instead.

### Design Decisions

**DD1: The Tools tab shows no self-configuration row, the agent's own included.** `mcps-tab.js::visibleSources` drops every source whose `config.self_configuration` marker is an object (today it keeps the agent's own). The `locked` branch of `buildEntry` (the disabled master, the `mcp-source-self-configuration-hint-{id}` hint and its `describedBy`), `isSelfConfiguration`, the `entry.locked` term in `patchEntry`'s master update (line 273, called by `setAgent`), and the header comments that describe them are deleted. `setSources` no longer adds a tile when self-configuration is enabled. The editor's `fetchMcpSources` keeps `?include_agent_surfaces=1` (unchanged; the tab simply filters), so no other consumer is affected. `agent-editor-selfconfig.js::rebaseBaseline_` (lines 51-89) special-cases the surface id in `mcp_source_ids` and the `'self-configuration'` key in `mcp_overrides` when it rebases a dirty baseline; with the surface never in the DOM those branches are dead, so they are removed (or, if removal is riskier than it looks, their comments corrected) and `test_studio_self_configuration_dirty.py` re-run. Known effect: a deep link `#agents/{name}/tools/{S}` now targets a hidden tile, and `focusSource` does nothing; accepted, since nothing in the app produces that link any more.
- Rationale: the Self-configuration tab is the only control (charter). Filtering in the one function that builds the visible list removes the tile, its tool rows and its master in one place.
- Trade-off: none for the operator; the row carried no control they could use.
- UI approval: the Tools tab is not reshaped beyond one tile's absence, and the operator approved that outcome in the charter (criterion 1: no tile, the existing empty state when no other servers). No mockup is needed under squawk 0293's rule, since there is no new or reshaped layout.

**DD2: An agent write never changes the self-configuration attachment.** In `create_agent` and `update_agent` (`interfaces/web/api.py`), after the body is read and before validation, the incoming `mcp_source_ids` are normalized: any id that is the agent's **own** surface row is removed, and on update, if the stored agent has its own surface row attached, that id is put back **at its stored position**, `min(stored_index, len(incoming))` (so payload and response order stay stable and the position is deterministic). Write-side order: the DD3 raw-body check first, then the DD2 carry and the DD7 strip; a non-list `mcp_source_ids` or `disabled_tools` is left alone for validation to refuse. A foreign surface id is still refused by `reject_foreign_surface_attachments` (422, unchanged). The helper lives in `self_configuration/manage.py` beside the other surface guards (suggested name `carry_surface_attachment(name, incoming_ids, stored_ids, *, mcp_repo)`), so both routes call one implementation.
- **Consequence: a PUT can no longer make an orphaned surface.** An orphan (row present, not attached) now arises only from legacy data or a crash between steps. Five tests build that state with a PUT that drops the id and must instead build it with a direct `SQLiteAgentStore.save` (the pattern at `tests/test_self_configuration_surface.py:318-323`), **keeping every security assertion unchanged**: `tests/test_self_configuration_external.py::test_mint_on_orphaned_surface_is_409` (~152) and `::test_orphaned_surface_keeps_rows_but_still_resolves_registry` (~311); `tests/test_self_configuration_api.py::test_status_reports_orphaned_row_after_detach_via_put` and `::test_next_enable_after_orphan_reuses_the_row_not_a_duplicate` (~172-235); `tests/test_self_configuration_surface.py::test_orphaned_surface_refuses_ext_tool_call` (~447). A new unit test pins that a PUT can neither detach nor re-attach the agent's own row. `manage.status()`'s docstring (`manage.py:104-109`) and `agents.md` (~897, the orphan "via PUT" text; ~2344, "`update_agent` never re-adds the loopback id") are reworded to match.
- Rationale: once the tile is gone, Studio's Save builds `mcp_source_ids` from the checked `[data-mcp-source-toggle]` inputs (`agent-form-data.js:171-184`), which no longer include the surface, so a client-side rule would have to reconstruct a value the form never shows. A server-side carry keeps every client correct (Studio before and after a reload, API callers round-tripping a GET), and follows the precedent of M33 F2 DD5, where an agent PUT ignores the Routines switches and the response echoes the stored truth. It also closes the side path where a PUT could re-attach an orphaned surface row, leaving the enable/disable routes as the only way in or out (charter: the Self-configuration tab is the only control).
- Trade-off: a PUT that omits the surface id no longer detaches it. That was never a supported way to disable the surface (the DELETE route also deletes the row, unregisters the credential and clears external credentials); the old behaviour left an orphaned row.

**DD3: The API refuses any `mcp_overrides` entry for the self-configuration server.** `create_agent` and `update_agent` return 422 when the **incoming** `mcp_overrides` is a dict containing the key `SURFACE_ROW_NAME` (`"self-configuration"`) with a **non-empty** entry (tool lists, credentials, anything). An empty `{}` or `null` entry is treated as absent and dropped, so a Studio page loaded before the upgrade (whose old `mcps-tab.js` sends `{"self-configuration": {}}` once the tile was expanded) still saves. Known effect: a pre-upgrade page that had a surface tool unchecked gets the 422 until it is reloaded. The check runs on the raw body **before** `_merge_preserved_mcp_credentials`, because the merge re-injects a stored entry the body omitted (`api.py:355-357`), so a post-merge check would refuse innocent Saves. The detail is one plain sentence, e.g. "The self-configuration server can't be set per agent. Turn Agent prompt on or off on the Self-configuration tab." `reject_surface_credential_overrides` is subsumed and removed (its credential case is a special case of this rule); its tests are kept, re-pointed at the new message.
- Rationale: the name is reserved for the platform (`api.py:3316-3327` refuses an ordinary source by that name with 409; legacy `"self-configuration (<agent>)"` rows are renamed at every startup), so the key always means the surface. Refusing the whole entry, not only tool lists, leaves nothing per agent to configure on it, which matches the charter.
- Trade-off: a client that round-trips a GET containing a stored surface entry would get a 422. DD4 removes every stored entry at startup before the app serves, so a GET no longer returns one.

**DD4: Stored selections are removed once at startup and ignored at every build site.**
- *Startup cleanup*: a **new, separate** function `manage.strip_surface_overrides(agent_store, mcp_repo)`, called from the lifespan in its **own** try/except **immediately after** `reconcile_on_startup` (`app.py:381`), inside `_self_configuration_session_scope`, before `_state["factory"]` is installed and before the connector and routine startup. So no agent build runs before it, and the credential-registry reload (`load_from_rows`) never depends on it. The outer try/except also covers a failing `mcp_repo.list()` before the agent loop. Its order relative to `cleanup_copied_overrides` (a different field, run earlier) does not matter. It follows the house pattern of `override_cleanup.cleanup_copied_overrides` and `repair_unsafe_names`: it scans **every** agent, wraps each agent in try/except with a WARNING (an `mcp_overrides` column that cannot be decrypted makes `SQLiteAgentStore.load` raise, `repositories.py:142-153`), and never raises. For each agent it removes the `"self-configuration"` key from `mcp_overrides` and removes `mcp__self-configuration__*` entries from `disabled_tools` (DD7). It saves through `SQLiteAgentStore.save` (encrypted column, never a raw `UPDATE`) only when something changed, and logs one INFO line per changed agent. Every agent is scanned, not only owners of marked rows, because `manage.disable` drops the attachment but leaves `mcp_overrides` untouched. It still runs before the app serves, so the Divert criterion holds. Legacy `"self-configuration (<agent>)"` keys are **not** removed: they match no source since the rows were renamed, so they are already inert at build, and the prefix is not reserved (an ordinary server named `self-configuration (docs)` is legal). `_migrate_override_key` is deleted (no point moving a key that is ignored); `reconcile_on_startup`'s row rename stays, and its two migration tests are rewritten to assert that the rename still happens and the override key is left alone. Known effects, harmless and accepted:
  - A leftover legacy key (present only where the old migration was skipped) stays stored, and GET still returns it.
  - `_warn_orphan_overrides` (`_tool_provider.py:193-206`) logs a WARNING for that key on every build.
  - Each agent the strip changes gets a new `updated_at`, once (`repositories.py:251-300` sets it on every save).
- *Unsupported state*: a **non-surface** MCP row named exactly `self-configuration` is unsupported (Architect review 2). Such a row exists only if created before the M21 F01 L03 reservation. It already collides with the surface's prefixed tool names, and `_tool_provider.py`'s first-source-wins check drops one source's tools. DD3, the DD4 strip and DD7 all treat the key and the `mcp__self-configuration__` prefix as the surface, with no carve-out.
- *Build-time ignore*: one helper, `override_for(overrides, source)` in the leaf `self_configuration/constants.py` beside `is_surface_row`, returns `None` for a surface row and `overrides.get(source.name)` otherwise. The three read sites call it: `mcp/_tool_provider.py:280` (the tools the agent actually gets), `agent/factory.py:169` (the `search_tools` index) and `self_configuration/projection.py:154` (what `describe_my_capabilities` reports).
- Rationale: the cleanup makes stored data match the rule, so GET responses and Studio show the truth. The ignore makes the rule hold whatever state the data is in (an older database restored, a copy saved before the restart), at three call sites that already exist, using one function.
- Trade-off: two mechanisms for one rule. The ignore is three one-line changes; the cleanup is what clears the data and lets DD3 refuse with no false positives.

**DD5: The per-tool way to withhold the write tools goes away; approval mode is the gate.** Today `SECURITY-MODEL.md` lists the per-tool checkboxes as a standing mitigation for prompt injection when approval mode is off ("withhold `update_my_description` / `update_my_system_prompt` from a specific agent"). After this sortie the mitigations are approval mode (recommended) or turning Agent prompt off. The operator accepted this in the charter. The leg rewrites that paragraph and the "nothing gates the write tools beyond the existing per-source/per-tool checkboxes" sentence.
- Rationale: an agent that can read its configuration but not write it was the only thing the checkboxes offered over the item switch. The operator judged that not worth a second, contradictory control.
- Trade-off: that read-only posture is no longer available.

**DD6: The hint testid is retired.** `mcp-source-self-configuration-hint-` moves from `docs/ui-testid-registry.md`'s live table (line 602) to its "Retired testids" table, and is added to `RETIRED_SELECTORS` in `tests/test_nav_helper.py` (`test_retired_selectors_cover_the_registry_retired_table` requires both).

**DD7: `AgentConfig.disabled_tools` cannot withhold a self-configuration tool either.** There is a second per-tool path: `factory.py:486-487` registers an MCP tool only if `config.is_tool_enabled(tool.name)`, and `is_tool_enabled` treats `disabled_tools` as a blacklist for `mcp__` names (`agent/config.py:181-197`). So a PUT with `disabled_tools: ["mcp__self-configuration__update_my_description"]` would still withhold a write tool, against the charter. Rule:
- On write (`create_agent`/`update_agent`), `mcp__self-configuration__*` entries are **stripped silently**, not refused, because Studio re-sends stored ungated names on every Save (`agent-form-data.js` `_storedUngatedDisabledNames`).
- At startup, `strip_surface_overrides` removes them (DD4).
- At build, the factory skips the whole `disabled_names` / `is_tool_enabled` conjunction at `factory.py:486-487` for tools whose source is a surface row, never keying on the name prefix:
  - `MCPClientTool` gains a public read-only boolean `is_platform_surface`, set in `__init__` from `is_surface_row(effective_source)`. `_effective_source` keeps the source's `config`, so the marker survives `_apply_override` (`_tool_provider.py:143-167`).
  - The factory reads it with `getattr(tool, "is_platform_surface", False)`. That way injected stubs, such as `tests/test_factory.py`'s `StubMCPProvider` returning plain `StubTool`s, keep the old behaviour, and a unit test pins that fallback.
  - No other site applies `disabled_tools` to MCP tools. Architect review 2 checked the `search_tools` index, the projection, and the drawer and Tools tab counts.
- `rename_references.py` needs no change: it never renames the surface, whose name is reserved.
- The operator-wide global tool switches (Settings › Built-in tools) do not cover MCP tools, so nothing else applies.
- Rationale: the charter says the agent has all four tools whenever Agent prompt is on, and DD5 says the per-tool withhold goes away. Leaving an API-only path would contradict both.

**DD8: Other surfaces are unchanged.** `GET /api/agents/{name}` still lists the surface id in `mcp_source_ids` (it is a real attachment, and the Self-configuration status reads it); `GET /api/mcp-sources?include_agent_surfaces=1` still returns the rows. The chat drawer already skips the surface in its MCP servers group (`agent-drawer.js:559`) and shows its own Self-configuration On/Off group; neither changes.

### Citation Audit

Verified against the working tree at `503d9751`:

| Citation | Status |
|---|---|
| `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js::visibleSources` (lines 73-85) keeps the agent's own marked row and drops other agents' | verified |
| `mcps-tab.js::buildEntry` `locked` branch (lines 138-214): disabled master, hint `mcp-source-tile-self-configuration-hint` / testid `mcp-source-self-configuration-hint-{id}`; `patchEntry` (called by `setAgent`) forces the master on for `entry.locked` (line 273) | verified |
| `agent-form-data.js:171-184` builds `mcp_source_ids` from checked `[data-mcp-source-toggle][data-mcp-source-id]` inputs once sources are loaded, else carries the stored list | verified |
| `agent-form-data.js` dirty state is a DOM snapshot comparison (`state.dirty = current !== state.snapshot`, line 33), so a server-carried id cannot make the editor permanently dirty | verified |
| `api.py::update_agent` (from 1240) merges `mcp_overrides` via `_merge_preserved_mcp_credentials` before `AgentConfig.model_validate`; the merge keeps a stored source entry the body omits (`api.py:355-357`) | verified |
| `api.py::update_agent` precedent: `routines_self_config_enabled` / `routines_require_approval` always take the stored value (M33 F2 DD5) | verified |
| `manage.py::reject_foreign_surface_attachments` and `reject_surface_credential_overrides` run on the validated, merged config in both `create_agent` (~1217) and `update_agent` (~1309) | verified |
| Override read sites keyed by `source.name`: `mcp/_tool_provider.py:280`, `agent/factory.py:169`, `self_configuration/projection.py:154` | verified |
| `manage.py::reconcile_on_startup` runs on every startup (`app.py:381`) and `_migrate_override_key` saves through `agent_store.save` | verified |
| `manage.py::disable` (225-290) detaches and deletes the row but does not touch `mcp_overrides` | verified |
| `SURFACE_ROW_NAME = "self-configuration"` is shared by every surface row, and an ordinary source by that name is refused with 409 (`api.py:3316-3327`) | verified |
| `constants.py::is_surface_row` is a leaf predicate on `source.config["self_configuration"]` | verified |
| Tests pinning the old behaviour: `tests/browser/test_studio_self_configuration_tab.py::test_enable_shows_locked_row_on_mcps_tab`, `tests/browser/test_studio_mcps_tab.py` (~1105-1200: enable-then-save keeps the surface; own-vs-foreign tile), `tests/test_self_configuration_surface.py::TestAC8PerToolControlThroughExistingMachinery`, `tests/test_self_configuration_api.py` (`test_credential_override_on_a_surface_row_is_rejected`, the two reconcile migration tests at 588 and 633), plus the five orphan-via-PUT tests listed under DD2 (added after Architect review 1) | verified |
| `agent/factory.py:486-487` registers an MCP tool only when `config.is_tool_enabled(tool.name)`; `agent/config.py:181-197` blacklists `mcp__` names in `disabled_tools` (DD7; Architect review 1) | verified |
| `lifespan` calls `reconcile_on_startup` with no try/except (`app.py:381`); `SQLiteAgentStore.load` raises on an undecryptable `mcp_overrides` (`repositories.py:142-153`) (DD4; Architect review 1) | verified |
| `MockProvider` returns the same `response.tool_calls` on every call (`llm/mock.py` `complete`), so a scripted tool call repeats until `max_iterations` | verified |

### Prerequisites
- [x] No open mission or sortie overlaps (all 34 missions and sorties 01-07 completed).
- [x] Behavior-test apparatus: browser (goldfinch MCP, registered in this session) to act on and observe the Tools tab, and shell `curl` for API reads. Read paths: `GET /api/agents/{name}` (`mcp_source_ids`, `mcp_overrides`), `GET /api/agents/{name}/self-configuration` (`enabled`), `GET /api/agents/{name}/self-configuration/revisions` (a revision row proves a write tool ran). Re-verify that goldfinch is registered at run time.
- [x] Mock provider tool calls work with dev mode on (`CLAUDE.md` "Mock provider `config` options").

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
One leg, because the UI removal is unsafe without the server carry (DD2) and the server rules are small:

1. **Server** (`self_configuration/manage.py`, `constants.py`, `interfaces/web/api.py`, `interfaces/web/app.py`, `mcp/_tool_provider.py`, `agent/factory.py`, `self_configuration/projection.py`): the attachment carry (DD2), the raw-body 422 replacing the credential guard (DD3), `override_for` at the three read sites, `strip_surface_overrides` in its own guarded lifespan call and the deletion of `_migrate_override_key` (DD4), and the `disabled_tools` strip and build-time skip (DD7).
2. **Tools tab** (`mcps-tab.js`, `agent-editor-selfconfig.js`): filter every marked row, delete the locked branch and its comments (DD1), and drop the dead surface branches in `rebaseBaseline_`. No CSS rule or catalogue row exists for `.mcp-source-tile-self-configuration-hint` (checked by Architect review 1), so no ownership or emitted-class guard is involved.
3. **Tests**: unit tests for the carry (own id kept at its stored position; a PUT can neither detach nor re-attach the own row; a foreign id still 422), the 422 (tool list, credential; create and update; an empty `{}`/`null` entry is dropped, not refused; a Save omitting the key with a stored entry is not refused), the `disabled_tools` strip on write, `override_for` at all three sites and the factory's `disabled_tools` skip, including the injected-stub `getattr` fallback (a stored `mcp_overrides` or `disabled_tools` withhold on the surface leaves all four tools registered), and `strip_surface_overrides` (owner; a disabled agent with a leftover entry; a legacy-named key is left alone; an agent with nothing to change is not re-saved; one agent whose column cannot be decrypted is skipped with a WARNING and the rest are cleaned). Rewrite the pinned tests in the Citation Audit, building orphans by direct store save and keeping their security assertions. Browser: the Tools tab shows no surface tile (and the empty state) with self-configuration on; enable, then Save from General and from Tools, and the surface stays attached. **Browser negative assertions must not spell the retired testid** (`test_no_retired_selectors_in_browser_tests` scans every browser file): assert absence through `[data-source-id="{S}"]` or `mcp-source-row-{S}`.
4. **Docs**:
   - `CLAUDE.md` "Self-configuration surface" paragraph: drop "the operator's existing per-source and per-tool checkboxes on the Tools tab govern it ... the row there is locked checked+disabled".
   - `the_one/agents.md`: ~887 ("per-source/per-tool controls ... govern it for free"), ~897 (orphan via PUT), ~905 ("the operator's per-tool checkboxes on the Tools tab show all four"), ~913 ("Reachable only through the confined surface", per-tool operator controls), the reconcile/LD7 notes, and ~2344 ("`update_agent` never re-adds the loopback id").
   - `SECURITY-MODEL.md`: the "Ownership is enforced server-side" bullet (~275-285: the 422 now covers any non-empty entry, plus the attachment carry) and the injection paragraph (~286-310, DD5).
   - `docs/ui-testid-registry.md` (DD6).
   - Comments and docstrings: `self-configuration-tab.js` header (lines 8-11); the `SURFACE_ROW_NAME` comment in `manage.py` (41-55) and `_reject_reserved_surface_name`'s docstring in `api.py` (~3314), both "mirrored in `mcps-tab.js`"; `reconcile_on_startup`'s LD6/LD7 bullets; `manage.status()` (104-109).

### Checkpoints
- [ ] Server carries the attachment and refuses surface overrides (unit tests green)
- [ ] Stored selections removed at startup and ignored at build (unit tests green)
- [ ] Tools tab shows no surface tile; browser tests green on the `agents`, `agent-tabs` and `routing` lanes as touched
- [ ] Docs updated; `make test-unit` and the touched browser lanes green

### Adaptation Criteria

**Divert if**:
- Something other than the Tools tab relies on per-agent overrides of the surface (for example, a test seam or the external-access path reading `mcp_overrides["self-configuration"]`).
- The startup removal cannot run before the app serves requests.

**Acceptable variations**:
- Helper names and file placement within `self_configuration/`.
- The exact wording of the 422 sentence, if it stays one plain sentence naming the Self-configuration tab.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `self-configuration-leaves-tools-tab` - Server carry, 422, startup removal and build-time ignore; Tools tab filter; tests; docs

No HAT leg (operator, 2026-11-03).

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Behavior test `self-configuration-off-tools-tab` passed

### Verification
- `make test-unit`; the browser lanes holding the changed files (`agent-tabs` for `test_studio_self_configuration_*`, `agents` for `test_studio_mcps_tab.py`) through `scripts/run-tests.sh` with `THE_ONE_TEST_NETNS=1`.
- The Flight Director runs `/mission-control:behavior-test self-configuration-off-tools-tab` against a scratch dev instance built from the sortie branch. It seeds a legacy stored selection, restarts, and checks every charter criterion through the browser and the API, including a real call to a write tool that the old selection had disabled.
