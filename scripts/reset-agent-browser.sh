#!/usr/bin/env bash
# reset-agent-browser.sh
#
# Automation hardening helper for agent-browser (used in Holograph verification
# and manual E2E flows). Addresses repeated SingletonLock / "Chrome exited early"
# / CDP session loss races that occur when:
#   • the same `--profile ~/.agent-browser/profiles/claude` is reused across
#     parallel subagents, or
#   • after previous runs left stale Chromium daemons / lockfiles.
#
# The project's pytest -m browser tests (tests/browser/) never hit these issues
# because they use:
#   • fresh uvicorn subprocess per test (via app_clean fixture + tmp_path)
#   • fresh Playwright BrowserContext + Page per test (see tests/browser/conftest.py)
#
# This script is the "easy reset everything" command that was missing.
#
# Usage (direct):
#   scripts/reset-agent-browser.sh                  # default: claude profile, locks only
#   scripts/reset-agent-browser.sh claude-rebuild-verify
#   FORCE=1 scripts/reset-agent-browser.sh claude   # also nuke entire dir (fresh start)
#
# Usage (via Makefile — recommended):
#   make agent-browser-clean
#   make agent-browser-clean PROFILE=claude-verify
#   make agent-browser-clean FORCE=1
#
# Safety:
#   • Never deletes the profile directory without FORCE=1 (mirrors reset-db CONFIRM=1)
#   • Idempotent — safe to run when nothing is wedged
#   • Tries graceful `agent-browser ... close --all` first
#   • Kills only processes whose command line references the target profile
#
# Lock files removed (Chromium user-data-dir convention):
#   SingletonLock, SingletonSocket, SingletonCookie, DevToolsActivePort,
#   RunningChromeVersion (and their copies under Default/ if present)
#
# Exit non-zero only on truly unexpected errors; most cleanup steps are best-effort.

set -euo pipefail

PROFILE="${1:-claude}"
FORCE="${2:-${FORCE:-0}}"

# Resolve the on-disk profile directory.
# If the argument already contains / or starts with . treat it as a literal path.
if [[ "$PROFILE" == */* || "$PROFILE" == .* ]]; then
  PROFILE_DIR="$PROFILE"
else
  PROFILE_DIR="${HOME}/.agent-browser/profiles/${PROFILE}"
fi

echo "── agent-browser profile reset ─────────────────────────────────────────"
echo "Profile name : $PROFILE"
echo "Profile dir  : $PROFILE_DIR"
echo ""

# ── Step 1: Graceful shutdown via the agent-browser CLI (if available) ────
echo "[1/5] Graceful close via agent-browser CLI ..."
if command -v agent-browser >/dev/null 2>&1; then
  # --all closes every session under that profile; ignore failure if no daemon
  if agent-browser --profile "$PROFILE" close --all >/dev/null 2>&1; then
    echo "  ✓ agent-browser close --all succeeded"
  else
    echo "  (no active daemon or close returned non-zero — safe to continue)"
  fi
else
  echo "  (agent-browser not found on \$PATH — skipping graceful close)"
fi
echo ""

# ── Step 2: Kill any orphaned Chromium / agent-browser processes ──────────
echo "[2/5] Terminating lingering browser processes for this profile ..."
# Strategy: pgrep for chrome/chromium/agent-browser, then filter those whose
# ps output mentions the profile name or the full profile dir path.
# This avoids accidentally killing the user's main Chrome.
set +e
PIDS=$(pgrep -f -i 'chrome\|chromium\|agent-browser' 2>/dev/null \
  | while read -r pid; do
      cmd=$(ps -p "$pid" -o command= 2>/dev/null || true)
      if echo "$cmd" | grep -qiE "(--user-data-dir=.*${PROFILE}|--profile[= ]*${PROFILE}|${PROFILE_DIR})"; then
        echo "$pid"
      fi
    done | tr '\n' ' ')

if [ -n "${PIDS// /}" ]; then
  echo "  Found matching PIDs: ${PIDS}"
  for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
      echo "  ✓ Killed PID $pid"
    fi
  done
  sleep 0.5
else
  echo "  ✓ No matching browser processes found"
fi

# Belt-and-suspenders broad pkill (still scoped by profile string)
pkill -9 -f "agent-browser.*${PROFILE}" 2>/dev/null || true
pkill -9 -f "chrome.*${PROFILE_DIR}" 2>/dev/null || true
set -e
echo ""

# ── Step 3: Remove the classic Chromium singleton / session lock files ────
echo "[3/5] Removing stale Singleton* lock files and session markers ..."
LOCK_CANDIDATES=(
  "$PROFILE_DIR/SingletonLock"
  "$PROFILE_DIR/SingletonSocket"
  "$PROFILE_DIR/SingletonCookie"
  "$PROFILE_DIR/DevToolsActivePort"
  "$PROFILE_DIR/RunningChromeVersion"
  # Chromium sometimes creates them under the Default/ sub-profile as well
  "$PROFILE_DIR/Default/SingletonLock"
  "$PROFILE_DIR/Default/SingletonSocket"
  "$PROFILE_DIR/Default/SingletonCookie"
  "$PROFILE_DIR/Default/DevToolsActivePort"
)

REMOVED=0
for f in "${LOCK_CANDIDATES[@]}"; do
  if [ -e "$f" ] || [ -L "$f" ]; then
    rm -f "$f" 2>/dev/null || true
    echo "  ✓ Removed $(basename "$f")"
    REMOVED=$((REMOVED + 1))
  fi
done

if [ "$REMOVED" -eq 0 ]; then
  echo "  ✓ No lock files present (already clean)"
fi
echo ""

# ── Step 4: Optional full-profile nuke (only with explicit FORCE=1) ───────
echo "[4/5] Full profile directory reset (guarded) ..."
if [ "$FORCE" = "1" ] || [ "$FORCE" = "true" ] || [ "$FORCE" = "yes" ]; then
  if [ -d "$PROFILE_DIR" ]; then
    echo "  FORCE detected — deleting entire ${PROFILE_DIR} ..."
    rm -rf "$PROFILE_DIR"
    echo "  ✓ Profile directory removed (next launch will create a pristine one)"
  else
    echo "  ✓ Profile directory did not exist"
  fi
else
  if [ -d "$PROFILE_DIR" ]; then
    echo "  Profile directory left intact (preserves cookies, localStorage, saved logins)."
    echo "  For a completely fresh profile (recommended after repeated races):"
    echo ""
    echo "      make agent-browser-clean FORCE=1"
    echo "      # or"
    echo "      FORCE=1 scripts/reset-agent-browser.sh ${PROFILE}"
    echo ""
    echo "  (This permanently deletes everything under the profile — use with care.)"
  else
    echo "  ✓ No profile directory existed"
  fi
fi
echo ""

# ── Step 5: Success message + strong guidance toward the project's test path
echo "[5/5] Reset complete."
echo ""
echo "Recommended workflow going forward:"
echo "  • Quick manual exploration:  agent-browser --profile ~/.agent-browser/profiles/claude open http://localhost:8484"
echo "  • Parallel / long verification runs: use dedicated profiles (claude-rebuild-verify, etc.)"
echo "  • Serious E2E / visual regression / HAT verification:"
echo "      make test-browser          # or  pytest -m browser tests/browser/"
echo "      make test-pixel            # visual snapshots (3 viewports)"
echo ""
echo "  The pytest browser suite spins a *fresh* uvicorn + isolated tmp_path data_dir"
echo "  + fresh Playwright BrowserContext per test — it is immune to the SingletonLock"
echo "  races that affect the long-lived Docker container + shared agent-browser profile."
echo ""
echo "  If you still see 'Chrome exited early' after this reset, try:"
echo "      agent-browser install"
echo "      # (re-downloads the headless Chromium binaries)"
echo ""
echo "── agent-browser profile reset finished ─────────────────────────────────"

exit 0
