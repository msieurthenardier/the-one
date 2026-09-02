# Connector Setup

Operator walkthroughs for pairing a real chat platform to an agent, one
per platform below. Both connectors share the same config shape
(Studio's "Connectors" section, or `POST /api/connectors`):

| Field | Shape | Meaning |
|---|---|---|
| `secrets.token` | `str` | The platform credential (bot token). Encrypted at rest, masked on every API response. |
| `config.default_agent` | `str` | The agent that receives DMs and any channel with no `channel_map` entry. |
| `config.channel_map` | `dict[str, str]` | `channel_id -> agent_name`, channel targets only. |
| `config.allowlist.peers` / `.channels` | `list[str]` | Admission list — everything else is silently ignored. |
| `config.always_listen` | `list[str]` | Channel ids that get a reply with no `@mention`. |

Pairing (both platforms): send the connector's DM peer a message; the
operator's DM back with the pairing code shown in Studio (10-minute TTL)
appends them to `allowlist.peers`.

**Verified against**: 2026-09-02 (Mission 23 Flights 3-4).

---

## Discord

1. **Create the application** — [discord.com/developers/applications](https://discord.com/developers/applications), in a real browser (the Discord developer portal actively resists headless/automated sessions). Sign in with the operator's Discord account.
2. **Add a Bot user** — "Bot" tab → "Add Bot". Copy the token immediately; Discord shows it once. A later token reset is **MFA-gated** on the operator's account — have an authenticator ready.
3. **Enable the Message Content intent** — "Bot" tab → "Privileged Gateway Intents" → toggle **Message Content Intent** ON. Without this, `content` arrives empty on every inbound message regardless of admission — the connector will look "connected but silent". **This applies to every bot token the connector reads messages with**, including a second bot used only for a driver/test account during a live check — not just the main bot.
4. **Invite the bot to a server** — "OAuth2" → "URL Generator" → scopes `bot`, permissions `Send Messages` + `Read Message History` (add more only as the deployment needs). Open the generated URL, pick the target server.
5. **Register the connector** — Studio → Connectors → New → type `discord`, paste the bot token into `secrets.token`, set `config.default_agent` to the agent that should own DMs.
6. **Pair a DM peer** — have the operator's Discord account DM the bot anything; Studio's connector detail page shows a pairing code; the operator replies with that code in the same DM within 10 minutes.
7. **Enable a channel** — add the channel id to `config.allowlist.channels` (and `config.always_listen` for reply-with-no-mention), or map it to a specific agent via `config.channel_map`.

**Known limitation**: a bot cannot see another bot's messages on Discord for two DIFFERENT bot accounts talking directly (each is invisible to the other's own gateway subscription unless allowlisted) — see `the_one/connectors/README.md`'s DD-4 amendment for the `allowlist.peers`-gated exception.

---

## Telegram

1. **Create the bot** — DM `@BotFather` on Telegram, send `/newbot`, follow the prompts (display name, then a `_bot`-suffixed username). BotFather returns the bot token — treat it exactly like the Discord token (paste into `secrets.token`, never share it elsewhere).
2. **Set group privacy mode — REQUIRED for always-listen groups.** By default a Telegram bot in **privacy mode** only receives messages that are commands, `@mention`s, or replies to its own messages in a group — everything else is invisible to it, even with `config.always_listen` set. To make a group fully readable: message `@BotFather`, send `/setprivacy`, pick the bot, choose **Disable**. This must be done BEFORE adding the bot to any group it should always-listen in; Telegram does not retroactively deliver messages the bot missed while privacy was on.
3. **Register the connector** — Studio → Connectors → New → type `telegram`, paste the bot token into `secrets.token`, set `config.default_agent`.
4. **Pair a DM peer** — DM the bot from the operator's own Telegram account; follow the same pairing-code flow as Discord above.
5. **Add the bot to a group** — invite it like any member; then add the group's chat id to `config.allowlist.channels` (Studio's connector directory — populated passively as the bot observes traffic — surfaces the chat id/title pairing once the bot has seen at least one qualifying message).
6. **Forum topics** — a message inside a forum-topic thread carries a `thread_id` distinct from the parent group's channel id; addressing that thread specifically (rather than the group's general topic) needs its own `channel_map`/`allowlist` entry, copied from the directory lookup tool's `thread_id` field.

**Known limitations**:
- **No automated live gate**: Telegram bots cannot see other bots' messages, so there is no driver-bot round-trip test analogous to Discord's — a guided human-operated HAT is the only live verification instrument for this platform.
- **Group → supergroup migration**: Telegram silently changes a group's chat id when it's promoted to a supergroup. The connector does not track this migration; re-pair the channel (new id) after a promotion.
- **No message history**: the Bot API has no endpoint to fetch past messages, so `fetch_channel_history` is unavailable for Telegram connectors — the tool reports this plainly rather than erroring opaquely.
