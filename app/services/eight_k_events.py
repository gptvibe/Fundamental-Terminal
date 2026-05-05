from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Company, FilingEvent
from app.services.refresh_state import build_payload_version_hash, mark_dataset_checked
from app.services.sec_edgar import FilingMetadata

EVENT_ITEM_LABELS: dict[str, str] = {
    "1.01": "Entry into a Material Definitive Agreement",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition",
    "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate or Increase a Direct Financial Obligation",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting or Failure to Satisfy Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.02": "Departure/Election of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}
FILING_EVENTS_PAYLOAD_VERSION = "filing-events-v1"
_EARNINGS_ADJACENT_ITEM_CODES = {"2.02", "7.01", "8.01"}
_TEXT_DOCUMENT_EXTENSIONS = {".htm", ".html", ".txt", ".xml", ".xhtml"}
_EXHIBIT_PREVIEW_MAX_LENGTH = 600


@dataclass(slots=True)
class NormalizedFilingEvent:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    items: str | None
    item_code: str
    category: str
    primary_document: str | None
    primary_doc_description: str | None
    source_url: str
    summary: str
    key_amounts: tuple[float, ...] = ()
    exhibit_references: tuple[str, ...] = ()
    exhibit_previews: tuple[dict[str, str | None], ...] = ()


def collect_filing_events(
    cik: str,
    filing_index: dict[str, FilingMetadata],
    *,
    client: Any | None = None,
) -> list[NormalizedFilingEvent]:
    rows: list[NormalizedFilingEvent] = []
    for filing in filing_index.values():
        form = (filing.form or "").upper()
        if form != "8-K":
            continue

        description = _normalize_optional_text(filing.primary_doc_description)
        item_tokens = _item_tokens(filing.items)
        if not item_tokens:
            item_tokens = ["UNSPECIFIED"]

        key_amounts = _extract_key_amounts(description)
        exhibit_references = _extract_exhibit_references(item_tokens, description)
        exhibit_previews_by_item = _extract_earnings_adjacent_exhibit_previews(
            cik,
            filing,
            item_tokens,
            client=client,
        )
        for item_code in item_tokens:
            category = _classify_event(item_code, description)
            summary = _build_event_summary(item_code, description, key_amounts)
            rows.append(
                NormalizedFilingEvent(
                    accession_number=filing.accession_number,
                    form=form,
                    filing_date=filing.filing_date,
                    report_date=filing.report_date,
                    items=_normalize_optional_text(filing.items),
                    item_code=item_code,
                    category=category,
                    primary_document=_normalize_optional_text(filing.primary_document),
                    primary_doc_description=description,
                    source_url=_build_filing_document_url(cik, filing.accession_number, filing.primary_document),
                    summary=summary,
                    key_amounts=key_amounts,
                    exhibit_references=exhibit_references,
                    exhibit_previews=exhibit_previews_by_item.get(item_code, ()),
                )
            )

    rows.sort(key=lambda row: (row.filing_date or row.report_date or datetime.min.date(), row.accession_number, row.item_code), reverse=True)
    return rows


def upsert_filing_events(
    session: Session,
    company: Company,
    events: Iterable[NormalizedFilingEvent],
    *,
    checked_at: datetime,
) -> int:
    count = 0
    event_list = list(events)
    payload_version_hash = build_payload_version_hash(
        version=FILING_EVENTS_PAYLOAD_VERSION,
        payload=event_list,
    )
    for event in event_list:
        statement = (
            insert(FilingEvent)
            .values(
                company_id=company.id,
                accession_number=event.accession_number,
                form=event.form,
                filing_date=event.filing_date,
                report_date=event.report_date,
                items=event.items,
                item_code=event.item_code,
                category=event.category,
                primary_document=event.primary_document,
                primary_doc_description=event.primary_doc_description,
                source_url=event.source_url,
                summary=event.summary,
                key_amounts=list(event.key_amounts),
                exhibit_references=_combined_exhibit_payload(event.exhibit_references, event.exhibit_previews),
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                index_elements=[FilingEvent.company_id, FilingEvent.accession_number, FilingEvent.item_code],
                set_={
                    "form": event.form,
                    "filing_date": event.filing_date,
                    "report_date": event.report_date,
                    "items": event.items,
                    "category": event.category,
                    "primary_document": event.primary_document,
                    "primary_doc_description": event.primary_doc_description,
                    "source_url": event.source_url,
                    "summary": event.summary,
                    "key_amounts": list(event.key_amounts),
                    "exhibit_references": _combined_exhibit_payload(event.exhibit_references, event.exhibit_previews),
                    "last_checked": checked_at,
                    "last_updated": checked_at,
                },
            )
        )
        session.execute(statement)
        count += 1

    mark_dataset_checked(
        session,
        company.id,
        "filings",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )
    return count


def _item_tokens(value: str | None) -> list[str]:
    normalized = (value or "").replace(" ", "")
    tokens = [token for token in normalized.split(",") if token]
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            deduped.append(token)
            seen.add(token)
    return deduped


def _classify_event(item_code: str, description: str | None) -> str:
    description_text = (description or "").lower()
    if item_code in {"2.02", "7.01", "9.01"}:
        return "Earnings"
    if item_code in {"1.01", "2.01"}:
        return "Deal"
    if item_code in {"2.03", "2.04", "2.05", "2.06"}:
        return "Financing"
    if item_code in {"4.01", "4.02"}:
        return "Accounting"
    if item_code in {"5.02", "5.03", "5.05"}:
        return "Leadership"
    if item_code in {"3.01", "3.02", "3.03"}:
        return "Capital Markets"
    if item_code == "8.01":
        return "General Update"
    if "earnings" in description_text or "results" in description_text:
        return "Earnings"
    if "director" in description_text or "officer" in description_text or "chief executive" in description_text:
        return "Leadership"
    if "agreement" in description_text or "acquisition" in description_text or "merger" in description_text:
        return "Deal"
    if "debt" in description_text or "credit" in description_text or "financing" in description_text:
        return "Financing"
    return "Other"


def _build_event_summary(item_code: str, description: str | None, key_amounts: tuple[float, ...]) -> str:
    label = EVENT_ITEM_LABELS.get(item_code)
    if description:
        return description
    if label:
        summary = f"8-K Item {item_code}: {label}."
    elif item_code == "UNSPECIFIED":
        summary = "8-K current report with event disclosure."
    else:
        summary = f"8-K Item {item_code} disclosure."
    if key_amounts:
        formatted = ", ".join(f"${value:,.0f}" for value in key_amounts[:2])
        return f"{summary} Key amounts: {formatted}."
    return summary


def _extract_key_amounts(description: str | None) -> tuple[float, ...]:
    if not description:
        return ()
    values: list[float] = []
    for match in re.finditer(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)", description):
        raw = match.group(1).replace(",", "")
        try:
            number = float(raw)
        except ValueError:
            continue
        values.append(number)
        if len(values) >= 3:
            break
    return tuple(values)


def _extract_exhibit_references(item_tokens: list[str], description: str | None) -> tuple[str, ...]:
    if not description:
        return ()
    has_item_901 = "9.01" in item_tokens
    description_text = description.lower()
    if not has_item_901 and "exhibit" not in description_text and " ex-" not in description_text:
        return ()

    references: list[str] = []
    seen: set[str] = set()
    pattern = re.compile(r"\b(?:exhibit|ex)\s*(?:no\.?\s*)?(?:-|:)?\s*([0-9]{1,3}(?:\.[0-9]{1,3})?)\b", re.IGNORECASE)
    for match in pattern.finditer(description):
        ref = match.group(1)
        if ref in seen:
            continue
        seen.add(ref)
        references.append(ref)
        if len(references) >= 20:
            break
    return tuple(references)


def _extract_earnings_adjacent_exhibit_previews(
    cik: str,
    filing: FilingMetadata,
    item_tokens: list[str],
    *,
    client: Any | None,
) -> dict[str, tuple[dict[str, str | None], ...]]:
    target_items = [item_code for item_code in item_tokens if item_code in _EARNINGS_ADJACENT_ITEM_CODES]
    if not target_items or client is None:
        return {}

    directory_items = _filing_directory_items(client, cik, filing.accession_number)
    exhibit_candidates = _select_exhibit_99_1_documents(directory_items)
    if not exhibit_candidates:
        return {}

    previews: list[dict[str, str | None]] = []
    for exhibit_name in exhibit_candidates:
        if not _is_supported_text_document(exhibit_name):
            continue
        try:
            source_url, payload = client.get_filing_document_text(cik, filing.accession_number, exhibit_name)
        except Exception:
            continue
        snippet = _extract_exhibit_snippet(payload)
        if not snippet:
            continue
        previews.append(
            {
                "accession_number": filing.accession_number,
                "item_code": None,
                "exhibit_filename": exhibit_name,
                "exhibit_type": "99.1",
                "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
                "source_url": source_url,
                "snippet": snippet,
            }
        )
        break

    if not previews:
        return {}

    per_item: dict[str, tuple[dict[str, str | None], ...]] = {}
    for item_code in target_items:
        per_item[item_code] = tuple({**preview, "item_code": item_code} for preview in previews)
    return per_item


def _filing_directory_items(client: Any, cik: str, accession_number: str) -> list[dict[str, Any]]:
    try:
        directory_index = client.get_filing_directory_index(cik, accession_number)
    except Exception:
        return []

    if not isinstance(directory_index, dict):
        return []
    directory = directory_index.get("directory")
    if not isinstance(directory, dict):
        return []
    items = directory.get("item")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _select_exhibit_99_1_documents(items: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in items:
        document_name = str(item.get("name") or item.get("document") or "").strip()
        if not document_name:
            continue
        search_text = " ".join(
            str(value)
            for value in (
                item.get("name"),
                item.get("document"),
                item.get("type"),
                item.get("description"),
            )
            if value
        ).lower()
        if not any(token in search_text for token in ("99.1", "99-1", "99_1", "ex-99.1", "ex99.1", "ex 99.1")):
            continue
        if document_name in seen:
            continue
        seen.add(document_name)
        names.append(document_name)
    return names


def _is_supported_text_document(document_name: str | None) -> bool:
    if not document_name:
        return False
    normalized = document_name.strip().lower()
    if not normalized:
        return False
    if "." not in normalized:
        return True
    return any(normalized.endswith(extension) for extension in _TEXT_DOCUMENT_EXTENSIONS)


def _extract_exhibit_snippet(payload: str | None) -> str | None:
    if not payload or "\x00" in payload:
        return None

    soup = BeautifulSoup(payload, "html.parser")
    text = _normalize_space(soup.get_text(" ", strip=True))
    if not text:
        return None
    if len(text) > _EXHIBIT_PREVIEW_MAX_LENGTH:
        return text[: _EXHIBIT_PREVIEW_MAX_LENGTH - 3].rstrip() + "..."
    return text


def _normalize_space(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or None


def _combined_exhibit_payload(
    references: tuple[str, ...],
    previews: tuple[dict[str, str | None], ...],
) -> list[str | dict[str, str | None]]:
    combined: list[str | dict[str, str | None]] = list(references)
    combined.extend(previews)
    return combined


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    numeric_cik = str(int(cik))
    compact_accession = accession_number.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{compact_accession}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json#accn={accession_number}"
