"""Real-load tests for the ``embedding model`` doctor probe (M24 F01 L02,
rewritten M24 F02 L03).

**This file exists because of an autouse fixture.** ``tests/test_doctor.py``
patches ``_probe_embedding_model`` for every test in that module, so the 16
``run_doctor(`` call sites there do not each pay the 62 MiB model load. pytest
offers no opt-out from an autouse fixture — the usual marker workaround needs
``request.node`` to be the test function, and at module scope it is the Module —
so the dedicated real-load coverage lives in a separate file instead.

Per M24 F01 DD-7 this is the **only host-side proof that the real asset loads**.
It must never be mocked or skipped. Two of the three tests below do stub
``StaticModel``/the model path, but only to observe the probe's *guards*; the
first one loads the committed weights for real.

Note the asset is untracked until a human stages it (the leg's terminal
handoff), so on a machine that has not run ``make refresh-embedding-model``
these tests fail — which is the correct signal, not a reason to skip.

M24 F02 L03 (DD-11): the probe now constructs a fresh
``the_one.embeddings.local.LocalStaticBackend`` rather than loading
``model2vec`` directly, and the two DD-5 offline-load guards now live in
``the_one.embeddings.local.resolve_model_dir`` / ``force_hf_offline`` — the
monkeypatch targets below retarget accordingly (the constants moved out of
``diagnostics.py`` entirely; nothing outside this file and ``diagnostics.py``
imports the underscored names, and now ``diagnostics.py`` itself imports only
the plain ``EMBEDDING_DIM`` / ``EMBEDDING_WEIGHTS_FILENAME`` names it still
needs).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from the_one import diagnostics
from the_one.diagnostics import _probe_embedding_model
from the_one.embeddings import local as embeddings_local
from the_one.embeddings.local import EMBEDDING_DIM


def _packaged_model_dir() -> Path:
    """The directory the probe resolves, computed the same way the probe does."""
    from importlib.resources import files

    return Path(
        str(
            files(embeddings_local.EMBEDDING_PACKAGE).joinpath(
                "data", embeddings_local.EMBEDDING_MODEL_DIRNAME
            )
        )
    )


class TestRealLoad:
    def test_probe_loads_the_committed_weights(self) -> None:
        """Load the real bundled model and assert on the EMITTED DETAIL.

        Leg 1's lesson: a naive monkeypatch that the probe's broad ``except``
        swallows yields a test that passes while asserting nothing. So this
        checks the concrete resolved values the probe reports — width, norm,
        weights size, RSS, resolved path — not merely ``ok``.
        """
        result = _probe_embedding_model()
        assert result.ok is True, result.detail
        assert result.name == "embedding model"
        assert f"{EMBEDDING_DIM}-dim" in result.detail
        # DD-11's rewritten shape: native dtype AND the float32 seam it's
        # upcast through, plus the truncation count for the probe text.
        assert "float16 model → float32 seam" in result.detail
        assert "truncated=0" in result.detail
        assert "norm " in result.detail
        # The truncated-file / LFS-pointer tell: the byte size is in the line.
        assert "model.safetensors=" in result.detail
        # DD-4 read path — Flight 2 needs this figure for the float16-vs-int8
        # vector-storage decision, and no CI task measures memory.
        assert "peak RSS" in result.detail
        assert embeddings_local.EMBEDDING_MODEL_DIRNAME in result.detail

    def test_reported_weights_size_matches_the_file_on_disk(self) -> None:
        """The size in the detail line is read, not hardcoded."""
        weights = _packaged_model_dir() / embeddings_local.EMBEDDING_WEIGHTS_FILENAME
        result = _probe_embedding_model()
        assert f"model.safetensors={weights.stat().st_size:,} bytes" in result.detail

    def test_weights_clear_the_github_blob_limit(self) -> None:
        """DD-2's whole basis: float16 keeps the single blob under 100 MiB.

        Asserted here as well as in the generator because this is the check that
        cannot be performed after the fact — once the blob is pushed it is in
        history permanently.
        """
        weights = _packaged_model_dir() / embeddings_local.EMBEDDING_WEIGHTS_FILENAME
        assert weights.stat().st_size < 100 * 1024 * 1024


class TestOfflineInvariant:
    """DD-5: the probe must be INCAPABLE of passing by download.

    ``model2vec._resolve_folder`` returns a local directory only if it exists
    and otherwise falls through to ``snapshot_download()``. On a networked
    machine a model tree-shaken out of the bundle would then produce a *passing*
    probe that fetched the weights over the network — the same fail-open the
    model-catalog probe was written against, one layer out.
    """

    def test_missing_packaged_directory_fails_rather_than_downloading(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Point the probe at a directory that genuinely is not there.

        Deliberately NOT implemented by renaming the real directory on disk: the
        asset is 62 MiB and untracked until a human stages it, so a test that
        moves it could leave the working tree needing a re-download. Repointing
        the name produces the identical filesystem miss with nothing at stake.

        Also guards against the wrong assertion: with an ABSOLUTE path — which
        is what ``importlib.resources.files(...)`` yields — a missed load raises
        ``HFValidationError`` from ``validate_repo_id``, not the
        ``LocalEntryNotFoundError`` a relative or repo-id-shaped string gives.
        Pinning either would be pinning the wrong thing. What matters is that
        ``from_pretrained`` is never reached at all.
        """
        sentinel = "definitely-not-a-real-model-directory"
        monkeypatch.setattr(embeddings_local, "EMBEDDING_MODEL_DIRNAME", sentinel)

        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("from_pretrained must not be reached — this is the DD-5 breach")

        import model2vec

        monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", _explode)

        result = _probe_embedding_model()
        assert result.ok is False
        assert "packaged model directory not found" in result.detail
        assert sentinel in result.detail

    def test_missing_weights_file_fails_rather_than_downloading(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Guard #2: the directory exists but ``model.safetensors`` is absent.

        Design review found this guard had no test anywhere in the tree —
        only guard #1 (directory absence) was covered. Builds a real
        ``tmp_path/data/fake-model`` directory holding stand-ins for the
        other four files but never the weights file, points
        ``_resource_files`` at ``tmp_path`` (mirroring what
        ``importlib.resources.files(...)`` would return for the real
        package) and ``EMBEDDING_MODEL_DIRNAME`` at ``fake-model``, and
        proves ``from_pretrained`` is never reached.
        """
        fake_model_dir = tmp_path / "data" / "fake-model"
        fake_model_dir.mkdir(parents=True)
        for name in ("config.json", "tokenizer.json", "tokenizer_config.json", "modules.json"):
            (fake_model_dir / name).write_text("{}")

        monkeypatch.setattr(embeddings_local, "_resource_files", lambda pkg: tmp_path)
        monkeypatch.setattr(embeddings_local, "EMBEDDING_MODEL_DIRNAME", "fake-model")

        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("from_pretrained must not be reached — this is the DD-5 breach")

        import model2vec

        monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", _explode)

        result = _probe_embedding_model()
        assert result.ok is False
        assert "model.safetensors missing from" in result.detail

    def test_hf_hub_offline_is_set_before_the_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The env var does the real work; the path check is defence in depth.

        Captures ``HF_HUB_OFFLINE`` at the moment ``from_pretrained`` is called,
        so this fails if a future edit sets it after the load or drops it.
        """
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        seen: dict[str, str | None] = {}

        import numpy as np

        class _StubModel:
            dim = EMBEDDING_DIM
            embedding = np.zeros((1, EMBEDDING_DIM), dtype=np.float16)

            @staticmethod
            def tokenize(sentences: list[str], max_length: int | None = None) -> list[list[int]]:
                return [[1, 2, 3] for _ in sentences]

            @staticmethod
            def encode(sentences: list[str], **kwargs: object) -> "np.ndarray":
                unit = np.zeros(EMBEDDING_DIM, dtype=np.float16)
                unit[0] = 1.0
                return np.tile(unit, (len(sentences), 1))

        def _capture(path: str, *args: object, **kwargs: object) -> _StubModel:
            seen["offline"] = os.environ.get("HF_HUB_OFFLINE")
            seen["path"] = path
            return _StubModel()

        import model2vec

        monkeypatch.setattr(model2vec.StaticModel, "from_pretrained", _capture)

        result = _probe_embedding_model()
        # Assert on the emitted detail too, not just ok — a stub the probe's
        # broad `except` swallowed would leave `seen` empty and `ok` False.
        assert result.ok is True, result.detail
        assert f"{EMBEDDING_DIM}-dim" in result.detail
        assert seen["offline"] == "1"
        # It loaded from the packaged path, not from a repo id.
        assert str(seen["path"]).endswith(embeddings_local.EMBEDDING_MODEL_DIRNAME)
        assert os.path.isabs(str(seen["path"]))

    def test_huggingface_hub_constant_is_forced_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``HF_HUB_OFFLINE`` is bound ONCE, at huggingface_hub import time.

        Setting the environment variable after the package is already imported
        is too late for ``huggingface_hub.constants.HF_HUB_OFFLINE``, which is
        the value the hub code actually consults. ``force_hf_offline`` sets
        both; this covers the second.
        """
        import huggingface_hub.constants as hf_constants

        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.setattr(hf_constants, "HF_HUB_OFFLINE", False, raising=False)

        embeddings_local.force_hf_offline()

        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert hf_constants.HF_HUB_OFFLINE is True


class TestPeakRss:
    def test_reports_a_plausible_positive_figure(self) -> None:
        """Advisory, but it must be a real number on the host that measures it."""
        peak, reason = diagnostics._peak_rss_bytes()
        assert peak is not None, reason
        assert reason is None
        # A Python process that has imported numpy and tokenizers is comfortably
        # over 8 MiB; anything under that means the units are wrong.
        assert peak > 8 * 1024 * 1024


class _FakeWinFunc:
    """A stand-in for a ctypes ``_FuncPtr`` that records restype/argtypes.

    Unlike a real Windows DLL function, this does not perform ctypes' own
    argument marshalling — but it is enough to prove the production code
    *declares* ``restype``/``argtypes`` before calling, which is what fixes
    the real truncated-HANDLE bug (verified on windows-worker; see the flight
    log). ``return_value`` may be a plain value or a callable of
    ``(*args) -> value`` for cases that need to inspect/mutate arguments.
    """

    def __init__(self, return_value):
        self._return_value = return_value
        self.restype = None
        self.argtypes = None
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        if callable(self._return_value):
            return self._return_value(*args)
        return self._return_value


class TestPeakRssWindowsBranch:
    """Exercises the ``os.name == "nt"`` branch from a Linux host.

    ``ctypes.wintypes`` imports fine on Linux, but ``ctypes.WinDLL`` does not
    exist there, so it is patched onto the module for the duration of each
    test. ``ctypes.get_last_error`` is Windows-only for the same reason.

    The counters struct built here mirrors ``_ProcessMemoryCounters`` inside
    ``_peak_rss_bytes`` field-for-field (same field names, order and ctypes
    types), so a pointer cast against it lands on the identical in-memory
    layout the production structure produces in this same process — no
    reliance on the private class or on hardcoded byte offsets.
    """

    def _fake_counters_type(self):
        import ctypes
        from ctypes import wintypes

        class _FakeProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        return _FakeProcessMemoryCounters

    def test_success_declares_handle_semantics_and_returns_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ctypes
        from ctypes import wintypes

        monkeypatch.setattr(os, "name", "nt")
        fake_counters_type = self._fake_counters_type()

        expected_peak = 25_288_704  # observed on windows-worker with the fix
        get_current_process = _FakeWinFunc(return_value=-1)

        def fill_counters(handle, counters_ref, cb):
            # Prove HANDLE semantics were declared before this call: on real
            # Windows, an undeclared restype truncates the -1 pseudo-handle to
            # 32 bits before it ever reaches here — the exact bug this fixes.
            assert get_current_process.restype is wintypes.HANDLE
            assert memory_info.argtypes is not None
            assert memory_info.argtypes[0] is wintypes.HANDLE
            assert handle == -1
            counters = ctypes.cast(counters_ref, ctypes.POINTER(fake_counters_type)).contents
            counters.PeakWorkingSetSize = expected_peak
            return 1

        memory_info = _FakeWinFunc(return_value=fill_counters)

        class _FakeKernel32:
            GetCurrentProcess = get_current_process
            K32GetProcessMemoryInfo = memory_info

        def fake_win_dll(name, use_last_error=False):
            assert name == "kernel32"
            return _FakeKernel32()

        monkeypatch.setattr(ctypes, "WinDLL", fake_win_dll, raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 0, raising=False)

        peak, reason = diagnostics._peak_rss_bytes()

        assert reason is None
        assert peak == expected_peak

    def test_failure_reports_get_last_error_in_reason(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import ctypes

        monkeypatch.setattr(os, "name", "nt")

        get_current_process = _FakeWinFunc(return_value=-1)
        memory_info = _FakeWinFunc(return_value=0)  # failure: returns FALSE

        class _FakeKernel32:
            GetCurrentProcess = get_current_process
            K32GetProcessMemoryInfo = memory_info

        def fake_win_dll(name, use_last_error=False):
            return _FakeKernel32()

        monkeypatch.setattr(ctypes, "WinDLL", fake_win_dll, raising=False)
        monkeypatch.setattr(ctypes, "get_last_error", lambda: 6, raising=False)

        peak, reason = diagnostics._peak_rss_bytes()

        assert peak is None
        assert reason is not None
        assert "GetLastError" in reason
        assert "6" in reason
