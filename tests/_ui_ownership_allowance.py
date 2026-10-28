"""Allowance for ``tests/test_ui_ownership.py`` (see its docstring for the ratchet).

Closed state (M31 F6 L09a): every table here is empty and stays empty; a use outside ``js/ui/``
is a failure, not an allowance.

M31 F5 L01 adds the move rule: ``TOTAL_USES`` (exact per-key totals across every file),
``START_ROWS`` (the rows that existed at the flight's start) and ``MOVES`` (a file split's
bookkeeping). All paths are relative to ``static/`` (``js/areas/...``, ``css/...``).
"""

from typing import NamedTuple

OWNERSHIP_ALLOWANCE: dict[tuple[str, str], int] = {}


class OwnershipMove(NamedTuple):
    """``uses`` of ``key`` moved from ``from_file`` to ``to_file`` by a split.

    ``retire_by`` names the leg by which the entry is deleted (documentation, not checked per
    leg): the flight's Verification requires this table to be empty at landing.
    """

    key: str
    from_file: str
    to_file: str
    uses: int
    retire_by: str


# Closed at M31 F6 L09a: there are no allowance rows, so a row outside this (empty) set is a NEW
# row and needs ``MOVES`` entries (a split is the only sanctioned way to create one).
START_ROWS: frozenset[tuple[str, str]] = frozenset()

MOVES: list[OwnershipMove] = [
    # Empty: every move retired by M31 F6 L07; closed for the mission at L09a.
]

# Exact total of every key across every file, measured at M31 F5 L01. A key absent here counts 0.
# Lower it in the same change that removes uses; never raise it without a flight-log reason.
TOTAL_USES: dict[str, int] = {}
