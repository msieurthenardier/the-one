#!/usr/bin/env python3
"""Select the four release packages for a version and write SHA256SUMS (Mission 32 Flight 4).

    release_assets.py --version V --dir DIR --out OUT

DIR holds the downloaded artifacts (searched recursively). The four exact file names for V come
from ``packaging/render.py`` and ``packaging/product.toml`` (never a glob, never a guess):

    the-one-setup-<V>.exe
    GleepGlorp_AI-<V>-arm64.dmg
    GleepGlorp_AI-<V>-x86_64.AppImage
    gleepglorp-ai_<deb_version>_amd64.deb

A missing package, or a package file of any other name or version, is an error. Exactly the four
files are copied to OUT (outside DIR) with SHA256SUMS (``sha256sum -c`` format); the
paths of the five files are printed, one per line. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE_SUFFIXES = (".exe", ".dmg", ".appimage", ".deb")


class AssetError(Exception):
    pass


def _load_render(repo: Path):
    spec = importlib.util.spec_from_file_location(
        "release_assets_render", Path(repo) / "packaging" / "render.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def asset_names(version: str, repo: Path = REPO) -> list[str]:
    v = _load_render(repo).load(repo, {"version": version})
    return [
        f"{v['setup_file_stem']}-{v['version']}.exe",
        f"{v['dmg_file_stem']}-{v['version']}-arm64.dmg",
        f"{v['appimage_file_stem']}-{v['version']}-x86_64.AppImage",
        f"{v['package']}_{v['deb_version']}_amd64.deb",
    ]


def select(version: str, directory: Path, repo: Path = REPO) -> dict[str, Path]:
    wanted = asset_names(version, repo)
    found: dict[str, list[Path]] = {}
    extra: list[Path] = []
    for path in sorted(Path(directory).rglob("*")):
        if not path.is_file():
            continue
        if path.name in wanted:
            found.setdefault(path.name, []).append(path)
        elif path.suffix.lower() in PACKAGE_SUFFIXES:
            extra.append(path)
    problems = []
    problems += [f"missing: {name}" for name in wanted if name not in found]
    problems += [f"duplicate: {name} ({len(p)} copies)" for name, p in found.items() if len(p) > 1]
    problems += [f"unexpected package file: {p.name}" for p in extra]
    if problems:
        raise AssetError("; ".join(problems))
    return {name: found[name][0] for name in wanted}


def write_release_dir(version: str, directory: Path, out: Path, repo: Path = REPO) -> list[Path]:
    chosen = select(version, directory, repo)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lines = []
    files = []
    for name, src in chosen.items():
        dest = out / name
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}\n")
        files.append(dest)
    sums = out / "SHA256SUMS"
    sums.write_text("".join(lines), encoding="utf-8", newline="\n")
    return files + [sums]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=REPO)
    args = parser.parse_args(argv)
    try:
        files = write_release_dir(args.version, args.dir, args.out, args.repo)
    except Exception as exc:  # AssetError, or a render error: both fail the release
        print(f"release assets: {exc}", file=sys.stderr)
        return 1
    for f in files:
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
