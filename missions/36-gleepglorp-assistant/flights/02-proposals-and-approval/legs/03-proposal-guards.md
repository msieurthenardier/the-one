# Leg: proposal-guards

**Status**: completed
**Flight**: [Proposals and approval](../flight.md)

## Objective
Make a proposal's "Check this" flag meaningful, and keep secrets out of
proposals.
- **The flag:** `read_app_config` marks a result that holds only operator-typed
  fields, and the taint rule trusts exactly those results. The views GleepGlorp
  reads before proposing come back operator-typed.
- **Secrets:** `propose_change` refuses any proposal whose strings contain a
  stored secret value or a key-shaped string.

## Context
- Flight DD9 (taint, the flag, the secret guard) and DD5 (the tool's step 4).
- Leg 2 builds `propose_change`, which computes taint with today's
  `compute_taint`. This leg changes what counts as trusted, and inserts the
  secret guard as the tool's step 4 (before the taint and the insert).
- Both legs are in Batch A, so nothing reaches the operator between them.
- **Why a content marker:** a tool cannot set `ToolResult.metadata` without
  the frozen `agent/core.py`. `_execute_tool` builds `ToolResult(content=...)`,
  and only the MCP auth path sets metadata. `compute_taint` already reads
  `tr.content` for `list_my_routines` (`FLAGGED_CONTENT_MARK`).
- **Survives truncation:** a tool result over budget keeps its start
  (`Tool.truncation_direction = "head"`, `agent/core.py:649`), so a first-line
  marker survives.
- **Shared code, side effect included:**
  - `compute_taint` is shared, so GleepGlorp's notes saved after
    operator-typed-only reads stop being flagged too. That is intended (the
    Flight 1 debrief noted most notes were flagged).
  - No other agent is affected: `read_app_config` is GleepGlorp's alone.
- **The eval scorer is untouched here:** `evals/checks.py::_taint_expected`
  mirrors the rule but is a frozen module (`tests/test_evals_freeze.py`). Leg 8
  switches it to the shared predicate under its operator-approved re-pin, so
  this leg does not touch `evals/`.

## Inputs
- `the_one/agent/taint.py`: `TRUSTED_TOOL_NAMES` (L36, with `propose_change`
  added by Leg 2), `FLAGGED_CONTENT_MARK` (L50), and `compute_taint` (L67).
  Its TOOL branch checks `name not in TRUSTED_TOOL_NAMES`.
- `the_one/gleepglorp/read_tool.py::ReadAppConfigTool.execute`: it returns
  `json.dumps(data, ...)`. A failure returns "Could not read {kind} right now."
  and a `PlainMessage` returns its text.
- `the_one/gleepglorp/view_core.py`: the declared key constants, `_emit` (the
  structural key guard) and `_list_or_detail`. The views are `view_agents.py`
  (the `agents` list summary is `cut(cfg.description, 100) or "model …"`,
  ~L34-36; the detail has `description`, `system_prompt`, `rules: [{text,
  enabled}]`, …), `view_mcp.py`, `view_library.py` and `view_overview.py`.
- `the_one/db/encryption_corpora.py::gather_corpora(conn, encryptor, *,
  strict)` (L89) returns a `Corpora` of the nine encrypted columns' decrypted
  values. It is shared with key rotation and the encryption-status count.
- Leg 2's `proposals/tool.py` and `shape.py`.

## Outputs
- `taint.py`: `is_trusted_result(name, content)` and `OPERATOR_TYPED_MARK`;
  `compute_taint` uses the predicate.
- The views tag each declared key with its provenance. `read_app_config`
  prefixes the marker when a result holds operator-typed fields only.
- The `agents` list summary becomes operator-typed. The agent detail gains a
  `fields_only` form, and its rules gain a `number`.
- `the_one/gleepglorp/proposals/guard.py`: the secret guard.
  `encryption_corpora.py` gains `secret_leaves`.
- `propose_change` runs the guard (step 4).
- Tests and docs.

## Acceptance Criteria
1. **The predicate.** `taint.py` gains `OPERATOR_TYPED_MARK = "[Settings you
   entered, no outside text.]"` and `is_trusted_result(name: str, content:
   object) -> bool`. It returns `True` when:
   - `name` is in `TRUSTED_TOOL_NAMES`, except a `list_my_routines` result
     holding `FLAGGED_CONTENT_MARK`, which stays untrusted as today; or
   - `name == "read_app_config"` and the content's first line is exactly
     `OPERATOR_TYPED_MARK`.

   It returns `False` otherwise. The content is read through `_tool_text`,
   since `ToolResult.content` may not be a string.
   - `compute_taint`'s TOOL branch uses it, keeping today's sources:
     - the tool's name for an untrusted result;
     - `routine:listed` for the flagged list;
     - `unknown tool` for no match.
   - Behaviour is byte-identical for every other tool. A test runs the
     existing taint tests unchanged, plus new cases.
2. **Provenance, per output path.**
   - **The rule is who can write a value.** It is `outside` when an agent
     (through self-configuration or its routine tools) or a server (MCP
     server reports, catalog data) can write it. It is `operator` when only
     the operator's credential-gated routes can write it, free text included.
   - **Tags are by dotted path** per kind (for example `agents.detail.rules[].text`,
     `mcp_servers.detail.tools[].description`), not by key name, because
     nested `name` and `description` keys mean different things in different
     places. The tables are `OPERATOR_PATHS[kind]` and `OUTSIDE_PATHS[kind]`,
     two declared constants beside `ALLOWED`.
     - A test asserts every path `ALLOWED` can produce is in exactly one of
       them. They cannot drift.
     - The walker treats any emitted path not in `OPERATOR_PATHS` as outside
       (fail closed).
   - **`outside`:**
     - agent `description` and `system_prompt`;
     - any `mcp__…` entry in an agent's `enabled_tools` or `disabled_tools`
       (the server named it; built-in tool names stay `operator`);
     - rule `text` (DD9 keeps it outside: an approved flagged proposal can
       have written it);
     - routine `name` and `prompt`;
     - MCP `tools[]` (names and descriptions);
     - every MCP `connection.*` value read from the server cache
       (`protocol_version`, `auth_posture`, `protocol_fallback`);
     - any server-reported name, version, instructions or model list;
     - any note.
   - **`operator`:** everything else. That includes:
     - names of agents, providers, MCP servers, knowledge bases, connectors and
       secrets;
     - ids, counts, the agent's model and provider;
     - MCP `transport`, `command`, `args`, `working_directory`, `address`;
     - the app-worded `connection.status` and the MCP list summary
       `"{type}, {status}"`, plus the synthetic self-configuration row's
       summary;
     - knowledge-base and secret `description` and the secrets list summary;
     - `built_in_tools` settings;
     - connector `channel_bindings` and `default_agent`;
     - enums, switches, the server-worded schedule sentence, and the `fields`
       kind.
   - A test pins the `outside` set for the agents, routines and MCP views.
   - **Accepted residual.** A field written by an approved proposal is
     operator-written from then on, including one made after untrusted content
     (an agent `name`, its model, tools or attachments). The approval click is
     the control, as flight DD9 records for rules and prompts. Agent names
     also pass the naming rule (no control or bidi characters, at most 64
     characters). `SECURITY-MODEL.md` records this beside the DD9 residual.
   - **The walker.** `views.read_with_provenance(conn, enc, kind, name, *,
     fields_only=False) -> (data, operator_only: bool)` walks the final output
     after the `ALLOWED` check. A walk after the fact covers every call path:
     `_list_or_detail`, the views that call `_emit` directly (`routines`,
     `overview`, `settings`), and nested lists. It reports `operator_only` as
     false when any outside path holds a non-empty value.
     - `fields_only` travels on `Ctx` (a new field, default false), so every
       `VIEWS` entry keeps its `(ctx, name)` call. Only `agents_view` reads
       it.
     - `views.read` keeps its signature and returns `data`, so its callers and
       tests (`test_gleepglorp_views.py` L32-484) are unchanged.
3. **The marker.** `ReadAppConfigTool.execute` returns `OPERATOR_TYPED_MARK +
   "\n" + json` when `operator_only` is true, and plain JSON otherwise.
   - Every failure or `PlainMessage` path returns text without the marker.
   - **The forgery test.** A seeded agent's description begins with the marker.
     Read through the detail form, the walker reports `operator_only` as false
     (the description is non-empty and outside), so the result is not marked.
     The JSON body itself always starts with `{` or `[`.
4. **The view changes.**
   - The `agents` list summary becomes `"{model or 'no model'}, {n} tools,
     {m} MCP servers"`, built from operator fields only, with no
     `description`.
   - The `agents` detail rules gain `number` (1-based, list order) so a rule
     change can name it.
   - **`fields_only`:**
     - `read_app_config` gains an optional boolean `fields_only` (default
       false; only meaningful for `agents` with a name). It returns the
       detail without `description`, `system_prompt` and the rules' `text`;
       rules show `number` and `enabled` only.
     - Every other kind ignores it.
     - The tool's description gains at most one short clause about it, keeping
       its current length plus at most 80 characters.
   - **Tests:** `tests/test_gleepglorp_views.py`'s allowlist, classification
     and secret-parity tests are updated for the new key (`number`) and the
     new form; secret parity covers `fields_only`. The `tests/
     test_gleepglorp_read_tool.py::test_shape` pin, `READ_APP_CONFIG_TOOL_NAME
     not in TRUSTED_TOOL_NAMES`, stays true (the trust is per result, not per
     name).
5. **Which reads are operator-only.** A table test reads each kind seeded with
   realistic data and asserts which results carry the marker:
   - `agents` list: marked;
   - `agents` detail `fields_only`: marked;
   - `agents` detail full: unmarked when a description, prompt or rule
     exists;
   - `mcp_servers` list: marked (its summary is app-worded);
   - `mcp_servers` detail: unmarked when it holds tools or a cached
     connection value;
   - `routines`: unmarked when any routine exists;
   - `overview`, `providers`, `knowledge_bases`, `connectors`, `secrets`,
     `built_in_tools`, `settings`, `fields`: marked.

   The Developer confirms each kind's actual keys and states the final table in
   the flight log.
6. **End to end.** A `compute_taint` test over a scripted message list asserts:
   - after `read_app_config(agents)` (marked) and `read_app_config(fields)`,
     a `propose_change` is not flagged;
   - after a full detail, a `web_search` or an MCP-detail read, it is flagged
     with that source.
7. **`secret_leaves`.** `encryption_corpora.secret_leaves(c: Corpora, *,
   min_len: int = 8) -> set[str]` returns the secret strings of at least
   `min_len` characters, chosen per column:
   - **Provider `api_key`:** the whole value.
   - **Provider and MCP `secrets` blobs:** walked recursively. It takes every
     string value except:
     - the keys `token_type`, `scope` and `scopes`;
     - `dcr_credentials.client_id` (public);
     - non-string values, such as a numeric `token_expires_at`.

     `access_token`, `refresh_token`, `dcr_credentials.client_secret` and every
     MCP source header and environment value are included.
     - Source-level secrets have no `plain_names` exemption. `plain_names`
       exists only on agent overrides.
   - **App-wide tool configs:** every string value of `tool_configs.secrets`
     (`Corpora.tool_configs`), for example a stored web-search API key.
   - **Connector `secrets`:** every string value.
   - **Library secret values:** every value.
   - **External credentials** (`ext_credentials`): the second element of each
     `(identifier, secret)` tuple, never the identifier.
   - **Agent `mcp_overrides`:** only each entry's `headers` and `env` values
     and `bearer_token`.
     - Values whose names are in that entry's `plain_names` are left out,
       matched case-insensitively for headers and exactly for environment
       variables.
     - `bearer_token` and an `Authorization` header are never exempt, even if
       listed, as `api.py` never unmasks them.
     - The tool lists and other keys are never included.
   - **Agent `tool_overrides`:** only the fields a tool's Config marks secret.
     The tool name is mapped to its Config class through the same lookup
     `view_library.py` (~L182) uses before calling
     `view_core._secret_field_names(config_cls)`. The tool lists, timeouts and
     paths are never included.

   Unit tests cover each column and each skip. One test names a disabled tool
   (`mcp__docs__search`) and an `enabled_tools` entry in a proposal and
   asserts they pass.
8. **The guard** (`proposals/guard.py::check(conn, enc, changes) -> str |
   None`) returns a refusal sentence, or `None`. It checks every string value
   in `changes`, nested lists included, so names are checked too:
   - **A stored secret:** containment of any `secret_leaves` value, after
     whitespace trimming.
   - **A key-shaped string:** named constants for common token prefixes
     (`sk-`, `sk-ant-`, `ghp_`, `gho_`, `github_pat_`, `xox`, `AKIA`, `AIza`,
     `glpat-`, `hf_`) followed by at least 16 key characters, and any run of at
     least 32 characters from the base64url alphabet with Shannon entropy of
     at least 4.0 bits per character (`KEY_MIN_LEN = 32`,
     `KEY_MIN_ENTROPY = 4.0`).
   - **Not a key:** a canonical UUID (8-4-4-4-12 hex) is exempt from the
     entropy rule, and a test asserts a UUID in a prompt passes.
   - **The refusal** is one sentence, the same for both cases: "That looks
     like a key or token. Leave it out of the proposal and tell the operator
     to enter it on the right page." It never echoes the value, and nothing is
     logged with the value.
   - **Placement:** `propose_change` calls it after normalising and before the
     taint and insert. A refused proposal writes no row.
   - **Gathering:** `gather_corpora(conn, enc, strict=False)`, called once per
     proposal, never cached.
9. **Tests**, each falsified where marked:
   - `tests/test_taint_results.py`: AC1, AC3's forgery case, AC6.
     Falsification: remove the marker check, and make the predicate trust
     `read_app_config` by name.
   - `tests/test_gleepglorp_views_provenance.py`: AC2, AC5.
   - `tests/test_gleepglorp_proposals_guard.py`:
     - a stored provider key, a Library secret value, an MCP header value and
       a connector token are each refused, from inside a longer prompt and
       from a name;
     - a `plain_names` header value is not refused;
     - an OAuth `token_type` value ("Bearer") is not refused;
     - each prefix and the entropy rule refuse;
     - an ordinary long English prompt and a normal UUID-free sentence pass;
     - a refused proposal writes no row.

     Falsification: drop the corpora check, and drop the entropy rule.
   - **The existing guard set**, unchanged and green: the taint tests, the
     routine and notes flag tests, `tests/test_gleepglorp_*`, and the
     encryption-rotation and status tests (`gather_corpora` is unchanged).
10. **Docs.**
    - `SECURITY-MODEL.md` "GleepGlorp's read surface" gains the provenance
      marker and its fail-closed rules. A new paragraph covers the proposal
      secret guard, its constants and its false-positive trade-off.
    - `the_one/agents.md`'s proposals section names both.

## Verification Steps
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_taint_results.py tests/test_gleepglorp_views_provenance.py tests/test_gleepglorp_proposals_guard.py tests/test_gleepglorp_views.py tests/test_gleepglorp_read_tool.py -x --timeout 60`
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh $(grep -rlE 'compute_taint|TRUSTED_TOOL_NAMES|gather_corpora|count_items_with_secrets' tests/*.py) -x --timeout 60`
- `THE_ONE_TEST_NETNS=1 make test-unit`.
- `ruff check` and `ruff format --check` on the touched files.

## Implementation Guidance
1. **The predicate.** Add `OPERATOR_TYPED_MARK` and `is_trusted_result`, and
   switch `compute_taint`'s TOOL branch to it. Run the existing taint tests.
2. **Provenance.**
   - Declare `OPERATOR_PATHS` and `OUTSIDE_PATHS` beside `ALLOWED`, with the
     drift test.
   - Write the post-hoc walker, and expose `read_with_provenance`.
   - Add `Ctx.fields_only`.

   Nothing is threaded through `_emit` or `_list_or_detail`.
3. **The views.** Make the view changes (the agents summary, rule `number`,
   `fields_only`) and update the views tests deliberately.
4. **The marker.** Wire the marker in `read_tool.py`.
5. **The guard.** Write `secret_leaves`, `guard.py`, and the call in
   `propose_change`.
6. **Tests and docs.** Write the tests, falsify the ones marked, then update
   the docs.

## Edge Cases
- **Empty values.** A free-text key emitted with an empty value (`""`, `[]`,
  `None`) does not taint; it carries no outside text. A test covers an agent
  with no description: the detail is then marked only if it also has no prompt
  and no rules.
- **The list summary's fallback** (`"model …"`) is operator-typed. The new
  summary never includes the description.
- **The marker inside JSON.** A model may quote the marker; only position 0 of
  a `read_app_config` result counts.
- **Short secrets.** A stored secret shorter than 8 characters is not
  searched, so it cannot cause false positives. Note this residual in
  SECURITY-MODEL.
- **Decrypt failures.** A decrypt that fails is skipped (`strict=False`); the
  key-shape rule still applies.
- **The guard's cost.** It runs only when GleepGlorp proposes (rare), and each
  call decrypts every stored secret once. That is acceptable; record it.
- **Eval impact.** Dropping the description from the `agents` list summary,
  plus the new `fields_only` parameter, changes GleepGlorp's model-facing
  text.
  - It is platform prompt text, so it lands with an eval run: Leg 9's
    re-baseline on the changed set covers it. `whats-configured` will need a
    detail read to describe the agents.
  - The offline `tests/test_evals_gleepglorp_*` use scripted calls. Verify
    they pass unchanged.
- **The app guide.** If a guide topic says the agent list shows what each
  agent does, update it in this leg (the guide convention). The guide drift
  test runs.

## Files Affected
- `the_one/agent/taint.py`.
- `the_one/gleepglorp/view_core.py`, `view_agents.py`, `views.py`,
  `read_tool.py`, and others only where tags are declared.
- `the_one/db/encryption_corpora.py` (`secret_leaves`).
- `the_one/gleepglorp/proposals/guard.py` (new) and `proposals/tool.py` (the
  call).
- Tests: three new files, plus `tests/test_gleepglorp_views.py` and possibly
  `tests/test_gleepglorp_read_tool.py`.
- `SECURITY-MODEL.md`, `the_one/agents.md`.

## Citation Audit
Checked against the working tree at `6f073dd4`. Leg 2 edits `tool.py`,
`read_tool.py` and the views. Re-check those citations after Leg 2 lands.
- `taint.py` `TRUSTED_TOOL_NAMES` L36, `FLAGGED_CONTENT_MARK` L50,
  `compute_taint` L67; its TOOL branch checks `name not in
  TRUSTED_TOOL_NAMES`, with the `list_my_routines` mark special case —
  verified.
- `tools/base.py` L57: `truncation_direction = "head"` keeps the start;
  `agent/core.py:649` `self._govern(output, tool.truncation_direction)` —
  verified.
- `read_tool.py::execute`: returns `json.dumps(...)`, the `PlainMessage` text,
  or "Could not read {kind} right now." — verified.
- `view_agents.py::agents_view`: the summary is `cut(cfg.description, 100) or
  f"model {...}"`; the detail emits `description`, `system_prompt`, `rules
  [{text, enabled}]` — verified.
- `encryption_corpora.py::gather_corpora(conn, encryptor, *, strict)` L89;
  `Corpora` L42; `count_items_with_secrets` L162 — verified.
- `evals/checks.py::_taint_expected` ~L554 imports `TRUSTED_TOOL_NAMES`
  (frozen; left to Leg 8) — verified.
- **Design review** (Developer, Sonnet): approve with changes. The findings,
  all folded in above:
  - `Corpora.agents` holds whole override blobs.
  - `OAUTH_MANAGED_SECRET_KEYS` includes the nested `dcr_credentials`.
  - The `ext_credentials` pair is `(identifier, secret)`.
  - The MCP `connection.*` values come from `_cache`.
  - `Ctx` is a dataclass with `conn` and `enc`, and the `VIEWS` call is
    `(ctx, name)`.
  - `routines`, `overview` and `settings` call `_emit` directly.
  - `ALLOWED["…"]["nested"]` is a flat set.
  - `test_gleepglorp_read_tool.py::test_shape` pins `len(description) <
    600`.
- **Design review cycle 2** (Developer, Sonnet): approve with changes. The
  findings, all folded in above:
  - The app-wide tool config secrets were missing (high).
  - `plain_names` applies only to agent overrides, and bearer and
    Authorization are never exempt.
  - Guidance step 2 contradicted AC2.
  - Agent tool lists can hold server-named `mcp__…` entries, now outside.
  - Approved values are an accepted, recorded residual.
  - The tool-overrides Config lookup is the one `view_library.py` uses
    (~L182).
  - `ext_credentials` takes its second element.

  The cycle limit is reached.
