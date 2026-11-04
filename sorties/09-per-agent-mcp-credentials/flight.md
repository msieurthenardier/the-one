# Sortie: Per-agent MCP credentials

**Status**: completed

## Charter

### Outcome
One MCP server in the Library can be shared by many agents, each connecting with its own header values (HTTP) or environment variables (stdio), such as its own API key, and each seeing the tools that key allows.

### Why Now
Today, giving agents different keys or permissions on the same server means registering a duplicate server per agent. The backend already stores and applies per-agent overrides (`mcp_overrides[<server>]` `headers` / `bearer_token` / `env`, encrypted, masked, preserved on PUT), but there's no way to set them in the app. The override fields were removed in Mission 07 Flight 8 (Anomaly A5), and the follow-up flight it recommended was never planned.

### Success Criteria
*(Assessed at close, 2026-11-04: all four met; criterion 1 with operator-approved changes: write-only narrowed to sensitive values, and "Set per agent" replaced by the `value` placeholder and an override hint. See flight-debrief.md, "Charter Criteria Assessment".)*
- [x] In an agent's Tools tab, each MCP server tile lets the operator give this agent its own value for any header or environment variable the server defines, or add new ones. Values are write-only: they're never shown again, and saving the agent keeps them. A value left blank in the Library is labelled "Set per agent" and isn't sent unless an agent supplies one.
- [x] After Save, the agent's next chat turn uses its new values, with no restart and no waiting for the idle connection to close. Two agents on the same server reach it with different keys, proven against a test server that checks the key.
- [x] Each agent's tools, both the Tools tab list and what it can call in chat, come from a listing made with that agent's own credentials. Switching a server on for an agent tests the connection immediately with that agent's credentials and shows the result in the tile: its tools, or a plain reason it needs more configuration (such as a missing or rejected key). So a server with no key in the Library still lists tools for an agent that has one, and two agents with different permissions see different lists.
- [x] On a server that uses OAuth sign-in, a per-agent Authorization override is refused with a plain reason, while other headers can still be overridden.

### Constraints
- Per-agent values are secrets: encrypted at rest, hidden in every API response, kept when the agent is saved (existing rules), never shown to the agent through self-configuration or any other text the agent sees, and never logged.
- An agent with no overrides behaves exactly as today: shared tool cache and the same fast startup from the cache.
- Per-agent OAuth sign-in (Mission 07 Flight 8 Anomaly A4) is out of scope.
- Renaming a server or agent still carries its overrides along (existing behaviour).

Charter agreed with the operator 2026-11-03, including the immediate switch-on test (folded into criterion 3).

---

## Pre-Flight

### Objective
Let one Library MCP server serve many agents, each with its own header values (streamable-http) or environment variables (stdio). The backend already stores, masks, preserves and applies `mcp_overrides[<source>].headers` / `.env` / `.bearer_token`. This sortie adds what is missing around it:
- an editor for those values in the agent's Tools tab (mockup approved, DD10);
- validation on save;
- "Set per agent" blank values in the Library;
- a saved change that takes effect at the agent's next connection;
- a tool list made with the agent's own credentials;
- an immediate per-agent connection test when a server is switched on.

### Open Questions
- [x] Which transports? -> Both: `headers` for streamable-http, `env` for stdio (operator, charter).
- [x] What can an agent override? -> The server's own names plus new ones (operator, charter; DD1).
- [x] OAuth servers? -> Overrides allowed except Authorization (operator, charter; DD2, DD8).
- [x] Which tool list does an agent see? -> One listed with its own credentials (operator, charter; DD4-DD6).
- [x] Test on switch-on? -> Yes, immediately (operator, charter; DD6, DD10).
- [x] Tile layout? -> Credentials above tools (operator, 2026-11-03; DD10).
- [x] Open chats after a Save? -> New credentials at the next connection; tool-list changes at the next join or in a new chat (operator, 2026-11-03; DD7).
- [x] Leg shape? -> Three legs plus a HAT, kept as a sortie (operator, 2026-11-03, after Architect review 1; first chosen as two legs).
- [x] Acceptance? -> Behavior test plus an interactive HAT leg (operator, 2026-11-03).
- [x] How Studio sends unchanged names (Architect review 1, high)? -> The full name set, unchanged values as the mask sentinel (DD1, Flight Director call).
- [x] What does a key-less agent get from the test? -> `needs_values` naming the missing names, without connecting (DD3, DD6, Flight Director call).
- [x] Who writes the shared cache once the Tools tab no longer calls the Library Test? -> The per-agent route, for an agent with no override (DD6, Flight Director call).

### Design Decisions

**DD1: What an agent can override, and the write shape Studio sends.**
- Per attached source, the agent's override entry carries `headers` (streamable-http) or `env` (stdio): a dict of name to value. A name may be one the server defines or a new one. The server's names are the keys of `config.headers` / `config.env` and of `secrets` minus `OAUTH_MANAGED_SECRET_KEYS`, all visible in `GET /api/mcp-sources`.
- Values are write-only. `_agent_response` masks each inner value and keeps the names (`api.py:255-266`). A value of 12 characters or more is masked with its last 4 characters shown (`_emit_mask`, `api.py:~2986-3006`), the existing rule for every stored secret. The tile can therefore show which names are set without seeing a value.
- **Write shape (Architect review 1, high; Flight Director call).** `_merge_preserved_mcp_credentials` is per name only for masked values. A name left out of a present `headers`/`env` dict is **dropped** (pinned by `tests/test_db_api.py:407-449`), and a `null` inner value would be stored and then break every build (`StreamableHttpMCPOverride.model_validate` raises in `get_tools_for_agent`, which does not catch it). The merge stays as it is. Studio sends, for a source whose credentials it touched, the **full** set of this agent's names:
  - an unchanged stored name: the mask sentinel `__MASKED__` (the merge keeps the stored value);
  - a new or replaced value: the string;
  - a removed name ("Use server value"): left out;
  - all names removed: the whole `headers`/`env` key set to `null`, which clears it (the existing top-level rule).
  
  For a source whose credentials it did not touch, Studio sends no credential key at all, so the merge keeps everything (the existing "omitted" rule).
- **Tool filters (verified at `api.py:~427`).** When a source entry is present in the body, its non-credential keys come from the body (`resolved_entry = dict(incoming_entry)`). Rule for `agent-form-data.js`: a source entry's `enabled_tools`/`disabled_tools` come from its loaded tool rows when they are loaded, and are otherwise copied from the stored agent record (the masked GET keeps them verbatim). So a credential change on a tile whose tool rows did not load never clears the stored tool selection. A browser test pins this.
- **`bearer_token`** stays API-only. When it is stored, the Authorization row reads "Set for this agent". When the tile sets, replaces or removes Authorization, Studio also sends `bearer_token: null`, so the two never disagree (`bearer_token` is applied after `headers`, `_tool_provider.py:177-180`).
- **Header names overlay case-insensitively, across both Library layers.** `build_request_headers` merges `config.headers` and `secrets` (`streamable_http.py:182-186`), while `_apply_override` touches only `secrets`. The overlay therefore removes a Library header from **either** layer whose name matches the agent's ignoring case, so `x-api-key` and `X-Api-Key` are never both sent (Architect review 2). `missing_values` (DD3) matches names ignoring case too. Env names stay case-sensitive.
- **Known effect (low):** a stored name the client does not know (added by another write between the editor's load and its Save) is dropped by the Save, because the merge drops a left-out name. Accepted.
- Open-and-close stays clean: the collection adds no credential key unless the operator changed one (sortie 07's seed-copy defect, its flight log line 15).

**DD2: Validation on save (422), new or changed values only.**
- **Where:** `create_agent`/`update_agent` check the **raw** body's `mcp_overrides` credential values, before `_merge_preserved_mcp_credentials`, after `_normalize_surface_fields` (which only touches the self-configuration entry). The helper is new, suggested `mcp/override_validation.py::validate_mcp_overrides(incoming, sources_by_name)`. `create_agent` already holds `mcp_repo`; call `mcp_repo.list()` only when the body carries a credential value.
- **Which values:** an inner value equal to a mask (`_looks_masked`) is unchanged and not checked. Any other value is checked. A non-string value, including `null`, for an inner name is refused, which also closes the build-breaking `null` for API callers.
- **Shape:** each refusal is a detail `{"type": "mcp_override", "loc": ["mcp_overrides", <source name>, "headers"|"env", <name>], "msg": <one plain sentence>}`, all raised together as one 422 (the sortie 07 shape, `tools/override_validation.py:115-117`).
- **Rules:**
  - A header name must be an HTTP token (RFC 9110 `tchar`). The names the transport manages are refused: `Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Content-Type`, `Accept`, `Mcp-Session-Id`, `Mcp-Protocol-Version` (case-insensitive).
  - A header value, once trimmed, must be non-empty and contain only visible ASCII, space and tab (the RFC 9110 field-value grammar without obs-text). Other control characters would make h11 raise an error that embeds the value, and that error text reaches the agent through `_tool.py:180` (a DD9 leak). The same grammar applies to a `bearer_token` (it becomes the `Authorization` value, `_tool_provider.py:177-180`).
  - Two header names in one entry that differ only by case are refused.
  - An env name must match `[A-Za-z_][A-Za-z0-9_]*`. An env value, once trimmed, must be non-empty and contain no NUL.
  - `headers` on a stdio source, or `env` on a streamable-http source, is refused (the loc ends at the field).
  - **OAuth state means `secrets` holds any `OAUTH_MANAGED_SECRET_KEYS`** (the existing `oauth_active`, `api.py:~3163`). The cached `auth_posture` is **not** used: any 401 to the Phase 0 probe writes `oauth` (`api.py:~4218-4223`), and that is exactly what a "Set per agent" server returns (Architect review 1, high). On a source with OAuth state, a header named `Authorization` (case-insensitive) or a `bearer_token` is refused: "This server signs in with OAuth, so its Authorization header can't be set per agent."
  - An entry for a name that matches no source is left to the existing orphan warning (no 422).
- **Client:** the agent editor's save-error path maps an `mcp_override` loc to the tile and the row (select Tools, expand the tile, put the message on the row and focus it), following sortie 07's `onSaveError_` route. The mapping lives in the new credentials module (DD10); `agent-editor-controller.js` gains a delegate of at most 10 lines. Any other refusal goes to the header error.

**DD3: A blank value is "Set per agent", is never sent, and counts as evidence.**
- **Runtime:** `build_request_headers` (`transports/streamable_http.py:157-190`) and `build_stdio_environ` (`transports/stdio.py:368-394`) drop a name whose final value, after the agent overlay, is empty once trimmed.
- **Missing values.** One helper (suggested `mcp/_overrides.py::missing_values(library_source, effective_source) -> list[str]`) lists the names the Library configures (config and secrets, minus OAuth keys) whose effective value is blank.
- **Classification (Architect review 1, medium).** With blanks dropped, a 401 would otherwise look like a sign-in prompt, because `MCPClient._signin_signal` (`client.py:381-405`) uses a non-empty `build_request_headers` as evidence. Rule: a source that configures any header name, blank or not, counts as evidence. A bare 401 is then `MCPCredentialsRejected`, never a sign-in prompt, and when values are missing its message names them ("needs a value for X-Api-Key"; names only). This keeps sortie 04's evidence rule: configured credentials, not a sign-in, are what the server rejected.
- **Library Test** of a source with missing values (Architect review 2: the Library's only sign-in path is Test's Phase B, so it must stay reachable for an OAuth server that also has a "Set per agent" header):
  - with live sign-in tokens, Phase A runs as today, with the blanks dropped;
  - without tokens, the Phase 0 probe is skipped and the no-auth path runs in cache mode `shared_no_posture` (DD6). If it raises `MCPAuthRequired` (a 401 carrying `resource_metadata`, sortie 04's rule, `client.py:381-405`), the test continues into Phase B through the existing `from_fallthrough` / `_SIGNIN_REQUIRED` mechanism (`api.py:~3712`, `~3842-3846`), so the operator can sign in;
  - only a **bare** 401 becomes `MCPCredentialsRejected`, naming the missing values; no doomed client registration runs;
  - a success (a server that does not need the value) writes the shared cache fields, without `auth_posture`;
  - a Test sent with no body still records `last_check` (the route's existing `recordable` rule). Only the DD6 route never writes it.
- **stdio:** `build_stdio_environ` layers the host allowlist first (`stdio.py:~394`), so a blank Library env value that is dropped lets the host's allowlisted value for that name through, where today the blank overrides it. Intended: a blank means "not set here".
- **Library editor** (`mcp-env-headers.js`): an empty value input shows the placeholder "Set per agent", and the headers and environment tables each get one hint line: "A blank value isn't sent. Agents can set their own in their Tools tab." Saving a blank value is already allowed (it sends `''`).
- **Known effect (release notes):** an existing source that saved a blank value stops sending it as an empty header or variable.

**DD4: Which agents get a per-agent tool list.**
- An agent **uses its own credentials** on a source when its stored override entry for that source, read through `override_for` (`self_configuration/constants.py:131-140`, so the self-configuration row never counts), has a non-empty `headers`, `env` or `bearer_token` that `_apply_override` would actually send. A per-agent `Authorization` or `bearer_token` on a source with OAuth state is skipped (DD8), so it does not count. One helper decides this everywhere (suggested `mcp/_overrides.py::has_credential_override(entry, source) -> bool`).
- Such an agent's tool list comes from its per-agent cache (DD5), never from the shared `_cache`. Every other agent uses the shared `_cache` exactly as today, so the charter's "no overrides, no change" holds by construction.
- Three build-time readers switch on the helper: `_tool_provider.py` Path B (~285); `factory._build_source_index` (~144-146, the `search_tools` index); `self_configuration/projection.py` (~139, `describe_my_capabilities`). The Tools tab's count chip reads through `cachedTools`, which DD10 switches.
- **Known effects:** the chat drawer's "What it can use" count (`agent-drawer.js:~560`, `App.usage.mcpToolCount`) keeps the shared count for a credentialed agent (accepted; low). A credentialed agent whose cache is cold and whose server is unreachable now waits for the SDK connect timeout at build, which an agent with no override never does.

**DD5: The per-agent tool cache is a new table.** Schema v50 adds `agent_mcp_tool_cache`.
- **Columns:**
  - `agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`;
  - `source_id TEXT NOT NULL REFERENCES mcp_sources(id) ON DELETE CASCADE`;
  - `tools TEXT NOT NULL`: a JSON list of `{name, description, input_schema}`, the shape of `_cache.tools`;
  - `fetched_at TEXT NOT NULL`;
  - primary key `(agent_name, source_id)`.
  
  The pattern is v43 `agent_notes` (`db/schema.py:~3030-3074`); `REFERENCES mcp_sources(id) ON DELETE CASCADE` has precedent (`schema.py:~2469`). Foreign keys are on for app connections (`db/connection.py:55`) and the test template. Agent save is an upsert and rename is `UPDATE agents SET name` (including `name_repair`), so the cascades fire and nothing deletes and reinserts rows.
- **Not encrypted:** it holds tool names and schemas only, like the shared `_cache`, and joins no rotation corpus.
- **Repository:** suggested `AgentMcpToolCacheRepository` in `db/repositories.py`: `get`, `put`, `delete(agent, source)`, `delete_for_source(source)`.
- **Written by:** the DD6 route (under its rules), and the build path when a credentialed agent's cache is cold and it lists live (Path A, `_tool_provider.py:~313-318`).
- **Race guard (one statement, Architect review 2):** a writer reads the agent's `updated_at` when its listing starts, and `put` is a single statement, `INSERT OR REPLACE INTO agent_mcp_tool_cache (...) SELECT ... WHERE (SELECT updated_at FROM agents WHERE name = ?) = ?`. All coroutines share one aiosqlite connection (`db/connection.py:45-57`), so a separate re-read and write could interleave with a Save. The agent upsert (`repositories.py:~266-281`) and rename (`~449`) always set `updated_at`, so any save in between cancels the write (safe), and a renamed or deleted agent matches no row. A unit test interleaves a Save between a listing and its write and checks that no row is written.
- **Deleted by:** an agent save that changes that source's credentials (DD7); a Library `update_mcp_source` that changes `type`, `config` (minus `_cache`) or `secrets`; Reset connection (`reset_mcp_connection`).
- **Exposed to Studio:** `GET /api/agents/{name}` (single-agent routes only, like `kb_tool_names`) gains an additive `mcp_tool_cache: {<source_id>: {tools, fetched_at}}` for the sources where DD4 holds.

**DD6: The per-agent connection test.**
- **Route:** `POST /api/mcp-sources/{source_id}/test/agent` (no collision: the existing routes are `/test/connect` and `/connection`), body `{"agent": <name> | null, "overrides": <one mcp_overrides entry in the DD1 write shape> | null}`.
  - `agent` is null in create mode (`#agents/~new`). A named agent that does not exist is a 404, the same as an unknown `source_id`.
  - A self-configuration row's id (`is_surface_row`) is refused with 422.
  - The logic lives in a new module (suggested `the_one/mcp/agent_test.py`); the route in `api.py` (about 6,900 lines) stays thin.
- **Cache-write modes (defined once, in leg 1).** The stdio and no-auth helpers take `cache_write: "none" | "shared" | "shared_no_posture"` and `record_era: bool` in place of their single `merge_cache` call (Architect review 2: `_build_and_test_no_auth_mcp` writes `auth_posture: "no_auth"` in the same call as `tools`, `api.py:~3822-3834`).
  - The Library Test passes `shared` (today's behaviour), or `shared_no_posture` on its DD3 missing-values path.
  - This route passes `none` and does its own persisting (below).
- **Steps:**
  1. Resolve the effective source the way a build does: the stored source, then the stored agent override read through `override_for` (if the agent exists), merged with the body by `_merge_preserved_mcp_credentials`, then the DD2 checks (a refusal is a 422 in the DD2 shape), then `_apply_override`.
  2. If `missing_values` (DD3) is non-empty, return `{"status": "needs_values", "missing": [<names>]}` without connecting.
  3. A source with live sign-in tokens: connect through Phase A, **extracted** from `_test_mcp_connection_inner` (inline at `api.py:~4230-4333`) into a helper that both routes call. For this route the helper never clears tokens, never calls `_evict_all_for_source` and never falls through to Phase B. `MCPAuthRequired` becomes `{"status": "auth_required"}` with no `consent_url`.
  4. stdio: `_build_and_test_stdio_mcp`; any other streamable-http: `_build_and_test_no_auth_mcp`, both with `cache_write="none"` and `record_era=False`. The no-auth helper reports `MCPAuthRequired` (as `auth_required`) and `MCPCredentialsRejected` (as `error`) separately instead of folding them. The evidence rule is `_signin_signal`'s, applied to the effective source (DD3).
- **Never** runs the Phase 0 probe or Phase B, and **never** writes `auth_posture`, `last_check` or the era record (`record_era=False`). Bare probes stay inside the existing task-group containment (M07 F08 A6).
- **What it persists:** only when the status is `ok` and the credentials it tested are the stored ones. That means the merged `headers`, `env` and `bearer_token` equal the stored agent's, so an unsaved removal (a left-out name, or `headers: null`) also counts as unsaved (Architect review 2).
  - The agent exists and DD4 holds for its stored override: the per-agent cache (DD5, single-statement race guard).
  - The agent has no credential override (or is null): the shared `_cache` fields (`tools`, `capabilities`, `server_info`, `instructions`, `meta`, `protocol_version`, `last_updated`) through the leg 1 writer in `shared_no_posture` mode, never `auth_posture` or `last_check`. These are the fields the Tools tab's first-expand probe writes today. This keeps the shared cache, and with it the charter's fast startup, filled for agents with no override now that the Tools tab no longer calls `/test/connect` (Architect review 1, medium). A blank Library value always returns `needs_values` first, so this list is always made with the Library's own values.
  - Otherwise: nothing.
- **Responses** keep the Library Test's shapes (`ok` with `tools`; `auth_required`; `error` with the class-prefixed message) plus `needs_values`. None echoes a credential value.
- The Library `/test/connect` behaviour is unchanged apart from the Phase A extraction and DD3's missing-values path.

**DD7: When a saved change takes effect.**
- **Resolve at connect (mechanism settled by Architect review 1).** `acquire` gains `resolve_source: Callable[[], Awaitable[MCPSource]] | None`. It is passed into `_entry_worker` and awaited **on the worker task, inside its `try`, before `MCPClient` is constructed**, so it never runs under `_lock`, never on a warm entry, and does not change the anyio connect/disconnect lifecycle (connect and disconnect stay on one task; the divert condition is not met).
  - The pre-`try` block in `_entry_worker` (`_pool.py:~207-224`, the OAuth provider construction with DB reads) moves inside the `try` too, so a failure there cannot orphan `client_ready` and hang waiters. Order inside the `try`: the resolver first, then the posture check and the OAuth provider built from the **resolved** source, then `MCPClient`.
  - The resolver lives in `_tool_provider.py` (lazy imports, as `factory.py` does): it loads the stored agent and the stored source and applies `override_for` + `_apply_override`. It returns the build-time `source_override` when the agent is not in the store (the CLI, a test stub). Any other failure (for example a deleted source) is raised as `MCPConnectionError`, which `_tool.py:173-179` already turns into a plain tool error.
  - `_tool.py:174` passes it; build Path A (`_tool_provider.py:313`) keeps passing its fresh effective source.
  - Side effect: a Library edit now also reaches an open chat at its next connection.
- **Eviction, synchronous, after the commit.** Leg 1 adds the pool evictions; leg 2 adds the DD5 cache-row deletes at the same hooks (agent save, `update_mcp_source`, Reset), since the table arrives in leg 2.
  - `create_agent`/`update_agent`: for each source whose final credential values (`headers`, `env`, `bearer_token`) differ from the stored ones (names mapped to ids with `mcp_repo.list()`), `_pool._evict((name, source_id))`, and (leg 2) delete that agent's cache row.
  - `rename_agent` and `delete_agent`: a new `_evict_all_for_agent(name)` evicts every `(name, *)` key; cache rows follow by cascade.
  - `update_mcp_source`: `_evict_all_for_source` when `type`, `config` (minus `_cache`) or `secrets` change (today it evicts nothing, `api.py:3386-3528`).
  - Reset connection already evicts.
  - `_evict` is safe from a request handler (same loop, pops under `_lock`); it can hold the response up to `_WORKER_TEARDOWN_TIMEOUT_SECONDS` (10 s) per key.
- **Open chats** (operator, 2026-11-03): the next tool call uses the new credentials. The open chat's tool list stays as built; it follows a change at the next join, and a new chat has it immediately.
- **Known effects:**
  - a tool call in flight on an evicted connection may fail with a connection error, as with Reset connection today;
  - after an agent **rename**, an open chat's tools still carry the old name: the resolver finds no such agent and falls back to the build-time copy, and that pool key under the old name escapes later evictions until the chat is opened again or the idle reaper takes it. Documented, not fixed.

**DD8: OAuth servers keep the sign-in's Authorization.**
- "OAuth state" is `oauth_active` only (DD2).
- `_apply_override` skips a per-agent `Authorization` header (case-insensitive) and `bearer_token` for a source with OAuth state, so a value stored before the source gained a sign-in is ignored, not sent.
- The tile renders an OAuth server's Authorization row as read-only: "Supplied by the server's sign-in." Other headers stay editable.
- Per-agent sign-in (M07 F08 A4) stays out of scope.

**DD9: Per-agent values stay secret.**
- They live only inside the encrypted `agents.mcp_overrides` column. No new secret column is added, so encryption rotation is unchanged.
- Every agent response masks them (existing; a long value shows its last 4 characters, the rule for every stored secret). The DD6 route echoes none.
- DD2's value grammar keeps transport errors that embed a header value from reaching the agent or a response.
- No log line carries a value. Header and env **names** may be logged.
- `describe_my_capabilities`, `get_my_configuration` and all other text the agent sees never include `mcp_overrides` (`projection.py:40`, unchanged).
- The DD5 table holds tool metadata only.
- `SECURITY-MODEL.md` gains a short "Per-agent MCP credentials" paragraph covering these points and noting that an agent's tool list now depends on its own credentials.

**DD10: The tile layout (operator-approved mockup, 2026-11-03: "Credentials above tools").** An expanded MCP server tile in the agent's Tools tab shows, in order:
1. the section "Headers for this agent" (streamable-http) or "Environment for this agent" (stdio);
2. a connection status line with Test and Refresh;
3. the existing tool list.

```
[on] GitHub MCP            HTTP  12 of 14 tools  [v]
     api.github.com/mcp
 --------------------------------------------------
 HEADERS FOR THIS AGENT
  Authorization  Server value          [Set for this agent]
  X-Org          Set for this agent    [Replace] [Use server value]
  X-Api-Key      Set per agent · missing  [Set for this agent]
  [+ Add header]

 (ok) Connected with this agent's values · 14 tools
                                  [Test] [Refresh]
 TOOLS
  [x] create_issue   Create an issue
  [x] list_repos     List repositories
  ...

While editing one row:
  X-Api-Key  [ •••••••••••• ]  [Cancel]

Library editor, blank value:
  X-Api-Key  [ Set per agent        ]  (o) Sensitive
```

- **Row states:**
  - **Server value**: the server sets it. Action: Set for this agent.
  - **Set per agent · missing**: the server's value is blank and this agent has none, shown in a warning tone. Action: Set for this agent.
  - **Set for this agent**: a value is stored for this agent (including an API-stored `bearer_token` on the Authorization row). Actions: Replace and Use server value.
  - **Supplied by the server's sign-in**: Authorization on an OAuth server. No action.
  
  A name added with Add header shows as Set for this agent once a value is typed; Cancel on an unsaved new row removes it.
- **Editing:** Set for this agent and Replace open a password input on that row, with Cancel. A typed value marks the form dirty. Use server value marks the name for removal and shows "Server value · on save"; undoing that returns the form to clean.
- **Status line:**
  - "Testing…" while a test runs;
  - "Connected with this agent's values · N tools", or "Connected · N tools" when the agent has no override;
  - "Needs a value for X-Api-Key" (from `needs_values`, or computed in the tile before any test);
  - for an error, the `App.mcpErrorMessage` headline, with the raw text under "Technical details";
  - for `auth_required`, the existing sign-in note;
  - for a credentialed agent with no per-agent list yet: "Not listed with this agent's values yet" with Test.
- **Which list the tile shows:** for a credentialed agent (DD4), only its per-agent cache (`mcp_tool_cache`) or a test result, never the shared `_cache` (Architect review 1, medium). For any other agent, the shared `_cache` as today.
- **When it tests:**
  - **Switch-on** (operator, charter): turning a tile's switch on expands it and runs the DD6 test at once with the tile's current values; the result fills the status line and the tool rows.
  - **First expand with no applicable list** runs DD6 once per tile per editor mount, as today's first-expand probe does. Later expands never probe (M07 F09 A-L3-2).
  - **Test** re-runs it with unsaved values; **Refresh** re-lists.
  - **After a Save** that changed a tile's credentials, the tile re-runs the test once with the saved values (`overrides: null`), which writes the per-agent cache.
  - Each test carries a per-tile generation number; a result whose generation is stale (a switch turned off and on again, a newer test, a remount) is dropped. A stdio first spawn can be slow.
- **Construction:** built from the control library (`App.ui.*`: `section`, `button`, `status`, `chip` or `badge`, a password `input`), with no HTML-string sinks and no owned classes outside `js/ui/`. It lives in a new area module (suggested `studio/mcp-agent-credentials.js`, `App.studio.mcpAgentCredentials`) that also holds the DD2 error mapping, so `mcps-tab.js` (497 lines) grows only by its hooks and `agent-editor-controller.js` (771 lines, no allowance in `tests/test_area_module_size.py`) by at most 10 lines.
- **Accessibility:**
  - each row is a labelled group named by its header name;
  - state is shown as text, not by colour alone;
  - the switch-on test result is announced through the tile's live status;
  - focus stays on the switch after the switch-on test, moves to the input when Set for this agent or Replace is pressed, and returns to that button on Cancel;
  - leg 3's spec names the event, announcement and focus for each transition (sortie 07 debrief).

**DD11: Test apparatus.** Leg 1 adds `tests/fixtures/mcp/key_server.py`, a streamable-http MCP server built like `rich_http_server.py`.
- It runs as a uvicorn subprocess (`--port 0` prints `PORT n`) and as an in-process ASGI app for unit tests.
- It starts with `--keys` naming the header and a set of keys, each mapped to its tools (for example header `X-Api-Key`, key `alpha` sees `echo`, key `beta` sees `echo` and `add`). Leg 1 fixes the exact flags and the `echo`/`add` argument names, which the behavior test then cites.
- A request without a matching key gets a bare 401 (no `resource_metadata`). `tools/list` returns only that key's tools.
- It keeps a request log readable over a control route, so the behavior test can see which key each agent sent. Each entry records a sequence number, the JSON-RPC method (so a `tools/call` can be told apart from a re-test's `tools/list`) and only the last 4 characters of the key.

**DD12 (HAT, operator 2026-11-04): the agent tile's section is the Library headers table, unlocked by one "Override headers" button.** This supersedes DD10's per-row layout (the "Set for this agent" / "Replace" / "Use server value" buttons, the row states and "Add header"). DD10's status line, test triggers, list choice and accessibility rules stay.
- **Why:** at the HAT the operator found the per-row layout off-style (the wrong font, a value field that was too short) and asked for the section to look identical to the Library MCP editor's headers table, with its key/value columns, "value" placeholder, Sensitive toggle and trash, and one "Override headers" button in place of the per-row buttons.
- **Locked (default):** the section shows this agent's **effective** headers, a stdio source's environment variables likewise:
  - the server's names, plus this agent's;
  - in the Library table's look, with the **Key and Value columns only** (operator: the toggle and trash appear only once Override is on);
  - values shown as the Library shows them: a sensitive value masked, a non-sensitive value in clear, a blank one empty with the "value" placeholder;
  - a row this agent overrides is marked (for example "this agent" beside the key).
  
  Above the table sits a single **"Override headers"** button ("Override environment variables" for stdio).
- **Unlocked (after "Override headers"):**
  - the table becomes the same editable table as the Library's: Key, Value, Sensitive, trash and "+ Add row";
  - a server row's key is not editable, and its value starts empty with the "value" placeholder; (superseded at HAT H6: it starts at the server's own value, clear or its mask; unchanged is no override, changing it is one, clearing it means none)
  - typing a value sets this agent's override; leaving it empty keeps the server's value;
  - trash on a server row removes this agent's value and returns to the server's;
  - trash on an agent-only row removes it;
  - Cancel discards the edits and locks the table again.
  
  Edits join the editor's dirty state and are sent on Save in the DD1 write shape.
- **Sensitive per row (operator 2026-11-04, "Toggle per row, like Library").** A per-agent value can be marked non-sensitive. It is still stored only in the encrypted `agents.mcp_overrides` column, but agent responses return it in clear, so it is shown again on reload. A sensitive value stays masked (DD9). This narrows charter criterion 1 ("values are write-only") to **sensitive** values; operator decision, recorded here. A new value defaults to sensitive, as in the Library.
- **Server change (to be confirmed by the design review):** a non-credential list in the override entry naming the non-sensitive names (suggested `plain_names: list[str]`, like `enabled_tools`: not `Substitute`-marked, stripped before the resolver).
  - `_agent_response` doesn't mask those names.
  - DD2 validation requires each listed name to be in the entry's `headers`/`env`.
  - The merge treats the list like the other non-credential keys (it comes from the body when the entry is present).
  - Studio sends a non-sensitive value back as its clear text and a sensitive unchanged one as `__MASKED__`.
- **Mockup review changes (operator, 2026-11-04, on the rendered mockup):**
  - The section title is just "Headers", the Library's own title (stdio: the Library's environment title).
  - The status-line row's buttons mimic the Library editor's Cancel/Save/Test trio. Test always shows; Cancel and Save show only after "Override headers".
  - Refresh is removed: it now does what Test does, a fresh per-agent listing with the tile's current values.
  - **The tile's Save saves right away** (operator: "Saves the overrides right away"). Save writes this server's credential overrides for this agent at once, re-tests and locks the table.
    - It goes through a new **targeted** route that updates only that source's credential keys (`headers`/`env`/`bearer_token`/`plain_names`) in the agent's `mcp_overrides`, with DD2 validation, DD7 eviction and the DD5 cache-row delete. It never does a whole-row PUT, so other unsaved editor edits and the stored tool filters are untouched.
    - The agent editor's main Save no longer sends credential keys; the existing omitted-keeps merge rule preserves them.
    - The tile's Save is disabled for an agent that has never been saved (create mode).
  - The row marker pill reads **"overridden"**: this agent sends its own value for that name instead of the Library's, or has a name the Library lacks (operator, final mockup review; approved).
  - The **"Override headers"** button ("Override environment variables" for stdio) lives in the same action row, not the section header (operator, second mockup review). The locked row is: status text, then **Override headers** and **Test**. The unlocked row is: status text, then **Cancel**, **Save** and **Test**. The section header carries only its title.
- **Mockup** (the first rendered version was approved with the changes above; an ASCII summary follows):
```
HEADERS FOR THIS AGENT                       [Override headers]
KEY                  VALUE
X-Api-Key  (agent)   ••••••••••-7Q2
X-Org                acme

-- after Override headers --
KEY              VALUE                        SENSITIVE
[X-Api-Key   ]   [••••••••••-7Q2      ](o)    [on ]      🗑
[X-Org       ]   [value               ]       [off]      🗑
[+ Add row]                                        [Cancel]
```

### Citation Audit

Verified against the working tree at `2958510f` (code interrogation, 2026-11-03); Architect review 1 re-checked a sample and added rows marked (A).

| Citation | Status |
|---|---|
| `mcp/_overrides.py`: `StdioMCPOverride.env`, `StreamableHttpMCPOverride.headers` / `bearer_token`, all `Substitute`; `MCP_OVERRIDE_CREDENTIAL_KEYS` = `{env, headers, bearer_token}` | verified |
| `mcp/_tool_provider.py::_apply_override` (~106-186) overlays `headers`/`env` flat onto `source.secrets`; `bearer_token` becomes `secrets["Authorization"]` after `headers` | verified |
| `_tool_provider.py` Path B (~285) uses `source.config["_cache"]["tools"]` when non-empty and skips `acquire`; Path A (~313-318) calls `acquire(agent_name, source.id, source_override=effective_source)` | verified |
| `api.py::_agent_response` (~211-270) masks each inner value of dict-valued credential keys and keeps the names | verified (A) |
| `api.py::_merge_preserved_mcp_credentials` (~366-455): a present entry takes its non-credential keys from the body (~427); inside a present `headers`/`env` dict a left-out name is dropped and only masked names keep their stored values; pinned by `tests/test_db_api.py:407-449` | verified (A) |
| `api.py::_emit_mask` (~2986-3006) shows the last 4 characters of a value of 12 or more | verified (A) |
| `mcp/_pool.py::acquire` (466) keys `(agent_name, source_id)` and pins the first `source_override`; `_evict(key)` (254) evicts one key under `_lock`; nothing in `create_agent`/`update_agent`/`update_mcp_source` evicts | verified (A) |
| `mcp/_pool.py::_entry_worker` (~207-224) builds the OAuth provider before its `try` | verified (A) |
| `mcp/_tool.py:126,174-177`: `MCPClientTool` captures `_effective_source` at build and passes it to every `acquire`; `_tool.py:180` returns `f"{type(e).__name__}: {e}"` to the agent | verified (A) |
| `app.py::_get_or_restore_session` (~1956): every join rebinds `Session.agent` to the current config; not mid-turn | verified (A) |
| `api.py::_test_mcp_connection_inner` (4023-4444): Phase 0 writes `auth_posture: "oauth"` on any 401 (~4218-4223); Phase A inline (~4230-4333) clears tokens, evicts and falls through to Phase B on failure; `_is_credentials_rejection` (~4375) needs non-empty headers; cache writes run even when an override was applied | verified (A) |
| `api.py::_mcp_source_response` (~3133-3169): `oauth_active` = any OAuth-managed key present | verified |
| `mcp/client.py::_signin_signal` (381-405) treats a non-empty `build_request_headers` as credentials evidence | verified (A) |
| `transports/streamable_http.py::build_request_headers` (157-190) and `transports/stdio.py::build_stdio_environ` (368-394) send empty values as-is | verified (A) |
| `agent-data.js:413-452` `fetchMcpSourceTools` POSTs `/test/connect` with no body; `mcps-tab.js::loadTools` (~367-404) calls it on first expand when nothing is cached; `cachedTools` (106-109) reads `source.config._cache.tools` | verified (A) |
| `agent-form-data.js::collectFormData` (277-325) builds `mcp_overrides` from loaded tool rows only; no credential keys | verified |
| `agent-editor-controller.js` is 771 lines with no allowance in `tests/test_area_module_size.py` | verified (A) |
| `db/schema.py` `CURRENT_VERSION = 49`; v43 `agent_notes` uses `REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`; `db/connection.py:55` turns foreign keys on | verified (A) |
| `mcp/oauth/storage.py::OAUTH_MANAGED_SECRET_KEYS` (51-60); OAuth tokens per source (`MCPSourceTokenStorage(repo, source.id)`) | verified |
| `tests/fixtures/mcp/asgi_401.py::Auth401Wrapper` keys on JSON-RPC method, not headers; no header-checking fixture exists | verified |

### Prerequisites
- [x] No open mission or sortie overlaps (missions 01-34 and sorties 01-08 completed).
- [x] Behavior-test apparatus:
  - a branch-built dev instance on port 8486 or higher with a scratch data dir under `$HOME` (never 8484/8485), and `MCP_POOL_IDLE_TTL_SECONDS=3600`, so a reconnect is proven to come from eviction on save and not from the idle reaper (an environment-supplied default, pinned);
  - the header-checking test MCP server (DD11, added in leg 1);
  - shell `curl` for API reads;
  - the goldfinch browser MCP for the UI steps.
  
  Read paths: `GET /api/agents/{name}` (`mcp_overrides` names, `mcp_tool_cache`), `GET /api/mcp-sources/{id}` (`config._cache`), the DD6 route's response, the test server's request log (which key each request carried), and the transcript of a chat whose mock provider calls an MCP tool. **Re-verify that goldfinch is registered and the ports are free at run time.**
- [x] Mock provider tool calls work with dev mode on (`CLAUDE.md` "Mock provider `config` options"; the mock needs a `base_url`). The mock repeats its `tool_calls` every iteration, so the behavior test uses `max_iterations: 1` and expects the step-limit notice.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined
- [x] Operator-approved mockup recorded (DD10)

---

## In-Flight

### Technical Approach
1. **Leg 1, credentials take effect.**
   - Files: `mcp/_overrides.py`, new `mcp/override_validation.py`, `mcp/_tool_provider.py`, `mcp/_tool.py`, `mcp/_pool.py`, `mcp/client.py`, `mcp/transports/streamable_http.py`, `mcp/transports/stdio.py`, `interfaces/web/api.py`, `tests/fixtures/mcp/key_server.py`.
   - Work: DD2 validation and its 422s; DD3 blank values dropped, `missing_values`, the `_signin_signal` evidence rule and the Library Test's missing-values path (including the Phase B fall-through for an OAuth server); the `cache_write` / `record_era` switches on the stdio and no-auth helpers (DD6); DD7 resolve-at-connect, `_evict_all_for_agent` and pool eviction at the four hook points; DD8 OAuth skip; DD1's case-insensitive header overlay; the DD11 fixture.
   - Extra tests: an OAuth server with a "Set per agent" header gets `auth_required` (and can sign in) from the Library Test, not a rejection; a resolver failure becomes a plain tool error.
   - Tests: unit tests per rule with falsification of each layer (validation, eviction trigger, resolve-at-connect, blank drop, classification), including two agents against `key_server.py` in-process (a changed key reaches the next call after a save, without a restart; the build-time capture is used only for an agent not in the store); a `null` inner value is a 422; a pool worker whose resolver raises does not hang its waiters.
   - Gate: `make test-unit`, plus the `mcp` and `mcp-connection` browser lanes (the Library Test path changes).
   - Docs: `the_one/agents.md` ("Agent override secrets storage", the pool's pinning note, "MCP error translation"), `SECURITY-MODEL.md` (DD9, first part).
2. **Leg 2, per-agent tool list.**
   - Files: `db/schema.py`, `db/repositories.py`, `mcp/_overrides.py`, `mcp/_tool_provider.py`, `agent/factory.py`, `self_configuration/projection.py`, new `mcp/agent_test.py`, `interfaces/web/api.py`.
   - Work: the DD4 helper and the three readers; the DD5 table (v50), repository, single-statement race guard, the cache-row deletes at the DD7 hooks and the additive `mcp_tool_cache` field; the DD6 route with the Phase A extraction, calling leg 1's `cache_write` modes. `update_agent` ignores the derived response fields (`mcp_tool_cache`, `notices`, `kb_tool_names`) when a client sends a GET body back; a test pins it.
   - Tests: two agents with different keys list different tools; an agent without overrides still uses the shared cache and does not acquire; the route never writes `auth_posture`, `last_check` or the era record, writes the shared cache only for an agent with no override and no unsaved values, and writes the per-agent cache only for stored credentials; a stale write is refused by the race guard; the Library Test is unchanged (its existing tests pass untouched); schema pins (`tests/test_schema.py`) and the template.
   - Gate: `make test-unit`, plus the `mcp`, `mcp-connection` and `agents` lanes.
   - Docs: `the_one/agents.md` (a new "Per-agent MCP credentials (sortie 09)" block), `CLAUDE.md` (the `mcp_overrides` watch-out gains the per-agent credentials rule and the test route), `SECURITY-MODEL.md` (the tool-list note).
3. **Leg 3, UI.**
   - Files: new `studio/mcp-agent-credentials.js`, `mcps-tab.js`, `agent-form-data.js`, `agent-data.js`, `agent-editor-controller.js` (a delegate of at most 10 lines), `mcp-env-headers.js`, `index.html`, `docs/ui-testid-registry.md`.
   - Work: the DD10 tile section and status line, the test triggers and generation guard, Test and Refresh through DD6 (replacing the tab's `/test/connect` call), the DD1 write shape and tool-filter rule, the DD2 error mapping, the DD3 Library placeholder and hint.
   - Client cache: `agent-data.js:413-447` keeps a module-level promise cache keyed by source id only. DD6 results are keyed by agent and source (or not cached) and dropped on Save, so switching agents in Studio never shows another agent's list. Keep the `fetchMcpSourceTools: HTTP` error prefix that `mcp-error.js:21` relies on, or update that regex.
   - Browser tests in a new file, `tests/browser/test_flow_studio_mcp_agent_credentials.py` (lane `agents`; mock `/test/agent` with `page.route`, as `test_studio_mcps_tab.py` does). They cover:
     - row states, including the `bearer_token` row and the OAuth row;
     - set, replace and remove, and the exact PUT body (masks for unchanged names, removed names left out);
     - open-and-close staying clean;
     - a credential change on a tile with unloaded rows keeping the stored tool selection;
     - the switch-on test result, "Needs a value", and a stale result dropped after off/on;
     - a credentialed agent never shown the shared list;
     - a 422 landing on the row;
     - stdio "Environment for this agent";
     - the Library placeholder (lane `mcp`, if it goes in an MCP-editor file).
     
     New testids are registered.
   - Gate: the full `--parallel 3` browser gate on a quiet host (the leg touches the shared agent write path): rc=0, or one failure that passes isolated and is logged.
4. **Leg 4, HAT** (optional; the operator opted in): a guided session over the tile, the Library placeholder and two agents on one real server, using `key_server.py` and the operator's own servers where useful. It includes at least one state the operator is not looking at: an open chat in another tab that keeps working after the key is changed (DD7). It also covers criterion 4 (an OAuth server's Authorization row) and the stdio path, which the behavior test leaves out.

### Checkpoints
- [x] Leg 1: validation, blank-drop, classification, eviction and resolve-at-connect green; `mcp` and `mcp-connection` lanes green
- [x] Leg 2: per-agent tool list, cache table and test route green; `mcp`, `mcp-connection` and `agents` lanes green
- [x] Leg 3: Tools tab and Library UI green; full `--parallel 3` gate green
- [x] Behavior test `per-agent-mcp-credentials`: run 1 (leg 3 UI) passed 14/14; run 2 (final build) 13/14, with step 5 failing on a spec error the operator resolved (pill timing), spec amended
- [x] HAT complete

### Adaptation Criteria

**Divert if**:
- Resolving credentials at connection time turns out to need changes to the anyio connect lifecycle after all (M07 F08: get an Architect pass first).
- The Phase A extraction changes the Library Test's observable behaviour (its existing tests must pass untouched).
- A second, independent cluster of decisions appears (for example, per-agent OAuth sign-in): escalate rather than widen.

**Acceptable variations**:
- Helper, module and route names; file placement within `mcp/` and `studio/`.
- The exact wording of row states, hints and 422 sentences, as long as each stays one plain sentence.
- Whether `mcp_tool_cache` rides on the agent response or a small separate read, as long as the Tools tab never probes on a later expand.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `credentials-take-effect` - DD1 (server side), DD2, DD3 (server), DD7, DD8, DD9 (part), DD11: validation, blank values, classification, resolve-at-connect, eviction, OAuth skip, the key-checking fixture
- [x] `per-agent-tool-list` - DD4, DD5, DD6: the cache table (v50), the three readers, the per-agent test route with the Phase A extraction
- [x] `credentials-ui` - DD1 (client), DD2 (mapping), DD3 (Library), DD10: the tile section, test triggers, write shape, Library placeholder; browser tests; full gate
- [x] `hat` - (optional) guided acceptance with the operator
- [x] `sensitivity-and-table-options` - (added at HAT, DD12) the per-agent `plain_names` flag, the targeted credentials route, five `keyValueTable` options
- [x] `tile-on-the-table` - (added at HAT, DD12) the agent tile rebuilt on the Library headers table: locked view, Override headers, Cancel/Save/Test, the tile Save

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Charter success criteria assessed
- [ ] Flight debrief written

### Verification
- Each leg's gate as above, with `THE_ONE_TEST_NETNS=1` for browser lanes; the full `--parallel 3` gate at the end of leg 3 on a quiet host (load below 1.0).
- The Flight Director runs `/mission-control:behavior-test per-agent-mcp-credentials` (`tests/behavior/per-agent-mcp-credentials.md`) against a branch-built dev instance with `key_server.py`:
  - three agents share one server whose Library key is blank; two reach it with their own keys and see their own tools, and the third is told it needs a value;
  - a changed key applies on the next tool call in an open chat;
  - the shared cache is never written by a credentialed agent's test, and no response or log carries a full key.
  
  Dry-run the setup requests before the witnessed run (M34 F2 debrief).
- The HAT leg.
