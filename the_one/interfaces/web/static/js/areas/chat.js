App.registerArea({
  id: 'chat',
  label: 'Chat',
  icon: App.icons.chat,
  order: 10,
  sidebarLabel: 'Chat sessions',

  // M25 F4 L3b (DD1, AC5): the session state machine serialises itself:
  // `new/{agent}` while pending or starting, `sessions/{id}` while joining or
  // joined, nothing while idle.
  serializeState: function () {
    return this._serialize ? this._serialize() : null;
  },
  // Bare `#chats` (no sub) keeps whatever is open, a joined session or a
  // pending chat (AC9b); the router's post-hydrate sync then re-canonicalises
  // the URL from serializeState.
  hydrateState: function (sub) {
    if (!sub) return;
    if (this._hydrate) this._hydrate(sub);
  },

  init: function (sidebar, content) {
    var ws = null;
    // Per-session in-flight tracker: a session is "busy" when its agent
    // is mid-turn. Was previously a single `busy` flag per WebSocket, but
    // that caused the input to stay disabled in a NEW conversation when
    // the user switched away from a still-running one (post-F4 surfacing).
    var inFlightSessions = Object.create(null);
    // M25 F4 L3b (DD1): the session state machine (areas/chat/session-state.js).
    // Every inbound frame passes its gate; busy, the hold queue and Stop key
    // on its activeId() (the client id while starting, the session id while
    // joined). There is no "null means idle": the state's name says it.
    var chatState = App.chat.createSessionState();
    // Busy while starting (the first turn is on its way, whatever the
    // in-flight map says), else when the active session has a turn in flight.
    function isCurrentBusy() {
      if (chatState.state().name === 'starting') return true;
      var a = chatState.activeId();
      return !!(a && inFlightSessions[a]);
    }

    // Show/hide the stop button derived from isCurrentBusy() so that any code
    // path that clears inFlightSessions (onclose, session-switch, done, cancelled)
    // automatically hides it without extra plumbing. Call this after any mutation
    // to inFlightSessions or after the session state changes.
    function updateStopControl() {
      if (!stopBtn) return;
      stopBtn.hidden = !isCurrentBusy();
    }

    // F09-04 (client-hold): render a PINNED chip for the held queued message.
    // The chip lives in pendingQueuedRegionEl — a region above the composer,
    // OUTSIDE the scrolling .messages list — so it never scrolls away. The
    // held text is stored per-session in pendingQueuedMessages; only one slot
    // (queue depth = 1). The message is NOT sent to the backend while held —
    // the WS `done` handler sends it via the normal send path once the running
    // turn finishes. The chip carries a keyboard-accessible cancel (×) button.
    function showPendingQueued(text) {
      clearPendingQueued();
      if (!text || !pendingQueuedRegionEl) return;

      pendingQueuedEl = document.createElement('div');
      pendingQueuedEl.className = 'pending-queued-chip';
      pendingQueuedEl.setAttribute('data-testid', 'pending-queued');
      pendingQueuedEl.setAttribute('aria-live', 'polite');

      var label = document.createElement('span');
      label.className = 'pending-queued-label';
      label.textContent = 'Queued:';
      pendingQueuedEl.appendChild(label);

      var body = document.createElement('span');
      body.className = 'pending-queued-text';
      body.textContent = text;
      pendingQueuedEl.appendChild(body);

      // Native <button> → focusable and Enter/Space-activatable for free.
      var cancelBtn = document.createElement('button');
      cancelBtn.type = 'button';
      cancelBtn.className = 'pending-queued-cancel';
      cancelBtn.setAttribute('data-testid', 'pending-queued-cancel');
      cancelBtn.setAttribute('aria-label', 'Cancel queued message');
      cancelBtn.textContent = '×'; // ×
      cancelBtn.addEventListener('click', cancelPendingQueued);
      pendingQueuedEl.appendChild(cancelBtn);

      pendingQueuedRegionEl.appendChild(pendingQueuedEl);
      pendingQueuedRegionEl.hidden = false;
    }

    // Remove the pinned chip from the DOM (idempotent). Does NOT touch the
    // held text in pendingQueuedMessages — callers manage that explicitly.
    function clearPendingQueued() {
      if (pendingQueuedEl && pendingQueuedEl.parentNode) {
        pendingQueuedEl.parentNode.removeChild(pendingQueuedEl);
      }
      pendingQueuedEl = null;
      if (pendingQueuedRegionEl) pendingQueuedRegionEl.hidden = true;
    }

    // F09-04: cancel (×) — discard the held message for the current session
    // and remove the chip. Purely local: nothing was sent to the backend, so
    // no turn runs for the discarded message.
    function cancelPendingQueued() {
      var a = chatState.activeId();
      if (a) delete pendingQueuedMessages[a];
      clearPendingQueued();
    }

    var pendingJoinId = null;
    var sessions = [];
    // A session_list has arrived on some socket (the idle rules can run).
    var listSeen = false;
    // AC8: the socket the current binding was made on (a start_session, join
    // or leave sent, or a session_joined received). Reconnect actions run
    // only for a binding made on an EARLIER socket.
    var boundOn = null;
    // Set in onopen; cleared after that socket's first session_list, so the
    // later lists (the refresh after `done`) never re-run the reconnect rules.
    var firstListPending = false;
    // Set in onopen while joined or joining (the fresh socket is unbound until
    // the re-join lands); cleared when that state resolves. While set, Send
    // keeps its text and Stop does nothing: a message on an unbound socket
    // would auto-create a default-agent session.
    var rebinding = false;
    // The agent an entry point asked to pick (requestPick): its hydrate is a
    // real pick even where the AC9 rail-restore rule would keep a session.
    var pickIntent = null;
    // A cold `#chats/~new/{agent}` waits for the agents store to validate the
    // agent; the composer stays disabled meanwhile (AC12).
    var validating = false;
    // The optimistic first-message bubble's nodes, removed on start_failed.
    var startBubbleNodes = [];
    var currentAgentName = null;
    // M27 F3 L2: live tool_call_id -> tool name (tool_result events carry no
    // name), so a note tool's result can refresh the agent panel's notes.
    var liveToolNames = {};
    var NOTE_TOOLS = { save_note: true, update_note: true, forget_note: true };
    // M23 F02 L03 (behavior-test fix): the joined session's connector
    // platform, if any (mirrors ChatSession.platform / session_joined's new
    // `platform` field). null for a web-native session. Used to gate the
    // peer-visible-tool-result promotion below — the operator-only /
    // peer-visible distinction only exists for connector-attached sessions;
    // a plain chat session's tool results have no visibility concept at all
    // and must keep collapsing into the "Tool activity" accordion.
    var currentSessionPlatform = null;
    var messagesEl, inputEl, sendBtn, stopBtn;
    var fileInputEl, attachBtn;
    // M16 F12 L08: minimal image-ingestion producer. Staged images
    // ({data: base64, media_type}) are collected by the file-attach handler
    // and consumed (and cleared) by the next performSend.
    // HAT fix (post-L08): a visible chicklet-row preview was added above the
    // composer so the operator can see what's attached.
    // HAT fix round 2 (post-L08): the single-image `stagedImage` slot is now
    // a `stagedImages` ARRAY — attaching APPENDS rather than replacing, and
    // the hidden file input carries `multiple` so one OS-picker interaction
    // can stage several images at once. The chicklet row lives in
    // `attachmentsEl` (`.chat-attachments`, resolved alongside
    // fileInputEl/attachBtn below) ABOVE the composer box (M25 F4 L5; above
    // the old `.input-area` row before it) — the standard multi-attachment
    // layout — rather than inline inside it. `renderAttachments()` fully
    // rebuilds the row from `stagedImages` on every mutation
    // (append/remove/clear) and mirrors non-empty-ness onto a
    // `data-staged="true"` attribute on the file input so a test can
    // deterministically wait for the async FileReader(s) to finish before
    // driving send.
    // NOTE: container visibility is driven via `style.display` (NOT the
    // `hidden` attribute) — `.chip` sets `display: inline-flex`
    // unconditionally, which beats the UA `[hidden]{display:none}` rule at
    // equal specificity (author origin wins over UA origin; see the
    // `.btn-muted-destructive[hidden]` override elsewhere in chat.css for
    // the same footgun). Each chicklet itself also uses `.chip`/`.chip-remove`
    // — no CSS file change.
    // M18 F02 L02: client-side mirror of the server's authoritative caps
    // (the_one/interfaces/web/app.py IMAGE_ATTACHMENT_CAP_BYTES /
    // IMAGE_ATTACHMENT_MAX_COUNT). UX-only — a client that bypasses these
    // is still bounded by the server-side check, which is the authoritative
    // guard. Kept in sync by convention (no shared constants module between
    // the Python backend and this static JS file).
    var IMAGE_ATTACHMENT_CAP_BYTES = 10 * 1024 * 1024; // ~10 MB per image
    var IMAGE_ATTACHMENT_MAX_COUNT = 10; // max attachments per turn
    var stagedImages = [];
    var attachmentsEl;
    function renderAttachments() {
      if (fileInputEl) {
        if (stagedImages.length) fileInputEl.setAttribute('data-staged', 'true');
        else fileInputEl.removeAttribute('data-staged');
      }
      if (!attachmentsEl) return;
      attachmentsEl.innerHTML = '';
      for (var i = 0; i < stagedImages.length; i++) {
        attachmentsEl.appendChild(buildAttachmentChip(stagedImages[i], i));
      }
      attachmentsEl.style.display = stagedImages.length ? 'flex' : 'none';
    }
    // M18 F03 L01 (A1): a SEPARATE visually-hidden aria-live="polite" status
    // element announces a short delta per stage/remove mutation. Deliberately
    // NOT on the visible `.chat-attachments` row above — that row fully
    // rebuilds via innerHTML on every mutation (see renderAttachments()), so
    // making IT the live region would re-announce all N remaining chips on
    // every single removal. This element's `textContent` is instead set to
    // just the delta for the mutation that just happened, mirroring the
    // aria-live="polite" precedent set by pendingQueuedEl (chat.js ~line 61).
    var attachmentsStatusEl;
    function announceAttachmentChange(text) {
      if (attachmentsStatusEl) attachmentsStatusEl.textContent = text;
    }
    // One removable chicklet: thumbnail + a per-chip ✕ that removes just
    // this image (closes over `idx` — safe because renderAttachments()
    // rebuilds every chip from scratch on every mutation, so indices are
    // never stale by the time a click fires).
    function buildAttachmentChip(img, idx) {
      var chip = document.createElement('div');
      chip.className = 'chat-attachment chip';
      chip.setAttribute('data-testid', 'chat-attachment');
      chip.setAttribute('data-attachment-index', String(idx));

      // M18 F03 L01 (A2): interpolate the 1-based index so no two staged
      // images share an identical accessible name (thumbnail alt / remove
      // aria-label) — with multi-image staging a user relying on a screen
      // reader could not otherwise tell which chip/remove-button was which.
      var displayIndex = idx + 1;

      var thumb = document.createElement('img');
      thumb.className = 'chat-attachment-thumb';
      thumb.alt = 'Staged image ' + displayIndex;
      thumb.style.width = '24px';
      thumb.style.height = '24px';
      thumb.style.objectFit = 'cover';
      thumb.style.borderRadius = '4px';
      thumb.style.display = 'block';
      thumb.src = 'data:' + img.media_type + ';base64,' + img.data;
      chip.appendChild(thumb);

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'chat-attachment-remove chip-remove';
      removeBtn.setAttribute('data-testid', 'chat-attachment-remove');
      removeBtn.setAttribute('aria-label', 'Remove staged image ' + displayIndex);
      removeBtn.style.fontSize = '12px';
      removeBtn.textContent = '✕';
      removeBtn.addEventListener('click', function () { removeStagedImage(idx); });
      chip.appendChild(removeBtn);

      return chip;
    }
    function appendStagedImage(img) {
      stagedImages.push(img);
      renderAttachments();
      announceAttachmentChange(
        stagedImages.length === 1 ? 'Image staged' : stagedImages.length + ' images staged'
      );
    }
    function removeStagedImage(idx) {
      stagedImages.splice(idx, 1);
      renderAttachments();
      announceAttachmentChange('Image removed');
    }
    function clearStagedImages() {
      stagedImages = [];
      renderAttachments();
    }
    // Per-session one-slot queue: key is session id, value is the pending message text.
    // Mirrors inFlightSessions shape so session-switch and onclose handle both together.
    var pendingQueuedMessages = Object.create(null);
    // DOM element showing the pending queued message hint (one shared element; swapped
    // on session-switch if the joined session has a pending queued message).
    var pendingQueuedEl = null;
    // F09-04: pinned container above the composer that hosts the queued chip,
    // outside the scrolling .messages list. Assigned during setup below.
    var pendingQueuedRegionEl = null;
    var setupIncomplete = false;
    var sessionBannerEl = null;
    var setupState = { hasProviders: false, hasAgents: false };

    // M25 F4 L4a (DD5): the Chats list column, an App.ui.listPane built with
    // DOM APIs (areas/chat/chats-list.js): the New chat button (it opens the
    // agent picker) above the cross-agent history in recency groups, with a
    // delete action per row and the pending chat's row. The agent dropdown,
    // its "Select Agent" label and the old history list are retired.
    var chatsList = App.chat.chatsList.create({
      onNew: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      },
      onDelete: function (id, li, btn) {
        // Two-step confirm (arm, then confirm) via App.confirmDelete on the
        // row's <li>; the WebSocket delete is fire-and-forget and the
        // server's session_deleted + list refresh update the list (the
        // listPane keeps an armed <li> across rebuilds, DD5).
        // A1 (WCAG 4.1.2/4.1.3): the focused action button's accessible name
        // follows the armed state ("Confirm delete: {title}"), kept in step
        // with the li's .confirm-delete class by one observer per li, so a
        // lapse, a revert and a re-render (the armed button node is reused)
        // all restore "Delete chat: {title}".
        var idleLabel = btn && !li.classList.contains('confirm-delete') ? btn.getAttribute('aria-label') : null;
        if (btn && idleLabel && !li._armLabelObs && typeof MutationObserver === 'function') {
          li._armLabelObs = new MutationObserver(function () {
            var armed = li.classList.contains('confirm-delete');
            btn.setAttribute('aria-label', armed ? 'Confirm delete: ' + li._armTitle : li._armIdle);
          });
          li._armLabelObs.observe(li, { attributes: true, attributeFilter: ['class'] });
        }
        if (idleLabel) {
          li._armIdle = idleLabel;
          li._armTitle = idleLabel.replace(/^Delete chat: /, '');
        }
        App.confirmDelete(li, function () {
          if (socketOpen()) ws.send(JSON.stringify({ action: 'delete_session', session_id: id }));
        });
      }
    });
    sidebar.appendChild(chatsList.el);

    // M25 F4 L4b (DD3, DD6): the detail pane, built with DOM APIs (the
    // content sink is gone): the welcome (the empty and guidance states under
    // one "Hello." h1) and the chrome (the chat header's h1 and "with
    // {agent}", the new-chat state, the message log, then the composer),
    // areas/chat/chat-pane.js. The composer is areas/chat/composer.js (leg 5:
    // reference spec 5.5, the telemetry row above it).
    var pane = App.chat.chatPane.create({
      onNewChat: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      },
      onPickDifferent: function (btn) {
        App.chat.openPicker({ opener: btn }).catch(function () { /* a guard Stay */ });
      }
    });
    var composer = App.chat.composer.create();
    // M25 F4 L6 (DD7): the agent drawer fills the static shell slot
    // (#chat-drawer, after <main>; areas/chat/agent-drawer.js). Its toggle
    // goes at the END of the chat header. renderPane feeds it the header's
    // agent; activate/deactivate show and hide it with the area.
    var agentDrawer = App.chat.agentDrawer.create({ slot: document.getElementById('chat-drawer') });
    pane.header.appendChild(agentDrawer.toggle);
    var chromeEl = pane.chrome;
    var welcomeEl = pane.welcome;
    messagesEl = pane.messages;
    inputEl = composer.input;
    fileInputEl = composer.fileInput;
    attachBtn = composer.attachBtn;
    attachmentsEl = composer.attachmentsEl;
    attachmentsStatusEl = composer.attachmentsStatusEl;
    stopBtn = composer.stopBtn;
    sendBtn = composer.sendBtn;

    // The mascot, decorative, above the greeting.
    var mascotEl = document.createElement('img');
    mascotEl.className = 'chat-welcome-mascot';
    mascotEl.src = '/static/brand/gleepglorp_icon.png';
    mascotEl.alt = '';
    mascotEl.setAttribute('aria-hidden', 'true');
    mascotEl.setAttribute('loading', 'eager');
    mascotEl.setAttribute('data-testid', 'chat-welcome-mascot');
    pane.welcomeInner.insertBefore(mascotEl, pane.welcomeInner.firstChild);

    // The chrome: header, new-chat state, the message log, then the composer
    // (M25 F4 L5): its wrapper holds the telemetry row (the readout, shown
    // only while joined: renderPane), the staged-image row and its status,
    // the queued-message region (F09-04: above the box and OUTSIDE the
    // scrolling .messages list, so a held message cannot scroll away;
    // showPendingQueued/clearPendingQueued toggle its `hidden`), then the box.
    composer.telemetryRow.appendChild(App.chat.renderTelemetry());
    pendingQueuedRegionEl = composer.queuedRegion;
    chromeEl.appendChild(composer.el);
    content.appendChild(welcomeEl);
    content.appendChild(chromeEl);

    // The joined session's title from its session_joined (the header's
    // fallback until the `sessions` store has its row).
    var joinedTitle = null;

    function sessionRow(id) {
      var rows = App.store.peek('sessions').value;
      if (!Array.isArray(rows) || !id) return null;
      for (var i = 0; i < rows.length; i++) if (rows[i] && rows[i].id === id) return rows[i];
      return null;
    }

    // M25 F4 L4b (AC1, AC2): the header and the new-chat state follow the
    // session state.
    //   pending / starting  "New chat", "with {agent}" (blank while a cold
    //                       `~new` route validates its agent); the new-chat
    //                       state only while pending (the chrome carries
    //                       .chat-chrome--new, so the log shrinks to its
    //                       notices).
    //   joining / joined    the session's title READ FROM THE `sessions`
    //                       STORE by id (so it follows the auto-title), else
    //                       the session_joined payload's, else "Untitled
    //                       chat"; the agent likewise (store row, then the
    //                       payload).
    //   idle                no header (the welcome, or nothing yet).
    // M25 F4 L5 (DD6): the composer follows the same agent as the header:
    // its placeholder "Message {agent}…" ("Message…" with none, or while the
    // header's agent line is blank) and the agent's model id from the
    // `agents` store ('' when unknown). The telemetry row shows only while
    // joined (reference spec 5.3, 5.4: none in the new-chat state).
    // Runs from every transition and from the `sessions`, `agents` and
    // `providers` subscriptions; it patches nodes, never rebuilds them.
    function renderPane() {
      var st = chatState.state();
      var name = st.name;
      var pending = name === 'pending';
      var composerAgent = null;
      // M25 F4 L6 (DD7): the drawer follows the header: its agent, or a
      // neutral loading state while the header's agent line is blank; no
      // chat view (null) while idle.
      var drawerView = null;
      if (pending || name === 'starting') {
        pane.renderHeader({ title: 'New chat', agent: st.agent, blank: validating });
        if (!validating) composerAgent = st.agent;
        drawerView = validating ? { loading: true } : { agent: st.agent };
      } else if (name === 'joined' || name === 'joining') {
        var row = sessionRow(st.id);
        var title = row ? row.title : (name === 'joined' ? joinedTitle : null);
        var agent = row ? row.agent_name : (name === 'joined' ? currentAgentName : null);
        if (!row && name === 'joining') {
          pane.renderHeader({ title: '', agent: null, blank: true });
          drawerView = { loading: true };
        } else {
          pane.renderHeader({ title: title || 'Untitled chat', agent: agent });
          composerAgent = agent || null;
          drawerView = { agent: agent || null, sessionId: st.id || null };
        }
      } else {
        pane.renderHeader(null);
      }
      agentDrawer.render(drawerView);
      var agents = App.store.peek('agents').value;
      var providers = App.store.peek('providers').value;
      if (pending) {
        pane.renderNewState(validating ? { blank: true } : App.chat.chatPane.agentInfo(
          st.agent, agents, providers
        ));
      } else {
        pane.renderNewState(null);
      }
      chromeEl.classList.toggle('chat-chrome--new', pending);
      composer.render({
        agent: composerAgent,
        model: composerAgent ? App.chat.chatPane.agentInfo(composerAgent, agents, providers).model : ''
      });
      composer.telemetryRow.hidden = name !== 'joined';
    }

    // M08 F6 L06 HAT fix: smart-scroll. Only auto-scroll to the bottom when
    // the user is already near it; if they've scrolled up to read history,
    // leave them where they are so an incoming chunk/message doesn't yank
    // them back down. Threshold is generous enough to absorb a single new
    // message bubble's height (typical ~40-80px) so a user who WAS at the
    // bottom stays pinned after an event.
    var SCROLL_PIN_THRESHOLD = 80;
    function scrollToBottomIfPinned() {
      var dist = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight;
      if (dist <= SCROLL_PIN_THRESHOLD) {
        messagesEl.scrollTop = messagesEl.scrollHeight;
      }
    }

    function addMsg(cls, text, attribution, opts) {
      App.perf.mark('addMsg:start');
      opts = opts || {};
      messagesEl.appendChild(App.chat.renderMessage(cls, text, opts));
      if (attribution) {
        // M11 F06 L04: side inferred from opts.peerName truthiness.
        // peer-attributed user bubbles align left ('from-peer'); operator-typed
        // user bubbles stay right ('from-you'); non-user bubbles ('assistant',
        // 'tool', 'system') align left ('from-agent') as before.
        var side = opts.peerName
          ? 'from-peer'
          : (cls.indexOf('user') === 0 ? 'from-you' : 'from-agent');
        var ts = Object.prototype.hasOwnProperty.call(opts, 'ts') ? opts.ts : new Date().toISOString();
        messagesEl.appendChild(App.chat.renderAttribution(side, attribution, ts));
      }
      scrollToBottomIfPinned();
      App.perf.mark('addMsg:end');
      App.perf.measure('addMsg', 'addMsg:start', 'addMsg:end');
    }

    // M25 F4 L4a (AC6): the ONE render of the Chats list. The rows are the
    // store's `sessions` (primed from every WebSocket session_list, DD4); the
    // pending chat's row and the selection come from the session state: the
    // pending row while pending or starting, else the joined or joining
    // session's row. It runs from the `sessions` subscription below and from
    // every transition that changes the pending row or the selection (pick,
    // open, joined, the starting-to-joined swap, idle, delete). Safe off
    // Chats: a REST-primed list with no socket renders into the hidden
    // sidebar panel, with the state idle.
    function renderChatsList() {
      var st = chatState.state();
      var pendingActive = st.name === 'pending' || st.name === 'starting';
      var peeked = App.store.peek('sessions');
      chatsList.render(Array.isArray(peeked.value) ? peeked.value : [], {
        pending: pendingActive ? { agent: st.agent } : null,
        selectedId: pendingActive ? App.chat.chatsList.PENDING_ID : chatState.boundId()
      });
    }

    // The list renders from the store subscription only (never also from
    // session_list). The chat area is never destroyed (deactivate keeps the
    // WebSocket and the DOM), so this subscription lives as long as the page
    // and is never unsubscribed.
    App.store.subscribe('sessions', function () { renderChatsList(); renderPane(); });
    // Clock times and day groups follow the operator's time zone (M28 F2 L1): re-label the
    // list and every message timestamp in place when it changes. Never released.
    App.time.onChange(function () {
      renderChatsList();
      var stamps = document.querySelectorAll('.msg-attribution-ts[data-ts]');
      for (var i = 0; i < stamps.length; i++) {
        var d = new Date(stamps[i].getAttribute('data-ts'));
        if (!isNaN(d.getTime())) stamps[i].textContent = App.time.formatClock(d);
      }
    });
    renderChatsList();
    // The new-chat state reads the agent's model, description and provider
    // type from these two stores: re-render when either loads. Never
    // released, like the `sessions` subscription.
    App.store.subscribe('agents', function () { renderPane(); });
    App.store.subscribe('providers', function () { renderPane(); });
    renderPane();

    // M25 F4 L4b (DD3, AC3-AC5): the welcome is the empty state (setup
    // complete: "Start a conversation with one of your agents." and New
    // chat) or the setup guidance (no New chat; the list's is disabled too).
    // The agent list it used to hold is retired (the picker replaces it).
    function renderWelcome() {
      pane.renderWelcome(setupState);
    }

    // Only while idle with no chat to auto-join: the idle rules' `welcome`.
    function showWelcome() {
      chromeEl.hidden = true;
      welcomeEl.hidden = false;
      renderWelcome();
    }

    function showChrome() {
      welcomeEl.hidden = true;
      chromeEl.hidden = false;
    }

    // ── The session state wiring (M25 F4 L3b, DD1, DD2) ─────────────────

    function socketOpen() {
      return !!(ws && ws.readyState === WebSocket.OPEN);
    }

    // start_session, join and leave (un)bind this socket: record which one
    // (AC8's per-socket binding record).
    function sendBinding(frame) {
      ws.send(JSON.stringify(frame));
      boundOn = ws;
    }

    // An idle notice ("That conversation no longer exists") on the welcome
    // canvas; pending and joined notices go into the message log.
    function setWelcomeNotice(text) {
      pane.setNotice(text);
    }

    function showNotice(text) {
      if (chatState.state().name === 'idle') setWelcomeNotice(text);
      else addMsg('system', text);
    }

    // The composer outside a health banner: a pending chat types unless setup
    // is incomplete or a cold load is still validating its agent; Send is
    // disabled while busy.
    function applyComposerState() {
      if (sessionBannerEl) return;
      var blocked = chatState.state().name === 'pending' && (setupIncomplete || validating);
      inputEl.disabled = blocked;
      sendBtn.disabled = blocked || isCurrentBusy();
    }

    function agentListed(list, name) {
      if (!Array.isArray(list)) return false;
      for (var i = 0; i < list.length; i++) if (list[i] && list[i].name === name) return true;
      return false;
    }

    // Every start intent (the agent picker: the Chats list's New chat, the
    // empty state's New chat, "Pick a different agent") is a route,
    // `#chats/~new/{agent}` (DD2): the router's hydrate performs the pick. A re-pick while already on a `~new` route replaces
    // it (AC12). Inert while setup is incomplete. opts.opener (the picker's
    // opener) is where a guard Stay returns focus.
    function requestPick(agent, opts) {
      if (setupIncomplete || !agent) return;
      goPick(agent, opts);
    }

    // The pick's guarded go() with its one-shot pickIntent, so the AC9 rail
    // restore never swallows a deliberate start. Also the agent editor's
    // Chat action (M25 F4 L6, DD8), through App.chat.chatWith: from a dirty
    // editor the router's guard asks once. Resolves with the go()'s result.
    function goPick(agent, opts) {
      var cur = App.router.current();
      var onNew = !!(cur && cur.destination === 'chats' && cur.route.indexOf('chats/~new/') === 0);
      var goOpts = onNew ? { replace: true } : {};
      if (opts && opts.opener) goOpts.opener = opts.opener;
      pickIntent = agent;
      var done = function (ok) { pickIntent = null; return ok; };
      return App.router.go(App.router.href({ destination: 'chats', create: true, agent: agent }), goOpts)
        .then(done, function () { pickIntent = null; return false; });
    }

    // pick(agent): pending(agent) (no session yet), a `leave` for whatever
    // this socket had bound, and the pending pane. A pick of the agent
    // already pending or starting changes nothing.
    function pickAgent(agent) {
      var eff = chatState.pick(agent);
      if (eff.noop) return false;
      if (eff.leave && socketOpen()) sendBinding({ action: 'leave' });
      if (eff.discardHeld) delete pendingQueuedMessages[eff.discardHeld];
      if (eff.clearPendingJoin) pendingJoinId = null;
      rebinding = false;
      startBubbleNodes = [];
      renderPending();
      return true;
    }

    // Drop a streaming bubble that belongs to the conversation being left.
    function resetStream() {
      stopPacing();
      pendingChars = '';
      currentStreamingMsg = null;
      currentStreamingVisibility = null;
    }

    // The pending pane (M25 F4 L4b, DD6): the header reads "New chat" with
    // "with {agent}" (blank while a cold load validates the agent), the
    // new-chat state shows the agent (renderPane), the welcome is hidden, the
    // log is empty, the composer is ready, and the Chats list carries the
    // selected "New chat" row (4a).
    function renderPending() {
      var st = chatState.state();
      currentAgentName = st.agent;
      currentSessionPlatform = null;
      hideThinking();
      resetStream();
      messagesEl.innerHTML = '';
      traceShells = Object.create(null);
      App.chat.resetTelemetry(content);
      clearPendingQueued();
      setWelcomeNotice(null);
      setSessionHealth('ok');
      applyComposerState();
      updateStopControl();
      showChrome();
      renderChatsList();
      renderPane();
    }

    // openConversation(id): joining(id) and one `join`. Discards a pending
    // chat or a held message of the conversation being left. The chrome
    // shows at once (AC B: the welcome never shows while joining, so no
    // empty state flashes before the session_joined), with the header read
    // from the `sessions` store.
    function openConversation(id) {
      var eff = chatState.openConversation(id);
      if (eff.discardHeld) {
        delete pendingQueuedMessages[eff.discardHeld];
        clearPendingQueued();
      }
      validating = false;
      startBubbleNodes = [];
      setWelcomeNotice(null);
      sendBinding({ action: 'join', session_id: id });
      showChrome();
      renderChatsList();
      renderPane();
    }

    function resetToIdle() {
      var eff = chatState.reset();
      if (eff.discardHeld) delete pendingQueuedMessages[eff.discardHeld];
      clearPendingQueued();
      rebinding = false;
      validating = false;
      startBubbleNodes = [];
      renderChatsList();
      renderPane();
    }

    // The pane after the state went idle: today's session_deleted reset.
    // The next session_list's idle rules pick what shows next.
    function clearConversation() {
      hideThinking();
      resetStream();
      currentAgentName = null;
      currentSessionPlatform = null;
      joinedTitle = null;
      App.router.sync('chat', null);
      messagesEl.innerHTML = '';
      setSessionHealth('ok');
      updateStopControl();
      renderChatsList();
      renderPane();
    }

    // AC2b: one set of idle rules on every session_list, only while idle.
    function runIdleRules() {
      if (!socketOpen()) return;
      var r = chatState.idleRules(sessions, pendingJoinId);
      if (r.clearPendingJoin) pendingJoinId = null;
      if (r.open) { openConversation(r.open); return; }
      if (r.welcome) showWelcome();
    }

    function hydrate(sub) {
      if (sub.indexOf('sessions/') === 0) { hydrateSession(sub.slice('sessions/'.length)); return; }
      if (sub === 'new' || sub.indexOf('new/') === 0) hydrateNew(sub.slice('new/'.length));
    }

    function hydrateSession(id) {
      if (!id || chatState.boundId() === id) return;
      if (socketOpen()) {
        pendingJoinId = null;
        openConversation(id);
        return;
      }
      // Not open yet (a cold entry, a reconnect gap): the first session_list
      // opens it through the idle rules. Opening a conversation discards
      // whatever was open, so the state goes idle now.
      if (chatState.state().name !== 'idle') resetToIdle();
      pendingJoinId = id;
    }

    // `#chats/~new/{agent}` (AC12). The router passes the still-encoded
    // segment. Sets the state SYNCHRONOUSLY: the router serialises it right
    // after this returns.
    function hydrateNew(seg) {
      var agent = null;
      try { agent = decodeURIComponent(seg || ''); } catch (e) { agent = null; }
      var intent = pickIntent !== null && pickIntent === agent;
      if (!agent || agent === 'default') { heal(); return; }
      var st = chatState.state();
      // AC9, the rail restore: back on the `~new` route of the pending chat
      // that became this joined session, with no pick or open since. Keep the
      // session; the router's post-hydrate sync re-canonicalises the URL.
      if (!intent && st.name === 'joined' && st.startedFrom &&
          st.startedFrom.agent === agent && st.startedFrom.cid === st.id) return;
      var peek = App.store.peek('agents');
      if (peek.loaded && agentListed(peek.value, agent)) {
        var wasValidating = validating;
        validating = false;
        // The same agent's cold pending chat, still validating: validated now.
        if (!pickAgent(agent) && wasValidating && st.name === 'pending' && st.agent === agent) {
          finishValidation();
        }
        // M25 F6 L2: the cached list can lag an API-side delete (nothing
        // invalidates the store), so a pending chat renders at once from it
        // and a background forced read re-validates: a deleted agent heals.
        if (chatState.state().name === 'pending') {
          App.store.get('agents', { force: true }).then(function (list) {
            validatePending(agent, list);
          }, function () { /* unverifiable: the server's start_session validates */ });
        }
        return;
      }
      // A cold load (or an agent the cached list lacks): pending at once
      // with a neutral pane, validated when the agents store resolves
      // (a stale cache refetches).
      if (!((st.name === 'pending' || st.name === 'starting') && st.agent === agent)) {
        validating = true;
        pickAgent(agent);
      }
      App.store.get('agents').then(function (list) {
        validatePending(agent, list);
      }, function () {
        validatePending(agent, null);
      });
    }

    function validatePending(agent, list) {
      var st = chatState.state();
      if (st.name !== 'pending' || st.agent !== agent) return; // moved on
      if (list && !agentListed(list, agent)) { heal(); return; }
      if (!validating) return;
      // Known (or unverifiable: the server's start_session validates too).
      finishValidation();
    }

    function finishValidation() {
      validating = false;
      applyComposerState();
      renderPane();
    }

    // AC12 heal: an unusable `~new` route (no agent, `default`, an unknown or
    // deleted agent, a malformed `%` escape) goes back to `#chats` (replace)
    // and the idle rules. A pending chat it made is reset; a joined or
    // starting conversation is left alone (the router's post-hydrate sync
    // re-canonicalises the URL to it).
    function heal() {
      if (chatState.state().name === 'pending') {
        resetToIdle();
        clearConversation();
      } else {
        App.router.sync('chat', null);
      }
      if (chatState.state().name === 'idle' && listSeen) runIdleRules();
    }

    // The first send of a pending chat: `start_session` with a client id
    // (AC2, DD1). The optimistic bubble, thinking and busy behave like any
    // turn; the reply's session_joined keeps the bubble when the history is
    // empty.
    function startSend(text) {
      var payload = { message: text };
      var displayText = text;
      if (stagedImages.length) {
        payload.images = stagedImages;
        displayText = text ? text + ' [image]' : '[image]';
      }
      var eff = chatState.startSend(App.chat.newClientId(), payload);
      if (eff.noop) return false;
      if (payload.images) clearStagedImages();
      var before = messagesEl.lastChild;
      addMsg('user', displayText, 'You');
      startBubbleNodes = [];
      for (var n = before ? before.nextSibling : messagesEl.firstChild; n; n = n.nextSibling) {
        startBubbleNodes.push(n);
      }
      sendBinding(eff.send);
      sendBtn.disabled = true;
      updateStopControl();
      // pending -> starting: the new-chat state gives way to the log.
      renderPane();
      showThinking();
      return true;
    }

    // start_failed (or a degraded, empty session_joined) while starting: back
    // to the pending chat with the message restored (AC2).
    function applyStartFailed(eff) {
      for (var i = 0; i < startBubbleNodes.length; i++) {
        var node = startBubbleNodes[i];
        if (node.parentNode) node.parentNode.removeChild(node);
      }
      startBubbleNodes = [];
      hideThinking();
      var held = null;
      if (eff.clientId) {
        delete inFlightSessions[eff.clientId];
        held = pendingQueuedMessages[eff.clientId] || null;
        delete pendingQueuedMessages[eff.clientId];
      }
      clearPendingQueued();
      var p = eff.payload || {};
      if (!inputEl.value && p.message) setInputValue(p.message);
      if (p.images && p.images.length) {
        stagedImages = p.images.concat(stagedImages);
        renderAttachments();
      }
      if (held) {
        if (!inputEl.value) setInputValue(held);
        else addMsg('system', 'The queued message was discarded.');
      }
      applyComposerState();
      updateStopControl();
      // starting -> pending: the new-chat state is back; the error shows in
      // the log under it (the pending chrome shrinks the log to its notices).
      renderPane();
      addMsg('system', eff.error);
    }

    function renderHistory(history, agentName) {
      messagesEl.setAttribute('aria-busy', 'true');
      // A streaming bubble from the conversation the log showed before is
      // detached by the wipe below; a later chunk must start a fresh one.
      resetStream();
      messagesEl.innerHTML = '';
      // L03: reset the trace-shell bucket on replay so the DOM-rebuild
      // starts fresh; getOrCreateTrace will append shells to the freshly
      // emptied .messages container.
      traceShells = Object.create(null);
      var agentLabel = agentName || 'agent';
      for (var i = 0; i < history.length; i++) {
        var ev = history[i];
        // Pass ts explicitly (server-side broadcast events carry it; DB-restored
        // events do not). When ts is undefined, addMsg's default is omitted so
        // historical messages without a stored timestamp render unsuffixed.
        // M10 F05 L05: forward ev.visibility so operator-only bubbles
        // gain the visual marker on replay. Codec emits the key only when
        // non-None (the_one/db/codec.py:154); undefined falls through to
        // the byte-identical path inside renderMessage.
        // M11 F06 L04: forward ev.peer_name onto histOpts.peerName so peer-
        // attributed user bubbles render with msg-from-peer (left-aligned)
        // and a peer-name attribution label. Codec emits peer_name only when
        // non-None (L1+L2 contract); undefined here is falsy → defaults to
        // operator-typed 'You'/'from-you' rendering.
        var histOpts = { ts: ev.ts || null, visibility: ev.visibility, peerName: ev.peer_name };
        if (ev.type === 'user') {
          var cls = ev.source === 'api' ? 'user api' : 'user';
          var attribution = ev.peer_name || 'You';
          addMsg(cls, (ev.source && ev.source !== 'web' && ev.source !== 'restored' ? '[' + ev.source + '] ' : '') + ev.content, attribution, histOpts);
        }
        else if (ev.type === 'assistant') addMsg('assistant', ev.content, agentLabel, histOpts);
        // M16 F10 L05: replay the thinking disclosure (position-independent).
        else if (ev.type === 'thinking') renderThinking(ev);
        else if (ev.type === 'tool_call') {
          // L03: bucket tool_call events under their parent_message_id's
          // trace shell; fall back to a standalone bubble for legacy/null.
          var argsText = '> ' + ev.name + '(' + Object.entries(ev.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
          var trace = getOrCreateTrace(ev.parent_message_id);
          var msg = buildToolMsg(argsText, false, ev.tool_call_id, { visibility: ev.visibility });
          if (trace) App.chat.appendToTrace(trace, msg);
          else messagesEl.appendChild(msg);
        }
        else if (ev.type === 'tool_result') {
          // M23 F02 L03: a delivered (peer-visible) tool result is
          // promoted to a top-level bubble — imperceivable buried inside
          // the collapsed accordion otherwise. Everything else keeps the
          // pre-existing L03 bucketing.
          if (isDeliveredToolResult(ev)) {
            appendDeliveredToolMsg(ev, agentLabel, ev.ts || null);
          } else {
            var trace2 = getOrCreateTrace(ev.parent_message_id);
            var msg2 = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
            if (trace2) App.chat.appendToTrace(trace2, msg2);
            else messagesEl.appendChild(msg2);
          }
        }
        // Filter transient model-loading pings — live UI hints, not history.
        else if (ev.type === 'system' && ev.content !== 'Loading model...' && ev.content !== 'Model loaded.') {
          addMsg('system', ev.content, null, histOpts);
        }
      }
      messagesEl.removeAttribute('aria-busy');
    }


    function refreshSessionList() {
      if (socketOpen()) ws.send(JSON.stringify({ action: 'list_sessions' }));
    }

    var thinkingEl = null;
    // Streaming bubble pointer — leg-04 minimal chunk rendering (option B).
    // Holds the `<div class="msg assistant">` currently accumulating chunks
    // for the in-flight assistant iteration. Reset to null at iteration
    // boundaries (`tool_call` / `tool_result`) and at the end of the agent
    // step (`done`) so iteration N+1 lands chunks in a fresh bubble.
    var currentStreamingMsg = null;
    // M10 F05 L05: visibility for the streaming bubble. Captured from the
    // FIRST ``assistant_chunk`` of a turn (``data.visibility`` if present)
    // and applied at placeholder construction so the class+label land
    // before chunk accumulation. Today's live broadcast doesn't carry
    // ``visibility`` on ``assistant_chunk`` (known limitation: storage-edge
    // shim runs AFTER the agent step; broadcasts fire WITHIN it) — value
    // stays null and the bubble is unmarked until page refresh, at which
    // point the codec replay carries the tag. Reset alongside
    // ``currentStreamingMsg`` at the call sites of ``finalizeStreamingBubble``
    // to preserve that function's no-signature-change contract.
    var currentStreamingVisibility = null;

    // Render-pacing queue: API chunks enqueue here; a setInterval loop
    // drains characters into the bubble's pending text node (always the
    // bubble's lastChild) at ~60 chars/sec. Adaptive: long queue drains
    // faster so we don't lag behind a fast API. On finalize, the queue
    // drains synchronously before the markdown swap.
    var pendingChars = '';
    var pacingTimer = null;

    // Find the last "safe" position for incremental markdown rendering:
    // the index AFTER a blank-line block boundary (`\n\n`) that is NOT
    // inside an unclosed code fence. Returns 0 if no safe boundary.
    // A real blank line requires two adjacent newlines, which appears in
    // text.split('\n') as a sequence ["...non-empty", "", "..."] — so we
    // require lines[i+1]==='' AND i+2<lines.length (the trailing "" from
    // a single \n at end-of-input has no element after it, so we skip it).
    function findSafeRenderBoundary(text) {
      var lines = text.split('\n');
      var inFence = false;
      var lastSafe = 0;
      var pos = 0;
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.replace(/^\s+/, '').indexOf('```') === 0) inFence = !inFence;
        pos += line.length + 1;
        if (!inFence && lines[i + 1] === '' && i + 2 < lines.length) {
          lastSafe = pos + 1;
        }
      }
      return lastSafe;
    }

    // After paced text is appended to the pending tail, check whether a
    // new block boundary became visible. If yes, render the committed
    // prefix as markdown and shrink the pending tail. Keeps the bubble's
    // lastChild as a (possibly-empty) text node for subsequent appends.
    function commitSafeBoundary() {
      if (!currentStreamingMsg) return;
      var tail = currentStreamingMsg.lastChild;
      if (!tail || tail.nodeType !== 3) return;
      var boundary = findSafeRenderBoundary(tail.nodeValue || '');
      if (boundary <= 0) return;
      var toRender = tail.nodeValue.slice(0, boundary);
      var rest = tail.nodeValue.slice(boundary);
      var fragment = App.markdown.render(toRender);
      if (!fragment.firstChild) return;
      currentStreamingMsg.insertBefore(fragment, tail);
      tail.nodeValue = rest;
    }

    function pacingTick() {
      if (!pendingChars.length || !currentStreamingMsg) return;
      var tail = currentStreamingMsg.lastChild;
      if (!tail || tail.nodeType !== 3) return;
      var n = Math.max(1, Math.ceil(pendingChars.length / 30));
      var slice = pendingChars.slice(0, n);
      pendingChars = pendingChars.slice(n);
      tail.nodeValue += slice;
      commitSafeBoundary();
      scrollToBottomIfPinned();
    }

    function startPacing() {
      if (pacingTimer) return;
      pacingTimer = setInterval(pacingTick, 16);
    }

    function stopPacing() {
      if (pacingTimer) { clearInterval(pacingTimer); pacingTimer = null; }
    }

    function drainPacing() {
      if (pendingChars.length && currentStreamingMsg) {
        var tail = currentStreamingMsg.lastChild;
        if (tail && tail.nodeType === 3) tail.nodeValue += pendingChars;
      }
      pendingChars = '';
      stopPacing();
    }

    // Leg 05: swap the streaming bubble's pending tail for its
    // markdown-rendered fragment. Already-committed blocks (from
    // commitSafeBoundary) stay in place. Idempotent — no-op if no
    // bubble is active. Clears the closure pointer via `void 0`.
    function finalizeStreamingBubble() {
      drainPacing();
      var bubble = currentStreamingMsg;
      if (!bubble) return;
      currentStreamingMsg = void 0;
      var tail = bubble.lastChild;
      var tailText = '';
      if (tail && tail.nodeType === 3) {
        tailText = tail.nodeValue || '';
        bubble.removeChild(tail);
      }
      if (tailText) bubble.appendChild(App.markdown.render(tailText));
    }

    function showThinking() {
      if (thinkingEl) return;
      thinkingEl = App.chat.createThinking();
      messagesEl.appendChild(thinkingEl);
      scrollToBottomIfPinned();
    }

    function hideThinking() {
      App.chat.removeThinking(thinkingEl);
      thinkingEl = null;
    }

    // F5 L5: Login-required inline button helpers.
    //
    // Idempotent: clearLoginRequiredButton removes any stale buttons for the
    // same source_id BEFORE renderLoginRequiredButton appends a new one. This
    // keeps the L3 reconnect-snapshot replay from creating duplicate buttons
    // (the cached auth_required event is re-broadcast on every WS reconnect
    // when the agent has a pending pause).
    function clearLoginRequiredButton(data) {
      var sid = data && data.source_id ? data.source_id : null;
      var sel = sid
        ? '.login-required-btn[data-source-id="' + cssEscape(sid) + '"]'
        : '.login-required-btn';
      var existing = messagesEl.querySelectorAll(sel);
      for (var i = 0; i < existing.length; i++) {
        var btn = existing[i];
        // L05: prefer removing the wrapper when present (post-L05 DOM);
        // fall back to the bare button (legacy / pre-L05 / test-synthesized).
        var group = btn.closest('.login-required-group');
        var toRemove = group || btn;
        var parent = toRemove.parentNode;
        if (parent) parent.removeChild(toRemove);
        // L03: if the removal left an empty trace-body, also drop the
        // enclosing trace shell so an empty chrome doesn't linger.
        // (Unchanged from pre-L05 — the wrapper sits inside .trace-body
        // exactly like the bare button did, so `parent` is still the
        // .trace-body in the trace-mount path.)
        if (parent && parent.classList && parent.classList.contains('trace-body') && parent.children.length === 0) {
          var shell = parent.closest('.trace-shell');
          if (shell && shell.parentNode) {
            var key = shell.dataset.parentMsgId;
            shell.parentNode.removeChild(shell);
            if (key) delete traceShells[key];
          }
        }
      }
    }

    function cssEscape(s) {
      // Minimal subset of CSS.escape — escape quotes + backslashes so the
      // attribute selector parses cleanly. source_ids are always slugs (no
      // whitespace) per L0/L1 validation, so this is sufficient.
      return String(s).replace(/(["\\])/g, '\\$1');
    }

    // L03: bucket of trace shells keyed by parent_message_id.
    // On first tool event for a parent, create the shell and append to
    // .messages after the assistant bubble. Subsequent events route to the
    // same shell. Reset on `renderHistory` (replay) and re-seeded from the
    // DOM on WS-reconnect mid-turn via getOrCreateTrace's fallback below.
    var traceShells = Object.create(null);

    function getOrCreateTrace(parentMessageId) {
      if (!parentMessageId) return null;
      if (traceShells[parentMessageId]) return traceShells[parentMessageId];
      // Self-heal across WS reconnect: if a shell for this parent already
      // exists in the DOM from a prior connection's closure, re-seed the
      // bucket from DOM rather than minting a duplicate.
      var existing = messagesEl.querySelector(
        '.trace-shell[data-parent-msg-id="' + cssEscape(parentMessageId) + '"]'
      );
      if (existing) {
        traceShells[parentMessageId] = existing;
        return existing;
      }
      var shell = App.chat.renderTrace(parentMessageId);
      messagesEl.appendChild(shell);
      traceShells[parentMessageId] = shell;
      return shell;
    }

    // M16 F10 L05: append a thinking disclosure in stream order. Used by BOTH
    // the live ``thinking`` ws handler and the ``renderHistory`` replay branch.
    // Position-independent (mirrors getOrCreateTrace's append) — the source
    // turn may have empty content and thus no preceding assistant bubble. Its
    // OWN disclosure (a distinct `.thinking-disclosure` <details>), NOT nested
    // in the tool-trace shell. Does NOT touch the loading spinner
    // (createThinking/removeThinking/showThinking/hideThinking).
    function renderThinking(evt) {
      messagesEl.appendChild(App.chat.renderThinking(evt));
      scrollToBottomIfPinned();
    }

    // M10 F05 L05: ``opts`` forwards visibility from the source event dict
    // (history-replay ``ev.visibility`` or live ``data.visibility``) into
    // renderMessage. Tool bubbles inherit the persisted visibility tag so
    // operator-only tool events render with the marker on replay.
    function buildToolMsg(text, isError, toolCallId, opts) {
      var el = App.chat.renderMessage(isError ? 'tool error' : 'tool', text, opts);
      if (toolCallId) el.dataset.toolCallId = toolCallId;
      return el;
    }

    // M23 F02 L03 (behavior-test fix): a tool_result event is "delivered"
    // (peer-visible, e.g. a successful send_to_platform_channel result) when
    // the session is connector-attached AND the event carries no
    // operator-only tag. Gated on `currentSessionPlatform` — a plain
    // (non-connector) chat session's tool results carry no `visibility` key
    // either, but there's no peer to have seen them, so they must keep
    // collapsing into the "Tool activity" accordion like before. Excludes
    // error results defensively (an error never actually reached a
    // platform-send success, but the visibility tag alone shouldn't be the
    // only guard against surfacing an error as if it were delivered).
    function isDeliveredToolResult(ev) {
      return !!currentSessionPlatform && !ev.is_error && ev.visibility !== 'operator';
    }

    // Renders a delivered (peer-visible) tool-result as a top-level bubble
    // — outside the "Tool activity" accordion — with the same agent
    // attribution row an ordinary assistant reply gets, so it reads as "this
    // reached the peer" rather than as leftover tool debug chatter. `ts`
    // mirrors addMsg's own default: history replay passes the stored
    // timestamp (may be undefined — renders unsuffixed); the live handler
    // passes the render-time Date.
    function appendDeliveredToolMsg(ev, agentLabel, ts) {
      var msgEl = buildToolMsg(ev.content, ev.is_error, ev.tool_call_id, { visibility: ev.visibility });
      messagesEl.appendChild(msgEl);
      messagesEl.appendChild(App.chat.renderAttribution('from-agent', agentLabel, ts));
    }

    // Track per-source consent popups so the WS-delivered consent_url
    // (which arrives AFTER /api/oauth/start) can navigate the popup that
    // was opened during the user's click gesture. Opening the popup at
    // click time (with about:blank as placeholder) preserves the
    // user-gesture chain — browsers will block window.open() called
    // later from inside a WS event handler.
    var oauthPopups = Object.create(null);
    // Preserve source_name across re-renders. The SECOND auth_required
    // event (broadcast by the SDK's redirect_handler) carries the real
    // consent_url but historically lacked source_name; the backend now
    // includes it, but we keep this map as a defensive cache so a stale
    // event still renders the friendly name.
    var sourceNames = Object.create(null);

    function openConsentPopup(url, sourceId) {
      var popupW = 600;
      var popupH = 700;
      var parentX = window.screenX !== undefined ? window.screenX : window.screenLeft;
      var parentY = window.screenY !== undefined ? window.screenY : window.screenTop;
      var parentW = window.outerWidth || window.innerWidth || screen.width;
      var parentH = window.outerHeight || window.innerHeight || screen.height;
      var popupLeft = parentX + Math.max(0, (parentW - popupW) / 2);
      var popupTop = parentY + Math.max(0, (parentH - popupH) / 2);
      var features = (
        'width=' + popupW + ',height=' + popupH +
        ',left=' + Math.round(popupLeft) +
        ',top=' + Math.round(popupTop)
      );
      var name = 'mcp-oauth-consent-' + (sourceId || 'unknown');
      return window.open(url || 'about:blank', name, features);
    }

    // Sortie 04 DD2: per-(chat session, source) sign-in state. A frame with a
    // consent_url stores it; the login-required group then shows the link block
    // (App.consentLink) instead of the "Log in" button. Replayed auth_required
    // frames carry consent_url=null (rebuilt from tool-result metadata), so the
    // map is what keeps the link across a reconnect and stops a second
    // /api/oauth/start. Cleared on auth_resolved / auth_failed.
    var loginFlows = Object.create(null);
    var LOGIN_KEY_SEP = '\u0000';

    function loginFlowKey(sourceId) {
      return (chatState.activeId() || '') + LOGIN_KEY_SEP + sourceId;
    }

    function clearLoginFlows(sourceId) {
      // Above the frame gate: a switched-away session's entry must still clear,
      // so match every session's key for this source.
      var suffix = LOGIN_KEY_SEP + sourceId;
      Object.keys(loginFlows).forEach(function (k) {
        if (k.slice(-suffix.length) === suffix) delete loginFlows[k];
      });
    }

    function startLoginFlow(data) {
      var sourceId = data.source_id;
      var key = loginFlowKey(sourceId);
      var known = loginFlows[key];
      // The consent URL is already known (idempotent re-emission): open it
      // again and do not POST /api/oauth/start a second time.
      if (known && known.consentUrl) {
        if (App.consentLink.isSafeUrl(known.consentUrl)) {
          var again = openConsentPopup(known.consentUrl, sourceId);
          if (again) oauthPopups[sourceId] = again;
        }
        return;
      }
      // startedHere is set synchronously, BEFORE the fetch, so a consent frame
      // that beats the POST response finds the entry.
      loginFlows[key] = { consentUrl: null, startedHere: true, autoOpened: false };
      // A browser keeps the click-time about:blank pre-open (it preserves the
      // user gesture; navigated when the consent frame arrives). The desktop
      // webview skips it: window.open there hands the URL straight to the
      // system browser and always returns null, so an about:blank would open
      // the system browser on nothing.
      if (!(App.desktop && App.desktop.isWebview())) {
        var popup = openConsentPopup('about:blank', sourceId);
        if (popup) oauthPopups[sourceId] = popup;
      }
      function abandon() {
        delete loginFlows[key];
        closeOauthPopup(sourceId);
      }
      fetch('/api/oauth/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: sourceId,
          chat_session_id: chatState.activeId(),
          tool_call_id: data.tool_call_id,
          resource_metadata_url: data.resource_metadata_url,
        }),
      }).then(function (r) {
        if (r.ok) return;
        return r.json().then(function (err) {
          var detail = (err && err.detail) || 'OAuth start failed';
          addMsg('system', detail);
          abandon();
        });
      }).catch(function (e) {
        addMsg('system', 'Network error: ' + (e && e.message ? e.message : e));
        abandon();
      });
    }

    function resetLoginGroups(sourceId) {
      var groups = messagesEl.querySelectorAll(
        '.login-required-group[data-source-id="' + cssEscape(sourceId || '') + '"]'
      );
      for (var i = 0; i < groups.length; i++) {
        var link = groups[i].querySelector('.consent-link');
        var hadFocus = !!(link && link.contains(document.activeElement));
        if (link && link.parentNode) link.parentNode.removeChild(link);
        var btn = groups[i].querySelector('.login-required-btn');
        if (btn) btn.hidden = false;
        if (hadFocus && btn) btn.focus();
      }
    }

    function closeOauthPopup(sourceId) {
      var popup = oauthPopups[sourceId];
      if (!popup) return;
      try { if (!popup.closed) popup.close(); } catch (e) { /* ignore */ }
      delete oauthPopups[sourceId];
    }

    function renderLoginRequiredButton(data) {
      // Focus inside this source's current group would be lost when it is
      // replaced; remember it so the new link block can take it over.
      var active = document.activeElement;
      var focusWasInGroup = !!(active && active.closest && data.source_id &&
        active.closest('.login-required-group[data-source-id="' +
          cssEscape(data.source_id) + '"]'));
      // Drop any prior button for this source first (reconnect idempotency).
      clearLoginRequiredButton(data);
      if (data.source_id && data.source_name) {
        sourceNames[data.source_id] = data.source_name;
      }
      // L05: wrapper groups the attribution + button so appendToTrace
      // increments the trace-count by 1 per auth_required event (NOT 2).
      var group = document.createElement('div');
      group.className = 'login-required-group';
      group.dataset.sourceId = data.source_id || '';

      var attr = document.createElement('div');
      attr.className = 'login-required-attribution';
      attr.textContent = 'Authorization required to continue.';
      group.appendChild(attr);

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-filled-primary login-required-btn';
      btn.dataset.sourceId = data.source_id || '';
      btn.dataset.toolCallId = data.tool_call_id || '';
      btn.dataset.resourceMetadataUrl = data.resource_metadata_url || '';
      if (data.consent_url) btn.dataset.consentUrl = data.consent_url;
      var label = data.source_name
        || (data.source_id && sourceNames[data.source_id])
        || data.source_id
        || '<unknown>';
      btn.textContent = 'Log in to ' + label;
      btn.addEventListener('click', function () {
        startLoginFlow(data);
      });
      group.appendChild(btn);
      // Sortie 04 DD2: a known consent URL (this frame's, or kept from the
      // flow's earlier frame when this one is a replay with consent_url=null)
      // shows the link block; the "Log in" button stays in the DOM, hidden, so
      // the group is still found by its button on the next replay and
      // un-hides if the flow fails.
      var flow = data.source_id ? loginFlows[loginFlowKey(data.source_id)] : null;
      var linkBlock = null;
      if (flow && flow.consentUrl) {
        btn.hidden = true;
        linkBlock = App.consentLink.build(flow.consentUrl, {
          surface: 'chat', sourceName: label,
        });
        group.appendChild(linkBlock);
      }
      // L03: mount in the trace shell for this turn, if its parent_message_id
      // is present (the M07 OAuth event carries it). Fall back to a direct
      // .messages append for legacy/null cases (e.g. synthetic auth_required
      // events injected by tests).
      var authTrace = getOrCreateTrace(data.parent_message_id);
      if (authTrace) {
        App.chat.appendToTrace(authTrace, group);
      } else {
        messagesEl.appendChild(group);
      }
      if (focusWasInGroup && linkBlock) {
        var target = App.consentLink.focusTarget(linkBlock);
        if (target) target.focus();
      }
      scrollToBottomIfPinned();
    }

    function renderResumingPlaceholder(data) {
      // Lightweight system message indicating the resumed tool call is
      // re-running. The eventual tool_result event renders normally; this
      // placeholder is purely cosmetic so the chat doesn't go silent
      // between auth_resolved and the resumed tool_result arrival.
      addMsg('system', 'Resuming…');
    }

    // Normal turn-send path: optimistic user bubble, transmit, mark in-flight,
    // show the thinking indicator. Shared by send() (direct send) and the WS
    // `done` handler (dequeue of a held message) so the two paths can never
    // diverge. Does NOT touch the input value — callers manage that (the direct
    // path clears it; the dequeue path must not clobber what the user is typing).
    //
    // M16 F12 L08: when image(s) are staged, the outgoing payload gains an
    // `images` field (text-only sends stay byte-identical — no `images` key).
    // The optimistic bubble mirrors the backend's content_to_text projection
    // ("text [image]", or just "[image]" with no text) so the sender sees the
    // same shape the server will broadcast/persist. Staged images are
    // cleared after every send, sent or held (HAT fix round 2: now the
    // whole `stagedImages` array, not a single-shot slot).
    function performSend(text) {
      var payload = { message: text };
      var displayText = text;
      if (stagedImages.length) {
        payload.images = stagedImages;
        displayText = text ? text + ' [image]' : '[image]';
        clearStagedImages();
      }
      addMsg('user', displayText, 'You');
      ws.send(JSON.stringify(payload));
      // Keyed on activeId() (AC6): the joined session (the `done` handler's
      // held message also comes through here, on the joined path).
      var active = chatState.activeId();
      if (active) inFlightSessions[active] = true;
      sendBtn.disabled = true;
      updateStopControl();
      showThinking();
    }

    // Every scripted write to the composer's text goes through here, so the
    // textarea re-fits (a cleared draft drops back to two rows).
    function setInputValue(text) {
      inputEl.value = text;
      composer.fit();
    }

    function send() {
      var text = inputEl.value.trim();
      if (!text && !stagedImages.length) return;
      // Blocked by health gate (agent deleted, provider missing, etc.) — never queue.
      if (sessionBannerEl || inputEl.disabled) return;
      var st = chatState.state().name;
      // Nothing open, or a join still in flight: nothing a message could go
      // to (an unbound socket would auto-create a default-agent session).
      // The text stays in the composer.
      if (st === 'idle' || st === 'joining') return;

      var isReset = (text === '/reset');
      // /reset clears a conversation; a chat that does not exist yet has
      // none. Never sent, never held (AC6).
      if (isReset && (st === 'pending' || st === 'starting')) {
        showNotice('Send a message to start the chat first');
        return;
      }
      var active = chatState.activeId();
      // F09-04: /reset is a control command — never hold it, and it wipes the
      // conversation, so discard any held queued message + chip first so a
      // stale hold can't fire after the context is cleared.
      if (isReset && active) {
        delete pendingQueuedMessages[active];
        clearPendingQueued();
      }

      if (!isReset && isCurrentBusy()) {
        // One-slot CLIENT-HOLD queue (F09-04): hold exactly one message locally
        // while a turn runs. It is NOT sent to the backend now — the `done`
        // handler sends it via the normal path once the running turn finishes.
        // This keeps cancel trivial (nothing sent) and the chip pinned. A
        // second hold attempt while one is already held is ignored. Keyed on
        // activeId(): the client id while starting (the server uses it as the
        // session id), so a second Send while starting is held, never sent
        // as a plain message (AC6).
        if (!active) return;
        if (pendingQueuedMessages[active]) return;
        pendingQueuedMessages[active] = text;
        // The hold queue carries text only (F09-04 predates image attach) —
        // attach-while-a-turn-is-running is explicitly out of scope for L08
        // (the attach handler below already ignores staging while busy, but
        // this guards the rare race where a turn starts busy between staging
        // and send).
        clearStagedImages();
        setInputValue('');
        showPendingQueued(text);
        return;
      }

      // AC8: a closed socket, or one not re-bound yet after a reconnect,
      // keeps the text: a message must never reach an unbound socket.
      if (!socketOpen() || rebinding) return;

      if (st === 'pending') {
        if (startSend(text)) setInputValue('');
        return;
      }
      performSend(text);
      setInputValue('');
    }

    // One read per activation: agents + providers through App.store, deriving
    // the setup state.  Errors are swallowed; on a failure the prior setup
    // state is kept (never flips to "no setup").
    function refreshAgentsAndSetup() {
      return Promise.all([
        App.store.get('providers', { force: true }),
        App.store.get('agents', { force: true })
      ])
        .then(function (results) {
          setupState.hasProviders = results[0].length > 0;
          setupState.hasAgents = results[1].length > 0;
          setupIncomplete = !setupState.hasProviders || !setupState.hasAgents;
          // M25 F4 L4a (AC2): New chat is natively disabled while setup is
          // incomplete (no provider or no agent); the pane's guidance says
          // why.
          chatsList.setNewDisabled(setupIncomplete);
          var stName = chatState.state().name;
          // A shown welcome follows the setup state (the empty state <->
          // the guidance). M25 F4 L4b (DD3): the welcome is SHOWN only by
          // the idle rules (idle with no chat to auto-join); this no longer
          // shows it while idle, so the guidance never flashes before an
          // auto-join (the onopen list request follows this read). A pending
          // chat is never covered by the welcome (AC4); its composer follows
          // the setup state instead.
          if (stName === 'idle' && !welcomeEl.hidden) renderWelcome();
          if (stName === 'pending') applyComposerState();
        })
        .catch(function () { /* best-effort */ });
    }

    function setSessionHealth(status) {
      var msg = null;
      if (status === 'agent_deleted') msg = 'This agent has been deleted. Chat history is preserved but new messages cannot be sent.';
      else if (status === 'provider_missing') msg = "This agent's provider is missing. Add a model provider in Library to continue this conversation.";
      if (msg) {
        if (!sessionBannerEl) {
          sessionBannerEl = document.createElement('div');
          sessionBannerEl.className = 'chat-session-banner';
          sessionBannerEl.setAttribute('role', 'status');
          chromeEl.insertBefore(sessionBannerEl, composer.el);
        }
        sessionBannerEl.textContent = msg;
        inputEl.disabled = true; sendBtn.disabled = true;
      } else {
        if (sessionBannerEl) { sessionBannerEl.parentNode.removeChild(sessionBannerEl); sessionBannerEl = null; }
        inputEl.disabled = false; sendBtn.disabled = false;
      }
    }

    function handleSystem(data) {
      if (data.content === 'Loading model...') {
        // Server will run `agent.step` only AFTER the load finishes — until
        // then, suppress the "thinking" indicator we optimistically showed
        // on send so the operator sees a single, accurate state.
        hideThinking();
        var loadEl = document.createElement('div');
        // `system-model-loading` is a system-only class so the
        // `Model loaded.` handler below can target this row exclusively
        // without accidentally matching the thinking indicator (which
        // also carries `.model-loading` for shared dot-animation styling).
        loadEl.className = 'msg system model-loading system-model-loading';
        // DOM-built (M25 F4 L4b; was a static innerHTML literal).
        var loadTextEl = document.createElement('span');
        loadTextEl.className = 'model-loading-text';
        loadTextEl.textContent = 'Loading model';
        var dotEl = document.createElement('span');
        dotEl.className = 'model-loading-dots';
        loadEl.appendChild(loadTextEl);
        loadEl.appendChild(dotEl);
        messagesEl.appendChild(loadEl);
        scrollToBottomIfPinned();
        var frames = ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'];
        var frameIdx = 0;
        loadEl._dotTimer = setInterval(function () { frameIdx = (frameIdx + 1) % frames.length; dotEl.textContent = ' ' + frames[frameIdx]; }, 120);
      } else if (data.content === 'Model loaded.') {
        var loadingMsg = messagesEl.querySelector('.system-model-loading');
        if (loadingMsg) {
          if (loadingMsg._dotTimer) clearInterval(loadingMsg._dotTimer);
          loadingMsg.classList.remove('model-loading');
          loadingMsg.classList.remove('system-model-loading');
          loadingMsg.innerHTML = '';
          loadingMsg.textContent = 'Model loaded.';
        } else { addMsg('system', data.content); }
        // Restore the "thinking" state — the agent step is about to run
        // and we still owe the user a response indicator until the first
        // chunk arrives.
        var loadedActive = chatState.activeId();
        if (loadedActive && inFlightSessions[loadedActive]) {
          showThinking();
        }
      } else {
        hideThinking();
        addMsg('system', data.content);
        var errActive = chatState.activeId();
        if (errActive && inFlightSessions[errActive]) {
          delete inFlightSessions[errActive];
          // Also clear any pending queued message — the session is no longer
          // processing so the queue slot is moot (the error terminated the turn).
          delete pendingQueuedMessages[errActive];
          clearPendingQueued();
          updateStopControl();
          if (!sessionBannerEl) sendBtn.disabled = false;
        }
      }
    }

    var reconnectTimer = null;

    function connect() {
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
      var proto = location.protocol === 'https:' ? 'wss' : 'ws';
      var sock = new WebSocket(proto + '://' + location.host + '/ws');
      ws = sock;

      sock.onopen = function () {
        if (sock !== ws) { sock.close(); return; } // superseded before it opened
        firstListPending = true;
        var st = chatState.state();
        var boundEarlier = boundOn !== null && boundOn !== sock;
        // AC8: while starting, re-send the SAME start_session at once (never
        // `join`); the server's idempotency joins or creates it exactly once.
        if (st.name === 'starting' && boundEarlier) {
          var act = chatState.reconnectAction(null, true);
          if (act.send === 'start_session' && act.frame) sendBinding(act.frame);
        }
        // Joined or joining: the fresh socket is unbound until the first
        // session_list re-joins (or idles); Send and Stop wait.
        if (st.name === 'joined' || st.name === 'joining') rebinding = true;
        refreshAgentsAndSetup()
          .then(function () {
            if (sock === ws && sock.readyState === WebSocket.OPEN) {
              sock.send(JSON.stringify({ action: 'list_sessions' }));
            }
          });
      };

      sock.onclose = function () {
        if (sock !== ws) return; // a superseded socket
        // AC6: while starting, keep the held slot, busy and the thinking
        // indicator: the re-sent start_session restores is_processing.
        if (chatState.state().name !== 'starting') {
          // Drop "thinking…" + re-enable input so a mid-response disconnect doesn't
          // strand the UI; the auto-reconnect below brings the WS back.
          hideThinking();
          // Disconnect drops every in-flight broadcast — clear both maps so neither
          // the one-slot queue guard nor the stop control get stuck after reconnect.
          for (var k in inFlightSessions) delete inFlightSessions[k];
          for (var k2 in pendingQueuedMessages) delete pendingQueuedMessages[k2];
          clearPendingQueued();
          updateStopControl();
          if (!sessionBannerEl) applyComposerState();
        }
        reconnectTimer = setTimeout(connect, 2000);
      };

      sock.onmessage = function (e) {
        if (sock !== ws) return;
        var data = JSON.parse(e.data);
        if (data.type === 'session_joined') boundOn = sock;

        if (data.type === 'session_list') {
          sessions = data.sessions || [];
          listSeen = true;
          // M25 F4 L1 (DD4): every session_list reply primes the store's
          // 'sessions' collection, mapped to the REST summary shape
          // (_session_summary), so a WebSocket-primed row and a REST-fetched
          // row never differ. While Chats is active the WebSocket is the
          // source; nothing here fetches. (A start_session join's refresh
          // lands here too: DD4's start_session invalidation row.)
          App.store.prime('sessions', sessions.map(function (s) {
            return {
              id: s.id,
              agent_name: s.agent_name,
              title: s.title,
              created_at: s.created_at,
              updated_at: s.updated_at,
              platform: s.platform || null
            };
          }));
          // M25 F4 L4a (AC6): the prime above notifies the `sessions`
          // subscription, which renders the Chats list; nothing here renders
          // it a second time.
          // AC8: the first list on a fresh socket re-binds a joined or joining
          // state made on an earlier socket: re-join when the session is still
          // listed, else idle with a notice (never join an unknown id).
          var firstOnSocket = firstListPending;
          firstListPending = false;
          var listName = chatState.state().name;
          if (firstOnSocket && (listName === 'joined' || listName === 'joining')) {
            var ids = sessions.map(function (s) { return s.id; });
            var re = chatState.reconnectAction(ids, boundOn !== null && boundOn !== sock);
            if (re.send === 'join') {
              // joined/joining(id) -> joining(id): the same row stays
              // selected, so the list (rendered by the prime above) is current.
              sendBinding({ action: 'join', session_id: re.id });
              return;
            }
            if (re.toIdle) {
              // Deleted while the socket was down: idle, a notice, and the
              // idle rules below.
              rebinding = false;
              clearConversation();
              setWelcomeNotice(re.notice);
            }
            // Otherwise the binding was made on this socket already (a join
            // sent since it opened): its own reply clears `rebinding`.
          }
          // AC2b: the idle rules, on every list, only while idle.
          runIdleRules();
          return;
        }

        if (data.type === 'session_joined') {
          var joinedEff = chatState.onFrame(data);
          if (!joinedEff.accept) {
            // A late reply to a superseded join or start (a start abandoned
            // by a pick may still have created its session: list it).
            if (joinedEff.refreshList) refreshSessionList();
            return;
          }
          rebinding = false;
          liveToolNames = {};
          if (joinedEff.startFailed) {
            applyStartFailed(joinedEff);
            return;
          }
          var joinedId = data.session_id;
          App.perf.mark('session-join:received');
          App.router.sync('chat', joinedEff.sync);
          currentAgentName = data.agent_name;
          // M23 F02 L03: capture the joined session's connector platform
          // (undefined on a degraded-session payload's older clients / any
          // server that hasn't rolled this field out — falls back to null,
          // same as a genuine web-native session) BEFORE renderHistory runs,
          // since it reads currentSessionPlatform to gate tool-result
          // promotion.
          currentSessionPlatform = data.platform || null;
          joinedTitle = data.title || null;
          // The selection follows the join (joining -> joined; a start's
          // starting -> joined swap drops the pending row), and so does the
          // header (AC1: the title from the `sessions` store, falling back
          // to this payload's).
          renderChatsList();
          renderPane();
          hideThinking();
          App.chat.resetTelemetry(content);
          // AC2/AC7: the first turn behaves like any turn. A start's join
          // with an empty history keeps the optimistic bubble; any other
          // join renders the history (an in-flight session's history already
          // holds the user event).
          if (joinedEff.render === 'history') renderHistory(data.history, data.agent_name);
          startBubbleNodes = [];
          // M16 F06 L02: synchronously restore persisted last_usage into
          // the overlay so the token counts aren't lost on session reopen.
          // Uses a defensive read pattern (session_metadata may be absent).
          // max_context_tokens is 0 here (unknown until the seed resolves);
          // the bar will fill once setTelemetryMax runs async shortly after.
          var lastUsage = (data.session_metadata && data.session_metadata.last_usage) || null;
          if (lastUsage) {
            App.chat.updateTelemetry(content, {
              input_tokens: lastUsage.input_tokens || 0,
              output_tokens: lastUsage.output_tokens || 0,
              context_tokens: lastUsage.context_tokens || 0,
              max_context_tokens: 0,
            });
          }
          setSessionHealth(data.status || 'ok');
          // Sync per-session busy state to server ground truth
          // (`is_session_processing(session.id)`). Without this,
          // switching away from an in-flight session and back leaves
          // the prior `busy` flag stale — either stuck-disabled (turn
          // finished while away) or stuck-enabled (turn still running).
          // F09-04 (client-hold): clear any stale chip from a previous session,
          // then re-show it if THIS session still holds one. The held message is
          // client-only (no backend task) and keyed per session, so it is
          // decoupled from is_processing — do not delete it based on the busy
          // flag (session switch / cancel / dequeue manage its lifecycle).
          // A start's hold was keyed on its client id, which IS this id.
          clearPendingQueued();
          if (data.is_processing) {
            inFlightSessions[joinedId] = true;
            if (!sessionBannerEl) sendBtn.disabled = true;
            showThinking();
          } else {
            delete inFlightSessions[joinedId];
            if (!sessionBannerEl) sendBtn.disabled = false;
          }
          if (pendingQueuedMessages[joinedId]) {
            showPendingQueued(pendingQueuedMessages[joinedId]);
          }
          updateStopControl();
          showChrome();
          agentDrawer.refreshNotes();
          // F7 L04 eager-resolve: fetch the agent's max_context_tokens
          // BEFORE the first user message so the telemetry overlay's
          // `max:` field shows the real value (not 0). Closes F6.5
          // debrief AI #5. Fire-and-forget; failures (404 — agent was
          // deleted between session create and join — or 400 — provider
          // misconfigured) leave `max:` at its default until the first
          // usage event arrives. Placed AFTER showChrome() so the
          // overlay element exists before updateTelemetry mutates it.
          if (currentAgentName) {
            fetch('/api/agents/' + encodeURIComponent(currentAgentName) + '/context-window')
              .then(function (r) { return r.ok ? r.json() : null; })
              .then(function (payload) {
                if (payload && payload.max_context_tokens) {
                  // M16 F06 L02: max-only seed — never re-zeros restored
                  // used-counts; recomputes the bar from retained context_tokens.
                  App.chat.setTelemetryMax(content, payload.max_context_tokens);
                }
              })
              .catch(function () { /* best-effort; silent on failure */ });
          }
          // M08 F6 L06 HAT fix: scroll-to-bottom on session join/deep-link/
          // refresh. renderHistory() above ran while chrome was hidden
          // (clientHeight=0), so smart-scroll's pin check failed. After
          // showChrome flips visibility, jump unconditionally to the most
          // recent message — that's where the user expects to land when
          // they open a session.
          messagesEl.scrollTop = messagesEl.scrollHeight;
          App.perf.mark('session-join:dom-mutated');
          App.perf.measure('session-join.ws-to-dom', 'session-join:received', 'session-join:dom-mutated');
          requestAnimationFrame(function () {
            App.perf.mark('session-join:painted');
            App.perf.measure('session-join.dom-to-paint', 'session-join:dom-mutated', 'session-join:painted');
          });
          // The list refresh also primes the store's `sessions` (a start's
          // new session appears; DD4's start_session invalidation row).
          refreshSessionList();
          return;
        }

        if (data.type === 'start_failed') {
          var failedEff = chatState.onFrame(data);
          if (failedEff.accept && failedEff.startFailed) applyStartFailed(failedEff);
          return;
        }

        if (data.type === 'join_failed') {
          var joinFailedEff = chatState.onFrame(data);
          if (!joinFailedEff.accept) return;
          rebinding = false;
          clearConversation();
          setWelcomeNotice(joinFailedEff.notice);
          refreshSessionList();
          return;
        }

        if (data.type === 'session_deleted') {
          var deletedEff = chatState.onFrame(data);
          if (deletedEff.toIdle) {
            rebinding = false;
            clearConversation();
            // Don't auto-create — the session_list refresh below runs the
            // idle rules.
          }
          refreshSessionList();
          return;
        }

        // OAuth: the popup close is global (it may belong to any session);
        // only the inline rendering below is gated (AC3).
        if (data.type === 'auth_resolved' || data.type === 'auth_failed') {
          closeOauthPopup(data.source_id);
          clearLoginFlows(data.source_id);
        }

        // AC3, the frame gate: every other frame is session-scoped (it
        // carries no session_id), so it renders only while joined. Frames
        // from a session this socket left (a pick's `leave`, a switch) are
        // dropped while pending, starting or joining.
        if (!chatState.onFrame(data).accept) return;

        if (data.type === 'user') {
          var cls = data.source === 'api' ? 'user api' : 'user';
          // M10 F05 L05: forward visibility from the live user event.
          // ``data.visibility`` is undefined on today's live broadcasts
          // (known limitation: storage-edge shim runs post-step; live
          // broadcast emits inline within step) — the channel is wired
          // for the follow-on live-broadcast tagging leg.
          // M11 F06 L04: forward peer_name from the live broadcast onto the
          // attribution + bubble side. Peer-attributed inbound user events
          // (per F6 L3 dispatcher binding + F6 L2 codec projection) carry
          // data.peer_name. Operator-typed user events have no peer_name.
          var liveAttribution = data.peer_name || 'You';
          addMsg(cls, (data.source && data.source !== 'web' ? '[' + data.source + '] ' : '') + data.content, liveAttribution, { visibility: data.visibility, peerName: data.peer_name });
        }
        else if (data.type === 'assistant_chunk') {
          // Streaming chunk path (leg-04, option B minimal rendering).
          // First chunk: clear thinking, mint a fresh assistant bubble +
          // attribution. Subsequent chunks: enqueue the delta into the
          // pacing queue; a setInterval loop drains characters at a
          // smooth rate. Markdown rendering on `done` lands in leg 05.
          hideThinking();
          if (!currentStreamingMsg) {
            // M10 F05 L05: capture visibility from the FIRST chunk so the
            // class+label land at placeholder construction (not at
            // finalize — that would cause a visual flip). Today's live
            // broadcast doesn't carry the tag; the placeholder renders
            // unmarked and the persisted view (post-refresh) shows the
            // marker via the codec replay path.
            currentStreamingVisibility = data.visibility || null;
            var bubble = App.chat.renderMessage('assistant', '', { renderMarkdown: false, visibility: currentStreamingVisibility });
            messagesEl.appendChild(bubble);
            messagesEl.appendChild(App.chat.renderAttribution('from-agent', currentAgentName || 'agent', new Date().toISOString()));
            // Ensure the bubble has a text node child to mutate.
            if (!bubble.firstChild) {
              bubble.appendChild(document.createTextNode(''));
            }
            currentStreamingMsg = bubble;
            startPacing();
          }
          pendingChars += data.content;
        }
        else if (data.type === 'assistant') {
          // Direct-action shortcut path (non-streaming). Server only emits
          // this when no chunks fired. Streaming path skips it server-side.
          // Uniform finalize call — no-op when currentStreamingMsg is null.
          hideThinking();
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // M10 F05 L05: forward visibility from the live assistant event.
          addMsg('assistant', data.content, currentAgentName || 'agent', { visibility: data.visibility });
        }
        else if (data.type === 'thinking') {
          // M16 F10 L05 (DD2 reveal-after): the settled turn's thinking
          // disclosure. Fires AFTER the answer streamed, so the loading spinner
          // is already hidden by the assistant/chunk path — do NOT call
          // hideThinking()/finalizeStreamingBubble() (that would disturb the
          // spinner state machine or an in-progress bubble). Just append the
          // disclosure in stream order.
          renderThinking(data);
        }
        else if (data.type === 'tool_call') {
          if (data.tool_call_id) liveToolNames[data.tool_call_id] = data.name;
          hideThinking();
          // Iteration boundary — finalize the current streaming bubble so
          // iteration N+1's chunks land in a fresh bubble (markdown
          // rendering + reset of currentStreamingMsg both happen inside).
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // L03: route into the trace shell for this assistant turn.
          var argsText = '> ' + data.name + '(' + Object.entries(data.arguments).map(function (kv) { return kv[0] + '=' + JSON.stringify(kv[1]); }).join(', ') + ')';
          var liveTrace = getOrCreateTrace(data.parent_message_id);
          // M10 F05 L05: forward visibility from the live tool_call event.
          var liveMsg = buildToolMsg(argsText, false, data.tool_call_id, { visibility: data.visibility });
          if (liveTrace) {
            App.chat.appendToTrace(liveTrace, liveMsg);
          } else {
            // Legacy / null parent_message_id — render standalone.
            messagesEl.appendChild(liveMsg);
          }
          scrollToBottomIfPinned();
        }
        else if (data.type === 'tool_result') {
          // M27 F3 L2: a note tool changed the notes; the panel re-fetches.
          if (NOTE_TOOLS[liveToolNames[data.tool_call_id]]) agentDrawer.refreshNotes();
          // Iteration boundary — finalize the current streaming bubble.
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // M23 F02 L03: a delivered (peer-visible) tool result is
          // promoted to a top-level bubble live too, matching renderHistory
          // — otherwise a live-vs-reload rendering gap would just move from
          // the operator-only marker (fixed above) to this accordion
          // placement instead.
          if (isDeliveredToolResult(data)) {
            appendDeliveredToolMsg(data, currentAgentName || 'agent', new Date().toISOString());
          } else {
            // L03: route into the trace shell for this assistant turn.
            var resTrace = getOrCreateTrace(data.parent_message_id);
            // M10 F05 L05: forward visibility from the live tool_result event.
            var resMsg = buildToolMsg(data.content, data.is_error, data.tool_call_id, { visibility: data.visibility });
            if (resTrace) {
              App.chat.appendToTrace(resTrace, resMsg);
            } else {
              messagesEl.appendChild(resMsg);
            }
          }
          scrollToBottomIfPinned();
        }
        else if (data.type === 'system') handleSystem(data);
        else if (data.type === 'usage') App.chat.updateTelemetry(content, data);
        else if (data.type === 'auth_required') {
          // F5 L5: lazy-path → render an inline "Login required for <source>"
          // button in the chat history. First emission has consent_url=null;
          // a second emission (post /api/oauth/start) carries the real
          // consent_url. When the second event arrives AND we have a popup
          // opened from the user's click gesture, navigate it to the
          // consent_url directly — preserves the gesture chain so the
          // browser doesn't block the navigation or convert it to a tab.
          hideThinking();
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          var flowKey = data.source_id ? loginFlowKey(data.source_id) : null;
          var flow = flowKey ? loginFlows[flowKey] : null;
          if (data.consent_url && flowKey) {
            if (!flow) {
              flow = loginFlows[flowKey] = {
                consentUrl: null, startedHere: false, autoOpened: false,
              };
            }
            flow.consentUrl = data.consent_url;
          }
          var popupHeld = false;
          var consentSafe = App.consentLink.isSafeUrl(data.consent_url);
          if (data.consent_url && oauthPopups[data.source_id]) {
            var p = oauthPopups[data.source_id];
            if (!consentSafe) {
              // Never navigate the pre-opened popup to a non-web address.
              closeOauthPopup(data.source_id);
            } else {
              try {
                if (!p.closed) {
                  popupHeld = true;
                  p.location.href = data.consent_url;
                  p.focus();
                }
              } catch (e) { /* cross-origin or closed; ignore */ }
            }
          }
          renderLoginRequiredButton(data);
          // One best-effort open of the consent page, only for the flow started
          // from this page's click, only when no popup is held and not yet tried.
          // The desktop webview hands this to the system browser (it may be
          // swallowed without a user gesture; the link block is the fallback).
          if (consentSafe && flow && flow.startedHere && !popupHeld && !flow.autoOpened) {
            flow.autoOpened = true;
            try { window.open(data.consent_url, '_blank'); } catch (e) { /* link block remains */ }
          }
        }
        else if (data.type === 'auth_resolved') {
          // F5 L5: auth completed. Clear inline button, surface a
          // "Resuming…" placeholder until the resumed tool_result arrives.
          // (The popup was closed above the frame gate: the callback page's
          // own window.close() usually fires first; that is a fallback.)
          clearLoginRequiredButton(data);
          renderResumingPlaceholder(data);
        }
        else if (data.type === 'auth_failed') {
          // F5 L5: surface the OAuth-flow failure as a system error
          // notice (the popup was closed above the frame gate).
          var failMsg = 'OAuth failed: ' + (data.description || data.error || 'unknown error');
          addMsg('system', failMsg);
          // The consent URL is dead: drop the link block and offer "Log in" again.
          resetLoginGroups(data.source_id);
        }
        else if (data.type === 'done') {
          hideThinking();
          // End of agent step — finalize so the streaming bubble swaps
          // its accumulated text for the markdown-rendered fragment, and
          // the next user message starts a fresh streaming round.
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          // AC6: the joined session (activeId); a held message goes out on
          // the joined path (performSend), never as a start.
          var sid = chatState.activeId();
          // F09-02 (client-hold): the held queued message was NOT sent during
          // the turn — it waited locally. Now the running turn has finished, so
          // dequeue it and send it via the NORMAL send path. This renders the
          // user bubble in the correct order (after this turn's response, before
          // the queued turn's response) and starts the queued turn — the sender's
          // optimistic render + the backend's sender-exclusion (app.py) align
          // because it flows through the same path as a normal send.
          var held = sid ? pendingQueuedMessages[sid] : null;
          if (held) {
            delete pendingQueuedMessages[sid];
            clearPendingQueued();
            performSend(held);
          } else {
            // No held message — normal idle reset.
            if (sid) delete inFlightSessions[sid];
            clearPendingQueued();
            updateStopControl();
            if (!sessionBannerEl) sendBtn.disabled = false;
          }
          refreshSessionList();
        }
        else if (data.type === 'cancelled') {
          // F7 L04: cancel — mirror the FULL done reset (binding per design review).
          // The partial assistant bubble was already committed by the backend (leg 3);
          // finalizeStreamingBubble() seals any streaming tail still in the pacing queue.
          hideThinking();
          finalizeStreamingBubble();
          currentStreamingVisibility = null;
          var cancelledActive = chatState.activeId();
          if (cancelledActive) {
            delete inFlightSessions[cancelledActive];
            // Cancel also discards any pending queued message (DD4 sub-decision:
            // "stop" means stop everything). Both the optimistic click handler and
            // this arrival path clear it so a race between the two is safe.
            delete pendingQueuedMessages[cancelledActive];
            clearPendingQueued();
          }
          updateStopControl();
          if (!sessionBannerEl) sendBtn.disabled = false;
          refreshSessionList();
        }
      };
    }

    // Wire events
    // M25 F4 L5 (DD6): the composer's textarea. Enter sends (its newline is
    // prevented); Shift+Enter keeps the native newline. An Enter that commits
    // an IME composition does nothing here (the IME takes it): WebKit can
    // deliver that Enter with isComposing false, so keyCode 229 (the
    // composition keyCode) is checked too.
    inputEl.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' || e.shiftKey) return;
      if (e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      send();
    });
    // The textarea grows with its content (to about eight lines).
    inputEl.addEventListener('input', function () { composer.fit(); });
    sendBtn.addEventListener('click', send);

    // M16 F12 L08: minimal image-ingestion producer. Attach (chat-attach-btn) opens
    // the OS file picker; the hidden file input's `change` handler reads
    // EVERY selected file (HAT fix round 2: `multiple` + iterate
    // fileInputEl.files, appending — a prior selection is not replaced) via
    // FileReader.readAsDataURL and stages {data, media_type} (base64 payload
    // with the `data:...;base64,` prefix stripped) per file for the next
    // performSend. Attach-while-a-turn-is-running is out of scope for L08
    // (the F09-04 hold queue carries text only) — both handlers ignore the
    // interaction while the current session is busy rather than staging an
    // image that would silently be dropped by the hold-queue clear above.
    attachBtn.addEventListener('click', function () {
      if (isCurrentBusy() || (sessionBannerEl || inputEl.disabled)) return;
      fileInputEl.click();
    });
    fileInputEl.addEventListener('change', function () {
      // Snapshot into a real array BEFORE clearing `.value` below — the
      // input's `.files` FileList is LIVE (tied to the element), so
      // resetting `.value` empties it in place; a stored reference to the
      // FileList itself (rather than to the individual File objects) would
      // silently see length 0 by the time the loop below runs.
      var files = fileInputEl.files ? Array.prototype.slice.call(fileInputEl.files) : [];
      // Reset the input value so selecting the SAME file(s) again still
      // fires `change` (browsers do not re-fire change for an unchanged
      // value).
      fileInputEl.value = '';
      if (!files.length) return;
      if (isCurrentBusy()) return;
      // M18 F02 L02: per-file size check + count cap. `plannedCount` (NOT
      // `stagedImages.length` alone) tracks images already staged PLUS
      // ones scheduled earlier in this same batch — FileReader is async,
      // so a multi-select batch would otherwise schedule more than
      // IMAGE_ATTACHMENT_MAX_COUNT reads before any of them resolves and
      // increments `stagedImages`.
      var plannedCount = stagedImages.length;
      var rejectedForSize = false;
      var rejectedForCount = false;
      for (var i = 0; i < files.length; i++) {
        (function (file) {
          // Only image/* is staged — a non-image pick (accept="image/*"
          // already restricts the OS picker, but this guards direct DOM
          // manipulation, e.g. Playwright's set_input_files) is silently
          // ignored per-file.
          if (file.type.indexOf('image/') !== 0) return;
          if (file.size > IMAGE_ATTACHMENT_CAP_BYTES) {
            rejectedForSize = true;
            return;
          }
          if (plannedCount >= IMAGE_ATTACHMENT_MAX_COUNT) {
            rejectedForCount = true;
            return;
          }
          plannedCount++;
          var reader = new FileReader();
          reader.onload = function () {
            var result = String(reader.result || '');
            var comma = result.indexOf(',');
            var base64 = comma >= 0 ? result.slice(comma + 1) : result;
            appendStagedImage({ data: base64, media_type: file.type });
          };
          reader.readAsDataURL(file);
        })(files[i]);
      }
      // Cap-rejection notices announce via the established addMsg('system',
      // ...) mechanism, which lands in the message log's own
      // role="log" aria-live="polite" region (chat.js ~line 279) — that has
      // always announced these to SR users. The M18 F03 L01 a11y pass added
      // a SEPARATE live-region (announceAttachmentChange()) that only
      // covers the staging-row silence (stage/remove of individual
      // chicklets); it is intentionally not wired to these cap notices.
      if (rejectedForSize) {
        addMsg(
          'system',
          'One or more images exceed the ' +
            Math.floor(IMAGE_ATTACHMENT_CAP_BYTES / (1024 * 1024)) +
            ' MB per-image limit and were not attached.'
        );
      }
      if (rejectedForCount) {
        addMsg(
          'system',
          'Only up to ' +
            IMAGE_ATTACHMENT_MAX_COUNT +
            ' images can be attached per message; extra selections were not attached.'
        );
      }
    });

    // F7 L04: stop/cancel button — send the cancel action, then optimistically
    // reset the thinking indicator and discard any pending queued message. The
    // `cancelled` event from the backend will perform the authoritative full reset.
    stopBtn.addEventListener('click', function () {
      if (!isCurrentBusy()) return; // no-op: already done, or raced to completion
      // AC8: a closed or not-yet-re-bound socket has nothing to cancel (and a
      // send on a closed socket throws). While starting, the cancel is
      // ordered after start_session on the socket, so it binds to the new
      // session.
      if (!socketOpen() || rebinding) return;
      ws.send(JSON.stringify({ action: 'cancel' }));
      // Optimistic: clear thinking immediately so the UI feels responsive.
      hideThinking();
      // Discard pending queued message — "stop" means stop everything.
      var stopActive = chatState.activeId();
      if (stopActive) {
        delete pendingQueuedMessages[stopActive];
        clearPendingQueued();
      }
      // Do NOT prematurely clear inFlightSessions or re-enable sendBtn here;
      // the authoritative `cancelled` event handles those (avoids a race where
      // a rapid double-click re-enables the button before the event arrives).
    });

    var self = this;
    self._connect = connect;
    self._ws = function () { return ws; };
    self._refreshAgentsAndSetup = refreshAgentsAndSetup;
    self._serialize = function () { return chatState.serialize(); };
    self._hydrate = hydrate;
    // Test seams. `_joinSession` opens a conversation (one `join`) on an open
    // socket; `_sessionState` is the state machine's state().
    self._joinSession = function (id) { if (socketOpen()) openConversation(id); };
    self._sessionState = function () { return chatState.state(); };
    // AC4: "the joined or joining id", derived from the state (null while
    // idle, pending or starting).
    Object.defineProperty(self, '_currentSessionId', {
      get: function () { return chatState.boundId(); },
      configurable: true
    });
    Object.defineProperty(self, '_pendingJoinId', {
      get: function () { return pendingJoinId; },
      set: function (v) { pendingJoinId = v; },
      configurable: true
    });

    // M25 F4 L4a (AC12): the agent picker's host, registered LAST in init so
    // App.chat.openPicker calls queued before the area existed run now. The
    // picker hands a pick to requestPick (the route and pickIntent stay
    // here); with setup incomplete an open is an inert no-op.
    App.chat.registerPickerHost({
      setupIncomplete: function () { return setupIncomplete; },
      onPick: function (agent, opts) { requestPick(agent, opts); },
      chatWith: function (agent, opts) { return goPick(agent, opts); }
    });
    self._agentDrawer = agentDrawer;
  },

  activate: function () {
    // M25 F4 L6 (DD7): the drawer shows only on Chats.
    if (this._agentDrawer) this._agentDrawer.setActive(true);
    if (!this._ws || !this._ws() || this._ws().readyState > 1) {
      this._connect();
    } else if (this._ws() && this._ws().readyState === WebSocket.OPEN) {
      this._refreshAgentsAndSetup();
    }
  },

  deactivate: function () {
    // Keep WS alive. The drawer is hidden off Chats, so <main> keeps its
    // full width on Agents, Library and Settings (M25 F4 L6, DD7).
    if (this._agentDrawer) this._agentDrawer.setActive(false);
  }
});
