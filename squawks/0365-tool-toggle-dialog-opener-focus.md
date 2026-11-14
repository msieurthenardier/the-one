# Squawk 0365: the "Turning on X affects N agents" dialog may not return focus to the switch for mouse users

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-11-14
**Completed**: —

## Report
Squawk 0322 added a confirm dialog before an enabling toggle on Settings › Built-in tools. `handleToolToggle` takes the dialog's opener from `document.activeElement`. A browser that does not focus a checkbox on click (Safari on macOS) leaves `activeElement` on the body, so the opener is null and focus does not return to the switch when the dialog closes for a mouse user.

Fix: take the opener from the event target or the tile's control, not from `document.activeElement`.

Also in the same change: the dialog can still open for a tool after the operator has left the Built-in tools page while the impact preview was pending. It is harmless, but guard it (check the page is still the live one before opening the dialog).

## Evidence
- `the_one/interfaces/web/static/js/areas/admin/tools-page.js::handleToolToggle`: `var active = document.activeElement; var opener = active && active !== document.body ? active : null;` (lines ~321-322), then `opener: opener || undefined` (line ~341).
- Found by the reviews of squawk 0322 (2026-11-14 turnaround).
