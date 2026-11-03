"""strip_vt_sequences: ConPTY output is returned as text (squawk 0165).

Pure function in the platform-neutral ``the_one.platform.pty``; no pywinpty.
"""

from __future__ import annotations

from the_one.platform.pty import strip_vt_sequences

ESC = b"\x1b"
BEL = b"\x07"


def test_plain_text_unchanged():
    data = b"hello world\r\nline two\r\n"
    assert strip_vt_sequences(data) == data


def test_conpty_startup_repaint():
    raw = (
        ESC
        + b"[?25l"
        + ESC
        + b"[2J"
        + ESC
        + b"[m"
        + ESC
        + b"[H"
        + ESC
        + b"]0;C:\\WINDOWS\\system32\\cmd.exe"
        + BEL
        + ESC
        + b"[?25h"
        + b"Microsoft Windows [Version 10.0.20348]\r\n"
        + b"C:\\Users\\x>"
    )
    assert strip_vt_sequences(raw) == (b"Microsoft Windows [Version 10.0.20348]\r\nC:\\Users\\x>")


def test_command_output_with_cursor_positioning():
    raw = b"C:\\>echo hi" + ESC + b"[4;16H" + b"\r\n" + b"hi" + ESC + b"[K" + b"\r\n" + b"C:\\>"
    assert strip_vt_sequences(raw) == b"C:\\>echo hi\r\nhi\r\nC:\\>"


def test_osc_terminated_by_st():
    assert strip_vt_sequences(ESC + b"]0;title" + ESC + b"\\text") == b"text"


def test_other_esc_sequences_and_bel():
    assert strip_vt_sequences(ESC + b"=" + ESC + b"(B" + b"a" + BEL + b"b") == b"ab"


def test_backspace_erases_previous_char_but_not_across_lines():
    assert strip_vt_sequences(b"abc\x08\x08x") == b"ax"
    assert strip_vt_sequences(b"a\r\n\x08b") == b"a\r\nb"


def test_non_ascii_bytes_survive():
    text = "caf\u00e9 \u2713".encode()
    assert strip_vt_sequences(ESC + b"[1m" + text + ESC + b"[0m") == text


def test_truncated_trailing_sequence_is_dropped():
    assert strip_vt_sequences(b"ok" + ESC + b"[4;1") == b"ok"
