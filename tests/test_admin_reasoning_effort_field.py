"""Hermetic source-content guard for the admin `reasoning_effort` field
(Mission 16 Flight 11 Leg 06).

Same genre as ``tests/test_ui_guards.py`` / ``tests/test_token_definitions.py``:
a plain ``Path.read_text()`` scan over the already-served JS sources, no
FastAPI app / SQLite / AsyncClient (that heavier machinery in
``tests/test_tools_admin_editor_assets.py`` exists to verify a *newly-mounted*
asset is wired into the SPA shell — these files are already served, so that
overhead is unwarranted here per design review).

Asserts:

- ``provider-editor.js`` renders a ``reasoning_effort`` ``<select>`` with
  ``data-field="config.reasoning_effort"`` and the three effort options
  (``low``/``medium``/``high``) plus the empty "Provider default" option.
- ``providers-section.js`` (the only home of ``TYPE_DEFAULTS`` since the Settings
  Providers page retired, sortie 02) gates the field via ``TYPE_DEFAULTS[...].showReasoningEffort``
  for the five reasoning-capable provider types (anthropic, openai,
  openrouter, ollama, openai-compatible) and leaves ``mock`` without the flag.
"""

from __future__ import annotations

from tests._ui_guard_helpers import JS_DIR

PROVIDER_EDITOR_JS = JS_DIR / "areas" / "studio" / "provider-editor.js"
PROVIDERS_SECTION_JS = JS_DIR / "areas" / "studio" / "providers-section.js"

REASONING_CAPABLE_TYPES = (
    "anthropic",
    "anthropic-plan",
    "anthropic-plan-token",
    "openai",
    "openrouter",
    "ollama",
    "openai-compatible",
)


def test_provider_editor_renders_reasoning_effort_select() -> None:
    """provider-editor.js must render the reasoning_effort <select> with the
    data-field hook and the low/medium/high options."""
    src = PROVIDER_EDITOR_JS.read_text()

    assert 'data-field="config.reasoning_effort"' in src, (
        "provider-editor.js is missing the config.reasoning_effort data-field hook"
    )
    assert 'id="pf-reasoning-effort"' in src, (
        "provider-editor.js is missing the pf-reasoning-effort control id"
    )
    assert (
        '<select class="field-input field-select admin-pf-input admin-pf-select" '
        'id="pf-reasoning-effort" data-field="config.reasoning_effort"'
    ) in src, "config.reasoning_effort must be rendered on the pf-reasoning-effort <select> element"
    assert "admin-pf-reasoning-effort" in src, (
        "provider-editor.js is missing the admin-pf-reasoning-effort marker class "
        "used by the type-change show/hide toggle"
    )

    for option_value in ("low", "medium", "high"):
        assert f'value="{option_value}"' in src, (
            f"provider-editor.js is missing the '{option_value}' reasoning_effort option"
        )
    assert 'value=""' in src, (
        "provider-editor.js is missing the empty 'Provider default' reasoning_effort option"
    )
    assert "Provider default" in src, (
        "provider-editor.js is missing the 'Provider default' option label"
    )


def test_provider_editor_toggles_reasoning_effort_row_on_type_change() -> None:
    """The type-change handler must show/hide the reasoning_effort row like
    the existing numCtx/thinkingEnabled rows."""
    src = PROVIDER_EDITOR_JS.read_text()

    assert "reasoningEffortRow" in src, (
        "provider-editor.js is missing the reasoningEffortRow lookup used by "
        "the type-change show/hide toggle"
    )
    assert "defaults.showReasoningEffort" in src, (
        "provider-editor.js does not gate the reasoning_effort row/toggle on "
        "defaults.showReasoningEffort"
    )


def test_provider_editor_persists_reasoning_effort_on_save() -> None:
    """The save-payload builder must always persist config.reasoning_effort
    when the field is shown (mirrors the thinking_enabled always-persist
    block)."""
    src = PROVIDER_EDITOR_JS.read_text()

    assert "payload.config.reasoning_effort" in src, (
        "provider-editor.js save-payload builder does not assign payload.config.reasoning_effort"
    )


def test_provider_editor_seeds_config_from_existing_provider_before_field_blocks() -> None:
    """Phase-2d review fix (config-wipe on save): collectFormData must seed
    ``payload.config`` from a shallow clone of the existing ``provider.config``
    BEFORE any field-specific block (openrouter referer/title, num_ctx,
    thinking_enabled, reasoning_effort) runs. The backend's update_provider
    does ``existing.model_copy(update=data)`` — a field-level REPLACE, not a
    deep merge — so a payload.config built only from fields the UI renders
    would silently wipe config/env-only keys (response_format, stop; DD6) on
    every Save. This is a source-level guard only (no JS unit runner exists);
    the behavioral save-preserves-config property is verified in the L07 HAT.
    """
    src = PROVIDER_EDITOR_JS.read_text()

    seed_idx = src.index("payload.config = (isEdit && provider && provider.config)")
    assert seed_idx != -1, (
        "collectFormData is missing the payload.config seed from the existing "
        "provider.config — without it, config keys the UI doesn't render "
        "(response_format, stop) are wiped on Save"
    )
    assert "Object.assign({}, provider.config)" in src, (
        "the config seed must shallow-clone provider.config rather than "
        "aliasing it (aliasing would let in-place edits mutate the original "
        "provider object before the fetch is sent)"
    )

    # The seed must run before every field-specific block that writes into
    # payload.config, so those blocks overlay onto (rather than replace) the
    # preserved keys.
    for marker in (
        "if (selectedType === 'openrouter')",
        "if (defaults.showNumCtx)",
        "if (defaults.showThinkingEnabled)",
        "if (defaults.showReasoningEffort)",
    ):
        marker_idx = src.index(marker)
        assert seed_idx < marker_idx, (
            f"the payload.config seed must appear before the '{marker}' block "
            "so that block overlays onto the preserved config"
        )

    # The openrouter branch must overlay (set/delete keys on the seeded
    # object) rather than replace payload.config with a fresh object.
    openrouter_start = src.index("if (selectedType === 'openrouter')")
    openrouter_end = src.index("if (defaults.showNumCtx)", openrouter_start)
    openrouter_block = src[openrouter_start:openrouter_end]
    assert "payload.config = cfg" not in openrouter_block, (
        "the openrouter branch must not replace payload.config with a fresh "
        "object — it must overlay referer/title onto the seeded config"
    )
    assert "payload.config.referer" in openrouter_block, (
        "the openrouter branch must set/delete referer directly on the seeded payload.config"
    )
    assert "payload.config.title" in openrouter_block, (
        "the openrouter branch must set/delete title directly on the seeded payload.config"
    )


def test_admin_type_defaults_gate_reasoning_effort_for_capable_types() -> None:
    """providers-section.js TYPE_DEFAULTS must carry showReasoningEffort: true for every
    reasoning-capable provider type, and must NOT add it to mock."""
    src = PROVIDERS_SECTION_JS.read_text()

    start = src.index("var TYPE_DEFAULTS")
    end = src.index("};", start) + 2
    type_defaults_block = src[start:end]

    for provider_type in REASONING_CAPABLE_TYPES:
        type_start = type_defaults_block.index(f"'{provider_type}'")
        type_end = type_defaults_block.index("}", type_start)
        entry = type_defaults_block[type_start:type_end]
        assert "showReasoningEffort: true" in entry, (
            f"providers-section.js TYPE_DEFAULTS['{provider_type}'] lacks showReasoningEffort: true"
        )

    mock_start = type_defaults_block.index("'mock'")
    mock_end = type_defaults_block.index("}", mock_start)
    mock_entry = type_defaults_block[mock_start:mock_end]
    assert "showReasoningEffort" not in mock_entry, (
        "providers-section.js TYPE_DEFAULTS['mock'] should not carry showReasoningEffort "
        "(mock is not a reasoning-capable provider type)"
    )
