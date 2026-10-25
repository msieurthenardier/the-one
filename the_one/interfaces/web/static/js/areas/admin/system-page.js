(function () {
  'use strict';
  window.App = window.App || {};
  window.App.admin = window.App.admin || {};

  // The three General pages (M25 F3 L5a, DD6): Appearance (theme toggle),
  // Prompts (the read-only platform prompt sections) and Encryption (the rotate flow).
  // Until L5a they were one "General" page with three blocks; each block now
  // has its own route and renders under the page's own header, so the block's
  // former section title is the page's h1 and nothing repeats it. The blocks
  // keep their markup and test ids. Each renderer owns its whole page and
  // shares no state with the others, so each block's wiring runs only on its
  // own page. Built with DOM APIs (no HTML-string sink).

  function el(tag, attrs, children) {
    return window.App.ui.util.el(tag, attrs, children);
  }

  // The page header (reference spec section 4): one h1 per page, no
  // breadcrumb, built by App.ui.pageHeader (M31 F4 L08a). `headingId` names
  // the h1 for anything labelled by it. Returns nothing.
  function renderPage(container, title, headingId, sectionChildren) {
    container.textContent = '';
    container.appendChild(window.App.ui.pageHeader({ title: title, headingId: headingId || null }).el);
    container.appendChild(el('div', { className: 'admin-form' }, [
      el('div', { className: 'admin-system-section' }, sectionChildren)
    ]));
  }

  function text(copy) {
    return el('p', { className: 'admin-system-text', text: copy });
  }

  // A paragraph inside a section stack, where the stack's gap is the spacing.
  function intro(copy) {
    return el('p', { className: 'admin-system-text admin-system-intro', text: copy });
  }

  // ── Appearance ────────────────────────────────────────────────────────

  var THEME_EVENT = 'theme-preference-changed';

  function renderAppearancePage(container) {
    var App = window.App;
    // The picker is an App.ui.radioGroup in its card look (ledger row 39). Its
    // fieldset is named "Theme" through a hidden legend; the page's h1 names
    // the page.
    var group = App.ui.radioGroup({
      legend: 'Theme',
      legendHidden: true,
      testid: 'theme-picker',
      value: App.theme.get(),
      options: [
        { value: 'light', label: 'Light', testid: 'theme-option-light' },
        { value: 'dark', label: 'Dark', testid: 'theme-option-dark' },
        { value: 'auto', label: 'Auto', testid: 'theme-option-auto' }
      ],
      onChange: function (pref) { App.theme.set(pref); }
    });
    renderPage(container, 'Appearance', 'admin-appearance-heading', [
      text('Choose a theme. Auto follows your operating system preference.'),
      group.el
    ]);
    // Another tab or the desktop shell changing the theme updates the picker.
    // The page returns {destroy()}, which admin.js calls on every re-render and
    // teardown, so the listener is removed when the page goes (DD8-19). It also
    // prunes itself on an event once the group has left the document, as a
    // backstop. setValue is silent, so this never loops back into App.theme.set.
    function onTheme(e) {
      if (!group.el.isConnected) {
        document.removeEventListener(THEME_EVENT, onTheme);
        return;
      }
      group.setValue(e.detail.pref);
    }
    document.addEventListener(THEME_EVENT, onTheme);
    return {
      destroy: function () { document.removeEventListener(THEME_EVENT, onTheme); }
    };
  }

  // ── Prompts ───────────────────────────────────────────────────────────

  // One read-only prompt text: a trimmed, scrollable App.ui.codeBlock (A1). The
  // `label` names it as a region when it scrolls. Text is set with textContent
  // only: note text is attacker-influenced (CLAUDE.md).
  function promptBlock(label) {
    var block = window.App.ui.codeBlock({
      text: 'Loading…',
      trim: true,
      maxHeight: 'tall',
      label: label
    });
    return block;
  }

  // A sub-heading under a layer (A3): the variant a block below belongs to. A plain
  // semibold line, not a second eyebrow, so it never competes with the layer title.
  function variantHeading(copy) {
    return el('p', { className: 'prompt-variant', text: copy });
  }

  // One layer of the assembled prompt (B11): the layer title is the section's h2,
  // the stronger heading; the rhythm between its parts is the section stack's (A2).
  function promptLayer(title, help, children) {
    return window.App.ui.section({
      title: title,
      titleTag: 'h2',
      layout: 'stack',
      inset: 'none',
      description: help || null,
      children: children
    });
  }

  // One platform-prompt section as a block (Flight 2 leg 1c, DD8): an h3 title, an
  // "Applies when" line and the section's text. The test id is
  // `platform-section-{variant}-{id}` (a parametric family, see the registry).
  function platformSectionBlock(row) {
    var key = row.variant + '-' + row.id;
    var applies = el('p', {
      className: 'admin-system-text prompt-block-applies',
      text: 'Applies when: ' + row.applies_when
    });
    applies.setAttribute('data-testid', 'platform-section-' + key + '-applies-when');
    var code = promptBlock(row.title);
    code.el.setAttribute('data-testid', 'platform-section-' + key + '-text');
    code.set(row.text);
    var block = el('div', { className: 'prompt-block' }, [
      el('h3', { className: 'prompt-block-title', text: row.title }),
      applies,
      code.el
    ]);
    block.setAttribute('data-testid', 'platform-section-' + key);
    return block;
  }

  // One list in assembly order (HAT step 9): the tools rows as served, with the
  // tool-free Identity placed right after the Identity block. A tool-free row whose
  // id and text repeat a tools row (Formatting) is shown once; one that differs
  // stays, adjacent to its tools twin. Each block's "Applies when" line says which
  // agents it reaches, so there are no variant sub-headings.
  function platformOrder(rows) {
    var tools = rows.filter(function (r) { return r.variant === 'tools'; });
    var free = rows.filter(function (r) { return r.variant !== 'tools'; });
    var out = tools.slice();
    free.forEach(function (f) {
      var twin = -1;
      var i;
      for (i = 0; i < out.length; i++) {
        if (out[i].variant === 'tools' && out[i].id === f.id) { twin = i; }
      }
      if (twin !== -1) {
        if (out[twin].text !== f.text) { out.splice(twin + 1, 0, f); }
        return;
      }
      var at = f.id.indexOf('identity') === 0 ? 0 : out.length - 1;
      for (i = 0; i < out.length; i++) {
        if (out[i].id === 'identity') { at = i; }
      }
      out.splice(f.id.indexOf('identity') === 0 ? at + 1 : out.length, 0, f);
    });
    return out;
  }

  function fillPlatformSections(mount, rows) {
    mount.textContent = '';
    platformOrder(rows).forEach(function (r) { mount.appendChild(platformSectionBlock(r)); });
  }

  function renderPromptsPage(container) {
    var App = window.App;
    var platform = el('div', { className: 'platform-sections' }, [
      el('p', { className: 'admin-system-text', text: 'Loading…' })
    ]);
    platform.setAttribute('data-testid', 'platform-sections');
    var rules = promptBlock('Rules prompt');
    rules.el.setAttribute('data-testid', 'rules-prompt-content');
    var notes = promptBlock('Notes prompt');
    notes.el.setAttribute('data-testid', 'notes-prompt-content');
    var notesFree = promptBlock('Notes prompt without tools');
    notesFree.el.setAttribute('data-testid', 'notes-prompt-content-tool-free');
    var dateWith = promptBlock('Date prompt');
    dateWith.el.setAttribute('data-testid', 'date-prompt-content');
    var dateWithout = promptBlock('Date prompt without the time tool');
    dateWithout.el.setAttribute('data-testid', 'date-prompt-content-without-tool');
    var loadError = el('div', {});
    loadError.setAttribute('data-testid', 'prompts-load-error');
    renderPage(container, 'Prompts', null, [
      text('Every agent’s system prompt is assembled from these layers, in this order, ' +
        'separated by ---: the platform prompt, the agent’s own system prompt (set on its General tab), ' +
        'then rules, notes and the date. Parts of the platform prompt apply only when the agent ' +
        'can use them (each block says when). They are read-only and only change via code releases. ' +
        'The Rules and Notes layers below show placeholder content.'),
      loadError,
      promptLayer('Platform prompt', null, [platform]).el,
      promptLayer('Rules', 'Added when the agent has enabled rules, numbered in your order.',
        [rules.el]).el,
      promptLayer('Notes', 'Added after the rules when the agent keeps notes.', [
        variantHeading('With tools'),
        notes.el,
        variantHeading('Without tools (it can’t save notes, so the saving instructions are left out)'),
        notesFree.el
      ]).el,
      promptLayer('Date',
        'Added last to every agent’s prompt, with the date in your time zone. ' +
        'The first wording is used when the agent has the current_time tool; ' +
        'the second when it doesn’t.', [
          variantHeading('With the time tool'),
          dateWith.el,
          variantHeading('Without it'),
          dateWithout.el
        ]).el
    ]);
    function fill(block, value) {
      block.set(typeof value === 'string' ? value : '(unavailable)');
    }
    var blocks = [rules, notes, notesFree, dateWith, dateWithout];
    App.api.fetchJson('/api/info').then(function (data) {
      if (!platform.isConnected) { return; }
      if (Array.isArray(data.platform_sections)) {
        fillPlatformSections(platform, data.platform_sections);
      } else {
        platform.textContent = '';
        platform.appendChild(App.ui.status({ state: 'danger', role: 'alert',
          text: 'The platform prompt is not available.' }).el);
      }
      fill(rules, data.rules_prompt_example);
      fill(notes, data.notes_prompt_example);
      fill(notesFree, data.notes_prompt_example_tool_free);
      fill(dateWith, data.date_prompt_example);
      fill(dateWithout, data.date_prompt_example_without_tool);
    }).catch(function (err) {
      if (!platform.isConnected) { return; }
      platform.textContent = '';
      blocks.forEach(function (b) { b.set('(unavailable)'); });
      loadError.textContent = '';
      loadError.appendChild(App.ui.status({
        state: 'danger',
        role: 'alert',
        text: 'The prompts could not be loaded. ' + (err && err.message ? err.message : '')
      }).el);
    });
  }

  // ── Encryption ────────────────────────────────────────────────────────

  var ROTATE_OK_MS = 3000;
  var STAGED_TEXT = 'The encryption key was rotated, but the key file could not be updated ' +
    'on disk. The new key is staged and will be applied at next start. Check the server log.';
  // The rotation timer, one handle for the whole module: cleared at the start of
  // every attempt and whenever the page renders again (DD8-10), so a first rotation's
  // "Key rotated." timer can never wipe a later attempt's warning.
  var rotateTimer = null;

  function clearRotateTimer() {
    if (rotateTimer) {
      clearTimeout(rotateTimer);
      rotateTimer = null;
    }
  }

  function renderEncryptionPage(container) {
    var App = window.App;
    clearRotateTimer();
    var gen = App.ui.util.latest();

    // The rotate button: App.ui.button (danger) with the [data-confirm-title] span the
    // two-step confirm swaps (App.ui.button's label is a bare text node).
    var rotateBtn = App.ui.button({ variant: 'danger', testid: 'rotate-key-btn' });
    var titleEl = el('span', { text: 'Rotate encryption key' });
    titleEl.setAttribute('data-confirm-title', '');
    rotateBtn.appendChild(titleEl);

    // The result: a persistent polite live region holding one App.ui.status that is
    // inserted when there is something to say and removed when there is not (a node
    // inserted into a live region is announced reliably; toggling `hidden` is not).
    var result = el('div', { role: 'status' });
    result.setAttribute('data-testid', 'rotate-result');
    function clearResult() {
      result.textContent = '';
      result.removeAttribute('data-state');
    }
    function showResult(state, copy) {
      clearRotateTimer();
      clearResult();
      result.setAttribute('data-state', state);
      result.appendChild(App.ui.status({ state: state, text: copy, live: 'off', textTone: true }).el);
    }

    // B12: when the key last changed and how many stored items it covers.
    var lastRotated = el('span', { text: '…' });
    lastRotated.setAttribute('data-testid', 'encryption-last-rotated');
    var facts = App.ui.facts({
      testid: 'encryption-facts',
      rows: [
        { label: 'Last rotated', value: lastRotated },
        { label: 'Items with stored secrets', value: '…',
          valueTestid: 'encryption-credential-count' }
      ]
    });
    var factsError = App.ui.status({ state: 'danger', text: 'The key details are unavailable.',
      live: 'off' });
    factsError.el.setAttribute('data-testid', 'encryption-facts-error');
    factsError.el.hidden = true;
    var rotatedIso = null;
    function paintRotated() {
      if (rotatedIso) {
        lastRotated.textContent = App.time.formatDateTime(rotatedIso);
        lastRotated.setAttribute('title', rotatedIso);
        lastRotated.setAttribute('data-rotated-at', rotatedIso);
      } else {
        lastRotated.textContent = 'Never';
        lastRotated.removeAttribute('title');
        lastRotated.removeAttribute('data-rotated-at');
      }
    }
    App.time.onChange(paintRotated, lastRotated);

    function loadFacts(initial) {
      var token = gen.next();
      App.api.fetchJson('/api/encryption/status').then(function (data) {
        if (!gen.isCurrent(token) || !result.isConnected) { return; }
        rotatedIso = data.last_rotated_at || null;
        paintRotated();
        facts.set([
          { label: 'Last rotated', value: lastRotated },
          { label: 'Items with stored secrets', value: String(data.credential_count),
            valueTestid: 'encryption-credential-count' }
        ]);
        facts.el.hidden = false;
        factsError.el.hidden = true;
        // A staged rotation keeps its warning across a reload (until the next attempt).
        if (initial && data.key_file_pending && !result.firstChild) {
          showResult('warning', STAGED_TEXT);
        }
      }).catch(function () {
        if (!gen.isCurrent(token) || !result.isConnected) { return; }
        facts.el.hidden = true;
        factsError.el.hidden = false;
      });
    }

    var busy = false;
    function commit(btn, revertFn) {
      if (busy) { return; }
      busy = true;
      clearRotateTimer();
      clearResult();
      var focus = App.focusAfter.begin(btn);
      // aria-disabled, never `disabled`: a disabled button drops focus (DD8-12).
      btn.setAttribute('aria-disabled', 'true');
      titleEl.textContent = 'Rotating…';
      function done() {
        busy = false;
        btn.removeAttribute('aria-disabled');
        revertFn();
        App.focusAfter.restore(focus, btn);
      }
      App.api.fetchJson('/api/encryption/rotate', { method: 'POST' }).then(function (data) {
        done();
        if (data && data.key_file === 'staged') {
          // The database and the in-memory key rotated, but the key file could not be
          // promoted (the `.next` sidecar reconciles at the next start). The warning
          // stays until the next attempt: an operator must not mistake it for success.
          showResult('warning', STAGED_TEXT);
        } else {
          // "promoted" and any other/missing key_file value are success.
          showResult('success', 'Key rotated.');
          rotateTimer = setTimeout(function () {
            rotateTimer = null;
            if (result.isConnected && result.getAttribute('data-state') === 'success') {
              clearResult();
            }
          }, ROTATE_OK_MS);
        }
        loadFacts(false);
      }).catch(function (err) {
        done();
        showResult('danger', err && err.message ? err.message : 'Rotation failed.');
      });
    }

    rotateBtn.addEventListener('click', function () {
      if (busy) { return; }
      App.ui.confirm(rotateBtn, commit, {
        confirmLabel: 'Rotate key?',
        announceName: 'Rotate encryption key'
      });
    });

    var banner = App.ui.banner({
      tone: 'warning',
      role: 'note',
      text: 'The old key is discarded. This can’t be undone.'
    });
    renderPage(container, 'Encryption', null, [
      App.ui.section({
        layout: 'stack',
        inset: 'none',
        children: [
          intro('The credentials the app stores, such as provider API keys, sign-in tokens, ' +
            'server and connector secrets and tool settings, are encrypted at rest with one key. ' +
            'Rotating generates a new key and re-encrypts everything stored with it.'),
          banner.el,
          facts.el,
          factsError.el,
          rotateBtn,
          result
        ]
      }).el
    ]);
    loadFacts(true);
  }

  window.App.admin.renderPage = renderPage;
  window.App.admin.renderAppearancePage = renderAppearancePage;
  window.App.admin.renderPromptsPage = renderPromptsPage;
  window.App.admin.renderEncryptionPage = renderEncryptionPage;
})();
