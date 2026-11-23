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
LANES = (
    "chats",
    "chats-transcript",
    "chats-widgets",
    "gleepglorp-chat",
    "gleepglorp-fill",
    "gleepglorp-kinds",
    "agents",
    "agent-tabs",
    "agent-routines",
    "library",
    "knowledge",
    "mcp",
    "mcp-connection",
    "routing",
    "settings",
    "settings-tools",
    "providers",
    "contracts-overlay",
    "contracts-chat",
    "contracts-widget",
    "contracts-widget-lifecycle",
    "contracts-controls",
    "shared",
)


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


def test_contracts_lanes_are_exactly_the_ui_contract_files(lanes: dict[str, set[str]]) -> None:
    ui = {f"tests/browser/{p.name}" for p in (REPO / "tests" / "browser").glob("test_ui_*.py")}
    assert (
        lanes["contracts-overlay"]
        | lanes["contracts-chat"]
        | lanes["contracts-widget"]
        | lanes["contracts-widget-lifecycle"]
        | lanes["contracts-controls"]
        == ui
    )
    # `contracts` stays an alias for the union (not a canonical lane).
    assert _lane_files("contracts") == ui
    assert "tests/browser/test_ui_listener_cleanup.py" in lanes["contracts-controls"]
    assert not (lanes["shared"] & ui)


def test_contracts_chat_lane_is_the_chat_control_files(lanes: dict[str, set[str]]) -> None:
    """M31 F6 L04 (DD15): the six chat-control contract files are their own lane, so
    `contracts-controls` no longer lists them and the `contracts` alias still does. M35 F1 L1
    adds the two chart files (`test_ui_chart*`); M35 F2 L2 adds the visual notice contract
    (`test_ui_visual_notice*`). The widget frame contract files moved out to `contracts-widget`
    in M35 F2 L3."""
    chat = {
        f"tests/browser/test_ui_{n}_contract.py"
        for n in (
            "composer",
            "message",
            "thinking",
            "telemetry",
            "notice",
            "chart",
            "visual_notice",
            "turn_work",
            "change_table",
        )
    }
    assert lanes["contracts-chat"] == chat
    assert not (lanes["contracts-controls"] & chat)
    assert not (lanes["contracts-overlay"] & chat)
    assert chat <= _lane_files("contracts")


def test_contracts_widget_lanes_are_every_widget_contract_file(lanes: dict[str, set[str]]) -> None:
    """M35 F2 L3 and L5 (AC6): every `test_ui_widget*` file is in `contracts-widget` (the frame
    and card files) or `contracts-widget-lifecycle` (the lifecycle and hang files) and nowhere
    else, and the `contracts` alias still covers them."""
    browser = REPO / "tests" / "browser"
    widget = {f"tests/browser/{p.name}" for p in browser.glob("test_ui_widget_frame*.py")} | {
        f"tests/browser/{p.name}" for p in browser.glob("test_ui_widget_card*.py")
    }
    life = {f"tests/browser/{p.name}" for p in browser.glob("test_ui_widget_lifecycle*.py")} | {
        f"tests/browser/{p.name}" for p in browser.glob("test_ui_widget_hang*.py")
    }
    assert widget and life, "no widget contract file"
    assert "tests/browser/test_ui_widget_frame_contract.py" in widget
    assert "tests/browser/test_ui_widget_lifecycle_contract.py" in life
    assert "tests/browser/test_ui_widget_hang_contract.py" in life
    assert lanes["contracts-widget"] == widget
    assert lanes["contracts-widget-lifecycle"] == life
    every = {f"tests/browser/{p.name}" for p in browser.glob("test_ui_widget*.py")}
    assert widget | life == every
    for other in ("contracts-chat", "contracts-controls", "contracts-overlay", "shared"):
        assert not (lanes[other] & (widget | life)), other
    assert not (lanes["contracts-widget"] & lanes["contracts-widget-lifecycle"])
    assert (widget | life) <= _lane_files("contracts")


def test_settings_tools_lane_is_the_built_in_tools_files(lanes: dict[str, set[str]]) -> None:
    """M31 F4 L11: `settings` was split; the tools files go to `settings-tools`, and the
    `system` alias is still the union of both settings lanes and `providers`."""
    tools = lanes["settings-tools"]
    assert "tests/browser/test_flow_admin_tools_editor.py" in tools
    assert "tests/browser/test_flow_admin_tool_config_fields.py" in tools
    assert "tests/browser/test_flow_admin_encryption_page.py" in lanes["settings"]
    assert not (tools & lanes["settings"])
    assert _lane_files("system") == lanes["settings"] | tools | lanes["providers"]


def test_chats_lanes_are_the_transcript_files_and_the_rest(lanes: dict[str, set[str]]) -> None:
    """M31 F6 L01 (squawk 0259): `chats` was split; the transcript, composer and streaming files
    are `chats-transcript`, a new `test_flow_chat_*` file lands in `chats`, and the `chat` alias
    is the union of both."""
    transcript = lanes["chats-transcript"]
    assert "tests/browser/test_flow_chat_composer.py" in transcript
    assert "tests/browser/test_flow_streaming.py" in transcript
    # Sortie 16 L02: the work-group-per-turn flow tests.
    assert "tests/browser/test_flow_chat_turn_work.py" in transcript
    assert "tests/browser/test_flow_chat_turn_work_states.py" in transcript
    assert "tests/browser/test_flow_chat_pane.py" in lanes["chats"]
    assert "tests/browser/test_chats_helper.py" in lanes["chats"]
    assert not (transcript & lanes["chats"])
    # M35 F2 L6: the widgets-in-chat flow tests are their own lane, kept out of both others.
    widgets = lanes["chats-widgets"]
    assert widgets == {
        "tests/browser/test_flow_chat_widgets.py",
        "tests/browser/test_flow_chat_widgets_scroll.py",
        "tests/browser/test_flow_chat_widgets_canvas.py",
        "tests/browser/test_flow_chat_widgets_isolated.py",
    }
    assert not (widgets & lanes["chats"]) and not (widgets & transcript)
    # M36 F4 L1b: the two GleepGlorp chat files left `chats-transcript` for `gleepglorp`, but
    # the `chat` alias keeps the `chats_pat` pattern, so it still expands them.
    gg_chat = {
        "tests/browser/test_flow_chat_gleepglorp.py",
        "tests/browser/test_flow_chat_proposals.py",
    }
    assert gg_chat <= lanes["gleepglorp-chat"] and not (gg_chat & (transcript | lanes["chats"]))
    assert _lane_files("chat") == lanes["chats"] | transcript | widgets | gg_chat


def test_gleepglorp_lanes_are_chat_fill_and_kinds(lanes: dict[str, set[str]]) -> None:
    """M36 F5 L1b (DD13): the GleepGlorp browser tests are three lanes; `gleepglorp` is an
    alias of their union."""
    chat = {
        "tests/browser/test_flow_gleepglorp_drawer_chat.py",
        "tests/browser/test_flow_gleepglorp_drawer_shell.py",
        "tests/browser/test_flow_chat_gleepglorp.py",
        "tests/browser/test_flow_chat_proposals.py",
    }
    fill = {
        "tests/browser/test_flow_gleepglorp_fill.py",
        "tests/browser/test_flow_gleepglorp_kinds.py",
    }
    kinds = {
        "tests/browser/test_flow_gleepglorp_fill_mcp.py",
        "tests/browser/test_flow_gleepglorp_follow_mcp.py",
        "tests/browser/test_flow_gleepglorp_fill_provider.py",
        "tests/browser/test_flow_gleepglorp_follow_provider.py",
    }
    assert lanes["gleepglorp-chat"] == chat
    assert lanes["gleepglorp-fill"] == fill
    assert lanes["gleepglorp-kinds"] == kinds
    union = chat | fill | kinds
    assert _lane_files("gleepglorp") == union
    for other in ("chats", "chats-transcript", "shared"):
        assert not (lanes[other] & union), other


def test_gleepglorp_alias_is_not_scheduled_in_parallel() -> None:
    plan = _list("--parallel", "3", "--plan").stdout
    assert "gleepglorp-chat" in plan and "gleepglorp-kinds" in plan
    assert "gleepglorp " not in plan and "gleepglorp\n" not in plan


def test_a_new_kinds_file_joins_without_a_pattern_edit() -> None:
    """AC6: `gleepglorp-kinds` is two globs; a new fill or follow file matches them, and the
    `fill` lane's two files do not."""
    import fnmatch
    import re

    text = SCRIPT.read_text()
    m = re.search(r"^gleepglorp_kinds_pat=\((.*?)\)", text, re.M)
    assert m, "gleepglorp_kinds_pat not found"
    globs = re.findall(r"'([^']+)'", m.group(1))
    assert globs

    def matches(name: str) -> bool:
        return any(fnmatch.fnmatch(name, g) for g in globs)

    assert matches("test_flow_gleepglorp_fill_secret.py")
    assert matches("test_flow_gleepglorp_follow_x.py")
    assert not matches("test_flow_gleepglorp_fill.py")
    assert not matches("test_flow_gleepglorp_kinds.py")


def test_mcp_lanes_are_the_split_editor_files(lanes: dict[str, set[str]]) -> None:
    """M31 F6 L01 (squawk 0271): the MCP editor test file was split by concern. `mcp` is create,
    fields, chip lists and key/value; `mcp-connection` is sign-in and lifecycle, status, the
    Server section and the controller tests. None of them falls into `agents`, and the
    `studio` alias still covers every one."""
    editor = {
        f"tests/browser/{p.name}"
        for p in (REPO / "tests" / "browser").glob("test_flow_studio_mcp_editor_*.py")
    }
    assert len(editor) == 7
    assert lanes["mcp"] | lanes["mcp-connection"] == editor
    assert not (lanes["mcp"] & lanes["mcp-connection"])
    assert "tests/browser/test_flow_studio_mcp_editor_create.py" in lanes["mcp"]
    assert "tests/browser/test_flow_studio_mcp_editor_status.py" in lanes["mcp-connection"]
    assert not (editor & lanes["agents"])
    assert not (REPO / "tests" / "browser" / "test_flow_studio_mcp_editor.py").exists()
    assert editor <= _lane_files("studio")


def test_list_without_lane_exits_2() -> None:
    proc = _list("--list")
    assert proc.returncode == 2
    assert "--list needs --lane" in proc.stderr
    assert proc.stdout == ""


def test_list_with_unknown_lane_exits_2_naming_every_lane() -> None:
    proc = _list("--lane", "no-such-lane", "--list")
    assert proc.returncode == 2
    lanes = (
        "chats|chats-transcript|chats-widgets|gleepglorp-chat|gleepglorp-fill|gleepglorp-kinds|agents|agent-tabs|agent-routines|library|knowledge|mcp|mcp-connection|routing|"
        "settings|settings-tools|providers|contracts-overlay|contracts-chat|contracts-widget|contracts-widget-lifecycle|contracts-controls|shared"
    )
    assert lanes in proc.stderr
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
    # WebKit is required in this one task: the contracts lanes are engine-parametrized.
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
    for name in ("test", "lint", "bwrap", "browser", "windows-tests"):
        text = (REPO / "ci" / "tasks" / f"{name}.yml").read_text()
        assert "uv sync --locked" in text, name
        # windows-tests has no uv image: it pip-installs the pinned uv itself, nothing else.
        assert "pip install" not in text.replace("pip install uv==0.9.30", ""), name
        if name == "windows-tests":
            assert "pip install uv==0.9.30" in text
