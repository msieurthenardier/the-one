# Behavior Test: Secrets Round Trip

**Slug**: `secrets-round-trip`
**Status**: active
**Created**: 2026-11-04
**Last Run**: 2026-11-05-00-43-42 — pass (10/10; run 1, sortie 10 after leg 2, build `c0d75b27`, port 8493; [run log](secrets-round-trip/runs/2026-11-05-00-43-42.md)). Steps 5 and 6 then pinned to the exact refusal wording seen in this run.

## Intent

Verifies sortie 10's charter end to end (DD9): a secret stored in the Library and granted to an agent reaches a tool as its real value when the agent writes `{{secret:key}}`. Meanwhile the stored chat, the REST result and every API response carry only the placeholder or a mask. A value read back by a tool comes back as `[secret:key]`. An ungranted key, or a key used in a tool not on its allowed list, is refused with an error naming only the key. A Library change and a key rotation apply on the next call.

The unit tests in legs 1 and 2 prove the substitution and masking mechanics with a scripted model. This spec proves the live wiring across the REST API, the agent factory, the loop, the encrypted store and the session persistence in one running instance, with the file system as the independent witness that the tool really got the value.

## Preconditions

- **Dev instance**, per CLAUDE.md "Behavior-test credential convention" (never port 8484 or the default data directory):
  - a dedicated port of 8490 or higher (not 8485, and not 8492 if the sortie 10 mockup instance is still running);
  - a scratch data directory and a scratch working directory under `$HOME`, e.g. `$HOME/the-one-behavior-test-scratch/secrets/{data,cwd}`;
  - `THE_ONE_DEV_MODE=true`;
  - started from the scratch working directory with the branch's `.venv/bin/the-one serve`;
  - the server PID taken from `ss -ltnp` (not `$!`) and stopped by that PID;
  - the credential created with `THE_ONE_DATA_DIR=<data> the-one rotate-api-credential` before the first request.
- **An output folder** `$HOME/the-one-behavior-test-scratch/secrets/out` exists and is empty. It is inside the default file-tool allowlist (`~`).
- **Values used** (the Executor records them and uses nothing else):
  - `V1 = S10-VALUE-alpha-7f3c91`
  - `V2 = 4826-pin-S10`
  - `V3 = S10-VALUE-bravo-2b8e40`, used in step 7
- **The seed**, through the REST API, every call with `Authorization: Bearer <credential>`. Order matters: providers first, then agents with the returned provider `id` as `provider_config_id` (squawk 0277).
  - A secret: `POST /api/secrets` with `{"name":"BT login","description":"Test credential for the round trip.","values":[{"key":"bt_token","value":"<V1>"},{"key":"bt_pin","value":"<V2>"}],"allowed_tools":["write_file","read_file"]}`. Record its `id` as `SID`.
  - Four `mock` providers (`"type":"mock"`, `"base_url":""`), each with one scripted `config.response`:
    - `p-writer`: `{"tool_calls":[{"id":"t1","name":"write_file","arguments":{"path":"<out>/token.txt","content":"token={{secret:bt_token}} pin={{secret:bt_pin}}"}}]}`
    - `p-reader`: `{"tool_calls":[{"id":"t1","name":"read_file","arguments":{"path":"<out>/token.txt"}}]}`
    - `p-outsider`: `{"tool_calls":[{"id":"t1","name":"write_file","arguments":{"path":"<out>/outsider.txt","content":"{{secret:bt_token}}"}}]}`
    - `p-wrongtool`: `{"tool_calls":[{"id":"t1","name":"list_dir","arguments":{"path":"<out>/{{secret:bt_token}}"}}]}`
    
    `<out>` is the absolute output-folder path.
  - Four agents, each with `max_iterations` 1 and `llm_model` `mock-default` (one model call and one tool dispatch per turn):
    - `writer` on `p-writer` with `secret_ids: ["<SID>"]`;
    - `reader` on `p-reader` with `secret_ids: ["<SID>"]`;
    - `outsider` on `p-outsider` with no `secret_ids`;
    - `wrongtool` on `p-wrongtool` with `secret_ids: ["<SID>"]`.
- **Dry run**: before the witnessed run, the Executor sends the seed once against a throwaway instance (or this one, then resets the data directory) and confirms every request returns 2xx (M34 F2 debrief).

## Observables Required

- http:
  - `POST /api/chat` (`{"message":"go","agent_name":"<agent>"}`) result bodies;
  - `GET /api/chat/sessions/{id}` for the stored `messages` (assistant `tool_calls[].arguments` and `tool_result.content`);
  - `GET /api/secrets` and `GET /api/secrets/{SID}`;
  - `POST /api/encryption/rotate`;
  - `PUT /api/secrets/{SID}`.
- shell (curl, `cat`, `grep -c` on the server log, the SQLite file under the data directory, and the output folder)
- filesystem (the files the tools wrote)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | `GET /api/secrets/{SID}` and `GET /api/secrets`. | Both return the secret with `name` "BT login", keys `bt_token` and `bt_pin`, and every `value` exactly `__MASKED__`. Neither body contains V1 or V2, nor any 4-character tail of them. |
| 2 | `POST /api/chat` as `writer`. Record the `session_id` from the result. Then `cat <out>/token.txt`. | The file reads exactly `token=<V1> pin=<V2>`, so the tool received the real values. The `/api/chat` result body contains neither V1 nor V2. |
| 3 | `GET /api/chat/sessions/{writer session}`. | The stored assistant message's `tool_calls[0].arguments.content` is exactly `token={{secret:bt_token}} pin={{secret:bt_pin}}`. No stored message contains V1 or V2. The tool result is not an error. |
| 4 | `POST /api/chat` as `reader`, then `GET /api/chat/sessions/{reader session}`. | Every stored tool result's content **contains** `token=[secret:bt_token] pin=[secret:bt_pin]`. `read_file` output is line-numbered (`filesystem.py:427`), so the line carries a number prefix. This shows masking of a value the tool read back. No stored message and no part of the `/api/chat` result contains V1 or V2. |
| 5 | `POST /api/chat` as `outsider`, then `GET` its session. `ls <out>`. | The stored tool result is an error that reads exactly "Secret `bt_token` is not granted to this agent." It contains neither V1 nor V2. `outsider.txt` does not exist. |
| 6 | `POST /api/chat` as `wrongtool`, then `GET` its session. | The stored tool result is an error that reads exactly "Secret `bt_token` can't be used with the tool `list_dir`." It contains neither V1 nor V2. |
| 7 | `PUT /api/secrets/{SID}` keeping `bt_pin` (`"__MASKED__"` with its pair `id`) and setting `bt_token` to V3. Delete `<out>/token.txt`. `POST /api/chat` as `writer`, continuing the step-2 session (`{"message":"go","agent_name":"writer","session_id":"<writer session>"}`). `cat <out>/token.txt`. | The PUT returns 200 with values `__MASKED__` only. The file now reads `token=<V3> pin=<V2>`, so the changed value applied on the session's next tool call with no agent edit. |
| 8 | `POST /api/encryption/rotate` (wait until it reports success). Delete `<out>/token.txt`. `POST /api/chat` as `writer`, again with the step-2 `session_id`. `cat <out>/token.txt`. | Rotation succeeds. The file reads `token=<V3> pin=<V2>`, so the secret survived the key rotation. |
| 9 | `grep -c` each of V1, V2 and V3 in the server log file. Run `grep -c` for each value on the SQLite database file(s) under the data directory (`*.db`, plus any `-wal` file). | Every count is 0: no plaintext value in the log or the database. |
| 10 | `DELETE /api/secrets/{SID}`, then `GET /api/agents/writer`. `POST /api/chat` as `writer` and `GET` its session. | The delete returns 204. `writer`'s `secret_ids` is `[]`. The new stored tool result is the "not granted" error for `bt_token`. |

## Out of Scope

- The Library editor, the Tools-tab grants, the drawer and the Settings › Prompts example: covered by leg 3's browser tests and the HAT.
- The prompt layer's wording: the HAT, with a real model (leg 2 only checks that it adds nothing for agents without grants).
- That an Agent built **before** a change picks it up. REST `POST /api/chat` with a `session_id` rebuilds the Agent on every call (`app.py:1956-1966`), so steps 7-8 prove the live store, the PUT and the rotation end to end, not the long-lived-Agent property. That is proven by leg 2's same-Agent unit tests and by the HAT's open-tab step over a live WebSocket chat.
- Real model behaviour (whether a real model chooses to use the placeholder): the HAT, with the operator's own provider.
- What the provider receives: the mock provider does not record requests. The stored history is the proxy (DD9), and leg 2's unit test asserts `FakeLLM`'s recorded calls.
