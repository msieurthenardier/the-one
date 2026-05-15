from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_lerp_counter_animates_value_change(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const node = document.createElement('div');
          node.textContent = '0';
          document.body.appendChild(node);
          const observed = [];
          const obs = new MutationObserver(() => observed.push(node.textContent));
          obs.observe(node, { characterData: true, childList: true, subtree: true });
          window.LerpCounter.animate(node, 100, 240);
          await new Promise(r => setTimeout(r, 280));
          obs.disconnect();
          return { final: node.textContent, intermediates: observed.length };
        }"""
    )
    assert result["final"] == "100"
    assert result["intermediates"] > 1


@pytest.mark.browser
def test_lerp_counter_respects_reduced_motion(app_clean: str, page: Page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const node = document.createElement('div');
          node.textContent = '0';
          document.body.appendChild(node);
          window.LerpCounter.animate(node, 100, 240);
          await new Promise(r => setTimeout(r, 20));
          return node.textContent;
        }"""
    )
    assert result == "100"
