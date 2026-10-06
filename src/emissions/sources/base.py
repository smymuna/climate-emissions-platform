from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx

from emissions.quality.steps import IndicatorTarget
from emissions.records import Record

log = logging.getLogger(__name__)


class SourceError(Exception):
    """A source could not be downloaded or its payload has an unexpected shape."""


@dataclass(frozen=True, slots=True)
class Download:
    """Raw bytes exactly as received. Kept in the landing zone before any parsing."""

    url: str
    content: bytes
    content_type: str


class SourceAdapter(Protocol):
    """Everything source-specific: how to download, how to parse, how codes map.

    The cleaning and validation steps are shared and live in ``emissions.quality``.
    """

    code: str
    country_map: Mapping[str, str]
    """Source country code -> ISO 3166 alpha-2."""
    indicator_map: Mapping[str, IndicatorTarget]
    """Source indicator code -> (metric, sector, gas)."""

    def extract(self, http: httpx.Client, *, last_year: int) -> list[Download]: ...

    def parse(self, downloads: list[Download]) -> list[Record]: ...


RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def get(
    http: httpx.Client,
    url: str,
    params: object = None,
    *,
    retries: int = 3,
    backoff_s: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """GET with retries on rate limiting, server errors and network errors.

    Public statistics APIs are often slow or briefly unavailable. Backoff is exponential
    (2 s, 4 s, 8 s by default). Other 4xx errors are not retried: they won't fix themselves.
    """
    for attempt in range(retries + 1):
        try:
            response = http.get(url, params=params)  # type: ignore[arg-type]
        except httpx.TransportError as exc:
            if attempt == retries:
                raise SourceError(f"{url} unreachable: {exc}") from exc
            log.warning("GET %s failed (%s), retry %d/%d", url, exc, attempt + 1, retries)
            sleep(backoff_s * 2**attempt)
            continue
        if response.status_code in RETRY_STATUSES and attempt < retries:
            log.warning(
                "GET %s -> HTTP %d, retry %d/%d", url, response.status_code, attempt + 1, retries
            )
            sleep(backoff_s * 2**attempt)
            continue
        if response.is_error:
            raise SourceError(f"{url} returned HTTP {response.status_code}")
        return response
    raise AssertionError("unreachable")
