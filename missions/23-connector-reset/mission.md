# Mission: Connector Reset

**Status**: planning

## Outcome

The connector subsystem does one job and does it at a weight the project can
carry: a person messages the bot on an external platform, the attached agent
replies in the same place, and the agent can speak first through one send
tool. The operator keeps the private console — everything peers and the bot
exchanged, plus the operator's own side-chat with the agent, visible in the
local Chat UI, with operator-typed messages never leaking to the platform.

Discord keeps working, on a small in-house gateway + REST client built on the
`websockets` and `httpx` the app already ships, so the runtime dependency
closure loses `discord.py` and the eight packages it drags in. A second
platform — Telegram — lands through the same contract and proves the seam is
actually additive, the one criterion Mission 10 set for itself and never met.

Everything that existed to make one bot serve many agents under a
many-dimensional permission model is removed rather than rebuilt: the routing
engine and its rules editor, the four-axis ACL and its per-agent overlays, the
Discord-native approval queue, the slash-command surface, the LLM engagement
gate, the live discoverable dropdowns. What replaces them is a flat allowlist,
a pairing code for first contact, one agent per connector, and a reply policy
of "DMs and @mentions, plus channels the operator marks always-listen."

## Context

Missions 10 and 11 built the connector substrate and made Discord the
operator's daily driver — 25 flights, ~30k insertions. Both debriefs are
candid: M10 landed "substrate-validated, far from shippable"; M11 closed that
gap and then judged itself "HUGE and probably should have been split." The
result is 9,050 Python lines under the connector umbrella (of which only
~2,300 are Discord-specific — the rest is platform-agnostic machinery), 7,973
lines of Studio JS (`connector-editor.js` alone is 4,982, the largest JS file
in the project and the 2026-08-27 maintenance report's "strongest split
candidate"), 18 REST routes, ~890 tests (≈19% of the suite), and an 80 KB
package README. The M11 debrief names `_acl.py` "a genuine maintenance risk";
the 08-27 report flags the 242-line `connector_acls` validator and the
426-line `Connector` reserved-key validator as oversized.

The research brief that precedes this mission (2026-08-27) established three
things that shape the scope:

- **There is no library to swap in.** Every Python "multi-platform bot
  framework" is archived (botbuilder), GPL and thread-based (errbot),
  daemon-shaped with no Discord (opsdroid), or aimed at other platforms
  (NoneBot2). The two large MIT Python projects that solved this problem in
  2026 — Hermes Agent and nanobot — both converged on a thin in-house channel
  layer plus one small client per platform. That is the shape we have, at
  roughly ten times the necessary weight.
- **`aiohttp` is unavoidable with any Python Discord library** (discord.py,
  py-cord, disnake, nextcord, hikari, interactions.py all hard-depend on it).
  Its CVE floor was raised in the 06-04, 07-10 and 08-07 maintenance cycles.
  The only way out is a hand-rolled bot-only client — an honest 700–1,100
  lines on a protocol (Gateway v10) unchanged since 2022. Our current pin
  (`<2.5`; current is 2.7.1) also carries a latent Python 3.13 ceiling via the
  removed `audioop` module.
- **More platforms is cheap only if the app stays endpoint-free.** Discord
  (gateway), Telegram (long-poll), Slack (Socket Mode), Matrix (sync) work with
  nothing exposed. WhatsApp-official, Teams and SMS require a public HTTPS
  endpoint, which inverts the local-only posture in `SECURITY-MODEL.md`.

The project's standing policy of limiting third-party libraries applies here
with unusual force: the one chat SDK we carry is the one that costs the most
maintenance, and the platforms worth adding next cost zero new dependencies
when done directly against their APIs.

## Success Criteria

- [ ] `discord.py` and `aiohttp` are absent from the runtime dependency
      closure (`uv.lock` resolved from `pyproject.toml` base dependencies),
      and no third-party chat-platform SDK is present in base dependencies.
- [ ] A Discord peer who DMs or @mentions the bot receives the attached
      agent's reply in the same channel, thread, or DM; the agent can send a
      message the peer did not prompt via the single send tool; the bot
      resumes automatically after a gateway disconnect — all observed live
      against a real Discord bot.
- [ ] A Telegram peer gets the same round-trip through the same contract,
      and the Telegram platform adds no files outside its own module and its
      registration site.
- [ ] The Chat UI shows the unified history for a connector-bound session
      with operator-only messages distinguished from peer-visible ones, and an
      operator-typed message never reaches the external platform — the
      existing `Message.visibility` semantic, retained not rebuilt.
- [ ] Connector credentials remain Fernet-encrypted at rest, masked in every
      response, and enrolled in `POST /api/encryption/rotate`.
- [ ] Admission is a flat allowlist of peer and channel identifiers plus a
      pairing code for first contact; an unknown sender gets silence and
      nothing is persisted for them. There is no LLM-based engagement gate,
      no per-agent ACL overlay, and no approval queue.
- [ ] Exactly one agent serves a connector (with an optional channel→agent
      map if Open Question 3 resolves that way); there is no routing engine,
      no routing rules, and no routing audit log.
- [ ] The `pending_approvals` table and the `agents.connector_acls` /
      `connector_always_listen` columns are retired by a single new migration;
      an existing database with legacy connector rows and legacy agent JSON
      upgrades cleanly and its Discord connector keeps working after the
      operator re-saves it in the new form.
- [ ] The connector subsystem — `the_one/connectors/` including both platform
      clients, plus the connector tools — is at most 3,000 Python lines, and
      the connector Studio UI is at most 1,000 JS lines.
- [ ] `make test-unit` and every browser lane pass; the tests for removed
      capabilities are deleted, not skipped; the `discord_hat` marker and its
      Makefile target are gone; a new live HAT exists for Discord and Telegram.
- [ ] `the_one/connectors/README.md`, `the_one/agents.md`, `SECURITY-MODEL.md`,
      `CLAUDE.md` and `README.md` describe the new contract, with no remaining
      references to routing, ACL axes, peer approvals, slash commands, or the
      engagement gate.
- [ ] The Windows packaged build (Concourse) still builds and the packaged
      smoke check passes with the smaller closure.

## Stakeholders

- **Operator (device owner)** — runs the Discord bot daily. Needs the reset to
  cost nothing in daily use: same bot, same channels, same private console,
  fewer knobs. Wants Telegram reachable next.
- **Maintenance cycles** — carry the aiohttp CVE floor, the oversized
  validators, the largest JS file, and 19% of the test suite on this
  subsystem. This mission is the structural fix for all four.
- **Future platforms (Slack, Matrix, Signal, email)** — inherit the contract
  Flight 4 proves; each is a small client, none needs a public endpoint.

## Constraints

- **No third-party chat-platform SDK in base dependencies.** Discord is built
  on `websockets` + `httpx`; Telegram on `httpx` against the Bot API. A future
  platform that genuinely needs an SDK (Slack Socket Mode via `slack_sdk`)
  is an optional extra and a separate mission — decided then, not here.
- **No public inbound endpoint.** Every platform in scope must work by the
  app connecting out (gateway, long-poll). The local-only, no-listener posture
  in `SECURITY-MODEL.md` is retained. Webhook-driven platforms stay out of
  scope, as in M10.
- **The agent loop is not modified.** `agent/core.py` and `agent/factory.py`
  stay as they are except for removing the `send_to_platform_channel`
  baseline carve-out if the tool's visibility is handled another way. Same
  constraint M10 carried and met.
- **Removal lands first and lands green.** Flight 1 deletes; it does not
  rebuild. The tree after Flight 1 has no connector runtime and a green
  suite. This is what makes the mission reversible flight-by-flight.
- **The six kept pieces are kept, not rewritten:** the encrypted connector
  row with masked-edit CRUD and a doctor probe; session keying on
  `(platform, connector_id, channel_id, thread_id, peer_id)` with the
  continuation window; `Message.visibility`; the single send tool as the
  only agent→platform path; the `set_factory()`/`get_factory()` accessor;
  and the `chat_sessions` platform columns and partial index. No chat-history
  migration.
- **The migration ledger is append-only.** v13–v29 remain as history; this
  mission adds one migration step. The `connectors.type` CHECK constraint
  changes only via the established table-rename ceremony.
- **Criteria come from the one-job statement, not from M10/M11's deferral
  lists.** The M11 debrief's first lesson. Nothing deferred by M10 or M11 is
  in scope unless it appears in the Success Criteria above.
- **Live verification never targets port 8484** or the operator's default
  data directory — dedicated dev instance only, per the standing rule.
- **Planning-only skills do not implement.** Implementation runs through
  `/agentic-workflow`.

## Environment Requirements

- Local toolchain; `make test-unit` is the canonical gate; browser lanes via
  `scripts/run-tests.sh --lane studio|chat|system|shared`.
- A Discord application + bot token with Message Content intent enabled, and
  a test guild the operator controls — the same apparatus
  `tests/live/discord_hat/` uses today (its config/env conventions can be
  reused by the replacement live HAT).
- A Telegram bot token from @BotFather and a Telegram account to drive it.
- A dedicated dev instance (`THE_ONE_PORT=8485` + scratch `THE_ONE_DATA_DIR`)
  for live and behavior-test verification.
- Concourse access for the Windows packaged build and smoke check (squawk
  0015 — the unlocked Windows closure — interacts with the dependency
  change; a smaller closure helps it, but confirm the build path resolves
  from the new lock).
- Network egress to `discord.com`/`gateway.discord.gg` and `api.telegram.org`
  from the dev machine.

## Open Questions

1. **Telegram: raw Bot API or `python-telegram-bot`?** The constraint above
   answers this (raw `getUpdates` long-poll on `httpx`, ~300 lines, zero
   deps), but PTB is LGPL and `httpx`-only and would save writing the
   client. Confirm the constraint holds before Flight 4 is specced.
2. **Does anything else re-introduce `aiohttp` once `discord.py` leaves?**
   Verify with a fresh `uv lock` after Flight 1; if a transitive path remains,
   the first criterion needs re-wording, not quiet failure.
3. **One agent per connector, or connector default + channel→agent map?** A
   flat map is a config field, not an engine, and covers "this channel is the
   coding agent's." Recommend the map; decide before Flight 2's contract is
   fixed.
4. **History tool: shrink to "last N messages" or drop?** The current
   546-line tool fetches channel and DM history. A 40-line "last N" is the
   common case. Decide in Flight 2.
5. **Text commands: keep `/new` only?** Recommend yes — a peer needs a way
   to start a fresh session; nothing else in the six-command vocabulary
   survives one-agent-per-connector.
6. **Existing Discord connector rows on upgrade.** Keep the row and prune
   reserved config keys in the migration (recommended), or require the
   operator to re-create the connector? The eighth criterion assumes keep.
7. **Where does the fake-gateway test fixture live?** A `websockets.serve`
   Discord gateway double is the natural unit fixture for Flight 3; decide
   whether it belongs under `tests/_sandbox_fixtures.py`-style shared helpers
   or the Discord module's own tests.

## Known Issues

*(none yet — populated as flights surface blockers)*

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [ ] Flight 1: Remove — delete `the_one/connectors/`, the connector tools,
      the Studio connector editor and Chat approval/audit panels, the 18
      routes, the lifespan warm-acquire/pool-drain, `AgentConfig` ACL fields
      and validator, `PendingApproval`; one migration retiring
      `pending_approvals` and the agent ACL columns; `discord.py` and the
      aiohttp CVE-floor block out of `pyproject.toml`, lock regenerated;
      `discord_hat` marker, Makefile target, `tests/live/discord_hat/`, the
      11 connector behavior specs and ~52 test files removed; PyInstaller
      `nacl` exclusion removed; docs reduced to a stub contract. Ends green
      with no connector runtime.
- [ ] Flight 2: Channel contract — one Protocol
      (`connect` / `disconnect` / `send` / `doctor` + an inbound callback),
      one long-lived listener task per connector with reconnect, the kept
      session keying and send tool re-attached, flat allowlist + pairing
      code, the DM / mention / always-listen reply policy, `/new`, a minimal
      Studio form, the in-process stub plugin, and the rewritten
      `connectors/README.md` and `agents.md` section. Target ≤1,500 Python
      lines including the stub.
- [ ] Flight 3: Discord on a hand-rolled client — gateway task (hello,
      heartbeat with jitter, identify with intents, resume to
      `resume_gateway_url`, reconnect with backoff, non-reconnectable close
      codes 4004/4010–4014), REST client with per-bucket + global rate
      limiting and 429 handling, the ~10 endpoints a text bot needs, a
      fake-gateway fixture, a live HAT and a behavior test against the
      operator's bot.
- [ ] Flight 4: Telegram — second platform through the same contract on
      `httpx` long-poll; proves the "no files outside its own module and
      registration site" criterion; live HAT.
- [ ] Flight 5 *(optional)*: Alignment — vibe coding session for creative
      collaboration and hands-on adjustments.

**Pre-declared split point:** if Flight 1's deletion cannot land green
without partially rebuilding (most likely because the Chat UI's connector
session rendering or the encryption-rotation invariant tests need a live
connector row to exercise), stop and split — a "stub-only connector row"
flight between 1 and 2 — rather than letting the delete flight absorb
rebuild work. The M11 "gate-sweep batch" lesson applies in reverse: a delete
flight that starts building is the same scope explosion.
