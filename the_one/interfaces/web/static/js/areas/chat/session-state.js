// App.chat.createSessionState() -- the chat area's session state machine
// (M25 F4 leg 3b, flight DD1).
//
// PURE: no DOM, no WebSocket, no timers. Each transition returns its effects
// as DATA, which the chat area (areas/chat.js) performs; the transition table
// is therefore testable with plain inputs and outputs
// (tests/browser/test_flow_chat_session_state.py).
//
// States:
//   idle                          nothing open
//   joining(id)                   a `join` was sent; waiting for its reply
//   joined(id)                    bound to a session; its frames render
//   pending(agent)                a new chat with `agent`, not created yet
//   starting(clientId, agent, payload)
//                                 the first send went out as `start_session`
//                                 with a client-generated id; waiting for its
//                                 `session_joined` (or `start_failed`)
//
// The state GATES every inbound frame (accepts / onFrame): `leave` cannot
// recall frames already in flight, and session-scoped frames carry no
// session_id, so only `joined` renders them. `session_list` and
// `session_deleted` are always accepted (the list); `session_joined`,
// `start_failed` and `join_failed` are accepted only for the id the state is
// waiting for.
//
// API (every transition returns an effects object; unknown keys are absent):
//   state()               -> {name, id, agent, clientId, startedFrom, suppressAutoJoin}
//   pick(agent)           -> {noop} | {leave, discardHeld, clearPendingJoin, render: 'pending'}
//   openConversation(id)  -> {join: id, discardHeld}
//   startSend(cid, payload) -> {noop} | {send: <start_session frame>, busy: true}
//   onFrame(frame)        -> {accept: false, refreshList?}
//                          | {accept: true, render: 'history'|'keep', sync, refreshList, fromStart?}
//                          | {accept: true, startFailed: true, error, payload, clientId}
//                          | {accept: true, toIdle: true, notice?, deleted?, refreshList}
//                          | {accept: true}   (session_list, other session_deleted, session-scoped)
//   reset()               -> {toIdle: true, discardHeld}
//   accepts(frame)        -> boolean (no state change)
//   activeId()            -> clientId in starting, id in joined, else null
//   boundId()             -> id in joined or joining, else null
//   serialize()           -> 'new/' + encodeURIComponent(agent) | 'sessions/' + id | null
//   startFrame()          -> the start_session frame while starting, else null
//   reconnectAction(listedIds, boundOnEarlierSocket)
//                         -> {send: 'start_session'|'join'|null, frame?, id?, toIdle?, notice?}
//                            (moves joined/joining to joining(id) or idle; see below)
//   idleRules(list, pendingJoinId)
//                         -> {} when not idle, else {open: id|null, clearPendingJoin, welcome}
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var GONE_NOTICE = 'That conversation no longer exists';

  // Degraded session_joined statuses -> the reason a start could not use them.
  var DEGRADED_REASONS = {
    agent_deleted: 'This agent has been deleted.',
    provider_missing: "This agent's provider is missing. Add a model provider in Library to continue.",
    build_failed: "This chat's agent could not be set up. Check the agent's settings; the app log has the details."
  };

  // M36 F1 L04: the GleepGlorp statuses carry the same banner sentences as the joined chat's
  // banner (agent-kind.js owns them; this module loads alone in its unit tests, so it is
  // read at use time).
  function reasonFor(status) {
    var gg = App.chat.GLEEPGLORP_STATUSES && App.chat.GLEEPGLORP_STATUSES[status];
    if (gg) return App.chat.gleepglorpBanner(gg);
    return DEGRADED_REASONS[status] || 'This chat cannot start.';
  }

  function isOk(frame) {
    return frame.status == null || frame.status === 'ok';
  }

  function copyPayload(p) {
    if (!p) return null;
    var out = { message: typeof p.message === 'string' ? p.message : '' };
    if (p.images && p.images.length) out.images = p.images.slice();
    if (p.page) out.page = p.page;
    return out;
  }

  function createSessionState() {
    var cur = blank('idle');
    var startedFrom = null; // {agent, cid}: the pending chat a joined session started from
    var suppressAutoJoin = false;

    function blank(name) {
      return { name: name, id: null, agent: null, clientId: null, payload: null };
    }

    function enter(name, fields) {
      var next = blank(name);
      fields = fields || {};
      if (fields.id != null) next.id = fields.id;
      if (fields.agent != null) next.agent = fields.agent;
      if (fields.clientId != null) next.clientId = fields.clientId;
      if (fields.payload != null) next.payload = fields.payload;
      cur = next;
    }

    function state() {
      return {
        name: cur.name,
        id: cur.id,
        agent: cur.agent,
        clientId: cur.clientId,
        startedFrom: startedFrom ? { agent: startedFrom.agent, cid: startedFrom.cid } : null,
        suppressAutoJoin: suppressAutoJoin
      };
    }

    function activeId() {
      if (cur.name === 'starting') return cur.clientId;
      if (cur.name === 'joined') return cur.id;
      return null;
    }

    function boundId() {
      return cur.name === 'joined' || cur.name === 'joining' ? cur.id : null;
    }

    function serialize() {
      if (cur.name === 'pending' || cur.name === 'starting') {
        return 'new/' + encodeURIComponent(cur.agent);
      }
      if (cur.name === 'joining' || cur.name === 'joined') return 'sessions/' + cur.id;
      return null;
    }

    function startFrame() {
      if (cur.name !== 'starting') return null;
      var p = copyPayload(cur.payload) || { message: '' };
      var f = { action: 'start_session', session_id: cur.clientId, agent_name: cur.agent, message: p.message };
      if (p.images) f.images = p.images;
      if (p.page) f.page = p.page;
      return f;
    }

    // ── Transitions ─────────────────────────────────────────────────────

    function pick(agent) {
      // The same agent while pending or starting: nothing (the header
      // button, a re-click, a re-hydrate). No leave, no reset.
      if ((cur.name === 'pending' || cur.name === 'starting') && cur.agent === agent) {
        return { noop: true };
      }
      var prev = cur.name;
      var eff = {
        leave: prev === 'joined' || prev === 'joining' || prev === 'starting',
        discardHeld: activeId(),
        clearPendingJoin: true,
        render: 'pending'
      };
      enter('pending', { agent: agent });
      startedFrom = null;
      suppressAutoJoin = false;
      return eff;
    }

    function openConversation(id) {
      var prevActive = activeId();
      enter('joining', { id: id });
      startedFrom = null;
      suppressAutoJoin = false;
      return { join: id, discardHeld: prevActive && prevActive !== id ? prevActive : null };
    }

    function startSend(clientId, payload) {
      if (cur.name !== 'pending') return { noop: true };
      enter('starting', { clientId: clientId, agent: cur.agent, payload: copyPayload(payload) });
      return { send: startFrame(), busy: true };
    }

    function reset() {
      var eff = { toIdle: true, discardHeld: activeId() };
      enter('idle');
      suppressAutoJoin = false;
      return eff;
    }

    // ── The frame gate ──────────────────────────────────────────────────

    function accepts(frame) {
      var t = frame && frame.type;
      if (t === 'session_list' || t === 'session_deleted' || t === 'sessions_changed') return true;
      if (t === 'session_joined') {
        if (cur.name === 'starting') return frame.session_id === cur.clientId;
        if (cur.name === 'joining') return frame.session_id === cur.id;
        // joined (the same id: a starting re-send's second reply; another
        // id: a late reply to a superseded join), pending, idle: dropped.
        return false;
      }
      if (t === 'start_failed') return cur.name === 'starting' && frame.session_id === cur.clientId;
      if (t === 'join_failed') return cur.name === 'joining' && frame.session_id === cur.id;
      // Every other frame is session-scoped: only a joined session renders.
      // `session_updated` (a connector turn ended) is one of them; chat.js
      // checks its session_id against boundId() and handles a same-id
      // `joining` case before this gate.
      return cur.name === 'joined';
    }

    function onFrame(frame) {
      var t = frame && frame.type;
      if (!accepts(frame)) {
        // A late session_joined while pending may be a session an abandoned
        // start created: refresh the list so it appears.
        return t === 'session_joined' && cur.name === 'pending'
          ? { accept: false, refreshList: true }
          : { accept: false };
      }
      if (t === 'session_list' || t === 'sessions_changed') return { accept: true };
      if (t === 'session_deleted') {
        if (cur.name === 'joined' && frame.session_id === cur.id) {
          enter('idle');
          return { accept: true, toIdle: true, deleted: true, refreshList: true };
        }
        return { accept: true, refreshList: true };
      }
      if (t === 'session_joined') {
        var sid = frame.session_id;
        var history = frame.history || [];
        if (cur.name === 'starting') {
          var agent = cur.agent;
          var payload = cur.payload;
          if (!isOk(frame) && !history.length) {
            // Degraded and empty: nothing to show; back to the pending chat,
            // as a start_failed.
            enter('pending', { agent: agent });
            return {
              accept: true, startFailed: true, clientId: sid, payload: copyPayload(payload),
              error: (typeof frame.reason === 'string' && frame.reason) ||
                reasonFor(frame.status)
            };
          }
          enter('joined', { id: sid });
          startedFrom = { agent: agent, cid: sid };
          return {
            accept: true, fromStart: true, render: history.length ? 'history' : 'keep',
            sync: 'sessions/' + sid, refreshList: true
          };
        }
        // joining(id) with the same id
        enter('joined', { id: sid });
        return { accept: true, render: 'history', sync: 'sessions/' + sid, refreshList: true };
      }
      if (t === 'start_failed') {
        var failedPayload = cur.payload;
        var failedId = cur.clientId;
        enter('pending', { agent: cur.agent });
        return {
          accept: true, startFailed: true, clientId: failedId, payload: copyPayload(failedPayload),
          error: frame.error || 'This chat could not start.'
        };
      }
      if (t === 'join_failed') {
        enter('idle');
        suppressAutoJoin = true;
        return { accept: true, toIdle: true, notice: GONE_NOTICE, refreshList: true };
      }
      // A session-scoped frame in joined.
      return { accept: true };
    }

    // ── Queries ─────────────────────────────────────────────────────────

    function listed(ids, id) {
      if (!ids) return false;
      for (var i = 0; i < ids.length; i++) if (ids[i] === id) return true;
      return false;
    }

    // A fresh socket. Runs ONLY for a binding made on an earlier socket.
    //   starting -> re-send the same start_session (never `join`: a join can
    //               pop a just-created in-memory session before its insert);
    //   joined / joining -> joining(id) + join(id) when the fresh list has
    //               the id; else idle with a notice (never join an unknown id);
    //   pending / idle -> nothing.
    // It moves the state itself (joined/joining -> joining or idle).
    function reconnectAction(listedIds, boundOnEarlierSocket) {
      if (!boundOnEarlierSocket) return { send: null };
      if (cur.name === 'starting') return { send: 'start_session', frame: startFrame() };
      if (cur.name === 'joined' || cur.name === 'joining') {
        var id = cur.id;
        if (listed(listedIds, id)) {
          enter('joining', { id: id });
          return { send: 'join', id: id };
        }
        enter('idle');
        return { send: null, toIdle: true, notice: GONE_NOTICE };
      }
      return { send: null };
    }

    // The idle rules, run on EVERY session_list, but only while idle:
    // pendingJoinId if listed, else the most recent session unless
    // suppressAutoJoin, else the welcome / empty state.
    function idleRules(list, pendingJoinId) {
      if (cur.name !== 'idle') return {};
      list = list || [];
      var out = { open: null, clearPendingJoin: !!pendingJoinId, welcome: false };
      if (pendingJoinId) {
        for (var i = 0; i < list.length; i++) {
          if (list[i] && list[i].id === pendingJoinId) { out.open = pendingJoinId; return out; }
        }
      }
      if (list.length && !suppressAutoJoin) { out.open = list[0].id; return out; }
      out.welcome = true;
      return out;
    }

    return {
      state: state,
      pick: pick,
      openConversation: openConversation,
      startSend: startSend,
      onFrame: onFrame,
      reset: reset,
      accepts: accepts,
      activeId: activeId,
      boundId: boundId,
      serialize: serialize,
      startFrame: startFrame,
      reconnectAction: reconnectAction,
      idleRules: idleRules
    };
  }

  // A client-generated session id for start_session: 32 lowercase hex
  // characters from crypto.getRandomValues (the server validates the format).
  function newClientId() {
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    var out = '';
    for (var i = 0; i < bytes.length; i++) out += (bytes[i] < 16 ? '0' : '') + bytes[i].toString(16);
    return out;
  }

  window.App.chat.createSessionState = createSessionState;
  window.App.chat.newClientId = newClientId;
  window.App.chat.DEGRADED_REASONS = DEGRADED_REASONS;
})();
