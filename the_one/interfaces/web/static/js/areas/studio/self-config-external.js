// App.studio.selfConfigExternal — the Self-configuration tab's External access
// section: grant, list, rotate and revoke external-client credentials, and the
// copy-once token reveal (M31 F2 L10b: split out of self-configuration-tab.js, a pure
// restructure). `build(ctx)` appends the section to `ctx.panel` and publishes
// `ctx.setExternalStatus`, `ctx.renderExternalState` and `ctx.hideTokenReveal`; it reads
// `ctx.agent` at call time. Mint, rotate and revoke refresh only their own list; none
// reaches `onSelfConfigChanged`.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  function build(ctx) {
    var panel = ctx.panel;
    var callbacks = ctx.callbacks;
    var formatRevisionTimestamp = window.App.studio.selfConfigHistory.formatRevisionTimestamp;

    // ── M21 F03 L03 — External access ───────────────────────────────────
    // Grant / list / revoke / rotate external-client credentials over
    // Leg 1's endpoints. Unlike the other actions on this tab, these do
    // NOT route through `_refreshAgentAfterSelfConfigurationChange`: mint
    // and rotate return the full `ext_<id>.<secret>` token exactly once,
    // and an editor refresh must not tear the copy-once reveal down
    // before the operator copies it. So each action re-fetches ONLY the
    // list locally (`refreshExternalList`) and the reveal persists until an
    // explicit dismiss, a disable (the credentials were revoked), a new
    // editor identity or `destroy` (the token is never persisted anywhere,
    // never `localStorage`/`sessionStorage`). Since M31 F2 L10a a same-identity
    // Save no longer clears it. The `announce`/`actionStatus` focus move above
    // does not apply here; this section announces through its own
    // `role="status" aria-live="polite"` line — the same live-region idiom
    // the tab's status/count lines already use — and moves focus itself.
    var externalSectionCtl = App.ui.section({
      title: 'External access',
      titleTag: 'h2',
      className: 'self-configuration-external-section'
    });
    var externalSection = externalSectionCtl.body;

    var externalDesc = document.createElement('p');
    externalDesc.className = 'self-configuration-description';
    externalDesc.textContent = 'Grant an external client — a tool outside the platform, or ' +
      'another agent inside it — a credential scoped to just this agent’s self-configuration ' +
      'surface. Each grant’s token is shown once, at creation. Revoke or rotate a grant at any ' +
      'time; the change takes effect immediately, without a restart.';
    externalSection.appendChild(externalDesc);

    // Announcement + status live region for grant/revoke/rotate (see the
    // rationale in the section comment above): an App.ui.status line without an LED.
    var externalStatusCtl = App.ui.status({
      state: 'idle', text: 'Loading…', led: false, testid: 'self-configuration-external-status'
    });
    var externalStatus = externalStatusCtl.el;
    externalStatus.classList.add('self-configuration-status', 'self-configuration-external-status');
    externalSection.appendChild(externalStatus);

    function setExternalStatus(text) {
      externalStatusCtl.set('idle', text);
    }

    // The copy control's announcement (its done text): its own
    // visually hidden live node, so the status line above is never replaced by it.
    var copyLive = document.createElement('p');
    copyLive.className = 'visually-hidden';
    copyLive.setAttribute('role', 'status');
    externalSection.appendChild(copyLive);

    // Section-level error (survives a list re-fetch — a per-row error would
    // vanish when the list rebuilds after a failed revoke/rotate).
    var externalErrorCtl = App.ui.status({
      state: 'danger', led: false, role: 'alert', testid: 'self-configuration-external-error'
    });
    var externalError = externalErrorCtl.el;
    externalError.classList.add('self-configuration-error');
    externalError.hidden = true;
    externalSection.appendChild(externalError);

    // ── grant control ──
    var grantRow = document.createElement('div');
    grantRow.className = 'self-configuration-external-grant';

    var grantLabelEl = document.createElement('label');
    grantLabelEl.className = 'self-configuration-external-grant-label-text';
    grantLabelEl.setAttribute('for', 'self-configuration-external-grant-label-input');
    grantLabelEl.textContent = 'Label';
    grantRow.appendChild(grantLabelEl);

    // Inert until the surface status resolves (parity with the enable toggle);
    // `renderExternalState` sets the real state.
    var grantInput = App.ui.textInput({
      id: 'self-configuration-external-grant-label-input',
      placeholder: 'e.g. staging-deploy-bot',
      disabled: true,
      minWidth: 160,
      testid: 'self-configuration-external-grant-label'
    });
    grantInput.setAttribute('maxlength', '200');
    grantRow.appendChild(grantInput);

    var grantBtn = App.ui.button({
      variant: 'primary',
      label: 'Grant access',
      disabled: true,
      className: 'self-configuration-external-grant-btn',
      testid: 'self-configuration-external-grant-btn'
    });
    grantRow.appendChild(grantBtn);

    externalSection.appendChild(grantRow);

    // Disabled-surface hint (AC1) — shown when self-configuration is off.
    var grantHint = document.createElement('p');
    grantHint.className = 'self-configuration-description self-configuration-external-grant-hint';
    grantHint.setAttribute('data-testid', 'self-configuration-external-grant-hint');
    grantHint.textContent = 'Enable self-configuration above to grant external access.';
    grantHint.hidden = true;
    externalSection.appendChild(grantHint);

    // ── copy-once secret reveal (hidden until a mint/rotate returns) ──
    var tokenWarning = document.createElement('p');
    tokenWarning.className = 'self-configuration-external-token-warning';
    // Programmatic association target (WCAG 1.3.1): the copy button and token
    // input point their aria-describedby at this id so the full shown-once
    // caution is read when focus lands on either control.
    tokenWarning.id = 'self-configuration-external-token-warning';
    tokenWarning.textContent = 'Copy this token now — it is shown only once and cannot be ' +
      'retrieved again. If you lose it, revoke this grant and create a new one.';

    // The token field is created with NO value and filled by `setValue` on a reveal
    // (a property write, never an attribute), and it carries no dataset: the
    // token must never reach an attribute, and the form sweep must not see it.
    var tokenField = App.ui.copyField({
      label: 'External access token (shown once)',
      testid: 'self-configuration-external-token-value',
      copyTestid: 'self-configuration-external-token-copy-btn',
      inputClass: 'self-configuration-external-token-value',
      rowClass: 'self-configuration-external-token-row',
      liveEl: copyLive,
      doneText: 'Token copied to the clipboard.'
    });
    tokenField.input.setAttribute('aria-describedby', 'self-configuration-external-token-warning');
    tokenField.button.setAttribute('aria-describedby', 'self-configuration-external-token-warning');

    var tokenUrl = document.createElement('p');
    tokenUrl.className = 'self-configuration-external-token-url';
    var tokenUrlLabel = document.createElement('span');
    tokenUrlLabel.className = 'self-configuration-external-token-url-label';
    tokenUrlLabel.textContent = 'Surface URL: ';
    var tokenUrlValue = document.createElement('span');
    tokenUrlValue.setAttribute('data-testid', 'self-configuration-external-token-url');
    tokenUrl.appendChild(tokenUrlLabel);
    tokenUrl.appendChild(tokenUrlValue);

    var tokenDismissBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      label: 'Dismiss',
      className: 'self-configuration-external-token-dismiss-btn',
      testid: 'self-configuration-external-token-dismiss-btn'
    });

    // Built with children and never set()/setChildren() afterwards (that would wipe the
    // token field); hideTokenReveal hides it and empties the field.
    var tokenRevealBanner = App.ui.banner({
      tone: 'warning', role: 'status', hidden: true,
      className: 'self-configuration-external-token-reveal',
      testid: 'self-configuration-external-token-reveal',
      children: [tokenWarning, tokenField.el, tokenUrl, tokenDismissBtn]
    });
    var tokenReveal = tokenRevealBanner.el;
    tokenReveal.tabIndex = -1;

    externalSection.appendChild(tokenReveal);

    // ── active-grants list ──
    var externalList = document.createElement('div');
    externalList.className = 'self-configuration-external-list';
    externalList.setAttribute('data-testid', 'self-configuration-external-list');
    externalList.setAttribute('role', 'group');
    externalList.setAttribute('aria-label', 'Active external-access grants');
    externalSection.appendChild(externalList);

    panel.appendChild(externalSectionCtl.el);

    // ── M21 F03 L03 — External access behavior ──────────────────────────
    function externalErrMsg(err) {
      return err && err.message ? err.message : String(err);
    }

    function clearExternalError() {
      externalError.hidden = true;
      externalErrorCtl.set('danger', '');
    }

    function showExternalError(message) {
      externalError.hidden = false;
      externalErrorCtl.set('danger', message);
    }

    // The copy-once reveal. The token lives ONLY here (the readonly input's
    // value property); it is never written to an attribute, localStorage or
    // sessionStorage, and is cleared by `hideTokenReveal` (dismiss, disable,
    // destroy, the tab being deactivated) or by a new editor identity (a new
    // mount).
    function hideTokenReveal() {
      tokenRevealBanner.hide();
      tokenField.setValue('');
      tokenUrlValue.textContent = '';
      copyLive.textContent = '';
    }

    function showTokenReveal(result) {
      // `result` is the mint/rotate response: {identifier, label, token, url}.
      tokenField.setValue(result && result.token ? result.token : '');
      tokenUrlValue.textContent = result && result.url ? result.url : '';
      tokenRevealBanner.show();
      // Focus lands on the reveal's primary action (Copy) — inside the
      // reveal, keyboard-operable, never the page top (AC7). The reveal is
      // an `aria-live` region, so its warning is announced as it appears.
      tokenField.button.focus();
    }

    tokenDismissBtn.onclick = function () {
      hideTokenReveal();
      setExternalStatus('Dismissed the token. It cannot be shown again.');
      grantInput.focus();
    };

    function renderCredentialRow(cred) {
      var row = document.createElement('div');
      row.className = 'self-configuration-external-credential-row';
      row.setAttribute('data-testid', 'self-configuration-external-credential-row');
      row.setAttribute('data-identifier', cred.identifier);

      var info = document.createElement('div');
      info.className = 'self-configuration-external-credential-info';

      // Label rendered as text content (never HTML) — AC / edge case.
      var labelEl = document.createElement('div');
      labelEl.className = 'self-configuration-external-credential-label';
      labelEl.textContent = cred.label ? cred.label : '(no label)';
      info.appendChild(labelEl);

      var meta = document.createElement('div');
      meta.className = 'self-configuration-external-credential-meta';
      var idEl = document.createElement('span');
      idEl.className = 'self-configuration-external-credential-id';
      // The public identifier (secret-free) — NOT the one-time token.
      idEl.textContent = 'ext_' + cred.identifier;
      meta.appendChild(idEl);
      var ts = formatRevisionTimestamp(cred.created_at);
      if (ts.text) {
        var sep = document.createElement('span');
        sep.textContent = ' · created ';
        meta.appendChild(sep);
        var timeEl = document.createElement('span');
        timeEl.className = 'self-configuration-external-credential-created';
        timeEl.textContent = ts.text;
        if (ts.title) timeEl.title = ts.title;
        meta.appendChild(timeEl);
      }
      info.appendChild(meta);
      row.appendChild(info);

      var actions = document.createElement('div');
      actions.className = 'self-configuration-external-credential-actions';

      var labelSnippet = cred.label ? cred.label : cred.identifier;
      if (labelSnippet.length > 40) labelSnippet = labelSnippet.slice(0, 40) + '…';

      var rotateBtn = App.ui.button({
        variant: 'secondary',
        size: 'sm',
        label: 'Rotate',
        ariaLabel: 'Rotate external access “' + labelSnippet + '”',
        className: 'self-configuration-external-rotate-btn',
        testid: 'self-configuration-external-rotate-btn'
      });
      rotateBtn.onclick = function () {
        if (!callbacks.onRotateExternalCredential) return;
        clearExternalError();
        rotateBtn.disabled = true;
        callbacks.onRotateExternalCredential(ctx.agent.name, cred.identifier).then(function (result) {
          setExternalStatus('Rotated external access “' +
            (result && result.label ? result.label : labelSnippet) +
            '”. Copy the new token now — it is shown only once.');
          showTokenReveal(result);
          return refreshExternalList();
        }).catch(function (err) {
          showExternalError('Failed to rotate external access: ' + externalErrMsg(err));
          // Move focus to a stable target BEFORE the list rebuild destroys
          // this button, so focus never drops to <body> (AC7 — never the
          // page top). grantInput is outside the list container and survives
          // the refresh, mirroring the revoke-success and grant-error paths.
          grantInput.focus();
          // The row may be stale (revoked out-of-band → 404). Re-fetch so
          // the list reflects reality; the error stays on the section.
          refreshExternalList();
        });
      };
      actions.appendChild(rotateBtn);

      // Revoke uses the canonical two-step in-place confirm (ui/confirm.js):
      // first click arms ("Confirm revoke?"), second click within the
      // window commits. Keyboard-operable (it is a <button>).
      var revokeBtn = App.ui.button({
        variant: 'danger',
        size: 'sm',
        ariaLabel: 'Revoke external access “' + labelSnippet + '”',
        className: 'self-configuration-external-revoke-btn',
        testid: 'self-configuration-external-revoke-btn'
      });
      var revokeLabel = document.createElement('span');
      revokeLabel.setAttribute('data-confirm-title', '');
      revokeLabel.textContent = 'Revoke';
      revokeBtn.appendChild(revokeLabel);
      revokeBtn.onclick = function () {
        if (!callbacks.onRevokeExternalCredential) return;
        var commit = function () {
          clearExternalError();
          revokeBtn.disabled = true;
          callbacks.onRevokeExternalCredential(ctx.agent.name, cred.identifier).then(function () {
            setExternalStatus('Revoked external access “' +
              (cred.label ? cred.label : labelSnippet) + '”.');
            // Focus a stable target BEFORE the list rebuilds (AC7 — never
            // the page top). The grant input is outside the list container.
            grantInput.focus();
            return refreshExternalList();
          }).catch(function (err) {
            showExternalError('Failed to revoke external access: ' + externalErrMsg(err));
            // Move focus to a stable target BEFORE the list rebuild destroys
            // this button, so focus never drops to <body> (AC7 — never the
            // page top). grantInput survives the refresh (it is outside the
            // list container), mirroring the revoke-success path above.
            grantInput.focus();
            refreshExternalList();
          });
        };
        // The persistent aria-label ("Revoke external access ...") is the
        // announced subject: App.ui.confirm announces the arm, the lapse and
        // the commit through its shared live region.
        App.ui.confirm(revokeBtn, commit, {
          titleSelector: '[data-confirm-title]',
          confirmLabel: 'Confirm revoke?'
        });
      };
      actions.appendChild(revokeBtn);

      row.appendChild(actions);
      return row;
    }

    function renderExternalList(credentials) {
      externalList.textContent = '';
      credentials = credentials || [];
      if (credentials.length === 0) {
        externalList.appendChild(App.ui.emptyState({
          title: 'No external-access grants.',
          titleTag: 'p',
          variant: 'plain',
          testid: 'self-configuration-external-empty'
        }));
        return;
      }
      credentials.forEach(function (cred) {
        externalList.appendChild(renderCredentialRow(cred));
      });
    }

    // Local list re-fetch (never the whole-editor re-render — see the
    // section comment). Returns a promise so callers can chain.
    function refreshExternalList() {
      if (!callbacks.fetchExternalCredentials) {
        renderExternalList([]);
        return Promise.resolve();
      }
      return callbacks.fetchExternalCredentials(ctx.agent.name).then(function (credentials) {
        renderExternalList(credentials);
      }).catch(function () {
        externalList.textContent = 'Unable to load external-access grants.';
      });
    }

    grantBtn.onclick = function () {
      if (!callbacks.onMintExternalCredential) return;
      var label = grantInput.value.trim();
      if (!label) {
        // Inline rejection — no server round-trip (AC6).
        showExternalError('Enter a label for this external client before granting access.');
        grantInput.focus();
        return;
      }
      clearExternalError();
      grantBtn.disabled = true;
      callbacks.onMintExternalCredential(ctx.agent.name, label).then(function (result) {
        grantInput.value = '';
        grantBtn.disabled = false;
        setExternalStatus('Granted external access “' +
          (result && result.label ? result.label : label) +
          '”. Copy the token now — it is shown only once.');
        showTokenReveal(result);
        return refreshExternalList();
      }).catch(function (err) {
        grantBtn.disabled = false;
        showExternalError('Failed to grant external access: ' + externalErrMsg(err));
      });
    };

    // AC1 — enablement gate. When the surface is enabled the grant control
    // is actionable and the active-grants list is shown; when disabled the
    // grant control is disabled with a hint and the list is empty (the
    // server cascades credentials away on disable, and mint 409s otherwise).
    function renderExternalState(enabled) {
      clearExternalError();
      if (enabled) {
        setExternalStatus('Grant external clients access to this agent’s surface.');
        grantInput.disabled = false;
        grantBtn.disabled = false;
        grantHint.hidden = true;
        refreshExternalList();
      } else {
        setExternalStatus('External access is unavailable while self-configuration ' +
          'is disabled.');
        grantInput.disabled = true;
        grantBtn.disabled = true;
        grantHint.hidden = false;
        hideTokenReveal();
        renderExternalList([]);
      }
    }

    ctx.setExternalStatus = setExternalStatus;
    ctx.renderExternalState = renderExternalState;
    ctx.hideTokenReveal = hideTokenReveal;
  }

  window.App.studio.selfConfigExternal = { build: build };
})();
