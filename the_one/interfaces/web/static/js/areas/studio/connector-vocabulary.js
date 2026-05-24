// App.studio.connectorVocabulary — per-connector-type display-text vocabulary (M11 F1 L6).
//
// A frontend-only lookup map that translates the substrate's neutral
// "peer / channel / guild / role" vocabulary into platform-native
// labels (e.g. Discord renders "user / channel / server / role"). The
// substrate (Pydantic models, ACL field names, routing-scope literals,
// audit-log keys) stays UNCHANGED — only the rendered display text
// varies per type. See ``flight.md`` Design Decision §6 for the
// substrate-preservation contract.
//
// Public surface:
//   App.studio.connectorVocabulary.get(type) -> entry
//     - Always returns a populated entry (never undefined).
//     - Registered types: 'discord'.
//     - Unregistered types fall back to the generic baseline, which
//       reproduces the pre-L6 "Peers / Channels / Guilds / Roles"
//       labels byte-for-byte (so existing 'stub'-type Playwright tests
//       pass unmodified at the display-text level).
//
// Entry shape:
//   {
//     peer, peers, group, groups, channel, channels, role, roles,
//     hintTone: 'native' | 'generic'
//   }
//
// Lower-case strings — call sites do their own capitalization via a
// local helper (``_capitalize`` in connector-account-editor.js). The
// ``hintTone`` flag controls whether the Allowlist hints emit the
// "Discord-flavored; ignored by other platforms" qualifier on the
// Guilds / Roles rows: drop it on a native-tone connector where the
// labels already say "Servers / Roles" (redundant noise); keep it on a
// generic-tone connector where the qualifier explains why those axes
// exist.
//
// Load order: this module attaches to ``window.App.studio`` and has no
// dependencies. ``index.html`` loads it BEFORE
// ``connector-account-editor.js``; ordering relative to the editor is
// the contract.

(function () {
  'use strict';

  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var _DEFAULT_VOCAB = {
    peer: 'peer', peers: 'peers',
    group: 'guild', groups: 'guilds',
    channel: 'channel', channels: 'channels',
    role: 'role', roles: 'roles',
    hintTone: 'generic'
  };

  var _ENTRIES = {
    discord: {
      peer: 'user', peers: 'users',
      group: 'server', groups: 'servers',
      channel: 'channel', channels: 'channels',
      role: 'role', roles: 'roles',
      hintTone: 'native'
    }
  };

  function get(type) {
    return _ENTRIES[type] || _DEFAULT_VOCAB;
  }

  window.App.studio.connectorVocabulary = { get: get };
})();
