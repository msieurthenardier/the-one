# Leg: prompts-and-encryption

**Status**: landed
**Flight**: [Settings on the library](../flight.md)

## Objective
Rebuild Settings › Prompts and Settings › Encryption on the library.
- **Prompts:** `section` per layer and `codeBlock`, with A1-A3 and B11, read through `fetchJson`.
- **Encryption:** a `banner` (A5), the rotate button through `App.ui.confirm` with sentence-case labels (A4), the result in an `App.ui.status` that never loses a staged warning to a timer (DD8-10), plain error text (DD8-11), focus kept (DD8-12), and a new read-only status route showing when the key was last rotated and how many stored credentials it covers (B12).

`codeBlock` takes ownership of `code-block` (DD12).

## Context
- **Flight decisions:** DD6 (Prompts, Encryption), DD8 10-12, DD7 (rows 1-5, 35, 36), DD12, DD3.
- **Tier HIGH:** a new backend route on the encryption surface.
- **Prompts today** (`system-page.js` about `:56-160`):
  - `promptLayer` is a `div.section-title` + `p` + `pre.admin-base-prompt.code-block`;
  - `platformSectionBlock` (`platform-section-{variant}-{id}[-applies-when|-text]` testids) for the platform sections;
  - captions (`.section-title`) at `:99`;
  - `fetch('/api/info')` with no `r.ok` check (an HTTP error shows "(platform prompt unavailable)").

  **After:**
  - one `App.ui.section` per layer, with the layer title as the stronger heading (B11): the layer title is the section's `h2`, and platform section titles are `h3`;
  - the "With tools"/"Without tools" variant is a sub-heading under its layer, not a second eyebrow (A3);
  - each text through `App.ui.codeBlock({text, trim: true, maxHeight: 'tall', label})` (A1);
  - caption spacing from the section stack (A2);
  - `App.api.fetchJson`, with a load error through `App.ui.status` that names the failure.

  Keep every `platform-section-*` and `*-prompt-content*` testid. Note text is attacker-influenced and stays `textContent` only (CLAUDE.md).
- **Encryption today** (`system-page.js` about `:180-250`):
  - `button.btn-muted-destructive > span[data-confirm-title]` "Rotate Encryption Key" (`rotate-key-btn`);
  - `App.confirmDelete(rotateBtn, …, {confirmLabel: 'Confirm Rotate?'})`;
  - a hand-built `div.admin-system-flash`;
  - `div.banner.banner-warning[role=note]`;
  - a raw `fetch('/api/encryption/rotate', {method: 'POST'})` reading `r.json().then(e => e.detail)` (a non-JSON body throws SyntaxError → "Error: Unexpected token…", DD8-11);
  - uncancelled `setTimeout` clears at `:236` (3 s) and `:244` (4 s) (DD8-10);
  - `btn.disabled = true` drops focus (DD8-12).

  **After:**
  - `pageHeader`, an intro line and a `banner` ({tone: 'warning'}, A5 wording: "The old key is discarded. This can't be undone.");
  - the B12 facts (`App.ui.facts`: "Last rotated" {date, time} or "Never", "Stored credentials" N);
  - the rotate button `App.ui.button({variant: 'danger' or today's muted-destructive look, label: 'Rotate encryption key'})` armed through `App.ui.confirm(btn, commit, {confirmLabel: 'Rotate key?'})` (A4);
  - the result in an `App.ui.status` (`rotate-result` testid):
    - **success** shows "Key rotated." and clears after 3 s;
    - **staged** shows the warning and **stays** until the next attempt;
    - **error** shows the message and stays until the next attempt;
    - **one timer handle**, cleared at the start of every attempt (DD8-10);
  - `fetchJson`, so a non-JSON error shows `fetchJson`'s "Server error N …" (DD8-11);
  - focus returns to the button through `App.focusAfter` (DD8-12);
  - after a rotation, the facts refresh.
- **B12, the new route:** `GET /api/encryption/status` → `{last_rotated_at: ISO|null, credential_count: int}`.
  - **`last_rotated_at`** is written by the rotate route on success (`AppMetadataRepository`, a key such as `encryption_last_rotated_at`), in the same transaction as the re-encryption. It is `null` before the first rotation on this install, and the interrupted-rotation reconcile (`the_one/db/key_reconcile.py`) sets it if it completes a rotation.
  - **`credential_count`** is the number of rows holding encrypted data across the seven corpora the rotate route re-encrypts (`api.py:6081` docstring): provider `api_key`, provider `secrets`, MCP source `secrets`, connector `secrets`, agent overrides, tool config `secrets`, external credentials. Count rows with a non-empty encrypted value. Read-only, behind the credential gate.
  - Check `SECURITY-MODEL.md`: the count and timestamp reveal no secret; record the check, and add a line if the document lists the encryption routes.
  - Unit tests: `null` then a timestamp after a rotation; the count changes when a provider with a key is added; the route requires the credential.

## Inputs
- Legs 03a (`fetchJson`), 04a (`pageHeader`, `banner`), 04b (`codeBlock`, `facts`), 08a (`renderPage` delegating) landed.

## Outputs
- `system-page.js` Prompts and Encryption on the library, with no hand-built section titles, banners, flashes or `pre`s. Its `OWNERSHIP_ALLOWANCE` rows (`section-title` 5, `btn-muted-destructive` 1, `api:App.confirmDelete(` 1) are gone.
- `the_one/interfaces/web/api.py`: `GET /api/encryption/status`, and the rotate route recording `last_rotated_at`; `key_reconcile.py` if needed.
- `admin.css`: `.admin-prompt-layer*`, `.platform-section*` overrides, `.admin-base-prompt`, `.admin-system-flash*`, `.admin-system-section .banner-warning` removed; `.admin-system-*` kept only where the remaining pages still use them (leg 10 finishes).
- `codeBlock`'s catalogue row lists `code-block` as owned (DD12). The emitted-class guard and `OWNERSHIP_ALLOWANCE` reflect the handover, with no area rule naming `code-block` left.
- Tests:
  - DD8-10 (success, then a second rotation within 3 s ending staged: the warning stays), DD8-11, DD8-12, test-first;
  - `test_flow_admin_rotate_flash.py` retargeted from `.admin-system-flash` classes to the status testid and `data-state`;
  - A1-A5, B11 and B12 checks;
  - the unit tests for the route.
- Docs: CLAUDE.md (the route, in the Settings or security paragraph), `the_one/agents.md`, the registry (`rotate-result`, `encryption-facts`), ledger rows confirmed by captures.

## Acceptance Criteria
1. **DD8-10, DD8-11 and DD8-12** tests fail before and pass after.
2. **The staged warning** persists until the next rotation attempt, and success clears after 3 s, with one timer.
3. **The rotate arm and confirm** behaves as before (the lapse cue tests pass), with labels "Rotate encryption key" and "Rotate key?".
4. **B12:** the route returns the shape above, with unit tests. The page shows "Last rotated {date}, {time}" (through `App.time`, ISO in `title`) or "Never", and "Stored credentials: N", refreshed after a rotation.
5. **Prompts:**
   - every `platform-section-*` testid is kept;
   - the code blocks are trimmed (A1);
   - captions have their space (A2);
   - no stacked eyebrows (A3);
   - the layer titles are the stronger heading (B11, the heading levels asserted);
   - an HTTP error shows an error status, not "(platform prompt unavailable)".
6. `system-page.js` has no allowance rows. `codeBlock` owns `code-block`.
7. The unit tier, the static guards, the emitted-class guard, and the `settings` and `agent-tabs` lanes pass (`agent-tabs` covers the self-configuration code blocks under the new ownership).

## Verification Steps
- `.venv/bin/python -m pytest tests/test_api_encryption*.py <new tests> tests/test_ui_guards.py tests/test_ui_ownership.py tests/test_ui_emitted_classes.py -q -x --timeout 120` (find the rotate route's existing tests and extend them).
- Lanes `settings` and `agent-tabs` under netns; the capture compare; `make test-unit` once.

## Edge Cases
- **Two tabs:** a rotation in one tab refreshes the facts there only. The other tab shows the old timestamp until its next activation. That is acceptable; record it.
- **A rotation that stages and later completes on restart** (`key_reconcile`): `last_rotated_at` is set by the reconcile.

## Files Affected
- `static/js/areas/admin/system-page.js`, `static/css/admin.css`, `the_one/interfaces/web/api.py`, possibly `the_one/db/key_reconcile.py`.
- `tests/browser/test_flow_admin_rotate_flash.py`, `test_flow_admin_settings_nav.py` (Prompts blocks), the unit tests for encryption.
- `SECURITY-MODEL.md` (if needed), CLAUDE.md, `the_one/agents.md`, `docs/ui-testid-registry.md`, `docs/ui-control-inventory.md`, the flight log.

## Citation Audit
- `api.py:6080-6081` the rotate route and its seven-corpora docstring; `:6403-6418` the log line and return: verified (FD read).
- `system-page.js:236`, `:244` timers: verified (FD read at planning).
- The Prompts lines and `admin.css` rules: from the pages survey.

## Design Review Amendments (cycle 1, 2026-10-23)
These override the body where they conflict.
- **`last_rotated_at` is written inside the rotate transaction with raw SQL.** `AppMetadataRepository.set` opens its own `write_transaction`, and nesting raises (`_write_lock.py`).
  - In the route's `async with write_transaction(conn):` block (`api.py` about `:6330`), run `INSERT INTO app_metadata(key, value) VALUES('encryption_last_rotated_at', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value` with a UTC ISO string. It commits and rolls back with the re-encryption.
  - Test that a forced failing UPDATE leaves the key unchanged, and that a `staged` outcome still stores the time.
- **`key_reconcile.py` is not touched.** Every crash after the commit already has the time stored, and reconcile cannot know when a rotation happened. Drop that bullet and its edge case.
- **`credential_count` is defined, and computed by decrypting in-process:**
  - **The unit is one per item that holds at least one non-empty secret:** a provider (its `api_key` or a non-empty `secrets`), an MCP source, a connector, an agent (non-empty `tool_overrides` or `mcp_overrides`), a tool config, an external credential. The page label reads "Items with stored secrets: N".
  - **Computed** by decrypting each corpus's values and counting non-empty strings or dicts, swallowing `InvalidToken` as residue (as rotate does). Nothing leaves the process.
  - **Factor the gather** into a helper shared with rotate's gather step, so the two can't drift.
  - Tolerate a missing table (as `sample_ciphertexts` does). If `encryptor.key_path is None`, return the count, not an error.
  - Tests:
    - an empty install gives 0;
    - a provider with a key gives 1;
    - a provider with an encrypted `{}` secrets blob and no key gives 0;
    - an agent with an encrypted empty override map gives 0.
- **The route also returns `key_file_pending: bool`** (`encryptor.pending_key is not None`), so a staged rotation keeps its warning across reloads: the page shows it as a persistent warning status. A test covers it.
- **The rotate control:**
  - `App.ui.button({variant: 'danger'})` (maps to `btn-muted-destructive`, removing the allowance row) armed by `App.ui.confirm(btn, commit, {confirmLabel: 'Rotate key?', announceName: 'Rotate encryption key'})`. Check that the announce sentence reads well.
  - Check that `App.ui.button` provides the `[data-confirm-title]` span `confirm` swaps. If not, use `confirm`'s `titleSelector` or build the label span; do not add a library option in this leg.
  - **DD8-12:** the in-flight state must not drop focus. Use `aria-disabled` plus ignoring clicks while busy, or a busy mechanism that keeps the element focusable. Test that `document.activeElement` is the button after success, staged and error.
- **DD8-10's test:** two rotations mocked in sequence (promoted, then staged within 3 s); the warning is still present after 3.5 s; the success timer is cleared at the start of the next attempt and on page teardown.
- **The pins to retarget (DD11)** in `test_flow_admin_rotate_flash.py`:
  - "Confirm Rotate?" → "Rotate key?";
  - "Rotate Encryption Key" → "Rotate encryption key";
  - "…rotated successfully" → "Key rotated.";
  - `.admin-system-flash` with `success`/`warning` classes → `rotate-result` with `data-state`;
  - its docstring.

  The lapse tests (`confirm-lapsed`, `confirm-delete`) pass unchanged. The status-route tests go in a new `tests/test_encryption_status.py` with the credential helper (the rotate route's tests are at `test_provider_api.py:586-615`).
- **`SECURITY-MODEL.md`** (it lists the rotate route at about `:859`): one sentence for the status route (read-only, behind the credential gate; a timestamp, a count and a pending flag; no secret material). The same in CLAUDE.md's route line.
- **The facts** refresh on page entry and after a rotation. "Last rotated" goes through `App.time.formatDate` and `formatClock`, with the ISO value in `title` and `data-rotated-at`. A failed status GET shows the facts as unavailable through `status`, and never blocks the rotate button.
- **Testids:** `rotate-result`, `encryption-facts`, `encryption-last-rotated`, `encryption-credential-count`.

Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
