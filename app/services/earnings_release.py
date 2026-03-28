from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Company, EarningsRelease
from app.services.sec_edgar import FilingMetadata

_EARNINGS_ITEM_CODES = {"2.02"}
_TEXT_DOCUMENT_EXTENSIONS = {".htm", ".html", ".txt", ".xml", ".xhtml"}
_GUIDANCE_HINTS = ("guidance", "expect", "expects", "forecast", "project", "projected", "outlook", "anticipate")
_MONEY_RANGE_PATTERN = re.compile(
    r"(?P<low>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)\s*(?:to|and|-)\s*(?P<high>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)",
    re.IGNORECASE,
)
_DATE_PATTERNS = (
    re.compile(r"\b(?:quarter|year|period|months?)\s+ended\s+(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"\bended\s+(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE),
    re.compile(r"\bended\s+(?P<date>\d{4}-\d{2}-\d{2})", re.IGNORECASE),
)
_LABEL_PATTERNS = (
    re.compile(r"\b(?P<label>(?:first|second|third|fourth)\s+quarter\s+\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(?P<label>q[1-4]\s+\d{4})\b", re.IGNORECASE),
    re.compile(r"\b(?P<label>(?:three|six|nine|twelve)\s+months?\s+ended\s+[A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b", re.IGNORECASE),
)
_METRIC_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "revenue": (
        re.compile(r"\brevenue\b[^$\n]{0,100}?(?:of|was|were|totaled|totalled|increased to|decreased to|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
        re.compile(r"\bnet sales\b[^$\n]{0,100}?(?:of|was|were|totaled|totalled|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
    ),
    "operating_income": (
        re.compile(r"\boperating income\b[^$\n]{0,100}?(?:of|was|were|totaled|totalled|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
        re.compile(r"\boperating profit\b[^$\n]{0,100}?(?:of|was|were|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
    ),
    "net_income": (
        re.compile(r"\bnet income\b[^$\n]{0,100}?(?:of|was|were|totaled|totalled|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
        re.compile(r"\bprofit(?: before| after)? tax\b[^$\n]{0,100}?(?:of|was|were|to|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", re.IGNORECASE),
    ),
    "diluted_eps": (
        re.compile(
            r"(?:earnings per diluted share|diluted earnings per share|diluted eps|eps|earnings per share)[^$\n]{0,100}?(?:of|was|were|at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ),
}
_GUIDANCE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "revenue": (
        re.compile(
            r"\brevenue\b.*?(?:guidance|expect|expects|forecast|project|projected|outlook).*?(?P<low>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)\s*(?:to|and|-)\s*(?P<high>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)",
            re.IGNORECASE,
        ),
    ),
    "eps": (
        re.compile(
            r"(?:eps|earnings per share|diluted eps|diluted earnings per share).*?(?:guidance|expect|expects|forecast|project|projected|outlook).*?(?P<low>\$?\s*\d[\d,]*(?:\.\d+)?)\s*(?:to|and|-)\s*(?P<high>\$?\s*\d[\d,]*(?:\.\d+)?)",
            re.IGNORECASE,
        ),
    ),
}
_BUYBACK_PATTERNS = (
    re.compile(
        r"(?:share repurchase|repurchase authorization|authorized to repurchase|buyback program|stock repurchase).*?(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)",
        re.IGNORECASE,
    ),
)
_DIVIDEND_PATTERNS = (
    re.compile(
        r"(?:quarterly dividend|cash dividend|dividend)\s+(?:of|in the amount of|set at|declared at)\s*(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?)\s*(?:per share|a share|/share)?",
        re.IGNORECASE,
    ),
)


@dataclass(slots=True)
class NormalizedEarningsRelease:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    filing_acceptance_at: datetime | None
    source_url: str
    primary_document: str | None
    exhibit_document: str | None
    exhibit_type: str | None
    reported_period_label: str | None
    reported_period_end: date | None
    revenue: float | None
    operating_income: float | None
    net_income: float | None
    diluted_eps: float | None
    revenue_guidance_low: float | None
    revenue_guidance_high: float | None
    eps_guidance_low: float | None
    eps_guidance_high: float | None
    share_repurchase_amount: float | None
    dividend_per_share: float | None
    highlights: tuple[str, ...] = ()
    parse_state: str = "metadata_only"


def collect_earnings_releases(
    cik: str,
    filing_index: dict[str, FilingMetadata],
    client: Any | None = None,
) -> list[NormalizedEarningsRelease]:
    rows: list[NormalizedEarningsRelease] = []
    for filing in filing_index.values():
        if (filing.form or "").upper() != "8-K":
            continue
        if not (_item_tokens(filing.items) & _EARNINGS_ITEM_CODES):
            continue
        rows.append(_build_release(cik, filing, client=client))

    rows.sort(key=lambda row: (row.filing_date or date.min, row.reported_period_end or date.min, row.accession_number), reverse=True)
    return rows


def upsert_earnings_releases(
    session: Session,
    company: Company,
    releases: Iterable[NormalizedEarningsRelease],
    *,
    checked_at: datetime,
) -> int:
    count = 0
    for release in releases:
        statement = (
            insert(EarningsRelease)
            .values(
                company_id=company.id,
                accession_number=release.accession_number,
                form=release.form,
                filing_date=release.filing_date,
                report_date=release.report_date,
                filing_acceptance_at=release.filing_acceptance_at,
                source_url=release.source_url,
                primary_document=release.primary_document,
                exhibit_document=release.exhibit_document,
                exhibit_type=release.exhibit_type,
                reported_period_label=release.reported_period_label,
                reported_period_end=release.reported_period_end,
                revenue=release.revenue,
                operating_income=release.operating_income,
                net_income=release.net_income,
                diluted_eps=release.diluted_eps,
                revenue_guidance_low=release.revenue_guidance_low,
                revenue_guidance_high=release.revenue_guidance_high,
                eps_guidance_low=release.eps_guidance_low,
                eps_guidance_high=release.eps_guidance_high,
                share_repurchase_amount=release.share_repurchase_amount,
                dividend_per_share=release.dividend_per_share,
                highlights=list(release.highlights),
                parse_state=release.parse_state,
                fetch_timestamp=checked_at,
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                index_elements=[EarningsRelease.company_id, EarningsRelease.accession_number],
                set_={
                    "form": release.form,
                    "filing_date": release.filing_date,
                    "report_date": release.report_date,
                    "filing_acceptance_at": release.filing_acceptance_at,
                    "source_url": release.source_url,
                    "primary_document": release.primary_document,
                    "exhibit_document": release.exhibit_document,
                    "exhibit_type": release.exhibit_type,
                    "reported_period_label": release.reported_period_label,
                    "reported_period_end": release.reported_period_end,
                    "revenue": release.revenue,
                    "operating_income": release.operating_income,
                    "net_income": release.net_income,
                    "diluted_eps": release.diluted_eps,
                    "revenue_guidance_low": release.revenue_guidance_low,
                    "revenue_guidance_high": release.revenue_guidance_high,
                    "eps_guidance_low": release.eps_guidance_low,
                    "eps_guidance_high": release.eps_guidance_high,
                    "share_repurchase_amount": release.share_repurchase_amount,
                    "dividend_per_share": release.dividend_per_share,
                    "highlights": list(release.highlights),
                    "parse_state": release.parse_state,
                    "fetch_timestamp": checked_at,
                    "last_checked": checked_at,
                    "last_updated": checked_at,
                },
            )
        )
        session.execute(statement)
        count += 1

    company.earnings_last_checked = checked_at
    return count


def _build_release(cik: str, filing: FilingMetadata, *, client: Any | None) -> NormalizedEarningsRelease:
    source_candidates = _candidate_documents(client, cik, filing)
    source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
    exhibit_document: str | None = None
    exhibit_type: str | None = None
    document_payload: str | None = None

    for candidate in source_candidates:
        if client is None:
            break
        document_name = candidate["document_name"]
        if not _is_supported_text_document(document_name):
            continue
        try:
            source_url, document_payload = client.get_filing_document_text(cik, filing.accession_number, document_name)
        except Exception:
            continue
        if not _looks_like_text_payload(document_payload):
            continue
        exhibit_document = candidate["exhibit_document"]
        exhibit_type = candidate["exhibit_type"]
        break

    parsed = _parse_release_document(document_payload, filing) if document_payload else _empty_release_parse(filing)
    parse_state = "parsed" if parsed["has_metrics"] else "metadata_only"

    return NormalizedEarningsRelease(
        accession_number=filing.accession_number,
        form=filing.form or "8-K",
        filing_date=filing.filing_date,
        report_date=filing.report_date,
        filing_acceptance_at=filing.acceptance_datetime,
        source_url=source_url,
        primary_document=filing.primary_document,
        exhibit_document=exhibit_document,
        exhibit_type=exhibit_type,
        reported_period_label=parsed["reported_period_label"],
        reported_period_end=parsed["reported_period_end"],
        revenue=parsed["revenue"],
        operating_income=parsed["operating_income"],
        net_income=parsed["net_income"],
        diluted_eps=parsed["diluted_eps"],
        revenue_guidance_low=parsed["revenue_guidance_low"],
        revenue_guidance_high=parsed["revenue_guidance_high"],
        eps_guidance_low=parsed["eps_guidance_low"],
        eps_guidance_high=parsed["eps_guidance_high"],
        share_repurchase_amount=parsed["share_repurchase_amount"],
        dividend_per_share=parsed["dividend_per_share"],
        highlights=parsed["highlights"],
        parse_state=parse_state,
    )


def _candidate_documents(client: Any | None, cik: str, filing: FilingMetadata) -> list[dict[str, str | None]]:
    candidates: list[dict[str, str | None]] = []
    if client is not None:
        try:
            directory = client.get_filing_directory_index(cik, filing.accession_number)
        except Exception:
            directory = {}
        items = directory.get("directory", {}).get("item", []) if isinstance(directory, dict) else []
        candidates.extend(_documents_from_directory(items))

    primary_document = (filing.primary_document or "").strip() or None
    if primary_document and _is_supported_text_document(primary_document):
        candidates.append(
            {
                "document_name": primary_document,
                "exhibit_document": None,
                "exhibit_type": None,
                "priority": "primary",
            }
        )

    priority_order = {"99.1": 0, "99.2": 1, "primary": 2}
    deduped: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            priority_order.get(str(item.get("priority") or "primary"), 3),
            str(item.get("document_name") or "").lower(),
        ),
    ):
        document_name = str(candidate.get("document_name") or "").strip()
        if not document_name or document_name in seen:
            continue
        seen.add(document_name)
        deduped.append(candidate)
    return deduped


def _documents_from_directory(items: list[Any]) -> list[dict[str, str | None]]:
    candidates: list[dict[str, str | None]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        document_name = str(item.get("name") or item.get("document") or "").strip()
        if not document_name:
            continue
        if not _is_supported_text_document(document_name):
            continue
        exhibit_type = _extract_exhibit_type(item)
        if exhibit_type not in {"99.1", "99.2"}:
            continue
        candidates.append(
            {
                "document_name": document_name,
                "exhibit_document": document_name,
                "exhibit_type": exhibit_type,
                "priority": exhibit_type,
            }
        )
    return candidates


def _extract_exhibit_type(item: dict[str, Any]) -> str | None:
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
    if any(token in search_text for token in ("99.1", "99-1", "99_1", "ex-99.1", "ex99.1", "ex 99.1")):
        return "99.1"
    if any(token in search_text for token in ("99.2", "99-2", "99_2", "ex-99.2", "ex99.2", "ex 99.2")):
        return "99.2"
    return None


def _parse_release_document(document_payload: str, filing: FilingMetadata) -> dict[str, Any]:
    blocks = _extract_text_blocks(document_payload)
    plain_text = " ".join(blocks)
    reported_period_label = _extract_reported_period_label(plain_text)
    reported_period_end = _extract_reported_period_end(plain_text) or filing.report_date

    revenue = _extract_metric_value(blocks, "revenue")
    operating_income = _extract_metric_value(blocks, "operating_income")
    net_income = _extract_metric_value(blocks, "net_income")
    diluted_eps = _extract_metric_value(blocks, "diluted_eps")
    revenue_guidance_low, revenue_guidance_high = _extract_guidance_range(blocks, "revenue")
    eps_guidance_low, eps_guidance_high = _extract_guidance_range(blocks, "eps")
    share_repurchase_amount = _extract_single_amount(blocks, _BUYBACK_PATTERNS)
    dividend_per_share = _extract_single_amount(blocks, _DIVIDEND_PATTERNS)
    highlights = _extract_highlights(blocks, plain_text)

    return {
        "reported_period_label": reported_period_label,
        "reported_period_end": reported_period_end,
        "revenue": revenue,
        "operating_income": operating_income,
        "net_income": net_income,
        "diluted_eps": diluted_eps,
        "revenue_guidance_low": revenue_guidance_low,
        "revenue_guidance_high": revenue_guidance_high,
        "eps_guidance_low": eps_guidance_low,
        "eps_guidance_high": eps_guidance_high,
        "share_repurchase_amount": share_repurchase_amount,
        "dividend_per_share": dividend_per_share,
        "highlights": highlights,
        "has_metrics": any(
            value is not None
            for value in (
                revenue,
                operating_income,
                net_income,
                diluted_eps,
                revenue_guidance_low,
                revenue_guidance_high,
                eps_guidance_low,
                eps_guidance_high,
                share_repurchase_amount,
                dividend_per_share,
            )
        ),
    }


def _empty_release_parse(filing: FilingMetadata) -> dict[str, Any]:
    return {
        "reported_period_label": None,
        "reported_period_end": filing.report_date,
        "revenue": None,
        "operating_income": None,
        "net_income": None,
        "diluted_eps": None,
        "revenue_guidance_low": None,
        "revenue_guidance_high": None,
        "eps_guidance_low": None,
        "eps_guidance_high": None,
        "share_repurchase_amount": None,
        "dividend_per_share": None,
        "highlights": (),
        "has_metrics": False,
    }


def _extract_text_blocks(document_payload: str) -> list[str]:
    soup = BeautifulSoup(document_payload, "html.parser")
    selectors = ["p", "li", "h1", "h2", "h3", "td", "th"]
    blocks: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        for node in soup.find_all(selector):
            text = _clean_text(node.get_text(" ", strip=True))
            if not text or text in seen:
                continue
            seen.add(text)
            blocks.append(text)
    if blocks:
        return blocks
    fallback = [
        cleaned
        for raw in re.split(r"[\r\n]+", soup.get_text(" ", strip=True))
        if (cleaned := _clean_text(raw))
    ]
    return fallback


def _extract_reported_period_label(text: str) -> str | None:
    for pattern in _LABEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return _clean_text(match.group("label"))
    return None


def _extract_reported_period_end(text: str) -> date | None:
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            parsed = _parse_date(match.group("date"))
            if parsed is not None:
                return parsed
    return None


def _extract_metric_value(blocks: list[str], metric_name: str) -> float | None:
    patterns = _METRIC_PATTERNS.get(metric_name, ())
    for block in blocks:
        for pattern in patterns:
            match = pattern.search(block)
            if match:
                amount = _parse_amount(match.group("amount"))
                if amount is not None:
                    return amount
    return None


def _extract_guidance_range(blocks: list[str], metric_name: str) -> tuple[float | None, float | None]:
    for block in blocks:
        lower = block.lower()
        if metric_name not in lower or not any(hint in lower for hint in _GUIDANCE_HINTS):
            continue
        range_match = _MONEY_RANGE_PATTERN.search(block)
        if range_match:
            return _parse_amount(range_match.group("low")), _parse_amount(range_match.group("high"))
        numbers = [amount for amount in (_parse_amount(match.group("amount")) for match in re.finditer(r"(?P<amount>\$?\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:billion|million|thousand|bn|mm|m|k))?)", block, re.IGNORECASE)) if amount is not None]
        if len(numbers) >= 2:
            return numbers[0], numbers[1]
        if len(numbers) == 1:
            return numbers[0], numbers[0]
    return (None, None)


def _extract_single_amount(blocks: list[str], patterns: tuple[re.Pattern[str], ...]) -> float | None:
    for block in blocks:
        for pattern in patterns:
            match = pattern.search(block)
            if match:
                amount = _parse_amount(match.group("amount"))
                if amount is not None:
                    return amount
    return None


def _extract_highlights(blocks: list[str], plain_text: str) -> tuple[str, ...]:
    highlights: list[str] = []
    for block in blocks:
        lower = block.lower()
        if lower.startswith("item "):
            continue
        if len(block) < 20:
            continue
        if any(keyword in lower for keyword in ("revenue", "income", "eps", "guidance", "repurchase", "dividend", "outlook")):
            highlights.append(_truncate(block, 220))
        elif not highlights and any(char.isdigit() for char in block):
            highlights.append(_truncate(block, 220))
        if len(highlights) >= 3:
            break

    if not highlights:
        for chunk in re.split(r"(?<=[.!?])\s+", plain_text):
            cleaned = _clean_text(chunk)
            if not cleaned or len(cleaned) < 20:
                continue
            highlights.append(_truncate(cleaned, 220))
            if len(highlights) >= 3:
                break

    deduped: list[str] = []
    seen: set[str] = set()
    for highlight in highlights:
        if highlight in seen:
            continue
        seen.add(highlight)
        deduped.append(highlight)
    return tuple(deduped[:3])


def _parse_amount(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().lower().replace("$", "").replace(",", "")
    if not cleaned:
        return None
    multiplier = 1.0
    for suffix, scale in (
        ("trillion", 1_000_000_000_000.0),
        ("billion", 1_000_000_000.0),
        ("million", 1_000_000.0),
        ("thousand", 1_000.0),
        ("bn", 1_000_000_000.0),
        ("mm", 1_000_000.0),
        ("m", 1_000_000.0),
        ("k", 1_000.0),
    ):
        if cleaned.endswith(f" {suffix}") or cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            multiplier = scale
            break
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _item_tokens(value: str | None) -> set[str]:
    normalized = (value or "").replace(" ", "")
    return {token for token in normalized.split(",") if token}


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    numeric_cik = str(int(cik))
    accession_compact = accession_number.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json#accn={accession_number}"


def _is_supported_text_document(document_name: str | None) -> bool:
    if not document_name:
        return False
    normalized = document_name.strip().lower()
    if not normalized:
        return False
    if "." not in normalized:
        return True
    for extension in _TEXT_DOCUMENT_EXTENSIONS:
        if normalized.endswith(extension):
            return True
    return False


def _looks_like_text_payload(document_payload: str | None) -> bool:
    if not document_payload:
        return False
    if "\x00" in document_payload:
        return False
    sample = document_payload[:2048]
    if not sample:
        return False
    control_count = sum(1 for char in sample if ord(char) < 32 and char not in "\t\n\r")
    if control_count:
        return False
    return any(token in sample.lower() for token in ("<html", "<body", "<table", "<p", "<div", "<xml", "revenue", "earnings", "guidance"))


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n;:,")
    return cleaned or None


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."
