"""Pins for .github/workflows/release.yml and its stub (Mission 32 Flight 4 leg 4, DD6, DD7).

The tag path (a ``push``, where every ``inputs.*`` is empty) first runs at the real release, so
these tests parse the YAML and pin every expression that has to fall back.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "release.yml"
STUB = ROOT / "packaging" / "release" / "release.stub.yml"
PLATFORM_JOBS = ("windows", "linux", "macos")


def _doc(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _on(doc: dict) -> dict:
    return doc["on"] if "on" in doc else doc[True]  # YAML 1.1 reads `on` as True


def _dispatch_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"^  workflow_dispatch:\n(?:    .*\n|\n)*", text, re.M)
    assert m, f"{path} has no workflow_dispatch block"
    return m.group(0).rstrip("\n") + "\n"


DOC = _doc(WORKFLOW)
JOBS = DOC["jobs"]


def _run_text(job: dict) -> str:
    return "\n".join(s.get("run", "") for s in job["steps"])


def test_triggers():
    on = _on(DOC)
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": ["v*"]}


def test_dispatch_inputs():
    inputs = _on(DOC)["workflow_dispatch"]["inputs"]
    assert list(inputs) == ["version", "platforms", "macos_mode", "windows_mode"]
    assert inputs["version"]["type"] == "string" and inputs["version"]["default"] == ""
    assert inputs["platforms"]["type"] == "string"
    assert inputs["platforms"]["default"] == "windows,linux,macos"
    for mode in ("macos_mode", "windows_mode"):
        assert inputs[mode]["type"] == "choice"
        assert inputs[mode]["options"] == ["full", "lifecycle"]
        assert inputs[mode]["default"] == "full"


def test_dispatch_block_equals_the_stub_byte_for_byte():
    assert _dispatch_block(WORKFLOW) == _dispatch_block(STUB)
    assert _on(_doc(STUB)).keys() == {"workflow_dispatch"}, "the stub has no push trigger"
    assert DOC["name"] == _doc(STUB)["name"] == "release"


def test_stub_is_one_noop_job_and_never_publishes():
    stub = _doc(STUB)
    assert list(stub["jobs"]) == ["stub"]
    text = STUB.read_text(encoding="utf-8")
    assert "gh release" not in text and "uses:" not in text.replace("# ", "")
    assert stub["permissions"] == {"contents": "read"}


def test_concurrency_is_per_event_and_never_cancels():
    assert DOC["concurrency"] == {
        "group": "release-${{ github.event_name == 'push' && github.ref || 'dispatch' }}",
        "cancel-in-progress": False,
    }


def test_permissions():
    assert DOC["permissions"] == {"contents": "read"}
    assert JOBS["publish"]["permissions"] == {"contents": "write"}
    for name, job in JOBS.items():
        if name != "publish":
            assert "permissions" not in job or job["permissions"] == {"contents": "read"}, name


def test_job_set():
    assert set(JOBS) == {"audit", "version", "windows", "linux", "macos", "publish"}


def test_audit_job():
    job = JOBS["audit"]
    run = _run_text(job)
    assert "pip install uv==0.10.0" in run and "pip-audit>=2.7" in run
    assert (
        "uv export --frozen --no-dev --no-emit-project --extra gui --extra all-llms "
        "--format requirements-txt > release-requirements.txt"
    ) in run
    assert "pip-audit --disable-pip -r release-requirements.txt" in run
    assert "needs" not in job


def test_version_job():
    job = JOBS["version"]
    checkout = next(
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout")
    )
    assert checkout["with"] == {"fetch-depth": 0}
    assert job["outputs"] == {"version": "${{ steps.gate.outputs.version }}"}
    gate = next(s for s in job["steps"] if s.get("id") == "gate")
    assert gate["env"] == {
        "EVENT": "${{ github.event_name }}",
        "REF": "${{ github.ref }}",
        "INPUT_VERSION": "${{ inputs.version }}",
        "INPUT_PLATFORMS": "${{ inputs.platforms }}",
    }
    assert 'python scripts/release_check.py "${args[@]}"' in gate["run"]
    assert '--event "$EVENT" --ref "$REF" --input-version "$INPUT_VERSION"' in gate["run"]
    assert '--platforms "$INPUT_PLATFORMS"' in gate["run"]
    assert "${{" not in gate["run"], "untrusted input goes through env, never interpolated"


def test_platform_jobs():
    for name in PLATFORM_JOBS:
        job = JOBS[name]
        assert job["needs"] == ["audit", "version"], name
        assert job["uses"] == f"./.github/workflows/{name}-packages.yml", name
        # a push has no inputs: the condition and the mode must both fall back
        assert job["if"] == (
            "github.event_name == 'push' || "
            f"contains(format(',{{0}},', inputs.platforms), ',{name},')"
        ), name
        assert job["with"]["version"] == "${{ needs.version.outputs.version }}", name
    assert JOBS["windows"]["with"] == {
        "version": "${{ needs.version.outputs.version }}",
        "mode": "${{ inputs.windows_mode || 'full' }}",
    }
    assert JOBS["macos"]["with"] == {
        "version": "${{ needs.version.outputs.version }}",
        "mode": "${{ inputs.macos_mode || 'full' }}",
    }
    assert JOBS["linux"]["with"] == {"version": "${{ needs.version.outputs.version }}"}


def test_called_workflows_accept_these_inputs():
    for name in PLATFORM_JOBS:
        callee = _on(_doc(WORKFLOWS / f"{name}-packages.yml"))["workflow_call"]["inputs"]
        assert set(JOBS[name]["with"]) <= set(callee), name


def test_publish_job():
    job = JOBS["publish"]
    assert job["if"] == "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
    assert sorted(job["needs"]) == ["linux", "macos", "version", "windows"]
    assert job["runs-on"] == "ubuntu-latest"
    downloads = [s["with"] for s in job["steps"] if "download-artifact" in str(s.get("uses"))]
    assert sorted(d["name"] for d in downloads) == [
        "linux-packages",
        "macos-dmg",
        "windows-installer",
    ]


def test_artifact_names_match_the_uploads():
    uploaded = {
        "windows-installer": "windows-packages.yml",
        "linux-packages": "linux-packages.yml",
        "macos-dmg": "macos-packages.yml",
    }
    for artifact, wf in uploaded.items():
        assert f"name: {artifact}\n" in (WORKFLOWS / wf).read_text(encoding="utf-8"), artifact


def test_publish_steps():
    job = JOBS["publish"]
    select = next(s for s in job["steps"] if s.get("name", "").startswith("Select the four"))
    assert "scripts/release_assets.py" in select["run"]
    assert "sha256sum -c SHA256SUMS" in select["run"]
    step = next(s for s in job["steps"] if s.get("name") == "Publish the GitHub release")
    run = step["run"]
    assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert step["env"]["TAG"] == "${{ github.ref_name }}"
    assert step["env"]["VERSION"] == "${{ needs.version.outputs.version }}"
    assert "${{" not in run
    assert "set -eo pipefail" in run
    # the checks come before anything is created
    first_create = run.index("gh release create")
    assert run.index('[ "${#FILES[@]}" -eq 5 ]') < first_create
    assert run.index("test -f SHA256SUMS") < first_create
    # drafts are invisible to `gh release view`: detection lists them
    assert "gh release list --limit 200 --json tagName,isDraft,name" in run
    assert "gh release view" not in run
    assert 'gh release create "$TAG" --draft --title "$TITLE" --notes-file "$NOTES_BODY"' in run
    assert 'gh release create "$TAG" --draft --title "$TAG" --generate-notes' in run
    assert run.count("--clobber") == 3
    assert run.count('gh release edit "$TAG" --draft=false') == 2
    for branch in ("branch: new draft", "branch: existing draft", "branch: existing published"):
        assert branch in run
    # a published release is never re-titled: its branch uploads and nothing else
    published = run[run.index("published)") :]
    published = published[: published.index(";;")]
    assert "gh release edit" not in published and "gh release create" not in published
    assert "gh release upload" in published
    # an existing draft may be re-titled, but is published only after the upload
    draft = run[run.index("draft)") : run.index("published)")]
    assert draft.index("gh release upload") < draft.index("--draft=false")


def test_no_secrets_beyond_the_github_token():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "secrets." not in text
    assert set(re.findall(r"github\.token", text)) == {"github.token"}


def test_standalone_dispatch_rule_is_recorded():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "NO standalone platform dispatch" in text


def test_retired_workflows_are_gone():
    assert not (WORKFLOWS / "windows-installer.yml").exists()
    assert not (WORKFLOWS / "packaging-probe-windows.yml").exists()


def test_artifact_retention_for_a_rerun_publish():
    for wf, name in (("macos-packages.yml", "macos-dmg"), ("linux-packages.yml", "linux-packages")):
        text = (WORKFLOWS / wf).read_text(encoding="utf-8")
        m = re.search(rf"name: {name}\n\s+path: .*\n\s+retention-days: (\d+)", text)
        assert m and m.group(1) == "14", wf
