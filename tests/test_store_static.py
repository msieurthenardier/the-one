"""Static guards for App.store (M25 F2 L7, AC2/AC4; M25 F3 L2, AC2/AC3/AC6).

Flight 3 leg 2 adds the Library collections (``knowledge-bases``,
``mcp-sources``, ``connectors``): the grep proof that no list fetch bypasses
the store, one pin per row of the invalidation map (``the_one/agents.md``
"Client data store"), the save-create name hints, and the router's
``sync`` announce ordering (DD8).

Flight 4 leg 1 (DD4) adds the sixth collection, ``sessions``
(``/api/chat/sessions``), ``App.store.prime``, the chat area's prime from the
WebSocket ``session_list`` reply, and the agent rename / Purge now rows.

Flight 4 leg 3b adds DD4's ``start_session`` row (a start's join refreshes the
list, whose reply primes ``sessions``) and the grep pins of squawk 0111's
retired start path (``new_session``, the stalled-join timer).
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parent.parent / "the_one/interfaces/web/static/js"
LITERAL_LIST = re.compile(
    r"""fetch\(\s*['"]/api/(agents|providers|knowledge-bases|mcp-sources|connectors|chat/sessions)['"]\s*\)"""
)


def _src(rel: str) -> str:
    return (JS / rel).read_text()


def _studio_src() -> str:
    """studio.js plus every studio module, for text-presence pins that may span
    files (M31 F2 L02a: studio.js is being split into modules; a pin that asserts
    a text exists, or does not exist, must cover all of them)."""
    parts = [_src("areas/studio.js")]
    parts += [p.read_text() for p in sorted((JS / "areas/studio").glob("*.js"))]
    return "\n".join(parts)


def _window(src: str, anchor: str, end: str) -> str:
    """The text from *anchor* up to the first *end* after it (both must exist)."""
    start = src.index(anchor)
    stop = src.index(end, start)
    return src[start:stop]


def test_no_literal_list_fetches_outside_store() -> None:
    offenders = [
        str(p.relative_to(JS))
        for p in JS.rglob("*.js")
        if p.name != "store.js" and LITERAL_LIST.search(p.read_text())
    ]
    assert offenders == []


def test_literal_list_guard_covers_chat_sessions() -> None:
    """The guard really matches a literal sessions fetch (so a green
    ``test_no_literal_list_fetches_outside_store`` means none exists)."""
    assert LITERAL_LIST.search("fetch('/api/chat/sessions')")
    assert LITERAL_LIST.search('fetch( "/api/chat/sessions" )')
    # A per-agent purge or a per-session URL is not the list fetch.
    assert not LITERAL_LIST.search("fetch('/api/agents/' + n + '/chat/sessions', {")


def test_store_urls_name_the_six_collections() -> None:
    src = _src("store.js")
    urls = _window(src, "var URLS", "};")
    for name, url in (
        ("agents", "/api/agents"),
        ("providers", "/api/providers"),
        ("'knowledge-bases'", "/api/knowledge-bases"),
        ("'mcp-sources'", "/api/mcp-sources"),
        ("connectors", "/api/connectors"),
        ("sessions", "/api/chat/sessions"),
    ):
        assert f"{name}: '{url}'" in urls, name
    assert len(re.findall(r"'/api/[^']+'", urls)) == 6
    # The plain MCP list: the surfaces variant stays a direct fetch.
    assert "include_agent_surfaces" not in urls


def test_store_prime_bumps_the_generation_and_is_exported() -> None:
    """AC20: prime replaces the value (loaded/ok/fresh), bumps gen and clears
    the in-flight request like invalidate, then notifies."""
    src = _src("store.js")
    body = _window(src, "function prime(name, rows)", "\n  }\n")
    assert "var c = col(name);" in body  # an unknown name throws through col()
    for needle in (
        "c.gen += 1;",
        "c.inflight = null;",
        "c.value = copy(rows);",
        "c.loaded = true; c.ok = true; c.error = null; c.fresh = true;",
    ):
        assert needle in body, needle
    assert body.index("c.gen += 1;") < body.index("c.subs.slice().forEach")
    assert "prime: prime" in _window(src, "window.App.store = {", "};")


def test_chat_session_list_primes_sessions_in_the_summary_shape() -> None:
    """AC21: the session_list handler primes 'sessions' with the REST summary
    keys, before it renders anything."""
    src = _src("areas/chat.js")
    handler = _window(
        src, "if (data.type === 'session_list') {", "if (data.type === 'session_joined')"
    )
    assert handler.count("App.store.prime('sessions'") == 1
    prime = _window(handler, "App.store.prime('sessions'", "}));")
    for key in ("id", "agent_name", "title", "created_at", "updated_at", "platform"):
        assert re.search(rf"\b{key}: s\.{key}\b", prime), key
    assert prime.count(": s.") == 6
    # Since M25 F4 L4a the handler renders nothing itself: the prime notifies
    # the `sessions` subscription, which renders the Chats list (AC6).
    assert "renderChatsList(" not in handler
    assert "renderList(" not in src and "renderSessionList" not in src


def test_chats_list_renders_from_the_sessions_subscription_only() -> None:
    """M25 F4 L4a (AC6): ONE renderChatsList reads the store's ``sessions``
    (peek) plus the session state; the area subscribes to ``sessions`` for its
    whole life (the chat area is never destroyed, so it never unsubscribes),
    and every state transition that moves the pending row or the selection
    calls it."""
    src = _src("areas/chat.js")
    assert src.count("function renderChatsList()") == 1
    body = _window(src, "function renderChatsList()", "\n    }")
    assert "App.store.peek('sessions')" in body
    assert "chatState.state()" in body and "chatState.boundId()" in body
    assert "App.chat.chatsList.PENDING_ID" in body
    assert src.count("App.store.subscribe('sessions'") == 1
    sub = _window(src, "App.store.subscribe('sessions'", ";")
    assert "renderChatsList()" in sub
    # The subscription is never released (the area lives as long as the page):
    # its unsubscribe handle is not even kept.
    assert "= App.store.subscribe('sessions'" not in src
    for fn in (
        "function renderPending()",  # pick
        "function openConversation(id)",  # open
        "function resetToIdle()",  # idle
        "function clearConversation()",  # idle (delete, join_failed)
    ):
        assert "renderChatsList();" in _window(src, fn, "\n    }\n"), fn
    joined = _window(
        src, "if (data.type === 'session_joined') {", "if (data.type === 'start_failed')"
    )
    assert "renderChatsList();" in joined  # joined, and the starting -> joined swap


def test_start_session_join_refreshes_the_list_that_primes_sessions() -> None:
    """DD4's start_session invalidation row (M25 F4 L3b, AC19): every
    accepted session_joined -- a start's included, whether or not its history
    renders -- ends with the list refresh, whose session_list reply primes
    'sessions'. No path between the gate and the refresh skips it except a
    start failure (nothing was created)."""
    src = _src("areas/chat.js")
    handler = _window(
        src, "if (data.type === 'session_joined') {", "if (data.type === 'start_failed')"
    )
    accepted = handler[handler.index("if (joinedEff.startFailed)") :]
    body = accepted[accepted.index("return;") + len("return;") :]
    # Only renderHistory is conditional on the start (AC2).
    assert "if (joinedEff.render === 'history') renderHistory(" in body
    assert "refreshSessionList();" in body, "the accepted session_joined path must refresh"
    assert body.index("refreshSessionList();") < body.rindex("return;")
    assert body.count("return;") == 1  # the refresh is on the one exit
    refresh = _window(src, "function refreshSessionList()", "\n    }")
    assert "action: 'list_sessions'" in refresh


# ── The retired start path (squawk 0111, M25 F4 L3b AC13/AC20) ──────────────


def test_retired_new_session_path_is_gone_from_the_client() -> None:
    """No client path sends ``new_session``, and squawk 0111's stalled-join
    recovery (the intent drain, the bounded 10s timer and its test hook) is
    gone with it: a first send is one idempotent ``start_session`` and only a
    socket close re-sends it."""
    gone = (
        "new_session",
        "pendingStart",
        "armPendingStartTimer",
        "clearPendingStartTimer",
        "DEFAULT_START_JOIN_TIMEOUT_MS",
        "chatStartJoinTimeoutMs",
        "startSessionWith",
    )
    hits = [
        (str(path.relative_to(JS)), token)
        for path in JS.rglob("*.js")
        for token in gone
        if token in path.read_text()
    ]
    assert hits == []
    # ...and the replacement is in place.
    chat = _src("areas/chat.js")
    assert "action: 'start_session'" in _src("areas/chat/session-state.js")
    assert "sendBinding({ action: 'leave' })" in chat


def test_library_fetch_sites_read_through_the_store() -> None:
    src = _src("areas/studio.js")
    # M31 F2 L02a: fetchKnowledgeBases moved to the agent-data module.
    assert "App.store.get('knowledge-bases'" in _window(
        _src("areas/studio/agent-data.js"), "function fetchKnowledgeBases(force)", "\n    }"
    )
    # M25 F3 L4a: the Library list's fetch policy (DD9's freshness bound). Pane
    # creation and studio activate force-get the three collections and plain-get
    # agents; a mutation reloads with a plain get after the editor's
    # invalidate; the pending-item rule force-gets only for a fresh hydrate.
    # M31 F2 L02b: the list's functions moved to the library-pane module.
    pane = _src("areas/studio/library-pane.js")
    load = _window(pane, "function loadLibrary(force)", "\n    }")
    assert "App.store.get(name, { force: !!force })" in load
    assert "App.store.get('agents')" in load
    assert "App.store.get(name)" in _window(pane, "function reloadLibrary(name)", "\n    }")
    create = _window(pane, "function createLibraryList()", "\n    }")
    assert "loadLibrary(true)" in create
    refresh = _window(src, "self._refresh = function ()", "\n    };")
    assert "libraryPane.load(true)" in refresh
    # ...and the pending-item rule is in connector-glue.js.
    pending = _window(
        _src("areas/studio/connector-glue.js"),
        "function resolvePendingLibraryItem(section, fresh)",
        "\n    }\n",
    )
    assert "App.store.get(k.collection, { force: true })" in pending
    assert "App.store.get(k.collection)" in pending
    # The retired grids' self-refetching paths are gone.
    all_studio = _studio_src()
    for gone in ("fetchKnowledgeBases_", "fetchMcpSources_", "fetchConnectors_"):
        assert gone not in all_studio, gone
    # The agent editor's detail-shaped variant stays a direct fetch.
    # (0145: through App.api.fetchJson so a non-ok response throws; never App.store.)
    assert "App.api.fetchJson('/api/mcp-sources?include_agent_surfaces=1')" in _src(
        "areas/studio/agent-data.js"
    )
    assert "App.store.get('mcp-sources?include_agent_surfaces" not in all_studio


def test_mcp_list_stale_callback_follows_the_non_save_invalidations() -> None:
    """M25 F3 L4a: a connect success and Reset connection invalidate
    'mcp-sources' and then tell the studio (``onListStale``) to reload the list,
    so the row's tool count follows a Refresh."""
    src = _src("areas/studio/mcp-server-editor.js")
    connect = _window(src, "function onTestConnectSuccess()", "fetch(")
    assert "callbacks.onListStale()" in connect
    reset = _window(src, "'/connection', { method: 'DELETE' })", "return fetch(")
    assert reset.index("App.store.invalidate('mcp-sources')") < reset.index(
        "callbacks.onListStale()"
    )
    # M31 F2 L02b: the MCP section glue moved to mcp-glue.js (which keeps the
    # local ``reloadLibrary`` alias, so the literal is unchanged).
    studio = _src("areas/studio/mcp-glue.js")
    assert "onListStale: function () { reloadLibrary('mcp-sources'); }" in studio


def test_oauth_and_provider_mutations_invalidate_providers() -> None:
    src = _src("areas/studio/provider-editor.js")
    assert src.count("App.store.invalidate('providers')") >= 4  # code, reset, save, delete


def test_cross_collection_mutations_invalidate_agents() -> None:
    for rel, minimum in (
        ("areas/studio/knowledge-detail.js", 2),  # M31 F3 L02: rename and delete
        ("areas/studio/mcp-server-editor.js", 2),
        # M31 F2 L02a: the self-configuration refresh site moved to agent-data (1);
        # M31 F2 L03: the four editor sites (create, rename, save, delete) moved to
        # the controller and studio.js keeps none. Per file, so a lost site is
        # still caught.
        ("areas/studio/agent-data.js", 1),
        ("areas/studio/agent-editor-controller.js", 4),
        ("areas/studio.js", 0),
    ):
        src = _src(rel)
        assert src.count("App.store.invalidate('agents')") >= minimum, rel


# One pin per invalidation-map row: (file, anchor, end, collections). Each
# invalidation sits on the success path between the request and the callback.
INVALIDATION_ROWS = (
    (  # knowledge base: create
        "areas/studio/knowledge-create.js",
        "App.api.fetchJson('/api/knowledge-bases', {",  # M31 F3 L05a: fetchJson form
        "onCreateSuccess(kb)",
        ("knowledge-bases",),
    ),
    (  # knowledge base: rename
        "areas/studio/knowledge-detail.js",
        "method: 'PUT',",
        "callbacks.onSaveSuccess(updated)",
        ("knowledge-bases", "agents"),
    ),
    (  # knowledge base: delete
        "areas/studio/knowledge-detail.js",
        "encodeURIComponent(kb.id), { method: 'DELETE' })",
        "callbacks.onDeleteSuccess()",
        ("knowledge-bases", "agents"),
    ),
    (  # MCP source: create and save
        "areas/studio/mcp-server-editor.js",
        "var method = isEdit ? 'PUT' : 'POST';",
        "callbacks.onSaveSuccess(updated, !isEdit)",
        ("mcp-sources",),
    ),
    (  # MCP source: delete
        "areas/studio/mcp-server-editor.js",
        "encodeURIComponent(source.id), { method: 'DELETE' })",
        "callbacks.onDeleteSuccess()",
        ("mcp-sources", "agents"),
    ),
    (  # MCP source: connection delete (Reset)
        "areas/studio/mcp-server-editor.js",
        "'/connection', { method: 'DELETE' })",
        "return fetch(",
        ("mcp-sources", "agents"),
    ),
    (  # MCP source: Refresh tools / test-connect success (writes config._cache)
        "areas/studio/mcp-server-editor.js",
        "'/test/connect', fetchOpts)",
        "renderToolsListHtml(data.tools)",
        ("mcp-sources",),
    ),
    (  # MCP source: the agent editor's tools load (also /test/connect; agent-data now)
        "areas/studio/agent-data.js",
        "'/test/connect', {",
        "return data;",
        ("mcp-sources",),
    ),
    (  # connector: create and save
        "areas/studio/connector-editor.js",
        "var method = isCreate ? 'POST' : 'PUT';",
        "callbacks.onSaveSuccess(updated, isCreate)",
        ("connectors",),
    ),
    (  # connector: delete
        "areas/studio/connector-editor.js",
        "encodeURIComponent(cfg.id), { method: 'DELETE' }",
        "callbacks.onDeleteSuccess()",
        ("connectors",),
    ),
    (  # provider: create and save (invalidated before the save-create sync)
        "areas/studio/provider-editor.js",
        "var method = isEdit ? 'PUT' : 'POST';",
        "callbacks.onSaveSuccess(updated, !isEdit)",
        ("providers",),
    ),
    (  # agent rename: re-points chat_sessions.agent_name (M25 F4 L1, DD4)
        "areas/studio/agent-editor-controller.js",
        "'/rename', {",
        "self._selectedAgent = renamed;",
        ("agents", "sessions"),
    ),
    (  # agent Purge now: the agent's sessions are deleted (M25 F4 L1, DD4)
        "areas/studio/agent-editor-controller.js",
        "var n = body && typeof body.deleted === 'number' ? body.deleted : 0;",
        "App.ui.flash('Purged '",
        ("sessions",),
    ),
)


def test_each_mutation_invalidates_its_collections() -> None:
    for rel, anchor, end, names in INVALIDATION_ROWS:
        window = _window(_src(rel), anchor, end)
        for name in names:
            assert f"App.store.invalidate('{name}')" in window, (rel, anchor, name)


def test_save_syncs_pass_the_item_name_hint() -> None:
    # The Settings admin area has no create-then-sync editor any more (providers
    # moved to Library, sortie 02); the provider save-create sync lives in the
    # section module, beside the connector one in studio.js.
    assert "App.router.sync('admin', self.serializeState(), { name: updated.name })" not in _src(
        "areas/admin.js"
    )
    # M31 F2 L02b: the MCP save-create sync moved to mcp-glue.js.
    assert "App.router.sync('studio', self.serializeState(), { name: updated.name })" in _src(
        "areas/studio/mcp-glue.js"
    )
    providers = _src("areas/studio/providers-section.js")
    window = _window(providers, "App.router.sync('studio', 'providers/' +", ");")
    assert "{ name: updated.name }" in window


# ── router (DD8) ─────────────────────────────────────────────────────────


def _router_fn(name: str) -> str:
    return _window(_src("router.js"), f"function {name}(", "\n  }\n")


def test_sync_reads_the_previous_key_before_overwriting_it() -> None:
    body = _router_fn("sync")
    read = body.index("var prevKey = lastAnnounceKey;")
    check = body.index("isCreateToItem(prevKey, dd.key)")
    write = body.index("lastAnnounceKey = dd.key;")
    assert read < check < write
    # Nothing writes the key before it is read.
    assert "lastAnnounceKey =" not in body[:read]
    # The only spoken path in sync is the create -> item transition.
    assert body.count("speak(") == 1


def test_describe_route_reads_the_store_guarded_and_known_collections_only() -> None:
    src = _src("router.js")
    store_name = _router_fn("storeName")
    assert "window.App && window.App.store" in store_name
    assert "typeof store.peek !== 'function'" in store_name
    table = _window(src, "var ITEM_COLLECTIONS = {", "};")
    named = set(re.findall(r"collection: '([\w-]+)'", table))
    assert named == {"providers", "knowledge-bases", "mcp-sources", "connectors"}
    urls = _window(_src("store.js"), "var URLS = {", "};")
    for name in named:
        assert re.search(rf"'?{re.escape(name)}'?: '/api/", urls), name


def test_studio_shell_keeps_its_public_surface() -> None:
    """M31 F2 L03: the editor modules own the code, but the shell (studio.js) still
    exposes exactly the area surface tests, the router and other areas reach: the
    `self._*` hooks, `App.studio.clearAgentFilter` (with its load-time stub) and the
    `_refresh` / `_dirty` seams. A move that drops one is caught here, not in a lane."""
    src = _src("areas/studio.js")
    for needle in (
        "self._syncAgentSelection = ",
        "self._enterCreate = ",
        "self._setActiveTab = ",
        "self._tryConsumePendingSelect = ",
        "App.studio.clearAgentFilter = agentsListMod.clearFilter",
        "self._refresh = function",
        "Object.defineProperty(self, '_dirty'",
        "window.App.studio.clearAgentFilter = function () {};",
    ):
        assert needle in src, needle
    assert len(src.splitlines()) <= 800  # the leg 03 shell budget
