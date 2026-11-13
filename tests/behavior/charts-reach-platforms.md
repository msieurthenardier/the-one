# Behavior Test: Charts Reach Chat Platforms

**Slug**: `charts-reach-platforms`
**Status**: active
**Created**: 2026-11-11
**Last Run**: 2026-11-12 (pass, `runs/2026-11-12-23-52-13.md`)

> Finalized at Mission 35 Flight 3 Leg 6 (`seam-and-round-trip`). The commands below were dry-checked through the Preconditions only; the steps are run by the Flight Director.

## Intent
This test checks that a reply carrying charts and a widget goes out through Discord and Telegram the way Mission 35 Flight 3 designed. Each chart arrives as a PNG image after the text, with a marker line where the chart was and the chart's title as caption or alt text. The widget arrives as a note. When an upload fails, the chart's source arrives as a code block. The stored chat keeps the agent's text unchanged.

It is a behavior test because the chain spans several components and only shows end to end:
- the platform client's real inbound path (the Discord gateway, Telegram polling);
- the connector pipeline and the agent loop;
- the server-side drawing, the multipart upload and the stored chat.

Unit tests pin each piece with mocks. This proves that they compose in a running app.

The platforms are local fakes (`scripts/fake_platforms.py`, operator decision 2026-11-11). The test proves what the app sends, not what Discord or Telegram show.

## Preconditions
Every command is a shell command. Nothing here touches port 8484, 8485 or the operator's default data directory (CLAUDE.md "SAFETY RULE"); the instance uses its own ports and a scratch data directory. Never print the credential.

1. **Variables** (use these in every later command; pick other ports of 8490 or higher if these are taken, and a different `S` if it exists and is not yours):
   ```bash
   export R=/home/cprch/projects/the-one S=$HOME/m35f3-l6-scratch PORT=8490 FPORT=8491
   export DATA=$S/data B=http://127.0.0.1:$PORT F=http://127.0.0.1:$FPORT
   mkdir -p $S/cwd $S/fake-files $DATA
   api() { curl -sS -H "Authorization: Bearer $(cat $DATA/api-credential)" -H 'Content-Type: application/json' "$@"; }
   ```
2. **The fake platforms**, started first, from the scratch working directory:
   ```bash
   cd $S/cwd
   $R/.venv/bin/python $R/scripts/fake_platforms.py --port $FPORT --save-dir $S/fake-files >fake.log 2>&1 &
   echo $! > $S/cwd/fake.pid
   curl -s $F/_control/health     # -> {"ok":true}
   ```
3. **The credential, then the dev instance** (same scratch cwd; the variable is read from the process environment and only with dev mode on):
   ```bash
   THE_ONE_DATA_DIR=$DATA $R/.venv/bin/the-one rotate-api-credential >/dev/null
   cd $S/cwd
   THE_ONE_PORT=$PORT THE_ONE_DATA_DIR=$DATA THE_ONE_DEV_MODE=true \
     THE_ONE_FAKE_PLATFORMS_URL=$F $R/.venv/bin/the-one serve >serve.log 2>&1 &
   echo $! > $S/cwd/serve.pid
   until curl -sf $B/api/live >/dev/null; do sleep 1; done
   ```
4. **Seeding** (the bodies are built by Python so the nested JSON is never hand-escaped; the sender ids are Discord `4242` and Telegram `5151`, the exact values the steps inject, and Telegram's DM chat id equals its sender id):
   ```bash
   S=$S $R/.venv/bin/python - <<'EOF'
   import json, os
   S = os.environ["S"]
   chart = {"type": "bar", "title": "Revenue by region",
            "x": {"values": ["North", "South", "East", "West"]},
            "y": {"label": "Revenue", "unit": "k"},
            "series": [{"name": "2026", "values": [120, 95, 140, 80]}]}
   reply = ("Here are the numbers.\n\n```chart\n" + json.dumps(chart) + "\n```\n\n"
            "And a live view:\n\n```widget\n<div>hello</div>\n```\n\nThat is all.")
   def w(name, body):
       open(f"{S}/{name}.json", "w").write(json.dumps(body))
   w("provider", {"name": "mockp", "type": "mock", "base_url": "",
                  "config": {"response": {"content": reply}}})
   w("disc", {"id": "disc1", "name": "Fake Discord", "type": "discord", "secrets": {"token": "fake-discord-token"},
              "config": {"default_agent": "chartbot", "allowlist": {"peers": ["4242"]}}})
   w("tg", {"id": "tg1", "name": "Fake Telegram", "type": "telegram", "secrets": {"token": "123456:fake-telegram-token"},
            "config": {"default_agent": "chartbot", "allowlist": {"peers": ["5151"]}}})
   # step 9: the provider's reply becomes one tool call
   send = {"content": "Tool send.\n\n```chart\n" + json.dumps(chart) + "\n```\n",
           "target": {"connector_id": "tg1", "peer_id": "5151"}}
   w("script9", {"content": "Done.", "tool_calls": [{"id": "tc1", "name": "send_to_platform_channel", "arguments": send}]})
   EOF
   api -X POST $B/api/providers -d @$S/provider.json > $S/provider.out
   PID=$($R/.venv/bin/python -c "import json,sys;print(json.load(open('$S/provider.out'))['id'])")
   echo "{\"name\":\"chartbot\",\"provider_config_id\":\"$PID\",\"llm_model\":\"mock-default\",\"system_prompt\":\"You are a test agent.\"}" > $S/agent.json
   api -X POST $B/api/agents -d @$S/agent.json          # 201
   api -X POST $B/api/connectors -d @$S/disc.json       # 201
   api -X POST $B/api/connectors -d @$S/tg.json         # 201
   ```
5. **Start-up check** (a seam failure is caught here, before step 1):
   - `grep -c "connectors use the fake platforms at http://127.0.0.1:$FPORT" $S/cwd/serve.log` prints `1`.
   - `api -X POST $B/api/connectors/disc1/test` and `api -X POST $B/api/connectors/tg1/test` both succeed against the fake (`"status":"ok"`, "gateway connected" and "poll loop connected").
6. Record both PIDs (`$S/cwd/fake.pid`, `$S/cwd/serve.pid`) and stop both by PID afterwards (`kill $(cat ...)`); never stop anything by name. (Start each process from a plain `cd` line, as above, not `cd … && cmd &`, which records a subshell's PID, not the server's.)

## Observables Required
- http: the fake's `GET $F/_control/received` records (`{"records": [...]}`, one per send: `seq`, `platform`, `method`, `path`, `json`, `fields`, `files`, `status`), and the app's chat-session API (`GET $B/api/chat/sessions`, `GET $B/api/chat/sessions/{id}`) via curl in the shell
- filesystem: the PNGs the fake saved under `$S/fake-files`; the Validator opens them by path to judge that each one is a chart
- shell: `$S/cwd/serve.log` for the fallback warning

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Reset the fake: `curl -s -X POST $F/_control/reset`. Inject a Discord direct message from the test sender (a DM is the default for a `channel_id`-less inject): `curl -s -X POST $F/_control/discord/inject -H 'Content-Type: application/json' -d '{"author_id":"4242","content":"show me the numbers"}'` (the answer is `{"ok": true, "channel_id": ...}`). | (setup) |
| 2 | (wait up to 30 s, polling `GET $F/_control/received`) | The fake has received exactly one Discord `POST /channels/{id}/messages` as multipart:<br>- `payload_json.content` holds the reply's text in order, with `📊 Chart: Revenue by region (below)` where the chart was and `🧩 Interactive widget: open this chat in the app to see it.` where the widget was;<br>- no ```` ```chart ```` or ```` ```widget ```` source is in the content;<br>- one `files[0]` PNG whose `attachments[0].description` is "Revenue by region" (look in `fields`/`json` for `payload_json`). |
| 3 | Open the saved PNG from step 2 (the newest `*files_0_*` file under `$S/fake-files`). | The image is a bar chart on a light card (near-white `#fafafa` with a thin grey edge) titled "Revenue by region", with readable axis text and bars in the light chart palette. The decoded size is 1280 px wide (640 logical at 2×). |
| 4 | Read the Discord chat session's stored messages through the app API (`GET $B/api/chat/sessions`, pick the row with platform `discord`, then `GET $B/api/chat/sessions/{id}`). | The stored assistant message is the scripted reply verbatim: it still contains the ```` ```chart ```` and ```` ```widget ```` blocks, and no marker or note. |
| 5 | Reset the fake. Inject a Telegram inbound update from the test sender: `curl -s -X POST $F/_control/telegram/inject -H 'Content-Type: application/json' -d '{"from_id":5151,"text":"show me the numbers"}'`. | (setup) |
| 6 | (wait up to 30 s) | The fake has received one `sendMessage` whose text holds the marker and the widget note and no visual source, followed by one multipart `sendPhoto` to the same `chat_id` (5151) with caption "Revenue by region" and a PNG `photo`. |
| 7 | Reset the fake. Set it to fail the next upload with HTTP 413 (a 4xx means nothing was posted, so a resend is safe; a 5xx is never re-sent, DD7): `curl -s -X POST $F/_control/fail-next -H 'Content-Type: application/json' -d '{"count":1,"status":413,"kind":"upload"}'`. Record the baseline (read-only): `wc -l < $S/cwd/serve.log` and `grep -c "falling back to text" $S/cwd/serve.log`. Inject another Discord message as in step 1. | (setup) |
| 8 | (wait up to 30 s) | The fake has received one multipart message with `status` 413 and then one JSON message (status 200) whose `content` contains the chart's ```` ```chart ```` block as code and the widget note. `$S/cwd/serve.log` gains exactly one fallback warning during the step: `grep -c "falling back to text" $S/cwd/serve.log` increases by exactly 1, and the new line names `charts [0]` and `status 413` and contains neither the chart's title nor its data nor the platform's response body. |
| 9 | Make two changes through the app API (no restart: the agent and provider are re-read per message), then reset the fake and inject a Telegram update as in step 5:<br>- Change the mock provider's scripted response to the `script9` body (a `send_to_platform_channel` tool call whose `content` holds a chart, sent to the Telegram DM target): `api -X PUT $B/api/providers/$PID -d "$($R/.venv/bin/python -c "import json;p=json.load(open('$S/provider.json'));p['config']={'response':json.load(open('$S/script9.json'))};print(json.dumps(p))")"`.<br>- Set the agent's `max_iterations` to 1 (the mock returns the same response on every call, so a single step is the only way to send exactly once): fetch it with `api $B/api/agents/chartbot`, set `max_iterations` to 1 in that JSON, and `PUT` it back to `$B/api/agents/chartbot`. | (setup) |
| 10 | (wait up to 30 s) | The fake has received the tool send's text, with the marker, and its `sendPhoto` exactly once. Then it has received the step-limit line (`STEP_LIMIT_LINE` in `the_one/connectors/delivery.py`) as plain text: a plain `sendMessage` with no chart or widget markup. Telegram's HTML `parse_mode` is its normal send path. No second copy of the chart arrives (the no-double-send rule). |

## Out of Scope
- What Discord or Telegram show to a reader. The fakes cannot prove it; this residual is recorded in SECURITY-MODEL.md.
- Message length splitting (not in scope for the mission).
- Live widgets in the app (`widget-escape`).
- The stub connector's record shape (unit tests).

## Variants (optional)
- A reply with an invalid chart. The block arrives as code with no image and no marker.
