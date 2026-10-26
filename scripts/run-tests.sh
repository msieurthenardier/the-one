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

# --- Per-area browser test lanes (F5; re-mapped to destinations in M25 F2) ---
# `--lane <lane>` runs just one slice of the browser suite. The canonical lanes
# are chats, agents, agent-tabs, library, knowledge, mcp, routing, settings, settings-tools, providers, contracts-overlay, contracts-controls and shared.
# Aliases (kept for muscle memory and older docs):
#   chat = chats, studio = agents + agent-tabs + library + knowledge + mcp,
#   system = settings + settings-tools + providers,
#   contracts = contracts-overlay + contracts-controls.
# chats/agents/agent-tabs/library/mcp/settings-tools/providers are basename-glob buckets or explicit file
# lists over tests/browser/ (`agents` is the old studio globs MINUS the library,
# mcp and agent-tabs lists). `routing` (M26 F1 L4) holds the router / leave-guard / client
# store files that used to be the long pole of `shared`. `contracts-overlay` and
# `contracts-controls` (M25 F4 L1 squawk 0117; split in M31 F3 L01) hold the `App.ui`
# control-library contract files (`test_ui_*`): overlay is an explicit list, controls the rest.
# `shared` is the COMPLEMENT (every browser test file not claimed by the named
# lanes), so the lanes' union is always exactly the whole browser suite and no
# test file can be orphaned — a newly-added test file lands in `shared` until it
# is assigned a lane glob. `tests/test_run_tests_lanes.py` pins that the lanes
# partition the suite. The lane expands to `-m browser <files…>`.
# `--list` (with `--lane`) prints the lane's file paths and exits 0.
#
# --- Parallel mode (M26 F1 L4) ---
# `--parallel N` (no --lane) runs every canonical lane as its own child
# `run-tests.sh --lane <lane>` invocation, at most N at a time, longest budget
# first. Output goes to <dir>/<lane>.log and <dir>/<lane>.xml, where <dir> is
# $TEST_LANE_DIR or a fresh mktemp -d. `--plan` (with --parallel) prints the
# schedule and exits. Run `--help` for lanes, budgets and the host policy.
#
# Cleanup contract: the parent on EXIT/INT/TERM sends TERM to every live child
# (whose own EXIT trap group-kills its pytest and watchdog), waits up to 5 s,
# then KILLs the child groups and every pgid still listed in a <lane>.pgids
# file. The parent's watchdog sends USR1 (exit 137) at TEST_TIMEOUT. A SIGKILLed
# parent cannot clean up: each child's watchdog polls RUN_TESTS_PARENT_PID every
# second and group-kills its pytest if the parent is gone. Residual window: a
# parent SIGKILLed before its first child has started its watchdog (well under a
# second) can leak that one child's pytest group.

LANE_LIST="chats|agents|agent-tabs|library|knowledge|mcp|routing|settings|settings-tools|providers|contracts-overlay|contracts-controls|shared"
CANON_LANES=(chats agents agent-tabs library knowledge mcp routing settings settings-tools providers contracts-overlay contracts-controls shared)

# Per-lane wall-clock budgets in seconds (re-measured in the M31 F5 L12 --parallel 3 run after moving the library-list file from mcp to library; earlier rows from the M31 F4 L11 run; earlier rows from the M31 F3 L09 and M31 F2 L11 --parallel 3
# gate run, plus about 25% headroom, rounded up to 30 s). Over budget is a warning, not a failure.
# QUIET-HOST RULE (squawk 0259): a budget reading counts only from a `--parallel 3` run with no
# other test process on the host (no other lanes, no unit suite, no other session's tests); a solo
# `--lane` run or a loaded host measures something else and must not move a budget.
declare -A BUDGET=(
  [chats]=450
  [agents]=540
  [agent-tabs]=360
  [library]=420
  [knowledge]=420
  [mcp]=630
  [routing]=600
  [settings]=360
  [settings-tools]=330
  [providers]=420
  [contracts-overlay]=270
  [contracts-controls]=480
  [shared]=420
)

usage() {
  cat <<EOF
usage: run-tests.sh [--lane LANE [--list]] [--parallel N [--plan]] [pytest args...]

  (no flags)          run pytest with the given args
  --lane LANE         run one browser lane ($LANE_LIST;
                      aliases: chat, studio, system, contracts)
  --list              with --lane: print the lane's files and exit
  --parallel N        run every browser lane, at most N at a time (N >= 1),
                      longest budget first; per-lane logs and junit files go to
                      \$TEST_LANE_DIR (default: a fresh mktemp -d)
  --plan              with --parallel: print the schedule and exit
  --help              this text

Lane budgets (seconds of wall time in a --parallel 3 run; over budget warns):
EOF
  local l
  for l in "${CANON_LANES[@]}"; do printf '  %-18s %ss\n' "$l" "${BUDGET[$l]}"; done
  cat <<EOF

Host policy: at most 3 browser lanes run concurrently on a local host; the
unit suite runs outside the concurrent set; a local gate and a CI build never
run at the same time. Env: TEST_TIMEOUT (seconds; default 1200, or 2400 with
--parallel, where it bounds the whole run), TEST_LANE_DIR, PYTHON, THE_ONE_TEST_NETNS, THE_ONE_REQUIRE_WEBKIT.
EOF
}

lane=""
list=0
parallel=""
plan=0
pytest_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --lane) lane="${2:-}"; shift; [[ $# -gt 0 ]] && shift ;;
    --lane=*) lane="${1#--lane=}"; shift ;;
    --list) list=1; shift ;;
    --parallel)
      parallel="${2:-}"; shift; [[ $# -gt 0 ]] && shift
      if [[ ! "$parallel" =~ ^[1-9][0-9]*$ ]]; then
        echo "run-tests.sh: --parallel needs a positive integer" >&2
        usage >&2
        exit 2
      fi ;;
    --parallel=*)
      parallel="${1#--parallel=}"; shift
      if [[ ! "$parallel" =~ ^[1-9][0-9]*$ ]]; then
        echo "run-tests.sh: --parallel needs a positive integer" >&2
        usage >&2
        exit 2
      fi ;;
    --plan) plan=1; shift ;;
    --help) usage; exit 0 ;;
    *) pytest_args+=("$1"); shift ;;
  esac
done

if [[ -n "$parallel" && -n "$lane" ]]; then
  echo "run-tests.sh: --parallel runs every lane; it cannot be combined with --lane" >&2
  usage >&2
  exit 2
fi
if [[ "$plan" -eq 1 && -z "$parallel" ]]; then
  echo "run-tests.sh: --plan needs --parallel N" >&2
  usage >&2
  exit 2
fi
# Effective TEST_TIMEOUT: an explicit caller value always wins; otherwise 1200s for
# a single run and 2400s for --parallel (the parent's cap bounds the whole run;
# children inherit the exported value).
if [[ -n "$parallel" ]]; then
  TEST_TIMEOUT="${TEST_TIMEOUT:-2400}"
else
  TEST_TIMEOUT="${TEST_TIMEOUT:-1200}"
fi
export TEST_TIMEOUT

if [[ "$list" -eq 1 && -z "$lane" ]]; then
  echo "run-tests.sh: --list needs --lane {$LANE_LIST}" >&2
  exit 2
fi

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
# Library-owned files (explicit): connectors, library focus, and the
# smaller MCP files. Each name also matches a studio glob, so it runs in this
# lane only (agents = studio minus library and mcp).
library_pat=('test_flow_studio_mcp_navigation.py' 'test_mcp_test_connection_button.py' \
             'test_studio_connector_editor.py' \
             'test_flow_studio_library_focus.py' 'test_flow_studio_library_list.py')
# Knowledge lane (M31 F3 L09, split from library when it ran 1.32x over budget): the
# knowledge-base inventory file alone, about 60% of the old library lane's time.
knowledge_pat=('test_flow_studio_knowledge_inventory.py')
# MCP lane (M26 F1 L4, split from library for balance): the MCP editor file alone
# (M31 F5 L12 moved the Library list file back to `library` when mcp ran 1.55x over budget).
mcp_pat=('test_flow_studio_mcp_editor.py')
# Today's studio globs; `agents` is these minus the library and mcp lists. The
# agents list/detail files (M25 F3 L3) are `test_flow_agents_*` and
# `test_agents_*` (`test_flow_agent_*` does not match a plural "agents").
studio_pat=('test_flow_studio_*' 'test_studio_*' 'test_mcp_*' 'test_flow_agent_*' \
            'test_flow_agents_*' 'test_agents_*')
# Agent-tabs (M31 F2 L11, squawk 0217, split from `agents` when it ran 1.3x over
# budget): the self-configuration, Rules and notes, and Tools-override files.
agent_tabs_pat=('test_studio_self_configuration_*' 'test_flow_agent_rules*' \
                'test_flow_agent_notes*' 'test_flow_studio_tools_*' \
                'test_flow_studio_tool_override*' 'test_flow_studio_time_tool.py')
# Routing (M26 F1 L4): the router, leave guard and client store files.
routing_pat=('test_router_*' 'test_nav_guard*' 'test_store*')
# Settings: the admin pages, plus the Settings item pages' list/detail file
# (M25 F3 L5b). `settings` is these globs MINUS the Built-in tools list below.
settings_all_pat=('test_flow_admin_*' 'test_flow_settings_*')
# Settings-tools (M31 F4 L11, split from `settings` when it ran 1.3x over budget): the
# Built-in tools grid, editor and shared tool-config field files, and the Settings item
# pages' list/detail, focus and visible-fix files (all of which drive the tools page).
settings_tools_pat=('test_flow_admin_tools_*' 'test_flow_admin_tool_config_fields.py' \
                    'test_flow_settings_items.py' 'test_flow_settings_focus_after.py' \
                    'test_flow_settings_visible_fixes.py')
# Providers (sortie 02): the provider editor and the Library provider group.
providers_pat=('test_flow_provider_*')
# Contracts (M25 F4 L1, squawk 0117; split in M31 F3 L01): the `App.ui` control-library
# contract files. Overlay is an explicit list; controls is `test_ui_*` minus it. No other
# lane's glob matches `test_ui_*`. `contracts` stays an alias for their union.
contracts_overlay_pat=('test_ui_modal*' 'test_ui_menu*' 'test_ui_rail*' 'test_ui_list_pane_chats*' \
  'test_ui_search_list*' 'test_ui_drawer*' 'test_ui_nav_groups*' 'test_ui_confirm*' \
  'test_ui_focus_after*' 'test_ui_dialog_rule*' 'test_ui_dialog_scroll*')
contracts_all_pat=('test_ui_*')

# Files matching the studio globs minus the library, mcp and agent-tabs lists, sorted.
agents_files() {
  comm -23 <(expand_lane "${studio_pat[@]}" | sort -u) \
           <(expand_lane "${library_pat[@]}" "${knowledge_pat[@]}" "${mcp_pat[@]}" "${agent_tabs_pat[@]}" | sort -u)
}

# Files matching the settings globs minus the settings-tools list, sorted.
settings_files() {
  comm -23 <(expand_lane "${settings_all_pat[@]}" | sort -u) \
           <(expand_lane "${settings_tools_pat[@]}" | sort -u)
}

# Files matching test_ui_* minus the overlay list, sorted.
contracts_controls_files() {
  comm -23 <(expand_lane "${contracts_all_pat[@]}" | sort -u) \
           <(expand_lane "${contracts_overlay_pat[@]}" | sort -u)
}

# Resolve lane $1 into the global array lane_files. Returns 1 for an unknown lane.
resolve_lane() {
  lane_files=()
  case "$1" in
    chats|chat)    mapfile -t lane_files < <(expand_lane "${chats_pat[@]}" | sort -u) ;;
    agents)        mapfile -t lane_files < <(agents_files) ;;
    agent-tabs)    mapfile -t lane_files < <(expand_lane "${agent_tabs_pat[@]}" | sort -u) ;;
    library)       mapfile -t lane_files < <(expand_lane "${library_pat[@]}" | sort -u) ;;
    knowledge)     mapfile -t lane_files < <(expand_lane "${knowledge_pat[@]}" | sort -u) ;;
    mcp)           mapfile -t lane_files < <(expand_lane "${mcp_pat[@]}" | sort -u) ;;
    routing)       mapfile -t lane_files < <(expand_lane "${routing_pat[@]}" | sort -u) ;;
    settings)      mapfile -t lane_files < <(settings_files) ;;
    settings-tools) mapfile -t lane_files < <(expand_lane "${settings_tools_pat[@]}" | sort -u) ;;
    providers)     mapfile -t lane_files < <(expand_lane "${providers_pat[@]}" | sort -u) ;;
    system)        mapfile -t lane_files < <(expand_lane "${settings_all_pat[@]}" "${providers_pat[@]}" | sort -u) ;;
    studio)        mapfile -t lane_files < <(expand_lane "${studio_pat[@]}" | sort -u) ;;
    contracts-overlay)  mapfile -t lane_files < <(expand_lane "${contracts_overlay_pat[@]}" | sort -u) ;;
    contracts-controls) mapfile -t lane_files < <(contracts_controls_files) ;;
    contracts)     mapfile -t lane_files < <(expand_lane "${contracts_all_pat[@]}" | sort -u) ;;
    shared)
      # Complement: all browser test files, minus the named lanes (agents +
      # library + mcp = studio_pat) and the pixel-only snapshot file (which
      # carries no @pytest.mark.browser tests).
      local _assigned _all f
      mapfile -t _assigned < <(
        expand_lane "${chats_pat[@]}" "${studio_pat[@]}" "${routing_pat[@]}" \
                    "${settings_all_pat[@]}" "${providers_pat[@]}" "${contracts_all_pat[@]}" \
                    'test_visual_snapshots.py' | sort -u)
      mapfile -t _all < <(for f in "$browser_dir/"test_*.py; do printf '%s\n' "$f"; done | sort -u)
      mapfile -t lane_files < <(comm -23 \
        <(printf '%s\n' "${_all[@]}") <(printf '%s\n' "${_assigned[@]}"))
      ;;
    *) return 1 ;;
  esac
}

# Canonical lanes ordered by budget, longest first (ties keep canonical order).
schedule_lanes() {
  local i=0 l
  for l in "${CANON_LANES[@]}"; do
    printf '%s %s %s\n' "${BUDGET[$l]}" "$i" "$l"
    i=$((i + 1))
  done | sort -k1,1nr -k2,2n | awk '{print $3}'
}

# ---------------------------------------------------------------------------
# Parallel mode
# ---------------------------------------------------------------------------
if [[ -n "$parallel" ]]; then
  mapfile -t sched < <(schedule_lanes)

  if [[ "$plan" -eq 1 ]]; then
    echo "run-tests.sh: parallel plan — up to $parallel lane(s) at a time, longest budget first"
    echo "  effective TEST_TIMEOUT=${TEST_TIMEOUT}s"
    n=1
    for l in "${sched[@]}"; do
      resolve_lane "$l" || true
      printf '  %d. %-10s budget=%ss files=%d\n' "$n" "$l" "${BUDGET[$l]}" "${#lane_files[@]}"
      n=$((n + 1))
    done
    exit 0
  fi

  # The parent's TEST_TIMEOUT (set above) bounds the whole run; children inherit
  # the same exported value, so the parent's watchdog is the binding cap.

  lane_dir="${TEST_LANE_DIR:-}"
  if [[ -z "$lane_dir" ]]; then
    lane_dir="$(mktemp -d)"
  else
    mkdir -p "$lane_dir"
  fi

  declare -A running=()     # pid -> lane
  declare -A lane_rc=()
  declare -A lane_start=()
  declare -A lane_wall=()
  queue=("${sched[@]}")
  par_watchdog=""
  summary_done=0

  alive() {
    local s
    s="$(ps -o stat= -p "$1" 2>/dev/null)" || return 1
    [[ -n "$s" && "$s" != Z* ]]
  }

  parallel_cleanup() {
    local code=$?
    trap '' INT TERM USR1
    local p f pg i any l joined
    for p in "${!running[@]}"; do kill -TERM "$p" 2>/dev/null || true; done
    for i in $(seq 50); do
      any=0
      for p in "${!running[@]}"; do
        if alive "$p"; then any=1; fi
      done
      if [[ "$any" -eq 0 ]]; then break; fi
      sleep 0.1
    done
    for p in "${!running[@]}"; do kill -KILL -- "-$p" 2>/dev/null || true; done
    for f in "${lane_dir:?}"/*.pgids; do
      [[ -e "$f" ]] || continue
      while read -r _ pg; do
        if [[ -n "$pg" ]]; then kill -KILL -- "-$pg" 2>/dev/null || true; fi
      done < "$f"
    done
    if [[ -n "$par_watchdog" ]]; then
      kill -KILL -- "-$par_watchdog" 2>/dev/null || true
    fi
    if [[ "$summary_done" -eq 0 ]]; then
      local unfinished=()
      for l in "${running[@]}" "${queue[@]}"; do unfinished+=("$l"); done
      joined="-"
      if [[ ${#unfinished[@]} -gt 0 ]]; then
        joined="$(IFS=,; echo "${unfinished[*]}")"
      fi
      echo "run-tests.sh: parallel run aborted (exit $code) after ${SECONDS}s; logs in $lane_dir"
      echo "PARALLEL_RESULT rc=$code total=${SECONDS}s lanes=${#sched[@]} failed=$joined"
    fi
    exit "$code"
  }
  trap parallel_cleanup EXIT
  trap 'exit 143' TERM
  trap 'exit 130' INT
  trap 'exit 137' USR1

  echo "run-tests.sh: parallel $parallel — ${#sched[@]} lanes; logs in $lane_dir"

  # Parent watchdog: own session, `sleep 1` loop. Exits when the parent is gone
  # (so a SIGKILLed parent leaves no orphaned sleep); at TEST_TIMEOUT sends USR1
  # to the parent and SIGKILLs it only if it is still alive 15 s later.
  setsid bash -c '
    parent=$1; limit=$2; el=0
    while kill -0 "$parent" 2>/dev/null; do
      sleep 1; el=$((el + 1))
      if (( el >= limit )); then
        kill -USR1 "$parent" 2>/dev/null || true
        for _ in $(seq 15); do
          sleep 1
          kill -0 "$parent" 2>/dev/null || exit 0
        done
        kill -KILL "$parent" 2>/dev/null || true
        exit 0
      fi
    done
  ' _ "$$" "$TEST_TIMEOUT" &
  par_watchdog=$!

  use_wait_p=0
  if (( BASH_VERSINFO[0] > 5 || (BASH_VERSINFO[0] == 5 && BASH_VERSINFO[1] >= 1) )); then
    use_wait_p=1
  fi

  launch_lane() {
    local l="${1:?}" pid
    # Clear stale per-lane files so a reused TEST_LANE_DIR cannot satisfy the
    # missing-junit rule with an old file.
    rm -f "${lane_dir:?}/${l}.xml" "${lane_dir:?}/${l}.log" \
          "${lane_dir:?}/${l}.pgids" "${lane_dir:?}/${l}.pgids.parent-died"
    RUN_TESTS_PARENT_PID="$$" RUN_TESTS_PGID_FILE="$lane_dir/$l.pgids" \
      setsid bash "$0" --lane "$l" -p no:cacheprovider "${pytest_args[@]}" \
        --junitxml="$lane_dir/$l.xml" > "$lane_dir/$l.log" 2>&1 &
    pid=$!
    running[$pid]="$l"
    lane_start[$l]=$SECONDS
    echo "run-tests.sh: started $l (pid $pid) at +${SECONDS}s"
  }

  while [[ ${#queue[@]} -gt 0 || ${#running[@]} -gt 0 ]]; do
    while [[ ${#queue[@]} -gt 0 && ${#running[@]} -lt $parallel ]]; do
      launch_lane "${queue[0]}"
      queue=("${queue[@]:1}")
    done
    if [[ ${#running[@]} -eq 0 ]]; then break; fi

    done_pid=""
    rc=0
    if [[ "$use_wait_p" -eq 1 ]]; then
      wait -n -p done_pid "${!running[@]}" || rc=$?
    else
      while [[ -z "$done_pid" ]]; do
        for p in "${!running[@]}"; do
          if ! alive "$p"; then done_pid="$p"; break; fi
        done
        if [[ -z "$done_pid" ]]; then sleep 0.5; fi
      done
      wait "$done_pid" || rc=$?
    fi
    # An empty done_pid means the wait was interrupted by a trapped signal.
    if [[ -z "$done_pid" ]]; then continue; fi
    l="${running[$done_pid]}"
    unset "running[$done_pid]"
    lane_rc[$l]=$rc
    lane_wall[$l]=$((SECONDS - lane_start[$l]))
    echo "run-tests.sh: finished $l rc=$rc wall=${lane_wall[$l]}s"
  done

  # --- Summary and exit code (deterministic: schedule order) ---
  final=0
  timeout_seen=0
  failed=()
  echo ""
  echo "run-tests.sh: parallel summary (logs in $lane_dir)"
  for l in "${sched[@]}"; do
    rc="${lane_rc[$l]}"
    note=""
    if [[ "$rc" -eq 137 || "$rc" -eq 143 ]]; then
      timeout_seen=1
      note=" (timeout or killed)"
    fi
    if [[ "$rc" -eq 0 && ! -s "$lane_dir/$l.xml" ]]; then
      rc=1
      note=" (junit xml missing or empty)"
    fi
    if [[ "$rc" -ne 0 ]]; then
      failed+=("$l")
      if [[ "$final" -eq 0 ]]; then final="$rc"; fi
    fi
    over=""
    if [[ "${lane_wall[$l]}" -gt "${BUDGET[$l]}" ]]; then over="  OVER BUDGET"; fi
    printf '  %-10s rc=%-3s wall=%4ss budget=%ss%s%s\n' \
      "$l" "$rc" "${lane_wall[$l]}" "${BUDGET[$l]}" "$over" "$note"
  done
  if [[ "$timeout_seen" -eq 1 ]]; then final=137; fi
  failed_str="-"
  if [[ ${#failed[@]} -gt 0 ]]; then failed_str="$(IFS=,; echo "${failed[*]}")"; fi
  echo "run-tests.sh: total wall ${SECONDS}s; logs in $lane_dir"
  echo "PARALLEL_RESULT rc=$final total=${SECONDS}s lanes=${#sched[@]} failed=$failed_str"
  summary_done=1
  exit "$final"
fi

# ---------------------------------------------------------------------------
# Single run (plain pytest, or one lane)
# ---------------------------------------------------------------------------
if [[ -n "$lane" ]]; then
  if ! resolve_lane "$lane"; then
    echo "run-tests.sh: unknown lane '$lane' (want: $LANE_LIST; aliases: chat|studio|system|contracts)" >&2
    exit 2
  fi

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
pgid_file="${RUN_TESTS_PGID_FILE:-}"

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
  # Only a crashed or still-live lane leaves its pgid record behind.
  if [[ -n "$pgid_file" ]]; then
    rm -f "${pgid_file:?}"
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
if [[ -n "$pgid_file" ]]; then printf 'pytest %s\n' "$pgid" >> "$pgid_file"; fi

# Watchdog: a `sleep 1` loop under its OWN setsid, so the watchdog bash is a
# process-group leader (PID == PGID) whose `sleep` child shares its group and
# can be group-killed below (a bare kill of the bash would orphan the sleep to
# PID 1). It kills the pytest group at TEST_TIMEOUT. When run as a parallel
# child (RUN_TESTS_PARENT_PID set) it also checks every second that the parent
# is alive; if the parent is gone (SIGKILLed) it writes a marker and
# group-kills pytest, so children never outlive a SIGKILLed parent.
parent_marker=""
if [[ -n "$pgid_file" ]]; then parent_marker="$pgid_file.parent-died"; fi
setsid bash -c '
  pg=$1; limit=$2; par=$3; marker=$4; el=0
  while :; do
    sleep 1; el=$((el + 1))
    kill -0 -- "-$pg" 2>/dev/null || exit 0
    if [[ -n "$par" ]] && ! kill -0 "$par" 2>/dev/null; then
      [[ -n "$marker" ]] && : > "$marker"
      kill -KILL -- "-$pg" 2>/dev/null || true
      exit 0
    fi
    if (( el >= limit )); then
      kill -KILL -- "-$pg" 2>/dev/null || true
      exit 0
    fi
  done
' _ "$pgid" "$TEST_TIMEOUT" "${RUN_TESTS_PARENT_PID:-}" "$parent_marker" &
watchdog=$!
if [[ -n "$pgid_file" ]]; then printf 'watchdog %s\n' "$watchdog" >> "$pgid_file"; fi

# Wait for the pytest group leader and capture its real exit status.
rc=0
wait "$pgid" || rc=$?

# Tear down the watchdog. Group-kill (`-$watchdog`) so the watchdog bash AND
# its `sleep` child are both reaped — a bare `kill "$watchdog"` would signal
# only the bash, leaving the sleep to reparent to PID 1 and linger.
kill -KILL "-$watchdog" 2>/dev/null || true
wait "$watchdog" 2>/dev/null || true
watchdog=""

# rc 137 == 128+SIGKILL: the watchdog reaped us at the cap (or the parent died).
if [[ "$rc" -eq 137 ]]; then
  if [[ -n "$parent_marker" && -e "$parent_marker" ]]; then
    echo "run-tests.sh: parent process gone — killed process group" >&2
  else
    timed_out=1
  fi
fi

if [[ "$timed_out" -eq 1 ]]; then
  echo "run-tests.sh: TIMEOUT after ${TEST_TIMEOUT}s — killed process group" >&2
fi

# pgid already reaped by `wait`; clear it so the EXIT trap is a no-op on the
# normal path (and a safety net if anything lingers).
exit "$rc"
