# Behavior Test: Per-agent MCP Credentials

**Slug**: `per-agent-mcp-credentials`
**Status**: active
**Created**: 2026-11-03
**Last Run**: 2026-11-04-18-29-45 (13/14; step 5 failed on a spec error, since amended per the operator's decision; see runs/2026-11-04-18-29-45.md). Previous: 2026-11-04-00-59-35 (pass, 14/14, the leg 3 UI).

## Intent

Verifies sortie 09 against a real running instance. One Library MCP server whose key is left blank ("Set per agent") is shared by three agents:
- two agents each reach it with their own key and see the tools that key allows;
- the third, with no key, is told it needs one.

A key changed and saved while a chat is open applies on that chat's next tool call. The shared tool cache is never written by a per-agent test, and no API response or log line carries a key.

Unit tests pin each rule separately. This test proves them together, on one instance, against a test server (`tests/fixtures/mcp/key_server.py`, sortie 09 DD11) that checks the key on every request and records the last 4 characters of the key each request carried. That request log is the independent witness of which credentials each agent actually sent.

## Preconditions

- **Never target port 8484 or 8485, or the operator's default data directory** (CLAUDE.md "SAFETY RULE"). Use a dedicated dev instance built from the sortie branch, on port 8486 or higher, with a scratch data directory and a scratch working directory under `$HOME`, started as CLAUDE.md "Behavior-test credential convention" shows, with `THE_ONE_DEV_MODE=true`, `THE_ONE_LOG_LEVEL=INFO` and `MCP_POOL_IDLE_TTL_SECONDS=3600`. The long idle timeout means step 12's reconnect can only come from eviction on save, not from the idle reaper. Record the PID.
- A credential exists (`THE_ONE_DATA_DIR=<scratch> the-one rotate-api-credential`). Shell requests carry `Authorization: Bearer <credential>`. The browser is signed in through `POST /api/session/handoff`, with one mint per fresh browser context.
- `GET /api/live` answers 200.
- The key server is started from the repo venv as a separate process on a free port, with header `X-Api-Key` and three keys:
  - `key-ALPHA-7Q2` sees `echo`;
  - `key-ALPHA2-3K8` sees `echo`;
  - `key-BETA-9Z4` sees `echo` and `add`.

  Start it from the repo root with the repo venv:
  `.venv/bin/python -m tests.fixtures.mcp.key_server --header X-Api-Key --keys "key-ALPHA-7Q2:echo;key-ALPHA2-3K8:echo;key-BETA-9Z4:echo,add"` (`--port 0`, the default, binds a free port and prints `PORT <n>` on stdout; `--keys` is `key:tool,tool;key:tool`, each key at least 8 characters). It serves MCP at `/mcp`. Its tools are `echo(message: str)` and `add(a: int, b: int)`. A request without a matching key gets a bare 401. Its request-log control route is `GET /_log` (no key needed; `DELETE /_log` clears it): a JSON list of `{seq, method, key_tail, status}` where `method` is the JSON-RPC method (`tools/call` is told apart from `tools/list`), `key_tail` is only the last 4 characters of the key sent (`null` when none) and `status` is 200 or 401. It stops within about a second on SIGTERM. Record its port **K** and PID.
- A browser apparatus is registered (goldfinch MCP or similar) and can open two tabs on `http://127.0.0.1:<port>`.
- Dry-run steps 1-2's requests once before the witnessed run (M34 F2 debrief).

## Observables Required

- **browser**: the Library MCP editor, the agent editor's Tools tab (DOM `data-testid` attributes and visible text) and the Chats pane, measured through the registered browser apparatus.
- **http**: `GET /api/agents/{name}` (`mcp_overrides`, `mcp_tool_cache`), `GET /api/mcp-sources/{id}` (`config._cache`), `POST /api/mcp-sources/{id}/test/agent`, `PUT /api/agents/{name}`, `PUT /api/agents/{name}/mcp-overrides/{id}/credentials` (the tile's Save), measured through `curl` in the shell or the browser's network log; the key server's request log. Read `GET /_log` before and after every step and keep both as evidence.
- **shell**: `grep` over the instance log and the scratch data directory's log files; stopping processes by PID.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Over HTTP, create a `mock` provider (`base_url` `http://127.0.0.1:9`, `config: {"models": ["mock-default"], "response": {"content": "ok"}}`). Create agents `alpha`, `beta` and `plain` that use it (`llm_model: "mock-default"`, `max_iterations: 1`; the mock repeats its tool call every iteration, so each turn makes one call and ends with the step-limit notice). Create an MCP source `keyed`: type `streamable-http`, `config: {"url": "http://127.0.0.1:K/mcp"}`, `secrets: {"X-Api-Key": ""}`. Attach it to no agent. | (setup) Every request returns 2xx. |
| 2 | Read `GET /api/mcp-sources/{keyed id}`. | `secrets` has the name `X-Api-Key` with an empty value. `config` has no `_cache.tools`. |
| 3 | In the browser, open `keyed` in Library › MCP servers. | The `X-Api-Key` row's value input is empty and shows the placeholder "value". A hint (`mcp-env-headers-hint`) near the headers table reads "Optionally override headers in agent settings." |
| 4 | Open agent `alpha`'s Tools tab and turn on the switch for `keyed`. Do not type anything. | The tile expands. It shows a "Headers" section (`mcp-agent-cred-section-{id}`) holding the locked table (`mcp-agent-cred-table-{id}`) with an `X-Api-Key` row (`tr.ui-kv-row[data-name="X-Api-Key"]`) whose value input is empty (placeholder "value") and has no "overridden" pill (`.ui-kv-marker` hidden or absent). The locked table has no Sensitive column, no trash and no "+ Add row". The action row shows Override headers (`mcp-agent-cred-override-{id}`) and Test (`mcp-agent-cred-test-{id}`); there is no Refresh button. The status line (`mcp-agent-cred-status-{id}`) reads "Needs a value for X-Api-Key". The tile shows no tool rows. The missing value is computed in the client, so no `/test/agent` request is sent (check the browser's network log), and no new request reaches the key server. The agent editor's Save (`save-agent-btn`) is enabled only because the attach switch is unsaved. |
| 5 | Press Override headers (`mcp-agent-cred-override-{id}`). The table becomes editable and the action row becomes Cancel (`mcp-agent-cred-cancel-{id}`), Save (`mcp-agent-cred-save-{id}`, disabled) and Test. Type `key-ALPHA-7Q2` into the `X-Api-Key` row's value input, then press Test (`mcp-agent-cred-test-{id}`). | The `X-Api-Key` key input is read-only and its Sensitive toggle is on; Save becomes enabled once the value is typed. Before Save nothing is stored: `GET /api/agents/alpha` has no `mcp_overrides.keyed`. The "overridden" pill already shows on the row, because it marks a value that differs from the server's, saved or not (operator decision, 2026-11-04, HAT H6 and behavior-test run 2026-11-04-18-29-45). The status line (`mcp-agent-cred-status-{id}`) reads "Connected with this agent's values · 1 tool" (or equivalent wording with the count 1). Exactly one tool row, `echo`, is shown. The key server's log shows requests carrying the key ending `-7Q2`. |
| 6 | Press the tile's Save (`mcp-agent-cred-save-{id}`) and wait for its live status (`mcp-agent-cred-live-{id}`) to read "Saved" and for the status line to settle after the post-save re-test. Then press the agent editor's Save (`save-agent-btn`) to store the attach switch. Read `GET /api/agents/alpha` and `GET /api/mcp-sources/{keyed id}`. | The tile's Save sends one `PUT /api/agents/alpha/mcp-overrides/{id}/credentials` (the key is written at once, before the agent's own Save) and the table locks again with focus on Override headers. The `X-Api-Key` row now shows a masked value (at most its last 4 characters) and the "overridden" pill. The agent editor's own PUT carries no `headers`, `env` or `bearer_token`. `mcp_source_ids` contains the `keyed` id. `mcp_overrides.keyed.headers` has the name `X-Api-Key` with a masked value that shows at most its last 4 characters (the existing mask rule). The response text does not contain `key-ALPHA-7Q2`. `mcp_tool_cache[<keyed id>].tools` lists `echo` only. `keyed`'s `config._cache` has no `tools`, no `auth_posture` and no `last_check`. |
| 7 | Reload the page and open `alpha`'s Tools tab and the `keyed` tile again. | The locked table's `X-Api-Key` row shows the masked value (never the full key) and the "overridden" pill. The tile lists exactly one tool row, `echo`, and the status line reads the cached wording "Last checked with this agent's values · 1 tool", without a new request reaching the key server (its log has no new entry). The form is clean: the editor's Save (`save-agent-btn`) is disabled and the `editor-unsaved` caption is empty. |
| 8 | Over HTTP, set `beta`'s key: `PUT /api/agents/beta` with its current body plus `mcp_source_ids` including `keyed` and `mcp_overrides: {"keyed": {"headers": {"X-Api-Key": "key-BETA-9Z4"}}}`. Then `POST /api/mcp-sources/{keyed id}/test/agent` with `{"agent": "beta", "overrides": null}`. | The PUT returns 200. The test returns `status: "ok"` with tools `echo` and `add`. The key server's log shows the key ending `-9Z4`. |
| 9 | Over HTTP, attach `keyed` to `plain` with no override. Then `POST .../test/agent` with `{"agent": "plain", "overrides": null}`. | The PUT returns 200. The test returns `status: "needs_values"` with `missing: ["X-Api-Key"]` and no tools. No new request reaches the key server. |
| 10 | Set the mock provider's response to call the MCP tool: `{"content": "", "tool_calls": [{"id": "c1", "name": "mcp__keyed__echo", "arguments": {"message": "from-alpha"}}]}` (`echo` takes `message`; the response is global to the provider, so every agent on it makes this call until it is changed in step 13). In browser tab 1, start a new chat with `alpha` and send `go`. Wait for the turn to end. Keep this chat open. | The transcript shows a tool call to `echo` whose result contains `from-alpha`, no tool error, and the step-limit notice. The key server's log has a `tools/call` entry for this call, and it carried the key ending `-7Q2`. |
| 11 | In browser tab 2 (a new context with a fresh handoff mint), open `alpha`'s Tools tab and the `keyed` tile, press Override headers (`mcp-agent-cred-override-{id}`), type `key-ALPHA2-3K8` over the masked value in the `X-Api-Key` row's value input and press the tile's Save (`mcp-agent-cred-save-{id}`). | The save succeeds with no agent Save: the live status (`mcp-agent-cred-live-{id}`) reads "Saved" and the table locks. The locked `X-Api-Key` row shows a new mask ending `-3K8` and the "overridden" pill. |
| 12 | Back in tab 1, without reloading or reopening the chat, send `again`. Wait for the turn to end. | The transcript shows a second `echo` call with no tool error. The newest `tools/call` entry in the key server's log (by sequence number, after step 11's re-test `tools/list` entries) carried the key ending `-3K8`, not `-7Q2`. (With the idle timeout pinned at 3600 s, only eviction on save explains the new key.) |
| 13 | In a new chat with `beta` (tab 1), with the mock response changed to call `mcp__keyed__add` (arguments `{"a": 2, "b": 3}`), send `go`. | The transcript shows an `add` result and no "unknown tool" error. The newest `tools/call` entry in the key server's log carried the key ending `-9Z4`. |
| 14 | Search the instance log and every file under the scratch data directory for the three full keys (`grep -r key-ALPHA-7Q2`, and likewise for `key-ALPHA2-3K8` and `key-BETA-9Z4`). | No file under the scratch data directory and no instance log contains any full key. The SQLite database holds them only inside the encrypted `agents.mcp_overrides` column, so a raw search of the database file finds none either. |
| 15 | Stop the instance and the key server by their PIDs. Confirm both ports are free. | (teardown) |

## Out of Scope

- The OAuth Authorization refusal (charter criterion 4) and the stdio "Environment for this agent" path. Unit tests and the HAT cover them, because an OAuth sign-in and a keyed stdio server need apparatus beyond this run.
- Per-agent OAuth sign-in (M07 F08 Anomaly A4).
- Whether a real model chooses to call the tool. The mock provider's scripted call is deliberate: the property under test is which credentials the call carried.
