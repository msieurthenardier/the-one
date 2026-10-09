"""Tests for the_one.api_credential — Mission 20 / Flight 1 / Leg 1
(`credential-foundation`).

Every test isolates `settings.data_dir` to a per-test `tmp_path` and resets
the module's process-local caches (`_cache`, `_sources`) via the
`_isolated_credential_module` autouse fixture below, mirroring the
`isolated_db` pattern in tests/conftest.py (`monkeypatch.setattr(settings,
"data_dir", tmp_path)`).
"""

from __future__ import annotations

import hmac
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from the_one import api_credential
from the_one.api_credential import (
    CredentialFileError,
    FileCredentialSource,
    IdentifiedCaller,
    LocalApiCredential,
    credential_path,
    get_credential,
    lookup_credential,
    register_source,
    resolve_caller,
    rotate_credential,
)
from the_one.config import settings


@pytest.fixture(autouse=True)
def _isolated_credential_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point settings.data_dir at a fresh tmp_path and reset this module's
    process-local caches so tests never see state from a previous test."""
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(api_credential, "_cache", {})
    monkeypatch.setattr(api_credential, "_sources", [FileCredentialSource()])
    yield


# ---------------------------------------------------------------------------
# Credential shape (DD1)
# ---------------------------------------------------------------------------


class TestCredentialShape:
    def test_generate_parses_back_into_identifier_and_secret(self) -> None:
        cred = LocalApiCredential.generate()
        token = cred.encode()
        parsed = LocalApiCredential.parse(token)
        assert parsed is not None
        assert parsed.identifier == cred.identifier
        assert parsed.secret == cred.secret

    def test_token_carries_type_distinguishing_prefix(self) -> None:
        cred = LocalApiCredential.generate()
        token = cred.encode()
        assert token.startswith(f"{api_credential.CREDENTIAL_PREFIX}_")

    def test_parse_rejects_wrong_prefix(self) -> None:
        assert LocalApiCredential.parse("other_abc.def") is None

    def test_parse_rejects_missing_separator(self) -> None:
        assert LocalApiCredential.parse(f"{api_credential.CREDENTIAL_PREFIX}_noseparator") is None

    def test_parse_rejects_empty_identifier_or_secret(self) -> None:
        prefix = api_credential.CREDENTIAL_PREFIX
        assert LocalApiCredential.parse(f"{prefix}_.secret") is None
        assert LocalApiCredential.parse(f"{prefix}_identifier.") is None

    def test_generate_uses_secrets_module_not_random(self) -> None:
        # Two generations must never collide in practice — a weak `random`
        # source would still pass this probabilistically, so this is a
        # smoke check, not the load-bearing assertion; the load-bearing
        # check is the `secrets.token_hex` call, verified by patching it.
        with mock.patch.object(api_credential.secrets, "token_hex") as spy:
            spy.return_value = "aa"
            LocalApiCredential.generate()
        assert spy.called

    def test_repr_reveals_identifier_but_never_secret(self) -> None:
        cred = LocalApiCredential(identifier="visible-id", secret="super-secret-value")
        r = repr(cred)
        assert "visible-id" in r
        assert "super-secret-value" not in r

    def test_str_reveals_identifier_but_never_secret(self) -> None:
        cred = LocalApiCredential(identifier="visible-id", secret="super-secret-value")
        s = str(cred)
        assert "visible-id" in s
        assert "super-secret-value" not in s

    # M21 F01 L02 (LD2): `parse`/`encode` gained a `prefix` keyword so the
    # self-configuration surface can mint `agt`-prefixed credentials
    # through the same shape without a parallel class.

    def test_encode_with_custom_prefix_round_trips_with_matching_parse(self) -> None:
        cred = LocalApiCredential.generate()
        token = cred.encode(prefix="agt")
        assert token.startswith("agt_")
        parsed = LocalApiCredential.parse(token, prefix="agt")
        assert parsed is not None
        assert parsed.identifier == cred.identifier
        assert parsed.secret == cred.secret

    def test_default_prefix_parse_rejects_custom_prefix_token(self) -> None:
        """A `FileCredentialSource` (which always parses with the default
        prefix) must reject an `agt_`-prefixed token on prefix mismatch and
        fall through — never accidentally accept it as a `loc` credential."""
        cred = LocalApiCredential.generate()
        token = cred.encode(prefix="agt")
        assert LocalApiCredential.parse(token) is None

    def test_custom_prefix_parse_rejects_default_prefix_token(self) -> None:
        cred = LocalApiCredential.generate()
        token = cred.encode()
        assert LocalApiCredential.parse(token, prefix="agt") is None

    def test_encode_default_prefix_unchanged(self) -> None:
        cred = LocalApiCredential.generate()
        assert cred.encode() == cred.encode(prefix=api_credential.CREDENTIAL_PREFIX)


# ---------------------------------------------------------------------------
# Identified caller / lookup seam (DD8)
# ---------------------------------------------------------------------------


class TestIdentifiedCallerAndLookup:
    def test_successful_lookup_yields_identified_caller(self) -> None:
        stored = get_credential()
        result = resolve_caller(stored.encode())
        assert isinstance(result, IdentifiedCaller)
        assert not isinstance(result, bool)
        assert result.identifier == stored.identifier
        assert result.source == "file"

    def test_failed_lookup_yields_none_not_false(self) -> None:
        get_credential()  # ensure a real credential exists
        result = resolve_caller("loc_wrong.wrong")
        assert result is None
        assert result is not False

    def test_malformed_presented_token_yields_none(self) -> None:
        get_credential()
        assert resolve_caller("not-even-the-right-shape") is None

    def test_right_identifier_wrong_secret_yields_none(self) -> None:
        stored = get_credential()
        wrong = f"{api_credential.CREDENTIAL_PREFIX}_{stored.identifier}.notthesecret"
        assert resolve_caller(wrong) is None

    def test_constant_time_comparison_primitive_is_used(self) -> None:
        """Pins the comparison primitive itself — a later refactor to a bare
        `==` must fail this test rather than silently regressing to a
        timing side-channel."""
        stored = get_credential()
        spy = mock.Mock(side_effect=hmac.compare_digest)
        with mock.patch.object(api_credential.hmac, "compare_digest", spy):
            resolve_caller(stored.encode())
        assert spy.called

    def test_second_source_resolves_through_same_entry_point(self) -> None:
        """Mission-criterion-7 evidence: a second, independently-owned
        credential source can be registered against the seam and resolves
        through `resolve_caller` with no change to the entry point."""

        class InMemorySource:
            name = "in-memory-test-source"

            def __init__(self, owned: LocalApiCredential) -> None:
                self._owned = owned

            def resolve(self, presented: str) -> IdentifiedCaller | None:
                parsed = LocalApiCredential.parse(presented)
                if parsed is None:
                    return None
                if parsed.identifier != self._owned.identifier:
                    return None
                if not hmac.compare_digest(parsed.secret, self._owned.secret):
                    return None
                return IdentifiedCaller(identifier=self._owned.identifier, source=self.name)

        file_cred = get_credential()
        second_cred = LocalApiCredential.generate()
        register_source(InMemorySource(second_cred))

        file_result = resolve_caller(file_cred.encode())
        second_result = resolve_caller(second_cred.encode())

        assert file_result is not None and second_result is not None
        assert file_result.source == "file"
        assert second_result.source == "in-memory-test-source"
        assert file_result.source != second_result.source


# ---------------------------------------------------------------------------
# Read-only resolve path (does not create, does not call ensure_dirs)
# ---------------------------------------------------------------------------


class TestReadOnlyResolvePath:
    """`resolve_caller` / `FileCredentialSource.resolve` must be a pure
    lookup: no credential creation, no `ensure_dirs()` call, as a side
    effect of a request-path caller (e.g. middleware, in a later leg)
    resolving a presented credential."""

    def test_resolve_does_not_create_credential_file_when_absent(self) -> None:
        path = credential_path()
        assert not path.exists()

        result = resolve_caller(f"{api_credential.CREDENTIAL_PREFIX}_whatever.secret")

        assert result is None
        assert not path.exists()

    def test_resolve_does_not_call_ensure_dirs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = mock.Mock(side_effect=settings.ensure_dirs)
        monkeypatch.setattr(type(settings), "ensure_dirs", spy)

        resolve_caller(f"{api_credential.CREDENTIAL_PREFIX}_whatever.secret")

        assert not spy.called

    def test_lookup_credential_returns_none_when_absent(self) -> None:
        assert not credential_path().exists()
        assert lookup_credential() is None
        assert not credential_path().exists()

    def test_lookup_credential_does_not_call_ensure_dirs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        spy = mock.Mock(side_effect=settings.ensure_dirs)
        monkeypatch.setattr(type(settings), "ensure_dirs", spy)

        lookup_credential()

        assert not spy.called

    def test_lookup_credential_returns_stored_credential_when_present(self) -> None:
        stored = get_credential()
        found = lookup_credential()
        assert found is not None
        assert found.identifier == stored.identifier
        assert found.secret == stored.secret

    def test_lookup_credential_logs_warning_when_absent(self, caplog) -> None:
        with caplog.at_level("WARNING", logger="the_one.api_credential"):
            result = lookup_credential()
        assert result is None
        assert any(
            "does not exist" in record.getMessage() or str(credential_path()) in record.getMessage()
            for record in caplog.records
        )

    def test_resolve_succeeds_once_credential_exists_via_create_on_first_use(self) -> None:
        """The read-only resolve path and the create-on-first-use path are
        two different entry points, but a credential created via the latter
        (`get_credential`) must still resolve through the former."""
        stored = get_credential()
        result = resolve_caller(stored.encode())
        assert result is not None
        assert result.identifier == stored.identifier


# ---------------------------------------------------------------------------
# Creation, permissions, atomicity (DD2)
# ---------------------------------------------------------------------------


class TestFileCreation:
    def test_first_use_creates_file_and_round_trips(self) -> None:
        path = credential_path()
        assert not path.exists()
        first = get_credential()
        assert path.exists()
        second = get_credential()
        assert second.identifier == first.identifier
        assert second.secret == first.secret

    @pytest.mark.skipif(
        os.name != "posix",
        reason="POSIX-only: Windows does not model 0o600 file permissions",
    )
    def test_credential_file_mode_is_exactly_0600(self) -> None:
        get_credential()
        mode = stat.S_IMODE(os.stat(credential_path()).st_mode)
        assert mode == 0o600

    def test_creation_uses_o_excl_and_never_chmods(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Structural proof of 'no world-readable window': the creation path
        opens with O_EXCL and a 0o600 mode argument in a single os.open call,
        and never calls os.chmod on the credential path itself.

        `get_credential()` also calls `settings.ensure_dirs()`, which (as of
        squawk 0011 / GH #169) chmods the *data directory* to 0o700 — that's
        a deliberate, separate at-rest-permissions fix and not part of what
        this test is proving, so it's excluded from the "never chmods"
        assertion below rather than asserting zero chmod calls process-wide."""
        open_calls: list[tuple[str, int, int]] = []
        chmod_calls: list[str] = []

        real_open = os.open
        real_chmod = os.chmod

        def spy_open(path, flags, mode=0o777, *a, **k):
            open_calls.append((str(path), flags, mode))
            return real_open(path, flags, mode, *a, **k)

        def spy_chmod(path, mode, *a, **k):
            chmod_calls.append(str(path))
            return real_chmod(path, mode, *a, **k)

        monkeypatch.setattr(api_credential.os, "open", spy_open)
        monkeypatch.setattr(api_credential.os, "chmod", spy_chmod)

        get_credential()

        assert len(open_calls) == 1
        _, flags, mode = open_calls[0]
        assert flags & os.O_EXCL
        assert flags & os.O_CREAT
        assert flags & os.O_WRONLY
        assert mode == 0o600
        assert str(credential_path()) not in chmod_calls
        assert chmod_calls == [str(settings.data_dir)]

    def test_creation_never_writes_canonical_path_directly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Structural proof of atomicity w.r.t. readers: os.open is only ever
        called against a temp file, never the canonical path — the canonical
        path's content changes only via the single atomic os.replace call, so
        a partially-written file is never observable there."""
        opened_paths: list[str] = []
        replaced: list[tuple[str, str]] = []

        real_open = os.open
        real_replace = os.replace

        def spy_open(path, *a, **k):
            opened_paths.append(str(path))
            return real_open(path, *a, **k)

        def spy_replace(src, dst):
            replaced.append((str(src), str(dst)))
            return real_replace(src, dst)

        monkeypatch.setattr(api_credential.os, "open", spy_open)
        monkeypatch.setattr(api_credential.os, "replace", spy_replace)

        get_credential()

        canonical = str(credential_path())
        assert canonical not in opened_paths
        assert len(replaced) == 1
        assert replaced[0][1] == canonical

    def test_data_dir_created_if_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # settings.data_dir points at tmp_path (already exists per pytest),
        # but ensure_dirs() must handle a nested, not-yet-created path too.
        nested = credential_path().parent / "nested" / "deeper"
        monkeypatch.setattr(settings, "data_dir", nested)
        assert not nested.exists()
        get_credential()
        assert nested.exists()
        assert credential_path().exists()

    def test_empty_credential_file_raises_named_error(self) -> None:
        path = credential_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
        os.chmod(path, 0o600)
        with pytest.raises(CredentialFileError, match="rotate-api-credential"):
            get_credential()

    def test_malformed_credential_file_raises_named_error(self) -> None:
        path = credential_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not-a-valid-credential")
        os.chmod(path, 0o600)
        with pytest.raises(CredentialFileError, match=re.escape(str(path))):
            get_credential()


# ---------------------------------------------------------------------------
# Cache contract
# ---------------------------------------------------------------------------


class TestCacheContract:
    def test_out_of_band_rewrite_is_visible_without_restart(self) -> None:
        first = get_credential()
        new_cred = LocalApiCredential.generate()
        # Rewrite out-of-band exactly as rotate does: temp file + os.replace.
        api_credential._write_new_credential_atomic(credential_path(), new_cred)
        second = get_credential()
        assert second.identifier == new_cred.identifier
        assert second.identifier != first.identifier

    def test_cache_invalidation_uses_inequality_not_greater_than(self) -> None:
        """Pins the specific footgun called out in the Cache Contract: a
        `new_mtime > cached_mtime` guard would silently skip a rebuild after
        a backward wall-clock step. Simulate that by inflating the cached
        mtime_ns past what the next real write will produce, then asserting
        the rewrite is still picked up."""
        get_credential()
        cache_key = str(credential_path())
        assert cache_key in api_credential._cache
        api_credential._cache[cache_key].mtime_ns += 10**9  # +1s, simulating
        # a cached value from "the future" relative to the next real write's
        # mtime.

        new_cred = LocalApiCredential.generate()
        api_credential._write_new_credential_atomic(credential_path(), new_cred)

        result = get_credential()
        assert result.identifier == new_cred.identifier

    def test_data_dir_swap_with_no_cache_reset_returns_correct_credential(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Proves the cache's correctness no longer depends on any test (or
        caller) remembering to reset `_cache` between data_dir swaps — the
        cache is keyed by resolved path, so a single-slot cache's failure
        mode (serving the previous directory's credential after a data_dir
        swap, whenever the new file's mtime_ns/size happen to coincide with
        the stale cached values) cannot occur regardless of what the two
        directories' stat values happen to be.

        Deliberately does NOT touch `api_credential._cache` anywhere in this
        test body (the autouse fixture's reset before the test doesn't
        count — the swaps below are mid-test, with nothing resetting
        between them)."""
        dir_a = tmp_path / "dir-a"
        dir_b = tmp_path / "dir-b"
        dir_a.mkdir()
        dir_b.mkdir()

        monkeypatch.setattr(settings, "data_dir", dir_a)
        cred_a = get_credential()

        monkeypatch.setattr(settings, "data_dir", dir_b)
        cred_b = get_credential()
        assert cred_b.identifier != cred_a.identifier

        # Swap back to dir_a with still no cache reset: must return dir_a's
        # credential, not whatever is cached for dir_b.
        monkeypatch.setattr(settings, "data_dir", dir_a)
        cred_a_again = get_credential()
        assert cred_a_again.identifier == cred_a.identifier
        assert cred_a_again.secret == cred_a.secret


class TestRotateCredentialFunction:
    """Direct, in-process coverage of `rotate_credential()` — cheaper than
    the CLI-subprocess tests below, which additionally cover the
    subcommand's stdout contract and THE_ONE_DATA_DIR targeting."""

    def test_rotate_replaces_value_and_stays_mode_0600(self) -> None:
        first = get_credential()
        second = rotate_credential()
        assert second.identifier != first.identifier
        assert second.secret != first.secret
        if os.name == "posix":
            mode = stat.S_IMODE(os.stat(credential_path()).st_mode)
            assert mode == 0o600

    def test_rotate_against_missing_credential_creates_one(self) -> None:
        assert not credential_path().exists()
        cred = rotate_credential()
        assert credential_path().exists()
        assert isinstance(cred, LocalApiCredential)


# ---------------------------------------------------------------------------
# Rotation (DD9) — via the real CLI subprocess, per the leg's Verification
# Steps.
# ---------------------------------------------------------------------------


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "the_one.main", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestRotateSubcommand:
    def test_rotate_replaces_credential_exits_zero_no_secret_printed(self, tmp_path: Path) -> None:
        env = {**os.environ, "THE_ONE_DATA_DIR": str(tmp_path)}
        # Seed an existing credential first via a preliminary rotate (also
        # exercises the "no credential yet" branch, reported as created).
        first = _run_cli(["rotate-api-credential"], env)
        assert first.returncode == 0
        assert "created" in first.stdout

        cred_path = tmp_path / "api-credential"
        before = cred_path.read_text()
        before_mode = stat.S_IMODE(os.stat(cred_path).st_mode)

        second = _run_cli(["rotate-api-credential"], env)
        assert second.returncode == 0
        assert "replaced" in second.stdout

        after = cred_path.read_text()
        after_mode = stat.S_IMODE(os.stat(cred_path).st_mode)

        assert after != before
        if os.name == "posix":
            assert before_mode == 0o600
            assert after_mode == 0o600

        parsed_before = LocalApiCredential.parse(before.strip())
        parsed_after = LocalApiCredential.parse(after.strip())
        assert parsed_before is not None and parsed_after is not None
        # The secret must never appear in stdout/stderr of either run.
        for proc in (first, second):
            assert parsed_before.secret not in proc.stdout
            assert parsed_before.secret not in proc.stderr
            assert parsed_after.secret not in proc.stdout
            assert parsed_after.secret not in proc.stderr

    def test_rotate_operates_on_settings_resolved_data_dir_only(self, tmp_path: Path) -> None:
        """Rotating against THE_ONE_DATA_DIR=<scratch> must never touch the
        operator's default (HOME-resolved) data directory."""
        target_dir = tmp_path / "target"
        fake_home = tmp_path / "fake-home"
        target_dir.mkdir()
        fake_home.mkdir()

        env = {
            **os.environ,
            "THE_ONE_DATA_DIR": str(target_dir),
            "HOME": str(fake_home),
        }
        result = _run_cli(["rotate-api-credential"], env)
        assert result.returncode == 0
        assert (target_dir / "api-credential").exists()

        # The operator's "default" location (resolved from fake_home via
        # platformdirs) must remain untouched — no api-credential file
        # anywhere under it.
        default_hits = list(fake_home.rglob("api-credential"))
        assert default_hits == []

    def test_cli_usage_text_lists_rotate_subcommand(self) -> None:
        env = {**os.environ}
        env.pop("THE_ONE_DATA_DIR", None)
        result = _run_cli(["bogus-unrecognized-subcommand"], env)
        assert result.returncode == 1
        assert "rotate-api-credential" in result.stdout
