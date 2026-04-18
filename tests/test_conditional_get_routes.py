from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main_module
from app.main import RefreshState, app
from app.services.hot_cache import HotCacheLookup


def _snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def _assert_304_on_second_request(client: TestClient, url: str) -> None:
    first = client.get(url)
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag

    second = client.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304


def _request_with_query_string(query_string: str, *, path: str = "/api/companies/AAPL/models") -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


def _stub_financials_route(monkeypatch, *, ticker: str = "AAPL"):
    snapshot = _snapshot(ticker=ticker)
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker=ticker, job_id=None),
    )
    return snapshot


def _stub_models_route(monkeypatch, *, ticker: str = "AAPL"):
    snapshot = _snapshot(ticker=ticker)
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker=ticker, job_id=None),
    )
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module.ModelEngine, "compute_models", lambda *_args, **_kwargs: [SimpleNamespace(cached=True)])
    return snapshot


def test_search_route_supports_conditional_get(monkeypatch):
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_snapshot_by_cik", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "search_company_snapshots", lambda *_args, **_kwargs: [_snapshot()])
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/search?query=AAPL&refresh=false")


def test_search_route_uses_fresh_hot_cache_without_opening_session(monkeypatch):
    payload = {
        "query": "AAPL",
        "results": [
            {
                "ticker": "AAPL",
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sector": "Technology",
                "market_sector": "Technology",
                "market_industry": "Consumer Electronics",
                "oil_exposure_type": "non_oil",
                "oil_support_status": "unsupported",
                "oil_support_reasons": ["non_energy_classification"],
                "regulated_entity": None,
                "strict_official_mode": False,
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "last_checked_financials": datetime.now(timezone.utc).isoformat(),
                "last_checked_prices": None,
                "last_checked_insiders": None,
                "last_checked_institutional": None,
                "last_checked_filings": None,
                "earnings_last_checked": None,
                "cache_state": "fresh",
            }
        ],
        "refresh": {"triggered": False, "reason": "fresh", "ticker": "AAPL", "job_id": None},
    }

    async def _get_cached(*_args, **_kwargs):
        return HotCacheLookup(
            content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            etag='W/"cached-search-fresh"',
            last_modified=None,
            is_fresh=True,
        )

    def _unexpected_session_scope():
        raise AssertionError("search route should not open a DB session on fresh hot-cache hits")

    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _get_cached)
    monkeypatch.setattr(main_module, "_session_scope", _unexpected_session_scope)

    client = TestClient(app)
    response = client.get("/api/companies/search?query=AAPL&refresh=false")

    assert response.status_code == 200
    assert response.json()["results"][0]["ticker"] == "AAPL"


def test_search_route_uses_in_memory_cache_without_opening_session(monkeypatch):
    cached_response = main_module.CompanySearchResponse.model_validate(
        {
            "query": "AAPL",
            "results": [
                {
                    "ticker": "AAPL",
                    "cik": "0000320193",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "oil_exposure_type": "non_oil",
                    "oil_support_status": "unsupported",
                    "oil_support_reasons": ["non_energy_classification"],
                    "regulated_entity": None,
                    "strict_official_mode": False,
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                    "last_checked_financials": datetime.now(timezone.utc).isoformat(),
                    "last_checked_prices": None,
                    "last_checked_insiders": None,
                    "last_checked_institutional": None,
                    "last_checked_filings": None,
                    "earnings_last_checked": None,
                    "cache_state": "fresh",
                }
            ],
            "refresh": {"triggered": False, "reason": "fresh", "ticker": "AAPL", "job_id": None},
        }
    )

    async def _no_hot_cache(*_args, **_kwargs):
        return None

    async def _store_hot_cache(*_args, **_kwargs):
        return None

    def _unexpected_session_scope():
        raise AssertionError("search route should not open a DB session on in-memory cache hits")

    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _no_hot_cache)
    monkeypatch.setattr(main_module, "_get_cached_search_response", lambda *_args, **_kwargs: cached_response)
    monkeypatch.setattr(main_module, "_store_hot_cached_payload", _store_hot_cache)
    monkeypatch.setattr(main_module, "_session_scope", _unexpected_session_scope)

    client = TestClient(app)
    response = client.get("/api/companies/search?query=AAPL&refresh=false")

    assert response.status_code == 200
    assert response.json()["results"][0]["ticker"] == "AAPL"


def test_search_route_prioritizes_exact_ticker_and_skips_contains_fallback(monkeypatch):
    search_calls: list[bool] = []
    exact_snapshot = _snapshot("AAPL", "0000320193")

    def _search_company_snapshots(*_args, **kwargs):
        search_calls.append(kwargs["allow_contains_fallback"])
        return [_snapshot("AAPLW", "0000000001")]

    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: exact_snapshot)
    monkeypatch.setattr(main_module, "get_company_snapshot_by_cik", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "search_company_snapshots", _search_company_snapshots)

    client = TestClient(app)
    response = client.get("/api/companies/search?query=AAPL&refresh=false")

    assert response.status_code == 200
    assert response.json()["results"][0]["ticker"] == "AAPL"
    assert search_calls == [False]


def test_search_route_prioritizes_exact_cik_and_skips_contains_fallback(monkeypatch):
    search_calls: list[bool] = []
    exact_snapshot = _snapshot("AAPL", "0000320193")

    def _search_company_snapshots(*_args, **kwargs):
        search_calls.append(kwargs["allow_contains_fallback"])
        return []

    monkeypatch.setattr(main_module, "get_company_snapshot_by_cik", lambda *_args, **_kwargs: exact_snapshot)
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "search_company_snapshots", _search_company_snapshots)

    client = TestClient(app)
    response = client.get("/api/companies/search?query=320193&refresh=false")

    assert response.status_code == 200
    assert response.json()["results"][0]["ticker"] == "AAPL"
    assert search_calls == [False]


def test_company_overview_route_supports_conditional_get(monkeypatch):
    snapshot = _snapshot()

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_build_company_financials_response",
        lambda *_args, **_kwargs: main_module.CompanyFinancialsResponse(
            company=main_module._serialize_company(snapshot),
            financials=[],
            price_history=[],
            refresh=RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
            diagnostics=main_module._build_data_quality_diagnostics(),
            **main_module._empty_provenance_contract(),
        ),
    )
    monkeypatch.setattr(
        main_module,
        "_build_company_research_brief_response",
        lambda *_args, **_kwargs: main_module._empty_company_brief_response(
            refresh=RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
            as_of=None,
        ).model_copy(update={"company": main_module._serialize_company(snapshot)}),
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/overview")


def test_readyz_returns_ok_when_database_is_usable(monkeypatch):
    class _HealthySession:
        async def execute(self, _statement):
            return None

    class _HealthyScope:
        async def __aenter__(self):
            return _HealthySession()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(main_module, "_session_scope", lambda: _HealthyScope())

    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_503_when_database_is_unavailable(monkeypatch):
    class _BrokenSession:
        async def execute(self, _statement):
            raise RuntimeError("db unavailable")

    class _BrokenScope:
        async def __aenter__(self):
            return _BrokenSession()

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(main_module, "_session_scope", lambda: _BrokenScope())

    client = TestClient(app)
    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "database not ready"


def test_search_route_does_not_trigger_refresh_when_refresh_disabled_on_stale_hot_cache(monkeypatch):
    trigger_calls: list[str] = []

    payload = {
        "query": "O",
        "results": [
            {
                "ticker": "ON",
                "cik": "0001097864",
                "name": "ON SEMICONDUCTOR CORP",
                "sector": "Semiconductors & Related Devices",
                "market_sector": "Technology",
                "market_industry": "Semiconductors",
                "oil_exposure_type": "non_oil",
                "oil_support_status": "unsupported",
                "oil_support_reasons": ["non_energy_classification"],
                "regulated_entity": None,
                "strict_official_mode": False,
                "last_checked": datetime.now(timezone.utc).isoformat(),
                "last_checked_financials": datetime.now(timezone.utc).isoformat(),
                "last_checked_prices": None,
                "last_checked_insiders": None,
                "last_checked_institutional": None,
                "last_checked_filings": None,
                "earnings_last_checked": None,
                "cache_state": "stale",
            }
        ],
        "refresh": {"triggered": False, "reason": "stale", "ticker": "O", "job_id": None},
    }

    async def _get_cached(*_args, **_kwargs):
        return HotCacheLookup(
            content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            etag='W/"cached-search"',
            last_modified=None,
            is_fresh=False,
        )

    monkeypatch.setattr(
        main_module,
        "_get_hot_cached_payload",
        _get_cached,
    )
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda *_args, **_kwargs: trigger_calls.append("called") or RefreshState(triggered=True, reason="stale", ticker="O", job_id="job-1"),
    )

    client = TestClient(app)
    response = client.get("/api/companies/search?query=O&refresh=false")

    assert response.status_code == 200
    assert response.json()["refresh"] == {"triggered": False, "reason": "stale", "ticker": "O", "job_id": None}
    assert trigger_calls == []


def test_financials_route_supports_conditional_get(monkeypatch):
    _stub_financials_route(monkeypatch)
    financials_calls: list[str] = []
    monkeypatch.setattr(
        main_module,
        "_visible_financials_for_company",
        lambda *_args, **_kwargs: financials_calls.append("called") or [],
    )

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/financials")
    assert first.status_code == 200
    assert first.headers.get("cache-control") == "public, max-age=20, stale-while-revalidate=300"
    etag = first.headers.get("etag")
    assert etag

    second = client.get("/api/companies/AAPL/financials", headers={"If-None-Match": etag})
    assert second.status_code == 304
    assert second.content == b""
    assert second.headers.get("cache-control") == "public, max-age=20, stale-while-revalidate=300"
    assert financials_calls == ["called"]


def test_financials_route_rejects_duplicate_as_of_regardless_of_order(monkeypatch):
    _stub_financials_route(monkeypatch)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/financials?as_of=not-a-date&as_of=2024-01-01")
    second = client.get("/api/companies/AAPL/financials?as_of=2024-01-01&as_of=not-a-date")

    assert first.status_code == 400
    assert second.status_code == 400
    assert first.json()["detail"] == "as_of may only be provided once"
    assert second.json()["detail"] == "as_of may only be provided once"


def test_financials_route_clean_as_of_keeps_200_and_duplicate_as_of_does_not_share_etag(monkeypatch):
    _stub_financials_route(monkeypatch)

    client = TestClient(app)
    clean = client.get("/api/companies/AAPL/financials?as_of=2024-01-01")
    duplicate_invalid = client.get("/api/companies/AAPL/financials?as_of=not-a-date&as_of=2024-01-01")

    assert clean.status_code == 200
    assert clean.headers.get("etag")
    assert duplicate_invalid.status_code == 400
    assert duplicate_invalid.headers.get("etag") is None
    assert duplicate_invalid.headers.get("etag") != clean.headers.get("etag")


def test_financials_route_uses_hot_cache_metadata_for_304_without_opening_session(monkeypatch):
    async def _get_cached(*_args, **_kwargs):
        return HotCacheLookup(
            content=b'{"company":{"ticker":"AAPL"}}',
            etag='W/"financials-hot"',
            last_modified="Sun, 13 Apr 2026 00:00:00 GMT",
            is_fresh=True,
        )

    def _unexpected_session_scope():
        raise AssertionError("fresh financial hot-cache metadata should satisfy 304 checks without opening a DB session")

    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _get_cached)
    monkeypatch.setattr(main_module, "_session_scope", _unexpected_session_scope)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/financials", headers={"If-None-Match": 'W/"financials-hot"'})

    assert response.status_code == 304
    assert response.content == b""


def test_models_route_supports_conditional_get(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/models")


def test_company_route_etag_is_stable_for_reordered_query_params():
    last_refreshed_at = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    first_request = _request_with_query_string("expand=input_periods&model=dcf")
    second_request = _request_with_query_string("model=dcf&expand=input_periods")

    first_etag = main_module._build_company_cache_etag(
        first_request,
        scope_key="ticker:AAPL",
        last_refreshed_at=last_refreshed_at,
    )
    second_etag = main_module._build_company_cache_etag(
        second_request,
        scope_key="ticker:AAPL",
        last_refreshed_at=last_refreshed_at,
    )

    assert first_etag == second_etag


def test_company_route_etag_canonicalizes_repeated_non_singleton_query_params_deterministically():
    last_refreshed_at = datetime(2026, 4, 17, 12, 0, tzinfo=timezone.utc)
    first_request = _request_with_query_string("foo=summary&model=dcf&foo=input_periods")
    second_request = _request_with_query_string("model=dcf&foo=input_periods&foo=summary")

    first_etag = main_module._build_company_cache_etag(
        first_request,
        scope_key="ticker:AAPL",
        last_refreshed_at=last_refreshed_at,
    )
    second_etag = main_module._build_company_cache_etag(
        second_request,
        scope_key="ticker:AAPL",
        last_refreshed_at=last_refreshed_at,
    )

    assert first_etag == second_etag
    assert main_module._canonicalize_company_query_string(first_request) == "foo=input_periods&foo=summary&model=dcf"


def test_company_route_hot_cache_keys_use_latest_when_as_of_absent():
    request = _request_with_query_string("", path="/api/companies/AAPL/financials")

    assert main_module._company_route_hot_cache_keys(request) == ["financials:AAPL:asof=latest"]


def test_company_route_hot_cache_keys_bypass_invalid_as_of():
    latest_request = _request_with_query_string("", path="/api/companies/AAPL/financials")
    invalid_request = _request_with_query_string("as_of=not-a-date", path="/api/companies/AAPL/financials")

    assert main_module._company_route_hot_cache_keys(latest_request) == ["financials:AAPL:asof=latest"]
    assert main_module._company_route_hot_cache_keys(invalid_request) == []


def test_models_route_hot_cache_keys_reject_duplicate_singletons():
    clean_request = _request_with_query_string(
        "model=dcf&expand=input_periods&dupont_mode=annual",
        path="/api/companies/AAPL/models",
    )
    duplicate_expand_request = _request_with_query_string(
        "model=dcf&expand=bogus&expand=input_periods",
        path="/api/companies/AAPL/models",
    )
    duplicate_dupont_request = _request_with_query_string(
        "model=dcf&dupont_mode=bogus&dupont_mode=annual",
        path="/api/companies/AAPL/models",
    )

    assert main_module._company_route_hot_cache_keys(clean_request) == [
        "models:AAPL:models=dcf:dupont=annual:expand=input_periods:asof=latest"
    ]
    assert main_module._company_route_hot_cache_keys(duplicate_expand_request) == []
    assert main_module._company_route_hot_cache_keys(duplicate_dupont_request) == []


def test_models_route_conditional_get_matches_canonicalized_etag(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/models?expand=input_periods&model=dcf")
    assert first.status_code == 200
    etag = first.headers.get("etag")
    assert etag

    second = client.get(
        "/api/companies/AAPL/models?model=dcf&expand=input_periods",
        headers={"If-None-Match": etag},
    )

    assert second.status_code == 304
    assert second.content == b""


def test_models_route_rejects_duplicate_expand_regardless_of_order(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/models?expand=bogus&expand=input_periods")
    second = client.get("/api/companies/AAPL/models?expand=input_periods&expand=bogus")

    assert first.status_code == 400
    assert second.status_code == 400
    assert first.json()["detail"] == "expand may only be provided once"
    assert second.json()["detail"] == "expand may only be provided once"


def test_models_route_rejects_duplicate_dupont_mode_regardless_of_order(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/models?dupont_mode=bogus&dupont_mode=annual")
    second = client.get("/api/companies/AAPL/models?dupont_mode=annual&dupont_mode=bogus")

    assert first.status_code == 400
    assert second.status_code == 400
    assert first.json()["detail"] == "dupont_mode may only be provided once"
    assert second.json()["detail"] == "dupont_mode may only be provided once"


def test_models_route_clean_valid_query_keeps_200(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/models?model=dcf&expand=input_periods&dupont_mode=annual")

    assert response.status_code == 200
    assert response.headers.get("etag")


def test_models_route_duplicate_invalid_query_does_not_match_clean_etag(monkeypatch):
    _stub_models_route(monkeypatch)

    client = TestClient(app)
    clean = client.get("/api/companies/AAPL/models?model=dcf&expand=input_periods&dupont_mode=annual")
    assert clean.status_code == 200
    clean_etag = clean.headers.get("etag")
    assert clean_etag

    duplicate_expand = client.get(
        "/api/companies/AAPL/models?model=dcf&expand=bogus&expand=input_periods&dupont_mode=annual",
        headers={"If-None-Match": clean_etag},
    )
    duplicate_dupont = client.get(
        "/api/companies/AAPL/models?model=dcf&expand=input_periods&dupont_mode=bogus&dupont_mode=annual",
        headers={"If-None-Match": clean_etag},
    )

    assert duplicate_expand.status_code == 400
    assert duplicate_dupont.status_code == 400
    assert duplicate_expand.headers.get("etag") is None
    assert duplicate_dupont.headers.get("etag") is None


def test_models_route_duplicate_invalid_query_skips_hot_cache_lookup(monkeypatch):
    hot_cache_keys: list[str] = []

    async def _get_cached(cache_key, *_args, **_kwargs):
        hot_cache_keys.append(cache_key)
        return HotCacheLookup(
            content=b'{"company":{"ticker":"AAPL"}}',
            etag='W/"models-hot"',
            last_modified="Sun, 13 Apr 2026 00:00:00 GMT",
            is_fresh=True,
        )

    def _unexpected_session_scope():
        raise AssertionError("duplicate singleton params should be rejected before cache metadata opens a DB session")

    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _get_cached)
    monkeypatch.setattr(main_module, "_session_scope", _unexpected_session_scope)

    client = TestClient(app)
    response = client.get(
        "/api/companies/AAPL/models?model=dcf&expand=bogus&expand=input_periods",
        headers={"If-None-Match": 'W/"models-hot"'},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "expand may only be provided once"
    assert hot_cache_keys == []
    assert response.headers.get("etag") is None


def test_financials_route_invalid_as_of_does_not_match_latest_hot_cache_etag(monkeypatch):
    hot_cache_keys: list[str] = []

    async def _get_cached(cache_key, *_args, **_kwargs):
        hot_cache_keys.append(cache_key)
        return HotCacheLookup(
            content=b'{"company":{"ticker":"AAPL"}}',
            etag='W/"financials-hot"',
            last_modified="Sun, 13 Apr 2026 00:00:00 GMT",
            is_fresh=True,
        )

    def _unexpected_session_scope():
        raise AssertionError("invalid as_of should be rejected before cache metadata opens a DB session")

    monkeypatch.setattr(main_module, "_get_hot_cached_payload", _get_cached)
    monkeypatch.setattr(main_module, "_session_scope", _unexpected_session_scope)

    client = TestClient(app)
    response = client.get(
        "/api/companies/AAPL/financials?as_of=not-a-date",
        headers={"If-None-Match": 'W/"financials-hot"'},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "as_of must be an ISO-8601 date or timestamp"
    assert hot_cache_keys == []
    assert response.headers.get("etag") is None


def test_model_evaluation_route_supports_conditional_get(monkeypatch):
    completed_at = datetime.now(timezone.utc)
    payload = {
        "id": 7,
        "suite_key": "historical_fixture_v1",
        "candidate_label": "fixture_baseline_v1",
        "baseline_label": "fixture_baseline_v1",
        "status": "completed",
        "completed_at": completed_at,
        "configuration": {"horizon_days": 420},
        "summary": {"provenance_mode": "synthetic_fixture", "latest_as_of": "2025-02-15"},
        "models": [
            {
                "model_name": "dcf",
                "sample_count": 8,
                "calibration": 0.75,
                "stability": 0.08,
                "mean_absolute_error": 0.11,
                "root_mean_square_error": 0.13,
                "mean_signed_error": 0.02,
                "status": "ok",
                "delta": {
                    "calibration": 0,
                    "stability": 0,
                    "mean_absolute_error": 0,
                    "root_mean_square_error": 0,
                    "mean_signed_error": 0,
                    "sample_count": 0,
                },
            }
        ],
        "deltas_present": False,
    }
    monkeypatch.setattr(main_module, "get_latest_model_evaluation_run", lambda *_args, **_kwargs: SimpleNamespace(created_at=completed_at, completed_at=completed_at))
    monkeypatch.setattr(main_module, "serialize_model_evaluation_run", lambda *_args, **_kwargs: payload)

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/model-evaluations/latest")


def test_peers_route_supports_conditional_get(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "build_peer_comparison",
        lambda *_args, **_kwargs: {
            "company": snapshot,
            "peer_basis": "Technology peers",
            "available_companies": [],
            "selected_tickers": [],
            "peers": [],
            "notes": {},
        },
    )

    client = TestClient(app)
    _assert_304_on_second_request(client, "/api/companies/AAPL/peers")


def test_compare_route_sets_public_cache_headers(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "get_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: {"AAPL": snapshot})
    monkeypatch.setattr(
        main_module,
        "_build_company_compare_item",
        lambda *_args, **_kwargs: main_module.CompanyCompareItemPayload.model_validate(
            {
                "ticker": "AAPL",
                "financials": {
                    "company": {
                        "ticker": "AAPL",
                        "cik": "0000320193",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "market_sector": "Technology",
                        "market_industry": "Consumer Electronics",
                        "last_checked": snapshot.last_checked.isoformat(),
                        "cache_state": "fresh",
                    },
                    "financials": [],
                    "price_history": [],
                    "refresh": {"triggered": False, "reason": "fresh", "ticker": "AAPL", "job_id": None},
                    "diagnostics": {},
                    "provenance": [],
                    "source_mix": {},
                    "confidence_flags": [],
                    "as_of": None,
                    "last_refreshed_at": snapshot.last_checked.isoformat(),
                },
                "metrics_summary": {
                    "company": {
                        "ticker": "AAPL",
                        "cik": "0000320193",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "market_sector": "Technology",
                        "market_industry": "Consumer Electronics",
                        "last_checked": snapshot.last_checked.isoformat(),
                        "cache_state": "fresh",
                    },
                    "period_type": "annual",
                    "latest_period_end": None,
                    "metrics": [],
                    "last_metrics_check": snapshot.last_checked.isoformat(),
                    "last_financials_check": snapshot.last_checked.isoformat(),
                    "last_price_check": snapshot.last_checked.isoformat(),
                    "staleness_reason": None,
                    "refresh": {"triggered": False, "reason": "fresh", "ticker": "AAPL", "job_id": None},
                    "diagnostics": {},
                    "provenance": [],
                    "source_mix": {},
                    "confidence_flags": [],
                    "as_of": None,
                    "last_refreshed_at": snapshot.last_checked.isoformat(),
                },
                "models": {
                    "company": {
                        "ticker": "AAPL",
                        "cik": "0000320193",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "market_sector": "Technology",
                        "market_industry": "Consumer Electronics",
                        "last_checked": snapshot.last_checked.isoformat(),
                        "cache_state": "fresh",
                    },
                    "requested_models": [],
                    "models": [],
                    "refresh": {"triggered": False, "reason": "fresh", "ticker": "AAPL", "job_id": None},
                    "diagnostics": {},
                    "provenance": [],
                    "source_mix": {},
                    "confidence_flags": [],
                    "as_of": None,
                    "last_refreshed_at": snapshot.last_checked.isoformat(),
                },
            }
        ),
    )

    client = TestClient(app)
    response = client.get("/api/companies/compare?tickers=AAPL")

    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=20, stale-while-revalidate=300"
    assert response.headers.get("etag")
