// App.gleepglorpDrawerChat -- the GleepGlorp drawer's chat (M36 F3 L3, flight DD2, DD3): a second
// chat instance (App.chat.create, the "drawer profile") mounted in the drawer shell's body slot,
// with its own WebSocket opened at page load (mount() connects at once, even while GleepGlorp is
// off, because the window socket serves every page: it carries the window-wide frames
// sessions_changed, config_changed and gleepglorp_changed on pages that never visit Chats).
//
//   App.gleepglorpDrawerChat.mount()      build the instance and the header buttons (app.js, once,
//                                         after App.gleepglorpDrawer.mount())
//   .instance()                           the chat instance handle, or null before mount
//
// The conversation is kept in localStorage `gleepglorp-drawer-session` (every tab shares it; a
// New chat in one tab does not move another until it reloads: there is no storage listener). The
// stored id is re-joined on the drawer's first open, never at boot, so a cold boot sends no
// `join`. The instance writes the id from one place (the accepted session_joined) and clears it
// on New chat, a failed join and a deleted or pruned conversation: a boot-time pending state, a
// start and a reconnect never touch it.
(function () {
  'use strict';
  window.App = window.App || {};

  var STORAGE_KEY = 'gleepglorp-drawer-session';
  var SUGGESTION = 'What does this page do?';
  var mounted = null;

  function readStored() {
    try { return localStorage.getItem(STORAGE_KEY) || null; } catch (e) { return null; }
  }

  function writeStored(id) {
    try {
      if (id) localStorage.setItem(STORAGE_KEY, id);
      else localStorage.removeItem(STORAGE_KEY);
    } catch (e) { /* no persistence (private mode): the drawer still works */ }
  }

  function el(tag, attrs, children) {
    return App.ui.util.el(tag, attrs, children);
  }

  function mount() {
    if (mounted) return mounted;
    var D = App.gleepglorpDrawer;
    var slot = D.bodySlot();
    if (!slot) return null;
    slot.classList.add('chat-instance');

    var inst = null;
    var liveId = null; // the bound session once joined (Open in Chats); not the stored id
    var firstOpenDone = false;

    // ── The empty state (the pending chat) ──────────────────────────────────
    var suggestion = App.ui.button({
      variant: 'secondary',
      size: 'sm',
      label: SUGGESTION,
      className: 'gg-drawer-suggestion',
      testid: 'gg-drawer-suggestion',
      disabled: true,
      onClick: function () { if (inst) inst.sendText(SUGGESTION); }
    });
    var empty = el('div', { className: 'gg-drawer-empty' }, [
      el('p', { className: 'gg-drawer-empty-lead', text: 'Ask about this page, or ask me to fill it in.' }),
      el('p', {
        className: 'gg-drawer-empty-note',
        text: 'I fill forms and suggest changes. Nothing is saved until you click.'
      }),
      suggestion
    ]);
    empty.setAttribute('data-testid', 'gg-drawer-empty');

    // ── The header buttons: New chat and Open in Chats, before the labelled Close ──
    var newBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      iconOnly: true,
      icon: 'square-pen',
      ariaLabel: 'New chat',
      testid: 'gg-drawer-new-chat',
      onClick: function () {
        if (!inst) return;
        inst.startNew();
        liveId = null;
        renderActions();
        inst.focusComposer();
      }
    });
    newBtn.setAttribute('title', 'New chat');
    var openBtn = App.ui.button({
      variant: 'ghost',
      size: 'sm',
      iconOnly: true,
      icon: 'chat',
      ariaLabel: 'Open in Chats',
      testid: 'gg-drawer-open-in-chats',
      onClick: function () {
        if (!liveId) return;
        // A guarded go: a dirty editor asks once, and Stay returns focus to this button.
        App.router.go(App.router.href({ destination: 'chats', id: liveId }), { opener: openBtn });
      }
    });
    openBtn.setAttribute('title', 'Open in Chats');
    openBtn.hidden = true;
    var actions = D.headerActions();
    if (actions) {
      actions.appendChild(newBtn);
      actions.appendChild(openBtn);
    }

    // Open in Chats shows only while a conversation is joined (absent while pending).
    function renderActions() { openBtn.hidden = !liveId; }

    // ── The instance ────────────────────────────────────────────────────────
    // The router adapter: the drawer never changes the URL (the chat is not a route).
    var router = {
      sync: function () {},
      goNew: function () { return Promise.resolve(false); },
      go: function (href, opts) { return App.router.go(href, opts); }
    };

    inst = App.chat.create({
      profile: 'drawer',
      content: slot,
      agent: App.chat.GLEEPGLORP,
      testidPrefix: 'gg-',
      pickerHost: false,
      signIn: false,
      router: router,
      emptyState: empty,
      onSessionChange: function (id) {
        liveId = id || null;
        writeStored(liveId);
        renderActions();
      },
      onBlockedChange: function (blocked) { suggestion.disabled = !!blocked; },
      testids: {
        testid: 'gg-chat-input',
        attachTestid: 'gg-chat-attach-btn',
        fileInputTestid: 'gg-chat-image-input',
        modelTestid: 'gg-chat-model',
        stopTestid: 'gg-chat-stop-btn',
        sendTestid: 'gg-chat-send-btn',
        attachmentsTestid: 'gg-chat-attachments',
        attachmentsStatusTestid: 'gg-chat-attachments-status',
        queuedTestid: 'gg-pending-queued-region',
        telemetryTestid: 'gg-chat-telemetry',
        copyStatusTestid: 'gg-chat-copy-status'
      }
    });

    // The first open re-joins the stored conversation (if any); a stored id that no longer
    // exists answers join_failed, and the instance goes pending and clears it.
    // The message log is a live region only while the drawer is open (a closed drawer is hidden).
    var log = inst.messagesEl;
    function setLive(on) {
      if (!log) return;
      if (on) {
        log.setAttribute('role', 'log');
        log.setAttribute('aria-live', 'polite');
        log.setAttribute('aria-relevant', 'additions');
        log.setAttribute('aria-atomic', 'false');
      } else {
        ['role', 'aria-live', 'aria-relevant', 'aria-atomic'].forEach(function (a) {
          log.removeAttribute(a);
        });
      }
    }
    D.onOpenChange(function (open) {
      if (open) inst.attach();
      setLive(open);
      if (!open || firstOpenDone) return;
      firstOpenDone = true;
      var id = readStored();
      if (id && inst.sessionState().name === 'pending') inst.joinSession(id);
    });
    // Opening focuses the composer when it can take input (else the shell's setup link / title).
    D.setInitialFocus(function () {
      if (inst.isBlocked()) return false;
      inst.focusComposer();
      return true;
    });

    // The window socket, opened now: it serves every page.
    inst.connect();

    mounted = { instance: function () { return inst; } };
    window.App.gleepglorpDrawerChat.instance = mounted.instance;
    return mounted;
  }

  window.App.gleepglorpDrawerChat = {
    mount: mount,
    instance: function () { return null; }
  };
})();
