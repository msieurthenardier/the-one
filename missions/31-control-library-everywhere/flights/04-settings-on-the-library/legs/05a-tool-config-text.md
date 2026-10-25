# Leg: tool-config-text

**Status**: completed
**Flight**: [Settings on the library](../flight.md)

## Objective
Give every built-in tool's settings plain, operator-facing text on the backend, none of it seen by the model:
- written field titles (A7) and descriptions (squawk 0231, B7);
- plain preset labels (B5);
- a short human summary per tool (B1);
- a per-tool list of the settings that apply to it (B6).

Separately, remove the stale "F6 admin will surface the picker." sentence from `web_search`'s model-facing description (A17), with a prompt eval run.

## Context
- **Flight decisions:** DD7 (ledger rows 7, 17, 25, 29, 30, 31), DD9 (0231), DD10.
- **Split at planning** from the original leg 05 (2026-10-23):
  - **05a (this leg):** the backend text and schema shaping. It changes what `GET /api/tools/configs[/{name}]` serves, and one model-facing sentence.
  - **05b:** the shared client field module.
- **The served schema is built by** `the_one/interfaces/web/api.py` `get_tool_config` → `_enrich_schema_with_markers(cls.Config.model_json_schema(), cls.Config)`:
  - it adds `x_marker`;
  - since squawk 0248, it also materialises each `default_factory` default.

  The Config classes are `FilesystemConfig` (`filesystem.py:61`, shared by 9 tools), `ExecutionConfig` (`execution.py:116`) and `PythonExecConfig` (`:302`), `WebConfig` (`_web_config.py:110`) and `WebSearchConfig` (`_web_search_config.py:51`). Tools with no settings use `_EmptyConfig` (`resolver.py:95`).
- **Not model-facing, verify it.** `model_json_schema()` and the tool classes' new `summary` and `config_fields` are read only by the tools-config routes. The model sees each tool's `name`, `description` and `parameters` (`the_one/tools/base.py` about `:179`), never its Config schema. Add a unit test proving it:
  - render every tool's model-facing schema (the provider tool-schema path) before and after the change, and assert it is byte-identical;
  - **except** `web_search`'s description, which changes for A17 only.
- **A7, field titles:** add `Field(title=…)` to every Config field, in sentence case, for example:
  - "Maximum read size" (`read_size_cap_bytes`);
  - "Default timeout" and "Maximum timeout";
  - "Idle session timeout" (`pty_session_idle_ttl_seconds`);
  - "SearXNG URL", "Google PSE API key", "Allow network in the sandbox", "Allowed paths", "Denied paths", "Allow binary files", "Response size limit", "Redirect limit", "Allowed hosts", "Denied hosts", "Extra allowed hosts", "Default user agent".

  Write every one; no field may fall back to the auto-generated title. A unit test asserts every property of every served schema has a `title` that is not the auto-generated Title Case of its name.
- **0231 and B7, descriptions:** every field of `FilesystemConfig` gets a `description` (one or two plain sentences: what it controls, and its default behaviour). Check the other Configs too, and add any that are missing. A unit test asserts every property of every served schema has a non-empty `description`.
- **B5, preset labels:** rewrite the `ui_choices` labels as plain text. Drop model jargon such as "Opus 200K headroom" and "Opus 1M only", and drop "default (shell)" and "(python)" in favour of "(default)" on the default value. Keep the values. A grep-backed list of every changed label goes in the flight log.
  - `ExecutionConfig`'s `_TIMEOUT_DEFAULT_UI_CHOICES` (`execution.py:59-71`) is shared by shell and python. The plain label marks the default of the tool being shown. If one shared list cannot do that, have the route mark the default per tool (`ui_choices` entries keep `value`/`label`, plus a served `default: true` flag the client reads). Pick one and say which.
  - On `fetch_url`, "Timeout Seconds Max" is a plain number while "Timeout Seconds Default" is a dropdown. Give the maximum a dropdown too only if a natural preset list exists; otherwise leave it.
- **B1, summaries:** a `summary` class attribute on every tool class in `_TOOL_CLASSES` (one short plain sentence, at most about 80 characters, for example "Reads a text file's contents."). It is served as `summary` by `GET /api/tools/configs` (the list) and the detail route. It is not model-facing. A unit test asserts every tool has one, within the length limit.
- **B6, per-tool fields:** a `config_fields` class attribute (a tuple of field names, or `None` meaning all) on tools whose shared Config has settings that don't apply to them:
  - `delete_file`, `mkdir` and `move_file` don't read file contents (no `read_size_cap_bytes`, no `allow_binary_files`). Check each tool's code for the fields it actually reads.

  The detail route filters `schema.properties` (and `required`) to `config_fields`. **Storage and resolution are unchanged:** the stored config and `Config` validation still accept every field, so an existing stored value for a hidden field is kept and still applied. A hidden field is only not shown; say this in `agents.md`. The agent Tools tab reads the same detail route (`tools-tab.js` `fetchToolSchema`), so it hides them too. Unit tests:
  - the filtered properties per tool;
  - a stored value for a hidden field survives a PUT that omits it;
  - the resolver still applies the stored hidden value.
- **A17:** remove "F6 admin will surface the picker." from `WebSearchTool.description` (`web.py` about `:468`), leaving "Search the web and return results (title, URL, snippet). The backend is operator-configurable (default DuckDuckGo). Useful for finding URLs to feed into fetch_url or read."
  - This is starting tool-description text, which CLAUDE.md "Prompt evals" puts under the convention: an eval run compared against `evals/baselines/m30-platform.json`, including token cost (`make eval ARGS="measure-prompt"`, then `compare --baseline evals/baselines/m30-platform.json`).
  - **Before running the eval, re-verify** (Architect E3): the plan token at `~/.config/the-one-evals/plan-token`; Ollama serving `gpt-oss:20b`; `pip install -e ".[evals]"` with the tiktoken cache.
  - **Then stop and ask the Flight Director to confirm** with the operator before spending plan quota. Emit `[BLOCKED:eval-consent]` with the exact command and its expected scenario count, and wait. Run the eval outside any concurrent browser lanes.
  - **If the compare fails its gate** (flight Adaptation Criteria): revert A17, leaving the description unchanged, and record it.

## Inputs
- Squawk 0248 merged (the materialised defaults).
- Legs 01-04f landed. Nothing in 04 touches this backend; 05a could run earlier, but it runs here so the before captures (leg 01) predate it.

## Outputs
- The Config classes with titles and descriptions, and plain `ui_choices` labels.
- `summary` and `config_fields` on the tool classes; the routes serving `summary` and the filtered properties.
- `WebSearchTool.description` without the stale sentence; the eval run's report in the flight log.
- Unit tests: titles, descriptions, summaries, per-tool fields, the model-facing schema being byte-identical except A17, hidden-value persistence.
- `the_one/agents.md` ("UI schema metadata", plus `summary` and `config_fields`); CLAUDE.md's evals note, if the baseline gains a run record; squawk 0231 completed.

## Acceptance Criteria
1. Every served property has a written sentence-case `title` and a non-empty `description` (unit-tested over all tools).
2. Every tool has a `summary` of at most about 80 characters (unit-tested). The list and detail routes serve it.
3. **`config_fields`:**
   - filters the detail schema for the tools named;
   - a stored hidden value is kept on a PUT that omits it, and still resolves (unit-tested);
   - the list of hidden fields per tool is in the flight log, with each choice justified by the tool's code.
4. The `ui_choices` labels are plain (the list of changes is in the flight log), and the default marking is correct for shell and python.
5. **The model-facing tool schemas are byte-identical before and after,** apart from `web_search`'s description (unit-tested).
6. **A17:** the eval compare passes its gate with the token delta recorded, and the operator's consent is recorded in the flight log. Or A17 is reverted with the reason recorded.
7. Squawk 0231 is completed.
8. The unit tier passes. The `settings` and `agent-tabs` lanes pass, with retargeted assertions only (their label text changes: ledger rows 7 and 29).
9. **The visible change is captured:** a re-capture of the tool editor surfaces and `agent-tools`, compared with leg 01's before set. Each difference maps to ledger rows 7, 25, 29, 30 and 31.

## Verification Steps
- `.venv/bin/python -m pytest tests/test_api_tool_configs.py tests/test_tool_categories.py <new tests> -q -x --timeout 120`, then `make test-unit`.
- `make eval ARGS="measure-prompt"` and `make eval ARGS="compare --baseline evals/baselines/m30-platform.json …"` (after consent).
- The `settings` and `agent-tabs` lanes under netns.

## Implementation Guidance
1. The byte-identical model-schema test first (it must pass before any change).
2. Titles and descriptions, then labels, then summaries, then `config_fields`, each with its tests.
3. A17 last: re-verify the eval prerequisites, emit `[BLOCKED:eval-consent]`, and wait.

## Edge Cases
- **A field shared by tools where one hides it:** the shared Config keeps it. Only the served schema differs per tool.
- **An agent override on a field that becomes hidden:** the agent Tools tab no longer shows it, but the stored override stays and still applies. Record that this is accepted, and note it in `agents.md`.

## Files Affected
- `the_one/tools/filesystem.py`, `execution.py`, `_web_config.py`, `_web_search_config.py`, `web.py`, `builtins.py` (or the tool classes), `the_one/interfaces/web/api.py`.
- `tests/test_api_tool_configs.py`, new unit tests, `settings`/`agent-tabs` browser test assertions.
- `the_one/agents.md`, `squawks/0231-*`, the flight log.

## Citation Audit
- Config classes at `filesystem.py:61`, `_web_config.py:110`, `execution.py:116`/`:302`, `_web_search_config.py:51`, `resolver.py:95`: verified (FD grep).
- `execution.py:59-71` `_TIMEOUT_DEFAULT_UI_CHOICES`: verified.
- `web.py` about `:466-470` `WebSearchTool.description`: verified (FD read).
- `api.py:465` `_enrich_schema_with_markers` with the 0248 defaults: verified.
- `tools-tab.js` `fetchToolSchema`: verified (FD grep).

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **B6 needs a PUT change: hidden fields keep their stored values.** Today `upsert_tool_config` validates the incoming config and stores `validated.model_dump()` (`api.py` about `:661`, `:676`), so an omitted field is filled with its default and overwrites the stored value.
  - **The fix:** for a tool with `config_fields`, the PUT copies each hidden field's stored value into the incoming dict before validating. A stored value that no longer validates falls back to its default, with a log line.
  - Test-first through the real route: store a custom `read_size_cap_bytes` on `delete_file` through the API (before hiding), hide the field, PUT the visible fields only, and the stored value survives.
  - Record in `agents.md` that `config_fields` is display-only, and that a PUT never resets a hidden field.
- **The `config_fields` audit** (from the review; confirm by reading each tool):
  - `read_size_cap_bytes` and `allow_binary_files` are read only by `read_file`, `edit_file` and `grep`, so **six** tools hide both: `write_file`, `list_dir`, `glob`, `delete_file`, `move_file` and `mkdir`;
  - audit `ExecutionConfig` across `shell` and the four `shell_session_*` tools (`close` and `list` likely read no timeouts);
  - audit `WebConfig` across `http_request`, `fetch_url` and `download_file`.

  Put the resulting table in the flight log.
- **The model-facing check is structural, not a committed golden** (the operator's no-golden-files rule):
  - every tool's `to_schema()` (`base.py` about `:176`) has exactly the keys `{name, description, parameters}`;
  - no `to_schema()` text contains any `summary`, Config title or Config description string;
  - `web_search`'s description equals the new literal;
  - check whether any provider adapter reads anything beyond `to_schema()`.
- **Default marking for the shared timeout list:** a helper builds `ui_choices` from the default value, giving two lists (shell default 30, python default 90), each marking "(default)" on its own default. No served flag and no client change.
- **No browser test pins** today's titles or labels (the review grepped). AC8's retargeting is expected to be empty or tiny; say so in the flight log.
- **Titles:** the unit test compares each `title` with `name.replace('_', ' ').title()` (Pydantic's auto title). Terse existing descriptions (for example `ExecutionConfig`'s "Used when agent omits timeout.") are rewritten too, not just filled in.
- **`fetch_url`'s maximum timeout** stays a number (`WebConfig` has no natural preset list).
- **A17's eval:**
  - `evals/harness.py:68` lists `web_search` in `DISABLED_TOOLS`, so no scenario exercises it; the deleted sentence only changes the token count.
  - At the `[BLOCKED:eval-consent]` stop, give the Flight Director two options with exact commands and costs:
    - (a) `measure-prompt` plus the `compare` size gates only, with no model run. This is cheap and justified by a one-sentence deletion on a tool the scenarios disable;
    - (b) the full `run` (quote the scenario and cell counts from `evals/README.md`) plus `compare`.
  - The operator chooses, and their choice is recorded. The revert-on-gate-fail rule stands either way.
- **The agent-override side of B6** (a stored override on a newly hidden field) is fixed in leg 05c, not here.

## Design Review Amendments (cycle 2, 2026-10-23)
These override the body and cycle 1 where they conflict.
- **The merge helper** `_merge_hidden_fields(cls, tool, incoming, stored)`:
  - it reads stored hidden values from `{**existing.config, **existing.secrets}` (secrets are split out of `config`);
  - **the stored value always wins** over any incoming value for a hidden field, so hidden fields are not writable through the form;
  - validate the merged dict; on `ValidationError`, retry without the stored hidden values. If the retry succeeds, store it and log that a stored hidden value no longer validated; if the retry also fails, return the 422 from the retry's errors (the operator's visible edit is at fault).
  - Tests drive the helper directly and through the route, with `config_fields` set by monkeypatching the tool class:
    - store a custom value before hiding the field;
    - an incoming differing hidden value is ignored;
    - a never-saved tool (no row) copies nothing, and 0248's defaults apply;
    - a secret hidden field is a guard test (latent today).
- **Replace semantics are narrowed:** a PUT, or a `{config: {}}` reset, no longer resets hidden fields. Update the `upsert_tool_config` docstring. If the audit hides a field the existing unit tests use on `http_request` (`test_put_replaces_config_wholesale` `:278`, `test_put_with_empty_config_wipes_to_defaults` `:349`), retarget those tests to visible fields; keep them as REPLACE tests for the visible set. Check whether any "reset to defaults" control exists (none expected); record that a reset leaves hidden fields as stored.
- **Superseded body lines,** read as amended:
  - Context's "render every tool's model-facing schema before and after … byte-identical", Outputs' "byte-identical except A17", AC5 and Guidance step 1 all mean **the structural `to_schema()` check** (cycle 1);
  - B6's three-tool list is superseded by cycle 1's six-tool audit.
- **AC8** adds the unit-tier retargets above.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
