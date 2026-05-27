# Leg: hat-pairing-and-detach

**Status**: partial
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Outcome

**Date**: 2026-05-27. Operator-driven HAT against the real Discord guild + 2 burner accounts.

| Step | Status | Notes |
|------|--------|-------|
| 1 | PASS | DM from B1 → bot silent on Discord; pending-approval banner rendered in operator Chat UI. |
| 2 | PASS | Banner shows peer name + preview + Approve / Dismiss + timestamp. |
| 3 | PASS | Approve click → buttons replaced with `approved` badge; B1's user id (`1389008395092103273`) added to `account.config["allowlist"]["peers"]`. |
| 4 | **FAIL** | Surfaces structural gap (see below). B1's follow-up DM was permitted by L1's resolver, but routing returned `no-eligible-agent` and the bot replied "No agents available for this conversation." |
| 5-8 | DEFERRED | Detach + PAIR-prefix fallback not exercised in this run; gap analysis takes priority. |

### Structural findings (escalated to F9 Known Issues + Mission Known Issues)

**Finding 1: ACL semantics — account-scope channels axis has no `is_dm` short-circuit.**

`the_one/connectors/_acl.py:323-329` (account-scope channel check inside `admits_inbound`) denies the inbound when `account.config["allowlist"]["channels"]` is non-empty AND the inbound `channel_id` is not in the list. The per-agent equivalent at `_acl.py:372-378` DOES short-circuit on `is_dm` for the empty-list sentinel, but the account-scope version has no `is_dm` parameter at all. Result: any account with a non-empty channels list rejects DMs from allowlisted peers — the F9 Discord-native flow's allowlist mutation (adding the peer) does not grant DM admission when channels are restricted.

**Finding 2: UI gap — single channels axis conflates two distinct concepts.**

Both the connector account allowlist editor (Studio → Connectors → {account} → Allowlist) and the per-agent overlay (Agent editor → Connectors → per-account ACL) expose ONE `channels` axis. There is no UI distinction between:

- **Guild channel restriction** — "the bot is only allowed to chat in these specific guild channels"
- **DM admission** — "the bot accepts DMs from approved peers (peer-axis controls who; channel-axis irrelevant for DMs)"

Today the operator can pick a restrictive guild-channels list OR an empty channels list (admits all channels including DMs), but not "this specific guild channel for guild chat + DMs admitted via peer-axis."

### Disposition

L8 status: **partial**. Steps 1-3 verify the F9 Discord-native approval substrate (resolver, storage, endpoints, banner, allowlist mutation) is sound. Step 4 surfaced the design gap that prevents end-to-end usability for an operator with a restrictive channels configuration. Steps 5-8 are deferred — the detach affordance (L5) and PAIR-prefix fallback (existing M10 path) are untouched by this gap but not exercised in this run.

Mission criterion #8 (pairing resolution) is **partially closed by F9**:
- ✓ Substrate landed (resolver hook, storage, endpoints, banner).
- ✓ Discord-native approval works END-TO-END when account-scope channels axis is empty.
- ✗ Discord-native approval does NOT work end-to-end when account-scope channels axis is non-empty (the operator's realistic production configuration).
- → Full closure requires the follow-on flight's DM-vs-channel axis split (UI + substrate).

The follow-on flight addresses both findings together — UI affordance (split DM admission from channel restriction) AND substrate (`is_dm` short-circuit at account-scope, OR a dedicated DM-admission flag, depending on what UI design demands).

## Objective

Operator-driven 8-step walkthrough exercising the F9 dual-flow pairing (Discord-native primary + PAIR text-prefix fallback) + the connector-account detach affordance end-to-end against a real Discord guild.

## Prerequisites

- L1-L7 landed and committed (F9 commit `61e56f6` on branch `flight/09-pairing-resolution-and-detach`).
- App running: `make rebuild` then verify at `http://localhost:8484`.
- Discord test guild + at least one Discord connector account configured in Studio + at least one agent attached to it.
- Two unpaired burner Discord accounts (B1, B2) that are NOT currently in `account.config["allowlist"]["peers"]`.
- One additional Discord account or burner (B3) for the PAIR-prefix fallback test.

## Steps

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | From burner **B1**, DM the bot something like "hello bot". | The bot does NOT reply on the Discord side. In the operator's Chat UI (the session for B1's DM-channel), a `pending-approval` banner appears with B1's username + the preview text + Approve / Dismiss buttons. |
| 2 | Inspect the banner in Chat UI. | The banner shows B1's display name, the message preview, a timestamp, an Approve button, and a Dismiss link. |
| 3 | Click **Approve**. | The buttons disappear; an `approved` status badge appears in place. The operator's Studio → Connector account detail page now shows B1 in the allowlist's `peers` list. |
| 4 | From B1, send another DM (e.g. "are you there now?"). | The agent engages normally — replies to B1 via Discord. The reply lands in B1's DM channel. The unified history in the operator console shows the exchange with peer-name attribution. |
| 5 | Navigate to the connector account detail page (Studio → Connectors → click the connector tile). Click **Detach** on one of the attached agents. | The Attached Agents row updates without page reload (the detached agent disappears from the list). The Connectors grid tile's agent-count badge decrements when you return to the grid (or the next navigation back). |
| 6 | From a user in a guild channel where the detached agent was previously responding, send a message mentioning the bot. | The detached agent does NOT respond. (Other still-attached agents on the same connector account may still respond.) |
| 7 | From burner **B3** (an unpaired account different from B1/B2), send a DM with `PAIR <code> hello` where `<code>` is the current pairing code from the Studio Pairing section. | The bot accepts the pairing; B3 is added to the allowlist via the text-prefix path. The agent processes the "hello" content (replies, or proceeds per the agent's logic). |
| 8 | Verify the Studio Pairing audit log (or the chat session's audit metadata) shows the two distinct paths: B1 was paired via the Discord-native flow (no PAIR prefix); B3 was paired via the text-prefix flow. | Both flows are observable in the audit trail. The allowlist now contains B1, B3 (and any pre-existing peers). |

## Inline-Hotfix Discipline (F7 L12 precedent)

If any step reveals a bug, the Flight Director can spawn a Developer agent to fix inline, then re-verify the step before moving on. Bounded fixes (<80 LOC across <3 files) stay in L8; larger surfaces divert to a follow-on leg.

## Operator-Judged Satisfaction

L8 lands when all 8 steps pass AND the operator's judgment is "shippable" — the dual-flow + detach UX feels right end-to-end, not just mechanically correct.
