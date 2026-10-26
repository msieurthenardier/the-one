"""The release version gate and asset selection (Mission 32 Flight 4 leg 4, DD6, DD7)."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"t_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


check = _load("release_check")
assets = _load("release_assets")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def fake_repo(tmp_path):
    """A tmp git repo with the real packaging/ and a chosen __version__; 'origin/main' is a ref."""

    def make(version: str = "0.12.0") -> Path:
        repo = tmp_path / "repo"
        (repo / "the_one").mkdir(parents=True)
        (repo / "packaging").mkdir()
        for name in ("render.py", "product.toml"):
            (repo / "packaging" / name).write_bytes((REPO / "packaging" / name).read_bytes())
        (repo / "the_one" / "__init__.py").write_text(f'__version__ = "{version}"\n')
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@invalid")
        _git(repo, "config", "user.name", "t")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "base")
        _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        return repo

    return make


def test_tag_equal_to_dunder_version(fake_repo):
    repo = fake_repo("0.12.0")
    assert check.gate("push", "refs/tags/v0.12.0", repo=repo) == "0.12.0"


def test_tag_not_equal_to_dunder_version(fake_repo):
    repo = fake_repo("0.12.0")
    with pytest.raises(check.GateError, match="does not match"):
        check.gate("push", "refs/tags/v0.12.1", repo=repo)


def test_dev_tag_is_refused(fake_repo):
    repo = fake_repo("0.12.0.dev1")
    with pytest.raises(check.GateError, match="dev version"):
        check.gate("push", "refs/tags/v0.12.0.dev1", repo=repo)


def test_rc_tag_is_refused(fake_repo):
    repo = fake_repo("0.12.0rc1")
    with pytest.raises(check.GateError):
        check.gate("push", "refs/tags/v0.12.0rc1", repo=repo)


def test_push_needs_a_tag_ref(fake_repo):
    repo = fake_repo()
    with pytest.raises(check.GateError, match="refs/tags/v"):
        check.gate("push", "refs/heads/main", repo=repo)


def test_tag_not_an_ancestor_of_main_is_refused(fake_repo):
    repo = fake_repo("0.12.0")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "x.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side commit, not on main")
    with pytest.raises(check.GateError, match="not an ancestor"):
        check.gate("push", "refs/tags/v0.12.0", repo=repo)
    # the same commit, once main has it, passes
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert check.gate("push", "refs/tags/v0.12.0", repo=repo) == "0.12.0"


def test_dispatch_on_a_tag_ref_is_a_dry_run(fake_repo):
    repo = fake_repo("0.12.0")
    # a workflow_dispatch --ref v0.12.0 takes the dispatch path: no tag equality, no ancestor
    # check; a dev input is fine, and so is the empty input.
    assert (
        check.gate("workflow_dispatch", "refs/tags/v0.12.0", "0.12.0.dev1", "windows", repo=repo)
        == "0.12.0.dev1"
    )
    assert check.gate("workflow_dispatch", "refs/tags/v0.12.0", "", "linux", repo=repo) == "0.12.0"
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    assert check.gate("workflow_dispatch", "refs/tags/v9.9.9", "", repo=repo) == "0.12.0"


@pytest.mark.parametrize("bad", ["0.12", "0.12.0rc1", "v0.12.0", "0.12.0.post1", "0.12.0.dev9999"])
def test_dispatch_refuses_bad_versions(fake_repo, bad):
    repo = fake_repo()
    with pytest.raises(check.GateError):
        check.gate("workflow_dispatch", "refs/heads/x", bad, repo=repo)


def test_unknown_event_is_refused(fake_repo):
    with pytest.raises(check.GateError, match="unsupported event"):
        check.gate("pull_request", "refs/heads/x", repo=fake_repo())


@pytest.mark.parametrize("platforms", ["windows,linux,macos", "macos", "linux,windows"])
def test_platforms_accepted(platforms):
    assert check.check_platforms(platforms) == platforms.split(",")


@pytest.mark.parametrize(
    "platforms", ["", ",", "windows,", "windows, linux", "Windows", "freebsd", "windows,,linux"]
)
def test_platforms_refused(platforms):
    with pytest.raises(check.GateError, match="platforms"):
        check.check_platforms(platforms)


def test_dispatch_validates_platforms(fake_repo):
    with pytest.raises(check.GateError, match="platforms"):
        check.gate("workflow_dispatch", "refs/heads/x", "", "", repo=fake_repo())


def test_derived_values_for_a_final_release():
    render = check.load_render(REPO)
    values = render.load(REPO, {"version": "0.12.0"})
    assert values["bundle_version"] == "0.12.9999"
    assert values["bundle_short_version"] == "0.12.0"
    assert values["deb_version"] == "0.12.0"
    assert render.load(REPO, {"version": "0.12.0.dev1"})["deb_version"] == "0.12.0~dev1"


def test_cli_prints_version_or_fails(fake_repo):
    repo = fake_repo("0.12.0")
    script = REPO / "scripts" / "release_check.py"
    ok = subprocess.run(
        [sys.executable, str(script), "--repo", str(repo), "--event", "push",
         "--ref", "refs/tags/v0.12.0"],
        capture_output=True, text=True,
    )  # fmt: skip
    assert ok.returncode == 0 and ok.stdout.strip() == "0.12.0"
    bad = subprocess.run(
        [sys.executable, str(script), "--repo", str(repo), "--event", "push",
         "--ref", "refs/tags/v0.12.1"],
        capture_output=True, text=True,
    )  # fmt: skip
    assert bad.returncode == 1 and bad.stdout == "" and "release gate:" in bad.stderr


def test_script_does_not_import_packaging_render():
    import ast

    for name in ("release_check", "release_assets"):
        tree = ast.parse((REPO / "scripts" / f"{name}.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] != "packaging" for a in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "packaging"


# ---- release_assets -------------------------------------------------------------------------


def _populate(root: Path, names: list[str]) -> None:
    for i, name in enumerate(names):
        sub = root / f"art{i % 3}"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / name).write_bytes(name.encode())


def test_asset_names_for_a_final_and_a_dev_version():
    assert assets.asset_names("0.12.0", REPO) == [
        "the-one-setup-0.12.0.exe",
        "GleepGlorp_AI-0.12.0-arm64.dmg",
        "GleepGlorp_AI-0.12.0-x86_64.AppImage",
        "gleepglorp-ai_0.12.0_amd64.deb",
    ]
    assert assets.asset_names("0.12.0.dev1", REPO)[3] == "gleepglorp-ai_0.12.0~dev1_amd64.deb"


def test_asset_selection_writes_sha256sums(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    names = assets.asset_names("0.12.0", REPO)
    _populate(src, names)
    (src / "art0" / "build.log").write_text("not a package")
    files = assets.write_release_dir("0.12.0", src, out, REPO)
    assert [f.name for f in files] == [*names, "SHA256SUMS"]
    lines = (out / "SHA256SUMS").read_text().splitlines()
    assert lines == [f"{hashlib.sha256(n.encode()).hexdigest()}  {n}" for n in names]


def test_asset_selection_refuses_a_missing_file(tmp_path):
    names = assets.asset_names("0.12.0", REPO)
    _populate(tmp_path / "src", names[:3])
    with pytest.raises(assets.AssetError, match="missing: gleepglorp-ai_0.12.0_amd64.deb"):
        assets.select("0.12.0", tmp_path / "src", REPO)


def test_asset_selection_refuses_an_extra_or_other_version_package(tmp_path):
    names = assets.asset_names("0.12.0", REPO)
    _populate(tmp_path / "src", [*names, "the-one-setup-0.11.9.dev1.exe"])
    with pytest.raises(assets.AssetError, match="unexpected package file"):
        assets.select("0.12.0", tmp_path / "src", REPO)


def test_asset_selection_refuses_duplicates(tmp_path):
    names = assets.asset_names("0.12.0", REPO)
    _populate(tmp_path / "src", names)
    other = tmp_path / "src" / "again"
    other.mkdir()
    (other / names[0]).write_bytes(b"x")
    with pytest.raises(assets.AssetError, match="duplicate"):
        assets.select("0.12.0", tmp_path / "src", REPO)


def test_asset_cli(tmp_path):
    names = assets.asset_names("0.12.0.dev1", REPO)
    _populate(tmp_path / "src", names)
    script = REPO / "scripts" / "release_assets.py"
    r = subprocess.run(
        [sys.executable, str(script), "--version", "0.12.0.dev1", "--dir", str(tmp_path / "src"),
         "--out", str(tmp_path / "out")],
        capture_output=True, text=True,
    )  # fmt: skip
    assert r.returncode == 0, r.stderr
    assert len(r.stdout.split()) == 5
    r2 = subprocess.run(
        [sys.executable, str(script), "--version", "0.12.0", "--dir", str(tmp_path / "src"),
         "--out", str(tmp_path / "out2")],
        capture_output=True, text=True,
    )  # fmt: skip
    assert r2.returncode == 1 and "release assets:" in r2.stderr
