// App.studio.connectorFormRegistry — per-type form-field registry (M11 F1 L3).
//
// A substrate-level abstraction so connector-editor.js can
// dispatch typed form rendering and form-data collection per connector
// type without hardcoded `if (type === 'discord')` branches. Each
// connector type that wants a typed form registers an entry here at
// module load time. The connector editor consults the registry
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
//
// ## Optional Hooks (each function-if-present per `_validateEntry`)
//
// Each connector-form-registry entry MAY expose any of the five
// optional hooks below. Absent → the substrate's default (chip-list /
// generic kv-table / no section render) applies. Each hook is
// independently opt-in; entries pick the surfaces they need.
//
// - snapshot(container) → object: per-type typed-state snapshot for
//   the dirty-tracker (F1 L4).
// - wireEvents(container, checkDirty, account) → void: per-type
//   listener wiring outside the substrate's delegation (F1 L4).
// - renderInviteSection(account) → string: per-type HTML returned as
//   WRAPPER-LESS content (no ``<section class="editor-section">``, no
//   section-title) and embedded INSIDE the Connection section of the
//   connector account editor (F1 L5; M11 F5 L2 MCP-parity refactor
//   moved the embed inside Connection — the registry contract is
//   unchanged, only the returned HTML shape).
// - renderDirectiveSection: REMOVED in M11 F5 L6 HAT round-8.
//   The per-type per-account directive surface (M11 F2 L4) was retired
//   when mission criterion #14 was reverted; the read-only effective-
//   directive surface now lives under the Auto-reply toggle in the
//   Session section of the substrate (``connector-editor.js``)
//   and is type-agnostic — no registry hook needed.
// - renderDiscoverableDropdown(account, axis, currentValues, vocab,
//   onChange) → HTMLElement | null: per-type axis-specific live-data
//   dropdown for the allowlist + routing-rules editors (F3 L5; absent
//   → consumers fall back to the chip-list editor).
// - renderRuntimeConfigFields(account) → string: per-type
//   runtime-config content (event types received, servers scoped,
//   presence status, etc.) returned as WRAPPER-LESS HTML. The
//   substrate (``connector-editor.js``) mounts the returned
//   content inside an ``editor-section`` with section-title "Runtime
//   Config" on the Access-and-Routing tab, between Lifecycle and
//   Allowlist (F5 L3). Absent → no Runtime Config section renders.

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
    // ``connector-editor.js:getFormSnapshot`` /
    // ``wireEditorEvents``) consults the registered entry for these
    // hooks so a per-type form with bare typed inputs (raw checkboxes,
    // ``<select>`` outside ``.editor-section .field-select``, etc.) can
    // participate in dirty-state without forcing the substrate to
    // dispatch per-input-type. The 4 required functions +
    // ``reservedConfigKeys`` array above stay REQUIRED.
    // M11 F1 L5 extends the optional set with ``renderInviteSection``: an
    // entry-provided hook that returns the per-type Invite block as
    // WRAPPER-LESS HTML content (no outer ``<section class="editor-section">``,
    // no section-title). The connector account editor embeds the
    // returned content INSIDE the Connection section, beneath the
    // Test Connection footer-row (M11 F5 L2 MCP-parity refactor mirrors
    // mcp-server-editor.js's mcp-test-row placement; pre-L2 the hook
    // returned a full ``<section class="editor-section">`` mounted
    // between Test Connection and Danger Zone). Absent → no invite
    // block renders (the ``'stub'`` fallback path and any
    // future-type-with-no-invite-helper).
    // M11 F2 L4's ``renderDirectiveSection`` hook was REMOVED in
    // M11 F5 L6 HAT round-8 (mission criterion #14 reverted). The
    // entry-provided per-account System Prompt Directive surface is
    // gone; the substrate now renders a read-only effective-directive
    // codeblock under the Auto-reply toggle in the Session section,
    // type-agnostic (no per-type override).
    // M11 F3 L5 extends the optional set with ``renderDiscoverableDropdown``:
    // ``renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange)
    // → HTMLElement | null`` is the entry's opt-in for the live-data
    // discoverable-dropdown component shipped by F3 (combobox shape
    // backed by the ``GET /api/connectors/{id}/discoverable-entities``
    // endpoint). Absent → consumers (allowlist + routing-rules editors
    // in L6) fall back to the existing chip-list editor. The 5th hook
    // preserves the flat-array ``optionalFns`` shape per the F2 debrief
    // operator decision (no object-map restructure at n=5).
    // M11 F5 L3 extends the optional set with ``renderRuntimeConfigFields``:
    // ``renderRuntimeConfigFields(account) → string`` is the entry's
    // hook for per-type runtime-config content (event types received,
    // servers scoped, presence status, etc.). When present, the
    // substrate (``connector-editor.js``) mounts the returned
    // HTML inside a ``<div class="editor-section"><div
    // class="section-title">Runtime Config</div>...</div>`` on the
    // Access-and-Routing tab, between Lifecycle and Allowlist. The
    // returned content is WRAPPER-LESS (same shape as
    // ``renderInviteSection`` post-F5 L2): the substrate owns the
    // section wrapper + section-title; the entry owns the inner
    // markup. Absent → no Runtime Config section renders (the
    // ``'stub'`` fallback path and any future-type-with-no-runtime-config).
    var optionalFns = [
      'snapshot',
      'wireEvents',
      'renderInviteSection',
      // ``renderDirectiveSection`` REMOVED in M11 F5 L6 HAT round-8.
      'renderDiscoverableDropdown',
      'renderRuntimeConfigFields'
    ];
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
  // duplicates in ``connector-editor.js`` and
  // ``connector-form-discord.js``. The studio's earliest-loading module
  // is the registry IIFE, so setting the constant here makes it
  // available to both editor + form-discord modules at their own
  // module-load time. Value is the same ``'__MASKED__'`` sentinel the
  // backend ``api.py`` honors per-secret-key for round-trip preservation.
  window.App.studio.MASKED_SENTINEL = '__MASKED__';
})();
