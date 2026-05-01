from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403


@main_bound
def company_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingsResponse(
            company=None,
            filings=[],
            timeline_source="sec_submissions",
            refresh=_trigger_refresh(background_tasks, normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(background_tasks, snapshot)

    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    if cached_filings is not None:
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(cached_filings)),
            filings=cached_filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            diagnostics=_diagnostics_for_filings_timeline(cached_filings, refresh, "sec_submissions"),
            error=None,
        )

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        _store_filings_in_cache(snapshot.company.cik, filings)
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(filings)),
            filings=filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            diagnostics=_diagnostics_for_filings_timeline(filings, refresh, "sec_submissions"),
            error=None,
        )
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing timeline for '%s'", snapshot.company.ticker)
        _evict_filings_cache(snapshot.company.cik)
        fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(fallback_filings)),
            filings=fallback_filings,
            timeline_source="cached_financials",
            refresh=refresh,
            diagnostics=_diagnostics_for_filings_timeline(fallback_filings, refresh, "cached_financials"),
            error=(
                "SEC submissions are temporarily unavailable. Showing cached annual and quarterly filings only."
                if fallback_filings
                else "SEC submissions are temporarily unavailable. Try refreshing again shortly."
            ),
        )
    finally:
        client.close()


@main_bound
def filings_timeline(
    ticker: str,
    session: Session = Depends(get_db_session),
) -> list[FilingTimelineItemPayload]:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    client = EdgarClient()
    try:
        submissions = client.get_submissions(snapshot.company.cik)
        filing_index = client.build_filing_index(submissions)
        filings = _serialize_recent_filings(snapshot.company.cik, filing_index)
        timeline: list[FilingTimelineItemPayload] = []
        for filing in filings:
            timeline.append(
                FilingTimelineItemPayload(
                    date=filing.filing_date or filing.report_date,
                    form=filing.form,
                    description=_filing_timeline_description(filing),
                    accession=filing.accession_number,
                )
            )
        return timeline
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load normalized filing timeline for '%s'", snapshot.company.ticker)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load filings")
    finally:
        client.close()


@main_bound
def search_filings(
    q: str = Query(..., min_length=2, max_length=120),
) -> list[FilingSearchResultPayload]:
    client = EdgarClient()
    try:
        response = client._request("GET", settings.sec_search_base_url, params={"q": q})
        payload = response.json()
        hits = ((payload or {}).get("hits") or {}).get("hits") or []
        results: list[FilingSearchResultPayload] = []
        for item in hits:
            parsed = _serialize_search_filing_hit(item)
            if parsed is not None:
                results.append(parsed)
        return results
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to search SEC filings for query '%s'", q)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to search filings")
    finally:
        client.close()


@main_bound
def company_filing_view(
    ticker: str,
    source_url: str = Query(..., min_length=1),
    session: Session = Depends(get_db_session),
) -> HTMLResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown ticker")

    normalized_source_url = source_url.strip()
    if not _is_allowed_sec_embed_url(normalized_source_url):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported filing URL")

    parsed = urlparse(normalized_source_url)
    if parsed.netloc == "data.sec.gov" and parsed.path.endswith(".json"):
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url))

    client = EdgarClient()
    try:
        payload, content_type = _fetch_sec_document(client, normalized_source_url)
        return HTMLResponse(_build_embedded_filing_html(payload, normalized_source_url, content_type))
    except HTTPException:
        raise
    except Exception:
        logging.getLogger(__name__).exception("Unable to load SEC filing document for '%s'", normalized_source_url)
        return HTMLResponse(_render_unavailable_filing_view(normalized_source_url), status_code=status.HTTP_502_BAD_GATEWAY)
    finally:
        client.close()


__all__ = ["company_filing_view", "company_filings", "filings_timeline", "search_filings"]
