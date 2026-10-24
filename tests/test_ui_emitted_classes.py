"""Emitted-class guard (M31 F4 L04c, flight DD12).

Every CSS class a ``static/js/ui/*.js`` factory emits is either OWNED (it appears in the
"Owned classes" column of some ``library:`` row of ``docs/ui-control-inventory.md``, or in the
"Owned by controls built later" table) or listed in ``EMITTED_EXEMPT`` with a reason. The
ratchet is exact in both directions: a new unowned class fails, and an exempt entry that is
no longer emitted, or has since become owned, fails. Legs that add a control add its classes
to the catalogue (DD12), so the owned-list check at the end of the flight is mechanical.

How classes are found: ``scan_js`` (``tests/test_ui_ownership.py``) tokenizes each file; for
every string literal the source since the last ``;``, ``{``, ``}`` or ``,`` is inspected. A
literal is a class literal when that stretch has a class-setting form (a ``className`` /
``rootClass`` / ``cls`` / ``*Class`` / ``*CLASS`` name followed by ``=``, ``+=`` or ``:``), or
when the literal sits in a ``classList.add/toggle(`` call or inside a ``*_CLASS`` table. Each
whitespace-separated token that looks like a class name is collected; a token ending in ``-``
is a dynamic family (``ui-list-pane-`` + a variable) and is matched as a prefix.

BLIND SPOTS (this is a ratchet, not a proof): a class built from a variable outside those
forms (a class name read from an options object, a helper's return value, a literal passed as
a bare argument such as ``el('span', 'x')``), a class set through ``setAttribute('class', ..)``
with no ``cls`` name, and a class written inside an HTML string are invisible to it. Queries
(``classList.contains/remove``) are not emissions and are ignored.
"""

from __future__ import annotations

import re

from tests._ui_guard_helpers import JS_DIR
from tests.test_ui_control_inventory import INVENTORY
from tests.test_ui_ownership import owned_classes, scan_js

_NAME = re.compile(r"[a-z][a-z0-9_]*(?:-[a-z0-9_]+)*-?")
_SEG_CUT = re.compile(r"[;{},]")
_SET_FORM = re.compile(r"(?:className|rootClass|\bcls\w*|\w*Class\w*|\w*CLASS\w*)\s*(?:\+?=|:)")
_CLASSLIST = re.compile(r"classList\.(?:add|toggle)\(\s*(?:[^;()]*,\s*)?$")
_COMPARED = re.compile(r"(?:[!=]==?|indexOf\()\s*$")
_COMPARED_AFTER = re.compile(r"\s*(?:[!=]==?|\)\s*[!=]==?)")
_TABLE = re.compile(r"\b\w*CLASS\w*\s*=\s*\{")

# name (or prefix ending in "-") -> why it is emitted without a catalogue row of its own.
EMITTED_EXEMPT: dict[str, str] = {
    # Legacy names the new page controls emit before their DD12 handover legs (04a, 04b):
    "page-header": "legacy name of pageHeader; joins the owned list at its handover leg",
    "page-title": "legacy name of the page title; joins the owned list at its handover leg",
    "banner": "legacy name of banner; joins the owned list at the banner handover leg",
    "banner-": "legacy banner-{tone} family; joins the owned list at the handover leg",
    "code-block": "legacy name of codeBlock; joins the owned list at the handover leg",
    # The toolTile's legacy names are owned since leg 06's handover (M31 F4 L06); only the
    # state class stays exempt (an everyday word, not safe to own):
    "active": "legacy selected state of the toolTile; an everyday word, deliberately not owned",
    # Internal parts and shared state classes with no row of their own:
    "badge-dot": "the status dot of the badge helper in feedback.js; the badge row covers it",
    "ui-info-bubble": "the field info bubble, a part of the field row",
    "ui-section-title-row": "the section title row, a part of the section row",
    "ui-status-text": "the status label, a part of the status row",
    "is-invalid": "shared invalid state of field, chipList and keyValueTable",
    "is-checked": "shared checked state of the choice controls",
    "is-disabled": "shared disabled state of the choice controls and toolTile",
    "visible": "flash's fade-in state class",
    "visually-hidden": "global utility in components.css, not owned by one control",
    "tab": "the tab button class; deliberately not owned (prose word), see the tabs row",
    # Scanner artefacts: a modifier VALUE in a ternary, not a class name:
    "error": "a tone value inside a class suffix expression, not a class",
    "idle": "a state value inside indicator-led--{state}, not a class",
    "unknown": "a kind value inside badge--{kind}, not a class",
}


def _table_ranges(code: str) -> list[tuple[int, int]]:
    out = []
    for m in _TABLE.finditer(code):
        depth, i = 1, m.end()
        while i < len(code) and depth:
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        out.append((m.end(), i))
    return out


def emitted_in(src: str) -> set[str]:
    scan = scan_js(src)
    tables = _table_ranges(scan.code)
    found: set[str] = set()
    for offset, content, _before in scan.literals:
        head = src[max(0, offset - 240) : offset]
        stretch = _SEG_CUT.split(head)[-1]
        in_table = any(a <= offset < b for a, b in tables)
        if not (in_table or _SET_FORM.search(stretch) or _CLASSLIST.search(head.split(";")[-1])):
            continue
        if re.search(r"classList\.(?:contains|remove)\(\s*$", head) or _COMPARED.search(head):
            continue
        if _COMPARED_AFTER.match(src, offset + len(content) + 2):
            continue
        for tok in content.split():
            if _NAME.fullmatch(tok):
                found.add(tok)
    return found


def emitted_classes() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in sorted((JS_DIR / "ui").glob("*.js")):
        for tok in emitted_in(path.read_text()):
            out.setdefault(tok, set()).add(path.name)
    return out


def _owned(tok: str, owned: set[str]) -> bool:
    if tok.endswith("-"):
        return any(o.startswith(tok) for o in owned)
    return tok in owned


def _exempt_key(tok: str) -> str | None:
    for key in EMITTED_EXEMPT:
        if tok == key or (key.endswith("-") and tok.startswith(key)):
            return key
    return None


def test_every_emitted_class_is_owned_or_exempt() -> None:
    owned = set(owned_classes(INVENTORY.read_text()))
    bad = {
        t: sorted(f)
        for t, f in emitted_classes().items()
        if not _owned(t, owned) and _exempt_key(t) is None
    }
    assert not bad, (
        "classes emitted by js/ui factories with no catalogue row and no EMITTED_EXEMPT entry "
        "(add the class to its control's Owned classes, or exempt it with a reason):\n"
        + "\n".join(f"  {t!r}: {f}" for t, f in sorted(bad.items()))
    )


def test_no_stale_exempt_entry() -> None:
    owned = set(owned_classes(INVENTORY.read_text()))
    emitted = emitted_classes()
    stale = []
    for key in EMITTED_EXEMPT:
        users = [t for t in emitted if _exempt_key(t) == key]
        if not users:
            stale.append(f"{key!r}: no longer emitted")
        elif all(_owned(t, owned) for t in users):
            stale.append(f"{key!r}: now owned by a catalogue row")
    assert not stale, "stale EMITTED_EXEMPT entries:\n  " + "\n  ".join(stale)


def test_scanner_recognises_the_class_forms() -> None:
    src = (
        "var T = { a: 'x-one' }; var VARIANT_CLASS = { p: 'y-two', q: 'z-three' };\n"
        "var cls = 'w-four' + (o ? ' w-five' : ''); cls += ' w-six';\n"
        "el('div', { className: 'v-seven ' + n, title: 'not-a-class' });\n"
        "n.classList.add('u-eight', 'u-nine'); n.classList.remove('r-ten');\n"
        "n.classList.contains('q-eleven'); k = 'p-twelve-' + id; cls = 'o-' + k;\n"
    )
    assert emitted_in(src) == {
        "y-two",
        "z-three",
        "w-four",
        "w-five",
        "w-six",
        "v-seven",
        "u-eight",
        "u-nine",
        "o-",
    }
