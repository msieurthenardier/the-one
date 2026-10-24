"""Unit tests for packaging/linux/checks/score.py, the gate scorer (M32 F2 L8, DD8)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).parent.parent / "packaging" / "linux" / "checks" / "score.py"
_SPEC = importlib.util.spec_from_file_location("packaging_score", _PATH)
score = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = score
_SPEC.loader.exec_module(score)

MOUNT = "/tmp/.mount_GleepGXYZ12"
FB = f"{MOUNT}/usr/lib/gleepglorp-ai-fallback/lib"
ARCH = "/usr/lib/x86_64-linux-gnu"
BASE = ["libglib-2.0.so.0", "libgobject-2.0.so.0", "libgtk-3.so.0", "libwebkit2gtk-4.1.so.0"]


def _maps(*paths: str) -> str:
    return "\n".join(f"7f00-7f01 r-xp 0 00:00 1 {p}" for p in paths) + "\n"


def _host_base() -> list[str]:
    return [f"{ARCH}/{n}" for n in BASE] + [
        f"{ARCH}/libstdc++.so.6",
        f"{ARCH}/libgcc_s.so.1",
        f"{ARCH}/libgirepository-2.0.so.0",
        f"{ARCH}/libdbusmenu-glib.so.4",
        f"{ARCH}/libdbusmenu-gtk3.so.4",
        f"{ARCH}/libayatana-ido3-0.4.so.0",
        f"{ARCH}/libayatana-indicator3.so.7",
        f"{ARCH}/libayatana-appindicator3.so.1",
    ]


# ---------------------------------------------------------------- gate 1


def _doctor(rc: int, *gates: tuple[str, str, str]) -> str:
    lines = [f"  {n}: {s} — {d}" for n, s, d in gates]
    return "\n".join(["the-one doctor", *lines, f"rc={rc}"])


def test_doctor_passes_when_every_gate_ok() -> None:
    assert score.score_doctor(_doctor(0, ("desktop shell", "OK", "fine")))["pass"]


def test_doctor_skip_is_a_failure() -> None:
    r = score.score_doctor(_doctor(0, ("desktop shell", "OK", "skipped (no display)")))
    assert not r["pass"] and r["bad"] == ["desktop shell skipped"]


def test_doctor_window_chrome_not_windows_skip_is_allowed() -> None:
    r = score.score_doctor(_doctor(0, ("window chrome", "OK", "skipped (not Windows)")))
    assert r["pass"]


def test_doctor_window_chrome_other_skip_is_not_allowed() -> None:
    r = score.score_doctor(_doctor(0, ("window chrome", "OK", "skipped (broken)")))
    assert not r["pass"]


def test_doctor_fail_nonzero_rc_or_no_gates_fail() -> None:
    assert not score.score_doctor(_doctor(1, ("x", "FAIL", "boom")))["pass"]
    assert not score.score_doctor(_doctor(1, ("x", "OK", "fine")))["pass"]
    assert not score.score_doctor("rc=0")["pass"]


# ---------------------------------------------------------------- gate 3, per soname


def test_host_library_from_usr_lib_passes() -> None:
    maps = _maps(*_host_base())
    r = score.score_maps(maps, web=False, appimage=True, host={"libgirepository-2.0.so.0": True})
    assert r["ok"], r["bad"]


def test_fallback_path_when_host_lacks_it_passes() -> None:
    files = [f for f in _host_base() if "libgirepository" not in f]
    maps = _maps(*files, f"{FB}/libgirepository-2.0.so.0")
    r = score.score_maps(maps, web=False, appimage=True, host={"libgirepository-2.0.so.0": False})
    assert r["ok"], r["bad"]


def test_fallback_path_when_host_has_it_fails() -> None:
    files = [f for f in _host_base() if "libgirepository" not in f]
    maps = _maps(*files, f"{FB}/libgirepository-2.0.so.0")
    r = score.score_maps(maps, web=False, appimage=True, host={"libgirepository-2.0.so.0": True})
    assert not r["ok"] and "libgirepository-2.0" in r["bad"]


def test_a_second_glib_copy_fails() -> None:
    maps = _maps(*_host_base(), f"{MOUNT}/usr/lib/gleepglorp-ai/_internal/libglib-2.0.so.0")
    assert not score.score_maps(maps, web=False, appimage=True, host={})["ok"]


def test_web_process_mapping_the_mount_fails() -> None:
    maps = _maps(f"{ARCH}/libglib-2.0.so.0", f"{FB}/libdbusmenu-glib.so.4")
    r = score.score_maps(maps, web=True, appimage=True, host={})
    assert not r["ok"]
    assert any("web process maps" in b for b in r["bad"])


def test_web_process_with_host_libraries_only_passes() -> None:
    maps = _maps(f"{ARCH}/libglib-2.0.so.0", f"{ARCH}/libgobject-2.0.so.0")
    # a web process need not map every family, but none may come from outside /usr/lib
    r = score.score_maps(maps, web=True, appimage=True, host={})
    assert all(b not in r["bad"] for b in ("libglib-2.0", "libgobject-2.0"))


# ---------------------------------------------------------------- environ and hook report


def test_environ_with_a_package_path_fails() -> None:
    assert score.score_environ("LD_LIBRARY_PATH=/tmp/.mount_x/usr/lib\nHOME=/h")["bad"]
    assert score.score_environ("HOME=/h\nPATH=/usr/bin")["ok"]
    assert not score.score_environ("")["ok"]


def test_hook_report_parse() -> None:
    log = (
        "fallback sources: {'libdbusmenu-glib.so.4': 'host'}\n"
        "GI_TYPELIB_PATH='/a:/b' LD_LIBRARY_PATH=None\n"
    )
    rep = score.hook_report(log)
    assert rep == {
        "sources": {"libdbusmenu-glib.so.4": "host"},
        "gi_typelib_path": "/a:/b",
        "ld_library_path": "None",
    }
    assert score.hook_report("nothing") is None


# ---------------------------------------------------------------- the ABI probe scorer


def _probe(tmp_path: Path, name: str, out: str, err: str, rc: str = "rc=0") -> Path:
    d = tmp_path / name
    d.mkdir()
    (d / "probe.stdout").write_text(out)
    (d / "probe.stderr").write_text(err)
    (d / "probe.rc").write_text(rc + "\n")
    return d


def test_probe_clean_run_passes(tmp_path) -> None:
    ev = _probe(tmp_path, "a", "PROBE_OK\n", "harmless line\n")
    assert score.score_probe(ev, None, False)["ok"]


def test_probe_flags_each_pattern(tmp_path) -> None:
    for i, bad in enumerate(
        [
            "GLib-CRITICAL **: boom",
            "GLib-GObject-WARNING **: x",
            "GLib-GIO-CRITICAL **: x",
            "symbol lookup error: foo",
            "undefined symbol: g_thing",
        ]
    ):
        ev = _probe(tmp_path, f"p{i}", "PROBE_OK\n", bad + "\n")
        assert not score.score_probe(ev, None, False)["ok"], bad


def test_probe_control_lines_are_excluded(tmp_path) -> None:
    line = "GLib-GIO-WARNING **: Error releasing name: closed"
    ctl = _probe(tmp_path, "ctl", "PROBE_OK\n", line + "\n")
    ev = _probe(tmp_path, "ev", "PROBE_OK\n", line + "\n")
    r = score.score_probe(ev, ctl, False)
    assert r["ok"] and r["excluded_as_in_control"] == [line]


def test_probe_missing_ok_or_nonzero_rc_fails(tmp_path) -> None:
    assert not score.score_probe(_probe(tmp_path, "n", "", ""), None, False)["ok"]
    assert not score.score_probe(_probe(tmp_path, "r", "PROBE_OK\n", "", "rc=1"), None, False)["ok"]


def test_probe_expect_fallback_needs_six_from_the_mount(tmp_path) -> None:
    sos = [
        "libgirepository-2.0.so.0",
        "libdbusmenu-glib.so.4",
        "libdbusmenu-gtk3.so.4",
        "libayatana-ido3-0.4.so.0",
        "libayatana-indicator3.so.7",
        "libayatana-appindicator3.so.1",
    ]
    good = "PROBE_OK\n" + "".join(f"PROBE_MAP {FB}/{s}\n" for s in sos)
    assert score.score_probe(_probe(tmp_path, "g", good, ""), None, True)["ok"]
    mixed = good + f"PROBE_MAP {ARCH}/libother.so\n"
    assert not score.score_probe(_probe(tmp_path, "m", mixed, ""), None, True)["ok"]
    assert not score.score_probe(_probe(tmp_path, "h", "PROBE_OK\n", ""), None, True)["ok"]
