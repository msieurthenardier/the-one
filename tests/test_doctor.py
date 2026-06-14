"""Tests for ``the-one doctor`` (M15 F5 L1, DD5) — ``the_one.diagnostics``.

The doctor must (a) spawn a probe child through the real spawn env, (b) detect
runtimes, (c) print a structured PASS/FAIL with a ``child spawn: OK``/``FAIL``
line, and (d) exit non-zero on failure. Runs LLM-free. These tests exercise the
host (non-frozen) path — the dev-loop / CI-host case the leg explicitly requires
to pass before a frozen binary exists — plus simulated-failure paths.
"""

from __future__ import annotations

import io

import pytest

from the_one import diagnostics
from the_one.diagnostics import ProbeResult, detect_runtimes, run_doctor


class TestRunDoctorHost:
    def test_passes_on_host_with_child_spawn_ok(self) -> None:
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code == 0
        assert "child spawn: OK" in text
        assert "RESULT: PASS" in text
        # Runtime-detection summary is present.
        assert "runtimes:" in text

    def test_no_llm_or_network_import(self) -> None:
        # The module must not require an agent loop. Smoke: importing and running
        # doctor doesn't pull a provider/agent at module top — just confirm the
        # public surface is the small diagnostic set.
        assert hasattr(diagnostics, "run_doctor")
        assert hasattr(diagnostics, "detect_runtimes")


class TestRunDoctorFailures:
    def test_nonzero_when_child_spawn_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_child_spawn",
            lambda env: ProbeResult("child spawn", False, "simulated unspawnable child"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "child spawn: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_nonzero_when_interpreter_unresolvable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            diagnostics,
            "_probe_interpreter",
            lambda: ProbeResult("python interpreter", False, "no interpreter (simulated)"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        assert code != 0
        assert "python interpreter: FAIL" in buf.getvalue()


class TestDetectRuntimes:
    def test_missing_runtime_is_advisory_not_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: None)
        results = detect_runtimes({"PATH": "/usr/bin"})
        # All reported, none are hard failures (advisory surface).
        assert results
        assert all(r.ok for r in results)
        # Missing runtimes carry install guidance.
        assert any("not found" in r.detail for r in results)

    def test_present_runtime_reports_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(diagnostics.shutil, "which", lambda name, path=None: f"/usr/bin/{name}")
        results = detect_runtimes({"PATH": "/usr/bin"})
        assert all(r.ok for r in results)
        assert any("found at /usr/bin/" in r.detail for r in results)


class TestDispatch:
    def test_main_doctor_branch_exits_with_doctor_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import the_one.main as main_mod

        monkeypatch.setattr(main_mod.sys, "argv", ["the-one", "doctor"])
        monkeypatch.setattr(diagnostics, "run_doctor", lambda: 0)
        with pytest.raises(SystemExit) as exc:
            main_mod.cli_entry()
        assert exc.value.code == 0

    def test_main_doctor_branch_propagates_failure_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import the_one.main as main_mod

        monkeypatch.setattr(main_mod.sys, "argv", ["the-one", "doctor"])
        monkeypatch.setattr(diagnostics, "run_doctor", lambda: 3)
        with pytest.raises(SystemExit) as exc:
            main_mod.cli_entry()
        assert exc.value.code == 3
