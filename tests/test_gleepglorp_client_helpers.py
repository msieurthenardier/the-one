"""The shared GleepGlorp client helpers (M36 F5 L2, flight DD4).

The MCP and provider fills and the three editors' follow notes are built on two cores under
``static/js/areas/shared/``. These checks keep a second copy from growing back; the behaviour
itself is pinned by the browser lanes (``gleepglorp-fill``, ``gleepglorp-kinds``, ``mcp``,
``providers``, ``agents``).
"""

from __future__ import annotations

from pathlib import Path

AREAS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js/areas"
STUDIO = AREAS / "studio"
FILL_CORE = AREAS / "shared/gleepglorp-fill-core.js"
FOLLOW_CORE = AREAS / "shared/gleepglorp-follow-core.js"

NOTE_SENTENCE = "Changed by a change you approved in a GleepGlorp chat"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_approval_note_is_built_in_one_place() -> None:
    hits = sorted(
        p.relative_to(AREAS).as_posix() for p in AREAS.rglob("*.js") if NOTE_SENTENCE in _src(p)
    )
    assert hits == ["shared/gleepglorp-follow-core.js"]
    for name in ("mcp-editor-follow", "provider-editor-follow", "agent-editor-follow"):
        assert "App.gleepglorpFollow.buildNote(" in _src(STUDIO / f"{name}.js"), name


def test_the_fill_scaffolding_is_in_the_core_only() -> None:
    for name in (
        "mcp-editor-fill",
        "provider-editor-fill",
        "knowledge-editor-fill",
        "secret-editor-fill",
    ):
        text = _src(STUDIO / f"{name}.js")
        for needle in ("__ggFillSettleTimeoutMs", "aria-describedby", "function whenSettled"):
            assert needle not in text, f"{name}.js still holds {needle}"
        assert "App.gleepglorpFill" in text
    for rel in ("tool-config-fill", "knowledge-settings-fill"):
        text = _src(AREAS / "admin" / f"{rel}.js")
        for needle in ("__ggFillSettleTimeoutMs", "aria-describedby", "function whenSettled"):
            assert needle not in text, f"{rel}.js still holds {needle}"
        assert "App.gleepglorpFill" in text
    core = _src(FILL_CORE)
    for needle in ("__ggFillSettleTimeoutMs", "aria-describedby", "function whenSettled"):
        assert needle in core


def test_the_library_kinds_register_through_the_shared_builder() -> None:
    for name in ("mcp-kinds", "provider-kinds", "knowledge-kinds", "secret-kinds"):
        assert "registerLibraryKind(" in _src(STUDIO / f"{name}.js"), name
    assert "function registerLibraryKind" in _src(AREAS.parent / "gleepglorp-kinds.js")


def test_the_client_kinds_register_in_the_server_registry_order() -> None:
    """DD13: the order the kinds scripts load in ``index.html`` is ``kinds.KINDS``."""
    import re

    from the_one.gleepglorp import kinds

    html = (AREAS.parent.parent / "index.html").read_text(encoding="utf-8")
    # Leg 4b's kinds live under ``areas/admin/``, so the pattern takes any area.
    scripts = re.findall(r'src="/static/js/areas/[a-z]+/([a-z-]+-kinds)\.js"', html)
    assert scripts == [
        "agent-kinds",
        "mcp-kinds",
        "provider-kinds",
        "knowledge-kinds",
        "secret-kinds",
        "tool-config-kinds",
        "app-settings-kinds",
    ]
    registered: list[str] = []
    for name in scripts:
        (path,) = AREAS.glob(f"*/{name}.js")  # the kind file lives under any area
        src = _src(path)
        registered += [a or b for a, b in re.findall(r"register\('(\w+)'|name: '(\w+)'", src)]
    assert tuple(registered) == kinds.KINDS


def test_the_follow_listener_is_registered_once_per_kind_in_the_core() -> None:
    for name in (
        "mcp-editor-follow",
        "provider-editor-follow",
        "knowledge-editor-follow",
        "secret-editor-follow",
    ):
        text = _src(STUDIO / f"{name}.js")
        assert "addEventListener" not in text, name
        assert "App.gleepglorpFollow.listen(" in text, name
    # Leg 4b: the Settings follows. The tool follow and the shared app_settings dispatcher call
    # `listen`; the Knowledge and Date and time pages register with the dispatcher instead.
    for rel in ("admin/tool-config-follow.js", "shared/app-settings-follow.js"):
        text = _src(AREAS / rel)
        assert "addEventListener" not in text, rel
        assert "App.gleepglorpFollow.listen(" in text, rel
    for rel in ("admin/knowledge-settings-follow.js",):
        text = _src(AREAS / rel)
        assert "addEventListener" not in text and "gleepglorpFollow.listen(" not in text, rel
    assert "CONFIG_CHANGED" in _src(FOLLOW_CORE)


def test_exactly_one_follow_listener_is_registered_per_kind() -> None:
    """AC10: ``listen`` is once per kind per page (a second call is a silent no-op), so a second
    registration for a kind is a bug that fails quietly."""
    import re
    from collections import Counter

    js = AREAS.parent
    kinds_listened: Counter[str] = Counter()
    for p in js.rglob("*.js"):
        if p == FOLLOW_CORE:
            continue
        for kind in re.findall(r"gleepglorpFollow\.listen\(\s*'(\w+)'", _src(p)):
            kinds_listened[kind] += 1
    assert kinds_listened, "no listeners found"
    assert {k: n for k, n in kinds_listened.items() if n != 1} == {}
    assert "app_settings" in kinds_listened and "tool_config" in kinds_listened
