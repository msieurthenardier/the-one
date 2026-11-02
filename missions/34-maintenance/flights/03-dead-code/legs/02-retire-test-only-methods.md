# Leg: retire-test-only-methods

**Status**: completed
**Flight**: [Dead code](../flight.md)

## Objective
Delete `Encryptor.rotate_key` and `ToolConfigRepository.list_all`, which only tests call, and move every property their tests alone pinned onto tests of the live code, so coverage does not drop.

## Context
- Flight Technical Approach step 2; mission criterion "Dead code removed" (#25, the two settled items). Mission constraint: no coverage loss — a test may be removed only when another test fails on the same regression; each removal is named in the flight log with the test that covers it.
- **`Encryptor.rotate_key`** (`the_one/encryption.py:198`): stage a new key (`stage_pending_key`), run a re-encrypt callback, `discard_pending_key` on any exception, else `promote_pending_key`. No production caller: the route `api.py::rotate_encryption_key` runs its own sequence on the same primitives, tested by `tests/test_provider_api.py::…::test_rotate_key` and the `test_rotate_*` route tests, and `tests/test_key_reconcile.py`. Its tests in `tests/test_encryption.py`:
  - `TestGetEncryptor::test_rotation_propagates_through_cache` (`:93`) — after a rotation, the cached instance (`get_encryptor` returns the same object) encrypts/decrypts with the new key. **Property to keep:** in-place install — the instance `get_encryptor` caches sees a promoted key. Move it onto `stage_pending_key` + `promote_pending_key` called directly on the cached instance.
  - `TestKeyRotation` (`:151-215`): `test_rotated_key_file_permissions` (0o600 after rotation; **keep**: assert the promoted key file is 0o600 after `promote_pending_key`, beside `test_stage_writes_sidecar_at_0600` `:225` and `test_promote_replaces_file_and_drops_fallback` `:256`), `test_rotation_generates_different_key`, `test_rotation_calls_callback`, `test_new_encryptor_decrypts_new_values`, `test_old_values_fail_after_rotation` (properties of the promote: the key file content changes, old ciphertext no longer decrypts once the fallback is dropped — check whether `test_promote_replaces_file_and_drops_fallback` already pins these; add what it does not), `test_rotation_preserves_key_on_callback_failure` (a `discard_pending_key` property: the key file and in-memory key are unchanged after discard — check the existing discard tests; add one if none), `test_rotation_without_key_path_raises` (a `rotate_key`-only guard; check whether `stage_pending_key` has the same guard and a test — if it does, the property is covered; if it has the guard but no test, add one; if it has no guard, the property disappears with the method and that is recorded).
  - `the_one/api_credential.py:172` docstring mentions "that module's `rotate_key` / `get_encryptor`": reword it to name what is still there.
  - Also grep `docs/`, `the_one/agents.md`, `SECURITY-MODEL.md` and CLAUDE.md for `rotate_key` prose and update it.
- **`ToolConfigRepository.list_all`** (`the_one/db/repositories.py:2463`; class docstring `:2433` says it is "a convenience read returning `{name: config_dict}`" for the resolver). The factory reads `list()` (`agent/factory.py` around `:396-402`, whose comment also mentions `list_all()`). Its consumers are tests:
  - `tests/test_db_repositories.py:2774-2786` (`list_all` returns `{name: config}` and `{}` when empty) and `:2855-2858` (the "resolver-facing list_all must stay {name: config_dict}" check after an enable toggle). Re-point each at `list()`, asserting the same rows through `list()`'s shape; rename the tests (rename over delete-and-re-add) so their names no longer say `list_all`.
  - `tests/test_factory.py:123` comment mentioning `list_all()`'s shape: reword.
  - **`tests/test_factory_disable_enforcement.py::test_factory_does_not_call_list_all` (`:313-375`)** spies on `list_all` to prove the factory never calls it. With the method gone that regression cannot happen, so the spy has no target. **Invert, don't delete:** rename it to state the live contract — the factory's tool-config read goes through `ToolConfigRepository.list()` (spy `list` and assert it is called on the factory path) — keeping its setup. Update the comment at `:265`.
  - Update the `agent/factory.py` comment and the `repositories.py` class docstring.
  - **`tools/resolver.py`:** the flight left it to sortie 07 (now merged, `ae2296f1`) or squawk 0296 (completed). Grep it for `list_all`; at design time `resolver.py:1-10` no longer mentions it. If any mention remains, update it in this leg (sortie 07 has landed, so the collision the flight avoided is gone) and record it.
- **Verification set that must stay green and unchanged:** the route rotation tests (`tests/test_provider_api.py` `test_rotate_*`) and `tests/test_key_reconcile.py`.

## Design Review
2026-11-02, Developer (Sonnet), cycle 1: **approve with changes** (applied; no second cycle, the mechanism is unchanged). The Context's coverage inventory was partly wrong; this table supersedes it:

| Removed test | Disposition |
|---|---|
| `test_rotation_propagates_through_cache` | **New test**: `enc = get_encryptor(tmp)`, `ct_old = enc.encrypt(...)`, `stage_pending_key(new)`, `promote_pending_key()`; assert `get_encryptor(tmp) is enc`, `Fernet(new).decrypt(enc.encrypt("x"))` works (an independent `Fernet`, not `enc`), `ct_old` raises `InvalidToken`; optionally clear `_encryptor_cache` and re-fetch to prove the file holds the new key. |
| `test_rotated_key_file_permissions` | **New test** (posix `skipif`, as `test_stage_writes_sidecar_at_0600`): the canonical `encryption.key` is 0o600 after `promote_pending_key`. No existing test checks the final path's mode. |
| `test_rotation_generates_different_key` | Covered by `test_promote_replaces_file_and_drops_fallback` (file equals the new key). Optionally assert the bytes differ from before. |
| `test_rotation_calls_callback` | **Property removed with the method** (the callback contract belongs only to `rotate_key`; the route tests cover the real re-encrypt sequence). |
| `test_new_encryptor_decrypts_new_values` | **Extend** `test_promote_replaces_file_and_drops_fallback`: `enc.decrypt(Encryptor(new_key).encrypt("x")) == "x"` after promote. |
| `test_old_values_fail_after_rotation` | Covered by `test_promote_replaces_file_and_drops_fallback` (`InvalidToken` on old ciphertext). |
| `test_rotation_preserves_key_on_callback_failure` | **Extend** `test_discard_unlinks_and_drops_pending`: read the canonical key file's bytes before stage and assert them unchanged after discard. |
| `test_rotation_without_key_path_raises` | **New tests** for the untested guards: `stage_pending_key` on `Encryptor(Fernet.generate_key())` raises `RuntimeError` matching "no key_path set"; and `promote_pending_key(explicit_key)` on a key-path-less instance raises the same (pass the key so the "no pending key" check does not fire first). |

Further changes from the review:
- **`encryption.py:8`** imports `Callable` only for `rotate_key`: change it to import just `Iterable`, or ruff fails F401.
- **`tests/test_factory.py` has two stale mentions**: the comment at `:123` and a docstring around `:487` ("await list_all(), and pass that dict"). Fix both.
- **Factory test inversion (AC4), concretely:** `test_factory_does_not_call_list_all` already spies `real_repo.list` and asserts `list_calls == 1`. Delete the `list_all` spy (`original_list_all`, `tracked_list_all`, the `real_repo.list_all =` patch, the `list_all_calls == 0` assert), keep the `list_calls == 1` assert, rename (e.g. `test_factory_reads_tool_configs_through_list_once`), and rewrite its docstring and the comments at `:265` and `:329`. Falsify by making the factory call `list()` twice (not skip it, which may break `create()` earlier).
- **Repo tests:** re-point and rename all three — `:2771` (compare `{i.name: i.config for i in await repo.list()}` to the expected configs), `:2783` (`await repo.list() == []`, or record it as covered if an empty-list `list()` test exists) and `test_list_all_omits_enabled` (`:2854`): keep its property as `"enabled" not in item.config` and `item.enabled is False` through `list()`.
- **Docstrings and comments:** rewrite `repositories.py:2433-2436` as a whole sentence (keep "the resolver makes no repository call"); rewrite the `factory.py:394-400` comment coherently (it names `list_all()` twice and the renamed `test_list_all_omits_enabled`); `api_credential.py:172` — name `_write_key_atomic` / `get_encryptor` and drop the stale "out of scope for this leg" clause.
- No `rotate_key`/`list_all` prose in agents.md, SECURITY-MODEL.md, docs, scripts, evals or CLAUDE.md; `resolver.py` already says the factory reads `list()`. Historical mission artifacts are left alone.
- Optional: a primitive-level `install_key` then `promote_pending_key(explicit)` test (the route's path).

## Inputs
- Leg 1 landed (independent files).

## Outputs
- `the_one/encryption.py` without `rotate_key`; `the_one/db/repositories.py` without `list_all`; docstrings and comments updated (`api_credential.py`, `factory.py`, `repositories.py`, any docs).
- `tests/test_encryption.py`: `TestKeyRotation` and `test_rotation_propagates_through_cache` removed, each property moved per Context; `tests/test_db_repositories.py` and `tests/test_factory_disable_enforcement.py` re-pointed and renamed; `tests/test_factory.py` comment.
- Flight log: a table, one row per removed test, naming the test that now covers its property (or "property removed with the method", with the reason).

## Acceptance Criteria
- [ ] **AC1 — methods gone.** `grep -rnE --exclude-dir={.claude,.git,.venv,missions,maintenance,squawks,sorties} '\brotate_key\b|\blist_all\b' the_one tests docs scripts evals CLAUDE.md SECURITY-MODEL.md` returns only known non-references, each named in the flight log: the route test `test_rotate_key` in `tests/test_provider_api.py` (a route test, stays). (Word boundaries keep `test_coerce_stop_list_all_entries_dropped_none` in `tests/test_request_params.py` out of the match.)
- [ ] **AC2 — coverage moved** (per the Design Review table below). Each property in Context is asserted by a test of the live primitives: the promoted key file is 0o600; the cached `get_encryptor` instance sees a promoted key in place; promote changes the key and drops the old key's fallback; discard leaves the key file and the in-memory key unchanged; the key-path guard (if the primitive has one). Each new or extended test is falsified (break the primitive's property by editing, see the test fail, restore by editing) and reported yes/no.
- [ ] **AC3 — no coverage loss recorded.** The flight log table names, for every removed or renamed test, the test that covers its regression.
- [ ] **AC4 — inverted factory test.** The renamed factory test asserts the factory reads tool configs through `list()`; falsified by making the factory skip the call (by editing), then restored.
- [ ] **AC5 — unchanged verification set.** `tests/test_provider_api.py` rotation tests and `tests/test_key_reconcile.py` pass with no edits to those files.
- [ ] **AC6 — suites.** `THE_ONE_TEST_NETNS=1 make test-unit` passes with the same 15 skips; ruff check and format clean; `uvx vulture the_one/ --min-confidence 60` does not list either method (skip if `uvx` is offline, and record that).

## Verification Steps
- AC1: the grep. AC2/AC4: run each test, falsify, restore. AC3: read the flight log. AC5: `git diff --stat` shows no change to the two files, and they pass. AC6: the commands.

## Implementation Guidance
1. Read `the_one/encryption.py` (the pending-key primitives) and the existing primitive tests in `tests/test_encryption.py` (`:220-360`) before deleting anything; list which `TestKeyRotation` properties are already covered.
2. Write the moved tests first and see them pass against the current code; falsify each; then delete `rotate_key` and its tests.
3. Re-point and rename the `list_all` tests, invert the factory test, then delete `list_all`.
4. Update docstrings, comments and any docs; run the suites.

## Edge Cases
- The `get_encryptor` cache is per data dir; the moved in-place test must use the cached instance, not a fresh `Encryptor(key)`.
- `promote_pending_key` may fsync and replace atomically; assert the mode on the final path, not the sidecar.
- `tests/test_factory_disable_enforcement.py` may monkeypatch the repository class or instance; keep the same scope when spying `list()`.

## Files Affected
- `the_one/encryption.py`, `the_one/api_credential.py`, `the_one/db/repositories.py`, `the_one/agent/factory.py`, possibly `the_one/tools/resolver.py` and docs
- `tests/test_encryption.py`, `tests/test_db_repositories.py`, `tests/test_factory_disable_enforcement.py`, `tests/test_factory.py`
- the flight log

## Citation Audit
Checked at `de03e35f` (Flight Director, 2026-11-02): `encryption.py::Encryptor.rotate_key` :198 (stage → callback → discard on exception / promote) — verified; callers only `tests/test_encryption.py` :96, :161-195 — verified; `api_credential.py:172` mentions `rotate_key` — verified; `repositories.py` `list_all` :2463 with class docstring :2433 — verified (flight said :2462); consumers `tests/test_db_repositories.py` :2774-2786 and :2855-2858, `tests/test_factory_disable_enforcement.py` :265 and :313-375, `tests/test_factory.py:123` (comment), `agent/factory.py:396-398` (comment) — verified; `tests/test_encryption.py` primitive tests `test_stage_writes_sidecar_at_0600` :225, `test_promote_replaces_file_and_drops_fallback` :256 — verified. Not in the flight's table: `tests/test_factory_disable_enforcement.py::test_factory_does_not_call_list_all`, which the leg inverts.
