# Squawk 0090: a failed fresh-agent fetch re-emits a pre-rename `kb__` disable

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-09-19

## Report

Opening an agent in Studio issues a fresh `GET /api/agents/{name}` specifically so
`collectFormData`'s ungated-prefix union reads a **post-rename** `disabled_tools`
(M24 F06 L03, L3-D3). Its failure handler returns the stale cached object:

```js
.catch(function () {
  return agent;          // the STALE cached agent
})
...
var freshAgent = results[3];
self._selectedAgent = freshAgent;
```

(`the_one/interfaces/web/static/js/areas/studio.js:1826-1838`)

So one transient failure on that GET seats the stale agent as
`self._selectedAgent`. `_storedUngatedDisabledNames()` (`studio.js:2340-2352`)
then unions the **pre-rewrite** `kb__{old_slug}__{hash}__search` back into the PUT,
and the server stores it — overwriting the correct post-rename entry that
`rename_kb_tool_references` had already written. The stale name matches no live
tool, so **a tool the operator deliberately disabled silently re-enables**. That is
precisely the failure DD-5 and DD-13 exist to prevent, reachable through one failed
fetch.

**The flight already decided the opposite for the sibling field, and wrote down
why.** DD-4 argues at length that a `catch` "must leave the marker unset and render
the load-failure state — 'set it when the promise resolves' would set the marker on
the failure path and reproduce the very defect this closes."
`knowledge-tab.js` implements that discipline for `kb_ids` via a
`data-kb-list-loaded` success marker, and
`test_flow_studio_knowledge_attach.py:255` pins it. The identical reasoning was
never applied to `disabled_tools`.

Sharpening the irony: the comment immediately below this `.catch`
(`studio.js:1799-1802`) warns that failing to reassign would mean "the union below
silently keeps reading stale disabled_tools." It diagnosed the hazard for the
success path; the failure path reintroduces it.

**Mitigating**: `renderEditor(freshAgent)` renders the same stale object, so the UI
is self-consistent — the operator is not shown one name and sent another. Over
loopback the GET rarely fails. **Aggravating**: when it does fire there is no error,
no UI affordance to notice it, and no way to undo it; and this is a
tool-authorization surface, where the flight's own risk tiering notes every defect
class fails open.

## Evidence

- `the_one/interfaces/web/static/js/areas/studio.js:1826-1830` — the `.catch` returning `agent`
- `:1838` — `self._selectedAgent = freshAgent`
- `:2350-2363` — `_storedUngatedDisabledNames()` reading `self._selectedAgent.disabled_tools`
- `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js` — the correct
  discipline for the sibling field (`data-kb-list-loaded`)
- `tests/browser/test_flow_studio_knowledge_attach.py:255` —
  `test_failed_fetch_shows_load_error_and_omits_kb_ids_from_save`, the sibling's net
- No test fails `GET /api/agents/{name}`; `test_flow_studio_knowledge_attach.py:279-281`
  fails only `**/api/knowledge-bases`

## Corrective Action

DD-4's marker discipline applied to `self._selectedAgent`, taking the **second** of
the two shapes the report offered: **refuse the save** with the load-failure state
rendered. The first shape — omit `disabled_tools` from the PUT and let a server-side
preserve-on-omit keep the stored value — was checked against the code and rejected:
**that path does not exist for this field.** `update_agent`
(`the_one/interfaces/web/api.py:886-893`) preserves exactly three fields on
omission — `mcp_overrides`, `self_revision_requires_approval`, `kb_ids` — and
`AgentConfig.disabled_tools` is `Field(default_factory=list)`
(`the_one/agent/config.py:117`), so an omitted `disabled_tools` validates to `[]`
and **wipes every disabled tool**, built-in ones included: a strictly worse
fail-open than the defect. Adding a fourth preserve would be a server-side
omission-semantics change — out of this squawk's scope by its own gate.

Changes, all in the agent-editor surface:

- `the_one/interfaces/web/static/js/areas/studio.js`
  - New per-instance flag `self._selectedAgentLoaded`, the direct analogue of
    DD-4's `self._knowledgeBasesLoaded`. Initialised `true` (nothing selected →
    nothing stale); set `false` at the top of `doSelect` (so a save racing the
    in-flight refresh is blocked too) and resolved from the fresh-agent fetch's
    outcome — the `.catch` now records `freshAgentLoaded = false` alongside
    returning the stale `agent`. `doEnterCreateMode` and `doHandleBack` set it
    `true` (create-mode has no stored entries to union — AC-9).
  - `renderEditor` renders an `agent-load-error` affordance when the flag is
    `false`, mirroring the sibling `agent-knowledge-load-error`'s wording and
    treatment. Built with `createElement` + `textContent`, so
    `tests/test_ui_guards.py`'s dynamic-sink baseline is untouched.
  - `checkDirty` keeps Save disabled while the flag is `false`. Cancel is
    deliberately **not** gated — discarding edits is always safe.
  - `save()` carries the same guard as a second line of defence (a scripted or
    keyboard-driven click, or a save that races the refresh, still reaches it) and
    writes the refusal into `.editor-error` instead of issuing the PUT.
- `the_one/interfaces/web/static/css/studio.css` — one `.area-studio
  .agent-load-error` rule, existing tokens only, identical treatment to the
  sibling's load-error line.
- `docs/ui-testid-registry.md` — registers `agent-load-error`.

**Deliberately unchanged**: `renderEditor(freshAgent)` still renders the stale
object (L3-D7's trade-off — an unhandled rejection would strand the editor with
nothing rendered), so the UI stays self-consistent: the operator sees the same
values the union would have read, plus an explicit statement that they may be out
of date and that saving is off. `_storedUngatedDisabledNames()` is untouched —
suppressing the union itself would emit a `disabled_tools` missing its ungated
entries, which is DD-13's wipe.

## Verification

New browser test —
`tests/browser/test_flow_studio_knowledge_attach.py::test_failed_agent_fetch_refuses_save_instead_of_reemitting_stale_disabled_tool`,
modelled on the sibling `test_failed_fetch_shows_load_error_and_omits_kb_ids_from_save`:
attach a knowledge base, disable its derived tool via the API, mount the editor
healthy (so the in-page caches hold the pre-rename entry), rename the knowledge base
out-of-band, then fail `GET /api/agents/{name}` and re-select the agent. Asserts the
`agent-load-error` affordance is visible; Save is disabled while the form is dirty
(Cancel is not); forcing the button live and clicking exercises `save()`'s own guard,
which surfaces the refusal and issues **no PUT at all**; and the stored
`disabled_tools` still holds only the post-rename name. The route handler dispatches
on `route.request.method` because the failing GET and the observed PUT share a path —
the same reason the sibling's handler does.

Gates, all green over the final tree: `ruff check` + `ruff format --check`
(all checks passed; 449 files already formatted); `tests/test_ui_guards.py`
(14 passed); `make test-unit` (4769 passed, 10 skipped, 594 deselected);
`scripts/run-tests.sh --lane studio`.

## Sign-Off

*Traced all 13 `self._selectedAgent` assignment sites — the flag is correctly reset on the one path that can seat a stale post-fetch object (`doSelect`'s `.catch`), and every other assignment site is safe by construction (null-outs with no live save surface, or post-confirmed-save results). Independently confirmed the rejected "omit from PUT" alternative would wipe all disabled tools via `update_agent`'s preserve-on-omit list and `AgentConfig.disabled_tools`'s empty-list default. New browser test passed as part of the green studio lane. Approved.*

**Reviewer**: independent Reviewer agent, turnaround batch 2026-09-19.

> Prior pending note, kept for the record:
>
> *(pending)*
> 
> ## Reporter's Error, Recorded
> 
> This squawk's original Corrective Action proposed two options and named the wrong
> one first: *"omit `disabled_tools` from the PUT entirely (the server's
> preserve-on-omit path then keeps the stored value)."* **That path does not exist
> for this field.** `update_agent` (`the_one/interfaces/web/api.py:886-893`)
> preserves exactly three fields on omission — `mcp_overrides`,
> `self_revision_requires_approval`, `kb_ids` — and
> `AgentConfig.disabled_tools` is `Field(default_factory=list)`
> (`the_one/agent/config.py:117`), so an omitted `disabled_tools` validates to `[]`
> and wipes **every** disabled tool, built-ins included. Following the suggestion
> would have converted a narrow fail-open reachable by a failed fetch into a total
> one reachable the same way.
> 
> The implementing Developer checked the claim instead of taking it, rejected it,
> and took the second option (refuse the save). Adding a fourth preserve clause was
> correctly declined as a server-side omission-semantics change and therefore out of
> squawk scope — which is the boundary the debrief already recommends turning into a
> named `PATCH`-vs-`PUT` design decision rather than a fifth special case.
> 
> Recorded because the squawk format invites a confident corrective action from the
> reporter, and a reporter who has not read the server path can make that confidence
> load-bearing. The Evidence citations above were also ~10 lines stale against the
> tree at implementation time and have been corrected.
