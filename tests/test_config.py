from __future__ import annotations

import pytest

from emissions.config import Settings
from emissions.db.repository import normalise_db_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_normalise_db_url_uses_psycopg3(url: str, expected: str) -> None:
    assert normalise_db_url(url) == expected


def test_cors_origins_from_env_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMISSIONS_CORS_ORIGINS", '["https://a.example", "https://b.example"]')
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]
