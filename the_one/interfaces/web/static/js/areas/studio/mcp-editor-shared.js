// App.studio.mcpEditor.shared — the MCP source editor's shared constants and
// pure helpers (M31 F5 L02, split out of mcp-server-editor.js, moved verbatim).
//
// Holds: the per-key __MASKED__ sentinel, the OAuth-managed secret keys and
// hasOAuthState (the Reset-connection visibility test), formatTimeAgo, the
// spec capability keys and the stdio runtime dropdown table with its three
// lookup helpers. A stateless function namespace: no DOM, no network.
// Exposes: MASKED_SENTINEL, formatTimeAgo, hasOAuthState, SPEC_CAPABILITY_KEYS,
// STDIO_CUSTOM_SENTINEL, STDIO_RUNTIME_OPTIONS, findStdioRuntimeOption,
// deriveStdioRuntimeSelection, lookupStdioRuntimeHint.
(function () {
  'use strict';
  window.App = window.App || {};
  window.App.studio = window.App.studio || {};
  window.App.studio.mcpEditor = window.App.studio.mcpEditor || {};

  var MASKED_SENTINEL = '__MASKED__';

  // ── F9 L1 (vibing): OAuth-managed-secret-keys allowlist ─────────────
  // Mirrors the backend's `OAUTH_MANAGED_SECRET_KEYS` constant in
  // `the_one/mcp/oauth/storage.py`. Used by the Reset-connection-button
  // visibility check to detect whether a streamable-http source has any
  // OAuth state worth resetting. Keep in sync with the backend constant.
  var OAUTH_MANAGED_SECRET_KEYS = [
    'access_token',
    'refresh_token',
    'token_expires_at',
    'token_type',
    'scope',
    'dcr_credentials',
  ];

  // ── F9 L1 (vibing): inline relative-time helper ─────────────────────
  // No existing App.formatTimeAgo helper found in the codebase; this
  // ~10-LOC inline helper renders a Unix epoch (seconds) as a coarse
  // relative-time string. If a shared helper later lands in app.js or
  // utils.js, replace this and remove.
  function formatTimeAgo(epochSeconds) {
    if (typeof epochSeconds !== 'number' || !isFinite(epochSeconds)) return '';
    var diffSec = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
    if (diffSec < 60) return 'just now';
    var diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
    var diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return diffHr + ' hour' + (diffHr === 1 ? '' : 's') + ' ago';
    var diffDay = Math.floor(diffHr / 24);
    return diffDay + ' day' + (diffDay === 1 ? '' : 's') + ' ago';
  }

  // True iff the source carries any OAuth-managed secret. The masked
  // GET response strips these keys entirely (never even masked), so the
  // canonical signal is the presence of ANY managed-key string in the
  // returned secrets dict — but since the API strips them, the UI has
  // no direct read on the OAuth state. Pragmatic substitute: treat the
  // presence of `_cache` (server-written after a successful authenticated
  // /test/connect) as a strong-but-imperfect proxy. The endpoint itself
  // is idempotent on already-clean state, so a Reset click on a source
  // that has no OAuth state is harmless.
  //
  // F9 L1 (vibing) refinement: read the `oauth_active` flag the masked
  // response can carry (server adds it when any managed key is present).
  // If absent, fall back to the cache-presence proxy.
  function hasOAuthState(source) {
    if (!source || source.type !== 'streamable-http') return false;
    if (source.oauth_active === true) return true;
    var secrets = source.secrets || {};
    for (var i = 0; i < OAUTH_MANAGED_SECRET_KEYS.length; i++) {
      if (Object.prototype.hasOwnProperty.call(secrets, OAUTH_MANAGED_SECRET_KEYS[i])) {
        return true;
      }
    }
    // Fallback proxy: a populated _cache implies a successful authed
    // /test/connect happened in the past. Reset is a no-op on already-
    // clean OAuth state, so a false-positive here is harmless.
    return !!(source.config && source.config._cache);
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
      label: 'uvx (Python · PyPI lazy install)',
      hint: 'Args: package name (e.g. `mcp-server-time`). Fetched + cached on first use.',
    },
    {
      value: 'npx -y',
      label: 'npx -y (Node · npm lazy install)',
      hint: 'Args: package name (e.g. `@modelcontextprotocol/server-everything`). Fetched + cached on first use.',
    },
    {
      value: 'pipx run',
      label: 'pipx run (Python · PyPI alternative)',
      hint: 'Args: package name. Alternative to uvx.',
    },
    {
      value: 'python',
      label: 'python (pre-installed module/script)',
      hint: 'Args: `-m <module>` (module must be pip-installed) or path to script.',
    },
    {
      value: 'node',
      label: 'node (script path)',
      hint: 'Args: path to .js file inside container.',
    },
    {
      value: 'bash',
      label: 'bash (wrapper script)',
      hint: 'Args: path to shell script.',
    },
    {
      value: STDIO_CUSTOM_SENTINEL,
      label: 'Custom…',
      hint: 'Free-text mode — operator owns the command resolution. ' +
            'Common patterns: `bash /app/script.sh`, absolute paths, custom binaries on container PATH.',
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
    formatTimeAgo: formatTimeAgo,
    hasOAuthState: hasOAuthState,
    SPEC_CAPABILITY_KEYS: SPEC_CAPABILITY_KEYS,
    STDIO_CUSTOM_SENTINEL: STDIO_CUSTOM_SENTINEL,
    STDIO_RUNTIME_OPTIONS: STDIO_RUNTIME_OPTIONS,
    findStdioRuntimeOption: findStdioRuntimeOption,
    deriveStdioRuntimeSelection: deriveStdioRuntimeSelection,
    lookupStdioRuntimeHint: lookupStdioRuntimeHint
  };
})();
