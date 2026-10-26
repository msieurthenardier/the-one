"""Frozen allowance for ``tests/test_ui_ownership.py`` (see its docstring for the ratchet).

M31 F5 L01 adds the move rule: ``TOTAL_USES`` (exact per-key totals across every file),
``START_ROWS`` (the rows that existed at the flight's start) and ``MOVES`` (a file split's
bookkeeping). All paths are relative to ``static/`` (``js/areas/...``, ``css/...``).
"""

from typing import NamedTuple

OWNERSHIP_ALLOWANCE: dict[tuple[str, str], int] = {
    ("css/chat.css", "badge"): 1,
    ("css/chat.css", "field-input"): 1,
    ("css/chat.css", "ui-drawer-header"): 1,
    ("css/chat.css", "ui-list-pane"): 1,
    ("css/chat.css", "ui-search-list"): 1,
    ("css/chat.css", "ui-search-list-empty"): 1,
    ("css/chat.css", "ui-search-list-field"): 2,
    ("css/chat.css", "ui-search-list-listbox"): 1,
    ("css/studio.css", "editor-section"): 1,
    ("css/studio.css", "field-input"): 2,
    ("css/studio.css", "tabpanel"): 1,
    ("css/studio.css", "ui-list-pane"): 2,
    ("js/areas/chat.js", "api:App.confirmDelete("): 1,
    ("js/areas/chat.js", "api:App.consentLink."): 4,
    ("js/areas/chat.js", "btn-filled-primary"): 1,
    ("js/areas/chat.js", "chip"): 1,
    ("js/areas/chat.js", "confirm-delete"): 2,
    ("js/areas/chat.js", "consent-link"): 1,
    ("js/areas/chat/agent-drawer.js", "badge"): 2,
    ("js/areas/chat/agent-picker.js", "modal-dialog-footer-end"): 1,
    ("js/areas/chat/chat-pane.js", "badge"): 2,
    ("js/areas/studio/mcp-server-editor.js", "api:App.confirmDelete("): 1,
    ("js/areas/studio/mcp-server-editor.js", "api:App.icon("): 1,
    ("js/areas/studio/mcp-server-editor.js", "api:App.showFlash("): 3,
    ("js/areas/studio/mcp-server-editor.js", "btn-filled-primary"): 1,
    ("js/areas/studio/mcp-server-editor.js", "btn-muted-destructive"): 1,
    ("js/areas/studio/mcp-server-editor.js", "btn-outlined-primary"): 1,
    ("js/areas/studio/mcp-server-editor.js", "danger-zone"): 1,
    ("js/areas/studio/mcp-server-editor.js", "danger-zone-title"): 1,
    ("js/areas/studio/mcp-server-editor.js", "delete-btn"): 2,
    ("js/areas/studio/mcp-server-editor.js", "editor-breadcrumb"): 1,
    ("js/areas/studio/mcp-server-editor.js", "editor-breadcrumb-link"): 1,
    ("js/areas/studio/mcp-server-editor.js", "editor-error"): 3,
    ("js/areas/studio/mcp-server-editor.js", "editor-header"): 1,
    ("js/areas/studio/mcp-server-editor.js", "editor-header-text"): 2,
    ("js/areas/studio/mcp-server-editor.js", "editor-section"): 2,
    ("js/areas/studio/mcp-server-editor.js", "editor-subtitle"): 1,
    ("js/areas/studio/mcp-server-editor.js", "editor-title"): 2,
    ("js/areas/studio/mcp-server-editor.js", "editor-unsaved"): 2,
    ("js/areas/studio/mcp-server-editor.js", "form-actions"): 1,
    ("js/areas/studio/mcp-server-editor.js", "section-title"): 2,
    ("js/icons.js", "api:App.icon("): 1,
    ("js/icons.js", "api:App.iconNode("): 1,
    ("js/markdown.js", "api:App.icon("): 1,
    ("js/markdown.js", "api:App.showFlash("): 3,
}


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


# Keys of ``OWNERSHIP_ALLOWANCE`` as of M31 F5 L01. A row outside this set is a NEW row and
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
        ("css/studio.css", "chip"),
        ("css/studio.css", "chip-list-editor"),
        ("css/studio.css", "chip-list-input"),
        ("css/studio.css", "editor-section"),
        ("css/studio.css", "field-info-icon"),
        ("css/studio.css", "field-input"),
        ("css/studio.css", "indicator-led"),
        ("css/studio.css", "tabpanel"),
        ("css/studio.css", "ui-chip-list"),
        ("css/studio.css", "ui-chip-list-input"),
        ("css/studio.css", "ui-list-pane"),
        ("js/areas/admin/tools-form-helpers.js", "chip"),
        ("js/areas/admin/tools-form-helpers.js", "chip-list-editor"),
        ("js/areas/admin/tools-form-helpers.js", "chip-list-input"),
        ("js/areas/chat.js", "api:App.confirmDelete("),
        ("js/areas/chat.js", "api:App.consentLink."),
        ("js/areas/chat.js", "btn-filled-primary"),
        ("js/areas/chat.js", "chip"),
        ("js/areas/chat.js", "confirm-delete"),
        ("js/areas/chat.js", "consent-link"),
        ("js/areas/chat/agent-drawer.js", "badge"),
        ("js/areas/chat/agent-picker.js", "modal-dialog-footer-end"),
        ("js/areas/chat/chat-pane.js", "badge"),
        ("js/areas/studio/mcp-server-editor.js", "api-key-eye"),
        ("js/areas/studio/mcp-server-editor.js", "api-key-wrap"),
        ("js/areas/studio/mcp-server-editor.js", "api:App.confirmDelete("),
        ("js/areas/studio/mcp-server-editor.js", "api:App.consentLink."),
        ("js/areas/studio/mcp-server-editor.js", "api:App.icon("),
        ("js/areas/studio/mcp-server-editor.js", "api:App.showFlash("),
        ("js/areas/studio/mcp-server-editor.js", "btn-filled-primary"),
        ("js/areas/studio/mcp-server-editor.js", "btn-muted-destructive"),
        ("js/areas/studio/mcp-server-editor.js", "btn-outlined-primary"),
        ("js/areas/studio/mcp-server-editor.js", "chip-list-editor"),
        ("js/areas/studio/mcp-server-editor.js", "chip-list-input"),
        ("js/areas/studio/mcp-server-editor.js", "danger-zone"),
        ("js/areas/studio/mcp-server-editor.js", "danger-zone-title"),
        ("js/areas/studio/mcp-server-editor.js", "delete-btn"),
        ("js/areas/studio/mcp-server-editor.js", "editor-breadcrumb"),
        ("js/areas/studio/mcp-server-editor.js", "editor-breadcrumb-link"),
        ("js/areas/studio/mcp-server-editor.js", "editor-error"),
        ("js/areas/studio/mcp-server-editor.js", "editor-header"),
        ("js/areas/studio/mcp-server-editor.js", "editor-header-text"),
        ("js/areas/studio/mcp-server-editor.js", "editor-section"),
        ("js/areas/studio/mcp-server-editor.js", "editor-subtitle"),
        ("js/areas/studio/mcp-server-editor.js", "editor-title"),
        ("js/areas/studio/mcp-server-editor.js", "editor-unsaved"),
        ("js/areas/studio/mcp-server-editor.js", "field-group"),
        ("js/areas/studio/mcp-server-editor.js", "field-info-icon"),
        ("js/areas/studio/mcp-server-editor.js", "field-input"),
        ("js/areas/studio/mcp-server-editor.js", "field-select"),
        ("js/areas/studio/mcp-server-editor.js", "form-actions"),
        ("js/areas/studio/mcp-server-editor.js", "indicator-led"),
        ("js/areas/studio/mcp-server-editor.js", "indicator-led--success"),
        ("js/areas/studio/mcp-server-editor.js", "section-title"),
        ("js/icons.js", "api:App.icon("),
        ("js/icons.js", "api:App.iconNode("),
        ("js/markdown.js", "api:App.icon("),
        ("js/markdown.js", "api:App.showFlash("),
    }
)

MOVES: list[OwnershipMove] = []

# Exact total of every key across every file, measured at M31 F5 L01. A key absent here counts 0.
# Lower it in the same change that removes uses; never raise it without a flight-log reason.
TOTAL_USES: dict[str, int] = {
    "api:App.confirmDelete(": 2,
    "api:App.consentLink.": 4,
    "api:App.icon(": 3,
    "api:App.iconNode(": 1,
    "api:App.showFlash(": 6,
    "badge": 5,
    "btn-filled-primary": 2,
    "btn-muted-destructive": 1,
    "btn-outlined-primary": 1,
    "chip": 1,
    "confirm-delete": 2,
    "consent-link": 1,
    "danger-zone": 1,
    "danger-zone-title": 1,
    "delete-btn": 2,
    "editor-breadcrumb": 1,
    "editor-breadcrumb-link": 1,
    "editor-error": 3,
    "editor-header": 1,
    "editor-header-text": 2,
    "editor-section": 3,
    "editor-subtitle": 1,
    "editor-title": 2,
    "editor-unsaved": 2,
    "field-input": 3,
    "form-actions": 1,
    "modal-dialog-footer-end": 1,
    "section-title": 2,
    "tabpanel": 1,
    "ui-drawer-header": 1,
    "ui-list-pane": 3,
    "ui-search-list": 1,
    "ui-search-list-empty": 1,
    "ui-search-list-field": 2,
    "ui-search-list-listbox": 1,
}
