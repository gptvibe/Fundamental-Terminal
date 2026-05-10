from __future__ import annotations

from app.api.handlers._common import main_bound
from app.api.handlers._shared import *  # noqa: F401,F403
from app.contracts.common import ResponseMetadataPayload
from app.api.schemas.filings import CompanyExhibitsResponse, CompanyFilingRiskSignalsResponse, ExhibitPayload, FilingRiskSignalPayload, FilingRiskSignalSummaryPayload
from app.services.sec.exhibits import extract_exhibits_from_index


def _filings_response_metadata(*, refresh: RefreshState, source: str) -> ResponseMetadataPayload:
    if refresh.reason == "fresh" and not refresh.triggered:
        freshness = "fresh"
    elif refresh.reason == "missing":
        freshness = "missing"
    else:
        freshness = "stale"
    return ResponseMetadataPayload(
        freshness=freshness,
        source=source,
        isStale=freshness != "fresh",
        refreshQueued=bool(refresh.triggered),
        jobId=refresh.job_id,
    )


@main_bound
def company_filings(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        refresh = _trigger_refresh(normalized_ticker, reason="missing")
        return CompanyFilingsResponse(
            company=None,
            filings=[],
            timeline_source="sec_submissions",
            refresh=refresh,
            response_metadata=_filings_response_metadata(refresh=refresh, source="none"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
            error=None,
        )

    refresh = _refresh_for_snapshot(snapshot)

    cached_filings = _load_filings_from_cache(snapshot.company.cik)
    if cached_filings is not None:
        return CompanyFilingsResponse(
            company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(cached_filings)),
            filings=cached_filings,
            timeline_source="sec_submissions",
            refresh=refresh,
            response_metadata=_filings_response_metadata(refresh=refresh, source="sec_submissions_cache"),
            diagnostics=_diagnostics_for_filings_timeline(cached_filings, refresh, "sec_submissions"),
            error=None,
        )

    fallback_filings = _serialize_cached_statement_filings(get_company_financials(session, snapshot.company.id))
    stale_refresh = refresh if refresh.triggered else _trigger_refresh(snapshot.company.ticker, reason="missing")
    return CompanyFilingsResponse(
        company=_serialize_company(snapshot, last_checked_filings=_filings_cache_last_checked(fallback_filings)),
        filings=fallback_filings,
        timeline_source="cached_financials",
        refresh=stale_refresh,
        response_metadata=_filings_response_metadata(refresh=stale_refresh, source="cached_financials"),
        diagnostics=_diagnostics_for_filings_timeline(fallback_filings, stale_refresh, "cached_financials"),
        error=(
            "Latest SEC filing timeline is not cached yet. Returning cached filing history while a refresh is queued."
            if fallback_filings
            else "No cached filing timeline is available yet. A background refresh has been queued."
        ),
    )


@main_bound
def company_filing_risk_signals(
    ticker: str,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db_session),
) -> CompanyFilingRiskSignalsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        return CompanyFilingRiskSignalsResponse(
            company=None,
            summary=FilingRiskSignalSummaryPayload(total_signals=0, high_severity_count=0, medium_severity_count=0, latest_filed_date=None),
            signals=[],
            refresh=_trigger_refresh(normalized_ticker, reason="missing"),
            diagnostics=_build_data_quality_diagnostics(stale_flags=["company_missing"]),
        )

    signals_last_checked, signals_cache_state = get_company_filing_risk_signals_cache_status(session, snapshot.company)
    signals = get_company_filing_risk_signals(session, snapshot.company.id)
    refresh = (
        _trigger_refresh(snapshot.company.ticker, reason=signals_cache_state)
        if signals_cache_state in {"missing", "stale"}
        else RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    )
    serialized = [_serialize_filing_risk_signal(signal) for signal in signals]
    return CompanyFilingRiskSignalsResponse(
        company=_serialize_company(snapshot, last_checked=signals_last_checked),
        summary=_build_filing_risk_signal_summary(serialized),
        signals=serialized,
        refresh=refresh,
        diagnostics=_build_data_quality_diagnostics(
            coverage_ratio=1.0 if serialized else 0.0,
            stale_flags=[] if serialized else ["filing_risk_signals_missing"],
        ),
    )


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


def _serialize_filing_risk_signal(signal: Any) -> FilingRiskSignalPayload:
    return FilingRiskSignalPayload(
        ticker=str(signal.ticker),
        cik=str(signal.cik),
        accession_number=str(signal.accession_number),
        form_type=str(signal.form_type),
        filed_date=getattr(signal, "filed_date", None),
        signal_category=str(signal.signal_category),
        matched_phrase=str(signal.matched_phrase),
        context_snippet=str(signal.context_snippet),
        confidence=str(signal.confidence),
        severity=str(signal.severity),
        source=str(signal.source),
        provenance=str(signal.provenance),
        last_updated=getattr(signal, "last_updated", None),
        last_checked=getattr(signal, "last_checked", None),
    )


def _build_filing_risk_signal_summary(signals: list[FilingRiskSignalPayload]) -> FilingRiskSignalSummaryPayload:
    return FilingRiskSignalSummaryPayload(
        total_signals=len(signals),
        high_severity_count=sum(1 for signal in signals if signal.severity == "high"),
        medium_severity_count=sum(1 for signal in signals if signal.severity == "medium"),
        latest_filed_date=max((signal.filed_date for signal in signals if signal.filed_date is not None), default=None),
    )


__all__ = ["company_exhibits", "company_filing_risk_signals", "company_filing_view", "company_filings", "filings_timeline", "search_filings"]


# ---------------------------------------------------------------------------
# Exhibits
# ---------------------------------------------------------------------------

_EXHIBIT_MAX_FILINGS = 40  # cap how many filings we scan per request


@main_bound
def company_exhibits(
    ticker: str,
    exhibit_type: str | None = Query(default=None, description="Filter by exhibit type prefix, e.g. EX-99.1"),
    filing_type: str | None = Query(default=None, description="Filter by filing form type, e.g. 8-K"),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> CompanyExhibitsResponse:
    normalized_ticker = _normalize_ticker(ticker)
    snapshot = _resolve_cached_company_snapshot(session, normalized_ticker)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown ticker '{normalized_ticker}'")

    cik = snapshot.company.cik
    client = EdgarClient()
    log = logging.getLogger(__name__)
    try:
        submissions = client.get_submissions(cik)
        filing_index = client.build_filing_index(submissions)

        # Collect candidate filings, optionally filtered by filing_type.
        candidates = sorted(
            filing_index.values(),
            key=lambda m: (getattr(m, "filing_date", None) or DateType.min),
            reverse=True,
        )
        if filing_type:
            normalized_filing_type = filing_type.strip().upper()
            candidates = [m for m in candidates if (getattr(m, "form", "") or "").upper() == normalized_filing_type]

        # Fetch exhibit lists for the most-recent candidate filings.
        all_exhibits: list[ExhibitPayload] = []
        scanned = 0
        for metadata in candidates:
            if scanned >= _EXHIBIT_MAX_FILINGS:
                break
            accession_number = str(getattr(metadata, "accession_number", "") or "")
            if not accession_number:
                continue
            form = str(getattr(metadata, "form", "") or "")
            filing_date = getattr(metadata, "filing_date", None)
            try:
                directory_index = client.get_filing_directory_index(cik, accession_number)
            except Exception:
                log.debug("Could not fetch directory index for %s / %s", ticker, accession_number)
                scanned += 1
                continue

            raw = extract_exhibits_from_index(cik, accession_number, form, filing_date, directory_index)
            accession_compact = accession_number.replace("-", "")
            numeric_cik = str(int(cik))
            filing_index_url = (
                f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/index.html"
            )
            for ex in raw:
                if exhibit_type:
                    normalized_ex_type = exhibit_type.strip().upper()
                    if not (ex.exhibit_number == normalized_ex_type or ex.exhibit_number.startswith(normalized_ex_type)):
                        continue
                all_exhibits.append(
                    ExhibitPayload(
                        exhibit_number=ex.exhibit_number,
                        description=ex.description,
                        document=ex.document,
                        accession_number=ex.accession_number,
                        filing_type=ex.filing_type,
                        filing_date=ex.filing_date,
                        tag=ex.tag,
                        tag_label=ex.tag_label,
                        source_url=ex.source_url,
                        filing_index_url=filing_index_url,
                    )
                )
            scanned += 1

        all_exhibits = all_exhibits[:limit]
        return CompanyExhibitsResponse(
            company=_serialize_company(snapshot),
            exhibits=all_exhibits,
            total=len(all_exhibits),
            provenance=["SEC EDGAR filing directory index (official)"],
            source="sec_edgar",
            error=None,
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("Unable to load exhibits for '%s'", normalized_ticker)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Unable to load exhibits")
