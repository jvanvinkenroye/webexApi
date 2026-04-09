"""Tests für Hilfsfunktionen."""

import pytest

import send_message


@pytest.mark.parametrize(
    "markdown,expected_key",
    [
        (False, "text"),
        (True, "markdown"),
    ],
)
def test_build_message_fields_key(markdown: bool, expected_key: str) -> None:
    result = send_message._build_message_fields({"roomId": "r1"}, "Hallo", markdown)
    assert expected_key in result
    assert result[expected_key] == "Hallo"


def test_build_message_fields_preserves_target() -> None:
    result = send_message._build_message_fields({"roomId": "r1"}, "msg", False)
    assert result["roomId"] == "r1"


def test_build_message_fields_does_not_mutate_target() -> None:
    target = {"roomId": "r1"}
    send_message._build_message_fields(target, "msg", False)
    assert "text" not in target


def test_build_message_fields_direct_message() -> None:
    result = send_message._build_message_fields({"toPersonEmail": "a@b.de"}, "Hi", True)
    assert result["toPersonEmail"] == "a@b.de"
    assert result["markdown"] == "Hi"
