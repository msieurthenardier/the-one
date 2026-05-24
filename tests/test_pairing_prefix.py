"""Unit tests for ``the_one.connectors._pairing._validate_pairing_prefix``.

M10 F7 L8: closes F6 debrief carry-forward — the pairing helper is
integration-tested only via the dispatcher path
(``tests/test_connectors_inbound.py`` NeedsPairing-path tests). This
module pins the helper's byte-equality + case-sensitivity claims at
the unit level so a future refactor that drifts the prefix-parsing
semantic is caught here instead of cascading into dispatcher failures.

M10 F8 L1: extends with four cross-platform whitespace edge cases
(ZWJ inside the code arg, NBSP between the ``PAIR`` keyword and the
code, smart-quote bytes inside the code, multi-line text remainder)
ahead of F8 L4's first real ingestion against real-platform clients
that may emit any of these shapes. Each case asserts the helper's
byte-equality contract — no normalization, no special-casing of
control characters, no smart-quote folding.

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

    # ─── M10 F8 L1 — cross-platform whitespace edge cases ────────────

    def test_zwj_in_code_arg_without_zwj_in_text_fails(self) -> None:
        # Zero-width joiner (U+200D) in the caller-provided ``code``
        # argument is not present in the inbound ``text``. Byte-equality
        # means a ZWJ-containing code only matches a ZWJ-containing
        # prefix in text — silent normalization would mask the
        # mismatch. Pinning against any future Unicode-folding refactor.
        assert _validate_pairing_prefix("PAIR ab hello", "a‍b") == (
            False,
            "PAIR ab hello",
        )

    def test_nbsp_between_pair_keyword_and_code_fails(self) -> None:
        # Non-breaking space (U+00A0) between ``PAIR`` and the code in
        # the inbound text. The helper does ``text.startswith("PAIR ")``
        # with an ASCII space (U+0020); NBSP is not equal, so the prefix
        # check fails. Mobile clients occasionally substitute NBSP via
        # autocorrect; pinning the mismatch.
        nbsp_text = "PAIR abc hello"
        assert _validate_pairing_prefix(nbsp_text, "abc") == (
            False,
            nbsp_text,
        )

    def test_smart_quotes_inside_code_require_byte_equal_caller_code(self) -> None:
        # Smart quotes (U+201C/U+201D) inside the code in the inbound
        # text. Byte-equality: a caller-provided ``code`` argument
        # containing the same smart-quote bytes MATCHES; a caller-
        # provided ``code`` with ASCII quotes does NOT match. Pinning
        # both directions of the contract.
        smart_text = "PAIR “abc” hello"
        # ASCII-quote code does not match the smart-quoted text.
        assert _validate_pairing_prefix(smart_text, '"abc"') == (
            False,
            smart_text,
        )
        # Byte-equal smart-quote code DOES match.
        assert _validate_pairing_prefix(smart_text, "“abc”") == (
            True,
            "hello",
        )

    def test_multi_line_text_remainder_preserves_newlines(self) -> None:
        # Multi-line text where the prefix occupies line 1 and the
        # message body spans subsequent lines. The helper does NOT
        # special-case newlines — ``text.startswith(f"PAIR {code} ")``
        # is satisfied as long as the prefix matches; the remainder is
        # returned verbatim, newlines included.
        multi_line = "PAIR abc hello\nworld\nthird line"
        assert _validate_pairing_prefix(multi_line, "abc") == (
            True,
            "hello\nworld\nthird line",
        )
