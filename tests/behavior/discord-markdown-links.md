# Behavior Test: Discord Markdown Links

**Slug**: `discord-markdown-links`
**Status**: draft
**Created**: 2026-10-14
**Last Run**: never

## Intent
This test proves Mission 30's link criterion through a real connector: when an agent replies with a link through the Discord connector, the link reaches Discord **usable**. Either a `[text](url)` markdown link arrives intact, or the URL itself arrives unbroken. The test also checks that the same reply shows as a clickable link in the app's chat view.

Unit tests cannot cover this. It depends on a real model choosing the link format under the platform prompt, on the connector's outbound path (`connectors/discord/_rest.py` posts `{"content": …}` with no transformation or splitting), and on Discord's own handling of the message. The test reads Discord's stored message content, not its rendering: Discord's documentation does not say whether bot messages render masked links, and the criterion is that the link stays usable either way.

## Preconditions
- **Dev instance boot** from the project root. Use port **8486** and a scratch data directory **under `$HOME`** (a Mission 29 lesson: not `/tmp`). Never use 8484, 8485 or the operator's default data directory (CLAUDE.md "SAFETY RULE").
  ```bash
  THE_ONE_PORT=8486 THE_ONE_DATA_DIR=$HOME/the-one-hat-scratch-m30 THE_ONE_DEV_MODE=true make up
  ```
  Check liveness with `curl http://127.0.0.1:8486/api/live`, which should return HTTP 200. Tear down with `THE_ONE_PORT=8486 THE_ONE_DATA_DIR=$HOME/the-one-hat-scratch-m30 make down`, then delete the scratch directory.
- **Credential.** Follow CLAUDE.md's "Behavior-test credential convention". Read `$HOME/the-one-hat-scratch-m30/api-credential`; if it is absent, run `THE_ONE_DATA_DIR=$HOME/the-one-hat-scratch-m30 the-one rotate-api-credential` (squawk 0195). Send `Authorization: Bearer <credential>` on every app-API call, and mint a handoff URL for the browser.
- **Model.** A "Claude Plan (Token)" provider (`anthropic-plan-token`, model `claude-haiku-4-5-20251001`).
  - A `python3` script creates it. The script reads `~/.config/the-one-evals/plan-token` itself and prints only status and booleans. **The token is never printed, quoted or put on a command line.**
  - An agent `link-agent` is bound to this provider, with an ordinary one-line system prompt ("You help people find things.") and no formatting instruction. Any formatting behaviour must come from the platform prompt.
- **Discord.** Use the env contract in `tests/behavior/.env.hat` (`THE_ONE_HAT_DRIVER_TOKEN`, `THE_ONE_HAT_MAIN_TOKEN`, `THE_ONE_HAT_GUILD_ID`, `THE_ONE_HAT_TEST_CHANNEL_ID`).
  - Re-verify at run start that both bot tokens authenticate (`GET /users/@me` returns 200 for each, status only).
  - Re-verify that the **driver** bot has the Message Content intent. Without it, REST reads return `content: ""` (see `discord-live-round-trip`).
- **Connector.** A Discord connector row for the MAIN bot, created through the app API:
  - `default_agent: link-agent`
  - the driver bot's user ID on `allowlist.peers`
- **Network.** Outbound access to `discord.com`, `gateway.discord.gg` and `api.anthropic.com`.

## Observables Required
- **http**:
  - Driver-bot Discord REST (`https://discord.com/api/v10`, `Authorization: Bot <driver token>`): `POST /channels/{id}/messages` to act, and `GET /channels/{id}/messages` to read the main bot's reply content.
  - App API: `POST /api/connectors/{id}/test` and `GET /api/chat/sessions`.
- **browser**: the app's chat view for the connector session (link rendering in-app).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | `POST /api/connectors/{id}/test` with the credential. | Doctor `status: "ok"` and the gateway is connected; no binding warning for `link-agent`. |
| 2 | Driver bot posts in `THE_ONE_HAT_TEST_CHANNEL_ID`: `<@MAIN_BOT_ID> Could you give me a link to the Python docs home page? It's https://docs.python.org/3/` | Within 90 s, a main-bot message appears in the channel (driver REST read). Its `content` contains the exact substring `https://docs.python.org/3/` unbroken. If it contains `](`, then the substring `](https://docs.python.org/3/` is present and the link text before it is enclosed in `[…]`. `content` length < 2000. |
| 3 | Driver bot posts: `<@MAIN_BOT_ID> And a link to the Wikipedia article on the Python language, please: https://en.wikipedia.org/wiki/Python_(programming_language)` | Within 90 s, a main-bot reply appears whose `content` contains `https://en.wikipedia.org/wiki/Python_(programming_language)` with the closing parenthesis intact (not truncated to `…Python_(programming_language`). Any markdown link around it is well-formed. `content` length < 2000. |
| 4 | In the app (browser, handoff-authenticated), open the Chats list, open the connector session for `THE_ONE_HAT_TEST_CHANNEL_ID`, and inspect the two agent replies. | Each reply shows a link element (`a[href]`) whose `href` equals the URL from steps 2 and 3, with no literal `[`/`](` markdown syntax visible around it. No error message is shown. [a11y] Each link has non-empty accessible text. |

## Out of Scope
- Discord client rendering of masked links (not observable through REST, and outside the criterion).
- Link formatting in the web chat with no connector: covered by the `markdown-links` eval scenario on both models.
- Message splitting above 2000 characters: the connector does not split. That is noted, not tested here.
