"""Gemeinsame Fixtures für alle Tests."""

import json
from pathlib import Path

import pytest

SAMPLE_ROOMS = [
    {
        "id": "room-id-alpha",
        "title": "Alpha Testroom",
        "type": "group",
    },
    {
        "id": "room-id-beta",
        "title": "Beta Produktiv",
        "type": "group",
    },
    {
        "id": "room-id-gamma",
        "title": "Gamma Support",
        "type": "group",
    },
]


@pytest.fixture
def roomlist_file(tmp_path: Path) -> Path:
    """Schreibt SAMPLE_ROOMS in eine temporäre roomlist.json."""
    path = tmp_path / "roomlist.json"
    path.write_text(json.dumps({"items": SAMPLE_ROOMS}))
    return path


@pytest.fixture
def mock_response():
    """Erstellt eine httpx-ähnliche Mock-Response."""
    class MockResponse:
        def __init__(self, data: dict, status_code: int = 200):
            self._data = data
            self.status_code = status_code
            self.text = json.dumps(data)

        def json(self) -> dict:
            return self._data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                import httpx
                raise httpx.HTTPStatusError(
                    self.text,
                    request=None,  # type: ignore[arg-type]
                    response=self,  # type: ignore[arg-type]
                )

    return MockResponse
