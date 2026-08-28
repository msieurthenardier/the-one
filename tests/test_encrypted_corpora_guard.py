"""Guard test: `_ENCRYPTED_CORPORA` and `rotate_encryption_key`'s SQL must agree.

The set of encrypted columns is enumerated twice — as data in
`the_one/db/key_reconcile.py:_ENCRYPTED_CORPORA` and as hand-written
SELECT/UPDATE statements in `the_one/interfaces/web/api.py:rotate_encryption_key`.
Nothing else enforces that the two agree; Mission 22 Flight 1 Decision D1 found
two corpora that had drifted out of the rotation route for several missions.

This test parses the route's own source (`inspect.getsource`) with a pair of
tolerant regexes — one for `SELECT col[, col...] FROM table`, one for
`UPDATE table SET col = ?[, col = ?...]`  — derives the `{(table, column)}`
set each side touches, and asserts both sets equal `_ENCRYPTED_CORPORA`. The
two extractions are independent (one from the read half of the route, one
from the write half), so a corpus that's read but never written back — or
written but never read — fails here too, not just a corpus missing from the
registry entirely.
"""

from __future__ import annotations

import inspect
import re

from the_one.db.key_reconcile import _ENCRYPTED_CORPORA
from the_one.interfaces.web import api as api_module

# Columns used to identify *which row* a query touches (primary/lookup keys),
# never an encrypted corpus column in their own right. Every SELECT in the
# route leads with one of these before its actual corpus column(s).
_LOOKUP_COLUMNS = {"id", "name", "identifier"}

_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"

# Tolerant of the route's queries spanning whitespace/newlines (adjacent
# string-literal concatenation, wrapped lines) — `.+?` with DOTALL rather than
# a same-line anchor.
_SELECT_RE = re.compile(
    rf"SELECT\s+(?P<cols>.+?)\s+FROM\s+(?P<table>{_IDENTIFIER})",
    re.IGNORECASE | re.DOTALL,
)
_UPDATE_RE = re.compile(
    rf"UPDATE\s+(?P<table>{_IDENTIFIER})\s+SET\s+(?P<set_clause>.+?)\s+WHERE",
    re.IGNORECASE | re.DOTALL,
)


def _extract_select_pairs(source: str) -> set[tuple[str, str]]:
    """Derive {(table, column)} from every `SELECT ... FROM <table>` in *source*."""
    pairs: set[tuple[str, str]] = set()
    for match in _SELECT_RE.finditer(source):
        table = match.group("table")
        cols_blob = re.sub(r"\s+", " ", match.group("cols")).strip()
        for raw_col in cols_blob.split(","):
            col = raw_col.strip()
            if not col or col.lower() in _LOOKUP_COLUMNS:
                continue
            if not re.fullmatch(_IDENTIFIER, col):
                # Not a bare column name (e.g. a WHERE fragment the lazy
                # `.+?` swallowed) — skip rather than mis-derive a pair.
                continue
            pairs.add((table, col))
    return pairs


def _extract_update_pairs(source: str) -> set[tuple[str, str]]:
    """Derive {(table, column)} from every `UPDATE <table> SET col = ?` in *source*."""
    pairs: set[tuple[str, str]] = set()
    for match in _UPDATE_RE.finditer(source):
        table = match.group("table")
        set_blob = re.sub(r"\s+", " ", match.group("set_clause")).strip()
        for assignment in set_blob.split(","):
            col = assignment.split("=", 1)[0].strip()
            if re.fullmatch(_IDENTIFIER, col):
                pairs.add((table, col))
    return pairs


def _format_mismatch(label: str, derived: set[tuple[str, str]]) -> str:
    expected = set(_ENCRYPTED_CORPORA)
    missing = expected - derived
    extra = derived - expected
    return (
        f"{label} out of sync with the_one/db/key_reconcile.py:_ENCRYPTED_CORPORA.\n"
        f"  missing from the_one/interfaces/web/api.py:rotate_encryption_key {label}: "
        f"{sorted(missing)}\n"
        f"  present in rotate_encryption_key {label} but absent from _ENCRYPTED_CORPORA: "
        f"{sorted(extra)}\n"
        "Update whichever side is stale so every encrypted (table, column) pair is "
        "both listed in _ENCRYPTED_CORPORA and read/written by the rotation route."
    )


def test_encrypted_corpora_matches_rotation_route_reads() -> None:
    source = inspect.getsource(api_module.rotate_encryption_key)
    select_pairs = _extract_select_pairs(source)
    # Sanity check on the extractor itself: if this trips, the regex found
    # nothing to compare against and the test below would pass vacuously.
    assert select_pairs, "extractor found no SELECT ... FROM pairs in rotate_encryption_key"
    assert select_pairs == set(_ENCRYPTED_CORPORA), _format_mismatch("SELECT reads", select_pairs)


def test_encrypted_corpora_matches_rotation_route_writes() -> None:
    source = inspect.getsource(api_module.rotate_encryption_key)
    update_pairs = _extract_update_pairs(source)
    assert update_pairs, "extractor found no UPDATE ... SET pairs in rotate_encryption_key"
    assert update_pairs == set(_ENCRYPTED_CORPORA), _format_mismatch("UPDATE writes", update_pairs)
