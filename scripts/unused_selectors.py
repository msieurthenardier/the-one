#!/usr/bin/env python3
"""List CSS class tokens with no user (a developer tool, not a gate).

    python scripts/unused_selectors.py <stylesheet.css> [more.css ...]

For each class token defined in the given stylesheets, look for a user in:
the static JS (comments stripped), static/index.html, the OTHER stylesheets
(as ``.token``) and ``tests/``. Class names built at runtime are matched as
prefixes (DYNAMIC_PREFIXES below); a token under one is listed under
"dynamic: check by hand" instead of "unused". ``data-testid`` values and the
behavior-test run logs (``tests/behavior/**/runs/``) do not count as users.
Always exits 0.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "the_one" / "interfaces" / "web" / "static"

# Class names assembled at runtime ('prefix' + value). Extend from a grep for
# `'...--' +` / `'...-' +` concatenations in static/js.
DYNAMIC_PREFIXES = (
    "indicator-led--",
    "connector-setup-steps-list-",
    "ui-menu-align-",
    "chip--",
    "badge--",
    "consent-link--",
    "settings-list--",
    "ui-list-pane-",
    "area-",
    "admin-tool-badge--",
    "banner-",  # 'banner banner-' + tone (ui/page.js)
    "ui-disclosure--",  # 'ui-disclosure--' + variant (ui/disclosure.js)
)

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_JS_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\"'\\])//[^\n]*", re.S)
_CLASS = re.compile(r"(?<![\w-])\.(-?[A-Za-z_][\w-]*)")
# A data-testid value is an id, not a class: `data-testid="test-result"` is no user of
# `.test-result`. Covers the HTML attribute, a CSS/Playwright attribute selector and a
# `data-testid=value` token inside a test's selector string.
_TESTID_VALUE = re.compile(r"data-testid\s*[=~|^$*]*=\s*\\?[\"']?[\w:.-]+\\?[\"']?")
_STRING_OR_URL = re.compile(r"\"[^\"]*\"|'[^']*'|url\([^)]*\)")


def class_tokens(css: str) -> set[str]:
    """Class tokens in selector preludes only (not in declaration values)."""
    css = _STRING_OR_URL.sub('""', _CSS_COMMENT.sub("", css))
    tokens: set[str] = set()
    buf: list[str] = []
    for ch in css:
        if ch == "{":
            prelude = "".join(buf).strip()
            if prelude and not prelude.startswith("@"):
                tokens.update(_CLASS.findall(prelude))
            buf = []
        elif ch in ";}":
            buf = []
        else:
            buf.append(ch)
    return tokens


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def build_corpus(stylesheets: list[Path], static: Path, tests: Path) -> tuple[str, str]:
    """Return (plain corpus for js/html/tests, css corpus of the other stylesheets)."""
    plain: list[str] = []
    for p in sorted((static / "js").rglob("*.js")):
        plain.append(_TESTID_VALUE.sub("", _JS_COMMENT.sub("", _read(p))))
    index = static / "index.html"
    if index.exists():
        plain.append(_TESTID_VALUE.sub("", _read(index)))
    if tests.exists():
        for p in sorted(tests.rglob("*")):
            if "runs" in p.relative_to(tests).parts and "behavior" in p.relative_to(tests).parts:
                continue  # behavior run logs are history, not users
            if p.is_file() and p.suffix in {".py", ".js", ".html", ".md"}:
                plain.append(_TESTID_VALUE.sub("", _read(p)))
    own = {p.resolve() for p in stylesheets}
    css: list[str] = []
    css_dir = static / "css"
    if css_dir.exists():
        for p in sorted(css_dir.glob("*.css")):
            if p.resolve() not in own:
                css.append(_CSS_COMMENT.sub("", _read(p)))
    return "\n".join(plain), "\n".join(css)


def find_unused(
    stylesheets: list[Path], static: Path = STATIC, tests: Path = REPO / "tests"
) -> dict[Path, tuple[list[str], list[str]]]:
    plain, css = build_corpus(stylesheets, static, tests)
    out: dict[Path, tuple[list[str], list[str]]] = {}
    for sheet in stylesheets:
        unused, dynamic = [], []
        for tok in sorted(class_tokens(_read(sheet))):
            esc = re.escape(tok)
            if re.search(rf"(?<![\w-]){esc}(?![\w-])", plain) or re.search(
                rf"\.{esc}(?![\w-])", css
            ):
                continue
            (dynamic if tok.startswith(DYNAMIC_PREFIXES) else unused).append(tok)
        out[sheet] = (unused, dynamic)
    return out


def main(argv: list[str]) -> int:
    sheets = [Path(a) for a in argv if not a.startswith("-")]
    if not sheets:
        print(__doc__)
        return 0
    for sheet, (unused, dynamic) in find_unused(sheets).items():
        print(f"== {sheet}")
        print(f"unused ({len(unused)}):")
        for t in unused:
            print(f"  .{t}")
        print(f"dynamic: check by hand ({len(dynamic)}):")
        for t in dynamic:
            print(f"  .{t}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
