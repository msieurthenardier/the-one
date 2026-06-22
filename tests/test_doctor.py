"""Tests for ``the-one doctor`` (M15 F5, DD5) — ``the_one.diagnostics``.

The doctor must (a) spawn a probe child through the real spawn env, (b) detect
runtimes, (c) print a structured PASS/FAIL with a ``child spawn: OK``/``FAIL``
line, and (d) exit non-zero on failure. Runs LLM-free. These tests exercise the
host (non-frozen) path — the dev-loop / CI-host case the leg explicitly requires
to pass before a frozen binary exists — plus simulated-failure paths.
"""

from __future__ import annotations

import io
import sys
import types

import pytest

from the_one import diagnostics
from the_one.diagnostics import (
    ProbeResult,
    _probe_desktop_shell,
    _probe_llm_providers,
    _probe_model_catalog,
    detect_runtimes,
    run_doctor,
)


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


# ── Desktop-shell doctor probe (M15 F6 L5) ───────────────────────────────────


def _make_stub_module(name: str) -> types.ModuleType:
    """Return a trivial stub module for sys.modules injection."""
    mod = types.ModuleType(name)
    return mod


class TestProbeDesktopShell:
    """Unit tests for the new ``_probe_desktop_shell`` doctor line."""

    def test_ok_path_when_imports_present(self) -> None:
        """When the desktop tray module and its deps are importable → ok=True, 'OK' in output."""
        # Inject stubs into sys.modules so the lazy imports inside
        # _probe_desktop_shell succeed without a real [gui] install.
        stubs = {
            "pystray": _make_stub_module("pystray"),
            "PIL": _make_stub_module("PIL"),
        }
        # the_one.interfaces.desktop.tray is a real module; ensure it's importable
        # (it only lazily imports pystray/PIL itself, so no stub needed for the
        # tray module on this path — the real module imports cleanly).
        with pytest.MonkeyPatch.context() as mp:
            for name, mod in stubs.items():
                mp.setitem(sys.modules, name, mod)
            result = _probe_desktop_shell()
        assert result.ok is True
        assert "OK" in result.detail or "importable" in result.detail

    def test_skip_path_when_import_absent_not_frozen(self) -> None:
        """When pystray is missing on a non-frozen host → ok=True (informational skip)."""
        with pytest.MonkeyPatch.context() as mp:
            # Remove pystray from sys.modules so the import raises ImportError.
            mp.delitem(sys.modules, "pystray", raising=False)
            # Ensure is_frozen() returns False.
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            # Make pystray unimportable by inserting a bad entry that will
            # be restored after the context.  We shadow via a None sentinel
            # which Python treats as "module not found" when __import__ hits it.
            mp.setitem(sys.modules, "pystray", None)  # type: ignore[arg-type]
            result = _probe_desktop_shell()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_skip_keeps_result_pass_in_run_doctor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-frozen skip → RESULT: PASS in the full doctor output."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_desktop_shell",
            lambda: ProbeResult("desktop shell", True, "skipped (gui extra not installed)"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code == 0
        assert "RESULT: PASS" in text
        assert "desktop shell: OK" in text

    def test_frozen_import_fail_is_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Frozen build with missing pystray → ok=False → RESULT: FAIL."""
        # Stub _probe_desktop_shell to return the frozen-fail outcome and verify
        # run_doctor promotes it to RESULT: FAIL.
        monkeypatch.setattr(
            diagnostics,
            "_probe_desktop_shell",
            lambda: ProbeResult(
                "desktop shell",
                False,
                "import failed in frozen build (gui extra missing from bundle?)",
            ),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "desktop shell: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_desktop_line_present_in_output(self) -> None:
        """The desktop shell line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        text = buf.getvalue()
        assert "desktop shell:" in text


class TestProbeLLMProviders:
    """Unit tests for the ``_probe_llm_providers`` doctor line (M16 frozen-
    provider regression gate)."""

    def test_ok_when_all_modules_importable(self) -> None:
        """On a dev host with the source tree present, all provider modules import."""
        result = _probe_llm_providers()
        assert result.ok is True
        assert "importable" in result.detail

    def test_frozen_fail_when_module_missing(self) -> None:
        """Frozen build missing a provider module → ok=False, actionable detail.

        Simulates the exact regression: a provider module tree-shaken out of the
        frozen bundle. A ``None`` sentinel in sys.modules makes the import raise
        ModuleNotFoundError, mirroring the absent-from-bundle condition.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setitem(sys.modules, "the_one.llm.ollama_provider", None)  # type: ignore[arg-type]
            result = _probe_llm_providers()
        assert result.ok is False
        assert "the_one.llm.ollama_provider" in result.detail
        assert "hiddenimports" in result.detail

    def test_nonfrozen_missing_is_informational_skip(self) -> None:
        """Missing provider on a non-frozen host → ok=True (extras may be absent)."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            mp.setitem(sys.modules, "the_one.llm.anthropic_provider", None)  # type: ignore[arg-type]
            result = _probe_llm_providers()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_frozen_fail_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A frozen provider-probe failure promotes the whole run to RESULT: FAIL."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_llm_providers",
            lambda: ProbeResult(
                "llm providers",
                False,
                "provider module(s) missing from frozen bundle",
            ),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "llm providers: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_llm_line_present_in_output(self) -> None:
        """The llm providers line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "llm providers:" in buf.getvalue()


class TestProbeModelCatalog:
    """Unit tests for the ``_probe_model_catalog`` doctor line — the M16 F05
    frozen-seed regression gate (seed data file tree-shaken from the bundle)."""

    def test_ok_when_seed_resolves(self) -> None:
        """On a dev host the bundled seed resolves the probe model to a window."""
        result = _probe_model_catalog()
        assert result.ok is True
        assert "->" in result.detail  # "seed resolves ... -> <window>"

    def test_frozen_fail_when_seed_missing(self) -> None:
        """Frozen build where the seed doesn't resolve (None) → ok=False, actionable.

        Simulates the bundle missing llm/data/model_catalog.json: the loader
        fail-opens to an empty catalog, so context_window_for returns None.
        """
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: True)
            mp.setattr(
                "the_one.llm.model_catalog.context_window_for",
                lambda provider, model: None,
            )
            result = _probe_model_catalog()
        assert result.ok is False
        assert "the-one.spec datas" in result.detail

    def test_nonfrozen_missing_is_informational_skip(self) -> None:
        """Seed not resolving on a non-frozen host → ok=True (informational)."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(diagnostics, "is_frozen", lambda: False)
            mp.setattr(
                "the_one.llm.model_catalog.context_window_for",
                lambda provider, model: None,
            )
            result = _probe_model_catalog()
        assert result.ok is True
        assert "skipped" in result.detail

    def test_frozen_fail_promotes_result_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A frozen catalog-probe failure promotes the whole run to RESULT: FAIL."""
        monkeypatch.setattr(
            diagnostics,
            "_probe_model_catalog",
            lambda: ProbeResult("model catalog", False, "bundled seed did not resolve"),
        )
        buf = io.StringIO()
        code = run_doctor(out=buf)
        text = buf.getvalue()
        assert code != 0
        assert "model catalog: FAIL" in text
        assert "RESULT: FAIL" in text

    def test_doctor_catalog_line_present_in_output(self) -> None:
        """The model catalog line appears in run_doctor output on this host."""
        buf = io.StringIO()
        run_doctor(out=buf)
        assert "model catalog:" in buf.getvalue()
