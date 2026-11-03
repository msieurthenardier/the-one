# Behavior Test: Self-configuration Leaves the Tools Tab

**Slug**: `self-configuration-off-tools-tab`
**Status**: active
**Created**: 2026-11-03
**Last Run**: 2026-11-03-15-45-56 (pass, 11/11; see runs/2026-11-03-15-45-56.md)
**Updated**: 2026-11-03 (after the first run: wording from the Validator's closing observations; no expectation weakened)

## Intent

Verifies sortie 08 against a real running instance. The Tools tab shows no self-configuration server. Saving an agent never detaches the server. The API refuses a per-agent setting for it. A tool selection stored before the change stops applying while the app runs, and is removed at the next restart. Unit and browser tests pin each piece separately. This test proves the pieces together on one instance and one database, across a real restart, and it observes the agent's actual toolset through a real tool call rather than a projection. The write tool `update_my_description` is the probe: a revision row in `GET /api/agents/{name}/self-configuration/revisions` exists only if the agent really had the tool and called it.

## Preconditions

- **Never target port 8484 or 8485, or the operator's default data directory** (CLAUDE.md "SAFETY RULE"). Use a dedicated dev instance built from the sortie branch, on port 8486 or higher, with a scratch data directory under `$HOME` and a scratch working directory, started as CLAUDE.md "Behavior-test credential convention" shows, with `THE_ONE_DEV_MODE=true` and `THE_ONE_LOG_LEVEL=INFO` set explicitly (step 10 asserts an INFO line, and the level otherwise comes from the environment). Record the PID and the exact start command (step 10 restarts with it).
- A credential exists (`THE_ONE_DATA_DIR=<scratch> the-one rotate-api-credential`). Shell requests carry `Authorization: Bearer <credential>`. The browser is signed in through `POST /api/session/handoff`, with a fresh mint after the restart in step 10.
- `GET /api/live` answers 200.
- A browser apparatus is registered (goldfinch MCP or similar) and can open a tab on `http://127.0.0.1:<port>`.

## Observables Required

- **browser**: the agent editor's Tools and Self-configuration tabs (DOM: `data-testid` attributes and visible text) and the Chats pane, measured through the registered browser apparatus.
- **http**: `GET /api/agents/{name}` (`mcp_source_ids`, `mcp_overrides`), `GET /api/agents/{name}/self-configuration` (`enabled`), `GET /api/agents/{name}/self-configuration/revisions` (rows and their proposed text), the 422 body of a refused `PUT`, measured through `curl` in the shell.
- **shell**: running a short Python script with the repo venv against the scratch data directory (step 8), stopping and starting the instance by PID (step 10), and reading the instance's log (step 10).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Over HTTP, create a `mock` provider (`POST /api/providers`, type `mock`, with a `base_url` such as `http://127.0.0.1:9`, which the API requires, and `config: {"models": ["mock-default"], "response": {"content": "ok"}}`). Then create an agent `probe` that uses it: the fields are `provider_config_id` (the provider's id) and `llm_model: "mock-default"`, with `max_iterations: 2`. Then create an ordinary MCP source `probe-ordinary` (`POST /api/mcp-sources`, type `streamable-http`, `config: {"url": "http://127.0.0.1:9/mcp"}`). Do not attach it. | (setup) |
| 2 | In the browser, open the agent editor for `probe` on its Self-configuration tab and turn on the Agent prompt switch ("Let this agent edit its description and system prompt"). Then read `GET /api/agents/probe/self-configuration` and `GET /api/agents/probe`. | The switch reads on. `enabled` is `true`. `mcp_source_ids` holds exactly one id; call it **S**. |
| 3 | Open the Tools tab and look at its MCP servers section. Do not expand any tile: tool rows are checked against the rendered page text and accessibility snapshot. | A tile for `probe-ordinary` is shown. No element has `data-testid="mcp-source-toggle-{S}"` or `data-testid="mcp-source-self-configuration-hint-{S}"`. The section shows no text "managed on the Self-configuration tab" and no tile titled "self-configuration". No tool row names `get_my_configuration`, `describe_my_capabilities`, `update_my_description` or `update_my_system_prompt`. |
| 4 | Delete `probe-ordinary` over HTTP (`DELETE /api/mcp-sources/{id}`), then reload the page and open `probe`'s Tools tab again. | The MCP servers section shows its empty state (`data-testid="mcp-empty-state"`). There is still no tile for **S**. |
| 5 | On the General tab, change the description to `Probe agent v2` and click Save. Then read `GET /api/agents/probe` and `GET /api/agents/probe/self-configuration`, and open the Self-configuration tab. | The save succeeds, with no error shown. The stored description is `Probe agent v2`. `mcp_source_ids` still contains **S**. `enabled` is `true`, and the Agent prompt switch still reads on. |
| 6 | On the Tools tab, turn one built-in tool off for this agent (default `mkdir`, reached by opening the Filesystem category's tool list; never `current_time`) and click Save. Then read `GET /api/agents/probe`. | The save succeeds. `mcp_source_ids` still contains **S**. |
| 7 | Over HTTP, send `PUT /api/agents/probe` with the body of the current `GET /api/agents/probe`, plus `"mcp_overrides": {"self-configuration": {"disabled_tools": ["update_my_description"]}}`. Then read `GET /api/agents/probe`. | The PUT returns 422, and its `detail` is a short plain message (no codes or field paths) that names the Self-configuration tab. The stored `mcp_overrides` has no `self-configuration` key. `mcp_source_ids` still contains **S**. |
| 8 | With the instance still running, write a legacy selection directly to the database. That is the state an older build's Tools tab left behind, and the API now refuses to write it. Run a short Python script with the repo venv and `THE_ONE_DATA_DIR=<scratch>`: load `probe` through `SQLiteAgentStore(await get_connection(), get_encryptor(settings.data_dir))`, set `mcp_overrides["self-configuration"] = {"disabled_tools": ["update_my_description", "update_my_system_prompt"]}`, also add `"mcp__self-configuration__update_my_description"` to `disabled_tools`, save it, and `await close_connection()` before exiting. (`save` commits through its write transaction. Python's default 5 s SQLite timeout applies against the live server, so retry once on "database is locked".) Then read `GET /api/agents/probe`. | The script exits 0. The GET shows `mcp_overrides["self-configuration"]` with both tools in `disabled_tools`, and `disabled_tools` contains `mcp__self-configuration__update_my_description`, which proves both legacy withholds are in place. |
| 9 | Update the mock provider so every reply calls the write tool (`PUT /api/providers/{id}`, `config.response = {"content": "", "tool_calls": [{"id": "c1", "name": "mcp__self-configuration__update_my_description", "arguments": {"text": "PROBE-DESC-1", "apply": "next_turn"}}]}`). In the browser, start a new chat with `probe` (Chats › New chat, pick `probe`) and send `go`. Wait for the turn to end, then read `GET /api/agents/probe/self-configuration/revisions`. | A revision row exists whose proposed value is `PROBE-DESC-1`. The agent had `update_my_description` and called it, even though both stored withholds from step 8 disable it, which is the build-time ignore at work. The transcript shows no "unknown tool" or similar error for that call. Expected with this setup: the mock repeats its call, so the turn shows two tool calls, writes two revision rows and ends in the step-limit notice ("Stopped: this agent used its 2 steps…"). |
| 10 | Stop the instance by its PID and start it again with the same command, port and data directory. Wait for `GET /api/live` to answer 200. Read the instance log, then `GET /api/agents/probe` and `GET /api/agents/probe/self-configuration`. | The log has a line from the startup cleanup that names agent `probe` (2026-11-03 wording: `self-configuration: removed a per-agent withhold of the surface's tools from agent 'probe' (disabled_tools, mcp_overrides)`, logger `the_one.self_configuration.manage`). `mcp_overrides` has no `self-configuration` key, and `disabled_tools` has no `mcp__self-configuration__` entry. `mcp_source_ids` still contains **S**, and `enabled` is `true`. |
| 11 | Set the mock provider's tool-call text to `PROBE-DESC-2` (same shape as step 9). Mint a fresh handoff, sign the browser in again, start a new chat with `probe` and send `go`. Wait for the turn to end, then read the revisions. | A revision row with proposed value `PROBE-DESC-2` exists (two are expected, as in step 9). |
| 12 | Open `probe`'s Self-configuration tab and turn the Agent prompt switch off. Then read `GET /api/agents/probe` and open the Tools tab. | The switch reads off. `mcp_source_ids` no longer contains **S**. The Tools tab's MCP servers section shows its empty state and no self-configuration tile. |
| 13 | Stop the instance by its PID. | (teardown) |

## Out of Scope

- The Self-configuration tab's approval queue, history, restore and external access, which this sortie leaves unchanged. Those are covered by `tests/browser/test_studio_self_configuration_*.py` and `agent-self-revision-propagation`.
- The Routines item and its native tools.
- Whether a real model chooses to call the write tools. The mock provider's scripted call is deliberate: the property under test is whether the tool is available, not the model's judgment.
- The `search_tools` index and the `describe_my_capabilities` projection, the two other build sites the leg changes. Unit tests cover them.
