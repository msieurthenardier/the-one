#!/usr/bin/env python3
"""Render packaging templates from packaging/product.toml (Mission 32, DD6).

Stdlib only (tomllib, Python 3.11 or newer).

    render.py --repo R --template T [--set K=V ...]   print the rendered template
    render.py --repo R --json [--set K=V ...]         print the values as JSON
    render.py --next-version V                        print the next dev version above V

A template holds ``@KEY@`` placeholders (uppercase letters, digits and underscores,
starting with a letter, so an address such as ``noreply@invalid`` is never touched). A key
with no value is an error, except the RESERVED names, which are filled later (at install
time by AppRun, or by build-inner.sh) and are left as they are unless ``--set`` gives them
a value. A template whose name ends in ``.xml.in`` has its values XML-escaped.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import tomllib
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"@([A-Z][A-Z0-9_]*)@")
VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]*)"\s*$', re.MULTILINE)
DEV_RE = re.compile(r"^\d+(\.\d+)*(\.dev\d+)?$")
RELEASE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$")
FINAL_BUILD = 9999  # the CFBundleVersion slot of a final release: above every dev number
DERIVED = (
    "version",
    "deb_version",
    "release_date",
    "appstream_category",
    "bundle_short_version",
    "bundle_version",
)
RESERVED = ("APPIMAGE_EXEC", "APPIMAGE_PATH", "ICON_PATH", "INSTALLED_SIZE")


class RenderError(Exception):
    pass


def read_version(repo: Path) -> str:
    text = (Path(repo) / "the_one" / "__init__.py").read_text(encoding="utf-8")
    hits = VERSION_RE.findall(text)
    if len(hits) != 1:
        raise RenderError(f"expected exactly one __version__ line, found {len(hits)}")
    return hits[0]


def deb_version(version: str) -> str:
    """PEP 440 to Debian: ``0.11.9.dev1`` -> ``0.11.9~dev1`` (sorts below 0.11.9)."""
    if not DEV_RE.match(version):
        raise RenderError(f"unsupported version form for a Debian package: {version!r}")
    return version.replace(".dev", "~dev")


def _release_parts(version: str) -> tuple[int, int, int, int | None]:
    m = RELEASE_RE.match(version)
    if not m:
        raise RenderError(
            f"unsupported version form for a macOS bundle: {version!r} "
            "(only X.Y.Z and X.Y.Z.devN; no a/b/rc/.postN)"
        )
    major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
    dev = int(m.group(4)) if m.group(4) is not None else None
    if dev is not None and dev >= FINAL_BUILD:
        raise RenderError(f"dev number {dev} in {version!r} is {FINAL_BUILD} or more")
    return major, minor, patch, dev


def bundle_short_version(version: str) -> str:
    """CFBundleShortVersionString: the release triplet (``0.11.9.dev1`` -> ``0.11.9``)."""
    major, minor, patch, _ = _release_parts(version)
    return f"{major}.{minor}.{patch}"


def bundle_version(version: str) -> str:
    """CFBundleVersion: three integers, ``major.minor.(patch * 10000 + n)``.

    ``n`` is the dev number, or 9999 for a final release, so ``0.11.9.dev1`` (0.11.90001)
    sorts below ``0.11.9`` (0.11.99999), which sorts below ``0.11.10.dev1`` (0.11.100001).
    """
    major, minor, patch, dev = _release_parts(version)
    return f"{major}.{minor}.{patch * 10000 + (FINAL_BUILD if dev is None else dev)}"


def next_version(version: str) -> str:
    """The next dev version above ``version`` (the upgrade rehearsal's N+1).

    A dev version gets its dev number plus one; a final one gets the next patch's ``.dev1``,
    so ``0.11.8`` -> ``0.11.9.dev1`` (CFBundleVersion 0.11.90001 > 0.11.89999).
    """
    major, minor, patch, dev = _release_parts(version)
    if dev is None:
        return f"{major}.{minor}.{patch + 1}.dev1"
    if dev + 1 >= FINAL_BUILD:
        raise RenderError(f"no dev number above {version!r}")
    return f"{major}.{minor}.{patch}.dev{dev + 1}"


def release_date(override: str | None = None) -> str:
    if override:
        return override
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return _dt.datetime.fromtimestamp(int(epoch), _dt.timezone.utc).strftime("%Y-%m-%d")
    return _dt.date.today().isoformat()


def appstream_category(categories: str) -> str:
    """AppStream takes one category; derive it from the desktop ``categories`` value."""
    entries = [c for c in categories.split(";") if c.strip()]
    if len(entries) != 1:
        raise RenderError(f"categories must have exactly one entry, got {categories!r}")
    return entries[0].strip()


def load(repo: Path | str, overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return the flat value map (lowercase keys). ``overrides`` win over everything."""
    repo = Path(repo)
    with open(repo / "packaging" / "product.toml", "rb") as fh:
        raw = tomllib.load(fh)
    values: dict[str, str] = {}
    owner: dict[str, str] = {}

    def put(key: str, val: object, where: str) -> None:
        if key in owner:
            raise RenderError(f"key {key!r} appears twice: in {owner[key]} and in {where}")
        if key in DERIVED:
            raise RenderError(f"key {key!r} in {where} is derived by render.py")
        owner[key] = where
        values[key] = str(val)

    for key, val in raw.items():
        if not isinstance(val, dict):
            put(key, val, "the top level")
    for section, table in raw.items():
        if isinstance(table, dict):
            for key, val in table.items():
                put(key, val, f"[{section}]")
    overrides = dict(overrides or {})
    values["version"] = overrides.pop("version", None) or read_version(repo)
    values["deb_version"] = deb_version(values["version"])
    values["bundle_short_version"] = bundle_short_version(values["version"])
    values["bundle_version"] = bundle_version(values["version"])
    values["release_date"] = release_date(overrides.pop("release_date", None))
    values.update(overrides)
    values["appstream_category"] = appstream_category(values["categories"])
    return values


def render(template: str, values: dict[str, str], *, xml: bool = False) -> str:
    """Replace ``@KEY@`` with ``values['key']``; raise on a key with no value."""
    upper = {k.upper(): v for k, v in values.items()}
    missing: list[str] = []

    def sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in upper:
            val = upper[key]
        elif key in RESERVED:
            return m.group(0)
        else:
            missing.append(key)
            return m.group(0)
        if xml:
            val = val.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return val

    out = PLACEHOLDER_RE.sub(sub, template)
    if missing:
        raise RenderError("unreplaced placeholder(s): " + ", ".join(sorted(set(missing))))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--next-version", metavar="V")
    mode.add_argument("--template")
    mode.add_argument("--json", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="K=V")
    args = ap.parse_args(argv)
    if args.next_version is None and not args.repo:
        ap.error("--repo is required")
    overrides: dict[str, str] = {}
    for item in args.set:
        key, sep, val = item.partition("=")
        if not sep:
            ap.error(f"--set needs K=V, got {item!r}")
        overrides[key.lower()] = val
    try:
        if args.next_version is not None:
            print(next_version(args.next_version))
            return 0
        values = load(args.repo, overrides)
        if args.json:
            print(json.dumps(values, indent=2, sort_keys=True))
        else:
            tpl = Path(args.template)
            sys.stdout.write(
                render(tpl.read_text(encoding="utf-8"), values, xml=tpl.name.endswith(".xml.in"))
            )
    except (RenderError, OSError, ValueError) as exc:
        print(f"render.py: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
