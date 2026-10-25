"""Shared extraction logic for the UI guard tests (``test_ui_guards.py``).

Two extractors over ``the_one/interfaces/web/static/js/**/*.js``:

- **Testid extraction** — finds every ``data-testid`` *definition* in the
  JS sources, classified as literal ids or parametric prefix families,
  and separately collects selector *references* (``[data-testid="..."]``
  inside ``querySelector`` strings), which do NOT count as definitions.
- **Sink classification** — finds every ``.innerHTML`` / ``.outerHTML``
  assignment and ``insertAdjacentHTML(...)`` call, joins the logical
  statement to its terminating ``;``, and classifies it STATIC (complete
  single string-literal payload) or DYNAMIC (everything else: variable,
  function call, any concatenation).

The guard tests compare live extraction against the human-readable
registry (``docs/ui-testid-registry.md``) and a frozen dynamic-sink
baseline embedded in the test module.

Pattern notes (calibrated against the sources at freeze time):

- JS strings are single-quoted; HTML attributes inside them are
  double-quoted (``'<div data-testid="foo">'``).  There are no
  ``data-testid='...'`` single-quoted attr forms and no backtick
  template literals carrying testids or innerHTML payloads.
- A parametric-in-HTML-string id is one whose attr value is interrupted
  by the JS string terminator + concatenation
  (``data-testid="tab-' + cid``).  The char class ``[^"'\\n]`` anchors
  matching to the attribute's own quoted value, which also defeats the
  false-parametric case ``data-testid="provider-card" data-id="' + id``
  (the concatenation belongs to ``data-id``).
- Fully variable-carried ids (``data-testid="' + saveTestId + '"``) are
  invisible to extraction; they are covered by the registry's
  manual-exceptions table, and the guard asserts each such id still
  appears as a plain string literal somewhere in the JS sources.
- Comments are scanned like live code (project decision: if a comment
  trips the extractor, delete the dead code rather than special-case).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
JS_DIR = REPO_ROOT / "the_one" / "interfaces" / "web" / "static" / "js"
REGISTRY_DOC = REPO_ROOT / "docs" / "ui-testid-registry.md"
TOKENS_CSS = REPO_ROOT / "the_one" / "interfaces" / "web" / "static" / "css" / "tokens.css"

# ── Testid patterns ─────────────────────────────────────────────────────────

# Literal attr-form: data-testid="foo" with an uninterrupted quoted value.
# Negative lookbehind excludes selector references ([data-testid="foo"]).
_ATTR_LITERAL = re.compile(r'(?<!\[)data-testid="([^"\'\n]+)"')

# Parametric-in-HTML-string: the attr value is cut short by the JS string
# terminator followed by concatenation: data-testid="tab-' + cid + ...
_ATTR_PARAMETRIC = re.compile(r'(?<!\[)data-testid="([^"\'\n]+)\'\s*\+')

# setAttribute literal: setAttribute('data-testid', 'foo')
_SETATTR_LITERAL = re.compile(r"setAttribute\(\s*'data-testid'\s*,\s*'([^\"'\n]+)'\s*\)")

# setAttribute parametric: setAttribute('data-testid', 'prefix-' + ...)
_SETATTR_PARAMETRIC = re.compile(r"setAttribute\(\s*'data-testid'\s*,\s*'([^\"'\n]+)'\s*\+")

# Quoted attrs-key literal (squawk 0130): an element-builder attrs object's
# ``'data-testid': 'foo'`` (or ``"data-testid": 'foo'``) key. The backreference
# pairs the key's quotes; the lookahead stops a parametric value also matching.
_KEY_LITERAL = re.compile(r"""(['"])data-testid\1\s*:\s*'([^"'\n]+)'(?!\s*\+)""")

# Quoted attrs-key parametric: ``'data-testid': 'prefix-' + ...``.
_KEY_PARAMETRIC = re.compile(r"""(['"])data-testid\1\s*:\s*'([^"'\n]+)'\s*\+""")

# Library literal (DD2, M25 F1): a ``testid: 'foo'`` property handed to an
# ``App.ui`` factory (own options, a nested option object, or a per-item
# object). ``\b`` excludes ``rowtestid:``; the negative lookahead stops a
# parametric site (``'prefix-' + x``) also matching as a literal. The char
# class ``[^"'\n]`` anchors to the value's own quotes. M25 F4 L1: a factory
# option named ``<lower>Testid`` (``App.ui.searchList``'s ``inputTestid`` and
# ``rowTestid``) is a test id key too, so its values stay registry-visible.
_TESTID_NAME = r"(?:testid|[a-z]+Testid)"
_PROP_LITERAL = re.compile(r"\b" + _TESTID_NAME + r":\s*'([^\"'\n]+)'(?!\s*\+)")

# Library parametric: ``testid: 'prefix-' + ...`` (``\s*`` spans a newline).
_PROP_PARAMETRIC = re.compile(r"\b" + _TESTID_NAME + r":\s*'([^\"'\n]+)'\s*\+")

# Selector reference: [data-testid="foo"] — used in querySelector strings.
_SELECTOR_REF = re.compile(r'\[data-testid="([^"\'\n\]]+)"\]')


def iter_js_files(js_dir: Path = JS_DIR) -> list[Path]:
    return sorted(js_dir.rglob("*.js"))


def relpath(path: Path, root: Path = JS_DIR) -> str:
    """Path relative to ``root`` (default the js/ root), as a forward-slash string."""
    return path.relative_to(root).as_posix()


def extract_testids(
    js_dir: Path = JS_DIR,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    """Extract testid definitions and selector references from JS sources.

    Returns ``(literals, parametric_prefixes, selector_refs)`` — each a
    dict mapping id (or prefix) to the set of defining/referencing file
    paths (relative to the js/ root).
    """
    literals: dict[str, set[str]] = {}
    parametric: dict[str, set[str]] = {}
    selector_refs: dict[str, set[str]] = {}
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        rel = relpath(js_file, js_dir)
        for testid in _ATTR_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for testid in _SETATTR_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for _q, testid in _KEY_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for _q, prefix in _KEY_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for prefix in _ATTR_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for prefix in _SETATTR_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for testid in _PROP_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for prefix in _PROP_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for testid in _SELECTOR_REF.findall(text):
            selector_refs.setdefault(testid, set()).add(rel)
    return literals, parametric, selector_refs


# ── testid-value scanner (DD2 composite-rule enforcement) ───────────────────
#
# Every ``testid`` KEY in static/js must carry a value the extractor can see:
# anything else is a silent manual exception, invisible to both directions of
# the registry diff. The lookbehind excludes ``data-testid`` / ``rowtestid`` /
# bare ``testid`` parameters; optional quotes catch ``'testid':`` keys.
_TESTID_KEY = re.compile(r"(?<![\w-])['\"]?" + _TESTID_NAME + r"['\"]?\s*:")

# Outside ui/: a single-quoted literal ending at , } ) or end of line, or a
# single-quoted ``'prefix' +`` concatenation (the + may start the next line).
_VALUE_LITERAL = re.compile(r"'[^\"'\n]+'(?:[ \t]*(?:[,})]|$)|\s*\+)", re.MULTILINE)

# Inside ui/: forwarding only, ``<identifier-chain>.testid`` (or ``.<lower>Testid``).
_VALUE_FORWARD = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\." + _TESTID_NAME + r"\b")


def find_testid_value_violations(js_dir: Path = JS_DIR) -> list[tuple[str, int, str]]:
    """Return ``(rel_path, line_number, excerpt)`` for every ``testid`` key whose
    value is not an allowed form. The value is classified by its LEADING token,
    so a ternary's inner quotes and colon are never split. Comments are scanned
    like live code, consistent with the extractor. Empty list = passing."""
    bad: list[tuple[str, int, str]] = []
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        rel = relpath(js_file, js_dir)
        in_ui = rel.startswith("ui/")
        for m in _TESTID_KEY.finditer(text):
            value = text[m.end() :].lstrip(" \t")
            if "'" in m.group(0) or '"' in m.group(0):
                ok = False  # quoted key
            elif in_ui:
                ok = bool(_VALUE_FORWARD.match(value))
            else:
                ok = bool(_VALUE_LITERAL.match(value))
            if not ok:
                lineno = text.count("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.start())
                excerpt = text[m.start() : len(text) if line_end < 0 else line_end]
                bad.append((rel, lineno, excerpt.strip()[:100]))
    return bad


UI_DIR = JS_DIR / "ui"


def find_ui_dir_sink_tokens(
    ui_dir: Path = UI_DIR,
) -> tuple[int, list[tuple[str, int, str, str]]]:
    """DD4 zero-token scan over ``static/js/ui/*.js`` (comments included).

    Returns ``(files_scanned, hits)``; each hit is ``(file, line, token,
    stripped_line)``. An absent directory scans zero files with no hits."""
    if not ui_dir.is_dir():
        return 0, []
    files = sorted(ui_dir.glob("*.js"))
    hits: list[tuple[str, int, str, str]] = []
    for f in files:
        for lineno, token, line in find_markdown_html_sink_tokens(f):
            hits.append((f.name, lineno, token, line))
    return len(files), hits


_DOC_ADD = re.compile(r"document\.addEventListener\(\s*'([^']+)'\s*,\s*([A-Za-z_$][\w$]*)")
_DOC_REMOVE = re.compile(r"document\.removeEventListener\(\s*'([^']+)'\s*,\s*([A-Za-z_$][\w$]*)")


def find_unpaired_document_listeners(
    ui_dir: Path = UI_DIR,
) -> tuple[int, list[tuple[str, str, str]]]:
    """M31 F2 L5: a control installs no PERMANENT document listener. Every
    ``document.addEventListener('<evt>', <handler>`` in ``static/js/ui/*.js`` needs a
    ``document.removeEventListener('<evt>', <handler>`` in the same file. Returns
    ``(adds_seen, [(file, event, handler), ...unpaired])``."""
    if not ui_dir.is_dir():
        return 0, []
    seen = 0
    bad: list[tuple[str, str, str]] = []
    for f in sorted(ui_dir.glob("*.js")):
        text = f.read_text()
        removes = set(_DOC_REMOVE.findall(text))
        for pair in _DOC_ADD.findall(text):
            seen += 1
            if pair not in removes:
                bad.append((f.name, pair[0], pair[1]))
    return seen, bad


def id_appears_as_string_literal(testid: str, js_dir: Path = JS_DIR) -> bool:
    """True if ``testid`` appears as a complete quoted string literal
    anywhere in the JS sources.  Used for manual-exception ids (variable-
    carried literals) so their deletion is still caught."""
    pattern = re.compile("['\"]" + re.escape(testid) + "['\"]")
    return any(pattern.search(f.read_text()) for f in iter_js_files(js_dir))


# ── Field label-association guard (M17 F5 L1) ───────────────────────────────
#
# The M17 F3 ``.field-group`` vocabulary wires label association BY HAND at
# every site (the old gallery-local ``fieldGroup()`` helper was deleted in M25 F1
# L6; the gallery now uses ``App.ui.field``): a ``<label for="X">`` must resolve
# to a control ``id="X"``, and
# an ``.is-invalid`` control's ``aria-describedby="Y"`` must resolve to a
# ``.field-error`` element ``id="Y"``. As the F5 studio re-skin migrates the 54
# ``.field-row`` sites to ``.field-group``, these guards catch the easy
# silent-drop (a label pointing at a renamed / removed id). Static-source scan
# over LITERAL attribute values; ids emitted through a concatenation helper
# (``id="' + escapeAttr(x) + '"``) are invisible to the literal scan, so their
# literal for-targets live in ``FIELD_FOR_ID_HELPER_INDIRECTED`` below (the same
# manual-exception pattern the testid registry uses for variable-carried ids).

# Literal ``id="X"`` / ``for="X"`` / ``aria-describedby="X"`` with an
# uninterrupted quoted value. The negative lookbehind ``(?<![\w-])`` keeps
# ``id=`` from matching inside ``data-testid=`` / ``provider-id=`` etc. and
# still matches an ``id="`` that opens a concatenated JS-string fragment
# (preceded by a quote). ``_ATTR_FOR_PARAM`` catches a ``for`` value cut short
# by the JS string terminator + concatenation (dynamic — skipped by the
# resolver, like the parametric-testid case).
_ATTR_ID = re.compile(r'(?<![\w-])id="([^"\'\n]+)"')
_ATTR_ID_SETATTR = re.compile(r"setAttribute\(\s*'id'\s*,\s*'([^\"'\n]+)'")
_ATTR_ID_PROP = re.compile(r"\.id\s*=\s*'([^'\n]+)'")
_ATTR_FOR = re.compile(r'(?<![\w-])for="([^"\'\n]+)"')
_ATTR_FOR_PARAM = re.compile(r'(?<![\w-])for="([^"\'\n]+)\'\s*\+')
_ATTR_ARIA_DESCRIBEDBY = re.compile(r'aria-describedby="([^"\'\n]+)"')
_ATTR_ARIA_DESCRIBEDBY_PARAM = re.compile(r'aria-describedby="([^"\'\n]+)\'\s*\+')

# for-targets whose control ``id`` is emitted through a concatenation helper,
# invisible to the literal-id scan but present at runtime.
#
# ``mf-args`` / ``mf-sandbox-writable-paths`` (mcp-connection-fields.js,
# mountChipListEditors): the two
# chip-list ``label[for]`` targets. M17 F6 L3 fixed the runtime label-dangle by
# landing the id on the real ``.chip-list-input`` via renderChipListEditor's
# ``controlId`` option (the placeholder <div> the label used to target carried
# no id — mountChipListEditors replaces it via ``outerHTML=`` which strips ids).
# The id is emitted through the shared helper (``id="' + controlId + '"``),
# invisible to the literal-id scan but present at runtime — asserted by the
# runtime DOM guard in ``tests/browser/test_flow_chiplist_label_resolver.py``.
FIELD_FOR_ID_HELPER_INDIRECTED: set[str] = {
    "mf-args",
    "mf-sandbox-writable-paths",
}


def _literal_ids(text: str) -> set[str]:
    """Every literal element id in ``text`` — ``id="X"`` HTML-string attrs,
    ``setAttribute('id', 'X')`` calls, and ``el.id = 'X'`` property sets."""
    return (
        set(_ATTR_ID.findall(text))
        | set(_ATTR_ID_SETATTR.findall(text))
        | set(_ATTR_ID_PROP.findall(text))
    )


def _field_error_ids(text: str) -> set[str]:
    """Literal ids carried by an element whose ``class`` contains
    ``field-error`` (either attribute order), scanned line by line."""
    ids: set[str] = set()
    for line in text.splitlines():
        if "field-error" not in line:
            continue
        for m in re.finditer(r'class="[^"\n]*field-error[^"\n]*"[^>]*?id="([^"\'\n]+)"', line):
            ids.add(m.group(1))
        for m in re.finditer(r'id="([^"\'\n]+)"[^>]*?class="[^"\n]*field-error[^"\n]*"', line):
            ids.add(m.group(1))
    return ids


def find_label_for_without_control(js_dir: Path = JS_DIR) -> dict[str, set[str]]:
    """Return ``{for_target: {files}}`` for every literal ``<label for="X">``
    whose ``X`` resolves to no literal control ``id="X"`` in the SAME file
    (helper-indirected targets excepted). Empty dict is the passing state."""
    viol: dict[str, set[str]] = {}
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        ids = _literal_ids(text)
        param = set(_ATTR_FOR_PARAM.findall(text))
        for target in _ATTR_FOR.findall(text):
            if target in param or target in FIELD_FOR_ID_HELPER_INDIRECTED:
                continue
            if target not in ids:
                viol.setdefault(target, set()).add(js_file.relative_to(js_dir).as_posix())
    return viol


def find_invalid_describedby_without_field_error(js_dir: Path = JS_DIR) -> dict[str, set[str]]:
    """Return ``{describedby_target: {files}}`` for every control that carries
    BOTH ``is-invalid`` and a literal ``aria-describedby="Y"`` on the same line
    where ``Y`` resolves to no ``.field-error`` element ``id="Y"`` in the file.
    Empty dict is the passing state (no inline-validation site drops its error
    message association). Line-scoped: a control's class + aria-describedby are
    authored on one HTML-string fragment line."""
    viol: dict[str, set[str]] = {}
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        error_ids = _field_error_ids(text)
        param = set(_ATTR_ARIA_DESCRIBEDBY_PARAM.findall(text))
        for line in text.splitlines():
            if "is-invalid" not in line:
                continue
            for target in _ATTR_ARIA_DESCRIBEDBY.findall(line):
                if target in param:
                    continue
                if target not in error_ids:
                    viol.setdefault(target, set()).add(js_file.relative_to(js_dir).as_posix())
    return viol


# ── Sink classification ─────────────────────────────────────────────────────

# Assignment anchor: .innerHTML = / .outerHTML =  (excludes == / === reads).
_SINK_ASSIGN = re.compile(r"\.(innerHTML|outerHTML)\s*=(?!=)")

# Call anchor: .insertAdjacentHTML(
_SINK_CALL = re.compile(r"\.insertAdjacentHTML\s*\(")

# A complete single string-literal payload (single- or double-quoted,
# escapes allowed), nothing else.  Includes the empty-string clear ''.
_SINGLE_STRING_LITERAL = re.compile(r"^\s*('(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\")\s*$")


def _statement_end(text: str, start: int) -> int:
    """Index just past the ``;`` terminating the statement beginning at
    ``start``, tracking string state so semicolons inside string literals
    don't terminate early.  Falls back to end-of-text."""
    quote: str | None = None
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ";":
            return i + 1
        i += 1
    return n


def normalize_snippet(statement: str, width: int = 80) -> str:
    """Whitespace-collapsed first ``width`` chars of the statement."""
    return re.sub(r"\s+", " ", statement.strip())[:width]


def _line_start(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def classify_sinks(js_dir: Path = JS_DIR) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Classify every innerHTML/outerHTML assignment and
    insertAdjacentHTML call site.

    Returns ``(dynamic, static)`` — dicts mapping file path (relative to
    the js/ root) to the list of normalized statement snippets, in source
    order.  Duplicate snippets are kept (multiset semantics).
    """
    dynamic: dict[str, list[str]] = {}
    static: dict[str, list[str]] = {}
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        rel = relpath(js_file, js_dir)
        sites: list[tuple[int, bool]] = []  # (anchor pos, is_static)

        for m in _SINK_ASSIGN.finditer(text):
            rhs_start = m.end()
            end = _statement_end(text, rhs_start)
            rhs = text[rhs_start:end].rstrip(";")
            sites.append((m.start(), bool(_SINGLE_STRING_LITERAL.match(rhs))))

        for m in _SINK_CALL.finditer(text):
            args_start = m.end()
            end = _statement_end(text, args_start)
            args = text[args_start:end]
            # Payload = everything after the first comma, up to the
            # closing ');'.  Static iff it is a single string literal.
            comma = args.find(",")
            payload = args[comma + 1 :] if comma >= 0 else args
            payload = re.sub(r"\)\s*;?\s*$", "", payload)
            sites.append((m.start(), bool(_SINGLE_STRING_LITERAL.match(payload))))

        for pos, is_static in sorted(sites):
            stmt_start = _line_start(text, pos)
            stmt_end = _statement_end(text, pos)
            snippet = normalize_snippet(text[stmt_start:stmt_end])
            (static if is_static else dynamic).setdefault(rel, []).append(snippet)
    return dynamic, static


# ── markdown.js no-inner-HTML invariant guard (M17 F4 L1) ───────────────────
#
# The chat markdown pipeline's XSS guarantee is structural: markdown.js builds
# DOM exclusively via createElement/createTextNode/setAttribute/appendChild,
# never via an HTML-string sink. This guard freezes that invariant so a future
# edit reintroducing an inner-HTML seam fails loudly. See the "No vendoring" DD
# in the M17 F4 flight and the flight-log no-vendor decision record.

MARKDOWN_JS = JS_DIR / "markdown.js"

# The three literal HTML-string sink tokens that must NEVER appear in
# markdown.js (camelCase — the prose comments use the hyphenated "inner-HTML"
# spelling, which does not match). Word-boundary anchored.
_MARKDOWN_HTML_SINK_TOKENS = re.compile(r"\b(innerHTML|outerHTML|insertAdjacentHTML)\b")

# createElement(<arg>) call sites. `<arg>` captured up to the first `)` — the
# markdown renderer never nests parens inside a createElement argument.
_CREATE_ELEMENT_CALL = re.compile(r"createElement\(\s*([^)]*?)\s*\)")

# A bare single- or double-quoted string literal (escapes allowed), nothing
# else — e.g. 'p', 'div', 'blockquote'.
_STRING_LITERAL_ARG = re.compile(r"^('(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\")$")

# The ONLY two dynamic (non-string-literal) createElement tag expressions the
# markdown renderer is allowed to use, each proven bounded:
#   'h' + lvl             -> h1..h6  (lvl is clamped to 1..6 by the ATX-heading
#                                     parser regex /^(#{1,6})\s+/, so the tag is
#                                     always a valid heading element)
#   ordered ? 'ol' : 'ul' -> ol | ul (boolean ternary over two literals)
# Whitespace-normalized (single spaces). Any OTHER non-literal arg — notably a
# variable or a call carrying untrusted data — fails the guard.
#
# Allowance note (not a sink, do NOT "tighten" into a failure): injectIcon()
# uses `new DOMParser().parseFromString(svg, 'image/svg+xml')` to turn a
# TRUSTED icons.js SVG string (App.icon('copy'), a literal name) into DOM
# without an inner-HTML assignment. That is the sanctioned no-inner-HTML path
# for the copy-button glyph; it parses no untrusted data and is not scanned by
# this guard (createElement + the three sink tokens are the only surfaces).
MARKDOWN_DYNAMIC_CREATE_ELEMENT_ALLOWED: set[str] = {
    "'h' + lvl",
    "ordered ? 'ol' : 'ul'",
}


def find_markdown_html_sink_tokens(path: Path = MARKDOWN_JS) -> list[tuple[int, str, str]]:
    """Return ``(line_number, token, stripped_line)`` for every literal
    ``innerHTML``/``outerHTML``/``insertAdjacentHTML`` token in ``path``.
    Empty list is the passing state."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        for m in _MARKDOWN_HTML_SINK_TOKENS.finditer(line):
            hits.append((lineno, m.group(1), line.strip()))
    return hits


def find_markdown_bad_create_element_args(path: Path = MARKDOWN_JS) -> list[tuple[int, str]]:
    """Return ``(line_number, arg)`` for every ``createElement`` call whose
    argument is neither a bare string literal nor one of the two bounded
    dynamic-tag expressions in ``MARKDOWN_DYNAMIC_CREATE_ELEMENT_ALLOWED``.
    Empty list is the passing state."""
    text = path.read_text()
    bad: list[tuple[int, str]] = []
    for m in _CREATE_ELEMENT_CALL.finditer(text):
        arg = re.sub(r"\s+", " ", m.group(1).strip())
        if _STRING_LITERAL_ARG.match(arg):
            continue
        if arg in MARKDOWN_DYNAMIC_CREATE_ELEMENT_ALLOWED:
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        bad.append((lineno, arg))
    return bad


# ── JS-string dead-CSS-var tripwire (M17 F3 debrief rec 5) ───────────────────
#
# The F3 Leg-1 dead-alias miss: a JS string referenced `var(--token)` for a
# token that no longer existed in tokens.css. CSS treats an undefined custom
# property as `unset` (silent), and test_token_definitions.py only scans *.css
# — a `var(--x)` baked into a JS string (inline style / innerHTML template) is
# invisible to it. This tripwire closes that gap by scanning JS STRING LITERALS
# (comments excluded — the F4 survey found a prose `var(--space-N)` mention in a
# tokens-section.js comment that is NOT a real reference).

_JS_VAR_REF = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
_CSS_VAR_DEF = re.compile(r"^\s*(--[a-zA-Z0-9_-]+)\s*:", re.MULTILINE)
FONTS_CSS = REPO_ROOT / "the_one" / "interfaces" / "web" / "static" / "css" / "fonts.css"


def extract_js_string_contents(text: str) -> str:
    """Concatenate the interiors of every JS string literal (single-, double-,
    and backtick-quoted) in ``text``, newline-joined. Line (`//`) and block
    (`/* */`) comments are excluded, so prose references inside comments do not
    leak into the scan. Escape sequences inside strings are skipped."""
    out: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and i + 1 < n and text[i + 1] == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                out.append("".join(buf))
                buf = []
                quote = None
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        # Not currently inside a string or comment.
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        i += 1
    return "\n".join(out)


def defined_css_tokens() -> set[str]:
    """Every ``--token`` DEFINED in tokens.css or fonts.css (the canonical
    token modules)."""
    defined: set[str] = set()
    for css in (TOKENS_CSS, FONTS_CSS):
        if css.exists():
            defined |= set(_CSS_VAR_DEF.findall(css.read_text()))
    return defined


def find_js_dead_css_var_refs(js_dir: Path = JS_DIR) -> dict[str, set[str]]:
    """Return ``{token: {defining_files}}`` for every ``var(--token)`` found in
    a JS string literal whose token is NOT defined in tokens.css/fonts.css.
    Empty dict is the passing state."""
    defined = defined_css_tokens()
    dead: dict[str, set[str]] = {}
    for js_file in iter_js_files(js_dir):
        strings = extract_js_string_contents(js_file.read_text())
        for token in _JS_VAR_REF.findall(strings):
            if token not in defined:
                dead.setdefault(token, set()).add(relpath(js_file))
    return dead


# ── tokens.css theme-block parsing (mirror-sync guard) ──────────────────────

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# ``--token-name: value;`` declaration inside a (comment-stripped) block.
_TOKEN_DECL = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);")


def _strip_at_media_blocks(text: str) -> str:
    """Remove every top-level ``@media { ... }`` region (brace-matched).

    tokens.css redefines ``[data-theme=...]`` selectors inside its
    ``prefers-reduced-motion`` @media block (v3; the
    reduced-transparency block was deleted in M17 F2 L2a), so each
    theme selector can occur more than once. The mirror pins the
    top-level values, so the @media regions must be stripped before
    locating the theme blocks.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        m = re.compile(r"@media\b").search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i : m.start()])
        # Skip to the block's opening brace, then to its matched close.
        brace = text.find("{", m.end())
        if brace < 0:
            break
        depth = 1
        j = brace + 1
        while j < n and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def parse_tokens_css_theme_blocks(css_path: Path = TOKENS_CSS) -> dict[str, dict[str, str]]:
    """Parse the two top-level theme blocks of ``tokens.css``.

    Returns ``{"dark": {token_name: raw_value}, "light": {...}}`` where
    ``token_name`` is the CSS custom-property name (``--fg-secondary``)
    and ``raw_value`` is the declaration value with comments stripped and
    whitespace collapsed. @media regions are removed first so only the
    top-level theme blocks are read.
    """
    text = _strip_at_media_blocks(css_path.read_text())
    blocks: dict[str, dict[str, str]] = {}
    for theme in ("dark", "light"):
        sel = f'[data-theme="{theme}"]'
        start = text.find(sel)
        assert start >= 0, f"tokens.css: no top-level {sel} block found"
        brace = text.find("{", start)
        depth = 1
        j = brace + 1
        while j < len(text) and depth:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
            j += 1
        body = _CSS_COMMENT.sub("", text[brace + 1 : j - 1])
        blocks[theme] = {
            name: re.sub(r"\s+", " ", value.strip()) for name, value in _TOKEN_DECL.findall(body)
        }
    return blocks


def normalize_css_color(value: str) -> str:
    """Normalize a CSS color value for comparison: lowercase, collapsed
    whitespace, ``#rgb`` expanded to ``#rrggbb``."""
    v = re.sub(r"\s+", " ", value.strip()).lower()
    m = re.fullmatch(r"#([0-9a-f]{3})", v)
    if m:
        v = "#" + "".join(c * 2 for c in m.group(1))
    return v


# ── Banned design vocabulary (M17 F2 L3 banned-token guard) ─────────────────

CSS_DIR = REPO_ROOT / "the_one" / "interfaces" / "web" / "static" / "css"

# Retired alien-console vocabulary (M17 F2 retirement, SC1 enforcement).
# Patterns are PREFIX-ANCHORED custom-property names (``--bezel-``, not the
# bare word "bezel") so prose mentions in comments — e.g. the "no gradient,
# no bezel" chip note in components.css — don't false-positive. Comments DO
# count as hits for the token names themselves: the retired vocabulary was
# scrubbed from comments in L2a and must not creep back even as prose
# references to ``--glass-*``-style names.
BANNED_CSS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("--accent-glow", re.compile(r"--accent-glow")),
    ("--status-*-glow", re.compile(r"--status-[a-z0-9-]*glow")),
    ("--glass-*", re.compile(r"--glass-")),
    ("--bezel-*", re.compile(r"--bezel-")),
    ("--btn-v3*", re.compile(r"--btn-v3")),
    ("--panel-shadow", re.compile(r"--panel-shadow")),
    ("--shell-*", re.compile(r"--shell-")),
    ("backdrop-filter", re.compile(r"backdrop-filter")),
    ("clip-path: polygon", re.compile(r"clip-path\s*:\s*polygon")),
    ("prefers-reduced-transparency", re.compile(r"prefers-reduced-transparency")),
]


def find_banned_css_vocabulary(
    css_dir: Path = CSS_DIR,
) -> list[tuple[str, int, str, str]]:
    """Scan every ``*.css`` under ``css_dir`` for the retired vocabulary.

    Returns ``(relative_file, line_number, pattern_label, stripped_line)``
    hits in file/line order. Line-scoped so failures name file+line;
    comments are scanned like live code.
    """
    hits: list[tuple[str, int, str, str]] = []
    for css_file in sorted(css_dir.rglob("*.css")):
        rel = css_file.relative_to(css_dir).as_posix()
        for lineno, line in enumerate(css_file.read_text().splitlines(), start=1):
            for label, pattern in BANNED_CSS_PATTERNS:
                if pattern.search(line):
                    hits.append((rel, lineno, label, line.strip()))
    return hits


# ── Backtick tripwire (M17 F2 L3) ───────────────────────────────────────────

# A line-scoped backtick pair whose content mentions data-testid. Testid
# extraction above is calibrated for single-quoted JS strings; a template
# literal carrying a testid would be invisible to it, so backtick-quoted
# testids are banned outright (comments scan like live code — write
# 'data-testid' with quotes in comments, not backticks). Line-scoped: a
# multi-line template literal's interior lines are out of reach, but the
# innerHTML-RHS pattern below catches the sink that would carry one.
_BACKTICK_TESTID = re.compile(r"`[^`\n]*data-testid[^`\n]*`")

# Template-literal payload feeding an HTML sink: ``.innerHTML = ` `` /
# ``.outerHTML = ` `` (RHS may start on the next line) and
# ``insertAdjacentHTML(pos, ` ``. Sink classification above joins
# statements by ``;`` and tracks only '/" quoting — a backtick payload
# would be misparsed, so it is banned at the source.
_BACKTICK_HTML_ASSIGN = re.compile(r"\.(?:innerHTML|outerHTML)\s*=(?!=)\s*`")
_BACKTICK_INSERT_ADJACENT = re.compile(r"insertAdjacentHTML\s*\(\s*[^),`]*,\s*`")


def find_backtick_tripwire_hits(js_dir: Path = JS_DIR) -> list[tuple[str, int, str, str]]:
    """Scan JS sources for backtick-quoted testids and backtick HTML-sink
    payloads. Returns ``(relative_file, line_number, kind, excerpt)``."""
    hits: list[tuple[str, int, str, str]] = []
    for js_file in iter_js_files(js_dir):
        text = js_file.read_text()
        rel = relpath(js_file)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _BACKTICK_TESTID.search(line):
                hits.append((rel, lineno, "backtick-quoted data-testid", line.strip()))
        for kind, pattern in (
            ("backtick innerHTML/outerHTML payload", _BACKTICK_HTML_ASSIGN),
            ("backtick insertAdjacentHTML payload", _BACKTICK_INSERT_ADJACENT),
        ):
            for m in pattern.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                excerpt = normalize_snippet(text[_line_start(text, m.start()) :])
                hits.append((rel, lineno, kind, excerpt))
    return sorted(hits)


# ── Registry doc parsing ────────────────────────────────────────────────────

_TABLE_ROW = re.compile(r"^\|\s*`?([^`|]+?)`?\s*\|")


def parse_registry(
    doc_path: Path = REGISTRY_DOC,
) -> tuple[list[str], list[str], list[str]]:
    """Parse the registry doc's three tables.

    Returns ``(literal_ids, parametric_prefixes, manual_exception_ids)``
    as lists in document order (lists, not sets, so callers can detect
    duplicate rows).  Rows are recognized by their first cell; header and
    separator rows are skipped.
    """
    literal_ids: list[str] = []
    parametric_prefixes: list[str] = []
    manual_ids: list[str] = []
    section: list[str] | None = None
    for line in doc_path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip().lower()
            if heading.startswith("literal"):
                section = literal_ids
            elif heading.startswith("parametric"):
                section = parametric_prefixes
            elif heading.startswith("manual"):
                section = manual_ids
            else:
                section = None
            continue
        if section is None or not stripped.startswith("|"):
            continue
        m = _TABLE_ROW.match(stripped)
        if not m:
            continue
        cell = m.group(1).strip()
        # Skip header and separator rows.
        if cell.lower() in {"testid", "prefix", "id"} or set(cell) <= {"-", ":", " "}:
            continue
        section.append(cell)
    return literal_ids, parametric_prefixes, manual_ids
