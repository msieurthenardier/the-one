# Behavior Test: Charts Reach Chat Platforms

**Slug**: `charts-reach-platforms`
**Status**: draft
**Created**: 2026-11-11
**Last Run**: never

> Draft at Mission 35 Flight 3 planning. It fixes the key observables and the rough steps. Leg 6 (`seam-and-round-trip`) finalizes the control-route names and the exact commands and sets the status to `active`.

## Intent
This test checks that a reply carrying charts and a widget goes out through Discord and Telegram the way Mission 35 Flight 3 designed. Each chart arrives as a PNG image after the text, with a marker line where the chart was and the chart's title as caption or alt text. The widget arrives as a note. When an upload fails, the chart's source arrives as a code block. The stored chat keeps the agent's text unchanged.

It is a behavior test because the chain spans several components and only shows end to end:
- the platform client's real inbound path (the Discord gateway, Telegram polling);
- the connector pipeline and the agent loop;
- the server-side drawing, the multipart upload and the stored chat.

Unit tests pin each piece with mocks. This proves that they compose in a running app.

The platforms are local fakes (`scripts/fake_platforms.py`, operator decision 2026-11-11). The test proves what the app sends, not what Discord or Telegram show.

## Preconditions
- **The fake platforms**, started first on a port of 8490 or higher, with its saved-files directory under the scratch area:
  `<repo>/.venv/bin/python <repo>/scripts/fake_platforms.py --port <fport> --save-dir $HOME/the-one-behavior-test-scratch/fake-files`
  Check with `curl http://127.0.0.1:<fport>/_control/health` → 200.
- **The dev instance**, started from a scratch working directory (CLAUDE.md "SAFETY RULE"; never port 8484/8485 or the default data directory):
  ```bash
  mkdir -p $HOME/the-one-behavior-test-scratch/cwd && cd $HOME/the-one-behavior-test-scratch/cwd
  THE_ONE_PORT=<port> THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data \
    THE_ONE_DEV_MODE=true THE_ONE_FAKE_PLATFORMS_URL=http://127.0.0.1:<fport> \
    <repo>/.venv/bin/the-one serve >serve.log 2>&1 &
  echo $! > serve.pid
  ```
  Create the credential with `THE_ONE_DATA_DIR=... the-one rotate-api-credential`. Every API call is a shell-only call with `Authorization: Bearer <credential>` (CLAUDE.md "Behavior-test credential convention").
- **Seeding through the API:**
  - A `mock` provider whose scripted `response.content` is a reply with text, one valid ```` ```chart ```` block (title "Revenue by region"), one ```` ```widget ```` block and closing text.
  - An agent on that provider.
  - A Discord connector and a Telegram connector with fake tokens, each with that agent as `default_agent` and the test sender on the allowlist.
- Record both PIDs, and stop both by PID afterwards.

## Observables Required
- http: the fake's `/_control/received` records, and the app's chat-session API (via curl in the shell)
- filesystem: the PNGs the fake saved; the Validator opens them to judge that each one is a chart
- shell: the server logs for the fallback warning

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Reset the fake. Through the fake's control route, inject a Discord direct message from the test sender. Admission needs a DM, a mention or `always_listen`, and the inject route defaults to a DM. | (setup) |
| 2 | (wait) | Within 30 s, the fake has received exactly one Discord `POST /channels/{id}/messages` as multipart:<br>- `payload_json.content` holds the reply's text in order, with `📊 Chart: Revenue by region (below)` where the chart was and `🧩 Interactive widget: open this chat in the app to see it.` where the widget was;<br>- no ```` ```chart ```` or ```` ```widget ```` source is in the content;<br>- one `files[0]` PNG whose `attachments[0].description` is "Revenue by region". |
| 3 | Open the saved PNG from step 2. | The image is a bar chart on a light card (near-white `#fafafa` with a thin grey edge) titled "Revenue by region", with readable axis text and bars in the light chart palette. The decoded size is 1280 px wide (640 logical at 2×). |
| 4 | Read the Discord chat session's stored messages through the app API. | The stored assistant message is the scripted reply verbatim: it still contains the ```` ```chart ```` and ```` ```widget ```` blocks, and no marker or note. |
| 5 | Reset the fake. Inject a Telegram inbound update from the test sender. | (setup) |
| 6 | (wait) | Within 30 s, the fake has received one `sendMessage` whose text holds the marker and the widget note and no visual source, followed by one multipart `sendPhoto` to the same `chat_id` with caption "Revenue by region" and a PNG `photo`. |
| 7 | Reset the fake. Set it to fail the next upload with HTTP 413. A 4xx means nothing was posted, so a resend is safe; a 5xx is never re-sent (DD7). Inject another Discord inbound message. | (setup) |
| 8 | (wait) | Within 30 s, the fake has received one failed multipart message and then one JSON message whose `content` contains the chart's ```` ```chart ```` block as code and the widget note. The server log shows one fallback warning that names the chart's index and not its data. |
| 9 | Make three changes through the app API, then reset the fake and inject a Telegram update:<br>- Change the mock provider's scripted response to a `send_to_platform_channel` tool call whose `content` is a reply with a chart, sent to the Telegram target.<br>- Set the agent's `max_iterations` to 1. The mock returns the same response on every call, so a single step is the only way to send exactly once.<br>- Leave everything else unchanged. | (setup) |
| 10 | (wait) | The fake has received the tool send's text, with the marker, and its `sendPhoto` exactly once. Then it has received the step-limit line as plain text. No second copy of the chart arrives (the no-double-send rule). |

## Out of Scope
- What Discord or Telegram show to a reader. The fakes cannot prove it; this residual is recorded in SECURITY-MODEL.md.
- Message length splitting (not in scope for the mission).
- Live widgets in the app (`widget-escape`).
- The stub connector's record shape (unit tests).

## Variants (optional)
- A reply with an invalid chart. The block arrives as code with no image and no marker.
