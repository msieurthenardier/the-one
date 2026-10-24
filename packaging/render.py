#!/usr/bin/env python3
"""Render packaging templates from packaging/product.toml (Mission 32, DD6).

Stdlib only (tomllib, Python 3.11 or newer).

    render.py --repo R --template T [--set K=V ...]   print the rendered template
    render.py --repo R --json [--set K=V ...]         print the values as JSON

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
    for key, val in raw.items():
        if isinstance(val, dict):
            values.update({k: str(v) for k, v in val.items()})
        else:
            values[key] = str(val)
    overrides = dict(overrides or {})
    values["version"] = overrides.pop("version", None) or read_version(repo)
    values["deb_version"] = deb_version(values["version"])
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
    ap.add_argument("--repo", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--template")
    mode.add_argument("--json", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="K=V")
    args = ap.parse_args(argv)
    overrides: dict[str, str] = {}
    for item in args.set:
        key, sep, val = item.partition("=")
        if not sep:
            ap.error(f"--set needs K=V, got {item!r}")
        overrides[key.lower()] = val
    try:
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
