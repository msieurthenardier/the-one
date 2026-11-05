# Sortie: Secrets

**Status**: completed

## Charter

### Outcome
An operator stores a secret once in the Library and grants it to agents. Those agents can use it in tool calls without the value ever appearing in a transcript, a request to the model provider, or the agent's prompt.

### Why Now
Today secrets (a Goldfinch vault key for `vaultUnlock`, website passwords, PII such as an address, email or phone number) sit in plain text in agent system prompts. They are sent to the model provider every turn, stored unencrypted, and the agent can repeat them back into a reply.

### Success Criteria
- [x] A granted secret used as `{{secret:key}}` in a tool call reaches the tool as its real value. The saved chat, the trace and the request to the provider contain only the placeholder.
- [x] A tool result or error containing a stored secret value reaches the model and the database as `[secret:key]`.
- [x] Using a secret that isn't granted, or in a tool that isn't on its allowed list, is refused with an error that names only the key.
- [x] Changing a secret in the Library changes what every granted agent uses on its next tool call, with no agent edits. No API ever returns the value.

### Constraints
- Secrets are encrypted with the app's Fernet key and included in key rotation; values are write-only.
- No environment-variable injection, no references from MCP headers (MCP headers and env already cover that), and no approve-each-use (later).
- A rendered mockup, in the app's real stylesheets and control factories, is approved before the legs are locked (sortie 09 lesson).

Charter agreed with the operator 2026-11-04. Moving secrets out of existing prompts is a manual operator step, not a helper. Criterion 2 was widened from "a granted value" to "a stored secret value" by the operator's mask-scope decision (DD7).

---

## Pre-Flight

### Objective
Add a Library item type, **Secret**: a friendly name, a description, one or more key/value pairs (values encrypted and write-only) and a required list of allowed tools. An agent is granted secrets in its Tools tab. In a tool call it writes `{{secret:key}}`; the agent loop fills the value into a copy of the arguments just before the tool runs and masks every stored secret value in what comes back. The agent learns its keys from a new prompt layer, shown on Settings › Prompts.

### Open Questions
All resolved with the operator on 2026-11-04 (flight log, "Crew interview").
- [x] Library editor model: like the provider editor (DD1).
- [x] Grant surface: a Secrets section at the top of the Tools tab, switch rows (DD2).
- [x] Allowed tools: required, chips with search-ahead (DD3).
- [x] Multi-value secrets: a list of key/value pairs, first key generated from the name, unique keys (DD4).
- [x] Delete: allowed; grants are removed (DD5).
- [x] Mask scope: every stored secret, not only grants (DD7).
- [x] Discovery: a prompt layer, shown on Settings › Prompts (DD8).
- [x] HAT: yes. Behavior test: yes. Legs: 3 plus HAT, accepted above the soft limit.

### Design Decisions

**DD1: Library › Secrets looks and acts like the provider editor (mockup approved, round 2).**
- A fifth Library group, "Secrets", after Connectors. Rows: key icon, the friendly name, meta "N values · N agents" (`App.usage.secretAgents`). The Add menu gains "Secret". The Library start page gains a Secrets card.
- Routes: `#library/secrets/~new` and `#library/secrets/{id}`, following the connector routing (`router.js` `SECTIONS`, section labels and the collection map; `studio-route.js`).
- Editor (`App.ui.editorShell`, breadcrumb "Library / Secrets"; Cancel and Save/Create; no Test):
  - Section "Secret": Name (`App.ui.textInput`), Description with the hint "Agents see the name, description and keys, never the values."
  - Section "Values" (stack layout, description as in the mockup): an `App.ui.keyValueTable` with columns Key (mono) and Value (`type: 'secret'`, always masked, stored mode via `storedKey`), "+ Add pair", remove per row, `keyColumn: 'key'` (a renamed key with a stored mask clears the value, the table's existing rule). On a new secret, the first row's key follows the name (`slug`: lowercase, runs of other characters to `_`, trimmed) until the operator edits that key.
  - Section "Allowed tools": `App.ui.chipList` with search-ahead (DD3).
  - Section "Used by": the granted agents as links to `#agents/{name}/tools`, or "No agent uses this secret yet."
  - Danger zone: "Delete secret", armed with `App.ui.confirm`; while any agent holds a grant, the arm text names the count ("Used by N agents; deleting removes it from them").
- **The approved mockup is kept in `sorties/10-secrets/mockup/`:**
  - `s10-mockup.js`, the round-2 script, built on `App.ui` factories, which the Developer reads as the reference;
  - `r2-1-home-address-light.png` (editor and search-ahead open);
  - `r2-2-new-light.png` (a new secret with the first key generated and the allowed-tools refusal);
  - `r2-3-tools-{light,dark}.png` (Tools tab);
  - `5-chat-transcript-{light,dark}.png` (transcript and drawer).

  The built Library list, editor, Tools-tab section and drawer group must match it.
- **Approved copy** (wording may be polished, not restructured):
  - Description hint: "Agents see the name, description and keys, never the values."
  - Values section description: "Agents use each key as {{secret:key}} in a tool call; the value is filled in when the tool runs. Values are stored encrypted and never shown again, and are hidden wherever they appear in a tool's output."
  - Allowed tools section description: "If an agent puts this secret in any other tool, the call is refused with an error that names the key, never its value."
  - Allowed tools field hint: "Only these tools can receive this secret's values. Type to search built-in and MCP tools."
  - Allowed tools empty refusal: "Choose at least one tool that may receive this secret."
  - Used by: "Granted to {agents}. Grant or remove it in each agent's Tools tab." / "No agent uses this secret yet. Grant it in an agent's Tools tab."
  - Library meta: "N value(s) · N agent(s)".
- Jump to (`static/js/jump-to.js`) lists secrets beside knowledge bases, MCP servers and connectors. The bare `#library/secrets` alias redirects to `#library`, like the other groups.

**DD2: Grants live in the agent's Tools tab, first section (mockup approved).**
- `AgentConfig.secret_ids: list[str]` (beside `kb_ids`, `agent/config.py:110`), persisted as `agents.secret_ids` JSON (v51, DD4).
- Tools tab (`agent-editor.js:91-125`): a new section "Secrets" (`h2`, testid `agent-tools-secrets-section`) inserted **before** MCP servers, with the intro line "Secrets this agent can pass to its tools. It never sees their values. Manage them in Library › Secrets." and one row per Library secret on the Knowledge tab's row shape (`knowledge-tab.js`): an `App.ui.toggle` labelled with the secret's name, then "{description} · N tool(s)". No keys and no tool names. Empty state: "No secrets yet." with a link to the Library.
- Save: the agent editor's main Save sends `secret_ids` only when the secrets list loaded (the `kb_ids` pattern, `agent-form-data.js:187-201`, root marker `data-secret-list-loaded`). `update_agent` preserves `secret_ids` when it is omitted, and an explicit `[]` clears it (copy `api.py:1526-1533`). `create_agent` defaults to `[]`.
- Unknown ids are refused on POST and PUT (422 on `loc ["secret_ids", i]`), so a stale editor cannot grant a deleted secret. Only ids new relative to the stored list are checked, as `tool_overrides` does. The Tools tab maps that 422 onto the section. Stored dangling ids (none expected after DD5) are ignored at runtime.
- Chat drawer (`areas/chat/agent-drawer.js`, "What it can use"): a read-only "Secrets" group after MCP servers listing granted secrets by name, "None" when empty.
- `agents-list.js:386-391` refreshes the secrets collection with the others.

**DD3: Allowed tools are required, chosen from a search-ahead over every tool name.**
- Server: `allowed_tools` must hold at least one name. Each name is a trimmed string of 1-128 characters with no whitespace. Empty list: 422 on `loc ["allowed_tools"]`. A bad entry: 422 on `["allowed_tools", i]`.
- Names are **not** checked against the catalogue: an MCP server's cached tool list can be empty or stale, and a typo shows up as a refusal in chat (Flight Director call).
- **Tools that store or publish their input are refused** (Architect review 1, medium; Flight Director call). If a tool persists its arguments and later feeds them back to the provider, a substituted value would become stored plaintext and break criteria 1 and 2. If it publishes them, the value goes to other people. The refused set is a module constant beside the resolver:
  - the notes tools and routine tools (`agent/tool_names.py`);
  - every `mcp__self-configuration__*` tool (match on `SURFACE_TOOL_PREFIX`, `self_configuration/constants.py:115`; never retype the prefix);
  - `send_to_platform_channel`;
  - the loop's virtual tools (`continue`, `search_tools`).

  Saving one is a 422 on `["allowed_tools", i]` ("{name} stores or publishes what it receives, so it can't receive secrets."). At runtime DD7 refuses a placeholder in these tools even if a stored row somehow lists one (defence in depth).
- **An MCP server rename carries `allowed_tools`** (Architect reviews 1-2, medium). This keeps a Goldfinch secret working after the server is renamed.
  - `mcp/rename_references.py::carry_mcp_rename` is agent-scoped: it loops over `agent_store.list_by_mcp_source`, has no transaction and never raises (`rename_references.py:66-91`). The secrets move is therefore a **separate loop over all secrets**, run after the agent loop: either inside the function, or as a sibling called right next to it.
  - The "keep the old name" check runs against **all** MCP sources, since names are not unique.
  - The secret repository is passed in untyped, to avoid an import cycle.
  - It is a plain UPDATE of the plaintext `allowed_tools` JSON in its own write transaction, keeping the never-raises and WARNING contract.
  - Both callers are updated and tested: `api.py:3798` (the MCP PUT) and `db/name_repair.py:111` (startup repair).
- New read-only route `GET /api/tool-names` returning `[{name, source: "builtin"|"mcp", source_name, description}]`. It is the union of:
  - built-ins (`BuiltinToolProvider`, as `GET /api/tools`, `api.py:921-926`);
  - every non-surface MCP source's cached tools under their prefixed names (`mcp__{sanitized source}__{tool}`, `mcp/_tool.py:54-61`);
  - the tools in `agent_mcp_tool_cache` rows. Their `tools` column is a JSON blob of tool metadata (`schema.py:3270-3279`), so the leg parses it and builds the prefixed name from `source_id` → source name.

  Duplicates are removed. Per-agent derived tools (`kb__…__search`) and the refused set above are left out.
- Client: before writing a new popover, check `js/ui/search-list.js` and `js/ui/menu.js` for a listbox pattern to reuse. Then add a new **`suggest`** option on `App.ui.chipList`: `suggest(term) -> [{value, label, detail}]` drives a listbox popover under the input (combobox pattern: `aria-expanded`, `aria-controls`, `aria-activedescendant`; Arrow keys move, Enter or click adds, Escape closes; Enter with no active suggestion keeps today's behaviour of adding the typed text). At most 8 suggestions, case-insensitive substring, already-chosen names left out. This changes a shared factory, so it needs its catalogue row in `docs/ui-control-inventory.md` and engine-parametrized contract tests (Chromium + WebKit) in the `contracts-controls` lane.

**DD4: Data model (schema v51).**
- `secrets(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', allowed_tools TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`.
- `secret_values(id TEXT PRIMARY KEY, secret_id TEXT NOT NULL REFERENCES secrets(id) ON DELETE CASCADE, key TEXT NOT NULL UNIQUE COLLATE NOCASE, value TEXT NOT NULL, position INTEGER NOT NULL)`; `value` is Fernet ciphertext. Uniqueness across all secrets is the SQL constraint.
- `agents.secret_ids TEXT NOT NULL DEFAULT '[]'` (guarded `ALTER TABLE` like v46, `schema.py:3176-3226`). `CURRENT_VERSION = 51`. Follow the v50 block shape (`schema.py:3265-3282`) and the frozen-imports rule (`tests/test_schema_frozen_imports.py`); pins in `tests/test_schema.py`.
- Key rule: `^[A-Za-z0-9_-]{1,64}$`, unique ignoring case. Placeholder grammar: exactly `{{secret:KEY}}` with no whitespace; anything else is ordinary text. **The placeholder lookup ignores case too**, matching the uniqueness rule; the mask always uses the stored key's spelling.
- The `Corpora` field is named `secret_values`, so it is not confused with the existing generic `secrets` blob columns or `count_items_with_secrets`.
- Repository: `SecretRepository` in `db/repositories.py` (list, get, create, update in one transaction, delete); `SQLiteAgentStore` gains `secret_ids` in `save` and `_row_to_config` and a `list_by_secret` modelled on `list_by_kb` (`repositories.py:196-222`).

**DD5: REST API under `/api/secrets`.**
- `GET /api/secrets`, `GET /api/secrets/{id}`, `POST /api/secrets` (201), `PUT /api/secrets/{id}`, `DELETE /api/secrets/{id}` (204). All behind the credential gate.
- Response shape: `{id, name, description, allowed_tools, values: [{id, key, value: "__MASKED__"}], created_at, updated_at}`. **Every value is the constant sentinel `__MASKED__`, with no tail** (Flight Director call: the existing `***…tail` mask shows the last four characters of a long value, which the charter's "no API ever returns the value" forbids). The Library editor renders the sentinel as a stored mask.
- Name: `_checked_name` (`api.py:192-197`) on create and on a present name in PUT; a duplicate name is 409 (`_name_conflict_detail`). Register `/api/secrets` in `tests/test_api_name_rule.py` (`PREFIXES`, `CHECKED`, `TestCreateRefuses`).
- **No pydantic body parameters on these routes** (Architect review 1, medium). The app has no `RequestValidationError` handler, so FastAPI's default 422 body would echo the submitted `input`, values included. The routes read `_read_json` and validate by hand through `_validation_detail` (`include_input=False`, `api.py:183-189`). A test sends a malformed body containing a value and asserts the value is absent from the 422.
- PUT is partial at the top level: an omitted `name`, `description`, `allowed_tools` or `values` key keeps the stored field.
- Values write shape (when `values` is present): the full ordered list of pairs `[{id?, key, value}]`. The pairs are written as delete-and-reinsert in one transaction, so swapping two keys never hits `UNIQUE COLLATE NOCASE` partway through.
  - `value == "__MASKED__"` with an `id` of a pair of this secret keeps that pair's stored ciphertext. The key may change: this is deliberate for API callers. The Library editor never sends it, because its table clears a masked value when the key is renamed (DD1);
  - `__MASKED__` without an id, or with an unknown id, is a 422 on `["values", i, "value"]`;
  - any other value is stored encrypted (an empty string is a 422 on the value);
  - a pair left out of the list is deleted;
  - at least one pair (422 on `["values"]`);
  - a key that breaks the rule, repeats within the body, or belongs to another secret (case-insensitively) is a 422 on `["values", i, "key"]` with a plain sentence, so the editor can place it on the row's key (sortie 09: say which part).
- `DELETE` removes the secret, its values (FK cascade) and its id from every agent's `secret_ids` in one transaction (operator decision); agents whose grants changed are listed in the log line, never values.
- The client store gains a `secrets` collection (`store.js` `URLS`), invalidated after every secret write and after agent saves that change grants.

**DD6: Secrets are the eighth encrypted corpus.**
- `secret_values.value`, registered in all five places in lockstep:
  - `db/key_reconcile.py:20-29` `_ENCRYPTED_CORPORA`;
  - `db/encryption_corpora.py`: a `Corpora` field, a `SELECT id, value FROM secret_values` in `gather_corpora` (the lead column satisfies `_LOOKUP_COLUMNS`, `tests/test_encrypted_corpora_guard.py:31`), and `count_items_with_secrets` (counts secrets with at least one value);
  - `api.py` `rotate_encryption_key` (`~:6979`): re-encrypt the field and add the `UPDATE secret_values SET value = ? WHERE id = ?` loop in the write transaction;
  - the "seven corpora" docstrings and the rotation log line.
- `tests/test_encrypted_corpora_guard.py` and `tests/test_encryption_status.py` are updated, not bypassed. A rotation test proves a secret still resolves after a rotation.

**DD7: Substitution and masking happen in `_execute_tool`, and fail closed.**
- New leaf module `the_one/secret_store/runtime.py` (package renamed from `the_one/secrets/` at leg 1 design: seven modules `import secrets` from the stdlib) (no `evals/` import): a `SecretResolver` passed to `Agent` through a new constructor kwarg.
  - The default is `None`, a no-op, so hand-built `FakeLLM` agents in unit tests keep working.
  - **The factory injects a resolver into every Agent it builds, with or without grants** (Architect review 2, medium). Without one, a placeholder from an agent with no grants would reach the tool as literal text, and stored secrets would go unmasked. `Agent(` is built only at `factory.py:635`, and the CLI goes through the factory. A test asserts that every factory-built Agent has a resolver.
  - The resolver gets the encryptor through `get_encryptor()` at each read (`encryption.py:265-308`, the cached singleton that `install_key` updates) and never copies a key at build. Otherwise a long-lived WebSocket Agent would fail closed after a rotation.
  - **When it reads:** the resolver reads the current secrets and the agent's current `secret_ids` from the database **at each call**, decrypting through the app `Encryptor`. A Library change or a grant change therefore applies to the next tool call with no restart and no stale cached Agent (criterion 4). A small cache keyed by a write generation is an acceptable optimisation if it keeps that property.
  - **Which agent it resolves for:** the session comes from `current_turn.get().session_id or current_chat_session_id.get()`, as the notes tools do (`notes/tools.py:122`). Every entry point sets `current_turn.session_id`: the WebSocket and REST paths (`app.py:2597`, `:2943`), connectors (`inbound.py:439`) and routines, through `_process_and_broadcast`. REST never sets `current_chat_session_id` (`app.py:3392`; Architect review 2).
    - With a session, the agent is that session's current `chat_sessions.agent_name`, which follows an agent rename.
    - Without one, it is the name the Agent was built with.
    - An agent with no stored row (the bare `default`) has no grants.
  - **Shared connection:** the resolver reads through the process-wide aiosqlite connection (`db/connection.py:45-57`), so it can see another coroutine's uncommitted secret write or rotation. Fail-closed covers that (a spurious refusal or "unavailable", never a leak). The agents.md entry says so.
- In `_execute_tool` (`agent/core.py:608`), after `bind_positional_args`:
  1. Collect `{{secret:KEY}}` tokens from every string leaf of the arguments (nested dicts and lists; dict keys are not scanned).
  2. For each token, refuse the whole call (no execution) with `is_error=True`. The messages name only the requested key and the tool, never other keys:
     - the key is unknown or not in a granted secret: "Secret `KEY` is not granted to this agent.";
     - the call's tool name (exact, as `ToolRegistry.get` matches, `tools/base.py:205-208`) is not in that secret's `allowed_tools`, or is in DD3's refused set: "Secret `KEY` can't be used with the tool `NAME`."
  3. Build a **new** argument structure with values substituted (`bind_positional_args` is only a shallow copy, `tools/base.py:151-164`); `tool_call.arguments` is never mutated, so the stored assistant message, the `tool_call` WebSocket events (`app.py:2714-2735`) and the provider request keep the placeholder. A test pins that `tool_call.arguments` is unchanged after execution.
- Masking: every stored secret value, granted or not (operator decision), in the normal output **before** `self._govern` (truncation could split a value), in the timeout string and in the `[error] Tool execution failed: …` string. It handles `str` and nested `dict`/`list` content (`db/codec.py:36-40`). Needles per value, longest first, each replaced by `[secret:KEY]`:
  - the raw value;
  - its Python `repr` body, `repr(v)[1:-1]` (tools format inputs with `!r` throughout, e.g. `connector_send.py`, and `repr` escapes quotes and backslashes differently from JSON; Architect review 1);
  - its JSON-escaped forms with `ensure_ascii` both true and false;
  - its URL-encoded forms (`quote`, `quote_plus`). Technique after `evals/env.py:120-150` `Redactor`, reimplemented. No minimum length: a short value such as a postcode may mask unrelated text, accepted by the operator (SECURITY-MODEL.md notes it).
- Fail closed: if the resolver raises while the arguments hold a token, the call is refused ("Secrets are unavailable right now."); if masking raises, the result is replaced by an error string rather than returned unmasked. Fast path: no tokens and no stored secrets means no work.
- Because the masked `ToolResult` is what `_dispatch_tool_calls` appends (`core.py:511-513`), masking here covers the model, the database (`_save_session_to_db`, `connectors/inbound.py:460`) and the `tool_result` events. Routines, connectors and the CLI share the loop (recon: no bypass; the only other `tool.execute` call is the operator test route `POST /api/tools/{name}/test`, which has no agent and no secrets).
- No log line may carry resolved arguments. The leg greps the tool-execution path and the tools that log their inputs. It checks the `httpx2`, `httpcore2` and `mcp` loggers the MCP client uses: `logging_config.py:23` quiets only `httpx`/`httpcore`, so the leg quiets these too if they log request bodies. A test runs a built-in call and an MCP tool call under `caplog` at DEBUG and asserts the value is absent.

**DD8: The agent learns its keys from a prompt layer, shown on Settings › Prompts.**
- New renderer `the_one/db/_secrets.py::render_secrets_block(entries)` beside `_rules.py`/`_notes.py`: a short heading and instruction (write `{{secret:key}}` in a tool argument; the value is filled in when the tool runs; you never see it; it works only in the listed tools), then one line per granted key: the placeholder, the secret's name and description, and its allowed tools. Empty when nothing is granted (no prompt cost for agents without grants).
- `compose_system_prompt` (`agent/config.py:38`) gains a `secrets` layer after notes and before the date line.
  - `build_system_prompts` (`agent/prompt_layers.py:73-133`) loads it by agent name, like rules, into the `tool_capable` prompt only. The `tool_free` prompt gets no secrets layer: a model without tools can't use them.
  - `self_configuration/pending.py:136-153`, the second caller, passes it through, and so does its fallback.
- **The layer is fixed when the Agent is built.** A new grant, a renamed key or a revoked grant reaches the prompt when the Agent is next rebuilt: a new chat, a rejoin, or the next REST call, because a session restore rebuilds the Agent and replaces `messages[0]` (Architect review 2). A live WebSocket chat keeps its prompt until then. Substitution changes on the next call (DD7), so a revoked key is refused at once even while the open chat's prompt still lists it. This follows the notes "Pending · used from the next chat" precedent; agents.md says so.
- `/api/info` gains `secrets_prompt_example` (rendered by the real renderer from fixed sample entries, beside `rules_prompt_example`, `app.py:3110`); Settings › Prompts shows it as its own section in assembly order, like the rules and notes examples.
- This is platform prompt text (CLAUDE.md, "Prompt evals"), and the leg adds `the_one/db/_secrets.py` to CLAUDE.md's list of platform prompt text files.
- **Eval scope** (Architect review 1; Flight Director call, option b): eval scenarios can't set `secret_ids`, so the comparison against `m30-platform` is a **no-leak regression check only**. It proves that agents with no grants see an unchanged platform prompt and an unchanged token cost. Its expected delta is zero, and a non-zero delta is a divert (Adaptation Criteria).
  - The leg runs `make eval ARGS="measure-prompt"` (no model calls, no plan quota) and records the platform size. It runs a full `compare` only if `measure-prompt` shows any change for an agent without grants.
  - The layer's wording is validated with a real model in the HAT.
  - A secrets eval scenario set (with its own baseline) is out of scope; it is a follow-up if the HAT shows models misuse the placeholder. A prerequisite for that follow-up: `evals/tokens.py::_layers` (`:183-209`) knows only the rules, notes and date layers, so a secrets layer would push the date line into "unattributed".
- Self-configuration's `get_my_configuration` is **not** extended (Flight Director call: the prompt layer already tells the agent its keys, and the projection's exact-key test stays untouched). Agents cannot grant themselves secrets: no agent-facing route writes `secret_ids` (pin with a test on the self-configuration write tools' field set).

**DD9: Acceptance apparatus (behavior test `secrets-round-trip`).**
- A scratch dev instance (non-default port, scratch data dir and cwd under `$HOME`, PID taken from `ss -ltnp`), shell-only Executor with the bearer credential.
- **Act:** create a secret and agents over REST; `POST /api/chat` (`app.py:3349`) to agents on `mock` providers whose `config.response.tool_calls` call `write_file` with `{{secret:key}}` in `content` (allowed), `read_file` on that file (masking), and a not-allowed or not-granted call (refusal), each with `max_iterations` 1: exactly one model call and one tool dispatch per turn (`core.py:290-291`).
- **Observe:**
  - the written file's contents on disk (the tool received the real value);
  - `GET /api/chat/sessions/{id}` (`api.py:5752`) for the stored assistant tool-call arguments (placeholder) and tool results (masked);
  - the `/api/chat` response body;
  - `GET /api/secrets` (sentinel only);
  - the server log and the SQLite file (no plaintext value, `grep -c`).
- **Provider-request proxy:** the mock provider does not record what it was sent. The request is built from `agent.messages`, which is exactly what `_save_session_to_db` encodes, so the stored history stands in for the provider request; the unit test in leg 2 asserts the `FakeLLM`'s recorded calls carry only placeholders.
- A Library value change followed by a call proves criterion 4 end to end: the live store, the PUT and the next call. A rotation step (`POST /api/encryption/rotate`) followed by another `write_file` call proves the value survives rotation. Both follow-up calls continue the writer's session (`session_id`).
- **What this does not prove** (Architect review 2, high; corrected): REST `POST /api/chat` with a `session_id` **rebuilds** the Agent through `factory.create` on every call (`_restore_session`, `app.py:1956-1966`). So these steps cannot show that an Agent built *before* the change picks it up. That property, which a wrongly snapshotting resolver would break, is proven by:
  - leg 2's unit test ("a Library change applies on the next call in the same Agent", plus a rotation variant);
  - the HAT's open-tab step (a live WebSocket chat, which keeps one Agent).
  
  Flight Director call: option (a), correct the claim, rather than a WebSocket client in the spec.

### Citation Audit
Spot-checked by the Flight Director on 2026-11-04 (others are from the code-mapping recon and are for the Architect to sample).

| Citation | Claim | Status |
|---|---|---|
| `agent/core.py:608-672` `_execute_tool` | `bind_positional_args`, `tool.execute`, then `_govern`; timeout and generic error strings | verified |
| `agent/config.py:110` | `kb_ids: list[str] = Field(default_factory=list)` | verified |
| `agent/config.py:38` `compose_system_prompt` | layers base, persona, rules, notes, date line (keyword-only) | verified |
| `interfaces/web/api.py:1526-1533` | `kb_ids` preserved when omitted, `[]` clears | verified |
| `db/schema.py:18` | `CURRENT_VERSION = 50` | verified |
| `db/encryption_corpora.py:38-49` | seven `Corpora` fields | verified |
| `db/key_reconcile.py:20-29` | `_ENCRYPTED_CORPORA`, eight (table, column) pairs | verified |
| `tests/test_encrypted_corpora_guard.py:31` | `_LOOKUP_COLUMNS = {"id","name","identifier"}` | verified |
| `evals/env.py:122` `Redactor` | raw and JSON-escaped needles | verified |
| `self_configuration/projection.py:28` | `build_get_my_configuration` | verified |
| `interfaces/web/app.py:3110`, `:3349` | `rules_prompt_example` in `/api/info`; `POST /api/chat` | verified |
| `interfaces/web/api.py:5752`, `:921-926` | `GET /chat/sessions/{id}`; `GET /tools` from `BuiltinToolProvider` | verified |
| `agent-editor.js:91-125` | Tools tab: MCP section then Built-in section | verified |
| `knowledge-tab.js` rows; `provider-editor.js:100-250` | row and editor shapes the mockup used | verified |
| `tools/base.py:151-164` | `bind_positional_args` shallow copy | recon |
| `app.py:2714-2735`, `:2785-2803` | `tool_call` / `tool_result` WebSocket events | recon |
| `agent/core.py:329-330`, `:511-513` | assistant message appended before execution; tool result appended after | recon |
| `api.py:~6979`, `:7116-7150` | rotation re-encrypt and write loops | recon |
| `agent/prompt_layers.py:73-133`, `self_configuration/pending.py:136-153` | the two prompt composition callers | recon |
| `mcp/_tool.py:54-61` | prefixed MCP tool names | recon |
| `agent-form-data.js:187-201` | `kb_ids` sent only when loaded | recon |

### Prerequisites
- [x] No active mission or open sortie overlaps (sortie 09 completed).
- [x] Eval prerequisites present: plan token at `~/.config/the-one-evals/plan-token`; Ollama answering with `gpt-oss:20b` (checked 2026-11-04). **Re-verify at the start of leg 2** (external session).
- [x] `mock` provider supports scripted `tool_calls` (CLAUDE.md, `llm/mock.py`); step-limit precedent in `tests/behavior/agent-step-limit-notice.md`.
- [x] Ports: the mockup instance uses 8492; legs and the behavior test use 8486 or 8490+, never 8484/8485.
- [x] HAT (external sessions, **re-verify at the start of leg 4**): Goldfinch running and reachable as an MCP source on the scratch instance; the operator's own model provider available; the Goldfinch vault holding a test entry the operator is willing to use.

### Pre-Flight Checklist
- [x] Open questions resolved
- [x] Design decisions documented
- [x] Citation Audit (sampled; Architect to spot-check the recon rows)
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined
- [x] Operator-approved rendered mockup recorded (DD1, DD2)

---

## In-Flight

### Technical Approach
1. **Leg 1, `secrets-store`** (risk tier: high: a schema migration, an encrypted corpus, a new write path).
   - Files: `db/schema.py`, `db/repositories.py`, `db/encryption_corpora.py`, `db/key_reconcile.py`, `agent/config.py`, `interfaces/web/api.py` (or a new `interfaces/web/secrets_api.py` router included by `api.py`; preferred, given `api.py`'s size and sortie 09's extraction recommendation), `tests/`.
   - Work:
     - DD4: v51, the repository, `secret_ids`.
     - DD5: routes, masks, the write shape, 422/409, the delete scrub, manual validation.
     - DD6: the corpus.
     - DD2 server half: `secret_ids` kept when omitted, the unknown-id 422 on POST and PUT.
     - DD3 server half: the `allowed_tools` rule and the refused set, the MCP-rename carry in `mcp/rename_references.py`, and `GET /api/tool-names`.
   - Tests:
     - schema pins and the template; repository round trips;
     - every 422 `loc`, including `["values", i, "key"]` for a key taken by another secret (ignoring case) and `["allowed_tools", i]` for a refused tool;
     - 409 on a duplicate name;
     - the `__MASKED__` keep and refuse rules; swapping two keys in one PUT;
     - no response ever carries a stored value: a test greps every route's body for the plaintext, including a malformed-body 422;
     - delete scrubs grants in one transaction;
     - rotation re-encrypts and the value still decrypts; the corpora guard;
     - `secret_ids` omitted keeps, `[]` clears;
     - an MCP rename moves `allowed_tools`, through both callers (the MCP PUT and the startup name repair);
     - the self-configuration loopback credential is refused on `/api/secrets` and `/api/tool-names` (`middleware.py:391` path scoping), so agents can't grant themselves secrets at the HTTP layer either;
     - the tool-names union, with sanitised MCP names and the blob-parsed per-agent cache.
   - Gate: `make test-unit`.
   - Docs: `the_one/agents.md` "Secrets (sortie 10)" (storage, routes, corpus), `SECURITY-MODEL.md` (storage part).
2. **Leg 2, `secrets-at-runtime`** (risk tier: high: the agent loop and the platform prompt).
   - Files: new `the_one/secrets/runtime.py`, `agent/core.py`, `agent/factory.py`, new `db/_secrets.py`, `agent/config.py` (`compose_system_prompt`), `agent/prompt_layers.py`, `self_configuration/pending.py`, `interfaces/web/app.py` (`/api/info`).
   - Work: DD7 and DD8 server half.
   - Tests (with `FakeLLM`/`StubTool`, falsification for each layer):
     - substitution into nested arguments, with `tool_call.arguments` unchanged;
     - `FakeLLM`'s recorded calls hold only placeholders;
     - each refusal message, with the tool not executed;
     - masking of str, dict and list results; of the `repr`, JSON-escaped (ASCII and non-ASCII) and URL-encoded forms, including a value holding both quote types and a backslash; of a value at a truncation boundary; of the timeout and exception strings; and of an ungranted value;
     - a refused-set tool is refused even when a stored row lists it;
     - the placeholder lookup ignores case;
     - fail-closed resolver and masker;
     - a Library change, and separately a key rotation (`install_key`), applies on the next call in the **same** Agent object;
     - every factory-built Agent has a resolver; an agent with no grants gets a refusal, never a literal placeholder in the tool;
     - after an agent rename, an open session's Agent still resolves through the session's current agent name, on the WebSocket path (`current_chat_session_id`) and the REST path (`current_turn` only);
     - the secrets layer goes into `tool_capable` only, in `build_system_prompts` and in the `pending.py` fallback;
     - `caplog` at DEBUG shows no value, for a built-in and an MCP tool call;
     - a routine run and a connector turn reach the same path (one test each through their entry points);
     - the prompt layer is empty without grants and lists keys with grants; `/api/info` carries the example.
   - Eval (DD8, option b): `make eval ARGS="measure-prompt"`, plus a full `compare` only if the platform size changed for an agent without grants (re-verify the plan token and Ollama first). Record the result in the flight log.
   - Gate: `make test-unit`.
   - Then the Flight Director runs behavior test `secrets-round-trip`, **run 1**, on the leg's build (REST-only, no UI needed), so wiring defects surface before leg 3 (Architect review 1 suggestion).
   - Docs:
     - `the_one/agents.md`: runtime, prompt layer, resolver key, shared-connection note.
     - `SECURITY-MODEL.md` "Secrets". The threat model: values never reach the model. Residual risks:
       - an allowed tool can still send a value where the operator did not intend (e.g. `typeText` into an injected page);
       - granting `write_file` or `shell` hands the value to anything that can read the file, including base64 exfiltration and a knowledge-base folder that indexes the plaintext;
       - encodings other than raw, `repr`, JSON and URL (base64, split values) are not masked;
       - short values over-mask;
       - `[secret:KEY]` masks reveal key names to agents that were never granted them.
     - `CLAUDE.md`: a "Secrets (sortie 10)" paragraph, and `the_one/db/_secrets.py` added to the platform prompt text list.
3. **Leg 3, `secrets-ui`** (risk tier: high: a shared control-library factory changes; Accessibility Reviewer on the factory change).
   - Files: `static/js/store.js`, `areas/studio/library-pane.js`, `router.js`, `areas/studio/studio-route.js`, `areas/studio.js`, new `areas/studio/secret-editor.js` and `secret-glue.js` (the connector pair as the model), `agent-editor.js`, new `areas/studio/secrets-section.js` (Tools-tab section), `agent-form-data.js`, `agents-list.js`, `areas/chat/agent-drawer.js`, `areas/admin/system-page.js` (Prompts), `js/ui/chip-list.js` (`suggest`), `index.html`, `docs/ui-control-inventory.md`, `docs/ui-testid-registry.md`, `scripts/run-tests.sh` (lane lists).
   - Work: DD1, DD2 client half, DD3 client half, the drawer group and the Prompts section; the 422 mapping of `["values", i, "key"|"value"]` onto the table row (`table.setError`) and of `["allowed_tools"]` onto the field; leave guard (`App.nav`) for the secret editor's dirty state, remembering that `discard` runs on a still-mounted editor (sortie 09 lesson).
   - Browser tests:
     - Library (lane `library`, a new `test_flow_studio_secrets_*.py` file added to `library_pat`): create with the name-generated first key, add and remove pairs, edit with masks kept, rename a key (the value clears), each 422 on its row or field, 409 on the name, delete with the used-by warning, and no plaintext in any DOM attribute;
     - Tools tab and drawer (lane `agent-tabs`, added to `agent_tabs_pat`): grant and ungrant through Save, the exact PUT body (`secret_ids` only when loaded), the empty state, the drawer group;
     - Settings › Prompts example (lane `settings`);
     - `chipList` `suggest` contract tests (Chromium + WebKit, lane `contracts-controls`).
   - Also: Jump to lists secrets; the `#library/secrets` alias; the `routing` lane's router tests updated if they pin the section list.
   - Size: this leg has over 15 acceptance criteria, so by the project rule it is designed as **part A** (`chipList` `suggest` with its contract tests and accessibility review, plus the Library editor) and **part B** (Tools-tab section, drawer, Prompts page, Jump to), with a checkpoint commit between them.
   - Gate: the full `--parallel 3` browser gate on a quiet host plus `make test-unit` (the leg touches the shared agent write path and a shared factory).
4. **Leg 4, `hat`** (operator opted in): a guided session over the Library editor, the Tools-tab grants, the drawer and the Prompts page, and a real chat (the operator's own provider) that uses a secret through Goldfinch (`vaultUnlock`, `typeText`), on a scratch instance. It includes at least one state the operator is not watching: an open chat in another tab whose next tool call picks up a changed value (criterion 4).

### Checkpoints
- [x] Leg 1: storage, routes, corpus and grants green; `make test-unit`
- [x] Leg 2: substitution, masking, prompt layer green; eval no-leak check recorded; `make test-unit`; behavior test run 1
- [x] Leg 3: UI green (parts A and B); full `--parallel 3` gate green (G2 `rc=1` on 12 stale pins in `agents`, `providers` and `settings`; pins fixed and those three lanes re-run in full green)
- [x] HAT complete; behavior test re-run on the final build if the HAT changed behaviour (not needed: the one HAT fix was doc-only)

### Adaptation Criteria

**Divert if**:
- A tool-execution path outside `_execute_tool` turns up (substitution or masking would be bypassed): stop and redesign before continuing.
- `measure-prompt` shows any platform size change for an agent without grants (the layer leaked into agents with no secrets).
- A second, independent decision cluster appears (per-use approval, environment-variable injection, origin binding): escalate rather than widen.

**Acceptable variations**:
- Module, helper and route-module names; whether the routes live in `api.py` or a new router module.
- Exact wording of hints, refusal sentences and the prompt layer, as long as each refusal names only the key and tool, the layer adds nothing for an agent without grants (`measure-prompt`), and the operator accepts the wording in the HAT.
- A resolver cache, provided a Library or grant change applies to the very next tool call.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `secrets-store` - DD2 (server), DD3 (server), DD4, DD5, DD6: schema v51, repository, `/api/secrets`, `/api/tool-names`, the eighth corpus, agent grants, refused tools, MCP-rename carry
- [ ] `secrets-at-runtime` - DD7, DD8 (server): substitution, refusal and masking in `_execute_tool`; the prompt layer and `/api/info` example; eval no-leak check; behavior test run 1
- [ ] `secrets-ui` - DD1, DD2 (client), DD3 (client), DD8 (Prompts page): part A `chipList` `suggest` and the Library editor; part B Tools-tab section, drawer group, Prompts page, Jump to; browser and contract tests; full gate
- [ ] `hat` - (optional) guided acceptance with the operator

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Charter success criteria assessed
- [ ] Flight debrief written

### Verification
- Each leg's gate as above, with `THE_ONE_TEST_NETNS=1` for browser lanes; the full `--parallel 3` gate at the end of leg 3 on a quiet host (load below 1.0).
- The Flight Director runs `/mission-control:behavior-test secrets-round-trip` (`tests/behavior/secrets-round-trip.md`, DD9) against a branch-built scratch instance: dry-run the setup requests first, then the witnessed run. Run 1 follows leg 2. Re-run it on the final build if leg 3 or the HAT changed server behaviour.
- The HAT leg.
