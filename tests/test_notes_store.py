"""Notes repository, normalisation, counter and switch (M27 F2 L1, DD1-DD8)."""

from __future__ import annotations

import pytest

from tests._schema_template import connect_template_db
from the_one.agent.config import AgentConfig
from the_one.db._notes import (
    NOTE_MAX_CHARS,
    NOTES_TOTAL_MAX_CHARS,
    NoteDuplicateError,
    NoteLimitError,
    NotesDisabledError,
    normalize_note_text,
)
from the_one.db.repositories import AgentNoteRepository, SQLiteAgentStore

ORIGIN = {
    "origin_kind": "web",
    "origin_session_id": None,
    "origin_label": None,
    "origin_platform": None,
    "origin_peer_id": None,
    "origin_peer_name": None,
}


@pytest.fixture
async def conn(tmp_path):
    c = await connect_template_db(tmp_path / "notes.db")
    store = SQLiteAgentStore(c)
    await store.save(AgentConfig(name="alpha"))
    await store.save(AgentConfig(name="beta"))
    await store.set_notes_enabled("alpha", True)
    await store.set_notes_enabled("beta", True)
    yield c
    await c.close()


@pytest.fixture
def repo(conn) -> AgentNoteRepository:
    return AgentNoteRepository(conn)


async def _save(repo, name, text, *, untrusted=False, sources=(), **origin):
    return await repo.create(
        name, text, untrusted=untrusted, sources=list(sources), **{**ORIGIN, **origin}
    )


async def test_switch_defaults_off_and_targeted_update(conn) -> None:
    store = SQLiteAgentStore(conn)
    await store.save(AgentConfig(name="gamma"))
    assert (await store.load("gamma")).notes_enabled is False
    await store.set_notes_enabled("gamma", True)
    assert (await store.load("gamma")).notes_enabled is True
    with pytest.raises(KeyError):
        await store.set_notes_enabled("nope", True)


async def test_numbers_increment_and_are_never_reused(repo) -> None:
    a, created = await _save(repo, "alpha", "one")
    b, _ = await _save(repo, "alpha", "two")
    assert created and (a.number, b.number) == (1, 2)
    await repo.forget_by_agent("alpha", 2)
    c, _ = await _save(repo, "alpha", "three")
    assert c.number == 3
    # beta has its own counter
    assert (await _save(repo, "beta", "one"))[0].number == 1


async def test_clear_does_not_reset_counter_but_recreate_agent_does(conn, repo) -> None:
    await _save(repo, "alpha", "one")
    await _save(repo, "alpha", "two")
    assert await repo.clear("alpha") == 2
    assert (await _save(repo, "alpha", "again"))[0].number == 3
    store = SQLiteAgentStore(conn)
    await store.delete("alpha")
    await store.save(AgentConfig(name="alpha"))
    await store.set_notes_enabled("alpha", True)
    assert (await _save(repo, "alpha", "fresh"))[0].number == 1


async def test_stale_whole_config_save_does_not_move_counter_back(conn, repo) -> None:
    store = SQLiteAgentStore(conn)
    stale = await store.load("alpha")
    await _save(repo, "alpha", "one")
    await _save(repo, "alpha", "two")
    await store.save(stale)  # whole-row save from before the notes existed
    assert (await _save(repo, "alpha", "three"))[0].number == 3
    async with conn.execute("SELECT notes_next_number FROM agents WHERE name='alpha'") as cur:
        assert (await cur.fetchone())[0] == 4


def test_agent_config_has_no_counter_field() -> None:
    assert "notes_next_number" not in AgentConfig.model_fields
    assert AgentConfig(name="x").notes_enabled is False


async def test_agent_methods_refuse_when_switch_off(conn, repo) -> None:
    n, _ = await _save(repo, "alpha", "kept")
    await SQLiteAgentStore(conn).set_notes_enabled("alpha", False)
    with pytest.raises(NotesDisabledError):
        await _save(repo, "alpha", "new")
    with pytest.raises(NotesDisabledError):
        await repo.update_by_agent("alpha", n.number, "x", untrusted=False, sources=[])
    with pytest.raises(NotesDisabledError):
        await repo.forget_by_agent("alpha", n.number)
    # operator paths are unaffected
    edited, changed = await repo.update_by_operator("alpha", n.id, "edited")
    assert changed and edited.text == "edited" and edited.updated_by == "operator"
    await repo.delete("alpha", n.id)


@pytest.mark.parametrize(
    "raw",
    [
        "a\r\nb",
        "a b",
        "a b",
        "a\x85b",
        "a\vb",
        "a\fb",
        "a\x1cb",
        "a\x00b",
        "a\nb",
    ],
)
def test_normalisation_makes_one_line_without_controls(raw) -> None:
    out = normalize_note_text(raw)
    assert "\n" not in out and "\r" not in out
    assert all(ord(c) >= 32 and ord(c) != 0x7F for c in out)
    assert out.startswith("a") and out.endswith("b")


def test_normalisation_nul_removed_and_zero_width_kept() -> None:
    assert normalize_note_text("a\x00b") == "ab"
    assert normalize_note_text("a​b") == "a​b"
    assert normalize_note_text("x\r\n[9] y") == "x [9] y"


async def test_stored_text_is_single_line(repo) -> None:
    note, _ = await _save(repo, "alpha", "x\r\n[9] y z\x00")
    assert note.text == "x [9] y z"
    assert (await repo.get_by_number("alpha", note.number)).text == "x [9] y z"


async def test_length_limits_use_normalised_text(repo) -> None:
    with pytest.raises(NoteLimitError, match="some text"):
        await _save(repo, "alpha", " \n\t ")
    with pytest.raises(NoteLimitError) as exc:
        await _save(repo, "alpha", "x" * (NOTE_MAX_CHARS + 1))
    assert "x" * 10 not in exc.value.detail
    await _save(repo, "alpha", "y" * NOTE_MAX_CHARS)
    # whitespace runs collapse before the check
    await _save(repo, "alpha", "z" + " " * 600 + "w")


async def test_total_limit_on_create_and_update(repo) -> None:
    for i in range(10):
        await _save(repo, "alpha", f"{i}" + "x" * (NOTE_MAX_CHARS - 1))
    assert await repo.total_chars("alpha") == NOTES_TOTAL_MAX_CHARS
    with pytest.raises(NoteLimitError) as exc:
        await _save(repo, "alpha", "extra")
    assert "4,000" in exc.value.detail and "extra" not in exc.value.detail
    first = await repo.get_by_number("alpha", 1)
    # shrinking is allowed: total - old + new
    short, changed = await repo.update_by_agent("alpha", 1, "short", untrusted=False, sources=[])
    assert changed and short.text == "short"
    # growing back to the max fits exactly; one char over the per-note cap fails
    await repo.update_by_agent("alpha", 1, "q" * NOTE_MAX_CHARS, untrusted=False, sources=[])
    with pytest.raises(NoteLimitError):
        await repo.update_by_agent(
            "alpha", 1, "q" * (NOTE_MAX_CHARS + 1), untrusted=False, sources=[]
        )
    assert first is not None


async def test_dedup_on_create_returns_existing(repo) -> None:
    a, created = await _save(repo, "alpha", "Likes tea.")
    b, created2 = await _save(repo, "alpha", "  likes   TEA!! ")
    assert created and not created2 and b.id == a.id
    assert len(await repo.list_for_agent("alpha")) == 1
    # counter was not consumed by the duplicate
    assert (await _save(repo, "alpha", "other"))[0].number == 2


async def test_update_dedup_excludes_own_row_and_refuses_other(repo) -> None:
    a, _ = await _save(repo, "alpha", "one")
    b, _ = await _save(repo, "alpha", "two")
    # same text (modulo case/punct) as itself: allowed no-op or change, never duplicate-of-self
    same, changed = await repo.update_by_agent(
        "alpha", a.number, "ONE.", untrusted=False, sources=[]
    )
    assert changed and same.text == "ONE."
    with pytest.raises(NoteDuplicateError) as exc:
        await repo.update_by_agent("alpha", b.number, "one!", untrusted=False, sources=[])
    assert exc.value.number == a.number and "one" not in exc.value.detail
    with pytest.raises(NoteDuplicateError):
        await repo.update_by_operator("alpha", b.id, "ONE")


async def test_identical_text_update_is_noop(repo) -> None:
    a, _ = await _save(repo, "alpha", "same", untrusted=True, sources=["fetch_url"])
    out, changed = await repo.update_by_agent(
        "alpha", a.number, " same ", untrusted=False, sources=[]
    )
    assert not changed and out.updated_at == a.updated_at
    out, changed = await repo.update_by_operator("alpha", a.id, "same")
    assert not changed and out.updated_by == "agent"


async def test_agent_update_ors_taint_and_merges_sources(repo) -> None:
    a, _ = await _save(repo, "alpha", "v1", untrusted=True, sources=["fetch_url", "peer:bob"])
    out, _ = await repo.update_by_agent(
        "alpha", a.number, "v2", untrusted=False, sources=["fetch_url", "shell"]
    )
    assert out.untrusted is True  # never laundered
    assert out.untrusted_sources == ["fetch_url", "peer:bob", "shell"]
    assert out.updated_by == "agent" and out.origin_kind == "web"
    clean, _ = await _save(repo, "alpha", "clean")
    flagged, _ = await repo.update_by_agent(
        "alpha", clean.number, "clean2", untrusted=True, sources=["x"]
    )
    assert flagged.untrusted is True and flagged.untrusted_sources == ["x"]


async def test_sources_capped_at_ten(repo) -> None:
    a, _ = await _save(repo, "alpha", "v1", untrusted=True, sources=[f"s{i}" for i in range(15)])
    assert len(a.untrusted_sources) == 10
    out, _ = await repo.update_by_agent(
        "alpha", a.number, "v2", untrusted=True, sources=[f"t{i}" for i in range(15)]
    )
    assert len(out.untrusted_sources) == 10


async def test_operator_edit_clears_flag_and_sets_updated_by(repo) -> None:
    a, _ = await _save(repo, "alpha", "v1", untrusted=True, sources=["fetch_url"])
    out, changed = await repo.update_by_operator("alpha", a.id, "v2")
    assert changed and not out.untrusted and out.updated_by == "operator"
    assert out.untrusted_sources == []
    # A later agent update in a tainted conversation flags it again.
    again, _ = await repo.update_by_agent("alpha", a.number, "v3", untrusted=True, sources=["x"])
    assert again.untrusted and again.untrusted_sources == ["x"]


async def test_identical_text_operator_save_keeps_flag(repo) -> None:
    a, _ = await _save(repo, "alpha", "v1", untrusted=True, sources=["fetch_url"])
    out, changed = await repo.update_by_operator("alpha", a.id, "v1")
    assert not changed and out.untrusted and out.untrusted_sources == ["fetch_url"]


async def test_scoped_by_agent_and_misses(repo) -> None:
    a, _ = await _save(repo, "alpha", "mine")
    assert await repo.get("beta", a.id) is None
    assert await repo.get_by_number("beta", a.number) is None
    with pytest.raises(KeyError):
        await repo.update_by_operator("beta", a.id, "x")
    with pytest.raises(KeyError):
        await repo.delete("beta", a.id)
    with pytest.raises(KeyError):
        await repo.update_by_agent("beta", a.number, "x", untrusted=False, sources=[])
    with pytest.raises(KeyError):
        await repo.forget_by_agent("beta", a.number)
    with pytest.raises(KeyError):
        await repo.forget_by_agent("alpha", 99)
    assert await repo.list_for_agent("beta") == []


async def test_create_validates_origin_kind_and_unknown_agent(repo) -> None:
    with pytest.raises(ValueError, match="origin_kind"):
        await _save(repo, "alpha", "x", origin_kind="bogus")
    with pytest.raises(KeyError):
        await _save(repo, "ghost", "x")


async def test_origin_label_live_title_then_fallback_after_purge(conn, repo) -> None:
    await conn.execute(
        "INSERT INTO chat_sessions (id, agent_name, title, messages, created_at, updated_at) "
        "VALUES ('cs1', 'alpha', 'Live title', '[]', 't', 't')"
    )
    await conn.commit()
    n, _ = await _save(repo, "alpha", "x", origin_session_id="cs1", origin_label="New chat")
    listed = (await repo.list_for_agent("alpha"))[0]
    assert (listed.origin_label, listed.origin_exists) == ("Live title", True)
    await conn.execute("DELETE FROM chat_sessions WHERE id = 'cs1'")
    await conn.commit()
    listed = (await repo.list_for_agent("alpha"))[0]
    assert (listed.origin_label, listed.origin_exists) == ("New chat", False)
    assert listed.id == n.id
    n2, _ = await _save(repo, "alpha", "y", origin_session_id="gone", origin_label=None)
    assert (await repo.get("alpha", n2.id)).origin_label == "Untitled chat"


async def test_connector_origin_columns_round_trip(repo) -> None:
    n, _ = await _save(
        repo,
        "alpha",
        "x",
        untrusted=True,
        sources=["peer:Bob"],
        origin_kind="connector",
        origin_platform="discord",
        origin_peer_id="42",
        origin_peer_name="Bob",
    )
    assert (n.origin_kind, n.origin_platform, n.origin_peer_id, n.origin_peer_name) == (
        "connector",
        "discord",
        "42",
        "Bob",
    )
