# Leg: secrets-at-runtime

**Status**: completed
**Flight**: [Secrets](../flight.md)

## Objective
Make secrets work in the agent loop. A `SecretResolver` is injected into every factory-built Agent. In `_execute_tool` it fills `{{secret:key}}` into a copy of the arguments, refuses calls that aren't granted or allowed, and masks every stored secret value in the result and error strings. Alongside it come a "Secrets" prompt layer (tool-capable prompt only), the `/api/info` example, the eval no-leak check and docs.

## Context
- The design is the flight's **DD7 and DD8** (server half). Read `../flight.md` first; this leg does not restate the rationale. Where this leg and the flight disagree, this leg wins and the disagreement is a defect to report.
- Charter criteria this leg delivers: 1 (substitution, placeholder-only history and provider request), 2 (masking), 3 (refusal naming only the key), 4 (a change applies on the next call).
- **Leg 1 landed and committed** (`dfc6677e`):
  - `the_one/secret_store/refused.py::is_refused_tool(name)` (exact, case-sensitive match; tool lookup is exact, `ToolRegistry.get`, `tools/base.py:205-208`);
  - `SecretRepository` in `db/repositories.py`: `list`/`get` never decrypt; the internal `get_values(secret_id) -> [(key, plaintext)]` and `all_values() -> [(secret_id, key, plaintext)]` decrypt through the app encryptor;
  - `AgentConfig.secret_ids`, persisted on `agents.secret_ids`.

  Read those before writing anything that reads secrets.
- **The frozen loop.** By project convention `the_one/agent/core.py` is touched only with owner approval (`agents.md` "frozen loop", the `send_to_platform_channel` precedent). The operator approved this flight's DD7, which places the hook in `_execute_tool`. This is that **deliberate, owner-approved touch**, kept minimal:
  - one constructor kwarg (`secrets=None`);
  - one call before execution and one after;
  - masking of the two error strings.

  Everything else lives in `the_one/secret_store/runtime.py` and the factory. agents.md records the touch next to the existing precedent.
- **Security-sensitive:** no value may reach the model, the database, a WebSocket frame, the REST result or a log line through anything this leg adds. Every new test is falsified.
- **Platform prompt text:** `the_one/db/_secrets.py` is new platform prompt text. Under the flight's option (b), the eval is a no-leak check only (Verification Steps).

## Inputs
- Branch `sortie/10-secrets` at `dfc6677e`.
- `the_one/agent/core.py`:
  - `Agent.__init__` (`:162-182`);
  - `_execute_tool` (`:608-672`), whose normal path is `bind_positional_args` → `asyncio.wait_for(tool.execute(**args))` → `self._govern(...)`, plus the `MCPAuthRequired`, `TimeoutError` and generic `Exception` branches;
  - `_dispatch_tool_calls` (`:494` `continue` short-circuit, `:511-513` append).
- `the_one/agent/_context.py`: `current_turn` (`TurnContext.session_id`), `current_chat_session_id`. The pattern is `notes/tools.py:122`: `(turn.session_id if turn else None) or current_chat_session_id.get()`.
- `the_one/agent/factory.py` (`:617-650`, prompt build and `Agent(...)`; `Agent(` is constructed only here).
- `the_one/agent/config.py::compose_system_prompt` (`:38`), `the_one/agent/prompt_layers.py::build_system_prompts` (`:73-133`: `layers` is passed to **both** prompts; secrets go to `tool_capable` only), `the_one/self_configuration/pending.py:136-153` (second caller, with its fallback).
- `the_one/db/_rules.py`, `the_one/db/_notes.py` (block style to match), `the_one/interfaces/web/app.py:3110` (`/api/info` `rules_prompt_example`).
- `evals/env.py:120-150` `Redactor` (technique only; `the_one/` must not import `evals/`).

## Outputs
- New `the_one/secret_store/runtime.py` (`SecretResolver`, the token pattern, the masker).
- New `the_one/db/_secrets.py` (`render_secrets_block`).
- Modified: `the_one/agent/core.py` (the hook), `the_one/agent/factory.py`, `the_one/agent/config.py`, `the_one/agent/prompt_layers.py`, `the_one/self_configuration/pending.py`, `the_one/interfaces/web/app.py` (`/api/info`), `the_one/db/repositories.py` (a keys-and-grants read without decryption, if needed), `the_one/logging_config.py` (only if the log sweep finds a logger that prints request bodies).
- Tests: new `tests/test_secret_runtime.py` (resolver and masker units), `tests/test_secret_loop.py` (through `Agent` with `FakeLLM`/`StubTool`), `tests/test_secret_prompt_layer.py`. Also updates to any test that pins `compose_system_prompt`'s signature, `/api/info` keys, or `Agent.__init__`.
- Docs: `the_one/agents.md` ("Secrets (sortie 10)" gains runtime, resolver key, masking, the frozen-loop touch, shared-connection note, prompt layer timing), `SECURITY-MODEL.md` (threat model and residual risks per the flight's leg 2 docs list), `CLAUDE.md` (the "Secrets (sortie 10)" paragraph extended; `the_one/db/_secrets.py` added to the platform prompt text list in "Prompt evals").

## Acceptance Criteria

**Resolver and masker (`the_one/secret_store/runtime.py`)**
- [ ] AC1. `TOKEN_RE = re.compile(r"\{\{secret:([A-Za-z0-9_-]{1,64})\}\}")`. `SecretResolver(agent_name)` reads through `get_connection()` and leg 1's repository at **each** `prepare` call, with **no cache**. AC11's freshness test depends on it, and a generation-keyed cache is a later optimisation, not to be introduced now. `prepare` makes a fixed number of queries (values once, grants and allowed tools once), never one per token.
  - The **agent for grants** is `chat_sessions.agent_name` for the session id `(current_turn.get().session_id if set) or current_chat_session_id.get()`, falling back to the constructor's `agent_name` when there is no session id or no such row.
  - An agent with no `agents` row (the bare `default`) has no grants.
- [ ] AC2. `await resolver.prepare(tool_name, args) -> Prepared`, where `Prepared` carries either `refusal: str` or `args` plus `mask`:
  - It loads every stored value (`all_values()`) and the agent's grants.
  - It collects tokens from every **string leaf** of `args`, recursing through dicts and lists. Dict keys are neither scanned nor substituted.
  - For each token it looks the key up **ignoring case**. A key that is unknown or not in a granted secret refuses with ``"Secret `KEY` is not granted to this agent."``.
  - A tool name (exact) that is refused by `is_refused_tool` or not in that secret's `allowed_tools` refuses with ``"Secret `KEY` can't be used with the tool `NAME`."``. The refused-set check applies whatever the secret's `allowed_tools` holds, even an empty or hand-edited list.
  - `KEY` is the token **as written** by the model; the messages never name another key or any value.
  - Otherwise it returns a **new** structure with each token replaced by the value, and every untouched container copied, so no object in the original `args`/`tool_call.arguments` is mutated or shared mutably.
- [ ] AC3. `mask` (a pure function bound to the loaded values) replaces every stored value, granted or not, with `[secret:STORED_KEY]`.
  - It recurses through `str`, `dict` (keys **and** values, intended: a tool result whose key holds a value is masked too), `list` and `tuple` (returned as a list).
  - Every other type is returned unchanged. No built-in or MCP tool returns another type today: MCP results arrive as str, and `ToolResult.__post_init__` `json.dumps`es only after masking, so a dict or list is masked on its raw leaves first. A `bytes` result already fails in `__post_init__`; a test pins that it errors without the value appearing.
  - The residual (a set or custom object that `json.dumps` accepts) is noted in SECURITY-MODEL.md as unreachable today.
  - Needles per value: the raw value, `repr(v)[1:-1]`, `json.dumps(v, ensure_ascii=True)[1:-1]`, `json.dumps(v, ensure_ascii=False)[1:-1]`, `urllib.parse.quote(v, safe="")` and `quote_plus(v)`. Empty needles and duplicates are dropped.
  - Masking is **one pass** of one compiled alternation (`re.escape`), longest needle first, with a replacement function. A replacement such as `[secret:x]` is never re-scanned, so a value like `secret` can't corrupt an earlier mask.
- [ ] AC4. **Fail closed.**
  - If loading values or grants raises, `prepare` returns the refusal "Secrets are unavailable right now, so this tool call was not run." and the tool does not run. This applies whether or not the arguments hold a token, since without the values the output can't be masked.
  - If `mask` raises, the loop returns an error result "The tool's output could not be checked for secrets, so it was withheld." and never the unmasked output.
  - With no tokens and no stored secrets, `prepare` returns the args unchanged and an identity mask. This is the fast path; it still costs one query.

**The loop hook (`the_one/agent/core.py`, the approved frozen-loop touch)**
- [ ] AC5. `Agent.__init__` gains a keyword `secrets: SecretResolver | None = None`. It is keyword-only after `max_iterations`, and the default keeps today's behaviour exactly, which existing hand-built `FakeLLM` agents rely on. In `_execute_tool`:
  - `prepared = None` is set **before** the inner `try`.
  - Inside the inner `try`, after `bind_positional_args` and before `wait_for`, when `self._secrets` is set: `prepared = await self._secrets.prepare(tool_call.name, args)`. A refusal returns `ToolResult(tool_call_id, content=refusal, is_error=True)` without calling `tool.execute`. Otherwise `args = prepared.args`.
  - After the tool runs, `output = prepared.mask(output)` (when `prepared` is set) happens **before** `self._govern(output, ...)`.
  - In the timeout and generic `Exception` branches, the error string is masked with `prepared.mask` when `prepared` is set, and passed unchanged otherwise. That covers a failure in `tools.get`, `bind_positional_args` or `prepare` itself, which happens before any substitution, so the string can't contain a value. `prepare` raising is reported by AC4's unavailable refusal: `prepare` catches its own load errors and returns that refusal rather than raising.
  - A `mask` failure on **any** path (normal, timeout, generic) returns the AC4 withheld-output error.
  - `MCPAuthRequired` is unchanged (its content and `metadata` are fixed fields).
  - **Only `ToolResult.content` and the two error strings are masked.** `metadata` is set only by the `MCPAuthRequired` branch, with fixed fields. State this in agents.md.

  `tool_call.arguments` is never mutated: a test asserts it equals its pre-call deep copy after execution.
- [ ] AC6. `resume_after_auth` re-dispatch goes through `_execute_tool`, so it re-prepares. A test covers it, or the leg cites the code path if a test would need MCP auth machinery. The `continue` virtual tool never reaches the hook.

**The factory**
- [ ] AC7. `AgentFactory.create` passes `secrets=SecretResolver(config.name)` to **every** `Agent(...)` it builds, with or without grants. `factory.py:635` is the only construction site in `the_one`, `evals` and `scripts`. Eval runs go through `AgentFactory` (`evals/harness.py:368`), so the resolver is present there too. A test builds agents with and without grants (and the `default` agent) and asserts each has a resolver. A test shows that an agent with no grants that writes a token gets the "not granted" refusal and the tool is not called.

**End-to-end loop tests (`FakeLLM` + `StubTool`, real template DB)**
- [ ] AC8. A granted secret in an allowed tool reaches the `StubTool` with the real value in a nested argument.
  - The Agent's `messages` assistant tool call still holds the placeholder.
  - `FakeLLM`'s recorded calls (what the provider would be sent) contain the placeholder and never the value.
  - The stored session (`encode_messages(agent.messages)`) contains no value.
- [ ] AC9. A `StubTool` that echoes its arguments has its result masked. Separate tests cover:
  - a str result, a dict result and a list result;
  - a value with both quote types, a backslash and a non-ASCII character, echoed via `repr`, JSON with `ensure_ascii` on and off, and URL encoding;
  - an **ungranted** secret's value appearing in output;
  - a value straddling the governor's truncation point (masked before truncation);
  - a dict result whose value appears only in a **key**;
  - a `bytes` result (errors, value absent);
  - a tool that raises an exception whose message contains the value;
  - a timeout.
- [ ] AC10. Refusals: a not-granted key, a not-allowed tool and a refused-set tool listed in a stored `allowed_tools` row (inserted directly in the DB to bypass the API check) each give the exact refusal text. The tool is not called, and the value appears nowhere.
- [ ] AC11. Freshness on **one Agent object**:
  - after a `SecretRepository.update` changes a value, the next call gets the new value;
  - after a key rotation (`install_key` through the same path the rotate route uses, or the route via `shared_app()`), the next call still resolves;
  - after a grant is removed from `agents.secret_ids`, the next call is refused.
- [ ] AC12. Rename and context, with entry-point coverage as the review found it:
  - REST and routines set `current_turn` (`app.py:2597`);
  - the WebSocket sets `current_chat_session_id` only (`app.py:1246`);
  - connectors and resume set both;
  - the CLI and selftest set a `TurnContext()` with no session.

  Tests:
  - with a session row bound through `current_turn` only, and separately through `current_chat_session_id` only, renaming the agent (`store.rename`) keeps the open Agent resolving its grants through the session's current `agent_name`;
  - with a turn context whose session id has **no row**, and with no session at all, the resolver falls back to the constructor's agent name.
- [ ] AC13. Entry points: a connector turn and a routine run each reach the hook (a token is substituted and the result masked).
  - Connector: reuse `tests/test_connectors_inbound.py` / `tests/test_inbound_session_updated.py` (the latter has `repos` and a factory seam, `:128-149`).
  - Routine: grep `tests/` for `run_routine` and reuse its seam.
  - If either has no practical seam, cite the code path that proves it goes through `factory.create` and `_execute_tool`, and say so in the flight log.
- [ ] AC14. Logs: one built-in tool call and one MCP tool call, each with a substituted value, run under `caplog` at DEBUG for all loggers. Use `tests/fixtures/mcp/hello_server.py`'s `echo(message)` tool (`:73`), which also proves masking of an echoed MCP result. No log record contains the value. Check `httpx2`/`httpcore2` explicitly: an MCP request body logged at DEBUG is the likeliest leak.
  - The leg also greps the execution path and the MCP client for logging of tool arguments or request bodies. Any logger that prints them (including `httpx2`, `httpcore2`, `mcp`) is quieted in `logging_config.py` or its call site fixed.
  - The grep result is recorded in the flight log.

**Prompt layer (DD8)**
- [ ] AC15. `the_one/db/_secrets.py::render_secrets_block(entries)` takes entries `[(key, secret_name, description, allowed_tools)]` and returns `""` for none. For one or more it returns a block in the style of `_rules.py`/`_notes.py` (match their heading and list conventions) that:
  - tells the agent to write `{{secret:key}}` inside a tool argument;
  - says the value is filled in when the tool runs and the agent never sees it;
  - says output shows `[secret:key]` where a value appears;
  - says each key works only in the listed tools;
  - tells it not to ask the user for a secret's value;
  - lists one line per key with its placeholder, the secret's name and description, and its tools.

  It is a pure function; snapshot-free unit tests check the empty case, one secret with two keys, and the order (secrets by name, keys by position).
- [ ] AC16. `compose_system_prompt` gains keyword `secrets: str = ""` (the rendered block) placed after notes and before the date line, joined by the existing separator. An empty block adds nothing, so the composed text is byte-identical to before for an agent without grants.
  - `build_system_prompts` loads the agent's granted secrets' keys, names, descriptions and allowed tools (**no decryption**) and passes the block to the `tool_capable` composition only, never `tool_free`.
  - `self_configuration/pending.py` passes it on its main path. Its fallback (`compose_system_prompt(render_platform(caps), system_prompt)`, used when the DB path failed) tries to load the block and passes `secrets=""` if that load raises. The fallback must never raise.
  - Tests cover both callers' main paths, "the fallback never raises", and the tool-free exclusion.
  - **The byte-identity guard** is the existing exact-output tests: `tests/test_prompt_layers.py`, `tests/test_config.py:230+` and `tests/test_evals_tokens.py`. They must stay green unchanged with the `secrets=""` default. Add one exact-output test with a block present.
- [ ] AC17. `/api/info` gains `secrets_prompt_example`, rendered by `render_secrets_block` from fixed sample entries (e.g. a "Home address" secret with `home_address` and `home_city` in `mcp__goldfinch__typeText`). The existing `/api/info` key pins are updated.
- [ ] AC18. **Eval no-leak check (DD8, option b):**
  - Before changing any prompt code, run `make eval ARGS="measure-prompt --json <scratch>/measure-before.json"`. The scratch path is outside the repo, e.g. the flight's scratch under `$HOME`.
  - After the leg, run it again as `measure-after.json`.
  - The two files' size figures for every configuration (bare, all-on, tool-free and the connector variants) are identical. Record both totals in the flight log.
  - If they differ, stop and report: that is the flight's divert criterion.
  - No `run` or `compare` is needed (no model calls, no plan quota). If `measure-prompt` itself fails for an environmental reason (tokenizer download), report it rather than skipping.
  - **What this proves:** no measurement scenario grants a secret, so before and after are identical by construction once an empty block adds nothing. The check confirms that end to end, through the factory (with the resolver present) and the eval harness. The real guard is AC16's byte-identity tests. The output path **must** be outside the repo: `evals/tokens.py` does not refuse a path inside it.

**Gate and docs**
- [ ] AC19. `THE_ONE_TEST_NETNS=1 make test-unit` passes, with the expected 15 skips under netns (explain any other count from `-rs`). Run it **after** the last code change. `ruff check` and `ruff format --check` are clean on `the_one/`, `tests/`, `scripts/` and `evals/`.
- [ ] AC20. The docs listed under Outputs are updated. agents.md records the frozen-loop touch beside the `send_to_platform_channel` precedent, and the prompt-layer timing: the layer is fixed at Agent build, and reaches an open chat at its next rebuild (a new chat, a rejoin, the next REST call, or a connector message), while substitution changes on the next call.

## Verification Steps
- AC1-AC4: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_secret_runtime.py -x --timeout 60`.
- AC5-AC14: `... tests/test_secret_loop.py -x --timeout 60` plus the connector and routine tests touched.
- AC15-AC17: `... tests/test_secret_prompt_layer.py` plus the `/api/info` and prompt-layer test files touched.
- AC18: the two `measure-prompt` JSON files and their diff.
- AC19: `THE_ONE_TEST_NETNS=1 make test-unit`; ruff.
- **Falsification** (report yes or no for each): AC2's no-mutation, AC3's single pass (by switching to sequential `str.replace` and showing the corruption), AC4's fail-closed paths, AC5's mask-before-govern (by moving the mask after `_govern` with the straddling test), AC7's every-agent resolver, AC8's provider-request check, AC9's repr needle and ungranted-value masking, AC10's refused-set runtime check, AC11's same-Agent freshness (by adding a resolver cache), AC14's log check.

## Implementation Guidance

1. **Baseline measurement first** (AC18 "before"), at the leg's starting code.
2. **`runtime.py`**:
   - token pattern, needle builder, one-pass masker, `Prepared`, `SecretResolver.prepare`;
   - the agent-name lookup (`SELECT agent_name FROM chat_sessions WHERE id = ?`);
   - grants from `agents.secret_ids`, secrets' `allowed_tools`, and keys→secret ids from leg 1's repository or a small read helper. Only `all_values()` decrypts.
   - Import `is_refused_tool` and the context vars; there is no import of `the_one.agent` package internals beyond `_context` (check for cycles with a fresh-interpreter import test, as leg 1 did).
3. **The loop hook** in `core.py`, minimal, with a comment naming DD7 and the owner approval.
4. **Factory** injection.
5. **Loop tests**, falsifying as you go.
6. **`_secrets.py` render** (style of `db/_notes.py`: a heading constant, a pure render function, and **no `the_one.agent` import**, per its header's cycle rule). Then the composer, both callers and `/api/info` (update the key-list pin in `tests/test_prompt_layers.py`).
7. **Log sweep and test.**
8. **Measure after**, the unit gate, docs.

## Edge Cases
- **Token inside a longer string** (`"Bearer {{secret:api_key}}"`): substituted in place. **Two tokens in one string**: both substituted. **The same token twice**: both.
- **Token with different case from the stored key** (`{{secret:Home_City}}` vs `home_city`): resolves; the refusal (if any) echoes what the model wrote; the mask uses the stored key.
- **Malformed token** (`{{ secret:x }}`, `{{secret:}}`): ordinary text, not substituted, not refused.
- **A value that contains another value** (`abc` and `abcdef`): longest-first alternation masks `abcdef` whole.
- **Non-string args** (numbers, bools, None): passed through unchanged.
- **A tool returning bytes or another non-str/dict/list/tuple type**: see AC3: returned unchanged; `bytes` already errors in `ToolResult.__post_init__`; the residual is documented.
- **`_govern` truncation markers**: masking happens first, so a mask token may itself be truncated; that's acceptable (no value fragment remains).

## Files Affected
See Outputs.

## Citation Audit
Checked by the Flight Director on 2026-11-04 against `dfc6677e`:
- `repositories.py:2033` `SecretRepository`, `:2101` `get_values`, `:2110` `all_values`: verified.
- `agent/_context.py:46` `current_chat_session_id`, `:108` `current_turn`; `notes/tools.py:122` lookup pattern: verified.
- `factory.py:617-650` (`build_system_prompts` call, `Agent(...)` at `:635`): verified.
- `prompt_layers.py:125-133` (`layers` passed to both compositions): verified.
- `core.py:608-672` `_execute_tool`: verified at planning; unchanged by leg 1.
- `app.py:3110` `rules_prompt_example`: verified.
- `evals/baselines/m30-platform.json` keys include `sizes`; `measure-prompt --json` exists (`evals/README.md:42`): verified.
