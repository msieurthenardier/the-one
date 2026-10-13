"""Split a release-notes file (docs/releases/vX.Y.Z.md) into a title and a body.

The first line must be ``# <title>``. Everything after it, with leading blank lines
trimmed, is the release body. Used by the Windows installer workflow (squawk 0200).

    python scripts/release_notes.py FILE --title            # print the title
    python scripts/release_notes.py FILE --title-out PATH   # write the title (UTF-8)
    python scripts/release_notes.py FILE --body-out PATH    # write the body to PATH
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def split_notes(text: str) -> tuple[str, str]:
    """Return ``(title, body)`` for the text of a release-notes file."""
    first, _, rest = text.lstrip("﻿").partition("\n")
    first = first.rstrip("\r")
    if not first.startswith("# ") or not first[2:].strip():
        raise ValueError("first line must be '# <release title>'")
    body = rest.lstrip("\r\n").rstrip() + "\n"
    if not body.strip():
        raise ValueError("release notes have no body after the title line")
    return first[2:].strip(), body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--title", action="store_true", help="print the title")
    parser.add_argument("--title-out", type=Path, help="write the title to this path (UTF-8)")
    parser.add_argument("--body-out", type=Path, help="write the body to this path")
    args = parser.parse_args(argv)
    try:
        title, body = split_notes(args.file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"{args.file}: {exc}", file=sys.stderr)
        return 1
    if args.body_out:
        args.body_out.write_text(body, encoding="utf-8", newline="\n")
    if args.title_out:
        args.title_out.write_text(title + "\n", encoding="utf-8", newline="\n")
    if args.title:
        print(title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
