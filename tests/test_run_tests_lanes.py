"""The six browser test lanes partition the browser suite (M25 F4 L1, squawk 0117).

`scripts/run-tests.sh --lane <lane> --list` prints a lane's files and exits
without running pytest. This test lists every lane and asserts the lanes are
pairwise disjoint and that their union is every `tests/browser/test_*.py`
except the pixel-only `test_visual_snapshots.py`. `shared` is computed as the
complement of the five named lanes, so a new file always lands somewhere; the
disjointness check is what catches a glob that claims a file twice.
"""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "run-tests.sh"
LANES = ("chats", "agents", "library", "settings", "contracts", "shared")


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
    assert "chats|agents|library|settings|contracts|shared" in proc.stderr
    assert proc.stdout == ""
