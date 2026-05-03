from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from typing import Callable

from bs4 import BeautifulSoup

from app.services.filing_risk_signals import extract_filing_risk_signals

SUPPORTED_PARSER_FORMS = {"10-K", "10-Q", "8-K"}

_HIGH_SIGNAL_FOOTNOTE_CONFIG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("revenue_recognition", "Revenue Recognition", ("revenue recognition", "revenue from contracts", "contract balances")),
    ("debt", "Debt And Borrowings", ("debt", "borrowings", "credit facility", "convertible", "notes payable")),
    ("stock_compensation", "Stock-Based Compensation", ("share based compensation", "stock based compensation", "stock compensation", "share compensation")),
    ("income_taxes", "Income Taxes", ("income taxes", "taxes")),
    ("goodwill_intangibles", "Goodwill And Intangibles", ("goodwill", "intangible")),
    ("contingencies", "Commitments And Contingencies", ("commitments", "contingencies", "legal proceedings", "litigation")),
    ("segments", "Segment Reporting", ("segments", "segment information")),
    ("fair_value", "Fair Value", ("fair value", "financial instruments")),
    ("inventory", "Inventory", ("inventory",)),
)
_NON_GAAP_TERMS = (
    "non gaap",
    "non-gaap",
    "adjusted ebitda",
    "adjusted operating income",
    "adjusted earnings",
    "adjusted diluted eps",
    "adjusted free cash flow",
)
_NON_GAAP_RECONCILIATION_TERMS = ("reconcile", "reconciliation", "most directly comparable gaap", "comparable gaap")
_CONTROL_TERMS = (
    "material weakness",
    "material weaknesses",
    "not effective",
    "ineffective",
    "internal control over financial reporting",
    "disclosure controls and procedures",
    "non-reliance",
    "non reliance",
    "restatement",
)
_AUDITOR_CHANGE_TERMS = ("dismissed", "resigned", "engaged", "appointed", "replaced", "changed auditors", "changed independent")
_AUDITOR_NAMES = (
    "pricewaterhousecoopers",
    "pwc",
    "deloitte",
    "ernst young",
    "ey",
    "kpmg",
    "bdo",
    "grant thornton",
)
_ITEM_SECTION_PATTERNS: dict[str, dict[str, tuple[tuple[str, ...], tuple[str, ...]]]] = {
    "10-K": {
        "mda": (
            (
                r"^item\s+7\b.*management.?s discussion and analysis",
                r"^management.?s discussion and analysis of financial condition and results of operations",
            ),
            (
                r"^item\s+7a\b",
                r"^item\s+8\b",
            ),
        ),
        "controls": (
            (
                r"^item\s+9a\b.*controls and procedures",
                r"^controls and procedures$",
            ),
            (
                r"^item\s+9b\b",
                r"^item\s+10\b",
                r"^signatures$",
            ),
        ),
    },
    "10-Q": {
        "mda": (
            (
                r"^item\s+2\b.*management.?s discussion and analysis",
                r"^management.?s discussion and analysis of financial condition and results of operations",
            ),
            (
                r"^item\s+3\b",
                r"^item\s+4\b",
            ),
        ),
        "controls": (
            (
                r"^item\s+4\b.*controls and procedures",
                r"^controls and procedures$",
            ),
            (
                r"^part\s+ii\b",
                r"^signatures$",
            ),
        ),
    },
}


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
        primary_document = getattr(metadata, "primary_document", None)
        source = _build_filing_source_url(cik, accession_number, primary_document)

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
        mdna: dict[str, object] | None = None
        footnotes: list[dict[str, object]] = []
        non_gaap: dict[str, object] = {}
        controls: dict[str, object] = {}

        if metric_report is not None:
            metric_payload = self._load_report_html(filing_base_url, metric_report.file_name)
            if metric_payload:
                revenue, net_income, operating_income = _extract_income_metrics(metric_payload)

        if segment_report is not None:
            segment_payload = self._load_report_html(filing_base_url, segment_report.file_name)
            if segment_payload:
                segments = _extract_segment_rows(segment_payload)

        main_payload = self._load_report_html(filing_base_url, primary_document) if primary_document else None
        main_text = _extract_document_text(main_payload) if main_payload else ""

        if main_payload and filing_type in _ITEM_SECTION_PATTERNS:
            mdna = _extract_item_section(main_payload, filing_type, "mda", source)
            control_section = _extract_item_section(main_payload, filing_type, "controls", source)
            controls = _extract_controls_signal(control_section or {}, main_text, source)
        else:
            controls = _extract_controls_signal({}, main_text, source)

        non_gaap = _extract_non_gaap_signal(mdna or {}, main_text, source)
        footnotes = _extract_high_signal_footnotes(self._load_report_html, filing_base_url, report_refs)

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
            "mdna": mdna,
            "footnotes": footnotes,
            "non_gaap": non_gaap,
            "controls": controls,
            "risk_signals": [
                {
                    "ticker": item.ticker,
                    "cik": item.cik,
                    "accession_number": item.accession_number,
                    "form_type": item.form_type,
                    "filed_date": item.filed_date,
                    "signal_category": item.signal_category,
                    "matched_phrase": item.matched_phrase,
                    "context_snippet": item.context_snippet,
                    "confidence": item.confidence,
                    "severity": item.severity,
                    "source": item.source,
                    "provenance": item.provenance,
                }
                for item in extract_filing_risk_signals(
                    cik=cik,
                    filing_metadata=metadata,
                    filing_text=main_text,
                    source=source,
                )
            ],
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


def _extract_high_signal_footnotes(
    load_report_html: Callable[[str, str], str | None],
    filing_base_url: str,
    report_refs: list[_ReportRef],
) -> list[dict[str, object]]:
    selected = _pick_high_signal_footnote_reports(report_refs)
    rows: list[dict[str, object]] = []
    for key, label, ref in selected:
        payload = load_report_html(filing_base_url, ref.file_name)
        if not payload:
            continue
        text = _extract_document_text(payload)
        if not text:
            continue
        terms = _matched_terms(text, next(config[2] for config in _HIGH_SIGNAL_FOOTNOTE_CONFIG if config[0] == key))
        rows.append(
            {
                "key": key,
                "label": label,
                "title": ref.title,
                "source": f"{filing_base_url}/{ref.file_name}",
                "excerpt": _build_excerpt(text, terms),
                "text": _clip_text(text, limit=7000),
                "signal_terms": terms,
            }
        )
    return rows


def _pick_high_signal_footnote_reports(refs: list[_ReportRef]) -> list[tuple[str, str, _ReportRef]]:
    selected: dict[str, tuple[int, _ReportRef, str]] = {}
    for ref in refs:
        normalized = _normalize_text(ref.title)
        if "policy" in normalized and "significant accounting" in normalized:
            continue
        for key, label, patterns in _HIGH_SIGNAL_FOOTNOTE_CONFIG:
            if not any(pattern in normalized for pattern in patterns):
                continue
            score = sum(2 for pattern in patterns if pattern in normalized)
            if "table" in normalized:
                score -= 2
            if "text block" in normalized:
                score += 3
            if "note" in normalized:
                score += 1
            current = selected.get(key)
            if current is None or score > current[0]:
                selected[key] = (score, ref, label)
    return [(key, payload[2], payload[1]) for key, payload in selected.items()]


def _extract_item_section(report_html: str, filing_type: str, section_kind: str, source: str) -> dict[str, object] | None:
    patterns = _ITEM_SECTION_PATTERNS.get(filing_type, {}).get(section_kind)
    if patterns is None:
        return None
    starts, ends = patterns
    lines = _extract_document_lines(report_html)
    if not lines:
        return None
    normalized_lines = [_normalize_text(line) for line in lines]
    start_index = _first_matching_index(normalized_lines, starts)
    if start_index is None:
        return None
    end_index = _first_matching_index(normalized_lines[start_index + 1 :], ends)
    absolute_end = start_index + 1 + end_index if end_index is not None else min(len(lines), start_index + 120)
    selected_lines = lines[start_index:absolute_end]
    if len(selected_lines) < 2:
        return None
    body = "\n".join(selected_lines[1:])
    if not body.strip():
        return None
    return {
        "key": section_kind,
        "label": "MD&A" if section_kind == "mda" else "Controls And Procedures",
        "title": selected_lines[0],
        "source": source,
        "excerpt": _build_excerpt(body, (), line_limit=4),
        "text": _clip_text(body, limit=9000),
    }


def _extract_non_gaap_signal(section_payload: dict[str, object], document_text: str, source: str) -> dict[str, object]:
    section_text = str(section_payload.get("text") or "") if isinstance(section_payload, dict) else ""
    text = section_text or document_text
    if not text:
        return {}
    normalized = _normalize_text(text)
    matched = _matched_terms(normalized, _NON_GAAP_TERMS, normalized_input=True)
    reconciliation_mentions = sum(normalized.count(term) for term in _NON_GAAP_RECONCILIATION_TERMS)
    mention_count = sum(normalized.count(term) for term in matched)
    if mention_count == 0 and reconciliation_mentions == 0:
        return {}
    return {
        "mention_count": mention_count,
        "terms": matched,
        "reconciliation_mentions": reconciliation_mentions,
        "has_reconciliation": reconciliation_mentions > 0,
        "source": source,
        "excerpt": _build_excerpt(text, matched or _NON_GAAP_RECONCILIATION_TERMS),
    }


def _extract_controls_signal(section_payload: dict[str, object], document_text: str, source: str) -> dict[str, object]:
    section_text = str(section_payload.get("text") or "") if isinstance(section_payload, dict) else ""
    text = section_text or document_text
    if not text:
        return {}
    normalized = _normalize_text(text)
    auditor_names = _matched_terms(normalized, _AUDITOR_NAMES, normalized_input=True)
    auditor_change_terms = _matched_terms(normalized, _AUDITOR_CHANGE_TERMS, normalized_input=True)
    control_terms = _matched_terms(normalized, _CONTROL_TERMS, normalized_input=True)
    if not auditor_names and not auditor_change_terms and not control_terms:
        return {}
    return {
        "auditor_names": auditor_names,
        "auditor_change_terms": auditor_change_terms,
        "control_terms": control_terms,
        "material_weakness": "material weakness" in normalized or "material weaknesses" in normalized,
        "ineffective_controls": "not effective" in normalized or "ineffective" in normalized,
        "non_reliance": "non reliance" in normalized or "non-reliance" in normalized,
        "source": source,
        "excerpt": _build_excerpt(text, control_terms or auditor_names or auditor_change_terms),
    }


def _extract_document_lines(report_html: str | None) -> list[str]:
    if not report_html:
        return []
    soup = BeautifulSoup(report_html, "html.parser")
    for element in soup(["script", "style", "ix:header"]):
        element.decompose()
    lines: list[str] = []
    for raw_line in soup.get_text("\n").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if len(line) < 2:
            continue
        if lines and line == lines[-1]:
            continue
        lines.append(line)
    return lines


def _extract_document_text(report_html: str | None) -> str:
    return "\n".join(_extract_document_lines(report_html))


def _first_matching_index(lines: list[str], patterns: tuple[str, ...]) -> int | None:
    compiled = [re.compile(pattern) for pattern in patterns]
    for index, line in enumerate(lines):
        if any(pattern.search(line) for pattern in compiled):
            return index
    return None


def _matched_terms(text: str, terms: tuple[str, ...], *, normalized_input: bool = False) -> list[str]:
    normalized = text if normalized_input else _normalize_text(text)
    matches = sorted({term for term in terms if term in normalized})
    return matches


def _build_excerpt(text: str, terms: tuple[str, ...] | list[str], *, line_limit: int = 3) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    normalized_lines = [_normalize_text(line) for line in lines]
    normalized_terms = [term for term in terms if term]
    for index, normalized_line in enumerate(normalized_lines):
        if normalized_terms and any(term in normalized_line for term in normalized_terms):
            excerpt = " ".join(lines[index:index + line_limit])
            return _clip_text(excerpt, limit=560)
    return _clip_text(" ".join(lines[:line_limit]), limit=560)


def _clip_text(text: str, *, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


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
