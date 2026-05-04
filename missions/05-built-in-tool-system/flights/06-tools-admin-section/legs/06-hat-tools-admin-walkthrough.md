# Leg: 06-hat-tools-admin-walkthrough

**Status**: landed
**Flight**: [Tools Admin Section](../flight.md)

## Objective

Human Acceptance Test of the F6 admin + Studio surfaces. Operator drives 9 scenarios end-to-end through the running container; Flight Director guides one step at a time, fixes UX issues inline (spawning a Developer agent for code changes), and re-verifies each step before advancing. No autonomous implementation in this leg — only fixes triggered by HAT findings.

## Context

- **F6 Decision 12** (two-Reviewer-pass batching): L6 commits no docs. Inline fixes from HAT findings count as part of the batched L0-L5 changes; the Reviewer pass over the L0-L8 batch will see them.
- **F5 debrief recommendation**: HAT scenarios are per-FLOW (one operator UX path), not per-bug. 9 scenarios cover: admin grid (1), grid toggle (2), per-tool editor save (3), test buttons web_search (4) + fetch_url (5), Studio disabled-tool surfacing (6), re-enable preserves agent state (7), agent override Narrow list (8), agent override NarrowSuperset locked chips (9).
- **Container expected to be running** — the L0 Makefile changes mean `make rebuild` no longer runs `_ensure-playwright`; the L0-L5 implementation has been rebuilt during prior leg verifications.

## Scenarios

1. **Admin grid renders 19 tiles**. Navigate to `http://localhost:8484/#admin/tools`. Verify: 19 tiles render alphabetically by tool name; each shows a category badge (filesystem/execution/python/web), name, description, and an enabled-state toggle (on by default).

2. **Grid toggle persists across reload**. Toggle `web_search` from enabled → disabled via the grid. Reload the page. State persists (toggle remains off).

3. **Per-tool editor save flow**. Click on the `web_search` tile (or directly load `#admin/tools/web_search`). Editor opens. Narrow `timeout_seconds_max` from default to `10`. Click Save. Refresh page. Values persist.

4. **`web_search` test button**. With editor open, click "Test connection". Result panel shows the parsed `SearchResult` list (`✓ Returned (Nms)`) OR `No results found.` if DDG rate-limits.

5. **`fetch_url` test button**. Navigate to `#admin/tools/fetch_url`. Click "Test connection". Result panel shows readability-extracted markdown of `https://example.com/`.

6. **Studio disabled-tool surfacing**. Open Studio → select an agent (e.g., Haiku45) → Tools tab. Confirm `web_search` (still disabled from step 2) renders with strikethrough name + dim row + "Disabled by operator" tooltip + un-clickable checkbox.

7. **Re-enable preserves agent state**. Re-enable `web_search` via `#admin/tools` grid. Refresh Studio Tools tab. Row is interactive again; agent's prior on/off state preserved.

8. **Narrow list override**. In Studio Tools tab, expand `http_request`'s "Narrow constraints" panel. Narrow `extra_allowed_hosts` to `["localhost"]`. Save agent. Verify via API: `curl http://localhost:8484/api/agents/Haiku45` shows `tool_overrides.http_request.extra_allowed_hosts == ["localhost"]`.

9. **NarrowSuperset locked chips**. In Studio Tools tab, expand `shell`'s "Narrow constraints" panel. Find `command_denylist` field. Verify operator's existing entries render as **locked chips** (no × button — keyboard focus skips them; screen-reader doesn't announce them). Add a NEW entry; save agent; verify saved override contains operator's items + the new agent addition.

## Acceptance Criteria

- [ ] All 9 scenarios pass (operator confirms in chat).
- [ ] Any UX gaps surfaced during the walkthrough are fixed inline (Developer agent spawned for code changes; re-verify before next scenario).
- [ ] Flight log entry for L6 lists pass/fix outcome per scenario.
- [ ] Leg status updated to `landed` after all scenarios pass.

---

## Post-Completion Checklist

- [ ] All 9 scenarios passed
- [ ] Inline fixes (if any) re-verified
- [ ] Flight log L6 entry written
- [ ] Leg status `landed`
- [ ] (NOT final leg — do NOT update flight.md status, do NOT commit)
