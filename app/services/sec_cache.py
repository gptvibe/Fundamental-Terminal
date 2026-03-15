from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)
_last_periodic_prune_monotonic = 0.0


@dataclass(frozen=True, slots=True)
class CachePolicy:
    endpoint: str
    cik: str | None
    accession: str | None
    ttl_seconds: float | None


class SecHttpCache:
    def __init__(self, cache_root: Path | None = None) -> None:
        root = cache_root or (Path(__file__).resolve().parents[2] / "data" / "sec_cache")
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def get(self, method: str, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response | None:
        policy = _policy_for_request(method, url)
        if policy is None:
            return None

        normalized_url = _normalized_url(url, params=params)
        cache_path = self._cache_path(policy)
        if not cache_path.exists():
            logger.info("CACHE MISS %s", normalized_url)
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            expires_at = payload.get("expires_at")
            if expires_at is not None and time.time() >= float(expires_at):
                logger.info("CACHE MISS %s", normalized_url)
                return None

            body = base64.b64decode(str(payload.get("content_b64", "")), validate=True)
            request = httpx.Request(method.upper(), normalized_url)
            response = httpx.Response(
                int(payload.get("status_code", 200)),
                headers=payload.get("headers", {}),
                content=body,
                request=request,
            )
            logger.info("CACHE HIT %s", normalized_url)
            return response
        except Exception:
            logger.info("CACHE MISS %s", normalized_url)
            return None

    def put(
        self,
        method: str,
        url: str,
        response: httpx.Response,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        policy = _policy_for_request(method, url)
        if policy is None:
            return

        if response.status_code >= 400:
            return

        normalized_url = _normalized_url(url, params=params)
        cache_path = self._cache_path(policy)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        response.read()
        created_at = time.time()
        expires_at = None if policy.ttl_seconds is None else created_at + policy.ttl_seconds
        payload = {
            "endpoint": policy.endpoint,
            "cik": policy.cik,
            "accession": policy.accession,
            "url": normalized_url,
            "status_code": response.status_code,
            "headers": dict(response.headers.items()),
            "created_at": created_at,
            "expires_at": expires_at,
            "content_b64": base64.b64encode(response.content).decode("ascii"),
        }

        tmp_path = cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(cache_path)

    def _cache_path(self, policy: CachePolicy) -> Path:
        filename = _cache_filename(policy)
        return self._root / filename

    def prune_expired(self, *, max_entries: int | None = None) -> int:
        removed = 0
        scanned = 0
        now = time.time()
        for cache_path in self._root.glob("*.json"):
            if max_entries is not None and scanned >= max_entries:
                break
            scanned += 1
            try:
                metadata = json.loads(cache_path.read_text(encoding="utf-8"))
                expires_at = metadata.get("expires_at")
                if expires_at is None or now < float(expires_at):
                    continue
            except Exception:
                # Corrupted metadata is treated as stale and removed.
                pass

            cache_path.unlink(missing_ok=True)
            removed += 1

        return removed


def _normalized_url(url: str, *, params: dict[str, Any] | None = None) -> str:
    parsed = urlsplit(url)
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    if params:
        for key, value in params.items():
            if isinstance(value, (list, tuple)):
                for item in value:
                    query_items.append((str(key), str(item)))
            else:
                query_items.append((str(key), str(value)))
    query_items.sort()
    encoded = urlencode(query_items, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, encoded, ""))


def _policy_for_request(method: str, url: str) -> CachePolicy | None:
    if method.upper() != "GET":
        return None

    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if not host.endswith("sec.gov"):
        return None

    submissions_match = re.search(r"/submissions/cik(\d{10})\.json$", path)
    if submissions_match:
        return CachePolicy("submissions", submissions_match.group(1), None, 24 * 60 * 60)

    companyfacts_match = re.search(r"/api/xbrl/companyfacts/cik(\d{10})\.json$", path)
    if companyfacts_match:
        return CachePolicy("companyfacts", companyfacts_match.group(1), None, 7 * 24 * 60 * 60)

    filing_index_match = re.search(r"/archives/edgar/data/(\d+)/(\d+)/index\.json$", path)
    if filing_index_match:
        cik = filing_index_match.group(1).zfill(10)
        accession = filing_index_match.group(2)
        return CachePolicy("filing_index", cik, accession, None)

    xml_match = re.search(r"/archives/edgar/data/(\d+)/(\d+)/([^/]+\.xml)$", path)
    if xml_match:
        cik = xml_match.group(1).zfill(10)
        accession = xml_match.group(2)
        name = xml_match.group(3).lower()
        if "ownership" in name or "form4" in name or "f345" in name:
            return CachePolicy("form4_xml", cik, accession, None)
        if "13f" in name or "infotable" in name or "informationtable" in name:
            return CachePolicy("13f_xml", cik, accession, None)
        return CachePolicy("filing_xml", cik, accession, None)

    return None


def _cache_filename(policy: CachePolicy) -> str:
    cik = policy.cik or "unknown"
    if policy.accession:
        return f"{policy.endpoint}_{cik}_{policy.accession}.json"
    return f"{policy.endpoint}_{cik}.json"


def prune_sec_cache(*, max_entries: int | None = None) -> int:
    return sec_http_cache.prune_expired(max_entries=max_entries)


def prune_sec_cache_periodic(*, min_interval_seconds: float, max_entries: int | None = None) -> int:
    global _last_periodic_prune_monotonic
    now = time.monotonic()
    elapsed = now - _last_periodic_prune_monotonic
    if elapsed < min_interval_seconds:
        return 0

    removed = prune_sec_cache(max_entries=max_entries)
    _last_periodic_prune_monotonic = now
    return removed


sec_http_cache = SecHttpCache()
