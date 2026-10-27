# Leg: sign-in-and-list-delete

**Status**: completed
**Flight**: [Chats, and closing every count to zero](../flight.md)

## Objective
Finish the chat area's remaining hand-built controls outside the transcript:
- **Chat sign-in:**
  - the "Log in" button becomes a library primary button reading "Sign in to {server}", under the attribution "Sign-in needed" (A3);
  - the consent block uses `App.ui.consentLink` directly;
  - a failed `/api/oauth/start` resets the sign-in group (squawk 0215, DD11 9).
- **The Chats list:**
  - the platform badge shows the platform's display name, "Discord" not `discord` (A16; moved here from 05c at Architect cycle 2, because the badge is built in `chat/chats-list.js:120`);
  - the per-row MutationObserver goes, replaced by `App.ui.confirm`'s `onArmChange`;
  - the `App.confirmDelete` alias call becomes `App.ui.confirm`;
  - a delete confirmed while the socket is down reverts the arm and says why (DD11 6).

When the leg ends, the chat area has no ownership-allowance row outside the transcript's.

## Context
- **Flight decisions:** DD6 (the remaining chat JS rows), DD7 (A3; ledger rows 3, 34 and 35), DD11 (6 and 9), DD13 and DD15 (re-author `start-a-chat` step 14).
- **`js/areas/chat/sign-in.js`** (334 lines, from leg 02):
  - **The flows:** `loginFlows` per (session, source); `startLoginFlow` (`:100-150`) POSTs `/api/oauth/start`, and on failure `abandon()` (`:127-131`) deletes the flow and closes the popup **without resetting the group** (squawk 0215). `resetLoginGroups(sourceId)` (`:153-165`) removes the `.consent-link` block and shows "Log in" again; it is used for `auth_failed`.
  - **`renderLoginRequiredButton`** (`:174-250`): the attribution `'Authorization required to continue.'` (`:194`), then a hand-built `btn.className = 'btn-filled-primary login-required-btn'` (`:199`) reading `'Log in to ' + label` (`:208`). The link block comes from `App.consentLink.build(…)` (`:222`), and `App.consentLink.focusTarget` (`:245`) handles the focus hand-off.
  - `App.consentLink.isSafeUrl` is called in `startLoginFlow` (`:109`) and `onAuthRequired` (`:281`).
  - **The ownership rows** (from leg 02's `MOVES`, `retire_by` 05b): `api:App.consentLink.` ×4, `consent-link` ×1, `btn-filled-primary` ×1.
  - `tests/test_consent_link_static.py:47-49` counts `isSafeUrl(` ≥ 2 and `consentSafe` ≥ 3 in `sign-in.js`. The `App.ui.consentLink.isSafeUrl(` spelling still contains `isSafeUrl(`, so the counts hold.
- **The Chats list delete** (`chat.js:105-130`, construction):
  - a MutationObserver per row (`li._armLabelObs`) swaps the action's `aria-label` between `li._armIdle` ("Delete chat: {title}") and "Confirm delete: {title}" as `.confirm-delete` comes and goes;
  - `App.confirmDelete(li, fn)`'s commit sends `delete_session` **only if** `ctx.socket.socketOpen()`;
  - with the socket closed nothing is sent, and the row stays armed (`App.ui.confirm` clears its timer on commit but does not revert).
  - **The rows:** `api:App.confirmDelete(` ×1 and `confirm-delete` ×2 in `js/areas/chat.js`.
- **`App.ui.confirm`'s `onArmChange(armed)`** (leg 03c) fires `true` on arm and `false` on revert, lapse and commit.
- **The "Log in" wording elsewhere** (grep):
  - tests: `tests/browser/test_oauth_modal_flow.py` (5 uses), `tests/test_mcp_oauth_integration.py`, `tests/test_mcp_oauth_errors.py` (check whether these are server-side strings or the chat's);
  - docs: CLAUDE.md ("Honest sign-in": "Log in" in chat) and `the_one/agents.md`;
  - `docs/releases/v0.11.8.md` is a release record and stays as written.

  The MCP editor and the Library already say "Sign in" and "Sign-in needed" (`mcp-oauth-consent.js:178`, `mcp-connection-status.js:410`, `store.js:211`).
- **Behavior spec:** `tests/behavior/start-a-chat.md` step 14 arms and confirms `chat-row-delete`. DD11 6 adds an offline branch, so check whether its wording names the armed label.

## Inputs
- Leg 05a landed. The composer is on `App.ui.composer`, and `sign-in.js` hands focus through the composer handle.

## Outputs
- **A3:**
  - the attribution reads "Sign-in needed";
  - the button is `App.ui.button({variant: 'primary', label: 'Sign in to ' + label, className: 'login-required-btn', testid: …})`, keeping today's testid if it has one, or the class hook the tests use;
  - `login-required-btn` stays an area hook;
  - the "Log in" strings in chat, its tests and the docs that describe chat become "Sign in". Server-side messages are left alone unless they name the chat's button.
- **Squawk 0215:** `abandon()` calls `resetLoginGroups(sourceId)` after deleting the flow, so a block rendered before the POST failed is removed and "Sign in to {server}" shows again. The squawk records its corrective action and verification, and stays `in-progress` (it closes at the flight's commit).
- **The consent link:** the four `App.consentLink.*` calls become `App.ui.consentLink.*`. The `.consent-link` query in `resetLoginGroups` is replaced by a reference kept on the group (for example `group._consentBlock`, or a `WeakMap` from group to block) or by the consent link's own handle, if `build` returns one. The three sign-in ownership rows and their `MOVES` entries are deleted.
- **The Chats list delete:**
  - `App.confirmDelete(li, fn)` becomes `App.ui.confirm(li, fn, {onArmChange: function (armed) {…}})`, which sets the action's `aria-label` from `li._armIdle` / `li._armTitle` (or plain closure variables);
  - the MutationObserver is deleted, and no `.confirm-delete` class is read in `chat.js`;
  - its two ownership rows go.
- **DD11 6:** the commit callback checks `ctx.socket.socketOpen()`. When the socket is closed:
  - it calls the `revert` that `App.ui.confirm` passes, so the row is no longer armed and `onArmChange(false)` restores the label;
  - it shows `App.ui.flash("Not connected, so the chat wasn't deleted. Try again in a moment.", {error: true})`;
  - nothing is sent.
- **The allowance:** after this leg the chat area holds only the transcript's remaining rows, if any. Leg 02's `MOVES` entries for sign-in are gone, and `TOTAL_USES` is lowered.
- **Behavior spec:** `start-a-chat.md` step 14 is re-read and re-authored only if its wording changes.
- **Docs:** CLAUDE.md "Honest sign-in" ("Log in" becomes "Sign in"), `the_one/agents.md`'s chat sign-in and Chats list notes (the observer is gone, `onArmChange`, the offline delete).
- **A16:** `chats-list.js:120` (`item.badges = [String(row.platform)]`) maps the slug through one display-name table (for example `{discord: 'Discord', telegram: 'Telegram', slack: 'Slack', stub: 'Stub'}`, unknown slugs title-cased). A test asserts a Discord session's row badge reads "Discord".
- **Ledger rows 3, 16, 34 and 35** confirmed in the flight log.

## Acceptance Criteria
- [ ] **New tests, failing first where marked:**
  - **squawk 0215** — **failing today:** with a consent frame shown for a flow this window started, stub `POST /api/oauth/start` to 500; the block is gone and "Sign in to {server}" is visible;
  - **DD11 6** — **failing today:** with the socket closed (suppress the reconnect), click `chat-row-delete` twice; the row is not armed, the error toast reads the sentence above, and no `delete_session` frame was sent;
  - **onArmChange:** arming a row sets the action's name to "Confirm delete: {title}", and a lapse restores "Delete chat: {title}" (the existing A1 test passes unchanged).
- [ ] **A3:** the chat sign-in group reads "Sign-in needed" and "Sign in to {server}", is a library primary button, and keeps its keyboard-to-link focus hand-off. `test_oauth_modal_flow.py` passes with only its strings retargeted.
- [ ] `git grep -n "App.consentLink\.\|App.confirmDelete\|btn-filled-primary\|MutationObserver" -- the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/js/areas/chat/` finds nothing.
- [ ] **The allowance:** `tests/test_ui_ownership.py` passes with the sign-in rows, the `App.confirmDelete(` and `confirm-delete` rows and their `MOVES` entries gone. `tests/test_consent_link_static.py` passes.
- [ ] **Static guards:** `tests/test_ui_guards.py`, `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py` pass.
- [ ] **Lanes:** `chats`, `chats-transcript` and `shared` (`test_oauth_modal_flow.py`, `test_flow_oauth_callback_cross_site.py`) pass, as do the unit tests that touch sign-in strings.
- [ ] `make test-unit` passes after the browser runs. `ruff` is clean.

## Verification Steps
1. `.venv/bin/python -m pytest tests/test_ui_ownership.py tests/test_consent_link_static.py tests/test_ui_guards.py -q -x --timeout 120`.
2. `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/browser/test_oauth_modal_flow.py -m browser -x`, then `--lane chats` and `--lane shared`.
3. `git grep` as in the criteria.
4. `make test-unit`; `ruff check`; `ruff format --check`.

## Implementation Guidance
1. **The failing-first tests** (0215, DD11 6).
2. **0215:** `abandon()` resets the group.
3. **A3 and the consent link:** the library button, `App.ui.consentLink`, the block reference instead of the class query; the test strings.
4. **The Chats list delete:** `App.ui.confirm` with `onArmChange`, the observer deleted, and DD11 6's offline revert.
5. **The allowance, the spec re-read, docs,** then the lanes and `make test-unit`.

## Edge Cases
- **The focus hand-off on Sign in:** today a keyboard "Log in" moves focus to the link once the block replaces the button (`App.consentLink.focusTarget`). Keep it with the library button.
- **The webview's null popup** (`App.desktop.isWebview()`): unchanged. Only the label and the button factory change.
- **An unsafe consent URL:** `isSafeUrl` still gates every show, open and navigate, with the same counts.
- **A replayed `auth_required` after a failed start** shows "Sign in" once, never twice beside a stale block.
- **The offline delete's toast** must not appear for an online delete. The socket check is at commit time, not arm time.
- **A row re-rendered while armed** (`listPane` keeps the armed `<li>`): `onArmChange` still fires on its lapse.

## Files Affected
- `the_one/interfaces/web/static/js/areas/chat/sign-in.js`, `js/areas/chat.js`.
- `tests/browser/test_oauth_modal_flow.py`, the new chat tests (`chats` or `chats-transcript`), possibly `tests/test_mcp_oauth_*.py` (strings only, if they assert the chat's button).
- `tests/_ui_ownership_allowance.py`, CLAUDE.md, `the_one/agents.md`, `tests/behavior/start-a-chat.md` (if needed), `squawks/0215-chat-stale-sign-in-link-after-failed-oauth-start.md`, the flight log.

## Citation Audit
- `sign-in.js:100-150`, `:127-131`, `:153-165`, `:174-250` (`:194`, `:199`, `:208`, `:222`, `:245`), `:281`. FD grep after B2 (2026-10-27).
- `chat.js:105-130`. FD read.
- `tests/test_consent_link_static.py:47-49`, from leg 02's re-anchoring (B1 review).
- **Leg 05a will shift `chat.js` lines.** Re-derive them before editing.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.

## Design Review Amendments (cycle 1, 2026-10-27; these take precedence)
- **A16:**
  - `tests/browser/test_flow_chat_list.py:212-215` asserts the Discord badge text `["discord"]`. It is **retargeted** to "Discord" (added to Files Affected and the AC).
  - The display-name table lives in one place in the chat area (for example `App.chat.platformName(slug)`, exported from `chats-list.js`), so any other chat surface that shows a platform reads the same table. Unknown slugs are title-cased (FD answer).
- **The delete label is derived from the row's title, never read back from the DOM.** A second click on an armed row runs `onDelete` again, by which point the button's `aria-label` already reads "Confirm delete: X". So:
  - the idle label is `'Delete chat: ' + title`, with the title passed from `chats-list.js` (the row's `current`) into `onDelete`;
  - `onArmChange(armed)` sets `armed ? 'Confirm delete: ' + title : 'Delete chat: ' + title`;
  - the callback is idempotent, because commit fires `onArmChange(false)` and an offline `revert()` fires it again.
- **The sign-in button keeps its hooks:**
  - `App.ui.button` has no dataset option, so after construction `sign-in.js` keeps setting `btn.dataset.sourceId`, `toolCallId`, `resourceMetadataUrl` and `consentUrl`;
  - the `login-required-btn` class stays: `clearLoginRequiredButton` selects `.login-required-btn[data-source-id=…]`, and about 40 test uses rely on it;
  - **no new testid** (FD answer), so the testid registry is unchanged;
  - the group keeps direct references (`group._btn`, `group._consentBlock`), which remove both class queries in `resetLoginGroups`;
  - the `"<unknown>"` fallback label keeps its wording inside "Sign in to {label}" (FD answer).
- **The 0215 failing-first test:**
  - hold `POST /api/oauth/start` pending until the test has injected the consent frame, then fulfil it with 500. An immediate 500 runs `abandon()` before the block exists, and would pass today;
  - cover the network-error branch (`.catch`) too;
  - after `abandon()`, a replayed `auth_required` renders the button visible.
- **The bookkeeping, together:**
  - the three `sign-in.js` `OWNERSHIP_ALLOWANCE` rows and their three `MOVES` entries;
  - the `chat.js` rows (`api:App.confirmDelete(` ×1 and `confirm-delete` ×2: the `classList.contains` uses at about `:112` and `:115` both go with the observer);
  - `TOTAL_USES` keys `api:App.confirmDelete(`, `api:App.consentLink.`, `btn-filled-primary`, `confirm-delete` and `consent-link` deleted (or set to 0 if the test requires the key);
  - check whether `tests/test_ui_ownership.py` requires pruning stale `START_ROWS` entries.
  - The objective's "no ownership row outside the transcript's" holds only with 05a's `chip` removal done. `markdown.js`'s rows are not chat-area (leg 07).
- **The AC grep for `MutationObserver`** first checks for pre-existing observer uses in `areas/chat/` and excludes them by name.
- **Strings and docs:**
  - the `sign-in.js` comments that mention "Log in" (`:2`, `:77-79`, `:215`, `:273-275`, `:319`);
  - `the_one/agents.md:28` and the CLAUDE.md "Honest sign-in" paragraph ("Log in", `App.consentLink`);
  - `test_oauth_modal_flow.py`'s text assertions (`:127`, `:147`) and comment mentions (`:416`, `:428`, `:445`).
  - `tests/test_mcp_oauth_*.py` assert only server strings and are left alone. "Authorization required to continue." is in no test or doc.
- **`start-a-chat.md` step 14** names the row text "Confirm delete?", not the aria-label, so no re-author is needed.
- **CSS:** `chat.css`'s `.login-required-btn`, `-group` and `-attribution` rules stay valid (the classes are kept), and `App.ui.button` emits the same `btn-filled-primary` class, so there is no CSS change.
- **`consentSafe`** appears exactly 3 times, against the static test's `>= 3`, so no rename.
- **The offline-delete test** closes the socket through `page.evaluate` and stubs the reconnect for its duration. A second test asserts **no toast for an online delete**. The lapse step reuses `test_flow_chat_list.py:329-343`'s approach.

## Design Review
- **Developer design review, cycle 1 (Sonnet, 2026-10-27, read-only, against the landed leg 04): approve with changes.** Applied as the amendments above. FD answers: unknown slugs are title-cased; no new testid; the fallback label is unchanged.
- No second cycle (precision within the design).
