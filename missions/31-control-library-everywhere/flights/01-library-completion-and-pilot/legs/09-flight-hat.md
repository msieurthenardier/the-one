# Leg: flight-hat

**Status**: completed
**Flight**: [Library completion and a stateful pilot](../flight.md)

## Objective
The operator walks the provider surfaces and the Settings nav on a dedicated dev instance, in both themes. The walk confirms that:
- the codified library reproduces the look;
- every visible difference traces to DD8, or the operator approves it;
- the key, sign-in and models-panel behaviour hold;
- the before and after capture set is approved (the mission's capture criterion).

## Context
- Flight DD8 (the canonical versions; some were recommended without an explicit operator pick, so they are re-confirmed here), DD10 (captures), DD11.
- The before set is `$HOME/.cache/the-one-ui-capture/m31-f1-before/` and the after set is `$HOME/.cache/the-one-ui-capture/m31-f1-after/` (and `-after-06/`).
- **Differences already recorded** in the flight log, which the operator approves or rejects:
  1. Test button: standard size, play icon (DD8).
  2. Danger-zone Delete: 16px trash icon; armed label "Confirm delete?", in the armed style (DD8).
  3. The Extended thinking switch: the library switch, placed before its label (operator picks: switch A, label B).
  4. Test result and token expiry: LED plus text, with no coloured text and no glyphs (DD8 status line).
  5. The sign-in consent block: the shared consent link. It has a 560px max width, a mono URL field, Open as a real link, and Copy showing "Copied" (DD8 copy feedback).
  6. Models panel: Refresh at the small size with a 14px icon; row Delete armed style (DD8).
  7. **Not in DD8; queued for the operator:** the pull select now uses the canonical `field-select` (custom chevron, about 10px shorter), matching the editor's other selects.
- **Fix-vs-feature gate:** a look-and-feel fix rides inline. New behaviour goes through a scoped design review first. A change spanning more than one surface gets a quick Developer design pass before the fix.

## Inputs
- The flight committed on `flight/01-library-completion-and-pilot`; the draft PR open.
- A dev instance:
  - port 8486 or higher (never 8484 or 8485);
  - a scratch data dir under `$HOME`;
  - started from a scratch cwd;
  - `THE_ONE_DEV_MODE=true`;
  - seeded with one provider of each type, plus one agent that uses one of them.

  An optional local Ollama makes step 6 live; otherwise step 6 reads the capture stills.

## HAT steps (state transitions)
1. **[fresh] Open the dev instance** through its handoff URL. Settings shows six pages in two groups ("General", "Defaults for agents"), with no Developer group.
   - Visiting `#settings/design-language` lands on a real page (no blank pane).
   - Ctrl K, then "design": no Design language result.
   - No error messages.
2. **[library] → [create]. Library › Add › Model provider.**
   - Breadcrumb "Library / Model providers", title "New model provider".
   - Cancel is enabled, Create is disabled until a field changes.
   - Switch the type to Anthropic: Extended thinking appears as a switch before its label, with an info button after it. Tab reaches the switch, then the info button. The info button's tooltip shows the description.
   - Cancel abandons creation and focus goes back to the list.
3. **[edit] Open an OpenAI-compatible provider.**
   - Header: Cancel, Save and Test are the same height. Test shows a play icon. The unsaved caption appears after an edit and clears after Save.
   - Press Test: a status line with an LED and the result text, no ✓/✗ glyphs. A flash appears.
   - No error messages.
4. **[edit] → [key]. Type a new API key and Save.**
   - After Save, the field shows the masked value again, hidden. The reveal button shows the masked value, not the typed key.
   - Save again without touching the key: no error, and the key is unchanged.
   - Cancel after typing restores the masked value.
5. **[edit] → [delete]. Danger Zone.**
   - Delete shows a trash icon. The first click arms it: "Confirm delete?" in the armed style, including while hovered.
   - Wait 3s: it lapses with the lapse cue.
   - On a provider used by an agent, the click shows the blocked notice.
6. **[ollama] The models panel** (live Ollama, or the capture stills).
   - Refresh keeps the list in place and focus where it was.
   - Load or Unload moves a row between Running and Available without the panel blinking.
   - With live Ollama, during a Pull: the progress bar and its Cancel survive a Refresh, and Cancel stops the pull.
   - Squawk 0139: cached library models show while the library list refreshes.
   - **Decide item 7** (the pull select style).
7. **[plan] Open the Claude Plan (OAuth) provider and press Sign in.**
   - The consent block appears: the URL field, an "Open sign-in page" link, Copy and the code field. Copy shows "Copied".
   - Do not complete sign-in; reset or close.
   - Claude Plan (Token) shows its "expires around" line as a status line.
8. **[theme] Switch to the other theme** (Settings › Appearance) and repeat a quick look at steps 3, 5 and 7. Nothing reads wrong.
9. **[captures] Review the before and after set**, either side by side or through a private comparison page the Flight Director can publish on request. Approve the set, or name each difference to change.
10. **[confirm] DD8 re-confirmation.** The operator confirms or amends the recommended canonical versions that had no explicit pick:
    - the editor header;
    - one error style;
    - the danger zone labels;
    - the armed style everywhere;
    - merged tiles;
    - chip remove;
    - status line;
    - disclosures;
    - icon sizes.

    These bind Flights 2-4.
11. **Optional: [desktop]** the same editor in the desktop window, `the-one app` against a scratch data dir.

## Acceptance Criteria
- [ ] Every step passes, or each failure is fixed and re-verified (fixes recorded in the flight log).
- [ ] Items 1-7 above are approved or changed by the operator; item 7 is decided.
- [ ] The before and after capture set is approved (the mission's capture criterion for this flight).
- [ ] DD8's recommended versions are confirmed or amended, and the flight spec records the outcome.

## Edge Cases
- **No live Ollama:** step 6 uses the stills and the browser-test evidence (`test_flow_provider_models_patch.py`), and records that.
- **A fix that touches other surfaces:** route it through a Developer design pass first.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
