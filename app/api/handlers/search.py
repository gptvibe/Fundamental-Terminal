from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
async def search_companies(
    request: Request,
    http_response: Response,
    background_tasks: BackgroundTasks,
    query: str | None = Query(default=None, min_length=1),
    ticker: str | None = Query(default=None, min_length=1),
    refresh: bool = Query(default=True),
) -> CompanySearchResponse:
    raw_query = query if query is not None else ticker
    if raw_query is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="query is required")

    normalized_query = _normalize_search_query(raw_query)
    hot_key = f"search:{normalized_query}:refresh={int(refresh)}"
    hot_tags = _build_hot_cache_tags(
        ticker=_normalize_ticker(normalized_query) if _looks_like_ticker(normalized_query) else None,
        datasets=("financials",),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["search"],),
    )
    cached_hot = await _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        if cached_hot.is_fresh:
            return _hot_cache_json_response(request, http_response, cached_hot)

        payload = _decode_hot_cache_payload(cached_hot)
        cached_response = CompanySearchResponse.model_validate(payload)
        if refresh and _looks_like_ticker(normalized_query):
            stale_refresh = _trigger_refresh(_normalize_ticker(normalized_query), reason="stale")
            cached_response = cached_response.model_copy(update={"refresh": stale_refresh})

        not_modified = _apply_conditional_headers(
            request,
            http_response,
            cached_response,
            last_modified=max(
                (item.last_checked for item in cached_response.results if item.last_checked is not None),
                default=None,
            ),
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return cached_response

    if not refresh:
        cached_response = _get_cached_search_response(normalized_query)
        if cached_response is not None:
            not_modified = _apply_conditional_headers(
                request,
                http_response,
                cached_response,
                last_modified=max(
                    (item.last_checked for item in cached_response.results if item.last_checked is not None),
                    default=None,
                ),
            )
            if not_modified is not None:
                return not_modified  # type: ignore[return-value]
            return cached_response

    async with _session_scope() as session:
        def build_search_payload(sync_session: Session) -> CompanySearchResponse:
            snapshots, exact_match = _resolve_search_snapshots(sync_session, normalized_query)
            normalized_ticker = _normalize_ticker(normalized_query)

            refresh_state = RefreshState()
            if not refresh:
                if exact_match is None:
                    refresh_state = RefreshState(
                        triggered=False,
                        reason="none",
                        ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None,
                        job_id=None,
                    )
                elif exact_match.cache_state in {"missing", "stale"}:
                    refresh_state = RefreshState(
                        triggered=False,
                        reason=exact_match.cache_state,
                        ticker=exact_match.company.ticker,
                        job_id=None,
                    )
                else:
                    refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)
            elif exact_match is None:
                if not snapshots and _looks_like_ticker(normalized_query):
                    refresh_state = _trigger_refresh(normalized_ticker, reason="missing")
                else:
                    refresh_state = RefreshState(
                        triggered=False,
                        reason="none",
                        ticker=normalized_ticker if _looks_like_ticker(normalized_query) else None,
                        job_id=None,
                    )
            elif exact_match.cache_state in {"missing", "stale"}:
                refresh_state = _trigger_refresh(exact_match.company.ticker, reason=exact_match.cache_state)
            else:
                refresh_state = RefreshState(triggered=False, reason="fresh", ticker=exact_match.company.ticker, job_id=None)

            payload = CompanySearchResponse(
                query=normalized_query,
                results=[_serialize_company(snapshot) for snapshot in snapshots],
                refresh=refresh_state,
            )
            return payload

        payload = await _run_with_session_binding(session, build_search_payload)
        _store_cached_search_response(normalized_query, payload)
        await _store_hot_cached_payload(hot_key, payload, tags=hot_tags)
        not_modified = _apply_conditional_headers(
            request,
            http_response,
            payload,
            last_modified=max((item.last_checked for item in payload.results if item.last_checked is not None), default=None),
        )
        if not_modified is not None:
            return not_modified  # type: ignore[return-value]
        return payload


@main_bound
async def resolve_company_identifier(query: str = Query(..., min_length=1)) -> CompanyResolutionResponse:
    normalized_query = _normalize_search_query(query)
    hot_key = f"resolve:{normalized_query}"
    hot_tags = _build_hot_cache_tags(
        ticker=_normalize_ticker(normalized_query) if _looks_like_ticker(normalized_query) else None,
        datasets=("financials",),
        schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["resolve"],),
    )
    cached_hot = await _get_hot_cached_payload(hot_key)
    if cached_hot is not None:
        return CompanyResolutionResponse.model_validate(_decode_hot_cache_payload(cached_hot))

    client = EdgarClient()
    try:
        identity = client.resolve_company(normalized_query)
    except ValueError:
        payload = CompanyResolutionResponse(query=normalized_query, resolved=False, error="not_found")
        await _store_hot_cached_payload(hot_key, payload, tags=hot_tags)
        return payload
    except Exception:
        logging.getLogger(__name__).exception("SEC company resolution failed for '%s'", normalized_query)
        return CompanyResolutionResponse(query=normalized_query, resolved=False, error="lookup_failed")
    finally:
        client.close()

    async with _session_scope() as session:
        canonical_ticker = await _run_with_session_binding(
            session,
            lambda sync_session: _resolve_canonical_ticker(sync_session, identity),
        )

    payload = CompanyResolutionResponse(
        query=normalized_query,
        resolved=True,
        ticker=canonical_ticker or identity.ticker,
        name=identity.name,
        error=None,
    )
    if payload.ticker:
        hot_tags = _build_hot_cache_tags(
            ticker=payload.ticker,
            datasets=("financials",),
            schema_versions=(HOT_CACHE_SCHEMA_VERSIONS["resolve"],),
        )
    await _store_hot_cached_payload(hot_key, payload, tags=hot_tags)
    return payload


__all__ = ["resolve_company_identifier", "search_companies"]

