from __future__ import annotations

from pathlib import Path

from emissions.landing import LocalLandingStore
from emissions.sources.base import Download


def test_landing_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = LocalLandingStore(tmp_path)
    a = store.save("owid", Download("u", b"a,b\n1,2\n", "text/csv; charset=utf-8"))
    again = store.save("owid", Download("u", b"a,b\n1,2\n", "text/csv"))
    other = store.save("owid", Download("u", b"different", "text/csv"))
    assert a.path == again.path
    assert a.path != other.path
    assert a.path.suffix == ".csv"
    assert a.path.read_bytes() == b"a,b\n1,2\n"
    assert a.size_bytes == 8
    assert len(a.sha256) == 64
    assert not list(tmp_path.rglob("*.part"))


def test_landing_extension_for_json_and_unknown(tmp_path: Path) -> None:
    store = LocalLandingStore(tmp_path)
    assert store.save("x", Download("u", b"{}", "application/json")).path.suffix == ".json"
    assert store.save("x", Download("u", b"?", "")).path.suffix == ".bin"
