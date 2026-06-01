#!/usr/bin/env bash
# run-tests.sh — self-bounding, self-cleaning pytest wrapper.
#
# Why this exists:
#   The dev container has no init/reaper (PID 1 is `uvicorn --reload`). Browser
#   tests spawn a Playwright node driver + Chromium and a per-test uvicorn
#   subprocess. If a `docker exec ... pytest` run is interrupted, the in-container
#   pytest is NOT killed and its Chromium subtree keeps running unbounded —
#   pegging a CPU core and leaving <defunct> zombies. This wrapper makes every
#   run self-bounding (wall-clock cap) and self-cleaning (group SIGKILL on
#   timeout OR on wrapper exit), so no run can orphan a subtree.
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
setsid python -m pytest "$@" &
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
