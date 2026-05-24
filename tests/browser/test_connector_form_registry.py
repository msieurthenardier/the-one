"""Browser tests for ``App.studio.connectorFormRegistry`` (M11 F1 L3).

Covers the registry's own contract via ``page.evaluate``:
  - ``register(type, entry)`` validates entry shape (type-must-equal-key
    plus three required functions plus ``reservedConfigKeys`` array).
  - Double-register on the same type emits ``console.warn`` containing
    "re-registering type"; last-writer-wins for ``get``.
  - Missing required function raises ``TypeError`` whose message names
    the missing field.
  - Mismatched ``entry.type`` vs registered key raises ``TypeError``.
  - ``get(unregistered)`` returns ``undefined`` (never throws).

The substrate ships without any registered entries — the existing
``'stub'``-path Playwright tests cover the fallback render contract;
this file pins the registry's standalone shape so L4 (and the second
connector) can rely on the contract.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
class TestConnectorFormRegistry:
    def test_register_and_get_round_trip(self, app_clean: str, page: Page) -> None:
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(
            """
            () => {
                const entry = {
                    type: 'test-type',
                    renderConnectionFields: function () { return '<div></div>'; },
                    renderCredentialsFields: function () { return '<div></div>'; },
                    collect: function () { return { config: {}, secrets: {} }; },
                    reservedConfigKeys: ['foo']
                };
                window.App.studio.connectorFormRegistry.register('test-type', entry);
                const got = window.App.studio.connectorFormRegistry.get('test-type');
                return {
                    sameRef: got === entry,
                    type: got && got.type,
                    reserved: got && got.reservedConfigKeys
                };
            }
            """
        )
        assert result["sameRef"] is True
        assert result["type"] == "test-type"
        assert result["reserved"] == ["foo"]

    def test_get_unregistered_returns_undefined(self, app_clean: str, page: Page) -> None:
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(
            "() => window.App.studio.connectorFormRegistry.get('unregistered-type') === undefined"
        )
        assert result is True

    def test_double_register_warns_and_last_writer_wins(
        self, app_clean: str, page: Page
    ) -> None:
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        warns: list[str] = []
        page.on(
            "console",
            lambda msg: warns.append(msg.text) if msg.type == "warning" else None,
        )

        result = page.evaluate(
            """
            () => {
                const make = function (tag) {
                    return {
                        type: 'dup-type',
                        renderConnectionFields: function () { return '<div>' + tag + '</div>'; },
                        renderCredentialsFields: function () { return '<div></div>'; },
                        collect: function () { return { config: {tag: tag}, secrets: {} }; },
                        reservedConfigKeys: []
                    };
                };
                window.App.studio.connectorFormRegistry.register('dup-type', make('first'));
                window.App.studio.connectorFormRegistry.register('dup-type', make('second'));
                const got = window.App.studio.connectorFormRegistry.get('dup-type');
                return got.collect().config.tag;
            }
            """
        )
        assert result == "second"
        assert any("re-registering type" in w and "dup-type" in w for w in warns), (
            f"Expected console.warn about re-registering type 'dup-type'; got: {warns!r}"
        )

    def test_missing_required_fn_raises_type_error_naming_field(
        self, app_clean: str, page: Page
    ) -> None:
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(
            """
            () => {
                try {
                    window.App.studio.connectorFormRegistry.register('bad-type', {
                        type: 'bad-type',
                        // renderConnectionFields intentionally missing
                        renderCredentialsFields: function () { return ''; },
                        collect: function () { return { config: {}, secrets: {} }; },
                        reservedConfigKeys: []
                    });
                    return { threw: false };
                } catch (e) {
                    return {
                        threw: true,
                        isTypeError: e instanceof TypeError,
                        message: e.message
                    };
                }
            }
            """
        )
        assert result["threw"] is True
        assert result["isTypeError"] is True
        assert "renderConnectionFields" in result["message"], (
            f"Expected message to name renderConnectionFields; got: {result['message']!r}"
        )

    def test_registry_optionalFns_includes_renderDiscoverableDropdown(
        self, app_clean: str, page: Page
    ) -> None:
        """M11 F3 L5: the optionalFns array gains a 5th hook
        ``renderDiscoverableDropdown`` validated as "must be a function
        IF present". Probes the validator by registering two stub
        entries — one with a function body (registration succeeds), one
        with a string body (validator throws TypeError naming the hook).
        Also asserts the Discord entry exposes the bridge method.
        """
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(
            """
            () => {
                // Accept-path: function body → registration succeeds.
                const acceptEntry = {
                    type: 'dd-accept',
                    renderConnectionFields: function () { return ''; },
                    renderCredentialsFields: function () { return ''; },
                    collect: function () { return { config: {}, secrets: {} }; },
                    reservedConfigKeys: [],
                    renderDiscoverableDropdown: function () { return null; }
                };
                let acceptThrew = false;
                try {
                    window.App.studio.connectorFormRegistry.register('dd-accept', acceptEntry);
                } catch (e) { acceptThrew = true; }

                const acceptGot = window.App.studio.connectorFormRegistry.get('dd-accept');
                const acceptHookType = typeof (acceptGot && acceptGot.renderDiscoverableDropdown);

                // Reject-path: non-function body → registration throws.
                let rejectThrew = false;
                let rejectMessage = '';
                try {
                    window.App.studio.connectorFormRegistry.register('dd-reject', {
                        type: 'dd-reject',
                        renderConnectionFields: function () { return ''; },
                        renderCredentialsFields: function () { return ''; },
                        collect: function () { return { config: {}, secrets: {} }; },
                        reservedConfigKeys: [],
                        renderDiscoverableDropdown: 'not-a-function'
                    });
                } catch (e) {
                    rejectThrew = true;
                    rejectMessage = e.message;
                }

                // Discord entry exposes the bridge method.
                const discordEntry = window.App.studio.connectorFormRegistry.get('discord');
                const discordHookType = typeof (discordEntry && discordEntry.renderDiscoverableDropdown);

                return {
                    acceptThrew: acceptThrew,
                    acceptHookType: acceptHookType,
                    rejectThrew: rejectThrew,
                    rejectMessage: rejectMessage,
                    discordHookType: discordHookType
                };
            }
            """
        )
        assert result["acceptThrew"] is False, (
            "Expected a stub entry with renderDiscoverableDropdown=function "
            "to register cleanly; got threw=True"
        )
        assert result["acceptHookType"] == "function"
        assert result["rejectThrew"] is True, (
            "Expected a stub entry with renderDiscoverableDropdown='not-a-function' "
            "to throw at register time"
        )
        assert "renderDiscoverableDropdown" in result["rejectMessage"], (
            f"Expected error message to name the offending hook; got: "
            f"{result['rejectMessage']!r}"
        )
        assert result["discordHookType"] == "function", (
            f"Expected the Discord entry to expose renderDiscoverableDropdown as a "
            f"function; got: {result['discordHookType']!r}"
        )

    def test_type_mismatch_raises_type_error(self, app_clean: str, page: Page) -> None:
        page.goto(app_clean)
        page.wait_for_load_state("domcontentloaded")

        result = page.evaluate(
            """
            () => {
                try {
                    window.App.studio.connectorFormRegistry.register('mismatch-type', {
                        type: 'other',
                        renderConnectionFields: function () { return ''; },
                        renderCredentialsFields: function () { return ''; },
                        collect: function () { return { config: {}, secrets: {} }; },
                        reservedConfigKeys: []
                    });
                    return { threw: false };
                } catch (e) {
                    return {
                        threw: true,
                        isTypeError: e instanceof TypeError,
                        message: e.message
                    };
                }
            }
            """
        )
        assert result["threw"] is True
        assert result["isTypeError"] is True
        assert "mismatch-type" in result["message"] or "entry.type" in result["message"], (
            f"Expected message to flag the type mismatch; got: {result['message']!r}"
        )
