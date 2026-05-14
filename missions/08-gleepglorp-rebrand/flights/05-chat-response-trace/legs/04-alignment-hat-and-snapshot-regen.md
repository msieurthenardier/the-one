# Leg: alignment-hat-and-snapshot-regen

**Status**: completed
**Flight**: [Chat Response Trace](../flight.md)

## Objective

Operator-driven Human Acceptance Test (HAT) of the chat-trace UI across golden + edge paths in both themes, fix the `app_with_agent` `.session-agent-badge` fixture race that has blocked mission KI #1 since Flight 1, regenerate the chat-area pixel snapshot baselines, and run a final post-leg browser-suite regression smoke. This is an **interactive leg**: the Flight Director walks the operator through verification steps one at a time, fixes inline issues as they surface, and commits the L04 changes only after every HAT step + the pixel regen + the regression smoke pass.

## Context

- **L01+L02+L03 already committed** as commit `7317659` on `flight/05-chat-response-trace`; draft PR #50 open. L04 is the final leg of Flight 5; it lands as a SECOND commit on the same branch and flips the PR from draft to ready-for-review.
- **HAT subject surface**: the L03 trace shell DOM. Per-assistant-turn collapsible `<details>`/`<summary>` grouping tool events under their parent message; native keyboard ops; F3.5 design-language token composition; ARIA preserved.
- **Mission KI #1 root cause confirmed during L04 design**: `test_snapshot_chat_with_messages` (at `tests/browser/test_visual_snapshots.py:188-207`) skips the welcome-canvas agent-click step that EVERY other chat test (`test_flow_chat.py:29-30`, `test_flow_chat.py:63-64`, `test_flow_new_chat.py:97-104, 120-124`) performs. The `app_with_agent` fixture creates an agent but does NOT pre-create a chat session — the welcome canvas shows on page load; the test then waits for `.session-agent-badge` text that never populates because no session is joined. **Fix**: add a single `page.locator(".chat-welcome-item").filter(has_text=...).click()` step before the badge wait. Fixture itself is correct; the test was the bug.
- **L03 accepted limitations to verify HAT-tolerable**:
  1. In-flight rejoin namespace-disjoint split — L02's intentional namespace boundary (live `{session.id}-msg-N` vs replay `replay-msg-N`) produces TWO trace shells for a single logical turn IF you join a session WHILE a turn is still running. Refresh-after-`done` resolves it. Operator decides whether this is tolerable or warrants a future namespace-alignment flight.
  2. OAuth `auth_required` button inside collapsed trace shell — sighted users may miss the consent affordance (button is hidden when shell is collapsed). The accessibility reviewer flagged this as a UX consideration (NOT a WCAG failure — `aria-live` propagation still announces it). Operator decides whether to auto-open the trace shell on `auth_required` events (would need a 1-line `details.open = true` injection in `getOrCreateTrace` when the triggering event is `auth_required`).
- **Pixel suite current state** (post-L03): 10 passed, 2 failed (`test_snapshot_chat_with_messages[dark|light]` — mission KI #1). Plus: the chat-area DOM has new `.trace-shell` structure but the existing 10 passing pixel baselines don't exercise tool-call paths, so they SURVIVED L03 unchanged. The 2 failing tests are exactly the ones that fail because the badge never appears.
- **Test infrastructure** (post-L01.5): broad pytest exits code 0 in ~91s; standard pytest discipline applies (no summary-line vs exit-code workaround needed).
- **HAT environment**: requires browser access to `http://localhost:8484` while `the-one` container is running. The operator uses the mock provider (or a real provider if they want to exercise the actual LLM behavior — mock provider is sufficient for verifying the trace shell DOM contract).

## Inputs

What exists before this leg runs:

- Commit `7317659` landed on `flight/05-chat-response-trace`; draft PR #50 open
- Working tree clean (post-batch-commit; nothing uncommitted)
- Container `the-one` running and serving the L03 chat-trace UI
- Mission KI #1 (`.session-agent-badge` race) still open in `missions/08-gleepglorp-rebrand/mission.md`
- 2 known pixel-failures: `test_snapshot_chat_with_messages[dark]`, `test_snapshot_chat_with_messages[light]`
- L03 leg artifact's documented open considerations (namespace split, OAuth auto-open) — to be resolved during HAT

## Outputs

What exists after this leg completes:

- All HAT scenarios operator-confirmed (or inline-fixed and re-confirmed)
- `tests/browser/test_visual_snapshots.py:test_snapshot_chat_with_messages` updated to perform the welcome-canvas agent-click before waiting for the badge → mission KI #1 RESOLVED
- Pixel-snapshot baselines regenerated locally for any tests whose rendered DOM changed (gitignored per project convention)
- Pixel suite: 12 passing, 0 failing on a clean re-run
- Browser suite: ≥ 315 passing, 35 skipped (regression smoke clean — same as L01.5 baseline)
- Flight log L04 entry documenting HAT step results, any inline fixes, and operator decisions on the L03 open considerations
- L04 leg status: `completed`
- Flight status: `landed` (after L04 commits); flight checked off in mission.md; mission KI #1 marked resolved
- PR #50 marked ready-for-review

## Acceptance Criteria

These are organized as HAT scenarios. Each scenario is presented by the Flight Director one at a time; the operator runs it, reports the result, and either confirms ✓ or triggers an inline fix.

### HAT Scenario 1 — Golden path (single tool call)
- [ ] Operator sends a message that triggers exactly one tool call (via the mock provider's pre-configured tool-call response, or a real agent with a `read_file` directive)
- [ ] Assistant bubble renders with the streamed content
- [ ] A `.trace-shell` element appears IMMEDIATELY AFTER the assistant bubble
- [ ] The trace shell's `<summary>` shows "Tool activity" + count badge "2" (one tool_call + one tool_result)
- [ ] Clicking the summary expands the trace; the two `.msg.tool` elements are visible, with the call BEFORE the result
- [ ] Each `.msg.tool` has `data-tool-call-id` set (inspectable via dev tools)
- [ ] Re-clicking the summary collapses; expanding again restores

### HAT Scenario 2 — Multi-tool turn
- [ ] Operator sends a message that triggers 3+ tool calls (configurable via mock provider's `tool_calls` array, or an agent with a multi-step directive)
- [ ] Exactly ONE `.trace-shell` exists for the turn — NOT three
- [ ] Count badge reads N (where N = total tool events for the turn)
- [ ] All tool events appear in broadcast order (call, result, call, result, ...)
- [ ] Each event has its own `data-tool-call-id` and `data-tool-call-id`s pair correctly between calls and results

### HAT Scenario 3 — Error turn
- [ ] Operator sends a message that triggers a tool call that ERRORS (mock provider `is_error: True` on a tool_result, or a real agent calling a tool that raises)
- [ ] The trace shell renders the tool_result as `.msg.tool.error` (red border-left per F3.5 `--status-danger` token)
- [ ] No JS console errors; no crash

### HAT Scenario 4 — Empty turn (no tool calls)
- [ ] Operator sends a simple "hello" that produces an assistant response WITHOUT any tool calls
- [ ] NO `.trace-shell` element appears for that turn — only the assistant bubble
- [ ] Send button re-enables after `done`

### HAT Scenario 5 — Multi-turn session (multiple shells)
- [ ] Within the same chat session, operator sends 3 separate messages, each triggering tool calls
- [ ] 3 distinct `.trace-shell` elements exist in the DOM, each with its own `data-parent-msg-id`
- [ ] Tool events under each shell pertain ONLY to that turn (cross-wiring check)

### HAT Scenario 6 — Hard refresh / session rejoin
- [ ] After HAT Scenario 5 completes, operator hard-refreshes the page (Cmd-Shift-R / Ctrl-Shift-R)
- [ ] Same chat session reloads from history
- [ ] The same 3 trace shells reappear with the same tool events inside (modulo pre-existing `tool_result.content[:2000]` truncation — KI carry-forward)
- [ ] Live structure assertion (browser dev console): `document.querySelectorAll('.trace-shell').length === 3`
- [ ] No JS console errors

### HAT Scenario 7 — Mid-turn rejoin (namespace-disjoint split documented limitation)
- [ ] Operator sends a long-running multi-tool message
- [ ] WHILE the agent is still emitting tool events, operator hard-refreshes
- [ ] Expected behavior per L03 design: TWO trace shells render for the same logical turn (one with replay-shape ids from the history, one with live-shape ids from post-rejoin live events)
- [ ] Operator documents whether this is tolerable as-is OR warrants a follow-up namespace-alignment flight. **Default**: tolerable; refresh-after-`done` resolves cleanly. **Override**: schedule a follow-up flight if the operator finds the split distracting in practice.

### HAT Scenario 8 — M07 OAuth `auth_required` flow
- [ ] Operator triggers an MCP source with OAuth (a real or mock OAuth-bearing MCP server)
- [ ] The agent attempts a tool call on that source → `auth_required` event broadcasts
- [ ] Login-required button appears INSIDE a trace shell (NOT as a sibling of `.messages` directly)
- [ ] Operator clicks the button; OAuth popup opens; consent flow completes
- [ ] The resumed tool_result groups under the SAME trace shell (same `data-parent-msg-id`)
- [ ] Optional (operator decision): is the trace shell auto-opened when `auth_required` arrives? If consent button visibility was missed because the shell was collapsed, the operator schedules a follow-up fix to add `details.open = true` to the auth_required path in `getOrCreateTrace`.

### HAT Scenario 9 — Keyboard navigation
- [ ] Operator clicks into chat content area, then uses Tab to move focus
- [ ] Tab order: chat-input → chat-send-btn → trace shell summary(ies) in DOM order
- [ ] Focused `<summary>` shows visible focus ring (purple accent per F3.5 tokens)
- [ ] Pressing Enter or Space on a focused summary toggles the trace
- [ ] No focus traps; Shift-Tab works in reverse

### HAT Scenario 10 — Both themes
- [ ] Operator toggles between light and dark themes via the theme toggle (Admin → System page or via the existing UI control)
- [ ] Trace shell renders correctly in BOTH themes — colors, borders, focus rings all visible
- [ ] Tool messages inside the shell are readable in both themes

### HAT Scenario 11 — Cross-area routing
- [ ] Operator switches to Admin area while a chat session is open
- [ ] Returns to Chat
- [ ] Trace shells from the previous session are still rendered correctly (no stale state, no duplicates)

### Fixture race fix (mission KI #1 resolution)
- [ ] `tests/browser/test_visual_snapshots.py:test_snapshot_chat_with_messages` updated to click `.chat-welcome-item` before waiting for `.session-agent-badge` (pattern from `test_flow_chat.py:29-30`)
- [ ] Running just this test (both parametrizations) with `--snapshot-update` regenerates the baseline cleanly
- [ ] Re-running WITHOUT `--snapshot-update` PASSES (pixel-match against the just-regenerated baseline)

### Pixel baseline regeneration
- [ ] After all HAT scenarios pass + the fixture race fix lands, operator runs `timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 --snapshot-update -q` to regenerate baselines for any tests whose DOM changed
- [ ] Re-run without `--snapshot-update`: 12 passed, 0 failed (10 carried-forward + 2 newly-fixed `chat_with_messages` pair)
- [ ] Snapshot directory remains gitignored (per `.gitignore` — they're local artifacts, not committed)

### Browser-suite regression smoke
- [ ] `timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5` reports ≥ 315 passing, 35 skipped, 12 deselected — matching the L01.5 baseline exactly. NO new failures.

### Flight close
- [ ] L04 leg status → `completed`
- [ ] `flight.md` status → `landed`; `alignment-hat-and-snapshot-regen` checked off in Legs list
- [ ] Mission KI #1 marked resolved in `missions/08-gleepglorp-rebrand/mission.md`
- [ ] Flight checked off in `mission.md`'s Flights list
- [ ] L04 changes committed on `flight/05-chat-response-trace` (one additional commit on top of `7317659`)
- [ ] Draft PR #50 marked ready-for-review

## Verification Steps

This leg is interactive — verification IS the leg. Each HAT scenario above is its own verification step. The Flight Director walks the operator through them ONE AT A TIME, captures results, and applies inline fixes when issues surface.

## Implementation Guidance

### For the Flight Director (orchestrator):

1. **Present each HAT scenario sequentially**. Wait for the operator's report ("✓" / "✗ — issue X") before moving to the next.
2. **On a "✗"**: diagnose the issue. If it's a 5-min-fix (e.g. a CSS adjustment, a missing data attribute, an obvious code bug), apply inline. If it's deeper, spawn a focused fix-cycle Developer agent with a tight scope. Re-verify that scenario before moving on.
3. **On HAT Scenario 7 (namespace-disjoint split)**: capture the operator's decision (tolerate / schedule follow-up). Do NOT attempt to fix in L04 — it's a documented L02 limitation.
4. **On HAT Scenario 8 (OAuth auto-open)**: capture the operator's decision. If they want the auto-open, the fix is small: in `getOrCreateTrace` or `renderLoginRequiredButton` add `traceEl.querySelector('details').open = true` when handling `auth_required`. Apply as inline fix.

### Fixture race fix (small focused change):

In `tests/browser/test_visual_snapshots.py:test_snapshot_chat_with_messages` (around line 190), add a welcome-canvas click before the badge expectation:

```python
@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_chat_with_messages(app_with_agent: SeededApp, page: Page, theme: str) -> None:
    """Chat with one user + one assistant message via mock provider."""
    page.set_viewport_size(VIEWPORT)
    page.goto(app_with_agent.base_url)
    _set_theme(page, theme)
    # F5 L04: click the welcome-canvas agent before waiting for the badge.
    # The `app_with_agent` fixture creates an agent but does NOT pre-create
    # a chat session; the welcome canvas shows on page load. Pattern matches
    # tests/browser/test_flow_chat.py:29-30. Fixes mission KI #1 (badge race).
    page.locator(".chat-welcome-item").filter(
        has_text=app_with_agent.agent_name
    ).click()
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=5000
    )
    page.locator('[data-testid="chat-input"]').fill("hello")
    # ... existing assertions unchanged ...
```

### Pixel baseline regen sequence:

After all HAT scenarios pass AND the fixture race fix lands:

```bash
# Regenerate baselines for any tests whose DOM changed (chat snapshots most likely):
timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 --snapshot-update -q

# Re-run without --snapshot-update to verify the new baselines pass:
timeout 120 docker exec the-one pytest tests/browser/ -m pixel --timeout=60 -q 2>&1 | tail -5
```

Expected: 12 passing, 0 failing. The 2 previously-failing chat_with_messages tests now pass; the other 10 carry forward unchanged (or are regenerated if any chat-area shared chrome changed and they were inadvertently affected — unlikely given L03's DOM is scoped to in-trace content).

### Browser regression smoke:

```bash
timeout 600 docker exec the-one pytest tests/browser/ -m browser --timeout=30 -q 2>&1 | tail -5
```

Expected: `315 passed, 35 skipped, 12 deselected` matching L01.5 baseline exactly. No new failures.

### Flight close commit:

After all the above passes, the Flight Director spawns a Developer agent (or, given the scope is small enough, drives directly) to:

1. Update `missions/08-gleepglorp-rebrand/mission.md`: mark KI #1 resolved with a status note pointing at the L04 fix
2. Update `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight.md`: status `in-flight` → `landed`; check off `alignment-hat-and-snapshot-regen` in Legs list
3. Check off Flight 5 in `missions/08-gleepglorp-rebrand/mission.md`'s Flights list
4. Update this leg artifact: status `in-flight` → `completed`
5. Append the L04 entry to `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md` with HAT scenario outcomes and operator decisions
6. Stage + commit:
   ```
   flight/05: chat response trace — L04 alignment HAT + snapshot regen

   Mission: 08-gleepglorp-rebrand

   - HAT-verified the L03 trace shell across N scenarios (...)
   - Fixed mission KI #1 (.session-agent-badge race) by adding the
     welcome-canvas click step in test_snapshot_chat_with_messages
   - Pixel baselines regenerated locally (gitignored)
   - Browser regression smoke clean (315 passing, 35 skipped — L01.5 baseline)
   - Flight 5 landed; mission KI #1 resolved

   Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
   ```
7. Push to origin
8. `gh pr ready 50` — flip PR #50 from draft to ready-for-review

## Edge Cases

- **HAT scenario surfaces a real defect**: if a non-trivial issue is found mid-HAT, the Flight Director either applies an inline fix (small, surgical) or marks the scenario as a "follow-up flight" if it's beyond L04's scope. The operator decides the threshold.
- **Pixel regen produces unexpected diffs in OTHER snapshots** (not just `chat_with_messages`): could happen if L03's CSS additions cascade unexpectedly. Operator inspects each new baseline; if a baseline change is unintentional, revert + investigate.
- **`make rebuild` needed mid-HAT**: if any inline fix touches JS/CSS/Python, run `make rebuild` before the operator resumes the HAT (operator may need to hard-refresh too).
- **PR ready-for-review fails**: `gh pr ready` may fail if there are merge conflicts. Resolve and retry.

## Files Affected

- `tests/browser/test_visual_snapshots.py` — 1 line added (welcome-canvas click step) at `test_snapshot_chat_with_messages`
- `missions/08-gleepglorp-rebrand/mission.md` — KI #1 status update + Flight 5 checked off in Flights list
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight.md` — status → `landed`; L04 checked off
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/legs/04-alignment-hat-and-snapshot-regen.md` — status → `completed`
- `missions/08-gleepglorp-rebrand/flights/05-chat-response-trace/flight-log.md` — L04 entry
- Local-only pixel baselines under `tests/browser/__snapshots__/` (gitignored)
- Any inline fixes applied during HAT (file list depends on what scenarios surface)

---

## Post-Completion Checklist

**Complete ALL steps before the L04 commit:**

- [ ] All HAT scenarios marked ✓ by the operator
- [ ] `.session-agent-badge` fixture race fixed (mission KI #1)
- [ ] Pixel suite 12 passed / 0 failed on clean re-run (no `--snapshot-update`)
- [ ] Browser suite 315 passed / 35 skipped (regression smoke)
- [ ] Operator decisions captured for HAT Scenarios 7 and 8 in flight log
- [ ] Mission KI #1 marked resolved in mission.md
- [ ] Flight 5 checked off in mission.md
- [ ] Flight status → `landed`
- [ ] L04 leg checked off in flight.md
- [ ] L04 leg status → `completed`
- [ ] L04 flight-log entry appended
- [ ] L04 commit landed on `flight/05-chat-response-trace`
- [ ] Pushed to origin
- [ ] PR #50 marked ready-for-review
- [ ] Signal `[COMPLETE:leg]` then `[COMPLETE:flight]`

---

## Citation Audit

6 source-code citations verified against current code at leg design time:

| Citation | Class | Notes |
|---|---|---|
| `tests/browser/test_visual_snapshots.py:188-207` (`test_snapshot_chat_with_messages`) | OK | Verified — function spans these lines; missing welcome-canvas click before badge wait at line 196 |
| `tests/browser/test_flow_chat.py:29-30` (`chat-welcome-item` click pattern) | OK | Verified — `page.locator(".chat-welcome-item").filter(has_text=agent_name).click()` followed by badge wait |
| `tests/browser/test_flow_chat.py:63-64` | OK | Verified — same pattern as above for the second test in that file |
| `tests/browser/test_flow_new_chat.py:97-104, 120-124` | OK | Verified — uses the same pattern across multiple tests |
| `tests/browser/conftest.py:222-243` (`app_with_provider`/`app_with_agent` fixtures) | OK | Verified — `app_with_agent` seeds an agent but does NOT create a chat session |
| Mission KI #1 (`mission.md` Known Issues section) | OK | Verified — KI documented; status will flip to resolved by this leg |

All citations OK. No drift; no rewrites required.
