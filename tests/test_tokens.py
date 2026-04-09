"""Tests für Token-Speicherung und -Auflösung."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

import send_message

# ---------------------------------------------------------------------------
# _load_tokens / _save_tokens
# ---------------------------------------------------------------------------


def test_load_tokens_missing(tmp_path: Path) -> None:
    with patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"):
        assert send_message._load_tokens() is None


def test_save_and_load_tokens(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    data = {"access_token": "abc", "refresh_token": "xyz", "expires_at": 9999999999.0}
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(data)
        loaded = send_message._load_tokens()
    assert loaded == data


def test_save_tokens_sets_permissions(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    data = {"access_token": "abc", "refresh_token": "xyz", "expires_at": 9999999999.0}
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(data)
    # 0o600 = owner read/write only
    assert oct(path.stat().st_mode)[-3:] == "600"


# ---------------------------------------------------------------------------
# _get_valid_oauth_token
# ---------------------------------------------------------------------------


def test_oauth_token_no_file(tmp_path: Path) -> None:
    with patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"):
        assert send_message._get_valid_oauth_token() is None


def test_oauth_token_still_valid(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    data = {
        "access_token": "valid-token",
        "refresh_token": "refresh",
        "expires_at": time.time() + 3600,
    }
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(data)
        token = send_message._get_valid_oauth_token()
    assert token == "valid-token"


def test_oauth_token_expired_refresh_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    expired = {
        "access_token": "old-token",
        "refresh_token": "my-refresh",
        "expires_at": time.time() - 10,
    }
    new_data = {
        "access_token": "new-token",
        "refresh_token": "new-refresh",
        "expires_in": 7200,
    }

    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(expired)
        refreshed = {**new_data, "expires_at": time.time() + 7200}
        with patch.object(send_message, "_refresh_access_token", return_value=refreshed):
            token = send_message._get_valid_oauth_token()

    assert token == "new-token"


def test_oauth_token_expired_refresh_fails(tmp_path: Path, capsys) -> None:
    path = tmp_path / "tokens.json"
    expired = {
        "access_token": "old-token",
        "refresh_token": "my-refresh",
        "expires_at": time.time() - 10,
    }
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(expired)
        with patch.object(
            send_message, "_refresh_access_token", side_effect=RuntimeError("Netzwerkfehler")
        ):
            token = send_message._get_valid_oauth_token()

    assert token is None
    captured = capsys.readouterr()
    assert "fehlgeschlagen" in captured.err


# ---------------------------------------------------------------------------
# _get_token
# ---------------------------------------------------------------------------


def test_get_token_explicit_arg(tmp_path: Path) -> None:
    with patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"):
        assert send_message._get_token("direct-token") == "direct-token"


def test_get_token_from_oauth(tmp_path: Path) -> None:
    path = tmp_path / "tokens.json"
    data = {"access_token": "oauth-token", "refresh_token": "r", "expires_at": time.time() + 3600}
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(data)
        token = send_message._get_token(None)
    assert token == "oauth-token"


def test_get_token_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBEX_TOKEN", "env-bot-token")
    with (
        patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"),
        patch.object(send_message, "CONFIG_PATH", tmp_path / "none_config.json"),
    ):
        assert send_message._get_token(None) == "env-bot-token"


def test_get_token_none_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import click

    monkeypatch.delenv("WEBEX_TOKEN", raising=False)
    with (
        patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"),
        patch.object(send_message, "CONFIG_PATH", tmp_path / "none_config.json"),
    ):
        with pytest.raises((SystemExit, click.exceptions.Exit)):
            send_message._get_token(None)
