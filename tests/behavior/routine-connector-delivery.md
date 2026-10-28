# Behavior Test: Routine Connector Delivery

**Slug**: `routine-connector-delivery`
**Status**: draft
**Created**: 2026-10-28
**Last Run**: never

> Draft authored at Mission 33 Flight 1 planning (DD13). The
> `routine-connector-delivery-behavior-test` leg finalizes the step wording
> against the landed routes and response shapes before the first run.

## Intent

Verifies that an operator routine runs unattended against a live instance and
that its reply reaches a connector channel:
- the reply is sent to the channel, and the routine's prompt never is;
- the run's message is stored as the routine's;
- a one-off routine fires on its own from the real scheduler, with no request
  driving it;
- after the channel's chat is ended with `/new`, the next run lands in a new
  chat for the same channel rather than the ended one.

This needs a real process: the lifespan-started scheduler, the connector
manager with a live stub listener, the shared session lock and the
persistence. Unit tests prove each part. This test proves they are wired
together in a running app.

It runs on the mock provider, so the reply text is deterministic. Whether a
real model writes a good routine reply is not in question here. The
real-model check belongs to the Flight 2 behavior test.

## Preconditions

- **Dev instance**, started from a scratch working directory (CLAUDE.md "SAFETY
  RULE"), never port 8484 or 8485 and never the operator's default data
  directory:
  ```bash
  mkdir -p $HOME/the-one-behavior-test-scratch/cwd && cd $HOME/the-one-behavior-test-scratch/cwd
  THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data the-one rotate-api-credential
  THE_ONE_PORT=<port ≥ 8490> THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/data \
    THE_ONE_DEV_MODE=true THE_ONE_STUB_TEST_ENDPOINT=1 <repo>/.venv/bin/the-one serve >serve.log 2>&1 &
  echo $! > serve.pid
  ```
  `GET /api/live` returns 200. Every other request carries
  `Authorization: Bearer <contents of the data dir's api-credential>`
  (shell-only Executor, CLAUDE.md "Behavior-test credential convention").
- The scratch data directory is fresh (no prior routines, chats or connectors).
- The host clock is correct. Step 6 waits on real time.

## Observables Required

- http: response status and JSON bodies, measured with curl through the
  shell.
- shell: elapsed time for the step-6 wait.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Create a `mock` provider whose `config.response.content` is `"ROUTINE-REPLY-7731"`. Create agent `routine-agent` on it. Create a stub connector with `default_agent` `routine-agent` and an allowlist that admits peer `alice`. | (setup) |
| 2 | `POST /api/_test/stub/inbound` a DM from `alice`, text `hello`. Then `GET /api/chat/sessions`. | One chat exists for `routine-agent` with platform `stub`. `GET /api/_test/stub/outbound` holds one send, the mock reply. |
| 3 | `GET /api/time-settings` and note the effective zone. `POST /api/agents/routine-agent/routines` with name `Morning check`, prompt `PROMPT-SECRET-4410 check things`, schedule `{"kind":"daily","time":"09:00"}`, target the chat from step 2. | 201. The body's `next_run_at` is the next 9:00 AM in the noted effective zone, expressed in UTC. Its `target.session_id` is the step-2 chat. |
| 4 | Note the routine's `next_run_at`. `POST …/routines/{id}/run` (Run now). Poll `GET …/routines/{id}/runs` until the newest run is not `running` (at most 30 s). | The newest run has outcome `ok`, trigger `manual` and `new_chat` false. `GET /api/_test/stub/outbound` gained exactly one send, whose text is `ROUTINE-REPLY-7731`; note its target (connector, channel, peer). No outbound send contains `PROMPT-SECRET-4410`. `GET …/routines/{id}` shows `next_run_at` unchanged by the manual run. |
| 5 | `GET /api/chat/sessions/{chat id}`. | The stored messages end with a USER message whose content is the prompt, with `routine_name` `Morning check` and `visibility` `operator`. An ASSISTANT message `ROUTINE-REPLY-7731` with no `visibility` (peer-visible) follows it. `session_metadata.routine.name` is `Morning check`. |
| 6 | Create a second routine, `One-off`, with prompt `ONEOFF-8812`, schedule `once` 1 minute from now, and the same target. Make no further requests that act on it. Poll its runs every 10 s for up to 150 s. | Within 150 s, one run appears with trigger `schedule` and outcome `ok`, and the outbound log gains one more `ROUTINE-REPLY-7731` send. `GET …/routines/{id}` shows the routine Done: `finished_at` set and `next_run_at` null. |
| 7 | `POST /api/_test/stub/inbound` a DM from `alice`, text `/new`. Then Run now on `Morning check` and poll as in step 4. | The run is `ok`. Its `session_id` differs from the step-2 chat. The outbound log gained one more reply send, whose target (connector, channel, peer) equals the one noted in step 4. `GET …/routines/{id}` shows `target.session_id` equal to the run's new `session_id`. |
| 8 | `POST /api/_test/stub/inbound` a DM from `alice`, text `thanks`. `GET /api/chat/sessions`. | The peer's `thanks` lands in the step-7 chat (the routine's run kept it current), and no third chat for that channel was created. |

## Out of Scope

- **Schedule arithmetic:** daylight-saving changes, the grace window, and
  catch-up after a restart. These are unit-tier tests with a frozen clock.
- **The Routines tab and the chat panel.** Browser tests cover them.
- **A real model's reply,** and agent-made routines (Mission 33 Flight 2).
- **A real Discord or Telegram channel.** The stub's recorded target is the
  delivery observable.
