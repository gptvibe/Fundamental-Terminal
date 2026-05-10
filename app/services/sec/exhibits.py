"""SEC exhibit metadata extraction and tagging.

Parses filing directory index responses from EDGAR to surface per-filing
exhibit lists with semantic tags.  No AI summarization is performed; all
data comes directly from official SEC EDGAR sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# ---------------------------------------------------------------------------
# Exhibit type → semantic tag mapping
# Ordered from most-specific prefix to least-specific so that the prefix scan
# below terminates on the right entry.
# ---------------------------------------------------------------------------
_EXHIBIT_TAG_PREFIXES: list[tuple[str, str]] = [
    ("EX-99.1", "earnings_release"),
    ("EX-99", "press_release"),
    ("EX-32", "certification_906"),
    ("EX-31", "certification_302"),
    ("EX-23", "auditor_consent"),
    ("EX-21", "subsidiaries"),
    ("EX-16", "auditor_letter"),
    ("EX-14", "code_of_ethics"),
    ("EX-101", "xbrl_data"),
    ("EX-10", "material_contract"),
    ("EX-4", "instrument_defining_rights"),
    ("EX-3", "charter_bylaws"),
]

_TAG_LABELS: dict[str, str] = {
    "earnings_release": "Earnings Release",
    "press_release": "Press Release",
    "material_contract": "Material Contract",
    "subsidiaries": "List of Subsidiaries",
    "certification_302": "SOX 302 Certification",
    "certification_906": "SOX 906 Certification",
    "auditor_consent": "Auditor Consent",
    "auditor_letter": "Auditor Letter",
    "code_of_ethics": "Code of Ethics",
    "xbrl_data": "XBRL Data",
    "instrument_defining_rights": "Instrument Defining Rights",
    "charter_bylaws": "Charter / Bylaws",
}


def tag_for_exhibit(exhibit_number: str) -> str | None:
    """Return a semantic tag string for a known exhibit type prefix, or None."""
    for prefix, tag in _EXHIBIT_TAG_PREFIXES:
        if exhibit_number == prefix or exhibit_number.startswith(prefix + ".") or exhibit_number.startswith(prefix + " "):
            return tag
    # Looser prefix match for bare prefixes (e.g. "EX-10.15" → "material_contract")
    for prefix, tag in _EXHIBIT_TAG_PREFIXES:
        if exhibit_number.startswith(prefix):
            return tag
    return None


def tag_label(tag: str | None) -> str | None:
    """Human-readable label for a tag, or None."""
    if tag is None:
        return None
    return _TAG_LABELS.get(tag)


@dataclass(slots=True)
class ExhibitMetadata:
    exhibit_number: str
    description: str | None
    document: str
    accession_number: str
    filing_type: str
    filing_date: date | None
    tag: str | None
    tag_label: str | None
    source_url: str


def extract_exhibits_from_index(
    cik: str,
    accession_number: str,
    filing_type: str,
    filing_date: date | None,
    directory_index: dict[str, Any],
) -> list[ExhibitMetadata]:
    """Parse an EDGAR filing directory index.json and return exhibit rows.

    Only items whose ``type`` field begins with ``"EX-"`` are returned.
    """
    items = directory_index.get("directory", {}).get("item", []) or []
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    base_url = f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}"

    exhibits: list[ExhibitMetadata] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        doc_type = str(item.get("type") or "").strip().upper()
        if not doc_type.startswith("EX-"):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        description = str(item.get("description") or "").strip() or None
        source_url = f"{base_url}/{name}"
        t = tag_for_exhibit(doc_type)
        exhibits.append(
            ExhibitMetadata(
                exhibit_number=doc_type,
                description=description,
                document=name,
                accession_number=accession_number,
                filing_type=filing_type,
                filing_date=filing_date,
                tag=t,
                tag_label=tag_label(t),
                source_url=source_url,
            )
        )
    return exhibits
