# Behavior Test: Agent Tells the Time

**Slug**: `agent-tells-the-time`
**Status**: active
**Created**: 2026-10-10 (Mission 28 Flight 1)
**Last Run**: 2026-10-11 pass, 8/8 ([run log](agent-tells-the-time/runs/2026-10-11-01-02-39.md))

## Intent

Verifies that a live agent knows today's date and the current time in the
operator's time zone. It checks this from the first turn, in the app and in a
connector conversation. It also checks:

- that the operator's zone setting changes what the agent reports;
- that a trimmed agent still has the time tool;
- that a per-agent disable removes the tool and the prompt's mention of it.

Unit tests prove the formatter, the composer and the factory gating. They
cannot prove that a newly built agent in a running instance carries the date
line, or that a real model uses it or the tool to answer. Two independent
observables are used, as in `agent-rules-round-trip`:

1. **The reply of a fresh conversation** is the adherence signal. Ask on the
   first turn of a new conversation only.
2. **The persisted session's messages** are the composition and tool-call
   signal: `chat_sessions.messages` is a JSON list. Element 0 is the system
   message, and later elements carry tool calls and tool results.

**The expected values are computed independently.** The Validator computes
every expected date and time with the shell (`TZ=<zone> date …`), never from the
instance.

The far zone `Pacific/Kiritimati` (UTC+14) is used so the expected date differs
from the host's for most of the day. Kiritimati is a calendar day ahead of UTC
from 10:00 to 24:00 UTC. With the host in America/Chicago (UTC-5 in October),
the host is a day behind UTC before 05:00 UTC. The Kiritimati, UTC and host
dates therefore all agree only from about **05:00 to 10:00 UTC**. A run in that
window can't tell the zones apart by date. The Validator records that and leans
on the time assertions (steps 3 and 4) instead. The Validator computes the
window from the host's actual zone, read from the instance as in step 7.

## Preconditions

- A dev instance built from the flight branch, on a port of 8490 or higher (never
  8484 or 8485), with a **scratch data directory**. Start it with
  `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`. Follow CLAUDE.md's
  "Behavior-test credential convention" for the credential and the browser
  handoff.
- The operator's local Ollama answers at `http://localhost:11434` with a
  tool-capable model (`gpt-oss:20b` or `qwen3:30b`). Re-check with
  `curl -s localhost:11434/api/tags` before step 1.
- An `ollama` provider pointing at it exists in the scratch instance, with an
  agent `time-probe` using it:
  - persona: "You are a terse assistant. Answer in one sentence.";
  - all built-in tools at their defaults (`enabled_tools` null, `disabled_tools` empty);
  - no rules;
  - notes off.
- A stub connector `bt-stub` exists with `default_agent` set to `time-probe` and
  peer `peer-1` admitted, set up as in `stub-connector-round-trip.md` steps 1-4
  (with this spec's port and agent).
- A browser apparatus can reach the dev instance.
- The database path is `{data_dir}/the-one.db`.

## Observables Required

- **browser**: the chat transcript.
- **http**:
  - `GET`/`PUT /api/time-settings`;
  - `PUT /api/agents/time-probe`;
  - the stub seam routes `POST /api/_test/stub/inbound` and
    `GET /api/_test/stub/outbound`;
  - `GET /api/chat/sessions`.
- **shell**:
  - `sqlite3 {data_dir}/the-one.db "SELECT messages FROM chat_sessions WHERE id='{SESSION}'"`,
    then parse the JSON;
  - `TZ=<zone> date '+%A %B %-d %Y %H:%M'` for the expected values.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | `PUT /api/time-settings` with `{"mode": "zone", "zone": "Pacific/Kiritimati"}`, then `GET /api/time-settings`. Compute `{KDATE}` with `TZ=Pacific/Kiritimati date '+%A, %B %-d, %Y'`. | The PUT returns 200. The GET shows `mode` "zone", `zone` "Pacific/Kiritimati" and `effective.zone` "Pacific/Kiritimati". `preview.prompt` begins `Today is {KDATE} (Pacific/Kiritimati).` and names `current_time`. `preview.prompt_without_tool` does not name it. `preview.tool`'s first line ends `+14:00 (Pacific/Kiritimati)`. |
| 2 | In the browser, start a **new** chat with `time-probe` and send "What is today's date? Reply with the weekday and the date only." Record the session id as `{WEB1}`, then read its stored messages. | The reply names `{KDATE}`'s weekday and its day of the month. Stored element 0, the system message, starts with the platform prompt ("You are an AI agent. Use your tools to do what you're asked"). Its last `---`-separated layer is the date line `Today is {KDATE} (Pacific/Kiritimati). … call current_time.` No error is shown in the transcript. |
| 3 | In the same chat, send "What time is it in Tokyo right now?" Compute `{TOKYO}` with `TZ=Asia/Tokyo date '+%H:%M'` immediately after the reply arrives. | The stored messages for `{WEB1}` include at least one assistant tool call named `current_time`. Record whether its arguments carry `zone` "Asia/Tokyo" or no zone; a model may convert itself. If `zone` is "Asia/Tokyo", the matching tool result's first line ends `+09:00 (Asia/Tokyo)` and contains an `Operator's time zone:` block naming Pacific/Kiritimati. If there is no zone, it ends `+14:00 (Pacific/Kiritimati)`. Either way, the reply's time is within 5 minutes of `{TOKYO}`, read in 12-hour or 24-hour form. |
| 4 | `PUT /api/agents/time-probe` with `enabled_tools: ["read_file"]` (trimming the agent's built-ins), keeping its other fields. Start a **new** chat and send "What time is it right now?" Record `{WEB2}` and compute `{KTIME}` with `TZ=Pacific/Kiritimati date '+%H:%M'`. | The stored system message's date line still names `current_time`. Either the stored messages include a `current_time` call (no `zone`, or `zone` Pacific/Kiritimati), or the reply's time is within 5 minutes of `{KTIME}`; record which. There is no "tool not found" or unknown-tool error in the stored messages. |
| 5 | `PUT /api/agents/time-probe` with `enabled_tools: null` and `disabled_tools: ["current_time"]`. Start a **new** chat and send "What is today's date? Reply with the weekday and the date only." Record `{WEB3}`. | The stored system message's last layer is the tool-free wording `Today is {KDATE} (Pacific/Kiritimati), as of when this conversation was last loaded.`, and the text `current_time` appears nowhere in it. The stored messages contain no `current_time` call. The reply still names `{KDATE}`'s weekday and day of the month. |
| 6 | Restore `time-probe` to defaults (`enabled_tools: null`, `disabled_tools: []`). Snapshot `GET /api/_test/stub/outbound` (the pairing setup may have left records). Inject a stub inbound message from `peer-1` on `bt-stub`: "What's today's date? Weekday and date only." Poll `GET /api/_test/stub/outbound` for up to 120 s. Find the connector session through `GET /api/chat/sessions` (platform `stub`), and read its stored messages. | An outbound reply addressed to `peer-1` arrives **beyond the snapshot's records** (outbound records carry no id or timestamp: compare the record list's length and contents with the snapshot); only that record is judged. It names `{KDATE}`'s weekday and day of the month. The connector session's stored system message ends with the date line naming Pacific/Kiritimati and `current_time`. |
| 7 | `PUT /api/time-settings` with `{"mode": "system", "zone": null}`, then `GET`. Compute `{HOSTZONE}` in the **instance's** environment. Read `TZ` from the running instance's `/proc/<pid>/environ` (the PID is in `.the-one.<port>.pid`). Then run `env TZ=<that value, or unset if absent> .venv/bin/python -c "import tzlocal; print(tzlocal.get_localzone_name())"` from the flight branch checkout. Start a **new** web chat, send "Hello.", record `{WEB4}`, and read its system message. | The GET shows `mode` "system", with `system.zone` and `effective.zone` both equal to `{HOSTZONE}` (or both null when `{HOSTZONE}` is empty). `{WEB4}`'s date line names `{HOSTZONE}`, or `system time zone, UTC…` when there is no name, and its date matches `TZ={HOSTZONE} date '+%A, %B %-d, %Y'`. |
| 8 | `PUT /api/time-settings` with `{"mode": "zone", "zone": "Mars/Olympus_Mons"}`, then `GET`. | The PUT returns **422** with a plain-sentence `detail` naming the unknown zone. The GET is unchanged from step 7. |

## Out of Scope

- The Settings › Date and time page and the app's displayed clock times
  (Mission 28 Flight 2). A later spec covers them.
- Windows. The frozen `time zones` doctor gate covers that platform (Flight 1,
  leg 3).
- Chat-only models. The tool-free wording for `supports_tools() == False` is
  unit-tested with a scripted provider.
