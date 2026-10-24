"""Pins for the Linux packaging metadata (Mission 32 Flight 2 leg 7, DD6)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import platformdirs
import pytest

import the_one
from the_one.config import _default_data_dir

REPO = Path(__file__).resolve().parents[1]
LINUX = REPO / "packaging" / "linux"
RUNTIME_KEYS = {"@APPIMAGE_EXEC@", "@APPIMAGE_PATH@", "@ICON_PATH@", "@INSTALLED_SIZE@"}


def _load_render():
    spec = importlib.util.spec_from_file_location(
        "packaging_render", REPO / "packaging" / "render.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


render = _load_render()
REQUIRED = [
    "display_name",
    "summary",
    "description",
    "maintainer",
    "homepage",
    "license",
    "icon_source",
    "data_slug",
    "package",
    "desktop_id",
    "appimage_desktop_id",
    "appimage_name",
    "appimage_file_stem",
    "install_dir",
    "executable",
    "wm_class",
    "categories",
    "quit_action_name",
    "metainfo_id",
    "version",
    "deb_version",
    "release_date",
]


def test_required_keys_present():
    values = render.load(REPO)
    for key in REQUIRED:
        assert values.get(key), key


def test_data_slug_matches_config():
    values = render.load(REPO)
    assert Path(platformdirs.user_data_dir(values["data_slug"], appauthor=False)) == (
        _default_data_dir()
    )


def test_pyproject_version_matches_dunder_version():
    with open(REPO / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == the_one.__version__
    assert render.load(REPO)["version"] == the_one.__version__


def test_license_matches_pyproject():
    with open(REPO / "pyproject.toml", "rb") as fh:
        project = tomllib.load(fh)["project"]
    assert render.load(REPO)["license"] == project["license"] == "MIT"
    assert (REPO / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def test_icon_source_exists():
    assert (REPO / render.load(REPO)["icon_source"]).is_file()


def test_deb_version_maps_dev():
    assert render.deb_version("0.11.9.dev1") == "0.11.9~dev1"
    assert render.deb_version("0.11.8") == "0.11.8"
    for bad in ("0.11.9a1", "0.11.9b2", "0.11.9rc1"):
        with pytest.raises(render.RenderError):
            render.deb_version(bad)


def test_unreplaced_key_raises():
    with pytest.raises(render.RenderError, match="NOPE"):
        render.render("x @NOPE@ y", {"version": "1"})


def test_email_is_not_a_placeholder():
    assert render.render("a <noreply@invalid> @VERSION@", {"version": "1"}) == (
        "a <noreply@invalid> 1"
    )


def test_set_version_overrides():
    values = render.load(REPO, {"version": "0.11.9.dev1"})
    assert values["version"] == "0.11.9.dev1"
    assert values["deb_version"] == "0.11.9~dev1"
    out = subprocess.run(
        [
            sys.executable,
            str(REPO / "packaging" / "render.py"),
            "--repo",
            str(REPO),
            "--json",
            "--set",
            "version=0.11.9.dev1",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(out)["deb_version"] == "0.11.9~dev1"


def test_release_date_from_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert render.load(REPO)["release_date"] == "2023-11-14"
    assert render.load(REPO, {"release_date": "2020-01-02"})["release_date"] == "2020-01-02"


def test_xml_templates_escape_values():
    assert render.render("<p>@SUMMARY@</p>", {"summary": "a & b <c>"}, xml=True) == (
        "<p>a &amp; b &lt;c&gt;</p>"
    )


@pytest.mark.parametrize("template", sorted(p.name for p in LINUX.glob("*.in")))
def test_every_template_renders(template):
    tpl = LINUX / template
    out = render.render(
        tpl.read_text(encoding="utf-8"), render.load(REPO), xml=template.endswith(".xml.in")
    )
    leftover = set(render.PLACEHOLDER_RE.findall(out))
    assert {f"@{k}@" for k in leftover} <= RUNTIME_KEYS, leftover
    if template == "appimage.desktop.in":
        assert "StartupNotify=true" in out and "Name=Quit GleepGlorp AI" in out
    if template == "control.in":
        assert "spike" not in out.lower()


def test_metainfo_category_derives_from_categories():
    tpl = (LINUX / "metainfo.xml.in").read_text(encoding="utf-8")
    values = render.load(REPO)
    entry = values["categories"].strip(";")
    assert f"<category>{entry}</category>" in render.render(tpl, values, xml=True)
    with pytest.raises(render.RenderError):
        render.load(REPO, {"categories": "Utility;Network;"})
