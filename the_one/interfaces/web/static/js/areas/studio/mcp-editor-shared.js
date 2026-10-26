// App.studio.mcpEditor.shared — the MCP source editor's shared constants and
// pure helpers (M31 F5 L02, split out of mcp-server-editor.js, moved verbatim).
//
// Holds: the per-key __MASKED__ sentinel, hasOAuthState (the Reset-connection
// visibility test), the spec capability keys and the stdio runtime dropdown table with its three
// lookup helpers. A stateless function namespace: no DOM, no network.
// Exposes: MASKED_SENTINEL, hasOAuthState, SPEC_CAPABILITY_KEYS,
// STDIO_CUSTOM_SENTINEL, STDIO_RUNTIME_OPTIONS, findStdioRuntimeOption,
// deriveStdioRuntimeSelection, lookupStdioRuntimeHint.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var MASKED_SENTINEL = '__MASKED__';

  // True iff a streamable-http source holds a sign-in: the server's own `oauth_active`
  // flag (the masked GET strips the managed secrets, so this flag is the only signal).
  // The Reset connection button shows on exactly this (M31 F5 L08b, DD6); there is no
  // cache-presence fallback, because a failed Test now records `_cache.last_check` and
  // would have shown Reset on every failed server.
  function hasOAuthState(source) {
    return !!(source && source.type === 'streamable-http' && source.oauth_active === true);
  }

  // ── F8 L2: Capability flags ─────────────────────────────────────────
  // Server capability keys per the installed `mcp` SDK's ServerCapabilities
  // model. 'experimental' is intentionally excluded — it's a free-form
  // sub-namespace dict (per-server custom keys), not a typed presence flag.
  // Update this allowlist when bumping to a newer SDK that adds new typed flags.
  var SPEC_CAPABILITY_KEYS = ['tools', 'resources', 'prompts', 'logging', 'completions', 'tasks'];

  // ── F9 L2 vibing: stdio command runtime dropdown ────────────────────
  // The free-text `command` input let operators type values that would not
  // resolve at runtime (e.g. `python -m foo` when `foo` isn't pip-installed
  // inside the container). The dropdown makes the canonical "just works"
  // runtimes the path of least resistance and keeps a Custom… escape for
  // power users who need bare paths or wrapper scripts.
  //
  // `value` is the dropdown literal (also the saved `config.command` for
  // single-token runtimes). `__custom__` is the sentinel that swaps in the
  // free-text input below. `npx -y` and `pipx run` are 2-token runtimes —
  // at save time they are split into `command=<binary>, args=[<flag>,
  // ...userArgs]` (option (b) in the leg spec); the reverse split happens
  // at hydrate time so the dropdown selection round-trips and the
  // operator's chip-list shows only their own args, not the implicit
  // `-y`/`run`. The literal `npx -y` / `pipx run` is never written to
  // `config.command` — keeps the saved JSON transparent to anyone
  // inspecting it via the API, and avoids the FileNotFoundError that
  // would result if the spawn layer tried to exec a 2-token string as
  // a single binary.
  var STDIO_CUSTOM_SENTINEL = '__custom__';
  var STDIO_RUNTIME_OPTIONS = [
    {
      value: 'uvx',
      label: 'Python package (uvx)',
      hint: 'Runs a Python package from PyPI, downloaded on first use. Put the package name in Arguments.',
    },
    {
      value: 'npx -y',
      label: 'Node package (npx)',
      hint: 'Runs a Node package from npm, downloaded on first use. Put the package name in Arguments.',
    },
    {
      value: 'pipx run',
      label: 'Python package (pipx)',
      hint: 'Runs a Python package from PyPI with pipx, downloaded on first use. Put the package name in Arguments.',
    },
    {
      value: 'python',
      label: 'Python module or script',
      hint: 'Runs a Python module or script that is already installed. Put -m and the module name, or the script path, in Arguments.',
    },
    {
      value: 'node',
      label: 'Node script',
      hint: 'Runs a Node script. Put the path to the .js file in Arguments.',
    },
    {
      value: 'bash',
      label: 'Shell script',
      hint: 'Runs a shell script. Put the script path in Arguments.',
    },
    {
      value: STDIO_CUSTOM_SENTINEL,
      label: 'Other command\u2026',
      hint: 'Runs the command exactly as you type it.',
    },
  ];

  // True when `value` matches one of the canonical runtime literals (i.e.
  // not Custom). Used at hydrate time to decide whether to round-trip the
  // saved command into the dropdown vs. the Custom… free-text field.
  function findStdioRuntimeOption(value) {
    if (!value) return null;
    for (var i = 0; i < STDIO_RUNTIME_OPTIONS.length; i++) {
      var opt = STDIO_RUNTIME_OPTIONS[i];
      if (opt.value === STDIO_CUSTOM_SENTINEL) continue;
      if (opt.value === value) return opt;
    }
    return null;
  }

  // Decompose a stored (command, args) pair into (dropdownValue, displayArgs).
  // Handles the `npx -y` split (option (b)): command=npx + args[0]=-y →
  // dropdownValue='npx -y', displayArgs=args.slice(1). Same pattern for
  // `pipx run`: command=pipx + args[0]=run → dropdownValue='pipx run',
  // displayArgs=args.slice(1). Falls back to the saved literal for the
  // other single-token runtimes; everything else (bash /app/x.sh,
  // absolute paths, etc.) lands on Custom… with the raw command string
  // preserved into the free-text field.
  function deriveStdioRuntimeSelection(command, args) {
    var argsList = Array.isArray(args) ? args.slice() : [];
    var cmd = (typeof command === 'string') ? command : '';
    if (!cmd) {
      // No saved command (newly typed-in row, defensive). Caller decides
      // the default; we just report "no match".
      return { dropdownValue: '', displayArgs: argsList, customCommand: '' };
    }
    // npx -y round-trip: detect and re-collapse.
    if (cmd === 'npx' && argsList.length > 0 && argsList[0] === '-y') {
      return {
        dropdownValue: 'npx -y',
        displayArgs: argsList.slice(1),
        customCommand: '',
      };
    }
    // pipx run round-trip: detect and re-collapse.
    if (cmd === 'pipx' && argsList.length > 0 && argsList[0] === 'run') {
      return {
        dropdownValue: 'pipx run',
        displayArgs: argsList.slice(1),
        customCommand: '',
      };
    }
    var match = findStdioRuntimeOption(cmd);
    if (match) {
      return { dropdownValue: cmd, displayArgs: argsList, customCommand: '' };
    }
    // Anything else falls into Custom… with the full saved string.
    return {
      dropdownValue: STDIO_CUSTOM_SENTINEL,
      displayArgs: argsList,
      customCommand: cmd,
    };
  }

  function lookupStdioRuntimeHint(dropdownValue) {
    for (var i = 0; i < STDIO_RUNTIME_OPTIONS.length; i++) {
      if (STDIO_RUNTIME_OPTIONS[i].value === dropdownValue) {
        return STDIO_RUNTIME_OPTIONS[i].hint;
      }
    }
    return '';
  }

  window.App.studio.mcpEditor.shared = {
    MASKED_SENTINEL: MASKED_SENTINEL,
    hasOAuthState: hasOAuthState,
    SPEC_CAPABILITY_KEYS: SPEC_CAPABILITY_KEYS,
    STDIO_CUSTOM_SENTINEL: STDIO_CUSTOM_SENTINEL,
    STDIO_RUNTIME_OPTIONS: STDIO_RUNTIME_OPTIONS,
    findStdioRuntimeOption: findStdioRuntimeOption,
    deriveStdioRuntimeSelection: deriveStdioRuntimeSelection,
    lookupStdioRuntimeHint: lookupStdioRuntimeHint
  };
})();
