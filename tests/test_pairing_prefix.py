"""Unit tests for ``the_one.connectors._pairing._validate_pairing_prefix``.

M10 F7 L8: closes F6 debrief carry-forward — the pairing helper is
integration-tested only via the dispatcher path
(``tests/test_connectors_inbound.py`` NeedsPairing-path tests). This
module pins the helper's byte-equality + case-sensitivity claims at
the unit level so a future refactor that drifts the prefix-parsing
semantic is caught here instead of cascading into dispatcher failures.

The helper's docstring at ``the_one/connectors/_pairing.py:18-31``
documents the contract this module verifies.
"""

from __future__ import annotations

from the_one.connectors._pairing import _validate_pairing_prefix


class TestValidatePairingPrefix:
    def test_validates_correct_prefix_and_strips(self) -> None:
        assert _validate_pairing_prefix("PAIR abc hello", "abc") == (True, "hello")

    def test_wrong_code_returns_false_and_unchanged_text(self) -> None:
        assert _validate_pairing_prefix("PAIR wrong hello", "abc") == (
            False,
            "PAIR wrong hello",
        )

    def test_empty_code_never_matches(self) -> None:
        assert _validate_pairing_prefix("PAIR abc hello", "") == (
            False,
            "PAIR abc hello",
        )

    def test_missing_prefix_returns_false(self) -> None:
        assert _validate_pairing_prefix("abc hello", "abc") == (False, "abc hello")

    def test_case_sensitive_pair_keyword(self) -> None:
        # PAIR is case-sensitive; lowercase fails.
        assert _validate_pairing_prefix("pair abc hello", "abc") == (
            False,
            "pair abc hello",
        )

    def test_case_sensitive_code_comparison(self) -> None:
        # Byte-equality on code.
        assert _validate_pairing_prefix("PAIR ABC hello", "abc") == (
            False,
            "PAIR ABC hello",
        )

    def test_leading_whitespace_fails(self) -> None:
        # Commands at column 0.
        assert _validate_pairing_prefix(" PAIR abc hello", "abc") == (
            False,
            " PAIR abc hello",
        )

    def test_code_with_internal_whitespace_matches_byte_equality(self) -> None:
        # The helper itself is byte-equality only: it strips ``PAIR `` then
        # checks ``remainder.startswith(code + " ")``. If the caller hands
        # in a ``code`` containing internal whitespace, the helper will
        # happily match — the docstring's "whitespace inside the code is
        # not permitted" is enforced upstream by the parser/storage layer,
        # NOT by this helper. Pinning this against silent drift: if a
        # future refactor adds internal-whitespace rejection here, this
        # test surfaces the change so the contract can be re-evaluated.
        assert _validate_pairing_prefix("PAIR ab cd hello", "ab cd") == (
            True,
            "hello",
        )
