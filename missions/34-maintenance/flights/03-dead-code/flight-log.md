# Flight Log: Dead code

**Flight**: [Dead code](flight.md)

## Summary
Landed 2026-11-02 on branch `flight/03-dead-code` (base `de03e35f`). Both legs completed:
- **Leg 1** deleted 11 dead items: `scripts/entrypoint.sh`, `_tool_read_file`, `VALID_ROUTING_SCOPES`, `UV_ENVIRONMENTS_ROOT`, `SEARCH_BACKENDS`, the `.self-configuration-toggle-switch` rule, the `make_registry` fixture and its CLAUDE.md bullet, the `App.studio.AGENT_PANEL_IDS` export, `NO_SLEEP_HOOKS`, `_MISSING`, `_origin`, plus imports left unused. Each was re-grepped before deletion. It kept `badge--local`/`badge--remote` and `ui-list-pane-compact`, which factories can still produce.
- **Leg 2** retired `Encryptor.rotate_key` and `ToolConfigRepository.list_all`. Their coverage moved to the live primitives: in-place cache promotion, 0o600 on the promoted file, and both key-path guards. The `list_all` tests and the factory spy test were renamed and re-pointed at `list()`. Only the `rotate_key` callback contract disappeared with the method.

Gates: `THE_ONE_TEST_NETNS=1 make test-unit` 8603 passed, 15 skipped (net −4, as expected); the `agents` lane passed; static guards and ruff clean; flight Reviewer (Sonnet) confirmed with no issues.

---

## Leg Progress

### Leg 1 — definite-dead-sweep

Grep used before each deletion (and again after): `grep -rn --exclude-dir={.claude,.git,.venv,missions,maintenance,squawks,sorties,node_modules} -e '<name>' .`. Every item showed only its definition (plus the listed exceptions).

| Item | Pre-deletion grep result | Outcome |
|---|---|---|
| `scripts/entrypoint.sh` | `'entrypoint.sh'`: no hits anywhere (no `.dockerignore`/packaging glob) | `git rm` |
| `ui_capture.py::_tool_read_file` | only `:750` definition | deleted |
| `models.py::VALID_ROUTING_SCOPES` | only `:189` definition (and its two-line comment) | deleted with comment |
| `cache_cleanup.py::UV_ENVIRONMENTS_ROOT` | `:62` comment + `:68` definition | deleted; the comment existed only for it, so removed. Kept the "Filesystem roots — module-level so tests can monkeypatch." line for `NPX_CACHE_ROOT` |
| `_search_backends.py::SEARCH_BACKENDS` | only `:539` definition | deleted; its comment reworded to describe the factory (no orphaned "Keyed by" text) |
| `studio.css` `.self-configuration-toggle-switch` | CSS rule only; JS has only `self-configuration-toggle-btn` testid, no string-building of `-switch` | deleted with its comment |
| `conftest.py::make_registry` | `:227` def + CLAUDE.md bullet; all other hits are the private `_make_registry` helpers (kept) | deleted; the `ToolRegistry` import in conftest became unused (ruff F401) and was dropped; CLAUDE.md "Test patterns" bullet removed |
| `agent-editor.js` `AGENT_PANEL_IDS` | only the export line; `PANEL_IDS` is used in-module (`:52-53`) | export line deleted only |
| `_evals_helpers.py::NO_SLEEP_HOOKS` | only definition (`Any` import still used) | deleted |
| `_mcp_signin_helpers.py::_MISSING` | `\b_MISSING` only definition in tests; other hits are unrelated `*_MISSING*` names | deleted |
| `_nav.py::_origin` | `-w _origin` only definition | deleted; `urlsplit` import became unused and was dropped |

Two ruff-format spacing fixes (two blank lines) made by hand in `_mcp_signin_helpers.py` and `_search_backends.py` after the deletions.

**CSS variants (AC3)**
- `badge--local`, `badge--remote`: **kept**. Producer: `library-pane.js:260` sets `kind: isLocal ? 'local' : 'remote'` on the MCP source row badge, and `ui/feedback.js:36/62` builds `'badge badge--' + kind`. Their `--badge-*` tokens stay with them.
- `ui-list-pane-compact`: **kept**. Producer: `ui/list-pane.js:197/211` builds `'ui-list-pane-' + density`, with `density: 'compact'` a documented option (`docs/ui-control-inventory.md`); no current call site passes it, but an option value can produce it, so the leg's rule says leave it. Noted as a candidate for a future API-trim decision, not dead CSS.

**Vulture (AC6)** `uvx vulture the_one/ evals/ scripts/ --min-confidence 60`: 252 lines before, 248 after. The four Python items (`_tool_read_file`, `VALID_ROUTING_SCOPES`, `UV_ENVIRONMENTS_ROOT`, `SEARCH_BACKENDS`) were listed before and are gone after.

**Tests**: guards (`test_ui_ownership`, `test_ui_emitted_classes`, `test_ui_control_inventory`, `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`) 446 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 8607 passed, 15 skipped. `ruff check` and `ruff format --check` clean. No tests were removed (the deleted fixture/constants had no users), so no coverage changed. `agents` lane (`THE_ONE_TEST_NETNS=1`): 180 passed. No `components.css` class deleted, so the contracts lanes were not required.

### Leg 2 — retire-test-only-methods

Deleted `Encryptor.rotate_key` (and the now-unused `Callable` import) and `ToolConfigRepository.list_all`; reworded `api_credential.py:172`, the `repositories.py` class docstring and the `factory.py` comment. `resolver.py` had no mention left. No `rotate_key`/`list_all` prose in docs, agents.md, SECURITY-MODEL.md or CLAUDE.md.

**No-coverage-loss table**

| Removed / renamed test | Now covered by | Falsified |
|---|---|---|
| `TestGetEncryptor::test_rotation_propagates_through_cache` | new `test_promotion_propagates_through_cache` (stage + promote on the cached instance; independent `Fernet(new)` decrypts; old ciphertext fails; fresh instance re-reads the file) | yes (removed `install_key` in promote: fails) |
| `test_rotated_key_file_permissions` | new `TestPendingKey::test_promoted_key_file_permissions` (final path 0o600 after promote) | yes (chmod 0o644 after replace: fails) |
| `test_rotation_generates_different_key` | extended `test_promote_replaces_file_and_drops_fallback` (file equals new key, differs from before) | covered by the same falsification as below |
| `test_rotation_calls_callback` | property removed with the method (the callback contract existed only in `rotate_key`; the route's re-encrypt sequence is covered by `test_provider_api.py::test_rotate_*` and `test_key_reconcile.py`) | n/a |
| `test_new_encryptor_decrypts_new_values` | extended `test_promote_replaces_file_and_drops_fallback` (`enc.decrypt(Encryptor(new).encrypt(..))`) | yes (removed `install_key`: fails) |
| `test_old_values_fail_after_rotation` | already in `test_promote_replaces_file_and_drops_fallback` (`InvalidToken`) | existing |
| `test_rotation_preserves_key_on_callback_failure` | extended `test_discard_unlinks_and_drops_pending` (canonical key file bytes unchanged, old ciphertext still decrypts) | yes (discard also unlinks the key file: fails) |
| `test_rotation_without_key_path_raises` | new `test_stage_without_key_path_raises` and `test_promote_without_key_path_raises` (both guards were untested) | yes (removed each guard: its test fails) |
| `test_list_all_returns_dict_shape` | renamed `test_list_carries_each_rows_config` (through `list()`) | yes |
| `test_list_all_empty_when_no_rows` | renamed `test_list_empty_when_no_rows` (`list() == []`) | no (trivial) |
| `test_list_all_omits_enabled` | renamed `test_list_omits_enabled_from_config` (`enabled` not in `config`, `item.enabled is False`) | yes (put `enabled` into `config` in `_row_to_model`: fails) |
| `test_factory_does_not_call_list_all` | inverted to `test_factory_reads_tool_configs_through_list_once` (spy on `list`, count == 1) | yes (factory calls `list()` twice: fails) |

After each `encryption.py` falsification the file was restored by editing; `git diff -- the_one/encryption.py` shows only the `rotate_key` and `Callable` deletions.

**AC1 grep** (`\brotate_key\b|\blist_all\b` over the_one, tests, docs, scripts, evals, CLAUDE.md, SECURITY-MODEL.md): no output. The route test `test_rotate_key` in `tests/test_provider_api.py` does not match (underscore is a word character) and is unchanged, as is `tests/test_key_reconcile.py` (AC5: no diff).

**Checks**: `ruff check` and `ruff format --check` clean. `THE_ONE_TEST_NETNS=1 make test-unit`: 8603 passed, 15 skipped (8607 less the four removed `TestKeyRotation`-era tests net of additions: 8 removed, 4 added). `uvx vulture the_one/ --min-confidence 60`: neither `rotate_key` nor `list_all` listed.

---

## Decisions

---

### Flight Director Notes

- 2026-11-02: phase file `.flightops/agent-crews/leg-execution.md` loaded (valid). Flight `ready` → `in-flight`; branch created from `de03e35f` (Flight 2 merged). Prerequisite ("green `make test-unit` at leg start") rests on the Flight 2 debrief's fresh unit run on the same code (8607 passed, 15 skipped under netns); each leg runs it again at its end.
- Both legs designed together; every sweep item and both methods re-grepped at `de03e35f` (excluding `.claude/`, `.git/`, `.venv/` and planning artifacts). All still dead. New finding: `tests/test_factory_disable_enforcement.py::test_factory_does_not_call_list_all` spies on `list_all`, so Leg 2 inverts it rather than deleting it.
- Leg 1 `definite-dead-sweep` tiered **low-risk**: deletions of items with no reference, inside established guards (UI ownership/emitted-class/inventory guards, the unit suite, the `agents` lane). No design review; the flight Reviewer covers it.
- Leg 2 `retire-test-only-methods` tiered **high-risk**: it touches key-rotation code (`the_one/encryption.py`, key material — a security-sensitive surface), removes tests under the no-coverage-loss constraint and inverts a test that pins factory behaviour. Design review by a Developer (Sonnet), run while Leg 1 is implemented (Leg 2's files do not overlap Leg 1's).
- Leg 2 design review cycle 1 (Developer, Sonnet): approve with changes, all applied — a per-test coverage table (4 new or extended primitive tests, 1 property removed with the method: the `rotate_key` callback contract), the `Callable` import, a second stale mention in `tests/test_factory.py`, the concrete factory-test inversion, the `enabled`-not-in-config property kept, a word-bounded AC1 grep. No second cycle: no design change. Leg 2 → `ready`.
- Leg 2 landed. Unit count 8607 → 8603 is the expected net −4 (`TestKeyRotation`'s 7 tests and `test_rotation_propagates_through_cache` removed, 4 primitive tests added; the 3 `list_all` repo tests and the factory test renamed, not removed). The Developer set the leg status line with `sed -i` (an artifact, not a source or test file; recorded). Flight review: Reviewer on **Sonnet** (key-rotation code in `the_one/encryption.py` is a security-sensitive surface). Accessibility Reviewer **skipped**: no user-facing change (Leg 1 deleted an unemitted CSS rule and an unread JS export; nothing renders differently).
- Flight review cycle 1: Reviewer (Sonnet) **[HANDOFF:confirmed]**, no issues (independent re-grep of every deleted name; `encryption.py` primitives unchanged; 8603 passed, 15 skipped).
