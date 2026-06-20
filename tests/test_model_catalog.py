"""Unit tests for the model-catalog module (M16 F05 L01).

Covers:
- Known OpenAI model lookup (exact match).
- Known Anthropic model lookup (exact match).
- Longest-prefix-wins: ``gpt-4-turbo`` and ``gpt-4-turbo-preview`` both
  resolve to 128000, not the shorter ``gpt-4`` 8192 entry.
- Dated/variant id: ``gpt-4o-2024-05-13`` resolves via the ``gpt-4o`` prefix.
- Unknown model → ``None`` (both miss shapes: provider-present-model-absent
  AND provider-absent).
- Malformed catalog → ``None`` return + WARNING log (fail-open DD3 path).
- Seed shape: ``generated_at`` and ``providers`` keys present.
"""

from __future__ import annotations

import json
import logging

import pytest

from the_one.llm.model_catalog import _reset_for_tests, context_window_for


@pytest.fixture(autouse=True)
def reset_catalog():
    """Force a fresh catalog load for each test (isolates injection side-effects)."""
    # Force reload from seed before test.
    _reset_for_tests(None)
    yield
    # Restore clean state after test.
    _reset_for_tests(None)


# ---------------------------------------------------------------------------
# Known-model lookups (seed data)
# ---------------------------------------------------------------------------


class TestKnownModels:
    def test_known_openai_exact(self):
        """gpt-4o is in the seed with a 128000 window."""
        assert context_window_for("openai", "gpt-4o") == 128000

    def test_known_openai_gpt4(self):
        """gpt-4 (legacy 8k) resolves correctly."""
        assert context_window_for("openai", "gpt-4") == 8192

    def test_known_openai_gpt35_turbo(self):
        """gpt-3.5-turbo resolves to 16385."""
        assert context_window_for("openai", "gpt-3.5-turbo") == 16385

    def test_known_openai_o1(self):
        assert context_window_for("openai", "o1") == 200000

    def test_known_openai_o3_mini(self):
        assert context_window_for("openai", "o3-mini") == 200000

    def test_known_anthropic_sonnet_4_6(self):
        """claude-sonnet-4-6 is natively 1M."""
        assert context_window_for("anthropic", "claude-sonnet-4-6") == 1_000_000

    def test_known_anthropic_haiku(self):
        """claude-3-5-haiku-latest is 200k."""
        assert context_window_for("anthropic", "claude-3-5-haiku-latest") == 200_000


# ---------------------------------------------------------------------------
# Longest-prefix-wins
# ---------------------------------------------------------------------------


class TestLongestPrefixWins:
    def test_gpt4_turbo_not_collapsed_to_gpt4(self):
        """gpt-4-turbo (128k) must not collapse onto the shorter gpt-4 (8k)."""
        assert context_window_for("openai", "gpt-4-turbo") == 128_000

    def test_gpt4_turbo_preview_via_gpt4_turbo_prefix(self):
        """gpt-4-turbo-preview resolves via the gpt-4-turbo prefix (128k).

        This proves the longest-prefix port did not collapse gpt-4-turbo-preview
        onto the shorter bare gpt-4 entry.
        """
        assert context_window_for("openai", "gpt-4-turbo-preview") == 128_000

    def test_dated_variant_gpt4o(self):
        """gpt-4o-2024-05-13 resolves via the gpt-4o prefix (128k)."""
        assert context_window_for("openai", "gpt-4o-2024-05-13") == 128_000

    def test_dated_variant_gpt4o_aug(self):
        """gpt-4o-2024-08-06 resolves via the gpt-4o prefix (128k)."""
        assert context_window_for("openai", "gpt-4o-2024-08-06") == 128_000

    def test_gpt4_32k_not_collapsed_to_gpt4(self):
        """gpt-4-32k (32768) is longer than gpt-4 (8192) — must not collapse."""
        assert context_window_for("openai", "gpt-4-32k") == 32_768

    def test_exact_match_beats_prefix(self):
        """An exact catalog key is returned directly, bypassing prefix search."""
        # gpt-4o is an exact key; this also confirms prefix search never
        # accidentally returns the wrong entry when the exact key exists.
        assert context_window_for("openai", "gpt-4o") == 128_000


# ---------------------------------------------------------------------------
# Unknown-model → None (both miss shapes)
# ---------------------------------------------------------------------------


class TestUnknownModel:
    def test_provider_present_model_absent(self):
        """openai provider section exists but 'nonexistent-xyz' is absent → None."""
        result = context_window_for("openai", "nonexistent-xyz")
        assert result is None

    def test_provider_absent(self):
        """'unknown-provider' section is absent entirely → None, no exception."""
        result = context_window_for("unknown-provider", "some-model")
        assert result is None

    def test_anthropic_model_absent(self):
        """anthropic provider exists but model is not in the seed → None."""
        result = context_window_for("anthropic", "claude-99-nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Malformed catalog → None + WARNING (DD3 fail-open path)
# ---------------------------------------------------------------------------


class TestMalformedCatalog:
    def test_non_dict_catalog_returns_none_and_warns(self, caplog):
        """Injecting a non-dict catalog (simulates parse failure) → None + WARN."""
        # Inject a malformed catalog by pointing the loader at bad JSON via the
        # module-level _load_catalog seam.
        import the_one.llm.model_catalog as mod

        _original = mod._load_catalog

        def _bad_load():
            raise ValueError("simulated parse failure")

        mod._load_catalog = _bad_load
        _reset_for_tests(None)  # force reload via the now-broken loader
        try:
            with caplog.at_level(logging.WARNING, logger="the_one.llm.model_catalog"):
                result = context_window_for("openai", "gpt-4o")
        finally:
            mod._load_catalog = _original
            _reset_for_tests(None)

        assert result is None
        assert any(
            "failed to load" in rec.message.lower() or "model_catalog" in rec.message.lower()
            for rec in caplog.records
            if rec.levelno >= logging.WARNING
        ), f"Expected a WARNING but got: {[r.message for r in caplog.records]}"

    def test_injected_bad_catalog_dict_returns_none(self, caplog):
        """Injecting a structurally wrong dict (no 'providers') → None, no crash."""
        _reset_for_tests({"generated_at": "2026-01-01"})  # no 'providers' key
        result = context_window_for("openai", "gpt-4o")
        assert result is None


# ---------------------------------------------------------------------------
# Seed shape validity
# ---------------------------------------------------------------------------


class TestSeedShape:
    def test_seed_has_generated_at(self):
        """The seed JSON must carry a 'generated_at' field."""
        import importlib.resources

        package = importlib.resources.files("the_one.llm")
        seed_file = package.joinpath("data").joinpath("model_catalog.json")
        data = json.loads(seed_file.read_text(encoding="utf-8"))
        assert "generated_at" in data, "seed JSON missing 'generated_at'"

    def test_seed_has_providers(self):
        """The seed JSON must carry a 'providers' dict."""
        import importlib.resources

        package = importlib.resources.files("the_one.llm")
        seed_file = package.joinpath("data").joinpath("model_catalog.json")
        data = json.loads(seed_file.read_text(encoding="utf-8"))
        assert "providers" in data, "seed JSON missing 'providers'"
        assert isinstance(data["providers"], dict)

    def test_seed_has_openai_and_anthropic(self):
        """The seed must have both 'openai' and 'anthropic' sections."""
        import importlib.resources

        package = importlib.resources.files("the_one.llm")
        seed_file = package.joinpath("data").joinpath("model_catalog.json")
        data = json.loads(seed_file.read_text(encoding="utf-8"))
        providers = data["providers"]
        assert "openai" in providers, "seed missing 'openai' provider section"
        assert "anthropic" in providers, "seed missing 'anthropic' provider section"

    def test_seed_covers_all_openai_model_context_entries(self):
        """Every model from _OPENAI_FLOOR must resolve in the catalog."""
        from the_one.llm.model_catalog import _OPENAI_FLOOR

        for model_id, expected_window in _OPENAI_FLOOR.items():
            result = context_window_for("openai", model_id)
            assert result is not None, f"seed missing openai/{model_id}"
            assert result >= expected_window, (
                f"seed regressed openai/{model_id}: expected >={expected_window}, got {result}"
            )
