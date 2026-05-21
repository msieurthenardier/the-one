# Leg: invite-url-section

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Add an always-mounted Invite section on the Discord connector detail page (General tab, edit-mode only, between Test Connection and Danger Zone) that renders the computed invite URL when the doctor probe has surfaced an `application_id`, falls back to a hint pre-probe, recomputes the URL reactively on intent-checkbox change, and is fully Discord-shaped via the L3 form registry.

## Context

- **Why now**: F1 mission-criterion #1 names "invite-URL helpers" as part of the Discord-shaped surface. L4 landed the typed intents form; L5 layers the always-visible Invite section that consumes the probe's `application_id` + current intent state + a constant permission integer to produce the bot's OAuth2 invite URL.
- **Source of `application_id`**: the doctor probe's `application` check at `_discord.py:1089, 1124, 1301` (per the F1 flight spec citation; verified against current code by the L1 design-time audit). The probe's report carries `details.application_id` which the existing `renderTestConnectionBanner` (line 1411+) consumes. L5 extends the consumption path to also refresh the Invite section.
- **Ephemeral vs persisted application_id**: the `application_id` is not persisted in `account.config` or any DB column — it's surfaced only by an active probe. L5 chooses to keep it ephemeral (module-scope cache keyed on `account_id`, cleared on reload). Rationale: persisting requires a backend change that doesn't pull weight; the Create-and-Test flow already runs the probe automatically; the operator can re-run Test Connection any time to refresh.
- **Constant permission integer**: per F1 Design Decision in `flight.md` ("Required permissions integer"), the permission set required by M10 F8 is `Send Messages` (1 << 11 = 2048) + `Read Message History` (1 << 16 = 65536) + `View Channels` (1 << 10 = 1024) + `Use Application Commands` (1 << 31 = 2147483648). Total: `2147552768`. Document this as a constant in the L5 module with a code-comment naming each permission so a future flight extending bot capabilities can update it alongside.
- **OAuth2 scope**: `bot+applications.commands` (URL-encoded as `bot%20applications.commands`). The full invite URL shape is:
  ```
  https://discord.com/oauth2/authorize?client_id={application_id}&permissions={permissions_int}&scope=bot+applications.commands
  ```
- **What's NOT in scope**: persisting `application_id`; running the probe automatically on L5-mount (the existing Create-and-Test flow already does this for new accounts; existing edit-mode accounts require the operator to click Test Connection to populate). Per-intent dynamic permission integers (operator selecting fewer intents does NOT reduce the required permissions; intents and permissions are orthogonal Discord concepts per F1 Design Decision).
- **L4 dependency**: the invite-section needs to wire its recompute listener to the same intent checkboxes L4 rendered. Use the Discord registry entry's `wireEvents` hook to attach an additional listener that re-renders the invite URL on intent-checkbox change — OR add the listener directly inside the invite-section render (simpler).

### Design Decisions (L5-internal)

- **Section ownership lives in `connector-account-editor.js`, not in the Discord registry entry**: the Invite section is mounted into the General tab between Test Connection and Danger Zone — a substrate-level mount point. The Discord-shaped behavior (URL composition, intent-aware) is conditional on the connector type being `'discord'`. Two implementation paths:
  - Path A: substrate-level mount + `'discord'`-type-gated rendering inside `connector-account-editor.js` (small additive change to the editor file).
  - Path B: extend the L3 form registry with a NEW optional `renderInviteSection(account)` hook on entries; substrate calls it; Discord entry implements it (preserves the registry's "per-type knowledge stays in the entry" pattern).
  - **Chosen**: Path B — the registry's design pattern is to keep Discord-specific logic OUT of `connector-account-editor.js`. The new hook is OPTIONAL; entries without it (no future-type entries today) trigger no Invite section render. The substrate's edit-mode HTML assembly calls `entry.renderInviteSection?.(account)` at the right place.
- **Section is always-mounted in edit mode** when an entry provides `renderInviteSection`: rendering an empty `<section>` (no content) when the entry returns empty string is fine. The renderer itself produces the pre-probe hint vs post-probe URL distinction. Rationale: a stable mount point survives type changes (though Discord-type immutability post-create makes this academic) and matches the F1 design decision "always-mounted Invite section ... content varies by probe state."
- **`application_id` cache**: module-level `var _lastApplicationIdByAccount = {};` in `connector-account-editor.js` (or in the Discord registry entry — see below). Keyed on `account.id`. Populated by an extension to `renderTestConnectionBanner` (or by the probe callback). Cleared on editor unmount via `cleanupEditor` if such a hook exists; otherwise survives until reload. The Discord entry's `renderInviteSection(account)` reads `_lastApplicationIdByAccount[account.id]` to decide pre-vs-post-probe state.
- **Recompute on intent change**: the Invite section renders both a stable hostnames + a dynamic URL display. The intent-checkbox `change` listener (already wired in L4's `wireEvents` hook) ALSO triggers an invite-URL recompute. L5 extends the Discord entry's `wireEvents` to add the recompute listener — or wires it inline inside `renderInviteSection`'s mount hook (cleaner). Implementation: attach a single `change` listener at the registry-entry's `wireEvents` invocation that also fires `recomputeInviteUrl(container, account)` when any intent checkbox changes.
- **Reactive recompute is pure (no I/O)**: the URL composition is a pure string template; no debounce; rapid toggling is operationally fine.
- **Copy button**: clicking copies the URL to clipboard via `navigator.clipboard.writeText(url)`; on success a short "Copied" affordance fires (badge or icon swap). Reuse existing copy-button patterns if any exist in studio (search for `navigator.clipboard.writeText` in the static directory).
- **Recompute button**: an explicit "Recompute" button next to the URL display. Useful when the operator changes intents and wants to verify the URL refreshed (though the change-event already refreshes; the button is a manual fallback + visible affordance). Optional polish; can omit if scope tight.
- **Section structure**:
  ```html
  <section class="editor-section connector-invite-section" data-testid="connector-invite-section">
    <div class="section-title">Invite</div>
    <!-- Pre-probe state -->
    <p class="connector-invite-hint" data-testid="connector-invite-hint" hidden>
      Run Test Connection first to fetch your application ID.
    </p>
    <!-- Post-probe state -->
    <div class="connector-invite-url-wrap" data-testid="connector-invite-url-wrap" hidden>
      <code class="connector-invite-url" data-testid="connector-invite-url"></code>
      <button type="button" class="btn-outlined-primary connector-invite-copy-btn" data-testid="connector-invite-copy-btn">Copy</button>
      <button type="button" class="btn-outlined-primary connector-invite-recompute-btn" data-testid="connector-invite-recompute-btn">Recompute</button>
    </div>
  </section>
  ```
  Toggle between `.connector-invite-hint` and `.connector-invite-url-wrap` based on whether `_lastApplicationIdByAccount[account.id]` is set.
- **Permission integer constant**: define inside `connector-form-discord.js` as `var _DISCORD_INVITE_PERMISSIONS = (1 << 11) | (1 << 16) | (1 << 10) | (1 << 31);` with a code-comment naming each permission: Send Messages, Read Message History, View Channels, Use Application Commands.

## Inputs

Files that must exist:
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` (L3 + L4 substrate — extends `_validateEntry` for an OPTIONAL `renderInviteSection` field)
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` (L4 entry — extended with `renderInviteSection` + `_lastApplicationIdByAccount` storage)
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (mount point in edit-mode General tab between Test Connection and Danger Zone; `renderTestConnectionBanner` extension to capture `application_id`)
- `the_one/connectors/_discord.py` (read-only: confirms the probe's `details["application_id"]` shape — already covered by L4 design audit)
- `tests/browser/test_flow_studio_connector_discord_form.py` (extend with invite-section tests, OR new file `test_flow_studio_connector_invite_section.py`)
- `tests/browser/seeders.py` (already supports Discord shape from L4)

State that must be true:
- L1-L4 all landed
- Branch `flight/01-discord-connector-type-and-creation-form` checked out
- 2792 baseline passes

## Outputs

State changes after this leg:
- **Modified `connector-form-registry.js`**: `_validateEntry` accepts `renderInviteSection` as OPTIONAL function (same pattern as `snapshot`, `wireEvents`).
- **Modified `connector-form-discord.js`** (~80-150 LOC added):
  - Module-level `_lastApplicationIdByAccount = {}` storage.
  - Module-level `_DISCORD_INVITE_PERMISSIONS` constant.
  - Module-level `_computeInviteUrl(applicationId)` function — pure; returns the full OAuth2 URL.
  - Entry's `renderInviteSection(account)` produces the section HTML.
  - Entry's `wireEvents` extended to wire: (a) intent-checkbox change → re-render invite URL (calls a helper `_updateInviteUrlDisplay(container, account)`); (b) Copy button → `navigator.clipboard.writeText(url)`; (c) Recompute button → manual refresh.
  - Public method on the module-namespace (e.g. `window.App.studio.connectorFormDiscord = { setApplicationId: function(accountId, appId) {...} }`) that `connector-account-editor.js` calls from `renderTestConnectionBanner` to populate the cache.
- **Modified `connector-account-editor.js`**:
  - Edit-mode HTML assembly (around line 430) inserts a new section's HTML between `testConnectionHtml` and `dangerZoneHtml`. The HTML is registry-mediated: `var inviteHtml = !isCreate && entry && entry.renderInviteSection ? entry.renderInviteSection(account) : '';` then `html += inviteHtml;`.
  - `renderTestConnectionBanner` (line 1411+) extended: after rendering the banner, if `report.details.application_id` is present, call into the Discord registry entry's namespace method to cache the ID and re-render the invite section (`window.App.studio.connectorFormDiscord.setApplicationId(account.id, report.details.application_id)` and trigger an invite-section re-render).
- **NEW or extended tests** (`tests/browser/test_flow_studio_connector_invite_section.py` OR additions to `test_flow_studio_connector_discord_form.py`):
  - Pre-probe state: invite-hint visible, invite-url hidden.
  - Post-probe state: invite-url visible with correct URL composition (assert URL substring contains `client_id={application_id}` and `permissions=2147552768`).
  - Intent change recomputes URL on the fly (toggle a checkbox; verify URL DOM didn't change because permissions are intent-independent — the URL stays stable; this is actually a *negative* test that intents do NOT affect the permission integer per F1 Design Decision).
  - Copy button copies to clipboard (Playwright clipboard read).
  - Recompute button refreshes the URL display.
  - `'stub'`-type account: no Invite section renders.
  - ~80-150 LOC of new test code.

## Acceptance Criteria

- [ ] `connector-form-registry.js:_validateEntry` accepts `renderInviteSection` as OPTIONAL (function if present; throws TypeError if defined but not a function; absent → no error). The 4 required + 3 optional contract holds.
- [ ] `connector-form-discord.js` exposes `window.App.studio.connectorFormDiscord = { setApplicationId(accountId, appId) }` (or equivalent — the L4 entry's module-namespace export). The function caches the application_id and re-renders the Invite section if it's currently mounted in the DOM.
- [ ] `connector-form-discord.js` defines `_DISCORD_INVITE_PERMISSIONS = (1 << 11) | (1 << 16) | (1 << 10) | (1 << 31)` (= 2147552768) with a comment naming each permission (Send Messages, Read Message History, View Channels, Use Application Commands).
- [ ] `connector-form-discord.js` exposes the Discord entry's `renderInviteSection(account)` that returns HTML matching the Section Structure in Design Decisions §8.
- [ ] `connector-account-editor.js` edit-mode HTML assembly: invite section HTML is inserted BETWEEN `testConnectionHtml` and `dangerZoneHtml`. The mount is registry-mediated — falls back to empty string when no entry provides `renderInviteSection` (so `'stub'`-type accounts get NO invite section).
- [ ] `connector-account-editor.js:renderTestConnectionBanner` (line 1411+) extended: when `report.details.application_id` is present AND the active connector type has a `renderInviteSection` hook, call the Discord namespace's `setApplicationId(account.id, application_id)` to cache. The banner-render is unchanged otherwise.
- [ ] Discord entry's `renderInviteSection(account)`:
  - When `_lastApplicationIdByAccount[account.id]` is undefined → invite-hint visible, invite-url-wrap hidden.
  - When set → invite-url-wrap visible with `<code>` containing the computed URL, invite-hint hidden.
- [ ] Discord entry's `wireEvents(container, checkDirty)` (extended from L4):
  - Adds `change` listener to each intent checkbox that calls a private `_updateInviteUrlDisplay(container, account)`. The display update is a string-template recompute — does NOT involve `checkDirty` (the URL display is not dirty state).
  - Copy button → `navigator.clipboard.writeText(urlText)` + ephemeral "Copied" feedback (badge swap or class toggle for ~1.5s).
  - Recompute button → `_updateInviteUrlDisplay(container, account)`.
- [ ] `_computeInviteUrl(applicationId)` is a pure function: returns `"https://discord.com/oauth2/authorize?client_id=" + applicationId + "&permissions=2147552768&scope=bot+applications.commands"`. Verifiable by inspection.
- [ ] No backend changes, no DB changes, no API changes. `git diff --name-only` shows only frontend JS files + new test file + leg/flight-log artifacts.
- [ ] Existing browser tests pass UNMODIFIED. The new invite-section tests pass. Full suite at or above L4's 2792 baseline.

## Implementation Guidance

1. **Read L4's `connector-form-discord.js`** to understand the module's IIFE shape, entry construction, and the `wireEvents` hook implementation.
2. **Extend `_validateEntry`** in `connector-form-registry.js` to accept `renderInviteSection` per the optional-function pattern (mirror `snapshot` and `wireEvents`).
3. **Add module-scope storage** in `connector-form-discord.js`:
   ```javascript
   var _lastApplicationIdByAccount = {};
   var _DISCORD_INVITE_PERMISSIONS = (1 << 11) | (1 << 16) | (1 << 10) | (1 << 31);
   // 2048 (Send Messages) + 65536 (Read Message History)
   //   + 1024 (View Channels) + 2147483648 (Use Application Commands)
   // = 2147552768. Intent toggles do NOT affect this integer; intents
   // and permissions are orthogonal Discord concepts.

   function _computeInviteUrl(applicationId) {
     return 'https://discord.com/oauth2/authorize?client_id=' + applicationId +
            '&permissions=' + _DISCORD_INVITE_PERMISSIONS +
            '&scope=bot+applications.commands';
   }
   ```
4. **Define `entry.renderInviteSection(account)`**: returns the HTML per the Section Structure. The `hidden` attribute toggling between hint vs url-wrap is initial-state only; runtime toggling happens in `_updateInviteUrlDisplay`. Initial state derives from `_lastApplicationIdByAccount[account.id]`:
   ```javascript
   function renderInviteSection(account) {
     var appId = _lastApplicationIdByAccount[account.id];
     var hintHidden = appId ? 'hidden' : '';
     var urlHidden = appId ? '' : 'hidden';
     var url = appId ? _computeInviteUrl(appId) : '';
     return '<section class="editor-section connector-invite-section" data-testid="connector-invite-section">' +
            '<div class="section-title">Invite</div>' +
            '<p class="connector-invite-hint" data-testid="connector-invite-hint" ' + hintHidden + '>' +
            'Run Test Connection first to fetch your application ID.</p>' +
            '<div class="connector-invite-url-wrap" data-testid="connector-invite-url-wrap" ' + urlHidden + '>' +
            '<code class="connector-invite-url" data-testid="connector-invite-url">' + url + '</code>' +
            '<button type="button" class="btn-outlined-primary connector-invite-copy-btn" data-testid="connector-invite-copy-btn">Copy</button>' +
            '<button type="button" class="btn-outlined-primary connector-invite-recompute-btn" data-testid="connector-invite-recompute-btn">Recompute</button>' +
            '</div></section>';
   }
   ```
5. **Define `_updateInviteUrlDisplay(container, account)`**: queries the DOM for the hint + url-wrap elements; toggles hidden; updates the `<code>`'s textContent with the current URL. Pure DOM mutation; no I/O.
6. **Extend `entry.wireEvents`**: after the existing intent-checkbox listeners, add `_updateInviteUrlDisplay(container, account)` to each. Also wire the Copy + Recompute buttons:
   ```javascript
   var copyBtn = container.querySelector('[data-testid="connector-invite-copy-btn"]');
   if (copyBtn) {
     copyBtn.addEventListener('click', function () {
       var urlEl = container.querySelector('[data-testid="connector-invite-url"]');
       if (urlEl && navigator.clipboard) {
         navigator.clipboard.writeText(urlEl.textContent || '').then(function () {
           copyBtn.textContent = 'Copied';
           setTimeout(function () { copyBtn.textContent = 'Copy'; }, 1500);
         });
       }
     });
   }
   var recomputeBtn = container.querySelector('[data-testid="connector-invite-recompute-btn"]');
   if (recomputeBtn) {
     recomputeBtn.addEventListener('click', function () {
       _updateInviteUrlDisplay(container, account);
     });
   }
   ```
7. **Expose the module namespace** at the bottom of `connector-form-discord.js`:
   ```javascript
   window.App.studio.connectorFormDiscord = {
     setApplicationId: function (accountId, appId) {
       _lastApplicationIdByAccount[accountId] = appId;
       // If the invite-section is mounted in the current DOM, re-render it.
       var inviteSection = document.querySelector('[data-testid="connector-invite-section"]');
       if (inviteSection) {
         // Use parent container to mutate state; query parents up to the
         // editor mount and trigger _updateInviteUrlDisplay.
         var container = inviteSection.closest('.connector-account-editor') ||
                         inviteSection.parentElement;
         if (container) {
           _updateInviteUrlDisplay(container, { id: accountId });
         }
       }
     }
   };
   ```
   (The implementer should verify the editor container's class name — read the connector-account-editor's mount point. If the class is different, use the correct selector.)

8. **Extend the edit-mode HTML assembly** in `connector-account-editor.js` (around lines 425-431 — the General tab assembly). Add a new `inviteHtml` variable computed from the registry consult, inserted between `testConnectionHtml` and `dangerZoneHtml`:
   ```javascript
   // L5: Invite section between Test Connection and Danger Zone (edit-mode only).
   var inviteHtml = '';
   if (!isCreate) {
     var inviteRegistry = (window.App && window.App.studio && window.App.studio.connectorFormRegistry) || null;
     var inviteEntry = (inviteRegistry && account && account.type) ? inviteRegistry.get(account.type) : undefined;
     if (inviteEntry && typeof inviteEntry.renderInviteSection === 'function') {
       inviteHtml = inviteEntry.renderInviteSection(account);
     }
   }
   // ... then in the General tab HTML assembly:
   html += testConnectionHtml;
   html += inviteHtml;
   html += dangerZoneHtml;
   ```

9. **Extend `renderTestConnectionBanner`** (line 1411+): change its signature from `(container, report)` to `(container, report, accountId)` and thread `accountId` through ALL call sites:
   - `handleTestConnection` at line 1359+ already has `accountId` in scope as a parameter — pass it on both the success path (around line 1395) and the synthetic-error path (around line 1400).
   - The post-mount `_pendingProbeReport` consumer at line 468-471: needs `account.id` from the editor's mount scope. Verify the path: `account` is in scope at line 467; pass `account.id`.
   - **Reason for the signature change**: there is NO `data-account-id` attribute in the editor DOM today. Pulling from a closure that captures `account.id` is the only correct source.
   - After the existing banner-render code, if the report carries `details.application_id` AND the Discord namespace is available, call `setApplicationId`:
     ```javascript
     var applicationId = report && report.details && report.details.application_id;
     if (applicationId && accountId && window.App && window.App.studio && window.App.studio.connectorFormDiscord) {
       window.App.studio.connectorFormDiscord.setApplicationId(accountId, applicationId);
     }
     ```
   - **Verify** at design time that `renderTestConnectionBanner` is not called from anywhere else (`grep -n "renderTestConnectionBanner(" the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` returned 3 call sites at design audit: line 471, 1395, 1400). The signature change touches all three.

10. **Add browser tests** in `tests/browser/test_flow_studio_connector_invite_section.py` (NEW FILE). Key scenarios:
    - Pre-probe: open an existing Discord account (with no probe report in-session) → invite-hint visible, invite-url-wrap hidden.
    - Post-probe: trigger test connection → wait for the probe response → verify invite-url-wrap visible with URL containing `client_id=` and the literal `permissions=2147552768` substring.
    - **Intent-toggle stability test (sharper assertion)**: read the URL string before toggle; toggle one intent checkbox; wait for the change-event tick; read URL again; assert (a) the strings are equal AND (b) the literal `permissions=2147552768` substring is still present. This catches both "URL got rewritten" and "future bug swapped the constant."
    - Stub-type account: no invite-section in the DOM (assert `data-testid="connector-invite-section"` selector returns no element).
    - Copy button: click, then `page.evaluate("navigator.clipboard.readText()")` returns the URL.
    - **Playwright clipboard setup**: the default `page` fixture in `tests/browser/conftest.py` does NOT grant clipboard permissions. Use the `test_markdown.py:131-137` precedent — define a local fixture in this test file that builds a context with `permissions=["clipboard-read", "clipboard-write"]` for the app's origin:
      ```python
      @pytest.fixture
      def clipboard_page(browser, app_url):
          context = browser.new_context(
              color_scheme="no-preference",
              permissions=["clipboard-read", "clipboard-write"],
              base_url=app_url,
          )
          page = context.new_page()
          yield page
          context.close()
      ```
      Read `test_markdown.py` to confirm the exact fixture shape before mirroring.

11. **Run regression tests** in order:
    - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_discord_form.py`
    - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_invite_section.py`
    - Existing 4 connector-account-editor tests pass UNMODIFIED.
    - Full suite at or above L4's 2792 baseline.

## Edge Cases

- **Probe never run**: `_lastApplicationIdByAccount[account.id]` undefined → invite-hint shown. Operator sees the hint, runs Test Connection, the banner-render path populates the cache, and the invite section re-renders with the URL. Acceptable UX.
- **Probe ran in a prior session (no persistence)**: cache is empty on fresh page load → hint shown again until the operator clicks Test Connection. Per Design Decisions §3 (ephemeral cache).
- **`'stub'`-type account**: registry entry is undefined → no invite section renders. Existing tests against `'stub'` continue to pass UNMODIFIED.
- **Probe report has no `application_id`** (probe failed at token-valid step before reaching the application probe): `report.details.application_id` is null/undefined; the cache is NOT updated; the hint stays visible. Acceptable.
- **Two Discord accounts open in different tabs**: each has its own `_lastApplicationIdByAccount` in its own page's JS context — no cross-contamination. The module-scope cache is per-page.
- **`document.querySelector('[data-testid="connector-invite-section"]')` first-match limitation**: the `setApplicationId` re-render path uses `document.querySelector`, which returns the FIRST matching element. If the UI ever mounts two Discord connector editors simultaneously (split-pane future, dev hot-reload edge case), the re-render targets the wrong one. Today the editor mounts one-at-a-time so this is a non-issue; flagged as a documented limit, not a bug.
- **Clipboard write fails** (browser permission denied, insecure context): the `.then` never fires; the button stays "Copy". No error feedback. Acceptable for an MVP; can polish later.
- **Application_id changes mid-session** (operator regenerated bot at Discord side): a fresh Test Connection click updates the cache; the URL re-renders. The operator must re-invite the bot to servers with the new URL.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` — additive optional `renderInviteSection` in `_validateEntry`.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — +80-150 LOC: cache, constants, `_computeInviteUrl`, `renderInviteSection`, `_updateInviteUrlDisplay`, `wireEvents` extension, namespace export.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — edit-mode HTML assembly extended; `renderTestConnectionBanner` extended to populate the Discord cache.
- `tests/browser/test_flow_studio_connector_invite_section.py` — NEW or extension to existing L4 file; ~80-150 LOC.
- Leg/flight-log artifacts.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Existing browser tests pass UNMODIFIED
- [ ] New invite-section tests pass
- [ ] Full suite at or above L4's 2792 baseline
- [ ] No backend / API / DB changes
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L4):

- `connector-account-editor.js:renderTestConnectionBanner` — verified at line 1411; consumes `report.details` directly.
- `connector-account-editor.js` Test Connection mount — verified at lines 362-378; lives in the General tab between Attached Agents and Danger Zone.
- `connector-account-editor.js` General tab HTML assembly — verified at lines 422-432; current order: connection, credentials, pairing, attached-agents, test-connection, danger-zone. Insertion point for invite is between test-connection (line 430) and danger-zone (line 431).
- `_discord.py:DiscordPlugin.doctor` — verified: `details["application_id"]` is populated in the doctor report at the application probe success path.
- L4 `connector-form-discord.js` — exists; module-level IIFE; ~329 LOC at L4 ship.
- L3 `connector-form-registry.js:_validateEntry` — verified: accepts `snapshot` and `wireEvents` as OPTIONAL; same shape applies to the new `renderInviteSection`.

Six citation clusters verified live. No drift.
