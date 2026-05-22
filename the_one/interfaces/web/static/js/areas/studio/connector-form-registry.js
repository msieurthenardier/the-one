// App.studio.connectorFormRegistry — per-type form-field registry (M11 F1 L3).
//
// A substrate-level abstraction so connector-account-editor.js can
// dispatch typed form rendering and form-data collection per connector
// type without hardcoded `if (type === 'discord')` branches. Each
// connector type that wants a typed form registers an entry here at
// module load time. The connector-account editor consults the registry
// at render and collect time; unregistered types fall back to the
// generic kv-table render path (the `'stub'` test-only carve-out and
// any future-type-with-no-UI path remain on the fallback).
//
// M11 mission constraint: the registry shape must not close design
// space for the second connector. Single-method-per-section render
// hooks + a structured `{config, secrets}` return from `collect` keep
// DOM coupling local to each entry and stitching local to the
// substrate.
//
// Public surface:
//   App.studio.connectorFormRegistry.register(type, entry)
//     - type: non-empty string (must equal entry.type).
//     - entry: {
//         type: string,
//         renderConnectionFields: function(account, isCreate) -> string,
//         renderCredentialsFields: function(account) -> string,
//         collect: function(container, account, isEdit) -> {config, secrets},
//         reservedConfigKeys: string[]
//       }
//     - Validates the shape at call time; missing or wrong-type fields
//       raise TypeError naming the offending field.
//     - Double-register on the same type emits a console.warn and
//       overwrites the prior entry (last-writer-wins).
//
//   App.studio.connectorFormRegistry.get(type)
//     - Returns the entry registered for `type`, or undefined if none.
//     - Never throws.
//
// L3 ships the substrate ONLY — no entries are registered here. L4
// will land the Discord entry as the first consumer; the existing
// `'stub'`-type Playwright tests exercise the fallback path (no entry
// → generic kv-table render unchanged).

(function () {
  'use strict';

  window.App = window.App || {};
  window.App.studio = window.App.studio || {};

  var _entries = {};

  function _validateEntry(type, entry) {
    if (!entry || typeof entry !== 'object') {
      throw new TypeError(
        'connectorFormRegistry.register: entry must be an object; got ' +
          (entry === null ? 'null' : typeof entry)
      );
    }
    if (entry.type !== type) {
      throw new TypeError(
        "connectorFormRegistry.register: entry.type must equal the registered key '" +
          type + "'; got " + JSON.stringify(entry.type)
      );
    }
    var requiredFns = ['renderConnectionFields', 'renderCredentialsFields', 'collect'];
    for (var i = 0; i < requiredFns.length; i++) {
      if (typeof entry[requiredFns[i]] !== 'function') {
        throw new TypeError(
          "connectorFormRegistry.register: entry." + requiredFns[i] +
            " must be a function for type '" + type + "'"
        );
      }
    }
    if (!Array.isArray(entry.reservedConfigKeys)) {
      throw new TypeError(
        "connectorFormRegistry.register: entry.reservedConfigKeys must be an array for type '" +
          type + "'"
      );
    }
    // M11 F1 L4: ``snapshot`` and ``wireEvents`` are OPTIONAL — if
    // present they MUST be functions. The dirty-tracker (in
    // ``connector-account-editor.js:getFormSnapshot`` /
    // ``wireEditorEvents``) consults the registered entry for these
    // hooks so a per-type form with bare typed inputs (raw checkboxes,
    // ``<select>`` outside ``.editor-section .field-select``, etc.) can
    // participate in dirty-state without forcing the substrate to
    // dispatch per-input-type. The 4 required functions +
    // ``reservedConfigKeys`` array above stay REQUIRED.
    // M11 F1 L5 extends the optional set with ``renderInviteSection``: an
    // entry-provided hook that returns the HTML for the per-type Invite
    // section mounted in the General tab between Test Connection and
    // Danger Zone. Absent → no invite section renders (the ``'stub'``
    // fallback path and any future-type-with-no-invite-helper).
    // M11 F2 L4 extends the optional set with ``renderDirectiveSection``:
    // an entry-provided hook that returns the HTML for the per-type
    // System Prompt Directive section mounted on the General tab
    // between Pairing and Attached Agents. Absent → no directive
    // section renders (the ``'stub'`` fallback path and any
    // future-type-with-no-directive-surface).
    var optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection'];
    for (var oi = 0; oi < optionalFns.length; oi++) {
      var ofn = optionalFns[oi];
      if (entry[ofn] !== undefined && typeof entry[ofn] !== 'function') {
        throw new TypeError(
          "connectorFormRegistry.register: entry." + ofn +
            " must be a function if present for type '" + type + "'"
        );
      }
    }
  }

  function register(type, entry) {
    if (typeof type !== 'string' || !type) {
      throw new TypeError('connectorFormRegistry.register: type must be a non-empty string');
    }
    _validateEntry(type, entry);
    if (_entries[type] !== undefined) {
      // Last-writer-wins; surface accidental double-registration via warn.
      try {
        console.warn('App.studio.connectorFormRegistry: re-registering type ' + type);
      } catch (e) { /* console may be missing in some test envs */ }
    }
    _entries[type] = entry;
  }

  function get(type) {
    return _entries[type];
  }

  window.App.studio.connectorFormRegistry = {
    register: register,
    get: get
  };

  // M11 F2 L4: shared masked-edit sentinel hoisted from per-module
  // duplicates in ``connector-account-editor.js`` and
  // ``connector-form-discord.js``. The studio's earliest-loading module
  // is the registry IIFE, so setting the constant here makes it
  // available to both editor + form-discord modules at their own
  // module-load time. Value is the same ``'__MASKED__'`` sentinel the
  // backend ``api.py`` honors per-secret-key for round-trip preservation.
  window.App.studio.MASKED_SENTINEL = '__MASKED__';
})();
