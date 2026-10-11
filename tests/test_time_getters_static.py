"""Display clocks and day arithmetic go through ``App.time`` (M28 F2 L1).

Only ``static/js/time.js`` may call the ``Date`` getters or the locale formatters;
every other module reads the operator's zone through ``App.time.parts`` and
``dayNumber``. This keeps a new caller from silently showing browser-local time.
"""

from __future__ import annotations

import re
from pathlib import Path

JS_ROOT = (
    Path(__file__).resolve().parent.parent / "the_one" / "interfaces" / "web" / "static" / "js"
)
BANNED = re.compile(
    r"getHours|getMinutes|getDay\(|getDate\(|getMonth\(|getFullYear\(|toLocale"
    r"|getTimezoneOffset"
    r"|\.set(?:Hours|Minutes|Seconds|Milliseconds|Date|Month|FullYear)\("
    r"|new Date\(\s*[^,()]+,"  # local-time construction: two or more arguments
    r"|Intl\.DateTimeFormat\("
)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:'\"\\])//.*")


def _code_lines(text: str) -> list[tuple[int, str]]:
    """Source lines with block and line comments blanked (line numbers kept)."""
    text = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return [(n, _LINE_COMMENT.sub("", line)) for n, line in enumerate(text.splitlines(), 1)]


def test_only_time_js_uses_date_getters() -> None:
    offenders = []
    for path in sorted(JS_ROOT.rglob("*.js")):
        if path == JS_ROOT / "time.js":
            continue
        for n, line in _code_lines(path.read_text(encoding="utf-8")):
            if BANNED.search(line):
                offenders.append(f"{path.relative_to(JS_ROOT)}:{n}: {line.strip()}")
    assert not offenders, "use App.time.parts/dayNumber instead:\n" + "\n".join(offenders)


def test_the_widened_patterns_catch_each_local_time_path() -> None:
    for bad in (
        "new Date(2026, 9, 11)",
        "new Date(y, m)",
        "d.getTimezoneOffset()",
        "d.setHours(0)",
        "d.setFullYear(1)",
        "Intl.DateTimeFormat()",
    ):
        assert BANNED.search(bad), bad
    for ok in ("new Date(ms)", "new Date()", "d.setUTCHours(0)", "new Date(Date.UTC(1, 2))"):
        assert not BANNED.search(ok), ok
    assert not [
        c for _, c in _code_lines("// getHours here\n/* d.setHours(1) */") if BANNED.search(c)
    ]
