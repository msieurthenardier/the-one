# Leg: uat-and-alignment

**Status**: ready
**Flight**: [Studio — Agent Builder](../flight.md)

## Objective

Interactive UAT session to verify all Studio acceptance criteria through hands-on browser testing, then fix any issues discovered.

## Context

- Legs 1-3 implemented the tools API, sidebar, and editor panel
- No browser testing has been performed yet — this is the first visual verification
- The server can be started with `the-one serve` and Studio accessed at `#studio`
- MCP sources and knowledge bases may need to be created via API first to test chip attachment

## Inputs

- `the_one/interfaces/web/api.py` — tools endpoint exists
- `the_one/interfaces/web/static/js/areas/studio.js` — full Studio area
- `the_one/interfaces/web/static/styles.css` — Studio CSS added
- Server starts without errors

## Outputs

- All acceptance criteria verified or issues fixed
- Any alignment tweaks (spacing, colors, interactions) applied
- Flight artifacts updated

## Acceptance Criteria

- [ ] Studio area loads when navigating to `#studio`
- [ ] Agent list populates from `GET /api/agents` (empty state shown if none)
- [ ] Create flow: click +, fill name + fields, click Create, agent appears in sidebar
- [ ] Edit flow: select agent, modify fields, Save button activates, save persists changes
- [ ] Tool toggles: populated from `GET /api/tools`, grouped by category, All/None works
- [ ] Tool persistence: disable tools, save, reload page, toggles reflect saved state
- [ ] MCP chip attachment: add/remove MCP sources, save persists `mcp_source_ids`
- [ ] KB chip attachment: add/remove knowledge bases, save persists `kb_ids`
- [ ] Delete flow: click Delete, red confirmation appears, second click deletes agent
- [ ] Dirty guard: modify a field, switch agents, confirmation dialog appears
- [ ] Empty state: delete all agents, "No agents yet" message shown
- [ ] Area switching: navigate Chat -> Studio -> Chat -> Studio, state preserved
- [ ] No console errors during normal operation

## Verification Steps

1. Start server: `the-one serve`
2. Open browser to the web UI, navigate to `#studio`
3. Walk through each acceptance criterion above, noting pass/fail
4. For each failure: diagnose, fix, re-verify
5. Check browser console for JS errors throughout
6. Verify API responses match UI state using browser devtools Network tab

## Implementation Guidance

This is a human-driven UAT leg. The implementing agent (Claude) assists by:

1. **Helping start the server** and confirming it's running
2. **Interpreting user reports** — when the user describes a bug or visual issue, diagnose from the code
3. **Making targeted fixes** — edit studio.js, styles.css, or api.py as needed
4. **Re-verifying** — confirm the fix addresses the reported issue
5. **Alignment tweaks** — adjust spacing, colors, or interactions per user feedback

Do not make speculative changes. Only fix what the user reports or what is clearly broken.

## Edge Cases

- **No MCP sources or KBs exist**: chip "Add" button should either show empty dropdown or do nothing gracefully
- **Very long agent names**: should truncate with ellipsis in sidebar
- **Special characters in agent name**: must not break HTML rendering (XSS via escapeHtml)
- **Rapid delete clicks**: timer-based confirmation should not stack or break
- **Network errors**: save/create/delete failures should show error message, not silently fail

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio.js` — bug fixes and alignment
- `the_one/interfaces/web/static/styles.css` — visual tweaks
- `the_one/interfaces/web/api.py` — only if API issues discovered

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)
