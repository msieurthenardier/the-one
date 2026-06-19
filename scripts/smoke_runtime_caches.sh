#!/usr/bin/env bash
# F9 L2 D2 smoke test — verify the generic-runtime model host-native.
#
# Runs host-native (invoked via `make smoke-runtimes` or directly).
# Verifies:
#
#   1. uvx / pipx / npx CLIs resolve on PATH
#   2. cache directories exist at the documented host paths
#   3. uvx end-to-end: `uvx mcp-server-time --help` runs (proves the
#      install pipeline works — first run fetches into the uv cache,
#      subsequent runs hit cache)
#   4. cache files actually written by step 3 (cache dir is being used)
#
# Host-native intent (M16 F03 L06): the original premise was that the
# generic-runtime caches PERSIST across `docker compose restart` (named
# volumes). Host-native there is no container restart — the caches live in
# the operator's host home (XDG / $HOME), so they persist by default. The
# check is therefore narrowed to cache-population + reuse on the host:
# step 3 populates the uv cache, step 4 confirms it. Re-running the script
# exercises the cache-hit (fast) path.
#
# Exit non-zero on any failure so `make` integration / CI can gate on it.

set -euo pipefail

UV_CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/uv"
PIPX_HOME_DIR="$HOME/.local/share/pipx"
NPM_CACHE_DIR="${npm_config_cache:-$HOME/.npm}"

echo "── F9 L2 D2 runtime smoke (host-native) ────────────────────────────"
echo ""

# Step 1: CLIs resolve.
echo "[1/4] Checking uvx / pipx / npx resolve on PATH ..."
for cmd in uvx pipx npx; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "  ✗ $cmd not found on PATH"
        exit 1
    fi
    version_line=$("$cmd" --version 2>&1 | head -n 1 || true)
    echo "  ✓ $cmd: $version_line"
done
echo ""

# Step 2: host cache dirs (created on demand by the runtimes; we just verify
# the paths are creatable / reachable).
echo "[2/4] Checking host cache directories are reachable ..."
for path in "$UV_CACHE_DIR" "$PIPX_HOME_DIR" "$NPM_CACHE_DIR"; do
    if ! mkdir -p "$path" 2>/dev/null; then
        echo "  ✗ Cannot create $path"
        exit 1
    fi
    echo "  ✓ $path reachable"
done
echo ""

# Step 3: uvx end-to-end. mcp-server-time is small and pure-compute — it's
# the canonical L2 secondary target per the leg artifact's "Cloudflare-
# state-equivalent for stdio" section.
echo "[3/4] Running 'uvx mcp-server-time --help' end-to-end ..."
echo "      (first run: fetches into $UV_CACHE_DIR; subsequent: cache-hit)"
if ! uvx mcp-server-time --help >/tmp/uvx_smoke.out 2>&1; then
    echo "  ✗ uvx invocation failed:"
    cat /tmp/uvx_smoke.out
    exit 1
fi
# `mcp-server-time --help` prints help text from the click/typer-like CLI;
# we don't assert on specific text (upstream may rewrite) — just that the
# process exited 0 and produced some output.
if [ ! -s /tmp/uvx_smoke.out ]; then
    echo "  ✗ uvx ran but produced no output"
    exit 1
fi
echo "  ✓ uvx mcp-server-time --help completed successfully"
echo ""

# Step 4: confirm cache was populated by step 3.
echo "[4/4] Verifying $UV_CACHE_DIR received cache content ..."
if [ -z "$(ls -A "$UV_CACHE_DIR" 2>/dev/null || true)" ]; then
    echo "  ✗ $UV_CACHE_DIR is empty after uvx run"
    exit 1
fi
cache_entries=$(ls "$UV_CACHE_DIR" | wc -l)
echo "  ✓ $UV_CACHE_DIR contains $cache_entries top-level entries"
echo ""

echo "── Smoke PASSED ────────────────────────────────────────────────────"
echo ""
echo "Reuse check: re-run this script — step 3 should be fast (cache-hit"
echo "against the host cache populated above)."
