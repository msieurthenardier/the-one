# Behavior Test: Agent Schedules a Follow-up

**Slug**: `agent-schedules-follow-up`
**Status**: active
**Created**: 2026-10-29
**Last Run**: 2026-10-30-20-45-42 (pass, 7/7; steps 1-4 `gpt-oss:20b`, steps 5-7 `qwen3:30b` after two Ollama 500s)

> Re-authored at Mission 33 Flight 4 (the HAT), against the HAT's legs 02, 05
> and 07: routines have no target, so every run starts a new web chat titled
> with the routine's name and nothing is delivered to a connector by the
> routine itself (an agent may still post with `send_to_platform_channel`);
> Routines approval is off for a newly created agent; only the canonical
> schedule shape is accepted. Steps 1, 3 and 4 changed; the rest stand.
>
> Re-authored at Mission 33 Flight 3 leg 8: schedules are stored in the calendar
> recurrence shape (`{start, repeat, ends}`, flight DD1); a one-off is `repeat` null.
> The model is taught only that shape (leg 5); the old `kind` shapes are still
> accepted on input (removed at Flight 4).
>
> Authored at Mission 33 Flight 2 planning (DD13). Finalized by the FD at leg 6
> against `ee4e8c5b`: the switches are read from `GET .../self-configuration/routines`
> (`enabled`, `requires_approval`, `pending_count`); the proposals list is
> `GET .../self-configuration/routines/proposals` (`{"proposals": [...]}`, each with
> `action` create/update/delete, `status`, `routine_id`, `untrusted_sources`); the
> routine view carries `created_by`, `untrusted`, `untrusted_sources` (`target` was removed at
> Flight 4); runs carry `trigger_kind` and `outcome`; taint sources read
> `peer:{name}`. The original draft note follows.
>
> This was a draft. The
> `agent-schedules-follow-up-behavior-test` leg finalizes every route, field
> and value against the landed code before running it. That code is the
> Routines item and proposals routes (leg 2), the routine view's `created_by`
> and `untrusted` fields, and the tools' result wording (leg 3).

## Intent

Verifies, against a live instance with a real model, that an agent schedules
its own follow-up when the operator allows it, and that the follow-up runs:
- with the Routines self-configuration item off, the agent has no way to
  schedule anything;
- with it on, a plain "check back with me in 2 minutes" makes the model call
  `schedule_routine`. The routine is recorded as the agent's, flagged because
  the request came from a connector peer, and logged as an applied change;
- the routine fires on its own, in a new chat of its own; the routine
  posts nothing to the channel by itself;
- with approval on, the agent's change is held as pending until the operator
  approves it;
- the agent can cancel its own routine.

A live model is the point of the test. Scripted tool calls prove the
mechanics at the unit tier (Flight 2 DD7). Only a real model shows that the
seeded tool descriptions lead to a follow-up being scheduled.

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
- The scratch data directory is fresh.
- **Local Ollama** answers at `http://127.0.0.1:11434` with `gpt-oss:20b`
  pulled. If the model does not call the tool in step 3 after two tries, the
  run may switch to `qwen3:30b`, and the run log records the switch.
- The host clock is correct. Step 4 waits on real time.
- **Before-counts.** Capture `GET /api/_test/stub/outbound` immediately before
  every triggering action.

- **Reading the run (learned at the first run, 2026-10-29-10-44-39):**
  - The stub connector create needs a `name`.
  - The agent create takes `provider_config_id` and `llm_model` (not
    `provider_id`/`model`, which are ignored). The pending count is
    `GET /api/agents/follow-agent/self-configuration/routines/proposals/pending-count`.
    Timing checks use `next_run_at` (UTC); `schedule.start` is local wall time.
    (Learned at the 2026-10-29-21-06-42 run.)
  - `POST /api/_test/stub/inbound` blocks until the agent's turn ends, so
    measure every time window from the stored user message's `created_at`.
  - Transcripts and tool calls come from `GET /api/chat/sessions/{id}`.
  - An inbound reply records `channel_id null` and `peer_id alice`. A run
    posts to the channel only if the agent calls `send_to_platform_channel`
    itself (Flight 4); such a record is allowed, not required.
  - "Done" means `finished_at` is set and `next_run_at` is null; `enabled`
    stays true.
  - Other taint sources may appear beside `peer:alice` (for example
    `routine:<name>` once a flagged run is in the chat).
  - A model's own retry inside one turn, after a validation refusal, is not
    the spec's retry rule.
  - Once a routine is deleted, every proposal for it reads `routine_id`
    null (`ON DELETE SET NULL`). Match a delete by `routine_name` and its
    `base` before-image.

## Observables Required

- http: response status and JSON bodies, measured with curl through the
  shell.
- shell: elapsed time for the step-4 wait.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Create an `ollama` provider (`base_url` `http://127.0.0.1:11434`). Create agent `follow-agent` on it with model `gpt-oss:20b`. Create a `stub` connector with `config.default_agent` `follow-agent` and `config.allowlist.peers` `["alice"]`; record `{CID}`. | (setup) The provider, agent and connector exist; `GET /api/agents/follow-agent/self-configuration/routines` returns `enabled` false, `requires_approval` false and `pending_count` 0. |
| 2 | Routines off. Stub inbound DM from `alice`: "I'm waiting on a build to finish. Check back with me in 2 minutes and ask if it finished." Wait for the reply record (at most 120 s). | A reply record exists. `GET /api/agents/follow-agent/routines` is empty. The chat's stored assistant messages contain no `schedule_routine` tool call. |
| 3 | `PUT /api/agents/follow-agent/self-configuration/routines` `{"enabled": true, "requires_approval": false}`. Send the same DM again and wait for the reply (at most 120 s). | One routine exists with `created_by` `agent`, a one-off schedule (`schedule.repeat` null), `next_run_at` between 1 and 5 minutes after the DM, and no `target` field. It has `untrusted` true and `untrusted_sources` containing `peer:alice`. The proposals list holds one `applied` `create` for it. The transcript shows a `schedule_routine` tool call. |
| 4 | Make no further requests that act on the routine. Poll its runs every 10 s, up to 240 s past its `next_run_at`. | One run appears with `trigger_kind` `schedule` and `outcome` `ok`, and its `session_id` is a new chat (not the DM's chat) titled with the routine's name, holding the routine's message (`routine_name` set) and the agent's reply. No outbound record contains the routine's prompt text (an outbound record is allowed only if the run's transcript shows the agent's own `send_to_platform_channel` call). The routine is Done. |
| 5 | `PUT …/self-configuration/routines` `{"requires_approval": true}`. Send a DM: "Also check back with me tomorrow at 9 AM about the build." Wait for the reply. | No new routine. The proposals list holds a `pending` `create` whose payload schedule is a one-off or a daily recurrence (`repeat` null, or `repeat.every` 1 with `unit` `day`), flagged `peer:alice`. `GET …/proposals/pending-count` returns `{"count": 1}`. |
| 6 | `POST …/proposals/{id}/approve`. | 200. A routine now exists with `created_by` `agent` and `untrusted` true. The proposal is `applied`. |
| 7 | `PUT …/self-configuration/routines` `{"requires_approval": false}`. Send a DM: "Cancel that 9 AM check, I don't need it." Wait for the reply. | The routine from step 6 is gone. The proposals list holds an `applied` `delete` for it. The transcript shows a `cancel_routine` (or `list_my_routines` then `cancel_routine`) tool call. |

## Out of Scope

- The wording or quality of the model's replies.
- The scripted taint matrix, the caps and the stale-approval paths. These are
  unit-tier, DD6-DD8.
- The Self-configuration tab UI. The browser lanes cover it.
- Posting to a real Discord channel: routines no longer deliver to
  connectors (Flight 4).
