from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import CapitalMarketsEvent, Company
from app.services.refresh_state import build_payload_version_hash, mark_dataset_checked
from app.services.sec_edgar import FilingMetadata

SUPPORTED_CAPITAL_FORMS = {
    "S-1", "S-1/A", "S-3", "S-3/A", "F-3", "F-3/A", "424B1", "424B2", "424B3", "424B4", "424B5", "NT 10-K", "NT 10-Q",
    "S-8", "S-8/A",
}
CAPITAL_MARKETS_PAYLOAD_VERSION = "capital-markets-v1"


@dataclass(slots=True)
class NormalizedCapitalMarketsEvent:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    primary_document: str | None
    primary_doc_description: str | None
    source_url: str
    summary: str
    event_type: str | None = None
    security_type: str | None = None
    offering_amount: float | None = None
    shelf_size: float | None = None
    is_late_filer: bool = False
    plan_name: str | None = None
    registered_shares: float | None = None
    shares_parse_confidence: str | None = None


def collect_capital_markets_events(cik: str, filing_index: dict[str, FilingMetadata]) -> list[NormalizedCapitalMarketsEvent]:
    rows: list[NormalizedCapitalMarketsEvent] = []
    for filing in filing_index.values():
        form = (filing.form or "").upper()
        if form not in SUPPORTED_CAPITAL_FORMS:
            continue

        description = _normalize_optional_text(filing.primary_doc_description)
        source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
        event_type = _event_type(form)
        security_type = _security_type(form, description)
        offering_amount = _extract_dollar_amount(description)
        shelf_size = offering_amount if form in {"S-3", "S-3/A", "F-3", "F-3/A"} else None
        is_late_filer = form in {"NT 10-K", "NT 10-Q"}
        is_s8 = form in {"S-8", "S-8/A"}
        plan_name = _extract_plan_name(description) if is_s8 else None
        registered_shares = _extract_registered_shares(description) if is_s8 else None
        shares_parse_confidence = _shares_parse_confidence(description, registered_shares, plan_name) if is_s8 else None
        summary = _summary_line(form, description, event_type, security_type, offering_amount, is_late_filer, plan_name, registered_shares)

        rows.append(
            NormalizedCapitalMarketsEvent(
                accession_number=filing.accession_number,
                form=form,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                primary_document=_normalize_optional_text(filing.primary_document),
                primary_doc_description=description,
                source_url=source_url,
                summary=summary,
                event_type=event_type,
                security_type=security_type,
                offering_amount=offering_amount,
                shelf_size=shelf_size,
                is_late_filer=is_late_filer,
                plan_name=plan_name,
                registered_shares=registered_shares,
                shares_parse_confidence=shares_parse_confidence,
            )
        )

    rows.sort(key=lambda row: (row.filing_date or row.report_date or datetime.min.date(), row.accession_number), reverse=True)
    return rows


def upsert_capital_markets_events(
    session: Session,
    company: Company,
    events: Iterable[NormalizedCapitalMarketsEvent],
    *,
    checked_at: datetime,
) -> int:
    count = 0
    event_list = list(events)
    payload_version_hash = build_payload_version_hash(
        version=CAPITAL_MARKETS_PAYLOAD_VERSION,
        payload=event_list,
    )
    for event in event_list:
        statement = (
            insert(CapitalMarketsEvent)
            .values(
                company_id=company.id,
                accession_number=event.accession_number,
                form=event.form,
                filing_date=event.filing_date,
                report_date=event.report_date,
                primary_document=event.primary_document,
                primary_doc_description=event.primary_doc_description,
                source_url=event.source_url,
                summary=event.summary,
                event_type=event.event_type,
                security_type=event.security_type,
                offering_amount=event.offering_amount,
                shelf_size=event.shelf_size,
                is_late_filer=event.is_late_filer,
                plan_name=event.plan_name,
                registered_shares=event.registered_shares,
                shares_parse_confidence=event.shares_parse_confidence,
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                index_elements=[CapitalMarketsEvent.company_id, CapitalMarketsEvent.accession_number],
                set_={
                    "form": event.form,
                    "filing_date": event.filing_date,
                    "report_date": event.report_date,
                    "primary_document": event.primary_document,
                    "primary_doc_description": event.primary_doc_description,
                    "source_url": event.source_url,
                    "summary": event.summary,
                    "event_type": event.event_type,
                    "security_type": event.security_type,
                    "offering_amount": event.offering_amount,
                    "shelf_size": event.shelf_size,
                    "is_late_filer": event.is_late_filer,
                    "plan_name": event.plan_name,
                    "registered_shares": event.registered_shares,
                    "shares_parse_confidence": event.shares_parse_confidence,
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
        "capital_markets",
        checked_at=checked_at,
        success=True,
        payload_version_hash=payload_version_hash,
        invalidate_hot_cache=True,
    )
    return count


def _event_type(form: str) -> str:
    if form in {"S-8", "S-8/A"}:
        return "Equity Plan Registration"
    if form.startswith("S-") or form.startswith("F-"):
        return "Registration"
    if form.startswith("424B"):
        return "Prospectus"
    if form.startswith("NT"):
        return "Late Filing Notice"
    return "Capital Markets"


def _security_type(form: str, description: str | None) -> str | None:
    description_text = (description or "").lower()
    if "preferred" in description_text:
        return "Preferred Equity"
    if "warrant" in description_text:
        return "Warrants"
    if "notes" in description_text or "debt" in description_text:
        return "Debt"
    if form.startswith("S-") or form.startswith("F-") or form.startswith("424B"):
        return "Common Equity"
    return None


def _extract_dollar_amount(description: str | None) -> float | None:
    if not description:
        return None
    match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)", description)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _summary_line(
    form: str,
    description: str | None,
    event_type: str | None,
    security_type: str | None,
    offering_amount: float | None,
    is_late_filer: bool,
    plan_name: str | None = None,
    registered_shares: float | None = None,
) -> str:
    if description:
        return description
    bits = [f"{form} {event_type or 'capital markets'} filing"]
    if plan_name:
        bits.append(plan_name)
    if registered_shares is not None:
        bits.append(f"{registered_shares:,.0f} shares")
    elif security_type:
        bits.append(security_type)
    if offering_amount is not None:
        bits.append(f"${offering_amount:,.0f}")
    if is_late_filer:
        bits.append("late-filer notice")
    return "; ".join(bits) + "."


_REGISTERED_SHARES_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s+(?:additional\s+)?shares",
    re.IGNORECASE,
)

_PLAN_UNDER_RE = re.compile(
    r"(?:pursuant to|under|for)\s+(?:the\s+)?(.+?(?:plan|program|espp|esop))",
    re.IGNORECASE,
)

_PLAN_INLINE_RE = re.compile(
    r"([A-Z][^\n,;]{3,80}?(?:Incentive Plan|Stock Plan|Stock Option Plan|Equity Plan|"
    r"Compensation Plan|Purchase Plan|Bonus Plan|ESPP|ESOP|Award Plan|Omnibus Plan|"
    r"Long-Term Incentive Plan))",
    re.IGNORECASE,
)

_PLAN_KEYWORDS = (
    "incentive plan", "stock plan", "equity plan", "stock option plan",
    "stock purchase plan", "equity incentive", "compensation plan", "bonus plan",
    "long-term incentive", "restricted stock", "award plan", "omnibus plan",
    "employee stock", "espp", "esop",
)


def _extract_registered_shares(description: str | None) -> float | None:
    if not description:
        return None
    match = _REGISTERED_SHARES_RE.search(description)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _extract_plan_name(description: str | None) -> str | None:
    if not description:
        return None
    # Try explicit "pursuant to / under / for the XYZ Plan" pattern first.
    match = _PLAN_UNDER_RE.search(description)
    if match:
        candidate = match.group(1).strip().rstrip(".,;")
        if len(candidate) <= 120:
            return candidate
    # Fall back to inline plan-name pattern.
    match = _PLAN_INLINE_RE.search(description)
    if match:
        candidate = match.group(1).strip().rstrip(".,;")
        if len(candidate) <= 120:
            return candidate
    # Last resort: return None — the caller can infer from keyword presence.
    desc_lower = description.lower()
    for kw in _PLAN_KEYWORDS:
        if kw in desc_lower:
            return None  # keyword present but name un-extractable
    return None


def _shares_parse_confidence(
    description: str | None,
    registered_shares: float | None,
    plan_name: str | None,
) -> str:
    has_shares = registered_shares is not None
    has_plan = plan_name is not None
    if not has_plan:
        desc_lower = (description or "").lower()
        has_plan_keyword = any(kw in desc_lower for kw in _PLAN_KEYWORDS)
    else:
        has_plan_keyword = True

    if has_shares and has_plan_keyword:
        return "high"
    if has_shares or has_plan_keyword:
        return "medium"
    return "low"


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
