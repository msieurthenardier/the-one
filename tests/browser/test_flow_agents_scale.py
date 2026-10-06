# ruff: noqa: E501  (inline JS snippets are evaluated verbatim; wrapping them hurts readability)
"""Agents at scale and at the 1024px minimum (M25 F3 L3, DD1 and DD4; SC4).

* Filter keystroke cost, as a RATIO (DD4): the script time of the filter's input
  handler (a ``performance.now()`` delta around a dispatched ``input`` event) at
  60 agents versus 10, in Chromium with ``Emulation.setCPUThrottlingRate(4)``.
  Gate: the 60-agent median is at most 3x the 10-agent median and at most 50ms.
  WebKit has no CPU throttling: its unthrottled figures are reported, not gated.
* ``GET /api/agents`` at 60 agents (one ``store.load`` per agent): the server
  time is reported; a forced refresh over 300ms is a squawk, not a fix here.
* 35 agents render intact at 1440x900: the list body scrolls, rows are 48px
  (+-1) and never overlap, and the title row and filter stay fixed.
* The tab strip at 1024x768, both engines: five tabs, no overflow
  (``scrollWidth <= clientWidth``), the last tab inside the detail pane; the aside
  is 300px and the detail pane at least 650px.

Figures are printed (``-s``/``-rA``) and recorded with ``record_property`` so the
flight log can quote them. Falls in the ``agents`` lane.
"""

from __future__ import annotations

import os
import statistics
import time

import httpx
import pytest
from browser import _lists, _nav, _ui_engines
from browser._credential_registry import auth_headers_for
from browser.conftest import credentialed_context
from browser.seeders import SeededApp, seed_mock_agents
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.browser

# A keystroke sequence: type the query a character at a time, then clear it
# back down, so both narrowing and widening are measured.
_QUERY = "agent 4"
_ROUNDS = 12

# Each round times REPEAT passes of the sequence (one performance.now() pair
# around all of their dispatched input events) and divides by the keystrokes:
# performance.now() is coarsened (Chromium 100us; WebKit 1ms), coarser than one
# keystroke, so a per-dispatch delta would mostly read 0. The figure is the
# median over rounds of the mean script time per keystroke.
_REPEAT = 10
_MEASURE_JS = """
([query, rounds, repeat]) => {
  const input = document.querySelector('[data-testid="agents-filter"]');
  const seq = [];
  for (let i = 1; i <= query.length; i++) seq.push(query.slice(0, i));
  for (let i = query.length - 1; i >= 0; i--) seq.push(query.slice(0, i));
  const perKey = [];
  for (let r = 0; r < rounds; r++) {
    const t0 = performance.now();
    for (let k = 0; k < repeat; k++) {
      for (const v of seq) {
        input.value = v;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
    perKey.push((performance.now() - t0) / (seq.length * repeat));
  }
  return perKey;
}
"""


def _median_keystroke_ms(page: Page) -> float:
    # One warm-up pass (JIT, style sharing) before the measured rounds.
    page.evaluate(_MEASURE_JS, [_QUERY, 2, _REPEAT])
    times = page.evaluate(_MEASURE_JS, [_QUERY, _ROUNDS, _REPEAT])
    return statistics.median(times)


def _load_agents(page: Page, base: str, n: int) -> None:
    """Load ``#agents`` fresh (a reload when already there: a same-URL goto is
    a fragment navigation that would keep the stale list)."""
    if page.url.startswith(base) and _nav.current_route(page) == "agents":
        page.reload()
        _nav.wait_settled(page)
    else:
        _nav.goto_settled(page, base, "agents")
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(n, timeout=10000)


def test_filter_keystroke_cost_ratio_60_vs_10_throttled(
    app_with_provider: SeededApp, page: Page, record_property
) -> None:
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    page.set_viewport_size({"width": 1440, "height": 900})
    cdp = page.context.new_cdp_session(page)

    seed_mock_agents(base, pid, 10, prefix="agent")
    _load_agents(page, base, 10)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    m10 = _median_keystroke_ms(page)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})

    seed_mock_agents(base, pid, 50, prefix="more")  # 60 in all
    _load_agents(page, base, 60)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    m60 = _median_keystroke_ms(page)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})

    ratio = m60 / m10 if m10 > 0 else float("inf")
    record_property("filter_median_ms_10", round(m10, 3))
    record_property("filter_median_ms_60", round(m60, 3))
    record_property("filter_ratio", round(ratio, 2))
    print(f"[agents-scale] chromium x4: median 10={m10:.3f}ms 60={m60:.3f}ms ratio={ratio:.2f}")
    assert m60 <= 50, f"60-agent median {m60:.3f}ms exceeds 50ms"
    assert m60 <= 3 * m10, f"60-agent median {m60:.3f}ms > 3x the 10-agent {m10:.3f}ms"


def test_filter_keystroke_cost_webkit_reported(
    playwright_instance, app_with_provider: SeededApp, record_property
) -> None:
    """Reported, not gated: WebKit has no CPU throttling, so the unthrottled
    medians at 10 and 60 agents are recorded for the flight log. WebKit is
    launched under the shared skip/require policy (``_ui_engines``)."""
    launch_error = None
    browser = None
    try:
        browser = _ui_engines._launch(playwright_instance, "webkit")
        _ui_engines._smoke(browser)
    except Exception as exc:  # noqa: BLE001 - any launch failure goes to the policy
        launch_error = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else repr(exc)
    result = _ui_engines.webkit_policy(os.environ, launch_error)
    if result.kind == "skip":
        pytest.skip(result.reason)
    if result.kind == "fail":
        pytest.fail(result.reason)
    assert browser is not None
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    context = credentialed_context(browser, base, viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        seed_mock_agents(base, pid, 10, prefix="agent")
        _load_agents(page, base, 10)
        m10 = _median_keystroke_ms(page)
        seed_mock_agents(base, pid, 50, prefix="more")
        _load_agents(page, base, 60)
        m60 = _median_keystroke_ms(page)
    finally:
        context.close()
        browser.close()
    record_property("webkit_filter_median_ms_10", round(m10, 3))
    record_property("webkit_filter_median_ms_60", round(m60, 3))
    print(f"[agents-scale] webkit: median 10={m10:.3f}ms 60={m60:.3f}ms")


def test_get_agents_server_time_at_60(
    app_with_provider: SeededApp, page: Page, record_property
) -> None:
    """``GET /api/agents`` costs one ``store.load`` per agent (api.py). Report the
    server time at 60 agents: direct (httpx, loopback) and as the app's own
    forced store refresh (Resource Timing request->response)."""
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    seed_mock_agents(base, pid, 60, prefix="agent")
    direct = []
    with httpx.Client(base_url=base, headers=auth_headers_for(base), timeout=10.0) as c:
        c.get("/api/agents")  # warm
        for _ in range(7):
            t0 = time.perf_counter()
            r = c.get("/api/agents")
            direct.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200 and len(r.json()) == 60
    _load_agents(page, base, 60)
    forced = page.evaluate(
        """async () => {
          const out = [];
          for (let i = 0; i < 5; i++) {
            performance.clearResourceTimings();
            await App.store.get('agents', { force: true });
            const e = performance.getEntriesByType('resource')
              .filter((x) => x.name.split('?')[0].endsWith('/api/agents')).pop();
            out.push(e.responseStart - e.requestStart);
          }
          return out;
        }"""
    )
    d, f = statistics.median(direct), statistics.median(forced)
    record_property("get_agents_60_direct_median_ms", round(d, 1))
    record_property("get_agents_60_forced_refresh_median_ms", round(f, 1))
    print(f"[agents-scale] GET /api/agents @60: direct median={d:.1f}ms forced={f:.1f}ms")


def test_35_agents_render_intact_at_1440(app_with_provider: SeededApp, page: Page) -> None:
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    seed_mock_agents(base, pid, 35, prefix="agent")
    page.set_viewport_size({"width": 1440, "height": 900})
    _load_agents(page, base, 35)
    geo_js = """() => {
      const list = document.querySelector('[data-testid="agents-list"]');
      const body = list.querySelector('.ui-list-pane-body');
      const rows = Array.from(body.querySelectorAll('.ui-list-pane-row')).map((r) => {
        const b = r.getBoundingClientRect(); return [b.top, b.bottom, b.height]; });
      const rect = (el) => { const b = el.getBoundingClientRect(); return [b.top, b.bottom]; };
      return {rows, scrollH: body.scrollHeight, clientH: body.clientHeight,
              header: rect(list.querySelector('.ui-list-pane-header')),
              filter: rect(list.querySelector('.ui-list-pane-filter')),
              bodyRect: rect(body), aside: document.getElementById('app-sidebar').scrollTop,
              panel: document.querySelector('#app-sidebar .sidebar-panel.active').scrollTop,
              docH: document.documentElement.scrollHeight, vh: innerHeight};
    }"""
    before = page.evaluate(geo_js)
    assert len(before["rows"]) == 35
    assert before["scrollH"] > before["clientH"], before  # the list scrolls
    for top, bottom, height in before["rows"]:
        assert abs(height - 48) <= 1, (top, bottom, height)
    for (_, prev_bottom, _), (top, _, _) in zip(before["rows"], before["rows"][1:], strict=False):
        assert top >= prev_bottom - 0.5, before["rows"]  # no overlap
    # The list is bounded by the viewport and nothing stretches the document
    # (the rows' visually-hidden suffixes stay inside their rows).
    assert before["bodyRect"][1] <= before["vh"] + 0.5 and before["docH"] <= before["vh"], before

    page.evaluate(
        "document.querySelector('[data-testid=\"agents-list\"] .ui-list-pane-body').scrollTop = 99999"
    )
    after = page.evaluate(geo_js)
    assert after["header"] == before["header"] and after["filter"] == before["filter"], after
    assert after["aside"] == 0 and after["panel"] == 0, after  # only the body scrolled
    last_top, last_bottom, _ = after["rows"][-1]
    assert last_bottom <= after["bodyRect"][1] + 0.5, after  # the last row is reachable


def test_tab_strip_and_columns_fit_at_1024(
    engine_browser, app_with_provider: SeededApp, record_property
) -> None:
    base, pid = app_with_provider.base_url, app_with_provider.provider_id
    names = seed_mock_agents(base, pid, 3, prefix="agent")
    context = credentialed_context(engine_browser, base, viewport={"width": 1024, "height": 768})
    page = context.new_page()
    try:
        _nav.goto_settled(page, base, "agents")
        _lists.open_item(page, "agents", names[0])
        expect(page.locator(".studio-editor .editor-title")).to_have_text(names[0], timeout=8000)
        out = page.evaluate(
            """() => {
              const tl = document.querySelector('.studio-editor .tablist');
              const tabs = tl.querySelectorAll('[role="tab"]');
              const main = document.getElementById('main-content').getBoundingClientRect();
              const aside = document.getElementById('app-sidebar').getBoundingClientRect();
              const last = tabs[tabs.length - 1].getBoundingClientRect();
              return {tabs: tabs.length, scrollW: tl.scrollWidth, clientW: tl.clientWidth,
                      lastRight: last.right, mainRight: main.right, mainW: main.width,
                      asideW: aside.width, tabTops: Array.from(tabs).map((t) => t.getBoundingClientRect().top)};
            }"""
        )
    finally:
        context.close()
    engine = engine_browser.browser_type.name
    record_property(f"{engine}_tablist", f"{out['scrollW']}/{out['clientW']}")
    print(
        f"[agents-width] {engine} @1024: tablist scroll/client={out['scrollW']}/{out['clientW']} "
        f"lastRight={out['lastRight']:.1f} mainRight={out['mainRight']:.1f} "
        f"aside={out['asideW']} main={out['mainW']}"
    )
    assert out["tabs"] == 5, out
    assert out["scrollW"] <= out["clientW"], out
    assert out["lastRight"] <= out["mainRight"], out
    assert len(set(round(t) for t in out["tabTops"])) == 1, out  # one row: no wrap
    assert out["asideW"] == 300, out
    assert out["mainW"] >= 650, out
