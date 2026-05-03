from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


SUPPORTED_FILING_RISK_SIGNAL_FORMS = {"10-K", "10-Q", "8-K"}


@dataclass(frozen=True, slots=True)
class FilingRiskSignalMatch:
    ticker: str | None
    cik: str
    accession_number: str
    form_type: str
    filed_date: date | None
    signal_category: str
    matched_phrase: str
    context_snippet: str
    confidence: str
    severity: str
    source: str
    provenance: str


@dataclass(frozen=True, slots=True)
class _SignalRule:
    category: str
    patterns: tuple[re.Pattern[str], ...]
    confidence: str
    severity: str


_WHITESPACE_RE = re.compile(r"\s+")

_SIGNAL_RULES: tuple[_SignalRule, ...] = (
    _SignalRule(
        category="material_weakness",
        patterns=(
            re.compile(r"\bmaterial weakness(?:es)?\b", re.IGNORECASE),
            re.compile(r"\bmaterial weakness in internal control(?: over financial reporting)?\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="high",
    ),
    _SignalRule(
        category="going_concern",
        patterns=(
            re.compile(r"\bsubstantial doubt\b", re.IGNORECASE),
            re.compile(r"\bgoing concern\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="high",
    ),
    _SignalRule(
        category="customer_concentration",
        patterns=(
            re.compile(r"\bcustomer concentration\b", re.IGNORECASE),
            re.compile(r"\b(?:single|major|largest) customer\b.{0,80}\b(?:represented|accounted for|accounts? for)\b", re.IGNORECASE),
            re.compile(r"\bconcentrated in a small number of customers\b", re.IGNORECASE),
        ),
        confidence="medium",
        severity="medium",
    ),
    _SignalRule(
        category="supplier_concentration",
        patterns=(
            re.compile(r"\bsupplier concentration\b", re.IGNORECASE),
            re.compile(r"\b(?:single|sole|major|largest) supplier\b.{0,80}\b(?:represented|accounted for|accounts? for|depend(?:s|ence))\b", re.IGNORECASE),
            re.compile(r"\bsole source supplier\b", re.IGNORECASE),
        ),
        confidence="medium",
        severity="medium",
    ),
    _SignalRule(
        category="covenant_risk",
        patterns=(
            re.compile(r"\bcovenant breach\b", re.IGNORECASE),
            re.compile(r"\bin breach of (?:a )?covenant\b", re.IGNORECASE),
            re.compile(r"\bnot in compliance with (?:the )?(?:financial )?covenants?\b", re.IGNORECASE),
            re.compile(r"\bcovenant compliance\b", re.IGNORECASE),
            re.compile(r"\bwaiver(?:s)? of (?:a )?covenant\b", re.IGNORECASE),
        ),
        confidence="medium",
        severity="high",
    ),
    _SignalRule(
        category="impairment",
        patterns=(
            re.compile(r"\bimpairment (?:charge|charges|loss|losses)\b", re.IGNORECASE),
            re.compile(r"\basset impairment\b", re.IGNORECASE),
            re.compile(r"\bgoodwill impairment\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="medium",
    ),
    _SignalRule(
        category="restructuring",
        patterns=(
            re.compile(r"\brestructuring (?:plan|plans|charge|charges|program|programs|initiative|initiatives)\b", re.IGNORECASE),
            re.compile(r"\bworkforce reduction\b", re.IGNORECASE),
            re.compile(r"\bcost reduction plan\b", re.IGNORECASE),
        ),
        confidence="medium",
        severity="medium",
    ),
    _SignalRule(
        category="cybersecurity_incident",
        patterns=(
            re.compile(r"\bcybersecurity incident\b", re.IGNORECASE),
            re.compile(r"\bmaterial cyber(?:security)? incident\b", re.IGNORECASE),
            re.compile(r"\bdata breach\b", re.IGNORECASE),
            re.compile(r"\bransomware\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="high",
    ),
    _SignalRule(
        category="restatement",
        patterns=(
            re.compile(r"\brestatement\b", re.IGNORECASE),
            re.compile(r"\bnon-reliance on previously issued financial statements\b", re.IGNORECASE),
            re.compile(r"\bshould no longer be relied upon\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="high",
    ),
    _SignalRule(
        category="late_filing",
        patterns=(
            re.compile(r"\blate filing\b", re.IGNORECASE),
            re.compile(r"\bunable to timely file\b", re.IGNORECASE),
            re.compile(r"\bnotification of late filing\b", re.IGNORECASE),
            re.compile(r"\bNT\s+(?:10-K|10-Q|20-F|11-K)\b", re.IGNORECASE),
        ),
        confidence="high",
        severity="high",
    ),
)


def extract_filing_risk_signals(
    *,
    cik: str,
    filing_metadata: Any,
    filing_text: str,
    ticker: str | None = None,
    source: str | None = None,
    provenance: str = "sec_filing_text",
) -> list[FilingRiskSignalMatch]:
    accession_number = str(getattr(filing_metadata, "accession_number", "") or "").strip()
    form_type = _base_form(getattr(filing_metadata, "form", None))
    if not accession_number or form_type not in SUPPORTED_FILING_RISK_SIGNAL_FORMS:
        return []

    normalized_text = _normalize_text(filing_text)
    if not normalized_text:
        return []

    filed_date = getattr(filing_metadata, "filing_date", None)
    source_value = str(source or "cached_sec_filing_text")
    matches: list[FilingRiskSignalMatch] = []
    seen: set[tuple[str, str]] = set()

    for rule in _SIGNAL_RULES:
        best_match = _first_match(rule, normalized_text)
        if best_match is None:
            continue
        matched_phrase = best_match.group(0).strip()
        dedupe_key = (rule.category, matched_phrase.casefold())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        matches.append(
            FilingRiskSignalMatch(
                ticker=ticker,
                cik=cik,
                accession_number=accession_number,
                form_type=form_type,
                filed_date=filed_date,
                signal_category=rule.category,
                matched_phrase=matched_phrase,
                context_snippet=_build_context_snippet(normalized_text, best_match.start(), best_match.end()),
                confidence=rule.confidence,
                severity=_severity_for_match(rule, matched_phrase),
                source=source_value,
                provenance=provenance,
            )
        )

    return matches


def _base_form(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        return ""
    return normalized.split("/")[0].split()[0]


def _normalize_text(value: str | None) -> str:
    text = str(value or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _first_match(rule: _SignalRule, filing_text: str) -> re.Match[str] | None:
    for pattern in rule.patterns:
        match = pattern.search(filing_text)
        if match is not None:
            return match
    return None


def _build_context_snippet(filing_text: str, start: int, end: int, window: int = 140) -> str:
    snippet_start = max(0, start - window)
    snippet_end = min(len(filing_text), end + window)
    snippet = filing_text[snippet_start:snippet_end].strip()
    if snippet_start > 0:
        snippet = f"...{snippet}"
    if snippet_end < len(filing_text):
        snippet = f"{snippet}..."
    return snippet


def _severity_for_match(rule: _SignalRule, matched_phrase: str) -> str:
    phrase = matched_phrase.casefold()
    if rule.category == "covenant_risk" and "compliance" in phrase and "not in compliance" not in phrase:
        return "medium"
    return rule.severity


__all__ = ["FilingRiskSignalMatch", "SUPPORTED_FILING_RISK_SIGNAL_FORMS", "extract_filing_risk_signals"]