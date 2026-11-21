"""The PreToolUse Bash hook refuses shell writes into the source tree (squawk 0292)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "block_shell_writes.py"
SETTINGS = REPO / ".claude" / "settings.json"
SCRATCH = "/tmp/claude-1000/scratchpad"


def run_hook(command, cwd=None, tool_name="Bash"):
    payload = {"tool_name": tool_name, "tool_input": {"command": command}, "cwd": cwd or str(REPO)}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"},
        timeout=30,
    )


BLOCKED = [
    "sed -i 's/a/b/' tests/test_x.py",
    "sed -i.bak -e 's/a/b/' the_one/agents.md",
    "sed -ni 's/a/b/p' docs/ui-control-inventory.md",
    "sed --in-place s/a/b/ scripts/run-tests.sh",
    "perl -pi -e 's/a/b/' evals/README.md",
    "perl -i.orig -pe 's/a/b/' missions/x/flight.md",
    "echo hi | tee tests/test_x.py",
    "echo hi | tee -a docs/x.md",
    "echo hi > tests/new.txt",
    "echo hi >> the_one/x.py",
    "echo hi >| scripts/x.sh",
    "echo hi &> tests/x.log",
    "echo hi 2> tests/err.log",
    "echo hi>tests/x.txt",
    f"echo hi > {REPO}/the_one/x.py",
    "echo hi > ./tests/x.txt",
    "cat > tests/test_new.py <<'EOF'\nprint(1)\nEOF",
    "cat >> docs/x.md <<EOF\nmore\nEOF",
    "cp /tmp/x tests/test_x.py",
    "cp -r /tmp/dir the_one/",
    "cp -t evals /tmp/x",
    "install -m 644 /tmp/x scripts/x.sh",
    "mv /tmp/x docs/x.md",
    "mv tests/test_x.py /tmp/x",
    "python3 -c \"open('tests/x.py','w').write('x')\"",
    "python -c \"from pathlib import Path; Path('docs/x.md').write_text('x')\"",
    "python3 - <<'EOF'\nimport shutil\nshutil.copy('/tmp/a', 'the_one/a.py')\nEOF",
    "python3 - <<'EOF'\nwith open('tests/x.py', mode='a') as f:\n    f.write('x')\nEOF",
    "perl -e 'open(F, \">tests/x\"); print F 1'",
    "node -e \"require('fs').writeFileSync('docs/x.md','x')\"",
    'bash -c "echo hi > tests/x.txt"',
    "sh -c 'sed -i s/a/b/ the_one/x.py'",
    'eval "echo hi > tests/x.txt"',
    "bash <<EOF\necho hi > tests/x.txt\nEOF",
    "git status && echo hi > tests/x.txt",
    "ls; sed -i s/a/b/ tests/x.py",
    "cd tests && echo hi > x.txt",
    "cd the_one; sed -i s/a/b/ x.py",
    "find tests -name '*.py' -exec sed -i s/a/b/ {} +",
    "grep -l a tests/*.py | xargs sed -i s/a/b/ tests/x.py",
    "FOO=1 sudo tee tests/x.txt",
    "truncate -s 0 tests/x.log",
    "dd if=/dev/zero of=tests/x bs=1 count=1",
    "echo hi > $CLAUDE_PROJECT_DIR/tests/x.txt",
    "echo hi > squawks/0999-x.md",
    "sed -i 's/a/b/' squawks/0385-x.md",
    "echo hi >> sorties/19-x/flight-log.md",
    "sed -i 's/a/b/' sorties/19-x/flight.md",
    "cp /tmp/x sorties/19-x/leg.md",
    "echo hi > CLAUDE.md",
    "sed -i 's/a/b/' CLAUDE.md",
    "sed -i 's/a/b/' ./SECURITY-MODEL.md",
    "echo hi | tee README.md",
    "echo hi >> README.md",
    f"echo hi > {REPO}/README.md",
    "mv /tmp/x SECURITY-MODEL.md",
    "python3 -c \"open('CLAUDE.md','w').write('x')\"",
]

ALLOWED = [
    "git status",
    "git diff HEAD -- tests/test_x.py",
    "git log --oneline -5 > /dev/null",
    "make test-unit 2>&1",
    "make lint 2>&1 | tail -20",
    "PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_x.py -x --timeout 60",
    "pytest tests/test_x.py -x -q 2>&1 | tail",
    "python -m pytest tests/ --tb=short -q",
    "ruff check the_one/ tests/ scripts/ evals/",
    "ruff format --check the_one/ tests/",
    "ruff format --diff tests/test_x.py",
    "gh pr view 12 --json title",
    "grep -rn foo the_one/ tests/",
    "grep '>' tests/x.py",
    'grep ">>" docs/x.md',
    'echo "a > b"',
    "echo 'a > tests/x.py'",
    "echo hi # > tests/x.py",
    "cat tests/x.py",
    "cat tests/x.py | head -5",
    "sed -n '1,10p' tests/x.py",
    "sed 's/a/b/' tests/x.py",
    "sed -e 's/a/b/' the_one/x.py | head",
    "head -3 docs/x.md > /dev/null",
    "cat tests/a.py 2>/dev/null",
    "ls tests/ > /dev/null 2>&1",
    f"echo hi > {SCRATCH}/out.txt",
    "echo hi > /tmp/out.txt",
    "grep -n foo squawks/0385-x.md sorties/19/flight-log.md",
    "cat CLAUDE.md SECURITY-MODEL.md README.md",
    "grep -n foo CLAUDE.md",
    "sed -n '1,5p' README.md",
    "sed -i s/a/b/ /tmp/README.md",
    "echo hi > /tmp/CLAUDE.md",
    "echo hi > $HOME/notes.txt",
    "echo hi > ~/notes.txt",
    "echo hi | tee /tmp/x",
    "cp tests/x.py /tmp/x.py",
    "cp -r the_one/ /tmp/copy",
    "mv /tmp/a /tmp/b",
    "install -m 644 tests/x.sh /tmp/x.sh",
    "sed -i s/a/b/ /tmp/x.txt",
    "perl -pi -e 's/a/b/' /tmp/x.txt",
    "python3 -c \"print(open('tests/x.py').read())\"",
    "python3 -c \"open('/tmp/x.txt','w').write('x')\"",
    "python3 scripts/ui_capture.py --list",
    "python3 - <<'EOF'\nprint(open('tests/x.py').read())\nEOF",
    "bash -c 'echo hi > /tmp/x'",
    "find tests -name '*.py' -exec grep -l a {} +",
    "find the_one -name '*.py' | xargs grep -l a",
    "cd tests && ls",
    "cd /tmp && echo hi > x.txt",
    "diff <(cat tests/a.py) <(cat tests/b.py)",
    "cat > /tmp/x <<EOF\nsed -i s/a/b/ tests/x.py\nEOF",
    "echo $(cat tests/x.py)",
    "wc -l < tests/x.py",
    "",
]


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked(command):
    result = run_hook(command)
    assert result.returncode == 2, (command, result.stderr)
    assert "Edit/Write" in result.stderr and "0286" in result.stderr
    assert result.stderr.count("\n") == 1  # one line


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed(command):
    result = run_hook(command)
    assert result.returncode == 0, (command, result.stderr)


def test_relative_path_resolves_against_cwd():
    assert run_hook("echo hi > x.txt", cwd=str(REPO / "tests")).returncode == 2
    assert run_hook("echo hi > x.txt", cwd="/tmp").returncode == 0
    assert run_hook("echo hi > x.txt", cwd=str(REPO / "squawks")).returncode == 2
    assert run_hook("echo hi > x.txt", cwd=str(REPO / "sorties")).returncode == 2
    assert run_hook("echo hi > CLAUDE.md", cwd=str(REPO)).returncode == 2
    # a root document name is only protected at the repo root
    assert run_hook("echo hi > README.md", cwd="/tmp").returncode == 0
    assert run_hook("echo hi > README.md", cwd=str(REPO / "docs")).returncode == 2
    assert run_hook("echo hi > README.md", cwd=str(REPO / ".flightops")).returncode == 0


def test_fails_open_on_bad_input():
    for raw in ("", "not json", "[]", '{"tool_input": {"command": 5}}', '{"tool_input": null}'):
        r = subprocess.run(
            [sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, timeout=30
        )
        assert r.returncode == 0, raw


def test_other_tools_pass():
    assert run_hook("echo hi > tests/x.txt", tool_name="Read").returncode == 0


def test_settings_wires_the_hook():
    cfg = json.loads(SETTINGS.read_text())
    entry = cfg["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Bash"
    command = entry["hooks"][0]["command"]
    assert entry["hooks"][0]["type"] == "command"
    assert "$CLAUDE_PROJECT_DIR/.claude/hooks/block_shell_writes.py" in command
    assert command.startswith("python3 ")
