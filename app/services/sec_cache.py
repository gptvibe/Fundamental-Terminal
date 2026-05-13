from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.config import settings
from app.observability import record_cache_event

logger = logging.getLogger(__name__)
_last_periodic_prune_monotonic = 0.0


@dataclass(frozen=True, slots=True)
class CachePolicy:
    endpoint: str
    cik: str | None
    accession: str | None
    ttl_seconds: float | None
    allow_conditional_revalidation: bool = False
    source: str = "sec"
    taxonomy: str | None = None
    tag: str | None = None
    period: str | None = None
    as_of: str | None = None
    immutable: bool = False


@dataclass(frozen=True, slots=True)
class CachedResponseEntry:
    policy: CachePolicy
    normalized_url: str
    cache_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SecCacheDiskUsage:
    root: str
    file_count: int
    total_bytes: int
    immutable_file_count: int
    immutable_bytes: int
    expiring_file_count: int
    expiring_bytes: int
    stale_file_count: int
    stale_bytes: int
    unreadable_file_count: int


class SecHttpCache:
    def __init__(self, cache_root: Path | None = None) -> None:
        root = cache_root or (Path(__file__).resolve().parents[2] / "data" / "sec_cache")
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def get(self, method: str, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response | None:
        try:
            entry = self.get_stale(method, url, params=params, headers=headers)
            if entry is None:
                record_cache_event("sec_http", "miss")
                return None
            expires_at = entry.payload.get("expires_at")
            if expires_at is not None and time.time() >= float(expires_at):
                logger.debug("CACHE MISS %s", entry.normalized_url)
                record_cache_event("sec_http", "stale")
                return None
            logger.debug("CACHE HIT %s", entry.normalized_url)
            record_cache_event("sec_http", "hit")
            return _response_from_payload(method, entry.normalized_url, entry.payload)
        except Exception:
            logger.debug("CACHE MISS %s", _normalized_url(url, params=params))
            record_cache_event("sec_http", "miss")
            return None

    def get_stale(self, method: str, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> CachedResponseEntry | None:
        policy = _policy_for_request(method, url)
        if policy is None:
            return None

        normalized_url = _normalized_url(url, params=params)
        cache_path = self._cache_path(policy, normalized_url)
        if not cache_path.exists():
            logger.debug("CACHE MISS %s", normalized_url)
            return None

        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            return CachedResponseEntry(
                policy=policy,
                normalized_url=normalized_url,
                cache_path=cache_path,
                payload=payload,
            )
        except Exception:
            logger.debug("CACHE MISS %s", normalized_url)
            return None

    def cache_key(self, method: str, url: str, *, params: dict[str, Any] | None = None) -> str | None:
        policy = _policy_for_request(method, url)
        if policy is None:
            return None
        return _normalized_url(url, params=params)

    def build_conditional_headers(
        self,
        entry: CachedResponseEntry,
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        if not entry.policy.allow_conditional_revalidation:
            return None

        merged = dict(headers or {})
        if_none_match_present = any(key.lower() == "if-none-match" for key in merged)
        if_modified_since_present = any(key.lower() == "if-modified-since" for key in merged)
        cached_headers = {
            str(key).lower(): str(value)
            for key, value in (entry.payload.get("headers") or {}).items()
        }
        if not if_none_match_present and cached_headers.get("etag"):
            merged["If-None-Match"] = cached_headers["etag"]
        if not if_modified_since_present and cached_headers.get("last-modified"):
            merged["If-Modified-Since"] = cached_headers["last-modified"]
        return merged if merged != dict(headers or {}) else None

    def revalidate(
        self,
        method: str,
        url: str,
        entry: CachedResponseEntry,
        response: httpx.Response,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        created_at = time.time()
        expires_at = None if entry.policy.ttl_seconds is None else created_at + entry.policy.ttl_seconds
        updated_headers = dict(entry.payload.get("headers") or {})
        updated_headers.update(dict(response.headers.items()))
        updated_payload = dict(entry.payload)
        updated_payload["headers"] = updated_headers
        updated_payload["created_at"] = created_at
        updated_payload["expires_at"] = expires_at

        tmp_path = entry.cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(updated_payload, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(entry.cache_path)

        return _response_from_payload(method, entry.normalized_url, updated_payload)

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
        cache_path = self._cache_path(policy, normalized_url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        response.read()
        created_at = time.time()
        expires_at = None if policy.ttl_seconds is None else created_at + policy.ttl_seconds
        payload = {
            "cache_key": _structured_cache_key(policy, normalized_url),
            "source": policy.source,
            "endpoint": policy.endpoint,
            "cik": policy.cik,
            "accession": policy.accession,
            "taxonomy": policy.taxonomy,
            "tag": policy.tag,
            "period": policy.period,
            "as_of": policy.as_of,
            "immutable": policy.immutable,
            "url": normalized_url,
            "status_code": response.status_code,
            "headers": dict(response.headers.items()),
            "created_at": created_at,
            "expires_at": expires_at,
            "content_b64": base64.b64encode(response.content).decode("ascii"),
        }
        cached_json = _cached_json_payload(policy, response)
        if cached_json is not None:
            payload["json_payload"] = cached_json

        tmp_path = cache_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        tmp_path.replace(cache_path)

    def _cache_path(self, policy: CachePolicy, normalized_url: str) -> Path:
        filename = _cache_filename(policy, normalized_url)
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

    def disk_usage(self) -> SecCacheDiskUsage:
        file_count = 0
        total_bytes = 0
        immutable_file_count = 0
        immutable_bytes = 0
        expiring_file_count = 0
        expiring_bytes = 0
        stale_file_count = 0
        stale_bytes = 0
        unreadable_file_count = 0
        now = time.time()

        for cache_path in self._root.glob("*.json"):
            try:
                size = cache_path.stat().st_size
            except OSError:
                unreadable_file_count += 1
                continue

            file_count += 1
            total_bytes += size
            try:
                metadata = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                unreadable_file_count += 1
                continue

            if metadata.get("immutable") is True:
                immutable_file_count += 1
                immutable_bytes += size
            else:
                expiring_file_count += 1
                expiring_bytes += size

            expires_at = metadata.get("expires_at")
            if expires_at is not None:
                try:
                    is_stale = now >= float(expires_at)
                except (TypeError, ValueError):
                    unreadable_file_count += 1
                    continue
                if is_stale:
                    stale_file_count += 1
                    stale_bytes += size

        return SecCacheDiskUsage(
            root=str(self._root),
            file_count=file_count,
            total_bytes=total_bytes,
            immutable_file_count=immutable_file_count,
            immutable_bytes=immutable_bytes,
            expiring_file_count=expiring_file_count,
            expiring_bytes=expiring_bytes,
            stale_file_count=stale_file_count,
            stale_bytes=stale_bytes,
            unreadable_file_count=unreadable_file_count,
        )


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

    if path == "/files/company_tickers.json":
        return CachePolicy(
            "company_tickers",
            None,
            None,
            float(settings.sec_ticker_cache_ttl_seconds),
            allow_conditional_revalidation=True,
        )

    submissions_match = re.search(r"/submissions/cik(\d{10})\.json$", path)
    if submissions_match:
        return CachePolicy("submissions", submissions_match.group(1), None, 24 * 60 * 60)

    submissions_history_match = re.search(r"/submissions/cik(\d{10})-submissions-\d+\.json$", path)
    if submissions_history_match:
        return CachePolicy("submissions_history", submissions_history_match.group(1), None, 7 * 24 * 60 * 60)

    companyfacts_match = re.search(r"/api/xbrl/companyfacts/cik(\d{10})\.json$", path)
    if companyfacts_match:
        return CachePolicy("companyfacts", companyfacts_match.group(1), None, 7 * 24 * 60 * 60)

    frames_match = re.search(r"/api/xbrl/frames/([^/]+)/([^/]+)/([^/]+)/([^/]+)\.json$", path)
    if frames_match:
        taxonomy = frames_match.group(1)
        tag = frames_match.group(2)
        period = frames_match.group(4)
        return CachePolicy(
            "frames",
            None,
            None,
            7 * 24 * 60 * 60,
            taxonomy=taxonomy,
            tag=tag,
            period=period,
        )

    filing_index_match = re.search(r"/archives/edgar/data/(\d+)/(\d+)/index\.json$", path)
    if filing_index_match:
        cik = filing_index_match.group(1).zfill(10)
        accession = filing_index_match.group(2)
        return CachePolicy("filing_index", cik, accession, None, immutable=True)

    archive_document_match = re.search(r"/archives/edgar/data/(\d+)/(\d+)/([^/]+\.(xml|xsd|html|htm|xhtml|txt))$", path)
    if archive_document_match:
        cik = archive_document_match.group(1).zfill(10)
        accession = archive_document_match.group(2)
        name = archive_document_match.group(3).lower()
        if "ownership" in name or "form4" in name or "f345" in name:
            return CachePolicy("form4_xml", cik, accession, None, immutable=True)
        if "13f" in name or "infotable" in name or "informationtable" in name:
            return CachePolicy("13f_xml", cik, accession, None, immutable=True)
        if name.endswith(".xml") or name.endswith(".xsd"):
            return CachePolicy("filing_xml", cik, accession, None, immutable=True)
        return CachePolicy("filing_document", cik, accession, None, immutable=True)

    return None


def _cache_filename(policy: CachePolicy, normalized_url: str) -> str:
    url_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]
    parts = [
        policy.source,
        policy.endpoint,
        policy.cik,
        policy.accession,
        policy.taxonomy,
        policy.tag,
        policy.period,
        policy.as_of,
        url_hash,
    ]
    return "_".join(_safe_key_part(part) for part in parts if part) + ".json"


def _safe_key_part(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9.-]+", "-", text)
    return text.strip("-") or "unknown"


def _structured_cache_key(policy: CachePolicy, normalized_url: str) -> str:
    parts = [
        policy.source,
        policy.endpoint,
        f"cik:{policy.cik}" if policy.cik else None,
        f"accession:{policy.accession}" if policy.accession else None,
        f"taxonomy:{policy.taxonomy}" if policy.taxonomy else None,
        f"tag:{policy.tag}" if policy.tag else None,
        f"period:{policy.period}" if policy.period else None,
        f"as_of:{policy.as_of}" if policy.as_of else None,
        f"url:{hashlib.sha256(normalized_url.encode('utf-8')).hexdigest()[:16]}",
    ]
    return "|".join(part for part in parts if part)


def _response_from_payload(method: str, normalized_url: str, payload: dict[str, Any]) -> httpx.Response:
    body = base64.b64decode(str(payload.get("content_b64", "")), validate=True)
    request = httpx.Request(method.upper(), normalized_url)
    headers = dict(payload.get("headers", {}))
    # Cached content is stored as decoded bytes, so transport/content encodings must be removed
    # to prevent httpx from attempting an extra decompression pass.
    for header_name in list(headers.keys()):
        if header_name.lower() in {"content-encoding", "content-length", "transfer-encoding"}:
            headers.pop(header_name, None)
    extensions: dict[str, Any] = {}
    cached_json = payload.get("json_payload")
    if cached_json is not None:
        extensions["cached_json_payload"] = cached_json
    return httpx.Response(
        int(payload.get("status_code", 200)),
        headers=headers,
        content=body,
        request=request,
        extensions=extensions,
    )


def _cached_json_payload(policy: CachePolicy, response: httpx.Response) -> Any | None:
    if policy.endpoint not in {"company_tickers", "submissions", "submissions_history", "companyfacts", "filing_index", "frames"}:
        return None
    content_type = str(response.headers.get("content-type") or "").lower()
    if "json" not in content_type:
        return None
    try:
        return response.json()
    except Exception:
        return None


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


def get_sec_cache_disk_usage() -> SecCacheDiskUsage:
    return sec_http_cache.disk_usage()


def log_sec_cache_disk_usage(*, level: int = logging.INFO) -> SecCacheDiskUsage:
    usage = get_sec_cache_disk_usage()
    logger.log(
        level,
        "SEC cache disk usage root=%s files=%s bytes=%s immutable_files=%s immutable_bytes=%s "
        "expiring_files=%s expiring_bytes=%s stale_files=%s stale_bytes=%s unreadable_files=%s",
        usage.root,
        usage.file_count,
        usage.total_bytes,
        usage.immutable_file_count,
        usage.immutable_bytes,
        usage.expiring_file_count,
        usage.expiring_bytes,
        usage.stale_file_count,
        usage.stale_bytes,
        usage.unreadable_file_count,
    )
    return usage


sec_http_cache = SecHttpCache()
