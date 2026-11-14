# Squawk 0358: four script-safety tests fail in a checkout without its own .venv

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-13
**Completed**: —

## Report
In a git worktree with no `.venv` of its own, four unit tests fail, although the behaviour they test is unaffected. Each expects a specific refusal (a bad setup script, handler name, flag combination or protected port). Before that check runs, the script derives the default data directory from `<checkout>/.venv/bin/python` and refuses when it is missing:
- `tests/test_webkitgtk_probe_safety.py::test_main_refuses_missing_setup_script_without_gtk`
- `tests/test_webkitgtk_probe_safety.py::test_main_refuses_a_bad_handler_name_before_any_gtk`
- `tests/test_webkitgtk_probe_safety.py::test_main_refuses_a_bad_combo_before_any_gtk`
- `tests/test_ui_capture_safety.py::test_keep_running_refuses_a_protected_port`

Error: `cannot derive the default data dir: <checkout>/.venv/bin/python missing (refusing to run unverified)`.

Reproduce: from a worktree without `.venv`, run `/path/to/main/.venv/bin/python -m pytest tests/test_webkitgtk_probe_safety.py tests/test_ui_capture_safety.py -q`.

Expected: these tests pass in any checkout. They should stub the data-dir derivation, the way a neighbouring test already does (`monkeypatch.setattr(cap, "default_data_dir", ...)` in `tests/test_ui_capture_safety.py`). The scripts' own refusal when the venv is missing is a deliberate safety guard and must not be weakened.

## Evidence
- `scripts/webkitgtk_probe.py:51` — `VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"`. `default_data_dir()` (line 65) raises `ProbeError` when it does not exist. `scripts/ui_capture.py:232` `default_data_dir()` has the same dependency.
- `tests/test_webkitgtk_probe_safety.py:78-90` asserts `"not an existing file"` in stderr, but gets the missing-venv refusal instead.
- `tests/test_ui_capture_safety.py:120-124` matches `8484`, but gets the missing-venv refusal instead.
- Seen in the sortie 15 unit runs (2026-11-13, worktree `/home/cprch/projects/the-one-notes-prompt-wording`): 10122 and 10137 passed, with these four failing each time. They pass in the main checkout, which has `.venv`.

## Corrective Action
*(written at completion)*

## Verification
*(written at completion)*
