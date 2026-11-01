# Leg: override-rules

**Status**: completed
**Flight**: [Agent tool overrides](../flight.md)

## Objective
Give the resolver one total definition of "what fits" for agent tool overrides and use it on the build path, so no stored override can make an agent build fail, with the `host_allowlist` "any when empty" marker and its code-enforced `NO_HOSTS` on the wire and in the client.

## Context
- Flight design decisions implemented here: **DD1** (strict `resolve` kept; new total `clip_override`), **DD2** (the clip table; default follows a lower max), **DD3** (denied lists resolve as a union), **DD4** (`NarrowAnyWhenEmpty` on `host_allowlist`; `NO_HOSTS` enforced in `_url_check` with no DNS; the `x_marker` and client `allowed()` change in the same leg), and **DD7's first two bullets** (clip in `BuiltinToolProvider.get_tools`; a rate-limited warning). Read those sections of `../flight.md` in full: they are the spec.
- **Split from the planned leg 1** (design review, 2026-10-31): the save-time 422 (DD5), derived notices (DD6) and DD7's failure-path hardening (`build_failed` restore, routine runner, connector catch-all) are the next leg, `save-and-notices`, which builds on this leg's per-field helpers. Legs after it keep their order.
- **Not in this leg:** the per-hop host check in `SSRFGuardedTransport` (DD15, `redirect-hosts`); anything on the agent tab beyond `allowed()`.
- **Baseline:** the worktree's unchanged-base run recorded in the flight log; a failure on that list is pre-existing.

## Inputs
- `the_one/tools/resolver.py` (`Narrow`, `NarrowPrefix`, `NarrowSuperset`, `Substitute`, `_check_narrow` `:110-150`, `_check_narrow_prefix`, `_check_narrow_superset`, `resolve` `:195-267`); no clip function.
- Marked fields (measured 2026-10-31): `FilesystemConfig` (`path_allowlist` NarrowPrefix, `path_denylist` NarrowSuperset, `read_size_cap_bytes` and `allow_binary_files` Narrow), `ExecutionConfig` and `PythonExecConfig` (timeout default/max, output cap, PTY TTL, session cap and `sandbox_network_allowed` Narrow; `command_denylist` NarrowSuperset), `WebConfig` (timeout default/max and response cap Narrow; `host_allowlist` Narrow; `host_denylist` NarrowSuperset; `extra_allowed_hosts` Narrow; `default_user_agent` Substitute; `redirect_cap` unmarked). `WebSearchConfig`'s fields are all unmarked. No config has an unmarked boolean.
- `the_one/tools/_web_config.py`: `_url_check` (`:350`, empty allow list = any host); `the_one/tools/builtins.py::get_tools` (`:140-205`, per-tool `resolve` at `:195-200`); `api.py` `x_marker` map (`:490-540`); `areas/shared/tool-config-fields.js::allowed` (`:81-86`).

## Outputs
- `resolver.py`:
  - `NarrowAnyWhenEmpty`, `NO_HOSTS = "none.invalid"`;
  - `OverrideWidensError(ValueError)` carrying tool, field, marker and the offending value, with `str()` byte-identical to today's messages;
  - **public per-field helpers shared by the check and the clip** (for example `check_field(schema, field, tool_val, agent_val, *, tool_name=None)` and `clip_field(...)`), so the next leg's save path calls them instead of re-implementing a marker rule;
  - `ClipResult` (frozen dataclass: `override`, `changes`, each change with `field`, `kind` `narrowed` | `invalid` | `coupled`, `dropped`, `effective`) and `clip_override(schema, tool_config, agent_override) -> ClipResult`;
  - `NarrowSuperset` resolved as app-wide ∪ agent (no longer raises); default-follows-max applied in `resolve` to the merged dict;
  - `resolve(..., *, tool_name: str | None = None)`, an optional keyword so the positional callers (`mcp/_tool_provider.py:158,169`, tests) are unchanged.
- `_web_config.py`: `host_allowlist` carries `NarrowAnyWhenEmpty`; `_url_check` refuses every host when the effective allow list contains `NO_HOSTS`, before any DNS work.
- `builtins.py::get_tools`: each override clipped before `resolve` (which is passed `tool_name=name`); one warning per (agent, tool, field, dropped).
- `api.py`: `x_marker` emits `NarrowAnyWhenEmpty`. `tool-config-fields.js`: `allowed()` accepts it.
- Updated existing tests (the flight's Verification list); new tests below.

## Acceptance Criteria
- [ ] **AC1 — totality (property tests).** For each of `FilesystemConfig`, `ExecutionConfig`, `PythonExecConfig` and `WebConfig`, over seeded generated arbitrary JSON overrides against generated app-wide rows: `clip_override` never raises; `resolve(schema, row, clip_override(...).override)` never raises; no effective field value is wider than the app-wide value, nor wider than the agent's value wherever that value is interpretable (empty `host_allowlist` modelled as the universe); `ClipResult.override` never gains a key the input lacked. Generated inputs include strings for ints, fractional floats, non-lists, non-string entries, `~nosuchuser`, a symlink loop and a NUL byte, in the override **and** in app-wide allow-list entries (an app-wide entry that cannot be canonicalised contains nothing; the clip treats it so rather than raising). A seeded hand-rolled generator (no `hypothesis`; do not add a dependency) with at least a few thousand cases per schema, fast enough for the unit tier (a few seconds in total).
- [ ] **AC2 — the clip table.** One unit test per row of DD2's table, plus: agent `~` with the app-wide list tightened to `~/work` gives `~/work`; an allow list emptied by bad entries gives `[]` (paths) or `[NO_HOSTS]` (hosts), never inherit; a non-list value on an allow-list field clips to its strictest value and on a deny-list field drops the key; `timeout_seconds_max` lowered below an inherited default lowers the effective default (kind `coupled`, never written to the override); an own default above a tightened max is lowered (kind `narrowed`); legacy data with an own default above the agent's own max clips the default to that max (kind `invalid`).
- [ ] **AC3 — union and any-when-empty.** `NarrowSuperset` resolves to app-wide ∪ agent and never raises; a stored legacy full union resolves to the same set; `host_allowlist` empty means "any host" on both sides; a list containing `NO_HOSTS` always fits; agent `[]` against a non-empty app-wide list resolves to the app-wide list, so the live "any host" hole is closed.
- [ ] **AC4 — `NO_HOSTS` with no DNS.** `_url_check` refuses every URL when the effective allow list contains `NO_HOSTS`, proven by a test that fails if any resolver call is made (monkeypatch `socket.getaddrinfo` and any async resolver the check uses to raise).
- [ ] **AC5 — the build never fails on an override.** `AgentFactory.create` succeeds for an agent whose stored override widens the current app-wide row (the charter's case: an agent `path_allowlist` entry outside the app-wide `~`); the tool gets the clipped config; exactly one warning is logged per (agent, tool, field, dropped) across repeated builds.
- [ ] **AC6 — strict `resolve` keeps its contract.** `resolve` still raises on a widening or invalid override, now as `OverrideWidensError` (a `ValueError`) with the tool when `tool_name` is passed, with unchanged message text; MCP's Substitute-only use and its tests are unchanged; a test pins that `get_tools` passes `tool_name`.
- [ ] **AC7 — marker on the wire.** `x_marker` for `host_allowlist` is `NarrowAnyWhenEmpty`; the agent tab still renders, edits and saves that field (an existing `agent-tabs` browser test covering web-tool overrides stays green, or one is added).
- [ ] **AC8 — no regressions.** `THE_ONE_TEST_NETNS=1 make test-unit` shows only the baseline failures; the `agent-tabs` and `settings-tools` lanes show only baseline failures; ruff check and format are clean; the static JS guards pass.

## Verification Steps
- AC1-AC3, AC6: new `tests/test_resolver_clip.py` (clip table and property tests) and updates to `tests/test_resolver.py`, `tests/test_filesystem_config.py`, `tests/test_execution_config.py`, `tests/test_web_config.py`, `tests/test_agent_tool_overrides_round_trip.py`: `PYTHON=.venv/bin/python bash scripts/run-tests.sh <files> -x --timeout 60`.
- AC4: a test in `tests/test_web_config.py` (or `test_web_helpers.py`) with the resolver monkeypatched to raise.
- AC5: a factory test (`tests/test_factory*.py` or new) with a widening stored override and `caplog`.
- AC7: `tests/test_api_tool_configs.py`, `tests/test_enrich_schema_with_markers.py`; `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane agent-tabs`.
- AC8: `THE_ONE_TEST_NETNS=1 make test-unit`; `--lane settings-tools`; `ruff check` and `ruff format --check` on `the_one/ tests/ scripts/ evals/`; `tests/test_ui_guards.py`, `tests/test_token_definitions.py`, `tests/test_design_tokens_a11y.py`.

## Implementation Guidance

1. **Markers, constant, error.** Add `NarrowAnyWhenEmpty` and `NO_HOSTS` beside the other markers (the import direction stays `_web_config`/`execution` → `resolver`). Add `OverrideWidensError(ValueError)`; the `_check_*` helpers raise it.
2. **Per-field helpers first.** Write one check and one clip per marker, sharing their interpretation code (canonicalisation, IDNA-free host comparison for now: leg `redirect-hosts` adds the one host normaliser), and a public `check_field` / `clip_field` dispatch on the field's marker. `resolve` and `clip_override` both go through them. The next leg's save validation will call `check_field` per changed field and then `resolve` over the merged config for cross-field rules, so give `check_field` a return or exception shape that carries the field name.
3. **`resolve`.** Optional `tool_name` keyword; union for `NarrowSuperset`; default-follows-max on the merged dict, only when the agent did not set the default (DD2).
4. **`clip_override` / `ClipResult`.** Total: catch `RuntimeError`, `OSError` and `ValueError` around every canonicalisation (the agent's entries and the app-wide entries); never add a key; `coupled` is report-only.
5. **`_url_check` and `NO_HOSTS`.** First-URL path only, before DNS.
6. **Build path.** `get_tools` clips each override, then `resolve(..., tool_name=name)`. The warning de-duplication is a bounded module-level set (cap it; on overflow, clear it).
7. **Wire and client.** `x_marker` (`api.py:490-540`) and `allowed()` (`tool-config-fields.js:81-86`) in this leg.
8. **Existing tests** listed under the flight's Verification ("Existing tests that change") and the marker references in `tests/browser/seeders.py`: update them here. Rename a test whose intent flips (for example "raises on a dropped default denied entry" → "unions a dropped default denied entry") rather than delete-and-add.

## Edge Cases
- **`FilesystemConfig.model_post_init`** appends the secrets dir to the private `_canonical_denylist` only (`filesystem.py:160-173`), never to the field, so the union and the clip, which work on raw field values, need no special case for it.
- **A legacy app-wide row that is itself bad** (for example a `~nosuchuser` deny entry, which `model_post_init` raises on at build): out of scope for this sortie (it is the operator's own row, and the Settings PUT validates it); the clip must still not raise on it.
- **Symlink-loop test fixtures** live under `tmp_path` (the bwrap `/tmp` quirk applies only to `requires_bwrap` tests).
- **`PythonExecConfig`** is a second execution schema with the same fields: cover it in the property and table tests.
- **`redirect_cap` and `WebSearchConfig` fields** (unmarked): `resolve` still raises on them; the clip drops them (kind `invalid`).

## Files Affected
- `the_one/tools/resolver.py` — markers, constant, error, per-field helpers, clip, union, coupling
- `the_one/tools/_web_config.py` — `host_allowlist` marker; `NO_HOSTS` in `_url_check`
- `the_one/tools/builtins.py` — clip before resolve; warning
- `the_one/interfaces/web/api.py` — `x_marker`
- `the_one/interfaces/web/static/js/areas/shared/tool-config-fields.js` — `allowed()`
- Tests: new `tests/test_resolver_clip.py`; updates per the flight's Verification list

### Citation Audit
Checked by the Flight Director against the worktree at `628a97dd` (2026-10-31) and by the design review: `resolver.py` (unchanged since planning), `builtins.py:140-205`, `_web_config.py:350`, `filesystem.py:160-173`, `api.py:490-540`, `tool-config-fields.js:81-86`, `mcp/_tool_provider.py:158,169`. The marked-field list was measured by introspecting `_TOOL_CLASSES`.

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
