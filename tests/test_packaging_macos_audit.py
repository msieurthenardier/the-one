"""Unit tests for the macOS bundle audit and recipe helpers (Mission 32 Flight 3 leg 6).

``audit.py`` is exercised on canned ``otool``/``lipo`` output through an injected runner;
``info_plist.py`` and ``frozen_entry_mac.py``'s log redirect are loaded by path.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MACOS = REPO / "packaging" / "macos"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


audit = _load("macos_audit", MACOS / "audit.py")
info_plist = _load("macos_info_plist", MACOS / "info_plist.py")
render = _load("packaging_render_macos", REPO / "packaging" / "render.py")

OTOOL_L_OK = """/app/x.so:
\t@rpath/libfoo.dylib (compatibility version 1.0.0, current version 1.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1311.0.0)
\t/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit (compatibility version 45.0.0)
\t@loader_path/../lib/libbar.dylib (compatibility version 0.0.0)
\t@executable_path/../Frameworks/libbaz.dylib (compatibility version 0.0.0)
"""
OTOOL_L_BAD = """/app/x.so:
\t/opt/homebrew/lib/libssl.3.dylib (compatibility version 3.0.0, current version 3.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1311.0.0)
\t/usr/local/lib/libz.dylib (compatibility version 1.0.0)
"""
OTOOL_L_DYLIB = """/app/libfoo.dylib:
\t/Users/runner/build/libfoo.dylib (compatibility version 1.0.0, current version 1.0.0)
\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1311.0.0)
"""


def cmds(minos: str | None = "11.0", *, dylib_id: str | None = None, legacy: str | None = None):
    out = "x.so:\nMach header\nLoad command 0\n      cmd LC_SEGMENT_64\n  cmdsize 72\n"
    if dylib_id:
        out += (
            "Load command 1\n          cmd LC_ID_DYLIB\n      cmdsize 48\n"
            f"         name {dylib_id} (offset 24)\n"
        )
    if minos:
        out += (
            "Load command 8\n      cmd LC_BUILD_VERSION\n  cmdsize 32\n platform 1\n"
            f"    minos {minos}\n      sdk 14.2\n   ntools 1\n"
        )
    if legacy:
        out += (
            "Load command 9\n      cmd LC_VERSION_MIN_MACOSX\n  cmdsize 16\n"
            f"  version {legacy}\n      sdk 10.9\n"
        )
    return out


def test_parse_libs_and_allowlist():
    libs = audit.parse_libs(OTOOL_L_OK)
    assert len(libs) == 5 and audit.bad_libs(libs) == []
    bad = audit.bad_libs(audit.parse_libs(OTOOL_L_BAD))
    assert bad == ["/opt/homebrew/lib/libssl.3.dylib", "/usr/local/lib/libz.dylib"]


def test_dylib_own_install_name_is_not_a_problem():
    libs = audit.parse_libs(OTOOL_L_DYLIB)
    own = audit.parse_install_name(cmds(dylib_id="/Users/runner/build/libfoo.dylib"))
    assert own == "/Users/runner/build/libfoo.dylib"
    assert audit.bad_libs(libs, own) == []
    assert audit.bad_libs(libs, None) == ["/Users/runner/build/libfoo.dylib"]


def test_parse_minos():
    assert audit.parse_minos(cmds("14.0")) == "14.0"
    assert audit.parse_minos(cmds(None, legacy="10.9")) == "10.9"
    assert audit.parse_minos(cmds(None)) is None
    assert audit.parse_minos(cmds("11.0", legacy="10.9")) == "11.0"
    assert audit.version_key("14.0") > audit.version_key("13.6.1") > audit.version_key("11.0")
    assert audit.version_key("10.15") < audit.version_key("11.0")


def fake_app(tmp_path, names=("a.so", "b.dylib", "main")):
    app = tmp_path / "X.app" / "Contents" / "MacOS"
    app.mkdir(parents=True)
    for n in names:
        (app / n).write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 16)
    (app / "data.txt").write_text("not macho")
    (app / "link.so").symlink_to(app / "a.so")
    return tmp_path / "X.app"


def runner(archs=None, libs=None, cmd=None):
    archs, libs, cmd = archs or {}, libs or {}, cmd or {}

    def run(argv):
        tool, path = argv[0], argv[-1]
        name = Path(path).name
        if tool == "lipo":
            return 0, archs.get(name, "arm64") + "\n"
        if "-L" in argv:
            return 0, libs.get(name, OTOOL_L_OK)
        return 0, cmd.get(name, cmds("11.0"))

    return run


def test_audit_passes(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "14.0", runner(archs={"b.dylib": "x86_64 arm64"}))
    assert r["files"] == 3 and r["fat"] == 1 and r["problems"] == []
    assert r["max_minos"] == "11.0"
    assert "0 problem(s)" in audit.format_report(r)


def test_audit_fails_on_bad_load_path(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "14.0", runner(libs={"a.so": OTOOL_L_BAD}))
    assert len(r["problems"]) == 2 and "a.so" in r["problems"][0]


def test_audit_fails_on_missing_arm64(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "14.0", runner(archs={"main": "x86_64"}))
    assert len(r["problems"]) == 1 and "no arm64 slice" in r["problems"][0]


def test_audit_fails_on_minos_above_declared(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "14.0", runner(cmd={"a.so": cmds("15.0")}))
    assert r["max_minos"] == "15.0" and "above the declared 14.0" in r["problems"][0]
    ok = audit.audit(str(app), "14.0", runner(cmd={"a.so": cmds("14.0")}))
    assert ok["problems"] == []


def test_audit_unknown_minos_is_reported_not_failed(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "14.0", runner(cmd={"a.so": cmds(None)}))
    assert r["problems"] == [] and r["unknown_minos"] == ["Contents/MacOS/a.so"]


def test_audit_legacy_version_min_is_read(tmp_path):
    app = fake_app(tmp_path)
    r = audit.audit(str(app), "9.0", runner(cmd={"a.so": cmds(None, legacy="10.9")}))
    assert any("a.so" in p and "10.9" in p for p in r["problems"])


def test_audit_tool_failure_is_a_problem(tmp_path):
    app = fake_app(tmp_path, names=("a.so",))
    r = audit.audit(str(app), "14.0", lambda argv: (1, "boom"))
    assert len(r["problems"]) == 1 and "lipo failed" in r["problems"][0]


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    app = fake_app(tmp_path)
    monkeypatch.setattr(audit, "run_tool", runner(archs={"main": "x86_64"}))
    assert audit.main([str(app), "--min-os", "14.0"]) == 1
    assert audit.main([str(app), "--min-os", "14.0", "--report-only"]) == 0
    assert "PROBLEM" in capsys.readouterr().out
    assert audit.main([str(tmp_path / "nope"), "--min-os", "14.0"]) == 2


def test_main_reads_min_os_from_product_json(tmp_path, monkeypatch):
    app = fake_app(tmp_path)
    pj = tmp_path / "product.json"
    pj.write_text('{"min_os": "10.0"}')
    monkeypatch.setattr(audit, "run_tool", runner())
    assert audit.main([str(app), "--product-json", str(pj)]) == 1  # minos 11.0 > 10.0


def test_info_plist_keys_and_values():
    values = render.load(REPO, {"version": "0.11.9.dev33"})
    plist = info_plist.info_plist(values)
    assert set(plist) == {
        "CFBundleName",
        "CFBundleDisplayName",
        "CFBundleShortVersionString",
        "CFBundleVersion",
        "LSMinimumSystemVersion",
        "LSApplicationCategoryType",
        "NSHumanReadableCopyright",
        "NSHighResolutionCapable",
        "LSAppNapIsDisabled",
        "NSAppTransportSecurity",
    }
    assert plist["CFBundleName"] == plist["CFBundleDisplayName"] == "GleepGlorp AI"
    assert plist["CFBundleShortVersionString"] == "0.11.9"
    assert plist["CFBundleVersion"] == "0.11.90033"
    assert plist["LSMinimumSystemVersion"] == "14.0"
    assert plist["LSApplicationCategoryType"] == "public.app-category.productivity"
    assert plist["NSHumanReadableCopyright"] == (
        "Copyright © GleepGlorp AI contributors. MIT License."
    )
    assert plist["NSHighResolutionCapable"] is True
    assert plist["LSAppNapIsDisabled"] is True
    assert plist["NSAppTransportSecurity"] == {"NSAllowsLocalNetworking": True}


def test_info_plist_follows_the_render_values():
    values = dict(render.load(REPO))
    values.update(bundle_name="Other", min_os="15.0", bundle_version="1.2.3")
    plist = info_plist.info_plist(values)
    assert plist["CFBundleName"] == "Other" and plist["LSMinimumSystemVersion"] == "15.0"
    assert plist["CFBundleVersion"] == "1.2.3"


def test_spec_has_no_pystray_and_reads_the_product_json():
    spec = (MACOS / "the-one.spec").read_text(encoding="utf-8")
    assert "pystray" not in spec.replace("so pystray is not collected at all", "")
    assert "M32_PRODUCT_JSON" in spec and "info_plist(PRODUCT)" in spec
    assert "ai.gleepglorp.the-one" not in spec and '"11.0"' not in spec


# ── frozen_entry_mac.py's log redirect ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def entry():
    return _load("macos_frozen_entry", MACOS / "frozen_entry_mac.py")


class Stream:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


def test_log_dir_name_is_the_bundle_name(entry):
    assert entry.LOG_DIR_NAME == render.load(REPO)["bundle_name"]


def test_tty_means_no_redirect(entry, tmp_path):
    assert entry.redirect_app_log(["app"], Stream(True), tmp_path) is None
    assert not (tmp_path / "Library").exists()


def test_other_commands_are_not_redirected(entry, tmp_path):
    assert entry.redirect_app_log(["doctor"], Stream(False), tmp_path) is None
    assert entry.redirect_app_log([], Stream(False), tmp_path) is None


def test_non_tty_app_launch_appends_to_the_log(entry, tmp_path):
    first = entry.redirect_app_log(["app"], Stream(False), tmp_path)
    first.write("one\n")
    first.close()
    second = entry.redirect_app_log(["app"], Stream(False), tmp_path)
    second.write("two\n")
    second.close()
    path = tmp_path / "Library" / "Logs" / "GleepGlorp AI" / "app.log"
    assert path == entry.app_log_path(tmp_path)
    assert path.read_text() == "one\ntwo\n"


def test_none_stderr_counts_as_not_a_terminal(entry, tmp_path):
    log = entry.redirect_app_log(["app"], io.StringIO(), tmp_path)
    assert log is not None
    log.close()


def test_oversized_log_is_truncated_at_start(entry, tmp_path):
    path = entry.app_log_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("x" * 100)
    log = entry.redirect_app_log(["app"], Stream(False), tmp_path, max_bytes=50)
    log.write("fresh\n")
    log.close()
    assert path.read_text() == "fresh\n"
    path.write_text("x" * 40)
    log = entry.redirect_app_log(["app"], Stream(False), tmp_path, max_bytes=50)
    log.write("more\n")
    log.close()
    assert path.read_text() == "x" * 40 + "more\n"


def test_redirect_failure_falls_back_to_current_streams(entry, tmp_path):
    blocker = tmp_path / "Library"
    blocker.write_text("a file where a directory must go")
    assert entry.redirect_app_log(["app"], Stream(False), tmp_path) is None


def test_launch_args_unchanged(entry):
    assert entry.launch_args([]) == ["app"]
    assert entry.launch_args(["-psn_0_123"]) == ["app"]
    assert entry.launch_args(["doctor"]) == ["doctor"]
