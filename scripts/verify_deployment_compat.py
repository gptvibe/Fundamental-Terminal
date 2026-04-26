from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class JsonCheck:
    label: str
    url: str
    required_keys: tuple[str, ...]
    nested_required_keys: dict[str, tuple[str, ...]]


def _http_get(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> tuple[int, bytes, str | None, dict[str, str]]:
    request = Request(url=url, method="GET", headers=headers or {})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type")
            return int(response.status), body, content_type, dict(response.headers.items())
    except HTTPError as exc:
        return int(exc.code), exc.read(), exc.headers.get("Content-Type"), dict(exc.headers.items())


def _load_json(url: str, *, timeout: float, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    status, body, _content_type, _headers = _http_get(url, timeout=timeout, headers=headers)
    payload = json.loads(body.decode("utf-8"))
    return status, payload


def _wait_for_json(url: str, *, timeout: float, headers: dict[str, str] | None, ready: callable[[Any], bool]) -> None:
    deadline = time.time() + timeout
    last_error: str | None = None
    while time.time() < deadline:
        try:
            status, payload = _load_json(url, timeout=min(15.0, timeout), headers=headers)
            if status == 200 and ready(payload):
                return
            last_error = f"unexpected response {status}: {payload!r}"
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_error}")


def _wait_for_frontend(url: str, *, timeout: float, headers: dict[str, str] | None) -> None:
    deadline = time.time() + timeout
    last_error: str | None = None
    while time.time() < deadline:
        try:
            status, body, content_type, _response_headers = _http_get(url, timeout=min(15.0, timeout), headers=headers)
            if status == 200 and body and (content_type or "").startswith("text/html"):
                return
            last_error = f"unexpected response {status} content-type={content_type!r}"
        except (URLError, OSError) as exc:
            last_error = str(exc)
        time.sleep(2.0)
    raise RuntimeError(f"Timed out waiting for {url}. Last error: {last_error}")


def _assert_keys(label: str, payload: Any, required_keys: tuple[str, ...], nested_required_keys: dict[str, tuple[str, ...]]) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} did not return a JSON object")

    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise RuntimeError(f"{label} missing top-level keys: {', '.join(missing)}")

    for key, nested_keys in nested_required_keys.items():
        nested_payload = payload.get(key)
        if not isinstance(nested_payload, dict):
            raise RuntimeError(f"{label} expected {key!r} to be an object")
        nested_missing = [nested_key for nested_key in nested_keys if nested_key not in nested_payload]
        if nested_missing:
            raise RuntimeError(f"{label} missing nested keys under {key!r}: {', '.join(nested_missing)}")


def _parse_headers(raw_headers: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_header in raw_headers:
        separator = ":" if ":" in raw_header else "="
        name, value = raw_header.split(separator, 1)
        normalized_name = name.strip()
        normalized_value = value.strip()
        if not normalized_name or not normalized_value:
            raise RuntimeError(f"Invalid header override: {raw_header!r}")
        parsed[normalized_name] = normalized_value
    return parsed


def _assert_security_headers(label: str, headers: dict[str, str], required_names: tuple[str, ...]) -> None:
    normalized_headers = {name.lower(): value for name, value in headers.items()}
    missing = [name for name in required_names if not normalized_headers.get(name.lower())]
    if missing:
        raise RuntimeError(f"{label} missing security headers: {', '.join(missing)}")


def _assert_health_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise RuntimeError("/health did not return an object")
    components = payload.get("components")
    if not isinstance(components, dict):
        raise RuntimeError("/health did not include components")

    for component_name in ("api", "db", "redis", "worker", "sec_upstream"):
        if component_name not in components:
            raise RuntimeError(f"/health missing component {component_name!r}")

    db_status = components["db"].get("status")
    redis_status = components["redis"].get("status")
    worker_status = components["worker"].get("status")
    if db_status != "ok":
        raise RuntimeError(f"database health is not ok: {db_status!r}")
    if redis_status not in {"ok", "degraded"}:
        raise RuntimeError(f"redis health is not acceptable: {redis_status!r}")
    if worker_status not in {"ok", "idle"}:
        raise RuntimeError(f"worker health is not acceptable: {worker_status!r}")


def _health_payload_ready(payload: Any) -> bool:
    try:
        _assert_health_payload(payload)
    except RuntimeError:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deployed frontend/backend image compatibility")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--frontend-url", default="http://127.0.0.1:3000", help="Frontend base URL")
    parser.add_argument("--ticker", default="AAPL", help="Ticker symbol used for compatibility probes")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds")
    parser.add_argument("--wait-timeout", type=float, default=180.0, help="Startup wait timeout in seconds")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend HTML reachability check")
    parser.add_argument("--header", action="append", default=[], help="Optional request header override in Name:Value form")
    args = parser.parse_args()

    backend_url = args.backend_url.rstrip("/")
    frontend_url = args.frontend_url.rstrip("/")
    ticker = args.ticker.upper().strip()
    headers = _parse_headers(list(args.header))

    _wait_for_json(
        f"{backend_url}/health",
        timeout=args.wait_timeout,
        headers=headers,
        ready=_health_payload_ready,
    )

    if not args.skip_frontend:
        _wait_for_frontend(f"{frontend_url}/company/{ticker}", timeout=args.wait_timeout, headers=headers)

    health_status, health_payload = _load_json(f"{backend_url}/health", timeout=args.timeout, headers=headers)
    if health_status != 200:
        raise RuntimeError(f"/health returned HTTP {health_status}")
    _assert_health_payload(health_payload)

    backend_health_status, _backend_health_body, _backend_health_content_type, backend_health_headers = _http_get(
        f"{backend_url}/health",
        timeout=args.timeout,
        headers=headers,
    )
    if backend_health_status != 200:
        raise RuntimeError(f"/health headers probe returned HTTP {backend_health_status}")
    _assert_security_headers(
        "backend /health",
        backend_health_headers,
        ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy"),
    )

    checks = [
        JsonCheck(
            label="company overview",
            url=f"{backend_url}/api/companies/{ticker}/overview",
            required_keys=("company", "financials", "brief"),
            nested_required_keys={"financials": ("company", "financials", "price_history", "refresh")},
        ),
        JsonCheck(
            label="workspace bootstrap",
            url=(
                f"{backend_url}/api/companies/{ticker}/workspace-bootstrap?"
                + urlencode(
                    {
                        "include_overview_brief": "true",
                        "include_earnings_summary": "true",
                        "include_insiders": "true",
                        "include_institutional": "true",
                    }
                )
            ),
            required_keys=(
                "company",
                "financials",
                "brief",
                "earnings_summary",
                "insider_trades",
                "institutional_holdings",
                "errors",
            ),
            nested_required_keys={"financials": ("company", "financials", "price_history", "refresh"), "errors": ()},
        ),
        JsonCheck(
            label="research brief",
            url=f"{backend_url}/api/companies/{ticker}/brief",
            required_keys=(
                "company",
                "refresh",
                "build_state",
                "build_status",
                "snapshot",
                "what_changed",
                "business_quality",
                "capital_and_risk",
                "valuation",
                "monitor",
            ),
            nested_required_keys={"refresh": ("job_id", "triggered", "reason", "ticker")},
        ),
    ]

    for check in checks:
        status, payload = _load_json(check.url, timeout=args.timeout, headers=headers)
        if status != 200:
            raise RuntimeError(f"{check.label} returned HTTP {status}")
        _assert_keys(check.label, payload, check.required_keys, check.nested_required_keys)

    if not args.skip_frontend:
        status, _body, content_type, frontend_headers = _http_get(f"{frontend_url}/company/{ticker}", timeout=args.timeout, headers=headers)
        if status != 200:
            raise RuntimeError(f"frontend company page returned HTTP {status}")
        if not (content_type or "").startswith("text/html"):
            raise RuntimeError(f"frontend company page returned unexpected content type {content_type!r}")
        _assert_security_headers(
            "frontend company page",
            frontend_headers,
            ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Strict-Transport-Security"),
        )

    print(
        json.dumps(
            {
                "backend_url": backend_url,
                "frontend_url": None if args.skip_frontend else frontend_url,
                "ticker": ticker,
                "status": "ok",
                "health": health_payload,
                "verified_routes": [check.url for check in checks],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
