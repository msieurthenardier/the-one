#!/usr/bin/env bash
# F9 L2 D2 smoke test — verify generic-runtime container model.
#
# Runs INSIDE the container (designed to be invoked via
# `docker compose exec the-one bash scripts/smoke_runtime_caches.sh` or
# directly inside an interactive shell). Verifies:
#
#   1. uvx / pipx / npx CLIs resolve on PATH (Dockerfile installed them)
#   2. cache directories exist at the documented paths (volumes mounted)
#   3. uvx end-to-end: `uvx mcp-server-time --help` runs (proves the
#      install pipeline works — first run fetches into /root/.cache/uv,
#      subsequent runs hit cache)
#   4. cache files actually written by step 3 (volume is being used)
#
# Cache PERSISTENCE-across-restart is verified by running this script
# BEFORE and AFTER `docker compose restart the-one`: step 3's second run
# will be fast if the volume persisted. The script does not run
# `docker compose restart` itself (it runs INSIDE the container; the
# operator drives the restart from the host).
#
# Exit non-zero on any failure so `make` integration / CI can gate on it.

set -euo pipefail

echo "── F9 L2 D2 runtime smoke ──────────────────────────────────────────"
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

# Step 2: cache dirs (created on demand by the runtimes; the named volumes
# mount the parent paths regardless, so we just verify the mountpoints
# resolve).
echo "[2/4] Checking cache directories are reachable ..."
for path in /root/.cache/uv /root/.local/share/pipx /root/.npm; do
    parent=$(dirname "$path")
    if ! mkdir -p "$path" 2>/dev/null; then
        echo "  ✗ Cannot create $path (volume mount failed?)"
        exit 1
    fi
    echo "  ✓ $path reachable"
done
echo ""

# Step 3: uvx end-to-end. mcp-server-time is small and pure-compute — it's
# the canonical L2 secondary target per the leg artifact's "Cloudflare-
# state-equivalent for stdio" section.
echo "[3/4] Running 'uvx mcp-server-time --help' end-to-end ..."
echo "      (first run: fetches into /root/.cache/uv; subsequent: cache-hit)"
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
echo "[4/4] Verifying /root/.cache/uv received cache content ..."
if [ -z "$(ls -A /root/.cache/uv 2>/dev/null || true)" ]; then
    echo "  ✗ /root/.cache/uv is empty after uvx run — cache volume mounted?"
    exit 1
fi
cache_entries=$(ls /root/.cache/uv | wc -l)
echo "  ✓ /root/.cache/uv contains $cache_entries top-level entries"
echo ""

echo "── Smoke PASSED ────────────────────────────────────────────────────"
echo ""
echo "Persistence check (operator drives from host):"
echo "  1. Note the timing of step 3 above (first run = slow fetch)"
echo "  2. Run: docker compose restart the-one"
echo "  3. Re-run this script — step 3 should be fast (cache-hit)"
