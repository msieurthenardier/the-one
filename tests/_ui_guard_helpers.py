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

# Selector reference: [data-testid="foo"] — used in querySelector strings.
_SELECTOR_REF = re.compile(r'\[data-testid="([^"\'\n\]]+)"\]')


def iter_js_files(js_dir: Path = JS_DIR) -> list[Path]:
    return sorted(js_dir.rglob("*.js"))


def relpath(path: Path) -> str:
    """Path relative to the js/ root, as a forward-slash string."""
    return path.relative_to(JS_DIR).as_posix()


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
        rel = relpath(js_file)
        for testid in _ATTR_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for testid in _SETATTR_LITERAL.findall(text):
            literals.setdefault(testid, set()).add(rel)
        for prefix in _ATTR_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for prefix in _SETATTR_PARAMETRIC.findall(text):
            parametric.setdefault(prefix, set()).add(rel)
        for testid in _SELECTOR_REF.findall(text):
            selector_refs.setdefault(testid, set()).add(rel)
    return literals, parametric, selector_refs


def id_appears_as_string_literal(testid: str, js_dir: Path = JS_DIR) -> bool:
    """True if ``testid`` appears as a complete quoted string literal
    anywhere in the JS sources.  Used for manual-exception ids (variable-
    carried literals) so their deletion is still caught."""
    pattern = re.compile("['\"]" + re.escape(testid) + "['\"]")
    return any(pattern.search(f.read_text()) for f in iter_js_files(js_dir))


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
        rel = relpath(js_file)
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
