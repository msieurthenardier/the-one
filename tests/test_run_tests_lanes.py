"""The browser test lanes partition the browser suite (M25 F4 L1, squawk 0117).

`scripts/run-tests.sh --lane <lane> --list` prints a lane's files and exits
without running pytest. This test lists every lane and asserts the lanes are
pairwise disjoint and that their union is every `tests/browser/test_*.py`
except the pixel-only `test_visual_snapshots.py`. `shared` is computed as the
complement of the named lanes, so a new file always lands somewhere; the
disjointness check is what catches a glob that claims a file twice.
"""

from __future__ import annotations

import itertools
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "run-tests.sh"
LANES = ("chats", "agents", "library", "mcp", "routing", "settings", "contracts", "shared")


def _list(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _lane_files(lane: str) -> set[str]:
    proc = _list("--lane", lane, "--list")
    assert proc.returncode == 0, f"--lane {lane} --list exited {proc.returncode}: {proc.stderr}"
    files = [line for line in proc.stdout.splitlines() if line.strip()]
    assert files, f"lane {lane!r} listed no files"
    assert len(files) == len(set(files)), f"lane {lane!r} lists a file twice"
    return set(files)


@pytest.fixture(scope="module")
def lanes() -> dict[str, set[str]]:
    return {lane: _lane_files(lane) for lane in LANES}


def test_lanes_are_pairwise_disjoint(lanes: dict[str, set[str]]) -> None:
    for a, b in itertools.combinations(LANES, 2):
        both = lanes[a] & lanes[b]
        assert not both, f"lanes {a!r} and {b!r} both claim {sorted(both)}"


def test_lanes_union_is_the_browser_suite(lanes: dict[str, set[str]]) -> None:
    every = {
        f"tests/browser/{p.name}"
        for p in (REPO / "tests" / "browser").glob("test_*.py")
        if p.name != "test_visual_snapshots.py"
    }
    union = set().union(*lanes.values())
    assert union == every, (
        f"missing from every lane: {sorted(every - union)}; "
        f"listed but not a browser test file: {sorted(union - every)}"
    )


def test_contracts_lane_is_exactly_the_ui_contract_files(lanes: dict[str, set[str]]) -> None:
    ui = {f"tests/browser/{p.name}" for p in (REPO / "tests" / "browser").glob("test_ui_*.py")}
    assert lanes["contracts"] == ui
    assert not (lanes["shared"] & ui)


def test_list_without_lane_exits_2() -> None:
    proc = _list("--list")
    assert proc.returncode == 2
    assert "--list needs --lane" in proc.stderr
    assert proc.stdout == ""


def test_list_with_unknown_lane_exits_2_naming_every_lane() -> None:
    proc = _list("--lane", "no-such-lane", "--list")
    assert proc.returncode == 2
    assert "chats|agents|library|mcp|routing|settings|contracts|shared" in proc.stderr
    assert proc.stdout == ""


# --- Parallel mode (M26 F1 L4) ---


def test_parallel_argument_errors_exit_2() -> None:
    for args in (
        ["--parallel", "3", "--lane", "chats"],
        ["--parallel", "0"],
        ["--parallel", "many"],
        ["--parallel"],
        ["--parallel", "--plan"],
        ["--plan"],
        ["--plan", "--lane", "chats"],
    ):
        proc = _list(*args)
        assert proc.returncode == 2, f"{args} exited {proc.returncode}"


def _plan(*args: str) -> list[tuple[str, int]]:
    proc = _list("--parallel", "3", "--plan", *args)
    assert proc.returncode == 0, proc.stderr
    rows = re.findall(r"^\s*\d+\.\s+(\S+)\s+budget=(\d+)s", proc.stdout, re.M)
    return [(name, int(sec)) for name, sec in rows]


def test_plan_lists_every_canonical_lane_once_with_a_numeric_budget() -> None:
    rows = _plan()
    names = [n for n, _ in rows]
    assert sorted(names) == sorted(LANES)
    assert all(sec > 0 for _, sec in rows)
    budgets = [sec for _, sec in rows]
    assert budgets == sorted(budgets, reverse=True), "longest budget first"


def _plan_timeout(**env: str) -> str:
    base = {k: v for k, v in os.environ.items() if k != "TEST_TIMEOUT"}
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--parallel", "3", "--plan"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        env={**base, **env},
    )
    assert proc.returncode == 0, proc.stderr
    m = re.search(r"effective TEST_TIMEOUT=(\d+)s", proc.stdout)
    assert m, proc.stdout
    return m.group(1)


def test_parallel_default_timeout_is_2400_and_caller_value_wins() -> None:
    assert _plan_timeout() == "2400"
    assert _plan_timeout(TEST_TIMEOUT="3600") == "3600"
    assert _plan_timeout(TEST_TIMEOUT="90") == "90"


def test_help_names_every_lane_and_the_host_policy() -> None:
    proc = _list("--help")
    assert proc.returncode == 0
    for lane in LANES:
        assert re.search(rf"^\s+{lane}\s+\d+s", proc.stdout, re.M), lane
    assert "Host policy" in proc.stdout


FAKE_PYTHON = """#!/usr/bin/env bash
# Stands in for `python -m pytest`: records argv, writes the junit file, exits $FAKE_RC.
out="${FAKE_OUT:?}"
printf '%s\\n' "$@" > "$out/args.$$"
for a in "$@"; do
  case "$a" in
    --junitxml=*)
      if [[ "${FAKE_NO_XML:-}" != "1" ]]; then
        printf '<testsuites><testsuite tests="1"/></testsuites>\\n' > "${a#--junitxml=}"
      fi ;;
  esac
done
exit "${FAKE_RC:-0}"
"""


def _run_parallel(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fake = tmp_path / "fake-python"
    fake.write_text(FAKE_PYTHON)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    out = tmp_path / "out"
    out.mkdir()
    lane_dir = tmp_path / "lanes"
    full_env = {
        **os.environ,
        "PYTHON": str(fake),
        "FAKE_OUT": str(out),
        "TEST_LANE_DIR": str(lane_dir),
        "TEST_TIMEOUT": "120",
        **env,
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--parallel", "3", "--tb=short"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        env=full_env,
    )
    return proc, out


def test_parallel_children_get_only_their_lane_and_the_passthrough_args(tmp_path: Path) -> None:
    proc, out = _run_parallel(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PARALLEL_RESULT rc=0" in proc.stdout
    assert "failed=-" in proc.stdout
    arg_files = list(out.glob("args.*"))
    assert len(arg_files) == len(LANES)
    seen: set[str] = set()
    for f in arg_files:
        args = f.read_text().splitlines()
        for banned in ("--parallel", "--plan", "--lane"):
            assert banned not in args
        assert "--tb=short" in args
        assert "no:cacheprovider" in args
        assert any(a.startswith("--junitxml=") for a in args)
        seen |= {a for a in args if a.startswith("tests/browser/")}
    assert seen == set().union(*(_lane_files(lane) for lane in LANES))


def test_parallel_exit_codes(tmp_path: Path) -> None:
    proc, _ = _run_parallel(tmp_path / "fail", FAKE_RC="1")
    assert proc.returncode == 1
    assert "PARALLEL_RESULT rc=1" in proc.stdout

    proc, _ = _run_parallel(tmp_path / "killed", FAKE_RC="137")
    assert proc.returncode == 137
    assert "timeout or killed" in proc.stdout

    proc, _ = _run_parallel(tmp_path / "noxml", FAKE_NO_XML="1")
    assert proc.returncode == 1
    assert "junit xml missing or empty" in proc.stdout


# --- CI browser task (M26 F1 L5) ------------------------------------------------
# ci/the-one.pipeline.yml runs ONE browser task, ci/tasks/browser.yml, which runs
# `run-tests.sh --parallel 1`: every canonical lane in sequence, by construction.


def _browser_script() -> str:
    import yaml

    task = yaml.safe_load((REPO / "ci" / "tasks" / "browser.yml").read_text())
    return task["run"]["args"][-1]


def test_ci_browser_task_runs_every_lane_through_parallel_1() -> None:
    import yaml

    pipeline = yaml.safe_load((REPO / "ci" / "the-one.pipeline.yml").read_text())
    job = next(j for j in pipeline["jobs"] if j["name"] == "ci")
    steps = next(s for s in job["plan"] if "in_parallel" in s)["in_parallel"]["steps"]
    browser = [s for s in steps if s.get("file") == "repo/ci/tasks/browser.yml"]
    assert len(browser) == 1, "the ci job runs exactly one browser task"
    assert "params" not in browser[0], "no per-task lane list in the pipeline"

    script = _browser_script()
    assert "scripts/run-tests.sh --parallel 1" in script
    # No hand-listed lane: the lane set comes from run-tests.sh, so it cannot drift.
    for lane in LANES:
        assert not re.search(rf"\b{lane}\b", script.replace("tests/browser", "")), lane
    assert "--lane" not in script
    # WebKit is required in this one task: contracts is engine-parametrized.
    assert "THE_ONE_REQUIRE_WEBKIT=1" in script
    assert "chromium webkit" in script


def test_no_ci_task_sets_container_limits() -> None:
    # The local Concourse workers reject container_limits (cgroup v2 threaded mode:
    # runc "cannot enter cgroupv2 /sys/fs/cgroup/garden with domain controllers"),
    # so the task fails at container creation. None may carry them until the
    # workers are fixed. See the header of ci/tasks/browser.yml.
    for path in sorted((REPO / "ci" / "tasks").glob("*.yml")):
        for line in path.read_text().splitlines():
            assert not line.startswith("container_limits"), path.name


def test_ci_tasks_install_from_the_lockfile() -> None:
    for name in ("test", "lint", "bwrap", "browser"):
        text = (REPO / "ci" / "tasks" / f"{name}.yml").read_text()
        assert "uv sync --locked" in text, name
        assert "pip install" not in text, name
