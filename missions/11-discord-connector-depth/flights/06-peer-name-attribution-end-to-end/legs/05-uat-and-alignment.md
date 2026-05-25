# Leg: uat-and-alignment

**Status**: completed
**Flight**: [Peer-name Attribution End-to-End (Bug C)](../flight.md)

## Objective

Operator-driven HAT against a real Discord channel: verify that peer-name attribution actually reads correctly in the unified Chat UI history when a real peer sends real messages — closing the gap between "tests pin the wire shape" and "the UX feels right to the operator."

## Context

L1-L4 closed the six Bug C surfaces and committed (`b64fea4`, PR #74). The autonomous review confirmed acceptance criteria, code quality, and accessibility. L5 is the last gate before flight close — per F5 debrief's methodology, single-feature flights budget 1-3 escalating-tightening HAT rounds (vs cumulative-debt flights which budget 5-8). F6 is single-feature.

The Flight Director (orchestrator) guides the operator through verification steps one at a time. Each step has a clear pass/fail. Failures get diagnosed inline; if code changes are needed, the orchestrator spawns a Developer to fix, then re-verifies that step before moving on.

## HAT Setup

**Prerequisites**:
- `flight/06-peer-name-attribution-end-to-end` branch is checked out locally with L1-L4 changes (commit `b64fea4`).
- A Discord bot token is configured as a connector account in the operator's the-one instance (M11 F1 landed; the operator should already have at least one connector account from prior HATs).
- The Discord bot is invited to at least one server with at least one channel.
- The operator has access to at least one peer Discord account (the operator + 1 burner is sufficient for the multi-peer assertion).
- The-one is running locally and accessible in the operator's browser.

## Acceptance Criteria (= verification steps)

Each `[ ]` is a single step the operator runs. Verified pass-by-pass; failures fold inline.

- [x] **Step 1 — Server is running F6 code.** Operator confirms the-one is restarted on the `flight/06-peer-name-attribution-end-to-end` branch (commit `b64fea4`+). **HAT outcome: pass.**
- [x] **Step 2 — Bot is online and attached.** Operator opens the Studio Connectors tab, picks the Discord connector account, confirms its lifecycle status reads `running` (or whatever the bot's online state surfaces as in the current UI). **HAT outcome: pass — Test Connection returned `discord probe ok`.**
- [x] **Step 3 — Send a peer message from Discord.** From a peer Discord account (the operator's burner, or a peer the operator coordinates with), send a message in a channel the bot can read (e.g. `"hello bot"` or `"@<bot> ping?"` depending on the channel's auto-relay configuration). Wait for the agent to respond. **HAT outcome: pass — peer message delivered, agent replied.**
- [x] **Step 4 — Open the unified history in the-one Chat UI.** Operator opens the Chat UI and navigates to the connector-attached session that just received the peer message. **HAT outcome: pass — unified history opened with the peer turn + agent reply visible.**
- [x] **Step 5 — Peer bubble renders left-aligned with peer-name attribution.** The operator visually confirms the peer-attributed user bubble:
  - Sits on the LEFT side of the chat (same alignment as agent replies, distinct from operator-typed user bubbles).
  - Shows the peer's Discord display name (NOT "You") as the attribution text below/above the bubble.
  - Renders with a distinct background — not the operator's accent color.
  - The agent's reply renders below it, also left-aligned, with the agent's name as attribution.
  **HAT outcome: pass — peer bubble left-aligned with peer-name attribution rendering correctly.**
- [x] **Step 6 — Operator-typed message renders right-aligned with "You".** From the Chat UI input, operator types a message into the same session and presses send. Confirms:
  - The operator's typed bubble renders on the RIGHT side.
  - Attribution reads `"You"`, NOT the peer's name or any other value.
  - The accent background is present (operator's own message styling).
  **HAT outcome: pass — operator-typed bubble right-aligned with "You" attribution.**
- [~] **Step 7 — Multi-peer in same channel (multi-user routing precursor for F7).** If a second peer Discord account is available, have them send a message in the same channel. Verify:
  - Their bubble also renders left-aligned with their distinct Discord display name as attribution.
  - The agent's response below also renders left-aligned with the agent name.
  - The two peers are visually distinguishable from each other AND from the operator's typed messages.
  - If only one peer account is available, skip this step and note it as "skipped — single peer account".
  **HAT outcome: SKIPPED — single peer account available at HAT time. Multi-peer wire-shape is pinned by the L4 browser test (`test_flow_chat_peer_attribution.py` seeds two distinct peers "alice" and "bob" and asserts both render with their own peer-name attribution); the live multi-peer in a real Discord channel will be exercised under F7 (mentions-aware response policy) and M11 criterion #5 / #7 (multi-user routing HAT against ≥3 distinct users), which are mission-scope items unaffected by this skip.**
- [x] **Step 8 — Reload preserves attribution.** Operator reloads the Chat UI page (Ctrl+R / Cmd+R) on the same session. Confirms:
  - The peer-attributed bubbles still render with peer names (replay through `messages_to_ui_events` + Chat UI consumption works).
  - The operator-typed bubbles still render right-aligned with "You".
  - No bubble loses its attribution after reload.
  **HAT outcome: pass — reload preserved peer-name attribution; replay path through `messages_to_ui_events` works end-to-end.**
- [~] **Step 9 — Screen reader announcement (optional but recommended).** Operator enables a screen reader (macOS VoiceOver: Cmd+F5; Windows Narrator: Ctrl+Win+Enter; or browser dev-tools accessibility tree inspection) and navigates to a peer-attributed bubble. Confirms the announcement begins with `"From <peer name>:"` followed by the message text. (The WCAG 1.3.3 fix landed via the visually-hidden `.msg-from-peer-label` span.)
  **HAT outcome: SKIPPED — operator did not engage a screen reader at HAT time. The label's DOM presence + sr-only CSS application are pinned by the L4 a11y follow-up assertions (Assertion 9 verifies `.msg-from-peer-label.visually-hidden` exists with textContent `'From alice: '` / `'From bob: '` and that `getComputedStyle.clip === 'rect(0px, 0px, 0px, 0px)'` so the utility is actually loaded/applied); the live screen-reader announcement is a future verification opportunity (M11 has no general a11y HAT criterion, so this is methodology-followup not mission-criterion).**
- [x] **Step 10 — Operator subjective rating: does this feel right?** Operator gives one of three ratings:
  - **`looks-good`** — UX reads naturally; ship as-is.
  - **`needs-tweak`** — There's a small issue the operator can articulate (e.g. spacing, color, text shape). The orchestrator captures the issue, spawns a Developer to fix, re-verifies that step, then re-checks the rating.
  - **`needs-rework`** — Something fundamental is off. The orchestrator escalates: either re-design within F6, or split out a follow-up flight, or revert. Likely doesn't happen — L1-L4 have been heavily reviewed — but the option is here.
  **HAT outcome: `looks-good` — UX reads naturally; ship as-is. No inline fixes needed.**

## Round Budget

Per F5 debrief methodology: single-feature flights budget 1-3 escalating-tightening rounds. Each round walks Steps 1-10. If Step 10 returns `looks-good`, the round is done and the flight proceeds to Phase 3. If `needs-tweak`, the round folds the fix inline and starts the next round. If the round counter hits 3 without `looks-good`, escalate.

Round 1 is the default expected case. Rounds 2-3 are reserved capacity.

## Files Affected

- None for the leg itself — this is verification work, not implementation.
- If a HAT round surfaces a code fix, the fix touches whatever surface the issue describes (e.g. `chat.css` for visual tweaks, `chat.js` for behavior tweaks). Fixes are folded into the existing L1-L4 surfaces and committed in a follow-up commit on the same branch.
- `flight-log.md` — HAT round entries appended per round under `## Leg Progress`.

---

## Post-Completion Checklist

- [x] All 10 verification steps passed at least once (Steps 1-6, 8, 10 pass; Step 7 skipped — single peer account; Step 9 skipped — operator did not engage a screen reader at HAT time; both skips have wire-shape pinning via the L4 browser tests).
- [x] Operator-rating in Step 10 is `looks-good`.
- [x] Round count and outcomes appended to `flight-log.md`.
- [x] Leg status set to `completed` (skipped intermediate `landed` since no inline fix work means no need for a separate transition).
- [x] `uat-and-alignment` checkbox ticked in `flight.md`'s Legs list.
- [ ] ~~If any inline code fixes landed during HAT rounds: commit them as a follow-up to `b64fea4` on the same branch.~~ **N/A — no inline fixes landed during HAT (single round; `looks-good` rating).**
- [x] Hand off to Phase 3: flip flight status to `landed`, check off F6 in mission.md, signal `[COMPLETE:flight]`.
