"""Frozen allowance for ``tests/test_ui_ownership.py`` (see its docstring for the ratchet).

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


# Keys of ``OWNERSHIP_ALLOWANCE`` as of M31 F6 L01. A row outside this set is a NEW row and
# needs ``MOVES`` entries (a split is the only sanctioned way to create one).
START_ROWS: frozenset[tuple[str, str]] = frozenset(
    {
        ("css/chat.css", "badge"),
        ("css/chat.css", "field-input"),
        ("css/chat.css", "ui-drawer-header"),
        ("css/chat.css", "ui-list-pane"),
        ("css/chat.css", "ui-search-list"),
        ("css/chat.css", "ui-search-list-empty"),
        ("css/chat.css", "ui-search-list-field"),
        ("css/chat.css", "ui-search-list-listbox"),
        ("css/studio.css", "editor-section"),
        ("css/studio.css", "field-input"),
        ("css/studio.css", "tabpanel"),
        ("css/studio.css", "ui-list-pane"),
        ("js/areas/chat.js", "api:App.confirmDelete("),
        ("js/areas/chat.js", "api:App.consentLink."),
        ("js/areas/chat.js", "btn-filled-primary"),
        ("js/areas/chat.js", "chip"),
        ("js/areas/chat.js", "confirm-delete"),
        ("js/areas/chat.js", "consent-link"),
        ("js/areas/chat/agent-drawer.js", "badge"),
        ("js/areas/chat/agent-picker.js", "modal-dialog-footer-end"),
        ("js/areas/chat/chat-pane.js", "badge"),
        ("js/icons.js", "api:App.icon("),
        ("js/icons.js", "api:App.iconNode("),
    }
)

MOVES: list[OwnershipMove] = [
    # M31 F6 L02: the chat.js split (DD3); the uses move verbatim, then each leg below retires them.
]

# Exact total of every key across every file, measured at M31 F5 L01. A key absent here counts 0.
# Lower it in the same change that removes uses; never raise it without a flight-log reason.
TOTAL_USES: dict[str, int] = {}
