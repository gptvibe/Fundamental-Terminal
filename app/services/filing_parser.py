from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Callable

from bs4 import BeautifulSoup

SUPPORTED_PARSER_FORMS = {"10-K", "10-Q", "8-K"}


@dataclass(slots=True)
class ParsedFilingInsight:
    accession_number: str
    filing_type: str
    period_start: date
    period_end: date
    source: str
    data: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ReportRef:
    title: str
    file_name: str


class FilingParser:
    def __init__(self, fetch_text: Callable[[str], str]) -> None:
        self._fetch_text = fetch_text

    def parse_financial_insights(self, cik: str, filing_index: dict[str, object], *, limit: int = 6) -> list[ParsedFilingInsight]:
        candidates = []
        for metadata in filing_index.values():
            filing_type = _base_form(getattr(metadata, "form", None))
            if filing_type not in SUPPORTED_PARSER_FORMS:
                continue
            candidates.append(metadata)

        candidates.sort(
            key=lambda metadata: (
                getattr(metadata, "filing_date", None) or date.min,
                getattr(metadata, "accession_number", ""),
            ),
            reverse=True,
        )

        parsed_items: list[ParsedFilingInsight] = []
        for metadata in candidates[:limit]:
            parsed = self._parse_single_filing(cik, metadata)
            if parsed is not None:
                parsed_items.append(parsed)

        return parsed_items

    def _parse_single_filing(self, cik: str, metadata: object) -> ParsedFilingInsight | None:
        accession_number = str(getattr(metadata, "accession_number", "") or "")
        if not accession_number:
            return None

        filing_type = _base_form(getattr(metadata, "form", None))
        filing_base_url = _filing_base_url(cik, accession_number)
        source = _build_filing_source_url(cik, accession_number, getattr(metadata, "primary_document", None))

        try:
            filing_summary_xml = self._fetch_text(f"{filing_base_url}/FilingSummary.xml")
        except Exception:
            return None

        report_refs = _parse_filing_summary(filing_summary_xml)
        if not report_refs:
            return None

        metric_report = _pick_metric_report(report_refs)
        segment_report = _pick_segment_report(report_refs)

        revenue: int | float | None = None
        net_income: int | float | None = None
        operating_income: int | float | None = None
        segments: list[dict[str, object]] = []

        if metric_report is not None:
            metric_payload = self._load_report_html(filing_base_url, metric_report.file_name)
            if metric_payload:
                revenue, net_income, operating_income = _extract_income_metrics(metric_payload)

        if segment_report is not None:
            segment_payload = self._load_report_html(filing_base_url, segment_report.file_name)
            if segment_payload:
                segments = _extract_segment_rows(segment_payload)

        report_date = getattr(metadata, "report_date", None)
        filing_date = getattr(metadata, "filing_date", None)
        period_end = report_date or filing_date
        if period_end is None:
            return None

        fiscal_year = period_end.year
        data: dict[str, object] = {
            "form": filing_type,
            "fiscal_year": fiscal_year,
            "revenue": revenue,
            "net_income": net_income,
            "operating_income": operating_income,
            "segments": segments,
        }
        return ParsedFilingInsight(
            accession_number=accession_number,
            filing_type=filing_type,
            period_start=period_end,
            period_end=period_end,
            source=source,
            data=data,
        )

    def _load_report_html(self, filing_base_url: str, report_name: str) -> str | None:
        if not report_name:
            return None

        try:
            return self._fetch_text(f"{filing_base_url}/{report_name}")
        except Exception:
            return None


def _parse_filing_summary(payload: str) -> list[_ReportRef]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []

    refs: list[_ReportRef] = []
    for report in _iter_elements_local(root, "Report"):
        title = ""
        for key in ("ShortName", "LongName", "MenuCategory"):
            value = _findtext_local(report, key)
            if value and value.strip():
                title = value.strip()
                break

        file_name = ""
        for key in ("HtmlFileName", "XmlFileName"):
            value = _findtext_local(report, key)
            if value and value.strip():
                file_name = value.strip()
                break

        if title and file_name:
            refs.append(_ReportRef(title=title, file_name=file_name))

    return refs


def _pick_metric_report(refs: list[_ReportRef]) -> _ReportRef | None:
    scored: list[tuple[int, _ReportRef]] = []
    for ref in refs:
        normalized = _normalize_text(ref.title)
        score = 0
        if "statement" in normalized and ("operation" in normalized or "income" in normalized):
            score += 6
        if "consolidated" in normalized:
            score += 2
        if "revenue" in normalized or "sales" in normalized:
            score += 1
        if score > 0:
            scored.append((score, ref))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _pick_segment_report(refs: list[_ReportRef]) -> _ReportRef | None:
    scored: list[tuple[int, _ReportRef]] = []
    for ref in refs:
        normalized = _normalize_text(ref.title)
        if "segment" not in normalized:
            continue

        score = 2
        if "revenue" in normalized or "net sales" in normalized:
            score += 3
        if "business" in normalized or "geographic" in normalized:
            score += 1
        scored.append((score, ref))

    if not scored:
        return None

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _extract_income_metrics(report_html: str) -> tuple[int | float | None, int | float | None, int | float | None]:
    soup = BeautifulSoup(report_html, "html.parser")
    revenue: int | float | None = None
    net_income: int | float | None = None
    operating_income: int | float | None = None

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            label = _normalize_text(cells[0].get_text(" ", strip=True))
            if not label:
                continue

            value = _first_numeric(cells[1:])
            if value is None:
                continue

            if revenue is None and _looks_like_revenue_label(label):
                revenue = value
            elif net_income is None and _looks_like_net_income_label(label):
                net_income = value
            elif operating_income is None and _looks_like_operating_income_label(label):
                operating_income = value

        if revenue is not None and net_income is not None and operating_income is not None:
            break

    return revenue, net_income, operating_income


def _extract_segment_rows(report_html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(report_html, "html.parser")
    rows: list[tuple[str, int | float]] = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            segment_name = cells[0].get_text(" ", strip=True)
            normalized_segment = _normalize_text(segment_name)
            if not segment_name or not normalized_segment:
                continue
            if any(token in normalized_segment for token in ("total", "elimination", "consolidated", "other")):
                continue

            value = _first_numeric(cells[1:])
            if value is None:
                continue

            rows.append((segment_name.strip(), value))

    deduped: dict[str, tuple[str, int | float]] = {}
    for segment_name, value in rows:
        key = segment_name.lower()
        current = deduped.get(key)
        if current is None or abs(value) > abs(current[1]):
            deduped[key] = (segment_name, value)

    segment_rows = [
        {"name": name, "revenue": value}
        for name, value in sorted(
            (item for item in deduped.values()),
            key=lambda item: abs(item[1]),
            reverse=True,
        )
    ]
    return segment_rows[:12]


def _iter_elements_local(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == local_name]


def _findtext_local(parent: ET.Element, local_name: str) -> str | None:
    for child in parent:
        if _local_name(child.tag) == local_name:
            return child.text
    return None


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def _first_numeric(cells: list[object]) -> int | float | None:
    for cell in cells:
        text = cell.get_text(" ", strip=True)
        value = _parse_number(text)
        if value is not None:
            return value
    return None


def _parse_number(value: str) -> int | float | None:
    text = value.strip()
    if not text:
        return None
    if text in {"-", "--", "n/a", "na"}:
        return None

    text = text.replace("$", "").replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")

    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None

    numeric = float(match.group(0))
    if negative:
        numeric = -abs(numeric)

    if numeric.is_integer():
        return int(numeric)
    return numeric


def _looks_like_revenue_label(label: str) -> bool:
    return any(token in label for token in ("revenue", "net sales", "sales")) and "cost" not in label


def _looks_like_net_income_label(label: str) -> bool:
    return "net income" in label or "net earnings" in label or "profit loss" in label


def _looks_like_operating_income_label(label: str) -> bool:
    return "operating income" in label or "income from operations" in label or "operating profit" in label


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", value.lower())).strip()


def _base_form(value: str | None) -> str:
    if not value:
        return ""
    return value.split("/")[0].upper()


def _filing_base_url(cik: str, accession_number: str) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}"


def _build_filing_source_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    filing_base_url = _filing_base_url(cik, accession_number)
    if primary_document:
        return f"{filing_base_url}/{primary_document}"
    return filing_base_url
