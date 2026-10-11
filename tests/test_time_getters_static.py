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
BANNED = re.compile(r"getHours|getMinutes|getDay\(|getDate\(|getMonth\(|getFullYear\(|toLocale")


def test_only_time_js_uses_date_getters() -> None:
    offenders = []
    for path in sorted(JS_ROOT.rglob("*.js")):
        if path == JS_ROOT / "time.js":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line):
                offenders.append(f"{path.relative_to(JS_ROOT)}:{n}: {line.strip()}")
    assert not offenders, "use App.time.parts/dayNumber instead:\n" + "\n".join(offenders)
