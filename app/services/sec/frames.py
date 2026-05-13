"""SEC XBRL frames API client for cross-company concept data.

The SEC EDGAR frames API returns all reported values for a given US-GAAP concept
across the entire public universe for a single period in one request.  This is
the most efficient way to populate a screener with official data because it
avoids per-company calls entirely.

Reference: https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.observability import observe_upstream_request
from app.services.sec_cache import sec_http_cache
from app.services.sec.refresh_orchestrator import _select_statement_period
from app.services.shared_upstream_cache import shared_upstream_cache

logger = logging.getLogger(__name__)

_FRAMES_BASE_URL = "https://data.sec.gov/api/xbrl/frames"
_DEFAULT_USER_AGENT = "Fundamental-Terminal research@example.com"
_MIN_REQUEST_INTERVAL_SECONDS = 0.12  # ~8 req/s — SEC asks for <=10/s
_MAX_RETRIES = 3

# Maps internal concept_key -> list of (taxonomy, tag, unit, period_suffix_hint)
# period_suffix_hint is "flow" (duration) or "instant" (point-in-time).
# Multiple tags per key are tried in order; the first non-empty frame wins.

XBRL_CONCEPT_MAP: dict[str, list[tuple[str, str, str, str]]] = {
    "revenue": [
        ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD", "flow"),
        ("us-gaap", "Revenues", "USD", "flow"),
        ("us-gaap", "SalesRevenueNet", "USD", "flow"),
    ],
    "operating_income": [
        ("us-gaap", "OperatingIncomeLoss", "USD", "flow"),
    ],
    "net_income": [
        ("us-gaap", "NetIncomeLoss", "USD", "flow"),
    ],
    "assets": [
        ("us-gaap", "Assets", "USD", "instant"),
    ],
    "liabilities": [
        ("us-gaap", "Liabilities", "USD", "instant"),
    ],
    "operating_cash_flow": [
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD", "flow"),
    ],
    "capex": [
        ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD", "flow"),
        ("us-gaap", "CapitalExpenditureDiscontinuedOperations", "USD", "flow"),
    ],
    "diluted_shares": [
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares", "flow"),
        ("us-gaap", "CommonStockSharesOutstanding", "shares", "instant"),
    ],
}

ALL_SCREENER_CONCEPT_KEYS: tuple[str, ...] = tuple(XBRL_CONCEPT_MAP.keys())


def build_frame_period_labels(
    fiscal_year: int,
    fiscal_quarter: int | None,
    period_suffix_hint: str,
) -> list[str]:
    """Return candidate period label strings in preference order."""
    if fiscal_quarter is not None:
        q = fiscal_quarter
        if period_suffix_hint == "instant":
            return [f"CY{fiscal_year}Q{q}I"]
        return [f"CY{fiscal_year}Q{q}"]
    return [f"CY{fiscal_year}"]


@dataclass
class FrameDataPoint:
    accn: str
    cik: int
    entity_name: str
    loc: str
    end: str
    val: float


@dataclass
class FrameResponse:
    taxonomy: str
    tag: str
    cip: str
    label: str
    description: str
    pts: int
    period_label: str
    concept_key: str
    fetched_at: datetime
    data: list[FrameDataPoint] = field(default_factory=list)


class SecFramesClient:
    """HTTP client for the SEC EDGAR XBRL frames endpoint."""

    def __init__(self, user_agent: str = _DEFAULT_USER_AGENT) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip"},
            timeout=30.0,
        )
        self._last_request_at: float = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SecFramesClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = _MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def fetch_frame(
        self,
        taxonomy: str,
        tag: str,
        unit: str,
        period_label: str,
        concept_key: str,
    ) -> FrameResponse | None:
        """Fetch a single frame.  Returns None on 404."""
        url = f"{_FRAMES_BASE_URL}/{taxonomy}/{tag}/{unit}/{period_label}.json"
        response = self._request_frame(url)
        if response is None:
            return None
        return _frame_response_from_http_response(
            response,
            period_label=period_label,
            concept_key=concept_key,
            fallback_taxonomy=taxonomy,
            fallback_tag=tag,
        )

    def _request_frame(self, url: str) -> httpx.Response | None:
        cached_response = sec_http_cache.get("GET", url)
        if cached_response is not None:
            return cached_response

        def _fetch_response() -> httpx.Response | None:
            for attempt in range(1, _MAX_RETRIES + 1):
                self._throttle()
                try:
                    with observe_upstream_request(source="sec_xbrl_frames"):
                        response = self._client.get(url)
                except httpx.RequestError as exc:
                    raise RuntimeError(f"SEC frames request failed: {exc}") from exc

                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    if attempt >= _MAX_RETRIES:
                        logger.warning("SEC frames rate-limited after %s attempts; returning no frame", attempt)
                        return None
                    retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
                    logger.warning("SEC frames rate-limited; sleeping %ss", retry_after)
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                if isinstance(response, httpx.Response):
                    sec_http_cache.put("GET", url, response)
                return response

        cache_key = sec_http_cache.cache_key("GET", url)
        if cache_key is None:
            return _fetch_response()
        return shared_upstream_cache.run_singleflight(
            f"sec:GET:{cache_key}",
            wait_for=lambda: sec_http_cache.get("GET", url),
            fill=_fetch_response,
        )

    def fetch_concept_frame(
        self,
        concept_key: str,
        fiscal_year: int,
        fiscal_quarter: int | None,
    ) -> FrameResponse | None:
        """Fetch the best available frame for a concept/period."""
        tag_candidates = XBRL_CONCEPT_MAP.get(concept_key)
        if not tag_candidates:
            raise ValueError(f"Unknown concept_key: {concept_key!r}")

        for taxonomy, tag, unit, hint in tag_candidates:
            for period_label in build_frame_period_labels(fiscal_year, fiscal_quarter, hint):
                frame = self.fetch_frame(taxonomy, tag, unit, period_label, concept_key)
                if frame is not None and frame.data:
                    return frame
        return None


def _frame_response_from_http_response(
    response: httpx.Response,
    *,
    period_label: str,
    concept_key: str,
    fallback_taxonomy: str,
    fallback_tag: str,
) -> FrameResponse:
    fetched_at = datetime.now(tz=timezone.utc)
    raw: dict[str, Any] = response.json()
    data_rows = [
        FrameDataPoint(
            accn=str(row.get("accn", "")),
            cik=int(row.get("cik", 0)),
            entity_name=str(row.get("entityName", "")),
            loc=str(row.get("loc", "")),
            end=str(row.get("end", "")),
            val=float(row.get("val", 0)),
        )
        for row in (raw.get("data") or [])
    ]
    return FrameResponse(
        taxonomy=raw.get("taxonomy", fallback_taxonomy),
        tag=raw.get("tag", fallback_tag),
        cip=raw.get("cip", ""),
        label=raw.get("label", fallback_tag),
        description=raw.get("description", ""),
        pts=int(raw.get("pts", len(data_rows))),
        period_label=period_label,
        concept_key=concept_key,
        fetched_at=fetched_at,
        data=data_rows,
    )


def _retry_after_seconds(value: str | None) -> int:
    try:
        return max(0, int(value or "10"))
    except ValueError:
        return 10


__all__ = [
    "_select_statement_period",
    "ALL_SCREENER_CONCEPT_KEYS",
    "XBRL_CONCEPT_MAP",
    "FrameDataPoint",
    "FrameResponse",
    "SecFramesClient",
    "build_frame_period_labels",
]
