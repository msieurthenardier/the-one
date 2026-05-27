# Leg: hat-acl-split-verify

**Status**: ready
**Flight**: [ACL DM-admission + channels-axis UI split](../flight.md)

## Objective

Operator-driven HAT verifying F10's substrate + UI close the F9 L8 gaps end-to-end. Run against a channels-restricted account configured with `dm_admission` set explicitly via L2's selector. Closes mission criterion #8 on operator-judged satisfaction.

## Prerequisites

- F10 L1, L2, L3 landed and committed (or staged for Phase 2d batch — Flight Director's call).
- App rebuilt: `make rebuild`. Verify the app serves L2's new "DM admission" row by loading the connector account detail page and confirming the selector renders.
- One Discord connector account configured with:
  - `config.allowlist.channels = [<one specific guild channel id>]` — the restrictive setup that broke F9 L8 step 4.
  - `config.allowlist.dm_admission = "allowlisted-peers-only"` — the F10 flow's target state. Set via L2's UI selector OR via direct API.
  - At least 2 attached agents, both with default `admit_dms` (inherit; checkbox checked).
- Two unpaired burner Discord accounts (B1, B2) NOT in `account.config.allowlist.peers`.
- The bot is invited to the test guild; burners can DM the bot.

## Steps

| # | Action | Expected Result |
|---|--------|-----------------|
| 1 | From burner **B1**, open a DM to the bot. Send "hello bot". | The bot does NOT reply on Discord. In the operator Chat UI, a `pending-approval` banner appears (F9 L4 surface). |
| 2 | Inspect the banner: B1's display name, preview, timestamp, Approve button, Dismiss link. | All four present. |
| 3 | Click **Approve**. | Buttons replaced with `approved` badge. Navigate to Studio → Connectors → account detail → Allowlist: B1's id is in `peers`. **Crucially:** channels list is UNCHANGED (still the one guild channel from setup). |
| 4 | From B1, send another DM: "are you there now?". | **This is the F9 L8 regression-fix gate.** The agent engages this time — bot replies on Discord; operator Chat UI shows the exchange with peer-name attribution. F10's `dm_admission` gate consults the new axis (not the channels axis) for DMs. |
| 5 | Navigate to connector account detail → Attached Agents. Click **Detach** on one of the attached agents. | The row updates without page reload; the detached agent disappears from the list. The Connectors grid tile's agent-count badge decrements. |
| 5b | **NEW: per-agent `admit_dms` opt-out.** Navigate to a still-attached agent → Connectors tab → expand the account's ACL section. Uncheck "Admit DMs from this account". Save. From B1, send another DM. | The opted-out agent does NOT engage. Other still-attached agents on the same connector still do engage (verify by sending a follow-up DM and observing which agent replies). Verify via API: `GET /api/agents/{name}` shows `connector_acls[acct].admit_dms == false`. |
| 6 | From a user in a guild channel where the detached agent was previously responding, send a message mentioning the bot. | The detached agent does NOT respond. Other still-attached agents may. |
| 7 | From burner **B2** (different from B1), send a DM with `PAIR <code> hello` where `<code>` is the account's current pairing code (Studio Pairing section). | The bot accepts the pairing; B2 is added to the allowlist via the text-prefix path. The agent processes "hello" content (replies per agent logic). |
| 8 | Verify the chat session audit log shows the two pairing paths: B1 was paired via the Discord-native flow (`reason: "pending_approval"` then `permit`); B2 via the text-prefix flow (`reason: "paired"`). | Both flows are observable in the audit trail. The allowlist now contains B1, B2, and any pre-existing peers. **Channels list still unchanged from setup.** |

## Inline-Hotfix-During-HAT Discipline

If any step fails, fix inline if <80 LOC across <3 files (F7 L12 / F9 L8 precedent). Otherwise divert to a follow-on leg.

## Operator-Judged Satisfaction

L5 lands when all 8 steps + 5b pass AND the operator's judgment is "shippable" — the dual-flow + axis-split UX feels right end-to-end.

## Mission Criterion #8

On L5 land: update `mission.md` criterion #8 from `[~]` to `[x]` (full closure). The substrate + UI gap that F9 L8 partial-closed is now fully resolved.
