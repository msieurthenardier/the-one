"""Unit tests for the Windows test-copy helper's pure core (M25 F5 L1a).

No Windows access: process tables are plain dicts, paths are strings, and the
helper imports on Linux (every ctypes.windll / winreg use is lazy).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_PATH = Path(__file__).parent.parent / "scripts" / "windows_test_copy.py"
_SPEC = importlib.util.spec_from_file_location("windows_test_copy", _PATH)
h = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(h)

LOCAL = "C:\\Users\\cprch\\AppData\\Local"
OPERATOR = LOCAL + "\\the-one"
ROOT = LOCAL + "\\Temp\\the-one-f5"


def test_base_python_matches_requires_python() -> None:
    """The setup venv's base interpreter must satisfy pyproject's requires-python
    (squawk 0343: it was hard-coded to 3.11 while the project needs 3.12)."""
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text()
    m = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', pyproject)
    assert m, "requires-python not found"
    floor = f"{m.group(1)}{m.group(2)}"
    assert h.BASE_PYTHON_DIR.endswith(f"Python{floor}")
    assert h.PYTHON_WIN.endswith(f"Python{floor}/python.exe")


# ---------------------------------------------------------------- ports


@pytest.mark.parametrize(
    ("port", "kind"),
    [(8484, "app"), (8485, "app"), (8489, "app"), (9389, "cdp"), (8484, "cdp"), (8485, "cdp")],
)
def test_ports_refused(port: int, kind: str) -> None:
    with pytest.raises(h.HelperError) as e:
        h.check_port(port, kind, [], set())
    assert e.value.code == 2


@pytest.mark.parametrize(("port", "kind"), [(8490, "app"), (9390, "cdp"), (8499, "app")])
def test_ports_accepted_when_free(port: int, kind: str) -> None:
    h.check_port(port, kind, [(50000, 50059)], {1234})


def test_port_in_excluded_range_refused() -> None:
    with pytest.raises(h.HelperError, match="excluded range"):
        h.check_port(8495, "app", [(8490, 8499)], set())


def test_busy_port_refused() -> None:
    with pytest.raises(h.HelperError, match="listening"):
        h.check_port(8490, "app", [], {8490})


def test_parse_excluded_and_listeners() -> None:
    text = (
        "Start Port  End Port\n----------  --------\n"
        "      5357        5357\n     50000       50059     *\n"
    )
    assert h.parse_excluded_ranges(text) == [(5357, 5357), (50000, 50059)]
    assert h.parse_listeners("0.0.0.0|8484|99\nbad\n::|9390|7") == [
        {"addr": "0.0.0.0", "port": 8484, "pid": 99},
        {"addr": "::", "port": 9390, "pid": 7},
    ]


# ---------------------------------------------------------------- paths

OPERATOR_FORMS = [
    "C:\\Users\\cprch\\AppData\\Local\\the-one",
    "c:/users/cprch/appdata/local/the-one",
    "/mnt/c/Users/cprch/AppData/Local/the-one",
    "\\\\?\\C:\\Users\\cprch\\AppData\\Local\\the-one",
    "C:\\Users\\cprch\\AppData\\Local\\Temp\\..\\the-one",
    "C:\\Users\\cprch\\AppData\\Local\\the-one.",
    "C:\\Users\\cprch\\AppData\\Local\\the-one ",
    "C:\\Users\\cprch\\AppData\\Local\\the-one\\",
    "C:/Users\\cprch/AppData\\Local/THE-ONE",
    "C:\\Users\\cprch\\AppData\\Local\\the-one\\webview\\x",
    "/mnt/c/Users/cprch/AppData/Local/the-one/../the-one/logs",
    "\\\\?\\UNC\\localhost\\C$\\x",  # not the operator dir: UNC stays UNC
]


@pytest.mark.parametrize("form", OPERATOR_FORMS[:-1])
def test_data_dir_forms_of_operator_dir_refused(form: str) -> None:
    with pytest.raises(h.HelperError, match="operator's data dir"):
        h.check_data_dir([h.to_win_path(form)], [OPERATOR], [ROOT])


def test_data_dir_containing_operator_dir_refused() -> None:
    with pytest.raises(h.HelperError, match="contains"):
        h.check_data_dir([LOCAL], [OPERATOR], [ROOT])


def test_relative_path_resolves_against_cwd() -> None:
    assert h.to_win_path("..\\the-one", cwd=ROOT + "\\data") == ROOT + "\\the-one"
    with pytest.raises(h.HelperError, match="operator's data dir"):
        h.check_data_dir(
            [h.to_win_path("..\\..\\..\\the-one", cwd=ROOT + "\\data")], [OPERATOR], [ROOT]
        )


def test_wsl_localhost_unc_is_not_a_windows_path_match() -> None:
    p = h.to_win_path("\\\\wsl.localhost\\Ubuntu\\home\\x")
    assert p.startswith("\\\\wsl.localhost")
    with pytest.raises(h.HelperError, match="outside the scratch root"):
        h.check_data_dir([p], [OPERATOR], [ROOT])


def test_sibling_prefix_is_not_containment() -> None:
    assert h.path_overlap(ROOT, OPERATOR) is None
    assert not h.is_within(ROOT, OPERATOR)
    assert not h.is_within(OPERATOR + "x", OPERATOR)


def test_allowed_inside_the_root() -> None:
    for d in (ROOT + "\\data-l1a", "/mnt/c/Users/cprch/AppData/Local/Temp/the-one-f5/data-x"):
        h.check_data_dir([h.to_win_path(d)], [OPERATOR], [ROOT])


def test_data_dir_outside_root_refused() -> None:
    with pytest.raises(h.HelperError, match="outside the scratch root"):
        h.check_data_dir([LOCAL + "\\Temp\\other"], [OPERATOR], [ROOT])


def test_resolved_form_of_a_junction_is_checked() -> None:
    # The target looks like a scratch dir lexically but resolves to the operator's dir.
    with pytest.raises(h.HelperError, match="operator's data dir"):
        h.check_data_dir([ROOT + "\\data", OPERATOR + "\\logs"], [OPERATOR], [ROOT])


def test_root_validation() -> None:
    assert h.validate_root(ROOT, LOCAL, [OPERATOR]) == ROOT
    assert h.validate_root("/mnt/c/Users/cprch/AppData/Local/Temp/the-one-f5-x", LOCAL, [OPERATOR])
    for bad in (
        "C:\\the-one-f5",  # outside Temp
        LOCAL + "\\the-one-f5",  # outside Temp
        LOCAL + "\\Temp\\other",  # wrong leaf
        LOCAL + "\\Temp",  # Temp itself
        OPERATOR,  # the operator's data dir
        LOCAL,  # an ancestor of it
    ):
        with pytest.raises(h.HelperError):
            h.validate_root(bad, LOCAL, [OPERATOR])
    with pytest.raises(h.HelperError, match="operator's data dir"):
        h.validate_root(ROOT, LOCAL, [ROOT + "\\data"])


def test_assert_within_for_writes() -> None:
    h.assert_within(ROOT + "\\src\\a.py", ROOT)
    with pytest.raises(h.HelperError, match="outside the scratch root"):
        h.assert_within(OPERATOR + "\\x", ROOT)
    with pytest.raises(h.HelperError):
        h.assert_within(ROOT + "-evil\\x", ROOT)


# ---------------------------------------------------------------- process identity


def proc(pid, ppid, create, path, cmd=""):
    return {"pid": pid, "ppid": ppid, "create": create, "path": path, "cmd": cmd}


PY = "C:\\Python312\\pythonw.exe"
VENV_PY = ROOT + "\\venv\\Scripts\\pythonw.exe"
WV = "C:\\Program Files (x86)\\Microsoft\\EdgeWebView\\Application\\154\\msedgewebview2.exe"
DATA = ROOT + "\\data-l1a"
ALLOWED = [ROOT, "C:\\Python312", "C:\\Program Files (x86)\\Microsoft\\EdgeWebView\\Application"]


def fixture_table():
    return {
        10: proc(10, 1, 100, VENV_PY),  # launcher
        11: proc(11, 10, 101, PY),  # the real interpreter
        12: proc(12, 11, 110, WV, f'"{WV}" --user-data-dir="{DATA}\\webview\\EBWebView" --x'),
        13: proc(13, 12, 111, WV, f"{WV} --type=renderer"),
        99: proc(99, 1, 90, "C:\\Program Files\\GleepGlorp AI\\the-one-app.exe"),
    }


def record(pid, table, role="app"):
    return {"pid": pid, "create": table[pid]["create"], "path": table[pid]["path"], "role": role}


def test_tree_launcher_interpreter_webview() -> None:
    t = fixture_table()
    found = h.descendants(t, {10})
    assert found == {11: 10, 12: 11, 13: 12}
    members, live = h.merge_members([record(10, t)], t, DATA)
    assert {m["pid"] for m in live} == {10, 11, 12, 13}
    assert 99 not in {m["pid"] for m in members}


def test_reused_parent_pid_does_not_adopt_unrelated_children() -> None:
    t = fixture_table()
    # pid 10 is recorded, but the live pid-10 process is a different, later one
    # (creation time differs): the recorded launcher is not live, so nothing is adopted.
    t[10] = proc(10, 1, 500, VENV_PY)
    members, live = h.merge_members([{"pid": 10, "create": 100, "path": VENV_PY}], t, DATA)
    assert 10 not in {m["pid"] for m in live}
    assert 11 not in {m["pid"] for m in members}  # the interpreter was never adopted
    # a child older than its parent is never adopted even when the parent is live
    t2 = fixture_table()
    t2[11] = proc(11, 10, 50, PY)  # created before the launcher at 100
    assert 11 not in h.descendants(t2, {10})


def test_parent_gone_webview_found_by_user_data_dir() -> None:
    t = fixture_table()
    rec = [record(10, t), record(11, t)]
    for gone in (10, 11):
        del t[gone]
    members, live = h.merge_members(rec, t, DATA)
    assert 12 in {m["pid"] for m in live}
    assert next(m for m in live if m["pid"] == 12)["role"] == "webview"


def test_reused_pid_is_refused() -> None:
    t = fixture_table()
    rec = record(11, t)
    reused = dict(t[11], create=999)
    assert h.check_kill(rec, reused, ALLOWED) == (False, "identity-mismatch")
    assert h.check_kill(rec, None, ALLOWED) == (False, "gone")
    other_path = dict(t[11], path="C:\\Windows\\notepad.exe")
    assert h.check_kill(rec, other_path, ALLOWED) == (False, "identity-mismatch")
    assert h.check_kill(rec, t[11], ALLOWED) == (True, "ok")


def test_path_outside_allowed_dirs_refused_even_if_identity_matches() -> None:
    t = fixture_table()
    rec = record(99, t)
    assert h.check_kill(rec, t[99], ALLOWED) == (False, "path-not-allowed")


def test_same_named_exe_outside_root_never_selected() -> None:
    t = fixture_table()
    t[50] = proc(50, 1, 120, ROOT + "\\src\\dist\\the-one\\the-one-app.exe")
    # the installed app is not a descendant of anything recorded and is outside the root
    members, live = h.merge_members([record(50, t)], t, DATA)
    assert 50 in {m["pid"] for m in live}
    assert 99 not in {m["pid"] for m in live}  # the installed app, by path
    assert h.check_kill(record(99, t), t[99], ALLOWED)[0] is False
    assert h.check_kill(record(50, t), t[50], ALLOWED)[0] is True


def test_kill_order_interpreter_first_watchdog_last() -> None:
    t = fixture_table()
    members, live = h.merge_members([record(10, t)], t, DATA)
    members.append({"pid": 77, "create": 1, "path": VENV_PY, "role": "watchdog"})
    order = [m["pid"] for m in h.kill_order(members)]
    assert order[0] == 11
    assert order[-1] == 77
    assert order.index(10) < order.index(12)


def test_installed_app_identified_with_two_same_named_processes() -> None:
    t = fixture_table()
    t[60] = proc(60, 1, 130, ROOT + "\\src\\dist\\the-one\\the-one-app.exe")
    lst = [{"port": 8484, "pid": 99}, {"port": 8490, "pid": 60}]
    got = h.find_installed_app(t, lst, ROOT, [])
    assert got["state"] == "running" and got["pid"] == 99
    # if the copy owned 8484 (it must not), it is still never "the installed app"
    lst2 = [{"port": 8484, "pid": 60}]
    assert h.find_installed_app(t, lst2, ROOT, [])["state"] == "not-running"
    assert h.find_installed_app(t, lst2, "", [t[60]["path"]])["state"] == "not-running"


def test_installed_app_not_running_and_unknown_owner() -> None:
    assert h.find_installed_app({}, [], ROOT, []) == {"state": "not-running"}
    assert (
        h.find_installed_app({}, [{"port": 8484, "pid": 5}], ROOT, [])["state"] == "unknown-owner"
    )


# ---------------------------------------------------------------- snapshot diff


def snap(**kw):
    base = {
        "installed": {"state": "running", "pid": 1, "create": 5, "path": "C:\\a.exe"},
        "files": {
            "api-credential": {"exists": True, "mtime_ns": 1, "sha256": "a"},
            ".env": {"exists": False},
            "window-chrome.json": {"exists": False},
            "window-state.json": {"exists": True, "mtime_ns": 2, "sha256": "b"},
        },
        "entries": ["api-credential", "the-one.db", "window-state.json"],
        "env": {"user": {}, "machine": {}},
    }
    base.update(kw)
    return base


def test_snapshot_unchanged() -> None:
    r = h.compare_snapshots(snap(), snap())
    assert r["ok"] and not r["allowed"] and not r["failures"]


def test_snapshot_allowed_geometry_change() -> None:
    after = snap()
    after["files"] = dict(
        after["files"], **{"window-state.json": {"exists": True, "mtime_ns": 9, "sha256": "z"}}
    )
    r = h.compare_snapshots(snap(), after)
    assert r["ok"] and len(r["allowed"]) == 1 and "geometry" in r["allowed"][0]


def test_snapshot_allowed_installed_restart() -> None:
    after = snap(installed={"state": "running", "pid": 2, "create": 9, "path": "C:\\a.exe"})
    r = h.compare_snapshots(snap(), after)
    assert r["ok"] and "restarted" in r["allowed"][0]


def test_snapshot_changed_credential_fails() -> None:
    after = snap()
    after["files"] = dict(
        after["files"], **{"api-credential": {"exists": True, "mtime_ns": 1, "sha256": "X"}}
    )
    r = h.compare_snapshots(snap(), after)
    assert not r["ok"] and "api-credential" in r["failures"][0]


def test_snapshot_new_chrome_json_or_env_file_fails() -> None:
    for name in ("window-chrome.json", ".env"):
        after = snap()
        after["files"] = dict(
            after["files"], **{name: {"exists": True, "mtime_ns": 1, "sha256": "q"}}
        )
        assert not h.compare_snapshots(snap(), after)["ok"]


def test_snapshot_new_top_level_entry_fails_and_gone_is_info() -> None:
    after = snap(entries=["api-credential", "the-one.db", "window-state.json", "oops"])
    r = h.compare_snapshots(snap(), after)
    assert not r["ok"] and "oops" in r["failures"][0]
    gone = snap(entries=["api-credential", "window-state.json"])
    r2 = h.compare_snapshots(snap(), gone)
    assert r2["ok"] and r2["info"]


def test_snapshot_env_change_fails() -> None:
    after = snap(env={"user": {"WEBVIEW2_X": "1"}, "machine": {}})
    assert not h.compare_snapshots(snap(), after)["ok"]


# ---------------------------------------------------------------- hands-off


def test_hands_off_own_injection_ignored() -> None:
    # last input is the helper's own injection tick: not the operator's
    assert not h.operator_input_recent(10_000, 10_000, 11_000)
    assert not h.operator_input_recent(9_990, 10_000, 11_000)


def test_hands_off_recent_operator_input() -> None:
    assert h.operator_input_recent(10_500, 10_000, 11_000)
    assert h.operator_input_recent(10_500, None, 11_000)
    assert not h.operator_input_recent(1_000, None, 11_000)  # idle for 10 s


def test_hands_off_tick_wraparound() -> None:
    wrapped_now = 500
    last_input = 0xFFFFFFFF - 1000  # 1.5 s before now across the wrap
    assert h.tick_age(wrapped_now, last_input) == 1501
    assert h.operator_input_recent(last_input, None, wrapped_now)
    # injection just before the wrap, operator input after it
    assert h.operator_input_recent(100, 0xFFFFFF00, wrapped_now)
    assert not h.operator_input_recent(0xFFFFFF10, 0xFFFFFF20, wrapped_now)


def test_missing_last_injection_means_none() -> None:
    assert h.parse_last_injection(None) is None
    assert h.parse_last_injection("garbage") is None
    assert h.parse_last_injection(" 123\n") == 123


# ---------------------------------------------------------------- setup sync


def test_sync_delete_pass_spares_build_products_and_only_deletes_manifest_files() -> None:
    src = {"a.py": (1, 10.0), "keep/b.py": (2, 10.0)}
    dest = {
        "a.py": (1, 10.0),
        "keep/b.py": (2, 10.0),
        "old.py": (3, 1.0),
        "dist/the-one/x.exe": (9, 1.0),
        "build/y": (9, 1.0),
        "the_one.egg-info/PKG-INFO": (9, 1.0),
        "pkg/__pycache__/m.pyc": (9, 1.0),
        "stray.txt": (1, 1.0),
    }
    prev = [
        "a.py",
        "old.py",
        "dist/the-one/x.exe",
        "build/y",
        "the_one.egg-info/PKG-INFO",
        "pkg/__pycache__/m.pyc",
    ]
    plan = h.plan_sync(src, dest, prev)
    assert plan["delete"] == ["old.py"]  # stray.txt is not in the manifest
    assert plan["copy"] == []


def test_sync_copies_only_changed_files() -> None:
    src = {"a": (1, 10.0), "b": (2, 20.0), "c": (3, 30.0)}
    dest = {"a": (1, 10.0), "b": (9, 20.0), "c": (3, 99.0)}
    assert h.plan_sync(src, dest, [])["copy"] == ["b", "c"]
    assert h.plan_sync(src, {}, [])["copy"] == ["a", "b", "c"]


def test_protected_names() -> None:
    for p in ("dist/a", "x/build/y", "the_one.egg-info/z", "a/__pycache__/b.pyc"):
        assert h.is_protected(p)
    assert not h.is_protected("the_one/dist_helper.py")


# ---------------------------------------------------------------- env, doctor


def test_scrub_env_removes_inherited_and_sets_cdp_only_on_request() -> None:
    inherited = {
        "PATH": "x",
        "THE_ONE_PORT": "8484",
        "the_one_data_dir": "C:\\op",
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--remote-debugging-port=1",
        "WEBVIEW2_USER_DATA_FOLDER": "C:\\z",
    }
    env = h.scrub_env(inherited, 8490, DATA, None)
    assert env["PATH"] == "x" and env["THE_ONE_PORT"] == "8490" and env["THE_ONE_DATA_DIR"] == DATA
    assert not any(k.upper().startswith("WEBVIEW2_") for k in env)
    assert "the_one_data_dir" not in env
    env2 = h.scrub_env(inherited, 8490, DATA, 9390)
    assert env2["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] == "--remote-debugging-port=9390"
    assert "WEBVIEW2_USER_DATA_FOLDER" not in env2


def test_scrub_env_dev_mode_is_explicit_opt_in() -> None:
    inherited = {"PATH": "x", "THE_ONE_DEV_MODE": "true"}
    assert "THE_ONE_DEV_MODE" not in h.scrub_env(inherited, 8490, DATA, None)
    assert h.scrub_env(inherited, 8490, DATA, None, dev_mode=True)["THE_ONE_DEV_MODE"] == "true"


class _ReachedError(Exception):
    pass


def _patch_launch(monkeypatch, live, stops):
    state = {"live": live}
    monkeypatch.setattr(h, "_require_ok_root", lambda root: None)
    monkeypatch.setattr(h, "_validate_dirs_and_ports", lambda a, need_ports: {})
    monkeypatch.setattr(h, "_env_file_refusal", lambda a, op: None)
    monkeypatch.setattr(h, "proc_table", lambda: {})
    monkeypatch.setattr(h, "_tree_ids", lambda root: ["main"])
    monkeypatch.setattr(h, "_refresh", lambda root, tid, table=None: ({}, state["live"]))

    def fake_stop(a):
        stops.append(a)
        state["live"] = []
        return {"stopped": [{"tree_id": a["tree_id"], "complete": True}]}

    def reached(a):
        raise _ReachedError

    monkeypatch.setattr(h, "op_stop", fake_stop)
    monkeypatch.setattr(h, "op_hands_off", reached)


def _launch_args():
    return {"root": "C:\\r", "tree_id": "main", "data_dir": DATA, "port": 8490}


def test_launch_stops_a_watchdog_left_after_the_app_exited(monkeypatch) -> None:
    stops: list[dict] = []
    _patch_launch(monkeypatch, [{"pid": 9, "role": "watchdog"}], stops)
    with pytest.raises(_ReachedError):
        h.op_launch(_launch_args())
    assert [s["tree_id"] for s in stops] == ["main"] and stops[0]["actor"] == "helper"


def test_launch_still_refuses_a_tree_whose_app_is_live(monkeypatch) -> None:
    stops: list[dict] = []
    live = [{"pid": 9, "role": "watchdog"}, {"pid": 8, "role": "app"}]
    _patch_launch(monkeypatch, live, stops)
    with pytest.raises(h.HelperError, match="still live"):
        h.op_launch(_launch_args())
    assert stops == []


def test_parse_doctor() -> None:
    out = (
        "the-one doctor\n  child spawn: OK — x\n  usearch: OK — y\n  fts5: OK — z\n"
        "  embedding model: OK — m\n  file watcher: OK — w\n  window chrome: OK — c\n"
        "  time zones: OK — t\n  mcp sdk: OK — s\n  chart images: OK — i\n\n"
        "  runtimes:\n    node: 1\n\nRESULT: PASS\n"
    )
    r = h.parse_doctor(out, 0)
    assert r["gate_count"] == 9 and r["result_line"] == "RESULT: PASS"
    assert all(r["needles"].values())
    assert not h.parse_doctor("RESULT: FAIL", 1)["needles"]["fts5: OK"]


# ---------------------------------------------------------------- the environment guard

# The patterns live HERE only, so the helper's own constants never match them.
FORBIDDEN_SOURCE_PATTERNS = [
    r"\bsetx\b",
    r"\[Environment\]::SetEnvironmentVariable",
    r"\breg\s+(add|delete|import)\b",
    r"\bSet-ItemProperty\b",
    r"\bNew-ItemProperty\b",
    r"\bRemove-ItemProperty\b",
    r"winreg\.(SetValue|SetValueEx|CreateKey|CreateKeyEx|DeleteValue|DeleteKey|DeleteKeyEx)",
    r"HK(CU|LM):",
    r"\btaskkill\b",
    r"Stop-Process",
]


@pytest.mark.parametrize("pattern", FORBIDDEN_SOURCE_PATTERNS)
def test_helper_source_never_writes_environment_or_kills_by_name(pattern: str) -> None:
    src = _PATH.read_text(encoding="utf-8")
    assert not re.search(pattern, src, re.IGNORECASE), pattern


def test_helper_imports_on_linux_without_windows_apis() -> None:
    assert callable(h.main) and callable(h._win_entry)
    assert h.local_path("C:\\Users\\x\\y") == "/mnt/c/Users/x/y"


def test_cli_refusals_exit_2_without_windows_access(monkeypatch, capsys) -> None:
    def boom(*a, **k):  # any Windows call would be a bug in a pure refusal
        raise h.HelperError("windows half reached", 2)

    monkeypatch.setattr(h, "win_call", boom)
    assert h.main(["launch", "--port", "8484", "--data-dir", "x"]) == 2
    assert "REFUSED" in capsys.readouterr().err


# ======================================================================
# Leg 1b: input, capture, own window, focus (pure parts)
# ======================================================================


# ---------------------------------------------------------- gate selection


def test_select_gate_single_tree() -> None:
    tid, pids = h.select_gate_pids({"main": [10, 11]}, None)
    assert tid == "main"
    assert pids == {10, 11}


def test_select_gate_several_trees_need_a_target() -> None:
    trees = {"main": [10], "spike": [20]}
    with pytest.raises(h.HelperError, match="several recorded trees"):
        h.select_gate_pids(trees, None)
    assert h.select_gate_pids(trees, "spike") == ("spike", {20})


def test_select_gate_unknown_target_and_no_tree_and_dead_tree() -> None:
    with pytest.raises(h.HelperError, match="no recorded tree 'x'"):
        h.select_gate_pids({"main": [1]}, "x")
    with pytest.raises(h.HelperError, match="no recorded tree"):
        h.select_gate_pids({}, None)
    with pytest.raises(h.HelperError, match="no live process"):
        h.select_gate_pids({"main": []}, None)


def test_select_gate_never_includes_the_own_record() -> None:
    # An own record is not a tree, even if something named one by mistake.
    trees = {"main": [10], "own": [99], "own-b": [98]}
    assert h.select_gate_pids(trees, None) == ("main", {10})
    with pytest.raises(h.HelperError, match="reserved"):
        h.select_gate_pids(trees, "own")
    only_own = {"own": [99]}
    with pytest.raises(h.HelperError, match="no recorded tree"):
        h.select_gate_pids(only_own, None)


# ---------------------------------------------------------- key grammar


def test_keys_plain_text_and_named() -> None:
    steps = h.parse_keys("ab{ENTER}")
    assert [(s["key"], s["named"], s["mods"]) for s in steps] == [
        ("a", False, []),
        ("b", False, []),
        ("ENTER", True, []),
    ]


def test_keys_modifiers_apply_to_the_next_key_only() -> None:
    steps = h.parse_keys("^kx")
    assert steps[0]["mods"] == ["ctrl"] and steps[0]["key"] == "k"
    assert steps[1]["mods"] == [] and steps[1]["key"] == "x"
    assert h.parse_keys("^+k")[0]["mods"] == ["ctrl", "shift"]
    assert h.parse_keys("%f")[0]["mods"] == ["alt"]
    assert h.parse_keys("{esc}")[0]["key"] == "ESC"
    assert h.parse_keys("{F5}")[0]["named"]


def test_keys_literal_modifier_characters_and_braces() -> None:
    for spec, ch in (("{^}", "^"), ("{+}", "+"), ("{%}", "%"), ("{{}", "{"), ("{}}", "}")):
        (step,) = h.parse_keys(spec)
        assert (step["key"], step["named"], step["mods"]) == (ch, False, [])
    (step,) = h.parse_keys("^{+}")
    assert step["mods"] == ["ctrl"] and step["key"] == "+"
    assert [s["key"] for s in h.parse_keys("a{^}b")] == ["a", "^", "b"]


@pytest.mark.parametrize(
    "spec",
    [
        "{WIN}",
        "{LWIN}",
        "{rwin}",
        "{WINDOWS}",
        "%{TAB}",
        "%{ESC}",
        "^{ESC}",
        "^+{ESC}",
        "%{F4}",
        "%{F1}",
        "^%a",
        "%^{DEL}",
        "^%{DEL}",
        "{PRTSC}",
        "{PRINTSCREEN}",
        "{VOLUME_UP}",
        "{MEDIA_PLAY_PAUSE}",
        "{BROWSER_BACK}",
        "{LAUNCH_MAIL}",
    ],
)
def test_keys_refused(spec: str) -> None:
    with pytest.raises(h.KeySpecError) as e:
        h.parse_keys(spec)
    assert e.value.code == 2
    assert "refused" in str(e.value)


@pytest.mark.parametrize("spec", ["", "{", "{ENTER", "{}", "{NOSUCH}", "^", "a^", "%+"])
def test_keys_malformed(spec: str) -> None:
    with pytest.raises(h.KeySpecError, match="malformed"):
        h.parse_keys(spec)


def test_keys_ctrl_k_and_escape_are_allowed() -> None:
    assert h.parse_keys("^k")[0]["mods"] == ["ctrl"]
    assert h.parse_keys("{ESC}")[0]["mods"] == []
    assert h.parse_keys("+{TAB}")[0]["mods"] == ["shift"]  # Shift+Tab is fine


def test_key_events_order() -> None:
    ev = h.key_events([([0x11], 0x4B, False), ([], 0x1B, False)])
    assert ev == [
        (0x11, True),
        (0x4B, True),
        (0x4B, False),
        (0x11, False),
        (0x1B, True),
        (0x1B, False),
    ]
    ev = h.key_events([([0x11, 0x10], 0x4B, False)])
    assert [e[0] for e in ev] == [0x11, 0x10, 0x4B, 0x4B, 0x10, 0x11]


# ---------------------------------------------------------- geometry and drags

FRAME = [880, 396, 1666, 989]  # a window with 786x593 frame bounds
WORK = [0, 0, 1920, 1040]


def test_point_and_rect_helpers() -> None:
    assert h.point_in_rect((880, 396), FRAME)
    assert not h.point_in_rect((1666, 396), FRAME)  # right edge is exclusive
    assert h.rect_inside([900, 400, 1000, 500], FRAME)
    assert not h.rect_inside([900, 400, 1700, 500], FRAME)
    assert h.rects_intersect([0, 0, 10, 10], [9, 9, 20, 20])
    assert not h.rects_intersect([0, 0, 10, 10], [10, 0, 20, 10])


def test_caption_zone_scales_with_dpi() -> None:
    assert h.caption_zone(FRAME) == [880, 396, 1666 - 138, 396 + 31]
    assert h.caption_zone(FRAME, 192) == [880, 396, 1666 - 276, 396 + 62]


def test_caption_drag_plan_ok() -> None:
    plan = h.plan_caption_drag((1000, 410), (1100, 460), FRAME, WORK)
    assert plan["mode"] == "caption"
    assert plan["delta"] == [100, 50]
    assert plan["planned"] == [980, 446, 1766, 1039]


@pytest.mark.parametrize(
    ("start", "end", "why"),
    [
        ((1000, 440), (1100, 460), "not on the window's caption"),  # below the caption
        ((1600, 410), (1650, 420), "not on the window's caption"),  # over the buttons
        ((870, 410), (900, 410), "not on the window's caption"),  # left of the window
        ((1000, 410), (1000, 600), "leave the work area"),  # window would sink off the bottom
        ((1000, 410), (-900, 410), "leave the work area"),
    ],
)
def test_caption_drag_plan_refused(start, end, why) -> None:
    with pytest.raises(h.HelperError, match=why):
        h.plan_caption_drag(start, end, FRAME, WORK)


def test_caption_drag_refuses_a_snap_zone_end() -> None:
    frame = [100, 100, 886, 693]
    # the window top lands on the screen top (a snap zone): 10px from the edge is refused
    with pytest.raises(h.HelperError, match="screen edge"):
        h.plan_caption_drag((300, 110), (300, 10), frame, [0, 0, 1920, 1040])


def test_content_drag_end_must_be_inside_the_current_bounds() -> None:
    plan = h.plan_content_drag((1000, 500), (1600, 900), FRAME)
    assert plan == {"mode": "content", "delta": [600, 400]}
    with pytest.raises(h.HelperError, match="end .* outside the window"):
        h.plan_content_drag((1000, 500), (1700, 900), FRAME)
    with pytest.raises(h.HelperError, match="start .* outside"):
        h.plan_content_drag((10, 10), (1000, 500), FRAME)


def test_drag_path_ends_exactly_on_the_target() -> None:
    path = h.drag_path((0, 0), (100, 50), 4)
    assert path == [(25, 12), (50, 25), (75, 38), (100, 50)] or path[-1] == (100, 50)
    assert path[-1] == (100, 50)
    assert h.drag_path((5, 5), (5, 5), 0) == [(5, 5)]


def test_gate_point_decision() -> None:
    assert h.gate_point_decision(100, 10, {10}, {200}, False) == "tree"
    assert h.gate_point_decision(200, 20, {10}, {200}, True) == "own"
    # an own window is never a drag end
    with pytest.raises(h.HelperError, match="not the gate tree"):
        h.gate_point_decision(200, 20, {10}, {200}, False)
    # a foreign window (the covered end point of a default-mode drag) is refused
    with pytest.raises(h.HelperError, match="pointer gate"):
        h.gate_point_decision(300, 30, {10}, {200}, True)
    with pytest.raises(h.HelperError, match="no window"):
        h.gate_point_decision(None, None, {10}, {200}, True)


def test_default_drag_end_covered_by_a_foreign_window_is_refused() -> None:
    # The plan alone accepts the end (inside the bounds); the covered end is caught by
    # the point gate, which sees a foreign window at that point.
    h.plan_content_drag((1000, 500), (1500, 900), FRAME)
    with pytest.raises(h.HelperError):
        h.gate_point_decision(555, 77, {10}, set(), False)


# ---------------------------------------------------------- captures


def test_capture_contained_in_frame_bounds_not_the_invisible_margin() -> None:
    outer = [872, 396, 1674, 997]  # GetWindowRect: 8px invisible margins
    assert h.capture_contained([880, 396, 900, 420], [FRAME])
    assert not h.capture_contained([872, 400, 880, 410], [FRAME])  # in the margin only
    assert h.capture_contained([872, 400, 880, 410], [outer])  # (why it is never used)
    assert h.capture_contained([10, 10, 20, 20], [FRAME, [0, 0, 200, 100]])
    assert not h.capture_contained([10, 10, 20, 20], [FRAME, None])


def _w(hwnd, pid, bounds, **kw):
    d = {"hwnd": hwnd, "pid": pid, "visible": True, "cloaked": False, "bounds": bounds}
    d.update(kw)
    return d


ZLIST = [
    _w(1, 50, [0, 0, 100, 100]),
    _w(2, 51, [0, 0, 100, 100]),
    _w(3, 10, [880, 396, 1666, 989]),  # the target (a tree window)
    _w(4, 52, [0, 0, 5000, 5000]),  # below the target: never an occluder
]


def test_z_above_is_the_earlier_windows() -> None:
    above = h.z_above(ZLIST, 3)
    assert [w["hwnd"] for w in above] == [1, 2]
    assert h.z_above(ZLIST, 99) is None
    assert h.z_above(ZLIST, 1) == []


def test_occluders_intersecting_and_not() -> None:
    above = [_w(1, 50, [0, 0, 100, 100]), _w(2, 51, [900, 400, 1000, 500])]
    rect = [890, 396, 1000, 430]
    occ = h.occluders(above, rect, {10}, {99})
    assert [(o["hwnd"], o["kind"]) for o in occ] == [(2, "covered_by_other")]


def test_occluders_skip_invisible_cloaked_zero_transparent_and_zero_alpha() -> None:
    rect = [890, 396, 1000, 430]
    cover = [880, 380, 1100, 450]
    above = [
        _w(1, 50, cover, visible=False),
        _w(2, 51, cover, cloaked=True),
        _w(3, 52, [900, 400, 900, 450]),  # zero width
        _w(4, 53, cover, transparent=True),  # a transparent overlay
        _w(5, 54, cover, alpha=0),  # a layered window at zero alpha
    ]
    assert h.occluders(above, rect, {10}, set()) == []
    # an ordinary layered window with alpha, and a tool window, DO occlude
    above = [_w(6, 55, cover, alpha=200), _w(7, 56, cover, tool=True)]
    assert [o["hwnd"] for o in h.occluders(above, rect, {10}, set())] == [6, 7]


def test_occluders_classify_own_and_tree_windows() -> None:
    rect = [890, 396, 1000, 430]
    cover = [880, 380, 1100, 450]
    occ = h.occluders([_w(1, 99, cover), _w(2, 10, cover), _w(3, 77, cover)], rect, {10}, {99})
    assert [o["kind"] for o in occ] == ["covered_by_own", "covered_by_tree", "covered_by_other"]


def test_occlusion_verdict() -> None:
    assert h.occlusion_verdict([])["ok"]
    own = [{"hwnd": 1, "pid": 99, "kind": "covered_by_own"}]
    v = h.occlusion_verdict(own)
    assert not v["ok"] and v["reason"] == "covered_by_own"
    v = h.occlusion_verdict(own, allow_own_cover=True)
    assert v["ok"] and v["own_cover_allowed"]
    tree = [{"hwnd": 2, "pid": 10, "kind": "covered_by_tree"}]
    assert h.occlusion_verdict(tree)["reason"] == "covered_by_tree"
    # the flag never excuses a foreign or tree window, alone or mixed with own
    assert not h.occlusion_verdict(tree, allow_own_cover=True)["ok"]
    mixed = own + [{"hwnd": 3, "pid": 5, "kind": "covered_by_other"}]
    v = h.occlusion_verdict(mixed, allow_own_cover=True)
    assert not v["ok"] and v["reason"] == "covered_by_other"


def test_series_limits() -> None:
    h.check_series(60, 16, 1280, 800)  # 60 * 4.096MB = 245.8MB: fits
    h.check_series(200, 20, 300, 24)
    with pytest.raises(h.HelperError, match="frames must be"):
        h.check_series(201, 20, 10, 10)
    with pytest.raises(h.HelperError, match="frames must be"):
        h.check_series(0, 20, 10, 10)
    with pytest.raises(h.HelperError, match="interval must be at least 16"):
        h.check_series(10, 15.9, 10, 10)
    with pytest.raises(h.HelperError, match="limit"):
        h.check_series(70, 20, 1280, 800)  # 286MB
    assert h.max_series_frames(1280, 800) == 65
    assert h.max_series_frames(300, 24) == 200


def test_luminance_and_contrast() -> None:
    assert h.luminance((255, 255, 255)) == pytest.approx(1.0)
    assert h.luminance((0, 0, 0)) == 0.0
    assert h.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert h.contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0)
    assert h.contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=0.02)
    assert h.contrast_ratio((10, 20, 30), (10, 20, 30)) == pytest.approx(1.0)


def test_patch_stats_mean_darkest_lightest() -> None:
    px = [(10, 10, 10), (200, 200, 200), (100, 50, 0), (255, 255, 0)]
    s = h.patch_stats(px)
    assert s["mean"] == [141.25, 128.75, 52.5]
    assert s["darkest"] == [10, 10, 10]
    assert s["lightest"] == [255, 255, 0]
    assert s["n"] == 4
    with pytest.raises(h.HelperError):
        h.patch_stats([])


def test_bgra_helpers_and_png_roundtrip() -> None:
    import struct
    import zlib

    buf = bytes([3, 2, 1, 255, 30, 20, 10, 255])  # BGRA: (1,2,3) and (10,20,30)
    assert h.bgra_pixels(buf, 2, 1) == [(1, 2, 3), (10, 20, 30)]
    assert h.bgra_mean(buf) == [5.5, 11.0, 16.5]
    assert h.bgra_to_rgb(buf) == bytes([1, 2, 3, 10, 20, 30])
    png = h.encode_png(2, 1, h.bgra_to_rgb(buf))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    pos, chunks = 8, {}
    while pos < len(png):
        (n,) = struct.unpack(">I", png[pos : pos + 4])
        tag = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + n]
        (crc,) = struct.unpack(">I", png[pos + 8 + n : pos + 12 + n])
        assert crc == zlib.crc32(tag + data) & 0xFFFFFFFF
        chunks[tag] = data
        pos += 12 + n
    assert struct.unpack(">IIBBBBB", chunks[b"IHDR"]) == (2, 1, 8, 2, 0, 0, 0)
    assert zlib.decompress(chunks[b"IDAT"]) == b"\x00" + bytes([1, 2, 3, 10, 20, 30])


# ---------------------------------------------------------- own window


def test_own_seconds_and_topmost_clamps() -> None:
    assert h.clamp_own_seconds(None) == 60
    assert h.clamp_own_seconds(5) == 5
    assert h.clamp_own_seconds(0) == 1
    assert h.clamp_own_seconds(100000) == 600
    assert h.clamp_topmost_seconds(None) == 60
    assert h.clamp_topmost_seconds(30) == 30
    assert h.clamp_topmost_seconds(600) == 60


def test_own_window_placement() -> None:
    work = [0, 0, 1920, 1040]
    assert h.place_own_window(work) == [8, 1040 - 100 - 8, 208, 1040 - 8]
    assert h.place_own_window(work, at=(500, 300)) == [500, 300, 700, 400]
    # clamped inside the work area
    assert h.place_own_window(work, at=(5000, 5000)) == [1720, 940, 1920, 1040]
    assert h.place_own_window(work, at=(-50, -50)) == [0, 0, 200, 100]
    # a work area that does not start at the origin
    assert h.place_own_window([100, 50, 1000, 600])[:2] == [108, 600 - 100 - 8]


def test_own_command_allowlist_nonce_and_expiry() -> None:
    now = 1000.0
    cmd = h.make_command("front-tree", "n1", now)
    assert h.validate_command(cmd, now + 1, set()) == (True, "ok")
    assert h.validate_command(cmd, now + 5.1, set()) == (False, "expired")
    assert h.validate_command(cmd, now + 1, {"n1"}) == (False, "repeated-nonce")
    assert h.validate_command(h.make_command("restore-focus", "n2", now), now, set())[0]
    for bad in ("shell", "keys", "click", "kill", ""):
        assert h.validate_command(h.make_command(bad, "n3", now), now, set()) == (
            False,
            "not-allowed",
        )
    assert h.validate_command({"action": "front-tree"}, now, set()) == (False, "no-nonce")
    far = h.make_command("front-tree", "n4", now)
    far["expires"] = now + 3600
    assert h.validate_command(far, now, set()) == (False, "bad-expiry")
    assert h.validate_command("front-tree", now, set()) == (False, "malformed")
    assert h.validate_command({"action": "front-tree", "nonce": "x"}, now, set()) == (
        False,
        "expired",
    )


# ---------------------------------------------------------- injection model


def test_record_injection_sends_then_reads_then_writes() -> None:
    calls = []
    tick = h.record_injection(
        lambda: calls.append("send"),
        lambda: (calls.append("read"), 1234)[1],
        lambda t: calls.append(("write", t)),
    )
    assert tick == 1234
    assert calls == ["send", "read", ("write", 1234)]


def test_interference_one_tick_tolerance() -> None:
    own = 1_000_000
    assert not h.injection_interference(own, own)
    assert not h.injection_interference(own - 50, own)  # older than ours
    assert not h.injection_interference(own + 16, own)  # exactly one tick: tolerated
    assert h.injection_interference(own + 17, own)  # past one tick: the operator
    assert h.injection_interference(own + 5000, own)
    assert not h.injection_interference(own + 5000, None)  # no injection yet


def test_interference_across_a_tick_wrap() -> None:
    own = 0xFFFFFFF0
    assert not h.injection_interference((own + 10) & 0xFFFFFFFF, own)  # wrapped, within 16
    assert h.injection_interference((own + 40) & 0xFFFFFFFF, own)  # wrapped, past 16
    assert not h.injection_interference(own - 100, own)  # older, no wrap


def test_hands_off_is_clear_right_after_an_injection() -> None:
    # `record_injection` writes the post-send tick, so the injection's own last-input
    # tick is not newer than it: not the operator's.
    inj = h.record_injection(lambda: None, lambda: 5000, lambda t: None)
    assert not h.operator_input_recent(4990, inj, 5003)
    assert h.operator_input_recent(5400, inj, 5403)


def test_cursor_restore_decision() -> None:
    assert h.cursor_restore_decision((10, 10), (500, 500), (500, 500)) == "restore"
    assert h.cursor_restore_decision((10, 10), (500, 500), (503, 500)) == "leave"
    assert h.cursor_restore_decision((500, 500), (500, 500), (500, 500)) == "none"
    assert h.cursor_restore_decision([10, 10], [500, 500], (500, 500)) == "restore"


# ---------------------------------------------------------- focus


def test_focus_restore_decision_table() -> None:
    d = h.focus_restore_decision
    assert d(False, 5, 9, True) == "gone"
    assert d(False, 5, 5, False) == "gone"
    assert d(True, 5, 5, False) == "already-foreground"
    assert d(True, 5, 9, False) == "operator-moved-on"  # an operator window is in front
    assert d(True, 5, 9, True) == "restore"  # the tree or an own window is in front
    assert d(True, 5, None, False) == "restore"  # nothing is in front
    assert d(True, 5, 0, False) == "restore"


def test_focus_restore_outcome() -> None:
    assert h.focus_restore_outcome(5, 5) == "restored"
    assert h.focus_restore_outcome(9, 5) == "failed"
    assert h.focus_restore_outcome(None, 5) == "failed"


def test_focus_save_first_save_wins_and_staleness() -> None:
    d = h.focus_save_decision
    now = 100_000.0
    fresh = {"saved_at": now - 60}
    assert d(None, False, now, True, False) == "save"
    assert d(fresh, True, now, True, False) == "refuse-fresh-exists"
    assert d({"saved_at": now - 3 * 3600}, True, now, True, False) == "replace-stale"
    assert d(fresh, False, now, True, False) == "replace-stale"  # identity no longer matches
    assert d(None, False, now, True, True) == "refuse-ours"
    assert d(fresh, True, now, True, True) == "refuse-ours"
    assert d(None, False, now, False, False) == "refuse-nothing"


def test_focus_save_discard() -> None:
    d = h.focus_save_decision
    assert d({"saved_at": 1}, True, 10.0, True, True, discard=True) == "discard"
    assert d(None, False, 10.0, True, False, discard=True) == "nothing-to-discard"


# ---------------------------------------------------------- input log


def test_input_log_summary_and_dangling() -> None:
    rows = [
        {"outcome": "begin", "gesture": "keys"},
        {"outcome": "sent", "target": "tree"},
        {"outcome": "sent", "target": "own"},
        {"outcome": "refused", "gesture": "keys"},
        {"outcome": "aborted"},
        {"outcome": "sent", "target": "tree"},
    ]
    import json

    text = "\n".join(json.dumps(r) for r in rows) + "\nnot json\n"
    s = h.summarize_input_log(text)
    assert (s["sent"], s["aborted"], s["refused"]) == (3, 1, 1)
    assert s["sent_targets"] == {"tree": 2, "own": 1}
    assert not h.log_dangling(text)
    assert h.log_dangling(text + json.dumps({"outcome": "begin"}) + "\n")
    assert not h.log_dangling("")


def test_target_translucent() -> None:
    assert not h.target_translucent({"alpha": None})
    assert not h.target_translucent({})
    assert not h.target_translucent({"alpha": 255})
    assert h.target_translucent({"alpha": 0})
    assert h.target_translucent({"alpha": 254})


def test_dangling_row_names_the_helper_that_began_it() -> None:
    import json

    begin = {"outcome": "begin", "gesture": "drag", "helper": {"pid": 7, "create": 1, "path": "p"}}
    text = json.dumps({"outcome": "sent"}) + "\n" + json.dumps(begin) + "\n"
    assert h.dangling_row(text) == begin
    assert h.dangling_row(text + json.dumps({"outcome": "sent"}) + "\n") is None
    assert h.dangling_row("") is None
    assert h.dangling_row("not json\n") is None


# ---------------------------------------------------------------- resize (M25 F5 L4)


def test_validate_resize_accepts_in_range():
    assert h.validate_resize(400, 250) == (400, 250)
    assert h.validate_resize(100, 10000) == (100, 10000)


@pytest.mark.parametrize(
    ("w", "ht"),
    [
        (0, 300),
        (-5, 300),
        (99, 300),
        (300, 99),
        (10001, 300),
        (300, 10001),
        ("400", 300),
        (400.0, 300),
        (True, 300),
    ],
)
def test_validate_resize_refuses_bad_sizes(w, ht):
    with pytest.raises(h.HelperError):
        h.validate_resize(w, ht)


def test_splash_title_is_not_the_main_title():
    assert h.SPLASH_WINDOW_TITLE != h.MAIN_WINDOW_TITLE
    assert h.SPLASH_WINDOW_TITLE.startswith(h.MAIN_WINDOW_TITLE)


def test_parser_has_resize_and_splash_series():
    p = h.build_parser()
    a = p.parse_args(["resize", "--width", "400", "--height", "250"])
    assert (a.width, a.height) == (400, 250)
    c = p.parse_args(["capture", "--window", "--splash", "--series", "5", "--out", "x"])
    assert c.splash is True and c.series == 5
    with pytest.raises(SystemExit):
        p.parse_args(["resize", "--width", "400"])


_BUILD_PS1 = Path(__file__).parent.parent / "packaging" / "windows" / "build.ps1"


def test_needles_match_build_ps1_list() -> None:
    """The helper's needles are the Windows recipe's (build.ps1) list, which adds the desktop
    shell and child-spawn gates after them."""
    ps1 = _BUILD_PS1.read_text(encoding="utf-8")
    m = re.search(r"function Get-DoctorNeedles \{\s*return @\((.*?)\n\s*\)\s*\}", ps1, re.S)
    assert m, "Get-DoctorNeedles list not found in build.ps1"
    recipe = tuple(re.findall(r"'([^']+)'", m.group(1)))
    assert recipe[: len(h.NEEDLES)] == h.NEEDLES
    assert recipe[len(h.NEEDLES) :] == ("desktop shell: OK", "child spawn: OK")


def test_closure_commands_match_build_ps1() -> None:
    """Squawk 0124: the helper's dependency closure equals the Windows recipe's.

    build.ps1 adds only ``--frozen`` (uv export), ``--output-file`` and ``--require-hashes``
    (pip), which the helper does not need. The helper keeps its editable project install (its
    non-frozen runs import the copy); the recipe never installs the project.
    """
    ps1 = _BUILD_PS1.read_text(encoding="utf-8")
    m = re.search(r"-m uv export (.+?) --output-file", ps1)
    assert m, "uv export line not found in build.ps1"
    assert tuple(a for a in m.group(1).split() if a != "--frozen") == h.CLOSURE_UV_EXPORT_ARGS
    m = re.search(r"-m pip install (--require-hashes .+? -r \$reqs)", ps1)
    assert m, "pip install -r line not found in build.ps1"
    flags = {a for a in m.group(1).split() if a.startswith("--") and a != "--require-hashes"}
    assert flags == {a for a in h.CLOSURE_PIP_REQUIREMENTS_ARGS if a.startswith("--")}
    assert "pip install -e" not in ps1


# ---------------------------------------------------------------- the staged freeze (M32 F4)


def test_freeze_plan_stages_and_sets_m32_stage() -> None:
    vpy = ROOT + "\\venv\\Scripts\\python.exe"
    plan = h.freeze_plan(ROOT, vpy, "0.11.9.dev1")
    assert plan["env"] == {"M32_STAGE": ROOT + "\\stage\\stage-windows-0.11.9.dev1"}
    stage = plan["stage_cmd"]
    assert stage[0] == vpy and stage[1].endswith("packaging\\stage.py")
    assert stage[stage.index("--target") + 1] == "windows"
    assert stage[stage.index("--version") + 1] == "0.11.9.dev1"
    assert stage[stage.index("--out") + 1] == ROOT + "\\stage"
    assert plan["freeze_cmd"][-1] == "packaging/windows/the-one.spec"


def test_op_freeze_runs_stage_before_pyinstaller_with_the_env() -> None:
    src = Path(_PATH).read_text(encoding="utf-8")
    body = src[src.index("def op_freeze") : src.index("def op_doctor(")]
    assert body.index('plan["stage_cmd"]') < body.index('plan["freeze_cmd"]')
    assert 'freeze_env.update(plan["env"])' in body
