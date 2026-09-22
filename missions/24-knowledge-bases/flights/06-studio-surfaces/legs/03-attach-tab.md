# Leg: attach-tab

**Status**: landed *(AC-15 met on re-verification. The behavior test's checkpoint 8 failed on 2026-09-18, the leg was reverted to `in-flight`, the defect was fixed, and checkpoint 8 re-ran PASS under the same single-process apparatus that exposed it — see `tests/behavior/kb-studio-round-trip/runs/2026-09-18-reverify.md`. One clause of that checkpoint is recorded as unexercisable at the rendered level, and one new finding — the counts-only invalidation signature — is carried forward as its own leg.)*
**Flight**: [Studio Surfaces](../flight.md)

## Objective

Replace the agent editor's Knowledge stub with the real attach surface, close
squawk 0050 and the `disabled_tools` save-time wipe on the client side, add the
rename affordance to the inventory, and run `kb-studio-round-trip` as the
combined regression evidence for everything this flight changed.

## Context

Client-side counterpart to Leg 2. **Every server change this leg depends on has
landed**: `kb_tool_names` on the single-agent responses (Leg 2 AC-6), the
`kb_ids` keep-on-omit (AC-7), and the rename `disabled_tools` rewrite (AC-8).

**Design decisions implemented**: DD-2 (attach-only tab), DD-3 (row toggles +
the rendered derived tool name, **read from `kb_tool_names`, never computed**),
DD-4's **client half** (the load marker and the omit rule), DD-13 (the
ungated-prefix `disabled_tools` union, from a freshly fetched agent), DD-15
(per-edit-mount knowledge-base refresh and the extended tab signature), and the
rename affordance DD-5 exists to make safe.

**Three fail-open paths close here, all in the same code block.** `squawk 0050`
(`data.kb_ids = []` on every save) and DD-13's `disabled_tools` wipe both live
in `collectFormData`, a handful of lines apart. Both fail *open*: the operator
loses an attachment, or a deliberately disabled tool silently switches back on.

**What this leg does NOT do**: no server changes. If something here seems to
need one, that is a `[BLOCKED:...]`, not a small edit — Leg 2 was reviewed twice
on the premise that the server surface is closed.

**Prior-leg learnings**: Leg 1 established the section's shape (chrome built
once plus an update handle, all data-derived DOM via `createElement`, three
poll-clear sites) and the **seven** `tests/test_ui_guards.py` invariants any new
Studio render code must satisfy — that table in `legs/01-knowledge-inventory.md`
under L1-D3 applies verbatim here and is not repeated. Leg 1 also added the
inventory's create form, whose 43-code-point advisory hint and empty-name
refusal the rename form reuses rather than reinvents.

## Inputs

- `static/js/areas/studio/knowledge-tab.js` — `renderKnowledgeTab(panel)`,
  a single `.empty-state` with `data-testid="agent-knowledge-tab-stub"`.
  Three assertions in `tests/browser/test_flow_agent_tabs.py` key off that id.
- `static/js/areas/studio/agent-editor.js:160` —
  `window.App.studio.renderKnowledgeTab(knowledgePanel)`, the sole caller; the
  MCPs tab beside it at `:164` already takes `(panel, agent, allSources,
  callbacks)`.
- `static/js/areas/studio/mcps-tab.js:142-143` —
  `checkbox.setAttribute('data-mcp-source-toggle', '')` +
  `setAttribute('data-mcp-source-id', source.id)`, DD-3's precedent.
- `static/js/areas/studio.js::collectFormData` —
  `data.disabled_tools` set in **all three** branches from
  `input[type="checkbox"][data-tool]`; `data.kb_ids = []` populated from
  `.chip-area[data-type="kb"] .chip`, a selector that matches nothing.
- `static/js/areas/studio.js::refreshMcpSourcesCache` — `.catch` keeps the
  **prior** cache (`self._allMcpSources || []`) and the promise always resolves.
- `static/js/areas/studio.js` — the edit-mount refresh at
  `Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache()])`, in
  **both** the select path and the new-agent path; and the
  `refreshMcpSourcesCache()` + `fetch('/api/agents/' + name)` + re-select
  pattern, DD-13's fresh-fetch precedent.
- `static/js/areas/studio/knowledge-section.js` (Leg 1) — the inventory,
  including the create form this leg's rename form mirrors.
- Leg 2's `kb_tool_names` on `GET`/`POST`/`PUT /api/agents/{name}` and
  `.../rename`, and **not** on `GET /api/agents`.

## Outputs

- `static/js/areas/studio/knowledge-tab.js` — rewritten as the real attach tab.
- `static/js/areas/studio/agent-editor.js` — extended call.
- `static/js/areas/studio.js` — `refreshKnowledgeBasesCache`, the load flag, the
  fresh agent fetch on edit mount, and `collectFormData`'s two fixes.
- `static/js/areas/studio/knowledge-section.js` — the rename affordance.
- `static/css/studio.css` — rows and the load-failure state.
- `docs/ui-testid-registry.md` — stub row retired, new rows added.
- `tests/browser/test_flow_agent_tabs.py` — three assertions re-pointed.
- `tests/browser/test_flow_studio_knowledge_attach.py` — NEW (`studio` lane).
- `tests/behavior/kb-studio-round-trip/runs/{ts}.md` — the run log, committed.

## Leg Design Decisions

**L3-D1 — One load flag, not a guessed one, and it is passed explicitly.**
The flag cannot be inferred from `allKnowledgeBases` being null or empty:
DD-15 requires keeping a populated **stale** array on failure, so a non-null
array says nothing about whether *this* refresh succeeded. Thread it as its own
value — `renderKnowledgeTab(panel, agent, allKnowledgeBases, callbacks)` with
`callbacks.knowledgeBasesLoaded` — rather than letting implementers invent
divergent plumbing. **This matches the established shape, it does not bend it**:
`renderMcpsTab` already threads a plain piece of state (`pendingSourceId`)
through its `callbacks` argument, and `agent-editor.js` builds a **new, smaller
object per tab** rather than forwarding the outer callbacks bag — do the same
here.
 `refreshKnowledgeBasesCache`
mirrors `refreshMcpSourcesCache` (keep the prior cache on failure — never blank
a populated one) **and additionally records whether *this* refresh succeeded**,
e.g. `self._knowledgeBasesLoaded = true` on the resolve path and `false` in the
`.catch`. That single flag drives both halves of the contract and is what
reconciles DD-4 and DD-15, which otherwise pull against each other:

- **DD-4**: `data-kb-list-loaded="true"` goes on the container **only when the
  flag is true**, and `collectFormData` sends `kb_ids` only when the marker is
  present. The `.catch` must leave it unset — the pattern being mirrored *always
  resolves*, so "set it when the promise resolves" would set it on failure and
  reproduce squawk 0050 through its own fix.
- **DD-15**: the cache keeps its prior contents for other consumers, but the tab
  **renders the load-failure state anyway when the flag is false** — it refuses
  to present stale attachment state as current. Rows from a stale cache plus an
  unset marker would let the operator toggle, save, see "Saved", and have nothing
  change.

**L3-D2 — The derived tool name is read, never computed.** Each row renders
`agent.kb_tool_names[kb.id]`. There is **no** fallback that derives a name in
JavaScript — not a slug, not a truncation, not the hash. A knowledge base with
no entry in the map (not attached, so the server did not resolve it) renders its
row with the tool-name slot showing an explicit "attach to see the tool name"
placeholder, or the row renders without the name; it does **not** guess. This is
DD-3's whole point: reproducing the sha256 discriminator, the 8→12→16 widening
and the budget-before-truncation rule in the browser is exactly the logic DD-5
and DD-17 argue is subtle enough to get wrong.

**L3-D3 — The `disabled_tools` union reads a freshly fetched agent.** DD-13's
union takes the built-in names from the checkboxes as today, then unions in the
stored entries whose names start with an `UNGATED_TOOL_PREFIXES` prefix
(`mcp__`, `kb__`). The stored entries must come from an agent fetched **on this
editor mount**, not from `self._agents`' cached object: `loadAll()` does not
re-run on a Studio section switch, so after a rename performed in the Knowledge
section the cached object still holds the pre-rewrite entry and the next save
would put it straight back — silently undoing Leg 2's AC-8. Add the agent
refetch to the **agent-select** edit-mount `Promise.all`, alongside
`refreshKnowledgeBasesCache()`.

**Fetching is not enough — the render must use what was fetched.** `doSelect`
assigns `self._selectedAgent = agent` **synchronously**, before its
`Promise.all` fires, and its `.then()` then calls `renderEditor(agent)` — the
outer closure parameter. A fetch added to that `Promise.all` without more would
retrieve the fresh agent and **silently discard it**: `collectFormData`'s union
would still read the stale `disabled_tools`, and DD-13's whole regression net
(AC-6, AC-12, behavior-test steps 13-14) would fail while looking implemented.
So the `.then()` callback must **reassign `self._selectedAgent` and the matching
entry in `self._agents`, and pass the fetched object to `renderEditor` — not the
outer `agent` variable.** The cited precedent
(`refreshMcpSourcesCache()` + `fetch('/api/agents/' + name)` + re-select) does
exactly this, but it is a *separate function* that re-enters `doSelect` with the
fresh object; it is not literally "a fetch inside `doSelect`'s own
`Promise.all`", so copying its shape without copying its reassignment is the
trap.

**The agent refetch goes into the select path ONLY.** `doEnterCreateMode` sets
`self._selectedAgent = null` — there is no agent to fetch. Only
`refreshKnowledgeBasesCache()` goes into both sites.

Three rules that are easy to miss and each break something:

- **All three branches.** `collectFormData` assigns `disabled_tools` in each of
  its three branches (`[]`, `[]`, `disabledNames`). The union applies to all
  three; fixing only the third leaves the wipe live for any agent whose tools are
  all on or mostly on.
- **Create mode is guarded.** The selected agent is `null` there, so an
  unguarded read crashes Save. A new agent has no stored entries, so the union is
  semantically a no-op — but it must be written as one, not assumed.
- **Stable append order.** The collected value feeds dirty-tracking, so append
  the stored ungated entries after the built-in names in a deterministic order.
  A `Set` iteration or an object-key walk makes the Save button flicker.

**L3-D7 — The fresh agent fetch degrades to today's behaviour; it never strands
the editor.** The `Promise.all` this fetch joins has **no rejection handler
anywhere in its call chain** — `doSelect` has no `.catch`, `selectAgent` chains
none, and both existing members are deliberately built to always resolve
(`refreshMcpSourcesCache` swallows into `self._allMcpSources || []`). A
rejecting member would mean `renderEditor`, `updateContentVisibility` and
`writeUrl_` never run: the editor panel stranded on whatever it last showed,
silently. The cited precedent is not safe to copy verbatim — its own callers in
`self-configuration-tab.js` chain a `.catch()` at the call site, and `doSelect`
has no equivalent.

**Decision**: give the fetch its own `.catch` that resolves with the **passed-in
`agent` object**, so the chain always resolves and the editor always renders;
set the freshness flag false; and render the Knowledge tab's load-failure state
(the same one DD-15 already specifies) so the degradation is visible rather than
silent. The union then re-emits from the cached agent.

Why this and not the alternatives, in the order they were ruled out:

1. **Omitting `disabled_tools` from the PUT is strictly worse, and that is
   measured, not assumed.** `update_agent` preserves only
   `self_revision_requires_approval` and `kb_ids` on omission, and
   `AgentConfig.disabled_tools` is `Field(default_factory=list)` — so omission
   wipes **every** disabled tool, built-ins included. It converts a narrow
   fail-open into a total one.
2. **Dropping just the ungated entries** is the same fail-open, wider.
3. **Blocking Save** fails *closed*, which is the direction this flight prefers —
   but it needs new machinery (a disabled Save plus its messaging) in a mission's
   last flight, to guard a conjunction of three conditions.
4. **A stranded editor is a certain, universal defect; a stale union is a
   conditional, narrow one.** Never trade the first for the second.

**Residual, recorded rather than hidden** — the same treatment DD-17's widening
loop and DD-5's partial-failure WARNING get: if a rename happened earlier in the
session **and** this refetch fails **and** the agent has a disabled `kb__` tool,
the stale name is re-emitted and that tool silently re-enables. Note what this
does and does not change: on that path the behaviour is **exactly today's**, so
the fresh fetch is a strict improvement that degrades to the status quo rather
than to something new. The load-failure state is the operator-visible signal.

**L3-D4 — `enabled_tools` is not touched, and `mcp_overrides` is not either.**
The union covers **top-level** `disabled_tools` only. The MCPs tab writes
per-tool disables to `mcp_overrides[source].disabled_tools`, a disjoint field, so
the union cannot resurrect anything that tab controls. Preserving top-level
`mcp__` entries set through the API is correct and is not new coupling.

**L3-D5 — Rename reuses the create form's validation, and refreshes what it
invalidates.** The inventory's rename control reuses Leg 1's 43-code-point
advisory hint and empty-name refusal rather than a second implementation. After
a successful rename the inventory re-fetches, because the derived tool name
every attached agent renders has just moved — and if an agent editor is mounted
its `kb_tool_names` is now stale. The editor is not open at the same time as the
Knowledge section (they are different Studio sections), so no cross-surface
invalidation is needed; the edit-mount refresh in L3-D3 is what makes the next
mount correct. **State that explicitly**, because it is the reason no
cache-busting event bus is needed here.

**L3-D6 — `agent-knowledge-tab-stub` is retired.** The tab root carries
`data-testid="agent-knowledge-tab"`. The three assertions in
`tests/browser/test_flow_agent_tabs.py` are re-pointed. **Two assert visibility
only; the third, `test_knowledge_tab_renders_stub`, asserts the stub's *text*
(`to_contain_text("Knowledge bases will be attached")`)** — a selector swap alone
leaves it permanently red, exactly as Leg 1 found with the inventory stub. That
test's content assertion is removed or replaced, and its name no longer describes
what it does, so rename it too.

## Acceptance Criteria

- [x] AC-1 — The agent editor's Knowledge tab lists every knowledge base with a
      toggle each, checked for those in the agent's `kb_ids`. The stub text and
      `data-testid="agent-knowledge-tab-stub"` are absent from the codebase.
- [x] AC-2 — Each row renders that knowledge base's derived tool name taken from
      the agent response's `kb_tool_names`. **No JavaScript anywhere derives a
      tool name**: `grep -rn "kb__" the_one/interfaces/web/static/js/` returns at
      most the single `'kb__'` prefix-test literal in `collectFormData`'s union —
      no concatenation, no slug, no hash, no truncation. (Today that grep returns
      **zero** occurrences, so the expected end state is exactly one line.) This
      is a read-and-judge criterion, not a scriptable pass/fail.
- [x] AC-3 — Toggling rows and saving writes exactly the checked ids to
      `kb_ids`; a loaded surface with zero checked rows still sends `[]`, which
      is a legitimate "detach everything".
- [x] AC-4 — Saving the agent from an **unrelated** tab leaves `kb_ids`
      unchanged (squawk 0050). Asserted at the API, not just in the UI.
- [x] AC-5 — When the knowledge-base fetch **fails**, the tab renders an explicit
      load-failure state — including when a prior cache is populated — the
      container carries **no** `data-kb-list-loaded` marker, and a save from that
      state **omits `kb_ids` entirely** so Leg 2's server-side preserve keeps the
      stored value.
- [x] AC-6 — A `kb__…__search` entry in `disabled_tools` survives a Studio save
      made from an unrelated tab, in **all three** of `collectFormData`'s
      branches (all tools on; a minority disabled; a majority disabled). Each
      branch asserted separately.
- [x] AC-7 — A top-level `mcp__` entry in `disabled_tools` survives the same
      save, and `mcp_overrides[source].disabled_tools` is unaffected.
- [x] AC-8 — **The un-disable path still works**: a `PUT /api/agents/{name}`
      sending a `disabled_tools` list that omits the `kb__` name removes it, and
      a subsequent Studio save does not re-add it. This is the inverse DD-13
      exists to preserve; a survival-only test would pass against a ratchet.
- [x] AC-9 — Creating an agent (create mode, no selected agent) saves without
      error and sends no stored-entry union.
- [x] AC-10 — A knowledge base created in the Knowledge section is present in the
      attach tab **in the same browser session, without a page reload** (DD-15).
- [x] AC-11 — A knowledge base can be renamed from the inventory. The advisory
      43-code-point hint and the empty-name refusal behave exactly as the create
      form's (empty refused client-side; over-length warned but accepted).
- [x] AC-12 — After a rename, reopening the agent editor shows the **new**
      derived tool name on the row, and the agent's `disabled_tools` still
      matches it — Leg 2's rewrite observed through this surface.
- [x] AC-13 — `tests/test_ui_guards.py` passes with **no new dynamic-sink
      entries** and a registry matching the sources in both directions; all seven
      invariants in `legs/01-knowledge-inventory.md` L1-D3 hold.
- [x] AC-14 — `make lint` clean, `make test-unit` green, `--lane studio` green
      including the new `test_flow_studio_knowledge_attach.py` and the re-pointed
      `test_flow_agent_tabs.py`.
- [x] AC-15 — **`kb-studio-round-trip` has been run and its run log committed** *(met on re-verification: the run of 2026-09-18-13-14-52 FAILED at checkpoint 8; the defect was fixed and checkpoint 8 re-ran PASS under the same single-process apparatus — see `runs/2026-09-18-reverify.md`)*,
      with every checkpoint passing or any failure explicitly dispositioned by
      the operator. (Run by the Flight Director via
      `/mission-control:behavior-test kb-studio-round-trip` — **not** by the
      implementing Developer.)

## Verification Steps

- AC-1, AC-2, AC-3, AC-9, AC-10, AC-11, AC-12: the new browser test, plus the
  AC-2 grep.
- AC-4, AC-6, AC-7, AC-8: browser test driving a real save and reading back via
  `GET /api/agents/{name}`. AC-6 needs three separate saves, one per branch.
- AC-5: browser test with the knowledge-base fetch stubbed to fail. The
  interception precedent is **`tests/browser/test_flow_studio_loadall_error.py`**
  — `page.route("**/api/knowledge-bases", …)` + `route.fulfill(status=500, …)`,
  whose glob matches the list endpoint exactly and leaves the other
  knowledge-base routes alone. (`test_flow_studio_knowledge_inventory.py` has no
  `page.route` call; an earlier draft cited it in error.) Assert the failure
  state and the absent marker. For the payload half — that `kb_ids` is **absent**
  from the PUT body — there is **no in-project precedent**: nothing under
  `tests/browser/` reads `post_data`. This leg establishes that pattern, using
  `route.request.post_data_json()` then `route.continue_()` (Playwright 1.58.0
  is pinned and supports both). Say so in the test's docstring so the next reader
  knows it is new rather than copied. **The route must filter on
  `route.request.method`**: L3-D3's new fresh-agent GET hits
  `/api/agents/{name}` — the *same path* as the save's PUT — so an unfiltered
  glob intercepts both and the body read fails intermittently in a way that looks
  like a product bug. `tests/browser/test_flow_studio_agent_save_race.py:60`
  already does exactly this method branch.
- AC-13: `PYTHON=.venv/bin/python bash scripts/run-tests.sh
  tests/test_ui_guards.py -x --timeout 30`.
- AC-14: `make lint`; `make test-unit` verbatim, alone, foreground;
  `PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane studio`.
- AC-15: Flight Director runs the behavior test after the Developer lands the
  code and the other criteria are green.

## Implementation Guidance

1. **`refreshKnowledgeBasesCache` + the load flag** (L3-D1), beside
   `refreshMcpSourcesCache`. It goes into **both** edit-mount `Promise.all`
   sites. The **fresh agent fetch (L3-D3) goes into the select path only** —
   create mode has no agent — and its `.then()` must reassign
   `self._selectedAgent` / `self._agents[i]` and render the **fetched** object,
   not the closure's `agent`.
2. **Rewrite `knowledge-tab.js`** to `(panel, agent, allKnowledgeBases,
   callbacks)`, mirroring `renderMcpsTab`. Row toggles carry `data-kb-toggle` +
   `data-kb-id`; the tool name comes from `agent.kb_tool_names` (L3-D2). Extend
   the `agent-editor.js` call. All data-derived DOM via `createElement` (L1-D3).
3. **`collectFormData`**: replace the dead `.chip-area[data-type="kb"] .chip`
   walk with `[data-kb-toggle][data-kb-id]:checked`, gated on the marker (DD-4);
   add the union to all three `disabled_tools` branches (L3-D3). Delete the dead
   selector rather than leaving it beside the new one.
4. **Rename in `knowledge-section.js`** (L3-D5), reusing Leg 1's validation.
5. **Re-point `test_flow_agent_tabs.py`**, checking each of the three assertions
   for a content assertion first (L3-D6).
6. **Gates**, then hand back. The Flight Director runs the behavior test.

## Edge Cases

- **An agent whose `kb_ids` holds a deleted knowledge base** (DD-14's dangling
  id): the tab renders only existing knowledge bases, so the id is simply not
  shown; the next save drops it. That is the decided behaviour, and the behavior
  test's step 18 asserts it — do not add code to "repair" it.
- **`kb_tool_names` missing a key** for an attached id that no longer resolves:
  render the row without a name, never a computed one (L3-D2).
- **Zero knowledge bases exist**: the tab renders an empty state **with** the
  marker set (the fetch succeeded), so a save correctly sends `kb_ids: []`.
  Distinguishing this from a failed fetch is exactly what L3-D1's flag is for.
- **The operator renames a knowledge base, then opens an agent editor that was
  already mounted earlier in the session** — the edit-mount refresh is what makes
  it correct (L3-D5); no event bus is needed because the two surfaces are
  different Studio sections and cannot be mounted simultaneously.
- **A save issued while the knowledge-base refresh is still in flight**: the
  marker is not yet set, so `kb_ids` is omitted and the server preserves. Correct
  by construction, but assert it rather than assuming it.
- **Rapid agent switching (select A, then B before A's fetch resolves)** — A's
  late `.then()` still fires and re-renders A's editor over B's. This is a
  **pre-existing race**, inherited from the unguarded `refreshMcpSourcesCache` /
  `refreshToolConfigsCache` chains, not introduced here; this leg adds one more
  concurrent write to it. **Do not fix it in this leg** — it is out of scope and
  a stale-then guard belongs with the others. Recorded so the Developer does not
  mistake it for a defect of their own making.
- **An agent with `disabled_tools` containing a `kb__` name for a knowledge base
  it is not attached to** — inert under DD-17 and preserved by the union. It must
  not crash the row renderer, which has no matching row for it.

## Citation Audit

Verified against the working tree on `flight/06-studio-surfaces` at the Leg 2
tip (Legs 1-2 uncommitted).

| Citation | Status |
|---|---|
| `static/js/areas/studio/knowledge-tab.js::renderKnowledgeTab` — takes `panel` only; renders one `.empty-state` with `data-testid="agent-knowledge-tab-stub"` | verified |
| `static/js/areas/studio/agent-editor.js:160` — `renderKnowledgeTab(knowledgePanel)`, sole caller; `:164` `renderMcpsTab(mcpsPanel, agent, callbacks.allMcpSources, {...})` is the signature precedent | verified |
| `tests/browser/test_flow_agent_tabs.py` — three `agent-knowledge-tab-stub` assertions (`:165`, `:214`, `:257`) | verified |
| `static/js/areas/studio/mcps-tab.js:142-143` — `data-mcp-source-toggle` + `data-mcp-source-id` (DD-3's precedent) | verified |
| `static/js/areas/studio.js::collectFormData` — `data.disabled_tools` assigned in **all three** branches from `input[type="checkbox"][data-tool]`; `data.kb_ids = []` then filled from `.chip-area[data-type="kb"] .chip`, which matches nothing (squawk 0050's mechanism) | verified |
| `static/js/areas/studio.js::refreshMcpSourcesCache` — `.catch` keeps `self._allMcpSources || []`; the promise always resolves (L3-D1's "set on success only" wording) | verified |
| `static/js/areas/studio.js` — edit-mount `Promise.all([refreshToolConfigsCache(), refreshMcpSourcesCache()])` appears in **two** paths (agent select and new-agent) | verified |
| `static/js/areas/studio.js` — `Promise.all([refreshMcpSourcesCache(), fetch('/api/agents/' + encodeURIComponent(name))])` then re-select: DD-13's fresh-fetch precedent | verified |
| `agent/config.py:15` — `UNGATED_TOOL_PREFIXES = ("mcp__", "kb__")` (L3-D3's prefix set) | verified |
| `interfaces/web/api.py::_agent_response` — returns `disabled_tools` byte-identical (only MCP credential keys masked), so the editor already holds stored ungated entries (DD-13's client-side feasibility) | verified |
| Leg 2 `api.py::_resolve_kb_tool_names` + `_agent_response(..., kb_tool_names=...)` — wired into the four single-agent routes, **not** the list route (L3-D2's read path; AC-2's premise) | verified |
| `legs/01-knowledge-inventory.md` L1-D3 — the seven `tests/test_ui_guards.py` invariants, applying verbatim to this leg's new render code | verified |
| `static/js/areas/studio.js::doSelect` — assigns `self._selectedAgent = agent` **synchronously** at `:1648`, then its `Promise.all().then()` calls `renderEditor(agent)` on the outer closure parameter (L3-D3's discard trap) | verified, cycle 1 |
| `static/js/areas/studio.js::doEnterCreateMode` — sets `self._selectedAgent = null`; no agent exists to refetch (L3-D3's select-path-only rule) | verified, cycle 1 |
| `tests/browser/test_flow_studio_loadall_error.py:42` — `page.route("**/api/knowledge-bases", …)` + `route.fulfill(status=500, …)`; `test_flow_studio_knowledge_inventory.py` has **no** `page.route` call (AC-5's corrected precedent) | verified, cycle 1 |
| `tests/browser/` — **no** occurrence of `post_data`/`postData` anywhere; AC-5's request-body assertion is a new pattern, not a reused one | verified, cycle 1 |
| `tests/browser/test_flow_agent_tabs.py` — of the three stub assertions, only `test_knowledge_tab_renders_stub` asserts text (`to_contain_text("Knowledge bases will be attached")`); the other two assert visibility (L3-D6) | verified, cycle 1 |
| `static/js/areas/studio.js::collectFormData` — the three `disabled_tools` branches are `allOn → []`, `enabledNames.length <= disabledNames.length → []`, `else → disabledNames`; all three reachable from the Tools tab (AC-6) | verified, cycle 1 |
| `static/js/areas/studio.js::doSelect` / `selectAgent` — **no `.catch` anywhere in the chain**; both existing `Promise.all` members are built to always resolve, so a rejecting member strands `renderEditor`/`updateContentVisibility`/`writeUrl_` (L3-D7's premise) | verified, cycle 2 |
| `static/js/areas/studio/self-configuration-tab.js` — the callers of the cited fresh-fetch precedent chain their own `.catch()` at the call site; `doSelect` has no equivalent, so the precedent is not safe to copy verbatim (L3-D7) | verified, cycle 2 |
| `interfaces/web/api.py::update_agent` — preserves **only** `self_revision_requires_approval` and `kb_ids` on omission; `agent/config.py:117` `disabled_tools: list[str] = Field(default_factory=list)`, so omitting it wipes every disabled tool including built-ins (L3-D7's ruled-out option 1) | verified, cycle 2 |
| `static/js/areas/studio/mcps-tab.js` / `agent-editor.js` — `renderMcpsTab` threads plain state (`pendingSourceId`) through `callbacks`, and `agent-editor.js` builds a new per-tab object rather than forwarding the outer bag (L3-D1's shape) | verified, cycle 2 |
| `tests/browser/test_flow_studio_agent_save_race.py:60` — `if route.request.method == "GET":` inside the route handler; the method-filter precedent AC-5 needs | verified, cycle 2 |
| Playwright **1.58.0** pinned in `pyproject.toml`; `Request.post_data_json()` exists in its Python sync API (AC-5's feasibility) | verified, cycle 2 |

---

## Post-Completion Checklist

- [x] All acceptance criteria verified except AC-15 (Flight Director runs it)
- [x] Tests passing (`make test-unit`; `--lane studio`)
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [x] Do NOT commit — the flight defers review and commit to Phase 2d
