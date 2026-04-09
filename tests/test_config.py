"""Tests für Konfiguration (_load_config, _save_config, _get_room)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import send_message
from send_message import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# _load_config / _save_config
# ---------------------------------------------------------------------------


def test_load_config_missing(tmp_path: Path) -> None:
    with patch.object(send_message, "CONFIG_PATH", tmp_path / "none.json"):
        assert send_message._load_config() == {}


def test_save_and_load_config(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    data = {"bot_token": "tok", "default_room": "Alpha"}
    with patch.object(send_message, "CONFIG_PATH", path):
        send_message._save_config(data)
        loaded = send_message._load_config()
    assert loaded == data


def test_save_config_sets_permissions(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    with patch.object(send_message, "CONFIG_PATH", path):
        send_message._save_config({"bot_token": "x"})
    assert oct(path.stat().st_mode)[-3:] == "600"


# ---------------------------------------------------------------------------
# _get_room
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_paths(tmp_path: Path, roomlist_file: Path):
    with (
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
        patch.object(send_message, "CONFIG_PATH", tmp_path / "config.json"),
    ):
        yield


def test_get_room_with_arg() -> None:
    assert send_message._get_room("alpha") == "room-id-alpha"


def test_get_room_default_from_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"default_room": "beta"}))
    with patch.object(send_message, "CONFIG_PATH", config_file):
        result = send_message._get_room(None)
    assert result == "room-id-beta"


def test_get_room_no_arg_no_config() -> None:
    import click

    with pytest.raises((SystemExit, click.exceptions.Exit)):
        send_message._get_room(None)


# ---------------------------------------------------------------------------
# _get_token with config bot_token
# ---------------------------------------------------------------------------


def test_get_token_from_config_bot_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBEX_TOKEN", raising=False)
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"bot_token": "config-bot-token"}))
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "TOKENS_PATH", tmp_path / "none.json"),
    ):
        token = send_message._get_token(None)
    assert token == "config-bot-token"


# ---------------------------------------------------------------------------
# setup-Befehl
# ---------------------------------------------------------------------------


def test_setup_saves_bot_token(tmp_path: Path, roomlist_file: Path) -> None:
    config_file = tmp_path / "config.json"
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
    ):
        # Eingabe: Token, kein Standard-Raum, kein OAuth
        result = runner.invoke(app, ["setup"], input="new-bot-token\n\nn\n")
    assert result.exit_code == 0, result.output
    config = json.loads(config_file.read_text())
    assert config["bot_token"] == "new-bot-token"


def test_setup_preserves_existing_token(tmp_path: Path, roomlist_file: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"bot_token": "old-token"}))
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
    ):
        # Eingabe: leeres Token (Enter), kein Raum, kein OAuth
        result = runner.invoke(app, ["setup"], input="\n\nn\n")
    assert result.exit_code == 0, result.output
    config = json.loads(config_file.read_text())
    assert config["bot_token"] == "old-token"


def test_setup_sets_default_room_by_number(tmp_path: Path, roomlist_file: Path) -> None:
    config_file = tmp_path / "config.json"
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
    ):
        # Token leer, Raum #2 (Beta Produktiv), kein OAuth
        result = runner.invoke(app, ["setup"], input="\n2\nn\n")
    assert result.exit_code == 0, result.output
    config = json.loads(config_file.read_text())
    assert config["default_room"] == "Beta Produktiv"


def test_setup_sets_default_room_by_name(tmp_path: Path, roomlist_file: Path) -> None:
    config_file = tmp_path / "config.json"
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
    ):
        # Token leer, Raum per Name, kein OAuth
        result = runner.invoke(app, ["setup"], input="\ngamma\nn\n")
    assert result.exit_code == 0, result.output
    config = json.loads(config_file.read_text())
    assert config["default_room"] == "gamma"


def test_setup_saves_oauth_credentials(tmp_path: Path, roomlist_file: Path) -> None:
    config_file = tmp_path / "config.json"
    with (
        patch.object(send_message, "CONFIG_PATH", config_file),
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
    ):
        # Token, kein Raum, OAuth ja, client_id, client_secret
        result = runner.invoke(app, ["setup"], input="bottoken\n\ny\nclientid123\nsecret456\n")
    assert result.exit_code == 0, result.output
    config = json.loads(config_file.read_text())
    assert config["oauth_client_id"] == "clientid123"
    assert config["oauth_client_secret"] == "secret456"
