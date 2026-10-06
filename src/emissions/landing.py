"""Landing zone: raw downloads are written to disk before anything parses them.

Keeping the exact bytes makes every run reproducible and auditable: if a parser bug is
found later, the data can be reprocessed without depending on what the source serves
today. Files are content-addressed, so re-downloading unchanged data costs no space.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from emissions.sources.base import Download


@dataclass(frozen=True, slots=True)
class LandedFile:
    source: str
    url: str
    path: Path
    sha256: str
    size_bytes: int
    fetched_at: datetime


class LocalLandingStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, source: str, download: Download) -> LandedFile:
        digest = hashlib.sha256(download.content).hexdigest()
        ext = _extension(download.content_type)
        now = datetime.now(UTC)
        path = self._root / source / f"{now:%Y-%m-%d}" / f"{digest[:16]}{ext}"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(download.content)
            tmp.replace(path)  # atomic: a crash never leaves a half-written file
        return LandedFile(source, download.url, path, digest, len(download.content), now)


def _extension(content_type: str) -> str:
    mime = content_type.split(";")[0].strip().lower()
    if mime in ("application/json", "text/json"):
        return ".json"
    if mime in ("text/csv", "text/plain"):
        return ".csv"
    return mimetypes.guess_extension(mime) or ".bin"
