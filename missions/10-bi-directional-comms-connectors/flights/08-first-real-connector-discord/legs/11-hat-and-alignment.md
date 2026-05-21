# Leg: hat-and-alignment

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Operator-driven end-to-end test of the F8 Discord connector against a real Discord bot. Validates that the F1-F7 substrate + L1-L10 Discord-specific implementation compose into a working "agent reachable on Discord" experience. The HAT exercises every layer: bot provisioning, connector account registration in Studio, doctor probe, agent attachment, inbound message reception, outbound reply, allowlist enforcement, DM handling, and slash commands.

## Context

L11 of F8. Per `/agentic-workflow` interactive-leg protocol: not autonomous. Flight Director (me) guides the operator (you) through verification steps one at a time; the operator performs each step in their environment and reports results; the Flight Director fixes issues inline (spawning Developer agents when code changes are needed) before moving on.

This leg is the empirical validation that:
1. The operator can register a Discord bot identity via Studio Admin without re-discovering the L2-L9 design.
2. The doctor probe surfaces useful diagnostics for the typical operator-side misconfigurations (missing intent, wrong scope, invalid token).
3. Inbound message ingestion works against the real Discord gateway with real network conditions (latency, intermittent disconnects).
4. Outbound replies post correctly to the right channel/thread/DM.
5. The 6 v1 slash commands appear in the Discord client and route through the dispatcher correctly.
6. Allowlist enforcement (peers, channels, guilds, roles) gates real Discord traffic per the operator's configuration.

## Prerequisites

- Discord application + bot user provisioned in [Discord Developer Portal](https://discord.com/developers/applications).
- **Bot Token** obtained (revealed via Bot page → Reset Token).
- **Message Content Intent** + **Server Members Intent** enabled (Bot page → Privileged Gateway Intents).
- Bot invited to at least one guild (server) the operator controls. Required scopes: `bot` + `applications.commands`. Required permissions: View Channels, Send Messages, Read Message History, Use Slash Commands, Send Messages in Threads.
- the-one running on branch `flight/08-planning-discord` (or whatever branch this PR is on after rebase/merge).
- At least one agent configured in Studio that the operator will attach to the Discord account.

## Verification Steps

Each step is performed by the operator; the Flight Director walks through them one at a time, debugging in-flight.

### Step 1: Bot invited and visible in server
- [ ] Bot appears in the configured server's member list (offline initially — the-one hasn't connected yet).

### Step 2: Connector account registration in Studio Admin
- [ ] In Studio Admin, navigate to Connector Accounts → New.
- [ ] Type field shows `discord` as an option.
- [ ] Fill in: name (operator-chosen), type = `discord`, BOT_TOKEN credential (paste the bot token from Discord Developer Portal).
- [ ] Save. Account appears in the list. Discord badge renders with the L2 brand color (#5865F2 Blurple).

### Step 3: Doctor probe — happy path
- [ ] Open the account's detail page. Click "Test Connection" / doctor button.
- [ ] Probe completes within ~30 seconds. Status = `ok`. Message reads something like "Discord probe ok".
- [ ] Inspector expanded view shows 5 sub-checks all passed: token-valid, application-summary, intent-coverage, gateway-connect, allowlist-resolution.

### Step 4: Doctor probe — failure mode (invalid token)
- [ ] Edit the account; change the token to a deliberately invalid string.
- [ ] Probe → status = `failed`, message indicates token authentication failure.
- [ ] Restore the real token; probe → `ok` again.

### Step 5: Agent attachment in Studio Agent editor
- [ ] Edit an existing agent. Navigate to the Connector Accounts tab.
- [ ] Attach the Discord account. Save.
- [ ] Verify the attachment renders correctly in the agent's editor.

### Step 6: Listener startup (lifespan auto-acquire)
- [ ] Restart the-one. On startup, the Discord bot appears ONLINE in the configured server's member list within ~30 seconds.
- [ ] Server-side log shows no errors. **NOTE**: F8 deferred lifespan-time auto-acquire to L11 — if the bot does not come online automatically on restart, this is the documented L11 gap. Flight Director walks through the manual workaround (trigger acquire via Studio doctor probe, OR — fix inline by adding the lifespan wiring).

### Step 7: Slash command registration
- [ ] In the Discord server, type `/` in any channel where the bot has access. The 6 v1 commands should appear in Discord's autocomplete: `/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help`. (Note: `talk_to` not `talk-to` — Discord command names can't have hyphens.)
- [ ] Slash command registration may take up to 5 minutes for Discord's cache to refresh after the listener connects.

### Step 8: Inbound message → agent reply
- [ ] Send a regular message to the bot in a channel: `@<bot-name> hello`.
- [ ] Within a few seconds, the agent replies in the same channel. The reply text matches what the configured agent would produce for the prompt.

### Step 9: Slash command execution
- [ ] Invoke `/whoami` in the same channel. The reply names the currently-routed agent (the one attached to the Discord account).
- [ ] Invoke `/agents`. The reply lists agents available on this connector account.
- [ ] Invoke `/help`. The reply lists the 6 v1 commands with descriptions.

### Step 10: DM end-to-end
- [ ] In Discord, open a DM with the bot (right-click bot name → Message).
- [ ] Send a message. The agent replies in the DM channel.
- [ ] Verify the DM session is distinct from the guild-channel session — agents see them as separate conversations.

### Step 11: Audit log inspection in Chat UI
- [ ] Open the agent's Chat session list in the-one's Chat UI.
- [ ] The Discord conversation appears alongside any Chat-UI-native sessions. Opening it shows the unified history.

### Step 12: Allowlist enforcement (optional)
- [ ] On the connector account, set `allowlist.peers = ["<your_discord_user_id>"]`.
- [ ] Send a message from your own account → still works.
- [ ] Have a different Discord user (or test account) send a message → ignored / pairing-required.
- [ ] Clear the allowlist; resume normal operation.

### Step 13: Operator console (Chat UI) separation
- [ ] Open the Discord-bound session in the-one's Chat UI.
- [ ] Type a message in the operator console (the Chat UI's input).
- [ ] The agent receives the message but does NOT relay it to Discord — operator-console messages stay local by default per F5.
- [ ] The agent can explicitly invoke `send_to_platform_channel` (F4 tool) to push to Discord if instructed.

## Acceptance Criteria

- [ ] All 13 verification steps pass against a real Discord bot.
- [ ] Any failure mode discovered is either fixed inline (with a Developer agent applying the fix + flight log Deviations entry) or explicitly deferred (with the deferral documented in the flight log as an F10 carry-forward).
- [ ] No new high-severity issues surfaced that aren't either fixed or documented.

## Post-Completion Checklist

- [ ] All verification steps signed off
- [ ] Flight log captures any in-flight fixes + deferrals
- [ ] Set leg status to `completed`
- [ ] Check off L11 in flight.md (HAT line in Checkpoints)
- [ ] Update flight status `in-flight` → `landed`
- [ ] Check off Flight 8 in mission.md
- [ ] Commit + push final HAT state
- [ ] Signal `[COMPLETE:flight]`
