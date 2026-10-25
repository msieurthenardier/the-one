"""Pins for the packaging metadata (Mission 32 Flight 2 leg 7, Flight 3 leg 6; DD6, DD8)."""

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
    "app_id",
    "bundle_name",
    "bundle_executable",
    "dmg_file_stem",
    "min_os",
    "bundle_category",
    "version",
    "deb_version",
    "bundle_short_version",
    "bundle_version",
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


def _write_repo(tmp_path, toml, version="0.11.8"):
    (tmp_path / "packaging").mkdir()
    (tmp_path / "packaging" / "product.toml").write_text(toml, encoding="utf-8")
    (tmp_path / "the_one").mkdir()
    (tmp_path / "the_one" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    return tmp_path


def test_app_id_and_macos_keys():
    values = render.load(REPO)
    assert values["app_id"] == "ai.gleepglorp.GleepGlorpAI"
    assert "metainfo_id" not in values
    assert values["min_os"] == "14.0"
    assert values["bundle_name"] == "GleepGlorp AI"
    assert values["bundle_executable"] == "the-one"
    assert values["dmg_file_stem"] == "GleepGlorp_AI"
    assert values["bundle_category"] == "public.app-category.productivity"


def test_key_repeated_across_sections_is_rejected(tmp_path):
    repo = _write_repo(tmp_path, '[linux]\nexecutable = "a"\n[macos]\nexecutable = "b"\n')
    with pytest.raises(render.RenderError, match="executable.*appears twice"):
        render.load(repo)


def test_key_repeated_between_section_and_top_level_is_rejected(tmp_path):
    repo = _write_repo(tmp_path, 'app_id = "x"\n[macos]\napp_id = "y"\n')
    with pytest.raises(render.RenderError, match="app_id.*appears twice"):
        render.load(repo)


def test_derived_key_in_toml_is_rejected(tmp_path):
    repo = _write_repo(tmp_path, 'bundle_version = "1"\n')
    with pytest.raises(render.RenderError, match="derived"):
        render.load(repo)


def _numeric(v):
    return tuple(int(p) for p in v.split("."))


def test_bundle_version_mapping_follows_pep440_order():
    versions = [
        "0.11.8.dev1",
        "0.11.8.dev9998",
        "0.11.8",
        "0.11.9.dev1",
        "0.11.9.dev2",
        "0.11.9",
        "0.11.10.dev1",
        "0.12.0.dev1",
        "0.12.0",
        "1.0.0.dev1",
    ]
    mapped = [render.bundle_version(v) for v in versions]
    assert all(len(m.split(".")) == 3 for m in mapped)
    assert [_numeric(m) for m in mapped] == sorted(_numeric(m) for m in mapped)
    assert len(set(mapped)) == len(mapped)
    assert render.bundle_version("0.11.9.dev1") == "0.11.90001"
    assert render.bundle_version("0.11.9") == "0.11.99999"
    assert render.bundle_version("0.11.10.dev1") == "0.11.100001"


def test_bundle_short_version_is_the_release_triplet():
    assert render.bundle_short_version("0.11.9.dev33") == "0.11.9"
    assert render.bundle_short_version("0.11.8") == "0.11.8"
    values = render.load(REPO, {"version": "0.11.9.dev33"})
    assert values["bundle_short_version"] == "0.11.9"
    assert values["bundle_version"] == "0.11.90033"


@pytest.mark.parametrize(
    "bad",
    [
        "0.11.9a1",
        "0.11.9b2",
        "0.11.9rc1",
        "0.11.9.post1",
        "0.11.9.dev9999",
        "0.11.9.dev10000",
        "1.0",
    ],
)
def test_bundle_version_refusals(bad):
    with pytest.raises(render.RenderError):
        render.bundle_version(bad)
    with pytest.raises(render.RenderError):
        render.bundle_short_version(bad)


def test_next_version_helper():
    assert render.next_version("0.11.9.dev33") == "0.11.9.dev34"
    assert render.next_version("0.11.8") == "0.11.9.dev1"
    with pytest.raises(render.RenderError):
        render.next_version("0.11.9.dev9998")
    with pytest.raises(render.RenderError):
        render.next_version("0.11.9rc1")


@pytest.mark.parametrize("n", ["0.11.8", "0.11.9.dev1", "0.11.9.dev33"])
def test_next_version_sorts_above_and_round_trips(n):
    up = render.next_version(n)
    assert _numeric(render.bundle_version(up)) > _numeric(render.bundle_version(n))
    values = render.load(REPO, {"version": up})
    assert values["version"] == up
    assert values["bundle_version"] == render.bundle_version(up)
    cli = subprocess.run(
        [sys.executable, str(REPO / "packaging" / "render.py"), "--next-version", n],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert cli == up


def test_metainfo_id_is_app_id():
    tpl = (LINUX / "metainfo.xml.in").read_text(encoding="utf-8")
    out = render.render(tpl, render.load(REPO), xml=True)
    assert "<id>ai.gleepglorp.GleepGlorpAI</id>" in out
    assert "METAINFO_ID" not in (LINUX / "build.env.in").read_text(encoding="utf-8")
    assert "METAINFO_ID" not in (LINUX / "build-inner.sh").read_text(encoding="utf-8")
