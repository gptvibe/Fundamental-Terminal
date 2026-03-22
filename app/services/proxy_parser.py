from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import html
import re


@dataclass(slots=True)
class ExecCompRow:
    """One named-executive officer row from the Summary Compensation Table."""
    executive_name: str
    executive_title: str | None = None
    fiscal_year: int | None = None
    salary: float | None = None
    bonus: float | None = None
    stock_awards: float | None = None
    option_awards: float | None = None
    non_equity_incentive: float | None = None
    other_compensation: float | None = None
    total_compensation: float | None = None


@dataclass(slots=True)
class ProxyFilingSignals:
    meeting_date: date | None = None
    executive_comp_table_detected: bool = False
    vote_item_count: int = 0
    board_nominee_count: int | None = None
    key_amounts: tuple[float, ...] = ()
    vote_outcomes: tuple["ProxyVoteOutcome", ...] = ()
    named_exec_rows: tuple[ExecCompRow, ...] = ()


@dataclass(slots=True)
class ProxyVoteOutcome:
    proposal_number: int
    title: str | None = None
    for_votes: int | None = None
    against_votes: int | None = None
    abstain_votes: int | None = None
    broker_non_votes: int | None = None


def parse_proxy_filing_signals(document_payload: str) -> ProxyFilingSignals:
    text = _collapse_document_text(document_payload)
    if not text:
        return ProxyFilingSignals()

    meeting_date = _extract_meeting_date(text)
    executive_comp_table_detected = "summary compensation table" in text.lower()
    vote_outcomes = _extract_vote_outcomes(text)
    vote_item_count = len(vote_outcomes) or _count_vote_proposals(text)
    board_nominee_count = _extract_board_nominee_count(text)
    key_amounts = _extract_key_amounts(text)
    named_exec_rows = _extract_exec_comp_rows(document_payload, text) if executive_comp_table_detected else ()

    return ProxyFilingSignals(
        meeting_date=meeting_date,
        executive_comp_table_detected=executive_comp_table_detected,
        vote_item_count=vote_item_count,
        board_nominee_count=board_nominee_count,
        key_amounts=key_amounts,
        vote_outcomes=vote_outcomes,
        named_exec_rows=named_exec_rows,
    )


def _collapse_document_text(document_payload: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", document_payload)
    unescaped = html.unescape(no_tags)
    normalized = re.sub(r"\s+", " ", unescaped)
    return normalized.strip()


def _extract_meeting_date(text: str) -> date | None:
    patterns = [
        r"(?i)annual\s+meeting\s+of\s+shareholders\s+(?:will\s+be\s+held\s+on|is\s+scheduled\s+for)\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"(?i)date\s+of\s+annual\s+meeting\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        parsed = _parse_month_day_year(match.group(1))
        if parsed is not None:
            return parsed
    return None


def _parse_month_day_year(value: str) -> date | None:
    cleaned = value.strip()
    for fmt in [
        "%B %d, %Y",
        "%b %d, %Y",
    ]:
        try:
            from datetime import datetime

            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _count_vote_proposals(text: str) -> int:
    # Deterministic heuristic: count proposal headings and de-duplicate by number.
    proposal_numbers = {
        int(match.group(1))
        for match in re.finditer(r"(?i)proposal\s+(\d{1,2})\b", text)
    }
    if proposal_numbers:
        return len(proposal_numbers)

    # Fallback when no numbered headings exist.
    vote_markers = len(re.findall(r"(?i)\b(for|against|abstain)\b", text))
    if vote_markers >= 3:
        return 1
    return 0


def _extract_board_nominee_count(text: str) -> int | None:
    match = re.search(r"(?i)nominees?\s+for\s+director\s*[:\-]?\s*(\d{1,2})", text)
    if match:
        return int(match.group(1))

    # Alternative proxy phrasing: "elect X directors".
    match = re.search(r"(?i)elect\s+(\d{1,2})\s+directors?", text)
    if match:
        return int(match.group(1))
    return None


def _extract_key_amounts(text: str) -> tuple[float, ...]:
    if "summary compensation table" not in text.lower():
        return ()

    amounts: list[float] = []
    for match in re.finditer(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)", text):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if value <= 0:
            continue
        amounts.append(value)
        if len(amounts) >= 3:
            break

    return tuple(amounts)


def _extract_vote_outcomes(text: str) -> tuple[ProxyVoteOutcome, ...]:
    matches = list(re.finditer(r"(?i)\bproposal\s+(\d{1,2})\b", text))
    if not matches:
        return ()

    outcomes: list[ProxyVoteOutcome] = []
    for index, match in enumerate(matches):
        block_start = match.start()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[block_start:block_end]
        proposal_number = int(match.group(1))

        title = _extract_proposal_title(block)
        for_votes = _extract_vote_metric(block, "for")
        against_votes = _extract_vote_metric(block, "against")
        abstain_votes = _extract_vote_metric(block, "abstain")
        broker_non_votes = _extract_vote_metric(block, "broker\\s+non[- ]?votes?")

        if (
            for_votes is None
            and against_votes is None
            and abstain_votes is None
            and broker_non_votes is None
            and title is None
        ):
            continue

        outcomes.append(
            ProxyVoteOutcome(
                proposal_number=proposal_number,
                title=title,
                for_votes=for_votes,
                against_votes=against_votes,
                abstain_votes=abstain_votes,
                broker_non_votes=broker_non_votes,
            )
        )

    return tuple(outcomes)


def _extract_proposal_title(block: str) -> str | None:
    title_match = re.search(
        r"(?is)\bproposal\s+\d{1,2}\b\s*[:\-]?\s*(.*?)(?:\bfor\b|\bagainst\b|\babstain\b|\bbroker\b|$)",
        block,
    )
    if not title_match:
        return None
    cleaned = re.sub(r"\s+", " ", title_match.group(1)).strip(" .;:-")
    if not cleaned:
        return None
    return cleaned[:160]


def _extract_vote_metric(block: str, label_pattern: str) -> int | None:
    pattern = rf"(?is)\b{label_pattern}\b\D{{0,24}}([0-9][0-9,]*)"
    match = re.search(pattern, block)
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Executive Compensation Table Extraction
# ---------------------------------------------------------------------------

# Column-header keyword → field mapping (order matters for the column scan).
_COMP_COL_KEYWORDS: list[tuple[str, str]] = [
    ("salary", "salary"),
    ("bonus", "bonus"),
    ("stock award", "stock_awards"),
    ("option award", "option_awards"),
    ("non-equity", "non_equity_incentive"),
    ("non equity", "non_equity_incentive"),
    ("all other", "other_compensation"),
    ("other comp", "other_compensation"),
    ("total", "total_compensation"),
]


def _extract_exec_comp_rows(raw_html: str, flat_text: str) -> tuple[ExecCompRow, ...]:
    """Attempt to extract named-executive rows from the Summary Compensation Table.

    Two strategies are tried in order:
    1. HTML table parsing — walks ``<table>`` tags, identifies the header row
       containing "salary", maps columns, then reads data rows.
    2. Line-by-line text fallback — scans the flat text for a line that looks
       like an executive name adjacent to dollar-amount columns.
    """
    rows = _extract_via_html_table(raw_html)
    if rows:
        return tuple(rows)
    return tuple(_extract_via_text_lines(flat_text))


def _extract_via_html_table(raw_html: str) -> list[ExecCompRow]:
    """Parse named-executive rows from an HTML summary compensation table."""
    # Find table blocks that contain "summary compensation table" context.
    table_pattern = re.compile(r"(?is)<table[^>]*>(.*?)</table>")
    rows: list[ExecCompRow] = []

    for table_match in table_pattern.finditer(raw_html):
        table_html = table_match.group(0)
        if "salary" not in table_html.lower():
            continue

        # Extract all rows from this table.
        tr_pattern = re.compile(r"(?is)<tr[^>]*>(.*?)</tr>")
        td_pattern = re.compile(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>")

        all_rows = tr_pattern.findall(table_html)
        if not all_rows:
            continue

        # Find the header row and map column indices to field names.
        col_map: dict[int, str] = {}
        name_col: int | None = None
        year_col: int | None = None
        title_col: int | None = None
        header_row_index: int | None = None

        for row_index, row_html in enumerate(all_rows):
            cells = [_strip_tags(cell) for cell in td_pattern.findall(row_html)]
            if not cells:
                continue
            cell_text_lower = [c.lower().strip() for c in cells]

            # Detect header by looking for "salary" among cells.
            if any("salary" in c for c in cell_text_lower):
                for col_i, cell_lower in enumerate(cell_text_lower):
                    if "name" in cell_lower or "principal" in cell_lower:
                        name_col = col_i
                    elif "title" in cell_lower or "position" in cell_lower:
                        title_col = col_i
                    elif "year" in cell_lower or "fiscal" in cell_lower:
                        year_col = col_i
                    else:
                        for keyword, field_name in _COMP_COL_KEYWORDS:
                            if keyword in cell_lower and col_i not in col_map:
                                col_map[col_i] = field_name
                                break
                header_row_index = row_index
                break

        if header_row_index is None or not col_map:
            continue

        # Read data rows after the header.
        for row_html in all_rows[header_row_index + 1:]:
            cells = [_strip_tags(cell).strip() for cell in td_pattern.findall(row_html)]
            if not cells or len(cells) < 2:
                continue

            # Name column: default to first column if we couldn't identify it.
            name_col_idx = name_col if name_col is not None else 0
            if name_col_idx >= len(cells):
                continue
            raw_name = cells[name_col_idx].strip()
            if not raw_name or _looks_like_number(raw_name):
                continue

            exec_row = ExecCompRow(executive_name=raw_name[:200])

            if title_col is not None and title_col < len(cells):
                raw_title = cells[title_col].strip()
                if raw_title:
                    exec_row.executive_title = raw_title[:200]

            if year_col is not None and year_col < len(cells):
                year_val = _parse_year(cells[year_col])
                if year_val:
                    exec_row.fiscal_year = year_val

            for col_i, field_name in col_map.items():
                if col_i < len(cells):
                    amount = _parse_amount(cells[col_i])
                    if amount is not None and amount > 0:
                        setattr(exec_row, field_name, amount)

            # Accept the row if at least salary or total is populated.
            if exec_row.salary is not None or exec_row.total_compensation is not None:
                rows.append(exec_row)

        if rows:
            return rows

    return rows


def _extract_via_text_lines(flat_text: str) -> list[ExecCompRow]:
    """Fallback: scan the flat text around 'Summary Compensation Table' for
    lines that pair a name/title with a series of dollar figures."""
    lower = flat_text.lower()
    start_idx = lower.find("summary compensation table")
    if start_idx == -1:
        return []

    # Take up to 4000 chars after the table heading.
    segment = flat_text[start_idx: start_idx + 4000]

    # A "data line" must have a non-numeric starting word and contain
    # at least two dollar amounts.
    line_pattern = re.compile(
        r"(?m)^([A-Z][A-Za-z\s\.\,]{2,50}?)\s+"
        r"(\d{4})?\s*"                       # optional year
        r"((?:\$?\s*[\d,]+\s+){2,})",        # two or more number groups
    )
    rows: list[ExecCompRow] = []
    for match in line_pattern.finditer(segment):
        name_part = match.group(1).strip()
        year_part = match.group(2)
        numbers_part = match.group(3)

        if not name_part or _looks_like_number(name_part):
            continue

        amounts = [
            float(n.replace(",", ""))
            for n in re.findall(r"[\d,]+", numbers_part)
            if "." not in n or len(n.replace(",", "")) > 3
        ]
        # Heuristic: last number is total, first is salary.
        exec_row = ExecCompRow(executive_name=name_part[:200])
        if year_part:
            exec_row.fiscal_year = _parse_year(year_part)
        if len(amounts) >= 1:
            exec_row.salary = amounts[0] if amounts[0] > 0 else None
        if len(amounts) >= 2:
            exec_row.total_compensation = amounts[-1] if amounts[-1] > 0 else None

        if exec_row.salary is not None or exec_row.total_compensation is not None:
            rows.append(exec_row)
        if len(rows) >= 10:
            break

    return rows


def _strip_tags(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(re.sub(r"\s+", " ", no_tags)).strip()


def _looks_like_number(value: str) -> bool:
    cleaned = value.replace(",", "").replace("$", "").strip()
    try:
        float(cleaned)
        return True
    except ValueError:
        return False


def _parse_amount(value: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", value.replace(",", ""))
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_year(value: str) -> int | None:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", value)
    if match:
        return int(match.group(1))
    return None
