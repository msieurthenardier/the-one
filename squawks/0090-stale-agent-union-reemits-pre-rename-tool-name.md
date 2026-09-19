# Squawk 0090: a failed fresh-agent fetch re-emits a pre-rename `kb__` disable

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: —

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

(`the_one/interfaces/web/static/js/areas/studio.js:1795-1805`)

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

- `the_one/interfaces/web/static/js/areas/studio.js:1795-1797` — the `.catch` returning `agent`
- `:1804` — `self._selectedAgent = freshAgent`
- `:2340-2352` — `_storedUngatedDisabledNames()` reading `self._selectedAgent.disabled_tools`
- `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js` — the correct
  discipline for the sibling field (`data-kb-list-loaded`)
- `tests/browser/test_flow_studio_knowledge_attach.py:255` —
  `test_failed_fetch_shows_load_error_and_omits_kb_ids_from_save`, the sibling's net
- No test fails `GET /api/agents/{name}`; `test_flow_studio_knowledge_attach.py:279-281`
  fails only `**/api/knowledge-bases`

## Corrective Action

*(pending)* Apply DD-4's marker discipline: on a failed fresh-agent fetch, do not
seat the stale object as the union's source — suppress the union and omit
`disabled_tools` from the PUT entirely (the server's preserve-on-omit path then
keeps the stored value), or refuse the save with the load-failure state rendered.
Do not union from stale data.

## Verification

*(pending)* A browser test mirroring the sibling's: rename a knowledge base, stub
`GET /api/agents/{name}` to 500, open the editor, save, and assert the PUT does not
carry the pre-rewrite tool name.

## Sign-Off

*(pending)*
