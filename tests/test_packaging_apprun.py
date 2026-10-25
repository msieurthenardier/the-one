"""AppRun self-integration (Mission 32 Flight 2 leg 7, DD5): the real rendered AppRun, run
with sh against a fake AppDir."""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
LINUX = REPO / "packaging" / "linux"

_spec = importlib.util.spec_from_file_location("packaging_render", REPO / "packaging" / "render.py")
render = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = render
_spec.loader.exec_module(render)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")


@pytest.fixture
def world(tmp_path):
    values = render.load(REPO)
    appdir = tmp_path / "appdir"
    stub = appdir / "usr" / "lib" / values["package"] / values["executable"]
    stub.parent.mkdir(parents=True)
    stub.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" > "$OUTFILE"\n'
        'printf "%s\\n" "${XDG_ACTIVATION_TOKEN:-}" > "$OUTFILE.token"\n'
    )
    stub.chmod(0o755)
    share = appdir / "usr" / "share" / values["package"]
    share.mkdir(parents=True)
    (share / "integration.desktop.in").write_text(
        render.render((LINUX / "appimage.desktop.in").read_text(encoding="utf-8"), values),
        encoding="utf-8",
    )
    (appdir / f"{values['desktop_id']}.png").write_bytes(b"\x89PNG fake")
    run = appdir / "AppRun"
    run.write_text(render.render((LINUX / "AppRun.in").read_text(encoding="utf-8"), values))
    run.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    data = tmp_path / "data"
    img = tmp_path / "My App" / "G.AppImage"
    img.parent.mkdir()
    img.write_bytes(b"x")

    class W:
        pass

    w = W()
    w.tmp, w.appdir, w.home, w.data, w.img, w.values = tmp_path, appdir, home, data, img, values
    w.out = tmp_path / "out.txt"
    w.entry = data / "applications" / f"{values['appimage_desktop_id']}.desktop"
    w.icon = data / "icons/hicolor/512x512/apps" / f"{values['appimage_desktop_id']}.png"

    def go(*args, appimage="default", env_extra=None, unset=()):
        env = {
            "PATH": os.environ["PATH"],
            "HOME": str(home),
            "XDG_DATA_HOME": str(data),
            "APPDIR": str(appdir),
            "OUTFILE": str(w.out),
        }
        if appimage == "default":
            env["APPIMAGE"] = str(w.img)
        elif appimage is not None:
            env["APPIMAGE"] = appimage
        env.update(env_extra or {})
        for k in unset:
            env.pop(k, None)
        return subprocess.run(
            ["sh", str(run), *args], env=env, capture_output=True, text=True, timeout=30
        )

    w.go = go
    return w


def _validate(path):
    exe = shutil.which("desktop-file-validate")
    if exe:
        r = subprocess.run([exe, str(path)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_no_args_integrates_and_runs_app(world):
    r = world.go()
    assert r.returncode == 0, r.stderr
    assert world.out.read_text().strip() == "app"
    text = world.entry.read_text()
    assert f'Exec="{world.img}" app' in text
    assert f'Exec="{world.img}" quit' in text
    assert f"TryExec={world.img}" in text
    assert f"Icon={world.icon}" in text
    assert "Name=Quit GleepGlorp AI" in text
    assert world.icon.read_bytes() == b"\x89PNG fake"
    _validate(world.entry)


def test_app_argument_integrates(world):
    world.go("app")
    assert world.entry.is_file()
    assert world.out.read_text().strip() == "app"


def test_second_run_leaves_file_untouched(world):
    world.go()
    old = 1_000_000_000
    for p in (world.entry, world.icon):
        os.utime(p, ns=(old * 10**9, old * 10**9))
    world.go()
    assert world.entry.stat().st_mtime_ns == old * 10**9
    assert world.icon.stat().st_mtime_ns == old * 10**9


def test_moved_appimage_rewrites_entry(world):
    world.go()
    moved = world.tmp / "elsewhere" / "G2.AppImage"
    moved.parent.mkdir()
    moved.write_bytes(b"x")
    world.go(appimage=str(moved))
    assert f'Exec="{moved}" app' in world.entry.read_text()


@pytest.mark.parametrize(
    "name",
    ["a b", "d$ollar", 'q"uote', "back`tick", "back\\slash", "per%cent", "am&per", "p|ipe", "x'y"],
)
def test_awkward_paths_are_quoted(world, name):
    img = world.tmp / "odd" / f"{name}.AppImage"
    img.parent.mkdir()
    img.write_bytes(b"x")
    r = world.go(appimage=str(img))
    assert r.returncode == 0
    assert world.out.read_text().strip() == "app"
    text = world.entry.read_text()
    p = str(img)
    # Exec layer (backslash before " ` $ \), then string layer (\ doubled, % doubled)
    ex = "".join("\\" + c if c in '"`$\\' else c for c in p)
    ex = ex.replace("\\", "\\\\").replace("%", "%%")
    assert f'Exec="{ex}" app' in text
    assert f"TryExec={p.replace(chr(92), chr(92) * 2)}" in text
    _validate(world.entry)


@pytest.mark.parametrize("bad", ["new\nline", "tab\there"])
def test_control_character_path_skips_integration(world, bad):
    img = world.tmp / "odd" / f"{bad}.AppImage"
    img.parent.mkdir()
    img.write_bytes(b"x")
    r = world.go(appimage=str(img))
    assert r.returncode == 0
    assert world.out.read_text().strip() == "app"
    assert not world.entry.exists() and not world.icon.exists()


def test_quit_and_others_pass_through_without_integration(world):
    for arg in ("quit", "doctor", "version"):
        world.out.unlink(missing_ok=True)
        world.go(arg, "--flag")
        assert world.out.read_text().strip() == f"{arg} --flag"
    assert not world.entry.exists()


def test_appimage_unset_still_runs(world):
    r = world.go(appimage=None)
    assert r.returncode == 0
    assert world.out.read_text().strip() == "app"
    assert not world.data.exists()


def test_appimage_not_a_file_still_runs(world):
    world.go(appimage=str(world.tmp / "missing"))
    assert world.out.read_text().strip() == "app"
    assert not world.data.exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_read_only_data_home_does_not_stop_launch(world):
    world.data.mkdir()
    world.data.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        r = world.go()
    finally:
        world.data.chmod(0o755)
    assert r.returncode == 0
    assert world.out.read_text().strip() == "app"
    assert not world.entry.exists()


def test_relative_xdg_data_home_is_ignored(world):
    world.go(env_extra={"XDG_DATA_HOME": "relative/data"})
    fallback = world.home / ".local/share/applications" / world.entry.name
    assert fallback.is_file()


def test_activation_token_reaches_app(world):
    world.go(env_extra={"XDG_ACTIVATION_TOKEN": "tok-123"})
    assert world.out.with_name("out.txt.token").read_text().strip() == "tok-123"
