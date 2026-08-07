# Behavior Test: Discord Slash Commands End-to-End (F14)

**Slug**: `discord-slash-end-to-end`
**Status**: active
**Created**: 2026-06-01
**Last Run**: 2026-06-01-18-39-11 (PASS 7/7 — after L11/L12/L13 inline-HAT fixes)

## Intent

Verify the six platform slash commands (`/whoami`, `/agents`, `/help`, `/talk_to`, `/new`, `/reset`) end-to-end against the operator's real Discord bot, observed from the dedicated Discord user's own web client — including the ephemeral-where-appropriate treatment on the three self-only commands. The test is written in the user's frame: what the dedicated Discord user sees with their own eyes when they invoke each command from the channel's slash menu. This needs a behavior test, not a unit test, because it exercises the live path no unit can stand in for as a UX flow: the real Discord web client renders the autocomplete and the interaction replies, the operator's real bot answers, slash-command registration must have fired for the guild (L2's `allowlist.guilds` slash-sync), and the per-command ACL admission must permit the dedicated user (L1's Bug D fix under the post-F12 structured-tuple allowlist). The user-perceivable "Only you can see this" ephemeral treatment (L7) is itself the observable. Unit and integration tests cover the substrate (the `DiscordClient.send` 4-cell routing matrix, token-expiry fallback, ACL admission); only a real-client run proves the whole stack renders correctly to a human.

## Preconditions

- the-one is running host-native (the operator's connector worker is up).
- The operator's Discord bot is online, and its connector is configured with the test guild listed in `allowlist.guilds` — so the six slash commands registered for that guild post-L2 (slash-sync reads `allowlist.guilds`). The autocomplete-probe step (step 1) actively verifies this decaying live state before any command row runs; a missing-command probe is a precondition failure, not a confusing mid-test cascade.
- The dedicated Discord user is logged into the Discord web client in the chrome-devtools MCP browser session, with the test channel open (the channel whose guild is on `allowlist.guilds`).
- The dedicated Discord user is on the connector's allowlist (peer + channel + guild axes), so all six commands are ACL-permitted for that user post-L1.
- At least one ACL-permitted agent is attached to the connector account, and the operator knows that agent's name to supply as the `/talk_to` argument at run time (see step 5). Parameterize via the `agent` variant below, or instruct the operator to use a known-attached agent name when the run starts.
- **Which instance**: the connector worker's live Discord bot connection is tied to
  whichever the-one instance the operator's bot token is configured on — infrastructure
  the operator controls, not something this run spins up fresh. If that is the operator's
  persistent `:8484` instance, that is an explicit operator decision, never a default this
  spec assumes; prefer a dedicated non-default-port instance where one exists.
- **Credential**: this test's only apparatus is the Discord web client (per Observables
  Required) — it does not itself navigate the-one's gated UI. If any step is adapted to
  also inspect the-one directly, follow CLAUDE.md's "Behavior-test credential convention"
  for that access.

## Observables Required

- browser (Discord web client rendered state — screenshot + accessibility tree primary, DOM supplementary; measured via chrome-devtools MCP). Pure browser frame; no `[mixed-frame]` observables are expected — every assertion is user-perceivable in the dedicated user's web client.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | In the test channel's message box, type `/` to open Discord's slash-command autocomplete. Take a screenshot. | The autocomplete menu lists the operator's bot's six commands: `whoami`, `agents`, `help`, `talk_to`, `new`, `reset`. Their presence proves slash-sync registered the commands for this guild (L2). If any are missing, this is a precondition failure (slash-sync did not fire / guild not in `allowlist.guilds`) — abort the run. |
| 2 | Invoke `/whoami` (type `/whoami`, select it from autocomplete, send). Take a screenshot of the reply. | The reply renders with the **"Only you can see this"** ephemeral treatment (a clearly-private reply visible only to the invoker; screenshot is the evidence). The reply does NOT appear as a normal channel message in history. The reply names the currently-routed agent (e.g. "Currently responding: \<agent\>."). |
| 3 | Invoke `/agents` (select from autocomplete, send). Take a screenshot of the reply. | The reply renders with the **"Only you can see this"** ephemeral treatment (not a normal channel message in history). The reply lists **at least one** agent the user can talk to here — it is NOT "No agents available for this conversation." A non-empty agent list is the user-perceivable proof of the L1 Bug D fix under the real structured-tuple allowlist. |
| 4 | Invoke `/help` (select from autocomplete, send). Take a screenshot of the reply. | The reply renders with the **"Only you can see this"** ephemeral treatment (not a normal channel message in history). The reply lists the available commands and includes `/talk_to` (and the other commands the user can use here). |
| 5 | Invoke `/talk_to <agent>` where `<agent>` is an actually-attached, ACL-permitted agent name (the operator supplies a known agent at run time, or use the `agent` variant). Select from autocomplete, supply the argument, send. Take a screenshot of the reply. | The reply is **channel-visible** — it appears as a normal message in the channel history with NO "Only you can see this" label, and persists in the channel. The reply confirms the routing override to the named agent (e.g. "Now routing your messages to \<agent\>."). |
| 6 | Invoke `/new` (select from autocomplete, send). Take a screenshot of the reply. | The reply is **channel-visible** (appears in channel history, NO ephemeral label, persists). The reply confirms a new conversation / session reset (e.g. "Started a new conversation. Your next message will begin a fresh session."). |
| 7 | Invoke `/reset` (select from autocomplete, send). Take a screenshot of the reply. | The reply is **channel-visible** (appears in channel history, NO ephemeral label, persists). The reply confirms a session reset (aliased to `/new` — same "fresh session" confirmation). |

Sequencing note: `/new` (step 6) and `/reset` (step 7) end the current session, so they run last among the channel-affecting commands; the earlier ephemeral rows (steps 2-4) read no session state that these reset, and `/talk_to` (step 5) runs before them so its routing-override confirmation isn't entangled with a session reset. Each row's expectation is self-contained.

## Out of Scope

- Wire-level ephemeral flag (`flags & 64`) on the interaction response — not DOM-observable from the web client; covered by L7's backend unit tests at the `DiscordClient.send` level (the 4-cell `ephemeral × token` routing matrix).
- The dropped `slash-command-ephemeral-routing.md` spec — its wire-level 4-cell substrate matrix and token-expiry (`NotFound` → channel fallback) behaviors are L7-unit-tested, not DOM-observable, and are not re-verified here.
- Multi-user routing and multi-channel routing — a single dedicated user in a single channel exercises the slash + ACL + ephemeral path; broader routing is out of frame.
- Exact ephemeral-label wording — the Validator judges the ephemeral-treatment intent (a clearly-private reply visible only to the invoker, absent from channel history), not a byte-exact "Only you can see this" string, since the web client's phrasing can change.

## Variants (optional)

- `agent` — the agent name supplied to `/talk_to` in step 5. Defaults to an operator-chosen known-attached, ACL-permitted agent at run time. Parameterize to re-run against a different attached agent.
