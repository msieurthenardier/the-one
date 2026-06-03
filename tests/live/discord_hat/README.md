# Live-Traffic Discord HAT — Operator Guide

This directory contains the committed, re-runnable live-traffic HAT
(Hardware-Approximation Test) suite for the Discord connector. It drives
real bot traffic into a real Discord guild and asserts against the-one's
HTTP API to verify multi-user routing, attribution, ACL differentiation,
agent overrides, and peer-decoupling guarantees against the live substrate.

---

## Contents

- [Provisioning burner bots](#provisioning-burner-bots)
- [Finding the-one's gateway bot user id](#finding-the-ones-gateway-bot-user-id)
- [Environment variable contract](#environment-variable-contract)
- [Running the suite](#running-the-suite)
- [Skip behaviour — no credentials](#skip-behaviour--no-credentials)
- [Timing rationale: `wait_for_session(until=…)`](#timing-rationale-wait_for_sessionuntil)
- [Connect-time closure — container restart requirement](#connect-time-closure--container-restart-requirement)
- [Bot-can't-DM-bot constraint (REST 50007)](#bot-cantdm-bot-constraint-rest-50007)
- [Scenario catalogue](#scenario-catalogue)
- [Known operational gotchas](#known-operational-gotchas)

---

## Provisioning burner bots

**Create bot apps in a normal browser — do NOT use an automated browser.**
The Discord Developer Portal requires hCaptcha during app creation and
MFA-gated token resets. Both hard-block automation (the captcha loops
forever; the token modal is MFA-gated). Use a real browser session.

Steps (once per set of bots — re-run if you re-provision):

1. Go to <https://discord.com/developers/applications> and sign in.
2. For each burner bot (the suite uses 3): **New Application** → name it
   (e.g. "HAT Test Bot 1"), accept terms.
3. In the app: **Bot** tab → **Reset Token** (MFA-gated) → copy the token.
   Store each token in `.env.hat` (gitignored — see below).
4. **Intents** (same Bot tab): **Message Content Intent is NOT needed on the
   burner bots**. The senders only POST messages; `message_content` is a
   privileged receive capability that the-one's own bot carries (it reads
   inbound messages). Requesting a privileged intent the bot apps don't have
   enabled raises `PrivilegedIntentsRequired` on connect. Leave it disabled.
   Enable **Server Members Intent** and **Presence Intent** only if your test
   scenarios require them (the smoke/routing scenarios do not).
5. **OAuth2 → URL Generator**: scope `bot`, permissions **Send Messages** +
   **Read Messages/View Channels**. Open the generated URL, authorize the bot
   into your test guild (NOT the production guild).
6. Assign any test roles the ACL scenarios require (e.g. `test-role1` for the
   ACL admission tests).

**The-one's own bot** (the one the connector connects as) DOES need Message
Content Intent enabled — it reads inbound messages from the burner bots.

---

## Finding the-one's gateway bot user id

The Discord API does not expose a bot's own user id through the REST `GET
/users/@me` for bot tokens in a simple way after the gateway handshake.
The easiest operator path:

1. Go to <https://discord.com/developers/applications>.
2. Open the-one's bot application.
3. **General Information** tab → copy the **Application ID**.

For Discord bots, **Application ID == Bot User ID**. This is the id you put
in `THE_ONE_HAT_BOT_USER_ID`. The driver uses it to construct `@mention`
strings (`<@<id>>`) and to address DMs to the-one.

Alternatively, once the connector is warm, `docker logs the-one` shows the
gateway READY event with the bot's user id.

---

## Environment variable contract

Copy `.env.hat.example` to `.env.hat` (gitignored) and fill in real values:

```bash
cp tests/live/discord_hat/.env.hat.example tests/live/discord_hat/.env.hat
# edit .env.hat with your real ids and tokens
```

| Variable | Required | Description |
|---|---|---|
| `THE_ONE_HAT_BOT_TOKENS` | yes | Comma-separated tokens for the N sender bots, in order. |
| `THE_ONE_HAT_BOT_TOKEN_1`/`_2`/`_3` | fallback | Numbered alternatives used only if `THE_ONE_HAT_BOT_TOKENS` is empty. |
| `THE_ONE_HAT_GUILD_ID` | yes | Discord guild (server) id for the test guild. |
| `THE_ONE_HAT_CHANNEL_IDS` | yes | Comma-separated channel ids (index-matched to scenarios). `channel_ids[0]` = smoke + multi-user; `channel_ids[1]` = multi-agent; `channel_ids[2]` = multi-channel third channel. |
| `THE_ONE_HAT_CONNECTOR_ID` | yes | The-one connector id for the test connector (`ingest_bots=true`, both agents attached). Find it in the-one Admin UI → Connectors. |
| `THE_ONE_HAT_BOT_USER_ID` | yes | The-one's OWN Discord bot user id (Application ID from the Developer Portal). Used to build `@mention` strings and DM targets. |
| `THE_ONE_HAT_BOT_USER_IDS` | **optional** | Comma-separated Discord user ids of the burner sender bots, in token order. Required only for `test_multi_user` and `test_pairing_peers_decoupling` (the ACL peers-axis tests). Absent = those two tests skip locally; other scenarios are unaffected. |
| `THE_ONE_TEST_URL` | optional | the-one HTTP base URL. Defaults to `http://localhost:8484`. |

**`THE_ONE_HAT_BOT_USER_IDS` is optional by design.** Only the two
scenarios that key the ACL `peers` axis on specific user ids read this var.
The other three scenarios (smoke, multi_channel, multi_agent) never read it,
so they run normally when it is absent. This avoids making the whole suite
skip for an operator who doesn't need the ACL tests.

Source the file before running:

```bash
set -a; . tests/live/discord_hat/.env.hat; set +a
```

---

## Running the suite

```bash
# Full HAT suite (all discord_hat-marked tests, env sourced):
set -a; . tests/live/discord_hat/.env.hat; set +a
make test-discord-hat

# Or directly via docker exec (matches the Makefile target):
docker exec the-one pytest -m discord_hat tests/live/discord_hat/ -v --tb=short

# Single scenario:
docker exec the-one pytest tests/live/discord_hat/test_smoke.py -v -s --timeout 300

# Smoke only (fastest — just premises + topology, no ACL mutation):
docker exec the-one pytest tests/live/discord_hat/test_smoke.py -v -s --timeout 120
```

**Use `docker exec the-one pytest …`** — NOT `docker compose exec` in
non-interactive contexts. `docker compose exec` defaults to `-it` (interactive
+ TTY) and hangs forever when stdin is not a TTY. Pass `-T` to disable TTY
if you must use compose.

---

## Skip behaviour — no credentials

With **none** of the required env vars set, every `discord_hat`-marked test
**SKIPs cleanly** (0 errors, 0 failures). This is the default state in CI and
on a fresh dev machine that hasn't provisioned the HAT env.

The normal backend test suite (`make test`) never collects the HAT tests
(they are deselected by the `not discord_hat` clause in `pyproject.toml`
`addopts`).

The two scenarios that also need `THE_ONE_HAT_BOT_USER_IDS` (`test_multi_user`
and `test_pairing_peers_decoupling`) will skip LOCALLY within those tests if
the var is absent, even if the other five required vars are set. The
remaining three scenarios continue to run normally.

---

## Timing rationale: `wait_for_session(until=…)`

The `wait_for_session` helper polls the session **detail** (messages +
`session_metadata.routing`) rather than just session existence. This is
required for any assertion on message history or routing entries.

**Why:** the session row is created early in the dispatch pipeline at
`resolve_session` (before the LLM call), but the inbound message, the F6
`peer_name`, and the engaged routing entry (disposition, agent, rule) are
persisted only **after `agent.step()` completes** — typically several seconds
later when the LLM call returns. Without an `until` predicate the caller races
the dispatch and reads an empty `messages` array or a stale routing state.

**Pattern:**

```python
# Wait for at least one inbound peer_name to appear:
detail = await wait_for_session(
    cfg.base_url, cfg.connector_id, channel_id,
    until=lambda d: bool(inbound_peer_names(d)),
)

# Wait for a specific routing disposition:
detail = await wait_for_session(
    cfg.base_url, cfg.connector_id, channel_id,
    until=lambda d: (latest_routing_entry(d) or {}).get("disposition") == "stepped",
)
```

When `until` is `None`, `wait_for_session` returns as soon as the session
resolves (topology / existence checks only).

---

## Connect-time closure — container restart requirement

The `ingest_bots` configuration flag is read from `account.config` at
**connect time** (inside the `on_message` closure captured when the Discord
client connects). It is NOT read fresh on every dispatch — the value is
captured in the closure at startup.

**Consequence:** if you change `ingest_bots` on the connector (via the Admin
UI or the API), the running container is still using the old value. You MUST
restart the container for the new setting to take effect:

```bash
docker restart the-one
# or:
make down && make up
```

Other fields like `always_listen` and `dm_admission` are read fresh on every
dispatch and do NOT require a restart.

---

## Bot-can't-DM-bot constraint (REST 50007)

Discord's REST API returns `50007 Cannot send messages to this user` when a
bot attempts to open a DM to another bot. This is a platform-level constraint.

**Impact on the HAT:**
- The `bots.dm()` driver method cannot be used to DM the-one's own bot from
  a burner sender bot.
- The DM-isolation topology premise (a DM to the-one keying on its own session
  distinct from the guild channel session) is verified in the **L7 interactive
  pass** using a real human account — not automated via `bots.dm()`.
- Any scenario that exercises DM pairing, approval UX, or DM-channel sessions
  requires a human operator using a real Discord account (Chrome MCP pass).

---

## Scenario catalogue

| File | What it tests |
|---|---|
| `test_smoke.py` | Three load-bearing premises: author-agnostic `@mention` engages (`stepped`); F6 `peer_name` attribution (bot-peer ingestion); negative control non-mention → `policy-silent`/`always-listen-off`. |
| `test_multi_user.py` | Three burner bots → one shared channel session (topology #5); all three F6 `peer_name`s attributed (#13); per-user ACL overlay routes bot0/bot1 to Agent 1 and bot2 to Agent 2 (#5 differentiation); both-agents-exclude-bot2 → `no-eligible` (#5 hard-deny). Requires `THE_ONE_HAT_BOT_USER_IDS`. |
| `test_multi_channel.py` | Per-channel routing rules: ch1→Agent 1, ch2→Agent 2, ch3→default (Agent 1); three channels → three distinct session ids (#6); ch3 channel-scoped override re-routes away from default (#6). |
| `test_multi_agent.py` | `/talk-to` override intercept (`command-intercepted`/`builtin`); next `@mention` routes to the target (`scope=override`/`reason=override`); override beats a channel rule (Phase B); dynamic re-override to a different agent (Phase C) (#7). |
| `test_pairing_peers_decoupling.py` | Account-scope `peers` narrowing to one approved peer does NOT lock guild channels (the F16 L1 fix regression gate): a DIFFERENT, un-approved bot's channel `@mention` is still admitted (`stepped`, not `no-eligible`). Requires `THE_ONE_HAT_BOT_USER_IDS`. |

---

## Known operational gotchas

**Re-provisioning bots invalidates `THE_ONE_HAT_BOT_USER_IDS`.**  
If you create new bot apps (e.g. because tokens expired or you want a fresh
setup), the bot user ids change. Update `THE_ONE_HAT_BOT_USER_IDS` in
`.env.hat` to match the new ids. The var is now in the env contract (not
hardcoded in source) precisely to make re-provisioning a one-file change.

**The test connector must have `ingest_bots=true`.**  
The-one's Discord connector by default ignores bot-authored messages
(`ingest_bots=false`). The test connector MUST have `ingest_bots=true` for
the burner bots to be ingested as peers. After changing this setting, restart
the container (see connect-time closure above). If the smoke sees no session
after timeout, `ingest_bots` is the first suspect — check `docker logs the-one`.

**Both Connector Agent 1 and Connector Agent 2 must be attached.**  
The multi-user and multi-channel scenarios assert on routing to specific
agents. If only one agent is attached, the connector won't warm at startup
("no attached agents") and all routing tests will fail or behave unexpectedly.
Attach both via the Admin UI → Connectors → the test connector → Agents.

**Agent `connector_acls` and connector `routing` are RESTORED in `finally`.**  
The ACL and routing scenarios mutate live config, then restore it in a
`finally` block (capturing the prior value before mutating). A mid-test crash
still restores the prior. A second run passes without manual cleanup.
