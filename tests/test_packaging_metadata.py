"""Pins for the packaging metadata (Mission 32 Flight 2 leg 7, Flight 3 leg 6; DD6, DD8)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
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


def test_pyproject_version_is_dynamic_from_dunder():
    with open(REPO / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    project = data["project"]
    assert "version" not in project, "the version lives only in the_one/__init__.py"
    assert project["dynamic"] == ["version"]
    assert data["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "the_one.__version__"}
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


# ---- the Windows recipe's metadata (Mission 32 Flight 4, leg 3) ----------------------------

WIN = REPO / "packaging" / "windows"
APP_GUID = "CAEEFB46-2698-4048-AD9F-0120D0B7174A"
WINDOWS_KEYS = [
    "app_guid",
    "install_dir_name",
    "setup_file_stem",
    "cli_executable",
    "gui_executable",
    "publisher",
]


def test_windows_keys_present_and_guid_pinned():
    values = render.load(REPO)
    for key in WINDOWS_KEYS:
        assert values[key], key
    # The upgrade/uninstall identity of every shipped install. NEVER change it.
    assert values["app_guid"] == APP_GUID
    assert values["setup_file_stem"] == "the-one-setup"
    assert (values["cli_executable"], values["gui_executable"]) == ("the-one", "the-one-app")
    assert values["install_dir_name"] == "GleepGlorp AI"


def test_appid_line_is_literal_and_equals_the_guid():
    iss = (WIN / "the-one.iss").read_text(encoding="utf-8")
    lines = [ln for ln in iss.splitlines() if ln.startswith("AppId=")]
    assert lines == ["AppId={{" + render.load(REPO)["app_guid"] + "}}"], lines
    # the line never goes through the preprocessor
    assert "{#" not in lines[0]
    assert "app_guid" not in (WIN / "product.iss.in").read_text(encoding="utf-8").lower()


def test_the_effective_appid_is_one_brace_pair_short_of_the_registry_key():
    # Inno reads "{{" as an escaped "{", so the effective AppId is "{GUID}}" (leg 1, W6); the
    # uninstall key therefore ends "}}_is1". The literal line above must stay as it ships.
    line = "AppId={{" + APP_GUID + "}}"
    effective = line.split("=", 1)[1].replace("{{", "{")
    assert effective == "{" + APP_GUID + "}}"


def test_out_writes_the_same_text_as_stdout(tmp_path, capsys):
    tpl = tmp_path / "x.txt.in"
    tpl.write_text("name=@DISPLAY_NAME@\r\nv=@VERSION@\n", encoding="utf-8")
    out = tmp_path / "x.txt"
    assert render.main(["--repo", str(REPO), "--template", str(tpl), "--set", "version=1.2.3"]) == 0
    stdout = capsys.readouterr().out
    assert (
        render.main(
            [
                "--repo",
                str(REPO),
                "--template",
                str(tpl),
                "--set",
                "version=1.2.3",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == ""
    raw = out.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "no BOM"
    assert b"\r" not in raw, "LF line endings only"
    assert raw.decode("utf-8") == stdout.replace("\r\n", "\n")
    assert raw == b"name=GleepGlorp AI\nv=1.2.3\n"


def test_out_errors_return_one(tmp_path, capsys):
    tpl = tmp_path / "bad.in"
    tpl.write_text("@NO_SUCH_KEY@", encoding="utf-8")
    out = tmp_path / "bad.out"
    assert render.main(["--repo", str(REPO), "--template", str(tpl), "--out", str(out)]) == 1
    assert "unreplaced placeholder" in capsys.readouterr().err
    assert not out.exists()
    missing = tmp_path / "gone" / "x.out"
    ok_tpl = tmp_path / "ok.in"
    ok_tpl.write_text("x", encoding="utf-8")
    assert render.main(["--repo", str(REPO), "--template", str(ok_tpl), "--out", str(missing)]) == 1


def test_out_needs_a_template():
    with pytest.raises(SystemExit):
        render.main(["--repo", str(REPO), "--json", "--out", "x"])


def test_iss_templates_double_quotes_and_refuse_newlines():
    assert render.render('#define A "@NAME@"', {"name": 'say "hi"'}, iss=True) == (
        '#define A "say ""hi"""'
    )
    # the other modes leave quotes alone
    assert render.render("@NAME@", {"name": '"'}) == '"'
    with pytest.raises(render.RenderError, match="newline"):
        render.render('#define A "@NAME@"', {"name": "a\nb"}, iss=True)
    with pytest.raises(render.RenderError, match="newline"):
        render.render('#define A "@NAME@"', {"name": "a\rb"}, iss=True)


def test_iss_in_render_goes_through_main_with_escaping(tmp_path):
    # the template name decides the mode: *.iss.in escapes, a plain *.in does not
    tpl = tmp_path / "t.iss.in"
    tpl.write_text('#define N "@DISPLAY_NAME@"\n', encoding="utf-8")
    out = tmp_path / "t.iss"
    assert render.main(["--repo", str(REPO), "--template", str(tpl), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == '#define N "GleepGlorp AI"\n'


def _expand(text: str, defines: dict[str, str]) -> str:
    """A tiny test-side ISPP: substitute ``{#Name}`` from the defines."""
    return re.sub(r"\{#(\w+)\}", lambda m: defines[m.group(1)], text)


def _parse_defines(include: str) -> dict[str, str]:
    out = {}
    for line in include.splitlines():
        m = re.match(r'^#define (\w+) "((?:[^"]|"")*)"$', line)
        if m:
            out[m.group(1)] = m.group(2).replace('""', '"')
    return out


def _section(iss: str, name: str) -> list[str]:
    lines, on = [], False
    for line in iss.splitlines():
        if line.startswith("["):
            on = line.strip() == f"[{name}]"
            continue
        if on and line.strip() and not line.startswith(";"):
            lines.append(line)
    return lines


def test_the_rendered_include_reproduces_todays_effective_installer_lines(tmp_path):
    version = "0.11.9.dev1"
    values = render.load(REPO, {"version": version})
    include = render.render((WIN / "product.iss.in").read_text(encoding="utf-8"), values, iss=True)
    defines = _parse_defines(include)
    defines["DistDir"] = "C:\\b\\dist"
    iss = (WIN / "the-one.iss").read_text(encoding="utf-8")
    setup = [_expand(ln, defines) for ln in _section(iss, "Setup")]
    # today's values (the 0.11.8 .iss), written here by hand: not a generated golden file
    for want in (
        "AppName=GleepGlorp AI",
        f"AppVersion={version}",
        f"AppVerName=GleepGlorp AI {version}",
        "DefaultDirName={autopf}\\GleepGlorp AI",
        "DefaultGroupName=GleepGlorp AI",
        f"OutputBaseFilename=the-one-setup-{version}",
    ):
        assert want in setup, want
    icons = [_expand(ln, defines) for ln in _section(iss, "Icons")]
    assert icons == [
        'Name: "{group}\\GleepGlorp AI"; Filename: "{app}\\the-one-app.exe"; '
        'IconFilename: "{app}\\the-one.ico"',
        'Name: "{group}\\Uninstall GleepGlorp AI"; Filename: "{uninstallexe}"',
        'Name: "{autodesktop}\\GleepGlorp AI"; Filename: "{app}\\the-one-app.exe"; '
        'IconFilename: "{app}\\the-one.ico"; Tasks: desktopicon',
    ]
    files = [_expand(ln, defines) for ln in _section(iss, "Files")]
    assert files[0] == (
        'Source: "C:\\b\\dist\\the-one\\*"; DestDir: "{app}"; '
        "Flags: recursesubdirs createallsubdirs ignoreversion"
    )
    run = [_expand(ln, defines) for ln in _section(iss, "Run")]
    assert run == [
        'Filename: "{app}\\the-one-app.exe"; Description: "Launch GleepGlorp AI"; '
        "Flags: nowait postinstall skipifsilent"
    ]
    # every {#Name} the .iss uses is defined by the include, plus DistDir from the command line
    used = set(
        re.findall(
            r"\{#(\w+)\}", "\n".join(ln for ln in iss.splitlines() if not ln.startswith(";"))
        )
    )
    assert used <= set(defines), used - set(defines)


def test_iss_has_no_version_fallback_and_requires_distdir():
    iss = (WIN / "the-one.iss").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in iss.splitlines() if not ln.startswith(";"))
    assert "#ifndef AppVersion" not in code and 'AppVersion "0.2.0"' not in code
    assert '#include "product.iss"' in code
    assert re.search(r"#ifndef DistDir\s+#error", code)
    assert "/DAppVersion" not in code


def test_product_iss_is_gitignored():
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "packaging/windows/product.iss" in ignore


def test_render_and_stage_agree_on_the_version(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "packaging_stage_v", REPO / "packaging" / "stage.py"
    )
    stage_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage_mod)
    version = render.load(REPO)["version"]
    src = tmp_path / "src"
    (src / "the_one").mkdir(parents=True)
    (src / "the_one" / "__init__.py").write_text(
        (REPO / "the_one" / "__init__.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    icon = src / stage_mod.ICON
    icon.parent.mkdir(parents=True)
    icon.write_bytes(b"png")
    env = {**os.environ, "M32_SOURCE": str(src)}
    for ver in (version, "0.11.9.dev1"):
        r = subprocess.run(
            [sys.executable, str(REPO / "packaging" / "stage.py"), "--version", ver,
             "--target", "windows", "--out", str(tmp_path / "out")],
            env=env, capture_output=True, text=True,
        )  # fmt: skip
        assert r.returncode == 0, r.stderr
        staged = tmp_path / "out" / f"stage-windows-{ver}"
        # the version render.py would read from the staged tree is the version asked for
        assert render.read_version(staged) == ver
        assert render.load(REPO, {"version": ver})["version"] == ver


def test_linux_build_dockerfile_pins_python_312_with_separated_args():
    """Squawk 0135 (review): the venv line once lost the space before the venv path."""
    text = (LINUX / "build.Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"^RUN uv python install 3\.12\.\d+ ", text, re.M), "uv python install"
    assert re.search(r"uv venv --python 3\.12\.\d+ /opt/venv\b", text), "uv venv --python line"
