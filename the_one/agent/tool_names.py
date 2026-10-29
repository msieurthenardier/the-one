"""Tool-name constants, in a leaf module (Mission 33 F2 L3, DD7).

Imports nothing from ``notes`` or ``routines``, so ``taint.py`` can name the trusted
tools without an import cycle. ``notes/tools.py`` re-exports the notes names.
"""

from __future__ import annotations

from the_one.time_zones import CURRENT_TIME_TOOL_NAME

SAVE_NOTE_TOOL_NAME = "save_note"
UPDATE_NOTE_TOOL_NAME = "update_note"
FORGET_NOTE_TOOL_NAME = "forget_note"
NOTES_TOOL_NAMES = (SAVE_NOTE_TOOL_NAME, UPDATE_NOTE_TOOL_NAME, FORGET_NOTE_TOOL_NAME)

LIST_ROUTINES_TOOL_NAME = "list_my_routines"
SCHEDULE_ROUTINE_TOOL_NAME = "schedule_routine"
CHANGE_ROUTINE_TOOL_NAME = "change_routine"
CANCEL_ROUTINE_TOOL_NAME = "cancel_routine"
ROUTINE_TOOL_NAMES = (
    LIST_ROUTINES_TOOL_NAME,
    SCHEDULE_ROUTINE_TOOL_NAME,
    CHANGE_ROUTINE_TOOL_NAME,
    CANCEL_ROUTINE_TOOL_NAME,
)

__all__ = [
    "CANCEL_ROUTINE_TOOL_NAME",
    "CHANGE_ROUTINE_TOOL_NAME",
    "CURRENT_TIME_TOOL_NAME",
    "FORGET_NOTE_TOOL_NAME",
    "LIST_ROUTINES_TOOL_NAME",
    "NOTES_TOOL_NAMES",
    "ROUTINE_TOOL_NAMES",
    "SAVE_NOTE_TOOL_NAME",
    "SCHEDULE_ROUTINE_TOOL_NAME",
    "UPDATE_NOTE_TOOL_NAME",
]
