from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html
import re


@dataclass(slots=True)
class ProxyFilingSignals:
    meeting_date: date | None = None
    executive_comp_table_detected: bool = False
    vote_item_count: int = 0
    board_nominee_count: int | None = None
    key_amounts: tuple[float, ...] = ()
    vote_outcomes: tuple["ProxyVoteOutcome", ...] = ()


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

    return ProxyFilingSignals(
        meeting_date=meeting_date,
        executive_comp_table_detected=executive_comp_table_detected,
        vote_item_count=vote_item_count,
        board_nominee_count=board_nominee_count,
        key_amounts=key_amounts,
        vote_outcomes=vote_outcomes,
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
