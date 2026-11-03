"""Unit tests for the Ollama pull catalog (``the_one/llm/ollama_library.py``).

No test reaches the network: every HTTP client is built over ``httpx.MockTransport``
through the module's ``_new_client`` seam.
"""

from __future__ import annotations

import asyncio
import json
import re
import time as real_time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from the_one.llm import ollama_library as lib

FIXTURE = Path(__file__).parent / "fixtures" / "ollama_library_excerpt.html"


# ── Helpers ───────────────────────────────────────────────────────────────


def li(name: str, tags: list[str] | None = None, cloud: bool = False) -> str:
    badge = '<span class="x text-cyan-500 y">cloud</span>' if cloud else ""
    spans = "".join(f'<span class="x text-blue-600 y">{t}</span>' for t in tags or [])
    return (
        '<li  class="flex items-baseline border-b py-6">'
        f'<a href="/library/{name}" class="group">{badge}{spans}</a></li>\n'
    )


def page(*models: tuple[str, list[str], bool]) -> str:
    return "<ul>" + "".join(li(n, t, c) for n, t, c in models) + "</ul>"


def manifest_body(layers: list[int], config: int = 485) -> dict:
    return {"config": {"size": config}, "layers": [{"size": s} for s in layers]}


class Fake:
    """A scripted ollama.com + registry. Scripts per ``name:tag`` key."""

    def __init__(self, page_html="__none__", tags=(), default=None):
        self.page_html = page_html
        self.tags = None if tags is None else list(tags)
        self.default = default if default is not None else manifest_body([1000])
        self.scripts: dict[str, object] = {}
        self.gates: dict[str, asyncio.Event] = {}
        self.delays: dict[str, float] = {}
        self.log: list[tuple[str, str]] = []  # (host, path)
        self.manifest_calls: Counter[str] = Counter()
        self.accepts: list[str | None] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        self.log.append((url.host, url.path))
        if url.host == "ollama.com" and url.path == "/library":
            if self.page_html == "__none__" or self.page_html is None:
                return httpx.Response(500)
            return httpx.Response(200, text=self.page_html)
        if url.host == "ollama.com" and url.path == "/api/tags":
            if self.tags is None:
                return httpx.Response(500)
            return httpx.Response(200, json={"models": [{"name": n} for n in self.tags]})
        m = re.fullmatch(r"/v2/library/([^/]+)/manifests/([^/]+)", url.path)
        assert url.host == "registry.ollama.ai" and m, f"unexpected request {url}"
        key = f"{m.group(1)}:{m.group(2)}"
        self.accepts.append(request.headers.get("accept"))
        n = self.manifest_calls[key]
        self.manifest_calls[key] += 1
        gate = self.gates.get(key)
        if gate is not None and n == 0:
            await gate.wait()
        if key in self.delays:
            await asyncio.sleep(self.delays[key])
        script = self.scripts.get(key, self.default)
        if isinstance(script, list):
            script = script[min(n, len(script) - 1)]
        if isinstance(script, Exception):
            raise script
        if isinstance(script, int):
            return httpx.Response(
                script, headers={"location": "https://x/y"} if script == 302 else {}
            )
        if isinstance(script, str):
            return httpx.Response(200, text=script)
        return httpx.Response(200, json=script)

    @property
    def registry_requests(self) -> int:
        return sum(self.manifest_calls.values())

    @property
    def page_requests(self) -> int:
        return sum(1 for h, p in self.log if p == "/library")


def install(monkeypatch, fake: Fake) -> Fake:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        lib, "_new_client", lambda **kw: real(transport=httpx.MockTransport(fake.handler), **kw)
    )
    return fake


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.delenv("THE_ONE_OLLAMA_LIBRARY_TEST_JSON", raising=False)
    lib._reset_for_tests(cache_path=tmp_path / "ollama-sizes.json")
    yield
    lib._reset_for_tests(cache_path=None)


def cache_file() -> Path:
    return lib._cache_path()


def by_name(result: dict) -> dict[str, dict]:
    return {m["name"]: m for m in result["models"]}


# ── Parser ────────────────────────────────────────────────────────────────


class TestParser:
    def test_fixture_entries_in_page_order(self) -> None:
        entries = lib.parse_library_page(FIXTURE.read_text())
        names = [e["name"] for e in entries]
        assert names[:3] == ["nomic-embed-text", "llama3.2:1b", "llama3.2:3b"]
        assert "gemma3:270m" in names and "gemma3:27b" in names and "qwen3:235b" in names
        assert names.index("gemma3:1b") < names.index("gemma3:12b")
        assert len(names) == len(set(names))

    def test_fixture_cloud_badges(self) -> None:
        entries = {e["name"]: e["cloud"] for e in lib.parse_library_page(FIXTURE.read_text())}
        assert entries["gemma4:e2b"] is True and entries["gemma4:31b"] is True
        assert entries["kimi-k3"] is True  # untagged, cloud-badged: bare name
        assert entries["llama3.2:1b"] is False
        assert entries["nomic-embed-text"] is False

    def test_spans_do_not_bleed_into_next_entry(self) -> None:
        html = page(("aaa", ["1b"], True), ("bbb", [], False))
        entries = {e["name"]: e["cloud"] for e in lib.parse_library_page(html)}
        assert entries == {"aaa:1b": True, "bbb": False}

    def test_tolerates_href_suffixes_and_quotes(self) -> None:
        def block(a: str) -> str:
            return f'<li  class="flex items-baseline">{a}</li>'

        html = "".join(
            block(a)
            for a in (
                "<a class='x' href='/library/phi4'>a</a>",
                '<a href="/library/deepseek-r1?tab=tags" class="y">b</a>',
                '<a data-x="1" href="/library/bge-m3#top">c</a>',
                '<a href="https://ollama.com/library/mistral/">d</a>',
                '<a href="/library/phi4">dup</a>',
            )
        )
        names = [e["name"] for e in lib.parse_library_page(html)]
        assert names == ["phi4", "deepseek-r1", "bge-m3", "mistral"]

    def test_skips_non_library_and_multi_segment_links(self) -> None:
        html = "".join(
            f'<li  class="flex items-baseline">{a}</li>'
            for a in (
                '<a href="/library">all</a>',
                '<a href="/blog">b</a>',
                '<a href="/library/x/tags">tags</a>',
                '<a href="/search?q=/library/x">s</a>',
            )
        )
        assert lib.parse_library_page(html) == []

    def test_invalid_names_and_tags_are_dropped(self) -> None:
        html = page(("Bad_Name", ["1b"], False), ("ok-name", ["1b", "bad tag!", "-x"], False))
        assert [e["name"] for e in lib.parse_library_page(html)] == ["ok-name:1b"]

    def test_empty_input(self) -> None:
        assert lib.parse_library_page("") == []
        assert lib.parse_library_page("<html>maintenance</html>") == []


class TestValidation:
    @pytest.mark.parametrize(
        "model,expected",
        [
            ("llama3.2", ("llama3.2", None)),
            ("llama3.2:1b", ("llama3.2", "1b")),
            ("mixtral:8x22b", ("mixtral", "8x22b")),
            ("qwen3:0.6b", ("qwen3", "0.6b")),
            (" gemma4:e2b ", ("gemma4", "e2b")),
        ],
    )
    def test_valid(self, model, expected) -> None:
        assert lib.split_model(model) == expected

    @pytest.mark.parametrize(
        "model",
        [
            "",
            "   ",
            "Upper",
            "a/b",
            "ns/model:tag",
            "model:",
            "model:a b",
            "model:ta\ng",
            "mod\nel",
            "../x",
            "x:../y",
            "a" * 129,
            "x:" + "t" * 129,
            ":tag",
        ],
    )
    def test_invalid(self, model) -> None:
        with pytest.raises(ValueError):
            lib.split_model(model)

    def test_key_normalises_bare_to_latest(self) -> None:
        assert lib._key("kimi-k3") == "kimi-k3:latest"
        assert lib._key("kimi-k3:latest") == "kimi-k3:latest"


# ── Status mapping / size ─────────────────────────────────────────────────


class TestManifestStatus:
    async def _status(self, monkeypatch, script, cloud_badge=False, tags=()):
        fake = install(
            monkeypatch,
            Fake(page(("m", ["1b"], cloud_badge)), tags=tags),
        )
        fake.scripts["m:1b"] = script
        result = await lib.search()
        return by_name(result)["m:1b"], fake

    async def test_ok_is_layers_plus_config(self, monkeypatch) -> None:
        entry, fake = await self._status(monkeypatch, manifest_body([1_000, 2_000], config=485))
        assert entry == {"name": "m:1b", "size": 3_485, "status": "ok"}
        assert fake.accepts and all(a == lib.ACCEPT for a in fake.accepts)

    async def test_all_requests_go_to_fixed_hosts(self, monkeypatch) -> None:
        _, fake = await self._status(monkeypatch, manifest_body([1]))
        assert {h for h, _ in fake.log} <= {"ollama.com", "registry.ollama.ai"}

    async def test_404_with_page_badge_is_cloud(self, monkeypatch) -> None:
        entry, _ = await self._status(monkeypatch, 404, cloud_badge=True)
        assert entry["status"] == "cloud" and entry["size"] is None

    async def test_404_listed_in_api_tags_is_cloud(self, monkeypatch) -> None:
        entry, _ = await self._status(monkeypatch, 404, tags=["m:1b"])
        assert entry["status"] == "cloud"

    async def test_404_without_signal_is_missing(self, monkeypatch) -> None:
        entry, _ = await self._status(monkeypatch, 404)
        assert entry["status"] == "missing"

    async def test_cloud_badge_with_200_is_ok(self, monkeypatch) -> None:
        entry, _ = await self._status(monkeypatch, manifest_body([5]), cloud_badge=True)
        assert entry["status"] == "ok" and entry["size"] == 5 + 485

    @pytest.mark.parametrize(
        "script",
        [
            403,
            429,
            500,
            503,
            302,
            httpx.ConnectError("down"),
            httpx.ReadTimeout("slow"),
            "not json",
            {"layers": "nope"},
            {"config": {"size": 1}},
            {"config": {"size": "x"}, "layers": []},
        ],
    )
    async def test_everything_else_is_unknown(self, monkeypatch, script) -> None:
        entry, _ = await self._status(monkeypatch, script)
        assert entry["status"] == "unknown" and entry["size"] is None
        assert (
            not cache_file().exists() or "m:1b" not in json.loads(cache_file().read_text())["sizes"]
        )


class TestSizeRoute:
    async def test_echoes_bare_name_and_keys_latest(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(default=manifest_body([10])))
        out = await lib.size("nomic-embed-text")
        assert out == {"name": "nomic-embed-text", "size": 495, "status": "ok"}
        assert list(fake.manifest_calls) == ["nomic-embed-text:latest"]
        assert "nomic-embed-text:latest" in json.loads(cache_file().read_text())["sizes"]

    async def test_invalid_model_raises_value_error(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake())
        with pytest.raises(ValueError):
            await lib.size("a/b:c")
        assert fake.log == []

    async def test_failed_recheck_keeps_cached_ok(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(default=manifest_body([10])))
        assert (await lib.size("m:1b"))["status"] == "ok"
        fake.scripts["m:1b"] = httpx.ConnectError("down")
        out = await lib.size("m:1b")
        assert out == {"name": "m:1b", "size": 495, "status": "ok"}

    async def test_failed_recheck_with_nothing_known_is_unknown(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake())
        fake.scripts["m:1b"] = 503
        out = await lib.size("m:1b")
        assert out == {"name": "m:1b", "size": None, "status": "unknown"}
        assert not cache_file().exists() or json.loads(cache_file().read_text())["sizes"] == {}

    async def test_takes_cloud_signal_from_last_listing(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(page(("cl", ["1b"], True))))
        fake.scripts["cl:1b"] = 404
        await lib.search()
        lib._sizes.clear()
        out = await lib.size("cl:1b")
        assert out["status"] == "cloud"

    async def test_never_starts_a_fill_or_prunes(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        await lib.search()
        calls = list(fake.log)
        await lib.size("other:1b")
        assert lib._fill is None or lib._fill.done()
        assert fake.log[len(calls) :] == [("registry.ollama.ai", "/v2/library/other/manifests/1b")]
        assert "a:1b" in lib._sizes  # not pruned


# ── Entries / merge / sort ────────────────────────────────────────────────


class TestSearch:
    async def test_entries_merge_dedupe_and_order(self, monkeypatch) -> None:
        html = page(
            ("zeta", [], False),
            ("gemma3", ["1b", "4b", "12b"], False),
            ("kimi-k3", [], True),
        )
        install(
            monkeypatch,
            Fake(html, tags=["kimi-k3", "kimi-k3:latest", "gemma3:e2b", "only-tags:9b"]),
        )
        result = await lib.search()
        names = [m["name"] for m in result["models"]]
        assert result["loading"] is False
        # sorted by model-name part; each model keeps page order, tags-only names after it.
        assert names == [
            "gemma3:1b",
            "gemma3:4b",
            "gemma3:12b",
            "gemma3:e2b",
            "kimi-k3",
            "only-tags:9b",
            "zeta",
        ]

    async def test_sort_does_not_interleave_prefixed_models(self, monkeypatch) -> None:
        html = page(
            ("llama3.2-vision", ["11b"], False),
            ("llama3.2", ["1b", "3b"], False),
            ("llama3", ["8b"], False),
        )
        install(monkeypatch, Fake(html))
        names = [m["name"] for m in (await lib.search())["models"]]
        assert names == ["llama3:8b", "llama3.2:1b", "llama3.2:3b", "llama3.2-vision:11b"]

    async def test_q_is_case_insensitive_substring(self, monkeypatch) -> None:
        install(monkeypatch, Fake(page(("gemma3", ["1b"], False), ("qwen3", ["1b"], False))))
        names = [m["name"] for m in (await lib.search("GEMMA"))["models"]]
        assert names == ["gemma3:1b"]

    async def test_fixture_page_end_to_end(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(FIXTURE.read_text(), tags=["kimi-k3", "gemma4:e2b"]))
        for k in ("kimi-k3:latest", "gemma4:e2b", "gemma4:e4b", "gemma4:31b"):
            fake.scripts[k] = 404
        got = by_name(await lib.search())
        assert got["llama3.2:1b"]["status"] == "ok"
        assert got["kimi-k3"]["status"] == "cloud"
        assert got["gemma4:e2b"]["status"] == "cloud"
        assert len([n for n in got if n.startswith("kimi-k3")]) == 1

    async def test_page_failure_with_no_listing_serves_tags_only(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(None, tags=["kimi-k3", "gpt-oss:20b"]))
        fake.scripts["kimi-k3:latest"] = 404
        result = await lib.search()
        assert sorted(by_name(result)) == ["gpt-oss:20b", "kimi-k3"]
        assert by_name(result)["kimi-k3"]["status"] == "cloud"

    async def test_both_sources_fail_returns_empty(self, monkeypatch) -> None:
        install(monkeypatch, Fake(None, tags=None))
        assert await lib.search() == {"loading": False, "models": []}

    async def test_page_failure_after_success_falls_back_to_persisted_listing(
        self, monkeypatch, tmp_path
    ) -> None:
        install(monkeypatch, Fake(page(("a", ["1b"], False), ("b", ["2b"], False))))
        await lib.search()
        # "restart" with a stale listing and a dead page
        lib._reset_for_tests(cache_path=tmp_path / "ollama-sizes.json")
        raw = json.loads(cache_file().read_text())
        raw["library"]["fetched_at"] = real_time.time() - 99999
        cache_file().write_text(json.dumps(raw))
        install(monkeypatch, Fake(None, tags=None))
        result = await lib.search()
        assert sorted(by_name(result)) == ["a:1b", "b:2b"]
        assert all(m["status"] == "ok" for m in result["models"])

    async def test_zero_parse_warns_once_serves_fallback_and_does_not_prune(
        self, monkeypatch, caplog
    ) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False), ("b", ["2b"], False))))
        await lib.search()
        lib._record("gone:1b", "ok", 5)
        # listing stale; the page now fetches fine (200) but parses to nothing
        lib._library["fetched_at"] = 0.0
        lib._last_attempt = 0.0
        fake.page_html = "<ul><li>restyled markup</li></ul>"
        with caplog.at_level("WARNING", logger=lib.logger.name):
            result = await lib.search()
        assert sum("parsed to zero models" in r.getMessage() for r in caplog.records) == 1
        assert not any("page fetch failed" in r.getMessage() for r in caplog.records)
        assert sorted(by_name(result)) == ["a:1b", "b:2b"]
        assert "gone:1b" in lib._sizes  # an empty parse prunes nothing


# ── Disk cache / TTLs ─────────────────────────────────────────────────────


class TestCache:
    async def test_persists_known_statuses_not_unknown(self, monkeypatch) -> None:
        fake = install(
            monkeypatch,
            Fake(page(("a", ["1b", "2b", "3b", "4b"], False)), tags=[]),
        )
        fake.scripts["a:2b"] = 404
        fake.scripts["a:3b"] = 500
        await lib.search()
        raw = json.loads(cache_file().read_text())
        assert set(raw["sizes"]) == {"a:1b", "a:2b", "a:4b"}
        assert raw["sizes"]["a:1b"]["status"] == "ok"
        assert raw["sizes"]["a:2b"]["status"] == "missing"
        assert [e["name"] for e in raw["library"]["entries"]] == ["a:1b", "a:2b", "a:3b", "a:4b"]
        assert not cache_file().with_suffix(".json.tmp").exists()

    async def test_warm_cache_after_restart_makes_no_requests(self, monkeypatch, tmp_path) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        await lib.search()
        lib._reset_for_tests(cache_path=tmp_path / "ollama-sizes.json")
        before = len(fake.log)
        result = await lib.search()
        assert len(fake.log) == before
        assert by_name(result)["a:1b"]["status"] == "ok"

    async def test_default_path_is_under_data_dir_resolved_lazily(
        self, monkeypatch, tmp_path
    ) -> None:
        from the_one.config import settings

        lib._reset_for_tests(cache_path=None)
        monkeypatch.setattr(settings, "data_dir", tmp_path / "later")
        assert lib._cache_path() == tmp_path / "later" / "ollama-sizes.json"

    async def test_ttls(self, monkeypatch, tmp_path) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False), ("b", ["1b"], False))))
        fake.scripts["b:1b"] = 404
        await lib.search()

        def reload(age_ok: float, age_missing: float) -> None:
            lib._reset_for_tests(cache_path=tmp_path / "ollama-sizes.json")
            raw = json.loads(cache_file().read_text())
            now = real_time.time()
            raw["sizes"]["a:1b"]["fetched_at"] = now - age_ok
            raw["sizes"]["b:1b"]["fetched_at"] = now - age_missing
            cache_file().write_text(json.dumps(raw))

        reload(6 * 86400, 0.5 * 86400)  # both within TTL
        fake.manifest_calls.clear()
        await lib.search()
        assert fake.registry_requests == 0

        reload(6 * 86400, 2 * 86400)  # missing expired (1 d), ok fresh (7 d)
        fake.manifest_calls.clear()
        await lib.search()
        assert list(fake.manifest_calls) == ["b:1b"]

        reload(8 * 86400, 0.5 * 86400)  # ok expired
        fake.manifest_calls.clear()
        await lib.search()
        assert list(fake.manifest_calls) == ["a:1b"]

    async def test_unknown_is_memory_only_for_300s(self, monkeypatch) -> None:
        clock = [1_000_000.0]
        monkeypatch.setattr(lib, "time", SimpleNamespace(time=lambda: clock[0]))
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        fake.scripts["a:1b"] = 503
        await lib.search()
        assert fake.manifest_calls["a:1b"] == 1
        clock[0] += 299
        await lib.search()
        assert fake.manifest_calls["a:1b"] == 1  # not re-hammered
        clock[0] += 2
        fake.scripts["a:1b"] = manifest_body([7])
        result = await lib.search()
        assert fake.manifest_calls["a:1b"] == 2
        assert by_name(result)["a:1b"]["status"] == "ok"

    def test_unknown_never_overwrites_known_within_ttl(self) -> None:
        lib._record("a:1b", "ok", 100)
        entry = lib._record("a:1b", "unknown", None)
        assert entry["status"] == "ok" and lib._sizes["a:1b"]["size"] == 100
        lib._sizes["a:1b"]["fetched_at"] -= 8 * 86400  # expired
        assert lib._record("a:1b", "unknown", None)["status"] == "unknown"

    def test_known_replaces_unknown_and_known(self) -> None:
        lib._record("a:1b", "unknown", None)
        assert lib._record("a:1b", "ok", 5)["size"] == 5
        assert lib._record("a:1b", "missing", None)["status"] == "missing"

    async def test_corrupt_file_degrades_to_empty(self, monkeypatch) -> None:
        cache_file().write_text("{ not json")
        install(monkeypatch, Fake(page(("a", ["1b"], False))))
        result = await lib.search()
        assert by_name(result)["a:1b"]["status"] == "ok"
        json.loads(cache_file().read_text())  # rewritten cleanly

    async def test_wrong_shape_file_degrades(self, monkeypatch) -> None:
        cache_file().write_text(json.dumps({"sizes": {"a:1b": "bad", "b:1b": {"status": "ok"}}}))
        install(monkeypatch, Fake(page(("a", ["1b"], False))))
        assert by_name(await lib.search())["a:1b"]["status"] == "ok"

    @pytest.mark.parametrize(
        "text",
        [
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": NaN}}}',
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": Infinity}}}',
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": -Infinity}}}',
            '{"library": {"fetched_at": NaN, "entries": [{"name": "a:1b"}]}}',
            '{"library": {"fetched_at": 1e999, "entries": [{"name": "a:1b"}]}}',
            '{"library": {"entries": [{"name": 5}, {"name": null}, {"name": "a:1b"}]}}',
            '{"library": {"entries": "not a list"}}',
            '{"library": {"entries": {"a": 1}}}',
            '{"library": ["not", "a", "dict"]}',
            '{"sizes": ["not", "a", "dict"]}',
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": 1}, "b:1b": null}}',
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": ' + "9" * 400 + "},"
            ' "b:1b": {"status": "ok", "size": 5, "fetched_at": 1}}}',
            '{"library": {"fetched_at": ' + "9" * 400 + ', "entries": [{"name": "a:1b"}]}}',
            "[" * 100000,
            '{"a": ' + "[" * 100000,
        ],
        ids=[
            "nan-size-fetched-at",
            "infinity-size-fetched-at",
            "neg-infinity-size-fetched-at",
            "nan-library-fetched-at",
            "overflow-float-library-fetched-at",
            "non-string-names",
            "entries-not-list",
            "entries-dict",
            "library-not-dict",
            "sizes-not-dict",
            "null-size-entry",
            "huge-int-size-fetched-at",
            "huge-int-library-fetched-at",
            "deeply-nested-array",
            "deeply-nested-in-object",
        ],
    )
    async def test_corrupt_cache_shapes_never_raise(self, monkeypatch, text) -> None:
        cache_file().write_text(text)
        install(monkeypatch, Fake(page(("a", ["1b"], False))))
        result = await lib.search()  # must return normally
        assert isinstance(result["models"], list)
        lib._loaded_from_disk = False  # a second, fresh load for the size route
        lib._sizes.clear()
        cache_file().write_text(text)
        got = await lib.size("a:1b")
        assert got["name"] == "a:1b"
        assert got["status"] == "ok"

    async def test_bad_timestamp_drops_only_that_entry(self, caplog) -> None:
        now = real_time.time()
        cache_file().write_text(
            '{"sizes": {"a:1b": {"status": "ok", "size": 5, "fetched_at": '
            + "9" * 400
            + '}, "b:1b": {"status": "ok", "size": 6, "fetched_at": '
            + repr(now)
            + '}, "c:1b": {"status": "ok", "size": 7, "fetched_at": NaN}}}'
        )
        with caplog.at_level("WARNING", logger=lib.logger.name):
            lib._load_disk()
        assert set(lib._sizes) == {"b:1b"}
        assert lib._sizes["b:1b"]["size"] == 6

    async def test_unparseable_file_logs_one_warning_and_stays_empty(self, caplog) -> None:
        cache_file().write_text("[" * 100000)
        with caplog.at_level("WARNING", logger=lib.logger.name):
            lib._load_disk()
        assert lib._sizes == {} and lib._library is None
        assert sum("unreadable" in r.getMessage() for r in caplog.records) == 1

    async def test_invalid_names_in_cache_file_are_dropped_not_raised(self, caplog) -> None:
        now = real_time.time()
        ok = {"size": 5, "status": "ok", "fetched_at": now}
        cache_file().write_text(
            json.dumps(
                {
                    "library": {
                        "fetched_at": now,
                        "entries": [
                            {"name": "a:1b", "cloud": False},
                            {"name": "Bad Name!:1b", "cloud": False},
                            {"name": "a:bad tag\n", "cloud": False},
                        ],
                    },
                    "sizes": {"a:1b": ok, "../evil:1b": ok, "b:tag with space": ok},
                }
            )
        )
        with caplog.at_level("WARNING", logger=lib.logger.name):
            result = await lib.search()  # fresh cache: no network, must not raise
        assert result["loading"] is False
        assert list(by_name(result)) == ["a:1b"]
        assert by_name(result)["a:1b"]["status"] == "ok"
        assert set(lib._sizes) == {"a:1b"}
        assert sum("dropped 4 invalid" in r.getMessage() for r in caplog.records) == 1

    async def test_replace_failure_never_raises(self, monkeypatch) -> None:
        install(monkeypatch, Fake(page(("a", ["1b"], False))))

        def boom(*a, **k):
            raise PermissionError("locked")

        monkeypatch.setattr(lib.os, "replace", boom)
        result = await lib.search()
        assert by_name(result)["a:1b"]["status"] == "ok"
        assert (await lib.size("a:1b"))["status"] == "ok"

    async def test_prune_only_after_successful_page_parse(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        await lib.search()
        lib._record("gone:1b", "ok", 5)
        # page fetch fails: listing stale, nothing pruned
        lib._library["fetched_at"] = 0.0
        lib._last_attempt = 0.0
        fake.page_html = None
        await lib.search()
        assert "gone:1b" in lib._sizes
        # page ok again: the vanished key is pruned
        lib._library["fetched_at"] = 0.0
        lib._last_attempt = 0.0
        fake.page_html = page(("a", ["1b"], False))
        await lib.search()
        assert "gone:1b" not in lib._sizes and "a:1b" in lib._sizes


# ── The fill ──────────────────────────────────────────────────────────────


class TestFill:
    async def test_budget_leaves_unsettled_entries_uncached(self, monkeypatch) -> None:
        monkeypatch.setattr(lib, "_BUDGET_S", 0.3)
        fake = install(monkeypatch, Fake(page(("a", ["1b", "2b", "3b"], False))))
        fake.delays["a:2b"] = 5
        result = await lib.search()
        assert "a:2b" not in lib._sizes
        assert "a:2b" not in json.loads(cache_file().read_text())["sizes"]
        assert by_name(result)["a:2b"]["status"] == "unknown"
        assert by_name(result)["a:1b"]["status"] == "ok"
        # the next fill retries it
        fake.delays.clear()
        lib._last_attempt = 0.0
        lib._library["fetched_at"] = 0.0
        assert by_name(await lib.search())["a:2b"]["status"] == "ok"
        assert fake.manifest_calls["a:2b"] == 2

    @pytest.mark.parametrize("failure", [httpx.ConnectError("x"), 403, 429])
    async def test_early_stop_after_first_wave(self, monkeypatch, failure) -> None:
        tags = [f"{i}b" for i in range(40)]
        fake = install(monkeypatch, Fake(page(("m", tags, False))))
        fake.default = failure
        for t in tags:
            fake.scripts[f"m:{t}"] = failure
        result = await lib.search()
        assert fake.registry_requests == 16
        statuses = Counter(m["status"] for m in result["models"])
        assert statuses == {"unknown": 40}
        # In cooldown: a second request does not hammer the registry again.
        await lib.search()
        assert fake.registry_requests == 16

    async def test_first_wave_with_one_success_continues(self, monkeypatch) -> None:
        tags = [f"{i}b" for i in range(20)]
        fake = install(monkeypatch, Fake(page(("m", tags, False))))
        for t in tags[:-1]:
            fake.scripts[f"m:{t}"] = 503  # unknown but not a hard failure
        result = await lib.search()
        assert fake.registry_requests == 20
        assert by_name(result)["m:19b"]["status"] == "ok"

    async def test_concurrent_callers_share_one_fill(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b", "2b"], False))))
        fake.delays["a:1b"] = 0.05
        results = await asyncio.gather(lib.search(), lib.search(), lib.search())
        assert fake.page_requests == 1
        assert fake.manifest_calls["a:1b"] == 1
        assert all(r["loading"] is False and len(r["models"]) == 2 for r in results)

    async def test_cancelled_waiter_does_not_cancel_the_fill(self, monkeypatch) -> None:
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        fake.gates["a:1b"] = gate = asyncio.Event()
        waiter = asyncio.create_task(lib.search())
        await asyncio.sleep(0.05)
        fill = lib._fill
        assert fill is not None and not fill.done()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not fill.cancelled() and not fill.done()
        gate.set()
        await fill
        assert lib._sizes["a:1b"]["status"] == "ok"

    async def test_bounded_wait_answers_loading_then_ready(self, monkeypatch) -> None:
        monkeypatch.setattr(lib, "_WAIT_S", 0.05)
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        fake.gates["a:1b"] = gate = asyncio.Event()
        first = await lib.search()
        assert first["loading"] is True
        gate.set()
        await lib._fill
        second = await lib.search()
        assert second["loading"] is False
        assert by_name(second)["a:1b"]["status"] == "ok"
        assert fake.page_requests == 1

    async def test_size_route_write_survives_a_later_unknown_from_the_fill(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(lib, "_WAIT_S", 0.05)
        fake = install(monkeypatch, Fake(page(("a", ["1b"], False))))
        # The fill's request (first) blocks then fails; the size route's (second) succeeds.
        fake.scripts["a:1b"] = [503, manifest_body([42])]
        fake.gates["a:1b"] = gate = asyncio.Event()
        assert (await lib.search())["loading"] is True
        out = await lib.size("a:1b")
        assert out["status"] == "ok" and out["size"] == 42 + 485
        gate.set()
        await lib._fill
        assert lib._sizes["a:1b"]["status"] == "ok"
        assert lib._sizes["a:1b"]["size"] == 42 + 485

    async def test_http_clients_are_per_fill_and_limited(self, monkeypatch) -> None:
        seen: list[dict] = []
        fake = Fake(page(("a", ["1b"], False)))
        real = httpx.AsyncClient

        def make(**kw):
            seen.append(kw)
            return real(transport=httpx.MockTransport(fake.handler), **kw)

        monkeypatch.setattr(lib, "_new_client", make)
        await lib.search()
        manifest_kw = seen[-1]
        assert manifest_kw["follow_redirects"] is False
        assert manifest_kw["limits"].max_connections == 16
        assert manifest_kw["timeout"] == 10.0


class TestShutdownDrain:
    async def test_no_fill_is_a_noop(self) -> None:
        await lib.shutdown_drain()
        assert not cache_file().exists()

    async def test_finished_fill_is_a_noop(self, monkeypatch) -> None:
        install(monkeypatch, Fake(page(("a", ["1b"], False))))
        await lib.search()
        mtime = cache_file().stat().st_mtime_ns
        await lib.shutdown_drain()
        assert cache_file().stat().st_mtime_ns == mtime

    async def test_cancels_running_fill_and_persists_what_settled(self, monkeypatch) -> None:
        monkeypatch.setattr(lib, "_WAIT_S", 0.05)
        fake = install(monkeypatch, Fake(page(("a", ["1b", "2b"], False))))
        fake.gates["a:2b"] = asyncio.Event()  # never released
        assert (await lib.search())["loading"] is True
        fill = lib._fill
        await lib.shutdown_drain()
        assert fill is not None and fill.done()
        raw = json.loads(cache_file().read_text())
        assert set(raw["sizes"]) == {"a:1b"}

    async def test_no_child_task_left_pending_after_drain(self, monkeypatch) -> None:
        monkeypatch.setattr(lib, "_WAIT_S", 0.05)
        fake = install(monkeypatch, Fake(page(("a", ["1b", "2b", "3b"], False))))
        for t in ("2b", "3b"):
            fake.gates[f"a:{t}"] = asyncio.Event()  # never released
        assert (await lib.search())["loading"] is True
        before = asyncio.all_tasks() - {asyncio.current_task()}
        fetchers = [t for t in before if "_fetch_one" in repr(t.get_coro())]
        assert len(fetchers) == 2  # the two gated manifests (a:1b already settled)
        await lib.shutdown_drain()
        assert all(t.done() for t in fetchers)
        leftover = [
            t for t in asyncio.all_tasks() - {asyncio.current_task()} if "_fetch_one" in repr(t)
        ]
        assert leftover == []

    def test_fill_on_another_loop_is_ignored(self) -> None:
        loop = asyncio.new_event_loop()

        async def forever():
            await asyncio.sleep(60)

        task = loop.create_task(forever())
        lib._fill = task
        try:
            asyncio.run(lib.shutdown_drain())  # a different loop: must neither cancel nor raise
            assert not task.cancelled() and not task.done()
        finally:
            lib._fill = None
            task.cancel()
            loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
            loop.close()

    def test_reset_tolerates_a_fill_on_a_closed_loop(self) -> None:
        loop = asyncio.new_event_loop()

        async def forever():
            await asyncio.sleep(60)

        task = loop.create_task(forever())
        loop.run_until_complete(asyncio.sleep(0))
        lib._fill = task
        loop.close()
        lib._reset_for_tests()
        assert lib._fill is None


# ── Seam ──────────────────────────────────────────────────────────────────

SEAM = json.dumps(
    {
        "models": [
            {"name": "qwen3:0.6b", "size": 523_000_000, "status": "ok"},
            {"name": "gemma3:1b", "size": 815_000_000, "status": "ok"},
            {"name": "gemma3:12b", "size": 8_100_000_000, "status": "ok"},
            {"name": "nomic-embed-text", "size": 274_000_000, "status": "ok"},
            {"name": "kimi-k3", "size": None, "status": "cloud"},
            {"name": "wizardlm", "size": None, "status": "missing"},
            {"name": "flaky:7b", "size": None, "status": "unknown"},
        ]
    }
)


class TestSeam:
    @pytest.fixture
    def dev(self, monkeypatch):
        from the_one.config import settings

        monkeypatch.setattr(settings, "dev_mode", True)
        monkeypatch.setenv("THE_ONE_OLLAMA_LIBRARY_TEST_JSON", SEAM)

        def no_network(**kw):
            raise AssertionError("seam must not touch the network")

        monkeypatch.setattr(lib, "_new_client", no_network)

    async def test_search_serves_the_catalog_sorted_without_files(self, dev) -> None:
        result = await lib.search()
        assert result["loading"] is False
        assert [m["name"] for m in result["models"]] == [
            "flaky:7b",
            "gemma3:1b",
            "gemma3:12b",
            "kimi-k3",
            "nomic-embed-text",
            "qwen3:0.6b",
            "wizardlm",
        ]
        assert by_name(result)["qwen3:0.6b"]["size"] == 523_000_000
        assert by_name(result)["kimi-k3"] == {"name": "kimi-k3", "size": None, "status": "cloud"}
        assert not cache_file().exists()

    async def test_q_applies_to_the_seam(self, dev) -> None:
        names = [m["name"] for m in (await lib.search("GEMMA"))["models"]]
        assert names == ["gemma3:1b", "gemma3:12b"]

    async def test_size_looks_up_with_bare_and_latest_equal(self, dev) -> None:
        assert await lib.size("nomic-embed-text") == {
            "name": "nomic-embed-text",
            "size": 274_000_000,
            "status": "ok",
        }
        assert (await lib.size("nomic-embed-text:latest"))["size"] == 274_000_000
        assert (await lib.size("kimi-k3"))["status"] == "cloud"
        assert (await lib.size("nope:1b")) == {"name": "nope:1b", "size": None, "status": "missing"}
        assert not cache_file().exists()

    async def test_size_validates_first(self, dev) -> None:
        with pytest.raises(ValueError):
            await lib.size("A/b")

    async def test_ignored_without_dev_mode(self, monkeypatch, caplog) -> None:
        from the_one.config import settings

        monkeypatch.setattr(settings, "dev_mode", False)
        monkeypatch.setenv("THE_ONE_OLLAMA_LIBRARY_TEST_JSON", SEAM)
        fake = install(monkeypatch, Fake(page(("real", ["1b"], False))))
        with caplog.at_level("WARNING"):
            result = await lib.search()
        assert [m["name"] for m in result["models"]] == ["real:1b"]
        assert fake.page_requests == 1
        assert "test seam is ignored" in caplog.text
