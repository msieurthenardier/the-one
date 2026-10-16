(function () {
  'use strict';
  window.App = window.App || {};
  App.ui = App.ui || {};

  // App.ui.consentLink - the sign-in link block for MCP sign-in (sortie 04, DD1;
  // moved into the library and rebuilt on copyField, M31 F1 L5).
  //
  // Shown in chat (the login-required group) and the MCP editor (the status
  // panel) whenever a consent URL is known, whatever window.open returned: the
  // desktop webview hands window.open to the system browser and returns null, so
  // the link is the one path that always works. A read-only URL field, an
  // "Open sign-in page" anchor (target=_blank, styled as a button), a Copy button
  // and one helper line. DOM APIs only; classes consent-link-*.
  //
  // App.ui.consentLink.build(url, opts) builds the block; opts: surface ('chat'
  // default, or 'mcp'), sourceName, and the test ids urlTestid, openTestid,
  // copyTestid. With none given, the surface's literal ids are used (one
  // setAttribute per id, so the registry extractor sees them). opts.help replaces
  // the helper line's words (a string) or omits the line (false), for a caller
  // whose flow differs (the provider sign-in pastes a code instead of waiting).
  var idSeq = 0;

  // Only http(s) addresses are ever shown as a link, opened or navigated to: the
  // consent URL comes from the MCP server's authorization endpoint.
  function isSafeUrl(url) {
    return typeof url === 'string' && /^https?:\/\//i.test(url);
  }

  // The element a keyboard user should land on when this block replaces the
  // control they were on: the open link, else the URL field, else the notice.
  function focusTarget(block) {
    if (!block) return null;
    return block.querySelector('.consent-link-open') ||
      block.querySelector('.consent-link-url') ||
      block.querySelector('.consent-link-unsafe');
  }

  function build(url, opts) {
    opts = opts || {};
    var surface = opts.surface === 'mcp' ? 'mcp' : 'chat';
    var isMcp = surface === 'mcp';
    var sourceName = opts.sourceName ? String(opts.sourceName) : '';

    var block = document.createElement('div');
    block.className = 'consent-link consent-link--' + surface;

    if (!isSafeUrl(url)) {
      var bad = document.createElement('p');
      bad.className = 'consent-link-help consent-link-unsafe';
      bad.tabIndex = -1;
      bad.textContent = "This server sent a sign-in address that isn't a web link, " +
        "so it can't be opened.";
      block.appendChild(bad);
      return block;
    }

    var helpId = 'consent-help-' + (++idSeq);
    var open = document.createElement('a');
    open.className = 'btn-outlined-primary consent-link-open';
    open.href = url;
    open.target = '_blank';
    open.rel = 'noopener noreferrer';
    var helpText = opts.help === undefined
      ? "Finish signing in in the browser window. This page updates when you're done."
      : opts.help;
    if (helpText) open.setAttribute('aria-describedby', helpId);
    open.appendChild(document.createTextNode('Open sign-in page'));
    var hint = document.createElement('span');
    hint.className = 'visually-hidden';
    hint.textContent = ' (opens in your browser)';
    open.appendChild(hint);
    if (opts.openTestid) open.setAttribute('data-testid', opts.openTestid);
    else if (isMcp) open.setAttribute('data-testid', 'mcp-consent-link-open');
    else open.setAttribute('data-testid', 'chat-consent-link-open');

    var live = document.createElement('span');
    live.className = 'visually-hidden consent-link-live';
    live.setAttribute('role', 'status');

    var field = App.ui.copyField({
      value: url,
      label: sourceName ? 'Sign-in address for ' + sourceName : 'Sign-in page URL',
      inputClass: 'consent-link-url',
      rowClass: 'consent-link-row',
      copyClass: 'consent-link-copy',
      extra: [open],
      liveEl: live,
      doneText: 'Link copied',
      failText: 'Copy failed — select the link and copy it'
    });
    if (opts.urlTestid) field.input.setAttribute('data-testid', opts.urlTestid);
    else if (isMcp) field.input.setAttribute('data-testid', 'mcp-consent-link-url');
    else field.input.setAttribute('data-testid', 'chat-consent-link-url');
    if (opts.copyTestid) field.button.setAttribute('data-testid', opts.copyTestid);
    else if (isMcp) field.button.setAttribute('data-testid', 'mcp-consent-link-copy');
    else field.button.setAttribute('data-testid', 'chat-consent-link-copy');
    block.appendChild(field.el);
    block.appendChild(live);

    if (helpText) {
      var help = document.createElement('p');
      help.className = 'consent-link-help';
      help.id = helpId;
      help.textContent = helpText;
      block.appendChild(help);
    }

    return block;
  }

  App.ui.consentLink = function (url, opts) {
    return build(url, opts);
  };
  App.ui.consentLink.build = build;
  App.ui.consentLink.isSafeUrl = isSafeUrl;
  App.ui.consentLink.focusTarget = focusTarget;
  window.App.consentLink = App.ui.consentLink;
})();
