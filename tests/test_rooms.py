"""Tests für Raumladen und -auflösung."""

from pathlib import Path
from unittest.mock import patch

import pytest

import send_message

# ---------------------------------------------------------------------------
# _load_rooms
# ---------------------------------------------------------------------------

def test_load_rooms_missing_file(tmp_path: Path) -> None:
    with patch.object(send_message, "ROOMLIST_PATH", tmp_path / "nonexistent.json"):
        assert send_message._load_rooms() == []


def test_load_rooms_returns_items(roomlist_file: Path) -> None:
    with patch.object(send_message, "ROOMLIST_PATH", roomlist_file):
        rooms = send_message._load_rooms()
    assert len(rooms) == 3
    assert rooms[0]["title"] == "Alpha Testroom"


# ---------------------------------------------------------------------------
# _resolve_room
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_roomlist(roomlist_file: Path):
    with patch.object(send_message, "ROOMLIST_PATH", roomlist_file):
        yield


def test_resolve_exact_id() -> None:
    assert send_message._resolve_room("room-id-beta") == "room-id-beta"


def test_resolve_exact_title() -> None:
    assert send_message._resolve_room("Alpha Testroom") == "room-id-alpha"


def test_resolve_partial_title_case_insensitive() -> None:
    assert send_message._resolve_room("gamma") == "room-id-gamma"


def test_resolve_partial_title_uppercase() -> None:
    assert send_message._resolve_room("BETA") == "room-id-beta"


def test_resolve_multiple_matches_exits(capsys) -> None:
    # "a" kommt in "Alpha Testroom" und "Gamma Support" vor → mehrere Treffer
    import click
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        send_message._resolve_room("a")


def test_resolve_unknown_returns_raw_with_warning(capsys) -> None:
    result = send_message._resolve_room("unbekannt-xyz")
    assert result == "unbekannt-xyz"
    captured = capsys.readouterr()
    assert "Warnung" in captured.err


@pytest.mark.parametrize("room_arg,expected_id", [
    ("alpha", "room-id-alpha"),
    ("support", "room-id-gamma"),
    ("room-id-beta", "room-id-beta"),
])
def test_resolve_parametrized(room_arg: str, expected_id: str) -> None:
    assert send_message._resolve_room(room_arg) == expected_id
