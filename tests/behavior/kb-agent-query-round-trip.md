# Behavior Test: An attached agent queries its knowledge base; an unattached one cannot

**Slug**: `kb-agent-query-round-trip`
**Status**: active
**Created**: 2026-09-17
**Last Run**: 2026-09-17-22-08-29 (8/8 checkpoints passed)

## Intent

Verify that attaching a knowledge base to an agent makes it answerable
during a real chat turn, and that an agent without the attachment cannot
reach it. The turn runs through the whole stack — the agent factory's
per-agent tool registry, the knowledge-base tool provider, the hybrid
retrieval path over a folder indexed from disk, the agent loop's tool
dispatch, and the persisted session transcript. This needs a behavior test
rather than a unit test because those pieces are only wired together by a
live process: the registry is built at agent construction from database
state, the index is produced by a background worker, and the tool result
reaches the model through the loop's own dispatch. The model itself is the
deterministic `mock` provider with a scripted tool call, so the test proves
reachability, isolation and the real retrieval result without depending on
a live model's judgement. Mission 24 Flight 5, DD-9.

## Preconditions

- the-one is running host-native as a **dedicated dev instance** on
  `http://127.0.0.1:8485` with a **scratch data directory** `<scratch>`
  and `THE_ONE_DEV_MODE=true` (the `mock` provider type is refused
  without it), started as `THE_ONE_DEV_MODE=true THE_ONE_PORT=8485
  THE_ONE_DATA_DIR=<scratch> make up`. Verify with an active probe:
  `GET http://127.0.0.1:8485/api/live` returns 200. **Never 8484, never
  the operator's default data directory** (CLAUDE.md "SAFETY RULE").
- **Credential**: CLAUDE.md's "Behavior-test credential convention" —
  read `<scratch>/api-credential` and attach `Authorization: Bearer
  <credential>`. A **fresh** scratch data directory has no credential file
  and `make up`'s verify step fails without one: run `THE_ONE_DATA_DIR=
  <scratch> the-one rotate-api-credential` once before the first `make up`.
- A writable fixture folder on a **native local filesystem**, outside the
  repository and outside `<scratch>`: `<fixture>` (e.g.
  `/tmp/kb-query-fixture`). Delete it if a prior run left it.
- The repository virtualenv is reachable for the WebSocket driver; the
  `websockets` package is a runtime dependency of the app, so no install is
  needed. **`/ws` authorizes on the bearer credential** — the credential
  middleware resolves the session cookie first and falls back to the
  `Authorization` header, and the Origin allowlist only rejects an upgrade
  that *carries* a disallowed `Origin` (a Python `websockets` client sends
  none). No handoff mint and no cookie are needed for this apparatus.
- **`/ws` protocol, pinned so every run drives it identically**: send
  `{"action":"join","session_id":…}` and wait for
  `{"type":"session_joined",…}`; send `{"action":"message","message":"…"}` —
  the key is **`message`**, not `content`; the turn is complete on
  `{"type":"done"}`, which is the driver's exit condition.
- **`POST /api/chat/sessions` request shape, pinned**: `{"agent_name":
  "<name>"}` — the body's only required key. The response's `session_id`
  is what every step from Step 5 on joins over `/ws`.
- **`tool_result` is nested, pinned**: a `role: "tool"` message in a
  session's `messages` carries a top-level `content` string *and* a
  nested `tool_result` object; only the nested `tool_result` object carries
  `is_error` and `tool_call_id`. Every isolation assertion (Steps 7 and 9)
  reads the nested object, not the top-level `content`.
- No knowledge base named `KBQ-test` and no agents named `kbq-attached` or
  `kbq-detached` exist; delete any leftovers before Step 1.

## Observables Required

- http (response status and JSON bodies of `/api/knowledge-bases…`, `/api/providers`, `/api/agents…`, `/api/chat/sessions…` — measured via curl via Bash)
- shell (the instance's `make up` exit code, the `/api/live` probe, and the WebSocket driver script's output — measured via Bash)
- filesystem (creating the fixture files — measured via Bash)

## Note on the isolation assertions (Steps 7 and 9)

The negative assertion is scoped to the **tool result**, not to the whole
transcript, and that is deliberate — an earlier draft asserted that the
session's `messages` contain no occurrence of the fixture identifier at all,
which can never pass. The scripted tool call carries
`{"query": "xylophone-quixotic-7731"}` as its arguments, and `message_to_dict`
persists `tool_calls` verbatim including `arguments`, so the identifier is in
the transcript of *every* turn that issues the scripted call — including the
attached agent's. Asserted that way, the two load-bearing isolation rows
would fail for a reason with nothing to do with isolation. What isolation
actually means here is that the *result handed back to the model* carries no
knowledge-base content, and that is what Steps 7 and 9 assert.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Probe `GET /api/live` for 200. Create `<fixture>/notes/manual.md` containing several paragraphs of ordinary prose about an unrelated subject, one of which contains the exact identifier `xylophone-quixotic-7731` in a sentence that uses no other distinctive vocabulary, and `<fixture>/notes/other.md` containing unrelated prose that never mentions that identifier. | (empty) |
| 2 | `POST /api/knowledge-bases` with `{"name": "KBQ-test"}`; record `kb_id`. `POST /api/knowledge-bases/{kb_id}/items` with `{"type": "folder", "path_or_url": "<fixture>"}`; record a wall-clock timestamp for this trigger response. From that same shell invocation, begin polling `GET /api/knowledge-bases/{kb_id}/status` every 2 s, recording a wall-clock timestamp for every poll sample, until the terminal condition is met or 60 s elapses. | Both creates respond 201. Within 60 s of the trigger timestamp the status body shows `items.indexed` = 2, `items.pending` = 0, `items.failed` = 0 and `chunks` ≥ 2 — judged from the recorded trigger and poll-sample timestamps, not from wall-clock impression. |
| 3 | `POST /api/providers` creating a `mock`-type provider whose config carries a scripted `response` with `content` and a `tool_calls` entry carrying **all three required keys** — `id` (any literal, e.g. `"call-1"`), `name` = `kb__KBQ-test__search`, and `arguments` = `{"query": "xylophone-quixotic-7731"}` — and at least one model id. (`MockProvider` builds `ToolCall(id=tc["id"], ...)`, so an entry without `id` raises `KeyError` inside the turn.) Record `provider_id` and the model id. | The create responds 201 and the stored provider's type is `mock` (dev mode admits it). |
| 4 | `POST /api/agents` creating `kbq-attached` bound to that provider and model with `kb_ids` set to `[kb_id]` and **`max_iterations` set to `1`**, and `kbq-detached` bound to the same provider and model with `kb_ids` empty and **`max_iterations` set to `1`**. Then `GET /api/agents/kbq-attached` and `GET /api/agents/kbq-detached`. | Both creates respond 201. `kbq-attached`'s body has `kb_ids` = `[kb_id]`; `kbq-detached`'s `kb_ids` is empty. |
| 5 | `POST /api/chat/sessions` for `kbq-attached`; record `session_id`. Drive one user turn: connect the WebSocket driver to `ws://127.0.0.1:8485/ws`, join `session_id`, send one message, and wait for the turn to finish. Then `GET /api/chat/sessions/{session_id}`. | The driver exits 0. The session's `messages` contain an assistant message whose tool call names **`kb__KBQ-test__search`**, followed by a tool result whose content contains the exact identifier `xylophone-quixotic-7731` and the path of `<fixture>/notes/manual.md`. No message reports an unknown or unavailable tool. |
| 6 | `PUT /api/providers/{provider_id}` changing the scripted `tool_calls` to a single call to `search_tools` with an empty query (`""`), so the result is unfiltered. `POST /api/chat/sessions` for `kbq-attached`; drive one turn as in Step 5; `GET` the session. Then `PUT /api/providers/{provider_id}` again, narrowing the `search_tools` query to name the knowledge base (`KBQ-test`); `POST /api/chat/sessions` for `kbq-attached`; drive a second turn; `GET` that session. | The unfiltered turn's tool result for `search_tools` lists at least one entry grouped under a **`kb:KBQ-test:`** label and at least one entry grouped under a **`built-in:`** label — both group labels present in the same result, which is what makes the groups' distinctness demonstrable rather than inferred. The narrowed turn's tool result lists `kb__KBQ-test__search` grouped under `kb:KBQ-test:`. |
| 7 | `PUT /api/providers/{provider_id}` restoring the Step 3 scripted call to `kb__KBQ-test__search`. `POST /api/chat/sessions` for **`kbq-detached`**; confirm from the create response and/or the `session_joined` frame that the session's agent is `kbq-detached` before driving the turn. Drive one turn; `GET` the session; capture the matching `tool_result`'s content in full, verbatim, and record its byte count alongside the captured string's length as the completeness check. | The create response and/or `session_joined` frame confirm the session belongs to `kbq-detached`. The turn completes rather than hanging. The session's `messages` carry an assistant tool call naming `kb__KBQ-test__search`, and the `tool_result` whose `tool_call_id` matches that call has `is_error: true` with content naming the tool as unknown. That result's content, captured in full (byte count matches the captured string's length, so the absence claim below is not from an excerpt), contains **neither** `xylophone-quixotic-7731` **nor** any text from `<fixture>/notes/manual.md`. |
| 8 | `GET /api/agents/kbq-attached`, then `PUT /api/agents/kbq-attached` with the **complete** body from that GET, re-sending `kb_ids` and `max_iterations` verbatim, and with `enabled_tools` set to a short list of built-in tool names that contains no `kb__` name. (`update_agent` is a full replace — `AgentConfig.model_validate(data)` with server-side preservation only for `mcp_overrides` and `self_revision_requires_approval`. Omitting `kb_ids` sets it to `[]`, silently detaching the knowledge base, and this step would then fail *looking like* a whitelist regression.) `POST /api/chat/sessions` for `kbq-attached`; drive one turn; `GET` the session. | The tool result for `kb__KBQ-test__search` still contains `xylophone-quixotic-7731` — a narrowed built-in whitelist does not strip knowledge-base tools. |
| 9 | `GET /api/agents/kbq-attached`, then `PUT /api/agents/kbq-attached` with the **complete** body from that GET (again re-sending `kb_ids`, `max_iterations` and the Step 8 `enabled_tools`), adding `kb__KBQ-test__search` to `disabled_tools`. Immediately `GET /api/agents/kbq-attached` again and confirm `kb_ids` still equals `[kb_id]` before driving any turn — this readback is what distinguishes a working blacklist from a silent `kb_ids` wipe, since the two produce a byte-identical `tool_result` below. `POST /api/chat/sessions` for `kbq-attached`; drive one turn; `GET` the session; capture the matching `tool_result`'s content in full, verbatim, and record its byte count alongside the captured string's length as the completeness check. | The post-PUT `GET /api/agents/kbq-attached` confirms `kb_ids` is still `[kb_id]` — proving the attachment survived the `PUT` and the tool's absence below is caused by `disabled_tools`, not a silent `kb_ids` wipe (the two causes are otherwise indistinguishable from the `tool_result` alone). The `tool_result` matching the `kb__KBQ-test__search` call has `is_error: true`, and its content, captured in full (byte count matches the captured string's length), contains **neither** `xylophone-quixotic-7731` **nor** any text from `<fixture>/notes/manual.md` — the explicit blacklist still removes a knowledge-base tool by name. |
| 10 | (Teardown, no judgment) Delete both agents, the provider, the knowledge base and every session created above; confirm `GET /api/knowledge-bases` no longer lists `KBQ-test`. Delete `<fixture>/`. | (empty) |

**Row conventions:** one row = one logical checkpoint. Steps 5, 7, 8 and 9
are the load-bearing rows — reachability, isolation, the whitelist
regression and the blacklist. Each turn runs in its **own** chat session so
no assertion can be satisfied by a message left over from an earlier step;
when reading a transcript back, judge only the messages of the session that
step created. The `mock` provider replies identically every turn, so a
scripted tool call is re-issued on each new session without further setup.
The measurement and evidence conventions in the Executor's own instructions
apply — in particular, every HTTP call captures its status code into the
evidence, not the body alone.

## Out of Scope

- Whether a real model, unprompted, chooses to call a knowledge-base tool.
  The `mock` provider's tool call is scripted, so this test proves the tool
  is reachable, dispatchable and correct — not that a model's judgement
  selects it. A live-model variant would be a separate spec.
- Retrieval quality beyond the exact-term guarantee: ranking order, recall
  at depth, and the fusion constant are unit-tested against fixtures, not
  observed here.
- Folder registration, walking, indexing and change monitoring — covered by
  `kb-folder-index-round-trip` and `kb-folder-watch-round-trip`.
- The Studio attach surface (Flight 6), and squawk 0050's `kb_ids`
  clobbering on save, which this flight deliberately does not fix.
- Behaviour when the vector sidecar is stale (retrieval degrades to
  keyword-only) — unit-tested; there is no operator-facing way to make a
  sidecar stale on demand.

## Variants (optional)

- **Live model**: the same steps with an agent on a tool-capable provider
  and no scripted call, asserting the model discovers and calls the tool
  from the knowledge base's description alone. Proves the discovery half
  this spec puts out of scope; needs a provider key and tolerates
  non-determinism.
