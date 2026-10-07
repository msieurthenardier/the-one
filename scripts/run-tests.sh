#!/usr/bin/env bash
# run-tests.sh — self-bounding, self-cleaning pytest wrapper.
#
# Why this exists:
#   Browser tests spawn a Playwright node driver + Chromium and a per-test
#   uvicorn subprocess. If a host-native pytest run is interrupted (Ctrl-C, an
#   agent's tool timeout, a killed shell), pytest's spawned Chromium subtree can
#   keep running unbounded — pegging a CPU core and leaving <defunct> zombies.
#   This wrapper makes every run self-bounding (wall-clock cap) and self-cleaning
#   (group SIGKILL on timeout OR on wrapper exit), so no run can orphan a subtree.
#
# Mechanism:
#   pytest runs in its OWN process group via `setsid`. All descendants
#   (pytest, conftest-spawned uvicorn, playwright node driver, chromium) inherit
#   that group. A plain `timeout`/single-pid kill does NOT reap grandchildren;
#   we kill the entire process GROUP (`kill -KILL -$pgid`), which does.
#
# Exit code: propagates pytest's real exit code (137 if timeout-killed).
set -euo pipefail

TEST_TIMEOUT="${TEST_TIMEOUT:-1200}"

# --- Per-area browser test lanes (F5; re-mapped to destinations in M25 F2) ---
# `--lane {chats|agents|library|settings|contracts|shared}` runs just one
# slice of the browser suite so a verification pass need not pay the full
# ~38min tax (the six lanes summed, M25 F4). Aliases (kept for muscle memory
# and older docs):
#   chat = chats, studio = agents + library, system = settings.
# chats/agents/library/settings are the four destination lanes: basename-glob
# buckets over tests/browser/ (`library` is an explicit file list; `agents` is
# the old studio globs MINUS that list). `contracts` (M25 F4 L1, squawk 0117)
# holds the `App.ui` control-library contract files (`test_ui_*`), so the
# dual-engine contracts run without paying for the `shared` lane. `shared` is
# the COMPLEMENT (every browser test file not claimed by the five named
# lanes), so the six lanes' union is always exactly the whole browser suite
# and no test file can be orphaned — a newly-added test file lands in `shared`
# until it is assigned a lane glob. `tests/test_run_tests_lanes.py` pins that
# the six lanes partition the suite. Implemented hand-rolled (no new deps):
# the lane expands to `-m browser <files…>`, mirroring `make test-browser`
# semantics.
# `--list` (with `--lane`) prints the lane's file paths, one per line, and
# exits 0 without running pytest.
# See CLAUDE.md "Per-area browser test lanes" for usage.
lane=""
list=0
pytest_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lane) lane="${2:-}"; shift; [[ $# -gt 0 ]] && shift ;;
    --lane=*) lane="${1#--lane=}"; shift ;;
    --list) list=1; shift ;;
    *) pytest_args+=("$1"); shift ;;
  esac
done

if [[ "$list" -eq 1 && -z "$lane" ]]; then
  echo "run-tests.sh: --list needs --lane {chats|agents|library|settings|contracts|shared}" >&2
  exit 2
fi

if [[ -n "$lane" ]]; then
  browser_dir="tests/browser"
  shopt -s nullglob

  # Expand basename glob patterns ($@) into existing file paths under browser_dir.
  expand_lane() {
    local p f
    for p in "$@"; do
      for f in "$browser_dir/"$p; do
        [[ -e "$f" ]] && printf '%s\n' "$f"
      done
    done
  }

  # Area lane globs. Files are cleanly area-prefixed; patterns stay single-
  # quoted so the '*' survives array storage and expands only in expand_lane.
  chats_pat=('test_flow_chat*' 'test_flow_markdown_chat.py' 'test_flow_new_chat.py' \
             'test_flow_streaming.py' 'test_flow_context_overlay_thresholds.py' \
             'test_flow_usage_restore.py' 'test_chats_helper.py')
  # Library-owned files (explicit): knowledge inventory, MCP servers,
  # connectors, and the Library list (M25 F3 L4a). Each name also matches a
  # studio glob, so it runs in this lane only (agents = studio minus these).
  library_pat=('test_flow_studio_knowledge_inventory.py' 'test_flow_studio_mcp_editor.py' \
               'test_flow_studio_mcp_navigation.py' 'test_mcp_test_connection_button.py' \
               'test_studio_connector_editor.py' 'test_flow_studio_library_list.py' \
               'test_flow_studio_library_focus.py')
  # Today's studio globs; `agents` is these minus the Library list. The
  # agents list/detail files (M25 F3 L3) are `test_flow_agents_*` and
  # `test_agents_*` (`test_flow_agent_*` does not match a plural "agents").
  studio_pat=('test_flow_studio_*' 'test_studio_*' 'test_mcp_*' 'test_flow_agent_*' \
              'test_flow_agents_*' 'test_agents_*')
  # Settings: the admin pages and the provider editor, plus the Settings item
  # pages' list/detail file (M25 F3 L5b).
  settings_pat=('test_flow_admin_*' 'test_flow_provider_*' 'test_flow_settings_*')
  # Contracts: the `App.ui` control-library contract files (M25 F4 L1,
  # squawk 0117). No other lane's glob matches `test_ui_*`.
  contracts_pat=('test_ui_*')

  # Files matching $@ (globs) minus files matching library_pat, sorted.
  agents_files() {
    comm -23 <(expand_lane "${studio_pat[@]}" | sort -u) \
             <(expand_lane "${library_pat[@]}" | sort -u)
  }

  lane_files=()
  case "$lane" in
    chats|chat)    mapfile -t lane_files < <(expand_lane "${chats_pat[@]}" | sort -u) ;;
    agents)        mapfile -t lane_files < <(agents_files) ;;
    library)       mapfile -t lane_files < <(expand_lane "${library_pat[@]}" | sort -u) ;;
    settings|system) mapfile -t lane_files < <(expand_lane "${settings_pat[@]}" | sort -u) ;;
    studio)        mapfile -t lane_files < <(expand_lane "${studio_pat[@]}" | sort -u) ;;
    contracts)     mapfile -t lane_files < <(expand_lane "${contracts_pat[@]}" | sort -u) ;;
    shared)
      # Complement: all browser test files, minus the five named lanes
      # (agents + library = studio_pat) and the pixel-only snapshot file
      # (which carries no @pytest.mark.browser tests).
      mapfile -t _assigned < <(
        expand_lane "${chats_pat[@]}" "${studio_pat[@]}" "${settings_pat[@]}" \
                    "${contracts_pat[@]}" 'test_visual_snapshots.py' | sort -u)
      mapfile -t _all < <(for f in "$browser_dir/"test_*.py; do printf '%s\n' "$f"; done | sort -u)
      mapfile -t lane_files < <(comm -23 \
        <(printf '%s\n' "${_all[@]}") <(printf '%s\n' "${_assigned[@]}"))
      ;;
    *)
      echo "run-tests.sh: unknown lane '$lane' (want: chats|agents|library|settings|contracts|shared; aliases: chat|studio|system)" >&2
      exit 2
      ;;
  esac

  if [[ ${#lane_files[@]} -eq 0 ]]; then
    echo "run-tests.sh: lane '$lane' matched no test files" >&2
    exit 2
  fi

  if [[ "$list" -eq 1 ]]; then
    printf '%s\n' "${lane_files[@]}"
    exit 0
  fi

  echo "run-tests.sh: lane '$lane' — ${#lane_files[@]} browser test file(s)" >&2
  set -- -m browser "${lane_files[@]}" "${pytest_args[@]}"
else
  set -- "${pytest_args[@]}"
fi

pgid=""
watchdog=""
timed_out=0

# Defensive cleanup: if the wrapper exits for ANY reason (normal, signal,
# error), SIGKILL the whole process group so nothing is left behind. Also
# group-kill the watchdog so its `sleep` child can't reparent to PID 1 and
# linger (holding inherited fds, e.g. a pipe write-end) for the full timeout.
cleanup() {
  if [[ -n "$pgid" ]] && kill -0 "-$pgid" 2>/dev/null; then
    kill -KILL "-$pgid" 2>/dev/null || true
  fi
  if [[ -n "$watchdog" ]]; then
    kill -KILL "-$watchdog" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Launch pytest in its own session/process group. setsid makes the child a
# process-group leader whose PID == PGID, so we can signal the whole tree.
if [[ "${THE_ONE_TEST_NETNS:-}" == "1" ]]; then
  # Opt-in loopback-only network namespace (WSL2 mirrored networking reflects
  # Windows' rotating IPv6 addresses; Chromium's NetworkChangeNotifier then
  # aborts in-flight loopback requests with ERR_NETWORK_CHANGED). Fail loudly
  # rather than silently running un-isolated.
  if ! unshare -rn sh -c 'ip link set lo up' >/dev/null 2>&1; then
    echo "run-tests.sh: THE_ONE_TEST_NETNS=1 but 'unshare -rn' + 'ip link set lo up' is unavailable here (need util-linux unshare, iproute2 ip, and unprivileged user namespaces). Unset THE_ONE_TEST_NETNS to run without isolation." >&2
    exit 2
  fi
  echo "run-tests.sh: running pytest in an isolated loopback-only network namespace" >&2
  setsid unshare -rn sh -c 'ip link set lo up && exec "$@"' sh \
    "${PYTHON:-python3}" -m pytest "$@" &
else
  setsid "${PYTHON:-python3}" -m pytest "$@" &
fi
pgid=$!

# Watchdog: kill the pytest group if it outlives the cap. Run it under its OWN
# setsid so the watchdog bash is a process-group leader (PID == PGID) whose
# `sleep` child shares its group. That lets us group-kill the watchdog below —
# reaping BOTH the bash and the sleep — instead of just the bash PID (which
# would orphan the sleep to PID 1, where it lingers holding inherited fds).
setsid bash -c "
  sleep \"$TEST_TIMEOUT\"
  if kill -0 \"-$pgid\" 2>/dev/null; then
    kill -KILL \"-$pgid\" 2>/dev/null || true
  fi
" &
watchdog=$!

# Wait for the pytest group leader and capture its real exit status.
rc=0
wait "$pgid" || rc=$?

# Tear down the watchdog. Group-kill (`-$watchdog`) so the watchdog bash AND
# its `sleep` child are both reaped — a bare `kill "$watchdog"` would signal
# only the bash, leaving the sleep to reparent to PID 1 and linger.
kill -KILL "-$watchdog" 2>/dev/null || true
wait "$watchdog" 2>/dev/null || true
watchdog=""

# rc 137 == 128+SIGKILL: the watchdog reaped us at the cap.
if [[ "$rc" -eq 137 ]]; then
  timed_out=1
fi

if [[ "$timed_out" -eq 1 ]]; then
  echo "run-tests.sh: TIMEOUT after ${TEST_TIMEOUT}s — killed process group" >&2
fi

# pgid already reaped by `wait`; clear it so the EXIT trap is a no-op on the
# normal path (and a safety net if anything lingers).
exit "$rc"
