"""Verify every ``var(--x)`` reference in CSS files has a corresponding
token definition somewhere in ``tokens.css`` or ``fonts.css``.

CSS treats undefined custom properties as ``unset`` rather than raising
an error — a typo like ``var(--accnet)`` silently renders no colour and
the bug only surfaces visually.  This test catches the typo at CI time
by parsing all ``static/css/*.css`` files and asserting every referenced
token has a definition in the canonical token modules.

Notes:

- The regex matches ``var(--name)`` and ``var(  --name  )``.  It does
  NOT match ``var(--name, fallback)`` if a fallback is present — but
  the codebase doesn't use the fallback form (verified by grep).  If a
  future leg introduces fallbacks, broaden the regex.
- Definitions may live in ``tokens.css`` (theme-scoped values) or
  ``fonts.css`` (theme-agnostic typography scale).  Both are aggregated
  into a single ``defined`` set.
- Component CSS files (``base.css``, ``chat.css``, etc.) are scanned
  for references; the token modules themselves are excluded from the
  reference scan so self-references inside ``var(--accent-glow)`` etc.
  don't get double-counted.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS_DIR = Path(__file__).parent.parent / "the_one" / "interfaces" / "web" / "static" / "css"

# ``var(--token-name)`` references.  The capture group strips the leading
# whitespace and the ``var(`` prefix; the ``--name`` is what we want.
VAR_REF_PATTERN = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")

# Token definitions ``--token-name: value;`` at the start of a line
# (allowing indentation).  The ``:`` enforces "this is a definition" and
# excludes incidental occurrences of ``--name`` in comments.
VAR_DEF_PATTERN = re.compile(r"^\s*(--[a-zA-Z0-9_-]+)\s*:", re.MULTILINE)


def _extract_var_references(css_path: Path) -> set[str]:
    return set(VAR_REF_PATTERN.findall(css_path.read_text()))


def _extract_var_definitions(css_path: Path) -> set[str]:
    return set(VAR_DEF_PATTERN.findall(css_path.read_text()))


def test_every_var_reference_is_defined() -> None:
    """Every ``var(--x)`` referenced in component CSS must be defined in
    ``tokens.css`` or ``fonts.css``.  Catches typos that wouldn't fail
    at runtime."""
    tokens_path = CSS_DIR / "tokens.css"
    assert tokens_path.exists(), f"Missing canonical tokens file: {tokens_path}"

    defined = _extract_var_definitions(tokens_path)

    fonts_path = CSS_DIR / "fonts.css"
    if fonts_path.exists():
        defined |= _extract_var_definitions(fonts_path)

    referenced: set[str] = set()
    referencing_files: dict[str, set[Path]] = {}
    for css_file in sorted(CSS_DIR.glob("*.css")):
        if css_file.name in {"tokens.css", "fonts.css"}:
            continue
        refs = _extract_var_references(css_file)
        referenced |= refs
        for token in refs:
            referencing_files.setdefault(token, set()).add(css_file)

    undefined = referenced - defined

    if undefined:
        # Build a human-friendly failure message naming each missing
        # token plus the file(s) that reference it — saves a manual
        # grep step when the test fails.
        lines = ["Undefined CSS custom properties referenced:"]
        for token in sorted(undefined):
            files = ", ".join(sorted(p.name for p in referencing_files[token]))
            lines.append(f"  {token}  (referenced in: {files})")
        lines.append("")
        lines.append(f"Defined tokens ({len(defined)}): {sorted(defined)}")
        raise AssertionError("\n".join(lines))
