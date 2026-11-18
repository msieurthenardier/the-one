// App.chat.agentKind -- the one "which agent is this" helper for the chat surfaces
// (M36 F1 L04). GleepGlorp has no agents row, so a name is one of four kinds:
//
//   App.chat.agentKind(name) -> { kind, settingsHref }
//     kind 'gleepglorp'  the exact name "GleepGlorp" (the built-in assistant); settingsHref is
//                        '#settings/gleepglorp'
//     kind 'agent'       a row in the loaded `agents` store; settingsHref is '#agents/{name}'
//     kind 'loading'     the agents store is not loaded (or failed) yet: the name may exist
//     kind 'unknown'     the loaded store has no such agent (a deleted agent, a null name)
//
// The five membership checks (session-flow agentListed, socket agentMayExist, chat-pane
// agentInfo, the transcript's step-limit link, the drawer's describe) all go through it, and
// no code path builds '#agents/GleepGlorp'.
//
//   App.chat.GLEEPGLORP                  the exact reserved name
//   App.chat.gleepglorpSettings()        a copy of App.gleepglorp's loaded value, or null
//   App.chat.gleepglorpEnabled()         true when the loaded settings say enabled
//   App.chat.gleepglorpBanner(state)     the chat banner sentence for a not-ready state
//   App.chat.GLEEPGLORP_STATUSES         the session_joined statuses -> state
//
// The three UNAVAILABLE sentences are a client copy of the server's table
// (the_one/gleepglorp/messages.py); tests/test_gleepglorp_messages.py reads them out of this
// file and checks they match.
(function () {
  'use strict';

  window.App = window.App || {};
  window.App.chat = window.App.chat || {};

  var GLEEPGLORP = 'GleepGlorp';

  var UNAVAILABLE = {
    off: "GleepGlorp is turned off.",
    needs_model: "GleepGlorp needs a model.",
    provider_missing: "GleepGlorp's model provider was removed."
  };

  var STATUSES = {
    gleepglorp_off: 'off',
    gleepglorp_needs_model: 'needs_model',
    gleepglorp_provider_missing: 'provider_missing'
  };

  function settingsHref() {
    return App.router.href({ destination: 'settings', section: 'gleepglorp' });
  }

  function agentKind(name) {
    if (name === GLEEPGLORP) return { kind: 'gleepglorp', settingsHref: settingsHref() };
    var peeked = App.store.peek('agents');
    if (!peeked.loaded || !peeked.ok || !Array.isArray(peeked.value)) {
      return { kind: 'loading', settingsHref: null };
    }
    for (var i = 0; i < peeked.value.length; i++) {
      if (peeked.value[i] && peeked.value[i].name === name) {
        return { kind: 'agent', settingsHref: App.router.href({ destination: 'agents', id: name }) };
      }
    }
    return { kind: 'unknown', settingsHref: null };
  }

  function gleepglorpSettings() {
    var p = App.gleepglorp.peek();
    return p.loaded && p.value ? p.value : null;
  }

  function gleepglorpEnabled() {
    var s = gleepglorpSettings();
    return !!(s && s.enabled);
  }

  // The banner sentence for a not-ready state: the table's sentence, plus the next step for the
  // off state (a stored chat can continue once it is turned on).
  function gleepglorpBanner(state) {
    var text = UNAVAILABLE[state] || 'GleepGlorp is not available.';
    return state === 'off' ? text + ' Turn it on to continue this chat.' : text;
  }

  window.App.chat.GLEEPGLORP = GLEEPGLORP;
  window.App.chat.GLEEPGLORP_STATUSES = STATUSES;
  window.App.chat.agentKind = agentKind;
  window.App.chat.gleepglorpSettings = gleepglorpSettings;
  window.App.chat.gleepglorpEnabled = gleepglorpEnabled;
  window.App.chat.gleepglorpBanner = gleepglorpBanner;
  window.App.chat.gleepglorpSentences = UNAVAILABLE;
})();
