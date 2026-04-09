"""Tests für CLI-Befehle via typer CliRunner."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import send_message
from send_message import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def patch_paths(tmp_path: Path, roomlist_file: Path):
    """Alle Tests bekommen tmp-Pfade für roomlist, tokens und config."""
    with (
        patch.object(send_message, "ROOMLIST_PATH", roomlist_file),
        patch.object(send_message, "TOKENS_PATH", tmp_path / "tokens.json"),
        patch.object(send_message, "CONFIG_PATH", tmp_path / "config.json"),
    ):
        yield


@pytest.fixture
def valid_token(tmp_path: Path):
    """Speichert einen gültigen OAuth-Token für Tests."""
    path = tmp_path / "tokens.json"
    data = {"access_token": "test-token", "refresh_token": "r", "expires_at": time.time() + 3600}
    with patch.object(send_message, "TOKENS_PATH", path):
        send_message._save_tokens(data)
    return "test-token"


def _mock_post(msg_id: str = "msg-123") -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {"id": msg_id}
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_shows_rooms() -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "Alpha Testroom" in result.output
    assert "Beta Produktiv" in result.output


def test_list_search_filter() -> None:
    result = runner.invoke(app, ["list", "--search", "gamma"])
    assert result.exit_code == 0
    assert "Gamma Support" in result.output
    assert "Alpha" not in result.output


def test_list_search_no_match() -> None:
    result = runner.invoke(app, ["list", "--search", "nichtvorhanden"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def test_send_text(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(app, ["send", "alpha", "Hallo Welt"])
    assert result.exit_code == 0
    assert "Gesendet" in result.output
    payload = mock_post.call_args.kwargs["json"]
    assert payload["text"] == "Hallo Welt"
    assert payload["roomId"] == "room-id-alpha"


def test_send_markdown(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(app, ["send", "alpha", "**fett**", "--markdown"])
    assert result.exit_code == 0
    payload = mock_post.call_args.kwargs["json"]
    assert "markdown" in payload
    assert "text" not in payload


def test_send_file(valid_token, tmp_path: Path) -> None:
    test_file = tmp_path / "test.log"
    test_file.write_text("Loginhalt")
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(app, ["send", "alpha", "Mit Anhang", "--file", str(test_file)])
    assert result.exit_code == 0
    # multipart sendet über data=, nicht json=
    assert mock_post.call_args.kwargs.get("files") is not None


def test_send_missing_file(valid_token, tmp_path: Path) -> None:
    missing = str(tmp_path / "missing.log")
    result = runner.invoke(app, ["send", "alpha", "Fehler", "--file", missing])
    assert result.exit_code == 1


def test_send_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBEX_TOKEN", raising=False)
    result = runner.invoke(app, ["send", "alpha", "Test"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# dm
# ---------------------------------------------------------------------------


def test_dm_sends_to_email(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(app, ["dm", "user@example.com", "Hallo"])
    assert result.exit_code == 0
    payload = mock_post.call_args.kwargs["json"]
    assert payload["toPersonEmail"] == "user@example.com"
    assert payload["text"] == "Hallo"


# ---------------------------------------------------------------------------
# card
# ---------------------------------------------------------------------------


def test_card_basic(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(
            app,
            [
                "card",
                "alpha",
                "--title",
                "Alert",
                "--text",
                "Server down",
            ],
        )
    assert result.exit_code == 0
    payload = mock_post.call_args.kwargs["json"]
    card = payload["attachments"][0]["content"]
    assert card["body"][0]["text"] == "Alert"
    assert card["body"][1]["text"] == "Server down"


def test_card_color_attention(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(
            app,
            [
                "card",
                "alpha",
                "--title",
                "Fehler",
                "--text",
                "Kritisch",
                "--color",
                "attention",
            ],
        )
    assert result.exit_code == 0
    card = mock_post.call_args.kwargs["json"]["attachments"][0]["content"]
    assert card["body"][0]["color"] == "Attention"


def test_card_with_facts(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(
            app,
            [
                "card",
                "alpha",
                "--title",
                "T",
                "--text",
                "M",
                "--fact",
                "Host=server1",
                "--fact",
                "Status=down",
            ],
        )
    assert result.exit_code == 0
    card = mock_post.call_args.kwargs["json"]["attachments"][0]["content"]
    fact_set = next(b for b in card["body"] if b["type"] == "FactSet")
    assert {"title": "Host", "value": "server1"} in fact_set["facts"]


def test_card_with_url(valid_token) -> None:
    with patch("send_message.httpx.post", return_value=_mock_post()) as mock_post:
        result = runner.invoke(
            app,
            [
                "card",
                "alpha",
                "--title",
                "T",
                "--text",
                "M",
                "--url",
                "https://example.com",
                "--url-label",
                "Details",
            ],
        )
    assert result.exit_code == 0
    card = mock_post.call_args.kwargs["json"]["attachments"][0]["content"]
    assert card["actions"][0]["url"] == "https://example.com"


# ---------------------------------------------------------------------------
# apprise-url
# ---------------------------------------------------------------------------


def test_apprise_url_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBEX_TOKEN", "my-bot-token")
    result = runner.invoke(app, ["apprise-url", "alpha"])
    assert result.exit_code == 0
    assert "wxteams://my-bot-token/room-id-alpha/" in result.output


def test_apprise_url_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEBEX_TOKEN", raising=False)
    result = runner.invoke(app, ["apprise-url", "alpha"])
    assert result.exit_code == 1
