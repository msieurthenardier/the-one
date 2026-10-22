"""Control-ownership reuse check (M31 F1 L2, flight DD3/DD4).

A control owns its CSS classes; ``docs/ui-control-inventory.md`` declares them (the
"Owned classes" column of each ``library:`` row, plus the "Owned by controls built later"
table). An owned class token appearing OUTSIDE the library is reuse debt: a hand-built copy
of a control, or a query for one. This test counts every such appearance and compares the
count with ``OWNERSHIP_ALLOWANCE`` (``tests/_ui_ownership_allowance.py``).

What is scanned:

- every ``static/js/**/*.js`` outside ``static/js/ui/``: the content of each string literal,
  found by a small tokenizer (``scan_js``) that understands ``//`` and ``/* */`` comments,
  ``'..'``/``".."`` strings with escapes and regex literals, so an apostrophe in a comment or a
  quote in a regex cannot desynchronise it (``test_scan_ends_in_the_code_state`` runs it over
  every real file);
- ``static/css/{chat,studio,admin,base}.css``: comments stripped, selector text only (the text
  before each ``{``), class tokens with a leading dot, attribute selectors ignored.

Not counted: testid values (a value after ``testid:`` or ``<word>Testid:``, after a
``'data-testid'`` key, or the second argument of ``setAttribute('data-testid', ..)``), and a
``data-testid="..."`` attribute written inside a markup string. A token match is
``(?<![\\w-])name(?![\\w-])``, so ``field-input-wide`` does not count as ``field-input``.

Retired-API calls are counted per file under pseudo-keys (``api:App.icon(`` and friends), in
code only (not in comments or strings).

THE RATCHET: the comparison fails on ANY difference, up and down. When a change removes uses,
lower the allowance in the same change (paste the dict this test prints). Never raise a count
without a reason recorded in the flight log; a new row means new debt.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from tests._ui_guard_helpers import JS_DIR
from tests._ui_ownership_allowance import OWNERSHIP_ALLOWANCE
from tests.test_ui_control_inventory import INVENTORY, control_table_rows

STATIC_DIR = JS_DIR.parent
CSS_DIR = STATIC_DIR / "css"
CSS_FILES = ("chat.css", "studio.css", "admin.css", "base.css")

RETIRED_APIS = {
    "api:App.icon(": re.compile(r"(?<![\w$.])(?:window\.)?App\.icon\("),
    "api:App.iconNode(": re.compile(r"(?<![\w$.])(?:window\.)?App\.iconNode\("),
    "api:App.showFlash(": re.compile(r"(?<![\w$.])(?:window\.)?App\.showFlash\("),
    "api:App.confirmDelete(": re.compile(r"(?<![\w$.])(?:window\.)?App\.confirmDelete\("),
    "api:App.consentLink.": re.compile(r"(?<![\w$.])(?:window\.)?App\.consentLink\."),
    "api:App.tabs(": re.compile(r"(?<![\w$.])(?:window\.)?App\.tabs\("),
}

# ── Tokenizer ───────────────────────────────────────────────────────────────

# After one of these words a `/` starts a regex; after any other identifier it divides.
_REGEX_AFTER_WORDS = {"return", "typeof", "case", "in", "of", "delete", "void", "throw", "new"}
_REGEX_AFTER_CHARS = set("(,=:[!&|?{};+-*%<>~^")
_IDENT = re.compile(r"[A-Za-z0-9_$]+")


class Scan:
    """Result of ``scan_js``: string literals, the code with non-code blanked, the end state."""

    def __init__(self) -> None:
        self.literals: list[tuple[int, str, str]] = []  # (offset, content, preceding source)
        self.code = ""
        self.end_state = "code"


def scan_js(src: str) -> Scan:
    """Tokenize ``src``. Yields each string literal's start offset, content and the 80 source
    characters before it; ``code`` is ``src`` with comments, strings and regexes blanked."""
    out = Scan()
    code: list[str] = []
    n = len(src)
    i = 0
    prev = "\n"  # last significant char, or the last identifier/number word
    state = "code"

    def blank(a: int, b: int) -> None:
        code.append("".join("\n" if c == "\n" else " " for c in src[a:b]))

    while i < n:
        ch = src[i]
        if ch in " \t\r\n":
            code.append(ch)
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                state = "block-comment"
                blank(i, n)
                i = n
            else:
                blank(i, j + 2)
                i = j + 2
        elif ch in "'\"`":
            j = i + 1
            while j < n and src[j] != ch:
                j += 2 if src[j] == "\\" else 1
            if j >= n:
                state = "string"
                j = n
            out.literals.append((i, src[i + 1 : j], src[max(0, i - 80) : i]))
            blank(i, min(j + 1, n))
            i = j + 1
            prev = ")"  # a string is an operand: a following `/` divides
        elif ch == "/":
            is_regex = prev in _REGEX_AFTER_CHARS or prev in _REGEX_AFTER_WORDS or prev == "\n"
            if not is_regex:
                code.append(ch)
                prev = ch
                i += 1
                continue
            j = i + 1
            in_class = False
            while j < n:
                c = src[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    break
                elif c == "\n":
                    break
                j += 1
            if j >= n or src[j] != "/":
                state = "regex"
                j = min(j, n)
            blank(i, min(j + 1, n))
            i = j + 1
            prev = ")"
        else:
            m = _IDENT.match(src, i)
            if m:
                code.append(m.group())
                prev = m.group() if m.group() in _REGEX_AFTER_WORDS else ")"
                i = m.end()
            else:
                code.append(ch)
                prev = ch
                i += 1
    out.code = "".join(code)
    out.end_state = state
    return out


_TESTID_KEY = re.compile(r"""(?:\b(?:testid|[a-z]+Testid)|['"]data-testid['"])\s*:\s*$""")
_TESTID_SETATTR = re.compile(r"""setAttribute\(\s*['"]data-testid['"]\s*,\s*$""")
_TESTID_IN_MARKUP = re.compile(r"""\[?data-testid=(?:"[^"]*"|\\"[^"]*\\")\]?""")


def is_testid_value(before: str) -> bool:
    return bool(_TESTID_KEY.search(before) or _TESTID_SETATTR.search(before))


def token_regex(name: str) -> re.Pattern[str]:
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")


def count_js_uses(src: str, names: list[str]) -> Counter[str]:
    """Owned-class uses in the string literals of ``src`` (testid values excluded)."""
    counts: Counter[str] = Counter()
    for _offset, content, before in scan_js(src).literals:
        if is_testid_value(before):
            continue
        content = _TESTID_IN_MARKUP.sub("", content)
        for name in names:
            found = len(token_regex(name).findall(content))
            if found:
                counts[name] += found
    return counts


_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_PRELUDE = re.compile(r"([^{}]*)\{")
_CSS_ATTR = re.compile(r"\[[^\]]*\]")


def count_css_uses(css: str, names: list[str]) -> Counter[str]:
    """Owned-class uses in the selector text of ``css``."""
    counts: Counter[str] = Counter()
    css = _CSS_COMMENT.sub("", css)
    for m in _CSS_PRELUDE.finditer(css):
        selector = _CSS_ATTR.sub("", m.group(1))
        for name in names:
            found = len(re.findall(r"\." + re.escape(name) + r"(?![\w-])", selector))
            if found:
                counts[name] += found
    return counts


def count_retired_api(code: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for key, pattern in RETIRED_APIS.items():
        found = len(pattern.findall(code))
        if found:
            counts[key] += found
    return counts


# ── Catalogue ───────────────────────────────────────────────────────────────


def owned_classes(text: str) -> list[str]:
    """Owned classes of every ``library:`` row, plus the planned (built later) classes."""
    names: set[str] = set()
    for cells in control_table_rows(text):
        if cells[2].startswith("library:"):
            names.update(re.findall(r"`([\w-]+)`", cells[4]))
    in_later = False
    for line in text.splitlines():
        if line.startswith("| Class | Owning control (planned) |"):
            in_later = True
        elif in_later and line.startswith("| `"):
            names.add(re.match(r"\| `([\w-]+)`", line).group(1))  # type: ignore[union-attr]
        elif in_later and not line.startswith("|"):
            in_later = False
    return sorted(names)


# ── The scan of the real tree ───────────────────────────────────────────────


def app_js_files() -> list[Path]:
    ui_dir = JS_DIR / "ui"
    return [p for p in sorted(JS_DIR.rglob("*.js")) if ui_dir not in p.parents]


def measure() -> dict[tuple[str, str], int]:
    names = owned_classes(INVENTORY.read_text())
    found: dict[tuple[str, str], int] = {}
    for path in app_js_files():
        rel = path.relative_to(STATIC_DIR).as_posix()
        src = path.read_text()
        for name, count in count_js_uses(src, names).items():
            found[(rel, name)] = count
        for key, count in count_retired_api(scan_js(src).code).items():
            found[(rel, key)] = count
    for filename in CSS_FILES:
        rel = f"css/{filename}"
        for name, count in count_css_uses((CSS_DIR / filename).read_text(), names).items():
            found[(rel, name)] = count
    return found


def format_allowance(found: dict[tuple[str, str], int]) -> str:
    lines = ["OWNERSHIP_ALLOWANCE: dict[tuple[str, str], int] = {"]
    lines += [f"    ({rel!r}, {key!r}): {count}," for (rel, key), count in sorted(found.items())]
    lines.append("}")
    return "\n".join(lines)


def test_ownership_matches_allowance() -> None:
    found = measure()
    if found == OWNERSHIP_ALLOWANCE:
        return
    diffs = []
    for k in sorted(set(found) | set(OWNERSHIP_ALLOWANCE)):
        have, want = found.get(k, 0), OWNERSHIP_ALLOWANCE.get(k, 0)
        if have != want:
            diffs.append(f"  {k}: found {have}, allowed {want}")
    raise AssertionError(
        "Owned-class / retired-API uses differ from tests/_ui_ownership_allowance.py.\n"
        "Lower the allowance in the same change that removes uses; never raise it without a\n"
        "flight-log reason. Differences:\n"
        + "\n".join(diffs)
        + "\n\nCorrected dict (paste into tests/_ui_ownership_allowance.py):\n"
        + format_allowance(found)
    )


def test_scan_ends_in_the_code_state() -> None:
    """The tokenizer stays in sync over every real JS file (guards against desynchronisation)."""
    bad = {
        p.relative_to(STATIC_DIR).as_posix(): scan_js(p.read_text()).end_state
        for p in sorted(JS_DIR.rglob("*.js"))
        if scan_js(p.read_text()).end_state != "code"
    }
    assert not bad, bad


def test_catalogue_declares_owned_classes() -> None:
    names = owned_classes(INVENTORY.read_text())
    assert {"field-input", "btn-ghost", "ui-icon", "field-info-icon", "chip"} <= set(names)
    assert "visually-hidden" not in names


# ── Tokenizer unit tests (fixture strings, no file IO) ──────────────────────


def _uses(js: str, *names: str) -> dict[str, int]:
    return dict(count_js_uses(js, list(names)))


def test_comment_text_is_ignored() -> None:
    js = "// field-input here\n/* and 'field-input' there */ var a = 1;\n"
    assert _uses(js, "field-input") == {}


def test_apostrophe_in_comment_does_not_break_string_pairing() -> None:
    js = "// don't count this\nvar a = 'field-input';\n// it's fine\nvar b = 'badge';\n"
    assert _uses(js, "field-input", "badge") == {"field-input": 1, "badge": 1}
    assert scan_js(js).end_state == "code"


def test_regex_literal_with_quote_does_not_open_a_string() -> None:
    js = "var r = /['\"]/g; var c = 'field-input';\nx = s.replace(/[/']/, ''); y = 'badge';\n"
    scan = scan_js(js)
    assert scan.end_state == "code"
    assert _uses(js, "field-input", "badge") == {"field-input": 1, "badge": 1}


def test_division_is_not_a_regex() -> None:
    js = "var a = b / 2; var c = 'badge'; var d = e / f;\n"
    assert scan_js(js).end_state == "code"
    assert _uses(js, "badge") == {"badge": 1}


def test_testid_values_are_ignored_in_all_three_forms() -> None:
    js = (
        "App.ui.button({testid: 'editor-unsaved'});\n"
        "App.ui.searchList({inputTestid: 'editor-unsaved'});\n"
        "el({'data-testid': 'editor-unsaved'});\n"
        "node.setAttribute('data-testid', 'editor-unsaved');\n"
        "var cls = 'editor-unsaved';\n"
    )
    assert _uses(js, "editor-unsaved") == {"editor-unsaved": 1}


def test_testid_attribute_inside_markup_is_ignored() -> None:
    js = 'var h = \'<span class="editor-unsaved" data-testid="editor-unsaved">\';\n'
    assert _uses(js, "editor-unsaved") == {"editor-unsaved": 1}


def test_token_match_is_whole_token() -> None:
    assert _uses("var a = 'field-input-wide';", "field-input") == {}
    assert _uses("var a = 'wide-field-input';", "field-input") == {}
    assert _uses("var a = 'field-input';", "field-input") == {"field-input": 1}


def test_two_classes_in_one_literal_count_both() -> None:
    assert _uses("var a = 'btn-ghost btn-sm';", "btn-ghost", "btn-sm") == {
        "btn-ghost": 1,
        "btn-sm": 1,
    }


def test_css_declaration_values_are_ignored_but_selectors_count() -> None:
    css = (
        "/* .field-input in a comment */\n"
        ".area-studio .field-input { content: 'field-input'; color: red; }\n"
        ".other { background: url(.field-input); }\n"
        '.x[data-testid="field-input"] { }\n'
        "@layer areas { .field-input-wide { } }\n"
    )
    assert dict(count_css_uses(css, ["field-input"])) == {"field-input": 1}


def test_retired_api_calls_count_in_code_only() -> None:
    js = (
        "// App.icon('x')\nvar a = 'App.icon(';\n"
        "var b = window.App.icon('x') + App.icon('y') + App.iconNode('z');\n"
        "App.confirmDelete(row, fn); App.consentLink.create(); App.ui.icon('x');\n"
        "var h = window.App.tabs(a, b) + App.tabs(c, d); App.ui.tabs({}); // App.tabs(e)\n"
    )
    counts = count_retired_api(scan_js(js).code)
    assert counts == {
        "api:App.icon(": 2,
        "api:App.iconNode(": 1,
        "api:App.confirmDelete(": 1,
        "api:App.consentLink.": 1,
        "api:App.tabs(": 2,
    }
